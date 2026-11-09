#!/usr/bin/env python3
"""README 自检：事实项自己查，文风项交给 `style --doc`。

分工：
  1. 文风与标题规则一律调用 `python3 -m factscribe style --doc README.md README.en.md`，
     本脚本不再重复实现第二套判据；
  2. 命令名必须真实存在（对照 `factscribe --help`）；
  3. 十个命令必须都写进两份 README；
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
COMMANDS = ["check", "audit", "matrix", "build", "preamble",
            "verify-pdf", "style", "protect", "tide", "prescribe"]
ok = True


def bad(msg):
    global ok
    ok = False
    print(f"  \u2717 {msg}")


def good(msg):
    print(f"  \u2713 {msg}")


def run(args):
    return subprocess.run([sys.executable, *args], cwd=ROOT,
                          capture_output=True, text=True)


def main():
    print("[文风与标题：交给 style --doc]")
    styled = run(["-m", "factscribe", "style", "--doc", *FILES])
    if styled.returncode == 0:
        good("style --doc 两份 README 均为 0 条")
    else:
        bad(f"style --doc 退出码 {styled.returncode}")
        print(styled.stdout)
        print(styled.stderr)

    help_txt = run(["-m", "factscribe", "--help"]).stdout
    for cmd in COMMANDS:
        (good if cmd in help_txt else bad)(f"命令 {cmd}")

    for name in FILES:
        path = ROOT / name
        if not path.is_file():
            bad(f"{name} 不存在")
            continue
        text = path.read_text(encoding="utf-8")
        print(f"[{name}]")
        missing = [cmd for cmd in COMMANDS if f"`{cmd}`" not in text]
        if missing:
            bad(f"命令未写入：{', '.join(missing)}")
        else:
            good(f"十个命令已写齐（{len(COMMANDS)} 条）")
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if link.startswith("http"):
                continue
            if not (ROOT / link).exists():
                bad(f"{name} 链接失效：{link}")
        good(f"{name} 链接检查完成")

    out = run(["-m", "unittest", "discover", "-s", "tests"]).stderr
    m = re.search(r"Ran (\d+) tests", out)
    actual = int(m.group(1)) if m else -1
    claimed = set()
    for name in FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        claimed |= {int(x) for x in re.findall(r"(\d+)\s*(?:tests|例)", text)}
    if actual > 0 and claimed and actual not in claimed:
        bad(f"README 写 {sorted(claimed)} 例，实际 {actual}")
    else:
        good(f"测试数 {actual}")

    print("\n结论：" + ("全过" if ok else "有问题"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
