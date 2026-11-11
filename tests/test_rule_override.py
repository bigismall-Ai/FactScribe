# -*- coding: utf-8 -*-
"""批 130：规则文件不得成为绕过面（先写测试，后实现）。

实测缺陷：被测项目在根目录新建 ``style-rules.toml``，写

```toml
numeral_density_stage = "off"
```

就把 ``NUMERAL_DENSITY`` 判据降级成 ``info``，检查消失。模型没改正文，
只改了「考卷的判据开关」——照旧文档做的，结果绕过了检查。

本批两条改法：

1. **阶段开关只能在被测物之外**：``numeral_density_stage`` 不再从项目内
   ``style-rules.toml`` 读取；写了也不认，输出一条 ``RULES_OVERRIDE_IGNORED``
   告警。阶段改由命令行 ``style --stage draft|revision`` 控制（默认 draft）。
   其它配置键（词表、阈值）保持可覆盖。
2. **规则被改要看得见**：``style`` / ``review`` / ``audit`` 读到项目内
   ``style-rules.toml`` 时逐键与内置默认比较，输出「本项目覆盖了 N 个规则键」
   并列出键名（informational，不进 findings）。

规范：``docs/design/SPEC-READABILITY.md`` §1.4，
实施记录：``docs/implementation/READABILITY.md`` §3。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOML = """[project]
title = "rule-override"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""

# 约 100 个英文词 + 5 个数字 = 约 49/千词（显式阈值 40，触发）。
# 批 131：NUMERAL_DENSITY 默认阈值改 null（不判）；保留实现与配置，
# 旧行为的测试都显式给阈值 40。
# 句长故意拉开，避免 SENTENCE_UNIFORMITY 等无关判据一起触发。
DENSE = "\\section{Measurement}\n\n" + (
    "Results shifted. "
    "The first run matched 12 entries, while the second run matched 9 "
    "entries after cleanup. "
    "We kept the ledger open. "
    "A short note about the third pass records 7 missing receipts and one "
    "stale hash, because the reviewer asked for the full trace. "
    "Then the gate closed. "
    "The final table lists 5 warm rows and 3 cold rows, with the source path "
    "beside each row so the reader can check it. "
    "Nothing else moved. "
    "On the next morning the reviewer opened the receipt, compared the hash, "
    "and signed the note without any further comment about the run. "
    "The curve stayed flat. We stopped there.\n")

NUMERAL_RULES = "[thresholds]\nnumeral_density = 40\n"
OFF_RULES = 'numeral_density_stage = "off"\n' + NUMERAL_RULES
LOOSE_RULES = "[thresholds]\nnumeral_density = 100\n"
DASH_RULES = "[thresholds]\ndash_budget = 5\n"


def run_cli(cwd, *args):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        cwd=str(cwd), capture_output=True, text=True, env=env)


def make_project(root: Path, rules: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "paperkit.toml").write_text(TOML, encoding="utf-8")
    (root / "sections" / "01.tex").write_text(DENSE, encoding="utf-8")
    if rules is not None:
        (root / "style-rules.toml").write_text(rules, encoding="utf-8")
    return root


def style_json(root: Path, *extra: str):
    proc = run_cli(root, "style", str(root), "--json", *extra)
    data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return proc, data


def warning_codes(data: dict) -> set:
    return {w.get("code") for w in data.get("rule_warnings", [])}


def finding_codes(data: dict) -> set:
    return {f["code"] for f in data.get("findings", [])}


class RuleOverrideCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="rule-override-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    # ------------------------------------------------------------ 1. 项目内 off 失效
    def test_project_off_is_ignored_and_criterion_still_fires(self):
        root = make_project(self.tmp / "p", OFF_RULES)
        proc, data = style_json(root)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("NUMERAL_DENSITY", finding_codes(data))
        self.assertEqual(data["metric_details"]["numeral_density_stage"],
                         "draft")
        self.assertGreater(data["metrics"]["numeral_density"], 40)

    def test_project_off_reports_rules_override_ignored_warning(self):
        root = make_project(self.tmp / "p", OFF_RULES)
        proc, data = style_json(root)
        self.assertIn("RULES_OVERRIDE_IGNORED", warning_codes(data))
        ignored = {w["code"]: w for w in data["rule_warnings"]}
        self.assertIn("numeral_density_stage",
                      ignored["RULES_OVERRIDE_IGNORED"]["ignored"])

    def test_human_output_names_the_ignored_warning(self):
        root = make_project(self.tmp / "p", OFF_RULES)
        proc = run_cli(root, "style", str(root))
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("RULES_OVERRIDE_IGNORED", proc.stdout)
        self.assertIn("numeral_density_stage", proc.stdout)

    # ------------------------------------------------------------ 2. 命令行阶段开关
    def test_stage_revision_downgrades_to_info(self):
        root = make_project(self.tmp / "p", OFF_RULES)
        proc, data = style_json(root, "--stage", "revision")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("NUMERAL_DENSITY", finding_codes(data))
        info = [f for f in data.get("info", [])
                if f["code"] == "NUMERAL_DENSITY"]
        self.assertEqual(len(info), 1)
        self.assertEqual(info[0]["severity"], "info")
        self.assertIn("PROTECT_NUMBER_CHANGED", info[0]["suggestion"])
        self.assertEqual(data["metric_details"]["numeral_density_stage"],
                         "revision")

    def test_stage_draft_is_explicit_default(self):
        root = make_project(self.tmp / "p", OFF_RULES)
        proc, data = style_json(root, "--stage", "draft")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("NUMERAL_DENSITY", finding_codes(data))

    def test_stage_revision_does_not_change_metrics(self):
        root = make_project(self.tmp / "p")
        _, draft = style_json(root)
        _, revision = style_json(root, "--stage", "revision")
        self.assertEqual(draft["metrics"]["numeral_density"],
                         revision["metrics"]["numeral_density"])
        self.assertLessEqual(revision["exit"], draft["exit"])

    # ------------------------------------------------------------ 3. 其它键仍可覆盖
    def test_threshold_override_still_applies(self):
        root = make_project(self.tmp / "p", LOOSE_RULES)
        proc, data = style_json(root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("NUMERAL_DENSITY", finding_codes(data))
        self.assertEqual(data["thresholds"]["numeral_density"], 100)

    def test_override_list_names_threshold_key(self):
        root = make_project(self.tmp / "p", LOOSE_RULES)
        _, data = style_json(root)
        report = data["rule_overrides"]
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["keys"], ["thresholds.numeral_density"])

    def test_override_line_appears_in_style_human_output(self):
        root = make_project(self.tmp / "p", LOOSE_RULES)
        proc = run_cli(root, "style", str(root))
        self.assertIn("本项目覆盖了 1 个规则键", proc.stdout)
        self.assertIn("thresholds.numeral_density", proc.stdout)

    # ------------------------------------------------------------ 4. review 看得见
    def test_review_output_carries_override_line(self):
        before = make_project(self.tmp / "before")
        after = make_project(self.tmp / "after", DASH_RULES)
        proc = run_cli(ROOT, "review", "--before", str(before),
                       "--after", str(after))
        self.assertIn("本项目覆盖了 1 个规则键", proc.stdout)
        self.assertIn("thresholds.dash_budget", proc.stdout)

    def test_review_json_carries_override_report(self):
        before = make_project(self.tmp / "before")
        after = make_project(self.tmp / "after", DASH_RULES)
        proc = run_cli(ROOT, "review", "--before", str(before),
                       "--after", str(after), "--json")
        data = json.loads(proc.stdout)
        report = data["style"]["rule_overrides"]
        self.assertEqual(report["count"], 1)
        self.assertIn("thresholds.dash_budget", report["keys"])

    # ------------------------------------------------------------ 5. 无规则文件行为不变
    def test_no_rules_file_has_no_override_line_and_same_behavior(self):
        # 批 131：NUMERAL_DENSITY 默认 null（不判）；没规则文件时同样不报。
        root = make_project(self.tmp / "p")
        proc, data = style_json(root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("NUMERAL_DENSITY", finding_codes(data))
        self.assertEqual(data["rule_overrides"]["count"], 0)
        self.assertFalse(data["rule_overrides"]["present"])
        self.assertEqual(data["rule_warnings"], [])
        human = run_cli(root, "style", str(root))
        self.assertNotIn("本项目覆盖了", human.stdout)

    # ------------------------------------------------------------ 6. audit 也看得见
    def test_audit_reports_project_override(self):
        root = self.tmp / "example"
        shutil.copytree(ROOT / "examples" / "minimal", root)
        (root / "style-rules.toml").write_text(DASH_RULES, encoding="utf-8")
        proc = run_cli(ROOT, "audit", str(root), "--json")
        data = json.loads(proc.stdout)
        report = data["rule_overrides"]
        self.assertEqual(report["count"], 1)
        self.assertIn("thresholds.dash_budget", report["keys"])
        human = run_cli(ROOT, "audit", str(root))
        self.assertIn("本项目覆盖了 1 个规则键", human.stdout)


if __name__ == "__main__":
    unittest.main()
