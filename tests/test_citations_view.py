# -*- coding: utf-8 -*-
"""引用页的数据层：多 bib 汇总 + 每条的状态（factscribe/citeview.py）。

钉住：

- bib 集合 = 配置里的 bib + 正文 `\\bibliography{}` 提到的（两个都进）；
- 汇总口径：total / used / unused / no_id / bad_id；
- 跨文件重复 key 单独算 duplicate，并给标记与它出现过的文件与它出现过的文件；
- 标识格式不合法也算 bad_id（复用 citations.valid_stable_id）；
- 没有 bib 时是空表，不是报错。

跑法（仓根）：python3 -m unittest discover -s tests -p "test_citations_view.py"
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.citeview import citations_data  # noqa: E402

PAPERKIT_TOML = """\
[project]
title = "引用页测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

INTRO_TEX = """\
\\section{引言}
我们基于 \\cite{alpha2020} 与 \\citep{beta2021} 开展工作。
\\bibliography{extra}
"""

REFS_BIB = """\
@article{alpha2020,
  title = {Alpha Paper},
  doi  = {10.1000/alpha}
}

@inproceedings{beta2021,
  title = {Beta Paper},
  arxiv = {2101.00001}
}

@article{gamma2022,
  title = {Gamma Paper}
}
"""

EXTRA_BIB = """\
@article{delta2023,
  title = {Delta Paper},
  doi = {10.1000/delta}
}

@article{alpha2020,
  title = {Alpha Paper Once More},
  doi = {10.1000/alpha-again}
}

@article{epsilon2024,
  title = {Epsilon Paper},
  doi = {not-a-doi}
}
"""


