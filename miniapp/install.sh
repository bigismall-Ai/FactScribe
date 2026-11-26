#!/bin/sh
# FactScribe MiniApp 安装：把插件源整体同步到 MiniMax Code 的插件目录。
#
# 用法：./install.sh [--check]
#   缺省目标 ~/.minimax/plugins/factscribe/（宿主缺省 dataDir＝~/.minimax）。
#   幂等：跑多少遍结果一致（先清空目标目录再整棵复制，目标目录完全归本脚本管）。
#   --check：只检查目标目录里的 plugin.json 与载荷是否齐，不写任何东西。
#
# 装完重启 MiniMax Code 桌面端即可识别；对助手说「打开 FactScribe 工作台」。
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ID="factscribe"
MINIMAX_DIR="${MINIMAX_DATA_DIR:-$HOME/.minimax}"
DEST="$MINIMAX_DIR/plugins/$PLUGIN_ID"

# 目标路径守卫：必须是 ~/.minimax/plugins/factscribe 这个形状，防手滑删错目录
case "$DEST" in
  "$HOME/.minimax/plugins/factscribe") ;;
  *) echo "拒绝：目标目录不像预期的安装落点：$DEST" >&2; exit 2 ;;
esac

if [ "${1:-}" = "--check" ]; then
  if [ -f "$DEST/.minimax-plugin/plugin.json" ] \
     && [ -f "$DEST/miniapp/miniapp.json" ] \
     && [ -f "$DEST/miniapp/node/server.mjs" ] \
     && [ -d "$DEST/miniapp/node/engine/factscribe" ]; then
    echo "已安装：$DEST"
    exit 0
  fi
  echo "未安装（或装得不全）：$DEST"
  exit 1
fi

# 身份与载荷必须先备齐：没 build 过就先提示
if [ ! -f "$HERE/.minimax-plugin/plugin.json" ] || [ ! -f "$HERE/miniapp/miniapp.json" ] \
   || [ ! -f "$HERE/miniapp/node/server.mjs" ] || [ ! -d "$HERE/miniapp/node/engine/factscribe" ]; then
  echo "插件源不齐（缺身份清单或引擎没 vendor）：先跑 ./build.sh 再安装。" >&2
  exit 1
fi

echo "安装 $PLUGIN_ID → $DEST"
rm -rf "$DEST"
mkdir -p "$DEST"
# 整棵复制（含隐藏的 .minimax-plugin/）；cp dir/. 会连点文件一起带走
cp -R "$HERE/." "$DEST/"
# 清掉复制过程带进来的缓存物（契约要求载荷干净）
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -name '.DS_Store' -delete 2>/dev/null || true

echo "装好了：$DEST"
echo "下一步：重启 MiniMax Code 桌面端 → 对助手说「打开 FactScribe 工作台」。"
