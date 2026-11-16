# factscribe-legal —— 给 paperkit 接上「法律」这一维（第三方集成）

> 这是**第三方集成件**，不是 paperkit 的一部分。
> 它不进 `factscribe/` 包，不改上游任何行为、退出码或违规码；
> 沿用 `integrations/minifactscribe/` 的先例。

## 它补的是哪一维

paperkit 判的是：**正文里的数字，能不能回到一份签过字、算过哈希的原始材料**。

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

## 四个闸，四个法域

| 子命令 | 法域 | 官方件是什么 | 能判到哪一层 |
|---|---|---|---|
| `verify` | 法国（Code du travail） | LEGI 官方条文 XML | 数字真出自官方正文（含法文数字词） |
| `verify-cn` | 中国（国家法律法规数据库） | 官方详情 JSON 派生卡 | 法规现行有效、条文号存在、官方件未变 |
| `verify-case` | 中国（人民法院案例库入库案例） | 官方案例正文 + 回执链 | 案号/日期/金额与官方件一致 |
| `verify-it` | 意大利（Normattiva） | 官方 AKN XML + 条文切片 | 数值真出自官方 AKN 正文 |

各闸的错误码（**红 = 必须修，黄 = 不是绿**）：

| 闸 | 红 | 黄 |
|---|---|---|
| `verify` | `LEGAL_PROV_UNKNOWN` `LEGAL_PROV_NOT_IN_FORCE` `LEGAL_PROV_HASH_MISMATCH` `LEGAL_CARD_SHA256_MISMATCH` `LEGAL_CARD_NO_HASH` `LEGAL_QUOTE_MISMATCH` | `LEGAL_PROV_SCHEDULED` `LEGAL_PROV_REPEALED` `LEGAL_PROV_VIEW_MISMATCH` `LEGAL_PROV_AMBIGUOUS` `LEGAL_COVERAGE_GAP` |
| `verify-cn` | `CN_PROV_UNKNOWN` `CN_PROV_NOT_IN_FORCE` `CN_ARTICLE_NOT_FOUND` `CN_CARD_MISSING` `CN_CARD_NO_HASH` `CN_CARD_SHA256_MISMATCH` `CN_OFFICIAL_HASH_MISMATCH` `CN_VALUE_MISMATCH` | — |
| `verify-case` | `CASE_OFFICIAL_MISSING` `CASE_CARD_MISSING` `CASE_OFFICIAL_HASH_MISMATCH` `CASE_NO_MISMATCH` `CASE_DATE_MISMATCH` `CASE_AMOUNT_MISMATCH` `CASE_VALUE_NOT_IN_OFFICIAL` `CASE_CARD_TEXT_DIVERGED` `CASE_CHAIN_BROKEN` | — |
| `verify-it` | `IT_PROV_UNKNOWN` `IT_CARD_MISSING` `IT_CARD_NO_HASH` `IT_CARD_SHA256_MISMATCH` `IT_SOURCE_HASH_MISMATCH` `IT_ARTICLE_HASH_MISMATCH` `IT_ARTICLE_NOT_IN_SOURCE` `IT_CARD_FIELD_MISMATCH` `IT_QUOTE_MISMATCH` | `IT_VERSION_GAP` |

**各闸的判据边界（很重要，不要越界引用）**：

- 中国侧官方件**不含条文正文** ⇒ `verify-cn` 能核「法规现行有效」「条文号存在」「官方件未变」，
  **不能**核「数字出自正文」。这不是缺陷，是官方发布形态决定的。
- 案例库存的是**要旨体例案例稿**，不是判决书原文 ⇒ `verify-case` 核的是「这份案例稿与官方件一致」。
- `verify-it` 判的是「数值出自官方 AKN 条文」；`IT_VERSION_GAP` 只说明**参考日**的版本没拿到，
  是黄不是红。

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

**归属靠文件名后缀判定**（`.it.card.txt` / `.cn.card.txt` / `.case.card.txt` / 法国侧的 `.card.txt`），
不靠卡内有没有某个标记字段 —— 靠标记猜会让「卡被删 / 卡被篡改」被静默跳过，变成假绿。

## 用法

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

# 3) 中国法条 / 中国案例 / 意大利法条
python3 -m factscribe_legal verify-cn   --project . --catalog out/cn/catalog_full.jsonl.gz --date 2026-11-14
python3 -m factscribe_legal verify-case --project .
python3 -m factscribe_legal verify-it   --project . --corpus runs/run-20261115-it --date 2026-11-15
```

退出码沿用上游：**0 绿 / 1 红 / 2 配置错 / 3 黄**。

## 与上游核心的关系

- 上游 `factscribe/` **一行未改**：行为、退出码、违规码、`packages = ["factscribe"]` 打包范围都不动。
- 本包**不 import 上游 `factscribe`**（只 import 标准库）⇒ 可以单独拷走单跑，也可以放进上游仓里共存。
- 事实账的字段用上游已有的那套（`id` / `claim` / `value` / `source` / `source_sha256` /
  `locator` / `confidence` / `derived_from`），**不新增 schema**。

## 自测

```bash
python3 -m unittest discover -s integrations/factscribe-legal/tests -v
```

**50 条测试，全部离线**（不联网、不写仓库外的东西）。含三类回归：

- **双向**：每条红码都有「必须触发」与「不该触发」两个用例（上游 §5 的做法）。
- **防假绿**：多级 source 路径曾经整批被跳过 ⇒ 测它；空集不许伪装成全绿。
- **跨版本可复现**：TOML 读取层在 3.10 兜底解析器与 3.11+ 标准库 `tomllib` 上
  必须读出**同一份**事实账（见下）。

## 依赖

**Python ≥ 3.10，纯标准库，无网络调用，无 `eval`。**

TOML 读取（`factscribe_legal/_toml.py`）有一处刻意设计：3.11+ 用标准库 `tomllib`，
3.10 用本包自带的极简解析器。**不直接复用上游 `factscribe.config.load_toml`** ——
实测上游那份 3.10 兜底解析器不认嵌套数组（`nested = [["x"], ["y", "z"]]` 会被拆成三个字符串），
若复用它，同一份事实账在 3.10 与 3.11 上会读出不同结构，门禁结论不可复现。
本包的兜底解析器有交叉校验测试：对事实账用得到的子集，与标准库 `tomllib` **逐字相同**。

## 语料从哪来

各法域的官方件都取自官方**开放数据**通道（不是爬页面）：

| 法域 | 官方通道 | 形态 | 许可 |
|---|---|---|---|
| 法国 | DILA LEGI 增量包（`echanges.dila.gouv.fr/OPENDATA/LEGI/`） | 官方 XML | 开放许可（Etalab） |
| 中国 | 国家法律法规数据库（FLK）详情 JSON | 官方 JSON | 官方公开接口 |
| 中国案例 | 人民法院案例库入库案例正文 | 官方正文 + 回执 | 官方用户协议（个人查询、建库须走程序） |
| 意大利 | Normattiva OpenData API（`caricaAKN`） | 官方 AKN XML | CC BY 4.0 |

取件、钉哈希、建卡、选版（`date_debut <= T < date_fin`）的脚本在各自的工程仓里，
本包只消费「已经钉好哈希的官方件」。

## 许可

MIT（与上游一致）。
