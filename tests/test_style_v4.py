# -*- coding: utf-8 -*-
"""批 82：文风规则 v4 的判据测试（全离线）。

规则清单见 SPEC-V3.0 §13：DASH_PARENTHETICAL、HEADING_TOO_LONG、
HEADING_MALFORMED、TERM_FIRST_IN_HEADING、RHYTHM_PLATEAU、COLLOQUIAL_TRIAD、
CONNECTIVE_DENSITY、EMPTY_ADJECTIVE、SENTENCE_LENGTH_EXTREME。

每条规则至少 3 例（正例/负例/白名单或豁免例）；另验证阈值来自
style-rules.toml、dash_budget 调大、术语白名单、数值范围/页码/数学环境豁免。
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
from factscribe.style import analyze, load_style_rules  # noqa: E402

PROJECT_TOML = """[project]
title = "t"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""


def make_project(tmp, body: str, rules: str | None = None,
                 extras: dict[str, str] | None = None) -> Path:
    root = Path(tmp)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections" / "01_main.tex").write_text(body, encoding="utf-8")
    (root / "paperkit.toml").write_text(PROJECT_TOML, encoding="utf-8")
    if rules is not None:
        (root / "style-rules.toml").write_text(rules, encoding="utf-8")
    for name, content in (extras or {}).items():
        (root / name).write_text(content, encoding="utf-8")
    return root


def analyze_text(tmp, body: str, rules: str | None = None,
                 extras: dict[str, str] | None = None):
    root = make_project(tmp, body, rules, extras)
    cfg = load_config(root)
    loaded, path = load_style_rules(root)
    return analyze(cfg, load_sections(cfg), loaded, rules_path=path)


def codes(result) -> set:
    return {f.code for f in result.findings}


def run_style(root: Path, *args: str, json_out: bool = False):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", "style", str(root), *args]
    if json_out:
        cmd.append("--json")
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


# --------------------------------------------------------------------------
# 1. DASH_PARENTHETICAL
# --------------------------------------------------------------------------

DASH_POS = (
    "我们提出一个新方法——它只在单机上运行——并报告全部结果与原始日志。\n\n"
    "读者可以按附录里的命令复算每一个数字，以及每一处引用与设置。\n"
)
DASH_NEG = (
    "我们提出一个新方法，它只在单机上运行，并报告全部结果与原始日志。\n\n"
    "读者可以按附录里的命令复算每一个数字，以及每一处引用与设置。\n"
)
DASH_EXEMPT = (
    "The measured range 1--2 and 3—4 both fall inside the reported band, and the reader can check it.\n\n"
    "See pp. 12—15 for the original proof, and the formula $a—b$ is inside math mode.\n\n"
    "The second paragraph is long enough to survive the minimum paragraph filter for this analyser.\n"
)


class TestDashParenthetical(unittest.TestCase):
    def test_positive_reports_each_dash(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, DASH_POS)
        self.assertIn("DASH_PARENTHETICAL", codes(result))
        self.assertGreaterEqual(result.metrics["dash_parenthetical"], 2)
        hit = result.findings[0]
        self.assertEqual(hit.severity, "yellow")
        # 三种改法按优先级给出
        for word in ("逗号", "括号", "拆"):
            self.assertIn(word, hit.suggestion)

    def test_negative_without_dash(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, DASH_NEG)
        self.assertNotIn("DASH_PARENTHETICAL", codes(result))
        self.assertEqual(result.metrics["dash_parenthetical"], 0)

    def test_numeric_range_pages_and_math_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, DASH_EXEMPT)
        self.assertEqual(result.metrics["dash_parenthetical"], 0)
        self.assertNotIn("DASH_PARENTHETICAL", codes(result))

    def test_budget_raises_suppresses_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = analyze_text(tmp, DASH_POS)
        self.assertIn("DASH_PARENTHETICAL", codes(base))
        with tempfile.TemporaryDirectory() as tmp:
            rules = "[thresholds]\ndash_budget = 99\n"
            result = analyze_text(tmp, DASH_POS, rules)
        self.assertNotIn("DASH_PARENTHETICAL", codes(result))
        self.assertEqual(result.metrics["dash_parenthetical"], base.metrics["dash_parenthetical"])


# --------------------------------------------------------------------------
# 2. HEADING_TOO_LONG
# --------------------------------------------------------------------------

