"""法国**判例**专项校验：把「引的是哪件法国官方法院判决、官方判决件有没有被动过、
那个金额/日期是不是真出自官方判决正文」变成机械判定。

与法条两维的判据差异（因为官方材料形态不同）：
  法条维度（法国）：官方件 = 条文 XML ⇒ 可判「数字出自该条正文」
  **判例维度（法国）：官方件 = 判决 XML（TEXTE_JURI_JUDI）** ⇒ 也能判
  「数字出自官方判决正文」，且多一层「案号一致」（判决自带案号）。

判据清单（全部红；红＝必须修）：
  FR_CASE_CARD_MISSING             事实账指向的判例证据卡不存在
  FR_CASE_OFFICIAL_MISSING         官方判决副本（XML 或纯文本还原件）不存在
  FR_CASE_CARD_NO_HASH             证据卡里缺 OFFICIAL_XML_SHA256 / OFFICIAL_TXT_SHA256 声明
  FR_CASE_OFFICIAL_HASH_MISMATCH   官方件现算哈希与卡片声明不符（官方件被改，fail-closed）
  FR_CASE_CARD_SHA256_MISMATCH     证据卡自身被改过（事实账钉的哈希与现算不符）
  FR_CASE_VALUE_NOT_IN_OFFICIAL    事实里的值不真出自官方判决正文（法式归一后仍找不到）
  FR_CASE_NO_MISMATCH              卡片案号与官方元数据（TITRE/NUMEROS_AFFAIRES）对不上
  FR_CASE_DATE_MISMATCH            卡片裁判日期与官方元数据/正文法文日期对不上
  FR_CASE_CARD_TEXT_DIVERGED       卡片内嵌的官方正文段与 official/*.txt 不一致

码一律 `FR_` 前缀（域前缀制：LEGAL_/CN_/CASE_/IT_/ES_/FR_ 各域一前缀；
码名只增不改，与既有全表零交集）。

法国写法的三条坑（照侦察批实测，处理不到位会误报红）：
  1. 金额：千分位是点（`300.000`＝30 万）或空格（`3 500`）；小数是逗号
     （`1 234,56`）⇒ 法式归一后比对，不能用中国 reader 的「去逗号」。
  2. 案号三形态：`01-16.595`（TITRE）／`01-16595`（NUMEROS_AFFAIRES）／
     `98-10.525`（正文，**可能是被引用的他案**）⇒ 案号一致性**只锚 XML
     元数据**（去点归一），不拿「正文出现过」当证据。
  3. 日期：元数据 ISO（2004-09-29）／正文法文月名（«29 septembre 2004»）
     ⇒ ISO↔法文月名双向匹配。

退出码沿用上游：0 绿 / 1 红 / 2 配置错 / 3 黄
"""
import hashlib
import os
import re

from .fr_case_reader import (card_text_fields, fr_date_to_iso, fr_dates_in,
                             fr_numbers_in, meta_case_numbers, norm_case_no,
                             norm_fr_number, parse_meta)
from .verify import Finding, load_facts

CARD_RE = re.compile(r"^runs/(?P<run>[^/]+)/(?P<case_id>[^/]+)\.fr-case\.card\.txt$")
CARD_MARK = "--- OFFICIAL TEXT ---"


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm_space(text):
    """空白归一（NBSP/窄空格→空格；连续空白→单空格）——字面比对用。"""
    out = []
    for ch in text or "":
        if ch in "\u00a0\u202f\u2009\u2007\u2008\u2005":
            out.append(" ")
        else:
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _value_in_official(value, official_text, meta):
    """事实的值是否真出自官方判决正文。

    返回 (命中?, 说法)。三种值型：
      数字 → 法式归一后与正文归一 token 集合比对（`300.000`≡`300000`≡`300 000`）
      日期 → ISO↔法文月名双向（正文法文日期或元数据 DATE_DEC 任一命中即算）
      其它 → 字面（空白归一后）命中
    """
    raw = str(value if value is not None else "").strip()
    if not raw:
        return True, "空值不判"

    # 1) 日期（含 ISO 与法文月名两种写法）
    iso = fr_date_to_iso(raw)
    if iso:
        if iso == fr_date_to_iso(meta.get("date_dec", "") or ""):
            return True, "日期与官方元数据 DATE_DEC 一致（%s）" % iso
        if iso in fr_dates_in(official_text):
            return True, "日期在官方正文里找到（%s）" % iso
        return False, "日期 %s 在官方正文与元数据里都找不到" % raw

    # 2) 数字（法式归一）
    canon = norm_fr_number(raw)
    if canon:
        if canon in fr_numbers_in(official_text):
            return True, "数值 %s 在官方正文里找到" % canon
        return False, "数值 %s（法式归一后）在官方正文里找不到" % raw

    # 3) 案号形态的值：去点归一后与官方元数据/正文比对
    if re.fullmatch(r"\d{2}-\d{2}[.\-]?\d{3,5}", raw):
        nc = norm_case_no(raw)
        if nc in meta_case_numbers(meta):
            return True, "案号 %s 与官方元数据一致" % raw
        if nc in _norm_space(official_text).replace(".", ""):
            return True, "案号 %s 在官方正文里找到" % raw
        return False, "案号 %s 在官方元数据与正文里都找不到" % raw

    # 4) 字面
    if _norm_space(raw) in _norm_space(official_text):
        return True, "值在官方正文里字面命中"
    return False, "值 %s 在官方正文里找不到" % raw[:40]


