# STYLE-V3｜批 71：`\$` 解析修复与阶段判断

> 日期：2026-11-08
> 范围：`factscribe/style.py`、`tests/test_style.py`、`docs/design/SPEC-V3.0.md` §12
> 纪律：不改 `paper/`、`paper-zh/` 正文；提交不 push。

## 0. 结论

1. **`\$` 解析 bug 已修**：`\$` 现在按字面美元符号处理，不再开启数学模式；
   `\(`/`\)`、`\[`/`\]` 与 `\\[2pt]`（换行命令）按同一套转义优先规则处理。
2. **阶段判断已生效**：`style` 新增 `stage_assessment`；成品稿判
   `polished/report_only`，`--prompt` 只输出一句「指标健康，建议不改；强行
   改写有降低自然度风险」，不再给逐条改写指令。
3. **修正后的真实基线**：`paper/` 词/字 **6390 → 6924（+8.4%）**，句
   **368 → 397（+7.9%）**，段 **90 → 96**；`paper-zh/` 词/字
   **10059 → 10893（+8.3%）**，句 **390 → 421（+7.9%）**，段 **91 → 96**。
   两稿都判 `polished/report_only`。
4. 测试 **247 → 256 例全绿**（新增 9 例：解析 4＋阶段 4＋CLI 1）。

## 1. `\$` 解析修复

### 1.1 根因

`prose_of()` 的 `_mask_inline_math()` 只检查字符是不是 `$`，没有先处理反斜杠
转义。正文里出现 `\$0.0486`（价格）时，`$` 被当成数学起点，随后一直找到下一个
真正的 `$` 才闭合；中间整段正文被抹成空格。最坏情况（该段之后再无 `$`）会吞到
文件末尾。后果：

- 词/字、句、段总数偏低；
- 句长序列缺句，句长 CV 偏移；
- 三项并列、节奏平台等按段/按句统计的指标漏算。

### 1.2 修法（`factscribe/style.py`）

数学遮罩改为「转义优先」的单遍扫描：

| 输入 | 处理 |
|---|---|
| `\$` `\%` `\&` `\_` `\#` `\{` `\}` | 跳过两个字符，按字面字符处理，**不进入数学** |
| `\\` | 跳过两个字符（换行命令）；后面的 `[` 不再被当成 `\[` |
| `\(` … `\)` | 找未转义的 `\)` 闭合 |
| `\[` … `\]` | 找未转义的 `\]` 闭合，与圆括号对称 |
| `$` … `$` / `$$` … `$$` | 闭合符搜索同样跳过 `\$` 等转义 |
| `\\[2pt]` | 换行命令连同可选间距参数在正文清洗阶段整体抹掉 |

新增 `_find_math_closer()`，避免 `\\)` 被误认为 `\)`。三种数学定界符现在走同一
条「未转义闭合符」规则，行为对称。

### 1.3 测试（`tests/test_style.py::TestEscapedDollarParsing`）

正例 2 条：

- `\$100`：保留 `$100`，后续句子保留，句数 2，计数单元与「把 `\$` 换成 `$`」
  的参照文本完全一致；
- `\$x\$`：两个转义美元都按字面处理，`x` 与后续文本保留，句数 2，计数一致。

负例 2 条：

- 同一段里 `\$100` 与真数学 `$a+b$` 混排：真数学仍被遮罩，`$100` 与后续文本
  保留；
- `\(x+1\)`、`\[y=2\]` 对称遮罩，`\\[2pt]` 后面的正文保留且不残留 `2pt`。

## 2. 阶段判断：成品稿不给改写指令

### 2.1 背景

批 67–70 三轮盲评：文风闸对 LLM 初稿有效（盲评 9/10），对已打磨稿有害
（3–5/24 被盲评判为改写后更差）。因此 `style` 不应对所有文本都给「逐条改写
清单」，必须先判断稿件阶段。

### 2.2 判据（同步写入 `docs/design/SPEC-V3.0.md` §12）

`triggers` = 触发指标项数（`fired` 的长度，不是 findings 条数）；`cv` = 句长
（词/字）标准差除以均值。

| 条件 | stage | advice | 行为 |
|---|---|---|---|
| `triggers >= 3` 或 `cv < 0.45` | `draft` | `rewrite` | 给逐条改写清单（沿用 V2 的 `--prompt`） |
| `triggers <= 2` 且 `0.45 <= cv <= 0.80` | `polished` | `report_only` | 明确输出「建议不改」；`--prompt` 只输出一句 |
| `triggers <= 2` 且 `cv > 0.80`（散） | `polished` | `report_only` | 散不是公式化特征，同样只报告 |

输出字段：

```json
{"stage": "draft|polished", "advice": "rewrite|report_only",
 "reason": "...", "triggers": 3, "cv": 0.52}
```

实现细节：

- 阶段判断的 `cv` 用**原始句长 CV**，即使句数少于 `uniformity_min_sentences`
  （10）也照算；指标侧的 `sentence_uniformity` 仍保留「少于 10 句不判」的
  1.0 哨兵。否则 6 句高度同构的初稿会被误判成品稿。
- `report_only` 下 `build_prompt()` 返回常量
  `指标健康，建议不改；强行改写有降低自然度风险`，长度远低于 400 字上限，
  不含任何 `文件:行 → 改法` 条目。
- 人读报告新增「阶段 / 判断」两行；`report_only` 时具体清单标为
  `[观察]`，并注明「建议不改，以下只作报告」。退出码语义不变（仍只 0/3）。

