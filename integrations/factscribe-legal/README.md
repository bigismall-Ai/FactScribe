# factscribe-legal —— 给 factscribe 接上「法律」这一维（核验包）

> 这是**第三方集成件**，不是 factscribe 核心的一部分。
> 它不进 `factscribe/` 包，不改上游任何行为、退出码或违规码；
> 沿用 `integrations/minifactscribe/` 的先例。
> **M2 起它是核验槽的第二个核验包**（`[checks]` 点名 `legal`，见下
> 「核验包注册形态」）；五条子命令保留作调试／单域入口，正式报告走
> `factscribe audit` 单命令双域。

## 它补的是哪一维

factscribe 判的是：**正文里的数字，能不能回到一份签过字、算过哈希的原始材料**。

它不判「这份材料是不是法条」「这条法条今天还有效」「这个数字是不是真的出自这条法条」。
这三条正是法律写作里最容易翻车的地方：

| 问题 | 怎么判 | 码 |
|---|---|---|
| 引用的法条是不是真的存在？ | 红 | `LEGAL_PROV_UNKNOWN` |
| 引的是不是**旧版本**（法条已被修改）？ | 红 | `LEGAL_PROV_NOT_IN_FORCE` |
| 引的是不是**还没生效**的未来版本？ | 黄 | `LEGAL_PROV_SCHEDULED` |
| 引的是不是已废止版本？ | 黄 | `LEGAL_PROV_REPEALED` |
| 官方材料有没有被人动过？ | 红 | `LEGAL_PROV_HASH_MISMATCH` |
| 派生证据卡有没有被人动过？ | 红 | `LEGAL_CARD_SHA256_MISMATCH` / `LEGAL_CARD_NO_HASH` |
| 事实里的数字**真的出自这条法条**吗？ | 红 | `LEGAL_QUOTE_MISMATCH` |
| 语料版本和现行视图是不是同一个？ | 黄 | `LEGAL_PROV_VIEW_MISMATCH` |
| 同一编号能不能定到唯一一条？ | 黄 | `LEGAL_PROV_AMBIGUOUS` |
| 参考日当天的官方件没拿到？ | 黄 | `LEGAL_COVERAGE_GAP` |

后两条是关键：**法国法条被修改后老版本不会消失**，按条文编号引用会静默拿到旧文本；
而法国法条常把数字写成词（`trente-cinq heures`），不解析法文数字词就核不出出处。

### 法文数字也要算数

本集成把法文数字词解析成整数再比对（`trente-cinq → 35`、`quatre-vingt-dix → 90`、
`soixante-douze → 72`），所以「引用 35 小时」能自动对上原文。

## 七个闸，七个法域

| 子命令 | 法域 | 官方件是什么 | 能判到哪一层 |
|---|---|---|---|
| `verify` | 法国（Code du travail） | LEGI 官方条文 XML | 数字真出自官方正文（含法文数字词） |
| `verify-cn` | 中国（国家法律法规数据库） | 官方详情 JSON 派生卡 | 法规现行有效、条文号存在、官方件未变 |
| `verify-case` | 中国（人民法院案例库入库案例） | 官方案例正文 + 回执链 | 案号/日期/金额与官方件一致 |
| `verify-it` | 意大利（Normattiva） | 官方 AKN XML + 条文切片 | 数值真出自官方 AKN 正文 |
| `verify-es` | 西班牙（BOE 官方公报） | 官方合并文本 XML + 条文切片 | 数值真出自官方 BOE 合并文本正文 |
| `verify-fr-case` | 法国（判例：Cour de cassation 等） | DILA INCA 官方判决 XML + 纯文本还原件 | 数值/日期真出自官方判决正文、案号与官方元数据一致 |

各闸的错误码（**红 = 必须修，黄 = 不是绿**）：

