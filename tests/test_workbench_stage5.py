# -*- coding: utf-8 -*-
"""tests/test_workbench_stage5.py —— 工作台段五：框架重排 ＋ 四个功能点。

覆盖四组（段五交付自查项）：

1. **摘要可编辑**：封面摘要（main.tex 的 ``abstract`` 环境）纳入就地编辑；
   保存走段二同一保护通道——``\\fact{}`` 芯片原样保留、原子写、留 ``.bak``。
2. **单语言隐藏逻辑（服务端可测部分）**：项目只有一个盘时
   ``multi_lang`` 为假（前端据此把中/EN 切换整组隐藏）；双盘项目为真。
3. **PDF 渲染端点结构**：``POST /api/disk/<p>/<d>/action`` 认 ``pdf``；
   ``GET /api/disk/<p>/<d>/pdf`` 回传 PDF 字节；没编译过就是 404。
4. **报告删除**：删导入记录只动草稿，报告源文件不动。

另外：投稿包动作与打开项目目录动作的返回结构、目录写回（调序/删除/新建）
仍走段二链路。
"""
from __future__ import annotations

import json
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

from factscribe.workbench import write as wb           # noqa: E402
from factscribe.workbench.importer import (           # noqa: E402
    delete_draft, draft_path, write_draft,
)
from factscribe.workbench.projects import load_projects  # noqa: E402
from factscribe.workbench.server import create_server   # noqa: E402

CONFIG_TOML = """[project]
title = "段五测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\title{段五测试}
\\begin{document}
\\maketitle
\\begin{abstract}
We report a resolve rate of 10/16\\fact{A1} on the testbed.
\\end{abstract}
\\input{sections/01-intro}
\\input{sections/02-method}
\\end{document}
"""

INTRO_TEX = """\\section{引言}

开臂解出 10/16\\fact{A1}。
"""

METHOD_TEX = """\\section{方法}

方法细节见 \\cite{knuth1984}。
"""


def _make_disk(root: Path, name: str, title: str = "段五测试",
               with_abstract: bool = True) -> Path:
    disk = root / name
    (disk / "sections").mkdir(parents=True)
    (disk / "facts").mkdir(parents=True)
    (disk / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (disk / "refs.bib").write_text("@article{knuth1984,\n  title={x}\n}\n",
                                   encoding="utf-8")
    main = MAIN_TEX if with_abstract else MAIN_TEX.replace(
        "\\begin{abstract}\nWe report a resolve rate of 10/16\\fact{A1} on the testbed.\n\\end{abstract}\n", "")
    (disk / "main.tex").write_text(main, encoding="utf-8")
    (disk / "sections" / "01-intro.tex").write_text(INTRO_TEX, encoding="utf-8")
    (disk / "sections" / "02-method.tex").write_text(METHOD_TEX, encoding="utf-8")
    return disk


class AbstractWriteBackTests(unittest.TestCase):
    """摘要就地编辑：写回 main.tex，保护面保留，留 .bak。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.disk = _make_disk(self.root, "paper")

    def tearDown(self):
        self.tmp.cleanup()

    def test_abstract_block_is_found(self):
        block = wb.abstract_block(self.disk)
        self.assertEqual(block.block_id, wb.ABSTRACT_BLOCK_ID)
        self.assertEqual(block.file, "main.tex")
        self.assertIn("10/16", block.raw)

    def test_abstract_model_exposes_fact_chip(self):
        model = wb.editable_model(self.disk, wb.abstract_block(self.disk))
        labels = [chip["label"] for chip in model["chips"]]
        self.assertIn("fact", labels)
        self.assertIn("num", labels)

    def test_save_abstract_keeps_fact_and_writes_backup(self):
        before = (self.disk / "main.tex").read_text(encoding="utf-8")
        result = wb.save_abstract(self.disk,
                                  "We report a resolve rate of 10/16 on the testbed, and more.")
        after = (self.disk / "main.tex").read_text(encoding="utf-8")
        self.assertIn("\\fact{A1}", after)
        self.assertNotEqual(before, after)
        backup = Path(result["backup"])
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_text(encoding="utf-8"), before)

    def test_deleted_chip_is_restored(self):
        result = wb.save_abstract(self.disk, "A rewritten abstract without any marker.")
        self.assertIn("\\fact{A1}", result["after"])

    def test_unbalanced_braces_are_rejected(self):
        before = (self.disk / "main.tex").read_text(encoding="utf-8")
        with self.assertRaises(Exception):
            wb.save_abstract(self.disk, "Broken { brace")
        self.assertEqual((self.disk / "main.tex").read_text(encoding="utf-8"), before)

    def test_missing_abstract_is_a_clear_error(self):
        disk = _make_disk(self.root, "noabs", with_abstract=False)
        with self.assertRaises(Exception) as ctx:
            wb.abstract_block(disk)
        self.assertIn("abstract", str(ctx.exception))


class SingleLanguageFlagTests(unittest.TestCase):
    """单语言项目（只有一个盘）→ 中/EN 切换整组隐藏：服务端给 multi_lang。"""

    def test_single_disk_project_is_not_multi_lang(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_disk(root, "solo")
            projects = load_projects(root)
            self.assertEqual(len(projects), 1)
            self.assertFalse(projects[0]["multi_lang"])
            self.assertEqual(projects[0]["langs"], ["en"])

    def test_two_disk_project_is_multi_lang(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_disk(root, "paper")
            _make_disk(root, "paper-zh")
            projects = load_projects(root)
            self.assertEqual(len(projects), 1)
            self.assertTrue(projects[0]["multi_lang"])
            self.assertEqual(sorted(projects[0]["langs"]), ["en", "zh"])


class ActionEndpointTests(unittest.TestCase):
    """常用功能端点：渲染 PDF / 导出投稿包 / 打开项目目录。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _make_disk(self.root, "paper")
        self.server, self.index = create_server(self.root, port=0, ttl=0.0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def _post(self, path, body):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=120) as res:
            return res.status, json.loads(res.read().decode("utf-8"))

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=30) as res:
            return res.status, res.read()

    def test_pdf_action_returns_structured_shape(self):
        status, data = self._post("/api/disk/paper/paper/action", {"action": "pdf"})
        self.assertEqual(status, 200)
        self.assertIn("ok", data)
        self.assertEqual(data.get("action"), "pdf")
        self.assertIn("pdf_path", data)
        self.assertIn("message", data)
        self.assertIn("duration_ms", data)
        # 没编译成功时必须明说失败，不许假装成功。
        if not data["ok"]:
            self.assertIn("error", data)

    def test_pdf_endpoint_404s_before_build(self):
        try:
            self._get("/api/disk/paper/paper/pdf")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)
        else:
            self.fail("没编译过就应当 404")

    def test_unknown_action_is_404(self):
        try:
            self._post("/api/disk/paper/paper/action", {"action": "nope"})
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)
        else:
            self.fail("没有这个动作应当 404")

    def test_bundle_action_returns_structured_shape(self):
        status, data = self._post("/api/disk/paper/paper/action", {"action": "bundle"})
        self.assertEqual(status, 200)
        self.assertEqual(data.get("action"), "bundle")
        for key in ("bundle_dir", "files", "file_count", "gate", "passed",
                    "failed", "waived", "exit_code"):
            self.assertIn(key, data)

    def test_open_dir_action_returns_path(self):
        status, data = self._post("/api/disk/paper/paper/action", {"action": "open_dir"})
        self.assertEqual(status, 200)
        self.assertEqual(data.get("action"), "open_dir")
        self.assertIn("path", data)
        self.assertIn("opened", data)
        # 非 macOS 时不许假装打开过。
        if data["ok"] and not data["opened"]:
            self.assertIn("error", data)

    def test_abstract_block_endpoint_shape(self):
        status, body = self._get("/api/disk/paper/paper/block/cover-abstract")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["id"], "cover-abstract")
        self.assertIn("plain", data)
        self.assertIn("chips", data)

    def test_abstract_edit_endpoint_writes_back(self):
        status, body = self._get("/api/disk/paper/paper/block/cover-abstract")
        model = json.loads(body.decode("utf-8"))
        plain = model["plain"]
        status, data = self._post("/api/disk/paper/paper/edit", {
            "block": "cover-abstract", "text": plain + " A new sentence.",
        })
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["block"], "cover-abstract")
        self.assertIn("\\fact{A1}", data["after"])
        self.assertTrue(Path(data["backup"]).is_file())


