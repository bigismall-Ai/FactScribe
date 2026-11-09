# -*- coding: utf-8 -*-
"""文风闸 v4/v5：机械检测「公式化写作特征」，只出黄牌、不阻断、不改正文。

规则清单见 ``docs/design/SPEC-V3.0.md`` §13 与 §15：

* 插入语破折号、标题过长/带解释、标题术语未在首句定义；
* 节奏平台、同构三点并列在相邻段重复、套话连接词、空泛形容词、超长句；
* 改写后复检：首句复述标题（``HEADING_ECHO``）、标题关系词变化
  （``HEADING_RELATION_CHANGED``）、旧标题主语丢失（``HEADING_SUBJECT_LOST``），
  以及只报新增违规的 ``style --diff <before>``。

* 本工具**不评估、也不试图规避任何 AI 检测器**。它只检测可机械复算的
  写法；输出是「文件:行 + 原文 + 具体改法」，不是「像 AI」的分数。
* 退出码只有 0（无触发）与 3（黄牌，仍是提示）；永不返回 1。
  本模块只服务 ``style`` 子命令，不改 ``audit`` 的判据与退出码。
* 阈值、词表与术语白名单来自 ``style-rules.toml``（项目根优先，其次
  仓根，最后内置默认值），改阈值即改判定。

LaTeX 正文的遮罩保持原长度、保留换行，所以任何位置都能直接换算回
源文件行号；公式、图表、文献表、verbatim 与批注宏不参与文风统计。
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, ConfigError, load_toml
from .constants import EXIT_OK, EXIT_YELLOW
from .livetext import _live_text
from .texscan import sentence_spans

DISCLAIMER = ("本工具不评估、也不试图规避任何 AI 检测器；它检测的是可机械判定的"
              "公式化写作特征。黄牌只是改写提示，不阻断、不改正文。")

STYLE_RULES_NAME = "style-rules.toml"

# --------------------------------------------------------------------------
# 内置默认规则（与仓根 style-rules.toml 同构；文件缺失时兜底）
# --------------------------------------------------------------------------

DEFAULT_RULES: dict = {
    # 术语白名单：两层——项目内 GLOSSARY.md ＋ 用户自维护纯文本（一行一个词）
    "term_allow_files": ["GLOSSARY.md", "term-allow.txt"],
    "thresholds": {
        "connective_density": 8.0,
        # 句长 CV 的健康区间是 [sentence_uniformity, sentence_uniformity_high]；
        # 只有低于下界才算「太平」——高于上界是散，散不是 AI 特征。
        "sentence_uniformity": 0.45,
        "sentence_uniformity_high": 0.80,
        "empty_adjective": 6.0,
        "paragraph_template": 0.5,
        "hedge_stack": 1,
        "repeated_opener": 2,
        "sentence_length_extreme_en": 60,
        "sentence_length_extreme_zh": 110,
        "rhythm_plateau_run": 3,
        "rhythm_plateau_window": 10,
        # v4 新规则
        "dash_budget": 0,
        "heading_max_chars_zh": 12,
        "heading_max_words_en": 8,
        "colloquial_triad_repeats": 2,
        # v5 改写后复检：首句至少要引入这么多个新实义词，否则视为复述标题
        "heading_echo_min_new_terms": 1,
    },
    "limits": {
        "max_findings_per_metric": 20,
        "min_paragraph_units": 8,
        "uniformity_min_sentences": 10,
    },
    "connectives": {
        "english": ["Moreover", "Furthermore", "Additionally", "In addition",
                    "Overall", "In conclusion"],
        "chinese": ["首先", "其次", "此外", "综上所述", "总而言之"],
    },
    "empty_adjectives": {
        "english": ["crucial", "robust", "comprehensive", "significant",
                    "essential", "vital"],
        "chinese": ["至关重要", "显著", "全面", "深入"],
        "exempt_phrases": ["statistically significant",
                           "robust standard error", "robust to",
                           "more robust", "less robust",
                           "significant at the"],
    },
    "paragraph_closers": {
        "english": ["Therefore", "Overall", "Thus", "In conclusion"],
        "chinese": ["综上", "因此", "总之", "总而言之", "总体而言"],
    },
    "hedge_stacks": {
        "english": ["may potentially", "might potentially", "could potentially",
                    "may possibly", "might possibly", "could possibly",
                    "may conceivably", "could conceivably",
                    "seems to suggest", "appears to indicate",
                    "appears to suggest", "seems to indicate"],
        "chinese": ["可能会", "或许会", "或许能够", "也许可能", "似乎可能",
                    "大概可能", "可能会是"],
    },
    "repeated_opener": {
        # 虚词开头不算「模板化同头」，否则正常论文会被大量误伤
        "stopwords": ["the", "a", "an", "this", "that", "these", "those",
                      "it", "its", "they", "their", "we", "our", "i", "in",
                      "on", "for", "to", "as", "at", "by", "with", "from",
                      "there", "and", "but", "or", "if", "when", "while",
                      "because", "since", "of",
                      # 中文虚词/代词开头同样不算模板化同头
                      "如果", "那么", "因为", "所以", "但是", "因此", "并且",
                      "而且", "这", "那", "我们", "它", "其", "在", "对",
                      "从", "当", "为了", "通过", "由", "被", "把", "让",
                      "使", "一个", "一种", "本文", "本节", "每一", "每"],
    },
    # v5：标题关系词。只收承载「对立/否定」的关系词；并列连接
    # （and / or / 与 / 及 / 、）不进本表——删掉它们不改变论证方向。
    "heading_relation_words": ["versus", "vs", "not", "without",
                               "对", "而非", "不是"],
    # v5：HEADING_ECHO 的可配词表（泛化词不算「新实义」；垫话开头视为复述式）
    "heading_echo": {
        "generic_terms_en": ["limitation", "problem", "issue", "result",
                             "question", "thing", "aspect", "case", "point",
                             "claim", "matter", "area", "topic", "subject",
                             "part", "example", "work", "study", "approach",
                             "method", "way"],
        "generic_terms_zh": ["限制", "问题", "结果", "内容", "方面", "部分",
                             "事情", "情况", "因素", "要点", "工作", "研究",
                             "方法", "做法", "角度", "例子"],
        "meta_openers_en": ["is about", "is concerned with", "is discussed",
                            "we discuss", "this section", "this subsection",
                            "in this section", "in this subsection", "here we"],
        "meta_openers_zh": ["里", "中", "方面", "来说", "而言", "要先", "先要",
                            "先问", "首先要", "需要先", "本节讨论", "本节讲",
                            "这里讨论", "这一节讨论", "我们讨论", "本文讨论",
                            "讨论的是", "讲的是", "谈的是"],
    },
}

# 指标方向：True = 超过阈值触发；False = 低于阈值触发；单点指标用下限。
DIRECTIONS = {
    "connective_density": "above",
    "sentence_uniformity": "below",
    "empty_adjective": "above",
    "paragraph_template": "above",
    "hedge_stack": "at_least",
    "repeated_opener": "at_least",
    "sentence_length_extreme": "at_least",
    "rhythm_plateau": "at_least",
    # v4
    "dash_parenthetical": "above",
    "heading_too_long": "at_least",
    "heading_malformed": "at_least",
    "term_first_in_heading": "at_least",
    "colloquial_triad": "at_least",
    # v5 改写后复检
    "heading_echo": "at_least",
    "heading_relation_changed": "at_least",
    "heading_subject_lost": "at_least",
}

CODE_OF = {
    "connective_density": "CONNECTIVE_DENSITY",
    "sentence_uniformity": "SENTENCE_UNIFORMITY",
    "empty_adjective": "EMPTY_ADJECTIVE",
    "paragraph_template": "PARAGRAPH_TEMPLATE",
    "hedge_stack": "HEDGE_STACK",
    "repeated_opener": "REPEATED_OPENER",
    "sentence_length_extreme": "SENTENCE_LENGTH_EXTREME",
    "rhythm_plateau": "RHYTHM_PLATEAU",
    # v4
    "dash_parenthetical": "DASH_PARENTHETICAL",
    "heading_too_long": "HEADING_TOO_LONG",
    "heading_malformed": "HEADING_MALFORMED",
    "term_first_in_heading": "TERM_FIRST_IN_HEADING",
    "colloquial_triad": "COLLOQUIAL_TRIAD",
    # v5 改写后复检
    "heading_echo": "HEADING_ECHO",
    "heading_relation_changed": "HEADING_RELATION_CHANGED",
    "heading_subject_lost": "HEADING_SUBJECT_LOST",
}

FINDING_ORDER = ["SENTENCE_LENGTH_EXTREME", "DASH_PARENTHETICAL",
                 "HEADING_TOO_LONG", "HEADING_MALFORMED",
                 "HEADING_ECHO", "HEADING_RELATION_CHANGED",
                 "HEADING_SUBJECT_LOST", "TERM_FIRST_IN_HEADING",
                 "HEDGE_STACK", "CONNECTIVE_DENSITY", "EMPTY_ADJECTIVE",
                 "COLLOQUIAL_TRIAD", "PARAGRAPH_TEMPLATE", "REPEATED_OPENER",
                 "RHYTHM_PLATEAU", "SENTENCE_UNIFORMITY"]

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’\-]*")


# --------------------------------------------------------------------------
# 规则装载
# --------------------------------------------------------------------------

def _merge(base: dict, override: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
           for k, v in base.items()}
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _rules_candidates(project_root: Path) -> list[Path]:
    here = Path(__file__).resolve().parent
    return [project_root / STYLE_RULES_NAME,
            here.parent / STYLE_RULES_NAME,
            here / STYLE_RULES_NAME]


def load_style_rules(project_root: Path, explicit: str | None = None
                     ) -> tuple[dict, str]:
    """返回 (规则, 来源说明)。显式 --rules 缺失即配置错；默认文件缺失走内置。"""
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ConfigError("--rules 指向的 %s 不存在" % path)
        return _merge(DEFAULT_RULES, load_toml(path)), str(path)
    for path in _rules_candidates(project_root):
        if path.is_file():
            return _merge(DEFAULT_RULES, load_toml(path)), str(path)
    return _merge(DEFAULT_RULES, {}), "内置默认值"


def _thresholds(rules: dict) -> dict:
    raw = rules.get("thresholds") or {}
    out = {}
    for key, default in DEFAULT_RULES["thresholds"].items():
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError("style-rules.toml 的 thresholds.%s 必须是数字，"
                              "现在是 %r" % (key, value))
        if value < 0:
            raise ConfigError("style-rules.toml 的 thresholds.%s 不能为负" % key)
        out[key] = value
    return out


def _limits(rules: dict) -> dict:
    raw = rules.get("limits") or {}
    out = {}
    for key, default in DEFAULT_RULES["limits"].items():
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError("style-rules.toml 的 limits.%s 必须是正整数，"
                              "现在是 %r" % (key, value))
        out[key] = value
    return out


def _words(rules: dict, group: str) -> list[str]:
    raw = (rules.get(group) or {}).get("english") or []
    return [str(x) for x in raw if str(x).strip()]


def _cn_words(rules: dict, group: str) -> list[str]:
    raw = (rules.get(group) or {}).get("chinese") or []
    return [str(x) for x in raw if str(x).strip()]


def _phrase_regex(phrases: list[str]) -> re.Pattern | None:
    if not phrases:
        return None
    parts = []
    for phrase in sorted(phrases, key=len, reverse=True):
        parts.append(re.escape(phrase).replace(r"\ ", r"\s+"))
    return re.compile(r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(parts),
                      re.IGNORECASE)


# --------------------------------------------------------------------------
# LaTeX -> 纯正文（等长遮罩，保留换行）
# --------------------------------------------------------------------------

_SKIP_ENV_RE = re.compile(
    r"\\begin\s*\{(verbatim\*?|Verbatim|lstlisting|minted|comment\*?|pkignore"
    r"|equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?|displaymath|math"
    r"|figure\*?|table\*?|tabular\*?|tabularx|thebibliography"
    r"|algorithm\*?|algorithmic|tikzpicture)\}.*?\\end\s*\{\1\}",
    re.S)
_HEADING_RE = re.compile(
    r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph"
    r"|caption|title|author|date|thanks)\*?\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}")
_CITE_RE = re.compile(
    r"\\[A-Za-z]*[Cc]ite[A-Za-z]*\*?(?:\s*\[[^\]]*\])*(?:\s*\{[^{}]*\})")
_SKIP_CMDS = {
    "ref", "eqref", "pageref", "autoref", "cref", "Cref", "nameref", "vref",
    "label", "input", "include", "includeonly", "subfile", "includegraphics",
    "bibliography", "bibliographystyle", "addbibresource", "url", "href",
    "centering", "raggedright", "raggedleft", "noindent", "newpage",
    "clearpage", "appendix", "maketitle", "tableofcontents", "linebreak",
    "pagebreak", "hfill", "vfill", "quad", "qquad", "item",
}
_CMD_RE = re.compile(r"\\([A-Za-z]+)\*?")
_FACT_RE = re.compile(r"\\fact\s*\{[^{}]*\}")


def _blank(chars: list, start: int, stop: int) -> None:
    for i in range(max(0, start), min(stop, len(chars))):
        if chars[i] != "\n":
            chars[i] = " "


def _find_math_closer(s: str, start: int, closer: str) -> int:
    """从 start 起找未转义的数学闭合符（\\) 或 \\]）；找不到返回 -1。

    反斜杠一律按「转义下一个字符」跳过，因此 `\\\\)`（换行命令后跟右括号）
    不会被误认为闭合符。
    """
    i, n = start, len(s)
    while i < n:
        if s.startswith(closer, i):
            return i
        if s[i] == "\\":
            i += 2
            continue
        i += 1
    return -1


def _mask_inline_math(chars: list) -> None:
    """把 $...$、$$...$$、\\(...\\)、\\[...\\] 抹成空白（保留换行）。

    转义序列必须先于定界符处理：`\\$` 是**字面美元符号**（价格），不是数学
    模式起点；`\\\\` 是换行命令，后面的 `[` 也不能被当成 `\\[` 数学定界符。
    否则正文里出现一个 `\\$0.05` 就会把后面整段吞进数学模式，导致词数、句数
    与句长统计系统性偏低（批 71）。
    """
    s = "".join(chars)
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            nxt = s[i + 1] if i + 1 < n else ""
            if nxt in ("(", "["):
                closer = "\\)" if nxt == "(" else "\\]"
                end = _find_math_closer(s, i + 2, closer)
                if end < 0:
                    end = n
                else:
                    end += 2
                _blank(chars, i, end)
                i = end
                continue
            # `\$`、`\%`、`\\`、`\{` 等：转义后是字面字符或换行命令，
            # 都不是数学模式；连反斜杠一起跳过。
            i += 2
            continue
        if c == "$":
            if i + 1 < n and s[i + 1] == "$":
                j = i + 2
                while j < n:
                    if s[j] == "\\":
                        j += 2
                        continue
                    if s.startswith("$$", j):
                        break
                    j += 1
                end = n if j >= n else j + 2
            else:
                j = i + 1
                while j < n:
                    if s[j] == "\\":
                        j += 2
                        continue
                    if s[j] == "$":
                        break
                    j += 1
                end = n if j >= n else j + 1
            _blank(chars, i, end)
            i = end
            continue
        i += 1


def prose_of(tex: str) -> str:
    """返回纯正文：保留换行，行号与源文件一一对应。

    注释在剥离时会缩短该行（列位置左移），但换行全部保留，因此位置→行号
    的映射仍然有效；文风统计只用到行号。
    """
    live, _defs = _live_text(tex)
    chars = list(live)
    for m in _SKIP_ENV_RE.finditer(live):
        _blank(chars, m.start(), m.end())
    s = "".join(chars)
    # 写作批注宏：连同参数整块去掉（不是正文命题）
    for m in re.finditer(r"\\(?:todoq|todo|fixme|tbd|pknote|note)\b"
                         r"(?:\s*\[[^\]]*\])?\s*(?:\{[^{}]*\})?", s):
        _blank(chars, m.start(), m.end())
    _mask_inline_math(chars)
    s = "".join(chars)
    for m in _HEADING_RE.finditer(s):
        _blank(chars, m.start(), m.end())
    s = "".join(chars)
    for m in _CITE_RE.finditer(s):
        _blank(chars, m.start(), m.end())
    s = "".join(chars)
    # \fact{ID} 只抹 ID 参数；V3 的第二个参数是渲染出来的数字，保留
    for m in _FACT_RE.finditer(s):
        _blank(chars, m.start(), m.end())
    s = "".join(chars)
    # 结构命令名与「不渲染内容」的命令参数
    out = list(s)
    pos = 0
    while True:
        m = _CMD_RE.search(s, pos)
        if not m:
            break
        name = m.group(1)
        j = m.end()
        if name in _SKIP_CMDS:
            # 吞掉紧随的一个可选参数与一个必选参数
            k = j
            while k < len(s) and s[k] in " \t":
                k += 1
            if k < len(s) and s[k] == "[":
                k = _balanced_end(s, k, "[", "]")
            k2 = k
            while k2 < len(s) and s[k2] in " \t":
                k2 += 1
            if k2 < len(s) and s[k2] == "{":
                k = _balanced_end(s, k2, "{", "}")
            _blank(out, m.start(), k)
            pos = max(k, m.end())
            continue
        _blank(out, m.start(), j)
        pos = m.end()
    prose = "".join(out)
    # 换行命令 \\ 与其可选间距参数（\\[2pt]）是排版结构，不参与文风统计
    prose = re.sub(r"\\\\\*?(?:\[[^\]]*\])?",
                   lambda m: " " * len(m.group(0)), prose)
    # 残余的转义与结构字符：等长替换
    prose = re.sub(r"\\%", "%", prose)
    prose = re.sub(r"\\&", "&", prose)
    prose = re.sub(r"\\\$", "$", prose)
    prose = re.sub(r"\\_", "_", prose)
    prose = re.sub(r"\\#", "#", prose)
    prose = re.sub(r"\\{", "{", prose)
    prose = re.sub(r"\\}", "}", prose)
    prose = re.sub(r"\\[A-Za-z]+\*?", lambda m: " " * len(m.group(0)), prose)
    prose = re.sub(r"~", " ", prose)
    prose = re.sub(r"[{}\[\]]", " ", prose)
    return prose


def _balanced_end(s: str, start: int, opener: str, closer: str) -> int:
    depth = 0
    i = start
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == opener:
            depth += 1
        elif s[i] == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(s)


# --------------------------------------------------------------------------
# 计数单元与句子
# --------------------------------------------------------------------------

def units_of(text: str) -> int:
    """英文按词、中文按字；混排时中文 1 字＝1 单元，英文 1 词＝1 单元。"""
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_WORD_RE.findall(text))
    return cjk + latin


def _cjk_heavy(text: str) -> bool:
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_WORD_RE.findall(text))
    return cjk > 0 and cjk >= latin


def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clip(text: str, limit: int) -> str:
    text = _norm_space(text)
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


@dataclass
class Finding:
    code: str
    file: str
    line: int
    text: str
    suggestion: str
    metric: str = ""
    severity: str = "yellow"

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity,
                "file": self.file, "line": self.line,
                "text": self.text, "suggestion": self.suggestion}


@dataclass
class ParagraphInfo:
    file: str
    line: int
    words: int
    flags: list = field(default_factory=list)
    first_word: str = ""

    def as_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "words": self.words,
                "flags": self.flags}


@dataclass
class StyleResult:
    metrics: dict
    thresholds: dict
    fired: list
    findings: list
    paragraphs: list
    instances: dict
    summary: dict
    rules_path: str = ""
    stage_assessment: dict = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return EXIT_YELLOW if self.fired else EXIT_OK

    def as_dict(self) -> dict:
        return {
            "metrics": self.metrics,
            "thresholds": dict(self.thresholds),
            "findings": [f.as_dict() for f in self.findings],
            "paragraphs": [p.as_dict() for p in self.paragraphs],
            "fired": self.fired,
            "summary": self.summary,
            "stage_assessment": dict(self.stage_assessment),
            "rules": self.rules_path,
            "disclaimer": DISCLAIMER,
        }


@dataclass
class _Doc:
    file: str
    prose: str
    newlines: list
    raw: str = ""


def _line_of(doc: _Doc, pos: int) -> int:
    return bisect.bisect_right(doc.newlines, pos) + 1


def _paragraphs(doc: _Doc, min_units: int):
    """按空行切段，返回 [(start, end)]。"""
    out = []
    for m in re.finditer(r"[^\n]*(?:\n(?!\s*\n)[^\n]*)*", doc.prose):
        start, end = m.start(), m.end()
        if not doc.prose[start:end].strip():
            continue
        if units_of(doc.prose[start:end]) >= min_units:
            out.append((start, end))
    return out


def _sentences(prose: str, base: int = 0):
    """句子区间（绝对位置），只保留有内容的。"""
    spans = sentence_spans(prose)
    out = []
    for start, end in spans:
        if not prose[start:end].strip():
            continue
        if units_of(prose[start:end]) < 2:
            continue
        out.append((base + start, base + end))
    return out


# --------------------------------------------------------------------------
# 各项指标
# --------------------------------------------------------------------------

def _iter_matches(text: str, eng_re, cn_words):
    """返回 [(start, end, matched)]；英文按词边界、中文按子串。"""
    found = []
    if eng_re is not None:
        for m in eng_re.finditer(text):
            found.append((m.start(), m.end(), m.group(0)))
    for word in cn_words:
        start = 0
        while True:
            idx = text.find(word, start)
            if idx < 0:
                break
            if not any(s <= idx < e for s, e, _ in found):
                found.append((idx, idx + len(word), word))
            start = idx + len(word)
    found.sort()
    return found


def _strip_connective(sentence: str, token: str) -> str:
    """给出「删掉连接词」后的替换示例。"""
    low = sentence.lower()
    idx = low.find(token.lower())
    if idx < 0:
        return sentence
    end = idx + len(token)
    tail = sentence[end:]
    tail = re.sub(r"^[\s,，、;；:：]+", "", tail)
    return tail


def _extreme_split(sentence: str) -> str:
    """在句子中段找一个可断点，给出拆分示例。"""
    words = list(re.finditer(r"\S+", sentence))
    if len(words) < 6:
        return sentence
    mid = len(words) // 2
    best = None
    best_dist = 10 ** 9
    for i, m in enumerate(words[:-1]):
        token = m.group(0)
        if token.endswith(",") or token.endswith("，") or token.endswith(";") \
                or token.endswith("；") or token == "and" or token == "but":
            dist = abs(i - mid)
            if dist < best_dist:
                best, best_dist = i, dist
    if best is None:
        return sentence
    left = " ".join(w.group(0) for w in words[:best + 1]).rstrip(",;，；")
    right = " ".join(w.group(0) for w in words[best + 1:])
    if not right:
        return sentence
    right = right[0].upper() + right[1:]
    return left + ". " + right


# 长句里的「结构断点」：从句引导词、分号、破折号、括号。
# 有断点的长句是专家写法，不报；只有「又长又平铺」才报。
_EN_BREAK_RE = re.compile(
    r"\b(?:which|that|who|whom|whose|because|although|though|while|whereas"
    r"|since|unless|if|when|whenever|where|wherever|after|before|as|whether"
    r"|despite|given|provided|such\s+that|so\s+that|in\s+order\s+that"
    r"|not\s+only|thereby|hence|thus)\b"
    r"|[;()\[\]]|—|–|--", re.IGNORECASE)
_CN_BREAK_RE = re.compile(
    r"因为|由于|虽然|尽管|如果|若是|只要|只有|无论|不论|即使|即便"
    r"|但是|然而|而且|并且|同时|因此|因而|从而|于是|以便|以致|甚至"
    r"|尤其|其中|以及|则|却|而|；|：|—|（|）|《|》|「|」")


def _has_structural_break(sentence: str) -> bool:
    """句内是否有从句/分号/破折号/括号这类换气点。"""
    if _cjk_heavy(sentence):
        return bool(_CN_BREAK_RE.search(sentence))
    return bool(_EN_BREAK_RE.search(sentence))


def _first_word(text: str) -> str:
    m = re.search(r"[A-Za-z][A-Za-z'’\-]*|[\u4e00-\u9fff]{1,4}", text)
    return m.group(0).lower() if m else ""


def _is_stopword(first: str, stops: set) -> bool:
    if not first:
        return True
    if _CJK_RE.match(first):
        return any(first.startswith(s) for s in stops
                   if s and _CJK_RE.match(s))
    return first in stops


def _english_triad_re() -> re.Pattern:
    item = r"[A-Za-z0-9][A-Za-z0-9'’\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9'’\-]*){0,3}"
    return re.compile(r"\b(%s)\s*,\s*(%s)\s*,\s*(?:and|or)\s+(%s)\b" % (item, item, item),
                      re.IGNORECASE)


_CN_TRIAD_RE = re.compile(r"[^，。；：、\s][^，。；：、]{0,20}、[^，。；：、]{0,20}、[^，。；：、]{0,20}")

# 三元组里的每一项应是名词短语，而不是从句。第三项以这些词开头，
# 说明匹配到的是「A, B, and because ...」这种句子结构，不是并列清单。
_TRIAD_BAD_START = {
    "because", "which", "while", "when", "where", "whereas", "so", "but",
    "although", "though", "since", "if", "then", "that", "thereby", "who",
    "whom", "whose", "what", "how", "why", "yet", "nor",
}


def _valid_triad(groups: tuple[str, ...]) -> bool:
    for group in groups:
        words = re.findall(r"[A-Za-z][A-Za-z'’\-]*", group)
        if not words:
            return False
        if words[0].lower() in _TRIAD_BAD_START:
            return False
        if any(w.lower() in ("and", "or") for w in words):
            return False
    return True


# --------------------------------------------------------------------------
# v4：破折号插入语、标题、术语白名单、同构三点并列
# --------------------------------------------------------------------------

_EM_DASH_RE = re.compile(r"——|—")
_HEADING_CMD_RE = re.compile(
    r"\\(part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?"
    r"\s*(?:\[[^\]]*\])?\s*\{")
_HEADING_MALFORMED_RE = re.compile(r"[：:？?。！!]|——|—|[（(][^）)]*[）)]")
_TERM_SEP_RE = re.compile(r"[的和与及在对从为是]")
_TERM_STOP = {
    "a", "an", "the", "of", "for", "and", "or", "to", "in", "on", "with",
    "by", "from", "as", "at", "is", "are", "be", "this", "that", "these",
    "those", "how", "why", "what", "when", "where", "which", "who", "its",
    "our", "their", "we", "you", "i", "via", "using", "toward", "towards",
}


def _line_start(doc: _Doc, line: int) -> int:
    """第 ``line`` 行（1 起）在 prose 中的起点；越界返回文末。"""
    if line <= 1:
        return 0
    idx = line - 2
    if idx < len(doc.newlines):
        return doc.newlines[idx] + 1
    return len(doc.prose)


def _is_range_dash(prose: str, start: int, end: int) -> bool:
    """破折号是否属于数值范围或文献页码（这些不算插入语）。"""
    left = prose[max(0, start - 32):start]
    right = prose[end:end + 32]
    left_num = re.search(r"(\d+)\s*$", left)
    right_num = re.match(r"\s*(\d+)", right)
    if left_num and right_num:
        return True
    if right_num:
        if re.search(r"(?:pp?\.?|pages?)\s*\d+\s*$", left.lower()):
            return True
        if re.search(r"第\s*\d+\s*$", left) and re.match(r"\s*\d+\s*页", right):
            return True
    return False


def _heading_title(tex: str, brace: int) -> tuple[str, int]:
    """从 ``\\section{`` 的左花括号位置取出清理后的标题与闭合后的位置。"""
    end = _balanced_end(tex, brace, "{", "}")
    raw = tex[brace + 1:max(brace + 1, end - 1)]
    raw = re.sub(r"\\(?:label|thanks|footnote)\s*\{[^{}]*\}", " ", raw)
    raw = re.sub(r"\\[A-Za-z]+\*?", " ", raw)
    raw = re.sub(r"[$~{}\\^_]", " ", raw)
    return _norm_space(raw), end


def _headings(tex: str) -> list[dict]:
    """扫描源文件的章节标题（``\\title{}`` 不在其中，因此天然豁免）。"""
    out = []
    for m in _HEADING_CMD_RE.finditer(tex):
        brace = m.end() - 1          # 正则以 `{` 结尾
        title, end = _heading_title(tex, brace)
        if not title:
            continue
        out.append({
            "cmd": m.group(1),
            "title": title,
            "start": m.start(),
            "end": end,
            "line": tex.count("\n", 0, m.start()) + 1,
            "end_line": tex.count("\n", 0, end) + 1,
        })
    return out


def _term_candidates(title: str) -> list[str]:
    """从标题抽「术语样」词：中文 ≥4 字段；英文 ≥2 词短语。"""
    raw: list[str] = []
    for run in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]{4,}", title):
        for seg in _TERM_SEP_RE.split(run):
            if len(seg) >= 4:
                raw.append(seg)
    words = re.findall(r"[A-Za-z][A-Za-z0-9'’\-]*", title)
    run: list[str] = []
    for word in words:
        if word.lower() in _TERM_STOP:
            if len(run) >= 2:
                raw.append(" ".join(run))
            run = []
        else:
            run.append(word)
    if len(run) >= 2:
        raw.append(" ".join(run))
    out: list[str] = []
    seen: set[str] = set()
    for cand in raw:
        norm = _norm_space(cand)
        key = norm.lower()
        if norm and key not in seen:
            seen.add(key)
            out.append(norm)
    return out


def _term_allowlist(rules: dict, project_root: Path) -> set[str]:
    """读取术语白名单：大小写不敏感、去首尾空白、忽略空行与 # 注释。"""
    names = rules.get("term_allow_files", DEFAULT_RULES["term_allow_files"])
    if not isinstance(names, (list, tuple)):
        names = [names]
    allow: set[str] = set()
    for name in names:
        path = project_root / str(name)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            allow.add(_norm_space(line).lower())
    return allow


def _first_sentence_span_after(doc: _Doc, line: int,
                               stop_line: int | None = None
                               ) -> tuple[str, int]:
    """标题结束行之后的第一个非空句子；返回 (文本, 绝对起点)。

    ``stop_line`` 给定时，若该句落在下一个标题之后（本标题没有自己的正文），
    返回空——避免拿下一节的句子判本节。
    """
    if line < 1:
        line = 1
    base = _line_start(doc, line)
    for start, end in _sentences(doc.prose[base:], base):
        text = _norm_space(doc.prose[start:end])
        if not text:
            continue
        if stop_line is not None and _line_of(doc, start) >= stop_line:
            return "", -1
        return text, start
    return "", -1


def _first_sentence_after(doc: _Doc, line: int) -> str:
    """标题结束行之后的第一个非空句子（标题在 prose 里已被等长遮罩）。"""
    return _first_sentence_span_after(doc, line)[0]


# --------------------------------------------------------------------------
# v5：改写后复检（HEADING_ECHO / HEADING_RELATION_CHANGED /
#     HEADING_SUBJECT_LOST / style --diff）
# --------------------------------------------------------------------------

_ECHO_STOP_EN = set(_TERM_STOP) | {
    "these", "those", "this", "that", "there", "here", "it", "its", "they",
    "their", "them", "we", "our", "us", "you", "your", "i", "my", "me",
    "he", "she", "his", "her", "are", "is", "was", "were", "be", "been",
    "being", "am", "do", "does", "did", "done", "have", "has", "had",
    "having", "will", "would", "can", "could", "should", "may", "might",
    "must", "shall", "not", "no", "nor", "only", "just", "also", "so",
    "then", "than", "but", "if", "because", "as", "at", "by", "for", "from",
    "in", "into", "of", "on", "or", "to", "with", "without", "and", "via",
    "using", "toward", "towards", "about", "all", "any", "each", "every",
    "some", "such", "same", "more", "most", "less", "least", "very",
    "which", "who", "whom", "whose", "what", "when", "where", "why", "how",
    "whether", "section", "subsection", "chapter", "paragraph", "paper",
    "one", "two", "three", "first", "second", "third", "per",
}

_ECHO_STOP_ZH_PHRASES = (
    "这些", "那些", "这个", "那个", "本节", "本文", "本小节", "这一节", "该节",
    "我们", "你们", "他们", "它们", "什么", "为什么", "如何", "以及", "或者",
    "并且", "可以", "需要", "应当", "应该", "已经", "正在", "还是", "不是",
    "没有", "一个", "一种", "一份", "一套", "方面", "来说", "而言", "说明",
)

_ECHO_STOP_ZH_CHARS = set(
    "的了着过吗呢吧啊呀哦嗯是在和与及对从为且而并或把被让使由向其之此该"
    "本我你他她它们这那就都也还又再很更最则即等有要会能可应需先将")

_ECHO_PUNCT_RE = re.compile(r"[\s。．.!！?？:：;；,，、\"'“”‘’()（）\[\]【】]+")

# 对比结构识别（§15.4）。「对」只认「A 对 B」里的介词，排除
# 对照 / 针对 / 面对 / 对比 / 对于 / 相对 / 绝对 等词内部的对。
_DUI_RE = re.compile(
    r"(?<![针面绝反相应核比一])对(?=\s*[A-Za-z0-9\u4e00-\u9fff])"
    r"(?![照于比此方应称象着])")
_YU_COMPARE_RE = re.compile(r"(.+?)与(.+?)(?:对比|相比|比较)")
_ORDINAL_EN = {"one", "two", "three", "four", "first", "second", "third",
               "fourth"}
_ORDINAL_ZH = set("一二三四")
# 同义关系词分组：组内互换不报，跨组替换报（§15.3）。
_RELATION_GROUPS = {
    "versus": "comparison", "vs": "comparison", "对": "comparison",
    "not": "negation", "不是": "negation",
    "without": "exclusion", "而非": "exclusion",
}

# 这些垫话单独出现在句首就是元话语，不需要先复述标题；
# 「里/中/方面/来说/而言」只在标题后紧跟时才算（见 _heading_echo）。
_DIRECT_META_ZH = ("本节讨论", "本节讲", "这里讨论", "这一节讨论", "我们讨论",
                   "本文讨论", "讨论的是", "讲的是", "谈的是", "要先", "先要",
                   "先问", "首先要", "需要先")


def _stem_en(word: str) -> str:
    """极轻量英文归一：大小写、所有格、常见复数。只为「同词」比较服务。"""
    w = word.lower().strip("'-")
    if w.endswith("'s"):
        w = w[:-2]
    if len(w) > 3 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _en_terms(text: str, stop: set | None = None) -> list[str]:
    stop = _ECHO_STOP_EN if stop is None else stop
    out = []
    for raw in _LATIN_WORD_RE.findall(text):
        word = _stem_en(raw)
        if word and word not in stop:
            out.append(word)
    return out


def _echo_generic(rules: dict) -> tuple[set, list]:
    cfg = rules.get("heading_echo") or {}
    en = {_stem_en(str(x)) for x in (cfg.get("generic_terms_en") or [])}
    zh = [str(x) for x in (cfg.get("generic_terms_zh") or [])]
    return en, zh


def _cjk_content_chars(text: str, generic_zh: list) -> set:
    s = text
    for term in sorted(generic_zh, key=len, reverse=True):
        if term:
            s = s.replace(term, " ")
    for phrase in _ECHO_STOP_ZH_PHRASES:
        s = s.replace(phrase, " ")
    for ch in _ECHO_STOP_ZH_CHARS:
        s = s.replace(ch, " ")
    return set(_CJK_RE.findall(s))


def _new_content_terms(title: str, sentence: str, rules: dict) -> list[str]:
    """首句相对标题「新引入」的实义词；中文按字，英文按词。"""
    generic_en, generic_zh = _echo_generic(rules)
    if _cjk_heavy(title) or _cjk_heavy(sentence):
        head = _cjk_content_chars(title, generic_zh)
        sent = _cjk_content_chars(sentence, generic_zh)
        return sorted(sent - head)
    head = {t for t in _en_terms(title) if t not in generic_en}
    sent = {t for t in _en_terms(sentence) if t not in generic_en}
    return sorted(sent - head)


def _heading_key(text: str) -> str:
    return _ECHO_PUNCT_RE.sub(" ", text).strip().lower()


def _echo_meta_openers(rules: dict) -> tuple[tuple, tuple]:
    cfg = rules.get("heading_echo") or {}
    en = tuple(str(x).lower() for x in (cfg.get("meta_openers_en") or []))
    zh = tuple(str(x) for x in (cfg.get("meta_openers_zh") or []))
    return en, zh


def _heading_echo(title: str, sentence: str, rules: dict,
                  thresholds: dict) -> bool:
    """首句是否只是复述标题（复述 / 垫话 / 纯设问三种伪满足）。"""
    if not sentence:
        return False
    min_new = int(thresholds["heading_echo_min_new_terms"])
    if len(_new_content_terms(title, sentence, rules)) < min_new:
        return True
    meta_en, meta_zh = _echo_meta_openers(rules)
    sent_key = _heading_key(sentence)
    # 「This section is about ...」「本节讨论……」这类垫话不依赖标题复述。
    if any(sent_key.startswith(op) for op in meta_en):
        return True
    stripped = sentence.strip()
    if any(stripped.startswith(op) for op in _DIRECT_META_ZH):
        return True
    key = _heading_key(title)
    if key and sent_key.startswith(key):
        rest = sent_key[len(key):].lstrip()
        if any(rest.startswith(op) for op in meta_zh):
            return True
        if any(rest.startswith(op) for op in meta_en):
            return True
    # 纯设问（「什么是 X？」「X 是什么？」）没有引入新实义，已被上面的
    # 「新实义词 < 阈值」分支抓住；带新信息的设问式开场不算伪满足。
    return False


def _relation_words(rules: dict) -> list[str]:
    raw = rules.get("heading_relation_words")
    if raw is None:
        raw = DEFAULT_RULES["heading_relation_words"]
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    return [str(x) for x in raw if str(x).strip()]


def _relation_hits(title: str, words: list[str]) -> list[str]:
    hits = []
    low = title.lower()
    for word in words:
        if _CJK_RE.search(word):
            if word == "对":
                # 只认「A 对 B」里的介词：排除 对照 / 针对 / 面对 / 对比 /
                # 对于 / 相对 / 绝对 这类词内部的「对」。
                if _DUI_RE.search(title) or _YU_COMPARE_RE.search(title):
                    hits.append(word)
            elif word in title:
                hits.append(word)
        elif re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(word.lower()), low):
            hits.append(word.lower())
    return sorted(set(hits))


