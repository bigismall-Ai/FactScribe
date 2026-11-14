# -*- coding: utf-8 -*-
"""P0 第二步：CLI（report check/lock/sign、fact import）、事实账新字段、审计接入。

覆盖：check 成败 / lock 产物 / sign 用法错与越界 card-out / import 的签收门与
final 门 / 幂等 / 脏文件 / dry-run / 导入后审计对账 / 旧账零行为变化。

跑法（仓根）：env PYTHONPATH=. python3 -m unittest discover -s tests -p "test_report_cli.py"
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.audit import run_audit  # noqa: E402
from factscribe.cli import main  # noqa: E402
from factscribe.config import load_config, load_facts, load_sections  # noqa: E402

REPORT_TOML = """\
schema = "factscribe/report@1"
id = "batch23-swb16"
experiment = "ctx-compiler"
status = "final"
generated_at = "2026-11-06T10:00:00Z"
population = { id = "swb16" }

[[metric]]
id = "open.rate"
claim = "开臂准确率"
value = "56.25"
value_type = "percent"
precision = 2
display = "56.25%"
sources = [
  { role = "value", path = "experiments/e/raw/result.json", probe = "json.pointer", pointer = "/summary/rate" },
]

[[metric]]
id = "open.ratio"
claim = "开臂做对的比例"
value = "10/16"
value_type = "ratio"
display = "10/16"
sources = [
  { role = "numerator", path = "experiments/e/raw/run-1.jsonl", probe = "jsonl.count_where", where = "resolved=true", expect_total = 16 },
  { role = "denominator", path = "experiments/e/raw/run-1.jsonl", probe = "jsonl.count" },
]

