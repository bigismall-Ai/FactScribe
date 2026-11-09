# -*- coding: utf-8 -*-
"""潮汐式改动账（SPEC-TIDE，批 89）。

改动本身是一个事务：**涨**（两个目录的哈希差）、**落**（改后真实文件状态）、
**波及面**（\\input/\\include 反向引用闭包）全部由工具派生，人不提供任何清单。

闭合＝ ``paired ∧ hash_ok ∧ pass_all``；闭合才写 append-only 账本与派生视图，
否则全退（不落盘、退出码 1）。

保护面的抽取与判据**复用** ``protect``：``_code_view`` / ``_heading_items`` /
``compare``，不改 ``audit`` / ``style`` / ``protect`` 的任何既有判据与退出码。
"""
from __future__ import annotations

import difflib
import hashlib
import json
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConfigError
from .constants import EXIT_OK, EXIT_RED, SEV_RED
from .protect import _code_view, _heading_items
from .protect import compare as compare_protect

RISE = "rise"
FALL = "fall"
VERDICT = "verdict"
_KINDS = (RISE, FALL, VERDICT)

LEDGER_NAME = "tide-events.ndjson"
VIEW_NAME = "tide-ledger.md"


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------

@dataclass
class Rise:
    path: str
    before: str | None
    after: str | None
    lines: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"event": RISE, "path": self.path, "before": self.before,
                "after": self.after, "lines": list(self.lines),
                "sections": list(self.sections)}


@dataclass
class Fall:
    path: str
    exists: bool
    sha256: str | None

    def as_dict(self) -> dict:
        return {"event": FALL, "path": self.path, "exists": self.exists,
                "sha256": self.sha256}


@dataclass
class TideResult:
    before: Path
    after: Path
    tx: str
    status: str
    paired: bool
    hash_ok: bool
    pass_all: bool
    rises: list[Rise]
    falls: list[Fall]
    affect: list[str]
    findings: list
    reasons: list[str]
    ledger_path: Path
    view_path: Path
    view_written: bool = False
    rows: list[dict] = field(default_factory=list)
    appends: int = 0

    @property
    def closed(self) -> bool:
        return self.status == "commit"

    @property
    def exit_code(self) -> int:
        return EXIT_OK if self.closed else EXIT_RED

    def criteria(self) -> dict:
        return {"paired": self.paired, "hash_ok": self.hash_ok,
                "pass_all": self.pass_all}


# --------------------------------------------------------------------------
# 哈希与库存
# --------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bytes(path: Path, rel: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ConfigError("读不了 %s：%s" % (rel, exc)) from exc


def _text(root: Path, rel: str) -> str | None:
    path = root / rel
    if not path.is_file():
        return None
    try:
        return _read_bytes(path, rel).decode("utf-8")
    except UnicodeDecodeError:
        return None


def _inventory(root: Path, exclude: set[str]) -> dict[str, str]:
    """普通文件相对路径 → 字节 sha256；跳过隐藏路径、顶层 audit/ 与产出本体。"""
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        if any(part.startswith(".") for part in parts):
            continue
        if parts[0] == "audit":
            continue
        if str(p.resolve()) in exclude:
            continue
        out[rel] = _sha256_bytes(_read_bytes(p, rel))
    return out


# --------------------------------------------------------------------------
# 涨：行区间与章节
# --------------------------------------------------------------------------

def _span(start: int, end: int) -> str:
    return str(start) if start == end else "%d-%d" % (start, end)


