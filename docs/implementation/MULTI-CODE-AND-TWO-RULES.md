# MULTI-CODE-AND-TWO-RULES｜批 58：多码原则＋两条新判据

> 日期：2026-11-08
> 输入：真盲测 #6 首跑 **9/12**（valid 12/12 干净、零误红）。
> 只读输入：`/tmp/holdout6`（未改动任何字节，仅作诊断，不作盲测结论）。
> 交付：SPEC-V3.0 §8 多码原则；`FACT_UNUSED_IN_SPAN`、`DUPLICATE_VALUE`
> 两条判据；`FACT_OUT_OF_SPAN` 补报；9 例新单测。

## 0. 结论（先看这里）

| 指标 | 改前 | 改后 |
|---|---|---|
| #6 hostile 命中（code 命中且不放行） | 9/12 | **12/12** |
| #6 hostile exit 与 EXPECT 逐项相等 | 10/12 | **12/12** |
| #6 valid 干净（exit 0/3 且无红） | 12/12 | **12/12** |
| 单测 | 194 | **203**（194 + 9 新）全绿 |
| 回归夹具 `fixtures/regression/paper-en`（v1） | 0 红 / 234 绑定 / 1 黄 | **不变** |

复现：

```bash
cd /Users/moc/workspaces/SiAgent/paperkit-dev
python3 -m unittest discover -s tests
python3 -m factscribe audit /tmp/holdout6/assertion-pointer-only/invalid      # exit 1，FACT_UNUSED_IN_SPAN + ASSERTION_DRIFT
python3 -m factscribe audit /tmp/holdout6/free-duplicate-value/invalid        # exit 3，DUPLICATE_VALUE
python3 -m factscribe audit /tmp/holdout6/assertion-moved-to-appendix/invalid --json  # 含 FACT_OUT_OF_SPAN
```

## 1. #6 逐项诊断（三处失败）

### 1.1 `assertion-pointer-only`（改前：绿；改后：`FACT_UNUSED_IN_SPAN` 黄＋`ASSERTION_DRIFT` 红，exit 1）

- 构造：正文 `The resolved rate is \fact{A1} as detailed in Appendix~\ref{app:rate}.`
  （单参数标记、整句无数字）；数字 `\fact{A1}{62.5\%}` 只在 `\appendix` 之后。
- 根因：`livetext.py::live_text_issues` 的三条规则各自被绕过——
  - 规则 2（标记句无数字）只在该 fact **所有**标记都缺第二参数时触发；
    附录那条带 `{62.5\%}`，`has_value=True`，规则 2 整体跳过；
  - 规则 3（附录搬家）只看 `role`，只在**正文完全没有标记**时触发；
    本题正文有裸标记，`body_marks` 非空，规则 3 跳过。
  → 两条规则正交，交叉点（正文有标记、但正文句无数字、数字在附录）没有码。
- 修法：新增规则 4，按「正文标记 vs 附录标记」分开记「这一句有没有数字承载」，
  见 §2。

### 1.2 `free-duplicate-value`（改前：绿；改后：`DUPLICATE_VALUE` 黄，exit 3）

- 构造：A1、A2 两条 fact，`claim` 不同、`run` 不同、**value 都是 62.5%**，
  各在一句里合法绑定。
- 根因：`DUPLICATE_VALUE` 只写在 `run_check()`（`factscribe check` 的路径），
  `run_audit()` 里根本没调用；盲测判卷跑的是 `audit`，所以看不见。
- 修法：把同值判定抽成 `_duplicate_value_issues()`，在 v3 的 `audit` 面调用；
  判定改用 `canon_text` 归一（`62.5\%`≡`0.625`≡`10/16`），并补三条豁免。
  `check` 面保留原判据，并同步认 `dup_ok`。

### 1.3 `assertion-moved-to-appendix`（改前：`ASSERTION_DRIFT`；改后：
`FACT_OUT_OF_SPAN` ＋ `ASSERTION_DRIFT`）

