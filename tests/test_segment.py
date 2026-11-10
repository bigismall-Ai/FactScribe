# -*- coding: utf-8 -*-
"""批 104：中文分词底座（纯标准库、全离线）。

规范：`docs/design/SPEC-SEGMENT.md`；读数：`docs/implementation/SEGMENT.md`。

覆盖：

* 两个经典歧义句：`研究生命起源`、`南京市长江大桥`；
* 未登录字按单字切；
* 英文/数字/标点原样保留；
* 空串；
* 确定性（同输入两次调用逐项相等）；
* 下标契约（`text[start:end] == token`）；
* 10 字上限（超长词条不会被整条吞下）；
* `load()` 进程内缓存。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.segment import load, segment  # noqa: E402


def tokens(text: str) -> list[str]:
    return [t for t, _s, _e, _p in segment(text)]


class TestSegmentAmbiguity(unittest.TestCase):
    def test_research_life_origin_prefers_common_words(self):
        # 逐位最长会切成 研究生/命/起源；词频仲裁选 研究/生命/起源。
        self.assertEqual(tokens("研究生命起源"), ["研究", "生命", "起源"])

    def test_nanjing_mayor_jiang_bridge(self):
        # 逐位按词频贪心会切成单字或 南京/市长/江/大桥；
        # 整段词频仲裁选自然读法。
        self.assertEqual(tokens("南京市长江大桥"), ["南京市", "长江大桥"])

    def test_positions_are_attached(self):
        out = segment("研究生命起源")
        self.assertEqual([p for _t, _s, _e, p in out],
                         ["vn", "vn", "n"])

    def test_unknown_chars_split_one_by_one(self):
        out = segment("龘靐龖")
        self.assertEqual([t for t, _s, _e, _p in out], ["龘", "靐", "龖"])
        self.assertEqual([p for _t, _s, _e, p in out], ["", "", ""])


class TestSegmentBoundaries(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(segment(""), [])

    def test_mixed_latin_digits_preserved(self):
        text = "我在用Python3.10做实验。"
        out = segment(text)
        self.assertEqual(tokens(text),
                         ["我", "在", "用", "Python3.10", "做", "实验", "。"])
        # 非中文块原样保留、词性为空。
        latin = [x for x in out if x[0] == "Python3.10"][0]
        self.assertEqual(latin[3], "")

    def test_offsets_slice_back_to_token(self):
        for text in ("研究生命起源", "南京市长江大桥", "我在用Python3.10做实验。",
                     "会议进行时，请不要打扰。"):
            with self.subTest(text=text):
                out = segment(text)
                self.assertEqual("".join(t for t, _s, _e, _p in out), text)
                for token, start, end, _pos in out:
                    self.assertEqual(text[start:end], token)

    def test_max_word_length_is_ten(self):
        # 词表里最长的一条是 16 字；上限 10 字后不许整条吐出。
        out = segment("侵华日军南京大屠杀遇难同胞纪念馆")
        self.assertTrue(out)
        self.assertLessEqual(max(len(t) for t, _s, _e, _p in out), 10)


class TestSegmentDeterminism(unittest.TestCase):
    def test_same_input_same_output(self):
        text = "研究生命起源，南京市长江大桥，Python3.10。"
        self.assertEqual(segment(text), segment(text))

    def test_load_is_cached(self):
        first = load()
        second = load()
        self.assertIs(first, second)
        self.assertGreater(len(first), 300000)


if __name__ == "__main__":
    unittest.main()
