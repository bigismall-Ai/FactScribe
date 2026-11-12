#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一致性锁夹具投影成 JS 移植件可消费的 project.json（批 138）。

为什么需要这层：Python 原版（factscribe/audit.py）读的是磁盘上的项目目录，
JS 移植件（integrations/minifactscribe/miniapp/node/audit.mjs）读的是一个内存对象。
两边要在一起比对，就得先把项目「拍平」成双方都认的形状；这个脚本就是那条
唯一的投影路——两边吃同一份 project.json，才不会各说各话。

输出契约（docs/design/SPEC-CONFORMANCE.md §3）::

    {"name": "...",
     "manuscript": "<所有节按 main.tex 的 \\input 顺序拼接>",
     "bib": "<refs.bib 原文>",
     "sources": [{"id": "results/x.md", "text": "...", "sha256": "..."}],
     "facts": [{"id", "claim", "value", "source", "sourceSha256",
                "locator", "confidence", "derivedFrom", "expr"}]}

确定性约定：排序固定（facts 按 id、sources 按 id）、无时间戳、无绝对路径、
UTF-8 JSON、末尾一个换行。只读夹具，绝不改写它。

用法（仓根）::

    python3 scripts/conformance-dump.py tests/conformance/fixture
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from factscribe.config import ConfigError, load_config, load_facts  # noqa: E402

INPUT_RE = re.compile(r"\\(?:input|include|subfile)\s*\{([^{}]*)\}")


def _strip_comments(tex: str) -> str:
    """去掉 LaTeX 注释（`\\%` 是转义百分号，不算注释起点）。"""
    out = []
    for line in tex.split("\n"):
        i = 0
        cut = len(line)
        while i < len(line):
            if line[i] == "\\":
                i += 2
                continue
            if line[i] == "%":
                cut = i
                break
            i += 1
        out.append(line[:cut])
    return "\n".join(out)


def _input_order(main_tex: str) -> list[str]:
    """main.tex 里 `\\input/\\include/\\subfile` 的出现顺序（去重保序）。"""
    refs: list[str] = []
    for m in INPUT_RE.finditer(_strip_comments(main_tex)):
        ref = m.group(1).strip()
        if not ref or ref in refs:
            continue
        refs.append(ref)
    return refs


def _resolve_section(root: Path, ref: str) -> Path:
    for cand in (root / ref, root / (ref + ".tex")):
        if cand.is_file():
            return cand
    raise ConfigError("成文里 \\input 的节 %r 找不到——投影无法确定正文" % ref)


def build_payload(root: Path) -> dict:
    cfg = load_config(root)
    facts = load_facts(cfg)

    main_tex = root / (cfg.root_tex or "main.tex")
    if not main_tex.is_file():
        raise ConfigError("找不到 %s——没有成文就拼不出 manuscript" % main_tex.name)
    sections = [_resolve_section(root, ref)
                for ref in _input_order(main_tex.read_text(encoding="utf-8"))]
    if not sections:
        raise ConfigError("%s 里没有 \\input——拼接不出正文" % main_tex.name)

    # 文件边界不是句子边界：直接按顺序拼接，节间补一个换行保持行数稳定。
    manuscript = "\n".join(p.read_text(encoding="utf-8").rstrip("\n")
                           for p in sections) + "\n"

    bib_path = root / cfg.bib
    if not bib_path.is_file():
        raise ConfigError("找不到参考文献 %s——引用对账无从做起" % cfg.bib)
    bib = bib_path.read_text(encoding="utf-8")

    # 来源材料：只投影账上真正引用到的那些，按 id 排序。
    sources = []
    for sid in sorted({f.source.strip() for f in facts if f.source.strip()}):
        text = (root / sid).read_text(encoding="utf-8")
        sources.append({
            "id": sid,
            "text": text,
            # 现算的是「投影出去的这段文本」的哈希：JS 侧对 text 现算，
            # 两边算的是同一串字节（文件本身是 UTF-8 时两者相等）。
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })

    projected = []
    for f in sorted(facts, key=lambda x: x.id.casefold()):
        projected.append({
            "id": f.id,
            "claim": f.claim,
            "value": f.value,
            "source": f.source,
            "sourceSha256": f.source_sha256,
            "locator": f.locator,
            "confidence": f.confidence,
            "derivedFrom": list(f.derived_from),
            "expr": f.expr,
        })

    return {
        "name": cfg.title or cfg.name or root.name,
        "manuscript": manuscript,
        "bib": bib,
        "sources": sources,
        "facts": projected,
    }


def render(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法：python3 scripts/conformance-dump.py <夹具目录>", file=sys.stderr)
        return 2
    root = Path(argv[1]).resolve()
    if not root.is_dir():
        print("不是目录：%s" % argv[1], file=sys.stderr)
        return 2
    try:
        payload = build_payload(root)
    except ConfigError as exc:
        print("投影失败：%s" % exc, file=sys.stderr)
        return 2
    sys.stdout.write(render(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
