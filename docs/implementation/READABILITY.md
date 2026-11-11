# READABILITY｜读者感觉三项代理判据的实施记录（批 129）

> 规范：`docs/design/SPEC-READABILITY.md`。本件只记实现落位、集成点、测试与
> 真材料读数；判据口径以规范为准。

## 1. 改动清单

| 路径 | 内容 |
|---|---|
| `factscribe/style.py` | 三条判据的实现与 `analyze` 集成；三档配置；`metric_details` |
| `style-rules.toml` | 三条阈值、`[we_action]` 词表（`numeral_density_stage` 批 130 起移出：只由命令行 `--stage` 控制） |
| `factscribe/patterns/thin-the-numbers/RULE.md` | 第 11 条处方（`NUMERAL_DENSITY`） |
| `factscribe/patterns/merge-overlap/RULE.md` | 第 12 条处方（`SECTION_OVERLAP`） |
| `factscribe/patterns/shift-to-implication/RULE.md` | 第 13 条处方（`WE_ACTION_DENSITY`） |
| `factscribe/patterns/priority.toml` | 三条处方的优先序登记 |
| `factscribe/patterns/PLAYBOOK.md` | 速查表从十条扩到十三条 |
| `factscribe/polish.py` | 三条处方的「约束一句话」 |
| `tests/test_readability_rules.py` | 18 例契约测试 |
| `tests/test_polish.py` / `test_prescription.py` / `test_docmode.py` | 处方数与基线读数随批更新 |
| `docs/design/SPEC-PRESCRIPTION.md` | 处方表与 §5.11–§5.13 |

## 2. 集成点

`analyze()` 在 `instances` 初始化后、句法级判据之前跑三条：

- `_numeral_density_findings(docs, threshold, stage, root_file)`：
  逐节算密度；`stage=="revision"` 时返回 `info` 通道；容器主文件跳过。
- `_section_overlap_findings(docs, threshold, root_file)`：
  `_blocks_of` 按标题切块 → `_shingle_map` 做 8 词/12 字片段 →
  两两求「共有 ÷ 较短一节」；少于 20 片段的小块不判。
- `_we_action_findings(sentences, rules)`：
  在 `all_sentences` 上判主语＋动作动词；一条汇总命中，附前 10 条例句。

三条指标进入 `metrics`：

```json
{
  "numeral_density": 73.7,
  "section_overlap": 19.7,
  "we_action_density": 0.015
}
```

`metric_details` 增加：

- `numeral_density_stage`、`numeral_density_sections`；
- `section_overlap_pairs`；
- `we_action_density`（`hits / sentences / ratio / examples`）。

触发判定沿用 `DIRECTIONS` 的 `above` 分支；`numeral_density` 多一个
`stage != "revision"` 条件。退出码仍由 `fired` 决定：有命中 `3`，无命中 `0`。

## 3. 与保护面的冲突

删数字会触发 `PROTECT_NUMBER_CHANGED`。实现不猜项目是否在验收，阶段
**只从命令行来**（批 130）：

- 默认 `--stage draft`：正常黄牌；
- `--stage revision`：读数照算，命中转 `info`，建议文字明写保护面原因，
  不改退出码；
- 项目内 `style-rules.toml` 写 `numeral_density_stage` 一律不读，只输出
  `RULES_OVERRIDE_IGNORED` 告警（列出被忽略的键）。

`thin-the-numbers` 的「必做」第 1 条、`PLAYBOOK.md` 与规范 §1.4 都要求
进入改写验收时用 `style --stage revision`。

## 4. 测试

`tests/test_readability_rules.py` 共 **18 例**：

| 组 | 例数 | 覆盖 |
|---|---|---|
| `NUMERAL_DENSITY` | 6 | 英文正/负、英文阈值边界（40 不报/50 报）、中文正例与边界（300 汉字 12 个=40 不报，13 个报）、`stage=revision` 降 info、项目内 stage 键被忽略并告警 |
| `SECTION_OVERLAP` | 5 | 英文真重复（100%）、英文只引用同一事实（不报）、中文真重复、中文只引用同一事实（不报）、阈值边界（100 不报/99 报） |
| `WE_ACTION_DENSITY` | 5 | 英文正例、`we propose/claim/argue/believe/suggest` 不计入、中文正例、`我们提出/主张/认为/建议` 不计入、阈值边界（0.5 不报/0.49 报） |
| 处方映射 | 2 | 三条码各自映射到 `thin-the-numbers` / `merge-overlap` / `shift-to-implication`；三条都不再是「无处方」 |

