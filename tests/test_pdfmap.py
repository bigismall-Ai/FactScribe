# -*- coding: utf-8 -*-
"""节标题 → PDF 页码（纯文本判断，不依赖 pdftotext）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.pdfmap import pick_page, section_title, split_pages  # noqa: E402


class SectionTitleTest(unittest.TestCase):
    def test_plain_title(self):
        self.assertEqual("任务挑选与排除",
                         section_title("\\section{任务挑选与排除}\n正文"))

    def test_starred_and_macros(self):
        self.assertEqual("A B C",
                         section_title("\\section*{\\textbf{A} B~C}"))

    def test_no_section(self):
        self.assertEqual("", section_title("没有标题"))


class PickPageTest(unittest.TestCase):
    def test_skips_toc_page(self):
        pages = ["目录\n任务挑选与排除 ...... 15\n", "正文第一页", "任务挑选与排除\n正文"]
        self.assertEqual(3, pick_page(pages, "任务挑选与排除"))

    def test_missing_returns_zero(self):
        self.assertEqual(0, pick_page(["别的"], "任务挑选与排除"))

    def test_split_pages(self):
        self.assertEqual(["a", "b"], split_pages("a\fb"))


if __name__ == "__main__":
    unittest.main()
