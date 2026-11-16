"""中国侧法律专项校验：把「引用的是哪部法规、哪一条、它现在有效吗、官方件有没有被动过」变成机械判定。

与法国侧的判据差异（因为官方材料形态不同）：
  法国官方件 = 条文 XML（含正文 + 生效区间） ⇒ 可判「数字出自正文」「参考日唯一生效版本」
  中国官方件 = 详情 JSON（目录树 + 元数据，**无正文**）⇒ 可判：
      · 法规在参考日是否现行有效（sxx）
      · 引用的「第X条」是否真的在该法规目录树里
      · 官方详情字节的哈希是否未变
      · 事实里的数字（条数/日期）是否与官方详情一致

退出码沿用上游：0 绿 / 1 红 / 2 配置错 / 3 黄
"""
import hashlib
import os
import re

from .cn_corpus import article_key, find_article, index_records, load_catalog
from .verify import Finding, load_citations, load_facts

CARD_RE = re.compile(r"^(?P<dir>.+)/(?P<slug>[^/]+)\.cn\.card\.txt$")
ART_IN_TEXT = re.compile(r"第[一二三四五六七八九十百千零〇两]+条")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _card_fields(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if ":" in line and not line.startswith("#") and not line.startswith("ARTICLE"):
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip()
    return out


def verify_cn(project_dir, catalog_path, reference_date):
    findings = []
    catalog = load_catalog(catalog_path)
    by_title = index_records(catalog)
    cards = {}   # slug → (path, fields, record)

    # ---- 事实账里指向中文证据卡的 fact ----
    for fact in load_facts(project_dir):
        src = fact.get("source", "")
        m = CARD_RE.match(src)
        if not m:
            continue
        loc = f"{fact['_file']}:{fact.get('id', '?')}"
        path = os.path.join(project_dir, src)
        if not os.path.exists(path):
            findings.append(Finding("CN_CARD_MISSING", "red", loc, f"证据卡不存在：{src}"))
            continue
        f = _card_fields(path)
        if "BBBS" not in f or "OFFICIAL_DETAIL_SHA256" not in f:
            # 不是中国证据卡（法国侧卡片同名不同后缀，这里双保险）
            continue
        title = f.get("TITLE", "")
        rec = by_title.get(title)
        if rec is None:
            findings.append(Finding("CN_PROV_UNKNOWN", "red", loc,
                                     f"全库里找不到《{title}》"))
            continue
        cards[m.group("slug")] = (path, f, rec)

        # ① 官方详情哈希：卡内声明 vs 全库现算
        declared = (f.get("OFFICIAL_DETAIL_SHA256") or "").lower()
        actual = (rec.get("detail_sha256") or "").lower()
        if not declared:
            findings.append(Finding("CN_CARD_NO_HASH", "red", loc,
                                     "证据卡里没有 OFFICIAL_DETAIL_SHA256 声明"))
        elif declared != actual:
            findings.append(Finding("CN_OFFICIAL_HASH_MISMATCH", "red", loc,
                                     f"《{title}》官方详情哈希与证据卡声明不符"
                                     f"（卡 {declared[:12]}… / 全库现算 {actual[:12]}…）——官方件被改过"))

        # ② 证据卡自身未被改（事实钉的哈希 vs 现算）
        pinned = (fact.get("source_sha256") or "").removeprefix("sha256:").lower()
        if pinned and pinned != _sha256_file(path):
            findings.append(Finding("CN_CARD_SHA256_MISMATCH", "red", loc,
                                     f"证据卡 {src} 自身被改过（事实钉的哈希与现算不符）"))

        # ③ 时效性：参考日当天是否现行有效
        sxx = rec.get("sxx")
        if sxx != 3:
            findings.append(Finding("CN_PROV_NOT_IN_FORCE", "red", loc,
                                     f"《{title}》在参考日不是现行有效（sxx={sxx}；"
                                     f"1废止/2修改/3有效/4未生效）"))

        # ④ 事实的值必须与官方详情一致
        val = str(fact.get("value", "")).strip()
        fid = str(fact.get("id", ""))
        if fid.endswith("-N"):
            if val != str(rec.get("n_articles")):
                findings.append(Finding("CN_VALUE_MISMATCH", "red", loc,
                                         f"条文条数与官方详情不符（账 {val} / 官方 {rec.get('n_articles')}）"))
        elif fid.endswith("-GBRQ"):
            if val != (rec.get("gbrq") or ""):
                findings.append(Finding("CN_VALUE_MISMATCH", "red", loc,
                                         f"公布日期与官方详情不符（账 {val} / 官方 {rec.get('gbrq')}）"))
        elif fid.endswith("-SXRQ"):
            if val != (rec.get("sxrq") or ""):
                findings.append(Finding("CN_VALUE_MISMATCH", "red", loc,
                                         f"施行日期与官方详情不符（账 {val} / 官方 {rec.get('sxrq')}）"))

    # ---- 正文里的中文法规引用 ----
    for key, rel, line in load_citations(project_dir):
        if not key.startswith("art-") or not re.search(r"[一-鿿]", key):
            continue
        title = key[4:]
        rec = by_title.get(title)
        loc = f"{rel}:{line}"
        if rec is None:
            findings.append(Finding("CN_PROV_UNKNOWN", "red", loc,
                                     f"引用了全库里没有的法规《{title}》"))
            continue
        if rec.get("sxx") != 3:
            findings.append(Finding("CN_PROV_NOT_IN_FORCE", "red", loc,
                                     f"引用的《{title}》不是现行有效（sxx={rec.get('sxx')}）"))
        # 同一句里出现的「第X条」必须在该法规目录树里
        for art in set(ART_IN_TEXT.findall(_line_text(project_dir, rel, line))):
            ok, _ = find_article(rec, art)
            if not ok:
                findings.append(Finding("CN_ARTICLE_NOT_FOUND", "red", loc,
                                         f"《{title}》的目录树里没有「{art}」——引了不存在的条"))

    return findings


def _line_text(project_dir, rel, line):
    path = os.path.join(project_dir, rel)
    try:
        with open(path, encoding="utf-8") as f:
            for i, text in enumerate(f, 1):
                if i == line:
                    return text
    except OSError:
        return ""
    return ""


def render_cn(findings):
    reds = [f for f in findings if f.severity == "red"]
    yellows = [f for f in findings if f.severity == "yellow"]
    lines = ["== factscribe-legal verify-cn =="]
    if reds:
        lines.append(f"[红] {len(reds)} 处（必须修）")
        for i, f in enumerate(reds, 1):
            lines.append(f"  {i}. {f.code:28s} {f.location}  →  {f.message}")
    else:
        lines.append("[红] 0 处")
    lines.append("")
    if yellows:
        lines.append(f"[黄] {len(yellows)} 处")
        for i, f in enumerate(yellows, 1):
            lines.append(f"  {i}. {f.code:28s} {f.location}  →  {f.message}")
    else:
        lines.append("[黄] 0 处")
    lines.append("")
    if reds:
        lines.append(f"结论：{len(reds)} 红 → 红（退出码 1）")
    elif yellows:
        lines.append(f"结论：0 红 / {len(yellows)} 黄 → 黄（退出码 3）")
    else:
        lines.append("结论：0 红 / 0 黄 → 绿（退出码 0）")
    lines.append("注意：中国侧官方件不含条文正文 ⇒ 可核的是「法规现行有效」「条文号存在」「官方件未变」，"
                 "不是「数字出自正文」。")
    return "\n".join(lines), (1 if reds else (3 if yellows else 0))
