"""事实账同值检测（只读）：``scan_dupes``。

分工（P-100 松尾账①拆分）：**检测与改账分家**——本模块只读地扫出
「同值且 claim 不同」的事实清单；会改写 ``facts/*.toml`` 的 ``dup_ok``
标注（写径）在独立维护模块 ``ledger_maint.py``，不与检测同居。

上游 FactScribe 的 R-04 规则：**同一个值挂在不同 claim 上**时会报
`DUPLICATE_VALUE`（黄），
确属同一个数（例如：法国侧参考日与中国侧参考日是同一天；某法公布日与施行日同为一天）
要显式写 `dup_ok = true` 承认同值。
"""
import os
import re

FACT_BLOCK = re.compile(r"\[\[fact\]\]\n(.*?)(?=\n\[\[fact\]\]|\Z)", re.S)


def _fields(block):
    out = {}
    for m in re.finditer(r'^(\w+)\s*=\s*"(.*)"\s*$', block, re.M):
        out[m.group(1)] = m.group(2)
    return out


def scan_dupes(project_dir):
    """返回 [(文件, id, value)]：同值且 claim 不同的事实。"""
    facts_dir = os.path.join(project_dir, "facts")
    by_value = {}
    allfacts = []
    if not os.path.isdir(facts_dir):
        return []
    for fn in sorted(os.listdir(facts_dir)):
        if not fn.endswith(".toml"):
            continue
        path = os.path.join(facts_dir, fn)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for m in FACT_BLOCK.finditer(text):
            fl = _fields(m.group(1))
            if "id" in fl and "value" in fl:
                rec = {"file": path, "id": fl["id"], "value": fl["value"],
                       "claim": fl.get("claim", ""), "block": m.group(1)}
                allfacts.append(rec)
                by_value.setdefault(fl["value"], []).append(rec)
    dupes = []
    for val, group in by_value.items():
        if len(group) > 1 and len({g["claim"] for g in group}) > 1:
            for g in group:
                dupes.append((g["file"], g["id"], val))
    return dupes, allfacts