def _diff_spans(before: str, after: str) -> list[tuple[int, int]]:
    """行级差异 → 合并后的行区间（改后侧行号；纯删除用改前侧行号）。"""
    a = before.splitlines()
    b = after.splitlines()
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    spans: list[tuple[int, int]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("replace", "insert"):
            if j2 > j1:
                spans.append((j1 + 1, j2))
        elif i2 > i1:
            spans.append((i1 + 1, i2))
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _sections_of(text: str, spans: list[tuple[int, int]]) -> list[str]:
    if not text or not spans:
        return []
    headings = _heading_items(_code_view(text))
    out: list[str] = []
    for start, _end in spans:
        chosen = None
        for head in headings:
            if head.line <= start:
                chosen = head
            else:
                break
        if chosen is not None and chosen.title and chosen.title not in out:
            out.append(chosen.title)
    return out


def _touch(before_text: str | None, after_text: str | None
           ) -> tuple[list[str], list[str]]:
    if before_text is None and after_text is None:
        return [], []
    if before_text is None:
        n = len(after_text.splitlines())
        spans = [(1, n)] if n else []
        return [_span(*s) for s in spans], _sections_of(after_text, spans)
    if after_text is None:
        n = len(before_text.splitlines())
        spans = [(1, n)] if n else []
        return [_span(*s) for s in spans], _sections_of(before_text, spans)
    spans = _diff_spans(before_text, after_text)
    return [_span(*s) for s in spans], _sections_of(after_text, spans)


def _rises(before: Path, after: Path, bfiles: dict[str, str],
           afiles: dict[str, str]) -> list[Rise]:
    out: list[Rise] = []
    for rel in sorted(set(bfiles) | set(afiles)):
        bhash = bfiles.get(rel)
        ahash = afiles.get(rel)
        if bhash == ahash:
            continue
        lines: list[str] = []
        sections: list[str] = []
        if rel.endswith(".tex"):
            lines, sections = _touch(_text(before, rel), _text(after, rel))
        out.append(Rise(path=rel, before=bhash, after=ahash,
                        lines=lines, sections=sections))
    return out


# --------------------------------------------------------------------------
# 落：改后真实文件状态（重新读盘）
# --------------------------------------------------------------------------

def _falls(after: Path, rises: list[Rise]) -> list[Fall]:
    out: list[Fall] = []
    for rise in rises:
        path = after / rise.path
        exists = path.is_file()
        digest = (_sha256_bytes(_read_bytes(path, rise.path))
                  if exists else None)
        out.append(Fall(path=rise.path, exists=exists, sha256=digest))
    return out


# --------------------------------------------------------------------------
# 波及面：\input / \include 反向闭包
# --------------------------------------------------------------------------

_INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]*)\}")


def _ref_candidates(base: str, raw: str) -> list[str]:
    """\\input 目标的两个候选：项目根相对（LaTeX 默认）→ 引用文件目录相对。"""
    name = raw.strip()
    if not name or name.startswith("/"):
        return []
    if not name.endswith(".tex"):
        name += ".tex"
    out = [posixpath.normpath(name)]
    if base:
        alt = posixpath.normpath(posixpath.join(base, name))
        if alt not in out:
            out.append(alt)
    return out


def _referrers(before: Path, after: Path, bfiles: dict[str, str],
               afiles: dict[str, str]) -> dict[str, set[str]]:
    known = set(bfiles) | set(afiles)
    refs: dict[str, set[str]] = {}
    for root, files in ((before, bfiles), (after, afiles)):
        for rel in sorted(files):
            if not rel.endswith(".tex"):
                continue
            text = _text(root, rel)
            if text is None:
                continue
            base = posixpath.dirname(rel)
            for match in _INPUT_RE.finditer(_code_view(text)):
                for target in _ref_candidates(base, match.group(1)):
                    if target in known:
                        refs.setdefault(target, set()).add(rel)
                        break
    return refs


def _closure(changed: set[str], refs: dict[str, set[str]]) -> list[str]:
    seen = set(changed)
    stack = list(changed)
    while stack:
        cur = stack.pop()
        for referrer in sorted(refs.get(cur, ())):
            if referrer not in seen:
                seen.add(referrer)
                stack.append(referrer)
    return sorted(seen)


# --------------------------------------------------------------------------
# 账本读写
# --------------------------------------------------------------------------

def _read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError("读不了账本 %s：%s" % (path, exc)) from exc
    events: list[dict] = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ConfigError("账本第 %d 行不是合法 JSON：%s"
                              % (lineno, exc)) from exc
        if not isinstance(event, dict) or event.get("event") not in _KINDS:
            raise ConfigError("账本第 %d 行事件类型不合法" % lineno)
        if not event.get("tx"):
            raise ConfigError("账本第 %d 行缺 tx" % lineno)
        events.append(event)
    return events


def _event_line(event: dict) -> str:
    return json.dumps(event, sort_keys=True, ensure_ascii=False)


