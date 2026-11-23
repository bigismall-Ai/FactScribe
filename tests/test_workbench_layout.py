# -*- coding: utf-8 -*-
"""tests/test_workbench_layout.py —— 条目 33（段五验收返修七）：右栏信息架构收敛。

框架三条，静态断言就够（布局的真读数靠浏览器，这里守结构不跑偏）：

1. **顶栏整条拆除**——页面里没有 ``.topbar`` 元素，也没有 ``<header>``；
   ``body`` 不留 52px 顶部留白。
2. **左栏＝顶部窄条 ＋ 其下正文**——``.left-head`` 左侧是可点的 FactScribe 字标
   与「项目管理」钮；右侧先是**常显的中/EN 界面语言开关**（``.lh-lang``，任何视图都在），
   后面才是**仅 workbench 视图渲染**的常用功能组
   （渲染PDF/全检一次/导出投稿包/打开目录）；新建钮只在项目列表页。
3. **右栏＝工具条 ＋ 面板**——工具条最左一枚**纯图标**收起钮，右侧三枚互斥切换钮
   （目录／智能助手／更多）；「更多」面板＝实验报告 / 知识库 / 版式 三段合并。
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
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
    """条目 33：常用功能组搬进左栏头部，且只在 workbench 视图渲染；
    中/EN 界面语言开关独立成组，任何视图都在。"""

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
        """项目管理列表视图时，工作台专属那组不渲染（切换钮不在其中，见上两条）。"""
        self.assertIn("tools.hidden = (view !== 'workbench');", JS)
        self.assertIn(".lh-tools[hidden]{display:none}", CSS)

    def test_lang_toggle_is_always_visible(self):
        """中/EN 切换常显——它同时是界面语言开关。

        做法：把切换钮从 #lhTools 里提出来，独立成 #lhLang。
        #lhTools 装的是工作台专属按钮（列表视图要整组藏掉），
        切换钮若还在里面，藏组＝藏切换钮，界面语言就再也切不了。
        """
        self.assertNotIn("seg.hidden", JS)
        self.assertNotIn(".lang-seg[hidden]", CSS)
        self.assertNotIn('id="langSeg" role="group" aria-label="panel language" hidden', HTML)
        self.assertIn("tools.hidden = (view !== 'workbench');", JS)

    def test_lang_toggle_lives_outside_the_hideable_tools_group(self):
        """结构钉：#langSeg 在 #lhTools 之前，且不属于它。"""
        self.assertIn('class="lh-lang" id="lhLang"', LEFT_HEAD)
        self.assertLess(LEFT_HEAD.index('id="langSeg"'), LEFT_HEAD.index('id="lhTools"'))
        tools_group = LEFT_HEAD[LEFT_HEAD.index('id="lhTools"'):]
        self.assertNotIn('id="langSeg"', tools_group)
        self.assertNotIn('id="lhLang"', tools_group)

    def test_lang_toggle_is_never_hidden_by_script(self):
        """脚本不许藏切换钮（或它的容器）：界面语言开关任何时候都在。"""
        self.assertNotIn("langSeg').hidden", JS)
        self.assertNotIn("lhLang').hidden", JS)
        for line in JS.splitlines():
            if "langSeg" in line or "lhLang" in line:
                self.assertNotIn(".hidden", line)
        self.assertIn(".lh-lang{", CSS)


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
        self.assertIn(".nav-open{display:none;position:fixed;right:0;top:50%;", CSS)
        self.assertNotIn(".nav-open{display:none;position:fixed;left:0;", CSS)

    def test_open_button_is_a_vertical_label(self):
        """条目 39：展开钮＝贴右缘中部的竖排文字标签（30×90），不是小图标。"""
        open_btn = _slice('<button type="button" class="nav-open"', '</button>')
        self.assertIn('data-i18n="nav.open"', open_btn)
        self.assertNotIn("<svg", open_btn)
        self.assertIn("展开导航", _visible_text(open_btn))
        nav_open_css = CSS[CSS.index(".nav-open{"):CSS.index(".nav-open:hover")]
        self.assertIn("writing-mode:vertical-rl", nav_open_css)
        self.assertIn("width:30px;height:90px", nav_open_css)
        self.assertIn("transform:translateY(-50%)", nav_open_css)

    def test_old_side_alone_scheme_is_gone(self):
        """旧 .nav-open/.side-alone 小图标方案废弃。"""
        self.assertNotIn(".side-alone{", CSS)
        self.assertNotIn('class="side-alone"', HTML)


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

    def test_venue_section_keeps_save_chain(self):
        """条目 39：版式面保留字段/截止/选刊指南，删掉「渲染并预览首页」。"""
        for field_id in ("vnVenue", "vnDeadline", "vnSave", "vnTemplates", "npVenueGuideBtn"):
            self.assertIn('id="%s"' % field_id, PANE_MORE)
        self.assertIn("$('#vnSave').addEventListener('click', saveVenueConfig);", JS)
        self.assertNotIn('id="vnPreviewBtn"', HTML)
        self.assertNotIn("renderVenuePreview", JS)

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


