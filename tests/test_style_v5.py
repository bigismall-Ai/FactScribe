# -*- coding: utf-8 -*-
"""批 87：文风闸 v5「改写后复检」判据测试（全离线）。

规则清单见 SPEC-V3.0 §15：

* ``HEADING_ECHO``：首句只是复述标题（复述 / 垫话 / 纯设问）；
* ``TERM_FIRST_IN_HEADING`` 文案修订：禁止三种伪满足；
* ``HEADING_RELATION_CHANGED``：标题关系词被替换或删除；
* ``HEADING_SUBJECT_LOST``：旧标题的实义成分在新标题与新首句里都消失；
* ``style --diff <before>``：只报本次改写新增的违规。

每条规则至少 3 例（正例 / 负例 / 边界）；另把批 84 的 6 个真实退步
做成最小复现夹具，并验证真正的定义式首句不会被误报。
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


def analyze_text(parent, body: str, rules: str | None = None):
    root = make_project(Path(parent) / "after", body, rules)
    cfg = load_config(root)
    loaded, path = load_style_rules(root)
    return analyze(cfg, load_sections(cfg), loaded, rules_path=path)


def analyze_pair(parent, before_body: str, after_body: str,
                 rules: str | None = None):
    """返回 (本次新增 findings, 改后完整结果, 改前结果)。"""
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


def codes(result) -> set:
    return {f.code for f in result.findings}


def run_style(root: Path, *args: str):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", "style", str(root), *args]
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


# --------------------------------------------------------------------------
# 1. HEADING_ECHO
# --------------------------------------------------------------------------

ECHO_EN = (
    "\\subsection{Known and not fixed}\n\n"
    "These limitations are known and not fixed. The main comparison has "
    "sixteen instances and a wide interval.\n"
)
ECHO_ZH = (
    "\\subsection{已知且未修}\n\n"
    "这些是已知且未修的限制。主对照有十六单，其中可判的十四单。\n"
)
ECHO_META_EN = (
    "\\section{Related work}\n\n"
    "This section is about long-horizon benchmarks and the tooling around them.\n"
)
ECHO_META_ZH = (
    "\\section{相关工作}\n\n"
    "相关工作里，长程软件基准把评测从函数级合成推进到仓库级修复。\n"
)
ECHO_META_ZH_2 = (
    "\\subsection{成本记账}\n\n"
    "成本记账要先问账本记了什么。账本过去每次调用只记一个数。\n"
)
ECHO_DEF_EN = (
    "\\section{Preregistration}\n\n"
    "Preregistration is fixing the hypotheses and the analysis plan before "
    "data collection.\n"
)
ECHO_DEF_ZH = (
    "\\section{预注册}\n\n"
    "预注册是在收集数据前固定假设与分析计划的做法。\n"
)
ECHO_ONE_NEW = (
    "\\section{Cost ledger}\n\n"
    "Cost ledger records.\n"
)
ECHO_NO_BODY = (
    "\\section{Method}\n"
    "\\section{Next}\n\n"
    "We describe the pipeline in enough detail to form a sentence.\n"
)


class TestHeadingEcho(unittest.TestCase):
    def test_positive_english_restates_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ECHO_EN)
        self.assertIn("HEADING_ECHO", codes(result))
        hit = next(f for f in result.findings if f.code == "HEADING_ECHO")
        self.assertEqual(hit.severity, "yellow")
        self.assertIn("复述标题", hit.suggestion)

    def test_positive_chinese_restates_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ECHO_ZH)
        self.assertIn("HEADING_ECHO", codes(result))

    def test_positive_english_meta_opener(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ECHO_META_EN)
        self.assertIn("HEADING_ECHO", codes(result))

    def test_positive_chinese_meta_opener(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ECHO_META_ZH)
        self.assertIn("HEADING_ECHO", codes(result))

    def test_positive_chinese_preamble_opener(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ECHO_META_ZH_2)
        self.assertIn("HEADING_ECHO", codes(result))

    def test_negative_english_definition(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ECHO_DEF_EN)
        self.assertNotIn("HEADING_ECHO", codes(result))

    def test_negative_chinese_definition(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ECHO_DEF_ZH)
        self.assertNotIn("HEADING_ECHO", codes(result))

    def test_boundary_one_new_term_passes_at_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ECHO_ONE_NEW)
        self.assertNotIn("HEADING_ECHO", codes(result))

    def test_threshold_raised_reports_one_new_term(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(
                tmp, ECHO_ONE_NEW,
                "[thresholds]\nheading_echo_min_new_terms = 2\n")
        self.assertIn("HEADING_ECHO", codes(result))

    def test_heading_without_own_body_is_not_judged(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ECHO_NO_BODY)
        self.assertNotIn("HEADING_ECHO", codes(result))


# --------------------------------------------------------------------------
# 2. TERM_FIRST_IN_HEADING（文案修订：禁止三种伪满足）
# --------------------------------------------------------------------------

TERM_UNDEFINED = (
    "\\section{Retrieval Augmented}\n"
    "We describe the pipeline in this section with enough words to form a sentence.\n"
)


class TestTermFirstCopy(unittest.TestCase):
    def test_suggestion_forbids_three_pseudo_definitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TERM_UNDEFINED)
        hit = next(f for f in result.findings
                   if f.code == "TERM_FIRST_IN_HEADING")
        self.assertIn("复述标题", hit.suggestion)
        self.assertIn("垫话", hit.suggestion)
        self.assertIn("设问", hit.suggestion)
        self.assertNotIn("本节讨论", hit.suggestion)

    def test_suggestion_points_to_definition_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TERM_UNDEFINED)
        hit = next(f for f in result.findings
                   if f.code == "TERM_FIRST_IN_HEADING")
        self.assertIn("预注册", hit.suggestion)

    def test_restating_heading_does_not_define_term(self):
        # 术语出现但只是复述标题：TERM 不再给「已定义」的错觉，
        # 由 HEADING_ECHO 接手报黄。
        body = ("\\section{Known and not fixed}\n\n"
                "These limitations are known and not fixed.\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, body)
        self.assertIn("HEADING_ECHO", codes(result))


# --------------------------------------------------------------------------
# 3. HEADING_RELATION_CHANGED（需 --before）
# --------------------------------------------------------------------------

REL_BEFORE = (
    "\\section{Mechanisms}\n\n"
    "\\paragraph{Prompt versus mechanism.} We first wrote the required process "
    "as six constraints.\n"
)
REL_AFTER = REL_BEFORE.replace("versus", "or")

REL_SAME = (
    "\\section{Mechanisms}\n\n"
    "\\paragraph{Prompt versus mechanism.} We first wrote the required process "
    "as six constraints.\n"
)
REL_ADDED = REL_BEFORE.replace("Prompt versus mechanism.",
                               "Prompt or mechanism.")
REL_ZH_BEFORE = (
    "\\section{机制}\n\n"
    "\\paragraph{提示词对机制。} 我们先把要求的流程写成六条约束。\n"
)
REL_ZH_AFTER = REL_ZH_BEFORE.replace("提示词对机制。", "提示词。")
REL_ZH_SAME = REL_ZH_BEFORE


class TestHeadingRelationChanged(unittest.TestCase):
    def test_positive_english_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(tmp, REL_BEFORE, REL_AFTER)
        self.assertIn("HEADING_RELATION_CHANGED", codes(new))

    def test_positive_chinese_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(tmp, REL_ZH_BEFORE,
                                                REL_ZH_AFTER)
        self.assertIn("HEADING_RELATION_CHANGED", codes(new))

    def test_negative_unchanged_relation_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(tmp, REL_SAME, REL_SAME)
        self.assertNotIn("HEADING_RELATION_CHANGED", codes(new))

    def test_boundary_added_relation_word_is_not_reported(self):
        # 旧标题没有关系词、新标题新增一个：不是「替换或删除」。
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(
                tmp, REL_BEFORE.replace("Prompt versus mechanism.",
                                        "Prompt mechanism."),
                REL_ADDED)
        self.assertNotIn("HEADING_RELATION_CHANGED", codes(new))

    def test_missing_before_never_reports_relation_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, REL_AFTER)
        self.assertNotIn("HEADING_RELATION_CHANGED", codes(result))

    def test_relation_words_are_configurable(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(
                tmp, "\\section{A and B}\n\nWe describe both parts.\n",
                "\\section{A B}\n\nWe describe both parts.\n",
                rules='heading_relation_words = ["versus"]\n')
        self.assertNotIn("HEADING_RELATION_CHANGED", codes(new))


# --------------------------------------------------------------------------
# 4. HEADING_SUBJECT_LOST（需 --before）
# --------------------------------------------------------------------------

LOST_ZH_BEFORE = (
    "\\section{机制}\n\n"
    "\\paragraph{提示词对机制。} 我们先把要求的流程写成六条约束。\n"
)
LOST_ZH_AFTER = (
    "\\section{机制}\n\n"
    "\\paragraph{提示词} 我们先把要求的流程写成六条约束。\n"
)
LOST_EN_BEFORE = (
    "\\section{Appendix}\n\n"
    "\\section{Debug log: run order and per-arm cost}\n"
    "The log records every arm and every run.\n"
)
LOST_EN_AFTER = (
    "\\section{Appendix}\n\n"
    "\\section{Debug log}\n"
    "The log records every arm and every run.\n"
)
LOST_EN_CONTRAST_BEFORE = (
    "\\section{Mechanisms}\n\n"
    "\\paragraph{Prompt versus mechanism.} We first wrote the required process "
    "as six constraints.\n"
)
LOST_EN_CONTRAST_AFTER = (
    "\\section{Mechanisms}\n\n"
    "\\paragraph{Prompt.} We first wrote the required process "
    "as six constraints.\n"
)
LOST_SUBJECT_BACK_IN_SENTENCE = (
    "\\section{机制}\n\n"
    "\\paragraph{提示词} 机制决定了这一回合何时收口。\n"
)


class TestHeadingSubjectLost(unittest.TestCase):
    def test_positive_chinese_subject_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(tmp, LOST_ZH_BEFORE,
                                                LOST_ZH_AFTER)
        self.assertIn("HEADING_SUBJECT_LOST", codes(new))

    def test_positive_english_subject_lost(self):
        # v5b：只有对比结构才判「对象丢失」。并列标题
        # ``Debug log: run order and per-arm cost`` → ``Debug log``
        # 现在归入负例（见 TestTightenedPrecision）。
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(
                tmp, LOST_EN_CONTRAST_BEFORE, LOST_EN_CONTRAST_AFTER)
        self.assertIn("HEADING_SUBJECT_LOST", codes(new))

    def test_negative_subject_kept_in_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(tmp, LOST_ZH_BEFORE,
                                                LOST_ZH_BEFORE)
        self.assertNotIn("HEADING_SUBJECT_LOST", codes(new))

    def test_boundary_subject_returns_in_first_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(
                tmp, LOST_ZH_BEFORE, LOST_SUBJECT_BACK_IN_SENTENCE)
        self.assertNotIn("HEADING_SUBJECT_LOST", codes(new))

    def test_missing_before_never_reports_subject_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, LOST_ZH_AFTER)
        self.assertNotIn("HEADING_SUBJECT_LOST", codes(result))


# --------------------------------------------------------------------------
# 5. style --diff：只报本次改写新增的违规
# --------------------------------------------------------------------------

CLEAN = (
    "\\section{Preregistration}\n\n"
    "Preregistration is fixing the hypotheses and the analysis plan before "
    "data collection.\n"
)
DASH_ONE = (
    "\\section{Method}\n\n"
    "We propose a new method—it runs on one machine and report every result.\n"
)
DASH_TWO = (
    "\\section{Method}\n\n"
    "We propose a new method—it runs on one machine and report every result.\n"
    "A second note—one aside does not change the measured outcome.\n"
)


class TestStyleDiff(unittest.TestCase):
    def test_clean_before_and_after_reports_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, after, baseline = analyze_pair(tmp, CLEAN, CLEAN)
        self.assertEqual(new.findings, [])
        self.assertEqual(new.summary["exit_code"], 0)
        self.assertGreaterEqual(len(after.findings), 0)
        self.assertEqual(len(after.findings), len(baseline.findings))

    def test_before_one_after_two_reports_only_the_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(tmp, DASH_ONE, DASH_TWO)
        dashes = [f for f in new.findings if f.code == "DASH_PARENTHETICAL"]
        self.assertEqual(len(dashes), 1)
        self.assertIn("second note", dashes[0].text)

    def test_same_violation_before_and_after_is_not_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(tmp, DASH_ONE, DASH_ONE)
        self.assertEqual([f for f in new.findings
                          if f.code == "DASH_PARENTHETICAL"], [])

    def test_echo_introduced_by_rewrite_is_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(
                tmp,
                "\\subsection{Known and not fixed}\n\nThe main comparison has "
                "sixteen instances and a wide interval.\n",
                ECHO_EN)
        self.assertIn("HEADING_ECHO", codes(new))

    def test_cli_diff_returns_zero_when_nothing_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            before_root = make_project(Path(tmp) / "before", CLEAN)
            after_root = make_project(Path(tmp) / "after", CLEAN)
            proc = run_style(after_root, "--diff", str(before_root), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["diff"]["new_findings"], 0)

    def test_cli_diff_returns_three_on_new_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            before_root = make_project(Path(tmp) / "before", DASH_ONE)
            after_root = make_project(Path(tmp) / "after", DASH_TWO)
            proc = run_style(after_root, "--diff", str(before_root), "--json")
        self.assertEqual(proc.returncode, 3, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["diff"]["new_findings"], 1)


# --------------------------------------------------------------------------
# 6. 批 84 的 6 个真实退步：最小复现夹具
# --------------------------------------------------------------------------

SAMPLE_EN_10_BEFORE = (
    "\\subsection{Known and not fixed}\n\n"
    "The main comparison has sixteen instances and a wide interval.\n"
)
SAMPLE_EN_10_AFTER = (
    "\\subsection{Known and not fixed}\n\n"
    "These limitations are known and not fixed.\n\n"
    "The main comparison has sixteen instances and a wide interval.\n"
)
SAMPLE_ZH_08_BEFORE = (
    "\\subsection{已知且未修}\n\n"
    "主对照有十六单，其中可判的十四单。\n"
)
SAMPLE_ZH_08_AFTER = (
    "\\subsection{已知且未修}\n\n"
    "这些是已知且未修的限制。主对照有十六单，其中可判的十四单。\n"
)
SAMPLE_ZH_06_BEFORE = (
    "\\subsection{成本记账}\n\n"
    "账本过去每次调用只记一个数：总 token。\n"
)
SAMPLE_ZH_06_AFTER = (
    "\\subsection{成本记账}\n\n"
    "成本记账要先问账本记了什么。账本过去每次调用只记一个数：总 token。\n"
)
SAMPLE_ZH_09_BEFORE = (
    "\\section{相关工作}\n\n"
    "长程软件基准把评测从函数级合成推进到仓库级修复。\n"
)
SAMPLE_ZH_09_AFTER = (
    "\\section{相关工作}\n\n"
    "相关工作里，长程软件基准把评测从函数级合成推进到仓库级修复。\n"
)
SAMPLE_EN_06_BEFORE = (
    "\\section{Mechanisms}\n\n"
    "\\paragraph{Prompt versus mechanism.} We first wrote the required process "
    "as six constraints.\n"
)
SAMPLE_EN_06_AFTER = SAMPLE_EN_06_BEFORE.replace("versus", "or")
SAMPLE_ZH_04_BEFORE = (
    "\\section{机制}\n\n"
    "\\paragraph{提示词对机制。} 我们先把要求的流程写成六条约束。\n"
)
SAMPLE_ZH_04_AFTER = (
    "\\section{机制}\n\n"
    "\\paragraph{提示词} 我们先把要求的流程写成六条约束。\n"
)


class TestBatch84Regressions(unittest.TestCase):
    """批 84 盲评判为退步的 6 处改动，每处 3–5 行 LaTeX 最小复现。"""

    def _run(self, before, after, expected):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(tmp, before, after)
        self.assertIn(expected, codes(new))

    def test_en_10_limitations_echo(self):
        self._run(SAMPLE_EN_10_BEFORE, SAMPLE_EN_10_AFTER, "HEADING_ECHO")

    def test_zh_08_limitations_echo(self):
        self._run(SAMPLE_ZH_08_BEFORE, SAMPLE_ZH_08_AFTER, "HEADING_ECHO")

    def test_zh_06_preamble_echo(self):
        self._run(SAMPLE_ZH_06_BEFORE, SAMPLE_ZH_06_AFTER, "HEADING_ECHO")

    def test_zh_09_related_work_preamble(self):
        self._run(SAMPLE_ZH_09_BEFORE, SAMPLE_ZH_09_AFTER, "HEADING_ECHO")

    def test_en_06_relation_word_replaced(self):
        self._run(SAMPLE_EN_06_BEFORE, SAMPLE_EN_06_AFTER,
                  "HEADING_RELATION_CHANGED")

    def test_zh_04_relation_and_subject_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(
                tmp, SAMPLE_ZH_04_BEFORE, SAMPLE_ZH_04_AFTER)
        self.assertIn("HEADING_RELATION_CHANGED", codes(new))
        self.assertIn("HEADING_SUBJECT_LOST", codes(new))


# --------------------------------------------------------------------------
# 7. v5b：收紧精度（只降噪，不丢召回）
# --------------------------------------------------------------------------

# 4 个良性实例（批 88 任务表）＋ 2 个同族实例，必须不再报。
NOISE_EN_DEBUG_BEFORE = (
    "\\section{Debug log: run order and per-arm cost}\n\n"
    "The log records every arm and every run.\n"
)
NOISE_EN_DEBUG_AFTER = (
    "\\section{Debug log}\n\n"
    "The log records every arm and every run.\n"
)
NOISE_EN_INVARIANTS_BEFORE = (
    "\\subsection{Invariants, and what they stop}\n\n"
    "The register names twenty-one invariants over the assembly.\n"
)
NOISE_EN_INVARIANTS_AFTER = (
    "\\subsection{Invariants}\n\n"
    "The register names twenty-one invariants over the assembly.\n"
)
NOISE_EN_ATTRIBUTION_BEFORE = (
    "\\section{Cost}\n\n"
    "\\paragraph{What the attribution shows.} The difference is in output, "
    "not input.\n"
)
NOISE_EN_ATTRIBUTION_AFTER = (
    "\\section{Cost}\n\n"
    "\\paragraph{Attribution.} The difference is in output, not input.\n"
)
NOISE_ZH_CAPACITY_BEFORE = (
    "\\section{消融}\n\n"
    "\\paragraph{假设一：容量。} 如果回合失败是因为空间不够，"
    "那么撤掉压力就该让它跑完。\n"
)
NOISE_ZH_CAPACITY_AFTER = (
    "\\section{消融}\n\n"
    "\\paragraph{容量假设} 如果回合失败是因为空间不够，"
    "那么撤掉压力就该让它跑完。\n"
)
NOISE_ZH_DEBUG_BEFORE = (
    "\\section{调试日志：运行顺序与每臂成本}\n\n"
    "本附录记录各臂实际运行的顺序。\n"
)
NOISE_ZH_DEBUG_AFTER = (
    "\\section{调试日志}\n\n"
    "本附录记录各臂实际运行的顺序。\n"
)
NOISE_ZH_INVARIANTS_BEFORE = (
    "\\subsection{不变式，以及它们拦住了什么}\n\n"
    "登记册列出了二十一条针对装配的不变式。\n"
)
NOISE_ZH_INVARIANTS_AFTER = (
    "\\subsection{不变式}\n\n"
    "登记册列出了二十一条针对装配的不变式。\n"
)
NOISE_ZH_CLI_BEFORE = (
    "\\subsection{对照一个成熟的 CLI}\n\n"
    "表在同样六题上比较两套脚手架。\n"
)
NOISE_ZH_CLI_AFTER = (
    "\\subsection{与成熟 CLI 对比}\n\n"
    "表在同样六题上比较两套脚手架。\n"
)

# 论文里未改动的正常标题（从 paper/、paper-zh/ 的 sections 实取）。
UNCHANGED_TITLES = [
    ("\\section{Related work}\n\nLong-horizon software benchmarks moved "
     "evaluation from function-level synthesis to repository-level repair.\n"),
    ("\\section{Cost accounting}\n\nThe ledger records the supplier usage "
     "fields verbatim.\n"),
    ("\\section{Across domains}\n\nTable reports a tool-and-policy benchmark "
     "from the tau-bench family.\n"),
    ("\\section{Mechanical gates}\n\nThe gates answer a different question "
     "from context: not what the model knows, but when the episode ends.\n"),
    ("\\section{相关工作}\n\n长程软件基准把评测从函数级合成推进到仓库级修复。\n"),
    ("\\section{成本记账}\n\n账本过去每次调用只记一个数：总 token。\n"),
    ("\\section{机械闸门}\n\n闸门回答的是与上下文不同的问题："
     "不是模型知道什么，而是这一回合何时结束。\n"),
    ("\\section{跨领域}\n\n表报告一个工具与策略基准，"
     "成功既取决于正确调用工具，也取决于遵守成文策略。\n"),
]

BOUNDARY_RELATION_TITLE = (
    "\\section{Mechanisms}\n\n"
    "\\paragraph{Prompt versus mechanism.} We first wrote the required process "
    "as six constraints.\n"
)


class TestTightenedPrecision(unittest.TestCase):
    """批 88：两条复检规则收紧后的正/负例锁。"""

    TARGET = {"HEADING_RELATION_CHANGED", "HEADING_SUBJECT_LOST"}

    def _new_codes(self, before: str, after: str) -> set:
        with tempfile.TemporaryDirectory() as tmp:
            new, _after, _before = analyze_pair(tmp, before, after)
        return codes(new)

    def assert_no_noise(self, before: str, after: str):
        fired = self._new_codes(before, after)
        self.assertFalse(fired & self.TARGET,
                         "unexpected heading noise: %s" % (fired & self.TARGET))

    # -- 4 个良性实例 ------------------------------------------------------
    def test_benign_debug_log_does_not_report(self):
        self.assert_no_noise(NOISE_EN_DEBUG_BEFORE, NOISE_EN_DEBUG_AFTER)

    def test_benign_invariants_and_does_not_report(self):
        self.assert_no_noise(NOISE_EN_INVARIANTS_BEFORE,
                             NOISE_EN_INVARIANTS_AFTER)

    def test_benign_attribution_subject_does_not_report(self):
        self.assert_no_noise(NOISE_EN_ATTRIBUTION_BEFORE,
                             NOISE_EN_ATTRIBUTION_AFTER)

    def test_benign_capacity_ordinal_does_not_report(self):
        self.assert_no_noise(NOISE_ZH_CAPACITY_BEFORE, NOISE_ZH_CAPACITY_AFTER)

    # -- 同族的并列/序数/介词噪声 -----------------------------------------
    def test_benign_chinese_debug_yu_does_not_report(self):
        self.assert_no_noise(NOISE_ZH_DEBUG_BEFORE, NOISE_ZH_DEBUG_AFTER)

    def test_benign_chinese_invariants_and_does_not_report(self):
        self.assert_no_noise(NOISE_ZH_INVARIANTS_BEFORE,
                             NOISE_ZH_INVARIANTS_AFTER)

    def test_benign_duizhao_to_yu_compare_does_not_report(self):
        self.assert_no_noise(NOISE_ZH_CLI_BEFORE, NOISE_ZH_CLI_AFTER)

    def test_benign_english_and_deletion_does_not_report(self):
        self.assert_no_noise(
            "\\section{A and B}\n\nWe describe both parts in detail.\n",
            "\\section{A B}\n\nWe describe both parts in detail.\n")

    def test_benign_chinese_yu_deletion_does_not_report(self):
        self.assert_no_noise(
            "\\section{甲与乙}\n\n我们分别描述两边的做法与代价。\n",
            "\\section{甲乙}\n\n我们分别描述两边的做法与代价。\n")

    # -- 论文里未改动的正常标题 -------------------------------------------
    def test_untouched_paper_titles_do_not_report(self):
        for body in UNCHANGED_TITLES:
            with self.subTest(title=body.splitlines()[0]):
                self.assert_no_noise(body, body)

    # -- 边界：EN-06 的新标题必报，原标题不报 -----------------------------
    def test_boundary_prompt_or_mechanism_reports(self):
        fired = self._new_codes(
            BOUNDARY_RELATION_TITLE,
            BOUNDARY_RELATION_TITLE.replace("versus", "or"))
        self.assertIn("HEADING_RELATION_CHANGED", fired)

    def test_boundary_prompt_versus_mechanism_itself_does_not_report(self):
        self.assert_no_noise(BOUNDARY_RELATION_TITLE, BOUNDARY_RELATION_TITLE)

    def test_contrast_replaced_by_coordination_still_reports(self):
        fired = self._new_codes(
            BOUNDARY_RELATION_TITLE,
            BOUNDARY_RELATION_TITLE.replace("versus", "and"))
        self.assertIn("HEADING_RELATION_CHANGED", fired)

    def test_subject_lost_while_relation_word_kept(self):
        # 关系词保留、对比对象被换掉：只有 HEADING_SUBJECT_LOST 能报，
        # 说明两条规则不完全重合，不能降为 info。
        fired = self._new_codes(
            BOUNDARY_RELATION_TITLE,
            BOUNDARY_RELATION_TITLE.replace("mechanism", "trigger"))
        self.assertIn("HEADING_SUBJECT_LOST", fired)
        self.assertNotIn("HEADING_RELATION_CHANGED", fired)


if __name__ == "__main__":
    unittest.main()
