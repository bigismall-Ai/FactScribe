# 润色工单实施记录（批 115）

> 定位：把 `style` 的机械命中与 `prescribe` 的处方数据合成**一份操作手册 ＋ 一张工作单**，
> 让执行改写的模型拿到命令输出就知道：改什么、用什么处方、不许动什么、改完怎么验、什么时候停。
>
> 硬边界：**不新增判据**。命中直接来自 `style.analyze`，处方映射直接来自
> `prescribe.prescriptions_for`（按 `patterns/priority.toml` 的五级优先序）。
> 本批未改 `style.py` / `prescribe.py` / `protect.py` / `tide.py` / `review.py`。
> 手册里的验收命令 `factscribe review` 由批 114 提供；本批只消费它，不提交它的实现。

## 1. 交付物

| 路径 | 内容 |
|---|---|
| `factscribe/polish.py` | 工作单组装、排序、渲染；手册读取；无处方判定 |
| `factscribe/patterns/PLAYBOOK.md` | 手册数据文件（六节，写给执行改写的模型） |
| `factscribe/cli.py` | 注册 `polish` 子命令（唯一改动的既有文件） |
| `tests/test_polish.py` | 25 例契约测试 |
| `docs/implementation/POLISH.md` | 本件 |

## 2. 两条命令

```bash
python3 -m factscribe polish --print                 # 打印操作手册（Markdown）
python3 -m factscribe polish --plan <项目目录> [--json]  # 打印工作单
```

- `--print` 逐字节等于 `factscribe/patterns/PLAYBOOK.md`，不需要项目目录；
  下游管道提前关闭（`| head`）时由 `_write_stdout` 静默收尾，不报内部错误。
- `--plan` 内部跑一次与 `style --json` 同源的 `analyze`；把三个通道
  （`findings`、`advisories`、`info`）的全部命中入单，按
  `(码, 文件, 行, 原文)` 去重。`--plan` 不带值等价于 `--plan .`。
- 本命令**不是闸门**：成功永远退出 `0`；只有配置错/用法错退出 `2`。
  `--print` 与 `--plan` 互斥，缺一即用法错。
- `--json` 只作用于 `--plan`，输出结构见 §4。

## 3. 手册结构（六节，结构冻结）

| 节 | 标题 | 内容要点 |
|---|---|---|
| 1 | 目标与边界 | 只做机械可判的润色；不改观点、事实、论证方向；工作单没列的句子一字不动 |
| 2 | 绝对不许动的 | `protect` 六面（`\fact{}`、数字、`\cite` 家族、公式、表格行、`\label/\ref/\eqref`）＋三条保护面查不到的红线 |
| 3 | 流程 | 读工作单 → 查处方 → 逐条改 → 跑 `review` → 看三项明细 → 达标或放弃 → 最多 3 轮；附九条处方速查表 |
| 4 | 验收 | `factscribe review --before 原稿 --after 改后`；通过（0）/ 需复核（3）/ 拒绝（1）各自怎么处理 |
| 5 | 已知坏改法 | 七条禁做，各带反例：复述标题（`摘要。`）、删对比对象、替换关系词、垫话与设问、为过规则改僵、换套语、换破折号 |
| 6 | 什么时候停 | 3 轮不达标即停手，报告「改不动」，不许继续硬改 |

测试机械断言：六节标题恰好是 `## 1.` 到 `## 6.`；九条处方名全部出现；
三种验收结论与退出码 0/3/1 全部出现；「反例」至少 5 处且六条关键反例逐字在场；
手册里出现的每个错误码都在全集内（`style.CODE_OF` ∪ 处方绑定的码）。

## 4. 工作单格式

人读版五列（`序号  文件:行  错误码  处方  约束一句话`）：

```text
序号  文件:行                        错误码              处方                            约束
----  -----------------------------  ------------------  ------------------------------  ------------------------------------------------------
   1  sections/02_related.tex:6      HEADING_MALFORMED   heading-malformed               只去标点与括号解释；关系词保留，两个对象一个不少。
```

`--json` 结构（`schema_version` 等公共字段之外）：

```json
{
  "project": "../paper-b-zh",
  "summary": {"total": 42, "prescribed": 33, "no_prescription": 9},
  "entries": [
    {"index": 1, "file": "sections/02_related.tex", "line": 6,
     "code": "HEADING_MALFORMED", "prescription": "heading-malformed",
     "constraint": "只去标点与括号解释；关系词保留，两个对象一个不少。"}
  ]
}
```

