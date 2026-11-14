# -*- coding: utf-8 -*-
"""P0：factscribe/report.py 的报告核心（factscribe/report@1）。

覆盖：合法报告过关 / 缺字段·坏枚举·重复 metric id 报错 / count_where 命中数不符 /
json.pointer 取值 / csv.cell 取格 / 路径逃逸被拒 / 锁后篡改 raw 报哈希不符 /
digest_of 的三条规矩 / 卡片+签收后 verify 通过、改报告后 verify 失败 / 分母为 0 报错。

跑法（仓根）：env PYTHONPATH=. python3 -m unittest discover -s tests -p "test_report_core.py"
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.report import (  # noqa: E402
    ReportError, check_report, digest_of, evidence_digest, load_report,
    lock_report, report_card, semantic_digest, sign_report, verify_signoff)

REPORT_TOML = """\
schema = "factscribe/report@1"
id = "batch23-swb16"
experiment = "ctx-compiler-redblue"
status = "final"
generated_at = "2026-11-06T10:00:00Z"
population = { id = "swb16" }

[[metric]]
id = "open.resolved"
claim = "开臂做对 10 题"
value = "10/16"
value_type = "ratio"
display = "10/16"
sources = [
  { role = "numerator", path = "raw/run-1.jsonl", probe = "jsonl.count_where", where = "resolved=true", expect_total = 16 },
  { role = "denominator", path = "raw/run-1.jsonl", probe = "jsonl.count" },
]

[[metric]]
id = "open.rate"
claim = "开臂准确率"
value = "56.25"
value_type = "percent"
precision = 2
display = "56.25\\\\%"
sources = [
  { role = "value", path = "raw/result.json", probe = "json.pointer", pointer = "/summary/rate" },
]

[[metric]]
id = "csv.count"
claim = "表格里数出来的"
value = "10"
value_type = "count"
display = "10"
sources = [
  { role = "value", path = "raw/summary.csv", probe = "csv.cell", row_column = "arm", row_key = "open", column = "resolved" },
]
"""


def codes(result) -> set:
    return {e["code"] for e in result.get("errors", [])}


class Workspace:
    """临时工作区：raw/ 放原始产物，reports/ 放报告。"""

    def __init__(self, tmp: str):
        self.root = Path(tmp) / "ws"
        (self.root / "raw").mkdir(parents=True)
        (self.root / "reports").mkdir(parents=True)
        self.write_raw()
        self.write_report(REPORT_TOML)

    def write_raw(self):
        lines = []
        for i in range(1, 17):
            lines.append(json.dumps({"id": i, "resolved": i <= 10},
                                    ensure_ascii=False))
        (self.root / "raw" / "run-1.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        (self.root / "raw" / "result.json").write_text(
            json.dumps({"run": "r1", "summary": {"rate": 56.25}}, ensure_ascii=False),
            encoding="utf-8")
        (self.root / "raw" / "summary.csv").write_text(
            "arm,resolved\nopen,10\nclosed,6\n", encoding="utf-8")

    def write_report(self, text: str, name: str = "batch23-swb16.report.toml"):
        path = self.root / "reports" / name
        path.write_text(text, encoding="utf-8")
        return path

    @property
    def report_path(self):
        return self.root / "reports" / "batch23-swb16.report.toml"


class TestValidReport(unittest.TestCase):
    """1. 合法报告 check 通过。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_passes(self):
        result = check_report(self.ws.root, self.ws.report_path)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual([], result["errors"])
        self.assertEqual(3, len(result["metrics"]))
        by_id = {m["id"]: m for m in result["metrics"]}
        self.assertEqual(10, by_id["open.resolved"]["probed"]["numerator"])
        self.assertEqual(16, by_id["open.resolved"]["probed"]["denominator"])
        self.assertEqual("10", by_id["csv.count"]["probed"]["value"])

    def test_load_report_normalizes(self):
        report = load_report(self.ws.root, self.ws.report_path)
        self.assertEqual("factscribe/report@1", report["schema"])
        self.assertEqual("batch23-swb16", report["id"])
        self.assertEqual("final", report["status"])
        self.assertEqual({"id": "swb16"}, report["population"])
        self.assertEqual("reports/batch23-swb16.report.toml", report["path"])
        self.assertEqual(3, len(report["metrics"]))
        self.assertEqual("ratio", report["metrics"][0]["value_type"])

    def test_source_entries_carry_hash_and_size(self):
        result = check_report(self.ws.root, self.ws.report_path)
        source = result["metrics"][0]["sources"][0]
        self.assertEqual("raw/run-1.jsonl", source["path"])
        self.assertEqual(64, len(source["sha256"]))
        self.assertGreater(source["size"], 0)
        self.assertEqual("numerator", source["role"])
        self.assertEqual("jsonl.count_where", source["probe"])


