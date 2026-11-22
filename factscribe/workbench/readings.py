# -*- coding: utf-8 -*-
"""工作台的另外两条只读读数：证据锁（G1）＋写作简报（G3）。

口径纪律（与四步链同一条原则）：**真闸算一次，界面与 MCP 都只做读数**。

* ``evidence_gate`` 复用 ``factscribe.evidence`` 的原件（``lock_check`` /
  ``unfrozen_info`` / ``log_state``），与 CLI 的 ``factscribe_evidence_status``
  同一条路——不另算一遍哈希，也不另判一次冻结。
* ``brief_reading`` 复用 ``factscribe.brief``（CLI ``factscribe brief`` 同一条路），
  只在其上**只增不改**地补三组读数：每节的「可引用／已绑／未绑」、每条事实的
  「绑在哪些节」、以及账上的「已绑／未绑」计数。

两者都只读：不写盘、不改稿、不改冻结件。
"""
from __future__ import annotations

from pathlib import Path

from ..brief import CONSTRAINTS, bound_fact_ids, build_brief, payload
from ..config import ConfigError, load_config, load_sections
from ..evidence import (canonical_sha256, lock_check, log_state, read_lock,
                         unfrozen_info)


def evidence_gate(disk: Path) -> dict:
    """证据锁读数：冻结状态／差异明细／最后一条日志（只读）。

    形状对齐 CLI MCP 的 ``factscribe_evidence_status``：
    ``frozen`` / ``entries`` / ``sha256`` / ``mismatch`` / ``unfrozen`` /
    ``diff{added,removed,moved}`` / ``last_log{action,reason,at}``。
    读不动就结构化报错，绝不抛 500。
    """
    disk = Path(disk)
    base = {"ok": True, "disk": str(disk)}
    try:
        cfg = load_config(disk)
    except ConfigError as exc:
        return {**base, "ok": False, "code": "CONFIG_INVALID", "error": str(exc)}
    except (OSError, ValueError) as exc:
        return {**base, "ok": False, "code": "READ_FAILED",
                "error": "读项目失败：%s" % exc}

    lock = None
    try:
        lock = read_lock(disk)
    except Exception:  # noqa: BLE001 - 锁读不动不该掀翻整页
        lock = None
    declared = dict(getattr(cfg, "evidence_sections", {}) or {})
    try:
        current_sha = canonical_sha256(declared)
    except Exception:  # noqa: BLE001
        current_sha = ""
    try:
        mismatch = lock_check(cfg)
    except Exception:  # noqa: BLE001
        mismatch = None
    try:
        unfrozen = unfrozen_info(disk)
        log = log_state(disk)
    except Exception:  # noqa: BLE001
        unfrozen, log = None, {}
    diff = (mismatch or {}).get("diff") or {"added": [], "removed": [], "moved": []}
    return {
        **base,
        "defined": bool(getattr(cfg, "evidence_defined", False)),
        "declared_sections": len(declared),
        "declared": {key: list(value)
                     for key, value in sorted(declared.items())},
        "frozen": bool(lock),
        "entries": int((lock or {}).get("entries") or 0),
        "sha256": (lock or {}).get("sha256", ""),
        "sha256_short": ((lock or {}).get("sha256") or "")[:8],
        "current_sha256": current_sha,
        "current_sha256_short": current_sha[:8],
        # mismatch＝None 表示「冻结件与当前清单一致」；不一致时带明细。
        "mismatch": mismatch,
        "diff": diff,
        "unfrozen": unfrozen,
        "log": log,
        "last_log": {"action": str(log.get("action") or ""),
                     "reason": str(log.get("reason") or ""),
                     "at": str(log.get("at") or ""),
                     "count": int(log.get("count") or 0)},
    }


def brief_reading(disk: Path, section: str = "") -> dict:
    """写作简报读数：可引用的事实、已绑的、还没绑的（只读）。

    口径复用 ``factscribe.brief``（CLI ``factscribe brief`` 同一条路）：
    事实表来自账，节清单来自主文件的 input 顺序，术语表来自词表。

    本函数**只增不改**：brief 原有的 ``sections`` / ``facts`` / ``terms``
    字段一字不动，另加三组读数，让宿主不必自己判断「能不能引」：

    * 每节：``usable``（可引用）、``bound``（已绑）、``unbound``（可引用
      但还没绑）、``reconciled``（声明是否都绑上了）；
    * 每条事实：``bound_in``（绑在哪些节）、``status``（bound / unbound）；
    * 汇总：``counts``（账上总数／已绑／未绑）。
    """
    disk = Path(disk)
    base = {"ok": True, "disk": str(disk)}
    try:
        cfg = load_config(disk)
        sections = load_sections(cfg)
        brief = build_brief(disk, (section or "").strip() or None)
    except ConfigError as exc:
        return {**base, "ok": False, "code": "BRIEF_UNAVAILABLE", "error": str(exc)}
    except (OSError, ValueError) as exc:
        return {**base, "ok": False, "code": "READ_FAILED",
                "error": "读项目失败：%s" % exc}

    data = payload(brief)
    bound_map = {rel: list(bound_fact_ids(text)) for rel, text in sections}

    # 每条事实绑在哪些节（跨全项目，不只本节）。
    fact_sections: dict = {}
    for rel, ids in bound_map.items():
        for fid in ids:
            fact_sections.setdefault(fid, []).append(rel)

    rows = []
    for row in data.get("sections") or []:
        rel = str(row.get("file") or "")
        bound = bound_map.get(rel, [])
        usable = [str(x) for x in (row.get("evidence") or [])]
        unbound = [fid for fid in usable if fid not in bound]
        rows.append({
            **row,
            "bound": bound,
            "usable": usable,
            "unbound": unbound,
            "reconciled": bool(usable) and not unbound,
        })

    facts = []
    bound_total = 0
    for fact in data.get("facts") or []:
        fid = str(fact.get("id") or "")
        where = sorted(fact_sections.get(fid, []))
        if where:
            bound_total += 1
        facts.append({**fact, "bound_in": where,
                      "status": "bound" if where else "unbound"})

    total = len(facts)
    return {
        **base,
        "project": data.get("project", ""),
        "root_tex": data.get("root_tex", ""),
        "section": data.get("section") or "",
        "facts_total": int(data.get("facts_total") or total),
        "counts": {"ledger_total": total, "bound": bound_total,
                   "unbound": total - bound_total,
                   "sections_total": len(rows)},
        "sections": rows,
        "facts": facts,
        "terms": data.get("terms") or [],
        "notes": list(data.get("notes") or []),
        "constraints": list(CONSTRAINTS),
    }
