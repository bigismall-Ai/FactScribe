#!/usr/bin/env python3
"""方法论产物 → 事实账草稿（批处理）。

把一份 TSV 里的主张批量变成 `facts/` 条目。它**不签字**：签清单仍然要人做。

用法：
    python3 draft-facts.py <项目目录> <claims.tsv> [--dry-run]

TSV 表头（制表符分隔，缺列可留空；以 # 开头的行忽略）：
    id	claim	value	source	locator	confidence	expr	derived_from

退出码：0 全部写入；1 任一行失败（先整体校验，校验不过一条都不写）；2 用法错。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
import sys
from pathlib import Path

COLUMNS = ["id", "claim", "value", "source", "locator", "confidence", "expr", "derived_from"]
ROOT = Path(__file__).resolve().parents[2]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(
            (line for line in f if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        if reader.fieldnames is None:
            raise SystemExit("claims 文件是空的")
        missing = [c for c in ("id", "claim", "value", "source") if c not in reader.fieldnames]
        if missing:
            raise SystemExit("claims 文件缺列：%s" % ", ".join(missing))
        for raw in reader:
            rows.append({k: (raw.get(k) or "").strip() for k in COLUMNS})
    return rows


def validate(project: Path, rows: list[dict]) -> list[str]:
    problems = []
    seen = set()
    for n, row in enumerate(rows, start=2):  # 2 = 第一条数据行（表头占 1）
        if not row["id"]:
            problems.append("第 %d 行：缺 id" % n)
        elif row["id"] in seen:
            problems.append("第 %d 行：id %s 在本文件里重复" % (n, row["id"]))
        seen.add(row["id"])
        if not row["claim"]:
            problems.append("第 %d 行：缺 claim" % n)
        if not row["value"]:
            problems.append("第 %d 行：缺 value" % n)
        src = project / row["source"] if row["source"] else None
        if not row["source"]:
            problems.append("第 %d 行：缺 source" % n)
        elif src is None or not src.is_file():
            problems.append("第 %d 行：source 不存在 %s" % (n, row["source"]))
        if row["derived_from"] and not row["expr"]:
            problems.append("第 %d 行：有 derived_from 但没有 expr" % n)
        if row["expr"] and not row["derived_from"]:
            problems.append("第 %d 行：有 expr 但没有 derived_from" % n)
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", type=Path)
    ap.add_argument("claims", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="只打印将要执行的命令")
    args = ap.parse_args()

    project = args.project.resolve()
    if not (project / "paperkit.toml").is_file():
        print("不是 factscribe 项目（缺 paperkit.toml）：%s" % project, file=sys.stderr)
        return 2

    rows = read_rows(args.claims)
    if not rows:
        print("claims 文件里没有数据行", file=sys.stderr)
        return 2

    problems = validate(project, rows)
    if problems:
        print("校验没过，一条都不写：", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 1

    manifest_lines = []
    for row in rows:
        cmd = [
            sys.executable, "-m", "factscribe", "fact", "add", str(project),
            "--id", row["id"], "--claim", row["claim"], "--value", row["value"],
            "--source", row["source"],
        ]
        if row["locator"]:
            cmd += ["--locator", row["locator"]]
        if row["confidence"]:
            cmd += ["--confidence", row["confidence"]]
        if row["expr"]:
            cmd += ["--expr", row["expr"]]
        if row["derived_from"]:
            cmd += ["--derived-from", row["derived_from"]]

        if args.dry_run:
            print("DRY " + " ".join(cmd[3:]))
            continue

        env = {"PYTHONPATH": str(ROOT)}
        proc = subprocess.run(cmd, capture_output=True, text=True, env={**env})
        if proc.returncode != 0:
            print("写入 %s 失败：\n%s%s" % (row["id"], proc.stdout, proc.stderr), file=sys.stderr)
            return 1
        for line in proc.stdout.splitlines():
            if "MANIFEST.toml" in line or '"results/' in line:
                manifest_lines.append(line.strip())

    if args.dry_run:
        return 0

    print("已写入 %d 条事实。" % len(rows))
    manifest_lines = list(dict.fromkeys(manifest_lines))  # 同一来源只列一次
    if manifest_lines:
        print("\n别忘了把人签清单补上（工具不代签）：")
        for line in manifest_lines:
            print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
