# -*- coding: utf-8 -*-
"""Markdown 文档解析：等长遮罩、标题清单、段落切分所需的 prose。

只服务 ``style --doc``（规范见 ``docs/design/SPEC-DOCMODE.md``）。做法与
``texscan`` 的 LaTeX 遮罩同构：

* 遮罩把目标区间替换为**等长空白**，换行原样保留，因此
  ``_line_of(prose, pos)`` 直接等于原文行号；
* 标题行在 prose 中整行遮罩，句子/段落统计不会把标题算成正文；
* 围栏、表格行、front matter 被遮成空白行，段落天然被它们隔开。

遮罩顺序：front matter → 围栏代码 → HTML 注释 → 行内代码 → 链接目标 →
表格行。前一步遮掉的字符在下一步里已是空白，不会被二次解释。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MARKDOWN_SUFFIXES = (".md", ".markdown")
TEX_SUFFIXES = (".tex",)

_FENCE_OPEN_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*([^\n]*)$")
_HEADING_LINE_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")


@dataclass
class ScanResult:
    """一段源码的解析结果：遮罩后的正文 + 标题清单。"""

    prose: str
    headings: list = field(default_factory=list)


def format_of(path) -> str:
    """按扩展名判定格式：markdown / tex / text。"""
    suffix = Path(str(path)).suffix.lower()
    if suffix in MARKDOWN_SUFFIXES:
        return "markdown"
    if suffix in TEX_SUFFIXES:
        return "tex"
    return "text"


def _blank(chars: list, start: int, stop: int) -> None:
    """把 [start, stop) 抹成空格，保留换行（行列号不漂）。"""
    stop = min(stop, len(chars))
    for i in range(max(0, start), stop):
        if chars[i] != "\n":
            chars[i] = " "


def _lines(s: str):
    """逐行产出 (行起点, 行尾位置(不含换行), 行内容)。"""
    i, n = 0, len(s)
    while i <= n:
        end = s.find("\n", i)
        if end < 0:
            end = n
        yield i, end, s[i:end]
        if end >= n:
            return
        i = end + 1


def _mask_front_matter(chars: list) -> None:
    """文件头的 ``---`` ... ``---``（或 ``...``）整块遮罩。

    只在文件第一行就是 ``---`` 时生效；没有闭合行则遮到文末。
    行尾允许空白，便于手写 YAML 常见的尾随空格。
    """
    s = "".join(chars)
    first_end = s.find("\n")
    first_line = s if first_end < 0 else s[:first_end]
    if first_line.strip() != "---":
        return
    pos = len(first_line) + 1
    while pos <= len(s):
        end = s.find("\n", pos)
        if end < 0:
            end = len(s)
        if s[pos:end].strip() in ("---", "..."):
            _blank(chars, 0, end)
            return
        if end >= len(s):
            break
        pos = end + 1
    _blank(chars, 0, len(s))


def _mask_fences_stable(chars: list) -> None:
    """围栏代码（``` 与 ~~~）整块遮罩，保留围栏内的换行。

    * 开启行允许最多 3 个空格缩进；
    * 闭合行必须同字符、长度 ≥ 开启串、其后只有空白；
    * 未闭合则遮到文末（不崩、不吞掉规则判断的稳定性）。
    * 逐行推进，被前一个围栏吞掉的行不会重复处理（嵌套围栏天然按内容算）。
    """
    s = "".join(chars)
    i, n = 0, len(s)
    while i < n:
        end = s.find("\n", i)
        if end < 0:
            end = n
        m = _FENCE_OPEN_RE.match(s[i:end])
        if not m:
            i = end + 1
            continue
        fence = m.group(1)
        ch, length = fence[0], len(fence)
        close_re = re.compile(
            r"^[ \t]{0,3}%s{%d,}[ \t]*$" % (re.escape(ch), length))
        pos = end + 1
        while pos <= n:
            c_end = s.find("\n", pos)
            if c_end < 0:
                c_end = n
            if close_re.match(s[pos:c_end]):
                _blank(chars, i, c_end)
                i = c_end + 1
                break
            if c_end >= n:
                _blank(chars, i, n)
                return
            pos = c_end + 1


def _mask_html_comments(chars: list) -> None:
    """``<!-- ... -->`` 整块遮罩；未闭合则到文末。"""
    s = "".join(chars)
    i = 0
    while True:
        start = s.find("<!--", i)
        if start < 0:
            return
        close = s.find("-->", start + 4)
        end = len(s) if close < 0 else close + 3
        _blank(chars, start, end)
        i = end


def _mask_inline_code(chars: list) -> None:
    """行内代码：反引号串长度相等的闭合串，允许跨行。

    未闭合的反引号不遮：宁可漏遮一条，也不吞掉后文。
    """
    s = "".join(chars)
    i, n = 0, len(s)
    while i < n:
        if s[i] != "`":
            i += 1
            continue
        j = i
        while j < n and s[j] == "`":
            j += 1
        run = j - i
        k = j
        close_end = -1
        while k < n:
            if s[k] == "`":
                m = k
                while m < n and s[m] == "`":
                    m += 1
                if m - k == run:
                    close_end = m
                    break
                k = m
            else:
                k += 1
        if close_end < 0:
            i = j
            continue
        _blank(chars, i, close_end)
        s = "".join(chars)
        i = close_end


