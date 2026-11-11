# -*- coding: utf-8 -*-
r"""批 128：篇幅预算 `[budget]` 与 `SECTION_LENGTH` 的契约测试（全离线）。

规范：`docs/design/SPEC-BUDGET.md`。

覆盖：

* 英文超预算 / 不超预算（含正好 120% 的边界）；
* 中文按汉字计数超 / 不超；
* 没有 `[budget]` 时判据不跑（向后兼容）；
* 按节覆盖（`[budget.sections]`）生效，且与 `default` 是同一份配置；
* 章节与附录分开算，预算互不借用；
* 注释、标题命令、公式、`\cite`、`\fact{ID}` 的 ID 不计入长度；
* 混排（英文词＋汉字）相加计数；
* `[budget]` 只写节、不写 `default` 时该节不判；
* 配置值非法即失败（退出码 2）；
* `--json` 的逐节读数与 `--json` 稳定形状；
* `brief` 的节清单带「篇幅预算」列，没有配置写 `—`。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.brief import (build_brief,  # noqa: E402
                              payload as brief_payload)
from factscribe.brief import render as render_brief  # noqa: E402
from factscribe.config import (ConfigError, load_config,  # noqa: E402
                               load_sections, section_budget)
from factscribe.style import analyze, load_style_rules  # noqa: E402

PROJECT_TOML = """[project]
title = "篇幅预算测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""

DEFAULT_BUDGET = 800


def en_words(count: int) -> str:
    """恰好 count 个英文词（每个词都是一个计数单元）。"""
    return " ".join(["word"] * count)


def zh_chars(count: int) -> str:
    """恰好 count 个汉字（不含标点，逐字计数）。"""
    return "".join(["汉"] * count)


def cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True)


def cli_json(*args: str) -> dict:
    proc = cli(*args, "--json")
    if proc.returncode not in (0, 3):
        raise AssertionError("退出码 %d：%s" % (proc.returncode, proc.stderr))
    return json.loads(proc.stdout)


def make_project(base: Path, sections: dict, budget: str | None = None) -> Path:
    """建一个最小 v1 项目：sections 字典是 {文件名: 正文}。"""
    root = Path(base)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    text = PROJECT_TOML
    if budget is not None:
        text += "\n" + budget.strip() + "\n"
    (root / "paperkit.toml").write_text(text, encoding="utf-8")
    (root / "facts" / "one.toml").write_text(
        '[[fact]]\nid = "B1"\nclaim = "一条主张"\nvalue = "53"\n',
        encoding="utf-8")
    for name, body in sections.items():
        (root / "sections" / name).write_text(body, encoding="utf-8")
    return root


def run_style(project: Path):
    cfg = load_config(project)
    sections = load_sections(cfg)
    rules, rules_path = load_style_rules(cfg.root)
    return cfg, analyze(cfg, sections, rules, rules_path=rules_path)


def section_findings(result) -> list:
    return [f for f in result.findings if f.code == "SECTION_LENGTH"]


def reading(result, file_suffix: str) -> dict:
    for item in result.metric_details["section_budget"]:
        if item["file"].endswith(file_suffix):
            return item
    raise AssertionError("读数里没有 %s：%r"
                        % (file_suffix, result.metric_details["section_budget"]))


def budget_block(default=None, sections=None) -> str:
    lines = ["[budget]"]
    if default is not None:
        lines.append("default = %d" % default)
    if sections:
        lines.append("")
        lines.append("[budget.sections]")
        for key, value in sections.items():
            lines.append('"%s" = %d' % (key, value))
    return "\n".join(lines)


class BudgetCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)


# --------------------------------------------------------------------------
# 1. 英文：超 / 不超 / 边界
# --------------------------------------------------------------------------

class TestEnglish(BudgetCase):
    def test_over_budget_fires_with_three_readings(self):
        project = make_project(self.tmp / "en-over",
                               {"01_intro.tex": en_words(1000)},
                               budget_block(DEFAULT_BUDGET))
        _cfg, result = run_style(project)
        hits = section_findings(result)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].severity, "yellow")
        self.assertIn("1000 词", hits[0].text)
        self.assertIn("预算 800 词", hits[0].text)
        self.assertIn("超出 25.0%", hits[0].text)
        self.assertEqual(result.metrics["section_length"], 25.0)
        self.assertIn("SECTION_LENGTH", {f["code"] for f in result.fired})
        # 处方顺序与三条禁做必须写在 message 里，改的人不用另找。
        for token in ("重复", "举例", "同义句", "论点", "证据"):
            with self.subTest(token=token):
                self.assertIn(token, hits[0].suggestion)

    def test_under_budget_does_not_fire(self):
        project = make_project(self.tmp / "en-under",
                               {"01_intro.tex": en_words(900)},
                               budget_block(DEFAULT_BUDGET))
        _cfg, result = run_style(project)
        self.assertEqual(section_findings(result), [])
        self.assertEqual(result.metrics["section_length"], 0.0)

    def test_exactly_twenty_percent_is_not_over(self):
        # 800 × 1.20 = 960：正好 120% 不算超；961 才超。
        at_limit = make_project(self.tmp / "en-edge-ok",
                                {"01_intro.tex": en_words(960)},
                                budget_block(DEFAULT_BUDGET))
        _cfg, result = run_style(at_limit)
        self.assertEqual(section_findings(result), [])
        self.assertEqual(reading(result, "01_intro.tex")["excess_percent"], 20.0)

        over = make_project(self.tmp / "en-edge-over",
                            {"01_intro.tex": en_words(961)},
                            budget_block(DEFAULT_BUDGET))
        _cfg, result = run_style(over)
        self.assertEqual(len(section_findings(result)), 1)
        self.assertEqual(result.metrics["section_length"], 20.1)


