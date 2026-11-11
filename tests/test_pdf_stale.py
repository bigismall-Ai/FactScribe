# -*- coding: utf-8 -*-
"""批 127：`PDF_STALE`——旧 PDF 不得当答案提示。

实测暴露的漏洞：模型把旧 `main.pdf` 读出来，比对数字多重集反推出
「这一节该有哪些数字」，再照着写；它没编数字，`audit` 判绿，但来源
不是证据而是旧 PDF。本判据要求 PDF 不早于闭包内任一 `.tex` / `.bib` /
`facts/*.toml`；过期即红（exit 5），且过期 PDF 的数字**不参与**比对。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from factscribe import pdfgate  # noqa: E402
from test_pdfgate_masking import write_pdf  # noqa: E402
from _pdfdep import requires_pdftotext  # noqa: E402

V3_TOML = """schema = "factscribe/3.0"
root_tex = "main.tex"
facts = "facts"
refs = "refs.bib"

[project]
title = "pdf stale"
signing_mode = "offline_manifest"
number_locale = "dot"
frac_allow = []
inline_images_allow = []
numeric_macro_allow = []
"""

FACT = """id = "A1"
role = "results"
quantitative = true
value = "10"
source = "runs/r1/summary.json"
run_id = "r1"
pointer = "/summary/on_resolved"
"""

FILLER = "Structural masking test page content only for this fixture."
GOOD_PAGES = [["1 Design", "We solved 10 tasks."], ["2", FILLER]]
# 旧 PDF 才有的数字：源层账上没有，过期 PDF 不得拿它参与比对。
STALE_PAGES = [["1 Design", "We solved 10 tasks and 999 samples."], ["2", FILLER]]

FAKE_ENGINE = r"""#!/bin/sh
cp "$FAKE_PDF" main.pdf
exit 0
"""


def _touch(path: Path, when: float) -> None:
    ns = int(when * 1_000_000_000)
    os.utime(path, ns=(ns, ns))


def _write_good_pdf(path: Path) -> None:
    write_pdf(path, GOOD_PAGES)


def _make_project(root: Path) -> Path:
    """最小 V3 项目：一条 fact、正文绑定 10、bib 为空、PDF 已存在。"""
    (root / "sections").mkdir(parents=True)
    (root / "facts").mkdir()
    (root / "runs" / "r1").mkdir(parents=True)
    (root / "factscribe.toml").write_text(V3_TOML, encoding="utf-8")
    (root / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\n"
        "\\input{sections/body}\n\\end{document}\n", encoding="utf-8")
    (root / "sections" / "body.tex").write_text(
        "\\section{Design}\nWe solved \\fact{A1}{10} tasks.\n",
        encoding="utf-8")
    summary = root / "runs" / "r1" / "summary.json"
    summary.write_text('{"run_id": "r1", "summary": {"on_resolved": 10}}\n',
                       encoding="utf-8")
    digest = hashlib.sha256(summary.read_bytes()).hexdigest()
    (root / "runs" / "r1" / "record.json").write_text(
        json.dumps({"run_id": "r1", "source": "runs/r1/summary.json",
                    "source_sha256": "sha256:" + digest,
                    "facts": ["A1"]}), encoding="utf-8")
    (root / "facts" / "A1.toml").write_text(
        FACT + '\nsource_sha256 = "sha256:%s"\n' % digest, encoding="utf-8")
    (root / "refs.bib").write_text("", encoding="utf-8")
    _write_good_pdf(root / "main.pdf")
    return root


def _age_pdf(root: Path, seconds: float = 100.0) -> None:
    _touch(root / "main.pdf", time.time() - seconds)


def run_cli(args, env=None):
    import subprocess
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run([sys.executable, "-m", "factscribe"] + args,
                          capture_output=True, text=True, cwd=str(ROOT),
                          env=merged)
    data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return proc.returncode, data, proc


class StalePdfIssueTest(unittest.TestCase):
    """pdfgate 单元面：比较口径与「过期即跳过 PDF 层」。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.pdf = self.root / "main.pdf"
        _write_good_pdf(self.pdf)
        self.tex = self.root / "main.tex"
        self.tex.write_text("x\n", encoding="utf-8")

    def test_tex_newer_than_pdf_reports_pdf_stale(self):
        """tex 比 pdf 新 → PDF_STALE，退出码 5，消息要求先重编。"""
        _age_pdf(self.root)
        issue = pdfgate.stale_pdf_issue(self.pdf, [self.tex])
        self.assertIsNotNone(issue)
        self.assertEqual(issue.code, "PDF_STALE")
        self.assertEqual(issue.exit_code, 5)
        self.assertIn("PDF 比源文件旧", issue.message)
        self.assertIn("重编", issue.message)

    def test_pdf_newer_than_tex_is_clean(self):
        """pdf 比 tex 新 → 不报（build 之后就是这个状态）。"""
        _touch(self.pdf, time.time() + 5)
        self.assertIsNone(pdfgate.stale_pdf_issue(self.pdf, [self.tex]))

    def test_no_pdf_is_not_stale(self):
        """项目没有 PDF → 本判据不报（缺 PDF 是另一条，不在这里报）。"""
        missing = self.root / "nope.pdf"
        self.assertIsNone(pdfgate.stale_pdf_issue(missing, [self.tex]))

    def test_facts_toml_newer_than_pdf_triggers(self):
        """改 facts/*.toml 也算源文件变新。"""
        facts = self.root / "facts"
        facts.mkdir()
        fact = facts / "A1.toml"
        fact.write_text("id = \"A1\"\n", encoding="utf-8")
        _age_pdf(self.root)
        issue = pdfgate.stale_pdf_issue(self.pdf, [fact])
        self.assertIsNotNone(issue)
        self.assertEqual(issue.code, "PDF_STALE")

    def test_bib_newer_than_pdf_triggers(self):
        """改 .bib 也算源文件变新。"""
        bib = self.root / "refs.bib"
        bib.write_text("@misc{k}\n", encoding="utf-8")
        _age_pdf(self.root)
        self.assertIsNotNone(pdfgate.stale_pdf_issue(self.pdf, [bib]))

    def test_stale_pdf_numbers_are_not_compared(self):
        """过期时直接跳过 PDF 层：旧 PDF 的 999 不得变成 PDF_UNACCOUNTED_NUMBER。"""
        write_pdf(self.pdf, STALE_PAGES)
        _age_pdf(self.root)
        stats: dict = {}
        issues, _warnings = pdfgate.verify_document(
            self.pdf, {"number_ledger": [], "pdf_whitelist": [],
                       "structural_whitelist": {}},
            stats=stats, sources=[self.tex])
        self.assertEqual([i.code for i in issues], ["PDF_STALE"])
        self.assertNotIn("PDF_UNACCOUNTED_NUMBER", {i.code for i in issues})
        self.assertTrue(stats.get("stale"))
        self.assertEqual(stats.get("structural_masked"), 0)

    def test_stale_pdf_skips_page_text_checks_too(self):
        """跳过的是整个 PDF 层（页面判据也不跑），不是只跳过数字比对。"""
        blank = self.root / "blank.pdf"
        write_pdf(blank, [["", ""]])
        _touch(blank, time.time() - 100)
        issues, _warnings = pdfgate.verify_document(
            blank, {"number_ledger": []}, sources=[self.tex])
        self.assertEqual([i.code for i in issues], ["PDF_STALE"])


