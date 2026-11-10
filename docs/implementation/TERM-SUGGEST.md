# TERM-SUGGEST — 术语候选抽取与人工入表实施记录

批 98 初版；批 98b 精度修订。规范：`docs/design/SPEC-TERM-SUGGEST.md`。

本流水线是「挖候选 → 人勾 → 入表」，**不自动写词表、不合并同义词**。
批 98b 只做精度：内置泛词表、LaTeX/模型名噪音遮罩、排序加分、默认阈值
收紧到 `--min-count 4 --min-sections 3`。

## 1. 判据

### 1.1 语料与遮罩

| 项 | 口径 |
|---|---|
| 有 `paperkit.toml` | 按 `sections` 配置＋`\input` 闭包取正文（复用 `load_config` / `load_sections`） |
| 无 `paperkit.toml` | 递归扫 `.tex` / `.md` / `.markdown` / `.txt`，跳过隐藏目录与 `audit`、`figures`、`results`、`tables` 等生成/结构化目录 |
| 遮罩 | 复用 `style._source_view`：TeX 走 `prose_of`，Markdown 走 `mdscan.scan_markdown`；注释、代码块、行内代码、数学、表格、链接目标先抹成等长空白 |
| 噪音遮罩 | 再抹一层 `\ref{}` / `\cite{}` / `\label{}` / `\fact{}` / `\input{}` 等命令参数，以及模型名形态（`Flash`、`Pro`、`MiniMax-M3.1-Flash`、`DeepSeek V4.1 Flash`、版本串 `V4.1`）；Markdown 里的 LaTeX 片段同样生效 |
| 小节 | 标题分隔区间（LaTeX：`\section`/`\subsection`/`\subsubsection`/`\paragraph`；Markdown：`#`–`######`）；首个标题前算第 0 节；无标题整篇算一节 |
| 行号 | 遮罩等长（换行保留），按遮罩后正文换行数计数；`first_location = 相对路径:行号` |

### 1.2 中文候选

1. 取连续 CJK 片段；
2. 先按多字虚词/套话切（`以及`、`并且`、`因为`、`我们`、`一个`、`什么`、
   `同样`，以及定义句式 `称为`、`记为`、`是指`、`指的是` 等），再按单字
   虚词切（`的`、`了`、`和`、`与`、`是`、`在`、`把`、`被` 等）；
3. 切出的片段 **2–8 字**才收；长于 8 字整段丢弃（不滑窗，避免重叠 n-gram
   子串噪声）；
4. 切分保留原串下标（多字虚词按原长抹空白），用于判断「紧跟定义句式」；
5. 纯数字、纯标点天然不会进入 CJK 片段；代码块已先遮罩。

### 1.3 英文候选

1. 逐行取 `[A-Za-z][A-Za-z0-9'’-]*` 词元；只有词元之间仅隔空格/制表符
   才属于同一短语（标点、换行断句）；
2. 以功能词表（冠词、代词、介词、连词、助动词、常见动词、数量/修饰词、
   定义动词 `is`/`are`/`refers to`/`denotes`/`describe`/`define`）为断点，
   取连续实词串；不做词性标注，靠词表近似「实词串＝名词短语」；
3. 实词串按 1–4 词切块：2–4 词块全收；单词块必须**首字母大写**或
   **词内带连字符**才收，压掉 `the model` → `model` 这类泛词；
4. 计数键用 `terms.key_of`，`System prompt` / `system prompt` /
   `system-prompt` 合并；展示表面形式用 `terms.normalize_surface`
   （NFKC＋小写）后出现次数最多者，同数取字典序最小者。

### 1.4 泛词表

内置两张泛词表（模块级 `frozenset`，可直接追加扩展）：

* 中文 **134** 词：`模型`、`任务`、`方法`、`结果`、`数据`、`问题`、`系统`、
  `实验`、`正文`、`小节`、`表格`、`文章`、`工作`、`研究`、`过程`、`情况`、
  `影响`、`原因`、`结论`、`假设`、`机制`、`失败`、`函数`、`实例` 等；
* 英文 **119** 词（复数形自动补齐，匹配键共 238 个）：`model(s)`、
  `method(s)`、`result(s)`、`table(s)`、`figure(s)`、`section(s)`、
  `paper(s)`、`system(s)`、`work`、`study`、`approach`、`example(s)`、
  `value(s)`、`case(s)`、`data`、`set`、`number(s)` 等。

过滤按**整条候选精确匹配**：命中即丢；泛词嵌在更长候选里则不受影响，
例如 `system` 命中但 `system prompt` 保留，`系统` 命中但 `系统提示` 保留。
`假设`、`机制` 只过滤单用形态，`零假设`、`失效机制` 这类更长词照常保留。

