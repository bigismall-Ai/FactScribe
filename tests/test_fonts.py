# -*- coding: utf-8 -*-
"""Fandol 字体缓存与构建注入的测试（批 123）。

全部离线：字体包用本地临时 zip 夹具，构建用假的 tectonic 脚本。
规范：docs/design/SPEC-FONTS.md。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FANDOL = (
    "FandolSong-Regular.otf",
    "FandolHei-Regular.otf",
    "FandolKai-Regular.otf",
    "FandolFang-Regular.otf",
)

ZH_TEX = (
    "\\documentclass[UTF8,11pt,fontset=fandol]{ctexart}\n"
    "\\begin{document}\n"
    "你好，10/16。\n"
    "\\end{document}\n"
)

FAKE_ENGINE = r"""#!/bin/sh
# 假 tectonic：main.tex 还带 fontset=fandol 就报字体错；否则写一个 2 页 PDF。
if grep -q "fontset=fandol" main.tex 2>/dev/null; then
  echo "error: CTeX fontset 'fandol' could not be found" >&2
  exit 1
fi
printf '%%PDF-1.4\n' > main.pdf
printf '1 0 obj << /Type /Pages /Count 2 >> endobj\n' >> main.pdf
printf '2 0 obj << /Type /Page /Parent 1 0 R >> endobj\n' >> main.pdf
printf '3 0 obj << /Type /Page /Parent 1 0 R >> endobj\n' >> main.pdf
printf 'trailer << /Root 1 0 R >>\n%%%%EOF\n' >> main.pdf
exit 0
"""


def make_zip(path: Path, fonts=FANDOL, extra=None, nested=True):
    """造一个与 CTAN 包同形的 zip：字体在深层目录，许可文本在包根。"""
    prefix = "fonts/opentype/public/fandol/" if nested else ""
    with zipfile.ZipFile(path, "w") as zf:
        for name in fonts:
            zf.writestr(prefix + name, b"OTF+" + name.encode("ascii"))
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return path


def make_project(tmp: Path):
    root = tmp / "proj"
    (root / "sections").mkdir(parents=True)
    (root / "facts").mkdir()
    (root / "sections" / "a.tex").write_text("占位正文\n", encoding="utf-8")
    (root / "refs.bib").write_text("", encoding="utf-8")
    (root / "paperkit.toml").write_text(
        '[project]\ntitle = "t"\nauthors = ["a"]\n'
        'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
        'bib = "refs.bib"\nbuild = ""\n', encoding="utf-8")
    (root / "main.tex").write_text(ZH_TEX, encoding="utf-8")
    return root


def write_engine(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "fake-tectonic"
    path.write_text(FAKE_ENGINE, encoding="utf-8")
    path.chmod(0o755)
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, cache=None):
    env = dict(os.environ)
    env.pop("HTTPS_PROXY", None)
    env.pop("https_proxy", None)
    if cache is not None:
        env["FACTSCRIBE_FONT_CACHE"] = str(cache)
    return subprocess.run([sys.executable, "-m", "factscribe"] + args,
                          capture_output=True, text=True, cwd=str(ROOT),
                          env=env)


def run_json(args, cache=None):
    proc = run(args + ["--json"], cache=cache)
    return proc.returncode, json.loads(proc.stdout)


class TestFontsStatus(unittest.TestCase):
    def test_status_missing_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            proc = run(["fonts", "--status"], cache=cache)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("缺失", proc.stdout)
            self.assertIn("fonts --fetch", proc.stdout)
            self.assertIn(str(cache), proc.stdout)

    def test_status_missing_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            code, data = run_json(["fonts", "--status"], cache=cache)
            self.assertEqual(code, 0)
            self.assertFalse(data["complete"])
            self.assertEqual(data["missing"], list(FANDOL))
            self.assertEqual(len(data["fonts"]), 4)
            self.assertTrue(all(not f["present"] for f in data["fonts"]))


class TestFontsFetch(unittest.TestCase):
    def test_fetch_from_file_uri_extracts_four(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            zpath = make_zip(Path(tmp) / "fandol.zip")
            code, data = run_json(
                ["fonts", "--fetch", "--url", zpath.as_uri()], cache=cache)
            self.assertEqual(code, 0, data)
            self.assertTrue(data["downloaded"])
            for name in FANDOL:
                self.assertTrue((cache / name).is_file(), name)
            self.assertEqual(data["missing"], [])

    def test_fetch_from_local_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            zpath = make_zip(Path(tmp) / "fandol.zip", nested=False)
            proc = run(["fonts", "--fetch", "--url", str(zpath)], cache=cache)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertTrue(all((cache / n).is_file() for n in FANDOL))

    def test_fetch_writes_source_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            zpath = make_zip(Path(tmp) / "fandol.zip")
            proc = run(["fonts", "--fetch", "--url", zpath.as_uri()],
                       cache=cache)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            source = (cache / "SOURCE.txt").read_text(encoding="utf-8")
            self.assertIn("URL:", source)
            self.assertIn(zpath.as_uri(), source)
            self.assertIn("Downloaded:", source)
            self.assertIn("Zip-Bytes:", source)
            self.assertIn("SHA256:", source)

    def test_fetch_keeps_license_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            zpath = make_zip(
                Path(tmp) / "fandol.zip",
                extra={"GUST-Font-License.txt": b"GUST Font License text",
                       "README": b"fandol readme"})
            proc = run(["fonts", "--fetch", "--url", zpath.as_uri()],
                       cache=cache)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertEqual((cache / "GUST-Font-License.txt").read_bytes(),
                             b"GUST Font License text")
            self.assertTrue((cache / "README").is_file())

    def test_fetch_missing_font_exits_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            zpath = make_zip(Path(tmp) / "fandol.zip",
                             fonts=FANDOL[:3])
            proc = run(["fonts", "--fetch", "--url", zpath.as_uri()],
                       cache=cache)
            self.assertEqual(proc.returncode, 4)
            self.assertIn(FANDOL[3], proc.stdout)
            self.assertIn("缺", proc.stdout)

    def test_fetch_idempotent_skips_second_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            zpath = make_zip(Path(tmp) / "fandol.zip")
            first = run(["fonts", "--fetch", "--url", zpath.as_uri()],
                        cache=cache)
            self.assertEqual(first.returncode, 0, first.stdout)
            before = (cache / "SOURCE.txt").stat().st_mtime_ns
            second = run(["fonts", "--fetch", "--url", zpath.as_uri()],
                         cache=cache)
            self.assertEqual(second.returncode, 0, second.stdout)
            self.assertIn("跳过下载", second.stdout)
            self.assertEqual((cache / "SOURCE.txt").stat().st_mtime_ns, before)

    def test_fetch_force_redownloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            zpath = make_zip(Path(tmp) / "fandol.zip")
            self.assertEqual(
                run(["fonts", "--fetch", "--url", zpath.as_uri()],
                    cache=cache).returncode, 0)
            old = 1_000_000_000
            os.utime(cache / "SOURCE.txt", (old, old))
            proc = run(["fonts", "--fetch", "--url", zpath.as_uri(),
                        "--force"], cache=cache)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("下载", proc.stdout)
            self.assertNotIn("跳过下载", proc.stdout)
            self.assertGreater(
                (cache / "SOURCE.txt").stat().st_mtime_ns, old * 10 ** 9)

    def test_fetch_network_error_exits_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            proc = run(["fonts", "--fetch", "--url",
                        "http://127.0.0.1:9/fandol.zip"], cache=cache)
            self.assertEqual(proc.returncode, 4)
            self.assertIn("下载失败", proc.stdout)

    def test_fetch_bad_zip_exits_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            bad = Path(tmp) / "bad.zip"
            bad.write_bytes(b"not a zip at all")
            proc = run(["fonts", "--fetch", "--url", str(bad)], cache=cache)
            self.assertEqual(proc.returncode, 4)
            self.assertIn("zip", proc.stdout.lower())

    def test_status_complete_after_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            zpath = make_zip(Path(tmp) / "fandol.zip")
            self.assertEqual(
                run(["fonts", "--fetch", "--url", zpath.as_uri()],
                    cache=cache).returncode, 0)
            code, data = run_json(["fonts", "--status"], cache=cache)
            self.assertEqual(code, 0)
            self.assertTrue(data["complete"])
            self.assertTrue(data["present"])
            self.assertEqual(data["missing"], [])
            self.assertTrue(all(f["present"] for f in data["fonts"]))
            self.assertGreater(data["cache_bytes"], 0)
            self.assertEqual(data["source"]["url"], zpath.as_uri())


class TestBuildFontPriority(unittest.TestCase):
    def _cache_with_fonts(self, tmp: Path) -> Path:
        cache = tmp / "cache"
        zpath = make_zip(tmp / "fandol.zip")
        proc = run(["fonts", "--fetch", "--url", zpath.as_uri()], cache=cache)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        return cache

    def test_build_injects_fandol_when_cache_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cache = self._cache_with_fonts(tmp)
            engine = write_engine(tmp / "bin")
            root = make_project(tmp)
            code, data = run_json(
                ["build", str(root), "--engine", str(engine), "--keep-temp"],
                cache=cache)
            self.assertEqual(code, 0, data)
            self.assertEqual(data["font_source"], "fandol")
            kept = Path(data["temp_dir"])
            try:
                patched = (kept / "project" / "main.tex").read_text(
                    encoding="utf-8")
                self.assertIn("fontset=none", patched)
                for name in FANDOL:
                    self.assertIn(name, patched)
                for macro in ("\\setCJKmainfont", "\\setCJKsansfont",
                              "\\setCJKmonofont", "\\setCJKfamilyfont{zhkai}"):
                    self.assertIn(macro, patched)
                self.assertNotIn("STHEITI", patched)
            finally:
                shutil.rmtree(kept, ignore_errors=True)

    def test_build_uses_system_font_when_cache_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cache = tmp / "empty-cache"
            engine = write_engine(tmp / "bin")
            font = tmp / "fonts" / "MyFont.ttf"
            font.parent.mkdir(parents=True)
            font.write_bytes(b"fake font bytes")
            root = make_project(tmp)
            code, data = run_json(
                ["build", str(root), "--engine", str(engine),
                 "--cjk-font", str(font), "--keep-temp"], cache=cache)
            self.assertEqual(code, 0, data)
            self.assertEqual(data["font_source"], "system")
            kept = Path(data["temp_dir"])
            try:
                patched = (kept / "project" / "main.tex").read_text(
                    encoding="utf-8")
                self.assertIn("MyFont.ttf", patched)
                self.assertNotIn("FandolSong-Regular.otf", patched)
            finally:
                shutil.rmtree(kept, ignore_errors=True)

    def test_build_output_says_system_font_not_fandol(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            engine = write_engine(tmp / "bin")
            font = tmp / "MyFont.ttf"
            font.write_bytes(b"fake font bytes")
            root = make_project(tmp)
            proc = run(["build", str(root), "--engine", str(engine),
                        "--cjk-font", str(font)], cache=tmp / "empty-cache")
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("用了系统字体，未用 Fandol", proc.stdout)
            self.assertIn("fonts --fetch", proc.stdout)

    def test_build_missing_explicit_cjk_font_exits_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            engine = write_engine(tmp / "bin")
            root = make_project(tmp)
            proc = run(["build", str(root), "--engine", str(engine),
                        "--cjk-font", str(tmp / "nope.ttf")],
                       cache=tmp / "empty-cache")
            self.assertEqual(proc.returncode, 4)
            self.assertIn("不存在", proc.stdout)

    def test_build_source_tex_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cache = self._cache_with_fonts(tmp)
            engine = write_engine(tmp / "bin")
            root = make_project(tmp)
            before = sha(root / "main.tex")
            code, _data = run_json(
                ["build", str(root), "--engine", str(engine)], cache=cache)
            self.assertEqual(code, 0)
            self.assertEqual(sha(root / "main.tex"), before)
            source = (root / "main.tex").read_text(encoding="utf-8")
            self.assertIn("fontset=fandol", source)
            self.assertNotIn("setCJKmainfont", source)


if __name__ == "__main__":
    unittest.main()
