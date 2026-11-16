#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factscribe_legal CLI 的废弃窗口提示测试（SPEC-CHECKS 裁定⑥，2026-11-16）。

核验槽时代（M2 起），五条子命令保留作调试／单域入口（不删功能、废弃窗口
不限期）；每次子命令运行输出一行提示，措辞照 README「核验槽时代」一节：
「单域调试入口……正式报告走 factscribe audit [checks]」。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import os
import subprocess
import sys
import tempfile
import unittest

PKG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

NOTICE_SNIPPETS = ("单域调试入口", "废弃窗口不限期", "factscribe audit [checks]")


def run_cli(*args, cwd=None):
    env = dict(os.environ, PYTHONPATH=PKG_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "factscribe_legal", *args],
        cwd=cwd or PKG_ROOT, env=env, capture_output=True, text=True)


class TestDeprecationNotice(unittest.TestCase):
    def test_notice_printed_and_functionality_intact(self):
        # verify-case 对空项目＝绿报告 exit 0；提示行出现且功能不坏。
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli("verify-case", "--project", tmp)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        lines = proc.stdout.splitlines()
        notice, report = lines[0], "\n".join(lines[1:])
        for snippet in NOTICE_SNIPPETS:
            self.assertIn(snippet, notice)
        self.assertIn("绿", report)          # 报告本体照旧
        self.assertIn("退出码 0", report)     # 退出码语义不被提示行挪动

    def test_notice_present_on_every_subcommand(self):
        # 五条子命令各跑一次（无料即绿/报缺，都不许坏）；提示行必须在。
        cases = [
            ("verify-case", ("--project", ".")),
            ("fetch", ("--corpus", ".", "--project", ".", "--nums", "L1")),
            ("verify", ("--project", ".", "--corpus", ".", "--date",
                        "2026-11-14")),
            ("verify-cn", ("--project", ".", "--catalog", ".", "--date",
                           "2026-11-14")),
            ("verify-it", ("--project", ".", "--corpus", ".", "--date",
                           "2026-11-14")),
        ]
        for cmd, args in cases:
            with self.subTest(cmd=cmd):
                proc = run_cli(cmd, *args)
                for snippet in NOTICE_SNIPPETS:
                    self.assertIn(snippet, proc.stdout, proc.stdout)
                self.assertNotEqual(proc.returncode, 2,
                                    "用法错＝CLI 面坏了：%s" % proc.stderr)

    def test_help_still_works_on_two_subcommands(self):
        # --help 抽两子命令（验收门 g）：功能面不坏。
        for cmd in ("verify", "verify-it"):
            with self.subTest(cmd=cmd):
                proc = run_cli(cmd, "--help")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("usage:", proc.stdout)
                self.assertNotIn("单域调试入口", proc.stdout)   # --help 不掺提示行


if __name__ == "__main__":
    unittest.main()
