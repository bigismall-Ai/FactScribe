# -*- coding: utf-8 -*-
"""证据钢印：人钉清单、机器执行（SPEC-EVIDENCE-STAMP，批 131）。

两条判据，都是红（阻断）：

* ``REQUIRED_EVIDENCE_MISSING``：`[evidence]` 声明的节里找不到某个
  ``\\fact{id}``；
* ``EVIDENCE_DROPPED``：改前本节有的 ``\\fact{id}``，改后本节没有
  （只在 ``style --diff`` / ``review`` 有 before 时运行，不依赖声明）。

硬边界：

* **只执行人写的清单**：声明的 id 一个不推导、不排序、不补全；机器不判断
  「哪个数字重要」（见规范 §6）；
* **存在性判据**：复用 ``texscan.scan_tex`` 的 markers——注释、verbatim、
  批注宏里的 ``\\fact{}`` 不算引用，与本工具其它数字判据同一套遮罩；
* **不新增退出码**：红＝1，与 ``protect`` 同一套；本模块只服务 ``style`` /
  ``review``，不改 ``audit``。
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import Config, ConfigError, load_facts
from .texscan import scan_tex

MISSING_CODE = "REQUIRED_EVIDENCE_MISSING"
DROPPED_CODE = "EVIDENCE_DROPPED"
EVIDENCE_CODES = (MISSING_CODE, DROPPED_CODE)


@dataclass(frozen=True)
class EvidenceIssue:
    """一条证据缺钉：style 负责转成 Finding（红）。"""

    code: str
    file: str
    line: int
    text: str
    suggestion: str
    metric: str = "evidence"

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": "red", "file": self.file,
                "line": self.line, "text": self.text,
                "suggestion": self.suggestion}


def fact_ids(text: str) -> list[tuple[str, int]]:
    """正文里 ``\\fact{id}`` 的 (id, 行号)，按出现顺序、按 id 去重。

    ``texscan`` 已经剥掉注释与 verbatim；这里只做去重（同一节重复引用同一
    事实是正常写法，存在性判据只看「有没有」）。
    """
    seen: set[str] = set()
    out: list[tuple[str, int]] = []
    for fid, line in scan_tex(text).markers:
        key = str(fid).strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((str(fid).strip(), line))
    return out


def _fact_index(facts: list) -> dict:
    return {f.id_key: f for f in facts}


def _safe_facts(cfg: Config) -> list:
    """账读不出来时不让 style 崩：message 写「账里没有这条 fact」，仍然红。"""
    try:
        return load_facts(cfg)
    except ConfigError:
        return []


def _describe(fid: str, facts: dict[str, object]) -> str:
    fact = facts.get(fid.casefold())
    if fact is None:
        return "账里没有这条 fact"
    claim = str(getattr(fact, "claim", "") or "—")
    value = str(getattr(fact, "value", "") or "—")
    return "claim：%s；value：%s" % (claim, value)


def check_evidence(cfg: Config, sections: list[tuple[str, str]],
                   before: tuple[Config, list[tuple[str, str]]] | None = None
                   ) -> tuple[list[EvidenceIssue], dict]:
    """跑两条判据；返回 (issues, 读数明细)。

    ``sections`` 是 ``load_sections`` 的 [(相对路径, 正文)]；``before`` 是
    ``style --diff`` / ``review`` 的 (改前 Config, 改前 sections)。
    """
    issues: list[EvidenceIssue] = []
    by_key: dict[str, tuple[str, str]] = {}
    for rel, text in sections:
        by_key.setdefault(rel.rsplit("/", 1)[-1].rsplit(".", 1)[0], (rel, text))

    declared = dict(getattr(cfg, "evidence_sections", {}) or {})
    unknown = [key for key in declared if key not in by_key]
    facts = _fact_index(_safe_facts(cfg)) if declared else {}

    # ---- 1. REQUIRED_EVIDENCE_MISSING：只查声明过的节 ----
    missing = 0
    for key, ids in declared.items():
        if key not in by_key:
            continue
        rel, text = by_key[key]
        present = {fid for fid, _line in fact_ids(text)}
        present_keys = {fid.casefold() for fid in present}
        for fid in ids:
            if fid.casefold() in present_keys:
                continue
            missing += 1
            issues.append(EvidenceIssue(
                MISSING_CODE, rel, 1,
                "节 %s 缺必需证据 %s（%s）"
                % (key, fid, _describe(fid, facts)),
                "把 %s 的 `\\fact{%s}` 绑定补回本节正文（值与账本逐字一致）；"
                "不许改 id、不许改数字、不许把论点搬到别节冒充。"
                % (fid, fid)))

    # ---- 2. EVIDENCE_DROPPED：只在有 before 时跑，不依赖声明 ----
    dropped = 0
    if before is not None:
        before_cfg, before_sections = before
        after_map = {rel: text for rel, text in sections}
        before_facts = facts or _fact_index(_safe_facts(before_cfg))
        for rel, text in before_sections:
            after_text = after_map.get(rel, "")
            after_ids = {fid.casefold() for fid, _line in fact_ids(after_text)}
            for fid, _line in fact_ids(text):
                if fid.casefold() in after_ids:
                    continue
                dropped += 1
                issues.append(EvidenceIssue(
                    DROPPED_CODE, rel, 1,
                    "节 %s 丢了改前已有的证据 %s（%s）"
                    % (rel, fid, _describe(fid, before_facts)),
                    "把 `\\fact{%s}` 与对应数字补回本节；若确属结构调整，先改 "
                    "[evidence] 清单与账，不许用 nearly/most/some 这类定性说法顶替。"
                    % fid))

    details = {
        "declared": [{"section": key, "ids": list(ids)}
                     for key, ids in declared.items()],
        "unknown_sections": unknown,
        "missing": missing,
        "dropped": dropped,
    }
    return issues, details
