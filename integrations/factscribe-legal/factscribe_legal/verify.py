"""法律专项校验：把「事实的来源是法条」这件事变成机械判定。

上游 FactScribe 判的是：正文数字 → 事实账 → 材料哈希。
本包判的是**法律这一层**：

  红
    LEGAL_PROV_UNKNOWN          引用/来源的法条在语料里不存在
    LEGAL_PROV_HASH_MISMATCH    钉的哈希与官方 XML 现算不符（法条被人动过）
    LEGAL_PROV_NOT_IN_FORCE     参考日当天该版本不生效（引用了旧版或未来版）
    LEGAL_QUOTE_MISMATCH        事实里的值并不出现在该法条的官方正文里
    LEGAL_FACT_NOT_PROVISION    事实声称来源是法条，但 source 指向的不是 provisions/
  黄
    LEGAL_PROV_SCHEDULED        引用的是已排期、尚未生效的版本
    LEGAL_PROV_REPEALED         引用的是已废止版本

退出码沿用上游：0 绿 / 1 红 / 2 配置错 / 3 黄
"""
import hashlib
import os
import re

from ._toml import load_toml
from .provisions import load_corpus, load_view

CITE_RE = re.compile(r"\\cite[a-zA-Z]*\{([^}]*)\}")
# 事实的 source 可以是官方 XML 本体，也可以是「法条证据卡」（派生件，内含官方 XML 哈希声明）
PROV_RE = re.compile(r"^(?P<dir>.+)/(?P<num>[^/]+?)(?:\.card\.txt|\.xml)$")
CARD_SHA_RE = re.compile(r"^OFFICIAL_XML_SHA256:\s*([0-9a-f]{64})\s*$", re.M)
CARD_FIELD_RE = re.compile(r"^(?P<k>[A-Z_]+):\s*(?P<v>.*)$", re.M)


def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_it_card(path):
    """证据卡是不是意大利侧的（看卡内自己的标记字段，不靠目录名猜）。"""
    try:
        with open(path, encoding="utf-8") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    return "ARTICLE_EID:" in head and "ACT_URN:" in head


class Finding:
    def __init__(self, code, severity, location, message, detail=""):
        self.code = code
        self.severity = severity      # red | yellow
        self.location = location
        self.message = message
        self.detail = detail

    def __repr__(self):
        return f"[{self.severity}] {self.code} {self.location} — {self.message}"


def load_facts(project_dir):
    facts = []
    fdir = os.path.join(project_dir, "facts")
    if not os.path.isdir(fdir):
        return facts
    for name in sorted(os.listdir(fdir)):
        if not name.endswith(".toml"):
            continue
        data = load_toml(os.path.join(fdir, name))
        for fact in data.get("fact", []):
            fact["_file"] = f"facts/{name}"
            facts.append(fact)
    return facts


