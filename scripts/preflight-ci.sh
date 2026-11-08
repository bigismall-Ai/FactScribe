#!/usr/bin/env bash
# preflight-ci.sh — 在推送前把 CI 会做的事在本机等价跑一遍。
#
# 为什么需要：三次 "本地绿、CI 红" 都来自**环境差异**，不是代码问题：
#   1) CI 是干净克隆（只含已提交文件）——本地工作区里未提交的实验报告让夹具“看起来”完整；
#   2) ubuntu runner 默认没有 poppler（pdftotext/pdfinfo）——macOS 上有；
#   3) runner 有外网——联网路径的行为与本地相反。
#
# 用法：
#   ./scripts/preflight-ci.sh            # 默认：干净克隆 + 3.10/3.11/3.12 + 外部依赖自检 + 验收步
#   ./scripts/preflight-ci.sh --fast     # 跳过克隆，直接在工作区跑
#   ./scripts/preflight-ci.sh --linux    # 额外在 siinfer 的 ubuntu 容器里跑（真 Linux）
#
# 退出码：0 = 全绿；1 = 有失败（会打印对应 CI 步骤名）。
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
FAST=0
LINUX=0
for arg in "$@"; do
  case "$arg" in
    --fast) FAST=1 ;;
    --linux) LINUX=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg"; exit 2 ;;
  esac
done

fail=0
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()  { printf '   \033[32m✓\033[0m %s\n' "$*"; }
bad() { printf '   \033[31m✗\033[0m %s\n' "$*"; fail=1; }

# ---------------------------------------------------------------- 1. 外部依赖
say "步骤 1/4：外部依赖（CI 装了 poppler；本机没有则 PDF 测试会红）"
missing=0
for tool in pdftotext pdfinfo; do
  if command -v "$tool" >/dev/null 2>&1; then
    ok "${tool}：$(command -v "$tool")"
  else
    bad "${tool} 缺失 —— CI 会装 poppler-utils；本机请 brew install poppler"
    missing=1
  fi
done
[ "$missing" -eq 0 ] && ok "PDF 工具齐备"

# ---------------------------------------------------------------- 2. 干净克隆
WORK="$REPO"
if [ "$FAST" -eq 0 ]; then
  say "步骤 2/4：干净克隆（只含已提交文件——夹具缺源文件这里就会暴露）"
  TMP=$(mktemp -d "${TMPDIR:-/tmp}/factscribe-ci.XXXXXX")
  trap 'rm -rf "$TMP"' EXIT
  if git -C "$REPO" clone -q --no-local "$REPO" "$TMP/repo" 2>/dev/null; then
    WORK="$TMP/repo"
    ok "克隆到 ${WORK}（HEAD $(git -C "$WORK" rev-parse --short HEAD)）"
    dirty=$(git -C "$REPO" status --porcelain | wc -l | tr -d ' ')
    [ "$dirty" -gt 0 ] && echo "   注意：工作区有 ${dirty} 个未提交改动，这些改动不会进 CI"
  else
    bad "克隆失败"; exit 1
  fi
else
  say "步骤 2/4：干净克隆（--fast：跳过，直接用工作区）"
fi

# ---------------------------------------------------------------- 3. 测试矩阵
say "步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12）"
for py in 3.10 3.11 3.12; do
  if ! command -v uv >/dev/null 2>&1; then
    bad "uv 未安装，无法切 Python ${py}"
    break
  fi
  out=$(cd "$WORK" && uv run --python "$py" --no-project python -m unittest discover -s tests 2>&1)
  if [ $? -eq 0 ]; then
    n=$(printf '%s\n' "$out" | grep -oE 'Ran [0-9]+ tests' | head -1)
    ok "Python ${py}：${n}"
  else
    bad "Python ${py} 失败："
    printf '%s\n' "$out" | grep -E '^(FAIL|ERROR):|AssertionError|ModuleNotFoundError' | head -8 | sed 's/^/      /'
  fi
done

# ---------------------------------------------------------------- 4. 验收步
say "步骤 4/4：验收样例必须 exit 1（workflow 的硬断言）"
if (cd "$WORK" && python3 -m factscribe audit examples/minimal >/dev/null 2>&1); then
  code=0
else
  code=$?
fi
if [ "$code" -eq 1 ]; then
  ok "examples/minimal audit exit=1（红，符合预期）"
else
  bad "examples/minimal audit exit=${code}，期望 1（0=假绿，2=配置坏）"
fi

# ---------------------------------------------------------------- 5. 可选：真 Linux
if [ "$LINUX" -eq 1 ]; then
  say "附加：在 siinfer 的 ubuntu 容器里跑（真 Linux，含 poppler）"
  if ! command -v ssh >/dev/null 2>&1; then
    bad "本机没有可用的 ssh（沙箱环境），--linux 跳过"
  else
    BUNDLE=$(mktemp -t fs.XXXXXX.bundle)
    if git -C "$WORK" bundle create "$BUNDLE" --all >/dev/null 2>&1; then
      if scp -q "$BUNDLE" siinfer-si:/tmp/factscribe.bundle 2>/dev/null; then
        ssh siinfer-si 'sudo -u moc bash -lc "
          rm -rf /tmp/fs-linux && git clone -q /tmp/factscribe.bundle /tmp/fs-linux &&
          docker run --rm -v /tmp/fs-linux:/w -w /w python:3.12-slim bash -lc \"
            apt-get update -qq && apt-get install -y -qq poppler-utils git >/dev/null &&
            python -m unittest discover -s tests 2>&1 | tail -3\""' 2>&1 | sed 's/^/      /'
      else
        bad "scp 到 siinfer 失败（--linux 跳过）"
      fi
    else
      bad "git bundle 失败（--linux 跳过）"
    fi
    rm -f "$BUNDLE"
  fi
fi

say "结论"
if [ "$fail" -eq 0 ]; then
  echo "   本地等价 CI 全绿——可以推。"
else
  echo "   有失败项，先修再推（上面的 ✗ 就是 CI 会红的地方）。"
fi
exit "$fail"
