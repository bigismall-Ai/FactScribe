# 统一法律语料卡片契约（草案）

**本轮性质**：只读调研＋文档产出。**未改任何代码、任何语料数据文件、任何既有文档**。
新增文件仅本目录下三份：
`legal-card-contract-draft.md`（本文）、`legal-card-contract-mapping.md`（字段映射表）、
`legal-card-contract-time-model.md`（时点模型对照表）。

---

## 1. 结论先行：**有条件可行**

**结论：这条路可行，但必须做成「加在前面的公共层」，不能做成「把六种形状拉平」。**
可行为什么成立、不可行会卡在哪、最小落地动作是什么，逐条给证据。

### 1.1 可行的三条依据

**依据一：六种形状的哈希钉完全一致，这部分零成本。**
六种语料都有「官方件原字节哈希」这一层，且位置相同：
法国法条 `OFFICIAL_XML_SHA256`（`corpus/fr/D641-10-1.card.txt:13`）、
中国 `OFFICIAL_DETAIL_SHA256`（`...劳动合同法_2c909f.cn.card.txt:4`）、
西班牙 `OFFICIAL_XML_SHA256`＋`ARTICLE_SHA256`（`.../a1.es.card.txt:14-15`）、
意法条 `OFFICIAL_XML_SHA256`＋`ARTICLE_SHA256`（`.../art_1.it.card.txt:11-12`）、
意判例 `OFFICIAL_XML_SHA256`＋`TEXT_SHA256`（`.../ECLI-IT-COST-1956-1.itcase.card.txt:13-14`）、
法判例 `OFFICIAL_XML_SHA256`＋`OFFICIAL_TXT_SHA256`（`.../JURITEXT000006951547.fr-case.card.txt:15,17`）。
⇒ 统一契约的 `official_ref.sha256` 这一栏**一个转换规则都不用写**，是全仓最齐的部分。

**依据二：契约的绝大多数字段在现有卡片里已经存在，只是叫各自的名字。**
逐字段核对见映射表：约 45 个字段可**直映**，约 20 个需要**转换**（且转换规则都能写成
一行确定性函数），约 22 个**缺**（要填「—」），约 40 个**国别专属**（留各国）。
「需要转换」的那 20 个里，没有一个是开放式的语义判断——全是
「日期格式」「枚举值映射」「切片哈希 vs 正文哈希」这类可机械执行的规则。

**依据三：现有代码已经把「时点」判过一次，只是判在各国闸里。**
法国闸的 `in_force_at/scheduled_at/repealed_at` 三分支（`factscribe_legal/provisions.py:100-115`）、
中国闸的 `sxx != 3` 判红（`factscribe_legal/cn_verify.py:89-93`）、
西班牙/意大利闸的 `VERSION_GAP` 黄牌（`es_verify.py:189-196`、`it_verify.py:180-187`）
⇒ 时点语义**已经被想清楚了**，只是没抽成公共层。统一层要做的不是重新发明，是**搬家**。

### 1.2 两种做法：一个是**真不可行**，一个是**只是贵**

**卡法一：把六种形状拉平成一种卡形状——真不可行。**
卡在三条硬约束上，任何一条都足以否掉「拉平」。
**这三条不是「成本高」，是那些字段在官方数据里本来就不存在，任何加工手段都补不出来**：

1. **中国官方件不含条文正文**——`factscribe_legal/cn_corpus.py:4-10` 明写「官方详情 JSON
   （目录树＋元数据，**无正文**）」；`cn_verify.py:171-172` 也重复了这一句。
   ⇒ 中国侧没有正文可哈希、没有条文号可填，**物理上做不出和法国同形的卡**。
2. **意大利法条官方件无生效区间**——实读 `corpus/it/run-20261116-it-1990n241/official/act.akn.xml`，
   AKN 头部只有 `<act name="monovigente">`，全文件 grep 只命中 `datatype="xsd:date"`，
   **没有 vigenza / 生效起止**。⇒ 意法条做不出 `effective_from/to`。