def _canon_relation(word: str) -> str:
    """关系词同义归一：同义关系词互换不算「对立关系被删」。

    比较：versus / vs / 对（含「与…对比」）；否定：not / 不是；
    排除：without / 而非。跨组替换仍算关系变化。
    """
    low = word.lower()
    return _RELATION_GROUPS.get(low, low)


def _contrast_sides(title: str) -> list[str]:
    """旧标题若是对比结构，返回对比双方（各取实义成分）；否则返回 []。

    只认 §15.4 列出的结构：英文 ``X versus/vs Y``；中文 ``X 对 Y``、
    ``X 与 Y 对比/相比/比较``、``X 而非 Y``、``X 不是 Y``。
    「并列连接」（and / 与 / 及 / 、）与普通修饰语不激活本规则。
    """
    if _cjk_heavy(title):
        m = _DUI_RE.search(title)
        if m:
            return [title[:m.start()], title[m.end():]]
        m = _YU_COMPARE_RE.search(title)
        if m:
            return [m.group(1), m.group(2)]
        for marker in ("而非", "不是"):
            if marker in title:
                left, right = title.split(marker, 1)
                return [left, right]
        return []
    m = re.search(r"(?<![A-Za-z])(?:versus|vs)(?![A-Za-z])", title, re.I)
    if not m:
        return []
    return [title[:m.start()], title[m.end():]]


