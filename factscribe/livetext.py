# -*- coding: utf-8 -*-
"""源层「断言是否真的活在正文里」判据（SPEC-V3.0 S-03）。

三条通用规则，不认项目名、不认路径：

1. 定量事实在活跃正文里没有任何 `\\fact{}` 标记
   → `APPROVAL_MISSING_ASSERTIONS`（没有断言可签）＋ `ASSERTION_DRIFT`（签过的断言不在正文）。
   「活跃正文」＝去掉注释、宏定义体、被丢弃的宏参数、`\\iffalse` 块之后的文本。
   宏定义体与 `\\newcommand{\\ignore}[1]{}` 的参数都不会被渲染，写在那里的
   标记等于没写（宏藏数 / 忽略宏包住结论 / 无标记定量句）。
2. 标记活着，但所在句子里连一个数字都没有，且标记没自带 `\\fact{ID}{值}`
   的第二参数 → 这句话没有断言任何定量值（计数器/表达式算出来的数不在
   源文本里）→ `ASSERTION_DRIFT`。
3. 事实声明了正文角色（role ∈ 正文节），而它的标记只出现在 `\\appendix`
   之后 → 角色变了（正文结论被搬进附录）→ `ASSERTION_DRIFT`。
"""
from __future__ import annotations

import re

from .audit import Issue
from .facts import fact_value_keys
from .v3 import _balanced

BODY_ROLES = {"abstract", "introduction", "methods", "results", "discussion",
              "conclusion", "background", "related", "analysis"}

_DEF_RE = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand)\*?\s*"
    r"(?:\{\s*\\([A-Za-z@]+)\s*\}|\\\\([A-Za-z@]+))\s*"
    r"(?:\[(\d)\])?\s*(?:\[[^\]]*\])?\s*\{")
_FACT_RE = re.compile(r"\\fact\s*\{([^{}]*)\}")
_IFFALSE_RE = re.compile(r"\\iffalse\b.*?\\fi\b", re.S)
_SENTENCE_END = re.compile(r"[.!?。！？]")


def _blank(chars: list, start: int, stop: int) -> None:
    for i in range(max(0, start), min(stop, len(chars))):
        if chars[i] != "\n":
            chars[i] = " "


