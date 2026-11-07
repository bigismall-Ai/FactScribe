#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paperkit —— 论文数字与引用的机械闸门（MVP）。

纯标准库；Python >= 3.10。
四个子命令：check / audit / matrix / build，全部支持 --json。

设计口径见同目录 SPEC.md。核心一句话：
正文里的每一个数字必须能回到 facts 账，每一个 \\cite 必须能在 refs.bib 里
落到一个稳定标识（arxiv 或 doi）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

VERSION = "0.1.0-mvp"

CONFIDENCE_OK = {"high", "med", "low"}

EXIT_OK = 0
EXIT_RED = 1
EXIT_CONFIG = 2


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

# 匹配一个“数字 + 可选量级后缀 + 可选百分号”。
# - 前面不能紧跟字母/下划线/点：避开 ctex2017、v2.0 这类；
# - 量级后缀必须紧贴数字（k/K/M/B），避免把 "47.3 ms" 读成 47.3 毫
# - 百分号允许中间有空格（\% 掩码后就是 " %"）
_NUM_RE = re.compile(
    r"(?<![\w.])"
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"([kKMB])?"
    r"(\s*%)?"
    r"(?![\w])"
)

_MAGNITUDE = {"k": Decimal(1000), "m": Decimal(10 ** 6), "b": Decimal(10 ** 9)}

_FRACTION_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?![\d.])")


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
        d = Decimal(token.replace(",", ""))
    except InvalidOperation:
        return token
    if suffix:
        d = d * _MAGNITUDE[suffix.lower()]
    if percent:
        d = d / Decimal(100)
    return _num_key(d)


def fact_value_keys(value: str) -> set[str]:
    """一个 fact.value 能接受的全部规范数字。

    除了字面数字，还接受：
    - 分数 a/b 的商（10/16 -> 0.625），并按 0~4 位小数放宽四舍五入；
    - 区间 10--16 的两端（NUM_RE 天然拆成两个）；
    - 百分号形式的裸数字（62.5% 同时接受 62.5）。
    """
    keys: set[str] = set()
    text = str(value or "")
    for m in _NUM_RE.finditer(text):
        raw, suffix, pct = m.group(1), m.group(2), bool(m.group(3))
        keys.add(number_key(raw, suffix, pct))
        if pct:
            keys.add(number_key(raw, suffix, False))
    for m in _FRACTION_RE.finditer(text):
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
    "label": 1, "input": 1, "include": 1, "includeonly": 1,
    "includegraphics": 1,
    "begin": 2, "end": 2,                 # \begin{tabular}{p{2cm}l}
    "bibitem": 1, "bibliography": 1, "bibliographystyle": 1,
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


@dataclass
class ScanResult:
    masked: str                     # 抹掉注释/命令/参数后的正文
    bindings: dict[int, list[str]]  # 行号 -> [fact id]
    markers: list[tuple[str, int]]  # (fact id, 行号)
    cites: list[tuple[str, int, int]]  # (key, 行号, 列)


def scan_tex(tex: str) -> ScanResult:
    # ---- pass 1：注释与转义 ----
    masked = list(tex)
    i, n = 0, len(tex)
    while i < n:
        c = tex[i]
        if c == "\\":
            nxt = tex[i + 1] if i + 1 < n else ""
            if nxt == "%":
                masked[i], masked[i + 1] = "%", " "   # 10\% -> "10 %"
                i += 2
                continue
            if nxt in "$&#_{}":
                masked[i], masked[i + 1] = " ", nxt
                i += 2
                continue
            if nxt in ",;:!~ ":
                masked[i], masked[i + 1] = " ", " "
                i += 2
                continue
            i += 2
            continue
        if c == "%":
            while i < n and tex[i] != "\n":
                masked[i] = " "
                i += 1
            continue
        i += 1

    s = "".join(masked)

    # ---- pass 2：引用抽取（在参数被抹掉之前）----
    cites: list[tuple[str, int, int]] = []
    for m in re.finditer(r"\\(?:no)?cite[A-Za-z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}", s):
        if m.group(0).startswith("\\nocite"):
            continue
        for key in m.group(1).split(","):
            key = key.strip()
            if key:
                offset = m.start(1) + m.group(1).find(key)
                cites.append((key, _line_of(s, offset), offset - s.rfind("\n", 0, offset)))

    # ---- pass 3：命令名与结构参数 ----
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

    # ---- pass 4：[[fact:A1]] 形式 ----
    chars = list(masked2)
    for m in _WIKI_FACT_RE.finditer(masked2):
        ids = [x.strip() for x in m.group(1).split(",") if x.strip()]
        line = _line_of(masked2, m.start())
        for fid in ids:
            bindings.setdefault(line, []).append(fid)
            markers.append((fid, line))
        _blank(chars, m.start(), m.end())
    masked2 = "".join(chars)

    return ScanResult(masked=masked2, bindings=bindings, markers=markers, cites=cites)


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


