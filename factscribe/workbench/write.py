# -*- coding: utf-8 -*-
"""工作台段二：写回与章节管理（唯一的落盘入口）。

前端与 CLI 都只调这一层。硬规矩四条：

1. **只写正文**：只写盘里 `sections/` 下的 `.tex`，以及根文件（`main.tex`）的
   装配行；`facts/`、`audit/`、`results/` 一律只读——事实账与证据链不归工作台管。
2. **原子写**：同目录写 `.tmp` 再 `rename` 覆盖；原文件权限原样保留；
   每次保存前把原文件复制成同目录 `.bak`（覆盖旧的，不堆叠）。
3. **保护面**（硬要求）：`\\fact{}`、`\\cite{}`、`\\ref{}` 等命令与其参数，
   以及与 `\\fact` 绑定的数字令牌，写回时原样保留——用户改散文改不掉它们。
   用户把芯片删掉了也不要紧：写回时按原文的相对次序补回来（见 `_rebuild`）。
4. **删除可逆**：删章节＝从装配移除＋把文件挪到 `sections/attic/`，不真删。

保护面的口径（写在这里，代码注释与文档同源）：

* **命令级**：凡是带参数的 LaTeX 命令（`\\fact`、`\\cite`、`\\ref`、`\\label`、
  `\\textbf`…）连同参数整体原样保留；
* **环境级**：`figure/table/tabular/equation/align/verbatim` 等整块保留；
  `abstract/itemize/enumerate` 只保留 `\\begin`/`\\end` 标记，里面照常可改；
* **数字级**：紧跟在 `\\fact{ID}` 标记前的那个数字（可以有空白或 `~`）＝
  **已绑定数字令牌**，原样保留；账本里同一条 fact 的 `value` 在本段里再出现
  也按绑定令牌处理。
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import ConfigError, load_config, load_facts
from .projects import (ABSTRACT_BLOCK_ID as _ABSTRACT_BLOCK_ID,
                       CONFIG_NAME, abstract_env_span as _abstract_env_span,
                       render_tex)

#: 客户端与本层之间的占位符（私用区字符，LaTeX 正文里不会出现）。
TOKEN_OPEN = "\ue000"
TOKEN_CLOSE = "\ue001"
TOKEN_RE = re.compile(TOKEN_OPEN + r"P(\d+)" + TOKEN_CLOSE)

#: 章节删除后的归档目录名（放在章节文件所在目录下）。
ATTIC_DIR = "attic"

#: 整块保留的环境（内容不是散文）。
SOLID_ENVS = {
    "figure", "figure*", "table", "table*", "tabular", "tabular*",
    "equation", "equation*", "align", "align*", "gather", "multline",
    "verbatim", "lstlisting", "minted", "tikzpicture", "thebibliography",
}

#: 命令类别：决定芯片上的标签与图标。
CMD_KIND = {
    "fact": "fact",
    "label": "ref", "ref": "ref", "eqref": "ref", "pageref": "ref",
    "autoref": "ref", "cref": "ref", "Cref": "ref", "crefrange": "ref",
    "vref": "ref", "nameref": "ref", "hyperref": "ref",
    "cite": "cite", "citep": "cite", "citet": "cite", "Cite": "cite",
    "citealp": "cite", "citealt": "cite", "citeauthor": "cite",
    "citeyear": "cite", "citeyearpar": "cite", "parencite": "cite",
    "textcite": "cite", "autocite": "cite", "footcite": "cite",
    "nocite": "cite",
}

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*(?:/\d+(?:[.,]\d+)*)?(?:\\?%)?")
_CMD_RE = re.compile(r"\\([A-Za-z@]+)\*?")
_INPUT_RE = re.compile(r"\\(input|include)\s*\{([^}]*)\}")


# ---------------------------------------------------------------- 段模型

@dataclass
class Segment:
    """一段：普通散文（kind=text）或保护面（kind=prot）。"""

    kind: str
    text: str
    index: int = -1
    label: str = ""


@dataclass
class Block:
    """一次编辑的落点：哪个文件、哪一段、原文是什么。"""

    file: str
    block_id: str
    kind: str
    start: int
    end: int
    raw: str
    title: str = ""
    segments: list = field(default_factory=list)


# ---------------------------------------------------------------- 保护面扫描

def _match_braces(text: str, start: int, end: int) -> int:
    """text[start] == '{' → 返回配对 '}' 之后的下标（找不到就返回 end）。"""
    depth = 0
    index = start
    while index < end:
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return end


def _parse_command(text: str, start: int, end: int):
    """解析一个命令：返回 (名字, 参数区间列表, 结束下标)；不是命令就 None。"""
    match = _CMD_RE.match(text, start)
    if not match or match.end() > end:
        return None
    name = match.group(1)
    index = match.end()
    while index < end and text[index] in " \t":
        index += 1
    if index < end and text[index] == "[":
        close = text.find("]", index)
        index = end if close < 0 else close + 1
    args: list[tuple[int, int]] = []
    while True:
        probe = index
        while probe < end and text[probe] in " \t":
            probe += 1
        if probe < end and text[probe] == "{":
            stop = _match_braces(text, probe, end)
            args.append((probe, stop))
            index = stop
            continue
        break
    return name, args, index


def _env_name(text: str, args: list) -> str:
    if not args:
        return ""
    start, stop = args[0]
    return text[start + 1:stop - 1].strip() if stop - 1 > start else ""


def _norm_number(text: str) -> str:
    """数字归一：去空白、去千分位逗号、去 `\\%` 的反斜杠。"""
    out = str(text or "").replace("\\", "")
    out = re.sub(r"(?<=\d),(?=\d)", "", out)
    return out.replace(" ", "")


def scan(text: str, bound_values=frozenset()) -> list[Segment]:
    """把一段 LaTeX 切成 [散文|保护面] 序列。

    `bound_values` 是账本里出现过的 fact value（归一后）；出现在本段里的
    同值数字按「已绑定数字令牌」处理。
    """
    segments = _scan_commands(text, 0, len(text))
    segments = _protect_numbers(segments, bound_values)
    index = 0
    out: list[Segment] = []
    for seg in segments:
        if seg.kind != "prot":
            out.append(seg)
            continue
        seg.index = index
        index += 1
        out.append(seg)
    return out


def _scan_commands(text: str, start: int, end: int) -> list[Segment]:
    """第一遍：命令 / 数学 / 环境层面的保护面。"""
    out: list[Segment] = []
    buffer: list[str] = []
    index = start

    def flush() -> None:
        if buffer:
            out.append(Segment("text", "".join(buffer)))
            buffer.clear()

    while index < end:
        char = text[index]
        if char == "\\":
            parsed = _parse_command(text, index, end)
            if parsed is None:
                # 不是命令＝转义字符（\%、\\、\&、\$_…）：反斜杠连下一个字符
                # 一起当普通文本。**否则 \% 会被当成注释开头**，把这一行
                # 剩下的东西（连同里面的 \cite）整段吞成「注释」保护面。
                buffer.append(char)
                index += 1
                if index < end:
                    buffer.append(text[index])
                    index += 1
                continue
            name, args, stop = parsed
            # 环境：整块保留 or 只留标记。
            if name == "begin" and args:
                env = _env_name(text, args)
                close = _find_env_end(text, stop, end, env)
                if env in SOLID_ENVS and close is not None:
                    flush()
                    out.append(Segment("prot", text[index:close], label="env"))
                    index = close
                    continue
            flush()
            label = CMD_KIND.get(name, "cmd" if args else "")
            out.append(Segment("prot", text[index:stop], label=label or "cmd"))
            index = stop
            continue
        if char == "$":
            stop = _find_math_end(text, index, end)
            if stop is not None:
                flush()
                out.append(Segment("prot", text[index:stop], label="math"))
                index = stop
                continue
        if char == "%":
            # 注释：整段留白（写回时原样保留，不让用户改坏注释）
            stop = text.find("\n", index)
            stop = end if stop < 0 else stop
            flush()
            out.append(Segment("prot", text[index:stop], label="comment"))
            index = stop
            continue
        buffer.append(char)
        index += 1
    flush()
    return out


def _find_math_end(text: str, start: int, end: int):
    """`$…$` / `\\[…\\]` / `\\(…\\)` 的结束下标；找不到返回 None。"""
    if text.startswith("\\[", start):
        stop = text.find("\\]", start + 2)
        return None if stop < 0 else stop + 2
    if text.startswith("\\(", start):
        stop = text.find("\\)", start + 2)
        return None if stop < 0 else stop + 2
    if text.startswith("$$", start):
        stop = text.find("$$", start + 2)
        return None if stop < 0 else stop + 2
    probe = start + 1
    while probe < end:
        if text[probe] == "\\":
            probe += 2
            continue
        if text[probe] == "$":
            return probe + 1
        probe += 1
    return None


def _find_env_end(text: str, start: int, end: int, env: str):
    """找 `\\end{env}` 的下标（从 start 起）。"""
    if not env:
        return None
    pattern = re.compile(r"\\end\s*\{" + re.escape(env) + r"\}")
    match = pattern.search(text, start, end)
    return match.end() if match else None


def _protect_numbers(segments: list[Segment], bound_values) -> list[Segment]:
    """第二遍：数字令牌。

    * 紧跟在 `\\fact{…}` 标记前的数字（中间只允许空白或 `~`）＝绑定令牌；
    * 账本里同条 fact 的 value 在本段再出现，也按绑定令牌处理。
    """
    values = {_norm_number(v) for v in (bound_values or ()) if str(v).strip()}
    out: list[Segment] = []
    for seg in segments:
        if seg.kind != "text":
            out.append(seg)
            continue
        out.append(seg)
    # 规则一：紧跟 fact 标记的数字。
    result: list[Segment] = []
    for seg in out:
        if seg.kind == "prot" and seg.label == "fact" and result:
            prev = result[-1]
            if prev.kind == "text":
                pieces = _split_trailing_number(prev.text)
                if pieces is not None:
                    before, number, after = pieces
                    result.pop()
                    if before:
                        result.append(Segment("text", before))
                    result.append(Segment("prot", number, label="num"))
                    if after:
                        result.append(Segment("text", after))
        result.append(seg)
    # 规则二：账本同值数字。
    final: list[Segment] = []
    for seg in result:
        if seg.kind != "text" or not values:
            final.append(seg)
            continue
        pieces: list[Segment] = []
        cursor = 0
        for match in _NUM_RE.finditer(seg.text):
            if _norm_number(match.group(0)) not in values:
                continue
            if match.start() > cursor:
                pieces.append(Segment("text", seg.text[cursor:match.start()]))
            pieces.append(Segment("prot", match.group(0), label="num"))
            cursor = match.end()
        if not pieces:
            final.append(seg)
            continue
        if cursor < len(seg.text):
            pieces.append(Segment("text", seg.text[cursor:]))
        final.extend(pieces)
    return final


def _split_trailing_number(text: str):
    """末尾是数字（后面只跟空白/波浪号）→ 返回 (前, 数字, 后)；否则 None。"""
    matches = list(_NUM_RE.finditer(text))
    if not matches:
        return None
    match = matches[-1]
    gap = text[match.end():]
    if gap.strip(" \t~ ") != "":
        return None
    return text[:match.start()], match.group(0), gap


# ---------------------------------------------------------------- 写回

def _rebuild(segments: list[Segment], client_text: str) -> tuple[str, list[str]]:
    """把客户端改后的文本与保护面拼回 LaTeX。

    返回 (新文本, 告警列表)。规则：

    * 客户端把某个保护面删了 → 按原文的相对次序**补回来**（改不掉）；
    * 客户端在散文里**原样抄回**原文的保护面 → 认回来（当成本来的那个，
      不当新写的），保证「保护面逐字相同」时写回是字节级一致的；
    * 客户端在散文里塞了**原文没有**的 `\\fact{…}`/`\\cite{…}`/`\\ref{…}` →
      **剥掉**（不许凭空造账本绑定），并记一条告警；
    * 客户端把保护面挪了位置 → 保留客户端的顺序（挪引用是合法的散文编辑）。
    """
    warnings: list[str] = []
    regions = [seg for seg in segments if seg.kind == "prot"]
    by_index = {seg.index: seg for seg in regions}

    parts = TOKEN_RE.split(client_text or "")
    # TOKEN_RE 有一个捕获组 → split 的结果是 [散文, 编号, 散文, 编号, …]：
    # 偶数位是散文，奇数位是保护面的编号。
    items: list[tuple[str, object]] = []
    seen: list[int] = []
    for position in range(0, len(parts), 2):
        free = parts[position]
        token = parts[position + 1] if position + 1 < len(parts) else None
        if free:
            # 先认回「原样抄回」的保护面，剩下的才当散文处理。
            for kind, value in _absorb_verbatim(free, regions, seen):
                if kind == "text":
                    clean, dropped = _strip_injected(value)
                    if dropped:
                        warnings.append(
                            "正文里新写的 %s 已被剥掉：工作台不让人凭空造账本绑定" % dropped)
                    if clean:
                        items.append(("text", clean))
                else:
                    items.append(("prot", value))
        if token is None:
            continue
        index = int(token)
        seg = by_index.get(index)
        if seg is None:
            continue
        if index in seen:
            warnings.append("同一个保护面被复制了一次，只保留第一处")
            continue
        seen.append(index)
        items.append(("prot", seg))

    # 缺失的保护面按原文位置补回来。
    missing = [seg for seg in regions if seg.index not in seen]
    for seg in missing:
        spot = _anchor_spot(segments, seg, items)
        if spot is None:
            position = len(items)
            for offset, item in enumerate(items):
                if item[0] == "prot" and item[1].index > seg.index:
                    position = offset
                    break
            items.insert(position, ("prot", seg))
        else:
            index, cut = spot
            text = str(items[index][1])
            items[index] = ("text", text[:cut])
            items.insert(index + 1, ("prot", seg))
            if text[cut:]:
                items.insert(index + 2, ("text", text[cut:]))
        warnings.append("被删掉的 %s 标记已按原文位置补回"
                        % (seg.label or "保护"))

    return "".join(item[1].text if item[0] == "prot" else str(item[1])
                   for item in items), warnings


def _anchor_spot(segments: list[Segment], seg: Segment,
                 items: list) -> tuple[int, int] | None:
    """被删掉的保护面补回到哪里：找原文里的锚（前一段散文的尾巴）。

    返回 (条目下标, 该条目内的切分位置)；找不到锚就返回 None（调用方退回
    「按保护面相对次序」插到下一个保护面之前）。

    锚点要连**它后面的空白**一起找：原文里芯片紧跟在这段空白之后，漏掉
    空白会把芯片插到空白前面（位置差一格：`见\\cite{x} 。`）。
    """
    anchor = ""
    for item in segments:
        if item is seg:
            break
        if item.kind == "text":
            anchor = item.text
    stripped = anchor.strip()
    tail = stripped[-24:] if len(stripped) > 24 else stripped
    if not tail:
        return None
    gap = anchor[len(anchor.rstrip()):]
    current = "".join(item[1].text if item[0] == "prot" else str(item[1])
                      for item in items)
    for probe in (tail + gap, tail):
        spot = current.rfind(probe)
        if spot < 0:
            continue
        target = spot + len(probe)
        offset = 0
        for index, item in enumerate(items):
            if item[0] != "text":
                length = len(item[1].text)
                if offset < target < offset + length:
                    return None          # 锚点落在保护面里：别切它
                offset += length
                continue
            length = len(str(item[1]))
            if offset + length > target:
                return index, max(0, target - offset)
            offset += length
    return None


def _absorb_verbatim(text: str, regions: list[Segment],
                     seen: list[int]) -> list[tuple[str, object]]:
    """把散文里**原样抄回**的保护面认回来。

    客户端有时不用占位符，而是把原文的保护面（`\\fact{A1}`、`\\cite{k}`…）
    原样抄回正文。这样的回写必须认成「原来的那个保护面」——若当成
    「凭空新写的命令」剥掉，再把原文的保护面补回来，就会写出重复内容
    （残渣）。认回来的判据是**逐字相同**：与某个原文保护面完全一致。

    返回 [("text", 片段) | ("prot", 保护面)]，按出现顺序。已被占位符认领过
    的保护面（`seen`）不再重复认领——多出来的那份照旧按「新写的」剥掉。
    """
    out: list[tuple[str, object]] = []
    buffer: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        best: Segment | None = None
        for seg in regions:
            if seg.index in seen or not seg.text:
                continue
            if text.startswith(seg.text, index):
                # 同一位置命中多个时取最长的（短的可能嵌在长的里面）。
                if best is None or len(seg.text) > len(best.text):
                    best = seg
        if best is not None:
            if buffer:
                out.append(("text", "".join(buffer)))
                buffer.clear()
            out.append(("prot", best))
            seen.append(best.index)
            index += len(best.text)
            continue
        buffer.append(text[index])
        index += 1
    if buffer:
        out.append(("text", "".join(buffer)))
    return out


_INJECT_RE = re.compile(r"\\(fact|cite[a-zA-Z]*|ref|label|eqref|pageref|"
                        r"autoref|cref|Cref|hyperref)\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}")


def _strip_injected(text: str) -> tuple[str, str]:
    """剥掉正文里新写的保护类命令；返回 (剩下的文本, 剥掉的命令名)。"""
    dropped: list[str] = []

    def kill(match: re.Match) -> str:
        dropped.append("\\" + match.group(1))
        return ""

    return _INJECT_RE.sub(kill, text), "、".join(dropped)


def _balanced_ok(text: str) -> bool:
    """花括号配平（写回前自检：写坏了不许落盘）。"""
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
        index += 1
    return depth == 0


def atomic_write(path: Path, text: str, backup: bool = True) -> dict:
    """原子写：同目录 `.tmp` → `rename`；保留原权限；先存 `.bak`。

    `.bak` 是「上一次保存前」的原文，同目录、固定名（覆盖旧的，不堆叠）。
    """
    path = Path(path)
    data = text.encode("utf-8")
    mode = None
    backup_path = ""
    if path.exists():
        try:
            mode = path.stat().st_mode & 0o7777
        except OSError:
            mode = None
        if backup:
            backup_path = str(path.with_name(path.name + ".bak"))
            tmp_bak = path.with_name(path.name + ".bak.tmp-%d" % os.getpid())
            try:
                shutil.copyfile(str(path), str(tmp_bak))
                if mode is not None:
                    os.chmod(str(tmp_bak), mode)
                os.replace(str(tmp_bak), str(backup_path))
            finally:
                if tmp_bak.exists():
                    try:
                        tmp_bak.unlink()
                    except OSError:
                        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("%s.tmp-%d" % (path.name, os.getpid()))
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(str(tmp), mode)
        os.replace(str(tmp), str(path))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return {"path": str(path), "backup": backup_path}


# ---------------------------------------------------------------- 段落定位

def _bound_values(disk_root: Path) -> set[str]:
    """盘里事实账上的 value（用于认「已绑定数字令牌」）。"""
    try:
        cfg = load_config(disk_root)
        facts = load_facts(cfg)
    except Exception:  # noqa: BLE001 - 账读不到就不按账认数字
        return set()
    return {fact.value for fact in facts if getattr(fact, "value", "")}


def _safe_section_file(disk_root: Path, rel: str) -> Path:
    """只许写盘里的**章节正文文件**。

    四道闸（段二硬约束「只写 sections 外的账本文件不许碰」）：

    1. 相对路径：不许绝对路径、不许 `..`；
    2. 不许越出盘根；
    3. 只写 `.tex`；
    4. 只写 `sections/` 下的（或配置 `sections` glob 命中的）文件——
       `facts/`、`audit/`、`results/` 一律只读。
    """
    from pathlib import PurePosixPath

    raw = str(rel or "").strip()
    pure = PurePosixPath(raw.replace("\\", "/"))
    if not raw or pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise ConfigError("章节文件路径不合法：%s" % rel,
                          code="SECTION_PATH_INVALID")
    root = disk_root.resolve()
    target = disk_root.joinpath(*[p for p in pure.parts if p not in ("", ".")])
    try:
        inside = target.resolve().relative_to(root)
    except (OSError, ValueError):
        raise ConfigError("章节文件越出项目根：%s" % rel,
                          code="SECTION_PATH_INVALID")
    if target.suffix.lower() != ".tex":
        raise ConfigError("只写 .tex 章节文件：%s" % rel,
                          code="SECTION_PATH_INVALID")
    parts = inside.parts
    if parts and parts[0] in ("facts", "audit", "results", "runs"):
        raise ConfigError("账本与产物目录只读：%s" % rel,
                          code="SECTION_READONLY")
    glob = ""
    try:
        cfg = load_config(disk_root)
        glob = str(getattr(cfg, "sections_glob", "") or "")
    except (ConfigError, OSError, ValueError):
        glob = ""
    in_sections = bool(parts) and parts[0] == "sections"
    matched = False
    if glob:
        import fnmatch
        matched = fnmatch.fnmatchcase(inside.as_posix(), glob)
    if not (in_sections or matched):
        raise ConfigError("只写 sections/ 下的章节文件：%s" % rel,
                          code="SECTION_PATH_INVALID")
    return target


# ---------------------------------------------------------------- 摘要（封面）

#: 摘要块的固定 id（封面摘要区只有一个摘要，前端按这个 id 就地编辑）。
#: 与渲染层同源（projects.ABSTRACT_BLOCK_ID）——渲染与写回共用一套闭包定位。
ABSTRACT_BLOCK_ID = _ABSTRACT_BLOCK_ID

#: `abstract` 环境的内容区间：与渲染层同一份实现（projects.abstract_env_span）。
_abstract_span = _abstract_env_span


def _root_tex_file(disk_root: Path) -> tuple[str, Path]:
    """根文件（配置里的 `root_tex`，没有就 `main.tex`）——相对名与绝对路径。

    摘要住在根文件的 `abstract` 环境里；根文件**不在** `sections/` 下，
    所以它自己一套闸（不许越出盘根、不许写账本目录、只写 .tex）。
    """
    rel = ""
    try:
        cfg = load_config(disk_root)
        rel = str(getattr(cfg, "root_tex", "") or "").strip()
    except (ConfigError, OSError, ValueError):
        rel = ""
    rel = rel or "main.tex"
    from pathlib import PurePosixPath

    pure = PurePosixPath(rel.replace("\\", "/"))
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise ConfigError("根文件路径不合法：%s" % rel,
                          code="SECTION_PATH_INVALID")
    root = Path(disk_root).resolve()
    target = Path(disk_root).joinpath(*[p for p in pure.parts if p not in ("", ".")])
    try:
        inside = target.resolve().relative_to(root)
    except (OSError, ValueError):
        raise ConfigError("根文件越出项目根：%s" % rel,
                          code="SECTION_PATH_INVALID")
    if target.suffix.lower() != ".tex":
        raise ConfigError("根文件必须是 .tex：%s" % rel,
                          code="SECTION_PATH_INVALID")
    parts = inside.parts
    if parts and parts[0] in ("facts", "audit", "results", "runs"):
        raise ConfigError("账本与产物目录只读：%s" % rel,
                          code="SECTION_READONLY")
    return inside.as_posix(), target


def abstract_block(disk_root: Path) -> Block:
    """封面摘要块：**走渲染闭包**定位——摘要在哪个文件就定位在哪个文件。

    两种布局都认：

    1. **节文件式**（sectioned）：摘要是独立节文件 `sections/00_abstract.tex`
       （自带 `\\begin{abstract}…\\end{abstract}`），经 `\\input` 装配；
    2. **根文件式**：摘要在根文件 `main.tex` 的 `abstract` 环境里。
    """
    from .projects import cover_abstract_block

    info = cover_abstract_block(disk_root)
    if not info:
        raise ConfigError("这个盘里找不到摘要（既没有 abstract 环境，也没有独立的摘要节文件）",
                          code="ABSTRACT_MISSING")
    return Block(file=info["file"], block_id=ABSTRACT_BLOCK_ID, kind="abstract",
                 start=info["start"], end=info["end"], raw=info["raw"],
                 title="摘要")


def _writable_target(disk_root: Path, rel: str) -> Path:
    """摘要所在文件的写闸：根文件走根文件闸，节文件走段二的章节文件闸。"""
    root_rel, root_path = _root_tex_file(disk_root)
    if rel == root_rel:
        return root_path
    return _safe_section_file(disk_root, rel)


def save_abstract(disk_root: Path, client_text: str) -> dict:
    """把改后的摘要写回它所在的那个文件。

    走段二同一条保护通道：保护面（`\\fact{}` 等）原样保留、删了按原位补回、
    花括号不配平不落盘、原子写、保存前留 `.bak`。
    """
    block = abstract_block(disk_root)
    segments = scan(block.raw, _bound_values(disk_root))
    new_raw, warnings = _rebuild(segments, client_text)
    if not _balanced_ok(new_raw):
        raise ConfigError("摘要的花括号不配平（写下去会编不过），没有保存。",
                          code="EDIT_UNBALANCED")
    rel = block.file
    path = _writable_target(disk_root, rel)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError("读不到摘要所在文件：%s（%s）" % (rel, exc),
                          code="SECTION_MISSING")
    span = _abstract_span(text)
    if span is None:
        raise ConfigError("摘要已经被挪走了（或文件变了）：%s，请刷新页面重试" % rel,
                          code="ABSTRACT_MISSING")
    start, end, lead, trail = span
    new_text = text[:start + lead] + new_raw + text[end - trail:]
    result = atomic_write(path, new_text)
    return {"ok": True, "file": rel, "block": ABSTRACT_BLOCK_ID,
            "before": block.raw, "after": new_raw,
            "backup": result["backup"], "warnings": warnings}



def find_block(disk_root: Path, rel_file: str, block_id: str) -> Block:
    """按 id 找到一段：返回它所在文件、偏移与原文。"""
    path = _safe_section_file(disk_root, rel_file)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError("读不到章节文件：%s（%s）" % (rel_file, exc),
                          code="SECTION_MISSING")
    for block in render_tex(text, stem=Path(rel_file).stem):
        if block["id"] == block_id:
            return Block(file=rel_file, block_id=block_id, kind=block["kind"],
                         start=block["start"], end=block["end"],
                         raw=block.get("raw", ""), title=block.get("title", ""))
    raise ConfigError("这一段已经不在文件里了（请刷新页面）：%s" % block_id,
                      code="BLOCK_MISSING")


def editable_model(disk_root: Path, block: Block) -> dict:
    """给前端的可编辑模型：散文 + 保护面芯片。"""
    segments = scan(block.raw, _bound_values(disk_root))
    plain = ""
    chips: list[dict] = []
    for seg in segments:
        if seg.kind == "text":
            plain += seg.text
            continue
        token = "%sP%d%s" % (TOKEN_OPEN, seg.index, TOKEN_CLOSE)
        plain += token
        chips.append({"i": seg.index, "label": seg.label,
                      "raw": seg.text, "display": _display(seg)})
    return {"id": block.block_id, "file": block.file, "kind": block.kind,
            "title": block.title, "plain": plain, "chips": chips,
            "raw": block.raw}


def _display(seg: Segment) -> str:
    """芯片上的字：\\fact{A1} → 「✓ A1」，\\cite{k} → 「[k]」，数字 → 数字。"""
    text = seg.text
    if seg.label == "fact":
        match = re.match(r"\\fact\s*\{([^{}]*)\}", text)
        if match:
            return "✓ %s" % match.group(1).strip()
        return "✓"
    if seg.label in ("cite", "ref"):
        match = re.search(r"\{([^{}]*)\}", text)
        if match:
            return "[%s]" % match.group(1).strip()
        return text
    if seg.label == "num":
        return text
    if seg.label == "env":
        return "⟨%s⟩" % (re.search(r"\{([^{}]*)\}", text).group(1)
                         if re.search(r"\{([^{}]*)\}", text) else "env")
    if len(text) > 18:
        return text[:17] + "…"
    return text


def save_block(disk_root: Path, rel_file: str, block_id: str,
               client_text: str) -> dict:
    """把改后的段落写回原文件。"""
    block = find_block(disk_root, rel_file, block_id)
    segments = scan(block.raw, _bound_values(disk_root))
    new_raw, warnings = _rebuild(segments, client_text)
    if not _balanced_ok(new_raw):
        raise ConfigError("这段的花括号不配平（写下去会编不过），没有保存。",
                          code="EDIT_UNBALANCED")
    path = _safe_section_file(disk_root, rel_file)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError("读不到章节文件：%s（%s）" % (rel_file, exc),
                          code="SECTION_MISSING")
    new_text = text[:block.start] + new_raw + text[block.end:]
    result = atomic_write(path, new_text)
    return {"ok": True, "file": rel_file, "block": block_id,
            "before": block.raw, "after": new_raw,
            "backup": result["backup"], "warnings": warnings}


# ---------------------------------------------------------------- 装配

def assembly_file(disk_root: Path, cfg=None) -> Path:
    """装配文件（根文件）：配置里的 `root_tex`，没有就 `main.tex`。"""
    rel = ""
    if cfg is not None:
        rel = str(getattr(cfg, "root_tex", "") or "").strip()
    rel = rel or "main.tex"
    return disk_root / rel


def read_assembly(disk_root: Path, cfg=None) -> dict:
    """读装配：main.tex 里 `\\input`/`\\include` 的章节列表。"""
    path = assembly_file(disk_root, cfg)
    if not path.is_file():
        return {"file": "", "entries": []}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"file": str(path), "entries": []}
    base = path.parent
    entries: list[dict] = []
    for number, line in enumerate(text.splitlines()):
        for match in _INPUT_RE.finditer(line):
            target = match.group(2).strip()
            if not target or "\\" in target or "#" in target:
                continue
            candidate = base / target
            if not candidate.is_file() and candidate.with_suffix(".tex").is_file():
                candidate = candidate.with_suffix(".tex")
            try:
                rel = candidate.resolve().relative_to(disk_root.resolve()).as_posix()
            except (OSError, ValueError):
                continue
            entries.append({"rel": rel, "target": target, "line": number,
                            "raw": line, "title": _section_title(candidate)})
    return {"file": str(path), "entries": entries}


def _section_title(path: Path) -> str:
    """章节文件的一级标题（给目录管理显示）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    for block in render_tex(text, stem=path.stem):
        if block["kind"] == "section" and block.get("title"):
            return block["title"]
    return ""


