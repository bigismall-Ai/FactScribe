# 论文侧 Miniapp ↔ 核心论文工作台：能力对齐缺口清单

> 日期：2026-11-22　分支：`feat/miniapp-host-seam`　基准：6655ad0 ＋ 本批（finding i18n、
> `fs_get_style`、`fs_mirror_check`）
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
> 1. **宿主问不到**：核心有、Miniapp 的 MCP 面上没有（宿主 Agent 只能问 `fs_*`）；
> 2. **口径不一致**：两侧都有，但读数形状／文案语言／行为不同。
>
> **本批已收口的两项不重复列**（见 §5）。本清单只列**还没收口**的。
>
> 优先级口径：**P0**＝宿主在 Miniapp 里会做错事或拿不到关键读数；**P1**＝能力缺口
>（宿主问不到某件事）；**P2**＝口径不一致（两侧都有，只是形状/语言/时机不同）。

---

## 1. 结论摘要

| # | 事项 | 类别 | 优先级 | 一句话 |
|---|------|------|--------|--------|
| G1 | 证据锁读数（冻结状态／差异／最后一条日志）宿主问不到 | 核心有·Miniapp 缺 | P1 | 报告里只有 frozen/entries/sha 三个数，问不到「为什么红」 |
| G2 | 证据冻结／解冻、add_fact 宿主做不了 | 核心有·Miniapp 缺 | P1 | Miniapp 只有「提议改稿」，账与证据面没有写入口 |
| G3 | 写作简报（brief）宿主问不到 | 核心有·Miniapp 缺 | P1 | `factscribe_brief` 有，Miniapp 没有对应工具 |
| G4 | 两条 MCP 面的 finding 文案语言口径不同 | 口径不一致 | P2 | CLI 侧永远中文，Miniapp 侧可按 lang 出 |
| G5 | CLI 的 JSON 输出仍只有中文文案 | 口径不一致 | P2 | `audit --json` / `style --json` 不出英文 |
| G6 | 模型选择与思考等级两侧不同源 | 口径不一致 | P2 | 核心只有 `[ai].models`，Miniapp 多宿主模型与 BYOK |
| G7 | AI 对话后端两侧不同 | 口径不一致 | P2 | 核心＝OpenAI 兼容后端，Miniapp＝宿主 Agent 回合 |
| G8 | 改稿路径两侧不同（直接写 vs 提议单） | 口径不一致 | P2 | Miniapp 更保守，建议保留 |
| G9 | 版式配置（venue）与投稿包导出宿主做不了 | 核心有·Miniapp 缺 | P2 | 页面里有，宿主 Agent 里没有 |
| G10 | 机器视图的分组标题是后端中文 | 口径不一致 | P2 | 界面已用前端 I18N 覆盖，但 MCP 侧读数仍是中文 |

---

## 2. 核心有、Miniapp 缺

### G1（P1）证据锁读数：宿主问不到「为什么红」

* **现象**：检查报告的 `evidence` 只有 `frozen` / `entries` / `sha256` 三个数
  （`factscribe/workbench/checkreport.py` 的 `report_payload`）。证据面真出问题时
  （冻结后被改过、处在解冻状态），宿主只知道一个 sha，看不到差异是哪几节、
  解冻理由是什么、最后一条日志是什么。核心侧有 `factscribe_evidence_status`
  （`factscribe/mcp.py:97`）专答这个。
* **证据**：`factscribe/mcp.py:97` `factscribe_evidence_status`；
  `factscribe/evidence.py` 的 `lock_check()` / `unfrozen_info()` 已经把差异算好了
  （added/removed/moved、hash_before、reason）。
* **影响**：宿主看到 `EVIDENCE_SET_CHANGED` 这条发现时，只能把发现文案复述一遍，
  没法给出「哪几节动了」的具体建议。
* **建议做法**：
  * 新增只读工具 `fs_evidence_status`（`{project, disk}` 入参），转发引擎新端点
    `GET /api/disk/<project>/<disk>/evidence`；
  * 返回形状对齐 `factscribe_evidence_status`：`frozen` / `entries` / `sha256` /
    `mismatch` / `unfrozen` / `diff{added,removed,moved}` / `last_log{action,reason,at}`；
  * **只读**：冻结/解冻是写操作，另开工具并另设授权（见 G2）。
  * 读数口径直接复用 `evidence.lock_check()`，不要另算一遍（与四步链同一原则：
    真闸算一次，界面与 MCP 都只做读数）。

### G2（P1）证据冻结／解冻、add_fact：宿主做不了

