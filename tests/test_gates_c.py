# -*- coding: utf-8 -*-
"""批 47 / C 阶段：12 道闸门的正负测试（与 hostile/benign 夹具互补）。

夹具测试证明「攻击必红、近邻必绿」；本文件锁住实现边界的单点行为：
- 值域不再有隐式舍入（R-04 / B2）
- BU 是句子不是行（R-02 / B3）
- 表格闭包（R-05/R-06 / B1）、pkignore（R-07 / B4）
- 宏体数字与算术命令（R-01A）
- display 严格等价（R-04 / 2-B2）
- PDF 双向多重集与 stamp 信任根（V3.0 P-02..P-08）
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import factscribe as fs  # noqa: E402
from factscribe import pdfgate  # noqa: E402
from _pdfdep import requires_pdftotext  # noqa: E402

FACT = """[[fact]]
id = "A2"
claim = "ours resolved"
value = "%s"
source = "results/run.log"
source_sha256 = "%s"
locator = ""
confidence = "high"
%s
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_project(tmp: str, value: str = "10/16", extra: str = "",
                 body: str = "", files: dict[str, str] | None = None,
                 config: str = "") -> Path:
    root = Path(tmp)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    run_log = root / "results" / "run.log"
    run_log.write_text("resolved 10/16; score 0.91; headline 91.4% 9 1.4 99 100\n",
                       encoding="utf-8")
    digest = _sha(run_log)
    (root / "facts" / "f.toml").write_text(
        FACT % (value, digest, extra.replace("{digest}", digest)), encoding="utf-8")
    (root / "sections" / "body.tex").write_text(body, encoding="utf-8")
    for name, text in (files or {}).items():
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    (root / "paperkit.toml").write_text(
        '[project]\ntitle = "t"\nsections = "sections/*.tex"\n'
        'facts = "facts/*.toml"\nbib = "refs.bib"\n%s\n' % config,
        encoding="utf-8")
    (root / "refs.bib").write_text("", encoding="utf-8")
    (root / "results" / "MANIFEST.toml").write_text(
        '[manifest]\nsigned_by = "tester"\nsigned_at = "2026-11-08"\n'
        '[files]\n"results/run.log" = "%s"\n' % digest, encoding="utf-8")
    return root


def audit(root: Path):
    import subprocess
    proc = subprocess.run([sys.executable, "-m", "factscribe", "audit",
                           str(root), "--json"],
                          cwd=str(ROOT), capture_output=True, text=True)
    return proc.returncode, json.loads(proc.stdout)


class ValueRangeTest(unittest.TestCase):
    def test_quotient_has_no_implicit_rounding(self):
        keys = fs.fact_value_keys("10/16")
        self.assertIn("0.625", keys)
        for widened in ("1", "0.6", "0.62", "0.63"):
            self.assertNotIn(widened, keys)

    def test_one_sixteenth_does_not_bind_to_ten_sixteenths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, body="We resolved 1/16 of the tasks\\fact{A2}.\n")
            code, data = audit(root)
            self.assertEqual(code, 1)
            self.assertIn("BOUND_MISMATCH", [i["code"] for i in data["issues"]])


class SentenceUnitTest(unittest.TestCase):
    def test_marker_does_not_cover_an_earlier_sentence_on_the_same_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                body="The baseline resolved 5/16. Ours resolved 10/16\\fact{A2}.\n",
                extra='\n[[fact]]\nid = "A3"\nclaim = "baseline"\nvalue = "5/16"\n'
                      'source = "results/run.log"\nsource_sha256 = "{digest}"\n'
                      'locator = ""\nconfidence = "high"\n')
            code, data = audit(root)
            self.assertEqual(code, 3)
            self.assertEqual(data["summary"]["numbers_bound"], 2)  # 10 + 16 两个片段
            unbound = [w for w in data["warnings"] if w["code"] == "UNBOUND_NUMBER"]
            self.assertTrue(any(w["token"] == "5" for w in unbound), data["warnings"])

    def test_attribution_by_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                body="Plain resolved 5/16 while ours resolved 10/16\\fact{A2}\\fact{A3}.\n",
                extra='\n[[fact]]\nid = "A3"\nclaim = "plain"\nvalue = "5/16"\n'
                      'source = "results/run.log"\nlocator = ""\nconfidence = "high"\n')
            code, data = audit(root)
            self.assertEqual(code, 1)
            self.assertIn("BINDING_ATTRIBUTION", [i["code"] for i in data["issues"]])


class TableClosureTest(unittest.TestCase):
    TABLE = "\\begin{tabular}{ll}\nArm & Resolved \\\\\nours & 9/16 \\\\\n\\end{tabular}\n"

    def test_wrapper_macro_expands_into_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                body="",
                files={
                    "sections/main.tex":
                        "\\newcommand{\\tableinput}[1]{\\input{#1}}\n"
                        "\\tableinput{tables/t1.tex}\n",
                    "tables/t1.tex": self.TABLE,
                })
            code, data = audit(root)
            self.assertEqual(code, 5)
            self.assertIn("TABLE_UNBOUND", [i["code"] for i in data["issues"]])

    def test_bound_table_cell_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                body="\\begin{tabular}{ll}\nours & 10/16\\fact{A2} \\\\\n\\end{tabular}\n")
            code, data = audit(root)
            self.assertEqual(code, 0, data)


