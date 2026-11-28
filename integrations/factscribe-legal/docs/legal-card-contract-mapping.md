# 法律侧卡片字段映射表（六种语料形状 → 统一契约）

本文只做**读侧对照**，不改任何语料、不改任何代码。全部结论来自 2026-11-28 对
`/Users/moc/workspaces/SiAgent/factscribe-dev` 主检出的实读，行号可点。

## 0. 读法与标注

映射结果只有四类，逐字段标注：

| 标注 | 含义 |
|---|---|
| **直映** | 现有字段值原样可用，不改语义 |
| **转换** | 需要一条写死的转换规则，规则见「转换规则」列 |
| **缺** | 现语料没有这个信息，缺省值按「—」处理，不臆造 |
| **国别专属** | 保留在各国卡片里，**不进**统一契约 |

证据列写法：`路径:行号`。行号指实读时的真实行（卡片为 `KEY: VALUE` 单行格式，
第 1 行是 `#` 注释）。

---

## 1. 统一契约字段定义（本表的目标列）

| 统一字段 | 含义 | 类型 |
|---|---|---|
| `kind` | 证据类型：`provision` / `case` / `agreement` | 枚举 |
| `jurisdiction` | 法域：`fr` / `cn` / `es` / `it` | 枚举 |
| `local_id` | 各国自己的号，原样保留，不翻译 | 字符串 |
| `canonical_id` | 跨法域寻址用的合成标识（**v0 统一填「—」**，官方数据里无此字段、无权威来源，见草案 §5） | 字符串 |
| `instrument` | 法条所属法件（法典／法律／宪法） | 字符串 |
| `provision_no` | 条文号 | 字符串 |
| `effective_from` | 生效起 | ISO 日期 |
| `effective_to` | 生效止（上界） | ISO 日期 |
| `status` | 三态：`in_force` / `repealed` / `unknown`（枚举名固定） | 枚举 |
| `status_source` | status 的判据出处（`国家:机制`，如 `cn:sxx`、`fr:date_range`） | 字符串／缺省「—」 |
| `text_sha256` | 正文哈希 | hex64 |
| `official_ref` | 官方件路径＋官方件哈希 | 结构 |
| `source_url` | 来源 URL | 字符串 |
| `source_licence` | 许可 | 字符串 |
| `source_attribution` | 署名（六形状都有，载体各异：卡片 `ATTRIBUTION` 行／`ATTRIBUTION.txt`／`ATTRIBUTION.md`） | 字符串／缺省「—」 |
| `fetched_at` | 取件时刻 | ISO 8601 |
| `asof` | 该证据对应的时点版本基准日 | ISO 日期（取不到填「—」） |
| `decided_on` | 判决日（仅 `kind=case`：判例有判决日但无生效日） | ISO 日期／缺省「—」 |
| `span` / `face` / `how` | 已定收据五元组的其余三位 | 字符串／缺省「—」 |

「缺」一律填 `—`，与**共用件层**的收据缺省口径一致
（`factscribe_legal/receipts.py:34` 的 `MISSING = "—"`；
`receipts.py:96-100` 的 `build_receipt` 里 `span`/`face`/`how` 取不到即填该标记）。

---

## 2. 法国法条 `corpus/fr/`（平铺 `NUM.xml` ＋ `NUM.card.txt` ＋ `index.json`）

卡片样本：`corpus/fr/D641-10-1.card.txt:1-14`；生成代码
`tools/fetch_corpus.py:817-830`（`_fr_card`）。

