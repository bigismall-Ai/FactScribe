# -*- coding: utf-8 -*-
"""账与证据面的提议单（宿主能提，人点才写）。

正文改稿走 write.py 的提议单；这里管另外几件非正文的写动作：

* 证据冻结 / 解冻（evidence.freeze_evidence / unfreeze_evidence）；
* 追加一条事实（scaffold.add_fact）；
* 导出投稿包（actions.export_bundle）。

形状纪律与正文提议单完全一致：

* 提议单只落状态目录，不碰正文、不碰账、不碰冻结件；
* 每张单都带 before_sha 指纹闸——提议之后状态被别处改过，采纳时拒写
  （BLOCK_STALE），不覆盖别人的改动；
* 差异卡展示的 after_text 就是真正会落盘的那一份。

铁律：不得凭空造事实——add_fact 走的是 CLI fact add 同一条路，
它自己查 id 重复、查来源文件、查 value 形态。
"""
from __future__ import annotations

from pathlib import Path

from ..config import ConfigError, load_config
from ..evidence import (canonical_sha256, entry_count, freeze_evidence,
                         read_lock, unfreeze_evidence)
from ..scaffold import add_fact, prepare_fact

KIND_EVIDENCE_FREEZE = "evidence_freeze"
KIND_EVIDENCE_UNFREEZE = "evidence_unfreeze"
KIND_ADD_FACT = "add_fact"
KIND_EXPORT_BUNDLE = "export_bundle"

#: 提议单类型 → 人类可读的标题（页面差异卡上的标签）。
KIND_LABELS = {
    KIND_EVIDENCE_FREEZE: "冻结证据清单",
    KIND_EVIDENCE_UNFREEZE: "解冻证据清单",
    KIND_ADD_FACT: "追加事实",
    KIND_EXPORT_BUNDLE: "导出投稿包",
}


def _declared_summary(declared: dict) -> str:
    lines = []
    for key in sorted(declared):
        ids = ", ".join(str(i) for i in (declared.get(key) or []))
        lines.append("节 %s → %s" % (key, ids or "（无）"))
    return "\n".join(lines) or "（清单为空）"


def _lock_summary(lock) -> str:
    if not lock:
        return "无（还没冻结过）"
    return "%s（sha256 %s…，%s 条）" % (
        str(lock.get("path") or "audit/evidence.lock"),
        str(lock.get("sha256") or "")[:12],
        int(lock.get("entries") or 0))


def _declared_of(disk_root: Path) -> dict:
    cfg = load_config(Path(disk_root))
    return dict(getattr(cfg, "evidence_sections", {}) or {})


# ---------------------------------------------------------------- 冻结


def propose_evidence_freeze(disk_root: Path, reason: str = "",
                             source: str = "", rationale: str = "") -> dict:
    """算一份「冻结证据清单」的提议（不写盘）。

    指纹闸用清单本身的 canonical_sha256：提议之后清单被改过，
    采纳时拒写（BLOCK_STALE）——冻结的必须是提议时那份清单。
    """
    declared = _declared_of(disk_root)
    digest = canonical_sha256(declared)
    entries = entry_count(declared)
    lock = read_lock(Path(disk_root))
    warnings = []
    if not declared:
        warnings.append("当前清单是空的（[evidence] 没声明任何节）——"
                        "冻结下来只会留一个空件。")
    if lock and str(lock.get("sha256") or "") == digest:
        warnings.append("当前清单与冻结件一致——冻结是幂等的，不会改任何东西。")
    before = "当前清单（[evidence] 声明）：%d 节 / %d 条\n%s\n冻结件：%s" % (
        len(declared), entries, _declared_summary(declared),
        _lock_summary(lock))
    after = ("冻结件将写入 %s：\n%d 节 / %d 条\n%s\ncanonical_sha256 = %s"
             % (str((lock or {}).get("path") or "audit/evidence.lock"),
                len(declared), entries, _declared_summary(declared),
                digest))
    if str(reason or "").strip():
        after += "\n冻结理由：%s" % str(reason).strip()
    return {"kind": KIND_EVIDENCE_FREEZE,
            "file": "", "block": "",
            "before_sha": digest,
            "before_text": before,
            "proposed_text": str(reason or ""),
            "after_text": after,
            "warnings": warnings,
            "source": source,
            "rationale": rationale,
            "reason": str(reason or "").strip(),
            "entries": entries,
            "declared": {key: list(value)
                         for key, value in sorted(declared.items())}}


