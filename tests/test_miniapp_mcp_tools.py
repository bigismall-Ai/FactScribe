# -*- coding: utf-8 -*-
"""tests/test_miniapp_mcp_tools.py —— MiniApp MCP 面上两条新只读工具的契约考题。

真起 Node 薄壳，走 **MCP 协议**（initialize → tools/list → tools/call）驱动
宿主那条路，断言：

1. 工具面上确实挂着 `fs_get_style` 与 `fs_mirror_check`，且都是只读注解、
   入参 `{project, disk}` 必填；
2. 两条工具**宿主直接调用**能拿回结构化读数（不是空壳、不是报错）；
3. `fs_get_report` 的英文读数（lang=en）里没有中文残留，中文读数仍是中文；
4. 报告里每条 finding 都带 `message_key` 与 `params`（i18n 原料）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tests" / "miniapp_mcp_driver.mjs"
PAPER = ROOT / "examples" / "minimal"

#: 中文（CJK 统一表意文字＋全角标点）。
CJK_RE = re.compile("[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")


def run_driver() -> dict:
    """跑驱动脚本，把 MCP 面的实测读数拿回来。"""
    with tempfile.TemporaryDirectory() as tmp:
        result = Path(tmp) / "result.json"
        env = dict(os.environ,
                   FS_PLUGIN_ROOT=str(ROOT / "miniapp"),
                   FS_PAPER_SRC=str(PAPER),
                   FS_RESULT_PATH=str(result))
        proc = subprocess.run(["node", str(DRIVER)], env=env,
                              cwd=str(ROOT), capture_output=True, text=True,
                              timeout=300)
        if not result.is_file():
            raise AssertionError("驱动脚本没产出结果文件（退出码 %d）：\n%s\n%s"
                                 % (proc.returncode, proc.stdout[-2000:],
                                    proc.stderr[-2000:]))
        data = json.loads(result.read_text(encoding="utf-8"))
    data["_returncode"] = proc.returncode
    data["_stderr"] = proc.stderr[-2000:]
    return data


class McpToolSurfaceTests(unittest.TestCase):
    """① 工具面：两条新工具在，形状对。"""

    @classmethod
    def setUpClass(cls):
        cls.data = run_driver()
        cls.tools = {t["name"]: t for t in cls.data.get("tools") or []}

    def test_the_driver_ran_clean(self):
        self.assertTrue(self.data.get("ok"),
                        "驱动脚本没跑通：%s" % (self.data.get("errors") or []))

    def test_both_new_tools_are_listed(self):
        for name in ("fs_get_style", "fs_mirror_check"):
            self.assertIn(name, self.tools, "工具面上没有 %s" % name)

    def test_both_new_tools_are_read_only_and_take_project_disk(self):
        for name in ("fs_get_style", "fs_mirror_check"):
            tool = self.tools[name]
            self.assertTrue(tool["readOnly"], "%s 不是只读工具" % name)
            self.assertEqual(sorted(tool["required"]), ["disk", "project"],
                             "%s 的必填入参不对" % name)
            self.assertIn("project", tool["properties"])
            self.assertIn("disk", tool["properties"])

    def test_the_existing_tools_are_still_there(self):
        for name in ("fs_status", "fs_get_outline", "fs_read_section",
                     "fs_get_report", "fs_query_facts", "fs_search_kb",
                     "fs_propose_edit", "fs_list_proposals"):
            self.assertIn(name, self.tools, "工具面上少了 %s" % name)

    def test_the_new_read_tools_are_listed_and_read_only(self):
        for name in ("fs_get_evidence_status", "fs_get_brief",
                     "fs_get_venue"):
            self.assertIn(name, self.tools, "工具面上少了 %s" % name)
            self.assertTrue(self.tools[name]["readOnly"],
                            "%s 不是只读工具" % name)

    def test_the_new_propose_tools_are_not_read_only(self):
        for name in ("fs_propose_evidence_freeze",
                     "fs_propose_evidence_unfreeze", "fs_propose_add_fact",
                     "fs_propose_export_bundle"):
            self.assertIn(name, self.tools, "工具面上少了 %s" % name)
            self.assertFalse(self.tools[name]["readOnly"],
                             "%s 不该标成只读" % name)


class McpToolCallTests(unittest.TestCase):
    """② 两条新工具：宿主直接调用拿回结构化读数。"""

    @classmethod
    def setUpClass(cls):
        cls.data = run_driver()
        cls.calls = cls.data.get("calls") or {}

    def test_the_driver_ran_clean(self):
        self.assertTrue(self.data.get("ok"),
                        "驱动脚本没跑通：%s" % (self.data.get("errors") or []))

    def test_style_reading_has_structured_numbers(self):
        payload = self.calls.get("fs_get_style") or {}
        self.assertIsInstance(payload, dict, "fs_get_style 没给回结构化读数")
        self.assertTrue(payload, "fs_get_style 回空")
        self.assertIn(payload.get("status"), ("ok", "yellow", "red"),
                      "fs_get_style 的 status 不对：%r" % payload.get("status"))
        self.assertIn("findings", payload)
        self.assertIn("summary", payload)
        self.assertIn("metrics", payload)

    def test_mirror_reading_has_structured_drift(self):
        payload = self.calls.get("fs_mirror_check") or {}
        self.assertIsInstance(payload, dict, "fs_mirror_check 没给回结构化读数")
        self.assertTrue(payload, "fs_mirror_check 回空")
        self.assertIn(payload.get("status"), ("ok", "drift", "na"),
                      "fs_mirror_check 的 status 不对：%r" % payload.get("status"))
        self.assertIn("drift", payload)
        self.assertIn("summary", payload)
        self.assertIn("disk_a", payload)

    def test_english_report_has_no_chinese_residue(self):
        payload = self.calls.get("report_en") or {}
        findings = payload.get("findings") or []
        self.assertTrue(findings, "英文报告一条发现都没有？")
        for finding in findings:
            self.assertFalse(CJK_RE.search(finding.get("message") or ""),
                             "%s 的英文文案里有中文：%s"
                             % (finding.get("code"), finding.get("message")))

    def test_chinese_report_is_still_chinese(self):
        payload = self.calls.get("report_zh") or {}
        findings = payload.get("findings") or []
        self.assertTrue(findings, "中文报告一条发现都没有？")
        for finding in findings:
            self.assertTrue(CJK_RE.search(finding.get("message") or ""),
                            "%s 的中文文案不该变成英文：%s"
                            % (finding.get("code"), finding.get("message")))

    def test_evidence_status_reading_has_the_diff_shape(self):
        payload = self.calls.get("fs_get_evidence_status") or {}
        self.assertIsInstance(payload, dict, "fs_get_evidence_status 没给回读数")
        self.assertIn("frozen", payload)
        self.assertIn("entries", payload)
        self.assertIn("sha256", payload)
        self.assertIn("mismatch", payload)
        self.assertIn("unfrozen", payload)
        self.assertIn("diff", payload)
        self.assertIn("last_log", payload)

    def test_brief_reading_separates_usable_and_bound(self):
        payload = self.calls.get("fs_get_brief") or {}
        self.assertIsInstance(payload, dict, "fs_get_brief 没给回读数")
        sections = payload.get("sections") or []
        self.assertTrue(sections, "简报里一节都没有？")
        for row in sections:
            for key in ("usable", "bound", "unbound", "reconciled"):
                self.assertIn(key, row)
        self.assertIn("counts", payload)
        self.assertIn("facts", payload)

    def test_venue_reading_has_the_publication_deadline(self):
        payload = self.calls.get("fs_get_venue") or {}
        self.assertIsInstance(payload, dict, "fs_get_venue 没给回读数")
        for key in ("venue", "deadline", "days_left", "lang_lock"):
            self.assertIn(key, payload)

    def test_proposals_land_in_the_state_dir_not_on_the_paper(self):
        freeze = self.calls.get("fs_propose_evidence_freeze") or {}
        self.assertTrue(freeze.get("id"), "冻结提议单没建起来")
        self.assertEqual(freeze.get("status"), "pending")
        fact = self.calls.get("fs_propose_add_fact") or {}
        self.assertTrue(fact.get("id"), "追加事实的提议单没建起来")
        self.assertIn("Z9", str(fact.get("after_text") or ""))
        rows = (self.calls.get("fs_list_proposals") or {}).get("proposals") or []
        kinds = {row.get("kind") for row in rows}
        self.assertIn("evidence_freeze", kinds)
        self.assertIn("add_fact", kinds)

    def test_the_paper_directory_is_untouched(self):
        self.assertTrue(self.data.get("paperUnchanged"),
                        "提议单碰了论文目录——它只该落状态目录")

    def test_findings_carry_the_i18n_raw_material(self):
        payload = self.calls.get("report_en") or {}
        for finding in payload.get("findings") or []:
            self.assertTrue(finding.get("message_key"), "发现没带 message_key")
            self.assertIsInstance(finding.get("params"), dict)


if __name__ == "__main__":
    unittest.main()
