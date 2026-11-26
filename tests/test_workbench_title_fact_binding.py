# -*- coding: utf-8 -*-
"""tests/test_workbench_title_fact_binding.py —— 标题/章节名 与 事实绑定的写侧。

三组能力（各走**独立通道**，不碰 /edit 的「散文＋token」写回）：

1. **改章节名**（rename_section）：只动 \\section{…} 里那一段，文件里其余
   字节一字不改；指纹闸对不上就拒写（BLOCK_STALE）。
2. **改论文标题**（set_disk_title）：写的就是封面读的那一条 \\title 命令
   （读侧与写侧同源：projects.title_command_span）。
3. **插入事实**（insert_fact_binding）：数字只能来自事实账，且必须过既有
   value 硬闸（factscribe/valuecheck.py 的 check_value_in_source）。

外加一条回归锁：**块偏移不许被环境标记截断**（段落里有 \\begin{table} 时，
块原文仍是完整的一段——修之前会被截断在半截命令上）。

跑法（仓根）：python3 -m pytest tests/test_workbench_title_fact_binding.py -q
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

from factscribe.config import ConfigError                    # noqa: E402
from factscribe.workbench import write as wb                  # noqa: E402
from factscribe.workbench.projects import (disk_meta,         # noqa: E402
                                            disk_sections, render_tex)
from factscribe.workbench.server import create_server        # noqa: E402

CONFIG_TOML = """[project]
title = "标题与绑定测试"
authors = ["tester"]
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\title{原始标题 \\\\ 原始副标题}
\\author{tester}
\\begin{document}
\\input{sections/01-intro}
\\end{document}
"""

INTRO_TEX = """\\section{引言}

开臂在 16 道题里解决 10 道，对比臂解决 8 道。
"""

TABLE_TEX = """\\section{带表的节}

\\begin{table}[t]
\\centering
\\begin{tabular}{lcc}
\\hline
arm & resolved & total \\\\
\\hline
open   & 10 & 16 \\\\
\\hline
\\end{tabular}
\\end{table}

表后面这段不能被吃掉：开臂解决 10 道\\fact{A1}。
"""

FACTS_TOML = """[[fact]]
id = "A1"
claim = "开臂解出"
value = "10"
source = "results/data.md"
locator = "汇总表"

[[fact]]
id = "A2"
claim = "时延"
value = "47.3"
source = "results/data.md"
locator = "时延行"

[[fact]]
id = "A9"
claim = "编的数"
value = "999"
source = "results/data.md"
locator = "没有这一行"
"""

DATA_MD = """# 原始产物（只读）