- 构造：`role = "results"`，正文只剩「见附录」，标记与数字都在 `\appendix` 后。
- 根因不是漏判，而是**一个现象两个码**：规则 3 只报了 `ASSERTION_DRIFT`，
  §8 旧口径「只能按最具体的码报一次」让实现不敢同时报 `FACT_OUT_OF_SPAN`。
  而这两个判据的触发条件本来就同时成立（角色越界＋断言漂移）。
- 修法：§8 落「多码原则」——跨判据并发时**全部报出**，EXPECT 命中任一即算；
  「只能报最具体的码」只保留给**同一判据内部的阶梯**（如证据链断点）。
  规则 3 同时发 `FACT_OUT_OF_SPAN` 与 `ASSERTION_DRIFT`。

## 2. 新判据 A：`FACT_UNUSED_IN_SPAN`（正文只剩指代）

**定义（写进 §8.2）**：定量 fact 的 `\fact{}` 标记留在正文，但正文该句里
没有任何数字承载它，数字只在 `\appendix` 之后出现 → 黄（exit 3），
并按多码原则同时记 `ASSERTION_DRIFT`（红）。复合现象整体 exit 1，
与 `EXPECT.json` 的 exit 1 一致。

**实现**（`factscribe/livetext.py::live_text_issues`，规则 4）：

1. 对每个活跃标记算三件事：所在句（`_sentence_of`）、句里有没有数字
   （`fact_value_keys`，与绑定判定同一个归一化函数）、标记在不在
   `\appendix` 之前（按行号比较 `\appendix` 行）。
2. 每条 fact 汇总：正文标记数、正文是否承载、附录是否承载。
3. 触发条件（四个同时成立）：定量（`quantitative` 或 `value` 非空）＋
   正文有标记 ＋ 正文不承载 ＋ 附录承载。

**误报边界**（宁漏勿误红）：

| 边界 | 行为 | 理由 |
|---|---|---|
| 正文句带数字、附录只是同值复述 | **不报**（良性近邻） | 判据看「正文有没有数字承载」，不看有没有附录 |
| 正文完全没有标记（即使数字在附录） | **不报本码** | 由 `role` 判据的 `FACT_OUT_OF_SPAN` 管；无 `role` 时不动 |
| 全篇没有任何数字承载（纯机制事实） | **不报本码** | 规则 2 已报 `ASSERTION_DRIFT`；本码要求「附录里才有」 |
| 正文句里有任何数字（含结构号、别的事实数字） | **不报** | 宁可漏一次，不把正常引用句打成违例 |
| 正文标记自带 `\fact{ID}{值}` 第二参数 | **不报** | 数字就在正文里 |
| 英文指代词表（appendix/Table X/如前述） | **不用词表** | 词表不可锚定、换语言即失效；只判「有没有数字承载」 |
| 注释 / 宏体 / `\iffalse` 里的标记 | 不参与（沿用 `_live_text`） | 不渲染的位置不算断言 |

## 3. 新判据 B：`DUPLICATE_VALUE`（第二张授权票）

**定义（§8.1 行已改写）**：两条 `kind=claim` 的 fact，`value` 按 `canon_text`
归一后相同、`claim` 不同 → 黄（exit 3）。

**归一化**：`canon_text` 是 §11.3 display 等价用的同一函数，因此
`62.5\%`（经 display 还原）/`62.5%`/`0.625`/`10/16` 都是同一个值；
不是字符串比较，换写法绕不过去。

**豁免（三条，全部要求人显式写）**：

1. `dup_ok = true`（§11.1 新增布尔字段）——承认「这两个值本来就是一个数」；
2. 组内 `supersedes` 指向其中一条——旧值已被替换；
3. 派生值（`derived_from`/`expr`）——父值与换算值天然同值，不是独立授权票。

另：`claim` 相同的同值不报本码（同一句话的重复由 `DUPLICATE_ID`／
`LEDGER_CONFLICT` 管）；`kind=config` 不参与（与旧 `check` 口径一致）。

**误报边界**：

