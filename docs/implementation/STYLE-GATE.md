# STYLE-GATE｜批 64：文风闸原型 `factscribe style`

> 日期：2026-11-08
> 目标：给作者（人或 LLM）一份**可机械复算**的改写清单——具体到文件、行号、
> 原文和改法——用来减少公式化写作痕迹、提高具体性。
> 交付：`factscribe/style.py`、`style-rules.toml`、`tests/test_style.py`（26 例）、
> 本文件（含对 `paper/` 与 `paper-zh/` 的零模型基线读数）。

## 批 67 修订（2026-11-08，本文件 §1/§5 的读数为批 64 存档）

盲评结论：批 64 的「长句＝坏」把文章改得更不像人（盲评改写胜率 4–13/17，
原文胜 12–13）。据结论改三处判据，本文其余章节保留批 64 存档读数：

1. `SENTENCE_LENGTH_EXTREME` 收窄：只报 **>60 词（英）/ >110 字（中）且句内
   没有任何从句、分号、破折号或括号断点** 的句子。长而有结构的长句是专家
   写法，不报；建议文案改为「保留结构，考虑在从句边界换气」，不再说「拆成
   短句」。
2. `SENTENCE_UNIFORMITY` 改为区间：健康区间 `[0.45, 0.80]`；`< 0.45` 报
   「太平」，`> 0.80` **不报**（散不是 AI 特征）。
3. 新增 `RHYTHM_PLATEAU`：同一段内连续 ≥3 句长度落在同一 10 词（字）区间
   即报黄，建议插入一句 8–15 词的短句或合并相邻两句。
4. `--prompt` 首行同步改为：优先保留结构与修辞，禁止整段拆短，只在
   `RHYTHM_PLATEAU` 处调节奏。

批 67 零模型基线（同一份 `paper/`、`paper-zh/`）：超长句 **4→0 / 3→0**
（旧标记全部因句内有结构而退休），节奏平台 **13 / 12** 处，CV 0.536 / 0.544。
按新规则改写后的读数、事实闸对比与盲评包见
`experiments/ctx-compiler-redblue/BATCH67-STYLE-V2.md`。

## 0. 定位（先看这里）

**本工具不评估、也不试图规避任何 AI 检测器。** 它检测的是「可机械判定的
公式化写作特征」：套话连接词、句长过齐、空泛形容词、三项并列、段末套话收尾、
双重模糊限定、相邻段同头、超长句。输出不是「像 AI」的分数，而是
`文件:行 + 原文 + 具体改法`。

- 只出**黄牌**：有触发时 `exit 3`，无触发 `exit 0`；**永不 `exit 1`**，
  不阻断构建、不改正文。
- `style` 是**独立子命令**。`check`/`audit` 的判据、红黄语义与退出码未动；
  既有 216 例测试原样通过（本批后总数 242）。
- 阈值全部来自 `style-rules.toml`（项目根优先，其次仓根，最后内置默认值）；
  改阈值会改判定，有测试锁定。

复现：

```bash
cd /Users/moc/workspaces/SiAgent/paperkit-dev
env PYTHONPATH=. python3 -m factscribe style ../paper
env PYTHONPATH=. python3 -m factscribe style ../paper --json
env PYTHONPATH=. python3 -m factscribe style ../paper --prompt
env PYTHONPATH=. python3 -m unittest discover -s tests          # 242 例
env PYTHONPATH=. python3 -m unittest discover -s tests -p "test_style.py"  # 26 例
```

## 1. 指标定义

统计口径：先把 LaTeX 转成等长、保留换行的纯正文（注释、宏定义体、公式、
图表/表格环境、文献表、verbatim、`\fact{}` 的 ID 参数、`\cite`/`\ref` 参数
全部抹成空格），再切句、切段。位置与源文件行号一一对应。

「词」的单位：英文按词；中文按字；混排时中文 1 字＝1 单元、英文 1 词＝1 单元。
密度类指标的分母是全文（闭包内所有章节）的单元总数。

