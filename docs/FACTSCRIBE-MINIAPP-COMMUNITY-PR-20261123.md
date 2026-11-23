# FactScribe 论文工作台 —— MiniMax-Code-MiniApps 社区仓库 PR 准备（2026-11-23）

> 这份文档是**交付给用户照着执行**的开 PR 手册 + PR 描述草稿。
> **没有开 PR、没有 push 到任何仓库、没有在克隆副本上提交任何东西。**
> 路径改自「官方插件市场飞书表单」为「官方社区仓库 PR」。

## 0. 一句话结论

包已按社区形态准备完毕（目录 `plugins/bigismall-ai/factscribe/`），社区 checker **0 error / 0 warning**，
随包 MCP 声明按证据判定为**保留官方 fail-closed 占位**（不是远程 MCP 声明），
源→载荷→本机已发布态三方逐文件 **0 差异**。剩下唯一需要人做的是：**fork → 复制 → commit → push → 开 PR**。

## 1. 社区形态下的最终目录树

```text
plugins/bigismall-ai/factscribe/
├── .minimax-plugin/
│   └── plugin.json          # 身份/图标/分类/示例查询/MCP 声明
├── docs/
│   └── workbench.png        # PR 用截图（样例论文盘，无用户稿件内容）
├── miniapp/
│   ├── miniapp.json         # 载荷根、Node 入口、页面路由、MCP 端点
│   ├── client/              # 页面三件：index.html / app.js / app.css
│   └── node/
│       ├── server.mjs       # Node 入口：export async function start(context)
│       └── engine/          # vendor 的 FactScribe 引擎（Python）
├── icon.png
├── package.json             # 只有 mcode 段
├── README.md                # 英文（社区主文档）
├── README.zh-CN.md          # 中文
├── LICENSE                  # MIT
└── servers.mcp.json         # 由本 MiniApp 自托管的 MCP server 声明
```

读数：**109 个文件／5.0 MiB**（上限 1024 文件／64 MiB）。

### 与我们仓内 `miniapp/` 的差别（两处，都是刻意的）

| 差别 | 原因 |
|---|---|
| 社区副本**不含** `build.sh`、`install.sh` | 这两个是 FactScribe 仓内开发脚本：`build.sh` 依赖仓源才能跑，`install.sh` 假设自己在一个源目录里；社区用户拿到的是成品包，不该看到它们 |
| 社区副本**不含** `factscribe/web/`（引擎自带网页 UI） | 见第 4 节（MCP/载荷判定）；另外它本来就是独立 `factscribe serve` 形态的 UI，不在 MiniApp 运行路径上 |

## 2. npm run check：0 error

社区 checker 源码（`scripts/`）逐条对照我们的包，**0 error、0 warning**：

```text
$ node scripts/validate.mjs plugins/bigismall-ai/factscribe
plugins/bigismall-ai/factscribe: OK
$ echo $?
0
```

**剩余 warning 清单：无。**（下面第 5 节列了逐条规则的核对结果，含为什么没有 warning。）

### 本机复现命令（包级）

```sh
cd <社区仓库克隆>
node scripts/validate.mjs plugins/bigismall-ai/factscribe
# 整仓：
npm run check      # = npm run validate && npm test
```

> `npm run check` 的 `npm test` 是 checker 自身的单测（`node --test "test/**/*.test.mjs"`），
> 与我们的包无关；整仓跑需要完整克隆（见第 8 节）。

## 3. 随包 MCP 声明：判定结论与依据

### 结论

**保留现状**：`plugin.json.mcpServers: ["servers.mcp.json"]` ＋ `servers.mcp.json` 里的
`url: "http://127.0.0.1:9/mcp/factscribe"` ＋ `miniapp.json` 里的
`mcpEndpoints: [{ "server": "factscribe", "path": "/mcp/factscribe" }]`。
**不能**把 `plugin.json.mcpServers` 置空、也**不能**删掉 `servers.mcp.json`。

### 依据（三条，都可复核）

1. **官方文档原文**（社区仓 `docs/package-contract.md`）：
   > `mcpEndpoints` is an array of `{ "server": string, "path": string }`. `server` matches
   > `^[a-zA-Z0-9_-]{1,128}$` and **must name a server declared through `plugin.json.mcpServers`**;
   > MiniMax Code checks that reference at install time.

   → 两处声明必须成对。清空 `mcpServers` 会让宿主直接拒绝整份 manifest。

