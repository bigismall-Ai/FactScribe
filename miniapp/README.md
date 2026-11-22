# FactScribe 论文工作台（MiniMax Code MiniApp）

把 FactScribe 本地论文工作台装进 MiniMax Code 桌面端：页面里看稿、改稿、看检查报告，
AI 助手通过 8 个 MCP 工具帮你查稿况、读正文、对事实账，以及提改稿提议单。

**人在回路（Human-in-the-loop）立场**：AI 只读、只建议；一切落笔都在页面里由你确认
（v2 的写稿只以「提议单 → 页面弹差异卡 → 你确认」的方式出现：**助手没有任何直接改正文的接口**）。

## 功能

- **工作台页面**（路由 `/workbench`）：项目与稿盘清单、章节芯片渲染（`\fact{}`、`\cite{}`、
  绑定数字显示为不可误碰的芯片）、正文写回（指纹闸保护）、检查报告、事实账本、知识库、AI 对话面板。
- **AI 助手工具面**（`/mcp/factscribe`）：前六个只读，后两个只提提议：
  | 工具 | 干什么 |
  |---|---|
  | `fs_status` | 项目与稿盘清单＋当前论文根目录 |
  | `fs_get_outline` | 某稿盘的目录树（标题级） |
  | `fs_read_section` | 某段（或某文件全部块）的 LaTeX 原文 |
  | `fs_get_report` | 检查报告（体检摘要＋发现＋四步链） |
  | `fs_query_facts` | 事实账本查询（写涉及数字的内容前先对账） |
  | `fs_search_kb` | 知识库检索（列文件／按路径读预览） |
  | `fs_propose_edit` | 提一份改稿**提议单**（不写盘，等人确认） |
  | `fs_list_proposals` | 看待人确认的提议单 |
- 首次使用给一个设置页（中/EN 都有），填论文根目录即可；配置存本插件私有数据目录，随时可改。
- **中/EN 界面语言开关常显**：左栏头部任何视图都在（项目管理页、新建页、工作台页），
  首启设置页也有一枚；进工作台后它顺带切盘，没有对应盘就只切界面语言。
- **AI 助手接 mcode 的模型**：MiniApp 里的对话直接跑**宿主 Agent 回合**（模型就是 mcode 自己那个），
  边跑边出字；面板顶上标出这轮是谁答的（宿主 Agent／本地后端）。
- **模型与思考等级可自选（v4）**：面板下拉里列**宿主自己的模型目录**（两个模型，各自带思考等级档位），
  另有一项「宿主默认」＝用 mcode 当前这个模型；选了模型还能选思考等级（关闭思考／低／中／高……）。
- **可以自己加自定义模型（v4）**：面板里填名称＋Base URL＋模型名＋API Key，就多一个可选项
  （OpenAI 兼容端点）；密钥只存在插件私有目录，不进论文目录、也不回传给页面。

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

改了插件代码要重发时，走 `miniapp publish --pluginId factscribe --sourcePath <本目录>`
（`miniapp restart` 只重跑宿主暂存里的旧副本，不刷新代码，见接缝 5）。

## 数据与访问（Data & access）

这一节按 MiniApp 平台的安全披露要求，写清本插件碰你机器上的什么。

**读**：
- 你在设置页指定的论文根目录（及其下三层）：只用来发现论文项目（含 `factscribe.toml` 的目录）、
  渲染章节、算检查报告、列知识库文件。引擎进程只绑 `127.0.0.1` 的内部端口，不对外。
- 插件自身的载荷目录（页面三件套与 Python 引擎，安装时已就位，运行时只读不写）。

**写**（只有两处）：
1. **插件私有数据目录**（宿主创建并持有的 `dataDir`）：
   - `config.json`——论文根目录路径（原子写：同目录临时文件再改名）；
   - `proposals/`——待人确认的改稿提议单（v2：状态，不是论文内容）；
   - `custom-models.json`——**v4：自定义模型的凭据**（含 API Key，文件权限 0600）；
   除此之外引擎进程被禁写字节码缓存（`-B` 启动），不产生 `__pycache__`。