| 代码 | 定义 | 默认阈值 | 触发方向 |
|---|---|---|---|
| `CONNECTIVE_DENSITY` | 每千词（字）套话连接词数：Moreover / Furthermore / Additionally / In addition / Overall / In conclusion / 首先 / 其次 / 此外 / 综上所述 / 总而言之 | `> 8` | 越高越差 |
| `SENTENCE_UNIFORMITY` | 句长（词/字）的总体标准差除以均值（burstiness 的倒数） | `< 0.45` | 越低越差 |
| `EMPTY_ADJECTIVE` | 每千词（字）空泛形容词数：crucial / robust / comprehensive / significant / essential / vital / 至关重要 / 显著 / 全面 / 深入 | `> 6` | 越高越差 |
| `TRIAD_DENSITY` | 每千词（字）三项并列数（`A, B, and C` / `A、B、C`） | `> 4` | 越高越差 |
| `PARAGRAPH_TEMPLATE` | 最后一句以 Therefore / Overall / Thus / In conclusion / 综上 / 因此 / 总之 / 总而言之 / 总体而言 **开头**的段落占比 | `> 0.5` | 越高越差 |
| `HEDGE_STACK` | 双重以上模糊限定出现次数（may potentially / 可能会 / 或许能够 …） | `>= 1` | 出现即报 |
| `REPEATED_OPENER` | 相邻段落首词相同的次数（跳过冠词/代词/介词等虚词） | `>= 2` | 达到即报 |
| `SENTENCE_LENGTH_EXTREME` | 单句超过 45 词（英）或 80 字（中） | `>= 1` | 每处都报 |

实现细节：

- **句长均匀度**：少于 10 句不判（短文本的 CV 无意义）；CV 越低越整齐。
- **段末套话**：只看最后一句的**句首**，句中出现的 therefore/因此不算。
- **相邻段同头**：跨文件不算相邻；`the/a/an/we/如果/因此…` 等虚词开头不报，
  避免正常学术写作被大量误伤（这是相对任务书的窄化，已写进 `style-rules.toml`）。
- **三项并列**：英文要求三项都是名词短语式短组；第三项以 because/which/while
  等从句引导词开头、或组内夹 and/or 的匹配丢弃，减少「A, B, and because…」误报。
- **空泛形容词**：`statistically significant`、`robust to`、`more robust` 等
  术语搭配进 `exempt_phrases`，不算空泛。
- **超长句**：中文句按汉字数判，英文句按词数判；句中有中文且汉字数不少于
  英文词数时按中文口径。

## 2. 阈值依据

这些是**工程默认值**，不是从「AI 文本 vs 人写文本」语料上拟合出来的检测阈值，
也没有任何检测器分数含义：

- 连接词 `8/千词` ≈ 每 125 词一个套话连接词；超过后段落会明显呈模板状。
- 句长 CV `< 0.45`：正常经过编辑的学术散文通常有明显长短起伏；CV 低于
  0.45 表示句长过度集中（burstiness 低）。
- 空泛形容词 `6/千词` ≈ 每 165 词一个；连续出现会稀释具体信息。
- 三项并列 `4/千词` ≈ 每 250 词一组；正常论文会有列表，但高频「三件套」
  是典型的公式化节奏。
- 段末模板 `> 0.5`：超过一半段落用总结连接词收尾，说明段落在按模板走。
- 双重限定、相邻段同头是局部缺陷，出现 1 次/2 次即值得看一眼。
- 45 词 / 80 字是常见可读性上限，超过通常需要断句。

保守性优先：故意让正常学术散文落在阈值内（见 §6 的负例测试与 §5 的真实
论文读数）。所有阈值、词表、豁免短语、每指标最多列几条都在
`style-rules.toml` 里，可逐项覆盖。

## 3. 输出形态

### 人读报告