def _rewrite_assembly(path: Path, entries: list[dict], text: str) -> str:
    """按新的条目顺序重写装配文件（保持其余行原样）。

    槽位＝原来那些条目所在的行号（升序）；第 i 个新条目写进第 i 个槽位，
    这样调序只动装配行，不动文件里的其它内容。
    """
    lines = text.splitlines()
    slots = sorted(entry["line"] for entry in entries)
    for index, entry in enumerate(entries):
        if index >= len(slots):
            break
        number = slots[index]
        if number >= len(lines):
            continue
        original = lines[number]
        cmd = "\\input" if "\\input" in original else "\\include"
        lines[number] = "%s{%s}" % (cmd, entry["target"])
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def move_section(disk_root: Path, rel: str, direction: str) -> dict:
    """调序：把某节在装配里往上/往下挪一格。"""
    if direction not in ("up", "down"):
        raise ConfigError("调序只能是 up 或 down", code="ORDER_INVALID")
    cfg = _safe_config(disk_root)
    assembly = read_assembly(disk_root, cfg)
    path = Path(assembly["file"]) if assembly["file"] else None
    if path is None or not path.is_file():
        raise ConfigError("这个盘没有装配文件（%s），调不了序"
                          % assembly_file(disk_root, cfg).name,
                          code="ASSEMBLY_MISSING")
    entries = assembly["entries"]
    index = next((i for i, e in enumerate(entries) if e["rel"] == rel), None)
    if index is None:
        raise ConfigError("装配里没有这一节：%s" % rel, code="SECTION_NOT_INCLUDED")
    other = index - 1 if direction == "up" else index + 1
    if other < 0 or other >= len(entries):
        return {"ok": True, "moved": False, "order": [e["rel"] for e in entries]}
    entries[index], entries[other] = entries[other], entries[index]
    text = path.read_text(encoding="utf-8")
    new_text = _rewrite_assembly(path, entries, text)
    result = atomic_write(path, new_text)
    return {"ok": True, "moved": True, "order": [e["rel"] for e in entries],
            "backup": result["backup"], "file": str(path)}


