# SYNTAX｜六条句法级判据实施读数（批 102；批 103 收紧 A2）

日期：2026-11-10｜规范：`docs/design/SPEC-SYNTAX.md`｜实施：D 席

## 0. 一句话

六项全部落地：五条新判据＋`EMPTY_ADJECTIVE` 的中文 bug 修复。批 103 把
`ZH_DE_STACK` 从「总数 ≥4 且句长 ≤30」收紧为「连续两层短修饰」，四份
本仓语料上一律 **0 条**；没有任何判据超误报预算（每万字 ≤2 条）。

## 1. 落地清单

| # | 判据 | 错误码 | 单位 | 阈值 | 状态 |
|---|---|---|---|---|---|
| A1 | 英文轻动词＋名义化 | `LIGHT_VERB_NOMINALIZATION` | 条 | `>= 1` | 落地 |
| A2 | 中文单句连续短修饰链 | `ZH_DE_STACK` | 句 | 连续两层间隔 ≤6 字 | 落地（批 103 收紧，见 §5.1） |
| A3 | 中文后置条件从句 | `ZH_POSTPOSED_CONDITION` | 处 | `>= 1` | 落地 |
| A4 | 由于/因为…使得 | `ZH_DUE_TO_MAKE` | 处 | `>= 1` | 落地 |
| A5 | 英文膨胀短语 | `WORDINESS_BLOAT` | 处 | `>= 1` | 落地 |
| A6 | 「显著」豁免 | `EMPTY_ADJECTIVE`（无新码） | 每千字 | 6.0（既有） | 修 bug |

实现落点：

- 判据与词表：`factscribe/style.py`（`LIGHT_VERB_NOMINALIZATION` 等五条
  在 `analyze()` 里按条汇总，无密度闸）、`style-rules.toml`（阈值与词表）；
- 测试：`tests/test_syntax.py`（42 例）；
- 处方：`factscribe/patterns/unbury-the-verb/RULE.md`、
  `factscribe/patterns/cut-the-de/RULE.md`，登记在
  `patterns/priority.toml` 与 `SPEC-PRESCRIPTION.md` §5；
- 既有测试同步：`tests/test_prescription.py`（9 条处方）、
  `tests/test_docmode.py`（指标快照加 5 个键）、两份 README（25 条判据 /
  9 条处方 / 660 例）。

## 2. 四份语料的规模与预算上限

预算口径：每条新规则每万字 ≤2 条。语料不足一万字时，允许条数取
`floor(2 × units / 10000)` 的下限：

| 语料 | 计数单元（词/字） | 预算上限（条/规则） |
|---|---|---|
| `paper` | 6,961 | 1 |
| `paper-zh` | 10,969 | 2 |
| `paper-b` | 5,983 | 1 |
| `paper-b-zh` | 9,592 | 1 |

复算命令（仓根 `paperkit-dev/`）：

```bash
env PYTHONPATH=src python3 -m factscribe style ../paper --json
env PYTHONPATH=src python3 -m factscribe style ../paper-zh --json
env PYTHONPATH=src python3 -m factscribe style ../paper-b --json
env PYTHONPATH=src python3 -m factscribe style ../paper-b-zh --json
```

## 3. 触发表（逐条）

| 判据 | `paper` | `paper-zh` | `paper-b` | `paper-b-zh` | 超预算？ |
|---|---|---|---|---|---|
| `LIGHT_VERB_NOMINALIZATION` | 0 | 0 | 0 | 0 | 否 |
| `WORDINESS_BLOAT` | 0 | 0 | 0 | 0 | 否 |
| `ZH_DE_STACK` | 0 | **0** | 0 | 0 | 否 |
| `ZH_POSTPOSED_CONDITION` | 0 | 0 | 0 | 0 | 否 |
| `ZH_DUE_TO_MAKE` | 0 | 0 | 0 | 0 | 否 |
| A6「显著」（修复后） | 0 | 0 | 0 | 0 | 否 |

批 103 收紧后，`ZH_DE_STACK` 在四份语料上全部 0 条；批 102 曾命中的
两条 `paper-zh` 句子（`表 的难度档用的是…`、`最后一臂的 5/5 是…`）
经复核都是正常句子，已按 §5.1 归零。

其余四份语料在这五条新判据上 **0 命中**：英文两篇没有「轻动词＋名义化」
与膨胀短语；中文两篇没有后置条件从句、没有「由于…使得」结构。

A6 的修复在本批四份语料上不可见（四份语料都没有「显著」），但 bug 本身
可复现：修复前若正文出现「统计显著」，`EMPTY_ADJECTIVE` 会按「显著」
命中；修复后 0 命中。测试锁死（见 §4）。

## 4. 测试

`tests/test_syntax.py`：**42 例**（任务要求 ≥24，每条规则 ≥4）。

| 规则 | 例数 | 覆盖 |
|---|---|---|
| `LIGHT_VERB_NOMINALIZATION` | 8 | 甲乙两组正例、无冠词甲组、白名单、宾语补足语/短语动词/状态名词负例、动作动词提示、按条计数 |
| `ZH_DE_STACK` | 9 | 短修饰链正例、3/4 个「的」、两条正常句负例、长定语负例、间隔 6/7 边界、单间隔负例、阈值可配、引文/列表遮罩 |
| `ZH_POSTPOSED_CONDITION` | 5 | 后置正例、前置负例、「若干」豁免、若/倘若/一旦 |
| `ZH_DUE_TO_MAKE` | 5 | 两种原因标记、正常因果负例、无介词负例、跨句负例、理由含「缺主」 |
| `WORDINESS_BLOAT` | 7 | 五条短语各一例＋直接替代、B 级负例、大小写 |
| A6「显著」 | 5 | 裸「显著」不报、统计术语不报、显著差异不报、其余空泛形容词照旧、配置面八条豁免 |
| 注册面与处方 | 3 | 指标/阈值已登记、两条处方可 `--for` 查到 |