### 2.3 测试（`tests/test_style.py::TestStageAssessment` / `TestCLI`）

- 多指标触发 → `draft/rewrite`；
- 低 CV（`UNIFORM_POS`，triggers 少）→ `draft/rewrite`；
- 健康稿（`NORMAL_1..3`，triggers 0、CV≈0.46）→ `polished/report_only`，
  reason 含「建议不改」；
- `report_only` 的 `--prompt` 恰好等于那一句，不含 `→`、`逐条`、`改法`、
  `替换`、`重写`、`rewrite`；
- CLI `--json` 含 `stage_assessment` 五字段，`--prompt` 单行输出。

## 3. 修正后的真实基线

命令（仓根 `paperkit-dev/`）：

```bash
env PYTHONPATH=. python3 -m factscribe style ../paper --json
env PYTHONPATH=. python3 -m factscribe style ../paper-zh --json
```

### 3.1 `paper/`（英文）

| 指标 | 修复前 | 修复后 | 变化 |
|---|---:|---:|---|
| 词/字 | 6390 | **6924** | +534（+8.4%） |
| 句 | 368 | **397** | +29（+7.9%） |
| 段 | 90 | **96** | +6 |
| 句长 CV | 0.536 | **0.529** | −0.007 |
| 节奏平台 RHYTHM_PLATEAU | 13 | **17** | +4 |
| 三项并列密度 | 1.88 | 1.88 | 0 |
| 连接词密度 | 0.0 | 0.0 | 0 |
| 空泛形容词 / 双重限定 / 同头 / 超长句 | 0 | 0 | 0 |
| 触发项 / findings | 1 / 13 | 1 / 17 | findings +4 |
| 阶段 | —（旧版无） | **polished / report_only** | cv=0.529 |

### 3.2 `paper-zh/`（中文）

| 指标 | 修复前 | 修复后 | 变化 |
|---|---:|---:|---|
| 词/字 | 10059 | **10893** | +834（+8.3%） |
| 句 | 390 | **421** | +31（+7.9%） |
| 段 | 91 | **96** | +5 |
| 句长 CV | 0.544 | **0.538** | −0.006 |
| 节奏平台 RHYTHM_PLATEAU | 12 | **13** | +1 |
| 三项并列密度 | 2.58 | **2.39** | −0.19（分母修正） |
| 连接词密度 | 0.1 | **0.09** | −0.01（分母修正） |
| 段末模板占比 | 0.044 | **0.042** | −0.002（分母修正） |
| 空泛形容词 / 双重限定 / 同头 / 超长句 | 0 | 0 | 0 |
| 触发项 / findings | 1 / 12 | 1 / 13 | findings +1 |
| 阶段 | —（旧版无） | **polished / report_only** | cv=0.538 |

### 3.3 哪些读数被低估了

- **规模类（明确低估）**：两稿的词/字、句、段都被少算约 8%。受影响位置是
  含 `\$` 的价格句：`paper/sections/01_intro.tex:36`、`04_mechanisms.tex:146`、
  `05_eval.tex:38`；中文版同三处。最坏情况从 `\$` 一直吞到下一个 `$`，可跨
  十余行甚至到文件尾。
- **按句/按段指标（明确低估）**：英文节奏平台 findings 13→17、中文 12→13。
  旧读数把这些段落里的连续同长句漏掉了。
- **密度类（方向不一，因分母修正）**：英文三项并列密度恰好持平；中文三项
  并列 2.58→2.39、连接词 0.1→0.09、段末模板 0.044→0.042，是分母变大后的
  正确值——旧值略偏高，不是偏低。
- **句长 CV（轻微偏移）**：0.536→0.529、0.544→0.538。旧 CV 略偏高，因为被
  吞掉的正文使句长序列缺句；修正后落在更可信的位置，仍处于健康区间。
- 空泛形容词、双重限定、相邻段同头、超长句均为 0，未被此 bug 改变。

## 4. 验证与复现

```bash
cd paperkit-dev
env PYTHONPATH=. python3 -m unittest discover -s tests        # 256 例全绿
env PYTHONPATH=. python3 -m factscribe style ../paper         # polished / 建议不改
env PYTHONPATH=. python3 -m factscribe style ../paper --prompt
# → 指标健康，建议不改；强行改写有降低自然度风险
```

刻意公式化的 10 句小文本（`Moreover/Furthermore/Additionally` ＋ 空泛形容词
＋ `A, B, and C`）验证结果：

```text
阶段    : draft（建议改写，triggers=6，cv=0.12）
判断    : 触发 6 项指标（CONNECTIVE_DENSITY、SENTENCE_UNIFORMITY、
          EMPTY_ADJECTIVE、TRIAD_DENSITY、PARAGRAPH_TEMPLATE、RHYTHM_PLATEAU）…
--prompt 输出逐条改写清单（3 条，400 字内）。
```

## 5. 改动清单

- `factscribe/style.py`：`_find_math_closer()`、转义优先的 `_mask_inline_math()`、
  换行命令清洗、`assess_stage()`、`StyleResult.stage_assessment`、
  `build_prompt()` 的 report-only 分支、人读报告阶段块。
- `factscribe/cli.py`：`style --json` 输出 `stage_assessment`。
- `tests/test_style.py`：新增 9 例（256 例全绿）。
- `docs/design/SPEC-V3.0.md`：新增 §12「文风闸阶段判断」。