@dataclass
class Fact:
    id: str
    claim: str = ""
    value: str = ""
    source: str = ""
    locator: str = ""
    confidence: str = ""
    derived_from: list = field(default_factory=list)
    supersedes: list = field(default_factory=list)
    note: str = ""
    file: str = ""
    line: int = 0
    value_keys: set = field(default_factory=set)


def load_config(root: Path) -> Config:
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
                locator=str(raw.get("locator") or ""),
                confidence=str(raw.get("confidence") or ""),
                derived_from=[str(x) for x in (raw.get("derived_from") or [])],
                supersedes=[str(x) for x in (raw.get("supersedes") or [])],
                note=str(raw.get("note") or ""),
                file=rel,
                line=_locate_id_line(path, fid),
            )
            if not f.id:
                raise ConfigError("%s 里有一条 fact 缺 id（不准匿名入账）" % path)
            f.value_keys = fact_value_keys(f.value)
            facts.append(f)
    return facts


def load_sections(cfg: Config) -> list[tuple[str, str]]:
    paths = sorted(p for p in cfg.root.glob(cfg.sections_glob) if p.is_file())
    out = []
    for p in paths:
        try:
            out.append((p.relative_to(cfg.root).as_posix(), p.read_text(encoding="utf-8")))
        except UnicodeDecodeError as exc:
            raise ConfigError("%s 不是合法 UTF-8：%s" % (p, exc))
    return out


# --------------------------------------------------------------------------
# bib 解析
# --------------------------------------------------------------------------

_BIB_ENTRY_RE = re.compile(r"@([A-Za-z]+)\s*[{(]\s*([^,\s]+)\s*,")


@dataclass
class BibEntry:
    key: str
    kind: str
    file: str
    line: int
    fields: dict = field(default_factory=dict)

    @property
    def stable_id(self):
        for name in ("arxiv", "eprint", "doi"):
            v = (self.fields.get(name) or "").strip()
            if v:
                return name, v
        return None, ""


def parse_bib(path: Path, root: Path) -> list[BibEntry]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError("读不了参考文献 %s：%s" % (path, exc))
    rel = path.relative_to(root).as_posix()
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
        entries.append(BibEntry(
            key=key, kind=kind, file=rel,
            line=text.count("\n", 0, m.start()) + 1, fields=fields,
        ))
    return entries


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

    def as_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.location:
            d["location"] = self.location
        if self.token:
            d["token"] = self.token
        if self.context:
            d["context"] = self.context
        return d


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

