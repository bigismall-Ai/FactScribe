# -*- coding: utf-8 -*-
"""tests/test_workbench_write.py —— 工作台段二：写回与章节管理。

覆盖五组（段二交付自查项）：

1. **编辑写回保留保护面**：改散文时 `\\fact{}`、绑定的数字、`\\cite{}`、
   `\\ref{}` 原样保留；用户把芯片删了也会按原文位置补回来；正文里新写的
   `\\fact{}` 会被剥掉。
2. **调序写回 main.tex**：装配顺序真的改了，且留 `.bak`。
3. **删除进 attic**：从装配移除，文件挪到 `sections/attic/`（不真删）。
4. **新建项目骨架**：`factscribe.toml` / `sections/` / `facts/` / `README.md`
   都在盘上，`[workbench]` 表写对了。
5. **toml 往返**：改 `[workbench]` 表后读回来还是那个值，别的段不动。

外加：原子写（`.tmp` + rename、保留权限、留 `.bak`）与 HTTP 端的写接口。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench import write as wb           # noqa: E402
from factscribe.workbench.projects import (           # noqa: E402
    disk_sections, load_projects,
)

CONFIG_TOML = """[project]
title = "写回测试"
authors = ["tester"]
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\title{写回测试}
\\author{tester}
\\begin{document}
\\input{sections/01-intro}
\\input{sections/02-method}
\\end{document}
"""

INTRO_TEX = """\\section{引言}

开臂解出 10/16\\fact{A1}。方法与记号见 \\cite{knuth1984}，详见 \\ref{sec:two}。
"""

METHOD_TEX = """\\section{方法}

对比臂解出 8 道\\fact{A3}。
"""

FACTS_TOML = """[[fact]]
id = "A1"
claim = "开臂解出"
value = "10/16"
source = "results/data.md"
source_sha256 = "0" * 64
locator = "汇总表"

