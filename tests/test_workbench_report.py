# -*- coding: utf-8 -*-
"""工作台段三：检查报告 / 只读重跑 / 机器视图端点。

用仓库里的真项目样本（``examples/minimal`` 或 ``fixtures/legal-demo``）
当被测项目，断言三件事：

1. 端点结构：体检摘要、发现列表、四步链、账本表行数；
2. 只读性：重跑前后项目目录零写入（哈希一致）；
3. 坏项目不崩：结构化错误，不是 500。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import unittest
import unittest.mock as mock
import urllib.error
import urllib.request
from pathlib import Path

from factscribe.workbench import checkreport
from factscribe.workbench.server import create_server

REPO = Path(__file__).resolve().parents[1]
SAMPLES = [REPO / "examples" / "minimal", REPO / "fixtures" / "legal-demo"]


def _dir_manifest(root: Path) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = Path(dirpath) / name
            rel = str(full.relative_to(root))
            try:
                out[rel] = hashlib.sha256(full.read_bytes()).hexdigest()
            except OSError:
                out[rel] = ""
    return out


def _sample_copy(tmp: Path) -> Path:
    """把真项目样本拷进临时目录（测试不该动仓库里的样本）。"""
    for sample in SAMPLES:
        if sample.is_dir():
            dst = tmp / sample.name
            shutil.copytree(sample, dst)
            return dst
    raise unittest.SkipTest("仓库里没有可用的真项目样本")


class _ServerCase(unittest.TestCase):
    """起一个真服务（临时根目录）供端点测试用。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.disk = _sample_copy(self.tmp)
        self.server, self.index = create_server(self.tmp, port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.project_id = self.disk.name
        self.disk_id = self.disk.name

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    def _url(self, path: str) -> str:
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def get(self, path: str) -> dict:
        with urllib.request.urlopen(self._url(path)) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post(self, path: str, body: dict | None = None) -> dict:
        raw = json.dumps(body or {}).encode("utf-8")
        req = urllib.request.Request(self._url(path), data=raw,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def disk_url(self, what: str) -> str:
        return "/api/disk/%s/%s/%s" % (self.project_id, self.disk_id, what)


class ReportEndpointTests(_ServerCase):
    def test_report_has_health_findings_and_chain(self):
        data = self.get(self.disk_url("report"))
        self.assertTrue(data.get("ok"), data)
        health = data["health"]
        for key in ("red", "yellow", "facts", "sections", "status",
                    "digest", "digest_short"):
            self.assertIn(key, health)
        self.assertEqual(len(health["digest_short"]), 8)
        self.assertEqual(health["digest"], health["digest"][:64])
        self.assertIsInstance(data["findings"], list)
        for finding in data["findings"]:
            self.assertIn(finding["severity"], ("red", "yellow"))
            self.assertTrue(finding["code"])
            self.assertIn("message", finding)
        chain = data["chain"]
        self.assertEqual(len(chain), 4)
        self.assertEqual([step["key"] for step in chain],
                         ["declare", "bind", "reconcile", "certify"])

    def test_report_facts_count_matches_ledger(self):
        data = self.get(self.disk_url("report"))
        machine = self.get(self.disk_url("machine"))
        self.assertEqual(data["health"]["facts"],
                         machine["groups"]["ledger"]["total"])
        self.assertEqual(len(machine["groups"]["ledger"]["rows"]),
                         data["health"]["facts"])

    def test_machine_has_four_groups(self):
        data = self.get(self.disk_url("machine"))
        self.assertTrue(data.get("ok"), data)
        groups = data["groups"]
        for key in ("ledger", "scan", "chain", "export"):
            self.assertIn(key, groups)
        row = groups["ledger"]["rows"][0]
        self.assertEqual(len(row["fp_short"]), 8)
        self.assertIn("fp", row)
        self.assertTrue(groups["export"]["commands"])


class RerunTests(_ServerCase):
    def test_rerun_is_readonly(self):
        before = _dir_manifest(self.disk)
        data = self.post(self.disk_url("report/rerun"))
        after = _dir_manifest(self.disk)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual(data["code"], "RERUN_OK")
        self.assertTrue(data["readonly"]["identical"], data["readonly"])
        self.assertEqual(data["readonly"]["changed"], [])
        self.assertEqual(before, after, "重跑真闸不许写项目目录")

    def test_rerun_returns_structured_error_on_broken_project(self):
        (self.disk / "factscribe.toml").write_text(
            "[project]\ntitle = \"x\"\n", encoding="utf-8")
        data = self.post(self.disk_url("report/rerun"))
        self.assertFalse(data.get("ok"))
        self.assertIn(data["code"], ("CONFIG_INVALID", "RERUN_FAILED",
                                     "RERUN_TIMEOUT"))
        self.assertTrue(data.get("error"))
        self.assertIn("readonly", data)

    def test_rerun_timeout_is_structured(self):
        result = checkreport.rerun(self.disk, timeout=0.001)
        if result.get("ok"):
            self.skipTest("真闸跑得太快，没触发超时分支")
        self.assertEqual(result["code"], "RERUN_TIMEOUT")
        self.assertTrue(result.get("error"))
        self.assertIn("readonly", result)


class RerunStatusMappingTests(unittest.TestCase):
    """重跑的「成功／失败」分层：**按退出码**判，不按 status/severity 判。

    回归：CLI 的 JSON 信封走 ``_severity_of()``，它只认 0/1/3，其余退出码
    （含 5＝覆盖或信任链红）一律折成 ``severity="error"``。早先按
    status/severity 判失败，会把「真闸查出一堆红」误报成「重跑炸了」——
    明明是体检结论，却让「重跑检查」按钮显示失败。
    """

    def _rerun_with_payload(self, payload: dict, exit_code: int) -> dict:
        class _Proc:
            returncode = exit_code
            stdout = json.dumps(payload).encode("utf-8")
            stderr = b""

        with mock.patch.object(checkreport.subprocess, "run",
                               return_value=_Proc()):
            return checkreport.rerun(Path("/tmp/factscribe-rerun-nonexistent"))

    def test_integrity_exit_is_a_verdict_not_a_failure(self):
        """exit 5（覆盖/信任链红）＝真闸跑完了，是体检结论，不是重跑失败。"""
        payload = {
            "status": "error", "severity": "error", "exit": 5,
            "summary": {"red": 1, "yellow": 0, "facts": 62},
            "findings": [{"severity": "red", "code": "PDF_STALE",
                          "message": "PDF 比源文件旧"}],
        }
        result = self._rerun_with_payload(payload, 5)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["code"], "RERUN_OK")
        self.assertEqual(result["exit_code"], 5)
        self.assertEqual(result["verdict"], "red")
        self.assertEqual(result["summary"]["red"], 1)
        self.assertEqual(len(result["findings"]), 1)

    def test_red_exit_is_a_verdict_not_a_failure(self):
        payload = {"status": "red", "severity": "red", "exit": 1,
                   "summary": {"red": 5, "yellow": 7}, "findings": []}
        result = self._rerun_with_payload(payload, 1)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verdict"], "red")

    def test_yellow_exit_is_a_verdict_not_a_failure(self):
        payload = {"status": "yellow", "severity": "yellow", "exit": 3,
                   "summary": {"red": 0, "yellow": 2}, "findings": []}
        result = self._rerun_with_payload(payload, 3)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verdict"], "yellow")

    def test_clean_exit_is_ok(self):
        payload = {"status": "ok", "severity": "ok", "exit": 0,
                   "summary": {"red": 0, "yellow": 0}, "findings": []}
        result = self._rerun_with_payload(payload, 0)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verdict"], "ok")

    def test_config_error_exit_is_a_failure(self):
        """exit 2（配置错）＝工具没跑起来，这才叫重跑失败。"""
        payload = {"status": "error", "severity": "error", "exit": 2,
                   "code": "CONFIG_INVALID", "message": "缺少 project.sections",
                   "findings": []}
        result = self._rerun_with_payload(payload, 2)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["code"], "CONFIG_INVALID")
        self.assertTrue(result["error"])
        self.assertIn("readonly", result)

    def test_tool_level_exits_are_failures(self):
        for code in (2, 4, 8):
            self.assertIn(code, checkreport.GATE_FAIL_EXITS)
        for code in (0, 1, 3, 5, 6, 7, 9):
            self.assertNotIn(code, checkreport.GATE_FAIL_EXITS)


class BrokenProjectTests(_ServerCase):
    def test_report_on_broken_project_returns_structured_error(self):
        (self.disk / "factscribe.toml").write_text(
            "[project]\ntitle = \"x\"\n", encoding="utf-8")
        data = self.get(self.disk_url("report"))
        self.assertFalse(data.get("ok"))
        self.assertIn(data["code"], ("CONFIG_INVALID", "READ_FAILED"))
        self.assertTrue(data.get("error"))

    def test_unknown_disk_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/disk/nope/nope/report")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
