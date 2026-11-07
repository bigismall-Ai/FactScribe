# -*- coding: utf-8 -*-
"""项目声明读取：factscribe.toml/paperkit.toml、迷你 TOML、facts/sections 装载。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .facts import Fact, canon_text, fact_value_keys

# --------------------------------------------------------------------------
# TOML 读写（3.11+ 用 tomllib；3.10 用内置极简解析器兜底）
# --------------------------------------------------------------------------

try:  # pragma: no cover - 解释器相关
    import tomllib as _tomllib
except ModuleNotFoundError:  # pragma: no cover
    _tomllib = None


class ConfigError(Exception):
    """配置/用法层面的错误 -> 退出码 2。"""


def _strip_toml_comment(line: str) -> str:
    out = []
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            out.append(c)
            if c == "\\" and quote == '"' and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        else:
            if c in "\"'":
                quote = c
                out.append(c)
            elif c == "#":
                break
            else:
                out.append(c)
        i += 1
    return "".join(out)


def _mini_toml_value(raw: str):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    if raw.startswith("[") and raw.endswith("]"):
        body = raw[1:-1]
        items, buf, quote = [], [], None
        for c in body:
            if quote:
                buf.append(c)
                if c == quote:
                    quote = None
            elif c in "\"'":
                quote = c
                buf.append(c)
            elif c == ",":
                items.append("".join(buf))
                buf = []
            else:
                buf.append(c)
        if "".join(buf).strip():
            items.append("".join(buf))
        return [_mini_toml_value(x) for x in items if x.strip()]
    try:
        if any(ch in raw for ch in ".eE") and not raw.startswith("0x"):
            return float(raw)
        return int(raw)
    except ValueError:
        return raw  # 裸词，容错


def _needs_more(value: str) -> bool:
    depth = 0
    quote = None
    for c in value:
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
    return depth > 0


def _mini_toml(text: str) -> dict:
    """只覆盖 paperkit 契约用得到的子集：表、表数组、字符串、数组、数字、布尔。"""
    root: dict = {}
    cur: dict = root
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        s = _strip_toml_comment(raw).strip()
        if not s:
            continue
        if s.startswith("[[") and s.endswith("]]"):
            name = s[2:-2].strip()
            arr = root.setdefault(name, [])
            if not isinstance(arr, list):
                raise ValueError("[[%s]] 与同名表冲突" % name)
            cur = {}
            arr.append(cur)
            continue
        if s.startswith("[") and s.endswith("]"):
            name = s[1:-1].strip()
            tbl = root.setdefault(name, {})
            if not isinstance(tbl, dict):
                raise ValueError("[%s] 与同名表数组冲突" % name)
            cur = tbl
            continue
        if "=" not in s:
            raise ValueError("无法解析的 TOML 行：%r" % raw)
        key, value = s.split("=", 1)
        value = value.strip()
        while _needs_more(value) and i < len(lines):
            value += " " + _strip_toml_comment(lines[i]).strip()
            i += 1
        cur[key.strip().strip("\"'")] = _mini_toml_value(value)
    return root


def load_toml(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError("读不了 %s：%s" % (path, exc))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError("%s 不是合法 UTF-8：%s" % (path, exc))
    try:
        if _tomllib is not None:
            return _tomllib.loads(text)
        return _mini_toml(text)
    except (ValueError, Exception) as exc:  # tomllib.TOMLDecodeError 是 ValueError 子类
        raise ConfigError("TOML 解析失败 %s：%s" % (path, exc))

# --------------------------------------------------------------------------
# 项目 / facts / 正文 读取
# --------------------------------------------------------------------------

@dataclass
class Config:
    root: Path
    title: str = ""
    authors: list = field(default_factory=list)
    sections_glob: str = "sections/*.tex"
    facts_glob: str = "facts/*.toml"
    bib: str = "refs.bib"
    build: str = ""
    manifest: str = "results/MANIFEST.toml"
    source_root: str = ""        # source 的解析根；空＝只许项目内 results/
    numeric_macro_allow: list = field(default_factory=list)  # 人签登记的数值宏名

    # ---- V3.0 扁平项目声明（schema = "paperkit-project/3.x"）----
    # v1 配置不写顶层 schema，以下字段保持默认值，行为与旧版完全一致。
    schema: str = ""
    name: str = ""
    root_tex: str = ""           # V3：审计闭包起点（非空即「从 root 文件展开」）
    output: str = "main.pdf"     # V3：最终 PDF（PDF 回检用）
    signing_mode: str = ""       # V3：offline_manifest | local_key
    number_locale: str = "period"  # V3：period | comma
    approver_keys_file: str = ""   # V3：审批公钥（项目外）
    release_keys_file: str = ""    # V3：发布公钥（项目外）
    image_budget_extra: int = 0    # V3：图片预算宽限（人签）
    frac_allow: list = field(default_factory=list)         # V3：允许的 \frac 登记
    inline_images_allow: list = field(default_factory=list)  # V3：行内小图登记

    @property
    def is_v3(self) -> bool:
        return self.schema.startswith(V3_PROJECT_SCHEMA_PREFIX)


V3_PROJECT_SCHEMA_PREFIX = "paperkit-project/3."
V3_FACT_SCHEMA_PREFIX = "paperkit-fact/3."
SIGNING_MODES = ("offline_manifest", "local_key")
NUMBER_LOCALES = ("period", "comma")


def _v3_str(data: dict, key: str, path: Path, *, default=None,
            required: bool = False) -> str:
    """取 V3 顶层字符串字段：缺省/空白按 default，类型不符直接报错。"""
    if key not in data:
        if required:
            raise ConfigError(
                "%s 缺少顶层 %s（schema=%r 必填）" % (path, key, data.get("schema")))
        return "" if default is None else default
    raw = data[key]
    if not isinstance(raw, str):
        raise ConfigError(
            "%s 的 %s 必须是字符串，现在是 %r" % (path, key, raw))
    raw = raw.strip()
    if not raw:
        if required:
            raise ConfigError("%s 的 %s 不能为空" % (path, key))
        return "" if default is None else default
    return raw


def _v3_rel_path(raw: str, key: str, path: Path) -> str:
    """V3 里的项目内路径：必须是相对路径，不许 absolute / ..。"""
    p = Path(raw)
    if p.is_absolute() or ".." in p.parts:
        raise ConfigError(
            "%s 的 %s 必须是项目内相对路径（不许绝对路径或 ..）：%s" % (path, key, raw))
    return p.as_posix()


def _v3_str_list(data: dict, key: str, path: Path) -> list:
    raw = data.get(key)
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ConfigError("%s 的 %s 必须是字符串数组，现在是 %r" % (path, key, raw))
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            item = item.get("name") or item.get("token") or ""
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(
                "%s 的 %s 里有非字符串条目：%r" % (path, key, item))
        out.append(item.strip())
    return out


def _load_v1_config(root: Path, path: Path, data: dict) -> Config:
    """旧版：顶层 [project] 表（title/sections/facts/bib/build…），行为不变。"""
    proj = data.get("project")
    if not isinstance(proj, dict):
        raise ConfigError("%s 缺少 [project] 段" % path)
    for key in ("sections", "facts"):
        if not proj.get(key):
            raise ConfigError("%s 缺少 project.%s" % (path, key))
    authors = proj.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    allow = proj.get("numeric_macro_allow") or []
    if isinstance(allow, (str, dict)):
        allow = [allow]
    macro_allow: list[str] = []
    for item in allow:
        name = item.get("name") if isinstance(item, dict) else item
        if str(name or "").strip():
            macro_allow.append(str(name).strip().lstrip("\\"))
    return Config(
        root=root,
        title=str(proj.get("title") or ""),
        authors=[str(a) for a in authors],
        sections_glob=str(proj["sections"]),
        facts_glob=str(proj["facts"]),
        bib=str(proj.get("bib") or "refs.bib"),
        build=str(proj.get("build") or ""),
        manifest=str(proj.get("manifest") or "results/MANIFEST.toml"),
        source_root=str(proj.get("source_root") or ""),
        numeric_macro_allow=macro_allow,
    )


def _load_v3_config(root: Path, path: Path, data: dict) -> Config:
    """V3.0 扁平声明：顶层 schema/name/root_tex/output/...（无 [project] 段）。

    本轮只负责「读得到、传得下去」：字段做类型与取值域校验后放进 Config；
    判据（keys 是否在项目外、locale 是否已签名、图片预算是否被签过等）
    留到 C 阶段，这里不预先判红。
    """
    schema = str(data.get("schema") or "").strip()
    root_tex = _v3_str(data, "root_tex", path, required=True)
    root_tex = _v3_rel_path(root_tex, "root_tex", path)
    output = _v3_str(data, "output", path, default="main.pdf")
    if output:
        output = _v3_rel_path(output, "output", path)
    signing_mode = _v3_str(data, "signing_mode", path, default="offline_manifest")
    if signing_mode not in SIGNING_MODES:
        raise ConfigError(
            "%s 的 signing_mode=%r 不认识（只允许 %s）"
            % (path, signing_mode, " / ".join(SIGNING_MODES)))
    number_locale = _v3_str(data, "number_locale", path, default="period")
    if number_locale not in NUMBER_LOCALES:
        raise ConfigError(
            "%s 的 number_locale=%r 不认识（只允许 %s）"
            % (path, number_locale, " / ".join(NUMBER_LOCALES)))
    budget = data.get("image_budget_extra", 0)
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        raise ConfigError(
            "%s 的 image_budget_extra 必须是非负整数，现在是 %r" % (path, budget))
    name = _v3_str(data, "name", path)
    return Config(
        root=root,
        title=name,
        sections_glob=root_tex,
        facts_glob="facts/*.toml",
        bib="refs.bib",
        build="",
        manifest="results/MANIFEST.toml",
        schema=schema,
        name=name,
        root_tex=root_tex,
        output=output,
        signing_mode=signing_mode,
        number_locale=number_locale,
        approver_keys_file=_v3_str(data, "approver_keys_file", path),
        release_keys_file=_v3_str(data, "release_keys_file", path),
        image_budget_extra=budget,
        frac_allow=_v3_str_list(data, "frac_allow", path),
        inline_images_allow=_v3_str_list(data, "inline_images_allow", path),
    )


def load_config(root: Path) -> Config:
    path = root / "factscribe.toml"
    if not path.is_file():
        path = root / "paperkit.toml"
    if not path.is_file():
        raise ConfigError("找不到项目声明 %s（缺 paperkit.toml 不敢跑）" % path)
    data = load_toml(path)

    # schema 自动识别：有顶层 schema 就只认 paperkit-project/3.x；
    # 没写 schema 的走 v1（[project] 表，行为不变）。未知版本明确报错，不猜。
    if "schema" in data:
        schema = data.get("schema")
        if not isinstance(schema, str) or not schema.strip():
            raise ConfigError(
                "%s 的顶层 schema 必须是非空字符串，现在是 %r" % (path, schema))
        if not schema.strip().startswith(V3_PROJECT_SCHEMA_PREFIX):
            raise ConfigError(
                "%s 的 schema=%r 不认识——本工具只认 %sx 的扁平声明；"
                "旧版配置请去掉顶层 schema、改用 [project] 表"
                % (path, schema, V3_PROJECT_SCHEMA_PREFIX))
        return _load_v3_config(root, path, data)

    return _load_v1_config(root, path, data)


def _normalise_display(raw) -> list[dict]:
    """display 项：字符串简写或 `{text, round_to?, setting?}` 表。"""
    if raw is None:
        return []
    if isinstance(raw, (str, dict)):
        raw = [raw]
    out: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            out.append({"text": item, "round_to": None, "setting": None})
        elif isinstance(item, dict):
            out.append({
                "text": str(item.get("text") or ""),
                "round_to": item.get("round_to"),
                "setting": item.get("setting"),
            })
    return out


def _locate_id_line(path: Path, fid: str) -> int:
    pat = re.compile(r"""^\s*id\s*=\s*["']%s["']""" % re.escape(fid))
    try:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pat.match(line):
                return i
    except OSError:
        pass
    return 0


def _fact_from_mapping(raw: dict, path: Path, cfg: Config) -> Fact:
    fid = str(raw.get("id") or "").strip()
    rel = path.relative_to(cfg.root).as_posix()
    locator = str(raw.get("locator") or "")
    if not locator:
        # V3 用 pointer 指向原始产物内部（如 "/summary/rate"）；落到 locator 供人看。
        locator = str(raw.get("pointer") or "")
    f = Fact(
        id=fid,
        claim=str(raw.get("claim") or ""),
        value=str(raw.get("value") or ""),
        source=str(raw.get("source") or ""),
        source_sha256=str(raw.get("source_sha256") or "").strip().lower(),
        locator=locator,
        confidence=str(raw.get("confidence") or ""),
        kind=str(raw.get("kind") or "claim"),
        derived_from=[str(x) for x in (raw.get("derived_from") or [])],
        supersedes=[str(x) for x in (raw.get("supersedes") or [])],
        expr=str(raw.get("expr") or "").strip(),
        metric=str(raw.get("metric") or ""),
        scope=str(raw.get("scope") or ""),
        note=str(raw.get("note") or ""),
        display=_normalise_display(raw.get("display")),
        co_claim=[str(x) for x in (raw.get("co_claim") or [])],
        file=rel,
        line=_locate_id_line(path, fid),
    )
    if not f.id:
        raise ConfigError("%s 里有一条 fact 缺 id（不准匿名入账）" % path)
    f.value_keys = fact_value_keys(f.value)
    # display 只允许追加与 value **严格等价**的写法（R-04）；这里先把
    # 它们的字面规范键并入值域，等价性另由 DISPLAY_INCONSISTENT 检查。
    for item in f.display:
        f.value_keys |= fact_value_keys(item["text"])
        canon = canon_text(item["text"])
        if canon is not None:
            f.value_keys.add(canon)
    return f


def load_facts(cfg: Config) -> list[Fact]:
    files = sorted(p for p in cfg.root.glob(cfg.facts_glob) if p.is_file())
    facts: list[Fact] = []
    for path in files:
        data = load_toml(path)
        # V3 的 fact 文件是「一文件一条、顶层扁平」；有 schema 就按 3.x 读，
        # 未知 fact schema 明确报错。没写 schema 的仍是 v1 的 [[fact]] 表数组。
        if "schema" in data:
            schema = data.get("schema")
            if not isinstance(schema, str) or not schema.strip().startswith(
                    V3_FACT_SCHEMA_PREFIX):
                raise ConfigError(
                    "%s 的 schema=%r 不认识——本工具只认 %sx 的扁平 fact 文件"
                    % (path, schema, V3_FACT_SCHEMA_PREFIX))
            entries = [data]
        else:
            entries = data.get("fact")
            if entries is None:
                continue
            if not isinstance(entries, list):
                raise ConfigError("%s 里 fact 必须是 [[fact]] 表数组" % path)
        for raw in entries:
            if not isinstance(raw, dict):
                raise ConfigError("%s 里有一条 fact 不是表" % path)
            facts.append(_fact_from_mapping(raw, path, cfg))
    return facts


def _glob_paths(root: Path, pattern: str) -> dict[str, Path]:
    """glob 默认递归：sections/*.tex 同时匹配 sections/**/*.tex（红队 B4）。"""
    pats = [pattern]
    if "**" not in pattern:
        d, sep, base = pattern.rpartition("/")
        if base:
            pats.append((d + "/**/" + base) if d else ("**/" + base))
    found: dict[str, Path] = {}
    for pat in pats:
        for p in root.glob(pat):
            if p.is_file():
                found[p.relative_to(root).as_posix()] = p
    return found


_INPUT_RE = re.compile(r"\\(?:input|include|subfile|import)\s*\{([^}]*)\}")
_DEF_RE = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand)\*?\s*\{\s*\\([A-Za-z@]+)\s*\}"
    r"\s*(?:\[(\d)\])?\s*(?:\[[^\]]*\])?\s*\{")
