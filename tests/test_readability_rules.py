# -*- coding: utf-8 -*-
"""批 129：读者感觉三项代理判据的契约测试（全离线）。

覆盖：

* ``NUMERAL_DENSITY``：英文/中文正例、负例、阈值边界、``stage="off"`` 降级；
* ``SECTION_OVERLAP``：英文/中文「真重复」正例、「正常引用同一事实」负例、
  阈值边界；
* ``WE_ACTION_DENSITY``：英文/中文正例、``we propose`` 不计入、阈值边界；
* ``polish --plan`` 三条各自映射到 ``thin-the-numbers`` / ``merge-overlap`` /
  ``shift-to-implication``。

规范：``docs/design/SPEC-READABILITY.md``。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import load_config, load_sections  # noqa: E402
from factscribe.polish import build_entries, no_prescription_codes  # noqa: E402
from factscribe.prescribe import prescriptions_for  # noqa: E402
from factscribe.style import Finding, analyze, load_style_rules  # noqa: E402

PROJECT_TOML = """[project]
title = "readability"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""

# 10 个英文词（数字不占词数），重复十次正好 100 词。
EN_SENTENCE = "The quick brown fox jumps over the lazy dog again"
ZH_SENTENCE = "本节报告三次实验得到的稳定读数"   # 15 个汉字


def make_project(tmp, files: dict, rules: str | None = None) -> Path:
    root = Path(tmp)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "paperkit.toml").write_text(PROJECT_TOML, encoding="utf-8")
    for name, body in files.items():
        path = root / "sections" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    if rules is not None:
        (root / "style-rules.toml").write_text(rules, encoding="utf-8")
    return root


def run_style(tmp, files: dict, rules: str | None = None):
    root = make_project(tmp, files, rules)
    cfg = load_config(root)
    loaded, path = load_style_rules(root)
    return analyze(cfg, load_sections(cfg), loaded, rules_path=path)


def codes(result) -> set:
    return {f.code for f in result.findings}


def en_numeral_body(numbers: int) -> str:
    """100 个英文词 + ``numbers`` 个阿拉伯数字 token。"""
    parts = []
    for i in range(10):
        tail = " %d" % (i + 1) if i < numbers else ""
        parts.append(EN_SENTENCE + tail + ".")
    return "\\section{Measurement}\n\n" + " ".join(parts) + "\n"


def zh_numeral_body(numbers: int) -> str:
    """300 个汉字 + ``numbers`` 个阿拉伯数字 token。"""
    parts = []
    for i in range(20):
        tail = " %d" % (i + 1) if i < numbers else ""
        parts.append(ZH_SENTENCE + tail + "。")
    return "\\section{测量}\n\n" + "".join(parts) + "\n"


def long_en_paragraph(seed: str) -> str:
    """约 100 个英文词的正文段落。"""
    return ("%s first line carries the sealed set and the registered bar. "
            "%s second line names the contract, the ledger, and the receipt. "
            "%s third line reports the blind curve without changing any value. "
            "%s fourth line keeps every number bound to a source file. "
            "%s fifth line closes the loop with a table of measured values. "
            "%s sixth line leaves the argument where the reader can check it."
            % ((seed,) * 6))


def chinese_long(seed: str) -> str:
    """约 180 个汉字的正文段落。"""
    return ("%s第一次运行把合同冻结在开工之前，所有读数都写进账本。"
            "%s第二次运行只比对新增加的违规，保护面一项都没有动。"
            "%s第三次运行把重复的数字并回主节，结论留在本节。" % (seed, seed, seed))


def english_other() -> str:
    """与 ``long_en_paragraph`` 词序不同的另一段英文正文。"""
    return ("The reviewer opens the report and checks the ledger entry for each "
            "claim. A missing receipt stops the review before the prose is read "
            "at all. The author cannot revise the bar after seeing the first "
            "score. Numbers in the manuscript point back to source files and run "
            "records. A clean report covers only the surfaces the checker can "
            "actually reach. The reader still has to decide whether the "
            "argument is worth keeping.")


def chinese_other() -> str:
    """与 ``chinese_long`` 词序不同的另一段中文正文。"""
    return ("评审先打开报告，再逐条核对账本里的回执与内容哈希。"
            "缺少回执的条目会在读正文之前就被拦下。"
            "作者不能在看到第一轮读数之后修改已经注册的门槛。"
            "正文里的每个数字都指回源文件与运行记录。"
            "清洁报告只覆盖检查器真正够得到的表面。"
            "论证是否站得住，仍要由读者自己判断。")


def en_we_body(action_sentences: int, total: int = 10) -> str:
    parts = []
    for i in range(total):
        if i < action_sentences:
            parts.append("We ran the sealed check number %d on the local disk." % i)
        else:
            parts.append("The sealed result number %d stayed stable across the run." % i)
    return "\\section{Method}\n\n" + " ".join(parts) + "\n"