HEAD_LONG_EN = (
    "\\section{A Very Long English Heading That Keeps Going And Going}\n"
    "We describe the pipeline in this section with enough words to form a sentence.\n"
)
HEAD_SHORT_EN = (
    "\\section{Method}\n"
    "We describe the pipeline in this section with enough words to form a sentence.\n"
)
HEAD_LONG_ZH = (
    "\\section{这是一个超过十二个字的中文标题示例}\n"
    "本节描述流水线的实现细节，并给出足够的文字形成一句话。\n"
)
TITLE_LONG = (
    "\\title{A Very Long Paper Title That Would Otherwise Trigger The Heading Rule For Sure}\n"
    "\\section{Method}\n"
    "We describe the pipeline in this section with enough words to form a sentence.\n"
)


class TestHeadingTooLong(unittest.TestCase):
    def test_positive_english(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, HEAD_LONG_EN)
        self.assertIn("HEADING_TOO_LONG", codes(result))
        self.assertEqual(result.metrics["heading_too_long"], 1)
        hit = next(f for f in result.findings if f.code == "HEADING_TOO_LONG")
        self.assertIn("8", hit.suggestion)

    def test_positive_chinese(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, HEAD_LONG_ZH)
        self.assertIn("HEADING_TOO_LONG", codes(result))
        self.assertEqual(result.metrics["heading_too_long"], 1)

    def test_negative_short_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, HEAD_SHORT_EN)
        self.assertNotIn("HEADING_TOO_LONG", codes(result))

    def test_title_is_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TITLE_LONG)
        self.assertNotIn("HEADING_TOO_LONG", codes(result))
        self.assertEqual(result.metrics["heading_too_long"], 0)


# --------------------------------------------------------------------------
# 3. HEADING_MALFORMED
# --------------------------------------------------------------------------

HEAD_COLON = (
    "\\section{Results: A New View}\n"
    "We describe the pipeline in this section with enough words to form a sentence.\n"
)
HEAD_PAREN = (
    "\\section{Results (Revisited)}\n"
    "We describe the pipeline in this section with enough words to form a sentence.\n"
)
HEAD_CLEAN = (
    "\\section{Results}\n"
    "We describe the pipeline in this section with enough words to form a sentence.\n"
)
TITLE_COLON = (
    "\\title{A Study: With A Colon In The Paper Title}\n"
    "\\section{Results}\n"
    "We describe the pipeline in this section with enough words to form a sentence.\n"
)


class TestHeadingMalformed(unittest.TestCase):
    def test_positive_colon(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, HEAD_COLON)
        self.assertIn("HEADING_MALFORMED", codes(result))

    def test_positive_parenthetical(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, HEAD_PAREN)
        self.assertIn("HEADING_MALFORMED", codes(result))

    def test_negative_clean_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, HEAD_CLEAN)
        self.assertNotIn("HEADING_MALFORMED", codes(result))

    def test_paper_title_is_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TITLE_COLON)
        self.assertNotIn("HEADING_MALFORMED", codes(result))


# --------------------------------------------------------------------------
# 4. TERM_FIRST_IN_HEADING
# --------------------------------------------------------------------------

TERM_POS = (
    "\\section{Retrieval Augmented}\n"
    "We describe the pipeline in this section with enough words to form a sentence.\n"
)
TERM_DEFINED = (
    "\\section{Retrieval Augmented}\n"
    "Retrieval Augmented generation reduces the cost in this section by a clear margin.\n"
)
TERM_ZH_POS = (
    "\\section{稀疏检索增强}\n"
    "我们描述流水线的实现细节，并给出足够的文字形成一句话。\n"
)
# 批 94 起 TERM_FIRST_IN_HEADING 只判在册术语；夹具术语由项目词表登记。
TERM_GLOSSARY = (
    "canonical\taliases(en)\taliases(cn)\tcategory\n"
    "Retrieval Augmented\tretrieval augmented\t\t写作\n"
    "稀疏检索增强\tsparse retrieval augmentation\t\t写作\n"
)


