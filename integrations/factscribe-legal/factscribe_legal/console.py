# -*- coding: utf-8 -*-
r"""控制台输出：非 UTF-8 控制台上，人读输出不许把命令自己搞崩。

背景（Windows 真机 winbox 实测，2026-11-26）：中文 Windows 的本地编码是
gbk/cp936（ACP=936），**编不出**人读输出里的装饰字符与部分拉丁字母
（`✓` / `🔴` / `ñ` …）。`print()` 撞上就抛 `UnicodeEncodeError`,
命令层把它当成「工具内部错误」，而不是这条命令本来的判定码与退出码。

真机实测原话（接口层 JSON 出口）：

    > python -m factscribe_legal api contract --project fixtures\legal-demo
    UnicodeEncodeError: 'gbk' codec can't encode character '\xf1'
    （退出码 1；载荷里的西班牙语标题里有 `Constitución`）

修法（口径照上游 `factscribe/console.py`，本包自带一份以便独立运行）：
**降级的是字符，不是命令的判定**。

* 人读输出编不出来时，换成**同义的 ASCII**：装饰字符按表换
  （`✓`→`v`、`🔴`→`[红]`、`→`→`->`…），带音标的拉丁字母按
  NFKD 折叠（`ñ`→`n`、`é`→`e`、`ü`→`u`…），语义不丢；
  表外与折不出 ASCII 的字换 `?`（不炸就行）。
* **编码不动**：流仍用它自己的编码（中文 Windows 上就是 cp936），
  所以重定向到文件的中文还是那个编码，外部读它的工具不用改。
* macOS / Linux 的流本来就是 UTF-8，装上这套处理器**不改变任何一个字节**
  （UTF-8 能编下所有字符，处理器根本不会被叫醒）。

本包**不 import 上游**（可单独拷走单跑）⇒ 这份实现自带一份，
与上游同款口径、同款纪律。
"""
import codecs
import sys
import unicodedata

__all__ = ["safe_stdio", "safe_stream", "ERROR_HANDLER"]

# 编码错误处理器的名字（进程内唯一）。
ERROR_HANDLER = "factscribe_legal.safe"

# 装饰字符 → 同义 ASCII（表里的每一项都是本包真在用的字符）
_ASCII_FALLBACK = {
    "✓": "v",      # U+2713 CHECK MARK —— 通过
    "✗": "x",      # U+2717 BALLOT X —— 失败
    "✔": "v",
    "↔": "<->",    # U+2194 LEFT RIGHT ARROW
    "⇒": "=>",     # U+21D2 RIGHTWARDS DOUBLE ARROW
    "→": "->",     # U+2192 RIGHTWARDS ARROW
    "⊆": "<=",     # U+2286 SUBSET OF OR EQUAL TO
    "«": "<<",     # U+00AB
    "»": ">>",     # U+00BB
    "²": "^2",     # U+00B2
    "…": "...",    # U+2026 HORIZONTAL ELLIPSIS
    "•": "*",      # U+2022 BULLET
    "·": "-",      # U+00B7 MIDDLE DOT
    "—": "-",      # U+2014 EM DASH
    "–": "-",      # U+2013 EN DASH
    "｜": "|",     # U+FF5C FULLWIDTH VERTICAL LINE
    "🔴": "[红]",   # U+1F534 RED CIRCLE
    "🟡": "[黄]",   # U+1F7E1 YELLOW CIRCLE
    "🟢": "[绿]",   # U+1F7E2 GREEN CIRCLE
    "⚠": "[!]",    # U+26A0 WARNING SIGN
    "✅": "[OK]",  # U+2705 WHITE HEAVY CHECK MARK
}

# 折不出 ASCII 的拉丁字母（NFKD 对它们没辙，手工给同义形）
_MANUAL_FOLD = {
    "ø": "o", "Ø": "O",
    "ß": "ss",
    "æ": "ae", "Æ": "AE",
    "œ": "oe", "Œ": "OE",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "þ": "th", "Þ": "TH",
    "ð": "d", "Ð": "D",
    "ı": "i",
}


def _fold(ch):
    """单个字符 → 同义 ASCII（折不出就空串）。"""
    if ch in _ASCII_FALLBACK:
        return _ASCII_FALLBACK[ch]
    if ch in _MANUAL_FOLD:
        return _MANUAL_FOLD[ch]
    if ord(ch) < 128:
        return ch
    decomposed = unicodedata.normalize("NFKD", ch)
    stripped = "".join(c for c in decomposed
                        if not unicodedata.combining(c))
    return stripped if stripped and all(ord(c) < 128 for c in stripped) else ""


def _replace_handler(exc):
    """编码错误处理器：编不出来的字符换同义 ASCII，其余照旧。

    只处理「编码」方向的错（UnicodeEncodeError）；解码方向的错照旧抛
    出去（那是输入坏了，不该悄悄改）。
    """
    if not isinstance(exc, UnicodeEncodeError):
        raise exc
    chunk = exc.object[exc.start:exc.end]
    out = "".join(_fold(ch) or "?" for ch in chunk)
    return (out, exc.end)


def _register_handler() -> None:
    """注册处理器（进程内一次就够；重复注册同名会报错，所以先查）。"""
    try:
        codecs.lookup_error(ERROR_HANDLER)
    except LookupError:
        codecs.register_error(ERROR_HANDLER, _replace_handler)


def safe_stream(stream) -> bool:
    """给一个文本流装上「安全降级」的编码错误处理器。

    返回是否真的装了：流不是 `TextIOWrapper`（测试里常见的 StringIO、
    被换过的 stdout）或重配失败 → 返回 False，不抛。
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return False
    _register_handler()
    try:
        reconfigure(errors=ERROR_HANDLER)
    except (ValueError, OSError, LookupError):
        return False
    return True


def safe_stdio() -> None:
    """CLI 入口统一把 stdout/stderr 装上安全降级（幂等，可重复调用）。

    只换**错误处理器**，不换编码：流的编码是环境的事（中文 Windows 上
    就是 cp936），我们不替用户改；改的只是「编不出来时怎么办」。
    """
    for stream in (sys.stdout, sys.stderr):
        safe_stream(stream)
