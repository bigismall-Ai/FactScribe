# -*- coding: utf-8 -*-
"""tests/test_workbench_layout.py —— 条目 33（段五验收返修七）：右栏信息架构收敛。

框架三条，静态断言就够（布局的真读数靠浏览器，这里守结构不跑偏）：

1. **顶栏整条拆除**——页面里没有 ``.topbar`` 元素，也没有 ``<header>``；
   ``body`` 不留 52px 顶部留白。
2. **左栏＝顶部窄条 ＋ 其下正文**——``.left-head`` 左侧是可点的 FactScribe 字标
   与「项目管理」钮，右侧是**仅 workbench 视图渲染**的常用功能组
   （中/EN ＋ 渲染PDF/全检一次/导出投稿包/打开目录）；新建钮只在项目列表页。
3. **右栏＝工具条 ＋ 面板**——工具条最左一枚**纯图标**收起钮，右侧三枚互斥切换钮
   （目录／智能助手／更多）；「更多」面板＝实验报告 / 知识库 / 版式 三段合并。
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


def _slice(start: str, end: str, text: str = HTML) -> str:
    """按锚点切一段 HTML（比正则稳：嵌套 div 不会截断）。"""
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


def _visible_text(fragment: str) -> str:
    """抽出片段里的可见文字（去掉标签后剩下的非空白字符）。"""
    close = fragment.find("</button>")
    inner = fragment[fragment.index(">") + 1: close if close != -1 else len(fragment)]
    return re.sub(r"<[^>]+>", "", inner).strip()


LEFT_HEAD = _slice('<div class="left-head">', '<!-- ============ 项目列表页')
TOOLBAR = _slice('<div class="np-toolbar" id="npToolbar">', '<div class="np-col">')
PANE_MORE = _slice('<section class="np-pane" id="paneMore">', '<!-- /np-body -->')
PANE_TOC = _slice('<section class="np-pane on" id="paneToc">', '<section class="np-pane" id="paneAi">')
PANEL = _slice('<aside class="navpanel" id="navPanel">', '</aside>')


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
    """② 左栏＝顶部窄条（可点字标 ＋ Projects ＋ 常用功能组）＋ 其下正文。"""

    def test_left_column_exists(self):
        self.assertIn('class="left-col" id="leftCol"', HTML)

    def test_brand_is_a_clickable_button(self):
        """条目 33：FactScribe 字标可点，与 [Projects] 同去项目管理视图。"""
        self.assertIn('id="goBrand"', LEFT_HEAD)
        self.assertIn('class="tb-brand lh-brand"', LEFT_HEAD)
        self.assertIn("$('#goBrand').addEventListener('click'", JS)

    def test_left_head_has_brand_and_projects(self):
        self.assertIn('class="tb-brand', LEFT_HEAD)
        self.assertIn('id="goProjects"', LEFT_HEAD)

    def test_left_head_has_no_new_button(self):
        self.assertNotIn('id="goNew"', LEFT_HEAD)

    def test_new_button_lives_only_on_projects_page(self):
        self.assertIn('id="goNew"', _slice('<main class="mainview" id="viewProjects">', '</main>'))
        self.assertNotIn('id="goNew"', _slice('<main class="doc" id="viewWorkbench">', '</main>'))

    def test_doc_sits_under_left_head(self):
        col = _slice('<div class="left-col" id="leftCol">', '</div><!-- /left-col -->')
        self.assertIn('class="left-head"', col)
        self.assertIn('id="viewWorkbench"', col)


class LeftHeadToolsTests(unittest.TestCase):
    """条目 33：常用功能组搬进左栏头部，且只在 workbench 视图渲染。"""

    def test_tools_group_lives_in_left_head(self):
        self.assertIn('class="lh-tools" id="lhTools"', LEFT_HEAD)

    def test_lang_toggle_moved_to_left_head(self):
        self.assertIn('id="langSeg"', LEFT_HEAD)
        self.assertNotIn('id="langSeg"', PANEL)

    def test_four_action_buttons_moved_to_left_head(self):
        for button_id in ("actPdf", "actCheck", "actBundle", "actOpenDir"):
            self.assertIn('id="%s"' % button_id, LEFT_HEAD)
            self.assertNotIn('id="%s"' % button_id, PANEL)

    def test_action_behaviour_unchanged(self):
        """搬家不改行为：仍是原来那四个动作处理器。"""
        self.assertIn("$('#actPdf').addEventListener('click', runPdfAction);", JS)
        self.assertIn("$('#actCheck').addEventListener('click', runFullCheck);", JS)
        self.assertIn("$('#actBundle').addEventListener('click', runBundleAction);", JS)
        self.assertIn("$('#actOpenDir').addEventListener('click', runOpenDirAction);", JS)

    def test_tools_group_hidden_outside_workbench(self):
        """项目管理列表视图时，右侧这组不渲染。"""
        self.assertIn("tools.hidden = (view !== 'workbench');", JS)
        self.assertIn(".lh-tools[hidden]{display:none}", CSS)

    def test_single_language_hides_only_the_lang_toggle(self):
        """单语项目隐藏中/EN，其余四钮照旧（条目 24 口径）。"""
        self.assertIn("seg.hidden = !multi;", JS)
        self.assertNotIn("const head = $('#npHead');", JS)
        self.assertIn(".lang-seg[hidden]{display:none}", CSS)


class RightColumnTests(unittest.TestCase):
    """③ 右栏＝图标收起钮 ＋ 三枚切换钮 ＋ 面板。"""

    def test_toolbar_is_horizontal_at_panel_top(self):
        panel = PANEL
        self.assertIn('class="np-toolbar" id="npToolbar"', panel)
        self.assertLess(panel.index('id="npToolbar"'), panel.index('class="np-col"'))
        self.assertIn("flex-direction:row", CSS)

    def test_toolbar_has_exactly_one_icon_collapse_and_three_tabs(self):
        """最左一枚纯图标收起钮（无文字、内联 SVG）＋ 目录/智能助手/更多。"""
        self.assertIn('id="npCollapse"', TOOLBAR)
        self.assertIn('class="np-tab np-icon"', TOOLBAR)
        for button_id in ("npToc", "npAi", "npMore"):
            self.assertIn('id="%s"' % button_id, TOOLBAR)
        # 收起钮是纯图标：没有可见文字，只有内联 SVG。
        collapse = TOOLBAR[TOOLBAR.index('id="npCollapse"'):TOOLBAR.index('id="npToc"')]
        self.assertIn("<svg", collapse)
        self.assertNotIn("data-i18n=", collapse)
        self.assertEqual(_visible_text(collapse), "")

    def test_seven_old_toolbar_buttons_are_gone(self):
        """渲染PDF/全检/导出/开目录/知识库/版式/实验报告 七枚钮不再占工具条。"""
        for button_id in ("npReports", "npKb", "npVenue"):
            self.assertNotIn('id="%s"' % button_id, HTML)
        for button_id in ("actPdf", "actCheck", "actBundle", "actOpenDir"):
            self.assertNotIn('id="%s"' % button_id, PANEL)

    def test_panel_starts_at_top(self):
        self.assertIn(".navpanel{top:0;height:100vh}", CSS)

    def test_collapse_button_anchors_to_window_edge(self):
        """收起后剩下的「展开导航」钮贴窗缘（不再是左缘）。"""
        self.assertIn(".nav-open{display:none;position:fixed;right:0;top:0;", CSS)
        self.assertNotIn(".nav-open{display:none;position:fixed;left:0;", CSS)

    def test_open_button_is_icon_only(self):
        """条目 33：展开钮也改成纯图标，不再竖排文字。"""
        open_btn = _slice('<button type="button" class="nav-open"', '</button>')
        self.assertIn("<svg", open_btn)
        self.assertNotIn("data-i18n=", open_btn)
        self.assertEqual(_visible_text(open_btn), "")
        nav_open_css = CSS[CSS.index(".nav-open{"):CSS.index(".nav-open:hover")]
        self.assertNotIn("writing-mode", nav_open_css)


class MorePaneTests(unittest.TestCase):
    """条目 33：「更多」面板＝实验报告 / 知识库 / 版式 三段合并。"""

    def test_three_sections_in_order(self):
        order = [PANE_MORE.index('id="secReports"'),
                 PANE_MORE.index('id="secKb"'),
                 PANE_MORE.index('id="secVenue"')]
        self.assertEqual(order, sorted(order))

    def test_reports_section_keeps_import_and_delete_chain(self):
        self.assertIn('id="npImportBtn"', PANE_MORE)
        self.assertIn('id="npReportsList"', PANE_MORE)
        self.assertIn("$('#npImportBtn').addEventListener('click', openWizard);", JS)

    def test_reports_row_delete_goes_through_confirm(self):
        """每条报告行带删除钮，删除前走一次确认模态（条目 35）。"""
        self.assertIn("$$('#npReportsList [data-del]')", JS)
        self.assertIn("id=\"modalConfirm\"", HTML)
        self.assertIn("function askConfirm(", JS)
        self.assertIn("const ok = await askConfirm(", JS)
        self.assertIn("postJSON(path, { name: id })", JS)
        self.assertNotIn("window.confirm(t('rp.delAsk'))", JS)

    def test_knowledge_section_keeps_upload_chain(self):
        self.assertIn('id="npKbUploadBtn"', PANE_MORE)
        self.assertIn('id="npKbUpload"', PANE_MORE)
        self.assertIn('id="kbFiles"', PANE_MORE)
        self.assertIn("$('#npKbUploadBtn').addEventListener('click', () => $('#npKbUpload').click());", JS)

    def test_knowledge_preview_moved_to_modal(self):
        """条目 35：预览改模态框——侧栏里的内嵌详情框没了。"""
        self.assertNotIn('id="kbDetail"', HTML)
        self.assertNotIn(".kb-detail{display", CSS.replace(".kb-detail{display:none}", ""))
        self.assertIn('id="modalKb"', HTML)
        self.assertIn("function openKbModal(", JS)
        self.assertIn("openKbModal(data);", JS)

    def test_venue_section_keeps_save_and_preview_chain(self):
        for field_id in ("vnVenue", "vnDeadline", "vnSave", "vnPreviewBtn", "vnTemplates"):
            self.assertIn('id="%s"' % field_id, PANE_MORE)
        self.assertIn("$('#vnSave').addEventListener('click', saveVenueConfig);", JS)

    def test_switch_pane_supports_more(self):
        self.assertIn("$('#paneMore').classList.toggle('on', name === 'more');", JS)
        self.assertIn("$('#npMore').classList.toggle('on', name === 'more');", JS)
        self.assertIn("$('#npMore').addEventListener('click', () => { switchNavPane('more'); });", JS)

    def test_more_pane_loads_three_sections(self):
        """切到「更多」把三段都拉起来（报告 / 知识库 / 版式）。"""
        more = JS[JS.index("if (name === 'more') {"):]
        more = more[:more.index("}")]
        for fn in ("loadReports()", "loadKb()", "loadVenue()"):
            self.assertIn(fn, more)

    def test_deadline_badge_lands_on_more_button(self):
        """版式并进「更多」后，截稿徽标改挂在「更多」钮上。"""
        self.assertIn("const btn = $('#npMore');", JS)

    def test_toc_pane_unchanged(self):
        """目录面板保持段五现状（目录 ＋ 章节管理行内钮）。"""
        self.assertIn('id="tocList"', PANE_TOC)
        self.assertIn('class="np-pane on" id="paneToc"', HTML)


class ActiveTabStyleTests(unittest.TestCase):
    """激活态深色底（同族样式）。"""

    def test_active_tab_has_dark_background(self):
        self.assertIn(".np-tab.on{background:#2f2e2b;border-color:#2f2e2b;color:#fff}", CSS)


class ProtocolGuardTests(unittest.TestCase):
    """硬约束：AI fallback 明牌不许被本轮改动带偏。"""

    def test_ai_fallback_marker_untouched(self):
        self.assertIn("const AI_FALLBACK_MARK = '模拟回答（未接模型）';", JS)

    def test_ai_fallback_still_leads_the_reply(self):
        self.assertIn("return text.indexOf(AI_FALLBACK_MARK) === 0;", JS)


class EmbeddedAssistantPaneTests(unittest.TestCase):
    """条目 34：智能助手改嵌入式面板——浮层元素与 CSS 零残留。"""

    def test_float_layer_is_gone(self):
        """半透明浮层（#aiFloat / .ai-float）从 HTML/CSS/JS 全部消失。"""
        self.assertNotIn('id="aiFloat"', HTML)
        self.assertNotIn("aiFloat", HTML)
        self.assertNotIn(".ai-float", CSS)
        self.assertNotIn("aiFloat", JS)
        self.assertNotIn(".ai-float", JS)

    def test_no_float_only_css_left(self):
        """浮层专属样式（竖排抽屉钮/关闭钮/浮层本体）一并清掉。"""
        for dead in (".ai-fab", ".ai-close", ".np-ai-ctx", ".np-ai-note"):
            self.assertNotIn(dead, CSS)

    def test_ai_pane_embeds_the_whole_chat(self):
        """对话内容原样搬进侧栏：消息历史＋快捷问题＋纪律角标＋输入框＋发送。"""
        pane = _slice('<section class="np-pane" id="paneAi">', '<section class="np-pane" id="paneMore">')
        for piece in ('id="aiModes"', 'id="aiFab"', 'class="ai-disc"', 'id="aiCtx"',
                      'id="aiMsgs"', 'class="ai-quick"', 'id="aiText"', 'id="aiSend"'):
            self.assertIn(piece, pane)
        self.assertEqual(pane.count('class="aq"'), 3)   # 三枚快捷问题芯片

    def test_input_is_a_tall_textarea(self):
        pane = _slice('<section class="np-pane" id="paneAi">', '<section class="np-pane" id="paneMore">')
        self.assertIn('<textarea id="aiText" rows="3"', pane)

    def test_panel_is_the_same_width_as_the_others(self):
        """嵌入式面板：与目录/更多同构（同一个 .np-pane 容器）。"""
        self.assertIn('<section class="np-pane" id="paneAi">', HTML)
        self.assertIn("#paneAi.on{display:flex;flex-direction:column;height:100%;min-height:0}", CSS)
        self.assertIn(".np-ai-face{display:flex;flex-direction:column;flex:1 1 auto;min-height:0}", CSS)

    def test_no_toggle_button_left(self):
        """不再有「打开对话层」钮。"""
        self.assertNotIn('id="npAiToggle"', HTML)
        self.assertNotIn("setAiOpen", JS)
        self.assertNotIn("state.nav.aiOpen", JS)

    def test_reclicking_active_ai_tab_is_a_noop(self):
        """已激活再点「智能助手」＝无操作。"""
        self.assertIn("if (name === 'ai' && state.nav.pane === 'ai') return;", JS)

    def test_ask_ai_prefills_and_switches_to_the_pane(self):
        """「问 AI」带引用：自动切到智能助手面板并预填问题。"""
        block = JS[JS.index("function askAiAbout("):JS.index("function showParaTools(")]
        self.assertIn("switchNavPane('ai');", block)
        self.assertIn("input.value = t('ai.askPara');", block)

    def test_report_read_ask_switches_to_the_pane(self):
        """「让 AI 解读这份报告」：自动切到智能助手面板并触发。"""
        block = JS[JS.index("$('#askReportRead').addEventListener"):]
        block = block[:block.index("});")]
        self.assertIn("switchNavPane('ai');", block)
        self.assertIn("aiSend(t('ai.reportQ'), 'explain');", block)

    def test_chat_still_hits_the_real_endpoint(self):
        """对话仍走 /api/chat 真端点，fallback 明牌不变。"""
        self.assertIn("'/api/chat'", JS)
        self.assertIn("const AI_FALLBACK_MARK = '模拟回答（未接模型）';", JS)
        self.assertIn("return text.indexOf(AI_FALLBACK_MARK) === 0;", JS)