def _append_ledger(path: Path, events: list[dict]) -> int:
    """append-only 追加；整行去重（同一事务重复跑不重复记账）。"""
    lines = [_event_line(e) for e in events]
    existing: set[str] = set()
    if path.exists():
        try:
            existing = {line for line in
                        path.read_text(encoding="utf-8").splitlines()
                        if line.strip()}
        except OSError as exc:
            raise ConfigError("读不了账本 %s：%s" % (path, exc)) from exc
    new = [line for line in lines if line not in existing]
    if not new:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for line in new:
            fh.write(line + "\n")
    return len(new)


def _tx_id(rises: list[Rise], falls: list[Fall]) -> str:
    blob = json.dumps({"rises": [r.as_dict() for r in rises],
                       "falls": [f.as_dict() for f in falls]},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _tx_events(tx: str, rises: list[Rise], falls: list[Fall],
               affect: list[str], status: str) -> list[dict]:
    events: list[dict] = []
    for rise in rises:
        event = rise.as_dict()
        event["tx"] = tx
        events.append(event)
    for fall in falls:
        event = fall.as_dict()
        event["tx"] = tx
        events.append(event)
    events.append({"event": VERDICT, "tx": tx, "status": status,
                   "rises": len(rises), "falls": len(falls),
                   "affect": list(affect)})
    return events


# --------------------------------------------------------------------------
# 判据：paired / hash_ok
# --------------------------------------------------------------------------

def _paired(rises: list[Rise], falls: list[Fall], ledger: list[dict]) -> tuple:
    reasons: list[str] = []
    rise_paths = sorted(r.path for r in rises)
    fall_paths = sorted(f.path for f in falls)
    ok = rise_paths == fall_paths

    groups: dict[str, dict[str, set]] = {}
    for event in ledger:
        if event.get("event") not in (RISE, FALL):
            continue
        group = groups.setdefault(event.get("tx"),
                                  {RISE: set(), FALL: set()})
        group[event["event"]].add(event.get("path"))
    for tx in sorted(groups):
        missing = groups[tx][RISE] - groups[tx][FALL]
        if missing:
            ok = False
            reasons.append("账本事务 %s 有涨无落（漏报）：%s"
                           % (tx, "、".join(sorted(missing))))
    return ok, reasons


def _hash_ok(before: Path, after: Path, rises: list[Rise],
             falls: list[Fall], ledger: list[dict], tx: str) -> tuple:
    reasons: list[str] = []
    ok = True
    for fall in falls:
        if not fall.exists:
            ok = False
            reasons.append("落的目标缺失：%s（改后文件不存在，哈希不可复算）"
                           % fall.path)
            continue
        actual = _sha256_bytes(_read_bytes(after / fall.path, fall.path))
        if actual != fall.sha256:
            ok = False
            reasons.append("落哈希复算不符：%s" % fall.path)

    # 账链连续性：账本里既有的落记录描述的是「改前状态」，必须与改前目录一致。
    prior: dict[str, dict] = {}
    for event in ledger:
        if event.get("event") != FALL or event.get("tx") == tx:
            continue
        prior[event.get("path")] = event
    for rise in rises:
        event = prior.get(rise.path)
        if event is None:
            continue
        path = before / rise.path
        actual = (_sha256_bytes(_read_bytes(path, rise.path))
                  if path.is_file() else None)
        if event.get("sha256") != actual:
            ok = False
            reasons.append("账本既有落与改前目录不符：%s（账链断了或账被改过）"
                           % rise.path)
    return ok, reasons


# --------------------------------------------------------------------------
# 派生视图
# --------------------------------------------------------------------------

_MARK = {True: "✓", False: "✗"}


def render_ledger(result: TideResult) -> str:
    lines = [
        "# 潮汐账（tide ledger）",
        "",
        "- 事务：%s" % result.tx,
        "- 涨：%d   落：%d   波及面：%d   事件：%d" % (
            len(result.rises), len(result.falls), len(result.affect),
            len(result.rises) + len(result.falls) + 1),
        "- 判定：paired %s   hash_ok %s   pass_all %s" % (
            _MARK[result.paired], _MARK[result.hash_ok],
            _MARK[result.pass_all]),
        "- 状态：%s" % result.status,
        "",
        "| 文件 | 改前(前8) | 改后(前8) | 波及面 | paired | hash_ok | pass_all |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in result.rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            row["path"],
            (row["before"] or "")[:8] or "—",
            (row["after"] or "")[:8] or "—",
            "、".join(row["affect"]) or "—",
            _MARK[row["paired"]], _MARK[row["hash_ok"]],
            _MARK[row["pass_all"]]))
    lines.append("")
    return "\n".join(lines)


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def render_human(result: TideResult) -> str:
    lines = [
        "== factscribe tide ==",
        "事务：%s    状态：%s" % (result.tx, result.status),
        "涨：%d   落：%d   波及面：%d   事件：%d" % (
            len(result.rises), len(result.falls), len(result.affect),
            len(result.rises) + len(result.falls) + 1),
        "判定：paired %s   hash_ok %s   pass_all %s" % (
            _MARK[result.paired], _MARK[result.hash_ok],
            _MARK[result.pass_all]),
    ]
    if result.reasons:
        lines.append("未闭合：")
        lines += ["- " + reason for reason in result.reasons]
    if result.closed:
        lines.append("账本：%s（append-only）"
                     % _rel(result.ledger_path, result.after))
        if result.view_written:
            lines.append("派生视图：%s" % _rel(result.view_path, result.after))
    else:
        lines.append("全退：未写账本、未产出派生视图。")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------