* **现象**：核心的 CLI MCP 给了三个写工具——`factscribe_evidence_freeze`、
  `factscribe_evidence_unfreeze`、`factscribe_add_fact`（`factscribe/mcp.py:38/47/60`），
  它们都要求 `--allow-write`。Miniapp 的 MCP 面只有 `fs_propose_edit`（提议单，
  由人在页面点「采纳写回」）。于是：宿主**改得了正文**（走提议单），却**动不了账与证据**。
* **证据**：`factscribe/mcp.py:22` `_WRITE_TOOLS`；`miniapp/miniapp/node/server.mjs:1015`
  `fs_propose_edit` 的注解是 `readOnlyHint: false`（唯一非只读工具）。
* **影响**：写稿闭环在 Miniapp 侧断在「账」上——加了新证据、改了 fact 的 value，
  只能请人回页面操作。
* **建议做法**：
  * **先做只读、再谈写**：把 `add_fact`／`evidence_freeze`／`evidence_unfreeze` 的
    **读**的部分（账本当前状态、可冻结性、冻结影响预览）用 G1 的 `fs_evidence_status`
    一次答完；
  * 写操作**沿用提议单机制**：`fs_propose_evidence_freeze` / `fs_propose_add_fact`
    落宿主私有目录，页面出差异卡，人点确认才写盘——与 `fs_propose_edit` 同一套
    「提议-确认」形状，不新开一条直写通道；
  * 授权边界写进工具注解（`readOnlyHint:false` ＋ 描述里点明「落提议单，不写正文」），
    与 `fs_propose_edit` 保持一致。

### G3（P1）写作简报（brief）：宿主问不到

* **现象**：核心有 `factscribe_brief`（`factscribe/mcp.py:103`）：给出某一节的
  章节清单、**可用的 fact 与数字**、术语表——这是「这一节该写什么」的机器读数。
  Miniapp 的 `fs_*` 面上没有；宿主只能 `fs_get_outline` 看标题、`fs_query_facts`
  捞全账，两者拼起来才知道「这节能引哪些数」。
* **证据**：`factscribe/mcp.py:103`；`factscribe/workbench_dataplayer.py` 的
  `brief_data()`；Miniapp 工具清单 `miniapp/miniapp/node/server.mjs:878-1040`。
* **影响**：宿主写稿时最需要的就是「这一节能用哪些已核验的数字」，现在要多走两步
  再自己拼，拼错的风险（把没绑定的数当可用）由宿主承担。
* **建议做法**：
  * 新增只读工具 `fs_get_brief`（`{project, disk, section?}`），转发
    `GET /api/disk/<project>/<disk>/brief`（复用 `brief_data`）；
  * 返回要**显式区分**「可引用」与「账上有但没绑」——这正是 brief 存在的理由，
    别让宿主自己判断；
  * 顺带把「这一节现有正文里哪些数已回账」一起给出（brief 已有相关读数，
    别新造口径）。

### G9（P2）版式配置与投稿包导出：宿主做不了

* **现象**：核心有 `GET/POST /api/project/<p>/venue`（版式配置：刊物/截稿/语言锁定）
  与 `POST /api/disk/<p>/<d>/action`（pdf / bundle / open_dir）
  （`factscribe/workbench/server.py:18,37,38`）。页面里都能用，宿主 Agent 里没有。
* **影响**：宿主知道刊物要求（页数上限、语言锁定）才能配合改稿；
  投稿包导出是「写完到投稿」的最后一步。
* **建议做法**：
  * `fs_get_venue`（只读）先做——刊物与截稿是**只读事实**，宿主需要它来约束建议；
  * bundle/pdf 是写盘动作，走 G2 的「提议单」通道（落提议单 → 人确认），
    不要给宿主直写。

---

## 3. 两侧口径不一致

### G4（P2）两条 MCP 面的 finding 文案语言口径不同

* **现象**：
  * CLI 的 MCP 面（`factscribe/mcp.py` 的 `factscribe_audit` → `audit_data`）
    返回的 `message` 永远是中文原话，且**不带** `message_key`/`params`；
  * Miniapp 的 MCP 面（`fs_get_report`）现在能按 `lang` 出中/英，并带
    `message_key` ＋ `params` ＋ 目录子集。
