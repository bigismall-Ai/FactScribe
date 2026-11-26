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

**浏览器那一层（网页工作台）**：编辑器是 `<textarea>`，HTML 规范把它的
API value 归一为 LF（本机实测：Chrome 158 headless 里 `textarea.value` 的
CRLF 与单独 CR 都变成 LF）。引擎侧若把浏览器交回的正文逐字写回，一份
CRLF 稿件**存一次就变成 LF**——正文内容一个字没动，行尾整篇被换掉。
写侧因此按**落盘原文**逐行还原行尾（`textio.restore_newlines`）：CRLF 稿
仍是 CRLF、LF 稿仍是 LF、混合稿逐行照旧，用户新输入的行用该节的主导
行尾。端到端那一组走真实的 `PUT /api/sections`。

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
                               restore_newlines, split_keepends,
                               write_text_exact)
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


def browser_text(text: str) -> str:
    """模拟浏览器的 `<textarea>`：行尾一律归一为 LF。

    HTML 规范规定 textarea 的 API value 把换行归一为 LF；本机实测
    （Chrome 158 headless）：`textarea.value` 里的 CRLF 与单独的 CR
    都变成 LF。网页工作台的编辑器就是 `<textarea>`，所以它交回给
    `PUT /api/sections` 的正文恒是 LF。
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


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

    def test_restore_newlines_keeps_each_original_line(self):
        original = "a\r\nb\nc\rd"
        self.assertEqual(restore_newlines("a\nb\nc\nd", original), original)

    def test_restore_newlines_new_line_takes_dominant_newline(self):
        self.assertEqual(restore_newlines("a\nb\nc\n", "a\r\nb\r\n"),
                         "a\r\nb\r\nc\r\n")
        self.assertEqual(restore_newlines("a\nb\nc\n", "a\nb\n"),
                         "a\nb\nc\n")

    def test_restore_newlines_never_adds_or_drops_a_line_break(self):
        # 用户把两行并成一行：那个换行没了就是没了，不许被还原回来；
        # 剩下的那一行仍按该节的行尾风格（CRLF）写。
        self.assertEqual(restore_newlines("ab\n", "a\r\nb\r\n"), "ab\r\n")
        # 用户在末尾补一个换行：补出来的换行按主导行尾写。
        self.assertEqual(restore_newlines("a\nb\n", "a\r\nb"),
                         "a\r\nb\r\n")
        # 换行的**个数**只由客户端那份文本决定：还原只改风格，不改个数。
        for original, new in (("a\r\nb\r\n", "ab\n"),
                              ("a\r\nb", "a\nb\n"),
                              ("a\nb\n", "a\nb\n")):
            self.assertEqual(restore_newlines(new, original).count("\n"),
                             new.count("\n"))

    def test_restore_newlines_keeps_explicit_client_crlf(self):
        # 客户端自己明确给了 CRLF（不是浏览器的 LF 归一）：一个字都不改。
        self.assertEqual(restore_newlines("a\r\nb\r\n", "a\nb\n"),
                         "a\r\nb\r\n")

    def test_restore_newlines_never_touches_content(self):
        original = "x \\fact{A1} 56.25\\% y\r\n"
        self.assertEqual(restore_newlines("x \\fact{A1} 56.26\\% y\n", original),
                         "x \\fact{A1} 56.26\\% y\r\n")


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
        """bib 也是用户内容：追加一条不得把已有内容的行尾改掉。"""
        root = make_project(self.base, CRLF_TEX)
        bib = root / "refs.bib"
        before = bib.read_bytes()
        result = citation_add_data(root, {"key": "new2024", "title": "T",
                                          "author": "A", "year": "2024",
                                          "kind": "article"}, allow_write=True)
        self.assertEqual(result["key"], "new2024")
        after = bib.read_bytes()
        self.assertTrue(after.startswith(before))
        self.assertNotIn(b"\r\r\n", after)

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
        spy = _OpenSpy()
        real_open = open
        import builtins
        builtins.open = spy
        try:
            citation_add_data(self.root, {"key": "spy2024", "title": "T",
                                           "author": "A", "year": "2024",
                                           "kind": "article"}, allow_write=True)
        finally:
            builtins.open = real_open
        self.assertTrue(spy.writes)
        for path, newline, _data in spy.writes:
            self.assertEqual(newline, "", path)


class BrowserSaveNewlineTest(unittest.TestCase):
    """网页工作台保存：浏览器交回 LF，落盘必须还原成该节原有的行尾。

    这一组是本批的**缺陷复现与修复锁**：修复前，浏览器在 `<textarea>` 里
    交回的 LF 正文被逐字写回，CRLF 稿件存一次就变成 LF（内容一个字
    没动，行尾整篇被换掉）。修复后：

    * CRLF 节 → 仍是 CRLF，且逐字节不变；
    * LF 节 → 仍是 LF，不许被改成 CRLF；
    * 混合节 → 逐行照旧；
    * 用户新输入的行 → 用该节的主导行尾。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _save(self, tex_bytes: bytes, submitted: str) -> bytes:
        """造盘 → 按客户端给的那份正文保存 → 交回落盘字节。"""
        root = make_project(self.base, tex_bytes)
        section = root / "sections" / "01-intro.tex"
        write_section_data(root, "sections/01-intro.tex", submitted,
                           allow_write=True)
        return section.read_bytes()

    def test_crlf_section_saved_from_browser_stays_crlf(self):
        """CRLF 稿存一次仍是 CRLF，且逐字节不变。"""
        original = CRLF_TEX.decode("utf-8")
        after = self._save(CRLF_TEX, browser_text(original))
        self.assertEqual(after, CRLF_TEX)
        self.assertEqual(after.count(b"\r\n"), CRLF_TEX.count(b"\r\n"))
        self.assertNotIn(b"\n", after.replace(b"\r\n", b""))

    def test_lf_section_saved_from_browser_stays_lf(self):
        """LF 稿不许被改成 CRLF。"""
        original = LF_TEX.decode("utf-8")
        after = self._save(LF_TEX, browser_text(original))
        self.assertEqual(after, LF_TEX)
        self.assertNotIn(b"\r", after)

    def test_mixed_section_saved_from_browser_keeps_every_line(self):
        """混合行尾逐行照旧：CRLF 的行、LF 的行、单独 CR 的行都不动。"""
        original = MIXED_TEX.decode("utf-8")
        after = self._save(MIXED_TEX, browser_text(original))
        self.assertEqual(after, MIXED_TEX)
        self.assertEqual(after.count(b"\r\n"), MIXED_TEX.count(b"\r\n"))
        self.assertEqual(after.count(b"\r"), MIXED_TEX.count(b"\r"))

    def test_new_user_line_takes_dominant_newline(self):
        """用户新输入的行：用该节的主导行尾，不拍脑袋选。"""
        original = CRLF_TEX.decode("utf-8")
        submitted = browser_text(original + "A brand new line.\n")
        after = self._save(CRLF_TEX, submitted)
        self.assertTrue(after.endswith(b"A brand new line.\r\n"), after)
        self.assertEqual(after.count(b"\r\n"), CRLF_TEX.count(b"\r\n") + 1)

    def test_new_user_line_in_lf_section_stays_lf(self):
        """LF 节里新输入的行也是 LF。"""
        original = LF_TEX.decode("utf-8")
        submitted = browser_text(original + "A brand new line.\n")
        after = self._save(LF_TEX, submitted)
        self.assertTrue(after.endswith(b"A brand new line.\n"), after)
        self.assertNotIn(b"\r", after)

    def test_edited_line_keeps_section_style(self):
        """真改一个字：改掉的那行仍是该节的行尾，其余字节一个不动。"""
        original = CRLF_TEX.decode("utf-8")
        submitted = browser_text(original.replace("56.25", "56.26"))
        after = self._save(CRLF_TEX, submitted)
        self.assertIn(b"56.26", after)
        self.assertEqual(after.count(b"\r\n"), CRLF_TEX.count(b"\r\n"))
        self.assertNotIn(b"\r\r\n", after)
        self.assertNotIn(b"56.25", after)

    def test_protected_surface_numbers_and_tokens_untouched(self):
        """保护面、数字、token 一个字都不能被保存链路改写。"""
        original = CRLF_TEX.decode("utf-8")
        submitted = browser_text(original)
        after = self._save(CRLF_TEX, submitted).decode("utf-8")
        self.assertIn("\\fact{A1}", after)
        self.assertIn("\\cite{alpha2020}", after)
        self.assertIn("56.25\\%", after)
        self.assertEqual(after.replace("\r\n", "\n"), original.replace("\r\n", "\n"))

    def test_explicit_client_crlf_is_not_rewritten(self):
        """非浏览器客户端明确给了 CRLF：一个字符都不许被改写。"""
        after = self._save(LF_TEX, "\\section{Intro}\r\nbody\r\n")
        self.assertEqual(after, b"\\section{Intro}\r\nbody\r\n")


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


