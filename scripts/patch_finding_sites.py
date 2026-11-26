#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/patch_finding_sites.py —— 给发现构造点补 message_key / params。

真闸的每条发现都要能被 i18n 渲染，就要带上两样东西：

* `message_key`  —— 目录里的 key（同一 code 的多种文案形态才显式写；
  单一形态的 code 由 code 推出 key，不写也不歧义）；
* `params`       —— 模板槽位的取值（与原 %-格式化的实参一一对应，
  取值先按原格式格式化过，所以渲染结果与原 message 逐字一致）。

本脚本**只加关键字参数**，不改原 message 表达式——所以中文 message、
CLI/JSON 输出、既有测试断言一字不动。

用法：
    python3 scripts/patch_finding_sites.py --scaffold /tmp/scaffold.json
    python3 scripts/patch_finding_sites.py --scaffold ... --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def kwargs_text(site):
    """这一处要补的关键字参数文本。"""
    parts = []
    key = site.get("key", "")
    code = site["code"]
    if key and key != "finding." + code:
        parts.append("message_key=%s" % json.dumps(key, ensure_ascii=False))
    if site.get("slots"):
        parts.append("params=%s" % site["params_src"])
    return ", ".join(parts)


def offsets(text):
    """行首绝对偏移表（用来把 (行, 列) 换算成绝对下标）。"""
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scaffold", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sites = json.loads(Path(args.scaffold).read_text(encoding="utf-8"))
    by_file = {}
    for site in sites:
        if site.get("manual"):
            continue
        if site.get("has_params") or site.get("explicit_expr"):
            continue            # 已经手改过，别再补一遍
        kwargs = kwargs_text(site)
        if not kwargs:
            continue
        by_file.setdefault(site["file"], []).append((site, kwargs))

    touched = 0
    for rel, items in sorted(by_file.items()):
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        starts = offsets(text)
        edits = []
        for site, kwargs in items:
            end = site["end_line"]
            col = site["end_col"]
            if end is None or col is None:
                continue
            # AST 的 col_offset 是**字节**偏移；源文件里有中文，
            # 字节下标不等于字符下标——先把这一行的字节前缀解码成字符数。
            line_start = starts[end - 1]
            line_end = starts[end] if end < len(starts) else len(text)
            line_text = text[line_start:line_end]
            head = line_text.encode("utf-8")[:col].decode("utf-8", "ignore")
            pos = line_start + len(head)
            if pos <= 0 or text[pos - 1] != ")":
                print("  ! %s:%d 不是以 ) 结尾——跳过" % (rel, site["line"]))
                continue
            insert_at = pos - 1
            j = insert_at - 1
            while j >= 0 and text[j] in " \t\n":
                j -= 1
            if j >= 0 and text[j] == ",":
                payload = kwargs + ","
            else:
                payload = ", " + kwargs
            edits.append((insert_at, payload))
        for insert_at, payload in sorted(edits, reverse=True):
            text = text[:insert_at] + payload + text[insert_at:]
        if not args.dry_run and edits:
            path.write_text(text, encoding="utf-8")
        touched += len(edits)
        print("  %s: %d 处" % (rel, len(edits)))
    print("合计补了 %d 处" % touched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
