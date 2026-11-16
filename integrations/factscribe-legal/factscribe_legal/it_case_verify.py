"""意大利**宪法法院判例**维度专项校验：把「引的是哪件判决、官方判决正文有没有被动过、
那个金额/日期是不是真出自那份判决正文」变成机械判定。

与法条维度（verify-it，Normattiva AKN）的差别：官方件形态不同。

  法条维度（意大利）：官方件 = 条文 XML（AKN）⇒ 判「数值出自该条正文」
  **判例维度（意大利）**：官方件 = 宪法法院判决档案 XML 的判决切片
    （Corte costituzionale 开放数据 `dati.cortecostituzionale.it`）⇒
    既能判「数值出自该判决正文」，也能判「ECLI/裁判日对得上」。

本模块与法国闸（verify）、中国闸（verify-cn）、中国案例闸（verify-case）、
意大利法条闸（verify-it）、西班牙闸（verify-es）**互不越界**：
事实的 source 以 `.itcase.card.txt` 结尾的才归本闸，其余各闸的卡一律跳过。

三判（判据清单）
----------------
1. 官方件哈希判
     切片现算 sha256 ↔ index.slice_sha256 ↔ 卡 OFFICIAL_XML_SHA256（三方对账）
     确定性纯文本现算 sha256 ↔ index.text_sha256 ↔ 卡 TEXT_SHA256
     事实账钉的 source_sha256 ↔ 证据卡文件现算（卡自身被改）
     **哈希先行**：先对账，后推正文。官方件被改坏（哪怕改到 XML 不再合法）都只落成
     闭集内的红码 finding，不许异常穿透 CLI；正文推不出来时其余依赖正文的判全跳过。
2. 值出自官方正文判
     数值/金额（意式 `1.000,00` / `1.234.567` 归一后比对）
     日期（ISO / gg/mm/aaaa / 意语月名 `11 gennaio 1956` 归一后比对）
     其余字面（在归一化正文里找）
3. 案号/日期一致性判
     卡 ECLI 必须出现在归一化正文里
     卡 DATA_DECISIONE 原始形或 ISO 形必须能从正文找到
     卡内嵌 `--- OFFICIAL TEXT ---` 段必须与现推文本前 600 字一致

码表（闭集；`ITCASE_` 前缀，与既有 LEGAL_/CN_/CASE_/IT_/ES_ 各域一前缀的
分域注册制一致；红级，无黄级——判决是历史件，没有「版本时效」语义，
照 verify-case 无黄先例）
------------------------------------------------------------------------
  ITCASE_CARD_MISSING            事实指向的证据卡不存在
  ITCASE_PROV_UNKNOWN            卡 ECLI 不在 index.judgments 里
  ITCASE_CARD_NO_HASH            卡缺 OFFICIAL_XML_SHA256 / TEXT_SHA256 声明
  ITCASE_SLICE_HASH_MISMATCH     切片缺失／切片 sha 与索引或卡不符／text_sha256 与现推不符
                                 ／切片 XML 解析失败（哈希声明虽一致，正文推不出）
  ITCASE_CARD_SHA256_MISMATCH     卡自身被改（事实账钉的哈希与现算不符）
  ITCASE_CARD_FIELD_MISMATCH     卡 anno/numero/ecli 与索引不符
  ITCASE_CARD_TEXT_DIVERGED      卡内嵌正文与现推文本前 600 字不一致（或缺段）
  ITCASE_VALUE_NOT_IN_OFFICIAL   事实值在官方正文找不到（归一化后）
  ITCASE_NO_MISMATCH             卡 ECLI 在归一化正文里找不到
  ITCASE_DATE_MISMATCH           卡裁判日期原始形与 ISO 形都在正文找不到

退出码沿用上游：0 绿 / 1 红 / 2 配置错 / 3 黄
"""
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET

from .verify import Finding, load_facts

CARD_SUFFIX = ".itcase.card.txt"
TEXT_MARKER = "--- OFFICIAL TEXT ---"
CARD_TEXT_CHARS = 600

# ---- 卡字段声明（只认这些键；头部注释与内嵌正文段不参与解析）----
CARD_DECL_RE = re.compile(
    r"^(ECLI|ANNO_PRONUNCIA|NUMERO_PRONUNCIA|TIPOLOGIA|PRESIDENTE|RELATORE|"
    r"DATA_DECISIONE|DATA_DECISIONE_ISO|DATA_DEPOSITO|SOURCE_FILE|SOURCE_URL|"
    r"OFFICIAL_XML_SHA256|TEXT_SHA256|TEXT_CHARS):\s*(.*)$", re.M)

