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
| G10 | 机器视图的分组标题是后端中文 | 口径不一致 | P2 | ✅ **已对齐**（四个分组加 `title_key`；2026-11-23 补：组内的命令标签/说明也走 `label_key`/`note_key`，见 §8） |

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