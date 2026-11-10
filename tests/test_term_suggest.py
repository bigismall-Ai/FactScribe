# -*- coding: utf-8 -*-
"""批 98：术语候选抽取与人工入表测试（SPEC-TERM-SUGGEST，全离线）。

先写测试、后实现。覆盖：

* 中文埋点术语全部挖出；已入表词不重复出现；
* 英文多词短语挖出，``the model`` 这类泛词不出现；
* 围栏代码里的词不参与计数；
* ``--min-count`` / ``--min-sections`` 收紧后弱/局部候选消失；
* TSV 列名与 JSON 结构；
* ``terms add`` 只写人工 pick、留日期/来源注释、幂等、词表仍可解析；
* 双跑逐字节一致与排序确定性。

批 98b 追加（精度）：

* 中英文泛词表命中即丢，但泛词嵌在更长候选里（``system prompt`` /
  ``系统提示``）不受影响；
* LaTeX 命令参数（``\\ref{}`` / ``\\cite{}`` / ``\\label{}`` / ``\\fact{}``
  / ``\\input{}``）与模型名（``Flash`` / ``Pro`` / ``MiniMax-M3.1-Flash``）
  不进候选；
* 排序加分：标题 +3、定义句式 +2、中文专业后缀 +2、英文连字符/首字母
  大写 +1；加分只改排序、不改入选；
* 默认阈值改为 ``--min-count 4 --min-sections 3``。
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

from factscribe.term_suggest import (add_from_tsv, render_tsv,  # noqa: E402
                                     suggest)
from factscribe.terms import parse_glossary  # noqa: E402

EMPTY_GLOSSARY = ("canonical\taliases(en)\taliases(cn)\tcategory\tblocked(cn)\n")

ZH_CORPUS = {
    "a.md": """# 第一节

剂量反应曲线是核心指标。
变异系数，用于衡量离散程度。
预注册在数据收集前完成。

## 甲小节

剂量反应曲线的斜率稳定。
变异系数，与均值一起报告。
预注册，写在补充材料里。
""",
    "b.md": """# 第二节

剂量反应曲线，再次出现。
变异系数，再次出现。
预注册，再次出现。
""",
}

EN_CORPUS = {
    "a.md": """# First

System prompt, appears here.
Token budget, appears here.
The model, appears here.

## Sub

System prompt, again.
Token budget, again.
The model, again.
""",
    "b.md": """# Second

