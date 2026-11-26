# -*- coding: utf-8 -*-
"""tests/test_workbench_tokens.py —— 条目 43：DOM 即模型，token 服务端烤进渲染 html。

四案（本批验收自查项）：

1. **一致性**：同一块的 ``render_tex`` html 里 ``data-token`` 序号集合 ==
   ``editable_model`` 的 chips 序号集合（同一 block.raw、同一绑定值、同一
   scan 顺序）；摘要块与模型应答的 html 同一口径。
2. **指纹闸**：``save_block``/``save_abstract`` 的 ``expect_sha``——一致才存，
   不一致抛 ``BLOCK_STALE``；应答带新块 ``sha``。
3. **blocks 映射**：``/edit`` 应答带同文件**全部块**的新鲜渲染（带 token），
   兄弟段烤在 DOM 里的 token 在本轮保存后立刻刷新。
4. **sha 落账**：装配应答（disk_sections 的块、assembly 的条目）都带
   ``sha``（同款 sha256 前 16 位），前端存下供保存时带上。

测试纪律：全量无 PYTHONPATH 直跑；不动真论文目录。
"""
from __future__ import annotations

import json
import re
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

from factscribe.workbench import write as wb         # noqa: E402
from factscribe.workbench.projects import (          # noqa: E402
    TOKEN_RE, disk_sections, render_tex,
)

CONFIG_TOML = """[project]
title = "token 测试"
authors = ["tester"]
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\title{token 测试}
\\author{tester}
\\begin{abstract}
本盘用于条目 43 的 token 一致性验证。
\\end{abstract}
\\begin{document}
\\input{sections/01-intro}
\\input{sections/02-method}
\\end{document}
"""

INTRO_TEX = """\\section{引言}

开臂解出 10/16\\fact{A1}。方法与记号见 \\cite{knuth1984}，详见 \\ref{sec:two}。
对照臂的情形由第二章给出，其中 8 道题与账本同值。
"""

METHOD_TEX = """\\section{方法}

对比臂解出 8/16\\fact{A3}，设置见 \\ref{sec:method-setup}。
"""

FACTS_TOML = """[[fact]]
id = "A1"
claim = "开臂解出"
value = "10/16"
source = "results/data.md"
source_sha256 = "%s"
locator = "汇总表"

[[fact]]
id = "A3"
claim = "对比臂解出"
value = "8/16"
source = "results/data.md"
source_sha256 = "%s"
locator = "汇总表"
""" % ("0" * 64, "0" * 64)


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


def tokens_in(html: str) -> list[str]:
    """html 里 data-token 的序号集合（排序后返回）。"""
    return sorted(set(TOKEN_RE.findall(html)), key=int)


