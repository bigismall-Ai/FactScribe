# -*- coding: utf-8 -*-
"""条目 44：正文编辑「不跟手」——实测定位与修复的守门测试。

这一组钉三件事（静态断言守结构，真浏览器那一跑验行为）：

1. **IME 组合感知**：组合进行中（拼音还在候选框里）不收正文、不改编辑宿主、
   不挂状态 UI；组合结束后统一补做（芯片重绑 ＋ 欠下的替换／角标／保存）。
   实测（真 Chrome ＋ CDP 真 IME 组合输入）修复前的样子：保存响应把「已保存」
   角标插进正在编辑的宿主，正文文本流被顶出角标文字，下一次组合把光标甩进
   角标文本节点（offset 1）；修复后宿主内零节点变动、光标稳稳跟住组合文本。
2. **光标恢复**：整块替换 DOM 前后按**段内偏移**把光标放回原处，不甩回块首。
3. **状态 UI 不落在编辑区内**：「已保存」角标挂 body 浮层（absolute ＋
   pointer-events:none），不再插进可编辑宿主；落盘层照旧跳过 data-badge。

真浏览器那一跑需要 node（≥22，内置 WebSocket）与 Chrome；缺任一个就跳过，
不拿「跳过」冒充「验过」。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATIC = ROOT / "factscribe" / "workbench" / "static"
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")

DRIVER = ROOT / "tests" / "editing_ime_driver.mjs"
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]


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


class ImeCompositionTests(unittest.TestCase):
    """① IME 组合感知：组合期间只记账，不动 DOM、不收正文。"""

    def test_composition_listeners_registered(self):
        """组合开始/结束都被听见（capture，冒泡到 document）。"""
        self.assertIn("document.addEventListener('compositionstart'", JS)
        self.assertIn("document.addEventListener('compositionend'", JS)
        start = _slice("document.addEventListener('compositionstart'", "}, true);")
        self.assertIn("imeState.active = true;", start)
        self.assertIn("imeState.blockId = node ? (node.dataset.blockId || '') : '';", start)
        end = _slice("document.addEventListener('compositionend'", "}, true);")
        self.assertIn("imeState.active = false;", end)
        self.assertIn("flushAfterComposition(blockId);", end)

    def test_composition_state_keeps_pending_work(self):
        """组合状态机把欠下的三件事分别记账。"""
        self.assertIn("const imeState = {", JS)
        for field in ("active:", "blockId:", "pendingSave:", "pendingBadge:", "pendingHtml:"):
            self.assertIn(field, JS)

    def test_save_is_deferred_during_composition(self):
        """组合期间不收正文——此刻 DOM 里是候选中的拼音，收下去会写进 .tex。"""
        save = _slice("async function saveBlockNode(", "/* 条目 43：BLOCK_STALE")
        self.assertIn("if (imeState.active) {", save)
        self.assertIn("imeState.pendingSave = node;", save)
        # 记账之后立刻返回，不落 POST
        guard = save[save.index("if (imeState.active) {"):save.index("if (node.dataset.saving === '1') {")]
        self.assertNotIn("fetch(", guard)

    def test_block_html_swap_deferred_during_composition(self):
        """组合期间不整块替换 DOM——换了内容，候选里的拼音就断了。"""
        apply_fn = _slice("function applyBlockHtml(", "/* 条目 43：保存一个块")
        self.assertIn("if (imeState.active && (!imeState.blockId || imeState.blockId === blockId)) {", apply_fn)
        self.assertIn("imeState.pendingHtml = { blockId: blockId, html: html, sha: sha || '' };", apply_fn)
        self.assertIn("return false;", apply_fn)

    def test_badge_deferred_during_composition(self):
        """组合期间不挂角标（挂它要动编辑宿主附近的 DOM）。"""
        badge = _slice("function showSavedBadge(", "/* ---------------------------------------------------------------- 章节管理")
        self.assertIn("if (imeState.active && (!imeState.blockId || imeState.blockId === blockId)) {", badge)
        self.assertIn("imeState.pendingBadge = blockId;", badge)

    def test_flush_after_composition_does_the_deferred_work(self):
        """组合结束统一补做：芯片重绑 ＋ 欠下的替换／角标／保存。"""
        flush = _slice("function flushAfterComposition(", "/* 条目 44：组合迟迟不结束")
        self.assertIn("bindFactChips(host);", flush)
        self.assertIn("bindChipCaret(host);", flush)
        self.assertIn("applyBlockHtml(pending.blockId, pending.html, pending.sha);", flush)
        self.assertIn("showSavedBadge(bid);", flush)
        self.assertIn("saveBlockNode(n);", flush)

    def test_stuck_composition_has_a_bounded_fallback(self):
        """组合迟迟不结束有兜底：撤掉「组合中」标记，但不当场去收正文。"""
        self.assertIn("function clearStuckComposition()", JS)
        self.assertIn("imeState.stuckTimer = setTimeout(clearStuckComposition, 5000);", JS)
        stuck = _slice("function clearStuckComposition()", "function collectPlain(")
        self.assertIn("imeState.active = false;", stuck)
        self.assertNotIn("saveBlockNode(", stuck)


class CaretRestoreTests(unittest.TestCase):
    """② 光标：整块替换 DOM 后按段内偏移放回原处。"""

    def test_caret_offset_helpers_exist(self):
        """取/还光标偏移：Range 取文本偏移，TreeWalker 按偏移回位。"""
        self.assertIn("function caretTextOffset(host) {", JS)
        self.assertIn("function restoreCaretOffset(host, offset) {", JS)
        take = _slice("function caretTextOffset(host) {", "function restoreCaretOffset(")
        self.assertIn("host.contains(range.startContainer)", take)
        self.assertIn("pre.toString().length", take)
        put = _slice("function restoreCaretOffset(host, offset) {", "/* 条目 44：组合结束")
        self.assertIn("document.createTreeWalker(host, NodeFilter.SHOW_TEXT)", put)
        self.assertIn("sel.removeAllRanges();", put)

    def test_apply_block_html_captures_then_restores(self):
        """先记偏移、再替换、后放回——顺序不能反。"""
        apply_fn = _slice("function applyBlockHtml(", "/* 条目 43：保存一个块")
        i_capture = apply_fn.index("const caret = caretTextOffset(host);")
        i_swap = apply_fn.index("host.innerHTML = fresh.innerHTML;")
        i_restore = apply_fn.index("restoreCaretOffset(host, caret);")
        self.assertLess(i_capture, i_swap)
        self.assertLess(i_swap, i_restore)

    def test_chip_caret_rebound_after_swap(self):
        """整块替换后芯片的「点一下把光标放回正文」要重绑（否则点芯片丢光标）。"""
        apply_fn = _slice("function applyBlockHtml(", "/* 条目 43：保存一个块")
        self.assertIn("bindFactChips(host);", apply_fn)
        self.assertIn("bindChipCaret(host);", apply_fn)


class StatusUiOutsideEditorTests(unittest.TestCase):
    """③ 保存状态类 UI 不得插在编辑宿主内部。"""

    def test_badge_not_appended_into_editable_host(self):
        """角标不再 append 进可编辑宿主（老写法已拆）。"""
        badge = _slice("function showSavedBadge(", "/* ---------------------------------------------------------------- 章节管理")
        self.assertNotIn("host.appendChild(badge)", badge)
        self.assertNotIn("blockContentHost(node);\n  host.appendChild", badge)

    def test_badge_mounted_on_body_as_overlay(self):
        """角标挂 body 浮层：出宿主、不吃点击、组合期不挂。"""
        badge = _slice("function showSavedBadge(", "/* ---------------------------------------------------------------- 章节管理")
        self.assertIn("document.body.appendChild(badge);", badge)
        self.assertIn("badge.setAttribute('contenteditable', 'false');", badge)
        self.assertIn("badge.dataset.badge = '1';", badge)
        self.assertIn("badge.style.visibility = 'hidden';", badge)

    def test_badge_css_is_floating_and_click_through(self):
        """CSS：浮层定位 ＋ 不吃鼠标事件（不吃就不会把编辑器点失焦）。"""
        rule = [line for line in CSS.splitlines() if ".save-badge{" in line]
        self.assertTrue(rule, "没有 .save-badge 规则")
        joined = "".join(rule) + CSS[CSS.index(".save-badge{"):CSS.index(".save-badge{") + 400]
        self.assertIn("position:absolute", joined)
        self.assertIn("pointer-events:none", joined)
        self.assertNotIn("margin-left:8px", joined)

    def test_collect_plain_still_skips_badge(self):
        """落盘层照旧跳过角标（收集的是散文＋token，不是界面零件）。"""
        collect = _slice("function collectPlain(", "/* 块的 DOM 节点")
        self.assertIn("node.dataset.badge", collect)


@unittest.skipUnless(HAS_BROWSER, "真浏览器那一跑需要 node≥22 与 Chrome")
class BrowserBehaviourTests(unittest.TestCase):
    """真浏览器复测：真键盘事件 ＋ 真 IME 组合输入（Chrome headless ＋ CDP）。"""

    @classmethod
    def setUpClass(cls):
        from factscribe.workbench.server import create_server

        import tempfile

        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        disk = root / "paper"
        shutil.copytree(ROOT / "examples" / "minimal", disk)
        server, _index = create_server(str(root), port=0, ttl=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.server = server
        cls.url = "http://127.0.0.1:%d/" % server.server_address[1]
        proc = subprocess.run(
            ["node", str(DRIVER), cls.url],
            capture_output=True, text=True, timeout=300,
            cwd=str(ROOT),
        )
        cls.raw = proc.stdout.strip()
        try:
            cls.data = json.loads(cls.raw.splitlines()[-1]) if cls.raw else {}
        except json.JSONDecodeError:
            cls.data = {}
        if not cls.data or "error" in cls.data:
            raise unittest.SkipTest("浏览器驱动没跑通：%s / %s" % (cls.raw[:300], proc.stderr[:300]))

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
        except Exception:
            pass
        cls._tmp.cleanup()

    def test_typing_latency_stays_low(self):
        """英文逐键：按键→上屏延迟在毫秒级，且每键只有正文变动。"""
        english = self.data.get("english", {})
        self.assertTrue(english.get("nInputs"), "没抓到输入事件")
        d = english["down2input"]
        self.assertLess(d["avg"], 5.0, "按键→DOM 延迟均值过高：%s" % d)
        self.assertLess(d["max"], 60.0, "按键→DOM 延迟峰值过高：%s" % d)
        p = english["input2paint"]
        self.assertLess(p["avg"], 40.0, "上屏延迟均值过高：%s" % p)
        self.assertEqual(english["mutNonChar"], 0, "打字期间有非正文的 DOM 变动")
        self.assertEqual(english["nodes"], english["nodes0"], "打字期间 DOM 节点数变了")

    def test_ime_composition_survives_save_response(self):
        """组合进行中保存响应回来：编辑宿主内零节点变动，角标不进宿主。"""
        badge = self.data.get("imeBadge", {}).get("afterBadge", {})
        self.assertFalse(badge.get("badgeInHost"), "角标插进了编辑宿主：%s" % badge)
        self.assertEqual(badge.get("kids"), badge.get("kidsBefore"),
                         "保存响应在编辑宿主里动了节点")
        self.assertNotIn("已保存", badge.get("tail", ""))
        self.assertNotIn("Saved", badge.get("tail", ""))
        comps = badge.get("comps", [])
        self.assertIn("compositionstart", comps)
        self.assertIn("compositionupdate", comps)

    def test_caret_stays_with_composition_text(self):
        """组合继续：光标跟住组合文本，不被甩进角标（老读数：offset 1 / ctx 'S'）。"""
        nxt = self.data.get("imeBadge", {}).get("nextComposition", {})
        caret = nxt.get("caret") or {}
        self.assertEqual(caret.get("node"), "#text", "光标不在文本节点上：%s" % caret)
        self.assertNotEqual(caret.get("ctx"), "S", "光标被甩进角标：%s" % caret)
        self.assertGreater(caret.get("offset", 0), 1, "光标被甩到块首：%s" % caret)

    def test_caret_survives_block_html_replacement(self):
        """整块替换 DOM 前后光标偏移不变（老读数：跳回 P offset 0＝块首）。"""
        restore = self.data.get("restore", {})
        before = restore.get("before") or {}
        after = restore.get("after") or {}
        self.assertTrue(before, "没抓到替换前的光标")
        self.assertEqual(after.get("offset"), before.get("offset"),
                         "整块替换后光标偏移变了：%s → %s" % (before, after))
        self.assertEqual(after.get("ctx"), before.get("ctx"),
                         "整块替换后光标落点变了：%s → %s" % (before, after))
        self.assertNotEqual(after.get("node"), "P", "光标跳回块首了：%s" % after)


if __name__ == "__main__":
    unittest.main()