* **证据**：`factscribe/workbench_dataplayer.py:100` `audit_data` 用 `i.as_dict()`；
  `factscribe/audit.py` 的 `Issue.as_dict()` **刻意没加** i18n 字段——因为
  `tests/golden/audit_findings_baseline.json` 把 `audit --json` 的 findings
  **逐字节锁死**（`tests/test_golden_lock.py`），加键就要重冻基线（须用户批准）。
  本批把 i18n 字段只加在**工作台/Miniapp 这一层**（`checkreport._finding_dict`），
  CLI 的 JSON 形状一字未动（见 `tests/test_finding_i18n.py`）。
* **建议做法**：
  * **不动** `Issue.as_dict()`（金样例锁）；
  * 在 `audit_data`（CLI MCP 面）这一层**只增键**地补 `message_key` ＋ `params`——
    它不走金样例（`audit --json` 走的是另一条路），可以安全加；
  * 文档里写明两条面的差异：CLI＝中文原话（兼容既有消费者），
    Miniapp＝按 lang 渲染 ＋ 结构化原料。

### G5（P2）CLI 的 JSON 输出仍只有中文文案

* **现象**：`factscribe audit --json`、`factscribe style --json` 的 findings 只有
  中文 `message`；本批的英文模板只在工作台/Miniapp 这一层用上。
* **证据**：`factscribe/audit.py` `Issue.as_dict()`；`factscribe/style.py`
  `StyleResult.as_dict()`。
* **建议做法**：给这两个 CLI 加 `--lang en`（**只影响 JSON 输出**，不改判定、
  不改退出码、不改金样例的默认形状——`lang` 不给就是现在这样）；
  渲染走 `factscribe/i18n.py` 的目录，与工作台共用一份文案。
  注意：`style --json` 的 findings 形状要跟着加 `message_key`/`params`，
  属于「只增键」。

### G6（P2）模型选择与思考等级两侧不同源

* **现象**：
  * 核心：`GET /api/ai/models` 给的是 `workbench.toml` 的 `[ai].models`
    （`factscribe/workbench/server.py:793`），**没有**思考等级概念；
  * Miniapp：模型分三路——`host:`（宿主模型目录，自带思考等级档位）、
    `engine:`（引擎本地后端）、`custom:`（用户自加的 OpenAI 兼容端点，凭据只存
    插件私有目录），见 `miniapp/miniapp/node/server.mjs:48-55`。
* **影响**：宿主 Agent 在 Miniapp 里能挑「带思考等级的宿主模型」，在核心工作台里
  不能——两边「同一个模型」不是同一个概念，换机器就断。
* **建议做法**：把「模型档位」抽成核心侧的一份声明（模型 id / 来源 / 支持的思考等级 /
  默认值），Miniapp 的三路与核心的 `[ai].models` 都从它派生；
  核心侧新增 `effort` 参数（缺省＝当前行为，不改口径）。

### G7（P2）AI 对话后端两侧不同

* **现象**：核心 `/api/chat` 走 OpenAI 兼容后端（不可达即降级）；
  Miniapp 走**宿主 Agent 回合**（`agentAccess: ["session.run"]`），
  另有 `/api/chat/prepare` 只组装提示词不调模型。
* **影响**：这是 Miniapp 的**超集**（能多一条宿主模型的路），不是缺失；
  但两侧的「建议采纳」链路不同：核心把建议写回正文，Miniapp 走提议单。
* **建议做法**：保留 Miniapp 的宿主回合；把 `/api/chat/prepare` 的「只组装提示词、
  不调模型」这一条提升成**两边共用的契约**（宿主 Agent 侧最需要这个形状：
  自己决定用哪个模型跑），核心侧补一个等价端点即可。

### G8（P2）改稿路径两侧不同（直接写 vs 提议单）

* **现象**：核心 CLI MCP 的 `factscribe_write_section` 直接写盘（带 `expect_sha`
  保存闸，`factscribe/mcp.py:23`）；Miniapp 只有 `fs_propose_edit`（落提议单，
  人在页面点「采纳写回」才落盘）。
* **判断**：**这是 Miniapp 更保守、也更对**，不建议对齐成直写。
* **建议做法**：不改实现；在 MCP 的 `INSTRUCTIONS` 与本清单里写明「Miniapp 侧没有
  任何直改正文的接口」，避免宿主以为有工具没暴露。

### G10（P2）机器视图的分组标题是后端中文

* **现象**：`machine_payload` 的分组标题是中文常量（`"账本表"`、`"正文扫描"`、
  `"文献与证据链"`、`"导出与命令"`，`factscribe/workbench/checkreport.py` 的
  `machine_payload`）。界面层已经用自己的 I18N 覆盖了这些标题
  （前端用 `t('mv.*')`，不渲染后端的 `title`），所以**界面没有中文残留**；
  但 MCP 侧读到的 `groups.ledger.title` 等仍是中文。