System prompt, third.
Token budget, third.
The model, third.
""",
}


def write_files(root: Path, files: dict) -> Path:
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def empty_glossary(root: Path) -> Path:
    path = root / "glossary-empty.tsv"
    path.write_text(EMPTY_GLOSSARY, encoding="utf-8")
    return path


def by_surface(rows) -> dict:
    return {row.surface: row for row in rows}


class CorpusCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.glossary = empty_glossary(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def rows(self, files: dict, **kwargs):
        write_files(self.root, files)
        kwargs.setdefault("glossary_path", self.glossary)
        return suggest(self.root, **kwargs)


# --------------------------------------------------------------------------
# 1. 中文候选
# --------------------------------------------------------------------------

class TestChineseCandidates(CorpusCase):
    def test_three_planted_terms_found(self):
        rows = by_surface(self.rows(ZH_CORPUS, min_count=3,
                                    min_sections=2))
        for term in ("剂量反应曲线", "变异系数", "预注册"):
            self.assertIn(term, rows, "漏掉中文术语：%s" % term)
            self.assertEqual(rows[term].lang, "zh")
            self.assertGreaterEqual(rows[term].count, 3)
            self.assertGreaterEqual(rows[term].sections, 2)

    def test_registered_term_is_excluded(self):
        glossary = self.root / "glossary-registered.tsv"
        glossary.write_text(EMPTY_GLOSSARY + "预注册\tpreregistration\t\t论文术语\t\n",
                            encoding="utf-8")
        rows = by_surface(self.rows(ZH_CORPUS, min_count=3,
                                    min_sections=2,
                                    glossary_path=glossary))
        self.assertNotIn("预注册", rows)
        self.assertIn("剂量反应曲线", rows)

    def test_sections_count_is_distinct_units(self):
        # 同一小节里重复两次只算一个小节。
        files = {"one.md": "# 甲\n\n局部词，出现。\n局部词，又出现。\n"}
        rows = by_surface(self.rows(files, min_count=2, min_sections=1))
        self.assertEqual(rows["局部词"].sections, 1)
        self.assertEqual(rows["局部词"].count, 2)

    def test_min_sections_filters_local_candidate(self):
        files = {"one.md": "# 甲\n\n局部术语，出现一次。\n局部术语，出现两次。\n局部术语，出现三次。\n局部术语，出现四次。\n"}
        write_files(self.root, files)
        # 默认 min-count=4 能过，但只在一个小节里，min-sections=3 卡掉。
        default = by_surface(suggest(self.root, glossary_path=self.glossary))
        relaxed = by_surface(suggest(self.root, glossary_path=self.glossary,
                                     min_sections=1))
        self.assertNotIn("局部术语", default)
        self.assertIn("局部术语", relaxed)

    def test_first_location_is_file_and_line(self):
        rows = by_surface(self.rows(
            {"only.md": "# 甲\n\n剂量反应曲线是核心指标。\n"},
            min_count=1, min_sections=1))
        self.assertEqual(rows["剂量反应曲线"].first_location, "only.md:3")


# --------------------------------------------------------------------------
# 2. 英文候选
# --------------------------------------------------------------------------

class TestEnglishCandidates(CorpusCase):
    def test_multiword_terms_found(self):
        rows = by_surface(self.rows(EN_CORPUS, min_count=3,
                                    min_sections=2))
        for term in ("system prompt", "token budget"):
            self.assertIn(term, rows, "漏掉英文短语：%s" % term)
            self.assertEqual(rows[term].lang, "en")
            self.assertEqual(rows[term].count, 3)

    def test_generic_the_model_absent(self):
        rows = by_surface(self.rows(EN_CORPUS))
        self.assertNotIn("model", rows)
        self.assertNotIn("the model", rows)

    def test_case_variants_merge(self):
        files = {
            "a.md": "# A\n\nSystem prompt, one.\n",
            "b.md": "# B\n\nsystem prompt, two.\n",
            "c.md": "# C\n\nsystem prompt, three.\n",
        }
        rows = by_surface(self.rows(files, min_count=3, min_sections=2))
        self.assertIn("system prompt", rows)
        self.assertEqual(rows["system prompt"].count, 3)

    def test_single_capitalized_or_hyphenated_word_allowed(self):
        files = {
            "a.md": "# A\n\nfail-closed, one.\nfail-closed, two.\n",
            "b.md": "# B\n\nfail-closed, three.\n",
        }
        rows = by_surface(self.rows(files, min_count=3, min_sections=2))
        self.assertIn("fail-closed", rows)


# --------------------------------------------------------------------------
# 3. 遮罩、阈值与输出
# --------------------------------------------------------------------------

class TestMaskingAndOutput(CorpusCase):
    def test_chinese_code_block_masked(self):
        files = {"code.md": """
# 甲

正文里没有术语。

```text
剂量反应曲线
剂量反应曲线
剂量反应曲线
剂量反应曲线
```
"""}
        rows = by_surface(self.rows(files, min_count=1, min_sections=1))
        self.assertNotIn("剂量反应曲线", rows)

    def test_english_code_block_masked(self):
        files = {"code.md": """
# A

No term in prose.

