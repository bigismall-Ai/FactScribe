# -*- coding: utf-8 -*-
"""argparse、子命令实现、退出码与 python -m factscribe 入口。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import mdscan
from .audit import _aggregate_exit, run_audit, run_check
from .buildpdf import _is_font_error, auto_build
from .config import (Config, ConfigError, load_config, load_facts,
                     load_sections)
from .constants import (EXIT_CONFIG, EXIT_INTERNAL, EXIT_OK, EXIT_RED,
                        EXIT_YELLOW, VERSION)
from .fonts import FontCacheError, fetch as fetch_fandol, font_status
from .fonts import render_fetch as render_fonts_fetch
from .fonts import render_status as render_fonts_status
from .pdfgate import verify_pdf
from .polish import (build_plan, plan_payload, playbook_text, render_plan)
from .prescribe import (NOTE, load_prescriptions, prescriptions_for,
                        priority_payload, render_bundle, resolve_conflicts)
from .protect import compare as compare_protect
from .protect import render_human as render_protect
from .report import (PREAMBLE_TEXT, _config_block, _emit, _human_audit,
                     _human_check, _payload, _severity_of, render_matrix)
from .review import payload as review_payload
from .review import render_human as render_review
from .review import run_review
from .style import (DISCLAIMER, analyze, build_prompt, filter_new_findings,
                    load_style_rules, render_human)
from .term_suggest import (add_from_tsv, json_payload, render_tsv,
                           suggest)
from .tide import DEFAULT_SNAPSHOT_ROOT
from .tide import render_human as render_tide
from .tide import render_restore as render_tide_restore
from .tide import render_snapshot as render_tide_snapshot
from .tide import restore_snapshot, run_tide, save_snapshot

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


def run_build_step(cfg: Config, engine: str = "tectonic",
                   cjk_font: str | None = None,
                   keep_temp: bool = False,
                   font_fallback: bool = False) -> tuple[int, str, dict]:
    """批 122：build 子命令与 audit/verify-pdf --build 共用同一条编译路。

    ``font_fallback`` 只在闸门（audit/verify-pdf --build）打开：``project.build``
    非空时仍按原样跑 shell，但若它败在字体上（批 120 §3.2 的特征），就复用
    自动路径的临时副本 CJK 兜底重试——项目里的 ``.tex`` 仍不改。
    """
    if cfg.build.strip():
        code, out = run_build(cfg)
        if code != EXIT_OK and font_fallback and _is_font_error(out):
            return auto_build(cfg.root, output=cfg.output, engine=engine,
                              cjk_font=cjk_font, keep_temp=keep_temp,
                              root_tex=cfg.root_tex or "main.tex")
        return code, out, {}
    return auto_build(cfg.root, output=cfg.output, engine=engine,
                      cjk_font=cjk_font, keep_temp=keep_temp,
                      root_tex=cfg.root_tex or "main.tex")


def _build_block(cfg: Config, code: int, info: dict,
                 ran: bool = True) -> dict:
    """--json 的 build 字段：ran/ok/pdf_bytes（pdf_bytes 只在成功时非零）。"""
    ok = code == EXIT_OK
    size = 0
    if ok:
        size = int(info.get("pdf_bytes") or 0)
        if size == 0:
            pdf = cfg.root / cfg.output
            if pdf.is_file():
                size = pdf.stat().st_size
    return {"ran": ran, "ok": ok, "pdf_bytes": size}


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
        ("build", "执行 project.build；为空时用 tectonic 自动编译 main.tex"),
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
            sp.add_argument("--build", action="store_true",
                            help="审计前先编 PDF（project.build 非空跑它；空则用 tectonic 自动编）")
        if name == "matrix":
            sp.add_argument("--out", default=None, help="默认 audit/matrix.md")
        if name == "preamble":
            sp.add_argument("--out", default=None, help="默认 audit/preamble.tex")
        if name == "build":
            sp.add_argument("--engine", default="tectonic",
                            help="自动编译用的引擎（默认 tectonic；可给绝对路径）")
            sp.add_argument("--cjk-font", default=None, metavar="PATH",
                            help="中文字体文件（缺省用 fc-match 找 STHeiti）")
            sp.add_argument("--keep-temp", action="store_true",
                            help="保留临时副本并打印路径（默认清理）")
    sp = sub.add_parser("verify-pdf", help="PDF 回检：文本层/栅格/双向多重集/stamp（V3.0）")
    sp.add_argument("pdf", help="最终 PDF 路径")
    sp.add_argument("--report", required=True, help="audit/report.json（被签的那一份）")
    sp.add_argument("--stamp", default=None, help="audit/stamp.json（有则必须先验信任链）")
    sp.add_argument("--keys", default=None, help="项目外公钥登记 approver_keys.json")
    sp.add_argument("--project", default=None,
                    help="--build 用的项目目录（默认取 PDF 所在目录）")
    sp.add_argument("--build", action="store_true",
                    help="回检前先编 PDF（项目目录默认取 PDF 上一级）")
    sp.add_argument("--json", action="store_true", help="（本命令默认只输出 JSON）")
    sp = sub.add_parser(
        "style", help="文风闸：只报公式化写作特征（黄牌 exit 3），不阻断、不改正文")
    sp.add_argument("project", nargs="?", default=None,
                    help="项目目录（默认当前目录；与 --doc 互斥）")
    sp.add_argument("--doc", action="append", nargs="+", default=None,
                    metavar="FILE",
                    help="文档模式：直接扫文件，不需要 paperkit.toml；"
                         "按扩展名判定格式（.md/.markdown = Markdown，"
                         ".tex = LaTeX，其它 = 纯文本）。可重复，可一次多个")
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
    sp.add_argument("--report-abbrev", action="store_true",
                    help="打开 ABBREV_FIRST_USE（默认关；缩写首现未展开，"
                         "按条报，进 findings）")
    sp = sub.add_parser(
        "protect", help="改写保护面比对：前后目录的 facts/数字/引用/公式/表格/交叉引用")
    sp.add_argument("--before", required=True, help="改写前目录")
    sp.add_argument("--after", required=True, help="改写后目录")
    sp.add_argument("--json", action="store_true", help="机器可读输出（stdout 只出 JSON）")
    sp.add_argument("--allow-renames", action="store_true",
                    help="章节标题变化降为信息（不让它拉黄）")
    sp = sub.add_parser(
        "tide", help="潮汐式改动账：涨/落/波及面/闭合三条件，全成或全退")
    sp.add_argument("--before", default=None, help="改前目录（比对模式必填）")
    sp.add_argument("--after", default=None,
                    help="改后目录（比对模式必填；快照模式为要快照的目录）")
    sp.add_argument("--out", default=None,
                    help="事件账本（默认 <after>/audit/tide-events.ndjson）")
    sp.add_argument("--snapshot", default=None, metavar="STORE",
                    help="快照库根（默认 ./.tide）；给了即保存模式")
    sp.add_argument("--restore", default=None, metavar="SNAPSHOT_ID",
                    help="按快照ID（全宽或任意唯一前缀）恢复，需配 --into")
    sp.add_argument("--into", default=None, metavar="DIR",
                    help="恢复目标目录（与 --restore 一起用）")
    sp.add_argument("--ignore", action="append", default=None, metavar="GLOB",
                    help="追加忽略规则（可重复），在默认 LaTeX 构建产物表之上"
                         "；fnmatch 对相对路径匹配")
    sp.add_argument("--no-default-ignore", action="store_true",
                    help="关掉默认忽略表（排查用）")
    sp.add_argument("--json", action="store_true",
                    help="机器可读输出（stdout 只出 JSON）")
    sp = sub.add_parser(
        "review",
        help="改写验收一条命令：protect + style --diff + tide 的组合，不新增判据",
        description="改写验收一条命令：protect + style --diff + tide 的组合，"
                    "不新增判据。保护面有红或 tide 不闭合即拒绝（exit 1）；"
                    "新增违规超过 --allow-new 即需复核（exit 3）；三项全过才"
                    "通过（exit 0）。--snapshot 只在通过时存快照。")
    sp.add_argument("--before", required=True, help="改写前目录")
    sp.add_argument("--after", required=True, help="改写后目录")
    sp.add_argument("--snapshot", default=None, metavar="STORE",
                    help="判定为「通过」时保存快照的库根（其余判定不存）")
    sp.add_argument("--allow-new", dest="allow_new", type=int, default=0,
                    metavar="N", help="允许的新增 style 违规条数（默认 0）")
    sp.add_argument("--json", action="store_true",
                    help="机器可读输出（stdout 只出 JSON）")
    sp = sub.add_parser(
        "polish",
        help="润色工单：打印操作手册，或按处方优先序出工作单（不新增判据）",
        description="润色工单：--print 打印写给执行改写的模型的操作手册；"
                    "--plan <项目> 扫描 style 的命中，按处方优先序出工作单。"
                    "没有处方的错误码一律标「无处方：只提示，不许为它改句子」。"
                    "本命令不是闸门，成功永远退出 0。")
    group = sp.add_mutually_exclusive_group(required=True)
    group.add_argument("--print", dest="print_playbook", action="store_true",
                       help="打印操作手册（Markdown）")
    group.add_argument("--plan", nargs="?", const=".", default=None,
                       metavar="PROJECT",
                       help="打印工作单（项目目录，默认当前目录）")
    sp.add_argument("--json", action="store_true",
                    help="机器可读输出（stdout 只出 JSON；仅 --plan 有效）")
    sp = sub.add_parser(
        "prescribe",
        help="处方层：只给可执行改法（数据文件），不参与判据、不产生分数")
    sp.add_argument("names", nargs="*", metavar="NAME",
                    help="处方名（可多个；多个一起输出时按优先序裁决并标「让位」）")
    sp.add_argument("--list", action="store_true", help="列出全部处方")
    sp.add_argument("--for", dest="for_code", default=None, metavar="CODE",
                    help="按错误码查处方（例：HEADING_ECHO）")
    sp.add_argument("--json", action="store_true",
                    help="机器可读输出（stdout 只出 JSON）")
    sp = sub.add_parser(
        "fonts", help="Fandol 中文字体缓存：--status 看状态，--fetch 按需下载")
    fgroup = sp.add_mutually_exclusive_group(required=True)
    fgroup.add_argument("--status", action="store_true",
                        help="查看缓存目录与四个必需 OTF 是否齐")
    fgroup.add_argument("--fetch", action="store_true",
                        help="下载 Fandol 包并解压到缓存（已完整则跳过）")
    sp.add_argument("--url", default=None, metavar="URL",
                    help="字体包地址或本地路径（默认 CTAN fandol.zip）")
    sp.add_argument("--force", action="store_true",
                    help="缓存已完整也重下")
    sp.add_argument("--json", action="store_true",
                    help="机器可读输出（stdout 只出 JSON）")
    sp = sub.add_parser(
        "terms", help="术语候选抽取与人工入表（零 LLM：suggest / add）")
    tsp = sp.add_subparsers(dest="terms_action", required=True)
    ss = tsp.add_parser("suggest", help="从论文语料抽术语候选（TSV）")
    ss.add_argument("root", help="论文目录")
    ss.add_argument("--min-count", type=int, default=4, metavar="N",
                    help="最少出现次数（默认 4）")
    ss.add_argument("--min-sections", type=int, default=3, metavar="N",
                    help="最少跨小节数（默认 3）")
    ss.add_argument("--out", default=None, metavar="FILE",
                    help="候选 TSV 落盘路径（默认只出 stdout）")
    ss.add_argument("--glossary", default=None, metavar="TSV",
                    help="既有词表（默认仓内 paper.tsv ＋ workspace.tsv）")
    ss.add_argument("--json", action="store_true",
                    help="机器可读输出（stdout 只出 JSON）")
    sa = tsp.add_parser("add", help="只把人工 --pick 点名的形式写进 paper.tsv")
    sa.add_argument("--from", dest="from_path", required=True, metavar="FILE",
                    help="terms suggest 产出的候选 TSV")
    sa.add_argument("--pick", action="append", required=True,
                    metavar="SURFACE",
                    help="人工指定的表面形式；逗号分隔，可重复")
    sa.add_argument("--glossary", default=None, metavar="TSV",
                    help="目标词表（默认 factscribe/terms/paper.tsv）")
    sa.add_argument("--json", action="store_true",
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
    build = {"ran": False, "ok": True, "pdf_bytes": 0}
    if getattr(args, "build", False):
        bcode, bout, binfo = run_build_step(cfg, font_fallback=True)
        build = _build_block(cfg, bcode, binfo)
        if bcode != EXIT_OK:
            payload = _payload("audit", _severity_of(bcode), bcode,
                               build=build, build_output=bout)
            payload["config"] = _config_block(cfg)
            payload["config_warnings"] = list(cfg.warnings)
            _emit(payload, "== paperkit audit ==\n编译失败，审计中止（退出码 %d）\n%s"
                  % (bcode, bout), args.json)
            return bcode
    facts = load_facts(cfg)
    sections = load_sections(cfg)
    red, yellow, hints, summary, unresolved = run_audit(
        cfg, facts, sections, resolve=getattr(args, "resolve", False))
    code = _aggregate_exit(red, yellow, getattr(args, "strict", False),
                           integrity_first=cfg.is_v3)
    text = _human_audit(cfg, red, yellow, hints, summary, unresolved, code)
    if build["ran"]:
        text += "\nbuild  : 已编译（%d 字节）" % build["pdf_bytes"]
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
                       resolved=unresolved,
                       build=build)
    payload["config"] = _config_block(cfg)
    payload["config_warnings"] = list(cfg.warnings)
    _emit(payload, text, args.json)
    return code


def cmd_verify_pdf(args) -> int:
    build = {"ran": False, "ok": True, "pdf_bytes": 0}
    if getattr(args, "build", False):
        project = Path(args.project) if args.project else Path(args.pdf).parent
        cfg = load_config(project)
        bcode, bout, binfo = run_build_step(cfg, font_fallback=True)
        build = _build_block(cfg, bcode, binfo)
        if bcode != EXIT_OK:
            payload = _payload("verify-pdf", _severity_of(bcode), bcode,
                               build=build, build_output=bout)
            _emit(payload, "", True)
            return bcode
    stats: dict = {}
    issues, warnings, code = verify_pdf(
        Path(args.pdf), Path(args.report),
        Path(args.stamp) if args.stamp else None,
        Path(args.keys) if args.keys else None,
        stats=stats)
    masked = int(stats.get("structural_masked", 0))
    by_cat = stats.get("structural_masked_by", {})
    human = ("== factscribe verify-pdf ==\n%s\n结构性 token 掩掉 %d 个（%s）\n"
             "红：%d   黄：%d   退出码：%d" % (
                 args.pdf, masked,
                 "、".join("%s %d" % (k, v) for k, v in by_cat.items()) or "无",
                 len(issues), len(warnings), code))
    payload = _payload("verify-pdf", _severity_of(code), code,
                       issues=[i.as_dict() for i in issues],
                       warnings=[w.as_dict() for w in warnings],
                       structural_masked=masked,
                       structural_masked_by=by_cat,
                       build=build)
    _emit(payload, human, True)
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


def cmd_fonts(args) -> int:
    if args.status:
        info = font_status()
        payload = _payload("fonts", "ok", EXIT_OK, action="status", **info)
        _emit(payload, render_fonts_status(info), args.json)
        return EXIT_OK
    try:
        info = fetch_fandol(url=args.url, force=args.force)
    except FontCacheError as exc:
        payload = _payload("fonts", "error", EXIT_INTERNAL,
                           action="fetch", message=str(exc))
        _emit(payload, "== factscribe fonts ==\n%s" % exc, args.json)
        return EXIT_INTERNAL
    payload = _payload("fonts", "ok", EXIT_OK, action="fetch", **info)
    _emit(payload, render_fonts_fetch(info), args.json)
    return EXIT_OK


def cmd_build(args) -> int:
    cfg = load_config(Path(args.project))
    code, out, info = run_build_step(
        cfg, engine=args.engine, cjk_font=args.cjk_font,
        keep_temp=args.keep_temp, font_fallback=True)
    payload = _payload("build", "ok" if code == EXIT_OK else "violation", code,
                       build=cfg.build, output=out)
    payload.update(info)
    payload["config"] = _config_block(cfg)
    payload["config_warnings"] = list(cfg.warnings)
    _emit(payload, "== paperkit build ==\n" + out, args.json)
    return code


def _cmd_style_doc(args, paths: list[str]) -> int:
    """``style --doc``：文档模式，不读项目配置，按扩展名分派解析器。"""
    if args.project is not None:
        raise ConfigError("--doc 与项目目录不能同时给出：doc 模式不需要 "
                          "paperkit.toml；项目模式请去掉 --doc")
    if getattr(args, "diff", None):
        raise ConfigError("--doc 不支持 --diff：改写前目录属于项目形态")
    root = Path.cwd()
    sections = []
    formats = {}
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            raise ConfigError("--doc 指向的 %s 不存在" % raw)
        sections.append((raw, path.read_text(encoding="utf-8")))
        formats[raw] = mdscan.format_of(raw)
    rules, rules_path = load_style_rules(root, args.rules)
    cfg = Config(root=root)
    result = analyze(cfg, sections, rules, rules_path=rules_path,
                     report_unregistered=bool(args.report_unregistered),
                     report_abbrev=bool(args.report_abbrev),
                     formats=formats)
    code = result.exit_code

    if args.prompt and not args.json:
        print(build_prompt(result))
        return code

    human = render_human(result, root)
    human += "\n文档模式：%d 个文件（%s）" % (
        len(sections), "、".join(formats.get(p, "text") for p in paths))
    payload = _payload("style", _severity_of(code), code,
                       metrics=result.metrics,
                       thresholds=dict(result.thresholds),
                       findings=[f.as_dict() for f in result.findings],
                       info=[f.as_dict() for f in getattr(result, "info", [])],
                       advisories=[f.as_dict()
                                   for f in getattr(result, "advisories", [])],
                       paragraphs=[p.as_dict() for p in result.paragraphs],
                       fired=result.fired,
                       summary=result.summary,
                       stage_assessment=dict(result.stage_assessment),
                       metric_details=dict(result.metric_details),
                       disclaimer=DISCLAIMER,
                       rules=rules_path,
                       mode="doc",
                       documents=[{"file": raw, "format": formats.get(raw, "text")}
                                  for raw in paths])
    if args.prompt:
        payload["prompt"] = build_prompt(result)
    payload["config"] = _config_block(cfg)
    payload["config_warnings"] = list(cfg.warnings)
    _emit(payload, human, args.json)
    return code


def cmd_style(args) -> int:
    doc_paths = [p for group in (args.doc or []) for p in group]
    if doc_paths:
        return _cmd_style_doc(args, doc_paths)
    cfg = load_config(Path(args.project or "."))
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
                     report_unregistered=bool(args.report_unregistered),
                     report_abbrev=bool(args.report_abbrev))
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
                       advisories=[f.as_dict()
                                   for f in getattr(result, "advisories", [])],
                       paragraphs=[p.as_dict() for p in result.paragraphs],
                       fired=result.fired,
                       summary=result.summary,
                       stage_assessment=dict(result.stage_assessment),
                       metric_details=dict(result.metric_details),
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
    """四种模式：比对 / 纯存快照 / 先判闭合再存快照 / 快照恢复。"""
    if args.restore:
        return _tide_restore(args)
    if args.into:
        raise ConfigError("--into 只能与 --restore 一起使用")
    # 批 109：--before/--after/--snapshot 三者同给＝先判闭合，闭合才存快照。
    if args.before and args.after and args.snapshot:
        return _tide_compare_and_snapshot(args)
    if args.snapshot or (args.after and not args.before):
        return _tide_snapshot(args)
    return _tide_compare(args)


def _tide_payload(result, mode: str = "compare") -> dict:
    payload = _payload("tide", "ok" if result.exit_code == EXIT_OK
                       else "violation", result.exit_code,
                       mode=mode, tx=result.tx,
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
    return payload


def _tide_compare(args) -> int:
    if not args.before or not args.after:
        raise ConfigError("比对模式需要 --before 与 --after")
    result = run_tide(Path(args.before), Path(args.after),
                      Path(args.out) if args.out else None,
                      ignore=args.ignore,
                      default_ignore=not args.no_default_ignore)
    code = result.exit_code
    _emit(_tide_payload(result), render_tide(result), args.json)
    return code


def _tide_compare_and_snapshot(args) -> int:
    """批 109：先判闭合，闭合才存快照；不闭合整次失败，不落快照。"""
    if not args.before or not args.after:
        raise ConfigError("闭合＋快照模式需要 --before 与 --after")
    result = run_tide(Path(args.before), Path(args.after),
                      Path(args.out) if args.out else None,
                      ignore=args.ignore,
                      default_ignore=not args.no_default_ignore)
    if not result.closed:
        payload = _tide_payload(result, mode="compare-snapshot")
        payload["snapshot_saved"] = False
        payload["snapshot"] = None
        human = (render_tide(result)
                 + "\n未保存快照：闭合判定未通过（不落快照、不落账）。")
        _emit(payload, human, args.json)
        return EXIT_RED

    snap = save_snapshot(Path(args.after),
                         Path(args.snapshot) if args.snapshot else None,
                         ignore=args.ignore,
                         default_ignore=not args.no_default_ignore)
    payload = _tide_payload(result, mode="compare-snapshot")
    payload.update({
        "snapshot_saved": True,
        "snapshot_id": snap.snapshot_id,
        "snapshot": snap.short,
        "files": snap.files,
        "bytes": snap.bytes,
        "blobs_new": snap.blobs_new,
        "blobs_shared": snap.blobs_shared,
        "store": str(snap.store),
        "manifest": str(snap.manifest_path),
    })
    human = render_tide(result) + "\n" + render_tide_snapshot(snap)
    _emit(payload, human, args.json)
    return EXIT_OK


def _tide_snapshot(args) -> int:
    if not args.after:
        raise ConfigError("快照保存需要 --after（要快照的目录）")
    result = save_snapshot(Path(args.after),
                           Path(args.snapshot) if args.snapshot else None,
                           ignore=args.ignore,
                           default_ignore=not args.no_default_ignore)
    payload = _payload("tide", "ok", EXIT_OK, mode="snapshot",
                       snapshot_id=result.snapshot_id,
                       snapshot=result.short, ok=True,
                       files=result.files, bytes=result.bytes,
                       blobs_new=result.blobs_new,
                       blobs_shared=result.blobs_shared,
                       store=str(result.store),
                       manifest=str(result.manifest_path),
                       ignored=list(result.ignored),
                       ignore=list(result.ignore),
                       closure_checked=False,
                       notice="未做闭合判定（未给 --before；纯存快照）")
    human = render_tide_snapshot(result)
    if not args.before:
        human += "\n说明：未给 --before，本趟是纯存快照，未做闭合判定。"
    _emit(payload, human, args.json)
    return EXIT_OK


def _tide_restore(args) -> int:
    if args.before or args.after:
        raise ConfigError("--restore 不能与 --before/--after 同时使用")
    if not args.into:
        raise ConfigError("快照恢复需要 --into（还原到哪个目录）")
    result = restore_snapshot(
        Path(args.snapshot) if args.snapshot else Path(DEFAULT_SNAPSHOT_ROOT),
        args.restore, Path(args.into))
    code = result.exit_code
    payload = _payload("tide", "ok" if code == EXIT_OK else "violation", code,
                       mode="restore", snapshot_id=result.snapshot_id,
                       snapshot=result.short, ok=result.ok,
                       files=result.files, bytes=result.bytes,
                       verified=result.verified, written=result.written,
                       reasons=list(result.reasons),
                       into=str(result.into), store=str(result.store))
    _emit(payload, render_tide_restore(result), args.json)
    return code


def cmd_review(args) -> int:
    """改写验收：一次跑保护面、复检、闭合三项，合成一个 final verdict。"""
    result = run_review(
        Path(args.before), Path(args.after),
        allow_new=args.allow_new,
        snapshot=Path(args.snapshot) if args.snapshot else None)
    code = result.exit_code
    data = _payload("review", _severity_of(code), code, **review_payload(result))
    _emit(data, render_review(result), args.json)
    return code


def _write_stdout(text: str) -> int:
    """写 stdout；下游提前关闭（如 ``| head``）时安静退出，不报内部错误。"""
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    return EXIT_OK


def cmd_polish(args) -> int:
    """润色工单：手册或工作单。不是闸门，成功永远 EXIT_OK。"""
    if args.print_playbook:
        return _write_stdout(playbook_text())
    plan = build_plan(Path(args.plan))
    data = _payload("polish", "ok", EXIT_OK, **plan_payload(plan))
    _emit(data, render_plan(plan), args.json)
    return EXIT_OK


def cmd_prescribe(args) -> int:
    """处方层：只输出处方原文或清单；成功永远 EXIT_OK，不产生 findings。"""
    prescriptions = load_prescriptions()
    names = list(getattr(args, "names", None) or [])
    for_code = (getattr(args, "for_code", None) or "").strip().upper()

    if args.list and (names or for_code):
        raise ConfigError("--list 不能与处方名或 --for 同时使用")
    if for_code and names:
        raise ConfigError("--for 不能与处方名同时使用")

    if args.list:
        ordered = sorted(prescriptions.values(),
                         key=lambda p: (p.level_number, p.name))
        payload = _payload(
            "prescribe", "ok", EXIT_OK,
            prescriptions=[p.as_dict(include_text=False) for p in ordered],
            priority=priority_payload(),
            conflicts=[], suppressed={}, note=NOTE)
        lines = ["== factscribe prescribe ==",
                 "处方：%d 条（只给改法；不参与判据、不产生分数）"
                 % len(ordered), ""]
        for p in ordered:
            lines.append("%-22s 优先 %d %-8s %s"
                         % (p.name, p.level_number, p.level_label,
                            "、".join(p.target_codes)))
        _emit(payload, "\n".join(lines), args.json)
        return EXIT_OK

    if for_code:
        matched = prescriptions_for(for_code, prescriptions)
        resolution = resolve_conflicts([p.name for p in matched],
                                       prescriptions)
        payload = _payload(
            "prescribe", "ok", EXIT_OK,
            for_code=for_code,
            prescriptions=[p.as_dict() for p in matched],
            conflicts=resolution["conflicts"],
            suppressed=resolution["suppressed"], note=NOTE)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif not matched:
            print("没有处方治 %s（处方层不处理该码）" % for_code)
        else:
            print(render_bundle([p.name for p in matched], prescriptions))
        return EXIT_OK

    if not names:
        raise ConfigError(
            "prescribe 需要处方名、--list 或 --for <错误码>"
            "（例：factscribe prescribe heading-shorten）")
    unknown = [n for n in names if n not in prescriptions]
    if unknown:
        raise ConfigError(
            "没有处方 %s；可用：%s"
            % ("、".join(repr(n) for n in unknown),
               "、".join(sorted(prescriptions))))

    if len(names) == 1 and not args.json:
        print(prescriptions[names[0]].text.rstrip())
        return EXIT_OK

    resolution = resolve_conflicts(names, prescriptions)
    if args.json:
        payload = _payload(
            "prescribe", "ok", EXIT_OK,
            prescriptions=[prescriptions[n].as_dict()
                           for n in resolution["order"]],
            conflicts=resolution["conflicts"],
            suppressed=resolution["suppressed"], note=NOTE)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_bundle(names, prescriptions))
    return EXIT_OK


def cmd_terms(args) -> int:
    """术语候选抽取 / 人工入表。零 LLM；不自动写词表。"""
    if args.terms_action == "suggest":
        rows = suggest(args.root, min_count=args.min_count,
                       min_sections=args.min_sections,
                       glossary_path=args.glossary)
        text = render_tsv(rows)
        out = Path(args.out) if args.out else None
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
        if args.json:
            print(json.dumps(
                json_payload(rows, args.root, args.min_count,
                             args.min_sections),
                ensure_ascii=False, indent=2))
            return EXIT_OK
        lines = ["== factscribe terms suggest ==",
                 "根：%s" % args.root,
                 "候选：%d 条（min-count=%d，min-sections=%d）"
                 % (len(rows), args.min_count, args.min_sections)]
        if out is not None:
            lines.append("写盘：%s" % out)
        print("\n".join(lines))
        print(text, end="")
        return EXIT_OK

    info = add_from_tsv(args.from_path, args.pick,
                        glossary_path=args.glossary)
    if args.json:
        payload = _payload("terms", "ok", EXIT_OK, **info)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    lines = ["== factscribe terms add ==",
             "词表：%s" % info["glossary"],
             "来源：%s" % info["source"],
             "新增：%d 条%s" % (len(info["added"]),
                              ("（%s）" % "、".join(info["added"]))
                              if info["added"] else ""),
             "跳过：%d 条" % len(info["skipped"])]
    for item in info["skipped"]:
        lines.append("  - %s：%s" % (item["surface"], item["reason"]))
    print("\n".join(lines))
    return EXIT_OK


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"check": cmd_check, "audit": cmd_audit, "matrix": cmd_matrix,
                "build": cmd_build, "preamble": cmd_preamble,
                "verify-pdf": cmd_verify_pdf, "style": cmd_style,
                "protect": cmd_protect, "tide": cmd_tide,
                "review": cmd_review,
                "polish": cmd_polish,
                "prescribe": cmd_prescribe, "terms": cmd_terms,
                "fonts": cmd_fonts}
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
