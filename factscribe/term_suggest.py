# -*- coding: utf-8 -*-
"""术语候选抽取与人工入表（SPEC-TERM-SUGGEST）。

纯统计＋规则，零 LLM、零第三方依赖：

* 语料遮罩复用 ``style._source_view``（TeX 走 ``prose_of``，Markdown 走
  ``mdscan``），代码块/注释/数学/表格先被抹成等长空白；
* 归一化与在册判断复用 ``terms``（``key_of`` / ``normalize_surface`` /
  ``Glossary``），不另写一套匹配键；
* 候选只做统计排序，交人用 ``terms add --pick`` 点名入表；本模块**不自动
  写词表**、不合并同义词。
"""
from __future__ import annotations

import bisect
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import ConfigError, load_config, load_sections
from .style import _source_view
from .terms import (load_glossary, key_of, normalize_surface,
                    parse_glossary)

# --------------------------------------------------------------------------
# 语料收集
# --------------------------------------------------------------------------

_SOURCE_SUFFIXES = {
    ".tex": "tex",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".text": "text",
}
# 生成物与结构化产物（表格、图、审计输出）不是论文正文语料。
_SKIP_DIRS = {
    "audit", "figures", "results", "tables", "build", "dist",
    "node_modules", "__pycache__", ".venv", ".git",
}


def _format_of(name: str) -> str:
    return _SOURCE_SUFFIXES.get(Path(name).suffix.lower(), "text")


def _walk_sources(root: Path) -> list[tuple[str, str]]:
    """递归收语料文件；路径排序，结果与文件系统枚举顺序无关。"""
    out: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if any(part.startswith(".") or part in _SKIP_DIRS
               for part in rel.parts[:-1]):
            continue
        out.append((rel.as_posix(),
                    path.read_text(encoding="utf-8", errors="replace")))
    return out


def _project_sources(root: Path) -> list[tuple[str, str]] | None:
    """有项目声明时按 ``sections`` 闭包取正文；坏配置退回递归扫描。"""
    try:
        cfg = load_config(root)
        sections = load_sections(cfg)
    except ConfigError:
        return None
    if not sections:
        return None
    return [(str(name), str(text)) for name, text in sections]


def collect_sources(root: Path) -> list[tuple[str, str]]:
    root = Path(root)
    if not root.is_dir():
        raise ConfigError("terms suggest 的目录不存在：%s" % root)
    return _project_sources(root) or _walk_sources(root)


# --------------------------------------------------------------------------
# 中文切分
# --------------------------------------------------------------------------

_CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")

# 先按多字虚词/套话切；长词在前，避免短词先把长词拆碎。
_ZH_MULTI_STOP = sorted({
    "以及", "并且", "但是", "而且", "因为", "所以", "如果", "虽然", "因此",
    "从而", "对于", "关于", "通过", "进行", "可以", "能够", "需要", "必须",
    "应该", "我们", "你们", "他们", "她们", "它们", "自己", "大家", "这个",
    "那个", "这些", "那些", "这类", "那类", "这种", "那种", "一个", "一种",
    "一些", "一样", "一直", "一起", "一般", "一旦", "每个", "各个", "各种",
    "什么", "怎么", "为什么", "这样", "那样", "同样", "其实", "只是", "不是",
    "而是", "还有", "比如", "例如", "已经", "仍然", "可能", "也许", "大概",
    "几乎", "完全", "非常", "比较", "相当", "十分", "更加", "最好", "最后",
    "首先", "其次", "此外", "另外", "其中", "所有", "任何", "有些", "有的",
    "有时", "有人", "没有", "无法", "不能", "不会", "不再", "就是", "还是",
    "或者", "然后", "然而", "当然", "之前", "之后", "之间", "现在", "以前",
    "用于", "来自", "作为", "成为", "具有", "存在", "包括", "属于", "位于",
}, key=len, reverse=True)
_ZH_MULTI_RE = re.compile("|".join(re.escape(word) for word in _ZH_MULTI_STOP))

_ZH_SINGLE_STOP = set(
    "的了着过和与及或而但则就都也还又再很更最把被让使是在对向从由并即若因"
    "这那哪吗呢吧啊呀哦嗯之其所以为于什怎")
_ZH_SPLIT_RE = re.compile(
    "[" + re.escape("".join(sorted(_ZH_SINGLE_STOP))) + r"\s]+")


def _chinese_segments(run: str):
    """按多字/单字虚词切分，产出 2–8 字的候选片段。"""
    run = _ZH_MULTI_RE.sub(" ", run)
    for part in _ZH_SPLIT_RE.split(run):
        if 2 <= len(part) <= 8:
            yield part


# --------------------------------------------------------------------------
# 英文切分
# --------------------------------------------------------------------------

