#!/bin/sh
# 一套界面：源在 factscribe/web/，MiniApp 插件里的 client 是同一份拷贝。
# 改完源文件跑这一句；tests/sync.test.mjs 会拦下忘记同步的提交。
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
src="$root/factscribe/web"
dst="$root/integrations/minifactscribe/miniapp/client"
for f in index.html app.js app.css; do
  cp "$src/$f" "$dst/$f"
done
rm -f "$dst/styles.css"
echo "synced $src -> $dst"