2. **论文根目录下你确认要写的地方**：只在页面里**你亲自点保存**时发生——
   写 `sections/*.tex` 的正文与根文件装配行。保护措施沿用 FactScribe 写回链：
   - **原子写**：同目录 `.tmp` → fsync → rename，写坏了不会留半个文件；
   - **备份**：每次覆盖前留 `.bak`（保留上一次内容，可手工回退）；
   - **指纹闸**：保存时带所基于内容的 sha256 指纹，别人（或另一个窗口）改过就拒写（409 BLOCK_STALE），不盖你的改动；
   - **路径闸**：只写盘内 `sections/` 下的 `.tex`，`facts/`、`audit/`、`results/` 一律只读；
   - **绑定数字保护**：`\fact{}`、`\cite{}` 与绑定数字按原文原位保留，删了芯片也会按锚点补回；
     新写的 `\fact/\cite` 会被剥掉并告警——凭空造账本绑定是不允许的。
   报告导入向导只写 `facts/draft/`（草稿），**绝不写活账本**。

**AI 助手（MCP 工具）**：上面表格里前 6 个工具**全部只读**；后 2 个只做一件事——
把改稿提成**提议单**（落宿主私有目录，不碰正文）。AI 拿不到任何直接改正文的接口：
真正的落盘只能由人在页面的「待确认」差异卡里点「采纳写回」。工具结果有长度上限，超限提示去页面看。

**子进程**：插件会拉起一个 Python 引擎子进程
（`python3 -B -m factscribe workbench --root <你配置的目录> --port 0 --json --no-browser`），
并可能在你的操作下再拉起 `factscribe audit`（检查报告只读重跑）、`tectonic`（渲染 PDF）、
macOS `open`（「打开目录」按钮）。这些进程随 MiniApp 停止而被终止。

**出站网络**：只有 AI 对话会出去，三条路：
- **MiniApp 里（宿主模型）**：AI 面板跑**宿主 Agent 回合**（`miniapp.json` 声明 `agentAccess: ["session.run"]`，
  宿主把 `context.agent` 交给薄壳）。用的模型就是 MiniMax Code 自己那个，走**宿主的账号与额度**；
  插件**不读你的 API key、不读宿主的配置**。回合在宿主里跑，材料（正文、知识库、检查报告摘要）
  是拼成提示词发过去的。
- **MiniApp 里（自定义模型，v4）**：你在面板里自己填的 OpenAI 兼容端点。**这条路的出站由你决定**——
  填什么 Base URL 就打哪里，凭据只存在插件私有目录，材料（同一套 `prepare_prompt` 组好的提示词）
  会发到那个端点；端点连不上时回复会明确标成「模拟回答（未接模型）」，不会假装是模型答的。
- **浏览器模式**（不开 MiniApp 的独立用法）：按项目配置（`workbench.toml` 的 `[ai]`）打一个
  OpenAI 兼容端点，缺省 `http://127.0.0.1:8220/v1`（本机 vLLM）——不出本机。

其余功能完全离线。

**权限声明**：本插件只申请一项宿主能力——`agentAccess: ["session.run"]`（让 AI 面板能跑宿主
Agent 回合）。没有 toolAccess / deviceAccess：插件不碰宿主工具、不碰设备。面板里的工具调用
**一律回绝**（模型被告知原因，改按材料回答），助手不会在机器上动手。

## 架构一句话

宿主只认 Node 入口：本插件的 Node 薄壳（`miniapp/node/server.mjs`，零 npm 依赖）占住宿主分配的
回环端口，伺服页面三件套、把 `/api/*` 反向代理给 Python 引擎子进程、在 `/mcp/factscribe` 上
提供 MCP 工具；`dispose` 时亲手杀掉 Python 子进程（宿主只停 Node，不会替我们收子进程）。
业务大脑（项目发现、渲染、写回保护链、检查报告）全部在 Python 引擎里，一行没改。

## 开发

- `./build.sh`：从 FactScribe 仓根复制引擎（排除 `__pycache__`/`tests`）与前端三件（零改动拷贝），
  并做插件包契约自检（≤1024 文件、单文件 ≤16 MiB、总 ≤64 MiB、路径纯 ASCII、无软链）。
- 独立自验 harness 在仓外（不入仓）：伪造宿主 context 起 `server.mjs`，断言代理、页面、
  MCP 八工具、提议单流与 dispose 收尸。