def verify_fr_case(project_dir):
    """跑法国判例专闸。返回 (findings, stats)。"""
    findings = []
    stats = {"cards": 0, "facts": 0, "runs": 0}
    checked_cards = set()
    run_ids = set()

    for fact in load_facts(project_dir):
        src = fact.get("source", "")
        if not src.endswith(".fr-case.card.txt"):
            continue  # 法条/中国/案例/意大利/西班牙的卡，各归各闸
        m = CARD_RE.match(src)
        if not m:
            continue
        stats["facts"] += 1
        run = m.group("run")
        case_id = m.group("case_id")
        run_ids.add(run)
        loc = "%s:%s" % (fact["_file"], fact.get("id", "?"))
        card_path = os.path.join(project_dir, src)

        # ---- 存在性 ----
        if not os.path.exists(card_path):
            findings.append(Finding("FR_CASE_CARD_MISSING", "red", loc,
                                    "法国判例证据卡不存在：%s" % src))
            continue
        off_dir = os.path.join(project_dir, "runs", run, "official")
        xml_path = os.path.join(off_dir, "%s.xml" % case_id)
        txt_path = os.path.join(off_dir, "%s.txt" % case_id)
        if not os.path.exists(xml_path) or not os.path.exists(txt_path):
            missing = []
            if not os.path.exists(xml_path):
                missing.append("runs/%s/official/%s.xml" % (run, case_id))
            if not os.path.exists(txt_path):
                missing.append("runs/%s/official/%s.txt" % (run, case_id))
            findings.append(Finding("FR_CASE_OFFICIAL_MISSING", "red", loc,
                                    "官方判决副本不存在：%s" % "、".join(missing)))
            continue

        with open(card_path, encoding="utf-8") as fh:
            card_text = fh.read()
        fields = card_text_fields(card_text)

        # ---- 官方件哈希钉版（fail-closed：声明缺了也判红）----
        decl_xml = (fields.get("OFFICIAL_XML_SHA256") or "").strip().lower()
        decl_txt = (fields.get("OFFICIAL_TXT_SHA256") or "").strip().lower()
        if not decl_xml or not decl_txt:
            findings.append(Finding(
                "FR_CASE_CARD_NO_HASH", "red", loc,
                "证据卡 %s 里缺 OFFICIAL_XML_SHA256 / OFFICIAL_TXT_SHA256 声明" % src))
            continue
        actual_xml = _sha256_file(xml_path)
        actual_txt = _sha256_file(txt_path)
        if decl_xml != actual_xml:
            findings.append(Finding(
                "FR_CASE_OFFICIAL_HASH_MISMATCH", "red", loc,
                "官方判决 XML 哈希与卡片声明不符"
                "（卡 %s… / 现算 %s…）——官方件被人动过"
                % (decl_xml[:12], actual_xml[:12])))
        if decl_txt != actual_txt:
            findings.append(Finding(
                "FR_CASE_OFFICIAL_HASH_MISMATCH", "red", loc,
                "官方判决纯文本还原件哈希与卡片声明不符"
                "（卡 %s… / 现算 %s…）——官方件被人动过"
                % (decl_txt[:12], actual_txt[:12])))

        # ---- 证据卡自身有没有被改 ----
        pinned = (fact.get("source_sha256") or "").removeprefix("sha256:").lower()
        if pinned and pinned != _sha256_file(card_path):
            findings.append(Finding(
                "FR_CASE_CARD_SHA256_MISMATCH", "red", loc,
                "证据卡 %s 自身被改过（事实账钉的哈希与现算不符）" % src))

        with open(txt_path, encoding="utf-8") as fh:
            official_text = fh.read()
        with open(xml_path, "rb") as fh:
            official_xml = fh.read()
        meta = parse_meta(official_xml)

        # ---- 事实的值必须真的出自官方判决正文 ----
        if fact.get("value") is not None:
            hit, why = _value_in_official(fact.get("value"), official_text, meta)
            if not hit:
                findings.append(Finding(
                    "FR_CASE_VALUE_NOT_IN_OFFICIAL", "red", loc,
                    "事实 %s 的%s" % (fact.get("id"), why)))

        # ---- 卡片级检查：每张卡只做一次 ----
        card_key = (run, case_id)
        if card_key in checked_cards:
            continue
        checked_cards.add(card_key)
        stats["cards"] += 1

        # A. 案号一致性：卡片声明的案号必须在**官方元数据**里（TITRE/NUMEROS_AFFAIRES）
        case_no = (fields.get("CASE_NO") or "").strip()
        meta_nos = meta_case_numbers(meta)
        if case_no:
            if norm_case_no(case_no) not in meta_nos:
                findings.append(Finding(
                    "FR_CASE_NO_MISMATCH", "red", loc,
                    "卡片案号 %s 与官方元数据（TITRE/NUMEROS_AFFAIRES）里的案号对不上"
                    "（官方：%s）——案号一致性只锚元数据，不拿正文出现过的他案号当证据"
                    % (case_no, "、".join(sorted(meta_nos)) or "（空）")))
        elif meta_nos:
            findings.append(Finding(
                "FR_CASE_NO_MISMATCH", "red", loc,
                "官方元数据里有案号 %s，卡片却没写 CASE_NO"
                % "、".join(sorted(meta_nos))))

        # B. 裁判日期一致性：卡片声明的日期必须与 DATE_DEC 或正文法文日期对得上
        judge_date = (fields.get("JUDGE_DATE") or fields.get("DATE_DEC") or "").strip()
        if judge_date:
            jd_iso = fr_date_to_iso(judge_date)
            meta_iso = fr_date_to_iso(meta.get("date_dec", "") or "")
            if not jd_iso:
                findings.append(Finding(
                    "FR_CASE_DATE_MISMATCH", "red", loc,
                    "卡片裁判日期 %s 不是可识别的日期（ISO 或法文月名都不像）"
                    % judge_date))
            elif jd_iso != meta_iso and jd_iso not in fr_dates_in(official_text):
                findings.append(Finding(
                    "FR_CASE_DATE_MISMATCH", "red", loc,
                    "卡片裁判日期 %s 与官方元数据 DATE_DEC（%s）和正文日期都对不上"
                    % (judge_date, meta_iso or "空")))

        # C. 卡片内嵌的官方正文段必须与 official/*.txt 一致
        if CARD_MARK in card_text:
            embedded = card_text.split(CARD_MARK, 1)[1]
            # 卡里标记后面先是一个换行（分隔行），再是正文；两端空行不计
            if embedded.lstrip("\n").rstrip("\n") != official_text.rstrip("\n"):
                findings.append(Finding(
                    "FR_CASE_CARD_TEXT_DIVERGED", "red", loc,
                    "卡片内嵌的官方正文与 official/*.txt 不一致"
                    "（卡片的正文副本被改过）"))
        else:
            findings.append(Finding(
                "FR_CASE_CARD_TEXT_DIVERGED", "red", loc,
                "卡片里找不到 %s 段" % CARD_MARK))

    stats["runs"] = len(run_ids)
    return findings, stats