def _heading_subjects(title: str, rules: dict) -> list[str]:
    """旧标题里的实义成分（中文按分隔字切段、英文按词），用于判「主语丢失」。

    序数词与单字词不承载对比对象，直接忽略。
    """
    generic_en, generic_zh = _echo_generic(rules)
    if _cjk_heavy(title):
        out = []
        for seg in _TERM_SEP_RE.split(title):
            seg = re.sub(r"[\s。．.!！?？:：;；,，、\"'“”‘’()（）\[\]【】]+",
                         "", seg)
            for phrase in _ECHO_STOP_ZH_PHRASES:
                seg = seg.replace(phrase, "")
            seg = "".join(ch for ch in seg if ch not in _ECHO_STOP_ZH_CHARS
                          and ch not in _ORDINAL_ZH)
            for term in generic_zh:
                seg = seg.replace(term, "")
            if len(seg) >= 2 and seg not in out:
                out.append(seg)
        return out
    out = []
    relation = {_canon_relation(w) for w in _relation_words(rules)}
    for word in _en_terms(title):
        if (len(word) < 2 or word in generic_en or word in _ORDINAL_EN
                or _canon_relation(word) in relation or word in out):
            continue
        out.append(word)
    return out


def _contrast_objects(title: str, rules: dict) -> list[str]:
    """对比结构里的「对象名词」；标题不是对比结构时返回 []。"""
    sides = _contrast_sides(title)
    if not sides:
        return []
    objects: list[str] = []
    for side in sides:
        for term in _heading_subjects(side, rules):
            if term not in objects:
                objects.append(term)
    return objects


