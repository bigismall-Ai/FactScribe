# -*- coding: utf-8 -*-
"""tests/test_workbench_proposal.py —— v2 提议单：AI 提议 → 人确认才写回。

覆盖八组：

1. **建单不碰正文**：提议单算完落状态目录，论文文件字节不变。
2. **提议单落在状态目录**：不在论文目录里（论文不因为有人提建议而变脏）。
3. **指纹闸**：建单时指纹不符 → BLOCK_STALE。
4. **确认才落盘**：确认后正文按保护链写回（\\fact{} 保留）＋留 .bak。
5. **拒绝不动纸**：拒绝后文件字节不变，提议单状态 rejected。
6. **过期拒写**：提议之后正文被别处改过 → 确认时 BLOCK_STALE，不覆盖。
7. **新写的绑定被剥**：提议里凭空写 \\fact{A9} → 落盘前剥掉并告警。
8. **草稿类提议**：kind=ai_draft 确认后落成独立草稿块。

外加：单号形状校验、重复确认拒、HTTP 面（建单→列表→确认→409）。
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

from factscribe.config import ConfigError                       # noqa: E402
from factscribe.workbench import proposal as pr                # noqa: E402
from factscribe.workbench import write as wb                   # noqa: E402
from factscribe.workbench.projects import disk_sections        # noqa: E402

CONFIG_TOML = """[project]
title = "提议单测试"
authors = ["tester"]
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\title{提议单测试}
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


class ProposalBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factscribe-wbprop-"))
        self.root = make_project(self.tmp / "paper")
        self.state = self.tmp / "state"
        self.state.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def para_id(self, rel: str = "sections/01-intro.tex", index: int = 0) -> str:
        blocks = disk_sections(self.root)["blocks"]
        hits = [b for b in blocks if b.get("file") == rel and b.get("kind") == "para"]
        return hits[index]["id"]

    def model(self, block_id: str, rel: str = "sections/01-intro.tex") -> dict:
        block = wb.find_block(self.root, rel, block_id)
        return wb.editable_model(self.root, block)

    def intro_text(self) -> str:
        return (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")

    def make_proposal(self, text: str = "", block_id: str = "",
                      kind: str = "block_edit", **kwargs) -> dict:
        rel = kwargs.pop("file", "sections/01-intro.tex")
        if not block_id:
            block_id = self.para_id(rel)
        if not text:
            model = self.model(block_id, rel)
            text = model["plain"].replace("开臂解出", "开臂终于解出")
        body = {"kind": kind, "file": rel, "block": block_id, "text": text}
        body.update(kwargs)
        return pr.create_proposal(self.state, "paper", "paper", self.root, body)


# --------------------------------------------------------------------------
# 1—3：建单阶段：只算不写
# --------------------------------------------------------------------------

class ProposalCreateTest(ProposalBase):
    def test_proposal_does_not_touch_the_paper(self):
        """建单之后章节文件字节不变——提议阶段只算不写。"""
        before = (self.root / "sections" / "01-intro.tex").read_bytes()
        self.make_proposal()
        after = (self.root / "sections" / "01-intro.tex").read_bytes()
        self.assertEqual(before, after)
        self.assertFalse((self.root / "sections" / "01-intro.tex.bak").exists())

    def test_proposal_lands_in_state_dir_not_paper(self):
        """提议单在状态目录里；论文目录不出现 proposals/。"""
        record = self.make_proposal()
        path = pr.proposal_path(self.state, record["id"])
        self.assertTrue(path.is_file())
        self.assertTrue(str(path).startswith(str(self.state)))
        self.assertFalse((self.root / "proposals").exists())
        self.assertFalse((self.root / "facts" / "proposals").exists())

    def test_proposal_carries_before_and_after(self):
        """提议单带着现状与「采纳后会落盘的那一份」。"""
        record = self.make_proposal()
        self.assertEqual(record["kind"], "block_edit")
        self.assertEqual(record["status"], "pending")
        self.assertIn("开臂解出", record["before_text"])
        self.assertIn("开臂终于解出", record["after_text"])
        self.assertEqual(len(record["before_sha"]), 16)
        self.assertNotEqual(record["before_text"], record["after_text"])

    def test_after_text_is_what_would_land(self):
        """after_text 与真写回的结果一致（所见即落盘）。"""
        record = self.make_proposal()
        applied = wb.apply_proposal(self.root, record)
        self.assertEqual(applied["after"], record["after_text"])

    def test_stale_expect_sha_is_rejected(self):
        """建单时指纹对不上 → BLOCK_STALE，不建单。"""
        with self.assertRaises(ConfigError) as ctx:
            self.make_proposal(expect_sha="0" * 16)
        self.assertEqual(getattr(ctx.exception, "code", ""), "BLOCK_STALE")
        self.assertEqual(pr.list_proposals(self.state), [])

    def test_new_fact_is_stripped_and_warned(self):
        """凭空写的 \fact{A9} 在落盘前被剥掉，并且有人被告知。"""
        model = self.model(self.para_id())
        text = model["plain"].replace("开臂解出", "开臂解出 \\fact{A9}")
        record = self.make_proposal(text=text)
        self.assertNotIn("\\fact{A9}", record["after_text"])
        self.assertTrue(record["warnings"])

    def test_empty_text_is_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            self.make_proposal(text="   ")
        self.assertEqual(getattr(ctx.exception, "code", ""), "PROPOSAL_TEXT_EMPTY")

    def test_unbalanced_braces_are_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            self.make_proposal(text="\\section{坏的")
        self.assertEqual(getattr(ctx.exception, "code", ""), "EDIT_UNBALANCED")

    def test_bad_id_shape_is_refused(self):
        with self.assertRaises(pr.ProposalError) as ctx:
            pr.proposal_path(self.state, "../../etc/passwd")
        self.assertEqual(getattr(ctx.exception, "code", ""), "PROPOSAL_ID_INVALID")


# --------------------------------------------------------------------------
# 4—6：确认阶段：人点头才落盘
# --------------------------------------------------------------------------

class ProposalApplyTest(ProposalBase):
    def test_confirm_writes_back_through_protection_chain(self):
        """确认后正文变了，\fact{} 与绑定数字原样保留，并留 .bak。"""
        record = self.make_proposal()
        applied = wb.apply_proposal(self.root, record)
        after = self.intro_text()
        self.assertIn("开臂终于解出 10/16\\fact{A1}", after)
        self.assertIn("\\cite{knuth1984}", after)
        self.assertTrue((self.root / "sections" / "01-intro.tex.bak").is_file())
        self.assertTrue(applied["ok"])

    def test_reject_leaves_paper_untouched(self):
        """拒绝之后论文一个字节都没动，提议单状态 rejected。"""
        record = self.make_proposal()
        before = (self.root / "sections" / "01-intro.tex").read_bytes()
        done = pr.resolve_proposal(self.state, record["id"], pr.STATUS_REJECTED)
        self.assertEqual(done["status"], "rejected")
        self.assertEqual(
            before, (self.root / "sections" / "01-intro.tex").read_bytes())

    def test_confirm_after_external_edit_is_blocked(self):
        """提议之后正文被别处改过 → 确认时 BLOCK_STALE，不覆盖。"""
        record = self.make_proposal()
        path = self.root / "sections" / "01-intro.tex"
        path.write_text(path.read_text(encoding="utf-8") + "\n别人加的一行。\n",
                        encoding="utf-8")
        changed = path.read_text(encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            wb.apply_proposal(self.root, record)
        self.assertEqual(getattr(ctx.exception, "code", ""), "BLOCK_STALE")
        self.assertEqual(changed, path.read_text(encoding="utf-8"))

    def test_double_resolve_is_refused(self):
        record = self.make_proposal()
        pr.resolve_proposal(self.state, record["id"], pr.STATUS_REJECTED)
        with self.assertRaises(pr.ProposalError) as ctx:
            pr.resolve_proposal(self.state, record["id"], pr.STATUS_APPLIED)
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         "PROPOSAL_ALREADY_RESOLVED")

    def test_ai_draft_proposal_lands_as_its_own_block(self):
        """kind=ai_draft：确认后落成独立草稿块，不混进正文。"""
        anchor = self.para_id()
        record = self.make_proposal(text="这是 AI 的一段回复。", block_id=anchor,
                                    kind="ai_draft")
        self.assertEqual(record["kind"], "ai_draft")
        applied = wb.apply_proposal(self.root, record)
        after = self.intro_text()
        self.assertIn("FACTSCRIBE-AI-DRAFT-BEGIN", after)
        self.assertIn("这是 AI 的一段回复。", after)
        self.assertTrue(applied["marker"].startswith("aidraft-"))


# --------------------------------------------------------------------------
# HTTP 面：建单 → 列表 → 确认 → 过期 409
# --------------------------------------------------------------------------

class HttpProposalTest(ProposalBase):
    def setUp(self):
        super().setUp()
        from factscribe.workbench.server import create_server

        self.server, self.index = create_server(self.tmp, port=0, ttl=0,
                                                 state_dir=str(self.state))
        self.port = self.server.server_address[1]
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

    def post(self, path: str, body: dict):
        request = urllib.request.Request(
            self.url(path), data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def first_disk(self):
        projects = self.get("/api/projects")["projects"]
        project = projects[0]
        return project["id"], project["disks"][0]["id"]

    def test_post_lists_then_confirms(self):
        project, disk = self.first_disk()
        blocks = self.get("/api/disk/%s/%s/sections" % (project, disk))["blocks"]
        block = next(b for b in blocks if b["kind"] == "para")
        model = self.get("/api/disk/%s/%s/block/%s"
                         % (project, disk, block["id"]))
        text = model["plain"].replace("开臂解出", "开臂终于解出")
        status, created = self.post("/api/disk/%s/%s/proposal" % (project, disk),
                                    {"file": block["file"], "block": block["id"],
                                     "text": text, "source": "mcp"})
        self.assertEqual(status, 200)
        pid = created["proposal"]["id"]
        listing = self.get("/api/disk/%s/%s/proposal" % (project, disk))
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["proposals"][0]["id"], pid)
        before = (self.root / "sections" / "01-intro.tex").read_bytes()
        status, confirmed = self.post(
            "/api/disk/%s/%s/proposal/%s/confirm" % (project, disk, pid), {})
        self.assertEqual(status, 200)
        self.assertTrue(confirmed["ok"])
        after = (self.root / "sections" / "01-intro.tex").read_bytes()
        self.assertNotEqual(before, after)

    def test_confirm_after_external_edit_returns_409(self):
        project, disk = self.first_disk()
        blocks = self.get("/api/disk/%s/%s/sections" % (project, disk))["blocks"]
        block = next(b for b in blocks if b["kind"] == "para")
        model = self.get("/api/disk/%s/%s/block/%s"
                         % (project, disk, block["id"]))
        text = model["plain"].replace("开臂解出", "开臂终于解出")
        status, created = self.post("/api/disk/%s/%s/proposal" % (project, disk),
                                    {"file": block["file"], "block": block["id"],
                                     "text": text})
        self.assertEqual(status, 200)
        pid = created["proposal"]["id"]
        path = self.root / "sections" / "01-intro.tex"
        path.write_text(path.read_text(encoding="utf-8") + "\n别人加的一行。\n",
                        encoding="utf-8")
        status, payload = self.post(
            "/api/disk/%s/%s/proposal/%s/confirm" % (project, disk, pid), {})
        self.assertEqual(status, 409)
        self.assertEqual(payload["code"], "BLOCK_STALE")

    def test_reject_marks_it_and_leaves_paper(self):
        project, disk = self.first_disk()
        blocks = self.get("/api/disk/%s/%s/sections" % (project, disk))["blocks"]
        block = next(b for b in blocks if b["kind"] == "para")
        model = self.get("/api/disk/%s/%s/block/%s"
                         % (project, disk, block["id"]))
        text = model["plain"].replace("开臂解出", "开臂终于解出")
        _, created = self.post("/api/disk/%s/%s/proposal" % (project, disk),
                               {"file": block["file"], "block": block["id"],
                                "text": text})
        pid = created["proposal"]["id"]
        before = (self.root / "sections" / "01-intro.tex").read_bytes()
        status, rejected = self.post(
            "/api/disk/%s/%s/proposal/%s/reject" % (project, disk, pid), {})
        self.assertEqual(status, 200)
        self.assertEqual(rejected["proposal"]["status"], "rejected")
        self.assertEqual(before,
                         (self.root / "sections" / "01-intro.tex").read_bytes())
