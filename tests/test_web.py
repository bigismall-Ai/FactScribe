# -*- coding: utf-8 -*-
"""`serve --ui` / `factscribe web`：静态页面与 API 同端口。"""
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

    def test_build_is_disabled_by_default(self):
        status, body = self._get("/api/build", token=TOKEN)
        self.assertEqual(status, 404)  # GET 没有 build；POST 见下
        req = urllib.request.Request(self.base + "/api/build", method="POST")
        req.add_header("Authorization", "Bearer " + TOKEN)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
        self.assertEqual(status, 403)

    def test_fact_form_is_present(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn('id="fact-form"', body)
        self.assertIn('id="btn-add-fact"', body)
        status, js = self._get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn("/api/facts", js)
        self.assertIn("manifest_line", js)

    def test_api_works_with_token(self):
        status, body = self._get("/api/project", token=TOKEN)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["sections"]), 2)


class WebBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", cls.root)
        conf = cls.root / "paperkit.toml"
        text = conf.read_text(encoding="utf-8")
        text = text.replace('build = "tectonic -X compile main.tex"',
                            'build = "printf \'%%PDF-1.4\' > main.pdf"')
        conf.write_text(text, encoding="utf-8")
        cls.server, cls.token = create_server(
            cls.root, port=0, token=TOKEN, allow_build=True)
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

    def test_build_and_download_pdf(self):
        req = urllib.request.Request(self.base + "/api/build", method="POST")
        req.add_header("Authorization", "Bearer " + TOKEN)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["exit"], 0)
        self.assertGreater(data["pdf_bytes"], 0)

        req = urllib.request.Request(self.base + "/api/pdf")
        req.add_header("Authorization", "Bearer " + TOKEN)
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read()
        self.assertTrue(body.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