def _lost_subjects(old_title: str, new_title: str, new_first: str,
                   rules: dict) -> list[str]:
    """只在旧标题是对比结构时，报「对比对象在新标题与新首句里都消失」。"""
    objects = _contrast_objects(old_title, rules)
    if not objects:
        return []
    lost = []
    if _cjk_heavy(old_title):
        probe = (new_title + " " + new_first)
        for obj in objects:
            if obj not in probe:
                lost.append(obj)
    else:
        probe = set(_en_terms(new_title + " " + new_first))
        for obj in objects:
            if _stem_en(obj) not in probe and obj not in probe:
                lost.append(obj)
    return lost


def _rewrite_heading_findings(docs: list["_Doc"], before_docs: list["_Doc"],
                              rules: dict) -> list[Finding]:
    """改写前后按文件、按标题出现顺序配对，报关系词变化与主语丢失。"""
    relation_words = _relation_words(rules)
    before_by_file = {d.file: _headings(d.raw) for d in before_docs}
    findings: list[Finding] = []
    for doc in docs:
        old_heads = before_by_file.get(doc.file)
        if not old_heads:
            continue
        new_heads = _headings(doc.raw)
        for idx, (old, new) in enumerate(zip(old_heads, new_heads)):
            if old["cmd"] != new["cmd"]:
                continue
            old_title, new_title = old["title"], new["title"]
            if old_title == new_title:
                continue
            old_rel = _relation_hits(old_title, relation_words)
            new_rel = _relation_hits(new_title, relation_words)
            old_set = {_canon_relation(w) for w in old_rel}
            new_set = {_canon_relation(w) for w in new_rel}
            if old_set and (old_set - new_set):
                findings.append(Finding(
                    "HEADING_RELATION_CHANGED", doc.file, new["line"],
                    _clip(new_title, 160),
                    "标题里的对立关系词被删除或替换了（旧：%s；新：%s）。"
                    "关系词承载论证方向，替换或删除前先确认结论没变；"
                    "要改就连正文一起改。"
                    % ("、".join(old_rel), "、".join(new_rel) or "无"),
                    "heading_relation_changed"))
            stop_line = None
            if idx + 1 < len(new_heads) and new_heads[idx + 1]["cmd"] not in (
                    "paragraph", "subparagraph"):
                stop_line = new_heads[idx + 1]["line"]
            first, _pos = _first_sentence_span_after(doc, new["end_line"],
                                                     stop_line=stop_line)
            lost = _lost_subjects(old_title, new_title, first, rules)
            if lost:
                findings.append(Finding(
                    "HEADING_SUBJECT_LOST", doc.file, new["line"],
                    _clip(new_title, 160),
                    "旧标题的实义成分在新标题与新首句里都消失了（%s）：要么写回"
                    "新标题，要么在新首句里交代它去了哪里。" % "、".join(lost),
                    "heading_subject_lost"))
    return findings


