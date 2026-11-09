# 文风闸 v5b 实施记录（批 88）：复检规则降噪

> 规范：`docs/design/SPEC-V3.0.md` §15（本次修订 §15.3 / §15.4 / §15.7 / §15.8）。
> 范围：只改 `factscribe style` 的两条改写后复检规则——`HEADING_RELATION_CHANGED`
> 与 `HEADING_SUBJECT_LOST`；`HEADING_ECHO`、`--diff`、`audit` / `protect` 均未改。
> 目标：**只提精度，不丢召回**——批 87 抓到的 6 处真实退步必须全部保留。

## 1. 为什么要降噪

批 87 在 `/tmp/v4-regen/{en,zh}` 上抓到了 6 处真实退步，但同时报出大量
良性提示。噪声集中在两条规则：

| 规则 | 旧判据的问题 | 良性实例 |
|---|---|---|
| `HEADING_RELATION_CHANGED` | 把删除并列连接也当「关系变化」 | `Invariants, and what they stop` → `Invariants`（删 `and`）；`Debug log: run order and per-arm cost` → `Debug log` |
| `HEADING_SUBJECT_LOST` | 旧标题任意实词消失都报，不管它是不是对比对象 | `What the attribution shows.` → `Attribution.`；`假设一：容量。` → `容量假设`（只少了个「一」） |

## 2. 收紧后的判据

### 2.1 `HEADING_RELATION_CHANGED`

- **只认对立/否定关系词**：`versus / vs / not / without / 对 / 而非 / 不是`
  （默认 `heading_relation_words`；可配）。
- **报**：旧标题里的对立关系词在新标题中不存在——被删除，或被别的词替换
  （`versus` → `or` 报；`versus` → `and` 也报，因为对立关系没了）。
- **不报**：删除 `and / or / 与 / 及 / 、` 这类**并列连接**（不承载对立关系）；
  只新增关系词；标题文字完全未变。
- `vs` 与 `versus` 视为同义，互换不报。
- 中文 `对` 只认「A 对 B」里的介词：`对照 / 针对 / 面对 / 对比 / 对于 /
  相对 / 绝对` 等词内部的「对」不触发。

### 2.2 `HEADING_SUBJECT_LOST`

- **只在旧标题本身是对比结构时启用**：
  - 英文：`X versus/vs Y`；
  - 中文：`X 对 Y`、`X 与 Y 对比/相比/比较`、`X 而非 Y`、`X 不是 Y`。
- **报**：对比结构的**对象名词**在新标题与新首句里都找不到。
- **忽略**：序数词（`one/two/three/four`、`一二三四`）、单字词、对比结构之外的
  修饰语；非对比标题（并列连接、普通名词短语）完全不判。
- **不降为 `info`**：它与关系词规则不完全重合——关系词可以保留而对象被换掉
  （`A versus B` → `A versus C`），此时只有本条能报；保留黄牌。

### 2.3 `HEADING_ECHO`

不变。批 87 实测 3/3 全中且无噪声，本次不碰。

## 3. 命中 / 不命中对照

### 3.1 必须保留的 6 处真实退步

| 条目 | 位置 | 码 | 收紧后 |
|---|---|---|---|
| EN-06 `Prompt versus mechanism.` → `Prompt or mechanism.` | `sections/04_mechanisms.tex:96` | `HEADING_RELATION_CHANGED` | ✅ 仍报 |
| EN-10 首句 `These limitations are known and not fixed.` | `sections/07_threats.tex:8` | `HEADING_ECHO` | ✅ 仍报 |
| ZH-04 `提示词对机制。` → `提示词` | `sections/04_mechanisms.tex:39` | `HEADING_RELATION_CHANGED` + `HEADING_SUBJECT_LOST` | ✅ 仍报（两码） |
| ZH-06 首句 `成本记账要先问账本记了什么。` | `sections/04_mechanisms.tex:53` | `HEADING_ECHO` | ✅ 仍报 |
| ZH-08 首句 `这些是已知且未修的限制。` | `sections/07_threats.tex:8` | `HEADING_ECHO` | ✅ 仍报 |
| ZH-09 首句 `相关工作里，…` | `sections/02_related.tex:3` | `HEADING_ECHO` | ✅ 仍报 |

### 3.2 必须不再报的良性实例

| 改写 | 旧标题结构 | 收紧后 |
|---|---|---|
| `Invariants, and what they stop` → `Invariants` | 并列（`and`） | ✅ 不报 |
| `Debug log: run order and per-arm cost` → `Debug log` | 并列（`and`） | ✅ 不报 |
| `What the attribution shows.` → `Attribution.` | 普通短语 | ✅ 不报 |
| `假设一：容量。` → `容量假设` | 序数 + 名词 | ✅ 不报 |
| `调试日志：运行顺序与每臂成本` → `调试日志` | 并列（`与`） | ✅ 不报 |
| `不变式，以及它们拦住了什么` → `不变式` | 并列（`及`） | ✅ 不报 |
| `对照一个成熟的 CLI` → `与成熟 CLI 对比` | 介词 `对照` 不是「A 对 B」 | ✅ 不报 |

