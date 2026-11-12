# -*- coding: utf-8 -*-
"""批 138：Python 原版 ↔ JS 移植件的一致性锁（Python 侧）。

锁的是什么：同一份夹具（tests/conformance/fixture）喂给两边，判出的**核心
错误码多重集**必须完全相等。不比行号、不比措辞——两边的文本模型不同，行号
和消息本来就不可能逐字一致；能锁的只有「哪几个码、各几次」。

核心码清单与期望读数都在 tests/conformance/expected.json：`core_codes` 是
「两边都实现、且已验证判得一样」的码，`codes` 是这份夹具的期望多重集。
为什么是这些、哪些码被排除，见 docs/design/SPEC-CONFORMANCE.md。

跑法（仓根）：
    env PYTHONPATH=src python3 -m unittest discover -s tests
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "tests" / "conformance"
FIXTURE = CONF / "fixture"
EXPECTED = CONF / "expected.json"
PROJECT = CONF / "project.json"
DUMP = ROOT / "scripts" / "conformance-dump.py"


def _expected() -> dict:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))


def _core_counts(codes: list[str], core: list[str]) -> dict[str, int]:
    """只留核心码，做成多重集（出现 0 次的码不写进结果）。"""
    wanted = set(core)
    return {k: v for k, v in Counter(c for c in codes if c in wanted).items()}


class TestPythonSideConformance(unittest.TestCase):
    """夹具 → factscribe audit → 核心码多重集 == expected.json。"""

    def test_core_code_multiset_matches_expected(self):
        expected = _expected()
        proc = subprocess.run(
            [sys.executable, "-m", "factscribe", "audit", str(FIXTURE), "--json"],
            cwd=str(ROOT), capture_output=True, text=True)
        self.assertIn(proc.returncode, (0, 1, 3, 5, 7),
                      "audit 没跑起来（配置/用法错）：\n%s" % proc.stderr)
        data = json.loads(proc.stdout)
        codes = [i["code"] for i in data.get("issues", [])]
        codes += [w["code"] for w in data.get("warnings", [])]
        got = _core_counts(codes, expected["core_codes"])
        self.assertEqual(got, expected["codes"],
                         "夹具的核心码多重集变了。若是有意改夹具/判据，请按 "
                         "docs/design/SPEC-CONFORMANCE.md §5 重生成 expected.json；"
                         "若没改，说明 Python 侧判据漂了。")
        # 夹具的红不是意外：三类红必须都在。
        for code in ("UNMATCHED_NUMBER", "BOUND_MISMATCH", "MISSING_CITE"):
            self.assertGreater(expected["codes"].get(code, 0), 0,
                               "夹具必须保留 %s 这一类红" % code)
        self.assertEqual(data.get("exit"), 1, "夹具应当判红（exit 1）")


class TestProjectionIsFresh(unittest.TestCase):
    """project.json 必须是投影脚本对当前夹具的逐字节输出。"""

    def _run_dump(self) -> bytes:
        proc = subprocess.run([sys.executable, str(DUMP), str(FIXTURE)],
                              cwd=str(ROOT), capture_output=True)
        self.assertEqual(proc.returncode, 0,
                         "投影脚本失败：%s" % proc.stderr.decode("utf-8", "replace"))
        return proc.stdout

    def test_projection_is_byte_identical_to_committed(self):
        got = self._run_dump()
        want = PROJECT.read_bytes()
        self.assertEqual(
            got, want,
            "tests/conformance/project.json 与投影结果不一致——改了夹具却忘了"
            "重生成。重生成：python3 scripts/conformance-dump.py "
            "tests/conformance/fixture > tests/conformance/project.json")

    def test_projection_is_deterministic_and_path_free(self):
        first = self._run_dump()
        second = self._run_dump()
        self.assertEqual(first, second, "投影不确定（排序/时间戳/随机性漏进来了）")
        text = first.decode("utf-8")
        self.assertNotIn(str(ROOT), text, "投影里漏出了本机绝对路径")
        self.assertNotIn("/private/", text, "投影里漏出了本机绝对路径")


class TestDiffListIsHonest(unittest.TestCase):
    """差异清单不是装饰：已修的差异要真的标成已修，且写明两侧同义。

    批 139 修的是同名不同义：JS 曾把「缺 source 字段」也叫 MISSING_SOURCE，
    而 Python 那个码指「来源文件不存在」。这里只锁文档口径——判据本身由
    两侧的审计测试守（JS 侧见 integrations/minifactscribe/tests/audit.test.mjs）。
    """

    SPEC = ROOT / "docs" / "design" / "SPEC-CONFORMANCE.md"

    def _row(self, code: str) -> list[str]:
        text = self.SPEC.read_text(encoding="utf-8")
        rows = [ln for ln in text.splitlines() if ln.startswith("| %s " % code)]
        self.assertEqual(len(rows), 1, "§7 差异清单里 %s 应恰好一行" % code)
        return [c.strip() for c in rows[0].strip().strip("|").split("|")]

    def test_missing_source_is_marked_fixed_and_same_meaning(self):
        cells = self._row("D1")
        self.assertEqual(len(cells), 5, "§7 的表格应有 5 列")
        _no, name, py, js, action = cells
        self.assertIn("MISSING_SOURCE", name)
        for side, cell in (("Python 原版", py), ("JS 移植件", js)):
            self.assertIn("来源文件不存在", cell,
                          "D1 的「%s」一列必须写明「来源文件不存在」——只写一列"
                          "等于语义仍可能分家" % side)
        self.assertIn("已修", action, "D1 修好后必须标成已修")

    def test_missing_source_field_code_is_named_on_both_sides(self):
        cells = self._row("D1b")
        _no, _name, py, js, action = cells
        for side, cell in (("Python 原版", py), ("JS 移植件", js)):
            self.assertIn("MISSING_SOURCE_FIELD", cell,
                          "D1b 的「%s」一列要写明 `MISSING_SOURCE_FIELD`"
                          "（不能仍写 `MISSING_SOURCE`）" % side)
        self.assertIn("已修", action, "D1b 修好后必须标成已修")


if __name__ == "__main__":
    unittest.main()