## 宿主侧验收（2026-11-22 实测）

装用四步：`./build.sh` → `./install.sh` → 重启宿主桌面端 → 对助手说「打开 FactScribe 工作台」。
读数（macOS，Node 26.7，Python 3.14；接缝清单见文末）：

- 插件簿里 `factscribe` 为 local 且 running；页面落在 `http://127.0.0.1:<宿主分配端口>/workbench`，
  项目列表与章节渲染都读的是真引擎数据（4 个论文项目、双语盘聚合）；
- MCP 八工具（六个只读＋`fs_propose_edit` / `fs_list_proposals` 两个提议工具）在本机
  `/mcp/factscribe` 上 `initialize` → `tools/list` →
  `tools/call` 三步全通；宿主登记簿 `~/.minimax/mcp-runtime-names.json` 已收录这八个工具名；
- **v2 提议工具经宿主真调**（2026-11-22 10:59，另开会话跑的）：助手侧 `fs_propose_edit`
  对 `01-intro-p1` 提单 → `prop-20261122-105942-4216`（status=pending，source=mcp）；
  `sections/01-intro.tex` 的 sha256 提单前后同为
  `b6022d92e9f9da6c57144c6819012399d31614e880de588031ab9f241f231385`，文件 mtime 未变；
  `fs_list_proposals` 列得该单 status=pending；引擎给出 5 条保护面补回告警
  （1 ref＋3 fact＋1 num 按原文位置补回）。
- 仓外 harness（伪造宿主 context）18/18 全绿：设置页 → 收表 → 页面 → 静态三件 → 引擎代理 →
  八工具 → 回环守卫（非回环 Host 403、跨站 Origin 403、合规 200）→ **提议单流**
  （MCP 建单时正文一字节没动 → 列表可见 → 人确认后才落盘 → 清单清空）→ dispose 收掉 Python 子进程；
  v3 加了宿主 Agent 桩：两种模式各跑一遍（无 Agent 19/19、有 Agent 23/23）。
- **宿主真的把 `context.agent` 给了插件**：`fs_status` 回报 `hostAgent: true`
  （2026-11-22 12:5x 实测），AI 面板因此走 mcode 的模型。

### 宿主侧五个已知接缝（排查时先看这里，别误判成薄壳坏了）

1. **401 是宿主加的，不是薄壳**。宿主在薄壳前面加了一层认证门：直连
   `127.0.0.1:<端口>` 一律回 401，正经通路是宿主分配的页面端口（面板里打开即是）。
2. **`servers.mcp.json` 里的 `http://127.0.0.1:9/mcp/factscribe` 是官方 fail-closed 占位**，
   宿主接管时改写成当前运行端口（miniapp-creator 的 `references/mcp.md` 口径）。
   接管发生在**下一次模型请求**前：本回合 `tool_search` 查不到 `mcp__factscribe__*` 属正常，
   下一回合才进工具表。
   复核（2026-11-22 10:26）：下一回合工具表已出现六个 `mcp__factscribe__*`，逐个实调——
   `fs_status` 返回 4 个项目 / 6 个稿盘；`fs_query_facts` 读出 minimal 的三条账（A1 10/16、A3 8/16、
   A2 56.25%，带来源、定位与指纹）；`fs_get_outline` 给出两个章节条目与 sha；
   `fs_read_section` 还原 `sections/01-intro.tex` 的原始 LaTeX（芯片回到 `\fact{}` 形态）；
   `fs_get_report` 读出 paper-b 真报告（health=ok，red 0 / yellow 0，facts 62 / sections 10）；
   `fs_search_kb` 列得 21 个知识库文件。
3. **宿主的 `plugin_uninstall` 对本地插件报 INTERNAL**（`Plugin System Cloud request was rejected`）。
   退路：移除 `~/.minimax/plugins/<id>` 与 `~/.minimax/v2/plugin-data/liveboards/<id>`；
   插件簿是扫目录得出的，目录一删条目即消失。
4. **工具表按会话缓存**：插件重发后，宿主会重连 MCP 并把新工具名写进登记簿，
   但**当前会话**的工具表可能仍停在旧清单（本回合 `tool_search` 查不到新工具即属此）。
   实测：新开一个会话，工具表已是八个 `mcp__factscribe__*`（含两个提议工具），逐个实调通过。
