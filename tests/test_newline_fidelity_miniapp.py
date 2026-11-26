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



class SharedCarriersTest(unittest.TestCase):
    """共享模块里的用户内容载体：bib、factscribe.toml、报告文件、PDF 临时副本。

    这些模块（citeedit／citations／citeview／projects／reportapi／buildpdf）
    与上游同源，但落在 MiniApp 线的镜像里，跟着改 bib、改声明文件、
    出报告、编译 PDF 的路径都会碰到——写盘不翻译换行的口径必须一致。
    """

    def setUp(self):
        # 落在解析后就是原样的目录下（macOS 的 /var → /private/var 是软链，
        # 项目根的两种拼法会让别的模块的相对路径算不出来——那是本线自己
        # 的项目根口径问题，与这里要验的换行保真无关）。
        self.tmp = Path(tempfile.mkdtemp(
            prefix="fs-crlf-shared-", dir=str(Path(tempfile.gettempdir()).resolve())))
        self.disk = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.disk)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_crlf_bib(self) -> Path:
        bib = self.disk / "refs.bib"
        bib.write_bytes(("@article{k1,\r\n"
                         "  title = {A},\r\n"
                         "  year = {2020}\r\n"
                         "}\r\n").encode("utf-8"))
        return bib

    def test_bib_append_keeps_existing_bytes(self):
        """bib 原子写：原有条目一个字节都不许动。"""
        from factscribe.citeedit import citation_add_data
        bib = self._write_crlf_bib()
        before = bib.read_bytes()
        citation_add_data(self.disk, {"key": "k2", "title": "B",
                                      "author": "X", "year": "2024"},
                          allow_write=True)
        after = bib.read_bytes()
        self.assertTrue(after.startswith(before),
                        "追加 bib 条目把原有字节改了")
        self.assertEqual(after.count(b"\r\n"), before.count(b"\r\n"),
                         "原有 CRLF 被改掉了")
        self.assertIn(b"@article{k2,", after)

    def test_bib_write_call_site_does_not_translate(self):
        """参数证据：bib 写盘走 newline=""（不翻译换行）。"""
        from factscribe.citeedit import citation_add_data
        bib = self._write_crlf_bib()
        recorder = _OpenRecorder()
        with _PatchedOpen(recorder):
            citation_add_data(self.disk, {"key": "k2", "title": "B"},
                              allow_write=True)
        calls = recorder.for_path(bib)
        self.assertTrue(calls, "bib 没有经过 open() 写")
        for mode, newline in calls:
            if any(ch in mode for ch in ("w", "a", "x")):
                self.assertEqual(newline, "",
                                 "写用户 bib 不许走会翻译换行的文本模式")

    def test_parse_bib_reads_crlf_bib(self):
        """读侧：CRLF 的 bib 照样能解析出条目。"""
        from factscribe.citations import parse_bib
        bib = self._write_crlf_bib()
        entries = parse_bib(bib, self.disk.resolve())
        self.assertEqual([e.key for e in entries], ["k1"])

    def test_citeview_read_keeps_crlf(self):
        """读侧：正文按原样读，CRLF 原样在。"""
        from factscribe.citeview import _read
        tex = self.disk / "sections" / "01-intro.tex"
        tex.write_bytes(SECTION_CRLF.encode("utf-8"))
        self.assertIn("\r\n", _read(tex))

    def test_factscribe_toml_rewrite_keeps_crlf(self):
        """factscribe.toml 改写：只改那一个键，别的行与行尾都不动。"""
        from factscribe.projects import _rewrite_project_table
        cfg = self.disk / "factscribe.toml"
        raw = ('[project]\r\n'
               'title = "旧题"\r\n'
               'description = "说明"\r\n')
        cfg.write_bytes(raw.encode("utf-8"))
        _rewrite_project_table(cfg, {"title": '"新题"'})
        after = cfg.read_bytes()
        self.assertIn('description = "说明"\r\n'.encode("utf-8"), after)
        self.assertIn('title = "新题"\r\n'.encode("utf-8"), after)
        self.assertEqual(after.count(b"\r\n"), raw.count("\r\n"))
        self.assertNotIn(b"\n", after.replace(b"\r\n", b""))

    def test_report_write_keeps_bytes(self):
        """报告文件：写盘逐字节（用户填的数字与注释不换行）。"""
        from factscribe.reportapi import _write_atomic
        target = self.disk / "notes.report.toml"
        text = "value = 42\r\n# 用户的注释\r\n"
        _write_atomic(target, text)
        self.assertEqual(target.read_bytes(), text.encode("utf-8"))

    def test_buildpdf_temp_copy_uses_exact_write(self):
        """调用点证据：PDF 临时副本按原样读写（逐字节对应源文件）。"""
        src = (ROOT / "factscribe" / "buildpdf.py").read_text(encoding="utf-8")
        self.assertIn("read_text_exact(target)", src)
        self.assertIn("write_text_exact(target, patched)", src)


if __name__ == "__main__":
    unittest.main()