def run_check(cfg: Config, facts: list[Fact]) -> tuple[list[Issue], list[dict], dict]:
    issues: list[Issue] = []
    conflicts: list[dict] = []

    if not facts:
        raise ConfigError("facts 为空（%s 没匹配到任何 fact）——空账不算通过" % cfg.facts_glob)

    seen: dict[str, Fact] = {}
    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        if f.id in seen:
            issues.append(Issue(
                "DUPLICATE_ID", "fact id %r 重复（%s 与 %s）" % (f.id, seen[f.id].file, f.file),
                location=loc, token=f.id))
        else:
            seen[f.id] = f
        if not f.source:
            issues.append(Issue("MISSING_SOURCE_FIELD", "fact %r 缺 source 字段" % f.id,
                                location=loc, token=f.id))
        elif not (cfg.root / f.source).exists():
            issues.append(Issue("MISSING_SOURCE", "fact %r 的 source 不存在：%s" % (f.id, f.source),
                                location=loc, token=f.id))
        if f.confidence not in CONFIDENCE_OK:
            issues.append(Issue(
                "BAD_CONFIDENCE", "fact %r 的 confidence=%r 不合法（只允许 high/med/low）"
                % (f.id, f.confidence), location=loc, token=f.id))
        if not f.value:
            issues.append(Issue("EMPTY_VALUE", "fact %r 的 value 为空（账上没有数）" % f.id,
                                location=loc, token=f.id))

    known = {f.id for f in facts}
    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        for dep in f.derived_from:
            if dep not in known:
                issues.append(Issue(
                    "BAD_DERIVED_FROM", "fact %r 的 derived_from 指向不存在的 id %r" % (f.id, dep),
                    location=loc, token=dep))
        for sup in f.supersedes:
            if sup not in known:
                issues.append(Issue(
                    "BAD_SUPERSEDES", "fact %r 的 supersedes 指向不存在的 id %r" % (f.id, sup),
                    location=loc, token=sup))

    # 冲突：同 claim、不同 value、且互不 supersede
    superseded = {s for f in facts for s in f.supersedes}
    groups: dict[str, list[Fact]] = {}
    for f in facts:
        groups.setdefault(f.claim.strip(), []).append(f)
    for claim, group in groups.items():
        if not claim or len(group) < 2:
            continue
        values = {f.value.strip() for f in group}
        if len(values) < 2:
            continue
        live = [f for f in group if f.id not in superseded]
        if len({f.value.strip() for f in live}) < 2:
            continue
        conflicts.append({
            "claim": claim,
            "ids": [f.id for f in live],
            "values": [f.value for f in live],
            "message": "同一 claim 有不同 value 且都没有 supersedes：%s"
                       % " / ".join("%s=%s" % (f.id, f.value) for f in live),
        })

    summary = {
        "facts": len(facts),
        "ids": len(known),
        "sources_ok": sum(1 for f in facts if f.source and (cfg.root / f.source).exists()),
        "conflicts": len(conflicts),
        "red": len(issues),
    }
    return issues, conflicts, summary


# --------------------------------------------------------------------------
# audit
# --------------------------------------------------------------------------

def _extract_numbers(masked: str, original: str) -> list[dict]:
    orig_lines = original.split("\n")
    out = []
    for ln, line in enumerate(masked.split("\n"), 1):
        for m in _NUM_RE.finditer(line):
            raw, suffix, pct = m.group(1), m.group(2), bool(m.group(3))
            out.append({
                "token": raw + (suffix or "") + ("%" if pct else ""),
                "key": number_key(raw, suffix, pct),
                "line": ln,
                "col": m.start(1) + 1,
                "text": orig_lines[ln - 1].strip() if ln - 1 < len(orig_lines) else "",
            })
    return out