class TestTermFirstInHeading(unittest.TestCase):
    def test_positive_english_term(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TERM_POS,
                                  extras={"glossary.tsv": TERM_GLOSSARY})
        self.assertIn("TERM_FIRST_IN_HEADING", codes(result))

    def test_negative_term_defined_in_first_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TERM_DEFINED,
                                  extras={"glossary.tsv": TERM_GLOSSARY})
        self.assertNotIn("TERM_FIRST_IN_HEADING", codes(result))

    def test_whitelist_term_allow_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(
                tmp, TERM_POS,
                'term_allow_files = ["term-allow.txt"]\n',
                {"term-allow.txt": "# user maintained\n\n  retrieval augmented  \n",
                 "glossary.tsv": TERM_GLOSSARY})
        self.assertNotIn("TERM_FIRST_IN_HEADING", codes(result))

    def test_whitelist_glossary(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(
                tmp, TERM_POS,
                extras={"GLOSSARY.md": "# Terms\n\nRetrieval Augmented\n",
                        "glossary.tsv": TERM_GLOSSARY})
        self.assertNotIn("TERM_FIRST_IN_HEADING", codes(result))

    def test_chinese_term_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TERM_ZH_POS,
                                  extras={"glossary.tsv": TERM_GLOSSARY})
        self.assertIn("TERM_FIRST_IN_HEADING", codes(result))


# --------------------------------------------------------------------------
# 5. RHYTHM_PLATEAU
# --------------------------------------------------------------------------

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
PLATEAU_EXEMPT = (
    "Short run.\n"
    "The first run finished on time and kept every record in the shared ledger for the team.\n"
    "It failed.\n"
    "The second run finished early and wrote the output to a separate file for review by all.\n"
)


class TestRhythmPlateau(unittest.TestCase):
    def test_positive(self):
        # 批 109：默认 info；要黄牌需把 rhythm_plateau_level 设为 yellow。
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, PLATEAU_POS,
                                  'rhythm_plateau_level = "yellow"\n')
        self.assertIn("RHYTHM_PLATEAU", codes(result))

    def test_negative_length_break(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, PLATEAU_NEG)
        self.assertNotIn("RHYTHM_PLATEAU", codes(result))

    def test_negative_short_sentences_interrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, PLATEAU_EXEMPT)
        self.assertNotIn("RHYTHM_PLATEAU", codes(result))


# --------------------------------------------------------------------------
# 6. COLLOQUIAL_TRIAD
# --------------------------------------------------------------------------

TRIAD_POS = (
    "Under the same load and the same budget, we test alpha, beta, and gamma on every bucket.\n\n"
    "With the same inputs and the same machine, we compare red, green, and blue across both buckets.\n"
)
TRIAD_SINGLE = (
    "Under the same load and the same budget, we test alpha, beta, and gamma on every bucket.\n\n"
    "The run finished on time and the logs stayed complete for every request in the batch.\n"
)
TRIAD_NONADJACENT = (
    "Under the same load and the same budget, we test alpha, beta, and gamma on every bucket.\n\n"
    "The run finished on time and the logs stayed complete for every request in the batch.\n\n"
    "With the same inputs and the same machine, we compare red, green, and blue across both buckets.\n"
)
TRIAD_DIFFERENT_SHAPE = (
    "Under the same load and the same budget, we test alpha, beta, and gamma on every bucket.\n\n"
    "With the same inputs and the same machine, we compare the first model, the second model, "
    "and the third model across both buckets.\n"
)


class TestColloquialTriad(unittest.TestCase):
    def test_positive_adjacent_same_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TRIAD_POS)
        self.assertIn("COLLOQUIAL_TRIAD", codes(result))
        self.assertGreaterEqual(result.metrics["colloquial_triad"], 2)

    def test_negative_single_triad(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TRIAD_SINGLE)
        self.assertNotIn("COLLOQUIAL_TRIAD", codes(result))

    def test_negative_non_adjacent(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TRIAD_NONADJACENT)
        self.assertNotIn("COLLOQUIAL_TRIAD", codes(result))

    def test_negative_different_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, TRIAD_DIFFERENT_SHAPE)
        self.assertNotIn("COLLOQUIAL_TRIAD", codes(result))


# --------------------------------------------------------------------------
# 7. CONNECTIVE_DENSITY
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
CONNECTIVE_EXEMPT = (
    "The overall accuracy stayed stable across every run and every bucket in this study.\n\n"
    "The pipeline reads one file at a time and writes a single patch to the main tree.\n"
)