| 闸 | 红 | 黄 |
|---|---|---|
| `verify` | `LEGAL_PROV_UNKNOWN` `LEGAL_PROV_NOT_IN_FORCE` `LEGAL_PROV_HASH_MISMATCH` `LEGAL_CARD_SHA256_MISMATCH` `LEGAL_CARD_NO_HASH` `LEGAL_QUOTE_MISMATCH` | `LEGAL_PROV_SCHEDULED` `LEGAL_PROV_REPEALED` `LEGAL_PROV_VIEW_MISMATCH` `LEGAL_PROV_AMBIGUOUS` `LEGAL_COVERAGE_GAP` |
| `verify-cn` | `CN_PROV_UNKNOWN` `CN_PROV_NOT_IN_FORCE` `CN_ARTICLE_NOT_FOUND` `CN_CARD_MISSING` `CN_CARD_NO_HASH` `CN_CARD_SHA256_MISMATCH` `CN_OFFICIAL_HASH_MISMATCH` `CN_VALUE_MISMATCH` | — |
| `verify-case` | `CASE_OFFICIAL_MISSING` `CASE_CARD_MISSING` `CASE_OFFICIAL_HASH_MISMATCH` `CASE_NO_MISMATCH` `CASE_DATE_MISMATCH` `CASE_AMOUNT_MISMATCH` `CASE_VALUE_NOT_IN_OFFICIAL` `CASE_CARD_TEXT_DIVERGED` `CASE_CHAIN_BROKEN` | — |
| `verify-it` | `IT_PROV_UNKNOWN` `IT_CARD_MISSING` `IT_CARD_NO_HASH` `IT_CARD_SHA256_MISMATCH` `IT_SOURCE_HASH_MISMATCH` `IT_ARTICLE_HASH_MISMATCH` `IT_ARTICLE_NOT_IN_SOURCE` `IT_CARD_FIELD_MISMATCH` `IT_QUOTE_MISMATCH` | `IT_VERSION_GAP` |
| `verify-es` | `ES_PROV_UNKNOWN` `ES_CARD_MISSING` `ES_CARD_NO_HASH` `ES_CARD_SHA256_MISMATCH` `ES_SOURCE_HASH_MISMATCH` `ES_ARTICLE_HASH_MISMATCH` `ES_ARTICLE_NOT_IN_SOURCE` `ES_CARD_FIELD_MISMATCH` `ES_QUOTE_MISMATCH` | `ES_VERSION_GAP` |
| `verify-fr-case` | `FR_CASE_CARD_MISSING` `FR_CASE_OFFICIAL_MISSING` `FR_CASE_CARD_NO_HASH` `FR_CASE_OFFICIAL_HASH_MISMATCH` `FR_CASE_CARD_SHA256_MISMATCH` `FR_CASE_VALUE_NOT_IN_OFFICIAL` `FR_CASE_NO_MISMATCH` `FR_CASE_DATE_MISMATCH` `FR_CASE_CARD_TEXT_DIVERGED` | — |
| `verify-it-case` | `ITCASE_CARD_MISSING` `ITCASE_PROV_UNKNOWN` `ITCASE_CARD_NO_HASH` `ITCASE_SLICE_HASH_MISMATCH` `ITCASE_CARD_SHA256_MISMATCH` `ITCASE_CARD_FIELD_MISMATCH` `ITCASE_CARD_TEXT_DIVERGED` `ITCASE_VALUE_NOT_IN_OFFICIAL` `ITCASE_NO_MISMATCH` `ITCASE_DATE_MISMATCH` | — |

**M2 新增三码**（挂槽后材料依赖与冻结锁的 fail-closed 语义；码表只增不改）：

| 码 | 严重度 | 判什么 |
|---|---|---|
| `LEGAL_DATE_INVALID` | 红 | `[checks.legal]` 的 `date` 缺失或不是 YYYY-MM-DD——参考日是时效判据的根基，缺它不许跑也不许只给建议 |
| `LEGAL_EVIDENCE_CHANGED` | 红 | `audit/evidence-legal.lock` 在，而语料索引／参考日／现行视图路径与冻结时不符（要换先解冻再重冻）；锁件坏了也是此码（不许静默当成没冻结） |
| `LEGAL_EVIDENCE_UNFROZEN` | 黄 | 冻结处在「已解冻、未重冻」状态（`audit/evidence-legal-log.ndjson` 最后一条是 unfreeze），或流水账不可读 |

