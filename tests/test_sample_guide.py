# -*- coding: utf-8 -*-
"""内置示例论文：`POST /api/samples/guide`。

要点：
  * 目标目录固定在 `~/.factscribe/samples/guide`（测试里换 HOME）；
  * 不需要 `--allow-write`——它只写自己的示例目录，用户的论文不受影响；
  * 已存在且不 reset → 原样返回，不覆盖用户改过的东西；
  * reset=true → 先删再复制，文件回到出厂状态；
  * 没 token → 401。
"""
from __future__ import annotations

import json
import os
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
from factscribe.workbench import audit_data  # noqa: E402

TOKEN = "guide-token"


class SampleGuideTest(unittest.TestCase):
    """装一份示例、改一改、再重置——都在临时 HOME 里做。"""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="factscribe-guide-")
        cls.saved_home = os.environ.get("HOME")
        os.environ["HOME"] = cls.home
        # 只读服务：示例接口不需要 --allow-write，这一条要验住。
        cls.server, cls.token = create_server(None, port=0, token=TOKEN,
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
        if cls.saved_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = cls.saved_home
        shutil.rmtree(cls.home, ignore_errors=True)

    # ------------------------------------------------------------ 帮手

    def setUp(self):
        # 每个用例都从「机器上还没有示例」开始：用例之间互不依赖。
        if self.target.exists():
            shutil.rmtree(self.target)

    def _post(self, body=None, token=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + "/api/samples/guide",
                                     method="POST", data=data)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            exc.close()
            return exc.code, json.loads(raw.decode("utf-8"))

    @property
    def target(self):
        return Path(self.home) / ".factscribe" / "samples" / "guide"

    # ------------------------------------------------------------ 用例

    def test_without_token_is_401(self):
        status, data = self._post({}, token=None)
        self.assertEqual(status, 401)
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")
        self.assertFalse(self.target.exists())

    def test_first_call_installs_the_sample(self):
        status, data = self._post({}, token=TOKEN)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])
        self.assertTrue(data["created"])
        self.assertFalse(data["reset"])
        self.assertEqual(data["path"], str(self.target))
        self.assertTrue((self.target / "paperkit.toml").is_file())
        self.assertTrue((self.target / "sections").is_dir())
        self.assertTrue((self.target / "sections" / "01-intro.tex").is_file())
        self.assertTrue((self.target / "sections" / "02-results.tex").is_file())
        self.assertTrue((self.target / "facts" / "01-core.toml").is_file())
        self.assertTrue((self.target / "results" / "swb16.md").is_file())
        self.assertTrue((self.target / "results" / "MANIFEST.toml").is_file())
        self.assertTrue((self.target / "refs.bib").is_file())
        self.assertTrue((self.target / "main.tex").is_file())
        self.assertTrue((self.target / "README.md").is_file())

    def test_sample_does_not_ship_pdf_or_audit_dir(self):
        status, _ = self._post({}, token=TOKEN)
        self.assertEqual(status, 200)
        self.assertFalse((self.target / "main.pdf").exists())
        self.assertFalse((self.target / "audit").exists())

    def test_second_call_keeps_local_changes(self):
        status, _ = self._post({}, token=TOKEN)
        self.assertEqual(status, 200)
        readme = self.target / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n改动\n",
                          encoding="utf-8")
        status, data = self._post({}, token=TOKEN)
        self.assertEqual(status, 200, data)
        self.assertFalse(data["created"])
        self.assertFalse(data["reset"])
        self.assertIn("改动", readme.read_text(encoding="utf-8"))

    def test_reset_restores_the_sample(self):
        status, _ = self._post({}, token=TOKEN)
        self.assertEqual(status, 200)
        readme = self.target / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n改动\n",
                          encoding="utf-8")
        status, data = self._post({"reset": True}, token=TOKEN)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["created"])
        self.assertTrue(data["reset"])
        self.assertNotIn("改动", readme.read_text(encoding="utf-8"))
        # 恢复的是整份，不是只补一个文件。
        self.assertTrue((self.target / "sections" / "01-intro.tex").is_file())

    def test_sample_is_a_project_with_the_two_planted_problems(self):
        status, _ = self._post({}, token=TOKEN)
        self.assertEqual(status, 200)
        report = audit_data(self.target)
        self.assertEqual(report["exit"], 1)
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("UNMATCHED_NUMBER", codes)
        self.assertIn("MISSING_CITE", codes)
        red = [f for f in report["findings"] if f["severity"] == "red"]
        self.assertEqual(len(red), 2, red)
        tokens = " ".join(str(f.get("token") or "") for f in red)
        self.assertIn("47.3", tokens)
        self.assertIn("ghost2024", tokens)

    def test_endpoint_needs_no_project(self):
        """没选论文项目也能装示例（项目管理模式下同样可用）。"""
        self.assertIsNone(self.server.project)
        status, data = self._post({"reset": True}, token=TOKEN)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
