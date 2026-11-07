#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FactScribe（原 paperkit）—— 论文数字与引用的机械闸门（v1）。

纯标准库；Python >= 3.10。
子命令：check / audit / matrix / build / preamble，全部支持 --json。

设计口径见同目录 SPEC-V1.md。核心一句话：
正文里的每一个数字必须**内联绑定**到一条 fact（``\\fact{A2}``），并且这个数字
必须是该 fact.value 里的 token；数字与引用都要能被 ``source_sha256`` /
人签清单锁死的原始产物回查。绿＝「有账、账有据、据未被改」，不是「真」。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

VERSION = "1.1.0"
SCHEMA_VERSION = "1.0"

CONFIDENCE_OK = {"high", "med", "low"}
KINDS_OK = {"claim", "config"}

# 退出码分层（SPEC-V1 §5）
EXIT_OK = 0        # 绿：完整覆盖且无红无黄
EXIT_RED = 1       # 红：违例（编造/不自洽/账坏）
EXIT_CONFIG = 2    # 配置或用法错（工具没跑起来）
EXIT_YELLOW = 3    # 黄：跑完了但有「未核验/未绑定/未签名/冲突」，不判死但必须列
EXIT_INTERNAL = 4  # 工具内部错误（异常）

SEV_RED = "red"
SEV_YELLOW = "yellow"
SEV_INFO = "info"


# --------------------------------------------------------------------------
# TOML 读写（3.11+ 用 tomllib；3.10 用内置极简解析器兜底）
# --------------------------------------------------------------------------

try:  # pragma: no cover - 解释器相关
    import tomllib as _tomllib
except ModuleNotFoundError:  # pragma: no cover
    _tomllib = None


class ConfigError(Exception):
    """配置/用法层面的错误 -> 退出码 2。"""


def _strip_toml_comment(line: str) -> str:
    out = []
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            out.append(c)
            if c == "\\" and quote == '"' and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        else:
            if c in "\"'":
                quote = c
                out.append(c)
            elif c == "#":
                break
            else:
                out.append(c)
        i += 1
    return "".join(out)


def _mini_toml_value(raw: str):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    if raw.startswith("[") and raw.endswith("]"):
        body = raw[1:-1]
        items, buf, quote = [], [], None
        for c in body:
            if quote:
                buf.append(c)
                if c == quote:
                    quote = None
            elif c in "\"'":
                quote = c
                buf.append(c)
            elif c == ",":
                items.append("".join(buf))
                buf = []
            else:
                buf.append(c)
        if "".join(buf).strip():
            items.append("".join(buf))
        return [_mini_toml_value(x) for x in items if x.strip()]
    try:
        if any(ch in raw for ch in ".eE") and not raw.startswith("0x"):
            return float(raw)
        return int(raw)
    except ValueError:
        return raw  # 裸词，容错


def _needs_more(value: str) -> bool:
    depth = 0
    quote = None
    for c in value:
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
    return depth > 0


def _mini_toml(text: str) -> dict:
    """只覆盖 paperkit 契约用得到的子集：表、表数组、字符串、数组、数字、布尔。"""
    root: dict = {}
    cur: dict = root
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        s = _strip_toml_comment(raw).strip()
        if not s:
            continue
        if s.startswith("[[") and s.endswith("]]"):
            name = s[2:-2].strip()
            arr = root.setdefault(name, [])
            if not isinstance(arr, list):
                raise ValueError("[[%s]] 与同名表冲突" % name)
            cur = {}
            arr.append(cur)
            continue
        if s.startswith("[") and s.endswith("]"):
            name = s[1:-1].strip()
            tbl = root.setdefault(name, {})
            if not isinstance(tbl, dict):
                raise ValueError("[%s] 与同名表数组冲突" % name)
            cur = tbl
            continue
        if "=" not in s:
            raise ValueError("无法解析的 TOML 行：%r" % raw)
        key, value = s.split("=", 1)
        value = value.strip()
        while _needs_more(value) and i < len(lines):
            value += " " + _strip_toml_comment(lines[i]).strip()
            i += 1
        cur[key.strip().strip("\"'")] = _mini_toml_value(value)
    return root


def load_toml(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError("读不了 %s：%s" % (path, exc))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError("%s 不是合法 UTF-8：%s" % (path, exc))
    try:
        if _tomllib is not None:
            return _tomllib.loads(text)
        return _mini_toml(text)
    except (ValueError, Exception) as exc:  # tomllib.TOMLDecodeError 是 ValueError 子类
        raise ConfigError("TOML 解析失败 %s：%s" % (path, exc))


# --------------------------------------------------------------------------
# 数字归一化
# --------------------------------------------------------------------------

# 匹配一个“数字 + 可选量级/单位后缀 + 可选百分号”。
# - 前面不能紧跟字母/下划线/点：避开 ctex2017、v2.0、R2、H2O 这类；
# - 量级后缀必须紧贴数字（k/K/M/B），避免把 "47.3 ms" 读成 47.3 毫
# - 单位后缀（v1.1）：131s / 2220s / 53000token / 5GB 都是「数字＋量纲」，
#   数字照抽，单位只作噪声（不参与数值换算）。长单位排在短单位前，避免
#   "ms" 被 "m"、"tokens" 被 "tok" 抢先；量级 [kKMB] 排在单位之后，
#   所以 "5MB" 是单位、"5M" 仍是量级。
# - 百分号允许中间有空格（\% 掩码后就是 " %"），也接受 percent/pct 英文词
# - 科学计数法整体成 token（3e-4 / 1.2E+05），不拆成 3 和 4
# *** 匹配是 token 锚定的：不做子串匹配（红队 B1）***
_UNIT_RE = (
    r"(?:tokens|token|toks|tok|mins|min|ms|secs|sec|hrs|hr|"
    r"GiB|MiB|KiB|TiB|GB|MB|KB|TB|"
    r"x|×|s|h)"
)
_NUM_RE = re.compile(
    r"(?<![\w.])"
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"(" + _UNIT_RE + r"|[kKMB])?"
    r"(\s*(?:%|percent\b|pct\b))?"
    r"(?![\w])"
)

_MAGNITUDE = {"k": Decimal(1000), "m": Decimal(10 ** 6), "b": Decimal(10 ** 9)}

_FRACTION_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?![\d.])")

# LaTeX 的“千分位空格”：\, \; \: \! \~ 与 ~ 与 {,}。扫面时保留成长度不变的
# 哨兵字符，抽数字时据此把 "1 000 000" 合并成 1000000（红队 C4）。
THIN = "\x01"


def _num_key(d: Decimal) -> str:
    """把 Decimal 收敛成比较用的规范串：1234 / 0.9 / 0.625 / 53000 / 3500000。"""
    try:
        d = d.normalize()
    except InvalidOperation:
        return str(d)
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("", "-", "-0"):
        s = "0"
    return s


def number_key(token: str, suffix: str | None = None, percent: bool = False) -> str:
    try:
        d = Decimal(str(token).replace(",", ""))
    except InvalidOperation:
        return token
    if suffix:
        # 只有量级后缀换算数值；s / token / GB 这类单位只表示量纲，不换算。
        mag = _MAGNITUDE.get(suffix.lower())
        if mag is not None:
            d = d * mag
    if percent:
        d = d / Decimal(100)
    return _num_key(d)


def literal_tokens(value: str) -> list[tuple[str, str, bool]]:
    """value 里字面写出的数字 token：(raw, suffix, pct)。不做分数展开。"""
    out = []
    for m in _NUM_RE.finditer(str(value or "")):
        out.append((m.group(1), m.group(2) or "", bool(m.group(3))))
    return out


def fact_value_keys(value: str, include_quotient: bool = True) -> set[str]:
    """一个 fact.value 能接受的全部规范数字。

    除了字面数字，还接受：
    - 分数 a/b 的商（10/16 -> 0.625），并按 0~4 位小数放宽四舍五入；
    - 区间 10--16 的两端（NUM_RE 天然拆成两个）；
    - 百分号形式的裸数字（62.5% 同时接受 62.5）。

    注意：这是**值域**；v1 里它只有在内联绑定（\\fact{ID}）的语境下才算核销，
    全局裸数字命中只算黄（UNBOUND_NUMBER），不再能换来绿（红队 B1/C6/C11）。
    """
    keys: set[str] = set()
    for raw, suffix, pct in literal_tokens(value):
        keys.add(number_key(raw, suffix, pct))
        if pct:
            keys.add(number_key(raw, suffix, False))
    if include_quotient:
        for m in _FRACTION_RE.finditer(str(value or "")):
            try:
                num, den = Decimal(m.group(1)), Decimal(m.group(2))
            except InvalidOperation:
                continue
            if den == 0:
                continue
            q = num / den
            keys.add(_num_key(q))
            for places in range(0, 5):
                try:
                    keys.add(_num_key(q.quantize(Decimal(1).scaleb(-places))))
                except InvalidOperation:
                    pass
    return keys


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


