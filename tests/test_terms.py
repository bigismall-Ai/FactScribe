# -*- coding: utf-8 -*-
"""批 90：术语归一化与同义词层测试（SPEC-TERMS，全离线）。

覆盖：

* 拉丁文归一（NFKC / 小写 / 去空白 / 连字符）与全半角；
* 中文最长匹配边界（相关工作 / 相关工作里；机制 / 提示词对机制）；
* ``TERM_VARIANT`` 正例（一篇多写法）与负例（只用一种、仅大小写差异、
  阈值可调、不跨文件）；
* ``TERM_UNREGISTERED`` 只提示、不改退出码、白名单归一后命中；
* ``HEADING_ECHO`` 换同义表述后仍判为复述；
* ``TERM_FIRST_IN_HEADING`` 同义词视为同词；
* 导入脚本可重跑、覆盖生成。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import load_config, load_sections  # noqa: E402
from factscribe.style import analyze, load_style_rules  # noqa: E402
from factscribe.terms import (DEFAULT_GLOSSARY_PATH, key_of,  # noqa: E402
                              load_glossary, normalize_surface,
                              parse_glossary)

PROJECT_TOML = """[project]
title = "t"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""

GLOSSARY = (
    "canonical\taliases(en)\taliases(cn)\tcategory\n"
    "预注册\tpreregistration\t事前登记|预先登记\t写作\n"
    "预注册流程\tpreregistration pipeline\t事前登记流程\t写作\n"
    "工作\twork\t\t通用\n"
    "相关工作\trelated work\t\t通用\n"
    "机制\tmechanism\t\t通用\n"
    "提示词\tprompt\t\t通用\n"
    "提示词对机制\tprompt versus mechanism\t\t通用\n"
)


def make_project(base: Path, sections: dict, glossary: str | None = GLOSSARY,
                 rules: str | None = None,
                 extras: dict | None = None) -> Path:
    root = Path(base)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    for name, body in sections.items():
        (root / "sections" / name).write_text(body, encoding="utf-8")
    (root / "paperkit.toml").write_text(PROJECT_TOML, encoding="utf-8")
    if glossary is not None:
        (root / "glossary.tsv").write_text(glossary, encoding="utf-8")
    if rules is not None:
        (root / "style-rules.toml").write_text(rules, encoding="utf-8")
    for name, content in (extras or {}).items():
        (root / name).write_text(content, encoding="utf-8")
    return root


def analyze_text(base: Path, body: str, glossary: str | None = GLOSSARY,
                 rules: str | None = None,
                 extras: dict | None = None):
    root = make_project(base, {"01_main.tex": body}, glossary, rules, extras)
    cfg = load_config(root)
    loaded, path = load_style_rules(root)
    return analyze(cfg, load_sections(cfg), loaded, rules_path=path)


def codes(result) -> set:
    return {f.code for f in result.findings}


# --------------------------------------------------------------------------
# 1. 归一化与最长匹配（直接测 terms 模块）
# --------------------------------------------------------------------------

