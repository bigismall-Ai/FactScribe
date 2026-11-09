# 文风闸 v5 实施记录（批 87）

> 规范：`docs/design/SPEC-V3.0.md` §15「改写后复检」。
> 只改 `factscribe style` 子命令；**未改 `audit` / `protect` 的判据与退出码**。
> 新规则全黄牌，退出码仍为 0 / 3；`--diff` 不传时行为与 v4 一致。

## 1. 背景与修法

批 84 用 v4 规则改写两篇论文，盲评发现 6 处退步。根因不是阈值松，而是
v4 的 `TERM_FIRST_IN_HEADING` 只问「标题里的词在不在首句」：

- 复述标题（`These limitations are known and not fixed.`）→ 词在，过关；
- 垫话（`相关工作里，`）→ 词在，过关；
- 删关系词（`Prompt versus mechanism.` → `Prompt or mechanism.`）→ 标题规则不管语义；
- 删主语（`提示词对机制。` → `提示词`）→ 没有跨版本比对。

v5 增加四条判据与一个 diff 回路：

| 码 | 一句话 | 严重级别 | 需要 `--diff` |
|---|---|---|---|
| `HEADING_ECHO` | 首句没有引入新实义（复述标题 / 垫话 / 纯设问） | 黄 | 否 |
| `TERM_FIRST_IN_HEADING`（文案修订） | 删除 `本节讨论 X` 范例，明写禁止三种伪满足 | 黄 | 否 |
| `HEADING_RELATION_CHANGED` | 标题关系词被替换或删除 | 黄 | 是 |
| `HEADING_SUBJECT_LOST` | 旧标题的实义成分在新标题与新首句里都消失 | 黄 | 是 |
| `style --diff <before>` | 只报本次改写新增的违规 | 黄 | — |

## 2. 判据与阈值

### 2.1 `HEADING_ECHO`

- 首句实义词 − 标题实义词 − 泛化词 = **新实义**；
- `len(新实义) < thresholds.heading_echo_min_new_terms`（默认 `1`）即报；
- 英文按词（大小写、所有格、常见复数归一）；中文按字（先删停用短语/停用字）；
- 另两种伪满足直接报：
  - 首句以标题开头后紧跟垫话（中文 `里/中/方面/来说/而言/要先/先要/先问/
    首先要/需要先/本节讨论/这里讨论…`；英文 `is about/is concerned with/
    is discussed/we discuss/this section/here we…`）；
  - 纯设问（「什么是 X？」这类没有新实义的设问，会先被「新实义 < 阈值」抓住）。
- 泛化词（`limitations` / `限制` 等）只从首句的「新实义」里扣除，标题保留。

### 2.2 `TERM_FIRST_IN_HEADING` 文案

- 删除旧范例 `本节讨论 X`；
- 改为定义式范例「预注册是在收集数据前固定假设与分析计划的做法」；
- 建议文案明写：复述标题、垫话（「相关工作里，」）、设问都不算定义；
- 判定逻辑与白名单不变。

### 2.3 `HEADING_RELATION_CHANGED`

- 关系词默认 `versus / vs / and / or / not / without / 对 / 与 / 及 / 不是`
  （`heading_relation_words` 可配）；
- 改写前后按文件、按标题出现顺序配对，命令层级不同不配对；
- 旧关系词集合非空且 ≠ 新集合 → 报；只新增（旧集合为空）不报；
- 标题文字完全未变 → 不判。

### 2.4 `HEADING_SUBJECT_LOST`

- 旧标题实义成分：中文按分隔字切段（去停用字/短语/泛化词，保留 ≥2 字段）；
  英文按词（去停用词/泛化词/关系词，轻量复数归一）；
- 成分在新标题与改后首句里**都不出现** → 报；标题文字未变 → 不判。

### 2.5 `style --diff`

- 先跑改后全文，再跑改前全文；
- 按 `(code, file, 规范化 text)` 做多重集差，只保留改后多出来的条目；
- `findings/fired/summary/exit_code` 都以新增为准，改后指标仍原样输出；
- `--json` 增加 `diff: {before, baseline_findings, new_findings}`；
- 不传 `--diff` 时完全向后兼容。

### 2.6 明确不实现

标题语义相似度模型、LLM 判分。保持离线、确定性、零 LLM。

## 3. 实现落点

- `factscribe/style.py`
  - 新增 `HEADING_ECHO` / `HEADING_RELATION_CHANGED` / `HEADING_SUBJECT_LOST`
    的词表、归一化、配对与 finding 生成；
  - `analyze(..., before=...)` 可选参数；`filter_new_findings(after, before)`
    做 diff 多重集差；
  - 每条 finding 仍为 `code / severity / file / line / text / suggestion`，
    severity 恒 `yellow`。
- `factscribe/cli.py`
  - `style` 增加 `--diff BEFORE`；不传时走原路径；
  - `--json` 增加 `diff` 块；人读报告末行显示「改前 N 处 → 只报新增 M 处」。
- `style-rules.toml`
  - 新增 `thresholds.heading_echo_min_new_terms = 1`；
  - 新增 `heading_relation_words`；
  - 新增 `[heading_echo]` 的泛化词与垫话词表。
- `docs/design/SPEC-V3.0.md`
  - 新增 §15（判据、阈值、误报边界、错误码、`--diff`、不实现项、验收）。

## 4. 测试

新增 `tests/test_style_v5.py`：**36 例**。

