# SYNTAX｜六条句法级判据实施读数（批 102）

日期：2026-11-10｜规范：`docs/design/SPEC-SYNTAX.md`｜实施：D 席

## 0. 一句话

六项全部落地：五条新判据＋`EMPTY_ADJECTIVE` 的中文 bug 修复。四份本仓
语料逐条跑过，**没有一条超误报预算**（每万字 ≤2 条）；唯一触发是新规则
`ZH_DE_STACK` 在 `paper-zh` 2 条（1.82/万字），两条都判为真阳性。

## 1. 落地清单

| # | 判据 | 错误码 | 单位 | 阈值 | 状态 |
|---|---|---|---|---|---|
| A1 | 英文轻动词＋名义化 | `LIGHT_VERB_NOMINALIZATION` | 条 | `>= 1` | 落地 |
| A2 | 中文单句「的」堆叠 | `ZH_DE_STACK` | 句 | 的 ≥4 且汉字 ≤30 | 落地（阈值收紧，见 §5） |
| A3 | 中文后置条件从句 | `ZH_POSTPOSED_CONDITION` | 处 | `>= 1` | 落地 |
| A4 | 由于/因为…使得 | `ZH_DUE_TO_MAKE` | 处 | `>= 1` | 落地 |
| A5 | 英文膨胀短语 | `WORDINESS_BLOAT` | 处 | `>= 1` | 落地 |
| A6 | 「显著」豁免 | `EMPTY_ADJECTIVE`（无新码） | 每千字 | 6.0（既有） | 修 bug |

实现落点：

- 判据与词表：`factscribe/style.py`（`LIGHT_VERB_NOMINALIZATION` 等五条
  在 `analyze()` 里按条汇总，无密度闸）、`style-rules.toml`（阈值与词表）；
- 测试：`tests/test_syntax.py`（38 例）；
- 处方：`factscribe/patterns/unbury-the-verb/RULE.md`、
  `factscribe/patterns/cut-the-de/RULE.md`，登记在
  `patterns/priority.toml` 与 `SPEC-PRESCRIPTION.md` §5；
- 既有测试同步：`tests/test_prescription.py`（9 条处方）、
  `tests/test_docmode.py`（指标快照加 5 个键）、两份 README（25 条判据 /
  9 条处方 / 656 例）。

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
| `ZH_DE_STACK` | 0 | **2** | 0 | 0 | 否（1.82/万字 ≤2） |
| `ZH_POSTPOSED_CONDITION` | 0 | 0 | 0 | 0 | 否 |
| `ZH_DUE_TO_MAKE` | 0 | 0 | 0 | 0 | 否 |
| A6「显著」（修复后） | 0 | 0 | 0 | 0 | 否 |

`ZH_DE_STACK` 两处（都在 `paper-zh`）：

| 文件:行 | 原句 | 的/汉字 | 判定 |
|---|---|---|---|
| `appendix/a_tasks.tex:5` | 表 的难度档用的是数据集自带的标签，不是我们另贴的。 | 4 / 23 | **真**：一句四「的」，定语叠成楼梯；首处「表 的」还带排版空格，但仍是「的」链。 |
| `sections/07_threats.tex:10` | 最后一臂的 5/5 是一个任务的五次运行，而不成功的那些臂是更小的集合。 | 4 / 29 | **真**：四个「的」串起三个限定，中心词到句末才出现；改法明确（拆两句）。 |

其余四份语料在这五条新判据上 **0 命中**：英文两篇没有「轻动词＋名义化」
与膨胀短语；中文两篇没有后置条件从句、没有「由于…使得」结构。

A6 的修复在本批四份语料上不可见（四份语料都没有「显著」），但 bug 本身
可复现：修复前若正文出现「统计显著」，`EMPTY_ADJECTIVE` 会按「显著」
命中；修复后 0 命中。测试锁死（见 §4）。

## 4. 测试

`tests/test_syntax.py`：**38 例**（任务要求 ≥24，每条规则 ≥4）。