class TestStructureErrors(unittest.TestCase):
    """2. 缺字段 / 坏枚举 / 重复 metric id 报错。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_field(self):
        text = REPORT_TOML.replace('claim = "开臂做对 10 题"\n', "")
        path = self.ws.write_report(text, "missing.report.toml")
        with self.assertRaises(ReportError) as ctx:
            load_report(self.ws.root, path)
        self.assertEqual("MISSING_FIELD", ctx.exception.code)
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("MISSING_FIELD", codes(result))

    def test_missing_display(self):
        text = REPORT_TOML.replace('display = "10/16"\n', "")
        path = self.ws.write_report(text, "nodisplay.report.toml")
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("MISSING_FIELD", codes(result))

    def test_bad_enum(self):
        text = REPORT_TOML.replace('status = "final"', 'status = "done"')
        path = self.ws.write_report(text, "badenum.report.toml")
        with self.assertRaises(ReportError) as ctx:
            load_report(self.ws.root, path)
        self.assertEqual("BAD_ENUM", ctx.exception.code)
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("BAD_ENUM", codes(result))

    def test_bad_value_type(self):
        text = REPORT_TOML.replace('value_type = "count"', 'value_type = "int"')
        path = self.ws.write_report(text, "badtype.report.toml")
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("BAD_ENUM", codes(result))

    def test_dup_metric_id(self):
        text = REPORT_TOML.replace('id = "open.rate"', 'id = "open.resolved"')
        path = self.ws.write_report(text, "dup.report.toml")
        with self.assertRaises(ReportError) as ctx:
            load_report(self.ws.root, path)
        self.assertEqual("DUP_METRIC_ID", ctx.exception.code)
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("DUP_METRIC_ID", codes(result))

    def test_percent_without_precision(self):
        text = REPORT_TOML.replace("precision = 2\n", "")
        path = self.ws.write_report(text, "noprecision.report.toml")
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("MISSING_FIELD", codes(result))

    def test_ratio_needs_numerator_and_denominator(self):
        text = REPORT_TOML.replace('role = "denominator", ', 'role = "value", ')
        path = self.ws.write_report(text, "badsources.report.toml")
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("SOURCE_SET_INVALID", codes(result))


class TestProbes(unittest.TestCase):
    """3/4/5. count_where 命中数不符 / json.pointer 取值 / csv.cell 取格。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_count_where_matched_count_mismatch(self):
        text = REPORT_TOML.replace('value = "10/16"', 'value = "9/16"')
        path = self.ws.write_report(text, "mismatch.report.toml")
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("PROBE_MISMATCH", codes(result))

    def test_count_where_expect_total_mismatch(self):
        text = REPORT_TOML.replace("expect_total = 16", "expect_total = 15")
        path = self.ws.write_report(text, "expecttotal.report.toml")
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("PROBE_MISMATCH", codes(result))

    def test_json_pointer_value(self):
        result = check_report(self.ws.root, self.ws.report_path)
        by_id = {m["id"]: m for m in result["metrics"]}
        self.assertEqual("56.25", by_id["open.rate"]["probed"]["value"])
        detail = by_id["open.rate"]["sources"][0]["detail"]
        self.assertIn("/summary/rate", detail)

    def test_csv_cell_value(self):
        result = check_report(self.ws.root, self.ws.report_path)
        by_id = {m["id"]: m for m in result["metrics"]}
        self.assertEqual("10", by_id["csv.count"]["probed"]["value"])
        self.assertIn("resolved", by_id["csv.count"]["sources"][0]["detail"])

    def test_csv_cell_row_key_not_unique(self):
        (self.ws.root / "raw" / "summary.csv").write_text(
            "arm,resolved\nopen,10\nopen,11\n", encoding="utf-8")
        result = check_report(self.ws.root, self.ws.report_path)
        self.assertFalse(result["ok"])
        self.assertIn("PROBE_ERROR", codes(result))

    def test_json_pointer_missing_key(self):
        text = REPORT_TOML.replace('pointer = "/summary/rate"',
                                   'pointer = "/summary/nope"')
        path = self.ws.write_report(text, "badptr.report.toml")
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("PROBE_ERROR", codes(result))


