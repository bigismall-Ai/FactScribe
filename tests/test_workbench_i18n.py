# -*- coding: utf-8 -*-
"""tests/test_workbench_i18n.py —— 工作台段六返修：EN 字典不许混中文。

验收打回（i18n 污染）：段五/段六重构时从 zh 字典复制了尾部落进 EN 字典，
EN 模式下这些界面文字全是中文，双语机制形同虚设。

这一组断言把口径钉死：

1. **EN 字典块内 CJK 字符数 ＝ 0**（zh 块除外）——字典边界按代码结构判定
   （`en: {` 到与之配对的顶层 `},`），不靠行号硬编码；
2. **zh / en 键集合一一对应**——不多不少，键名一致；
3. **界面文案不许硬编码中文**——toast 这类直接写死的中文串要改成 i18n 键。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP_JS = ROOT / "factscribe" / "workbench" / "static" / "app.js"
INDEX_HTML = ROOT / "factscribe" / "workbench" / "static" / "index.html"

#: CJK 统一表意文字 ＋ 中文标点 ＋ 全角符号。
CJK_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")

#: i18n 键的写法：'key': 'value'
KEY_RE = re.compile(r"'([A-Za-z][A-Za-z0-9_.]*)':")


def _dict_blocks(lines: list[str]) -> tuple[tuple[int, int], tuple[int, int]]:
    """I18N 里 zh 块与 en 块的行号区间（0 基，含首尾）。

    边界按代码结构判定：`zh: {` / `en: {` 起始，到与之配对的顶层 `},`
    或 `}` 结束——不靠行号硬编码，改了字典长度也不会失效。
    """
    zh_start = next(i for i, ln in enumerate(lines) if ln.strip() == "zh: {")
    en_start = next(i for i, ln in enumerate(lines) if ln.strip() == "en: {")

    def block_end(start: int) -> int:
        for i in range(start + 1, len(lines)):
            if lines[i] in ("  },", "  }"):
                return i
        raise AssertionError("i18n 字典块没有闭合")

    return (zh_start, block_end(zh_start)), (en_start, block_end(en_start))


class EnglishDictIsPureEnglishTests(unittest.TestCase):
    """EN 字典块内不许有 CJK。"""

    def setUp(self):
        self.lines = APP_JS.read_text(encoding="utf-8").splitlines()
        (self.zh_start, self.zh_end), (self.en_start, self.en_end) = _dict_blocks(self.lines)

    def test_english_block_has_zero_cjk(self):
        offenders = []
        for index in range(self.en_start, self.en_end + 1):
            text = self.lines[index]
            if not text.strip() or text.strip().startswith(("/*", "//", "*")):
                continue
            hits = CJK_RE.findall(text)
            if hits:
                offenders.append((index + 1, text.strip(), "".join(sorted(set(hits)))))
        self.assertEqual(
            offenders, [],
            "EN 字典块（第 %d–%d 行）里有中文值：%s"
            % (self.en_start + 1, self.en_end + 1, offenders))

    def test_english_block_cjk_character_count_is_zero(self):
        total = sum(len(CJK_RE.findall(self.lines[i]))
                    for i in range(self.en_start, self.en_end + 1)
                    if self.lines[i].strip()
                    and not self.lines[i].strip().startswith(("/*", "//", "*")))
        self.assertEqual(total, 0)

    def test_chinese_block_still_holds_chinese(self):
        """反查：zh 块里确实有中文（别把两块内容搞反了）。"""
        total = sum(len(CJK_RE.findall(self.lines[i]))
                    for i in range(self.zh_start, self.zh_end + 1))
        self.assertGreater(total, 100)

    def test_key_sets_match(self):
        zh_block = "\n".join(self.lines[self.zh_start + 1:self.zh_end])
        en_block = "\n".join(self.lines[self.en_start + 1:self.en_end])
        zh_keys = set(KEY_RE.findall(zh_block))
        en_keys = set(KEY_RE.findall(en_block))
        self.assertEqual(zh_keys - en_keys, set(), "zh 有、en 缺的键")
        self.assertEqual(en_keys - zh_keys, set(), "en 有、zh 缺的键")
        self.assertEqual(len(zh_keys), len(en_keys))

    def test_no_hardcoded_chinese_in_ui_toasts(self):
        """界面文案不许硬编码中文（注释与协议标记除外）。"""
        offenders = []
        for index, line in enumerate(self.lines):
            if self.zh_start <= index <= self.en_end:
                continue
            text = line.strip()
            if not text or text.startswith(("/*", "//", "*")):
                continue
            if "toast(" not in text:
                continue
            if CJK_RE.search(text):
                offenders.append((index + 1, text))
        self.assertEqual(offenders, [], "这些 toast 写死了中文，改走 i18n：%s" % offenders)

    def test_fallback_marker_is_untouched(self):
        """降级标记是协议（服务端首行约定），不许被 i18n 改掉。"""
        text = "\n".join(self.lines)
        self.assertIn("const AI_FALLBACK_MARK = '模拟回答（未接模型）';", text)

    def test_html_chrome_is_localised(self):
        """index.html 里除语言钮与标题外，界面文案都走 data-i18n。"""
        lines = INDEX_HTML.read_text(encoding="utf-8").splitlines()
        allowed = {"中"}      # 语言钮本身就用「中」标自己
        offenders = []
        for index, line in enumerate(lines):
            text = line.strip()
            if not text or text.startswith(("<!--", "//", "*")):
                continue
            if "data-i18n" in line:
                continue
            if "<title>" in line:
                continue                      # 标题由 applyI18n 设
            hits = [c for c in CJK_RE.findall(line) if c not in allowed]
            if hits:
                offenders.append((index + 1, text))
        # 未被 JS 覆盖的静态占位（新建页标题、摘要标签）由 JS 就地改写，
        # HTML 里留着中文占位没问题——但**只许这两个**，多一个就是漏网。
        allowed_prefixes = ("<h1 id=\"fvTitle\"",
                            "<div class=\"ab-label\"")
        self.assertEqual([o for o in offenders
                          if not o[1].startswith(allowed_prefixes)], [])
        self.assertEqual(len(offenders), 2)


if __name__ == "__main__":
    unittest.main()
