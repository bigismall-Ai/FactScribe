# -*- coding: utf-8 -*-
"""改写验收一条命令（SPEC-REVIEW，批 114）。

``review`` 是 ``protect + style --diff + tide`` 的组合，不新增判据：

1. **保护面**：复用 ``protect.compare``——事实/数字/引用/公式/表格/交叉引用；
2. **复检**：复用 ``style`` 的 ``analyze`` + ``filter_new_findings``——
   只算「改前没有、改后有」的新增违规；
3. **闭合**：复用 ``tide.run_tide``——涨/落/波及面三条件。

判定（fail-closed）::

    保护面有红                  → 拒绝（exit 1）
    tide 不闭合                 → 拒绝（exit 1）
    新增违规 > --allow-new       → 需复核（exit 3）
    三项全过                     → 通过（exit 0）

``--snapshot`` 只在判定为「通过」时存快照，其余不存。
本模块只做编排，不改三条底层命令的判据与退出码。
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConfigError, load_config, load_sections
from .constants import EXIT_OK, EXIT_RED, EXIT_YELLOW, SEV_RED
from .protect import ProtectResult
from .protect import compare as compare_protect
from .style import (StyleResult, analyze, filter_new_findings,
                    load_style_rules)
from .tide import SnapshotResult, TideResult, run_tide, save_snapshot

VERDICT_PASS = "pass"
VERDICT_REJECT = "reject"
VERDICT_REVIEW = "needs_review"

_VERDICT_LABEL = {
    VERDICT_PASS: "通过",
    VERDICT_REJECT: "拒绝",
    VERDICT_REVIEW: "需复核",
}
_MARK = {True: "✓", False: "✗"}


@dataclass
class ReviewResult:
    before: Path
    after: Path
    allow_new: int
    protect: ProtectResult
    style: StyleResult
    baseline_findings: int
    tide: TideResult
    verdict: str
    reasons: list[str] = field(default_factory=list)
    snapshot_requested: bool = False
    snapshot_saved: bool = False
    snapshot: SnapshotResult | None = None

    @property
    def exit_code(self) -> int:
        return {VERDICT_PASS: EXIT_OK, VERDICT_REJECT: EXIT_RED,
                VERDICT_REVIEW: EXIT_YELLOW}[self.verdict]

    @property
    def red_findings(self) -> list:
        return [f for f in self.protect.findings if f.severity == SEV_RED]

    @property
    def new_findings(self) -> list:
        return list(self.style.findings)

    def verdict_label(self) -> str:
        return _VERDICT_LABEL[self.verdict]


def run_review(before: Path | str, after: Path | str, *,
               allow_new: int = 0,
               snapshot: Path | str | None = None) -> ReviewResult:
    """跑保护面、复检、闭合三项，合成一个 final verdict（fail-closed）。"""
    before = Path(before)
    after = Path(after)
    for flag, path in (("--before", before), ("--after", after)):
        if not path.is_dir():
            raise ConfigError("%s 目录不存在或不是目录：%s" % (flag, path))
    if allow_new < 0:
        raise ConfigError("--allow-new 不能为负：%d" % allow_new)

    # 1) 保护面：protect 的抽取与判据原样复用。
    protect_result = compare_protect(before, after)

    # 2) 复检：style 的 analyze + filter_new_findings 原样复用。
    before_cfg = load_config(before)
    after_cfg = load_config(after)
    before_sections = load_sections(before_cfg)
    after_sections = load_sections(after_cfg)
    rules, rules_path = load_style_rules(after_cfg.root)
    after_style = analyze(after_cfg, after_sections, rules,
                          rules_path=rules_path,
                          before=(before_cfg, before_sections))
    baseline = analyze(before_cfg, before_sections, rules,
                       rules_path=rules_path)
    style_result = filter_new_findings(after_style, baseline)

    # 3) 闭合：tide 的涨/落/波及面判定原样复用。账本放临时目录，
    #    让 review 对文档树只读（不往 --after 的 audit/ 里写账）。
    with tempfile.TemporaryDirectory(prefix="factscribe-review-") as tmp:
        tide_result = run_tide(before, after,
                               Path(tmp) / "tide-events.ndjson")

    reasons: list[str] = []
    red = [f for f in protect_result.findings if f.severity == SEV_RED]
    reject = False
    if red:
        reject = True
        codes = "、".join(sorted({f.code for f in red}))
        reasons.append("保护面有 %d 条红：%s" % (len(red), codes))
    if not tide_result.closed:
        reject = True
        reasons.append("tide 未闭合：%s" % ("；".join(tide_result.reasons)
                                            or "三条件未全过"))

    if reject:
        verdict = VERDICT_REJECT
    elif len(style_result.findings) > allow_new:
        verdict = VERDICT_REVIEW
        reasons.append("新增违规 %d 条 > 允许 %d 条"
                       % (len(style_result.findings), allow_new))
    else:
        verdict = VERDICT_PASS

    result = ReviewResult(
        before=before, after=after, allow_new=allow_new,
        protect=protect_result, style=style_result,
        baseline_findings=len(baseline.findings), tide=tide_result,
        verdict=verdict, reasons=reasons,
        snapshot_requested=snapshot is not None)

    # 只有「通过」才存快照；其余一律不存（fail-closed）。
    if snapshot is not None and verdict == VERDICT_PASS:
        result.snapshot = save_snapshot(after, Path(snapshot))
        result.snapshot_saved = True
    return result


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

def _protect_summary(result: ReviewResult) -> dict:
    counts = {"red": 0, "yellow": 0, "info": 0}
    for f in result.protect.findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    counts["total"] = len(result.protect.findings)
    return counts


def payload(result: ReviewResult) -> dict:
    """三块明细 + 最终判定；调用方再套 ``_payload`` 的公共字段。"""
    p = _protect_summary(result)
    return {
        "before": str(result.before),
        "after": str(result.after),
        "allow_new": result.allow_new,
        "verdict": result.verdict,
        "verdict_label": result.verdict_label(),
        "reasons": list(result.reasons),
        "protect": {
            "red": p["red"], "yellow": p["yellow"],
            "info": p["info"], "total": p["total"],
            "findings": [f.as_dict() for f in result.protect.findings],
        },
        "style": {
            "new_findings": len(result.style.findings),
            "allow_new": result.allow_new,
            "baseline_findings": result.baseline_findings,
            "rejected": result.verdict == VERDICT_REVIEW,
            "findings": [f.as_dict() for f in result.style.findings],
        },
        "tide": {
            "closed": result.tide.closed,
            "status": result.tide.status,
            "paired": result.tide.paired,
            "hash_ok": result.tide.hash_ok,
            "pass_all": result.tide.pass_all,
            "criteria": result.tide.criteria(),
            "rises": len(result.tide.rises),
            "falls": len(result.tide.falls),
            "affect": len(result.tide.affect),
            "reasons": list(result.tide.reasons),
        },
        "snapshot": {
            "requested": result.snapshot_requested,
            "saved": result.snapshot_saved,
            "id": result.snapshot.snapshot_id if result.snapshot else None,
            "short": result.snapshot.short if result.snapshot else None,
            "files": result.snapshot.files if result.snapshot else None,
            "bytes": result.snapshot.bytes if result.snapshot else None,
            "store": str(result.snapshot.store) if result.snapshot else None,
        },
    }


def render_human(result: ReviewResult) -> str:
    lines = [
        "== factscribe review ==",
        "改写前：%s" % result.before,
        "改写后：%s" % result.after,
        "判定：%s（退出码 %d）" % (result.verdict_label(), result.exit_code),
    ]
    if result.reasons:
        lines.append("原因：%s" % "；".join(result.reasons))

    p = _protect_summary(result)
    lines.append("")
    lines.append("保护面：红 %d   黄 %d   信息 %d" % (p["red"], p["yellow"],
                                                     p["info"]))
    if not result.protect.findings:
        lines.append("  （全部一致）")
    for f in result.protect.findings:
        loc = "%s:%d" % (f.file, f.line) if f.line else f.file
        lines.append("  [%s] %s %s: %s"
                     % ({"red": "红", "yellow": "黄", "info": "信息"}
                        .get(f.severity, f.severity),
                        f.code, loc, f.message))

    lines.append("")
    lines.append("复检（只算新增）：改前 %d 处 → 新增 %d 处（允许 %d）"
                 % (result.baseline_findings, len(result.style.findings),
                    result.allow_new))
    if not result.style.findings:
        lines.append("  （没有新增违规）")
    for f in result.style.findings:
        lines.append("  [黄] %s %s:%d: %s"
                     % (f.code, f.file, f.line, f.text))

    lines.append("")
    lines.append("闭合：paired %s   hash_ok %s   pass_all %s"
                 % (_MARK[result.tide.paired], _MARK[result.tide.hash_ok],
                    _MARK[result.tide.pass_all]))
    lines.append("  涨 %d   落 %d   波及面 %d"
                 % (len(result.tide.rises), len(result.tide.falls),
                    len(result.tide.affect)))
    for reason in result.tide.reasons:
        lines.append("  - %s" % reason)

    lines.append("")
    if result.snapshot_saved and result.snapshot is not None:
        lines.append("快照：已保存 %s（%d 个文件，%d 字节）→ %s"
                     % (result.snapshot.short, result.snapshot.files,
                        result.snapshot.bytes, result.snapshot.store))
    elif result.snapshot_requested:
        lines.append("快照：未保存（判定不是「通过」，不落快照）")
    return "\n".join(lines)
