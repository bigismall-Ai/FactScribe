# -*- coding: utf-8 -*-
"""tests/test_workbench_stage6.py —— 工作台段六：段落三动作 ＋ AI 标记块 ＋ 两档模式。

覆盖三组（段六交付自查项 a / e）：

1. **段落三动作**（续写／改写／提问）：都走 `/api/chat`，`action` 字段区分，
   带段落引用上下文；后端不可达时降级口径不变（首行「模拟回答（未接模型）」）。
2. **写进稿**：以 AI 标记块插到那一段之后——**标记在 .tex 里、块与正文分离**，
   用户可再编辑、可删除，不自动混进正文。
3. **两档模式**（聊想法／写论文）：系统提示必须不同（用假后端抓真实请求）。
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench import ai, write as wb             # noqa: E402
from factscribe.workbench.projects import disk_sections      # noqa: E402
from factscribe.workbench.server import create_server       # noqa: E402

BS = chr(92)

CONFIG_TOML = """[project]
title = "段六测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\begin{document}
\\maketitle
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

ANSWER = "这是来自真后端的回答：续写如下。"


class _FakeBackend:
    """冒充 vLLM 的假后端：把真实收到的请求存下来。"""

    def __init__(self, answer: str = ANSWER) -> None:
        self.answer = answer
        self.requests: list[dict] = []
        self._server = None
        self._thread = None

    def start(self) -> str:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # noqa: D102
                pass

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except ValueError:
                    payload = {}
                outer.requests.append(payload)
                body = json.dumps({
                    "id": "chatcmpl-fake", "model": payload.get("model", "?"),
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant",
                                             "content": outer.answer}}],
                }, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()
        host, port = self._server.server_address[:2]
        return "http://%s:%d/v1" % (host, port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def system_texts(self) -> list[str]:
        """这一轮请求里的所有 system 消息。"""
        out: list[str] = []
        for request in self.requests:
            for message in request.get("messages", []):
                if message.get("role") == "system":
                    out.append(str(message.get("content") or ""))
        return out


def _make_disk(root: Path, name: str = "paper") -> Path:
    disk = root / name
    (disk / "sections").mkdir(parents=True)
    (disk / "facts").mkdir(parents=True)
    (disk / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (disk / "refs.bib").write_text("@article{knuth1984,\n  title={x}\n}\n",
                                   encoding="utf-8")
    (disk / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (disk / "sections" / "01-intro.tex").write_text(INTRO_TEX, encoding="utf-8")
    (disk / "sections" / "02-method.tex").write_text(METHOD_TEX, encoding="utf-8")
    return disk


def _paragraph(disk: Path, file: str = "sections/01-intro.tex") -> dict:
    for block in disk_sections(disk)["blocks"]:
        if block["kind"] == "para" and block.get("file") == file:
            return block
    raise AssertionError("这一段没找到：%s" % file)


class ParagraphActionTests(unittest.TestCase):
    """段落三动作：都走 /api/chat，action 字段区分。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.backend = _FakeBackend()
        self.base_url = self.backend.start()
        (self.disk / "workbench.toml").write_text(
            '[ai]\nbase_url = "%s"\nmodel = "qwen"\n' % self.base_url,
            encoding="utf-8")
        self.addCleanup(self.backend.stop)
        self.addCleanup(self._tmp.cleanup)

    def _chat(self, action: str, mode: str = "paper") -> dict:
        return ai.chat(self.disk, [{"role": "user", "content": "干活的"}],
                       quote={"text": "开臂解出 10/16。", "section": "引言"},
                       mode=mode, action=action)

    def test_three_actions_return_reply(self):
        for action in ("continue", "rewrite", "ask"):
            result = self._chat(action)
            self.assertTrue(result["ok"], action)
            self.assertFalse(result["fallback"], action)
            self.assertIn(ANSWER, result["reply"])

    def test_action_field_is_echoed(self):
        for action in ("continue", "rewrite", "ask"):
            self.assertEqual(self._chat(action)["action"], action)

    def test_each_action_has_its_own_system_prompt(self):
        self._chat("continue")
        self._chat("rewrite")
        systems = self.backend.system_texts()
        self.assertTrue(any("续写" in text for text in systems))
        self.assertTrue(any("改写" in text for text in systems))

    def test_quote_context_is_sent(self):
        self._chat("continue")
        systems = self.backend.system_texts()
        self.assertTrue(any("开臂解出 10/16" in text for text in systems))

    def test_two_modes_use_different_system_prompts(self):
        idea = ai.IDEA_SYSTEM_PROMPT
        paper = ai.PAPER_SYSTEM_PROMPT
        self.assertNotEqual(idea, paper)
        self.assertEqual(ai.MODE_PROMPTS["idea"], idea)
        self.assertEqual(ai.MODE_PROMPTS["paper"], paper)
        # 两档的落点不同：聊想法讲「先想清楚」，写论文讲「围着当前稿」。
        self.assertIn("想清楚", idea)
        self.assertIn("当前稿件", paper)
        self._chat("ask", mode="idea")
        self._chat("ask", mode="paper")
        systems = self.backend.system_texts()
        joined = "\n".join(systems)
        self.assertIn(idea, joined)
        self.assertIn(paper, joined)

    def test_unreachable_backend_keeps_fallback_contract(self):
        (self.disk / "workbench.toml").write_text(
            '[ai]\nbase_url = "http://127.0.0.1:9/v1"\nmodel = "qwen"\n',
            encoding="utf-8")
        result = self._chat("continue")
        self.assertFalse(result["ok"])
        self.assertTrue(result["fallback"])
        self.assertTrue(result["reply"].startswith(ai.FALLBACK_MARK))


class AiDraftBlockTests(unittest.TestCase):
    """写进稿：AI 标记块 ＋ 与正文分离 ＋ 可编辑可删。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.addCleanup(self._tmp.cleanup)

    def test_insert_writes_marker_into_tex(self):
        para = _paragraph(self.disk)
        result = wb.insert_ai_draft(self.disk, para["file"], para["id"],
                                    "这是 AI 给的续写。")
        self.assertTrue(result["ok"])
        text = (self.disk / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("FACTSCRIBE-AI-DRAFT-BEGIN", text)
        self.assertIn("FACTSCRIBE-AI-DRAFT-END", text)
        self.assertIn("这是 AI 给的续写。", text)

    def test_draft_lands_after_the_paragraph(self):
        para = _paragraph(self.disk)
        wb.insert_ai_draft(self.disk, para["file"], para["id"], "AI 草稿正文。")
        text = (self.disk / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        body_at = text.index("开臂解出 10/16")
        draft_at = text.index("AI 草稿正文。")
        self.assertLess(body_at, draft_at)

    def test_draft_is_a_separate_block_not_body_text(self):
        para = _paragraph(self.disk)
        wb.insert_ai_draft(self.disk, para["file"], para["id"], "AI 草稿正文。")
        blocks = disk_sections(self.disk)["blocks"]
        kinds = [b["kind"] for b in blocks]
        self.assertIn("ai_draft", kinds)
        # 正文那一段没被草稿污染。
        body = [b for b in blocks if b["kind"] == "para"][0]
        self.assertNotIn("AI 草稿正文", body["raw"])
        self.assertIn("10/16", body["raw"])

    def test_draft_block_has_badge_html(self):
        para = _paragraph(self.disk)
        wb.insert_ai_draft(self.disk, para["file"], para["id"], "AI 草稿正文。")
        blocks = disk_sections(self.disk)["blocks"]
        draft = [b for b in blocks if b["kind"] == "ai_draft"][0]
        self.assertIn("aidraft", draft["html"])
        self.assertIn("AI 草稿正文", draft["html"])

    def test_draft_can_be_edited_again(self):
        para = _paragraph(self.disk)
        inserted = wb.insert_ai_draft(self.disk, para["file"], para["id"],
                                      "AI 草稿正文。")
        model = wb.editable_model(
            self.disk, wb.find_block(self.disk, para["file"], inserted["block"]))
        wb.save_block(self.disk, para["file"], inserted["block"],
                      model["plain"] + " 再补一句。")
        text = (self.disk / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("再补一句。", text)
        # 标记行没丢。
        self.assertIn("FACTSCRIBE-AI-DRAFT-BEGIN", text)
        self.assertEqual(text.count("FACTSCRIBE-AI-DRAFT-BEGIN"), 1)

    def test_draft_can_be_deleted(self):
        para = _paragraph(self.disk)
        inserted = wb.insert_ai_draft(self.disk, para["file"], para["id"],
                                      "AI 草稿正文。")
        wb.delete_ai_draft(self.disk, para["file"], inserted["block"])
        text = (self.disk / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertNotIn("FACTSCRIBE-AI-DRAFT-BEGIN", text)
        self.assertNotIn("AI 草稿正文", text)
        # 别的段落一个字没动。
        self.assertIn("开臂解出 10/16", text)

    def test_insert_leaves_backup(self):
        para = _paragraph(self.disk)
        target = self.disk / "sections" / "01-intro.tex"
        before = target.read_text(encoding="utf-8")
        result = wb.insert_ai_draft(self.disk, para["file"], para["id"], "AI 草稿。")
        backup = Path(result["backup"])
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_text(encoding="utf-8"), before)

    def test_insert_refuses_ledger_file(self):
        para = _paragraph(self.disk)
        with self.assertRaises(Exception):
            wb.insert_ai_draft(self.disk, "facts/ledger.toml", para["id"], "x")

    def test_insert_refuses_path_escape(self):
        para = _paragraph(self.disk)
        with self.assertRaises(Exception):
            wb.insert_ai_draft(self.disk, "../../etc/passwd", para["id"], "x")

    def test_delete_refuses_non_draft_block(self):
        para = _paragraph(self.disk)
        with self.assertRaises(Exception):
            wb.delete_ai_draft(self.disk, para["file"], para["id"])

    def test_percent_in_draft_is_escaped(self):
        para = _paragraph(self.disk)
        wb.insert_ai_draft(self.disk, para["file"], para["id"], "提升了 50% 的准确率。")
        text = (self.disk / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn(r"50\%", text)


class DraftEndpointTests(unittest.TestCase):
    """HTTP 全链：写进稿 ＋ 删草稿块。"""

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
        with urllib.request.urlopen(self.base + path, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))

    def _post(self, path, body):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_insert_endpoint_writes_marker(self):
        sections = self._get("/api/disk/paper/paper/sections")
        para = [b for b in sections["blocks"] if b["kind"] == "para"][0]
        status, data = self._post("/api/disk/paper/paper/draft/insert",
                                  {"file": para["file"], "block": para["id"],
                                   "text": "这是写进稿的 AI 草稿。"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        text = (self.root / "paper" / "sections" / "01-intro.tex").read_text(
            encoding="utf-8")
        self.assertIn("FACTSCRIBE-AI-DRAFT-BEGIN", text)
        self.assertIn("这是写进稿的 AI 草稿。", text)

    def test_insert_endpoint_requires_text(self):
        sections = self._get("/api/disk/paper/paper/sections")
        para = [b for b in sections["blocks"] if b["kind"] == "para"][0]
        status, data = self._post("/api/disk/paper/paper/draft/insert",
                                  {"file": para["file"], "block": para["id"]})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])

    def test_delete_endpoint_removes_block(self):
        sections = self._get("/api/disk/paper/paper/sections")
        para = [b for b in sections["blocks"] if b["kind"] == "para"][0]
        _, inserted = self._post("/api/disk/paper/paper/draft/insert",
                                  {"file": para["file"], "block": para["id"],
                                   "text": "待删的草稿。"})
        status, data = self._post("/api/disk/paper/paper/draft/delete",
                                  {"file": para["file"], "block": inserted["block"]})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        text = (self.root / "paper" / "sections" / "01-intro.tex").read_text(
            encoding="utf-8")
        self.assertNotIn("FACTSCRIBE-AI-DRAFT-BEGIN", text)

    def test_chat_endpoint_accepts_action(self):
        status, data = self._post("/api/chat",
                                  {"project": "paper", "disk": "paper",
                                   "messages": [{"role": "user", "content": "续写"}],
                                   "quote": {"text": "开臂解出 10/16。"},
                                   "action": "continue", "mode": "paper"})
        self.assertEqual(status, 200)
        self.assertEqual(data["action"], "continue")
        self.assertEqual(data["mode"], "paper")


if __name__ == "__main__":
    unittest.main()