# --------------------------------------------------------------------------
# 2. 中文：按汉字计
# --------------------------------------------------------------------------

class TestChinese(BudgetCase):
    def test_over_budget_counts_cjk_chars(self):
        project = make_project(self.tmp / "zh-over",
                               {"01_intro.tex": zh_chars(1000)},
                               budget_block(DEFAULT_BUDGET))
        _cfg, result = run_style(project)
        hits = section_findings(result)
        self.assertEqual(len(hits), 1)
        self.assertEqual(reading(result, "01_intro.tex")["actual"], 1000)
        self.assertIn("1000 字", hits[0].text)
        self.assertIn("超出 25.0%", hits[0].text)

    def test_under_budget_does_not_fire(self):
        project = make_project(self.tmp / "zh-under",
                               {"01_intro.tex": zh_chars(700)},
                               budget_block(DEFAULT_BUDGET))
        _cfg, result = run_style(project)
        self.assertEqual(section_findings(result), [])
        self.assertEqual(reading(result, "01_intro.tex")["actual"], 700)

    def test_mixed_text_adds_words_and_chars(self):
        body = en_words(500) + " " + zh_chars(600)
        project = make_project(self.tmp / "mixed",
                               {"01_intro.tex": body},
                               budget_block(DEFAULT_BUDGET))
        _cfg, result = run_style(project)
        self.assertEqual(reading(result, "01_intro.tex")["actual"], 1100)
        self.assertEqual(len(section_findings(result)), 1)


# --------------------------------------------------------------------------
# 3. 没有 [budget] 就不跑（向后兼容）
# --------------------------------------------------------------------------

class TestNoBudget(BudgetCase):
    def test_long_section_is_silent_without_config(self):
        project = make_project(self.tmp / "no-budget",
                               {"01_intro.tex": en_words(2000)})
        _cfg, result = run_style(project)
        self.assertEqual(section_findings(result), [])
        self.assertEqual(result.metrics["section_length"], 0.0)
        self.assertEqual(result.metric_details["section_budget"], [])
        self.assertNotIn("SECTION_LENGTH", {f["code"] for f in result.fired})

    def test_budget_without_default_judges_nothing(self):
        project = make_project(self.tmp / "only-sections",
                               {"01_intro.tex": en_words(2000)},
                               budget_block(sections={"02_related": 3000}))
        cfg, result = run_style(project)
        self.assertTrue(cfg.budget_defined)
        self.assertEqual(cfg.budget_default, 0)
        self.assertEqual(section_findings(result), [])
        self.assertEqual(result.metric_details["section_budget"], [])


# --------------------------------------------------------------------------
# 4. 按节覆盖
# --------------------------------------------------------------------------

class TestSectionOverride(BudgetCase):
    def test_override_lifts_only_its_own_section(self):
        project = make_project(
            self.tmp / "override",
            {"01_intro.tex": en_words(1000),
             "04_style_case.tex": en_words(1100)},
            budget_block(DEFAULT_BUDGET, {"04_style_case": 1200}))
        cfg, result = run_style(project)
        self.assertEqual(cfg.budget_sections, {"04_style_case": 1200})
        self.assertEqual(section_budget(cfg, "sections/04_style_case.tex"), 1200)
        self.assertEqual(section_budget(cfg, "sections/01_intro.tex"), 800)
        hits = section_findings(result)
        self.assertEqual([f.file for f in hits], ["sections/01_intro.tex"])
        self.assertEqual(reading(result, "04_style_case.tex")["budget"], 1200)
        self.assertEqual(reading(result, "04_style_case.tex")["excess_percent"],
                         0.0)

    def test_chapter_and_appendix_are_judged_separately(self):
        project = make_project(
            self.tmp / "appendix",
            {"03_design.tex": en_words(1000),
             "appendix_a.tex": en_words(1500)},
            budget_block(DEFAULT_BUDGET, {"appendix_a": 2000}))
        cfg, result = run_style(project)
        self.assertEqual(section_budget(cfg, "sections/appendix_a.tex"), 2000)
        self.assertEqual(section_budget(cfg, "sections/03_design.tex"), 800)
        hits = section_findings(result)
        self.assertEqual([f.file for f in hits], ["sections/03_design.tex"])
        self.assertEqual(len(result.metric_details["section_budget"]), 2)


