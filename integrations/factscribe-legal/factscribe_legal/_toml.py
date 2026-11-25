"""TOML 读取层：让本包在 Python 3.10 上也能跑，且不引入任何第三方依赖。

为什么需要这一层
----------------
上游 factscribe 的 CI 矩阵是 Python 3.10–3.14，而标准库 `tomllib` 是 3.11 才有的。
本集成包若在模块顶层 `import tomllib`，在 3.10 上直接 ImportError —— 整个包装不上，
上游 CI 的 3.10 那一格会红。

解析器怎么选（一条环境只走一条路径，结论可复现）
--------------------------------------------------
1. **Python 3.11+**：标准库 `tomllib`。
2. **Python 3.10**：本文件自带的极简解析器 `mini_loads`。
3. 环境变量 `FACTSCRIBE_LEGAL_TOML=mini` 可强制走极简解析器 ——
   用来在没有 3.10 解释器的机器上验证那条兜底路径（`tests/test_toml_compat.py` 这么用）。

**为什么不直接复用上游 `factscribe.config.load_toml`？**
当初（2026-11-15）不复用的原因是上游那份 3.10 兜底解析器太弱：不认嵌套数组，
`nested = [["x"], ["y", "z"]]` 会被拆成 `[['x'], '["y"', '"z"']`。
**上游那份解析器已在 2026-11-25 重写成严格档**（坏 TOML 一律报错、嵌套数组正常读），
当年那条理由已经过期。本包仍自带一份极简解析器，理由换成两条：
1. 本包要能独立安装、独立运行，不把上游包变成运行依赖；
2. 自带的那份是**更保守**的子集 —— 子集之外的写法一律报错（fail closed），
   不猜、不静默跳过。

两条路径都必须与标准库 `tomllib` 在事实账用得到的子集上**读出同一个 dict**，
由 tests/test_toml_compat.py 的交叉校验锁住。

自带解析器的边界
----------------
只覆盖事实账用得到的子集：表、表数组、字符串、数组、数字、布尔。
子集之外的写法（内联表、多行字符串、日期时间）**直接报错**，不猜、不静默跳过
（沿用上游 "fail closed / no silent passes" 的规矩）。
"""
import os
import re
from pathlib import Path

__all__ = ["load_toml", "mini_loads", "parser_name", "TomlSubsetError"]


class TomlSubsetError(ValueError):
    """文件里有本解析器不覆盖的写法 —— fail closed，不猜。"""


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "b": "\b", "f": "\f"}


# --------------------------------------------------------------------------
# 极简解析器（3.10 兜底 / 交叉校验用）
# --------------------------------------------------------------------------

def _strip_comment(line):
    """去掉行尾注释；引号内的 # 不算注释。"""
    out = []
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
        i += 1
    if quote:
        raise TomlSubsetError("引号未闭合：%r" % line)
    return "".join(out)


def _parse_basic_string(s):
    """基本字符串：逐字扫到收尾引号；引号后面不许还有东西。

    旧实现只看首尾引号，「引号闭合之后还有内容」会被当成一条字符串收下（值还错了）。
    """
    if not s.startswith('"'):
        raise TomlSubsetError("不是基本字符串：%r" % s)
    out = []
    i = 1
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            i += 1
            if i >= len(s):
                raise TomlSubsetError("转义未结束：%r" % s)
            e = s[i]
            if e in _ESCAPES:
                out.append(_ESCAPES[e])
                i += 1
            elif e == "u":
                hexs = s[i + 1:i + 5]
                if len(hexs) != 4:
                    raise TomlSubsetError("坏的 \\u 转义：%r" % s)
                try:
                    out.append(chr(int(hexs, 16)))
                except ValueError:
                    raise TomlSubsetError("坏的 \\u 转义：%r" % s)
                i += 5
            else:
                raise TomlSubsetError("不认识的转义 \\%s：%r" % (e, s))
            continue
        if ch == '"':
            if i != len(s) - 1:
                raise TomlSubsetError("字符串后面有多余内容：%r" % s)
            return "".join(out)
        out.append(ch)
        i += 1
    raise TomlSubsetError("字符串未闭合：%r" % s)


def _parse_literal_string(s):
    """字面字符串：逐字扫到收尾引号（不解释转义）。"""
    if not s.startswith("'"):
        raise TomlSubsetError("不是字面字符串：%r" % s)
    i = 1
    while i < len(s):
        if s[i] == "'":
            if i != len(s) - 1:
                raise TomlSubsetError("字符串后面有多余内容：%r" % s)
            return s[1:i]
        i += 1
    raise TomlSubsetError("字符串未闭合：%r" % s)


# 整数/浮点的词法照标准库 tomllib：前导零、「1.」「.5」都不是合法写法。
_INT_RE = re.compile(r"[+-]?(?:0|[1-9](?:_?[0-9])*)")
_FLOAT_RE = re.compile(
    r"[+-]?(?:0|[1-9](?:_?[0-9])*)"
    r"(?:\.[0-9](?:_?[0-9])*)?(?:[eE][+-]?[0-9](?:_?[0-9])*)?")


def _parse_number(s):
    """数字：整数与浮点；前导零、缺小数位都按 tomllib 口径拒。"""
    body = s.replace("_", "")
    if _FLOAT_RE.fullmatch(body) and ("." in body or "e" in body or "E" in body):
        return float(body)
    if _INT_RE.fullmatch(body):
        return int(body)
    raise ValueError("不是合法数字：%r" % s)