# --------------------------------------------------------------------------
# 项目 / facts / 正文 读取
# --------------------------------------------------------------------------

@dataclass
class Config:
    root: Path
    title: str = ""
    authors: list = field(default_factory=list)
    sections_glob: str = "sections/*.tex"
    facts_glob: str = "facts/*.toml"
    bib: str = "refs.bib"
    build: str = ""
    manifest: str = "results/MANIFEST.toml"
    source_root: str = ""        # source 的解析根；空＝只许项目内 results/


@dataclass
class Fact:
    id: str
    claim: str = ""
    value: str = ""
    source: str = ""
    source_sha256: str = ""
    locator: str = ""
    confidence: str = ""
    kind: str = "claim"          # claim | config
    derived_from: list = field(default_factory=list)
    supersedes: list = field(default_factory=list)
    expr: str = ""
    metric: str = ""
    scope: str = ""
    note: str = ""
    file: str = ""
    line: int = 0
    value_keys: set = field(default_factory=set)

    @property
    def id_key(self) -> str:
        return self.id.strip().casefold()

    @property
    def is_derived(self) -> bool:
        return bool(self.derived_from) or bool(self.expr)


def load_config(root: Path) -> Config:
    path = root / "factscribe.toml"
    if not path.is_file():
        path = root / "paperkit.toml"
    if not path.is_file():
        raise ConfigError("找不到项目声明 %s（缺 paperkit.toml 不敢跑）" % path)
    data = load_toml(path)
    proj = data.get("project")
    if not isinstance(proj, dict):
        raise ConfigError("%s 缺少 [project] 段" % path)
    for key in ("sections", "facts"):
        if not proj.get(key):
            raise ConfigError("%s 缺少 project.%s" % (path, key))
    authors = proj.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    return Config(
        root=root,
        title=str(proj.get("title") or ""),
        authors=[str(a) for a in authors],
        sections_glob=str(proj["sections"]),
        facts_glob=str(proj["facts"]),
        bib=str(proj.get("bib") or "refs.bib"),
        build=str(proj.get("build") or ""),
        manifest=str(proj.get("manifest") or "results/MANIFEST.toml"),
        source_root=str(proj.get("source_root") or ""),
    )


def _locate_id_line(path: Path, fid: str) -> int:
    pat = re.compile(r"""^\s*id\s*=\s*["']%s["']""" % re.escape(fid))
    try:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pat.match(line):
                return i
    except OSError:
        pass
    return 0


def load_facts(cfg: Config) -> list[Fact]:
    files = sorted(p for p in cfg.root.glob(cfg.facts_glob) if p.is_file())
    facts: list[Fact] = []
    for path in files:
        data = load_toml(path)
        entries = data.get("fact")
        if entries is None:
            continue
        if not isinstance(entries, list):
            raise ConfigError("%s 里 fact 必须是 [[fact]] 表数组" % path)
        for raw in entries:
            if not isinstance(raw, dict):
                raise ConfigError("%s 里有一条 fact 不是表" % path)
            fid = str(raw.get("id") or "").strip()
            rel = path.relative_to(cfg.root).as_posix()
            f = Fact(
                id=fid,
                claim=str(raw.get("claim") or ""),
                value=str(raw.get("value") or ""),
                source=str(raw.get("source") or ""),
                source_sha256=str(raw.get("source_sha256") or "").strip().lower(),
                locator=str(raw.get("locator") or ""),
                confidence=str(raw.get("confidence") or ""),
                kind=str(raw.get("kind") or "claim"),
                derived_from=[str(x) for x in (raw.get("derived_from") or [])],
                supersedes=[str(x) for x in (raw.get("supersedes") or [])],
                expr=str(raw.get("expr") or "").strip(),
                metric=str(raw.get("metric") or ""),
                scope=str(raw.get("scope") or ""),
                note=str(raw.get("note") or ""),
                file=rel,
                line=_locate_id_line(path, fid),
            )
            if not f.id:
                raise ConfigError("%s 里有一条 fact 缺 id（不准匿名入账）" % path)
            f.value_keys = fact_value_keys(f.value)
            facts.append(f)
    return facts


def _glob_paths(root: Path, pattern: str) -> dict[str, Path]:
    """glob 默认递归：sections/*.tex 同时匹配 sections/**/*.tex（红队 B4）。"""
    pats = [pattern]
    if "**" not in pattern:
        d, sep, base = pattern.rpartition("/")
        if base:
            pats.append((d + "/**/" + base) if d else ("**/" + base))
    found: dict[str, Path] = {}
    for pat in pats:
        for p in root.glob(pat):
            if p.is_file():
                found[p.relative_to(root).as_posix()] = p
    return found


_INPUT_RE = re.compile(r"\\(?:input|include|subfile|import)\s*\{([^}]*)\}")
_SKIP_DIRS = {".git", ".venv", "__pycache__", "audit", "node_modules", ".pytest_cache"}


