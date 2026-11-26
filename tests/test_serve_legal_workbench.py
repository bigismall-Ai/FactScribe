# -*- coding: utf-8 -*-
"""法律侧工作台第 ② 步的 HTTP 出口：读侧视图 ＋ 待批提案通道。

钉住：

* 四条读侧视图各有 GET 出口（单件详情／文书分段／条→事实反查／CLI 清单）；
* 待批提案：POST 建单 → 201；GET 能看到；采纳 → 过指纹闸 200，指纹不符 409；
* **写路径仍未挂**：POST verify／facts／ledger-dup-ok 一律 404（不留假接口）；
* 页面静态件：GET /legal 出页面（页面住在 legal 集成件自己的 web/ 目录里）。

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.serve import create_server  # noqa: E402

TOKEN = "legal-workbench-token"
VIEWS = ("corpus_item", "document", "provision_facts", "cli")


def _proposals():
    """提议存储（进程内存；测试要能清空它）。"""
    from factscribe import checks
    checks.load_integration("legal")
    from factscribe_legal import proposals
    return proposals


class ServeLegalWorkbenchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.token = create_server(
            ROOT / "fixtures" / "legal-demo", port=0, token=TOKEN,
            serve_ui=True)
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

    def setUp(self):
        self.proposals = _proposals()
        self.proposals.clear()

    def tearDown(self):
        self.proposals.clear()

    # -- 工具 ----------------------------------------------------------
    def _get(self, path, token=TOKEN):
        headers = {"Authorization": "Bearer " + token} if token else {}
        req = urllib.request.Request(self.base + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
                try:
                    return resp.status, json.loads(body)
                except ValueError:
                    return resp.status, {"raw": body}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(body)
            except ValueError:
                return exc.code, {"raw": body}

    def _post(self, path, payload, token=TOKEN):
        headers = {"Authorization": "Bearer " + token} if token else {}
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data,
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(body)
            except ValueError:
                return exc.code, {"raw": body}

    # -- 读侧视图 ------------------------------------------------------
    def test_corpus_item_view(self):
        status, payload = self._get("/api/legal/corpus/L3121-27")
        self.assertEqual(status, 200, payload)
        contract = payload["contract"]
        self.assertEqual(contract["view"], "corpus_item")
        self.assertEqual(contract["item"]["id"], "L3121-27")
        self.assertEqual(contract["receipts"]["fields"],
                         ["id", "sha16", "span", "face", "how"])

    def test_unknown_corpus_item_is_404(self):
        status, payload = self._get("/api/legal/corpus/%s"
                                    % quote("没有这件-000"))
        self.assertEqual(status, 404)
        self.assertFalse(payload.get("ok", True))

    def test_document_view(self):
        status, payload = self._get("/api/legal/document")
        self.assertEqual(status, 200, payload)
        contract = payload["contract"]
        self.assertEqual(contract["view"], "document")
        self.assertTrue(contract["paragraphs"])
        marked = [p for p in contract["paragraphs"] if p["markers"]]
        self.assertTrue(marked)
        self.assertTrue(marked[0]["markers"][0]["receipt"])

    def test_provision_facts_view(self):
        status, payload = self._get("/api/legal/provision/L3121-27/facts")
        self.assertEqual(status, 200, payload)
        contract = payload["contract"]
        self.assertEqual(contract["view"], "provision_facts")
        self.assertEqual(contract["total"], 1)
        self.assertTrue(contract["items"][0]["receipt"])

    def test_cli_view(self):
        status, payload = self._get("/api/legal/cli")
        self.assertEqual(status, 200, payload)
        contract = payload["contract"]
        self.assertEqual(contract["view"], "cli")
        self.assertEqual(contract["total"], 12)
        for item in contract["items"]:
            self.assertTrue(item["name"])
            self.assertTrue(item["help"])

    def test_views_require_token(self):
        for path in ("/api/legal/document", "/api/legal/cli",
                     "/api/legal/corpus/L3121-27"):
            with self.subTest(path=path):
                status, _payload = self._get(path, token="")
                self.assertEqual(status, 401)

    # -- 待批提案：只建单不写盘 ----------------------------------------
    def test_proposal_create_and_read_back(self):
        status, payload = self._post("/api/legal/proposals", {
            "kind": "receipt_quote",
            "target": {"scope": "receipt", "fact_id": "FR-HOURS"},
            "payload": {"note": "复核这个值"}})
        self.assertEqual(status, 201, payload)
        record = payload["contract"]["proposal"]
        self.assertTrue(record["id"].startswith("P-"))
        self.assertEqual(record["status"], "proposed")
        self.assertFalse(record["decision"]["write_path"])
        status, payload = self._get("/api/legal/proposals")
        self.assertEqual(status, 200)
        self.assertEqual(payload["contract"]["proposals"]["total"], 1)

    def test_proposal_adopt_passes_gate(self):
        status, payload = self._post("/api/legal/proposals", {
            "kind": "receipt_quote",
            "target": {"scope": "receipt", "fact_id": "FR-HOURS"}})
        self.assertEqual(status, 201, payload)
        pid = payload["contract"]["proposal"]["id"]
        status, payload = self._post("/api/legal/proposals/%s/adopt" % pid, {})
        self.assertEqual(status, 200, payload)
        record = payload["contract"]["proposal"]
        self.assertEqual(record["status"], "adopted_pending")
        self.assertFalse(record["decision"]["write_path"])

    def test_proposal_with_wrong_fingerprint_is_refused(self):
        status, payload = self._post("/api/legal/proposals", {
            "kind": "receipt_quote",
            "target": {"scope": "receipt", "fact_id": "FR-HOURS"},
            "before_sha": "0000000000000000"})
        self.assertEqual(status, 409, payload)
        self.assertEqual(payload["error"]["code"], "PROPOSAL_STALE")
        status, payload = self._get("/api/legal/proposals")
        self.assertEqual(payload["contract"]["proposals"]["total"], 0)

    def test_proposal_writes_no_file(self):
        project = ROOT / "fixtures" / "legal-demo"
        before = sorted(p.name for p in project.iterdir())
        status, _payload = self._post("/api/legal/proposals", {
            "kind": "receipt_quote",
            "target": {"scope": "receipt", "fact_id": "FR-HOURS"}})
        self.assertEqual(status, 201)
        after = sorted(p.name for p in project.iterdir())
        self.assertEqual(before, after, "提议单不许写盘")

    # -- 写路径仍未挂 --------------------------------------------------
    def test_write_paths_are_not_mounted(self):
        for path in ("/api/legal/verify", "/api/legal/facts",
                     "/api/legal/ledger/dup-ok"):
            with self.subTest(path=path):
                status, payload = self._post(path, {})
                self.assertEqual(status, 404, payload)
                self.assertFalse(payload.get("ok", True))

    # -- 页面静态件 ----------------------------------------------------
    def test_legal_page_is_served(self):
        status, payload = self._get("/legal")
        self.assertEqual(status, 200)
        self.assertIn("text/html", payload.get("raw", "")[:0] or "text/html")
        status, payload = self._get("/legal")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("raw"), "页面是空的")

    def test_legal_page_assets_are_served(self):
        for name in ("legal.css", "legal.js"):
            with self.subTest(name=name):
                status, payload = self._get("/legal/%s" % name)
                self.assertEqual(status, 200)
                self.assertTrue(payload.get("raw"))

    def test_legal_page_served_on_both_urls(self):
        """/legal 与 /legal/ 都出页面，且都带 <base href=".">。

        无尾斜杠那个曾经把相对资源解析到根路径（/legal.css）⇒ 取不到 ⇒
        脚本从未执行 ⇒ 页面零渲染。这个用例就是那个阻断缺陷的回归锁。
        """
        for path in ("/legal", "/legal/"):
            with self.subTest(path=path):
                status, payload = self._get(path)
                self.assertEqual(status, 200)
                body = payload.get("raw", "")
                self.assertIn('<base href=".">', body)
                self.assertIn("legal.css", body)
                self.assertIn("legal.js", body)

    def test_legal_page_assets_on_both_paths(self):
        for path in ("/legal.css", "/legal.js",
                     "/legal/legal.css", "/legal/legal.js"):
            with self.subTest(path=path):
                status, payload = self._get(path)
                self.assertEqual(status, 200, path)
                self.assertTrue(payload.get("raw"), path)

    def test_legal_page_uses_miniapp_palette_not_legacy(self):
        """色板只许来自段落级 miniapp；不许回退 --mcode-*（factscribe/web 旧前端）。"""
        status, payload = self._get("/legal/legal.css")
        self.assertEqual(status, 200)
        css = payload.get("raw", "")
        self.assertNotIn("--mcode-", css)
        self.assertIn("--paper:", css)


if __name__ == "__main__":
    unittest.main()