def run_tide(before: Path | str, after: Path | str,
             out: Path | str | None = None) -> TideResult:
    before = Path(before)
    after = Path(after)
    for flag, path in (("--before", before), ("--after", after)):
        if not path.is_dir():
            raise ConfigError("%s 目录不存在或不是目录：%s" % (flag, path))

    ledger_path = Path(out) if out is not None else after / "audit" / LEDGER_NAME
    view_path = after / "audit" / VIEW_NAME
    exclude = {str(ledger_path.resolve()), str(view_path.resolve())}

    bfiles = _inventory(before, exclude)
    afiles = _inventory(after, exclude)
    rises = _rises(before, after, bfiles, afiles)
    falls = _falls(after, rises)
    tx = _tx_id(rises, falls)
    ledger = _read_ledger(ledger_path)

    paired, paired_reasons = _paired(rises, falls, ledger)
    hash_ok, hash_reasons = _hash_ok(before, after, rises, falls, ledger, tx)

    refs = _referrers(before, after, bfiles, afiles)
    affect = _closure({r.path for r in rises}, refs)
    affect_set = set(affect)
    protect_result = compare_protect(before, after)
    hard = [f for f in protect_result.findings
            if f.severity == SEV_RED and f.file in affect_set]
    pass_all = not hard

    reasons = []
    reasons += paired_reasons
    reasons += hash_reasons
    if not pass_all:
        codes = sorted({f.code for f in hard})
        reasons.append("波及面内保护面有 %d 条红：%s"
                       % (len(hard), "、".join(codes)))

    status = "commit" if (paired and hash_ok and pass_all) else "rollback"
    closed = status == "commit"

    rows = []
    for rise in rises:
        fall = next((f for f in falls if f.path == rise.path), None)
        rows.append({
            "path": rise.path,
            "before": rise.before,
            "after": rise.after,
            "affect": _closure({rise.path}, refs),
            "paired": fall is not None,
            "hash_ok": bool(fall and fall.exists and fall.sha256),
            "pass_all": not any(f.file == rise.path for f in hard),
        })

    result = TideResult(before=before, after=after, tx=tx, status=status,
                        paired=paired, hash_ok=hash_ok, pass_all=pass_all,
                        rises=rises, falls=falls, affect=affect,
                        findings=hard, reasons=reasons,
                        ledger_path=ledger_path, view_path=view_path,
                        rows=rows)

    if closed:
        events = _tx_events(tx, rises, falls, affect, status)
        events[-1].update({"paired": paired, "hash_ok": hash_ok,
                           "pass_all": pass_all})
        if rises:
            result.appends = _append_ledger(ledger_path, events)
        if out is None:
            view_path.parent.mkdir(parents=True, exist_ok=True)
            view_path.write_text(render_ledger(result), encoding="utf-8")
            result.view_written = True
    return result