_EN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’\-]*")

# 功能词与常见动词都当断点；不做词性标注，靠这张表近似「实词串＝名词短语」。
_EN_STOP = frozenset("""
a an the this that these those each every some any no all both either neither
another other such what which whose its their his her our your my
i we you he she it they them us me him one ones someone something anything
everything nothing everyone anyone nobody
of in on at to for from by with without about into onto over under between
among through during before after above below across per via as than like
unlike within upon toward towards against around behind beyond
and or but nor so yet because although though while whereas if unless since
whether not
is are was were be been being am do does did done doing have has had having
can could will would shall should may might must need needs ought
use uses used using show shows showed shown showing see sees saw seen make
makes made making take takes took taken get gets got give gives gave given go
goes went come comes came keep keeps kept put puts run runs ran running set
sets setting call calls called consider considers considered require requires
required allow allows allowed ensure ensures ensured provide provides provided
include includes included increase increases increased decrease decreases
decreased reduce reduces reduced add adds added remain remains remained become
becomes became appear appears appeared seem seems seemed want wants wanted try
tries tried work works worked working report reports reported measure measures
measured test tests tested testing evaluate evaluates evaluated compare
compares compared choose chooses chose chosen treat treats treated label
labels labeled emit emits emitted leak leaks leaked mask masks masked drop
drops dropped deliver delivers delivered compile compiles compiled assemble
assembles assembled load loads loaded cache caches cached prune prunes pruned
truncate truncates truncated
""".split())


def _english_phrases(line: str):
    """逐行产 1–4 词的实词短语；标点/换行即断句。"""
    run: list[str] = []

    def flush():
        nonlocal run
        if not run:
            return
        for i in range(0, len(run), 4):
            chunk = run[i:i + 4]
            if len(chunk) >= 2:
                yield " ".join(chunk)
            elif "-" in chunk[0] or chunk[0][0].isupper():
                yield chunk[0]
        run = []

    prev_end = None
    for match in _EN_TOKEN_RE.finditer(line):
        if prev_end is not None and line[prev_end:match.start()].strip(" \t"):
            yield from flush()
        word = match.group(0)
        if word.lower() in _EN_STOP:
            yield from flush()
        else:
            run.append(word)
        prev_end = match.end()
    yield from flush()


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    surface: str
    lang: str
    count: int
    sections: int
    first_location: str
    score: int

    def as_dict(self) -> dict:
        return {
            "surface": self.surface,
            "lang": self.lang,
            "count": self.count,
            "sections": self.sections,
            "first_location": self.first_location,
            "score": self.score,
        }


