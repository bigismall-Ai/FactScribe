# -*- coding: utf-8 -*-
r"""松尾账①（P-100）：mark_dup_ok 移出 facts_ledger 为独立维护模块的守锁。

规范出处：SPEC-CHECKS §9 裁定⑦（改账是写径不是核验，不进 verify()）；
拆分口径＝``facts_ledger`` 只读检测、``ledger_maint`` 改账维护。

锁三件事：

* 幂等语义不变：首跑标注「同值且 claim 不同」的事实，重跑零标注、零字节变化；
* 已带 ``dup_ok`` 的块不动（不重复追加）；
* 单一实现：``facts_ledger`` 里不再有 mark_dup_ok（写径只此一份）。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGAL = ROOT / "integrations" / "factscribe-legal"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(LEGAL))

from factscribe_legal.facts_ledger import scan_dupes  # noqa: E402
from factscribe_legal.ledger_maint import mark_dup_ok  # noqa: E402


def _project(base: Path, toml_text: str) -> Path:
    root = Path(base)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "facts" / "one.toml").write_text(toml_text, encoding="utf-8")
    return root


TWO_SAME_VALUE = """[[fact]]
id = "A"
claim = "法国侧参考日"
value = "2026-11-14"

[[fact]]
id = "B"
claim = "中国侧参考日"
value = "2026-11-14"
"""


class TestMarkDupOk(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_marks_same_value_different_claim(self):
        root = _project(self.tmp / "p1", TWO_SAME_VALUE)
        changed = mark_dup_ok(root)
        self.assertEqual(changed, ["A", "B"])
        text = (root / "facts" / "one.toml").read_text(encoding="utf-8")
        self.assertEqual(text.count("dup_ok = true"), 2)

    def test_idempotent_rerun_changes_nothing(self):
        root = _project(self.tmp / "p2", TWO_SAME_VALUE)
        mark_dup_ok(root)
        before = (root / "facts" / "one.toml").read_bytes()
        self.assertEqual(mark_dup_ok(root), [])
        self.assertEqual((root / "facts" / "one.toml").read_bytes(), before)

    def test_existing_dup_ok_block_is_untouched(self):
        root = _project(self.tmp / "p3", TWO_SAME_VALUE.replace(
            'value = "2026-11-14"\n', 'value = "2026-11-14"\ndup_ok = true\n', 1))
        before = (root / "facts" / "one.toml").read_text(encoding="utf-8")
        changed = mark_dup_ok(root)
        self.assertEqual(changed, ["B"])   # 已标的 A 不重标
        after = (root / "facts" / "one.toml").read_text(encoding="utf-8")
        self.assertIn("dup_ok = true\n\n[[fact]]", after)
        self.assertEqual(after.count("dup_ok = true"), 2)
        self.assertNotEqual(before, after)

    def test_no_dupes_is_noop(self):
        root = _project(self.tmp / "p4",
                        '[[fact]]\nid = "A"\nclaim = "c1"\nvalue = "1"\n')
        before = (root / "facts" / "one.toml").read_bytes()
        self.assertEqual(mark_dup_ok(root), [])
        self.assertEqual((root / "facts" / "one.toml").read_bytes(), before)

    def test_scan_dupes_stays_read_only_in_facts_ledger(self):
        # 检测（只读）留 facts_ledger；写径只有 ledger_maint 一份。
        root = _project(self.tmp / "p5", TWO_SAME_VALUE)
        dupes, allfacts = scan_dupes(root)
        self.assertEqual([d[1] for d in dupes], ["A", "B"])
        self.assertEqual(len(allfacts), 2)
        text = (root / "facts" / "one.toml").read_text(encoding="utf-8")
        self.assertNotIn("dup_ok", text)   # 检测不改账


if __name__ == "__main__":
    unittest.main()
