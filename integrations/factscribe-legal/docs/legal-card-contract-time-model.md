# 时点模型对照表（法律侧最核心语义）

**为什么单独成表**：时点是法律侧最核心的语义，也是「乱」的面积最大的一块。
六种形状里，只有法国法条和 CCNL 能直接回答「这条现在有效吗」，其余四形状
要么只能间接推、要么根本不适用。

统一层只定**三态**：`in_force`（在效）／`repealed`（已失效）／`unknown`（未知）。
三态之外一律填 `—`（不适用），与收据缺省口径一致
（`factscribe_legal/fr_case_verify.py:303`）。

**统一层的判定只有一个输入**：参考日 `reference_date`。参考日缺失即无法判时点，
这是既有闸的 fail-closed 口径（`factscribe_legal/checks_adapter.py:151-159`，
`LEGAL_DATE_INVALID` 判红）。

---

## 1. 总表

| 形状 | 源侧用什么表达「有效」 | 机制 | 映射到三态的规则 | 取不到时填什么 |
|---|---|---|---|---|
| 法国法条 | `DATE_DEBUT` + `DATE_FIN` 区间（**不看 ETAT**） | 区间与参考日比 | `date_debut <= ref < date_fin` ⇒ `in_force`；`date_fin <= ref` ⇒ `repealed`；`date_debut > ref` ⇒ `unknown`（未来才生效，尚未在效） | 两字段皆空 ⇒ `unknown`＋`effective_from`/`effective_to` 填 `—` |
| 中国法规 | `SXX` 状态标志 | 单值枚举 | `3`⇒`in_force`；`1`（已废止）⇒`repealed`；`2`（已修改）⇒`unknown`；`4`（未生效）⇒`unknown`（**已定**，见 §2.2）；其余/缺失⇒`unknown` | `SXX` 缺失 ⇒ `unknown`；失效日不可得 ⇒ `effective_to` 填 `—` |
| 西班牙法条 | `fecha_vigencia`（生效日）＋ 官方是否仍提供现行合并文本（**不用 `estado_consolidacion`**，已定见 §2.3） | 日期比 + 现行合并文本可得性 | `fecha_vigencia <= ref` ⇒ `in_force`；`fecha_vigencia > ref` ⇒ `unknown`；官方已不再提供现行合并文本 ⇒ `repealed`；判不出 ⇒ `unknown` | `fecha_vigencia` 缺失 ⇒ `unknown`；`effective_to` 恒填 `—`（合并文本无终止日） |
| 意大利法条 | **无官方效力字段**（AKN 只有 `<act name="monovigente">`） | 无 | 取件口径：`asof` 日取到的就是该日生效版 ⇒ 记 `in_force`（弱口径，非官方判定） | 官方层取不到 ⇒ 若连 `asof` 也没有 ⇒ `unknown` |
| 意大利判例 | 不适用 | 无 | 三态**不适用** ⇒ `—` | 一律 `—` |
| 法国判例 | 不适用 | 无 | 三态**不适用** ⇒ `—` | 一律 `—` |
| 意大利 CCNL | `scadenza_ultimo_accordo`（末次协议到期日）＋ `inizio_storia` | 日期比 | 到期日 ≥ 参考日 ⇒ `in_force`；到期日 < 参考日 ⇒ `unknown`（不是 `repealed`，见 §2.5） | 到期日为空 ⇒ `unknown` |

---

## 2. 逐国细则

### 2.1 法国法条：区间制，且明令不许用 ETAT

- 源字段：`corpus/fr/D641-10-1.card.txt:6-8`（`ETAT: VIGUEUR`、`DATE_DEBUT: 2017-05-07`、
  `DATE_FIN: 2999-01-01`）。
- **判定口径在代码里写死**：`factscribe_legal/provisions.py:100-115`
  - `in_force_at(date)`：`date_debut <= date < date_fin`
  - `scheduled_at(date)`：`date_debut > date`
  - `repealed_at(date)`：`date_fin <= date`
  - 注释 `provisions.py:102`：**「⚠️ 不能用 etat 判：etat=VIGUEUR 的版本可能只是『未来才生效』」**
- 现行闸的三分支消费：`factscribe_legal/verify.py:166-176`
  - `scheduled_at` ⇒ 黄牌 `LEGAL_PROV_SCHEDULED`（"到 X 才生效"）
  - `repealed_at` ⇒ 黄牌 `LEGAL_PROV_REPEALED`（"已于 X 失效"）
  - 两者都不成立且 `in_force_at` 为假 ⇒ 红牌 `LEGAL_PROV_NOT_IN_FORCE`
