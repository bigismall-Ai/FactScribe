# -*- coding: utf-8 -*-
"""工作台段四：AI 对话适配层（假后端 socket 测）。

测三件要紧的事：

1. 真打一次 OpenAI 兼容后端（用本机假 socket 服务冒充 vLLM），拿到真回复；
2. 后端不可达 → **结构化降级**：`ok=False, fallback=True`，
   模拟回复**首行**必须是「模拟回答（未接模型）」——绝不静默造假；
3. 配置可配：项目级 `workbench.toml` 的 `[ai]` 节（base_url / model / api_key）。
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from factscribe.workbench import ai
from factscribe.workbench.server import create_server

REPO = Path(__file__).resolve().parents[1]
SAMPLES = [REPO / "examples" / "minimal", REPO / "fixtures" / "legal-demo"]

ANSWER = "这是来自真后端的回答：盲评对数是 10。"


class _FakeBackend:
    """冒充 vLLM 的假后端：OpenAI 兼容 `/v1/chat/completions`。"""

    def __init__(self, answer: str = ANSWER, status: int = 200) -> None:
        self.answer = answer
        self.status = status
        self.requests: list[dict] = []
        self.headers_seen: list[dict] = []
        self._server = None
        self._thread = None

    def start(self) -> str:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # noqa: D102 - 安静
                pass

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except ValueError:
                    payload = {"_raw": raw.decode("utf-8", "replace")}
                outer.requests.append(payload)
                outer.headers_seen.append(dict(self.headers))
                if outer.status != 200:
                    body = b'{"error":"boom"}'
                    self.send_response(outer.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                body = json.dumps({
                    "id": "chatcmpl-fake",
                    "model": payload.get("model", "?"),
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant",
                                    "content": outer.answer},
                        "finish_reason": "stop",
                    }],
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


def _sample_copy(tmp: Path) -> Path:
    for sample in SAMPLES:
        if sample.is_dir():
            dst = tmp / sample.name
            shutil.copytree(sample, dst)
            return dst
    raise unittest.SkipTest("仓库里没有可用的真项目样本")


class TestAIAdapter(unittest.TestCase):
    """适配层本身。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.project = _sample_copy(self.tmp)
        self.backend = _FakeBackend()
        self.base_url = self.backend.start()
        self.addCleanup(self.backend.stop)
        self.addCleanup(self._tmp.cleanup)

    def _use_backend(self, model: str = "qwen") -> None:
        """让这个盘指到假后端。"""
        (self.project / "workbench.toml").write_text(
            '[ai]\nbase_url = "%s"\nmodel = "%s"\n' % (self.base_url, model),
            encoding="utf-8")

    def test_chat_completion_returns_text(self):
        """真打一次假后端：拿到正文。"""
        text = ai.chat_completion(self.base_url, "qwen",
                                  [{"role": "user", "content": "盲评对数？"}])
        self.assertEqual(text, ANSWER)
        self.assertEqual(len(self.backend.requests), 1)
        self.assertEqual(self.backend.requests[0]["model"], "qwen")
        self.assertEqual(self.backend.requests[0]["messages"][-1]["content"],
                         "盲评对数？")

    def test_chat_ok_true_when_backend_reachable(self):
        """后端在 → ok=True，fallback=False。"""
        self._use_backend()
        result = ai.chat(self.project, [{"role": "user", "content": "盲评对数？"}])
        self.assertTrue(result["ok"])
        self.assertFalse(result["fallback"])
        self.assertEqual(result["reply"], ANSWER)
        self.assertEqual(result["model"], "qwen")
        self.assertEqual(result["error"], "")

    def test_chat_fallback_when_backend_down(self):
        """后端不在 → 结构化降级，首行标注「模拟回答（未接模型）」。"""
        self._use_backend()
        result = ai.chat(self.project, [{"role": "user", "content": "盲评对数？"}])
        self.assertTrue(result["ok"])  # 假后端还开着时是真答

        # 真的把它关掉。
        self.backend.stop()
        result = ai.chat(self.project, [{"role": "user", "content": "盲评对数？"}])
        self.assertFalse(result["ok"])
        self.assertTrue(result["fallback"])
        self.assertEqual(result["reply"].splitlines()[0], ai.FALLBACK_MARK)
        self.assertTrue(result["reply"].startswith("模拟回答（未接模型）"))
        self.assertTrue(result["error"])
        self.assertNotIn(ANSWER, result["reply"])

    def test_fallback_never_looks_like_a_model_answer(self):
        """降级回复里不许出现真回答的内容（绝不多处造假）。"""
        reply = ai.simulated_reply("问题？", "连不上")
        self.assertTrue(reply.startswith(ai.FALLBACK_MARK))
        self.assertIn("问题？", reply)

    def test_config_from_workbench_toml(self):
        """项目级 `workbench.toml` 的 `[ai]` 节生效。"""
        (self.project / "workbench.toml").write_text(
            '[ai]\nbase_url = "%s"\nmodel = "my-model"\napi_key = "sk-test"\n'
            % self.base_url, encoding="utf-8")
        config = ai.ai_config(self.project)
        self.assertEqual(config["base_url"], self.base_url)
        self.assertEqual(config["model"], "my-model")
        self.assertEqual(config["api_key"], "sk-test")
        result = ai.chat(self.project, [{"role": "user", "content": "在？"}])
        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "my-model")
        self.assertEqual(self.backend.requests[0]["model"], "my-model")
        self.assertEqual(
            self.backend.headers_seen[0].get("Authorization"), "Bearer sk-test")

    def test_default_config(self):
        """没有配置时用缺省（本机 8220 / qwen）。"""
        config = ai.ai_config(self.project)
        self.assertEqual(config["base_url"], ai.DEFAULT_BASE_URL)
        self.assertEqual(config["model"], ai.DEFAULT_MODEL)
        self.assertEqual(ai.DEFAULT_BASE_URL, "http://127.0.0.1:8220/v1")

    def test_quote_goes_into_context(self):
        """引用段要进上下文。"""
        self._use_backend()
        ai.chat(self.project, [{"role": "user", "content": "这段有什么问题？"}],
                quote={"text": "被引用的那一段文字", "section": "结果"})
        sent = json.dumps(self.backend.requests[0], ensure_ascii=False)
        self.assertIn("被引用的那一段文字", sent)
        self.assertIn("结果", sent)

    def test_explain_mode_includes_report_summary(self):
        """解读模式：上下文里带检查报告摘要。"""
        self._use_backend()
        ai.chat(self.project, [{"role": "user", "content": "解读这份报告"}],
                mode="explain")
        sent = json.dumps(self.backend.requests[0], ensure_ascii=False)
        self.assertIn("检查报告摘要", sent)

    def test_context_has_disk_body_text(self):
        """上下文里有当前盘的正文。"""
        context = ai.build_context(self.project)
        self.assertTrue(context.strip())
        self.assertIn("当前稿件正文", context)


