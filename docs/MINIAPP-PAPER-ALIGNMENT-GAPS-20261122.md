# 论文侧 Miniapp ↔ 核心论文工作台：能力对齐缺口清单

> 日期：2026-11-22　分支：`feat/miniapp-host-seam`　基准：aad2e3e ＋ **本批（A/B 两组全收口）**
>
> **本批状态：A 组 4 项全部实现，B 组 6 项全部对齐（其中 G7 核实后本已对齐）。**

> **第七轮（2026-11-23）追加：G16–G19 四项全部实现**（改章节名／改论文标题／右栏宽度可拖／保护面命令的省力入口），
> 全仓 `pytest tests/ -q`＝**2353 passed / 0 failed**；miniapp 已 publish 到本机宿主，
> **源 → 载荷 → 已发布 104/104 文件逐字节一致**——见 §13。
>
> **第五轮（2026-11-23）追加：G12–G15 四项必做全部实现**，全仓 `pytest tests/ -q`＝**2271 passed / 0 failed**。
> 第 8/9 条（证据锁读数并进检查报告／投稿包导出前预览清单）**只记录不实现**，待用户拍板——见 §11.3。
> 全仓 `pytest tests/ -q`＝**2167 passed / 0 failed**（本批前基线 2120 passed）。
> MiniApp 已 publish 到本机宿主（`~/.minimax/plugins/factscribe/`），发布态载荷
> 走**真实 MCP 协议**验过：17 个工具全部可调、新读数结构化返回、论文目录零改动。
>
> 这份清单比的是**两侧**：
>
> * **核心**＝`factscribe/workbench/`（本地网页工作台）＋ `factscribe/mcp.py`（CLI 的
>   MCP 面，`factscribe_*` 工具）；
> * **Miniapp**＝`miniapp/`（同一套前端 + Node 薄壳 + MiniApp MCP 面，`fs_*` 工具）。
>
> Miniapp 的前端**就是**核心前端的逐字节拷贝（`miniapp/build.sh` 第 2 步同步
> `factscribe/workbench/static/` → `miniapp/miniapp/client/`；
> `tests/test_miniapp_align.py::PayloadInSyncTests` 守着这条不变式）。
> 所以**界面能力基本齐平**，缺口集中在两处：
>
> 1. **宿主问不到**：核心有、Miniapp 的 MCP 面上没有；
> 2. **口径不一致**：两侧都有，但读数形状／文案语言／行为不同。
>
> **优先级口径**：**P0**＝宿主在 Miniapp 里会做错事或拿不到关键读数；**P1**＝能力缺口
> （宿主问不到某件事）；**P2**＝口径不一致（两侧都有，只是形状/语言/时机不同）。

---

## 1. 结论摘要

| # | 事项 | 类别 | 优先级 | 本批状态 |
|---|------|------|--------|----------|
| G1 | 证据锁读数（冻结状态／差异／最后一条日志）宿主问不到 | 核心有·Miniapp 缺 | P1 | ✅ **已实现** `fs_get_evidence_status` |
| G2 | 证据冻结／解冻、add_fact 宿主做不了 | 核心有·Miniapp 缺 | P1 | ✅ **已实现**（四个提议单工具） |
| G3 | 写作简报（brief）宿主问不到 | 核心有·Miniapp 缺 | P1 | ✅ **已实现** `fs_get_brief` |
| G4 | 两条 MCP 面的 finding 文案语言口径不同 | 口径不一致 | P2 | ✅ **已对齐**（CLI MCP 面补 i18n 原料 ＋ `lang`） |
| G5 | CLI 的 JSON 输出仍只有中文文案 | 口径不一致 | P2 | ✅ **已对齐**（`audit --json` / `style --json` 加 `--lang`） |
| G6 | 模型选择与思考等级两侧不同源 | 口径不一致 | P2 | ✅ **已对齐**（共用模型档位声明 ＋ 核心侧 `effort`） |
| G7 | AI 对话后端两侧不同 | 口径不一致 | P2 | ✅ **已核实：两侧本已同源**（`/api/chat/prepare` 两侧都有） |
| G8 | 改稿路径两侧不同（直接写 vs 提议单） | 口径不一致 | P2 | ✅ **按建议保留 Miniapp 的提议制**，并写进工具注解与 INSTRUCTIONS |
| G9 | 版式配置（venue）与投稿包导出宿主做不了 | 核心有·Miniapp 缺 | P2 | ✅ **已实现** `fs_get_venue` ＋ `fs_propose_export_bundle` |
| G10 | 机器视图的分组标题是后端中文 | 口径不一致 | P2 | ✅ **已对齐**（四个分组加 `title_key`；2026-11-23 补：组内的命令标签/说明也走 `label_key`/`note_key`，见 §8） |
| G12 | 追加事实的 value 不校验产物原文（只有界面提示，不拦） | 核心有·Miniapp 缺 | P0 | ✅ **已实现**：建单前硬闸＋采纳时复核（`factscribe/valuecheck.py`） |
| G13 | 追加事实提议单没有 `before_sha` 指纹闸（其余三类单都有） | 口径不一致 | P0 | ✅ **已对齐**：以目标账本文件 sha256 为闸，账本被别处改过即 `BLOCK_STALE` 拒写 |
| G14 | 候选列表把 8124 个未签产物与 9 个已签产物平铺在一起 | 口径不一致 | P1 | ✅ **已对齐**：默认只显示已签，未签折叠进「搜索未签产物」并标注「未签（需人签）」 |
| G15 | `.bak` 只有一格深（连续保存互相覆盖）＋ 刷新页面会触发一次自动保存 | 口径不一致 | P0 | ✅ **已对齐**：正文备份保留 10 代不互相覆盖；前端加脏标记门，只有真编辑才存 |
| G16 | 章节名改不了（核心**已有** heading 块写能力，Miniapp 没暴露） | 核心有·Miniapp 缺 | P1 | ✅ **已实现**：目录行 ✎ → `rename_section` 独立通道（只改 `\section{…}` 花括号里那一段） |
| G17 | 论文标题改不了（核心无 writer，封面只读；表单的 `[project].title` 与封面 `\title{}` 不是同一层） | 核心无·Miniapp 无 | P1 | ✅ **已实现**：核心新写 `set_disk_title`（与封面读侧同源）＋ 封面 ✎（既有 `[project].title` 口径一字未动） |
| G18 | 右栏宽度写死 320px，不能拖 | 口径不一致 | P2 | ✅ **已对齐**：`--nav-w` 变量 ＋ 拖动分隔条（实时变、刷新保留、240–640 钳位） |
| G19 | 保护面命令（`\fact{}`／`\cite{}`）手写写不进去（服务端剥掉） | 口径不一致 | P1 | ✅ **已实现**：「插入事实」面板（数字只来自账本 ＋ 过既有 value 硬闸） |

> **工具面**：Miniapp 的 MCP 工具 **10 → 17**（新增 3 个只读 ＋ 4 个提议单）。
> **本批新增文件**：`factscribe/workbench/readings.py`（两条只读读数）、
> `factscribe/workbench/proposals.py`（账与证据面的提议单）。

---

## 2. A 组：核心有、Miniapp 缺 —— 全部已实现

### G1 ✅ 证据锁读数：宿主问得到「为什么红」

