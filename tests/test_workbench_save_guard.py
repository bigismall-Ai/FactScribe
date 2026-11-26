# -*- coding: utf-8 -*-
"""保存这条路上的两道闸：.bak 保留多份 ＋ 刷新页面不触发保存。

第一道（引擎）：正文保存前的备份**不再互相覆盖**——按本盘既有命名风格留
多份（.bak 是上一版、.bak.1 是上上版……轮转保留）。配置文件（factscribe.toml）
仍旧只留固定名那一份：「打开磁盘」这个动作本身就会写一次配置，留多份会在
盘上堆垃圾——这条既有副作用保持原样。

第二道（前端）：只有**真编辑过**的块才保存。刷新页面、打开盘、引擎自己
写盘（last_opened 之类）都不算编辑——不碰正文，也就不该触发保存。

前端的闸用静态断言守（口径写在 app.js 的注释里）；真浏览器的实测在
docs/MINIAPP-E2E-ACCEPTANCE-20261122.md 里。

跑法（仓根）：python3 -m pytest tests/test_workbench_save_guard.py -q
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench.projects import disk_sections  # noqa: E402
from factscribe.workbench.write import (BACKUP_KEEP, atomic_write,  # noqa: E402
                                        find_block, save_block, touch_opened)

MINIMAL = ROOT / "examples" / "minimal"
STATIC = ROOT / "factscribe" / "workbench" / "static"

CJK_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")


class BackupRotationTests(unittest.TestCase):
    """.bak 保留多份，不互相覆盖。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-backup-keep-"))
        self.path = self.tmp / "x.tex"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_each_generation_is_kept(self):
        self.path.write_text("v0", encoding="utf-8")
        atomic_write(self.path, "v1", keep=BACKUP_KEEP)
        atomic_write(self.path, "v2", keep=BACKUP_KEEP)
        atomic_write(self.path, "v3", keep=BACKUP_KEEP)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "v3")
        self.assertEqual((self.tmp / "x.tex.bak").read_text(encoding="utf-8"), "v2")
        self.assertEqual((self.tmp / "x.tex.bak.1").read_text(encoding="utf-8"), "v1")
        self.assertEqual((self.tmp / "x.tex.bak.2").read_text(encoding="utf-8"), "v0")

    def test_the_oldest_generation_is_dropped(self):
        self.path.write_text("v0", encoding="utf-8")
        for index in range(1, BACKUP_KEEP + 3):
            atomic_write(self.path, "v%d" % index, keep=BACKUP_KEEP)
        self.assertFalse((self.tmp / ("x.tex.bak.%d" % BACKUP_KEEP)).exists(),
                         "超过上限就该淘汰最老的那一代")
        self.assertTrue((self.tmp / "x.tex.bak").is_file())

    def test_the_edit_path_keeps_several_generations(self):
        """正文写回那条路（save_block）也留多份。"""
        disk = self.tmp / "paper"
        shutil.copytree(MINIMAL, disk)
        blocks = disk_sections(disk).get("blocks") or []
        target = None
        for block in blocks:
            if block.get("kind") == "para":
                target = block
                break
        self.assertIsNotNone(target, "样例盘里没有正文块")
        rel = str(target.get("file") or "")
        block_id = str(target.get("id") or "")
        found = find_block(disk, rel, block_id)
        save_block(disk, rel, block_id, found.raw + " 第一处改动。")
        save_block(disk, rel, block_id, found.raw + " 第二处改动。")
        base = disk / rel
        self.assertTrue((base.parent / (base.name + ".bak")).is_file())
        self.assertTrue((base.parent / (base.name + ".bak.1")).is_file(),
                        "第二次保存不该把 .bak 覆盖掉")

    def test_the_config_write_keeps_one_backup_only(self):
        """配置（factscribe.toml）仍旧只留固定名那一份——既有副作用不变。"""
        disk = self.tmp / "paper2"
        shutil.copytree(MINIMAL, disk)
        touch_opened(disk)
        touch_opened(disk)
        self.assertTrue((disk / "factscribe.toml.bak").is_file())
        self.assertFalse((disk / "factscribe.toml.bak.1").exists())


class FrontendSaveGuardTests(unittest.TestCase):
    """前端静态闸：真编辑过才保存；刷新页面不触发保存。"""

    @classmethod
    def setUpClass(cls):
        cls.app = (STATIC / "app.js").read_text(encoding="utf-8")

    def test_input_marks_the_block_dirty(self):
        self.assertIn("addEventListener('input'", self.app)
        self.assertIn("node.dataset.dirty = '1'", self.app)

    def test_saving_requires_the_dirty_mark(self):
        self.assertIn("if (node.dataset.dirty !== '1') return;", self.app)

    def test_the_focusout_path_checks_the_dirty_mark(self):
        hit = re.search(r"addEventListener\('focusout'[\s\S]{0,1600}", self.app)
        self.assertIsNotNone(hit, "找不到 focusout 那段")
        self.assertIn("dataset.dirty", hit.group(0))

    def test_a_saved_block_is_cleaned_up(self):
        self.assertIn("delete node.dataset.dirty;", self.app)

    def test_refreshing_with_unsaved_text_warns_instead_of_saving(self):
        self.assertIn("addEventListener('beforeunload'", self.app)

    def test_only_the_input_event_marks_a_block_dirty(self):
        """引擎自己写盘（last_opened 之类）不打脏标记——只有 input 事件打。"""
        self.assertEqual(self.app.count("node.dataset.dirty = '1'"), 1)


class CandidateFoldTests(unittest.TestCase):
    """候选列表改版：默认只显示已签；未签折叠进「搜索未签产物」。"""

    @classmethod
    def setUpClass(cls):
        cls.app = (STATIC / "app.js").read_text(encoding="utf-8")
        cls.html = (STATIC / "index.html").read_text(encoding="utf-8")

    def test_the_unsigned_group_is_a_folded_region(self):
        self.assertIn('id="afUnsignedFold"', self.html)
        self.assertIn("<details", self.html)
        self.assertIn('data-i18n="ff.g.unsignedFold"', self.html)
        self.assertIn('data-i18n="ff.tag.unsigned"', self.html)

    def test_the_unsigned_list_is_only_rendered_when_opened(self):
        self.assertIn("const open = fold ? fold.open : true;", self.app)
        self.assertIn("unsignedHost.innerHTML = open", self.app)

    def test_the_fold_toggles_the_list(self):
        self.assertIn("afUnsignedFold').addEventListener('toggle'", self.app)

    def test_both_languages_have_the_new_keys(self):
        for key in ("ff.g.unsignedFold", "ff.tag.unsigned", "ff.sha.manifest",
                    "ff.sha.live", "ai.kindHostDefault"):
            self.assertEqual(self.app.count("'" + key + "':"), 2,
                             key + " 应当中英各一条")

    def test_the_english_labels_have_no_chinese(self):
        for key in ("ff.g.unsignedFold", "ff.tag.unsigned", "ai.kindHostDefault"):
            texts = re.findall("'" + key + "': '([^']*)'", self.app)
            self.assertTrue(texts, "找不到 " + key)
            english = [t for t in texts if not CJK_RE.search(t)]
            self.assertTrue(english, key + " 的英文条目没找到")


if __name__ == "__main__":
    unittest.main()
