# -*- coding: utf-8 -*-
"""tests/test_workbench_cite_assets_samples.py —— 第 ④ 步：三样能力搬进段落级前端。

旧节级网页前端（`factscribe/web/`，第 ④ 步废弃）与旧宿主
（`integrations/minifactscribe/`）里还有价值的三样能力，搬进段落级工作台：

1. **引用增删**：清单（只读）＋ 往 bib 末尾加一条 ＋ 按 key 删一条。
2. **图片预览**：盘里的图片清单 ＋ 取一张图的字节（路径闸与旧通道同规则）。
3. **示例安装**：把内置示例论文装到工作根下面，装完就在项目列表里。

每样都走真实 HTTP（本地起一个工作台服务），不是直接调函数。
"""
from __future__ import annotations

import base64
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench.server import create_server  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"

#: 1×1 的 PNG（够当"一张图"用；真图与它走同一条读通道）。
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class PortedCapabilityBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-wb-port-"))
        self.paper = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.paper)
        # 盘里放一张图：图片预览要有东西可看。
        (self.paper / "figs").mkdir(exist_ok=True)
        (self.paper / "figs" / "a.png").write_bytes(PNG_1PX)
        self.state = self.tmp / "state"
        self.server, self.index = create_server(str(self.tmp), port=0,
                                                state_dir=str(self.state))
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.project, self.disk = self._first_disk()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _first_disk(self):
        data = self.get("/api/projects")
        project = (data.get("projects") or [])[0]
        disk = (project.get("disks") or [])[0]
        return project["id"], disk["id"]

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_bytes(self, path):
        with urllib.request.urlopen(self.base + path, timeout=30) as resp:
            return resp.read(), resp.headers.get("Content-Type", "")

    def post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, method="POST", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post_expect_error(self, path, body):
        """POST 但要失败：返回 (HTTP 状态, 机器码)。"""
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, method="POST", data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def disk_path(self, *parts):
        return "/api/disk/%s/%s/%s" % (self.project, self.disk, "/".join(parts))

    def bib_text(self):
        return (self.paper / "refs.bib").read_text(encoding="utf-8")

def _get_error(base, path):
    """GET 但要失败：返回 (HTTP 状态, 机器码)。"""
    try:
        with urllib.request.urlopen(base + path, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


class CitationTests(PortedCapabilityBase):
    """引用：清单（只读）＋ 增 ＋ 删。"""

    def test_citation_list_is_readable(self):
        data = self.get(self.disk_path("citations"))
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("total"), 2)
        keys = [row["key"] for row in data.get("entries") or []]
        self.assertIn("chen2023factscore", keys)
        self.assertIn("lewis2020rag", keys)

    def test_add_citation_appends_to_bib(self):
        result = self.post(self.disk_path("citations", "add"),
                            {"key": "smith2024demo", "title": "A Demo Paper",
                             "author": "Smith, A", "year": "2024",
                             "doi": "10.1000/demo"})
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("key"), "smith2024demo")
        text = self.bib_text()
        self.assertIn("@article{smith2024demo,", text)
        self.assertIn("10.1000/demo", text)

    def test_add_duplicate_key_is_refused(self):
        status, payload = self.post_expect_error(
            self.disk_path("citations", "add"), {"key": "chen2023factscore"})
        self.assertEqual(status, 409)
        self.assertEqual(payload.get("err_code"), "CITATION_EXISTS")

    def test_add_without_key_is_refused(self):
        status, payload = self.post_expect_error(
            self.disk_path("citations", "add"), {"key": "  "})
        self.assertEqual(status, 400)
        self.assertEqual(payload.get("err_code"), "CITATION_INVALID")

    def test_delete_citation_removes_the_entry(self):
        result = self.post(self.disk_path("citations", "delete"),
                            {"key": "lewis2020rag"})
        self.assertTrue(result.get("ok"))
        self.assertNotIn("lewis2020rag", self.bib_text())

    def test_delete_missing_key_is_refused(self):
        status, payload = self.post_expect_error(
            self.disk_path("citations", "delete"), {"key": "nosuchkey2020"})
        self.assertEqual(status, 404)
        self.assertEqual(payload.get("err_code"), "CITATION_MISSING")

    def test_list_reflects_the_new_entry(self):
        self.post(self.disk_path("citations", "add"),
                  {"key": "smith2024demo", "title": "A Demo Paper"})
        data = self.get(self.disk_path("citations"))
        keys = [row["key"] for row in data.get("entries") or []]
        self.assertIn("smith2024demo", keys)
        self.assertEqual(data.get("total"), 3)