- **注意三态与现行红黄牌不是一一对应**：现行实现里「未来才生效」和「已失效」是**两个不同的黄牌**，
  统一三态只能把它们压成 `unknown` 一态（未来）或 `repealed`（已失效），
  **「已失效」在现行实现里是黄牌不是红牌**——映射时不要把 `repealed` 理解成「出错」。
- `2999-01-01` 是「无终止」哨兵值（实读三张卡全是此值），映射时**原样保留**，不要归一成 `—`。
- 交叉验证面：`corpus/fr/view_current.jsonl` 每行 `{"date_debut","date_fin","etat","id","num","num_param"}`，
  与 `index.json` 同值；现行闸用它判 `LEGAL_PROV_VIEW_MISMATCH`（`verify.py:178-184`，黄牌）。
- **盲区**：采集端 `tools/fetch_corpus.py:733` 的 `sample` 模式 `if c["etat"] != "VIGUEUR"` 直接跳过，
  ⇒ 本地这 3 张卡全是在效条文；`date_fin` 真实到期的条文**根本没进库**。
  统一层的 `repealed` 态在法国侧**当前无法被语料实证**，除非走 bulk 全量包。

### 2.2 中国法规：状态标志制（**口径已定 2026-11-28**）

- 源字段：`corpus/cn/cards/中华人民共和国劳动合同法_2c909f.cn.card.txt:5`（`SXX: 3`）。
- 枚举含义在 `factscribe_legal/cn_verify.py:91-93` 写死：**1 废止 / 2 修改 / 3 有效 / 4 未生效**。
- 现行闸判据：`cn_verify.py:89-93`，`sxx != 3` ⇒ 红牌 `CN_PROV_NOT_IN_FORCE`。
- 取代表偏好：`factscribe_legal/cn_corpus.py:56-63`（`_prefer`），
  优先级 `{3:3, 2:2, 4:1, 1:0}`＝现行有效 > 已修改 > 未生效 > 废止，同级比 `gbrq` 新旧。

**已定口径（2026-11-28 用户拍板）**——`sxx` 的 status 判定规则：

| `sxx` | 含义 | 有效无效 | 三态落法 |
|---|---|---|---|
| `3` | 现行有效 | 在效 | `in_force` |
| `1` | 已废止 | 不在效 | `repealed` |
| `4` | 尚未生效 | 不在效 | `unknown`（尚未在效，与 §2.1 法国「未来才生效」同口径） |
| `2` | 已修改 | **判不出**——「已修改」不足以证明今天还在适用 | `unknown` |
| 缺失/其余 | — | 判不出 | `unknown` |

- **关键区分（矛盾消解的关键）**：「**挑代表版本时的排序**」与「**这条今天算不算有效**」是两件事。
  - `factscribe_legal/cn_corpus.py:56-63` 的 `_prefer`（`{3:3, 2:2, 4:1, 1:0}`）**保持不动**——
    它管的是「同题多条里挑哪条当代表」；
  - status 判定只管「有效无效」，两者互不覆盖，**不必二选一**。
- **原先那个矛盾因此消解**：旧稿把「统一三态落哪一态」当成必须与 `_prefer` 二选一，
  才觉得 `sxx=2` 必须放宽成 `in_force`（那会让统一层比现行闸宽松、悄悄放宽红线语义）。
  按已定口径 `sxx=2` ⇒ `unknown`，**统一层不比现行闸宽松**，冲突不存在了。
- 现行闸 `cn_verify.py:89-93` 的 `sxx != 3` ⇒ 红牌 `CN_PROV_NOT_IN_FORCE` **保持不动**——
  它答的是「这条能不能引」（红线判定），status 答的是「今天算不算有效」（描述），各管各的。
  ⚠️ 本次只落**文档口径**，未改动任何代码；第 3 步（status/asof 落地）由并行任务做。
- **盲区**：中国侧官方详情只给 `sxrq`（施行日），**不给失效日** ⇒ `sxx=1` 时
  `effective_to` 只能填 `—`，不能反推。
- `GBRQ`（公布日）**不是**生效日，不进 `effective_from`；生效日用 `SXRQ`。

