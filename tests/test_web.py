# -*- coding: utf-8 -*-
"""`serve --ui` / `factscribe web`：静态页面与 API 同端口。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
import os
import urllib.error
import urllib.parse
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
        self.assertIn("FactScribe", body)
        self.assertIn("/app.css", body)

    def test_static_assets(self):
        for path, needle in (("/app.js", "wb('/project')"),
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
        self.assertIn('id="wb-fact-form"', body)
        self.assertIn('id="btn-wb-add-fact"', body)
        status, js = self._get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn("wb('/facts')", js)
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


class SectionCrudTest(unittest.TestCase):
    """章节增删改：/api/sections/create|rename|delete。

    每个用例都拿一份临时项目副本，跑完即扔——不许碰到仓库里的样例。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", cls.root)
        cls.server, cls.token = create_server(
            cls.root, port=0, token=TOKEN, allow_write=True)
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
        cls.tmp.cleanup()

    def _call(self, path, body=None, method="POST", token=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, method=method, data=data)
        req.add_header("Authorization", "Bearer " + (token or TOKEN))
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            exc.close()
            return exc.code, json.loads(raw)

    def _create(self, name, text=None):
        body = {"file": name}
        if text is not None:
            body["text"] = text
        return self._call("/api/sections/create", body)

    def _write(self, name, text):
        """直接落盘（用来造「谁在引用它」的现场）。"""
        (self.root / name).write_text(text, encoding="utf-8")

    # ------------------------------------------------------------ 新建

    def test_create_writes_default_body(self):
        status, data = self._create("sections/99-new.tex")
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])
        self.assertEqual(data["file"], "sections/99-new.tex")
        target = self.root / "sections" / "99-new.tex"
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_text(encoding="utf-8"),
                         "\\section{新章节}\n")

    def test_create_accepts_explicit_text(self):
        status, data = self._create("sections/98-body.tex", "% hi\n")
        self.assertEqual(status, 200, data)
        self.assertEqual((self.root / "sections" / "98-body.tex")
                         .read_text(encoding="utf-8"), "% hi\n")

    def test_create_rejects_existing_file(self):
        status, data = self._create("sections/01-intro.tex")
        self.assertEqual(status, 409)
        self.assertEqual(data["error"]["code"], "SECTION_EXISTS")

    def test_create_rejects_escape_and_absolute_path(self):
        for name in ("../outside.tex", "sections/../../outside.tex",
                     "/tmp/outside.tex"):
            status, data = self._create(name)
            self.assertEqual(status, 400, name)
            self.assertEqual(data["error"]["code"], "PATH_ESCAPE", name)

    def test_create_rejects_non_tex(self):
        status, data = self._create("sections/notes.md")
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "SECTION_INVALID")

    def test_create_rejects_missing_parent_dir(self):
        status, data = self._create("nowhere/01.tex")
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "SECTION_PARENT_MISSING")
        self.assertFalse((self.root / "nowhere").exists())

    def test_create_rejects_symlink(self):
        link = self.root / "sections" / "linked.tex"
        link.symlink_to(self.root / "sections" / "01-intro.tex")
        try:
            status, data = self._create("sections/linked.tex")
            self.assertEqual(status, 400)
            self.assertEqual(data["error"]["code"], "PATH_ESCAPE")
        finally:
            link.unlink()

    # ------------------------------------------------------------ 改名

    def test_rename_moves_file_and_keeps_references(self):
        self._create("sections/99-a.tex", "% a\n")
        status, data = self._call("/api/sections/rename",
                                  {"from": "sections/99-a.tex",
                                   "to": "sections/99-b.tex"})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["file"], "sections/99-b.tex")
        self.assertTrue((self.root / "sections" / "99-b.tex").is_file())
        self.assertFalse((self.root / "sections" / "99-a.tex").exists())
        # 只改名：正文里的引用一个字都不动，并且要把这件事说出来
        self.assertIn("引用", data["note"])
        main_text = (self.root / "main.tex").read_text(encoding="utf-8")
        self.assertIn("\\input{sections/01-intro}", main_text)

    def test_rename_rejects_existing_target(self):
        self._create("sections/99-from.tex", "% from\n")
        self._create("sections/99-to.tex", "% to\n")
        status, data = self._call("/api/sections/rename",
                                  {"from": "sections/99-from.tex",
                                   "to": "sections/99-to.tex"})
        self.assertEqual(status, 409)
        self.assertEqual(data["error"]["code"], "SECTION_EXISTS")
        self.assertTrue((self.root / "sections" / "99-from.tex").is_file())

    def test_rename_rejects_missing_source(self):
        status, data = self._call("/api/sections/rename",
                                  {"from": "sections/does-not-exist.tex",
                                   "to": "sections/whatever.tex"})
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "SECTION_MISSING")

    # ------------------------------------------------------------ 删除

    def test_delete_referenced_section_is_blocked(self):
        self._create("sections/99-ref.tex", "% ref\n")
        self._write("sections/99-holder.tex",
                    "\\input{sections/99-ref}\n")
        status, data = self._call("/api/sections/delete",
                                  {"file": "sections/99-ref.tex"})
        self.assertEqual(status, 409, data)
        self.assertEqual(data["error"]["code"], "SECTION_REFERENCED")
        refs = data["error"]["references"]
        self.assertTrue(refs)
        self.assertTrue(any(r["file"] == "sections/99-holder.tex"
                            for r in refs), refs)
        self.assertTrue((self.root / "sections" / "99-ref.tex").is_file())

    def test_delete_force_removes_referenced_section(self):
        self._create("sections/99-force.tex", "% force\n")
        self._write("sections/99-holder2.tex",
                    "\\input{sections/99-force}\n")
        status, data = self._call("/api/sections/delete",
                                  {"file": "sections/99-force.tex",
                                   "force": True})
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])
        self.assertFalse((self.root / "sections" / "99-force.tex").exists())

    def test_delete_unreferenced_section(self):
        self._create("sections/99-free.tex", "% free\n")
        status, data = self._call("/api/sections/delete",
                                  {"file": "sections/99-free.tex"})
        self.assertEqual(status, 200, data)
        self.assertFalse((self.root / "sections" / "99-free.tex").exists())

    def test_delete_missing_file(self):
        status, data = self._call("/api/sections/delete",
                                  {"file": "sections/gone.tex"})
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "SECTION_MISSING")

    def test_delete_rejects_escape(self):
        status, data = self._call("/api/sections/delete",
                                  {"file": "../outside.tex"})
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "PATH_ESCAPE")