class TestConnectiveDensity(unittest.TestCase):
    def test_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, CONNECTIVE_POS)
        self.assertIn("CONNECTIVE_DENSITY", codes(result))

    def test_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, CONNECTIVE_NEG)
        self.assertNotIn("CONNECTIVE_DENSITY", codes(result))

    def test_inline_overall_accuracy_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, CONNECTIVE_EXEMPT)
        self.assertNotIn("CONNECTIVE_DENSITY", codes(result))

    def test_threshold_from_toml_changes_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = analyze_text(tmp, CONNECTIVE_POS)
        self.assertIn("CONNECTIVE_DENSITY", codes(base))
        with tempfile.TemporaryDirectory() as tmp:
            raised = analyze_text(tmp, CONNECTIVE_POS,
                                  "[thresholds]\nconnective_density = 1000.0\n")
        self.assertNotIn("CONNECTIVE_DENSITY", codes(raised))


# --------------------------------------------------------------------------
# 8. EMPTY_ADJECTIVE
# --------------------------------------------------------------------------

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
ADJ_EXEMPT = (
    "The gain is statistically significant under the same load and the same budget.\n\n"
    "The estimate is statistically significant across every bucket in this study.\n\n"
    "The difference is statistically significant on the held-out split as well.\n"
)


class TestEmptyAdjective(unittest.TestCase):
    def test_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ADJ_POS)
        self.assertIn("EMPTY_ADJECTIVE", codes(result))

    def test_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ADJ_NEG)
        self.assertNotIn("EMPTY_ADJECTIVE", codes(result))

    def test_exempt_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, ADJ_EXEMPT)
        self.assertNotIn("EMPTY_ADJECTIVE", codes(result))
        self.assertEqual(result.metrics["empty_adjective"], 0.0)


# --------------------------------------------------------------------------
# 9. SENTENCE_LENGTH_EXTREME
# --------------------------------------------------------------------------

EXTREME_POS = (
    "We compare the first method with the second method and the third method against the "
    "fourth method and the fifth method on the same task set with the same inputs and the same "
    "budget, and we then repeat every comparison on a second machine with a slower disk and a "
    "warmer cache, and we record the wall time and the peak memory and the cache size for every "
    "single run in a shared ledger, and we report the median of five repetitions for each method "
    "and each bucket and each machine."
)
EXTREME_STRUCTURED = (
    "We compare the first method with the second method and the third method against the fourth "
    "method, which is slower than the fifth method, while the sixth method is faster; and the "
    "seventh method is stable under load (measured twice on the same machine), so the comparison "
    "is informative but not conclusive in this setting, and we therefore report exact counts "
    "instead of a single average for the whole task set."
)
EXTREME_SHORT = (
    "We compare the first method with the second method on the same task and report every "
    "failure in the appendix, where the raw logs are kept for replay."
)


class TestSentenceLengthExtreme(unittest.TestCase):
    def test_positive_long_flat(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, EXTREME_POS)
        self.assertIn("SENTENCE_LENGTH_EXTREME", codes(result))

    def test_negative_long_with_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, EXTREME_STRUCTURED)
        self.assertNotIn("SENTENCE_LENGTH_EXTREME", codes(result))

    def test_negative_short_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, EXTREME_SHORT)
        self.assertNotIn("SENTENCE_LENGTH_EXTREME", codes(result))


# --------------------------------------------------------------------------
# 输出契约：finding 字段、--json、--prompt
# --------------------------------------------------------------------------

class TestFindingContract(unittest.TestCase):
    def test_every_finding_has_five_fields_plus_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, CONNECTIVE_POS)
        self.assertTrue(result.findings)
        for finding in result.findings:
            item = finding.as_dict()
            for key in ("code", "severity", "file", "line", "text", "suggestion"):
                self.assertIn(key, item)
            self.assertEqual(item["severity"], "yellow")

    def test_json_and_prompt_are_in_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, CONNECTIVE_POS)
            proc = run_style(root, "--prompt", json_out=True)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["findings"])
        self.assertIn("prompt", payload)
        self.assertIn("黄牌", payload["prompt"])
        self.assertIn("不改事实", payload["prompt"])
        for finding in payload["findings"]:
            self.assertEqual(finding["severity"], "yellow")
        # 只有黄牌才进 prompt 条目（条目给原文与改法，不重复 code）
        self.assertIn("Moreover", payload["prompt"])

    def test_prompt_never_asks_to_change_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, CONNECTIVE_POS)
            proc = run_style(root, "--prompt")
        prompt = proc.stdout.strip()
        self.assertLessEqual(len(prompt), 400)
        self.assertIn("不改事实", prompt)
        self.assertIn("不得删数字", prompt)
        self.assertIn("不得删引用", prompt)


if __name__ == "__main__":
    unittest.main()