def _read_text(path: Path, root: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError("%s 不是合法 UTF-8：%s" % (path, exc))
    except OSError as exc:
        raise ConfigError("读不了 %s：%s" % (path, exc))


def load_sections(cfg: Config) -> list[tuple[str, str]]:
    """sections = glob 递归命中 + \\input/\\include/\\subfile 闭包（红队 B4）。"""
    found = _glob_paths(cfg.root, cfg.sections_glob)
    seen: dict[str, Path] = dict(found)
    queue: list[Path] = list(found.values())
    while queue:
        p = queue.pop(0)
        text = _read_text(p, cfg.root)
        for m in _INPUT_RE.finditer(text):
            ref = m.group(1).strip()
            if not ref or "\\" in ref or "#" in ref:
                continue
            for base_dir in (cfg.root, p.parent):
                for cand in (base_dir / ref, base_dir / (ref + ".tex")):
                    if not cand.is_file():
                        continue
                    try:
                        rel = cand.resolve().relative_to(cfg.root.resolve()).as_posix()
                    except ValueError:
                        continue
                    if rel not in seen:
                        seen[rel] = cand
                        queue.append(cand)
    out = []
    for rel in sorted(seen):
        out.append((rel, _read_text(seen[rel], cfg.root)))
    return out


def all_tex_files(cfg: Config) -> list[str]:
    """项目内全部 .tex（用于「闭包外文件是否从未被审计」的覆盖报告）。"""
    out = []
    for p in cfg.root.glob("**/*.tex"):
        if not p.is_file():
            continue
        parts = set(p.relative_to(cfg.root).parts)
        if parts & _SKIP_DIRS:
            continue
        out.append(p.relative_to(cfg.root).as_posix())
    return sorted(out)


def facts_digest(cfg: Config) -> str:
    """账本输入指纹：所有 facts 文件按路径排序后串哈希（红队 D7）。"""
    h = hashlib.sha256()
    for name, path in sorted(_glob_paths(cfg.root, cfg.facts_glob).items()):
        h.update(name.encode("utf-8"))
        h.update(path.read_bytes())
    return h.hexdigest()


def git_commit(root: Path) -> str:
    """尽力读 git 提交号；读不到就空串（不联网、不调 git 命令）。"""
    head = root / ".git" / "HEAD"
    try:
        raw = head.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if raw.startswith("ref:"):
        ref = raw.split(":", 1)[1].strip()
        try:
            return (root / ".git" / ref).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return raw


# --------------------------------------------------------------------------
# bib 解析
# --------------------------------------------------------------------------

_BIB_ENTRY_RE = re.compile(r"@([A-Za-z]+)\s*[{(]\s*([^,\s]+)\s*,")
_STRING_RE = re.compile(r"@string\s*[{(]\s*([A-Za-z][\w-]*)\s*=\s*(?:\{([^{}]*)\}|\"([^\"]*)\")",
                        re.I)
_URL_OK_TYPES = {"misc", "online", "software", "dataset", "unpublished",
                 "manual", "techreport", "webpage", "www"}
_ARXIV_NEW = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
_ARXIV_OLD = re.compile(r"^[a-z-]+(?:\.[A-Z]{2})?/\d{7}(v\d+)?$")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_URL_RE = re.compile(r"^https?://\S+$")


def valid_stable_id(name: str, value: str) -> bool:
    v = (value or "").strip()
    if name in ("arxiv", "eprint"):
        v = re.sub(r"^(arxiv:|https?://arxiv\.org/abs/)", "", v, flags=re.I)
        v = v.rstrip("/")
        return bool(_ARXIV_NEW.match(v) or _ARXIV_OLD.match(v))
    if name == "doi":
        v = re.sub(r"^(doi:|https?://(dx\.)?doi\.org/)", "", v, flags=re.I)
        return bool(_DOI_RE.match(v))
    if name == "url":
        return bool(_URL_RE.match(v))
    return False


@dataclass
class BibEntry:
    key: str
    kind: str
    file: str
    line: int
    fields: dict = field(default_factory=dict)
    inherited: set = field(default_factory=set)

    @property
    def stable_id(self):
        for name in ("arxiv", "eprint", "doi"):
            v = (self.fields.get(name) or "").strip()
            if v:
                return name, v
        if self.kind in _URL_OK_TYPES:
            v = (self.fields.get("url") or "").strip()
            if v:
                return "url", v
        return None, ""


def parse_bib(path: Path, root: Path) -> list[BibEntry]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError("读不了参考文献 %s：%s" % (path, exc))
    rel = path.relative_to(root).as_posix()
    macros = {}
    for sm in _STRING_RE.finditer(text):
        macros[sm.group(1).lower()] = " ".join((sm.group(2) or sm.group(3) or "").split())
    entries: list[BibEntry] = []
    for m in _BIB_ENTRY_RE.finditer(text):
        kind, key = m.group(1).lower(), m.group(2)
        if kind in ("comment", "string", "preamble"):
            continue
        body_start = m.end()
        depth = 1
        i = body_start
        while i < len(text) and depth > 0:
            c = text[i]
            if c == "\\":
                i += 2
                continue
            if c in "{(":
                depth += 1
            elif c in "})":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = text[body_start:i]
        fields = {}
        for fm in re.finditer(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body):
            name = fm.group(1).lower()
            j = fm.end()
            while j < len(body) and body[j] in " \t\r\n":
                j += 1
            if j < len(body) and body[j] == "{":
                end = _balanced(body, j, "{", "}")
                value = body[j + 1:end - 1]
            elif j < len(body) and body[j] == '"':
                end = body.find('"', j + 1)
                end = len(body) if end < 0 else end
                value = body[j + 1:end]
            else:
                vm = re.match(r"[^,\n]+", body[j:])
                value = vm.group(0) if vm else ""
            fields.setdefault(name, " ".join(value.split()))
        # @string 宏替换（红队 C8-C）
        for name, value in list(fields.items()):
            bare = value.strip()
            if bare and " " not in bare and bare.lower() in macros:
                fields[name] = macros[bare.lower()]
        entries.append(BibEntry(
            key=key, kind=kind, file=rel,
            line=text.count("\n", 0, m.start()) + 1, fields=fields,
        ))
    # crossref 一层继承（红队 C8-D）
    by_key = {e.key: e for e in entries}
    for e in entries:
        parent = (e.fields.get("crossref") or "").strip()
        if parent and parent in by_key:
            for name, value in by_key[parent].fields.items():
                if name not in e.fields:
                    e.fields[name] = value
                    e.inherited.add(name)
    return entries


def bib_duplicates(entries: list[BibEntry]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """返回 (重复 key 列表, [(稳定标识, [key...]), ...])。

    crossref 继承来的标识不参与「重复标识」判定：父子同 DOI 是 BibTeX 的正常用法。
    """
    keys: dict[str, int] = {}
    ids: dict[tuple[str, str], list[str]] = {}
    for e in entries:
        keys[e.key] = keys.get(e.key, 0) + 1
        name, value = e.stable_id
        if name and name not in e.inherited:
            ids.setdefault((name, value.lower()), []).append(e.key)
    dup_keys = sorted(k for k, n in keys.items() if n > 1)
    dup_ids = [(name + "=" + value, ks) for (name, value), ks in ids.items() if len(ks) > 1]
    return dup_keys, dup_ids


# --------------------------------------------------------------------------
# 问题单
# --------------------------------------------------------------------------

@dataclass
class Issue:
    code: str
    message: str
    location: str = ""
    token: str = ""
    context: str = ""
    severity: str = SEV_RED

    def as_dict(self) -> dict:
        d = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.location:
            d["location"] = self.location
        if self.token:
            d["token"] = self.token
        if self.context:
            d["context"] = self.context
        return d


# --------------------------------------------------------------------------
# 源头锚定：sha256 / 人签清单 / value 回查（红队 B6）
# --------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_rel_ok(src: str) -> str:
    """source 必须是相对路径；返回错误码或空串。"""
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", src):
        return "BAD_SOURCE_PATH"
    p = Path(src)
    if p.is_absolute() or ".." in p.parts:
        return "BAD_SOURCE_PATH"
    return ""


def source_base(cfg: Config) -> Path:
    """source 的解析根（v1.1）。

    - 配了 project.source_root：source 相对它解析（论文项目指到工作区根，
      原始产物留在 experiments/ 原地，不必为过闸复制）；
    - 没配：兼容 v1，source 只许在项目内 results/ 下。
    """
    raw = (cfg.source_root or "").strip()
    if not raw:
        return cfg.root
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (cfg.root / p)


def source_path(cfg: Config, src: str) -> Path:
    return source_base(cfg) / src


def _source_text_keys(text: str) -> set[str]:
    keys = set()
    for raw, suffix, pct in literal_tokens(text):
        keys.add(number_key(raw, suffix or None, pct))
    return keys


def verify_sources(cfg: Config, facts: list[Fact]) -> tuple[list[Issue], list[Issue]]:
    red: list[Issue] = []
    yellow: list[Issue] = []
    root = cfg.root
    results_dir = (root / "results")
    base = source_base(cfg)
    texts: dict[str, str] = {}
    actual: dict[str, str] = {}

    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        src = f.source.strip()
        if not src:
            red.append(Issue("MISSING_SOURCE_FIELD", "fact %r 缺 source 字段" % f.id,
                             location=loc, token=f.id))
            continue
        bad = _source_rel_ok(src)
        if bad:
            red.append(Issue(bad, "fact %r 的 source 必须是相对路径（不许 URL/绝对路径/%s）：%s"
                             % (f.id, ".. 越界" if ".." in Path(src).parts else "绝对路径", src),
                             location=loc, token=f.id))
            continue
        full = base / src
        try:
            full.resolve().relative_to(base.resolve())
        except ValueError:
            red.append(Issue(
                "SOURCE_OUTSIDE_SOURCE_ROOT",
                "fact %r 的 source 越出 source_root（%s）：%s" % (f.id, base, src),
                location=loc, token=f.id))
            continue
        if not cfg.source_root.strip():
            # 未配 source_root：沿用 v1 口径，source 必须在项目 results/ 下
            try:
                full.resolve().relative_to(results_dir.resolve())
            except ValueError:
                red.append(Issue(
                    "SOURCE_OUTSIDE_RESULTS",
                    "fact %r 的 source 不在 results/ 下（%s）——原始产物必须由人签清单锁死"
                    "；跨目录请配 project.source_root" % (f.id, src),
                    location=loc, token=f.id))
                continue
        if not full.is_file():
            red.append(Issue("MISSING_SOURCE", "fact %r 的 source 不存在或不是普通文件：%s"
                             % (f.id, src), location=loc, token=f.id))
            continue
        try:
            digest = sha256_file(full)
            texts[src] = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            red.append(Issue("UNREADABLE_SOURCE", "fact %r 的 source 读不了：%s（%s）"
                             % (f.id, src, exc), location=loc, token=f.id))
            continue
        actual[src] = digest
        if not f.source_sha256:
            red.append(Issue(
                "MISSING_SOURCE_SHA256",
                "fact %r 缺 source_sha256——没有内容锚定，账就无法证明「从签过那刻起没被改」"
                % f.id, location=loc, token=f.id))
        elif f.source_sha256 != digest:
            red.append(Issue(
                "SOURCE_SHA256_MISMATCH",
                "fact %r 的 source_sha256 与现算不符（声明 %s…，实际 %s…）——产物被改过"
                % (f.id, f.source_sha256[:12], digest[:12]), location=loc, token=f.id))

        # value 回查：非派生 claim 的数字必须字面出现在 source 里（B6 的内容锚）
        if not f.is_derived and f.kind == "claim" and src in texts:
            src_keys = _source_text_keys(texts[src])
            missing = []
            for raw, suffix, pct in literal_tokens(f.value):
                if number_key(raw, suffix or None, pct) not in src_keys:
                    missing.append(raw + suffix + ("%" if pct else ""))
            if missing:
                yellow.append(Issue(
                    "VALUE_NOT_IN_SOURCE",
                    "fact %r 的 value 数字 %s 没有出现在 source 里（内容回查失败）"
                    % (f.id, "、".join(missing)), location=loc, token=f.id,
                    severity=SEV_YELLOW))

    # ---- 人签清单 ----
    mpath = cfg.root / cfg.manifest
    if not mpath.is_file():
        yellow.append(Issue(
            "NO_MANIFEST",
            "缺人签清单 %s：工具只能证明「账与正文自洽」，不能证明 results/ 当初没被编"
            % cfg.manifest, location=cfg.manifest, severity=SEV_YELLOW))
        return red, yellow
    try:
        data = load_toml(mpath)
    except ConfigError as exc:
        red.append(Issue("MANIFEST_INVALID", str(exc), location=cfg.manifest))
        return red, yellow
    meta = data.get("manifest")
    if not isinstance(meta, dict) or not str(meta.get("signed_by") or "").strip():
        red.append(Issue(
            "MANIFEST_UNSIGNED",
            "清单 %s 没有 signed_by——没人签的清单不算锚" % cfg.manifest,
            location=cfg.manifest))
    if isinstance(meta, dict) and not str(meta.get("signed_at") or "").strip():
        yellow.append(Issue(
            "MANIFEST_NO_TIMESTAMP", "清单 %s 缺 signed_at（签的时间点）" % cfg.manifest,
            location=cfg.manifest, severity=SEV_YELLOW))
    files = data.get("files")
    if not isinstance(files, dict):
        files = {}
        yellow.append(Issue("MANIFEST_NO_FILES", "清单 %s 没有 [files] 段" % cfg.manifest,
                            location=cfg.manifest, severity=SEV_YELLOW))
    signed = {str(k): str(v).strip().lower() for k, v in files.items()}

    for f in facts:
        src = f.source.strip()
        if src not in actual:
            continue
        if src not in signed:
            red.append(Issue(
                "SOURCE_NOT_SIGNED",
                "fact %r 的 source %s 不在人签清单里——没人确认过它" % (f.id, src),
                location="%s:%s" % (f.file, f.line or "?"), token=f.id))
        elif signed[src] != actual[src]:
            red.append(Issue(
                "MANIFEST_HASH_MISMATCH",
                "清单里 %s 的 sha256 与文件现值不符——签过之后被改过" % src,
                location=cfg.manifest, token=f.id))

    if results_dir.is_dir():
        for p in sorted(results_dir.rglob("*")):
            if not p.is_file() or p.resolve() == mpath.resolve():
                continue
            rel = p.relative_to(root).as_posix()
            if rel not in signed:
                yellow.append(Issue(
                    "UNSIGNED_RESULT",
                    "results/ 下有未签文件 %s——它没有被任何清单锁住" % rel,
                    location=rel, severity=SEV_YELLOW))
    return red, yellow


# --------------------------------------------------------------------------
# derived 的 expr 求值：只允许四则运算与括号，ast 白名单，禁 eval（红队 B7）
# --------------------------------------------------------------------------

class ExprError(Exception):
    pass


_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
    ast.Attribute, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.UAdd, ast.USub,
)


def _numeric_parts(value: str) -> tuple[float, float]:
    """把 value 读成 (num, den)：'10/16' -> (10,16)；'56.25%' -> (56.25,1)。"""
    text = str(value).strip().replace(",", "")
    m = _FRACTION_RE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    toks = literal_tokens(text)
    if not toks:
        raise ExprError("父 fact 的 value 不是数值：%r" % value)
    raw = toks[0][0]
    return float(Decimal(raw)), 1.0


def eval_expr(expr: str, facts: dict[str, Fact]) -> float:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExprError("算式语法错：%s" % exc)
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExprError("算式里不许出现 %s（只允许四则运算、括号与 fact id）"
                            % type(node).__name__)

    def name_value(node) -> float:
        if isinstance(node, ast.Name):
            fid, attr = node.id, ""
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            fid, attr = node.value.id, node.attr
        else:
            raise ExprError("算式里的名字解析不了")
        f = facts.get(fid.strip().casefold())
        if f is None:
            raise ExprError("算式引用了不存在的 fact %r" % fid)
        num, den = _numeric_parts(f.value)
        if attr == "num":
            return num
        if attr == "den":
            return den
        if attr:
            raise ExprError("只支持 .num / .den，不支持 .%s" % attr)
        if den == 0:
            raise ExprError("父 fact %r 的分母为 0" % fid)
        return num / den

    def walk(node) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                raise ExprError("算式里只允许数字常量")
            return float(node.value)
        if isinstance(node, (ast.Name, ast.Attribute)):
            return name_value(node)
        if isinstance(node, ast.UnaryOp):
            v = walk(node.operand)
            return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp):
            a, b = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if b == 0:
                raise ExprError("算式除零")
            return a / b
        raise ExprError("算式节点不支持：%s" % type(node).__name__)

    return walk(tree)