5. **`miniapp restart` 重跑的是宿主暂存里的旧副本**：改完插件代码要生效，
   用 `miniapp publish --pluginId factscribe --sourcePath <插件目录>`（publish 会把源装进
   `~/.minimax/plugins/<id>` 再起运行时）。
6. **引擎子进程被杀后，薄壳手里的端口有一拍没清**：直接 `kill` 引擎进程，
   接着的两次业务请求都回 `engine_unreachable`（ECONNREFUSED）且不重拉引擎；
   `miniapp restart --pluginId factscribe` 之后恢复（重读配置、按新 root 重拉引擎）。
   换论文根请走设置页/配置写回，别手杀引擎进程。

### 首启配置在哪

插件私有 dataDir：`~/.minimax/v2/plugin-data/liveboards/factscribe/`。
里面 `config.json` 就是 `{"root": "<论文根目录>"}`——未配置时页面给中文设置页，
填完由薄壳原子写回并换根重启引擎。论文根是**目录**（含 `factscribe.toml` 的子目录会被扫成项目）。
同一目录里还有两样：**`proposals/`**（v2 的待确认提议单）与 **`custom-models.json`**
（v4 的自定义模型凭据，0600）。三样都在插件私有目录里，**都不在论文目录里**。

## v2：提议单改稿（助手提议 → 人确认才写回）

- **助手侧**：`fs_propose_edit` 把一段改稿提成**一张提议单**（落宿主私有 dataDir，**不碰正文**），
  `fs_list_proposals` 看待确认的。助手**没有**直接改正文的接口；
- **页面侧**：左栏头部出现「待确认 N」→ 差异卡（左＝现状，右＝采纳后，逐行标增删）→
  「采纳写回」／「拒绝」；采纳后自动重跑检查报告；
- **落盘只有一条路**：人点采纳 → 复用工作台既有写回保护链（指纹闸 → 保护面重建 →
  花括号配平 → 原子写＋.bak）。提议之后正文若被别处改过 → **BLOCK_STALE 拒写**，不覆盖；
- **提议单不是论文内容**：落状态目录（`--state-dir` → `$FACTSCRIBE_STATE_DIR` → `~/.factscribe/state`），
  论文目录不因为「有人提建议」而变脏；
- 顺带补上的洞：`/draft/insert`（AI 面板「写进稿」）以前**绕过指纹闸**直写稿，
  现在它走提议单，草稿通道本身也加了指纹校验。

设计件：`docs/design/SPEC-MINIAPP-V2.md`；考题：`tests/test_workbench_proposal.py`（17 例）。

## v3：AI 面板接 mcode 的模型

- **怎么接的**：薄壳拿到宿主给的 `context.agent`（声明 `agentAccess: ["session.run"]` 才有），
  把这一轮交给它跑——**用的模型就是 mcode 自己那个**。
- **材料口径不变**：引擎新增 `POST /api/chat/prepare`，只组装提示词、**不调任何模型**；
  材料（当前正文、知识库、检查报告摘要、引用段）用的是与 `/api/chat` 同一套 `build_context`，
  两边看到的东西一致。
- **边跑边出字**：宿主 Agent 回合走 SSE（`text/event-stream`）——`delta` 增量、`done` 收尾，
  面板里的气泡随字出现。浏览器模式的老后端仍回 JSON，两种都吃。
- **面板里标明是谁答的**：AI 面板那行标出「后端：MCode 宿主模型」还是「后端：本地后端」；
  MCP 的 `fs_status` 也回报 `hostAgent`，助手能自己看。
- **只读，不动手**：面板里的工具调用**一律回绝**（模型被告知原因，改按材料回答）；
  问卷类提问自动跳过（面板里没有问卷界面，不把回合挂死），并在气泡上说明。
- **会话连着**：宿主给的 `sessionId` 记在页面里，下一轮接着同一个会话（模型记得上文）。
- **兜底**：宿主 Agent 不可用（宿主旧版／未授权）→ 回落引擎的本地后端
  （`workbench.toml` 的 `[ai]`），面板照旧显示是谁答的。

## v4：模型选择（宿主模型＋思考等级）与自定义模型

