# SPEC-BUDGET｜篇幅预算：可判、可改的闭环（批 128）

状态：批 128 冻结（实施依据）。
范围：`paperkit.toml` 新增可选节 `[budget]`；`style` 新增黄牌判据
`SECTION_LENGTH`；处方层新增第 10 条 `trim-to-budget`；`polish --plan`
映射该码；`brief` 节清单加「篇幅预算」列。
**不改**既有判据的取值与退出码；零第三方依赖（纯标准库）。

一句话：**给项目配一份篇幅预算，`style` 就能判出「哪一节写超了、超多少」，
`polish --plan` 把这条命中派给「先删重复、再删举例、最后合并同义句」的处方，
`brief` 在起草前就把同一份预算摆给写作模型看。**

## 1. 为什么要有

实测（批 127 收尾）：空白模型按 `brief` 起草一节，写了 **1292 词**，而目标是
**400–800**。原因不是模型不会写短，而是**简报里没有篇幅预算，也没有任何判据
管长度**——写多写少，机器一句话都不说。

三件事缺一不可：

| 缺哪件 | 后果 |
|---|---|
| 配置里没有预算 | 机器不知道「多长算超」 |
| 判据不量长度 | 超了也没人报 |
| 命中没有处方 | `polish --plan` 标「无处方」，模型只能自己猜怎么压 |

## 2. 配置（`[budget]`，可选）

```toml
[budget]
default = 800          # 英文按词、中文按汉字

[budget.sections]
"04_style_case" = 1200
```

- `default`：全项目默认预算，正整数；
- `[budget.sections]`：按节覆盖，键＝**节文件名去扩展名**
  （`sections/04_style_case.tex` → `04_style_case`），值为正整数；
- **没有 `[budget]` 时判据不生效**（向后兼容）：`SECTION_LENGTH` 指标恒为
  `0`，`metric_details.section_budget` 恒为空表，不产生任何 finding；既有指标
  的取值、`style` 的 findings 与退出码与批 127 逐字节相同（唯一的可见差别是
  `metrics` 多了一个恒为 `0` 的 `section_length` 键）；
- 有 `[budget]` 但既没 `default` 也没命中的节：该节不判（不是「预算 0」）；
- `[budget]` 里的未知键忽略，不进判据；
- 值不是「正整数」即配置错（退出码 2），不猜、不截断。

`default` 与 `[budget.sections]` 是**同一份配置**：`style` / `brief` /
`polish --plan` 三处读的是同一套值，不存在第二份抄写。

## 3. 计数口径（冻结）

- 计的是**正文单元**：英文按**词**（`[A-Za-z][A-Za-z0-9'’\-]*`），中文按
  **汉字**（CJK 统一表意区），混排时两者相加——与 `style.units_of` 完全相同；
- 先把 LaTeX 剥成正文再数：注释、`\section{...}` 等标题命令、公式、
  `\cite`、`\fact{ID}` 的 ID 参数、表格/图环境、verbatim 都不计入；
  复用 `style.prose_of`，不另写一套解析；
- 一篇一节：项目闭包里每个 `.tex` 文件单独算一节；主文件（`root_tex`）
  与被剥成空白的文件（如只有宏定义的 `audit/preamble.tex`）不判；
- **章节与附录按文件分开算**：`sections/appendix_a.tex` 的键是
  `appendix_a`，与正文章节的预算互不借用；附录要放宽就单独写一行覆盖。

## 4. 判据 `SECTION_LENGTH`（黄）

| 项 | 值 |
|---|---|
| 错误码 | `SECTION_LENGTH` |
| 严重级别 | 黄（`yellow`），不阻断 |
| 指标 | `section_length`＝超预算最狠的那一节的超出百分比（保留 1 位小数）；没有超预算的节时为 `0.0` |
| 阈值 | `style-rules.toml` 的 `thresholds.section_length_excess_percent`，默认 **20** |
| 触发 | 实际 > 预算 × 1.20（**严格超过**；正好 120% 不算超） |
| 前置 | 只在 `[budget]` 存在时运行 |

每超一节出一条 finding，消息固定给出三项读数：

```text
本节 1431 词 / 预算 800 词（超出 78.9%）
```

- 单位随该节语种走：中文节写「字」，英文节写「词」；
- `file` 是该节文件，`line` 是该节第一行正文；
- `suggestion` 只转述处方顺序（先删重复引用的数字 → 再删举例 → 再合并
  同义句），并写明三条禁做（不删论点、不删每个论点的最后一条证据、不把
  句子改短凑数）；
- 指标明细 `metric_details.section_budget` 逐节列出
  `{file, actual, budget, excess_percent}`（按文件排序），供 `--json` 消费；
  没有超预算的节 `excess_percent` 记 `0.0`（不记负数）。

## 5. 处方 `trim-to-budget`（第 10 条）

数据：`factscribe/patterns/trim-to-budget/RULE.md`，六段固定结构
（见 `SPEC-PRESCRIPTION §1`）。

| 段 | 内容要点 |
|---|---|
| 治的判据 | `- 错误码：SECTION_LENGTH` |
| 必做 | 先删重复引用的数字；再删举例；再合并同义句 |
| 禁做（含反例） | 不删论点；不删每个论点的最后一条证据；不把句子改短来凑数。反例：一段拆成三行短句，词数没降 |
| 改写示例（旧 → 新） | 正例：一段 180 词压到 120 词，论点与证据都在 |
| 验收命令 | `env PYTHONPATH=src python3 -m factscribe prescribe trim-to-budget --json` |

优先序：`style`（5）——长度是文句层的改写，不抢事实、结构、标题、术语的位。

**这条处方的红线只有一条：压的是「重复」，不是「论证」。** 观点、论点、每条
论点的最后一条证据都在保护面之内；把句子改短来骗过词数（例如一段拆成三行
短句、词数没降）是换法子过检查，不是改写。

## 6. `polish --plan` 映射

`SECTION_LENGTH` 命中必须映射到 `trim-to-budget`，不许再落到
「无处方：只提示，不许为它改句子」。映射由处方数据决定（`RULE.md` 的
`- 错误码：` 行 → `prescribe.prescriptions_for`），`polish` 不写第二张表。

## 7. `brief` 同步

`brief` 第 1 节的节清单表加一列「篇幅预算」：

```text
| # | 文件 | 当前标题 | 该节已有事实条数 | 篇幅预算 |
```

- 值来自同一份 `[budget]` 配置（`default` 或 `[budget.sections]` 覆盖）；
- 没有 `[budget]`、或该节没有可用的预算值时写 `—`；
- `--json` 的 `sections[i]` 增 `budget` 字段（整数；`0`＝无预算）。

## 8. 失败面

| 情形 | 退出码 | 说明 |
|---|---|---|
| `[budget]` 不是表 | 2 | 点名文件与字段 |
| `default` / 覆盖值不是正整数 | 2 | 点名字段与当前值 |
| `[budget.sections]` 的键不是字符串 | 2 | 点名键 |
| 没有 `[budget]` | 0 | 判据不跑（向后兼容），不是错误 |

## 9. 边界

- `SECTION_LENGTH` 是**提示**，不进 `audit`，不改红/绿判定；`style` 的退出码
  仍只有 `0` 与 `3`；
- 不新增第二套正文解析：长度复用 `style.prose_of` 与 `style.units_of`；
- 处方不参与判据：删掉 `patterns/` 整块后，`style` 的 findings、指标与退出码
  逐项不变（`tests/test_prescription.py` 的隔离用例继续成立）。