### 2.3 西班牙法条：日期制，但生效日不在卡上

- 源字段：`corpus/es/run-20261116-es-ley39-2015-procedimiento-administrativo/a1.es.card.txt:9-11`
  （`VERSION_DATE`/`FETCH_DATE`/`REFERENCE_DATE` 全是 `2026-11-16`）。
- **`VERSION_DATE` 不是生效日**，代码注释写死（`factscribe_legal/es_verify.py:186-188`）：
  「version_date 是合并文本自身的最后更新日（fecha_actualizacion），不是『这一版在什么时候生效』；
  真正可比的是取件时用的参考日（fetch_reference_date）」。
- 真正的生效日在两处，卡上都没有：
  - `corpus/es/*/index.json` 顶层 `fecha_vigencia`（实读：ley39 `20161002`；
    const1978 `19781229`；ley40 `20161002`）
  - **官方整件每块都带属性**：实读 `corpus/es/.../official/act.xml` 有
    `fecha_vigencia="20161002"`，切片 `a1.xml` 内为
    `<version id_norma="BOE-A-2015-10565" fecha_publicacion="20151002" fecha_vigencia="20161002">`
- 合并状态 `estado_consolidacion`：实读三个 run **全为 `"Finalizado"`**。
  ⚠️ 该值在 BOE 语义里指「合并文本的**编纂流程**已结束」，**不是**「该法已废止」。
  实读三个法（1978 宪法、39/2015、40/2015）今天全部现行有效，但状态串都是 `Finalizado`。
  ⇒ **不能把 `Finalizado` 当 `repealed`**，否则会把三法全判成已失效。
- **已定口径（2026-11-28 用户拍板）**：**不用 `estado_consolidacion` 判 status**——
  它三个 run 全是 `"Finalizado"` 而三法今天全部现行有效，拿它判必错（上面已证）。
  status 改从「**官方是否仍提供现行合并文本**」判定：
  - `fecha_vigencia <= ref` 且官方仍提供现行合并文本 ⇒ `in_force`；
  - 官方已不再提供现行合并文本 ⇒ `repealed`；
  - 判不出 ⇒ `unknown`；
  - `estado_consolidacion` **留国别专属，不参与 status 判定**。
- ⚠️ 两个日期别混用（`factscribe_legal/es_verify.py:189-196`）：
  `fetch_reference_date`（取件参考日）**可比**——它对应「取件那天的官方现行合并文本」；
  `version_date`（合并文本自身最后更新日）**不是**「这一版何时生效」（同文件 `:186-188` 注释）。
  现行闸在两日不一致时出黄牌 `ES_VERSION_GAP`（`es_verify.py:191-196`），**保持不动**。
- ⚠️ 现状：本地语料**没有**「官方是否仍提供现行合并文本」这个信号
  （三个法都是 `Finalizado` ＋ `fecha_vigencia`）⇒ 现阶段西侧 status 实测只能落
  `in_force`／`unknown` 两支；「不再提供 ⇒ `repealed`」那一支待采集侧给信号后才可实证。

### 2.4 意大利法条：官方件无生效字段

- 源字段：`corpus/it/run-20261116-it-1990n241/art_1.it.card.txt:7-9`
  （`VERSION_DATE: 2026-04-21`、`FETCH_VIGENZA: 20261116`、`REFERENCE_DATE: 2026-11-16`）。
- `VERSION_DATE` 同西班牙，是文本日期戳（`factscribe_legal/it_verify.py:178-179` 注释同义）。
- 官方件实读：`corpus/it/run-20261116-it-1990n241/official/act.akn.xml`
  头部 `<act name="monovigente">`（monovigente＝单一生效版本），grep 全文件只有
  `datatype="xsd:date"` 两处命中，**无 vigenza、无生效区间**。
- `FETCH_VIGENZA` 是取件参数（`dataVigenza`），语义＝「参考日当天生效的版本」
  （`corpus/README.md:40-42` 明写「意大利侧取件参数 dataVigenza＝参考日当天生效的版本」）。
- ⇒ 统一层只能记**弱口径** `in_force`（取件日当刻生效），并在文档里注明这是取件口径不是官方效力判定；
  真正的 `effective_from`/`effective_to` 填 `—`。
- **盲区**：意大利的 `status` 实质上无法从语料自证。真正的效力判定需要另接
  Normattiva 的「vigente/abrogato」元数据接口，本轮不覆盖。

