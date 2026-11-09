# -*- coding: utf-8 -*-
"""argparse、子命令实现、退出码与 python -m factscribe 入口。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .audit import _aggregate_exit, run_audit, run_check
from .config import (ConfigError, load_config, load_facts, load_sections)
from .constants import (EXIT_CONFIG, EXIT_INTERNAL, EXIT_OK, EXIT_RED,
                        EXIT_YELLOW, VERSION)
from .pdfgate import verify_pdf
from .protect import compare as compare_protect
from .protect import render_human as render_protect
from .report import (PREAMBLE_TEXT, _config_block, _emit, _human_audit,
                     _human_check, _payload, _severity_of, render_matrix)
from .style import (DISCLAIMER, analyze, build_prompt, filter_new_findings,
                    load_style_rules, render_human)
from .tide import render_human as render_tide
from .tide import run_tide

# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def run_build(cfg: Config) -> tuple[int, str]:
    if not cfg.build.strip():
        return EXIT_OK, "project.build 为空，按契约跳过编译"
    try:
        proc = subprocess.run(cfg.build, shell=True, cwd=str(cfg.root),
                              capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return EXIT_RED, "$ %s\n构建超时（600 秒）被终止" % cfg.build
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return EXIT_RED, "$ %s\n%s\n构建失败：退出码 %d" % (cfg.build, out.rstrip(), proc.returncode)
    return EXIT_OK, "$ %s\n%s\n构建成功：退出码 0" % (cfg.build, out.rstrip())

def _exit_code(red: int, yellow: int, strict: bool = False) -> int:
    if red:
        return EXIT_RED
    if yellow:
        return EXIT_RED if strict else EXIT_YELLOW
    return EXIT_OK

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="factscribe",
        description="论文数字与引用的机械闸门（check / audit / matrix / build / preamble / style / protect）")
    p.add_argument("--version", action="version", version="factscribe %s" % VERSION)
    sub = p.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("check", "校验事实账：id/sha256/人签清单/expr 算术/冲突"),
        ("audit", "核心：内联绑定 + 数字回账 + 引用落稳定标识 + 覆盖报告"),
        ("matrix", "生成 audit/matrix.md 追溯矩阵"),
        ("build", "执行 project.build（v1 仍按 shell 字符串执行，见 SPEC-V1 B5）"),
        ("preamble", "生成 audit/preamble.tex（\\fact / \\pkignore 宏定义）"),
    ):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("project", nargs="?", default=".", help="项目目录（默认当前目录）")
        sp.add_argument("--json", action="store_true", help="机器可读输出（stdout 只出 JSON）")
        if name in ("check", "audit"):
            sp.add_argument("--strict", action="store_true",
                            help="黄也当红（CI 用：未核验不许过）")
        if name == "audit":
            sp.add_argument("--resolve", action="store_true",
                            help="联网核验 arXiv/DOI（超时 5 秒；失败标 unverified 黄）")
        if name == "matrix":
            sp.add_argument("--out", default=None, help="默认 audit/matrix.md")
        if name == "preamble":
            sp.add_argument("--out", default=None, help="默认 audit/preamble.tex")
    sp = sub.add_parser("verify-pdf", help="PDF 回检：文本层/栅格/双向多重集/stamp（V3.0）")
    sp.add_argument("pdf", help="最终 PDF 路径")
    sp.add_argument("--report", required=True, help="audit/report.json（被签的那一份）")
    sp.add_argument("--stamp", default=None, help="audit/stamp.json（有则必须先验信任链）")
    sp.add_argument("--keys", default=None, help="项目外公钥登记 approver_keys.json")
    sp.add_argument("--json", action="store_true", help="（本命令默认只输出 JSON）")
    sp = sub.add_parser(
        "style", help="文风闸：只报公式化写作特征（黄牌 exit 3），不阻断、不改正文")
    sp.add_argument("project", nargs="?", default=".", help="项目目录（默认当前目录）")
    sp.add_argument("--json", action="store_true", help="机器可读输出（stdout 只出 JSON）")
    sp.add_argument("--prompt", action="store_true",
                    help="只输出给 LLM 的改写指令（≤ 400 字）")
    sp.add_argument("--rules", default=None,
                    help="style-rules.toml 路径（默认项目根，其次仓根）")
    sp.add_argument("--diff", default=None, metavar="BEFORE",
                    help="改写前目录：只报本次改写新增的违规，并启用标题"
                         "关系词/主语丢失比对（需该目录有 paperkit.toml）")
    sp.add_argument("--report-unregistered", action="store_true",
                    help="打开 TERM_UNREGISTERED 提示（默认关；只查标题，"
                         "结果进 info 通道，不进 findings、不影响退出码）")
    sp = sub.add_parser(
        "protect", help="改写保护面比对：前后目录的 facts/数字/引用/公式/表格/交叉引用")
    sp.add_argument("--before", required=True, help="改写前目录")
    sp.add_argument("--after", required=True, help="改写后目录")
    sp.add_argument("--json", action="store_true", help="机器可读输出（stdout 只出 JSON）")
    sp.add_argument("--allow-renames", action="store_true",
                    help="章节标题变化降为信息（不让它拉黄）")
    sp = sub.add_parser(
        "tide", help="潮汐式改动账：涨/落/波及面/闭合三条件，全成或全退")
    sp.add_argument("--before", required=True, help="改前目录")
    sp.add_argument("--after", required=True, help="改后目录")
    sp.add_argument("--out", default=None,
                    help="事件账本（默认 <after>/audit/tide-events.ndjson）")
    sp.add_argument("--ignore", action="append", default=None, metavar="GLOB",
                    help="追加忽略规则（可重复），在默认 LaTeX 构建产物表之上"
                         "；fnmatch 对相对路径匹配")
    sp.add_argument("--no-default-ignore", action="store_true",
                    help="关掉默认忽略表（排查用）")
    sp.add_argument("--json", action="store_true",
                    help="机器可读输出（stdout 只出 JSON）")
    return p


def cmd_check(args) -> int:
    cfg = load_config(Path(args.project))
    facts = load_facts(cfg)
    issues, warnings, conflicts, summary = run_check(cfg, facts)
    code = _aggregate_exit(issues, warnings, getattr(args, "strict", False))
    text = _human_check(cfg, facts, issues, warnings, conflicts, summary, code)
    if cfg.warnings:
        text += "\n配置告警：%d 条（--json 的 config.warnings 有明细）" % len(cfg.warnings)
    payload = _payload("check", _severity_of(code), code,
                       summary=summary,
                       issues=[i.as_dict() for i in issues],
                       warnings=[i.as_dict() for i in warnings],
                       hints=[], conflicts=conflicts)
    payload["config"] = _config_block(cfg)
    payload["config_warnings"] = list(cfg.warnings)
    _emit(payload, text, args.json)
    return code


def cmd_audit(args) -> int:
    cfg = load_config(Path(args.project))
    facts = load_facts(cfg)
    sections = load_sections(cfg)
    red, yellow, hints, summary, unresolved = run_audit(
        cfg, facts, sections, resolve=getattr(args, "resolve", False))
    code = _aggregate_exit(red, yellow, getattr(args, "strict", False),
                           integrity_first=cfg.is_v3)
    text = _human_audit(cfg, red, yellow, hints, summary, unresolved, code)
    if cfg.warnings:
        text += "\n配置告警：%d 条（--json 的 config.warnings 有明细）" % len(cfg.warnings)
    findings = [i.as_dict() for i in red] + [w.as_dict() for w in yellow]
    payload = _payload("audit", _severity_of(code), code,
                       summary=summary,
                       findings=findings,
                       issues=[i.as_dict() for i in red],
                       warnings=[i.as_dict() for i in yellow],
                       hints=[h.as_dict() for h in hints],
                       coverage=summary.get("coverage", {}),
                       resolved=unresolved)
    payload["config"] = _config_block(cfg)
    payload["config_warnings"] = list(cfg.warnings)
    _emit(payload, text, args.json)
    return code


def cmd_verify_pdf(args) -> int:
    issues, warnings, code = verify_pdf(
        Path(args.pdf), Path(args.report),
        Path(args.stamp) if args.stamp else None,
        Path(args.keys) if args.keys else None)
    human = "== factscribe verify-pdf ==\n%s\n红：%d   黄：%d   退出码：%d" % (
        args.pdf, len(issues), len(warnings), code)
    _emit(_payload("verify-pdf", _severity_of(code), code,
                   issues=[i.as_dict() for i in issues],
                   warnings=[w.as_dict() for w in warnings]), human, True)
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
    payload = _payload("matrix", "ok", EXIT_OK, path=str(out), rows=rows,
                       facts=len(rows))
    payload["config"] = _config_block(cfg)
    payload["config_warnings"] = list(cfg.warnings)
    _emit(payload, human, args.json)
    return EXIT_OK


def cmd_preamble(args) -> int:
    cfg = load_config(Path(args.project))
    out = Path(args.out) if getattr(args, "out", None) else cfg.root / "audit" / "preamble.tex"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PREAMBLE_TEXT, encoding="utf-8")
    human = "== paperkit preamble ==\n写盘：%s\n%s" % (out, PREAMBLE_TEXT)
    payload = _payload("preamble", "ok", EXIT_OK, path=str(out))
    payload["config"] = _config_block(cfg)
    payload["config_warnings"] = list(cfg.warnings)
    _emit(payload, human, args.json)
    return EXIT_OK


def cmd_build(args) -> int:
    cfg = load_config(Path(args.project))
    code, out = run_build(cfg)
    payload = _payload("build", "ok" if code == EXIT_OK else "violation", code,
                       build=cfg.build, output=out)
    payload["config"] = _config_block(cfg)
    payload["config_warnings"] = list(cfg.warnings)
    _emit(payload, "== paperkit build ==\n" + out, args.json)
    return code


def cmd_style(args) -> int:
    cfg = load_config(Path(args.project))
    sections = load_sections(cfg)
    rules, rules_path = load_style_rules(cfg.root, args.rules)
    before = None
    baseline = None
    if getattr(args, "diff", None):
        before_cfg = load_config(Path(args.diff))
        before_sections = load_sections(before_cfg)
        before = (before_cfg, before_sections)
    result = analyze(cfg, sections, rules, rules_path=rules_path,
                     before=before,
                     report_unregistered=bool(args.report_unregistered))
    if before is not None:
        baseline = analyze(before[0], before[1], rules, rules_path=rules_path)
        result = filter_new_findings(result, baseline)
    code = result.exit_code

    if args.prompt and not args.json:
        print(build_prompt(result))
        return code

    human = render_human(result, cfg.root)
    if before is not None:
        human += ("\n对比    : %s（改前 %d 处 → 只报新增 %d 处）"
                  % (Path(args.diff), len(baseline.findings),
                     len(result.findings)))
    if cfg.warnings:
        human += "\n配置告警：%d 条（--json 的 config.warnings 有明细）" % len(cfg.warnings)
    payload = _payload("style", _severity_of(code), code,
                       metrics=result.metrics,
                       thresholds=dict(result.thresholds),
                       findings=[f.as_dict() for f in result.findings],
                       info=[f.as_dict() for f in getattr(result, "info", [])],
                       paragraphs=[p.as_dict() for p in result.paragraphs],
                       fired=result.fired,
                       summary=result.summary,
                       stage_assessment=dict(result.stage_assessment),
                       disclaimer=DISCLAIMER,
                       rules=rules_path)
    if before is not None:
        payload["diff"] = {"before": str(Path(args.diff)),
                           "baseline_findings": len(baseline.findings),
                           "new_findings": len(result.findings)}
    if args.prompt:
        payload["prompt"] = build_prompt(result)
    payload["config"] = _config_block(cfg)
    payload["config_warnings"] = list(cfg.warnings)
    _emit(payload, human, args.json)
    return code


def cmd_protect(args) -> int:
    result = compare_protect(Path(args.before), Path(args.after),
                             allow_renames=args.allow_renames)
    code = result.exit_code
    payload = _payload("protect", _severity_of(code), code,
                       before=str(result.before), after=str(result.after),
                       allow_renames=bool(result.allow_renames),
                       summary=result.summary(),
                       findings=[f.as_dict() for f in result.findings])
    _emit(payload, render_protect(result), args.json)
    return code


def cmd_tide(args) -> int:
    result = run_tide(Path(args.before), Path(args.after),
                      Path(args.out) if args.out else None,
                      ignore=args.ignore,
                      default_ignore=not args.no_default_ignore)
    code = result.exit_code
    payload = _payload("tide", "ok" if code == EXIT_OK else "violation", code,
                       tx=result.tx,
                       criteria=result.criteria(),
                       reasons=list(result.reasons),
                       rises=[r.as_dict() for r in result.rises],
                       falls=[f.as_dict() for f in result.falls],
                       affect=list(result.affect),
                       findings=[f.as_dict() for f in result.findings],
                       ledger=str(result.ledger_path),
                       view=(str(result.view_path)
                             if result.view_written else None),
                       ignored=list(result.ignored),
                       ignore=list(result.ignore),
                       events=len(result.rises) + len(result.falls) + 1)
    payload["status"] = result.status      # 事务状态：commit / rollback
    _emit(payload, render_tide(result), args.json)
    return code


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"check": cmd_check, "audit": cmd_audit, "matrix": cmd_matrix,
                "build": cmd_build, "preamble": cmd_preamble,
                "verify-pdf": cmd_verify_pdf, "style": cmd_style,
                "protect": cmd_protect, "tide": cmd_tide}
    try:
        return handlers[args.command](args)
    except ConfigError as exc:
        code = getattr(exc, "code", "CONFIG_INVALID")
        if getattr(args, "json", False):
            payload = _payload(args.command, "error", EXIT_CONFIG,
                               message=str(exc))
            payload["code"] = code
            # §8：CONFIG 类码也必须出现在 findings/issues 里，判卷器不用
            # 猜顶层 code 字段。唯一映射：一个错误一个码。
            finding = {"severity": "red", "code": code, "message": str(exc)}
            payload["findings"] = [finding]
            payload["issues"] = [finding]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("factscribe: 配置/用法错：%s" % exc, file=sys.stderr)
        return EXIT_CONFIG
    except Exception as exc:  # noqa: BLE001 - 内部错误必须与「有违例」分开
        if getattr(args, "json", False):
            print(json.dumps(_payload(args.command, "error", EXIT_INTERNAL,
                                      message="%s: %s" % (type(exc).__name__, exc)),
                             ensure_ascii=False, indent=2))
        else:
            print("factscribe: 工具内部错误：%s: %s" % (type(exc).__name__, exc),
                  file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
