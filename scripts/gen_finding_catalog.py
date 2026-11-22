#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/gen_finding_catalog.py —— 把脚手架与英译合成 factscribe/i18n.py 的目录。

输入：
* scripts/gen_finding_i18n.py 产出的脚手架 JSON（zh 模板与槽位）；
* 各分组的英译 JSON（{key: {"en": ...}}）；
* 手写条目 JSON（动态码那几处，zh 与 en 都人写）。

输出：就地改写 factscribe/i18n.py 里 BEGIN/END FINDING_MESSAGES 之间的数据块。
zh 模板取自脚手架（与真闸原中文 message 逐字一致）；en 模板取自英译文件。
英译文件里的槽位名可能是 {slot0} 形态——本脚本按脚手架的槽位顺序映射回
真实槽位名。

用法：
    python3 scripts/gen_finding_catalog.py --scaffold /tmp/scaffold.json \\
        --en /tmp/fs_i18n/group_A.en.json --en /tmp/fs_i18n/group_B.en.json \\
        --en /tmp/fs_i18n/group_C.en.json --manual /tmp/fs_i18n/manual.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "factscribe" / "i18n.py"
BEGIN = "# --- BEGIN FINDING_MESSAGES ---"
END = "# --- END FINDING_MESSAGES ---"

_SLOT_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def remap_slots(text, slots):
    """把英译里的 {slotN} 换回脚手架的真实槽位名。"""
    def sub(match):
        name = match.group(1)
        if name.startswith("slot") and name[4:].isdigit():
            idx = int(name[4:])
            if idx < len(slots):
                return "{" + slots[idx]["name"] + "}"
        return match.group(0)

    return _SLOT_RE.sub(sub, text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scaffold", required=True)
    ap.add_argument("--en", action="append", default=[])
    ap.add_argument("--manual", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sites = json.loads(Path(args.scaffold).read_text(encoding="utf-8"))
    en_all = {}
    for path in args.en:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for key, entry in data.items():
            en_all[key] = entry["en"] if isinstance(entry, dict) else entry

    manual = {}
    for path in args.manual:
        manual.update(json.loads(Path(path).read_text(encoding="utf-8")))

    by_key = {s["key"]: s for s in sites if not s.get("manual")}
    missing = sorted(k for k in by_key if k not in en_all and k not in manual)
    extra = sorted(k for k in en_all if k not in by_key and k not in manual)

    entries = {}
    for key, site in by_key.items():
        en = en_all.get(key, "")
        if not en:
            continue
        entries[key] = {"zh": site["zh"], "en": remap_slots(en, site["slots"])}
    for key, entry in manual.items():
        entries[key] = {k: v for k, v in entry.items() if k in ("zh", "en")}

    lines = ["FINDING_MESSAGES: dict = {"]
    for key in sorted(entries):
        entry = entries[key]
        lines.append("    %s: {" % json.dumps(key, ensure_ascii=False))
        if entry.get("zh"):
            lines.append("        " + json.dumps("zh", ensure_ascii=False) + ": "
                         + json.dumps(entry["zh"], ensure_ascii=False) + ",")
        if entry.get("en"):
            lines.append("        " + json.dumps("en", ensure_ascii=False) + ": "
                         + json.dumps(entry["en"], ensure_ascii=False) + ",")
        lines.append("    },")
    lines.append("}")
    block = "\n".join(lines)

    print("scaffold keys: %d ; en provided: %d ; manual: %d ; missing en: %d"
          % (len(by_key), len(en_all), len(manual), len(missing)))
    if missing:
        print("missing en for:")
        for key in missing:
            print("   ", key)
    if extra:
        print("en keys not in scaffold:")
        for key in extra:
            print("   ", key)
    if args.dry_run:
        print(block)
        return 0

    src = I18N.read_text(encoding="utf-8")
    i = src.index(BEGIN)
    j = src.index(END)
    new = src[:i + len(BEGIN)] + "\n" + block + "\n" + src[j:]
    I18N.write_text(new, encoding="utf-8")
    print("wrote %s (%d entries)" % (I18N, len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