class PkignoreTest(unittest.TestCase):
    def test_quant_inside_pkignore_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                body="We resolved 10/16\\fact{A2}. "
                     "\\pkignore{we fabricated 99 of 100 tasks.}\n")
            code, data = audit(root)
            self.assertEqual(code, 1)
            self.assertIn("PKIGNORE_QUANT", [i["code"] for i in data["issues"]])
            self.assertEqual(data["summary"]["annotations_skipped"], 1)

    def test_identifier_and_table_block_are_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                body="\\pkignore{sphinx-10449} is excluded. We resolved 10/16\\fact{A2}.\n")
            code, data = audit(root)
            self.assertEqual(code, 0, data)


class MacroAndArithTest(unittest.TestCase):
    def test_macro_body_digit_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, value="91.4%",
                body="\\newcommand{\\acc}{9}\nOur headline is \\acc\\fact{A2}.\n")
            code, data = audit(root)
            self.assertEqual(code, 1)
            self.assertIn("NUMERIC_IN_MACRO", [i["code"] for i in data["issues"]])

    def test_registered_layout_macro_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, value="91.4%",
                body="\\newcommand{\\figwidth}{0.9\\linewidth}\nHeadline 91.4\\%\\fact{A2}.\n",
                config='numeric_macro_allow = ["figwidth"]')
            code, data = audit(root)
            self.assertEqual(code, 0, data)

    def test_numexpr_family_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, value="10",
                body="We evaluated \\the\\numexpr 9+1\\relax tasks\\fact{A2}.\n")
            code, data = audit(root)
            self.assertEqual(code, 1)
            self.assertIn("ARITH_IN_BODY", [i["code"] for i in data["issues"]])

    def test_token_concatenation_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, value="91.4%",
                body="Our headline result is 9{}1.4\\%\\fact{A2}.\n")
            code, data = audit(root)
            self.assertEqual(code, 1)
            codes = {i["code"] for i in data["issues"]}
            self.assertTrue({"NUM_AFTER_GROUP", "NUM_ADJACENT_GROUP"} & codes, codes)


class DisplayTest(unittest.TestCase):
    def test_round_to_cannot_widen_display(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, value="0.91",
                extra='display = [{ text = "0.9", round_to = 1 }]',
                body="The score reached 0.91\\fact{A2}.\n")
            code, data = audit(root)
            self.assertEqual(code, 1)
            self.assertIn("DISPLAY_INCONSISTENT", [i["code"] for i in data["issues"]])

    def test_exact_display_forms_are_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, value="10/16",
                extra='display = ["10/16", "62.5%"]',
                body="We resolved 10/16\\fact{A2}.\n")
            code, data = audit(root)
            self.assertEqual(code, 0, data)


class PdfGateTest(unittest.TestCase):
    def _verify(self, case: str):
        base = ROOT / "fixtures" / case
        keys = base / "keys" / "approver_keys.json"
        if not keys.is_file():
            keys = ROOT / "fixtures" / "trust" / "approver_keys.json"
        stamp = base / "audit" / "stamp.json"
        return pdfgate.verify_pdf(
            base / "main.pdf", base / "audit" / "report.json",
            stamp if stamp.is_file() else None, keys)

    @requires_pdftotext
    def test_raster_page_is_red(self):
        issues, _warnings, code = self._verify("hostile/R3-PDF-RASTER")
        self.assertEqual(code, 5)
        codes = {i.code for i in issues}
        self.assertIn("PDF_PAGE_NO_TEXT", codes)
        self.assertIn("PDF_PAGE_RASTERIZED", codes)

    @requires_pdftotext
    def test_one_way_inclusion_is_red(self):
        issues, _warnings, code = self._verify("hostile/R3-PDF-ONEWAY")
        self.assertEqual(code, 5)
        self.assertIn("PDF_LEDGER_TOKEN_MISSING", {i.code for i in issues})

    @requires_pdftotext
    def test_self_signed_stamp_is_untrusted(self):
        issues, _warnings, code = self._verify("hostile/R3-STAMP-SELFSIGN")
        self.assertEqual(code, 5)
        self.assertIn("STAMP_KEY_UNTRUSTED", {i.code for i in issues})

    @requires_pdftotext
    def test_external_key_stamp_passes(self):
        issues, _warnings, code = self._verify("benign/R3-STAMP-SELFSIGN")
        self.assertEqual(code, 0, [i.as_dict() for i in issues])

    def test_missing_poppler_fails_closed(self):
        base = ROOT / "fixtures" / "benign" / "R3-PDF-RASTER"
        with mock.patch.object(pdfgate, "missing_tools", return_value=["pdftotext"]):
            issues, _warnings, code = pdfgate.verify_pdf(
                base / "main.pdf", base / "audit" / "report.json", None, None)
        self.assertEqual(code, 8)
        self.assertEqual([i.code for i in issues], ["PDF_TOOL_MISSING"])


if __name__ == "__main__":
    unittest.main()
