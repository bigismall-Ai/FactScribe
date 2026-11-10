# -*- coding: utf-8 -*-
"""批 119：``HEADING_SUBSTITUTED``——只换冒号不重写的机械判据。

判据（详见 ``docs/design/SPEC-SYNTAX-C.md``）：

* 只在 ``style --diff`` 带改写前目录时运行；
* 同一文件、同一命令层级、按出现顺序配对旧/新标题；
* 旧标题含冒号、新标题不含冒号；
* 把旧标题的冒号换成 ``、，,（）`` 之一后与新标题逐字相同，或换成
  ``as / with / for / of`` 之一后与新标题相同（介词大小写不敏感）；
* 命中即报，消息给出旧标题、新标题与被替换成的 token。

本文件锁住正例、负例与「没有 --before 不运行」的回归面。
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

from factscribe.config import load_config, load_sections  # noqa: E402
from factscribe.style import (analyze, filter_new_findings,  # noqa: E402
                              load_style_rules)

PROJECT_TOML = """[project]
title = "t"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""


def make_project(parent, body: str, rules: str | None = None) -> Path:
    root = Path(parent)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections" / "01_main.tex").write_text(body, encoding="utf-8")
    (root / "paperkit.toml").write_text(PROJECT_TOML, encoding="utf-8")
    if rules is not None:
        (root / "style-rules.toml").write_text(rules, encoding="utf-8")
    return root


def analyze_pair(parent, before_body: str, after_body: str,
                 rules: str | None = None):
    """返回 (本次新增 findings, 改后结果, 改前结果)。"""
    before_root = make_project(Path(parent) / "before", before_body, rules)
    after_root = make_project(Path(parent) / "after", after_body, rules)
    loaded, path = load_style_rules(after_root)
    before_cfg = load_config(before_root)
    after_cfg = load_config(after_root)
    before_sections = load_sections(before_cfg)
    after_sections = load_sections(after_cfg)
    after = analyze(after_cfg, after_sections, loaded, rules_path=path,
                    before=(before_cfg, before_sections))
    baseline = analyze(before_cfg, before_sections, loaded, rules_path=path)
    return filter_new_findings(after, baseline), after, baseline


def analyze_text(parent, body: str, rules: str | None = None):
    root = make_project(Path(parent) / "after", body, rules)
    cfg = load_config(root)
    loaded, path = load_style_rules(root)
    return analyze(cfg, load_sections(cfg), loaded, rules_path=path)


def codes(result) -> set:
    return {f.code for f in result.findings}


def finding(result, code: str):
    return next(f for f in result.findings if f.code == code)


def section(title: str, body: str = "本节给出一个可检验的断言。") -> str:
    return "\\section{%s}\n\n%s\n" % (title, body)