class AssetTests(PortedCapabilityBase):
    """图片：清单 ＋ 取字节 ＋ 路径闸。"""

    def test_asset_list_finds_the_image(self):
        data = self.get(self.disk_path("assets"))
        self.assertTrue(data.get("ok"))
        paths = [row["path"] for row in data.get("assets") or []]
        self.assertIn("figs/a.png", paths)

    def test_asset_bytes_are_served(self):
        body, ctype = self.get_bytes(self.disk_path("asset")
                                      + "?path=figs/a.png")
        self.assertEqual(body, PNG_1PX)
        self.assertEqual(ctype, "image/png")

    def test_asset_path_escape_is_refused(self):
        for bad in ("../outside.png", "/etc/passwd", "figs/../../outside.png"):
            path = self.disk_path("asset") + "?path=" + urllib.parse.quote(bad)
            status, payload = _get_error(self.base, path)
            self.assertEqual(status, 400, bad)
            self.assertEqual(payload.get("err_code"), "PATH_ESCAPE", bad)

    def test_asset_symlink_is_refused(self):
        outside = self.tmp / "outside.png"
        outside.write_bytes(PNG_1PX)
        link = self.paper / "figs" / "link.png"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("本机不支持软链")
        status, payload = _get_error(self.base,
                                     self.disk_path("asset") + "?path=figs/link.png")
        self.assertEqual(status, 400)
        self.assertEqual(payload.get("err_code"), "PATH_ESCAPE")

    def test_missing_asset_is_404(self):
        status, payload = _get_error(
            self.base, self.disk_path("asset") + "?path=figs/nope.png")
        self.assertEqual(status, 404)
        self.assertEqual(payload.get("err_code"), "ASSET_NOT_FOUND")

    def test_non_image_is_refused(self):
        (self.paper / "notes.txt").write_text("x", encoding="utf-8")
        status, payload = _get_error(
            self.base, self.disk_path("asset") + "?path=notes.txt")
        self.assertEqual(status, 400)
        self.assertEqual(payload.get("err_code"), "ASSET_INVALID")


class SampleInstallTests(PortedCapabilityBase):
    """示例安装：装到工作根下面；已装的不给 reset 就不覆盖。"""

    def test_sample_installs_into_the_root(self):
        result = self.post("/api/samples/guide", {"reset": False})
        self.assertTrue(result.get("ok"))
        target = Path(result.get("path") or "")
        self.assertTrue(target.is_dir())
        self.assertTrue((target / "factscribe.toml").is_file())
        self.assertTrue((target / "sections").is_dir())

    def test_sample_is_not_overwritten_without_reset(self):
        target = self.tmp / "guide-sample"
        target.mkdir()
        (target / "marker.txt").write_text("mine", encoding="utf-8")
        result = self.post("/api/samples/guide", {"reset": False})
        self.assertFalse(result.get("created"))
        self.assertTrue((target / "marker.txt").is_file())

    def test_sample_reset_reinstalls(self):
        target = self.tmp / "guide-sample"
        target.mkdir()
        (target / "marker.txt").write_text("mine", encoding="utf-8")
        result = self.post("/api/samples/guide", {"reset": True})
        self.assertTrue(result.get("created"))
        self.assertFalse((target / "marker.txt").exists())
        self.assertTrue((target / "factscribe.toml").is_file())

    def test_installed_sample_shows_up_in_the_project_list(self):
        self.post("/api/samples/guide", {"reset": False})
        data = self.get("/api/projects?refresh=1")
        names = [p.get("name") or "" for p in data.get("projects") or []]
        self.assertIn("factscribe 最小验收样例", names)


class FrontendWiringTests(unittest.TestCase):
    """前端接线静态断言：三样能力在段落级前端里都在（中英双语各一份）。"""

    @classmethod
    def setUpClass(cls):
        static = ROOT / "factscribe" / "workbench" / "static"
        cls.html = (static / "index.html").read_text(encoding="utf-8")
        cls.js = (static / "app.js").read_text(encoding="utf-8")

    def test_panels_and_modals_exist(self):
        for marker in ('id="secCite"', 'id="secAssets"', 'id="modalCite"',
                       'id="modalAsset"', 'id="goSample"',
                       'id="citeList"', 'id="assetGrid"'):
            self.assertIn(marker, self.html, marker)

    def test_endpoints_are_called(self):
        for marker in ("/citations", "/citations/add", "/citations/delete",
                       "/assets", "/asset", "/api/samples/guide"):
            self.assertIn(marker, self.js, marker)

    def test_both_languages_have_the_labels(self):
        for key in ("'np.cite'", "'np.assets'", "'cite.addT'", "'cite.delT'",
                    "'asset.empty'", "'tb.sample'"):
            # 至少两处＝中英两个词典各一份（多的那几处是代码里的引用点）。
            self.assertGreaterEqual(self.js.count(key), 2, key)


if __name__ == "__main__":
    unittest.main()
