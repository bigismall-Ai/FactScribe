# 法律侧只读接口层：JSON 契约（factscribe-legal-api/1.0）

> 本件是**规范**（接口契约）。实现记录在 `integrations/factscribe-legal/`，
> 实现在 `factscribe_legal/api.py` 等件。

## 0. 这是什么 / 不是什么

**是**：法律侧工作台（原型见 Bunny 事项「FactScribe 法律侧工作台原型」）的第 ① 步——
**只读接口层**：一个版本化 JSON 契约（JSON 出口）＋ 一组只读 HTTP 路由。
它把法律侧引擎已有的真实读数（七条闸的判定、逐条收据、语料件、判定码表、
域级锁）按**跨域同构**的形状吐出来，供工作台页面直接消费。

**不是**：

* 不是判定层。接口层**不下任何判定**：红黄码、措辞、退出码语义全部照抄各闸，
  一字不改（各闸判定语义见本包 README「码表（冻结）」节）。
* 不是写路径。本步**零落盘**：不写项目、不写语料、不建任何落盘动作。
  「待批提案」通道属于第 ② 步（UI 与提议存储），本步只读返回**空数组**。
* 不是第 ② 步。第 ② 步（FR 判例样板页）直接复用本件的通道即可。

## 1. 契约版本与信封

顶层形状（`factscribe-legal api contract` 的输出）：

```json
{
  "version": "factscribe-legal-api/1.0",
  "schema": "factscribe-legal-api/1.0",
  "generated_by": "factscribe-legal api",
  "read_only": true,
  "project": "/abs/path/to/project",
  "reference_date": "2026-11-14",
  "findings":    { "...": "见 §2" },
  "receipts":    { "...": "见 §3" },
  "corpus":      { "...": "见 §4" },
  "codes":       { "...": "见 §5" },
  "timeliness":  { "...": "见 §6" },
  "summary":     { "...": "见 §7" },
  "proposals":   { "...": "见 §8" }
}
```

* `version` ＝ 契约版本（**改形状就改版本号**；加字段是次版本，向后兼容）。
* `read_only` 恒为 `true`（机器可据此拒绝写操作）。
* `reference_date` ＝ 参考日（各域时效判据的基准；空串＝未定，时效判据全跳过）。
* 七个通道**至少**都有；单通道出口（`api findings` 等）只带那一路。

HTTP 路由把整份契约嵌在 payload 的 `contract` 键下
（payload 自己的 `version`/`exit`/`severity` 等键不与之冲突）。

## 2. findings 通道：七条线各自的判定结果

```json
{
  "total": 1, "red": 1, "yellow": 0,
  "lines": [
    {
      "line": "fr-case", "label": "法国判例", "country": "法国",
      "kind": "判例", "gate": "verify-fr-case",
      "status": "ran", "note": "",
      "red": 1, "yellow": 0,
      "items": [
        {
          "code": "FR_CASE_VALUE_NOT_IN_OFFICIAL",
          "severity": "red",
          "location": "facts/50-fr-case.toml:F-JURITEXT000007100000",
          "message": "事实 F-JURITEXT000007100000 的数值 999999（法式归一后）在官方正文里找不到"
        }
      ]
    }
  ]
}
```

字段逐条：

| 字段 | 含义 |
|---|---|
| `lines[].line` | 线 id：`fr`/`cn`/`case`/`it`/`es`/`fr-case`/`it-case` |
| `lines[].label`/`country`/`kind` | 线的展示名／国家／件型 |
| `lines[].gate` | 对应的既有闸（CLI 子命令名），便于反查判定口径 |
| `lines[].status` | `ran`（跑了）／`skipped`（材料没拿到）／`na`（不适用） |
| `lines[].note` | skipped 的原因（人话，如「意大利语料没拿到（it/ 目录不在）」） |
| `lines[].red`/`yellow` | 该线红／黄码条数 |
| `items[].code` | **真实判定码名**（一字不改） |
| `items[].severity` | `red` 或 `yellow`（**源码判出来的**，不是接口层另判） |
| `items[].location` | 位置（照抄各闸的 `facts/xx.toml:ID` 形态） |
| `items[].message` | **现有措辞**（照抄，不改写、不翻译、不加前缀） |
| `items[].detail` | 可选；各闸给了才出现（目前多数为空） |

