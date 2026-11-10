# -*- coding: utf-8 -*-
"""build 自动编译 PDF 的测试（批 120）。

全部离线：用假的 tectonic 可执行脚本模拟成功/字体报错/硬失败，不依赖真 TeX。
规范：docs/design/SPEC-BUILD.md。
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from factscribe.buildpdf import pdf_page_count, rewrite_cjk_font  # noqa: E402

EN_TEX = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "Hello 10/16.\n"
    "\\end{document}\n"
)
ZH_TEX = (
    "\\documentclass[UTF8,11pt,fontset=fandol]{ctexart}\n"
    "\\begin{document}\n"
    "你好，10/16。\n"
    "\\end{document}\n"
)

FAKE_ENGINE = r"""#!/bin/sh
# 假 tectonic：按 __MODE__ 决定行为；成功时在 cwd 写一个 3 页 PDF。
log="${FAKE_LOG:-}"
if [ -n "$log" ]; then
  printf '%s\n' "$PWD" >> "$log"
fi
mode="__MODE__"
case "$mode" in
  ok)
    ;;
  font_then_ok)
    if grep -q "fontset=fandol" main.tex 2>/dev/null; then
      echo "error: CTeX fontset 'fandol' could not be found" >&2
      exit 1
    fi
    ;;
  always_fail)
    i=1
    while [ "$i" -le 30 ]; do
      echo "fail line $i" >&2
      i=$((i + 1))
    done
    exit 1
    ;;
