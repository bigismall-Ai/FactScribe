# -*- coding: utf-8 -*-
"""F7：citeedit（写侧）与 citeview（读侧）的项目根口径统一。

原来的毛病：同一套代码里有两个「项目根」口径——

* `factscribe/citeedit.py`：`cfg.root.resolve()`（解析软链）
* `factscribe/citeview.py`：`os.path.normpath(cfg.root)`（不解析软链）

同一个项目在两侧算出的根目录可能不同，于是 `Path.relative_to()` 抛
`ValueError`，而调用方只 catch `ConfigError`/`OSError` → 裸崩。
macOS 上 `/tmp` → `/private/tmp`、`/var` → `/private/var`，凡是项目
路径里带软链分量就必然触发。

产品路径（`serve.py` 建服时先 `resolve()`）把它挡住了，所以 HTTP 上
打不到；但库口径不统一就是隐患，直接调库函数就崩。

钉住三件事：

1. 两侧都用 `resolve()`（`citeview.project_root()` 是唯一口径）；
2. 「在不在项目内」的判定规则只有一份（`citeview.inside_root()`）：
   读侧丢、写侧拒；
3. 越界路径、符号链接指向外部、不存在的路径——三种输入两侧行为一致，
   且都是**可预期的错误**（`ConfigError`），不裸崩。

跑法（仓根）：python3 -m unittest discover -s tests -p "test_cite_root_consistency.py"
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.citeedit import citation_add_data, citation_delete_data  # noqa: E402
from factscribe.citeview import (citations_data, inside_root,  # noqa: E402
                                 project_root)
from factscribe.config import ConfigError, load_config  # noqa: E402

FACTSCRIBE_TOML = """\
[project]
title = "引用页根口径测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

INTRO_TEX = """\
\\section{引言}
我们基于 \\cite{alpha2020} 开展工作。
"""

REFS_BIB = """\
@article{alpha2020,
  title = {Alpha Paper},
  doi  = {10.1000/alpha}
}
"""

FACT_TOML = """\
[[fact]]
id = "A1"
claim = "一件事"
value = "1"
source = "results/one.md"
locator = "L1"
confidence = "high"
"""


def make_project(root: Path, bib_rel: str = "refs.bib",
                 tex: str = INTRO_TEX, with_refs: bool = True) -> Path:
    """造一个最小项目（事实账 + 正文 + bib）。bib_rel 可指向项目外。"""
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    toml = FACTSCRIBE_TOML.replace('bib = "refs.bib"', 'bib = "%s"' % bib_rel)
    (root / "factscribe.toml").write_text(toml, encoding="utf-8")
    (root / "facts" / "01-core.toml").write_text(FACT_TOML, encoding="utf-8")
    (root / "results" / "one.md").write_text("evidence\n", encoding="utf-8")
    (root / "sections" / "01-intro.tex").write_text(tex, encoding="utf-8")
    if with_refs and bib_rel == "refs.bib":
        (root / "refs.bib").write_text(REFS_BIB, encoding="utf-8")
    return root


def add_entry(root: Path, key: str = "new2024"):
    return citation_add_data(root, {"key": key, "title": "T", "author": "A",
                                     "year": "2024", "kind": "article"},
                              allow_write=True)


class ProjectRootTest(unittest.TestCase):
    """口径本身：两侧都用 resolve()；越界判定只有一份。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_project_root_resolves_symlinks(self):
        real = self.base / "real"
        real.mkdir()
        project = make_project(real / "paper")
        link = self.base / "link"
        link.mkdir()
        (link / "paper").symlink_to(project, target_is_directory=True)
        cfg = load_config(link / "paper")
        self.assertNotEqual(Path(cfg.root), Path(cfg.root).resolve())
        self.assertEqual(project_root(cfg), Path(cfg.root).resolve())

    def test_inside_root_rule(self):
        root = Path("/tmp/proj")
        self.assertEqual(inside_root(root, "refs.bib"), root / "refs.bib")
        self.assertEqual(inside_root(root, "sub/../refs.bib"), root / "refs.bib")
        self.assertIsNone(inside_root(root, "../outside.bib"))
        self.assertIsNone(inside_root(root, "/etc/passwd"))
        self.assertIsNone(inside_root(root, ""))

    def test_bib_paths_are_under_resolved_root(self):
        real = self.base / "real"
        real.mkdir()
        project = make_project(real / "paper")
        link = self.base / "link"
        link.mkdir()
        (link / "paper").symlink_to(project, target_is_directory=True)
        cfg = load_config(link / "paper")
        data = citations_data(link / "paper")
        self.assertEqual([row["path"] for row in data["files"]], ["refs.bib"])
        self.assertEqual(data["total"], 1)


class SymlinkedProjectRootTest(unittest.TestCase):
    """原崩溃复现：项目根本身是软链时，直接调库函数不许崩。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.real = self.base / "real"
        self.real.mkdir()
        self.project = make_project(self.real / "paper")
        self.links = self.base / "link"
        self.links.mkdir()
        self.linked = self.links / "paper"
        self.linked.symlink_to(self.project, target_is_directory=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_add_citation_through_symlinked_root(self):
        result = add_entry(self.linked)
        self.assertEqual(result["key"], "new2024")
        self.assertEqual(result["path"], "refs.bib")
        self.assertIn(b"new2024", (self.project / "refs.bib").read_bytes())

    def test_view_citations_through_symlinked_root(self):
        data = citations_data(self.linked)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["entries"][0]["key"], "alpha2020")

    def test_delete_citation_through_symlinked_root(self):
        add_entry(self.linked)
        result = citation_delete_data(self.linked, {"key": "new2024"},
                                       allow_write=True)
        self.assertEqual(result["key"], "new2024")
        self.assertNotIn(b"new2024", (self.project / "refs.bib").read_bytes())

    def test_no_valueerror_escapes(self):
        """两侧都不许把 ValueError 抛给调用方。"""
        try:
            add_entry(self.linked)
            citations_data(self.linked)
        except ValueError as exc:      # pragma: no cover - 修复前会命中
            self.fail("ValueError 裸崩：%s" % exc)
        except ConfigError:
            pass


