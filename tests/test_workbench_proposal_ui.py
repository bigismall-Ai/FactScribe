# -*- coding: utf-8 -*-
"""tests/test_workbench_proposal_ui.py —— v2 前端契约：差异卡与提议流。

页面这一层没有单测框架可跑（它是浏览器里的原生 JS），所以按仓里既有的
做法（tests/test_workbench_layout.py）：用字符串断言把契约钉住——
「页面上必须有这些东西」「它必须调这些接口」「它不许再直写稿」。

钉的六组：

1. **徽标**：左栏头部有「待确认」入口与计数位；
2. **差异卡模态**：有模态与列表容器，卡里有改前/改后两栏与采纳/拒绝按钮；
3. **JS 函数**：载入、渲染、采纳、拒绝、打开五个函数都在；
4. **接口路径**：页面调 `/proposal`、`/confirm`、`/reject`；
5. **AI 写稿改道**：页面不再直调 `/draft/insert`（那条路绕过指纹闸）；
6. **样式**：差异卡有 CSS。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATIC = ROOT / "factscribe" / "workbench" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")


class ProposalUiContractTest(unittest.TestCase):
    """v2 前端契约：差异卡在页面上，且只走提议单这一条路。"""

    def test_badge_entry_exists(self):
        """左栏头部有「待确认」入口与计数位。"""
        self.assertIn('id="btnProposals"', HTML)
        self.assertIn('id="proposalCount"', HTML)

    def test_modal_and_list_exist(self):
        """差异卡模态与列表容器都在。"""
        self.assertIn('id="modalProposal"', HTML)
        self.assertIn('id="proposalList"', HTML)

    def test_card_has_before_after_and_buttons(self):
        """卡里有改前/改后两栏与采纳/拒绝按钮。"""
        self.assertIn("prop-before", JS)
        self.assertIn("prop-after", JS)
        self.assertIn("data-confirm", JS)
        self.assertIn("data-reject", JS)

    def test_js_functions_exist(self):
        """五个函数都在（名字是约定，别改）。"""
        for name in ("loadProposals", "renderProposals", "confirmProposal",
                     "rejectProposal", "openProposals"):
            self.assertIn("function %s(" % name, JS)

    def test_api_paths_are_called(self):
        """页面调提议单的三个路径。"""
        self.assertIn("/proposal", JS)
        self.assertIn("/confirm", JS)
        self.assertIn("/reject", JS)

    def test_ai_write_no_longer_writes_directly(self):
        """AI「写进稿」改道：页面不再直调 /draft/insert（那条路绕过指纹闸）。"""
        self.assertNotIn("/draft/insert", JS)

    def test_diff_card_has_css(self):
        """差异卡有样式。"""
        self.assertIn("proposal-card", CSS)