2. **宿主实现代码**（本机 `/Applications/MiniMax Inside Code.app` 的 app.asar，插件清单读取器）：

   ```js
   function readMcpEndpoints(value, mcpServerNames) {
     ...
     if (!knownServers.has(item.server)) {
       miniAppFail('MCP_ENDPOINTS_INVALID',
         `MCP server ${item.server} is not declared by the Plugin`);
     }
   ```

   → 同上，宿主在安装/发布时强校验。

3. **官方内置的 Mini App MCP 编写指南**（同一 app.asar 内，标题 `# Mini App MCP authoring`）明写：

   > ## Mini App-managed Streamable HTTP MCP
   > Declare the MCP file in `.minimax-plugin/plugin.json` as above. In `servers.mcp.json`,
   > declare a Streamable HTTP identity with **the valid fail-closed placeholder used only
   > before Host adoption**:
   > ```json
   > { "schemaVersion": 1, "mcpServers": { "board-summary": {
   >     "type": "streamable-http", "url": "http://127.0.0.1:9/mcp/board-summary",
   >     "headers": {}, "description": "...", "timeout": 30000 } } }
   > ```
   > The Node entry must implement Streamable HTTP MCP at that exact `context.listen` path
   > before `start(context)` resolves. **The Host rewrites only the named server to the current run.**

   → `http://127.0.0.1:9/...` 就是官方规定的「宿主接管前的 fail-closed 占位」，
   端口 9 永远没人应答；宿主采纳 MiniApp 时把它改写成当前运行实例的地址。

4. **本机实测**（仓库 `miniapp/README.md` 的宿主侧验收段，2026-11-22）：
   下一回合工具表出现 `mcp__factscribe__*`，逐个实调通过（`fs_status` 读出 4 个项目、
   `fs_query_facts` 读出账本三条、`fs_get_report` 读出真报告……）→ 宿主确实接管改写了地址。

### 顺带解决的载荷问题

社区 checker 会扫载荷里 `.js/.mjs/.cjs/.html/.htm` 的宿主 API 调用
（`scripts/lib/rules/usage.mjs`）。我们载荷里 **唯一** 的两处违规来自
`miniapp/node/engine/factscribe/web/app.js`（独立 `factscribe serve` 网页形态的旧 UI）：

| 违规 | checker 判据 | 我们的处理 |
|---|---|---|
| `agent.session()` | 要 `agentAccess: ["session.read"]`（error） | 不声明 session.read——本 MiniApp 一个用户对话都不读，声明它是权限虚增 |
| `host.navigation.getState()` | 要 `hostAccess: ["navigation.read"]`（error） | 同上，不声明宿主导航读取 |

处理方式：**把 `factscribe/web/` 从 vendor 载荷里去掉**（改 `miniapp/build.sh`，
见 `rm -rf "$ENGINE/factscribe/web"`）。理由：MiniApp 走的是 `factscribe workbench`，
它的网页由 Node 薄壳伺服（`miniapp/client/`），引擎自带的 `web/` 静态页在这个形态下永远打不开；
去掉的是网页形态的 UI 资产，不是引擎能力（`factscribe workbench` / `factscribe audit` 都不碰它）。
**没有**动 FactScribe 的任何已定口径，也**没有**为了过 checker 放宽任何闸门。

## 4. 载荷与同步一致性

| 比对 | 读数 |
|---|---|
| 源（仓内 `factscribe/` 去掉 web/）vs 载荷 | 95 vs 95 文件，**0 差异** |
| 前端三件：源 vs 载荷 vs 本机已发布 | `index.html`/`app.js`/`app.css` 三方**逐字节一致** |
| 载荷 vs 本机已发布（`~/.minimax/plugins/factscribe/miniapp/`） | 101 vs 101 文件，**0 差异** |
| 本机已发布 manifest | version **1.1.0**、author `Bigismall AI`、17 工具、engines 已移除 |

同步链：`miniapp/build.sh`（vendor 引擎＋同步前端三件＋契约自检）→
`miniapp publish --pluginId factscribe --sourcePath <miniapp>`（宿主发布态）。

## 5. 逐条规则核对（为什么 0 warning）

