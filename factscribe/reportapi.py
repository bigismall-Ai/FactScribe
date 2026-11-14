# -*- coding: utf-8 -*-
"""实验报告（factscribe/report@1）在工作台接口里的数据层。

只做编排：读报告、跑探针、上锁、出卡、签收、入账全部走 report.py 与 cli.py
的既有语义；这里不重新实现任何一条判定，也不改它们的退出码。

工作区（workspace）＝报告与原始产物所在的那个目录：

* ``cfg.source_root`` 非空 → ``(cfg.root / cfg.source_root).resolve()``；
* 否则 → ``cfg.root``。

扫描面（只读）：

* ``<工作区>/experiments/<实验>/reports/*.report.toml``
* ``<工作区>/reports/*.report.toml``
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path

from .config import ConfigError, load_config
from .report import (ReportError, _artifact_path, _rel_posix, _resolve_in_ws,
                     _ws_root, check_report, load_report, lock_report,
                     report_card, sign_report, verify_signoff)

# 报告扫描面：两个 glob，顺序即展示顺序。
REPORT_PATTERNS = ("experiments/*/reports/*.report.toml",
                   "reports/*.report.toml")

ACTIONS = ("check", "lock", "sign", "import")
WRITE_ACTIONS = ("lock", "sign", "import")

_REPORT_SUFFIX = ".report.toml"


def workspace_of(cfg) -> Path:
    """工作区根：source_root 指哪儿，报告就在哪儿找。"""
    raw = str(getattr(cfg, "source_root", "") or "").strip()
    if not raw:
        return cfg.root.resolve()
    p = Path(raw).expanduser()
    return (p if p.is_absolute() else cfg.root / p).resolve()


def report_files(ws: Path) -> list[Path]:
    """扫报告文件（只读）。同一份文件只算一次，按工作区相对路径排序。"""
    found: dict[str, Path] = {}
    for pattern in REPORT_PATTERNS:
        for path in ws.glob(pattern):
            if not path.is_file():
                continue
            try:
                key = _rel_posix(ws, path)
            except (OSError, ValueError):
                continue
            found[key] = path
    return [found[key] for key in sorted(found)]


def _lock_state(ws: Path, report: dict) -> tuple:
    """锁的状态：("ok"|"missing"|"stale", 人话)。与 cli 的同名判断一致。"""
    from .cli import _lock_state as cli_lock_state  # cli→serve→本模块是环
    return cli_lock_state(ws, report)


def report_entry(ws: Path, path: Path) -> dict:
    """一份报告在列表里的样子。读不动也要列出，并说清为什么。"""
    rel = _rel_posix(ws, path)
    entry = {
        "path": rel,
        "id": path.name[:-len(_REPORT_SUFFIX)]
        if path.name.endswith(_REPORT_SUFFIX) else path.stem,
        "experiment": "",
        "status": "",
        "metrics": 0,
        "locked": False,
        "lock_ok": False,
        "signed": False,
        "reason": "",
        "card": [],
    }
    try:
        report = load_report(ws, rel)
    except ReportError as exc:
        entry["reason"] = exc.message
        return entry

    entry["id"] = str(report.get("id") or entry["id"])
    entry["experiment"] = str(report.get("experiment") or "")
    entry["status"] = str(report.get("status") or "")
    entry["metrics"] = len(report.get("metrics", []) or [])

    lock_path = _artifact_path(ws, report, ".lock.json")
    entry["locked"] = lock_path.exists()
    state, reason = _lock_state(ws, report)
    entry["lock_ok"] = state == "ok"

    verified = verify_signoff(ws, rel)
    entry["signed"] = bool(verified.get("ok"))

    if entry["lock_ok"]:
        try:
            entry["card"] = list(report_card(ws, rel).get("lines", []) or [])
        except ReportError as exc:
            entry["card"] = []
            if not entry["reason"]:
                entry["reason"] = exc.message

    if not entry["reason"]:
        if entry["locked"] and not entry["lock_ok"]:
            entry["reason"] = reason
        elif not entry["signed"]:
            entry["reason"] = str(verified.get("reason") or "还没有签收")
    return entry


def reports_data(project: Path | str) -> dict:
    """GET /api/reports 的数据面。"""
    cfg = load_config(Path(project))
    ws = _ws_root(workspace_of(cfg))
    return {
        "workspace": str(ws),
        "reports": [report_entry(ws, path) for path in report_files(ws)],
    }


def _require_write(allow_write: bool) -> None:
    if not allow_write:
        raise ConfigError(
            "serve 当前是只读模式；封存/签收/导入需要启动时加 --allow-write",
            code="READ_ONLY")


def _report_ref(ws: Path, raw: str) -> str:
    """把请求里的报告路径解析成工作区内的相对路径（越界当场拒）。"""
    text = str(raw or "").strip()
    if not text:
        raise ConfigError("report 必填：要处理哪一份报告", code="USAGE")
    path = _resolve_in_ws(ws, text)
    return _rel_posix(ws, path)


def _fact_import(paper: Path, ws: Path, rel: str, dry_run: bool) -> dict:
    """入账：走 cli 里那三道门（final / 锁一致 / 已签收），不另写一套。

    cli → serve → reportapi 是个环，所以延迟导入；命令行的判据与退出码原样
    复用，这里只把结果翻译成接口的返回。
    """
    from .cli import cmd_fact_import  # 延迟导入，避免 cli↔serve 循环

    args = argparse.Namespace(ws=str(ws), report=rel, paper=str(paper),
                              dry_run=bool(dry_run), json=True)
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cmd_fact_import(args)
    payload = _last_json(out.getvalue())
    if code != 0:
        info = payload.get("error") or {}
        raise ConfigError(str(info.get("message") or "导入失败"),
                          code=str(info.get("code") or "IMPORT_FAILED"))
    return {
        "facts_file": str(payload.get("facts_file") or ""),
        "written": bool(payload.get("written")),
        "unchanged": bool(payload.get("unchanged")),
        "dry_run": bool(payload.get("dry_run")),
        "facts": len(payload.get("facts") or []),
    }


def _last_json(text: str) -> dict:
    """stdout 末行是单行 JSON（tail -1 能解析）。"""
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return {}


def report_action_data(project: Path | str, body: dict,
                       allow_write: bool = False) -> dict:
    """POST /api/reports/action 的数据面。

    check 只读；lock / sign / import 要 --allow-write。失败一律抛
    ConfigError（带 code）或 ReportError（带 code），由 serve 翻译成
    403 / 400 的 JSON，不让异常变成空响应。
    """
    if not isinstance(body, dict):
        raise ConfigError("请求体必须是 JSON 对象", code="USAGE")
    action = str(body.get("action") or "").strip().lower()
    if action not in ACTIONS:
        raise ConfigError(
            "action 只能是 %s" % " / ".join(ACTIONS), code="USAGE")
    if action in WRITE_ACTIONS:
        _require_write(allow_write)
    by = str(body.get("by") or "").strip()
    if action == "sign" and not by:
        raise ConfigError("签收必须写签收人（不能替人签字）", code="USAGE")

    cfg = load_config(Path(project))
    ws = _ws_root(workspace_of(cfg))
    rel = _report_ref(ws, str(body.get("report") or ""))

    if action == "check":
        return {"action": action,
                "result": check_report(ws, rel)}

    if action == "lock":
        lock = lock_report(ws, rel)
        report = load_report(ws, rel)
        lock_path = _artifact_path(ws, report, ".lock.json")
        return {"action": action, "result": {
            "locked": True,
            "lock_path": _rel_posix(ws, lock_path),
            "locked_at": str(lock.get("locked_at") or ""),
            "report_sha256": str(lock.get("report_sha256") or ""),
            "semantic_digest": str(lock.get("semantic_digest") or ""),
            "evidence_digest": str(lock.get("evidence_digest") or ""),
        }}

    if action == "sign":
        signoff = sign_report(ws, rel, by)
        report = load_report(ws, rel)
        return {"action": action, "result": {
            "signed": True,
            "signed_by": by,
            "signed_at": str(signoff.get("signed_at") or ""),
            "card": list(signoff.get("card_lines") or []),
            "signoff_path": _rel_posix(ws, _artifact_path(ws, report,
                                                          ".signoff.toml")),
            "log_path": _rel_posix(ws, _artifact_path(ws, report,
                                                       ".signoff.log")),
        }}

    # import：入账走既有三道门，写进论文项目的事实账。
    result = _fact_import(cfg.root, ws, rel, bool(body.get("dry_run")))
    return {"action": action, "result": result}
