# 篇幅预算实施记录（批 128）

> 规范：`docs/design/SPEC-BUDGET.md`。
> 新增 `paperkit.toml` 可选节 `[budget]`、`style` 黄牌判据 `SECTION_LENGTH`、
> 处方第 10 条 `trim-to-budget`、`polish --plan` 映射、`brief` 篇幅预算列；
> **未改**任何既有判据的取值与退出码；零第三方依赖（纯标准库）。

一句话：给项目配一份篇幅预算，`style` 判出「哪一节写超了、超多少」，
`polish --plan` 把它派给「先删重复、再删举例、最后合并同义句」的处方，
`brief` 在起草前就把同一份预算摆给写作模型看。

## 1. 交付物

| 路径 | 内容 |
|---|---|
| `factscribe/config.py` | `[budget]` 读取与校验、`section_budget()` 取某节预算；3.10 极简 TOML 解析器支持点号表名（`[budget.sections]`） |
| `factscribe/style.py` | `SECTION_LENGTH` 判据＋`section_length` 指标＋逐节读数 `metric_details.section_budget` |
| `factscribe/patterns/trim-to-budget/RULE.md` | 第 10 条处方（六段固定结构） |
| `factscribe/patterns/priority.toml` | `trim-to-budget = "style"`（优先序 5） |
| `factscribe/patterns/PLAYBOOK.md` | 速查表补第 10 条、§5 补「禁止拆句凑数」反例 |
| `factscribe/polish.py` | `CONSTRAINTS["trim-to-budget"]`（工作单的「约束」列） |
| `factscribe/brief.py` | 节清单「篇幅预算」列、`--json` 的 `sections[i].budget` |
| `tests/test_budget.py` | 17 例契约测试（新增） |
| `tests/test_polish.py` / `tests/test_prescription.py` | 增补 `SECTION_LENGTH` 映射与第 10 条可查、六段齐 |
| `docs/design/SPEC-BUDGET.md` | 配置、计数口径、判据、处方、映射、brief、失败面 |
| `docs/implementation/BUDGET.md` | 本件 |

## 2. 实现要点

### 2.1 配置（`config.py`）

- `_parse_budget()` 读 `[budget]`：`default` 与 `[budget.sections]`，值必须是
  正整数（布尔/字符串/0/负数一律 `ConfigError`，退出码 2）；
- 没有 `[budget]`：`budget_defined=False`，判据整体不跑；
- `section_budget(cfg, file)`：键＝`Path(file).stem`，按节覆盖优先，其次
  `default`；都没有返回 `0`（该节不判，不是「预算 0」）；
- 3.10 无 `tomllib` 时的极简解析器原来把 `[budget.sections]` 存成扁平键
  `"budget.sections"`；本批让它按点号分段建表（`budget → sections`），
  并在读取端兼容旧扁平形态。

### 2.2 判据（`style.py`）

- 正文单元复用 `units_of(prose_of(...))`：英文按词、中文按汉字；注释、
  标题命令、公式、`\cite`、`\fact{ID}` 的 ID 参数都不计；
- 触发条件：`实际 > 预算 × (1 + 20%)`，**严格超过**（正好 120% 不报）；
  20% 来自 `style-rules.toml` 的 `thresholds.section_length_excess_percent`，
  默认 `20.0`；
- 每超一节一条黄牌，消息固定三项读数：
  `本节 1431 词 / 预算 800 词（超出 78.9%）`（中文节写「字」）；
- 指标 `section_length`＝超预算最狠的百分比（都不超时 `0.0`）；
- `metric_details.section_budget` 逐节列 `{file, actual, budget, excess_percent}`
  （未超记 `0.0`），按文件排序，输出确定；
- 主文件（`root_tex`）与剥成空白的文件不判——那是容器，不是一节。

### 2.3 处方与映射

`trim-to-budget` 绑 `SECTION_LENGTH`、优先序 `style`（5）。六段要点：