| checker 规则 | 我们的读数 |
|---|---|
| `LAYOUT_FILE_MISSING` | `.minimax-plugin/plugin.json`、`package.json`、`miniapp/miniapp.json`、`README.md`、`LICENSE` 齐 |
| `LAYOUT_AUTHOR_NOT_LOWERCASE` | 目录 `bigismall-ai` 全小写 |
| `LAYOUT_NAME_MISMATCH` | 目录名 = `plugin.json.name` = `factscribe` |
| `LAYOUT_IMAGE_INVALID` | `icon.png` 461 字节，PNG magic `89504e470d0a1a0a`，128×128 |
| `MANIFEST_*` | 字段全在白名单内；`name` 匹配 `^[a-z][a-z0-9]*...$`；version SemVer；category `Office`；exampleQueries 3 条非空 |
| `MCODE_INVALID` | `package.json#mcode` 恰好 `{schemaVersion:2, miniApp:"./miniapp/miniapp.json"}` |
| `MINIAPP_*` | 载荷根存在、entry 在 node 根内、`surface.path=/workbench` 不在 `/__mavis/` 下、`mcpEndpoints` 合法 |
| `PATH_NOT_PORTABLE` | 全 ASCII，路径段匹配 `[A-Za-z0-9._-]+`，无 `..`、无反斜杠、无 Windows 保留名 |
| `PACKAGE_SPECIAL_FILE` | 无软链、无硬链、无特殊文件、无 `node_modules` |
| `PACKAGE_TOO_MANY_FILES` / `PACKAGE_TOO_LARGE` / `PACKAGE_FILE_TOO_LARGE` | 109 文件 ≤1024；5.0 MiB ≤64 MiB；最大单文件 1.8 MiB ≤16 MiB |
| `ENTRY_START_EXPORT_MISSING` | `miniapp/node/server.mjs` 有 `export async function start(context)` |
| `ENTRY_STDOUT` | 入口无 `console.log`/`process.stdout.write`（走 `context.logger`） |
| `NODE_UNGUARDED_SERVER` | 只用 `node:http`，无 https/http2/net/tls |
| `NODE_RESERVED_ROUTE` | 无 `/__mavis/` 路由 |
| `ACCESS_UNDECLARED` | 见第 3 节：载荷里没有未声明的 tool/device/host/session 调用 |
| `README_HEADING_MISSING` | `## Tested environment`、`## Data & access` 两节都在 |
| `README_MIN_VERSION_MISSING` | 本包最低客户端 3.1.2（`agentAccess`），README 写明 MiniMax Code 3.1.16 |

## 6. README 两节的实际内容

### `## Tested environment`（英文 README.md）

- MiniMax Code 3.1.16 on macOS 26.6.2 (arm64)：从本目录安装、经助手打开、页面渲染正常，
  17 个 MCP 工具在宿主 MCP 运行时上逐个实调通过。
- Node 26.7 + Python 3.14；引擎随包 vendor，不用装任何东西。
- 最低客户端 3.1.2（本包声明 `agentAccess: ["session.run"]`）；**未声明 `engines` 下限**，
  所以 3.1.2 起的客户端都装得上，只是客户端不提供模型目录时面板少一个模型下拉。
- **未验证**：Windows / Linux 宿主（包内无平台专属二进制、Node 入口只用内置模块，但没实跑过）。

> `engines` 是本轮特意**不写**的：契约写明「Clients before 3.1.6 do not know the field and
> reject the whole package」——声明它等于把真实下限从 3.1.2 悄悄抬到 3.1.6。我们不需要更新的客户端。

### `## Data & access`（英文 README.md）

按社区要求逐项写全：读取的文件（论文根目录＋载荷目录）、写入的文件（插件私有 `dataDir` 的
`config.json`/`proposals/`/`custom-models.json`，以及你点了才写的 `sections/*.tex`、
`facts/draft/`）、网络 host（默认无；自加自定义模型时只打你填的端点）、
拉起的进程（引擎 workbench 子进程 / `factscribe audit` / 可选 `tectonic` / macOS `open`）、
Agent 回合（只声明 `session.run`）、**读取的对话：无**、**调用的工具：无**、
**麦克风/摄像头/通知：不用**、**宿主导航读取：不用**、状态存放位置（宿主私有 dataDir）。

## 7. 两个根 README 的表格行（已加在第 96 行）

