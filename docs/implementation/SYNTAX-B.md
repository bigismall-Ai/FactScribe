# SYNTAX-B｜B 档五条判据实施读数（批 105）

日期：2026-11-10｜规范：`docs/design/SPEC-SYNTAX-B.md`｜实施：D 席

## 0. 一句话

五条全部落地：`NOMINALIZATION_RATE`、`ZH_ASPECT_ZHE`、`ZH_DANG_WHEN`、
`ZH_COLLOCATION_REDUNDANCY` 默认开启；`ABBREV_FIRST_USE` 默认关闭，只在
`style --report-abbrev` 时输出。四份本仓语料上，B1/B2/B4 零触发，B3 触发
1 处（真阳性），B5 打开后 13 处（9 真 / 4 假），每份 3.1–5.0 处/万字，
超过准入单的 2 处/万字 → 按准入单第 1 条降级为默认关闭，不硬调阈值。

## 1. 落地清单

| # | 判据 | 错误码 | 单位 | 阈值 | 默认 | 状态 |
|---|---|---|---|---|---|---|
| B1 | 英文名词化密度 | `NOMINALIZATION_RATE` | 每百词百分数 | `> 4.5` | 开 | 落地 |
| B2 | 中文动词＋着 | `ZH_ASPECT_ZHE` | 每千汉字 | `> 0.8` | 开 | 落地 |
| B3 | 当……的时候/之后/时 | `ZH_DANG_WHEN` | 处 | `>= 1` | 开 | 落地 |
| B4 | 搭配冗余 | `ZH_COLLOCATION_REDUNDANCY` | 处 | `>= 1` | 开 | 落地 |
| B5 | 缩写首现 | `ABBREV_FIRST_USE` | 处 | `>= 1` | **关** | 落地（`--report-abbrev`） |

实现落点：

- 判据与词表：`factscribe/style.py`（五条扫描函数在 `analyze()` 里汇总）；
- 阈值、词表、开关：`style-rules.toml`（`[thresholds]`、`[nominalization]`、
  `[zh_aspect_zhe]`、`[zh_dang_when]`、`[zh_collocation_redundancy.items]`、
  `[abbrev_rules]`、顶层 `abbrev_first_use = false`）；
- 命令行：`factscribe/cli.py` 的 `style --report-abbrev`；
- 报告面：`metric_details.nominalization_stripped`（被剥离的 5 个词）、
  `metric_details.zh_aspect_zhe_raw_hits`（密度分子）、
  `metric_details.abbrev_first_use_enabled`（开关状态）；
- 测试：`tests/test_syntax_b.py`（41 例）。

## 2. 四份语料的规模与触发表

预算口径：按条计的新规则每万字 ≤ 2 条（`CONTRIBUTING.md` §2 第 1 条）。
两条密度规则按「是否过阈值」计，不折算条数；原始分子/密度另列。

| 语料 | 计数单元（词/字） | B1 密度 | B2 密度 | B3（/万字） | B4 | B5（/万字） |
|---|---|---|---|---|---|---|
| `paper` | 6,961 | 2.73/百词（未过线） | 0.00（0 命中） | 0 | 0 | 3（4.31） |
| `paper-zh` | 10,969 | 0.00（未过线） | 0.19（2 命中） | **1（0.91）** | 0 | 4（3.65） |
| `paper-b` | 5,983 | 2.09/百词（未过线） | 0.00（0 命中） | 0 | 0 | 3（5.01） |
| `paper-b-zh` | 9,592 | 0.00（未过线） | 0.63（6 命中） | 0 | 0 | 3（3.13） |
| **触发条数** | | **0** | **0** | **1** | **0** | **13（默认关）** |

复算命令（仓根 `paperkit-dev/`）：

```bash
env PYTHONPATH=src python3 -m factscribe style ../paper --json
env PYTHONPATH=src python3 -m factscribe style ../paper-zh --json
env PYTHONPATH=src python3 -m factscribe style ../paper-b --json
env PYTHONPATH=src python3 -m factscribe style ../paper-b-zh --json
# B5 必须显式打开
env PYTHONPATH=src python3 -m factscribe style ../paper --json --report-abbrev
```