```text
system prompt
system prompt
system prompt
system prompt
```
"""}
        rows = by_surface(self.rows(files, min_count=1, min_sections=1))
        self.assertNotIn("system prompt", rows)

    def test_min_count_filters_weak_candidate(self):
        files = {
            "a.md": "# 甲\n\n弱候选，出现。\n弱候选，再现。\n",
            "b.md": "# 乙\n\n弱候选，最后一次。\n",
        }
        # 三处出现、两小节：显式 min-count=3,min-sections=2 收；默认 4/3 卡掉。
        self.assertIn("弱候选", by_surface(self.rows(
            files, min_count=3, min_sections=2)))
        self.assertNotIn("弱候选", by_surface(self.rows(files)))

    def test_tsv_header_and_columns(self):
        text = render_tsv(suggest(self.root, glossary_path=self.glossary))
        self.assertEqual(text.splitlines()[0],
                         "surface\tlang\tcount\tsections\tfirst_location\tscore")

    def test_json_shape_via_cli(self):
        write_files(self.root, {"a.md": (
            "# 甲\n\n剂量反应曲线。\n剂量反应曲线。\n"
            "\n## 乙\n\n剂量反应曲线。\n"
            "\n## 丙\n\n剂量反应曲线。\n")})
        proc = run_cli(self.root, "terms", "suggest", ".", "--json",
                       "--glossary", str(self.glossary))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["tool"], "terms")
        self.assertEqual(payload["action"], "suggest")
        self.assertEqual(payload["min_count"], 4)
        self.assertEqual(payload["min_sections"], 3)
        self.assertEqual(payload["count"], len(payload["candidates"]))
        row = payload["candidates"][0]
        self.assertEqual(set(row), {"surface", "lang", "count", "sections",
                                    "first_location", "score"})

    def test_output_is_byte_identical_twice(self):
        write_files(self.root, ZH_CORPUS)
        first = self.root / "one.tsv"
        second = self.root / "two.tsv"
        for out in (first, second):
            proc = run_cli(self.root, "terms", "suggest", ".",
                           "--glossary", str(self.glossary),
                           "--min-count", "3", "--min-sections", "2",
                           "--out", str(out))
            self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_sort_is_score_desc_then_surface(self):
        write_files(self.root, ZH_CORPUS)
        rows = suggest(self.root, glossary_path=self.glossary)
        keys = [(-row.score, row.surface) for row in rows]
        self.assertEqual(keys, sorted(keys))

    def test_missing_root_is_usage_error(self):
        proc = run_cli(self.root, "terms", "suggest", "no-such-dir")
        self.assertEqual(proc.returncode, 2)


# --------------------------------------------------------------------------
# 4. terms add
# --------------------------------------------------------------------------

class TestTermsAdd(CorpusCase):
    def _candidates(self, surface: str = "剂量反应曲线") -> Path:
        path = self.root / "candidates.tsv"
        path.write_text(
            "surface\tlang\tcount\tsections\tfirst_location\tscore\n"
            "%s\tzh\t5\t3\ta.md:3\t15\n"
            "变异系数\tzh\t4\t2\tb.md:2\t8\n" % surface,
            encoding="utf-8")
        return path

    def test_add_writes_row_category_and_comment(self):
        glossary = self.root / "paper.tsv"
        glossary.write_text(EMPTY_GLOSSARY, encoding="utf-8")
        cand = self._candidates()
        info = add_from_tsv(cand, ["剂量反应曲线"], glossary_path=glossary)
        text = glossary.read_text(encoding="utf-8")
        self.assertIn("剂量反应曲线\t\t\t待分类", text)
        self.assertIn("# terms add ", text)
        self.assertIn(str(cand), text)
        self.assertEqual(info["added"], ["剂量反应曲线"])
        parsed = parse_glossary(text)
        self.assertEqual(parsed.canonical_of("剂量反应曲线"), "剂量反应曲线")
        self.assertIsNone(parsed.canonical_of("变异系数"))

    def test_add_is_idempotent(self):
        glossary = self.root / "paper.tsv"
        glossary.write_text(EMPTY_GLOSSARY, encoding="utf-8")
        cand = self._candidates()
        add_from_tsv(cand, ["剂量反应曲线"], glossary_path=glossary)
        add_from_tsv(cand, ["剂量反应曲线"], glossary_path=glossary)
        text = glossary.read_text(encoding="utf-8")
        self.assertEqual(text.count("剂量反应曲线\t\t\t待分类"), 1)

    def test_add_unknown_pick_is_usage_error(self):
        glossary = self.root / "paper.tsv"
        glossary.write_text(EMPTY_GLOSSARY, encoding="utf-8")
        proc = run_cli(self.root, "terms", "add",
                       "--from", str(self._candidates()),
                       "--pick", "不存在的词",
                       "--glossary", str(glossary))
        self.assertEqual(proc.returncode, 2)

    def test_add_then_style_still_parses(self):
        glossary = self.root / "paper.tsv"
        glossary.write_text(EMPTY_GLOSSARY, encoding="utf-8")
        add_from_tsv(self._candidates(), ["剂量反应曲线"],
                     glossary_path=glossary)
        rules = self.root / "style-rules.toml"
        rules.write_text('term_glossary = "%s"\n' % glossary, encoding="utf-8")
        doc = self.root / "doc.md"
        doc.write_text("# 甲\n\n剂量反应曲线是核心指标。\n", encoding="utf-8")
        proc = run_cli(self.root, "style", "--doc", "doc.md",
                       "--rules", str(rules), "--json")
        self.assertIn(proc.returncode, (0, 3), proc.stderr)
        self.assertNotIn("内部错误", proc.stderr)


# --------------------------------------------------------------------------
# 5. LaTeX 项目入口
# --------------------------------------------------------------------------

class TestLatexProject(CorpusCase):
    def test_project_sections_and_verbatim_masking(self):
        write_files(self.root, {
            "paperkit.toml": ("[project]\ntitle = \"t\"\n"
                              "sections = \"sections/*.tex\"\n"
                              "facts = \"facts/*.toml\"\n"),
            "facts/empty.toml": "",
            "sections/01.tex": (
                "\\section{甲}\n"
                "剂量反应曲线是核心指标。\n"
                "\\begin{verbatim}\n剂量反应曲线\n剂量反应曲线\n\\end{verbatim}\n"),
            "sections/02.tex": (
                "\\section{乙}\n"
                "变异系数，与均值一起报告。\n"
                "剂量反应曲线，再次出现。\n"),
        })
        rows = by_surface(suggest(self.root, glossary_path=self.glossary,
                                   min_count=2, min_sections=2))
        self.assertIn("剂量反应曲线", rows)
        self.assertEqual(rows["剂量反应曲线"].count, 2)  # verbatim 里两处不计
        self.assertTrue(rows["剂量反应曲线"].first_location.startswith(
            "sections/01.tex:"))


# --------------------------------------------------------------------------
# 6. 精度：泛词、遮罩与加分（批 98b）
# --------------------------------------------------------------------------

class TestGenericStoplist(CorpusCase):
    def test_chinese_generic_words_filtered(self):
        files = {
            "a.md": "# 第一节\n\n模型。\n任务。\n剂量反应曲线。\n变异系数。\n"
                    "\n## 甲小节\n\n模型。\n任务。\n剂量反应曲线。\n变异系数。\n",
            "b.md": "# 第二节\n\n模型。\n任务。\n剂量反应曲线。\n变异系数。\n",
        }
        rows = by_surface(self.rows(files, min_count=3, min_sections=3))
        self.assertNotIn("模型", rows)
        self.assertNotIn("任务", rows)
        self.assertIn("剂量反应曲线", rows)
        self.assertIn("变异系数", rows)

    def test_english_generic_words_filtered(self):
        files = {
            "a.md": "# First\n\nSystem prompt.\nTable.\nFlash.\n"
                    "MiniMax-M3.1-Flash.\n"
                    "\n## Sub\n\nSystem prompt.\nTable.\nFlash.\n"
                    "MiniMax-M3.1-Flash.\n",
            "b.md": "# Second\n\nSystem prompt.\nTable.\nFlash.\n"
                    "MiniMax-M3.1-Flash.\n",
        }
        rows = by_surface(self.rows(files, min_count=3, min_sections=3))
        self.assertNotIn("table", rows)
        for surface in rows:
            self.assertNotIn("flash", surface)
            self.assertNotIn("minimax", surface)
        self.assertIn("system prompt", rows)

    def test_generic_inside_longer_term_survives(self):
        files = {
            "a.md": "# 甲\n\n系统提示。\nmodel compression.\n"
                    "\n## 乙\n\n系统提示。\nmodel compression.\n"
                    "\n## 丙\n\n系统提示。\nmodel compression.\n",
        }
        rows = by_surface(self.rows(files, min_count=3, min_sections=3))
        # 系统 / model 是泛词，但嵌在更长候选里不受影响。
        self.assertIn("系统提示", rows)
        self.assertIn("model compression", rows)


class TestNoiseMasking(CorpusCase):
    def test_latex_command_arguments_masked(self):
        files = {"a.tex": (
            "\\section{甲}\n"
            "See \\ref{tab:x} and \\ref{tab:x}.\n"
            "\\label{sec:y} \\cite{smith2020}.\n"
            "\\fact{D1} \\input{foo/bar}.\n")}
        rows = by_surface(self.rows(files, min_count=1, min_sections=1))
        for surface in ("tab", "x", "sec", "y", "smith2020", "d1",
                        "foo", "bar"):
            self.assertNotIn(surface, rows, "LaTeX 参数漏进候选：%s" % surface)

    def test_latex_snippets_in_markdown_masked(self):
        files = {"a.md": (
            "# A\n\n"
            "See \\ref{tab:x} and \\ref{tab:x}.\n"
            "\\label{sec:y} \\cite{smith2020}.\n"
            "\\fact{D1} \\input{foo/bar}.\n")}
        rows = by_surface(self.rows(files, min_count=1, min_sections=1))
        for surface in ("tab", "x", "sec", "y", "smith2020", "d1",
                        "foo", "bar"):
            self.assertNotIn(surface, rows)

    def test_model_names_masked(self):
        files = {"a.md": (
            "# A\n\n"
            "DeepSeek V4.1 Flash is used.\n"
            "MiniMax-M3.1-Flash is used.\n"
            "Flash is used.\nPro is used.\n"
            "MiniMax is used.\n")}
        rows = by_surface(self.rows(files, min_count=1, min_sections=1))
        for surface in rows:
            lowered = surface.lower()
            for marker in ("flash", "minimax", "deepseek", "v4.1"):
                self.assertNotIn(marker, lowered,
                                 "模型名漏进候选：%s" % surface)


class TestScoringBonuses(CorpusCase):
    def test_heading_term_ranks_higher(self):
        files = {
            "a.md": "# 预注册\n\n预注册。\n随机化。\n"
                    "\n## 甲\n\n预注册。\n随机化。\n",
            "b.md": "# 乙\n\n预注册。\n随机化。\n",
        }
        rows = self.rows(files, min_count=3, min_sections=3)
        surfaces = [row.surface for row in rows]
        self.assertIn("预注册", surfaces)
        self.assertIn("随机化", surfaces)
        self.assertLess(surfaces.index("预注册"), surfaces.index("随机化"))

    def test_definition_adjacent_term_ranks_higher(self):
        files = {
            "a.md": "# 甲\n\n灰盒测试是指标。\n白盒测试，指标。\n"
                    "\n## 乙\n\n灰盒测试是指标。\n白盒测试，指标。\n"
                    "\n## 丙\n\n灰盒测试是指标。\n白盒测试，指标。\n",
        }
        rows = self.rows(files, min_count=3, min_sections=3)
        surfaces = [row.surface for row in rows]
        self.assertIn("灰盒测试", surfaces)
        self.assertIn("白盒测试", surfaces)
        self.assertLess(surfaces.index("灰盒测试"), surfaces.index("白盒测试"))

    def test_chinese_professional_suffix_ranks_higher(self):
        files = {
            "a.md": "# 甲\n\n变异系数。\n预注册。\n"
                    "\n## 乙\n\n变异系数。\n预注册。\n"
                    "\n## 丙\n\n变异系数。\n预注册。\n",
        }
        rows = self.rows(files, min_count=3, min_sections=3)
        surfaces = [row.surface for row in rows]
        self.assertLess(surfaces.index("变异系数"), surfaces.index("预注册"))

    def test_english_hyphen_ranks_higher(self):
        files = {
            "a.md": "# A\n\nfail-closed.\nclosed loop.\n"
                    "\n## B\n\nfail-closed.\nclosed loop.\n"
                    "\n## C\n\nfail-closed.\nclosed loop.\n",
        }
        rows = self.rows(files, min_count=3, min_sections=3)
        surfaces = [row.surface for row in rows]
        self.assertIn("fail-closed", surfaces)
        self.assertIn("closed loop", surfaces)
        self.assertLess(surfaces.index("fail-closed"),
                        surfaces.index("closed loop"))

    def test_bonus_does_not_change_inclusion(self):
        # 同一份语料里，有加分与无加分的候选都过阈值，只是排序不同。
        files = {
            "a.md": "# A\n\nfail-closed.\nclosed loop.\n"
                    "\n## B\n\nfail-closed.\nclosed loop.\n"
                    "\n## C\n\nfail-closed.\nclosed loop.\n",
        }
        rows = self.rows(files, min_count=3, min_sections=3)
        self.assertEqual(len(rows), 2)


class TestDefaultThresholds(CorpusCase):
    def test_default_is_4_3(self):
        files = {
            "a.md": "# 甲\n\n弱候选。\n"
                    "\n## 乙\n\n弱候选。\n"
                    "\n## 丙\n\n弱候选。\n",
        }
        # 3 次出现、3 个小节：默认 4/3 卡 count；显式 3/3 才收。
        self.assertNotIn("弱候选",
                         by_surface(self.rows(files)))
        self.assertIn("弱候选", by_surface(self.rows(
            files, min_count=3, min_sections=3)))


def run_cli(cwd, *args, stdin=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        cwd=str(cwd), capture_output=True, text=True, env=env, input=stdin)


if __name__ == "__main__":
    unittest.main()
