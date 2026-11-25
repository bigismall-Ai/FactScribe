# -*- coding: utf-8 -*-
"""3.10 兜底 TOML 解析器（`factscribe/config.py::_mini_toml`）的边界锁。

背景：标准库 `tomllib` 只在 3.11+ 有，3.10 走 factscribe 自带的兜底解析器。
兜底解析器当年是「宽松」的：坏 TOML 不报错，当成合法内容收下 —— 闸门于是
fail-open（坏账本被放行），而 3.11+ 的 tomllib 拒绝同一份文件。同一份坏文件
在两种解释器上结论相反，两道闸不再跨版本一致（CI 矩阵里 3.10 一条腿红、
别的腿绿；audit 输出也不再逐字节相同）。

本文件锁两件事（CONTRIBUTING §2「正反例各三」）：
1. **负例**：坏 TOML 兜底解析器必须抛错 —— 经既有 ConfigError 通道变成
   exit 2（配置错），不许放行。
2. **正例**：合法 TOML 必须照常读出来 —— 不许把闸修成「一律拒绝」。

这些用例在任何解释器上都能跑：`_mini_toml` 是显式调用的，不依赖 tomllib
在不在 —— 这正是「3.10 上也能验这条边界」的意思。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import ConfigError, _mini_toml, load_toml  # noqa: E402


# 坏 TOML：每一行都是 tomllib 会拒绝的形状（标准库是判据的权威来源）。
BROKEN = [
    ("坏表头：少右括号", '[[ref]\nslug = "broken"\n'),
    ("坏表头：没闭合", '[ref\nslug = "broken"\n'),
    ("坏表头：表头后面有垃圾", '[[ref]] trailing\n'),
    ("坏表头：多一个右括号", '[ref]]\n'),
    ("未闭合字符串", 'id = "X1\nvalue = "42"\n'),
    ("未闭合字面字符串", "id = 'X1\n"),
    ("未闭合数组", "a = [1, 2\n"),
    ("未闭合内联表", "a = {b = 1\n"),
    ("裸词值（不是合法 TOML 值）", "a = hello\n"),
    ("一行没有等号", "这一行没有等号\n"),
    ("表头后面跟键值", "[a] b = 1\n"),
    ("值后面有多余内容", "a = 1 b = 2\n"),
    ("重复键", "a = 1\na = 2\n"),
    ("重复表", "[a]\n[a]\n"),
    # 控制字符：标准库 tomllib 只放行制表符（多行字符串里另放行换行）。
    ("基本字符串里的控制字符", "a = \"x\x01y\"\n"),
    ("字面字符串里的控制字符", "a = 'x\x01y'\n"),
    ("多行字符串里的控制字符", "a = \"\"\"x\x01y\"\"\"\n"),
    ("多行字面字符串里的控制字符", "a = '''x\x01y'''\n"),
    ("注释里的控制字符", "a = 1 # c\x01c\n"),
    ("裸 CR（不是 CRLF）", "a = 1\rb = 2\n"),
]

# 合法 TOML：factscribe 契约真正用得到的形状，一个都不许被误伤。
LEGAL = [
    ("普通表", '[project]\ntitle = "T"\n'),
    ("表数组", '[[fact]]\nid = "A"\n'),
    ("点号表名", '[a.b]\nk = "v"\n'),
    ("点号键", "a.b = 1\n"),
    ("引号键（带点、带斜杠）", '"results/run.log" = "x"\n'),
    ("数组", 'a = ["x", "y"]\n'),
    ("跨行数组", 'a = [\n  "x",\n]\n'),
    ("内联表", 'a = { id = "g" }\n'),
    ("数组里的内联表", 'a = [{ text = "0.9", round_to = 1 }]\n'),
    ("字面字符串（不解释转义）", "a = 'lit\\path'\n"),
    ("布尔/整数/浮点", "a = true\nb = -12\nc = 1.25\nd = 1e3\n"),
    ("注释", '# 整行注释\na = "b # c"  # 行尾注释\n'),
    # CRLF 行尾：Windows 写的文件必须读得动（标准库在入口把 CRLF 归一成 LF）。
    ("CRLF 行尾", "a = 1\r\nb = 2\r\n"),
    ("CRLF 表头", "[a]\r\nb = 1\r\n"),
    ("CRLF 多行字符串", "a = \"\"\"x\r\ny\"\"\"\n"),
]


class TestMiniTomlRefusesBrokenInput(unittest.TestCase):
    """负例锁：坏 TOML 必须报错（与标准库 tomllib 同一口径）。"""

    def test_broken_input_raises(self):
        for why, text in BROKEN:
            with self.subTest(why=why):
                with self.assertRaises(ValueError):
                    _mini_toml(text)

    def test_broken_file_becomes_config_error(self):
        """坏文件经既有 ConfigError 通道 → 退出码 2（配置错），不是 exit 4。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.toml"
            path.write_text('[[ref]\nslug = "broken"\n', encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_toml(path)

    def test_crlf_file_is_readable(self):
        """Windows 写的文件（CRLF）在 3.10 上必须读得动。

        旧兜底解析器按行切，CRLF 没问题；严格重写一度把 CRLF 当坏输入拒了
        —— 那是本次修复自己引入的回归（同一份文件 3.10 拒、3.11+ 收）。
        标准库 tomllib.loads() 在入口就把 CRLF 归一成 LF，兜底解析器照做。
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "crlf.toml"
            path.write_bytes(b'[project]\r\ntitle = "T"\r\nn = 1\r\n')
            data = load_toml(path)
        self.assertEqual({"project": {"title": "T", "n": 1}}, data)

    def test_control_chars_are_refused(self):
        """控制字符（除制表符/换行外）必须报错，不许悄悄收下。"""
        for text in ('a = "x\x01y"\n', "a = 'x\x01y'\n",
                     'a = """x\x01y"""\n', "a = 1 # c\x01c\n"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    _mini_toml(text)


class TestMiniTomlStillReadsLegalInput(unittest.TestCase):
    """正例锁：合法 TOML 照常读出来（不许把闸修成「一律拒绝」）。"""

    def test_legal_input_parses(self):
        for why, text in LEGAL:
            with self.subTest(why=why):
                data = _mini_toml(text)
                self.assertIsInstance(data, dict)
                self.assertTrue(data)

    def test_matches_stdlib_when_available(self):
        """3.11+ 有 tomllib 时：兜底解析器与标准库必须读出同一个 dict。"""
        try:
            import tomllib
        except ModuleNotFoundError:
            self.skipTest("本解释器没有 tomllib（3.10），跳过对照")
        for why, text in LEGAL:
            with self.subTest(why=why):
                self.assertEqual(_mini_toml(text), tomllib.loads(text))

    def test_stdlib_also_refuses_broken_input(self):
        """反例自检：这些形状标准库也拒（判据不是我们自己发明的）。"""
        try:
            import tomllib
        except ModuleNotFoundError:
            self.skipTest("本解释器没有 tomllib（3.10），跳过对照")
        for why, text in BROKEN:
            with self.subTest(why=why):
                with self.assertRaises(Exception):
                    tomllib.loads(text)


if __name__ == "__main__":
    unittest.main()
