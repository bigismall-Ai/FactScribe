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

_TITLE_CMD_RE = re.compile(r"\\title\s*\{")
# 标题里的排版命令：只影响观感，不该出现在页面上。
_TITLE_NOISE = ("\\large", "\\Large", "\\LARGE", "\\huge", "\\Huge",
                "\\bfseries", "\\rmfamily", "\\sffamily", "\\mdseries",
                "\\itshape", "\\upshape", "\\normalfont")
# `\\`（换行）后面可跟 `[4pt]` 这样的可选参数。
_TITLE_BREAK_RE = re.compile(r"\\\\(?:\[[^\]]*\])?")


def _clean_title(text: str) -> str:
    """去掉标题里的 LaTeX 排版味，留人读得懂的一句。"""
    out = text.replace("\\%", "%").replace("\\&", "&").replace("\\_", "_")
    for cmd in _TITLE_NOISE:
        out = out.replace(cmd, "")
    out = out.replace("{", "").replace("}", "")
    return " ".join(out.split())


def _title_files(path: Path) -> list[Path]:
    """这个盘自己的入口 .tex：先按项目声明的 `root_tex`，再按常见文件名。"""
    out: list[Path] = []
    try:
        from ..config import ConfigError, load_config
        cfg = load_config(path)
        if cfg.root_tex:
            target = path / cfg.root_tex
            if target.is_file():
                out.append(target)
    except Exception:  # noqa: BLE001 - 读不到声明就按常见文件名找
        pass
    for name in ("main.tex", "paper.tex", "root.tex"):
        target = path / name
        if target.is_file() and target not in out:
            out.append(target)
    return out


def _tex_title_parts(path: Path) -> tuple[str, str]:
    """盘自己的标题：读这个盘入口 .tex 的 `\\title{…}` → (主标题, 副标题)。

    段二起，标题**分盘取**：中文盘显示中文标题，不再统一挂英题。
    段三再进一步：把 `\\large …`、`\\[4pt]` 这类排版命令剥掉，
    副标题（`\\` 之后那半句）单独返回，不跟主标题挤在一行里。
    """
    for target in _title_files(path):
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = _TITLE_CMD_RE.search(text)
        if not match:
            continue
        body, _end = _balanced(text, match.end() - 1)
        if not body.strip():
            continue
        pieces = [p for p in _TITLE_BREAK_RE.split(body)]
        title = _clean_title(pieces[0]) if pieces else ""
        if not title:
            continue
        subtitle = _clean_title(pieces[1]) if len(pieces) > 1 else ""
        return title, subtitle
    return "", ""


def _tex_title(path: Path) -> str:
    """盘自己的主标题（分盘取，去排版味）。"""
    return _tex_title_parts(path)[0]


def _tex_subtitle(path: Path) -> str:
    """盘自己的副标题（`\\title{…}` 里 `\\` 之后那半句）。"""
    return _tex_title_parts(path)[1]


def _disk_title(path: Path) -> str:
    """盘名：先取这个盘自己的 `main.tex` 标题，再退回项目声明，最后目录名。"""
    from ..config import ConfigError, load_config

    tex_title = _tex_title(path)
    if tex_title:
        return tex_title
    try:
        cfg = load_config(path)
    except (ConfigError, OSError, ValueError):
        return path.name
    return (cfg.name or cfg.title or "").strip() or path.name


def _config_title(path: Path) -> str:
    """项目声明里的标题（不分盘）。"""
    from ..config import ConfigError, load_config

    try:
        cfg = load_config(path)
    except (ConfigError, OSError, ValueError):
        return ""
    return (cfg.name or cfg.title or "").strip()


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


