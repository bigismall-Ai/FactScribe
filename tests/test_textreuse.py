# -*- coding: utf-8 -*-
"""CARD-G6：双目录字面重合检测（`factscribe textreuse`）。

正负例成对：

* 正例——逐字照搬的段落一律红（exit 1），并给两侧 `文件:行-行` 与重合词数；
* 负例——干净文档对不红（exit 0），改写/洗稿类不红（漏检属语义层），
  LaTeX 注释行不红；
* 用法错——目录不存在、n 越界、两侧同一目录一律 exit 2（不静默放行）。

口径见工单 G6「实现面」与「验收」节；能力边界（语义层不覆盖）由模块
常量 `textreuse.BOUNDARY` 逐字承载。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe import textreuse                  # noqa: E402
from factscribe.config import ConfigError        # noqa: E402

PLANTED = ("the experimental design phase of this manuscript relies on a fixed "
           "and publicly documented sampling protocol that has been applied "
           "unchanged across every arm of the comparative study reported in "
           "the following paragraph of the results section")

CLEAN_A = ("alpha document discussing quantum widgets harmonic oscillations "
           "and unrelated astronomy measurements of distant nebulae")

CLEAN_B = ("beta document examining sedimentation patterns in river deltas "
           "across seasonal surveys of coastal marshes and their fauna")

CLEAN_C = ("zeta document profiling migratory bird routes using ringed "
           "specimens collected every year along the northern coastline")

CLEAN_D = ("eta document measuring corrosion resistance of recycled aluminium "
           "alloy fasteners stored in humid chambers for long periods")

REWRITTEN = ("the empirical layout stage of this paper depends on a constant "
             "and publically recorded selection procedure that has been used "
             "unaltered throughout each arm of the comparative investigation "
             "described in the next passage of the findings portion of the "
             "document")

# 词级扰动版：模拟「插入段落被随机插入拉丁词打断」——固定 8 词窗切不中
# （逐字段最长 5 词），但句子级词集包含仍成立（P-165 改进批的核心场景）。
PERTURBED = ("the experimental design phase of sic this manuscript relies on a "
             "jubeo fixed and publicly documented sampling positis protocol "
             "that has been applied quidem unchanged across every arm of the "
             "omen comparative study reported in the tempus the following "
             "paragraph of the results section")

# 换词版：四个词被换成别的词 → 句级包含率落在 0.8–0.9 之间（阈值旋钮可测）。
REPLACED = ("the experimental consilium phase of this manuscript relies on a "
            "fixed and publice documented sampling protocol that has been "
            "applied unchanged across every brachium of the comparative study "
            "reported in the subsequens paragraph of the results section")


def write_side(root: Path, name: str, docs: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for fname, text in docs.items():
        target = root / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def run_textreuse(dir_a, dir_b, *extra):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", "textreuse",
           str(dir_a), str(dir_b), *extra]
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


class TextReuseFixture(unittest.TestCase):
    """基类：每个用例一对临时目录。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def side(self, name: str, docs: dict) -> Path:
        return write_side(self.tmp / name, name, docs)