class Item36InPlaceUpdateTests(unittest.TestCase):
    """条目 36：废模式切换——保存原地更新 ＋ 顶导航固定/进度条嵌入。"""

    def test_edit_endpoint_returns_block_html(self):
        """① 后端 /edit 应答带该块新渲染的 html。"""
        source = (ROOT / "factscribe" / "workbench" / "server.py").read_text(encoding="utf-8")
        self.assertIn("def _rerender_block(", source)
        self.assertIn('result["html"] = self._rerender_block(disk, rel, block_id)', source)
        self.assertIn('result["html"] = self._rerender_block(disk, "", block_id)', source)

    def test_draft_endpoints_return_affected_html(self):
        """④ AI 草稿 insert/delete 也回传受影响块的 html。"""
        source = (ROOT / "factscribe" / "workbench" / "server.py").read_text(encoding="utf-8")
        self.assertIn('result["html"] = self._rerender_block(disk, rel, affected)', source)
        self.assertIn('result["affected"] = affected', source)

    def test_save_edit_updates_in_place(self):
        """② 保存只原地换块，不整篇 loadDisk（条目 43 起新链路 saveBlockNode）。"""
        save = JS[JS.index("async function saveBlockNode("):JS.index("/* 条目 43：BLOCK_STALE")]
        self.assertIn("applyBlockHtml(blockId,", save)
        self.assertNotIn("loadDisk()", save)

    def test_no_cancel_edit_concept(self):
        """③ 条目 43：没有「取消编辑」——Esc＝主动失焦走保存，克隆还原机已拆。"""
        self.assertNotIn("function cancelEdit(", JS)
        self.assertNotIn("restoreEditedNode", JS)
        esc_block = JS[JS.index("// 条目 43：Esc＝主动失焦"):]
        esc_block = esc_block[:esc_block.index("});")]
        self.assertIn("active.blur()", esc_block)

    def test_focused_sibling_is_skipped_and_marked_stale(self):
        """条目 43：保存成功刷新兄弟块时，正被聚焦的块跳过并记 stale。"""
        save = JS[JS.index("async function saveBlockNode("):JS.index("/* 条目 43：BLOCK_STALE")]
        self.assertIn("live.dataset.stale = '1';", save)
        self.assertIn("live.contains(active)", save)

    def test_draft_insert_delete_in_place(self):
        self.assertIn("insertBlockAfter(data.after, data.block, data.html, quote.file)", JS)
        self.assertIn("removeBlockNode(data.block || blockId)", JS)

    def test_loaddisk_only_three_triggers(self):
        """⑤ loadDisk 只保留三种触发：初次载入、换盘、切语言。"""
        calls = []
        for line in JS.splitlines():
            if "loadDisk()" in line and "function loadDisk" not in line:
                calls.append(line.strip())
        self.assertLessEqual(len(calls), 6)   # openProject/换盘/切语言 ＋ 兜底分支

    def test_left_head_is_fixed(self):
        """B① 左栏头部固定在顶。"""
        self.assertIn(".left-head{position:fixed;top:0;left:0;right:var(--side-w", CSS)

    def test_progress_bar_moved_into_header(self):
        """B② 进度条从正文流挪出，贴头部下缘。"""
        self.assertIn('id="progWrap"', HTML)
        self.assertNotIn('<div class="progwrap"><div id="prog"></div></div>', HTML)
        self.assertIn(".progwrap{position:fixed;top:48px;left:0;right:var(--side-w", CSS)

    def test_content_makes_room_for_header_and_bar(self):
        """B③ 正文让出「头部高＋进度条高」。"""
        self.assertIn(".left-col{padding-top:51px}", CSS)