* **建议做法**：给分组加 `title_key`（`mv.ledger` / `mv.scan` / `mv.chain` /
  `mv.export`），与四步链的 `label_key` 同一套做法；后端 `title` 保留（兼容旧消费者）。

---

## 4. 明确不改的（口径已定，本批只记不动）

| 事项 | 为什么不动 |
|------|------------|
| 四步链闸门语义（声明→绑定→回账→出证） | 已定口径；本批只给 findings 加 i18n 读数，没碰判定 |
| 提议单形状校验（提议-确认、人点才写盘） | 已定口径；G2 的建议沿用同一形状，不新开直写通道 |
| 双 Profile 契约（Profile S 严格基线 / Profile A 需显式传 C） | 本批未触及任何判定面 |
| `Issue.as_dict()` 的形状 | `tests/golden/audit_findings_baseline.json` 逐字节锁；改它要重冻基线，须用户批准 |
| 文风闸「轻度命中不算系统性」的 P-152 三规则 | 本批只翻译文案，不动判定 |

---

## 5. 本批已收口（不再算缺口）

### 5.1 finding message 全量 i18n

* 目录在 `factscribe/i18n.py`（`FINDING_MESSAGES`，key→{zh, en}）：187 条，
  key 形状 `finding.<CODE>`（同一 code 多种文案形态时 `finding.<CODE>.vN`，
  手写形态用语义后缀如 `.display` / `.command` / `.number` / `.left` / `.right`）。
* 真闸的每一处 `Issue(...)` / `Finding(...)` 都带 `message_key` ＋ `params`；
  `message` 旧字段**一字未改**（CLI/JSON 输出与金样例不受影响）。
* 中文模板与真闸原话**逐字相同**（`tests/test_finding_i18n.py::ChineseFidelityTests`
  在 26 个金样例项目上逐条比对，0 差异）。
* 英文模板**零中文**（同文件 `CatalogTests::test_english_templates_have_no_chinese`）。
* 工作台报告层按 `lang` 渲染（`checkreport.report_payload(..., lang=...)`），
  并把目录子集随报告带给前端；前端按 `message_key` ＋ `params` 自己翻
  （`factscribe/workbench/static/app.js` 的 `findingMsg()`），
  所以只切界面语言（没有对应语言盘）时文案也跟着切。
* 文风闸的 findings 走同一套（`style.Finding` 也带 `message_key`/`params`，
  `checks.py` 包装成 Issue 时原样带上）。

### 5.2 MCP 新增两条只读工具

| 工具 | 入参 | 出处 | 说明 |
|------|------|------|------|
| `fs_get_style` | `{project, disk, lang?}` | `miniapp/miniapp/node/server.mjs:942`；引擎 `GET /api/disk/<p>/<d>/style` | 文风闸读数：status / red / yellow / count / rules / summary / metrics / findings |
| `fs_mirror_check` | `{project, disk}` | `miniapp/miniapp/node/server.mjs:962`；引擎 `GET /api/disk/<p>/<d>/mirror` | 双语对账读数：status / count / disk_a / disk_b / summary / drift[]（code / kind / target / id / field / 两侧取值）|

两条都带 `readOnlyHint: true` 等只读注解（复用 `READ_ANNOTATIONS`），
入参风格与既有 `fs_*` 一致（`{project, disk}` 必填，`additionalProperties: false`），
超长截断带 `truncated` ＋ `note`（复用 `TRUNCATE_NOTE`）。
引擎侧只读端点在 `factscribe/workbench/server.py`，数据层是
`factscribe/workbench/checkreport.py` 的 `style_gate()` / `mirror_gate()`——
与报告里的 `gates.style` / `gates.mirror` **同一条路**，不另算一遍。

---

## 6. 收口顺序建议

1. **G3 `fs_get_brief`**（P1，纯只读，最便宜，宿主写稿立刻受益）；
2. **G1 `fs_evidence_status`**（P1，只读；把 G2 的写操作前置读数做出来）；
3. **G2 证据/账的提议单工具**（P1，沿用提议单形状，不新开直写）；
4. **G4/G5 两条面的文案口径统一**（P2：CLI MCP 面补 `message_key`/`params`；
   CLI 加 `--lang`，都不改默认形状）；
5. **G6/G7 模型与对话后端抽公共契约**（P2，跨两个仓的接口活，建议单独一批）；
6. **G9/G10**（P2，量小，可搭车）。