_INPUT_WRAPPER_RE = re.compile(r"^\s*\\input\s*\{([^{}]*#(\d)[^{}]*)\}\s*$")
_SKIP_DIRS = {".git", ".venv", "__pycache__", "audit", "node_modules", ".pytest_cache"}


def _balanced_braces(text: str, start: int) -> int:
    """text[start] == '{'；返回配对 '}' 之后的位置。"""
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def _input_wrappers(text: str) -> dict[str, tuple[str, str]]:
    """识别 `\\newcommand{\\X}[1]{\\input{#1}}` 这类「审计隧道」包装宏。

    V2.2 R-05 / 内部 B1：闭包必须展开纯 `\\input` 包装宏，否则表格整体
    绕开审计。返回 {宏名: (参数号, 目标模板)}，模板里保留 `#1` 占位。
    """
    out: dict[str, tuple[str, str]] = {}
    for m in _DEF_RE.finditer(text):
        name = m.group(1)
        body_start = m.end() - 1
        body_end = _balanced_braces(text, body_start)
        body = text[body_start + 1:body_end - 1].strip()
        w = _INPUT_WRAPPER_RE.match(body)
        if w:
            out[name] = (w.group(2), w.group(1))
    return out


def _wrapper_calls(text: str, wrappers: dict[str, tuple[str, str]]):
    for name, (argn, template) in wrappers.items():
        pat = re.compile(r"\\%s\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}" % re.escape(name))
        for m in pat.finditer(text):
            yield template.replace("#" + argn, m.group(1).strip())