B1 的被剥离词（JSON `metric_details.nominalization_stripped`）：

| 语料 | 剥离的 5 个类型 |
|---|---|
| `paper` | `section`、`instance`、`evidence`、`direction`、`harness` |
| `paper-zh` | `harness`、`completion`（该篇只有 2 个类型） |
| `paper-b` | `sentence`、`specification`、`section`、`implementation`、`evidence` |
| `paper-b-zh` | 无（该篇只有 2 个英文词，均不构成名词化） |

## 3. 逐条真假判定

### 3.1 B1 `NOMINALIZATION_RATE`（未触发，抽检 10 个保留命中）

四份语料都没过 4.5/百词，**没有逐条 finding**。为满足准入单第 2 条，
抽检 `paper` 保留命中的前 10 个（剥离 5 个高频词之后）：

| 命中 | 句子 | 判定 |
|---|---|---|
| environment | That filter removes instances whose tests are broken in this environment… | 后缀真（-ment），语义是具体名词，**不是**「动作藏在名词里」 |
| classification | this is the only case where the classification rests on a rerun. | 真（动作：classify） |
| configuration | …the arm selected by a single configuration flag. | 真（动作：configure） |
| experiment | …not the truth of the underlying experiment. | 后缀真（-ment），语义是具体名词 |
| ablation | the main text states the ablation as four hypotheses… | 真（动作：ablate） |
| sequence | Arms ran in sequence on one machine… | 后缀真（-ence），语义是具体名词 |
| citation | every citation must resolve to the bibliography; | 真（动作：cite） |
| document | …before any document is written. | 后缀真（-ment），语义是具体名词 |
| detection | In nine sealed blind sets, first-run detection rose… | 真（动作：detect） |
| version | A style gate from the same toolchain… | 后缀真（-sion），语义是具体名词 |

结论：后缀口径「真」，但约 5/10 是具体名词而非动作名词化。这是 Sword
名词化率的已知粗糙处，也是阈值保持 4.5（而不是 3.0）的原因——保留命中
仍可能混入具体名词，只在密度明显偏高时才值得逐条复核。

### 3.2 B2 `ZH_ASPECT_ZHE`（未触发，原始命中 8 处）

| 语料 | 命中 | 句子 | 判定 |
|---|---|---|---|
| `paper-zh` | 握着 | 我们能测到的瓶颈，不是模型手里握着多少上下文… | 真（V+着，常规进行体） |
| `paper-zh` | 带着 | 终止是账本里的一个事件，带时间戳，带着一份补丁。 | 真（V+着） |
| `paper-b-zh` | 带着 | …科学论文，常常带着读者查不到出处的数字… | 真（V+着） |
| `paper-b-zh` | 带着 | 用语言模型写出的学术文句带着一些规律… | 真（V+着） |
| `paper-b-zh` | 穿着 | …是穿着文风外衣的事实 bug… | 真（V+着，字面「穿着」） |
| `paper-b-zh` | 带着 | …运行记录带着请求与响应的哈希… | 真（V+着） |
| `paper-b-zh` | 带着 | …一条派生事实可能带着与自身取值不一致的表达式通过… | 真（V+着） |
| `paper-b-zh` | 留着 | …也都是有意留着的… | 真（V+着） |

结论：8/8 形态为真，但全部读起来自然，不是「进行体滥用」。密度分别
0.19 与 0.63/千字，低于 0.8，不输出。若把阈值压到 0.5，`paper-b-zh`
会把这 6 句全部报出来（6/6 都是风格假阳性），所以 0.8 是「只在高密度
时提示」的线，不是「逐句抓进行体」的线。

### 3.3 B3 `ZH_DANG_WHEN`（触发 1 处，1 真 / 0 假）

| 语料:行 | 句子 | 判定 |
|---|---|---|
| `paper-zh` sections/04_mechanisms.tex:59 | 当两套约定不一致时，两套都印在这条主张旁边。 | 真（`当…时`；删「当/时」后更短） |

