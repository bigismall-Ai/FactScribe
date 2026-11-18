#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PAN-PC-11 考卷：factscribe textreuse v2（多尺度窗＋句级包含）读数采集。

工单：/tmp/fs-gcards-wo/WORKORDER-PANFIX.md
判据：P-157（已冻结，本脚本不参与判据计算，数字一个不改）
语料：PAN Plagiarism Corpus 2011 (PAN-PC-11)，Zenodo record 3250095，CC BY 4.0。

**与 v1 的关系**：抽样、真源反推、案例构造、判据数字**逐字沿用**
`run_pan_experiment.py`（同 seed 20261118、同抽样顺序、同干扰源抽取、同判据）。
只改两处：① 工具调用换成 v2 工具的**默认参数**（多尺度 n=8/5 ＋ 句级包含）；
② 输出落到 `READINGS-PAN-V2.json`，并**逐例与 v1 读数对照**出前后表。

**dev/eval 分离（机械强制）**：
  * dev 档＝`random`（工单指定）＋G6 合成夹具 → 可反复跑；
  * eval 档＝`none` ＋ `clean`（P-157 原样）→ **只许跑一次**：
    跑完在 `EVAL-ONCE-RECEIPT.json` 落receipt，第二次调用直接报错退出。
    读数出来**不得回头调参**。

产出：experiments/fs-textreuse-pan/READINGS-PAN-V2.json
     /tmp/panfix-work/SUBSET-PAN-V2.json（子集清单副本；**不写 pan-corpus**）
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_pan_experiment as v1            # noqa: E402  复用 v1 的抽样/反推/案例构造

SEED = v1.SEED
N_PER_TIER = v1.N_PER_TIER
N_CLEAN_PAIRS = v1.N_CLEAN_PAIRS
N_DISTRACTORS = v1.N_DISTRACTORS
TIERS = v1.TIERS

WORK = Path("/tmp/panfix-work/_work")
SUBSET_JSON = Path("/tmp/panfix-work/SUBSET-PAN-V2.json")
OUT_JSON = HERE / "READINGS-PAN-V2.json"
RECEIPT = HERE / "EVAL-ONCE-RECEIPT.json"
V1_JSON = HERE / "READINGS-PAN.json"

# dev 档（可反复跑）／eval 档（只许跑一次）
DEV_TIERS = ("random",)
EVAL_TIERS = ("none", "clean")


def run_case(case_id, susp_path, b_files, extra_args=()):
    """跑一次工具（默认参数＝v2 口径：多尺度 8/5 ＋ 句级包含）。"""
    base = v1.RUN_ROOT / case_id
    a_dir, b_dir = base / "A", base / "B"
    for d in (a_dir, b_dir):
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*"):
            f.unlink()
    data = susp_path.read_bytes()
    (a_dir / susp_path.name).write_bytes(data)
    for src in b_files:
        (b_dir / src.name).write_bytes(src.read_bytes())
    cmd = [sys.executable, "-m", "factscribe", "textreuse",
           str(a_dir), str(b_dir), "--json", *extra_args]
    proc = subprocess.run(cmd, cwd=v1.FACTSCRIBE_ROOT, capture_output=True,
                          text=True, timeout=1800)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "bad json", "stderr": proc.stderr[-1000:],
                "stdout": proc.stdout[-1000:], "exit": proc.returncode}
    payload["_exit"] = proc.returncode
    return payload


