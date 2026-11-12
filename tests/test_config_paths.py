# -*- coding: utf-8 -*-
"""配置里的路径不许越出项目根（v1 与 V3 同一口径）。

背景：`sections = "../elsewhere/*.tex"` 曾经 glob 到项目外，再算相对路径时
抛裸 `ValueError`（exit 4）；`facts` 更糟——直接读项目外的账本而**不报错**。
配置错必须是 exit 2，并点名是哪个键。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(*args):
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        capture_output=True, text=True, cwd=str(ROOT),
        env=dict(os.environ, PYTHONPATH=str(ROOT)))


def new_project(tmp: Path) -> Path:
    project = tmp / "proj"
    proc = run("init", str(project))
    assert proc.returncode == 0, proc.stderr
    return project


def set_key(project: Path, key: str, value: str) -> None:
    path = project / "paperkit.toml"
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("%s =" % key):
            line = '%s = "%s"' % (key, value)
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ConfigPathTest(unittest.TestCase):
    def test_sections_may_not_escape_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = new_project(base)
            outside = base / "outside"
            outside.mkdir()
            (outside / "x.tex").write_text("secret 999\n", encoding="utf-8")
            set_key(project, "sections", "../outside/*.tex")
            proc = run("audit", str(project))
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("sections", proc.stderr)
            self.assertIn("项目内相对路径", proc.stderr)
            self.assertNotIn("ValueError", proc.stderr)

    def test_facts_may_not_escape_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = new_project(base)
            outside = base / "outside"
            outside.mkdir()
            (outside / "x.toml").write_text("[[fact]]\n", encoding="utf-8")
            set_key(project, "facts", "../outside/*.toml")
            proc = run("check", str(project))
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("facts", proc.stderr)
            self.assertIn("项目内相对路径", proc.stderr)

    def test_absolute_sections_is_a_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project(Path(tmp))
            set_key(project, "sections", "/tmp/*.tex")
            proc = run("audit", str(project))
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("sections", proc.stderr)
            self.assertIn("项目内相对路径", proc.stderr)


if __name__ == "__main__":
    unittest.main()
