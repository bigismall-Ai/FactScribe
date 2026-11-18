# -*- coding: utf-8 -*-
"""双目录字面重合检测（`factscribe textreuse`）。

查重的第一步是**字面层**：两段文字是不是逐字一样（只差空白、LaTeX 注释、
LaTeX 命令这类排版噪声）。这一层是纯机械的，词级 n-gram 镶嵌就能判，
不需要模型，也不需要网络。本模块只做这一层。

**能力边界（硬声明，写进人读输出与 JSON）**：改写、洗稿、AI 拼装属**语义
层**，本卡不覆盖——**漏检属语义层，本卡不覆盖**。字面层绿了不等于没有抄，
只等于「没有逐字照搬」。语义/改写层是身份外延，另裁（P-139/P-143）。

机械口径：

* 收文件：递归 `.tex`/`.md`/`.txt`（`--ext` 可扩），零配置——**裸目录也能跑**
  （不读 `factscribe.toml`，不需要任何项目声明）。
* 归一：空白折叠（跨行也算同一个分隔）；LaTeX 注释行默认去（`--no-strip-comments`
  可留）；LaTeX 命令与其花括号实参默认去（排版骨架不算重合）；大小写折叠。
* 分词：拉丁/数字按词切；CJK 汉字按字切（中文没有空格，按字切才分得出
  词级 n-gram 的步进）。
* 镶嵌：词级 n-gram（默认 n=8，`--n` 可调 5–20），相邻命中聚成段。
* 报告：逐段两侧 `文件:行-行`＋重合词数；汇总各文件对的重合词数与 A 侧占比。

退出码照 factscribe 家规：**0**＝无超阈重合、**1**＝发现重合（逐段列）、
**2**＝用法错（目录不存在、n 越界、两侧同一目录等）。

本模块只读，不改任何既有模块的行为；错误码按不透明数据键处理
（`TR_` 前缀），不进错误码词册。
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path

from .config import ConfigError

# --------------------------------------------------------------------------
# 常量（口径与预注册阈值）
# --------------------------------------------------------------------------
# 默认收的文件类型（`--ext` 是**扩**，不是替换）。
DEFAULT_EXTS = (".tex", ".md", ".txt")
# n-gram 长度范围（工单 G6：可调 5–20）。
N_MIN = 5
N_MAX = 20
DEFAULT_N = 8
# 小段过滤阈值：重合词数少于它的小段不报（工单 G6：缺省 8）。
DEFAULT_MIN_TOKENS = 8

# 码（不透明数据键；不进错误码词册）。
CODE_OVERLAP = "TR_OVERLAP"
CODE_SELF_COMPARE = "TR_SELF_COMPARE"
CODE_DIR_MISSING = "TR_DIR_MISSING"
CODE_DIR_INVALID = "TR_DIR_INVALID"
CODE_N_RANGE = "TR_N_RANGE"
CODE_MIN_TOKENS_RANGE = "TR_MIN_TOKENS_RANGE"
CODE_NO_FILES = "TR_NO_FILES"

# 能力边界声明——人读输出与 JSON 里逐字出现这一句，不许改写口径。
BOUNDARY = ("本卡只查字面层：逐字照搬才算重合；改写／洗稿／AI 拼装属语义层，"
            "本卡不覆盖——漏检属语义层，本卡不覆盖。")

# CJK 逐字切，其余按词切（`[^\W_]+`＝Unicode 字母数字连读）。
_CJK = "぀-ヿ㐀-䶿一-鿿豈-﫿가-힯"
_TOKEN_RE = re.compile(r"[%s]|[^\W_]+" % _CJK)
# LaTeX 命令（含可选的方括号参与花括号实参）——排版骨架不算文字重合。
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z@]+\s*\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})*")
# 注释行首的百分号（未转义的）。
_PERCENT_RE = re.compile(r"(?<!\\)%.*$")


# --------------------------------------------------------------------------
# 归一与分词
# --------------------------------------------------------------------------
def _strip_latex_comments(text: str) -> str:
    """去 LaTeX 注释（`%` 到行尾；`\\%` 保留）。行数不变，行号可对齐。"""
    out = []
    for line in text.splitlines():
        out.append(_PERCENT_RE.sub("", line))
    return "\n".join(out)


def _strip_latex_commands(text: str) -> str:
    """去 LaTeX 命令与其花括号实参（`\\cite{key}`、`\\section{标题}` 之类）。"""
    return _LATEX_CMD_RE.sub(" ", text)


def tokenize(text: str, strip_comments: bool = True) -> list:
    """文本 → `[(词, 行号), ...]`。

    归一顺序：去 LaTeX 注释（默认开）→ 去 LaTeX 命令 → 空白折叠（即：
    词与词之间的一切空白都等价，跨行也算同一分隔）→ 大小写折叠 →
    分词（拉丁/数字按词，CJK 按字）。
    """
    if strip_comments:
        text = _strip_latex_comments(text)
    text = _strip_latex_commands(text)
    tokens = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for raw in _TOKEN_RE.findall(line):
            tokens.append((raw.casefold(), lineno))
    return tokens


def parse_exts(values) -> tuple:
    """`--ext` 列表 → 扩展名元组（补点、小写、允许逗号分隔、去重、保持顺序）。"""
    exts = []
    for value in values or ():
        for part in str(value).split(","):
            part = part.strip().lower()
            if not part:
                continue
            if not part.startswith("."):
                part = "." + part
            if part not in exts:
                exts.append(part)
    return tuple(exts)


def collect_files(root: Path, exts: tuple) -> list:
    """递归收文件（扩展名在清单内），按相对路径排序（结果可复现）。"""
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in exts:
            continue
        files.append(path)
    return files


# --------------------------------------------------------------------------
# 结果模型
# --------------------------------------------------------------------------
@dataclass
class Doc:
    """一侧的一个文件：词流＋逐词行号。"""
    rel: str                      # 相对该侧根目录的路径（报告用）
    tokens: list = dc_field(default_factory=list)   # 词形
    lines: list = dc_field(default_factory=list)    # 逐词行号
    total: int = 0                # 总词数

    def line_of(self, index: int) -> int:
        if not self.lines:
            return 0
        index = max(0, min(index, len(self.lines) - 1))
        return self.lines[index]


@dataclass
class Segment:
    """一段跨侧重合（两侧都是一段连续的行区间）。"""
    a_file: str
    a_line_start: int
    a_line_end: int
    b_file: str
    b_line_start: int
    b_line_end: int
    overlap_tokens: int           # 重合词数（两侧共有的那段文字有多长）
    a_span_tokens: int            # A 侧该段覆盖的词数
    b_span_tokens: int            # B 侧该段覆盖的词数
    a_token_start: int = 0        # A 侧词流起点（算并集用）
    a_token_end: int = 0
    b_token_start: int = 0
    b_token_end: int = 0

    @property
    def code(self) -> str:
        return CODE_OVERLAP

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "a_file": self.a_file,
            "a_line_start": self.a_line_start,
            "a_line_end": self.a_line_end,
            "a_span_tokens": self.a_span_tokens,
            "b_file": self.b_file,
            "b_line_start": self.b_line_start,
            "b_line_end": self.b_line_end,
            "b_span_tokens": self.b_span_tokens,
            "overlap_tokens": self.overlap_tokens,
        }


@dataclass
class Pair:
    """一个文件对的重合汇总。

    `overlap_tokens`＝**A 侧被复制的词数**（A 侧被覆盖区间的并集长度）：
    同一段 A 文字在 B 侧出现三次也只按一份算，所以 A 侧占比恒 ≤ 100%。
    `shared_tokens` 是各段重合词数之和（同一段在 B 侧多次出现会重复计）。
    """
    a_file: str
    b_file: str
    overlap_tokens: int
    a_total_tokens: int
    b_total_tokens: int
    segments: int
    b_overlap_tokens: int = 0
    shared_tokens: int = 0

    @property
    def a_ratio(self) -> float:
        """A 侧占比＝重合词数 ÷ A 侧该文件总词数。"""
        if not self.a_total_tokens:
            return 0.0
        return self.overlap_tokens / self.a_total_tokens

    @property
    def b_ratio(self) -> float:
        """B 侧占比＝重合词数 ÷ B 侧该文件总词数。"""
        if not self.b_total_tokens:
            return 0.0
        return self.b_overlap_tokens / self.b_total_tokens

    def as_dict(self) -> dict:
        return {
            "a_file": self.a_file,
            "b_file": self.b_file,
            "overlap_tokens": self.overlap_tokens,
            "a_total_tokens": self.a_total_tokens,
            "b_total_tokens": self.b_total_tokens,
            "b_overlap_tokens": self.b_overlap_tokens,
            "shared_tokens": self.shared_tokens,
            "a_ratio": round(self.a_ratio, 6),
            "b_ratio": round(self.b_ratio, 6),
            "segments": self.segments,
        }


@dataclass
class TextReuseResult:
    """一次双目录字面重合扫描的结果。"""
    dir_a: Path
    dir_b: Path
    n: int = DEFAULT_N
    min_tokens: int = DEFAULT_MIN_TOKENS
    exts: tuple = DEFAULT_EXTS
    strip_comments: bool = True
    files_a: int = 0
    files_b: int = 0
    tokens_a: int = 0
    tokens_b: int = 0
    segments: list = dc_field(default_factory=list)
    pairs: list = dc_field(default_factory=list)
    boundary: str = BOUNDARY

    @property
    def exit_code(self) -> int:
        """0＝无超阈重合；1＝有重合段。用法错由 ConfigError 走 exit 2。"""
        return 1 if self.segments else 0

    def summary(self) -> dict:
        return {
            "n": self.n,
            "min_tokens": self.min_tokens,
            "exts": list(self.exts),
            "strip_comments": self.strip_comments,
            "files_a": self.files_a,
            "files_b": self.files_b,
            "tokens_a": self.tokens_a,
            "tokens_b": self.tokens_b,
            "segment_count": len(self.segments),
            "overlap_tokens": sum(p.overlap_tokens for p in self.pairs),
            "pair_count": len(self.pairs),
        }


# --------------------------------------------------------------------------
# 扫描
# --------------------------------------------------------------------------
def _load_side(root: Path, exts: tuple, strip_comments: bool):
    """读一侧：文件清单＋逐文件词流。"""
    docs = []
    for path in collect_files(root, exts):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tokens = tokenize(text, strip_comments=strip_comments)
        if not tokens:
            continue
        docs.append(Doc(
            rel=str(path.relative_to(root)),
            tokens=[t for t, _ in tokens],
            lines=[ln for _, ln in tokens],
            total=len(tokens),
        ))
    return docs


def _shingles(doc: Doc, n: int) -> dict:
    """一个文件的 n-gram → 起始位置列表（升序）。"""
    index = {}
    toks = doc.tokens
    for i in range(len(toks) - n + 1):
        key = tuple(toks[i:i + n])
        index.setdefault(key, []).append(i)
    return index


def _match_runs(index_a: dict, toks_b: list, n: int) -> list:
    """贪心延伸：命中连成 run（run 内 A、B 两侧位置都连续）。

    每个 B 位置只延伸一个 run（优先延伸能接上的那个），所以命中数与文本体量
    同阶——同一个 n-gram 在文件里重复出现时不会把命中表炸成天文数字。
    位置查找用二分（候选位置表是升序的）。
    """
    runs = []
    active = []          # 上一位置命中、还可能接上的 run
    for j in range(len(toks_b) - n + 1):
        cands = index_a.get(tuple(toks_b[j:j + n]))
        if not cands:
            active = []
            continue
        extended = False
        for run in active:
            want = run["a_end"] + 1
            k = bisect.bisect_left(cands, want)
            if k < len(cands) and cands[k] == want:
                run["a_end"] = want
                run["b_end"] = j
                run["hits"] += 1
                extended = True
                break
        if not extended:
            run = {"a_start": cands[0], "a_end": cands[0],
                   "b_start": j, "b_end": j, "hits": 1}
            runs.append(run)
            active.append(run)
        active = [r for r in active if r["b_end"] == j]
    return runs


def _merge_runs(runs: list, n: int) -> list:
    """合并跨度重叠的 run（A 侧重叠或 B 侧重叠）——同一段文字重复出现时
    不该被算成两段。返回 `(a_start, a_end, b_start, b_end, shared)` 列表。"""
    spans = []
    for run in runs:
        spans.append((run["a_start"], run["a_end"] + n - 1,
                      run["b_start"], run["b_end"] + n - 1,
                      run["hits"] + n - 1))
    spans.sort(key=lambda s: (s[0], s[2]))
    merged = []
    for a_start, a_end, b_start, b_end, shared in spans:
        if merged:
            last = merged[-1]
            if a_start <= last[1] or b_start <= last[3]:
                merged[-1] = (min(last[0], a_start), max(last[1], a_end),
                              min(last[2], b_start), max(last[3], b_end),
                              max(last[4], shared))
                continue
        merged.append((a_start, a_end, b_start, b_end, shared))
    return merged


def _segments_for_pair(doc_a: Doc, doc_b: Doc, n: int, min_tokens: int) -> list:
    """两个文件之间的重合段（相邻命中聚成段）。"""
    index_a = _shingles(doc_a, n)
    runs = _match_runs(index_a, doc_b.tokens, n)
    if not runs:
        return []
    out = []
    for a_start, a_end, b_start, b_end, shared in _merge_runs(runs, n):
        if shared < min_tokens:
            continue
        out.append(Segment(
            a_file=doc_a.rel,
            a_line_start=doc_a.line_of(a_start),
            a_line_end=doc_a.line_of(min(a_end, doc_a.total - 1)),
            b_file=doc_b.rel,
            b_line_start=doc_b.line_of(b_start),
            b_line_end=doc_b.line_of(min(b_end, doc_b.total - 1)),
            overlap_tokens=shared,
            a_span_tokens=a_end - a_start + 1,
            b_span_tokens=b_end - b_start + 1,
            a_token_start=a_start,
            a_token_end=a_end,
            b_token_start=b_start,
            b_token_end=b_end,
        ))
    return out



def scan(dir_a: Path, dir_b: Path, n: int = DEFAULT_N,
         min_tokens: int = DEFAULT_MIN_TOKENS, exts: tuple = None,
         strip_comments: bool = True) -> TextReuseResult:
    """扫描两个目录的字面重合。只读。

    用法错（目录不存在、n 越界、两侧同一目录）抛 ConfigError（exit 2）。
    """
    dir_a = Path(dir_a)
    dir_b = Path(dir_b)
    exts = tuple(exts) if exts else DEFAULT_EXTS

    if not (N_MIN <= int(n) <= N_MAX):
        raise ConfigError("n 必须在 %d–%d 之间（给了 %s）" % (N_MIN, N_MAX, n),
                          code=CODE_N_RANGE)
    if int(min_tokens) < 1:
        raise ConfigError("--min-tokens 必须 ≥1（给了 %s）" % min_tokens,
                          code=CODE_MIN_TOKENS_RANGE)
    for root, label in ((dir_a, "目录A"), (dir_b, "目录B")):
        if not root.exists():
            raise ConfigError("%s 不存在：%s" % (label, root),
                              code=CODE_DIR_MISSING)
        if not root.is_dir():
            raise ConfigError("%s 不是目录：%s" % (label, root),
                              code=CODE_DIR_INVALID)
    if _same_dir(dir_a, dir_b):
        raise ConfigError(
            "自身对账无查重意义：目录A 与目录B 是同一个目录（%s）" % dir_a.resolve(),
            code=CODE_SELF_COMPARE)

    docs_a = _load_side(dir_a, exts, strip_comments)
    docs_b = _load_side(dir_b, exts, strip_comments)
    if not docs_a:
        raise ConfigError("目录A 下没有可读文件（找的是 %s）"
                          % "/".join(exts), code=CODE_NO_FILES)
    if not docs_b:
        raise ConfigError("目录B 下没有可读文件（找的是 %s）"
                          % "/".join(exts), code=CODE_NO_FILES)

    segments = []
    for doc_a in docs_a:
        for doc_b in docs_b:
            segments.extend(_segments_for_pair(doc_a, doc_b, int(n), int(min_tokens)))
    segments.sort(key=lambda s: (-s.overlap_tokens, s.a_file, s.a_line_start,
                                  s.b_file, s.b_line_start))

    totals_a = {d.rel: d.total for d in docs_a}
    totals_b = {d.rel: d.total for d in docs_b}
    pair_map = {}
    for seg in segments:
        key = (seg.a_file, seg.b_file)
        agg = pair_map.get(key)
        if agg is None:
            agg = Pair(a_file=seg.a_file, b_file=seg.b_file, overlap_tokens=0,
                       a_total_tokens=totals_a.get(seg.a_file, 0),
                       b_total_tokens=totals_b.get(seg.b_file, 0), segments=0)
            pair_map[key] = agg
        agg.segments += 1
        agg.shared_tokens += seg.overlap_tokens
    # 覆盖量取区间并集：同一段 A 文字在 B 侧出现多次也只按一份算。
    for key, agg in pair_map.items():
        a_spans, b_spans = [], []
        for seg in segments:
            if (seg.a_file, seg.b_file) != key:
                continue
            a_spans.append((seg.a_token_start, seg.a_token_end))
            b_spans.append((seg.b_token_start, seg.b_token_end))
        agg.overlap_tokens = _union_len(a_spans)
        agg.b_overlap_tokens = _union_len(b_spans)
    pairs = sorted(pair_map.values(),
                   key=lambda p: (-p.overlap_tokens, p.a_file, p.b_file))

    return TextReuseResult(
        dir_a=dir_a, dir_b=dir_b, n=int(n), min_tokens=int(min_tokens),
        exts=exts, strip_comments=strip_comments,
        files_a=len(docs_a), files_b=len(docs_b),
        tokens_a=sum(d.total for d in docs_a),
        tokens_b=sum(d.total for d in docs_b),
        segments=segments, pairs=pairs,
    )


def _union_len(spans: list) -> int:
    """若干闭区间的并集长度（词数）。"""
    if not spans:
        return 0
    ordered = sorted(spans)
    total = 0
    cur_start, cur_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= cur_end + 1:
            cur_end = max(cur_end, end)
            continue
        total += cur_end - cur_start + 1
        cur_start, cur_end = start, end
    return total + (cur_end - cur_start + 1)


def _same_dir(dir_a: Path, dir_b: Path) -> bool:
    """两个路径是不是同一个目录（同一路径，或同一 inode＝同盘同一目录）。"""
    try:
        a_resolved = dir_a.resolve()
        b_resolved = dir_b.resolve()
    except OSError:
        a_resolved = dir_a.absolute()
        b_resolved = dir_b.absolute()
    if a_resolved == b_resolved:
        return True
    try:
        if dir_a.exists() and dir_b.exists() and dir_a.samefile(dir_b):
            return True
    except OSError:
        pass
    return False


# --------------------------------------------------------------------------
# 报告
# --------------------------------------------------------------------------
def segment_dicts(result: TextReuseResult) -> list:
    return [s.as_dict() for s in result.segments]


def pair_dicts(result: TextReuseResult) -> list:
    return [p.as_dict() for p in result.pairs]


def render(result: TextReuseResult) -> str:
    """人读报告：逐段两侧行区间＋重合词数，末尾给汇总与能力边界。"""
    lines = ["== factscribe textreuse ==",
             "目录A：%s" % result.dir_a,
             "目录B：%s" % result.dir_b,
             "口径：词级 n=%d 字面重合；归一＝空白折叠＋LaTeX 注释行%s＋LaTeX 命令去"
             "＋大小写折叠；扩展名 %s"
             % (result.n, "已去" if result.strip_comments else "保留",
                "/".join(result.exts)),
             "覆盖：A 侧 %d 个文件 / %d 词；B 侧 %d 个文件 / %d 词"
             % (result.files_a, result.tokens_a, result.files_b, result.tokens_b),
             "能力边界：%s" % result.boundary]
    if not result.segments:
        lines.append("零重合：两侧没有 ≥%d 词的字面重合段。" % result.min_tokens)
        lines.append("注意：这不等于没有抄——改写与语义重合不在本卡口径内。")
        return "\n".join(lines)

    lines.append("重合段 %d 段（≥%d 词）：" % (len(result.segments), result.min_tokens))
    for i, seg in enumerate(result.segments, 1):
        lines.append("  %d) [%s] 重合 %d 词" % (i, seg.code, seg.overlap_tokens))
        lines.append("     A：%s:%d-%d" % (seg.a_file, seg.a_line_start, seg.a_line_end))
        lines.append("     B：%s:%d-%d" % (seg.b_file, seg.b_line_start, seg.b_line_end))
    lines.append("汇总（按文件对，A 侧被复制词数降序）：")
    for pair in result.pairs:
        lines.append("  %s ↔ %s：A 侧被复制 %d 词（占该文件 %.1f%%，%d/%d 词）；"
                     "B 侧被覆盖 %d 词（占该文件 %.1f%%）；共 %d 段"
                     % (pair.a_file, pair.b_file, pair.overlap_tokens,
                        pair.a_ratio * 100, pair.overlap_tokens,
                        pair.a_total_tokens, pair.b_overlap_tokens,
                        pair.b_ratio * 100, pair.segments))
    return "\n".join(lines)