def read_case(case_id, susp_path, b_files, primary_name, dist_names, f, tier):
    """跑一例并算读数（口径与 v1 逐字一致）。"""
    payload = run_case(case_id, susp_path, b_files)
    segs = payload.get("segments") or []
    text = susp_path.read_text(encoding="utf-8", errors="replace")
    offsets = v1.line_offsets(text)
    primary = [s for s in segs if s.get("b_file") == primary_name]
    false_segs = [s for s in segs if s.get("b_file") in dist_names]
    if f is not None:
        spans = [v1.line_range_to_chars(offsets, len(text),
                                       s.get("a_line_start", 1),
                                       s.get("a_line_end", 1)) for s in primary]
        cov = v1.coverage_of(f.span, spans)
    else:
        spans, cov = [], None
    by_source = {}
    for s in segs:
        key = s.get("match_source") or "word-window"
        by_source[key] = by_source.get(key, 0) + 1
    return {
        "case_id": case_id, "tier": tier,
        "suspicious_document": susp_path.name,
        "source_document": primary_name,
        "reported_primary_char_spans": [list(s) for s in spans],
        "true_source_reported": bool(primary),
        "char_coverage": None if cov is None else round(cov, 6),
        "distractor_reported": bool(false_segs),
        "distractor_matches": sorted({s.get("b_file") for s in false_segs}),
        "n_false_pairs": len(false_segs),
        "segments_total": len(segs),
        "segments_by_source": by_source,
        "reported_pairs": [{"b_file": s.get("b_file"),
                            "a_line_start": s.get("a_line_start"),
                            "a_line_end": s.get("a_line_end"),
                            "overlap_tokens": s.get("overlap_tokens"),
                            "match_source": s.get("match_source"),
                            "scale": s.get("scale")}
                           for s in segs],
        "exit_code": payload.get("_exit"), "error": payload.get("error"),
    }


