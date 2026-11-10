# SPEC-SYNTAX｜六条句法级判据（批 102）

状态：批 102 定稿。五条新判据＋一条既有判据的 bug 修复，全部只出黄牌
（`style` 退出码 3），不改正文、不阻断构建。阈值与词表在仓根
`style-rules.toml`；实现读数见 `docs/implementation/SYNTAX.md`。

## 0. 要抓的毛病

现有 20 条判据集中在**长度、密度、清单、标题**四层，没有一条看**虚词与
语序**。本批补的六条，全部落在「一个词形／一个语序／一个固定短语」上，
能机械判定，且误报可测：

| # | 错误码 | 语言 | 抓什么 |
|---|---|---|---|
| A1 | `LIGHT_VERB_NOMINALIZATION` | 英 | `make a distinction` / `perform an analysis`：动词是空的，动作藏在名词里 |
| A2 | `ZH_DE_STACK` | 中 | 单句内「的」堆叠（的的不休） |
| A3 | `ZH_POSTPOSED_CONDITION` | 中 | `……，如果/若 B。`：条件从句后置（英文语序） |
| A4 | `ZH_DUE_TO_MAKE` | 中 | `由于/因为 X，使得/致使/导致 Y`：介词短语作主语，全句缺主 |
| A5 | `WORDINESS_BLOAT` | 英 | `due to the fact that` 这类固定膨胀短语 |
| A6 | `EMPTY_ADJECTIVE` 修复 | 中 | 「显著」是统计术语，之前被当空泛形容词 |

A1–A5 是新增判据；A6 是**修 bug**，不新增错误码。

## 1. `LIGHT_VERB_NOMINALIZATION`（英文）

### 1.1 判定

一句内出现「轻动词 ＋ 名义化名词」即报，**按条报，不设密度闸**。

- 甲组（高精度，可直接跟名义化名词，冠词可有可无）：
  `perform / conduct / carry out / undertake / provide / offer`
- 乙组（低精度，只认 `a/an ＋ 名词` 或复数名词）：
  `make / give / take / have / do / reach / achieve / establish`
- 名义化后缀：`tion / sion / ment / ance / ence / ity / ness / sis`。
  **不含裸 `-al`**：`several / partial / beneficial` 会大面积误命中。
- 名词与动词之间允许一个 `-ly` 副词（`perform a careful analysis`）。

### 1.2 为什么乙组要收窄

首版按「动词 ＋ 可选冠词 ＋ 名词」直跑，四份语料里 `paper` 命中 6 次，
其中 4 次不是名义化：

- `made the section more uniform` —— 宾语补足语（make X Y）；
- `made the ablation legible` —— 同上；
- `took the decision away` / `take the decision away` —— 短语动词；
- `establish superiority` —— 状态名词，`establish` 本身是实义动词。

乙组改认「a/an ＋ 名词」或复数名词后，这五类全部消失。甲组动词本身几乎
只在轻动词用法里出现，保留无冠词形态（`perform analysis`）。

### 1.3 白名单

`have a chance`、`provide a basis`、`have a role`、`take a look`、
`give a view`、`make a difference`。这些是正常搭配，名词不承载动作。

### 1.4 报告内容

每条 finding 必须给出「动作其实是什么」：常见名义化查
`[light_verbs.actions]` 表（`distinction → distinguish`、
`analysis → analyze`、`decision → decide`…）；表里没有的，只提示「把 X
还原成对应的动词」，**不瞎猜词形**（后缀还原会产出 `distinction →
distinc` 这类错词）。

### 1.5 单位

单位＝条。阈值 `light_verb_nominalization = 1`（`>= 1` 触发）。不做
每千词密度：真实论文实测每千词 0.1–0.9 次，密度闸没有意义。

## 2. `ZH_DE_STACK`（中文，单句式）

### 2.1 判定

一句内同时满足两条才报：