def _declared_number(value: str) -> float:
    toks = literal_tokens(value)
    if not toks:
        raise ExprError("value 不是数值：%r" % value)
    return float(Decimal(toks[0][0].replace(",", "")))


def _cycles(facts: list[Fact]) -> list[list[str]]:
    graph = {f.id_key: [d.strip().casefold() for d in f.derived_from] for f in facts}
    color: dict[str, int] = {}
    stack: list[str] = []
    out: list[list[str]] = []

    def dfs(u: str) -> None:
        color[u] = 1
        stack.append(u)
        for v in graph.get(u, []):
            if v not in graph:
                continue
            if color.get(v, 0) == 0:
                dfs(v)
            elif color.get(v) == 1:
                if v in stack:
                    out.append(stack[stack.index(v):] + [v])
        stack.pop()
        color[u] = 2

    for k in graph:
        if color.get(k, 0) == 0:
            dfs(k)
    return out


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

def run_check(cfg: Config, facts: list[Fact]):
    issues: list[Issue] = []
    warnings: list[Issue] = []
    conflicts: list[dict] = []

    if not facts:
        raise ConfigError("facts 为空（%s 没匹配到任何 fact）——空账不算通过" % cfg.facts_glob)

    red_src, yellow_src = verify_sources(cfg, facts)
    issues += red_src
    warnings += yellow_src

    seen: dict[str, Fact] = {}
    superseded = {s.strip().casefold() for f in facts for s in f.supersedes}
    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        key = f.id_key
        if key in seen:
            issues.append(Issue(
                "DUPLICATE_ID", "fact id %r 重复（%s 与 %s；id 按大小写不敏感判重）"
                % (f.id, seen[key].file, f.file), location=loc, token=f.id))
        else:
            seen[key] = f
        if re.search(r"\s", f.id) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", f.id):
            issues.append(Issue(
                "BAD_ID_FORMAT",
                "fact id %r 不合法：只允许字母开头，后接字母/数字/_ . : -（不许空白）"
                % f.id, location=loc, token=f.id))
        if f.confidence not in CONFIDENCE_OK:
            issues.append(Issue(
                "BAD_CONFIDENCE", "fact %r 的 confidence=%r 不合法（只允许 high/med/low）"
                % (f.id, f.confidence), location=loc, token=f.id))
        if f.kind not in KINDS_OK:
            issues.append(Issue(
                "BAD_KIND", "fact %r 的 kind=%r 不合法（只允许 claim/config）"
                % (f.id, f.kind), location=loc, token=f.id))
        if not f.value:
            issues.append(Issue("EMPTY_VALUE", "fact %r 的 value 为空（账上没有数）" % f.id,
                                location=loc, token=f.id))

    known = {f.id_key: f for f in facts}
    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        for dep in f.derived_from:
            if dep.strip().casefold() not in known:
                issues.append(Issue(
                    "BAD_DERIVED_FROM", "fact %r 的 derived_from 指向不存在的 id %r" % (f.id, dep),
                    location=loc, token=dep))
        for sup in f.supersedes:
            if sup.strip().casefold() not in known:
                issues.append(Issue(
                    "BAD_SUPERSEDES", "fact %r 的 supersedes 指向不存在的 id %r" % (f.id, sup),
                    location=loc, token=sup))
        for dep in f.derived_from:
            if dep.strip().casefold() in superseded:
                issues.append(Issue(
                    "SUPERSEDED_PARENT",
                    "fact %r 从已被 supersedes 的 %r 推算——父值已作废" % (f.id, dep),
                    location=loc, token=dep))

        # derived 值必须写可求值算式
        if f.derived_from and not f.expr:
            issues.append(Issue(
                "MISSING_EXPR",
                "fact %r 是推算值，但没写 expr——只写 derived_from 不算可复核" % f.id,
                location=loc, token=f.id))
        if f.expr:
            try:
                got = eval_expr(f.expr, known)
                want = _declared_number(f.value)
                if abs(got - want) > 1e-9 * max(1.0, abs(want)):
                    issues.append(Issue(
                        "EXPR_MISMATCH",
                        "fact %r 的 expr=%r 算出 %s，与 value=%r 不符"
                        % (f.id, f.expr, ("%.10g" % got), f.value),
                        location=loc, token=f.id))
            except ExprError as exc:
                issues.append(Issue("EXPR_INVALID", "fact %r 的 expr 不可用：%s" % (f.id, exc),
                                    location=loc, token=f.id))
        elif not f.derived_from and f.is_derived:
            # is_derived 只看 expr/derived_from，这里不会发生；保底留白
            pass

    for cyc in _cycles(facts):
        issues.append(Issue(
            "DERIVED_CYCLE", "推算链成环：%s" % " -> ".join(cyc),
            location="facts/", token=",".join(cyc)))

    # 冲突：结构化 (metric, scope) 优先，否则 claim 全文；用 supersedes 封冲突
    groups: dict[tuple, list[Fact]] = {}
    for f in facts:
        if f.metric.strip():
            key = ("metric", f.metric.strip(), f.scope.strip())
        else:
            key = ("claim", f.claim.strip(), "")
        groups.setdefault(key, []).append(f)
    for _key, group in groups.items():
        label = group[0].metric.strip() or group[0].claim.strip()
        if not label or len(group) < 2:
            continue
        if len({f.value.strip() for f in group}) < 2:
            continue
        live = [f for f in group if f.id_key not in superseded]
        if len({f.value.strip() for f in live}) < 2:
            continue
        conflicts.append({
            "claim": label,
            "ids": [f.id for f in live],
            "values": [f.value for f in live],
            "message": "同一 claim/metric 有不同 value 且没有被 supersedes：%s"
                       % " / ".join("%s=%s" % (f.id, f.value) for f in live),
        })
        warnings.append(Issue(
            "LEDGER_CONFLICT",
            "账本自相矛盾（黄）：" + conflicts[-1]["message"],
            location="%s:%s" % (live[0].file, live[0].line or "?"),
            token=",".join(f.id for f in live), severity=SEV_YELLOW))

    # 账本卫生：同一 value 挂在多条不同 claim 上 -> 疑似「数字白名单」（红队 C6）
    by_value: dict[str, list[Fact]] = {}
    for f in facts:
        if f.kind == "claim" and f.value.strip() and f.id_key not in superseded:
            by_value.setdefault(f.value.strip(), []).append(f)
    for value, group in by_value.items():
        if len(group) > 1 and len({f.claim.strip() for f in group}) > 1:
            warnings.append(Issue(
                "DUPLICATE_VALUE",
                "同一个 value=%r 挂在 %s 上——像在拿一份数字白名单充事实账"
                % (value, "、".join(f.id for f in group)),
                location="%s:%s" % (group[0].file, group[0].line or "?"),
                token=",".join(f.id for f in group), severity=SEV_YELLOW))

    summary = {
        "facts": len(facts),
        "ids": len(known),
        "sources_ok": sum(1 for f in facts if f.source and source_path(cfg, f.source).is_file()),
        "sha_pinned": sum(1 for f in facts if f.source_sha256),
        "conflicts": len(conflicts),
        "red": len(issues),
        "yellow": len(warnings),
        "confidence": {
            "high": sum(1 for f in facts if f.confidence == "high"),
            "med": sum(1 for f in facts if f.confidence == "med"),
            "low": sum(1 for f in facts if f.confidence == "low"),
        },
        "derived": sum(1 for f in facts if f.derived_from),
        "attestation": {"facts_sha256": facts_digest(cfg),
                        "git_commit": git_commit(cfg.root)},
    }
    return issues, warnings, conflicts, summary