def summarize(readings):
    """逐档汇总（判据数字与 v1 同口径）。"""
    out = {}
    for tier in list(TIERS) + ["clean"]:
        rows = [r for r in readings if r["tier"] == tier]
        if not rows:
            continue
        covs = [r["char_coverage"] for r in rows if r["char_coverage"] is not None]
        cov08 = [c for c in covs if c >= 0.8]
        item = {
            "n_cases": len(rows),
            "true_source_reported": len([r for r in rows if r["true_source_reported"]]),
            "char_coverage_ge_0.8": len(cov08),
            "char_coverage_mean": (round(sum(covs) / len(covs), 6) if covs else None),
            "char_coverage_median": (round(sorted(covs)[len(covs) // 2], 6)
                                     if covs else None),
            "n_cases_with_any_report": sum(1 for r in rows if r["segments_total"] > 0),
            "distractor_false_positive_cases": len([r for r in rows
                                                   if r["distractor_reported"]]),
        }
        if tier == "clean":
            item["any_report_cases"] = item["n_cases_with_any_report"]
        out[tier] = item
    return out


def judge(summary):
    """P-157 判据（数字不改）：none 覆盖≥0.8 ≥18/20 且干扰误配 ≤1；clean 零报告。"""
    verdicts = {}
    none = summary.get("none")
    if none:
        ok_cov = none["char_coverage_ge_0.8"] >= 18
        ok_fp = none["distractor_false_positive_cases"] <= 1
        verdicts["none"] = {
            "cov_ge_0.8": none["char_coverage_ge_0.8"], "need": ">=18",
            "distractor_fp_cases": none["distractor_false_positive_cases"],
            "need_fp": "<=1",
            "verdict": "PASS" if (ok_cov and ok_fp) else "FAIL",
        }
    clean = summary.get("clean")
    if clean:
        verdicts["clean"] = {
            "any_report_cases": clean["any_report_cases"], "need": "0",
            "verdict": "PASS" if clean["any_report_cases"] == 0 else "FAIL",
        }
    for tier in ("random", "manual"):
        if tier in summary:
            verdicts[tier] = {"verdict": "参考（不设门；random 档为 dev 集）"}
    return verdicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", default=",".join(DEV_TIERS),
                    help="要跑的档：dev=random（可反复）；eval=none,clean（只许一次）")
    ap.add_argument("--allow-eval", action="store_true",
                    help="显式声明「这是最终评测」——eval 档只认这一次")
    args = ap.parse_args()
    tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]
    is_eval = any(t in EVAL_TIERS for t in tiers)
    if is_eval:
        if not args.allow_eval:
            print("eval 档（none/clean）只许在最终评测跑一次：加 --allow-eval",
                  file=sys.stderr)
            return 2
        if RECEIPT.exists():
            print("eval 档已经跑过了（receipt: %s）——评测集只许跑一次。"
                  "读数在 READINGS-PAN-V2.json。" % RECEIPT, file=sys.stderr)
            return 2

    v1.WORK = WORK
    v1.SUBSET_JSON = SUBSET_JSON
    v1.OUT_JSON = Path("/tmp/panfix-work/_unused-v1.json")
    WORK.mkdir(parents=True, exist_ok=True)

    susp_dirs = v1.list_suspicious()
    src_dirs = v1.list_sources()
    feats, stats = v1.parse_features(susp_dirs)
    negatives = v1.parse_negatives(susp_dirs)
    src_names = sorted(p.name for d in src_dirs for p in d.glob("*.txt"))

    rng = random.Random(SEED)
    pools = {t: [f for f in feats if f.tier == t] for t in TIERS}
    picked = {t: v1.sample_tier(pools[t], N_PER_TIER, rng) for t in TIERS}
    negs = list(negatives)
    rng.shuffle(negs)
    cleans = [(n, rng.choice(src_names)) for n in negs[:N_CLEAN_PAIRS]]
    pool_sizes = {t: len(pools[t]) for t in TIERS}

    # 真源反推（与 v1 同口径）
    norm_path, src_meta = v1.build_normalized_sources(src_dirs)
    cases = []
    for t in TIERS:
        for i, f in enumerate(picked[t], 1):
            cases.append({"case_id": "%s-%03d" % (t, i), "tier": t,
                          "kind": "annotated", "feat": f, "feat_list": [f]})
    for i, (nm, nominal) in enumerate(cleans, 1):
        cases.append({"case_id": "clean-%03d" % i, "tier": "clean",
                      "kind": "clean", "susp_name": nm, "nominal": nominal,
                      "feat": None, "feat_list": []})
    hits = v1.resolve_sources(cases, src_meta, norm_path)
    for c in cases:
        if c["kind"] != "annotated":
            continue
        best = hits.get(c["case_id"])
        scale = best.get("_scale", {}) if best else {}
        cand = {k: val for k, val in (best or {}).items() if k != "_scale"}
        if cand:
            nm = max(cand.items(),
                     key=lambda kv: (scale.get(kv[0], 0), kv[1], kv[0]))[0]
            c["feat"].src_name = nm
            c["src_hits"] = cand[nm]
            c["src_scale"] = scale.get(nm, 0)
            c["src_candidates"] = len(cand)
        else:
            c["src_hits"] = c["src_scale"] = c["src_candidates"] = 0

    # 子集清单落盘（**不写 pan-corpus**）；与既有 SUBSET-PAN.json 对表＝抽样同一性的机械证据
    subset = {"seed": SEED, "pool_sizes": pool_sizes, "n_cases": len(cases),
              "cases": []}
    for c in cases:
        if c["kind"] == "annotated":
            f = c["feat"]
            subset["cases"].append({
                "case_id": c["case_id"], "tier": c["tier"],
                "suspicious_document": f.susp_name,
                "source_document": f.src_name,
                "source_resolution_hits": c.get("src_hits", 0),
                "source_resolution_candidates": c.get("src_candidates", 0),
                "obfuscation": f.obfuscation, "type": f.kind,
                "manual_obfuscation": f.manual_obfuscation,
                "this_offset": f.this_off, "this_length": f.this_len})
        else:
            subset["cases"].append({
                "case_id": c["case_id"], "tier": c["tier"],
                "suspicious_document": c["susp_name"],
                "source_document": c["nominal"],
                "note": "clean pair: no-plagiarism suspicious doc x random non-source doc"})
    SUBSET_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUBSET_JSON.write_text(json.dumps(subset, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    same = None
    orig = Path("/Users/moc/workspaces/SiAgent/pan-corpus/SUBSET-PAN.json")
    if orig.exists():
        same = (json.loads(orig.read_text(encoding="utf-8"))["cases"]
                == subset["cases"])
    print("subset manifest -> %s （与 v1 的 SUBSET-PAN.json 逐例一致：%s）"
          % (SUBSET_JSON, same))

    src_path_by_name = {p.name: p for d in src_dirs for p in d.glob("*.txt")}
    readings = []
    for c in cases:
        # 注意：**rng 抽取的顺序必须与 v1 完全一致**（none→random→manual→clean），
        # 否则干扰源会换一批，前后对照表就不是同一批用例了。
        # 因此这里对所有档都照 v1 抽干扰源，只是「跑不跑工具」按 tiers 过滤。
        if c["kind"] == "annotated":
            f = c["feat"]
            susp_path = None
            for d in susp_dirs:
                p = d / f.susp_name
                if p.exists():
                    susp_path = p
                    break
            if f.src_name and f.src_name in src_path_by_name:
                true_src = src_path_by_name[f.src_name]
                distract = [src_path_by_name[nm] for nm in rng.sample(
                    [x for x in src_names if x != f.src_name], N_DISTRACTORS)]
                b_files = [true_src] + distract
            else:
                pool = [x for x in src_names if x != ""]
                distract = [src_path_by_name[nm] for nm in rng.sample(pool,
                                                                     N_DISTRACTORS + 1)]
                b_files = distract[:N_DISTRACTORS + 1]
        else:
            susp_path = None
            for d in susp_dirs:
                p = d / c["susp_name"]
                if p.exists():
                    susp_path = p
                    break
            nominal = src_path_by_name[c["nominal"]]
            distract = [src_path_by_name[nm] for nm in rng.sample(
                [x for x in src_names if x != c["nominal"]], N_DISTRACTORS)]
            b_files = [nominal] + distract
            f = None
        primary_name = b_files[0].name
        dist_names = [b.name for b in b_files[1:]]
        if c["tier"] not in tiers:
            continue
        cid = c["case_id"]
        row = read_case(cid, susp_path, b_files, primary_name, dist_names,
                        f, c["tier"])
        row["source_resolved"] = bool(f is not None and f.src_name)
        row["source_resolution_scale_words"] = c.get("src_scale", 0) if f else None
        readings.append(row)
        print("[%s] %-12s cov=%-6s primary=%-5s false=%-5s segs=%d %s"
              % (c["tier"], cid,
                 "-" if row["char_coverage"] is None else "%.3f" % row["char_coverage"],
                 row["true_source_reported"], row["distractor_reported"],
                 row["segments_total"], row["segments_by_source"]), flush=True)

    summary = summarize(readings)
    verdicts = judge(summary)
    out = {
        "schema_version": "1.0",
        "corpus": "PAN-PC-11 (Zenodo record 3250095, CC BY 4.0)",
        "seed": SEED, "criteria_ref": "P-157 (frozen)",
        "tool": "factscribe textreuse v2 (default: multi-scale n=8/5 + "
                "sentence-containment 0.7)",
        "tiers_run": tiers,
        "subset_matches_v1": same,
        "pool_sizes": pool_sizes,
        "n_sources": len(src_names),
        "source_resolution": {
            "annotated_cases": len([c for c in cases if c["kind"] == "annotated"]),
            "resolved": len([r for r in readings
                             if r.get("source_resolved")]),
        },
        "summary": summary, "verdicts": verdicts, "readings": readings,
    }
    prev = {}
    if V1_JSON.exists():
        v1data = json.loads(V1_JSON.read_text(encoding="utf-8"))
        prev = {r["case_id"]: r for r in v1data.get("readings", [])}
    before_after = []
    for r in readings:
        old = prev.get(r["case_id"])
        if not old:
            continue
        before_after.append({
            "case_id": r["case_id"], "tier": r["tier"],
            "v1_coverage": old.get("char_coverage"),
            "v2_coverage": r.get("char_coverage"),
            "v1_primary": old.get("true_source_reported"),
            "v2_primary": r.get("true_source_reported"),
            "v1_false": old.get("distractor_reported"),
            "v2_false": r.get("distractor_reported"),
            "v1_segments": old.get("segments_total"),
            "v2_segments": r.get("segments_total"),
            "v2_by_source": r.get("segments_by_source"),
        })
    out["before_after"] = before_after
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print("\nwrote %s" % OUT_JSON)
    print(json.dumps({"summary": summary, "verdicts": verdicts},
                     ensure_ascii=False, indent=2))
    if is_eval:
        RECEIPT.write_text(json.dumps({
            "note": "P-157 eval 档（none+clean）已跑过——评测集只许跑一次，"
                    "读数不得回头调参。",
            "tiers_run": tiers, "n_cases": len(readings),
            "verdicts": verdicts}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print("eval receipt -> %s" % RECEIPT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