3. **判例无效力概念**——法国判例与意大利判例都没有「在效/已失效」，
   现有代码也无任何 status 消费（实读 `fr_case_verify.py:330-331`、`it_case_verify.py:295-296`）。
   ⇒ 三态对 `kind=case` 不适用。

⇒ **「拉平」是真不可行**：缺口在官方数据本身，不在任何加工手段能补出来的范围内。

**卡法二：重排目录或重写语料来「对齐」——可行，但成本高（本轮不做）。**
卡住的**不是技术**，是**重钉的活量**：哈希本来就**能重算**，重算一次即可。
卡片是**派生件＋官方字节哈希钉**，改一张卡就改它的 sha256，
而事实账钉的就是卡的 sha256
（`factscribe_legal/verify.py:156-159` 判 `LEGAL_CARD_SHA256_MISMATCH`；
`cn_verify.py:83-86`、`es_verify.py:155-163` 同理）
⇒ 重排目录／重排语料之后，**重新算一遍哈希、重写事实账**，链路即可重新变绿。
「重排会让所有引用旧卡的事实账集体变红」说的只是**重钉之前那一瞬**，
不是「回不来」——**这是成本，不是「不可能」**。
本轮不做的理由只有一条：成本（明细见 §3.2）——24 张卡 + 全部引用它们的事实账
+ `corpus/manifest.json` 72 条 + 法国 bulk 重采约 1.2GB。

### 1.3 最小落地动作（建议按这个顺序）

**第一步：只加公共层，一个字节都不改现有语料。**
- 在 `factscribe_legal/` 新增一个 **adapter 层**（每国一个 adapter 函数），
  输入＝现有卡片＋index，输出＝统一契约的字段字典。
- **不改任何 `.card.txt`、`.json`、`.jsonl`、`.ndjson`、`.tsv`**；
  **不改任何现有 verify 逻辑**。
- adapter 读路径**同时兼容新旧两种**：先看有没有公共层视图，没有就现场从旧卡推导。
  这样现有六闸的判定结果**逐字不变**（可回归验证）。

**第二步：先只落 `kind` + `jurisdiction` + `local_id` 三个字段。**
这三个字段在六种形状里**全是直映**（见映射表 §2-§8），零转换、零歧义，
且立刻就能支撑「证据类型分类」这一层的检索与筛选——这是用户认可的三层里的第一层，
也是最省事的一层。

**第三步：再落 `status` 三态与 `asof`。**
这是最费劲也最有价值的一步，因为五国五套机制（时点表 §1）。
做法：**统一层只定义三态的名字与缺省「—」，判据全放各国 adapter**。
不要试图在统一层写一个通用的「有效性公式」——那正是「拉平」的陷阱。

**第四步：最后落 `span`/`face`/`how`。**
这三位的**生产逻辑已经在法国判例闸里跑通了**
（`factscribe_legal/fr_case_verify.py:213-217`，`face`=`body`/`résumé`/`—`，
`how`=`contains`/`numnorm`/`—`，`span`=`"s-e"` 原文坐标区间），
且**五元组口径已定**（`id｜sha16｜span｜face｜how`，缺省「—」）。
⇒ 这一步不是设计，是**引用仓里已有的共用生产逻辑**：`factscribe_legal/receipts.py` 的
`build_receipt`（`receipts.py:89`；字段序 `id｜sha16｜span｜face｜how` 见 `receipts.py:37`，
缺省标记 `MISSING = "—"` 见 `receipts.py:34`）＋ `factscribe_legal/lines.py` 的七线适配点
（适配表 `lines.py:22-38`、`LINES` 表 `lines.py:75`、七处 `build_receipt` 调用
`lines.py:331/355/385/431/476/516/565`）。
**统一契约的 `span`/`face`/`how` 直接与收据五元组对齐、取不到填「—」，不另立一套定义**
（已定口径，2026-11-28 用户拍板）。