```markdown
| [FactScribe Paper Workbench](plugins/bigismall-ai/factscribe/) | A local workbench for writing papers: open your manuscript projects, read the check report, the fact ledger and the knowledge base, and let the assistant propose edits you approve before anything reaches the file; 17 MCP tools, read-mostly by design, every write gated by your confirmation | [bigismall-ai](https://github.com/bigismall-ai) |
```

```markdown
| [FactScribe 论文工作台](plugins/bigismall-ai/factscribe/README.zh-CN.md) | 写论文的本地工作台：打开稿盘，看检查报告、事实账本与知识库；助手的改稿建议先成提议单，你点了才落盘；17 个 MCP 工具以只读为主，写盘一律由你确认 | [bigismall-ai](https://github.com/bigismall-ai) |
```

（仓库级校验 `REPO_README_LINK_MISSING` 要求两个根 README 都出现 `plugins/bigismall-ai/factscribe/`，
两行都满足。）

## 8. 怎么开 PR（用户本人执行；我们不代劳）

### 8.1 已完成的准备工作（可复核）

1. 取社区仓库（Git 协议在本机被拦，走 tarball 兜底）：

   ```sh
   curl -sSL -o /tmp/mm-miniapps.tar.gz \
     https://codeload.github.com/MiniMax-AI/MiniMax-Code-MiniApps/tar.gz/refs/heads/main
   mkdir -p /tmp/mm-miniapps && tar xzf /tmp/mm-miniapps.tar.gz -C /tmp/mm-miniapps --strip-components=1
   ```

2. 把我们的包放进社区形态（**源在自家仓**，别在别人的克隆上改）：

   ```sh
   REPO=/Users/moc/workspaces/SiAgent/factscribe-dev/.worktrees/miniapp-host
   DEST=/tmp/mm-miniapps/plugins/bigismall-ai/factscribe
   mkdir -p "$DEST"
   rsync -a --exclude 'build.sh' --exclude 'install.sh' \
         --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
         "$REPO/miniapp/" "$DEST/"
   ```

3. 两个根 README 各加一行（第 8.3 节），checker 跑通。

> 克隆副本 **/tmp/mm-miniapps** 现在已经装好了包、也改了两个根 README，
> 但**没有 git 初始化、没有 add、没有 commit、没有 push**——按约定不在别人的仓库上提交。

### 8.2 开 PR 的步骤（需要你自己的 GitHub 账号）

```sh
# ① fork（在浏览器里把 MiniMax-AI/MiniMax-Code-MiniApps fork 到 bigismall-ai）
# ② 克隆你自己的 fork
git clone https://github.com/bigismall-ai/MiniMax-Code-MiniApps.git
cd MiniMax-Code-MiniApps

# ③ 把已经准备好的文件搬进来
mkdir -p plugins/bigismall-ai
cp -R /tmp/mm-miniapps/plugins/bigismall-ai/factscribe plugins/bigismall-ai/
cp /tmp/mm-miniapps/README.md /tmp/mm-miniapps/README.zh-CN.md .

# ④ 跑 checker（必须 0 error）
npm run check

# ⑤ 提交并推到你自己的分支
git checkout -b add/factscribe-miniapp
git add plugins/bigismall-ai/factscribe README.md README.zh-CN.md
git commit -m "feat(miniapp): add FactScribe paper workbench"
git push -u origin add/factscribe-miniapp

# ⑥ 开 PR（浏览器里对着上游仓库开）
#    https://github.com/MiniMax-AI/MiniMax-Code-MiniApps/compare/main...bigismall-ai:add/factscribe-miniapp
```

PR 描述直接用第 9 节的草稿（**开头 1–3 句请你自己改一遍**——AGENTS.md 明确要求
「Ask the person you work for to read and edit the opener before you submit」）。

## 9. PR 描述草稿（可直接粘贴）