* **做了什么**：
  * 核心新增只读端点 `GET /api/disk/<project>/<disk>/evidence`
    （`factscribe/workbench/server.py`），数据层是新增模块
    `factscribe/workbench/readings.py::evidence_gate`；
  * Miniapp 新增只读工具 `fs_get_evidence_status`（`fs_get_evidence_status`
    转发该端点）。
* **读数口径**：**复用 `factscribe.evidence` 的原件**——`lock_check` /
  `unfrozen_info` / `log_state` / `read_lock`，与 CLI 的
  `factscribe_evidence_status` 同一条路（不另算一遍哈希、不另判一次冻结）。
* **返回形状**：`frozen` / `entries` / `sha256` / `sha256_short` /
  `current_sha256` / `declared_sections` / `declared` / `mismatch` /
  `diff{added,removed,moved}` / `unfrozen` / `log` / `last_log{action,reason,at,count}`。
* **只读**：冻结／解冻是写操作，另走 G2 的提议单通道。

### G2 ✅ 证据冻结／解冻、add_fact：宿主能提，人点才写

* **做了什么**（**沿用提议单机制，没有新开直写通道**）：
  * 新增模块 `factscribe/workbench/proposals.py`，给出四种**非正文**的提议单：
    `evidence_freeze` / `evidence_unfreeze` / `add_fact` / `export_bundle`；
  * Miniapp 新增四个工具：`fs_propose_evidence_freeze` /
    `fs_propose_evidence_unfreeze` / `fs_propose_add_fact` /
    `fs_propose_export_bundle`（`readOnlyHint: false`，与 `fs_propose_edit` 同一套形状）。
* **纪律（与正文提议单完全一致）**：
  * 提议单**只落状态目录**（Miniapp 侧＝宿主分配的 dataDir），**不碰正文、不碰账、
    不碰冻结件**——真实 MCP 驱动验过：提完两张单，论文目录文件清单逐字节不变；
  * 每张单带 `before_sha` **指纹闸**：提议之后状态被别处改过，采纳时拒写
    （`BLOCK_STALE`），不覆盖别人的改动；
  * 差异卡展示的 `after_text` **就是真正会落盘的那一份**（账那条是
    `scaffold.render_fact_block` 算出的原始 TOML 片段）。
* **落盘时仍走既有真闸**：`add_fact` 走 CLI `fact add` 同一条路
  （id 按大小写不敏感判重、查来源文件、查 value 形态、`.derived_from` 必须配
  `.expr`）；冻结／解冻走 `evidence.freeze_evidence` / `unfreeze_evidence`；
  投稿包走 `actions.export_bundle`（**清单门不过就不出包**，单子留在待确认）。
* **⚠️ 提议单形状校验：本批只扩了种类，没有改形状校验**——见 §4。

### G3 ✅ 写作简报：宿主知道「这一节能引哪些数」

* **做了什么**：
  * 核心新增只读端点 `GET /api/disk/<project>/<disk>/brief?section=<前缀>`
    （数据层 `factscribe/workbench/readings.py::brief_reading`）；
  * Miniapp 新增只读工具 `fs_get_brief`。
* **口径复用**：`factscribe.brief`（CLI `factscribe brief` 同一条路）——事实表来自账，
  节清单来自主文件的 `\input` 顺序，术语表来自词表。
* **显式区分「可引用」与「账上有但没绑」**（brief 之上**只增不改**）：
  * 每节：`usable`（可引用）／`bound`（这一节正文里已绑的）／
    `unbound`（可引用但还没绑）／`reconciled`（声明是否都绑上了）；
  * 每条事实：`bound_in`（绑在哪些节）／`status`（bound / unbound）；
  * 汇总：`counts{ledger_total, bound, unbound, sections_total}`；
  * 外加 `constraints`（五条硬约束）与 `terms`（术语表）。

### G9 ✅ 版式配置与投稿包导出

* **做了什么**：
  * Miniapp 新增只读工具 `fs_get_venue`（转发核心既有的
    `GET /api/project/<p>/venue`）：刊物／截稿／还剩几天／语言锁定／模板清单；
  * 投稿包导出走**提议单**通道（`fs_propose_export_bundle`）——不新开直写。

---

## 3. B 组：两侧口径不一致 —— 全部已对齐

### G4 ✅ 两条 MCP 面的 finding 文案语言口径

* **CLI 的 MCP 面**（`factscribe_audit`）：每条 finding 现在都带
  `message_key` ＋ `params`（i18n 原料）；工具新增可选入参 `lang`（zh/en），
  给 `lang=en` 时 `message` 出英文模板。**默认仍是中文原话**。
* **实现位置**：`factscribe/i18n.py` 新增 `issue_dict(issue, lang)`——
  工作台数据层与 CLI 共用同一份渲染，不各写一遍。
* **不动 `Issue.as_dict()`**（金样例锁），形状只增键。

### G5 ✅ CLI 的 JSON 输出出英文

* `factscribe audit --json --lang en`／`factscribe style --json --lang en`：
  * **只影响 JSON 输出**，不改判定、不改退出码；
  * **`--lang` 不给就是现在的样子**——`audit --json` 的四个数组
    （findings/issues/warnings/hints）逐字节不变，金样例**没有重冻**；
  * `style --json` 的 findings **只增键**：`message_key` ＋ `params` ＋ `message`
    （默认中文＝真闸原话，`--lang en` 出英文）。
* 两侧的文案目录是同一份：`factscribe/i18n.py::FINDING_MESSAGES`。

### G6 ✅ 模型档位两侧同源

* **共用声明**：核心新增 `factscribe/workbench/ai.py::model_catalog(disk)`，
  形状＝Miniapp 面板那套：`id` / `kind` / `label` / `model` / `efforts` /
  `defaultEffort`。核心的 `GET /api/ai/models` 现在多给一个 `catalog` 字段
  （旧的 `models` / `model` 字段一字不动）。
* **Miniapp 薄壳直接吃核心那份声明**（`engineModelEntry`）——老引擎没有
  `catalog` 就退回按 `models` 拼（形状一样）。宿主那一路与自定义那一路
  本来就是同一个形状，现在三路真的同形了。
* **核心侧新增 `effort` 参数**（缺省＝当前行为，不改口径）：
  `POST /api/chat` 接受 `effort`，透传到 OpenAI 兼容后端的 `reasoning_effort`；
  Miniapp 选引擎模型时把思考等级一并带过去。

### G7 ✅ AI 对话后端：核实后**两侧本已同源**

* 核心 `POST /api/chat/prepare`（`factscribe/workbench/ai.py::prepare_prompt`）
  与 Miniapp 薄壳的 `AGENT_PREPARE_PATH` 指向**同一个端点**：两边都是
  「只组装提示词、不调模型」。**本批没有改动**，核实后判定无需再动。
* 两侧的差异是**超集关系**（Miniapp 多一条宿主模型的路），不是缺失——按建议保留。

### G8 ✅ 改稿路径：保留 Miniapp 的提议制，并写明

* **实现不动**（Miniapp 更保守、也更对）。本批把这条口径**写进两处**，
  免得宿主以为有工具没暴露：
  * MCP 的 `INSTRUCTIONS`：明写「助手这边没有任何直接改正文、直接改账、
    直接改冻结件的接口」；
  * `fs_propose_edit` 等工具的描述里逐条点明「只建单，不写盘」。