### 3.3 边界

| 用例 | 期望 | 实测 |
|---|---|---|
| `Prompt or mechanism.`（EN-06 的新标题） | 报 `HEADING_RELATION_CHANGED` | ✅ |
| `Prompt versus mechanism.` 本身（未改动） | 不报 | ✅ |
| `Prompt versus mechanism.` → `Prompt versus trigger.` | 报 `HEADING_SUBJECT_LOST`（关系词保留，只有对象丢了） | ✅ |
| `Prompt versus mechanism.` → `Prompt and mechanism.` | 报（对立关系被并列替换） | ✅ |

## 4. 前后告警数（`--diff`）

命令（在 `paperkit-dev/` 下）：

```bash
python3 -m factscribe style /tmp/v4-regen/en --diff ../paper --json
python3 -m factscribe style /tmp/v4-regen/zh --diff ../paper-zh --json
```

| 口径 | EN 改前 | EN 改后 | ZH 改前 | ZH 改后 |
|---|---:|---:|---:|---:|
| 两条复检规则新增告警 | 8 | **2** | 15 | **5** |
| 全部码新增告警 | 9 | **3** | 19 | **9** |

- 两条复检规则：EN `8 → 2`（≤4 ✅），ZH `15 → 5`（≤6 ✅）。
- 全部码：EN `9 → 3`（≤4 ✅），ZH `19 → 9`。
  ZH 余下 4 条不是本次两条规则的告警，而是改写文本真实产生的新条目：
  `COLLOQUIAL_TRIAD` 1 条、`RHYTHM_PLATEAU` 3 条；它们在原文基线里不存在，
  不是误报，按「不许丢召回」不压制。
- 6 处真实退步逐条保留，清单见 §3.1；ZH-04 两码都在。

### 原文与未改写论文基线

| 项目 | `HEADING_ECHO` | `HEADING_RELATION_CHANGED` | `HEADING_SUBJECT_LOST` |
|---|---:|---:|---:|
| `../paper` | 0 | 0 | 0 |
| `../paper-zh` | 0 | 0 | 0 |
| `../paper-b` | 0 | 0 | 0 |
| `../paper-b-zh` | 0 | 0 | 0 |

## 5. 测试

`tests/test_style_v5.py`：**50 例**（批 87 的 36 例全部保留，新增 14 例）。

新增覆盖：

- 4 个任务表列出的良性实例负例锁（Debug log / Invariants / Attribution / 容量假设）；
- 3 个同族中文噪声负例（调试日志删 `与`、不变式删 `及`、`对照`→`与…对比`）；
- 2 个并列连接删除负例（英文 `and`、中文 `与`）；
- 8 个论文里未改动的真实标题负例（`Related work`、`Cost accounting`、
  `Across domains`、`Mechanical gates`、`相关工作`、`成本记账`、`机械闸门`、
  `跨领域`）；
- 3 个边界（`Prompt or mechanism.` 必报、`Prompt versus mechanism.` 不报、
  对立关系被并列替换仍报）；
- 1 个「关系词保留、对象被换掉」的边界（只有 `HEADING_SUBJECT_LOST` 报，
  证明两条规则不完全重合）；
- 原有 `test_positive_english_subject_lost` 的夹具从「并列标题」改为
  「对比结构」；原并列实例转为负例，未删除测试面。

全套：`Ran 376 tests` 全绿（原 362 ＋ 新增 14）。

## 6. 门禁输出

`env PYTHONPATH=src python3 -m unittest discover -s tests`：

```text
Ran 376 tests in 17.638s

OK
```

`./scripts/preflight-ci.sh --fast`（工作区，含本次改动）：

```text
== 步骤 1/4：外部依赖 ==
   ✓ pdftotext：/opt/homebrew/bin/pdftotext
   ✓ pdfinfo：/opt/homebrew/bin/pdfinfo
   ✓ PDF 工具齐备
== 步骤 2/4：干净克隆（--fast：跳过，直接用工作区）==
== 步骤 3/4：测试矩阵 ==
   ✓ Python 3.10：Ran 376 tests
   ✓ Python 3.11：Ran 376 tests
   ✓ Python 3.12：Ran 376 tests
== 步骤 4/4：验收样例 ==
   ✓ examples/minimal audit exit=1（红，符合预期）
== 结论 ==
   本地等价 CI 全绿——可以推。
```

提交后对干净克隆再跑一次 `./scripts/preflight-ci.sh`，测试矩阵同为本仓
`376 tests`，结论全绿（提交信息「复检规则降噪」）。

## 7. 兼容性

- `HEADING_ECHO` 判据与词表未改；
- `--diff` 的多重集差语义未改；
- `HEADING_RELATION_CHANGED` / `HEADING_SUBJECT_LOST` 仍只在 `--diff` 时运行；
- 退出码仍只有 0 / 3，永不 1；
- `heading_relation_words` 仍可配；默认值收窄为对立关系词，删除并列连接不再触发。
