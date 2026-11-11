# SPEC-READABILITY｜读者感觉三项的代理判据（批 129）

> 状态：**冻结**（批 129；批 130 修订 §1.4，新增 §1.5「开关只能在被测物
> 之外」）。本件规定 `style` 里三条「读者感觉」判据的口径、
> 阈值、排除面与处方映射。三条都只出黄牌（`exit 3`），不阻断、不改正文；
> 不新增 `audit` / `protect` / `review` 的判据，也不改变它们的退出码。

## 0. 为什么需要代理判据

一次起草实验给出三条读者评价：

1. 数字太密，读者记不住，也没有推进论点；
2. 末段与 Limitations 重复；
3. 通篇「我们做了什么」多于「这意味着什么」。

这三条此前被判「机器判不了」。它们确实不能由机器判断「读起来好不好」，
但可以拆成**可机械复算的代理量**：数字 token 密度、节间字面片段重合率、
「主语＋动作动词」句占比。代理量只负责指出可疑位置，取舍仍由写作者做。

三条都是**黄牌**：命中只进 `findings`，退出码仍是 `3`；不命中退出 `0`。
`style --diff` 的「只报新增」逻辑对三条同样生效。

## 1. `NUMERAL_DENSITY`

### 1.1 定义

- 分子：一节正文里的**阿拉伯数字 token** 数。正则
  `\d+(?:[.,]\d+)*`：整数、小数、千分位各算一个 token；`5/24` 算两个。
- 分母：英文按**每千词**、中文按**每千汉字**；混排时按该节里 CJK 字数与
  拉丁词数较多的一侧选单位。
- 密度 `X = 数字 token 数 × 1000 ÷ 分母`。
- 默认阈值 `40`，可配（`[thresholds].numeral_density`）。
- 触发条件：`X > 阈值`（**严格大于**；正好 40 不报）。
- 主文件（`root_tex`）若是只 `\input` 别的文件的容器，跳过——容器不是一节。

### 1.2 报时格式

每条命中必须给出：

```
本节 N 个数字 / 阈值 M / 密度 X/千词（或 千汉字）
```

并在 `metric_details.numeral_density_sections` 里逐节列出
`numerals / units / unit / density / threshold`。

### 1.3 排除面

`prose_of` 已排除：`\fact` ID、`\cite` 家族、公式环境、LaTeX 命令、
图表与文献表、注释与写作批注。`\fact{ID}{渲染数字}` 的第二个参数是正文
数字，保留计数。表格与图里的数字不进正文统计。

### 1.4 与改写保护面的冲突（一等公民）

删数字会触发 `PROTECT_NUMBER_CHANGED`。因此本判据按**阶段**分档：

- 阶段开关 `style --stage draft|revision`，默认 `draft`：
  - `draft`：正常判定；
  - `revision`：读数照算，命中降为 `info`（`severity="info"`），
    不进 `findings`、不改退出码，建议文字明写
    「改稿阶段数字受 `PROTECT_NUMBER_CHANGED` 保护，本条只报告」。
- **开关只能从命令行来（批 130）**：`numeral_density_stage` 写在项目内
  `style-rules.toml` 里**不生效**，只输出一条 `RULES_OVERRIDE_IGNORED`
  告警并列出被忽略的键。`style` 无法知道项目是否正在验收，但它能保证
  「被判据管的正文／被测项目」改不动判据开关；阶段由运行方在命令行声明。

### 1.5 原则：开关只能在被测物之外（批 130）

一次实测暴露了绕过面：模型没改正文，只在项目根新建 `style-rules.toml`
写 `numeral_density_stage = "off"`，`NUMERAL_DENSITY` 就降级成 `info`，
检查消失；它还引用我们的文档说「改稿阶段就该关」——**照文档做，结果绕过
了检查**。

由此立一条通用原则：

> 判据的开关、阈值口径与「是否接受检查」不得由被测物自己声明。
> 被测物只能提供**判据要读的材料**（词表、阈值），不能提供**判据的
> 开关**（开/关、阶段、跳过）。

落地方式：

- 阶段类开关只从命令行来（`--stage`）；项目内写了不认并报
  `RULES_OVERRIDE_IGNORED`；
- 普通配置键（词表、阈值）仍可覆盖——它们是「按本项目口径判」，
  不是「不判」；
- 项目规则文件被改动要**看得见**：`style` / `review` / `audit` 读到
  项目内 `style-rules.toml` 时逐键与内置默认比较，输出
  「本项目覆盖了 N 个规则键」并列出键名。覆盖是收紧还是放宽机器无法
  判断，所以只列键名、不评判；这一行 informational，不进 findings。

## 2. `SECTION_OVERLAP`

### 2.1 定义

- 把每篇按标题（`\section` / `\subsection` / Markdown 标题）拆成节/小节块；
  标题本身在 `prose` 里已遮罩，块内只含正文。