### 1.5 噪音遮罩

* LaTeX 命令参数：`\ref{}`、`\eqref{}`、`\cite{}`、`\citep{}`、`\citet{}`、
  `\label{}`、`\fact{}`、`\input{}`（含可选参数）整段抹空白；测试夹具
  `\ref{tab:x}` 不会产出 `tab` 或 `x`。
* 模型名：`Flash`、`Pro`、`MiniMax`、`DeepSeek`、`GPT`、`Claude`、`Gemini`、
  `Llama`、`Qwen`、`GLM`、`Mistral` 等族名，连同版本串
  （`M3.1`、`V4.1`、`-Flash`、`-Pro` 等）整段抹空白；独立版本串如 `V4.1`
  也遮。
* 遮罩保持等长、保留换行，行号不漂。

### 1.6 过滤、打分与排序

* `count >= min-count`（默认 **4**）；
* `sections >= min-sections`（默认 **3**）；
* 匹配键不在既有词表（默认 `paper.tsv` ＋ `workspace.tsv`，`--glossary`
  可覆盖）的任一表面形式里；
* 命中泛词表（整条精确匹配，见 §1.4）即丢；
* 基础分 `score = count × sections`，再加排序加分（**只改排序，不改入选**）：

| 加分项 | 分值 | 判定 |
|---|---|---|
| 出现在标题里 | +3 | 候选键出现在任一标题的切分结果里 |
| 紧跟定义句式 | +2 | 中文 `是/指/称为/记为/是指/指的是/定义为`；英文 `is/are/refers to/denotes` 紧跟候选之后（允许空白） |
| 中文专业后缀 | +2 | 候选以 `率/度/曲线/假设/效应/系数/机制/约束/预算/协议/口径` 结尾 |
| 英文形态 | +1 | 原始写法含连字符或首字母大写 |

* 排序 `score` 降序、同分按 `surface` 字典序升序；双跑逐字节一致。

## 2. 命令与入表

```
python3 -m factscribe terms suggest <目录> [--min-count 4] [--min-sections 3]
                                   [--out candidates.tsv] [--json]
python3 -m factscribe terms add --from candidates.tsv --pick <表面形式>[,<表面形式>...]
```

`terms add` 只写 `--pick` 点名的形式：`canonical=表面形式`、两个别名列为
空、`category=待分类`、`blocked` 为空；追加一行注释
`# terms add <日期>：来源 <候选文件>`。已在该词表的形式跳过（幂等），
全部 pick 都找不到＝退出码 2。写入后立即用 `terms.parse_glossary` 重解析，
坏表当场报错。

## 3. 实测

### 3.1 命令

```
python3 -m factscribe terms suggest ../paper     --out /tmp/cand-en2.tsv
python3 -m factscribe terms suggest ../paper-zh  --out /tmp/cand-zh2.tsv
```

### 3.2 条数前后对比

| 语料 | 批 98（默认 3/2） | 批 98b（默认 4/3） | 变化 |
|---|---|---|---|
| `../paper` | 20 | **3** | 去泛词 + 模型名遮罩 + 阈值收紧 |
| `../paper-zh` | 97 | **21** | 去泛词 + 阈值收紧（批 98 在 4/3 下仍有 49） |

两份候选都远低于 40 条上限。

### 3.3 `../paper` 前 10 条：批 98 → 批 98b

批 98（默认 3/2）：

| # | surface | lang | count | sections | score |
|---|---|---|---|---|---|
| 1 | flash | en | 9 | 5 | 45 |
| 2 | recorded request bodies | en | 5 | 4 | 20 |
| 3 | table | en | 5 | 4 | 20 |
| 4 | input token | en | 4 | 4 | 16 |
| 5 | same model | en | 4 | 4 | 16 |
| 6 | typed sections | en | 4 | 4 | 16 |
| 7 | gold patch | en | 5 | 3 | 15 |
| 8 | minimax-m3 | en | 5 | 3 | 15 |
| 9 | same six tasks | en | 4 | 3 | 12 |
| 10 | section | en | 4 | 3 | 12 |

批 98b（默认 4/3；全量 3 条）：

| # | surface | lang | count | sections | score |
|---|---|---|---|---|---|
| 1 | input token | en | 4 | 4 | 18 |
| 2 | typed sections | en | 4 | 4 | 16 |
| 3 | gold patch | en | 5 | 3 | 15 |