**明确不做**：不重排目录、不重写语料（**是本轮不做，不是做不到**——重排要重钉一遍，成本见 §3.2）、不动现有闸的判定、不动 `factscribe/` 引擎。

---

## 2. 统一卡片契约（草案）

### 2.1 契约的定位（最重要的一条）

> **各国原有字段一个都不删。统一契约是加在前面的公共层，不是替换层。**
> 现有卡片继续是事实账钉哈希的对象（`verify.py:156-159` 等处依赖这一点），
> 公共层是**读侧派生视图**，可随时重建、可丢弃。

这个定位有三重好处：
1. 现有六闸的判定结果不变 ⇒ 回归成本≈0；
2. 公共层坏了，删掉重算即可 ⇒ 不污染数据；
3. 将来某国要改形状，只改该国 adapter，不牵动别人。

### 2.2 字段清单

```yaml
# 统一法律卡片契约 v0（草案；未落任何数据）
kind:            provision | case | agreement     # 证据类型三分
jurisdiction:    fr | cn | es | it                # 法域
local_id:        <string>                          # 各国自己的号，原样保留
canonical_id:    <string>                          # 跨法域寻址用（v0 暂不落值，见 §5）
instrument:      <string>                          # 法条所属法件 / 协议全称
provision_no:    <string>                          # 条文号；取不到填 "—"
effective_from:  <YYYY-MM-DD>                      # 生效起；取不到填 "—"
effective_to:    <YYYY-MM-DD>                      # 生效止；取不到填 "—"
status:          in_force | repealed | unknown | "—" # 三态；不适用填 "—"
text_sha256:     <hex64>                           # 正文哈希；取不到填 "—"
official_ref:
  path:          <string>                          # 官方件相对路径
  sha256:        <hex64>                           # 官方件哈希钉
  slice_sha256:  <hex64>                           # 条文切片哈希（西班牙/意大利）
  txt_sha256:    <hex64>                           # 纯文本还原件哈希（法国判例）
source_url:      <string>                          # 来源 URL
source_licence:  <string>                          # 许可
source_attribution: <string>                       # 署名（建议新增，承接各国 ATTRIBUTION）
fetched_at:      <ISO-8601>                        # 取件时刻
asof:            <YYYY-MM-DD>                      # 时点版本基准日
decided_on:      <YYYY-MM-DD>                      # 判决日（仅 kind=case）
status_source:   <string>                          # status 的判据出处（如 "fr:date_range"）
span:            <string>                          # 收据五元组之一，缺省 "—"
face:            body | résumé | "—"                # 收据五元组之一
how:             contains | numnorm | "—"            # 收据五元组之一
```

### 2.3 相对用户建议的三处微调（附理由）

| 建议字段 | 本草案的处置 | 理由 |
|---|---|---|
| `kind`（provision/case/agreement） | **保留** | 三分正好对上三种现实：中国卡是「法规级」不是「条文级」，只能归 provision 并标 `scope=law`；CCNL 单列 agreement |
| `local_id` | **保留，但允许复合** | 西班牙与意大利法条需要「法件层 + 条文层」两级号 ⇒ 允许 `local_id` 存 `BOE-A-2015-10565/a1`、`urn:...;241/art_1` 这类复合，原样保留各国原号不翻译 |
| `instrument` | **保留，但对 case 改语义** | 法国判例的 `TITRE` 是判决标题不是法件 ⇒ 对 `kind=case` 建议 `instrument` 填「—」，另用 `title` 字段 |
| —— | **新增 `decided_on`** | 判例有判决日但无生效日；不新增就得拿判决日去填 `effective_from`，那是语义污染 |
| —— | **新增 `source_attribution`** | 六个形状都有署名，但形状各异（有的在卡上、有的在 `ATTRIBUTION.txt`、有的在 `ATTRIBUTION.md`）⇒ 需要一个统一落点，否则「署名」这一面在契约层会丢 |
| —— | **新增 `status_source`** | 五国五套 status 判据，必须能回答「这个状态是谁判的、凭什么判的」，否则统一层就成黑箱 |
| —— | **新增 `official_ref.slice_sha256` / `.txt_sha256`** | 西班牙/意法条的 `ARTICLE_SHA256` 是切片哈希、意判例有 `TEXT_SHA256`、法判例有 `OFFICIAL_TXT_SHA256` ⇒ 混进 `text_sha256` 会让「正文哈希」名不副实（映射表 §9.2 规律三） |