def load_citations(project_dir):
    """扫 .tex 里的 \\cite{...}，返回 [(key, file, line)]"""
    out = []
    for root, _dirs, files in os.walk(project_dir):
        if any(p in root for p in ("/.git", "/audit", "/vendor")):
            continue
        for fn in files:
            if not fn.endswith(".tex"):
                continue
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, project_dir)
            with open(path, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    for m in CITE_RE.finditer(line):
                        for key in m.group(1).split(","):
                            out.append((key.strip(), rel, i))
    return out


def verify(project_dir, provisions_dir, reference_date, view_path=None):
    """跑法律专项校验，返回 findings 列表。"""
    findings = []
    corpus = load_corpus(provisions_dir)
    view = load_view(view_path) if view_path else {}

    # ---- 1. 事实账里指向法条的 fact ----
    for fact in load_facts(project_dir):
        src = fact.get("source", "")
        if src.endswith(".cn.card.txt"):
            # 中国侧证据卡：不属法国语料（两侧共用一个项目，各判各的）
            continue
        if src.endswith(".case.card.txt"):
            # 中国案例维度证据卡：归第 5 层 legal-case 判，这里跳过
            continue
        if src.endswith(".it.card.txt"):
            # 意大利证据卡：归意大利专闸（verify-it）判，这里跳过
            continue
        if src.endswith(".es.card.txt"):
            # 西班牙证据卡：归西班牙专闸（verify-es）判，这里跳过
            continue
        if src.endswith(".fr-case.card.txt"):
            # 法国判例证据卡：归法国判例专闸（verify-fr-case）判，这里跳过
            # （不加这行，PROV_RE 兜底会把判例卡当成法条卡报 LEGAL_PROV_UNKNOWN 假红）
            continue
        m = PROV_RE.match(src)
        if not m:
            continue
        num = m.group("num")
        loc = f"{fact['_file']}:{fact.get('id', '?')}"
        prov = corpus.get(num)
        if prov is None:
            findings.append(Finding("LEGAL_PROV_UNKNOWN", "red", loc,
                                     f"法条 {num} 不在语料里（{provisions_dir}）"))
            continue
        # ---- 哈希现算比对 ----
        # source 直接指向官方 XML ⇒ 比对事实账钉的哈希
        # source 指向证据卡 ⇒ 比对卡片里声明的官方 XML 哈希与现算值（两层都不丢）
        pinned = (fact.get("source_sha256") or "").removeprefix("sha256:").lower()
        if src.endswith(".card.txt"):
            card_path = os.path.join(project_dir, src)
            declared = ""
            if os.path.exists(card_path):
                with open(card_path, encoding="utf-8") as fh:
                    card = fh.read()
                cm = CARD_SHA_RE.search(card)
                declared = (cm.group(1) if cm else "").lower()
            if not declared:
                findings.append(Finding(
                    "LEGAL_CARD_NO_HASH", "red", loc,
                    f"证据卡 {src} 里没有 OFFICIAL_XML_SHA256 声明"))
            elif declared != prov.xml_sha256:
                findings.append(Finding(
                    "LEGAL_PROV_HASH_MISMATCH", "red", loc,
                    f"法条 {num} 的官方 XML 哈希与证据卡声明不符"
                    f"（卡 {declared[:12]}… / 现算 {prov.xml_sha256[:12]}…）——材料被改过"))
            elif pinned and pinned != _sha256_file(os.path.join(project_dir, src)):
                findings.append(Finding(
                    "LEGAL_CARD_SHA256_MISMATCH", "red", loc,
                    f"证据卡 {src} 自身被改过（事实账钉的哈希与现算不符）"))
        elif pinned and pinned != prov.xml_sha256:
            findings.append(Finding(
                "LEGAL_PROV_HASH_MISMATCH", "red", loc,
                f"法条 {num} 的 XML 哈希与事实账不符"
                f"（账 {pinned[:12]}… / 现算 {prov.xml_sha256[:12]}…）——材料被改过"))
        # 生效判定
        if prov.scheduled_at(reference_date):
            findings.append(Finding("LEGAL_PROV_SCHEDULED", "yellow", loc,
                                     f"法条 {num} 到 {prov.date_debut} 才生效"
                                     f"（参考日 {reference_date}）"))
        elif prov.repealed_at(reference_date):
            findings.append(Finding("LEGAL_PROV_REPEALED", "yellow", loc,
                                     f"法条 {num} 已于 {prov.date_fin} 失效"))
        elif not prov.in_force_at(reference_date):
            findings.append(Finding("LEGAL_PROV_NOT_IN_FORCE", "red", loc,
                                     f"法条 {num} 在参考日 {reference_date} 不生效"
                                     f"（{prov.date_debut} → {prov.date_fin}）"))
        # 视图交叉验证
        if view:
            v = view.get(num)
            if v and v.get("id") != prov.legiarti:
                findings.append(Finding(
                    "LEGAL_PROV_VIEW_MISMATCH", "yellow", loc,
                    f"法条 {num} 与现行视图不是同一个版本"
                    f"（语料 {prov.legiarti} / 视图 {v.get('id')}）"))
        # 事实的值是否真的出自该法条
        val = fact.get("value")
        if val is not None and prov.text and not prov.contains_number(val):
            findings.append(Finding(
                "LEGAL_QUOTE_MISMATCH", "red", loc,
                f"事实 {fact.get('id')} 的值 {val} 不出现在法条 {num} 的官方正文里"))

    # ---- 1b. 版本池覆盖度：池子比参考日落后几天 ----
    pool_asof = ""
    for prov in corpus.values():
        pool_asof = prov.extra.get("pool_asof") or pool_asof
    if pool_asof and reference_date > pool_asof:
        try:
            from datetime import date as _d
            gap = (_d(*map(int, reference_date.split("-"))) -
                   _d(*map(int, pool_asof.split("-")))).days
        except Exception:
            gap = -1
        if gap > 0:
            findings.append(Finding(
                "LEGAL_COVERAGE_GAP", "yellow", "corpus",
                f"版本池的数据截止日是 {pool_asof}，比参考日 {reference_date} 落后 {gap} 天"
                f"——这段时间内的法律变化不在池子里；引用仍是「池内最新」，"
                f"不是「今日最新」（要当日最新请先拉日更增量包）"))

    # ---- 1c. 参考日唯一性：同一编号在参考日有且只有一个生效版本 ----
    for num, prov in sorted(corpus.items()):
        vers = prov.extra.get("versions") or []
        if not vers:
            continue
        live = [v for v in vers
                if v.get("date_debut") and v["date_debut"] <= reference_date
                and (not v.get("date_fin") or reference_date < v["date_fin"])]
        if len(live) > 1:
            findings.append(Finding(
                "LEGAL_PROV_AMBIGUOUS", "yellow", f"corpus:{num}",
                f"{num} 在参考日 {reference_date} 有 {len(live)} 个版本同时生效"
                f"（数据异常，需人工看版本链）"))

    # ---- 2. 正文里的法条引用 ----
    for key, rel, line in load_citations(project_dir):
        if re.search(r"[\u4e00-\u9fff]", key):
            # 中文法规引用归中国闸管
            continue
        if key.startswith("art-it-"):
            # 意大利法条引用归意大利专闸（verify-it）判，这里跳过
            continue
        if key.startswith("art-es-"):
            # 西班牙法条引用归西班牙专闸（verify-es）判，这里跳过
            continue
        if key.startswith("art:"):
            num = key[4:]
        elif key.startswith("art-"):
            num = key[4:]
        else:
            continue
        prov = corpus.get(num)
        loc = f"{rel}:{line}"
        if prov is None:
            findings.append(Finding("LEGAL_PROV_UNKNOWN", "red", loc,
                                     f"引用了语料里没有的法条 {num}"))
            continue
        if prov.scheduled_at(reference_date):
            findings.append(Finding("LEGAL_PROV_SCHEDULED", "yellow", loc,
                                     f"引用的 {num} 到 {prov.date_debut} 才生效"))
        elif prov.repealed_at(reference_date):
            findings.append(Finding("LEGAL_PROV_REPEALED", "yellow", loc,
                                     f"引用的 {num} 已于 {prov.date_fin} 失效"))
        elif not prov.in_force_at(reference_date):
            findings.append(Finding("LEGAL_PROV_NOT_IN_FORCE", "red", loc,
                                     f"引用的 {num} 在参考日 {reference_date} 不生效"))

    return findings, corpus


def render(findings, corpus=None):
    reds = [f for f in findings if f.severity == "red"]
    yellows = [f for f in findings if f.severity == "yellow"]
    lines = ["== factscribe-legal verify =="]
    if corpus:
        lines.append(f"corpus : {len(corpus)} 条法条")
    lines.append("")
    if yellows:
        lines.append(f"[黄] {len(yellows)} 处")
        for i, f in enumerate(yellows, 1):
            lines.append(f"  {i}. {f.code:28s} {f.location}  →  {f.message}")
        lines.append("")
    if reds:
        lines.append(f"[红] {len(reds)} 处（必须修）")
        for i, f in enumerate(reds, 1):
            lines.append(f"  {i}. {f.code:28s} {f.location}  →  {f.message}")
    else:
        lines.append("[红] 0 处")
    lines.append("")
    total = len(reds) + len(yellows)
    if reds:
        lines.append(f"结论：{len(reds)} 红 / {len(yellows)} 黄 → 红（退出码 1）")
    elif yellows:
        lines.append(f"结论：0 红 / {len(yellows)} 黄 → 黄（退出码 3）")
    else:
        lines.append("结论：0 红 / 0 黄 → 绿（退出码 0）")
    lines.append("注意：绿只代表「引用的法条真实存在、哈希未变、且在参考日生效」，不代表法条写得对。")
    return "\n".join(lines), (1 if reds else (3 if yellows else 0))
