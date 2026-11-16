"""法条模型与语料读取。

「语料」= 一份证据包：
    provisions/
      index.json        索引（每条法条的官方 XML 路径 + 哈希 + 生效区间）
      <编号>.xml        官方条文 XML 原字节（被事实账钉哈希的对象）

另可挂一份「视图」JSONL（我们管线的现行版），用来回答「某条文在参考日是否生效」——
因为 index.json 里的 date_debut/date_fin 已经是权威字段，视图只是交叉验证。
"""
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, fields

# 法文数字词（0–99，含 alors/soixante-dix/quatre-vingt-dix 等 70–99 的复合）
_UNITS = {
    "zero": 0, "une": 1, "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
    "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "dix-sept": 17,
    "dix-huit": 18, "dix-neuf": 19, "vingt": 20, "trente": 30, "quarante": 40,
    "cinquante": 50, "soixante": 60,
}
_TENS = {"vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}
_UNIT_WORDS = set(_UNITS)


def fr_number_to_int(s):
    """把法文数字词转成整数：'trente-cinq' → 35；'quatre-vingt-dix' → 90。
    认不出的返回 None。"""
    if not s:
        return None
    s = s.strip().lower().replace(" ", "-")
    if s in _UNITS:
        return _UNITS[s]
    m = re.fullmatch(r"(quatre-vingt)(s)?-([a-z]+)?", s)
    if m:
        base = 80
        rest = m.group(3)
        if rest is None:
            return base
        if rest == "dix":
            return 90
        return base + _UNITS.get(rest, 0) if rest in _UNITS else None
    if "-" in s:
        head, _, tail = s.partition("-")
        if head in _TENS and tail in _UNIT_WORDS:
            return _TENS[head] + _UNITS[tail]
        # soixante-dix / soixante et onze …
        if head == "soixante" and tail in _UNITS:
            v = _UNITS[tail]
            return 60 + v if v >= 10 else 60 + v
    return None


def norm_text(el):
    """与 Légifrance 管线一致的正文归一：<br> 换行、空白归一、**不去重相邻重复行**。"""
    parts = []

    def rec(node):
        if node.tag == "br":
            parts.append("\n")
            return
        if node.text:
            parts.append(node.text)
        for c in node:
            rec(c)
            if c.tail:
                parts.append(c.tail)

    rec(el)
    lines = []
    for ln in "".join(parts).split("\n"):
        s = re.sub(r"[ \t\u00a0\u202f]+", " ", ln).strip()
        if s:
            lines.append(s)
    return "\n".join(lines)


@dataclass
class Provision:
    """一条法条（官方 XML 的某一条版本）。"""
    num: str
    legiarti: str = ""
    code_id: str = ""
    etat: str = ""
    date_debut: str = ""
    date_fin: str = ""
    xml_file: str = ""
    xml_sha256: str = ""
    text_sha256: str = ""
    text: str = field(default="", repr=False)
    xml_bytes: int = 0
    text_chars: int = 0
    extra: dict = field(default_factory=dict, repr=False)

    # ---------- 生效判定 ----------
    def in_force_at(self, date):
        """date_debut <= date < date_fin 才算当天生效。
        ⚠️ 不能用 etat 判：etat=VIGUEUR 的版本可能只是「未来才生效」。"""
        if not self.date_debut:
            return False
        if self.date_debut > date:
            return False
        if self.date_fin and self.date_fin <= date:
            return False
        return True

    def scheduled_at(self, date):
        return bool(self.date_debut) and self.date_debut > date

    def repealed_at(self, date):
        return bool(self.date_fin) and self.date_fin <= date

    # ---------- 正文查询 ----------
    def contains_number(self, value):
        """事实的值是否真的出自这条法条。
        数字既可能写成阿拉伯数字，也可能写成法文数字词（'trente-cinq heures'）。"""
        if value is None:
            return False
        raw = str(value).strip().rstrip("%")
        try:
            n = int(float(raw))
        except ValueError:
            return False
        text = self.text
        # 阿拉伯数字（带词边界，避免 3 命中 35）
        if re.search(r"(?<![\d.,])" + re.escape(str(n)) + r"(?![\d.,])", text):
            return True
        # 法文数字词
        for word in _fr_spellings(n):
            if re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", text, re.I):
                return True
        return False


def _fr_spellings(n):
    """给出 n 的法文写法候选（含带连字符/不带连字符两种）。"""
    if n < 0 or n > 99:
        return []
    out = []
    if n < 20:
        for k, v in _UNITS.items():
            if v == n and k not in ("zéro",):
                out.append(k)
    elif n % 10 == 0 and n in _TENS.values():
        for k, v in _TENS.items():
            if v == n:
                out.append(k)
    else:
        tens = (n // 10) * 10
        unit = n % 10
        tk = next((k for k, v in _TENS.items() if v == tens), None)
        uk = next((k for k, v in _UNITS.items() if v == unit), None)
        if tens == 60 and unit >= 11:
            base = next((k for k, v in _UNITS.items() if v == 10 + unit), None)
            if base:
                out.append(f"soixante-{base}")
                out.append(f"soixante et {base.replace('-', ' ')}")
        elif tens == 80:
            rest = unit
            if rest == 0:
                out.append("quatre-vingts")
            elif unit == 1:
                out.append("quatre-vingt-un")
            else:
                rk = next((k for k, v in _UNITS.items() if v == rest), None)
                if rk:
                    out.append(f"quatre-vingt-{rk}")
        elif tk and uk:
            out.append(f"{tk}-{uk}")
            out.append(f"{tk} {uk}")
    return out


def load_corpus(provisions_dir):
    """读证据包 → {编号: Provision}"""
    idx_path = os.path.join(provisions_dir, "index.json")
    if not os.path.exists(idx_path):
        raise FileNotFoundError(f"找不到 {idx_path}")
    with open(idx_path, encoding="utf-8") as fh:
        idx = json.load(fh)
    out = {}
    known = {f.name for f in fields(Provision)}
    pool_asof = str(idx.get("pool_asof") or "").strip()
    for num, meta in idx.get("provisions", {}).items():
        p = Provision(num=num, **{k: v for k, v in meta.items()
                                   if k in known and k != "num"})
        # 索引里可能带额外字段（同编号的历史版本清单等），挂到 extra 上
        p.extra = {k: v for k, v in meta.items() if k not in known}
        p.extra["pool_asof"] = pool_asof
        xml_path = os.path.join(provisions_dir, meta.get("xml_file", f"{num}.xml"))
        if os.path.exists(xml_path):
            with open(xml_path, "rb") as fh:
                raw = fh.read()
            p.xml_bytes = len(raw)
            p.xml_sha256 = hashlib.sha256(raw).hexdigest()
            root = ET.fromstring(raw)
            p.text = norm_text(root.find("BLOC_TEXTUEL"))
            p.text_sha256 = hashlib.sha256(p.text.encode("utf-8")).hexdigest()
        out[num] = p
    return out


def load_view(path):
    """管线的现行版视图 → {编号: record}（用于交叉验证生效状态）"""
    if not path or not os.path.exists(path):
        return {}
    out = {}
    opener = __import__("gzip").open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out.setdefault(r["num"], r)
    return out
