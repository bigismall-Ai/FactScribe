# -*- coding: utf-8 -*-
"""tests/test_miniapp_setup_page.py —— 首启设置页的中/EN 切换（静态契约）。

首启页由 Node 薄壳伺服（miniapp/miniapp/node/server.mjs 里的 setupPageHtml），
它没有工作台那套 data-i18n 机制，翻译直接内嵌在页面脚本的词典里。

这里守三件事：

1. **切换钮常显**——首启页也有中/EN（不藏）；
2. **两套文案都在**——zh 与 en 各一份，键名一致；
3. **提示文案全部来自词典**——提交处理器里不再硬编码中文，
   免得切到英文后提示还是中文；页面也不许自己写浏览器存储
   （插件的写盘面仍然只有「私有 dataDir」与「论文根目录」两处）。
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "miniapp" / "miniapp" / "node" / "server.mjs"
SOURCE = SERVER.read_text(encoding="utf-8")

# 设置页模板函数的那一段（含 <script> 里的词典与切换逻辑）。
START = SOURCE.index("function setupPageHtml(")
END = SOURCE.index("/** @param {string} s */", START)
PAGE = SOURCE[START:END]

# 提交处理器（提示文案都该从词典取）。
HANDLER = PAGE[PAGE.index("form.addEventListener('submit'"):PAGE.index("</script>")]

CJK = re.compile(r"[\u3000-\u9fff]")


class SetupPageLangToggleTests(unittest.TestCase):
    """① 切换钮常显。"""

    def test_page_has_lang_segment(self):
        self.assertIn('id="langSeg"', PAGE)
        self.assertIn('data-lang="zh"', PAGE)
        self.assertIn('data-lang="en"', PAGE)

    def test_toggle_is_not_hidden(self):
        """不许用 hidden 把切换钮藏掉。"""
        self.assertNotIn('id="langSeg" role="group" aria-label="language" hidden', PAGE)
        self.assertNotIn("langSeg').hidden", PAGE)
        self.assertNotIn("langSeg\").hidden", PAGE)

    def test_toggle_click_switches_page(self):
        self.assertIn("document.getElementById('langSeg').addEventListener('click'", PAGE)
        self.assertIn("applyLang(button.getAttribute('data-lang'))", PAGE)


class SetupPageI18nTests(unittest.TestCase):
    """② 两套文案都在，键名一致。"""

    def test_both_dictionaries_exist(self):
        self.assertIn("zh: {", PAGE)
        self.assertIn("en: {", PAGE)

    def test_english_strings_present(self):
        for text in ("First-time setup", "FactScribe Paper Workbench", "Apply",
                     "Type a folder path first.", "Applying…",
                     "Saved. Opening the workbench…", "Could not save. Please check the path.",
                     "Network error. Please retry."):
            self.assertIn(text, PAGE)

    def test_both_dictionaries_share_the_same_keys(self):
        """zh 与 en 的键必须一一对应（少一个键＝切语言后露出半截中文）。"""
        zh = PAGE[PAGE.index("zh: {"):PAGE.index("en: {")]
        en = PAGE[PAGE.index("en: {"):PAGE.index("};", PAGE.index("en: {"))]
        zh_keys = set(re.findall(r"^\s{6}(\w+):", zh, re.M))
        en_keys = set(re.findall(r"^\s{6}(\w+):", en, re.M))
        self.assertTrue(zh_keys, "zh 词典没解析出键")
        self.assertEqual(zh_keys, en_keys)

    def test_lang_attribute_and_title_follow(self):
        self.assertIn("document.documentElement.lang", PAGE)
        self.assertIn("document.title = d.title;", PAGE)


class SetupPageWriteSurfaceTests(unittest.TestCase):
    """③ 提示文案来自词典；页面不自己写存储。"""

    def test_submit_messages_come_from_dictionary(self):
        """提交处理器里不许出现硬编码中文（切到英文后提示也得是英文）。"""
        self.assertIsNone(CJK.search(HANDLER), "提交处理器里还有硬编码中文")
        for key in ("d.empty", "d.applying", "d.saved", "d.fail", "d.neterr"):
            self.assertIn(key, HANDLER)

    def test_page_does_not_write_browser_storage(self):
        """插件的写盘面仍只有两处（私有 dataDir、论文根目录）——首启页不加第三处。"""
        self.assertNotIn("localStorage", PAGE)
        self.assertNotIn("sessionStorage", PAGE)
        self.assertNotIn("indexedDB", PAGE)


if __name__ == "__main__":
    unittest.main()