def _finding_signature(f: Finding) -> tuple[str, str, str]:
    return (f.code, f.file, _norm_space(f.text))


def filter_new_findings(after: StyleResult, before: StyleResult) -> StyleResult:
    """``style --diff``：只保留改后新增的违规（改前没有、改后有）。"""
    allowance: dict = {}
    for f in before.findings:
        key = _finding_signature(f)
        allowance[key] = allowance.get(key, 0) + 1
    new_findings = []
    for f in after.findings:
        key = _finding_signature(f)
        if allowance.get(key, 0) > 0:
            allowance[key] -= 1
            continue
        new_findings.append(f)
    fired_codes = {f.code for f in new_findings}
    fired = [item for item in after.fired if item["code"] in fired_codes]
    summary = dict(after.summary)
    summary["findings"] = len(new_findings)
    summary["triggered"] = len(fired)
    summary["exit_code"] = EXIT_YELLOW if new_findings else EXIT_OK
    return StyleResult(metrics=after.metrics, thresholds=after.thresholds,
                       fired=fired, findings=new_findings,
                       paragraphs=after.paragraphs, instances=after.instances,
                       summary=summary, rules_path=after.rules_path,
                       stage_assessment=after.stage_assessment)


def _shape_bucket(n: int) -> int:
    return 1 if n <= 2 else (2 if n <= 4 else 3)


def _paragraph_triads(text: str, triad_re: re.Pattern, base: int) -> list[tuple]:
    """返回段内三点并列的 (绝对起点, 绝对终点, 原文, 结构指纹)。"""
    hits = []
    for m in triad_re.finditer(text):
        if not _valid_triad(m.groups()):
            continue
        items = [_norm_space(g) for g in m.groups()]
        shape = tuple(_shape_bucket(len(re.findall(r"[A-Za-z][A-Za-z0-9'’\-]*", it)))
                      for it in items)
        hits.append((base + m.start(), base + m.end(),
                     _norm_space(m.group(0)), ("en", shape)))
    for m in _CN_TRIAD_RE.finditer(text):
        raw = m.group(0)
        items = [x.strip() for x in raw.split("、")]
        if len(items) != 3 or any(not x for x in items):
            continue
        shape = tuple(_shape_bucket(len(x)) for x in items)
        hits.append((base + m.start(), base + m.end(),
                     _norm_space(raw), ("cn", shape)))
    return sorted(hits)


# --------------------------------------------------------------------------
# 阶段判断：初稿 vs 成品稿
# --------------------------------------------------------------------------

STAGE_DRAFT = "draft"
STAGE_POLISHED = "polished"
ADVICE_REWRITE = "rewrite"
ADVICE_REPORT_ONLY = "report_only"

# 盲评结论（批 67–70）：文风闸对 LLM 初稿有效，对已打磨的人写稿有害。
# 因此只在「初稿特征明显」时给逐条改写指令；成品稿只报告、明确建议不改。
DRAFT_TRIGGER_FLOOR = 3
DRAFT_CV_LOW = 0.45
POLISHED_CV_HIGH = 0.80

REPORT_ONLY_PROMPT = "指标健康，建议不改；强行改写有降低自然度风险"


def assess_stage(triggers: int, cv: float, fired: list) -> dict:
    """按「触发项数 + 句长 CV」判初稿/成品稿。

    * ``triggers >= 3`` 或 ``cv < 0.45`` → draft + rewrite；
    * 其余（``triggers <= 2`` 且 CV 不在「太整齐」区）→ polished + report_only。

    CV 高于 0.80 是「散」，散不是公式化特征，同样按成品稿只报告。
    """
    codes = "、".join(f["code"] for f in fired) or "无"
    cv_shown = round(cv, 3)
    if triggers >= DRAFT_TRIGGER_FLOOR or cv < DRAFT_CV_LOW:
        parts = []
        if triggers >= DRAFT_TRIGGER_FLOOR:
            parts.append("触发 %d 项指标（%s）" % (triggers, codes))
        if cv < DRAFT_CV_LOW:
            parts.append("句长 CV=%.2f 低于 0.45（句子过于整齐）" % cv)
        reason = "；".join(parts) + "：呈现初稿的公式化特征，建议按改写清单处理。"
        return {"stage": STAGE_DRAFT, "advice": ADVICE_REWRITE,
                "reason": reason, "triggers": triggers, "cv": cv_shown}
    if cv > POLISHED_CV_HIGH:
        reason = ("仅 %d 项指标触发（%s）；句长 CV=%.2f 高于 0.80，属自然散落"
                  "（散不是公式化特征）：稿子已到打磨阶段，建议不改。"
                  % (triggers, codes, cv))
    else:
        reason = ("仅 %d 项指标触发（%s），句长 CV=%.2f 在健康区间 [0.45, 0.80]："
                  "稿子已到打磨阶段，建议不改。" % (triggers, codes, cv))
    return {"stage": STAGE_POLISHED, "advice": ADVICE_REPORT_ONLY,
            "reason": reason, "triggers": triggers, "cv": cv_shown}


