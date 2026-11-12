#!/bin/sh
# 方法论 → 命令的薄封装：只调用 factscribe，不改判定、不改退出码。
#
#   ./gate.sh brief  <项目>            # 阶段 1：写作简报（stdout）
#   ./gate.sh check  <项目>            # 阶段 3：audit --build
#   ./gate.sh plan   <项目>            # 阶段 4：polish --plan
#   ./gate.sh accept <旧> <新>         # 阶段 4：review --before 旧 --after 新
#
# 退出码原样透传：0 绿 / 1 红 / 2 配置错 / 3 黄。
# 依赖：python3；不依赖网络。

set -eu

usage() {
    cat <<'EOF'
用法：
  gate.sh brief  <项目目录>
  gate.sh check  <项目目录>
  gate.sh plan   <项目目录>
  gate.sh accept <旧目录> <新目录>
EOF
    exit 2
}

[ $# -ge 2 ] || usage
cmd=$1
shift

# 允许从仓库根之外调用
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../.." && pwd)

run() {
    PYTHONPATH="$root" python3 -m factscribe "$@"
}

case "$cmd" in
    brief)
        [ $# -eq 1 ] || usage
        run brief "$1"
        ;;
    check)
        [ $# -eq 1 ] || usage
        run audit "$1" --build
        ;;
    plan)
        [ $# -eq 1 ] || usage
        run polish --plan "$1"
        ;;
    accept)
        [ $# -eq 2 ] || usage
        run review --before "$1" --after "$2"
        ;;
    *)
        usage
        ;;
esac
