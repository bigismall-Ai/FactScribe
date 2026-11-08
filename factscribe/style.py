# -*- coding: utf-8 -*-
"""文风闸原型：机械检测「公式化写作特征」，只出黄牌、不阻断、不改正文。

定位（写进 docs/implementation/STYLE-GATE.md）：

* 本工具**不评估、也不试图规避任何 AI 检测器**。它只检测可机械复算的
  写法：套话连接词、句长过齐、空泛形容词、三项并列、段末套话收尾、
  双重模糊限定、相邻段同头、超长句。
* 输出是「文件:行 + 原文 + 具体改法」，不是「像 AI」的分数。
* 退出码只有 0（无触发）与 3（黄牌，仍是提示）；永不返回 1。
* 阈值与词表来自 ``style-rules.toml``（项目根优先，其次仓根，最后内置
  默认值），改阈值即改判定。

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
    "thresholds": {
        "connective_density": 8.0,
        # 句长 CV 的健康区间是 [sentence_uniformity, sentence_uniformity_high]；
        # 只有低于下界才算「太平」——高于上界是散，散不是 AI 特征。
        "sentence_uniformity": 0.45,
        "sentence_uniformity_high": 0.80,
        "empty_adjective": 6.0,
        "triad_density": 4.0,
        "paragraph_template": 0.5,
        "hedge_stack": 1,
        "repeated_opener": 2,
        "sentence_length_extreme_en": 60,
        "sentence_length_extreme_zh": 110,
        "rhythm_plateau_run": 3,
        "rhythm_plateau_window": 10,
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
}

# 指标方向：True = 超过阈值触发；False = 低于阈值触发；单点指标用下限。
DIRECTIONS = {
    "connective_density": "above",
    "sentence_uniformity": "below",
    "empty_adjective": "above",
    "triad_density": "above",
    "paragraph_template": "above",
    "hedge_stack": "at_least",
    "repeated_opener": "at_least",
    "sentence_length_extreme": "at_least",
    "rhythm_plateau": "at_least",
}

CODE_OF = {
    "connective_density": "CONNECTIVE_DENSITY",
    "sentence_uniformity": "SENTENCE_UNIFORMITY",
    "empty_adjective": "EMPTY_ADJECTIVE",
    "triad_density": "TRIAD_DENSITY",
    "paragraph_template": "PARAGRAPH_TEMPLATE",
    "hedge_stack": "HEDGE_STACK",
    "repeated_opener": "REPEATED_OPENER",
    "sentence_length_extreme": "SENTENCE_LENGTH_EXTREME",
    "rhythm_plateau": "RHYTHM_PLATEAU",
}

FINDING_ORDER = ["SENTENCE_LENGTH_EXTREME", "HEDGE_STACK", "CONNECTIVE_DENSITY",
                 "EMPTY_ADJECTIVE", "TRIAD_DENSITY", "PARAGRAPH_TEMPLATE",
                 "REPEATED_OPENER", "RHYTHM_PLATEAU", "SENTENCE_UNIFORMITY"]

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

    def as_dict(self) -> dict:
        return {"code": self.code, "file": self.file, "line": self.line,
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
            rules_path: str = "") -> StyleResult:
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
        docs.append(_Doc(rel, prose, [i for i, c in enumerate(prose) if c == "\n"]))

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

    # ---- 3. 三项并列 ----
    triad_hits = 0
    for doc in docs:
        text = doc.prose
        hits = [(m.start(), m.end(), _norm_space(m.group(0)))
                for m in triad_re.finditer(text)
                if _valid_triad(m.groups())]
        for m in _CN_TRIAD_RE.finditer(text):
            hits.append((m.start(), m.end(), _norm_space(m.group(0))))
        for start, end, raw in sorted(hits):
            triad_hits += 1
            instances["TRIAD_DENSITY"].append(Finding(
                "TRIAD_DENSITY", doc.file, _line_of(doc, start), _clip(raw, 160),
                "三项并列改成两项或拆成两句（例：'A, B, and C' → 'A and B. C ...'），"
                "只留有信息的两项", "triad_density"))

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
        "triad_density": density(triad_hits),
        "paragraph_template": template_ratio,
        "hedge_stack": hedge_hits,
        "repeated_opener": repeated,
        "sentence_length_extreme": extreme_hits,
        "rhythm_plateau": plateau_hits,
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

    head = ("只改下列标记句；不改事实、数字、引用；不得删数字、不得删引用、"
            "不得整段删除。优先保留原有结构与修辞，禁止整段拆短；"
            "只在 RHYTHM_PLATEAU 处调节奏。逐条处理后重新提交。")
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
        ("connective_density", "CONNECTIVE_DENSITY", ">"),
        ("sentence_uniformity", "SENTENCE_UNIFORMITY", "<"),
        ("empty_adjective", "EMPTY_ADJECTIVE", ">"),
        ("triad_density", "TRIAD_DENSITY", ">"),
        ("paragraph_template", "PARAGRAPH_TEMPLATE", ">"),
        ("hedge_stack", "HEDGE_STACK", ">="),
        ("repeated_opener", "REPEATED_OPENER", ">="),
        ("sentence_length_extreme", "SENTENCE_LENGTH_EXTREME", ">="),
        ("rhythm_plateau", "RHYTHM_PLATEAU", ">="),
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
