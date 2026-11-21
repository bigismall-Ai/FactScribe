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
        """② 保存只换那一块的 DOM，不整篇 loadDisk。"""
        save = JS[JS.index("async function saveEdit()"):JS.index("async function cancelEdit()")]
        self.assertIn("replaceBlockNode(blockId, result.html)", save)
        self.assertNotIn("loadDisk()", save)

    def test_cancel_edit_is_local_only(self):
        """③ 取消编辑：零网络请求，本地还原原文。"""
        cancel = JS[JS.index("async function cancelEdit()"):]
        cancel = cancel[:cancel.index("}")]
        self.assertIn("restoreEditedNode(editing)", cancel)
        self.assertNotIn("loadDisk()", cancel)
        self.assertNotIn("fetch(", cancel)
        self.assertNotIn("postJSON(", cancel)

    def test_original_text_copy_is_kept(self):
        """前端保存进入编辑时的原文副本。"""
        self.assertIn("orig: target", JS)
        self.assertIn("function restoreEditedNode(", JS)
        self.assertIn("host.replaceWith(editing.orig);", JS)

    def test_draft_insert_delete_in_place(self):
        self.assertIn("insertBlockAfter(data.after, data.block, data.html)", JS)
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
    """条目 37 四案：单击进编辑／写回寻址同源／blur 自动保存／ZZEDIT 全文往返。"""

    def _enter_edit_body(self) -> str:
        body = JS[JS.index("function enterEdit("):]
        return body[:body.index("\n}\n")]

    def test_1_single_click_enters_edit_synchronously(self):
        """案一：单击即进入编辑——编辑器同步挂载，不等模型（老实现的 await 缺口
        会让「单击＋输入」落空，也会让两次点击互相串台）。"""
        body = self._enter_edit_body()
        self.assertIn("function enterEdit(", JS)
        self.assertNotIn("async function enterEdit(", JS)
        self.assertNotIn("await ", body)
        mount = body.index("target.replaceWith(editor);")
        fetch = body.index("fetchBlockModel(")
        self.assertLess(mount, fetch, "编辑器必须先同步挂载，再去后台取模型")
        self.assertIn("buildPlainEditor(target)", body)
        # 单击处理器把节点本身传进去（不再靠 id 反查）
        self.assertIn("enterEdit(block.id, block.file || '', node);", JS)

    def test_2_save_carries_dom_identity(self):
        """案二：保存携带的 (file, block-id) 从**正在编辑的 DOM 节点**读回，
        与渲染闭包同源。"""
        save = JS[JS.index("async function saveEdit()"):JS.index("/* 条目 36：取消编辑")]
        self.assertIn("host.dataset.file", save)
        self.assertIn("host.dataset.blockId", save)
        self.assertIn("node.dataset.blockId = block.id;", JS)
        self.assertIn("node.dataset.file = block.file || '';", JS)
        # 不许再拿异步模型里的 file 当权威
        self.assertNotIn("file: file || model.file", JS)

    def test_3_blur_auto_saves(self):
        """案三：blur 自动保存 ＋ 可见的「已保存」反馈。"""
        body = self._enter_edit_body()
        self.assertIn("addEventListener('blur'", body)
        blur = body[body.index("addEventListener('blur'"):]
        self.assertIn("saveEdit()", blur[:400])
        self.assertIn("live.contains(document.activeElement)", blur[:400])
        self.assertIn("function showSavedBadge(", JS)
        self.assertIn("setTimeout(() => { if (badge.parentNode) badge.remove(); }, 1500);", JS)
        self.assertIn("'edit.savedBadge': '已保存',", JS)
        self.assertIn("'edit.savedBadge': 'Saved',", JS)

    def test_4_zzedit_round_trip_restores_bytes(self):
        """案四：ZZEDIT 全文往返（写入→读回→删除→字节还原），跑在真项目样例上。

        样例＝examples/minimal 的真实项目副本；另起一节纯文本段落当受试块
        （编辑器走的是纯文本，LaTeX 命令不在可编辑面内）。
        """
        import shutil
        import tempfile

        from factscribe.workbench.projects import render_tex
        from factscribe.workbench.write import save_block

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
            text = target.read_text(encoding="utf-8")
            blocks = [b for b in render_tex(text, stem="03-zzedit") if b["kind"] == "para"]
            self.assertTrue(blocks, "样例段落没渲染出来")
            block = blocks[0]
            body = block["raw"].strip()

            # ① 写入：ZZEDIT 真进文件
            result = save_block(disk, rel, block["id"], body + " ZZEDIT")
            self.assertTrue(result.get("ok"), "写入失败：%s" % result)
            after = target.read_text(encoding="utf-8")
            self.assertIn("ZZEDIT", after, "编辑没写进文件")

            # ② 读回：重新渲染这一块，能看到 ZZEDIT
            blocks2 = render_tex(after, stem="03-zzedit")
            self.assertTrue(any("ZZEDIT" in b["raw"] for b in blocks2), "读回看不到 ZZEDIT")

            # ③ 删除 ④ 字节还原：写回原文，文件回到逐字节相同
            save_block(disk, rel, block["id"], body)
            self.assertNotIn("ZZEDIT", target.read_text(encoding="utf-8"))
            self.assertEqual(target.read_bytes(), original, "删掉 ZZEDIT 后字节没还原")


