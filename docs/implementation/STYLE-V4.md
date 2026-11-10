# 文风闸 v4 实施记录（批 82）

> 规范：`docs/design/SPEC-V3.0.md` §13「文风规则 v4」。
> 只改 `factscribe style` 子命令；**未改 `audit` 的判据与退出码**。
> 文风闸仍只出黄牌（exit 3），不阻断、不改正文；`--json` 与 `--prompt` 同步。

## 1. 规则表（9 条，全部黄牌）

| 码 | 判据 | 阈值（`style-rules.toml`） | 说明 |
|---|---|---|---|
| `DASH_PARENTHETICAL` | `——`/`—` 用作插入解释，**逐处报** | `thresholds.dash_budget = 0` | 数值范围、文献页码、数学环境排除；ASCII `--` 不匹配 |
| `HEADING_TOO_LONG` | 中文标题 >12 字、英文 >8 词 | `heading_max_chars_zh = 12`、`heading_max_words_en = 8` | `\title{}` 豁免 |
| `HEADING_MALFORMED` | 标题含冒号/破折号/括号解释/问号/句号（含英文句点，常见缩写豁免） | 出现即报 | 论文主标题 `\title{}` 除外；连字符不算破折号；批 112 起 `.` 同判，`heading_period_exempt` 放行缩写 |
| `TERM_FIRST_IN_HEADING` | 标题出现术语样词（中文 ≥4 字段、英文 ≥2 词短语），该节首句未出现 | 出现即报；白名单命中不报 | 启发式，只黄 |
| `RHYTHM_PLATEAU` | 同段连续 ≥3 句落在同一 10 词区间 | `rhythm_plateau_run = 3`、`rhythm_plateau_window = 10` | 保留 |
| `COLLOQUIAL_TRIAD` | **模板式**三点并列（`首先/其次/最后` 等）在**相邻段落**重复 ≥2 次 | `colloquial_triad_repeats = 2` | 替代旧 `TRIAD_DENSITY`；批 110 起顿号/逗号列举不算，不按条数判 |
| `CONNECTIVE_DENSITY` | 套话连接词密度 | `connective_density = 8.0`（每千词/字） | 保留；句中定语用法不算 |
| `EMPTY_ADJECTIVE` | 空泛形容词密度 | `empty_adjective = 6.0`（每千词/字） | 保留；`exempt_phrases` 排除术语搭配 |
| `SENTENCE_LENGTH_EXTREME` | 英文 >60 词/中文 >110 字且句内无断点 | `sentence_length_extreme_en = 60`、`_zh = 110` | 保留窄版；长而有结构不报 |

### 明确不实现（写进 SPEC §13.11）

排比限两项；冒号只许引原话；长句必拆；标题数量限制；引用式长标题白名单（已撤销）。

## 2. 阈值来源

全部阈值与词表来自仓根 `style-rules.toml`（项目根同名文件优先，其次仓根，
最后内置默认值）。实现里 `DEFAULT_RULES` 与 `style-rules.toml` 同构；改 TOML
即改判定，未知键向前兼容，已知键必须是非负数字，否则 `CONFIG_INVALID`（exit 2）。

v4 新增键：

```toml
term_allow_files = ["GLOSSARY.md", "term-allow.txt"]

[thresholds]
dash_budget = 0
heading_max_chars_zh = 12
heading_max_words_en = 8
colloquial_triad_repeats = 2
```

旧的 `thresholds.triad_density` 已移除（规则本身被 `COLLOQUIAL_TRIAD` 替代）。

## 3. 术语白名单机制

两层来源，合并后统一匹配：

1. 项目内 `GLOSSARY.md`；
2. 用户自维护纯文本 `term-allow.txt`（一行一个词）。

文件清单由 `term_allow_files` 配置。解析规则：大小写不敏感、去首尾空白、
忽略空行与 `#` 注释行。命中白名单的标题术语不报 `TERM_FIRST_IN_HEADING`。

## 4. 实现要点

- `factscribe/style.py`：新增破折号、标题、术语、同构排比四组检测；删除
  `TRIAD_DENSITY` 的按密度判定。
- 每条 finding 固定字段：`code / severity / file / line / text / suggestion`，
  `severity` 恒为 `yellow`。
- 标题规则单独扫描源文件（走 `_live_text` 活跃正文，注释里的标题不算）；
  `\title{}` 天然不在章节标题集合内，因此长度/格式/术语三规则均豁免。
- 破折号检测在遮罩后的正文上做：数值范围（`3—4`、`1--2`）、页码
  （`pp. 12—15`、`第 12—15 页`）与数学环境自动排除。
- `--prompt` 只列黄牌条目，首句明确「只改措辞，不改事实、数字、引用」；
  `report_only` 阶段仍只输出一句「建议不改」。

## 5. 测试

- 新增 `tests/test_style_v4.py`：**37 例**。
  - 9 条规则每条至少 3 例（正例/负例/白名单或豁免例）；
  - 阈值来自 `style-rules.toml` 的验证（改阈值即改判定）；
  - `dash_budget` 调大后不再报；数值范围 `1--2`、文献页码、数学环境豁免；
  - 标题术语命中 `term-allow.txt` / `GLOSSARY.md` 不报；
  - finding 六字段契约、`--json` 与 `--prompt` 同步。
- 同步更新 `tests/test_style.py` 的三项并列旧测试为 `COLLOQUIAL_TRIAD` 语义。
- 全套：`Ran 293 tests` 全绿（原 256 ＋ 新增 37）。

## 6. 门禁输出

`python3 -m unittest discover -s tests`：

```text
Ran 293 tests in 11.828s

OK
```

`./scripts/preflight-ci.sh --fast`：

```text
== 步骤 1/4：外部依赖 ==
   ✓ pdftotext / pdfinfo 齐备
== 步骤 2/4：干净克隆（--fast：跳过）==
== 步骤 3/4：测试矩阵 ==
   ✓ Python 3.10：Ran 293 tests
   ✓ Python 3.11：Ran 293 tests
   ✓ Python 3.12：Ran 293 tests
== 步骤 4/4：验收样例 ==
   ✓ examples/minimal audit exit=1（红，符合预期）
== 结论 ==
   本地等价 CI 全绿——可以推。
```

干净克隆版 `./scripts/preflight-ci.sh`（HEAD `faa5590`）同样全绿：

```text
== 步骤 2/4：干净克隆 ==
   ✓ 克隆到 …/repo（HEAD faa5590）
== 步骤 3/4：测试矩阵 ==
   ✓ Python 3.10：Ran 293 tests
   ✓ Python 3.11：Ran 293 tests
   ✓ Python 3.12：Ran 293 tests
== 步骤 4/4：验收样例 ==
   ✓ examples/minimal audit exit=1（红，符合预期）
== 结论 ==
   本地等价 CI 全绿——可以推。
```