class TestChatEndpoint(unittest.TestCase):
    """`POST /api/chat` 端点（真 HTTP）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.project = _sample_copy(self.tmp)
        self.backend = _FakeBackend()
        self.base_url = self.backend.start()
        self.addCleanup(self.backend.stop)
        self.addCleanup(self._tmp.cleanup)
        self.server, self.index = create_server(self.tmp)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        project_id = self.index.projects()[0]["id"]
        disk_id = self.index.projects()[0]["disks"][0]["id"]
        self.project_id = project_id
        self.disk_id = disk_id

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            "http://127.0.0.1:%d/api/chat" % self.port,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_endpoint_returns_real_answer(self):
        """端点真打后端。"""
        (self.project / "workbench.toml").write_text(
            '[ai]\nbase_url = "%s"\nmodel = "qwen"\n' % self.base_url,
            encoding="utf-8")
        data = self._post({"project": self.project_id, "disk": self.disk_id,
                           "messages": [{"role": "user", "content": "盲评对数？"}]})
        self.assertTrue(data["ok"])
        self.assertFalse(data["fallback"])
        self.assertEqual(data["reply"], ANSWER)
        self.assertEqual(data["project"], self.project_id)

    def test_endpoint_fallback_shape(self):
        """后端不可达：端点也必须给结构化降级（HTTP 200 + fallback 标记）。"""
        (self.project / "workbench.toml").write_text(
            '[ai]\nbase_url = "http://127.0.0.1:9/v1"\nmodel = "qwen"\n',
            encoding="utf-8")
        data = self._post({"project": self.project_id, "disk": self.disk_id,
                           "messages": [{"role": "user", "content": "盲评对数？"}]})
        self.assertFalse(data["ok"])
        self.assertTrue(data["fallback"])
        self.assertTrue(data["reply"].startswith("模拟回答（未接模型）"))

    def test_endpoint_rejects_bad_input(self):
        """messages 缺失 → 结构化 400，不崩。"""
        request = urllib.request.Request(
            "http://127.0.0.1:%d/api/chat" % self.port,
            data=b"{}", headers={"Content-Type": "application/json"},
            method="POST")
        try:
            urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)
            body = json.loads(exc.read().decode("utf-8"))
            self.assertFalse(body["ok"])
            return
        self.fail("应当 400")


if __name__ == "__main__":
    unittest.main()
