"""意大利法条专项校验：把「事实的来源是意大利官方法条」变成机械判定。

上游 FactScribe 判的是：正文数字 → 事实账 → 材料哈希。
本模块判的是**意大利法条这一层**（与法国闸、中国闸互不越界）：

  红
    IT_PROV_UNKNOWN            引用/来源的条文不在语料索引里
    IT_ARTICLE_NOT_IN_SOURCE   官方整件里已经找不到这个条文（切片与官方件脱钩）
    IT_ARTICLE_HASH_MISMATCH   条文切片的哈希与索引/证据卡声明不符（条文被人动过）
    IT_SOURCE_HASH_MISMATCH    官方整件的哈希与索引/证据卡声明不符（整件被人动过）
    IT_CARD_NO_HASH            证据卡里缺必要的哈希声明
    IT_CARD_SHA256_MISMATCH    证据卡自身被改过（事实账钉的哈希与现算不符）
    IT_CARD_FIELD_MISMATCH     证据卡声明的法件/条文/版本与索引对不上
    IT_QUOTE_MISMATCH          事实里的数值不真的出现在该条官方正文里
  黄
    IT_VERSION_GAP             钉住的是另一个日期的时点版本，与本次参考日不一致

退出码沿用上游：0 绿 / 1 红 / 2 配置错 / 3 黄
"""
import hashlib
import json
import os
import re

from .verify import Finding, load_citations, load_facts

CARD_MARK = re.compile(r"^ARTICLE_EID:\s*(.+)$", re.M)
CITE_RE = re.compile(r"^art-it-(art_\d+)$")
ART_RE = re.compile(rb'<article eId="(art_[0-9]+)">')


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
    s = s.replace("&amp;", "&").replace("&#13;", " ")
    return re.sub(r"\s+", " ", s).strip()


def _is_it_card(path):
    """意大利证据卡的后缀是 .it.card.txt（与 .cn.card.txt / .case.card.txt 同级区分）。"""
    return path.endswith(".it.card.txt")


