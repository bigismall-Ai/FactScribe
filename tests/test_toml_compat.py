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

判据（标准库）怎么进到 3.10 那条腿里：
标准库 tomllib 只在 3.11+ 有，所以本文件把标准库对每条样本的**实测裁决**
记在样本表第三列（接受→("accept", 解析出的 dict)；拒收→("refused", None)）：
- 3.11+ 的用例每次都现场复核这张表（表与真 tomllib 不一致就红）；
- 3.10 的用例拿这张表当判据：兜底解析器必须逐条同裁决，合法样本逐字同 dict。
于是 3.10 那条腿也有**确定断言**，不必靠「tomllib 在不在」才判 ——
3.10 恰恰是兜底解析器唯一在用的版本，对照必须是硬的。
（这张表只在 3.11/3.12/3.13/3.14 上实测一致；改表只有一个办法：在 3.11+ 上
重录，改完先看 3.11+ 的用例还红不红。）

同名文件的隐患（核对点 ④）：
本仓另有一份同名文件 `integrations/factscribe-legal/tests/test_toml_compat.py`
（legal 包自己的 TOML 读取层）。两份同名撞不上：CI 与 preflight 都是**分进程**
跑两套 discovery（`-s tests` 与 `-s integrations/factscribe-legal/tests`），
两个进程各有各的模块表；单次 discovery 覆盖全仓时收集到 0 例（`tests/` 不是
包，`integrations/factscribe-legal` 目录名带连字符不是合法包名），因此不存在
「同一个进程里 import 两个 test_toml_compat」的路径 —— 真撞上会报
import file mismatch。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import ConfigError, _mini_toml, load_toml  # noqa: E402


def _tomllib_or_none():
    """标准库 tomllib 在场就返回它，不在（3.10）就返回 None。

    刻意**不用 skip**：跳过会让 3.10 那条腿（兜底解析器唯一在用的版本）没有
    判据，而「本机有 poppler 却出现任何跳过」是本地发布门禁判红的条件
    （scripts/preflight-ci.sh）。合法跳过必须写进用例本身，不能靠跳过逃过门禁。
    """
    try:
        import tomllib
    except ModuleNotFoundError:
        return None
    return tomllib


def _verdict(parse):
    """把一次解析归一化成可比对的裁决：接受→("accept", dict)，拒收→("refused", None)。"""
    try:
        return ("accept", parse())
    except ValueError:
        return ("refused", None)


# 坏 TOML：每一行都是 tomllib 会拒绝的形状（标准库是判据的权威来源）。
# 第三列＝标准库 tomllib 的实测裁决（3.11/3.12/3.13/3.14 实测一致）。
BROKEN = [
    ("坏表头：少右括号", '[[ref]\nslug = "broken"\n', ("refused", None)),
    ("坏表头：没闭合", '[ref\nslug = "broken"\n', ("refused", None)),
    ("坏表头：表头后面有垃圾", '[[ref]] trailing\n', ("refused", None)),
    ("坏表头：多一个右括号", '[ref]]\n', ("refused", None)),
    ("未闭合字符串", 'id = "X1\nvalue = "42"\n', ("refused", None)),
    ("未闭合字面字符串", "id = 'X1\n", ("refused", None)),
    ("未闭合数组", "a = [1, 2\n", ("refused", None)),
    ("未闭合内联表", "a = {b = 1\n", ("refused", None)),
    ("裸词值（不是合法 TOML 值）", "a = hello\n", ("refused", None)),
    ("一行没有等号", "这一行没有等号\n", ("refused", None)),
    ("表头后面跟键值", "[a] b = 1\n", ("refused", None)),
    ("值后面有多余内容", "a = 1 b = 2\n", ("refused", None)),
    ("重复键", "a = 1\na = 2\n", ("refused", None)),
    ("重复表", "[a]\n[a]\n", ("refused", None)),
    # 控制字符：标准库 tomllib 只放行制表符（多行字符串里另放行换行）。
    ("基本字符串里的控制字符", "a = \"x\x01y\"\n", ("refused", None)),
    ("字面字符串里的控制字符", "a = 'x\x01y'\n", ("refused", None)),
    ("多行字符串里的控制字符", "a = \"\"\"x\x01y\"\"\"\n", ("refused", None)),
    ("多行字面字符串里的控制字符", "a = '''x\x01y'''\n", ("refused", None)),
    ("注释里的控制字符", "a = 1 # c\x01c\n", ("refused", None)),
    ("裸 CR（不是 CRLF）", "a = 1\rb = 2\n", ("refused", None)),
]

