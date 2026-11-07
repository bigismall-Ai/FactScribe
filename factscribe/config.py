# -*- coding: utf-8 -*-
"""项目声明读取：factscribe.toml/paperkit.toml、迷你 TOML、facts/sections 装载。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .facts import Fact, fact_value_keys

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

def load_config(root: Path) -> Config:
    path = root / "factscribe.toml"
    if not path.is_file():
        path = root / "paperkit.toml"
    if not path.is_file():
        raise ConfigError("找不到项目声明 %s（缺 paperkit.toml 不敢跑）" % path)
    data = load_toml(path)
    proj = data.get("project")
    if not isinstance(proj, dict):
        raise ConfigError("%s 缺少 [project] 段" % path)
    for key in ("sections", "facts"):
        if not proj.get(key):
            raise ConfigError("%s 缺少 project.%s" % (path, key))
    authors = proj.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
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
    )


def _locate_id_line(path: Path, fid: str) -> int:
    pat = re.compile(r"""^\s*id\s*=\s*["']%s["']""" % re.escape(fid))
    try:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pat.match(line):
                return i
    except OSError:
        pass
    return 0


def load_facts(cfg: Config) -> list[Fact]:
    files = sorted(p for p in cfg.root.glob(cfg.facts_glob) if p.is_file())
    facts: list[Fact] = []
    for path in files:
        data = load_toml(path)
        entries = data.get("fact")
        if entries is None:
            continue
        if not isinstance(entries, list):
            raise ConfigError("%s 里 fact 必须是 [[fact]] 表数组" % path)
        for raw in entries:
            if not isinstance(raw, dict):
                raise ConfigError("%s 里有一条 fact 不是表" % path)
            fid = str(raw.get("id") or "").strip()
            rel = path.relative_to(cfg.root).as_posix()
            f = Fact(
                id=fid,
                claim=str(raw.get("claim") or ""),
                value=str(raw.get("value") or ""),
                source=str(raw.get("source") or ""),
                source_sha256=str(raw.get("source_sha256") or "").strip().lower(),
                locator=str(raw.get("locator") or ""),
                confidence=str(raw.get("confidence") or ""),
                kind=str(raw.get("kind") or "claim"),
                derived_from=[str(x) for x in (raw.get("derived_from") or [])],
                supersedes=[str(x) for x in (raw.get("supersedes") or [])],
                expr=str(raw.get("expr") or "").strip(),
                metric=str(raw.get("metric") or ""),
                scope=str(raw.get("scope") or ""),
                note=str(raw.get("note") or ""),
                file=rel,
                line=_locate_id_line(path, fid),
            )
            if not f.id:
                raise ConfigError("%s 里有一条 fact 缺 id（不准匿名入账）" % path)
            f.value_keys = fact_value_keys(f.value)
            facts.append(f)
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
_SKIP_DIRS = {".git", ".venv", "__pycache__", "audit", "node_modules", ".pytest_cache"}


def _read_text(path: Path, root: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError("%s 不是合法 UTF-8：%s" % (path, exc))
    except OSError as exc:
        raise ConfigError("读不了 %s：%s" % (path, exc))


def load_sections(cfg: Config) -> list[tuple[str, str]]:
    """sections = glob 递归命中 + \\input/\\include/\\subfile 闭包（红队 B4）。"""
    found = _glob_paths(cfg.root, cfg.sections_glob)
    seen: dict[str, Path] = dict(found)
    queue: list[Path] = list(found.values())
    while queue:
        p = queue.pop(0)
        text = _read_text(p, cfg.root)
        for m in _INPUT_RE.finditer(text):
            ref = m.group(1).strip()
            if not ref or "\\" in ref or "#" in ref:
                continue
            for base_dir in (cfg.root, p.parent):
                for cand in (base_dir / ref, base_dir / (ref + ".tex")):
                    if not cand.is_file():
                        continue
                    try:
                        rel = cand.resolve().relative_to(cfg.root.resolve()).as_posix()
                    except ValueError:
                        continue
                    if rel not in seen:
                        seen[rel] = cand
                        queue.append(cand)
    out = []
    for rel in sorted(seen):
        out.append((rel, _read_text(seen[rel], cfg.root)))
    return out


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