**各闸的判据边界（很重要，不要越界引用）**：

- 中国侧官方件**不含条文正文** ⇒ `verify-cn` 能核「法规现行有效」「条文号存在」「官方件未变」，
  **不能**核「数字出自正文」。这不是缺陷，是官方发布形态决定的。
- 案例库存的是**要旨体例案例稿**，不是判决书原文 ⇒ `verify-case` 核的是「这份案例稿与官方件一致」。
- `verify-it` 判的是「数值出自官方 AKN 条文」；`IT_VERSION_GAP` 只说明**参考日**的版本没拿到，
  是黄不是红。
- `verify-es` 判的是「数值出自官方 BOE 合并文本条文」；`ES_VERSION_GAP` 只说明**参考日**
  的版本没拿到，是黄不是红（口径与 `IT_VERSION_GAP` 相同）。
- **ES 桶已升独立分节**（2026-11-16 批）：槽内 gates 行五桶并列
  `fr｜cn｜case｜it｜es`，ES 事项（`.es.card.txt` 卡与 `\cite{art-es-…}` 引用）
  归 es 桶计数，有事项而 `<corpus>/es/index.json` 没拿到 ⇒ 黄 `LEGAL_COVERAGE_GAP`
  fail-closed。此前「ES 卡被 `PROV_RE` 兜底误并进 fr 桶」的边界申明就此修掉
  （回归钉常驻 `tests/test_checks_legal.py` 的 `TestESBucket`）。
- **法国判例闸（`verify-fr-case`）尚未接进核验槽**（照 ES 批先例：只做
  `factscribe_legal` 层，不越界动 [checks] 槽）。法国法条闸本身已跳过
  `.fr-case.card.txt`（不加这行，`PROV_RE` 兜底会把判例卡当成法条卡报
  `LEGAL_PROV_UNKNOWN` **假红**）。本批也**不加** `\cite{…}` 前缀（判例闸不处理
  cite，照抄 CN 案例闸的最小面）。

另有三条 `cn-lead-*` 子命令属**线索层**（不是闸，不进核验槽）——见下文专节。

## 中国判例线索层（第三方：文书查）：`cn-lead-*`（非闸，不进核验槽）

五条 `verify-*` 子命令核的都是**官方件**（官方发布渠道取来的字节，钉哈希）。
线索层是另一回事：**文书查**（wenshucha.com，MCP 服务）是第三方聚合库
（服务自报 1.6 亿条记录、案号字段覆盖 97.8%、约 91% 记录正文非空），它**不是**
人民法院案例库，也不是裁判文书网。所以它的输出只能当「线索与初步核对」，
**禁止写成官方证明**——每条命令输出的**首行**固定是这句话：

```
线索层（第三方：文书查）——非官方核验，溯源凭案号＋法院＋日期三元组上裁判文书网核对
```

| | `verify-case`（官方维度） | `cn-lead-*`（线索层） |
|---|---|---|
| 回答的问题 | 官方入库案例正文被动没动（哈希链） | 找案子＋案号存在性（第三方库检索） |
| 材料来源 | 官方件＋回执链（钉哈希） | 第三方聚合库（无哈希可钉） |
| 结论效力 | 红/黄/绿机械判定 | 线索与初步核对，**不是官方证明** |
| 进核验槽？ | 是（`[checks]` 点名 legal） | 否——独立 CLI，`[checks]` 永不点名线索层 |

```bash
# 找案子：精确词检索（BM25 非语义；一发一页 ≤5 条，页顶 3，翻页＝换 --page 重跑）
python3 -m factscribe_legal cn-lead-search --q "机动车交通事故责任纠纷" [--page 2]

# 案号存在性核验（exists=退出码 0；查无/判不出=1）
python3 -m factscribe_legal cn-lead-verify --case-no "（2022）苏0322执保100号"

# 取单件库内元信息/正文（--meta 只取元信息省正文配额；--max-chars 分段读）
python3 -m factscribe_legal cn-lead-get --case-no "（2022）苏0322执保100号"
```