| 现有字段 | 证据 | 映射 | 结果 | 转换规则 |
|---|---|---|---|---|
| `NUM` | `corpus/fr/D641-10-1.card.txt:2` | `local_id` | 直映 | 值原样（如 `D641-10-1`） |
| `CODE_ID` | 同上 `:3`（`LEGITEXT000022197698`） | `canonical_id`（候选源） | 转换 | 法国法条号→法典号，与 `canonical_id` 不同层，见草案 §5 |
| `CODE_TITLE` | 同上 `:4` | `instrument` | 直映 | 已是法典全称 |
| `LEGIARTI` | 同上 `:5`（`LEGIARTI000034616245`） | — | 国别专属 | Légifrance 条文版本号，仅法国侧用 |
| `ETAT` | 同上 `:6`（`VIGUEUR`） | `status` | 转换 | **不能直接用 ETAT 判在效**：`factscribe_legal/provisions.py:102` 明写「⚠️ 不能用 etat 判：etat=VIGUEUR 的版本可能只是『未来才生效』」。规则见时点表 §2.1 |
| `DATE_DEBUT` | 同上 `:7` | `effective_from` | 直映 | 已是 `YYYY-MM-DD` |
| `DATE_FIN` | 同上 `:8`（`2999-01-01`） | `effective_to` | 直映 | 已是 `YYYY-MM-DD`；`2999-01-01` 是「无终止」哨兵值，不改 |
| `POOL_ASOF` | 同上 `:9` | `asof` | 直映 | `2026-11-15` |
| `OFFICIAL_XML` | 同上 `:10` | `official_ref.path` | 直映 | 相对语料根的路径 |
| `OFFICIAL_XML_BYTES` | 同上 `:11` | — | 国别专属 | 字节数不进契约 |
| `TEXT_CHARS` | 同上 `:12` | — | 国别专属 | 同上 |
| `OFFICIAL_XML_SHA256` | 同上 `:13` | `official_ref.sha256` | 直映 | 官方件原字节哈希 |
| `SOURCE` | 同上 `:14` | `source_url` | 直映 | 已是 URL（增量包地址） |
| —（卡上无） | — | `text_sha256` | **缺** | `corpus/fr/index.json` 每条只有 `code_id/code_title/date_debut/date_fin/etat/legiarti/xml_file`（实读 `corpus/fr/index.json`），无正文哈希 |
| —（卡上无） | — | `source_licence` | **缺** | 法国侧许可写在 `corpus/README.md:46-47`（Etalab 开放许可），不在卡片上 |
| —（卡上无） | — | `fetched_at` | **缺** | 法国法条卡片只有 `POOL_ASOF`，无取件时刻 |
| —（卡上无） | — | `kind`/`jurisdiction` | 转换 | 由 adapter 按目录填 `provision` + `fr`，不写进卡 |
| —（卡上无） | — | `span`/`face`/`how` | **缺／转换** | 闸层不产（`factscribe_legal/fr_case_verify.py` 本分支**不定义**五元组）；**共用件层七条线都能产同构五元组**（`receipts.py:89` 的 `build_receipt` ＋ `lines.py` 的七线适配 `lines.py:22-38`、`:75`）⇒ 法国法条线取不到即填「—」 |

`index.json` 顶层另有 `generator`（`corpus/fr/index.json:2`）→ **国别专属**。

---

## 3. 中国法规 `corpus/cn/`（`cards/*.cn.card.txt` ＋ `*.cn.detail.json` ＋ `catalog.jsonl.gz`）

卡片样本：`corpus/cn/cards/中华人民共和国劳动合同法_2c909f.cn.card.txt:1-11`；
生成代码 `tools/fetch_corpus.py:986-998`。

