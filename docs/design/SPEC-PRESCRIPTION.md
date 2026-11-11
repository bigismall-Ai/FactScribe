# SPEC-PRESCRIPTION｜处方层（只给怎么改，不参与判据）

> 状态：**冻结**（批 92）。本件规定 `factscribe prescribe` 子命令与
> `factscribe/patterns/` 的数据契约。
>
> 处方层**不改** `audit` / `style` / `protect` 的判据与退出码，**不产生分数**，
> **不写 findings**。它只回答一个问题：已知这条判据被触发，下一步该怎么改。

## 0. 为什么要有这一层

闸门只会说「这里有问题」，不说「该怎么改」。结果改写方（人或模型）自己发明
改法，实测改出 6 处退步：复述标题、删掉对比对象、用垫话冒充定义、把破折号
换成另一个破折号、替换标题关系词、首段只交代任务不给结论。

处方层把这些改法**固定成数据文件**：

- 只给已经验证过的改法；
- 把已知坏改法写成「禁做＋反例」；
- 每条处方绑定它治的错误码，可按码查；
- 处方之间冲突时，按固定优先序裁决，被压制的处方明写「让位」。

## 1. 数据形态：处方是数据，不是代码

落位：

```
factscribe/patterns/<name>/RULE.md
```

UTF-8、Markdown，六段固定结构（顺序固定，缺一段即配置错）：

```markdown
# 名称
## 治的判据
## 必做
## 禁做（含反例）
## 改写示例（旧 → 新）
## 验收命令
```

| 段 | 内容 | 机器约定 |
|---|---|---|
| `# 名称` | 处方显示名（可带一句副题） | 必须存在且非空 |
| `## 治的判据` | 这条处方治什么现象、绑定哪个错误码 | 见 §1.1 |
| `## 必做` | 改写的硬要求，逐条可核对 | 纯文本 |
| `## 禁做（含反例）` | 已知坏改法，**至少一条反例** | 必须出现「反例」二字 |
| `## 改写示例（旧 → 新）` | 旧写法与新写法的对照 | 必须同时出现「旧」与「新」 |
| `## 验收命令` | 改完怎么验 | 第一块围栏代码必须可直接跑，见 §1.2 |

### 1.1 错误码声明（`--for` 的唯一依据）

「治的判据」段里，以下面这种**条目行**声明绑定：

```markdown
- 错误码：HEADING_ECHO
- 错误码：TERM_FIRST_IN_HEADING
```

- 只有以 `- 错误码：`（或 `* 错误码:`）开头的行参与机器绑定；
- 同一段里其它地方提到的码（例如「与 `HEADING_SUBJECT_LOST` 冲突时让位」）
  **不算绑定**，避免散文里的顺带提及污染 `--for`；
- 每条处方至少绑定一个码，否则加载期报配置错（退出码 2）；
- 码的形态是 `UPPER_SNAKE`。现有判据码之外，处方层允许一个自有检查码
  `SECTION_INCOMPLETE`（`style` 不产生它，见 §5.6）。

### 1.2 验收命令必须真能跑

「验收命令」段的**第一块围栏代码**是处方自检命令，必须满足：

- 在仓根直接执行，不依赖临时目录、不依赖网络；
- 退出码为 `0` 或 `3`；
- 输出只含处方内容或 JSON。

改写落地后的复核命令可以写占位符（如 `<项目>`、`<改前目录>`），由人替换；
测试只执行第一块，不执行占位符命令。

## 2. 与判据严格分离（硬约束）

1. `factscribe/prescribe.py` **不 import** `style.py` / `terms.py` / `tide.py`；
   反向也不 import 处方层。
2. 处方**不产生** `Finding`；不进入 `style --json` 的 `findings` / `info` /
   `paragraphs` / `fired`，不影响 `style` 的计数与退出码。
3. `prescribe` 的退出码只有两种：成功 `0`、用法/配置错 `2`。永不返回
   `1`（红）、`3`（黄）、`4` / `5` / `7` / `8`。
4. 处方不写正文、不做替换、不保存任何「分数 / 等级 / 通过率」字段。

证明落在 `tests/test_prescription.py`：

- 跑 `style` 后断言 findings 里没有任何处方名或处方段落文字，且码集合仍在
  `style` 既有码内；