class Item35ManageTests(unittest.TestCase):
    """条目 35：知识库/实验报告管理收口 ＋ 预览/详情改模态。"""

    def test_kb_preview_modal_exists(self):
        """知识库预览＝模态框（文件名＋元信息＋内容）。"""
        self.assertIn('id="modalKb"', HTML)
        self.assertIn('id="kbModalTitle"', HTML)
        self.assertIn('id="kbModalBody"', HTML)
        self.assertIn('id="kbModalClose"', HTML)
        self.assertIn("t('kb.path')", JS)
        self.assertIn("t('kb.size')", JS)
        self.assertIn("t('kb.sha')", JS)

    def test_kb_preview_truncates_at_200_lines(self):
        """大文件截断 200 行 ＋ 提示「完整内容请打开原文件」。"""
        self.assertIn("lines.slice(0, 200)", JS)
        self.assertIn("t('kb.fullNote')", JS)

    def test_kb_modal_closes_by_esc_mask_and_button(self):
        """Esc/遮罩/关闭钮都能关。"""
        self.assertIn("const kbModal = $('#modalKb');", JS)
        self.assertIn("if (kbModal && !kbModal.hidden) kbModal.hidden = true;", JS)
        self.assertIn("if (ev.target.id === 'modalKb') $('#modalKb').hidden = true;", JS)
        self.assertIn("$('#kbModalClose').addEventListener('click'", JS)

    def test_kb_delete_only_for_knowledge_files(self):
        """删除钮只给 knowledge/ 里的文本文件；源文件/PDF 不给。"""
        self.assertIn("if (file.in_knowledge && file.status !== 'pending') {", JS)
        self.assertIn("t('kb.sourceNote')", JS)

    def test_kb_delete_goes_through_server_gate(self):
        """服务端写闸：只许删 knowledge/ 里的文件。"""
        from factscribe.workbench import knowledge as kbmod
        self.assertTrue(hasattr(kbmod, "delete_file"))
        source = (ROOT / "factscribe" / "workbench" / "knowledge.py").read_text(encoding="utf-8")
        self.assertIn("target = _safe_knowledge_file(disk, rel)", source)

    def test_report_detail_modal_has_all_fields(self):
        """报告详情模态：报告名＋状态＋来源文件/sha256＋绑定清单＋删除钮。"""
        self.assertIn('id="modalRp"', HTML)
        self.assertIn('id="rpModalDel"', HTML)
        self.assertIn("t('rp.boundList')", JS)
        self.assertIn("t('rp.claim')", JS)
        self.assertIn("t('rp.value')", JS)
        self.assertIn("data.report_sha256", JS)
        self.assertIn("reportsApiPath('/detail')", JS)

    def test_report_row_has_detail_and_delete(self):
        self.assertIn('data-detail=', JS)
        self.assertIn('data-del=', JS)
        self.assertIn("openReportDetail(", JS)

    def test_confirm_modal_is_shared(self):
        """通用确认模态：Esc/遮罩/取消＝不删。"""
        self.assertIn('id="modalConfirm"', HTML)
        self.assertIn('id="cfOk"', HTML)
        self.assertIn('id="cfCancel"', HTML)
        self.assertIn("function closeConfirm(", JS)
        self.assertIn("if (cfModal && !cfModal.hidden) closeConfirm(false);", JS)

    def test_discipline_notes_in_more_panel(self):
        """更多面板两段顶部各一行纪律提示。"""
        self.assertIn('data-i18n="more.rpNote"', HTML)
        self.assertIn('data-i18n="more.kbNote"', HTML)
        self.assertIn("'more.rpNote':", JS)
        self.assertIn("'more.kbNote':", JS)


if __name__ == "__main__":
    unittest.main()