class CitationsDataTest(unittest.TestCase):
    """临时项目：两个 bib（一个来自配置，一个来自 \\bibliography{}）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "paper"
        (self.root / "sections").mkdir(parents=True)
        (self.root / "facts").mkdir(parents=True)
        (self.root / "paperkit.toml").write_text(PAPERKIT_TOML, encoding="utf-8")
        (self.root / "refs.bib").write_text(REFS_BIB, encoding="utf-8")
        (self.root / "extra.bib").write_text(EXTRA_BIB, encoding="utf-8")
        (self.root / "sections" / "01-intro.tex").write_text(INTRO_TEX,
                                                              encoding="utf-8")
        self.data = citations_data(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------ 工具

    def rows(self, key):
        return [row for row in self.data["entries"] if row["key"] == key]

    def row(self, key, file=None):
        found = self.rows(key)
        if file:
            found = [r for r in found if r["file"] == file]
        self.assertEqual(1, len(found), "key %r 应有且只有一条，实际 %d"
                         % (key, len(found)))
        return found[0]

    # ------------------------------------------------------------ bib 集合

    def test_both_bib_files_are_collected(self):
        paths = [item["path"] for item in self.data["files"]]
        self.assertIn("refs.bib", paths, "配置里的 bib 要在")
        self.assertIn("extra.bib", paths, "正文 \\bibliography{} 的 bib 要在")
        self.assertEqual(2, len(self.data["files"]))

    def test_file_entries_count(self):
        by_path = {item["path"]: item for item in self.data["files"]}
        self.assertEqual(3, by_path["refs.bib"]["entries"])
        self.assertEqual(3, by_path["extra.bib"]["entries"])

    # ------------------------------------------------------------ 汇总

    def test_totals(self):
        self.assertEqual(6, self.data["total"])
        # alpha2020 出现两次，都被引到；beta2021 被引到 → 3 条已用
        self.assertEqual(3, self.data["used"])
        self.assertEqual(3, self.data["unused"])
        self.assertEqual(self.data["total"], self.data["used"] + self.data["unused"])
        self.assertEqual(1, self.data["no_id"])
        self.assertEqual(1, self.data["bad_id"])
        self.assertEqual(2, self.data["duplicate"])

    # ------------------------------------------------------------ 每条的状态

    def test_used_entry_is_ok(self):
        row = self.row("beta2021")
        self.assertEqual("ok", row["status"])
        self.assertEqual(1, row["used"])
        self.assertEqual("2101.00001", row["arxiv"])
        self.assertEqual("inproceedings", row["kind"])
        self.assertEqual("refs.bib", row["file"])
        self.assertTrue(row["line"] > 0, "要给出 bib 里的行号")
        self.assertFalse(row["duplicate"])

    def test_missing_id_is_no_id(self):
        row = self.row("gamma2022")
        self.assertEqual("no_id", row["status"])
        self.assertEqual(0, row["used"])
        self.assertEqual("", row["doi"])

    def test_unused_entry(self):
        row = self.row("delta2023")
        self.assertEqual("unused", row["status"])
        self.assertEqual(0, row["used"])

    def test_invalid_id_is_bad_id(self):
        row = self.row("epsilon2024")
        self.assertEqual("bad_id", row["status"])
        self.assertEqual("not-a-doi", row["doi"])

    def test_duplicate_key_across_files(self):
        rows = self.rows("alpha2020")
        self.assertEqual(2, len(rows), "两个 bib 里的同名 key 都要列出来")
        for row in rows:
            self.assertEqual("duplicate", row["status"])
            self.assertTrue(row["duplicate"], "跨文件重复 key 要标出来")
            self.assertEqual(["extra.bib", "refs.bib"], row["files"])
        self.assertEqual({1}, {row["used"] for row in rows},
                         "同一个 key 的引用次数按 key 统计，两边一样")

    def test_entry_shape(self):
        row = self.row("alpha2020", file="refs.bib")
        for field in ("key", "kind", "title", "doi", "arxiv", "url", "file",
                      "line", "used", "files", "status"):
            self.assertIn(field, row, "每条都要有 " + field)
        self.assertEqual("Alpha Paper", row["title"])
        self.assertIsInstance(row["files"], list)


class EmptyProjectTest(unittest.TestCase):
    """没有 bib 的项目：空表，不是报错。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "paper"
        (self.root / "sections").mkdir(parents=True)
        (self.root / "facts").mkdir(parents=True)
        (self.root / "paperkit.toml").write_text(PAPERKIT_TOML, encoding="utf-8")
        (self.root / "sections" / "01-intro.tex").write_text(
            "这一节没有引用。\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_bib_is_empty_not_error(self):
        data = citations_data(self.root)
        self.assertEqual(0, data["total"])
        self.assertEqual(0, data["used"])
        self.assertEqual(0, data["unused"])
        self.assertEqual(0, data["no_id"])
        self.assertEqual(0, data["bad_id"])
        self.assertEqual([], data["files"])
        self.assertEqual([], data["entries"])


class CiteCountTest(unittest.TestCase):
    """正文引用次数：按 key 数出现次数；\\nocite{*} ＝整库引用。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "paper"
        (self.root / "sections").mkdir(parents=True)
        (self.root / "facts").mkdir(parents=True)
        (self.root / "paperkit.toml").write_text(PAPERKIT_TOML, encoding="utf-8")
        (self.root / "refs.bib").write_text(REFS_BIB, encoding="utf-8")
        (self.root / "extra.bib").write_text(EXTRA_BIB, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, text: str):
        (self.root / "sections" / "01-intro.tex").write_text(text,
                                                             encoding="utf-8")

    def test_counts_every_occurrence(self):
        self._write("见 \\cite{beta2021} 与 \\cite{beta2021,delta2023}。\n"
                    "\\bibliography{extra}\n")
        data = citations_data(self.root)
        rows = {row["key"]: row for row in data["entries"]}
        self.assertEqual(2, rows["beta2021"]["used"])
        self.assertEqual(1, rows["delta2023"]["used"])

    def test_nocite_star_marks_whole_library(self):
        self._write("\\nocite{*}\n")
        data = citations_data(self.root)
        self.assertTrue(data["nocite_all"])
        self.assertEqual(3, data["used"], "\\nocite{*} 是整库引用")
        self.assertEqual(0, data["unused"])


if __name__ == "__main__":
    unittest.main()
