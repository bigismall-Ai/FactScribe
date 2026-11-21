# -*- coding: utf-8 -*-
"""tests/test_workbench_layout.py —— 条目 31（段五返修四）：严格左右分栏。

框架三条，静态断言就够（布局的真读数靠浏览器，这里守结构不跑偏）：

1. **顶栏整条拆除**——页面里没有 ``.topbar`` 元素，也没有 ``<header>``；
   ``body`` 不留 52px 顶部留白。
2. **左栏＝顶部窄条 ＋ 其下正文**——``.left-head`` 里只有 FactScribe 字标与
   「项目管理」钮，**没有**新建钮；新建钮只在项目列表页（``#viewProjects``），
   工作台（``#viewWorkbench``）里没有。
3. **右栏＝切换钮列 ＋ 面板**——钮列在面板右侧、竖排一列；中/EN 切换在
   右栏顶部条（面板头部 ``#npHead``），单语项目整组隐藏。

CSS 侧另断言：钮列 ``top:0``（不再垂直居中悬浮）、面板 ``top:0``（不再让开
顶栏 52px）。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATIC = ROOT / "factscribe" / "workbench" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")


def _block(pattern: str, text: str = HTML) -> str:
    match = re.search(pattern, text, re.DOTALL)
    return match.group(0) if match else ""


class NoTopbarTests(unittest.TestCase):
    """① 顶栏整条拆除。"""

    def test_no_topbar_element(self):
        self.assertNotIn('class="topbar"', HTML)
        self.assertNotIn("<header", HTML)

    def test_body_has_no_top_padding(self):
        self.assertIn("body{padding-top:0}", CSS)

    def test_topbar_css_is_neutralised(self):
        self.assertIn(".topbar{display:none !important}", CSS)


class LeftColumnTests(unittest.TestCase):
    """② 左栏＝顶部窄条（FactScribe ＋ Projects）＋ 其下正文。"""

    def test_left_column_exists(self):
        self.assertIn('class="left-col" id="leftCol"', HTML)

    def test_left_head_has_brand_and_projects(self):
        head = _block(r'<div class="left-head">.*?</div>\s*\n\s*\n')
        self.assertIn('class="tb-brand"', head)
        self.assertIn('id="goProjects"', head)

    def test_left_head_has_no_new_button(self):
        head = _block(r'<div class="left-head">.*?</div>\s*\n\s*\n')
        self.assertNotIn('id="goNew"', head)

    def test_new_button_lives_only_on_projects_page(self):
        self.assertIn('id="goNew"', _block(r'<main class="mainview" id="viewProjects">.*?</main>'))
        self.assertNotIn('id="goNew"', _block(r'<main class="doc" id="viewWorkbench">.*?</main>'))

    def test_doc_sits_under_left_head(self):
        col = _block(r'<div class="left-col" id="leftCol">.*?\n  </div><!-- /left-col -->')
        self.assertIn('class="left-head"', col)
        self.assertIn('id="viewWorkbench"', col)


class RightColumnTests(unittest.TestCase):
    """③ 右栏＝切换钮列（锚顶）＋ 面板。"""

    def test_lang_toggle_in_panel_head(self):
        head = _block(r'<div class="np-head" id="npHead">.*?</div>\s*\n\s*\n')
        self.assertIn('id="langSeg"', head)
        self.assertNotIn('id="goProjects"', head)

    def test_projects_button_left_the_panel(self):
        panel = _block(r'<aside class="navpanel" id="navPanel">.*?</aside>')
        self.assertNotIn('id="goProjects"', panel)

    def test_rail_is_inside_the_panel_not_floating(self):
        """条目 32：钮列进侧栏内部，不再是窗口右缘的悬浮元素。"""
        self.assertIn(".side-rail{position:static;", CSS)
        self.assertNotIn(".side-rail{position:fixed", CSS)
        self.assertIn("np-inner", HTML)
        panel = _block(r'<aside class="navpanel" id="navPanel">.*?</aside>')
        self.assertIn('class="side-rail" id="sideRail"', panel)
        self.assertIn('class="np-col"', panel)

    def test_rail_column_precedes_panel_content(self):
        panel = _block(r'<aside class="navpanel" id="navPanel">.*?</aside>')
        self.assertLess(panel.index('id="sideRail"'), panel.index('class="np-col"'))

    def test_panel_starts_at_top(self):
        self.assertIn(".navpanel{top:0;height:100vh}", CSS)

    def test_collapse_button_anchors_to_window_edge(self):
        """收起后剩下的「展开导航」钮贴窗缘（不再是左缘）。"""
        self.assertIn(".nav-open{display:none;position:fixed;right:0;top:0;", CSS)
        self.assertNotIn(".nav-open{display:none;position:fixed;left:0;", CSS)

    def test_single_language_hides_the_whole_head(self):
        self.assertIn("const head = $('#npHead');", JS)
        self.assertIn("if (head) head.hidden = !multi;", JS)
        self.assertIn(".np-head[hidden]{display:none}", CSS)


class RailButtonTests(unittest.TestCase):
    """切换钮列的成员与顺序。"""

    def test_rail_buttons_present(self):
        rail = _block(r'<div class="side-rail" id="sideRail">.*?</div>\s*\n\s*<div class="np-col">')
        for button_id in ("npCollapse", "npToc", "npAi", "npReports", "npKb", "npVenue"):
            self.assertIn('id="%s"' % button_id, rail)

    def test_rail_is_a_vertical_column(self):
        self.assertIn("flex-direction:column", CSS)


if __name__ == "__main__":
    unittest.main()