全仓测试：`982 tests ... OK`（本批新增 `test_readability_rules.py` 18 例；
既有测试只更新处方数与 `examples/minimal` 基线读数）。

## 5. 真材料读数

命令：

```bash
python3 -m factscribe style <项目> --json
python3 -m factscribe polish --plan <项目>
```

### 5.1 三篇材料

| 材料 | 词/字 | `numeral_density`（最高节） | `section_overlap`（最高对） | `we_action_density` |
|---|---|---|---|---|
| `/tmp/draft3/proj`（英文草稿） | 7183 | 73.7（结论节 14/190） | 19.7%（讨论「What We Would Do Differently」↔ 限制「Known Gaps」） | 0.015（6/409） |
| `../paper-b`（英文定稿） | 6012 | 73.7（结论节 14/190） | 4.8% | 0.017（6/359） |
| `../paper-b-zh`（中文定稿） | 9645 | 50.7（结论节 14/276） | 5.6% | 0.008（3/376） |

### 5.2 触发条数

| 材料 | `NUMERAL_DENSITY` | `SECTION_OVERLAP` | `WE_ACTION_DENSITY` | 合计 | 每万字 |
|---|---|---|---|---|---|
| 草稿 draft3 | 4 节 | 1 对 | 0 | 5 | **6.96** |
| paper-b | 3 节 | 0 | 0 | 3 | 4.99 |
| paper-b-zh | 2 节 | 0 | 0 | 2 | 2.07 |

草稿每万字 6.96 条，超过 5 条，逐条核对如下：

- **真报 1 条**：讨论节 64 个数字 / 1171 词 = 54.7/千词，正是读者说的
  「数字太密」；本轮新增的讨论节的读数列表也确实密集。
- **真报 1 条**：讨论「What We Would Do Differently」与限制「Known Gaps」
  重合 24 个 8 词片段 / 较短节 122 个 = 19.7%，正是读者说的「末段与
  Limitations 重复」；定稿 paper-b 只有 4.8%，说明这段重复是草稿新增的。
- **可能是误报 3 条**：摘要（12/213 = 56.3）、结论（14/190 = 73.7）、
  `04_style_case`（100/1431 = 69.9）都是「结果/数字摘要」型小节，数字
  本身就是内容。`NUMERAL_DENSITY` 只数 token，不区分结果节与叙事节；
  这三条按 §4 的已知边界应人工排除，不能为过判据删结果数字。
- `WE_ACTION_DENSITY` 在草稿上只有 1.5%（6/409），**未触发**；读者感觉的
  「我们做了什么多于这意味着什么」在这份草稿里不是动作句密度问题，更可能
  是讨论节缺少「所以呢」句。该判据在本材料上不误报，但也不命中；需要更
  细的语义判据才能抓住，超出本批代理量的能力。

### 5.3 `polish --plan` 映射

`polish --plan /tmp/draft3/proj` 共 19 条：有处方 5 条（`SECTION_OVERLAP`
→ `merge-overlap` 1 条；`NUMERAL_DENSITY` → `thin-the-numbers` 4 条），
其余 14 条是 `RHYTHM_PLATEAU` 的无处方参考读数。

`WE_ACTION_DENSITY` 在本材料未触发，所以本次工作单里没有
`shift-to-implication` 行；映射本身由 `tests/test_readability_rules.py`
的三码映射例锁定（三条都能映射到各自处方）。定稿 paper-b / paper-b-zh
的 `section_overlap` 与 `we_action_density` 都在阈值内，只有数字密度在
摘要/结果/结论节命中，同上按结果节误报人工排除。

## 6. 已知缺口

- `SECTION_OVERLAP` 只认字面片段，同义改写的语义重复抓不到；草稿这轮
  能抓到，是因为重复段落几乎逐字复制。
- `WE_ACTION_DENSITY` 的默认动词表只收规范点名的九个动作词及常见屈折；
  `we built`、`we wrote` 不在表内。扩表会改变读数，按「改表即改判据」
  处理，需要单独批次与基线更新。
- `NUMERAL_DENSITY` 对短节（摘要、结论）与结果节偏严，已知误报面见 §5.2；
  本批不引入「按节类型豁免」——那需要新的节分类判据，不在本批范围。

## 7. 批 130：规则覆盖可见化（开关只能在被测物之外）

### 7.1 缺陷

一次「按工作单修数字密度」的实验里，模型没改正文，只在项目根新建
`style-rules.toml` 写 `numeral_density_stage = "off"`，`NUMERAL_DENSITY`
就降为 `info`，检查消失。它还引用旧文档说「改稿阶段就该关」——照文档做，
结果绕过了检查。根因：判据开关放在被测物里，被测物可以自己关掉判据。

