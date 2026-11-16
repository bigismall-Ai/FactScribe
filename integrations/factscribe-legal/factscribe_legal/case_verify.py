"""中国**案例**维度专项校验：把「引的是哪条官方案例、官方正文有没有被动过、那个赔偿金额是不是真出自官方正文」变成机械判定。

与法条两个维度的判据差异（因为官方材料形态不同）：
  法条维度（法国）：官方件 = 条文 XML ⇒ 可判「数字出自该条正文」
  法条维度（中国）：官方件 = 详情 JSON（只有目录树，无正文）⇒ 只能判「第X条在目录树里」
  **案例维度（中国）：官方件 = 官方入库案例的正文全文** ⇒ 又能判「数字出自官方正文」

判据清单：
  CASE_CARD_MISSING          事实账指向的案例证据卡不存在
  CASE_OFFICIAL_MISSING      官方正文副本不存在
  CASE_OFFICIAL_HASH_MISMATCH 官方正文副本的哈希 ≠ 卡片里声明的哈希（官方件被改）
  CASE_VALUE_NOT_IN_OFFICIAL  事实里的金额/案号/日期在官方正文里找不到（字面）
  CASE_NO_MISMATCH           卡片里的案号与官方正文里出现的案号对不上
  CASE_DATE_MISMATCH         卡片里的裁判日期与官方正文里的日期对不上
  CASE_CHAIN_BROKEN          FactScribe v3 证据链断了（fact.source → runs/<id>/result.json → record.json）

退出码沿用上游：0 绿 / 1 红 / 2 配置错 / 3 黄
"""
import hashlib
import json
import os
import re

from .verify import Finding, load_facts

CASE_CARD_RE = re.compile(r"^runs/(?P<run>[^/]+)/(?P<slug>.+)\.case\.card\.txt$")
NUM_RE = re.compile(r"^\d[\d,]*(\.\d+)?$")
# ⚠️ 必须覆盖事实值的实际写法：案例库元数据给的是 "2023.10.20"（点分隔），
#    若只认 YYYY-MM-DD，值会**静默落到字符串分支**按字面比 → 误报「找不到」。
DATE_RE = re.compile(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}$")


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
            if ":" in line and not line.startswith("#") and not line.startswith("---"):
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip()
    return out


def _norm_num(v):
    return v.replace(",", "")