class Item37RegressionTests(unittest.TestCase):
    """条目 43（取代条目 37 的旧口径）四案：渲染即可编辑／写回寻址同源／
    失焦自动保存／ZZEDIT 全文往返（新链路：散文＋token 走 /edit）。"""

    def test_1_rendered_as_editable_no_clone_switch(self):
        """案一：渲染即 contenteditable——没有「单击进入编辑」的克隆替换，
        enterEdit/克隆机整体不存在。"""
        self.assertIn("function collectPlain(", JS)
        for dead in ("function enterEdit(", "function buildEditor(",
                     "function buildPlainEditor(", "function upgradeEditor(",
                     "function fetchBlockModel(", "function tokenizePlain(",
                     "function placeCaretAtEnd(", "function liveEditorNode(",
                     "function restoreEditedNode("):
            self.assertNotIn(dead, JS)
        self.assertNotIn("replaceWith(editor)", JS)
        self.assertNotIn("state.blockModels", JS)
        self.assertNotIn("state.editing", JS)
        # 渲染循环：段落生来可编辑，不再挂 click→替换
        blocks_fn = JS[JS.index("function renderBlocks()"):JS.index("/* 段五：目录住进导航面板")]
        self.assertIn("node.setAttribute('contenteditable', 'true');", blocks_fn)
        self.assertIn("node.setAttribute('spellcheck', 'false');", blocks_fn)
        self.assertNotIn("enterEdit(", blocks_fn)

    def test_2_save_carries_dom_identity(self):
        """案二：保存携带的 (file, block-id) 从**可编辑块自身的 DOM**读回，
        与渲染闭包同源（渲染时写进 data-*）。"""
        save = JS[JS.index("async function saveBlockNode("):JS.index("/* 条目 43：BLOCK_STALE")]
        self.assertIn("node.dataset.blockId", save)
        self.assertIn("node.dataset.file", save)
        blocks_fn = JS[JS.index("function renderBlocks()"):JS.index("/* 段五：目录住进导航面板")]
        self.assertIn("node.dataset.blockId = block.id;", blocks_fn)
        self.assertIn("node.dataset.file = block.file || '';", blocks_fn)
        self.assertNotIn("file: file || model.file", JS)

    def test_3_focusout_auto_saves(self):
        """案三：失焦自动保存（容器级委托＋120ms 守卫）＋ 可见的「已保存」反馈；
        Esc＝主动失焦走保存。"""
        self.assertIn("document.addEventListener('focusout'", JS)
        delegate = JS[JS.index("document.addEventListener('focusout'"):]
        delegate = delegate[:delegate.index("});")]
        self.assertIn("closest('[data-block-id]')", delegate)
        self.assertIn("setTimeout(", delegate)
        self.assertIn("node.contains(active)", delegate)
        self.assertIn("saveBlockNode(node);", delegate)
        self.assertIn("function showSavedBadge(", JS)
        self.assertIn("setTimeout(() => { if (badge.parentNode) badge.remove(); }, 1500);", JS)
        self.assertIn("'edit.savedBadge': '已保存',", JS)
        self.assertIn("'edit.savedBadge': 'Saved',", JS)

    def test_4_zzedit_round_trip_restores_bytes(self):
        """案四：ZZEDIT 全文往返（写入→读回→删除→字节还原），跑在真项目样例上，
        走**新链路**：collect 等价于「散文＋token」，带 expect_sha 调 /edit。"""
        import shutil
        import tempfile
        import threading
        import urllib.error
        import urllib.request

        from factscribe.workbench.projects import render_tex
        from factscribe.workbench.server import create_server
        from factscribe.workbench.write import TOKEN_RE, editable_model, find_block

        src = ROOT / "examples" / "minimal"
        self.assertTrue(src.is_dir(), "真项目样例不在：examples/minimal")
        with tempfile.TemporaryDirectory() as tmp:
            disk = Path(tmp) / "paper"
            shutil.copytree(src, disk)
            rel = "sections/03-zzedit.tex"
            target = disk / rel
            target.write_text("\\section{Round Trip Probe}\n\nZZPLAIN body text here.\n",
                              encoding="utf-8")
            original = target.read_bytes()
            blocks = [b for b in render_tex(target.read_text(encoding="utf-8"),
                                            stem="03-zzedit") if b["kind"] == "para"]
            self.assertTrue(blocks, "样例段落没渲染出来")
            block = blocks[0]
            real = find_block(disk, rel, block["id"])
            model = editable_model(disk, real)
            body = TOKEN_RE.split(model["plain"])[0].strip()   # collect 的散文等价

            server, _index = create_server(tmp, port=0, ttl=0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.shutdown)

            def post(payload):
                request = urllib.request.Request(
                    "http://127.0.0.1:%d/api/disk/paper/paper/edit" % server.server_address[1],
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST")
                try:
                    with urllib.request.urlopen(request, timeout=10) as resp:
                        return resp.status, json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    return exc.code, json.loads(exc.read().decode("utf-8"))

            # ① 写入：ZZEDIT 带指纹闸真进文件（服务端应答 blocks 刷新映射）
            status, result = post({"file": rel, "block": block["id"],
                                   "text": body + " ZZEDIT",
                                   "expect_sha": model["sha"]})
            self.assertEqual(status, 200, "写入被拒：%s" % result)
            self.assertTrue(result.get("ok"), "写入失败：%s" % result)
            self.assertIn("ZZEDIT", target.read_text(encoding="utf-8"), "编辑没写进文件")
            self.assertIn(block["id"], result.get("blocks", {}), "应答没带同文件块映射")

            # ② 读回：重新渲染这一块，能看到 ZZEDIT
            blocks2 = render_tex(target.read_text(encoding="utf-8"), stem="03-zzedit")
            self.assertTrue(any("ZZEDIT" in b["raw"] for b in blocks2), "读回看不到 ZZEDIT")

            # ③ 删除 ④ 字节还原：写回原文，文件回到逐字节相同
            fresh = editable_model(disk, find_block(disk, rel, block["id"]))
            status, result = post({"file": rel, "block": block["id"],
                                   "text": body, "expect_sha": fresh["sha"]})
            self.assertEqual(status, 200)
            self.assertNotIn("ZZEDIT", target.read_text(encoding="utf-8"))
            self.assertEqual(target.read_bytes(), original, "删掉 ZZEDIT 后字节没还原")


class Item38RegressionTests(unittest.TestCase):
    """条目 43（取代条目 38 的旧口径）：收集宿主＝可编辑块本身（生来挂载）；
    ZZEDIT 真落文件、再删真还原——跑在**真项目副本**上，断言服务器文件内容。"""

    def _project_copy(self, tmp: str) -> Path:
        import shutil

        src = ROOT / "examples" / "minimal"
        self.assertTrue(src.is_dir(), "真项目样例不在：examples/minimal")
        disk = Path(tmp) / "paper"
        shutil.copytree(src, disk)
        return disk

    def _probe_section(self, disk: Path):
        """造一节纯文本段落当受试块，返回 (rel, 目标文件, 块, 可编辑模型)。"""
        from factscribe.workbench.projects import render_tex
        from factscribe.workbench.write import editable_model, find_block

        rel = "sections/03-zzedit.tex"
        target = disk / rel
        target.write_text("\\section{Round Trip Probe}\n\nZZPLAIN body text here.\n",
                          encoding="utf-8")
        text = target.read_text(encoding="utf-8")
        blocks = [b for b in render_tex(text, stem="03-zzedit") if b["kind"] == "para"]
        self.assertTrue(blocks, "受试段落没渲染出来")
        block = blocks[0]
        real = find_block(disk, rel, block["id"])
        return rel, target, block, editable_model(disk, real)

    def test_1_collect_reads_the_block_node_itself(self):
        """案一（JS 侧）：收集直接走「生来挂载」的可编辑块——没有克隆机，
        也就没有「已出 DOM 的旧引用」问题；失焦委托把节点交给保存。"""
        self.assertIn("function collectPlain(", JS)
        save = JS[JS.index("async function saveBlockNode("):JS.index("/* 条目 43：BLOCK_STALE")]
        self.assertIn("collectPlain(node)", save)
        delegate = JS[JS.index("document.addEventListener('focusout'"):]
        delegate = delegate[:delegate.index("});")]
        self.assertIn("saveBlockNode(node);", delegate)

    def test_2_typed_text_reaches_the_server_file(self):
        """案二（文件侧）：「散文＋token」客户端文本（含 expect_sha 指纹）
        真落进服务器文件。"""
        from factscribe.workbench.write import save_block

        with tempfile.TemporaryDirectory() as tmp:
            disk = self._project_copy(tmp)
            rel, target, block, model = self._probe_section(disk)
            typed = model["plain"] + " ZZEDIT"     # collectPlain 出来的那串
            result = save_block(disk, rel, block["id"], typed,
                                expect_sha=model["sha"])
            self.assertTrue(result.get("ok"), "写入失败：%s" % result)
            self.assertIn("ZZEDIT", target.read_text(encoding="utf-8"),
                          "用户敲的字没落到服务器文件里")
            self.assertTrue(result.get("sha"), "应答没带新块指纹")

    def test_3_second_edit_removes_zzedit_and_restores(self):
        """案三：二次编辑删掉 ZZEDIT → 文件还原（逐字节相同）。"""
        from factscribe.workbench.write import editable_model, find_block, save_block

        with tempfile.TemporaryDirectory() as tmp:
            disk = self._project_copy(tmp)
            rel, target, block, model = self._probe_section(disk)
            original = target.read_bytes()
            without = model["plain"]               # 用户删掉了 ZZEDIT 的那版文本
            save_block(disk, rel, block["id"], without + " ZZEDIT",
                       expect_sha=model["sha"])
            self.assertIn("ZZEDIT", target.read_text(encoding="utf-8"))
            fresh = editable_model(disk, find_block(disk, rel, block["id"]))
            save_block(disk, rel, block["id"], without,
                       expect_sha=fresh["sha"])    # 二次编辑：删掉 ZZEDIT
            self.assertNotIn("ZZEDIT", target.read_text(encoding="utf-8"))
            self.assertEqual(target.read_bytes(), original, "删掉 ZZEDIT 后文件没还原")


class Item40HeaderWidthTests(unittest.TestCase):
    """条目 40 三案：头部右缘不压侧栏 / 侧栏工具条首钮可点 / 收起标签 z 序更高。"""

    def _z_of(self, selector: str) -> int:
        import re

        match = re.search(re.escape(selector) + r"\{[^}]*?z-index:(\d+)", CSS)
        self.assertTrue(match, "没找到 %s 的 z-index" % selector)
        return int(match.group(1))

    def test_1_header_right_follows_the_left_column(self):
        """案一：固定头部宽度＝左区宽——右缘由 --side-w（DOM 实测）驱动，
        不是写死的 336，更不是横贯全窗的 0。"""
        self.assertIn(".left-head{position:fixed;top:0;left:0;right:var(--side-w", CSS)
        self.assertNotIn(".left-head{position:fixed;top:0;left:0;right:0;", CSS)
        self.assertIn("function syncFixedHeaderWidth(", JS)
        self.assertIn("'--side-w'", JS)
        self.assertIn("window.innerWidth - rect.right", JS)
        self.assertIn("scheduleHeaderWidthSync();", JS)
        self.assertIn("window.addEventListener('resize', scheduleHeaderWidthSync);", JS)

    def test_2_header_stops_before_the_sidebar(self):
        """案二：侧栏本体钉在视口右缘，头部止于左区右缘 → 不叠盖侧栏，
        工具条首钮（最左）不会被头部压住。"""
        self.assertIn(".navpanel{position:fixed;right:0;", CSS)
        self.assertIn("right:var(--side-w,336px)", CSS)
        # 侧栏在文档流里由 .shell 的 padding-right 让位，头部宽度与之同源。
        # 让位宽度改由 --nav-w 驱动（右栏可拖分隔条）：拖到多宽，正文就让出多宽，
        # 头部仍止于左区右缘——不叠盖侧栏。
        self.assertIn(":root{--nav-w:320px}", CSS)
        self.assertIn(
            ".shell{padding-right:calc(var(--nav-w,320px) + 16px);transition:padding-right .22s ease}",
            CSS)

    def test_3_expand_label_is_above_the_header(self):
        """案三：收起态的展开标签 z 序高于固定头部（恒可点，不被压在其下）。"""
        self.assertIn("z-index:85;", CSS)
        self.assertGreater(self._z_of(".nav-open"), self._z_of(".left-head"))
        self.assertGreater(self._z_of(".nav-open"), self._z_of(".progwrap"))


class PaneHeaderContrastTests(unittest.TestCase):
    """段五返修十三（小修）：面板节标题/段头对比度修复。

    起因：``.np-pane-h`` 用的是 #a3a29c（rgb(163,162,156)），压在面板底 #fafaf9 上
    对比度只有约 1.8:1（低于 4.5:1 可读标准）——用户报的「英文页目录字体颜色不对」
    就是这一处。口径：

    1. ``.np-pane-h`` 色值 = #5f5e5b（rgb(95,94,91)），字号落在 11–12px；
    2. 三个面板（目录 / 智能助手 / 更多）的节标题、段头同族浅色一并加深
       （标题级 #5f5e5b，次级小字 #6f6e69）；
    3. 色值不随语言——CSS 里没有任何按语言覆盖的规则；
    4. AI 层 ``.who`` 是装饰性发送者标，保持原样。
    """

    PANEL_BG = "#fafaf9"
    HEADINGS = (".np-pane-h", ".vn-sec-h", ".kbd-title", ".vn-l",
                ".rp-b-table th", ".toc-item.sub a")
    SECONDARY = (".np-note", ".np-rp-meta", ".kbf-meta", ".kb-empty",
                 ".kbd-kv span:first-child", ".vn-tpl-note", ".toc-empty")

    @staticmethod
    def _all_rules(css):
        rules = []
        for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            rules.append((match.group(1).strip(), match.group(2)))
        return rules

    @classmethod
    def _rules_for(cls, selector):
        hits = []
        for sel, body in cls._all_rules(CSS):
            if any(one.strip().endswith(selector) for one in sel.split(",")):
                hits.append(body)
        assert hits, "CSS rule not found: " + selector
        return hits

    @classmethod
    def _rule(cls, selector):
        return cls._rules_for(selector)[0]

    @classmethod
    def _color(cls, selector):
        for body in cls._rules_for(selector):
            match = re.search(r"color:(#[0-9a-fA-F]{3,6})", body)
            if match:
                return match.group(1).lower()
        raise AssertionError("no color in: " + selector)

    @staticmethod
    def _lum(hexstr):
        h = hexstr.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        chans = []
        for i in (0, 2, 4):
            v = int(h[i:i + 2], 16) / 255.0
            chans.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]

    @classmethod
    def _contrast(cls, a, b):
        la, lb = cls._lum(a), cls._lum(b)
        hi, lo = max(la, lb), min(la, lb)
        return (hi + 0.05) / (lo + 0.05)

    def test_1_pane_header_color_and_size(self):
        """案一：``.np-pane-h`` = #5f5e5b（rgb(95,94,91)），字号 11–12px，
        压在面板底 #fafaf9 上对比度 ≥4.5:1。"""
        rule = self._rule(".np-pane-h")
        self.assertIn("color:#5f5e5b", rule)
        size = float(re.search(r"font-size:([0-9.]+)px", rule).group(1))
        self.assertGreaterEqual(size, 11.0)
        self.assertLessEqual(size, 12.0)
        self.assertGreaterEqual(self._contrast("#5f5e5b", self.PANEL_BG), 4.5)
        self.assertGreaterEqual(self._contrast("#5f5e5b", "#ffffff"), 4.5)

    def test_2_panel_headings_are_deepened(self):
        """案二：三面板的节标题/段头不再残留同族浅色，且各自对比度 ≥4.5:1。"""
        stale = ("#a3a29c", "#9b9a96", "#8f8d86", "#a49e8d")
        for selector in self.HEADINGS:
            rule = self._rule(selector)
            for bad in stale:
                self.assertNotIn(bad, rule, f"{selector} 仍是浅色 {bad}")
            color = self._color(selector)
            self.assertGreaterEqual(self._contrast(color, self.PANEL_BG), 4.5, selector)
            self.assertGreaterEqual(self._contrast(color, "#ffffff"), 4.5, selector)

    def test_3_panel_secondary_text_is_readable(self):
        """案三：面板里的次级小字（提示/空态/元信息）一并离开 1.8:1 那一档。"""
        for selector in self.SECONDARY:
            rule = self._rule(selector)
            for bad in ("#a3a29c", "#9b9a96"):
                self.assertNotIn(bad, rule, f"{selector} 仍是浅色 {bad}")
            color = self._color(selector)
            self.assertGreaterEqual(self._contrast(color, self.PANEL_BG), 4.5, selector)
            self.assertGreaterEqual(self._contrast(color, "#ffffff"), 4.5, selector)

    def test_4_color_does_not_depend_on_language(self):
        """案四：色值不随语言——CSS 里没有按语言覆盖的规则，三个面板共用同一条。"""
        self.assertIsNone(re.search(r"\[lang[=\]]", CSS))
        for selector in self.HEADINGS:
            for body in self._rules_for(selector):
                for bad in ("#a3a29c", "#9b9a96", "#8f8d86", "#a49e8d"):
                    self.assertNotIn(bad, body, selector + " still pale: " + bad)
        # 三个面板（目录 / 智能助手 / 更多）都挂着 .np-pane-h：
        # 目录 ＋ 智能助手 ＋（更多里的）实验报告 / 知识库 / 事实账 / 版式。
        # 新增段也必须挂同一条类——色值由上面那条规则统一守住，不另开样式。
        self.assertEqual(HTML.count('class="np-pane-h'), 6)

    def test_5_decorative_who_is_untouched(self):
        """案五：AI 层 ``.who`` 发送者标是装饰，保持原浅色。"""
        self.assertIn("#a49e8d", self._rule(".msg .who"))


