# -*- coding: utf-8 -*-
"""tests/test_miniapp_align.py —— 2026-11-22 四个交互/视觉问题的契约考题。

用户在真机上点了四下，报了四件事：正文要点一下才能编辑、正文里有奇怪的渲染
（点开是 claim/value/source/locator）、点智能助手冒出多余提示、模型选择行前面
有个看不懂的 backend 且下拉框不美观还重复。

这四条的结论钉在这里（面板是浏览器里的原生 JS、薄壳是 Node 脚本，仓里没有
它们的测试框架，所以沿用仓里既有的做法：字符串断言）：

1. **正文即编辑器**：段落生来 contenteditable（没有「只读态 → 点按 → 编辑态」
   两段式）；保护面芯片点击后要把光标放回正文，不许把编辑意图吃掉。
2. **事实标记的形态**：事实芯片（.fc.prot-chip）是「有据的数字」标记，
   契约上必须留着（点它弹证据卡、contenteditable=false、data-fact 在）；
   但它不能套用旧的小圆点妆容（.62em 圆点盒子装不下「✓ B1」，会渲染成
   竖排碎片）——形态要改，标记不许删。
3. **助手面板没有多余提示**：面板顶上不再自带一段「后端说明」气泡。
4. **模型选择区**：模型行前面不留 backend 字段；下拉按来源分组、同一个模型
   只列一条；样式沿用右栏既有控件语汇（不是浏览器默认外观）。

另加一条不变式：仓里的事实源（factscribe/workbench/static）与 miniapp 载荷
里的两份拷贝（client/ 与 vendored engine/）必须逐字节一致。
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = (ROOT / "miniapp" / "miniapp" / "node" / "server.mjs").read_text(encoding="utf-8")
STATIC = ROOT / "factscribe" / "workbench" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")

ZH = JS[JS.index("zh: {"):JS.index("en: {")]
EN = JS[JS.index("en: {"):]


class BodyIsEditorTests(unittest.TestCase):
    """① 正文可直接编辑；芯片不许吃掉点击。"""

    def test_paragraph_is_contenteditable_from_the_start(self):
        """没有「进入编辑」这一步：段落生来可编辑。"""
        self.assertIn("node.setAttribute('contenteditable', 'true')", JS)
        self.assertIn("body.setAttribute('contenteditable', 'true')", JS)

    def test_chip_click_puts_the_caret_back_into_the_text(self):
        """点芯片（看证据／看受保护内容）之后光标要落回正文，能接着改字。"""
        self.assertIn("function caretBesideChip(chip)", JS)
        self.assertIn("range.setStartAfter(chip)", JS)
        self.assertIn("function bindChipCaret(root)", JS)

    def test_chip_caret_is_bound_in_body_and_abstract(self):
        self.assertIn("bindChipCaret(host);", JS)
        self.assertIn("bindChipCaret(body);", JS)

    def test_fact_card_still_opens_on_chip_click(self):
        """事实标记弹证据卡是契约（不能为了「能编辑」把它删了）。"""
        self.assertIn("function openFactCard(id, anchor)", JS)
        self.assertIn("openFactCard(chip.dataset.fact || '', chip);", JS)
        self.assertIn("'fc.claim'", JS)
        self.assertIn("'fc.value'", JS)
        self.assertIn("'fc.source'", JS)
        self.assertIn("'fc.locator'", JS)


class FactChipFormTests(unittest.TestCase):
    """② 事实标记：形态要改，标记不许删。"""

    def test_legacy_dot_geometry_does_not_hit_protected_chips(self):
        """旧的无作用域 .fc 圆点规则已撤（它把新芯片压成 12x8 的小圆点）。"""
        self.assertNotIn(".fc{", CSS)
        self.assertIn(".fc:not(.prot-chip){", CSS)

    def test_fact_chip_has_a_readable_pill_form(self):
        self.assertIn(".fc.prot-chip{", CSS)
        chip_rule = CSS[CSS.index(".fc.prot-chip{"):]
        chip_rule = chip_rule[:chip_rule.index("}")]
        self.assertIn("white-space:nowrap", chip_rule)
        self.assertIn("border-radius", chip_rule)

    def test_protected_chips_never_wrap_vertically(self):
        """长 LaTeX（\\label{...}）也不许竖排成碎片。"""
        rule = CSS[CSS.index(".prot-chip{"):]
        rule = rule[:rule.index("}")]
        self.assertIn("white-space:nowrap", rule)

    def test_chip_contract_kept(self):
        """芯片仍带保护面身份：contenteditable=false ＋ data-fact ＋ 标题。"""
        self.assertIn("data-fact", JS)
        self.assertIn("contenteditable', 'false'", JS)


class AssistantPanelTests(unittest.TestCase):
    """③ 点智能助手不该冒出一段说明书。"""

    def test_no_long_note_bubble(self):
        self.assertNotIn('id="seg4Note"', HTML)
        self.assertNotIn("'ai.note'", JS)

    def test_source_badge_lives_in_the_pane_header(self):
        """「这一轮是谁答的」住在面板顶上，不挤在模型选择行前面。"""
        self.assertIn('id="aiSrc"', HTML)
        header = HTML[HTML.index('id="paneAi"'):HTML.index('id="aiPane"')]
        self.assertIn('id="aiSrc"', header)
        row = HTML[HTML.index('class="ai-modelrow"'):HTML.index('class="ai-input"')]
        self.assertNotIn('id="aiSrc"', row)

    def test_badge_stays_hidden_until_a_reply(self):
        self.assertIn("function renderAiSource()", JS)
        self.assertIn("if (!state.ai.source) { el.hidden = true;", JS)


class ModelPickerTests(unittest.TestCase):
    """④ 模型选择区：没有 backend 残留，下拉分组不重复，样式统一。"""

    def test_no_backend_field_in_the_model_row(self):
        row = HTML[HTML.index('class="ai-modelrow"'):HTML.index('class="ai-input"')]
        self.assertNotIn("aiSrc", row)
        self.assertNotIn("ai.srcIdle", HTML)

    def test_dropdown_is_grouped_by_source(self):
        self.assertIn("document.createElement('optgroup')", JS)
        self.assertIn("['host', 'custom', 'engine'].forEach", JS)

    def test_same_model_is_listed_once(self):
        self.assertIn("function dedupeModelEntries(list)", JS)
        self.assertIn("dedupeModelEntries(state.ai.models || [])", JS)

    def test_shell_dedupes_the_host_catalog(self):
        """薄壳按 modelId 折叠同一模型的多个通道（API 里记 alsoVia）。"""
        self.assertIn("function dedupeHostModels(models, catalogDefault)", SHELL)
        self.assertIn("dedupeHostModels(models, catalog.default)", SHELL)
        self.assertIn("alsoVia", SHELL)

    def test_provider_id_is_not_shown_raw(self):
        """provider 的协议前缀（custom_provider:）不甩给用户看。"""
        self.assertIn("replace(/^custom_provider:/, '')", SHELL)

    def test_dropdown_uses_the_panel_visual_vocabulary(self):
        rule = CSS[CSS.index(".np-ai-face .ai-modelrow select{")::]
        rule = rule[:rule.index("}")]
        self.assertIn("appearance:none", rule)
        self.assertIn("border-radius:8px", rule)

    def test_badge_wording_is_human(self):
        """徽标不再说「后端」这种术语。"""
        self.assertNotIn("后端：", ZH)
        self.assertNotIn("Backend:", EN)
        for key in ("'ai.srcAgent'", "'ai.srcEngine'", "'ai.srcCustom'"):
            self.assertIn(key, ZH)
            self.assertIn(key, EN)


class PayloadInSyncTests(unittest.TestCase):
    """不变式：事实源与两份拷贝逐字节一致（build.sh 同步出来的）。"""

    def test_client_copy_matches_source(self):
        for name in ("app.js", "app.css", "index.html"):
            self.assertEqual(
                (STATIC / name).read_bytes(),
                (ROOT / "miniapp" / "miniapp" / "client" / name).read_bytes(),
                name,
            )

    def test_vendored_engine_copy_matches_source(self):
        engine = ROOT / "miniapp" / "miniapp" / "node" / "engine" / "factscribe" / "workbench" / "static"
        for name in ("app.js", "app.css", "index.html"):
            self.assertEqual((STATIC / name).read_bytes(), (engine / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
