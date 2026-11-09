#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 sia-harness 词册一次性导入术语表（可重跑，覆盖生成）。

来源：``../sia-harness/nomenclator/terms/*.yaml``（相对本仓根）。
输出：``factscribe/terms/glossary.tsv``（四列，Tab 分隔）。

只读取词册的 ``id`` / ``en`` / ``cn`` / ``aliases`` / ``category`` 字段；
词册是简单键值 + 单行 flow 列表，这里用标准库解析，避免给运行时添依赖。
canonical 取 ``cn``；``en`` 与拉丁别名进 aliases(en)，中文别名进 aliases(cn)。
表面形式冲突（同一形式指向两个 canonical）直接报错退出，不静默错归。

用法：
    env PYTHONPATH=src python3 scripts/import-terms.py
    env PYTHONPATH=src python3 scripts/import-terms.py --source <词册目录> --out <tsv>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO.parent / "sia-harness" / "nomenclator" / "terms"
DEFAULT_OUT = REPO / "factscribe" / "terms" / "glossary.tsv"
GENERATED_BY = "env PYTHONPATH=src python3 scripts/import-terms.py"

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_FIELD_RE = re.compile(r"^([A-Za-z_]+):\s*(.*)$")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_aliases(value: str) -> list[str]:
    value = value.strip()
    if not value.startswith("["):
        return []
    body = value[1:]
    end = body.rfind("]")
    if end >= 0:
        body = body[:end]
    if not body.strip():
        return []
    out = []
    for part in body.split(","):
        part = _unquote(part)
        if part:
            out.append(part)
    return out


def read_term(path: Path) -> dict:
    fields: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = _FIELD_RE.match(raw)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if key in ("id", "en", "cn", "category"):
            fields[key] = _unquote(value)
        elif key == "aliases":
            fields["aliases"] = _parse_aliases(value)
    if not fields.get("en") and not fields.get("cn"):
        raise SystemExit("词册缺少 en/cn：%s" % path)
    return fields


def build_rows(source: Path) -> list[tuple[str, list[str], list[str], str]]:
    files = sorted(source.glob("*.yaml")) + sorted(source.glob("*.yml"))
    if not files:
        raise SystemExit("源目录没有词册文件：%s" % source)
    rows = []
    for path in files:
        term = read_term(path)
        canonical = term.get("cn") or term["en"]
        en_forms: list[str] = []
        cn_forms: list[str] = []
        en = term.get("en", "").strip()
        if en and en != canonical:
            en_forms.append(en)
        for alias in term.get("aliases") or []:
            if alias == canonical:
                continue
            (cn_forms if _CJK_RE.search(alias) else en_forms).append(alias)
        rows.append((canonical, en_forms, cn_forms,
                     term.get("category") or "未分类"))
    return rows


def check_collisions(rows) -> None:
    seen: dict[str, str] = {}
    for canonical, en_forms, cn_forms, _cat in rows:
        for form in [canonical, *en_forms, *cn_forms]:
            key = form.strip().lower()
            if not key:
                continue
            owner = seen.get(key)
            if owner is not None and owner != canonical:
                raise SystemExit("表面形式冲突：「%s」同时属于「%s」与「%s」"
                                 % (form, owner, canonical))
            seen[key] = canonical


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO.parent))
    except ValueError:
        return str(path)


def render(rows, source: Path) -> str:
    forms = sum(1 + len(en) + len(cn)
                for _canonical, en, cn, _cat in rows)
    lines = [
        "# factscribe 术语表——由 scripts/import-terms.py 覆盖生成，请勿手改。",
        "# 来源：%s/*.yaml" % _display_path(source),
        "# 生成命令：%s" % GENERATED_BY,
        "# 规模：%d 个 canonical，%d 个表面形式" % (len(rows), forms),
        "canonical\taliases(en)\taliases(cn)\tcategory",
    ]
    for canonical, en_forms, cn_forms, category in rows:
        lines.append("\t".join([canonical, "|".join(en_forms),
                                "|".join(cn_forms), category]))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="导入 sia-harness 词册为术语表")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE),
                        help="词册目录（默认 %(default)s）")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="输出 TSV（默认 %(default)s）")
    args = parser.parse_args(argv)
    source = Path(args.source).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    if not source.is_dir():
        raise SystemExit("源目录不存在：%s" % source)
    rows = build_rows(source)
    check_collisions(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rows, source), encoding="utf-8")
    print("导入 %d 个 canonical 到 %s" % (len(rows), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