`flash`、`table`、`same model`、`section`、`minimax-m3` 全部消失：前三个
命中泛词表，后两个被模型名遮罩/功能词断点处理。

### 3.4 `../paper-zh` 前 10 条：批 98 → 批 98b

批 98（收紧 4/3）：

| # | surface | lang | count | sections | score |
|---|---|---|---|---|---|
| 1 | 模型 | zh | 18 | 12 | 216 |
| 2 | 失败 | zh | 15 | 11 | 165 |
| 3 | 任务 | zh | 13 | 8 | 104 |
| 4 | 测试 | zh | 10 | 6 | 60 |
| 5 | 结果 | zh | 8 | 7 | 56 |
| 6 | 送达 | zh | 8 | 7 | 56 |
| 7 | 上限 | zh | 7 | 7 | 49 |
| 8 | 输出 | zh | 8 | 6 | 48 |
| 9 | 闸门 | zh | 8 | 6 | 48 |
| 10 | flash | en | 9 | 5 | 45 |

批 98b（默认 4/3）：

| # | surface | lang | count | sections | score |
|---|---|---|---|---|---|
| 1 | 送达 | zh | 8 | 7 | 59 |
| 2 | 闸门 | zh | 8 | 6 | 48 |
| 3 | 卡片 | zh | 6 | 6 | 38 |
| 4 | 一臂 | zh | 6 | 5 | 30 |
| 5 | cli | en | 6 | 4 | 28 |
| 6 | 智能体 | zh | 7 | 4 | 28 |
| 7 | 回合 | zh | 5 | 5 | 25 |
| 8 | 提示词 | zh | 5 | 4 | 25 |
| 9 | 两臂 | zh | 5 | 4 | 22 |
| 10 | fail-to-pass | en | 6 | 3 | 19 |

`模型`、`失败`、`任务`、`测试`、`结果`、`上限`、`输出`、`flash` 等泛词/
噪音不再出现；前 10 条均为论文语境里的实义术语或实验术语。

### 3.5 人工判真术语比例

按论文正文用法逐条判读（判定依据：该词在论文里指称一个可定义的对象、
指标或机制，而非通用学术套话）：

| 语料 | 总条数 | 判为真术语 | 比例 | 非术语举例 |
|---|---|---|---|---|
| `../paper` | 3 | 3 | **100%** | — |
| `../paper-zh` | 21 | 19 | **90%** | `按新鲜价计`（句子碎片） |

中文两条待清理项：`按新鲜价计` 是「按新鲜价计（价）」的切分碎片；另一条
`指令` 属于通用词，但在本文语境里指对智能体的行为指令，暂按真术语计。
其余如 `送达`、`闸门`、`卡片`、`一臂/两臂`、`智能体`、`回合`、`提示词`、
`测试选择器`、`判卷器`、`哈希`、`章程` 都是论文自己的概念或实验件。

## 4. 测试

`tests/test_term_suggest.py`：**34 例**（全离线；批 98 的 22 例 + 批 98b
新增 12 例）。新增覆盖：

* 中文 `模型`、`任务`、`失败` 等泛词不出现，`变异系数`、`剂量反应曲线`
  必须出现；
* 英文 `table`、`flash`、`minimax` 不出现，`system prompt` 出现；
* 泛词嵌在更长候选里（`系统提示`、`model compression`）不受影响；
* `\ref{tab:x}` / `\cite{}` / `\label{}` / `\fact{}` / `\input{}` 不产出
  `tab`、`x` 等参数词（TeX 与 Markdown 两条路径）；
* 模型名 `Flash` / `Pro` / `MiniMax-M3.1-Flash` / `DeepSeek V4.1 Flash`
  不进候选；
* 标题 +3、定义句式 +2、中文专业后缀 +2、英文连字符 +1 的排序效果；
* 加分只改排序、不改入选；
* 默认阈值 `4/3`（3 次出现/3 小节默认不收，显式 3/3 才收）。

全套：`env PYTHONPATH=src python3 -m unittest discover -s tests` →
**597 例 OK**。

## 5. 门禁

```
env PYTHONPATH=src python3 -m unittest discover -s tests
./scripts/preflight-ci.sh
```

结果：

* 工作区全量测试：**Ran 597 tests — OK**；
* `./scripts/preflight-ci.sh --fast`：Python 3.10 / 3.11 / 3.12 各
  **Ran 597 tests**，验收样例 `examples/minimal audit exit=1`（红，符合预期），
  全绿；
* 默认 `./scripts/preflight-ci.sh`：干净克隆本批提交后的 HEAD，Python 3.10 /
  3.11 / 3.12 各 **Ran 597 tests**，全绿。