[[metric]]
id = "open.count"
claim = "开臂做对的题数"
value = "10"
value_type = "count"
display = "10"
sources = [
  { role = "value", path = "experiments/e/raw/run-1.jsonl", probe = "jsonl.count_where", where = "resolved=true", expect_total = 16 },
]
"""

PAPERKIT_TOML = """\
[project]
title = "P0 测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
source_root = "../experiments/e/raw"
"""

OLD_FACT_TOML = """\
[[fact]]
id = "A1"
claim = "旧账里的一条"
value = "42"
source = "run-1.jsonl"
source_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
locator = "旧账"
confidence = "med"
kind = "claim"
"""


def run_cli(*argv):
    """跑 CLI，返回 (退出码, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def last_json(text: str) -> dict:
    """stdout 末行必须是单行 JSON（tail -1 能解析）。"""
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    assert lines, "stdout 是空的"
    return json.loads(lines[-1])


class Workspace:
    """临时工作区：experiments/<e>/raw/ 放原始产物，reports/ 放报告，paper/ 是论文项目。"""

    def __init__(self, tmp: str):
        self.root = Path(tmp) / "ws"
        (self.root / "experiments" / "e" / "raw").mkdir(parents=True)
        (self.root / "reports").mkdir(parents=True)
        paper = self.root / "paper"
        (paper / "sections").mkdir(parents=True)
        (paper / "facts").mkdir(parents=True)
        self.write_raw()
        self.write_paper()
        self.write_report(REPORT_TOML)

    # ---- 原始产物 ----
    def write_raw(self):
        raw = self.root / "experiments" / "e" / "raw"
        lines = [json.dumps({"id": i, "resolved": i <= 10}, ensure_ascii=False)
                 for i in range(1, 17)]
        (raw / "run-1.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (raw / "result.json").write_text(
            json.dumps({"run": "r1", "summary": {"rate": 56.25}}, ensure_ascii=False),
            encoding="utf-8")

    # ---- 论文项目 ----
    def write_paper(self):
        paper = self.root / "paper"
        (paper / "paperkit.toml").write_text(PAPERKIT_TOML, encoding="utf-8")
        (paper / "refs.bib").write_text("", encoding="utf-8")
        (paper / "sections" / "01-intro.tex").write_text(
            "本节没有数字，只有一句话。\n", encoding="utf-8")

    # ---- 报告 ----
    def write_report(self, text: str, name: str = "batch23.report.toml"):
        path = self.root / "reports" / name
        path.write_text(text, encoding="utf-8")
        return path

    @property
    def report_path(self) -> Path:
        return self.root / "reports" / "batch23.report.toml"

    @property
    def paper(self) -> Path:
        return self.root / "paper"

    @property
    def lock_path(self) -> Path:
        return self.root / "reports" / "batch23-swb16.lock.json"

    @property
    def signoff_path(self) -> Path:
        return self.root / "reports" / "batch23-swb16.signoff.toml"

    @property
    def log_path(self) -> Path:
        return self.root / "reports" / "batch23-swb16.signoff.log"

    def lock_and_sign(self):
        code, _out, err = run_cli("report", "lock", str(self.root),
                                  "--report", str(self.report_path))
        assert code == 0, err
        code, _out, err = run_cli("report", "sign", str(self.root),
                                  "--report", str(self.report_path), "--by", "测试员")
        assert code == 0, err

    def audit_codes(self) -> set:
        """跑 audit，返回红项的违规码集合。"""
        cfg = load_config(self.paper)
        facts = load_facts(cfg)
        sections = load_sections(cfg)
        red, _yellow, _hints = run_audit(cfg, facts, sections)[:3]
        return {i.code for i in red}


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


class TestReportCheck(BaseCase):
    """1. check 成功 0；坏报告 1。"""

    def test_check_ok(self):
        code, out, _err = run_cli("report", "check", str(self.ws.root),
                                  "--report", str(self.ws.report_path))
        self.assertEqual(0, code, out)
        self.assertIn("检查通过", out)

    def test_check_json(self):
        code, out, _err = run_cli("report", "check", str(self.ws.root),
                                  "--report", str(self.ws.report_path), "--json")
        self.assertEqual(0, code, out)
        payload = last_json(out)
        self.assertTrue(payload["ok"])
        self.assertEqual("report check", payload["command"])
        self.assertEqual(0, payload["exit"])
        self.assertTrue(payload["report"])

    def test_check_bad_report(self):
        bad = self.ws.write_report(REPORT_TOML.replace('value = "56.25"',
                                                        'value = "99.99"'),
                                    name="bad.report.toml")
        code, out, err = run_cli("report", "check", str(self.ws.root),
                                 "--report", str(bad), "--json")
        self.assertEqual(1, code)
        payload = last_json(out)
        self.assertFalse(payload["ok"])
        self.assertEqual(1, payload["exit"])
        self.assertIn("code", payload["error"])
        self.assertIn("message", payload["error"])

    def test_check_missing_workspace(self):
        code, _out, _err = run_cli("report", "check", str(self.ws.root / "nope"),
                                   "--report", str(self.ws.report_path))
        self.assertEqual(2, code)


class TestReportLock(BaseCase):
    """2. lock 成功后生成 .lock.json。"""

    def test_lock_writes_lock_file(self):
        code, out, err = run_cli("report", "lock", str(self.ws.root),
                                 "--report", str(self.ws.report_path), "--json")
        self.assertEqual(0, code, err)
        self.assertTrue(self.ws.lock_path.is_file())
        lock = json.loads(self.ws.lock_path.read_text(encoding="utf-8"))
        self.assertEqual("factscribe/report-lock@1", lock["schema"])
        self.assertEqual(64, len(lock["semantic_digest"]))
        payload = last_json(out)
        self.assertTrue(payload["ok"])
        self.assertEqual("report lock", payload["command"])

    def test_lock_permission(self):
        self.ws.lock_and_sign()
        mode = self.ws.lock_path.stat().st_mode & 0o777
        self.assertEqual(0o600, mode, "锁文件必须是 0600")


class TestReportSign(BaseCase):
    """3. sign 无 --by → 2；正常签收 0，--card-out 写出卡片；越界 card-out → 1。"""

    def test_sign_without_by(self):
        run_cli("report", "lock", str(self.ws.root), "--report",
                str(self.ws.report_path))
        code, out, _err = run_cli("report", "sign", str(self.ws.root),
                                  "--report", str(self.ws.report_path))
        self.assertEqual(2, code)
        code, out, _err = run_cli("report", "sign", str(self.ws.root),
                                  "--report", str(self.ws.report_path),
                                  "--by", "   ", "--json")
        self.assertEqual(2, code)
        self.assertEqual("USAGE", last_json(out)["error"]["code"])

    def test_sign_ok(self):
        run_cli("report", "lock", str(self.ws.root), "--report",
                str(self.ws.report_path))
        code, out, err = run_cli("report", "sign", str(self.ws.root),
                                 "--report", str(self.ws.report_path),
                                 "--by", "张三")
        self.assertEqual(0, code, err)
        self.assertTrue(self.ws.signoff_path.is_file())
        self.assertTrue(self.ws.log_path.is_file())
        self.assertIn("签收位置", out)
        # 审阅卡逐行打印：每个指标一行
        self.assertIn("open.rate", out)

    def test_sign_card_out(self):
        run_cli("report", "lock", str(self.ws.root), "--report",
                str(self.ws.report_path))
        card = self.ws.root / "audit" / "card.txt"
        code, _out, err = run_cli("report", "sign", str(self.ws.root),
                                  "--report", str(self.ws.report_path),
                                  "--by", "张三", "--card-out", str(card))
        self.assertEqual(0, code, err)
        self.assertTrue(card.is_file())
        text = card.read_text(encoding="utf-8")
        self.assertIn("open.rate", text)
        self.assertIn("open.count", text)

    def test_sign_card_out_escape(self):
        run_cli("report", "lock", str(self.ws.root), "--report",
                str(self.ws.report_path))
        code, out, _err = run_cli("report", "sign", str(self.ws.root),
                                  "--report", str(self.ws.report_path),
                                  "--by", "张三", "--card-out", "../逃逸.txt",
                                  "--json")
        self.assertEqual(1, code)
        self.assertEqual("PATH_ESCAPE", last_json(out)["error"]["code"])


class TestFactImport(BaseCase):
    """4–8. fact import 的门、产物、幂等、脏文件、dry-run。"""

    def facts_file(self) -> Path:
        return self.ws.paper / "facts" / "ctx-compiler.batch23-swb16.toml"

    def test_import_not_signed(self):
        code, out, _err = run_cli("fact", "import", str(self.ws.root),
                                  "--report", str(self.ws.report_path), "--json")
        self.assertEqual(1, code)
        payload = last_json(out)
        self.assertFalse(payload["ok"])
        self.assertEqual("REPORT_LOCK_MISMATCH", payload["error"]["code"])

        run_cli("report", "lock", str(self.ws.root), "--report",
                str(self.ws.report_path))
        code, out, _err = run_cli("fact", "import", str(self.ws.root),
                                  "--report", str(self.ws.report_path), "--json")
        self.assertEqual(1, code)
        self.assertEqual("REPORT_NOT_SIGNED", last_json(out)["error"]["code"])

    def test_import_partial_report(self):
        self.ws.write_report(REPORT_TOML.replace('status = "final"',
                                                  'status = "partial"'))
        code, out, _err = run_cli("fact", "import", str(self.ws.root),
                                  "--report", str(self.ws.report_path), "--json")
        self.assertEqual(1, code)
        self.assertEqual("REPORT_NOT_FINAL", last_json(out)["error"]["code"])

    def test_import_ok(self):
        self.ws.lock_and_sign()
        code, out, err = run_cli("fact", "import", str(self.ws.root),
                                 "--report", str(self.ws.report_path), "--json")
        self.assertEqual(0, code, err)
        payload = last_json(out)
        self.assertTrue(payload["ok"])
        self.assertEqual("fact import", payload["command"])
        self.assertEqual(0, payload["exit"])
        self.assertFalse(payload.get("unchanged"))
        self.assertTrue(self.facts_file().is_file())

        cfg = load_config(self.ws.paper)
        facts = load_facts(cfg)
        self.assertEqual(3, len(facts))
        by_id = {f.id: f for f in facts}
        fid = "ctx-compiler.batch23-swb16.open.rate"
        self.assertIn(fid, by_id)
        fact = by_id[fid]
        self.assertEqual("56.25%", fact.value)
        self.assertEqual("开臂准确率", fact.claim)
        self.assertEqual("result.json", fact.source)
        self.assertEqual(64, len(fact.source_sha256))
        self.assertEqual("json.pointer /summary/rate", fact.locator)
        self.assertEqual("high", fact.confidence)
        self.assertEqual("claim", fact.kind)
        self.assertEqual("reports/batch23.report.toml", fact.report)
        self.assertEqual("open.rate", fact.report_metric)
        # 值就是论文显示形
        self.assertEqual("10/16", by_id["ctx-compiler.batch23-swb16.open.ratio"].value)

    def test_import_idempotent(self):
        self.ws.lock_and_sign()
        run_cli("fact", "import", str(self.ws.root), "--report",
                str(self.ws.report_path))
        before = self.facts_file().read_bytes()
        code, out, err = run_cli("fact", "import", str(self.ws.root),
                                 "--report", str(self.ws.report_path), "--json")
        self.assertEqual(0, code, err)
        self.assertTrue(last_json(out)["unchanged"])
        self.assertEqual(before, self.facts_file().read_bytes())

    def test_import_dirty(self):
        self.ws.lock_and_sign()
        run_cli("fact", "import", str(self.ws.root), "--report",
                str(self.ws.report_path))
        self.facts_file().write_text(
            self.facts_file().read_text(encoding="utf-8") + "\n# 人手改过\n",
            encoding="utf-8")
        code, out, _err = run_cli("fact", "import", str(self.ws.root),
                                  "--report", str(self.ws.report_path), "--json")
        self.assertEqual(1, code)
        self.assertEqual("FACTS_FILE_DIRTY", last_json(out)["error"]["code"])

    def test_import_dry_run(self):
        self.ws.lock_and_sign()
        code, out, err = run_cli("fact", "import", str(self.ws.root),
                                 "--report", str(self.ws.report_path),
                                 "--dry-run", "--json")
        self.assertEqual(0, code, err)
        payload = last_json(out)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["written"])
        self.assertEqual(3, len(payload["facts"]))
        self.assertFalse(self.facts_file().exists())

    def test_import_without_paper(self):
        self.ws.lock_and_sign()
        code, out, _err = run_cli("fact", "import", str(self.ws.root),
                                  "--report", str(self.ws.report_path),
                                  "--paper", str(self.ws.root / "不存在"),
                                  "--json")
        self.assertEqual(2, code)
        self.assertEqual("PAPER_MISSING", last_json(out)["error"]["code"])

    def test_import_source_outside_project(self):
        # 论文项目没配 source_root 时，来源必须落在项目根内
        (self.ws.paper / "paperkit.toml").write_text(
            PAPERKIT_TOML.replace('source_root = "../experiments/e/raw"\n', ""),
            encoding="utf-8")
        self.ws.lock_and_sign()
        code, out, _err = run_cli("fact", "import", str(self.ws.root),
                                  "--report", str(self.ws.report_path), "--json")
        self.assertEqual(1, code)
        self.assertEqual("SOURCE_OUTSIDE_PROJECT", last_json(out)["error"]["code"])


