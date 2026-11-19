# -*- coding: utf-8 -*-
"""工作台段一：项目发现、盘聚合与只读渲染。

这里只读磁盘：找 `factscribe.toml`、把同根名的两语言盘配成一个项目、
把 `.tex` 章节渲染成轻量 HTML。任何写操作都不在本模块里。

聚合规则（段一约定）：
  * `paper` 与 `paper-zh` 是同一个项目的两个盘（en 盘 + zh 盘）；
  * `paper-b` 与 `paper-b-zh` 同理；
  * 没有配对的盘自己成一个单盘项目。
项目名取项目声明里的标题，取不到就退回目录名。
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path

CONFIG_NAME = "factscribe.toml"
MAX_DEPTH = 3

#: 扫描时跳过的目录名（版本库、依赖目录、构建产物……）。
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache", ".idea",
    ".vscode", ".tox", ".eggs", "site-packages", "dist", "build",
    ".factscribe", ".DS_Store", "__MACOSX",
}

#: 目录名 → 语言。带 `-zh` 的是中文盘，其余按英文盘算。
_ZH_SUFFIX = "-zh"
_EN_SUFFIX = "-en"


# ---------------------------------------------------------------- 发现

def disk_language(name: str) -> str:
    """按目录名判断盘的语言：`xxx-zh` 是中文盘，`xxx-en` 与裸名是英文盘。"""
    lowered = name.lower()
    if lowered.endswith(_ZH_SUFFIX):
        return "zh"
    if lowered.endswith(_EN_SUFFIX):
        return "en"
    return "en"


def disk_base_name(name: str) -> str:
    """去掉语言后缀，得到配对用的根名。"""
    lowered = name.lower()
    for suffix in (_ZH_SUFFIX, _EN_SUFFIX):
        if lowered.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def discover_disks(root: str | Path, max_depth: int = MAX_DEPTH) -> list[Path]:
    """在 root 下面（深度受限）找出所有含 `factscribe.toml` 的目录。"""
    base = Path(root).expanduser()
    try:
        base = base.resolve()
    except OSError:
        return []
    if not base.is_dir():
        return []
    found: list[Path] = []
    base_depth = len(base.parts)

    def walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            return
        for entry in entries:
            try:
                if not entry.is_dir() or entry.is_symlink():
                    continue
            except OSError:
                continue
            if entry.name in SKIP_DIRS or entry.name.startswith("."):
                continue
            if (entry / CONFIG_NAME).is_file():
                found.append(entry)
                continue
            walk(entry, depth + 1)

    if (base / CONFIG_NAME).is_file():
        found.append(base)
    walk(base, 1)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in found:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


# ---------------------------------------------------------------- 聚合

def _disk_title(path: Path) -> str:
    """盘名：取项目声明里的标题，取不到退回目录名。"""
    from ..config import ConfigError, load_config

    try:
        cfg = load_config(path)
    except (ConfigError, OSError, ValueError):
        return path.name
    return (cfg.name or cfg.title or "").strip() or path.name


def _disk_counts(path: Path) -> tuple[int, int]:
    """(sections 数, facts 数)；读坏了就当 0，不让整页崩掉。"""
    from ..config import ConfigError, load_config, load_facts, load_sections

    try:
        cfg = load_config(path)
    except (ConfigError, OSError, ValueError):
        return 0, 0
    try:
        sections = load_sections(cfg)
    except Exception:  # noqa: BLE001 - 坏文件不该让整页崩
        sections = []
    try:
        facts = load_facts(cfg)
    except Exception:  # noqa: BLE001
        facts = []
    return len(sections), len(facts)


def aggregate(disks: list[Path]) -> list[dict]:
    """把盘按根名聚合成项目。

    同一个父目录下、去掉语言后缀后同名的盘属于同一个项目；
    项目 id 取根名（重复时加序号），项目名取声明里的标题。
    """
    groups: dict[tuple[str, str], list[Path]] = {}
    for disk in disks:
        parent = str(disk.parent)
        base = disk_base_name(disk.name)
        groups.setdefault((parent, base), []).append(disk)

    projects: list[dict] = []
    used_ids: set[str] = set()
    for (parent, base), members in sorted(groups.items(), key=lambda kv: kv[0][1]):
        members = sorted(members, key=lambda p: (disk_language(p.name) != "en", p.name))
        project_id = _unique_id(base, used_ids)
        used_ids.add(project_id)
        disks_out = []
        for member in members:
            sections, facts = _disk_counts(member)
            disks_out.append({
                "id": member.name,
                "lang": disk_language(member.name),
                "name": _disk_title(member),
                "path": str(member),
                "sections": sections,
                "facts": facts,
            })
        primary = next((d for d in disks_out if d["lang"] == "en"), disks_out[0])
        projects.append({
            "id": project_id,
            "name": primary["name"],
            "root": parent,
            "disks": disks_out,
        })
    return projects


def _unique_id(base: str, used: set[str]) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-") or "project"
    if slug not in used:
        return slug
    index = 2
    while "%s-%d" % (slug, index) in used:
        index += 1
    return "%s-%d" % (slug, index)


def load_projects(root: str | Path, max_depth: int = MAX_DEPTH) -> list[dict]:
    """发现 + 聚合：给 `/api/projects` 用。"""
    return aggregate(discover_disks(root, max_depth=max_depth))


# ---------------------------------------------------------------- 渲染

_ENV_RE = re.compile(r"\\(begin|end)\s*\{([A-Za-z*]+)\}")
_HEADING_RE = re.compile(r"\\(section|subsection|subsubsection)\s*\*?\s*\{")
_FACT_RE = re.compile(r"\\fact\s*\{([^{}]*)\}")
_CITE_RE = re.compile(r"\\(cite|citep|citet|Cite)\s*\{([^{}]*)\}")
_REF_RE = re.compile(r"\\(ref|eqref|autoref)\s*\{([^{}]*)\}")
_TEXT_CMD_RE = re.compile(
    r"\\(textbf|bfseries|emph|textit|texttt|underline|textsf)\s*\{")
_INLINE_KEEP = ("url", "href")


def _strip_comments(text: str) -> str:
    r"""去掉 `%` 注释（`\%` 是字面百分号，保留）。"""
    out: list[str] = []
    for line in text.splitlines():
        kept: list[str] = []
        index = 0
        length = len(line)
        while index < length:
            char = line[index]
            if char == "\\" and index + 1 < length:
                kept.append(line[index:index + 2])
                index += 2
                continue
            if char == "%":
                break
            kept.append(char)
            index += 1
        out.append("".join(kept))
    return "\n".join(out)


def _balanced(text: str, start: int) -> tuple[str, int]:
    """从 `{`（text[start]）起取配对花括号里的内容；返回 (内容, 结束下标)。"""
    if start >= len(text) or text[start] != "{":
        return "", start
    depth = 0
    index = start
    while index < len(text):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
        index += 1
    return text[start + 1:], len(text)


def _heading_title(text: str) -> tuple[str, str, int]:
    """读一行开头的 `\\section{...}`；返回 (级别, 标题, 消费到的下标)。"""
    match = _HEADING_RE.match(text)
    if not match:
        return "", "", 0
    level = {"section": 1, "subsection": 2, "subsubsection": 3}[match.group(1)]
    body, end = _balanced(text, match.end() - 1)
    return level, body, end


def _inline(text: str) -> str:
    """行内命令 → HTML（文本已经转义过）。"""
    out = text
    # \fact{ID} → 事实芯片（沿用原型的 .fc 样式）
    out = _FACT_RE.sub(
        lambda m: '<span class="fc" tabindex="0" data-fact="%s" role="button" '
                  'aria-label="有据的数字，查看出处">✓</span>' % m.group(1).strip(),
        out)
    # 强调类命令：把花括号内容换成带标签的
    def emph(match: re.Match) -> str:
        body, end = _balanced(out, match.end() - 1)
        tag = {"textbf": "b", "bfseries": "b", "emph": "i", "textit": "i",
               "texttt": "code", "underline": "u", "textsf": "span"}[match.group(1)]
        return "<%s>%s</%s>" % (tag, body, tag)

    previous = None
    while previous != out:
        previous = out
        out = _TEXT_CMD_RE.sub(emph, out)
    # 引用与交叉引用
    out = _CITE_RE.sub(
        lambda m: '<span class="cite">[%s]</span>' % m.group(2).strip(), out)
    out = _REF_RE.sub(
        lambda m: '<span class="xref">[%s]</span>' % m.group(2).strip(), out)
    # 其余命令一律去掉（含花括号参数）
    out = re.sub(r"\\[A-Za-z@]+\s*\*?\s*\[[^\]]*\]\s*\{[^{}]*\}", "", out)
    out = re.sub(r"\\[A-Za-z@]+\s*\*?\s*\[[^\]]*\]", "", out)
    out = re.sub(r"\\[A-Za-z@]+\s*\*?\s*\{[^{}]*\}", "", out)
    out = re.sub(r"\\[A-Za-z@]+\s*\*?", "", out)
    out = out.replace("~", " ").replace("---", "—").replace("--", "–")
    out = out.replace("\\%", "%").replace("\\&", "&").replace("\\_", "_")
    return out


def render_tex(text: str, stem: str = "sec") -> list[dict]:
    """把一段 LaTeX 渲染成块列表。

    块：`{"kind", "id", "level", "title", "title_en", "html"}`。
    `kind` 取 abstract / section / subsection / para。
    """
    source = _strip_comments(text)
    blocks: list[dict] = []
    buffer: list[str] = []
    in_abstract = False
    index = 0
    counter = 0
    length = len(source)

    def flush() -> None:
        nonlocal buffer
        chunk = "".join(buffer).strip()
        buffer = []
        if not chunk:
            return
        body = _inline(html.escape(chunk, quote=False))
        body = re.sub(r"[ \t]+", " ", body)
        body = re.sub(r"\n+", " ", body).strip()
        if not body:
            return
        blocks.append({
            "kind": "abstract" if in_abstract else "para",
            "id": "%s-p%d" % (stem, len(blocks)),
            "level": 0, "title": "", "title_en": "",
            "html": "<p>%s</p>" % body,
        })

    while index < length:
        char = source[index]
        if char == "\\":
            env = _ENV_RE.match(source, index)
            if env:
                name = env.group(2).lower()
                if env.group(1) == "begin" and name == "abstract":
                    flush()
                    in_abstract = True
                elif env.group(1) == "end" and name == "abstract":
                    flush()
                    in_abstract = False
                index = env.end()
                continue
            level, title, end = _heading_title(source[index:])
            if level:
                flush()
                counter += 1
                clean = _inline(html.escape(title, quote=False)).strip()
                blocks.append({
                    "kind": "section" if level == 1 else "subsection",
                    "id": "%s-s%d" % (stem, counter),
                    "level": level, "title": clean, "title_en": "",
                    "html": "",
                })
                index += end
                continue
        if char == "\n" and source[index:index + 2] == "\n":
            flush()
            index += 2
            continue
        buffer.append(char)
        index += 1
    flush()
    return blocks


def _section_files(path: Path) -> list[tuple[str, str]]:
    r"""读盘里的章节文件：[(相对名, 文本)]。

    走审计那套闭包（`load_sections`）：配置写 `sections/*.tex` 时收章节，
    写 `main.tex` 时收 `\input` 链。根文件（main.tex）的导言区不当作正文，
    还有别的章节文件时把它剔掉。
    """
    from ..config import ConfigError, load_config, load_sections

    try:
        cfg = load_config(path)
    except (ConfigError, OSError, ValueError):
        return []
    rows: list[tuple[str, str]] = []
    try:
        for row in load_sections(cfg):
            try:
                name, text = row
            except (TypeError, ValueError):
                continue
            rows.append((str(name), str(text)))
    except Exception:  # noqa: BLE001 - 坏文件不该让整页崩
        rows = []
    if rows:
        root_tex = Path(cfg.root_tex or "main.tex").name
        kept = [(name, text) for name, text in rows
                if Path(name).name != root_tex
                and not _is_generated(name)]
        kept.sort(key=lambda row: _file_order(row[0]))
        return kept or rows
    pattern = cfg.sections_glob or "sections/*.tex"
    out: list[tuple[str, str]] = []
    try:
        candidates = sorted(path.glob(pattern))
    except (OSError, ValueError):
        candidates = []
    for candidate in candidates:
        try:
            out.append((str(candidate.relative_to(path)),
                        candidate.read_text(encoding="utf-8", errors="replace")))
        except (OSError, ValueError):
            continue
    return out


def _is_generated(rel: str) -> bool:
    """生成的工件（audit/ 下的宏定义等）不是正文。"""
    parts = Path(rel).parts
    return bool(parts) and parts[0] in ("audit", "results")


def _file_order(rel: str) -> tuple:
    """正文顺序：sections/ 在前，其余按路径排。"""
    parts = Path(rel).parts
    head = parts[0] if parts else ""
    return (0 if head == "sections" else 1, rel)


def _titles_by_stem(path: Path) -> dict[str, str]:
    """{章节文件名: 标题}——给双语盘配英文标题用。"""
    titles: dict[str, str] = {}
    for name, text in _section_files(path):
        stem = Path(name).stem
        for block in render_tex(text, stem=stem):
            if block["kind"] == "section" and block["title"]:
                titles[stem] = block["title"]
                break
    return titles


def disk_sections(path: str | Path, lang: str = "") -> dict:
    """一个盘的章节内容：块列表 + 标题（含配对盘的英文标题）。"""
    root = Path(path)
    paired = _paired_titles(root) if lang == "zh" else {}
    blocks: list[dict] = []
    for name, text in _section_files(root):
        stem = Path(name).stem
        for block in render_tex(text, stem=stem):
            if block["kind"] == "section" and not block["title_en"]:
                block["title_en"] = paired.get(stem, "")
            blocks.append(block)
    return {"blocks": blocks, "count": len(blocks)}


def _paired_titles(path: Path) -> dict[str, str]:
    """找同父目录下另一个语言盘的 {文件名: 标题}。"""
    sibling = None
    name = path.name
    base = disk_base_name(name)
    for candidate in path.parent.iterdir():
        if not candidate.is_dir() or candidate == path:
            continue
        if not (candidate / CONFIG_NAME).is_file():
            continue
        if disk_base_name(candidate.name) != base:
            continue
        if disk_language(candidate.name) == disk_language(name):
            continue
        sibling = candidate
        break
    if sibling is None:
        return {}
    return _titles_by_stem(sibling)


def disk_meta(path: str | Path, lang: str = "") -> dict:
    """状态行数据：事实条数、章节数、最近编译时间。"""
    from ..config import ConfigError, load_config

    root = Path(path)
    sections, facts = _disk_counts(root)
    title = _disk_title(root)
    built = ""
    built_file = ""
    try:
        cfg = load_config(root)
        output = cfg.output or "main.pdf"
    except (ConfigError, OSError, ValueError):
        output = "main.pdf"
    for candidate in (output, "main.pdf", "main.log"):
        target = root / candidate
        if target.is_file():
            try:
                stamp = datetime.fromtimestamp(target.stat().st_mtime, timezone.utc)
            except OSError:
                continue
            built = stamp.isoformat(timespec="seconds")
            built_file = candidate
            break
    return {
        "path": str(root),
        "name": title,
        "lang": lang or disk_language(root.name),
        "facts": facts,
        "sections": sections,
        "last_build": built,
        "last_build_file": built_file,
    }
