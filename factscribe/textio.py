# -*- coding: utf-8 -*-
"""用户正文内容的换行保真读写。

事项约定：**保存必须逐字保留正文内容**——用户正文（论文正文 `.tex`、
参考文献 `.bib`、事实账、项目声明、术语表）里的任何字符，**包括行尾**，
都不许被保存链路改写。

Windows 上默认文本模式两头都动手：

* **写**：`newline=None`（默认）时，任何 `'\n'` 都被翻译成 `os.linesep`
  （Windows 上是 `'\r\n'`）；已经存在的 `'\r\n'` 会被写成
  `'\r\r\n'`——CR 被复制，是内容损坏。
* **读**：`newline=None`（默认）时做通用换行翻译（universal newlines），
  `'\r\n'` 被读成 `'\n'`。于是「读入 → 编辑 → 写回」跑一遍，正文的
  行尾就被悄悄换掉了——这同样违反「逐字保留」。

这里统一收口：

* **读**用 `newline=""`：不做任何换行翻译，`'\r\n'` 原样留在字符串里；
* **写**用 `newline=""`：不翻译，`'\n'` 就是 `'\n'`，`'\r\n'` 就是
  `'\r\n'`。

换行交还给人：文件里原本是什么行尾，写回还是什么行尾，一个字符不多、
一个字符不少。

机器产物（JSON 报告、审计矩阵、证据锁、清单 manifest、日志……）**不用**
这一套——它们是工具自己生成、自己消费，格式由工具定，行尾统一成 `'\n'`
反而更可预期。哪些算「用户内容」、划分依据见
`docs/design/SPEC-V3.0.md` 与本次修复的交付报告。
"""
from __future__ import annotations

from pathlib import Path

__all__ = [
    "read_text_exact",
    "write_text_exact",
    "split_keepends",
    "dominant_newline",
]


def read_text_exact(path: Path | str, errors: str | None = None) -> str:
    """按原样读文本：不做通用换行翻译，`'\r\n'` 原样保留。

    与 `Path.read_text()` 的差别只有一处——换行。其它行为一致：
    按 UTF-8 解码（非 UTF-8 抛 `UnicodeDecodeError`，读不动抛
    `OSError`），不剥离 BOM，不动末尾换行。

    `errors` 透传给 `open()`：`"replace"` 时坏字节换成 U+FFFD，
    与 `Path.read_text(errors="replace")` 行为一致。
    """
    with open(path, "r", encoding="utf-8", newline="", errors=errors) as handle:
        return handle.read()


def write_text_exact(path: Path | str, text: str) -> None:
    """按原样写文本：`'\n'` 不翻译成 `'\r\n'`，`'\r\n'` 不变成
    `'\r\r\n'`。写出去的字节与传进来的字符串逐字节对应。"""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def split_keepends(text: str) -> list[tuple[str, str]]:
    """把文本切成 `[(行内容, 行尾), ...]`，行尾**原样保留**。

    `str.splitlines()` 会把行尾吃掉——重建时行尾就丢了（CRLF 的文件会被
    悄悄改成 LF）。这里把行尾单独摘出来，改哪一行都不影响其它行的行尾。
    """
    out: list[tuple[str, str]] = []
    index = 0
    size = len(text)
    while index < size:
        stop = index
        while stop < size and text[stop] not in "\r\n":
            stop += 1
        if stop >= size:
            out.append((text[index:stop], ""))
            break
        if text[stop] == "\r" and stop + 1 < size and text[stop + 1] == "\n":
            end = stop + 2
        else:
            end = stop + 1
        out.append((text[index:stop], text[stop:end]))
        index = end
    return out


def dominant_newline(text: str, default: str = "\n") -> str:
    """文本里占多数的行尾（`'\r\n'` / `'\n'` / `'\r'`）。

    追加内容时用它做新行的行尾：CRLF 的文件补进去的也是 CRLF，不会补出
    一份混合行尾的文件。一行行尾都没有时用 `default`。
    """
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    best = max(crlf, lf, cr)
    if best <= 0:
        return default
    if crlf == best:
        return "\r\n"
    if lf == best:
        return "\n"
    return "\r"
