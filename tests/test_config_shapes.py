# -*- coding: utf-8 -*-
"""SPEC-V3.0 §10「项目配置（冻结）」与源层活跃正文判据的读取测试。

锁四件事：
1. 三种写法（扁平 schema / [project]+root_tex / [project]+sections）归一化一致；
2. 未知字段不静默（进 --json 的 config_warnings），但不改判据；
3. 缺闭包起点 exit 2 且点名；
4. 宏定义体/被丢弃的宏参数里的 \\fact{} 标记不算活跃正文。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import ConfigError, load_config, load_sections  # noqa: E402

CLI_ROOTS = str(ROOT)


def write_base(root: Path, toml_text: str, body: str = None,
               fact_value: str = "0.91") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(toml_text, encoding="utf-8")
    (root / "sections").mkdir(exist_ok=True)
    (root / "sections" / "main.tex").write_text(
        body if body is not None else
        "\\documentclass{article}\n\\begin{document}\n"
        "\\section{Results}\nThe effect is \\fact{A1}0.91.\n\\end{document}\n",
        encoding="utf-8")
    (root / "refs.bib").write_text("", encoding="utf-8")
    (root / "runs" / "r1").mkdir(parents=True, exist_ok=True)
    summary = root / "runs" / "r1" / "result.json"
    summary.write_text('{"run_id": "r1", "clause_count_effect": 0.91}\n',
                       encoding="utf-8")
    digest = hashlib.sha256(summary.read_bytes()).hexdigest()
    (root / "runs" / "r1" / "record.json").write_text(
        json.dumps({"run_id": "r1", "source": "runs/r1/result.json",
                    "source_sha256": "sha256:" + digest, "facts": ["A1"]}),
        encoding="utf-8")
    (root / "facts").mkdir(exist_ok=True)
    (root / "facts" / "A1.toml").write_text(
        'id = "A1"\nclaim = "effect"\nvalue = "%s"\nquantitative = true\n'
        'role = "results"\nsetting = "assembly"\nanchor = ["assembly"]\n'
        'source = "runs/r1/result.json"\n'
        'source_sha256 = "sha256:%s"\n' % (fact_value, digest),
        encoding="utf-8")
    return root


PROJECT_ROOT = """[project]
name = "demo"
root_tex = "sections/main.tex"
number_locale = "dot"
level = "l1"
"""

PROJECT_SECTIONS = """[project]
name = "demo"
sections = ["sections/main.tex"]
"""

FLAT_SCHEMA = """schema = "factscribe/3.0"
name = "demo"
root_tex = "sections/main.tex"
facts = "facts"
refs = "refs.bib"
"""


class TestThreeShapes(unittest.TestCase):
    def test_project_root_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_base(Path(tmp), PROJECT_ROOT))
            self.assertTrue(cfg.is_v3)
            self.assertEqual(cfg.config_shape, "project-root")
            self.assertEqual(cfg.schema, "paperkit-project/3.0")   # 缺省 schema 补齐
            self.assertEqual(cfg.name, "demo")
            self.assertEqual(cfg.root_tex, "sections/main.tex")
            self.assertEqual(cfg.level, "l1")
            self.assertEqual(cfg.number_locale, "period")          # dot 的规范名
            self.assertEqual([r for r, _ in load_sections(cfg)],
                             ["sections/main.tex"])

    def test_project_sections_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_base(Path(tmp), PROJECT_SECTIONS))
            self.assertTrue(cfg.is_v3)
            self.assertEqual(cfg.config_shape, "project-sections")
            self.assertEqual(cfg.section_files, ["sections/main.tex"])
            self.assertEqual(cfg.root_tex, "sections/main.tex")    # 首项推导
            self.assertEqual([r for r, _ in load_sections(cfg)],
                             ["sections/main.tex"])

    def test_flat_schema_shape_and_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_base(Path(tmp), FLAT_SCHEMA))
            self.assertTrue(cfg.is_v3)
            self.assertEqual(cfg.config_shape, "flat-schema")
            self.assertEqual(cfg.schema, "factscribe/3.0")
            self.assertEqual(cfg.facts_glob, "facts/*.toml")

    def test_sections_glob_is_still_v1(self):
        toml = ('[project]\ntitle = "old"\nsections = "sections/*.tex"\n'
                'facts = "facts/*.toml"\nroot_tex = "ignored.tex"\n')
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_base(Path(tmp), toml))
            self.assertFalse(cfg.is_v3)
            self.assertEqual(cfg.config_shape, "v1")
            self.assertEqual(cfg.root_tex, "")

    def test_single_file_sections_with_facts_is_v1(self):
        """单文件 sections 不再被误判成 V3（否则 fact add 会拒绝）。"""
        toml = ('[project]\ntitle = "old"\n'
                'sections = "sections/main.tex"\nfacts = "facts/*.toml"\n')
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_base(Path(tmp), toml))
            self.assertFalse(cfg.is_v3)
            self.assertEqual(cfg.config_shape, "v1")
            self.assertEqual(cfg.sections_glob, "sections/main.tex")

    def test_single_file_sections_with_v3_marker_stays_v3(self):
        """有 V3 标记（output/level…）时仍是 V3，不被单文件规则吞掉。"""
        toml = ('[project]\ntitle = "new"\n'
                'sections = "sections/main.tex"\nfacts = "facts/*.toml"\n'
                'level = "l2"\n')
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_base(Path(tmp), toml))
            self.assertTrue(cfg.is_v3)


class TestDefaultsAndErrors(unittest.TestCase):
    def test_level_alias_and_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_base(
                Path(tmp), PROJECT_ROOT.replace('level = "l1"', 'level = "2"')))
            self.assertEqual(cfg.level, "l2")
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_base(
                Path(tmp), PROJECT_ROOT.replace('level = "l1"\n', "")))
            self.assertEqual(cfg.level, "l1")                      # 默认 l1

    def test_bad_level_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(write_base(
                    Path(tmp), PROJECT_ROOT.replace('"l1"', '"l9"')))
            self.assertIn("level", str(ctx.exception))

    def test_missing_closure_seed_names_both(self):
        toml = '[project]\nname = "demo"\nnumber_locale = "dot"\nlevel = "l1"\n'
        with tempfile.TemporaryDirectory() as tmp:
            root = write_base(Path(tmp), toml)
            with self.assertRaises(ConfigError) as ctx:
                load_config(root)
            self.assertIn("root_tex", str(ctx.exception))
            self.assertIn("sections", str(ctx.exception))
            p = subprocess.run([sys.executable, "-m", "factscribe", "audit",
                                str(root), "--json"],
                               capture_output=True, text=True, cwd=CLI_ROOTS)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("root_tex", p.stdout)

    def test_unknown_field_warns_but_does_not_block(self):
        toml = PROJECT_ROOT + 'root_tx = "typo.tex"\ncolour = "red"\n'
        with tempfile.TemporaryDirectory() as tmp:
            root = write_base(Path(tmp), toml)
            cfg = load_config(root)
            fields = {w.get("field") for w in cfg.warnings}
            self.assertIn("root_tx", fields)
            self.assertIn("colour", fields)
            p = subprocess.run([sys.executable, "-m", "factscribe", "audit",
                                str(root), "--json"],
                               capture_output=True, text=True, cwd=CLI_ROOTS)
            data = json.loads(p.stdout)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            got = {w.get("field") for w in data["config_warnings"]}
            self.assertIn("root_tx", got)
            self.assertEqual({w["field"] for w in data["config"]["warnings"]},
                             got)
            self.assertEqual(data["config"]["shape"], "project-root")


class TestLiveTextBinding(unittest.TestCase):
    """宏藏标记 / 附录搬家 → 断言不在活跃正文里。"""

    def _run(self, root: Path) -> dict:
        p = subprocess.run([sys.executable, "-m", "factscribe", "audit",
                            str(root), "--json"],
                           capture_output=True, text=True, cwd=CLI_ROOTS)
        return json.loads(p.stdout)

    def test_marker_inside_macro_definition_is_not_live(self):
        body = ("\\documentclass{article}\n"
                "\\newcommand{\\fact}[1]{}\n"
                "\\newcommand{\\resulttab}{\\fact{A1}0.91}\n"
                "\\begin{document}\n\\section{Results}\n"
                "The effect is \\resulttab.\n\\end{document}\n")
        with tempfile.TemporaryDirectory() as tmp:
            data = self._run(write_base(Path(tmp), PROJECT_ROOT, body=body))
            codes = {f["code"] for f in data["findings"]}
            self.assertIn("ASSERTION_DRIFT", codes)
            self.assertEqual(data["exit"], 1)

    def test_marker_inside_discarded_macro_argument_is_not_live(self):
        body = ("\\documentclass{article}\n"
                "\\newcommand{\\fact}[1]{}\n"
                "\\newcommand{\\ignore}[1]{}\n"
                "\\begin{document}\n\\section{Results}\n"
                "\\ignore{The effect is \\fact{A1}0.91.}\n"
                "The effect is discussed here.\n\\end{document}\n")
        with tempfile.TemporaryDirectory() as tmp:
            data = self._run(write_base(Path(tmp), PROJECT_ROOT, body=body))
            codes = {f["code"] for f in data["findings"]}
            self.assertIn("APPROVAL_MISSING_ASSERTIONS", codes)
            self.assertIn("ASSERTION_DRIFT", codes)

    def test_marker_only_in_appendix_drifts(self):
        body = ("\\documentclass{article}\n"
                "\\newcommand{\\fact}[1]{}\n"
                "\\begin{document}\n\\section{Results}\n"
                "We state the effect in the appendix.\n"
                "\\appendix\n\\section{Effect}\n"
                "The effect is \\fact{A1}0.91.\n\\end{document}\n")
        with tempfile.TemporaryDirectory() as tmp:
            data = self._run(write_base(Path(tmp), PROJECT_ROOT, body=body))
            codes = [f["code"] for f in data["findings"]]
            self.assertIn("ASSERTION_DRIFT", codes)

    def test_live_marker_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._run(write_base(Path(tmp), PROJECT_ROOT))
            self.assertEqual(data["exit"], 0, data["findings"])
            self.assertEqual(data["findings"], [])


if __name__ == "__main__":
    unittest.main()