def load_sections(cfg: Config) -> list[tuple[str, str]]:
    """sections = glob 递归命中 + `\\input/\\include/\\subfile` 闭包（红队 B4）
    + 纯 `\\input` 包装宏展开（V2.2 R-05 / 内部 B1）。

    文件边界不是句子边界（R-02）；这里只负责把「会被编译进 PDF 的文本文件」
    收齐，拼流与切句交给 texscan。
    """
    if cfg.root_tex:
        # V3：闭包从 root_tex 这个文件出发（不是 glob），避免递归把子目录里
        # 同名的 main.tex 也卷进来。
        root_file = cfg.root / cfg.root_tex
        if not root_file.is_file():
            raise ConfigError(
                "root_tex 指向的 %s 不存在——没有起点就无法展开审计闭包"
                % cfg.root_tex)
        found = {cfg.root_tex: root_file}
    else:
        found = _glob_paths(cfg.root, cfg.sections_glob)
    seen: dict[str, Path] = dict(found)
    queue: list[Path] = list(found.values())

    def add_ref(ref: str, base_dir: Path) -> bool:
        ref = ref.strip()
        if not ref or "\\" in ref or "#" in ref:
            return False
        for candidate in (base_dir / ref, base_dir / (ref + ".tex")):
            if not candidate.is_file():
                continue
            try:
                rel = candidate.resolve().relative_to(cfg.root.resolve()).as_posix()
            except ValueError:
                return False
            if rel in seen:
                continue
            seen[rel] = candidate
            queue.append(candidate)
            return True
        return False

    while True:
        # 普通 \input 闭包
        while queue:
            p = queue.pop(0)
            text = _read_text(p, cfg.root)
            for m in _INPUT_RE.finditer(text):
                add_ref(m.group(1), p.parent)
                add_ref(m.group(1), cfg.root)
        # 包装宏：定义可能出现在后加载的文件里，故反复扫到稳定为止
        wrappers: dict[str, tuple[str, str]] = {}
        for p in list(seen.values()):
            wrappers.update(_input_wrappers(_read_text(p, cfg.root)))
        if not wrappers:
            break
        grew = False
        for p in list(seen.values()):
            text = _read_text(p, cfg.root)
            for ref in _wrapper_calls(text, wrappers):
                if add_ref(ref, p.parent) or add_ref(ref, cfg.root):
                    grew = True
        if not grew:
            break

    out = []
    for rel in sorted(seen):
        out.append((rel, _read_text(seen[rel], cfg.root)))
    return out