### G10 ✅ 机器视图的分组标题

* 四个分组都加了 `title_key`：`ledger` → `mv.ledger`、`scan` → `mv.scan`、
  `chain` → `mv.evidence`、`export` → `mv.export`（与前端 `t('mv.*')`
  用的 key 一一对应）。后端 `title`（中文原值）**保留**，兼容只读旧的消费者。
* 2026-11-23 补：「导出与命令」组**组内**的四条命令标签与说明原先仍是
  后端硬编码中文（EN 界面残留）——现在带 `label_key`/`note_key`，随机器视图
  载荷发一份 `i18n` 目录子集，前端按界面语言渲染（中文原值留在
  `label`/`note` 上，兼容只读旧消费者）。

---

## 4. 口径边界：本批碰到什么、没碰什么

### 没碰的（已定口径，一字未动）

| 事项 | 本批怎么保证没动 |
|------|------------------|
| 四步链闸门语义（声明→绑定→回账→出证） | `checkreport._chain_steps` 未改；只读了它的读数 |
| 双 Profile 契约（Profile S 严格基线 / Profile A 需显式传 C） | 本批未触及任何判定面 |
| P-152（文风闸「轻度命中不算系统性」三规则） | 只翻译文案，判定未动 |
| `Issue.as_dict()` 的形状 | **未改**（金样例逐字节锁；i18n 字段只加在 `i18n.issue_dict` 这一层） |
| `tests/golden/audit_findings_baseline.json` | **未重冻、未改一个字节**（`audit --json` 默认路径逐字节不变） |
| `fs_propose_edit` 的提议单形状校验（块形状闸） | `_block_shape_guard` 未改一字 |

### ⚠️ 碰到的：提议单**种类**扩了（形状校验没改）

* **要动什么**：`factscribe/workbench/proposal.py` 增了四个 kind
  （`evidence_freeze` / `evidence_unfreeze` / `add_fact` / `export_bundle`），
  `factscribe/workbench/write.py::apply_proposal` 增了这四个分支，
  新模块 `factscribe/workbench/proposals.py` 给它们各配一个「算」的函数。
* **为什么**：G2 的写入口不能新开直写通道（那是已定口径），只能走提议单；
  而提议单系统原本只认正文改稿与草稿块两种。
* **对「形状校验」的影响**：**零**。块形状闸（`_block_shape_guard`：节标题混入／
  一块多标题／重复 `\label{}`）只作用于 `block_edit` 与 `ai_draft`，
  **一字未改**；新四种单不产生正文文本，走的是各自的**指纹闸**
  （清单 digest / 冻结件 sha256）。
* **风险**：
  1. 新四种单的差异卡用的是**人话摘要**（账那条附原始 TOML 片段），
     不是 LaTeX 块——与正文单的渲染形态不同，但卡片组件是同一套；
  2. 页面差异卡的类型标签新增了四个（前端 i18n 已补中英），
     旧标签行为不变；
  3. 若将来有人要求「非正文提议单也走块形状闸」，那才是要动口径——**本批没做**。
* **要不要用户拍板**：**不需要**（旧两种 kind 的行为与校验逐字节不变，
  金样例与全仓测试都绿）。若要收回，删掉 `proposals.py` 与四个 kind 即可，
  不影响既有链路。

---

## 5. 验证读数（本批实测）

| 项 | 读数 |
|----|------|
| 全仓测试 | `pytest tests/ -q` → **2167 passed / 0 failed**（基线 2120，本批 +47） |
| 金样例锁 | `tests/test_golden_lock.py` 通过——**没有重冻基线** |
| MCP 协议（仓内载荷） | `tests/miniapp_mcp_tools.py`：真起 Node 薄壳，17 个工具可调 |
| MCP 协议（**发布态载荷**） | `FS_PLUGIN_ROOT=~/.minimax/plugins/factscribe` 跑同一驱动：\n**17 个工具全部可调**，`fs_get_evidence_status` / `fs_get_brief` / `fs_get_venue` / \n`fs_propose_evidence_freeze` / `fs_propose_add_fact` / `fs_list_proposals` 全部 `ok=true` |
| 提议单零写入 | 驱动前后比对论文目录文件清单（路径＋大小＋mtime）：**完全一致**（`paperUnchanged=true`） |
| 英文读数 | `audit --json --lang en` / `style --json --lang en`：**零中文残留** |
| 载荷契约 | `miniapp/build.sh`：110 文件 / 4.7 MiB（上限 1024 / 64 MiB），契约自检通过，引擎 import ok |
| 本机发布 | `miniapp publish`（包根＝工作树 `miniapp/`）→ 宿主 runtime 重启并 ready |

### 本批新增的测试

| 文件 | 覆盖 |
|------|------|
| `tests/test_workbench_readings.py`（10 例） | 证据锁读数（冻结／解冻／差异／坏项目）与简报读数（usable/bound/unbound 一致性、节过滤、只增不改） |
| `tests/test_workbench_proposals.py`（13 例） | 四种提议单：只建单不写盘、差异卡＝落盘内容、指纹闸拒写、解冻必带理由、追加事实查重、落状态目录 |
| `tests/test_workbench_endpoints.py`（8 例） | 真起工作台 HTTP 服务：`/evidence`、`/brief`、`/venue`、`/ai/models` 的 catalog、提议单建单与采纳 |
| `tests/test_cli_lang.py`（9 例） | `audit --json` 默认形状不变、`--lang en` 零中文、`style --json` 只增键、CLI MCP 面带 i18n 原料、模型档位声明形状 |
| `tests/test_miniapp_mcp_tools.py`（+7 例） | 17 个工具的面与调用、提议单落状态目录、论文目录零改动 |

---

## 6. 剩余建议与各自代价

| 建议 | 代价 | 收益 |
|------|------|------|
| **推送 `feat/miniapp-host-seam` 到 GitHub 远端** | 需用户授权（不推远端、不建 PR 是本批约定） | 收口成果备份与协作 |
| **把「宿主默认」也做成一个显式模型档位**（现在是 `host:default` 特例） | 小：薄壳与前端各一处 | 面板下拉更整齐；但当前行为正确，非必需 |
| **`fs_propose_*` 的差异卡再细分视图**（账条目显示 TOML 高亮） | 中：前端组件 + 样式 | 审账更舒服；当前人话摘要已够用 |
| **给 `fs_get_brief` 加「按 fact id 查在哪节绑了」的过滤** | 小：薄壳一个参数 | 改稿时更快定位；现有 `fs_query_facts` 的 `bound_in` 已能覆盖大半 |
| **把 `evidence_gate` 的读数也并进检查报告**（报告里的 `evidence` 目前只有 frozen/entries/sha） | 小：checkreport 一处 | 报告页不必再调第二个端点；但四步链语义不动的约束下要小心，暂不并 |
| **投稿包导出加「导出前预览清单」** | 中：actions + 前端 | 少一次误点；当前清单门不过就不出包，已兜底 |

---

## 7. 本批之前已收口（不再算缺口）

### 7.1 finding message 全量 i18n

* 目录在 `factscribe/i18n.py`（`FINDING_MESSAGES`，key→{zh, en}）：187 条，
  key 形状 `finding.<CODE>`。
* 真闸的每一处 `Issue(...)` / `Finding(...)` 都带 `message_key` ＋ `params`；
  `message` 旧字段**一字未改**。