# --------------------------------------------------------------------------
# audit
# --------------------------------------------------------------------------

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


def _resolve_arxiv(arxiv_id: str) -> tuple[str, str]:
    """返回 (status, detail)：verified / not_found / unverified。"""
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"id_list": arxiv_id, "max_results": "1"})
    req = urllib.request.Request(url, headers={"User-Agent": "factscribe/%s" % VERSION})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "not_found", "arXiv API 返回 HTTP 404"
        return "unverified", "联网核验失败（%s）" % exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return "unverified", "联网核验失败（%s）" % exc
    if status != 200:
        return "unverified", "arXiv API 返回 HTTP %s" % status
    if re.search(r"<entry\b", body):
        return "verified", "arXiv API 命中"
    if "<opensearch:totalResults>0<" in body or "totalResults>0<" in body:
        return "not_found", "arXiv API 明确返回 0 条"
    return "unverified", "arXiv API 响应无法判定"


def _resolve_doi(doi: str) -> tuple[str, str]:
    url = "https://doi.org/api/handles/" + urllib.parse.quote(doi, safe="/")
    req = urllib.request.Request(url, headers={"User-Agent": "factscribe/%s" % VERSION})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "not_found", "doi.org 返回 HTTP 404（该 DOI 不存在）"
        return "unverified", "联网核验失败（%s）" % exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return "unverified", "联网核验失败（%s）" % exc
    if '"responseCode":1' in body.replace(" ", "") or '"responseCode": 1' in body:
        return "verified", "doi.org handle 命中"
    if '"responseCode":100' in body.replace(" ", "") or '"responseCode": 100' in body:
        return "not_found", "doi.org 明确返回不存在"
    return "unverified", "doi.org 响应无法判定"


