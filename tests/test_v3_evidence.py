# -*- coding: utf-8 -*-
"""批 50：V3 证据模型判据的正负测试（与盲测集互补的合成样例）。

覆盖：项目声明别名、runs/ 证据根、BU 句子指纹、断言漂移、数值宏形状/
双签、key 信任根、PDF 双向多重集与白名单。所有样例都在临时目录内合成，
不读任何外部的封存盲测集。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe import pdfgate  # noqa: E402
from factscribe.audit import _aggregate_exit, _v3_whitelist  # noqa: E402
from factscribe.config import load_config  # noqa: E402
from factscribe.facts import Fact  # noqa: E402
from factscribe.v3 import (bu_index, assertion_issues,  # noqa: E402
                           key_trust_issues, numeric_macro_issues)


def run_audit(project: Path):
    proc = subprocess.run([sys.executable, "-m", "factscribe", "audit",
                           str(project), "--json"],
                          cwd=str(ROOT), capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError(proc.stdout[:400] + proc.stderr[:400])
    return proc.returncode, data


def codes_of(data: dict) -> set[str]:
    return {str(f.get("code")) for f in data.get("findings", [])}


V3_TOML = """schema = "factscribe/3.0"
root_tex = "main.tex"
facts = "facts"
refs = "refs.bib"

[project]
title = "synthetic"
signing_mode = "offline_manifest"
number_locale = "dot"
frac_allow = []
inline_images_allow = []
numeric_macro_allow = []
"""

FACT = """id = "A1"
role = "results"
quantitative = true
value = "10/16"
display = ["10/16", "62.5%"]
source = "runs/r1/summary.json"
run_id = "r1"
pointer = "/summary/on_resolved"
"""


def make_v3(root: Path, body: str = "We resolved \\fact{A1}{10/16} tasks.\n",
            toml: str = V3_TOML, pdf_from: Path | None = None,
            fact: str = FACT, bib: str = "") -> Path:
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "runs" / "r1").mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(toml, encoding="utf-8")
    (root / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\n\\input{sections/body}\n"
        "\\end{document}\n", encoding="utf-8")
    (root / "sections" / "body.tex").write_text(body, encoding="utf-8")
    (root / "facts" / "A1.toml").write_text(fact, encoding="utf-8")
    (root / "runs" / "r1" / "summary.json").write_text(
        '{"run_id": "r1", "summary": {"on_resolved": 10, "n": 16}}\n',
        encoding="utf-8")
    (root / "refs.bib").write_text(bib, encoding="utf-8")
    if pdf_from is not None:
        shutil.copyfile(pdf_from, root / "main.pdf")
    return root


class V3ConfigTest(unittest.TestCase):
    def test_factscribe_schema_alias_with_project_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(make_v3(Path(tmp)))
            self.assertTrue(cfg.is_v3)
            self.assertEqual(cfg.schema, "factscribe/3.0")
            self.assertEqual(cfg.root_tex, "main.tex")
            self.assertEqual(cfg.facts_glob, "facts/*.toml")
            self.assertEqual(cfg.number_locale, "period")   # dot 的规范名
            self.assertEqual(cfg.source_dir, "runs")

    def test_numeric_macro_tables_are_structured(self):
        toml = V3_TOML + """
[[numeric_macro_allow]]
name = "numwidth"
parameter_kind = "count"
body_regex = '^[0-9]+$'
reason = "layout"
signed_by = ["ed25519:A", "ed25519:B"]
expires = "2099-01-01"
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(make_v3(Path(tmp), toml=toml))
            self.assertEqual(len(cfg.numeric_macro_rules), 1)
            self.assertEqual(cfg.numeric_macro_rules[0]["name"], "numwidth")

    def test_v1_stays_v1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "paperkit.toml").write_text(
                '[project]\ntitle = "x"\nsections = "sections/*.tex"\n'
                'facts = "facts/*.toml"\n', encoding="utf-8")
            cfg = load_config(root)
            self.assertFalse(cfg.is_v3)
            self.assertEqual(cfg.source_dir, "results")


