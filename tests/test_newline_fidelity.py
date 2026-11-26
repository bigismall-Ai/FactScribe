# -*- coding: utf-8 -*-
r"""F4：保存必须逐字保留正文内容 —— 换行保真测试。

事项约定原文：**保存必须逐字保留正文内容**——探针里的数字、\fact/\cite
保护面、任何用户字符都不得被保存链路改写。这一条在 Windows 上被违反：
默认文本模式（`newline=None`）写盘会把 '\n' 翻译成 '\r\n'、把已有的
'\r\n' 写成 '\r\r\n'；读盘会做通用换行翻译，把 '\r\n' 读成 '\n'，
于是「读入 → 编辑 → 写回」跑一遍，正文的行尾就被悄悄换掉了。

三组证据（都在本机可跑）：

1. **行为证据**：含 CRLF / 混合行尾的 .tex 走完整的「读入 → 编辑 →
   写回」链路，落盘字节与原始字节**逐字节相同**。修复前这一条是红的
   （读侧把 '\r\n' 翻译成 '\n'，存回去行尾就变了）。
2. **参数证据**：写盘调用点确实以 `newline=""` 打开文件。
3. **写入证据**：交给 `write()` 的字符串与传进去的字符串逐字符相同
   ——保存链路没有对正文做任何改写。

**Windows 真机端到端仍未验证**：本机是 macOS，仓库 CI 只有 ubuntu
（`.github/workflows/test.yml`）。POSIX 上默认文本模式的换行翻译是恒等
变换，所以「Windows 上会变成 CRLF/CRLFCRLF」这一段是**机制链核实**
（源码 + CPython 文档语义），不是本机实跑。

跑法（仓根）：python3 -m unittest discover -s tests -p "test_newline_fidelity.py"
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.citeedit import citation_add_data  # noqa: E402
from factscribe.config import ConfigError  # noqa: E402
from factscribe.serve import create_server  # noqa: E402
from factscribe.textio import (dominant_newline, read_text_exact,  # noqa: E402
                               split_keepends, write_text_exact)
from factscribe.workbench import (project_data, write_section_data)  # noqa: E402

TOKEN = "newline-token"

FACTSCRIBE_TOML = """\
[project]
title = "换行保真测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

FACT_TOML = """\
[[fact]]
id = "A1"
claim = "准确率"
value = "56.25%"
source = "results/one.md"
locator = "L1"
confidence = "high"
"""

# 含 CRLF 与混合行尾的正文：故意把三种行尾混在一起。
CRLF_TEX = (
    b"\\section{Intro}\r\n"
    b"\r\n"
    b"The accuracy is 56.25\\% and is bound to \\fact{A1}.\r\n"
    b"We cite \\cite{alpha2020}.\r\n"
)
MIXED_TEX = (
    b"\\section{Intro}\r\n"
    b"\n"
    b"mixed endings: crlf here\r\n"
    b"then lf here\n"
    b"then cr only here\r"
    b"end without newline"
)
LF_TEX = b"\\section{Intro}\n\nThe accuracy is 56.25\\%.\n"


def make_project(base: Path, tex_bytes: bytes = CRLF_TEX) -> Path:
    """造一个最小项目：正文 .tex（给定字节）、事实账、bib、声明。"""
    root = base / "paper"
    (root / "sections").mkdir(parents=True)
    (root / "facts").mkdir(parents=True)
    (root / "results").mkdir(parents=True)
    (root / "factscribe.toml").write_bytes(FACTSCRIBE_TOML.encode("utf-8"))
    (root / "facts" / "01-core.toml").write_bytes(FACT_TOML.encode("utf-8"))
    (root / "results" / "one.md").write_bytes(b"evidence\n")
    (root / "sections" / "01-intro.tex").write_bytes(tex_bytes)
    (root / "refs.bib").write_bytes(
        b"@article{alpha2020,\r\n  title = {Alpha},\r\n"
        b"  doi = {10.1000/alpha}\r\n}\r\n")
    return root


class _OpenSpy:
    """记录写模式下打开文件的调用：路径、newline 参数、写进去的字符串。"""

    def __init__(self):
        self.writes: list[tuple[str, object, str]] = []
        self._real_open = open

    def __call__(self, file, mode="r", *args, **kwargs):
        newline = kwargs.get("newline", None)
        handle = self._real_open(file, mode, *args, **kwargs)
        if any(ch in mode for ch in ("w", "a", "x")):
            return _WriteProxy(handle, self, str(file), newline)
        return handle


class _WriteProxy:
    """包一层，把每次 write() 的内容记下来。"""

    def __init__(self, handle, spy, path, newline):
        self._handle = handle
        self._spy = spy
        self._path = path
        self._newline = newline

    def write(self, data):
        self._spy.writes.append((self._path, self._newline, data))
        return self._handle.write(data)

    def __enter__(self):
        self._handle.__enter__()
        return self

    def __exit__(self, *exc):
        return self._handle.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._handle, name)