def run_audit(cfg: Config, facts: list[Fact], sections: list[tuple[str, str]],
              resolve: bool = False):
    if not facts:
        raise ConfigError("facts 为空（%s 没匹配到任何 fact）——空账不算通过" % cfg.facts_glob)
    if not sections:
        raise ConfigError("sections 为空（%s 没匹配到任何 .tex）——没正文不算通过"
                          % cfg.sections_glob)

    red: list[Issue] = []
    yellow: list[Issue] = []
    hints: list[Issue] = []

    red_src, yellow_src = verify_sources(cfg, facts)
    red += red_src
    yellow += yellow_src

    scanned = {rel: scan_tex(text) for rel, text in sections}

    # ---- bib 文件集合：config + 正文声明的多 bib（红队 C8-B）----
    bib_paths: list[Path] = []
    cfg_bib = cfg.root / cfg.bib
    if not cfg_bib.is_file():
        raise ConfigError("找不到参考文献 %s——引用对账无从做起" % cfg_bib)
    bib_paths.append(cfg_bib)
    for rel, scan in scanned.items():
        for decl in scan.bib_files:
            p = (cfg.root / decl)
            if not p.is_file():
                red.append(Issue(
                    "BIB_FILE_MISSING", "正文声明的参考文献 %s 不存在" % decl,
                    location=rel, token=decl))
                continue
            if p.resolve() not in {q.resolve() for q in bib_paths}:
                bib_paths.append(p)
    bib_entries: list[BibEntry] = []
    for p in bib_paths:
        try:
            bib_entries += parse_bib(p, cfg.root)
        except ConfigError:
            raise
    bib_by_key: dict[str, BibEntry] = {}
    for e in bib_entries:
        bib_by_key.setdefault(e.key, e)
    dup_keys, dup_ids = bib_duplicates(bib_entries)
    for k in dup_keys:
        e = bib_by_key[k]
        red.append(Issue("DUPLICATE_BIB_KEY", "bib 里 key %r 定义了不止一次" % k,
                         location="%s:%s" % (e.file, e.line), token=k))
    for ident, ks in dup_ids:
        yellow.append(Issue(
            "DUPLICATE_STABLE_ID", "%s 挂在多个 key 上：%s" % (ident, "、".join(ks)),
            location="%s:%s" % (bib_by_key[ks[0]].file, bib_by_key[ks[0]].line),
            token=",".join(ks), severity=SEV_YELLOW))

    fact_by_id = {f.id_key: f for f in facts}
    # 全局值域只收 claim 事实：config 事实不能当「数字白名单」用（红队 C3/C6）
    key_to_facts: dict[str, list[str]] = {}
    for f in facts:
        if f.kind != "claim":
            continue
        for k in f.value_keys:
            key_to_facts.setdefault(k, []).append(f.id)

    numbers_total = 0
    matched = 0        # 旧口径：回得到账（含未绑定）
    bound = 0          # 内联绑定且对得上
    unbound_yellow = 0
    unmatched = 0
    annotations_total = 0
    annotation_sites: list[str] = []
    usage: dict[str, list[str]] = {f.id: [] for f in facts}
    marker_count: dict[str, int] = {f.id: 0 for f in facts}
    used_keys: dict[str, int] = {}
    unresolved: list[dict] = []
    seen_figures: set[str] = set()

    for rel, text in sections:
        scan = scanned[rel]
        nums = _extract_numbers(scan.masked, text)
        numbers_total += len(nums)
        annotations_total += len(scan.annotations)
        annotation_sites += ["%s:%s \\%s" % (rel, line, name)
                             for name, line in scan.annotations]

        for fid, _line in scan.markers:
            f = fact_by_id.get(fid.strip().casefold())
            if f is None:
                red.append(Issue(
                    "UNKNOWN_FACT_MARKER",
                    "正文标记了不存在的 fact %r（账上没有这个 id）" % fid,
                    location="%s:%s" % (rel, _line), token=fid))
            else:
                marker_count[f.id] += 1
                if rel not in usage[f.id]:
                    usage[f.id].append(rel)

        for name, line, col in scan.unknown_cites:
            red.append(Issue(
                "UNKNOWN_CITE_COMMAND",
                "认不出的引用命令 \\%s——引用闸门默认 fail-closed，请改用已知的 cite 家族命令"
                % name, location="%s:%s:%s" % (rel, line, col), token=name))

        for num in nums:
            loc = "%s:%s:%s" % (rel, num["line"], num["col"])
            ids = scan.bindings.get(num["line"])
            if ids:
                allowed: set[str] = set()
                known_ids = []
                for fid in ids:
                    f = fact_by_id.get(fid.strip().casefold())
                    if f is not None:
                        known_ids.append(f.id)
                        allowed |= f.value_keys
                if num["key"] in allowed:
                    bound += 1
                else:
                    unmatched += 1
                    red.append(Issue(
                        "BOUND_MISMATCH",
                        "该行绑定 %s，但数字 %s 不在其 value 里（内联绑定是硬约束）"
                        % ("/".join(known_ids or ids), num["token"]),
                        location=loc, token=num["token"], context=num["text"]))
                continue
            if num["key"] in key_to_facts:
                unbound_yellow += 1
                yellow.append(Issue(
                    "UNBOUND_NUMBER",
                    "数字 %s 回得到账（%s），但正文没内联绑定——只算黄，不算已核验"
                    % (num["token"], "/".join(key_to_facts[num["key"]])),
                    location=loc, token=num["token"], context=num["text"],
                    severity=SEV_YELLOW))
            else:
                unmatched += 1
                red.append(Issue(
                    "UNMATCHED_NUMBER", "数字 %s 回不到任何 fact.value" % num["token"],
                    location=loc, token=num["token"], context=num["text"]))
        matched = bound + unbound_yellow

        for key, line, col in scan.cites:
            used_keys[key] = used_keys.get(key, 0) + 1
            entry = bib_by_key.get(key)
            line_text = text.split("\n")[line - 1].strip() if line - 1 < len(text.split("\n")) else ""
            if entry is None:
                red.append(Issue(
                    "MISSING_CITE", "引用了 bib 里不存在的 key %r" % key,
                    location="%s:%s:%s" % (rel, line, col), token=key,
                    context=line_text))
                continue
            name, value = entry.stable_id
            if name is None:
                red.append(Issue(
                    "BIB_NO_STABLE_ID",
                    "bib 条目 %r（@%s）没有 arxiv/doi%s（不可复核）"
                    % (key, entry.kind, "/url" if entry.kind in _URL_OK_TYPES else ""),
                    location="%s:%s" % (entry.file, entry.line), token=key))
                continue
            if not valid_stable_id(name, value):
                red.append(Issue(
                    "BAD_STABLE_ID_FORMAT",
                    "%r 的 %s=%r 格式不合法（不能解析成真实标识）" % (key, name, value),
                    location="%s:%s" % (entry.file, entry.line), token=key))
                continue
            if resolve:
                status, detail = (_resolve_doi(value) if name == "doi"
                                  else _resolve_arxiv(value))
                item = {"key": key, "id_type": name, "id": value,
                        "status": status, "detail": detail}
                unresolved.append(item)
                if status == "not_found":
                    red.append(Issue(
                        "UNRESOLVED_CITE",
                        "引用 %r 的 %s=%s 在远端不存在（%s）" % (key, name, value, detail),
                        location="%s:%s" % (entry.file, entry.line), token=key))
                elif status == "unverified":
                    hints.append(Issue(
                        "CITE_UNVERIFIED",
                        "%r 的 %s=%s 未能联网核验（%s），不判红" % (key, name, value, detail),
                        location="%s:%s" % (entry.file, entry.line), token=key,
                        severity=SEV_YELLOW))
                    yellow.append(hints[-1])

        # 图的数据面：没有随图 CSV 的图，数字不可核（红队 D10）
        for path, line in scan.figures:
            p = (cfg.root / path)
            candidates = [p.with_suffix(".csv") if p.suffix else Path(str(p) + ".csv"),
                          Path(str(p) + ".csv")]
            if any(c.is_file() for c in candidates):
                continue
            if path in seen_figures:
                continue
            seen_figures.add(path)
            yellow.append(Issue(
                "FIGURE_UNVERIFIED",
                "图 %s 没有随图数据（.csv），图里的数字不在本闸门覆盖范围内" % path,
                location="%s:%s" % (rel, line), token=path, severity=SEV_YELLOW))

    # 未进 bib 可复核字段的条目（即使没被引用也要说一声）
    for e in bib_entries:
        if e.key not in used_keys and e.stable_id[0] is None:
            hints.append(Issue(
                "BIB_NO_STABLE_ID", "bib 条目 %r 既没有 arxiv 也没有 doi（不可复核）" % e.key,
                location="%s:%s" % (e.file, e.line), token=e.key, severity=SEV_INFO))
        if e.key in used_keys and e.stable_id[0] is not None and not valid_stable_id(*e.stable_id):
            pass  # 已在引用处判红

    for f in facts:
        if marker_count.get(f.id, 0) == 0:
            hints.append(Issue(
                "UNUSED_FACT", "账上有、文里没用：fact %r（%s）" % (f.id, f.claim),
                location="%s:%s" % (f.file, f.line or "?"), token=f.id, severity=SEV_INFO))
    for e in bib_entries:
        if e.key not in used_keys:
            hints.append(Issue(
                "UNUSED_BIB", "bib 里有、文里没引：%r" % e.key,
                location="%s:%s" % (e.file, e.line), token=e.key, severity=SEV_INFO))

    # 覆盖：闭包外还有 .tex 从未被审计 -> 黄（红队 B4/B8）
    all_tex = all_tex_files(cfg)
    unscanned = [p for p in all_tex if p not in scanned]
    for p in unscanned:
        yellow.append(Issue(
            "UNSCANNED_TEX", "%s 不在审计闭包里（未被扫描）" % p,
            location=p, token=p, severity=SEV_YELLOW))

    # 绑定率过低 = 还在靠白名单（红队 C6/C11）
    denom = bound + unbound_yellow + unmatched
    if denom >= 4 and (bound / denom) < 0.5:
        yellow.append(Issue(
            "LOW_BINDING_RATE",
            "内联绑定率 %d/%d 低于 50%%——大部分数字只是「回得到账」，还没回到对的那条账"
            % (bound, denom), location="audit", severity=SEV_YELLOW))

    if resolve and len(unresolved) >= 3:
        bad = sum(1 for u in unresolved if u["status"] == "unverified")
        if bad / len(unresolved) > 0.5:
            yellow.append(Issue(
                "RESOLVE_DEGRADED",
                "联网核验 %d/%d 条都没成功（限流/无网？）——引用存在性本轮等于没验"
                % (bad, len(unresolved)), location="refs.bib", severity=SEV_YELLOW))

    summary = {
        "facts": len(facts),
        "sections": len(sections),
        "numbers_total": numbers_total,
        "numbers_matched": matched,
        "numbers_bound": bound,
        "numbers_unbound": unbound_yellow,
        "numbers_unmatched": unmatched,
        "annotations_skipped": annotations_total,
        "annotation_sites": annotation_sites,
        "cites_total": sum(used_keys.values()),
        "cites_unique": len(used_keys),
        "bib_entries": len(bib_entries),
        "bib_files": [p.relative_to(cfg.root).as_posix() for p in bib_paths],
        "bib_used": len([k for k in used_keys if k in bib_by_key]),
        "red": len(red),
        "yellow": len(yellow),
        "hints": len(hints),
        "confidence": {
            "high": sum(1 for f in facts if f.confidence == "high"),
            "med": sum(1 for f in facts if f.confidence == "med"),
            "low": sum(1 for f in facts if f.confidence == "low"),
        },
        "coverage": {
            "files_scanned": sorted(scanned),
            "files_scanned_count": len(scanned),
            "files_matched_by_glob": len(_glob_paths(cfg.root, cfg.sections_glob)),
            "files_unscanned": unscanned,
            "facts_loaded": len(facts),
            "parse_errors": 0,
            "sha_pinned": sum(1 for f in facts if f.source_sha256),
            "numbers_total": numbers_total,
            "numbers_bound": bound,
        },
        "usage": {k: v for k, v in usage.items()},
        "marker_count": marker_count,
        "attestation": {
            "facts_sha256": facts_digest(cfg),
            "sources_sha256": {src: digest for src, digest in sorted(
                (f.source, f.source_sha256) for f in facts if f.source_sha256)},
            "git_commit": git_commit(cfg.root),
        },
    }
    return red, yellow, hints, summary, unresolved