- open 臂 resolved 10 of 16
- 端到端时延 47.3 ms
"""


def make_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (root / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (root / "refs.bib").write_text("", encoding="utf-8")
    (root / "sections").mkdir(exist_ok=True)
    (root / "sections" / "01-intro.tex").write_text(INTRO_TEX, encoding="utf-8")
    (root / "sections" / "02-table.tex").write_text(TABLE_TEX, encoding="utf-8")
    (root / "facts").mkdir(exist_ok=True)
    (root / "facts" / "01-core.toml").write_text(FACTS_TOML, encoding="utf-8")
    (root / "results").mkdir(exist_ok=True)
    (root / "results" / "data.md").write_text(DATA_MD, encoding="utf-8")
    return root


class WriteBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-wb-title-"))
        self.root = make_project(self.tmp / "paper")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def blocks(self):
        return disk_sections(self.root)["blocks"]

    def heading(self, rel="sections/01-intro.tex"):
        return next(b for b in self.blocks()
                    if b["kind"] == "section" and b["file"] == rel)

    def para(self, rel="sections/01-intro.tex"):
        return next(b for b in self.blocks()
                    if b["kind"] == "para" and b["file"] == rel)


# --------------------------------------------------------------------------
# 1. 改章节名
# --------------------------------------------------------------------------
class RenameSectionTest(WriteBase):
    def test_only_title_command_changes(self):
        """只动 \\section{…} 里那一段；文件里其余字节一字不改。"""
        head = self.heading()
        path = self.root / "sections" / "01-intro.tex"
        before = path.read_text(encoding="utf-8")
        result = wb.rename_section(self.root, "sections/01-intro.tex",
                                   head["id"], "新的章节名")
        after = path.read_text(encoding="utf-8")
        self.assertTrue(result["changed"])
        self.assertEqual(result["before"], "\\section{引言}")
        self.assertEqual(result["after"], "\\section{新的章节名}")
        self.assertEqual(after, before.replace("\\section{引言}",
                                                 "\\section{新的章节名}"))

    def test_backup_left_behind(self):
        """落盘前留 .bak（与正文同一条）。"""
        head = self.heading()
        wb.rename_section(self.root, "sections/01-intro.tex", head["id"], "改名")
        bak = self.root / "sections" / "01-intro.tex.bak"
        self.assertTrue(bak.is_file())
        self.assertIn("\\section{引言}", bak.read_text(encoding="utf-8"))

    def test_fingerprint_gate_rejects(self):
        """指纹对不上 → 拒写（BLOCK_STALE），文件不动。"""
        head = self.heading()
        path = self.root / "sections" / "01-intro.tex"
        before = path.read_text(encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            wb.rename_section(self.root, "sections/01-intro.tex", head["id"],
                              "别的名字", expect_sha="deadbeefdeadbeef")
        self.assertEqual(getattr(ctx.exception, "code", ""), wb.BLOCK_STALE_CODE)
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_refuses_non_heading(self):
        """正文段不是标题 → 拒。"""
        para = self.para()
        with self.assertRaises(ConfigError) as ctx:
            wb.rename_section(self.root, "sections/01-intro.tex", para["id"], "x")
        self.assertEqual(getattr(ctx.exception, "code", ""), "SECTION_NOT_HEADING")

    def test_empty_title_rejected(self):
        """空标题不写盘。"""
        head = self.heading()
        with self.assertRaises(ConfigError) as ctx:
            wb.rename_section(self.root, "sections/01-intro.tex", head["id"], "   ")
        self.assertEqual(getattr(ctx.exception, "code", ""), "SECTION_TITLE_MISSING")


# --------------------------------------------------------------------------
# 2. 改论文标题
# --------------------------------------------------------------------------
class DiskTitleTest(WriteBase):
    def test_writes_title_command_and_meta_follows(self):
        """写的就是封面读的那一条 \\title 命令；meta 跟着走。"""
        meta = disk_meta(self.root)
        self.assertEqual(meta["name"], "原始标题")
        self.assertEqual(meta["subtitle"], "原始副标题")
        result = wb.set_disk_title(self.root, "新标题", "新副标题",
                                   expect_sha=meta["title_sha"])
        self.assertTrue(result["changed"])
        text = (self.root / "main.tex").read_text(encoding="utf-8")
        self.assertIn("\\title{新标题 \\\\ 新副标题}", text)
        again = disk_meta(self.root)
        self.assertEqual(again["name"], "新标题")
        self.assertEqual(again["subtitle"], "新副标题")

    def test_title_without_subtitle(self):
        """副标题留空 → 只写主标题。"""
        wb.set_disk_title(self.root, "只有主标题")
        text = (self.root / "main.tex").read_text(encoding="utf-8")
        self.assertIn("\\title{只有主标题}", text)
        self.assertEqual(disk_meta(self.root)["subtitle"], "")

    def test_fingerprint_gate_rejects(self):
        """指纹对不上 → 拒写。"""
        with self.assertRaises(ConfigError) as ctx:
            wb.set_disk_title(self.root, "x", "", expect_sha="deadbeefdeadbeef")
        self.assertEqual(getattr(ctx.exception, "code", ""), wb.BLOCK_STALE_CODE)
        self.assertIn("\\title{原始标题 \\\\ 原始副标题}",
                      (self.root / "main.tex").read_text(encoding="utf-8"))

    def test_other_files_untouched(self):
        """改标题只动入口 .tex；正文一个字不动。"""
        intro = self.root / "sections" / "01-intro.tex"
        before = intro.read_text(encoding="utf-8")
        wb.set_disk_title(self.root, "新标题")
        self.assertEqual(intro.read_text(encoding="utf-8"), before)


# --------------------------------------------------------------------------
# 3. 插入事实（数字只能来自账本 ＋ value 硬闸）
# --------------------------------------------------------------------------
class InsertFactBindingTest(WriteBase):
    def test_marker_lands_after_the_number(self):
        """正文里已有这个数字 → 只补标记，插在那个数字后面。"""
        para = self.para()
        result = wb.insert_fact_binding(self.root, "sections/01-intro.tex",
                                        para["id"], "A1", expect_sha=para["sha"])
        self.assertEqual(result["mode"], "marker")
        self.assertEqual(result["matched"], "10")
        text = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("解决 10\\fact{A1} 道", text)

    def test_value_mode_appends_when_number_absent(self):
        """正文里没有这个数字 → 连数字带标记插在段末（不编造位置）。"""
        para = self.para()
        result = wb.insert_fact_binding(self.root, "sections/01-intro.tex",
                                        para["id"], "A2", expect_sha=para["sha"])
        self.assertEqual(result["mode"], "value")
        text = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("47.3\\fact{A2}", text)

    def test_unknown_fact_rejected(self):
        """账上没有的事实 → 拒（不许凭空造）。"""
        para = self.para()
        with self.assertRaises(ConfigError) as ctx:
            wb.insert_fact_binding(self.root, "sections/01-intro.tex",
                                   para["id"], "NOPE")
        self.assertEqual(getattr(ctx.exception, "code", ""), "FACT_NOT_IN_LEDGER")

    def test_value_gate_rejects_number_not_in_source(self):
        """value 硬闸：数字必须真的在那件产物里（A9 的 999 不在产物里）。"""
        para = self.para()
        with self.assertRaises(ConfigError):
            wb.insert_fact_binding(self.root, "sections/01-intro.tex",
                                   para["id"], "A9")
        text = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertNotIn("999", text)

    def test_duplicate_binding_rejected(self):
        """同一段里已经有这条事实的标记 → 拒（不重复绑）。"""
        para = next(b for b in self.blocks()
                    if b["kind"] == "para" and b["file"] == "sections/02-table.tex")
        with self.assertRaises(ConfigError) as ctx:
            wb.insert_fact_binding(self.root, "sections/02-table.tex",
                                   para["id"], "A1")
        self.assertEqual(getattr(ctx.exception, "code", ""), "FACT_ALREADY_BOUND")

    def test_fingerprint_gate_rejects(self):
        """指纹对不上 → 拒写。"""
        para = self.para()
        before = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            wb.insert_fact_binding(self.root, "sections/01-intro.tex", para["id"],
                                   "A1", expect_sha="deadbeefdeadbeef")
        self.assertEqual(getattr(ctx.exception, "code", ""), wb.BLOCK_STALE_CODE)
        self.assertEqual((self.root / "sections" / "01-intro.tex")
                         .read_text(encoding="utf-8"), before)


# --------------------------------------------------------------------------
# 4. 回归锁：块偏移不许被环境标记截断
# --------------------------------------------------------------------------
class RenderSpanTest(WriteBase):
    def test_environment_does_not_truncate_block(self):
        """段落里有 \\begin{table} → 块原文仍是**完整**的一段。

        修之前：环境标记不进缓冲区，而块尾按「缓冲区长度」倒推 ——
        这一段会被截断在半截命令上（渲染少半句，写回也错位）。
        """
        text = (self.root / "sections" / "02-table.tex").read_text(encoding="utf-8")
        blocks = render_tex(text, stem="02-table", disk_root=self.root)
        para = next(b for b in blocks if b["kind"] == "para")
        self.assertIn("\\begin{table}[t]", para["raw"])
        self.assertIn("表后面这段不能被吃掉", para["raw"])
        self.assertEqual(para["raw"], text[para["start"]:para["end"]])


# --------------------------------------------------------------------------
# 5. HTTP 端点（真起服务，走真实协议路径）
# --------------------------------------------------------------------------
class EndpointTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-wb-title-api-"))
        self.paper = self.tmp / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", self.paper)
        self.server, self.index = create_server(str(self.tmp), port=0,
                                                state_dir=str(self.tmp / "state"))
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        data = self.get("/api/projects")
        project = (data.get("projects") or [])[0]
        self.project = project["id"]
        self.disk = (project.get("disks") or [])[0]["id"]
        self.addCleanup(self._teardown)

    def _teardown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, method="POST", data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_rename_endpoint(self):
        blocks = self.get("/api/disk/%s/%s/sections" % (self.project, self.disk))["blocks"]
        head = next(b for b in blocks if b["kind"] == "section")
        status, data = self.post("/api/disk/%s/%s/toc/rename" % (self.project, self.disk),
                                 {"file": head["file"], "block": head["id"],
                                  "title": "端点改名", "expect_sha": head["sha"]})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        self.assertIn("\\section{端点改名}",
                      (self.paper / head["file"]).read_text(encoding="utf-8"))

    def test_title_endpoint(self):
        meta = self.get("/api/disk/%s/%s/meta" % (self.project, self.disk))
        status, data = self.post("/api/disk/%s/%s/title" % (self.project, self.disk),
                                 {"title": "端点标题", "subtitle": "端点副标题",
                                  "expect_sha": meta.get("title_sha")})
        self.assertEqual(status, 200)
        again = self.get("/api/disk/%s/%s/meta" % (self.project, self.disk))
        self.assertEqual(again["name"], "端点标题")
        self.assertEqual(again["subtitle"], "端点副标题")

    def test_facts_endpoint_is_readonly_list(self):
        payload = self.get("/api/disk/%s/%s/facts" % (self.project, self.disk))
        self.assertEqual(payload.get("ok"), True)
        ids = [row.get("id") for row in payload.get("rows") or []]
        self.assertIn("A1", ids)

    def test_insert_endpoint_uses_ledger_number(self):
        blocks = self.get("/api/disk/%s/%s/sections" % (self.project, self.disk))["blocks"]
        # 样例盘里 01-intro 那段已经绑了 A1（重复绑会被拒）——挑没绑过的那段。
        para = next(b for b in blocks if b["kind"] == "para"
                    and b["file"] == "sections/02-results.tex")
        status, data = self.post("/api/disk/%s/%s/fact/insert" % (self.project, self.disk),
                                 {"file": para["file"], "block": para["id"],
                                  "fact": "A1", "expect_sha": para["sha"]})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("value"), "10/16")
        self.assertEqual(data.get("mode"), "value")
        self.assertIn("blocks", data)


if __name__ == "__main__":
    unittest.main()