def analyze(cfg: Config, sections: list[tuple[str, str]], rules: dict,
            rules_path: str = "",
            before: tuple[Config, list[tuple[str, str]]] | None = None
            ) -> StyleResult:
    thresholds = _thresholds(rules)
    limits = _limits(rules)
    min_units = limits["min_paragraph_units"]
    cap = limits["max_findings_per_metric"]

    connective_re = _phrase_regex(_words(rules, "connectives"))
    connective_cn = _cn_words(rules, "connectives")
    adjective_re = _phrase_regex(_words(rules, "empty_adjectives"))
    adjective_cn = _cn_words(rules, "empty_adjectives")
    exempts = [str(x).lower() for x in
               (rules.get("empty_adjectives") or {}).get("exempt_phrases") or []]
    closer_re = _phrase_regex(_words(rules, "paragraph_closers"))
    closer_cn = _cn_words(rules, "paragraph_closers")
    hedge_re = _phrase_regex(_words(rules, "hedge_stacks"))
    hedge_cn = _cn_words(rules, "hedge_stacks")
    triad_re = _english_triad_re()

    docs: list[_Doc] = []
    for rel, text in sections:
        prose = prose_of(text)
        live, _defs = _live_text(text)   # 标题扫描走活跃正文（注释里的标题不算）
        docs.append(_Doc(rel, prose,
                         [i for i, c in enumerate(prose) if c == "\n"], live))
    before_docs: list[_Doc] = []
    if before is not None:
        for rel, text in before[1]:
            prose = prose_of(text)
            live, _defs = _live_text(text)
            before_docs.append(_Doc(rel, prose,
                                    [i for i, c in enumerate(prose) if c == "\n"],
                                    live))

    total_units = sum(units_of(d.prose) for d in docs)
    all_sentences = []          # [(doc, start, end, units)]
    all_paragraphs = []         # [(doc, start, end, units)]
    paragraph_sentences = []    # 每段的句子序列（节奏平台按段判，不跨段）
    for doc in docs:
        for start, end in _paragraphs(doc, min_units):
            all_paragraphs.append((doc, start, end, units_of(doc.prose[start:end])))
            seq = []
            for s, e in _sentences(doc.prose[start:end], start):
                item = (doc, s, e, units_of(doc.prose[s:e]))
                all_sentences.append(item)
                seq.append(item)
            paragraph_sentences.append(seq)

    instances: dict[str, list[Finding]] = {code: [] for code in CODE_OF.values()}
    paragraph_infos: dict[tuple[str, int], ParagraphInfo] = {}

    # ---- 1. 套话连接词 ----
    connective_hits = 0
    for doc, start, end, _w in all_sentences:
        sentence = _norm_space(doc.prose[start:end])
        for s, _e, token in _iter_matches(sentence, connective_re, connective_cn):
            # 只把句首（或分句首）的连接词算作「套话连接」；"overall accuracy"
            # 这类定语用法不算，避免误伤。
            if sentence[:s].strip(" \"'“‘(["):
                continue
            connective_hits += 1
            replacement = _strip_connective(sentence, token)
            instances["CONNECTIVE_DENSITY"].append(Finding(
                "CONNECTIVE_DENSITY", doc.file, _line_of(doc, start), _clip(sentence, 180),
                "删去「%s」，直接陈述：%s" % (token, _clip(replacement, 120)),
                "connective_density"))

    # ---- 2. 空泛形容词 ----
    adjective_hits = 0
    for doc, start, end, _w in all_sentences:
        sentence = _norm_space(doc.prose[start:end])
        for s, e, token in _iter_matches(sentence, adjective_re, adjective_cn):
            context = sentence[max(0, s - 24):min(len(sentence), e + 24)].lower()
            if any(x in context for x in exempts):
                continue
            adjective_hits += 1
            nxt = re.match(r"[A-Za-z][A-Za-z'’\-]*",
                           sentence[e:].lstrip(" ,，"))
            phrase = token + (" " + nxt.group(0) if nxt else "")
            instances["EMPTY_ADJECTIVE"].append(Finding(
                "EMPTY_ADJECTIVE", doc.file, _line_of(doc, start), _clip(sentence, 180),
                "删掉「%s」这个标签，改成可核验的事实（例：'This step is %s' → "
                "'This step raises resolved instances from 5 to 10'）" % (phrase, token),
                "empty_adjective"))

    # ---- 3. 插入语破折号（逐处报；数值范围/页码/数学环境排除）----
    dash_hits = 0
    for doc in docs:
        for m in _EM_DASH_RE.finditer(doc.prose):
            if _is_range_dash(doc.prose, m.start(), m.end()):
                continue
            dash_hits += 1
            excerpt = _norm_space(doc.prose[max(0, m.start() - 40):
                                            min(len(doc.prose), m.end() + 40)])
            instances["DASH_PARENTHETICAL"].append(Finding(
                "DASH_PARENTHETICAL", doc.file, _line_of(doc, m.start()),
                _clip(excerpt, 180),
                "插入语破折号：按优先级改 ① 去掉「——」，改成逗号从属句；"
                "② 改用括号括起；③ 拆成独立一句。三种都不改事实与数字。",
                "dash_parenthetical"))

    # ---- 3b. 标题：过长 / 带解释 / 术语未在首句定义 / 首句复述标题 ----
    heading_counts = {"HEADING_TOO_LONG": 0, "HEADING_MALFORMED": 0,
                      "HEADING_ECHO": 0, "HEADING_RELATION_CHANGED": 0,
                      "HEADING_SUBJECT_LOST": 0, "TERM_FIRST_IN_HEADING": 0}
    term_allow = _term_allowlist(rules, cfg.root)
    for doc in docs:
        heads = _headings(doc.raw)
        for idx, head in enumerate(heads):
            title, line = head["title"], head["line"]
            if _cjk_heavy(title):
                too_long = (len(_CJK_RE.findall(title))
                            > thresholds["heading_max_chars_zh"])
                limit_txt = "%d 字" % thresholds["heading_max_chars_zh"]
            else:
                too_long = (len(_LATIN_WORD_RE.findall(title))
                            > thresholds["heading_max_words_en"])
                limit_txt = "%d 词" % thresholds["heading_max_words_en"]
            if too_long:
                heading_counts["HEADING_TOO_LONG"] += 1
                instances["HEADING_TOO_LONG"].append(Finding(
                    "HEADING_TOO_LONG", doc.file, line, _clip(title, 160),
                    "标题压到 %s 以内：把副标题或解释移到正文首句，标题只留"
                    "名词短语；不改正文事实。" % limit_txt,
                    "heading_too_long"))
            if _HEADING_MALFORMED_RE.search(title):
                heading_counts["HEADING_MALFORMED"] += 1
                instances["HEADING_MALFORMED"].append(Finding(
                    "HEADING_MALFORMED", doc.file, line, _clip(title, 160),
                    "标题不用冒号/破折号/括号解释/问号/句号：把解释移到正文"
                    "首句，标题只留名词短语；不改正文事实。",
                    "heading_malformed"))
            first = _first_sentence_after(doc, head["end_line"]).lower()
            for cand in _term_candidates(title):
                key = cand.lower()
                if key in term_allow or key in first:
                    continue
                heading_counts["TERM_FIRST_IN_HEADING"] += 1
                instances["TERM_FIRST_IN_HEADING"].append(Finding(
                    "TERM_FIRST_IN_HEADING", doc.file, line, _clip(title, 160),
                    "标题里的「%s」第一次出现时，请在该节首句用一句话定义或"
                    "点明它是什么（例：预注册是在收集数据前固定假设与分析"
                    "计划的做法）；复述标题、垫话（如「相关工作里，」）与设问"
                    "都不算定义。可在 term-allow.txt 登记白名单，只改措辞，"
                    "不改事实。" % cand,
                    "term_first_in_heading"))
            # v5：首句只是复述标题（复述/垫话/设问）——只判本节自己的正文。
            # 下一标题若是行内 \paragraph，它的首句可能和标题同在一行，
            # 仍算本节正文，不能用 stop_line 跳过。
            stop_line = None
            if idx + 1 < len(heads) and heads[idx + 1]["cmd"] not in (
                    "paragraph", "subparagraph"):
                stop_line = heads[idx + 1]["line"]
            first_txt, first_pos = _first_sentence_span_after(
                doc, head["end_line"], stop_line=stop_line)
            if first_txt and _heading_echo(title, first_txt, rules, thresholds):
                heading_counts["HEADING_ECHO"] += 1
                instances["HEADING_ECHO"].append(Finding(
                    "HEADING_ECHO", doc.file, _line_of(doc, first_pos),
                    _clip(first_txt, 180),
                    "首句只是复述标题；改成一句定义或可检验的断言（例：预注册"
                    "是在收集数据前固定假设与分析计划的做法）。复述标题、"
                    "垫话（「相关工作里，」）与设问都不算定义。",
                    "heading_echo"))

    # v5：改写前后标题比对（只在 style --diff 传入 --before 时运行）
    if before is not None:
        for finding in _rewrite_heading_findings(docs, before_docs, rules):
            heading_counts[finding.code] += 1
            instances[finding.code].append(finding)

    # ---- 3c. 同构三点并列：相邻段落重复才算 ----
    para_triads = []
    for doc, start, end, _units in all_paragraphs:
        hits = _paragraph_triads(doc.prose[start:end], triad_re, start)
        para_triads.append((doc, hits))
    repeated_triads = []
    seen_triad = set()
    prev_sigs: dict = {}
    prev_file = None
    for doc, hits in para_triads:
        if prev_file != doc.file:
            prev_sigs = {}
        cur_sigs: dict = {}
        for start, end, raw, sig in hits:
            cur_sigs.setdefault(sig, []).append((doc, start, end, raw))
            if sig in prev_sigs:
                for occ in prev_sigs[sig] + [(doc, start, end, raw)]:
                    key = (occ[0].file, occ[1])
                    if key not in seen_triad:
                        seen_triad.add(key)
                        repeated_triads.append(occ)
        prev_sigs = cur_sigs
        prev_file = doc.file
    for doc, start, _end, raw in repeated_triads:
        instances["COLLOQUIAL_TRIAD"].append(Finding(
            "COLLOQUIAL_TRIAD", doc.file, _line_of(doc, start), _clip(raw, 160),
            "同构三点并列在相邻段落重复：把其中一段的三项改成两项或拆成两句，"
            "只留有信息的两项；结构跟着内容走，不改事实。",
            "colloquial_triad"))

    # ---- 4. 段末套话收尾 / 5. 相邻段同头 ----
    template_flags = 0
    repeated = 0
    opener_stop = {str(x).lower() for x in
                   (rules.get("repeated_opener") or {}).get("stopwords") or []}
    prev_first = None
    prev_line = 0
    prev_file = None
    for doc, start, end, units in all_paragraphs:
        text = doc.prose[start:end]
        sentences = _sentences(text, start)
        info = ParagraphInfo(doc.file, _line_of(doc, start), units,
                             [], _first_word(text))
        if sentences:
            last_start, last_end = sentences[-1]
            last = _norm_space(doc.prose[last_start:last_end])
            head = last.lstrip(" \"'“”‘’`")
            closes = bool(closer_re and closer_re.match(head)) or \
                any(head.startswith(w) for w in closer_cn)
            if closes:
                template_flags += 1
                info.flags.append("PARAGRAPH_TEMPLATE")
                instances["PARAGRAPH_TEMPLATE"].append(Finding(
                    "PARAGRAPH_TEMPLATE", doc.file, _line_of(doc, last_start),
                    _clip(last, 180),
                    "段末不要用套话收尾：删掉句首的「Therefore/Overall/Thus」等，"
                    "让最后一句停在具体证据上（例：'Therefore, X is better' → "
                    "'X resolved 10 of 16 instances'）", "paragraph_template"))
            if (prev_file == doc.file and prev_first
                    and info.first_word == prev_first
                    and not _is_stopword(info.first_word, opener_stop)):
                repeated += 1
                info.flags.append("REPEATED_OPENER")
                instances["REPEATED_OPENER"].append(Finding(
                    "REPEATED_OPENER", doc.file, info.line,
                    _clip(_norm_space(text), 180),
                    "本段与上一段（第 %d 行）都以「%s」开头：把本段首句改成以研究对象"
                    "开头（例：'We use X to ...' → 'X is used to ...'）"
                    % (prev_line, info.first_word), "repeated_opener"))
        prev_first = info.first_word
        prev_line = info.line
        prev_file = doc.file
        paragraph_infos[(doc.file, info.line)] = info

    # ---- 6. 双重模糊限定 ----
    hedge_hits = 0
    for doc in docs:
        for m in _iter_matches(doc.prose, hedge_re, hedge_cn):
            start, end, token = m
            line = _line_of(doc, start)
            excerpt = _norm_space(doc.prose[start:min(end + 80, len(doc.prose))])
            hedge_hits += 1
            low = token.lower()
            if low.startswith(("may", "might", "could")):
                short = token.split()[0]
            elif "suggest" in low:
                short = "suggests"
            elif "indicate" in low:
                short = "indicates"
            elif _CJK_RE.search(token):
                short = "可能" if token.startswith("可能") else token
            else:
                short = token
            instances["HEDGE_STACK"].append(Finding(
                "HEDGE_STACK", doc.file, line, _clip(excerpt, 180),
                "双重限定叠在一起：把「%s」减成一层「%s」；能给出证据就删掉限定"
                % (token, short), "hedge_stack"))

    # ---- 7. 超长句（只报「又长又没有结构」的；长而有结构的句子不报） ----
    extreme_hits = 0
    sentence_units = []
    for doc, start, end, units in all_sentences:
        sentence = _norm_space(doc.prose[start:end])
        sentence_units.append((units, doc, start, sentence))
        limit = (thresholds["sentence_length_extreme_zh"] if _cjk_heavy(sentence)
                 else thresholds["sentence_length_extreme_en"])
        if units > limit and not _has_structural_break(sentence):
            extreme_hits += 1
            instances["SENTENCE_LENGTH_EXTREME"].append(Finding(
                "SENTENCE_LENGTH_EXTREME", doc.file, _line_of(doc, start),
                _clip(sentence, 220),
                "这句 %d 词超过 %d，且句内没有从句/分号/破折号/括号断点：这一句"
                "又长又平铺，保留原有结构，考虑在语义边界换气（例：%s）；"
                "长而有结构的句子不必改，也不要整段拆短"
                % (units, limit, _clip(_extreme_split(sentence), 120)),
                "sentence_length_extreme"))

    # ---- 7b. 节奏平台：连续 >=N 句落在同一 10 词区间 ----
    plateau_run = int(thresholds["rhythm_plateau_run"])
    plateau_window = int(thresholds["rhythm_plateau_window"])
    plateau_hits = 0
    for seq in paragraph_sentences:
        i = 0
        while i < len(seq):
            bucket = seq[i][3] // plateau_window
            j = i + 1
            while j < len(seq) and seq[j][3] // plateau_window == bucket:
                j += 1
            if j - i >= plateau_run:
                plateau_hits += 1
                first = seq[i]
                last = seq[j - 1]
                joined = " ".join(_norm_space(first[0].prose[it[1]:it[2]])
                                  for it in seq[i:j])
                unit = "字" if _cjk_heavy(joined) else "词"
                l1 = _line_of(first[0], first[1])
                l2 = _line_of(last[0], last[2])
                where = ("第 %d 行" % l1) if l1 == l2 else ("第 %d–%d 行" % (l1, l2))
                instances["RHYTHM_PLATEAU"].append(Finding(
                    "RHYTHM_PLATEAU", first[0].file, l1, _clip(joined, 220),
                    "%s连续 %d 句长度都在 %d–%d %s：节奏成了平台，"
                    "在其中插入一句 8–15 %s的短句，或把相邻两句合并，"
                    "让长短有起伏；内容与结构不动"
                    % (where, j - i, bucket * plateau_window,
                       bucket * plateau_window + plateau_window - 1, unit,
                       unit),
                    "rhythm_plateau"))
                i = j
            else:
                i += 1

    # ---- 8. 句长均匀度 ----
    sizes = [u for u, _d, _s, _t in sentence_units]
    min_sentences = limits["uniformity_min_sentences"]
    if sizes:
        raw_mean = sum(sizes) / len(sizes)
        raw_variance = sum((x - raw_mean) ** 2 for x in sizes) / len(sizes)
        raw_cv = (raw_variance ** 0.5 / raw_mean) if raw_mean else 0.0
    else:
        raw_cv = 1.0
    if len(sizes) >= min_sentences:
        mean = sum(sizes) / len(sizes)
        variance = sum((x - mean) ** 2 for x in sizes) / len(sizes)
        std = variance ** 0.5
        uniformity = (std / mean) if mean else 0.0
    else:
        mean = sum(sizes) / len(sizes) if sizes else 0.0
        std = 0.0
        # 句太少不判「整齐」（避免短文本误伤）：指标侧用 1.0 表示「不判」。
        # 阶段判断仍用 raw_cv（能算就算），否则 6 句高度同构的初稿会被误判成品。
        uniformity = 1.0

    # ---- 指标汇总与触发判定 ----
    def density(count: int) -> float:
        return round(count * 1000.0 / total_units, 2) if total_units else 0.0

    template_ratio = round(template_flags / len(all_paragraphs), 3) if all_paragraphs else 0.0
    metrics = {
        "connective_density": density(connective_hits),
        "sentence_uniformity": round(uniformity, 3),
        "empty_adjective": density(adjective_hits),
        "paragraph_template": template_ratio,
        "hedge_stack": hedge_hits,
        "repeated_opener": repeated,
        "sentence_length_extreme": extreme_hits,
        "rhythm_plateau": plateau_hits,
        "dash_parenthetical": dash_hits,
        "heading_too_long": heading_counts["HEADING_TOO_LONG"],
        "heading_malformed": heading_counts["HEADING_MALFORMED"],
        "heading_echo": heading_counts["HEADING_ECHO"],
        "heading_relation_changed": heading_counts["HEADING_RELATION_CHANGED"],
        "heading_subject_lost": heading_counts["HEADING_SUBJECT_LOST"],
        "term_first_in_heading": heading_counts["TERM_FIRST_IN_HEADING"],
        "colloquial_triad": len(repeated_triads),
    }

    fired = []
    for metric, direction in DIRECTIONS.items():
        if metric not in metrics:
            continue
        value = metrics[metric]
        if metric == "sentence_length_extreme":
            limit = 1
            hit = extreme_hits >= 1
            shown = limit
        elif metric == "rhythm_plateau":
            limit = int(thresholds["rhythm_plateau_run"])
            hit = plateau_hits >= 1
            shown = limit
        elif metric in ("hedge_stack", "repeated_opener"):
            limit = thresholds[metric]
            hit = value >= limit
            shown = limit
        elif metric == "dash_parenthetical":
            limit = int(thresholds["dash_budget"])
            hit = dash_hits > limit
            shown = limit
        elif metric == "colloquial_triad":
            limit = int(thresholds["colloquial_triad_repeats"])
            hit = len(repeated_triads) >= limit
            shown = limit
        elif metric in ("heading_too_long", "heading_malformed",
                        "term_first_in_heading", "heading_echo",
                        "heading_relation_changed", "heading_subject_lost"):
            limit = 1
            hit = value >= limit
            shown = limit
        elif direction == "above":
            limit = thresholds[metric]
            hit = value > limit
            shown = limit
        else:
            limit = thresholds[metric]
            hit = value < limit
            if metric == "sentence_uniformity":
                if len(sizes) < min_sentences:
                    hit = False
                # 上界只做健康区间说明：CV 高＝散，散不是 AI 特征，不报
                if value > thresholds["sentence_uniformity_high"]:
                    hit = False
            shown = limit
        if hit:
            fired.append({"code": CODE_OF[metric], "metric": metric,
                          "value": value, "threshold": shown,
                          "direction": direction})

    # 句长均匀度：整篇一条，指出最短/最长句的位置，便于具体改
    if (len(sizes) >= min_sentences
            and uniformity < thresholds["sentence_uniformity"]
            and uniformity <= thresholds["sentence_uniformity_high"]
            and sentence_units):
        short = min(sentence_units, key=lambda x: x[0])
        long = max(sentence_units, key=lambda x: x[0])
        doc = max(docs, key=lambda d: len(d.prose)) if docs else None
        instances["SENTENCE_UNIFORMITY"].append(Finding(
            "SENTENCE_UNIFORMITY", doc.file if doc else "", 1,
            "全文 %d 句：句长均值 %.1f，标准差 %.1f，CV=%.2f"
            % (len(sizes), mean, std, uniformity),
            "句长太整齐（CV=%.2f，低于健康下界 %.2f）：交替长短句，"
            "插入一句 8–15 词的短句，或把相邻短句合并；"
            "最短句在 %s:%d（%d 词），最长句在 %s:%d（%d 词）"
            % (uniformity, thresholds["sentence_uniformity"],
               short[1].file, _line_of(short[1], short[2]), short[0],
               long[1].file, _line_of(long[1], long[2]), long[0]),
            "sentence_uniformity"))

    # ---- findings：只对触发的指标出具体条目；单点指标已按条目计 ----
    fired_metrics = {f["metric"] for f in fired}
    findings: list[Finding] = []
    for code, items in instances.items():
        metric = next((m for m, c in CODE_OF.items() if c == code), "")
        if metric not in fired_metrics:
            continue
        findings.extend(items[:cap])
    findings.sort(key=lambda f: (FINDING_ORDER.index(f.code)
                                 if f.code in FINDING_ORDER else 99,
                                 f.file, f.line))

    paragraphs = sorted(paragraph_infos.values(), key=lambda p: (p.file, p.line))
    stage = assess_stage(len(fired), raw_cv, fired)
    summary = {
        "files": len(docs),
        "words": total_units,
        "sentences": len(all_sentences),
        "paragraphs": len(all_paragraphs),
        "triggered": len(fired),
        "findings": len(findings),
        "exit_code": EXIT_YELLOW if fired else EXIT_OK,
        "stage": stage["stage"],
        "advice": stage["advice"],
    }
    return StyleResult(metrics=metrics, thresholds=dict(thresholds), fired=fired,
                       findings=findings, paragraphs=paragraphs,
                       instances=instances, summary=summary,
                       rules_path=rules_path, stage_assessment=stage)


