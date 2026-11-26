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


def png_bytes(width: int = 2, height: int = 2) -> bytes:
    """最小合法 PNG：纯标准库拼出来，不引第三方。"""
    import struct
    import zlib

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class ServeApiAuthTest(unittest.TestCase):
    """serve 的 API 面（网页 UI 那一层已按第 ④ 步删除，见 SPEC-SERVE.md）。"""

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
        conf = cls.root / "factscribe.toml"
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

    def test_delete_moves_section_to_attic_instead_of_destroying_it(self):
        """删节＝挪 attic（可逆），不真删——口径 8 与段落级统一。"""
        self._create("sections/99-keep.tex", "% keep\n")
        status, data = self._call("/api/sections/delete",
                                  {"file": "sections/99-keep.tex"})
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])
        attic = self.root / "attic" / "sections" / "99-keep.tex"
        self.assertTrue(attic.is_file(), "删掉的节要挪进 attic（可逆）")
        self.assertEqual(attic.read_text(encoding="utf-8"), "% keep\n")
        self.assertFalse((self.root / "sections" / "99-keep.tex").exists())
        self.assertEqual(data.get("attic"), "attic/sections/99-keep.tex")

    def test_deleted_section_leaves_the_audit_closure(self):
        """挪进 attic 的节不许再进审计闭包（否则等于没删）。"""
        self._create("sections/99-closure.tex", "% closure\n")
        status, _data = self._call("/api/sections/delete",
                                   {"file": "sections/99-closure.tex"})
        self.assertEqual(status, 200)
        status, data = self._call("/api/audit", {})
        self.assertEqual(status, 200)
        files = [s.get("file") for s in (data.get("project", {}).get("sections")
                                         or [])]
        self.assertNotIn("sections/99-closure.tex", files, files)

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


class AssetApiTest(unittest.TestCase):
    """读图接口：GET /api/asset?path=…

    只读：要 token，但不写盘（不用 --allow-write）。路径必须留在项目根里。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", cls.root)
        (cls.root / "figs").mkdir()
        (cls.root / "figs" / "a.png").write_bytes(png_bytes())
        (cls.root / "figs" / "b.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4">'
            '<rect width="4" height="4"/></svg>', encoding="utf-8")
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

    def _get(self, path, token=None):
        req = urllib.request.Request(self.base + path)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.headers.get("Content-Type"), resp.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            exc.close()
            body = json.loads(raw.decode("utf-8")) if raw else {}
            return exc.code, body.get("error", {}).get("code"), raw

    def test_png_is_served_with_image_png(self):
        status, ctype, body = self._get(
            "/api/asset?path=figs/a.png", token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "image/png")
        self.assertTrue(body.startswith(b"\x89PNG"), body[:8])

    def test_svg_content_type_follows_extension(self):
        status, ctype, body = self._get(
            "/api/asset?path=figs/b.svg", token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "image/svg+xml")
        self.assertIn(b"<svg", body)

    def test_escape_and_absolute_path_are_rejected(self):
        for path in ("../x.png", "figs/../../x.png", "/etc/hosts"):
            status, code, _ = self._get(
                "/api/asset?path=" + urllib.parse.quote(path), token=TOKEN)
            self.assertEqual(status, 400, path)
            self.assertEqual(code, "PATH_ESCAPE", path)

    def test_symlink_is_rejected(self):
        link = self.root / "figs" / "link.png"
        link.symlink_to(self.root / "figs" / "a.png")
        try:
            status, code, _ = self._get(
                "/api/asset?path=figs/link.png", token=TOKEN)
            self.assertEqual(status, 400)
            self.assertEqual(code, "PATH_ESCAPE")
        finally:
            link.unlink()

    def test_missing_file_is_404(self):
        status, code, _ = self._get(
            "/api/asset?path=figs/nope.png", token=TOKEN)
        self.assertEqual(status, 404)
        self.assertEqual(code, "ASSET_NOT_FOUND")

    def test_unsupported_extension_is_rejected(self):
        (self.root / "figs" / "note.txt").write_text("hi", encoding="utf-8")
        status, code, _ = self._get(
            "/api/asset?path=figs/note.txt", token=TOKEN)
        self.assertEqual(status, 400)
        self.assertEqual(code, "ASSET_INVALID")

    def test_oversize_file_is_rejected(self):
        big = self.root / "figs" / "big.png"
        with big.open("wb") as fh:
            fh.truncate(21 * 1024 * 1024)      # 21 MiB > 20 MiB 上限
        try:
            status, code, _ = self._get(
                "/api/asset?path=figs/big.png", token=TOKEN)
            self.assertEqual(status, 400)
            self.assertEqual(code, "ASSET_INVALID")
        finally:
            big.unlink()

    def test_asset_needs_token(self):
        status, code, _ = self._get("/api/asset?path=figs/a.png")
        self.assertEqual(status, 401)
        self.assertEqual(code, "UNAUTHORIZED")

    def test_asset_is_read_only(self):
        # 服务没开 --allow-write，图片照样读得到：这一条不写盘。
        status, _, _ = self._get("/api/asset?path=figs/a.png", token=TOKEN)
        self.assertEqual(status, 200)


MINIMAL_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>stream
BT /F1 24 Tf 20 100 Td (Hello) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R>>
%%EOF
"""