class SectionCrudReadOnlyTest(unittest.TestCase):
    """只读服务：写接口一律 403 READ_ONLY，一个都不许漏。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", cls.root)
        cls.server, cls.token = create_server(cls.root, port=0, token=TOKEN)
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
        cls.tmp.cleanup()

    def _post(self, path, body):
        req = urllib.request.Request(self.base + path, method="POST",
                                     data=json.dumps(body).encode("utf-8"))
        req.add_header("Authorization", "Bearer " + TOKEN)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            exc.close()
            return exc.code, json.loads(raw)

    def test_all_write_endpoints_are_403(self):
        cases = [
            ("/api/sections/create", {"file": "sections/97-x.tex"}),
            ("/api/sections/rename", {"from": "sections/01-intro.tex",
                                      "to": "sections/97-x.tex"}),
            ("/api/sections/delete", {"file": "sections/01-intro.tex"}),
        ]
        for path, body in cases:
            status, data = self._post(path, body)
            self.assertEqual(status, 403, path)
            self.assertEqual(data["error"]["code"], "READ_ONLY", path)
        self.assertFalse((self.root / "sections" / "97-x.tex").exists())
        self.assertTrue((self.root / "sections" / "01-intro.tex").is_file())


class CitationsApiTest(unittest.TestCase):
    """引用页的只读接口：GET /api/citations。

    只读：不要 --allow-write 也能查（这一页只读不写盘）。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", cls.root)
        cls.server, cls.token = create_server(cls.root, port=0, token=TOKEN)
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

    def _get(self, path, token=None):
        req = urllib.request.Request(self.base + path)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            exc.close()
            return exc.code, json.loads(raw) if raw else {}

    def test_citations_ok(self):
        status, data = self._get("/api/citations", token=self.token)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])
        self.assertEqual("citations", data["endpoint"])
        self.assertIn("total", data)
        self.assertIn("entries", data)
        self.assertTrue(data["total"] >= 1, "样例项目里应该有 bib 条目")
        for row in data["entries"]:
            for field in ("key", "kind", "title", "doi", "arxiv", "url",
                          "file", "line", "used", "files", "status"):
                self.assertIn(field, row, "每条都要有 " + field)
            self.assertIn(row["status"], ("ok", "no_id", "bad_id", "unused"))

    def test_citations_needs_token(self):
        status, data = self._get("/api/citations")
        self.assertEqual(status, 401)
        self.assertEqual("UNAUTHORIZED", data["error"]["code"])

    def test_citations_is_read_only(self):
        # 只读服务（没加 --allow-write）照样能查引用：这一页不写盘。
        status, data = self._get("/api/citations", token=self.token)
        self.assertEqual(status, 200, data)


if __name__ == "__main__":
    unittest.main()


class ProjectManagementTest(unittest.TestCase):
    """不带项目启动：先起服务，再由页面/接口选文件夹。"""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="factscribe-home-")
        cls.saved_home = os.environ.get("HOME")
        os.environ["HOME"] = cls.home
        cls.server, cls.token = create_server(None, port=0, token=TOKEN,
                                             serve_ui=True)
        cls.port = cls.server.server_address[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
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

    def _call(self, path, method="GET", body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, method=method, data=data)
        req.add_header("Authorization", "Bearer " + TOKEN)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body_bytes = exc.read()
            exc.close()
            return exc.code, json.loads(body_bytes)

    def test_boot_without_project(self):
        status, data = self._call("/api/projects")
        self.assertEqual(status, 200)
        self.assertTrue(data["dir"].endswith(".factscribe"))
        self.assertIsNone(data["current"])
        status, data = self._call("/api/status")
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "NO_PROJECT")

    def test_select_and_remove_project(self):
        project = str(ROOT / "examples" / "minimal")
        status, data = self._call("/api/projects", "POST", {"path": project})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["project"]["name"], "paperkit 最小验收样例")
        selected = data["project"]["path"]
        self.assertEqual(data["projects"][0]["path"], selected)

        status, data = self._call("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["project"], "paperkit 最小验收样例")

        status, _ = self._call("/api/projects", "POST", {"path": "/tmp"})
        self.assertEqual(status, 400)

        status, data = self._call(
            "/api/projects?path=" + urllib.parse.quote(selected), "DELETE")
        self.assertEqual(status, 200)
        self.assertEqual(data["projects"], [])
        status, data = self._call("/api/status")
        self.assertEqual(status, 400)