class TestPathSafety(unittest.TestCase):
    """6. 路径逃逸（../x）与软链被拒。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_relative_escape_rejected(self):
        text = REPORT_TOML.replace('path = "raw/run-1.jsonl"',
                                   'path = "../outside.jsonl"')
        path = self.ws.write_report(text, "escape.report.toml")
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("PATH_ESCAPE", codes(result))
        with self.assertRaises(ReportError) as ctx:
            load_report(self.ws.root, path)
        self.assertEqual("PATH_ESCAPE", ctx.exception.code)

    def test_symlink_rejected(self):
        outside = Path(self.tmp.name) / "outside.jsonl"
        outside.write_text('{"resolved": true}\n', encoding="utf-8")
        link = self.ws.root / "raw" / "link.jsonl"
        try:
            os.symlink(str(outside), str(link))
        except (OSError, NotImplementedError):  # pragma: no cover
            self.skipTest("这个平台不支持软链")
        text = REPORT_TOML.replace('path = "raw/run-1.jsonl"',
                                   'path = "raw/link.jsonl"')
        path = self.ws.write_report(text, "symlink.report.toml")
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("PATH_ESCAPE", codes(result))


class TestLockAndTamper(unittest.TestCase):
    """7. lock 写入后篡改 raw → check 报哈希不符。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lock_written_and_frozen(self):
        lock = lock_report(self.ws.root, self.ws.report_path)
        self.assertEqual("factscribe/report-lock@1", lock["schema"])
        self.assertEqual(64, len(lock["report_sha256"]))
        self.assertEqual(64, len(lock["semantic_digest"]))
        self.assertEqual(64, len(lock["evidence_digest"]))
        self.assertTrue(lock["inputs"])
        self.assertTrue(lock["probe_results"])
        lock_path = self.ws.root / "reports" / "batch23-swb16.lock.json"
        self.assertTrue(lock_path.exists())
        self.assertEqual(0o600, lock_path.stat().st_mode & 0o777)

    def test_tampered_raw_is_reported(self):
        lock_report(self.ws.root, self.ws.report_path)
        raw = self.ws.root / "raw" / "run-1.jsonl"
        raw.write_text(raw.read_text(encoding="utf-8")
                       + json.dumps({"id": 17, "resolved": True}) + "\n",
                       encoding="utf-8")
        result = check_report(self.ws.root, self.ws.report_path)
        self.assertFalse(result["ok"])
        self.assertIn("HASH_MISMATCH", codes(result))

    def test_lock_blocks_report_card(self):
        lock_report(self.ws.root, self.ws.report_path)
        path = self.ws.report_path
        path.write_text(path.read_text(encoding="utf-8")
                        .replace('value = "10/16"', 'value = "11/16"'),
                        encoding="utf-8")
        with self.assertRaises(ReportError) as ctx:
            report_card(self.ws.root, self.ws.report_path)
        self.assertIn(ctx.exception.code, ("LOCK_MISMATCH", "CHECK_FAILED"))


