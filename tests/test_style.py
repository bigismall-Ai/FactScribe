# -*- coding: utf-8 -*-
"""批 64：文风闸 `factscribe style` 的判据测试（全离线）。

覆盖 8 个指标各 1 正 1 负、阈值可配、正常学术段落零误伤、中文支持、
CLI 退出码/JSON/--prompt 长度上限。

定位：style 只出黄牌（exit 3），不阻断、不改正文；它不评估、也不试图规避
任何 AI 检测器。
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
from factscribe.style import (REPORT_ONLY_PROMPT, analyze, build_prompt,  # noqa: E402
                              load_style_rules, prose_of, units_of,
                              _sentences)

PROJECT_TOML = """[project]
title = "t"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""


def make_project(tmp, body: str, rules: str | None = None) -> Path:
    root = Path(tmp)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections" / "01_main.tex").write_text(body, encoding="utf-8")
    (root / "paperkit.toml").write_text(PROJECT_TOML, encoding="utf-8")
    if rules is not None:
        (root / "style-rules.toml").write_text(rules, encoding="utf-8")
    return root


def run_style(root: Path, *args: str, json_out: bool = False):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", "style", str(root), *args]
    if json_out:
        cmd.append("--json")
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


def analyze_text(tmp, body: str, rules: str | None = None):
    root = make_project(tmp, body, rules)
    cfg = load_config(root)
    loaded, path = load_style_rules(root)
    return analyze(cfg, load_sections(cfg), loaded, rules_path=path)


def codes(result) -> set:
    return {f.code for f in result.findings}


# --------------------------------------------------------------------------
# 各指标 1 正 1 负
# --------------------------------------------------------------------------

CONNECTIVE_POS = (
    "Moreover, the first run finished on time and produced a stable log for the team.\n\n"
    "Furthermore, the second run finished early and produced a clean log for review.\n\n"
    "Additionally, the third run finished late but still produced a readable log.\n\n"
    "In addition, the fourth run finished on schedule and kept every record intact.\n\n"
    "Moreover, the fifth run added a short note about the local disk and its free space.\n\n"
    "Furthermore, the sixth run closed the loop with a clear table of measured values.\n"
)
CONNECTIVE_NEG = (
    "The first run finished on time and produced a stable log for the team.\n\n"
    "The second run finished early and produced a clean log for review.\n\n"
    "The third run finished late but still produced a readable log.\n\n"
    "The fourth run finished on schedule and kept every record intact.\n\n"
    "The fifth run added a short note about the local disk and its free space.\n\n"
    "The sixth run closed the loop with a clear table of measured values.\n"
)

UNIFORM_POS = "This sentence has exactly ten words in it. " * 12
UNIFORM_NEG = (
    "Short run. "
    "The first experiment ran for forty-one minutes on a single node while every request was logged. "
    "It failed. "
    "A second pass reused the same inputs, changed only the provider key, and produced a very different tail latency profile. "
    "We stopped. "
    "The third pass then measured memory, disk, and network use under the same load for two hours. "
    "Noise. "
    "After that we repeated the whole sequence on a second machine with a slower disk and a warmer cache. "
    "Done. "
    "The logs are in the appendix and the raw numbers are in the shared ledger for this batch. "
    "End."
)

ADJ_POS = (
    "This is a crucial step for the pipeline.\n\n"
    "That is a robust method for the workload.\n\n"
    "This is a comprehensive study of the problem.\n\n"
    "That is a significant result for the field.\n\n"
    "This is an essential part of the system.\n\n"
    "That is a vital point for the design.\n"
)
ADJ_NEG = (
    "The pipeline reads one file at a time and writes a single patch.\n\n"
    "The method uses the same inputs as the baseline and reports every failure.\n\n"
    "The study covers sixteen tasks and reports both denominators.\n\n"
    "The result holds on the subset and the raw log is in the appendix.\n\n"
    "The system keeps one copy of the payload and checks its hash at turn end.\n\n"
    "The design puts the rule in a typed section with a declared budget.\n"
)

TRIAD_POS = (
    "We compare alpha, beta, and gamma on the same task.\n\n"
    "We test red, green, and blue under the same load.\n\n"
    "We report one, two, and three in the main table.\n\n"
    "We measure width, height, and depth for each sample.\n\n"
    "We log input, output, and cache counts for every call.\n"
)
TRIAD_NEG = (
    "We compare alpha with beta on the same task.\n\n"
    "We test red and green under the same load.\n\n"
    "We report one and two in the main table.\n\n"
    "We measure width and height for each sample.\n\n"
    "We log input and output counts for every call.\n"
)

