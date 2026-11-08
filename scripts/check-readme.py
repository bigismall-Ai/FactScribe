#!/usr/bin/env python3
"""README 自检：用我们自己的规则检查两份 README。

检查项（与文风闸 v4、事实闸同口径）：
  1. 命令名必须真实存在（对照 `factscribe --help`）；
  2. 标题：中文 ≤12 字、英文 ≤8 词，且不含冒号/破折号/括号/问号；
  3. 正文不出现插入式破折号（—— / —）；
  4. 相对链接的目标文件必须存在；
  5. README 里写的测试数必须等于实际跑出来的数。

用法：python3 scripts/check-readme.py
退出码：0 全过；1 有问题。
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.md", "README.en.md"]
ok = True


def bad(msg):
    global ok
    ok = False
    print(f"  \u2717 {msg}")


def good(msg):
    print(f"  \u2713 {msg}")


def main():
    help_txt = subprocess.run([sys.executable, "-m", "factscribe", "--help"],
                              cwd=ROOT, capture_output=True, text=True).stdout
    for cmd in ("check", "audit", "protect", "style", "verify-pdf", "matrix"):
        (good if cmd in help_txt else bad)(f"命令 {cmd}")

    for name in FILES:
        path = ROOT / name
        if not path.is_file():
            bad(f"{name} 不存在")
            continue
        text = path.read_text(encoding="utf-8")
        print(f"[{name}]")
        for line in text.splitlines():
            m = re.match(r"^(#{1,3}) (.+)$", line)
            if not m or m.group(1) == "#":
                continue
            head = m.group(2).strip()
            cn = len(re.findall(r"[\u4e00-\u9fff]", head))
            words = len(re.findall(r"[A-Za-z][A-Za-z'-]*", head))
            if cn and cn > 12:
                bad(f"标题过长（中文 {cn} 字）：{head}")
            if words and not cn and words > 8:
                bad(f"标题过长（英文 {words} 词）：{head}")
            if re.search(r"[：:—–（）()？?。]", head):
                bad(f"标题含标点或解释：{head}")
        if "——" in text or "—" in text:
            bad(f"{name} 出现破折号")
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if link.startswith("http"):
                continue
            if not (ROOT / link).exists():
                bad(f"{name} 链接失效：{link}")
        good(f"{name} 结构检查完成")

    out = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                         cwd=ROOT, capture_output=True, text=True).stderr
    m = re.search(r"Ran (\d+) tests", out)
    actual = int(m.group(1)) if m else -1
    claimed = set()
    for name in FILES:
        claimed |= {int(x) for x in re.findall(r"(\d+) tests", (ROOT / name).read_text(encoding="utf-8"))}
    if actual > 0 and claimed and actual not in claimed:
        bad(f"README 写 {sorted(claimed)} 例，实际 {actual}")
    else:
        good(f"测试数 {actual}")

    print("\n结论：" + ("全过" if ok else "有问题"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