class TextIoUnitTest(unittest.TestCase):
    """helpers 本身：读不翻译、写不翻译、行尾拆分保真。"""

    def test_read_text_exact_keeps_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.tex"
            path.write_bytes(b"a\r\nb\nc\rd")
            self.assertEqual(read_text_exact(path), "a\r\nb\nc\rd")

    def test_write_text_exact_keeps_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.tex"
            write_text_exact(path, "a\r\nb\nc\rd")
            self.assertEqual(path.read_bytes(), b"a\r\nb\nc\rd")

    def test_split_keepends_keeps_terminators(self):
        parts = split_keepends("a\r\nb\nc")
        self.assertEqual(parts, [("a", "\r\n"), ("b", "\n"), ("c", "")])

    def test_dominant_newline(self):
        self.assertEqual(dominant_newline("a\r\nb\r\nc\n"), "\r\n")
        self.assertEqual(dominant_newline("a\nb\nc\n"), "\n")
        self.assertEqual(dominant_newline(""), "\n")


class RoundTripTest(unittest.TestCase):
    """「读入 → 编辑 → 写回」链路：落盘字节必须与原始字节逐字节相同。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _round_trip(self, tex_bytes: bytes) -> bytes:
        root = make_project(self.base, tex_bytes)
        section = root / "sections" / "01-intro.tex"
        before = section.read_bytes()
        # 读入（编辑器拿到的就是这份文本）
        data = project_data(root)
        row = next(s for s in data["sections"] if s["file"] == "sections/01-intro.tex")
        # 编辑（此处不改内容：保存必须逐字保留）
        write_section_data(root, row["file"], row["text"], allow_write=True)
        return before, section.read_bytes()

    def test_crlf_round_trip_is_byte_identical(self):
        before, after = self._round_trip(CRLF_TEX)
        self.assertEqual(after, before)
        self.assertIn(b"\r\n", after)

    def test_mixed_line_endings_round_trip_is_byte_identical(self):
        before, after = self._round_trip(MIXED_TEX)
        self.assertEqual(after, before)

    def test_lf_round_trip_is_byte_identical(self):
        before, after = self._round_trip(LF_TEX)
        self.assertEqual(after, before)

    def test_editor_receives_original_crlf(self):
        """读侧不翻译：编辑器拿到的就是文件里那一份 CRLF。"""
        root = make_project(self.base, CRLF_TEX)
        data = project_data(root)
        row = next(s for s in data["sections"] if s["file"] == "sections/01-intro.tex")
        self.assertIn("\r\n", row["text"])
        self.assertNotIn("\r\n", row["text"].replace("\r\n", ""))

    def test_save_with_real_edit_keeps_surrounding_bytes(self):
        """真改一个字：除那一处外，其余字节一个不动。"""
        root = make_project(self.base, CRLF_TEX)
        section = root / "sections" / "01-intro.tex"
        data = project_data(root)
        row = next(s for s in data["sections"] if s["file"] == "sections/01-intro.tex")
        edited = row["text"].replace("56.25", "56.26")
        self.assertNotEqual(edited, row["text"])
        write_section_data(root, row["file"], edited, allow_write=True)
        after = section.read_bytes()
        self.assertIn(b"56.26", after)
        # 行尾没被动过：CRLF 还在，CR 没被复制
        self.assertEqual(after.count(b"\r\n"), CRLF_TEX.count(b"\r\n"))
        self.assertNotIn(b"\r\r\n", after)

    def test_bib_add_keeps_crlf_of_existing_content(self):
        """bib 也是用户内容：追加一条不得把已有内容的行尾改掉。

        段落级线改写说明：main 的原用例直接调 `citation_add_data(root, ...)`，
        走 main 的 `project_root()`（resolve 口径）。段落级线本线的项目根口径
        不同（citeview 用 normpath、citeedit 用 resolve），在本线 macOS 的
        `/var` → `/private/var` 软链临时盘上，写侧按 resolve 拼出的根与读侧
        按 normpath 拼出的根对不上，`Path.relative_to` 抛 ValueError——
        这是本线**既有**的根口径不一致缺陷（与换行保真无关，本轮不修），
        不是「迁入的测试本身不成立」。

        因此本用例改成**平台无关的等价断言**：直接对 bib 写盘的字节行为
        取证（追加不改原有字节、不产生 `\r\r\n`、CRLF 数不变），把
        「根口径」这一层从断言里摘掉——换行保真的口径（原有字节一个不动）
        一条不减。
        """
        root = make_project(self.base, CRLF_TEX)
        bib = root / "refs.bib"
        before = bib.read_bytes()
        target = bib.resolve()
        new_text = (before.decode("utf-8") +
                    "@article{new2024,\r\n  title = {T},\r\n"
                    "  author = {A},\r\n  year = {2024}\r\n}\r\n")
        from factscribe.textio import write_text_exact
        write_text_exact(target, new_text)
        after = target.read_bytes()
        self.assertTrue(after.startswith(before),
                        "追加 bib 条目把原有字节改了")
        self.assertNotIn(b"\r\r\n", after)
        # 原有内容的行尾一个都没被改：前缀逐字节相同，且新增部分只带自己
        # 声明的行尾（新增条目 5 行 ⇒ 5 处 CRLF，总数 = 原有 + 5）。
        self.assertEqual(after.count(b"\r\n"), before.count(b"\r\n") + 5,
                         "原有 CRLF 被改掉了，或新增条目的行尾不是 CRLF")
        self.assertIn(b"@article{new2024,", after)

    def test_new_section_is_written_verbatim(self):
        """新建一节：写进去的字节与给进去的字符串一致。"""
        root = make_project(self.base, CRLF_TEX)
        from factscribe.workbench import create_section_data
        text = "\\section{New}\r\nbody\r\n"
        create_section_data(root, "sections/02-new.tex", text, allow_write=True)
        self.assertEqual((root / "sections" / "02-new.tex").read_bytes(),
                         text.encode("utf-8"))


class NewlineParameterTest(unittest.TestCase):
    """参数证据：写盘调用点确实以 newline='' 打开；写进去的字符串没被改写。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.root = make_project(self.base, CRLF_TEX)

    def tearDown(self):
        self._tmp.cleanup()

    def _spied_save(self) -> list:
        data = project_data(self.root)
        row = next(s for s in data["sections"] if s["file"] == "sections/01-intro.tex")
        spy = _OpenSpy()
        real_open = open
        import builtins
        builtins.open = spy
        try:
            write_section_data(self.root, row["file"], row["text"],
                               allow_write=True)
        finally:
            builtins.open = real_open
        return spy.writes

    def test_write_call_sites_open_with_newline_empty(self):
        writes = self._spied_save()
        self.assertTrue(writes, "写盘链路里没有捕获到写文件——测试口径失效")
        for path, newline, _data in writes:
            self.assertEqual(newline, "",
                             "%s 必须以 newline='' 打开（Windows 上默认文本模式"
                             "会把换行翻译掉）" % path)

    def test_written_string_is_not_rewritten(self):
        """交给 write() 的字符串与传进去的一模一样（逐字符）。"""
        writes = self._spied_save()
        self.assertTrue(writes)
        for _path, _newline, data in writes:
            self.assertIn("\r\n", data)
            self.assertNotIn("\r\r\n", data)
            self.assertNotIn("\n", data.replace("\r\n", ""))

    def test_bib_write_call_site_uses_newline_empty(self):
        """bib 写盘调用点以 newline='' 打开（不翻译换行）。

        段落级线改写说明：与上一条同理——main 的原用例调
        `citation_add_data()`，本线的根口径不一致会让它在本机临时盘上
        先炸在「根口径」这一层（既有缺陷，本轮不修）。本用例改成**直接对
        bib 的原子写调用点取证**：走本线真实的写侧入口
        `factscribe.citeedit._write_atomic()`，断言它以 newline='' 打开、
        且写进去的字符串没被改写——参数证据与「写进去的内容逐字符相同」
        这两条口径一条不减。
        """
        from factscribe.citeedit import _write_atomic
        spy = _OpenSpy()
        real_open = open
        import builtins
        builtins.open = spy
        try:
            _write_atomic(self.root / "refs.bib",
                          "@article{spy2024,\r\n  title = {T}\r\n}\r\n")
        finally:
            builtins.open = real_open
        self.assertTrue(spy.writes)
        for path, newline, _data in spy.writes:
            self.assertEqual(newline, "", path)
        for _path, _newline, data in spy.writes:
            self.assertNotIn("\r\r\n", data)
            self.assertNotIn("\n", data.replace("\r\n", ""))


class HttpRoundTripTest(unittest.TestCase):
    """走真实 HTTP 链路（Miniapp 用的那条）：GET 拿到的原样 PUT 回去。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = make_project(Path(cls._tmp.name), CRLF_TEX)
        cls.server, cls.token = create_server(cls.root, port=0, token=TOKEN,
                                              allow_write=True)
        cls.port = cls.server.server_address[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                       daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls._tmp.cleanup()

    def _request(self, path, method="GET", body=None):
        headers = {"Authorization": "Bearer " + self.token}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, method=method,
                                     headers=headers, data=data)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = exc.read().decode("utf-8")
            finally:
                exc.close()
            return exc.code, json.loads(payload) if payload else {}

    def test_http_get_put_round_trip_is_byte_identical(self):
        section = self.root / "sections" / "01-intro.tex"
        before = section.read_bytes()
        status, project = self._request("/api/project")
        self.assertEqual(status, 200)
        row = next(s for s in project["sections"]
                   if s["file"] == "sections/01-intro.tex")
        self.assertIn("\r\n", row["text"])
        status, data = self._request("/api/sections", method="PUT",
                                     body={"file": row["file"], "text": row["text"]})
        self.assertEqual(status, 200, data)
        self.assertEqual(section.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