- 子进程跑 `style` 后断言 `factscribe.prescribe` **没有被导入**；
- 断言 `prescribe --json` 的载荷没有 `findings` / `score` 字段，退出码为 `0`。

## 3. 冲突优先序（一等公民）

固定五级，序号小的胜：

| 序号 | 级别 | 名称 | 管什么 |
|---|---|---|---|
| 1 | `facts` | 事实与数字 | 事实、数字、引用、公式、表格不许因改写而变化 |
| 2 | `structure` | 结构完整 | 对比对象、主语、章节论证结构必须完整 |
| 3 | `heading` | 标题指向内容 | 标题要短、要指向本节内容，但不许牺牲结构 |
| 4 | `term` | 术语首现解释 | 术语首次出现要给定义或可检验断言 |
| 5 | `style` | 文句风格 | 破折号、节奏、连接词等文句层面偏好 |

规则：

- 每条处方在 `factscribe/patterns/priority.toml` 的 `[ranks]` 里登记一个级别；
- 冲突对在 `[[conflicts]]` 里**显式登记**，不自动推断；
- 同一冲突对的两端必须落在不同序号（加载期校验，违反即退出码 2）；
- 同时输出两条冲突处方时：序号小的胜；**被压制的一条必须在输出里写
  「让位」**，格式：

  ```
  让位：与 <winner> 冲突（<reason>）；按优先序 <n> < <m> 让位，本处方不执行。
  ```

- 只输出单条处方时不写「让位」（没有对手在场，不制造假冲突）。

配置落位 `factscribe/patterns/priority.toml`：

```toml
[levels]
facts = 1
structure = 2
heading = 3
term = 4
style = 5

[names]
facts = "事实与数字"
structure = "结构完整"
heading = "标题指向内容"
term = "术语首现解释"
style = "文句风格"

[ranks]
heading-shorten = "heading"
heading-subject-keep = "structure"
heading-malformed = "heading"
section-completeness = "structure"
term-first-sentence = "term"
dash-rewrite = "style"

[[conflicts]]
a = "heading-shorten"
b = "heading-subject-keep"
reason = "压标题不得丢掉对比对象与主语"

[[conflicts]]
a = "heading-malformed"
b = "heading-subject-keep"
reason = "去标题标点不得删掉对比对象或替换关系词"
```

## 4. CLI

```
python3 -m factscribe prescribe <name|--list> [--for <错误码>] [--json]
```

| 用法 | 行为 | stdout |
|---|---|---|
| `prescribe --list` | 列出全部处方 | 清单（名 / 绑定的码 / 优先序 / 一句摘要） |
| `prescribe --list --json` | 同上，机器可读 | 单个 JSON |
| `prescribe <name>` | 输出该处方原文 | 只出处方原文，逐字节等同 `RULE.md` 去尾空白 |
| `prescribe <name> --json` | 同上，带结构化字段 | 单个 JSON |
| `prescribe --for <CODE>` | 输出所有绑定该码的处方 | 处方原文；有冲突时附「让位」 |
| `prescribe --for <CODE> --json` | 同上 | 单个 JSON（含 `conflicts` / `suppressed`） |
| `prescribe <a> <b>` | 一次输出多条，用于看冲突裁决 | 按优先序输出；被压制者带「让位」 |

退出码：

- `0`：成功（包括「没有处方治这个码」——这是合法结果，不是错误）；
- `2`：缺参数、未知处方名、处方文件缺段、优先序配置非法。

`--json` 的载荷只含处方数据与元信息，不含 `findings`、不含分数：

```json
{
  "schema_version": "1.0",
  "tool": "factscribe",
  "version": "1.2.0",
  "command": "prescribe",
  "status": "ok",
  "severity": "ok",
  "exit": 0,
  "prescriptions": [
    {
      "name": "heading-shorten",
      "title": "heading-shorten｜压标题长度（保留对比对象与主语）",
      "target_codes": ["HEADING_TOO_LONG"],
      "priority": {"level": "heading", "number": 3, "label": "标题指向内容"},
      "sections": {"治的判据": "...", "必做": "...", "禁做（含反例）": "...",
                   "改写示例（旧 → 新）": "...", "验收命令": "..."},
      "fields": {"名称": "...", "治的判据": "...", "必做": "...",
                 "禁做（含反例）": "...", "改写示例（旧 → 新）": "...",
                 "验收命令": "..."},
      "path": "factscribe/patterns/heading-shorten/RULE.md"
    }
  ],
  "conflicts": [],
  "suppressed": {},
  "note": "处方层不参与判据、不产生分数；style 的 findings 与退出码不受影响。"
}
```