class TestAuditReportBinding(BaseCase):
    """9–10. 导入后审计对账；旧账零行为变化。"""

    def test_audit_clean_after_import(self):
        self.ws.lock_and_sign()
        code, _out, err = run_cli("fact", "import", str(self.ws.root),
                                  "--report", str(self.ws.report_path))
        self.assertEqual(0, code, err)
        codes = self.ws.audit_codes()
        self.assertEqual(set(), {c for c in codes if c.startswith("REPORT_")})

    def test_audit_reports_metric_mismatch(self):
        self.ws.lock_and_sign()
        run_cli("fact", "import", str(self.ws.root), "--report",
                str(self.ws.report_path))
        # 改报告的 display；旧锁会让 check 判不一致，先把锁与签收撤掉
        for path in (self.ws.lock_path, self.ws.signoff_path, self.ws.log_path):
            if path.exists():
                path.unlink()
        self.ws.write_report(REPORT_TOML.replace('display = "56.25%"',
                                                  'display = "57%"'))
        self.ws.lock_and_sign()
        codes = self.ws.audit_codes()
        self.assertIn("REPORT_METRIC_MISMATCH", codes)

    def test_audit_reports_source_swap(self):
        # 来源文件被换成另一份内容相同的文件：哈希没变，但不是报告声明的来源
        self.ws.lock_and_sign()
        run_cli("fact", "import", str(self.ws.root), "--report",
                str(self.ws.report_path))
        raw_dir = self.ws.root / "experiments" / "e" / "raw"
        (raw_dir / "run-2.jsonl").write_bytes((raw_dir / "run-1.jsonl").read_bytes())
        facts_file = self.ws.paper / "facts" / "ctx-compiler.batch23-swb16.toml"
        text = facts_file.read_text(encoding="utf-8")
        facts_file.write_text(text.replace('source = "run-1.jsonl"',
                                           'source = "run-2.jsonl"'),
                              encoding="utf-8")
        self.assertIn("REPORT_SOURCE_MISMATCH", self.ws.audit_codes())

    def test_audit_reports_missing_report(self):
        self.ws.lock_and_sign()
        run_cli("fact", "import", str(self.ws.root), "--report",
                str(self.ws.report_path))
        self.ws.report_path.unlink()
        codes = self.ws.audit_codes()
        self.assertIn("REPORT_MISSING", codes)

    def test_old_ledger_unchanged(self):
        # 旧账（没有 report 字段）：审计结果与导入前一致，也没有 REPORT_* 码
        old = self.ws.paper / "facts" / "01-core.toml"
        old.write_text(OLD_FACT_TOML, encoding="utf-8")
        before = self.ws.audit_codes()
        self.assertEqual(set(), {c for c in before if c.startswith("REPORT_")})
        self.ws.lock_and_sign()
        run_cli("fact", "import", str(self.ws.root), "--report",
                str(self.ws.report_path))
        after = self.ws.audit_codes()
        self.assertEqual(set(), {c for c in after if c.startswith("REPORT_")})


if __name__ == "__main__":
    unittest.main()