```markdown
Adds **FactScribe Paper Workbench** (`factscribe`): a local Mini App for writing papers in
MiniMax Code. It opens your manuscript projects, shows the check report, the fact ledger and the
knowledge base, and exposes 17 MCP tools that are read-mostly by design — every edit the assistant
suggests arrives as a proposal you approve in the page before anything is written to your manuscript.

![FactScribe paper workbench](plugins/bigismall-ai/factscribe/docs/workbench.png)

The screenshot shows the vendored sample paper (no user documents).

## Tested environment

- MiniMax Code 3.1.16 on macOS 26.6.2 (arm64): installed from this directory, opened through the
  Agent, page rendered, and all 17 MCP tools called end to end over the Host's MCP runtime.
- Node 26.7 and Python 3.14 on the same machine; the Python engine is vendored, nothing to install.
- Minimum client version: 3.1.2 (the package declares `agentAccess: ["session.run"]`).
  No `engines` bound is declared on purpose: clients older than 3.1.6 reject a package that
  carries the field, so declaring it would silently raise the real floor.

## Not verified

- Windows and Linux hosts. The package ships no platform-specific binary and the Node entry uses
  only Node built-ins, but no run on those platforms has been done.
- The web UI of the standalone `factscribe serve` mode is not part of this package: the vendored
  engine keeps every command the Mini App uses (`factscribe workbench`, `factscribe audit`) but
  not that page, which called Host APIs this package does not declare.

## `npm run check`

No errors and no warnings for this package:

```
plugins/bigismall-ai/factscribe: OK
```

## Access and permissions

No new access is requested: `agentAccess: ["session.run"]` only. The package does not declare
`toolAccess`, `deviceAccess`, `hostAccess` or `session.read`, so it cannot call Host tools,
cannot use the microphone, camera or notifications, cannot read Host navigation, and cannot read
the user's conversations. The Mini App serves its own MCP server; see the README section
"MCP tools and the placeholder address" for why `servers.mcp.json` points at the documented
fail-closed placeholder.

<details><summary>Written by MiniMax-M3.1-Flash</summary>

Package layout: `.minimax-plugin/plugin.json`, `package.json` (mcode only), `miniapp/miniapp.json`,
`miniapp/client/` (page), `miniapp/node/server.mjs` (Node entry) and `miniapp/node/engine/`
(vendored Python engine), plus `servers.mcp.json`, `icon.png`, `README.md`,
`README.zh-CN.md` and `LICENSE` (MIT).

The MCP server is declared in `plugin.json.mcpServers` and referenced from
`miniapp/miniapp.json` with `mcpEndpoints`, because the Host checks that every
`mcpEndpoints.server` is declared in `plugin.json.mcpServers`. The URL in `servers.mcp.json`
is the fail-closed placeholder MiniMax Code documents for a Mini App that serves its own MCP
server; the Host rewrites it to the running instance when it adopts the package.

</details>
```

## 10. 本轮改了哪些文件（我们自己的仓，分支 `feat/miniapp-host-seam`）

| 文件 | 改动 |
|---|---|
| `miniapp/.minimax-plugin/plugin.json` | version 1.0.0→1.1.0；description 改写为「解决什么问题」；author `Bigismall AI`；exampleQueries 改英文三条 |
| `miniapp/package.json` | 只留 `mcode` 段 |
| `miniapp/miniapp/miniapp.json` | **移除** `engines`（写了反而把真实下限从 3.1.2 抬到 3.1.6） |
| `miniapp/LICENSE` | 新增：MIT，holder `Bigismall AI` |
| `miniapp/README.md` | 重写为英文社区文档（含 `## Tested environment`、`## Data & access`） |
| `miniapp/README.zh-CN.md` | 新增：中文版同结构 |
| `miniapp/build.sh` | vendor 时去掉 `factscribe/web/`（见第 3 节） |
| `miniapp/docs/workbench.png` | 新增：样例论文盘截图 |
| `scripts/make_miniapp_submit_zip.py` | 新增：单包快照打包＋发布前限制自检（市场表单路已作废，脚本留着以后发版用） |
| `docs/FACTSCRIBE-MINIAPP-COMMUNITY-PR-20261123.md` | 本文件 |

## 11. 验证读数

| 项 | 读数 |
|---|---|
| 全仓 pytest | `2353 passed, 397 subtests passed`（0 failed） |
| 社区 checker（包级） | `plugins/bigismall-ai/factscribe: OK`，exit 0，0 error / 0 warning |
| 源→载荷→已发布 | 逐文件 0 差异（载荷 101 文件；前端三件逐字节一致） |
| 包体积 | 109 文件 / 5.0 MiB（上限 1024 / 64 MiB） |
| 用户正式稿盘 | `paper`/`paper-zh`/`paper-b`/`paper-b-zh` **未触碰**（本轮只写插件目录与 `/tmp` 副本） |