def _split_items(body):
    """按顶层逗号切数组元素（引号内、嵌套括号内的逗号不算）。"""
    items = []
    cur = []
    depth = 0
    quote = None
    i = 0
    while i < len(body):
        ch = body[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(body):
                cur.append(body[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch == "[":
            depth += 1
            cur.append(ch)
        elif ch == "]":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if quote:
        raise TomlSubsetError("引号未闭合")
    tail = "".join(cur).strip()
    if tail:
        items.append(tail)
    return items


def _parse_value(raw):
    s = raw.strip()
    if not s:
        raise TomlSubsetError("空值")
    if s.startswith('"'):
        if s.startswith('"""'):
            raise TomlSubsetError("不覆盖多行字符串：%r" % raw)
        return _parse_basic_string(s)
    if s.startswith("'"):
        if s.startswith("'''"):
            raise TomlSubsetError("不覆盖多行字符串：%r" % raw)
        return _parse_literal_string(s)
    if s.startswith("["):
        if not s.endswith("]"):
            raise TomlSubsetError("数组未闭合：%r" % raw)
        body = s[1:-1].strip()
        if not body:
            return []
        return [_parse_value(it.strip()) for it in _split_items(body)]
    if s.startswith("{"):
        raise TomlSubsetError("不覆盖内联表：%r" % raw)
    if s in ("true", "false"):
        return s == "true"
    try:
        return _parse_number(s)
    except ValueError:
        raise TomlSubsetError("不认识的取值：%r" % raw)


def _unquote_key(k):
    k = k.strip()
    if len(k) >= 2 and k[0] == k[-1] and k[0] in "\"'":
        return k[1:-1]
    return k


def _split_dotted(path):
    """按点号分段；引号里的点号不算分隔符。"""
    parts = []
    cur = []
    quote = None
    for ch in path:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            cur.append(ch)
            continue
        if ch == ".":
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur))
    out = []
    for p in parts:
        p = _unquote_key(p.strip())
        if not p:
            raise TomlSubsetError("空表名：%r" % path)
        out.append(p)
    return out


def _table_for(root, path):
    cur = root
    for part in _split_dotted(path):
        nxt = cur.get(part)
        if nxt is None:
            nxt = {}
            cur[part] = nxt
        elif isinstance(nxt, list):
            # [[a.b]] 之后又出现 [a.b.c]：落到最后一个数组元素里
            nxt = nxt[-1]
        elif not isinstance(nxt, dict):
            raise TomlSubsetError("表名冲突：%r" % path)
        cur = nxt
    return cur


def mini_loads(text):
    """极简 TOML 解析：只覆盖事实账用得到的子集。

    与标准库 tomllib 同一口径：坏输入一律报错（fail closed）。
    重复键、重复表头、前导零、多行字符串这些"以前能悄悄收下"的写法，
    现在一律报错 —— 否则同一份事实账在 3.10 与 3.11+ 上读出的结果不同，
    门禁结论不可复现。
    """
    root = {}
    cur = root
    declared = set()   # 显式声明过的 [表] 路径（不许重复声明）
    arrays = set()     # 显式声明过的 [[表数组]] 路径
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        s = _strip_comment(raw).strip()
        if not s:
            continue
        if s.startswith("[["):
            if not s.endswith("]]"):
                raise TomlSubsetError("表数组头未闭合：%r" % raw)
            name = s[2:-2].strip()
            path = tuple(_split_dotted(name))
            if path in declared:
                raise TomlSubsetError("表 %r 与同名表数组冲突" % name)
            arrays.add(path)
            parent, _, leaf = name.rpartition(".")
            holder = _table_for(root, parent) if parent else root
            leaf = _unquote_key(leaf)
            arr = holder.setdefault(leaf, [])
            if not isinstance(arr, list):
                raise TomlSubsetError("[[%s]] 与同名表冲突" % name)
            cur = {}
            arr.append(cur)
            continue
        if s.startswith("["):
            if not s.endswith("]"):
                raise TomlSubsetError("表头未闭合：%r" % raw)
            name = s[1:-1].strip()
            path = tuple(_split_dotted(name))
            if path in declared or path in arrays:
                raise TomlSubsetError("表 %r 重复声明" % name)
            declared.add(path)
            cur = _table_for(root, name)
            continue
        if "=" not in s:
            raise TomlSubsetError("无法解析的行：%r" % raw)
        key, _, value = s.partition("=")
        key = key.strip()
        value = value.strip()
        # 多行数组
        while value.startswith("[") and value.count("[") > value.count("]") and i < len(lines):
            value += " " + _strip_comment(lines[i]).strip()
            i += 1
        parsed = _parse_value(value)
        if "." in key:
            parent, _, leaf = key.rpartition(".")
            target = _table_for(cur, parent)
        else:
            target, leaf = cur, key
        leaf = _unquote_key(leaf)
        if leaf in target:
            raise TomlSubsetError("键 %r 重复定义" % leaf)
        target[leaf] = parsed
    return root


# --------------------------------------------------------------------------
# 分发
# --------------------------------------------------------------------------

def _read_text(path):
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise TomlSubsetError("读不了 %s：%s" % (path, exc))
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TomlSubsetError("%s 不是合法 UTF-8：%s" % (path, exc))


def _resolve():
    forced = os.environ.get("FACTSCRIBE_LEGAL_TOML", "").strip().lower()
    if forced == "mini":
        return "mini", None
    try:
        import tomllib
    except ModuleNotFoundError:
        return "mini", None
    return "tomllib", tomllib


def parser_name():
    """当前实际用的解析器（写进报告/日志，便于复现时确认口径）。"""
    return _resolve()[0]


def load_toml(path):
    """读一个 TOML 文件，返回 dict。"""
    name, fn = _resolve()
    if name == "upstream":
        return fn(Path(path))
    text = _read_text(path)
    if name == "tomllib":
        return fn.loads(text)
    return mini_loads(text)