def _disk_progress(path: Path) -> dict:
    """进度口径（写在这里，前端只显示，不另算）：

    **进度 = 已绑事实数 / 定量事实总数**。
    * 分母：账本（`facts/*.toml`）里 `value` 非空的事实数（定量事实）；
    * 分子：其中在本盘正文里出现过 `\\fact{ID}` 标记的事实数（已绑）；
    * 分母为 0（还没有定量事实）时进度记 0，界面显示「暂无定量事实」。
    """
    from ..config import ConfigError, load_config, load_facts

    empty = {"bound": 0, "total": 0, "percent": 0}
    try:
        cfg = load_config(path)
        facts = load_facts(cfg)
    except (ConfigError, OSError, ValueError):
        return empty
    total = {f.id for f in facts if str(getattr(f, "value", "") or "").strip()}
    if not total:
        return empty
    marked: set[str] = set()
    for _name, text in _section_files(path):
        for match in re.finditer(r"\\fact\s*\{([^{}]*)\}", text):
            for fid in match.group(1).split(","):
                fid = fid.strip()
                if fid:
                    marked.add(fid)
    bound = len(total & marked)
    return {"bound": bound, "total": len(total),
            "percent": int(round(bound * 100 / len(total)))}


def _workbench_table(path: Path) -> dict:
    """项目配置里的 `[workbench]` 表（工作台自己的字段：目录、最近打开…）。"""
    from ..config import load_toml

    config = path / CONFIG_NAME
    if not config.is_file():
        return {}
    try:
        data = load_toml(config)
    except Exception:  # noqa: BLE001 - 坏配置当没有
        return {}
    table = data.get("workbench")
    return table if isinstance(table, dict) else {}