### 2.5 意大利 CCNL：到期日 ≠ 失效日

- 源字段：`corpus-bulk-it/it-inventory-vigenti.tsv` 第 7、8 列
  （`inizio_storia`、`scadenza_ultimo_accordo`）；实读 144 行两列**全非空**
  （示例 `A011`：`1979-06-25` / `2029-12-31`）。
- ⚠️ **语义陷阱**：`scadenza_ultimo_accordo` 是「**末次协议**的到期日」，
  不是「该协议的失效日」。集体协议的续签不改变 `local_id`，
  所以到期日过了只能说明**末次协议文本过期**，不能判该 CCNL 已废止。
  ⇒ 过期时应落 `unknown`，**不是** `repealed`。
- 另注：清单层**只列表不取全文**（`corpus-bulk-it/ATTRIBUTION`），
  协议正文、附件、等级表都没采 ⇒ 无正文哈希、无法核「条款是否真在协议里」。
- 全 144 簇都来自「现行或超期有效」专区（`ATTRIBUTION` 自述），
  ⇒ 清单本身就**不含**已废止协议，`repealed` 态同样无法被本层实证。

### 2.6 判例（法国／意大利）：三态不适用

- 判例没有「在效/失效」这个概念：判决作出即固定，不随时间失效。
- 现有代码也没有任何 status 判定：`factscribe_legal/fr_case_verify.py`、
  `it_case_verify.py` 全文无 status 字段消费（实读两文件的字段消费点：
  `fr_case_verify.py:330-331` 只认 `OFFICIAL_XML_SHA256`/`OFFICIAL_TXT_SHA256`；
  `it_case_verify.py:295-296` 只认 `OFFICIAL_XML_SHA256`/`TEXT_SHA256`）。
- ⇒ `kind=case` 时 `status`/`effective_from`/`effective_to` 一律填 `—`，
  **不要**拿判决日 `DATE_DEC`/`DATA_DECISIONE_ISO` 去填 `effective_from`
  （那是判决日，不是生效日；草案里另设 `decided_on` 字段承接）。

---

## 3. 统一层的时点判定总口径

1. **输入**：参考日 `reference_date`（缺失 ⇒ 判不了 ⇒ `unknown`，与
   `checks_adapter.py:151-159` 的 fail-closed 一致）。
2. **三态**：`in_force` / `repealed` / `unknown`；**不适用填 `—`**。
3. **判据归属**：统一层只定义三态的**名字与缺省**；**判据全部在各国 adapter**，
   各国特有断言（法国红黄牌四分支、中国 sxx 枚举、西班牙 fecha_vigencia、
   意法条取件口径、CCNL 到期日）留在各国。
4. **不可反推**：凡官方侧没给失效日的（中国、意大利法条、西班牙），
   `effective_to` 一律 `—`，不得用 `status` 反推日期。
5. **版本戳 ≠ 生效日**：五国的 `VERSION_DATE`／文本戳一律不映射到 `effective_from`；
   生效日只能来自 `DATE_DEBUT`（法）、`SXRQ`（中）、`fecha_vigencia`（西）。
6. **取件口径要标出来**：意大利法条与 CCNL 的 `in_force` 含「取件日当刻」成分，
   文档与 `status_source` 标注区分，别让它冒充官方判定。

## 4. 时点层的未覆盖项（明写，不假装覆盖）

- **西班牙 `estado_consolidacion` 的完整取值域未查**：本轮只见到三个 run 的
  `"Finalizado"`，BOE 该字段的其它取值（如废止/暂停/草案）本轮未取证，
  ⇒ 该字段**一律留国别专属、不参与 status 判定**（已定口径，§2.3）——
  查不查取值域都不改变这条结论。
- **意大利法条官方效力元数据未接**：Normattiva 侧有 vigente/abrogato 信息，
  本轮未探接口。
- **法国 bulk 全量包的已失效条文未取**：`fetch_corpus.py:733` 的 sample 过滤
  导致本地库无已失效条文，`repealed` 态在法国侧无实证样本。
- **CCNL 协议正文未采**：无法核条款级事实，只能核协议级元数据。
- **中国 sxx=2（修改）的三态归属已定**（§2.2，2026-11-28 用户拍板）：落 `unknown`。
  本次只落文档口径，未改动任何代码（现行闸 `cn_verify.py:89-93` 不动）。