| 现有字段 | 证据 | 映射 | 结果 | 转换规则 |
|---|---|---|---|---|
| `TITLE` | `...劳动合同法_2c909f.cn.card.txt:2` | `instrument` | 直映 | 中国侧一张卡＝一部法规（**不含条文正文**，见 §9.1） |
| `BBBS` | 同上 `:3`（`2c909fdd678bf17901678bf74d7106b3`） | `local_id` | 直映 | 国家法律法规数据库版本标识，原样 |
| `OFFICIAL_DETAIL_SHA256` | 同上 `:4` | `official_ref.sha256` | 直映 | 官方详情 JSON 原字节哈希 |
| `SXX` | 同上 `:5`（`3`） | `status` | 转换 | `1 废止 / 2 修改 / 3 有效 / 4 未生效`（判据 `factscribe_legal/cn_verify.py:91-93`）。**已定规则**：`3`⇒`in_force`；`1`⇒`repealed`；`4`⇒`unknown`；`2`⇒`unknown`（「已修改」不足以证明今天还在适用）⇒ 见时点表 §2.2 |
| `GBRQ` | 同上 `:6`（`2012-12-28`） | — | 国别专属 | 公布日期。**不进** `effective_from`——公布 ≠ 生效 |
| `SXRQ` | 同上 `:7`（`2013-07-01`） | `effective_from` | 直映 | 施行日期＝生效起 |
| `FLXZ` | 同上 `:8`（`法律`） | — | 国别专属 | 法律形式分类 |
| `ZDJG` | 同上 `:9` | — | 国别专属 | 制定机关 |
| `DETAIL_BYTES` | 同上 `:10` | — | 国别专属 | 字节数 |
| `SOURCE_URL` | 同上 `:11` | `source_url` | 直映 | 已是详情接口 URL |
| —（卡上无） | — | `effective_to` | **缺** | 官方详情只给 `sxrq`，不给失效日期；`sxx=1` 时失效日未知 ⇒ `—` |
| —（卡上无） | — | `provision_no` | **缺** | 中国侧卡是「法规级」，不含条文号；条文号在 `catalog.jsonl.gz` 的目录树里（`factscribe_legal/cn_corpus.py:66-73` 从节点标题取「第X条」） |
| —（卡上无） | — | `text_sha256` | **缺** | 官方详情 JSON **不含条文正文**（`factscribe_legal/cn_corpus.py:4-10` 明写），无正文可哈希 |
| —（卡上无） | — | `source_licence` | **缺** | 中国侧许可未在卡片与 catalog 中声明（实读 `catalog.jsonl.gz` 全部字段：`bbbs/detail_bytes/detail_sha256/detail_url/fetched_at/flxz/gbrq/n_articles/office/sxrq/sxx/title`） |
| —（卡上无） | — | `fetched_at` | 转换 | 卡片无，但 `corpus/cn/catalog.jsonl.gz` 每条有 `fetched_at`（实读 `2026-11-16T04:58:16Z`）⇒ 取 catalog 值 |
| —（卡上无） | — | `asof` | 转换 | **已定（选项 A）**：取**全库目录 `corpus/cn/catalog.jsonl.gz` 里该卡 `local_id`（=`BBBS`）对应条目的 `fetched_at` 的日期部分**（UTC 截断；实读两条为 `2026-11-16T04:58:11Z`／`2026-11-16T04:58:16Z` ⇒ `2026-11-16`）。理由：`sxx` 是**官方全库快照那一刻**的状态标志，锚点就是快照日（同法国 `POOL_ASOF`／西班牙 `REFERENCE_DATE`／意大利 `FETCH_VIGENZA` 一类的「取件/快照日」锚点）。**这不是跨卡推断**——经的是卡片自带的 `local_id`（BBBS）这把键，直连它自己的目录条目（同法国侧「卡上无 NUM 时到 `corpus/fr/index.json` 反查」同型）；目录缺该 BBBS 或目录不可得 ⇒ 填「—」 |

`catalog.jsonl.gz` 另有 `detail_bytes` / `n_articles` / `office` / `detail_url` ⇒ 国别专属。

---

## 4. 西班牙法条 `corpus/es/run-*/`（按**法件**分 run）

卡片样本：`corpus/es/run-20261116-es-ley39-2015-procedimiento-administrativo/a1.es.card.txt:1-21`；
生成代码 `tools/fetch_corpus.py:1405-1429`。

