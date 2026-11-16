# INTEGRATION-LEGAL｜第三方集成件：法律维度（法国 / 中国 / 中国案例 / 意大利）

> 日期：2026-11-15（M2 挂槽更新：2026-11-16）
> 对应规范：`docs/design/SPEC-V1.md` §2.3（factscribe 的诚实边界：只核「账本一致」，不核「科学为真」）；`docs/design/SPEC-CHECKS.md` §3（核验包契约）、§7 M2
> 对应集成件：`integrations/factscribe-legal/`（**第三方件，不进 `factscribe/` 包**；M2 起兼任**核验槽第二个核验包**）
> 纪律：**上游 `factscribe/` 判据一行未改** —— 行为、退出码、违规码、`packages = ["factscribe"]` 打包范围都不动（M1 核验槽机构与 M2 适配器挂载是修约批的既定增量）。
> 本文件只记「这个集成件在哪、判什么、边界在哪、读数是多少」。

## 0. 结论（先看这里）

| 事项 | 结果 |
|---|---|
| 进不进上游包 | **不进**。放 `integrations/factscribe-legal/`，沿用 `integrations/minifactscribe/` 的先例；`pyproject.toml` 的 `packages = ["factscribe"]` 不变 |
| 上游核心改动 | 判据**零**。M2 挂槽批（四步走之④）按 SPEC-CHECKS 新增：core `factscribe/checks.py`（M1 已交付的核验槽机构上，加 `load_integration` 约定路径发现＋多包 summary 合并）、`report.py`／`cli.py`（多域分节渲染）；适配器居本件 `checks_adapter.py`，core 不 import integrations |
| M2 挂槽形态 | `[checks] packages = ["paper", "legal"]` → `factscribe audit` 单命令双域报告（legal 节在后、`summary.by_domain` 域计数、退出码 aggregate_exit 单一入口折算）；发现注册＝约定路径 `check-package.toml`（domain＋adapter 两字段），整目录删掉＝legal 回到未注册（点名即 exit 2），「integrations 独立、可卸载」先例不破 |
| M2 新增码 | `LEGAL_DATE_INVALID`（红，date 缺/非法）／`LEGAL_EVIDENCE_CHANGED`（红，`audit/evidence-legal.lock` 与现算不符或锁件坏）／`LEGAL_EVIDENCE_UNFROZEN`（黄，已解冻未重冻）——码表只增 |
| 每域冻结锁 | legal 维锁件＝`audit/evidence-legal.lock`（与 paper 的 `audit/evidence.lock` 互不干扰）；canonical 四键＝语料视图路径＋参考日＋现行视图路径＋语料索引哈希；解冻走只加流水账 `audit/evidence-legal-log.ndjson` |
| 新增依赖 | **零**。纯标准库，无网络调用，无 `eval` |
| Python 版本 | **≥ 3.10**（CI 矩阵 3.10–3.14 全跑；3.10 走自带 TOML 兜底解析器） |
| 退出码 | 独立子命令沿用上游：**0 绿 / 1 红 / 2 配置错 / 3 黄**；槽内退出码由 `checks.aggregate_exit` 单一入口折算（同一套语义） |
| 集成件自测 | **50 例全绿**（离线，不依赖上游）；仓侧新增：`tests/test_checks_legal.py` 25 例＋`tests/test_legal_maint.py` 5 例＋`tests/test_legal.py` …（M2 守锁面，跑在 core 测试套里） |
| 真实项目读数 | 法国 **0 红 / 1 黄**（`LEGAL_COVERAGE_GAP`）｜中国法条 **0 红 / 0 黄**｜中国案例 **0 红 / 0 黄**｜意大利 **0 红 / 0 黄**（参考日取 2026-11-14；改用 2026-11-15 则报 `IT_VERSION_GAP` 黄）。**P-100：抓取脚本丢失后真语料跑不通**，M2 行为锁改用离线合成替身 `fixtures/legal-demo`（槽内与独立子命令同项目同读数） |
| 事实账规模（真实项目） | 法国 15 条｜中国法条 16 条｜中国案例 7 条｜意大利 9 条｜管道 13 条（合计 60 条） |
| 篡改检出 | 法国官方 XML 被改 → 上游是绿的、法律闸是红的（两层不重叠）；CN/IT 篡改演示各 5/5 命中 |