- **按宿主那套模式直接嵌**：薄壳读宿主给的模型目录（`agent.models()`），
  把每个模型做成面板下拉里的一项，并带上**这个模型支持的思考等级档位**
  （目录里 `variants` 含空串＝「关闭思考」也算一档）。第一项是「宿主默认」——
  不指定模型，用 mcode 当前这个模型（与旧行为一致）。
- **选的模型真的被用上**：面板发的（模型＋等级）会被核对目录，再按宿主的形状传给回合：
  `{providerId, modelId, variant?, thinking:{effort}}`——`off` 走 `variant: ""`，
  其余档走 `thinking.effort`，「模型默认」走目录给的默认档。
- **失效不偷换**：模型或等级宿主不认了（目录里没有／宿主报 INVALID_ARGUMENTS），
  明确回 `MODEL_UNAVAILABLE` 让页面重选——**不会**悄悄换个模型答给你。
- **自定义模型（BYOK）**：面板「＋ 模型」填名称／Base URL／模型名／API Key；
  凭据落插件私有 `dataDir` 的 `custom-models.json`（0600），**不进论文目录**，
  回给页面的只有 `hasKey`（有没有配密钥），**密钥不出薄壳**。
  选它时走 OpenAI 兼容通道：引擎组材料（同宿主通道那套 `prepare_prompt`）→ 薄壳打
  `{base_url}/chat/completions`（带 `Authorization: Bearer …`）。
- **写盘面没变**：插件仍然只写「私有 dataDir」与「你确认过的论文位置」两处；
  自定义模型只是多了一个 dataDir 里的 json 文件。
- 考题：`tests/test_miniapp_models.py`（26 例，静态契约）＋
  `tests/test_miniapp_shell_models.py`（8 例，**真起薄壳**跑模型三条路，
  带宿主 Agent 桩与 OpenAI 兼容桩）。

### v4 宿主侧实测（2026-11-22，宿主真的给了模型目录）

- **目录真读到了**：面板下拉五项——「宿主当前模型」（＝宿主默认，不指定模型就用 MCode 当前那个）、
  `M3.1-Flash`、`M3`、`custom_provider:minimax-direct/MiniMax-M3.1-Flash`、
  `custom_provider:mm-direct2/MiniMax-M3.1-Flash`。目录里 displayName 重样时自动加 provider 尾注
  （不然三个都叫「MiniMax-M3.1-Flash」，分不清谁是谁）。
- **思考等级真列出来了**：M3.1-Flash 有 7 档（default／low／medium／high／xhigh／max／off），
  下拉里连「模型默认」一共 8 项；M3 只有 off；两个 custom_provider 没有档位。
- **选的模型真被用上**：选 M3.1-Flash ＋ High 提问，徽标读
  「Backend: MCode host model · M3.1-Flash · High」，答的是这篇稿子里的真问题
  （Demo 段有个未绑定的数字 7）。
- **自定义模型真跑通**：面板填「本地桩模型 / http://127.0.0.1:8231/v1 / qwen-32b / 密钥」
  → 下拉多出「本地桩模型 · Custom」；选中提问，徽标读「Backend: custom model · 本地桩模型」，
  回答来自桩后端；桩端收到 `POST /v1/chat/completions`，带
  `Authorization: Bearer …`，模型名 `qwen-32b`，提示词里带着材料。
- **凭据没乱跑**：`custom-models.json` 落在插件私有 dataDir，权限 `0600`；
  论文根（`/Users/moc/workspaces/SiAgent`）下搜不到它。删模型走面板上的 ✕，删完下拉即清空。
- 界面切到 EN 时，下拉项、思考等级与徽标一并切英文（"Model default (Default)"、
  "Thinking off"、"Backend: custom model · …"）；切语言时下拉会重画，选中的模型不丢。
- **不碰你的密钥**：插件不读 API key、不读宿主配置；模型走宿主账号与额度。

考题：引擎侧 `tests/test_workbench_ai.py`（+8 例：提示词组装、双语角色提示、
不许调工具、引用与历史、端点 200/400/404）；仓外 harness 两种模式各跑一遍——
没有宿主 Agent 时 19/19（回落本地后端），有 Agent 桩时 23/23（宿主通道接管、提示词带材料、
SSE 流式、工具调用回绝、模型清单＝宿主 Agent）。