def _resolve_arxiv(arxiv_id: str) -> tuple[str, str]:
    """返回 (status, detail)：verified / not_found / unverified。"""
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"id_list": arxiv_id, "max_results": "1"})
    req = urllib.request.Request(url, headers={"User-Agent": "paperkit/%s" % VERSION})
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
    req = urllib.request.Request(url, headers={"User-Agent": "paperkit/%s" % VERSION})
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

    bib_path = cfg.root / cfg.bib
    if not bib_path.is_file():
        raise ConfigError("找不到参考文献 %s——引用对账无从做起" % bib_path)
    bib_entries = parse_bib(bib_path, cfg.root)
    bib_by_key = {e.key: e for e in bib_entries}

    key_to_facts: dict[str, list[str]] = {}
    for f in facts:
        for k in f.value_keys:
            key_to_facts.setdefault(k, []).append(f.id)
    fact_by_id = {f.id: f for f in facts}

    red: list[Issue] = []
    hints: list[Issue] = []
    numbers_total = 0
    matched = 0
    bound = 0
    unmatched = 0
    usage: dict[str, list[str]] = {f.id: [] for f in facts}
    marker_count: dict[str, int] = {f.id: 0 for f in facts}
    used_keys: dict[str, int] = {}
    unresolved: list[dict] = []

    for rel, text in sections:
        scan = scan_tex(text)
        nums = _extract_numbers(scan.masked, text)
        numbers_total += len(nums)

        for fid, _line in scan.markers:
            if fid in marker_count:
                marker_count[fid] += 1
                if rel not in usage[fid]:
                    usage[fid].append(rel)
            else:
                red.append(Issue(
                    "UNKNOWN_FACT_MARKER",
                    "正文标记了不存在的 fact %r（账上没有这个 id）" % fid,
                    location="%s:%s" % (rel, _line), token=fid))

        for num in nums:
            loc = "%s:%s:%s" % (rel, num["line"], num["col"])
            ids = scan.bindings.get(num["line"])
            if ids:
                allowed: set[str] = set()
                for fid in ids:
                    f = fact_by_id.get(fid)
                    if f:
                        allowed |= f.value_keys
                if num["key"] in allowed:
                    bound += 1
                else:
                    unmatched += 1
                    red.append(Issue(
                        "BOUND_MISMATCH",
                        "该行绑定 %s，但数字 %s 不在其 value 里"
                        % ("/".join(ids), num["token"]),
                        location=loc, token=num["token"], context=num["text"]))
                continue
            if num["key"] in key_to_facts:
                matched += 1
            else:
                unmatched += 1
                red.append(Issue(
                    "UNMATCHED_NUMBER", "数字 %s 回不到任何 fact.value" % num["token"],
                    location=loc, token=num["token"], context=num["text"]))

        for key, line, col in scan.cites:
            used_keys[key] = used_keys.get(key, 0) + 1
            entry = bib_by_key.get(key)
            if entry is None:
                red.append(Issue(
                    "MISSING_CITE", "引用了 bib 里不存在的 key %r" % key,
                    location="%s:%s:%s" % (rel, line, col), token=key,
                    context=text.split("\n")[line - 1].strip() if line - 1 < len(text.split("\n")) else ""))
                continue
            name, value = entry.stable_id
            if name is None:
                red.append(Issue(
                    "BIB_NO_STABLE_ID", "bib 条目 %r 既没有 arxiv 也没有 doi（不可复核）" % key,
                    location="%s:%s" % (entry.file, entry.line), token=key))
                continue
            if resolve:
                if name == "doi":
                    status, detail = _resolve_doi(value)
                else:
                    status, detail = _resolve_arxiv(value)
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
                        location="%s:%s" % (entry.file, entry.line), token=key))

    # 未进 bib 可复核字段的条目（即使没被引用也要说一声）
    for e in bib_entries:
        if e.key not in used_keys and e.stable_id[0] is None:
            hints.append(Issue(
                "BIB_NO_STABLE_ID", "bib 条目 %r 既没有 arxiv 也没有 doi（不可复核）" % e.key,
                location="%s:%s" % (e.file, e.line), token=e.key))

    for f in facts:
        if marker_count.get(f.id, 0) == 0:
            hints.append(Issue(
                "UNUSED_FACT", "账上有、文里没用：fact %r（%s）" % (f.id, f.claim),
                location="%s:%s" % (f.file, f.line or "?"), token=f.id))
    for e in bib_entries:
        if e.key not in used_keys:
            hints.append(Issue(
                "UNUSED_BIB", "bib 里有、文里没引：%r" % e.key,
                location="%s:%s" % (e.file, e.line), token=e.key))

    summary = {
        "facts": len(facts),
        "sections": len(sections),
        "numbers_total": numbers_total,
        "numbers_matched": matched,
        "numbers_bound": bound,
        "numbers_unmatched": unmatched,
        "cites_total": sum(used_keys.values()),
        "cites_unique": len(used_keys),
        "bib_entries": len(bib_entries),
        "bib_used": len([k for k in used_keys if k in bib_by_key]),
        "red": len(red),
        "hints": len(hints),
        "usage": {k: v for k, v in usage.items()},
        "marker_count": marker_count,
    }
    return red, hints, summary, unresolved


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
            if fid in counts:
                counts[fid] += 1
                if rel not in used_sections[fid]:
                    used_sections[fid].append(rel)

    lines = [
        "# Fact 追溯矩阵",
        "",
        "- 项目：%s" % (cfg.title or "（未命名）"),
        "- 生成：paperkit %s" % VERSION,
        "- facts：%d 条；sections：%d 个" % (len(facts), len(sections)),
        "",
        "| fact id | claim | value | source | locator | confidence | 被引用次数 | 被哪些节引用 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for f in facts:
        used = used_sections[f.id]
        lines.append("| %s | %s | %s | %s | %s | %s | %d | %s |" % (
            _cell(f.id), _cell(f.claim), _cell(f.value), _cell(f.source),
            _cell(f.locator), _cell(f.confidence), counts[f.id],
            _cell("、".join(used) if used else "（未使用）"),
        ))
    unused = [f.id for f in facts if counts[f.id] == 0]
    lines += ["", "## 提示", ""]
    lines.append("- 账上有、文里没用：%s" % ("、".join(unused) if unused else "无"))
    lines.append("- 正文引用只在 marker（`\\fact{A1}` 或 `[[fact:A1]]`）里计数。")
    lines.append("")

    rows = [{
        "id": f.id, "claim": f.claim, "value": f.value, "source": f.source,
        "locator": f.locator, "confidence": f.confidence,
        "citations": counts[f.id], "sections": used_sections[f.id],
    } for f in facts]
    return "\n".join(lines), rows


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def run_build(cfg: Config) -> tuple[int, str]:
    if not cfg.build.strip():
        return EXIT_OK, "project.build 为空，按契约跳过编译"
    proc = subprocess.run(cfg.build, shell=True, cwd=str(cfg.root),
                          capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return EXIT_RED, "$ %s\n%s\n构建失败：退出码 %d" % (cfg.build, out.rstrip(), proc.returncode)
    return EXIT_OK, "$ %s\n%s\n构建成功：退出码 0" % (cfg.build, out.rstrip())


# --------------------------------------------------------------------------
# 人读输出
# --------------------------------------------------------------------------

def _print_issue(i: Issue, idx: int) -> str:
    head = " %2d. %-18s %s" % (idx, i.code, i.location or "-")
    lines = [head]
    if i.token:
        lines[0] += "  →  " + i.token
    lines.append("     " + i.message)
    if i.context:
        lines.append("     行: " + i.context[:200])
    return "\n".join(lines)


def _human_check(cfg, facts, issues, conflicts, summary, status) -> str:
    lines = ["== paperkit check ==", "project : %s" % cfg.root,
             "facts   : %d 条（id %d 个，source 均在位 %d 条）"
             % (summary["facts"], summary["ids"], summary["sources_ok"]), ""]
    if issues:
        lines.append("[红] %d 处" % len(issues))
        lines += [_print_issue(i, n) for n, i in enumerate(issues, 1)]
    else:
        lines.append("[红] 0 处 —— 账本身干净")
    if conflicts:
        lines.append("")
        lines.append("[冲突] %d 组（不是错，但必须列出来给人看）" % len(conflicts))
        for c in conflicts:
            lines.append(" - " + c["message"])
    else:
        lines.append("")
        lines.append("[冲突] 0 组")
    lines.append("")
    lines.append("结论：%s（退出码 %d）" % ("有红，必须修" if issues else "绿",
                                          EXIT_RED if issues else EXIT_OK))
    return "\n".join(lines)


def _human_audit(cfg, red, hints, summary, unresolved) -> str:
    lines = [
        "== paperkit audit ==",
        "project : %s" % cfg.root,
        "facts   : %d 条      sections: %d 个" % (summary["facts"], summary["sections"]),
        "numbers : %d 个（matched %d / bound %d / unmatched %d）" % (
            summary["numbers_total"], summary["numbers_matched"],
            summary["numbers_bound"], summary["numbers_unmatched"]),
        "cites   : %d 次调用、%d 个 key；bib %d 条（命中 %d）" % (
            summary["cites_total"], summary["cites_unique"],
            summary["bib_entries"], summary["bib_used"]),
        "",
    ]
    if red:
        lines.append("[红] %d 处（必须修）" % len(red))
        lines += [_print_issue(i, n) for n, i in enumerate(red, 1)]
    else:
        lines.append("[红] 0 处 —— 数字与引用全部有账可循")
    if hints:
        lines.append("")
        lines.append("[提示] %d 条（非红，不拦）" % len(hints))
        for h in hints:
            lines.append(" - %-16s %s %s" % (h.code, h.location, h.message))
    if unresolved:
        lines.append("")
        lines.append("联网核验：")
        for u in unresolved:
            lines.append(" - %-18s %s=%s -> %s（%s）" % (
                u["key"], u["id_type"], u["id"], u["status"], u["detail"]))
    lines.append("")
    lines.append("结论：%d 处红%s（退出码 %d）" % (
        len(red), "" if red else "，绿", EXIT_RED if red else EXIT_OK))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _emit(payload: dict, text: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text)


def _payload(command: str, status: str, code: int, **kw) -> dict:
    d = {"tool": "paperkit", "version": VERSION, "command": command,
         "status": status, "exit": code}
    d.update(kw)
    return d


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="paperkit",
        description="论文数字与引用的机械闸门（check / audit / matrix / build）")
    p.add_argument("--version", action="version", version="paperkit %s" % VERSION)
    sub = p.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("check", "校验事实账：id 唯一、source 在位、confidence 合法、derived_from 有效、同 claim 冲突单列"),
        ("audit", "核心：正文数字回账 + 引用落稳定标识 + 未用事实提示"),
        ("matrix", "生成 audit/matrix.md 追溯矩阵"),
        ("build", "执行 project.build（默认 tectonic main.tex）"),
    ):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("project", nargs="?", default=".", help="项目目录（默认当前目录）")
        sp.add_argument("--json", action="store_true", help="机器可读输出")
        if name == "audit":
            sp.add_argument("--resolve", action="store_true",
                            help="联网核验 arXiv/DOI（超时 5 秒；失败标 unverified 不判红）")
        if name == "matrix":
            sp.add_argument("--out", default=None, help="默认 audit/matrix.md")
    return p


