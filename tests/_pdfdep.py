# -*- coding: utf-8 -*-
"""PDF 层测试的二进制依赖标记（poppler：pdftotext / pdfinfo / pdfimages）。

为什么要有：PDF 回检要调外部命令，本机（macOS + brew poppler）有、CI runner 装不上。
以前缺工具时这些用例直接红，把「环境没装好」误报成「代码坏了」。
现在缺 pdftotext 就跳过并计数（`skipped=` 会显示在测试尾部），装了则照常全跑。

用法：
    from _pdfdep import requires_pdftotext

    @requires_pdftotext
    class PdfMaskingTest(unittest.TestCase): ...
    # 或用例级：类里混有纯逻辑用例时只标真正调二进制的那些。

甄别纪律：只标**真的会执行 `pdftotext`/`pdfinfo`/`pdfimages`** 的用例。
纯逻辑与夹具（`structural_whitelist`、`pdf_number_counts`、mock 掉 `missing_tools` 的
`test_missing_poppler_fails_closed` 等）一律不标——本地缺工具时也要照常验。
"""
from __future__ import annotations

import shutil
import unittest

# 跳过条件只认 pdftotext：它是 PDF 文本层的主路径，缺它就整层跑不了。
requires_pdftotext = unittest.skipIf(
    shutil.which("pdftotext") is None,
    "缺 pdftotext（poppler）——PDF 层测试跳过；本机装 poppler 后即恢复",
)