def _read_text(path: Path, root: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError("%s 不是合法 UTF-8：%s" % (path, exc))
    except OSError as exc:
        raise ConfigError("读不了 %s：%s" % (path, exc))


def all_tex_files(cfg: Config) -> list[str]:
    """项目内全部 .tex（用于「闭包外文件是否从未被审计」的覆盖报告）。"""
    out = []
    for p in cfg.root.glob("**/*.tex"):
        if not p.is_file():
            continue
        parts = set(p.relative_to(cfg.root).parts)
        if parts & _SKIP_DIRS:
            continue
        out.append(p.relative_to(cfg.root).as_posix())
    return sorted(out)


def facts_digest(cfg: Config) -> str:
    """账本输入指纹：所有 facts 文件按路径排序后串哈希（红队 D7）。"""
    h = hashlib.sha256()
    for name, path in sorted(_glob_paths(cfg.root, cfg.facts_glob).items()):
        h.update(name.encode("utf-8"))
        h.update(path.read_bytes())
    return h.hexdigest()


def git_commit(root: Path) -> str:
    """尽力读 git 提交号；读不到就空串（不联网、不调 git 命令）。"""
    head = root / ".git" / "HEAD"
    try:
        raw = head.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if raw.startswith("ref:"):
        ref = raw.split(":", 1)[1].strip()
        try:
            return (root / ".git" / ref).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return raw