* 中文模板与真闸原话**逐字相同**（`tests/test_finding_i18n.py::ChineseFidelityTests`
  在 26 个金样例项目上逐条比对，0 差异）；英文模板**零中文**。

### 7.2 MCP 新增两条只读工具（上一批）

| 工具 | 入参 | 出处 | 说明 |
|------|------|------|------|
| `fs_get_style` | `{project, disk, lang?}` | 引擎 `GET /api/disk/<p>/<d>/style` | 文风闸读数 |
| `fs_mirror_check` | `{project, disk}` | 引擎 `GET /api/disk/<p>/<d>/mirror` | 双语对账读数 |

---

## 8. 2026-11-23 补修：i18n 三处缺口（P2-1 / P2-2 / P2-3）

> 分支 `feat/miniapp-host-seam`；范围**只限 i18n 三处**，其余 P2 不动。
> 实跑复验记录见 `docs/MINIAPP-E2E-ACCEPTANCE-20261122.md` §6。

### 8.1 三处缺口与收口

| # | 缺口 | 收口方式 | 状态 |
|---|------|---------|------|
| P2-1 | 机器视图「导出与命令」组内命令标签/说明是后端硬编码中文 | 命令带 `label_key`、说明带 `note_key`；载荷带 `i18n` 子集；中文原值保留在 `label`/`note` | ✅ 已修（EN 实跑 CJK 命中 0） |
| P2-2 | 提议单差异卡的正文（Current / After adopting）与告警是引擎拼的中文 | 四种新单 + 既有改稿单的正文/告警拆成 `display`（key ＋ params）；前端按 lang 渲染，缺模板回落到中文原话 | ✅ 已修（EN 实跑 CJK 命中 0） |
| P2-3 | 追加事实卡来源显示「Unknown source」 | 事实的 `source` 与提议单的来源（mcp）分键（`fact` 子对象）；MCP 工具入参 schema 未动 | ✅ 已修（卡片显示 `From assistant`） |

### 8.2 口径边界：这一批**没有**改任何已定口径

| 事项 | 怎么保证没动 |
|------|------------------|
| 四步链闸门语义 | `checkreport._chain_steps` 未改 |
| 提议单形状校验（块形状闸） | `_block_shape_guard` 的判定与硬闸未改，只把告警文案拆成 key＋params |
| 双 Profile 契约 / P-152 | 未触及任何判定面 |
| `Issue.as_dict()` 的形状 / 金样例基线 | 未改、未重冻（`audit --json` 默认路径逐字节不变） |
| 既有提议单字段 | `before_text`/`after_text`/`warnings` 逐字不变，只**加** `display` 字段 |
| MCP 工具的入参 schema | `fs_propose_*` 一字未动 |
| P2-4（`.bak` 只有一格深）/ P2-5（账本命名分裂） | 仍记录，未擅改 |

### 8.3 两侧一致性的口径（本批新增的读法）

工作台自己生成的说明文案现在是**两层**：

* **展示层**：`key` ＋ `params`，模板目录（`factscribe/i18n.py::WORKBENCH_MESSAGES`，
  `wb.*`）随载荷发到页面——页面按 `state.lang` 渲染，缺哪条回落到中文原话；
* **契约／落盘层**：`before_text`/`after_text`/`warnings`/`label`/`note`
  一字未动，中文原话由**同一个目录**渲染（所以两层不会漂）。

这与既有 finding 文案的路子同构（`finding.*` 目录随报告发出去，页面按
`message_key` ＋ `params` 渲染），只是目录分开：真闸的话归 `finding.*`，
工作台的话归 `wb.*`。

## 9. 2026-11-23 第三轮：追加事实的界面表单（新增能力，缺口 G11 收口）

### 9.1 补的是什么缺口

上一轮盘点后剩下的最后一处界面缺口是：**追加事实只有 MCP 面的入口，页面
没有**。而且核心侧「写哪本账」是写死的（`facts/01-core.toml`），与本盘真正
在用的主题账本文件（`facts/a_swebench.toml` … `facts/h_conflicts.toml`）
对不上——在 `paper` 盘上落账会凭空多出一本 `01-core.toml`，而不是并进
「主结果／pilot／跨模型／成本／闸／τ2／TerminalBench／冲突」里的哪一本。

这一轮把这两件事一起收口：

| 缺口 | 收口方式 | 口径 |
|---|---|---|
| 页面没有追加事实的入口 | 右栏「更多」→ 事实账 → 追加事实：两步表单 | 只建单，走既有「提议-确认」通道，落盘由人点「采纳写回」 |
| 写哪本账写死 | 核心新增 `resolve_ledger`：目标文件限 facts glob 内的**直接子文件**；新建文件沿用**本盘既有命名风格**、前缀不撞 | 不指定时行为与从前一字不变；风格从盘内现有账本文件推断，不跨盘借 |
| 挑产物没有清单口径 | 新增只读端点 `fact-form`：已签产物（清单那组，附 drift 比对）／未进清单的产物（清单产物**所在目录**下、未进清单的文件） | 扫描范围写在载荷里，界面照实说（`experiments` 下 2 层，8124 个文件） |
| 界面不能碰哈希、不能手打 source | 表单没有哈希框、没有路径框；`source_sha256` 由 `prepare_fact` 现算 | 哈希只读、路径只从候选里选 |

### 9.2 口径边界：这一批**没有**改任何已定口径

| 已定口径 | 怎么保证没动 |
|---|---|
| `scaffold._check_source` 的强制校验 | 一条没放松：source 必填／项目内相对路径／不收 URL／不越出 source_root／文件必须存在（实测：手打不存在的路径照样 400） |
| 四步链闸门语义 | `checkreport._chain_steps` 未改；本轮只**读**它的读数（声明 48→49、绑定 232→233、回账 232→233） |
| 提议单形状校验（块形状闸） | `_block_shape_guard` 未改 |
| 提议单既有字段 | `before_text`／`after_text`／`warnings` 逐字不变；追加事实单只**加**了 `fact.ledger`／`fact.ledger_explicit` |
| 双 Profile 契约 / P-152 | 未触及任何判定面 |
| 金样例基线 | `tests/golden/audit_findings_baseline.json` 未重冻、未改一个字节 |
| MCP 工具入参 | `fs_propose_*` 一字未动；`factscribe_add_fact` 只**加**了可选 `ledger` |

### 9.3 两侧一致性的口径（新增两处，说明清楚）

本轮多出两类文案，各走各的既有机制：

* **界面 chrome**（步骤标题、字段标签、按钮、占位符）＝ app.js 的静态中英
  字典（`ff.*` ＋ `np.*` ＋ `more.factNote`），跟别的表单一致，受既有
  「EN 字典零 CJK ＋ zh/en 键集一致」守卫测试守门；
* **引擎侧文案**（清单未签、产物签后被改、未签清单的扫描范围、账本目标
  被拒的错因）＝ `factscribe/i18n.py::WORKBENCH_MESSAGES` 的 `wb.form.fact.*`
  目录，随 `fact-form` 端点的载荷发到页面，页面按 `state.lang` 渲染，
  缺哪条回落到中文原话。

与上一轮 §8.3 的两层口径同构：真闸的话归 `finding.*`，工作台的话归 `wb.*`，
界面自己的话归 app.js 字典——三处不混。

