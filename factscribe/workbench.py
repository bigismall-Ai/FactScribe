# -*- coding: utf-8 -*-
"""本地工作台的数据层：serve（HTTP）与 mcp（stdio）共用。

这里只做「读项目 / 改一节 / 追加事实 / 跑审计」的数据动作；不涉及 HTTP、
JSON-RPC、token 或页面。判定仍由 audit/brief 原函数给出。
"""
from __future__ import annotations

import os
from pathlib import Path

from .audit import _aggregate_exit, run_audit, source_path
from .brief import build_brief, payload as brief_payload
from .config import (ConfigError, load_config, load_facts, load_sections)
from .report import _config_block, _severity_of
from .scaffold import add_fact


def _config_bits(cfg) -> dict:
    return {"config": _config_block(cfg),
            "config_warnings": list(cfg.warnings)}


def _require_write(allow_write: bool) -> None:
    if not allow_write:
        raise ConfigError("当前是只读模式；写操作需要 --allow-write",
                          code="READ_ONLY")


def status_data(project: Path | str, allow_write: bool = False) -> dict:
    cfg = load_config(Path(project))
    facts = load_facts(cfg)
    sections = load_sections(cfg)
    return {
        "project": cfg.name or cfg.title,
        "root": str(cfg.root),
        "facts": len(facts),
        "sections": len(sections),
        "facts_glob": cfg.facts_glob,
        "sections_glob": cfg.sections_glob,
        "read_only": not allow_write,
        **_config_bits(cfg),
    }


def project_data(project: Path | str, allow_write: bool = False) -> dict:
    cfg = load_config(Path(project))
    facts = load_facts(cfg)
    sections = load_sections(cfg)
    source_rows: dict[str, dict] = {}
    for fact in facts:
        src = fact.source.strip()
        if not src or src in source_rows:
            continue
        text = ""
        try:
            base = source_path(cfg, "").resolve()
            path = source_path(cfg, src).resolve()
            path.relative_to(base)
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError, UnicodeDecodeError):
            text = ""
        source_rows[src] = {"id": src, "name": src, "text": text,
                            "sha256": fact.source_sha256}
    bib_path = cfg.root / cfg.bib
    try:
        bib = bib_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        bib = ""
    return {
        "read_only": not allow_write,
        "project": cfg.name or cfg.title,
        "root": str(cfg.root),
        "sections": [{"file": rel, "text": text} for rel, text in sections],
        "facts": [{
            "id": f.id, "claim": f.claim, "value": f.value,
            "source": f.source, "sourceSha256": f.source_sha256,
            "locator": f.locator, "confidence": f.confidence,
            "derivedFrom": list(f.derived_from), "expr": f.expr,
            "dupOk": f.dup_ok, "notes": f.note,
        } for f in facts],
        "sources": list(source_rows.values()),
        "bib": bib,
        **_config_bits(cfg),
    }


def brief_data(project: Path | str, section: str | None = None) -> dict:
    brief = build_brief(Path(project), section)
    cfg = load_config(Path(project))
    return {**brief_payload(brief), **_config_bits(cfg)}


def audit_data(project: Path | str) -> dict:
    cfg = load_config(Path(project))
    facts = load_facts(cfg)
    sections = load_sections(cfg)
    red, yellow, hints, summary, unresolved = run_audit(
        cfg, facts, sections, resolve=False)
    code = _aggregate_exit(red, yellow, False,
                           integrity_first=cfg.is_v3)
    return {
        "exit": code,
        "verdict": _severity_of(code),
        "summary": summary,
        "findings": [i.as_dict() for i in red] + [w.as_dict() for w in yellow],
        "issues": [i.as_dict() for i in red],
        "warnings": [w.as_dict() for w in yellow],
        "hints": [h.as_dict() for h in hints],
        "coverage": summary.get("coverage", {}),
        "resolved": unresolved,
        **_config_bits(cfg),
    }


def write_section_data(project: Path | str, file: str, text: str,
                       allow_write: bool = False) -> dict:
    _require_write(allow_write)
    cfg = load_config(Path(project))
    rel = str(file or "").strip()
    if not rel:
        raise ConfigError("file 必填：要写哪一节")
    if not isinstance(text, str):
        raise ConfigError("text 必须是字符串")
    sections = dict(load_sections(cfg))
    if rel not in sections:
        raise ConfigError("file 不在审计闭包内：%s" % rel)
    if not rel.endswith(".tex"):
        raise ConfigError("只允许写 .tex 章节：%s" % rel)
    root = cfg.root.resolve()
    target = (cfg.root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ConfigError("章节越出项目根：%s" % rel)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)
    return {"file": rel, "bytes": len(text.encode("utf-8"))}


def add_fact_data(project: Path | str, body: dict,
                  allow_write: bool = False) -> dict:
    _require_write(allow_write)
    if not isinstance(body, dict):
        raise ConfigError("参数必须是对象")
    return add_fact(
        Path(project),
        fid=str(body.get("id") or ""),
        claim=str(body.get("claim") or ""),
        value=str(body.get("value") or ""),
        source=str(body.get("source") or ""),
        locator=str(body.get("locator") or ""),
        confidence=str(body.get("confidence") or "med"),
        expr=str(body.get("expr") or ""),
        derived_from=body.get("derived_from") or body.get("derivedFrom"),
        note=str(body.get("note") or ""))