class TestNormalization(unittest.TestCase):
    def setUp(self):
        self.glossary = parse_glossary(GLOSSARY)

    def test_chinese_synonyms_share_canonical(self):
        for surface in ("预注册", "事前登记", "预先登记"):
            self.assertEqual(self.glossary.canonical_of(surface), "预注册")

    def test_latin_case_width_and_hyphen(self):
        for surface in ("Preregistration", "PRE-REGISTRATION",
                        "ｐｒｅｒｅｇｉｓｔｒａｔｉｏｎ"):
            self.assertEqual(self.glossary.canonical_of(surface), "预注册")

    def test_latin_normalize_surface(self):
        self.assertEqual(normalize_surface("  Pre-Registration  "),
                         "pre-registration")
        self.assertEqual(normalize_surface("ＡＢＣ"), "abc")

    def test_key_ignores_punctuation_width_and_space(self):
        self.assertEqual(key_of("ＡＢ，cd"), "abcd")
        self.assertEqual(key_of("pre - registration"), "preregistration")
        self.assertEqual(key_of("预 注 册，"), "预注册")

    def test_longest_match_prefers_longer_at_same_position(self):
        matches = self.glossary.matches("相关工作里，")
        self.assertEqual([m.canonical for m in matches], ["相关工作"])

    def test_longest_match_registered_phrase_beats_parts(self):
        matches = self.glossary.matches("提示词对机制")
        self.assertEqual([m.canonical for m in matches], ["提示词对机制"])

    def test_scan_finds_adjacent_registered_terms(self):
        glossary = parse_glossary(
            "canonical\taliases(en)\taliases(cn)\tcategory\n"
            "提示词\tprompt\t\t\n"
            "机制\tmechanism\t\t\n")
        matches = glossary.matches("提示词对机制")
        self.assertEqual([m.canonical for m in matches], ["提示词", "机制"])

    def test_latin_word_boundary(self):
        glossary = parse_glossary(
            "canonical\taliases(en)\taliases(cn)\tcategory\n"
            "编号\tid\t\t\n")
        self.assertEqual(glossary.matches("did"), [])
        self.assertEqual([m.surface for m in glossary.matches("the id field")],
                         ["id"])

    def test_unregistered_surface(self):
        self.assertIsNone(self.glossary.canonical_of("量子纠缠网络"))
        self.assertIsNone(self.glossary.canonical_of("unknown term"))

    def test_parse_skips_comments_and_header(self):
        glossary = parse_glossary(
            "# comment\n\ncanonical\taliases(en)\taliases(cn)\tcategory\n"
            "词册\tnomenclator\t术语册\t流程\n")
        self.assertEqual(len(glossary), 1)
        self.assertEqual(glossary.canonical_of("术语册"), "词册")
        self.assertEqual(glossary.form_count, 3)

    def test_default_glossary_loads_without_sia_harness(self):
        glossary = load_glossary(DEFAULT_GLOSSARY_PATH)
        self.assertGreater(len(glossary), 100)
        self.assertGreaterEqual(glossary.form_count, len(glossary))


# --------------------------------------------------------------------------
# 2. TERM_VARIANT
# --------------------------------------------------------------------------

VARIANT_THREE = (
    "预注册要求在收集数据前固定假设。\n\n"
    "事前登记让分析计划在见数据前冻结。\n\n"
    "预先登记还要求把原始日志一并留档。\n"
)


class TestTermVariant(unittest.TestCase):
    def test_positive_three_forms_reports_forms_and_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), VARIANT_THREE)
        self.assertIn("TERM_VARIANT", codes(result))
        hit = next(f for f in result.findings if f.code == "TERM_VARIANT")
        for form in ("预注册", "事前登记", "预先登记"):
            self.assertIn(form, hit.text)
        self.assertIn("第1行", hit.text)
        self.assertEqual(result.exit_code, 3)
        self.assertIn("TERM_VARIANT", {f["code"] for f in result.fired})

    def test_negative_single_form_repeated(self):
        body = ("预注册要求在收集数据前固定假设。\n\n"
                "这一节再次说明预注册的边界。\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), body)
        self.assertNotIn("TERM_VARIANT", codes(result))

    def test_negative_case_and_width_do_not_make_new_form(self):
        body = ("Preregistration fixes the analysis plan before data collection.\n\n"
                "ｐｒｅｒｅｇｉｓｔｒａｔｉｏｎ also covers the raw logs and the\n"
                "pre-registration record kept in the appendix.\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), body)
        self.assertNotIn("TERM_VARIANT", codes(result))

    def test_threshold_config(self):
        rules = "[thresholds]\nterm_variant_min_forms = 3\n"
        two_forms = ("预注册要求在收集数据前固定假设。\n\n"
                     "事前登记让分析计划在见数据前冻结。\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), two_forms, rules=rules)
        self.assertNotIn("TERM_VARIANT", codes(result))
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), VARIANT_THREE, rules=rules)
        self.assertIn("TERM_VARIANT", codes(result))

    def test_no_cross_file_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), {
                "01_a.tex": "预注册要求在收集数据前固定假设。\n",
                "02_b.tex": "事前登记让分析计划在见数据前冻结。\n",
            })
            cfg = load_config(root)
            loaded, path = load_style_rules(root)
            result = analyze(cfg, load_sections(cfg), loaded, rules_path=path)
        self.assertNotIn("TERM_VARIANT", codes(result))


# --------------------------------------------------------------------------
# 3. TERM_UNREGISTERED（只提示、不改退出码）
# --------------------------------------------------------------------------

UNREGISTERED = (
    "\\section{量子纠缠网络}\n\n"
    "量子纠缠网络的十六次远程测量读数与全部原始日志都放在附录里。\n"
)