class Item41LangToggleAlwaysVisibleTests(unittest.TestCase):
    """条目 41（返修十五）：中/EN 切换常显——它同时是界面语言开关。

    用户裁定：单语言项目藏掉它之后界面语言就没法切了，所以不许再隐藏。
    """

    def test_apply_lang_toggle_never_hides(self):
        self.assertIn("function applyLangToggle()", JS)
        self.assertNotIn("seg.hidden", JS)
        self.assertNotIn("multi_lang", JS)

    def test_seg_starts_visible_and_css_hide_rule_is_gone(self):
        self.assertIn('<div class="lang-seg" id="langSeg" role="group" aria-label="panel language">', HTML)
        self.assertNotIn(".lang-seg[hidden]", CSS)

    def test_lang_click_switches_ui_language_first(self):
        """界面语言永远切；workbench 下有对应盘才切盘，没有就留在当前盘。"""
        block = JS[JS.index("$('#langSeg').addEventListener('click'"):]
        block = block[:block.index("});")]
        self.assertIn("state.lang = lang;", block)
        self.assertIn("applyI18n();", block)
        self.assertNotIn("toast(t('lang.none'))", block)
        self.assertIn("if (disk) openProject(state.project.id, disk.id);", block)


class Item42AiPanelTests(unittest.TestCase):
    """条目 42：发送钮内嵌输入框 ＋ 模型选择（前后端联动）。"""

    def test_send_button_embedded_in_a_relative_box(self):
        """textarea＋发送钮被 .ai-box（position:relative）包住；按钮绝对定位右下角。"""
        pane = _slice('<section class="np-pane" id="paneAi">', '<section class="np-pane" id="paneMore">')
        start = pane.index('<div class="ai-box">')
        box = pane[start:pane.index('id="aiSend"', start)]
        self.assertIn('<textarea id="aiText" rows="3"', box)
        self.assertIn('id="aiSend"', pane)
        self.assertIn(".np-ai-face .ai-box{position:relative", CSS)
        button_css = CSS[CSS.index(".np-ai-face .ai-input button{"):]
        button_css = button_css[:button_css.index("}")]
        self.assertIn("position:absolute", button_css)
        self.assertIn("bottom:6px", button_css)
        # textarea 底部留出按钮高度的空间不压字。
        textarea_css = CSS[CSS.index(".np-ai-face .ai-input textarea{"):]
        textarea_css = textarea_css[:textarea_css.index("}")]
        self.assertIn("padding:7px 9px 36px", textarea_css)

    def test_model_row_sits_above_the_input(self):
        """输入框上方一行紧凑模型选择行（label＋select，label 走 i18n）。"""
        pane = _slice('<section class="np-pane" id="paneAi">', '<section class="np-pane" id="paneMore">')
        self.assertLess(pane.index('class="ai-modelrow"'), pane.index('<div class="ai-box">'))
        self.assertIn('data-i18n="ai.model"', pane)
        self.assertIn('id="aiModel"', pane)
        self.assertIn(".np-ai-face .ai-modelrow{", CSS)

    def test_model_state_fetch_and_payload(self):
        """state.ai 带 model/models；智能助手面打开拉一次清单；payload 带选中模型。"""
        self.assertIn("model: '', models: [], modelsKey: ''", JS)
        face = JS[JS.index("function renderAiFace()"):]
        face = face[:face.index("function renderAiModelSelect()")]
        self.assertIn("refreshAiModels();", face)
        body = JS[JS.index("async function refreshAiModels("):]
        body = body[:body.index("function renderAiModelSelect()")]
        self.assertIn("'/api/ai/models?project='", body)
        self.assertIn("state.ai.modelsKey === key", body)
        send = JS[JS.index("async function aiSend("):JS.index("/* 段六：复制回复")]
        # v4：清单条目带来源与思考等级，发送时带 modelSelection；
        # 引擎本地后端那条老路仍走 model 字段（那边认的是模型名）。
        self.assertIn("payload.modelSelection = { id: entry.id, effort: state.ai.effort || '' }", send)
        self.assertIn("payload.model = entry.model;", send)
        self.assertIn("$('#aiModel').addEventListener('change'", JS)

    def test_backend_model_override_and_models_route_exist(self):
        """后端：chat 认 model 覆盖；available_models 在；服务器路由挂上。"""
        source = (ROOT / "factscribe" / "workbench" / "ai.py").read_text(encoding="utf-8")
        self.assertIn("def available_models(disk_path", source)
        self.assertIn('chosen = str(model or "").strip()', source)
        server = (ROOT / "factscribe" / "workbench" / "server.py").read_text(encoding="utf-8")
        self.assertIn('route == "/api/ai/models"', server)
        self.assertIn("def _ai_models_get(self, query", server)
        self.assertIn("model=model or None", server)