首版正则 `当[^。！？\n]{1,40}?(的时候|之后|时)` 在四份语料触发 4 处，
其中 2 处一眼是假阳性：`当成可靠坐标时`（`当成`＝treat as）与
`……没说它什么时候跑`（`什么时候` 的「时」）。收紧为：

- 冒号/分号也切断匹配；
- `时` 后不能跟 `候`；
- `当` 后紧跟 `成/作/然/当/天…` 时跳过。

第二版在 `paper-zh` 还剩 2 处，其中
`只有当运行时把决定权拿走，任务才被解决。` 仍是假阳性：这里的
「运行时」是名词 runtime，「时」不是「当…时」的尾巴。第三版补一条：

- 尾巴后面必须是停顿（`，,、：:；;。！？!?`）、句末，或主句标记
  （`才/就/则/便/方`）；`时` 后面跟「把」说明它是「运行时」的一部分。

收紧后 `paper-b-zh` 归零，`paper-zh` 只剩 1 处真阳性。触发量
1 / 10,969 字＝0.91/万字，在 2/万字预算内。

### 3.4 B4 `ZH_COLLOCATION_REDUNDANCY`（四份语料 0 处）

十条词表在四份语料上一次都没命中：论文里没有「大约…左右/唯一一个/
相互之间/彼此互相/提前预…/免费赠送/亲眼目睹/再次重申/一致公认/
首先第一」。0 触发即 0 假阳性；词表本身用 10 条正例 + 1 组负例锁在
`tests/test_syntax_b.py`。

### 3.5 B5 `ABBREV_FIRST_USE`（打开后 13 处，9 真 / 4 假）

| # | 语料:行 | 缩写 | 句子（截断） | 判定 |
|---|---|---|---|---|
| 1 | paper abstract:4 | SWE | On a 16-instance subset of SWE-bench Verified… | **假**：基准专名，不是待展开缩写 |
| 2 | paper abstract:6 | CLI | …against 12,495 for the official mcode CLI. | 真（Command Line Interface 未展开） |
| 3 | paper related:12 | RULER | …and RULER shows that the effective context… | **假**：基准专名 |
| 4 | paper-zh abstract:9 | SWE | 在 SWE-bench Verified 的一个 16 题子集上… | **假**：基准专名 |
| 5 | paper-zh abstract:11 | CLI | …官方 mcode CLI 是 12,495。 | 真 |
| 6 | paper-zh related:12 | RULER | RULER 表明当前模型的有效上下文… | **假**：基准专名 |
| 7 | paper-zh related:21 | API | Toolformer 让模型学会何时调用 API； | 真（Application Programming Interface 未展开） |
| 8 | paper-b intro:13 | PDF | …survives into the compiled PDF… | 真（后缀口径），但通用缩写 |
| 9 | paper-b design:58 | OCR | …the gate runs no OCR… | 真，但通用缩写 |
| 10 | paper-b style:32 | CV | …a very low sentence-length CV is reported… | 真（coefficient of variation 未展开） |
| 11 | paper-b-zh intro:6 | PDF | 一条排版用的注释活进了编译出的 PDF… | 真，但通用缩写 |
| 12 | paper-b-zh design:24 | OCR | …闸门不做 OCR… | 真，但通用缩写 |
| 13 | paper-b-zh style:14 | CV | …句长 CV 过低会报「过于均匀」… | 真 |

合计 13 处：真 9、假 4（30.8%），假阳性未过半；但每份语料 3.1–5.0
处/万字，**全部超过 2 处/万字预算**。按准入单第 1 条「超过 2/万字即调
阈值或降级」，本规则降级为默认关闭，只在 `--report-abbrev` 时输出。
没有为了压数而删掉 PDF/OCR/CV：它们按规则确实是「首现未展开」，问题在
规则把专名与通用缩写一视同仁，删词表也救不回精度。

## 4. 阈值来历

