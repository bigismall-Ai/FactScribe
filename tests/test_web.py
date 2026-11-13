# -*- coding: utf-8 -*-
"""`serve --ui` / `factscribe web`：静态页面与 API 同端口。"""
from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.serve import create_server  # noqa: E402

TOKEN = "web-token"


class WebUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.token = create_server(
            ROOT / "examples" / "minimal", port=0, token=TOKEN,
            serve_ui=True)
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

    def _get(self, path, token=None):
        req = urllib.request.Request(self.base + path)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
            finally:
                exc.close()
            return exc.code, body

    def test_index_is_served_without_token(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("FactScribe Workbench", body)

    def test_static_assets(self):
        for path, needle in (("/app.js", "api('/api/project')"),
                             ("/app.css", ".layout")):
            status, body = self._get(path)
            self.assertEqual(status, 200, path)
            self.assertIn(needle, body)

    def test_api_still_requires_token(self):
        status, body = self._get("/api/project")
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"]["code"], "UNAUTHORIZED")

    def test_api_works_with_token(self):
        status, body = self._get("/api/project", token=TOKEN)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["sections"]), 2)


if __name__ == "__main__":
    unittest.main()
