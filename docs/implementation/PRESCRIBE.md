# 处方层实施记录（批 92）

> 规范：`docs/design/SPEC-PRESCRIPTION.md`。
>
> 本批只新增处方层：`factscribe/prescribe.py`、`factscribe/patterns/`、
> `prescribe` 子命令与测试。**未改** `style.py` / `terms.py` / `tide.py`；
> `audit` / `protect` 的判据与退出码未动。处方不产生 findings、不产生分数，
> 成功永远退出 `0`。

## 1. 交付物

| 路径 | 内容 |
|---|---|
| `factscribe/prescribe.py` | 装载 RULE.md、错误码查询、冲突裁决、`让位` 渲染 |
| `factscribe/patterns/priority.toml` | 五级优先序 ＋ 显式冲突对 |
| `factscribe/patterns/<name>/RULE.md` | 六条处方数据（六段固定结构） |
| `factscribe/cli.py` | 注册 `prescribe` 子命令（唯一改动的既有文件） |
| `tests/test_prescription.py` | 38 例契约测试 |
| `docs/design/SPEC-PRESCRIPTION.md` | 规范（冻结） |
| `docs/implementation/PRESCRIBE.md` | 本件 |

## 2. 六条处方

| # | 名称 | 治的判据（错误码） | 优先序 | 反例（坏改法） |
|---|---|---|---|---|
| 1 | `heading-shorten` | `HEADING_TOO_LONG` | 3 标题指向内容 | `提示词对机制` → `提示词`（删掉对比对象「机制」） |
| 2 | `term-first-sentence` | `HEADING_ECHO`、`TERM_FIRST_IN_HEADING` | 4 术语首现解释 | 复述标题、`相关工作里，……` 垫话、`什么是 X？` 设问 |
| 3 | `dash-rewrite` | `DASH_PARENTHETICAL` | 5 文句风格 | `——` → `–`（换成另一个破折号） |
| 4 | `heading-malformed` | `HEADING_MALFORMED`、`HEADING_RELATION_CHANGED` | 3 标题指向内容 | `Prompt versus mechanism` → `Prompt or mechanism`（替换关系词） |
| 5 | `heading-subject-keep` | `HEADING_SUBJECT_LOST`、`HEADING_RELATION_CHANGED` | 2 结构完整 | `提示词对机制` → `提示词`（第二个对象消失） |
| 6 | `section-completeness` | `SECTION_INCOMPLETE` | 2 结构完整 | `本节讨论 X。`（只有任务，没有结论） |

- 六条均为中文，逐条含「禁做（含反例）」与「改写示例（旧 → 新）」；
  测试机械断言每条禁做段同时出现「反例」与 `→`，示例段出现「旧」「新」。
- `SECTION_INCOMPLETE` 是处方层自有检查码：`style` 不产生它，处方层也不反向
  给 `style` 增加判据。检查点转述自 XtraGPT 的 20 条学术写作标准里与章节
  组织相关的项（不抄原文措辞）。
- 五个既有判据码全部有处方可查：`HEADING_ECHO` → `term-first-sentence`；
  `HEADING_MALFORMED` → `heading-malformed`；`TERM_FIRST_IN_HEADING` →
  `term-first-sentence`；`DASH_PARENTHETICAL` → `dash-rewrite`；
  `HEADING_SUBJECT_LOST` → `heading-subject-keep`。

## 3. 冲突优先序

| 序号 | 级别 | 名称 |
|---|---|---|
| 1 | `facts` | 事实与数字 |
| 2 | `structure` | 结构完整 |
| 3 | `heading` | 标题指向内容 |
| 4 | `term` | 术语首现解释 |
| 5 | `style` | 文句风格 |

显式登记两条冲突对（`factscribe/patterns/priority.toml`）：

1. `heading-shorten`（3）vs `heading-subject-keep`（2）：
   压标题不得丢掉对比对象与主语 → 保结构胜。
2. `heading-malformed`（3）vs `heading-subject-keep`（2）：
   去标题标点不得删掉对比对象或替换关系词 → 保结构胜。

同一冲突对必须落在不同序号，加载期校验；违反即退出码 `2`。两条一起输出时
序号小的在前，被压制的一条明写：

```
===== 处方 2/2：heading-shorten（优先序 3 标题指向内容）=====

让位：与 heading-subject-keep 冲突（压标题不得丢掉对比对象与主语）；按优先序 2 < 3 让位，本处方不执行。
```

只输出单条处方时不写「让位」（没有对手在场）。

## 4. CLI

```
python3 -m factscribe prescribe <name|--list> [--for <错误码>] [--json]
```

实测：