class TestDigest(unittest.TestCase):
    """8. digest_of：键顺序无关、浮点拒收、NFC 等价同摘要。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_key_order_irrelevant(self):
        self.assertEqual(digest_of({"a": 1, "b": 2}),
                         digest_of({"b": 2, "a": 1}))

    def test_float_rejected(self):
        with self.assertRaises(ReportError):
            digest_of({"x": 1.5})
        with self.assertRaises(ReportError):
            digest_of([1, 2.0])

    def test_nfc_equivalent_strings(self):
        composed = "caf\u00e9"          # 预组合的 é
        decomposed = "cafe\u0301"       # 拆开的 e + 组合尖音符
        self.assertNotEqual(composed, decomposed)
        self.assertEqual(unicodedata.normalize("NFC", decomposed), composed)
        self.assertEqual(digest_of(composed), digest_of(decomposed))

    def test_path_fields_are_posix_relative(self):
        a = digest_of({"path": "raw/run-1.jsonl"})
        b = digest_of({"path": "raw\\run-1.jsonl"})
        self.assertEqual(a, b)
        self.assertNotEqual(a, digest_of({"path": "raw/run-2.jsonl"}))

    def test_semantic_digest_ignores_generated_at(self):
        base = {"schema": "factscribe/report@1", "id": "x", "experiment": "e",
                "status": "final", "generated_at": "2026-11-06T10:00:00Z",
                "population": {"id": "p"},
                "metrics": [{"id": "m", "claim": "c", "value": "1",
                             "value_type": "count", "display": "1",
                             "sources": []}]}
        other = dict(base, generated_at="2027-01-01T00:00:00Z")
        self.assertEqual(semantic_digest(base), semantic_digest(other))
        changed = dict(base, metrics=[dict(base["metrics"][0], value="2")])
        self.assertNotEqual(semantic_digest(base), semantic_digest(changed))

    def test_evidence_digest_changes_with_raw(self):
        report = load_report(self.ws.root, self.ws.report_path)
        before = evidence_digest(self.ws.root, report)
        raw = self.ws.root / "raw" / "run-1.jsonl"
        raw.write_text(raw.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertNotEqual(before, evidence_digest(self.ws.root, report))


class TestCardAndSignoff(unittest.TestCase):
    """9. card/signoff 生成后 verify 通过；改动报告后 verify 失败。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_card_lines(self):
        lock_report(self.ws.root, self.ws.report_path)
        card = report_card(self.ws.root, self.ws.report_path)
        self.assertLessEqual(len(card["lines"]), 6)
        self.assertTrue(card["lines"])
        self.assertEqual(64, len(card["card_digest"]))
        joined = "\n".join(card["lines"])
        self.assertIn("open.resolved", joined)
        self.assertIn("raw/run-1.jsonl", joined)
        self.assertIn("请确认", joined)

    def test_card_requires_lock(self):
        with self.assertRaises(ReportError) as ctx:
            report_card(self.ws.root, self.ws.report_path)
        self.assertEqual("LOCK_MISSING", ctx.exception.code)

    def test_signoff_and_verify(self):
        lock_report(self.ws.root, self.ws.report_path)
        signoff = sign_report(self.ws.root, self.ws.report_path, "moc")
        self.assertEqual("factscribe/report-signoff@1", signoff["schema"])
        self.assertEqual("moc", signoff["signed_by"])
        self.assertTrue((self.ws.root / "reports"
                         / "batch23-swb16.signoff.toml").exists())
        self.assertTrue((self.ws.root / "reports"
                         / "batch23-swb16.signoff.log").exists())
        verified = verify_signoff(self.ws.root, self.ws.report_path)
        self.assertTrue(verified["ok"], verified["reason"])
        self.assertIsNotNone(verified["signoff"])

    def test_signoff_chain_links(self):
        lock_report(self.ws.root, self.ws.report_path)
        first = sign_report(self.ws.root, self.ws.report_path, "moc")
        second = sign_report(self.ws.root, self.ws.report_path, "moc")
        self.assertEqual("0" * 64, first["prev_sha256"])
        self.assertEqual(first["entry_sha256"], second["prev_sha256"])

    def test_card_out_written(self):
        lock_report(self.ws.root, self.ws.report_path)
        out = self.ws.root / "reports" / "card.txt"
        sign_report(self.ws.root, self.ws.report_path, "moc", card_out=out)
        self.assertTrue(out.exists())
        self.assertIn("open.resolved", out.read_text(encoding="utf-8"))

    def test_verify_fails_after_report_changed(self):
        lock_report(self.ws.root, self.ws.report_path)
        sign_report(self.ws.root, self.ws.report_path, "moc")
        path = self.ws.report_path
        path.write_text(path.read_text(encoding="utf-8")
                        .replace('value = "10/16"', 'value = "11/16"'),
                        encoding="utf-8")
        verified = verify_signoff(self.ws.root, self.ws.report_path)
        self.assertFalse(verified["ok"])
        self.assertTrue(verified["reason"])

    def test_verify_fails_without_signoff(self):
        lock_report(self.ws.root, self.ws.report_path)
        verified = verify_signoff(self.ws.root, self.ws.report_path)
        self.assertFalse(verified["ok"])
        self.assertIsNone(verified["signoff"])


