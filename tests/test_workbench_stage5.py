# -*- coding: utf-8 -*-
"""tests/test_workbench_stage5.py —— 工作台段五：框架重排 ＋ 四个功能点。

覆盖四组（段五交付自查项）：

1. **摘要可编辑**：封面摘要（main.tex 的 ``abstract`` 环境）纳入就地编辑；
   保存走段二同一保护通道——``\\fact{}`` 芯片原样保留、原子写、留 ``.bak``。
2. **单语言标记（服务端可测部分）**：项目只有一个盘时
   ``multi_lang`` 为假；双盘项目为真。（条目 41 起前端不再据此隐藏中/EN 切换。）
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
from factscribe.workbench.projects import (           # noqa: E402
    disk_sections, load_projects,
)
from factscribe.workbench.server import create_server   # noqa: E402

CONFIG_TOML = """[project]
title = "段五测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

#: 节文件式布局的配置：闭包走 main.tex 的 \input 链（没有 sections glob），
#: 摘要因此是独立节文件 `sections/00_abstract.tex`（真实 paper-b 就是这套）。
SECTIONED_CONFIG_TOML = """schema = "factscribe-project/3.0"

[project]
name = "节文件式摘要"
root_tex = "main.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

SECTIONED_MAIN_TEX = """\\documentclass{article}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\title{节文件式摘要}
\\begin{document}
\\maketitle
\\input{sections/00_abstract}
\\input{sections/01-intro}
\\end{document}
"""

SECTIONED_ABSTRACT_TEX = """\\begin{abstract}
We report a resolve rate of 10/16\\fact{A1} on the testbed, and the gate
caught 30/36\\fact{B1} planted defects.
\\end{abstract}

% FACTS-USED: A1 B1
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


def _make_sectioned_disk(root: Path, name: str = "paper-b") -> Path:
    """节文件式摘要的项目：摘要在 `sections/00_abstract.tex`，经 \\input 装配。"""
    disk = root / name
    (disk / "sections").mkdir(parents=True)
    (disk / "facts").mkdir(parents=True)
    (disk / "factscribe.toml").write_text(SECTIONED_CONFIG_TOML, encoding="utf-8")
    (disk / "refs.bib").write_text("@article{knuth1984,\n  title={x}\n}\n",
                                   encoding="utf-8")
    (disk / "main.tex").write_text(SECTIONED_MAIN_TEX, encoding="utf-8")
    (disk / "sections" / "00_abstract.tex").write_text(SECTIONED_ABSTRACT_TEX,
                                                        encoding="utf-8")
    (disk / "sections" / "01-intro.tex").write_text(INTRO_TEX, encoding="utf-8")
    return disk



class SectionedAbstractTests(unittest.TestCase):
    """节文件式摘要（sectioned）：摘要是独立节文件，走同一套写回通道。

    回归背景：段五验收打回——`save_abstract` 原来只认根文件的 `abstract`
    环境，paper-b 这套「摘要独立成 `sections/00_abstract.tex` 经 \\input 装配」
    的布局直接 400。现在渲染与写回共用同一套闭包定位。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.disk = _make_sectioned_disk(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_abstract_block_points_at_section_file(self):
        block = wb.abstract_block(self.disk)
        self.assertEqual(block.file, "sections/00_abstract.tex")
        self.assertEqual(block.block_id, wb.ABSTRACT_BLOCK_ID)
        self.assertIn("10/16", block.raw)

    def test_render_closure_carries_cover_abstract(self):
        blocks = disk_sections(self.disk)["blocks"]
        cover = [b for b in blocks if b.get("id") == wb.ABSTRACT_BLOCK_ID]
        self.assertEqual(len(cover), 1)
        self.assertEqual(cover[0]["kind"], "abstract")
        self.assertEqual(cover[0]["file"], "sections/00_abstract.tex")
        self.assertIn("start", cover[0])
        self.assertIn("end", cover[0])

    def test_save_writes_back_to_the_section_file(self):
        abstract_file = self.disk / "sections" / "00_abstract.tex"
        before = abstract_file.read_text(encoding="utf-8")
        result = wb.save_abstract(self.disk, block_text(self.disk)
                                  + " A new closing sentence.")
        after = abstract_file.read_text(encoding="utf-8")
        self.assertTrue(result["ok"])
        self.assertEqual(result["file"], "sections/00_abstract.tex")
        self.assertNotEqual(before, after)
        self.assertIn("A new closing sentence.", after)
        # 保护面：两个 \fact 芯片都在
        self.assertEqual(before.count("\\fact{"), after.count("\\fact{"))
        self.assertIn("\\fact{A1}", after)
        self.assertIn("\\fact{B1}", after)
        # main.tex 一个字节没动
        self.assertEqual((self.disk / "main.tex").read_text(encoding="utf-8"),
                         SECTIONED_MAIN_TEX)

    def test_save_leaves_backup(self):
        abstract_file = self.disk / "sections" / "00_abstract.tex"
        before = abstract_file.read_text(encoding="utf-8")
        result = wb.save_abstract(self.disk, block_text(self.disk) + " More prose.")
        backup = Path(result["backup"])
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_text(encoding="utf-8"), before)

    def test_deleted_chip_is_restored_in_section_file(self):
        result = wb.save_abstract(self.disk, "A rewritten abstract without markers.")
        self.assertIn("\\fact{A1}", result["after"])
        self.assertIn("\\fact{B1}", result["after"])


def block_text(disk: Path) -> str:
    """摘要块的散文（保护面芯片换成占位符）——模拟前端送来的文本。"""
    model = wb.editable_model(disk, wb.abstract_block(disk))
    return model["plain"]


class SectionedAbstractEndpointTests(unittest.TestCase):
    """节文件式摘要走 HTTP 全链：读模型 → 写回。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _make_sectioned_disk(self.root)
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

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=30) as res:
            return res.status, res.read()

    def _post(self, path, body):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=60) as res:
            return res.status, json.loads(res.read().decode("utf-8"))

    def test_block_endpoint_returns_section_file_model(self):
        status, body = self._get("/api/disk/paper-b/paper-b/block/cover-abstract")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["file"], "sections/00_abstract.tex")
        self.assertEqual(data["id"], "cover-abstract")
        self.assertIn("fact", [chip["label"] for chip in data["chips"]])

    def test_edit_endpoint_writes_back_to_section_file(self):
        status, body = self._get("/api/disk/paper-b/paper-b/block/cover-abstract")
        model = json.loads(body.decode("utf-8"))
        status, data = self._post("/api/disk/paper-b/paper-b/edit", {
            "block": "cover-abstract",
            "text": model["plain"] + " A sentence added through the HTTP chain.",
        })
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["file"], "sections/00_abstract.tex")
        self.assertIn("\\fact{A1}", data["after"])
        target = self.root / "paper-b" / "sections" / "00_abstract.tex"
        self.assertIn("A sentence added through the HTTP chain.",
                      target.read_text(encoding="utf-8"))
        self.assertTrue(Path(data["backup"]).is_file())


