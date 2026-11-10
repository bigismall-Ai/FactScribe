# SPEC-SYNTAX-C｜标题换标点/换介词规避（批 119）

状态：批 119 定稿。判据 `HEADING_SUBSTITUTED` 只出黄牌（`style` 退出码 3），
只在 `style --diff <before>` 传了改写前目录时运行；不改正文、不阻断构建。
实现：`factscribe/style.py` 的 `_heading_substitution` 与
`_rewrite_heading_findings`；测试：`tests/test_heading_substituted.py`（17 例）。

本件只写这一条判据。其余句法判据见 `SPEC-SYNTAX.md`、`SPEC-SYNTAX-B.md`；
标题的改写后复检（`HEADING_ECHO` / `HEADING_RELATION_CHANGED` /
`HEADING_SUBJECT_LOST`）见 `SPEC-V3.0.md` §15。

## 0. 起因

两次真实改写里，空白模型用「最小代价」绕过了标题规则：

| 语言 | 旧标题 | 新标题 | 规避手法 |
|---|---|---|---|
| 中 | `结论：一项草稿阶段的干预` | `结论、一项草稿阶段的干预` | 冒号换顿号 |
| 英 | `Conclusion: A Draft-Stage Intervention` | `Conclusion as a Draft-Stage Intervention` | 冒号换介词 `as` |
| 英 | `Method: Indicators, Bidirectional Rules, and Stage` | `Method with Indicators, Bidirectional Rules, and Stage` | 冒号换介词 `with` |

手册（`factscribe/patterns/PLAYBOOK.md` §5 第 8 条）早已把这类改法写成禁做，
但手册靠执行模型自觉。本判据把「只换一个 token、其余逐字不动」变成机器可查。

## 1. 判定

### 1.1 输入与配对

- 只在 `style <after> --diff <before>` 时运行；没有 `--before` 时**不运行**
  （回归锁见 `test_no_before_never_runs_substitution_rule`）。
- 按文件、按标题出现顺序配对旧/新标题；命令层级不同（`\section` /
  `\subsection` / `\paragraph` …）不配对；标题文字完全未变不判。

### 1.2 触发条件

对每一对旧标题 `old`、新标题 `new`：

1. `old` 含冒号（半角 `:` 或全角 `：`），且 `new` 不含冒号；
2. 满足任一「纯替换」：
   - **换标点**：把 `old` 的冒号替换成 `、`、`，`、`,`、`（`、`）` 之一后，
     与 `new` 逐字相同（只容首尾空白差异）；
   - **换介词**：把 `old` 的冒号两侧换成 `as`、`with`、`for`、`of` 之一后，
     与 `new` 相同（大小写不敏感，冒号两侧空白可增减）；除替换 token 外
     不再改别的词。
3. 命中即报一条 `HEADING_SUBSTITUTED`，消息给出旧标题、新标题与被替换成
   的那个 token。

替换 token 表可配：项目根 `style-rules.toml` 的 `[heading_substitute]`
`punctuation` / `prepositions`，缺省即上表。

### 1.3 明确不报（写死）

- **真重写**：`Results: The Gate Wins on Drafts and Loses on Polished Text`
  → `Gate Wins on Drafts, Loses on Polished Text`（删类别词、改逗号，不是纯替换）；
- **删类别词**：`结论：一项草稿阶段的干预` → `一项草稿阶段的干预`；
- **只删句号**：`生成系统。` → `生成系统`（旧标题本来没有冒号）；
- **旧标题无冒号**：任何新旧标题都不进入本判据；
- **除冒号外还改了别的词**：`结论：一项草稿阶段的干预` →
  `结论、一项草稿阶段的方案`（「干预」→「方案」）。
  这类改动不是纯替换，交给真重写与人工判断；本判据只抓逐字可证的替换。

### 1.4 与手册第 8 条的关系

手册第 8 条给出「禁做」的正反例（换标点、换介词、正解删类别词），是给执行
模型的**操作约束**；`HEADING_SUBSTITUTED` 是同一约束的**机械复核**：

- 手册管「改之前该怎么做」，判据管「改之后机器能不能查」；
- 手册允许的正解（删类别词、改成名词短语）不会命中本判据；
- 手册列出的反例（顿号/逗号/括号顶替冒号、`as/with/for/of` 顶替冒号）
  在 `style --diff` 里逐条可复现。

手册第 8 条已加一句指向本判据，避免「手册说了但机器不查」的缝。

## 2. 验收读数（真材料）

2026-11-10 在 `paperkit-dev/` 运行，四条命令与读数：

```text
$ python3 -m factscribe style /tmp/e2e2/zh --diff ../paper-b-zh --json
exit 3；diff.new_findings = 1；metrics.heading_substituted = 1
  HIT sections/04_style_case.tex:48  结论、一项草稿阶段的干预
      旧「结论：一项草稿阶段的干预」；token「、」

$ python3 -m factscribe style /tmp/e2e4/en --diff ../paper-b --json
exit 3；diff.new_findings = 3；metrics.heading_substituted = 3
  HIT sections/04_style_case.tex:22   Method with Indicators, Bidirectional Rules, and Stage
      旧「Method: Indicators, Bidirectional Rules, and Stage」；token「with」
  HIT sections/04_style_case.tex:49   Experiment with Three Comparisons and a Blind Protocol
      旧「Experiment: Three Comparisons and a Blind Protocol」；token「with」
  HIT sections/04_style_case.tex:155  Conclusion as a Draft-Stage Intervention
      旧「Conclusion: A Draft-Stage Intervention」；token「as」

$ python3 -m factscribe style /tmp/e2e3/zh --diff ../paper-b-zh --json
exit 0；diff.new_findings = 0；metrics.heading_substituted = 0

$ python3 -m factscribe style /tmp/e2e5/en --diff ../paper-b --json
exit 0；diff.new_findings = 0；metrics.heading_substituted = 0
```

结论：

- 能抓住历史规避：中文顿号 1 条；英文 `with/with/as` 3 条；
- 不误伤正确改法：e2e3（中文正确删类别词/真重写）与 e2e5（英文正确删类别词）
  均为 0；
- 旧标题里本来没有冒号的 `Design as a Contract Before a Judge`（它对
  `Contract-first design` 是真重写）不报——判据只认「冒号 → token」的纯替换。

> 语料说明：2026-11-10 23:29 有一次并行批把 `paper-b` / `paper-b-zh` 直接
> 覆盖成了改后版，四条验收因此在临时还原了 `04_style_case.tex` 四条冒号
> 标题后运行；运行完已逐字节恢复原目录。上面四条就是该基线上的真实读数。

## 3. 回归面

- `tests/test_heading_substituted.py`：17 例，覆盖中文顿号/逗号/括号、
  英文 `as/with/for/of`、真重写、删类别词、删句号、旧标题无冒号、
  改别的词、空白容忍、大小写、文件内按序配对、token 可配、CLI `--diff`、
  以及「没有 `--before` 不运行」的回归锁；
- 全仓 `env PYTHONPATH=src python3 -m unittest discover -s tests` 全绿；
- `HEADING_SUBSTITUTED` 已进 `DIRECTIONS` / `CODE_OF` / `FINDING_ORDER` /
  `metrics` / 人读报告指标表；`style --json` 多出
  `metrics.heading_substituted`（默认 0）。