# ---- 意式数字 ----
# `1.000,00` / `1.234.567` → 去千分位点、逗号转点；`1000,00` → `1000.00`。
# 两侧（事实值与正文）用**同一套**规则改写后再比对。
IT_NUM_GROUPED_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")
IT_NUM_COMMA_RE = re.compile(r"\d+,\d+")
# 事实值「像不像一个数」（只有数字/点/逗号）
IT_NUM_VALUE_RE = re.compile(r"^\d+(?:[.,]\d+)*$")
# 事实值「像不像一个日期」
IT_DATE_VALUE_RE = re.compile(
    r"^(?:\d{4}[-./]\d{1,2}[-./]\d{1,2}"          # 2026-11-16
    r"|\d{1,2}[-./]\d{1,2}[-./]\d{4}"             # 16/11/2026（意式 gg/mm/aaaa）
    r"|\d{1,2}\s+[A-Za-zÀ-ÿ]{3,12}\.?,?\s+\d{4})$")   # 11 gennaio 1956

# 正文里的日期形态（分隔符两侧允许空白：判决正文里日期常被跨行断开）
IT_DDMMYYYY_RE = re.compile(r"\b(\d{1,2})\s*[/.]\s*(\d{1,2})\s*[/.]\s*(\d{4})\b")
IT_YYYYMMDD_RE = re.compile(r"\b(\d{4})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})\b")
IT_MONTHNAME_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-zÀ-ÿ]{3,12})\.?,?\s+(\d{4})\b")
IT_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
    "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
    "novembre": 11, "dicembre": 12,
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "lug": 7,
    "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
}


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _itcase_plain(data):
    """判决切片字节 → 确定性纯文本（抓取器内联同款算法；同输入同字节，sha256 可复现）。

    流程：解码 → 去 XML 声明（str 解析器不认声明里的 encoding）→ ElementTree 解析
    → `"".join(root.itertext())`（文档序；实体已被解析器解掉，`&#13;` 变 CR）
    → NBSP→空格 → 所有空白串（含 CR/LF/TAB）折叠成单空格 → strip。
    """
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", "replace")
    else:
        text = data
    stripped = re.sub(r"^﻿?\s*<\?xml[^>]*\?>", "", text, count=1)
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError:
        root = ET.fromstring(data)   # 兜底：按字节解析（ET 自认声明里的编码）
    s = "".join(root.itertext())
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _itcase_testata(data):
    """切片字节 → testata 字段字典（根可能是 pronuncia，也可能是 elenco_pronunce 包装）。"""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    node = root if root.tag == "pronuncia" else root.find("pronuncia")
    if node is None:
        node = root.find(".//pronuncia")
    if node is None:
        return None
    tt = node.find("pronuncia_testata")
    if tt is None:
        return None

    def g(tag):
        el = tt.find(tag)
        return (el.text or "").strip() if el is not None else ""

    return {
        "ecli": g("ecli"),
        "anno": g("anno_pronuncia"),
        "numero": g("numero_pronuncia"),
        "tipologia": g("tipologia_pronuncia"),
        "presidente": g("presidente"),
        "relatore": g("relatore_pronuncia"),
        "data_decisione": g("data_decisione"),
        "data_deposito": g("data_deposito"),
    }


def _itcase_norm_numbers(text):
    """意式数字改写（两侧同规则）。"""
    text = IT_NUM_GROUPED_RE.sub(
        lambda m: m.group(0).replace(".", "").replace(",", "."), text)
    text = IT_NUM_COMMA_RE.sub(lambda m: m.group(0).replace(",", "."), text)
    return text


def _itcase_iso(y, m, d):
    try:
        return "%04d-%02d-%02d" % (int(y), int(m), int(d))
    except (TypeError, ValueError):
        return ""


def _itcase_dates(text):
    """正文里的日期 → ISO 集合（意式 gg/mm/aaaa、ISO、意语月名都认）。"""
    out = set()
    for d, m, y in IT_DDMMYYYY_RE.findall(text):
        iso = _itcase_iso(y, m, d)      # 意式：日/月/年
        if iso:
            out.add(iso)
    for y, m, d in IT_YYYYMMDD_RE.findall(text):
        iso = _itcase_iso(y, m, d)
        if iso:
            out.add(iso)
    for d, name, y in IT_MONTHNAME_RE.findall(text):
        mo = IT_MONTHS.get(name.rstrip(".").lower())
        if mo:
            iso = _itcase_iso(y, mo, d)
            if iso:
                out.add(iso)
    return out