退出码：**0**＝服务有答（verify 仅当判定「库内存在」）；**1**＝verify 查无／判不出
（线索口径：库内没有，不代表案件不存在）；**2**＝配置错／网络错／参数错
（fail-closed：超时、连不上、信封坏都明确报错退出——拿不到线索不许编；
服务侧参数错误不计数）。三次输出都透出服务自报的 `_quota` 余额行与
`_coverage` 数据口径全文。

### 数据口径三条（如实转抄服务自报）

1. **无原文链接**：线索层不提供官方原文链接——溯源凭「案号＋法院＋裁判日期」
   三元组上中国裁判文书网（或人民法院案例库）自行核对官方件；
2. **记录数≠案件数**：服务自报「160,291,678 条记录（不是案件数）」——同一案号
   多条记录常见（保全/执行系列），且约 2.2% 记录无案号字段，别拿记录数当规模、
   别拿命中条数当案件数；
3. **查不到≠不存在**：检索基于标题与库内正文（约 91% 非空），调解结案等文书
   本就不公开正文。0 命中只说明这个第三方库没检索到，不说明案件不存在。

### 配额与专属 Key

- 缺省走**公共测试 Key**（`wsc_demo_public`，共享评估额度，**禁批量**）：
  客户端内置串行＋随机间隔 ≥2 秒，每条命令恰好一次服务调用；
- 生产用请申请**专属 Key**（输出里 `_coverage.more_quota` 指引，
  wenshucha.com/pricing），注入方式二选一，**不要**写进代码或命令行参数
  （命令行参数会留在 shell 历史里）：
  - `factscribe.toml` 可选节（照 `[budget]`/`[evidence]` 可选节先例，缺了不报错）：

    ```toml
    [cn_lead]
    endpoint = "https://mcp.wenshucha.com/mcp"   # 缺省即此，可不填
    key      = "你的专属 Key"
    ```

    该节对三条 `cn-lead-*` 生效（`--config` 显式给路径，不给则看当前目录的
    `factscribe.toml`）；
  - 环境变量 `FACTSCRIBE_CN_LEAD_ENDPOINT` / `FACTSCRIBE_CN_LEAD_KEY`
    （优先级：环境变量 > toml 节 > 缺省）。

### 实现备注

- 纯标准库 urllib 直调 JSON-RPC（免 MCP SDK——quickstart 已证 curl 直调合法）；
  不 import 上游 `factscribe`，可单独拷走单跑。
- `verify_case_number` 的参数名照服务实测是 **`caseNo`**（不是 caseNumber），
  发错名会白扣评估额度——客户端已按实测形状写死并有测试锁。
- `get_judgment` 的 `include_body=false` 形状已实测入库；`include_body=true`
  的正文键名未实测（省正文配额），解析按 `body`/`content`/`text` 等多键防御
  适配——首次真实取正文后建议回来校准一次（照实适配，不猜）。
- 离线夹具是 2026-11-17 真端点响应录制后脱敏（人名/公司名 → 某某）；
  真端点冒烟是一次性人工验收，不进测试套。

## 两层证据

```
runs/run-YYYYMMDD-legal/
  official/<num>.xml      权威层：官方条文 XML 原字节 —— 法条本体
  <num>.card.txt          派生层：证据卡（元数据 + 法文数字归一 + 官方正文）
  index.json              语料索引（官方标识、哈希、版本日期）
```

事实账指向**卡片**（上游的字面回查需要数字以阿拉伯数字出现），
卡里声明 `OFFICIAL_XML_SHA256`，法律闸**现算官方字节的哈希**再复核。

⇒ 上游钉住卡片没被改；法律闸钉住官方字节没被改。**两层都不丢**，
而且两层的篡改会落在不同闸上（实测：官方 XML 被改，上游是绿的）。

证据卡的字段名一律大写、稳定、可机读：

- 法国：`NUM` `LEGIARTI` `ETAT` `DATE_DEBUT` `DATE_FIN` `REFERENCE_DATE`
  `OFFICIAL_XML` `OFFICIAL_XML_BYTES` `TEXT_CHARS` `NUMERIC_NORMALIZATION`
