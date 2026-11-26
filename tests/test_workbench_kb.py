# -*- coding: utf-8 -*-
"""tests/test_workbench_kb.py —— 工作台段六：知识库。

覆盖四组（段六交付自查项 b）：

1. **收集**：项目目录下递归收集 `.tex` / `.md` / `.toml` / `.txt`；
   PDF 只登记文件名与大小，状态「待提取」。
2. **上传**：multipart 存进 `knowledge/` 目录（项目级 `workbench.toml`
   的 `[workbench].knowledge_dir`，缺省 `knowledge/`）。
3. **预览**：文本类直接读内容；路径越界（`..`、绝对路径）一律拒绝。
4. **进上下文**：知识库文本拼进 `/api/chat` 的上下文（有长度上限）。
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench import knowledge                  # noqa: E402
from factscribe.workbench.ai import build_context           # noqa: E402
from factscribe.workbench.server import create_server       # noqa: E402

BS = chr(92)

CONFIG_TOML = """[project]
title = "知识库测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\begin{document}
\\input{sections/01-intro}
\\end{document}
"""

INTRO_TEX = """\\section{引言}

开臂解出 10/16\\fact{A1}。
"""

NOTES_MD = """# 我们的口径

解出率按「解出臂数 / 总臂数」算，不做归一化。
"""


def _make_disk(root: Path, name: str = "paper") -> Path:
    disk = root / name
    (disk / "sections").mkdir(parents=True)
    (disk / "facts").mkdir(parents=True)
    (disk / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (disk / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (disk / "sections" / "01-intro.tex").write_text(INTRO_TEX, encoding="utf-8")
    (disk / "notes.md").write_text(NOTES_MD, encoding="utf-8")
    (disk / "measurements.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (disk / "paper.pdf").write_bytes(b"%PDF-1.4\n%stub\n")
    return disk


class KnowledgeListTests(unittest.TestCase):
    """文件清单：真文件、状态、大小。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.addCleanup(self._tmp.cleanup)

    def test_collects_text_files_recursively(self):
        rows = knowledge.list_files(self.disk)
        paths = [row["path"] for row in rows]
        self.assertIn("main.tex", paths)
        self.assertIn("sections/01-intro.tex", paths)
        self.assertIn("notes.md", paths)
        self.assertIn("factscribe.toml", paths)

    def test_ignores_unsupported_suffixes(self):
        paths = [row["path"] for row in knowledge.list_files(self.disk)]
        self.assertNotIn("measurements.csv", paths)

    def test_pdf_is_registered_only(self):
        rows = {row["path"]: row for row in knowledge.list_files(self.disk)}
        self.assertIn("paper.pdf", rows)
        pdf = rows["paper.pdf"]
        self.assertEqual(pdf["status"], "pending")
        self.assertEqual(pdf["status_label"], "待提取")
        self.assertGreater(pdf["size"], 0)

    def test_text_files_are_ready(self):
        rows = {row["path"]: row for row in knowledge.list_files(self.disk)}
        self.assertEqual(rows["notes.md"]["status"], "ready")
        self.assertEqual(rows["notes.md"]["status_label"], "可用")

    def test_skips_noise_dirs(self):
        (self.disk / "__pycache__").mkdir()
        (self.disk / "__pycache__" / "x.py").write_text("x = 1\n", encoding="utf-8")
        paths = [row["path"] for row in knowledge.list_files(self.disk)]
        self.assertFalse(any("__pycache__" in p for p in paths))


class KnowledgeDirTests(unittest.TestCase):
    """知识库目录：缺省 `knowledge/`，可配。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.addCleanup(self._tmp.cleanup)

    def test_default_knowledge_dir(self):
        self.assertEqual(knowledge.knowledge_dir(self.disk),
                         (self.disk / "knowledge").resolve())

    def test_configured_knowledge_dir(self):
        (self.disk / "workbench.toml").write_text(
            '[workbench]\nknowledge_dir = "refs"\n', encoding="utf-8")
        self.assertEqual(knowledge.knowledge_dir(self.disk),
                         (self.disk / "refs").resolve())

    def test_absolute_knowledge_dir_is_rejected(self):
        (self.disk / "workbench.toml").write_text(
            '[workbench]\nknowledge_dir = "/tmp/elsewhere"\n', encoding="utf-8")
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.knowledge_dir(self.disk)

    def test_knowledge_dir_outside_project_is_rejected(self):
        (self.disk / "workbench.toml").write_text(
            '[workbench]\nknowledge_dir = "../outside"\n', encoding="utf-8")
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.knowledge_dir(self.disk)


class KnowledgePreviewTests(unittest.TestCase):
    """预览：文本类直接读；越界路径拒绝。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.addCleanup(self._tmp.cleanup)

    def test_text_preview_returns_content(self):
        data = knowledge.preview(self.disk, "notes.md")
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "ready")
        self.assertIn("解出率", data["text"])

    def test_pdf_preview_has_no_text(self):
        data = knowledge.preview(self.disk, "paper.pdf")
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["text"], "")
        self.assertIn("段七", data["note"])

    def test_parent_path_is_rejected(self):
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.preview(self.disk, "../../etc/passwd")

    def test_absolute_path_is_rejected(self):
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.preview(self.disk, "/etc/passwd")


