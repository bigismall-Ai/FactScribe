# MiniFactScribe —— FactScribe 的 Mini App

把 FactScribe 的**机械闸门**搬到 MiniMax Code 的 Mini App 面板里，在浏览器本地跑。
不装 Python、不连服务器、不写论文正文。

> **这是一个第三方移植件，不是 FactScribe 的一部分。**
> 它不进入 `factscribe/` 包，不参与本仓库的 Python 打包、测试矩阵与退出码契约。
> 上游 `factscribe/` 的行为、退出码与违规码一律未改。
> 移植件自身的缺陷请开在 `integrations/minifactscribe/` 下的 issue，不要混进上游判据问题。

---

## 它做什么

一句话：**正文里的每个数，能不能回到一份签过字、算过哈希的原始材料。**

Mini App 只有一个判定引擎：**上游的 Python 原版**。Node 这一侧不再自带审计实现，
只做三件事：启动 Python 工作台、把请求代理过去、把结果渲染出来。

界面上的页签：

| 页签 | 干什么 |
|---|---|
| 工作台 | 当前论文项目的章节：源码 / 预览双栏、章节目录、要处理的问题 |
| 工作台事实账 | 论文项目的事实账：追加事实、证据冻结 |
| 实验报告 | 封存 / 签收 / 导入一份实验报告 |
| 引用 | 多个 bib 汇总：引了哪些、哪些缺标识、哪些没被引用（只读） |
| 项目 | 论文项目列表、新建项目、一键启动工作台 |
| AI 起草 | 宿主 agent 起草当前节，输出只进候选区，采纳后才写入 |

---

## 与上游的对应关系

**没有移植了。** 判定只有一套：上游的 Python 原版。

Node 这一侧（`miniapp/node/server.mjs`）不再自带审计实现，只做代理：
把 `/api/workbench/*` 转给本机 `factscribe serve`，把上游的 400 / 403 / 409 原样带回。
接口语义、违规码、处方与退出码契约，一律以上游为准；插件里没有第二套判据，
也就不会出现「Mini App 判红、Python 判绿」这种对不上的情况。

早先这里有一份 JS 移植件（`miniapp/node/audit.mjs` + `demo.mjs`）和一把
「JS ↔ Python 一致性锁」（`tests/conformance.test.mjs`）。两者都已删除：
一份判据两处实现，本身就是不一致的来源。现在只剩一个引擎，也就没有对不上的可能。

### 上游有、这里没有

| 缺什么 | 为什么 |
|---|---|
| verify-pdf / PDF 直读 | Mini App 侧不做 PDF 解析 |
| style / polish / terms 等 CLI 子命令 | 界面里没有它们的入口，命令行仍可用 |

---

## 跑起来

需要 Node 18+（用到 node:crypto 与 fetch）。零第三方依赖，只用 Node 内置模块与浏览器 API。

### 作为 Mini App 装到 MiniMax Code

把 integrations/minifactscribe/ 整个目录拷进 MiniMax Code 的工作区，用 miniapp init 绑定，
然后 miniapp publish。面板里会出现「事实闸 FactScribe」。

### 单独跑测试（不依赖 Mini App 宿主）