## 1. 改动地图

| 文件 | 责任 |
|---|---|
| `integrations/factscribe-legal/factscribe_legal/provisions.py` | 法国侧语料读取（LEGI 版本池）、法文数字词 → 整数、`norm_text` |
| `integrations/factscribe-legal/factscribe_legal/verify.py` | 法国闸：法条存在性、参考日生效、官方字节哈希、卡片哈希、值出自正文、语料/现行视图一致性 |
| `integrations/factscribe-legal/factscribe_legal/cn_corpus.py` | 中国侧语料读取（FLK catalog 目录树） |
| `integrations/factscribe-legal/factscribe_legal/cn_verify.py` | 中国法条闸：法规现行有效、条文号存在、官方件未变、卡片链完整 |
| `integrations/factscribe-legal/factscribe_legal/case_verify.py` | 中国案例闸：案号/日期/金额与官方件一致、卡片正文未分叉、回执链完整 |
| `integrations/factscribe-legal/factscribe_legal/it_verify.py` | 意大利闸：条文存在、官方 AKN 哈希、条文切片哈希、卡片字段一致、值出自 AKN 正文、参考日版本差 |
| `integrations/factscribe-legal/factscribe_legal/facts_ledger.py` | 事实账同值检测（只读；上游 R-04 的 `DUPLICATE_VALUE` 需要显式承认同值） |
| `integrations/factscribe-legal/factscribe_legal/ledger_maint.py` | 事实账维护（写径）：`mark_dup_ok` 补 `dup_ok = true`（幂等）。P-100 松尾账①从 `facts_ledger.py` 移出——改账不是核验，不进 `verify()` |
| `integrations/factscribe-legal/factscribe_legal/checks_adapter.py` | **M2**：legal 核验包适配器（核验包卡＋四闸组装＋材料 fail-closed＋域级冻结锁）；本件唯一 import 上游 `factscribe` 的模块，且只在槽点名 legal 时被载入 |
| `integrations/factscribe-legal/check-package.toml` | **M2**：核验槽注册指针（domain＝legal ＋ adapter 模块名；core 按约定路径发现） |
| `integrations/factscribe-legal/factscribe_legal/_toml.py` | TOML 读取层：3.11+ 用 `tomllib`，3.10 用自带兜底解析器 |
| `integrations/factscribe-legal/factscribe_legal/cli.py` | `fetch` / `verify` / `verify-cn` / `verify-case` / `verify-it` |
| `integrations/factscribe-legal/tests/` | 50 例离线测试（含双向、跨版本、假绿回归） |
| `.github/workflows/test.yml` | 加一步：在主矩阵（3.10–3.14）里跑集成件的离线测试 |

## 2. 为什么它值得单独成一件

上游判的是**证据链**：正文里的数字能不能回到一份签过字、算过哈希的原始材料。
它不判「这份材料是不是法条」「这条法条今天还有效」「这个数字是不是真的出自这条法条」。

这三条在法律写作里最容易翻车，且**都是静默翻车**：

- 法条被修改后**旧版本不会消失** ⇒ 按条文编号引用会悄悄拿到旧文本；
- 法条常把数字写成词（`trente-cinq heures`）⇒ 不解析法文数字词就核不出出处；
- 官方法条是**多形态**的（原始 / 现行 / 多时效）⇒ 不钉版本就是在赌。

所以本集成件做的事只有一件：**把「引用的是不是那条、那天的、那个字节」变成机械判定。**

## 3. 四个闸的判据与边界