def delete_section(disk_root: Path, rel: str) -> dict:
    """删节：从装配移除 + 把文件挪到 `attic/`（可逆，不真删）。"""
    cfg = _safe_config(disk_root)
    assembly = read_assembly(disk_root, cfg)
    path = Path(assembly["file"]) if assembly["file"] else None
    if path is None or not path.is_file():
        raise ConfigError("这个盘没有装配文件（%s），删不了节"
                          % assembly_file(disk_root, cfg).name,
                          code="ASSEMBLY_MISSING")
    entries = assembly["entries"]
    index = next((i for i, e in enumerate(entries) if e["rel"] == rel), None)
    if index is None:
        raise ConfigError("装配里没有这一节：%s" % rel, code="SECTION_NOT_INCLUDED")
    source = disk_root / rel
    attic_dir = source.parent / ATTIC_DIR
    attic_dir.mkdir(parents=True, exist_ok=True)
    attic = attic_dir / source.name
    if attic.exists():
        attic.unlink()
    moved = False
    if source.is_file():
        shutil.move(str(source), str(attic))
        moved = True
    lines = path.read_text(encoding="utf-8").splitlines()
    dropped = entries.pop(index)
    if 0 <= dropped["line"] < len(lines):
        lines.pop(dropped["line"])
    text = "\n".join(lines) + "\n"
    result = atomic_write(path, text)
    return {"ok": True, "removed": rel, "attic": str(attic),
            "moved": moved, "backup": result["backup"],
            "order": [e["rel"] for e in entries]}