class Item43EditableAlwaysTests(unittest.TestCase):
    """条目 43（用户裁定：正文永远直接可编辑）——前端新口径的静态断言。

    页面本身就是编辑器：渲染即 contenteditable，没有「渲染态↔编辑态」两个
    状态；保护面芯片由服务端烤进 html（data-token），保存走失焦委托链。
    """

    def test_paragraphs_are_born_editable(self):
        """正文段落与 AI 草稿块渲染时就挂 contenteditable＋spellcheck。"""
        blocks_fn = JS[JS.index("function renderBlocks()"):JS.index("/* 段五：目录住进导航面板")]
        self.assertIn("node.setAttribute('contenteditable', 'true');", blocks_fn)
        self.assertIn("body.setAttribute('contenteditable', 'true');", blocks_fn)
        abstract_fn = JS[JS.index("function renderAbstract()"):JS.index("/* ---------------------------------------------------------------- 证据卡")]
        self.assertIn("body.setAttribute('contenteditable', 'true');", abstract_fn)

    def test_save_chain_is_focusout_delegation(self):
        """保存链：容器级 focusout 委托 → 120ms 守卫 → saveBlockNode，
        带 expect_sha；BLOCK_STALE 走原地重载并 toast 说清。"""
        self.assertIn("async function saveBlockNode(", JS)
        save = JS[JS.index("async function saveBlockNode("):JS.index("/* 条目 43：BLOCK_STALE")]
        self.assertIn("expect_sha", save)
        self.assertIn("res.status === 409", save)
        self.assertIn("t('edit.stale')", save)
        self.assertIn("await reloadBlocks();", save)
        reload_fn = JS[JS.index("async function reloadBlocks()"):JS.index("/* 条目 43：段落菜单")]
        self.assertIn("state.blockSha[block.id] = block.sha;", reload_fn)
        self.assertIn("await loadAbstract();", reload_fn)

    def test_success_refreshes_same_file_blocks(self):
        """保存成功：用应答 blocks 刷新同文件其他块（innerHTML 原地换，
        保持可编辑外壳），聚焦中的块跳过记 stale。"""
        save = JS[JS.index("async function saveBlockNode("):JS.index("/* 条目 43：BLOCK_STALE")]
        self.assertIn("const blocks = data.blocks || {};", save)
        self.assertIn("applyBlockHtml(id, blocks[id]);", save)
        self.assertIn("live.dataset.stale = '1';", save)
        apply_fn = JS[JS.index("function applyBlockHtml("):JS.index("/* 条目 43：保存一个块")]
        self.assertIn("host.setAttribute('contenteditable', 'true');", apply_fn)
        self.assertIn("host.setAttribute('spellcheck', 'false');", apply_fn)

    def test_dead_click_to_edit_ui_is_gone(self):
        """「点段落进入编辑」的口子全拆：抽象芯片拼装、ai_draft 的 click 入场。"""
        self.assertNotIn("abstractChipHtml", JS)
        blocks_fn = JS[JS.index("function renderBlocks()"):JS.index("/* 段五：目录住进导航面板")]
        self.assertNotIn("wrap.addEventListener('click'", blocks_fn)
        self.assertNotIn("body.onclick", JS)

    def test_para_menu_edit_means_focus(self):
        """段落工具条菜单的「编辑」＝聚焦该块（focusBlockNode），不再进编辑态。"""
        self.assertIn("function focusBlockNode(", JS)
        self.assertIn("focusBlockNode(target.id);", JS)

    def test_server_bakes_tokens_into_rendered_html(self):
        """服务端：渲染 html 直接带保护面芯片（fc/prot-chip＋data-token＋不可编辑）。"""
        from factscribe.workbench.projects import render_tex

        blocks = render_tex("Rate 10/16\\fact{A1}，见 \\cite{k1} 与 \\ref{s2}。\n")
        para = next(b for b in blocks if b["kind"] == "para")
        self.assertIn('class="fc prot-chip"', para["html"])
        self.assertIn('data-fact="A1"', para["html"])
        self.assertIn("data-token=", para["html"])
        self.assertIn('contenteditable="false"', para["html"])
        self.assertIn("✓ A1", para["html"])
        self.assertIn("[k1]", para["html"])
        self.assertIn("[s2]", para["html"])

    def test_model_endpoint_carries_html_and_sha(self):
        """/block/<id> 模型应答带 html（带 token 渲染）与 sha。"""
        from factscribe.workbench.write import Block, editable_model

        block = Block(file="sections/01.tex", block_id="x-p1", kind="para",
                      start=0, end=20, raw="数字 16\\fact{A1} 在此。")
        model = editable_model(Path("."), block)   # 无盘上下文：数字绑定段不编
        self.assertIn("html", model)
        self.assertIn("sha", model)
        self.assertIn("data-token=", model["html"])

    def test_editing_css_is_dismantled(self):
        """CSS：.editing 模式妆容拆除，聚焦圈替代；死掉的保存/取消钮妆容清掉。"""
        self.assertNotIn(".editing", CSS)
        self.assertNotIn("p[data-pid]", CSS)
        self.assertNotIn(".pt.save", CSS)
        self.assertNotIn(".pt.cancel", CSS)
        self.assertIn(".editable-para:focus{outline:2px solid #dcdcd6;outline-offset:3px}", CSS)