# --------------------------------------------------------------------------
# matrix
# --------------------------------------------------------------------------

def _cell(v) -> str:
    return str(v if v not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def render_matrix(cfg: Config, facts: list[Fact], sections: list[tuple[str, str]]):
    if not facts:
        raise ConfigError("facts 为空（%s 没匹配到任何 fact）——矩阵无从生成" % cfg.facts_glob)
    if not sections:
        raise ConfigError("sections 为空（%s 没匹配到任何 .tex）" % cfg.sections_glob)

    used_sections: dict[str, list[str]] = {f.id: [] for f in facts}
    counts: dict[str, int] = {f.id: 0 for f in facts}
    for rel, text in sections:
        scan = scan_tex(text)
        for fid, _line in scan.markers:
            f = next((x for x in facts if x.id_key == fid.strip().casefold()), None)
            if f is not None:
                counts[f.id] += 1
                if rel not in used_sections[f.id]:
                    used_sections[f.id].append(rel)

    lines = [
        "# Fact 追溯矩阵",
        "",
        "- 项目：%s" % (cfg.title or "（未命名）"),
        "- 生成：FactScribe %s（schema %s）" % (VERSION, SCHEMA_VERSION),
        "- facts：%d 条；sections：%d 个" % (len(facts), len(sections)),
        "",
        "| fact id | claim | value | source | locator | confidence | 被引用次数 | 被哪些节引用 | kind | source_sha256(前12) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for f in facts:
        used = used_sections[f.id]
        lines.append("| %s | %s | %s | %s | %s | %s | %d | %s | %s | %s |" % (
            _cell(f.id), _cell(f.claim), _cell(f.value), _cell(f.source),
            _cell(f.locator), _cell(f.confidence), counts[f.id],
            _cell("、".join(used) if used else "（未使用）"),
            _cell(f.kind), _cell(f.source_sha256[:12] if f.source_sha256 else ""),
        ))
    unused = [f.id for f in facts if counts[f.id] == 0]
    lines += ["", "## 提示", ""]
    lines.append("- 账上有、文里没用：%s" % ("、".join(unused) if unused else "无"))
    lines.append("- 正文引用只在 marker（`\\fact{A1}` 或 `[[fact:A1]]`）里计数。")
    lines.append("- 绿＝「有账、账有据、据未被改」；不是「内容为真」。")
    lines.append("")

    rows = [{
        "id": f.id, "claim": f.claim, "value": f.value, "source": f.source,
        "locator": f.locator, "confidence": f.confidence, "kind": f.kind,
        "source_sha256": f.source_sha256,
        "citations": counts[f.id], "sections": used_sections[f.id],
    } for f in facts]
    return "\n".join(lines), rows


# --------------------------------------------------------------------------
# preamble：给正文里的 \fact / \pkignore 一个真宏（红队 C10）
# --------------------------------------------------------------------------

PREAMBLE_TEXT = """% 由 paperkit 生成：把本文件 \\input 到导言区（main.tex 的 \\begin{document} 之前）。
% \\fact{ID} 只做审计绑定，排版上不产生可见字符，避免 PDF 里出现字面量。
\\providecommand{\\fact}[1]{}
% \\pkignore{...} 是显式的数字豁免区：内容照排，但不进数字审计。
\\providecommand{\\pkignore}[1]{#1}
"""


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def run_build(cfg: Config) -> tuple[int, str]:
    if not cfg.build.strip():
        return EXIT_OK, "project.build 为空，按契约跳过编译"
    try:
        proc = subprocess.run(cfg.build, shell=True, cwd=str(cfg.root),
                              capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return EXIT_RED, "$ %s\n构建超时（600 秒）被终止" % cfg.build
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return EXIT_RED, "$ %s\n%s\n构建失败：退出码 %d" % (cfg.build, out.rstrip(), proc.returncode)
    return EXIT_OK, "$ %s\n%s\n构建成功：退出码 0" % (cfg.build, out.rstrip())


# --------------------------------------------------------------------------
# 人读输出
# --------------------------------------------------------------------------

def _print_issue(i: Issue, idx: int) -> str:
    head = " %2d. %-22s %s" % (idx, i.code, i.location or "-")
    lines = [head]
    if i.token:
        lines[0] += "  →  " + i.token
    lines.append("     " + i.message)
    if i.context:
        lines.append("     行: " + i.context[:200])
    return "\n".join(lines)


def _status_word(code: int) -> str:
    return {EXIT_OK: "绿", EXIT_RED: "红（有违例）", EXIT_YELLOW: "黄（未核验，不判死）",
            EXIT_CONFIG: "配置/用法错", EXIT_INTERNAL: "工具内部错误"}.get(code, "?")


def _human_check(cfg, facts, issues, warnings, conflicts, summary, code) -> str:
    lines = ["== paperkit check ==", "project : %s" % cfg.root,
             "facts   : %d 条（id %d 个，source 均在位 %d 条，sha 钉住 %d 条）"
             % (summary["facts"], summary["ids"], summary["sources_ok"],
                summary["sha_pinned"]), ""]
    if warnings:
        lines.append("[黄] %d 处（账本自相矛盾/未签名/未核验——必须列出来给人看）"
                     % len(warnings))
        lines += [_print_issue(i, n) for n, i in enumerate(warnings, 1)]
        lines.append("")
    else:
        lines.append("[黄] 0 处")
    if issues:
        lines.append("[红] %d 处" % len(issues))
        lines += [_print_issue(i, n) for n, i in enumerate(issues, 1)]
    else:
        lines.append("[红] 0 处 —— 账本身干净（不等于内容为真）")
    lines.append("")
    lines.append("结论：%s（退出码 %d）" % (_status_word(code), code))
    return "\n".join(lines)


def _human_audit(cfg, red, yellow, hints, summary, unresolved, code) -> str:
    cov = summary.get("coverage", {})
    lines = [
        "== paperkit audit ==",
        "project : %s" % cfg.root,
        "facts   : %d 条      sections: %d 个（扫描 %d 个 .tex）" % (
            summary["facts"], summary["sections"], cov.get("files_scanned_count", 0)),
        "numbers : %d 个（bound %d / unbound %d / unmatched %d）" % (
            summary["numbers_total"], summary["numbers_bound"],
            summary.get("numbers_unbound", 0), summary["numbers_unmatched"]),
        "notes   : 已跳过 %d 处批注（\\todoq/\\todo/\\pkignore 等，内容不参与审计）"
        % summary.get("annotations_skipped", 0),
        "cites   : %d 次调用、%d 个 key；bib %d 条（命中 %d）" % (
            summary["cites_total"], summary["cites_unique"],
            summary["bib_entries"], summary["bib_used"]),
        "coverage: %s" % ("、".join(cov.get("files_scanned", [])) or "（无）"),
        "",
    ]
    if yellow:
        lines.append("[黄] %d 处（未核验/未绑定/未签名——不判死，但不许当绿）" % len(yellow))
        lines += [_print_issue(i, n) for n, i in enumerate(yellow, 1)]
        lines.append("")
    else:
        lines.append("[黄] 0 处")
    if red:
        lines.append("[红] %d 处（必须修）" % len(red))
        lines += [_print_issue(i, n) for n, i in enumerate(red, 1)]
    else:
        lines.append("[红] 0 处 —— 数字与引用全部有账、有据")
    shown = [h for h in hints if h.severity != SEV_YELLOW]
    if shown:
        lines.append("")
        lines.append("[提示] %d 条（非红非黄，不拦）" % len(shown))
        for h in shown:
            lines.append(" - %-16s %s %s" % (h.code, h.location, h.message))
    if unresolved:
        lines.append("")
        lines.append("联网核验：")
        for u in unresolved:
            lines.append(" - %-18s %s=%s -> %s（%s）" % (
                u["key"], u["id_type"], u["id"], u["status"], u["detail"]))
    lines.append("")
    lines.append("结论：%d 红 / %d 黄 → %s（退出码 %d）" % (
        len(red), len(yellow), _status_word(code), code))
    lines.append("注意：绿只代表「账、据、正文自洽且据未被改」，不代表内容为真。")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _emit(payload: dict, text: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text)


def _exit_code(red: int, yellow: int, strict: bool = False) -> int:
    if red:
        return EXIT_RED
    if yellow:
        return EXIT_RED if strict else EXIT_YELLOW
    return EXIT_OK


def _severity_of(code: int) -> str:
    if code == EXIT_OK:
        return "ok"
    if code == EXIT_RED:
        return SEV_RED
    if code == EXIT_YELLOW:
        return SEV_YELLOW
    return "error"


def _payload(command: str, status: str, code: int, **kw) -> dict:
    d = {"schema_version": SCHEMA_VERSION, "tool": "factscribe", "version": VERSION,
         "command": command, "status": status, "severity": _severity_of(code),
         "exit": code}
    d.update(kw)
    return d


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="factscribe",
        description="论文数字与引用的机械闸门（check / audit / matrix / build / preamble）")
    p.add_argument("--version", action="version", version="factscribe %s" % VERSION)
    sub = p.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("check", "校验事实账：id/sha256/人签清单/expr 算术/冲突"),
        ("audit", "核心：内联绑定 + 数字回账 + 引用落稳定标识 + 覆盖报告"),
        ("matrix", "生成 audit/matrix.md 追溯矩阵"),
        ("build", "执行 project.build（v1 仍按 shell 字符串执行，见 SPEC-V1 B5）"),
        ("preamble", "生成 audit/preamble.tex（\\fact / \\pkignore 宏定义）"),
    ):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("project", nargs="?", default=".", help="项目目录（默认当前目录）")
        sp.add_argument("--json", action="store_true", help="机器可读输出（stdout 只出 JSON）")
        if name in ("check", "audit"):
            sp.add_argument("--strict", action="store_true",
                            help="黄也当红（CI 用：未核验不许过）")
        if name == "audit":
            sp.add_argument("--resolve", action="store_true",
                            help="联网核验 arXiv/DOI（超时 5 秒；失败标 unverified 黄）")
        if name == "matrix":
            sp.add_argument("--out", default=None, help="默认 audit/matrix.md")
        if name == "preamble":
            sp.add_argument("--out", default=None, help="默认 audit/preamble.tex")
    return p


def cmd_check(args) -> int:
    cfg = load_config(Path(args.project))
    facts = load_facts(cfg)
    issues, warnings, conflicts, summary = run_check(cfg, facts)
    code = _exit_code(len(issues), len(warnings), getattr(args, "strict", False))
    text = _human_check(cfg, facts, issues, warnings, conflicts, summary, code)
    _emit(_payload("check", _severity_of(code), code,
                   summary=summary,
                   issues=[i.as_dict() for i in issues],
                   warnings=[i.as_dict() for i in warnings],
                   hints=[], conflicts=conflicts), text, args.json)
    return code


def cmd_audit(args) -> int:
    cfg = load_config(Path(args.project))
    facts = load_facts(cfg)
    sections = load_sections(cfg)
    red, yellow, hints, summary, unresolved = run_audit(
        cfg, facts, sections, resolve=getattr(args, "resolve", False))
    code = _exit_code(len(red), len(yellow), getattr(args, "strict", False))
    text = _human_audit(cfg, red, yellow, hints, summary, unresolved, code)
    _emit(_payload("audit", _severity_of(code), code,
                   summary=summary,
                   issues=[i.as_dict() for i in red],
                   warnings=[i.as_dict() for i in yellow],
                   hints=[h.as_dict() for h in hints],
                   coverage=summary.get("coverage", {}),
                   resolved=unresolved), text, args.json)
    return code


def cmd_matrix(args) -> int:
    cfg = load_config(Path(args.project))
    facts = load_facts(cfg)
    sections = load_sections(cfg)
    text, rows = render_matrix(cfg, facts, sections)
    out = Path(args.out) if getattr(args, "out", None) else cfg.root / "audit" / "matrix.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    human = "== paperkit matrix ==\n写盘：%s\n行数：%d（每行一条 fact）\n%s" % (
        out, len(rows), text)
    _emit(_payload("matrix", "ok", EXIT_OK, path=str(out), rows=rows,
                   facts=len(rows)), human, args.json)
    return EXIT_OK


