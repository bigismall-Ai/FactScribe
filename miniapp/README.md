# FactScribe 论文工作台（MiniMax Code MiniApp）

把 FactScribe 本地论文工作台装进 MiniMax Code 桌面端：页面里看稿、改稿、看检查报告，
AI 助手通过 6 个**只读** MCP 工具帮你查稿况、读正文、对事实账。

**人在回路（Human-in-the-loop）立场**：AI 只读、只建议；一切落笔都在页面里由你确认
（v1 甚至没有写稿类 MCP 工具，v2 也不给——写稿只会以「提议单 → 页面弹差异卡 → 你确认」的方式出现）。

## 功能

- **工作台页面**（路由 `/workbench`）：项目与稿盘清单、章节芯片渲染（`\fact{}`、`\cite{}`、
  绑定数字显示为不可误碰的芯片）、正文写回（指纹闸保护）、检查报告、事实账本、知识库、AI 对话面板。
- **AI 助手工具面**（`/mcp/factscribe`，全部只读）：
  | 工具 | 干什么 |
  |---|---|
  | `fs_status` | 项目与稿盘清单＋当前论文根目录 |
  | `fs_get_outline` | 某稿盘的目录树（标题级） |
  | `fs_read_section` | 某段（或某文件全部块）的 LaTeX 原文 |
  | `fs_get_report` | 检查报告（体检摘要＋发现＋四步链） |
  | `fs_query_facts` | 事实账本查询（写涉及数字的内容前先对账） |
  | `fs_search_kb` | 知识库检索（列文件／按路径读预览） |
- 首次使用给一个中文设置页，填论文根目录即可；配置存本插件私有数据目录，随时可改。

## 要求

- macOS（首版只保 macOS；Windows 二期）。
- MiniMax Code 桌面端 ≥ 3.1.2。
- Python ≥ 3.10（`python3` 在 PATH 里，或设环境变量 `FS_PYTHON` 指到你的 Python）。
  FactScribe 引擎已整体随插件带（vendored），**无需 pip 安装任何东西**。
- 可选：`tectonic`（「渲染 PDF」按钮用，没装只影响这一个按钮）。

## 安装

```sh
cd <本目录>
./build.sh      # 从 FactScribe 仓同步引擎与前端＋契约自检（发布前跑；仓内已备好成品）
./install.sh    # 同步到 ~/.minimax/plugins/factscribe/（幂等，可反复跑）
./install.sh --check   # 只查不装
```

装完**重启 MiniMax Code 桌面端**，对助手说「打开 FactScribe 工作台」即可打开页面。
卸载＝关掉 MiniApp 后删掉 `~/.minimax/plugins/factscribe/` 目录。

## 数据与访问（Data & access）

这一节按 MiniApp 平台的安全披露要求，写清本插件碰你机器上的什么。

**读**：
- 你在设置页指定的论文根目录（及其下三层）：只用来发现论文项目（含 `factscribe.toml` 的目录）、
  渲染章节、算检查报告、列知识库文件。引擎进程只绑 `127.0.0.1` 的内部端口，不对外。
- 插件自身的载荷目录（页面三件套与 Python 引擎，安装时已就位，运行时只读不写）。

**写**（只有两处）：
1. **插件私有数据目录**（宿主创建并持有的 `dataDir`）：只写一个 `config.json`（论文根目录路径，
   原子写：同目录临时文件再改名）。除此之外引擎进程被禁写字节码缓存（`-B` 启动），不产生 `__pycache__`。
2. **论文根目录下你确认要写的地方**：只在页面里**你亲自点保存**时发生——
   写 `sections/*.tex` 的正文与根文件装配行。保护措施沿用 FactScribe 写回链：
   - **原子写**：同目录 `.tmp` → fsync → rename，写坏了不会留半个文件；
   - **备份**：每次覆盖前留 `.bak`（保留上一次内容，可手工回退）；
   - **指纹闸**：保存时带所基于内容的 sha256 指纹，别人（或另一个窗口）改过就拒写（409 BLOCK_STALE），不盖你的改动；
   - **路径闸**：只写盘内 `sections/` 下的 `.tex`，`facts/`、`audit/`、`results/` 一律只读；
   - **绑定数字保护**：`\fact{}`、`\cite{}` 与绑定数字按原文原位保留，删了芯片也会按锚点补回；
     新写的 `\fact/\cite` 会被剥掉并告警——凭空造账本绑定是不允许的。
   报告导入向导只写 `facts/draft/`（草稿），**绝不写活账本**。