- 条目字段固定六个：`index`、`file`、`line`、`code`、`prescription`、`constraint`；
  对照组逐键断言（`test_plan_json_shape_is_stable`）。
- 排序：处方优先序（事实 1 ＞ 结构 2 ＞ 标题指向 3 ＞ 术语 4 ＞ 文句 5）→
  无处方 6 → 文件 → 行 → 码 → 原文。同一码绑多条处方时取
  `prescriptions_for` 的第一个（`priority.toml` 序号小的胜），例如
  `HEADING_RELATION_CHANGED` 走 `heading-subject-keep`（2）而不是
  `heading-malformed`（3）。
- 确定性：同一输入两跑，文本与 JSON 均逐字节一致（`test_plan_output_is_byte_deterministic`）。

## 5. 无处方清单（20 条，机器现算）

规则：`style` 注册表里没有任何处方绑定的码，一律标
**`无处方：只提示，不许为它改句子`**，约束列写死为
`只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。`
这是防「为过规则而改坏」的最后一道闸——本模块不为这些码提供任何替代改法。

清单由 `no_prescription_codes()` 从 `style.CODE_OF` 与处方数据现算（**不硬编码**）：

| # | 错误码 | # | 错误码 |
|---|---|---|---|
| 1 | `ABBREV_FIRST_USE` | 11 | `NOMINALIZATION_RATE` |
| 2 | `COLLOQUIAL_TRIAD` | 12 | `PARAGRAPH_TEMPLATE` |
| 3 | `CONNECTIVE_DENSITY` | 13 | `REPEATED_OPENER` |
| 4 | `EMPTY_ADJECTIVE` | 14 | `RHYTHM_PLATEAU` |
| 5 | `HEDGE_STACK` | 15 | `SENTENCE_LENGTH_EXTREME` |
| 6 | `TERM_UNREGISTERED` | 16 | `SENTENCE_UNIFORMITY` |
| 7 | `TERM_VARIANT` | 17 | `WORDINESS_BLOAT` |
| 8 | `ZH_ASPECT_ZHE` | 18 | `ZH_DUE_TO_MAKE` |
| 9 | `ZH_COLLOCATION_REDUNDANCY` | 19 | `ZH_LIGHT_VERB_NOUN` |
| 10 | `ZH_DANG_WHEN` | 20 | `ZH_POSTPOSED_CONDITION` |

`style` 注册表 31 个码 − 11 个有处方的码（第 12 个处方码
`SECTION_INCOMPLETE` 是处方层自有检查码，`style` 不产生它）＝ 20 条。
任务点名的 13 条（`RHYTHM_PLATEAU`、`SENTENCE_UNIFORMITY`、
`REPEATED_OPENER`、`CONNECTIVE_DENSITY`、`PARAGRAPH_TEMPLATE`、
`HEDGE_STACK`、`EMPTY_ADJECTIVE`、`COLLOQUIAL_TRIAD`、
`TERM_UNREGISTERED`、`NOMINALIZATION_RATE`、`ZH_ASPECT_ZHE`、
`ZH_COLLOCATION_REDUNDANCY`、`ZH_DANG_WHEN`）全部落在本表内。

`RHYTHM_PLATEAU` 与 `TERM_UNREGISTERED` 走 `advisories` / `info` 通道，
不进 `style` 的 `findings`；工作单把三个通道一起扫，所以它们仍会出现在工作单上，
并被明确标成不可改。

## 6. 真实验收

### 6.1 `polish --print | head -40`

