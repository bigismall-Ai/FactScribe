"""西班牙法条专项校验：把「事实的来源是西班牙官方法条」变成机械判定。

上游 FactScribe 判的是：正文数字 → 事实账 → 材料哈希。
本模块判的是**西班牙法条这一层**（与法国闸、中国闸、意大利闸互不越界）：

  红
    ES_PROV_UNKNOWN            引用/来源的条文不在语料索引里
    ES_ARTICLE_NOT_IN_SOURCE   官方整件里已经找不到这个条文（切片与官方件脱钩）
    ES_ARTICLE_HASH_MISMATCH   条文切片的哈希与索引/证据卡声明不符（条文被人动过）
    ES_SOURCE_HASH_MISMATCH    官方整件的哈希与索引/证据卡声明不符（整件被人动过）
    ES_CARD_NO_HASH            证据卡里缺必要的哈希声明
    ES_CARD_SHA256_MISMATCH    证据卡自身被改过（事实账钉的哈希与现算不符）
    ES_CARD_FIELD_MISMATCH     证据卡声明的法件/条文/版本与索引对不上
    ES_CARD_MISSING            事实指向的证据卡不存在
    ES_QUOTE_MISMATCH          事实里的数值不真的出现在该条官方正文里
  黄
    ES_VERSION_GAP             钉住的是另一个日期的时点版本，与本次参考日不一致

码一律 `ES_` 前缀（照既有码表的分域注册制：LEGAL_/CN_/CASE_/IT_ 各域一前缀）。

官方件＝西班牙官方公报 BOE（Agencia Estatal Boletín Oficial del Estado）的
**合并文本 XML**（开放数据 API `legislacion-consolidada` by-id）。整件里每个
`<bloque id="a7" tipo="precepto">` 是一个条文块；切片是整件字节的原样子串。

退出码沿用上游：0 绿 / 1 红 / 2 配置错 / 3 黄
"""
import hashlib
import json
import os
import re

from .verify import Finding, load_citations, load_facts

