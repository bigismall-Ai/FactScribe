#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PAN-PC-11 考卷：factscribe textreuse 字面层读数采集（纯标准库）。

工单：/tmp/fs-gcards-wo/WORKORDER-PAN.md（判据 P-157 已冻结，本脚本不参与判据计算）。
语料：PAN Plagiarism Corpus 2011 (PAN-PC-11)，Zenodo record 3250095，CC BY 4.0。

**关键事实（实测）**：PAN-PC-11 发布的注释 XML **没有 `source_reference` 属性**
（11,443 条 plagiarism feature 全量核查，属性词表仅
name/type/this_offset/this_length/this_language/obfuscation/manual_obfuscation），
归档里也**没有 external-detection-corpus/suspicious-document/**（外部可疑文档子集缺失）。
→ 「真源文档」必须**从语料自身反推**：注释 span 是从某源文档复制来的，
把 span 文本回查源池即可定位真源文档（none 档逐字、translation 档局部逐字）。

流程：
  ① 解析注释 XML → 案例（可疑文档／obfuscation 档／抄袭 span 字符区间）
  ② 抽样（seed 20261118）：none 20 + random 20 + manual 20（同文档 ≤2 例）+ 干净对 10 对
  ③ 反推真源文档：空白折叠源池 + 词窗探针 + 一次 Aho-Corasick 扫描（grep -F -f）
  ④ 跑测：每例 /tmp/pan-run/<例id>/{A,B}/，B = 真源 + 4 份随机干扰源
        `factscribe textreuse A B --json`（默认 n=8，工具与 n 参数零改动）
  ⑤ 读数：①真源是否被报 ②字符覆盖（行区间 × 行长 折算字符区间）③干扰源是否被报（误配）

产出：experiments/fs-textreuse-pan/READINGS-PAN.json
     pan-corpus/SUBSET-PAN.json（抽样子集清单）
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import random
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SEED = 20261118
N_PER_TIER = 20
N_CLEAN_PAIRS = 10
N_DISTRACTORS = 4
FACTSCRIBE_ROOT = "/tmp/fs-gcards-wt"
RUN_ROOT = Path("/tmp/pan-run")
CORPUS = Path("/Users/moc/workspaces/SiAgent/pan-corpus/corpus/pan-plagiarism-corpus-2011")
OUT_JSON = Path("/tmp/fs-gcards-wt/experiments/fs-textreuse-pan/READINGS-PAN.json")
SUBSET_JSON = Path("/Users/moc/workspaces/SiAgent/pan-corpus/SUBSET-PAN.json")
WORK = Path("/tmp/pan-run/_work")

TIER_NONE, TIER_RANDOM, TIER_MANUAL = "none", "random", "manual"
TIERS = (TIER_NONE, TIER_RANDOM, TIER_MANUAL)

# 工单三档 ← 语料属性（实测词表，见 REPORT-PAN.md「映射口径」节）
#   none   ← obfuscation == "none"                     逐字照搬（人工/程序插入）
#   random ← type == "translation" 且 manual_obfuscation != "true"   程序自动改写（机器翻译）
#   manual ← type == "translation" 且 manual_obfuscation == "true"   众包人工改写（MTurk）
# 语料**没有** obfuscation=="random"、也没有 type=="manual"（已全量核查）。
def tier_of(obf, kind, man):
    if kind == "translation" and man == "true":
        return TIER_MANUAL
    if kind == "translation":
        return TIER_RANDOM
    if obf == "none":
        return TIER_NONE
    return ""


# ---------------------------------------------------------------------------
# 语料解析
# ---------------------------------------------------------------------------
class Feature:
    __slots__ = ("susp_name", "obfuscation", "kind", "manual_obfuscation",
                 "this_off", "this_len", "tier", "src_name")

    def __init__(self, susp_name, obfuscation, kind, manual_obfuscation,
                 this_off, this_len, tier):
        self.susp_name = susp_name
        self.obfuscation = obfuscation
        self.kind = kind
        self.manual_obfuscation = manual_obfuscation
        self.this_off = this_off
        self.this_len = this_len
        self.tier = tier
        self.src_name = ""

    @property
    def span(self):
        return (self.this_off, self.this_off + self.this_len)

    def as_dict(self):
        return {
            "suspicious_document": self.susp_name,
            "source_document": self.src_name,
            "obfuscation": self.obfuscation,
            "type": self.kind,
            "manual_obfuscation": self.manual_obfuscation,
            "tier": self.tier,
            "this_offset": self.this_off,
            "this_length": self.this_len,
        }


def list_suspicious():
    """全部可疑文档目录（分片 partN）。"""
    base = CORPUS / "intrinsic-detection-corpus" / "suspicious-document"
    return sorted([base] + [p for p in base.iterdir() if p.is_dir()])


def list_sources():
    base = CORPUS / "external-detection-corpus" / "source-document"
    return sorted([base] + [p for p in base.iterdir() if p.is_dir()])


def parse_features(susp_dirs):
    feats = []
    stats = {}
    seen = set()
    for d in susp_dirs:
        for xp in sorted(d.glob("*.xml")):
            if xp.name in seen:
                continue
            seen.add(xp.name)
            try:
                root = ET.parse(str(xp)).getroot()
            except ET.ParseError:
                continue
            for el in root.iter("feature"):
                if el.get("name") != "plagiarism":
                    continue
                obf, kind = el.get("obfuscation") or "", el.get("type") or ""
                man = el.get("manual_obfuscation") or ""
                try:
                    off = int(el.get("this_offset"))
                    ln = int(el.get("this_length"))
                except (TypeError, ValueError):
                    continue
                tier = tier_of(obf, kind, man)
                key = (obf, kind, man)
                stats[key] = stats.get(key, 0) + 1
                feats.append(Feature(xp.stem + ".txt", obf, kind, man, off, ln, tier))
    return feats, stats


def parse_negatives(susp_dirs):
    """无抄袭的可疑文档（无 plagiarism feature）。"""
    out = []
    for d in susp_dirs:
        for tp in sorted(d.glob("*.txt")):
            xp = tp.with_suffix(".xml")
            if not xp.exists():
                out.append(tp.name)
                continue
            try:
                root = ET.parse(str(xp)).getroot()
            except ET.ParseError:
                out.append(tp.name)
                continue
            if not any(el.get("name") == "plagiarism" for el in root.iter("feature")):
                out.append(tp.name)
    return out


# ---------------------------------------------------------------------------
# 抽样
# ---------------------------------------------------------------------------
def sample_tier(feats, n, rng):
    """同文档 ≤2 例：先一轮一文档一例（保证分散），再补第二轮。"""
    pool = list(feats)
    rng.shuffle(pool)
    by_doc = {}
    for f in pool:
        by_doc.setdefault(f.susp_name, []).append(f)
    docs = sorted(by_doc)
    rng.shuffle(docs)
    chosen = []
    for d in docs:
        if len(chosen) >= n:
            break
        chosen.append(by_doc[d][0])
    if len(chosen) < n:
        for d in docs:
            if len(chosen) >= n:
                break
            if len(by_doc[d]) > 1:
                chosen.append(by_doc[d][1])
    return chosen[:n]


# ---------------------------------------------------------------------------
# 真源反推：空白折叠源池 + 词窗探针 + 一次 grep -F -f（Aho-Corasick）扫描
# ---------------------------------------------------------------------------
WS = re.compile(r"\s+")


def build_normalized_sources(src_dirs):
    """把源池拼成空白折叠的单个文件（已存在则复用），并记每篇的起始偏移。"""
    WORK.mkdir(parents=True, exist_ok=True)
    norm_path = WORK / "sources.norm.bin"
    meta_path = WORK / "sources.norm.meta.json"
    if meta_path.exists():
        return norm_path, json.loads(meta_path.read_text(encoding="utf-8"))
    meta = []
    off = 0
    with norm_path.open("wb") as out:
        for d in src_dirs:
            for p in sorted(d.glob("*.txt")):
                txt = p.read_text(encoding="utf-8", errors="replace")
                b = WS.sub(" ", txt).strip().encode("utf-8")
                meta.append({"name": p.name, "off": off, "len": len(b)})
                out.write(b)
                out.write(b"\n")
                off += len(b) + 1
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    return norm_path, meta


def probes_for(span_text, scales=(30, 15, 8, 5), per_scale=600):
    """多尺度探针：从 span 取定长词窗（空白折叠）。

    PAN 的随机抄袭程序对插入段落做过**词级扰动**（插拉丁词等），所以只有
    短词窗能命中、且命中越少越可能是噪音。→ 用多个尺度同时探：能命中最长
    尺度的那篇源文档，就是真源（长尺度命中＝长逐字段＝高置信）。
    """
    words = WS.sub(" ", span_text).strip().split(" ")
    out = []
    for win in scales:
        if len(words) < win:
            continue
        step = 1
        i = 0
        got = 0
        while i + win <= len(words) and got < per_scale:
            w = " ".join(words[i:i + win])
            if len(w) >= 20:
                out.append((win, w))
                got += 1
            i += step
    return out


def resolve_sources(cases, src_meta, norm_path):
    """一次 grep 扫描定位所有案例的真源文档。"""
    probe_owner = {}
    probe_list = []
    for case in cases:
        feats = case.get("feat_list", [])
        for k, f in enumerate(feats):
            txt = read_susp(f.susp_name)
            span = txt[f.this_off:f.this_off + f.this_len]
            for win, p in probes_for(span):
                if len(p) < 20:
                    continue
                if p not in probe_owner:
                    probe_owner[p] = []
                    probe_list.append(p)
                probe_owner[p].append((case["case_id"], k, win))
    if not probe_list:
        return {}
    pf = WORK / "probes.txt"
    pf.write_text("\n".join(probe_list) + "\n", encoding="utf-8")
    print("probes: %d unique -> %s" % (len(probe_list), pf))
    proc = subprocess.run(["rg", "-F", "-b", "-o", "--no-filename",
                           "-f", str(pf), str(norm_path)], capture_output=True)
    if proc.returncode not in (0, 1):
        print("grep rc=%d stderr=%s" % (proc.returncode, proc.stderr[:300]))
    hits = {}     # case_id -> {docname: hit_count}
    names = [m["name"] for m in src_meta]
    starts = [m["off"] for m in src_meta]
    for line in proc.stdout.split(b"\n"):
        if not line:
            continue
        head, _, rest = line.partition(b":")
        try:
            off = int(head)
        except ValueError:
            continue
        probe = rest.decode("utf-8", "replace")
        i = bisect.bisect_right(starts, off) - 1
        if i < 0:
            continue
        nm = names[i]
        for cid, k, win in probe_owner.get(probe, []):
            hits.setdefault(cid, {})
            hits[cid][nm] = hits[cid].get(nm, 0) + 1
            hits[cid].setdefault("_scale", {})
            hits[cid]["_scale"][nm] = max(hits[cid]["_scale"].get(nm, 0), win)
    return hits


SUSP_CACHE = {}


def read_susp(name):
    if name not in SUSP_CACHE:
        for d in list_suspicious():
            p = d / name
            if p.exists():
                SUSP_CACHE[name] = p.read_text(encoding="utf-8", errors="replace")
                break
        else:
            SUSP_CACHE[name] = ""
    return SUSP_CACHE[name]


# ---------------------------------------------------------------------------
# 跑测
# ---------------------------------------------------------------------------
def run_case(case_id, susp_path, b_files):
    base = RUN_ROOT / case_id
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
           str(a_dir), str(b_dir), "--json"]
    proc = subprocess.run(cmd, cwd=FACTSCRIBE_ROOT, capture_output=True,
                          text=True, timeout=900)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "bad json", "stderr": proc.stderr[-1000:],
                "stdout": proc.stdout[-1000:], "exit": proc.returncode}
    payload["_exit"] = proc.returncode
    return payload


def line_offsets(text):
    offsets = [0]
    idx = 0
    for line in text.split("\n"):
        offsets.append(idx)
        idx += len(line) + 1
    return offsets


def line_range_to_chars(offsets, text_len, l1, l2):
    start = offsets[l1] if 1 <= l1 < len(offsets) else 0
    end = offsets[l2 + 1] if l2 + 1 < len(offsets) else text_len
    return (start, max(end, start))


def coverage_of(span, reported):
    a_s, a_e = span
    total = a_e - a_s
    if total <= 0:
        return 0.0
    covered = 0
    for s, e in reported:
        lo, hi = max(a_s, s), min(a_e, e)
        if hi > lo:
            covered += hi - lo
    return min(1.0, covered / total)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--inspect-only", action="store_true")
    args = ap.parse_args()

    susp_dirs = list_suspicious()
    src_dirs = list_sources()
    feats, stats = parse_features(susp_dirs)
    negatives = parse_negatives(susp_dirs)
    src_names = sorted(p.name for d in src_dirs for p in d.glob("*.txt"))
    print("suspicious dirs: %d | source dirs: %d" % (len(susp_dirs), len(src_dirs)))
    print("(obfuscation,type,manual_obfuscation) 分布: %s" % sorted(stats.items()))
    print("features=%d  negatives=%d  sources=%d"
          % (len(feats), len(negatives), len(src_names)))

    rng = random.Random(SEED)
    pools = {t: [f for f in feats if f.tier == t] for t in TIERS}
    picked = {t: sample_tier(pools[t], N_PER_TIER, rng) for t in TIERS}
    negs = list(negatives)
    rng.shuffle(negs)
    cleans = [(n, rng.choice(src_names)) for n in negs[:N_CLEAN_PAIRS]]
    pool_sizes = {t: len(pools[t]) for t in TIERS}
    print("tier pools: %s" % pool_sizes)
    for t in TIERS:
        docs = {f.susp_name for f in picked[t]}
        print("  [%s] %d 例 / %d 文档" % (t, len(picked[t]), len(docs)))

    # --- 真源反推 ---------------------------------------------------------
    norm_path, src_meta = build_normalized_sources(src_dirs)
    print("normalized source pool: %s (%d docs, %.1f MB)"
          % (norm_path, len(src_meta), norm_path.stat().st_size / 1e6))

    cases = []
    for t in TIERS:
        for i, f in enumerate(picked[t], 1):
            cases.append({"case_id": "%s-%03d" % (t, i), "tier": t,
                          "kind": "annotated", "feat": f, "feat_list": [f]})
    for i, (nm, nominal) in enumerate(cleans, 1):
        cases.append({"case_id": "clean-%03d" % i, "tier": "clean",
                      "kind": "clean", "susp_name": nm, "nominal": nominal,
                      "feat": None, "feat_list": []})
    hits = resolve_sources(cases, src_meta, norm_path)
    print("source resolution: %d/%d cases resolved"
          % (len(hits), len([c for c in cases if c["kind"] == "annotated"])))

    src_path_by_name = {p.name: p for d in src_dirs for p in d.glob("*.txt")}
    for c in cases:
        if c["kind"] != "annotated":
            continue
        best = hits.get(c["case_id"])
        scale = best.get("_scale", {}) if best else {}
        cand = {k: v for k, v in (best or {}).items() if k != "_scale"}
        if cand:
            nm = max(cand.items(),
                     key=lambda kv: (scale.get(kv[0], 0), kv[1], kv[0]))[0]
            c["feat"].src_name = nm
            c["src_hits"] = cand[nm]
            c["src_scale"] = scale.get(nm, 0)
            c["src_candidates"] = len(cand)
        else:
            c["src_hits"] = 0
            c["src_scale"] = 0
            c["src_candidates"] = 0

    # --- 子集清单 ---------------------------------------------------------
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
    print("subset manifest -> %s" % SUBSET_JSON)

    if args.inspect_only:
        return 0

    # --- 跑测 -------------------------------------------------------------
    if args.limit:
        cases = cases[:args.limit]
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    readings = []
    for n, c in enumerate(cases, 1):
        cid = c["case_id"]
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
                resolved = True
            else:
                # 真源未反推成功：改用同档随机源占位，并如实标记
                pool = [x for x in src_names if x != ""]
                distract = [src_path_by_name[nm] for nm in rng.sample(pool, N_DISTRACTORS + 1)]
                b_files = distract[:N_DISTRACTORS + 1]
                resolved = False
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
            resolved = True
            f = None

        payload = run_case(cid, susp_path, b_files)
        segs = payload.get("segments") or []
        text = susp_path.read_text(encoding="utf-8", errors="replace")
        offsets = line_offsets(text)
        primary_name = b_files[0].name
        dist_names = [b.name for b in b_files[1:]] if c["kind"] == "annotated" \
            else [b.name for b in b_files[1:]]
        primary = [s for s in segs if s.get("b_file") == primary_name]
        false_segs = [s for s in segs if s.get("b_file") in dist_names]
        if f is not None:
            spans = [line_range_to_chars(offsets, len(text),
                                         s.get("a_line_start", 1),
                                         s.get("a_line_end", 1)) for s in primary]
            cov = coverage_of(f.span, spans)
        else:
            spans, cov = [], None
        readings.append({
            "case_id": cid, "tier": c["tier"], "kind": c["kind"],
            "suspicious_document": susp_path.name,
            "source_document": (f.src_name if f else c["nominal"]),
            "source_resolved": resolved,
            "source_resolution_hits": c.get("src_hits", 0) if f else None,
            "source_resolution_candidates": c.get("src_candidates", 0) if f else None,
            "source_resolution_scale_words": c.get("src_scale", 0) if f else None,
            "annotation": f.as_dict() if f else None,
            "annotation_char_span": list(f.span) if f else None,
            "reported_primary_char_spans": [list(s) for s in spans],
            "true_source_reported": bool(primary),
            "char_coverage": None if cov is None else round(cov, 6),
            "distractor_reported": bool(false_segs),
            "distractor_matches": sorted({s.get("b_file") for s in false_segs}),
            "n_false_pairs": len(false_segs),
            "segments_total": len(segs),
            "reported_pairs": [{"b_file": s.get("b_file"),
                                "a_line_start": s.get("a_line_start"),
                                "a_line_end": s.get("a_line_end"),
                                "overlap_tokens": s.get("overlap_tokens")}
                               for s in segs],
            "exit_code": payload.get("_exit"), "error": payload.get("error")})
        print("[%3d/%3d] %-12s cov=%-6s primary=%-5s false=%-5s segs=%d"
              % (n, len(cases), cid,
                 "-" if cov is None else "%.3f" % cov,
                 bool(primary), bool(false_segs), len(segs)), flush=True)

    summary = summarize(readings)
    out = {
        "schema_version": "1.0",
        "corpus": "PAN-PC-11 (Zenodo record 3250095, CC BY 4.0)",
        "seed": SEED, "criteria_ref": "P-157 (frozen)",
        "tool": "factscribe textreuse (default n=8, min_tokens=8, unmodified)",
        "corpus_dir": {"suspicious": [str(d) for d in susp_dirs],
                       "source": [str(d) for d in src_dirs]},
        "annotation_attr_distribution": {"%s|%s|%s" % k: v
                                         for k, v in sorted(stats.items())},
        "pool_sizes": pool_sizes,
        "n_negative_suspicious": len(negatives),
        "n_sources": len(src_names),
        "source_resolution": {
            "annotated_cases": len([c for c in cases if c["kind"] == "annotated"]),
            "resolved": len([r for r in readings
                             if r["kind"] == "annotated" and r["source_resolved"]]),
        },
        "summary": summary, "readings": readings,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print("\nwrote %s" % OUT_JSON)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def summarize(readings):
    out = {}
    for tier in list(TIERS) + ["clean"]:
        rows = [r for r in readings if r["tier"] == tier]
        if not rows:
            continue
        hit = [r for r in rows if r["true_source_reported"]]
        covs = [r["char_coverage"] for r in rows if r["char_coverage"] is not None]
        cov08 = [c for c in covs if c >= 0.8]
        item = {
            "n_cases": len(rows),
            "n_source_resolved": len([r for r in rows if r.get("source_resolved")]),
            "true_source_reported": len(hit),
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


if __name__ == "__main__":
    main()