```
$ env PYTHONPATH=src python3 -m factscribe prescribe --list
== factscribe prescribe ==
处方：6 条（只给改法；不参与判据、不产生分数）

heading-subject-keep   优先 2 结构完整     HEADING_SUBJECT_LOST、HEADING_RELATION_CHANGED
section-completeness   优先 2 结构完整     SECTION_INCOMPLETE
heading-malformed      优先 3 标题指向内容   HEADING_MALFORMED、HEADING_RELATION_CHANGED
heading-shorten        优先 3 标题指向内容   HEADING_TOO_LONG
term-first-sentence    优先 4 术语首现解释   HEADING_ECHO、TERM_FIRST_IN_HEADING
dash-rewrite           优先 5 文句风格     DASH_PARENTHETICAL
```

- `prescribe <name>`：stdout 逐字节等同 `RULE.md`（去尾空白）；
- `prescribe --for <CODE>`：输出绑定该码的处方；有冲突时附「让位」；
- `prescribe --for NO_SUCH_CODE`：退出 `0`、空清单（合法结果，不是错误）；
- 未知处方名、缺参数、处方缺段、优先序非法：退出 `2`；
- 成功路径永不返回 `1` / `3`。

`--for HEADING_RELATION_CHANGED` 会同时命中 `heading-subject-keep`（2）与
`heading-malformed`（3），输出中 `heading-malformed` 带「让位」——这是冲突
机制在真实查询上的体现。

## 5. 与判据完全隔离——怎么证的

四条硬约束（`SPEC-PRESCRIPTION` §2）＋三项机械证据：

1. **源码层**：`style.py` / `terms.py` / `tide.py` 里没有 `prescribe` 字样
   （测试 `test_style_sources_do_not_mention_prescribe` 逐个 grep）。
2. **行为层（最硬）**：把整个 `factscribe/` 包复制到临时目录并**删掉
   `patterns/`**，对同一个项目跑 `style --json`，与正常包的结果比较：
   `findings`、`metrics`、`exit` 三项逐项相同
   （`test_style_works_without_patterns_data`）。判据不读处方数据，处方在不在
   场都不改变读数。
3. **输出层**：`style` 的 findings 里不出现任何处方名或处方段落标记
   （`## 必做` / `## 禁做` / `## 验收命令`），且 findings 的码集合仍是
   `style` 既有码（`test_prescription_text_never_appears_in_style_findings`、
   `test_style_finding_codes_stay_in_style_registry`）。
4. **载荷层**：`prescribe --json` 没有 `findings` / `score` / `grade` /
   `passed` 字段，`exit` 恒为 `0`、`severity` 恒为 `ok`
   （`test_prescribe_json_has_no_findings_or_scores`）。

因此：**处方既不进判据，也不从判据读分；两边只有「错误码」这一个只读的
字符串接口。**

## 6. 测试

`tests/test_prescription.py`：**38 例**（全离线）。分组：

| 组 | 例数 | 覆盖 |
|---|---|---|
| 清单与六段 | 6 | 恰好 6 条、六段齐全、优先序/绑定字段、五个既有码全覆盖 |
| `--for` | 5 | 五个码都能查、映射正确、未知码退 0 且空 |
| CLI 原文 | 4 | 单名逐字节等同 RULE.md、JSON 字段、未知名/缺参退 2 |
| 隔离 | 5 | findings 无处方文字、码集合不变、删 patterns 后读数相同、载荷无分数、源码无引用 |
| 冲突优先序 | 6 | 五级与规范一致、冲突对不同序号、低序号胜、渲染含「让位」、无冲突不写、CLI 多名字 |
| 处方质量 | 7 | 六条验收命令可执行、每条有反例、每条有旧→新、关键反例在文 |
| 解析 fail-closed | 4 | 缺段/缺码绑定报错、好文件可解析、错误类型是配置错 |
| 规范文档 | 1 | 规范列出六条、五级与「让位」 |

全量：`env PYTHONPATH=src python3 -m unittest discover -s tests` →
**Ran 496 tests ... OK**（基线 458 ＋ 本批 38）。

## 7. 门禁输出

工作区（`--fast`，3.10 / 3.11 / 3.12）：

```
== 步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12）
   ✓ Python 3.10：Ran 496 tests
   ✓ Python 3.11：Ran 496 tests
   ✓ Python 3.12：Ran 496 tests
== 步骤 4/4：验收样例必须 exit 1（workflow 的硬断言）
   ✓ examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

提交后干净克隆门禁（`./scripts/preflight-ci.sh`，只含已提交文件）：

```
== 步骤 2/4：干净克隆（只含已提交文件——夹具缺源文件这里就会暴露）
   ✓ 克隆到 .../repo（HEAD 为本批提交）
== 步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12）
   ✓ Python 3.10：Ran 496 tests
   ✓ Python 3.11：Ran 496 tests
   ✓ Python 3.12：Ran 496 tests
== 步骤 4/4：验收样例必须 exit 1（workflow 的硬断言）
   ✓ examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

两次门禁（工作区 `--fast` 与干净克隆）读数一致：三个 Python 版本均为
`Ran 496 tests`，验收样例均按预期 `exit 1`。