### 2.4 `kind=agreement`（集体协议）的单独形状

CCNL 这套**不是卡片**（无 `.card.txt`、无官方件副本、无正文），
引用单位是「协议 § 条款／附件／等级表」，不是条文号。
所以它**不是 provision 的变体**，是第三种形状：

```yaml
kind:            agreement
jurisdiction:    it
local_id:        A011                    # CNEL 簇码，原样
instrument:      CCNL per gli operai agricoli e florovivaisti
provision_no:    "—"                     # 协议内条款号未采集
parties:
  employer:      [CONFAGRICOLTURA, ...]  # 雇主方签约方
  union:         [FLAI CGIL, ...]        # 工会方
  adhesion:      [UGL Agroalimentare]   # 附议方
  separate_table: []                     # 独立谈判桌
scope:
  sector:        agricoltura             # 行业/工种（派生）
  cluster_count: 144
effective_from:  1979-06-25             # inizio_storia
effective_to:    2029-12-31             # scadenza_ultimo_accordo（到期日≠失效日）
status:          in_force | unknown      # 不落 repealed，理由见时点表 §2.5
text_sha256:     "—"                     # 本层不取全文
official_ref:
  path:          corpus-bulk-it/it-inventory-vigenti.tsv
  sha256:        408c0710...            # 源 xlsx 哈希（it-clusters.json:3）
source_url:      https://www.cnel.it/.../ccnl-di-settore-vigenti-e-ultrattivi.xlsx
source_licence:  "—"                     # 本层未见许可声明
fetched_at:      2026-11-17T09:50:41Z   # 取自 manifest 的 ts
asof:            2026-11-17
```

共用规则：**哈希钉、来源、许可、时点三态**四样与其它 kind 共用；
**形状不共用**——它没有 `text_sha256`、没有 `provision_no`、`instrument` 装的是协议全称。

### 2.5 通用校验收敛成一份（各国特有断言留在各国）

**通用层（一份，对所有 kind 生效）：**
1. `official_ref.sha256` 与现算官方件字节一致（哈希钉对账）——这是全套的地基，
   六国现有闸都已实现，只是各写一遍（`verify.py:151-155`、`cn_verify.py:77-80`、
   `es_verify.py:122-125`、`it_verify.py:114-117`、`it_case_verify.py:325-344`、
   `fr_case_verify.py:337-344`）。
2. 卡片自身哈希与事实账钉的一致（`verify.py:156-159` 等）。
3. 必填字段非空：`kind`/`jurisdiction`/`local_id`/`official_ref.sha256`/
   `source_licence`（缺失即红，与现行 fail-closed 一致，
   如 `cn_verify.py:74-76` 的 `CN_CARD_NO_HASH`）。
4. 许可与署名的存在性（现在散在 `ATTRIBUTION.txt`/`ATTRIBUTION.md`／卡片 `LICENCE` 行三处）。
5. `asof` 与参考日的一致性（西班牙/意大利已有 `VERSION_GAP` 黄牌可复用口径）。

**各国特有（留在各国 adapter 与各国闸）：**
- 法国：`date_debut`/`date_fin` 区间判定四分支（`verify.py:166-176`）、视图交叉验证
  （`LEGAL_PROV_VIEW_MISMATCH`）、法文数字词归一（`provisions.py:30-55`）。