class ReportDeleteTests(unittest.TestCase):
    """删导入记录：只删草稿；报告源文件不动。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.disk = _make_disk(self.root, "paper")
        self.reports = self.disk / "reports"
        self.reports.mkdir(parents=True, exist_ok=True)
        self.source = self.reports / "run1.toml"
        self.source.write_text(
            "[[metric]]\nid = \"m1\"\nclaim = \"c\"\nvalue = \"1\"\nsource = \"s\"\n",
            encoding="utf-8")
        write_draft(self.disk, "run1.toml",
                    [{"id": "m1", "claim": "c", "value": "1", "source": "s"}],
                    mapping={"m1": "A1"}, source_path=self.source,
                    report_sha256="0" * 64)

    def tearDown(self):
        self.tmp.cleanup()

    def test_delete_removes_draft_only(self):
        draft = draft_path(self.disk, "run1.toml")
        self.assertTrue(draft.is_file())
        result = delete_draft(self.disk, "run1.toml")
        self.assertTrue(result["ok"])
        self.assertFalse(draft.exists())
        self.assertTrue(self.source.is_file())
        self.assertEqual(result["source_file"], "run1.toml")

    def test_delete_missing_record_raises(self):
        with self.assertRaises(Exception):
            delete_draft(self.disk, "nope.toml")


class TocWriteBackTests(unittest.TestCase):
    """目录并入导航面板后，调序/删除/新建仍走段二写回链路。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.disk = _make_disk(self.root, "paper")

    def tearDown(self):
        self.tmp.cleanup()

    def test_move_rewrites_assembly(self):
        before = (self.disk / "main.tex").read_text(encoding="utf-8")
        result = wb.move_section(self.disk, "sections/02-method.tex", "up")
        self.assertTrue(result["ok"])
        after = (self.disk / "main.tex").read_text(encoding="utf-8")
        self.assertNotEqual(before, after)
        self.assertLess(after.index("02-method"), after.index("01-intro"))

    def test_create_section_writes_back(self):
        result = wb.create_section(self.disk, "新章节", slug="new-section")
        self.assertTrue(result["ok"])
        text = (self.disk / "main.tex").read_text(encoding="utf-8")
        self.assertIn("new-section", text)

    def test_delete_section_moves_to_attic(self):
        result = wb.delete_section(self.disk, "sections/02-method.tex")
        self.assertTrue(result["ok"])
        attic = self.disk / "sections" / "attic"
        self.assertTrue(any(attic.glob("*.tex")))


if __name__ == "__main__":
    unittest.main()
