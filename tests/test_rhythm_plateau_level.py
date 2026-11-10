# -*- coding: utf-8 -*-
"""批 109：RHYTHM_PLATEAU 默认降为参考读数（info）。

默认 `rhythm_plateau_level = "info"`：读数照常在 metrics 里，但只进
advisories（参考区），不进 findings、不影响退出码；设成 "yellow" 恢复旧行为。
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

PLATEAU_POS = (
    "The first run finished on time and kept every record in the shared ledger.\n"
    "The second run finished early and wrote the output to a separate file.\n"
    "The third run finished late and left a clear table of measured values.\n"
    "The fourth run closed the loop and saved the raw log for replay."
)


def make_project(tmp, body: str, rules: str | None = None) -> Path:
    root = Path(tmp)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections" / "01_main.tex").write_text(body, encoding="utf-8")
    (root / "paperkit.toml").write_text(PROJECT_TOML, encoding="utf-8")
    if rules is not None:
        (root / "style-rules.toml").write_text(rules, encoding="utf-8")
    return root


def analyze_text(tmp, body: str, rules: str | None = None):
    root = make_project(tmp, body, rules)
    cfg = load_config(root)
    loaded, path = load_style_rules(root)
    return analyze(cfg, load_sections(cfg), loaded, rules_path=path)


def run_style(root: Path, *args: str):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", "style", str(root), *args]
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


def codes(result) -> set:
    return {f.code for f in result.findings}


class TestRhythmPlateauLevel(unittest.TestCase):
    def test_default_info_not_in_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, PLATEAU_POS)
        self.assertEqual(result.metrics["rhythm_plateau"], 1)
        self.assertNotIn("RHYTHM_PLATEAU", codes(result))
        self.assertNotIn("rhythm_plateau", {f["metric"] for f in result.fired})
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.summary["findings"], 0)
        self.assertEqual([f.code for f in result.advisories],
                         ["RHYTHM_PLATEAU"])

    def test_yellow_config_restores_old_behaviour(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_text(tmp, PLATEAU_POS,
                                  'rhythm_plateau_level = "yellow"\n')
        self.assertIn("RHYTHM_PLATEAU", codes(result))
        self.assertEqual(result.exit_code, 3)
        self.assertEqual(result.advisories, [])
        hit = next(f for f in result.findings if f.code == "RHYTHM_PLATEAU")
        self.assertIn("短句", hit.suggestion)

    def test_human_output_has_reference_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, PLATEAU_POS)
            proc = run_style(root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[参考]", proc.stdout)
        self.assertIn("RHYTHM_PLATEAU", proc.stdout)
        self.assertIn("SENTENCE_UNIFORMITY", proc.stdout)
        self.assertIn("[黄] 0 处", proc.stdout)

    def test_json_separates_advisories_from_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, PLATEAU_POS)
            proc = run_style(root, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["findings"], [])
        self.assertEqual([f["code"] for f in payload["advisories"]],
                         ["RHYTHM_PLATEAU"])
        self.assertEqual(payload["metric_details"]["rhythm_plateau_level"],
                         "info")

    def test_invalid_level_is_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, PLATEAU_POS,
                                'rhythm_plateau_level = "red"\n')
            proc = run_style(root, "--json")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("rhythm_plateau_level", payload["message"])


if __name__ == "__main__":
    unittest.main()