# --------------------------------------------------------------------------
# 正例：逐字照搬必红
# --------------------------------------------------------------------------
class PlantedOverlap(TextReuseFixture):
    def test_verbatim_passage_is_detected(self):
        a = self.side("A", {"a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        result = textreuse.scan(a, b)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(len(result.segments), 1)
        seg = result.segments[0]
        self.assertEqual(seg.a_file, "a1.md")
        self.assertEqual(seg.b_file, "b1.md")
        self.assertGreaterEqual(seg.overlap_tokens, 8)

    def test_segment_reports_both_sides_file_and_lines(self):
        a = self.side("A", {"a1.md": "# A\n\nintro line\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        result = textreuse.scan(a, b)
        seg = result.segments[0]
        self.assertGreater(seg.a_line_start, 0)
        self.assertGreaterEqual(seg.a_line_end, seg.a_line_start)
        self.assertGreaterEqual(seg.b_line_start, 1)
        text = textreuse.render(result)
        self.assertIn("a1.md:%d-%d" % (seg.a_line_start, seg.a_line_end), text)
        self.assertIn("b1.md:%d-%d" % (seg.b_line_start, seg.b_line_end), text)

    def test_summary_reports_a_side_ratio(self):
        a = self.side("A", {"a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        result = textreuse.scan(a, b)
        pair = result.pairs[0]
        self.assertEqual(pair.a_file, "a1.md")
        self.assertEqual(pair.b_file, "b1.md")
        self.assertGreater(pair.overlap_tokens, 0)
        self.assertGreater(pair.a_ratio, 0.0)
        self.assertLessEqual(pair.a_ratio, 1.0)
        self.assertEqual(pair.a_ratio,
                         pair.overlap_tokens / pair.a_total_tokens)

    def test_cli_exit_1_and_lists_segments(self):
        a = self.side("A", {"a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        proc = run_textreuse(a, b)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("TR_OVERLAP", proc.stdout)
        self.assertIn("a1.md", proc.stdout)
        self.assertIn("b1.md", proc.stdout)

    def test_cli_json_lists_segments_and_pairs(self):
        a = self.side("A", {"a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        proc = run_textreuse(a, b, "--json")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["command"], "textreuse")
        self.assertEqual(payload["exit"], 1)
        self.assertEqual(len(payload["segments"]), 1)
        self.assertEqual(len(payload["pairs"]), 1)
        self.assertEqual(payload["segments"][0]["code"], "TR_OVERLAP")

    def test_planted_pair_recall_three_of_three(self):
        """K=3 种植段：三段全中，且干净文档对零误报。"""
        p1 = PLANTED
        p2 = ("the second planted passage describes the calibration procedure of "
              "the instrument together with the tolerance band that reviewers "
              "asked about in the third round of comments and which the authors "
              "answered with the numbers printed in table two of this fixture")
        p3 = ("the third planted passage is a verbatim copy of the discussion "
              "paragraph about reproducibility that appears in the mirror disk "
              "of the same study and was pasted here without any modification "
              "whatsoever during the packaging exercise of the whole corpus")
        a = self.side("A", {"a1.md": "# A\n\n" + p1 + ".\n",
                            "a2.md": "# A2\n\n" + p2 + ".\n",
                            "a3.md": "# A3\n\n" + p3 + ".\n",
                            "a4.md": CLEAN_A, "a5.md": CLEAN_B})
        b = self.side("B", {"b1.md": CLEAN_C, "b2.md": CLEAN_D,
                            "b3.md": "# B3\n\n" + p1 + ".\n",
                            "b4.md": "# B4\n\n" + p2 + ".\n",
                            "b5.md": "# B5\n\n" + p3 + ".\n"})
        result = textreuse.scan(a, b)
        found = {(p.a_file, p.b_file) for p in result.pairs}
        for a_name, b_name in (("a1.md", "b3.md"), ("a2.md", "b4.md"),
                               ("a3.md", "b5.md")):
            self.assertIn((a_name, b_name), found)
        self.assertEqual(len(found), 3)

    def test_recursive_collection_finds_nested_files(self):
        a = self.side("A", {"deep/nest/a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"sub/dir/b1.md": "# B\n\n" + PLANTED + ".\n"})
        result = textreuse.scan(a, b)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.segments[0].a_file, "deep/nest/a1.md")
        self.assertEqual(result.segments[0].b_file, "sub/dir/b1.md")


# --------------------------------------------------------------------------
# 负例：不该红的不红
# --------------------------------------------------------------------------
class NoOverlap(TextReuseFixture):
    def test_clean_pair_is_green(self):
        a = self.side("A", {"a1.md": "# A\n\n" + CLEAN_A + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + CLEAN_B + ".\n"})
        result = textreuse.scan(a, b)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.segments, [])

    def test_cli_exit_0_on_clean_pair(self):
        a = self.side("A", {"a1.md": "# A\n\n" + CLEAN_A + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + CLEAN_B + ".\n"})
        proc = run_textreuse(a, b)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("零重合", proc.stdout)

    def test_short_common_phrase_below_threshold_is_green(self):
        """只有 4 个词相同：不足 min-tokens，不该报。"""
        a = self.side("A", {"a1.md": "# A\n\nshared words here plus much else\n"})
        b = self.side("B", {"b1.md": "# B\n\nshared words here plus other stuff\n"})
        result = textreuse.scan(a, b)
        self.assertEqual(result.exit_code, 0)

    def test_rewritten_passage_is_not_flagged(self):
        """改写降敏：允许漏检，但输出必须明示能力边界。"""
        a = self.side("A", {"a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + REWRITTEN + ".\n"})
        result = textreuse.scan(a, b)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("漏检属语义层，本卡不覆盖", result.boundary)
        self.assertIn("漏检属语义层，本卡不覆盖", textreuse.render(result))

    def test_latex_comment_lines_are_stripped_by_default(self):
        """注释行不是文字：默认去注释，共同文字只在注释里就不该红。"""
        comment = ("% this shared comment line mentions many words that would "
                   "otherwise form a literal overlap if comments were kept")
        a = self.side("A", {"a.tex": comment + "\n" + CLEAN_A + "\n"})
        b = self.side("B", {"b.tex": comment + "\n" + CLEAN_B + "\n"})
        result = textreuse.scan(a, b)
        self.assertEqual(result.exit_code, 0)

    def test_keep_comments_makes_comment_overlap_visible(self):
        """--no-strip-comments：注释行留着，就按文字算（口径开关可测）。"""
        comment = ("% this shared comment line mentions many words that would "
                   "otherwise form a literal overlap if comments were kept")
        a = self.side("A", {"a.tex": comment + "\n" + CLEAN_A + "\n"})
        b = self.side("B", {"b.tex": comment + "\n" + CLEAN_B + "\n"})
        result = textreuse.scan(a, b, strip_comments=False)
        self.assertEqual(result.exit_code, 1)

    def test_whitespace_folding_makes_different_spacing_still_overlap(self):
        """空白折叠：换行/多空格差异不该算「不同」——折叠后仍重合。"""
        a = self.side("A", {"a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED.replace(" ", "  ") + ".\n"})
        result = textreuse.scan(a, b)
        self.assertEqual(result.exit_code, 1)   # 折叠后仍重合（不是漏检）

    def test_latex_commands_are_not_prose(self):
        """LaTeX 排版骨架不算文字：命令实参里的长句不算重合。"""
        title = ("Shared Heading With Many Words That Would Otherwise Form "
                 "ALiteralOverlap")
        a = self.side("A", {"a.tex": "\\section{%s}\n%s\n" % (title, CLEAN_A)})
        b = self.side("B", {"b.tex": "\\chapter{%s}\n%s\n" % (title, CLEAN_B)})
        result = textreuse.scan(a, b)
        self.assertEqual(result.exit_code, 0)

    def test_zero_config_bare_txt_dirs(self):
        """外行手写：两个裸 .txt 目录，无任何项目声明，照跑。"""
        a = self.side("A", {"one.txt": CLEAN_A + "\n"})
        b = self.side("B", {"two.txt": CLEAN_B + "\n"})
        self.assertFalse((a / "factscribe.toml").exists())
        proc = run_textreuse(a, b)
        self.assertEqual(proc.returncode, 0)


# --------------------------------------------------------------------------
# 阈值与参数
# --------------------------------------------------------------------------
class Thresholds(TextReuseFixture):
    def test_min_tokens_filters_small_segments(self):
        a = self.side("A", {"a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        loose = textreuse.scan(a, b, min_tokens=5)
        strict = textreuse.scan(a, b, min_tokens=500)
        self.assertEqual(loose.exit_code, 1)
        self.assertEqual(strict.exit_code, 0)

    def test_smaller_n_finds_shorter_overlap(self):
        a = self.side("A", {"a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        result = textreuse.scan(a, b, n=5, min_tokens=5)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.n, 5)

    def test_ext_extends_default_extensions(self):
        a = self.side("A", {"a1.rst": "# A\n\n" + PLANTED + ".\n",
                            "a2.md": CLEAN_A})
        b = self.side("B", {"b1.rst": "# B\n\n" + PLANTED + ".\n",
                            "b2.md": CLEAN_B})
        # 缺省只收 .tex/.md/.txt：.rst 不在内 → 无重合。
        self.assertEqual(textreuse.scan(a, b).exit_code, 0)
        # --ext .rst 是「扩」：.rst 也收 → 命中。
        result = textreuse.scan(a, b, exts=textreuse.parse_exts([".rst"]))
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.exts, (".rst",))

    def test_parse_exts_normalizes(self):
        self.assertEqual(textreuse.parse_exts(["rst", ".md", ".md"]),
                         (".rst", ".md"))
        self.assertEqual(textreuse.parse_exts([".a,.b"]), (".a", ".b"))
        self.assertEqual(textreuse.parse_exts(None), ())


# --------------------------------------------------------------------------
# 多尺度窗 ＋ 句级包含（P-165 改进批）
# --------------------------------------------------------------------------
class MultiScaleAndSentenceLayer(TextReuseFixture):
    """词级扰动打断固定词窗时，多尺度与句级包含层要能接住。"""

    def test_perturbed_passage_is_caught_by_sentence_layer(self):
        """插入几个词之后仍要红——句级包含层兜住。"""
        a = self.side("A", {"a1.md": "# A\n\n" + PERTURBED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        result = textreuse.scan(a, b)
        self.assertEqual(result.exit_code, 1)
        sources = {s.match_source for s in result.segments}
        self.assertIn(textreuse.SRC_SENTENCE, sources)

    def test_perturbed_passage_is_green_when_sentence_layer_off(self):
        """关掉句级层就红不了——证明命中确实来自句级层（口径可关＝可归因）。"""
        a = self.side("A", {"a1.md": "# A\n\n" + PERTURBED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        result = textreuse.scan(a, b, sentences=False)
        self.assertEqual(result.exit_code, 0)

    def test_single_window_mode_keeps_verbatim_detection(self):
        """--n 单窗模式仍按旧口径工作（向后兼容）。"""
        a = self.side("A", {"a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        result = textreuse.scan(a, b, n=8)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.scales, (8,))
        self.assertEqual(result.n, 8)

    def test_default_is_multi_scale(self):
        a = self.side("A", {"a1.md": "# A\n\n" + PLANTED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        result = textreuse.scan(a, b)
        self.assertEqual(result.scales, (8, 5))
        self.assertTrue(result.sentences)

    def test_short_overlap_found_only_by_small_scale(self):
        """6 词逐字重合：n=8 切不中，n=5 切得中（多尺度的意义）。"""
        short = "alpha beta gamma delta epsilon zeta"
        a = self.side("A", {"a1.md": "# A\n\n" + short + "\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + short + "\n"})
        self.assertEqual(textreuse.scan(a, b, n=8, min_tokens=6).exit_code, 0)
        self.assertEqual(textreuse.scan(a, b, min_tokens=6).exit_code, 1)

    def test_match_source_is_reported_and_in_json(self):
        """每段带匹配来源：人读报告与 JSON 都要有，便于归因。"""
        a = self.side("A", {"a1.md": "# A\n\n" + PERTURBED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        result = textreuse.scan(a, b)
        seg = result.segments[0]
        self.assertIn(seg.match_source,
                      (textreuse.SRC_WORD_WINDOW, textreuse.SRC_SENTENCE))
        text = textreuse.render(result)
        self.assertIn(seg.match_source, text)
        payload = json.loads(run_textreuse(a, b, "--json").stdout)
        self.assertIn("match_source", payload["segments"][0])
        self.assertIn("scales", payload["summary"])
        self.assertIn("sentences", payload["summary"])

    def test_sentence_layer_does_not_fire_on_unrelated_pair(self):
        """负例：无关文档对不红（句级层也不能乱报）。"""
        a = self.side("A", {"a1.md": "# A\n\n" + CLEAN_A + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + CLEAN_B + ".\n"})
        self.assertEqual(textreuse.scan(a, b).exit_code, 0)

    def test_short_common_sentence_is_not_flagged(self):
        """短句整句撞车（共享 6 词）不得报——最少共享词数护栏。"""
        a = self.side("A", {"a1.md": "# A\n\nthe committee met on tuesday.\n"})
        b = self.side("B", {"b1.md": "# B\n\nthe committee met on tuesday.\n"})
        self.assertEqual(textreuse.scan(a, b).exit_code, 0)

    def test_sentence_threshold_is_configurable(self):
        """阈值可配：阈值以下的句级命中不再成立（旋钮真能拧）。"""
        a = self.side("A", {"a1.md": "# A\n\n" + REPLACED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        loose = textreuse.scan(a, b, sentence_threshold=0.8)
        strict = textreuse.scan(a, b, sentence_threshold=0.9)
        loose_sent = [s for s in loose.segments
                      if s.match_source == textreuse.SRC_SENTENCE]
        strict_sent = [s for s in strict.segments
                       if s.match_source == textreuse.SRC_SENTENCE]
        self.assertTrue(loose_sent)
        self.assertEqual(strict_sent, [])

    def test_bad_sentence_threshold_is_usage_error(self):
        a = self.side("A", {"a1.md": "# A\n\n" + CLEAN_A + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + CLEAN_B + ".\n"})
        with self.assertRaises(ConfigError) as ctx:
            textreuse.scan(a, b, sentence_threshold=1.5)
        self.assertEqual(ctx.exception.code,
                         textreuse.CODE_SENTENCE_THRESHOLD_RANGE)
        proc = run_textreuse(a, b, "--sentence-threshold", "0")
        self.assertEqual(proc.returncode, 2)

    def test_cli_no_sentences_switch(self):
        """CLI 开关：--no-sentences 关掉句级层。"""
        a = self.side("A", {"a1.md": "# A\n\n" + PERTURBED + ".\n"})
        b = self.side("B", {"b1.md": "# B\n\n" + PLANTED + ".\n"})
        self.assertEqual(run_textreuse(a, b).returncode, 1)
        self.assertEqual(run_textreuse(a, b, "--no-sentences").returncode, 0)


# --------------------------------------------------------------------------
# 分句口径
# --------------------------------------------------------------------------
class SentenceSplitting(unittest.TestCase):
    def test_sentences_split_on_terminal_punctuation(self):
        sents = textreuse.sentences("one two three. four five six!")
        self.assertEqual(len(sents), 2)
        self.assertEqual(sents[0], ["one", "two", "three"])
        self.assertEqual(sents[1], ["four", "five", "six"])

    def test_hard_wrap_does_not_split_sentence(self):
        sents = textreuse.sentences("one two\nthree four\nfive.")
        self.assertEqual(len(sents), 1)

    def test_blank_line_breaks_sentence(self):
        sents = textreuse.sentences("one two\n\nthree four")
        self.assertEqual(len(sents), 2)

    def test_abbreviation_and_decimal_do_not_split(self):
        sents = textreuse.sentences("Dr. Smith paid 3.5 dollars for it.")
        self.assertEqual(len(sents), 1)

    def test_initials_do_not_split(self):
        sents = textreuse.sentences("J. R. Smith arrived late.")
        self.assertEqual(len(sents), 1)


# --------------------------------------------------------------------------
# 用法错：exit 2，不静默放行
# --------------------------------------------------------------------------
class UsageErrors(TextReuseFixture):
    def test_missing_directory_raises_config_error(self):
        a = self.side("A", {"a1.md": CLEAN_A})
        with self.assertRaises(ConfigError) as ctx:
            textreuse.scan(a, self.tmp / "nope")
        self.assertEqual(ctx.exception.code, textreuse.CODE_DIR_MISSING)

    def test_file_instead_of_directory_is_config_error(self):
        a = self.side("A", {"a1.md": CLEAN_A})
        with self.assertRaises(ConfigError) as ctx:
            textreuse.scan(a, a / "a1.md")
        self.assertEqual(ctx.exception.code, textreuse.CODE_DIR_INVALID)

    def test_self_comparison_is_config_error(self):
        a = self.side("A", {"a1.md": CLEAN_A})
        with self.assertRaises(ConfigError) as ctx:
            textreuse.scan(a, a)
        self.assertEqual(ctx.exception.code, textreuse.CODE_SELF_COMPARE)
        self.assertIn("自身对账", str(ctx.exception))

    def test_n_out_of_range_is_config_error(self):
        a = self.side("A", {"a1.md": CLEAN_A})
        b = self.side("B", {"b1.md": CLEAN_B})
        for bad_n in (4, 21):
            with self.assertRaises(ConfigError) as ctx:
                textreuse.scan(a, b, n=bad_n)
            self.assertEqual(ctx.exception.code, textreuse.CODE_N_RANGE)

    def test_cli_exit_2_on_missing_dir(self):
        a = self.side("A", {"a1.md": CLEAN_A})
        proc = run_textreuse(a, self.tmp / "nope")
        self.assertEqual(proc.returncode, 2)

    def test_cli_exit_2_on_self_comparison(self):
        a = self.side("A", {"a1.md": CLEAN_A})
        proc = run_textreuse(a, a)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("自身对账", proc.stderr + proc.stdout)

    def test_cli_exit_2_on_usage_error(self):
        proc = subprocess.run([sys.executable, "-m", "factscribe", "textreuse"],
                              cwd=str(ROOT), capture_output=True, text=True,
                              env=dict(os.environ, PYTHONPATH=str(ROOT)))
        self.assertEqual(proc.returncode, 2)

    def test_cli_exit_2_on_bad_n(self):
        a = self.side("A", {"a1.md": CLEAN_A})
        b = self.side("B", {"b1.md": CLEAN_B})
        proc = run_textreuse(a, b, "--n", "99")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("5–20", proc.stdout + proc.stderr)
        payload = json.loads(run_textreuse(a, b, "--n", "99", "--json").stdout)
        self.assertEqual(payload["exit"], 2)
        self.assertEqual(payload["code"], textreuse.CODE_N_RANGE)

    def test_empty_side_is_config_error(self):
        a = self.side("A", {"a1.md": CLEAN_A})
        b = self.side("B", {})
        with self.assertRaises(ConfigError) as ctx:
            textreuse.scan(a, b)
        self.assertEqual(ctx.exception.code, textreuse.CODE_NO_FILES)


# --------------------------------------------------------------------------
# 性能：≥500KB 文本对，30 秒内出结果
# --------------------------------------------------------------------------
class Performance(unittest.TestCase):
    def test_500kb_pair_within_30s(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "A"
            b = root / "B"
            a.mkdir()
            b.mkdir()
            line = ("the calibration of the instrument followed the documented "
                    "procedure and the resulting measurements were archived with "
                    "their provenance metadata before the analysis was performed ")
            chunk = (line * 60).strip()
            body = "\n".join(chunk for _ in range(120))
            (a / "big.md").write_text(body, encoding="utf-8")
            (b / "big.md").write_text(body, encoding="utf-8")
            size = (a / "big.md").stat().st_size
            self.assertGreaterEqual(size, 500 * 1024)
            start = time.time()
            result = textreuse.scan(a, b)
            elapsed = time.time() - start
            self.assertEqual(result.exit_code, 1)
            self.assertLess(elapsed, 30.0)


if __name__ == "__main__":
    unittest.main()