- 中国：`sxx` 枚举判定（`cn_verify.py:89-93`）、目录树「第X条」存在性（`cn_verify.py:126-130`）。
- 西班牙：条文切片与整件的从属校验（`es_verify.py:139-149` 的 `ES_ARTICLE_NOT_IN_SOURCE`）。
- 意大利法条：同上的切片从属校验（`it_verify.py:141`）。
- 意大利判例：ECLI/ANNO/NUMERO 三元组一致性（`it_case_verify.py:413-419`）。
- 法国判例：引文契约（face/span/how）、拼接未标记（`fr_case_verify.py:229-268`）。
- CCNL：簇码在 144 簇清单内的存在性。

---

## 3. 重钉成本量化（本轮绝不重钉，但要算清账）

### 3.1 现有卡片规模（实读，2026-11-28）

| 形状 | 已物化卡片数 | 位置 |
|---|---|---|
| 法国法条 | 3 | `corpus/fr/*.card.txt` |
| 中国法规 | 2 | `corpus/cn/cards/*.cn.card.txt` |
| 西班牙法条 | 9 | `corpus/es/run-*/*.es.card.txt`（3 个 run × 3 块） |
| 意大利法条 | 4 | `corpus/it/run-*/*.it.card.txt` |
| 意大利判例 | 2 | `corpus/it-case/run-*/*.itcase.card.txt` |
| 法国判例 | 4 | `corpus/fr-case/run-*/*.fr-case.card.txt` |
| **合计（已物化）** | **24** | `corpus/` 下 `find -name '*.card.txt'` |
| 法国法条（blobstore 未物化） | **171,801** | `corpus-bulk/fr-blobstore-manifest.jsonl` 中 `kind="fr-law-card"` 的行数 |
| 法国法条官方 XML（同批） | 171,801 | 同上 `kind="fr-law-xml"` |
| CCNL 协议簇 | 144 | `it-inventory-vigenti.tsv` 行数 −1 表头 |

即：本地可动的卡片 **24 张**；blobstore 里还有 **171,801 张法国法条卡**未物化
（该 manifest 共 343,604 行）。

### 3.2 成本结论

- **只做公共层（不动卡）⇒ 重钉成本 = 0**。公共层是读侧派生，不进哈希链。
- **若要给现有卡「加统一字段」⇒ 24 张卡要重钉**，即：
  - 24 个 `.card.txt` 的 sha256 变；
  - 所有引用这些卡的事实账 `source_sha256` 全部要重算（`verify.py:156-159` 那道闸会先判红，**重钉一次即转绿**——哈希能重算，不存在「回不来」）；
  - `corpus/manifest.json` 的 `files` 72 条对账项要重算
    （实读：`manifest.json` 顶层 `files` 共 72 条，按目录分布
    `cn:5 / es:24 / fr:8 / fr-case:14 / it:12 / it-case:6 / state:1 / +2 文本`）；
  - **法国侧还要跑 bulk 全量包重采**才能覆盖 blobstore 的 171,801 张卡
    （`corpus/README.md:26` 明写 bulk_fr 约 1.2GB；`corpus/README.md:30` 写 fr-case bulk 约 664MB）。
- **CCNL 那套若要加字段**：改 `it-inventory-vigenti.tsv` 会动 144 行的源投影，
  但它是**表不是卡**，没有卡片哈希链 ⇒ 成本远低于法条侧；
  真正的哈希钉在源 xlsx（sha256 `408c0710…`，`it-clusters.json:3`），
  改表不动 xlsx 就不断链。

### 3.3 为什么最小落地动作选「读侧派生」

| 方案 | 重钉成本 | 事实账影响 | 回归成本 | 建议 |
|---|---|---|---|---|
| A 读侧 adapter 派生统一层 | 0 | 无 | ≈0 | ✅ **推荐** |
| B 在现有卡上加统一字段行 | 24 张卡 + 全部引用事实账 | 需重钉（先红后绿） | 需重跑六闸 | ✗ 本轮不（成本） |
| C 重排目录统一形状 | 24 + 171,801 张 | 需重钉（先红后绿） | 需重跑采集 | ✗ 本轮不（成本） |

（「拉平各国官方格式」不在表内：它是**真不可行**——中国无正文、意法条无生效区间、
判例无效力概念，那些字段在官方数据里就不存在，见 §1.2 卡法一。）

