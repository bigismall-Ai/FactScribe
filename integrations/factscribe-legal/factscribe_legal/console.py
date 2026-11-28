# -*- coding: utf-8 -*-
"""控制台输出：非 UTF-8 控制台上，人读输出不许把命令自己搞崩。

背景（Windows 真机 winbox 实测，2026-11-26）：中文 Windows 的本地编码是
gbk/cp936（ACP=936），**编不出**人读输出里的装饰字符与部分带音标的拉丁
字母（`✓` / `🔴` / `ñ` …）。`print()` 撞上就抛 `UnicodeEncodeError`,
命令层把它当成「工具内部错误」，而不是这条命令本来的判定码与退出码。

真机实测原话（第①步只装 api 族时，接口层 JSON 出口）：

    > python -m factscribe_legal api contract --project fixtures\\legal-demo
    UnicodeEncodeError: 'gbk' codec can't encode character '\\xf1'
    （退出码 1；载荷里的西班牙语标题里有 `Constitución`）

修法（口径照上游 `factscribe/console.py`，本包自带一份以便独立运行）：
**降级的是字符，不是命令的判定**。

* 人读输出编不出来时，换成**同义的 ASCII**：装饰字符按表换
  （`✓`→`v`、`🔴`→`[红]`、`⚠`→`[!]`…）。表外的字符（含带音标的
  拉丁字母）**不折叠、不用问号**：按 backslashreplace 的规矩转义保留原
  字符（`ñ`→`\\xf1`、`Constitución`→`Constituci\\xf3n`）——
  问号分不清「通过」与「失败」，折叠会把 `Constitución` 悄悄改成
  `Constitucion`（文书名字被改了，语义就漂了）；转义写法信息不丢、可还原。
* **编码不动**：人读通道仍用它自己的编码（中文 Windows 上就是 cp936），
  所以重定向到文件的中文还是那个编码，外部读它的工具不用改。
* **JSON 通道单独走 UTF-8**（`write_json_text`）：JSON 是机器通道，载荷必须
  **逐字相同**（UTF-8 环境与 cp936 环境一个字节不差），所以 JSON 文本按
  UTF-8 字节出（RFC 8259：JSON 文本的交换编码就是 UTF-8）；人读通道的
  降级不碰它，载荷也不做 NFKD 折叠。
* macOS / Linux 的流本来就是 UTF-8，装上这套处理器**不改变任何一个字节**
  （UTF-8 能编下所有字符，处理器根本不会被叫醒）。

本包**不 import 上游**（可单独拷走单跑）⇒ 这份实现自带一份，
与上游同款口径、同款纪律。
"""
import codecs
import sys

__all__ = ["safe_stdio", "safe_stream", "write_json_text", "ERROR_HANDLER"]

# 编码错误处理器的名字（进程内唯一）。
ERROR_HANDLER = "factscribe_legal.safe"

# 装饰字符 → 同义 ASCII（表里的每一项都是本包真在用的字符）。
# 与上游 factscribe/console.py **共有八个字符的映射逐字相同**（`✓`→`v`、
# `✗`→`x`、`↔`→`<->`、`⇒`→`=>`、`⊆`→`<=`、`«`→`<<`、
# `»`→`>>`、`²`→`^2`），本包另加法律侧真在用的几个。
_ASCII_FALLBACK = {
    "✓": "v",      # U+2713 CHECK MARK —— 通过
    "✗": "x",      # U+2717 BALLOT X —— 失败
    "✔": "v",      # U+2714 HEAVY CHECK MARK
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

# 看不见的排版控制符：丢掉不丢信息（emoji 里的变体选择符、零宽连接符）。
# 不丢它会在降级后的行里留下一串噪声（"[!]\ufe0f"）。
_DROP_FORMAT = frozenset(chr(cp) for cp in
                          (0xFE0F, 0x200D, 0x200B, 0x200E, 0x200F))


def _escape_char(ch):
    """原字符的可逆转义写法（backslashreplace 同款）：不丢信息、不折叠。"""
    code = ord(ch)
    if code < 0x100:
        return "\\x%02x" % code
    if code <= 0xFFFF:
        return "\\u%04x" % code
    return "\\U%08x" % code


def _fallback_text(ch):
    """表外字符的降级写法：**不折叠、不用问号**，转义保留原字符。

    为什么不用问号（上游 factscribe/console.py 的表外兜底）：问号丢信息，
    而且分不清「通过」与「失败」。为什么不用 NFKD 折叠：折叠会把
    `Constitución` 悄悄改成 `Constitucion`——法律文书的名字被改了，
    语义就漂了（本单要钉死的「带音标的拉丁字母不要乱折」）。
    """
    return _escape_char(ch)


def _replace_handler(exc):
    """编码错误处理器：编不出来的字符换同义 ASCII（或转义保留），其余照旧。

    只处理「编码」方向的错（UnicodeEncodeError）；解码方向的错照旧抛
    出去（那是输入坏了，不该悄悄改）。
    """
    if not isinstance(exc, UnicodeEncodeError):
        raise exc
    chunk = exc.object[exc.start:exc.end]
    out = []
    for ch in chunk:
        if ch in _ASCII_FALLBACK:
            out.append(_ASCII_FALLBACK[ch])
        elif ch in _DROP_FORMAT:
            continue          # 看不见的排版符：丢掉不丢信息
        else:
            out.append(_fallback_text(ch))
    return ("".join(out), exc.end)


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
    """把 stdout/stderr 装上安全降级（幂等，可重复调用）。

    **CLI 入口统一调用**（见 cli.main）：法律侧全部子命令（既有 11 条
    ＋ api 族）在 cp936 上都不许因为人读输出里的装饰字符而崩。

    只换**错误处理器**，不换编码：流的编码是环境的事（中文 Windows 上
    就是 cp936），我们不替用户改；改的只是「编不出来时怎么办」。
    """
    for stream in (sys.stdout, sys.stderr):
        safe_stream(stream)


def write_json_text(text: str) -> None:
    """把 JSON 载荷按 **UTF-8 字节**写进 stdout（与控制台编码无关）。

    为什么单开一条通道：JSON 是机器通道，载荷必须**逐字相同**——UTF-8
    环境与 cp936 环境一个字节不差（人读通道的降级不许改写载荷，也不做
    NFKD 折叠）。RFC 8259 也说 JSON 文本的交换编码就是 UTF-8。

    换行翻译照文本层的规矩（Windows 上 "\n" → CRLF），所以 UTF-8 环境
    下这条通道的字节与改动前**逐字节相同**（零变化）。
    """
    stream = sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        # 不是 TextIOWrapper（测试替身/被换过的 stdout）：退回文本层。
        stream.write(text + "\n")
        return
    orig_encoding = getattr(stream, "encoding", None)
    orig_errors = getattr(stream, "errors", None)
    try:
        reconfigure(encoding="utf-8", errors="strict")
        stream.write(text + "\n")
        stream.flush()
    finally:
        if orig_encoding:
            try:
                reconfigure(encoding=orig_encoding,
                            errors=orig_errors or "strict")
            except (ValueError, OSError, LookupError):
                pass