PARA_POS = (
    "We ran the first test on the main machine and recorded every result in the shared ledger, "
    "where each row names the task, the arm, the token count, and the wall time.\n\n"
    "Therefore, the method is better than the baseline on this task set, and the margin survives "
    "a change of model in the same budget.\n\n"
    "Overall, the arm wins on every bucket in this comparison, and the raw counts are in the "
    "appendix for anyone who wants to recompute the rates.\n"
)
PARA_NEG = (
    "We ran the first test on the main machine and recorded every result in the shared ledger.\n\n"
    "We ran the second test on the same machine and wrote the output to a separate file.\n\n"
    "The method beat the baseline on this task set by five instances out of sixteen.\n\n"
    "We ran the third test and the numbers were stable across all repetitions.\n\n"
    "The arm wins on every bucket in this comparison, with two instances in the hardest bucket.\n"
)

HEDGE_POS = (
    "The gap may potentially come from provider latency rather than from the arm.\n\n"
    "We ran the same six tasks twice and kept every request body for replay.\n\n"
    "The logs are complete and the raw counts are in the shared ledger.\n"
)
HEDGE_NEG = (
    "The gap may come from provider latency rather than from the arm.\n\n"
    "We ran the same six tasks twice and kept every request body for replay.\n\n"
    "The logs are complete and the raw counts are in the shared ledger.\n"
)

OPENER_POS = (
    "Assembly improves the result on every task in the benchmark, and the margin survives a change of model.\n\n"
    "Assembly cuts the cost on the easy bucket and keeps the same accuracy, which we report in a separate table.\n\n"
    "Assembly raises accuracy on the middle bucket and lowers it on the hard one, so we report both buckets.\n"
)
OPENER_NEG = (
    "Assembly improves the result on every task in the benchmark, and the margin survives a change of model.\n\n"
    "The cost falls on the easy bucket while accuracy stays the same, which we report in a separate table.\n\n"
    "Results on the middle bucket are mixed, so we report both buckets instead of one average.\n"
)

EXTREME_POS = (
    "We compare the first method with the second method and the third method against the "
    "fourth method and the fifth method on the same task set with the same inputs and the same "
    "budget, and we then repeat every comparison on a second machine with a slower disk and a "
    "warmer cache, and we record the wall time and the peak memory and the cache size for every "
    "single run in a shared ledger, and we report the median of five repetitions for each method "
    "and each bucket and each machine."
)
# 又长又有结构（从句/分号/破折号/括号）：专家写法，不该报
EXTREME_STRUCTURED = (
    "We compare the first method with the second method and the third method against the fourth "
    "method, which is slower than the fifth method, while the sixth method is faster; and the "
    "seventh method is stable under load (measured twice on the same machine), so the comparison "
    "is informative but not conclusive in this setting, and we therefore report exact counts "
    "instead of a single average for the whole task set."
)
EXTREME_NEG = (
    "We compare the first method with the second method on the same task and report every "
    "failure in the appendix, where the raw logs are kept for replay."
)

# 句长节奏平台：正例四句都落在 10–19 词区间；负例中间一句跳出该区间
PLATEAU_POS = (
    "The first run finished on time and kept every record in the shared ledger.\n"
    "The second run finished early and wrote the output to a separate file.\n"
    "The third run finished late and left a clear table of measured values.\n"
    "The fourth run closed the loop and saved the raw log for replay."
)
PLATEAU_NEG = (
    "The first run finished on time and kept every record in the shared ledger.\n"
    "The second run finished early and wrote the output to a separate file.\n"
    "The third run finished late and left a clear table of measured values on the shared disk "
    "for review by the whole team after the batch closed.\n"
    "The fourth run closed the loop and saved the raw log for replay."
)