```text
== factscribe style ==
project : ../paper
正文    : 18 个文件，6390 词/字，368 句，90 段
规则    : .../style-rules.toml

注意：本工具不评估、也不试图规避任何 AI 检测器；……

指标                    读数      阈值     状态
CONNECTIVE_DENSITY       0         8        ok
SENTENCE_UNIFORMITY      0.536     0.45     ok
...
SENTENCE_LENGTH_EXTREME  4         45/80    触发

[黄] 4 处具体改法（只提示，不阻断；退出码 3）
  1. SENTENCE_LENGTH_EXTREME sections/00_abstract.tex:3
     原文：We treat the prompt as a compiled artifact instead: ...
     改法：这句 49 词超过 45：在逗号或 and 处断成两句（例：...）
...
说明：本闸只报「可机械判定的公式化写法」，不评估、也不试图规避任何 AI 检测器。
```

### `--json`

顶层键：`metrics`、`thresholds`、`findings`、`paragraphs`、`fired`、
`summary`、`disclaimer`、`rules`（另有工具统一的 `tool`/`command`/`exit` 等）。

```json
{"metrics": {"connective_density": 0.0, "sentence_uniformity": 0.536,
             "empty_adjective": 0.0, "triad_density": 1.88,
             "paragraph_template": 0.0, "hedge_stack": 0,
             "repeated_opener": 0, "sentence_length_extreme": 4},
 "thresholds": {"connective_density": 8.0, "sentence_uniformity": 0.45,
                "empty_adjective": 6.0, "triad_density": 4.0,
                "paragraph_template": 0.5, "hedge_stack": 1,
                "repeated_opener": 2, "sentence_length_extreme_en": 45,
                "sentence_length_extreme_zh": 80},
 "findings": [{"code": "SENTENCE_LENGTH_EXTREME",
               "file": "sections/00_abstract.tex", "line": 3,
               "text": "We treat the prompt as a compiled artifact instead: ...",
               "suggestion": "这句 49 词超过 45：在逗号或 and 处断成两句（例：...）"}],
 "paragraphs": [{"file": "sections/01_intro.tex", "line": 23, "words": 165,
                 "flags": ["PARAGRAPH_TEMPLATE"]}],
 "fired": [{"code": "SENTENCE_LENGTH_EXTREME", "metric": "sentence_length_extreme",
            "value": 4, "threshold": 1, "direction": "at_least"}]}
```

`findings` 只列**触发指标**的具体条目（每指标默认最多 20 条），不是把全文
所有候选都倒出来；`paragraphs` 是段级概览，`flags` 标出该段命中的段级特征。

### `--prompt`（给 LLM 的改写指令，≤ 400 字）

真实输出（对 `paper/`，385 字）：

```text
只改下列标记句；不改事实、数字、引用；不得删数字、不得删引用、不得整段删除。逐条处理后重新提交。
1. 00_abstract.tex:3 「We treat the prompt as a compiled…」→ 这句 49 词超过 45：在逗号或 and 处断成两句（例：We treat the pr…
2. 02_related.tex:16 「We therefore spend a fixed budget…」→ 这句 51 词超过 45：在逗号或 and 处断成两句（例：We therefore sp…
3. 04_mechanisms.tex:92 「We first wrote the required proce…」→ 这句 54 词超过 45：在逗号或 and 处断成两句（例：We first wrote…
（共 4 处，先改前 3 处。）
```

生成规则：先按指标各取一条保证覆盖面，再按严重度补；逐条加入「文件:行
原文 → 改法」，超出 400 字就停并注明「共 N 处，先改前 K 处」。禁用项
（不得删数字/引用/整段）固定写在首行。无触发时只输出一句「不要为改写而改写」。

## 4. 阈值与词表的配置

`style-rules.toml` 四段：

```toml
[thresholds]        # 全部阈值：7 个指标阈值 + 英文/中文超长句上限
[limits]            # max_findings_per_metric / min_paragraph_units / uniformity_min_sentences
[connectives] ...   # 英文/中文词表
[empty_adjectives]  # 词表 + exempt_phrases
[paragraph_closers] # 段末收尾词
[hedge_stacks]      # 双重限定短语
[repeated_opener]   # stopwords（虚词开头不报）
```

查找顺序：`--rules <path>` → `<project>/style-rules.toml` → 仓根
`style-rules.toml` → 内置默认值。显式路径不存在是配置错（exit 2）；
数值类型/负数校验失败也是 exit 2。

