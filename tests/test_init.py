# -*- coding: utf-8 -*-
"""批 136：`factscribe init` 生成最小可用项目骨架。

本组测试只钉「契约面」：

- 七个文件齐全、TOML 可被工具自己的解析器读回；
- 目录非空拒绝（exit 2），`--force` 才覆盖同名文件（别的文件不动）；
- **确定性**：不写时间戳、不写绝对路径——同参数两次生成逐字节一致，
  `--title` 不同则不同；
- `--lang zh|en` 两套措辞；
- 生成后打印「下一步」三条命令；`--json` 出机器面。

跑法（仓根）：env PYTHONPATH=src python3 -m unittest discover -s tests
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

from factscribe.config import load_config, load_facts, load_toml  # noqa: E402

FILES = [
    "paperkit.toml",
    "main.tex",
    "sections/01-intro.tex",
    "facts/01-core.toml",
    "results/MANIFEST.toml",
    "refs.bib",
    "README.md",
]


def run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        capture_output=True, text=True, cwd=str(cwd or ROOT),
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))


def snapshot(root: Path) -> dict[str, bytes]:
    """目录下全部文件的字节快照（路径 → 内容），用于逐字节判等。"""
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


class TestInitFiles(unittest.TestCase):
    """生成面：文件齐全、可解析、骨架自洽。"""

    def test_creates_all_seven_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            proc = run("init", str(target))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for name in FILES:
                self.assertTrue((target / name).is_file(), name)

    def test_creates_missing_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a" / "b" / "paper"
            proc = run("init", str(target))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((target / "paperkit.toml").is_file())

    def test_project_toml_parses_and_declares_v1_skeleton(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            run("init", str(target), "--title", "Demo", "--author", "张三")
            data = load_toml(target / "paperkit.toml")
            proj = data["project"]
            self.assertEqual(proj["title"], "Demo")
            self.assertEqual(proj["authors"], ["张三"])
            self.assertEqual(proj["sections"], "sections/*.tex")
            self.assertEqual(proj["facts"], "facts/*.toml")
            self.assertEqual(proj["bib"], "refs.bib")
            self.assertEqual(proj["manifest"], "results/MANIFEST.toml")
            cfg = load_config(target)
            self.assertFalse(cfg.is_v3)
            self.assertEqual(cfg.title, "Demo")

    def test_empty_ledger_and_unsigned_manifest(self):
        """空账 + 留空的人签清单：这就是「新项目」应有的样子。"""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            run("init", str(target))
            self.assertEqual(load_facts(load_config(target)), [])
            manifest = load_toml(target / "results/MANIFEST.toml")
            self.assertEqual(manifest["manifest"]["signed_by"], "")
            self.assertEqual(manifest["files"], {})

    def test_main_tex_inputs_the_section_and_defines_fact_macro(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            run("init", str(target))
            text = (target / "main.tex").read_text(encoding="utf-8")
            self.assertIn("\\input{sections/01-intro}", text)
            self.assertIn("\\newcommand{\\fact}", text)
            body = (target / "sections/01-intro.tex").read_text(encoding="utf-8")
            self.assertIn("\\section{引言}", body)

    def test_author_is_tex_escaped_in_main_tex(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            run("init", str(target), "--title", "A & B", "--author", "50%_lab")
            text = (target / "main.tex").read_text(encoding="utf-8")
            self.assertIn("\\title{A \\& B}", text)
            self.assertIn("\\author{50\\%\\_lab}", text)


class TestInitRefusals(unittest.TestCase):
    """不安全的落盘必须拒绝（exit 2），且不留下半成品。"""

    def test_non_empty_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            target.mkdir()
            (target / "keep.txt").write_text("mine", encoding="utf-8")
            proc = run("init", str(target))
            self.assertEqual(proc.returncode, 2)
            self.assertIn("非空", proc.stderr)
            self.assertFalse((target / "paperkit.toml").exists())
            self.assertEqual((target / "keep.txt").read_text(encoding="utf-8"), "mine")

    def test_hidden_file_counts_as_non_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            target.mkdir()
            (target / ".git").mkdir()
            proc = run("init", str(target))
            self.assertEqual(proc.returncode, 2)

    def test_target_that_is_a_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            target.write_text("not a dir", encoding="utf-8")
            proc = run("init", str(target))
            self.assertEqual(proc.returncode, 2)
            self.assertIn("不是目录", proc.stderr)

    def test_force_overwrites_own_files_but_keeps_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            target.mkdir()
            (target / "paperkit.toml").write_text("junk = 1\n", encoding="utf-8")
            (target / "keep.txt").write_text("mine", encoding="utf-8")
            proc = run("init", str(target), "--force", "--title", "Forced")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(load_config(target).title, "Forced")
            self.assertEqual((target / "keep.txt").read_text(encoding="utf-8"), "mine")


class TestInitDeterminism(unittest.TestCase):
    """确定性：无时间戳、无绝对路径；同参数逐字节一致。"""

    def test_two_runs_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            run("init", str(a), "--title", "Demo", "--author", "张三")
            run("init", str(b), "--title", "Demo", "--author", "张三")
            self.assertEqual(snapshot(a), snapshot(b))

    def test_different_title_gives_different_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            run("init", str(a), "--title", "One")
            run("init", str(b), "--title", "Two")
            self.assertNotEqual(snapshot(a), snapshot(b))
            self.assertIn(b"One", (a / "paperkit.toml").read_bytes())
            self.assertIn(b"Two", (b / "paperkit.toml").read_bytes())

    def test_no_absolute_path_leaks_into_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            run("init", str(target))
            for name, blob in snapshot(target).items():
                text = blob.decode("utf-8")
                self.assertNotIn(str(target), text, name)
                self.assertNotIn(str(Path(tmp)), text, name)

    def test_no_wall_clock_timestamp(self):
        """模板里的占位说明可以有格式串，但生成面不许带一个具体年份日期。"""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            run("init", str(target))
            for name, blob in snapshot(target).items():
                text = blob.decode("utf-8")
                self.assertIsNone(
                    __import__("re").search(r"\b20\d{2}-\d{2}-\d{2}\b", text), name)


class TestInitLanguage(unittest.TestCase):
    """两套措辞：zh（默认）与 en。"""

    def test_zh_is_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            proc = run("init", str(target))
            self.assertIn("下一步", proc.stdout)
            readme = (target / "README.md").read_text(encoding="utf-8")
            self.assertIn("四步上手", readme)
            self.assertIn("未命名论文", readme)
            main = (target / "main.tex").read_text(encoding="utf-8")
            self.assertIn("ctex", main)

    def test_en_switches_all_wording(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            proc = run("init", str(target), "--lang", "en")
            self.assertIn("Next (three commands)", proc.stdout)
            readme = (target / "README.md").read_text(encoding="utf-8")
            self.assertIn("Four steps", readme)
            self.assertIn("Untitled Paper", readme)
            main = (target / "main.tex").read_text(encoding="utf-8")
            self.assertNotIn("ctex", main)
            self.assertIn("fontenc", main)

    def test_unknown_language_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            proc = run("init", str(target), "--lang", "fr")
            self.assertEqual(proc.returncode, 2)


class TestInitOutput(unittest.TestCase):
    """人读输出：下一步三条命令；机器面：--json。"""

    def test_prints_three_next_step_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            proc = run("init", str(target))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = proc.stdout
            self.assertIn("下一步（三条命令）", out)
            self.assertIn("fact add", out)
            self.assertIn("check", out)
            self.assertIn("matrix", out)
            steps = [ln for ln in out.splitlines()
                     if ln.strip().startswith(("1)", "2)", "3)"))]
            self.assertEqual(len(steps), 3, out)

    def test_json_payload_lists_files_and_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            proc = run("init", str(target), "--json")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual(data["command"], "init")
            self.assertEqual(data["exit"], 0)
            self.assertEqual(data["files"], FILES)
            self.assertEqual(data["lang"], "zh")
            self.assertEqual(len(data["next"]), 3)

    def test_json_error_for_non_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            target.mkdir()
            (target / "keep.txt").write_text("mine", encoding="utf-8")
            proc = run("init", str(target), "--json")
            self.assertEqual(proc.returncode, 2)
            data = json.loads(proc.stdout)
            self.assertEqual(data["command"], "init")
            self.assertEqual(data["exit"], 2)


if __name__ == "__main__":
    unittest.main()