def cmd_check(args) -> int:
    cfg = load_config(Path(args.project))
    facts = load_facts(cfg)
    issues, conflicts, summary = run_check(cfg, facts)
    code = EXIT_RED if issues else EXIT_OK
    text = _human_check(cfg, facts, issues, conflicts, summary, code)
    _emit(_payload("check", "violation" if issues else "ok", code,
                   summary=summary, issues=[i.as_dict() for i in issues],
                   conflicts=conflicts), text, args.json)
    return code


def cmd_audit(args) -> int:
    cfg = load_config(Path(args.project))
    facts = load_facts(cfg)
    sections = load_sections(cfg)
    red, hints, summary, unresolved = run_audit(
        cfg, facts, sections, resolve=getattr(args, "resolve", False))
    code = EXIT_RED if red else EXIT_OK
    text = _human_audit(cfg, red, hints, summary, unresolved)
    _emit(_payload("audit", "violation" if red else "ok", code,
                   summary=summary, issues=[i.as_dict() for i in red],
                   hints=[h.as_dict() for h in hints],
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


def cmd_build(args) -> int:
    cfg = load_config(Path(args.project))
    code, out = run_build(cfg)
    _emit(_payload("build", "ok" if code == EXIT_OK else "violation", code,
                   build=cfg.build, output=out), "== paperkit build ==\n" + out, args.json)
    return code


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"check": cmd_check, "audit": cmd_audit,
                "matrix": cmd_matrix, "build": cmd_build}
    try:
        return handlers[args.command](args)
    except ConfigError as exc:
        if getattr(args, "json", False):
            print(json.dumps(_payload(args.command, "error", EXIT_CONFIG,
                                      message=str(exc)), ensure_ascii=False, indent=2))
        else:
            print("paperkit: 配置/用法错：%s" % exc, file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
