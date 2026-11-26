# -*- coding: utf-8 -*-
"""tests/test_miniapp_shell_models.py —— v4 运行时考题：真起薄壳跑模型三条路。

这不是字符串断言，是**真跑**：起 Node 薄壳（同一份 miniapp/miniapp/node/server.mjs），
给一份论文根（examples 的临时拷贝，绝不脏源目录），再灌两个桩
（见 tests/miniapp_shell_driver.mjs）：

  * 宿主 Agent 桩——带模型目录（两个模型，各自的思考等级档位），
    记录每次 run() 收到的 model；
  * OpenAI 兼容桩后端——记录收到的请求（URL／Authorization／模型名／提示词）。

然后断言：

1. GET /api/ai/models 给出宿主目录（含思考等级档位）＋「宿主默认」；
2. POST /api/chat 选了宿主模型与等级时，**run() 真的收到那个 model**；
   选「宿主默认」时不带 model（用 MCode 当前模型）；
3. 自定义模型：凭据只落插件私有 dataDir（0600）、不进论文目录、不进页面回包；
   选它时走 OpenAI 兼容通道（Authorization 带密钥、模型名对）；
4. 宿主不认的模型明确报 MODEL_UNAVAILABLE（不偷换模型、不多跑一轮）。

node 不在 PATH 就跳过。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tests" / "miniapp_shell_driver.mjs"


@unittest.skipUnless(shutil.which("node"), "node 不在 PATH")
class ShellModelRuntimeTests(unittest.TestCase):
    """真起薄壳：宿主模型目录、按模型跑回合、自定义模型三条路。"""

    result: dict

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="fs-shell-models-")
        result_path = Path(cls.tmp) / "result.json"
        env = dict(os.environ)
        env["FS_PLUGIN_ROOT"] = str(ROOT / "miniapp")
        env["FS_PAPER_SRC"] = str(ROOT / "examples")
        env["FS_RESULT_PATH"] = str(result_path)
        proc = subprocess.run(
            ["node", str(DRIVER)], capture_output=True, text=True, timeout=300, env=env,
        )
        if not result_path.is_file():
            raise AssertionError(
                "驱动脚本没产出结果（exit=%s）\nstdout:\n%s\nstderr:\n%s"
                % (proc.returncode, proc.stdout[-3000:], proc.stderr[-3000:])
            )
        cls.result = json.loads(result_path.read_text(encoding="utf-8"))
        cls.proc = proc

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def step(self, name):
        for item in self.result.get("steps", []):
            if item["name"] == name:
                return item["value"]
        self.fail("驱动脚本没产出步骤：%s" % name)

    def test_driver_ran(self):
        self.assertTrue(self.result.get("ok"), self.result.get("error"))
        self.assertEqual(200, self.step("setup"))
        project = self.step("project")
        self.assertTrue(project.get("id"), project)
        self.assertTrue(project.get("disk"), project)

    def test_models_catalog_lists_host_models_with_efforts(self):
        data = self.step("models")
        self.assertEqual("mcode-agent", data.get("source"))
        ids = [m["id"] for m in data["models"]]
        self.assertIn("host:default", ids)
        self.assertIn("host:minimax/MiniMax-M3", ids)
        self.assertIn("host:minimax/MiniMax-M3.1-Flash", ids)
        self.assertEqual("host:default", data.get("model"))
        by_id = {m["id"]: m for m in data["models"]}
        self.assertEqual(["low", "medium", "high", "off"],
                         by_id["host:minimax/MiniMax-M3"]["efforts"])
        self.assertEqual("medium", by_id["host:minimax/MiniMax-M3"]["defaultEffort"])
        self.assertEqual(["low", "high"], by_id["host:minimax/MiniMax-M3.1-Flash"]["efforts"])
        self.assertEqual("host", by_id["host:minimax/MiniMax-M3"]["kind"])

    def test_chat_runs_with_the_selected_model_and_effort(self):
        chat = self.step("chatHost")
        self.assertEqual(200, chat["status"])
        self.assertEqual("mcode-agent", chat["json"].get("source"))
        calls = self.result.get("agentCalls") or []
        self.assertTrue(calls, "宿主 Agent 没被叫起来")
        self.assertEqual(
            {"providerId": "minimax", "modelId": "MiniMax-M3",
             "variant": "thinking", "thinking": {"effort": "high"}},
            calls[0].get("model"),
        )
        self.assertEqual("MiniMax-M3", chat["json"].get("model"))

    def test_host_default_passes_no_model(self):
        chat = self.step("chatDefault")
        self.assertEqual(200, chat["status"])
        calls = self.result.get("agentCalls") or []
        self.assertEqual(2, len(calls))
        self.assertIsNone(calls[1].get("model"), "宿主默认不该带 model")

    def test_custom_model_goes_through_openai_channel(self):
        chat = self.step("chatCustom")
        self.assertEqual(200, chat["status"])
        self.assertEqual("custom-model", chat["json"].get("source"))
        self.assertIn("自定义模型答", chat["json"].get("reply", ""))
        hits = self.result.get("openaiHits") or []
        self.assertEqual(1, len(hits))
        self.assertEqual("/v1/chat/completions", hits[0]["url"])
        self.assertEqual("Bearer secret-key-123", hits[0]["auth"])
        self.assertEqual("qwen-32b", hits[0]["model"])
        self.assertTrue(hits[0]["contentHasMaterial"], "提示词里没有材料")
        self.assertGreater(hits[0]["contentLen"], 0)
        self.assertFalse(hits[0]["stream"], "这一路是非流式")

    def test_api_key_never_leaves_the_plugin_dir(self):
        self.assertFalse(self.step("customLeak"), "页面回包漏了密钥")
        listed = self.step("customListed")
        self.assertEqual(1, len(listed["models"]))
        self.assertTrue(listed["models"][0]["hasKey"])
        self.assertNotIn("apiKey", listed["models"][0])
        store = self.step("store")
        self.assertTrue(store["exists"])
        self.assertEqual("600", store["mode"])
        self.assertFalse(store["inPaperRoot"], "凭据不该落进论文目录")

    def test_engine_kind_selection_goes_to_the_engine_not_the_agent(self):
        """选了引擎本地后端的模型 → 直接问引擎，宿主 Agent 不接管这一路。"""
        chat = self.step("chatEngine")
        self.assertEqual(200, chat["status"])
        # 本机没有可用的本地后端 → 引擎给的是老实的「模拟回答（未接模型）」降级。
        self.assertTrue(chat["json"].get("fallback"), chat["json"])
        self.assertIn("模拟回答（未接模型）", chat["json"].get("reply", ""))
        calls = self.result.get("agentCalls") or []
        self.assertEqual(2, len(calls), "引擎本地模型不该惊动宿主 Agent")

    def test_unknown_model_is_reported_not_swapped(self):
        chat = self.step("chatBadModel")
        self.assertEqual(400, chat["status"])
        self.assertEqual("MODEL_UNAVAILABLE", chat["json"].get("code"))
        calls = self.result.get("agentCalls") or []
        self.assertEqual(2, len(calls), "模型不认时不该再跑一轮")


if __name__ == "__main__":
    unittest.main()