def create_section(disk_root: Path, title: str, slug: str = "",
                   after: str = "") -> dict:
    """新建一节：建 `sections/NN-slug.tex` ＋ 挂进装配。"""
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ConfigError("新章节要有个标题", code="SECTION_TITLE_MISSING")
    cfg = _safe_config(disk_root)
    sections_dir = disk_root / "sections"
    if not sections_dir.is_dir():
        raise ConfigError("这个盘没有 sections/ 目录，建不了节",
                          code="SECTIONS_DIR_MISSING")
    stem = _slugify(slug or clean_title)
    numbers = []
    for item in sections_dir.glob("*.tex"):
        head = item.stem.split("-", 1)[0]
        if head.isdigit():
            numbers.append(int(head))
    number = (max(numbers) + 1) if numbers else 1
    name = "%02d-%s.tex" % (number, stem)
    target = sections_dir / name
    if target.exists():
        raise ConfigError("这一节已经存在：%s" % name, code="SECTION_EXISTS")
    content = "\\section{%s}\n\n" % clean_title
    atomic_write(target, content, backup=False)
    assembly = read_assembly(disk_root, cfg)
    path = Path(assembly["file"]) if assembly["file"] else None
    if path is None or not path.is_file():
        return {"ok": True, "file": str(target), "rel": target.name,
                "assembled": False}
    text = path.read_text(encoding="utf-8")
    line = "\\input{%s}" % target.relative_to(disk_root).as_posix()[:-len(".tex")]
    entries = assembly["entries"]
    position = len(entries)
    if after:
        for index, entry in enumerate(entries):
            if entry["rel"] == after:
                position = index + 1
                break
    lines = text.splitlines()
    insert_at = None
    if entries and position > 0:
        insert_at = entries[position - 1]["line"] + 1
    else:
        insert_at = _before_end_document(lines)
    lines.insert(insert_at, line)
    new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    result = atomic_write(path, new_text)
    return {"ok": True, "file": str(target),
            "rel": target.relative_to(disk_root).as_posix(),
            "assembled": True, "backup": result["backup"]}