def cmd_preamble(args) -> int:
    cfg = load_config(Path(args.project))
    out = Path(args.out) if getattr(args, "out", None) else cfg.root / "audit" / "preamble.tex"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PREAMBLE_TEXT, encoding="utf-8")
    human = "== paperkit preamble ==\n写盘：%s\n%s" % (out, PREAMBLE_TEXT)
    _emit(_payload("preamble", "ok", EXIT_OK, path=str(out)), human, args.json)
    return EXIT_OK


def cmd_build(args) -> int:
    cfg = load_config(Path(args.project))
    code, out = run_build(cfg)
    _emit(_payload("build", "ok" if code == EXIT_OK else "violation", code,
                   build=cfg.build, output=out), "== paperkit build ==\n" + out, args.json)
    return code


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"check": cmd_check, "audit": cmd_audit, "matrix": cmd_matrix,
                "build": cmd_build, "preamble": cmd_preamble}
    try:
        return handlers[args.command](args)
    except ConfigError as exc:
        if getattr(args, "json", False):
            print(json.dumps(_payload(args.command, "error", EXIT_CONFIG,
                                      message=str(exc)), ensure_ascii=False, indent=2))
        else:
            print("factscribe: 配置/用法错：%s" % exc, file=sys.stderr)
        return EXIT_CONFIG
    except Exception as exc:  # noqa: BLE001 - 内部错误必须与「有违例」分开
        if getattr(args, "json", False):
            print(json.dumps(_payload(args.command, "error", EXIT_INTERNAL,
                                      message="%s: %s" % (type(exc).__name__, exc)),
                             ensure_ascii=False, indent=2))
        else:
            print("factscribe: 工具内部错误：%s: %s" % (type(exc).__name__, exc),
                  file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())