纪律：材料缺失**不是错误**——标 `skipped` 并写清原因，不发空壳 finding。

## 3. receipts 通道：统一五元组

一行＝一条事实，字段固定五元组（顺序固定）：

```json
{
  "line": "fr-case", "label": "法国判例", "country": "法国",
  "kind": "判例", "gate": "verify-fr-case",
  "status": "ran", "total": 2,
  "items": [
    {"id": "F-JURITEXT000006953017", "sha16": "cc55b21afeb852da",
     "span": "1707-1711", "face": "body", "how": "numnorm"},
    {"id": "F-JURITEXT000007100000", "sha16": "64360f87695a1a0a",
     "span": "—", "face": "—", "how": "numnorm"}
  ]
}
```

| 字段 | 含义 | 取不到时 |
|---|---|---|
| `id` | 事实 id | `"—"` |
| `sha16` | 事实账钉的来源哈希**前 16 位**（剥掉 `sha256:` 前缀） | `"—"` |
| `span` | 值在官方正文**原文坐标**的首次命中区间 `"起-止"` | `"—"` |
| `face` | 命中面：`body`（官方正文）／`résumé`（官方摘要段） | `"—"` |
| `how` | 核验方式：`contains`（逐字）／`numnorm`（数字·日期归一）／`catalog`（目录树·详情元数据对账） | `"—"` |

**缺省标记统一是 `"—"`**（沿用法国判例线的既有写法，不新造标记形状）。
通道顶层另给 `fields`（五元组字段名）与 `missing_marker`（缺省标记），
页面不用硬编码。

### 3.1 共用生产逻辑（这套是七条线**同一套**，不是各线各造）

实现位置：`integrations/factscribe-legal/factscribe_legal/receipts.py`
（纯函数、只读、零 LLM、零网络、不写盘）：

| 函数 | 职责 |
|---|---|
| `sha16_of(source_sha256)` | 钉版哈希 → 前 16 位（没钉 → 缺省标记） |
| `span_in_text(value, text)` | 原文坐标命中区间（**空白容忍**：token 用 `\\s+` 连接，NBSP／窄空格／换行不影响定位） |
| `classify_how(value)` | 值型 → 核验方式（数字/日期 → `numnorm`，其余 → `contains`） |
| `build_receipt(id, sha, span, face, how)` | 造一行，字段固定五元组，取不到的一律缺省标记 |
| `norm_space` / `contains_norm` | 空白归一（NBSP/窄空格→空格、连续空白→单空格）与归一后命中 |

span 算法出自法国判例线既有的收据实现（`_span_in_text`，收编进正仓那支），
本步把它**抬成七条线共用的一套**，并由法国判例线改调它。

### 3.2 七条线的适配点（材料在哪／面怎么定／怎么核验）

适配实现：`factscribe_legal/lines.py`。

| 线 | 官方材料 | span 取自 | face | how |
|---|---|---|---|---|
| `fr` 法国法条 | 条文 XML（`BLOC_TEXTUEL`） | 条文正文 | body / — | 法式数字词也算 `numnorm`，否则 `contains` |
| `cn` 中国法规 | 详情 JSON（**无正文**） | —（无正文） | —（缺省） | `catalog` |
| `case` 中国案例 | 官方案例正文 `runs/<run>/official/<slug>.txt` | 正文 | body / — | contains / numnorm |
| `it` 意大利法条 | AKN 条文切片 XML | 切片正文 | body / — | `contains` |
| `es` 西班牙法条 | BOE 条文块切片 XML | 切片正文 | body / — | `contains` |
| `fr-case` 法国判例 | 判决 XML ＋ 纯文本还原件 | txt 全文 | body / résumé | contains / numnorm |
| `it-case` 意大利判例 | 判决档案切片 XML | 切片正文 | body / — | contains / numnorm |