- 意大利：`ACT_URN` `ACT_ELI` `ACT_TITLE` `DATA_GU` `CODICE_REDAZIONALE`
  `ARTICLE_EID` `ARTICLE_NUM` `VERSION_DATE` `FETCH_VIGENZA` `REFERENCE_DATE`
  `SOURCE_FILE` `OFFICIAL_XML_SHA256` `ARTICLE_SHA256` `TEXT_SHA256` `LICENCE` `ATTRIBUTION`
- 西班牙：`ACT_ID` `ACT_ELI` `ACT_TITLE` `ACT_NUMBER` `BLOCK_ID` `ARTICLE_NUM`
  `ARTICLE_TITLE` `VERSION_DATE` `FETCH_DATE` `REFERENCE_DATE` `SOURCE_FILE`
  `SOURCE_URL` `OFFICIAL_XML_SHA256` `ARTICLE_SHA256` `TEXT_CHARS` `TEXT_STATUS`
  `LICENCE` `ATTRIBUTION` `FETCHED_AT`
- 法国判例：`CASE_ID` `TITRE` `DATE_DEC` `JUDGE_DATE` `JURIDICTION` `CASE_NO`
  `NUMEROS_AFFAIRES` `FORMATION` `NATURE` `SOLUTION` `OFFICIAL_XML`
  `OFFICIAL_TXT` `OFFICIAL_XML_BYTES` `OFFICIAL_XML_SHA256` `OFFICIAL_TXT_BYTES`
  `OFFICIAL_TXT_SHA256` `TEXT_CHARS` `SOURCE_URL` `SOURCE_PATH` `FETCHED_AT`
  `LICENCE` `ATTRIBUTION`

**归属靠文件名后缀判定**（`.it.card.txt` / `.es.card.txt` / `.cn.card.txt` / `.case.card.txt` /
`.fr-case.card.txt` / 法国侧的 `.card.txt`），
不靠卡内有没有某个标记字段 —— 靠标记猜会让「卡被删 / 卡被篡改」被静默跳过，变成假绿。

## 核验包注册形态（M2）：`audit [checks]` 单命令双域

factscribe 核心有一个**核验槽**（`factscribe/checks.py`，SPEC-CHECKS §3）：
每个领域交一张「核验包卡」（domain_id、冻结码表、config 键集、材料依赖声明、
纯函数 `verify`），`factscribe audit` 按项目 `factscribe.toml` 的 `[checks]`
节点名一次跑多个域、一份报告（按域分节，legal 节在后）、一套退出码
（任一域红＝1，仅黄＝3，与既有折算完全同口径）。

本件的卡在 `factscribe_legal/checks_adapter.py`：`domain_id = "legal"`、
`config_keys = {corpus, date, view}`。项目里这样点名：

```toml
[checks]
packages = ["paper", "legal"]     # 缺省（无 [checks] 节）＝只跑 paper，行为不变

[checks.legal]
corpus = "results/corpus-legal"   # 语料视图目录（FR 读 index.json＋官方 XML；
                                  # CN 看 <corpus>/catalog.jsonl.gz；IT 看 <corpus>/it/；
                                  # ES 看 <corpus>/es/——一目录一法，照 IT 同款约定）
date   = "2026-11-14"             # 参考日（不读系统钟）
view   = "out/…/merged_current.jsonl"   # 可选：现行视图，交叉验证生效状态
```

**注册机制**：core 不 import 本件。`[checks]` 点名 `legal` 而槽内未注册时，
core 按约定路径发现 `integrations/*/check-package.toml`（本目录下这枚指针
声明 `domain = "legal"`、`adapter = "factscribe_legal.checks_adapter"`），
载入适配器，适配器调 `register_package` 挂卡——载入方向是本件 import 宿主，
`integrations/` 整目录删掉＝legal 回到未注册（点名即 exit 2），先例不破。
判据模块与五子命令依旧零上游依赖、可单独拷走单跑。

**材料依赖 fail-closed 表**（空集不许伪装成全绿）：