| 规则 | 例数 | 覆盖 |
|---|---|---|
| `LIGHT_VERB_NOMINALIZATION` | 8 | 甲乙两组正例、无冠词甲组、白名单、宾语补足语/短语动词/状态名词负例、动作动词提示、按条计数 |
| `ZH_DE_STACK` | 5 | 正例、3 个「的」负例、超长负例、阈值可配、边界 |
| `ZH_POSTPOSED_CONDITION` | 5 | 后置正例、前置负例、「若干」豁免、若/倘若/一旦 |
| `ZH_DUE_TO_MAKE` | 5 | 两种原因标记、正常因果负例、无介词负例、跨句负例、理由含「缺主」 |
| `WORDINESS_BLOAT` | 7 | 五条短语各一例＋直接替代、B 级负例、大小写 |
| A6「显著」 | 5 | 裸「显著」不报、统计术语不报、显著差异不报、其余空泛形容词照旧、配置面八条豁免 |
| 注册面与处方 | 3 | 指标/阈值已登记、两条处方可 `--for` 查到 |

全仓：656 例（原 618 ＋ 新增 38）。

## 5. 阈值调整记录（被误报预算逼出来的三处）

三处调整都写进 `SPEC-SYNTAX.md`，这里记原始读数与理由。

### 5.1 `ZH_DE_STACK`：`≥3 且 ≤40` → `≥4 且 ≤30`

调研稿初值直跑本仓语料（按句计）：

| 语料 | 初值命中 | 每万字 | 样本问题 |
|---|---|---|---|
| `paper-zh` | 19 | 17.3 | 多为正常列举/复句，如「两臂都跑 X，用同样的计划、同样的预检……」 |
| `paper-b-zh` | 13 | 13.6 | 同上 |

逐档试跑后取 `≥4 且 ≤30`：

| 阈值 | `paper-zh` | `paper-b-zh` |
|---|---|---|
| ≥3 / ≤40（初值） | 19 | 13 |
| ≥4 / ≤40 | 4 | 3 |
| ≥4 / ≤30（采用） | 2 | 0 |
| ≥5 / ≤40 | 0 | 1 |

采用档在 `paper-zh` 恰为 2 条（1.82/万字），未超预算，且两条都是真阳性。
这是对初值的收紧，不是原方法的数据；`SPEC-SYNTAX.md` §2.2 已写明。

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
Ran 656 tests in 38.007s

OK
```

### 6.2 `./scripts/preflight-ci.sh --fast`（工作区，含未提交改动）

```
步骤 1/4：外部依赖 —— pdftotext / pdfinfo 齐备
步骤 2/4：干净克隆（--fast：跳过）
步骤 3/4：测试矩阵
   ✓ Python 3.10：Ran 656 tests
   ✓ Python 3.11：Ran 656 tests
   ✓ Python 3.12：Ran 656 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

### 6.3 `python3 scripts/check-readme.py`

```
✓ style --doc 两份 README 均为 0 条
✓ 测试数 656
结论：全过
```

### 6.4 提交后 `./scripts/preflight-ci.sh`（默认模式，干净克隆）

提交后复跑，克隆只含已提交文件（与 6.2 的 `--fast` 同一份代码）：

```
步骤 2/4：干净克隆（只含已提交文件）
步骤 3/4：测试矩阵
   ✓ Python 3.10：Ran 656 tests
   ✓ Python 3.11：Ran 656 tests
   ✓ Python 3.12：Ran 656 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

## 7. 已知边界

- 五条新判据都是「字面串 + 位置 + 计数」，不依赖分词与词性标注；
- 引号/代码块/公式/文献表沿用 `style` 既有遮罩口径，不另开豁免；
- `LIGHT_VERB_NOMINALIZATION` 的动作提示只对 `[light_verbs.actions]` 里
  的词给确切动词；表外名词只提示「还原成对应的动词」，不猜词形；
- `ZH_DE_STACK` 只是单句式，不做全文「的」密度（跨语料差 4 倍，不可移植）。
