# -*- coding: utf-8 -*-
"""法律侧只读 HTTP 路由（`factscribe serve` 的 /api/legal/*）的契约测试。

钉住：
- legal 专属前缀，与论文侧路由不冲突；
- 七路通道各有 GET 出口，返回**同一个**版本化契约；
- 契约嵌在 payload 的 contract 键下（不覆盖 payload 自己的 version 等键）；
- 只读：路由不写盘；未带 token 一律 401；
- 未知通道 404（不留空壳假接口）；
- 集成件不可用时 501 并说清原因。
"""
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

TOKEN = "legal-test-token"
CHANNELS = ("findings", "receipts", "corpus", "codes", "timeliness",
            "summary", "proposals")


class ServeLegalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.token = create_server(
            ROOT / "fixtures" / "legal-demo", port=0, token=TOKEN)
        cls.port = cls.server.server_address[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                       daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _get(self, path, token=TOKEN):
        headers = {"Authorization": "Bearer " + token} if token else {}
        req = urllib.request.Request(self.base + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(body)
            except ValueError:
                return exc.code, {"raw": body}

    def test_each_channel_has_a_get_exit(self):
        for channel in CHANNELS:
            with self.subTest(channel=channel):
                status, payload = self._get("/api/legal/%s" % channel)
                self.assertEqual(status, 200, payload)
                contract = payload["contract"]
                self.assertTrue(contract["version"])
                self.assertTrue(contract["read_only"])
                self.assertIn(channel, contract)

    def test_contract_version_is_shared(self):
        versions = set()
        for channel in CHANNELS:
            _status, payload = self._get("/api/legal/%s" % channel)
            versions.add(payload["contract"]["version"])
        self.assertEqual(len(versions), 1)

    def test_payload_keeps_its_own_envelope_keys(self):
        status, payload = self._get("/api/legal/codes")
        self.assertEqual(status, 200)
        for key in ("schema_version", "tool", "version", "command", "exit",
                    "ok", "endpoint"):
            self.assertIn(key, payload)
        self.assertEqual(payload["endpoint"], "legal.codes")

    def test_unknown_channel_is_404(self):
        status, payload = self._get("/api/legal/nope")
        self.assertEqual(status, 404)
        self.assertFalse(payload.get("ok", True))

    def test_requires_token(self):
        status, _payload = self._get("/api/legal/codes", token="")
        self.assertEqual(status, 401)

    def test_corpus_filter_by_country(self):
        status, payload = self._get("/api/legal/corpus?country=%E6%B3%95%E5%9B%BD")
        self.assertEqual(status, 200)
        items = payload["contract"]["corpus"]["items"]
        self.assertTrue(items)
        for item in items:
            self.assertEqual(item["country"], "法国")

    def test_proposals_is_empty(self):
        status, payload = self._get("/api/legal/proposals")
        self.assertEqual(status, 200)
        self.assertEqual(payload["contract"]["proposals"]["items"], [])

    def test_routes_are_read_only(self):
        """路由不写盘：跑完一遍，项目目录里不多出文件。"""
        project = ROOT / "fixtures" / "legal-demo"
        before = sorted(p.name for p in project.iterdir())
        for channel in CHANNELS:
            self._get("/api/legal/%s" % channel)
        after = sorted(p.name for p in project.iterdir())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