### 9.4 本批新增的测试

`tests/test_workbench_fact_form.py`（22 条）：

* 账本目标校验 9 条：默认不变、既有账本可用、新文件沿用风格、风格不符被拒
  （`LEDGER_STYLE_MISMATCH`）、前缀占用被拒（`LEDGER_PREFIX_TAKEN`）、
  出 glob 被拒（`LEDGER_OUTSIDE_GLOB`）、子目录被拒
  （`LEDGER_NOT_IN_GLOB_DIR`）、绝对路径与 `..` 被拒（`LEDGER_PATH_INVALID`）、
  `add_fact` 落进所选账本、命名风格从盘内现有文件推断；
* 只读读数 3 条：三组读数齐、引擎侧目录随载荷下发、读数不写盘；
* 真实 HTTP 端点 4 条：端点形状、提议单只建单不写账、采纳落**所选**账本且
  与预览逐字一致、坏账本名回 400 且带 `err_code`、不存在的 source 照样被拒；
* 入口 2 条：CLI `--ledger`、MCP／serve 的 `ledger`；
* 文案 2 条：`wb.form.fact.*` 双语齐、EN 侧零 CJK。

另有 `tests/test_workbench_layout.py` 的一处计数更新（面板节标题 5 → 6：
新增的「事实账」段沿用同一条 `.np-pane-h`，色值闸不变）。

全仓 `pytest tests/ -q`＝**2215 passed / 0 failed**（上一轮 2193，本轮 +22）。

### 9.5 仍然记着、没擅自动的

| 事项 | 为什么没动 |
|---|---|
| P2-4（`.bak` 只有一格深） | 与本轮无关 |
| P2-5（账本命名分裂） | 本轮**正面处理了其中一半**：新增账本文件必须沿用本盘既有风格（`letter_topic`／`index_topic`），但**既有**那 8 本账的命名本身没动（改名会动事实的 source 绑定语义） |
| 「value 必须在产物里」做成硬校验 | 会破坏既有 MCP 驱动测试（value `7/8`）；本轮只写成界面提示 |
| add_fact 提议单加 before_sha 指纹闸 | 追加事实只追加账本，改的是新增片段；加闸会改既有提议单口径，超出本批 |
| 「实验报告 → 事实」自动桥 | 本批不做；`wizardModal` 导入向导写的是草稿块，不是事实账 |
| 双语对账表里的全角分隔符「A ｜ B」 | 既有面的既有写法，本轮没碰（它出现在检查报告模态里，不是追加事实面） |

## 10. 2026-11-23 第四轮：正文编辑「不跟手」（先实测定位，再按实测修）

### 10.1 三个嫌疑的实测裁定

事前列的三个嫌疑都是**假设**，这一轮用真浏览器（Chrome headless ＋ CDP 真键盘事件／
真 IME 组合管线）逐个证实或推翻：

| 嫌疑 | 实测裁定 | 处置 |
|---|---|---|
| IME 未被处理 | **成立**——但表现不是「拼音提前上屏」，而是**组合进行中宿主被改，下一次组合的光标被甩进角标文本节点**（读数：offset 1／ctx 'S'） | 接入 `compositionstart`／`compositionend`；组合期间**不收正文、不换 DOM、不挂角标**，组合结束统一补做（芯片重绑 ＋ 欠下的替换／角标／保存） |
| 保存后整块替换把光标甩回块首 | **基本证伪**——聚焦中的块被既有守卫生效跳过（只记 `data-stale='1'`），同文件连续编辑**不丢字**、无 BLOCK_STALE | 守卫生效，**不动**；只补「替换后按段内偏移恢复光标」这层保险（替换前记偏移、替换后放回） |
| 「已保存」角标插在编辑宿主里顶动光标 | **成立**——角标被 append 进正在编辑的宿主（kids 147→148），正文文本流被顶出角标文字 | 角标改挂 `body` 浮层（`position:absolute` ＋ `pointer-events:none`），不再进编辑宿主；组合期间先记账 |
| 附：累积卡顿 | **证伪**——300 次真按键：DOM 节点 1887→1887、document 监听 9→9、每键延迟全程 0.4–1.3ms 无上升 | 不动 |
| 附：英文打字慢 | **证伪**——keydown→input 均值 **0.72ms**、上屏均值 **6.99ms** | 不动。「不跟手」的根因是**编辑过程中光标/组合被破坏**，不是打字本身慢 |

### 10.2 口径边界：这一批**没有**改任何已定口径

| 口径 | 本批的处理 |
|---|---|
| 「聚焦中的块不替换、只记 stale」 | **不动**（实测它是对的）；只在 `applyBlockHtml` 里加「替换前记光标偏移、替换后放回」 |
| 落盘层（`collectPlain` 的散文＋token、`\fact`／`\cite` 保护面） | **不动**；角标本就被收集时跳过，实测 `.tex` 里没有角标文字 |
| 四步链闸门语义、提议单口径、块形状闸、双 Profile 契约 | **不动** |
| 金样例基线 `tests/golden/audit_findings_baseline.json` | **未重冻、未改一个字节** |
| 界面 chrome 与引擎侧文案分层 | 本批只动界面行为，**没加新文案**（角标文字沿用既有 `edit.savedBadge` 双语键） |

### 10.3 本批新增的测试

`tests/test_workbench_editing_ime.py`：**18 条**＝14 条静态断言（IME 事件序列／
组合期不收正文不换 DOM／光标取还与替换后恢复／状态 UI 不落编辑区）＋ 4 条**真浏览器**
行为（英文逐键延迟与 DOM 变动、组合不被保存响应打断、光标跟住组合文本、整块替换后光标不丢）；
配套 `tests/editing_ime_driver.mjs`（真 Chrome ＋ CDP；缺 node≥22 或 Chrome 时该 4 条 skip，
静态 14 条永远跑）。

全仓 `pytest tests/ -q`＝**2233 passed / 0 failed**（397 subtests；上一轮 2215，本轮 +18）。

### 10.4 记着、没擅自动的

| 事项 | 为什么没动 |
|---|---|
| **打开磁盘会写用户正式盘**（`[workbench].last_opened` ＋ 一个 `.bak` 旁文件） | 引擎 `factscribe/workbench/write.py::touch_opened` 的既有行为（「记住上次开的是哪个盘」）。本轮实测撞到它：宿主重启后自动打开正式盘 → 正式盘 `paper` 的指纹在 **11:12:13** 变了（只差一行时间戳 ＋ 一个 `.bak`；发生在本轮开工前 7 分钟）。**没动**——改它要改 P0-5 的口径；本轮验收一律走 `/tmp` 副本盘，报告里如实记下这条差口，没去改用户盘凑指纹 |
| 组合期间的自动保存策略（组合结束补跑；超过 5s 撤标记但**不当场收**） | 没有用户可配的口径需求；本轮只保证「不把候选中的拼音写进 `.tex`」 |
| 整块替换后光标恢复的**精确度**（按文本偏移回位，芯片文本算进偏移） | 段内偏移口径够用且与落盘口径无关；本轮不引入「按 token 位置回位」的更细口径 |

---

## 11. 2026-11-23 第五轮：四项必做收尾（G12–G15）

> 实跑复验记录见 `docs/MINIAPP-E2E-ACCEPTANCE-20261122.md` §9（宿主内嵌浏览器，发布态插件，副本盘）。