# 合法 TOML：factscribe 契约真正用得到的形状，一个都不许被误伤。
# 第三列＝标准库 tomllib 的实测裁决（接受→解析出的 dict）。
LEGAL = [
    ("普通表", '[project]\ntitle = "T"\n', ("accept", {"project": {"title": "T"}})),
    ("表数组", '[[fact]]\nid = "A"\n', ("accept", {"fact": [{"id": "A"}]})),
    ("点号表名", '[a.b]\nk = "v"\n', ("accept", {"a": {"b": {"k": "v"}}})),
    ("点号键", "a.b = 1\n", ("accept", {"a": {"b": 1}})),
    ("引号键（带点、带斜杠）", '"results/run.log" = "x"\n', ("accept", {"results/run.log": "x"})),
    ("数组", 'a = ["x", "y"]\n', ("accept", {"a": ["x", "y"]})),
    ("跨行数组", 'a = [\n  "x",\n]\n', ("accept", {"a": ["x"]})),
    ("内联表", 'a = { id = "g" }\n', ("accept", {"a": {"id": "g"}})),
    ("数组里的内联表", 'a = [{ text = "0.9", round_to = 1 }]\n',
     ("accept", {"a": [{"text": "0.9", "round_to": 1}]})),
    ("字面字符串（不解释转义）", "a = 'lit\\path'\n", ("accept", {"a": "lit\\path"})),
    ("布尔/整数/浮点", "a = true\nb = -12\nc = 1.25\nd = 1e3\n",
     ("accept", {"a": True, "b": -12, "c": 1.25, "d": 1000.0})),
    ("注释", '# 整行注释\na = "b # c"  # 行尾注释\n', ("accept", {"a": "b # c"})),
    # CRLF 行尾：Windows 写的文件必须读得动（标准库在入口把 CRLF 归一成 LF）。
    ("CRLF 行尾", "a = 1\r\nb = 2\r\n", ("accept", {"a": 1, "b": 2})),
    ("CRLF 表头", "[a]\r\nb = 1\r\n", ("accept", {"a": {"b": 1}})),
    ("CRLF 多行字符串", "a = \"\"\"x\r\ny\"\"\"\r\n", ("accept", {"a": "x\ny"})),
]


class TestMiniTomlRefusesBrokenInput(unittest.TestCase):
    """负例锁：坏 TOML 必须报错（与标准库 tomllib 同一口径）。"""

    def test_broken_input_raises(self):
        for why, text, _recorded in BROKEN:
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
        for why, text, _recorded in LEGAL:
            with self.subTest(why=why):
                data = _mini_toml(text)
                self.assertIsInstance(data, dict)
                self.assertTrue(data)


class TestMiniTomlMatchesStdlibVerdict(unittest.TestCase):
    """对照锁：兜底解析器的裁决必须与标准库 tomllib 逐条相同 —— 任何解释器上都跑。

    这两条对照以前是「有 tomllib 才跑」（3.10 上跳过两条），而 3.10 恰恰是
    兜底解析器唯一在用的版本：跳过的正是最该验的那条腿。现在标准库的实测
    裁决记在样本表第三列，任何版本都拿它当确定断言；3.11+ 再现场复核这张表，
    表烂了会响。
    """

    def test_matches_stdlib_verdict_on_legal_samples(self):
        """合法样本：兜底解析器读出的 dict 必须与标准库实测记录逐字相同。"""
        tomllib = _tomllib_or_none()
        for why, text, recorded in LEGAL:
            with self.subTest(why=why):
                if tomllib is not None:
                    self.assertEqual(
                        _verdict(lambda: tomllib.loads(text)), recorded,
                        "标准库实测记录与真 tomllib 不一致——记录表烂了，先在 3.11+ 上重录",
                    )
                self.assertEqual(
                    _verdict(lambda: _mini_toml(text)), recorded,
                    "兜底解析器读出的结果与标准库实测记录不一致",
                )

    def test_matches_stdlib_verdict_on_broken_samples(self):
        """坏样本：标准库实测裁决是拒收，兜底解析器必须同样拒收（不许收下）。"""
        tomllib = _tomllib_or_none()
        for why, text, recorded in BROKEN:
            with self.subTest(why=why):
                if tomllib is not None:
                    self.assertEqual(
                        _verdict(lambda: tomllib.loads(text)), recorded,
                        "标准库实测记录与真 tomllib 不一致——记录表烂了，先在 3.11+ 上重录",
                    )
                self.assertEqual(
                    _verdict(lambda: _mini_toml(text)), recorded,
                    "兜底解析器收下了标准库拒收的坏 TOML",
                )

    def test_recorded_verdicts_are_well_formed(self):
        """记录表自身的形状不许坏：接受项带 dict，拒收项标 refused，样本不许重名。"""
        for why, text, recorded in LEGAL:
            with self.subTest(why=why):
                self.assertEqual(recorded[0], "accept")
                self.assertIsInstance(recorded[1], dict)
                self.assertTrue(recorded[1])
        for why, text, recorded in BROKEN:
            with self.subTest(why=why):
                self.assertEqual(recorded, ("refused", None))
        texts = [t for _why, t, _r in LEGAL] + [t for _why, t, _r in BROKEN]
        self.assertEqual(len(texts), len(set(texts)), "样本文本必须互不相同，否则子测试会互相遮蔽")


if __name__ == "__main__":
    unittest.main()