# --------------------------------------------------------------------------
# 给 LLM 的改写指令（<= 400 字）
# --------------------------------------------------------------------------

PROMPT_LIMIT = 400


def build_prompt(result: StyleResult, limit: int = PROMPT_LIMIT) -> str:
    # 成品稿（polished）只输出一句「建议不改」，不给逐条改写指令——盲评显示
    # 对已打磨的稿子强行改写会降低自然度（批 67–70）。
    if (result.stage_assessment or {}).get("advice") == ADVICE_REPORT_ONLY:
        return REPORT_ONLY_PROMPT[:limit]
    if not result.findings:
        text = ("未发现需要改写的公式化痕迹。不要为改写而改写；优先保留原有结构"
                "与修辞，事实、数字、引用保持原样。")
        return text[:limit]

    head = ("下列均为黄牌提示，只改措辞，不改事实、数字、引用；"
            "不得删数字、不得删引用、不得整段删除。优先保留原有结构与修辞，"
            "禁止整段拆短；只在 RHYTHM_PLATEAU 处调节奏。逐条处理后重新提交。")
    items = []
    # 先每个指标取一条，保证覆盖面，再补其余
    seen = set()
    ordered = []
    for f in result.findings:
        if f.code not in seen:
            seen.add(f.code)
            ordered.append(f)
    ordered += [f for f in result.findings if f not in ordered]

    for idx, f in enumerate(ordered, 1):
        item = "%d. %s:%d 「%s」→ %s" % (
            idx, Path(f.file).name, f.line, _clip(f.text, 34),
            _clip(f.suggestion, 46))
        trial = head + "\n" + "\n".join(items + [item])
        if len(trial) > limit:
            break
        items.append(item)
    tail = ""
    if len(items) < len(result.findings):
        tail = "\n（共 %d 处，先改前 %d 处。）" % (len(result.findings), len(items))
    text = head + "\n" + "\n".join(items) + tail
    if len(text) > limit:
        # 极端情况下裁掉条目，保证硬上限
        while items and len(head + "\n" + "\n".join(items) + tail) > limit:
            items.pop()
        text = head + "\n" + "\n".join(items)
        if len(text) > limit:
            text = text[:limit]
    return text