def _before_end_document(lines: list[str]) -> int:
    for index in range(len(lines) - 1, -1, -1):
        if "\\end{document}" in lines[index]:
            return index
    return len(lines)


def _slugify(text: str) -> str:
    """章节文件名：只留 ASCII 字母数字与短横线；中文标题退回 `section`。"""
    out = re.sub(r"[^A-Za-z0-9]+", "-", str(text or "")).strip("-").lower()
    return out or "section"


def _safe_config(disk_root: Path):
    try:
        return load_config(disk_root)
    except (ConfigError, OSError, ValueError):
        return None


# ---------------------------------------------------------------- 项目级配置

def _toml_value(text: str) -> str:
    """TOML 基本字符串（与 config 的迷你解析器兼容的最小转义集）。"""
    out = (str(text or "")
           .replace("\\", "\\\\")
           .replace('"', '\\"')
           .replace("\n", "\\n")
           .replace("\r", "\\r")
           .replace("\t", "\\t"))
    return '"%s"' % out


def read_table(path: Path, table: str) -> dict:
    """读 factscribe.toml 里某张表（读不到就空表）。"""
    from ..config import load_toml
    try:
        data = load_toml(path)
    except Exception:  # noqa: BLE001 - 坏配置当空表
        return {}
    value = data.get(table)
    return value if isinstance(value, dict) else {}