def _itcase_norm_date(value):
    """事实值/卡字段 → ISO（认 ISO、gg/mm/aaaa、意语月名）；认不出回空串。"""
    v = (value or "").strip()
    if not v:
        return ""
    m = IT_YYYYMMDD_RE.search(v)
    if m:
        return _itcase_iso(m.group(1), m.group(2), m.group(3))
    m = IT_DDMMYYYY_RE.search(v)
    if m:
        return _itcase_iso(m.group(3), m.group(2), m.group(1))   # 意式 gg/mm/aaaa
    m = IT_MONTHNAME_RE.search(v)
    if m:
        mo = IT_MONTHS.get(m.group(2).rstrip(".").lower())
        if mo:
            return _itcase_iso(m.group(3), mo, m.group(1))
    return ""


def _itcase_has_number(norm_text, norm_val):
    """数字/金额：归一化后逐位找（数字边界护栏：999 不许在 1999 里命中）。"""
    if not norm_val:
        return False
    return re.search(r"(?<!\d)" + re.escape(norm_val) + r"(?!\d)", norm_text) is not None


def _itcase_tight(text):
    """去空白的紧致形（判决正文里的 ECLI/案号常被 NBSP 或跨行拆开）。"""
    return re.sub(r"\s+", "", text)


def _itcase_has_literal(norm_text, value):
    """字面值是否在正文里：先原样找，再在「去空白」的紧致形里找。

    判决正文里 ECLI 常被 NBSP 与 `&#13;`＋换行拆开；归一化后中间会留一个空格，
    只按原样找就会把「官方件里明明有」判成「找不到」（假红）。
    紧致比较只对长度 ≥4 的字面量启用，避免短串在词边界上误命中。
    """
    if value in norm_text:
        return True
    tight_val = _itcase_tight(value)
    if len(tight_val) < 4:
        return False
    return tight_val in _itcase_tight(norm_text)


def _itcase_card_fields(card_text):
    """卡头字段（只解析 `--- OFFICIAL TEXT ---` 之前的部分）。"""
    head = card_text.split(TEXT_MARKER, 1)[0]
    return {k: v.strip() for k, v in CARD_DECL_RE.findall(head)}