[[fact]]
id = "A3"
claim = "对比臂解出"
value = "8"
source = "results/data.md"
source_sha256 = "0" * 64
locator = "汇总表"
"""


def make_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (root / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (root / "refs.bib").write_text("", encoding="utf-8")
    (root / "sections").mkdir(exist_ok=True)
    (root / "sections" / "01-intro.tex").write_text(INTRO_TEX, encoding="utf-8")
    (root / "sections" / "02-method.tex").write_text(METHOD_TEX, encoding="utf-8")
    (root / "facts").mkdir(exist_ok=True)
    (root / "facts" / "01-core.toml").write_text(FACTS_TOML, encoding="utf-8")
    return root


class WriteBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factscribe-wbwrite-"))
        self.root = make_project(self.tmp / "paper")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def para_id(self, rel: str = "sections/01-intro.tex", index: int = 0) -> str:
        blocks = disk_sections(self.root)["blocks"]
        hits = [b for b in blocks if b.get("file") == rel and b["kind"] == "para"]
        return hits[index]["id"]

    def model(self, block_id: str) -> dict:
        block = wb.find_block(self.root, "sections/01-intro.tex", block_id)
        return wb.editable_model(self.root, block)


# --------------------------------------------------------------------------
# 1. 编辑写回：保护面
# --------------------------------------------------------------------------

class EditWriteBackTest(WriteBase):
    def test_prose_changes_but_fact_and_number_survive(self):
        """改散文 → 散文变了，\\fact 与绑定的数字原样保留。"""
        block_id = self.para_id()
        model = self.model(block_id)
        edited = model["plain"].replace("开臂解出", "开臂最终解出")
        result = wb.save_block(self.root, "sections/01-intro.tex", block_id, edited)
        after = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("开臂最终解出 10/16\\fact{A1}", after)
        self.assertIn("\\cite{knuth1984}", after)
        self.assertIn("\\ref{sec:two}", after)
        self.assertEqual(result["warnings"], [])

    def test_bound_number_is_protected_and_marked(self):
        """紧跟 \\fact 的数字＝绑定令牌：它在保护面里。"""
        model = self.model(self.para_id())
        labels = [chip["label"] for chip in model["chips"]]
        self.assertIn("fact", labels)
        self.assertIn("num", labels)
        self.assertIn("cite", labels)
        self.assertIn("ref", labels)
        numbers = [chip for chip in model["chips"] if chip["label"] == "num"]
        self.assertEqual(numbers[0]["raw"], "10/16")

    def test_deleted_chip_is_restored(self):
        """用户把芯片删了 → 写回时按原文位置补回来（改不掉）。"""
        block_id = self.para_id()
        model = self.model(block_id)
        stripped = model["plain"].replace("\ue000P0\ue001", "")
        stripped = stripped.replace("\ue000P1\ue001", "")
        stripped = stripped.replace("\ue000P2\ue001", "")
        stripped = stripped.replace("\ue000P3\ue001", "")
        wb.save_block(self.root, "sections/01-intro.tex", block_id, stripped)
        after = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("\\fact{A1}", after)
        self.assertIn("\\cite{knuth1984}", after)
        self.assertIn("\\ref{sec:two}", after)
        self.assertIn("10/16", after)

    def test_injected_fact_is_stripped(self):
        """正文里新写的 \\fact{B9} 被剥掉（不许凭空造账本绑定）。"""
        block_id = self.para_id()
        model = self.model(block_id)
        edited = model["plain"].replace("开臂解出", "开臂解出 \\fact{B9}")
        result = wb.save_block(self.root, "sections/01-intro.tex", block_id, edited)
        after = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertNotIn("\\fact{B9}", after)
        self.assertTrue(result["warnings"])

    def test_backup_is_written_next_to_the_file(self):
        """每次保存前留一个同目录 .bak（覆盖旧的，不堆叠）。"""
        block_id = self.para_id()
        model = self.model(block_id)
        before = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        wb.save_block(self.root, "sections/01-intro.tex", block_id,
                      model["plain"].replace("开臂解出", "开臂解出X"))
        bak = self.root / "sections" / "01-intro.tex.bak"
        self.assertTrue(bak.is_file())
        self.assertEqual(bak.read_text(encoding="utf-8"), before)
        # 再存一次：.bak 仍是「上一次保存前」的内容，不堆叠
        wb.save_block(self.root, "sections/01-intro.tex", block_id,
                      model["plain"].replace("开臂解出", "开臂解出Y"))
        self.assertTrue(bak.is_file())
        self.assertEqual(len(list((self.root / "sections").glob("*.bak"))), 1)

    def test_atomic_write_keeps_permissions(self):
        """原子写保留原文件权限，且不留 .tmp 残骸。"""
        target = self.root / "sections" / "01-intro.tex"
        os.chmod(target, 0o640)
        wb.atomic_write(target, target.read_text(encoding="utf-8"))
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list((self.root / "sections").glob("*.tmp-*")), [])

    def test_unbalanced_braces_are_rejected(self):
        """写坏了的花括号不许落盘。"""
        block_id = self.para_id()
        with self.assertRaises(Exception):
            wb.save_block(self.root, "sections/01-intro.tex", block_id, "开臂 {解出")
        after = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("\\fact{A1}", after)


# --------------------------------------------------------------------------
# 2/3. 章节管理：调序 / 删除 / 新建
# --------------------------------------------------------------------------

class AssemblyTest(WriteBase):
    def test_assembly_lists_sections_in_order(self):
        assembly = wb.read_assembly(self.root)
        rels = [entry["rel"] for entry in assembly["entries"]]
        self.assertEqual(rels, ["sections/01-intro.tex", "sections/02-method.tex"])

    def test_move_rewrites_main_tex(self):
        """调序：main.tex 的装配顺序真的换了，且留 .bak。"""
        result = wb.move_section(self.root, "sections/02-method.tex", "up")
        self.assertTrue(result["moved"])
        main = (self.root / "main.tex").read_text(encoding="utf-8")
        self.assertLess(main.index("sections/02-method"), main.index("sections/01-intro"))
        self.assertTrue((self.root / "main.tex.bak").is_file())
        rels = [e["rel"] for e in wb.read_assembly(self.root)["entries"]]
        self.assertEqual(rels, ["sections/02-method.tex", "sections/01-intro.tex"])

    def test_delete_moves_file_into_attic(self):
        """删除：从装配移除 + 文件挪到 sections/attic/（不真删）。"""
        result = wb.delete_section(self.root, "sections/02-method.tex")
        self.assertTrue(result["moved"])
        attic = self.root / "sections" / "attic" / "02-method.tex"
        self.assertTrue(attic.is_file())
        self.assertFalse((self.root / "sections" / "02-method.tex").exists())
        main = (self.root / "main.tex").read_text(encoding="utf-8")
        self.assertNotIn("sections/02-method", main)
        rels = [e["rel"] for e in wb.read_assembly(self.root)["entries"]]
        self.assertEqual(rels, ["sections/01-intro.tex"])

    def test_create_section_writes_file_and_assembly(self):
        """新建：建 sections/NN-slug.tex ＋ 挂进 main.tex。"""
        result = wb.create_section(self.root, "实验设置", slug="setup")
        target = self.root / "sections" / "03-setup.tex"
        self.assertTrue(target.is_file())
        self.assertIn("\\section{实验设置}", target.read_text(encoding="utf-8"))
        main = (self.root / "main.tex").read_text(encoding="utf-8")
        self.assertIn("sections/03-setup", main)
        rels = [e["rel"] for e in wb.read_assembly(self.root)["entries"]]
        self.assertIn("sections/03-setup.tex", rels)
        self.assertTrue(result["assembled"])


# --------------------------------------------------------------------------
# 4/5. 项目新建与 toml 往返
# --------------------------------------------------------------------------

class ProjectCreateTest(WriteBase):
    def test_create_project_skeleton(self):
        """新建项目：目录骨架 + factscribe.toml 最小合法内容 + [workbench]。"""
        result = wb.create_paper_project(self.tmp, slug="my-paper", title="我的论文",
                                         langs=["en"], project_dir="papers/my-paper")
        target = self.tmp / "my-paper"
        self.assertTrue((target / "factscribe.toml").is_file())
        self.assertTrue((target / "sections").is_dir())
        self.assertTrue((target / "facts").is_dir())
        self.assertTrue((target / "README.md").is_file())
        self.assertTrue((target / "main.tex").is_file())
        bench = wb.workbench_config(target)
        self.assertEqual(bench["project_dir"], "papers/my-paper")
        self.assertEqual(bench["reports_dir"], "papers/my-paper/reports")
        self.assertEqual(bench["lang"], "en")
        self.assertEqual(len(result["created"]), 1)

    def test_created_project_shows_up_in_the_project_list(self):
        wb.create_paper_project(self.tmp, slug="listed", title="上榜论文")
        projects = load_projects(self.tmp)
        ids = [p["id"] for p in projects]
        self.assertIn("listed", ids)

    def test_zh_disk_gets_its_own_directory(self):
        result = wb.create_paper_project(self.tmp, slug="duo", title="双语论文",
                                         langs=["en", "zh"])
        names = sorted(Path(p).name for p in result["created"])
        self.assertEqual(names, ["duo", "duo-zh"])

    def test_toml_round_trip_keeps_other_tables(self):
        """改 [workbench] 表 → 读回来还是那个值；[project] 表一个字不动。"""
        target = self.root
        wb.save_workbench_config(target, {"project_dir": "papers/x",
                                          "reports_dir": "papers/x/reports"})
        bench = wb.workbench_config(target)
        self.assertEqual(bench["project_dir"], "papers/x")
        self.assertEqual(bench["reports_dir"], "papers/x/reports")
        text = (target / "factscribe.toml").read_text(encoding="utf-8")
        self.assertIn('title = "写回测试"', text)
        self.assertIn('sections = "sections/*.tex"', text)

    def test_update_project_changes_title_only(self):
        result = wb.update_paper_project(self.root, title="改了标题",
                                          reports_dir="papers/xx/reports")
        self.assertIn("title", result["changed"])
        text = (self.root / "factscribe.toml").read_text(encoding="utf-8")
        self.assertIn('title = "改了标题"', text)
        bench = wb.workbench_config(self.root)
        self.assertEqual(bench["reports_dir"], "papers/xx/reports")


# --------------------------------------------------------------------------
# 6. HTTP 端：写接口
# --------------------------------------------------------------------------

class HttpWriteTest(WriteBase):
    def setUp(self):
        super().setUp()
        from factscribe.workbench.server import create_server

        self.server, self.index = create_server(self.tmp, port=0, ttl=0)
        self.port = self.server.server_address[1]
        self.thread = None
        import threading
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()

    def url(self, path: str) -> str:
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def get(self, path: str) -> dict:
        with urllib.request.urlopen(self.url(path), timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post(self, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            self.url(path), data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read().decode("utf-8"))

    def test_edit_endpoint_writes_back(self):
        projects = self.get("/api/projects")["projects"]
        project = projects[0]
        disk = project["disks"][0]["id"]
        blocks = self.get("/api/disk/%s/%s/sections" % (project["id"], disk))["blocks"]
        block = next(b for b in blocks if b["kind"] == "para")
        model = self.get("/api/disk/%s/%s/block/%s" % (project["id"], disk, block["id"]))
        edited = model["plain"].replace("开臂解出", "开臂解出了")
        result = self.post("/api/disk/%s/%s/edit" % (project["id"], disk),
                           {"file": block["file"], "block": block["id"],
                            "text": edited})
        self.assertTrue(result["ok"])
        after = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("开臂解出了 10/16\\fact{A1}", after)
        self.assertTrue((self.root / "sections" / "01-intro.tex.bak").is_file())

    def test_toc_endpoints(self):
        projects = self.get("/api/projects")["projects"]
        project = projects[0]
        disk = project["disks"][0]["id"]
        base = "/api/disk/%s/%s" % (project["id"], disk)
        assembly = self.get(base + "/assembly")
        self.assertEqual(len(assembly["entries"]), 2)
        moved = self.post(base + "/toc/move",
                          {"file": "sections/02-method.tex", "direction": "up"})
        self.assertTrue(moved["ok"])
        created = self.post(base + "/toc/create", {"title": "新章节", "slug": "new"})
        self.assertTrue(created["ok"])
        self.assertIn("sections/03-new", (self.root / "main.tex").read_text(encoding="utf-8"))
        deleted = self.post(base + "/toc/delete", {"file": "sections/03-new.tex"})
        self.assertTrue(deleted["ok"])
        self.assertTrue((self.root / "sections" / "attic" / "03-new.tex").is_file())

    def test_project_new_endpoint_creates_skeleton(self):
        result = self.post("/api/project/new",
                            {"title": "网页新建", "slug": "web-made", "langs": ["en"]})
        self.assertTrue(result["ok"])
        target = self.tmp / "web-made"
        self.assertTrue((target / "factscribe.toml").is_file())
        self.assertTrue((target / "sections").is_dir())
        self.assertTrue((target / "facts").is_dir())
        self.assertTrue((target / "README.md").is_file())
        ids = [p["id"] for p in self.get("/api/projects")["projects"]]
        self.assertIn("web-made", ids)

    def test_write_outside_root_is_refused(self):
        result = self.post("/api/project/new",
                            {"title": "越界", "slug": "../escape", "langs": ["en"]})
        self.assertFalse(result.get("ok", False))


# --------------------------------------------------------------------------
# 4. 写回保真（段二验收打回）：保护面残渣回归
# --------------------------------------------------------------------------

#: 验收打回的用例原文：两行一行散文一行待改，尾部有转义百分号 `\%`。
VERBATIM_TEX = """\\section{逐字保真}

