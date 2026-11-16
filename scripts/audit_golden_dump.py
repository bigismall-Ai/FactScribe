#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核验槽行为锁（SPEC-CHECKS §7 M1）：跑 audit --json、固化发现清单金样例。

用法（仓根）：

    python3 scripts/audit_golden_dump.py            # 重新生成金样例
    python3 scripts/audit_golden_dump.py --check    # 只比对不写盘（CI/手工）

覆盖项目：examples/minimal ＋ fixtures/ 全部项目（benign 12、hostile 12、
regression/paper-en）。trust/ 只是密钥材料，不是项目，不在列。

金样例文件：tests/golden/audit_findings_baseline.json，逐项目存——

    exit                     退出码（重构前后必须同值）
    findings/issues/warnings/hints   信封四个数组，逐条逐字节

生成纪律：重构前冻结一次；重构后跑 --check 必须逐字节相同才算过锁。
退出码、码表、报告信封三样同锁。权威脚本只有本件；金样例只由本件写。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "audit_findings_baseline.json"

# 信封里与「发现清单」同锁的四个数组（summary/attestation 不入锁：它随
# 账本内容漂移，且已由 spec 的 facts_sha256 单独钉住）。
FINDING_KEYS = ("findings", "issues", "warnings", "hints")

# 固定项目清单：显式列举，不动态 glob——夹具增删必须过人审才能进锁。
PROJECTS = ["examples/minimal"]
PROJECTS += sorted("fixtures/benign/" + p.name for p in
                   (ROOT / "fixtures" / "benign").iterdir() if p.is_dir())
PROJECTS += sorted("fixtures/hostile/" + p.name for p in
                   (ROOT / "fixtures" / "hostile").iterdir() if p.is_dir())
PROJECTS += ["fixtures/regression/paper-en"]


def run_audit(rel: str) -> dict:
    """跑一次 `python -m factscribe audit <rel> --json`，抽锁面字段。"""
    proc = subprocess.run(
        [sys.executable, "-m", "factscribe", "audit", rel, "--json"],
        cwd=str(ROOT), capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit("audit %s 的 --json 输出解析失败：%s\n%s"
                         % (rel, exc, proc.stderr[-2000:]))
    out = {"exit": proc.returncode}
    for key in FINDING_KEYS:
        out[key] = payload[key]
    return out


def collect() -> dict:
    projects = {}
    for rel in PROJECTS:
        projects[rel] = run_audit(rel)
    return {
        "schema": "factscribe-audit-golden/1.0",
        "command": "python3 -m factscribe audit <project> --json",
        "note": ("核验槽 M1 行为锁（SPEC-CHECKS §7 M1）：重构前后同命令同项目 "
                 "findings 与退出码逐字节相同才算过锁。只由 "
                 "scripts/audit_golden_dump.py 生成。"
                 "重冻记录：2026-11-16 用户批准核验槽修约九条建议，裁定③使"
                 "裸 [checks] 节走槽（默认 [\"paper\"]，输出带 domain 键与 "
                 "by_domain）——基线重冻；26 个在锁项目均无 [checks] 节，"
                 "重冻后各项目发现本体与退出码逐条相同。"
                 "重冻记录：2026-11-17 CI 矩阵 3.11+ 独红——基线冻在 3.10 兜底"
                 "解析器 _mini_toml 的误解析形（不支持内联表、数组切分不顾花"
                 "括号，R2-ROUNDTO 的 display 被按逗号劈成两条裸串）；修 _mini_toml"
                 "（补内联表解析＋深度感知切分）后重冻，R2-ROUNDTO 的 2 条误解析"
                 "发现并成 1 条正确 DISPLAY_INCONSISTENT（退出码仍 1），26 个在锁"
                 "项目与退出码在 Python 3.10–3.14 全矩阵逐字节相同。"),
        "projects": projects,
    }


def canonical(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    data = collect()
    text = canonical(data)
    if check_only:
        if not GOLDEN.is_file():
            print("golden_check: 金样例不存在（先跑不带 --check 的本脚本）：%s"
                  % GOLDEN)
            return 2
        current = GOLDEN.read_text(encoding="utf-8")
        if current == text:
            print("golden_check: 逐字节相同，%d 个项目全过锁" % len(PROJECTS))
            return 0
        # 逐项目报差异，方便人看是哪一项目漂了
        old = json.loads(current)
        bad = 0
        for rel in PROJECTS:
            if canonical(old["projects"].get(rel, {})) != canonical(
                    data["projects"][rel]):
                print("golden_check: DIFF %s" % rel)
                bad += 1
        print("golden_check: %d/%d 个项目漂移" % (bad, len(PROJECTS)))
        return 1
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(text, encoding="utf-8")
    total = sum(len(p["findings"]) + len(p["hints"])
                for p in data["projects"].values())
    print("golden_dump: 冻结 %d 个项目、%d 条发现＋提示 → %s"
          % (len(PROJECTS), total, GOLDEN.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
