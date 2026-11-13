# -*- coding: utf-8 -*-
"""`factscribe mcp`：stdio JSON-RPC 的协议面与工具面。

只测协议与工具结果，不测模型；read-only 与 --allow-write 各一组。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "minimal"


def start(project: Path, *args):
    return subprocess.Popen(
        [sys.executable, "-u", "-m", "factscribe", "mcp", str(project), *args],
        cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8")


def rpc(proc, message: dict) -> dict:
    proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise AssertionError("MCP server closed stdout")
    return json.loads(line)


def call(proc, name: str, arguments=None) -> dict:
    return rpc(proc, {"jsonrpc": "2.0", "id": 99, "method": "tools/call",
                      "params": {"name": name, "arguments": arguments or {}}})


def stop(proc):
    try:
        proc.stdin.write('{"jsonrpc":"2.0","method":"exit"}\n')
        proc.stdin.flush()
    except Exception:
        pass
    try:
        proc.stdin.close()
    except Exception:
        pass
    proc.wait(timeout=5)


class McpReadOnlyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = start(EXAMPLES)
        init = rpc(cls.proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "0"}},
        })
        cls.init = init

    @classmethod
    def tearDownClass(cls):
        stop(cls.proc)

    def test_initialize(self):
        result = self.init["result"]
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertEqual(result["serverInfo"]["name"], "factscribe")
        self.assertIn("tools", result["capabilities"])

    def test_tools_list_is_read_only(self):
        result = rpc(self.proc, {"jsonrpc": "2.0", "id": 2,
                                 "method": "tools/list"})["result"]
        names = {t["name"] for t in result["tools"]}
        self.assertIn("factscribe_status", names)
        self.assertIn("factscribe_project", names)
        self.assertIn("factscribe_audit", names)
        self.assertIn("factscribe_evidence_status", names)
        self.assertNotIn("factscribe_write_section", names)
        self.assertNotIn("factscribe_add_fact", names)

    def test_status_and_audit(self):
        status = call(self.proc, "factscribe_status")
        body = json.loads(status["result"]["content"][0]["text"])
        self.assertEqual(body["facts"], 3)
        self.assertEqual(body["sections"], 2)
        self.assertTrue(body["read_only"])
        audit = call(self.proc, "factscribe_audit")
        body = json.loads(audit["result"]["content"][0]["text"])
        self.assertEqual(body["exit"], 1)
        self.assertEqual(body["verdict"], "red")
        self.assertTrue(body["findings"])

    def test_write_tool_is_refused(self):
        result = call(self.proc, "factscribe_write_section",
                      {"file": "sections/01-intro.tex", "text": "x"})
        self.assertTrue(result["result"]["isError"])
        self.assertIn("只读", result["result"]["content"][0]["text"])

    def test_unknown_method(self):
        result = rpc(self.proc, {"jsonrpc": "2.0", "id": 7, "method": "nope"})
        self.assertEqual(result["error"]["code"], -32601)


class McpWritableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "paper"
        shutil.copytree(EXAMPLES, cls.root)
        cls.proc = start(cls.root, "--allow-write")
        rpc(cls.proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2024-11-05",
                                  "capabilities": {},
                                  "clientInfo": {"name": "test", "version": "0"}}})

    @classmethod
    def tearDownClass(cls):
        stop(cls.proc)
        cls.tmp.cleanup()

    def test_write_section_and_add_fact(self):
        listing = rpc(self.proc, {"jsonrpc": "2.0", "id": 2,
                                  "method": "tools/list"})["result"]
        names = {t["name"] for t in listing["tools"]}
        self.assertIn("factscribe_write_section", names)
        self.assertIn("factscribe_add_fact", names)
        self.assertIn("factscribe_evidence_freeze", names)
        self.assertIn("factscribe_evidence_unfreeze", names)

        text = "\\section{Intro}\n\n新写的一句 42。\n"
        result = call(self.proc, "factscribe_write_section",
                      {"file": "sections/01-intro.tex", "text": text})
        self.assertFalse(result["result"]["isError"])
        self.assertEqual((self.root / "sections/01-intro.tex").read_text(
            encoding="utf-8"), text)

        result = call(self.proc, "factscribe_add_fact", {
            "id": "A9", "claim": "测试事实", "value": "42",
            "source": "results/swb16.md", "locator": "§二"})
        self.assertFalse(result["result"]["isError"])
        body = json.loads(result["result"]["content"][0]["text"])
        self.assertEqual(body["id"], "A9")

        frozen = call(self.proc, "factscribe_evidence_freeze", {})
        self.assertFalse(frozen["result"]["isError"])
        frozen_body = json.loads(frozen["result"]["content"][0]["text"])
        self.assertIn("sha256", frozen_body)
        unfrozen = call(self.proc, "factscribe_evidence_unfreeze",
                        {"reason": "测试", "at": "2026-11-13"})
        self.assertFalse(unfrozen["result"]["isError"])
        unfrozen_body = json.loads(unfrozen["result"]["content"][0]["text"])
        self.assertEqual(unfrozen_body["action"], "unfreeze")


if __name__ == "__main__":
    unittest.main()
