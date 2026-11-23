# -*- coding: utf-8 -*-
"""追加事实的两道闸：value 硬校验 ＋ 账本指纹闸。

第一道（value 硬校验）：填的 value 必须能在所选 source 产物原文里命中，
否则**拒建单**，并给一句人话（带定位信息：value、产物、没找到的数字、人
写的 locator）。命中口径在 factscribe/valuecheck.py——归一化后按数字项
逐个按出现顺序比对，单位不参与比较；value 里没有数字时按归一化子串比。

第二道（before_sha 指纹闸）：以目标账本文件的 sha256 为闸——提议之后账本
被别处改过，采纳时拒写（BLOCK_STALE），与其它提议单同一套纪律。

跑法（仓根）：python3 -m pytest tests/test_workbench_value_guard.py -q
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
from factscribe.valuecheck import check_value_in_source  # noqa: E402
from factscribe.workbench.proposal import create_proposal  # noqa: E402
from factscribe.workbench.write import apply_proposal  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"

#: 产物里真实存在的一段（tests 用的是**真样本**，不是编出来的数字）。
ARTIFACT = """
## 二 汇总表

| arm    | resolved | total |
|--------|----------|-------|
| open   | 10       | 16    |
| closed | 8        | 16    |

两臂合计：(10 + 8) / (16 + 16) = 56.25%
开臂均值 **90,431**／中位 **85,928**，调用数 14.8 vs 15.6。
分数写法：\\frac{10}{16}；百分号写法：56.25\\%
"""


def make_disk(root: Path) -> Path:
    disk = root / "paper"
    shutil.copytree(MINIMAL, disk)
    (disk / "results" / "sample.md").write_text(ARTIFACT, encoding="utf-8")
    return disk


class NormalizationTests(unittest.TestCase):
    """归一化口径：命中与不命中都钉死（不模糊放过）。"""

    def check(self, value, text):
        return check_value_in_source(value, text)

    def test_plain_numbers_hit(self):
        self.assertTrue(self.check("16", "16 题全部取自批 18")["ok"])
        self.assertTrue(self.check("10/16", "开臂 resolved 10/16，不开臂 5/16")["ok"])

    def test_a_number_inside_a_longer_one_does_not_hit(self):
        """「1」不该在「10/16」里蒙混过关（数字项按整项比）。"""
        result = self.check("1", "开臂 resolved 10/16")
        self.assertFalse(result["ok"])
        self.assertEqual(result["mode"], "numbers")

    def test_thousands_separators_are_normalized(self):
        self.assertTrue(self.check("1,234", "total 1,234 items")["ok"])
        self.assertTrue(self.check("1234", "total 1,234 items")["ok"])

    def test_percent_sign_is_normalized(self):
        self.assertTrue(self.check("56.25%", "合计 = 56.25%")["ok"])
        self.assertTrue(self.check("56.25%", "合计 = 56.25\\%")["ok"])
        self.assertFalse(self.check("56.25%", "合计 = 56.25")["ok"],
                         "百分号不能被糊弄过去")

    def test_latex_fraction_is_normalized(self):
        self.assertTrue(self.check("10/16", "结果 \\frac{10}{16} 更好")["ok"])

    def test_units_are_not_compared(self):
        """单位写法千差万别，不参与比较（产物 16 instances、value 16 算命中）。"""
        self.assertTrue(self.check("16", "16 instances resolved")["ok"])

    def test_full_width_digits_are_normalized(self):
        self.assertTrue(self.check("16", "１６ 题")["ok"])

    def test_value_without_digits_is_compared_as_text(self):
        result = self.check("请求体里搜不到 _asciidoc_row",
                            "日志：请求体里搜不到 _asciidoc_row 之类")
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "text")

    def test_a_fabricated_number_never_hits(self):
        result = self.check("17/16", "开臂 resolved 10/16")
        self.assertFalse(result["ok"])
        self.assertIn("17", result["missing"])


class ValueGuardTests(unittest.TestCase):
    """建单那一步：命中不了就拒建单，并说清为什么。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-value-guard-"))
        self.disk = make_disk(self.tmp)
        self.state = self.tmp / "state"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def body(self, **over):
        body = {"id": "Z9", "claim": "新增主张", "value": "56.25%",
                "source": "results/sample.md", "locator": "§二 汇总表",
                "confidence": "high"}
        body.update(over)
        return body

    def propose(self, **over):
        return create_proposal(self.state, "p", "d", self.disk,
                               dict(self.body(**over), kind="add_fact"))

    def test_a_value_in_the_artifact_is_accepted(self):
        record = self.propose()
        self.assertEqual(record["kind"], "add_fact")
        self.assertIn('id = "Z9"', record["proposed_text"])

    def test_a_value_outside_the_artifact_is_refused(self):
        with self.assertRaises(ConfigError) as ctx:
            self.propose(value="17/16")
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         "VALUE_NOT_IN_SOURCE")
        message = str(ctx.exception)
        self.assertIn("17", message)
        self.assertIn("results/sample.md", message)
        self.assertIn("§二 汇总表", message)

    def test_the_error_carries_machine_readable_slots(self):
        with self.assertRaises(ConfigError) as ctx:
            self.propose(value="17/16")
        params = getattr(ctx.exception, "params", None) or {}
        self.assertEqual(params.get("value"), "17/16")
        self.assertEqual(params.get("source"), "results/sample.md")
        self.assertEqual(params.get("locator"), "§二 汇总表")
        self.assertIn("17", params.get("missing") or "")

    def test_a_non_text_artifact_is_refused(self):
        (self.disk / "results" / "bin.md").write_bytes(b"\x00\x01\xff\xfe")
        with self.assertRaises(ConfigError) as ctx:
            self.propose(source="results/bin.md")
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         "VALUE_SOURCE_NOT_TEXT")

    def test_a_missing_source_is_still_refused_by_the_old_gate(self):
        """_check_source 的口径没变：产物不存在照样拒（这里先撞上它）。"""
        with self.assertRaises(ConfigError) as ctx:
            self.propose(source="results/nope.md")
        self.assertNotEqual(getattr(ctx.exception, "code", ""),
                            "VALUE_NOT_IN_SOURCE")

    def test_the_ledger_is_not_touched_by_a_refused_proposal(self):
        with self.assertRaises(ConfigError):
            self.propose(value="17/16")
        ledger = (self.disk / "facts" / "01-core.toml").read_text(encoding="utf-8")
        self.assertNotIn("Z9", ledger)