class HttpBrowserSaveTest(unittest.TestCase):
    """端到端：走真实 HTTP 保存接口，浏览器交回的 LF 不得吃掉行尾。

    这一组起真服务器（`create_server`），用真实的 `PUT /api/sections`
    把浏览器归一后的正文存回去，再读落盘字节——网页工作台那条路就
    是这么走的（`app.js` 的 `saveWorkbenchSection()` → PUT → 引擎写盘）。
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = make_project(Path(cls._tmp.name), CRLF_TEX)
        sections = cls.root / "sections"
        (sections / "02-lf.tex").write_bytes(LF_TEX)
        (sections / "03-mixed.tex").write_bytes(MIXED_TEX)
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

    def _browser_save(self, name: str, before: bytes) -> bytes:
        status, project = self._request("/api/project")
        self.assertEqual(status, 200)
        row = next(s for s in project["sections"] if s["file"] == name)
        # 浏览器那一层：<textarea> 交回的恒是 LF。
        submitted = browser_text(row["text"])
        self.assertNotIn("\r", submitted)
        status, data = self._request("/api/sections", method="PUT",
                                     body={"file": name, "text": submitted})
        self.assertEqual(status, 200, data)
        path = self.root / name
        after = path.read_bytes()
        self.assertEqual(after, before,
                         "%s 存一次后行尾变了（浏览器交回 LF 不得吃掉 CRLF）" % name)
        return after

    def test_http_put_crlf_section_stays_crlf(self):
        after = self._browser_save("sections/01-intro.tex", CRLF_TEX)
        self.assertIn(b"\r\n", after)
        self.assertNotIn(b"\n", after.replace(b"\r\n", b""))

    def test_http_put_lf_section_stays_lf(self):
        after = self._browser_save("sections/02-lf.tex", LF_TEX)
        self.assertNotIn(b"\r", after)

    def test_http_put_mixed_section_keeps_every_line(self):
        after = self._browser_save("sections/03-mixed.tex", MIXED_TEX)
        self.assertEqual(after.count(b"\r\n"), MIXED_TEX.count(b"\r\n"))
        self.assertEqual(after.count(b"\r"), MIXED_TEX.count(b"\r"))


if __name__ == "__main__":
    unittest.main()