def zh_we_body(action_sentences: int, total: int = 10) -> str:
    parts = []
    for i in range(total):
        if i < action_sentences:
            parts.append("我们跑了第%d次实验并记录了每次的读数。" % i)
        else:
            parts.append("第%d次实验的读数在整轮里保持稳定。" % i)
    return "\\section{方法}\n\n" + "".join(parts) + "\n"


# --------------------------------------------------------------------------
# 1. NUMERAL_DENSITY
# --------------------------------------------------------------------------

class TestNumeralDensity(unittest.TestCase):
    def test_english_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {"01.tex": en_numeral_body(5)})
        self.assertIn("NUMERAL_DENSITY", codes(result))
        self.assertEqual(result.metrics["numeral_density"], 50.0)
        text = next(f.text for f in result.findings
                    if f.code == "NUMERAL_DENSITY")
        self.assertIn("本节 5 个数字", text)
        self.assertIn("阈值 40", text)
        self.assertIn("密度 50.0", text)

    def test_english_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {"01.tex": en_numeral_body(0)})
        self.assertNotIn("NUMERAL_DENSITY", codes(result))
        self.assertEqual(result.metrics["numeral_density"], 0.0)

    def test_english_threshold_boundary_strictly_above(self):
        # 4/100 词 = 40.0，正好等于阈值不报；5/100 词 = 50.0 报。
        with tempfile.TemporaryDirectory() as tmp:
            at = run_style(tmp, {"01.tex": en_numeral_body(4)})
        self.assertNotIn("NUMERAL_DENSITY", codes(at))
        self.assertEqual(at.metrics["numeral_density"], 40.0)
        with tempfile.TemporaryDirectory() as tmp:
            over = run_style(tmp, {"01.tex": en_numeral_body(5)})
        self.assertIn("NUMERAL_DENSITY", codes(over))

    def test_chinese_positive_and_boundary(self):
        # 300 汉字：12 个数字 = 40.0 不报；13 个 = 43.3 报。
        with tempfile.TemporaryDirectory() as tmp:
            at = run_style(tmp, {"01.tex": zh_numeral_body(12)})
        self.assertNotIn("NUMERAL_DENSITY", codes(at))
        self.assertEqual(at.metrics["numeral_density"], 40.0)
        with tempfile.TemporaryDirectory() as tmp:
            over = run_style(tmp, {"01.tex": zh_numeral_body(13)})
        self.assertIn("NUMERAL_DENSITY", codes(over))
        self.assertGreater(over.metrics["numeral_density"], 40.0)

    def test_stage_off_downgrades_to_info(self):
        rules = 'numeral_density_stage = "off"\n'
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {"01.tex": en_numeral_body(5)}, rules)
        self.assertNotIn("NUMERAL_DENSITY", codes(result))
        self.assertGreater(result.metrics["numeral_density"], 40.0)
        info = [f for f in result.info if f.code == "NUMERAL_DENSITY"]
        self.assertEqual(len(info), 1)
        self.assertEqual(info[0].severity, "info")
        self.assertIn("PROTECT_NUMBER_CHANGED", info[0].suggestion)
        self.assertNotIn("NUMERAL_DENSITY",
                         {f["code"] for f in result.fired})

    def test_bad_stage_is_config_error(self):
        rules = 'numeral_density_stage = "rewrite"\n'
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                run_style(tmp, {"01.tex": en_numeral_body(5)}, rules)


# --------------------------------------------------------------------------
# 2. SECTION_OVERLAP
# --------------------------------------------------------------------------

class TestSectionOverlap(unittest.TestCase):
    def test_english_true_duplicate(self):
        body = long_en_paragraph("Alpha")
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {
                "01.tex": "\\section{First}\n\n" + body + "\n",
                "02.tex": "\\section{Second}\n\n" + body + "\n"})
        hits = [f for f in result.findings if f.code == "SECTION_OVERLAP"]
        self.assertEqual(len(hits), 1)
        self.assertIn("本节与", hits[0].text)
        self.assertIn("重合率 100.0%", hits[0].text)
        self.assertEqual(hits[0].file, "sections/02.tex")

    def test_english_citing_same_fact_is_not_duplicate(self):
        shared = "The gate caught thirty of thirty six planted defects."
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {
                "01.tex": "\\section{First}\n\n" + shared + " "
                          + long_en_paragraph("One") + "\n",
                "02.tex": "\\section{Second}\n\n" + shared + " "
                          + english_other() + "\n"})
        self.assertNotIn("SECTION_OVERLAP", codes(result))

    def test_chinese_true_duplicate(self):
        body = chinese_long("甲")
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {
                "01.tex": "\\section{第一节}\n\n" + body + "\n",
                "02.tex": "\\section{第二节}\n\n" + body + "\n"})
        self.assertIn("SECTION_OVERLAP", codes(result))
        self.assertEqual(result.metrics["section_overlap"], 100.0)

    def test_chinese_same_fact_is_not_duplicate(self):
        shared = "样本只有十六单，区间宽到十三到十九单。"
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {
                "01.tex": "\\section{第一节}\n\n" + shared
                          + chinese_long("甲") + "\n",
                "02.tex": "\\section{第二节}\n\n" + shared
                          + chinese_other() + "\n"})
        self.assertNotIn("SECTION_OVERLAP", codes(result))

    def test_threshold_boundary_strictly_above(self):
        body = long_en_paragraph("Beta")
        files = {"01.tex": "\\section{First}\n\n" + body + "\n",
                 "02.tex": "\\section{Second}\n\n" + body + "\n"}
        with tempfile.TemporaryDirectory() as tmp:
            at = run_style(tmp, files, "[thresholds]\nsection_overlap = 100\n")
        self.assertNotIn("SECTION_OVERLAP", codes(at))
        with tempfile.TemporaryDirectory() as tmp:
            over = run_style(tmp, files, "[thresholds]\nsection_overlap = 99\n")
        self.assertIn("SECTION_OVERLAP", codes(over))