| 判据 | 阈值 | 来历 |
|---|---|---|
| B1 | 4.5/百词 | Sword 裸线是 6%；四份语料剥离后实测 2.09–2.73，6% 永远打不到。取 4.5（约为实测上限的 1.65 倍）：只抓明显高于本仓真实论文的稿子，同时保留可触发空间。 |
| B2 | 0.8/千字 | B 计划实测区间 0.25↔1.50；本仓自然稿是 0.19–0.63。0.5 会把 `paper-b-zh` 的 6 句自然「带着/留着」全报出来；0.8 在自然稿之上、滥用稿之下。 |
| B3 | 1 处 | 按条报，不设密度闸。1/10,969 字＝0.91/万字，在预算内。 |
| B4 | 1 处 | 按条报。四份语料 0 处，属防回归词表。 |
| B5 | 1 处（默认关） | 按条报；因 3.1–5.0/万字超预算而降级，阈值本身不调（调高会漏掉真阳性，调低更超）。 |

## 5. 测试

`tests/test_syntax_b.py`：**42 例**。每条规则的覆盖：

| 判据 | 正例 | 负例 | 反向锁/配置 |
|---|---|---|---|
| B1 | 5 | 3 | 中文语料 0；`strip_top` 可配；单位＝15.79/百词 |
| B2 | 4 | 3 | 英文 0；阈值可配；原始分子可查 |
| B3 | 3 | 5 | `paper-b-zh` 原句 0；`运行时` 不误报；冒号不跨 |
| B4 | 10（词表逐条） | 3 | 英文 0；跨句不报；词表 10 条 |
| B5 | 4 | 5 | 已展开语料 0；默认关；CLI 开关 |

全量回归：**750 例**（批 105 前 708 例，新增 42 例）。`tests/test_docmode.py`
的 `EXPECTED_METRICS` 已加 5 个新键（`abbrev_first_use`、
`nominalization_rate`、`zh_aspect_zhe`、`zh_collocation_redundancy`、
`zh_dang_when`）。

## 6. 门禁输出

### 6.1 `env PYTHONPATH=src python3 -m unittest discover -s tests`

```
Ran 750 tests in 33.6s
OK
```

### 6.2 `./scripts/preflight-ci.sh --fast`（提交前，工作区含未提交改动）

```
步骤 1/4：pdftotext / pdfinfo 齐备
步骤 3/4：Python 3.10 / 3.11 / 3.12 各 Ran 750 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

### 6.3 `python3 scripts/check-readme.py`

```
✓ style --doc 两份 README 均为 0 条
✓ 测试数 750
结论：全过
```

### 6.4 提交后 `./scripts/preflight-ci.sh`（默认模式，干净克隆）

提交后复跑，克隆只含已提交文件（与 6.2 的 `--fast` 同一份代码）：

```
步骤 2/4：干净克隆（只含已提交文件）
步骤 3/4：测试矩阵
   ✓ Python 3.10：Ran 750 tests
   ✓ Python 3.11：Ran 750 tests
   ✓ Python 3.12：Ran 750 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

## 7. 已知边界

1. **B1 是后缀计数，不是语义判断。** `environment / experiment / document /
   sequence / version` 这类具体名词也会计入。剥离 5 个高频类型能压住
   术语密集论文，但压不住「具体名词刚好不多不少」的稿子。阈值 4.5 与
   「逐条复核」是配套的。
2. **B2 只给密度信号。** 真正在进行的动作也被计入分子；不过线不报，
   过线后逐条由人判断。固定词表（`exclude`）只排词内「着」，不排
   正常进行体。
3. **B5 的「首次出现」按分析顺序。** 项目模式下 `load_sections` 的文件
   顺序不保证等于 PDF 阅读顺序（`appendix/` 可能排在 `sections/` 前）；
   若附录先提到缩写、正文才展开，会多报一条。默认关闭使这个边界不进
   日常读数。
4. **B3/B4 是中文专用。** 英文语料上不可能触发，反向锁已写成测试。
5. **密度单位写死。** B1 是每百词，B2 是每千汉字；二者都不是每千词，
   混用会差 10 倍。配置注释与本件 §2/§4 三处同写。