def verify_it(project_dir, corpus_dir, reference_date):
    findings = []
    idx_path = os.path.join(corpus_dir, "index.json")
    if not os.path.exists(idx_path):
        raise FileNotFoundError(f"找不到 {idx_path}")
    with open(idx_path, encoding="utf-8") as fh:
        index = json.load(fh)
    articles = index.get("articles") or {}
    official_rel = index.get("source_file") or ""
    official_path = os.path.join(corpus_dir, official_rel)
    official_sha = ""
    official_raw = b""
    if os.path.exists(official_path):
        with open(official_path, "rb") as fh:
            official_raw = fh.read()
        official_sha = _sha256_bytes(official_raw)
        if official_sha != index.get("source_sha256"):
            findings.append(Finding(
                "IT_SOURCE_HASH_MISMATCH", "red", "corpus",
                f"官方整件 {official_rel} 的哈希与索引不符"
                f"（索引 {str(index.get('source_sha256'))[:12]}… / 现算 {official_sha[:12]}…）"
                "——官方件被人动过"))
    else:
        findings.append(Finding("IT_SOURCE_HASH_MISMATCH", "red", "corpus",
                                f"官方整件 {official_rel} 不在语料目录里"))
    # 官方整件里现存的条文（用于回查切片是否还属于官方件）
    live_eids = {m.group(1).decode() for m in ART_RE.finditer(official_raw)}

    # ---- 1. 事实账里指向意大利证据卡的 fact ----
    for fact in load_facts(project_dir):
        src = fact.get("source", "")
        if not src.endswith(".it.card.txt"):
            continue  # 法国/中国/案例的卡，各归各闸
        card_path = os.path.join(project_dir, src)
        loc = f"{fact['_file']}:{fact.get('id', '?')}"
        if not os.path.exists(card_path):
            findings.append(Finding("IT_CARD_MISSING", "red", loc,
                                    f"意大利证据卡不存在：{src}"))
            continue
        with open(card_path, encoding="utf-8") as fh:
            card = fh.read()
        m_eid = CARD_MARK.search(card)
        if not m_eid:
            findings.append(Finding("IT_CARD_NO_HASH", "red", loc,
                                    f"证据卡 {src} 里没有 ARTICLE_EID 声明"))
            continue
        eid = m_eid.group(1).strip()
        meta = articles.get(eid)
        if meta is None:
            findings.append(Finding("IT_PROV_UNKNOWN", "red", loc,
                                    f"条文 {eid} 不在语料索引里（{corpus_dir}）"))
            continue
        # 哈希声明
        decl = dict(re.findall(r"^(ARTICLE_SHA256|OFFICIAL_XML_SHA256|SOURCE_FILE|ACT_URN|VERSION_DATE):\s*(.*)$",
                               card, re.M))
        if not decl.get("ARTICLE_SHA256") or not decl.get("OFFICIAL_XML_SHA256"):
            findings.append(Finding("IT_CARD_NO_HASH", "red", loc,
                                    f"证据卡 {src} 里缺 ARTICLE_SHA256 / OFFICIAL_XML_SHA256 声明"))
            continue
        if decl["OFFICIAL_XML_SHA256"].strip() != official_sha:
            findings.append(Finding(
                "IT_SOURCE_HASH_MISMATCH", "red", loc,
                f"证据卡声明的官方整件哈希与现算不符"
                f"（卡 {decl['OFFICIAL_XML_SHA256'].strip()[:12]}… / 现算 {official_sha[:12]}…）"))
        # 条文切片：文件现算 + 是否仍属于官方整件
        art_rel = meta.get("article_file") or f"official/{eid}.xml"
        art_path = os.path.join(corpus_dir, art_rel)
        if not os.path.exists(art_path):
            findings.append(Finding("IT_ARTICLE_HASH_MISMATCH", "red", loc,
                                    f"条文切片 {art_rel} 不在语料目录里"))
            continue
        with open(art_path, "rb") as fh:
            art_raw = fh.read()
        art_sha = _sha256_bytes(art_raw)
        if art_sha != meta.get("article_sha256"):
            findings.append(Finding(
                "IT_ARTICLE_HASH_MISMATCH", "red", loc,
                f"条文 {eid} 的切片哈希与索引不符"
                f"（索引 {str(meta.get('article_sha256'))[:12]}… / 现算 {art_sha[:12]}…）"))
        if decl["ARTICLE_SHA256"].strip() != art_sha:
            findings.append(Finding(
                "IT_ARTICLE_HASH_MISMATCH", "red", loc,
                f"证据卡声明的条文哈希与现算不符"
                f"（卡 {decl['ARTICLE_SHA256'].strip()[:12]}… / 现算 {art_sha[:12]}…）"))
        if eid not in live_eids:
            findings.append(Finding(
                "IT_ARTICLE_NOT_IN_SOURCE", "red", loc,
                f"官方整件里已经找不到 {eid}——切片与官方件脱钩（可能整件被换过）"))
        else:
            # 官方整件里同名条文的字节应当与切片一致
            m2 = re.search(rb'<article eId="' + eid.encode() + rb'">(.*?)</article>',
                           official_raw, re.S)
            if m2 and _sha256_bytes(m2.group(0)) != art_sha:
                findings.append(Finding(
                    "IT_ARTICLE_HASH_MISMATCH", "red", loc,
                    f"切片与官方整件里的 {eid} 字节不一致"))
        # 证据卡自身是否被改
        pinned = (fact.get("source_sha256") or "").removeprefix("sha256:").lower()
        if pinned and pinned != _sha256_file(card_path):
            findings.append(Finding(
                "IT_CARD_SHA256_MISMATCH", "red", loc,
                f"证据卡 {src} 自身被改过（事实账钉的哈希与现算不符）"))
        # 卡里的字段与索引是否对得上
        if decl.get("ACT_URN", "").strip() and index.get("act_urn") and \
                decl["ACT_URN"].strip() != index["act_urn"]:
            findings.append(Finding("IT_CARD_FIELD_MISMATCH", "red", loc,
                                    f"证据卡声明的法件 {decl['ACT_URN'].strip()} 与索引 "
                                    f"{index['act_urn']} 不一致"))
        if decl.get("VERSION_DATE", "").strip() and index.get("version_date") and \
                decl["VERSION_DATE"].strip() != index["version_date"]:
            findings.append(Finding("IT_CARD_FIELD_MISMATCH", "red", loc,
                                    f"证据卡声明的版本 {decl['VERSION_DATE'].strip()} 与索引 "
                                    f"{index['version_date']} 不一致"))
        # 事实的数值是否真的出自该条正文
        val = fact.get("value")
        if val is not None:
            text = _plain_text(art_raw.decode("utf-8", "replace"))
            if not re.search(r"(?<!\d)" + re.escape(str(val).strip()) + r"(?!\d)", text):
                findings.append(Finding(
                    "IT_QUOTE_MISMATCH", "red", loc,
                    f"事实 {fact.get('id')} 的值 {val} 不出现在条文 {eid} 的官方正文里"))

    # ---- 2. 版本基准日与参考日是否一致 ----
    # ⚠️ version_date 只是合并文本自身的日期戳（最后一次修法日），不是「这一版在什么时候生效」。
    #    真正可比的是取件时用的 dataVigenza（fetch_reference_date）——它是「参考日当天生效的版本」。
    fetch_ref = index.get("fetch_reference_date") or ""
    ver = index.get("version_date") or ""
    if fetch_ref and reference_date and reference_date != fetch_ref:
        findings.append(Finding(
            "IT_VERSION_GAP", "yellow", "corpus",
            f"钉住的是「{fetch_ref} 当天生效」的时点版本（文本日期戳 {ver}），"
            f"而本次参考日是 {reference_date}——两日之间的法律变化不在钉住的版本里"
            "（要当日最新请按新参考日重新取件）"))

    # ---- 3. 正文里的意大利法条引用 ----
    for key, rel, line in load_citations(project_dir):
        m = CITE_RE.match(key)
        if not m:
            continue
        eid = m.group(1)
        loc = f"{rel}:{line}"
        if eid not in articles:
            findings.append(Finding("IT_PROV_UNKNOWN", "red", loc,
                                    f"引用了语料里没有的意大利条文 {eid}"))
    return findings, index


def render_it(findings, index=None):
    reds = [f for f in findings if f.severity == "red"]
    yellows = [f for f in findings if f.severity == "yellow"]
    lines = ["== factscribe-legal verify-it（意大利法条）=="]
    if index:
        lines.append(f"act    : {index.get('act_urn')}  {index.get('act_title', '')}")
        lines.append(f"版本日 : {index.get('version_date')}   参考日 : {index.get('reference_date')}")
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
    lines.append("注意：绿只代表「引用的意大利条文真实存在、哈希未变、且数值真出自官方正文」，"
                 "不代表法条写得对。")
    return "\n".join(lines), (1 if reds else (3 if yellows else 0))