# ---------------------------------------------------------------- 解冻


def propose_evidence_unfreeze(disk_root: Path, reason: str = "", at: str = "",
                               source: str = "", rationale: str = "") -> dict:
    """算一份「解冻证据清单」的提议（不写盘）。

    解冻必须带非空理由——理由会写进 audit/evidence-log.ndjson，
    那是给未来的人看的「为什么当时改了清单」。
    """
    text = str(reason or "").strip()
    if not text:
        raise ConfigError("解冻必须带非空理由（为什么改）——理由会写进 "
                          "audit/evidence-log.ndjson",
                          code="EVIDENCE_REASON_REQUIRED")
    lock = read_lock(Path(disk_root))
    if lock is None:
        raise ConfigError("尚未冻结（没有 audit/evidence.lock）：无冻可解。",
                          code="EVIDENCE_NOT_FROZEN")
    declared = _declared_of(disk_root)
    before = "冻结件：%s\n清单：%d 节 / %d 条\n%s\n状态：已冻结" % (
        _lock_summary(lock), len(declared), entry_count(declared),
        _declared_summary(declared))
    after = ("冻结件保留（%s），但清单进入「解冻」状态\n"
             "日志将追加一条 unfreeze 记录到 audit/evidence-log.ndjson\n"
             "解冻理由：%s") % (str(lock.get("sha256") or "")[:12], text)
    if str(at or "").strip():
        after += "\n日期：%s" % str(at).strip()
    return {"kind": KIND_EVIDENCE_UNFREEZE,
            "file": "", "block": "",
            "before_sha": str(lock.get("sha256") or ""),
            "before_text": before,
            "proposed_text": text,
            "after_text": after,
            "warnings": [],
            "source": source,
            "rationale": rationale,
            "reason": text,
            "at": str(at or "").strip()}


# ---------------------------------------------------------------- 追加事实


def propose_add_fact(disk_root: Path, body: dict, source: str = "",
                      rationale: str = "") -> dict:
    """算一份「追加一条事实」的提议（不写盘）。

    校验走 scaffold.prepare_fact——与 CLI fact add 同一套，
    算出来的 block 就是真正会追加进账本的那几行 TOML。
    """
    body = body or {}
    prepared = prepare_fact(Path(disk_root),
                            fid=str(body.get("id") or ""),
                            claim=str(body.get("claim") or ""),
                            value=str(body.get("value") or ""),
                            source=str(body.get("source") or ""),
                            locator=str(body.get("locator") or ""),
                            confidence=str(body.get("confidence") or "med"),
                            expr=str(body.get("expr") or ""),
                            derived_from=(body.get("derived_from")
                                          or body.get("derivedFrom")),
                            note=str(body.get("note") or ""))
    ledger = str(prepared.get("ledger") or "")
    before = "账本 %s：当前没有 id=%s 的事实\n（这条将追加到账本末尾）" % (
        ledger or "（未定位）", str(prepared.get("id") or ""))
    after = ("将向账本 %s 追加一条事实：\n%s"
             % (ledger or "（未定位）", str(prepared.get("block") or "")))
    fact = {key: prepared.get(key) for key in
            ("id", "claim", "value", "source", "source_sha256", "locator",
             "confidence", "derived_from", "expr", "note", "ledger",
             "manifest", "manifest_line")}
    return {"kind": KIND_ADD_FACT,
            "file": "", "block": "",
            "before_sha": "",
            "before_text": before,
            "proposed_text": str(prepared.get("block") or ""),
            "after_text": after,
            "warnings": [],
            "source": source,
            "rationale": rationale,
            "fact": fact}


# ---------------------------------------------------------------- 投稿包


def propose_export_bundle(disk_root: Path, source: str = "",
                           rationale: str = "") -> dict:
    """算一份「导出投稿包」的提议（不写盘）。

    投稿包是真收集：把正文、账、文献、PDF 收进一个目录，
    再逐条过清单门。清单门不过＝不出包。
    """
    before = "投稿包：还没导出过（本提议会真收集一次并过清单门）"
    after = ("将导出投稿包：正文 ＋ 事实账 ＋ 参考文献 ＋ PDF\n"
             "清单门逐条核对；门不过就不出包（提议单留在待确认，人可重提）")
    return {"kind": KIND_EXPORT_BUNDLE,
            "file": "", "block": "",
            "before_sha": "",
            "before_text": before,
            "proposed_text": "",
            "after_text": after,
            "warnings": [],
            "source": source,
            "rationale": rationale}


