# -*- coding: utf-8 -*-
"""人读文本渲染、追溯矩阵与 JSON 载荷。"""
from __future__ import annotations

import json

from .audit import Issue
from .config import Config, ConfigError
from .constants import (EXIT_CONFIG, EXIT_INTERNAL, EXIT_OK, EXIT_RED,
                        EXIT_YELLOW, SCHEMA_VERSION, SEV_RED, SEV_YELLOW,
                        VERSION)
from .facts import Fact
from .texscan import scan_tex

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