class NoNestingWriteBackTests(unittest.TestCase):
    """摘要保存不套娃（段五二次验收打回）。

    回归背景：写回按「文件里第一个 `\\end{abstract}`」截断，于是提交文本若
    自带环境（或整份文件被回传），每存一次就多包一层。现在写回以渲染闭包
    给出的块为权威 span，提交文本自带环境时只取环境内散文，环境标记与环境
    外的 `% FACTS-USED` 行属文件原有结构，不补、不重生成。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.disk = _make_sectioned_disk(self.root)
        self.target = self.disk / "sections" / "00_abstract.tex"

    def tearDown(self):
        self.tmp.cleanup()

    def _layers(self, text):
        return (text.count("\\begin{abstract}"), text.count("\\end{abstract}"),
                text.count("FACTS-USED"))

    def test_same_text_saved_three_times_is_byte_stable(self):
        text = block_text(self.disk)
        digests = []
        for _ in range(3):
            wb.save_abstract(self.disk, text)
            digests.append(self.target.read_bytes())
        self.assertEqual(digests[0], digests[1])
        self.assertEqual(digests[1], digests[2])
        self.assertEqual(self._layers(digests[0].decode("utf-8")), (1, 1, 1))

    def test_submitted_text_carrying_env_is_not_wrapped_again(self):
        before = self.target.read_text(encoding="utf-8")
        # 前端把整份文件回传了（自带环境 ＋ 环境外的 FACTS-USED 行）
        wb.save_abstract(self.disk, before)
        after = self.target.read_text(encoding="utf-8")
        self.assertEqual(after, before)
        self.assertEqual(self._layers(after), (1, 1, 1))

    def test_submitted_wrapped_prose_keeps_file_structure(self):
        prose = block_text(self.disk)
        wrapped = ("\\begin{abstract}\n" + prose + "\n\\end{abstract}\n\n"
                   "% FACTS-USED: A1 B1\n")
        wb.save_abstract(self.disk, wrapped)
        after = self.target.read_text(encoding="utf-8")
        self.assertEqual(self._layers(after), (1, 1, 1))
        self.assertIn("FACTS-USED: A1 B1", after)
        self.assertIn("\\fact{A1}", after)

    def test_external_change_then_save_does_not_stack(self):
        stale = self.target.read_text(encoding="utf-8")
        # 绕过服务端直改文件
        self.target.write_text(
            stale.replace("We report a resolve rate",
                          "We reported a resolve rate"), encoding="utf-8")
        wb.save_abstract(self.disk, stale)      # 前端还拿着旧文本
        after = self.target.read_text(encoding="utf-8")
        self.assertEqual(self._layers(after), (1, 1, 1))
        self.assertNotIn("Scientific papers", after)   # 没多出第二层

    def test_already_nested_file_does_not_grow(self):
        # 已经被套过一层的老文件：再存一次不得再叠一层（层数不变）
        original = self.target.read_text(encoding="utf-8")
        self.target.write_text(
            original.replace("\\begin{abstract}\n",
                              "\\begin{abstract}\n\\begin{abstract}\n", 1),
            encoding="utf-8")
        wb.save_abstract(self.disk, original)
        after = self.target.read_text(encoding="utf-8")
        self.assertLessEqual(after.count("\\begin{abstract}"), 2)
        self.assertLessEqual(after.count("\\end{abstract}"), 2)


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
    """单语言项目（只有一个盘）→ 服务端给 multi_lang 假（条目 41 起前端不再隐藏切换）。"""

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
