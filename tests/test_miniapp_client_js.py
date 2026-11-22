"""Miniapp 前端（workbench 静态三件套）的静态闸。

两条闸：
  1. **const 被重新赋值**——2026-11-22 端到端验收实测：aad2e3e 给
     loadReport() 的 reportPath 追加 lang 参数时写成 "reportPath += ..."，
     而它是 const → 运行期 TypeError: Assignment to constant variable。
     后果不是「报告少一行」：异常发生在 openProject() 的 loadDisk() 里，
     整条打开链当场断掉——「记上次打开的盘」(/api/project/opened) 永不执行，
     last_disk 记忆、检查报告、机器视图同时失效。本闸把这一类错误挡在提交前。
  2. **三份副本必须逐字节一致**——真源是 factscribe/workbench/static/，
     miniapp/client/（宿主伺服的那份）与 vendored 引擎那份由 build.sh 同步。
     任何一份漂移＝宿主跑的和仓里测的不是同一份代码。

口径只管「静态可判的错」，不替代真浏览器验收。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = REPO_ROOT / "factscribe" / "workbench" / "static" / "app.js"
MIRRORS = (
    REPO_ROOT / "miniapp" / "miniapp" / "client" / "app.js",
    REPO_ROOT / "miniapp" / "miniapp" / "node" / "engine" / "factscribe"
    / "workbench" / "static" / "app.js",
)

# 声明：const x = / let x / var x
_DECL = re.compile(r"(?<![\w$])(const|let|var)\s+([A-Za-z_$][\w$]*)")
# 声明里的那个等号不是赋值，先抹掉
_DECL_ASSIGN = re.compile(r"(?<![\w$])(const|let|var)\s+([A-Za-z_$][\w$]*)\s*=")
# 真赋值：等号（非 ==/===）、复合赋值、自增自减
_ASSIGN = re.compile(
    r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*"
    r"(?:\+\+|--|&&=|\|\|=|\?\?=|\*\*=|<<=|>>=|[+\-*/%&|^]=|=(?!=))"
)


def _strip_noise(line: str) -> str:
    """抹掉字符串/模板串/行注释，剩下的才是真代码。"""
    out: list[str] = []
    i, n = 0, len(line)
    quote = None
    while i < n:
        ch = line[i]
        if quote:
            if ch == "\\":
                out.append(" ")
                i += 1
                if i < n:
                    out.append(" ")
                    i += 1
                continue
            if ch == quote:
                quote = None
            out.append(" ")
            i += 1
            continue
        if ch in "\"'" + chr(96):
            quote = ch
            out.append(" ")
            i += 1
            continue
        if ch == "/" and i + 1 < n and line[i + 1] == "/":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def const_reassignments(src: str) -> list[tuple[int, str, int, str]]:
    """找出「同一作用域里 const 绑定后来又被赋值」的地方。

    返回 (声明行, 变量名, 赋值行, 原始行文本)。
    作用域用花括号深度近似：赋值所在深度不得浅于声明所在深度，
    且中间若同名重新声明（let/var），以最近的那次声明为准。
    """
    depth = 0
    decls: list[tuple[str, str, int, int]] = []  # (name, kind, depth, line)
    hits: list[tuple[int, str, int, str]] = []
    for lineno, raw in enumerate(src.splitlines(), 1):
        code = _strip_noise(raw)
        scannable = _DECL_ASSIGN.sub(lambda m: " " * len(m.group(0)), code)
        for match in _ASSIGN.finditer(scannable):
            # 只认「语句开头」的赋值：模板串里的 title="${...}" 不是赋值。
            if scannable[: match.start()].strip():
                continue
            name = match.group(1)
            prev = None
            for decl in decls:
                if decl[0] == name and decl[3] < lineno:
                    prev = decl
            if prev and prev[1] == "const" and prev[2] <= depth:
                hits.append((prev[3], name, lineno, raw.strip()))
        for match in _DECL.finditer(code):
            decls.append((match.group(2), match.group(1), depth, lineno))
        depth += code.count("{") - code.count("}")
    return hits


def test_client_has_no_const_reassignment():
    """闸一：const 绑定不得被重新赋值（2026-11-22 的 P0 就是这么进来的）。"""
    hits = const_reassignments(CANONICAL.read_text(encoding="utf-8"))
    assert not hits, "客户端里存在 const 被重新赋值（运行期会抛 TypeError）：\n" + "\n".join(
        "  L{} 声明 {} → L{} 赋值：{}".format(*h) for h in hits
    )


def test_load_report_path_is_mutable():
    """闸一·定点：loadReport() 的 reportPath 要能被追加 lang 参数。"""
    src = CANONICAL.read_text(encoding="utf-8")
    body = src.split("async function loadReport(", 1)
    assert len(body) == 2, "找不到 loadReport()"
    fn = body[1][:1200]
    assert "let reportPath" in fn, "loadReport() 的 reportPath 必须是 let（要追加 lang 参数）"
    assert "const reportPath" not in fn, "reportPath 声明成 const 会被 += 撞死"


def test_miniapp_payload_copies_match_canonical():
    """闸二：真源与两份副本逐字节一致（宿主跑的和仓里测的是同一份）。"""
    canonical = CANONICAL.read_bytes()
    for mirror in MIRRORS:
        assert mirror.is_file(), f"副本缺失：{mirror}"
        assert mirror.read_bytes() == canonical, (
            f"副本与真源不一致：{mirror}（跑 miniapp/build.sh 同步）"
        )