### 11.1 四项收口

| # | 缺口 | 收口方式 | 状态 |
|---|------|---------|------|
| G12 | 追加事实的 value 不校验产物原文（上一轮只写成界面提示，不拦） | 新增 `factscribe/valuecheck.py`（纯计算）：NFKC／LaTeX 百分号／分数命令→`A/B`／去强调标记／千分位归一；**数字项按出现顺序子序列匹配**（数值相等、百分号一致、单位不比），无数字项按归一化子串比；产物非文本 → `VALUE_SOURCE_NOT_TEXT`。`propose_add_fact` **建单前**拒建单，`apply_add_fact` **采纳时**再核一遍 | ✅ 已实现（宿主实测：`42` 拒建单且 Pending 仍 0；`10/16` 建单成功） |
| G13 | 追加事实提议单没有 `before_sha` 指纹闸（其余三类单都有） | `before_sha`＝**目标账本文件**的 sha256（账本本来不存在时记 `before_absent`）；采纳前复核，不符 → `BLOCK_STALE` 拒写；账本被别处建出来同样拒 | ✅ 已对齐（宿主实测：外部追加 `EXT3` 后采纳被拒，`Z90` 未落盘、账本 sha 未变） |
| G14 | 候选列表把 8124 个未签产物与 9 个已签产物平铺 | 未签组改 `<details id="afUnsignedFold">`：**默认折叠且不渲染**；summary＝「搜索未签产物」＋标签「未签（需人签后才能作数）」；已签行 title 同时给清单 sha256 与现算 sha256；一个筛选框同时管两组 | ✅ 已对齐（宿主实测：默认已签 9 行／未签 0 行；展开 120 行；搜 `BATCH12` → 已签空、未签 2 行） |
| G15 | `.bak` 只有一格深（连续保存互相覆盖）＋ 刷新页面会触发一次自动保存 | `write.py`：`atomic_write(..., keep=)` ＋ `backup_paths()`；正文与 main.tex 走 `BACKUP_KEEP=10`（`.bak`＝上一版，`.bak.1/.bak.2…` 轮转不互相覆盖）；配置文件仍 `CONFIG_BACKUP_KEEP=1`。前端：`input` 事件打脏标记，`saveBlockNode` 与 `focusout` 都要求脏标记；另加 `beforeunload` 提醒 | ✅ 已对齐（宿主实测：三次保存留下 6 代互不覆盖的备份；刷新与「只聚焦不编辑」后刷新均**零写入**） |

### 11.2 口径边界：这一轮**没有**改任何已定口径

| 口径 | 本轮的处理 |
|---|---|
| 四步链闸门语义 | `checkreport._chain_steps` 未改 |
| 提议单形状校验（块形状闸） | `_block_shape_guard` 未改 |
| 双 Profile 契约 / P-152 | 未触及任何判定面 |
| `Issue.as_dict()` 的形状 / 金样例基线 | 未改、未重冻（`tests/golden/audit_findings_baseline.json` 一个字节没动） |
| `scaffold._check_source` 的既有校验 | 一条没放松（`resolve_source()`＝把既有逻辑提成公开版；`check_value_in_source()` 是**新增**的一道闸） |
| 落盘层散文＋token 口径、绑定数字保护面 | 未动 |
| 既有提议单字段 | 追加事实单只**加**了 `before_sha`／`before_absent`；`before_text`／`after_text`／`warnings` 一字未改 |
| MCP 工具既有入参 schema | `fs_*` 一字未动（只给 `fs_get_brief` 加了**可选** `fact`） |

### 11.3 记着、没擅自动的（**要用户拍板**）

| 条 | 为什么没动 | 要用户拍板的点 |
|---|---|---|
| 第 8 条：把 `evidence_gate` 的读数（冻结状态／差异／最后一条日志）并进检查报告 | 报告里的「出证」读数来自四步链闸门，并进去会让两个读数源耦合；**四步链闸门语义是已定口径** | 并进去以后，报告的「出证」要不要**显式标注两个来源**（闸门读数 vs `evidence_gate` 读数）？还是合并成一个？ |
| 第 9 条：投稿包导出前加「预览清单」 | 导出流程已有**清单门**（门不过就不出包）；预览＝再加一条人工确认链，属导出流程口径 | 「预览清单」做成导出前的**必经闸**（强制）还是**可选**的一步？强制会改导出流程的既有口径 |

### 11.4 仍留在缺口里的（下一轮候选）

| 事项 | 代价 | 收益／为什么不现在做 |
|---|---|---|
| ~~CLI `fact add` 直写通道也加 value 硬校验~~ | **第六轮已做**（→ §12.1 B） | 直写通道现在与「提议-确认」共用 `check_value_in_source()`，同一句文案 |
| ~~探针尾数字被绑定保护层吃掉（`[HOSTBAK1]` → `[HOSTBAK]`）~~ | **第六轮已查清并修掉**（→ §12.1 A、§12.3） | 根因＝保护面序号整体错位时服务端静默丢保护面＋客户端提前推进块指纹；两层都修了 |
| `.bak` 对配置文件也保留多份 | 小 | 「打开磁盘」每次都写 `factscribe.toml`，多份会在盘上堆垃圾；现状（配置只留一份）更合适 |
| 宿主模型目录里重复 displayName 的去重尾注 | 小 | 上一轮已处理（加 provider 尾注），本轮无新缺口 |

### 11.5 本轮新增的测试

`tests/test_workbench_value_guard.py`（19 条）＋ `tests/test_workbench_save_guard.py`（15 条）＋
`tests/test_workbench_brief_focus.py`（4 条）；既有测试改用**真实样本**（`7/8` → `56.25%`）而非放宽校验。

全仓 `pytest tests/ -q`＝**2271 passed / 0 failed**（397 subtests，266.17s；上一轮 2233，本轮 **+38**）。

## 12. 2026-11-23 第六轮：四项必做（A/B/C/D）

> 实跑复验记录见 `docs/MINIAPP-E2E-ACCEPTANCE-20261122.md` §10（真 Chrome ＋ CDP 副本盘、发布态插件）。

### 12.1 四项收口

