# -*- coding: utf-8 -*-
"""账与证据面的提议单（宿主能提，人点才写）。

钉住（与正文提议单同一套形状与同一条纪律）：

- 提议单**只落状态目录**：正文、账、冻结件一个字节都不动；
- 差异卡上展示的 after_text 就是真正会落盘的那一份（所见即落盘）；
- 指纹闸：提议之后状态被别处改过，采纳时拒写（BLOCK_STALE），
  不覆盖别人的改动；
- 铁律：不得凭空造事实——重复 id、缺来源文件一律拒。

跑法（仓根）：python3 -m pytest tests/test_workbench_proposals.py -q
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import ConfigError  # noqa: E402
from factscribe.workbench.proposal import create_proposal, list_proposals  # noqa: E402
from factscribe.workbench.write import apply_proposal  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"

#: 正文提议单也带的字段——账与证据面必须同形（页面差异卡是一套渲染）。
COMMON_KEYS = ("kind", "file", "block", "before_sha", "before_text",
               "proposed_text", "after_text", "warnings", "source",
               "rationale")


class ProposalFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-proposals-"))
        self.disk = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.disk)
        self.state = self.tmp / "state"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def propose(self, kind, **body):
        return create_proposal(self.state, "p", "d", self.disk,
                               dict(body, kind=kind))


class EvidenceProposalTests(ProposalFixture):
    """证据冻结／解冻。"""

    def test_freeze_proposal_does_not_touch_the_lock(self):
        record = self.propose("evidence_freeze", reason="留底")
        for key in COMMON_KEYS:
            self.assertIn(key, record)
        self.assertEqual(record["kind"], "evidence_freeze")
        self.assertFalse((self.disk / "audit" / "evidence.lock").exists(),
                         "提议单不许写冻结件")
        self.assertIn("canonical_sha256", record["after_text"])

    def test_freeze_applies_only_when_human_confirms(self):
        record = self.propose("evidence_freeze", reason="留底")
        applied = apply_proposal(self.disk, record)
        self.assertTrue(applied["ok"])
        self.assertTrue((self.disk / "audit" / "evidence.lock").is_file())
        self.assertEqual(applied["kind"], "evidence_freeze")

    def test_stale_declaration_is_refused_on_apply(self):
        record = self.propose("evidence_freeze", reason="留底")
        record["before_sha"] = "deadbeef" * 8
        with self.assertRaises(ConfigError) as ctx:
            apply_proposal(self.disk, record)
        self.assertEqual(ctx.exception.code, "BLOCK_STALE")
        self.assertFalse((self.disk / "audit" / "evidence.lock").exists())

    def test_unfreeze_requires_a_reason(self):
        with self.assertRaises(ConfigError) as ctx:
            self.propose("evidence_unfreeze", reason="")
        self.assertEqual(ctx.exception.code, "EVIDENCE_REASON_REQUIRED")

    def test_unfreeze_needs_a_lock_first(self):
        with self.assertRaises(ConfigError) as ctx:
            self.propose("evidence_unfreeze", reason="要改")
        self.assertEqual(ctx.exception.code, "EVIDENCE_NOT_FROZEN")

    def test_unfreeze_proposal_previews_the_log_entry(self):
        from factscribe.evidence import freeze_evidence

        freeze_evidence(self.disk, {}, "先冻")
        log = self.disk / "audit" / "evidence-log.ndjson"
        before = log.read_text(encoding="utf-8")
        record = self.propose("evidence_unfreeze", reason="要改清单")
        self.assertEqual(record["kind"], "evidence_unfreeze")
        self.assertIn("要改清单", record["after_text"])
        self.assertEqual(log.read_text(encoding="utf-8"), before,
                         "提议单不许往流水账里追加记录")
        applied = apply_proposal(self.disk, record)
        self.assertTrue(applied["ok"])
        self.assertTrue((self.disk / "audit" / "evidence-log.ndjson").is_file())


class AddFactProposalTests(ProposalFixture):
    """追加一条事实。"""

    def fact_body(self, **over):
        # value 用**产物里真有的**那一份（results/swb16.md 的「= 56.25%」）：
        # 追加事实现在有 value 硬校验——数字必须能在产物原文里命中。
        body = {"id": "Z9", "claim": "新增主张", "value": "56.25%",
                "source": "results/swb16.md", "locator": "line 3",
                "confidence": "high"}
        body.update(over)
        return body

    def test_fact_proposal_does_not_touch_the_ledger(self):
        record = self.propose("add_fact", **self.fact_body())
        self.assertEqual(record["kind"], "add_fact")
        ledger = (self.disk / "facts" / "01-core.toml").read_text(
            encoding="utf-8")
        self.assertNotIn("Z9", ledger, "提议单不许写账")

    def test_fact_preview_is_what_actually_gets_written(self):
        record = self.propose("add_fact", **self.fact_body())
        block = record["fact"] and record["proposed_text"]
        self.assertIn('id = "Z9"', block)
        applied = apply_proposal(self.disk, record)
        self.assertTrue(applied["ok"])
        ledger = (self.disk / "facts" / "01-core.toml").read_text(
            encoding="utf-8")
        self.assertIn(block.strip(), ledger)

    def test_duplicate_id_is_refused_at_propose_time(self):
        self.propose("add_fact", **self.fact_body())
        record = self.propose("add_fact", **self.fact_body())
        applied = apply_proposal(self.disk, record)
        self.assertTrue(applied["ok"])
        with self.assertRaises(ConfigError):
            self.propose("add_fact", **self.fact_body())

    def test_fact_without_source_is_refused(self):
        with self.assertRaises(ConfigError):
            self.propose("add_fact", **self.fact_body(source="results/nope.md"))


class BundleProposalTests(ProposalFixture):
    """导出投稿包。"""

    def test_bundle_proposal_does_not_export(self):
        record = self.propose("export_bundle")
        self.assertEqual(record["kind"], "export_bundle")
        for key in COMMON_KEYS:
            self.assertIn(key, record)
        self.assertIn("投稿包", record["after_text"])


class ProposalStoreTests(ProposalFixture):
    """提议单落状态目录，不落论文目录。"""

    def test_proposal_is_listed_from_the_state_dir(self):
        record = self.propose("evidence_freeze", reason="留底")
        rows = list_proposals(self.state, project="p", disk="d")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], record["id"])
        self.assertEqual(rows[0]["status"], "pending")

    def test_state_dir_is_outside_the_paper(self):
        self.propose("evidence_freeze", reason="留底")
        self.assertTrue(self.state.is_dir())
        self.assertFalse((self.disk / "proposals").exists())


if __name__ == "__main__":
    unittest.main()