@unittest.skipUnless(shutil.which("pdftoppm"), "缺 poppler：PDF 图转换跳过")
class AssetPdfTest(unittest.TestCase):
    """PDF 图：服务端用 pdftoppm 转第一页 PNG 再返回。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", cls.root)
        cls.pdf = cls.root / "figs.pdf"
        cls.pdf.write_bytes(MINIMAL_PDF)
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

    def _get(self, path):
        req = urllib.request.Request(self.base + path)
        req.add_header("Authorization", "Bearer " + TOKEN)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, resp.headers.get("Content-Type"), resp.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            exc.close()
            body = json.loads(raw.decode("utf-8")) if raw else {}
            return exc.code, body.get("error", {}).get("code"), raw

    def test_pdf_is_converted_to_png(self):
        status, ctype, body = self._get("/api/asset?path=figs.pdf")
        if status == 400 and ctype == "POPPLER_MISSING":
            self.skipTest("本机没有 pdftoppm（poppler）")
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "image/png")
        self.assertTrue(body.startswith(b"\x89PNG"), body[:8])


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
        self.assertEqual(data["project"]["name"], "factscribe 最小验收样例")
        selected = data["project"]["path"]
        self.assertEqual(data["projects"][0]["path"], selected)

        status, data = self._call("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["project"], "factscribe 最小验收样例")

        status, _ = self._call("/api/projects", "POST", {"path": "/tmp"})
        self.assertEqual(status, 400)

        status, data = self._call(
            "/api/projects?path=" + urllib.parse.quote(selected), "DELETE")
        self.assertEqual(status, 200)
        self.assertEqual(data["projects"], [])
        status, data = self._call("/api/status")
        self.assertEqual(status, 400)


class NoTokenAndOriginTest(unittest.TestCase):
    """无 token 模式 + 同源检查：token 可选，跨源一律拒。"""

    @classmethod
    def setUpClass(cls):
        cls.server, cls.token = create_server(
            ROOT / "examples" / "minimal", port=0, token="",
            require_token=False)
        cls.port = cls.server.server_address[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _get(self, path, origin=None):
        req = urllib.request.Request(self.base + path)
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            exc.close()
            return exc.code, json.loads(body)

    def test_no_token_mode_serves_api(self):
        status, data = self._get("/api/project")
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"))

    def test_cross_origin_is_rejected(self):
        status, data = self._get("/api/project", origin="http://evil.example")
        self.assertEqual(403, status)
        self.assertEqual("CROSS_ORIGIN", data["error"]["code"])

    def test_same_origin_is_allowed(self):
        status, _ = self._get("/api/project", origin=self.base)
        self.assertEqual(200, status)

    def test_token_mode_still_rejects_cross_origin(self):
        server, token = create_server(ROOT / "examples" / "minimal", port=0, token="t2")
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            req = urllib.request.Request("http://127.0.0.1:%d/api/project" % port)
            req.add_header("Authorization", "Bearer " + token)
            req.add_header("Origin", "http://evil.example")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(403, ctx.exception.code)
            ctx.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class CrossOriginPutTest(unittest.TestCase):
    """跨源写闸：PUT /api/sections 是唯一覆盖论文正文 .tex 的写接口。

    do_PUT 原先是四个 HTTP 方法里唯一没做同源校验的（GET/POST/DELETE 都有
    _origin_ok）——浏览器里任意一个恶意页面能整节覆盖论文正文；--no-token
    模式下连 token 都不需要。语义与其它三处一致：没有 Origin 头放行（命令行
    与 Node 代理走这条），带了 Origin 但不是本监听地址就拒。
    """

    REL = "sections/01-intro.tex"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="fs-web-put-")
        cls.root = Path(cls.tmp) / "proj"
        shutil.copytree(ROOT / "examples" / "minimal", cls.root)
        cls.server, cls.token = create_server(
            cls.root, port=0, token=TOKEN, require_token=False,
            allow_write=True)
        cls.port = cls.server.server_address[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _put(self, origin=None, text="跨源注入的正文\n", token=TOKEN):
        body = json.dumps({"file": self.REL, "text": text}).encode("utf-8")
        req = urllib.request.Request(self.base + "/api/sections",
                                     method="PUT", data=body)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            exc.close()
            return exc.code, json.loads(raw) if raw else {}

    def _disk(self):
        return (self.root / self.REL).read_text(encoding="utf-8")

    def test_cross_origin_put_is_rejected_and_does_not_write(self):
        """--no-token 模式（个人机器常用组合）：跨源 PUT 必须 403 且不写盘。"""
        before = self._disk()
        status, data = self._put(origin="http://evil.example")
        self.assertEqual(status, 403, data)
        self.assertEqual(data["error"]["code"], "CROSS_ORIGIN")
        self.assertEqual(self._disk(), before)

    def test_cross_origin_put_with_other_loopback_port_is_rejected(self):
        before = self._disk()
        status, data = self._put(origin="http://127.0.0.1:1")
        self.assertEqual(status, 403, data)
        self.assertEqual(data["error"]["code"], "CROSS_ORIGIN")
        self.assertEqual(self._disk(), before)

    def test_same_origin_put_still_writes(self):
        """前端同源写路径不许被闸门挡住。"""
        status, data = self._put(origin=self.base, text="同源写入的正文\n")
        self.assertEqual(status, 200, data)
        self.assertIn("同源写入的正文", self._disk())

    def test_no_origin_put_still_writes(self):
        """命令行与 Node 代理不带 Origin 头——这条路径必须照常能写。"""
        status, data = self._put(origin=None, text="无 Origin 头的写入\n")
        self.assertEqual(status, 200, data)
        self.assertIn("无 Origin 头的写入", self._disk())


if __name__ == "__main__":
    unittest.main()