- `HEADING_ECHO`：英文/中文复述、英文/中文垫话、中文「要先问」垫话、
  中英定义式首句负例、`heading_echo_min_new_terms` 边界（1 个新词默认不报、
  调到 2 报）、无正文标题不判——共 10 例；
- `TERM_FIRST_IN_HEADING` 文案：三种伪满足都写进建议、含定义式范例、
  复述标题由 `HEADING_ECHO` 接手——共 3 例；
- `HEADING_RELATION_CHANGED`：英文替换、中文删除、未变负例、只新增不报、
  不传 `--diff` 不跑、关系词可配——共 6 例；
- `HEADING_SUBJECT_LOST`：中文/英文丢失、标题保留负例、首句写回负例、
  不传 `--diff` 不跑——共 5 例；
- `--diff`：两边都干净不报、改前 1 条改后 2 条只报 1 条、同一条不重复报、
  新引入 `HEADING_ECHO` 被抓、CLI exit 0/3——共 6 例；
- 批 84 的 6 个真实退步最小复现夹具：6 例。

全套：`Ran 362 tests` 全绿（原 326 ＋ 新增 36）。

## 5. 验收：批 84 的 6 个退步

命令（在 `paperkit-dev/` 下跑，`--diff` 指向原始论文目录）：

```bash
python3 -m factscribe style /tmp/v4-regen/en --diff ../paper
python3 -m factscribe style /tmp/v4-regen/zh --diff ../paper-zh
```

两条均 exit 3。6 个退步全部被抓到：

| 条目 | 改动 | 抓到的码 | 位置 |
|---|---|---|---|
| EN-10 | 首句插入 `These limitations are known and not fixed.` | `HEADING_ECHO` | `sections/07_threats.tex:8` |
| EN-06 | `Prompt versus mechanism.` → `Prompt or mechanism.` | `HEADING_RELATION_CHANGED` | `sections/04_mechanisms.tex:96` |
| ZH-04 | `提示词对机制。` → `提示词` | `HEADING_RELATION_CHANGED` + `HEADING_SUBJECT_LOST` | `sections/04_mechanisms.tex:39` |
| ZH-06 | 首句插入 `成本记账要先问账本记了什么。` | `HEADING_ECHO` | `sections/04_mechanisms.tex:53` |
| ZH-08 | 首句插入 `这些是已知且未修的限制。` | `HEADING_ECHO` | `sections/07_threats.tex:8` |
| ZH-09 | 首句插入 `相关工作里，` | `HEADING_ECHO` | `sections/02_related.tex:3` |

`--diff` 汇总：

```text
en: 改前 42 处 → 只报新增 9 处
zh: 改前 76 处 → 只报新增 19 处
```

新增条目里除上述 6 条退步外，还包括本次改写真实产生的其他标题变化
（如 `Debug log: run order and per-arm cost` → `Debug log`、
`Invariants, and what they stop` → `Invariants`、`What the attribution shows.` →
`Attribution.`、`与成熟 CLI 对比` → `对比成熟 CLI`）和原有的节奏平台条目；
这些是黄牌提示，不是误报。

### 原文误报清单

对 `paper/` 与 `paper-zh/` 原文跑常规 `style`（不带 `--diff`），新规则
（`HEADING_ECHO` / `HEADING_RELATION_CHANGED` / `HEADING_SUBJECT_LOST`）的
新增违规：

```text
paper/    : 0 条
paper-zh/ : 0 条
```

无逐条清单（为空）。远低于「≤10 条」的上限。

## 6. 门禁输出

`env PYTHONPATH=src python3 -m unittest discover -s tests`：

```text
Ran 362 tests in 17.635s

OK
```

`./scripts/preflight-ci.sh --fast`：

```text
== 步骤 1/4：外部依赖 ==
   ✓ pdftotext：/opt/homebrew/bin/pdftotext
   ✓ pdfinfo：/opt/homebrew/bin/pdfinfo
   ✓ PDF 工具齐备
== 步骤 2/4：干净克隆（--fast：跳过，直接用工作区）==
== 步骤 3/4：测试矩阵 ==
   ✓ Python 3.10：Ran 362 tests
   ✓ Python 3.11：Ran 362 tests
   ✓ Python 3.12：Ran 362 tests
== 步骤 4/4：验收样例 ==
   ✓ examples/minimal audit exit=1（红，符合预期）
== 结论 ==
   本地等价 CI 全绿——可以推。
```

干净克隆版 `./scripts/preflight-ci.sh`（被测代码提交 `9d6507b`；随后仅把本段
门禁输出写回文档并 amend，代码与测试面未变）同样全绿：

```text
== 步骤 2/4：干净克隆 ==
   ✓ 克隆到 …/factscribe-ci.*/repo（HEAD 9d6507b）
== 步骤 3/4：测试矩阵 ==
   ✓ Python 3.10：Ran 362 tests
   ✓ Python 3.11：Ran 362 tests
   ✓ Python 3.12：Ran 362 tests
== 步骤 4/4：验收样例 ==
   ✓ examples/minimal audit exit=1（红，符合预期）
== 结论 ==
   本地等价 CI 全绿——可以推。
```

## 7. 兼容性核对

- `audit` / `protect` 未改动；
- 新规则全黄牌，`exit_code` 仍为 0 或 3，永不 1；
- `--diff` 不传时，`analyze` / `style` 的原有输出路径不变（只多出 `HEADING_ECHO`
  与修订后的 `TERM_FIRST_IN_HEADING` 文案）；
- `HEADING_RELATION_CHANGED` / `HEADING_SUBJECT_LOST` 只在 `--diff` 时运行。