- 每块切成片段：英文 **8 个连续词**，中文 **12 个连续汉字**；大小写归一，
  标点不参与。数字与拉丁词不混入中文片段。
- 两块的**重合率** `R = 共有片段数 ÷ 两节中较短一节的片段数 × 100%`。
  取较短一节为分母，避免长节把短节的整段重复稀释掉。
- 默认阈值 `12%`，可配（`[thresholds].section_overlap`）。
- 触发条件：`R > 阈值`。片段数少于 `20` 的块不判（单句引用同一事实会因
  分母太小被误判成重复）。
- 主文件若是容器，跳过。

### 2.2 报时格式

每条命中必须给出：

- 「本节与 X 节重复」；
- 重合率与阈值；
- 本节的行号与对方节的行号；
- 一条共有片段原文，便于人核对。

`metric_details.section_overlap_pairs` 逐对列出
`file / section / other_file / other_section / rate / line / other_line /
shared_shingles / denominator`。

### 2.3 排除面与「正常引用同一事实」

`prose_of` 排除 `\fact`、引用、公式与 LaTeX 命令后，片段只由正文词/字
组成。**只引用同一事实一次**（例如两节都提「门槛 10/12」）通常只产生
几个共有片段；只要两节各自有独立正文，重合率会远低于 12%，不报。
「真重复」是整段近乎相同，重合率显著高于 12%。

本判据只认**字面片段**，不认语义改写：把同一段换成同义词不算重复。
这是代理判据的已知边界，见 §4。

## 3. `WE_ACTION_DENSITY`

### 3.1 定义

- 分子：主语是 `we` / `我们`，且谓语是**动作动词**的句子数。
- 动作动词表（可配 `[we_action]`）：英文 `ran/run/did/do/tried/try/
  changed/change/added/add/removed/remove/tested/test/looked/look`
  及常见屈折；中文 `跑/做/试/改/加/删/测/查/记` 及
  `尝试/修改/增加/添加/删除/运行/测试/测量/检查/记录/核对/查验`。
- **只认动作动词**：`we propose` / `we claim` / `we argue` / `we believe`
  /「我们提出」/「我们主张」/「我们认为」不算。
- 主语与谓语之间允许副词/助动词：`We then ran`、`We have tested`、
  `我们随后跑了`。`do/does/did` 后跟 `not/never` 时按助动词处理，不计。
- 分母：全部句子的数量（与 `summary.sentences` 同源；只算段长达到
  `min_paragraph_units` 的段落里的句子）。
- 默认阈值 `0.15`，可配（`[thresholds].we_action_density`）。
- 触发条件：`占比 > 阈值`（严格大于；正好 15% 不报）。

### 3.2 报时格式

命中时出一条汇总：

```
动作句 H / 总句 N = P%（阈值 T%）
```

`metric_details.we_action_density` 给出 `hits / sentences / ratio` 与前
10 条例句（文件、行、命中的动词、原句）。

## 4. 已知边界（代理判据不承诺的事）

- **数字密度不区分「结果节」与「叙事节」**：结果节的数字就是内容，
  40/千词的阈值可能偏严；误报要在人读时排除，不能为过判据删结果数字。
- **节间重合只认字面片段**：同义改写造成的语义重复抓不到；字面重复但
  论证不同（例如两节都复述同一组必要前提）可能误报。
- **动作句只认词表**：`we built`、`we wrote` 不在默认表内就不计；
  词表可配，但扩表会改变读数，改表即改判据。
- 三条都不判断「论证好不好」；它们只把可疑位置排到人眼前。

## 5. 处方映射

| 判据 | 处方 | 一句话 |
|---|---|---|
| `NUMERAL_DENSITY` | `thin-the-numbers` | 只在起草阶段用；每个论点只留一条证据 |
| `SECTION_OVERLAP` | `merge-overlap` | 把重复段落并进被引用的那一节，保留本节独有结论 |
| `WE_ACTION_DENSITY` | `shift-to-implication` | 把「我们做了 X」改成「X 意味着 Y」 |

三条处方都是六段结构，原文在 `factscribe/patterns/<name>/RULE.md`；
`polish --plan` 按 `priority.toml` 把命中映射到处方。

## 6. 验收

```bash
env PYTHONPATH=src python3 -m unittest discover -s tests
./scripts/preflight-ci.sh
```

真材料复核：

```bash
python3 -m factscribe style <项目目录> --json
python3 -m factscribe polish --plan <项目目录>
```

测试 `tests/test_readability_rules.py` ≥15 例，覆盖三条各自正例/负例/
阈值边界、中英各一组、`SECTION_OVERLAP` 的「真重复」与「正常引用同一
事实」、`we propose` 不计入、`polish --plan` 三条映射。