## 5. 零模型基线：`paper/` 与 `paper-zh/`

统计对象是审计闭包内的全部 `.tex`（含附录与 `\input` 拉入的表文件；表体
在 `tabular` 环境里被遮掉，不进入句子统计）。英文 6390 词、368 句、90 段；
中文 10059 字、390 句、91 段。**注意**：任务书给的 7012 词是另一种统计口径
（含 caption/表格/公式参数等）；本闸只统计参与文风判断的正文单元。

### 5.1 指标读数

| 指标 | 英文稿 `paper/` | 中文稿 `paper-zh/` | 阈值 | 状态 |
|---|---:|---:|---:|---|
| `CONNECTIVE_DENSITY` | 0.00（0 处） | 0.10（1 处） | > 8 | ok |
| `SENTENCE_UNIFORMITY` | 0.536 | 0.544 | < 0.45 | ok |
| `EMPTY_ADJECTIVE` | 0.00（0 处） | 0.00（0 处） | > 6 | ok |
| `TRIAD_DENSITY` | 1.88（12 处） | 2.58（26 处） | > 4 | ok |
| `PARAGRAPH_TEMPLATE` | 0.000（0/90） | 0.044（4/91） | > 0.5 | ok |
| `HEDGE_STACK` | 0（0 处） | 0（0 处） | ≥ 1 | ok |
| `REPEATED_OPENER` | 0（0 处） | 0（0 处） | ≥ 2 | ok |
| `SENTENCE_LENGTH_EXTREME` | **4 处** | **3 处** | ≥ 1 | **触发** |

两篇都只有 `SENTENCE_LENGTH_EXTREME` 越线，`exit 3`；其余七项全部在阈值内。

### 5.2 每项最严重的 3 处

英文稿 `paper/`：

| 指标 | 最严重 3 处（文件:行，原文） |
|---|---|
| `CONNECTIVE_DENSITY` | —（0 处） |
| `SENTENCE_UNIFORMITY` | 全文 CV=0.536（均值 17.3，标准差 9.3，最短 3 词 `sections/07_threats.tex:16`，最长 54 词 `sections/04_mechanisms.tex:92`） |
| `EMPTY_ADJECTIVE` | —（0 处） |
| `TRIAD_DENSITY` | `sections/07_threats.tex:20`（同段 2 处）"There is no repetition, no seed control, and no second machine"；`sections/01_intro.tex:3` "cause of a failure, edit, and verify"；`sections/01_intro.tex:19` "locator card was assembled, counted against its budget, and reported as delivered" |
| `PARAGRAPH_TEMPLATE` | —（0 处） |
| `HEDGE_STACK` | —（0 处） |
| `REPEATED_OPENER` | —（0 处） |
| `SENTENCE_LENGTH_EXTREME` | `sections/04_mechanisms.tex:92`（54 词）"We first wrote the required process as six constraints --- …"；`sections/06_ablation.tex:13`（53 词）同句式；`sections/02_related.tex:16`（51 词）"We therefore spend a fixed budget on evidence …" |

中文稿 `paper-zh/`：

| 指标 | 最严重 3 处（文件:行，原文） |
|---|---|
| `CONNECTIVE_DENSITY` | `sections/04_mechanisms.tex:33` "此外摘录是原始运行器文本，格式一变就会得到空载荷……"（唯一 1 处） |
| `SENTENCE_UNIFORMITY` | 全文 CV=0.544（均值 25.8，标准差 14.0，最短 2 字 `sections/01_intro.tex:12`，最长 88 字 `sections/04_mechanisms.tex:39`） |
| `EMPTY_ADJECTIVE` | —（0 处） |
| `TRIAD_DENSITY` | `sections/03_system.tex:8`（同段 4 处）"章程、任务、意图"；`sections/03_system.tex:9`（2 处）"每种小节都声明它的来源、加载方式、信任级别"；`sections/04_mechanisms.tex:10`（2 处）"候选按符号名中的任务词、匹配强度、跳数与定义行排序" |
| `PARAGRAPH_TEMPLATE` | `appendix/c_debuglog.tex:10` "因此卡片那一行在墙钟顺序上晚于容量那几行……"；`sections/01_intro.tex:23` "因此我们不再相信装配器自己的日志……"；`sections/05_eval.tex:8` "因此这个子集比随机抽样更容易……"（共 4/91 段） |
| `HEDGE_STACK` | —（0 处） |
| `REPEATED_OPENER` | —（0 处；去掉虚词开头后） |
| `SENTENCE_LENGTH_EXTREME` | `sections/04_mechanisms.tex:39`（88 字）"我们先把要求的流程写成六条约束——……"；`sections/06_ablation.tex:13`（87 字）同句式；`sections/00_abstract.tex:8`（86 字）"我们把提示词当作编译产物来对待：……" |