* 「没有官方全文命中面」的行（CN）→ `face` 取**缺省标记**，不是新造的形状。
* 数值在原文里的写法与账上不同（`300.000` vs `300000`）时：`how` 如实写
  `numnorm`，而 `span` 记**字面**命中区间（定不到就是缺省标记）——不假装定位到了。

## 4. corpus 通道：语料件清单

```json
{
  "total": 27,
  "roots": ["<项目语料视图>", "<本仓打包语料 integrations/factscribe-legal/corpus>"],
  "filters": {"country": "法国"},
  "items": [
    {
      "id": "L594-8", "country": "法国", "domain": "fr", "kind": "法条",
      "title": "Code de l'environnement",
      "path": "corpus/fr/L594-8.xml", "gate": "verify",
      "meta": {"etat": "VIGUEUR", "date_debut": "2012-01-07",
               "date_fin": "2999-01-01", "legiarti": "LEGIARTI000025110353",
               "code_id": "LEGITEXT000006074220", "xml_file": "L594-8.xml",
               "pool_asof": "2026-11-15"},
      "timeliness": { "...": "见 §6" },
      "root": "<本仓打包语料 integrations/factscribe-legal/corpus>"
    }
  ]
}
```

* 「件」＝一份官方件（一条法条／一个判决／一部法规／一个条文切片）。
* **只列真实可见的件**：扫描不到的件不出现在清单里（不占位、不编造）。
  仓内可见件分布：FR 法条 3／FR 判例 4／CN 法规 2／IT 切片 4／ES 切片 9／
  IT 判例 2（CN 案例 0 件——案例材料在项目 `runs/` 里，不在语料视图）。
* 同名不同 run 是**不同的件**（去重键含 `path`）。
* 过滤：`country`／`domain`／`line`／`state`（时效状态）／`kind`。

## 5. codes 通道：判定码表

```json
{
  "total": 70, "red": 62, "yellow": 8, "table_total": 70,
  "items": [
    {"code": "LEGAL_PROV_UNKNOWN", "severity": "red", "label": "法条不在语料里",
     "domain": "fr", "gate": "verify"}
  ]
}
```

| 字段 | 含义 |
|---|---|
| `code` | 真实码名（域前缀制，只增不改） |
| `severity` | `red`／`yellow`（与本包 README 冻结码表一致） |
| `label` | 中文短名（**展示名**，不是判定语义） |
| `domain` | 域 id |
| `gate` | 闸（CLI 子命令名） |

机读副本在 `factscribe_legal/code_table.py`；**与本包 README 的冻结码表逐条互锁**
（`tests/test_api.py` 里有一条对表测试：码名集合、严重度逐条一致，
一个不多一个不少）。

> **本基线的码表是 70 个（红 62／黄 8）**。另有三条码
> （`FR_CASE_VALUE_NOT_QUOTE`／`FR_CASE_STITCH_UNMARKED`／
> `FR_CASE_QUOTE_FACE_UNDECLARED`）只存在于**未合并**的分支
> `feat/fr-case-contract`（提交 577c280），不在本基线（`origin/main` = f31a6c76）。
> 本步不引入它们：加判定码＝改判定语义（硬约束），且会让「既有 11 条子命令的
> 输出与退出码不变」不成立。分支合进 main 后，本通道与 README 对表测试会同时
> 红，届时按「码只增不改」的既有做法把三码补进 README 与本表即可，
> 接口层零改动。

## 6. timeliness 通道：跨域统一时效字段

各域判定器**内部不动**（仍按各自现状判定：FR 区间／CN 状态标志／
IT、ES 时点戳／判例日期）。本通道只在**接口层**把四种来源归一成**同一形状**：

```json
{
  "domain": "fr", "kind": "法条", "item_id": "L594-8",
  "reference_date": "2026-11-14",
  "state": "in_force", "state_label": "参考日当天生效",
  "effective_from": "2012-01-07", "effective_to": "2999-01-01",
  "source": "区间", "source_fields": ["date_debut", "date_fin"],
  "note": "法国法条：版本区间完整（date_debut / date_fin），是七条线里唯一能回答「参考日当天是否生效」的结构。"
}
```