# ---------------------------------------------------------------- 落盘


def _guard(expect: str, current: str, what: str) -> None:
    """指纹闸：提议之后状态被别处改过 → 拒写（BLOCK_STALE）。"""
    expect = str(expect or "")
    current = str(current or "")
    if not expect:
        return
    if expect != current:
        raise ConfigError("%s在提议之后被改过（当前 %s…，提议时 %s…）——"
                          "请重新提一张单。"
                          % (what, current[:12], expect[:12]),
                          code="BLOCK_STALE")


def apply_evidence_freeze(disk_root: Path, proposal: dict) -> dict:
    """采纳「冻结证据清单」：真写冻结件 ＋ 流水账。"""
    root = Path(disk_root)
    declared = _declared_of(root)
    _guard(str(proposal.get("before_sha") or ""),
            canonical_sha256(declared), "证据清单")
    info = freeze_evidence(root, declared,
                            str(proposal.get("reason") or ""))
    return {"ok": True, "kind": KIND_EVIDENCE_FREEZE,
            "path": str(info.get("path") or ""),
            "sha256": str(info.get("sha256") or ""),
            "entries": int(info.get("entries") or 0),
            "idempotent": bool(info.get("idempotent")),
            "warnings": []}


def apply_evidence_unfreeze(disk_root: Path, proposal: dict) -> dict:
    """采纳「解冻证据清单」：真写一条 unfreeze 记录。"""
    root = Path(disk_root)
    lock = read_lock(root)
    _guard(str(proposal.get("before_sha") or ""),
            str((lock or {}).get("sha256") or ""), "冻结件")
    info = unfreeze_evidence(root, str(proposal.get("reason") or ""),
                              str(proposal.get("at") or ""))
    return {"ok": True, "kind": KIND_EVIDENCE_UNFREEZE,
            "path": str(info.get("path") or ""),
            "action": str(info.get("action") or ""),
            "reason": str(info.get("reason") or ""),
            "at": str(info.get("at") or ""),
            "idempotent": bool(info.get("idempotent")),
            "warnings": []}


def apply_add_fact(disk_root: Path, proposal: dict) -> dict:
    """采纳「追加事实」：真写账本（走 CLI fact add 同一条路）。"""
    fact = dict(proposal.get("fact") or {})
    if not fact:
        raise ConfigError("这张提议单里没有事实内容——没法落账。",
                          code="PROPOSAL_FACT_MISSING")
    info = add_fact(Path(disk_root),
                    fid=str(fact.get("id") or ""),
                    claim=str(fact.get("claim") or ""),
                    value=str(fact.get("value") or ""),
                    source=str(fact.get("source") or ""),
                    locator=str(fact.get("locator") or ""),
                    confidence=str(fact.get("confidence") or "med"),
                    expr=str(fact.get("expr") or ""),
                    derived_from=fact.get("derived_from"),
                    note=str(fact.get("note") or ""))
    return {"ok": True, "kind": KIND_ADD_FACT,
            "id": str(info.get("id") or ""),
            "claim": str(info.get("claim") or ""),
            "value": str(info.get("value") or ""),
            "source": str(info.get("source") or ""),
            "source_sha256": str(info.get("source_sha256") or ""),
            "ledger": str(info.get("ledger") or ""),
            "manifest_line": str(info.get("manifest_line") or ""),
            "warnings": []}


def apply_export_bundle(disk_root: Path, proposal: dict) -> dict:
    """采纳「导出投稿包」：真收集 ＋ 真过清单门。"""
    from .actions import export_bundle

    info = export_bundle(Path(disk_root))
    if not info.get("ok"):
        raise ConfigError("投稿包没过清单门：%s"
                          % (str(info.get("failure_reason")
                                 or info.get("error") or "见明细")),
                          code="BUNDLE_FAILED")
    return {"ok": True, "kind": KIND_EXPORT_BUNDLE,
            "bundle_dir": str(info.get("bundle_dir") or ""),
            "file_count": int(info.get("file_count") or 0),
            "passed": int(info.get("passed") or 0),
            "waived": int(info.get("waived") or 0),
            "failed": int(info.get("failed") or 0),
            "exit_code": int(info.get("exit_code") or 0),
            "warnings": []}