CN_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def _dates_in(text):
    """把正文里的中文日期归一化成 YYYY-MM-DD 集合（卡片用 2023.10.20，正文写 2023年10月20日）"""
    out = set()
    for y, m, d in CN_DATE_RE.findall(text):
        out.add(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")
        out.add(f"{int(y):04d}.{int(m):02d}.{int(d):02d}")
    return out


def _date_present(value, official, dates):
    if value in official:
        return True
    try:
        y, m, d = re.split(r"[.\-/]", value)
        norm = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except Exception:  # noqa: BLE001
        return False
    return norm in dates


def verify_case(project_dir):
    findings = []
    run_ids = set()
    checked_cards = set()   # 卡片级检查每张卡只做一次

    for fact in load_facts(project_dir):
        src = fact.get("source", "")
        m = CASE_CARD_RE.match(src)
        if not m:
            continue
        loc = f"{fact['_file']}:{fact.get('id', '?')}"
        run = m.group("run")
        slug = m.group("slug")
        run_ids.add(run)
        card_path = os.path.join(project_dir, src)
        if not os.path.exists(card_path):
            findings.append(Finding("CASE_CARD_MISSING", "red", loc, f"案例证据卡不存在：{src}"))
            continue
        fields = _card_fields(card_path)
        if "OFFICIAL_TEXT_SHA256" not in fields:
            continue  # 不是案例卡

        # ---- 官方正文副本：现算哈希，与卡片声明比对 ----
        off_path = os.path.join(project_dir, "runs", run, "official", f"{slug}.txt")
        if not os.path.exists(off_path):
            findings.append(Finding("CASE_OFFICIAL_MISSING", "red", loc,
                                     f"官方正文副本不存在：runs/{run}/official/{slug}.txt"))
            continue
        actual = _sha256_file(off_path)
        if actual != fields.get("OFFICIAL_TEXT_SHA256"):
            findings.append(Finding("CASE_OFFICIAL_HASH_MISMATCH", "red", loc,
                                     f"官方正文哈希与卡片声明不符：声明 {fields['OFFICIAL_TEXT_SHA256'][:16]}… "
                                     f"实算 {actual[:16]}…（官方件被改）"))
            continue
        with open(off_path, encoding="utf-8") as f:
            official = f.read()
        dates = _dates_in(official)

        # ---- 事实的值必须真的在官方正文里（字面） ----
        val = str(fact.get("value", ""))
        if NUM_RE.match(val):
            if _norm_num(val) not in official.replace(",", ""):
                findings.append(Finding("CASE_VALUE_NOT_IN_OFFICIAL", "red", loc,
                                         f"金额 {val} 在官方正文里找不到"))
        elif DATE_RE.match(val):
            if not _date_present(val, official, dates):
                findings.append(Finding("CASE_VALUE_NOT_IN_OFFICIAL", "red", loc,
                                         f"日期 {val} 在官方正文里找不到"))
        else:
            if val and val not in official:
                findings.append(Finding("CASE_VALUE_NOT_IN_OFFICIAL", "red", loc,
                                         f"值 {val[:30]} 在官方正文里找不到"))

        # ---- 卡片级检查：每张卡只做一次（在 fact 循环里做会重复 N 遍）----
        card_key = (run, slug)
        if card_key in checked_cards:
            continue
        checked_cards.add(card_key)

        # A. 卡片声明的每个金额必须能在官方正文里找到
        #    （否则「改卡片 + 同步改账里的 source_sha256」只会被上游判**黄**，两层都不红）
        amounts = [x.strip() for x in fields.get("AMOUNTS", "").split(",") if x.strip()]
        for a in amounts:
            if _norm_num(a) not in official.replace(",", ""):
                findings.append(Finding("CASE_AMOUNT_MISMATCH", "red", loc,
                                         f"卡片声明的金额 {a} 在官方正文里找不到"
                                         "（卡片与官方件已脱钩）"))
        # B. 卡片内嵌的正文段必须与 official/*.txt 逐字节相同
        marker = "--- OFFICIAL TEXT ---\n"
        with open(card_path, encoding="utf-8") as fh:
            card_text = fh.read()
        if marker in card_text:
            embedded = card_text.split(marker, 1)[1]
            if embedded.rstrip("\n") != official.rstrip("\n"):
                findings.append(Finding("CASE_CARD_TEXT_DIVERGED", "red", loc,
                                         "卡片内嵌的正文与 official/*.txt 不一致"
                                         "（卡片的正文副本被改过）"))
        else:
            findings.append(Finding("CASE_CARD_TEXT_DIVERGED", "red", loc,
                                     "卡片里找不到 --- OFFICIAL TEXT --- 段"))

        # C. 案号一致性：卡片声明的案号必须在官方正文里出现
        case_no = fields.get("CASE_NO", "")
        if case_no and case_no not in official:
            findings.append(Finding("CASE_NO_MISMATCH", "red", loc,
                                     f"卡片案号 {case_no} 在官方正文里不存在"))
        jd = fields.get("JUDGE_DATE", "")
        if jd and not _date_present(jd, official, dates):
            findings.append(Finding("CASE_DATE_MISMATCH", "red", loc,
                                     f"裁判日期 {jd} 在官方正文里不存在"))

    # ---- FactScribe v3 证据链：fact.source → runs/<run>/result.json → record.json ----
    for run in sorted(run_ids):
        rdir = os.path.join(project_dir, "runs", run)
        rj = os.path.join(rdir, "result.json")
        cj = os.path.join(rdir, "record.json")
        if not os.path.exists(rj) or not os.path.exists(cj):
            findings.append(Finding("CASE_CHAIN_BROKEN", "red", f"runs/{run}",
                                     "缺少 result.json 或 record.json（证据链断）"))
            continue
        try:
            with open(rj, encoding="utf-8") as fh:
                result = json.load(fh)
            with open(cj, encoding="utf-8") as fh:
                record = json.load(fh)
        except Exception as e:  # noqa: BLE001
            findings.append(Finding("CASE_CHAIN_BROKEN", "red", f"runs/{run}", f"回执读不了：{e}"))
            continue
        if result.get("run_id") != run or record.get("run_id") != run:
            findings.append(Finding("CASE_CHAIN_BROKEN", "red", f"runs/{run}",
                                     "run_id 对不上"))
            continue
        # 上游 FactScribe 的 record.json 里 facts[] 是**字符串数组**
        rids = {str(x) for x in (record.get("facts") or [])}
        for fact in load_facts(project_dir):
            src = fact.get("source", "")
            m = CASE_CARD_RE.match(src)
            if not m or m.group("run") != run:
                continue
            fid = fact.get("id")
            if fid not in rids:
                findings.append(Finding("CASE_CHAIN_BROKEN", "red",
                                         f"{fact['_file']}:{fid}",
                                         f"record.json 的 facts[] 里没有 {fid}"))

    return findings


def render_case(findings):
    red = [f for f in findings if f.severity == "red"]
    yellow = [f for f in findings if f.severity == "yellow"]
    lines = ["【第 5 层 · 中国案例维度】"]
    if not findings:
        lines.append("  ✓ 绿：案例官方正文哈希、金额、案号、日期、证据链全部一致")
    for f in findings:
        mark = "🔴" if f.severity == "red" else ("🟡" if f.severity == "yellow" else "🟢")
        lines.append(f"  {mark} [{f.code}] {f.location}")
        lines.append(f"      {f.message}")
    lines.append(f"  —— 红 {len(red)} / 黄 {len(yellow)}")
    code = 1 if red else (3 if yellow else 0)
    lines.append(f"  退出码 {code}")
    return "\n".join(lines), code