- 「的」计数 `>= zh_de_stack_min_de`，默认 **4**；
- 该句汉字数 `<= zh_de_stack_max_chars`，默认 **30**。

判定单位是句（按 `。！？；` 与空行切分）。不做全文「的」密度：本仓四份
语料从 11.3 到 42.6/千字，差 4 倍，跨库不可移植（见
`BATCH101-MERGED-PLAN.md` §四）。

### 2.2 阈值为什么从「≥3 且 ≤40」收紧

调研稿给的初值是「≥3 且 ≤40 字」。按初值直跑本仓语料：

| 语料 | 初值命中 | 每万字 |
|---|---|---|
| `paper-zh` | 19 | 17.3 |
| `paper-b-zh` | 13 | 13.6 |

远超「每条规则每万字 ≤2 条」的误报预算，且被命中的句子多是正常的列举
与复句（「两臂都跑 X，用同样的计划、同样的预检……」）。逐档下调后，
「≥4 且 ≤30 字」在四份语料上为 2 / 0 / 0 / 0 条，命中的两句都是真正的
「的」链（一句 4 个「的」、23 字；一句 4 个「的」、29 字）。这是**被
误报预算逼出来的收紧**，不是原方法的初值。

### 2.3 误报边界

- 「的」≥4 但句长 >30 字：不报（正常学术复句，定语长但有结构）。
- 引号内引用病灶本身仍会计数。`style` 的 `prose` 已遮罩代码块、公式、
  文献表；Markdown 引文块与列表按既有口径处理（列表不进本判据）。

## 3. `ZH_POSTPOSED_CONDITION`（中文，语序）

### 3.1 判定

正则形态：

```
[^。！？\n]{4,}[，,]\s*(如果|假如|倘若|一旦|要是|若)[^。！？\n]{2,}[。！？]
```

即：逗号前至少有 4 个字，逗号后紧跟条件标记，条件从句直到句末。逐句
只报第一处。

- **句首就是「如果」的正常前置不报**：正则要求条件标记在逗号之后。
- 只锁条件标记，**不锁「因为」**：`……，因为 B。` 是正常后置追补。
- 「若干」不是条件：条件体以「干」开头时跳过（`若` 后接 `干`）。
- `若` 与其他标记同时出现在句中时，取最长匹配（`倘若` 优先于 `若`）。

### 3.2 报告内容

给出机械改写示例：把条件从句移到逗号前——`「如果X，A。」`。

### 3.3 单位

单位＝处。阈值 `zh_postposed_condition = 1`。四份语料实测 0 命中。

## 4. `ZH_DUE_TO_MAKE`（中文，语法错）

### 4.1 判定

同句内：

```
(由于|因为)[^。；]{1,40}(使得|致使|导致)
```

「由于/因为 X」是介词短语，**不能作主语**；后半句用「使得/致使/导致」
另起一个谓语，全句就没有主语了。这是语法错误，不只是文风。

### 4.2 报告内容

理由必须写明「介词短语不能作主语，全句缺主」，并给改法：删掉
「由于/因为」，让原因自己当主语，后半句直接给结果。

### 4.3 误报边界

- 只判同句（句内不含 `。；`），跨句的「由于 X。这使得 Y。」不报。
- `由于` 后 1–40 字内没有「使得/致使/导致」不报（正常因果句）。
- 四份语料实测 0 命中。

### 4.4 单位

单位＝处。阈值 `zh_due_to_make = 1`。

## 5. `WORDINESS_BLOAT`（英文，固定短语）

### 5.1 判定

逐条命中下列短语（大小写不敏感）即报，每处给直接替代：

| 膨胀短语 | 直接替代 |
|---|---|
| `due to the fact that` | `because` |
| `at this point in time` | `now` |
| `in spite of the fact that` | `although` |
| `in the event that` | `if` |
| `on account of the fact that` | `because` |

表在 `[wordiness.replacements]`，可增删。

### 5.2 误报边界