| 情形 | 行为 |
|---|---|
| `corpus` 未声明／目录不存在／缺 index.json | 黄 `LEGAL_COVERAGE_GAP`（法律域 0 覆盖，报告里亮出），FR 闸不跑 |
| 有中国事项而 `<corpus>/catalog.jsonl.gz` 没拿到 | 黄 `LEGAL_COVERAGE_GAP`，CN 闸不跑 |
| 有意大利事项而 `<corpus>/it/index.json` 没拿到 | 黄 `LEGAL_COVERAGE_GAP`，IT 闸不跑 |
| 有西班牙事项而 `<corpus>/es/index.json` 没拿到 | 黄 `LEGAL_COVERAGE_GAP`，ES 闸不跑 |
| `date` 缺失或非 YYYY-MM-DD | 红 `LEGAL_DATE_INVALID`，时效类四闸全跳过 |
| 无 CN／IT／ES 事项且材料没配 | 正常跳过（0 事项，报告 gates 行可见 `na`） |
| CASE 闸 | 材料全在项目内（`runs/<run>/`），永远可跑 |

**每域冻结锁**：legal 维的锁件是 `audit/evidence-legal.lock`（paper 的
`audit/evidence.lock` 互不干扰）。锁的是「语料视图路径＋参考日＋现行视图
路径＋语料索引哈希」四键；冻结后换了语料或参考日 ⇒ 红 `LEGAL_EVIDENCE_CHANGED`；
解冻必须走只加流水账 `audit/evidence-legal-log.ndjson`，已解冻未重冻 ⇒ 黄
`LEGAL_EVIDENCE_UNFROZEN`。ES 与 CN／IT 同口径：**共用 legal 这一把锁**
（ES 不是独立域、没有独立 manifest，不发 `audit/evidence-es.lock`——裁定⑨
每域一把锁按 domain_id 计，`ES_` 只是 legal 码表里的子闸前缀）；ES 材料的
防篡改由 ES 闸自己的「整件／切片／卡」三层哈希链每跑现算兜底。
冻结／解冻入口（库函数，不写盘于核验路径）：

```python
from factscribe_legal.checks_adapter import write_evidence_lock, unfreeze_evidence_lock
write_evidence_lock(".", corpus="results/corpus-legal", date="2026-11-14", view="")
unfreeze_evidence_lock(".", reason="换语料", at="2026-11-16")   # 不碰系统钟，at 由人给
```

单命令双域演示（离线合成，无需真语料）：

```bash
python -m factscribe audit fixtures/legal-demo            # paper＋legal 两节报告
python -m factscribe audit fixtures/legal-demo --json     # summary.by_domain 域计数
```

## 事实账维护工具：`ledger_maint`（dup_ok 标注）

上游 R-04 规则：同一个值挂在不同 claim 上会报 `DUPLICATE_VALUE`（黄），
确属同一个数要显式写 `dup_ok = true` 承认同值。**改账是写径不是核验**
（SPEC-CHECKS §9.7），所以标注工具是独立维护模块 `factscribe_legal/ledger_maint.py`，
与核验（只读）分家——`facts_ledger.py` 只留只读检测 `scan_dupes`：

```python
from factscribe_legal.ledger_maint import mark_dup_ok
mark_dup_ok(project_dir)   # 给「同值且 claim 不同」的事实补 dup_ok = true（幂等）
```

幂等语义：已标的不动，重跑零字节变化（`tests/test_legal_maint.py` 守锁）。

## 用法（独立 CLI：调试／单域入口）

```bash
# 1) 把要引用的法条物化进项目（官方 XML + 证据卡 + 哈希）
python3 -m factscribe_legal fetch \
    --corpus  runs/run-20261114-legal \
    --project . \
    --nums L3121-27 L1225-1 L1242-2

# 2) 跑法律专项校验（参考日 = 讨论时点）
python3 -m factscribe_legal verify \
    --project . \
    --corpus  runs/run-20261114-legal \
    --date    2026-11-14 \
    --view    out/legifrance/view_20261114/merged_current.jsonl

# 3) 中国法条 / 中国案例 / 意大利法条 / 西班牙法条 / 法国判例
python3 -m factscribe_legal verify-cn   --project . --catalog out/cn/catalog_full.jsonl.gz --date 2026-11-14
python3 -m factscribe_legal verify-case --project .
python3 -m factscribe_legal verify-it   --project . --corpus runs/run-20261115-it --date 2026-11-15
python3 -m factscribe_legal verify-es   --project . --corpus corpus/es/run-20261116-es-ley39-2015-procedimiento-administrativo --date 2026-11-16
python3 -m factscribe_legal verify-fr-case --project .

# 4) 中国判例线索层（第三方文书查，非官方核验——详见上文专节）
python3 -m factscribe_legal cn-lead-search --q "机动车交通事故责任纠纷"
python3 -m factscribe_legal cn-lead-verify --case-no "（2022）苏0322执保100号"
python3 -m factscribe_legal cn-lead-get    --case-no "（2022）苏0322执保100号" --meta
```

