#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法律侧 CLI 的控制台编码降级：非 UTF-8 控制台（中文 Windows cp936/GBK）不许崩。

缺陷（Windows 真机实测，2026-11-26）：中文 Windows 的本地编码是
gbk/cp936（ACP=936），**编不出**人读输出里的装饰字符（`✓` / `🔴` / `⚠` …）。
`print()` 撞上就抛 `UnicodeEncodeError`，命令退成异常路径——退出码不是它
本来的判定码（修前实测：`fetch` 在 UTF-8 下 0、cp936 下 1；`verify-es`
在 UTF-8 下 3、cp936 下 1；`api` 的 JSON 载荷在 cp936 下被改小 3912 字节）。

本文件把三条口径锁住（2026-11-26 用户拍板）：

1. **人读输出安全降级**：装饰字符换同义 ASCII（`✓`→`v`、`🔴`→`[红]`），
   不问号、不崩；
2. **退出码不变**：同一条命令在 UTF-8 与 cp936 下退出码**逐条一致**
   （0 绿 / 1 红或查无 / 2 配置错 / 3 黄）；
3. **--json 载荷逐字不变**：JSON 通道按 UTF-8 字节出，两种环境一个字节不差。

做法是平台无关的：把子进程的 stdout/stderr 编码设成 `cp936`（与中文
Windows 的 ACP 同一个编解码器，Python 自带，本机 macOS／Linux 也有），
同一条命令跑两次比较。覆盖法律侧全部子命令：既有 11 条 ＋ api 族。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, ".."))
CORPUS = os.path.join(PKG, "corpus")

# 中文 Windows 的本地编码（ACP=936）就是 gbk/cp936 这一族。
CP936 = "cp936"

FR = os.path.join(CORPUS, "fr")
ES = os.path.join(CORPUS, "es",
                  "run-20261116-es-const1978-constitucion-espanola")
IT = os.path.join(CORPUS, "it", "run-20261116-it-2012n190")
ITCASE = os.path.join(CORPUS, "it-case", "run-20261116-itcase-1956_1980")
CN_CATALOG = os.path.join(CORPUS, "cn", "catalog.jsonl.gz")


