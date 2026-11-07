# -*- coding: utf-8 -*-
"""源头锚定、check/audit 各类检查、报告模型与错误码。"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .citations import (BibEntry, _URL_OK_TYPES, bib_duplicates, parse_bib,
                        valid_stable_id)
from .config import (Config, ConfigError, _glob_paths, all_tex_files,
                     facts_digest, git_commit, load_toml)
from .constants import (CONFIDENCE_OK, KINDS_OK, SEV_INFO, SEV_RED,
                        SEV_YELLOW, VERSION)
from .facts import (Fact, ExprError, _cycles, _declared_number, eval_expr,
                    literal_tokens, number_key, sha256_file)
from .texrules import (adjacency_hits, arith_hits, display_hits,
                       numeric_macro_hits, pkignore_quant_hits,
                       tabular_regions)
from .texscan import (_balanced, _blank, _extract_numbers,
                      _merge_number_units, scan_tex, sentence_index,
                      sentence_spans)

# --------------------------------------------------------------------------
# 问题单
# --------------------------------------------------------------------------

@dataclass
class Issue:
    code: str
    message: str
    location: str = ""
    token: str = ""
    context: str = ""
    severity: str = SEV_RED
    exit_code: int = 1        # 1=FACT/CONFIG，5=COVERAGE/INTEGRITY，7=STALE，8=工具缺失

    def as_dict(self) -> dict:
        d = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.location:
            d["location"] = self.location
        if self.token:
            d["token"] = self.token
        if self.context:
            d["context"] = self.context
        return d

def _source_rel_ok(src: str) -> str:
    """source 必须是相对路径；返回错误码或空串。"""
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", src):
        return "BAD_SOURCE_PATH"
    p = Path(src)
    if p.is_absolute() or ".." in p.parts:
        return "BAD_SOURCE_PATH"
    return ""


def _display_issues(facts: list[Fact]) -> list[Issue]:
    """R-04：display 只能追加与 value 严格等价的写法（内部 B2/2-B2）。"""
    out: list[Issue] = []
    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        for code, detail in display_hits(f):
            out.append(Issue(code, "fact %r：%s" % (f.id, detail),
                             location=loc, token=f.id))
    return out


def _mask_fact_bodies(tex: str) -> str:
    """V3：`\\fact{ID}{value}` 的 value 是**被绑定**的显示形。

    `\\the\\value{counter}` 这类计数渲染出现在绑定体内时，数字由 fact 授权、
    再由 PDF 闸门核对；不该在这里重复判 ARITH_IN_BODY。空白保留换行以
    维持行号。
    """
    out = list(tex)
    i = 0
    n = len(tex)
    while i < n:
        if tex.startswith("\\fact", i):
            j = i + 5
            while j < n and tex[j] in " \t\r\n":
                j += 1
            if j < n and tex[j] == "{":
                e1 = _balanced(tex, j, "{", "}")
                k = e1
                while k < n and tex[k] in " \t\r\n":
                    k += 1
                if k < n and tex[k] == "{":
                    e2 = _balanced(tex, k, "{", "}")
                    _blank(out, i, e2)
                    i = e2
                    continue
        i += 1
    return "".join(out)


def _source_rule_issues(cfg: Config, sections) -> list[Issue]:
    """R-01A / R-05 / R-07 的闭包级判据（对每个扫描到的文本文件跑）。"""
    out: list[Issue] = []
    # V3：计数器**声明/赋值**（\newcounter/\setcounter…）是证据源定义，不是
    # 渲染出的数字；真正把计数器渲染成数字的 \the/\value/\numexpr 仍判红，
    # 绑定体内的渲染由 _mask_fact_bodies 交给 PDF 闸门核对。
    counter_setup = {"newcounter", "setcounter", "addtocounter",
                     "stepcounter", "refstepcounter"} if cfg.is_v3 else set()
    for rel, text in sections:
        for name, line in arith_hits(_mask_fact_bodies(text) if cfg.is_v3 else text):
            if name in counter_setup:
                continue
            out.append(Issue(
                "ARITH_IN_BODY",
                "算术/计数器命令 \\%s 会产生账上没有的数字——数值不可寻址（R-01A-A）"
                % name, location="%s:%s" % (rel, line), token="\\" + name))
        for name, line, digit in numeric_macro_hits(text, cfg.numeric_macro_allow):
            out.append(Issue(
                "NUMERIC_IN_MACRO",
                "宏 \\%s 的定义体携带数字（%r）——宏可以携带 fact id，不可以携带数字"
                "（R-01A-B；确属布局宏请进 project.numeric_macro_allow 人签登记）"
                % (name, digit), location="%s:%s" % (rel, line), token="\\" + name))
        for line, arg, hits in pkignore_quant_hits(scan_tex(text).annotation_args):
            out.append(Issue(
                "PKIGNORE_QUANT",
                "\\pkignore 参数里出现定量（%s）——豁免宏不得用来抹掉结论句：%r"
                % (hits, arg), location="%s:%s" % (rel, line), token=hits))
    return out


def _aggregate_exit(red: list[Issue], yellow: list[Issue], strict: bool = False,
                    integrity_first: bool = False) -> int:
    if red:
        codes = {i.exit_code for i in red}
        if integrity_first and 5 in codes:
            return 5
        for code in (8, 1, 5, 7):
            if code in codes:
                return code
        return 1
    if yellow:
        return 1 if strict else 3
    return 0


def _v3_source_issues(cfg: Config, facts: list[Fact],
                      sections: list[tuple[str, str]]) -> list[Issue]:
    """V3 专属的源层判据：key 信任根、数值宏形状、断言/审批（S-01/S-03/S-08）。"""
    from .v3 import (_load_json, approval_issues, approval_report_issues,
                     assertion_issues, bu_index, key_trust_issues,
                     numeric_macro_issues)
    from .livetext import live_text_issues

    out: list[Issue] = []
    out += key_trust_issues(cfg)
    out += numeric_macro_issues(cfg)
    out += assertion_issues(facts, bu_index(sections))
    out += live_text_issues(cfg, facts, sections)
    # display 也是审批对象的一部分（S-03 的 approve_target 含 display）：
    # 追加一个与 value 不等价的显示形，就是断言漂移。
    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        for code, detail in display_hits(f):
            if code == "DISPLAY_INCONSISTENT":
                out.append(Issue(
                    "ASSERTION_DRIFT",
                    "fact %r 的批准显示形与 value 不等价：%s（S-03）" % (f.id, detail),
                    location=loc, token=f.id))
    rpath = cfg.root / "audit" / "report.json"
    report = _load_json(rpath) if rpath.is_file() else None
    out += approval_issues(cfg, facts, report)
    out += approval_report_issues(cfg)
    return out


def _fact_form_keys(value: str) -> list[str]:
    """把 value/display 这种字面写法展开成 PDF 侧会抽到的 key（去重）。"""
    keys: list[str] = []
    for raw, suffix, pct in literal_tokens(value):
        keys.append(number_key(raw, suffix or None, pct))
        if pct:
            keys.append(number_key(raw, suffix or None, False))
    return sorted(set(keys))


def _v3_whitelist(bib_entries, used_keys: dict) -> list[dict]:
    """P-05 W2：被引用文献的字段数字是白名单（每 entry 同一值最多 3 次）。

    W1（页码）/W3（引用标签）/W4（结构号）由 pdfgate 的上下文掩码处理，
    不在这里重复计数——避免同一数字被「掩掉 + 白名单」双重放行。
    """
    declared: dict[str, dict] = {}
    for e in bib_entries:
        if used_keys and e.key not in used_keys:
            continue
        for field in ("year", "volume", "number", "pages", "doi", "eprint"):
            text = str(e.fields.get(field) or "")
            for raw, suffix, pct in literal_tokens(text):
                key = number_key(raw, suffix or None, pct)
                entry = declared.setdefault(key, {"key": key, "count": 0,
                                                  "source": "%s#%s.%s"
                                                            % (e.file, e.key, field)})
                if entry["count"] < 3:
                    entry["count"] += 1
    return list(declared.values())


def _drift_issues(cfg: Config, fact_id: str, unit: dict, rel: str) -> list[Issue]:
    """V3：正文断言的数字与账上的值不符 ＝ 断言漂移（S-03）。

    v1 里同一件事叫 BOUND_MISMATCH；V3 的审批对象是「断言」，值与句子
    一起被签，所以同一处同时记一条 ASSERTION_DRIFT，供盲测/审计分诊。
    """
    if not cfg.is_v3:
        return []
    return [Issue(
        "ASSERTION_DRIFT",
        "fact %r 在正文断言的数字 %s 不在被签的 value/display 里——"
        "句子与账的断言漂移（S-03）" % (fact_id, unit["token"]),
        location="%s:%s:%s" % (rel, unit["line"], unit["col"]),
        token=unit["token"], context=unit["text"])]


def source_base(cfg: Config) -> Path:
    """source 的解析根（v1.1）。

    - 配了 project.source_root：source 相对它解析（论文项目指到工作区根，
      原始产物留在 experiments/ 原地，不必为过闸复制）；
    - 没配：兼容 v1，source 只许在项目内 results/ 下。
    """
    raw = (cfg.source_root or "").strip()
    if not raw:
        return cfg.root
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (cfg.root / p)


def source_path(cfg: Config, src: str) -> Path:
    return source_base(cfg) / src


def _source_text_keys(text: str) -> set[str]:
    keys = set()
    for raw, suffix, pct in literal_tokens(text):
        keys.add(number_key(raw, suffix or None, pct))
    return keys


def verify_sources(cfg: Config, facts: list[Fact]) -> tuple[list[Issue], list[Issue]]:
    red: list[Issue] = []
    yellow: list[Issue] = []
    root = cfg.root
    # v1 的原始产物在 results/；V3 证据模型在 runs/（SPEC-V3.0 证据根）。
    results_dir = (root / cfg.source_dir)
    base = source_base(cfg)
    texts: dict[str, str] = {}
    actual: dict[str, str] = {}

    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        src = f.source.strip()
        if not src:
            red.append(Issue("MISSING_SOURCE_FIELD", "fact %r 缺 source 字段" % f.id,
                             location=loc, token=f.id))
            continue
        bad = _source_rel_ok(src)
        if bad:
            red.append(Issue(bad, "fact %r 的 source 必须是相对路径（不许 URL/绝对路径/%s）：%s"
                             % (f.id, ".. 越界" if ".." in Path(src).parts else "绝对路径", src),
                             location=loc, token=f.id))
            continue
        full = base / src
        try:
            full.resolve().relative_to(base.resolve())
        except ValueError:
            red.append(Issue(
                "SOURCE_OUTSIDE_SOURCE_ROOT",
                "fact %r 的 source 越出 source_root（%s）：%s" % (f.id, base, src),
                location=loc, token=f.id))
            continue
        if not cfg.source_root.strip():
            # 未配 source_root：沿用口径，source 必须在项目 results/（v1）
            # 或 runs/（V3）下
            try:
                full.resolve().relative_to(results_dir.resolve())
            except ValueError:
                red.append(Issue(
                    "SOURCE_OUTSIDE_RESULTS" if not cfg.is_v3 else "SOURCE_OUTSIDE_RUNS",
                    "fact %r 的 source 不在 %s/ 下（%s）——原始产物必须由人签清单/"
                    "审批目标锁死；跨目录请配 source_root"
                    % (f.id, cfg.source_dir, src),
                    location=loc, token=f.id))
                continue
        if not full.is_file():
            red.append(Issue("MISSING_SOURCE", "fact %r 的 source 不存在或不是普通文件：%s"
                             % (f.id, src), location=loc, token=f.id))
            continue
        try:
            digest = sha256_file(full)
            texts[src] = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            red.append(Issue("UNREADABLE_SOURCE", "fact %r 的 source 读不了：%s（%s）"
                             % (f.id, src, exc), location=loc, token=f.id))
            continue
        actual[src] = digest
        if not f.source_sha256:
            # V3 的内容锚在审批目标的 source_sha256 上（S-03）；v1 仍然要求
            # fact 本件钉住 sha256。
            if not cfg.is_v3:
                red.append(Issue(
                    "MISSING_SOURCE_SHA256",
                    "fact %r 缺 source_sha256——没有内容锚定，账就无法证明「从签过那刻起没被改」"
                    % f.id, location=loc, token=f.id))
        elif f.source_sha256.removeprefix("sha256:").strip() != digest:
            red.append(Issue(
                "SOURCE_SHA256_MISMATCH",
                "fact %r 的 source_sha256 与现算不符（声明 %s…，实际 %s…）——产物被改过"
                % (f.id, f.source_sha256[:12], digest[:12]), location=loc, token=f.id))
            if cfg.is_v3:
                # S-03：source_sha256 是 approve_target 的字段。它比现算值旧，
                # 就等于「被签的审批对象已经不是磁盘上这一份」。
                red.append(Issue(
                    "APPROVAL_STALE",
                    "fact %r 的 source_sha256 与磁盘现算值不符——审批对象（S-03 的 "
                    "approve_target）已过期，必须重签" % f.id,
                    location=loc, token=f.id))

        # value 回查：非派生 claim 的数字必须字面出现在 source 里（B6 的内容锚）
        if not f.is_derived and f.kind == "claim" and src in texts:
            src_keys = _source_text_keys(texts[src])
            missing = []
            for raw, suffix, pct in literal_tokens(f.value):
                keys = [number_key(raw, suffix or None, pct)]
                # V3 的 runs/ 摘要常把百分比存成整数（40 / 0.4 都是 40%），
                # 源层回查接受这两种写法；值域判定仍用严格 canon。
                if cfg.is_v3 and pct:
                    keys.append(number_key(raw, suffix or None, False))
                if not any(k in src_keys for k in keys):
                    missing.append(raw + suffix + ("%" if pct else ""))
            if missing:
                yellow.append(Issue(
                    "VALUE_NOT_IN_SOURCE",
                    "fact %r 的 value 数字 %s 没有出现在 source 里（内容回查失败）"
                    % (f.id, "、".join(missing)), location=loc, token=f.id,
                    severity=SEV_YELLOW))

    if cfg.is_v3:
        # V3 没有 results/MANIFEST.toml：证据是项目外审批目标 + runs/ 产物，
        # 由 v3.approval_issues / key_trust_issues 单独判。
        return red, yellow

    # ---- 人签清单 ----
    mpath = cfg.root / cfg.manifest
    if not mpath.is_file():
        yellow.append(Issue(
            "NO_MANIFEST",
            "缺人签清单 %s：工具只能证明「账与正文自洽」，不能证明 results/ 当初没被编"
            % cfg.manifest, location=cfg.manifest, severity=SEV_YELLOW))
        return red, yellow
    try:
        data = load_toml(mpath)
    except ConfigError as exc:
        red.append(Issue("MANIFEST_INVALID", str(exc), location=cfg.manifest))
        return red, yellow
    meta = data.get("manifest")
    if not isinstance(meta, dict) or not str(meta.get("signed_by") or "").strip():
        red.append(Issue(
            "MANIFEST_UNSIGNED",
            "清单 %s 没有 signed_by——没人签的清单不算锚" % cfg.manifest,
            location=cfg.manifest))
    if isinstance(meta, dict) and not str(meta.get("signed_at") or "").strip():
        yellow.append(Issue(
            "MANIFEST_NO_TIMESTAMP", "清单 %s 缺 signed_at（签的时间点）" % cfg.manifest,
            location=cfg.manifest, severity=SEV_YELLOW))
    files = data.get("files")
    if not isinstance(files, dict):
        files = {}
        yellow.append(Issue("MANIFEST_NO_FILES", "清单 %s 没有 [files] 段" % cfg.manifest,
                            location=cfg.manifest, severity=SEV_YELLOW))
    signed = {str(k): str(v).strip().lower() for k, v in files.items()}

    for f in facts:
        src = f.source.strip()
        if src not in actual:
            continue
        if src not in signed:
            red.append(Issue(
                "SOURCE_NOT_SIGNED",
                "fact %r 的 source %s 不在人签清单里——没人确认过它" % (f.id, src),
                location="%s:%s" % (f.file, f.line or "?"), token=f.id))
        elif signed[src] != actual[src]:
            red.append(Issue(
                "MANIFEST_HASH_MISMATCH",
                "清单里 %s 的 sha256 与文件现值不符——签过之后被改过" % src,
                location=cfg.manifest, token=f.id))

    if results_dir.is_dir():
        for p in sorted(results_dir.rglob("*")):
            if not p.is_file() or p.resolve() == mpath.resolve():
                continue
            rel = p.relative_to(root).as_posix()
            if rel not in signed:
                yellow.append(Issue(
                    "UNSIGNED_RESULT",
                    "results/ 下有未签文件 %s——它没有被任何清单锁住" % rel,
                    location=rel, severity=SEV_YELLOW))
    return red, yellow

# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

def run_check(cfg: Config, facts: list[Fact]):
    issues: list[Issue] = []
    warnings: list[Issue] = []
    conflicts: list[dict] = []

    if not facts:
        raise ConfigError("facts 为空（%s 没匹配到任何 fact）——空账不算通过" % cfg.facts_glob)

    red_src, yellow_src = verify_sources(cfg, facts)
    issues += red_src
    warnings += yellow_src
    issues += _display_issues(facts)

    seen: dict[str, Fact] = {}
    superseded = {s.strip().casefold() for f in facts for s in f.supersedes}
    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        key = f.id_key
        if key in seen:
            issues.append(Issue(
                "DUPLICATE_ID", "fact id %r 重复（%s 与 %s；id 按大小写不敏感判重）"
                % (f.id, seen[key].file, f.file), location=loc, token=f.id))
        else:
            seen[key] = f
        if re.search(r"\s", f.id) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", f.id):
            issues.append(Issue(
                "BAD_ID_FORMAT",
                "fact id %r 不合法：只允许字母开头，后接字母/数字/_ . : -（不许空白）"
                % f.id, location=loc, token=f.id))
        if f.confidence not in CONFIDENCE_OK:
            issues.append(Issue(
                "BAD_CONFIDENCE", "fact %r 的 confidence=%r 不合法（只允许 high/med/low）"
                % (f.id, f.confidence), location=loc, token=f.id))
        if f.kind not in KINDS_OK:
            issues.append(Issue(
                "BAD_KIND", "fact %r 的 kind=%r 不合法（只允许 claim/config）"
                % (f.id, f.kind), location=loc, token=f.id))
        if not f.value:
            issues.append(Issue("EMPTY_VALUE", "fact %r 的 value 为空（账上没有数）" % f.id,
                                location=loc, token=f.id))

    known = {f.id_key: f for f in facts}
    for f in facts:
        loc = "%s:%s" % (f.file, f.line or "?")
        for dep in f.derived_from:
            if dep.strip().casefold() not in known:
                issues.append(Issue(
                    "BAD_DERIVED_FROM", "fact %r 的 derived_from 指向不存在的 id %r" % (f.id, dep),
                    location=loc, token=dep))
        for sup in f.supersedes:
            if sup.strip().casefold() not in known:
                issues.append(Issue(
                    "BAD_SUPERSEDES", "fact %r 的 supersedes 指向不存在的 id %r" % (f.id, sup),
                    location=loc, token=sup))
        for dep in f.derived_from:
            if dep.strip().casefold() in superseded:
                issues.append(Issue(
                    "SUPERSEDED_PARENT",
                    "fact %r 从已被 supersedes 的 %r 推算——父值已作废" % (f.id, dep),
                    location=loc, token=dep))

        # derived 值必须写可求值算式
        if f.derived_from and not f.expr:
            issues.append(Issue(
                "MISSING_EXPR",
                "fact %r 是推算值，但没写 expr——只写 derived_from 不算可复核" % f.id,
                location=loc, token=f.id))
        if f.expr:
            try:
                got = eval_expr(f.expr, known)
                want = _declared_number(f.value)
                if abs(got - want) > 1e-9 * max(1.0, abs(want)):
                    issues.append(Issue(
                        "EXPR_MISMATCH",
                        "fact %r 的 expr=%r 算出 %s，与 value=%r 不符"
                        % (f.id, f.expr, ("%.10g" % got), f.value),
                        location=loc, token=f.id))
            except ExprError as exc:
                issues.append(Issue("EXPR_INVALID", "fact %r 的 expr 不可用：%s" % (f.id, exc),
                                    location=loc, token=f.id))
        elif not f.derived_from and f.is_derived:
            # is_derived 只看 expr/derived_from，这里不会发生；保底留白
            pass

    for cyc in _cycles(facts):
        issues.append(Issue(
            "DERIVED_CYCLE", "推算链成环：%s" % " -> ".join(cyc),
            location="facts/", token=",".join(cyc)))

    # 冲突：结构化 (metric, scope) 优先，否则 claim 全文；用 supersedes 封冲突
    groups: dict[tuple, list[Fact]] = {}
    for f in facts:
        if f.metric.strip():
            key = ("metric", f.metric.strip(), f.scope.strip())
        else:
            key = ("claim", f.claim.strip(), "")
        groups.setdefault(key, []).append(f)
    for _key, group in groups.items():
        label = group[0].metric.strip() or group[0].claim.strip()
        if not label or len(group) < 2:
            continue
        if len({f.value.strip() for f in group}) < 2:
            continue
        live = [f for f in group if f.id_key not in superseded]
        if len({f.value.strip() for f in live}) < 2:
            continue
        conflicts.append({
            "claim": label,
            "ids": [f.id for f in live],
            "values": [f.value for f in live],
            "message": "同一 claim/metric 有不同 value 且没有被 supersedes：%s"
                       % " / ".join("%s=%s" % (f.id, f.value) for f in live),
        })
        warnings.append(Issue(
            "LEDGER_CONFLICT",
            "账本自相矛盾（黄）：" + conflicts[-1]["message"],
            location="%s:%s" % (live[0].file, live[0].line or "?"),
            token=",".join(f.id for f in live), severity=SEV_YELLOW))

    # 账本卫生：同一 value 挂在多条不同 claim 上 -> 疑似「数字白名单」（红队 C6）
    by_value: dict[str, list[Fact]] = {}
    for f in facts:
        if f.kind == "claim" and f.value.strip() and f.id_key not in superseded:
            by_value.setdefault(f.value.strip(), []).append(f)
    for value, group in by_value.items():
        if len(group) > 1 and len({f.claim.strip() for f in group}) > 1:
            warnings.append(Issue(
                "DUPLICATE_VALUE",
                "同一个 value=%r 挂在 %s 上——像在拿一份数字白名单充事实账"
                % (value, "、".join(f.id for f in group)),
                location="%s:%s" % (group[0].file, group[0].line or "?"),
                token=",".join(f.id for f in group), severity=SEV_YELLOW))

    summary = {
        "facts": len(facts),
        "ids": len(known),
        "sources_ok": sum(1 for f in facts if f.source and source_path(cfg, f.source).is_file()),
        "sha_pinned": sum(1 for f in facts if f.source_sha256),
        "conflicts": len(conflicts),
        "red": len(issues),
        "yellow": len(warnings),
        "confidence": {
            "high": sum(1 for f in facts if f.confidence == "high"),
            "med": sum(1 for f in facts if f.confidence == "med"),
            "low": sum(1 for f in facts if f.confidence == "low"),
        },
        "derived": sum(1 for f in facts if f.derived_from),
        "attestation": {"facts_sha256": facts_digest(cfg),
                        "git_commit": git_commit(cfg.root)},
    }
    return issues, warnings, conflicts, summary

def _resolve_arxiv(arxiv_id: str) -> tuple[str, str]:
    """返回 (status, detail)：verified / not_found / unverified。"""
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"id_list": arxiv_id, "max_results": "1"})
    req = urllib.request.Request(url, headers={"User-Agent": "factscribe/%s" % VERSION})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "not_found", "arXiv API 返回 HTTP 404"
        return "unverified", "联网核验失败（%s）" % exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return "unverified", "联网核验失败（%s）" % exc
    if status != 200:
        return "unverified", "arXiv API 返回 HTTP %s" % status
    if re.search(r"<entry\b", body):
        return "verified", "arXiv API 命中"
    if "<opensearch:totalResults>0<" in body or "totalResults>0<" in body:
        return "not_found", "arXiv API 明确返回 0 条"
    return "unverified", "arXiv API 响应无法判定"


def _resolve_doi(doi: str) -> tuple[str, str]:
    url = "https://doi.org/api/handles/" + urllib.parse.quote(doi, safe="/")
    req = urllib.request.Request(url, headers={"User-Agent": "factscribe/%s" % VERSION})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "not_found", "doi.org 返回 HTTP 404（该 DOI 不存在）"
        return "unverified", "联网核验失败（%s）" % exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return "unverified", "联网核验失败（%s）" % exc
    if '"responseCode":1' in body.replace(" ", "") or '"responseCode": 1' in body:
        return "verified", "doi.org handle 命中"
    if '"responseCode":100' in body.replace(" ", "") or '"responseCode": 100' in body:
        return "not_found", "doi.org 明确返回不存在"
    return "unverified", "doi.org 响应无法判定"


def run_audit(cfg: Config, facts: list[Fact], sections: list[tuple[str, str]],
              resolve: bool = False):
    if not facts:
        raise ConfigError("facts 为空（%s 没匹配到任何 fact）——空账不算通过" % cfg.facts_glob)
    if not sections:
        raise ConfigError("sections 为空（%s 没匹配到任何 .tex）——没正文不算通过"
                          % cfg.sections_glob)

    red: list[Issue] = []
    yellow: list[Issue] = []
    hints: list[Issue] = []

    red_src, yellow_src = verify_sources(cfg, facts)
    red += red_src
    yellow += yellow_src

    scanned = {rel: scan_tex(text) for rel, text in sections}

    # ---- bib 文件集合：config + 正文声明的多 bib（红队 C8-B）----
    bib_paths: list[Path] = []
    cfg_bib = cfg.root / cfg.bib
    if not cfg_bib.is_file():
        raise ConfigError("找不到参考文献 %s——引用对账无从做起" % cfg_bib)
    bib_paths.append(cfg_bib)
    for rel, scan in scanned.items():
        for decl in scan.bib_files:
            p = (cfg.root / decl)
            if not p.is_file():
                red.append(Issue(
                    "BIB_FILE_MISSING", "正文声明的参考文献 %s 不存在" % decl,
                    location=rel, token=decl))
                continue
            if p.resolve() not in {q.resolve() for q in bib_paths}:
                bib_paths.append(p)
    bib_entries: list[BibEntry] = []
    for p in bib_paths:
        try:
            bib_entries += parse_bib(p, cfg.root)
        except ConfigError:
            raise
    bib_by_key: dict[str, BibEntry] = {}
    for e in bib_entries:
        bib_by_key.setdefault(e.key, e)
    dup_keys, dup_ids = bib_duplicates(bib_entries)
    for k in dup_keys:
        e = bib_by_key[k]
        red.append(Issue("DUPLICATE_BIB_KEY", "bib 里 key %r 定义了不止一次" % k,
                         location="%s:%s" % (e.file, e.line), token=k))
    for ident, ks in dup_ids:
        yellow.append(Issue(
            "DUPLICATE_STABLE_ID", "%s 挂在多个 key 上：%s" % (ident, "、".join(ks)),
            location="%s:%s" % (bib_by_key[ks[0]].file, bib_by_key[ks[0]].line),
            token=",".join(ks), severity=SEV_YELLOW))

    fact_by_id = {f.id_key: f for f in facts}
    # 全局值域只收 claim 事实：config 事实不能当「数字白名单」用（红队 C3/C6）
    key_to_facts: dict[str, list[str]] = {}
    for f in facts:
        if f.kind != "claim":
            continue
        for k in f.value_keys:
            key_to_facts.setdefault(k, []).append(f.id)

    numbers_total = 0
    matched = 0        # 旧口径：回得到账（含未绑定）
    bound = 0          # 内联绑定且对得上
    unbound_yellow = 0
    unmatched = 0
    annotations_total = 0
    annotation_sites: list[str] = []
    usage: dict[str, list[str]] = {f.id: [] for f in facts}
    marker_count: dict[str, int] = {f.id: 0 for f in facts}
    used_keys: dict[str, int] = {}
    unresolved: list[dict] = []
    seen_figures: set[str] = set()
    ledger: list[dict] = []          # P-04 的账（V3 用来对 PDF 多重集）

    def _ledger_add(rel: str, fid: str, unit: dict) -> None:
        keys: list[str] = []
        for tok in unit["tokens"]:
            keys.append(tok["key"])
            if tok["pct"]:
                keys.append(number_key(tok["raw"], tok["suffix"] or None, False))
        ledger.append({"fact_id": fid, "raw": unit["token"],
                       "keys": sorted(set(keys)), "file": rel, "page": 1,
                       "line": unit["line"], "col": unit["col"]})

    red += _display_issues(facts)
    red += _source_rule_issues(cfg, sections)
    if cfg.is_v3:
        red += _v3_source_issues(cfg, facts, sections)

    for rel, text in sections:
        scan = scanned[rel]
        nums = _extract_numbers(scan.masked, text)
        units = _merge_number_units(nums, scan.masked)
        numbers_total += len(nums)
        annotations_total += len(scan.annotations)
        annotation_sites += ["%s:%s \\%s" % (rel, line, name)
                             for name, line in scan.annotations]

        for fid, _line in scan.markers:
            f = fact_by_id.get(fid.strip().casefold())
            if f is None:
                red.append(Issue(
                    "UNKNOWN_FACT_MARKER",
                    "正文标记了不存在的 fact %r（账上没有这个 id）" % fid,
                    location="%s:%s" % (rel, _line), token=fid))
            else:
                marker_count[f.id] += 1
                if rel not in usage[f.id]:
                    usage[f.id].append(rel)

        for name, line, col in scan.unknown_cites:
            red.append(Issue(
                "UNKNOWN_CITE_COMMAND",
                "认不出的引用命令 \\%s——引用闸门默认 fail-closed，请改用已知的 cite 家族命令"
                % name, location="%s:%s:%s" % (rel, line, col), token=name))

        # ---- R-01A C：数字不得贴宏 / 不得紧跟闭合组 / 不得被空组拼接 ----
        seen_adj: set[tuple[str, int]] = set()
        for num in nums:
            for code, detail in adjacency_hits(scan.adjacency, num):
                mark = (code, num["start_abs"])
                if mark in seen_adj:
                    continue
                seen_adj.add(mark)
                red.append(Issue(
                    code, "%s（%r）——渲染出的数字必须由连续字面数字构成"
                    % (detail, num["token"]),
                    location="%s:%s:%s" % (rel, num["line"], num["col"]),
                    token=num["token"], context=num["text"]))

        # ---- R-02/R-03：BU 是句子；标记组只闭合自己那一句，token 按出现顺序归属 ----
        spans = sentence_spans(scan.masked)
        groups = scan.marker_groups
        group_sentence = [sentence_index(spans, max(0, g["end"] - 1))
                          for g in groups]
        covered: dict[int, list[dict]] = {i: [] for i in range(len(groups))}
        ungrouped: list[dict] = []
        for unit in units:
            unit["sentence"] = sentence_index(spans, unit["start_abs"])
            owner = None
            for gi, g in enumerate(groups):
                if group_sentence[gi] != unit["sentence"]:
                    continue
                if g.get("next_only"):
                    continue          # 向后绑定，交给下面的 next_only 分配
                if g["end"] > unit["start_abs"]:
                    owner = gi
                    break
            if owner is None:
                ungrouped.append(unit)
            else:
                covered[owner].append(unit)

        # 单参数标记（`\fact{A1}10/16`）绑定**紧随其后**的数字：v1 的
        # `10/16\fact{A1}` 由上面的「闭合句子」规则处理，这里补上 V3 的
        # 前置标记写法。一个 token 只归一个组。
        assigned = {id(u) for group in covered.values() for u in group}
        for gi, g in enumerate(groups):
            if not g.get("next_only") or covered[gi]:
                continue
            for unit in units:
                if id(unit) in assigned:
                    continue
                if unit["sentence"] != group_sentence[gi]:
                    continue
                if unit["start_abs"] >= g["end"]:
                    covered[gi].append(unit)
                    assigned.add(id(unit))
                    break
        ungrouped = [u for u in units if id(u) not in assigned]

        for gi, g in enumerate(groups):
            utokens = covered[gi]
            if not utokens:
                continue
            known_facts = []
            for fid in g["ids"]:
                f = fact_by_id.get(fid.strip().casefold())
                if f is not None:
                    known_facts.append(f)
            if not known_facts:
                continue       # 未知 id 已由 UNKNOWN_FACT_MARKER 判红
            quant_facts = [f for f in known_facts if f.value_keys]
            if not quant_facts:
                for unit in utokens:
                    unmatched += len(unit["tokens"])
                    red.append(Issue(
                        "NONQUANT_BACKS_QUANT",
                        "只有机制陈述（%s）来背数字 %s——非定量 fact 不能授权定量断言"
                        % ("/".join(f.id for f in known_facts), unit["token"]),
                        location="%s:%s:%s" % (rel, unit["line"], unit["col"]),
                        token=unit["token"], context=unit["text"]))
                continue
            allowed: set[str] = set()
            for f in quant_facts:
                allowed |= f.value_keys
            sequential = (len(utokens) == len(quant_facts)
                          and not any(f.co_claim for f in quant_facts))
            if sequential and len(quant_facts) > 1:
                # ① 归属分支：第 k 个 token 归第 k 个 fact（内部 B3 / 2-S1）
                for unit, f in zip(utokens, quant_facts):
                    if unit["canon"] in f.value_keys:
                        bound += len(unit["tokens"])
                        _ledger_add(rel, f.id, unit)
                    else:
                        unmatched += len(unit["tokens"])
                        red.append(Issue(
                            "BINDING_ATTRIBUTION",
                            "组内第 %d 个数字 %s 归 %s，但不在它的 value 里——"
                            "标记组成员按书写顺序一一对应（想真·同值请写 co_claim）"
                            % (utokens.index(unit) + 1, unit["token"], f.id),
                            location="%s:%s:%s" % (rel, unit["line"], unit["col"]),
                            token=unit["token"], context=unit["text"]))
                        red += _drift_issues(cfg, f.id, unit, rel)
            else:
                # ② 并集分支：token 数≠fact 数时整段取并集（R-03）
                for unit in utokens:
                    if all(k in allowed for k in unit["keys"]):
                        bound += len(unit["tokens"])
                        _ledger_add(rel, quant_facts[0].id, unit)
                    else:
                        unmatched += len(unit["tokens"])
                        red.append(Issue(
                            "BOUND_MISMATCH",
                            "该段绑定 %s，但数字 %s 不在其 value 里（内联绑定是硬约束）"
                            % ("/".join(f.id for f in quant_facts), unit["token"]),
                            location="%s:%s:%s" % (rel, unit["line"], unit["col"]),
                            token=unit["token"], context=unit["text"]))
                        red += _drift_issues(cfg, quant_facts[0].id, unit, rel)

        # ---- 未被任何标记组闭合的尾段/远句 ----
        tables = tabular_regions(text)
        for unit in ungrouped:
            in_table = any(s <= unit["start_abs"] < e for s, e in tables)
            keys_known = all(k in key_to_facts for k in unit["keys"])
            if in_table and not keys_known:
                # R-06：表格 cell 里的数字必须能被账回查，否则整表绕开审计
                unmatched += len(unit["tokens"])
                red.append(Issue(
                    "TABLE_UNBOUND",
                    "表格 cell 里的数字 %s 回不到任何 fact.value——表格必须进扫描闭包"
                    "并带 cell→fact 映射（R-06）" % unit["token"],
                    location="%s:%s:%s" % (rel, unit["line"], unit["col"]),
                    token=unit["token"], context=unit["text"], exit_code=5))
                continue
            if keys_known and unit["keys"]:
                _ledger_add(rel, key_to_facts[unit["keys"][0]][0], unit)
            for tok in unit["tokens"]:
                loc = "%s:%s:%s" % (rel, tok["line"], tok["col"])
                if tok["key"] in key_to_facts:
                    unbound_yellow += 1
                    yellow.append(Issue(
                        "UNBOUND_NUMBER",
                        "数字 %s 回得到账（%s），但正文没内联绑定——只算黄，不算已核验"
                        % (tok["token"], "/".join(key_to_facts[tok["key"]])),
                        location=loc, token=tok["token"], context=tok["text"],
                        severity=SEV_YELLOW))
                else:
                    unmatched += 1
                    red.append(Issue(
                        "UNMATCHED_NUMBER", "数字 %s 回不到任何 fact.value" % tok["token"],
                        location=loc, token=tok["token"], context=tok["text"]))
        matched = bound + unbound_yellow

        for key, line, col in scan.cites:
            used_keys[key] = used_keys.get(key, 0) + 1
            entry = bib_by_key.get(key)
            line_text = text.split("\n")[line - 1].strip() if line - 1 < len(text.split("\n")) else ""
            if entry is None:
                red.append(Issue(
                    "MISSING_CITE", "引用了 bib 里不存在的 key %r" % key,
                    location="%s:%s:%s" % (rel, line, col), token=key,
                    context=line_text))
                continue
            name, value = entry.stable_id
            if name is None:
                # V3 的证据模型不把「远端稳定标识」当发布闸：本地审计只要求
                # 引用 key 在 bib 里有条目；缺 DOI/arXiv 记提示，供人工补。
                issue = Issue(
                    "BIB_NO_STABLE_ID",
                    "bib 条目 %r（@%s）没有 arxiv/doi%s（不可远端复核）"
                    % (key, entry.kind, "/url" if entry.kind in _URL_OK_TYPES else ""),
                    location="%s:%s" % (entry.file, entry.line), token=key,
                    severity=SEV_INFO if cfg.is_v3 else SEV_RED)
                if cfg.is_v3:
                    hints.append(issue)
                else:
                    red.append(issue)
                continue
            if not valid_stable_id(name, value):
                red.append(Issue(
                    "BAD_STABLE_ID_FORMAT",
                    "%r 的 %s=%r 格式不合法（不能解析成真实标识）" % (key, name, value),
                    location="%s:%s" % (entry.file, entry.line), token=key))
                continue
            if resolve:
                status, detail = (_resolve_doi(value) if name == "doi"
                                  else _resolve_arxiv(value))
                item = {"key": key, "id_type": name, "id": value,
                        "status": status, "detail": detail}
                unresolved.append(item)
                if status == "not_found":
                    red.append(Issue(
                        "UNRESOLVED_CITE",
                        "引用 %r 的 %s=%s 在远端不存在（%s）" % (key, name, value, detail),
                        location="%s:%s" % (entry.file, entry.line), token=key))
                elif status == "unverified":
                    hints.append(Issue(
                        "CITE_UNVERIFIED",
                        "%r 的 %s=%s 未能联网核验（%s），不判红" % (key, name, value, detail),
                        location="%s:%s" % (entry.file, entry.line), token=key,
                        severity=SEV_YELLOW))
                    yellow.append(hints[-1])

        # 图的数据面：没有随图 CSV 的图，数字不可核（红队 D10）
        for path, line in scan.figures:
            p = (cfg.root / path)
            candidates = [p.with_suffix(".csv") if p.suffix else Path(str(p) + ".csv"),
                          Path(str(p) + ".csv")]
            if any(c.is_file() for c in candidates):
                continue
            if path in seen_figures:
                continue
            seen_figures.add(path)
            yellow.append(Issue(
                "FIGURE_UNVERIFIED",
                "图 %s 没有随图数据（.csv），图里的数字不在本闸门覆盖范围内" % path,
                location="%s:%s" % (rel, line), token=path, severity=SEV_YELLOW))

    # 未进 bib 可复核字段的条目（即使没被引用也要说一声）
    for e in bib_entries:
        if e.key not in used_keys and e.stable_id[0] is None:
            hints.append(Issue(
                "BIB_NO_STABLE_ID", "bib 条目 %r 既没有 arxiv 也没有 doi（不可复核）" % e.key,
                location="%s:%s" % (e.file, e.line), token=e.key, severity=SEV_INFO))
        if e.key in used_keys and e.stable_id[0] is not None and not valid_stable_id(*e.stable_id):
            pass  # 已在引用处判红

    for f in facts:
        if marker_count.get(f.id, 0) == 0:
            hints.append(Issue(
                "UNUSED_FACT", "账上有、文里没用：fact %r（%s）" % (f.id, f.claim),
                location="%s:%s" % (f.file, f.line or "?"), token=f.id, severity=SEV_INFO))
    for e in bib_entries:
        if e.key not in used_keys:
            hints.append(Issue(
                "UNUSED_BIB", "bib 里有、文里没引：%r" % e.key,
                location="%s:%s" % (e.file, e.line), token=e.key, severity=SEV_INFO))

    # 覆盖：闭包外还有 .tex 从未被审计 -> 黄（红队 B4/B8）
    all_tex = all_tex_files(cfg)
    unscanned = [p for p in all_tex if p not in scanned]
    for p in unscanned:
        yellow.append(Issue(
            "UNSCANNED_TEX", "%s 不在审计闭包里（未被扫描）" % p,
            location=p, token=p, severity=SEV_YELLOW))

    # 绑定率过低 = 还在靠白名单（红队 C6/C11）
    denom = bound + unbound_yellow + unmatched
    if denom >= 4 and (bound / denom) < 0.5:
        yellow.append(Issue(
            "LOW_BINDING_RATE",
            "内联绑定率 %d/%d 低于 50%%——大部分数字只是「回得到账」，还没回到对的那条账"
            % (bound, denom), location="audit", severity=SEV_YELLOW))

    if resolve and len(unresolved) >= 3:
        bad = sum(1 for u in unresolved if u["status"] == "unverified")
        if bad / len(unresolved) > 0.5:
            yellow.append(Issue(
                "RESOLVE_DEGRADED",
                "联网核验 %d/%d 条都没成功（限流/无网？）——引用存在性本轮等于没验"
                % (bad, len(unresolved)), location="refs.bib", severity=SEV_YELLOW))

    pdf_summary: dict = {"checked": False}
    if cfg.is_v3:
        # 账上每条定量 fact 都必须能在 PDF 里找到（未被正文绑定的 fact 也
        # 要出现：账上的数被删/漏渲染同样是完整性缺口，P-04）。
        bound_ids = {e["fact_id"] for e in ledger}
        for f in facts:
            if f.kind != "claim" or not f.value_keys or f.id in bound_ids:
                continue
            forms = [f.value] + [d.get("text", "") for d in f.display]
            keys: list[str] = []
            for form in forms:
                keys.extend(_fact_form_keys(form))
            keys = sorted(set(keys))
            if keys:
                ledger.append({"fact_id": f.id, "raw": f.value, "keys": keys,
                               "file": f.file, "page": 1,
                               "line": f.line or 1, "col": 1})

        pdf_path = cfg.root / cfg.output
        if pdf_path.is_file():
            from .pdfgate import pdf_key_counts, verify_document
            actual = pdf_key_counts(pdf_path)
            declared = _v3_whitelist(bib_entries, used_keys)
            whitelist = []
            for item in declared:
                present = actual.get(item["key"], 0)
                if present <= 0:
                    continue
                whitelist.append({"key": item["key"],
                                  "count": min(item["count"], present),
                                  "source": item["source"],
                                  "category": "W2-bib"})
            pdf_red, pdf_yellow = verify_document(
                pdf_path, {"number_ledger": ledger, "pdf_whitelist": whitelist})
            red += pdf_red
            yellow += pdf_yellow
            pdf_summary = {"checked": True, "file": cfg.output,
                           "ledger": len(ledger),
                           "whitelist": len(whitelist),
                           "red": len(pdf_red), "yellow": len(pdf_yellow)}

    summary = {
        "facts": len(facts),
        "sections": len(sections),
        "numbers_total": numbers_total,
        "numbers_matched": matched,
        "numbers_bound": bound,
        "numbers_unbound": unbound_yellow,
        "numbers_unmatched": unmatched,
        "annotations_skipped": annotations_total,
        "annotation_sites": annotation_sites,
        "cites_total": sum(used_keys.values()),
        "cites_unique": len(used_keys),
        "bib_entries": len(bib_entries),
        "bib_files": [p.relative_to(cfg.root).as_posix() for p in bib_paths],
        "bib_used": len([k for k in used_keys if k in bib_by_key]),
        "red": len(red),
        "yellow": len(yellow),
        "hints": len(hints),
        "pdf": pdf_summary,
        "confidence": {
            "high": sum(1 for f in facts if f.confidence == "high"),
            "med": sum(1 for f in facts if f.confidence == "med"),
            "low": sum(1 for f in facts if f.confidence == "low"),
        },
        "coverage": {
            "files_scanned": sorted(scanned),
            "files_scanned_count": len(scanned),
            "files_matched_by_glob": len(_glob_paths(cfg.root, cfg.sections_glob)),
            "files_unscanned": unscanned,
            "facts_loaded": len(facts),
            "parse_errors": 0,
            "sha_pinned": sum(1 for f in facts if f.source_sha256),
            "numbers_total": numbers_total,
            "numbers_bound": bound,
        },
        "usage": {k: v for k, v in usage.items()},
        "marker_count": marker_count,
        "attestation": {
            "facts_sha256": facts_digest(cfg),
            "sources_sha256": {src: digest for src, digest in sorted(
                (f.source, f.source_sha256) for f in facts if f.source_sha256)},
            "git_commit": git_commit(cfg.root),
        },
    }
    return red, yellow, hints, summary, unresolved