退出码沿用上游：**0 绿 / 1 红 / 2 配置错 / 3 黄**（`cn-lead-*` 三条例外，
见专节：0 有答 / 1 查无或判不出 / 2 fail-closed）。

> 核验槽时代（M2 起），核验子命令（现七闸＋fetch 族）作为**调试／单域入口保留**（不删功能、
> 废弃窗口不限期）；正式的跨域报告走 `factscribe audit [checks]`——一份
> 信封、一套退出码、legal 节并排在 paper 之后。线索层三条（cn-lead-*）
> 不是核验入口，不挂废弃窗口提示，`[checks]` 也永不点名线索层。

## 只读接口层（`api` 族）：版本化 JSON 契约

第 12 条子命令（**只读**）：吐版本化 JSON 契约，供法律侧工作台消费。

```bash
# JSON 出口（默认就是 JSON；--human 出人读摘要）
python3 -m factscribe_legal api contract --project .
python3 -m factscribe_legal api findings --project .
python3 -m factscribe_legal api receipts --project .
python3 -m factscribe_legal api corpus    --project . --country 法国
python3 -m factscribe_legal api codes     --project .
python3 -m factscribe_legal api timeliness --project . --domain it
python3 -m factscribe_legal api summary   --project .
python3 -m factscribe_legal api proposals --project .
```

七路通道：**findings**（七条线的判定结果）、**receipts**（统一五元组收据）、
**corpus**（语料件清单）、**codes**（判定码表）、**timeliness**（跨域统一时效字段）、
**summary**（各域状态 ＋ 域级锁四键）、**proposals**（待批提案；本步只读 ⇒ 恒空数组）。

- 契约版本 `factscribe-legal-api/1.0`；字段逐条说明见
  [`docs/design/SPEC-LEGAL-API.md`](../../docs/design/SPEC-LEGAL-API.md)。
- **本层不下判定**：红黄码、措辞、退出码语义全照抄各闸；材料缺失按 `skipped`
  如实标出（不崩、不发空壳 finding）。
- **零写盘**：不写项目、不写语料、不建任何落盘动作；「待批提案」的存储与采纳
  回写属下一步（UI 与提议存储），本步只读返回空数组。
- core 侧对应只读路由：`factscribe serve` 的
  `/api/legal/{findings,receipts,corpus,codes,timeliness,summary,proposals,contract}`。

## 与上游核心的关系

- 上游 `factscribe/` **一行未改**：行为、退出码、违规码、`packages = ["factscribe"]` 打包范围都不动。
- 本包判据与五子命令**不 import 上游 `factscribe`**（只 import 标准库）⇒ 可以单独拷走单跑，也可以放进上游仓里共存。唯一例外＝`checks_adapter.py`（核验槽适配器）：它 import 宿主的 `factscribe.checks`／`factscribe.audit`，且只在 `[checks]` 点名 legal 时才被核验槽载入（见「核验包注册形态」）。
- 事实账的字段用上游已有的那套（`id` / `claim` / `value` / `source` / `source_sha256` /
  `locator` / `confidence` / `derived_from`），**不新增 schema**。

## 自测

```bash
python3 -m unittest discover -s integrations/factscribe-legal/tests -v
```

**196 条测试，全部离线**（不联网、不写仓库外的东西；线索层 `cn-lead-*` 的
真端点冒烟是一次性人工验收读数，不进测试套，离线夹具用真响应录制后脱敏）。
含三类回归：