---

## 4. 边界与风险（必须说清的）

1. **改卡就改 sha**——卡片是派生件＋官方字节哈希钉，事实账钉的就是卡哈希
   （`verify.py:156-159`）。⇒ 本轮**不做**重排目录或重写语料——
   **是成本问题不是不可行**：重排后重钉一遍即可（哈希能重算），
   代价见 §3.2（24 张卡 + 全部引用事实账 + `manifest.json` 72 条 + 法国 bulk 约 1.2GB）；
   公共层必须是**读侧派生**，不写回卡片。
2. **目录语义混着两种轴**——西班牙按**法件**分 run
   （`run-20261116-es-ley39-2015-procedimiento-administrativo` 等 3 个），
   意大利法条与法国判例按**采集批次**分 run
   （`run-20261116-it-1990n241`、`run-20261116-it-2012n190`、`run-20261116-inca`）。
   ⇒ 同一目录层级在不同法域含义不同，`kind`/`jurisdiction` **不能靠目录名推断**，
   必须由 adapter 显式绑定。
3. **意大利法条与判例是两套 run 命名**——`corpus/it/run-*it-*` 与
   `corpus/it-case/run-*itcase-*`，切勿混；卡片后缀也分别靠
   `.it.card.txt`（`it_verify.py:50-52`）与 `.itcase.card.txt` 区分。
4. **中国侧是法规级不是条文级**——卡上没有条文号、没有正文；
   条文号在目录树里（`cn_corpus.py:66-73`）。统一层若不显式标 `scope`，会误导检索。
5. **判例的 status 不适用**——三态填「—」，别拿判决日冒充生效日。
6. **五元组只在法国判例产出**——其余五闸不产 `span`/`face`/`how`
   （实读：`fr_case_verify.py:302-304` 是唯一产地）。
   ⇒ **已定**（2026-11-28 用户拍板）：统一契约的 `span`/`face`/`how` **直接与收据五元组对齐**——
   引用仓里已有的共用生产逻辑（`receipts.py` 的 `build_receipt` ＋ `lines.py` 的七线适配），
   取不到填「—」，**不另立一套定义**；其余闸走同一套共用件，不再各写一套。
7. **SXX=2（修改）语义已定**——时点表 §2.2：落 `unknown`（「已修改」不足以证明今天还在适用）；
   `_prefer` 的 `3>2>4>1` 排序**保持不动**（管的是挑哪条当代表，不是有效无效）。
8. **西班牙 `estado_consolidacion` 不可当废止标志**——实读三法全是 `"Finalizado"`，
   而三法今天全部现行有效。**已定**：该字段不参与 status 判定，
   改判「官方是否仍提供现行合并文本」，判不出落 `unknown`（时点表 §2.3）。
9. **意大利法条 `in_force` 是取件口径不是官方判定**——须用 `status_source` 标出来。

---

## 5. `canonical_id`：v0 统一填「—」（**口径已定 2026-11-28**）

用户建议的 `canonical_id` 是「跨法域寻址」的合成标识。但**六种形状的官方数据里
都没有这个字段**（实读六种形状的卡与 index，无一有跨法域编号），
⇒ **已定：v0 统一填「—」**——跨法域编号**无权威来源**，等真有展示需求再单独建对照表。
本轮**不**臆造、**不**用 `{jurisdiction}:{local_id}` 顶替：那种形式解决不了
「同一实体多法域」的问题，而那才是它存在的意义；先占位会让人误以为寻址问题已解决。

将来真要立项跨法域对照表时，需要先定三件事（本轮**不立项**，仅备查）：

1. **合成规则**：是 `{jurisdiction}:{local_id}` 就完事，还是跨法域对齐同一实体
   （如「欧盟条例」同时出现在 `fr`/`es`/`it` 三个语料里）？后者要一张
   **跨法域实体对照表**——那是新数据、新工程。
