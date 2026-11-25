# -*- coding: utf-8 -*-
"""收据五元组的**共用生产逻辑**（七条线同一套，不各线各造一套）。

一行＝一条事实，字段固定五元组：

    id ｜ sha16 ｜ span ｜ face ｜ how

* ``id``     事实 id（取事实账的 id）
* ``sha16``  事实账钉的来源哈希前 16 位（没钉 → 缺省标记）
* ``span``   值在官方正文**原文坐标**里的首次命中区间 `"s-e"`；定不到 → 缺省标记
* ``face``   命中面：`body`（官方正文）／`résumé`（官方摘要段）／缺省标记
* ``how``    核验方式：`contains`（逐字）／`numnorm`（数字·日期归一）／
  `catalog`（目录树·详情元数据对账）／缺省标记

**缺省标记统一是 `"—"`**（沿用法国判例线的既有实现，不新造标记形状）。

为什么独立成件
----------------
「五元组长什么样、span 怎么定位、取不到时写什么」是**跨七条线的一条**契约；
各线不一样的只有「材料在哪、命中面怎么定、怎么核验」。前者归本件（纯函数），
后者归 `factscribe_legal.lines`（各线适配点）。同一套生产逻辑 ⇒ 各线产出
同构，跨域比较与后续扩线不用再各写一套。

本件只读、零 LLM、零网络、不写盘、不碰系统钟。
"""
import re

__all__ = [
    "MISSING", "RECEIPT_FIELDS", "sha16_of", "span_in_text",
    "classify_how", "build_receipt", "norm_space", "contains_norm",
]

# 统一的缺省标记（沿用法国判例线的既有写法，不新造标记形状）
MISSING = "—"

# 五元组的字段名与顺序（契约的一部分：各线产出必须同构）
RECEIPT_FIELDS = ("id", "sha16", "span", "face", "how")

# 各种空白（含 NBSP / 窄 NBSP / thin space）——法式千分位常用 NBSP
_SPACEY = "\u00a0\u202f\u2009\u2007\u2008\u2005"

# 纯数字（含千分位点/逗号写法：`1.234`、`1,234`、`1234`）
_NUMERIC_RE = re.compile(r"^\d+(?:[.,]\d+)*$")
# 日期形（ISO 与点/斜杠分隔都收）
_DATEISH_RE = re.compile(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}$")


def sha16_of(source_sha256):
    """事实账钉的来源哈希前 16 位（没钉 → 缺省标记）。

    钉的形如 `sha256:<64 hex>`；前缀剥掉，只留前 16 位十六进制。
    """
    s = str(source_sha256 or "").strip()
    if s.startswith("sha256:"):
        s = s[len("sha256:"):]
    s = s.strip().lower()
    return s[:16] if s else MISSING


def span_in_text(value, text):
    """value 在原文**原文坐标**里的首次命中区间（空白容忍）→ `"s-e"`。

    引文收据用：把 value 按空白切成 token、token 串用 `\\s+` 连接后搜索——
    NBSP/窄空格/换行差异不影响定位；找不到（或 value 为空）→ 缺省标记。

    算法出自法国判例线既有的收据实现（收编进正仓那支的 `_span_in_text`），
    本件把它抬成七条线共用的一套。
    """
    pat = r"\s+".join(re.escape(tok) for tok in str(value or "").split())
    if not pat:
        return MISSING
    m = re.search(pat, text or "")
    return "%d-%d" % (m.start(), m.end()) if m else MISSING


def classify_how(value):
    """值型 → 核验方式：数字/日期 → `numnorm`；其余逐字 → `contains`。

    空值 → 缺省标记（空值不判，判据层的既有口径）。
    """
    raw = str(value if value is not None else "").strip()
    if not raw:
        return MISSING
    if _NUMERIC_RE.match(raw) or _DATEISH_RE.match(raw):
        return "numnorm"
    return "contains"


def build_receipt(fact_id, source_sha256=None, span=None, face=None, how=None):
    """造一行收据：字段固定五元组，取不到的一律写缺省标记。

    收据是**观察**：只说「这条查过了、查到什么、怎么查的」，
    不产生任何判定码，也不改任何退出码。
    """
    return {
        "id": str(fact_id if fact_id not in (None, "") else MISSING),
        "sha16": sha16_of(source_sha256),
        "span": str(span) if span else MISSING,
        "face": str(face) if face else MISSING,
        "how": str(how) if how else MISSING,
    }


def norm_space(text):
    """空白归一（NBSP/窄空格→空格；连续空白→单空格）——字面比对用。"""
    out = []
    for ch in str(text or ""):
        out.append(" " if ch in _SPACEY else ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def contains_norm(value, text):
    """value（空白归一后）是否出现在 text（空白归一后）里。"""
    v = norm_space(value)
    if not v:
        return False
    return v in norm_space(text)