解决 10 道\\fact{A5} 题，正确率 56.25\\%，见 \\cite{key2024}。
这是第二句话，将被修改。
"""

#: A5 的 value＝"10"：正文里的 10 因此是「已绑定数字令牌」（保护面）。
VERBATIM_FACTS = """[[fact]]
id = "A5"
claim = "解出"
value = "10"
source = "results/data.md"
source_sha256 = "%s"
locator = "汇总表"
""" % ("0" * 64)


class VerbatimFidelityTest(WriteBase):
    """写回必须字节级保真：保护面残渣回归（段二验收打回）。

    打回用例：段落两行，第一行含 `\\fact{}`、绑定数字、`\\%` 与 `\\cite{}`；
    客户端把第一行**原样**回写（raw LaTeX，不是占位符）时，旧实现把原样
    回写的保护面当成「凭空新写」剥掉，再把原文保护面补回来 → 写出重复内容
    （残渣 `%，见 。`）。修法：原样回写逐字相同就认回来，只剥真正新写的。
    """

    REL = "sections/03-verbatim.tex"

    def setUp(self):
        super().setUp()
        (self.root / self.REL).write_text(VERBATIM_TEX, encoding="utf-8")
        (self.root / "facts" / "02-verbatim.toml").write_text(
            VERBATIM_FACTS, encoding="utf-8")

    def original(self) -> str:
        return (self.root / self.REL).read_text(encoding="utf-8")

    def para(self) -> dict:
        blocks = disk_sections(self.root)["blocks"]
        hits = [b for b in blocks
                if b.get("file") == self.REL and b["kind"] == "para"]
        return hits[0]

    def model(self, block: dict) -> dict:
        return wb.editable_model(self.root, wb.Block(
            file=self.REL, block_id=block["id"], kind=block["kind"],
            start=block["start"], end=block["end"], raw=block["raw"]))

    def test_1_verbatim_resubmit_is_byte_identical(self):
        """① 保护面原样重提交：除被改的散文行外逐字节一致，零残渣。"""
        block = self.para()
        submitted = ("解决 10 道\\fact{A5} 题，正确率 56.25\\%，见 \\cite{key2024}。\n"
                     "这是第二句话，已被工作台改写。")
        result = wb.save_block(self.root, self.REL, block["id"], submitted)
        after = self.original()
        expected = VERBATIM_TEX.replace("这是第二句话，将被修改。",
                                        "这是第二句话，已被工作台改写。")
        self.assertEqual(after, expected)
        self.assertEqual(result["warnings"], [])
        # 零残渣：每个保护面各一次，数字不被复制
        self.assertEqual(after.count("\\fact{A5}"), 1)
        self.assertEqual(after.count("\\cite{key2024}"), 1)
        self.assertEqual(after.count("解决 10 道"), 1)
        self.assertNotIn("，见 。", after)

    def test_2_moved_protected_surface_follows_client_order(self):
        """② 保护面换位置：跟着客户端走，只留一处，无残渣。"""
        block = self.para()
        submitted = ("解决 10 道\\fact{A5} 题，正确率 56.25\\%。\n"
                     "这是第二句话，已被工作台改写。见 \\cite{key2024}")
        wb.save_block(self.root, self.REL, block["id"], submitted)
        after = self.original()
        self.assertEqual(after.count("\\cite{key2024}"), 1)
        self.assertEqual(after.count("\\fact{A5}"), 1)
        self.assertEqual(after.count("解决 10 道"), 1)
        # 引用确实挪到了段尾，旧位置不再留残渣
        self.assertNotIn("，见 \\cite{key2024}", after)
        self.assertIn("已被工作台改写。见 \\cite{key2024}", after)
        self.assertLess(after.index("\\fact{A5}"), after.index("\\cite{key2024}"))

    def test_3_deleted_protected_surface_is_restored(self):
        """③ 保护面被删除：按原文位置补回，有告警，无残渣。"""
        block = self.para()
        model = self.model(block)
        cite_chip = [c for c in model["chips"] if c["label"] == "cite"][0]
        stripped = model["plain"].replace("\ue000P%d\ue001" % cite_chip["i"], "")
        result = wb.save_block(self.root, self.REL, block["id"], stripped)
        after = self.original()
        self.assertEqual(after.count("\\cite{key2024}"), 1)
        self.assertEqual(after.count("\\fact{A5}"), 1)
        self.assertEqual(after.count("解决 10 道"), 1)
        # 补回到原文位置（不是段尾）
        self.assertIn("56.25\\%，见 \\cite{key2024}。", after)
        self.assertTrue(any("补回" in w for w in result["warnings"]), result["warnings"])

    def test_4_duplicated_protected_surface_is_deduplicated(self):
        """④ 保护面被复制两份：只留一份，有告警，无残渣。"""
        block = self.para()
        model = self.model(block)
        cite_chip = [c for c in model["chips"] if c["label"] == "cite"][0]
        token = "\ue000P%d\ue001" % cite_chip["i"]
        duplicated = model["plain"].replace(token, token + token)
        result = wb.save_block(self.root, self.REL, block["id"], duplicated)
        after = self.original()
        self.assertEqual(after.count("\\cite{key2024}"), 1)
        self.assertEqual(after.count("\\fact{A5}"), 1)
        self.assertEqual(after.count("解决 10 道"), 1)
        self.assertTrue(any("复制" in w for w in result["warnings"]), result["warnings"])

        # 原样（raw）抄回时抄两份也一样：只留一份
        raw_dup = ("解决 10 道\\fact{A5} 题，正确率 56.25\\%，见 \\cite{key2024}。\n"
                   "这是第二句话，已被工作台改写。\\cite{key2024}")
        wb.save_block(self.root, self.REL, block["id"], raw_dup)
        after2 = self.original()
        self.assertEqual(after2.count("\\cite{key2024}"), 1)
        self.assertEqual(after2.count("\\fact{A5}"), 1)
        self.assertEqual(after2.count("解决 10 道"), 1)


if __name__ == "__main__":
    unittest.main()