## 5. 十条处方

| # | 名称 | 治的判据（错误码） | 优先序 | 一句话 |
|---|---|---|---|---|
| 1 | `heading-shorten` | `HEADING_TOO_LONG` | 3 标题指向内容 | 压标题长度，保留对比对象与主语 |
| 2 | `term-first-sentence` | `HEADING_ECHO`、`TERM_FIRST_IN_HEADING` | 4 术语首现解释 | 首句给定义或可检验断言，禁复述/垫话/设问 |
| 3 | `dash-rewrite` | `DASH_PARENTHETICAL` | 5 文句风格 | 插入语破折号改逗号从属句 / 括号 / 拆句 |
| 4 | `heading-malformed` | `HEADING_MALFORMED`、`HEADING_RELATION_CHANGED` | 3 标题指向内容 | 去冒号/问号/句号，但不许替换关系词 |
| 5 | `heading-subject-keep` | `HEADING_SUBJECT_LOST`、`HEADING_RELATION_CHANGED` | 2 结构完整 | 对比结构改写后，第二个对象必须还在 |
| 6 | `section-completeness` | `SECTION_INCOMPLETE` | 2 结构完整 | 每节首段交代「本节做什么、结论是什么」 |
| 7 | `drop-the-proof` | `EXPLAINER_DENSITY`、`JUSTIFY_CHAIN` | 5 文句风格 | 删掉反射式解释，让断言自己站住 |
| 8 | `unbury-the-verb` | `LIGHT_VERB_NOMINALIZATION` | 5 文句风格 | 把埋进名词的动作挖回动词 |
| 9 | `cut-the-de` | `ZH_DE_STACK` | 5 文句风格 | 拆掉单句里的「的」链 |
| 10 | `trim-to-budget` | `SECTION_LENGTH` | 5 文句风格 | 先删重复的数字、再删举例、最后合并同义句；论点与证据不许动 |

### 5.1 `heading-shorten`

反例是 `提示词对机制` → `提示词`：压短时把「机制」这个对比对象删掉了。
本处方只许删修饰语、解释性从句、括号补充与重复限定；压不下就换短名词短语，
不许删论证对象与主语。

### 5.2 `term-first-sentence`

首句必须给出「属概念＋区别特征」的定义，或给出可检验断言；反例包括复述标题
（「本节讨论预注册」）、垫话（「相关工作里，……」）、纯设问（「什么是预注册？」）。
判据是 `HEADING_ECHO` 与 `TERM_FIRST_IN_HEADING`。

### 5.3 `dash-rewrite`

插入语破折号按序改：① 逗号从属句；② 括号；③ 拆成独立一句。禁做是「换成
另一个破折号」（en dash / em dash / 双 hyphen 都算），以及顺手删掉插入语里的
事实或数字。

### 5.4 `heading-malformed`

去掉标题里的冒号、问号、句号、破折号与括号解释，把解释移到正文首句。禁做是
**替换关系词**：反例 `Prompt versus mechanism` → `Prompt or mechanism`
（versus 是对立，or 是选择，论证方向被改掉）。

### 5.5 `heading-subject-keep`

对比结构改写后，旧标题里的每个对象必须出现在**新标题或本节首句**；关系词保留
或只在同义组内替换（versus / vs / 对；not / 不是；without / 而非）。反例仍是
`提示词对机制` → `提示词`。

### 5.6 `section-completeness`

每节首段要同时交代两件事：本节做什么（任务句）、本节结论是什么（可复述的
断言句）。结论要落到「对象＋条件＋结果」，不能是「效果很好」这类空泛评价，
也不能用「详见下文」代替。

检查点**转述**自 XtraGPT 的 20 条学术写作标准中与章节组织相关的项（不抄原文
措辞）：

- 每节首段先给本节任务，再给本节结论；
- 段内顺序是任务 → 方法/证据 → 结论，不先铺三段背景；
- 一节只承担一个论证任务，新任务另起一节；
- 结论必须可复述、可检验，有明确对象与条件；
- 首段不重复上一节结论，也不复述标题；
- 节末不引入新任务。

