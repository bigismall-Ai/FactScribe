# -*- coding: utf-8 -*-
r"""三件用户诉求的守门测试：章节名／论文标题、右栏可拖、\fact 插入。

这一组钉两件事：

1. **静态断言守结构**——前端三件套（app.js / app.css / index.html）与核心
   端点都要有对应的入口、指纹闸与双语文案。
2. **真浏览器那一跑验行为**——真 Chrome（headless）＋ CDP 真鼠标／真键盘，
   把三件事各跑一遍，再把落盘内容读回来比对。

真浏览器那一跑需要 node（≥22，内置 WebSocket）与 Chrome；缺任一个就跳过，
不拿「跳过」冒充「验过」。驱动跑起来了但读数不对 → 判红，不静默跳过。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATIC = ROOT / "factscribe" / "workbench" / "static"
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
SERVER_PY = (ROOT / "factscribe" / "workbench" / "server.py").read_text(encoding="utf-8")
WRITE_PY = (ROOT / "factscribe" / "workbench" / "write.py").read_text(encoding="utf-8")

DRIVER = ROOT / "tests" / "miniapp_ui_driver.mjs"
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]

#: 这一轮新加的文案键——中英各一条，缺一条就是半中半英。
NEW_I18N_KEYS = (
    "toc.rename", "toc.renameT", "toc.renamePh", "toc.renameDone",
    "title.edit", "title.editT", "title.main", "title.sub", "title.hint",
    "title.saved",
    "fact.ins", "fact.insT", "fact.insPh", "fact.insLoading",
    "fact.insEmpty", "fact.insHint", "fact.insDone", "fact.insFail",
    "nav.resize",
)

#: 测试用事实：value=16（产物里真有这个数），正文里也有 → 插入应只补标记。
FACT_A4_TOML = """
[[fact]]
id = "A4"
claim = "题目集总数（16 题）"
value = "16"
source = "results/swb16.md"
source_sha256 = "0147ea0c82fd08052ff62cca1f13f2436264e2998db5d69a2ae051848c63808a"
locator = "§一 口径：SWB16（16 题，固定）"
confidence = "high"
derived_from = []
note = "测试用事实：数字 16 来自产物，正文里也有"
"""


def _chrome() -> str | None:
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    return shutil.which("google-chrome") or shutil.which("chromium")


def _node_ok() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    try:
        out = subprocess.run([node, "-p", "process.versions.node.split('.')[0]"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return False
    try:
        return int(out) >= 22
    except ValueError:
        return False


HAS_BROWSER = bool(_chrome()) and _node_ok()


def _slice(start: str, end: str, text: str = JS) -> str:
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


class SectionRenameTests(unittest.TestCase):
    """① 章节名：目录每行一支笔 → 只改标题命令（指纹闸护着）。"""

    def test_toc_row_carries_rename_button(self):
        self.assertIn('data-rename="1"', JS)
        self.assertIn("data-block=", JS)
        self.assertIn("data-sha=", JS)

    def test_rename_button_is_wired(self):
        self.assertIn("$$('#tocList [data-rename]').forEach", JS)
        self.assertIn("openRenameSection(btn);", JS)

    def test_rename_reads_the_block_fingerprint(self):
        fn = _slice("function openRenameSection(btn) {",
                    "async function saveRenameSection()")
        self.assertIn("sha: btn.dataset.sha || '',", fn)

    def test_rename_uses_its_own_channel_with_expect_sha(self):
        fn = _slice("async function saveRenameSection()", "function moveSection(")
        self.assertIn("await tocAction('toc/rename', {", fn)
        self.assertIn("expect_sha: target.sha,", fn)
        # 不许借道 /edit：那条通道会把标题命令整条写掉。
        self.assertNotIn("/edit", fn)

    def test_server_exposes_rename_endpoint(self):
        self.assertIn('what == "rename"', SERVER_PY)
        self.assertIn("rename_section(disk, rel,", SERVER_PY)

    def test_core_rename_only_rewrites_the_heading(self):
        fn = _slice("def rename_section(", "def set_disk_title(", WRITE_PY)
        self.assertIn("_rewrite_heading_title(block.raw, clean)", fn)
        self.assertIn("_check_expect_sha(block, expect_sha)", fn)
        self.assertIn("atomic_write(path, new_text", fn)

    def test_rename_modal_exists(self):
        for ident in ("modalRename", "rnTitle", "rnOk", "rnCancel"):
            self.assertIn('id="%s"' % ident, HTML)


class DiskTitleTests(unittest.TestCase):
    """① 论文标题：封面上一支笔 → 改盘自己入口文件的标题命令。"""

    def test_cover_has_edit_button(self):
        self.assertIn('id="btnEditTitle"', HTML)
        self.assertIn('class="cover-title-row"', HTML)

    def test_title_modal_exists(self):
        for ident in ("modalTitle", "dtTitle", "dtSub", "dtOk", "dtCancel"):
            self.assertIn('id="%s"' % ident, HTML)

    def test_title_save_posts_expect_sha(self):
        fn = _slice("async function saveDiskTitle()",
                    "/* ---------------------------------------------------------------- 封面摘要")
        self.assertIn("disk.id)}/title", fn)
        self.assertIn("expect_sha: (state.meta && state.meta.title_sha) || '',", fn)

    def test_title_edit_refreshes_the_cover(self):
        fn = _slice("async function saveDiskTitle()",
                    "/* ---------------------------------------------------------------- 封面摘要")
        self.assertIn("renderCover();", fn)

    def test_server_exposes_title_endpoint(self):
        self.assertIn('if action == "title":', SERVER_PY)
        self.assertIn("set_disk_title(disk,", SERVER_PY)

    def test_core_title_uses_the_same_locator_as_the_reader(self):
        fn = _slice("def set_disk_title(", "def _number_spot(", WRITE_PY)
        self.assertIn("title_command_span(root)", fn)
        self.assertIn("_short_sha(raw) != expect_sha", fn)


class NavSplitterTests(unittest.TestCase):
    """② 右栏可拖：分隔条改左右比例，宽度记本机、刷新还在。"""

    def test_splitter_element_and_style_exist(self):
        self.assertIn('id="navSplitter"', HTML)
        self.assertIn(".nav-splitter{", CSS)
        self.assertIn("cursor:col-resize", CSS)

    def test_width_is_a_css_variable(self):
        self.assertIn(":root{--nav-w:320px}", CSS)
        self.assertIn("width:var(--nav-w,320px)", CSS)
        self.assertIn("padding-right:calc(var(--nav-w,320px) + 16px)", CSS)

    def test_width_is_persisted_on_this_machine(self):
        self.assertIn("const NAVW_KEY = 'factscribe.navw';", JS)
        self.assertIn("localStorage.setItem(NAVW_KEY, String(w));", JS)

    def test_width_has_bounds(self):
        self.assertIn("const NAVW_MIN = 240;", JS)
        self.assertIn("const NAVW_MAX = 640;", JS)
        self.assertIn("const NAVW_BODY_MIN = 420;", JS)

    def test_drag_uses_pointer_events(self):
        fn = _slice("function initNavSplitter()", "async function main()")
        self.assertIn("bar.addEventListener('pointerdown'", fn)
        self.assertIn("bar.addEventListener('pointermove'", fn)
        self.assertIn("bar.addEventListener('pointerup', stop);", fn)

    def test_release_records_the_live_width(self):
        # 松手时记的是**本轮生效**的宽度；回头去读存储里的旧值会把刚拖出来的
        # 宽度又弹回默认（那是上一版实测复现过的 bug）。
        fn = _slice("function initNavSplitter()", "async function main()")
        self.assertIn("const w = currentNavWidth;", fn)
        self.assertIn("localStorage.setItem(NAVW_KEY, String(w));", fn)

    def test_splitter_is_initialised(self):
        self.assertIn("initNavSplitter();", JS)


class FactInsertTests(unittest.TestCase):
    """③ 保护面：段落菜单里挑账上的一条事实 → 标记插进正文。"""

    def test_paragraph_menu_has_insert_entry(self):
        self.assertIn('id="miFact"', HTML)
        self.assertIn("openFactInsert(target);", JS)

    def test_insert_panel_reads_the_ledger(self):
        fn = _slice("async function openFactInsert(",
                    "function renderFactInsertList(")
        self.assertIn("disk.id)}/facts", fn)

    def test_insert_posts_expect_sha(self):
        fn = _slice("async function insertFactBinding(",
                    "/* ---------------------------------------------------------------- 项目表单")
        self.assertIn("disk.id)}/fact/insert", fn)
        self.assertIn("expect_sha: target.sha,", fn)

    def test_inserted_marker_is_applied_in_place(self):
        fn = _slice("async function insertFactBinding(",
                    "/* ---------------------------------------------------------------- 项目表单")
        self.assertIn("applyBlockHtml(id, blocks[id], shas[id]);", fn)

    def test_client_does_not_type_protected_commands_by_hand(self):
        # 手写的 \fact{…} 会被服务端剥掉（那是给散文留的口径）——面板只发
        # 事实 id，标记由服务端落盘。
        fn = _slice("async function insertFactBinding(",
                    "/* ---------------------------------------------------------------- 项目表单")
        self.assertNotIn("\\fact{", fn)

    def test_server_exposes_facts_endpoints(self):
        self.assertIn('if what == "facts":', SERVER_PY)
        self.assertIn('action == "fact" and len(parts) > 5 and parts[5] == "insert":',
                      SERVER_PY)

    def test_core_insert_goes_through_the_ledger_and_the_value_gate(self):
        fn = _slice("def insert_fact_binding(", "def _safe_config(", WRITE_PY)
        self.assertIn("load_facts(cfg)", fn)
        self.assertIn("check_value_in_source(root, cfg, source_rel, source_path, value",
                      fn)
        self.assertIn("FACT_NOT_IN_LEDGER", fn)
        self.assertIn("FACT_ALREADY_BOUND", fn)


class I18nTests(unittest.TestCase):
    """新文案必须中英双语齐全——不许半中半英。"""

    def test_new_keys_exist_in_both_dictionaries(self):
        for key in NEW_I18N_KEYS:
            # 只数字典条目（键后面带冒号），t() 的调用不算。
            self.assertEqual(JS.count("'%s':" % key), 2,
                             "%s 的文案不是中英各一条" % key)

    def test_rename_toast_is_translated(self):
        self.assertIn("'toc.renameDone': '章节名已改'", JS)
        self.assertIn("'toc.renameDone': 'Section renamed'", JS)

    def test_fact_insert_done_is_translated(self):
        self.assertIn("'fact.insDone': '事实标记已插进正文'", JS)
        self.assertIn("'fact.insDone': 'Fact marker inserted'", JS)


@unittest.skipUnless(HAS_BROWSER, "真浏览器那一跑需要 node≥22 与 Chrome")
class BrowserFeatureTests(unittest.TestCase):
    """真浏览器实跑：Chrome headless ＋ CDP（真鼠标／真键盘）。"""

    @classmethod
    def setUpClass(cls):
        from factscribe.workbench.server import create_server

        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        disk = root / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", disk)
        ledger = disk / "facts" / "01-core.toml"
        ledger.write_text(ledger.read_text(encoding="utf-8") + FACT_A4_TOML,
                          encoding="utf-8")
        server, _index = create_server(str(root), port=0, ttl=0,
                                        state_dir=str(root / "_state"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.server = server
        cls.disk = disk
        cls.url = "http://127.0.0.1:%d/" % server.server_address[1]
        proc = subprocess.run(
            ["node", str(DRIVER), cls.url, "A4"],
            capture_output=True, text=True, timeout=420, cwd=str(ROOT),
        )
        cls.raw = proc.stdout.strip()
        try:
            cls.data = json.loads(cls.raw.splitlines()[-1]) if cls.raw else {}
        except (json.JSONDecodeError, IndexError):
            cls.data = {}
        if not cls.data:
            raise unittest.SkipTest("浏览器驱动没输出读数：%s / %s"
                                    % (cls.raw[:300], proc.stderr[:300]))

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
        except Exception:
            pass
        cls._tmp.cleanup()

    def test_driver_ran(self):
        self.assertTrue(self.data.get("ok"),
                        "浏览器驱动报错：%s" % self.data.get("error"))

    def test_rename_section_writes_only_the_heading(self):
        ren = self.data.get("rename", {})
        self.assertTrue(ren.get("modalOpen"), "改名弹窗没打开")
        before = ren.get("before") or []
        after = ren.get("after") or []
        self.assertTrue(before, "目录里没有可改的行")
        self.assertEqual(after[0], "E2E 章节名", "目录里的章节名没改：%s" % after)
        text = (self.disk / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("\\section{E2E 章节名}", text)
        # 这一节里原有的绑定标记一个没少（只动了标题命令那一处）。
        self.assertIn("\\fact{A1}", text)
        self.assertIn("\\fact{A3}", text)
        self.assertIn("\\label{sec:intro}", text)

    def test_paper_title_writes_the_title_command(self):
        t = self.data.get("title", {})
        self.assertTrue(t.get("modalOpen"), "标题弹窗没打开")
        self.assertEqual(t.get("after"), "E2E 论文标题 / E2E 副标题",
                         "封面标题没改：%s" % t.get("after"))
        main = (self.disk / "main.tex").read_text(encoding="utf-8")
        self.assertIn("\\title{E2E 论文标题 \\\\ E2E 副标题}", main)

    def test_splitter_changes_width_and_survives_reload(self):
        sp = self.data.get("splitter", {})
        before = sp.get("before")
        after = sp.get("afterDrag", {})
        reloaded = sp.get("afterReload", {})
        self.assertEqual(before, 320, "默认宽度不是 320：%s" % before)
        self.assertGreater(after.get("navW", 0), before,
                           "拖了没变宽：%s" % after)
        self.assertEqual(after.get("stored"), str(after.get("navW")),
                         "拖出来的宽度没记进本机存储：%s" % after)
        self.assertEqual(reloaded.get("navW"), after.get("navW"),
                         "刷新后宽度没保住：%s" % reloaded)
        self.assertEqual(reloaded.get("stored"), str(after.get("navW")),
                         "刷新后存储里的宽度不对：%s" % reloaded)
        events = sp.get("events", {})
        for name in ("down", "move", "up"):
            self.assertGreaterEqual(events.get(name, 0), 1,
                                    "分隔条没收到 pointer%s：%s" % (name, events))
        clamp = sp.get("clamp", {})
        self.assertLessEqual(clamp.get("wide", 9999), 640, "最宽没被钳住：%s" % clamp)
        self.assertGreaterEqual(clamp.get("narrow", 0), 240, "最窄没被钳住：%s" % clamp)
        self.assertGreaterEqual(clamp.get("bodyLeft", 0), 420,
                                "正文被拖没了：%s" % clamp)

    def test_insert_fact_binds_from_the_ledger(self):
        f = self.data.get("fact", {})
        self.assertTrue(f.get("menuOpen"), "段落菜单没打开")
        rows = f.get("rows") or []
        self.assertIn("A4", rows, "账上事实没列出来：%s" % rows)
        before = f.get("before", {})
        after = f.get("after", {})
        self.assertEqual(after.get("chips"), before.get("chips", 0) + 1,
                         "芯片数没多一个：%s → %s"
                         % (before.get("chips"), after.get("chips")))
        text = (self.disk / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("\\fact{A4}", text)
        # 标记插在那个数字后面（数字来自账本 value，不是现编的）。
        self.assertTrue(re.search(r"16\s*\\fact\{A4\}", text),
                        "标记没插在 16 后面：%s" % text[-400:])
        self.assertIn("\\fact{A1}", text)


if __name__ == "__main__":
    unittest.main()