class _Bucket:
    __slots__ = ("lang", "count", "sections", "first_location", "surfaces")

    def __init__(self, lang: str):
        self.lang = lang
        self.count = 0
        self.sections: set[str] = set()
        self.first_location = ""
        self.surfaces: Counter = Counter()

    def add(self, surface: str, section: str, location: str) -> None:
        self.count += 1
        self.sections.add(section)
        if not self.first_location:
            self.first_location = location
        self.surfaces[normalize_surface(surface)] += 1

    def display_surface(self) -> str:
        # 出现次数最多的写法；同数取字典序最小，保证确定性。
        return sorted(self.surfaces.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _section_index(heading_lines: list[int], line: int) -> int:
    return bisect.bisect_right(heading_lines, line)


def _scan_document(rel: str, text: str, buckets: dict) -> None:
    fmt = _format_of(rel)
    prose, headings, _raw, _list_prose, _list_spans = _source_view(text, fmt)
    heading_lines = sorted({int(h["line"]) for h in headings
                            if isinstance(h.get("line"), int)})

    def section_of(line: int) -> str:
        return "%s#%d" % (rel, _section_index(heading_lines, line))

    for line_no, line in enumerate(prose.split("\n"), 1):
        for match in _CJK_RUN_RE.finditer(line):
            for segment in _chinese_segments(match.group(0)):
                bucket = buckets.setdefault(
                    ("zh", segment), _Bucket("zh"))
                bucket.add(segment, section_of(line_no),
                           "%s:%d" % (rel, line_no))
        for phrase in _english_phrases(line):
            bucket = buckets.setdefault(
                ("en", key_of(phrase)), _Bucket("en"))
            bucket.add(phrase, section_of(line_no),
                       "%s:%d" % (rel, line_no))

def suggest(root, min_count: int = 3, min_sections: int = 2,
            glossary_path=None) -> list[Candidate]:
    """挖候选：返回按 (score 降序, surface 升序) 排好的列表。"""
    if min_count < 1:
        raise ConfigError("--min-count 必须 ≥ 1")
    if min_sections < 1:
        raise ConfigError("--min-sections 必须 ≥ 1")
    glossary = load_glossary(glossary_path) if glossary_path else load_glossary()
    buckets: dict = {}
    for rel, text in collect_sources(Path(root)):
        _scan_document(rel, text, buckets)

    rows: list[Candidate] = []
    for (lang, _key), bucket in buckets.items():
        if bucket.count < min_count:
            continue
        if len(bucket.sections) < min_sections:
            continue
        surface = bucket.display_surface()
        if glossary.canonical_of(surface) is not None:
            continue
        rows.append(Candidate(
            surface=surface,
            lang=lang,
            count=bucket.count,
            sections=len(bucket.sections),
            first_location=bucket.first_location,
            score=bucket.count * len(bucket.sections),
        ))
    rows.sort(key=lambda row: (-row.score, row.surface))
    return rows


def render_tsv(rows) -> str:
    lines = ["surface\tlang\tcount\tsections\tfirst_location\tscore"]
    for row in rows:
        lines.append("%s\t%s\t%d\t%d\t%s\t%d" % (
            row.surface, row.lang, row.count, row.sections,
            row.first_location, row.score))
    return "\n".join(lines) + "\n"


def json_payload(rows, root, min_count: int, min_sections: int) -> dict:
    return {
        "tool": "terms",
        "action": "suggest",
        "root": str(Path(root)),
        "min_count": min_count,
        "min_sections": min_sections,
        "candidates": [row.as_dict() for row in rows],
        "count": len(rows),
    }


# --------------------------------------------------------------------------
# 入表（只写人工 pick）
# --------------------------------------------------------------------------

_CANDIDATE_COLUMNS = ("surface", "lang", "count", "sections",
                      "first_location", "score")


def _read_candidates(path: Path) -> list[dict]:
    if not path.is_file():
        raise ConfigError("候选文件不存在：%s" % path)
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        raise ConfigError("候选文件为空：%s" % path)
    header = [cell.strip() for cell in lines[0].split("\t")]
    if tuple(header[:6]) != _CANDIDATE_COLUMNS:
        raise ConfigError(
            "候选文件首行必须是 %s，现在是 %r"
            % ("\t".join(_CANDIDATE_COLUMNS), lines[0]))
    rows = []
    for raw in lines[1:]:
        cols = raw.split("\t")
        if len(cols) < 6:
            raise ConfigError("候选行缺列：%r" % raw)
        rows.append(dict(zip(_CANDIDATE_COLUMNS, cols[:6])))
    return rows


def add_from_tsv(from_path, picks, glossary_path=None,
                 today: str | None = None) -> dict:
    """把人工 ``picks`` 里点名的表面形式追加进词表；不合并同义词。"""
    source = Path(from_path)
    rows = _read_candidates(source)
    targets = Path(glossary_path) if glossary_path else None
    if targets is None:
        from .terms import DEFAULT_PAPER_PATH
        targets = DEFAULT_PAPER_PATH
    if not targets.is_file():
        raise ConfigError("词表不存在：%s" % targets)

    wanted: dict[str, str] = {}
    for raw in picks:
        for piece in str(raw).split(","):
            piece = piece.strip()
            if piece:
                wanted.setdefault(key_of(piece), piece)
    if not wanted:
        raise ConfigError("terms add 需要至少一个 --pick 表面形式")

    existing = load_glossary(targets)
    added: list[str] = []
    skipped: list[dict] = []
    matched: set[str] = set()
    for row in rows:
        key = key_of(row["surface"])
        if key not in wanted:
            continue
        matched.add(key)
        surface = row["surface"].strip()
        if not surface:
            continue
        if existing.canonical_of(surface) is not None:
            skipped.append({"surface": surface, "reason": "已在该词表"})
            continue
        added.append(surface)

    missing = [wanted[key] for key in wanted if key not in matched]
    if missing:
        raise ConfigError(
            "--pick 不在候选文件里：%s" % "、".join(repr(x) for x in missing))

    if added:
        text = targets.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            text += "\n"
        stamp = today or date.today().isoformat()
        comment = "# terms add %s：来源 %s" % (stamp, source)
        body = [comment]
        body += ["%s\t\t\t待分类" % surface for surface in added]
        targets.write_text(text + "\n".join(body) + "\n", encoding="utf-8")
        # 写完立刻重解析：词表坏了必须当场报错，不能留给 style 才发现。
        parsed = parse_glossary(targets.read_text(encoding="utf-8"))
        for surface in added:
            if parsed.canonical_of(surface) is None:
                raise ConfigError("写入后词表无法解析新术语：%s" % surface)

    return {
        "glossary": str(targets),
        "source": str(source),
        "added": added,
        "skipped": skipped,
        "comment": ("# terms add %s：来源 %s"
                    % (today or date.today().isoformat(), source))
        if added else "",
    }