### 6.1 统一形状（11 个键，域间逐条同形）

| 字段 | 含义 |
|---|---|
| `domain` | 域 id |
| `kind` | 件型（法条／法规／判例／案例） |
| `item_id` | 件 id |
| `reference_date` | 参考日 |
| `state` | 时效状态（闭集，见 6.2） |
| `state_label` | 状态中文名 |
| `effective_from` | 生效起（ISO；无则空串） |
| `effective_to` | 生效止（ISO；无则空串） |
| `source` | 来源形态（区间／状态标志／时点戳／日期／无） |
| `source_fields` | 来源字段名（逐条写清，便于反查） |
| `note` | 一句话口径说明（参考日未定时会补一句「参考日未定（时效判据不跑）」；参考日定了就不留这句） |

### 6.2 四域来源映射表

| 域 | 来源形态 | `source_fields` | 判定规则 | 状态取值 |
|---|---|---|---|---|
| `fr` 法国法条 | 区间 | `date_debut`/`date_fin` | `date_debut <= 参考日 < date_fin` ＝当天生效（`etat` 不参与） | `in_force`／`scheduled`／`repealed`／`unknown` |
| `cn` 中国法规 | 状态标志 | `sxx` | 1废止／2修改／3有效／4未生效 | `in_force`／`amended`／`repealed`／`not_yet_effective`／`unknown` |
| `it`/`es` 法条 | 时点戳 | `version_date` | 版本戳 ＝ 参考日 → 当天生效；否则参考日版本没拿到 | `in_force`／`version_gap`／`unknown` |
| `fr-case`/`it-case` 判例 | 日期 | `date_dec`／`data_decisione` | 历史件：只有裁判日期，无版本时效语义 | `historical`／`unknown` |
| `case` 中国案例 | 无 | （空） | 官方件不含时效材料 | `not_applicable` |

状态闭集（`state`）：`in_force`、`scheduled`、`repealed`、`amended`、
`not_yet_effective`、`version_gap`、`historical`、`unknown`、`not_applicable`。

## 7. summary 通道：各域状态 ＋ 域级锁

```json
{
  "domain": "legal", "red": 0, "yellow": 0, "hints": 0,
  "corpus": "results/corpus-legal", "date": "2026-11-14", "view": "",
  "lines": [
    {"line": "fr", "label": "法国法条", "status": "ran", "note": "",
     "red": 0, "yellow": 0}
  ],
  "lock": {
    "path": "audit/evidence-legal.lock",
    "keys": ["corpus", "date", "index_sha256", "view"],
    "corpus": "results/corpus-legal",
    "date": "2026-11-14",
    "view": "",
    "index_sha256": "ef3acaf73720ca8e71e13dd79910970631260e73d9da75d7460513e3348a968f",
    "current_canonical_sha256": "bad76552d16f8b60c50a3ec2d5804846607c796282a7c0188da01efc74803574",
    "frozen": false,
    "frozen_canonical_sha256": "",
    "frozen_keys": {"corpus": "", "date": "", "index_sha256": "", "view": ""},
    "last_action": "",
    "matches": null
  }
}
```

* `lock` 是**域级**锁（`audit/evidence-legal.lock`），与论文侧的
  `audit/evidence.lock` 互不干扰。
* 四键闭集：`corpus`／`date`／`index_sha256`／`view`——canonical 形态与
  `checks_adapter` 同一套实现（本步把它从「唯一 import 上游的适配器」里
  搬到纯标准库的 `factscribe_legal/lock.py`，适配器改为 import 本件再导出，
  行为逐字节不变）。
* `matches`：`true` 锁在且现算一致；`false` 不一致；`null` 没冻过。
* 本通道**只读**：不写锁、不写流水账。

## 8. proposals 通道：待批提案

```json
{
  "total": 0,
  "items": [],
  "note": "待批提案通道属第 ② 步（UI 与提议存储）：本步只读，恒返回空数组，不建任何写路径。"
}
```

本步**只读**：恒为空数组，**不建写路径**（没有 POST、没有落盘、没有提议存储）。
通道位置留给第 ② 步。