| 现有字段 | 证据 | 映射 | 结果 | 转换规则 |
|---|---|---|---|---|
| `ACT_ID` | `.../a1.es.card.txt:2`（`BOE-A-2015-10565`） | `local_id`（法件层） | 直映 | BOE 官方标识 |
| `ACT_ELI` | 同上 `:3` | — | 国别专属 | 官方法件 ELI URL |
| `ACT_TITLE` | 同上 `:4` | `instrument` | 直映 | 法件全称 |
| `ACT_NUMBER` | 同上 `:5`（`39/2015`） | — | 国别专属 | 官方文号 |
| `BLOCK_ID` | 同上 `:6`（`a1`） | `local_id`（条文层） | 直映 | BOE 合并文本块号 |
| `ARTICLE_NUM` | 同上 `:7`（`1`） | `provision_no` | 直映 | 条文号 |
| `ARTICLE_TITLE` | 同上 `:8` | — | 国别专属 | 条文标题 |
| `VERSION_DATE` | 同上 `:9`（`2026-11-16`） | — | 转换 | **不是**「这一版何时生效」——它是合并文本自身最后更新日（`factscribe_legal/es_verify.py:186-188` 注释）⇒ 不进 `effective_from` |
| `FETCH_DATE` | 同上 `:10` | `asof`（候选） | 转换 | 与 `REFERENCE_DATE` 同值，均为取件参考日 |
| `REFERENCE_DATE` | 同上 `:11` | `asof` | 直映 | `2026-11-16`＝「取件那天的官方现行合并文本」 |
| `SOURCE_FILE` | 同上 `:12`（`official/act.xml`） | `official_ref.path` | 直映 | 整件路径 |
| `SOURCE_URL` | 同上 `:13` | `source_url` | 直映 | 已是 BOE API URL |
| `OFFICIAL_XML_SHA256` | 同上 `:14` | `official_ref.sha256` | 直映 | 整件哈希 |
| `ARTICLE_SHA256` | 同上 `:15` | `text_sha256` | 转换 | 这是**条文切片**哈希，不是正文纯文本哈希（对照同目录 `index.json` 里另有 `text_sha256`）。建议契约 `text_sha256` 取 index 的 `text_sha256`，切片哈希另置 `official_ref.slice_sha256` |
| `TEXT_CHARS` | 同上 `:16` | — | 国别专属 | 字数 |
| `TEXT_STATUS` | 同上 `:17` | — | 国别专属 | 「texto consolidado de carácter meramente informativo」＝合并文本仅供参考的官方声明 |
| `LICENCE` | 同上 `:18` | `source_licence` | 直映 | AEBOE 复用条件 |
| `ATTRIBUTION` | 同上 `:19` | — | 国别专属 | 署名（建议契约加 `source_attribution` 字段承接） |
| `FETCHED_AT` | 同上 `:20` | `fetched_at` | 直映 | ISO 8601 |
| —（卡上无） | — | `effective_from`/`effective_to` | 转换（可补） | 卡片没有，但 `index.json` 有 `fecha_vigencia`（`20161002`）、`fecha_publicacion`、`fecha_disposicion`，且**官方整件每块带 `fecha_vigencia` 属性**（实读 `corpus/es/.../official/act.xml`：`fecha_vigencia="20161002"`；`a1.xml` 内 `<version ... fecha_vigencia="20161002">`）⇒ adapter 可补 |
| —（卡上无） | — | `status` | 转换 | **官方整件 `official/act.xml` 的三个效力标志**：`estatus_derogacion`（已废止）／`estatus_anulacion`（已撤销）／`vigencia_agotada`（效力已耗尽），实读三个 run 全为 `N`；**当前不在 `index.json` 里**（采集器 `tools/fetch_corpus.py:1296-1320` 的 `_es_meta` 未抽这三个键）。**已定规则**：**不用 `estado_consolidacion`**（全为 `"Finalizado"` 而三法今天全部现行有效，拿它判必错）；按三个标志判——任一为 `S` ⇒ `repealed`；全 `N` 且 `fecha_vigencia <= 参考日` ⇒ `in_force`；全 `N` 且 `fecha_vigencia > 参考日` ⇒ `unknown`；判不出落 `unknown` ⇒ 见时点表 §2.3 |

`index.json` 顶层 `estado_consolidacion` / `fecha_publicacion` / `fecha_disposicion` /
`fecha_vigencia` / `version_date` / `fetch_reference_date` / `reference_date` /
`source_bytes` / `source_sha256` / `url_html_consolidada` / `act_eli` / `act_id` /
`act_number` / `act_range` / `act_title` ⇒ 除已映射项外均国别专属。

---

## 5. 意大利法条 `corpus/it/run-*/`（按**采集批次**分 run）

卡片样本：`corpus/it/run-20261116-it-1990n241/art_1.it.card.txt:1-17`；
生成代码 `tools/fetch_corpus.py:1198-1217`。