def _strip_comments(tex: str) -> str:
    """去掉 TeX 注释（`\\%` 不是注释），保留换行。"""
    out: list[str] = []
    i, n = 0, len(tex)
    while i < n:
        c = tex[i]
        if c == "\\" and i + 1 < n:
            out.append(tex[i:i + 2])
            i += 2
            continue
        if c == "%":
            while i < n and tex[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _macro_definitions(tex: str) -> list[dict]:
    """`\\newcommand` 家族的定义体：名字、参数个数、体文本、覆盖区间。"""
    out: list[dict] = []
    for m in _DEF_RE.finditer(tex):
        name = m.group(1) or m.group(2) or ""
        arity = int(m.group(3) or 0)
        body_start = m.end() - 1
        body_end = _balanced(tex, body_start)
        out.append({"name": name, "arity": arity,
                    "body": tex[body_start + 1:body_end - 1],
                    "start": m.start(), "end": body_end})
    return out


def _live_text(tex: str) -> tuple[str, list[dict]]:
    """活跃正文：抹掉宏定义体、被丢弃的宏参数、`\\iffalse` 块。

    返回 (活跃文本, 宏定义列表)。活跃文本保留原长度（空白替换），
    所以标记的位置/行号在原文里仍然有效。
    """
    text = _strip_comments(tex)
    chars = list(text)
    defs = _macro_definitions(text)
    for d in defs:
        _blank(chars, d["start"], d["end"])
    # 参数被丢弃的宏（`\\newcommand{\\ignore}[1]{}`）：调用点的参数也不渲染。
    for d in defs:
        used = {int(k) for k in re.findall(r"#(\d)", d["body"])}
        missing = [p for p in range(1, d["arity"] + 1) if p not in used]
        if not missing:
            continue
        call_re = re.compile(r"\\%s\b" % re.escape(d["name"]))
        for m in call_re.finditer("".join(chars)):
            j = m.end()
            for param in range(1, d["arity"] + 1):
                k = j
                while k < len(chars) and chars[k] in " \t\r\n":
                    k += 1
                if k < len(chars) and chars[k] == "{":
                    end = _balanced("".join(chars), k)
                else:
                    break
                if param in missing:
                    _blank(chars, k, end)
                j = end
    for m in _IFFALSE_RE.finditer(text):
        _blank(chars, m.start(), m.end())
    return "".join(chars), defs


def _live_markers(tex: str) -> tuple[str, list[dict]]:
    live, _defs = _live_text(tex)
    out: list[dict] = []
    for m in _FACT_RE.finditer(live):
        ids = [x.strip() for x in m.group(1).split(",") if x.strip()]
        has_value = False
        k = m.end()
        while k < len(live) and live[k] in " \t":
            k += 1
        if k < len(live) and live[k] == "{":
            has_value = True
        out.append({"ids": ids, "pos": m.start(), "has_value": has_value})
    return live, out


def _sentence_of(tex: str, pos: int) -> str:
    """标记所在句子的文本（向前后各找到句末标点或空行）。"""
    head = max(tex.rfind("\n\n", 0, pos), tex.rfind(". ", 0, pos),
               tex.rfind("。", 0, pos))
    start = 0 if head < 0 else head + 1
    m = _SENTENCE_END.search(tex, pos)
    end = m.end() if m else len(tex)
    return tex[start:end]


def live_text_issues(cfg, facts, sections) -> list[Issue]:
    """三条源层「断言活着吗」判据；只对 V3 项目生效。"""
    if not cfg.is_v3:
        return []
    out: list[Issue] = []
    # 每条 fact 的活跃标记：[(rel, pos, has_value)]
    live: dict[str, list[tuple[str, int, bool]]] = {}
    live_sentences: dict[str, list[str]] = {}
    appendix_line: dict[str, int] = {}
    for rel, text in sections:
        stripped = _strip_comments(text)
        app = re.search(r"\\appendix\b", stripped)
        appendix_line[rel] = (stripped.count("\n", 0, app.start()) + 1) if app else 0
        live_tex, marks = _live_markers(text)
        for m in marks:
            line = stripped.count("\n", 0, m["pos"]) + 1
            for fid in m["ids"]:
                live.setdefault(fid, []).append((rel, line, m["has_value"]))
                # 句子里的 \fact{} 标记本身不含值（A1 的 1 不是数字断言）。
                sentence = _FACT_RE.sub(" ", _sentence_of(live_tex, m["pos"]))
                live_sentences.setdefault(fid, []).append(sentence)

    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        marks = live.get(f.id, [])
        if not marks:
            if f.quantitative or f.value.strip():
                out.append(Issue(
                    "APPROVAL_MISSING_ASSERTIONS",
                    "fact %r 有定量值 %r，但活跃正文里没有任何 \\fact{%s} 标记——"
                    "没有断言可签（宏定义体/被丢弃的宏参数/附录外都算没写）"
                    % (f.id, f.value, f.id), location=loc, token=f.id))
                out.append(Issue(
                    "ASSERTION_DRIFT",
                    "fact %r 的定量断言不在活跃正文里（标记缺失或只出现在不会渲染的位置）"
                    % f.id, location=loc, token=f.id))
            continue

        # 规则 2：标记活着，但句子里没有任何数字，也没有 \\fact{ID}{值} 的第二参数。
        if f.quantitative and not any(has_value for _rel, _line, has_value in marks):
            sentences = live_sentences.get(f.id, [])
            if sentences and not any(fact_value_keys(s) for s in sentences):
                out.append(Issue(
                    "ASSERTION_DRIFT",
                    "fact %r 的标记所在句子没有任何数字——定量值不是源文本字面量"
                    "（计数器/表达式算出来的数无法核对）" % f.id,
                    location=loc, token=f.id))

        # 规则 3：正文角色的事实，标记只在 \\appendix 之后出现。
        role = (f.role or "").strip().lower()
        if role in BODY_ROLES:
            body_marks = [rel for rel, line, _v in marks
                          if not appendix_line.get(rel) or line < appendix_line[rel]]
            if not body_marks:
                out.append(Issue(
                    "ASSERTION_DRIFT",
                    "fact %r 声明 role=%r，但标记只在 \\appendix 之后出现——"
                    "结论被搬进附录，正文角色对不上（S-03）" % (f.id, f.role),
                    location=loc, token=f.id))
    return out
