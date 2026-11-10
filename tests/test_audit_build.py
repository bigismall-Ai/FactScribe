# -*- coding: utf-8 -*-
"""批 122：`audit` / `verify-pdf` 的 `--build` 开关。

全部离线：假 tectonic 脚本按 `FAKE_MODE` 模拟成功/硬失败/复制真实 PDF。
规范：docs/design/SPEC-BUILD.md §7。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BIB_OK = """@inproceedings{chen2023,
  title = {A Paper},
  doi = {10.18653/v1/2023.emnlp-main.741}
}
"""

RESULT_TEXT = "open 10/16 closed 8/16\n"

FACT = """[[fact]]
id = "A1"
claim = "开臂 resolved（16 题）"
value = "10/16"
source = "results/raw.md"
locator = "§二"
confidence = "high"
derived_from = []
"""

EN_TEX = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "Hello. \\cite{chen2023}\n"
    "\\end{document}\n"
)

FAKE_ENGINE = r"""#!/bin/sh
log="${FAKE_LOG:-}"
if [ -n "$log" ]; then
  printf '%s\n' "$*" >> "$log"
fi
mode="__MODE__"
case "$mode" in
  ok)
    ;;
  copy)
    cp "$FAKE_PDF" main.pdf
    exit 0
    ;;
  always_fail)
    echo "fake tectonic: hard failure" >&2
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


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_engine(directory: Path, mode: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "tectonic"
    path.write_text(FAKE_ENGINE.replace("__MODE__", mode), encoding="utf-8")
    path.chmod(0o755)
    return path


def make_project(tmp, build="", tex=EN_TEX) -> Path:
    """最小 v1 项目：一条 fact、干净正文、可审计的人签清单。"""
    root = Path(tmp) / "proj"
    (root / "facts").mkdir(parents=True)
    (root / "results").mkdir()
    raw = root / "results" / "raw.md"
    raw.write_text(RESULT_TEXT, encoding="utf-8")
    digest = sha(raw)
    (root / "facts" / "f.toml").write_text(
        FACT.replace('source = "results/raw.md"',
                     'source = "results/raw.md"\nsource_sha256 = "%s"' % digest),
        encoding="utf-8")
    (root / "main.tex").write_text(tex, encoding="utf-8")
    (root / "refs.bib").write_text(BIB_OK, encoding="utf-8")
    (root / "results" / "MANIFEST.toml").write_text(
        "[manifest]\nsigned_by = \"test-human\"\n"
        "signed_at = \"2026-11-07T00:00:00Z\"\nversion = 1\n\n[files]\n"
        '"results/raw.md" = "%s"\n' % digest, encoding="utf-8")
    (root / "paperkit.toml").write_text(
        '[project]\ntitle = "t"\nauthors = ["a"]\n'
        'sections = "*.tex"\nfacts = "facts/*.toml"\n'
        'bib = "refs.bib"\nbuild = "%s"\n' % build, encoding="utf-8")
    return root


def run(args, env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run([sys.executable, "-m", "factscribe"] + args,
                          capture_output=True, text=True, cwd=str(ROOT),
                          env=merged)


def run_json(args, env=None):
    proc = run(args, env=env)
    return proc.returncode, json.loads(proc.stdout), proc


class AuditBuildTest(unittest.TestCase):
    def test_audit_build_success_runs_build_then_audit(self):
        """--build 成功：先编（假引擎留日志、落 main.pdf），再审计，exit 0。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            log = Path(tmp) / "calls.log"
            root = make_project(tmp)
            code, data, _ = run_json(["audit", str(root), "--build", "--json"],
                                     env={"PATH": str(engine.parent) + os.pathsep
                                          + os.environ.get("PATH", ""),
                                          "FAKE_LOG": str(log)})
            self.assertEqual(code, 0, data)
            self.assertTrue(log.is_file() and log.read_text().strip())
            self.assertTrue((root / "main.pdf").is_file())
            self.assertEqual(data["build"]["ran"], True)
            self.assertEqual(data["build"]["ok"], True)
            self.assertGreater(data["build"]["pdf_bytes"], 0)
            self.assertEqual(data["issues"], [])
            self.assertIn("build", data)

    def test_audit_build_failure_aborts_with_build_exit_4(self):
        """编译失败：审计中止，退出码沿用 build 的 4，不输出审计结论。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "always_fail")
            root = make_project(tmp)
            proc = run(["audit", str(root), "--build"],
                       env={"PATH": str(engine.parent) + os.pathsep
                            + os.environ.get("PATH", "")})
            self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
            self.assertIn("审计中止", proc.stdout)
            self.assertNotIn("结论：", proc.stdout)
            self.assertNotIn("审计通过", proc.stdout)

    def test_audit_build_missing_engine_exits_8(self):
        """引擎缺失：exit 8（PDF_TOOL_MISSING），审计不跑。"""
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty-bin"
            empty.mkdir()
            root = make_project(tmp)
            code, data, _ = run_json(["audit", str(root), "--build", "--json"],
                                     env={"PATH": str(empty)})
            self.assertEqual(code, 8, data)
            self.assertEqual(data["build"]["ran"], True)
            self.assertEqual(data["build"]["ok"], False)
            self.assertEqual(data["build"]["pdf_bytes"], 0)
            self.assertIn("PDF_TOOL_MISSING", data["build_output"])

    def test_audit_without_build_never_invokes_engine(self):
        """不传 --build：行为完全不变，假 tectonic 一次都不调用。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            log = Path(tmp) / "calls.log"
            root = make_project(tmp)
            code, data, _ = run_json(["audit", str(root), "--json"],
                                     env={"PATH": str(engine.parent) + os.pathsep
                                          + os.environ.get("PATH", ""),
                                          "FAKE_LOG": str(log)})
            self.assertEqual(code, 0, data)
            self.assertFalse(log.exists() and log.read_text().strip())
            self.assertEqual(data["build"], {"ran": False, "ok": True,
                                             "pdf_bytes": 0})

    def test_audit_build_shell_project_build_still_runs_first(self):
        """project.build 非空：走原来那条 shell 路，不碰 tectonic。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            log = Path(tmp) / "calls.log"
            root = make_project(tmp, build="sh -c 'echo shell-built > built.txt'")
            code, data, _ = run_json(["audit", str(root), "--build", "--json"],
                                     env={"PATH": str(engine.parent) + os.pathsep
                                          + os.environ.get("PATH", ""),
                                          "FAKE_LOG": str(log)})
            self.assertEqual(code, 0, data)
            self.assertTrue((root / "built.txt").is_file())
            self.assertFalse(log.exists() and log.read_text().strip())
            self.assertEqual(data["build"]["ok"], True)

    def test_audit_build_shell_failure_aborts_with_exit_1(self):
        """project.build 非空且失败：退出码沿用 build 的 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, build="sh -c 'exit 9'")
            code, data, _ = run_json(["audit", str(root), "--build", "--json"])
            self.assertEqual(code, 1, data)
            self.assertEqual(data["build"]["ok"], False)
            self.assertIn("构建失败", data["build_output"])

    def test_audit_build_shell_font_error_falls_back_to_auto(self):
        """project.build 败在字体上：闸门用批 120 的临时副本兜底，不改项目 .tex。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            root = make_project(
                tmp, build="sh -c 'echo CTeX fontset fandol could not be found >&2; exit 1'")
            before = (root / "main.tex").read_bytes()
            code, data, _ = run_json(
                ["audit", str(root), "--build", "--json"],
                env={"PATH": str(engine.parent) + os.pathsep
                     + os.environ.get("PATH", "")})
            self.assertEqual(code, 0, data)
            self.assertEqual(data["build"]["ok"], True)
            self.assertEqual((root / "main.tex").read_bytes(), before)
            self.assertTrue((root / "main.pdf").is_file())

    def test_audit_build_json_block_has_exact_shape(self):
        """--json 的 build 字段形状固定：ran/ok/pdf_bytes 三个键。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            root = make_project(tmp)
            code, data, _ = run_json(["audit", str(root), "--build", "--json"],
                                     env={"PATH": str(engine.parent) + os.pathsep
                                          + os.environ.get("PATH", "")})
            self.assertEqual(code, 0, data)
            self.assertEqual(set(data["build"]), {"ran", "ok", "pdf_bytes"})


class VerifyPdfBuildTest(unittest.TestCase):
    def _pdf_project(self, tmp):
        """复制一个真实可验的 benign 夹具（verify-pdf 期望 exit 0）。"""
        src = ROOT / "fixtures" / "benign" / "R3-PDF-ONEWAY"
        dest = Path(tmp) / "proj"
        shutil.copytree(src, dest)
        # 夹具是 verify-pdf 用的，没有可编的根文件；--build 需要 main.tex。
        (dest / "main.tex").write_text(EN_TEX, encoding="utf-8")
        return dest

    def test_verify_pdf_build_success_then_checks(self):
        """verify-pdf --build：先编（真实 PDF 覆盖），再回检，exit 0。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "copy")
            log = Path(tmp) / "calls.log"
            project = self._pdf_project(tmp)
            source_pdf = project / "main.pdf"
            env = {"PATH": str(engine.parent) + os.pathsep
                   + os.environ.get("PATH", ""),
                   "FAKE_LOG": str(log),
                   "FAKE_PDF": str(source_pdf)}
            # 先把旧 PDF 移走，证明 --build 重新产出了它。
            saved = Path(tmp) / "saved.pdf"
            shutil.copyfile(source_pdf, saved)
            source_pdf.unlink()
            env["FAKE_PDF"] = str(saved)
            code, data, _ = run_json(
                ["verify-pdf", str(project / "main.pdf"),
                 "--report", str(project / "audit" / "report.json"),
                 "--build"], env=env)
            self.assertEqual(code, 0, data)
            self.assertTrue(log.is_file() and log.read_text().strip())
            self.assertTrue((project / "main.pdf").is_file())
            self.assertEqual(data["build"]["ran"], True)
            self.assertEqual(data["build"]["ok"], True)
            self.assertGreater(data["build"]["pdf_bytes"], 0)
            self.assertEqual(data["issues"], [])

    def test_verify_pdf_build_failure_aborts_with_exit_4(self):
        """verify-pdf --build 编译失败：exit 4，不进入 PDF 回检。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "always_fail")
            project = self._pdf_project(tmp)
            code, data, _ = run_json(
                ["verify-pdf", str(project / "main.pdf"),
                 "--report", str(project / "audit" / "report.json"),
                 "--build"],
                env={"PATH": str(engine.parent) + os.pathsep
                     + os.environ.get("PATH", "")})
            self.assertEqual(code, 4, data)
            self.assertEqual(data["build"]["ran"], True)
            self.assertEqual(data["build"]["ok"], False)
            self.assertNotIn("structural_masked", data)

    def test_verify_pdf_without_build_never_invokes_engine(self):
        """verify-pdf 不传 --build：只回检，假 tectonic 不被调用。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = write_engine(Path(tmp) / "bin", "ok")
            log = Path(tmp) / "calls.log"
            project = self._pdf_project(tmp)
            code, data, _ = run_json(
                ["verify-pdf", str(project / "main.pdf"),
                 "--report", str(project / "audit" / "report.json")],
                env={"PATH": str(engine.parent) + os.pathsep
                     + os.environ.get("PATH", ""),
                     "FAKE_LOG": str(log)})
            self.assertEqual(code, 0, data)
            self.assertFalse(log.exists() and log.read_text().strip())
            self.assertEqual(data["build"], {"ran": False, "ok": True,
                                             "pdf_bytes": 0})

    def test_verify_pdf_build_missing_engine_exits_8(self):
        """verify-pdf --build 引擎缺失：exit 8，PDF 回检不跑。"""
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty-bin"
            empty.mkdir()
            project = self._pdf_project(tmp)
            code, data, _ = run_json(
                ["verify-pdf", str(project / "main.pdf"),
                 "--report", str(project / "audit" / "report.json"),
                 "--build"], env={"PATH": str(empty)})
            self.assertEqual(code, 8, data)
            self.assertEqual(data["build"]["ok"], False)
            self.assertIn("PDF_TOOL_MISSING", data["build_output"])


if __name__ == "__main__":
    unittest.main()
