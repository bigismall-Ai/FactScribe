# -*- coding: utf-8 -*-
"""批 102：六条句法级判据（全离线）。

规范：`docs/design/SPEC-SYNTAX.md`；读数：`docs/implementation/SYNTAX.md`。

覆盖：

* `LIGHT_VERB_NOMINALIZATION`：甲/乙两组正例、名词后缀、白名单、
  乙组精度边界（宾语补足语 / 短语动词 / 状态名词）、动作动词提示；
* `ZH_DE_STACK`：短修饰链正例、正常定语负例、长定语负例、间隔 6/7 边界、
  阈值可配、引文与列表遮罩；
* `ZH_POSTPOSED_CONDITION`：后置正例、前置负例、「若干」豁免、多标记；
* `ZH_DUE_TO_MAKE`：两种原因标记、负例、跨句不报、理由含「缺主」；
* `WORDINESS_BLOAT`：五条短语各一例、直接替代、B 级不报、大小写；
* A6 bug 修复：只写「显著」不报、八条中文统计短语、其余形容词照旧；
* 两条处方 `unbury-the-verb` / `cut-the-de` 可查。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import Config  # noqa: E402
from factscribe.prescribe import prescriptions_for  # noqa: E402
from factscribe.style import analyze, load_style_rules  # noqa: E402


def analyze_text(text: str, rules: str = "", fmt: str = "markdown") -> object:
    """把一段文本当独立文件跑 style，返回 StyleResult。"""
    name = "doc.tex" if fmt == "tex" else "doc.md"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if rules:
            (root / "style-rules.toml").write_text(rules, encoding="utf-8")
        loaded, path = load_style_rules(root)
        result = analyze(Config(root=root), [(name, text)], loaded,
                         rules_path=path, formats={name: fmt})
    return result


def codes(result) -> set:
    return {f.code for f in result.findings}


def findings(result, code: str):
    return [f for f in result.findings if f.code == code]


# --------------------------------------------------------------------------
# 样本
# --------------------------------------------------------------------------

LIGHT_ARTICLE = (
    "We make a distinction between the two runtime paths in this section."
)
LIGHT_ANALYSIS = (
    "The team performed an analysis of the failing runs before the rewrite."
)
LIGHT_CARRY = (
    "We carried out an evaluation of the gate on the frozen project."
)
LIGHT_BARE = (
    "We performed analysis on the logs and recorded every verdict."
)
LIGHT_PLAIN = (
    "The model performs well under load and stays within the token budget."
)
LIGHT_COMPLEMENT = (
    "The instruction made the section more uniform and tripped a rule. "
    "The result does not establish superiority over the baseline."
)
LIGHT_EXEMPT = (
    "Every run has a chance to fail on the first attempt. "
    "These measurements provide a basis for the comparison."
)

DE_CHAIN = "弯弯的杨柳的稀疏的倩影。"                    # 余光中原例：连续短修饰
DE_STACK = "这是他的老师的学生的作业的答案。"            # 4 个「的」，每段修饰 2 字
DE_SHORT_CHAIN = "他的老师的学生的作业。"                # 3 个「的」也报（不再要求 ≥4）
# 正常定语：不是连续短修饰。第一句「难度档用的是…」是「是…的」结构，
# 第二句夹着「是一个任务的」与「那些臂是更小的」两个谓词断点。
DE_NORMAL_TABLE = "表 的难度档用的是数据集自带的标签，不是我们另贴的。"
DE_NORMAL_ARM = (
    "最后一臂的 5/5 是一个任务的五次运行，而不成功的那些臂是更小的集合。")
DE_LONG_ATTR = "一个关于模型在长程任务中失败原因的分析。"  # 只有 1 个「的」
DE_GAP_6 = "红红的杨柳花草树木的叶子的颜色。"           # 链内间隔恰好 6 字
DE_GAP_7 = "红红的杨柳花草树木林的叶子的颜色。"         # 链内间隔 7 字，不报
DE_SINGLE_GAP = "他收到的载荷的哈希。"                  # 只有一个短间隔：相对从句，不成链

POST_COND = "这个矩阵是幂等的，如果它的秩等于阶数。"
PRE_COND = "如果矩阵的秩等于阶数，它就是幂等的。"
POST_RUO = "我们检查了矩阵，若结果为空则跳过。"
POST_TANG = "实验会继续，倘若样本量达到阈值。"
POST_YIDAN = "流程不会停，一旦样本量达到阈值。"
POST_RUOGAN = "我们讨论了下述问题，若干细节仍需确认。"

DUE_MAKE_1 = "由于他的家境贫穷，使得他只好休学。"
DUE_MAKE_2 = "因为数据缺失，导致结果不可靠。"
DUE_OK = "由于数据缺失，结果不可靠。"
DUE_NO_PREP = "数据缺失导致结果不可靠。"
DUE_CROSS = "由于数据缺失。这使得结果不可靠。"

BLOAT_BECAUSE = (
    "The run was rejected due to the fact that the cache was cold."
)
BLOAT_NOW = "At this point in time the pipeline is stable under load."
BLOAT_ALTHOUGH = (
    "In spite of the fact that the gate fired, the patch was correct."
)
BLOAT_IF = "The fallback runs in the event that the primary fails."
BLOAT_ACCOUNT = (
    "The job stopped on account of the fact that the disk was full."
)
BLOAT_TIER_B = "In order to keep the log short, we drop repeated lines."
BLOAT_CASE = (
    "Due to the fact that the cache was cold, the run was rejected."
)

SIGNIFICANT_BARE = "这个结果很显著。我们重复了三次实验。"
SIGNIFICANT_TERM = "这个差异是统计显著的。我们重复了三次实验。"
SIGNIFICANT_PHRASE = "两组之间存在显著差异。我们重复了三次实验。"
EMPTY_STILL = "这个方案至关重要。我们重复了三次实验。"

DE_GAP_CONFIG = "[thresholds]\nzh_de_stack_max_gap = 7\n"


# --------------------------------------------------------------------------
# 1. LIGHT_VERB_NOMINALIZATION
# --------------------------------------------------------------------------

class TestLightVerbNominalization(unittest.TestCase):
    def test_make_a_distinction_reports_action_verb(self):
        result = analyze_text(LIGHT_ARTICLE)
        found = findings(result, "LIGHT_VERB_NOMINALIZATION")
        self.assertEqual(len(found), 1)
        self.assertIn("distinguish", found[0].suggestion)

    def test_perform_an_analysis_reports_analyze(self):
        result = analyze_text(LIGHT_ANALYSIS)
        found = findings(result, "LIGHT_VERB_NOMINALIZATION")
        self.assertEqual(len(found), 1)
        self.assertIn("analyze", found[0].suggestion)

    def test_carry_out_an_evaluation(self):
        result = analyze_text(LIGHT_CARRY)
        self.assertIn("LIGHT_VERB_NOMINALIZATION", codes(result))

    def test_direct_group_allows_missing_article(self):
        result = analyze_text(LIGHT_BARE)
        self.assertIn("LIGHT_VERB_NOMINALIZATION", codes(result))

    def test_plain_verb_negative(self):
        result = analyze_text(LIGHT_PLAIN)
        self.assertNotIn("LIGHT_VERB_NOMINALIZATION", codes(result))
        self.assertEqual(result.metrics["light_verb_nominalization"], 0)

    def test_article_group_rejects_complement_and_particle(self):
        # "make the X more uniform" 是宾语补足语，"establish superiority"
        # 是状态名词；两者都不是「动作藏在名词里」。
        result = analyze_text(LIGHT_COMPLEMENT)
        self.assertNotIn("LIGHT_VERB_NOMINALIZATION", codes(result))

    def test_whitelisted_collocations_negative(self):
        result = analyze_text(LIGHT_EXEMPT)
        self.assertNotIn("LIGHT_VERB_NOMINALIZATION", codes(result))

    def test_metric_is_item_count_not_density(self):
        text = (LIGHT_ARTICLE + " " + LIGHT_ANALYSIS + " "
                + LIGHT_CARRY + "\n")
        result = analyze_text(text)
        self.assertEqual(result.metrics["light_verb_nominalization"], 3)


# --------------------------------------------------------------------------
# 2. ZH_DE_STACK
# --------------------------------------------------------------------------

class TestZhDeStack(unittest.TestCase):
    def test_short_modifier_chain_reports(self):
        result = analyze_text(DE_CHAIN)
        found = findings(result, "ZH_DE_STACK")
        self.assertEqual(len(found), 1)
        self.assertEqual(result.metrics["zh_de_stack"], 1)

    def test_four_de_chain_reports(self):
        result = analyze_text(DE_STACK)
        self.assertEqual(result.metrics["zh_de_stack"], 1)

    def test_three_de_short_chain_reports(self):
        # 不再要求总数 ≥4：三个「的」连成短链就报。
        result = analyze_text(DE_SHORT_CHAIN)
        self.assertIn("ZH_DE_STACK", codes(result))

    def test_normal_attributive_sentences_negative(self):
        # 「是…的」/ 谓词断点不是连续短修饰。
        for text in (DE_NORMAL_TABLE, DE_NORMAL_ARM):
            with self.subTest(text=text):
                self.assertNotIn("ZH_DE_STACK", codes(analyze_text(text)))

    def test_long_attributive_negative(self):
        # 「的」少但修饰长（长定语），不是「的的不休」。
        result = analyze_text(DE_LONG_ATTR)
        self.assertNotIn("ZH_DE_STACK", codes(result))

    def test_gap_boundary_six_reports_seven_not(self):
        self.assertIn("ZH_DE_STACK", codes(analyze_text(DE_GAP_6)))
        self.assertNotIn("ZH_DE_STACK", codes(analyze_text(DE_GAP_7)))

    def test_single_short_gap_is_not_a_chain(self):
        # 「收到的载荷的哈希」只有一个短间隔，是相对从句而非连续短修饰。
        result = analyze_text(DE_SINGLE_GAP)
        self.assertNotIn("ZH_DE_STACK", codes(result))

    def test_gap_threshold_configurable(self):
        result = analyze_text(DE_GAP_7, DE_GAP_CONFIG)
        self.assertIn("ZH_DE_STACK", codes(result))

    def test_masked_blockquote_and_list_negative(self):
        for text in ("> " + DE_CHAIN + "\n", "- " + DE_CHAIN + "\n"):
            with self.subTest(text=text):
                self.assertNotIn("ZH_DE_STACK", codes(analyze_text(text)))


# --------------------------------------------------------------------------
# 3. ZH_POSTPOSED_CONDITION
# --------------------------------------------------------------------------

class TestZhPostposedCondition(unittest.TestCase):
    def test_postposed_condition_reports(self):
        result = analyze_text(POST_COND)
        self.assertIn("ZH_POSTPOSED_CONDITION", codes(result))

    def test_preposed_condition_negative(self):
        result = analyze_text(PRE_COND)
        self.assertNotIn("ZH_POSTPOSED_CONDITION", codes(result))

    def test_ruo_marker_reports(self):
        result = analyze_text(POST_RUO)
        self.assertIn("ZH_POSTPOSED_CONDITION", codes(result))

    def test_ruogan_is_not_a_condition(self):
        result = analyze_text(POST_RUOGAN)
        self.assertNotIn("ZH_POSTPOSED_CONDITION", codes(result))

    def test_tangruo_and_yidan_markers(self):
        for text in (POST_TANG, POST_YIDAN):
            with self.subTest(text=text):
                self.assertIn("ZH_POSTPOSED_CONDITION",
                              codes(analyze_text(text)))


# --------------------------------------------------------------------------
# 4. ZH_DUE_TO_MAKE
# --------------------------------------------------------------------------

class TestZhDueToMake(unittest.TestCase):
    def test_due_to_make_reports_missing_subject(self):
        result = analyze_text(DUE_MAKE_1)
        found = findings(result, "ZH_DUE_TO_MAKE")
        self.assertEqual(len(found), 1)
        self.assertIn("缺主", found[0].suggestion)

    def test_because_make_reports(self):
        result = analyze_text(DUE_MAKE_2)
        self.assertIn("ZH_DUE_TO_MAKE", codes(result))

    def test_plain_causal_negative(self):
        result = analyze_text(DUE_OK)
        self.assertNotIn("ZH_DUE_TO_MAKE", codes(result))

    def test_make_without_prep_negative(self):
        result = analyze_text(DUE_NO_PREP)
        self.assertNotIn("ZH_DUE_TO_MAKE", codes(result))

    def test_cross_sentence_negative(self):
        result = analyze_text(DUE_CROSS)
        self.assertNotIn("ZH_DUE_TO_MAKE", codes(result))


# --------------------------------------------------------------------------
# 5. WORDINESS_BLOAT
# --------------------------------------------------------------------------

class TestWordinessBloat(unittest.TestCase):
    def test_due_to_the_fact_that(self):
        result = analyze_text(BLOAT_BECAUSE)
        found = findings(result, "WORDINESS_BLOAT")
        self.assertEqual(len(found), 1)
        self.assertIn("because", found[0].suggestion)

    def test_at_this_point_in_time(self):
        result = analyze_text(BLOAT_NOW)
        self.assertIn("now", findings(result, "WORDINESS_BLOAT")[0].suggestion)

    def test_in_spite_of_the_fact_that(self):
        result = analyze_text(BLOAT_ALTHOUGH)
        self.assertIn("although",
                      findings(result, "WORDINESS_BLOAT")[0].suggestion)

    def test_in_the_event_that(self):
        result = analyze_text(BLOAT_IF)
        self.assertIn("if", findings(result, "WORDINESS_BLOAT")[0].suggestion)

    def test_on_account_of_the_fact_that(self):
        result = analyze_text(BLOAT_ACCOUNT)
        self.assertIn("because",
                      findings(result, "WORDINESS_BLOAT")[0].suggestion)

    def test_tier_b_phrase_negative(self):
        result = analyze_text(BLOAT_TIER_B)
        self.assertNotIn("WORDINESS_BLOAT", codes(result))

    def test_case_insensitive(self):
        result = analyze_text(BLOAT_CASE)
        self.assertIn("WORDINESS_BLOAT", codes(result))


# --------------------------------------------------------------------------
# 6. EMPTY_ADJECTIVE 的「显著」修复
# --------------------------------------------------------------------------

class TestSignificantNotEmpty(unittest.TestCase):
    def test_bare_significant_not_reported(self):
        result = analyze_text(SIGNIFICANT_BARE)
        self.assertNotIn("EMPTY_ADJECTIVE", codes(result))

    def test_statistical_term_not_reported(self):
        result = analyze_text(SIGNIFICANT_TERM)
        self.assertNotIn("EMPTY_ADJECTIVE", codes(result))

    def test_significant_difference_phrase_not_reported(self):
        result = analyze_text(SIGNIFICANT_PHRASE)
        self.assertNotIn("EMPTY_ADJECTIVE", codes(result))

    def test_other_empty_adjective_still_reported(self):
        result = analyze_text(EMPTY_STILL)
        self.assertIn("EMPTY_ADJECTIVE", codes(result))

    def test_config_drops_word_and_keeps_chinese_exemptions(self):
        loaded, _path = load_style_rules(ROOT)
        empty = loaded["empty_adjectives"]
        self.assertNotIn("显著", empty["chinese"])
        for phrase in ("统计显著", "显著差异", "显著性", "显著水平",
                       "显著优于", "显著低于", "显著提高", "不显著"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, empty["exempt_phrases"])


# --------------------------------------------------------------------------
# 7. 注册面与处方
# --------------------------------------------------------------------------

class TestRegistrationAndPrescriptions(unittest.TestCase):
    def test_metrics_and_thresholds_registered(self):
        loaded, _path = load_style_rules(ROOT)
        for key in ("light_verb_nominalization", "wordiness_bloat",
                    "zh_de_stack", "zh_de_stack_max_gap",
                    "zh_postposed_condition", "zh_due_to_make"):
            with self.subTest(key=key):
                self.assertIn(key, loaded["thresholds"])

    def test_unbury_the_verb_targets_light_verb(self):
        found = prescriptions_for("LIGHT_VERB_NOMINALIZATION")
        self.assertEqual([p.name for p in found], ["unbury-the-verb"])

    def test_cut_the_de_targets_de_stack(self):
        found = prescriptions_for("ZH_DE_STACK")
        self.assertEqual([p.name for p in found], ["cut-the-de"])


if __name__ == "__main__":
    unittest.main()