```text
# 润色操作手册（给执行改写的模型）

你拿到的是一张工作单，不是一篇待重写的文章。按下面的规矩改，改到机器不再命中就停。

## 1. 目标与边界

你只做**机械可判的润色**：在句子层面调整措辞，让正文不再命中 `style` 的机械判据。

- 只改工作单条目所指的那一句/那一行。工作单没列的句子，一个字都不动。
- 不改观点，不改论证方向，不合并或拆分小节，不新增或删除论断。
- 不改事实、数字、引用、公式、表格与交叉引用——它们属于保护面（见 §2）。
- 不追求「读起来更漂亮」。判据只有机器那几条，不命中就停，不要顺手多改。
- 工作单里标`无处方：只提示，不许为它改句子`的条目，一律跳过。那是整篇读数或聚合指标，不是逐句改法；为它改句子必然改坏。

## 2. 绝对不许动的

下面六面由 `factscribe review` 的保护面机械比对。任何一面变了，判定就是「拒绝」，本轮改动全部作废。

| 保护面 | 不许动的内容 |
|---|---|
| 事实标记 | 全文 `\fact{...}` 的 id 与顺序，`[[fact:...]]` 同算 |
| 数字 | 所有阿拉伯数字、百分比、区间、量级（`53`、`62.5\%`、`13--19`、`53k`） |
| 引用 | `\cite` 家族的全部命令与 key：`\cite` `\citep` `\citet` `\citealp` `\citeauthor` `\nocite` 等 |
| 公式 | 行内 `$...$`、`$$...$$`、`\[...\]`、`equation` / `align`（含星号）环境的内容 |
| 表格行 | `tabular` / `tabular*` 每一行的单元格数与单元格内容 |
| 交叉引用 | `\label` / `\ref` / `\eqref` 的 key 集合 |

另外三条，保护面查不到但同样是红线：

- 标题不许改论证方向：不删对比对象，不换关系词（`versus` 不许改成 `or`，`对` 不许改成 `和`）。
- 不许整段删除，不许把一段拆成一串残句，不许把解释搬到别的段落。
- 不许新增数字，不许把文字改写成数字，不许改文件名或章节名。

## 3. 流程

1. 读工作单：`python3 -m factscribe polish --plan <项目目录>`。五列：序号、文件:行、错误码、处方、约束。
2. 逐条查处方原文：`python3 -m factscribe prescribe <处方名>`。照「必做」做，「禁做（含反例）」一条都不许碰。
3. 按处方改这一处。一次只改一个条目，改完立刻记下改了哪一句。
4. 跑验收：`python3 -m factscribe review --before 原稿 --after 改后`。看三项明细：保护面、复检（只算新增）、闭合。
5. 三项都过就收工；有新增违规，只回退或重改造成新增的那几条，其它已通过的不要动。
```

### 6.2 `polish --plan ../paper-b-zh`（前 10 条）

```text
== factscribe polish --plan ==
项目：../paper-b-zh
条目：42（有处方 33，无处方 9）

序号  文件:行                        错误码              处方                            约束
----  -----------------------------  ------------------  ------------------------------  ------------------------------------------------------
   1  sections/02_related.tex:6      HEADING_MALFORMED   heading-malformed               只去标点与括号解释；关系词保留，两个对象一个不少。
   2  sections/02_related.tex:9      HEADING_MALFORMED   heading-malformed               只去标点与括号解释；关系词保留，两个对象一个不少。
   3  sections/02_related.tex:12     HEADING_MALFORMED   heading-malformed               只去标点与括号解释；关系词保留，两个对象一个不少。
   4  sections/02_related.tex:15     HEADING_MALFORMED   heading-malformed               只去标点与括号解释；关系词保留，两个对象一个不少。
   5  sections/02_related.tex:18     HEADING_MALFORMED   heading-malformed               只去标点与括号解释；关系词保留，两个对象一个不少。
   6  sections/03_design.tex:1       HEADING_MALFORMED   heading-malformed               只去标点与括号解释；关系词保留，两个对象一个不少。
   7  sections/04_style_case.tex:10  HEADING_MALFORMED   heading-malformed               只去标点与括号解释；关系词保留，两个对象一个不少。
   8  sections/04_style_case.tex:10  HEADING_TOO_LONG    heading-shorten                 只删修饰语压长度；对比对象、主语与关系词一项都不许少。
   9  sections/04_style_case.tex:18  HEADING_MALFORMED   heading-malformed               只去标点与括号解释；关系词保留，两个对象一个不少。
  10  sections/04_style_case.tex:18  HEADING_TOO_LONG    heading-shorten                 只删修饰语压长度；对比对象、主语与关系词一项都不许少。
```

**前 10 条里「无处方」的条数是 0 条**——前 33 条全部有处方
（`HEADING_MALFORMED` 10 条、`HEADING_TOO_LONG` 4 条、`DASH_PARENTHETICAL`
19 条），第 34–42 条才是 9 条 `RHYTHM_PLATEAU`，全部标「无处方」。
换句话说：这张单真正可改的只有前 33 条，最后 9 条只提示、不许动句子。

### 6.3 `polish --plan ../paper-zh`