def render_fr_case(findings, stats=None):
    reds = [f for f in findings if f.severity == "red"]
    yellows = [f for f in findings if f.severity == "yellow"]
    lines = ["== factscribe-legal verify-fr-case（法国判例）=="]
    if stats:
        lines.append("判例数 : %d 件（卡 %d 张 / 事实 %d 条 / run %d 个）"
                     % (stats.get("cards", 0), stats.get("cards", 0),
                        stats.get("facts", 0), stats.get("runs", 0)))
    lines.append("")
    if yellows:
        lines.append("[黄] %d 处" % len(yellows))
        for i, f in enumerate(yellows, 1):
            lines.append("  %d. %-28s %s  →  %s" % (i, f.code, f.location, f.message))
        lines.append("")
    if reds:
        lines.append("[红] %d 处（必须修）" % len(reds))
        for i, f in enumerate(reds, 1):
            lines.append("  %d. %-28s %s  →  %s" % (i, f.code, f.location, f.message))
    else:
        lines.append("[红] 0 处")
    lines.append("")
    if reds:
        lines.append("结论：%d 红 / %d 黄 → 红（退出码 1）" % (len(reds), len(yellows)))
    elif yellows:
        lines.append("结论：0 红 / %d 黄 → 黄（退出码 3）" % len(yellows))
    else:
        lines.append("结论：0 红 / 0 黄 → 绿（退出码 0）")
    lines.append("注意：绿只代表「引用的法国判决真实存在、官方件哈希未变、"
                 "且数值/日期真出自官方判决正文」，不代表判决写得对、"
                 "也不代表该案结论适用于你的案子。")
    return "\n".join(lines), (1 if reds else (3 if yellows else 0))
