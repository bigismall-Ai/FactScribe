#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/gen_finding_i18n.py —— 发现文案 i18n 的脚手架生成器（只读扫描）。

把仓里所有 Issue(...) / Finding(...) 构造点扫出来，为每一条生成：

* key     —— 建议的 message_key（finding.<CODE>，同码多形态时加后缀）；
* zh      —— 从原中文 literal 机械推出来的模板（%s 转 {slot}）；
* args    —— 原 % 格式化实参的源码（槽位的取值来源）；
* params  —— 建议插进构造点的参数字典源码。

只读：本脚本不写任何文件，只把脚手架打到 stdout。生成出来的脚手架要人读
人改（英文文案是人写的），改完落进 factscribe/i18n.py。

用法：
    python3 scripts/gen_finding_i18n.py            # 人读脚手架
    python3 scripts/gen_finding_i18n.py --json     # 机读 JSON
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "factscribe"

# 实参表达式 → 槽位名的精确映射（拿不准就落到 argN，别猜语义）。
EXACT_SLOTS = {
    "f.id": "fact",
    "fact.id": "fact",
    "fact_id": "fact",
    "f.value": "value",
    "name": "name",
    "key": "key",
    "k": "key",
    "idx": "page",
    "exc": "detail",
    "str(exc)": "detail",
    "err": "detail",
    "str(err)": "detail",
}

# 后缀启发：表达式以这些词结尾时，槽位名取该词。
SUFFIX_SLOTS = ("name", "key", "file", "path", "line", "count", "chars",
                "page", "value", "ids", "field", "metric")

CONSTRUCTORS = {"Issue": 2, "Finding": 5}


def slot_name(expr, index):
    """给一个实参表达式起个槽位名。"""
    expr = expr.strip()
    if expr in EXACT_SLOTS:
        return EXACT_SLOTS[expr]
    if expr.startswith("str("):
        return "detail"
    if expr.startswith("f."):
        return "fact"
    base = expr
    for cut in ("[", ".", "("):
        base = base.split(cut)[0]
    base = base.strip()
    if not base.isidentifier():
        return "arg%d" % index
    name = "".join(ch if ch.isalnum() else "_" for ch in base).lower()
    name = name.strip("_")
    if not name or name in ("self", "cls", "str", "int", "float", "len"):
        return "arg%d" % index
    return name