class TestZeroDenominator(unittest.TestCase):
    """10. 分母为 0 → 错。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_declared_zero_denominator(self):
        text = REPORT_TOML.replace('value = "10/16"', 'value = "10/0"')
        path = self.ws.write_report(text, "zeroden.report.toml")
        result = check_report(self.ws.root, path)
        self.assertFalse(result["ok"])
        self.assertIn("ZERO_DENOMINATOR", codes(result))

    def test_probed_zero_denominator(self):
        (self.ws.root / "raw" / "run-1.jsonl").write_text("", encoding="utf-8")
        result = check_report(self.ws.root, self.ws.report_path)
        self.assertFalse(result["ok"])
        self.assertIn("ZERO_DENOMINATOR", codes(result))


class TestMiniTomlFallback(unittest.TestCase):
    """3.10 兜底解析器：inline table 与 inline table 数组要认。"""

    def test_parses_report_shape(self):
        from factscribe.report import _MiniToml
        data = _MiniToml(REPORT_TOML).parse()
        self.assertEqual("factscribe/report@1", data["schema"])
        self.assertEqual({"id": "swb16"}, data["population"])
        self.assertEqual(3, len(data["metric"]))
        first = data["metric"][0]
        self.assertEqual("10/16", first["value"])
        self.assertEqual(2, len(first["sources"]))
        self.assertEqual("numerator", first["sources"][0]["role"])
        self.assertEqual(16, first["sources"][0]["expect_total"])
        self.assertEqual(2, data["metric"][1]["precision"])

    def test_matches_tomllib_when_available(self):
        # 3.10 没有 tomllib，不能因此 skip（CI 把跳过当未覆盖）；
        # 没有 tomllib 时改对一份固定的期望值，保证兜底解析器仍被验。
        from factscribe.report import _MiniToml
        parsed = _MiniToml(REPORT_TOML).parse()
        try:
            import tomllib
        except ModuleNotFoundError:
            self.assertEqual(
                {"schema": "factscribe/report@1",
                 "id": "batch23-swb16",
                 "experiment": "ctx-compiler-redblue",
                 "status": "final",
                 "population": {"id": "swb16"}},
                {k: parsed[k] for k in ("schema", "id", "experiment", "status",
                                        "population")})
            self.assertEqual(3, len(parsed["metric"]))
            self.assertEqual("10/16", parsed["metric"][0]["value"])
            return
        self.assertEqual(tomllib.loads(REPORT_TOML), parsed)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TestCardBoundaries(unittest.TestCase):
    """卡片不许截断；--card-out 不许跑出工作区。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_card_lists_every_metric(self):
        blocks = []
        for i in range(7):
            blocks.append("""
[[metric]]
id = "m%d"
claim = "第 %d 条"
value = "10"
value_type = "count"
display = "10"
sources = [
  { role = "value", path = "raw/summary.csv", probe = "csv.cell", row_column = "arm", row_key = "open", column = "resolved" },
]
""" % (i, i))
        head = """schema = "factscribe/report@1"
id = "seven"
experiment = "e"
status = "final"
generated_at = "2026-11-14T00:00:00Z"
population = { id = "p" }
"""
        path = self.ws.write_report(head + "".join(blocks), name="seven.report.toml")
        lock_report(self.ws.root, path)
        card = report_card(self.ws.root, path)
        self.assertEqual(7, len(card["lines"]), "卡片截断会让人签下没看见的指标")
        for i in range(7):
            self.assertTrue(any("m%d" % i in line for line in card["lines"]))

    def test_card_out_escape_rejected(self):
        lock_report(self.ws.root, self.ws.report_path)
        with self.assertRaises(ReportError) as ctx:
            sign_report(self.ws.root, self.ws.report_path, "moc",
                        card_out="../escape.txt")
        self.assertEqual("PATH_ESCAPE", ctx.exception.code)
        self.assertFalse((self.ws.root.parent / "escape.txt").exists())