# 句长分布极端散：一半 2 词、一半 80+ 词，CV > 0.80（散不是 AI 特征，不报）
_LONG_A = (
    "The first experiment ran for forty-one minutes on a single node while every request was "
    "logged and the second pass reused the same inputs and changed only the provider key and "
    "produced a very different tail latency profile under the same load and the same budget and "
    "the same cache state for two hours and then we repeated the whole sequence on a second "
    "machine with a slower disk and a warmer cache and a different kernel and recorded every "
    "request body for replay in the shared ledger for this batch of runs."
)
_LONG_B = (
    "A third pass measured memory and disk and network use under the same load and the same "
    "budget and the same cache state for two hours and then we repeated the whole sequence on a "
    "third machine with a slower disk and a warmer cache and a different kernel and recorded "
    "every request body for replay in the shared ledger for this batch of runs and kept the raw "
    "logs as well for anyone who wants to recompute."
)
UNIFORM_SPREAD = " ".join([
    "Short run.", _LONG_A, "It failed.", _LONG_B, "We stopped.", _LONG_A,
    "Noise.", _LONG_B, "End.", _LONG_A,
])
# 健康区间内的正常起伏（CV ≈ 0.50）
UNIFORM_MID = (
    "The run finished on time. "
    "The first experiment ran for forty-one minutes on a single node while every request was "
    "logged and the provider key stayed fixed. "
    "It failed at the end of the second hour. "
    "A second pass reused the same inputs and produced a very different tail latency profile. "
    "We stopped the pass. "
    "The third pass measured memory and disk use under the same load for two hours and reported "
    "the median. "
    "The numbers were stable across five repetitions of the whole sequence. "
    "After that we repeated the sequence on a second machine with a slower disk. "
    "The gap between the two machines was small and the raw logs are in the appendix. "
    "We report exact counts for every bucket instead of one average. "
    "The result holds."
)

NORMAL_1 = (
    "The experiment ran on a single node for 41 minutes.\n"
    "We measured wall time and peak memory for each task, and the raw logs are in the appendix.\n"
    "Wall time varied between 38 and 44 minutes across runs.\n"
    "The variance came from provider latency rather than from the system under test.\n"
    "We report the median of five repetitions.\n"
)
NORMAL_2 = (
    "Table 2 lists the per-task results.\n"
    "Three tasks failed in both arms, and the failures trace to missing system packages rather than to the patch.\n"
    "The remaining thirteen tasks show a clear improvement: assembly resolved ten and the baseline resolved five.\n"
    "That gap is larger than the difference reported in the pilot, which used six tasks and a different mix of difficulty.\n"
)
NORMAL_3 = (
    "Two limitations deserve mention.\n"
    "The sample is small, so the interval around each rate is wide.\n"
    "We report exact counts instead of rates where the denominator is below twenty, because a percentage over five cases hides the raw number.\n"
    "A larger replication with a frozen model version is left for future work.\n"
)


