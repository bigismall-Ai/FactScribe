# -*- coding: utf-8 -*-
"""不许有 invalid escape sequence 这类 SyntaxWarning。

Python 3.12+ 把部分警告升级成错误；在那之前它们只是刷屏，但会在未来变成
SyntaxError。这里用编译期警告当错误，把问题挡在提交前。
"""
from __future__ import annotations

import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class SyntaxWarningTest(unittest.TestCase):
    def test_package_has_no_syntax_warnings(self):
        files = sorted((ROOT / "factscribe").rglob("*.py"))
        self.assertTrue(files, "没找到 factscribe 包")
        bad = []
        for path in files:
            source = path.read_text(encoding="utf-8")
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("error", SyntaxWarning)
                try:
                    compile(source, str(path), "exec")
                except SyntaxWarning as exc:
                    bad.append("%s: %s" % (path.relative_to(ROOT), exc))
                except SyntaxError:
                    # 语法错由别的测试兜底；这里只盯逃逸序列警告
                    continue
        self.assertEqual([], bad, "存在 SyntaxWarning：\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