class TokenConsistencyTest(unittest.TestCase):
    """案①：渲染 html 的 data-token 序号集 == editable_model 的 chips 序号集。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factscribe-token-"))
        self.root = make_project(self.tmp / "paper")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_every_para_html_matches_model_chips(self):
        from factscribe.workbench.write import Block, editable_model

        for block in disk_sections(self.root)["blocks"]:
            if block["kind"] not in ("para", "abstract"):
                continue
            real = Block(file=block["file"], block_id=block["id"],
                         kind=block["kind"], start=block["start"],
                         end=block["end"], raw=block["raw"])
            model = editable_model(self.root, real)
            self.assertEqual(
                tokens_in(block["html"]),
                sorted({str(c["i"]) for c in model["chips"]}, key=int),
                "html 与模型的 token 序号没对齐：%s" % block["id"])
            self.assertEqual(block["sha"], model["sha"], "指纹没对齐")
            self.assertEqual(block["html"], model["html"], "模型 html 与渲染 html 不同源")

    def test_bound_numbers_are_tokened_in_html(self):
        """绑定数字在 html 里就是芯片（序号与模型同源），不再有裸数字两种态。"""
        blocks = [b for b in disk_sections(self.root)["blocks"]
                  if b["kind"] == "para" and b["file"] == "sections/01-intro.tex"]
        html = blocks[0]["html"]
        self.assertIn('title="10/16"', html)          # 绑定数字烤成了芯片
        self.assertGreaterEqual(len(tokens_in(html)), 4)  # num+fact+cite+ref 至少四枚

    def test_degraded_render_without_disk_context_still_tokens_commands(self):
        """没有盘上下文的调用点允许退化：命令类片段（fact/cite/ref/env）照编，
        紧跟 \\fact 的数字（规则一，不依赖账本）照编；账本同值数字（规则二）
        无账可对就不编——同一部署内该口径自身一致。"""
        blocks = render_tex("开臂解出 10/16\\fact{A1}，见 \\cite{k1}。另有 8/16 道同值。\n")
        para = next(b for b in blocks if b["kind"] == "para")
        self.assertIn('data-fact="A1"', para["html"])
        self.assertIn("[k1]", para["html"])
        self.assertIn('title="10/16"', para["html"])     # 规则一：紧跟 fact
        self.assertNotIn('title="8/16"', para["html"])   # 规则二需要账本


class ExpectShaGateTest(unittest.TestCase):
    """案②：expect_sha 指纹闸——一致才存，不一致 BLOCK_STALE。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factscribe-token-"))
        self.root = make_project(self.tmp / "paper")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _para(self) -> dict:
        blocks = [b for b in disk_sections(self.root)["blocks"]
                  if b["kind"] == "para" and b["file"] == "sections/01-intro.tex"]
        return blocks[0]

    def test_matching_sha_saves(self):
        from factscribe.workbench.write import Block, editable_model

        block = self._para()
        real = Block(file=block["file"], block_id=block["id"], kind="para",
                     start=block["start"], end=block["end"], raw=block["raw"])
        model = editable_model(self.root, real)
        result = wb.save_block(self.root, block["file"], block["id"],
                               model["plain"], expect_sha=model["sha"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["sha"], wb._short_sha(result["after"]))
        after = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("10/16\\fact{A1}", after)     # 保护面照旧

    def test_mismatched_sha_is_refused_with_block_stale(self):
        from factscribe.workbench.write import Block, editable_model
        from factscribe.config import ConfigError

        block = self._para()
        real = Block(file=block["file"], block_id=block["id"], kind="para",
                     start=block["start"], end=block["end"], raw=block["raw"])
        model = editable_model(self.root, real)
        # 另一处先改掉这一块（模拟别处已改）
        stale_text = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        (self.root / "sections" / "01-intro.tex").write_text(
            stale_text.replace("开臂解出", "别处改过"), encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            wb.save_block(self.root, block["file"], block["id"],
                          model["plain"], expect_sha=model["sha"])
        self.assertEqual(ctx.exception.code, "BLOCK_STALE")
        # 文件没被写坏：别处改的内容还在
        self.assertIn("别处改过",
                      (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8"))

    def test_empty_expect_sha_keeps_old_semantics(self):
        """不带 expect_sha ＝ 老语义（不设闸）；既有写回测试全绿的前提。"""
        block = self._para()
        result = wb.save_block(self.root, block["file"], block["id"],
                               block["raw"])
        self.assertTrue(result["ok"])

    def test_abstract_gate_and_sha(self):
        block = wb.abstract_block(self.root)
        model = wb.editable_model(self.root, block)
        result = wb.save_abstract(self.root, model["plain"],
                                  expect_sha=model["sha"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["sha"])
        with self.assertRaises(Exception) as ctx:
            wb.save_abstract(self.root, model["plain"], expect_sha="deadbeefdeadbeef")
        self.assertEqual(getattr(ctx.exception, "code", ""), "BLOCK_STALE")


class EditBlocksMappingTest(unittest.TestCase):
    """案③：/edit 应答带同文件全部块的新鲜渲染（带 token）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factscribe-token-"))
        self.root = make_project(self.tmp / "paper")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        from factscribe.workbench.server import create_server

        self.server, self.index = create_server(self.tmp, port=0, ttl=0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()

    def _get(self, path: str) -> dict:
        url = "http://127.0.0.1:%d%s" % (self.server.server_address[1], path)
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, body: dict):
        url = "http://127.0.0.1:%d%s" % (self.server.server_address[1], path)
        request = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_edit_response_has_fresh_blocks_for_the_same_file(self):
        blocks = self._get("/api/disk/paper/paper/sections")["blocks"]
        targets = [b for b in blocks if b["kind"] == "para"
                   and b["file"] == "sections/01-intro.tex"]
        self.assertGreaterEqual(len(targets), 1, "受试文件至少一段")
        first = targets[0]
        status, result = self._post("/api/disk/paper/paper/edit", {
            "file": first["file"], "block": first["id"],
            "text": first["raw"], "expect_sha": first["sha"],
        })
        self.assertEqual(status, 200)
        blocks_map = result.get("blocks") or {}
        self.assertIn(first["id"], blocks_map, "应答没带被存块的新 html")
        same_file = [b for b in blocks if b.get("file") == first["file"]
                     and b.get("html")]
        for block in same_file:
            self.assertIn(block["id"], blocks_map,
                          "同文件块 %s 没进刷新映射" % block["id"])
        other_file = next(b for b in blocks if b.get("file") != first["file"]
                          and b.get("html"))
        self.assertNotIn(other_file["id"], blocks_map, "别文件不该混进映射")
        # 映射里的 html 带 token 芯片
        self.assertTrue(all("data-token=" in h for h in blocks_map.values()))

    def test_stale_edit_returns_409_with_fresh_blocks(self):
        blocks = self._get("/api/disk/paper/paper/sections")["blocks"]
        first = next(b for b in blocks if b["kind"] == "para")
        status, result = self._post("/api/disk/paper/paper/edit", {
            "file": first["file"], "block": first["id"],
            "text": first["raw"], "expect_sha": "0123456789abcdef",
        })
        self.assertEqual(status, 409)
        self.assertEqual(result.get("code"), "BLOCK_STALE")
        self.assertIn("blocks", result)


class ShaOnPayloadsTest(unittest.TestCase):
    """案④：装配应答（disk_sections 的块、assembly 的条目）都带同款 sha。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factscribe-token-"))
        self.root = make_project(self.tmp / "paper")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_sections_blocks_carry_sha(self):
        for block in disk_sections(self.root)["blocks"]:
            self.assertTrue(block.get("sha"), "块 %s 没带 sha" % block["id"])
            self.assertEqual(block["sha"], wb._short_sha(block["raw"]))

    def test_assembly_entries_carry_sha(self):
        assembly = wb.read_assembly(self.root)
        self.assertEqual(len(assembly["entries"]), 2)
        for entry in assembly["entries"]:
            self.assertTrue(entry.get("sha"), "装配条目 %s 没带 sha" % entry["rel"])
            expect = wb._short_sha(
                (self.root / entry["rel"]).read_text(encoding="utf-8"))
            self.assertEqual(entry["sha"], expect)


if __name__ == "__main__":
    unittest.main()