| # | 缺口 | 收口方式 | 状态 |
|---|------|---------|------|
| **A** | 「保存会改内容」：正文里的数字与保护面在保存往返中消失或被换掉（§9.11 实测到、当时没查根因） | 两层，各必要：①**客户端**块指纹只在 DOM 真被换成服务端新文时推进（`applyBlockHtml(blockId, html, sha)` 接管；块仍被聚焦且用户又打了字时不推进）；②**服务端**占位符序号在当前扫描里不存在 → **拒写**（`EDIT_TOKEN_MISMATCH`／HTTP 409），不再静默丢保护面；另加「命令类保护面不许丢」的兜底 | ✅ 已收口（真浏览器：修复前第二次保存把 `0/3` 换成 `\fact{E5}`、凭空多出 `0/2`；修复后两次落盘**逐字节相同**，探针数字仍在） |
| **A-2** | 同族另一个入口：正文里与绑定数字令牌**同名**的数字被按**文字**认领，芯片旁边的绑定数字整段消失 | `_absorb_verbatim` **不再按文字认领 `num` 令牌**（派生令牌只认占位符）；命令类保护面的认领口径、token 格式一字未动 | ✅ 已收口（回归测试先红后绿：一次保存就把 `8\fact{A3}` 写成 `\fact{A3}`） |
| **A-3** | 账本变了（新事实的 value 出现在正文里）→ 同一段原文的保护面**数量**变 → 客户端 DOM 的占位符序号整体错位（指纹闸抓不到：块原文一个字没变） | 客户端报「这份 DOM 里有几枚保护面芯片」（`expect_tokens`），服务端与当前扫描对不上就**拒写**（`EDIT_TOKEN_COUNT_MISMATCH`／HTTP 409） | ✅ 已收口（四个盘逐块比对：112 段正文 ＋ 4 段摘要全等；HTTP 实测 409／200；真浏览器两路照旧通过） |
| **B** | CLI `fact add` 直写通道不校验 value（§11.4 留在缺口里的那条） | `scaffold.prepare_fact()` 在 `_check_source` 之后加 `check_value_in_source()`——CLI／MCP／serve／采纳写回**共用同一道闸、同一句文案**（同一个 `factscribe/valuecheck.py`） | ✅ 已收口（副本盘实跑：value `42` 被拒且**账本零改动**；`10/16` 写入） |
| **C** | 证据锁读数只在 MCP `fs_get_evidence_status`，检查报告里看不到（上一轮第 8 条：用户拍板「独立一张卡」） | 报告载荷新增顶层 `evidence_lock`（与 `fs_get_evidence_status` **同源**：`readings.evidence_gate`）；四步链 `_chain_steps` **一字未动**；页面随报告载荷渲染，**不多一次调用**；MCP `fs_get_report` 自行整形载荷 → 输出形状不变 | ✅ 已收口（真界面：徽标 `frozen`／entries 106／指纹 `03bd1dae`；`chain` 与 `evidence` 两个键的载荷 diff 为空） |
| **D** | 投稿包导出前没有「预览清单」（上一轮第 9 条：用户拍板「可选」） | `bundle.run_bundle(preview=True)`：**只算不写**（与真导出共用 `_artifact_bytes`，路径/指纹/大小同一口径）；清单门判定**一字不改**；模态给「继续导出」与「跳过预览，直接导出」两钮 | ✅ 已收口（真界面：36 件逐件列出＋清单门 5 过 0 不过；预览后包目录**不出现**；门不过 → 预览与真导出同一结论、都不出包） |

### 12.2 口径边界：这一轮**没有**改任何已定口径

| 口径 | 本轮的处理 |
|---|---|
| 四步链闸门语义 | `checkreport._chain_steps` 未改；`chain` 与 `evidence` 两个键的载荷逐字不变 |
| 提议单形状校验（块形状闸） | `_block_shape_guard` 未改 |
| 双 Profile 契约 / P-152 | 未触及任何判定面 |
| `Issue.as_dict()` 的形状／金样例基线 | 未改、未重冻（`tests/golden/audit_findings_baseline.json` 一个字节没动） |
| `scaffold._check_source` 的既有校验 | 一条没放松（`check_value_in_source()` 是**新增**的一道闸） |
| 落盘层散文＋token 口径 | 未动——token 格式、占位符口径、保护面「命令级／环境级／数字级」三条口径一字未改；本轮只把「序号对不上」从静默丢弃改成拒写 |
| 绑定数字保护面 | 口径未动（`num` 仍是**派生**令牌：插字可能让它整段消失，那是合法编辑）；新增的「保护面不许丢」兜底**只管命令类**保护面（`\fact{}`／`\cite{}`／公式／环境／注释） |
| MCP 工具既有入参 schema | `fs_*` 一字未动 |
| 导出口径（清单门） | 一字未改；预览只是**可选**的一步，判定权仍在清单门 |

### 12.3 记着、没擅自动的

| 条 | 为什么没动 | 说明 |
|---|---|---|
| stale 场景下「飞行途中新打的字」会丢 | 客户端在块仍被聚焦时不能整块重绘（会吞掉新字）；要保住它得做客户端↔服务端的合并重写（rebase），风险大于收益 | 沿用既有 BLOCK_STALE 语义「未保存的字会丢」；本轮优先保证「**内容不被改**」 |
| 探针尾数字**单独**消失（`[HOSTBAK1]` → `[HOSTBAK]`）这一形态 | 本轮查到并修掉的是**同一机制族**（保护面序号整体错位 → 保存改内容）；真浏览器复现出来的是 `0/3` 被换成 `\fact{E5}`、凭空多出 `0/2` | 「尾数字单独消失」要求探针里那个数字**本身**是一枚绑定令牌（账本里有这个值，或它紧邻 `\fact{}` 且其后只跟空白）；四个盘的账本里**没有裸值 `1`**，所以那一形态在本工作树**未能单独复现**——如实记，不把没复现的说成复现了 |
| 保存会把**段内**换行压成空格、把 `---` 写成 `—` | 这是「页面即编辑器」的既有渲染口径（`projects.py` 与 `app.js::collectPlain` 本轮一字未改，HEAD 就是这样）；要连空白也逐字保留，得改落盘层散文口径 | 如实记：**既有**现象、**非本轮引入**；用户看得见的字（数字／芯片／探针）逐字保留，看不见的空白与连字符按既有口径规范化 |
| 客户端↔服务端合并重写（保住飞行途中的新字） | 属前端保存链路的进一步改造 | 需要单独立项 |

### 12.4 本轮新增的测试

* `tests/test_workbench_save_fidelity.py`：**14 条**（连续两次保存逐字稳定；stale DOM 拒写且文件逐字节不变；序号不存在 → 拒写不静默丢；保护面不许丢；**正文同名数字不许被认成别处的绑定令牌**；**结构闸**：保护面数量对不上 → 拒写、数量对得上 → 放行；前端指纹口径与 `expect_tokens` 口径的静态断言）
* `tests/test_workbench_evidence_lock_card.py`：**7 条**（独立卡；与 `evidence_gate` 同源；冻结读数；清单变了报差异；四步链形状不变；MCP 输出形状不变；页面不多一次调用）
* `tests/test_workbench_bundle_preview.py`：**4 条**（门不过：预览与真导出同一结论、都不出包；门过：预览与包内文件**逐件 sha256 一致**；预览不写盘；两次预览结论一致）
* `tests/save_probe_driver.mjs`：真浏览器驱动（`normal`／`stale` 两种模式；stale 模式拦下 `/edit` 的请求、在飞行途中把光标放回块里再放行）
* 既有测试改用**真实样本**（`value="1"` → `"10/16"`；`value="42"` → `"10"`；doctor 与 method-workflow 的产物补上真实数字）——**没有放宽校验**

### 12.5 §11.4 的更新

§11.4 里那两行现在收口了：

* 「CLI `fact add` 直写通道也加 value 硬校验」→ 已做（本轮 B）。
* 「探针尾数字被绑定保护层吃掉」→ 根因查清并修掉（本轮 A；形态差异见 §12.3）。

## 13. 2026-11-23 第七轮：三个用户诉求（新增能力 G16–G19）

> 本轮开工 HEAD `71e824b`（分支 `feat/miniapp-host-seam`，**未推远端、未建 PR**）。
> 全仓 `pytest tests/ -q`＝**2353 passed / 0 failed**（上一轮基线 2298，本轮 **+55**）。
> miniapp 已 publish 到本机宿主；**源 → 载荷 → 已发布 104/104 文件逐字节一致**（§13.4）。