`SECTION_INCOMPLETE` 是处方层自有的检查码：`style` 不产生它，处方层也不反过来
给 `style` 增加判据。它只用于把「本节缺结论」与「首句复述标题」区分开。

### 5.7 `drop-the-proof`

治「每句都跟一个证明」的答辩腔（`EXPLAINER_DENSITY`、`JUSTIFY_CHAIN`，
判据见 `SPEC-EXPLAINER.md`）。必做三件：让一半断言独立成立；把证据挪到
真正需要它的地方；一段最多解释一次。禁做是**把解释句改成同义的另一句
解释**——那只是换词，反射还在。

反例（旧 → 新）：

```
旧  数字全对，结论照样可能是错的。这是最常见的一种误会。
新  数字全对，结论照样可能是错的。
```

验收命令：

```bash
env PYTHONPATH=src python3 -m factscribe prescribe drop-the-proof --json
```

### 5.8 `unbury-the-verb`

治「轻动词＋名义化」（`make a distinction`、`perform an analysis`，
判据见 `SPEC-SYNTAX.md` §1）。必做是先把名词背后的动作找出来
（distinction → distinguish），再把动作写成动词、把施动者放回主语。
禁做是**换一个轻动词**（`make a decision` → `take a decision`，动作仍在
名词里），或者为了去名词删掉宾语与限定。

反例（旧 → 新）：

```
旧  We make a distinction between the two runtime paths.
新  We distinguish the two runtime paths.
```

验收命令：

```bash
env PYTHONPATH=src python3 -m factscribe prescribe unbury-the-verb --json
```

### 5.9 `cut-the-de`

治单句连续短修饰链（相邻两个「的」间隔 ≤6 字，且至少两对连续成立，
判据见 `SPEC-SYNTAX.md` §2）。必做是先找中心词，再把定语改写成动词句
或短句：`A 的 B 的 C` → `C 由 B 做，B 属于 A`。禁做是**把「的」换成
另一个虚词**（「之」）硬撑，或者为了少一个「的」删掉定语里的读数与限定。

反例（旧 → 新）：

```
旧  最后一臂的 5/5 是一个任务的五次运行，而不成功的那些臂是更小的集合。
新  最后一臂在 5/5 上通过；那是一个任务的五次运行。不成功的臂则是更小的集合。
```

验收命令：

```bash
env PYTHONPATH=src python3 -m factscribe prescribe cut-the-de --json
```

### 5.10 `trim-to-budget`

治「本节写超预算」（`SECTION_LENGTH`，配置与判据见 `SPEC-BUDGET.md`）。
必做按顺序：**先删重复引用的数字 → 再删举例 → 最后合并同义句**。禁做三条：
不删论点、不删每个论点的最后一条证据、不把句子改短来凑数（拆成短句但词数
没降，是换法子过检查）。正例：一段 180 词压到 120 词，论点与证据都在。

反例（旧 → 新）：

```
旧  模型在十六次运行里都保持稳定，只在措辞层面有变化。
新  模型在十六次运行里。都保持稳定。只在措辞层面有变化。
```

（三行短句，词数没降，句子还残了——不是改写，是换法子过检查。）

验收命令：

```bash
env PYTHONPATH=src python3 -m factscribe prescribe trim-to-budget --json
```

## 6. 边界与非目标

- 不判断「改得好不好」，不打分、不排名、不给通过率；
- 不自动改写正文，不调用模型，不联网；
- 不新增 `style` 判据，不改 `style-rules.toml` 的阈值含义；
- 不改 `audit` / `protect` 的判据与退出码；
- 处方不进入 CI 的通过/失败判定：`prescribe` 成功永远退出 `0`。

## 7. 验收

- `tests/test_prescription.py` ≥ 10 例，覆盖：清单与六段完整性、按既有
  错误码可查（含批 99 的 `EXPLAINER_DENSITY`、`JUSTIFY_CHAIN` 与批 102
  的 `LIGHT_VERB_NOMINALIZATION`、`ZH_DE_STACK`）、
  处方文字不进 `style` findings、`style` 不导入处方模块、
  冲突优先序与「让位」、验收命令可执行、反例与旧→新示例存在。
- 门禁：

```
env PYTHONPATH=src python3 -m unittest discover -s tests
./scripts/preflight-ci.sh
```