class Item38RegressionTests(unittest.TestCase):
    """条目 38 两案：收集宿主指向挂载编辑器；ZZEDIT 真落文件、再删真还原。

    两案都跑在**真项目副本**（examples/minimal 的真实项目）上，
    断言的是**服务器文件内容**，不是 DOM。
    """

    def _project_copy(self, tmp: str) -> Path:
        import shutil

        src = ROOT / "examples" / "minimal"
        self.assertTrue(src.is_dir(), "真项目样例不在：examples/minimal")
        disk = Path(tmp) / "paper"
        shutil.copytree(src, disk)
        return disk

    def _probe_section(self, disk: Path):
        """造一节纯文本段落当受试块，返回 (rel, 目标文件, 块, 纯文本)。"""
        import html as htmllib
        import re

        from factscribe.workbench.projects import render_tex

        rel = "sections/03-zzedit.tex"
        target = disk / rel
        target.write_text("\\section{Round Trip Probe}\n\nZZPLAIN body text here.\n",
                          encoding="utf-8")
        text = target.read_text(encoding="utf-8")
        blocks = [b for b in render_tex(text, stem="03-zzedit") if b["kind"] == "para"]
        self.assertTrue(blocks, "受试段落没渲染出来")
        block = blocks[0]
        # 前端挂载＝克隆原节点的 innerHTML；从克隆里取纯文本。
        plain = htmllib.unescape(re.sub(r"<[^>]+>", "", block["html"]))
        return rel, target, block, plain

    def test_1_collect_host_is_the_mounted_dom_node(self):
        """案一（JS 侧）：保存/blur/还原全链路都用「挂载进 DOM 的那个节点」，
        不再拿已出 DOM 的旧引用收集文本。"""
        self.assertIn("function liveEditorNode(", JS)
        self.assertIn("document.getElementById(editing.id)", JS)
        self.assertIn("isConnected", JS)
        save = JS[JS.index("async function saveEdit()"):JS.index("/* 条目 36：取消编辑")]
        self.assertIn("liveEditorNode(editing)", save)
        self.assertNotIn("collectPlain(editing.host)", save)
        blur = JS[JS.index("addEventListener('blur'"):]
        self.assertIn("liveEditorNode(state.editing)", blur[:500])
        restore = JS[JS.index("function restoreEditedNode("):]
        restore = restore[:restore.index("}")]
        self.assertIn("liveEditorNode(editing)", restore)

    def test_2_typed_text_reaches_the_server_file(self):
        """案一（文件侧）：克隆里 insertText 出来的 ZZEDIT 真落进服务器文件。"""
        import tempfile

        from factscribe.workbench.write import save_block

        with tempfile.TemporaryDirectory() as tmp:
            disk = self._project_copy(tmp)
            rel, target, block, plain = self._probe_section(disk)
            typed = plain + " ZZEDIT"          # 克隆里插入的那几个字
            result = save_block(disk, rel, block["id"], typed)
            self.assertTrue(result.get("ok"), "写入失败：%s" % result)
            self.assertIn("ZZEDIT", target.read_text(encoding="utf-8"),
                          "用户敲的字没落到服务器文件里")

    def test_3_second_edit_removes_zzedit_and_restores(self):
        """案二：再二次编辑删掉 ZZEDIT → 文件还原（逐字节相同）。"""
        import tempfile

        from factscribe.workbench.write import save_block

        with tempfile.TemporaryDirectory() as tmp:
            disk = self._project_copy(tmp)
            rel, target, block, plain = self._probe_section(disk)
            original = target.read_bytes()
            save_block(disk, rel, block["id"], plain + " ZZEDIT")
            self.assertIn("ZZEDIT", target.read_text(encoding="utf-8"))
            save_block(disk, rel, block["id"], plain)      # 二次编辑：删掉 ZZEDIT
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
        # 侧栏在文档流里由 .shell 的 padding-right 让位，头部宽度与之同源
        self.assertIn(".shell{padding-right:336px;transition:padding-right .22s ease}", CSS)

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
        # 三个面板（目录 / 智能助手 / 更多）都挂着 .np-pane-h
        self.assertEqual(HTML.count('class="np-pane-h'), 5)

    def test_5_decorative_who_is_untouched(self):
        """案五：AI 层 ``.who`` 发送者标是装饰，保持原浅色。"""
        self.assertIn("#a49e8d", self._rule(".msg .who"))


if __name__ == "__main__":
    unittest.main()