CARD_MARK = re.compile(r"^BLOCK_ID:\s*(.+)$", re.M)
CITE_RE = re.compile(r"^art-es-([A-Za-z0-9_.-]+)$")
BLOQUE_RE = re.compile(rb'<bloque id="([^"]+)"')
CARD_DECL_RE = re.compile(
    r"^(ARTICLE_SHA256|OFFICIAL_XML_SHA256|SOURCE_FILE|ACT_ID|VERSION_DATE):\s*(.*)$",
    re.M)


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _plain_text(xml_text):
    s = re.sub(r"<[^>]+>", " ", xml_text)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&#13;", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def verify_es(project_dir, corpus_dir, reference_date):
    findings = []
    idx_path = os.path.join(corpus_dir, "index.json")
    if not os.path.exists(idx_path):
        raise FileNotFoundError(f"找不到 {idx_path}")
    with open(idx_path, encoding="utf-8") as fh:
        index = json.load(fh)
    articles = index.get("articles") or {}
    official_rel = index.get("source_file") or "official/act.xml"
    official_path = os.path.join(corpus_dir, official_rel)
    official_sha = ""
    official_raw = b""
    if os.path.exists(official_path):
        with open(official_path, "rb") as fh:
            official_raw = fh.read()
        official_sha = _sha256_bytes(official_raw)
        if official_sha != index.get("source_sha256"):
            findings.append(Finding(
                "ES_SOURCE_HASH_MISMATCH", "red", "corpus",
                f"官方整件 {official_rel} 的哈希与索引不符"
                f"（索引 {str(index.get('source_sha256'))[:12]}… / 现算 {official_sha[:12]}…）"
                "——官方件被人动过"))
    else:
        findings.append(Finding("ES_SOURCE_HASH_MISMATCH", "red", "corpus",
                                f"官方整件 {official_rel} 不在语料目录里"))
    # 官方整件里现存的条文块（用于回查切片是否还属于官方件）
    live_ids = {m.group(1).decode("utf-8", "replace")
                for m in BLOQUE_RE.finditer(official_raw)}

    # ---- 1. 事实账里指向西班牙证据卡的 fact ----
    for fact in load_facts(project_dir):
        src = fact.get("source", "")
        if not src.endswith(".es.card.txt"):
            continue  # 法国/中国/案例/意大利的卡，各归各闸
        card_path = os.path.join(project_dir, src)
        loc = f"{fact['_file']}:{fact.get('id', '?')}"
        if not os.path.exists(card_path):
            findings.append(Finding("ES_CARD_MISSING", "red", loc,
                                    f"西班牙证据卡不存在：{src}"))
            continue
        with open(card_path, encoding="utf-8") as fh:
            card = fh.read()
        m_bid = CARD_MARK.search(card)
        if not m_bid:
            findings.append(Finding("ES_CARD_NO_HASH", "red", loc,
                                    f"证据卡 {src} 里没有 BLOCK_ID 声明"))
            continue
        bid = m_bid.group(1).strip()
        meta = articles.get(bid)
        if meta is None:
            findings.append(Finding("ES_PROV_UNKNOWN", "red", loc,
                                    f"条文 {bid} 不在语料索引里（{corpus_dir}）"))
            continue
        # 哈希声明
        decl = dict(CARD_DECL_RE.findall(card))
        if not decl.get("ARTICLE_SHA256") or not decl.get("OFFICIAL_XML_SHA256"):
            findings.append(Finding("ES_CARD_NO_HASH", "red", loc,
                                    f"证据卡 {src} 里缺 ARTICLE_SHA256 / "
                                    "OFFICIAL_XML_SHA256 声明"))
            continue
        if decl["OFFICIAL_XML_SHA256"].strip() != official_sha:
            findings.append(Finding(
                "ES_SOURCE_HASH_MISMATCH", "red", loc,
                f"证据卡声明的官方整件哈希与现算不符"
                f"（卡 {decl['OFFICIAL_XML_SHA256'].strip()[:12]}… / 现算 {official_sha[:12]}…）"))
        # 条文切片：文件现算 + 是否仍属于官方整件
        art_rel = meta.get("article_file") or f"official/{bid}.xml"
        art_path = os.path.join(corpus_dir, art_rel)
        if not os.path.exists(art_path):
            findings.append(Finding("ES_ARTICLE_HASH_MISMATCH", "red", loc,
                                    f"条文切片 {art_rel} 不在语料目录里"))
            continue
        with open(art_path, "rb") as fh:
            art_raw = fh.read()
        art_sha = _sha256_bytes(art_raw)
        if art_sha != meta.get("article_sha256"):
            findings.append(Finding(
                "ES_ARTICLE_HASH_MISMATCH", "red", loc,
                f"条文 {bid} 的切片哈希与索引不符"
                f"（索引 {str(meta.get('article_sha256'))[:12]}… / 现算 {art_sha[:12]}…）"))
        if decl["ARTICLE_SHA256"].strip() != art_sha:
            findings.append(Finding(
                "ES_ARTICLE_HASH_MISMATCH", "red", loc,
                f"证据卡声明的条文哈希与现算不符"
                f"（卡 {decl['ARTICLE_SHA256'].strip()[:12]}… / 现算 {art_sha[:12]}…）"))
        if bid not in live_ids:
            findings.append(Finding(
                "ES_ARTICLE_NOT_IN_SOURCE", "red", loc,
                f"官方整件里已经找不到 {bid}——切片与官方件脱钩（可能整件被换过）"))
        else:
            # 官方整件里同名条文的字节应当与切片一致
            m2 = re.search(rb'<bloque id="' + bid.encode("utf-8") +
                           rb'"[^>]*>.*?</bloque>', official_raw, re.S)
            if m2 and _sha256_bytes(m2.group(0)) != art_sha:
                findings.append(Finding(
                    "ES_ARTICLE_HASH_MISMATCH", "red", loc,
                    f"切片与官方整件里的 {bid} 字节不一致"))
        # 证据卡自身是否被改
        pinned = (fact.get("source_sha256") or "").removeprefix("sha256:").lower()
        if pinned and pinned != _sha256_file(card_path):
            findings.append(Finding(
                "ES_CARD_SHA256_MISMATCH", "red", loc,
                f"证据卡 {src} 自身被改过（事实账钉的哈希与现算不符）"))
        # 卡里的字段与索引是否对得上
        if decl.get("ACT_ID", "").strip() and index.get("act_id") and \
                decl["ACT_ID"].strip() != index["act_id"]:
            findings.append(Finding("ES_CARD_FIELD_MISMATCH", "red", loc,
                                    f"证据卡声明的法件 {decl['ACT_ID'].strip()} 与索引 "
                                    f"{index['act_id']} 不一致"))
        if decl.get("VERSION_DATE", "").strip() and index.get("version_date") and \
                decl["VERSION_DATE"].strip() != index["version_date"]:
            findings.append(Finding("ES_CARD_FIELD_MISMATCH", "red", loc,
                                    f"证据卡声明的版本 {decl['VERSION_DATE'].strip()} 与索引 "
                                    f"{index['version_date']} 不一致"))
        # 事实的数值是否真的出自该条正文
        val = fact.get("value")
        if val is not None:
            text = _plain_text(art_raw.decode("utf-8", "replace"))
            if not re.search(r"(?<!\d)" + re.escape(str(val).strip()) + r"(?!\d)", text):
                findings.append(Finding(
                    "ES_QUOTE_MISMATCH", "red", loc,
                    f"事实 {fact.get('id')} 的值 {val} 不出现在条文 {bid} 的官方正文里"))

    # ---- 2. 版本基准日与参考日是否一致 ----
    # ⚠️ version_date 是合并文本自身的最后更新日（fecha_actualizacion），
    #    不是「这一版在什么时候生效」；真正可比的是取件时用的参考日
    #    （fetch_reference_date）——它对应「取件那天的官方现行合并文本」。
    fetch_ref = index.get("fetch_reference_date") or ""
    ver = index.get("version_date") or ""
    if fetch_ref and reference_date and reference_date != fetch_ref:
        findings.append(Finding(
            "ES_VERSION_GAP", "yellow", "corpus",
            f"钉住的是「{fetch_ref} 取件时」的合并文本（最后更新 {ver}），"
            f"而本次参考日是 {reference_date}——两日之间的法律变化不在钉住的版本里"
            "（要当日最新请按新参考日重新取件）"))

    # ---- 3. 正文里的西班牙法条引用 ----
    for key, rel, line in load_citations(project_dir):
        m = CITE_RE.match(key)
        if not m:
            continue
        bid = m.group(1)
        loc = f"{rel}:{line}"
        if bid not in articles:
            findings.append(Finding("ES_PROV_UNKNOWN", "red", loc,
                                    f"引用了语料里没有的西班牙条文 {bid}"))
    return findings, index


def render_es(findings, index=None):
    reds = [f for f in findings if f.severity == "red"]
    yellows = [f for f in findings if f.severity == "yellow"]
    lines = ["== factscribe-legal verify-es（西班牙法条）=="]
    if index:
        lines.append(f"act    : {index.get('act_id')}  {index.get('act_title', '')}")
        lines.append(f"版本日 : {index.get('version_date')}   参考日 : "
                     f"{index.get('reference_date')}")
        lines.append(f"条文数 : {len(index.get('articles') or {})}")
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
    lines.append("注意：绿只代表「引用的西班牙条文真实存在、哈希未变、且数值真出自官方正文」，"
                 "不代表法条写得对。")
    return "\n".join(lines), (1 if reds else (3 if yellows else 0))