def rewrite_table(path: Path, table: str, values: dict) -> None:
    """改写 factscribe.toml 里某张表的给定键；别的行一个字都不动。

    `values` 的值是**排版好的 TOML 字面量**（字符串带引号）。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    start = None
    end = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("["):
            continue
        if start is None:
            if stripped == "[%s]" % table:
                start = index + 1
            continue
        end = index
        break
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("[%s]" % table)
        for key, value in values.items():
            lines.append("%s = %s" % (key, value))
    else:
        pending = dict(values)
        section: list[str] = []
        for line in lines[start:end]:
            match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", line)
            key = match.group(1) if match else ""
            if key in pending:
                section.append("%s = %s" % (key, pending.pop(key)))
            else:
                section.append(line)
        for key, value in pending.items():
            section.append("%s = %s" % (key, value))
        lines[start:end] = section
    atomic_write(path, "\n".join(lines).rstrip("\n") + "\n")


def workbench_config(disk_root: Path) -> dict:
    """项目级工作台配置（factscribe.toml 的 `[workbench]` 表）。"""
    path = disk_root / CONFIG_NAME
    if not path.is_file():
        return {}
    return read_table(path, "workbench")


def save_workbench_config(disk_root: Path, values: dict) -> None:
    """写 `[workbench]` 表（原子写 + .bak）。"""
    path = disk_root / CONFIG_NAME
    if not path.is_file():
        raise ConfigError("这个项目没有 %s" % CONFIG_NAME, code="PROJECT_INVALID")
    literals = {key: _toml_value(value) for key, value in values.items()}
    rewrite_table(path, "workbench", literals)


def touch_opened(disk_root: Path) -> dict:
    """记「最近打开」时间（写进项目配置的 `[workbench].last_opened`）。"""
    when = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    values = workbench_config(disk_root)
    values["last_opened"] = when
    save_workbench_config(disk_root, values)
    return {"last_opened": when}


def create_paper_project(root: Path, *, slug: str, title: str,
                         langs=("en",), journal: str = "",
                         template: str = "", question: str = "",
                         project_dir: str = "",
                         reports_dir: str = "") -> dict:
    """新建论文项目：在 `root` 下落目录骨架（每个语言盘一个目录）。

    骨架复用 `factscribe init` 的模板（`scaffold.init_project`），再补
    `[workbench]` 表：项目目录、实验报告目录、标题等。
    """
    from ..scaffold import init_project

    base = Path(root).expanduser()
    if not base.is_dir():
        raise ConfigError("根目录不存在：%s" % base, code="PROJECT_PARENT_MISSING")
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ConfigError("请填论文标题", code="PROJECT_TITLE_MISSING")
    clean_slug = str(slug or "").strip()
    if not clean_slug:
        clean_slug = _slugify(clean_title)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", clean_slug) or clean_slug in (".", ".."):
        raise ConfigError("文件夹名只允许字母、数字、点、下划线和连字符：%r"
                          % clean_slug, code="PROJECT_SLUG_INVALID")
    wanted = [lang for lang in (langs or ["en"]) if lang in ("zh", "en")]
    if not wanted:
        wanted = ["en"]

    created: list[str] = []
    disks: list[dict] = []
    for lang in wanted:
        name = clean_slug if lang == "en" else "%s-zh" % clean_slug
        target = base / name
        if target.exists():
            raise ConfigError("目标已存在：%s" % target, code="PROJECT_DIR_NOT_EMPTY")
        init_project(target, title=clean_title, author="", lang=lang)
        disk_project_dir = project_dir.strip() or name
        disk_reports = reports_dir.strip() or (disk_project_dir + "/reports")
        save_workbench_config(target, {
            "project_dir": disk_project_dir,
            "reports_dir": disk_reports,
            "lang": lang,
            "title": clean_title,
            "journal": journal,
            "template": template,
            "question": question,
        })
        created.append(str(target))
        disks.append({"id": name, "lang": lang, "path": str(target),
                      "project_dir": disk_project_dir,
                      "reports_dir": disk_reports})
    return {"ok": True, "created": created, "disks": disks,
            "title": clean_title, "slug": clean_slug}


def update_paper_project(disk_root: Path, *, title: str = "",
                          journal: str = "", template: str = "",
                          question: str = "", reports_dir: str = "",
                          last_disk: str = "") -> dict:
    """改项目：标题与几个可改字段。

    锁死的字段（FEEDBACK-v4 条目 24 的裁定）：**项目目录**（身份锚）与
    **写作语言／盘集合**——这两个这里根本不接受参数。
    """
    root = Path(disk_root)
    cfg_path = root / CONFIG_NAME
    if not cfg_path.is_file():
        raise ConfigError("这个目录不是论文项目：%s" % root, code="PROJECT_INVALID")
    values = workbench_config(root)
    changed: list[str] = []
    clean_title = str(title or "").strip()
    if clean_title:
        project = read_table(cfg_path, "project")
        if project.get("title") != clean_title:
            rewrite_table(cfg_path, "project",
                          {"title": _toml_value(clean_title)})
            changed.append("title")
        values["title"] = clean_title
    for key, value in (("journal", journal), ("template", template),
                       ("question", question), ("reports_dir", reports_dir),
                       ("last_disk", last_disk)):
        text = str(value or "").strip()
        if not text:
            continue
        if values.get(key) != text:
            values[key] = text
            changed.append(key)
    if changed:
        save_workbench_config(root, values)
    return {"ok": True, "changed": changed, "config": values}