def _disk_last_opened(path: Path) -> str:
    """最近打开时间：项目配置 `factscribe.toml` 的 `[workbench].last_opened`。"""
    return str(_workbench_table(path).get("last_opened") or "").strip()


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
            bench = _workbench_table(member)
            disks_out.append({
                "id": member.name,
                "lang": disk_language(member.name),
                "name": _disk_title(member),
                "subtitle": _tex_subtitle(member),
                "path": str(member),
                "sections": sections,
                "facts": facts,
                "progress": _disk_progress(member),
                "last_opened": _disk_last_opened(member),
                "project_dir": str(bench.get("project_dir") or member.name),
                "reports_dir": str(bench.get("reports_dir")
                                   or (bench.get("project_dir") or member.name)
                                   + "/reports"),
            })
        primary = next((d for d in disks_out if d["lang"] == "en"), disks_out[0])
        projects.append({
            "id": project_id,
            "name": _config_title(Path(primary["path"])) or primary["name"],
            "root": parent,
            "disks": disks_out,
            # 单语项目（只有一个盘）→ 导航面板上的中/EN 切换整组隐藏。
            "multi_lang": len(disks_out) > 1,
            "langs": sorted({d["lang"] for d in disks_out if d.get("lang")}),
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
    for line in text.splitlines(keepends=True):
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
                while index < length and line[index] != "\n":
                    kept.append(" ")
                    index += 1
                continue
            kept.append(char)
            index += 1
        out.append("".join(kept))
    return "".join(out)


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

    块：`{"kind", "id", "level", "title", "title_en", "html", "start", "end",
    "raw"}`。`kind` 取 abstract / section / subsection / para。

    `start`/`end` 是这一块在**原文**里的偏移（`_strip_comments` 等长替换，
    偏移与原文一一对应），`raw` 是原文片段——段二的写回按偏移精确回填。
    """
    source = _strip_comments(text)
    blocks: list[dict] = []
    buffer: list[str] = []
    buffer_start = 0
    in_abstract = False
    index = 0
    counter = 0
    length = len(source)

    def flush() -> None:
        nonlocal buffer, buffer_start
        raw = "".join(buffer)
        chunk = raw.strip()
        start = buffer_start + (len(raw) - len(raw.lstrip()))
        end = buffer_start + len(raw) - (len(raw) - len(raw.rstrip()))
        buffer = []
        buffer_start = index
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
            "start": start, "end": end, "raw": text[start:end],
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
                    "start": index, "end": index + end,
                    "raw": text[index:index + end],
                })
                index += end
                continue
        if char == "\n" and source[index:index + 2] == "\n":
            flush()
            index += 2
            continue
        if not buffer:
            buffer_start = index
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
    """一个盘的章节内容：块列表 + 标题（含配对盘的英文标题）。

    封面摘要块（`cover-abstract`）也在这份列表里：渲染层与写回层共用同一套
    闭包定位——摘要在哪个文件就定位在哪个文件（根文件的 abstract 环境，
    或独立节文件 `sections/00_abstract.tex`）。
    """
    root = Path(path)
    paired = _paired_titles(root) if lang == "zh" else {}
    blocks: list[dict] = []
    for name, text in _section_files(root):
        stem = Path(name).stem
        for block in render_tex(text, stem=stem):
            block["file"] = name
            if block["kind"] == "section" and not block["title_en"]:
                block["title_en"] = paired.get(stem, "")
            blocks.append(block)
    _attach_cover_abstract(root, blocks)
    return {"blocks": blocks, "count": len(blocks)}


# ---------------------------------------------------------------- 封面摘要（渲染闭包）

#: 封面摘要块的固定 id（前端按这个 id 就地编辑）。
ABSTRACT_BLOCK_ID = "cover-abstract"

_ABSTRACT_BEGIN_RE = re.compile(r"\\begin\s*\{abstract\}")
_ABSTRACT_END_RE = re.compile(r"\\end\s*\{abstract\}")

#: 独立摘要节文件的名字特征（`00_abstract.tex` / `abstract.tex` / `00-abstract.tex`…）。
_ABSTRACT_FILE_RE = re.compile(r"^(?:[\d_.-]*[-_])?abstract$", re.IGNORECASE)


def abstract_env_spans(text: str) -> list[tuple[int, int]]:
    """文件里所有 `abstract` 环境的内容区间（绝对偏移，平衡配对）。

    配对时数嵌套：`\\begin{abstract} … \\begin{abstract} … \\end{abstract} …
    \\end{abstract}` 里，外层环境的区间**包含**内层那一段。
    """
    spans: list[tuple[int, int]] = []
    pos = 0
    while True:
        begin = _ABSTRACT_BEGIN_RE.search(text, pos)
        if not begin:
            break
        depth = 1
        scan = begin.end()
        end_pos = None
        while depth > 0:
            nested = _ABSTRACT_BEGIN_RE.search(text, scan)
            closing = _ABSTRACT_END_RE.search(text, scan)
            if closing is None:
                break
            if nested is not None and nested.start() < closing.start():
                depth += 1
                scan = nested.end()
                continue
            depth -= 1
            end_pos = closing.start()
            scan = closing.end()
        if end_pos is None:
            break
        spans.append((begin.end(), end_pos))
        pos = scan
    return spans


def abstract_content_range(text: str) -> tuple[int, int] | None:
    """摘要**散文**的内容区间（绝对偏移，不含环境标记）。

    取最内层 `abstract` 环境的内容（嵌套时外层区间含内层，故要往里再挖一层）；
    找不到环境返回 None。
    """
    spans = abstract_env_spans(text)
    if not spans:
        return None
    start, end = spans[-1]
    inner = text[start:end]
    nested = abstract_env_spans(inner)
    if nested:
        s2, e2 = nested[-1]
        return (start + s2, start + e2)
    return (start, end)


def abstract_env_span(text: str) -> tuple[int, int, int, int] | None:
    """摘要散文区间 + 两头空白长度。

    返回 (内容起点, 内容终点, 前导空白长度, 尾部空白长度)；找不到返回 None。
    内容两头的空白另算——写回时照原样保留，版式不塌。
    """
    rng = abstract_content_range(text)
    if rng is None:
        return None
    start, end = rng
    core = text[start:end]
    lead = len(core) - len(core.lstrip())
    trail = len(core) - len(core.rstrip())
    return (start, end, lead, trail)


def abstract_prose(text: str) -> str:
    """提交文本里的摘要散文。

    提交文本若**自带** `abstract` 环境（整段环境甚至整份文件被回传），只取
    环境内的散文：写回时不再包一层环境，也不重生成环境外的标记行
    （`% FACTS-USED` 之类属于文件原有结构，不在编辑块范围内）。
    没有环境时原样返回。
    """
    rng = abstract_content_range(text)
    if rng is None:
        return text
    start, end = rng
    return text[start:end].strip()



def _looks_like_abstract_file(rel: str) -> bool:
    """这个节文件是不是「独立摘要节」（`00_abstract.tex` 这种）。"""
    stem = Path(rel).stem
    if _ABSTRACT_FILE_RE.match(stem):
        return True
    return False


def cover_abstract_block(path: str | Path) -> dict | None:
    """封面摘要块：走渲染闭包定位（file/start/end/raw 一起给）。

    两种布局都认：

    1. **节文件式**（sectioned）：摘要是独立节文件 `sections/00_abstract.tex`
       （内容自带 `\\begin{abstract}…\\end{abstract}`），经 `\\input` 装配；
    2. **根文件式**：摘要在根文件 `main.tex` 的 `abstract` 环境里。

    找不到就返回 None（前端据此不渲染封面摘要区）。
    """
    root = Path(path)
    # 1) 闭包里的节文件：优先「像摘要文件」的，其次任何带 abstract 环境的。
    fallback = None
    for name, text in _section_files(root):
        span = abstract_env_span(text)
        if not span:
            continue
        start, end, lead, trail = span
        info = {"id": ABSTRACT_BLOCK_ID, "kind": "abstract", "file": name,
                "start": start + lead, "end": end - trail,
                "raw": text[start + lead:end - trail], "title": "",
                "level": 0, "html": "", "title_en": ""}
        if _looks_like_abstract_file(name):
            return info
        if fallback is None:
            fallback = info
    if fallback is not None:
        return fallback
    # 2) 根文件（main.tex）的 abstract 环境（sectioned 布局下根文件被闭包剔除）
    rel, root_tex = _root_tex_rel_and_path(root)
    if root_tex is None:
        return None
    try:
        text = root_tex.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    span = abstract_env_span(text)
    if not span:
        return None
    start, end, lead, trail = span
    return {"id": ABSTRACT_BLOCK_ID, "kind": "abstract", "file": rel,
            "start": start + lead, "end": end - trail,
            "raw": text[start + lead:end - trail], "title": "",
            "level": 0, "html": "", "title_en": ""}


def _root_tex_rel_and_path(root: Path) -> tuple[str, Path | None]:
    """根文件（配置里的 `root_tex`，没有就 `main.tex`）：相对名与绝对路径。"""
    from ..config import ConfigError, load_config

    rel = ""
    try:
        cfg = load_config(root)
        rel = str(getattr(cfg, "root_tex", "") or "").strip()
    except (ConfigError, OSError, ValueError):
        rel = ""
    rel = rel or "main.tex"
    target = root / rel
    return rel, (target if target.is_file() else None)


def _attach_cover_abstract(root: Path, blocks: list[dict]) -> None:
    """把封面摘要块挂进块列表（固定 id `cover-abstract`）。

    闭包里本来就有 abstract 块 → 就地换 id（渲染层与写回层同一套定位）；
    没有（摘要在根文件里）→ 补一块进来。
    """
    cover = cover_abstract_block(root)
    if not cover:
        return
    for block in blocks:
        if (block.get("kind") == "abstract"
                and block.get("file") == cover["file"]
                and block.get("start") == cover["start"]):
            block["id"] = cover["id"]
            return
    blocks.insert(0, cover)



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
    subtitle = _tex_subtitle(root)
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
        "subtitle": subtitle,
        "lang": lang or disk_language(root.name),
        "facts": facts,
        "sections": sections,
        "last_build": built,
        "last_build_file": built_file,
    }