全仓：660 例（原 618 ＋ 批 102 新增 38 ＋ 批 103 净增 4）。

## 5. 阈值调整记录（被误报预算逼出来的三处）

三处调整都写进 `SPEC-SYNTAX.md`，这里记原始读数与理由。

### 5.1 `ZH_DE_STACK`：`≥4 且 ≤30` → 连续两层间隔 `≤6 字`

批 102 采用「单句 ≥4 个「的」且 ≤30 字」，四份语料 0 / 2 / 0 / 0。
两条都落在 `paper-zh`，批 103 复核后确认都是正常句子：

- `表 的难度档用的是数据集自带的标签，不是我们另贴的。`
  ——「难度档用的是」是「是…的」结构；
- `最后一臂的 5/5 是一个任务的五次运行，而不成功的那些臂是更小的集合。`
  ——「是一个任务的」与「那些臂是更小的」都是小句。

批 103 先按「相邻两个「的」间隔 ≤6 字」直跑（单间隔即报）：

| 语料 | 单间隔命中 |
|---|---|
| `paper` | 0 |
| `paper-zh` | 6 |
| `paper-b` | 0 |
| `paper-b-zh` | 5 |

11 条全是相对从句或「是…的」结构，例如
`相邻的几条线扩展的是…`（间隔 5，「扩展」是动词）、
`在我们的消融里活下来的只有前者`（间隔 6）、
`模型实际收到的载荷的哈希`（间隔 2，但「收到的」是相对从句）。
可见单看一对间隔仍会把正常定语链算进来。

实装再收紧一格：要求**至少两个连续短间隔**（三个「的」成链），并把
谓词/连接断点（`是、用、而、不`…）与标点/数字视为链断。前后读数：

| 语料 | 批 102（≥4 / ≤30） | 批 103（连续短链） |
|---|---|---|
| `paper` | 0 | 0 |
| `paper-zh` | 2 | **0** |
| `paper-b` | 0 | 0 |
| `paper-b-zh` | 0 | 0 |

代价是「美丽的花的颜色」这类只有两层、仅一处短间隔的轻度「的」链不再
报；这是精度优先的取舍，`SPEC-SYNTAX.md` §2.2 已写明。

### 5.2 `LIGHT_VERB_NOMINALIZATION`：乙组只认 `a/an` 或复数

初版按「动词＋可选冠词＋名词」直跑，`paper` 命中 6 条：

- 真阳性候选：`makes violation impossible`、`makes inclusion falsifiable`；
- 明显误报：`made the section more uniform`（宾语补足语）、
  `made the ablation legible`（同上）、`took the decision away` /
  `take the decision away`（短语动词）、`establish superiority`（状态名词）。

乙组（make/give/take/have/do/reach/achieve/establish）收窄为只认
`a/an＋名词` 或复数名词后，`paper` 与 `paper-b` 均为 0，且没有丢掉
`make a distinction` / `perform an analysis` 这类真阳性。甲组
（perform/conduct/carry out/undertake/provide/offer）保留无冠词形态。

### 5.3 `ZH_POSTPOSED_CONDITION`：逗号前 `≥6 字` → `≥4 字`

初值要求主句至少 6 字，会漏掉「实验会继续，倘若样本量达到阈值。」
（主句 5 字）这类正常短主句。降到 4 字后仍要求逗号后紧跟条件标记，
「若干」照旧豁免；四份语料仍是 0 命中（无新增误报）。

## 6. 门禁输出

### 6.1 `env PYTHONPATH=src python3 -m unittest discover -s tests`

```
Ran 660 tests

OK
```

### 6.2 `./scripts/preflight-ci.sh --fast`（工作区，含未提交改动）

```
步骤 1/4：外部依赖 —— pdftotext / pdfinfo 齐备
步骤 2/4：干净克隆（--fast：跳过）
步骤 3/4：测试矩阵
   ✓ Python 3.10：Ran 660 tests
   ✓ Python 3.11：Ran 660 tests
   ✓ Python 3.12：Ran 660 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

### 6.3 `python3 scripts/check-readme.py`

```
✓ style --doc 两份 README 均为 0 条
✓ 测试数 660
结论：全过
```

### 6.4 提交后 `./scripts/preflight-ci.sh`（默认模式，干净克隆）

提交后复跑，克隆只含已提交文件（与 6.2 的 `--fast` 同一份代码）：

```
步骤 2/4：干净克隆（只含已提交文件）
步骤 3/4：测试矩阵
   ✓ Python 3.10：Ran 660 tests
   ✓ Python 3.11：Ran 660 tests
   ✓ Python 3.12：Ran 660 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

## 7. 已知边界

- 五条新判据都是「字面串 + 位置 + 计数」，不依赖分词与词性标注；
- 引号/代码块/公式/文献表沿用 `style` 既有遮罩口径，不另开豁免；
- `LIGHT_VERB_NOMINALIZATION` 的动作提示只对 `[light_verbs.actions]` 里
  的词给确切动词；表外名词只提示「还原成对应的动词」，不猜词形；
- `ZH_DE_STACK` 只看同句内的连续短修饰链，不做全文「的」密度（跨语料差
  4 倍，不可移植）；单处短间隔（相对从句）不报。