### 5.3 一句话诊断

**英文稿**：按本闸的阈值口径，最像 AI 的三项依次是
① 超长句（4 处，唯一越线；54/53/51 词的三句都是「六条约束」式长列举）、
② 句长均匀度（CV 0.536，距 0.45 的阈值只差 0.086）、
③ 三项并列密度（1.88/千词，约为阈值的一半）。
连接词、空泛形容词、段末套话、双重限定、段落同头五项全为 0——稿子的主要
问题不是「AI 味词汇」，而是长句和并列节奏。

**中文稿**：最像 AI 的三项依次是
① 超长句（3 处，88/87/86 字，全部集中在「六条约束」的整段复述与摘要长句）、
② 句长均匀度（CV 0.544，距阈值 0.094）、
③ 三项并列密度（2.58/千词，约为阈值的 65%，主要来自系统章节的小节/来源枚举）。
连接词只有 1 处「此外」，空泛形容词、双重限定、段落同头为 0；段末「因此」
收尾占 4.4%，远低于 0.5。中文稿的公式化风险同样主要是长句与高频枚举，
不是套话词汇。

> 判读提醒：`SENTENCE_LENGTH_EXTREME` 是**可读性**指标，不是「AI 证据」；
> 本闸没有、也不试图给出任何 AI 检测结论。上表只说明「按这八条机械规则，
> 哪些地方值得改写」。

## 6. 测试（26 例）

`tests/test_style.py`：

- 8 个指标各 1 正 1 负（16 例）：构造小文本，断言命中/不命中与读数方向；
- 阈值可配（2 例）：把 `connective_density` 提到 1000 后不再触发；把
  `triad_density` 提到 1000 后三元组不再触发；默认配置下同一文本触发；
- 中文支持（1 例）：连接词、空泛形容词、双重限定、超长句四项同时命中；
- 不误伤（2 例）：3 段正常学术段落零 findings、零 fired、exit 0；LaTeX
  遮罩不把 `\citep`/`\ref`/公式内容算进正文；
- CLI（5 例）：exit 3 与 JSON 顶层键、干净项目 exit 0、`--prompt` ≤400 字且
  含禁用项与「→」、`--prompt --json` 内嵌 prompt、paragraphs 字段形状。

全量回归：`env PYTHONPATH=. python3 -m unittest discover -s tests` → **242 例全绿**
（原 216 + 新 26）。`audit`/`check` 的既有判据与退出码未改。

## 7. 已知边界

- 只做**句/段级表面特征**，不判断论证质量、事实正确性或「是否 AI 生成」。
- 三项并列用正则识别，仍可能把「A, B, and C」式的三连从句算进去；宁多报
  一条提示，不静默漏掉（但阈值会过滤低频噪声）。
- 中文按字计，未做分词；`REPEATED_OPENER` 的中文首词取前 4 个汉字，靠
  虚词表抑制误报，不等同于语言学上的「词」。
- 句切分沿用 `texscan.sentence_spans`，分号也会断句；这是既有审计的切句口径，
  本闸不另造一套。
- 报告里的「词」是正文单元，不等于 Word/LaTeX 的字数统计；与外部字数不一致
  属预期。
- 本闸不修改任何文件；`--prompt` 只是给调用方（人或 LLM）的文本。
