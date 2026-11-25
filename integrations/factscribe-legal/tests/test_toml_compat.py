"""TOML 读取层的交叉校验。

背景：上游 factscribe 的 CI 矩阵含 Python 3.10，而标准库 `tomllib` 是 3.11 才有。
本包用一个「优先复用上游、否则自带极简解析器」的读取层解决（见 `_toml.py`）。

风险在于：**两个解析器对同一文件给出不同结果** ⇒ 同一份事实账在不同机器上
判出不同的门禁结论 ⇒ 不可复现。所以这里必须有交叉校验：
自带极简解析器 vs 标准库 tomllib vs 上游 factscribe.config.load_toml，
三者对同一份样本必须给出**完全相同**的 dict。
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent
sys.path.insert(0, str(PKG_ROOT))

from factscribe_legal._toml import (  # noqa: E402
    TomlSubsetError, load_toml, mini_loads, parser_name,
)

SAMPLE = HERE / "fixtures" / "facts_sample.toml"


def _upstream_on(text):
    """用上游 factscribe 的解析器读一段 TOML 文本（拿不到就跳过）。"""
    try:
        from factscribe.config import _mini_toml
    except Exception:
        raise unittest.SkipTest("拿不到 factscribe")
    return _mini_toml(text)



class TestMiniParserMatchesStdlib(unittest.TestCase):
    """自带极简解析器 vs 标准库 tomllib：必须逐字相同。"""

    def setUp(self):
        try:
            import tomllib  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("本解释器没有 tomllib（3.10），跳过对照")

    def test_same_result_on_sample(self):
        import tomllib
        text = SAMPLE.read_text(encoding="utf-8")
        self.assertEqual(mini_loads(text), tomllib.loads(text))

    def test_same_result_on_chinese_and_escapes(self):
        import tomllib
        text = (
            'schema = "x"\n\n'
            '[[fact]]\n'
            'id = "A"\n'
            'claim = "含\\"引号\\"与\\\\反斜杠的标题"\n'
            'value = "2018-12-29"\n'
            'note = "路径 runs/run-2026/中华人民共和国 劳动法.txt"\n'
            'n = -12\n'
            'f = 1.25\n'
            'b = true\n'
        )
        self.assertEqual(mini_loads(text), tomllib.loads(text))

    def test_comment_handling(self):
        import tomllib
        text = (
            "# 整行注释\n"
            'a = "有 # 号"  # 行尾注释\n'
            'b = "另一个"\n'
        )
        self.assertEqual(mini_loads(text), tomllib.loads(text))


class TestMiniParserFailsClosed(unittest.TestCase):
    """子集之外的写法必须报错，不许猜。"""

    def test_inline_table_rejected(self):
        with self.assertRaises(TomlSubsetError):
            mini_loads('a = {b = 1}\n')

    def test_unknown_value_rejected(self):
        with self.assertRaises(TomlSubsetError):
            mini_loads('a = 2026-11-15\n')

    def test_unclosed_string_rejected(self):
        with self.assertRaises(TomlSubsetError):
            mini_loads('a = "没闭合\n')

    def test_unparsable_line_rejected(self):
        with self.assertRaises(TomlSubsetError):
            mini_loads("这一行没有等号\n")

    def test_duplicate_key_rejected(self):
        """重复键必须报错 —— 默默覆盖会让同一份事实账读出两种结果。"""
        with self.assertRaises(TomlSubsetError):
            mini_loads("a = 1\na = 2\n")

    def test_duplicate_table_rejected(self):
        with self.assertRaises(TomlSubsetError):
            mini_loads("[a]\n[a]\n")

    def test_table_after_array_of_tables_rejected(self):
        with self.assertRaises(TomlSubsetError):
            mini_loads("[[a]]\n[a]\n")

    def test_leading_zero_number_rejected(self):
        """前导零不是合法 TOML 数字（标准库 tomllib 拒）。"""
        with self.assertRaises(TomlSubsetError):
            mini_loads("a = 01\n")

    def test_multiline_string_rejected(self):
        """多行字符串不在这份子集里 —— 报错，不许悄悄按单行解析（值会错）。"""
        with self.assertRaises(TomlSubsetError):
            mini_loads('a = """x"""\n')

    def test_trailing_junk_after_string_rejected(self):
        """字符串闭合之后还有内容 —— 报错（以前会被当字符串收下，值还错了）。"""
        with self.assertRaises(TomlSubsetError):
            mini_loads('a = "x" 后面\n')


class TestLoaderDispatch(unittest.TestCase):
    def test_load_toml_reads_sample(self):
        data = load_toml(SAMPLE)
        self.assertEqual(data["schema"], "paperkit-fact/3.0")
        self.assertEqual(len(data["fact"]), 2)
        self.assertEqual(data["fact"][0]["id"], "LBR-GBRQ")
        self.assertIs(data["fact"][0]["dup_ok"], True)

    def test_forced_mini_env(self):
        env = dict(os.environ, FACTSCRIBE_LEGAL_TOML="mini")
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,%r);"
             "from factscribe_legal._toml import parser_name,load_toml;"
             "print(parser_name());"
             "d=load_toml(%r);print(len(d['fact']))" % (str(PKG_ROOT), str(SAMPLE))],
            env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("mini", out.stdout)
        self.assertIn("2", out.stdout)

    def test_mini_and_tomllib_give_same_verdict(self):
        """3.10 兜底与 3.11+ 标准库必须读出**同一份**事实账（可复现性契约）。"""
        import json
        env = dict(os.environ, FACTSCRIBE_LEGAL_TOML="mini")
        code = ("import sys,json;sys.path.insert(0,%r);"
                "from factscribe_legal._toml import load_toml;"
                "print(json.dumps(load_toml(%r), sort_keys=True, ensure_ascii=False))"
                % (str(PKG_ROOT), str(SAMPLE)))
        mini = subprocess.run([sys.executable, "-c", code], env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(mini.returncode, 0, mini.stderr)
        std = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(std.returncode, 0, std.stderr)
        self.assertEqual(json.loads(mini.stdout), json.loads(std.stdout))

    def test_upstream_loader_agrees_on_supported_subset(self):
        """上游 factscribe 的 load_toml 对**我们实际写出的子集**必须与 tomllib 一致。

        背景：本包没有直接复用上游解析器，因为实测上游那份 3.10 兜底
        （factscribe/config.py::_mini_toml）不认嵌套数组。这里锁住「上游在我们
        真正用到的子集上与 tomllib 一致」这一事实 —— 若上游哪天改了方言，
        这条测试会先响。
        """
        try:
            from factscribe.config import load_toml as upstream
        except Exception:
            self.skipTest("当前环境拿不到 factscribe（独立运行），跳过")
        try:
            import tomllib
        except ModuleNotFoundError:
            self.skipTest("本解释器没有 tomllib（3.10），跳过对照")
        text = SAMPLE.read_text(encoding="utf-8")
        # 只取我们事实账真正写出的形态：字符串 + 空数组 + 布尔 + 数字
        subset = (
            'schema = "paperkit-fact/3.0"\n\n'
            '[[fact]]\n'
            'id = "A"\n'
            'value = "2018-12-29"\n'
            'derived_from = []\n'
            'dup_ok = true\n'
        )
        self.assertEqual(upstream(SAMPLE), tomllib.loads(text))
        self.assertEqual(upstream.__module__, "factscribe.config")
        self.assertEqual(_upstream_on(subset), tomllib.loads(subset))


class TestWithoutTomllib(unittest.TestCase):
    """把 tomllib 从 import 里掐掉，包仍须可用（3.10 的真实处境）。"""

    def test_import_and_load_without_tomllib(self):
        code = (
            "import sys\n"
            "sys.modules['tomllib'] = None\n"
            "sys.path.insert(0, %r)\n"
            "from factscribe_legal.verify import load_facts\n"
            "print('import-ok')\n" % str(PKG_ROOT)
        )
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("import-ok", out.stdout)

    def test_reads_facts_without_tomllib(self):
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            facts_dir = Path(tmp) / "facts"
            facts_dir.mkdir()
            shutil.copy(SAMPLE, facts_dir / "01-sample.toml")
            code = (
                "import sys\n"
                "sys.modules['tomllib'] = None\n"
                "sys.path.insert(0, %r)\n"
                "from factscribe_legal.verify import load_facts\n"
                "f = load_facts(%r)\n"
                "print(len(f), f[0]['id'])\n" % (str(PKG_ROOT), tmp)
            )
            out = subprocess.run([sys.executable, "-c", code],
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("2 LBR-GBRQ", out.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestUpstreamFallbackFailsClosed(unittest.TestCase):
    """上游 3.10 兜底解析器（factscribe.config._mini_toml）遇坏 TOML 必须报错。

    上游那条兜底路径当年是宽松的：坏表头 `[[ref]` 被当成表名 `[ref` 收下、
    未闭合字符串 `id = "X1` 被当裸词吞下 —— 闸门 fail-open（放行），
    而 3.11+ 的 tomllib 拒绝同一份文件（两种解释器结论相反）。
    这里把「坏输入必须 raise」锁死；任何解释器上都能验（显式调用 `_mini_toml`，
    不依赖 tomllib 在不在）—— 这正是 3.10 那条腿要验的边界。
    """

    def _upstream_refused(self, text):
        try:
            from factscribe.config import _mini_toml
        except Exception:
            raise unittest.SkipTest("拿不到 factscribe")
        with self.assertRaises(ValueError):
            _mini_toml(text)

    def test_broken_table_header_refused(self):
        self._upstream_refused('[[ref]\nslug = "broken"\n')

    def test_unclosed_string_refused(self):
        self._upstream_refused('id = "X1\nvalue = "42"\n')

    def test_unclosed_array_refused(self):
        self._upstream_refused("a = [1, 2\n")

    def test_unclosed_inline_table_refused(self):
        self._upstream_refused("a = {b = 1\n")

    def test_bare_word_refused(self):
        self._upstream_refused("a = hello\n")

    def test_legal_subset_still_reads(self):
        """正例：合法写法不许被误伤（不许把闸修成「一律拒绝」）。"""
        try:
            from factscribe.config import _mini_toml
        except Exception:
            raise unittest.SkipTest("拿不到 factscribe")
        text = (
            'schema = "paperkit-fact/3.0"\n\n'
            '[[fact]]\n'
            'id = "A"\n'
            'value = "2018-12-29"\n'
            'derived_from = []\n'
            'dup_ok = true\n'
        )
        self.assertEqual(_mini_toml(text)["fact"][0]["id"], "A")


if __name__ == "__main__":
    unittest.main()
