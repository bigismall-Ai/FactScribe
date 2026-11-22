# 论文侧 Miniapp ↔ 核心论文工作台：能力对齐缺口清单

> 日期：2026-11-22　分支：`feat/miniapp-host-seam`　基准：aad2e3e ＋ **本批（A/B 两组全收口）**
>
> **本批状态：A 组 4 项全部实现，B 组 6 项全部对齐（其中 G7 核实后本已对齐）。**
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
| G10 | 机器视图的分组标题是后端中文 | 口径不一致 | P2 | ✅ **已对齐**（四个分组加 `title_key`） |

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