class TestMetrics(unittest.TestCase):
    def test_connective_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, CONNECTIVE_POS)
        self.assertIn("CONNECTIVE_DENSITY", codes(result))
        self.assertGreater(result.metrics["connective_density"], 8)
        hit = next(f for f in result.findings if f.code == "CONNECTIVE_DENSITY")
        self.assertIn("Moreover", hit.suggestion)
        self.assertIn("删去", hit.suggestion)

    def test_connective_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, CONNECTIVE_NEG)
        self.assertNotIn("CONNECTIVE_DENSITY", codes(result))
        self.assertEqual(result.metrics["connective_density"], 0.0)

    def test_uniformity_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, UNIFORM_POS)
        self.assertIn("SENTENCE_UNIFORMITY", codes(result))
        self.assertLess(result.metrics["sentence_uniformity"], 0.45)
        hit = next(f for f in result.findings if f.code == "SENTENCE_UNIFORMITY")
        self.assertIn("CV", hit.text)

    def test_uniformity_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, UNIFORM_NEG)
        self.assertNotIn("SENTENCE_UNIFORMITY", codes(result))
        self.assertGreaterEqual(result.metrics["sentence_uniformity"], 0.45)

    def test_uniformity_mid_range_not_reported(self):
        """健康区间 [0.45, 0.80] 内的正常起伏不报。"""
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, UNIFORM_MID)
        cv = result.metrics["sentence_uniformity"]
        self.assertGreaterEqual(cv, 0.45)
        self.assertLessEqual(cv, 0.80)
        self.assertNotIn("SENTENCE_UNIFORMITY", codes(result))

    def test_uniformity_high_end_not_reported(self):
        """CV > 0.80 是散，散不是 AI 特征：不报。"""
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, UNIFORM_SPREAD)
        self.assertGreater(result.metrics["sentence_uniformity"], 0.80)
        self.assertNotIn("SENTENCE_UNIFORMITY", codes(result))

    def test_empty_adjective_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ADJ_POS)
        self.assertIn("EMPTY_ADJECTIVE", codes(result))
        self.assertGreater(result.metrics["empty_adjective"], 6)
        hit = next(f for f in result.findings if f.code == "EMPTY_ADJECTIVE")
        self.assertIn("crucial", hit.suggestion)
        self.assertIn("可核验", hit.suggestion)

    def test_empty_adjective_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ADJ_NEG)
        self.assertNotIn("EMPTY_ADJECTIVE", codes(result))
        self.assertEqual(result.metrics["empty_adjective"], 0.0)

    def test_colloquial_triad_positive(self):
        body = (
            "首先，我们固定任务集与预算，再记录每臂的耗时与失败数。"
            "其次，我们把每一轮的原始日志完整留档。最后，我们把对照结果写进共享账本。\n\n"
            "首先，我们固定数据切分与随机种子，再重跑一遍基线。"
            "其次，我们保存每一轮的原始输出与堆栈。最后，我们把两臂的差值记进同一本账。\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, body)
        self.assertIn("COLLOQUIAL_TRIAD", codes(result))
        self.assertGreaterEqual(result.metrics["colloquial_triad"], 2)
        hit = next(f for f in result.findings if f.code == "COLLOQUIAL_TRIAD")
        self.assertIn("相邻段落", hit.suggestion)

    def test_colloquial_triad_negative(self):
        body = ("We compare alpha, beta, and gamma on the same task under the same load "
                "and report every failure in the appendix for replay.\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, body)
        self.assertNotIn("COLLOQUIAL_TRIAD", codes(result))

    def test_paragraph_template_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, PARA_POS)
        self.assertIn("PARAGRAPH_TEMPLATE", codes(result))
        self.assertGreater(result.metrics["paragraph_template"], 0.5)
        hit = next(f for f in result.findings if f.code == "PARAGRAPH_TEMPLATE")
        self.assertIn("套话", hit.suggestion)
        flagged = [p for p in result.paragraphs if "PARAGRAPH_TEMPLATE" in p.flags]
        self.assertEqual(len(flagged), 2)

    def test_paragraph_template_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, PARA_NEG)
        self.assertNotIn("PARAGRAPH_TEMPLATE", codes(result))
        self.assertEqual(result.metrics["paragraph_template"], 0.0)

    def test_hedge_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, HEDGE_POS)
        self.assertIn("HEDGE_STACK", codes(result))
        self.assertEqual(result.metrics["hedge_stack"], 1)
        hit = next(f for f in result.findings if f.code == "HEDGE_STACK")
        self.assertIn("一层", hit.suggestion)
        self.assertIn("may", hit.suggestion)

    def test_hedge_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, HEDGE_NEG)
        self.assertNotIn("HEDGE_STACK", codes(result))
        self.assertEqual(result.metrics["hedge_stack"], 0)

    def test_repeated_opener_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, OPENER_POS)
        self.assertIn("REPEATED_OPENER", codes(result))
        self.assertGreaterEqual(result.metrics["repeated_opener"], 2)
        hit = next(f for f in result.findings if f.code == "REPEATED_OPENER")
        self.assertIn("上一段", hit.suggestion)

    def test_repeated_opener_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, OPENER_NEG)
        self.assertNotIn("REPEATED_OPENER", codes(result))
        self.assertEqual(result.metrics["repeated_opener"], 0)

    def test_sentence_length_extreme_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, EXTREME_POS)
        self.assertIn("SENTENCE_LENGTH_EXTREME", codes(result))
        self.assertEqual(result.metrics["sentence_length_extreme"], 1)
        hit = next(f for f in result.findings if f.code == "SENTENCE_LENGTH_EXTREME")
        self.assertIn("保留", hit.suggestion)
        self.assertIn("换气", hit.suggestion)
        self.assertNotIn("断成两句", hit.suggestion)

    def test_sentence_length_extreme_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, EXTREME_NEG)
        self.assertNotIn("SENTENCE_LENGTH_EXTREME", codes(result))
        self.assertEqual(result.metrics["sentence_length_extreme"], 0)

    def test_long_structured_sentence_not_reported(self):
        """长而有结构（从句/分号/括号）的长句是专家写法，不报。"""
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, EXTREME_STRUCTURED)
        self.assertNotIn("SENTENCE_LENGTH_EXTREME", codes(result))
        self.assertEqual(result.metrics["sentence_length_extreme"], 0)

    def test_rhythm_plateau_positive(self):
        # 批 109：默认 info 只作参考；旧黄牌行为由配置恢复。
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, PLATEAU_POS,
                                  'rhythm_plateau_level = "yellow"\n')
        self.assertIn("RHYTHM_PLATEAU", codes(result))
        self.assertEqual(result.metrics["rhythm_plateau"], 1)
        hit = next(f for f in result.findings if f.code == "RHYTHM_PLATEAU")
        self.assertIn("短句", hit.suggestion)
        self.assertIn("合并", hit.suggestion)

    def test_rhythm_plateau_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, PLATEAU_NEG)
        self.assertNotIn("RHYTHM_PLATEAU", codes(result))
        self.assertEqual(result.metrics["rhythm_plateau"], 0)