| 现有字段 | 证据 | 映射 | 结果 | 转换规则 |
|---|---|---|---|---|
| `ACT_URN` | `.../art_1.it.card.txt:2` | `local_id`（法件层） | 直映 | `urn:nir:stato:legge:1990-08-07;241` |
| `ACT_ELI` | 同上 `:3` | — | 国别专属 | ELI 路径 |
| `ARTICLE_EID` | 同上 `:4`（`art_1`） | `local_id`（条文层） | 直映 | Normattiva 条文 EID |
| `ARTICLE_NUM` | 同上 `:5`（`1`） | `provision_no` | 直映 | 条文号 |
| `CODICE_REDAZIONALE` | 同上 `:6`（`090G0294`） | — | 国别专属 | 意大利官方编纂号（与 CCNL 的 `A011` 之类簇码不是一回事，两码同名不同物） |
| `VERSION_DATE` | 同上 `:7`（`2026-04-21`） | — | 转换 | 同西班牙：文本日期戳，非生效日（`factscribe_legal/it_verify.py:178-179` 注释） |
| `FETCH_VIGENZA` | 同上 `:8`（`20261116`） | `asof` | 转换 | 紧凑格式 `YYYYMMDD` ⇒ 补横杠为 `2026-11-16`；语义＝「取件那天生效的版本」 |
| `REFERENCE_DATE` | 同上 `:9` | `asof` | 直映 | `2026-11-16` |
| `SOURCE_FILE` | 同上 `:10` | `official_ref.path` | 直映 | `official/act.akn.xml` |
| `OFFICIAL_XML_SHA256` | 同上 `:11` | `official_ref.sha256` | 直映 | AKN 整件哈希 |
| `ARTICLE_SHA256` | 同上 `:12` | `text_sha256` | 转换 | 同西班牙：切片哈希；契约取 index 的 `text_sha256` 更准 |
| `TEXT_CHARS` | 同上 `:13` | — | 国别专属 | 字数 |
| `LICENCE` | 同上 `:14` | `source_licence` | 直映 | CC BY 4.0 |
| `ATTRIBUTION` | 同上 `:15` | — | 国别专属 | 署名 |
| —（卡上无） | — | `effective_from`/`effective_to` | **缺** | 实读 `corpus/it/run-20261116-it-1990n241/official/act.akn.xml`：AKN 头部是 `<act name="monovigente">`，grep 只命中 `datatype="xsd:date"`，**没有任何 vigenza／生效区间属性** ⇒ 法条层取不到生效区间 |
| —（卡上无） | — | `status` | **缺／转换** | 官方件无「在效」字段；`it-inventory-vigenti.tsv` **只覆盖 CCNL 集体协议（144 簇），不覆盖法条**（实读 TSV 全部标题形如 `CCNL per gli …`）⇒ 法条 status 只能由 `asof` 语义推出「该版本在 asof 日生效」＝`in_force`，但这是取件口径，不是官方效力判定 |
| —（卡上无） | — | `fetched_at` | **缺** | 意大利法条卡片无取件时刻 |
| —（卡上无） | — | `source_url` | **缺** | 意大利法条卡片只有 `SOURCE_FILE`，无源 URL（判例卡才有） |

`index.json` 顶层 `act_eli` / `act_key` / `act_title` / `act_urn` /
`codice_redazionale` / `data_gu`（1990-08-18 公布日）/ `fetch_reference_date` /
`fetch_vigenza` / `reference_date` / `source_bytes` / `source_file` /
`source_sha256` / `version_date` ⇒ 除已映射项外均国别专属。

---

## 6. 意大利宪法法院判例 `corpus/it-case/run-*/`（按批次分 run，件内按 ECLI）

卡片样本：`corpus/it-case/run-20261116-itcase-1956_1980/ECLI-IT-COST-1956-1.itcase.card.txt:1-19`；
生成代码 `tools/fetch_corpus.py:1792`（`_itcase_card`）。