只收「删掉/替换后不丢信息」的固定说法。**B 级**（`in order to` /
`in terms of` / `a number of` / `the fact that` / `with regard to`）属正常
学术行文，不进表——它们某篇能到 11 次，逐条报会刷屏。

### 5.3 单位

单位＝处。阈值 `wordiness_bloat = 1`。四份语料实测 0 命中。

## 6. `EMPTY_ADJECTIVE` 的中文「显著」（bug 修复）

### 6.1 问题

中文词表收了「显著」，`exempt_phrases` 只有英文 `statistically
significant`。中文统计写作里「显著」是术语（「统计显著」「显著差异」），
会被误判成空泛形容词。英文侧有豁免、中文侧漏了，是既有 bug。

### 6.2 修法

1. 从 `[empty_adjectives].chinese` 移除「显著」（只数无法核验的标签）；
2. 在 `exempt_phrases` 补中文八条：`统计显著`、`显著差异`、`显著性`、
   `显著水平`、`显著优于`、`显著低于`、`显著提高`、`不显著`。
   即使将来词表重新收入「显著」，这些搭配也不会误伤。

### 6.3 验收口径

只写「显著」不得被 `EMPTY_ADJECTIVE` 报（`tests/test_syntax.py` 锁死）。
其余空泛形容词（`至关重要`、`全面`、`深入`）照旧判。

## 7. 指标、错误码与单位总表

| 指标 | 错误码 | 方向 | 阈值 | 单位 |
|---|---|---|---|---|
| `light_verb_nominalization` | `LIGHT_VERB_NOMINALIZATION` | `>=` | 1 | 条 |
| `wordiness_bloat` | `WORDINESS_BLOAT` | `>=` | 1 | 处 |
| `zh_de_stack` | `ZH_DE_STACK` | `>=` | 1 | 句（句内「的」≥4 且汉字 ≤30） |
| `zh_postposed_condition` | `ZH_POSTPOSED_CONDITION` | `>=` | 1 | 处 |
| `zh_due_to_make` | `ZH_DUE_TO_MAKE` | `>=` | 1 | 处 |
| `empty_adjective` | `EMPTY_ADJECTIVE` | `>` | 6.0 | 每千词/字（既有） |

五条新指标都是「低频高信」型：按条报，不按密度报。密度型指标必须显式
写死单位（每千词 vs 每百词），本批不新增密度指标。

## 8. 误报预算（硬验收）

每条新判据在四份本仓语料上，**每万字触发 ≤2 条**：

```
env PYTHONPATH=src python3 -m factscribe style ../paper --json
env PYTHONPATH=src python3 -m factscribe style ../paper-zh --json
env PYTHONPATH=src python3 -m factscribe style ../paper-b --json
env PYTHONPATH=src python3 -m factscribe style ../paper-b-zh --json
```

实测读数与逐条判定见 `docs/implementation/SYNTAX.md` §3。`paper-zh`
的 `ZH_DE_STACK` 为 2 条（1.82/万字），是唯一触发的规则对。

## 9. 明确不判（防止回填）

- 「的」全文密度（跨语料差 4 倍，不可移植）；
- 平均句长 15–20 词、段落 ≤150 词（会打掉真实论文 18%–41% 的段落）；
- 被动占比、be 动词档位、介词密度（方法节天然多）；
- `-al/-ic/-ive` 后缀密度（命中的几乎全是技术词）；
- 通用「名词化密度」裸线（术语密集论文会被误伤，需先做术语剥离）。

## 10. 处方

| 处方 | 治的判据 | 优先序 |
|---|---|---|
| `unbury-the-verb` | `LIGHT_VERB_NOMINALIZATION` | 5 文句风格 |
| `cut-the-de` | `ZH_DE_STACK` | 5 文句风格 |

六段结构见 `factscribe/patterns/<name>/RULE.md`；登记在
`docs/design/SPEC-PRESCRIPTION.md` §5。