# --------------------------------------------------------------------------
# 5. 计数口径：LaTeX 命令与注释不算
# --------------------------------------------------------------------------

class TestCounting(BudgetCase):
    def test_commands_comments_math_and_markers_are_not_counted(self):
        noise = "\n".join(["% " + en_words(50) for _ in range(10)])
        body = (r"""\section{A Very Long Heading That Nobody Counts As Prose}
""" + noise + "\n" + r"""$ a + b = c $ \cite{key} \fact{B1}{53}
""" + en_words(100) + "\n")
        project = make_project(self.tmp / "counting",
                               {"01_intro.tex": body},
                               budget_block(DEFAULT_BUDGET))
        _cfg, result = run_style(project)
        self.assertEqual(reading(result, "01_intro.tex")["actual"], 100)
        self.assertEqual(section_findings(result), [])

    def test_empty_stub_files_are_not_judged(self):
        project = make_project(
            self.tmp / "stub",
            {"01_intro.tex": en_words(100),
             "02_macros.tex": "\\newcommand{\\foo}{bar}\n"},
            budget_block(DEFAULT_BUDGET))
        _cfg, result = run_style(project)
        judged = [item["file"]
                  for item in result.metric_details["section_budget"]]
        self.assertEqual(judged, ["sections/01_intro.tex"])
        self.assertEqual(section_findings(result), [])


# --------------------------------------------------------------------------
# 6. 配置失败面与 JSON 形状
# --------------------------------------------------------------------------

class TestConfigAndJson(BudgetCase):
    def test_non_positive_default_is_a_config_error(self):
        project = make_project(self.tmp / "bad",
                               {"01_intro.tex": en_words(100)},
                               "[budget]\ndefault = 0\n")
        proc = cli("style", str(project), "--json")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("budget", proc.stdout + proc.stderr)
        with self.assertRaises(ConfigError):
            load_config(project)

    def test_non_integer_override_is_a_config_error(self):
        project = make_project(self.tmp / "bad-override",
                               {"01_intro.tex": en_words(100)},
                               '[budget]\ndefault = 800\n'
                               '[budget.sections]\n"01_intro" = "很多"\n')
        proc = cli("style", str(project), "--json")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("budget", proc.stdout + proc.stderr)

    def test_json_exposes_per_section_readings(self):
        project = make_project(self.tmp / "json",
                               {"01_intro.tex": en_words(1000)},
                               budget_block(DEFAULT_BUDGET))
        payload = cli_json("style", str(project))
        self.assertEqual(payload["exit"], 3)
        self.assertEqual(payload["metrics"]["section_length"], 25.0)
        self.assertEqual(payload["thresholds"]["section_length_excess_percent"],
                         20.0)
        rows = payload["metric_details"]["section_budget"]
        self.assertEqual(rows, [{"file": "sections/01_intro.tex",
                                 "actual": 1000, "budget": 800,
                                 "excess_percent": 25.0}])
        hits = [f for f in payload["findings"] if f["code"] == "SECTION_LENGTH"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "yellow")


# --------------------------------------------------------------------------
# 7. brief 同步
# --------------------------------------------------------------------------

class TestBriefColumn(BudgetCase):
    def test_brief_lists_budget_column_from_same_config(self):
        project = make_project(
            self.tmp / "brief",
            {"01_intro.tex": en_words(100),
             "04_style_case.tex": en_words(100)},
            budget_block(DEFAULT_BUDGET, {"04_style_case": 1200}))
        brief = build_brief(project)
        text_brief = render_brief(brief)
        self.assertIn("篇幅预算", text_brief)
        rows = {row.file: row.budget for row in brief.sections}
        self.assertEqual(rows["sections/01_intro.tex"], 800)
        self.assertEqual(rows["sections/04_style_case.tex"], 1200)
        data = brief_payload(brief)
        self.assertEqual([s["budget"] for s in data["sections"]], [800, 1200])

    def test_brief_writes_dash_without_budget_config(self):
        project = make_project(self.tmp / "brief-none",
                               {"01_intro.tex": en_words(100)})
        brief = build_brief(project)
        text_brief = render_brief(brief)
        row = next(line for line in text_brief.splitlines()
                   if "01_intro.tex" in line)
        self.assertTrue(row.rstrip().endswith("| — |"), row)
        self.assertEqual([s["budget"] for s in brief_payload(brief)["sections"]],
                         [0])


if __name__ == "__main__":
    unittest.main()