| 现有字段 | 证据 | 映射 | 结果 | 转换规则 |
|---|---|---|---|---|
| `ECLI` | `.../ECLI-IT-COST-1956-1.itcase.card.txt:2`（`ECLI:IT:COST:1956:1`） | `local_id` | 直映 | 欧洲判例标识 |
| `ANNO_PRONUNCIA` | 同上 `:3`（`1956`） | — | 国别专属 | 判决年份 |
| `NUMERO_PRONUNCIA` | 同上 `:4`（`1`） | — | 国别专属 | 判决序号 |
| `TIPOLOGIA` | 同上 `:5`（`S`） | — | 国别专属 | 判决类型（S＝Sentenza） |
| `PRESIDENTE` | 同上 `:6` | — | 国别专属 | 院长 |
| `RELATORE` | 同上 `:7` | — | 国别专属 | 报告法官 |
| `DATA_DECISIONE` | 同上 `:8`（`05/06/1956`） | — | 转换 | `DD/MM/YYYY` ⇒ `1956-06-05`；判例不是「法规」，不进 `effective_from` |
| `DATA_DECISIONE_ISO` | 同上 `:9` | — | 转换 | 卡上已是 ISO；建议映射到契约新字段 `decided_on`（判决日），**不占用** `effective_from`/`effective_to` |
| `DATA_DEPOSITO` | 同上 `:10` | — | 国别专属 | 公布日 |
| `SOURCE_FILE` | 同上 `:11` | `official_ref.path` | 直映 | 切片路径 |
| `SOURCE_URL` | 同上 `:12` | `source_url` | 直映 | 官方开放数据 URL |
| `OFFICIAL_XML_SHA256` | 同上 `:13` | `official_ref.sha256` | 直映 | 官方切片哈希 |
| `TEXT_SHA256` | 同上 `:14` | `text_sha256` | 直映 | **本形状唯一名副其实的正文哈希** |
| `TEXT_CHARS` | 同上 `:15` | — | 国别专属 | 字数 |
| `LICENCE` | 同上 `:16` | `source_licence` | 直映 | CC BY-SA 3.0 |
| `ATTRIBUTION` | 同上 `:17` | — | 国别专属 | 署名 |
| `FETCHED_AT` | 同上 `:18` | `fetched_at` | 直映 | ISO 8601 |
| —（卡上无） | — | `status` | **缺** | 判例无「在效/失效」概念 ⇒ 统一三态对 `kind=case` **不适用**，填 `—`（时点表 §2.6） |
| —（卡上无） | — | `effective_from`/`effective_to` | **缺** | 判例无生效区间 |
| —（卡上无） | — | `asof` | 转换 | 判例无时点版本概念；可用 `fetch_reference_date`（`corpus/it-case/run-20261116-itcase-1956_1980/index.json:2`＝`2026-11-16`）当「取件日」，但**不是**版本基准日 |
| —（卡上无） | — | `span`/`face`/`how` | 转换 | **共用件层产出**（闸层 `factscribe_legal/fr_case_verify.py` 本分支**不定义**五元组）：`face`＝`body`/`résumé`/`—` 由 `factscribe_legal/lines.py:254-262` 的 `_face_of` 给、`how`＝`contains`/`numnorm`/`—` 由 `receipts.py:76-85` 的 `classify_how` 给、`span`＝原文坐标区间由 `receipts.py:60-73` 的 `span_in_text` 给；法国判例线在 `lines.py:501-521` |

`index.json` 的 `judgments` 每条另有 `anno`/`card_sha256`/`data_decisione`/
`data_deposito`/`ecli`/`numero`/`presidente`/`relatore`/`slice_bytes`/`slice_file`/
`slice_sha256`/`text_chars`/`text_sha256`/`tipologia` ⇒ 国别专属；
顶层 `fetch_reference_date`/`generator`/`source_url`/`source_zip_bytes`/
`source_zip_last_modified`/`source_zip_sha256`/`tier` ⇒ 国别专属。

---

## 7. 法国判例 `corpus/fr-case/run-*/`（按批次分 run，件内按 JURITEXT）

卡片样本：`corpus/fr-case/run-20261116-inca/JURITEXT000006951547.fr-case.card.txt:1-24`；
生成代码 `factscribe_legal/fr_case_reader.py:330-372`（`build_card`）。

