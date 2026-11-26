# -*- coding: utf-8 -*-
"""工作台的两条新只读读数：证据锁（G1）＋写作简报（G3）。

钉住：

- evidence_gate 与 CLI MCP 的 factscribe_evidence_status 同源：
  冻结状态／差异明细／解冻状态／最后一条日志，读数口径复用
  factscribe.evidence 的原件（不另算一遍哈希）；
- brief_reading 只在 brief 之上只增不改：显式区分
  「可引用（usable）／已绑（bound）／可引用但还没绑（unbound）」，
  宿主不必自己判断哪个数能引；
- 读不动就结构化报错（ok:false ＋ code ＋ error），绝不抛异常。

跑法（仓根）：python3 -m pytest tests/test_workbench_readings.py -q
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench.readings import brief_reading, evidence_gate  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"


class ReadingFixture(unittest.TestCase):
    """每个用例一份干净的 examples/minimal 拷贝。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-readings-"))
        self.disk = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.disk)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class EvidenceGateTests(ReadingFixture):
    """证据锁读数。"""

    def test_unfrozen_project_reports_no_lock(self):
        data = evidence_gate(self.disk)
        self.assertTrue(data.get("ok"))
        self.assertFalse(data.get("frozen"))
        self.assertEqual(data.get("entries"), 0)
        self.assertIsNone(data.get("mismatch"))
        self.assertIsNone(data.get("unfrozen"))
        self.assertEqual(data.get("last_log", {}).get("action"), "")

    def test_freezing_then_reading_shows_the_lock(self):
        from factscribe.evidence import freeze_evidence

        freeze_evidence(self.disk, {}, "测试冻结")
        data = evidence_gate(self.disk)
        self.assertTrue(data.get("frozen"))
        self.assertEqual(data.get("last_log", {}).get("action"), "freeze")
        self.assertEqual(data.get("last_log", {}).get("reason"), "测试冻结")

    def test_unfreeze_shows_reason_and_at(self):
        from factscribe.evidence import freeze_evidence, unfreeze_evidence

        freeze_evidence(self.disk, {}, "先冻")
        unfreeze_evidence(self.disk, "要改清单", "2026-11-22")
        data = evidence_gate(self.disk)
        self.assertIsNotNone(data.get("unfrozen"))
        self.assertEqual(data["unfrozen"]["reason"], "要改清单")
        self.assertEqual(data["unfrozen"]["at"], "2026-11-22")
        self.assertEqual(data.get("last_log", {}).get("action"), "unfreeze")

    def test_diff_reports_which_sections_moved(self):
        from factscribe.evidence import freeze_evidence

        freeze_evidence(self.disk, {"01-intro": ["A1"]}, "冻结")
        # 冻结之后清单变了 → lock_check 给出差异明细。
        lock = self.disk / "audit" / "evidence.lock"
        lock.write_text(lock.read_text(encoding="utf-8").replace(
            '"A1"', '"A2"'), encoding="utf-8")
        data = evidence_gate(self.disk)
        self.assertIsNotNone(data.get("mismatch"))
        diff = data.get("diff") or {}
        self.assertIn("added", diff)
        self.assertIn("removed", diff)
        self.assertIn("moved", diff)

    def test_broken_project_reports_structured_error(self):
        broken = self.tmp / "broken"
        broken.mkdir()
        data = evidence_gate(broken)
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("code"), "CONFIG_INVALID")
        self.assertTrue(data.get("error"))


class BriefReadingTests(ReadingFixture):
    """写作简报读数。"""

    def test_brief_lists_usable_bound_and_unbound(self):
        data = brief_reading(self.disk)
        self.assertTrue(data.get("ok"))
        sections = data.get("sections") or []
        self.assertTrue(sections, "简报里一节都没有？")
        for row in sections:
            self.assertIn("usable", row)
            self.assertIn("bound", row)
            self.assertIn("unbound", row)
            self.assertIn("reconciled", row)
            # usable 减 bound 必须是 unbound（别让宿主自己算）。
            self.assertEqual([x for x in row["usable"] if x not in row["bound"]],
                             row["unbound"])

    def test_bound_facts_are_marked_in_the_ledger_view(self):
        data = brief_reading(self.disk)
        facts = data.get("facts") or []
        self.assertTrue(facts, "简报里一条事实都没有？")
        for fact in facts:
            self.assertIn(fact["status"], ("bound", "unbound"))
            self.assertIsInstance(fact.get("bound_in"), list)
        counts = data.get("counts") or {}
        bound = sum(1 for f in facts if f["status"] == "bound")
        self.assertEqual(counts.get("bound"), bound)
        self.assertEqual(counts.get("ledger_total"), len(facts))
        self.assertEqual(counts.get("unbound"), len(facts) - bound)

    def test_brief_keeps_the_original_fields(self):
        data = brief_reading(self.disk)
        for row in data.get("sections") or []:
            # brief 原有的字段一个都不许少（只增不改）。
            for key in ("file", "title", "facts", "budget", "evidence",
                        "evidence_source"):
                self.assertIn(key, row)
        for fact in data.get("facts") or []:
            for key in ("id", "claim", "value"):
                self.assertIn(key, fact)

    def test_section_filter_narrows_the_reading(self):
        data = brief_reading(self.disk, "01")
        self.assertEqual(data.get("section"), "01")
        for row in data.get("sections") or []:
            self.assertTrue(str(row.get("file", "")).startswith("sections/01"),
                            "节过滤没生效：%s" % row.get("file"))

    def test_unknown_section_reports_structured_error(self):
        data = brief_reading(self.disk, "99")
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("code"), "BRIEF_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
