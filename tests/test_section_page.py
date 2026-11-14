# -*- coding: utf-8 -*-
"""GET /api/section-page：把当前节映射到编译后 PDF 的页码。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.serve import create_server  # noqa: E402

TOKEN = "section-token"


class SectionPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="section-page-")
        cls.project = Path(cls.tmp) / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", cls.project)
        (cls.project / "main.pdf").write_bytes(b"%PDF-1.4\n")
        cls.server, cls.token = create_server(cls.project, port=0, token=TOKEN)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _get(self, path: str):
        req = urllib.request.Request(self.base + path)
        req.add_header("Authorization", "Bearer " + TOKEN)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            exc.close()
            return exc.code, json.loads(body)

    def test_returns_page_from_locate(self):
        with mock.patch("factscribe.serve.locate",
                        return_value={"page": 3, "pages": 9, "found": True,
                                      "title": "Introduction"}):
            status, data = self._get(
                "/api/section-page?file=" + urllib.parse.quote("sections/01-intro.tex"))
        self.assertEqual(200, status, data)
        self.assertEqual(3, data["page"])
        self.assertEqual(9, data["pages"])
        self.assertEqual("sections/01-intro.tex", data["file"])

    def test_rejects_path_escape(self):
        status, data = self._get("/api/section-page?file=" + urllib.parse.quote("../x.tex"))
        self.assertEqual(400, status)
        self.assertEqual("SECTION_INVALID", data["error"]["code"])

    def test_missing_pdf(self):
        pdf = Path(self.tmp) / "paper" / "main.pdf"
        pdf.unlink()
        try:
            status, data = self._get(
                "/api/section-page?file=" + urllib.parse.quote("sections/01-intro.tex"))
            self.assertEqual(400, status)
            self.assertEqual("PDF_MISSING", data["error"]["code"])
        finally:
            pdf.write_bytes(b"%PDF-1.4\n")


if __name__ == "__main__":
    unittest.main()
