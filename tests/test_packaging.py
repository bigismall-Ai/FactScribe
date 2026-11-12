# -*- coding: utf-8 -*-
"""打包面：wheel 必须带运行时要读的数据文件。

背景：`pip install -e .` 直接读源码目录，数据文件缺了也看不出来；
真正打成 wheel 后，`prescribe` 与中文 `style` 会在运行时才报“文件不存在”。
本组测试用 `pyproject.toml` 的 `package-data` 做静态锁，CI 的 wheel 任务做真装锁。
"""
from __future__ import annotations

import fnmatch
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import load_toml  # noqa: E402


class PackageDataTest(unittest.TestCase):
    def setUp(self):
        data = load_toml(ROOT / "pyproject.toml")
        self.globs = list(
            data["tool"]["setuptools"]["package-data"]["factscribe"])

    def test_runtime_data_is_declared(self):
        for rel in ("terms/seg.tsv.gz", "terms/paper.tsv",
                    "patterns/priority.toml", "patterns/PLAYBOOK.md"):
            self.assertTrue(
                any(fnmatch.fnmatchcase(rel, g) for g in self.globs),
                "%s 不在 package-data 里" % rel)

    def test_no_data_file_is_left_out(self):
        """factscribe/ 下每个非 .py 文件都必须被某条 package-data 覆盖。"""
        pkg = ROOT / "factscribe"
        missing = []
        for path in pkg.rglob("*"):
            if not path.is_file() or path.suffix == ".py":
                continue
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(pkg).as_posix()
            if not any(fnmatch.fnmatchcase(rel, g) for g in self.globs):
                missing.append(rel)
        self.assertEqual(missing, [],
                         "这些数据文件不会进 wheel：%s" % "、".join(missing))


if __name__ == "__main__":
    unittest.main()