| 现有字段 | 证据 | 映射 | 结果 | 转换规则 |
|---|---|---|---|---|
| `CASE_ID` | `.../JURITEXT000006951547.fr-case.card.txt:2` | `local_id` | 直映 | `JURITEXT000006951547` |
| `TITRE` | 同上 `:3` | — | 转换 | 判决标题，语义上不是「法件」；契约里建议对 case 留空 `instrument`，改用 `title` |
| `DATE_DEC` | 同上 `:4`（`2006-12-15`） | — | 转换 | 判决日 → 建议 `decided_on`，不占 `effective_from` |
| `JUDGE_DATE` | 同上 `:5` | — | 转换 | 与 `DATE_DEC` 同值（`fr_case_reader.py:348-349` 两行都取 `meta["date_dec"]`）；保留其一即可 |
| `JURIDICTION` | 同上 `:6` | — | 国别专属 | 法院名 |
| `CASE_NO` | 同上 `:7`（本例为空） | — | 国别专属 | 案号；判例事实账靠它判「案号形 value」（`factscribe_legal/fr_case_verify.py:205-216`） |
| `NUMEROS_AFFAIRES` | 同上 `:8`（本例为空） | — | 国别专属 | 全部案号（逗号分隔） |
| `FORMATION` | 同上 `:9`（本例为空） | — | 国别专属 | 合议庭组成 |
| `NATURE` | 同上 `:10`（`ARRET`） | — | 国别专属 | 裁判种类 |
| `SOLUTION` | 同上 `:11`（本例为空） | — | 国别专属 | 裁判主文 |
| `OFFICIAL_XML` | 同上 `:12` | `official_ref.path` | 直映 | |
| `OFFICIAL_TXT` | 同上 `:13` | — | 国别专属（建议并列进 `official_ref`） | 纯文本还原件路径 |
| `OFFICIAL_XML_BYTES` | 同上 `:14` | — | 国别专属 | |
| `OFFICIAL_XML_SHA256` | 同上 `:15` | `official_ref.sha256` | 直映 | |
| `OFFICIAL_TXT_BYTES` | 同上 `:16` | — | 国别专属 | |
| `OFFICIAL_TXT_SHA256` | 同上 `:17` | — | 国别专属（建议进 `official_ref.txt_sha256`） | |
| `TEXT_CHARS` | 同上 `:18` | — | 国别专属 | |
| `SOURCE_URL` | 同上 `:19` | `source_url` | 直映 | 档案 URL |
| `SOURCE_PATH` | 同上 `:20` | — | 国别专属 | 档案内路径（署名三件套之一） |
| `FETCHED_AT` | 同上 `:21` | `fetched_at` | 直映 | |
| `LICENCE` | 同上 `:22` | `source_licence` | 直映 | Licence ouverte v2.0 |
| `ATTRIBUTION` | 同上 `:23` | — | 国别专属 | 署名 |
| —（卡上无） | — | `text_sha256` | **缺** | 卡上只有 XML/TXT 哈希，无「正文纯文本」哈希；`TEXT_CHARS` 只是字数 |
| —（卡上无） | — | `status`/`effective_from`/`effective_to` | **缺** | 判例无效力概念 |
| —（卡上无） | — | `asof` | **缺** | |
| —（卡上无） | — | `span`/`face`/`how` | 转换 | 同上：产出在**共用件层**（`receipts.py:89` 的 `build_receipt` ＋ `lines.py` 的七线适配），意大利判例线在 `lines.py:539-570` |

---

## 8. 意大利集体协议 CCNL（`corpus-bulk-it/`，**不是卡片**）

这套**没有**证据卡，也没有条文正文。引用单位是「协议 § 条款／附件／等级表」，
不是条文号 ⇒ 单列 `kind=agreement`，形状独立，不塞进法条模板。

实读文件：`corpus-bulk-it/it-inventory-vigenti.tsv`（145 行＝1 表头＋144 簇）、
`it-clusters.json`、`it-ccnl-accordi-manifest.ndjson`（6 行）、`ATTRIBUTION`。