**AI 助手（MCP 工具）**：上面表格里 6 个工具**全部只读**，AI 拿不到任何写接口；
v1 没有改稿工具，v2 的写稿也走「提议单 → 人确认」。工具结果有长度上限，超限提示去页面看。

**子进程**：插件会拉起一个 Python 引擎子进程
（`python3 -B -m factscribe workbench --root <你配置的目录> --port 0 --json --no-browser`），
并可能在你的操作下再拉起 `factscribe audit`（检查报告只读重跑）、`tectonic`（渲染 PDF）、
macOS `open`（「打开目录」按钮）。这些进程随 MiniApp 停止而被终止。

**出站网络**：唯一一处是页面里的 AI 对话面板，按项目配置（`workbench.toml` 的 `[ai]`）
打一个 OpenAI 兼容端点，缺省 `http://127.0.0.1:8220/v1`（本机 vLLM）——不出本机；
你不配置它就没有任何出站流量。其余功能完全离线。

**权限声明**：本插件不申请任何宿主权限（无 agentAccess / toolAccess / deviceAccess）。

## 架构一句话

宿主只认 Node 入口：本插件的 Node 薄壳（`miniapp/node/server.mjs`，零 npm 依赖）占住宿主分配的
回环端口，伺服页面三件套、把 `/api/*` 反向代理给 Python 引擎子进程、在 `/mcp/factscribe` 上
提供 MCP 工具；`dispose` 时亲手杀掉 Python 子进程（宿主只停 Node，不会替我们收子进程）。
业务大脑（项目发现、渲染、写回保护链、检查报告）全部在 Python 引擎里，一行没改。

## 开发

- `./build.sh`：从 FactScribe 仓根复制引擎（排除 `__pycache__`/`tests`）与前端三件（零改动拷贝），
  并做插件包契约自检（≤1024 文件、单文件 ≤16 MiB、总 ≤64 MiB、路径纯 ASCII、无软链）。
- 独立自验 harness 在仓外（不入仓）：伪造宿主 context 起 `server.mjs`，断言代理、页面、
  MCP 六工具与 dispose 收尸。

## 宿主侧验收（2026-11-22 实测）

装用四步：`./build.sh` → `./install.sh` → 重启宿主桌面端 → 对助手说「打开 FactScribe 工作台」。
读数（macOS，Node 26.7，Python 3.14）：

- 插件簿里 `factscribe` 为 local 且 running；页面落在 `http://127.0.0.1:<宿主分配端口>/workbench`，
  项目列表与章节渲染都读的是真引擎数据（4 个论文项目、双语盘聚合）；
- MCP 六工具（`fs_status` / `fs_get_outline` / `fs_read_section` / `fs_get_report` /
  `fs_query_facts` / `fs_search_kb`）在本机 `/mcp/factscribe` 上 `initialize` → `tools/list` →
  `tools/call` 三步全通；
- 仓外 harness（伪造宿主 context）13/13 全绿：设置页 → 收表 → 页面 → 静态三件 → 引擎代理 →
  六工具 → 回环守卫（非回环 Host 403、跨站 Origin 403、合规 200）→ dispose 收掉 Python 子进程。

### 宿主侧三个已知接缝（排查时先看这里，别误判成薄壳坏了）

1. **401 是宿主加的，不是薄壳**。宿主在薄壳前面加了一层认证门：直连
   `127.0.0.1:<端口>` 一律回 401，正经通路是宿主分配的页面端口（面板里打开即是）。
2. **`servers.mcp.json` 里的 `http://127.0.0.1:9/mcp/factscribe` 是官方 fail-closed 占位**，
   宿主接管时改写成当前运行端口（miniapp-creator 的 `references/mcp.md` 口径）。
   接管发生在**下一次模型请求**前：本回合 `tool_search` 查不到 `mcp__factscribe__*` 属正常，
   下一回合才进工具表。
3. **宿主的 `plugin_uninstall` 对本地插件报 INTERNAL**（`Plugin System Cloud request was rejected`）。
   退路：移除 `~/.minimax/plugins/<id>` 与 `~/.minimax/v2/plugin-data/liveboards/<id>`；
   插件簿是扫目录得出的，目录一删条目即消失。

### 首启配置在哪

插件私有 dataDir：`~/.minimax/v2/plugin-data/liveboards/factscribe/`。
里面 `config.json` 就是 `{"root": "<论文根目录>"}`——未配置时页面给中文设置页，
填完由薄壳原子写回并换根重启引擎。论文根是**目录**（含 `factscribe.toml` 的子目录会被扫成项目）。