def verify_it_case(project_dir, corpus_dir):
    """跑意大利宪法法院判例专项校验，返回 (findings, index)。"""
    findings = []
    idx_path = os.path.join(corpus_dir, "index.json")
    if not os.path.exists(idx_path):
        raise FileNotFoundError(f"找不到 {idx_path}")
    with open(idx_path, encoding="utf-8") as fh:
        index = json.load(fh)
    judgments = index.get("judgments") or {}
    # ECLI → slug（卡里的 ECLI 是判决的权威标识，索引按 slug 存）
    ecli_map = {}
    for slug, meta in judgments.items():
        ecli = (meta or {}).get("ecli") or ""
        if ecli:
            ecli_map[ecli] = slug

    checked_cards = set()      # 卡级检查每张卡只做一次（值检查仍逐 fact 走）
    hash_checked = set()       # 哈希先行门每张卡只做一次（先于正文推导）
    cache = {}                 # slug → 现算的切片/正文（每卡只现算一次）

    for fact in load_facts(project_dir):
        src = fact.get("source", "")
        if not src.endswith(CARD_SUFFIX):
            continue        # 法国/中国/中国案例/意大利法条/西班牙的卡，各归各闸
        loc = f"{fact['_file']}:{fact.get('id', '?')}"
        card_path = os.path.join(project_dir, src)
        if not os.path.exists(card_path):
            findings.append(Finding("ITCASE_CARD_MISSING", "red", loc,
                                    f"意大利宪法法院判例证据卡不存在：{src}"))
            continue
        with open(card_path, encoding="utf-8") as fh:
            card_text = fh.read()
        fields = _itcase_card_fields(card_text)
        ecli = fields.get("ECLI", "")
        if not ecli:
            findings.append(Finding("ITCASE_CARD_NO_HASH", "red", loc,
                                    f"证据卡 {src} 里没有 ECLI 声明"))
            continue
        slug = ecli_map.get(ecli)
        if slug is None:
            findings.append(Finding("ITCASE_PROV_UNKNOWN", "red", loc,
                                    f"判决 {ecli} 不在语料索引里（{corpus_dir}）"))
            continue
        meta = judgments.get(slug) or {}

        # ---- 哈希声明齐全否 ----
        decl_slice = fields.get("OFFICIAL_XML_SHA256", "")
        decl_text = fields.get("TEXT_SHA256", "")
        if not decl_slice or not decl_text:
            findings.append(Finding("ITCASE_CARD_NO_HASH", "red", loc,
                                    f"证据卡 {src} 里缺 OFFICIAL_XML_SHA256 / "
                                    "TEXT_SHA256 声明"))
            continue

        # ---- 官方切片：现算字节与哈希（每卡只现算一次；**先不碰 XML**）----
        if slug not in cache:
            slice_rel = meta.get("slice_file") or f"official/{slug}.xml"
            slice_path = os.path.join(corpus_dir, slice_rel)
            if not os.path.exists(slice_path):
                cache[slug] = {"missing": slice_rel}
            else:
                with open(slice_path, "rb") as fh:
                    slice_raw = fh.read()
                cache[slug] = {
                    "missing": "",
                    "raw": slice_raw,
                    "slice_sha": _sha256_bytes(slice_raw),
                    # broken：官方件已判红 ⇒ 正文推不出来，其余依赖正文的判全跳过
                    "broken": False,
                    "text": "",
                    "text_sha": "",
                    "norm_text": "",
                    "dates": set(),
                }
        item = cache[slug]
        if item.get("missing"):
            findings.append(Finding("ITCASE_SLICE_HASH_MISMATCH", "red", loc,
                                    f"判决切片 {item['missing']} 不在语料目录里"))
            continue
        slice_sha = item["slice_sha"]

        # ---- 哈希先行：现算 sha256 ↔ 索引 ↔ 卡（**不解析 XML**）----
        #   官方件被改坏（哪怕改到 XML 不再合法）先在哈希层落成闭集内的红码，
        #   不许异常穿透 CLI；正文只在哈希三方对齐之后才推。
        if slug not in hash_checked:
            hash_checked.add(slug)
            if slice_sha != meta.get("slice_sha256"):
                item["broken"] = True
                findings.append(Finding(
                    "ITCASE_SLICE_HASH_MISMATCH", "red", loc,
                    f"判决 {ecli} 的切片哈希与索引不符"
                    f"（索引 {str(meta.get('slice_sha256'))[:12]}… / 现算 {slice_sha[:12]}…）"))
            if decl_slice != slice_sha:
                item["broken"] = True
                findings.append(Finding(
                    "ITCASE_SLICE_HASH_MISMATCH", "red", loc,
                    f"证据卡声明的官方件哈希与现算不符"
                    f"（卡 {decl_slice[:12]}… / 现算 {slice_sha[:12]}…）"))
            if not item["broken"]:
                # 哈希三方对齐 ⇒ 才推正文（解析失败同样是红码，不许异常外泄）
                try:
                    text = _itcase_plain(item["raw"])
                except (ET.ParseError, ValueError):
                    item["broken"] = True
                    findings.append(Finding(
                        "ITCASE_SLICE_HASH_MISMATCH", "red", loc,
                        "切片 XML 解析失败（哈希声明虽一致，正文推不出）"
                        "——材料异常，须人工看"))
                else:
                    item["text"] = text
                    item["text_sha"] = _sha256_bytes(text.encode("utf-8"))
                    item["norm_text"] = _itcase_norm_numbers(text)
                    item["dates"] = _itcase_dates(text)
                    if item["text_sha"] != meta.get("text_sha256"):
                        findings.append(Finding(
                            "ITCASE_SLICE_HASH_MISMATCH", "red", loc,
                            f"判决 {ecli} 的正文哈希与索引不符"
                            f"（索引 {str(meta.get('text_sha256'))[:12]}… / 现算 {item['text_sha'][:12]}…）"))
                    if decl_text != item["text_sha"]:
                        findings.append(Finding(
                            "ITCASE_SLICE_HASH_MISMATCH", "red", loc,
                            f"证据卡声明的正文哈希与现算不符"
                            f"（卡 {decl_text[:12]}… / 现算 {item['text_sha'][:12]}…）"))
        norm_text = item["norm_text"]
        dates = item["dates"]

        # ---- 事实的值必须真的在官方正文里（正文推不出来就不判）----
        if not item["broken"]:
            val = fact.get("value")
            if val is not None:
                raw_val = str(val).strip()
                if raw_val:
                    if IT_NUM_VALUE_RE.match(raw_val):
                        if not _itcase_has_number(norm_text,
                                                   _itcase_norm_numbers(raw_val)):
                            findings.append(Finding(
                                "ITCASE_VALUE_NOT_IN_OFFICIAL", "red", loc,
                                f"金额 {raw_val} 在判决 {ecli} 的官方正文里找不到"))
                    elif IT_DATE_VALUE_RE.match(raw_val):
                        iso = _itcase_norm_date(raw_val)
                        if not (iso and iso in dates) and raw_val not in norm_text:
                            findings.append(Finding(
                                "ITCASE_VALUE_NOT_IN_OFFICIAL", "red", loc,
                                f"日期 {raw_val} 在判决 {ecli} 的官方正文里找不到"))
                    else:
                        if not _itcase_has_literal(norm_text,
                                                   _itcase_norm_numbers(raw_val)):
                            findings.append(Finding(
                                "ITCASE_VALUE_NOT_IN_OFFICIAL", "red", loc,
                                f"值 {raw_val[:40]} 在判决 {ecli} 的官方正文里找不到"))

        # ---- 卡级检查：每张卡只做一次 ----
        if slug in checked_cards:
            continue
        checked_cards.add(slug)

        # B. 事实账钉的卡哈希 vs 卡文件现算（卡自身被改）
        pinned = (fact.get("source_sha256") or "").removeprefix("sha256:").lower()
        if pinned and pinned != _sha256_file(card_path):
            findings.append(Finding(
                "ITCASE_CARD_SHA256_MISMATCH", "red", loc,
                f"证据卡 {src} 自身被改过（事实账钉的哈希与现算不符）"))

        # C. 卡字段 vs 索引
        for key, ikey in (("ECLI", "ecli"), ("ANNO_PRONUNCIA", "anno"),
                          ("NUMERO_PRONUNCIA", "numero")):
            cv = fields.get(key, "")
            iv = str(meta.get(ikey) or "")
            if cv and iv and cv != iv:
                findings.append(Finding(
                    "ITCASE_CARD_FIELD_MISMATCH", "red", loc,
                    f"证据卡声明的 {key} {cv} 与索引 {iv} 不一致"))

        # D/E/F 依赖正文：官方件已判红（哈希对不上或推不出正文）⇒ 一并跳过，
        # 材料已经判红，不重复刷屏。
        if item["broken"]:
            continue

        # D. 卡内嵌正文 vs 现推文本前 600 字
        if TEXT_MARKER in card_text:
            embedded = card_text.split(TEXT_MARKER, 1)[1].strip()
            text = item["text"]
            expected = text[:CARD_TEXT_CHARS] + \
                ("…" if len(text) > CARD_TEXT_CHARS else "")
            if embedded != expected:
                findings.append(Finding(
                    "ITCASE_CARD_TEXT_DIVERGED", "red", loc,
                    "卡片内嵌的正文与官方切片现推文本前 %d 字不一致"
                    "（卡片的正文副本被改过）" % CARD_TEXT_CHARS))
        else:
            findings.append(Finding(
                "ITCASE_CARD_TEXT_DIVERGED", "red", loc,
                f"卡片里找不到 {TEXT_MARKER} 段"))

        # E. ECLI 一致性：卡 ECLI 必须出现在归一化正文里（NBSP／跨行拆开也算）
        if ecli and not _itcase_has_literal(norm_text, ecli):
            findings.append(Finding(
                "ITCASE_NO_MISMATCH", "red", loc,
                f"卡片判决号 {ecli} 在官方正文里不存在"))

        # F. 裁判日期一致性：原始形或 ISO 形必须能从正文找到
        dd = fields.get("DATA_DECISIONE", "")
        dd_iso = fields.get("DATA_DECISIONE_ISO", "") or _itcase_norm_date(dd)
        if dd and not (dd in norm_text or (dd_iso and dd_iso in dates)):
            findings.append(Finding(
                "ITCASE_DATE_MISMATCH", "red", loc,
                f"卡片裁判日期 {dd} 在官方正文里不存在"))

    return findings, index


def render_it_case(findings, index=None):
    reds = [f for f in findings if f.severity == "red"]
    yellows = [f for f in findings if f.severity == "yellow"]
    lines = ["== factscribe-legal verify-it-case（意大利宪法法院判例）=="]
    if index:
        lines.append("档位   : %s" % index.get("tier"))
        lines.append("来源   : %s" % index.get("source_url"))
        lines.append("判决数 : %d" % len(index.get("judgments") or {}))
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
    if reds:
        lines.append(f"结论：{len(reds)} 红 / {len(yellows)} 黄 → 红（退出码 1）")
    elif yellows:
        lines.append(f"结论：0 红 / {len(yellows)} 黄 → 黄（退出码 3）")
    else:
        lines.append("结论：0 红 / 0 黄 → 绿（退出码 0）")
    lines.append("注意：绿只代表「引用的判决真实存在、哈希未变、且数值真出自官方正文」，"
                 "不代表判决写得对。")
    return "\n".join(lines), (1 if reds else (3 if yellows else 0))
