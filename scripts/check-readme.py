#!/usr/bin/env python3
"""README 自检：事实项自己查，文风项交给 `style --doc`。

分工：
  1. 文风与标题规则一律调用 `python3 -m factscribe style --doc README.md README.en.md`，
     本脚本不再重复实现第二套判据；
  2. 命令名必须真实存在（对照 `factscribe --help`）；
  3. 子命令清单从 `factscribe --help` 现取，两份 README 必须一条不落；
  3b. 反向对表：README 命令表里写了、而 `--help` 里没有的命令，红（防再犯绊线）；
  3c. 联网边界声明行必须存在（`refs search` 是唯一默认联网的命令）；
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

# 命令表第一格：整格就是一个反引号包住的命令名（可带子动作，如 `fact import`）。
# 只认「整格就是命令名」，免得把正文里的路径、句子误当成命令行。
CMD_CELL_RE = re.compile(r"^\s*`([a-z][a-z0-9\-]*(?:\s+[a-z][a-z0-9\-]*)?)`\s*$")


def bad(msg):
    global ok
    ok = False
    print(f"  ✗ {msg}")


def good(msg):
    print(f"  ✓ {msg}")


def run(args):
    return subprocess.run([sys.executable, *args], cwd=ROOT,
                          capture_output=True, text=True)


def documented_commands(text):
    """README 命令表里写了哪些命令（取表头格里的反引号命令名，取第一个词做主命令）。

    表格行形如 `| `cmd` | 说明 |`；表头行、分隔行、说明格里的路径都不算。
    """
    heads = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) < 3:
            continue
        m = CMD_CELL_RE.match(cells[1])
        if not m:
            continue
        head = m.group(1).split()[0]
        if head not in heads:
            heads.append(head)
    return heads


def has_net_declaration(text):
    """有没有一行把联网边界说全了。

    四件事同时点到才算：`refs search`、唯一、联网、以及「不发正文」这半句。
    少了最后那半句，代码块里的行内注释（如 `# 唯一默认联网：只发查询词`）
    也能蒙混过关，所以不许省。
    中英文各认一套关键词。
    """
    for line in text.splitlines():
        if "refs search" not in line:
            continue
        if not re.search(r"唯一|only", line, re.I):
            continue
        if not re.search(r"联网|network", line, re.I):
            continue
        if not re.search(r"不发正文|never prose", line, re.I):
            continue
        return True
    return False


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
    m = re.search(r"\{([a-z0-9,\-]+)\}", help_txt)
    COMMANDS = m.group(1).split(",") if m else []
    if not COMMANDS:
        bad("无法从 --help 解析子命令列表")
    else:
        good(f"--help 里有 {len(COMMANDS)} 个子命令")

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
            good(f"命令已写齐（{len(COMMANDS)} 条）")

        # 反向对表：命令表里多写的命令名也要红。
        heads = documented_commands(text)
        extra = [cmd for cmd in heads if cmd not in COMMANDS]
        if extra:
            bad(f"命令表多写了 --help 里没有的命令：{', '.join(extra)}")
        else:
            good(f"命令表无多余命令（{len(heads)} 条）")

        # 联网边界声明行必须存在。
        if has_net_declaration(text):
            good("「唯一联网命令」声明行在位")
        else:
            bad("缺「唯一联网命令」声明行（须有一行同时点到 `refs search`、唯一、联网）")

        for link in re.findall(r"\]\(([^)]+)\)", text):
            if link.startswith("http"):
                continue
            if link.startswith("#"):
                # 页内锚点（目录里的「#章节名」）：目标是本文档里的标题，
                # 没有对应的目标文件可查——按文件存在性查它是查不成的。
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