### 7.2 改动

| 路径 | 内容 |
|---|---|
| `factscribe/style.py` | `CLI_ONLY_RULE_KEYS`；装载时剥离 `numeral_density_stage`；`project_rule_report()` 逐键比较；`analyze(stage=..., rule_report=...)`；`StyleResult` 增加 `rule_overrides / rule_warnings / stage` |
| `factscribe/cli.py` | `style --stage draft\|revision`；`style` / `style --doc` / `audit` 输出覆盖行与 `RULES_OVERRIDE_IGNORED`；JSON 增加 `rule_overrides / rule_warnings / stage` |
| `factscribe/review.py` | 复用同一份覆盖读数，`review` 汇总里打印「本项目覆盖了 N 个规则键」；JSON `style.rule_overrides` |
| `style-rules.toml` | 删除已无意义的 `numeral_density_stage` 键，注释改为命令行 `--stage` |
| `factscribe/patterns/thin-the-numbers/RULE.md`、`factscribe/polish.py`、`docs/design/SPEC-PRESCRIPTION.md` | 把「项目里设 off」的旧指令改为 `style --stage revision`，并注明项目内写了不生效 |
| `docs/design/SPEC-READABILITY.md` | §1.4 重写，新增 §1.5「开关只能在被测物之外」原则 |
| `tests/test_rule_override.py` | 13 例门禁测试 |

覆盖清单只列与内置默认**不同**的键（点号路径，如
`thresholds.dash_budget`）；把默认文件整份抄进项目不会报几十个覆盖。
覆盖是收紧还是放宽机器无法判断，所以只列键名、不评判；不进 findings、
不改退出码。`audit` 的读数只报告，不装载规则、不影响审计判据。

### 7.3 验收读数

复现原场景（`/tmp/loop2` 是 `/tmp/loop/proj` 的副本，项目内
`style-rules.toml` 第 38 行仍写着 `numeral_density_stage = "off"`）：

```bash
python3 -m factscribe style /tmp/loop2 --json
python3 -m factscribe style /tmp/loop2 --stage revision --json
```

| 读数 | 默认（draft） | `--stage revision` |
|---|---|---|
| 退出码 | **3** | **0** |
| `findings` 里的 `NUMERAL_DENSITY` | **4 条**（摘要 56.3、结果案例 69.9、结论 73.7、讨论 56.6，均 /千词） | 0 条 |
| `info` 里的 `NUMERAL_DENSITY` | 0 条 | **4 条**（同一组读数） |
| `metric_details.numeral_density_stage` | `draft` | `revision` |
| `rule_warnings` | `RULES_OVERRIDE_IGNORED`（`numeral_density_stage`） | 同左 |
| `rule_overrides` | `count=2`：`heading_substitute.heading_period_exempt`、`zh_dang_when.min_per_paragraph` | 同左 |

`style` 人读输出（默认）前 5 行：

```
覆盖    : 本项目覆盖了 2 个规则键：heading_substitute.heading_period_exempt、zh_dang_when.min_per_paragraph
规则告警：RULES_OVERRIDE_IGNORED（项目内 style-rules.toml 设置了只允许命令行控制的键：numeral_density_stage。这些键已被忽略；阶段开关请用 style --stage draft|revision。）
```

`review --before /tmp/loop/proj_before --after /tmp/loop2` 的汇总里也带同一
行覆盖；该次判定为「需复核（exit 3）」，复检新增 1 条
`NUMERAL_DENSITY`（讨论节 56.6/千词）——项目里写 `off` 再也藏不住它。

### 7.4 测试

`tests/test_rule_override.py` 共 **13 例**：

| 组 | 例数 | 覆盖 |
|---|---|---|
| 项目内 `off` 失效 | 3 | JSON 仍触发且 `stage=draft`；`RULES_OVERRIDE_IGNORED` 带键名；人读输出含告警 |
| 命令行阶段开关 | 3 | `revision` 降 info、退出 0；`draft` 显式默认仍触发；阶段不改读数 |
| 普通键仍可覆盖 | 3 | 阈值 100 生效；覆盖清单键名；人读覆盖行 |
| `review` 看得见 | 2 | 人读含覆盖行；JSON `style.rule_overrides` |
| 无规则文件行为不变 | 1 | 无覆盖行、无告警、判据照常 |
| `audit` 看得见 | 1 | JSON `rule_overrides` 与真值一致；人读含覆盖行 |

全仓：`995 tests ... OK`。