esac
printf '%%PDF-1.4\n' > main.pdf
printf '1 0 obj << /Type /Pages /Count 3 >> endobj\n' >> main.pdf
printf '2 0 obj << /Type /Page /Parent 1 0 R >> endobj\n' >> main.pdf
printf '3 0 obj << /Type /Page /Parent 1 0 R >> endobj\n' >> main.pdf
printf '4 0 obj << /Type /Page /Parent 1 0 R >> endobj\n' >> main.pdf
printf 'trailer << /Root 1 0 R >>\n%%%%EOF\n' >> main.pdf
exit 0
"""


def write_engine(directory: Path, mode: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "fake-tectonic"
    path.write_text(FAKE_ENGINE.replace("__MODE__", mode), encoding="utf-8")
    path.chmod(0o755)
    return path


def make_project(tmp, build="", tex=EN_TEX):
    root = Path(tmp) / "proj"
    (root / "sections").mkdir(parents=True)
    (root / "facts").mkdir()
    (root / "sections" / "a.tex").write_text("占位正文\n", encoding="utf-8")
    (root / "refs.bib").write_text("", encoding="utf-8")
    (root / "paperkit.toml").write_text(
        '[project]\ntitle = "t"\nauthors = ["a"]\n'
        'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
        'bib = "refs.bib"\nbuild = "%s"\n' % build, encoding="utf-8")
    if tex is not None:
        (root / "main.tex").write_text(tex, encoding="utf-8")
    return root


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    return subprocess.run([sys.executable, "-m", "factscribe"] + args,
                          capture_output=True, text=True, cwd=str(ROOT))


def run_json(args):
    p = run(args)
    return p.returncode, json.loads(p.stdout)


class TestShellBuildUnchanged(unittest.TestCase):
    def test_shell_build_path_unchanged(self):
        """project.build 非空：照旧跑 shell，不走自动路径。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "always_fail")
            root = make_project(tmp, build="sh -c 'echo built > out.txt'")
            code, data = run_json(["build", str(root), "--json",
                                   "--engine", str(engine)])
            self.assertEqual(code, 0, data)
            self.assertTrue((root / "out.txt").is_file())
            self.assertFalse((root / "main.pdf").exists())
            self.assertNotIn("engine", data)

    def test_shell_build_failure_keeps_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, build="false")
            p = run(["build", str(root)])
            self.assertEqual(p.returncode, 1)
            self.assertIn("构建失败", p.stdout)

    def test_shell_path_ignores_missing_engine(self):
        """非空 build 不碰引擎：引擎不存在也不影响原行为。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, build="sh -c 'echo ok > out.txt'")
            code, _data = run_json(["build", str(root), "--json",
                                    "--engine", "/nonexistent/tectonic"])
            self.assertEqual(code, 0)
            self.assertTrue((root / "out.txt").is_file())


class TestAutoBuildSuccess(unittest.TestCase):
    def test_english_success_creates_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            root = make_project(tmp)
            code, data = run_json(["build", str(root), "--json",
                                   "--engine", str(engine)])
            self.assertEqual(code, 0, data)
            pdf = root / "main.pdf"
            self.assertTrue(pdf.is_file())
            self.assertEqual(data["pdf_bytes"], pdf.stat().st_size)
            self.assertEqual(data["pdf_pages"], 3)
            self.assertEqual(len(data["attempts"]), 1)
            self.assertEqual(data["attempts"][0]["mode"], "direct")

    def test_source_tex_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            root = make_project(tmp)
            before = sha(root / "main.tex")
            tree_before = sorted(p.name for p in root.iterdir())
            code, _data = run_json(["build", str(root), "--json",
                                    "--engine", str(engine)])
            self.assertEqual(code, 0)
            self.assertEqual(sha(root / "main.tex"), before)
            self.assertEqual(sorted(p.name for p in root.iterdir()),
                             sorted(tree_before + ["main.pdf"]))

    def test_no_intermediate_files_in_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            root = make_project(tmp)
            code, _data = run_json(["build", str(root), "--json",
                                    "--engine", str(engine)])
            self.assertEqual(code, 0)
            leftovers = [p.name for p in root.iterdir()
                         if p.suffix in (".aux", ".log", ".toc", ".out")]
            self.assertEqual(leftovers, [])

    def test_json_payload_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            root = make_project(tmp)
            code, data = run_json(["build", str(root), "--json",
                                   "--engine", str(engine)])
            self.assertEqual(code, 0)
            for key in ("engine", "engine_requested", "attempts",
                        "pdf_bytes", "pdf_pages", "pdf_path"):
                self.assertIn(key, data)
            self.assertEqual(data["engine"], str(engine))
            self.assertEqual(data["pdf_path"], str(root / "main.pdf"))
            self.assertEqual(data["severity"], "ok")

    def test_default_cleans_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            root = make_project(tmp)
            code, data = run_json(["build", str(root), "--json",
                                   "--engine", str(engine)])
            self.assertEqual(code, 0)
            self.assertIsNone(data["temp_dir"])

    def test_keep_temp_keeps_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            root = make_project(tmp)
            code, data = run_json(["build", str(root), "--json",
                                   "--engine", str(engine), "--keep-temp"])
            self.assertEqual(code, 0)
            kept = Path(data["temp_dir"])
            try:
                self.assertTrue(kept.is_dir())
                self.assertTrue((kept / "project" / "main.tex").is_file())
                self.assertTrue((kept / "project" / "main.pdf").is_file())
            finally:
                shutil.rmtree(kept, ignore_errors=True)


class TestCjkFontFallback(unittest.TestCase):
    def test_fontset_failure_retries_then_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "font_then_ok")
            root = make_project(tmp, tex=ZH_TEX)
            code, data = run_json(["build", str(root), "--json",
                                   "--engine", str(engine), "--keep-temp"])
            self.assertEqual(code, 0, data)
            try:
                self.assertEqual(len(data["attempts"]), 2)
                self.assertEqual(data["attempts"][0]["mode"], "direct")
                self.assertFalse(data["attempts"][0]["ok"])
                self.assertEqual(data["attempts"][1]["mode"], "temp-cjk-font")
                self.assertTrue(data["attempts"][1]["ok"])
                self.assertTrue((root / "main.pdf").is_file())
            finally:
                shutil.rmtree(Path(data["temp_dir"]), ignore_errors=True)

    def test_retry_only_touches_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "font_then_ok")
            root = make_project(tmp, tex=ZH_TEX)
            before = sha(root / "main.tex")
            code, data = run_json(["build", str(root), "--json",
                                   "--engine", str(engine), "--keep-temp"])
            self.assertEqual(code, 0, data)
            kept = Path(data["temp_dir"])
            try:
                self.assertEqual(sha(root / "main.tex"), before)
                source = (root / "main.tex").read_text(encoding="utf-8")
                self.assertIn("fontset=fandol", source)
                self.assertNotIn("setCJKmainfont", source)
                patched = (kept / "project" / "main.tex").read_text(
                    encoding="utf-8")
                self.assertIn("fontset=none", patched)
                self.assertNotIn("fontset=fandol", patched)
                self.assertIn("\\setCJKmainfont[Path=", patched)
                self.assertIn("BoldFont=", patched)
            finally:
                shutil.rmtree(kept, ignore_errors=True)

    def test_cjk_font_flag_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "font_then_ok")
            font = Path(tmp) / "fonts" / "MyFont.ttf"
            font.parent.mkdir(parents=True)
            font.write_bytes(b"fake font bytes")
            root = make_project(tmp, tex=ZH_TEX)
            code, data = run_json(["build", str(root), "--json",
                                   "--engine", str(engine),
                                   "--cjk-font", str(font), "--keep-temp"])
            self.assertEqual(code, 0, data)
            kept = Path(data["temp_dir"])
            try:
                patched = (kept / "project" / "main.tex").read_text(
                    encoding="utf-8")
                self.assertIn(
                    "\\setCJKmainfont[Path=%s/,BoldFont=MyFont.ttf]{MyFont.ttf}"
                    % font.parent, patched)
            finally:
                shutil.rmtree(kept, ignore_errors=True)


class TestAutoBuildFailures(unittest.TestCase):
    def test_missing_main_tex_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            root = make_project(tmp, tex=None)
            code, data = run_json(["build", str(root), "--json",
                                   "--engine", str(engine)])
            self.assertEqual(code, 2)
            self.assertIn("main.tex", data["output"])

    def test_missing_engine_exit_8(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            p = run(["build", str(root), "--engine",
                     "/nonexistent/tectonic"])
            self.assertEqual(p.returncode, 8)
            self.assertIn("PDF_TOOL_MISSING", p.stdout)

    def test_compile_failure_exit_4_keeps_last_20_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "always_fail")
            root = make_project(tmp)
            p = run(["build", str(root), "--engine", str(engine)])
            self.assertEqual(p.returncode, 4)
            self.assertIn("fail line 30", p.stdout)
            self.assertIn("fail line 11", p.stdout)
            self.assertNotIn("fail line 10", p.stdout)

    def test_compile_failure_writes_no_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "always_fail")
            root = make_project(tmp)
            run(["build", str(root), "--engine", str(engine)])
            self.assertFalse((root / "main.pdf").exists())


class TestHelpers(unittest.TestCase):
    def test_rewrite_replaces_fontset_and_inserts_cjk_line(self):
        font = Path("/tmp/fonts/STHEITI.ttf")
        out = rewrite_cjk_font(ZH_TEX, font)
        self.assertIn("fontset=none", out)
        self.assertNotIn("fontset=fandol", out)
        self.assertIn(
            "\\setCJKmainfont[Path=/tmp/fonts/,BoldFont=STHEITI.ttf]"
            "{STHEITI.ttf}", out)
        # 插入行紧跟 documentclass 行
        lines = out.splitlines()
        idx = next(i for i, ln in enumerate(lines)
                   if "\\documentclass" in ln)
        self.assertIn("\\setCJKmainfont", lines[idx + 1])

    def test_rewrite_requires_documentclass(self):
        with self.assertRaises(ValueError):
            rewrite_cjk_font("no class line\n", Path("/tmp/a.ttf"))

    def test_pdf_page_count_objects_and_count(self):
        data = b"%PDF-1.4\n/Type /Pages /Count 2\n/Type /Page\n/Type /Page\n"
        self.assertEqual(pdf_page_count(data), 2)
        self.assertEqual(pdf_page_count(b"%PDF-1.4\n/Count 7\n"), 7)
        self.assertEqual(pdf_page_count(b"not a pdf"), 0)

    def test_pdf_page_count_decompresses_object_streams(self):
        inner = b"/Type /Pages /Count 4 /Type /Page /Type /Page " \
                b"/Type /Page /Type /Page"
        payload = zlib.compress(inner)
        data = (b"%PDF-1.5\n1 0 obj <</Filter/FlateDecode>>\nstream\n"
                + payload + b"\nendstream\n")
        self.assertEqual(pdf_page_count(data), 4)


if __name__ == "__main__":
    unittest.main()