### 13.1 四处缺口与收口

| # | 缺口（两侧比对后的样子） | 之前的现状 | 现在的样子 | 收口 |
|---|---|---|---|---|
| G16 | **改章节名** | 核心**已有**能力（`write.py::_block_shape_guard` 专为 heading 块写，`save_block` 支持标题块），但 Miniapp **没暴露**：目录行只有 ↑↓🗑，正文 `<h2 class="sec-h">` 非 contenteditable | 目录每行一支 ✎ → 弹窗 → 新写 `rename_section()` 独立通道（只改 `\section{…}` 花括号里那一段） | ✅ 已实现 |
| G17 | **改论文标题** | 核心**没有** writer（CLI 全子命令无此命令）；封面 `#coverTitle` 只读；Miniapp「编辑项目」表单里的「论文标题」写的是 `[project].title`——与封面显示的 `\title{}` **不是同一层**（既有口径错位） | 核心新写 `set_disk_title()`（盘自己入口 .tex 的 `\title{主 \\ 副}`，与封面读侧**共用同一处定位** `title_command_span`）＋ 封面旁的 ✎ | ✅ 已实现（既有 `[project].title` 口径**一字未动**） |
| G18 | **右栏宽度** | 写死：`.navpanel{width:320px}` ＋ `shell{padding-right:336px}`；右栏是 Miniapp 自渲染的（宿主框架无「职能助手」字样，`app.asar`／`~/.minimax` 全搜 0 命中），宿主侧**没有**可配入口 | 宽度走 CSS 变量 `--nav-w` ＋ 拖动分隔条：拖动实时变、**松手**才记进 `localStorage['factscribe.navw']`、刷新后仍在、240–640 钳位（正文至少留 420）、双击回默认 | ✅ 已对齐 |
| G19 | **保护面命令手写费劲** | 客户端散文里新写的 `\fact{…}`／`\cite{…}` 会被服务端 `_strip_injected` **剥掉**（并告警）→ 手打标签今天写不进去 | 段落 ⋯ 菜单「插入事实」→ 列**账上**事实 → 选一条 → 标记插进正文那个数字后面；数字**只能来自账本 value**，且服务端**再过一遍既有 value 硬闸**（`scaffold.check_value_in_source`） | ✅ 已实现（**不做**纯前端命令补全——补出来的标记会被剥掉，是假功能） |

### 13.2 口径边界：这一轮**没有**改任何已定口径

| 口径 | 本轮的处理 |
|---|---|
| 四步链闸门语义 | `checkreport._chain_steps` 未改 |
| 提议单形状校验（块形状闸） | `_block_shape_guard` 未改（改名走**新通道**，不借道 `/edit`） |
| 双 Profile 契约 / P-152 | 未触及任何判定面 |
| `Issue.as_dict()` 的形状／金样例基线 | 未改、未重冻（`tests/golden/audit_findings_baseline.json` 一个字节没动） |
| `scaffold._check_source` 的既有校验 | 一条没放松（插入事实走的是**新增**的 `check_value_in_source` 这道闸，与「追加事实」同一道） |
| 落盘层散文＋token 口径、`\fact`／`\cite` 保护面 | 未动——三条新通道各自独立（只动那一处），绕开 `/edit` 而不是改它 |
| `[project].title`（项目表单「论文标题」） | **一字未改**；本轮只补「改封面那一条」的入口，两者是不同的层 |
| MCP 工具既有入参 schema | `fs_*` 一字未动（本轮没有新增 MCP 工具） |

### 13.3 两侧一致性的口径（本轮新增两处，说明清楚）

| 口径 | 怎么定的 |
|---|---|
| 标题：**读的是哪一条，写的就是哪一条** | 封面读的是该盘入口 .tex 的 `\title{…}`；写侧用**同一个**定位函数（`projects.title_command_span`，读侧 `_tex_title_parts` 已改为复用它）——不会出现「改了另一个 `\title{}`」或「改到别的盘」的错位 |
| 插入事实的数字：**唯一来源是事实账** | 面板列的是 `readings.facts_list()`（复用机器视图的账本表，同一份事实同一套字段）；数字取账本 value 原文；服务端再过一次 value 硬闸；正文里已有这个数 → 只补标记（mode=`marker`），没有 → 连数字带标记插段末（mode=`value`） |

### 13.4 发布态三方一致（源 → 载荷 → 已发布）

| 项 | 读数 |
|---|---|
| 载荷同步 | `miniapp/build.sh`：文件数 111（上限 1024）／4.9 MiB／契约自检通过／engine import ok／104 个载荷文件 |
| 前端三件 | `app.js`（`3098c8a2…`）／`app.css`（`4068f1f5…`）／`index.html`（`71f8d65d…`）：源＝载荷＝已发布 |
| 引擎 | `factscribe/**` 98 个文件：源 vs 载荷 0 差异；载荷 vs 已发布 0 差异 |
| 载荷整棵 vs 已发布整棵 | 104 / 104 文件，0 差异 |

### 13.5 本轮新增的测试

* `tests/test_workbench_title_fact_binding.py`：**20 条**（改名只动标题命令／指纹闸拒写／标题与读侧同源／插入事实三道铁律／`render_tex` 块偏移回归锁／真起服务的端点用例）
* `tests/test_miniapp_ui_features.py`：**35 条**＝30 条静态断言（三个入口的结构、指纹闸、双语文案齐不齐）＋ 5 条**真浏览器**行为（Chrome headless ＋ CDP 真鼠标/真键盘）
* `tests/miniapp_ui_driver.mjs`：真浏览器驱动
* 改 `tests/test_workbench_layout.py`：条目 40 案二的静态闸原钉着硬编码 `padding-right:336px`%；宽度改由 `--nav-w` 驱动后，闸改为钉「`padding-right:calc(var(--nav-w,320px) + 16px)`」＋「`:root{--nav-w:320px}`」（让位宽度仍与侧栏同源，只是不再写死）——**本轮唯一被改的既有测试断言**

### 13.6 记着、没擅自动的（要用户拍板）

| 条 | 为什么没动 | 要用户拍板的点 |
|---|---|---|
| **空行分段从未生效**（既有缺陷，本轮只记录） | `projects.py:789` 的 `if char == "\n" and source[index:index + 2] == "\n":` 拿 2 字符字面量比 1 字符的 `char`，恒假 → 一个章节文件＝**一个**可编辑段（实测：`01-intro.tex` 两段散文被并成一段） | 要不要按空行分段？分段会改变块结构与编辑粒度，保存/指纹/审计的粒度也得跟着变——属独立产品决策 |
| `[project].title` 与封面 `\title{}` 的口径错位（既有） | 既有表单继续写 `[project].title`，本轮只补封面那一条的写侧；两者不是同一层 | 要不要把项目表单的「论文标题」也指向 `\title{}`？还是保持两层各写各的？ |
| 纯前端「`\fact{…}` 命令补全」 | 补出来的标记会被服务端剥掉＝假功能；要真做就得动落盘层那条已定口径 | 要做「手写命令」这条路吗？要做的话得开一条与散文写回并列的通道 |
| 保存把段内换行压成空格、`---` 写成 `—`（上一轮记着，用户已拍板待定） | 属「落盘层散文＋token 口径」，本轮不动 | 待用户拍板 |

---