### 3.1 法国（`verify`）

| 码 | 严重度 | 判什么 |
|---|---|---|
| `LEGAL_PROV_UNKNOWN` | 红 | 引用的法条在语料里不存在 |
| `LEGAL_PROV_NOT_IN_FORCE` | 红 | 参考日当天该版本不生效（引了旧版或未来版） |
| `LEGAL_PROV_HASH_MISMATCH` | 红 | 现算官方 XML 哈希 ≠ 语料记录的哈希（官方字节被人动过） |
| `LEGAL_CARD_SHA256_MISMATCH` | 红 | 现算证据卡哈希 ≠ 事实账 `source_sha256`（卡被人动过） |
| `LEGAL_CARD_NO_HASH` | 红 | 卡里没有 `OFFICIAL_XML_SHA256` 声明（无法复核） |
| `LEGAL_QUOTE_MISMATCH` | 红 | 事实里的值不出现于该法条的官方正文 |
| `LEGAL_PROV_SCHEDULED` | 黄 | 引的是已排期、尚未生效的版本 |
| `LEGAL_PROV_REPEALED` | 黄 | 引的是已废止版本 |
| `LEGAL_PROV_VIEW_MISMATCH` | 黄 | 语料版本与现行视图不是同一份 |
| `LEGAL_PROV_AMBIGUOUS` | 黄 | 同一编号能定到多条（版本选不唯一） |
| `LEGAL_COVERAGE_GAP` | 黄 | 参考日当天的官方件没拿到（版本池落后） |

**边界**：绿**不代表**法条写得对，只代表「引用的法条真实存在、哈希未变、且在参考日生效」。

### 3.2 中国法条（`verify-cn`）

红：`CN_PROV_UNKNOWN` `CN_PROV_NOT_IN_FORCE` `CN_ARTICLE_NOT_FOUND` `CN_CARD_MISSING`
`CN_CARD_NO_HASH` `CN_CARD_SHA256_MISMATCH` `CN_OFFICIAL_HASH_MISMATCH` `CN_VALUE_MISMATCH`。

**边界（必须写进任何引用本闸结论的地方）**：中国侧官方件**不含条文正文**
⇒ 能核「法规现行有效」「条文号存在」「官方件未变」，**不能**核「数字出自正文」。
这是官方发布形态决定的，不是实现的缺陷。

### 3.3 中国案例（`verify-case`）

红：`CASE_OFFICIAL_MISSING` `CASE_CARD_MISSING` `CASE_OFFICIAL_HASH_MISMATCH`
`CASE_NO_MISMATCH` `CASE_DATE_MISMATCH` `CASE_AMOUNT_MISMATCH`
`CASE_VALUE_NOT_IN_OFFICIAL` `CASE_CARD_TEXT_DIVERGED` `CASE_CHAIN_BROKEN`。

**边界**：人民法院案例库存的是**要旨体例案例稿**，不是判决书原文（无抬头、无审判长、无落款印章）。
本闸核的是「这份案例稿与官方件一致」，不是「判决书原文没被改」。

### 3.4 意大利（`verify-it`）

红：`IT_PROV_UNKNOWN` `IT_CARD_MISSING` `IT_CARD_NO_HASH` `IT_CARD_SHA256_MISMATCH`
`IT_SOURCE_HASH_MISMATCH` `IT_ARTICLE_HASH_MISMATCH` `IT_ARTICLE_NOT_IN_SOURCE`
`IT_CARD_FIELD_MISMATCH` `IT_QUOTE_MISMATCH`；黄：`IT_VERSION_GAP`。

**边界**：`IT_VERSION_GAP` 只说明**参考日**的版本没拿到，是黄不是红。

## 4. 两层证据：为什么不能只靠上游

```
runs/<run>-legal/
  official/<num>.xml      权威层：官方条文 XML 原字节 —— 法条本体
  <num>.card.txt          派生层：证据卡（元数据 + 法文数字归一 + 官方正文）
  index.json              语料索引（官方标识、哈希、版本日期）
```