- **双向**：每条红码都有「必须触发」与「不该触发」两个用例（上游 §5 的做法）。
- **防假绿**：多级 source 路径曾经整批被跳过 ⇒ 测它；空集不许伪装成全绿。
- **跨版本可复现**：TOML 读取层在 3.10 兜底解析器与 3.11+ 标准库 `tomllib` 上
  必须读出**同一份**事实账（见下）。

## 依赖

**Python ≥ 3.10，纯标准库，无 `eval`。** 五条 `verify-*` 闸与抓取面全离线运行；
线索层 `cn-lead-*` 是本包唯一按需联网的面（第三方文书查 MCP 端点，纯标准库
urllib 直调 JSON-RPC，见上文专节）。

TOML 读取（`factscribe_legal/_toml.py`）有一处刻意设计：3.11+ 用标准库 `tomllib`，
3.10 用本包自带的极简解析器。**不直接复用上游 `factscribe.config.load_toml`** ——
当年（2026-11-15）的理由是上游那份 3.10 兜底解析器不认嵌套数组
（`nested = [["x"], ["y", "z"]]` 会被拆成三个字符串），若复用它，同一份事实账在
3.10 与 3.11 上会读出不同结构，门禁结论不可复现。**上游那份解析器已于 2026-11-25
重写成严格档**（坏 TOML 一律报错、嵌套数组正常读），当年那条理由已经过期。
本包仍自带一份，理由换成两条：本包要能独立安装、独立运行，不把上游包变成运行依赖；
自带的那份是**更保守**的子集 —— 子集之外的写法一律报错（fail closed），不猜、不静默跳过。
本包的兜底解析器有交叉校验测试：对事实账用得到的子集，与标准库 `tomllib` **逐字相同**。
2026-11-25 另把它身上的 fail-open 洞堵上：重复键与重复表头以前是默默覆盖，
前导零整数（`01`）、多行字符串（`"""x"""` 以前被当单行解析成 `""x""`）、
闭合引号后面还有内容，这几种写法现在一律报错。

## 语料从哪来

各法域的官方件都取自官方**开放数据**通道（不是爬页面）：

| 法域 | 官方通道 | 形态 | 许可 |
|---|---|---|---|
| 法国 | DILA LEGI 增量包（`echanges.dila.gouv.fr/OPENDATA/LEGI/`） | 官方 XML | 开放许可（Etalab） |
| 中国 | 国家法律法规数据库（FLK）详情 JSON | 官方 JSON | 官方公开接口 |
| 中国案例 | 人民法院案例库入库案例正文 | 官方正文 + 回执 | 官方用户协议（个人查询、建库须走程序） |
| 意大利 | Normattiva OpenData API（`caricaAKN`） | 官方 AKN XML | CC BY 4.0 |
| 西班牙 | BOE 开放数据 API（`legislacion-consolidada` by-id） | 官方合并文本 XML | AEBOE 复用条件（2024-06-27 决议；须注明出处） |
| 法国判例 | DILA INCA 全球判决档案（`echanges.dila.gouv.fr/OPENDATA/INCA/`，stock tar.gz；sample 只取 12MB 前缀） | 官方判决 XML（TEXTE_JURI_JUDI） | licence ouverte v2.0（Etalab；须署发布方＋源 URL＋下载日期） |
| 意大利宪法法院判例 | Corte costituzionale 开放数据（`dati.cortecostituzionale.it/opendata/distribuzione/CC_OpenPronunce_*.zip`） | 官方判决档案 XML 切片 | CC BY-SA 3.0（署名＋相同方式共享；见 `corpus/it-case/ATTRIBUTION.md`） |

取件、钉哈希、建卡、选版（`date_debut <= T < date_fin`）的脚本在各自的工程仓里，
本包只消费「已经钉好哈希的官方件」。

线索层（`cn-lead-*`）**不在上表**：它的数据源是第三方聚合库文书查，不是官方
开放数据通道，也没有可钉哈希的官方字节——这正是它只能当线索、不能当官方件、
进不了核验槽的根本原因（见「中国判例线索层」专节）。

## 许可

MIT（与上游一致）。