```text
== factscribe polish --plan ==
项目：../paper-zh
条目：12（有处方 0，无处方 12）

序号  文件:行                        错误码          处方                            约束
----  -----------------------------  --------------  ------------------------------  ------------------------------------------------------
   1  appendix/b_repro.tex:5         RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
   2  appendix/d_codes.tex:4         RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
   3  sections/02_related.tex:7      RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
   4  sections/02_related.tex:11     RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
   5  sections/02_related.tex:16     RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
   6  sections/02_related.tex:20     RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
   7  sections/04_mechanisms.tex:55  RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
   8  sections/05_eval.tex:16        RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
   9  sections/05_eval.tex:22        RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
  10  sections/05_eval.tex:35        RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
  11  sections/05_eval.tex:39        RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
  12  sections/07_threats.tex:14     RHYTHM_PLATEAU  无处方：只提示，不许为它改句子  只作参考读数或整篇聚合，不是逐句改法；不许为它改句子。
```

`style` 对 `paper-zh` 的 `findings` 是 0（阶段判定已是 `polished`），
只有 12 条 `RHYTHM_PLATEAU` 参考读数；工作单因此给出 12 条「无处方」，
等于明确告诉模型：**这份稿子不用改。**

## 7. 测试

`tests/test_polish.py`：**25 例**（全离线）。分组：

| 组 | 例数 | 覆盖 |
|---|---|---|
| 手册 | 10 | 六节标题、九条处方名、三种结论与退出码、≥5 条反例与逐字反例、码全集校验、protect 六面、3 轮停手、无处方原句、`--print` 与数据文件逐字节一致、无需项目 |
| 命中→条目 | 6 | 无处方标注与约束、处方映射、约束表覆盖九条、优先序排序、无处方全集与注册表一致、注册表每码二分覆盖 |
| 工作单 CLI | 9 | 每条 finding 有条目、顺序符合优先序、处方名可在 `prescribe --list` 查到、JSON 键集合稳定、两跑逐字节一致、空单、默认当前目录、缺模式退 2、`--print/--plan` 互斥退 2 |

全量：`env PYTHONPATH=src python3 -m unittest discover -s tests`
→ 干净克隆（只含本批提交）**Ran 796 tests ... OK**（基线 771 ＋ 本批 25）。
工作区 `--fast` 读数 816，多出的 20 例是批 114 当时未提交的 `test_review.py`，
不属于本批。

## 8. 门禁输出

### 8.1 工作区测试（`env PYTHONPATH=src python3 -m unittest discover -s tests`）

```text
Ran 816 tests in 96.634s

OK
```

（816 ＝ 基线 771 ＋ 本批 25 ＋ 批 114 工作区里未提交的 review 测试 20。）

### 8.2 `./scripts/preflight-ci.sh`（干净克隆，HEAD 992089e，只含已提交文件）

```text
== 步骤 1/4：外部依赖（CI 装了 poppler；本机没有则 PDF 测试会红）
   ✓ pdftotext：/opt/homebrew/bin/pdftotext
   ✓ pdfinfo：/opt/homebrew/bin/pdfinfo
   ✓ PDF 工具齐备

== 步骤 2/4：干净克隆（只含已提交文件——夹具缺源文件这里就会暴露）
   ✓ 克隆到 .../factscribe-ci.IpTLvf/repo（HEAD 992089e）

== 步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12）
   ✓ Python 3.10：Ran 796 tests
   ✓ Python 3.11：Ran 796 tests
   ✓ Python 3.12：Ran 796 tests

== 步骤 4/4：验收样例必须 exit 1（workflow 的硬断言）
   ✓ examples/minimal audit exit=1（红，符合预期）

== 结论
   本地等价 CI 全绿——可以推。
```

### 8.3 `./scripts/preflight-ci.sh --fast`（工作区）

```text
== 步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12）
   ✓ Python 3.10：Ran 816 tests
   ✓ Python 3.11：Ran 816 tests
   ✓ Python 3.12：Ran 816 tests

== 步骤 4/4：验收样例必须 exit 1（workflow 的硬断言）
   ✓ examples/minimal audit exit=1（红，符合预期）

== 结论
   本地等价 CI 全绿——可以推。
```

错误码与非处方清单全部机器现算；干净克隆三个 Python 版本读数一致（796），
验收样例仍按预期 `exit 1`。

## 9. 提交

| 提交 | 内容 |
|---|---|
| `992089e` | 本批：`factscribe/polish.py`、`patterns/PLAYBOOK.md`、`cli.py`（只加 polish 注册）、`tests/test_polish.py`、本件 |