| 现有字段 | 证据 | 映射 | 结果 | 转换规则 |
|---|---|---|---|---|
| `code`（TSV 首列） | `corpus-bulk-it/it-inventory-vigenti.tsv:1` 表头；数据行自第 2 行起，如 `A011` | `local_id` | 直映 | CNEL 簇码 |
| `title` | 同上第 2 列（`CCNL per gli operai agricoli e florovivaisti`） | `instrument` | 直映 | 协议全称 |
| `firmatari_datoriali` | 同上第 3 列（`CONFAGRICOLTURA; …`） | — | 国别专属 | 雇主方签约方（分号分隔）⇒ 契约建议 `parties.employer` |
| `firmatari_sindacali` | 同上第 4 列 | — | 国别专属 | ⇒ `parties.union` |
| `firmatari_sindacali_adesione` | 同上第 5 列 | — | 国别专属 | 附议签署方 |
| `firmatari_sindacali_tavolo_separato` | 同上第 6 列 | — | 国别专属 | 独立谈判桌签署方 |
| `inizio_storia` | 同上第 7 列（`1979-06-25`） | `effective_from` | 直映 | 协议起始日 |
| `scadenza_ultimo_accordo` | 同上第 8 列（`2029-12-31`） | `effective_to` | 直映 | 末次协议到期日（**不是**失效日，语义差别见时点表 §2.5） |
| `datori_2025`/`dipendenti_m_2025`/`dipendenti_f_2025`/`dipendenti_2025` | 同上第 9–12 列 | — | 国别专属 | 2025 年人数统计 |
| `source`（顶层） | `corpus-bulk-it/it-clusters.json:2` | `source_url` | 直映 | CNEL xlsx 链接 |
| `xlsx_sha256` | 同上 `:3` | `official_ref.sha256` | 直映 | **清单源文件**哈希（545,236 字节，sha256 `408c0710…`） |
| `n` / `n_clusters` | 同上 `:4`；`it-ccnl-accordi-manifest.ndjson:1`（`"kind": "inventory"` 行） | — | 国别专属 | 144 簇 |
| `clusters[].code`/`.title`/`.dipendenti_2025` | `it-clusters.json` 簇数组 | `local_id`/`instrument` | 直映 | 与 TSV 同源的冗余投影 |
| manifest 各行 `kind`（`inventory`/`anomaly`） | `it-ccnl-accordi-manifest.ndjson:1-3` | — | 国别专属 | 运行事件日志，非证据 |
| — | — | `text_sha256` | **缺** | 本层只取清单与链接，**不取全文**（`corpus-bulk-it/ATTRIBUTION` 明写：「全文取件端点 scarica/accordi/<idAccordo> 已探明但**本层不调用**——只取列表与链接」）⇒ 无正文、无正文哈希 |
| — | — | `provision_no` | **缺** | 协议内条款号未采集 ⇒ `—` |
| — | — | `status` | 转换 | 由 `scadenza_ultimo_accordo` 与参考日比较得出（时点表 §2.5） |
| — | — | `fetched_at` | 转换 | manifest 里 `ts`（`2026-11-17T09:50:41Z`）可当取件时刻 |
| — | — | `kind` | 转换 | `agreement` |
| — | — | `jurisdiction` | 转换 | `it`（唯一法域，但形状独立） |

---

## 9. 汇总与三条总规律

### 9.1 各形状的硬约束（决定了契约不能一刀切）

| 形状 | 致命约束 | 证据 |
|---|---|---|
| 中国 | 官方详情 JSON **不含条文正文**，只有目录树 ⇒ 无正文哈希、卡是法规级 | `factscribe_legal/cn_corpus.py:4-10`；`cn_verify.py:171-172` |
| 意大利法条 | AKN 整件**无生效区间属性**（只有 `<act name="monovigente">`） | 实读 `corpus/it/run-20261116-it-1990n241/official/act.akn.xml` |
| 法国法条 | 采集端 `sample` 只收 `etat == "VIGUEUR"` 的条文 ⇒ 库里**根本没有已失效条文** | `tools/fetch_corpus.py:733` |
| 西班牙 | `VERSION_DATE` 是文本戳不是生效日；生效日另在 `fecha_vigencia` | `es_verify.py:186-188`；`corpus/es/*/index.json` |
| 中/意判例 | 判例无效力概念 ⇒ 三态不适用 | `fr_case_verify.py`、`it_case_verify.py` 均无 status 判定 |
| CCNL | 不是卡片、无全文、引用单位是「协议§」 | `corpus-bulk-it/ATTRIBUTION` |

### 9.2 三条规律

1. **哈希类字段全部直映**——这是全仓最一致的部分，六个形状都有官方字节哈希钉，
   统一契约的 `official_ref.sha256` 零成本。
2. **`status` 与 `asof` 是全部转换成本所在**——五国五套机制，统一层只能定
   **三态**＋**缺省「—」**，判据留给各国 adapter（时点表独立成表）。
3. **`text_sha256` 有两种语义混用**——西班牙 `ARTICLE_SHA256`、意大利
   `ARTICLE_SHA256` 都是**切片**哈希而非正文哈希；只有意大利判例的 `TEXT_SHA256`
   名副其实。契约须把「切片哈希」与「正文哈希」分列，否则 `text_sha256` 名不副实。

### 9.3 字段计数（按映射结果，概数）

| 映射结果 | 数量 | 说明 |
|---|---|---|
| 直映 | 约 45 | 哈希钉、URL、日期、标识 |
| 转换 | 约 20 | `status` 六套规则、`asof` 四种格式、`text_sha256` 两处语义混用、`kind`/`jurisdiction` 填充 |
| 缺 | 约 22 | 中国无正文/无失效日、意法条无生效区间、法法条无 `fetched_at`/`source_licence`、CCNL 无正文 |
| 国别专属 | 约 40 | 署名、许可人、字数、法典号、审判人员、簇统计… |
