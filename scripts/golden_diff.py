#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare two golden trees, normalizing absolute paths and timestamps.

Usage:
    python3 scripts/golden_diff.py /tmp/golden-before /tmp/golden-after

Exit 0 = all files identical after normalization; 1 = differences;
2 = usage / missing directory. JSON payloads are compared as raw text (after
normalization), so field order and byte layout still matter.
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

_PATH_RE = re.compile(r"/[^\s\"']*(?:/workspaces/|/private/|/tmp/)[^\s\"']*")
_TIME_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b")
_EPOCH_RE = re.compile(r'"(?:mtime|timestamp|generated_at)"\s*:\s*\d+(?:\.\d+)?')


def normalize(text: str) -> str:
    text = _PATH_RE.sub("<PATH>", text)
    text = _TIME_RE.sub("<TIME>", text)
    text = _EPOCH_RE.sub('"<FIELD>":"<TIME>"', text)
    return text


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    before, after = Path(argv[1]), Path(argv[2])
    if not before.is_dir() or not after.is_dir():
        print("golden_diff: both arguments must be directories", file=sys.stderr)
        return 2

    names_before = {p.relative_to(before).as_posix() for p in before.rglob("*") if p.is_file()}
    names_after = {p.relative_to(after).as_posix() for p in after.rglob("*") if p.is_file()}
    all_names = sorted(names_before | names_after)

    same = 0
    diffs = 0
    for name in all_names:
        a = before / name
        b = after / name
        if not a.is_file() or not b.is_file():
            side = "missing in after" if a.is_file() else "missing in before"
            print("DIFF %s (%s)" % (name, side))
            diffs += 1
            continue
        left = normalize(a.read_text(encoding="utf-8", errors="replace"))
        right = normalize(b.read_text(encoding="utf-8", errors="replace"))
        if left == right:
            same += 1
            continue
        diffs += 1
        print("DIFF %s" % name)
        for line in list(difflib.unified_diff(
                left.splitlines(), right.splitlines(),
                fromfile="before/" + name, tofile="after/" + name, lineterm=""))[:40]:
            print(line)

    print("golden_diff: %d identical, %d different, %d files" % (same, diffs, len(all_names)))
    return 0 if diffs == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