class TestThresholdsAndLang(unittest.TestCase):
    def test_threshold_override_changes_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = analyze_text(tmp, CONNECTIVE_POS)
        self.assertIn("CONNECTIVE_DENSITY", codes(base))
        with tempfile.TemporaryDirectory() as tmp:
            rules = "[thresholds]\nconnective_density = 1000.0\n"
            raised = analyze_text(tmp, CONNECTIVE_POS, rules)
        self.assertNotIn("CONNECTIVE_DENSITY", codes(raised))
        self.assertNotIn("CONNECTIVE_DENSITY", {f["code"] for f in raised.fired})

    def test_threshold_override_disables_colloquial_triad(self):
        body = (
            "首先，我们固定任务集与预算，再记录每臂的耗时与失败数。"
            "其次，我们把每一轮的原始日志完整留档。最后，我们把对照结果写进共享账本。\n\n"
            "首先，我们固定数据切分与随机种子，再重跑一遍基线。"
            "其次，我们保存每一轮的原始输出与堆栈。最后，我们把两臂的差值记进同一本账。\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = analyze_text(tmp, body)
        self.assertIn("COLLOQUIAL_TRIAD", codes(base))
        with tempfile.TemporaryDirectory() as tmp:
            rules = "[thresholds]\ncolloquial_triad_repeats = 99\n"
            result = analyze_text(tmp, body, rules)
        self.assertNotIn("COLLOQUIAL_TRIAD", codes(result))
        self.assertNotIn("COLLOQUIAL_TRIAD", {f["code"] for f in result.fired})

    def test_chinese_metrics(self):
        body = (
            "此外，这个方法在多数任务上都能稳定复现。\n\n"
            "首先，我们记录每次运行的耗时，并把结果写进共享账本。\n\n"
            "其次，我们把每一单的原始日志都保留下来，供后续复核使用。\n\n"
            "综上所述，这一节给出的结论只覆盖当前任务集，不能外推到其他模型或其他预算。\n\n"
            "这个结论至关重要，而且它看起来可能会在更长的运行中发生变化，所以我们把全部原始数据都留在附录里，"
            "让读者能够自己重新计算每一个数字而不是只看我们给出的汇总比例，每一个表格与每一处引用也都能追溯到原始记录。\n\n"
            "这项工作提供了全面的分析，也做了深入的讨论，读者可以据此复核每一个实验设置与数据口径。\n\n"
            "我们比较甲、乙、丙三种做法，并逐一报告它们的结果。\n\n"
            "我们在第一台机器上运行第一个方法，记录每次调用的输入、输出与时延，在第二台机器上运行第二个方法，"
            "记录每次调用的输入、输出与时延，在第三台机器上运行第三个方法，记录每次调用的输入、输出与时延，"
            "最后把所有原始记录整理成一张表放进附录，让读者能逐项复算每一个数字与每一处设置。\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, body)
        self.assertIn("CONNECTIVE_DENSITY", codes(result))
        self.assertIn("EMPTY_ADJECTIVE", codes(result))
        self.assertIn("HEDGE_STACK", codes(result))
        self.assertIn("SENTENCE_LENGTH_EXTREME", codes(result))


class TestNoFalsePositive(unittest.TestCase):
    def test_three_normal_academic_paragraphs(self):
        body = NORMAL_1 + "\n\n" + NORMAL_2 + "\n\n" + NORMAL_3
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, body)
        self.assertEqual(result.findings, [], msg=str([f.as_dict() for f in result.findings]))
        self.assertEqual(result.fired, [])
        self.assertEqual(result.exit_code, 0)

    def test_prose_extraction_strips_math_and_citations(self):
        tex = ("We compare $x, y, and z$ on 16 tasks \\citep{a2024} and report the "
               "median in Table~\\ref{tab:x}. The result is stable across runs.\n")
        prose = prose_of(tex)
        self.assertNotIn("citep", prose)
        self.assertNotIn("ref", prose)
        self.assertIn("median", prose)
        self.assertIn("The result is stable", prose)


class TestEscapedDollarParsing(unittest.TestCase):
    """批 71：`\\$` 是字面美元符号，不是数学模式起点。

    修复前，正文里一个 `\\$0.05` 会把后面整段吞进数学模式，词数/句数/句长
    统计系统性偏低。这里正例两条（字面美元、成对转义美元）、负例两条
    （真数学仍要遮罩；`\\(...\\)` 与 `\\[...\\]` 对称处理）。
    """

    def test_escaped_dollar_keeps_number_and_following_text(self):
        tex = ("The price is \\$100 for 5 tasks. "
               "The follow-up sentence has 7 words and stays here.\n")
        prose = prose_of(tex)
        self.assertIn("$100 for 5 tasks", prose)
        self.assertIn("follow-up sentence has 7 words", prose)
        self.assertEqual(len(_sentences(prose)), 2)
        # 转义美元只是去掉反斜杠，不改变任何计数单元
        self.assertEqual(units_of(prose), units_of(tex.replace("\\$", "$")))

    def test_escaped_dollar_pair_is_not_math(self):
        tex = ("The variable costs \\$x\\$ and 42 tasks remain. "
               "The tail sentence is intact.\n")
        prose = prose_of(tex)
        self.assertIn("$x$ and 42 tasks remain", prose)
        self.assertIn("tail sentence is intact", prose)
        self.assertEqual(len(_sentences(prose)), 2)
        self.assertEqual(units_of(prose), units_of(tex.replace("\\$", "$")))

    def test_real_inline_math_still_masked_after_escaped_dollar(self):
        tex = ("The price is \\$100 and the formula $a+b$ is masked. "
               "This tail stays.\n")
        prose = prose_of(tex)
        self.assertIn("$100", prose)
        self.assertNotIn("a+b", prose)
        self.assertIn("is masked", prose)
        self.assertIn("This tail stays", prose)
        self.assertEqual(len(_sentences(prose)), 2)

    def test_paren_and_bracket_math_symmetric(self):
        tex = ("Inline \\(x+1\\) math and 7 tasks. "
               "Display \\[y=2\\] math and 8 tasks. "
               "A line break \\\\[2pt] keeps the tail.\n")
        prose = prose_of(tex)
        self.assertNotIn("x+1", prose)
        self.assertNotIn("y=2", prose)
        for kept in ("math and 7 tasks", "math and 8 tasks",
                     "A line break", "keeps the tail"):
            self.assertIn(kept, prose)
        self.assertEqual(len(_sentences(prose)), 3)
        # \\[2pt] 是换行命令，不是 \[ 数学起点：后面的 2pt 也不该留下
        self.assertNotIn("2pt", prose)


class TestStageAssessment(unittest.TestCase):
    """判据：triggers>=3 或 cv<0.45 → draft/rewrite；否则 polished/report_only。"""

    def test_many_triggers_is_draft(self):
        body = (
            "Moreover, this is a crucial, robust, and comprehensive method.\n\n"
            "Furthermore, the pipeline is significant, essential, and vital.\n\n"
            "Additionally, we test alpha, beta, and gamma under the same load.\n\n"
            "In addition, we compare red, green, and blue on one machine.\n\n"
            "Overall, the approach delivers a comprehensive, robust gain.\n\n"
            "Moreover, the system provides significant and essential support.\n\n"
            "Furthermore, we measure width, height, and depth for each sample.\n\n"
            "Additionally, the results are crucial and comprehensive.\n\n"
            "In conclusion, the method is essential and significant.\n\n"
            "Overall, we log input, output, and cache counts for every call.\n\n"
            "首先，我们固定任务集与预算，再记录每臂的耗时与失败数。"
            "其次，我们把每一轮的原始日志完整留档。最后，我们把对照结果写进共享账本。\n\n"
            "首先，我们固定数据切分与随机种子，再重跑一遍基线。"
            "其次，我们保存每一轮的原始输出与堆栈。最后，我们把两臂的差值记进同一本账。\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, body)
        stage = result.stage_assessment
        self.assertGreaterEqual(stage["triggers"], 3)
        self.assertEqual(stage["stage"], "draft")
        self.assertEqual(stage["advice"], "rewrite")

    def test_low_cv_is_draft_even_with_few_triggers(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, UNIFORM_POS)
        stage = result.stage_assessment
        self.assertLess(stage["cv"], 0.45)
        self.assertEqual(stage["stage"], "draft")
        self.assertEqual(stage["advice"], "rewrite")

    def test_healthy_polished_is_report_only(self):
        body = NORMAL_1 + "\n\n" + NORMAL_2 + "\n\n" + NORMAL_3
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, body)
        stage = result.stage_assessment
        self.assertLessEqual(stage["triggers"], 2)
        self.assertGreaterEqual(stage["cv"], 0.45)
        self.assertLessEqual(stage["cv"], 0.80)
        self.assertEqual(stage["stage"], "polished")
        self.assertEqual(stage["advice"], "report_only")
        self.assertIn("建议不改", stage["reason"])
        self.assertIn("建议不改", build_prompt(result))

    def test_report_only_prompt_has_no_rewrite_items(self):
        body = NORMAL_1 + "\n\n" + NORMAL_2 + "\n\n" + NORMAL_3
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, body)
        prompt = build_prompt(result)
        self.assertEqual(prompt, REPORT_ONLY_PROMPT)
        self.assertIn("建议不改", prompt)
        for banned in ("→", "逐条", "改法", "替换", "重写", "rewrite"):
            self.assertNotIn(banned, prompt)
        self.assertNotIn("\n1.", prompt)