| 边界 | 行为 | 理由 |
|---|---|---|
| 两条同值、claim 不同 | 报黄 | 正是「用第二个 id 再登记一次同一个数」 |
| 两条同值、claim 相同 | 不报 | 不是第二张票 |
| `dup_ok = true` / 组内 `supersedes` / 派生 | 不报 | 人签豁免与结构性豁免 |
| v1 项目（`paperkit.toml`） | `audit` **不启用** | v1 审计读数已冻结（回归夹具 234 绑定不变）；仍在 `check` 判 |
| 一条 fact 的 value 是非单一数值（区间、比值串） | `canon_text` 返回 None，退回去空白字符串比较 | 只在逐字相同的写法上判 |
| 三条以上同值 | 一次报出整组 id | 一个现象一条 findings |

## 4. 判卷读数（改后，`/tmp/holdout6` 只读）

| 族 | exit/EXPECT | 实际 codes | 判定 |
|---|---|---|---|
| assertion-moved-to-appendix | 1/1 | `FACT_OUT_OF_SPAN`, `ASSERTION_DRIFT` | HIT（多码） |
| assertion-pointer-only | 1/1 | `FACT_UNUSED_IN_SPAN`(黄), `ASSERTION_DRIFT`(红) | HIT |
| cite-handwritten-crossref | 3/3 | `NUMBER_AS_CROSSREF` | HIT |
| cite-unknown-fact-id | 1/1 | `UNKNOWN_FACT_MARKER` | HIT |
| evidence-receipt-broken | 1/1 | `EVIDENCE_CHAIN_BROKEN` | HIT |
| evidence-source-hash | 1/1 | `SOURCE_SHA256_MISMATCH`, `APPROVAL_STALE` | HIT |
| free-duplicate-value | 3/3 | `DUPLICATE_VALUE` | HIT |
| free-table-bare-literal | 5/5 | `TABLE_UNBOUND` | HIT |
| number-binding-marker-mismatch | 1/1 | `BOUND_MISMATCH`, `ASSERTION_DRIFT` | HIT |
| number-binding-missing-marker | 3/3 | `UNBOUND_NUMBER` | HIT |
| tex-macro-body-number | 1/1 | `NUMERIC_IN_MACRO` | HIT |
| tex-numexpr-computed | 1/1 | `COMPUTED_VALUE_UNREGISTERED`, `NUM_ADJACENT_MACRO` | HIT |

valid 12/12：全部 exit 0、findings 为空（含 pointer-only 的良性近邻：
正文带数字、附录复述）。

## 5. 附带发现（不在本批范围，仅记账）

1. **旧集 `holdout`..`holdout4` 的 benign 全部红在 `EVIDENCE_CHAIN_BROKEN`**
   （`git stash` 对照：改前改后**同读数**，不是本批回归）。原因：批 56 把
   证据链升红后，旧集项目没有 `record.json`。旧集不作结论，仅说明「benign
   0/32」这行不是新判据造成的。
2. **`tex-numexpr-computed` 同一句报 3 条 `COMPUTED_VALUE_UNREGISTERED`**
   （不同 location 但同一现象）。多码原则不要求同一判据重复报；去重属
   下一批清理，改动会影响既有计数，未在本批动。

## 6. 需用户裁定的两处措辞

1. **`FACT_UNUSED_IN_SPAN` 的 severity**：§8.2 原登记 `red/1`，批 58 任务
   书写的是「黄（exit 3）」。本批按任务书登记为 **yellow/3**，并同时报
   `ASSERTION_DRIFT`（红），所以复合退出码仍是 1、与 #6 的 `EXPECT.json`
   一致。若您要它单独就是红，把 §8.2 那一行的 severity 改回 red 即可，
   代码只需去掉 `severity=SEV_YELLOW`。
2. **「一个现象两个码」与 §8.4「唯一映射」的关系**：本批把「唯一映射」理解
   为「同一判据内部只报最具体的一个节点」，跨判据并发全部报出（§8 开头已
   写明）。若您要的是「跨判据也只能留一个码」，`FACT_OUT_OF_SPAN` 与
   `ASSERTION_DRIFT` 并发这条要回炉。