# --------------------------------------------------------------------------
# 3. WE_ACTION_DENSITY
# --------------------------------------------------------------------------

class TestWeActionDensity(unittest.TestCase):
    def test_english_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {"01.tex": en_we_body(5)})
        self.assertIn("WE_ACTION_DENSITY", codes(result))
        self.assertEqual(result.metrics["we_action_density"], 0.5)

    def test_english_propose_is_not_action(self):
        body = ("\\section{Method}\n\n"
                "We propose a new order of work for every sealed set. "
                "We claim the gate is replaceable but the order is not. "
                "We argue that registration matters more than truth here. "
                "We believe the reader can check the report without a rerun. "
                "We suggest the contract is frozen before the first run.")
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {"01.tex": body})
        self.assertNotIn("WE_ACTION_DENSITY", codes(result))
        self.assertEqual(result.metrics["we_action_density"], 0.0)

    def test_chinese_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {"01.tex": zh_we_body(5)})
        self.assertIn("WE_ACTION_DENSITY", codes(result))
        self.assertEqual(result.metrics["we_action_density"], 0.5)

    def test_chinese_propose_is_not_action(self):
        body = ("\\section{方法}\n\n"
                "我们提出一条新的工作顺序，先冻结合同再开工。"
                "我们主张登记比真理更重要，报告可以复核。"
                "我们认为读者不需要重跑管线就能检查结论。"
                "我们建议把门槛写在第一次运行之前。"
                "我们强调顺序比工具更值得保留。")
        with tempfile.TemporaryDirectory() as tmp:
            result = run_style(tmp, {"01.tex": body})
        self.assertNotIn("WE_ACTION_DENSITY", codes(result))
        self.assertEqual(result.metrics["we_action_density"], 0.0)

    def test_threshold_boundary_strictly_above(self):
        files = {"01.tex": en_we_body(5)}
        with tempfile.TemporaryDirectory() as tmp:
            at = run_style(tmp, files,
                           "[thresholds]\nwe_action_density = 0.5\n")
        self.assertNotIn("WE_ACTION_DENSITY", codes(at))
        self.assertEqual(at.metrics["we_action_density"], 0.5)
        with tempfile.TemporaryDirectory() as tmp:
            over = run_style(tmp, files,
                             "[thresholds]\nwe_action_density = 0.49\n")
        self.assertIn("WE_ACTION_DENSITY", codes(over))


# --------------------------------------------------------------------------
# 4. polish --plan 映射
# --------------------------------------------------------------------------

class TestPrescriptionMapping(unittest.TestCase):
    def test_three_codes_map_to_their_prescriptions(self):
        result = SimpleNamespace(findings=[
            Finding("NUMERAL_DENSITY", "sections/a.tex", 1, "x", ""),
            Finding("SECTION_OVERLAP", "sections/a.tex", 2, "y", ""),
            Finding("WE_ACTION_DENSITY", "sections/a.tex", 3, "z", ""),
        ], advisories=[], info=[])
        entries = build_entries(result)
        got = {e.code: e.prescription for e in entries}
        self.assertEqual(got["NUMERAL_DENSITY"], "thin-the-numbers")
        self.assertEqual(got["SECTION_OVERLAP"], "merge-overlap")
        self.assertEqual(got["WE_ACTION_DENSITY"], "shift-to-implication")

    def test_three_codes_are_no_longer_no_prescription(self):
        missing = set(no_prescription_codes())
        for code in ("NUMERAL_DENSITY", "SECTION_OVERLAP",
                     "WE_ACTION_DENSITY"):
            with self.subTest(code=code):
                self.assertNotIn(code, missing)
                self.assertTrue(prescriptions_for(code))


if __name__ == "__main__":
    unittest.main()
