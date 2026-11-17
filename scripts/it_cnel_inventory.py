#!/usr/bin/env python3
"""意大利 CCNL 全行业清单层（corpus-bulk-it）——CNEL 档案「现行或超期有效」专区主表。

来源：CNEL Archivio nazionale dei contratti collettivi（L.936/1986 art.17 官方档案），
    清单表 xlsx 挂 www.cnel.it（无反爬，礼貌单发即可）：
    https://www.cnel.it/media/docs/default-source/archivio-contratti---cartelle-excel/
        ccnl-di-settore-vigenti-e-ultrattivi.xlsx

子命令：
    python3 -I scripts/it_cnel_inventory.py fetch     # 下载 xlsx→解析 sheet①→TSV＋clusters.json＋manifest 行
    python3 -I scripts/it_cnel_inventory.py verify    # 对账：TSV/clusters.json 与 state 中的 xlsx sha256

约定：
- 纯标准库（zipfile+regex 解 xlsx，不引第三方）。
- _state/ 下留 xlsx 原件缓存＋请求日志；TSV/clusters.json/manifest 入仓（皆元数据，IODL 2.0）。
- 幂等：manifest 追加行仅在 xlsx sha256 变化时写一行 {kind:"inventory",...}。
- 礼貌：单请求＋UA 真实浏览器串＋失败即停（不带病续跑）。
- 法律面：取件合法（官方档案公开）；全文再分发未清权（当事方 Proprietà riservata）——
  本脚本只取清单元数据，不取全文（见 ATTRIBUTION）。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

XLSX_URL = (
    "https://www.cnel.it/media/docs/default-source/archivio-contratti---cartelle-excel/"
    "ccnl-di-settore-vigenti-e-ultrattivi.xlsx?sfvrsn=eb19a03c_17"
)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

HERE = Path(__file__).resolve().parent
WORKDIR = HERE.parent / "integrations" / "factscribe-legal" / "corpus-bulk-it"
STATE_DIR = WORKDIR / "_state"

COLS = [
    ("A", "code"),
    ("B", "title"),
    ("C", "firmatari_datoriali"),
    ("D", "firmatari_sindacali"),
    ("E", "firmatari_sindacali_adesione"),
    ("F", "firmatari_sindacali_tavolo_separato"),
    ("G", "inizio_storia"),
    ("H", "scadenza_ultimo_accordo"),
    ("I", "datori_2025"),
    ("J", "dipendenti_m_2025"),
    ("K", "dipendenti_f_2025"),
    ("L", "dipendenti_2025"),
]
EPOCH = datetime.date(1899, 12, 30)


def xldate(v: str) -> str:
    """Excel serial date → ISO 8601；非日期原样返回。"""
    try:
        return (EPOCH + datetime.timedelta(days=int(float(v)))).isoformat()
    except (TypeError, ValueError):
        return v or ""


def parse_xlsx(path: Path) -> list[dict]:
    """解析 sheet「1 - CCNL di settore, elenco」为行字典列表（含表头/杂行过滤）。"""
    z = zipfile.ZipFile(path)
    shared_xml = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
    strings = [re.sub(r"<[^>]+>", "", s) for s in re.findall(r"<si>(.*?)</si>", shared_xml, re.S)]

    # 找主清单表（名含 "elenco"）
    wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
    sheets = re.findall(r'<sheet name="([^"]+)"[^>]*r:id="rId(\d+)"', wb)
    target = next((f"xl/worksheets/sheet{n}.xml") for name, n in sheets if "elenco" in name.lower())
    sheet = z.read(target).decode("utf-8", "replace")

    rows: list[dict] = []
    for _rno, rowxml in re.findall(r'<row[^>]*r="(\d+)"[^>]*>(.*?)</row>', sheet, re.S):
        cells: dict[str, str] = {}
        for m in re.finditer(
            r'<c r="([A-Z]+)(\d+)"(?:[^>]*t="([^"]*)")?[^>]*>(?:<v>(.*?)</v>)?(?:<is><t[^>]*>(.*?)</t></is>)?', rowxml
        ):
            col, _row, t, v, inline = m.groups()
            if t == "s" and v:
                cells[col] = strings[int(v)]
            elif inline:
                cells[col] = re.sub(r"<[^>]+>", "", inline)
            elif v:
                cells[col] = v
        if not cells.get("A"):
            continue
        row = {}
        for col, key in COLS:
            raw = cells.get(col, "")
            row[key] = xldate(raw) if key in ("inizio_storia", "scadenza_ultimo_accordo") else (raw or "").strip()
        # 簇行＝code「字母起头＋共 4 位数字字母」（A011/HV17/GI81/D0L1…）；「CCNL id」表头跳过
        if not re.fullmatch(r"[A-Z][A-Z0-9]{3}", row["code"]):
            if "CCNL id" not in row["code"]:
                raise ValueError(f"unexpected non-code row in sheet: {row['code']!r} title={row['title']!r}")
            continue
        rows.append(row)
    return rows


def fetch(workdir: Path) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    xlsx_path = STATE_DIR / "ccnl-di-settore-vigenti-e-ultrattivi.xlsx"
    req = urllib.request.Request(XLSX_URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except Exception as e:  # 失败即停
        print(f"FAIL download: {e}", file=sys.stderr)
        return 1
    xlsx_path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    print(f"downloaded {len(data)} bytes sha256={sha[:16]}")

    rows = parse_xlsx(xlsx_path)  # 表头过滤在 parse_xlsx 内（verify 同口径）
    codes = [r["code"] for r in rows]
    dupes = {c for c in codes if codes.count(c) > 1}
    if dupes:
        print(f"FAIL duplicate codes in inventory: {sorted(dupes)}", file=sys.stderr)
        return 1

    # TSV（全字段）
    tsv = workdir / "it-inventory-vigenti.tsv"
    header = [k for _, k in COLS]
    with tsv.open("w", encoding="utf-8") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(r[k] for _, k in COLS) + "\n")

    # clusters.json（采集器输入：码＋标题）
    clusters = [{"code": r["code"], "title": r["title"], "dipendenti_2025": r["dipendenti_2025"]} for r in rows]
    (workdir / "it-clusters.json").write_text(
        json.dumps({"source": XLSX_URL, "xlsx_sha256": sha, "n": len(clusters), "clusters": clusters}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    # manifest 追加行（仅在 sha 变化时）
    manifest = workdir / "it-ccnl-accordi-manifest.ndjson"
    prev_sha = None
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("kind") == "inventory":
                prev_sha = rec.get("xlsx_sha256")
    if prev_sha != sha:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with manifest.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "kind": "inventory",
                        "ts": ts,
                        "xlsx_url": XLSX_URL,
                        "xlsx_sha256": sha,
                        "xlsx_bytes": len(data),
                        "n_clusters": len(rows),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        print(f"manifest: inventory line appended (sha {prev_sha} -> {sha[:16]})")
    else:
        print("manifest: inventory unchanged, no line appended")

    # 请求日志
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with (STATE_DIR / "request-log.ndjson").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "url": XLSX_URL, "status": 200, "bytes": len(data)}) + "\n")

    print(f"OK: {len(rows)} clusters -> {tsv.name}, it-clusters.json")
    return 0


def verify(workdir: Path) -> int:
    manifest = workdir / "it-ccnl-accordi-manifest.ndjson"
    inv_lines = [json.loads(l) for l in manifest.read_text(encoding="utf-8").splitlines() if '"inventory"' in l]
    if not inv_lines:
        print("FAIL no inventory line in manifest", file=sys.stderr)
        return 1
    rec = inv_lines[-1]
    cached = STATE_DIR / "ccnl-di-settore-vigenti-e-ultrattivi.xlsx"
    if not cached.exists():
        print(f"FAIL cached xlsx missing: {cached}", file=sys.stderr)
        return 1
    data = cached.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    ok_sha = sha == rec["xlsx_sha256"]
    rows = parse_xlsx(cached)
    ok_n = len(rows) == rec["n_clusters"]
    clusters = json.loads((workdir / "it-clusters.json").read_text(encoding="utf-8"))
    ok_json = [c["code"] for c in clusters["clusters"]] == [r["code"] for r in rows]
    tsv = (workdir / "it-inventory-vigenti.tsv").read_text(encoding="utf-8").splitlines()
    ok_tsv = len(tsv) == len(rows) + 1
    print(f"sha256 match: {ok_sha}; n_clusters {len(rows)}=={rec['n_clusters']}: {ok_n}; "
          f"clusters.json codes match: {ok_json}; tsv rows match: {ok_tsv}")
    return 0 if (ok_sha and ok_n and ok_json and ok_tsv) else 1


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fetch":
        return fetch(WORKDIR)
    if cmd == "verify":
        return verify(WORKDIR)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
