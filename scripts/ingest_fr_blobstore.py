#!/usr/bin/env python3
"""法国法条全量语料（corpus-bulk/fr）灌入 sihankor blobstore（共享压缩存储）。

工作单 feat/fr-blobstore-ingest（factscribe-dev worktree /tmp/fs-fringest-wt）：

    python3 -I scripts/ingest_fr_blobstore.py train    # 训练 zstd 字典（~500 XML 样本）
    python3 -I scripts/ingest_fr_blobstore.py ingest   # 灌库 343,602＋2 件，幂等可续
    python3 -I scripts/ingest_fr_blobstore.py stats    # 压缩率/dedup/前五大码/字典效果
    python3 -I scripts/ingest_fr_blobstore.py verify   # 四不变量＋round-trip＋源对表＋dedup 抽验

约定：
- blobstore 用 sihruntime 模块默认库（SIH_BLOBSTORE_DIR 未设 → ~/.local/share/sih/blobs），
  不在本脚本里硬编码 root——照模块自身机制。
- 条文件＝fr/ 下 *.xml 与 *.card.txt（171,801 对＝343,602 件）；另灌 fr/index.json 与
  fr/view_current.jsonl 两件；fr/raw/（Légifrance 原始 tar 包）与 state/ 不在清单。
- mapping manifest：JSONL 逐行追加，一行一件：
  {path, sha16, sha256, bytes, kind, codec, bytes_out, dict_sha16?, dedup}。
- 幂等可续：重跑先跳过 manifest 已收路径；未收件先 has(sha16) 探库，已存只补账不重压。
- 失败关闭：BlobStoreError、源 sha256/字节数与地表真值（corpus-bulk/manifest.json）不符、
  件数与 343,602＋2 不符——一律停机如实报，不带病续跑。
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

SIAH_RUNTIME = Path("/Users/moc/workspaces/SiAgent/sihankor-wt-ctx-loop/runtime")
sys.path.insert(0, str(SIAH_RUNTIME))

from sihruntime import blobstore  # noqa: E402
from sihruntime.blobstore import BlobStore, BlobStoreError  # noqa: E402

CORPUS_BULK = Path("/tmp/fs-frbulk-wt/integrations/factscribe-legal/corpus-bulk")
FR_DIR = CORPUS_BULK / "fr"
GT_MANIFEST = CORPUS_BULK / "manifest.json"  # 地表真值（fetch 时逐件 sha256）
REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_MANIFEST = (REPO_ROOT / "integrations/factscribe-legal/corpus-bulk"
                / "fr-blobstore-manifest.jsonl")
STATE_DIR = Path("/tmp/fs-fringest-state")

EXPECTED_ITEMS = 343_602          # 条文（xml＋证据卡）
EXPECTED_TOTAL = EXPECTED_ITEMS + 2  # ＋ index.json ＋ view_current.jsonl
DICT_SAMPLES = 500
DICT_SIZE = 131_072               # 模块默认
SEED = 20261117
SPECIALS = ("fr/index.json", "fr/view_current.jsonl")
PRE_EXISTING_ENTRIES = 41         # 默认库本次灌库前的既有块数（2026-11-09 烟测遗留）

CODE_ID_RE = re.compile(r"^CODE_ID:\s*(\S+)", re.M)
CODE_TITLE_RE = re.compile(r"^CODE_TITLE:\s*(.+)$", re.M)


def die(msg: str) -> None:
    print(f"FAIL-CLOSED: {msg}", file=sys.stderr)
    sys.exit(1)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def kind_of(relpath: str) -> str:
    name = relpath.rsplit("/", 1)[-1]
    if name == "index.json":
        return "fr-law-index"
    if name == "view_current.jsonl":
        return "fr-law-view"
    if name.endswith(".card.txt"):
        return "fr-law-card"
    if name.endswith(".xml"):
        return "fr-law-xml"
    raise BlobStoreError(f"清单内出现不认识的文件形：{relpath}")


def load_gt() -> dict[str, dict]:
    """地表真值：corpus-bulk/manifest.json 里 fr/ 语料件（不含 raw/ 与 state/）。"""
    raw = json.loads(GT_MANIFEST.read_text(encoding="utf-8"))
    gt = {}
    for e in raw["files"]:
        p = e["path"]
        if p.startswith("fr/") and not p.startswith("fr/raw/"):
            gt[p] = e
    return gt


def scan_items() -> list[str]:
    """灌库清单：条文 343,602 件（xml＋card 名序）＋ index.json ＋ view_current.jsonl。"""
    names = []
    for e in os.scandir(FR_DIR):
        if not e.is_file():
            continue
        n = e.name
        if n in ("index.json", "view_current.jsonl"):
            continue
        if n.endswith(".xml") or n.endswith(".card.txt"):
            names.append(n)
        else:
            die(f"fr/ 下出现清单外文件：{n}")
    xmls = [n for n in names if n.endswith(".xml")]
    cards = [n for n in names if n.endswith(".card.txt")]
    if len(names) != EXPECTED_ITEMS:
        die(f"条文件数不符：盘上 {len(names)}，期望 {EXPECTED_ITEMS}")
    if len(xmls) != len(cards) or len(xmls) * 2 != EXPECTED_ITEMS:
        die(f"xml/证据卡不成对：xml {len(xmls)}，card {len(cards)}")
    return [f"fr/{n}" for n in sorted(names)] + list(SPECIALS)


def load_manifest() -> list[dict]:
    """读 mapping manifest；末行残缺（中断残留）则截掉并如实报。"""
    if not OUT_MANIFEST.exists():
        return []
    text = OUT_MANIFEST.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    recs, ok_bytes = [], 0
    dropped = 0
    for ln in lines:
        try:
            recs.append(json.loads(ln))
            ok_bytes += len(ln.encode("utf-8"))
        except json.JSONDecodeError:
            dropped += 1
            break  # 只可能末行残缺：追加写中断
    if dropped:
        with open(OUT_MANIFEST, "r+", encoding="utf-8") as f:
            f.truncate(ok_bytes)
        print(f"resume: 截掉残缺末行 {dropped} 行（追加写中断残留）")
    return recs


def parse_code(stem_card: bytes) -> tuple[str, str]:
    m = CODE_ID_RE.search(stem_card.decode("utf-8", "replace"))
    t = CODE_TITLE_RE.search(stem_card.decode("utf-8", "replace"))
    return (m.group(1) if m else "(无码)"), (t.group(1).strip() if t else "(无题)")


# ------------------------------------------------------------------ train
def cmd_train(_args) -> None:
    xmls = sorted(e.name for e in os.scandir(FR_DIR)
                  if e.is_file() and e.name.endswith(".xml"))
    if len(xmls) < DICT_SAMPLES:
        die(f"XML 样本不足：{len(xmls)} < {DICT_SAMPLES}")
    step = (len(xmls) - 1) / (DICT_SAMPLES - 1)
    picks = sorted({xmls[round(i * step)] for i in range(DICT_SAMPLES)})
    samples = []
    for n in picks:
        samples.append((FR_DIR / n).read_bytes())
    store = BlobStore()
    t0 = time.monotonic()
    dict_sha16 = store.train_dict(samples, size=DICT_SIZE)
    dt = time.monotonic() - t0
    if not store.has_dict(dict_sha16):
        die("训练后的字典不在库里")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "dict.json").write_text(json.dumps({
        "dict_sha16": dict_sha16,
        "size": DICT_SIZE,
        "n_samples": len(samples),
        "sample_bytes": sum(len(s) for s in samples),
        "backend": blobstore.zstd_backend().name,
        "seconds": round(dt, 3),
    }, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok", "dict_sha16": dict_sha16, "size": DICT_SIZE,
        "n_samples": len(samples),
        "sample_bytes": sum(len(s) for s in samples),
        "backend": blobstore.zstd_backend().name,
        "seconds": round(dt, 3),
    }, ensure_ascii=False))


# ------------------------------------------------------------------ ingest
def cmd_ingest(_args) -> None:
    state = json.loads((STATE_DIR / "dict.json").read_text(encoding="utf-8"))
    dict_sha16 = state["dict_sha16"]
    store = BlobStore()
    if not store.has_dict(dict_sha16):
        die(f"库里没有训练字典 {dict_sha16}——拒绝无字典灌库")
    entries_before = store.stats()["entries"]

    gt = load_gt()
    items = scan_items()
    missing_gt = [p for p in items if p not in gt]
    if missing_gt:
        die(f"地表真值缺件 {len(missing_gt)} 例，如 {missing_gt[:3]}")

    recs = load_manifest()
    done = {r["path"]: r for r in recs}
    dup_paths = len(recs) - len(done)
    if dup_paths:
        die(f"manifest 内路径重复 {dup_paths} 行——账有伤，先人查再续")
    if done:
        print(f"resume: manifest 已收 {len(done)} 件，续跑补齐 {len(items)-len(done)} 件")

    t0 = time.monotonic()
    puts = dedup_skips = 0
    OUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MANIFEST, "a", encoding="utf-8") as mf:
        for i, relpath in enumerate(items, 1):
            if relpath in done:
                continue
            data = (CORPUS_BULK / relpath).read_bytes()
            digest = sha256(data)
            g = gt[relpath]
            if g["sha256"] != digest or g["bytes"] != len(data):
                die(f"源与地表真值不符：{relpath}（真值 {g['sha256'][:16]}/"
                    f"{g['bytes']}B，实读 {digest[:16]}/{len(data)}B）")
            sid = digest[:16]
            if store.has(sid):  # 已存块：只补账不重压（重跑跳过）
                rec = store.meta(sid)
                dedup = True
                dedup_skips += 1
            else:
                rec = store.put(data, kind=kind_of(relpath),
                                codec="zstd+dict", dict_sha16=dict_sha16)
                dedup = bool(rec["dedup"])
                puts += 1
                if dedup:
                    dedup_skips += 1
            line = {
                "path": relpath, "sha16": rec["sha16"], "sha256": rec["sha256"],
                "bytes": len(data), "kind": kind_of(relpath),
                "codec": rec["codec"], "bytes_out": rec["bytes_out"],
                "dedup": dedup,
            }
            if rec.get("dict_sha16"):
                line["dict_sha16"] = rec["dict_sha16"]
            mf.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
            if i % 20_000 == 0:
                mf.flush()
                dt = time.monotonic() - t0
                remain = len(items) - i
                rate = i / dt if dt else 0.0
                print(f"progress {i}/{len(items)}  {rate:.0f} 件/s  "
                      f"已 {dt:.0f}s  剩约 {remain/rate:.0f}s"
                      f"（put {puts}，has 跳过 {dedup_skips}）", flush=True)
        mf.flush()
        os.fsync(mf.fileno())

    # 收账核对：manifest 行数＝343,602＋2，零遗漏零重复
    final = load_manifest()
    paths = [r["path"] for r in final]
    if len(paths) != len(set(paths)):
        die("manifest 出现重复路径")
    if set(paths) != set(items):
        lack = set(items) - set(paths)
        extra = set(paths) - set(items)
        die(f"manifest 与清单不齐：缺 {len(lack)} 如 {sorted(lack)[:3]}；"
            f"多 {len(extra)} 如 {sorted(extra)[:3]}")

    dt = time.monotonic() - t0
    summary = {
        "status": "ok",
        "items": len(items),
        "manifest_lines": len(final),
        "puts": puts,
        "has_skips": dedup_skips,
        "resumed_done": len(done),
        "seconds": round(dt, 1),
        "store_entries_before": entries_before,
        "store_entries_after": store.stats()["entries"],
        "dict_sha16": dict_sha16,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "ingest-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


# ------------------------------------------------------------------ stats
def cmd_stats(_args) -> None:
    recs = load_manifest()
    if len(recs) != EXPECTED_TOTAL:
        die(f"manifest 行数 {len(recs)} ≠ {EXPECTED_TOTAL}")
    store = BlobStore()

    raw_total = sum(r["bytes"] for r in recs)
    line_out_total = sum(r["bytes_out"] for r in recs)   # 每件按自身压缩件计
    dedup_hits = sum(1 for r in recs if r["dedup"])

    with store._lock:
        row = store._conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(bytes_in),0) bi,"
            " COALESCE(SUM(bytes_out),0) bo FROM blobs WHERE kind LIKE 'fr-law-%'"
        ).fetchone()
    uniq_n, uniq_in, uniq_out = int(row["n"]), int(row["bi"]), int(row["bo"])
    dict_row = store._conn.execute(
        "SELECT sha16, LENGTH(bytes) FROM dicts").fetchall()
    dict_bytes = sum(int(r[1]) for r in dict_row)

    per_kind = defaultdict(lambda: [0, 0, 0])  # kind → [n, bytes, bytes_out]
    for r in recs:
        k = per_kind[r["kind"]]
        k[0] += 1
        k[1] += r["bytes"]
        k[2] += r["bytes_out"]

    # 逐码归并：从证据卡 CODE_ID/CODE_TITLE 归码（xml 搭同源卡）
    codeacc: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    code_title = {}
    card_cache: dict[str, tuple[str, str]] = {}
    for r in recs:
        name = r["path"].rsplit("/", 1)[-1]
        if name.endswith(".xml"):
            stem = name[:-4]
        elif name.endswith(".card.txt"):
            stem = name[:-9]
        else:
            continue
        if stem not in card_cache:
            cp = FR_DIR / f"{stem}.card.txt"
            card_cache[stem] = parse_code(cp.read_bytes()) if cp.exists() \
                else ("(无卡)", "(无卡)")
        cid, ctitle = card_cache[stem]
        code_title[cid] = ctitle
        blob = codeacc[cid].setdefault(r["sha16"], (r["bytes"], r["bytes_out"]))
        if blob[0] != r["bytes"]:
            die(f"同块不同长：{r['path']} vs 库内 {blob}")
    codes = []
    for cid, blobs in codeacc.items():
        bi = sum(v[0] for v in blobs.values())
        bo = sum(v[1] for v in blobs.values())
        codes.append({"code_id": cid, "title": code_title[cid],
                      "files": len(blobs), "bytes_in": bi, "bytes_out": bo,
                      "ratio": round(bi / bo, 3) if bo else 0.0})
    codes.sort(key=lambda c: -c["bytes_in"])

    # 字典效果对比：中位 xml＋其卡，各压两遍（有字典／无字典）
    xml_recs = sorted((r for r in recs if r["kind"] == "fr-law-xml"),
                      key=lambda r: r["bytes"])
    mid = xml_recs[len(xml_recs) // 2]
    samples = [mid["path"], mid["path"].replace(".xml", ".card.txt")]
    dict_sha16 = json.loads((STATE_DIR / "dict.json").read_text())["dict_sha16"]
    dict_demo = []
    for p in samples:
        data = (CORPUS_BULK / p).read_bytes()
        with_d = store.compress(data, dict_sha16=dict_sha16)
        no_d = store.compress(data)
        dict_demo.append({
            "path": p, "bytes": len(data),
            "bytes_out_dict": with_d["bytes_out"],
            "bytes_out_plain": no_d["bytes_out"],
            "ratio_dict": round(len(data) / with_d["bytes_out"], 2),
            "ratio_plain": round(len(data) / no_d["bytes_out"], 2),
        })

    summary = {
        "manifest_lines": len(recs),
        "raw_total_bytes": raw_total,
        "raw_total_gib": round(raw_total / 2**30, 3),
        "stored_unique_bytes": uniq_out,            # 库内 fr-law-* 压缩件总量（去重后）
        "stored_unique_plus_dict_bytes": uniq_out + dict_bytes,
        "line_compressed_bytes": line_out_total,    # 每件独立压缩件合计（未去重口径）
        "ratio_with_dedup": round(raw_total / uniq_out, 3) if uniq_out else 0,
        "ratio_compression_only": round(raw_total / line_out_total, 3)
                                  if line_out_total else 0,
        "dedup_hits": dedup_hits,
        "unique_blobs": uniq_n,
        "unique_bytes_in": uniq_in,
        "kinds": {k: {"files": v[0], "bytes_in": v[1], "bytes_out": v[2],
                      "ratio": round(v[1] / v[2], 3) if v[2] else 0}
                  for k, v in sorted(per_kind.items())},
        "code_count": len(codes),
        "top5_codes": codes[:5],
        "dict_demo": dict_demo,
        "dict_sha16": dict_sha16,
        "dict_bytes": dict_bytes,
    }
    if (STATE_DIR / "ingest-summary.json").exists():
        summary["ingest_timing"] = json.loads(
            (STATE_DIR / "ingest-summary.json").read_text())
    print(json.dumps(summary, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ verify
def cmd_verify(_args) -> None:
    recs = load_manifest()
    if len(recs) != EXPECTED_TOTAL:
        die(f"manifest 行数 {len(recs)} ≠ {EXPECTED_TOTAL}")
    store = BlobStore()
    failures: list[str] = []

    # 0) 四不变量（隔离 scratch 库）
    v = store.verify()
    for c in v["checks"]:
        print(f"{'OK ' if c['ok'] else 'BAD'} {c['id']} {c['name']} — {c['detail']}")
    if not v["ok"]:
        failures.append("blobstore.verify() 四不变量未全过")

    by_path = {r["path"]: r for r in recs}
    by_sha16 = defaultdict(list)
    for r in recs:
        by_sha16[r["sha16"]].append(r)

    # 1) 随机 100 块 round-trip（get == 源文件逐字节，且 sha256 对表）
    rng = random.Random(SEED)
    sample = rng.sample(recs, 100)
    rt_ok = 0
    for r in sample:
        src = (CORPUS_BULK / r["path"]).read_bytes()
        back = store.get(r["sha16"])
        if back == src and sha256(back) == r["sha256"]:
            rt_ok += 1
        else:
            failures.append(f"round-trip 失败：{r['path']}")
    print(f"round-trip 抽验：{rt_ok}/100")

    # 2) 源对表 10 块（显式逐字节 sha256 重算，与 manifest、库账三方对齐）
    src_ok = 0
    for r in sample[:10]:
        src = (CORPUS_BULK / r["path"]).read_bytes()
        m = store.meta(r["sha16"])
        if sha256(src) == r["sha256"] == m["sha256"] and len(src) == m["bytes_in"]:
            src_ok += 1
        else:
            failures.append(f"源对表失败：{r['path']}")
    print(f"源 sha256 对表：{src_ok}/10")

    # 3) dedup 证据卡 20 张：内容相同卡必须同 sha16、同库块、逐字节一致
    card_groups = {s: rs for s, rs in by_sha16.items()
                   if len(rs) > 1 and rs[0]["kind"] == "fr-law-card"}
    multi_paths = sum(len(rs) for rs in card_groups.values())
    group_list = sorted(card_groups.items(), key=lambda kv: kv[0])
    picked_groups = group_list[:20] if len(group_list) >= 20 else group_list
    dd_ok = 0
    for _s, rs in picked_groups:
        contents = [store.get(r["sha16"]) for r in rs[:2]]
        srcs = [(CORPUS_BULK / r["path"]).read_bytes() for r in rs[:2]]
        if len(set(map(bytes, contents))) == 1 and contents == srcs:
            dd_ok += 1
        else:
            failures.append(f"dedup 卡不一致：{[r['path'] for r in rs[:2]]}")
    print(f"dedup 证据卡抽验：{dd_ok}/{len(picked_groups)}"
          f"（同内容卡组 {len(card_groups)} 组，覆盖路径 {multi_paths} 条）")

    # 4) 全量在库覆盖：manifest 每一块都 has() 得到，且块数与库账一致
    missing = [s for s in by_sha16 if not store.has(s)]
    if missing:
        failures.append(f"manifest 有 {len(missing)} 块不在库里，如 {missing[:3]}")
    with store._lock:
        row = store._conn.execute(
            "SELECT COUNT(*) FROM blobs WHERE kind LIKE 'fr-law-%'").fetchone()
    if int(row[0]) != len(by_sha16):
        failures.append(f"库内 fr-law-* 块数 {row[0]} ≠ manifest 唯一块数 {len(by_sha16)}")
    total = store.stats()["entries"]
    print(f"全量在库覆盖：{len(by_sha16) - len(missing)}/{len(by_sha16)}；"
          f"库账 entries={total}（灌前既有 {PRE_EXISTING_ENTRIES}）")
    if total != PRE_EXISTING_ENTRIES + len(by_sha16):
        failures.append(f"库账条数异常：{total} ≠ {PRE_EXISTING_ENTRIES}＋{len(by_sha16)}")

    if failures:
        for f in failures:
            print(f"FAIL {f}", file=sys.stderr)
        sys.exit(1)
    print("VERIFY OK：四不变量＋round-trip＋源对表＋dedup 抽验＋全量在库覆盖全过")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("train").set_defaults(fn=cmd_train)
    sub.add_parser("ingest").set_defaults(fn=cmd_ingest)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    sub.add_parser("verify").set_defaults(fn=cmd_verify)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
