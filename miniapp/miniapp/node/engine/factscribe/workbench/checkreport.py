# -*- coding: utf-8 -*-
"""段三：检查报告与机器视图的数据层（只读）。

本模块只做「读项目 → 跑真闸 → 摆数据」，不重新实现任何一条判定：
真闸就是 ``factscribe.audit``（``audit.run_audit``，与 CLI ``cmd_audit``
同一条路），闸的退出码与发现清单原样透传。

**只读承诺**：

* ``report_payload`` / ``machine_payload`` 只跑 ``run_audit``（只读）＋
  ``load_facts`` / ``load_sections``（只读）＋ ``read_lock``（只读）；
* ``rerun`` 走 subprocess 跑真闸（``python -m factscribe audit --json``），
  **不加 ``--build``**（不编译＝不落 PDF），并在跑前跑后对项目目录做
  哈希对比，证明零写入；
* 任何一步失败都返回结构化错误（``ok:false`` ＋ ``code`` ＋ ``message``），
  绝不抛 500。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from ..config import (ConfigError, facts_digest, load_config, load_facts,
                      load_sections)
from ..constants import (EXIT_ATTACK_OPEN, EXIT_CONFIG, EXIT_INTEGRITY,
                         EXIT_INTERNAL, EXIT_MISSING, EXIT_OK, EXIT_PROOF,
                         EXIT_RED, EXIT_STALE, EXIT_YELLOW)
from ..evidence import read_lock

# 真闸：与 CLI `factscribe audit` 同一条路（不带 --build，绝不编译落盘）。
GATE_COMMAND = ("audit", "--json")
RERUN_TIMEOUT = 120.0

# 「真闸跑不起来」的退出码＝工具级失败：配置错(2)／内部错(4)／必需工具缺失(8)。
# 这些才叫重跑失败。
#
# 其余退出码都是**真闸跑完了并给出判定**（体检结论，不是失败）：
#   0 绿 / 1 红 / 3 黄 / 5 覆盖或信任链红 / 6 证明红 / 7 过期 / 9 攻击面红。
# 注意：CLI 的 JSON 信封里 `status`/`severity` 走 `_severity_of()`，
# 它只认 0/1/3，**其余一律折成 "error"**——所以 exit 5（红）也会吐
# severity="error"。用 status/severity 判失败＝把「查出一堆红」误报成
# 「重跑炸了」。这里只按退出码分层判。
GATE_FAIL_EXITS = frozenset({EXIT_CONFIG, EXIT_INTERNAL, EXIT_MISSING})

# 判定档位：退出码 → 绿/黄/红（前端只认这三档）。
_VERDICT_BY_EXIT = {
    EXIT_OK: "ok",
    EXIT_RED: "red",
    EXIT_YELLOW: "yellow",
    EXIT_INTEGRITY: "red",
    EXIT_PROOF: "red",
    EXIT_STALE: "red",
    EXIT_ATTACK_OPEN: "red",
}

# 仓库根（factscribe 的上一级）：subprocess 用它当 cwd，保证
# `python -m factscribe` 在未安装的环境里也能跑起来。
REPO_ROOT = Path(__file__).resolve().parents[2]

SEV_ORDER = {"red": 0, "yellow": 1, "info": 2, "hint": 3}


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------

def short_fp(text: str, size: int = 8) -> str:
    """短指纹：完整 sha256 的前 8 位。完整值仍留在数据里，只是不渲染。"""
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:size]


def _norm_title(text: str) -> str:
    """标题去 LaTeX 排版味：`\\large`、`\\[4pt]`、`\textbf{}` 之类。"""
    out = text.replace("\\%", "%").replace("\\&", "&").replace("\\_", "_")
    for cmd in ("\\large", "\\Large", "\\LARGE", "\\bfseries", "\\rmfamily",
                "\\sffamily", "\\mdseries", "\\itshape", "\\upshape"):
        out = out.replace(cmd, "")
    out = out.replace("\\[", " ").replace("\\]", " ")
    out = out.replace("{", "").replace("}", "")
    return " ".join(out.split())


def _fact_file_name(rel: str) -> str:
    """出处文件只显文件名（悬浮看全路径）。"""
    if not rel:
        return ""
    if "://" in rel:
        return rel
    return Path(rel).name


def _dir_manifest(root: Path) -> dict:
    """项目目录清单：相对路径 → (大小, mtime_ns, 内容 sha256)。"""
    out: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = Path(dirpath) / name
            rel = str(full.relative_to(root))
            try:
                raw = full.read_bytes()
                st = full.stat()
            except OSError:
                out[rel] = (-1, -1, "")
                continue
            out[rel] = (st.st_size, st.st_mtime_ns,
                        hashlib.sha256(raw).hexdigest())
    return out


def _diff_manifest(before: dict, after: dict) -> dict:
    """两份清单的差：内容变了 / 只被动过（mtime 变但内容没变）。"""
    changed, touched = [], []
    for rel in sorted(set(before) | set(after)):
        old = before.get(rel)
        new = after.get(rel)
        if old == new:
            continue
        if old is None or new is None:
            changed.append(rel)
            continue
        if old[2] != new[2]:
            changed.append(rel)
        else:
            touched.append(rel)
    return {"changed": changed, "touched": touched,
            "identical": not changed and not touched}


# --------------------------------------------------------------------------
# 真闸（只读）
# --------------------------------------------------------------------------

def run_gate(disk: Path):
    """跑真闸：``audit.run_audit``。返回 (red, yellow, hints, summary)。"""
    from ..audit import run_audit
    from ..checks import run_packages

    cfg = load_config(disk)
    facts = load_facts(cfg)
    sections = load_sections(cfg)
    if getattr(cfg, "checks_defined", False):
        red, yellow, hints, summary, _unresolved = run_packages(
            cfg, facts, sections, resolve=False)
    else:
        red, yellow, hints, summary, _unresolved = run_audit(
            cfg, facts, sections, resolve=False)
    return cfg, facts, sections, red, yellow, hints, summary


# --------------------------------------------------------------------------
# 附加只读闸（体检报告的第二层读数）
# --------------------------------------------------------------------------
#
# 「只看 miniapp」的人看不到文风闸与双语双盘对账的读数（2026-11-22 体检
# 报告 P0-1）。这两道闸在 CLI 里本来就是只读命令（factscribe style /
# factscribe mirror-check），这里把它们当只读读数并进检查报告：
#
# * 只读：style 只读正文与规则文件；mirror-check 只读两个盘的事实账与
#   参考文献。全程没有写路径，不改盘、不改稿。
# * 不改判定面：主体检（health）与发现清单（findings）仍然只认 audit ＋
#   清单门那两道闸。文风黄牌不混进主黄牌计数——否则一个干净的稿子会
#   凭空多出几条黄牌，吓人（体检报告 P0-1 的副作用须知）。
# * 可缺席：单语项目没有第二个盘，双语对账就是「不适用」，不是错。


def _style_finding_dict(item) -> dict:
    """style 的 Finding → 报告里那条 finding 的形状（字段名与 audit 那套一致）。"""
    return {
        "code": getattr(item, "code", "") or "",
        "severity": getattr(item, "severity", "yellow") or "yellow",
        "message": getattr(item, "suggestion", "") or getattr(item, "text", ""),
        "location": "%s:%s" % (getattr(item, "file", "") or "",
                              getattr(item, "line", 0) or 0),
        "token": getattr(item, "text", "") or "",
        "context": getattr(item, "metric", "") or "",
    }


def _style_gate(cfg, sections) -> dict:
    """文风闸读数（只读）。跑的是 CLI factscribe style 同一条分析路。"""
    from ..style import analyze, load_style_rules_info

    gate = {"ok": True, "gate": "style", "status": "ok",
            "red": 0, "yellow": 0, "count": 0, "findings": [],
            "summary": {}, "rules": "", "note": ""}
    try:
        info = load_style_rules_info(cfg.root, None)
        result = analyze(cfg, sections, info.rules, rules_path=info.path,
                         stage="draft", rule_report=info.report)
    except Exception as exc:  # noqa: BLE001 - 附加读数读不动不该掀翻整页
        # error 给机器码，界面文案由前端翻译（error_detail 留给 API 消费者）。
        gate.update({"ok": False, "status": "error", "error": "STYLE_FAILED",
                     "error_detail": str(exc)})
        return gate
    findings = [_style_finding_dict(f) for f in result.findings]
    red = sum(1 for f in findings if f["severity"] == "red")
    yellow = sum(1 for f in findings if f["severity"] == "yellow")
    gate.update({
        "status": "red" if red else ("yellow" if yellow else "ok"),
        "red": red, "yellow": yellow, "count": len(findings),
        "findings": findings,
        "summary": dict(result.summary or {}),
        "rules": result.rules_path or info.path,
        "metrics": dict(result.metrics or {}),
    })
    return gate


def _mirror_gate(disk: Path, sibling: Path | None) -> dict:
    """双语双盘对账读数（只读）。跑的是 CLI factscribe mirror-check 同一条路。"""
    from .. import mirror

    gate = {"ok": True, "gate": "mirror-check", "status": "na",
            "count": 0, "drift": [], "summary": {},
            "disk_a": str(disk), "disk_b": "", "note": ""}
    if sibling is None:
        # note 给机器码：界面上的解释由前端 i18n 出，后端不塞中文。
        gate["note"] = "MIRROR_NO_SIBLING"
        return gate
    gate["disk_b"] = str(sibling)
    try:
        result = mirror.check(Path(disk), Path(sibling))
    except ConfigError as exc:
        gate.update({"ok": False, "status": "error",
                     "error": str(getattr(exc, "code", "") or "MIRROR_CONFIG_INVALID"),
                     "error_detail": str(exc)})
        return gate
    except Exception as exc:  # noqa: BLE001
        gate.update({"ok": False, "status": "error", "error": "MIRROR_FAILED",
                     "error_detail": str(exc)})
        return gate
    gate.update({
        "status": "drift" if result.drifts else "ok",
        "count": result.drift_count,
        "drift": mirror.drift_dicts(result),
        "summary": result.summary(),
    })
    return gate


def _safe_digest(cfg) -> str:
    """账本指纹：读不动就给空串，不让整页崩（指纹只是徽标，不是判定）。"""
    try:
        return facts_digest(cfg) or ""
    except (OSError, ValueError, ConfigError):
        return ""


def _finding_dict(issue) -> dict:
    """发现条目：code / severity / 信息 / 定位。"""
    data = issue.as_dict()
    return {
        "code": data.get("code", ""),
        "severity": data.get("severity", "red"),
        "message": data.get("message", ""),
        "location": data.get("location", ""),
        "token": data.get("token", ""),
        "context": data.get("context", ""),
    }


def _chain_steps(summary: dict, lock: dict | None, facts_count: int) -> list:
    """四步链：声明 → 绑定 → 回账 → 出证。每步都是真读数。"""
    total = int(summary.get("numbers_total") or 0)
    bound = int(summary.get("numbers_bound") or 0)
    matched = int(summary.get("numbers_matched") or 0)
    unmatched = int(summary.get("numbers_unmatched") or 0)
    entries = int((lock or {}).get("entries") or 0)
    pdf = summary.get("pdf") or {}
    pdf_ok = bool(pdf.get("checked")) and not pdf.get("stale")

    # label/detail 是旧字段（MCP 工具的对外形状不变，仍给得出中文标签）；
    # label_key/detail_key 是结构化 i18n key——界面文案一律由前端翻译，
    # 免得 EN 界面下半中半英（P0-4）。
    steps = [
        {"key": "declare", "label": "声明",
         "label_key": "chain.declare",
         "detail": "facts/*.toml 里的事实条数",
         "detail_key": "chain.declare.detail",
         "value": facts_count, "total": facts_count,
         "ok": facts_count > 0,
         "state": "ok" if facts_count else "missing"},
        {"key": "bind", "label": "绑定",
         "label_key": "chain.bind",
         "detail": "正文里 \\fact{} 绑定的数字",
         "detail_key": "chain.bind.detail",
         "value": bound, "total": total,
         "ok": total == 0 or bound >= total,
         "state": "ok" if (total == 0 or bound >= total) else "partial"},
        {"key": "reconcile", "label": "回账",
         "label_key": "chain.reconcile",
         "detail": "正文数字回对到事实账",
         "detail_key": "chain.reconcile.detail",
         "value": matched, "total": total,
         "ok": unmatched == 0,
         "state": "ok" if unmatched == 0 else "partial"},
        {"key": "certify", "label": "出证",
         "label_key": "chain.certify",
         "detail": "证据冻结与 PDF 闸",
         "detail_key": "chain.certify.detail",
         "value": entries, "total": entries,
         "ok": bool(lock) and pdf_ok,
         "state": ("ok" if (lock and pdf_ok) else
                   ("partial" if lock else "missing"))},
    ]
    return steps


def report_payload(disk: Path, sibling_disk: Path | None = None) -> dict:
    """检查报告：体检摘要 ＋ 发现列表 ＋ 四步链 ＋ 附加只读闸。

    sibling_disk＝同一项目的另一个盘（双语对账用）；没有就传 None，
    双语对账读数就是「不适用」。

    读不到就结构化报错。
    """
    disk = Path(disk)
    base = {"ok": True, "disk": str(disk), "generated_at": time.strftime(
        "%Y-%m-%dT%H:%M:%S%z")}
    try:
        cfg, facts, sections, red, yellow, hints, summary = run_gate(disk)
    except ConfigError as exc:
        return {**base, "ok": False, "code": "CONFIG_INVALID",
                "error": str(exc), "findings": [], "chain": []}
    except (OSError, ValueError) as exc:
        return {**base, "ok": False, "code": "READ_FAILED",
                "error": "读项目失败：%s" % exc, "findings": [], "chain": []}

    findings = [_finding_dict(i) for i in red] + [_finding_dict(w) for w in yellow]
    findings.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["code"]))
    digest = _safe_digest(cfg)
    lock = None
    try:
        lock = read_lock(disk)
    except Exception:  # noqa: BLE001 - 锁读不动不影响体检
        lock = None

    summary = dict(summary or {})
    health = {
        "red": len(red),
        "yellow": len(yellow),
        "hints": len(hints),
        "facts": len(facts),
        "sections": len(sections),
        "status": "red" if red else ("yellow" if yellow else "ok"),
        "digest": digest,
        "digest_short": digest[:8],
        "numbers": {k: summary.get(k) for k in
                    ("numbers_total", "numbers_matched", "numbers_bound",
                     "numbers_unbound", "numbers_unmatched")},
        "citations": {k: summary.get(k) for k in
                      ("cites_total", "cites_unique", "bib_entries")},
        "bib_unused": list(summary.get("bib_unused") or []),
        "pdf": dict(summary.get("pdf") or {}),
        "coverage": dict(summary.get("coverage") or {}),
    }
    gates = {
        "style": _style_gate(cfg, sections),
        "mirror": _mirror_gate(disk, sibling_disk),
    }
    return {
        **base,
        "health": health,
        "findings": findings,
        "chain": _chain_steps(summary, lock, len(facts)),
        "gates": gates,
        "evidence": {"frozen": bool(lock),
                     "entries": int((lock or {}).get("entries") or 0),
                     "sha256": (lock or {}).get("sha256", ""),
                     "sha256_short": ((lock or {}).get("sha256") or "")[:8]},
    }


# --------------------------------------------------------------------------
# 机器视图
# --------------------------------------------------------------------------

def _ledger_rows(facts) -> list:
    rows = []
    for f in facts:
        source = f.source or ""
        fp = hashlib.sha256(
            "|".join([f.id, f.value, source, f.locator]).encode("utf-8")
        ).hexdigest()
        rows.append({
            "id": f.id,
            "claim": f.claim or "",
            "value": f.value or "",
            "confidence": f.confidence or "",
            "kind": f.kind or "claim",
            "source_file": _fact_file_name(source),
            "source_path": source,
            "locator": f.locator or "",
            "file": f.file or "",
            "line": f.line or 0,
            "fp": fp,
            "fp_short": fp[:8],
        })
    return rows


def machine_payload(disk: Path) -> dict:
    """机器视图：账本表 / 正文扫描 / 文献与证据链 / 导出与命令。"""
    disk = Path(disk)
    base = {"ok": True, "disk": str(disk)}
    try:
        cfg, facts, sections, red, yellow, hints, summary = run_gate(disk)
    except ConfigError as exc:
        return {**base, "ok": False, "code": "CONFIG_INVALID", "error": str(exc)}
    except (OSError, ValueError) as exc:
        return {**base, "ok": False, "code": "READ_FAILED",
                "error": "读项目失败：%s" % exc}

    summary = dict(summary or {})
    rows = _ledger_rows(facts)
    total = int(summary.get("numbers_total") or 0)
    matched = int(summary.get("numbers_matched") or 0)

    scan_rows = []
    for rel, _text in sections:
        target = disk / rel
        try:
            size = target.stat().st_size
        except OSError:
            size = 0
        scan_rows.append({"file": rel, "name": Path(rel).name, "bytes": size})

    lock = None
    try:
        lock = read_lock(disk)
    except Exception:  # noqa: BLE001
        lock = None
    log_rows = []
    log_file = disk / "audit" / "evidence-log.ndjson"
    if log_file.is_file():
        try:
            for line in log_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                log_rows.append({"action": item.get("action", ""),
                                 "hash": (item.get("hash") or "")[:8],
                                 "entries": item.get("entries", 0),
                                 "reason": item.get("reason", "")})
        except OSError:
            log_rows = []

    groups = {
        "ledger": {
            "title": "账本表",
            "rows": rows,
            "total": len(rows),
            "digest_short": (_safe_digest(cfg) or "")[:8],
        },
        "scan": {
            "title": "正文扫描",
            "rows": scan_rows,
            "sections": len(sections),
            "numbers_total": total,
            "numbers_matched": matched,
            "numbers_unbound": int(summary.get("numbers_unbound") or 0),
            "numbers_unmatched": int(summary.get("numbers_unmatched") or 0),
            "coverage_percent": int(round(matched * 100 / total)) if total else 0,
            "annotations_skipped": int(summary.get("annotations_skipped") or 0),
        },
        "chain": {
            "title": "文献与证据链",
            "cites_total": int(summary.get("cites_total") or 0),
            "cites_unique": int(summary.get("cites_unique") or 0),
            "bib_entries": int(summary.get("bib_entries") or 0),
            "bib_files": list(summary.get("bib_files") or []),
            "bib_unused": list(summary.get("bib_unused") or []),
            "frozen": bool(lock),
            "evidence_entries": int((lock or {}).get("entries") or 0),
            "evidence_sha256": (lock or {}).get("sha256", ""),
            "evidence_sha256_short": ((lock or {}).get("sha256") or "")[:8],
            "evidence_log": log_rows,
            "pdf": dict(summary.get("pdf") or {}),
        },
        "export": {
            "title": "导出与命令",
            "commands": [
                {"label": "真闸体检（只读）", "cmd": "factscribe audit --json %s" % disk},
                {"label": "账本体检（只读）", "cmd": "factscribe check --json %s" % disk},
                {"label": "追溯矩阵（写 audit/matrix.md）",
                 "cmd": "factscribe matrix %s" % disk},
                {"label": "证据冻结（写 audit/evidence.lock）",
                 "cmd": "factscribe evidence freeze %s" % disk},
            ],
            "note": "本视图只读；上面前两条是只读命令，后两条会写盘，需人自己跑。",
        },
    }
    return {**base, "groups": groups,
            "findings": len(red) + len(yellow)}


# --------------------------------------------------------------------------
# 重跑（只读 subprocess 真闸）
# --------------------------------------------------------------------------

def rerun(disk: Path, timeout: float = RERUN_TIMEOUT) -> dict:
    """只读重跑真闸：跑前跑后对项目目录做哈希对比。"""
    disk = Path(disk)
    started = time.time()
    before = _dir_manifest(disk)
    cmd = [sys.executable, "-m", "factscribe", *GATE_COMMAND, str(disk)]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        after = _dir_manifest(disk)
        return {"ok": False, "code": "RERUN_TIMEOUT",
                "error": "真闸超时（上限 %g 秒）：%s" % (timeout, " ".join(cmd)),
                "timeout_seconds": timeout,
                "duration_ms": int((time.time() - started) * 1000),
                "readonly": _diff_manifest(before, after)}
    except OSError as exc:
        return {"ok": False, "code": "RERUN_FAILED",
                "error": "起不动真闸进程：%s" % exc,
                "duration_ms": int((time.time() - started) * 1000)}
    after = _dir_manifest(disk)
    readonly = _diff_manifest(before, after)

    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    payload = None
    try:
        payload = json.loads(stdout)
    except ValueError:
        payload = None
    if payload is None:
        return {"ok": False, "code": "RERUN_FAILED",
                "error": "真闸没有吐出可解析的 JSON（退出码 %d）" % proc.returncode,
                "exit_code": proc.returncode, "stderr": stderr[-4000:],
                "duration_ms": int((time.time() - started) * 1000),
                "readonly": readonly}
    # 退出码是「真闸跑没跑起来」的唯一权威判据：
    # 工具级失败（配置错/内部错/工具缺失）＝重跑失败；
    # 其余＝真闸跑完了，红黄多少是**体检结论**，照样算重跑成功。
    exit_code = payload.get("exit")
    if exit_code is None:
        exit_code = proc.returncode
    try:
        exit_code = int(exit_code)
    except (TypeError, ValueError):
        exit_code = proc.returncode
    if exit_code in GATE_FAIL_EXITS:
        return {"ok": False,
                "code": str(payload.get("code") or "RERUN_FAILED"),
                "error": str(payload.get("message") or "真闸报错"),
                "exit_code": exit_code,
                "findings": payload.get("findings") or [],
                "duration_ms": int((time.time() - started) * 1000),
                "readonly": readonly,
                "command": " ".join(cmd),
                "stderr": stderr[-2000:]}
    verdict = _VERDICT_BY_EXIT.get(exit_code)
    if verdict is None:
        verdict = "red" if (payload.get("findings") or []) else "ok"
    return {
        "ok": True,
        "code": "RERUN_OK",
        "exit_code": exit_code,
        "verdict": verdict,
        "severity": payload.get("severity", ""),
        "summary": payload.get("summary") or {},
        "findings": payload.get("findings") or [],
        "duration_ms": int((time.time() - started) * 1000),
        "readonly": readonly,
        "command": " ".join(cmd),
        "stderr": stderr[-2000:],
    }
