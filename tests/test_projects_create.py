# -*- coding: utf-8 -*-
"""新建论文项目：`POST /api/projects/create`。

要点：
  * 要 token，也要 `--allow-write`（它会写盘）；
  * 父目录必须存在且是目录；文件夹名只允许 `[A-Za-z0-9._-]`，不许 `.` / `..`；
  * 目标目录必须不存在或是空目录（非空 → 409 `PROJECT_DIR_NOT_EMPTY`）；
  * 建完只生成骨架，不编译；
  * `GET /api/projects` 每项带 `description` 与 `guide`（示例论文被标出来）。

一切都在临时 HOME 与临时目录里做，不碰用户机器上的任何东西。
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

from factscribe.config import load_config  # noqa: E402
from factscribe.serve import create_server  # noqa: E402

TOKEN = "create-token"


class ProjectsCreateTest(unittest.TestCase):
    """建项目、撞错、只读拦截、列表字段——都在临时 HOME 里做。"""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="factscribe-create-")
        cls.saved_home = os.environ.get("HOME")
        os.environ["HOME"] = cls.home
        cls.server, cls.token = create_server(None, port=0, token=TOKEN,
                                              allow_write=True)
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

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="factscribe-work-"))
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

    # ------------------------------------------------------------ 帮手

    def _post(self, path, body=None, token=TOKEN):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, method="POST", data=data)
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

    def _get(self, path, token=TOKEN):
        req = urllib.request.Request(self.base + path)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            exc.close()
            return exc.code, json.loads(raw.decode("utf-8"))

    def _create(self, **overrides):
        body = {
            "title": "测试论文",
            "parent": str(self.work),
            "slug": "paper-test",
            "authors": ["甲"],
            "description": "一句话简介：送达证据，而非规则。",
            "lang": "zh",
            "sections": "sections/*.tex",
            "facts": "facts/*.toml",
            "bib": "refs.bib",
            "root_tex": "main.tex",
            "build": "tectonic -X compile main.tex",
            "source_root": str(self.work),
            "output": "main.pdf",
        }
        body.update(overrides)
        return self._post("/api/projects/create", body)

    # ------------------------------------------------------------ 用例

    def test_create_success(self):
        status, data = self._create()
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])
        self.assertTrue(data["created"])
        project = data["project"]
        root = Path(project["path"])
        self.assertEqual(root, (self.work / "paper-test").resolve())
        self.assertEqual(project["name"], "测试论文")
        self.assertEqual(project["description"], "一句话简介：送达证据，而非规则。")

        # 骨架真的落了盘
        self.assertTrue((root / "paperkit.toml").is_file())
        self.assertTrue((root / "main.tex").is_file())
        self.assertTrue((root / "sections" / "01-intro.tex").is_file())
        self.assertTrue((root / "facts").is_dir())
        self.assertTrue((root / "refs.bib").is_file())
        # 只生成骨架，不编译
        self.assertFalse((root / "main.pdf").exists())

    def test_paperkit_toml_has_description_build_source_root(self):
        status, data = self._create()
        self.assertEqual(status, 200, data)
        root = Path(data["project"]["path"])
        text = (root / "paperkit.toml").read_text(encoding="utf-8")
        self.assertIn('description = "一句话简介：送达证据，而非规则。"', text)
        self.assertIn('build = "tectonic -X compile main.tex"', text)
        self.assertIn('source_root = "%s"' % self.work, text)
        self.assertIn('root_tex = "main.tex"', text)
        self.assertIn('output = "main.pdf"', text)
        # 骨架里原有的键要保住
        self.assertIn('title = "测试论文"', text)
        self.assertIn("sections = ", text)
        self.assertIn("facts = ", text)

    def test_new_project_config_loads_without_warnings(self):
        status, data = self._create()
        self.assertEqual(status, 200, data)
        cfg = load_config(Path(data["project"]["path"]))
        self.assertEqual(cfg.description, "一句话简介：送达证据，而非规则。")
        self.assertEqual(cfg.title, "测试论文")
        self.assertEqual(cfg.authors, ["甲"])
        self.assertEqual(cfg.build, "tectonic -X compile main.tex")
        self.assertEqual(cfg.output, "main.pdf")
        self.assertFalse(cfg.is_v3, "新建的项目仍是 v1 形态")
        unknown = [w["field"] for w in cfg.warnings
                   if w["code"] == "CONFIG_UNKNOWN_FIELD"]
        self.assertEqual(unknown, [], "自己写的字段不该被当成未知字段")

    def test_registry_marks_the_new_project_as_current(self):
        status, data = self._create()
        self.assertEqual(status, 200, data)
        root = str((self.work / "paper-test").resolve())
        registry = json.loads((Path(self.home) / ".factscribe" / "projects.json")
                               .read_text(encoding="utf-8"))
        self.assertEqual(registry["lastPath"], root)
        self.assertEqual(registry["projects"][0]["path"], root)
        self.assertEqual(registry["projects"][0]["name"], "测试论文")
        # 服务端的当前项目也切过去了
        self.assertEqual(str(self.server.project), root)

    def test_non_empty_directory_is_409(self):
        target = self.work / "paper-busy"
        target.mkdir(parents=True)
        (target / "已有东西.txt").write_text("x", encoding="utf-8")
        status, data = self._create(slug="paper-busy")
        self.assertEqual(status, 409, data)
        self.assertEqual(data["error"]["code"], "PROJECT_DIR_NOT_EMPTY")
        self.assertFalse(data["ok"])

    def test_empty_directory_is_allowed(self):
        (self.work / "paper-empty").mkdir(parents=True)
        status, data = self._create(slug="paper-empty")
        self.assertEqual(status, 200, data)
        self.assertTrue((self.work / "paper-empty" / "paperkit.toml").is_file())

    def test_bad_slug_is_400(self):
        for slug in ["bad/name", "..", ".", "有中文", "a b"]:
            status, data = self._create(slug=slug)
            self.assertEqual(status, 400, (slug, data))
            self.assertEqual(data["error"]["code"], "PROJECT_SLUG_INVALID")

    def test_missing_parent_is_400(self):
        status, data = self._create(parent=str(self.work / "不存在"))
        self.assertEqual(status, 400, data)
        self.assertEqual(data["error"]["code"], "PROJECT_PARENT_MISSING")

    def test_parent_must_be_a_directory(self):
        plain = self.work / "plain.txt"
        plain.write_text("x", encoding="utf-8")
        status, data = self._create(parent=str(plain))
        self.assertEqual(status, 400, data)
        self.assertEqual(data["error"]["code"], "PROJECT_PARENT_INVALID")

    def test_without_token_is_401(self):
        status, data = self._post("/api/projects/create", {
            "title": "没带 token", "parent": str(self.work), "slug": "paper-noauth",
        }, token=None)
        self.assertEqual(status, 401)
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")
        self.assertFalse((self.work / "paper-noauth").exists())

    def test_read_only_server_is_403(self):
        server, token = create_server(None, port=0, token="ro-token")
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        body = {"title": "只读", "parent": str(self.work), "slug": "paper-ro"}
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/projects/create" % port,
            method="POST", data=json.dumps(body).encode("utf-8"))
        req.add_header("Authorization", "Bearer ro-token")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status, data = resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            exc.close()
            status, data = exc.code, json.loads(raw.decode("utf-8"))
        self.assertEqual(status, 403, data)
        self.assertEqual(data["error"]["code"], "READ_ONLY")
        self.assertFalse((self.work / "paper-ro").exists())

    def test_list_carries_description_and_guide(self):
        status, data = self._create(slug="paper-listed")
        self.assertEqual(status, 200, data)
        status, listing = self._get("/api/projects")
        self.assertEqual(status, 200, listing)
        rows = {row["path"]: row for row in listing["projects"]}
        target = str((self.work / "paper-listed").resolve())
        self.assertIn(target, rows)
        self.assertEqual(rows[target]["description"],
                         "一句话简介：送达证据，而非规则。")
        self.assertFalse(rows[target]["guide"])

    def test_list_marks_the_guide_sample(self):
        """内置示例论文（~/.factscribe/samples/guide）被标成 guide。"""
        guide = Path(self.home) / ".factscribe" / "samples" / "guide"
        guide.mkdir(parents=True)
        shutil.copytree(ROOT / "factscribe" / "samples" / "guide",
                        guide, dirs_exist_ok=True)
        # 直接登记进册子（登记册不挑项目，只登记）
        registry_file = Path(self.home) / ".factscribe" / "projects.json"
        registry = {"version": 1, "projects": [
            {"path": str(guide.resolve()), "name": "示例论文",
             "lastOpenedAt": "2026-01-01T00:00:00+00:00"}],
            "lastPath": "", "python": "", "pythonpath": ""}
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        registry_file.write_text(json.dumps(registry), encoding="utf-8")
        status, listing = self._get("/api/projects")
        self.assertEqual(status, 200, listing)
        rows = {row["path"]: row for row in listing["projects"]}
        self.assertTrue(rows[str(guide.resolve())]["guide"])
        self.assertFalse(rows[str(guide.resolve())]["description"])

    def test_list_keeps_most_recent_first(self):
        self._create(slug="paper-first")
        self._create(slug="paper-second")
        status, listing = self._get("/api/projects")
        self.assertEqual(status, 200, listing)
        paths = [row["path"] for row in listing["projects"]]
        self.assertEqual(paths[0], str((self.work / "paper-second").resolve()))


if __name__ == "__main__":
    unittest.main()