class BuFingerprintTest(unittest.TestCase):
    TEXT = ("Assembly succeeded in \\fact{A1}{62.5\\%} of the runs under "
            "the recorded schedule.\n")

    def test_fingerprint_matches_frozen_formula(self):
        index = bu_index([("sections/body.tex", self.TEXT)])
        bu = index["sections/body.tex#1"]
        self.assertEqual(
            bu.sha256,
            "sha256:94fd7854fc2f1ed6ae2b16d16a6658c1133169ecfeaaac39c5f1978a5c8b9845")
        self.assertIn("A1", bu.fact_ids)

    def test_assertion_drift_when_bu_moved(self):
        fact = Fact(id="A1", file="facts/A1.toml", line=1)
        fact.assertions = [{
            "bu_id": "sections/body.tex#1",
            "bu_text_sha256":
                "sha256:94fd7854fc2f1ed6ae2b16d16a6658c1133169ecfeaaac39c5f1978a5c8b9845",
        }]
        moved = [("sections/body.tex",
                  "The report is in the appendix. The schedule is recorded.\n")]
        issues = assertion_issues([fact], bu_index(moved))
        self.assertIn("ASSERTION_DRIFT", {i.code for i in issues})

    def test_assertion_ok_when_bu_carries_marker(self):
        fact = Fact(id="A2", file="facts/A2.toml", line=1)
        fact.assertions = [{
            "bu_id": "sections/body.tex#1",
            # 指纹算法版本差异（不一样），但 BU 确实承载 A2 的绑定标记
            "bu_text_sha256": "sha256:" + "0" * 64,
        }]
        text = [("sections/body.tex", "Of \\fact{A2}{10} runs, 16 were kept.\n")]
        self.assertEqual(assertion_issues([fact], bu_index(text)), [])


class NumericMacroTest(unittest.TestCase):
    def _cfg(self, rule):
        import types
        return types.SimpleNamespace(numeric_macro_rules=[rule])

    def test_valid_count_macro(self):
        cfg = self._cfg({"name": "numwidth", "parameter_kind": "count",
                         "body_regex": "^[0-9]+$",
                         "signed_by": ["ed25519:A", "ed25519:B"],
                         "expires": "2099-01-01"})
        self.assertEqual(numeric_macro_issues(cfg), [])

    def test_bad_shape_and_double_sign(self):
        cfg = self._cfg({"name": "resrate", "parameter_kind": "count",
                         "body_regex": "^[0-9.]+$",
                         "signed_by": ["ed25519:A", "ed25519:A"],
                         "expires": "2099-01-01"})
        codes = {i.code for i in numeric_macro_issues(cfg)}
        self.assertIn("NUMERIC_MACRO_SHAPE_INVALID", codes)
        self.assertIn("NUMERIC_MACRO_DOUBLE_SIGN", codes)

    def test_expired_registration(self):
        cfg = self._cfg({"name": "figwidth", "parameter_kind": "width",
                         "body_regex": "^[0-9.]+ *(?:linewidth|textwidth|columnwidth)$",
                         "signed_by": ["ed25519:A", "ed25519:B"],
                         "expires": "2000-01-01"})
        self.assertIn("NUMERIC_MACRO_EXPIRED",
                      {i.code for i in numeric_macro_issues(cfg)})


class KeyTrustTest(unittest.TestCase):
    def test_key_inside_project_is_untrusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp))
            (root / "audit").mkdir()
            (root / "audit" / "keys.json").write_text("{}", encoding="utf-8")
            toml = V3_TOML.replace(
                'numeric_macro_allow = []',
                'numeric_macro_allow = []\napprover_keys_file = "audit/keys.json"')
            (root / "factscribe.toml").write_text(toml, encoding="utf-8")
            issues = key_trust_issues(load_config(root))
            self.assertIn("STAMP_KEY_UNTRUSTED", {i.code for i in issues})
            self.assertEqual({i.exit_code for i in issues}, {5})

    def test_key_outside_project_is_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = make_v3(base / "proj")
            keys = base / "_keys" / "approver_keys.json"
            keys.parent.mkdir(parents=True)
            keys.write_text("{}", encoding="utf-8")
            toml = V3_TOML.replace(
                'numeric_macro_allow = []',
                'numeric_macro_allow = []\n'
                'approver_keys_file = "../_keys/approver_keys.json"')
            (root / "factscribe.toml").write_text(toml, encoding="utf-8")
            self.assertEqual(key_trust_issues(load_config(root)), [])