事实账指向**卡片**（上游的字面回查需要数字以阿拉伯数字出现），卡里声明 `OFFICIAL_XML_SHA256`，
法律闸**现算官方字节的哈希**再复核。

⇒ 上游钉住卡片没被改；法律闸钉住官方字节没被改。
**实测两层不重叠：官方 XML 被改时，上游是绿的，法律闸是红的。**

## 5. 三条工程纪律（都被实测教过）

### 5.1 归属靠文件名后缀，不靠卡内标记

维度后缀 `.it.card.txt` / `.cn.card.txt` / `.case.card.txt` / 法国侧 `.card.txt`。
若靠「卡内有没有某个字段」来判归属，则「卡被删 / 卡被篡改」会被**静默跳过** ⇒ 变成假绿
（与「空集伪装成全绿」同源）。

### 5.2 3.10 的 TOML 兜底不能图省事复用上游的

上游 `factscribe/config.py` 自带 3.10 兜底解析器（`_mini_toml`）。实测它**不认嵌套数组**：
`nested = [["x"], ["y", "z"]]` 会被拆成 `[['x'], '["y"', '"z"']`。
若直接复用，同一份事实账在 3.10 与 3.11 上会读出**不同结构** ⇒ 门禁结论不可复现。

所以本集成件自带一份兜底解析器，并配交叉校验测试：**对事实账用得到的子集，
它与标准库 `tomllib` 逐字相同**（`tests/test_toml_compat.py`）。
另外留了一条测试锁住「上游在我们真正用到的子集上与 `tomllib` 一致」，
上游哪天改方言，这条会先响。

### 5.3 官方件的身份由官方元数据自证，不由文件名决定

证据卡必须同时带**官方稳定标识**（`LEGIARTI` / `ACT_URN` / `ACT_ELI`）、
**官方标题与日期**、**官方正文**；文件名只放官方标识。
曾发生过：把一份 AKN 命名成「劳动法典」，实际取回的是另一部法典（`codiceRedaz` 参数抄错，
而文件名是自己起的 ⇒ 错误被自洽地固化）。修法就是这条：**身份由官方元数据 + 内容自证。**

另有一条日期纪律：**官方件里常有两套日期**（文本日期戳 = 最后一次修法日；
取件参数 `dataVigenza` = 参考日当天生效的版本）⇒ **判「版本时效」必须比后者**。

## 6. 自测

```bash
python3 -m unittest discover -s integrations/factscribe-legal/tests -v   # 50 例（不依赖上游）
env PYTHONPATH=. python3 -m unittest tests.test_checks_legal tests.test_legal_maint -v
# ↑ M2 仓侧守锁面（跑在 core 测试套）：发现注册／fail-closed／双域报告／
#   每域冻结锁／挂槽与独立子命令同读数（离线合成替身）／mark_dup_ok 幂等
```

集成件自身三类回归：

- **双向**：每条红码都有「必须触发」与「不该触发」两个用例（上游 CONTRIBUTING §5 的做法）。
- **防假绿**：多级 source 路径曾整批被跳过（假绿）；空集不许伪装成全绿。
- **跨版本**：TOML 读取层在兜底解析器与标准库上必须读出同一份事实账；
  把 `tomllib` 从 import 里掐掉后，包仍须可用（3.10 的真实处境）。

## 7. 刻意没做的事

- **没做**判例自动下载：各法域的官方发布形态不一样（法国的 DILA 交数据文件，
  中国的裁判文书网交阅读界面且协议禁批量），所以本集成件只消费「已经钉好哈希的官方件」。
- **没做**中文法律文书里的 NLP 抽取：那是另一个量级的问题，不该混进一个证据链闸里。
- **没改**上游 `factscribe/` 的任何一行：包括码表、退出码、SPEC 文档。