def _mask_link_targets(chars: list) -> None:
    """``](...)`` 的目标部分遮罩，保留链接文字与两侧括号。

    圆括号可嵌套（URL 里出现括号）；未闭合的目标不遮。
    """
    s = "".join(chars)
    i = 0
    while True:
        marker = s.find("](", i)
        if marker < 0:
            return
        start = marker + 2
        depth = 1
        k = start
        while k < len(s) and depth > 0:
            c = s[k]
            if c == "\\" and k + 1 < len(s):
                k += 2
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            k += 1
        if depth > 0:
            return
        _blank(chars, start, k - 1)       # 不含右括号
        s = "".join(chars)
        i = k


def _mask_table_rows(chars: list) -> None:
    """以 ``|`` 开头的整行遮罩（允许最多 3 个空格缩进）。"""
    s = "".join(chars)
    for start, end, line in _lines(s):
        if re.match(r"^[ \t]{0,3}\|", line):
            _blank(chars, start, end)


def _headings_of(chars: list) -> list[dict]:
    """从遮罩后的文本识别标题行；标题文字取遮罩后的原文（URL/代码已空白）。

    返回的 ``end_line`` 是标题自身行号：标题行在 prose 中整行遮罩后，
    ``_first_sentence_span_after`` 从该行行首开始找得到的第一句就是正文首句。
    """
    masked = "".join(chars)
    out: list[dict] = []
    for start, end, line in _lines(masked):
        m = _HEADING_LINE_RE.match(line)
        if not m:
            continue
        title = m.group(2)
        title = re.sub(r"[ \t]+#+[ \t]*$", "", title).strip()
        if not title:
            continue
        line_no = masked.count("\n", 0, start) + 1
        out.append({
            "cmd": "h%d" % len(m.group(1)),
            "title": title,
            "start": start,
            "end": end,
            "line": line_no,
            "end_line": line_no,
            "format": "markdown",
        })
        _blank(chars, start, end)
    return out


def scan_markdown(text: str) -> ScanResult:
    """解析一段 Markdown：返回等长遮罩的 prose 与标题清单。"""
    chars = list(text)
    _mask_front_matter(chars)
    _mask_fences_stable(chars)
    _mask_html_comments(chars)
    _mask_inline_code(chars)
    _mask_link_targets(chars)
    _mask_table_rows(chars)
    headings = _headings_of(chars)
    return ScanResult("".join(chars), headings)


def scan_plain(text: str) -> ScanResult:
    """纯文本：不遮罩、无标题（句级规则照跑）。"""
    return ScanResult(text, [])
