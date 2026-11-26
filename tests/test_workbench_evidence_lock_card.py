# -*- coding: utf-8 -*-
"""检查报告里的「证据锁」独立只读卡。

这一组钉三件事：

1. **独立一张卡**：报告载荷顶层多一个 `evidence_lock`（冻结与否／条目数／
   两个指纹／差异明细／最后一条日志），它与四步链**分开**——四步链的读数与
   语义一个字没动（`chain` 与 `evidence` 两个键逐字不变）。
2. **同一来源**：卡片读的就是 `readings.evidence_gate`——MCP 工具
   `fs_get_evidence_status` 调的也是它，两边读数不会互相矛盾。
3. **MCP 既有工具行为不变**：MCP 的 `fs_get_report` 自行整形载荷（不透传未知
   键），所以引擎报告里多一个键，MCP 工具的输出形状一个字没变。

跑法（仓根）：python3 -m pytest tests/test_workbench_evidence_lock_card.py -q
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.evidence import freeze_evidence  # noqa: E402
from factscribe.workbench.checkreport import report_payload  # noqa: E402
from factscribe.workbench.readings import evidence_gate  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"
MCP_SERVER = ROOT / "miniapp" / "miniapp" / "node" / "server.mjs"
APP_JS = ROOT / "factscribe" / "workbench" / "static" / "app.js"

DECLARED = {"01-intro": ["A1", "A3"], "02-results": ["A2"]}


def make_disk(root: Path) -> Path:
    disk = root / "paper"
    shutil.copytree(MINIMAL, disk)
    cfg = disk / "factscribe.toml"
    body = cfg.read_text(encoding="utf-8")
    body += chr(10) + "[evidence]" + chr(10)
    body += '"01-intro" = ["A1", "A3"]' + chr(10)
    body += '"02-results" = ["A2"]' + chr(10)
    cfg.write_text(body, encoding="utf-8")
    return disk


class EvidenceLockCardTests(unittest.TestCase):
    """报告里多一张独立的证据锁卡，四步链不动。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-evidence-card-"))
        self.disk = make_disk(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_card_is_a_separate_top_level_key(self):
        payload = report_payload(self.disk)
        self.assertIn("evidence_lock", payload)
        self.assertNotIn("evidence_lock", payload["chain"],
                         "证据锁是独立一张卡，不许混进四步链")

    def test_card_reads_the_same_source_as_the_evidence_gate(self):
        gate = evidence_gate(self.disk)
        card = report_payload(self.disk)["evidence_lock"]
        self.assertTrue(card["ok"])
        self.assertEqual(card["frozen"], gate["frozen"])
        self.assertEqual(card["entries"], gate["entries"])
        self.assertEqual(card["sha256"], gate["sha256"])
        self.assertEqual(card["current_sha256"], gate["current_sha256"])
        self.assertEqual(card["mismatch"], gate["mismatch"])

    def test_frozen_lock_is_reported(self):
        freeze_evidence(self.disk, DECLARED, reason="测试冻结")
        card = report_payload(self.disk)["evidence_lock"]
        self.assertTrue(card["frozen"])
        self.assertEqual(card["entries"], 3)
        self.assertEqual(card["sha256"], card["current_sha256"])
        self.assertIsNone(card["mismatch"], "冻结件与当前清单一致")
        self.assertEqual(card["diff"], {"added": [], "removed": [], "moved": []})
        self.assertEqual(card["last_log"].get("action"), "freeze")

    def test_changed_declaration_shows_the_difference(self):
        freeze_evidence(self.disk, DECLARED, reason="测试冻结")
        cfg = self.disk / "factscribe.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace(
            '"02-results" = ["A2"]', '"02-results" = ["A1"]'), encoding="utf-8")
        card = report_payload(self.disk)["evidence_lock"]
        self.assertTrue(card["frozen"])
        self.assertNotEqual(card["sha256"], card["current_sha256"])
        self.assertTrue(card["mismatch"], "清单变了就该报差异")
        self.assertTrue(card["diff"]["moved"] or card["diff"]["added"])

    def test_chain_readings_are_untouched(self):
        """四步链的键与形状不许因为多了这张卡而变。"""
        payload = report_payload(self.disk)
        chain = payload["chain"]
        self.assertEqual([step.get("key") for step in chain],
                         ["declare", "bind", "reconcile", "certify"])
        for step in chain:
            self.assertIn("state", step)
            self.assertIn("label_key", step)
        # 既有顶层 evidence 键仍在（旧的读数面不许消失）
        self.assertIn("evidence", payload)
        self.assertEqual(payload["evidence"]["entries"],
                         payload["evidence_lock"]["entries"])


class McpShapeTests(unittest.TestCase):
    """MCP 既有工具行为不变：报告载荷多一个键，MCP 输出形状不变。"""

    def test_mcp_report_shapes_its_own_payload(self):
        src = MCP_SERVER.read_text(encoding="utf-8")
        start = src.index("async report(args)")
        body = src[start:start + 2000]
        self.assertIn("chain: data.chain || []", body)
        self.assertIn("evidence: data.evidence || {}", body)
        self.assertNotIn("evidence_lock", body,
                         "MCP 工具的输出形状这一轮不许变（多一个键也不透传）")

    def test_page_reads_the_card_from_the_report_payload(self):
        """证据锁随报告载荷来——页面不多调一次端点。"""
        src = APP_JS.read_text(encoding="utf-8")
        start = src.index("function reportEvidenceLock(")
        body = src[start:src.index("function renderEvidenceLockCard(")]
        self.assertIn("state.report", body)
        self.assertIn("evidence_lock", body)
        self.assertNotIn("fetch(", body)
        self.assertNotIn("getJSON(", body)


if __name__ == "__main__":
    unittest.main()