2. **谁维护**：对照表是机器生成还是人工维护？出错谁背？
3. **冲突时怎么办**：同一 `canonical_id` 在两国语料里指向不同版本时，以谁为准？

⇒ v0 落 `kind`/`jurisdiction`/`local_id` 三件套 ＋ `canonical_id` 填「—」。

---

## 6. 未覆盖项（明写，不假装覆盖）

| 未覆盖 | 为什么 | 影响 |
|---|---|---|
| 中国 sxx=2（修改）的三态归属 | **口径已定**：落 `unknown`（时点表 §2.2）；代码落地由第 3 步并行任务做，本轮只落文档 | 文档已定，代码未落 |
| 西班牙 `estado_consolidacion` 完整取值域 | 本轮只见 `"Finalizado"`（3 个 run），BOE 其它取值未取证 | 该字段**已定不参与 status 判定**（时点表 §2.3），留国别专属；取值域未查不改变该结论 |
| 意大利法条官方效力元数据（vigente/abrogato） | Normattiva 接口本轮未探 | 意法条 `status` 只能是弱口径 |
| 法国已失效条文（`repealed` 态实证） | 采集端 `fetch_corpus.py:733` 只收 `VIGUEUR`；本地库无失效样本 | `repealed` 在法国侧无法实证 |
| CCNL 协议正文与条款 | 本层只列表不取全文（`corpus-bulk-it/ATTRIBUTION`） | 协议只能核到元数据层 |
| blobstore 171,801 张法国卡的逐张字段核对 | 未物化，只核了 manifest 的 kind 计数与首两条 | 该批卡的字段集推定与已物化的 3 张同构，**未逐张验证** |
| `corpus/manifest.json` 72 条对账项的逐条重算 | 本轮只读未重算 | 重钉成本按「需重算」计 |
| 五元组在非法国判例闸的产出方式 | **口径已定**：统一契约 `span`/`face`/`how` 直接对齐收据五元组（`receipts.py` 的 `build_receipt` ＋ `lines.py` 七线适配），取不到填「—」，不另立定义 | 口径已定，代码落地待第 4 步 |
| 跨法域 `canonical_id` 对照表 | 需新数据新工程 | `canonical_id` v0 留空 |
| 现有六闸的回归跑批 | 本轮只读不写盘，按约定不跑会写盘的全量自检 | adapter 落地时需补定向回归 |
| 中国案例（`corpus/case/`） | 该目录**当前不存在**（`corpus/README.md:13` 表格登记为「**本批为空**：检索接口需登录」，实读 `corpus/` 下无 `case/` 目录） | 第七种形状待接口解封后再补，本轮不纳入 |

---

## 7. 一页纸小结

- **可行，但只能「加层」，不能「拉平」。** 中国无正文、意法条无生效区间、判例无效力概念
  —— 三条硬约束否掉任何形式的形状统一；**理由是那些字段在官方数据里就不存在**（补不出来），
  不是「要重算哈希」这类成本问题。
- **哈希钉零成本**（六国都齐），**转换只有约 20 条**（全是机械规则），**缺的约 22 个填「—」**。
- **时点是最乱的一块**：五国五套机制，统一层只管三态的名字与缺省，判据留各国
  （时点表独立成表）。
- **重钉成本**：不动卡＝0；动卡＝24 张卡 + 全部引用事实账 + 法国 bulk 重采（1.2GB）；
  blobstore 里还有 171,801 张未物化卡。
- **可行性口径（2026-11-28 更正）**：「**拉平各国官方格式**」＝**真不可行**（字段不存在）；
  「**重排语料**」＝**可行，只是要重钉一遍**（哈希能重算，重算一次即转绿）。
  旧稿把「有成本」写成「不可行」，此处已更正。
- **最小落地动作**：新增 adapter 层（只读派生，不写回）→ 先落
  `kind`/`jurisdiction`/`local_id`（全直映）→ 再落 `status`/`asof` → 最后收五元组。
- **本轮产出**：三份文档，**未改任何代码与语料数据文件**，主检出与其它工作树全程只读。
