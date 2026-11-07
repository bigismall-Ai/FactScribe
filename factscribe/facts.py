# -*- coding: utf-8 -*-
"""数字归一化、Fact 模型、算式求值与 sha256。"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# --------------------------------------------------------------------------
# 数字归一化
# --------------------------------------------------------------------------

# 匹配一个“数字 + 可选量级/单位后缀 + 可选百分号”。
# - 前面不能紧跟字母/下划线/点：避开 ctex2017、v2.0、R2、H2O 这类；
# - 量级后缀必须紧贴数字（k/K/M/B），避免把 "47.3 ms" 读成 47.3 毫
# - 单位后缀（v1.1）：131s / 2220s / 53000token / 5GB 都是「数字＋量纲」，
#   数字照抽，单位只作噪声（不参与数值换算）。长单位排在短单位前，避免
#   "ms" 被 "m"、"tokens" 被 "tok" 抢先；量级 [kKMB] 排在单位之后，
#   所以 "5MB" 是单位、"5M" 仍是量级。
# - 百分号允许中间有空格（\% 掩码后就是 " %"），也接受 percent/pct 英文词
# - 科学计数法整体成 token（3e-4 / 1.2E+05），不拆成 3 和 4
# *** 匹配是 token 锚定的：不做子串匹配（红队 B1）***
_UNIT_RE = (
    r"(?:tokens|token|toks|tok|mins|min|ms|secs|sec|hrs|hr|"
    r"GiB|MiB|KiB|TiB|GB|MB|KB|TB|"
    r"x|×|s|h)"
)
_NUM_RE = re.compile(
    r"(?<![\w.])"
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"(" + _UNIT_RE + r"|[kKMB])?"
    r"(\s*(?:%|percent\b|pct\b))?"
    r"(?![\w])"
)

_MAGNITUDE = {"k": Decimal(1000), "m": Decimal(10 ** 6), "b": Decimal(10 ** 9)}

_FRACTION_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?![\d.])")

# LaTeX 的“千分位空格”：\, \; \: \! \~ 与 ~ 与 {,}。扫面时保留成长度不变的
# 哨兵字符，抽数字时据此把 "1 000 000" 合并成 1000000（红队 C4）。
THIN = "\x01"


def _num_key(d: Decimal) -> str:
    """把 Decimal 收敛成比较用的规范串：1234 / 0.9 / 0.625 / 53000 / 3500000。"""
    try:
        d = d.normalize()
    except InvalidOperation:
        return str(d)
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("", "-", "-0"):
        s = "0"
    return s


def number_key(token: str, suffix: str | None = None, percent: bool = False) -> str:
    try:
        d = Decimal(str(token).replace(",", ""))
    except InvalidOperation:
        return token
    if suffix:
        # 只有量级后缀换算数值；s / token / GB 这类单位只表示量纲，不换算。
        mag = _MAGNITUDE.get(suffix.lower())
        if mag is not None:
            d = d * mag
    if percent:
        d = d / Decimal(100)
    return _num_key(d)


def literal_tokens(value: str) -> list[tuple[str, str, bool]]:
    """value 里字面写出的数字 token：(raw, suffix, pct)。不做分数展开。"""
    out = []
    for m in _NUM_RE.finditer(str(value or "")):
        out.append((m.group(1), m.group(2) or "", bool(m.group(3))))
    return out


def fact_value_keys(value: str, include_quotient: bool = True) -> set[str]:
    """一个 fact.value 能接受的全部规范数字。

    除了字面数字，还接受：
    - 分数 a/b 的商（10/16 -> 0.625），并按 0~4 位小数放宽四舍五入；
    - 区间 10--16 的两端（NUM_RE 天然拆成两个）；
    - 百分号形式的裸数字（62.5% 同时接受 62.5）。

    注意：这是**值域**；v1 里它只有在内联绑定（\\fact{ID}）的语境下才算核销，
    全局裸数字命中只算黄（UNBOUND_NUMBER），不再能换来绿（红队 B1/C6/C11）。
    """
    keys: set[str] = set()
    for raw, suffix, pct in literal_tokens(value):
        keys.add(number_key(raw, suffix, pct))
        if pct:
            keys.add(number_key(raw, suffix, False))
    if include_quotient:
        for m in _FRACTION_RE.finditer(str(value or "")):
            try:
                num, den = Decimal(m.group(1)), Decimal(m.group(2))
            except InvalidOperation:
                continue
            if den == 0:
                continue
            q = num / den
            keys.add(_num_key(q))
            for places in range(0, 5):
                try:
                    keys.add(_num_key(q.quantize(Decimal(1).scaleb(-places))))
                except InvalidOperation:
                    pass
    return keys

@dataclass
class Fact:
    id: str
    claim: str = ""
    value: str = ""
    source: str = ""
    source_sha256: str = ""
    locator: str = ""
    confidence: str = ""
    kind: str = "claim"          # claim | config
    derived_from: list = field(default_factory=list)
    supersedes: list = field(default_factory=list)
    expr: str = ""
    metric: str = ""
    scope: str = ""
    note: str = ""
    file: str = ""
    line: int = 0
    value_keys: set = field(default_factory=set)

    @property
    def id_key(self) -> str:
        return self.id.strip().casefold()

    @property
    def is_derived(self) -> bool:
        return bool(self.derived_from) or bool(self.expr)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

# --------------------------------------------------------------------------
# derived 的 expr 求值：只允许四则运算与括号，ast 白名单，禁 eval（红队 B7）
# --------------------------------------------------------------------------

class ExprError(Exception):
    pass


_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
    ast.Attribute, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.UAdd, ast.USub,
)


def _numeric_parts(value: str) -> tuple[float, float]:
    """把 value 读成 (num, den)：'10/16' -> (10,16)；'56.25%' -> (56.25,1)。"""
    text = str(value).strip().replace(",", "")
    m = _FRACTION_RE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    toks = literal_tokens(text)
    if not toks:
        raise ExprError("父 fact 的 value 不是数值：%r" % value)
    raw = toks[0][0]
    return float(Decimal(raw)), 1.0


def eval_expr(expr: str, facts: dict[str, Fact]) -> float:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExprError("算式语法错：%s" % exc)
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExprError("算式里不许出现 %s（只允许四则运算、括号与 fact id）"
                            % type(node).__name__)

    def name_value(node) -> float:
        if isinstance(node, ast.Name):
            fid, attr = node.id, ""
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            fid, attr = node.value.id, node.attr
        else:
            raise ExprError("算式里的名字解析不了")
        f = facts.get(fid.strip().casefold())
        if f is None:
            raise ExprError("算式引用了不存在的 fact %r" % fid)
        num, den = _numeric_parts(f.value)
        if attr == "num":
            return num
        if attr == "den":
            return den
        if attr:
            raise ExprError("只支持 .num / .den，不支持 .%s" % attr)
        if den == 0:
            raise ExprError("父 fact %r 的分母为 0" % fid)
        return num / den

    def walk(node) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                raise ExprError("算式里只允许数字常量")
            return float(node.value)
        if isinstance(node, (ast.Name, ast.Attribute)):
            return name_value(node)
        if isinstance(node, ast.UnaryOp):
            v = walk(node.operand)
            return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp):
            a, b = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if b == 0:
                raise ExprError("算式除零")
            return a / b
        raise ExprError("算式节点不支持：%s" % type(node).__name__)

    return walk(tree)


def _declared_number(value: str) -> float:
    toks = literal_tokens(value)
    if not toks:
        raise ExprError("value 不是数值：%r" % value)
    return float(Decimal(toks[0][0].replace(",", "")))


def _cycles(facts: list[Fact]) -> list[list[str]]:
    graph = {f.id_key: [d.strip().casefold() for d in f.derived_from] for f in facts}
    color: dict[str, int] = {}
    stack: list[str] = []
    out: list[list[str]] = []

    def dfs(u: str) -> None:
        color[u] = 1
        stack.append(u)
        for v in graph.get(u, []):
            if v not in graph:
                continue
            if color.get(v, 0) == 0:
                dfs(v)
            elif color.get(v) == 1:
                if v in stack:
                    out.append(stack[stack.index(v):] + [v])
        stack.pop()
        color[u] = 2

    for k in graph:
        if color.get(k, 0) == 0:
            dfs(k)
    return out