class AuditPdfStaleTest(unittest.TestCase):
    """audit 面：闭包含 facts/bib，--build 先编再判所以天然不命中。"""

    def _setup(self, tmp):
        root = _make_project(Path(tmp) / "proj")
        return root

    def test_audit_reports_pdf_stale_with_exit_5(self):
        """tex 比 pdf 新：audit 报 PDF_STALE，exit 5。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp)
            _age_pdf(root)
            code, data, proc = run_cli(["audit", str(root), "--json"])
            self.assertEqual(code, 5, proc.stdout + proc.stderr)
            self.assertIn("PDF_STALE",
                          {i["code"] for i in data["issues"]})

    def test_audit_facts_change_alone_triggers_stale(self):
        """只动 facts/*.toml（tex/bib 不动）也触发：闭包含 facts。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp)
            _age_pdf(root)
            _touch(root / "facts" / "A1.toml", time.time())
            code, data, proc = run_cli(["audit", str(root), "--json"])
            self.assertEqual(code, 5, proc.stdout + proc.stderr)
            self.assertIn("PDF_STALE", {i["code"] for i in data["issues"]})

    @requires_pdftotext
    def test_audit_build_regenerates_pdf_and_is_clean(self):
        """--build 先编（假引擎产出新 PDF）→ 不再过期，exit 0。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp)
            _age_pdf(root)
            engine_dir = Path(tmp) / "bin"
            engine_dir.mkdir()
            engine = engine_dir / "tectonic"
            engine.write_text(FAKE_ENGINE, encoding="utf-8")
            engine.chmod(0o755)
            fresh = Path(tmp) / "fresh.pdf"
            _write_good_pdf(fresh)
            env = {"PATH": str(engine_dir) + os.pathsep
                   + os.environ.get("PATH", ""), "FAKE_PDF": str(fresh)}
            code, data, proc = run_cli(["audit", str(root), "--build", "--json"],
                                       env=env)
            self.assertEqual(code, 0, proc.stdout + proc.stderr)
            self.assertNotIn("PDF_STALE",
                             {i["code"] for i in data["issues"]})
            self.assertTrue(data["build"]["ran"])
            self.assertTrue(data["build"]["ok"])

    def test_audit_without_pdf_does_not_report_stale(self):
        """项目没有 PDF：本判据不报（也不该凭空要求重编）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp)
            (root / "main.pdf").unlink()
            code, data, proc = run_cli(["audit", str(root), "--json"])
            self.assertNotIn("PDF_STALE",
                             {i["code"] for i in data.get("issues", [])},
                             proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