class TestTermUnregistered(unittest.TestCase):
    def test_heading_hint_does_not_change_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), UNREGISTERED)
        self.assertIn("TERM_UNREGISTERED", codes(result))
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("term_unregistered",
                         {f["metric"] for f in result.fired})
        self.assertEqual(result.summary["triggered"], 0)
        hit = next(f for f in result.findings if f.code == "TERM_UNREGISTERED")
        self.assertIn("只提示", hit.suggestion)

    def test_registered_heading_term_has_no_hint(self):
        body = ("\\section{预注册流程}\n\n"
                "预注册流程固定假设，分析计划在见数据前冻结。\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), body)
        hints = [f.text for f in result.findings
                 if f.code == "TERM_UNREGISTERED"]
        self.assertNotIn("预注册流程", hints)

    def test_whitelist_suppresses_hint_after_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(
                Path(tmp), UNREGISTERED,
                extras={"term-allow.txt": "# user\n量子纠缠网络\n"})
        hints = [f.text for f in result.findings
                 if f.code == "TERM_UNREGISTERED"]
        self.assertNotIn("量子纠缠网络", hints)

    def test_first_sentence_hint(self):
        body = ("\\section{测量}\n\n"
                "我们报告量子纠缠网络的十六次远程读数与全部原始日志。\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), body)
        hints = [f.text for f in result.findings
                 if f.code == "TERM_UNREGISTERED"]
        self.assertTrue(any("量子纠缠网络" in x for x in hints))
        self.assertEqual(result.exit_code, 0)


# --------------------------------------------------------------------------
# 4. HEADING_ECHO / TERM_FIRST_IN_HEADING 按 canonical 比对
# --------------------------------------------------------------------------

ECHO_SYNONYM = (
    "\\section{预注册}\n\n"
    "事前登记。\n"
)

ECHO_SYNONYM_META = (
    "\\section{预注册}\n\n"
    "事前登记里，我们报告了十六单的读数。\n"
)

ECHO_SYNONYM_NEG = (
    "\\section{预注册}\n\n"
    "事前登记要求分析计划在收集数据前冻结，并记录十六次远程运行的读数。\n"
)


class TestCanonicalHeadingRules(unittest.TestCase):
    def test_heading_echo_still_caught_after_synonym(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), ECHO_SYNONYM)
        self.assertIn("HEADING_ECHO", codes(result))
        self.assertEqual(result.exit_code, 3)

    def test_heading_echo_meta_synonym(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), ECHO_SYNONYM_META)
        self.assertIn("HEADING_ECHO", codes(result))

    def test_heading_echo_negative_with_new_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), ECHO_SYNONYM_NEG)
        self.assertNotIn("HEADING_ECHO", codes(result))

    def test_term_first_accepts_synonym_definition(self):
        body = ("\\section{预注册流程}\n\n"
                "事前登记流程是在收集数据前固定假设与分析计划的做法。\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), body)
        self.assertNotIn("TERM_FIRST_IN_HEADING", codes(result))

    def test_term_first_still_reports_when_not_defined(self):
        body = ("\\section{预注册流程}\n\n"
                "我们报告十六次远程运行的读数与全部原始日志。\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(Path(tmp), body)
        self.assertIn("TERM_FIRST_IN_HEADING", codes(result))

    def test_whitelist_alias_suppresses_term_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(
                Path(tmp),
                "\\section{预注册流程}\n\n我们报告十六次运行的读数。\n",
                extras={"GLOSSARY.md": "# terms\n事前登记流程\n"})
        self.assertNotIn("TERM_FIRST_IN_HEADING", codes(result))


# --------------------------------------------------------------------------
# 5. 导入脚本
# --------------------------------------------------------------------------

class TestImportScript(unittest.TestCase):
    def test_import_is_repeatable_and_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "terms"
            src.mkdir()
            (src / "obj-x.yaml").write_text(
                "id: obj-x\nen: exemplar\ncn: 样例\n"
                "aliases: [示例, exemplar-alt]\ncategory: obj\n"
                "definition: 测试\nstatus: draft\nupdated: '2026-01-01'\n",
                encoding="utf-8")
            out = tmp / "glossary.tsv"
            cmd = [sys.executable, str(ROOT / "scripts" / "import-terms.py"),
                   "--source", str(src), "--out", str(out)]
            first = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                                   text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            text = out.read_text(encoding="utf-8")
            self.assertIn("exemplar", text)
            self.assertIn("示例", text)
            second = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                                    text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(out.read_text(encoding="utf-8"), text)
            parsed = parse_glossary(text)
            self.assertEqual(parsed.canonical_of("示例"), "样例")
            self.assertEqual(parsed.canonical_of("exemplar-alt"), "样例")


if __name__ == "__main__":
    unittest.main()