| 段 | 内容 |
|---|---|
| 必做 | 先删重复引用的数字 → 再删举例 → 最后合并同义句 → 压完再数 |
| 禁做 | 不删论点、不删每个论点的最后一条证据、不把句子改短来凑数（拆句词数不降） |
| 正例 | 一段 180 词压到 120 词，论点与证据都在 |

`polish --plan` 的映射由处方数据的 `- 错误码：` 行决定，`polish` 不写第二张表；
`CONSTRAINTS` 只加一句「约束」（改什么、不许动什么），不是新判据。

### 2.4 brief

第 1 节节清单加「篇幅预算」列（值来自同一份 `[budget]`，没有则 `—`），
`--json` 的每行多一个 `budget` 字段（`0`＝无预算）。

## 3. 真实材料读数（paper-b）

`paper-b` **不进仓**：只在 `/tmp` 副本上加预算，仓库里的 `paper-b` 一个字没动。

```bash
cp -R ../paper-b /tmp/budget-probe
# 在 /tmp/budget-probe/paperkit.toml 追加：[budget] default = 800
python3 -m factscribe style /tmp/budget-probe --json
python3 -m factscribe polish --plan /tmp/budget-probe
python3 -m factscribe brief /tmp/budget-probe
```

### 3.1 `style`：4 节超预算（退出码 3）

| 节 | 实际 | 预算 | 超出 |
|---|---|---|---|
| `sections/01_intro.tex` | 967 词 | 800 | 20.9% |
| `sections/03_design.tex` | 1036 词 | 800 | 29.5% |
| `sections/04_style_case.tex` | 1431 词 | 800 | 78.9% |
| `sections/05_blind.tex` | 1039 词 | 800 | 29.9% |

其余四节在预算内（`00_abstract` 213、`02_related` 551、`06_limits` 558、
`07_conclusion` 190）。指标 `section_length=78.9`。

按节覆盖也验过：把 `"04_style_case" = 1600` 加进 `[budget.sections]` 后，
该节不再报（1431 ≤ 1600 × 1.2），其余三节照报——覆盖只作用于自己那一节。

### 3.2 `polish --plan`：4 条映射到 `trim-to-budget`

```text
条目：17（有处方 4，无处方 13）
1  sections/01_intro.tex:4        SECTION_LENGTH  trim-to-budget  ...
2  sections/03_design.tex:4       SECTION_LENGTH  trim-to-budget  ...
3  sections/04_style_case.tex:6   SECTION_LENGTH  trim-to-budget  ...
4  sections/05_blind.tex:6        SECTION_LENGTH  trim-to-budget  ...
```

`SECTION_LENGTH` 不再落到「无处方」。

### 3.3 `brief`：节清单带预算列

```text
| # | 文件 | 当前标题 | 该节已有事实条数 | 篇幅预算 |
| 1 | `sections/00_abstract.tex` | （无标题） | 6 | 800 |
| 2 | `sections/01_intro.tex` | Introduction | 12 | 800 |
...
```

同一篇不带 `[budget]` 时，该列全部写 `—`（向后兼容，旧项目输出只多一列）。

## 4. 测试

```bash
python3 -m unittest discover -s tests
# Ran 964 tests ... OK
```

新增 `tests/test_budget.py` 17 例：英文超/不超/正好 120% 边界、中文按汉字、
混排相加、无 `[budget]` 不跑、只写节不写 `default`、按节覆盖、章节与附录
分开算、LaTeX 命令与注释不计、空白文件不判、非法配置退出 2、逐节读数与
`--json` 形状、`brief` 预算列与 `—`。

增补：`tests/test_polish.py`（`SECTION_LENGTH` 在 plan 里有处方，单元＋CLI
两路）、`tests/test_prescription.py`（第 10 条可查、六段齐、三条禁做与正例
可核对）。`tests/test_docmode.py` 的 `.tex` 回归锁只多一个恒为 `0.0` 的
`section_length` 指标键。

## 5. 没做的事

- README 不改（主控处理）；
- 不给 `audit` 加篇幅判据：`SECTION_LENGTH` 只是 `style` 的黄牌提示；
- 不自动改写正文：压篇幅仍由人或模型按处方执行，`review` 的保护面照旧把关。