class TestHeadingSubstitutedPositive(unittest.TestCase):
    """纯替换：旧冒号换成标点或介词，其余逐字不动 → 必报。"""

    def _assert_hit(self, before_title: str, after_title: str,
                    token: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(
                tmp, section(before_title), section(after_title))
        self.assertIn("HEADING_SUBSTITUTED", codes(new))
        hit = finding(new, "HEADING_SUBSTITUTED")
        self.assertIn(before_title, hit.suggestion)
        self.assertIn(after_title, hit.suggestion)
        self.assertIn("「%s」" % token, hit.suggestion)

    def test_chinese_dunhao_substitution_reports(self):
        self._assert_hit("结论：一项草稿阶段的干预",
                         "结论、一项草稿阶段的干预", "、")

    def test_chinese_comma_substitution_reports(self):
        self._assert_hit("结论：一项草稿阶段的干预",
                         "结论，一项草稿阶段的干预", "，")

    def test_chinese_fullwidth_paren_substitution_reports(self):
        self._assert_hit("结论：一项草稿阶段的干预",
                         "结论（一项草稿阶段的干预", "（")

    def test_english_as_substitution_reports(self):
        self._assert_hit("Conclusion: A Draft-Stage Intervention",
                         "Conclusion as A Draft-Stage Intervention", "as")

    def test_case_change_in_article_still_reports(self):
        # 介词替换大小写不敏感：`A` → `a` 不能成为规避口子。
        self._assert_hit("Design: A Contract Before a Judge",
                         "Design as a Contract Before a Judge", "as")

    def test_english_with_substitution_reports(self):
        self._assert_hit("Method: Indicators, Bidirectional Rules, and Stage",
                         "Method with Indicators, Bidirectional Rules, and Stage",
                         "with")

    def test_english_for_and_of_substitutions_report(self):
        for token in ("for", "of"):
            with self.subTest(token=token):
                self._assert_hit("Scope: One Machine",
                                 "Scope %s One Machine" % token, token)

    def test_whitespace_around_colon_is_tolerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(
                tmp,
                "\\section{Conclusion:  A Draft-Stage Intervention}\n\n"
                "We report a testable claim.\n",
                "\\section{Conclusion   as   A Draft-Stage Intervention}\n\n"
                "We report a testable claim.\n")
        self.assertIn("HEADING_SUBSTITUTED", codes(new))


class TestHeadingSubstitutedNegative(unittest.TestCase):
    """真重写、删句号、旧标题无冒号、改了别的词 → 都不报。"""

    def _assert_no_hit(self, before_title: str, after_title: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(
                tmp, section(before_title), section(after_title))
        self.assertNotIn("HEADING_SUBSTITUTED", codes(new))

    def test_english_true_rewrite_does_not_report(self):
        self._assert_no_hit(
            "Results: The Gate Wins on Drafts and Loses on Polished Text",
            "Gate Wins on Drafts, Loses on Polished Text")

    def test_chinese_true_rewrite_does_not_report(self):
        self._assert_no_hit("结论：一项草稿阶段的干预",
                            "一项草稿阶段的干预")

    def test_trailing_period_deletion_does_not_report(self):
        self._assert_no_hit("生成系统。", "生成系统")

    def test_old_title_without_colon_does_not_report(self):
        self._assert_no_hit("Design as a Contract Before a Judge",
                            "Design with a Contract Before a Judge")

    def test_changed_word_besides_colon_does_not_report(self):
        # 冒号换成了顿号，但「干预」改成了「方案」：不是纯替换。
        self._assert_no_hit("结论：一项草稿阶段的干预",
                            "结论、一项草稿阶段的方案")

    def test_no_before_never_runs_substitution_rule(self):
        # 回归锁：不带 --before 时，即使标题是替换式改写，也不运行本判据。
        body = ("\\section{结论、一项草稿阶段的干预}\n\n"
                "本节给出一个可检验的断言。\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, body)
        self.assertNotIn("HEADING_SUBSTITUTED", codes(result))
        self.assertEqual(result.metrics["heading_substituted"], 0)


class TestHeadingSubstitutedPairingAndConfig(unittest.TestCase):
    def test_pairs_by_file_and_order_and_reports_only_the_substitution(self):
        before = (
            "\\section{Results: The Gate Wins on Drafts}\n\n"
            "We report a testable claim.\n\n"
            "\\section{Conclusion: A Draft-Stage Intervention}\n\n"
            "We report a second testable claim.\n"
        )
        after = (
            "\\section{Gate Wins on Drafts}\n\n"
            "We report a testable claim.\n\n"
            "\\section{Conclusion as A Draft-Stage Intervention}\n\n"
            "We report a second testable claim.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(tmp, before, after)
        hits = [f for f in new.findings
                if f.code == "HEADING_SUBSTITUTED"]
        self.assertEqual(len(hits), 1)
        self.assertIn("Conclusion as A Draft-Stage Intervention", hits[0].text)

    def test_substitute_tokens_are_configurable(self):
        rules = ('[heading_substitute]\n'
                 'punctuation = ["、"]\n'
                 'prepositions = ["via"]\n')
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(
                tmp, section("Scope: One Machine"),
                section("Scope via One Machine"), rules=rules)
        self.assertIn("HEADING_SUBSTITUTED", codes(new))

    def test_cli_diff_reports_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            before_root = make_project(
                Path(tmp) / "before", section("Conclusion: A Draft-Stage Intervention"))
            after_root = make_project(
                Path(tmp) / "after", section("Conclusion as A Draft-Stage Intervention"))
            env = dict(os.environ, PYTHONPATH=str(ROOT))
            proc = subprocess.run(
                [sys.executable, "-m", "factscribe", "style", str(after_root),
                 "--diff", str(before_root), "--json"],
                cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(
            [f["code"] for f in payload["findings"]],
            ["HEADING_SUBSTITUTED"])
        self.assertEqual(payload["diff"]["new_findings"], 1)


if __name__ == "__main__":
    unittest.main()
