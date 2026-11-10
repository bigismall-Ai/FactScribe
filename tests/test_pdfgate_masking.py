# -*- coding: utf-8 -*-
"""批 121：PDF 结构性 token 白名单（章节号/浮动体/年份/页码）的正负测试。

白名单必须从**源文件**推导：`\\section` 序列、figure/table/公式环境计数、
`refs.bib` 的 year 字段；页码由 PDF 实际页数补。正文数据数字不在白名单内时
仍须报 `PDF_UNACCOUNTED_NUMBER`（回归锁）。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe import pdfgate  # noqa: E402
from factscribe.texscan import structural_whitelist  # noqa: E402

FILLER = "Structural masking test page content only for this fixture."


# --------------------------------------------------------------------------
# 最小 PDF 生成器（纯标准库；pdftotext 能读）
# --------------------------------------------------------------------------

def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: Path, pages: list[list[str]]) -> None:
    objects: list[str] = []
    count = len(pages)
    font_id = 3 + 2 * count
    kids = " ".join("%d 0 R" % (3 + 2 * i) for i in range(count))
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    objects.append("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, count))
    for i, lines in enumerate(pages):
        content = ("BT /F1 12 Tf 14 TL 72 720 Td\n"
                   + "\n".join("(%s) Tj T*" % _escape(line) for line in lines)
                   + "\nET")
        content_id = 4 + 2 * i
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (font_id, content_id))
        objects.append("<< /Length %d >>\nstream\n%s\nendstream"
                       % (len(content.encode("utf-8")), content))
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    blob = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(blob))
        blob += ("%d 0 obj\n%s\nendobj\n" % (index, obj)).encode("utf-8")
    xref = len(blob)
    blob += ("xref\n0 %d\n0000000000 65535 f \n"
             % (len(objects) + 1)).encode("utf-8")
    for offset in offsets:
        blob += ("%010d 00000 n \n" % offset).encode("utf-8")
    blob += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
             % (len(objects) + 1, xref)).encode("utf-8")
    path.write_bytes(bytes(blob))


def verify(path: Path, ledger=(), structural=None, whitelist=()):
    stats: dict = {}
    issues, warnings = pdfgate.verify_document(
        path,
        {"number_ledger": list(ledger),
         "pdf_whitelist": list(whitelist),
         "structural_whitelist": structural or {}},
        stats=stats)
    return issues, warnings, stats


def tokens(issues) -> set[str]:
    return {str(i.token) for i in issues if i.code == "PDF_UNACCOUNTED_NUMBER"}


class StructuralSourceTest(unittest.TestCase):
    """白名单本身必须从源文件算对。"""

    def test_section_hierarchy_numbers(self):
        sections = [
            ("main.tex", "\\input{sections/a}\n\\input{sections/b}\n"),
            ("sections/a.tex", "\\section{One}\n\\subsection{One A}\n"),
            ("sections/b.tex", "\\section{Two}\n\\subsection{Two A}\n"
                               "\\subsubsection{Deep}\n"),
        ]
        self.assertEqual(structural_whitelist(sections, [], "main.tex")["sections"],
                         ["1", "1.1", "2", "2.1", "2.1.1"])

    def test_section_order_follows_input_not_filename(self):
        sections = [
            ("main.tex", "\\input{sections/z}\n\\input{sections/a}\n"),
            ("sections/a.tex", "\\section{Second in document}\n"),
            ("sections/z.tex", "\\section{First in document}\n"
                               "\\subsection{Child}\n"),
        ]
        # 按文件名排序会得到 1(Second), 2(First), 2.1；按 \input 才是 1, 1.1, 2。
        self.assertEqual(structural_whitelist(sections, [], "main.tex")["sections"],
                         ["1", "1.1", "2"])

    def test_starred_section_not_numbered(self):
        sections = [("main.tex", "\\section*{Preface}\n\\section{One}\n"
                                 "\\section*{Note}\n\\section{Two}\n")]
        self.assertEqual(structural_whitelist(sections, [], "main.tex")["sections"],
                         ["1", "2"])

    def test_appendix_headings_not_numeric(self):
        sections = [
            ("main.tex", "\\section{Body}\n\\appendix\n\\input{appendix/a}\n"),
            ("appendix/a.tex", "\\section{Extra}\n\\subsection{Sub}\n"),
        ]
        self.assertEqual(structural_whitelist(sections, [], "main.tex")["sections"],
                         ["1"])

    def test_section_31_whitelisted_99_not(self):
        sections = [("main.tex", "\\section{A}\n\\section{B}\n\\section{C}\n"
                                 "\\subsection{Target}\n")]
        whitelist = structural_whitelist(sections, [], "main.tex")["sections"]
        self.assertIn("3.1", whitelist)
        self.assertNotIn("9.9", whitelist)

    def test_float_numbers_one_to_n(self):
        body = ("\\begin{figure}\n\\end{figure}\n"
                "\\begin{figure*}\n\\end{figure*}\n"
                "\\begin{figure}\n\\end{figure}\n"
                "\\begin{table}\n\\end{table}\n"
                "\\begin{table}\n\\end{table}\n"
                "\\begin{equation}\n\\end{equation}\n")
        self.assertEqual(
            structural_whitelist([("main.tex", body)], [], "main.tex")["floats"],
            ["1", "2", "3"])

    def test_float_n_plus_one_not_listed(self):
        body = ("\\begin{figure}\n\\end{figure}\n"
                "\\begin{table}\n\\end{table}\n"
                "\\begin{table}\n\\end{table}\n")
        floats = structural_whitelist([("main.tex", body)], [], "main.tex")["floats"]
        self.assertEqual(floats, ["1", "2"])
        self.assertNotIn("3", floats)

    def test_starred_math_env_not_counted(self):
        body = ("\\begin{equation}\n\\end{equation}\n"
                "\\begin{equation*}\n\\end{equation*}\n"
                "\\begin{align*}\n\\end{align*}\n"
                "\\begin{align}\n\\end{align}\n")
        self.assertEqual(
            structural_whitelist([("main.tex", body)], [], "main.tex")["floats"],
            ["1", "2"])

    def test_bib_years_extracted(self):
        entries = [SimpleNamespace(fields={"year": "{2024}"}),
                   SimpleNamespace(fields={"year": "2018"}),
                   SimpleNamespace(fields={"year": "n.d."})]
        self.assertEqual(
            structural_whitelist([("main.tex", "")], entries, "main.tex")["years"],
            ["2018", "2024"])

    def test_year_not_in_bib_not_listed(self):
        entries = [SimpleNamespace(fields={"year": "2023"})]
        years = structural_whitelist([("main.tex", "")], entries, "main.tex")["years"]
        self.assertNotIn("2024", years)


class PdfMaskingTest(unittest.TestCase):
    """PDF 侧的放行与仍报红。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _pdf(self, pages):
        path = self.dir / ("p%d.pdf" % len(list(self.dir.iterdir())))
        write_pdf(path, pages)
        return path

    def test_pdf_section_token_masked(self):
        pdf = self._pdf([["3.1 Contract design text here", FILLER]])
        issues, _warnings, stats = verify(
            pdf, structural={"sections": ["3.1"]})
        self.assertEqual(issues, [])
        self.assertEqual(stats["structural_masked"], 1)

    def test_pdf_section_not_in_sequence_still_red(self):
        pdf = self._pdf([["9.9 Not a heading in this paper", FILLER]])
        issues, _warnings, _stats = verify(
            pdf, structural={"sections": ["3.1"]})
        self.assertEqual(tokens(issues), {"9.9"})

    def test_pdf_float_number_masked(self):
        pdf = self._pdf([["2 Imported figure caption text", FILLER]])
        issues, _warnings, _stats = verify(
            pdf, structural={"floats": ["1", "2"]})
        self.assertEqual(issues, [])

    def test_pdf_float_n_plus_one_still_red(self):
        pdf = self._pdf([["3 Imported figure caption text", FILLER]])
        issues, _warnings, _stats = verify(
            pdf, structural={"floats": ["1", "2"]})
        self.assertEqual(tokens(issues), {"3"})

    def test_pdf_bib_year_masked(self):
        pdf = self._pdf([["2024 A study of mechanical gates", FILLER]])
        issues, _warnings, _stats = verify(
            pdf, structural={"years": ["2024"]})
        self.assertEqual(issues, [])

    def test_pdf_year_absent_from_bib_still_red(self):
        pdf = self._pdf([["2024 A study of mechanical gates", FILLER]])
        issues, _warnings, _stats = verify(
            pdf, structural={"years": ["2023"]})
        self.assertEqual(tokens(issues), {"2024"})

    def test_pdf_page_numbers_masked(self):
        pdf = self._pdf([["1", FILLER], ["2", FILLER], ["3", FILLER]])
        issues, _warnings, stats = verify(pdf, structural={})
        self.assertEqual(issues, [])
        self.assertEqual(stats["structural_masked"], 3)

    def test_body_data_not_whitelisted_still_red(self):
        pdf = self._pdf([["42 samples were tested in the run", FILLER]])
        issues, _warnings, _stats = verify(
            pdf, structural={"sections": ["1", "3.1"],
                             "floats": ["1", "2"],
                             "years": ["2024"]})
        self.assertEqual(tokens(issues), {"42"})

    def test_masked_count_only_surplus_over_ledger(self):
        pdf = self._pdf([["3.1 heading text and 3.1 repeated", FILLER]])
        issues, _warnings, stats = verify(
            pdf,
            ledger=[{"fact_id": "A1", "keys": ["3.1"]}],
            structural={"sections": ["3.1"]})
        self.assertEqual(issues, [])
        self.assertEqual(stats["structural_masked"], 1)

    def test_masked_breakdown_by_category(self):
        pdf = self._pdf([["3.1 Design", "2024 A study", FILLER]])
        issues, _warnings, stats = verify(
            pdf, structural={"sections": ["3.1"], "years": ["2024"]})
        self.assertEqual(issues, [])
        self.assertEqual(stats["structural_masked_by"],
                         {"sections": 1, "years": 1})


V3_TOML = """schema = "factscribe/3.0"
root_tex = "main.tex"
facts = "facts"
refs = "refs.bib"

[project]
title = "synthetic masking"
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


class AuditJsonTest(unittest.TestCase):
    def test_audit_json_exposes_structural_masked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
                FACT + '\nsource_sha256 = "sha256:%s"\n' % digest,
                encoding="utf-8")
            (root / "refs.bib").write_text("", encoding="utf-8")
            write_pdf(root / "main.pdf", [["1 Design", "We solved 10 tasks."]])

            proc = subprocess.run(
                [sys.executable, "-m", "factscribe", "audit", str(root), "--json"],
                cwd=str(ROOT), capture_output=True, text=True)
            data = json.loads(proc.stdout)
            pdf = data["summary"]["pdf"]
            self.assertTrue(pdf["checked"])
            self.assertEqual(pdf["red"], 0)
            self.assertGreaterEqual(pdf["structural_masked"], 1)


if __name__ == "__main__":
    unittest.main()
