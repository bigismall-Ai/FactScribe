#!/bin/sh
# FactScribe MiniApp build：引擎 vendoring ＋ 前端同步 ＋ 插件包契约自检。
#
# 用法：在本目录跑 ./build.sh（从仓根 factscribe/ 复制引擎与前端进来）。
# 产物都落在 miniapp/ 插件源内（安装时整体同步到 ~/.minimax/plugins/factscribe/）。
#
# 契约自检（官方 docs/package-contract.md 口径，超限即报错退出）：
#   - ≤1024 个文件；单文件 ≤16 MiB；总共 ≤64 MiB；
#   - 路径纯 ASCII；无软链；路径段匹配 [A-Za-z0-9._-]+。
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
PAYLOAD="$HERE/miniapp"
ENGINE="$PAYLOAD/node/engine"
CLIENT="$PAYLOAD/client"

echo "[1/4] vendor Python 引擎：factscribe/ → miniapp/node/engine/factscribe/"
rm -rf "$ENGINE/factscribe"
mkdir -p "$ENGINE"
cp -R "$REPO_ROOT/factscribe" "$ENGINE/factscribe"
# 排除构建中间物与缓存（契约要求载荷干净）
find "$ENGINE/factscribe" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$ENGINE/factscribe" -name '*.pyc' -delete 2>/dev/null || true
find "$ENGINE/factscribe" -name '.DS_Store' -delete 2>/dev/null || true
# 独立 'factscribe serve' 的网页 UI 不进 MiniApp 载荷：
#   1) MiniApp 走的是 'factscribe workbench'，它的前端由 Node 薄壳伺服（miniapp/client/），
#      引擎自带的 web/ 静态页在这个形态下永远不会被打开；
#   2) web/app.js 里调了 host.navigation.getState() 与 agent.session()——那是 MiniFactScribe
#      独立网页形态要用的宿主 API，本 MiniApp 一个都没声明（社区 checker 判 ACCESS_UNDECLARED）。
#   去掉的是网页形态的 UI 资产，不是引擎能力：'factscribe workbench'/'factscribe audit' 都不碰它。
rm -rf "$ENGINE/factscribe/web"

# 文风闸的规则文件也要跟着走：规则的查找顺序是「项目根 → 发行包根 → 包内」，
# 发行包根 = <engine>/。少了它，miniapp 的文风读数会退回内置默认值，
# 与仓里 CLI 的读数不一致（style-rules.toml 覆盖了几十个键）。
if [ -f "$REPO_ROOT/style-rules.toml" ]; then
  cp "$REPO_ROOT/style-rules.toml" "$ENGINE/style-rules.toml"
fi

echo "[2/4] 同步前端：workbench/static/ 三件 → miniapp/client/（零改动拷贝）"
mkdir -p "$CLIENT"
for f in index.html app.js app.css; do
  cp "$REPO_ROOT/factscribe/workbench/static/$f" "$CLIENT/$f"
done

echo "[3/4] 契约自检（miniapp/ 全目录）"
python3 - "$HERE" <<'PYCHECK'
import os, re, sys

root = os.path.abspath(sys.argv[1])
MAX_FILES = 1024
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
SEG_RE = re.compile(r'^[A-Za-z0-9._-]+$')

count = 0
total = 0
problems = []
for dirpath, dirnames, filenames in os.walk(root):
    for name in dirnames + filenames:
        p = os.path.join(dirpath, name)
        rel = os.path.relpath(p, root)
        if not all(ord(c) < 128 for c in rel):
            problems.append(f"路径含非 ASCII：{rel}")
        for seg in rel.split(os.sep):
            if not SEG_RE.match(seg):
                problems.append(f"路径段不合规（只许字母数字点下划线连字符）：{rel}")
        if os.path.islink(p):
            problems.append(f"含软链：{rel}")
    for name in filenames:
        p = os.path.join(dirpath, name)
        if os.path.islink(p):
            continue
        size = os.path.getsize(p)
        count += 1
        total += size
        if size > MAX_FILE:
            problems.append(f"单文件超 16MiB：{os.path.relpath(p, root)}（{size} 字节）")

if count > MAX_FILES:
    problems.append(f"文件数超上限：{count} > {MAX_FILES}")
if total > MAX_TOTAL:
    problems.append(f"总体积超上限：{total} 字节 > {MAX_TOTAL}")

print(f"  文件数：{count}（上限 {MAX_FILES}）")
print(f"  总体积：{total / 1048576:.1f} MiB（上限 64 MiB）")
if problems:
    print("契约自检失败：")
    for p in problems:
        print("  - " + p)
    sys.exit(1)
print("  契约自检通过。")
PYCHECK

echo "[4/4] 引擎自检：vendored 包可被 import（-B：不往载荷里写 __pycache__）"
PYTHONPATH="$ENGINE" python3 -B -c "import factscribe, factscribe.workbench.server; print('  engine import ok')" 2>/dev/null \
  || { echo "vendored 引擎 import 失败"; exit 1; }

echo "build 完成：$(find "$PAYLOAD" -type f | wc -l | tr -d ' ') 个载荷文件。"
