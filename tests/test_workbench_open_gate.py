# -*- coding: utf-8 -*-
"""tests/test_workbench_open_gate.py —— 条目 32：开目录的 dry-run 闸。

`actions.open_project_dir` 会调 macOS 的 `open`（真弹访达）。闸门：

* 环境变量 ``FACTSCRIBE_NO_OPEN`` 非空 → **不执行** `open`，
  只返回 ``{ok: True, opened: False, path: ...}``；
* 真实使用不受影响（那个变量只有测试与端到端脚本会设）；
* 仓里所有测试都设它（``tests/conftest.py``），跑测试不弹访达。

另外守住「零 open 调用」这条：仓里 `subprocess.run(["open", ...])`
只有 `actions.open_project_dir` 一处，且被闸门挡在前面；
服务器启动路径（`create_server`）根本不碰它。
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench import actions                 # noqa: E402
from factscribe.workbench.server import create_server   # noqa: E402


def _make_disk(root: Path, name: str = "paper") -> Path:
    disk = root / name
    (disk / "sections").mkdir(parents=True)
    (disk / "facts").mkdir(parents=True)
    (disk / "factscribe.toml").write_text(
        '[project]\ntitle = "闸门测试"\nsections = "sections/*.tex"\n'
        'facts = "facts/*.toml"\nbib = "refs.bib"\n', encoding="utf-8")
    (disk / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\input{sections/01-intro}\n\\end{document}\n", encoding="utf-8")
    (disk / "sections" / "01-intro.tex").write_text(
        "\\section{Intro}\n\nBody.\n", encoding="utf-8")
    return disk


class OpenDirGateTests(unittest.TestCase):
    """闸门本身。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get(actions.NO_OPEN_ENV)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(actions.NO_OPEN_ENV, None)
        else:
            os.environ[actions.NO_OPEN_ENV] = self._saved

    def test_gate_env_name(self):
        self.assertEqual(actions.NO_OPEN_ENV, "FACTSCRIBE_NO_OPEN")

    def test_non_empty_env_suppresses_open(self):
        os.environ[actions.NO_OPEN_ENV] = "1"
        result = actions.open_project_dir(self.disk)
        self.assertTrue(result["ok"])
        self.assertFalse(result["opened"])
        self.assertTrue(result["path"])
        self.assertTrue(result.get("dry_run"))

    def test_empty_env_is_treated_as_off(self):
        os.environ[actions.NO_OPEN_ENV] = "   "
        self.assertFalse(actions._no_open())

    def test_missing_env_is_treated_as_off(self):
        os.environ.pop(actions.NO_OPEN_ENV, None)
        self.assertFalse(actions._no_open())

    def test_conftest_sets_the_gate_for_the_whole_suite(self):
        """仓里所有测试都在闸门下跑（conftest 统一设）。"""
        self.assertEqual(os.environ.get(actions.NO_OPEN_ENV), "1")


class OpenDirEndpointTests(unittest.TestCase):
    """HTTP 一层：闸门开着时端点不弹访达。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _make_disk(self.root)
        self.server, self.index = create_server(self.root, port=0, ttl=0.0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        self._saved = os.environ.get(actions.NO_OPEN_ENV)

    def tearDown(self):
        os.environ[actions.NO_OPEN_ENV] = self._saved or "1"
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def test_endpoint_reports_opened_false_under_the_gate(self):
        import json
        import urllib.request

        os.environ[actions.NO_OPEN_ENV] = "1"
        request = urllib.request.Request(
            self.base + "/api/disk/paper/paper/action",
            data=json.dumps({"action": "open_dir"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=30) as res:
            data = json.loads(res.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertFalse(data["opened"])
        self.assertTrue(data["path"])


class NoOpenCallSiteTests(unittest.TestCase):
    """「零 open 调用」的静态防线。"""

    def test_only_one_open_call_site_in_the_repo(self):
        hits = []
        for path in (ROOT / "factscribe").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if '["open"' in text:
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, ["factscribe/workbench/actions.py"])

    def test_server_startup_path_never_opens(self):
        """建服务本身不碰 open_project_dir（只有动作端点会调）。"""
        text = (ROOT / "factscribe" / "workbench" / "server.py").read_text(
            encoding="utf-8")
        create = text[text.index("def create_server"):]
        self.assertNotIn("open_project_dir", create)

    def test_gate_is_checked_before_the_open_call(self):
        text = (ROOT / "factscribe" / "workbench" / "actions.py").read_text(
            encoding="utf-8")
        self.assertLess(text.index("if _no_open():"),
                        text.index('subprocess.run(["open"'))


if __name__ == "__main__":
    unittest.main()