# --------------------------------------------------------------------------
# 人读报告
# --------------------------------------------------------------------------

def render_human(result: StyleResult, project: Path) -> str:
    m = result.metrics
    stage = result.stage_assessment or {}
    stage_line = ""
    if stage:
        verdict = "建议不改" if stage.get("advice") == ADVICE_REPORT_ONLY else "建议改写"
        stage_line = "阶段    : %s（%s，triggers=%d，cv=%.2f）\n判断    : %s" % (
            stage.get("stage", "?"), verdict, stage.get("triggers", 0),
            stage.get("cv", 0.0), stage.get("reason", ""))
    lines = ["== factscribe style ==",
             "project : %s" % project,
             "正文    : %d 个文件，%d 词/字，%d 句，%d 段"
             % (result.summary["files"], result.summary["words"],
                result.summary["sentences"], result.summary["paragraphs"]),
             "规则    : %s" % result.rules_path]
    if stage_line:
        lines.append(stage_line)
    lines += ["",
              "注意：" + DISCLAIMER,
              "",
              "指标                    读数      阈值     状态",
              "-----------------------  --------  -------  ----"]
    labels = [
        ("sentence_length_extreme", "SENTENCE_LENGTH_EXTREME", ">="),
        ("dash_parenthetical", "DASH_PARENTHETICAL", ">"),
        ("heading_too_long", "HEADING_TOO_LONG", ">="),
        ("heading_malformed", "HEADING_MALFORMED", ">="),
        ("heading_echo", "HEADING_ECHO", ">="),
        ("heading_relation_changed", "HEADING_RELATION_CHANGED", ">="),
        ("heading_subject_lost", "HEADING_SUBJECT_LOST", ">="),
        ("term_first_in_heading", "TERM_FIRST_IN_HEADING", ">="),
        ("rhythm_plateau", "RHYTHM_PLATEAU", ">="),
        ("colloquial_triad", "COLLOQUIAL_TRIAD", ">="),
        ("connective_density", "CONNECTIVE_DENSITY", ">"),
        ("empty_adjective", "EMPTY_ADJECTIVE", ">"),
        ("sentence_uniformity", "SENTENCE_UNIFORMITY", "<"),
        ("paragraph_template", "PARAGRAPH_TEMPLATE", ">"),
        ("hedge_stack", "HEDGE_STACK", ">="),
        ("repeated_opener", "REPEATED_OPENER", ">="),
    ]
    fired_codes = {f["code"] for f in result.fired}
    for key, label, op in labels:
        if key == "sentence_length_extreme":
            threshold = ">%d/%d" % (result.thresholds["sentence_length_extreme_en"],
                                    result.thresholds["sentence_length_extreme_zh"])
        elif key == "sentence_uniformity":
            threshold = "%s-%s" % (_fmt(result.thresholds["sentence_uniformity"]),
                                   _fmt(result.thresholds["sentence_uniformity_high"]))
        elif key == "rhythm_plateau":
            threshold = "run>=%d" % result.thresholds["rhythm_plateau_run"]
        elif key == "dash_parenthetical":
            threshold = "<=%d" % result.thresholds["dash_budget"]
        elif key == "heading_too_long":
            threshold = "<=%d字/%d词" % (
                result.thresholds["heading_max_chars_zh"],
                result.thresholds["heading_max_words_en"])
        elif key == "colloquial_triad":
            threshold = "repeat>=%d" % result.thresholds["colloquial_triad_repeats"]
        elif key in ("heading_malformed", "term_first_in_heading", "heading_echo",
                     "heading_relation_changed", "heading_subject_lost"):
            threshold = ">=1"
        else:
            threshold = "%s" % _fmt(result.thresholds.get(key, 0))
        value = m[key]
        status = "触发" if label in fired_codes else "ok"
        lines.append("%-23s  %-8s  %-7s  %s"
                     % (label, _fmt(value), threshold, status))
    lines.append("")
    if result.fired and stage.get("advice") == ADVICE_REPORT_ONLY:
        lines.append("[观察] %d 处清单（成品稿：建议不改，以下只作报告）"
                     % len(result.findings))
    elif result.fired:
        lines.append("[黄] %d 处具体改法（只提示，不阻断；退出码 3）"
                     % len(result.findings))
    else:
        lines.append("[黄] 0 处——所有指标在阈值内。")
    if result.fired:
        for idx, f in enumerate(result.findings, 1):
            lines.append(" %2d. %-22s %s:%d" % (idx, f.code, f.file, f.line))
            lines.append("     原文：" + _clip(f.text, 160))
            lines.append("     改法：" + f.suggestion)
    flagged = [p for p in result.paragraphs if p.flags]
    if flagged:
        lines.append("")
        lines.append("段级标记（%d 段）：" % len(flagged))
        for p in flagged[:40]:
            lines.append("  %s:%d  %d 词  %s"
                         % (p.file, p.line, p.words, "、".join(p.flags)))
    lines.append("")
    lines.append("说明：本闸只报「可机械判定的公式化写法」，不评估、也不试图规避"
                 "任何 AI 检测器；不阻断构建、不改正文。")
    return "\n".join(lines)


def _fmt(value) -> str:
    if isinstance(value, float):
        return ("%.2f" % value).rstrip("0").rstrip(".")
    return str(value)
