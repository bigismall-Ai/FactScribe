# -*- coding: utf-8 -*-
"""实验报告的工作台接口：GET /api/reports 与 POST /api/reports/action。

钉住：

- 列表按工作区扫（experiments/*/reports/ 与 reports/），逐份给出状态；
- check 只读（只读服务也能查）；lock / sign / import 要 --allow-write；
- sign 缺签收人 → 400 USAGE；越界路径 → 400；
- import 走既有三道门：没签收不让入账，签收后写进 facts/。

跑法（仓根）：python3 -m unittest discover -s tests -p "test_report_api.py"
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.serve import create_server  # noqa: E402

TOKEN = "report-token"

REPORT_TOML = """\
schema = "factscribe/report@1"
id = "batch23"
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
"""

OTHER_REPORT_TOML = """\
schema = "factscribe/report@1"
id = "batch24"
experiment = "ctx-compiler"
status = "partial"
generated_at = "2026-11-07T10:00:00Z"
population = { id = "swb16" }

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
title = "报告接口测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
source_root = ".."
"""


class Workspace:
    """临时工作区：ws/ 是工作区根，ws/paper/ 是论文项目（serve 的项目）。

    source_root = ".." ⇒ 工作区＝ws/，报告在 ws/experiments/e/reports/ 与
    ws/reports/ 下，原始产物在 ws/experiments/e/raw/ 下。
    """

    def __init__(self, tmp: str):
        self.root = Path(tmp) / "ws"
        (self.root / "experiments" / "e" / "raw").mkdir(parents=True)
        (self.root / "experiments" / "e" / "reports").mkdir(parents=True)
        (self.root / "reports").mkdir(parents=True)
        paper = self.root / "paper"
        (paper / "sections").mkdir(parents=True)
        (paper / "facts").mkdir(parents=True)
        self.write_raw()
        self.write_paper()
        self.write_report(REPORT_TOML, "experiments/e/reports/batch23.report.toml")
        self.write_report(OTHER_REPORT_TOML, "reports/batch24.report.toml")

    def write_raw(self):
        raw = self.root / "experiments" / "e" / "raw"
        lines = [json.dumps({"id": i, "resolved": i <= 10}, ensure_ascii=False)
                 for i in range(1, 17)]
        (raw / "run-1.jsonl").write_text("\n".join(lines) + "\n",
                                         encoding="utf-8")
        (raw / "result.json").write_text(
            json.dumps({"run": "r1", "summary": {"rate": 56.25}},
                       ensure_ascii=False),
            encoding="utf-8")

    def write_paper(self):
        paper = self.root / "paper"
        (paper / "paperkit.toml").write_text(PAPERKIT_TOML, encoding="utf-8")
        (paper / "refs.bib").write_text("", encoding="utf-8")
        (paper / "sections" / "01-intro.tex").write_text(
            "本节没有数字，只有一句话。\n", encoding="utf-8")

    def write_report(self, text: str, rel: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    @property
    def paper(self) -> Path:
        return self.root / "paper"

    @property
    def report_rel(self) -> str:
        return "experiments/e/reports/batch23.report.toml"

    @property
    def report_abs(self) -> Path:
        return self.root / self.report_rel

    @property
    def facts_file(self) -> Path:
        return self.paper / "facts" / "ctx-compiler.batch23.toml"


class ReportApiBase:
    """每个用例一套干净的工作区与服务（动作会改状态，不能串味）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)
        self.server, self.token = create_server(
            self.ws.paper, port=0, token=TOKEN, allow_write=True)
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    # ------------------------------------------------------------ 工具

    def _request(self, path, method="GET", body=None, token=None):
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, method=method,
                                     headers=headers, data=data)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8")
            finally:
                exc.close()
            return exc.code, json.loads(raw) if raw else {}

    def reports(self):
        status, data = self._request("/api/reports", token=self.token)
        self.assertEqual(status, 200, data)
        return data

    def action(self, body, token=None):
        return self._request("/api/reports/action", method="POST", body=body,
                             token=token or self.token)

    def entry(self, rel=None):
        rel = rel or self.ws.report_rel
        for item in self.reports()["reports"]:
            if item["path"] == rel:
                return item
        self.fail("列表里没有 %s" % rel)

    # ------------------------------------------------------------ 1. 列表

    def test_lists_reports_in_workspace(self):
        data = self.reports()
        self.assertTrue(data["ok"])
        self.assertEqual(str(self.ws.root.resolve()), data["workspace"])
        paths = [item["path"] for item in data["reports"]]
        self.assertIn("experiments/e/reports/batch23.report.toml", paths)
        self.assertIn("reports/batch24.report.toml", paths)

    def test_entry_shape(self):
        item = self.entry()
        self.assertEqual("batch23", item["id"])
        self.assertEqual("ctx-compiler", item["experiment"])
        self.assertEqual("final", item["status"])
        self.assertEqual(2, item["metrics"])
        self.assertFalse(item["locked"])
        self.assertFalse(item["signed"])
        self.assertFalse(item["lock_ok"])
        self.assertTrue(item["reason"], "没封存没签收要说清为什么")

    def test_reports_need_token(self):
        status, data = self._request("/api/reports")
        self.assertEqual(status, 401)
        self.assertEqual("UNAUTHORIZED", data["error"]["code"])

    # ------------------------------------------------------------ 2. check / lock

    def test_check_is_read_only(self):
        status, data = self.action({"action": "check",
                                    "report": self.ws.report_rel})
        self.assertEqual(status, 200, data)
        self.assertEqual("check", data["action"])
        self.assertTrue(data["result"]["ok"], data["result"])
        self.assertEqual(2, len(data["result"]["metrics"]))

    def test_lock_then_entry_locked(self):
        status, data = self.action({"action": "lock",
                                    "report": self.ws.report_rel})
        self.assertEqual(status, 200, data)
        self.assertTrue(data["result"]["locked"])
        item = self.entry()
        self.assertTrue(item["locked"])
        self.assertTrue(item["lock_ok"])

    def test_lock_makes_card_visible(self):
        self.action({"action": "lock", "report": self.ws.report_rel})
        item = self.entry()
        self.assertTrue(item["card"], "封存后要能出审阅卡")
        self.assertTrue(any("open.ratio" in line for line in item["card"]))

    # ------------------------------------------------------------ 3. sign

    def test_sign_requires_by(self):
        self.action({"action": "lock", "report": self.ws.report_rel})
        status, data = self.action({"action": "sign",
                                    "report": self.ws.report_rel})
        self.assertEqual(status, 400)
        self.assertEqual("USAGE", data["error"]["code"])
        status, data = self.action({"action": "sign",
                                    "report": self.ws.report_rel, "by": "  "})
        self.assertEqual(status, 400)
        self.assertEqual("USAGE", data["error"]["code"])

    def test_sign_ok(self):
        self.action({"action": "lock", "report": self.ws.report_rel})
        status, data = self.action({"action": "sign",
                                    "report": self.ws.report_rel, "by": "张三"})
        self.assertEqual(status, 200, data)
        self.assertTrue(data["result"]["signed"])
        self.assertEqual("张三", data["result"]["signed_by"])
        item = self.entry()
        self.assertTrue(item["signed"])

    # ------------------------------------------------------------ 4. import

    def test_import_needs_signoff(self):
        status, data = self.action({"action": "import",
                                    "report": self.ws.report_rel})
        self.assertEqual(status, 400, data)
        self.assertIn(data["error"]["code"],
                      ("REPORT_LOCK_MISMATCH", "REPORT_NOT_SIGNED"))
        self.assertFalse(self.ws.facts_file.exists())

    def test_import_after_signoff(self):
        self.action({"action": "lock", "report": self.ws.report_rel})
        self.action({"action": "sign", "report": self.ws.report_rel,
                     "by": "张三"})
        status, data = self.action({"action": "import",
                                    "report": self.ws.report_rel})
        self.assertEqual(status, 200, data)
        self.assertTrue(data["result"]["written"])
        self.assertTrue(self.ws.facts_file.is_file())
        text = self.ws.facts_file.read_text(encoding="utf-8")
        self.assertIn("ctx-compiler.batch23.open.rate", text)

    def test_import_dry_run_writes_nothing(self):
        self.action({"action": "lock", "report": self.ws.report_rel})
        self.action({"action": "sign", "report": self.ws.report_rel,
                     "by": "张三"})
        status, data = self.action({"action": "import",
                                    "report": self.ws.report_rel,
                                    "dry_run": True})
        self.assertEqual(status, 200, data)
        self.assertTrue(data["result"]["dry_run"])
        self.assertFalse(data["result"]["written"])
        self.assertFalse(self.ws.facts_file.exists())

    # ------------------------------------------------------------ 5. 只读服务

    def test_read_only_server_refuses_lock(self):
        server, token = create_server(self.ws.paper, port=0, token=TOKEN,
                                      allow_write=False)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:%d" % port

            def call(path, method="GET", body=None):
                headers = {"Authorization": "Bearer " + token}
                data = None
                if body is not None:
                    data = json.dumps(body).encode("utf-8")
                    headers["Content-Type"] = "application/json"
                req = urllib.request.Request(base + path, method=method,
                                             headers=headers, data=data)
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return resp.status, json.loads(resp.read().decode())
                except urllib.error.HTTPError as exc:
                    try:
                        raw = exc.read().decode("utf-8")
                    finally:
                        exc.close()
                    return exc.code, json.loads(raw) if raw else {}

            status, data = call("/api/reports/action", "POST",
                                {"action": "lock", "report": self.ws.report_rel})
            self.assertEqual(status, 403)
            self.assertEqual("READ_ONLY", data["error"]["code"])
            # 只读服务照样能查报告
            status, data = call("/api/reports")
            self.assertEqual(status, 200)
            self.assertTrue(data["reports"])
            status, data = call("/api/reports/action", "POST",
                                {"action": "check", "report": self.ws.report_rel})
            self.assertEqual(status, 200, data)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    # ------------------------------------------------------------ 6. 越界路径

    def test_path_escape_rejected(self):
        outside = Path(self.tmp.name) / "outside.report.toml"
        outside.write_text(REPORT_TOML, encoding="utf-8")
        for ref in ("../outside.report.toml", str(outside),
                    "experiments/e/reports/../../outside.report.toml"):
            status, data = self.action({"action": "check", "report": ref})
            self.assertEqual(status, 400, ref)
            self.assertEqual("PATH_ESCAPE", data["error"]["code"], ref)

    def test_missing_report_field(self):
        status, data = self.action({"action": "check"})
        self.assertEqual(status, 400)
        self.assertEqual("USAGE", data["error"]["code"])

    def test_unknown_action(self):
        status, data = self.action({"action": "delete",
                                    "report": self.ws.report_rel})
        self.assertEqual(status, 400)
        self.assertEqual("USAGE", data["error"]["code"])


class ReportApiTest(ReportApiBase, unittest.TestCase):
    """报告接口的契约。"""


class ReportAliasTest(ReportApiBase, unittest.TestCase):
    """POST /api/reports 是 /api/reports/action 的别名（同一份界面要同一个 URL）。"""

    def test_alias_path_works(self):
        status, data = self._request("/api/reports", method="POST",
                                     body={"action": "check",
                                           "report": self.ws.report_rel},
                                     token=self.token)
        self.assertEqual(status, 200, data)
        self.assertEqual("check", data["action"])


if __name__ == "__main__":
    unittest.main()
