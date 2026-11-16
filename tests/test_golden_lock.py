# -*- coding: utf-8 -*-
r"""核验槽行为锁（SPEC-CHECKS §7 M1）：金样例逐字节比对（常驻）。

金样例 tests/golden/audit_findings_baseline.json 由
scripts/audit_golden_dump.py 在重构前冻结（26 个项目：examples/minimal ＋
fixtures/ benign 12＋hostile 12＋regression/paper-en）。本测试在每次改动后
重跑同命令（`python -m factscribe audit <project> --json`），逐项目比对：

- 退出码同值；
- findings/issues/warnings/hints 四数组规范化序列化后逐字节相同。

改判据先过这把锁；锁红了要么是回归（改代码），要么是有意的行为变更
（那要走修约程序并重新冻结金样例，不许静默改金样例）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GOLDEN = ROOT / "tests" / "golden" / "audit_findings_baseline.json"
FINDING_KEYS = ("findings", "issues", "warnings", "hints")


def run_audit_json(rel: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "factscribe", "audit", rel, "--json"],
        cwd=str(ROOT), env=env, capture_output=True, text=True)


def canonical(items) -> str:
    return json.dumps(items, ensure_ascii=False, sort_keys=True)


class GoldenLock(unittest.TestCase):
    """行为锁：重构前后同命令同项目 findings＋退出码逐字节相同。"""

    def test_baseline_exists_and_is_frozen_shape(self):
        self.assertTrue(GOLDEN.is_file(),
                        "金样例缺失——先跑 scripts/audit_golden_dump.py")
        data = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "factscribe-audit-golden/1.0")
        self.assertGreaterEqual(len(data["projects"]), 26,
                                "金样例项目数缩水——不许静默删项目")

    def test_findings_and_exit_byte_identical_per_project(self):
        baseline = json.loads(GOLDEN.read_text(encoding="utf-8"))
        projects = baseline["projects"]
        for rel in sorted(projects):
            expected = projects[rel]
            with self.subTest(project=rel):
                proc = run_audit_json(rel)
                self.assertEqual(
                    proc.returncode, expected["exit"],
                    "%s 退出码漂移：%d ≠ 基线 %d"
                    % (rel, proc.returncode, expected["exit"]))
                payload = json.loads(proc.stdout)
                for key in FINDING_KEYS:
                    self.assertEqual(
                        canonical(payload[key]), canonical(expected[key]),
                        "%s 的 %s 漂移（逐字节锁红）" % (rel, key))


if __name__ == "__main__":
    unittest.main()