~~~bash
node --test integrations/minifactscribe/tests/*.test.mjs
~~~

界面层的断言读的是 `miniapp/client/` 里的静态文件，不需要宿主。

---

## 界面是共用的一份

这个页签式的界面同时是 `factscribe web` 的页面：源在 `factscribe/web/`，插件里是拷贝
（`scripts/sync-miniapp-ui.sh` 同步，测试钉住逐字节一致）。页面自己判断在哪运行：

- 在 MiniApp 里：显示「AI 起草」与一键启动工作台；
- 在浏览器里：藏掉宿主专属页签，向你要 token，操作真实论文项目；
- 网页加 `?dev=1`（或 `factscribe web --dev`）：把宿主专属区也显示出来，方便对照调试。

## 论文项目与一键启动工作台

**一个文件夹就是一个论文项目**（里面有 `paperkit.toml`）。切换项目＝换文件夹；
工作台的读写、审计只对当前文件夹生效。

```text
工作台页签
  最近项目 [下拉]        ← 来自 ~/.factscribe/projects.json
  项目文件夹 [/path/...] ← 手填、或用当前对话项目
  [加入项目列表] [用当前对话项目] [从列表移除]
  ☐ 允许写章节与事实（--allow-write）   ☐ 允许编译 PDF（--allow-build）
  [启动并连接] [停止工作台]
```

- 启动只跑固定命令，不经过 shell：
  `<python> -m factscribe serve <文件夹> --port 0 --json [--allow-write] [--allow-build]`；
  读首行 JSON 拿到 URL/token 后自动连接；「停止工作台」或插件退出时杀掉子进程；
- 启动前重新校验文件夹：必须存在、是目录、含 `paperkit.toml`；
- 登记册在 `~/.factscribe/projects.json`（0600），不在 dataDir——重装插件还认得；
  `dataDir/workbench.json` 只存手动连接的 URL/token；
- 一键启动的服务跟着本进程活：宿主重启后不会假装还连着；
- **前提**：能 `import factscribe` 的 Python。没装包时在「高级」里填解释器
  （如某个 venv 的 `bin/python3`）和包路径（源码仓库根，走 `PYTHONPATH`），
  或设 `FACTSCRIBE_PYTHON`；
- 手动连接仍然保留在「高级」里：只接受 `http://127.0.0.1:...` / `http://localhost:...`，
  token 不进页面；
- 默认只读；写章节只接受审计闭包内的 `.tex`，不新建、不删除、不改名。

## AI 起草（宿主 agent）

「AI 起草」页签用 mcode 宿主的大模型，不接模型 SDK：

- 先在「工作台」连接本地 `factscribe serve` 并载入项目；
- **从论文项目的对话里打开本页**（页面发起的 session 才会绑定项目目录）；
  页面用 `agent.session()` 读当前对话的 `workspaceDir`，显示在「工作台」里；
  从插件库/首页打开、或对话没有项目文件夹时，会显示提示条并禁用 AI 起草；
- 选一节，点「生成候选」；agent 的输出只进候选区；
- 工具审批卡出现时，由你点「允许一次 / 拒绝」；
- 点「采纳并写入本节」后才写工作台项目，并自动重跑审计。

要求写在提示里：只能使用账里已有的数字，不得编造；输出完整替换本节的 LaTeX。
这一版不处理问卷；遇到问卷会提示到聊天侧面板回答。

## 测试

~~~bash
cd integrations/minifactscribe
node --test tests/
~~~

31 例判据层自测，全离线（`node:test` + `node:assert`，零第三方依赖）。每个判据都有正反两例：
数字归一化与值域、绑定硬约束、引用族 fail-closed、稳定标识、派生事实重算、
界面层的不变量还钉着：界面与 MiniApp 逐字节一致、导航只有那几页、
问题码有中文短名、危险动作先确认、旧的本地草稿整套不许回来。

另有 7 例暗色主题不变量（`tests/styles.test.mjs`）、84 例呈现层可读性不变量
（`tests/ui.test.mjs`）与 5 例本地工作台连接层（`tests/workbench.test.mjs`）：
问题码必须有中文短名、危险动作必须先确认、草稿页与草稿接口不许复辟；
工作台只接受本机 http、token 不对要拒绝。
再加上 6 例项目登记册与启动握手（`tests/projects.test.mjs`）、9 例 Node 路由
（`tests/server-routes.test.mjs`）与 4 例界面同步（`tests/sync.test.mjs`）：
六组共 117 例，全部离线（握手用假解释器，不 spawn 真 Python；路由用临时 HOME）。

---

## 示例论文

「打开示例论文」装的是上游 `examples/minimal`（MIT 许可），由上游的
`factscribe samples guide` 装进 `~/.factscribe/`：

- 3 条事实：A1 = 10/16、A3 = 8/16，A2 = 56.25% 是 expr 派生的
- 1 份来源材料 results/swb16.md（哈希现算）
- 2 条上游 bib + 演示用的坏条目

正文沿用上游样例，故意埋的问题与上游一致：

- 47.3,ms —— 账外数字 → UNMATCHED_NUMBER（红）
- cite{ghost2024} —— bib 里没有的 key → MISSING_CITE（红）

读数以上游为准：改一个数、重跑审计、看着红牌变绿，走的就是 Python 原版那条路。

---

## 边界

绿只说明三件事：账有据、据未改、文有绑。**它不说明结论为真**，也不替审稿人判断结论是否成立。

插件在上游边界之外还有一条自己的边界：

- **判定只在工作台连上之后才有。** Node 这一侧不自己判，代理没连上就没有红黄牌。
  工作台页签的「用工作台审计」按钮在没连上时是灰的，页面上也写明为什么。

---

## 目录

~~~
integrations/minifactscribe/
├── README.md                    # 本文件
├── package.json                 # Mini App 包声明
├── icon.png
├── .minimax-plugin/plugin.json  # 插件清单
├── tests/
│   ├── styles.test.mjs          # 暗色主题不变量，7 例
│   ├── ui.test.mjs              # 呈现层不变量，85 例（含「草稿不许回来」）
│   ├── workbench.test.mjs       # 本地工作台连接层，5 例
│   ├── projects.test.mjs        # 论文项目登记册 + 启动握手，6 例
│   ├── sync.test.mjs            # 网页与 MiniApp 界面逐字节一致，4 例
│   └── server-routes.test.mjs   # 项目/启动/静态资源路由，10 例
└── miniapp/
    ├── miniapp.json             # surface / runtime 配置
    ├── client/                  # 浏览器端：index.html / app.js / app.css
    └── node/                    # Node 端：server.mjs（API + 代理）/ launcher.mjs / projects.mjs
~~~

- server.mjs —— REST API 与工作台代理（判定全在 Python 一侧）
- launcher.mjs —— 一键启动 `factscribe serve` 子进程
- projects.mjs —— 论文项目登记册（`~/.factscribe/projects.json`）
- tests/styles.test.mjs —— 暗色主题不变量（主按钮 hover、滚动条配色）
- tests/ui.test.mjs —— 呈现层不变量（中文短名、危险动作确认、草稿已删除）
- tests/workbench.test.mjs —— 本地工作台地址校验与带 token 的代理

## Tested environment

- macOS，MiniMax Code 3.1.14（Mini App 3.1.14）
- Node 24.19
- 零第三方依赖；`node --test integrations/minifactscribe/tests/*.test.mjs` 全离线

## Data & access

- 默认不联网：判定与示例论文都在本地。
- 项目数据存在宿主分配的私有 `dataDir`，不写工作区。
- 只连本机回环地址；token 不返回页面。一键启动只跑固定命令，项目文件夹由你指定并校验
  （必须含 `paperkit.toml`），不写项目文件夹除非你点保存/采纳。
- 项目登记册在 `~/.factscribe/projects.json`：只存文件夹路径、显示名、上次使用时间，
  不存正文；你可以随时删。
- 声明 `hostAccess: ["navigation.read"]`：只用来判断当前是不是从论文对话打开（`view`），不读对话内容。
- 声明 `agentAccess` 含 `session.read`：只调用 `agent.session()`（不带 id）读**当前对话**的
  项目文件夹；不列、不读其他对话。
- 声明 `agentAccess: ["session.run"]`：AI 起草会把当前节、事实账与你的要求发给宿主 agent；
  agent 可能读写工作区，所有工具审批由你在页面上决定；不声明 `toolAccess`。

---

## 许可

本移植件与本仓库同属 MIT。移植自 bigismall-Ai/FactScribe 的部分保留了上游的语义与代码结构，
版权归 FactScribe contributors。