class KnowledgeUploadTests(unittest.TestCase):
    """上传：multipart 存进知识库目录。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.addCleanup(self._tmp.cleanup)

    def test_upload_lands_in_knowledge_dir(self):
        result = knowledge.save_upload(self.disk, "ref.md", b"# reference\n")
        self.assertTrue(result["ok"])
        target = self.disk / "knowledge" / "ref.md"
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_text(encoding="utf-8"), "# reference\n")
        self.assertEqual(result["status"], "ready")

    def test_upload_pdf_is_registered_as_pending(self):
        result = knowledge.save_upload(self.disk, "scan.pdf", b"%PDF-1.4\n")
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["status_label"], "待提取")

    def test_upload_rejects_unknown_suffix(self):
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.save_upload(self.disk, "data.xlsx", b"x")

    def test_upload_strips_directory_components(self):
        result = knowledge.save_upload(self.disk, "../evil.md", b"x")
        self.assertEqual(result["name"], "evil.md")
        self.assertTrue((self.disk / "knowledge" / "evil.md").is_file())

    def test_uploaded_file_shows_up_in_list(self):
        knowledge.save_upload(self.disk, "ref.md", b"# reference\n")
        paths = [row["path"] for row in knowledge.list_files(self.disk)]
        self.assertIn("knowledge/ref.md", paths)


class KnowledgeContextTests(unittest.TestCase):
    """知识库文本进对话上下文（带长度上限）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.addCleanup(self._tmp.cleanup)

    def test_context_includes_knowledge_text(self):
        knowledge.save_upload(self.disk, "ref.md", "口径是解出臂数除以总臂数。\n".encode("utf-8"))
        text = knowledge.context_text(self.disk)
        self.assertIn("解出臂数除以总臂数", text)
        self.assertIn("【知识库文件：knowledge/ref.md】", text)

    def test_context_is_truncated_to_limit(self):
        knowledge.save_upload(self.disk, "big.md", ("长" * 20000).encode("utf-8"))
        text = knowledge.context_text(self.disk, limit=500)
        self.assertLessEqual(len(text), 700)     # 截断标记本身占一点
        self.assertIn("已截断", text)

    def test_context_includes_project_text_files(self):
        text = knowledge.context_text(self.disk)
        self.assertIn("解出率", text)

    def test_build_context_carries_knowledge_block(self):
        knowledge.save_upload(self.disk, "ref.md", "独门口径XYZ。\n".encode("utf-8"))
        context = build_context(self.disk)
        self.assertIn("【知识库】", context)
        self.assertIn("独门口径XYZ", context)


class KnowledgeEndpointTests(unittest.TestCase):
    """HTTP 全链：清单 / 预览 / 上传。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _make_disk(self.root)
        self.server, self.index = create_server(self.root, port=0, ttl=0.0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=30) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def _upload(self, path, filename, payload):
        boundary = "----factscribekb"
        body = b""
        body += ("--%s\r\n" % boundary).encode("utf-8")
        body += ('Content-Disposition: form-data; name="file"; filename="%s"\r\n'
                 % filename).encode("utf-8")
        body += b"Content-Type: application/octet-stream\r\n\r\n"
        body += payload
        body += ("\r\n--%s--\r\n" % boundary).encode("utf-8")
        request = urllib.request.Request(
            self.base + path, data=body, method="POST",
            headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
        try:
            with urllib.request.urlopen(request, timeout=30) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_list_endpoint_returns_real_files(self):
        status, data = self._get("/api/project/paper/knowledge")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        paths = [row["path"] for row in data["files"]]
        self.assertIn("main.tex", paths)
        self.assertIn("sections/01-intro.tex", paths)

    def test_preview_endpoint_returns_text(self):
        status, data = self._get("/api/project/paper/knowledge/preview?path=notes.md")
        self.assertEqual(status, 200)
        self.assertIn("解出率", data["text"])

    def test_preview_endpoint_rejects_escape(self):
        status, data = self._get("/api/project/paper/knowledge/preview?path=../../etc/passwd")
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])

    def test_upload_endpoint_stores_file(self):
        status, data = self._upload("/api/project/paper/knowledge/upload",
                                    "ref.md", b"# uploaded\n")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertTrue((self.root / "paper" / "knowledge" / "ref.md").is_file())

    def test_unknown_knowledge_route_is_404(self):
        status, _ = self._get("/api/project/paper/knowledge/nope")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
