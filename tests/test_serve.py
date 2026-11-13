# -*- coding: utf-8 -*-
"""`factscribe serve`：本地工作台 HTTP API 的契约测试。

钉住：
- 只绑回环；默认/指定 token，未带 token 一律 401；
- health 不需要 token；
- status / brief / audit 返回结构化 JSON；audit 的 exit 是命令行同一判定；
- 红黄不变成 HTTP 错误（传输 200，判定在 payload.exit）；
- serve 只读，不写项目。
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

from factscribe.config import ConfigError  # noqa: E402
from factscribe.serve import create_server  # noqa: E402

TOKEN = "test-token"


class ServeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.token = create_server(
            ROOT / "examples" / "minimal", port=0, token=TOKEN)
        cls.port = cls.server.server_address[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _request(self, path, method="GET", token=None):
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(self.base + path, method=method,
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
            finally:
                exc.close()
            return exc.code, json.loads(body) if body else {}

    def test_health_needs_no_token(self):
        status, data = self._request("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["service"], "workbench")

    def test_status_requires_token(self):
        status, data = self._request("/api/status")
        self.assertEqual(status, 401)
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_status_shape(self):
        status, data = self._request("/api/status", token=self.token)
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["endpoint"], "status")
        self.assertEqual(data["facts"], 3)
        self.assertEqual(data["sections"], 2)
        self.assertIn("config", data)

    def test_brief_shape(self):
        status, data = self._request("/api/brief", token=self.token)
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["endpoint"], "brief")
        self.assertEqual(len(data["sections"]), 2)
        self.assertEqual(data["facts_total"], 3)

    def test_audit_is_200_even_when_red(self):
        status, data = self._request("/api/audit", method="POST",
                                     token=self.token)
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["endpoint"], "audit")
        self.assertEqual(data["exit"], 1)  # examples/minimal 故意两红
        codes = {f["code"] for f in data["findings"]}
        self.assertIn("UNMATCHED_NUMBER", codes)
        self.assertIn("MISSING_CITE", codes)
        self.assertIn("coverage", data)

    def test_unknown_endpoint_is_404(self):
        status, data = self._request("/api/nope", token=self.token)
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "NOT_FOUND")

    def test_bad_project_is_refused_at_startup(self):
        with self.assertRaises(ConfigError):
            create_server(ROOT / "examples" / "minimal" / "nope",
                          token="x")

    def test_non_loopback_host_is_refused(self):
        with self.assertRaises(ConfigError):
            create_server(ROOT / "examples" / "minimal", host="0.0.0.0",
                          token="x")

    def test_read_only_server_refuses_writes(self):
        status, data = self._request("/api/sections", method="PUT",
                                     token=self.token)
        self.assertEqual(status, 403)
        self.assertEqual(data["error"]["code"], "READ_ONLY")
        status, data = self._request("/api/facts", method="POST",
                                     token=self.token)
        self.assertEqual(status, 403)
        self.assertEqual(data["error"]["code"], "READ_ONLY")

    def test_serve_does_not_write_project(self):
        before = {p: p.read_bytes() for p in
                  (ROOT / "examples" / "minimal").rglob("*") if p.is_file()}
        self._request("/api/status", token=self.token)
        self._request("/api/brief", token=self.token)
        self._request("/api/audit", method="POST", token=self.token)
        after = {p: p.read_bytes() for p in
                 (ROOT / "examples" / "minimal").rglob("*") if p.is_file()}
        self.assertEqual(before, after)


class WritableServeTest(unittest.TestCase):
    """--allow-write：读项目、改一节、加一条事实；越界一律拒绝。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", cls.root)
        cls.server, cls.token = create_server(
            cls.root, port=0, token=TOKEN, allow_write=True)
        cls.port = cls.server.server_address[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.tmp.cleanup()

    def _request(self, path, method="GET", token=None, body=None):
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, method=method,
                                     headers=headers, data=data)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8")
            finally:
                exc.close()
            return exc.code, json.loads(raw) if raw else {}

    def test_project_view_has_sections_facts_sources(self):
        status, data = self._request("/api/project", token=self.token)
        self.assertEqual(status, 200)
        self.assertFalse(data["read_only"])
        self.assertEqual(len(data["sections"]), 2)
        self.assertGreaterEqual(len(data["facts"]), 3)
        ids = {f["id"] for f in data["facts"]}
        self.assertTrue({"A1", "A2", "A3"} <= ids)
        self.assertTrue(data["bib"])
        self.assertTrue(all("text" in s and "file" in s for s in data["sections"]))
        self.assertTrue(all("id" in s and "text" in s for s in data["sources"]))

    def test_write_section_round_trip(self):
        rel = "sections/01-intro.tex"
        text = "\\section{Intro}\n\n新写的一句。\n"
        status, data = self._request(
            "/api/sections", method="PUT", token=self.token,
            body={"file": rel, "text": text})
        self.assertEqual(status, 200)
        self.assertEqual(data["endpoint"], "write_section")
        self.assertEqual((self.root / rel).read_text(encoding="utf-8"), text)
        # 审计读到的也是新内容
        status, project = self._request("/api/project", token=self.token)
        row = next(s for s in project["sections"] if s["file"] == rel)
        self.assertEqual(row["text"], text)

    def test_write_section_rejects_outside_closure(self):
        status, data = self._request(
            "/api/sections", method="PUT", token=self.token,
            body={"file": "../outside.tex", "text": "x"})
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "CONFIG_INVALID")

    def test_add_fact_round_trip(self):
        status, data = self._request(
            "/api/facts", method="POST", token=self.token,
            body={"id": "A9", "claim": "测试事实", "value": "42",
                  "source": "results/swb16.md", "locator": "§二"})
        self.assertEqual(status, 200)
        self.assertEqual(data["endpoint"], "add_fact")
        self.assertEqual(data["id"], "A9")
        status, project = self._request("/api/project", token=self.token)
        self.assertTrue(any(f["id"] == "A9" for f in project["facts"]))


if __name__ == "__main__":
    unittest.main()
