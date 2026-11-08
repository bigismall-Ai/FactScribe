# 改写保护面比对实施记录（批 83）

> 规范：`docs/design/SPEC-V3.0.md` §14「改写保护面」。
> 新增 `factscribe protect` 子命令；**未改 `audit` / `style` 的判据与退出码**。
> 用途：文档改写前后机械比对「不许变」的内容；只改措辞/标点则全绿。

## 1. 保护面表

### 硬面（变了即红，exit 1）

| 项 | 抽取规则 | 码 |
|---|---|---|
| 事实标记 | 全文 `\fact{...}` 的 id 多重集；`[[fact:...]]` 同算；注释/verbatim/批注宏里的不算 | `PROTECT_FACT_CHANGED` |
| 数字 | 与 `audit` 同一 tokenizer（`scan_tex` → `_extract_numbers`）抽出的数字多重集，按 `number_key` 归一 | `PROTECT_NUMBER_CHANGED` |
| 引用 | cite 家族命令的 key 多重集（`\cite`/`\citep`/`\citet`/`\citealp`/`\citeauthor`/`\nocite` 等） | `PROTECT_CITE_CHANGED` |
| 公式 | 行内 `$...$`、`$$...$$`、`\[...\]`、`equation/align`（含星号）环境的内容哈希 | `PROTECT_MATH_CHANGED` |
| 表格 | `tabular`/`tabular*` 每一行的单元格数 + 行内容哈希 | `PROTECT_TABLE_CHANGED` |
| 交叉引用 | `\label{}`／`\ref{}`／`\eqref{}` 的 key 集合（按 key 去重） | `PROTECT_LABEL_CHANGED` |

### 软面（黄，exit 3）

| 项 | 抽取规则 | 码 |
|---|---|---|
| 章节标题文字 | `\part`/`\chapter`/`\section`/`\subsection`/`\subsubsection`/`\paragraph` 的标题按序列对齐；层级不同不算改名 | `PROTECT_HEADING_RENAMED` |
| 文件集合 | 相对路径下 `.tex` 的新增/删除 | `PROTECT_FILE_SET_CHANGED` |

`--allow-renames` 只把标题变化降为**信息**（不进黄计数、不影响退出码）；
文件增删恒为黄。改名 = 一删一增，报 `PROTECT_FILE_SET_CHANGED`。

## 2. 抽取规则（实现细节）

- **统一遮罩**：`protect._code_view()` 复用 `texscan._mask_envs_and_verb`
  抹掉 verbatim/`\verb`/`\pkignore`/`\todo` 等批注宏，再抹掉 `%` 注释；
  **保持长度与换行**，所以所有位置都能直接换算回源文件行号。
- **事实标记**：`scan_tex(text).markers`，一次命令一条（多 id 写法按 id 拆开）。
- **数字**：`scan_tex(text).masked` → `_extract_numbers(masked, text)`，
  与 `audit` 完全同一套 tokenizer。比较键是 `number_key`：
  `1,234` ≡ `1234`；`53k` ≡ `53000`；`62.5\%` ≡ `0.625`；`53~tokens` 仍是 53。
  千分位空格（`1\,000\,000`）照旧合并。
- **引用**：`scan_tex(text).cites` 的 key；命令换名（`\cite`↔`\citep`）但
  key 不变时不算变化。
- **公式**：公式内容去掉全部空白后 sha256（TeX 数学里空白不承载语义）；
  行内、行间、环境三种来源按文档顺序进入同一条时间线。
- **表格**：`\begin{tabular}{...}` 后的列格式先跳过；行按 `\\` 切分，
  `\hline`/`\toprule`/`\midrule`/`\bottomrule`/`\cline` 等横线命令先剥掉；
  单元格按未转义的 `&` 切分，去空白后取 sha256。
- **交叉引用**：`\label`/`\ref`/`\eqref` 三个命令合并成一个 key 集合
  （同一 key 重复出现只算一次）。
- **标题**：只取标题参数内的文字；用 `difflib.SequenceMatcher` 对齐前后
  标题序列，只把 `replace` 段按位置配对成「改名」；纯插入/删除标题不报。

## 3. 判定与输出

- 任一条红 → exit 1；只有黄 → exit 3；全同或只剩信息 → exit 0。
- 目录不存在/不是目录 → `CONFIG_INVALID`（exit 2），不会误判为「全同」。
- 每条发现都带 `文件:行`，并说清多/少/改成了什么，例如：