def run_cli(args, encoding="utf-8", cwd=None):
    """跑一次法律侧 CLI，stdout/stderr 用指定编码。

    返回 (returncode, stdout_bytes, stderr_bytes)：字节原样带回来，解码由
    用例自己按编码解——这样「控制台编码」这件事在用例里看得见。
    """
    env = dict(os.environ,
               PYTHONIOENCODING=encoding,
               PYTHONPATH=PKG,
               no_proxy="*", NO_PROXY="*")
    proc = subprocess.run([sys.executable, "-m", "factscribe_legal", *args],
                          capture_output=True, cwd=cwd or PKG, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


FACT_TOML = (
    'schema = "paperkit-fact/3.0"\n'
    '\n'
    '[[fact]]\n'
    'id = "CASE-1"\n'
    'claim = "案例赔偿金额"\n'
    'value = "12345"\n'
    'source = "runs/run-20260101-cncase-x/abc.case.card.txt"\n'
    'source_sha256 = "sha256:%s"\n'
    'locator = "案例正文"\n'
    'confidence = "high"\n'
    'derived_from = []\n'
)


class ConsoleCp936Base(unittest.TestCase):
    """共用夹具：一个绿项目、一个红项目、一个离线线索层配置。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="fs-legal-cp936-")
        root = cls._tmp.name
        cls.proj_green = os.path.join(root, "green")
        os.makedirs(os.path.join(cls.proj_green, "facts"), exist_ok=True)
        cls.proj_red = os.path.join(root, "red")
        _write(os.path.join(cls.proj_red, "facts", "40-case.toml"),
               FACT_TOML % ("0" * 64))
        # 线索层：指向一个必关端口 ⇒ 确定性网络错（退出码 2），全程不联网。
        cls.cnlead_cfg = os.path.join(root, "cnlead.toml")
        _write(cls.cnlead_cfg,
               '[cn_lead]\nendpoint = "http://127.0.0.1:9"\nkey = "test"\n')

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # ---- 断言helpers ----------------------------------------------------

    def assert_same_exit(self, args, cwd=None):
        """同一条命令：UTF-8 与 cp936 的退出码必须一致，stderr 必须空。"""
        rc_u8, out_u8, err_u8 = run_cli(args, "utf-8", cwd)
        rc_cp, out_cp, err_cp = run_cli(args, CP936, cwd)
        self.assertEqual(
            err_u8, b"", "%s：UTF-8 下 stderr 不该有东西" % args[0])
        self.assertEqual(
            err_cp, b"", "%s：cp936 下 stderr 不该有东西（不许崩）" % args[0])
        self.assertNotIn(b"UnicodeEncodeError", err_cp)
        self.assertNotIn(b"Traceback", err_cp)
        self.assertEqual(
            rc_u8, rc_cp,
            "%s：退出码漂移——UTF-8 下 %d，cp936 下 %d" % (args[0], rc_u8, rc_cp))
        # 降级后的字节必须仍是**合法 cp936**（不许留半个多字节序列）——
        # 这条守住「降级的是字符，不是编码」。
        out_cp.decode(CP936)
        return rc_u8, out_u8, out_cp

    def assert_glyph_downgraded(self, out_u8, out_cp, glyph, ascii_form):
        """装饰字符在 UTF-8 下原样，cp936 下换成同义 ASCII。"""
        text_u8 = out_u8.decode("utf-8", "replace")
        text_cp = out_cp.decode(CP936, "replace")
        self.assertIn(glyph, text_u8, "UTF-8 下装饰字符应当原样：%s" % glyph)
        self.assertNotIn(glyph, text_cp,
                         "cp936 下装饰字符必须降级：%s" % glyph)
        self.assertIn(ascii_form, text_cp,
                      "cp936 下应当换成同义 ASCII：%s" % ascii_form)


class TestExistingSubcommands(ConsoleCp936Base):
    """既有 11 条子命令：退出码逐条一致，stderr 空，不崩。"""

    def test_fetch(self):
        rc, out_u8, out_cp = self.assert_same_exit(
            ["fetch", "--corpus", FR, "--project", self.proj_green,
             "--nums", "L594-8"])
        self.assertEqual(rc, 0)
        self.assert_glyph_downgraded(out_u8, out_cp, "✓", "v L594-8")

    def test_verify(self):
        rc, _u8, _cp = self.assert_same_exit(
            ["verify", "--project", self.proj_green, "--corpus", FR,
             "--date", "2026-01-01"])
        self.assertEqual(rc, 0)

    def test_verify_cn(self):
        rc, _u8, _cp = self.assert_same_exit(
            ["verify-cn", "--project", self.proj_green, "--catalog", CN_CATALOG,
             "--date", "2026-01-01"])
        self.assertEqual(rc, 0)

    def test_verify_case_green(self):
        """绿：退出码 0，人读输出里的 ✓ 降级成 v。"""
        rc, out_u8, out_cp = self.assert_same_exit(
            ["verify-case", "--project", self.proj_green])
        self.assertEqual(rc, 0)
        self.assert_glyph_downgraded(out_u8, out_cp, "✓", "v 绿")

    def test_verify_case_red(self):
        """查无/判不出：UTF-8 下退出码 1，cp936 下必须也是 1（不许变 0，
        也不许走异常路径变成别的值）。"""
        rc, out_u8, out_cp = self.assert_same_exit(
            ["verify-case", "--project", self.proj_red])
        self.assertEqual(rc, 1)
        self.assert_glyph_downgraded(out_u8, out_cp, "🔴", "[红]")

    def test_verify_it(self):
        rc, _u8, _cp = self.assert_same_exit(
            ["verify-it", "--project", self.proj_green, "--corpus", IT,
             "--date", "2026-01-01"])
        self.assertEqual(rc, 3, "语料里版本池有黄码——黄码就是 3")

    def test_verify_es(self):
        """修前 cp936 下这条是 1（崩了），UTF-8 下是 3（黄）——必须一致。"""
        rc, _u8, _cp = self.assert_same_exit(
            ["verify-es", "--project", self.proj_green, "--corpus", ES,
             "--date", "2026-01-01"])
        self.assertEqual(rc, 3, "语料里版本池有黄码——黄码就是 3")

    def test_verify_fr_case(self):
        rc, _u8, _cp = self.assert_same_exit(
            ["verify-fr-case", "--project", self.proj_green])
        self.assertEqual(rc, 0)

    def test_verify_it_case(self):
        rc, _u8, _cp = self.assert_same_exit(
            ["verify-it-case", "--project", self.proj_green, "--corpus", ITCASE])
        self.assertEqual(rc, 0)

    def test_cn_lead_search(self):
        """线索层：离线失败是 exit 2（fail-closed），两种环境一致。"""
        rc, _u8, _cp = self.assert_same_exit(
            ["cn-lead-search", "--q", "合同纠纷", "--config", self.cnlead_cfg])
        self.assertEqual(rc, 2)

    def test_cn_lead_verify(self):
        rc, _u8, _cp = self.assert_same_exit(
            ["cn-lead-verify", "--case-no", "（2022）苏0322执保100号",
             "--config", self.cnlead_cfg])
        self.assertEqual(rc, 2)

    def test_cn_lead_get(self):
        rc, _u8, _cp = self.assert_same_exit(
            ["cn-lead-get", "--case-no", "（2022）苏0322执保100号", "--meta",
             "--config", self.cnlead_cfg])
        self.assertEqual(rc, 2)


class TestApiFamily(ConsoleCp936Base):
    """api 族：JSON 载荷在两种编码下逐字相同（一个字节都不许差）。"""

    def _run_pair(self, args):
        rc_u8, out_u8, err_u8 = run_cli(args, "utf-8")
        rc_cp, out_cp, err_cp = run_cli(args, CP936)
        self.assertEqual(err_u8, b"")
        self.assertEqual(err_cp, b"")
        self.assertNotIn(b"UnicodeEncodeError", err_cp)
        self.assertNotIn(b"Traceback", err_cp)
        self.assertEqual(rc_u8, rc_cp, "退出码漂移")
        return rc_u8, out_u8, out_cp

    def test_json_payload_is_byte_identical(self):
        rc, out_u8, out_cp = self._run_pair(
            ["api", "contract", "--project", self.proj_red])
        self.assertEqual(rc, 0)
        self.assertEqual(
            out_cp, out_u8,
            "JSON 载荷必须逐字相同（JSON 通道按 UTF-8 字节出）")

    def test_json_payload_survives_non_ascii_titles(self):
        """载荷里有西班牙语标题（带 ñ，cp936 编不出）——载荷不许被改写。"""
        rc, out_u8, out_cp = self._run_pair(
            ["api", "corpus", "--project", self.proj_green,
             "--corpus", ES])
        self.assertEqual(rc, 0)
        self.assertEqual(out_cp, out_u8)
        self.assertIn("Constitución", out_u8.decode("utf-8"),
                      "本用例要真的带上有音标的标题")

    def test_human_output_degrades_but_stays_readable(self):
        """--human 是人读通道：cp936 下照旧降级，但判定语义一个字不许丢。"""
        rc, out_u8, out_cp = self._run_pair(
            ["api", "contract", "--project", self.proj_red, "--human"])
        self.assertEqual(rc, 0)
        text_u8 = out_u8.decode("utf-8")
        text_cp = out_cp.decode(CP936)      # 严格解码：字节必须是合法 cp936
        for glyph in ("🔴", "🟡", "🟢", "✓"):
            self.assertNotIn(glyph, text_cp, "cp936 下装饰字符必须降级")
        self.assertIn("判定结果：2 条（红 2 / 黄 0）", text_cp,
                      "判定语义一个字不许丢")
        self.assertEqual(text_u8.count("｜"), text_cp.count("｜"),
                         "收据五元组的分隔符一字不许变")


class TestConsoleFallbackTable(unittest.TestCase):
    """降级表本身：装饰字符映射到同义 ASCII；表外字符不折叠、不用问号。"""

    def test_glyphs_map_to_readable_ascii(self):
        sys.path.insert(0, PKG)
        from factscribe_legal.console import (ERROR_HANDLER, _register_handler)
        _register_handler()
        text = "✓ ✗ ↔ ⇒ ⊆ « » ² ⚠"
        encoded = text.encode(CP936, ERROR_HANDLER)
        self.assertEqual(encoded.decode(CP936),
                         "v x <-> => <= << >> ^2 [!]")

    def test_utf8_text_is_untouched(self):
        sys.path.insert(0, PKG)
        from factscribe_legal.console import (ERROR_HANDLER, _register_handler)
        _register_handler()
        text = "✓ 中文 ↔ 🔴"
        self.assertEqual(text.encode("utf-8", ERROR_HANDLER).decode("utf-8"),
                         text)

    def test_accented_letters_are_not_folded(self):
        """带音标的拉丁字母不许被折成别的字母（也不许变问号）。"""
        sys.path.insert(0, PKG)
        from factscribe_legal.console import (ERROR_HANDLER, _register_handler)
        _register_handler()
        out = "Constitución".encode(CP936, ERROR_HANDLER).decode(CP936)
        self.assertNotIn("?", out)
        self.assertNotIn("Constitucion", out)
        self.assertIn("Constituci", out)

    def test_rare_cjk_is_escaped_not_lost(self):
        """GBK 编不出的生僻汉字：转义保留，不丢。"""
        sys.path.insert(0, PKG)
        from factscribe_legal.console import (ERROR_HANDLER, _register_handler)
        _register_handler()
        out = "\u9f9a".encode(CP936, ERROR_HANDLER).decode(CP936)
        self.assertNotIn("?", out)


if __name__ == "__main__":
    unittest.main()
