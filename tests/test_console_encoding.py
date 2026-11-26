# -*- coding: utf-8 -*-
"""控制台编码降级：非 UTF-8 控制台（中文 Windows cp936/gbk）上不许崩。

缺陷 D2（Windows 真机实测，2026-11-25）：真机 ACP=936（gb2312，zh-CN）下
`python -m factscribe doctor examples/minimal` 抛
`UnicodeEncodeError: 'gbk' codec can't encode character '\\u2713'`，
退成 **exit 4**（工具内部错误），而不是这条命令本来的退出码；全量 1798 例
里 12 条红由它引起。

本文件把这条锁住。做法是平台无关的：把子进程的 stdout/stderr 编码设成
`gbk`（与中文 Windows 的 cp936 同一个编解码器，Python 自带，
本机 macOS／Linux 也有），人读命令在该编码下必须正常退出。

锁住的两条口径：

* 人读命令**不得 exit 4**：装饰字符降级成同义 ASCII（`✓`→`v`、
  `✗`→`x`），中文一字不动，退出码照旧；
* 结构化输出（`--json`）在两种编码下**逐字相同**——不许因为
  控制台编码被替换掉字符，也不许被破坏成编不出来的载荷。

跑法（仓根）：python3 -m unittest discover -s tests
"""
from __future__ import annotations

import codecs
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    codecs.lookup("gbk")
    HAS_GBK = True
except LookupError:  # pragma: no cover - 极端精简的构建
    HAS_GBK = False

# 中文 Windows 的本地编码（ACP=936）就是 gbk 这一族。
GBK = "gbk"


def run_cli(*args, encoding="utf-8", cwd=None):
    """跑一次 CLI，stdout/stderr 用指定编码（默认 utf-8）。

    返回 (returncode, stdout_bytes, stderr_bytes)：字节原样带回来，
    解码由用例自己按编码解——这样「控制台编码」这件事在用例里看得见。
    """
    env = dict(os.environ, PYTHONIOENCODING=encoding, PYTHONPATH=str(ROOT))
    proc = subprocess.run([sys.executable, "-m", "factscribe", *args],
                          capture_output=True, cwd=str(cwd or ROOT), env=env)
    return proc.returncode, proc.stdout, proc.stderr


def init_project(path: Path) -> Path:
    """最小项目（`init` 落骨架，同参数逐字节一致）。"""
    code, out, err = run_cli("init", str(path), "--title", "Demo",
                            "--lang", "zh")
    assert code == 0, err.decode("utf-8", "replace")
    return path


@unittest.skipUnless(HAS_GBK, "本机没有 gbk 编解码器（中文 Windows 的编码）")
class TestConsoleEncoding(unittest.TestCase):
    """人读命令在 gbk 控制台下的行为（缺陷 D2 的回归线）。"""

    def test_doctor_on_gbk_console_exits_zero(self):
        """doctor：gbk 控制台下 exit 0（真机实测：修前是 exit 4 + UnicodeEncodeError）。"""
        code, out, err = run_cli("doctor", "examples/minimal", encoding=GBK)
        text = out.decode(GBK)
        self.assertNotEqual(code, 4, "不许退成工具内部错误：" + err.decode(GBK))
        self.assertEqual(code, 0, text)
        self.assertNotIn("UnicodeEncodeError", err.decode(GBK))
        # 装饰字符降级成同义 ASCII；中文一字不动。
        self.assertIn("v Python", text)
        self.assertNotIn("✓", text)
        self.assertIn("事实账", text)

    def test_utf8_console_keeps_the_original_glyphs(self):
        """UTF-8 控制台：装饰字符一字不改（macOS／Linux 现有行为不回退）。"""
        code, out, _err = run_cli("doctor", "examples/minimal", encoding="utf-8")
        text = out.decode("utf-8")
        self.assertEqual(code, 0)
        self.assertIn("✓ Python", text)
        self.assertNotIn("v Python", text)

    def test_human_commands_do_not_exit_four_on_gbk_console(self):
        """doctor／fonts／review／tide／mirror-check：gbk 控制台下一律不许 exit 4。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            proj = init_project(base / "proj")
            before = base / "before"
            after = base / "after"
            shutil.copytree(proj, before)
            shutil.copytree(proj, after)
            mirror_b = base / "mirror_b"
            shutil.copytree(proj, mirror_b)
            cases = [
                ("doctor", ("doctor", str(proj))),
                ("fonts", ("fonts", "--status")),
                ("review", ("review", "--before", str(before),
                             "--after", str(after))),
                ("tide", ("tide", "--before", str(before),
                           "--after", str(after))),
                ("mirror-check", ("mirror-check", str(proj), str(mirror_b))),
            ]
            for name, argv in cases:
                with self.subTest(command=name):
                    code, out, err = run_cli(*argv, encoding=GBK)
                    self.assertNotEqual(
                        code, 4,
                        name + " 退成工具内部错误："
                        + err.decode(GBK, "replace"))
                    self.assertNotIn("UnicodeEncodeError",
                                     err.decode(GBK, "replace"))
                    self.assertNotIn("Traceback", err.decode(GBK, "replace"))

    def test_json_payload_is_identical_under_gbk_and_utf8(self):
        """--json：两种控制台编码下内容逐字相同（不许被编码改写）。"""
        code_u8, out_u8, _ = run_cli("audit", "examples/minimal", "--json",
                                    encoding="utf-8")
        code_gbk, out_gbk, _ = run_cli("audit", "examples/minimal", "--json",
                                     encoding=GBK)
        self.assertEqual(code_u8, code_gbk)
        text_u8 = out_u8.decode("utf-8")
        text_gbk = out_gbk.decode(GBK)
        self.assertEqual(text_u8, text_gbk,
                         "结构化输出不许因为控制台编码被改写")
        self.assertEqual(json.loads(text_u8), json.loads(text_gbk))


class TestConsoleFallbackTable(unittest.TestCase):
    """降级表本身：编不出来的字符换同义 ASCII（不是问号）。"""

    def test_glyphs_map_to_readable_ascii(self):
        from factscribe.console import ERROR_HANDLER
        from factscribe.console import _register_handler
        _register_handler()
        text = "✓ ✗ ↔ ⇒ ⊆ « » ²"
        encoded = text.encode("gbk", ERROR_HANDLER)
        self.assertEqual(encoded.decode("gbk"), "v x <-> => <= << >> ^2")

    def test_utf8_text_is_untouched(self):
        from factscribe.console import ERROR_HANDLER
        from factscribe.console import _register_handler
        _register_handler()
        text = "✓ 中文 ↔"
        self.assertEqual(text.encode("utf-8", ERROR_HANDLER).decode("utf-8"),
                         text)

    def test_unknown_char_falls_back_to_question_mark(self):
        from factscribe.console import ERROR_HANDLER
        from factscribe.console import _register_handler
        _register_handler()
        # 表外的字符不许炸：换成问号，命令继续跑。
        self.assertEqual("\u2028".encode("gbk", ERROR_HANDLER).decode("gbk"),
                         "?")


if __name__ == "__main__":
    unittest.main()