class OutOfBoundsPathTest(unittest.TestCase):
    """越界路径：读侧丢掉、写侧拒；两侧都不碰项目外的文件。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.outside = self.base / "outside.bib"
        self.outside.write_text("@article{evil2020,\n  title = {Evil}\n}\n",
                                 encoding="utf-8")
        self.project = make_project(self.base / "paper", bib_rel="../outside.bib",
                                    with_refs=False)

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_side_refuses_out_of_bounds_bib(self):
        with self.assertRaises(ConfigError) as ctx:
            add_entry(self.project)
        self.assertEqual(ctx.exception.code, "BIB_PATH_ESCAPE")
        self.assertNotIn(b"new2024", self.outside.read_bytes())

    def test_read_side_drops_out_of_bounds_bib(self):
        data = citations_data(self.project)
        self.assertEqual(data["files"], [])
        self.assertEqual(data["total"], 0)

    def test_bibliography_command_pointing_outside_is_dropped(self):
        project = make_project(self.base / "paper2",
                                tex="\\section{引言}\n\\bibliography{../outside}\n")
        data = citations_data(project)
        listed = [row["path"] for row in data["files"]]
        self.assertNotIn("outside.bib", listed)
        add_entry(project)
        self.assertNotIn(b"new2024", self.outside.read_bytes())


class SymlinkEscapeTest(unittest.TestCase):
    """软链指向项目外：读侧不列、写侧拒。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.outside = self.base / "outside.bib"
        self.outside.write_text("@article{evil2020,\n  title = {Evil}\n}\n",
                                 encoding="utf-8")
        self.project = make_project(self.base / "paper", bib_rel="evil.bib",
                                    with_refs=False)
        (self.project / "evil.bib").symlink_to(self.outside)

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_side_refuses_symlink_out_of_project(self):
        with self.assertRaises(ConfigError) as ctx:
            add_entry(self.project)
        self.assertEqual(ctx.exception.code, "BIB_PATH_ESCAPE")
        self.assertNotIn(b"new2024", self.outside.read_bytes())

    def test_read_side_drops_symlink_out_of_project(self):
        data = citations_data(self.project)
        self.assertEqual(data["files"], [])
        self.assertEqual(data["total"], 0)

    def test_in_project_bib_still_works(self):
        """项目内的正常 bib 不受影响。"""
        project = make_project(self.base / "paper2")
        result = add_entry(project)
        self.assertEqual(result["path"], "refs.bib")
        data = citations_data(project)
        self.assertEqual(data["total"], 2)


class MissingPathTest(unittest.TestCase):
    """不存在的路径：不许裸崩。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_bib_file_is_created_on_write(self):
        project = make_project(self.base / "paper", bib_rel="missing.bib")
        result = add_entry(project)
        self.assertEqual(result["path"], "missing.bib")
        self.assertTrue((project / "missing.bib").is_file())

    def test_missing_bib_file_is_not_listed_on_read(self):
        project = make_project(self.base / "paper", bib_rel="missing.bib")
        data = citations_data(project)
        self.assertEqual(data["files"], [])
        self.assertEqual(data["total"], 0)

    def test_missing_bibliography_target_is_dropped(self):
        project = make_project(self.base / "paper2",
                                tex="\\section{引言}\n\\bibliography{nope}\n")
        data = citations_data(project)
        listed = [row["path"] for row in data["files"]]
        self.assertNotIn("nope.bib", listed)
        self.assertEqual(data["total"], 1)   # 只有项目自己那份 refs.bib

    def test_missing_project_raises_config_error(self):
        missing = self.base / "no-such-project"
        with self.assertRaises(ConfigError):
            add_entry(missing)
        with self.assertRaises(ConfigError):
            citations_data(missing)

    def test_delete_from_missing_bib_reports_expected_error(self):
        project = make_project(self.base / "paper", bib_rel="missing.bib")
        with self.assertRaises(ConfigError) as ctx:
            citation_delete_data(project, {"key": "nope2024"}, allow_write=True)
        self.assertEqual(ctx.exception.code, "CITATION_MISSING")


if __name__ == "__main__":
    unittest.main()