class LedgerFingerprintTests(unittest.TestCase):
    """before_sha 指纹闸：账本被别处改过 → 采纳时拒写（BLOCK_STALE）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-guard-sha-"))
        self.disk = make_disk(self.tmp)
        self.state = self.tmp / "state"
        self.ledger = self.disk / "facts" / "01-core.toml"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def body(self, **over):
        body = {"id": "Z9", "claim": "新增主张", "value": "56.25%",
                "source": "results/sample.md", "locator": "§二 汇总表",
                "confidence": "high"}
        body.update(over)
        return body

    def propose(self, **over):
        return create_proposal(self.state, "p", "d", self.disk,
                               dict(self.body(**over), kind="add_fact"))

    def test_the_proposal_carries_the_ledger_fingerprint(self):
        import hashlib
        record = self.propose()
        digest = hashlib.sha256(self.ledger.read_bytes()).hexdigest()
        self.assertEqual(record["before_sha"], digest)

    def test_a_ledger_changed_elsewhere_is_refused_on_apply(self):
        record = self.propose(id="Z10")
        before = self.ledger.read_text(encoding="utf-8")
        with open(self.ledger, "a", encoding="utf-8") as handle:
            handle.write("\n[[fact]]\nid = \"EXT1\"\n")
        with self.assertRaises(ConfigError) as ctx:
            apply_proposal(self.disk, record)
        self.assertEqual(getattr(ctx.exception, "code", ""), "BLOCK_STALE")
        text = self.ledger.read_text(encoding="utf-8")
        self.assertIn("EXT1", text, "别人的追加不该被抹掉")
        self.assertNotIn("Z10", text, "拒写就是没写")

    def test_a_new_ledger_created_elsewhere_is_refused_on_apply(self):
        """提议时账本还不存在；采纳前它被别人建出来了 → 同样拒写。"""
        record = self.propose(id="Z11", ledger="facts/02-core.toml")
        self.assertTrue(record.get("before_absent"))
        (self.disk / "facts" / "02-core.toml").write_text(
            "[[fact]]\nid = \"EXT2\"\n", encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            apply_proposal(self.disk, record)
        self.assertEqual(getattr(ctx.exception, "code", ""), "BLOCK_STALE")
        self.assertIn("EXT2",
                      (self.disk / "facts" / "02-core.toml").read_text(encoding="utf-8"))

    def test_adopting_writes_exactly_the_preview(self):
        record = self.propose()
        applied = apply_proposal(self.disk, record)
        self.assertTrue(applied["ok"])
        text = self.ledger.read_text(encoding="utf-8")
        self.assertIn(record["proposed_text"].strip(), text)


if __name__ == "__main__":
    unittest.main()
