#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从论文的 GLOSSARY.md 生成论文术语表（可重跑，覆盖生成）。

来源：``../paper-zh/GLOSSARY.md``（Markdown 表格：英文 | 中文 | 备注）。
输出：``factscribe/terms/paper.tsv``（五列，Tab 分隔）：

    canonical  aliases(en)  aliases(cn)  category  blocked(cn)

* canonical 取表格的中文列（括号里的说明剥掉）；
* aliases(en) 取英文列（``/``、``／`` 分隔的多写法拆开）；
* aliases(cn) 取中文列里 ``／`` 分隔的并列写法；
* ``blocked(cn)`` 是备注里「不写「X」「Y」」声明的**禁用变体**——它们仍进
  匹配表（同义词归一时视同正名），但 ``TERM_VARIANT`` 会单独按禁用变体报。

缺失来源时跳过并提示（退出码 0），不阻断流水线。GLOSSARY.md 尚未收录、
但属于论文方法学常用词的少量条目放在 ``PAPER_SUPPLEMENT``，与表格同源
生成，保证重跑结果稳定。

用法：
    env PYTHONPATH=src python3 scripts/import-glossary.py
    env PYTHONPATH=src python3 scripts/import-glossary.py --source <md> --out <tsv>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO.parent / "paper-zh" / "GLOSSARY.md"
DEFAULT_OUT = REPO / "factscribe" / "terms" / "paper.tsv"
GENERATED_BY = "env PYTHONPATH=src python3 scripts/import-glossary.py"

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_BLOCKED_RE = re.compile(r"不写((?:「[^」]+」[与和、]?)+)")
_PAREN_RE = re.compile(r"[（(][^）)]*[）)]")

# GLOSSARY.md 未收、但论文方法学常用的少量词条；只补正名与禁用变体，
# 不引入工作区流程词。可重跑：每次生成都在表格行之后追加。
PAPER_SUPPLEMENT = [
    ("预注册", ["preregistration"], [], "论文术语",
     ["事前登记", "预先登记"]),
]


def _split_multi(value: str) -> list[str]:
    parts = re.split(r"\s*[/／|]\s*", value.strip())
    return [p.strip() for p in parts if p.strip()]


def _strip_paren(value: str) -> str:
    return _PAREN_RE.sub("", value).strip()


def parse_blocked(note: str) -> list[str]:
    """备注里「不写「X」「Y」」→ 禁用变体列表（保留首次出现顺序）。"""
    out: list[str] = []
    for m in _BLOCKED_RE.finditer(note or ""):
        for form in re.findall(r"「([^」]+)」", m.group(1)):
            form = form.strip()
            if form and form not in out:
                out.append(form)
    return out


def read_table(path: Path) -> list[tuple[str, list[str], list[str], str, list[str]]]:
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = _TABLE_ROW_RE.match(raw)
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 3:
            continue
        en, zh, note = cells[0], cells[1], cells[2]
        if not en or not zh or en.lower() in ("english", "英文"):
            continue
        if zh == "中文":
            continue
        if set(en) <= set("-: "):
            continue
        # 「保留英文」「保留 trial」是排版约定，不是术语条目。
        if zh.startswith("保留"):
            continue
        canonical = _strip_paren(zh) or zh
        zh_parts = _split_multi(zh)
        en_parts = _split_multi(en)
        # 「指针／对象存储」这类并列概念当成两条术语，而不是同一 canonical
        # 的两种写法——否则 TERM_VARIANT 会把两个概念误报成用词不一致。
        if len(zh_parts) > 1 and len(zh_parts) == len(en_parts):
            for zh_part, en_part in zip(zh_parts, en_parts):
                rows.append((zh_part, [en_part], [], "论文术语",
                             parse_blocked(note)))
            continue
        en_forms = [x for x in en_parts if x != canonical]
        cn_forms = [x for x in zh_parts
                    if x and x != canonical and x != zh]
        rows.append((canonical, en_forms, cn_forms, "论文术语",
                     parse_blocked(note)))
    return rows


def build_rows(source: Path) -> list[tuple[str, list[str], list[str], str, list[str]]]:
    rows = read_table(source)
    seen = {canonical for canonical, *_ in rows}
    for canonical, en, cn, category, blocked in PAPER_SUPPLEMENT:
        if canonical in seen:
            continue
        rows.append((canonical, list(en), list(cn), category, list(blocked)))
        seen.add(canonical)
    return rows


def check_collisions(rows) -> None:
    seen: dict[str, str] = {}
    for canonical, en_forms, cn_forms, _cat, blocked in rows:
        for form in [canonical, *en_forms, *cn_forms, *blocked]:
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
    forms = sum(1 + len(en) + len(cn) + len(blocked)
                for _canonical, en, cn, _cat, blocked in rows)
    lines = [
        "# factscribe 论文术语表——由 scripts/import-glossary.py 覆盖生成，请勿手改。",
        "# 来源：%s（表格：英文 | 中文 | 备注）" % _display_path(source),
        "# 备注里的「不写「X」」进 blocked(cn) 列：仍是同义匹配形式，但按禁用变体报。",
        "# 生成命令：%s" % GENERATED_BY,
        "# 规模：%d 个 canonical，%d 个表面形式" % (len(rows), forms),
        "canonical\taliases(en)\taliases(cn)\tcategory\tblocked(cn)",
    ]
    for canonical, en_forms, cn_forms, category, blocked in rows:
        lines.append("\t".join([canonical, "|".join(en_forms),
                                "|".join(cn_forms), category,
                                "|".join(blocked)]))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="从 GLOSSARY.md 生成论文术语表")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE),
                        help="GLOSSARY.md（默认 %(default)s）")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="输出 TSV（默认 %(default)s）")
    args = parser.parse_args(argv)
    source = Path(args.source).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    if not source.is_file():
        print("跳过：来源 %s 不存在，保留现有 %s" % (source, out))
        return 0
    rows = build_rows(source)
    if not rows:
        print("跳过：%s 里没有可导入的术语行" % source)
        return 0
    check_collisions(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rows, source), encoding="utf-8")
    print("导入 %d 个 canonical 到 %s" % (len(rows), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
