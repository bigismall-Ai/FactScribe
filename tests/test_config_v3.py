# -*- coding: utf-8 -*-
"""批 49：V3.0 扁平项目声明（paperkit-project/3.0）的读取测试。

只锁「配置能读、错误信息准确、v1 行为不变」；判据（keys 在项目外、
locale 签名、图片预算等）是 C 阶段的事，这里不测。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import (ConfigError, load_config, load_facts,  # noqa: E402
                               load_sections)

CLI_ROOTS = str(ROOT)

V3_TOML = """schema = "paperkit-project/3.0"
name = "demo"
root_tex = "main.tex"
output = "main.pdf"
signing_mode = "offline_manifest"
number_locale = "period"
approver_keys_file = "../_keys/demo/approver_keys.json"
release_keys_file = "../_keys/demo/release_keys.json"
image_budget_extra = 2
frac_allow = ["frac:A/B"]
"""

V3_FACT = """schema = "paperkit-fact/3.0"
id = "A1"
claim = "rate"
value = "10/16"
source = "runs/r1/summary.json"
display = ["10/16"]
"""

V1_TOML = """[project]
title = "old"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
root_tex = "ignored.tex"
"""


def make_v3(root: Path, toml_text: str = V3_TOML) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(toml_text, encoding="utf-8")
    (root / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}"
        "\\input{sections/body}\\end{document}\n", encoding="utf-8")
    (root / "sections").mkdir(exist_ok=True)
    (root / "sections" / "body.tex").write_text("plain text\n", encoding="utf-8")
    return root


class TestV3ProjectConfig(unittest.TestCase):
    def test_v3_fields_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp))
            cfg = load_config(root)
            self.assertTrue(cfg.is_v3)
            self.assertEqual(cfg.schema, "paperkit-project/3.0")
            self.assertEqual(cfg.name, "demo")
            self.assertEqual(cfg.title, "demo")
            self.assertEqual(cfg.root_tex, "main.tex")
            self.assertEqual(cfg.output, "main.pdf")
            self.assertEqual(cfg.signing_mode, "offline_manifest")
            self.assertEqual(cfg.number_locale, "period")
            self.assertTrue(cfg.approver_keys_file.endswith("approver_keys.json"))
            self.assertTrue(cfg.release_keys_file.endswith("release_keys.json"))
            self.assertEqual(cfg.image_budget_extra, 2)
            self.assertEqual(cfg.frac_allow, ["frac:A/B"])

    def test_v3_sections_start_at_root_tex(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp))
            cfg = load_config(root)
            got = [rel for rel, _ in load_sections(cfg)]
            self.assertEqual(got, ["main.tex", "sections/body.tex"])

    def test_v3_fact_file_flat_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp))
            (root / "facts").mkdir()
            (root / "facts" / "A1.toml").write_text(V3_FACT, encoding="utf-8")
            facts = load_facts(load_config(root))
            self.assertEqual([f.id for f in facts], ["A1"])
            self.assertEqual(facts[0].value, "10/16")
            self.assertTrue(facts[0].value_keys)

    def test_unknown_project_schema_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp),
                           V3_TOML.replace("paperkit-project/3.0",
                                           "paperkit-project/9.9"))
            with self.assertRaises(ConfigError) as ctx:
                load_config(root)
            self.assertIn("schema", str(ctx.exception))
            self.assertIn("9.9", str(ctx.exception))

    def test_unknown_fact_schema_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp))
            (root / "facts").mkdir()
            (root / "facts" / "A1.toml").write_text(
                V3_FACT.replace("paperkit-fact/3.0", "paperkit-fact/1.0"),
                encoding="utf-8")
            with self.assertRaises(ConfigError) as ctx:
                load_facts(load_config(root))
            self.assertIn("fact", str(ctx.exception))

    def test_missing_root_tex_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp), V3_TOML.replace('root_tex = "main.tex"\n', ""))
            with self.assertRaises(ConfigError) as ctx:
                load_config(root)
            self.assertIn("root_tex", str(ctx.exception))

    def test_bad_enum_and_type_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp),
                           V3_TOML.replace('signing_mode = "offline_manifest"',
                                           'signing_mode = "self_sign"'))
            with self.assertRaises(ConfigError):
                load_config(root)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp),
                           V3_TOML.replace("image_budget_extra = 2",
                                           "image_budget_extra = -1"))
            with self.assertRaises(ConfigError):
                load_config(root)

    def test_unknown_schema_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp),
                           V3_TOML.replace("paperkit-project/3.0",
                                           "paperkit-project/4.0"))
            p = subprocess.run(
                [sys.executable, "-m", "factscribe", "check", str(root)],
                capture_output=True, text=True, cwd=CLI_ROOTS)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("schema", p.stderr)


class TestV1Unchanged(unittest.TestCase):
    def test_v1_project_table_still_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "paperkit.toml").write_text(V1_TOML, encoding="utf-8")
            cfg = load_config(root)
            self.assertFalse(cfg.is_v3)
            self.assertEqual(cfg.schema, "")
            self.assertEqual(cfg.root_tex, "")      # v1 不认 root_tex，行为不变
            self.assertEqual(cfg.sections_glob, "sections/*.tex")
            self.assertEqual(cfg.title, "old")
            self.assertEqual(cfg.output, "main.pdf")
            self.assertEqual(cfg.number_locale, "period")

    def test_v1_missing_project_still_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "paperkit.toml").write_text('title = "x"\n', encoding="utf-8")
            with self.assertRaises(ConfigError) as ctx:
                load_config(root)
            self.assertIn("[project]", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
