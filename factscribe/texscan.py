# -*- coding: utf-8 -*-
"""TeX 遮罩、scan_tex 与数字抽取。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .facts import THIN, _NUM_RE, number_key

# --------------------------------------------------------------------------
# LaTeX 扫描：注释、命令名、结构参数、\fact{} 绑定
# --------------------------------------------------------------------------

# 命令 -> 要吞掉的必选参数（{...}）个数
_SKIP_ARGS = {
    "cite": 1, "citep": 1, "citet": 1, "citealp": 1, "citealt": 1,
    "citeauthor": 1, "citeyear": 1, "Cite": 1, "Citep": 1, "Citet": 1,
    "nocite": 1,
    "ref": 1, "eqref": 1, "pageref": 1, "autoref": 1, "cref": 1, "Cref": 1,
    "nameref": 1, "vref": 1,
    "label": 1, "input": 1, "include": 1, "includeonly": 1, "subfile": 1,
    "includegraphics": 1,
    "begin": 2, "end": 2,                 # \begin{tabular}{p{2cm}l}
    "bibitem": 1, "bibliography": 1, "bibliographystyle": 1,
    "addbibresource": 1,
    "documentclass": 1, "usepackage": 1, "RequirePackage": 1,
    "url": 1, "href": 2,
    "setlength": 2, "addtolength": 2, "setcounter": 2,
    "hspace": 1, "vspace": 1, "rule": 2, "raisebox": 2,
    "graphicspath": 1, "linespread": 1,
    "multicolumn": 2, "multirow": 2,
    "newcommand": 2, "renewcommand": 2, "providecommand": 2,
    "color": 1, "textcolor": 2, "resizebox": 2, "scalebox": 1,
    "fontsize": 2, "setmainfont": 1, "setCJKmainfont": 1,
}

_CMD_RE = re.compile(r"\\([A-Za-z]+[0-9]*)(\*?)")
_WIKI_FACT_RE = re.compile(r"\[\[\s*fact\s*:\s*([^\]]+?)\s*\]\]")

# 引用命令：任何名字里带 cite 的命令都算「引用家族」（红队 B2 的 fail-closed）。
# - 已知合法：照常抽 key；
# - 明确不是 key 的排版命令：忽略；
# - 其余未知的 *cite* 命令：判红，不许静默放行。
_CITE_IGNORE = {"citestyle", "citetext", "bibcite", "citeindextrue", "citeindexfalse"}
_CITE_KNOWN = {
    "cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear",
    "citenum", "cites", "nocite", "upcite", "parencite", "textcite", "autocite",
    "footcite", "fullcite", "smartcite", "supercite", "notecite", "citeurl",
    "citefield", "citetitle", "citedate", "citejournal", "citelist",
}
_CITE_RE = re.compile(
    r"\\([A-Za-z]*[Cc]ite[A-Za-z]*)\*?((?:\s*\[[^\]]*\])*)\s*\{([^}]*)\}")
_FIGURE_RE = re.compile(r"\\includegraphics\*?(?:\s*\[[^\]]*\])*\s*\{([^}]*)\}")
_BIBRES_RE = re.compile(r"\\(?:bibliography|addbibresource)\s*\{([^}]*)\}")

# 整体跳过的环境：verbatim 里的 % 不是注释（红队 B3）；pkignore 是显式豁免区。
_SKIP_ENVS = r"(?:verbatim\*?|Verbatim|lstlisting|minted|comment\*?|pkignore)"
_SKIP_ENV_RE = re.compile(
    r"\\begin\{(%s)\}.*?\\end\{\1\}" % _SKIP_ENVS, re.S)
_VERB_RE = re.compile(r"\\verb\*?([^A-Za-z\s])")


def _blank(chars: list, start: int, stop: int) -> None:
    """把 [start, stop) 抹成空格，保留换行（保证行列号不漂）。"""
    stop = min(stop, len(chars))
    for i in range(start, stop):
        if chars[i] != "\n":
            chars[i] = " "


def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t\r\n":
        i += 1
    return i


def _balanced(s: str, start: int, opener: str, closer: str) -> int:
    """s[start] == opener；返回配对 closer 之后的位置（找不到则到串尾）。"""
    depth = 0
    i = start
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(s)


def _line_of(s: str, pos: int) -> int:
    return s.count("\n", 0, pos) + 1


# 写作批注宏（v1.1）：内容是作者给作者的问题，不是正文命题。
# 抽数字前整块剥离（连同参数），不参与审计，只计数上报。
_ANNOTATION_CMDS = ("todoq", "todo", "pkignore", "pknote", "fixme", "note", "tbd")


def _mask_envs_and_verb(tex: str) -> tuple[list, list[tuple[str, int]]]:
    """第一刀：verbatim/verb/pkignore 整块与写作批注宏抹掉（在剥注释之前）。

    返回 (chars, annotations)，annotations 是 [(宏名, 行号)]，供审计报告单列
    「已跳过 N 处批注」——跳过不等于放行，必须让人看见跳了多少。
    """
    chars = list(tex)
    annotations: list[tuple[str, int]] = []
    for m in _SKIP_ENV_RE.finditer(tex):
        _blank(chars, m.start(), m.end())
    # \verb|...|（同一行内，分隔符为任意非字母非空白字符）；在环境掩码之后做，
    # 免得 verbatim 内容里的 \verb 把范围抹歪。
    s = "".join(chars)
    for m in _VERB_RE.finditer(s):
        delim = m.group(1)
        end = s.find(delim, m.end())
        if end < 0:
            end = s.find("\n", m.end())
            end = len(s) if end < 0 else end
        else:
            end += 1
        _blank(chars, m.start(), end)
    # \pkignore{...} / \todoq{...} / \todo[...]{...}：整条批注连同参数抹成空白。
    # 行号用抹除前的文本算（结构未被改动前的位置）。
    s = "".join(chars)
    ann_re = re.compile(r"\\(%s)\b" % "|".join(_ANNOTATION_CMDS))
    for m in ann_re.finditer(s):
        # 注释里的批注不算（先剥注释做不到——verbatim 里的 % 不是注释）
        line_start = s.rfind("\n", 0, m.start()) + 1
        if re.search(r"(?<!\\)%", s[line_start:m.start()]):
            continue
        j = m.end()
        while True:
            k = _skip_ws(s, j)
            if k < len(s) and s[k] == "[":
                j = _balanced(s, k, "[", "]")
            else:
                break
        k = _skip_ws(s, j)
        if k < len(s) and s[k] == "{":
            end = _balanced(s, k, "{", "}")
        else:
            end = s.find("\n", m.end())
            end = len(s) if end < 0 else end
        annotations.append((m.group(1), _line_of(s, m.start())))
        _blank(chars, m.start(), end)
    return chars, annotations


def _mask_scripts(chars: list) -> None:
    """上下标是结构量：R^2 / x_{12} / a_1 里的数字不算命题（红队 C1）。"""
    s = "".join(chars)
    for m in re.finditer(r"[\^_]\s*", s):
        j = m.end()
        if j < len(s) and s[j] == "{":
            end = _balanced(s, j, "{", "}")
        elif j < len(s) and s[j].isalnum():
            end = j + 1
        else:
            continue
        _blank(chars, m.start(), end)


@dataclass
class ScanResult:
    masked: str                     # 抹掉注释/命令/参数后的正文
    bindings: dict[int, list[str]]  # 行号 -> [fact id]
    markers: list[tuple[str, int]]  # (fact id, 行号)
    cites: list[tuple[str, int, int]]  # (key, 行号, 列)
    unknown_cites: list[tuple[str, int, int]] = field(default_factory=list)
    bib_files: list[str] = field(default_factory=list)
    figures: list[tuple[str, int]] = field(default_factory=list)
    annotations: list[tuple[str, int]] = field(default_factory=list)  # (宏名, 行号)


def scan_tex(tex: str) -> ScanResult:
    # ---- pass 1a：verbatim/verb/批注宏整块跳过 ----
    masked, annotations = _mask_envs_and_verb(tex)

    # ---- pass 1b：{,} 当千分位哨兵（数学里 1{,}024） ----
    s0 = "".join(masked)
    for m in re.finditer(r"\{,\}", s0):
        for k in range(m.start(), m.end()):
            masked[k] = THIN

    # ---- pass 1c：注释与转义（唯一顺序：\% 不是注释；~ / \, 是千分位哨兵） ----
    i, n = 0, len(s0)
    while i < n:
        c = s0[i]
        if c == "\\":
            nxt = s0[i + 1] if i + 1 < n else ""
            if nxt == "%":
                masked[i], masked[i + 1] = "%", " "   # 10\% -> "10 %"
                i += 2
                continue
            if nxt in "$&#_{}":
                masked[i], masked[i + 1] = " ", nxt
                i += 2
                continue
            if nxt in ",;:!~":
                if nxt == "~":
                    masked[i], masked[i + 1] = " ", " "
                else:
                    masked[i], masked[i + 1] = THIN, THIN
                i += 2
                continue
            if nxt in " \t":
                masked[i], masked[i + 1] = THIN, THIN
                i += 2
                continue
            i += 2
            continue
        if c == "~":
            masked[i] = THIN
            i += 1
            continue
        if c == "%":
            while i < n and s0[i] != "\n":
                masked[i] = " "
                i += 1
            continue
        i += 1

    s = "".join(masked)

    # ---- pass 2：引用 / 图 / bib 文件（在参数被抹掉之前）----
    cites: list[tuple[str, int, int]] = []
    unknown_cites: list[tuple[str, int, int]] = []
    for m in _CITE_RE.finditer(s):
        name = m.group(1)
        lname = name.lower()
        if lname in _CITE_IGNORE:
            continue
        keys = [(km.start(), km.group(0)) for km in re.finditer(r"[^,\s]+", m.group(3))]
        if lname not in _CITE_KNOWN:
            line = _line_of(s, m.start())
            col = m.start() - s.rfind("\n", 0, m.start())
            unknown_cites.append((name, line, col))
        if lname == "nocite":
            # \nocite{*} = 整库；具体 key 仍要核
            pass
        for off, key in keys:
            if key == "*":
                continue
            offset = m.start(3) + off
            line = _line_of(s, offset)
            col = offset - s.rfind("\n", 0, offset)
            cites.append((key, line, col))

    figures: list[tuple[str, int]] = []
    for m in _FIGURE_RE.finditer(s):
        figures.append((m.group(1).strip(), _line_of(s, m.start())))

    bib_files: list[str] = []
    for m in _BIBRES_RE.finditer(s):
        for part in m.group(1).split(","):
            part = part.strip()
            if part:
                if part.lower().endswith(".bib") or "\\" not in part:
                    bib_files.append(part if part.lower().endswith(".bib") else part + ".bib")

    # ---- pass 3：上下标 ----
    _mask_scripts(masked)
    s = "".join(masked)

    # ---- pass 4：命令名与结构参数 ----
    out = list(s)
    bindings: dict[int, list[str]] = {}
    markers: list[tuple[str, int]] = []
    pos = 0
    while True:
        m = _CMD_RE.search(s, pos)
        if not m:
            break
        name = m.group(1)
        j = m.end()
        while True:
            k = _skip_ws(s, j)
            if k < len(s) and s[k] == "[":
                j = _balanced(s, k, "[", "]")
            else:
                break
            # 只吞一层可选项；再往后若还是 '[' 继续吞（如 \cite[a][b]{k}）
        if name == "fact":
            k = _skip_ws(s, j)
            if k < len(s) and s[k] == "{":
                end = _balanced(s, k, "{", "}")
                ids = [x.strip() for x in s[k + 1:end - 1].split(",") if x.strip()]
                line = _line_of(s, k)
                for fid in ids:
                    bindings.setdefault(line, []).append(fid)
                    markers.append((fid, line))
                _blank(out, m.start(), end)
                pos = end
                continue
        # 引用家族（含未知 *cite*）：命令名 + 可选参数 + key 参数整段吞掉
        if "cite" in name.lower():
            k = _skip_ws(s, j)
            if k < len(s) and s[k] == "{":
                end = _balanced(s, k, "{", "}")
                _blank(out, m.start(), end)
                pos = end
                continue
        count = _SKIP_ARGS.get(name, 0)
        if count:
            j2 = j
            for _ in range(count):
                k = _skip_ws(s, j2)
                if k < len(s) and s[k] == "{":
                    j2 = _balanced(s, k, "{", "}")
                else:
                    break
            _blank(out, m.start(), j2)
            pos = max(j2, m.end())
            continue
        # 普通命令：只抹命令名本身（吃掉 \foo2 里的数字）
        _blank(out, m.start(), m.end())
        pos = m.end()

    masked2 = "".join(out)

    # ---- pass 5：[[fact:A1]] 形式 ----
    chars = list(masked2)
    for m in _WIKI_FACT_RE.finditer(masked2):
        ids = [x.strip() for x in m.group(1).split(",") if x.strip()]
        line = _line_of(masked2, m.start())
        for fid in ids:
            bindings.setdefault(line, []).append(fid)
            markers.append((fid, line))
        _blank(chars, m.start(), m.end())
    masked2 = "".join(chars)

    return ScanResult(masked=masked2, bindings=bindings, markers=markers,
                      cites=cites, unknown_cites=unknown_cites,
                      bib_files=bib_files, figures=figures,
                      annotations=annotations)

def _extract_numbers(masked: str, original: str) -> list[dict]:
    orig_lines = original.split("\n")
    out = []
    for ln, line in enumerate(masked.split("\n"), 1):
        toks: list[dict] = []
        for m in _NUM_RE.finditer(line):
            raw, suffix, pct = m.group(1), m.group(2) or "", bool(m.group(3))
            item = {
                "raw": raw,
                "suffix": suffix,
                "pct": pct,
                "key": number_key(raw, suffix or None, pct),
                "line": ln,
                "col": m.start(1) + 1,
                "end": m.end(),
                "text": orig_lines[ln - 1].strip() if ln - 1 < len(orig_lines) else "",
            }
            # 千分位合并：1<THIN>000<THIN>000 -> 1000000（只合并 3 位整数段）
            if toks:
                prev = toks[-1]
                gap = line[prev["end"]:m.start(1)]
                if (gap and set(gap) <= {THIN}
                        and not prev["suffix"] and not prev["pct"]
                        and not suffix and not pct
                        and re.fullmatch(r"\d{3}", raw)):
                    prev["raw"] += raw
                    prev["end"] = m.end()
                    prev["key"] = number_key(prev["raw"])
                    continue
            toks.append(item)
        for it in toks:
            out.append({
                "token": it["raw"] + it["suffix"] + ("%" if it["pct"] else ""),
                "key": it["key"],
                "line": it["line"],
                "col": it["col"],
                "text": it["text"],
            })
    return out
