"""法国**判例**专项校验：把「引的是哪件法国官方法院判决、官方判决件有没有被动过、
那个金额/日期是不是真出自官方判决正文」变成机械判定。

与法条两维的判据差异（因为官方材料形态不同）：
  法条维度（法国）：官方件 = 条文 XML ⇒ 可判「数字出自该条正文」
  **判例维度（法国）：官方件 = 判决 XML（TEXTE_JURI_JUDI）** ⇒ 也能判
  「数字出自官方判决正文」，且多一层「案号一致」（判决自带案号）。

判据清单（红＝必须修；黄＝声明/补正后可绿）：
  FR_CASE_CARD_MISSING             事实账指向的判例证据卡不存在（红）
  FR_CASE_OFFICIAL_MISSING         官方判决副本（XML 或纯文本还原件）不存在（红）
  FR_CASE_CARD_NO_HASH             证据卡里缺 OFFICIAL_XML_SHA256 / OFFICIAL_TXT_SHA256 声明（红）
  FR_CASE_OFFICIAL_HASH_MISMATCH   官方件现算哈希与卡片声明不符（官方件被改，fail-closed）（红）
  FR_CASE_CARD_SHA256_MISMATCH     证据卡自身被改过（事实账钉的哈希与现算不符）（红）
  FR_CASE_VALUE_NOT_IN_OFFICIAL    事实里的值不真出自官方判决全文（法式归一后仍找不到；伪造）（红）
  FR_CASE_NO_MISMATCH              卡片案号与官方元数据（TITRE/NUMEROS_AFFAIRES）对不上（红）
  FR_CASE_DATE_MISMATCH            卡片裁判日期与官方元数据/正文法文日期对不上（红）
  FR_CASE_CARD_TEXT_DIVERGED       卡片内嵌的官方正文段与 official/*.txt 不一致（红）

引文契约（P-166 收编自试车线闸包装层 quote_contract，判定逻辑照搬；
三路负控＋三席实弹已验，见 fr-trial-rolls/gate-align/QUOTE-CONTRACT-REPORT.md）：
  FR_CASE_VALUE_NOT_QUOTE          判例事实账 value 必须＝逐字引文（红）：
                                   案号形（01-16.595／01-16595）或去空白后 <25 字 ⇒ 红。
                                   数字/日期型 value 走 numnorm 对账，不受本契约约束。
  FR_CASE_STITCH_UNMARKED          无标记拼接/截断（红）：value 无省略号标记（[…]/[...]/…）
                                   且既不连续命中判决正文（CONTENU）也不连续命中官方件全文；
                                   或带标记拼接里有片段两面皆不命中。伪造由既有
                                   FR_CASE_VALUE_NOT_IN_OFFICIAL 另判，本码专抓无标记拼接。
  FR_CASE_QUOTE_FACE_UNDECLARED    摘要段引文未声明面（黄）：value 连续命中官方件全文但不在
                                   判决正文（CONTENU）内＝官方摘要段（SOMMAIRE/ANA）引文，
                                   且 claim/note 未声明面（résumé/摘要/sommaire/要旨 字样，
                                   或 quote_face 字段明标非正文面）——声明后按全文对账放行。
                                   分面区间从官方 XML 现算（to_plain_faces，确定性还原），
                                   或读旁车 official/<ID>.faces.json（钉 txt 哈希）；
                                   无法定面时按「全正文」处理，不发明面黄码。

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
                             norm_fr_number, parse_meta, read_faces_sidecar,
                             to_plain_faces)
from .verify import Finding, load_facts

CARD_RE = re.compile(r"^runs/(?P<run>[^/]+)/(?P<case_id>[^/]+)\.fr-case\.card\.txt$")
CARD_MARK = "--- OFFICIAL TEXT ---"

# ---- 引文契约常量（移植自闸包装层 quote_contract）----
# 案号形：01-16.595（TITRE 写法）/ 01-16595（官方去点写法）
CASENO_RE = re.compile(r"^\d{2}-\d{2,5}(?:\.\d{2,5})?$")
# 省略号标记闭集（与判卷器同口径）
ELLIPSIS_RE = re.compile(r"\[…\]|\[\.\.\.\]|…")
# 面声明字样（claim/note 内出现即算已声明面）
FACE_MARK_RE = re.compile(r"résumé|resume|摘要|sommaire|要旨", re.I)
# quote_face 字段里算「已声明非正文面」的取值
FACE_DECL_VALUES = frozenset(("résumé", "resume", "sommaire", "summary",
                              "摘要", "要旨"))
# 逐字引文最小长度（去空白后）；短于此＝案号/短语而非引文
MIN_QUOTE_LEN = 25


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


def _sha16(fact):
    """事实账钉的证据卡哈希前 16 位（收据用；没钉 → 「—」）。"""
    s = (fact.get("source_sha256") or "").strip()
    if s.startswith("sha256:"):
        s = s[len("sha256:"):]
    return s[:16] if s else "—"


def _face_declared(fact):
    """事实账是否声明了引文面（摘要段引文须声明后按全文对账放行）。

    两路：claim/note 含 résumé/摘要/sommaire/要旨 字样；或 quote_face 字段
    明标非正文面（résumé/sommaire/摘要/要旨…）。quote_face="body" 不算
    摘要段声明——声称正文却引在摘要段，照旧报黄。
    """
    hay = str(fact.get("claim", "") or "") + " " + str(fact.get("note", "") or "")
    if FACE_MARK_RE.search(hay):
        return True
    return str(fact.get("quote_face", "") or "").strip().lower() in FACE_DECL_VALUES


def _official_faces(off_dir, case_id, xml_bytes, official_text):
    """官方 txt 的正文分面区间（切片语义列表）；None＝无法定面（按全正文处理）。

    旁车 official/<ID>.faces.json 优先（钉 txt 哈希，失效即弃）；
    缺省从官方 XML 现算（to_plain_faces 确定性还原），现算文本与 official txt
    不逐字节一致时宁可不定面——分面错了会发明面黄码，不定面只少报不误报。
    """
    side = os.path.join(off_dir, "%s.faces.json" % case_id)
    if os.path.exists(side):
        ranges = read_faces_sidecar(side, official_text)
        if ranges is not None:
            return ranges
    try:
        text, ranges = to_plain_faces(xml_bytes)
    except Exception:  # noqa: BLE001 —— XML 坏了不该发明面，回落全正文口径
        return None
    if text != official_text:
        return None
    return ranges


def _span_in_text(value, text):
    """value 在官方 txt **原文坐标**里的首次命中区间（空白容忍）→ "s-e"。

    引文收据用：把 value 按空白切成 token、token 串用 `\\s+` 连接后搜索——
    NBSP/窄空格/换行差异不影响定位；找不到 → 「—」。
    """
    pat = r"\s+".join(re.escape(tok) for tok in str(value or "").split())
    if not pat:
        return "—"
    m = re.search(pat, text)
    return "%d-%d" % (m.start(), m.end()) if m else "—"


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


def _quote_contract(raw, fact_id, declared, loc, body_norm, full_norm,
                    official_text):
    """判例事实 value 的引文契约前置检查（P-166 收编，判定逻辑照搬包装层）。

    返回 (findings, face, span, how)：
      findings  本关新增 Finding：红 FR_CASE_VALUE_NOT_QUOTE / FR_CASE_STITCH_UNMARKED；
                黄 FR_CASE_QUOTE_FACE_UNDECLARED；
      face      命中面："body"（判决正文）/ "résumé"（仅官方摘要段）/ "—"；
      span      value 在官方 txt 原文坐标的首次命中区间（"s-e"；"—"＝定不到）；
      how       核验方式："contains"（逐字）/ "numnorm"（数字/日期归一）/ "—"。

    契约：value 必须＝逐字引文（案号形或过短 ⇒ 红）；无省略号标记且两面皆不
    连续命中 ⇒ 红（拼接/截断嫌疑，伪造由既有 FR_CASE_VALUE_NOT_IN_OFFICIAL
    另判）；仅摘要段命中且未声明面 ⇒ 黄（声明后按全文对账放行）。
    空值不判（口径同既有闸）；数字/日期型 value 走 numnorm 对账，不受逐字
    契约约束——数字锚点（如「48」对正文数词 quarante-huit）是既有闸的合法值型。
    """
    findings = []
    face, span, how = "—", "—", "—"
    if not raw:
        return findings, face, span, how          # 空值不判
    if fr_date_to_iso(raw) or norm_fr_number(raw):
        return findings, face, span, "numnorm"    # 数字/日期：numnorm 对账
    how = "contains"
    if CASENO_RE.match(raw) or len(raw) < MIN_QUOTE_LEN:
        why = ("案号形（%s）" % raw if CASENO_RE.match(raw)
               else "去空白后仅 %d 字（逐字引文至少 %d 字）" % (len(raw), MIN_QUOTE_LEN))
        findings.append(Finding(
            "FR_CASE_VALUE_NOT_QUOTE", "red", loc,
            "事实 %s 的 value 不像逐字引文：%s——判例事实账 value 必须＝判决正文"
            "逐字引文（数字/日期型 value 除外）" % (fact_id, why)))
        return findings, face, _span_in_text(raw, official_text), how
    v = _norm_space(raw)
    frags = [f for f in (_norm_space(x) for x in ELLIPSIS_RE.split(raw)) if f]
    marked = bool(ELLIPSIS_RE.search(raw))
    first_raw = ELLIPSIS_RE.split(raw)[0] if marked else raw
    span = _span_in_text(first_raw, official_text)
    in_body = [f in body_norm for f in frags]
    in_full = [f in full_norm for f in frags]
    if marked:
        # 带标记拼接：逐片段分类，任一片段两面皆未命中即红（片段缺失）
        if not all(b or f for b, f in zip(in_body, in_full)):
            n_miss = sum(1 for b, f in zip(in_body, in_full) if not b and not f)
            findings.append(Finding(
                "FR_CASE_STITCH_UNMARKED", "red", loc,
                "事实 %s 的 value 带「…」标记，但 %d/%d 个片段在判决正文（CONTENU）"
                "与官方件全文皆不连续命中——拼接里混入官方件没有的片段（拼接/截断嫌疑）"
                % (fact_id, n_miss, len(frags))))
            return findings, "—", span, how
        if any(f and not b for b, f in zip(in_body, in_full)):
            # 有片段仅摘要段命中 → 面声明复核
            face = "résumé"
            if not declared:
                findings.append(Finding(
                    "FR_CASE_QUOTE_FACE_UNDECLARED", "yellow", loc,
                    "事实 %s 的 value 是官方摘要段（SOMMAIRE/ANA）引文（含仅摘要段"
                    "命中的片段）——按 PREREG v2 允许引用但必须明标面：在 claim/note "
                    "写明 résumé/摘要/sommaire/要旨（或 quote_face 明标面），或把 "
                    "value 换成判决正文原文；声明后按全文对账放行" % fact_id))
            return findings, face, span, how
        return findings, "body", span, how
    # 无标记：要求连续命中任一面
    if v in body_norm:
        return findings, "body", span, how
    if v in full_norm:
        face = "résumé"
        if not declared:
            findings.append(Finding(
                "FR_CASE_QUOTE_FACE_UNDECLARED", "yellow", loc,
                "事实 %s 的 value 只在官方摘要段（SOMMAIRE/ANA）连续命中、不在判决"
                "正文（CONTENU）——按 PREREG v2 允许引用但必须明标面：在 claim/note "
                "写明 résumé/摘要/sommaire/要旨（或 quote_face 明标面），或把 value "
                "换成判决正文原文；声明后按全文对账放行" % fact_id))
        return findings, face, span, how
    findings.append(Finding(
        "FR_CASE_STITCH_UNMARKED", "red", loc,
        "事实 %s 的 value 无省略号标记，且在判决正文（CONTENU）与官方件全文皆不"
        "连续命中——只能是拼接/截断（伪造由 FR_CASE_VALUE_NOT_IN_OFFICIAL 另判）"
        % fact_id))
    return findings, "—", span, how


def verify_fr_case(project_dir):
    """跑法国判例专闸。返回 (findings, stats)。

    stats["receipts"]＝每条判例事实一行的核验收据
    （id｜sha256 前 16｜span｜命中面｜核验方式），render_fr_case 据此出
    「✅ 收据闭环」区——闸不光报红黄，还逐条证明「这条查过了、怎么查的」。
    """
    findings = []
    stats = {"cards": 0, "facts": 0, "runs": 0, "receipts": []}
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
        # ---- 收据（每条事实恰好一行；后续检查能查到什么就补什么）----
        receipt = {"id": str(fact.get("id", "?")), "sha16": _sha16(fact),
                   "span": "—", "face": "—", "how": "—"}
        stats["receipts"].append(receipt)
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

        # ---- 分面（③）：正文区间旁车优先，缺省从官方 XML 现算；无法定面
        #      ⇒ 全文视为正文（缺省口径，不发明面黄码）----
        faces = _official_faces(off_dir, case_id, official_xml, official_text)
        full_norm = _norm_space(official_text)
        if faces is None:
            body_norm = full_norm
        else:
            body_norm = _norm_space("\n".join(official_text[s:e]
                                              for s, e in faces))

        # ---- 事实的值必须真的出自官方判决正文 ----
        # 引文契约前置检查（①②③，P-166 收编）＋既有对账（伪造另判，照跑）
        if fact.get("value") is not None:
            raw = str(fact.get("value") or "").strip()
            new_findings, face, span, how = _quote_contract(
                raw, str(fact.get("id", "?")),
                _face_declared(fact), loc, body_norm, full_norm, official_text)
            findings.extend(new_findings)
            if face != "—":
                receipt["face"] = face
            if span != "—":
                receipt["span"] = span
            if how != "—":
                receipt["how"] = how
            # 既有对账（伪造另判）：整值字面命中检查。带省略号标记的值整值
            # 永不字面命中（标记不在原文里），逐片段对账已由引文契约做全——
            # 整值检查对带标记值只会发明假红，跳过；无标记值照跑
            # （无标记拼接/伪造 ⇒ STITCH_UNMARKED 与 NOT_IN_OFFICIAL 双红并存）。
            if raw and not ELLIPSIS_RE.search(raw):
                hit, why = _value_in_official(fact.get("value"), official_text,
                                              meta)
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
    """三区报告：✅ 收据闭环 → ⚠️ 黄码区（附修复指引）→ 🔴 红码区（附原因）。

    报告尾部固定一行边界声明；退出码语义不变（红 1 > 黄 3 > 绿 0）。
    """
    stats = stats or {}
    reds = [f for f in findings if f.severity == "red"]
    yellows = [f for f in findings if f.severity == "yellow"]
    receipts = stats.get("receipts") or []
    lines = ["== factscribe-legal verify-fr-case（法国判例）=="]
    if stats:
        lines.append("判例数 : %d 件（卡 %d 张 / 事实 %d 条 / run %d 个）"
                     % (stats.get("cards", 0), stats.get("cards", 0),
                        stats.get("facts", 0), stats.get("runs", 0)))
    lines.append("")
    # ---- ✅ 收据闭环：每条事实一行收据 ----
    lines.append("✅ 收据闭环（每条事实一行：id｜sha256 前 16｜span｜命中面｜核验方式）")
    if receipts:
        for r in receipts:
            lines.append("  %s｜%s｜%s｜%s｜%s"
                         % (r.get("id", "—"), r.get("sha16", "—"),
                            r.get("span", "—"), r.get("face", "—"),
                            r.get("how", "—")))
    else:
        lines.append("  （无判例事实）")
    lines.append("")
    # ---- ⚠️ 黄码区：每条黄码＋修复指引一句话 ----
    if yellows:
        lines.append("⚠️ 黄码区：%d 条（须声明/补正后复跑）" % len(yellows))
        for i, f in enumerate(yellows, 1):
            lines.append("  %d. %-30s %s" % (i, f.code, f.location))
            lines.append("     → %s" % f.message)
    else:
        lines.append("⚠️ 黄码区：0 条")
    lines.append("")
    # ---- 🔴 红码区：每条红码＋原因 ----
    if reds:
        lines.append("🔴 红码区：%d 条（必须修）" % len(reds))
        for i, f in enumerate(reds, 1):
            lines.append("  %d. %-30s %s" % (i, f.code, f.location))
            lines.append("     → %s" % f.message)
    else:
        lines.append("🔴 红码区：0 条")
    lines.append("")
    if reds:
        lines.append("结论：%d 红 / %d 黄 → 红（退出码 1）" % (len(reds), len(yellows)))
    elif yellows:
        lines.append("结论：0 红 / %d 黄 → 黄（退出码 3）" % len(yellows))
    else:
        lines.append("结论：0 红 / 0 黄 → 绿（退出码 0）")
    lines.append("边界声明：本闸只核验引用真实、在库、逐字、面内、账据一致；"
                 "法律判断正确性不在核验范围。")
    return "\n".join(lines), (1 if reds else (3 if yellows else 0))