```text
[红] PROTECT_NUMBER_CHANGED main.tex:3: 数字 "53" 改成了 "54"
[红] PROTECT_TABLE_CHANGED main.tex:14: 多出表格行（列数 2）
[黄] PROTECT_HEADING_RENAMED main.tex:1: 标题 "Introduction" 改成了 "Overview"
```

- 行号口径：「改成了」用改写前位置（消息注明改后行号）；「多出」用改后
  位置；「少了」用改前位置。
- `--json` 的 `findings[]` 固定字段：
  `severity / code / file / line / message / before / after`。

## 4. 误报边界（保守方向：多报不漏报）

- 只改标点、断句、换行、空格、同义措辞 → 全绿。
- 注释、verbatim、`\pkignore`/`\todo` 等批注宏内容 → 不参与保护面。
- 公式重排/换行 → 去空白后哈希相同，不报。
- 数字写法不同但值相同 → `number_key` 归一后不报。
- 表格里的横线命令、单元格内空白 → 不改变行哈希。
- `\multicolumn` 的跨列不折成实际列数，单元格数按 `&` 切分。
- 文件级新增/删除只报一次文件集合变化，不再逐面比较该文件。
- 同一数字在文里出现多次、只改一处时，按行号最近原则配对，位置指向
  改动点而不是第一次出现处。
- 保护面只证明「字符级抽取结果没变」，不证明语义等价；公式/表格哈希
  只去空白，不做 LaTeX 等价变换（如 `\frac{1}{2}` ↔ `0.5` 会报）。

## 5. 测试（33 例）

`tests/test_protect.py`：

- 六条硬保护面各 1 正 1 负：fact、number、cite、math、table、label；
- 只改标点/断句 → exit 0；数字/引用/公式/表格空白重排 → exit 0；
- 改一个数字 → `PROTECT_NUMBER_CHANGED` 且报 `main.tex:3`；
- `\fact{A1}` → `\fact{A2}` → 报红并给前后值；
- `\fact{A1}{53}` → `\fact{A1}{54}`（V3 绑定体）→ 数字面报红；
- 加表行 → `PROTECT_TABLE_CHANGED`（报「多出表格行」）；
- 改单元格列数 → 报「列数」变化；
- 插入新章节标题 → 不算改名（exit 0）；
- 文件增/删 → `PROTECT_FILE_SET_CHANGED` 黄（exit 3）；
- 标题改名 → 黄（exit 3）；`--allow-renames` → 信息（exit 0）；
- 红黄并存 → exit 1（红优先）；
- 空目录 → exit 0；目录不存在 → exit 2；
- JSON 字段契约与人读 `文件:行` 输出。

## 6. 门禁输出

`python3 -m unittest discover -s tests`：

```text
Ran 326 tests in 13.804s

OK
```

`./scripts/preflight-ci.sh --fast`：

```text
== 步骤 1/4：外部依赖 ==
   ✓ pdftotext：/opt/homebrew/bin/pdftotext
   ✓ pdfinfo：/opt/homebrew/bin/pdfinfo
   ✓ PDF 工具齐备
== 步骤 2/4：干净克隆（--fast：跳过，直接用工作区）==
== 步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12）==
   ✓ Python 3.10：Ran 326 tests
   ✓ Python 3.11：Ran 326 tests
   ✓ Python 3.12：Ran 326 tests
== 步骤 4/4：验收样例必须 exit 1 ==
   ✓ examples/minimal audit exit=1（红，符合预期）
== 结论 ==
   本地等价 CI 全绿——可以推。
```

干净克隆版 `./scripts/preflight-ci.sh`（HEAD `ff140c0`）同样全绿：

```text
== 步骤 1/4：外部依赖 ==
   ✓ pdftotext / pdfinfo 齐备
== 步骤 2/4：干净克隆 ==
   ✓ 克隆到 …/repo（HEAD ff140c0）
== 步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12）==
   ✓ Python 3.10：Ran 326 tests
   ✓ Python 3.11：Ran 326 tests
   ✓ Python 3.12：Ran 326 tests
== 步骤 4/4：验收样例必须 exit 1 ==
   ✓ examples/minimal audit exit=1（红，符合预期）
== 结论 ==
   本地等价 CI 全绿——可以推。
```

本文件随后的提交只追加上述门禁记录，不进测试矩阵。

## 7. 落位

- 新模块：`factscribe/protect.py`
- CLI：`factscribe/cli.py` 新增 `protect` 子命令
- 测试：`tests/test_protect.py`
- 规范：`docs/design/SPEC-V3.0.md` §14
- 未触碰 `audit.py` / `style.py` 的判据与退出码。