class TestCLI(unittest.TestCase):
    def test_exit_three_and_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, CONNECTIVE_POS)
            proc = run_style(root, json_out=True)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["tool"], "factscribe")
        self.assertEqual(payload["command"], "style")
        for key in ("metrics", "findings", "paragraphs", "thresholds", "disclaimer",
                    "stage_assessment"):
            self.assertIn(key, payload)
        self.assertEqual(set(payload["stage_assessment"]),
                         {"stage", "advice", "reason", "triggers", "cv"})
        self.assertIn("CONNECTIVE_DENSITY", {f["code"] for f in payload["findings"]})
        self.assertIn("不评估", payload["disclaimer"])
        self.assertIn("规避", payload["disclaimer"])

    def test_clean_project_exits_zero(self):
        body = NORMAL_1 + "\n\n" + NORMAL_2 + "\n\n" + NORMAL_3
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, body)
            proc = run_style(root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[黄] 0 处", proc.stdout)

    def test_prompt_is_short_and_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, CONNECTIVE_POS)
            proc = run_style(root, "--prompt")
        self.assertEqual(proc.returncode, 3, proc.stderr)
        prompt = proc.stdout.strip()
        self.assertLessEqual(len(prompt), 400)
        self.assertIn("不得删数字", prompt)
        self.assertIn("不得删引用", prompt)
        self.assertIn("禁止整段拆短", prompt)
        self.assertIn("RHYTHM_PLATEAU", prompt)
        self.assertIn("→", prompt)

    def test_prompt_json_embeds_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, CONNECTIVE_POS)
            proc = run_style(root, "--prompt", json_out=True)
        payload = json.loads(proc.stdout)
        self.assertIn("prompt", payload)
        self.assertLessEqual(len(payload["prompt"]), 400)
        self.assertEqual(payload["stage_assessment"]["advice"], "rewrite")

    def test_report_only_prompt_cli_is_one_sentence(self):
        body = NORMAL_1 + "\n\n" + NORMAL_2 + "\n\n" + NORMAL_3
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, body)
            proc = run_style(root, "--prompt")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), REPORT_ONLY_PROMPT)
        self.assertEqual(len(proc.stdout.strip().splitlines()), 1)
        self.assertNotIn("→", proc.stdout)

    def test_paragraphs_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, PARA_POS)
            proc = run_style(root, json_out=True)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["paragraphs"])
        for item in payload["paragraphs"]:
            self.assertEqual(set(item), {"file", "line", "words", "flags"})


if __name__ == "__main__":
    unittest.main()