## 9. CLI 出口

```bash
# 只读接口层：JSON 出口（默认就是 JSON）
python3 -m factscribe_legal api contract --project <项目目录>
python3 -m factscribe_legal api findings --project <项目目录>
python3 -m factscribe_legal api receipts --project <项目目录>
python3 -m factscribe_legal api corpus   --project <项目目录> --country 法国
python3 -m factscribe_legal api codes    --project <项目目录>
python3 -m factscribe_legal api timeliness --project <项目目录> --domain it
python3 -m factscribe_legal api summary  --project <项目目录>
python3 -m factscribe_legal api proposals --project <项目目录>

# 人读摘要（与 JSON 同源）
python3 -m factscribe_legal api summary --project <项目目录> --human
```

* `--project` 默认当前目录；`--corpus`/`--date`/`--view` 缺省取项目
  `factscribe.toml` 的 `[checks.legal]`（显式参数优先）。
* `--json` 与默认同义（本族默认就出 JSON）；`--human` 出人读摘要。
* 退出码：`0` 接口可用（本层**不下判定**，红黄码不据此改退出码）；
  `2` 配置错（如项目目录不存在）。材料缺失不报错——按 `skipped` 如实标出。
* **既有 11 条子命令的输出与退出码一字未动**（本族是第 12 条子命令，
  且不打「单域调试入口」提示——它的 stdout 必须是纯 JSON）。

## 10. HTTP 路由（core `factscribe serve`）

legal 专属前缀，与论文侧路由不冲突；**全部只读**：

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/api/legal/findings` | 契约的 findings 通道 |
| GET | `/api/legal/receipts` | 契约的 receipts 通道 |
| GET | `/api/legal/corpus` | 契约的 corpus 通道 |
| GET | `/api/legal/codes` | 契约的 codes 通道 |
| GET | `/api/legal/timeliness` | 契约的 timeliness 通道 |
| GET | `/api/legal/summary` | 契约的 summary 通道（含域级锁四键） |
| GET | `/api/legal/proposals` | 契约的 proposals 通道（本步恒空） |
| GET | `/api/legal/contract` | 整份契约（七路） |

* 查询参数：`line`/`country`/`domain`/`state`/`kind`/`severity`（过滤）。
* 认证：与既有 `/api/*` 一致（Bearer token 或 `X-FactScribe-Token`）。
* 未知通道 → 404（不留空壳假接口）；集成件没装/装不上 → 501 并说清原因。
* 契约嵌在 payload 的 `contract` 键下（payload 自己的 `version`/`exit` 不被覆盖）。

## 11. 只读纪律

* 零写盘：不写项目、不写语料、不写锁、不写流水账。
* 零 LLM、零网络、零系统钟。
* 不改判定语义：码名、措辞、严重度、退出码语义全照抄各闸。
* 不动金样例基线（`tests/golden/audit_findings_baseline.json`）——
  本层不进 `audit` 路径，27 盘 `audit --json` 逐盘逐字节不变。

## 12. 第 ② 步（FR 判例样板页）可直接复用的东西

* 契约七路通道（直接消费，不用再解析 CLI 文本）。
* 收据五元组（页面右栏「逐条收据」直接渲染 `id｜sha16｜span｜face｜how`）。
* 语料件清单与时效字段（左栏「依据」的件与时效状态）。
* 域级锁四键（页面顶栏的锁状态面）。
* `proposals` 通道的位置（第 ② 步把「恒空数组」换成提议存储即可，形状不变）。

## 13. 本步未做的事（如实列明）

* **不实现写路径**：无「待批提案」的存储与采纳回写（第 ② 步）。
* **不实现逐件浏览**：corpus 通道给的是件清单与元数据，不给单件的全文正文
  （全文回灌要按域分别取，见 §3.2 的材料列）。
* **不实现反查**（从数值反查是哪件官方材料）。
* **不引入 P-166 三码**（见 §5 的说明与理由）。
* 线索层 `cn-lead-*`（第三方检索）**不属本接口层**：它是联网的第三方聚合库，
  不是官方件，不进本契约。