class PdfMultisetTest(unittest.TestCase):
    BENIGN = ROOT / "fixtures" / "benign" / "R3-PDF-RASTER" / "main.pdf"
    RASTER = ROOT / "fixtures" / "hostile" / "R3-PDF-RASTER" / "main.pdf"

    def test_pct_produces_both_keys(self):
        counts = pdfgate.pdf_number_counts("rate 62.5% only")
        self.assertEqual(counts["62.5"], 1)
        self.assertEqual(counts["0.625"], 1)

    def test_equal_multiset_is_green(self):
        issues, _warnings = pdfgate.verify_document(
            self.BENIGN, {"number_ledger": [
                {"fact_id": "A1", "keys": ["10", "16"]}], "pdf_whitelist": []})
        self.assertEqual(issues, [])

    def test_missing_ledger_token_is_red(self):
        issues, _warnings = pdfgate.verify_document(
            self.BENIGN, {"number_ledger": [
                {"fact_id": "A1", "keys": ["10", "16", "0.625"]}],
                "pdf_whitelist": []})
        self.assertIn("PDF_LEDGER_TOKEN_MISSING", {i.code for i in issues})

    def test_unaccounted_number_is_red(self):
        issues, _warnings = pdfgate.verify_document(
            self.BENIGN, {"number_ledger": [
                {"fact_id": "A1", "keys": ["10"]}], "pdf_whitelist": []})
        self.assertIn("PDF_UNACCOUNTED_NUMBER", {i.code for i in issues})

    def test_whitelisted_reference_number_is_green(self):
        issues, _warnings = pdfgate.verify_document(
            self.BENIGN, {"number_ledger": [
                {"fact_id": "A1", "keys": ["10", "16"]}],
                "pdf_whitelist": [{"key": "2024", "count": 1,
                                   "source": "refs.bib#k.year"}]})
        # PDF 里没有 2024 → 只应有「白名单未用」的黄，不判红
        self.assertEqual(issues, [])

    def test_rasterized_page_is_red(self):
        issues, _warnings = pdfgate.verify_document(
            self.RASTER, {"number_ledger": [], "pdf_whitelist": []})
        codes = {i.code for i in issues}
        self.assertIn("PDF_PAGE_NO_TEXT", codes)
        self.assertIn("PDF_PAGE_RASTERIZED", codes)

    def test_bib_whitelist_expands_fields(self):
        class E:
            key = "k"
            file = "refs.bib"
            fields = {"year": "2024", "pages": "1--8"}

        items = {i["key"]: i for i in _v3_whitelist([E()], {"k": 1})}
        self.assertIn("2024", items)
        self.assertIn("1", items)
        self.assertIn("8", items)


class AuditIntegrationTest(unittest.TestCase):
    """V3 项目从 runs/ 取证据、从 output 取 PDF，整条 audit 走到同一结论。"""

    BENIGN = ROOT / "fixtures" / "benign" / "R3-PDF-RASTER" / "main.pdf"
    RASTER = ROOT / "fixtures" / "hostile" / "R3-PDF-RASTER" / "main.pdf"

    def test_v3_project_with_matching_pdf_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp), pdf_from=self.BENIGN)
            code, data = run_audit(root)
            self.assertEqual(code, 0, data.get("findings"))
            self.assertEqual(codes_of(data), set())

    def test_v3_project_with_raster_pdf_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp), pdf_from=self.RASTER)
            code, data = run_audit(root)
            self.assertEqual(code, 5)
            self.assertTrue({"PDF_PAGE_NO_TEXT", "PDF_PAGE_RASTERIZED"}
                            <= codes_of(data))

    def test_v3_project_with_internal_key_is_untrusted(self):
        toml = V3_TOML.replace(
            'numeric_macro_allow = []',
            'numeric_macro_allow = []\napprover_keys_file = "audit/keys.json"')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_v3(Path(tmp), toml=toml, pdf_from=self.BENIGN)
            (root / "audit").mkdir()
            (root / "audit" / "keys.json").write_text("{}", encoding="utf-8")
            code, data = run_audit(root)
            self.assertEqual(code, 5)
            self.assertIn("STAMP_KEY_UNTRUSTED", codes_of(data))

    def test_v3_error_exit_prefers_integrity(self):
        from factscribe.audit import Issue
        red = [Issue("BOUND_MISMATCH", "x", exit_code=1),
               Issue("PDF_LEDGER_TOKEN_MISSING", "y", exit_code=5)]
        self.assertEqual(_aggregate_exit(red, [], integrity_first=True), 5)
        self.assertEqual(_aggregate_exit(red, [], integrity_first=False), 1)


if __name__ == "__main__":
    unittest.main()