class Item44TocSlotTests(unittest.TestCase):
    """条目 44：界面英文态目录条目灭字修复——条目槽永不空。

    病根：CSS 按 body.panel-en 把 .cn 槽藏掉，而 JS 从不出 .en 槽 → EN 态条目
    空无一字。修法：JS 按语言与数据择一（有英文标题走 .en，否则 .cn），
    CSS 两槽常显；只切界面语言时目录槽跟着刷。
    """

    def test_css_no_longer_hides_slots_by_body_class(self):
        self.assertNotIn("body.panel-en #tocList .cn{display:none}", CSS)
        self.assertNotIn("body:not(.panel-en) #tocList .en{display:none}", CSS)
        self.assertIn("#tocList .cn,#tocList .en{display:block}", CSS)

    def test_toc_entries_pick_one_nonempty_slot(self):
        """renderTocList 按 title_en 与界面语言择槽：EN 态英文标题走 .en，
        其余走 .cn（EN 盘标题本就是英文，.cn 槽照常显示）。"""
        toc_fn = JS[JS.index("function renderTocList()"):JS.index("function renderCover()")]
        self.assertIn("const enTitle = block.title_en || '';", toc_fn)
        self.assertIn("(state.lang === 'en' && enTitle)", toc_fn)
        self.assertIn("'<span class=\"en\">' + esc(enTitle) + '</span>'", toc_fn)
        self.assertIn("'<span class=\"cn\">' + esc(block.title || block.file || '') + '</span>'", toc_fn)

    def test_lang_only_switch_refreshes_toc_slots(self):
        """workbench 下无对应盘、只切界面语言的分支，applyI18n 之后刷 renderTocList。"""
        seg = JS[JS.index("$('#langSeg').addEventListener('click'"):]
        seg = seg[:seg.index("});")]
        self.assertIn("applyI18n();", seg)
        self.assertIn("else renderTocList();", seg)


if __name__ == "__main__":
    unittest.main()