def literal_template(node):
    """从一个表达式里取出 (模板, 实参列表)。

    只认三种形态：常量串、"..." % (a, b)、"..." % x。其余返回 None，
    交给人处理（脚手架里标 manual）。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, []
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        left = node.left
        if not (isinstance(left, ast.Constant) and isinstance(left.value, str)):
            return None
        right = node.right
        if isinstance(right, ast.Tuple):
            args = [ast.unparse(e) for e in right.elts]
        else:
            args = [ast.unparse(right)]
        return left.value, args
    return None


def _parse_spec(template, i):
    """解析 % 之后的转换说明：返回 (精度, 类型字符, 下一位置)。"""
    j = i + 1
    while j < len(template) and template[j] in "-+ #0":
        j += 1
    while j < len(template) and template[j].isdigit():
        j += 1
    prec = ""
    if j < len(template) and template[j] == ".":
        j += 1
        start = j
        while j < len(template) and template[j].isdigit():
            j += 1
        prec = template[start:j]
    if j >= len(template):
        return None
    return prec, template[j], j + 1


def convert(template, args):
    """%s / %r / %d / %.3g 等转 {slot}；实参预先按原转换格式化。"""
    slots = []
    used = {}
    out = []
    idx = 0
    i = 0
    while i < len(template):
        ch = template[i]
        if ch != "%":
            out.append(ch)
            i += 1
            continue
        if i + 1 < len(template) and template[i + 1] == "%":
            out.append("%")
            i += 2
            continue
        got = _parse_spec(template, i)
        if got is None:
            out.append(template[i:])
            break
        prec, tchar, nxt = got
        expr = args[idx] if idx < len(args) else ""
        base = slot_name(expr, idx)
        # 同一个表达式出现多次时槽位名要各不相同——同一表达式的
        # %-格式可能不同（%r 与 %s），共用一个名字会渲染错。
        seen = used.get(base, 0)
        name = base if seen == 0 else "%s%d" % (base, seen)
        used[base] = seen + 1
        out.append("{" + name + "}")
        if tchar == "s":
            value = "str(%s)" % expr
        elif tchar == "r":
            value = "repr(%s)" % expr
        elif tchar in "di":
            value = "str(int(%s))" % expr
        elif tchar in "fFeEgG":
            q = chr(34)
            value = ("format(%s, " + q + ".%s%s" + q + ")") % (expr, prec, tchar)
        else:
            value = "str(%s)" % expr
        slots.append({"name": name, "expr": expr, "spec": "%" + tchar,
                      "value": value})
        idx += 1
        i = nxt
    return "".join(out), slots


def code_of(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def scan():
    sites = []
    for path in sorted(PKG.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else None)
            if name not in CONSTRUCTORS:
                continue
            want = CONSTRUCTORS[name]
            if len(node.args) < want:
                continue
            if name == "Issue":
                code_node, msg_node = node.args[0], node.args[1]
            else:
                code_node, msg_node = node.args[0], node.args[4]
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            explicit_key = None
            explicit_expr = ""
            if "message_key" in kw:
                kk = kw["message_key"]
                if isinstance(kk, ast.Constant) and isinstance(kk.value, str):
                    explicit_key = kk.value
                else:
                    explicit_expr = ast.unparse(kk)
            params_keys = []
            has_params = "params" in kw
            if has_params and isinstance(kw["params"], ast.Dict):
                for kk in kw["params"].keys:
                    if isinstance(kk, ast.Constant) and isinstance(kk.value, str):
                        params_keys.append(kk.value)
            code = code_of(code_node)
            if code is None:
                # code 是变量（动态码）：也算一处发现，人写 key。
                sites.append({
                    "file": str(path.relative_to(ROOT)),
                    "line": node.lineno, "kind": name, "code": "VAR",
                    "end_line": node.end_lineno, "end_col": node.end_col_offset,
                    "manual": True, "zh": None, "slots": [],
                    "explicit_key": explicit_key, "explicit_expr": explicit_expr,
                    "params_keys": params_keys, "has_params": has_params,
                    "note": "variable code - human write",
                })
                continue
            got = literal_template(msg_node)
            if got is None:
                sites.append({
                    "file": str(path.relative_to(ROOT)),
                    "line": node.lineno, "kind": name, "code": code,
                    "manual": True, "zh": None, "slots": [],
                    "explicit_key": explicit_key, "explicit_expr": explicit_expr,
                    "params_keys": params_keys,
                    "has_params": has_params,
                    "note": "non-literal template - human write",
                })
                continue
            template, args = got
            zh, slots = convert(template, args)
            sites.append({
                "file": str(path.relative_to(ROOT)),
                "line": node.lineno, "kind": name, "code": code,
                "end_line": node.end_lineno, "end_col": node.end_col_offset,
                "manual": False, "zh": zh, "slots": slots,
                "explicit_key": explicit_key, "explicit_expr": explicit_expr,
                    "params_keys": params_keys,
                "has_params": has_params,
                "params_src": "{%s}" % ", ".join(
                    chr(34) + s["name"] + chr(34) + ": " + s["value"]
                    for s in slots),
            })
    return sites


def assign_keys(sites):
    """给每一处发现定 message_key。

    同一个 code 有多种文案形态时，按「形态首次出现的位置」排序：
    只有一种形态取 finding.<CODE>；多种形态依次取 finding.<CODE>.v2 /
    .v3 ……（同一形态的多个站点共用同一个 key——它们是同一条文案）。
    排序确定性：同一份仓跑两次结果一致。
    """
    by_code = {}
    for s in sites:
        if s["manual"]:
            continue
        by_code.setdefault(s["code"], []).append(s)
    for code, group in by_code.items():
        group.sort(key=lambda s: (s["file"], s["line"]))
        order = []
        for s in group:
            if s["zh"] not in order:
                order.append(s["zh"])
        if len(order) == 1:
            for s in group:
                s["key"] = "finding." + code
            continue
        for s in group:
            s["key"] = "finding.%s.v%d" % (code, order.index(s["zh"]) + 2)
    for s in sites:
        if s.get("explicit_key"):
            s["key"] = s["explicit_key"]
        elif s["manual"]:
            s["key"] = "finding." + s["code"]
    return sites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    sites = assign_keys(scan())
    if args.json:
        print(json.dumps(sites, ensure_ascii=False, indent=2))
        return 0
    for s in sites:
        print("%s:%d  [%s] %s" % (s["file"], s["line"], s["kind"], s["code"]))
        if s["manual"]:
            print("    MANUAL")
            continue
        print("    zh: %s" % s["zh"])
        print("    params: %s" % (s["params_src"] or "{}"))
    print("")
    print("sites: %d ; manual: %d" % (
        len(sites), sum(1 for s in sites if s["manual"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
