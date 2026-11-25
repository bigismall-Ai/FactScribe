# -*- coding: utf-8 -*-
r"""社区包块编辑链与 dataplayer 链的换行保真（CRLF 不丢）。

这一组用例守的是 miniapp 用户真正会踩到的两条保存链：

1. **块编辑链**（/api/disk/.../edit → factscribe/workbench/write.py）：
   客户端拿到的块原文、行尾必须与磁盘上的一致；保存回去时，块以外的
   字节一个都不许动——CRLF 的盘不许被写成 LF。
2. **dataplayer 链**（/api/sections → factscribe/workbench_dataplayer.py）：
   接口下发的正文是原字节，存回去也按原字节。

三组证据：

* **行为证据**：含 CRLF／混合行尾的 .tex 走完整链路，落盘字节与原始
  字节**逐字节相同**；
* **参数证据**：读盘调用点以 newline="" 打开（不翻译），写盘调用点
  走二进制写（不翻译）；
* **读侧证据**：下发给客户端的块原文里，CRLF 原样在。

**Windows 真机端到端仍未验证**：本机是 macOS，仓库 CI 矩阵只有 ubuntu。

跑法（仓根）：python3 -m unittest discover -s tests -p "test_newline_fidelity_miniapp.py"
"""
from __future__ import annotations

import builtins
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench.projects import (bound_values_of,  # noqa: E402
                                            disk_sections, token_of)
from factscribe.workbench.write import find_block, save_block, scan  # noqa: E402
from factscribe.workbench_dataplayer import write_section_data  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"

#: 这一段的正文：数字**紧贴** \fact{}（绑定数字令牌因此成立）。
SECTION_CRLF = (
    "\\label{sec:intro}\r\n"
    "\r\n"
    "开臂解决 10\\fact{A1}，对比臂解决 8\\fact{A3}。\r\n"
)

SECTION_MIXED = (
    "\\label{sec:intro}\r\n"
    "\n"
    "mixed: crlf here\r\n"
    "then lf here\n"
    "尾行没有换行"
)


def _payload(raw, bound_values):
    """按服务端扫描结果拼一份「散文＋占位符」的提交文本（前端同口径）。"""
    parts = []
    for seg in scan(raw, bound_values):
        parts.append(seg.text if seg.kind == "text" else token_of(seg.index))
    return "".join(parts)


class _OpenRecorder:
    """记录所有 open() 调用：路径、模式、newline 参数。"""

    def __init__(self):
        self.calls = []
        self._real_open = builtins.open

    def __call__(self, file, mode="r", *args, **kwargs):
        self.calls.append((str(file), mode, kwargs.get("newline", None)))
        return self._real_open(file, mode, *args, **kwargs)

    def for_path(self, path: Path):
        return [(mode, newline) for (f, mode, newline) in self.calls
                if os.path.abspath(f) == os.path.abspath(str(path))]


class _PatchedOpen:
    def __init__(self, recorder: _OpenRecorder):
        self._recorder = recorder
        self._real = builtins.open

    def __enter__(self):
        builtins.open = self._recorder
        return self._recorder

    def __exit__(self, *exc):
        builtins.open = self._real
        return False


class BlockEditChainTest(unittest.TestCase):
    """社区包块编辑链：/api/disk/.../edit → workbench/write.py。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-crlf-block-"))
        self.disk = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.disk)
        self.rel = "sections/01-intro.tex"
        self.file = self.disk / self.rel

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _block_id(self):
        for block in disk_sections(self.disk).get("blocks") or []:
            if str(block.get("file")) == self.rel and block.get("kind") == "para":
                return str(block.get("id"))
        self.fail("样例盘里找不到段落块")

    def _save_once(self, text: str):
        self.file.write_bytes(text.encode("utf-8"))
        before = self.file.read_bytes()
        block = find_block(self.disk, self.rel, self._block_id())
        bound = bound_values_of(self.disk)
        client = _payload(block.raw, bound)
        save_block(self.disk, self.rel, block.block_id, client,
                   expect_sha=block.sha if hasattr(block, "sha") else "",
                   expect_tokens="")
        after = self.file.read_bytes()
        return before, after, block

    def test_crlf_block_save_is_byte_identical(self):
        before, after, block = self._save_once(SECTION_CRLF)
        self.assertEqual(before, after, "块保存把 CRLF 正文改掉了")
        self.assertEqual(after.count(b"\r\n"), before.count(b"\r\n"))

    def test_mixed_line_endings_block_save_is_byte_identical(self):
        before, after, block = self._save_once(SECTION_MIXED)
        self.assertEqual(before, after, "块保存把混合行尾正文改掉了")

    def test_delivered_block_keeps_crlf(self):
        """读侧证据：下发给客户端的块原文里 CRLF 原样在。"""
        self.file.write_bytes(SECTION_CRLF.encode("utf-8"))
        block = find_block(self.disk, self.rel, self._block_id())
        self.assertIn("\r\n", block.raw)

    def test_read_and_write_call_sites_do_not_translate(self):
        """参数证据：读盘走 newline=""，写盘走二进制（都不翻译换行）。"""
        self.file.write_bytes(SECTION_CRLF.encode("utf-8"))
        block = find_block(self.disk, self.rel, self._block_id())
        bound = bound_values_of(self.disk)
        client = _payload(block.raw, bound)
        recorder = _OpenRecorder()
        with _PatchedOpen(recorder):
            save_block(self.disk, self.rel, block.block_id, client,
                       expect_sha="", expect_tokens="")
        calls = recorder.for_path(self.file)
        self.assertTrue(calls, "正文没有经过 open() 读写")
        for mode, newline in calls:
            if mode == "r":
                self.assertEqual(newline, "",
                                 "读用户正文必须以 newline=\"\" 打开")
            elif any(ch in mode for ch in ("w", "a", "x")):
                self.assertEqual(newline, "",
                                 "写用户正文不许走会翻译换行的文本模式")


class DataPlayerChainTest(unittest.TestCase):
    """dataplayer 链：/api/sections → workbench_dataplayer.py。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-crlf-dl-"))
        self.disk = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.disk)
        self.rel = "sections/01-intro.tex"
        self.file = self.disk / self.rel

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_section_save_is_byte_identical(self):
        text = SECTION_CRLF
        self.file.write_bytes(text.encode("utf-8"))
        before = self.file.read_bytes()
        write_section_data(self.disk, self.rel, text, allow_write=True)
        after = self.file.read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(after.count(b"\r\n"), text.count("\r\n"))


if __name__ == "__main__":
    unittest.main()