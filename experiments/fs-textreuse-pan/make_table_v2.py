#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 READINGS-PAN-V2.json 压成报告要的前后对照表（纯标准库）。"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
d = json.loads((HERE / "READINGS-PAN-V2.json").read_text(encoding="utf-8"))
ba = d.get("before_after", [])
rows = sorted(ba, key=lambda r: r["case_id"])
print("| 例 id | 档 | v1 覆盖 | v2 覆盖 | v1 真源被报 | v2 真源被报 | v1 干扰误配 | v2 干扰误配 | v1 段数 | v2 段数（来源） |")
print("|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    src = r.get("v2_by_source") or {}
    print("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
          % (r["case_id"], r["tier"],
             "—" if r["v1_coverage"] is None else "%.3f" % r["v1_coverage"],
             "—" if r["v2_coverage"] is None else "%.3f" % r["v2_coverage"],
             "是" if r["v1_primary"] else "否",
             "是" if r["v2_primary"] else "否",
             "是" if r["v1_false"] else "否",
             "是" if r["v2_false"] else "否",
             r["v1_segments"], r["v2_segments"], src or "—"))
print()
print("== 逐档汇总（v2） ==")
for tier, s in d.get("summary", {}).items():
    print(tier, json.dumps(s, ensure_ascii=False))
print("== 判据 ==")
print(json.dumps(d.get("verdicts", {}), ensure_ascii=False, indent=2))
