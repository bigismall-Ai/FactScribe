# -*- coding: utf-8 -*-
"""argparse、子命令实现、退出码与 python -m factscribe 入口。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .audit import run_audit, run_check
from .config import (ConfigError, load_config, load_facts, load_sections)
from .constants import (EXIT_CONFIG, EXIT_INTERNAL, EXIT_OK, EXIT_RED,
                        EXIT_YELLOW, VERSION)
from .report import (PREAMBLE_TEXT, _emit, _human_audit, _human_check,
                     _payload, _severity_of, render_matrix)

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
        description="论文数字与引用的机械闸门（check / audit / matrix / build / preamble）")
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
    return p


def cmd_check(args) -> int:
    cfg = load_config(Path(args.project))
    facts = load_facts(cfg)
    issues, warnings, conflicts, summary = run_check(cfg, facts)
    code = _exit_code(len(issues), len(warnings), getattr(args, "strict", False))
    text = _human_check(cfg, facts, issues, warnings, conflicts, summary, code)
    _emit(_payload("check", _severity_of(code), code,
                   summary=summary,
                   issues=[i.as_dict() for i in issues],
                   warnings=[i.as_dict() for i in warnings],
                   hints=[], conflicts=conflicts), text, args.json)
    return code


def cmd_audit(args) -> int:
    cfg = load_config(Path(args.project))
    facts = load_facts(cfg)
    sections = load_sections(cfg)
    red, yellow, hints, summary, unresolved = run_audit(
        cfg, facts, sections, resolve=getattr(args, "resolve", False))
    code = _exit_code(len(red), len(yellow), getattr(args, "strict", False))
    text = _human_audit(cfg, red, yellow, hints, summary, unresolved, code)
    _emit(_payload("audit", _severity_of(code), code,
                   summary=summary,
                   issues=[i.as_dict() for i in red],
                   warnings=[i.as_dict() for i in yellow],
                   hints=[h.as_dict() for h in hints],
                   coverage=summary.get("coverage", {}),
                   resolved=unresolved), text, args.json)
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
    _emit(_payload("matrix", "ok", EXIT_OK, path=str(out), rows=rows,
                   facts=len(rows)), human, args.json)
    return EXIT_OK


def cmd_preamble(args) -> int:
    cfg = load_config(Path(args.project))
    out = Path(args.out) if getattr(args, "out", None) else cfg.root / "audit" / "preamble.tex"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PREAMBLE_TEXT, encoding="utf-8")
    human = "== paperkit preamble ==\n写盘：%s\n%s" % (out, PREAMBLE_TEXT)
    _emit(_payload("preamble", "ok", EXIT_OK, path=str(out)), human, args.json)
    return EXIT_OK


def cmd_build(args) -> int:
    cfg = load_config(Path(args.project))
    code, out = run_build(cfg)
    _emit(_payload("build", "ok" if code == EXIT_OK else "violation", code,
                   build=cfg.build, output=out), "== paperkit build ==\n" + out, args.json)
    return code


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"check": cmd_check, "audit": cmd_audit, "matrix": cmd_matrix,
                "build": cmd_build, "preamble": cmd_preamble}
    try:
        return handlers[args.command](args)
    except ConfigError as exc:
        if getattr(args, "json", False):
            print(json.dumps(_payload(args.command, "error", EXIT_CONFIG,
                                      message=str(exc)), ensure_ascii=False, indent=2))
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
