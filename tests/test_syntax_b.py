# -*- coding: utf-8 -*-
"""批 105：B 档五条判据（全离线）。

规范：`docs/design/SPEC-SYNTAX-B.md`；读数：`docs/implementation/SYNTAX-B.md`。

覆盖（每条 ≥3 正例、≥3 负例、1 条反向锁）：

* `NOMINALIZATION_RATE`：后缀与词长、剥离前 5 高频类型、每百词单位、
  `strip_top` 可配、中文语料反向锁；
* `ZH_ASPECT_ZHE`：动词＋着、词尾「有着」、词内用法排除、每千汉字单位、
  英文反向锁；
* `ZH_DANG_WHEN`：同段 ≥2 处才报、单句单次不报、跨段不累计、三种尾巴、
  词内「当成/当天/当然」排除、「什么时候」排除、paper-b-zh 反向锁；
* `ZH_COLLOCATION_REDUNDANCY`：十条词表逐一触发、每条给删法、跨句不报、
  单一半词不报；
* `ABBREV_FIRST_USE`：默认关、`--report-abbrev` 打开、同句/前一句展开、
  中文全角括号、只报首现、罗马数字排除。
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

from factscribe.config import Config  # noqa: E402
from factscribe.style import analyze, load_style_rules  # noqa: E402


def analyze_text(text: str, rules: str = "", fmt: str = "markdown",
                 report_abbrev: bool = False) -> object:
    name = "doc.tex" if fmt == "tex" else "doc.md"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if rules:
            (root / "style-rules.toml").write_text(rules, encoding="utf-8")
        loaded, path = load_style_rules(root)
        result = analyze(Config(root=root), [(name, text)], loaded,
                         rules_path=path, formats={name: fmt},
                         report_abbrev=report_abbrev)
    return result


def codes(result) -> set:
    return {f.code for f in result.findings}


def findings(result, code: str):
    return [f for f in result.findings if f.code == code]


def run_cli(cwd, *args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run([sys.executable, "-m", "factscribe", *args],
                          cwd=str(cwd), capture_output=True, text=True,
                          env=env)


# --------------------------------------------------------------------------
# 样本
# --------------------------------------------------------------------------

NOM_DENSE = (
    "Implementation measurement observation evaluation classification "
    "optimization validation configuration matter for this study and for "
    "the result of the comparison."
)
NOM_SPARSE = (
    "The model performs well under load and stays within the token budget."
)
# 两个类型各出现多次：剥离前 5 个类型后，一个都不剩。
NOM_TWO_TERMS = (
    "configuration configuration configuration configuration configuration "
    "implementation implementation implementation implementation implementation "
    "the run is stable and the log is short and the gate is quiet."
)
# paper-b-zh 的实际中文句子：只有 2 个英文词，不该有英文名词化密度。
NOM_CHINESE = "一条排版用的注释活进了编译出的 PDF，被当作正文印出来。"

ZHE_EXIST = "系统存在着两个问题，我们记录了它们。"
ZHE_TWO = "研究人员进行着讨论，也保持着记录。"
ZHE_HAVE = "这个方案有着明显的优势。"
ZHE_LEXICAL = (
    "沿着河走，照着做，意味着失败，接着来，跟着走，随着时间过去。"
)
ZHE_PLAIN = "他把书读完了，我们没有意见。"
ZHE_ENGLISH = "The gate stays quiet under load and reports no findings."

DANG_DE = "当数据缺失的时候，流程会停下。当字段缺失的时候，流程也会停下。"
DANG_AFTER = "当数据加载之后，流程才开始。当索引重建之后，流程才继续。"
DANG_SHI = "当两套约定不一致时，两套都印出来。当两套命名冲突时，两套都报出来。"
# 单次出现是正常中文（批 107 主语者裁定），不是欧化病灶。
DANG_SINGLE = "当两套约定不一致时，两套都印在这条主张旁边。"
DANG_CROSS = ("当数据缺失的时候，流程会停下。\n\n"
              "当数据加载之后，流程才开始。")
DANG_WHEN = "当它什么时候跑，没人知道。当它什么时候停，也没人知道。"
DANG_LEXICAL = ("他把规格当成文档来攻。他又把需求当成结论。"
                "当天下午我们复跑了实验。当然，这条也要改。")
DANG_CORPUS = ("外部席位没有实现者的心智模型，它把规格当文档来攻：定义可以有"
               "两种读法，保证提到了某项检查却没说它什么时候跑。")

COLLOC = [
    ("大约三成左右的样本被丢弃。", "大约…左右", "大约"),
    ("这是唯一一个能复现的配置。", "唯一一个", "一个"),
    ("两端相互之间保持独立。", "相互之间", "相互"),
    ("两套规则彼此互相覆盖。", "彼此互相", "彼此"),
    ("会议提前预订了场地。", "提前预…", "提前"),
    ("入场券免费赠送，不需要另外付钱。", "免费赠送", "免费"),
    ("我们亲眼目睹了重跑。", "亲眼目睹", "亲眼"),
    ("这里再次重申阈值。", "再次重申", "再次"),
    ("这条结论一致公认。", "一致公认", "一致"),
    ("首先第一，阈值不改。", "首先第一", "首先"),
]
COLLOC_NEGATIVE = (
    "大约三次，我们记下结果。唯一的一条规则仍然成立，两端相互依赖，"
    "彼此信任；会议提前到达，入场券免费提供，亲眼看到重跑，再次说明阈值，"
    "一致同意结论，第一步先冻结。"
)

ABBR_PLAIN = "We use the CNN model here. The CNN is fast."
ABBR_ONE_SENT = "Convolutional Neural Network (CNN) is used here."
ABBR_PREV = "We use a Convolutional Neural Network (CNN). The CNN is fast."
ABBR_ZH = "卷积神经网络（CNN）用于这里。CNN 很快。"
ABBR_ROMAN = "Section II describes the run. Section III continues."


# --------------------------------------------------------------------------
# 1. NOMINALIZATION_RATE
# --------------------------------------------------------------------------

class TestNominalizationRate(unittest.TestCase):
    def test_dense_nominalization_fires(self):
        result = analyze_text(NOM_DENSE)
        self.assertIn("NOMINALIZATION_RATE", codes(result))
        self.assertGreater(result.metrics["nominalization_rate"], 4.5)

    def test_metric_is_per_hundred_words(self):
        result = analyze_text(NOM_DENSE)
        # 20 个英文词，剥离前 5 个类型后剩 3 个 → 15.0/百词。
        self.assertEqual(result.metrics["nominalization_rate"], 15.79)
        self.assertEqual(result.thresholds["nominalization_rate"], 4.5)

    def test_stripped_terms_are_reported(self):
        result = analyze_text(NOM_DENSE)
        stripped = result.metric_details["nominalization_stripped"]
        self.assertEqual(len(stripped), 5)
        self.assertIn("implementation", stripped)
        # 报告正文必须能让人复查被剥离的词。
        self.assertIn("已剥离本文高频术语", findings(
            result, "NOMINALIZATION_RATE")[0].suggestion)
        for word in stripped:
            self.assertIn(word, findings(result, "NOMINALIZATION_RATE")[0].suggestion)

    def test_two_domain_terms_are_stripped_to_zero(self):
        result = analyze_text(NOM_TWO_TERMS)
        self.assertEqual(result.metrics["nominalization_rate"], 0.0)
        self.assertNotIn("NOMINALIZATION_RATE", codes(result))
        self.assertEqual(set(result.metric_details["nominalization_stripped"]),
                         {"configuration", "implementation"})

    def test_sparse_text_negative(self):
        result = analyze_text(NOM_SPARSE)
        self.assertEqual(result.metrics["nominalization_rate"], 0.0)
        self.assertNotIn("NOMINALIZATION_RATE", codes(result))

    def test_short_words_do_not_count(self):
        # "tion" 只有 4 个字母，不构成词形；词长下限是 5。
        result = analyze_text("tion tion tion tion tion is not a word.")
        self.assertEqual(result.metrics["nominalization_rate"], 0.0)

    def test_chinese_corpus_reverse_lock(self):
        # paper-b-zh 的一句实测文本：英文词只有 2 个，规则应 0 触发。
        result = analyze_text(NOM_CHINESE)
        self.assertEqual(result.metrics["nominalization_rate"], 0.0)
        self.assertNotIn("NOMINALIZATION_RATE", codes(result))

    def test_strip_top_configurable(self):
        rules = "[nominalization]\nstrip_top = 8\n"
        result = analyze_text(NOM_DENSE, rules)
        self.assertEqual(len(result.metric_details["nominalization_stripped"]), 8)
        self.assertEqual(result.metrics["nominalization_rate"], 0.0)


# --------------------------------------------------------------------------
# 2. ZH_ASPECT_ZHE
# --------------------------------------------------------------------------

class TestZhAspectZhe(unittest.TestCase):
    def test_exist_zhe_fires(self):
        result = analyze_text(ZHE_EXIST)
        found = findings(result, "ZH_ASPECT_ZHE")
        self.assertEqual(len(found), 1)
        self.assertIn("存在着", found[0].suggestion + found[0].text)

    def test_two_verb_zhe_forms_count(self):
        result = analyze_text(ZHE_TWO)
        self.assertEqual(result.metrics["zh_aspect_zhe"], 133.33)
        self.assertEqual(result.metric_details["zh_aspect_zhe_raw_hits"], 2)

    def test_token_ending_zhe_counts(self):
        # 「有着」在词表里是一个整词（v），不是「有」＋「着」。
        result = analyze_text(ZHE_HAVE)
        self.assertEqual(result.metric_details["zh_aspect_zhe_raw_hits"], 1)
        self.assertIn("ZH_ASPECT_ZHE", codes(result))

    def test_lexical_zhe_negative(self):
        result = analyze_text(ZHE_LEXICAL)
        self.assertEqual(result.metric_details["zh_aspect_zhe_raw_hits"], 0)
        self.assertEqual(result.metrics["zh_aspect_zhe"], 0.0)
        self.assertNotIn("ZH_ASPECT_ZHE", codes(result))

    def test_plain_text_negative(self):
        result = analyze_text(ZHE_PLAIN)
        self.assertNotIn("ZH_ASPECT_ZHE", codes(result))

    def test_english_reverse_lock(self):
        result = analyze_text(ZHE_ENGLISH)
        self.assertEqual(result.metrics["zh_aspect_zhe"], 0.0)
        self.assertNotIn("ZH_ASPECT_ZHE", codes(result))

    def test_threshold_configurable(self):
        rules = "[thresholds]\nzh_aspect_zhe = 1000\n"
        result = analyze_text(ZHE_TWO, rules)
        self.assertEqual(result.metric_details["zh_aspect_zhe_raw_hits"], 2)
        self.assertNotIn("ZH_ASPECT_ZHE", codes(result))


# --------------------------------------------------------------------------
# 3. ZH_DANG_WHEN
# --------------------------------------------------------------------------

class TestZhDangWhen(unittest.TestCase):
    def test_de_shihou(self):
        result = analyze_text(DANG_DE)
        found = findings(result, "ZH_DANG_WHEN")
        self.assertEqual(len(found), 2)
        self.assertIn("让条件自己站住", found[0].suggestion)  # 给删法，不只报数
        # 报的时候列出本段全部命中位置。
        self.assertIn("本段共 2 处", found[0].suggestion)
        self.assertIn("当字段缺失的时候", found[0].suggestion)

    def test_zhihou(self):
        result = analyze_text(DANG_AFTER)
        self.assertEqual(result.metrics["zh_dang_when"], 2)
        self.assertIn("删「当」", findings(result, "ZH_DANG_WHEN")[0].suggestion)

    def test_dang_shi(self):
        result = analyze_text(DANG_SHI)
        self.assertEqual(result.metrics["zh_dang_when"], 2)

    def test_single_occurrence_is_normal_chinese(self):
        # 主语者裁定：单次「当…时」是正常中文；只有同段成串才是欧化病灶。
        result = analyze_text(DANG_SINGLE)
        self.assertNotIn("ZH_DANG_WHEN", codes(result))
        self.assertEqual(result.metrics["zh_dang_when"], 0)

    def test_cross_paragraph_occurrences_do_not_add_up(self):
        # 每段各一处，跨段不累计。
        result = analyze_text(DANG_CROSS)
        self.assertNotIn("ZH_DANG_WHEN", codes(result))
        self.assertEqual(result.metrics["zh_dang_when"], 0)

    def test_when_question_negative(self):
        result = analyze_text(DANG_WHEN)
        self.assertNotIn("ZH_DANG_WHEN", codes(result))

    def test_lexical_dang_negative(self):
        result = analyze_text(DANG_LEXICAL)
        self.assertNotIn("ZH_DANG_WHEN", codes(result))

    def test_paper_b_zh_reverse_lock(self):
        result = analyze_text(DANG_CORPUS)
        self.assertNotIn("ZH_DANG_WHEN", codes(result))
        self.assertEqual(result.metrics["zh_dang_when"], 0)

    def test_runtime_noun_not_a_condition(self):
        # 「运行时」是名词（runtime），不是「当…时」；尾巴后面跟「把」，
        # 不是停顿或主句标记。写两处，确认不是靠同段闸挡住的。
        result = analyze_text(
            "只有当运行时把决定权拿走，任务才被解决。"
            "只有当运行时把控制权交回，任务才收尾。")
        self.assertNotIn("ZH_DANG_WHEN", codes(result))

    def test_colon_does_not_bridge(self):
        result = analyze_text(
            "他把它当文档：检查什么时候跑，没人知道。"
            "他又把它当文档：检查什么时候停，也没人知道。")
        self.assertNotIn("ZH_DANG_WHEN", codes(result))


# --------------------------------------------------------------------------
# 4. ZH_COLLOCATION_REDUNDANCY
# --------------------------------------------------------------------------

class TestZhCollocationRedundancy(unittest.TestCase):
    def test_all_ten_items_fire_with_a_fix(self):
        for text, label, fix_word in COLLOC:
            with self.subTest(label=label):
                result = analyze_text(text)
                found = findings(result, "ZH_COLLOCATION_REDUNDANCY")
                self.assertEqual(len(found), 1, found)
                self.assertIn(label, found[0].suggestion)
                self.assertIn(fix_word, found[0].suggestion)

    def test_metric_counts_places(self):
        text = "\n".join(item[0] for item in COLLOC)
        result = analyze_text(text)
        self.assertEqual(result.metrics["zh_collocation_redundancy"], 10)

    def test_half_phrase_negative(self):
        result = analyze_text(COLLOC_NEGATIVE)
        self.assertEqual(result.metrics["zh_collocation_redundancy"], 0)
        self.assertNotIn("ZH_COLLOCATION_REDUNDANCY", codes(result))

    def test_cross_sentence_negative(self):
        result = analyze_text("大约三成样本被丢弃。左右两栏都记了数。")
        self.assertNotIn("ZH_COLLOCATION_REDUNDANCY", codes(result))

    def test_english_reverse_lock(self):
        result = analyze_text("The run is unique and the two arms differ.")
        self.assertEqual(result.metrics["zh_collocation_redundancy"], 0)

    def test_config_carries_ten_items(self):
        loaded, _path = load_style_rules(ROOT)
        items = loaded["zh_collocation_redundancy"]["items"]
        self.assertEqual(len(items), 10)
        for item in items:
            self.assertTrue(item["pattern"])
            self.assertTrue(item["fix"])


# --------------------------------------------------------------------------
# 5. ABBREV_FIRST_USE
# --------------------------------------------------------------------------

class TestAbbrevFirstUse(unittest.TestCase):
    def test_default_off(self):
        result = analyze_text(ABBR_PLAIN)
        self.assertEqual(result.metrics["abbrev_first_use"], 0)
        self.assertNotIn("ABBREV_FIRST_USE", codes(result))
        self.assertFalse(result.metric_details["abbrev_first_use_enabled"])

    def test_reports_when_enabled(self):
        result = analyze_text(ABBR_PLAIN, report_abbrev=True)
        found = findings(result, "ABBREV_FIRST_USE")
        self.assertEqual(len(found), 1)
        self.assertIn("CNN", found[0].suggestion)
        self.assertIn("全称", found[0].suggestion)

    def test_same_sentence_expansion_negative(self):
        result = analyze_text(ABBR_ONE_SENT + " The CNN is fast.",
                              report_abbrev=True)
        self.assertNotIn("ABBREV_FIRST_USE", codes(result))

    def test_previous_sentence_expansion_negative(self):
        result = analyze_text(ABBR_PREV, report_abbrev=True)
        self.assertNotIn("ABBREV_FIRST_USE", codes(result))

    def test_chinese_fullwidth_expansion_negative(self):
        result = analyze_text(ABBR_ZH, report_abbrev=True)
        self.assertNotIn("ABBREV_FIRST_USE", codes(result))

    def test_only_first_use_reported(self):
        result = analyze_text("We use CNN. CNN is fast. CNN wins.",
                              report_abbrev=True)
        self.assertEqual(result.metrics["abbrev_first_use"], 1)

    def test_roman_numerals_excluded(self):
        result = analyze_text(ABBR_ROMAN, report_abbrev=True)
        self.assertEqual(result.metrics["abbrev_first_use"], 0)

    def test_reverse_lock_expanded_corpus(self):
        text = ("Software Engineering (SWE) benchmarks are hard. "
                "The SWE suite is small.\n"
                "Optical Character Recognition (OCR) reads pixels. "
                "The OCR gate is off.")
        result = analyze_text(text, report_abbrev=True)
        self.assertEqual(result.metrics["abbrev_first_use"], 0)

    def test_cli_flag_opens_and_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.md"
            path.write_text(ABBR_PLAIN + "\n", encoding="utf-8")
            closed = run_cli(tmp, "style", "--doc", "doc.md", "--json")
            opened = run_cli(tmp, "style", "--doc", "doc.md", "--json",
                             "--report-abbrev")
        self.assertNotIn("ABBREV_FIRST_USE",
                         [f["code"] for f in json.loads(closed.stdout)["findings"]])
        payload = json.loads(opened.stdout)
        self.assertIn("ABBREV_FIRST_USE",
                      [f["code"] for f in payload["findings"]])
        self.assertTrue(payload["metric_details"]["abbrev_first_use_enabled"])


# --------------------------------------------------------------------------
# 6. 注册面
# --------------------------------------------------------------------------

class TestRegistrationB(unittest.TestCase):
    def test_thresholds_registered_with_units(self):
        loaded, _path = load_style_rules(ROOT)
        self.assertEqual(loaded["thresholds"]["nominalization_rate"], 4.5)
        self.assertEqual(loaded["thresholds"]["zh_aspect_zhe"], 0.8)
        for key in ("zh_dang_when", "zh_collocation_redundancy",
                    "abbrev_first_use"):
            with self.subTest(key=key):
                self.assertEqual(loaded["thresholds"][key], 1)

    def test_abbrev_switch_default_false(self):
        loaded, _path = load_style_rules(ROOT)
        self.assertFalse(loaded["abbrev_first_use"])

    def test_nominalization_suffixes_fixed(self):
        loaded, _path = load_style_rules(ROOT)
        group = loaded["nominalization"]
        self.assertEqual(group["suffixes"],
                         ["tion", "sion", "ment", "ance", "ence", "ity",
                          "ness", "ism"])
        self.assertEqual(group["min_length"], 5)
        self.assertEqual(group["strip_top"], 5)

    def test_zhe_exclude_has_lexical_forms(self):
        loaded, _path = load_style_rules(ROOT)
        exclude = loaded["zh_aspect_zhe"]["exclude"]
        for word in ("意味着", "沿着", "照着", "接着", "随着"):
            with self.subTest(word=word):
                self.assertIn(word, exclude)


if __name__ == "__main__":
    unittest.main()
