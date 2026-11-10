# TERM-SUGGEST — 术语候选抽取与人工入表实施记录

批 98。规范：`docs/design/SPEC-TERM-SUGGEST.md`。

本批只新增 `factscribe/term_suggest.py`、`terms` 子命令与测试；`terms.py`
的归一化、`style.py` 的判据、`audit` / `protect` 的退出码均未改动。
流水线是「挖候选 → 人勾 → 入表」，**不自动写词表、不合并同义词**。

## 1. 判据

### 1.1 语料与遮罩

| 项 | 口径 |
|---|---|
| 有 `paperkit.toml` | 按 `sections` 配置＋`\input` 闭包取正文（复用 `load_config` / `load_sections`） |
| 无 `paperkit.toml` | 递归扫 `.tex` / `.md` / `.markdown` / `.txt`，跳过隐藏目录与 `audit`、`figures`、`results`、`tables` 等生成/结构化目录 |
| 遮罩 | 复用 `style._source_view`：TeX 走 `prose_of`，Markdown 走 `mdscan.scan_markdown`；注释、代码块、行内代码、数学、表格、链接目标先抹成等长空白 |
| 小节 | 标题分隔区间（LaTeX：`\section`/`\subsection`/`\subsubsection`/`\paragraph`；Markdown：`#`–`######`）；首个标题前算第 0 节；无标题整篇算一节 |
| 行号 | 遮罩等长，按遮罩后正文换行数计数；`first_location = 相对路径:行号` |

### 1.2 中文候选

1. 取连续 CJK 片段；
2. 先按多字虚词/套话切（`以及`、`并且`、`因为`、`我们`、`一个`、`什么`、
   `同样` 等），再按单字虚词切（`的`、`了`、`和`、`与`、`是`、`在`、
   `把`、`被` 等）；
3. 切出的片段 **2–8 字**才收；长于 8 字整段丢弃（不滑窗，避免重叠 n-gram
   子串噪声）；
4. 纯数字、纯标点天然不会进入 CJK 片段；代码块已先遮罩。

### 1.3 英文候选

1. 逐行取 `[A-Za-z][A-Za-z0-9'’-]*` 词元；只有词元之间仅隔空格/制表符
   才属于同一短语（标点、换行断句）；
2. 以功能词表（冠词、代词、介词、连词、助动词、常见动词）为断点，取
   连续实词串；不做词性标注，靠词表近似「实词串＝名词短语」；
3. 实词串按 1–4 词切块：2–4 词块全收；单词块必须**首字母大写**或
   **词内带连字符**才收，压掉 `the model` → `model` 这类泛词；
4. 计数键用 `terms.key_of`，`System prompt` / `system prompt` /
   `system-prompt` 合并；展示表面形式用 `terms.normalize_surface`
   （NFKC＋小写）后出现次数最多者，同数取字典序最小者。

### 1.4 过滤、打分与排序

* `count >= min-count`（默认 3）；
* `sections >= min-sections`（默认 2）；
* 匹配键不在既有词表（默认 `paper.tsv` ＋ `workspace.tsv`，`--glossary`
  可覆盖）的任一表面形式里；
* `score = count × sections`；排序 `score` 降序、同分按 `surface` 字典序
  升序；双跑逐字节一致。

## 2. 命令与入表

```
python3 -m factscribe terms suggest <目录> [--min-count 3] [--min-sections 2]
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
python3 -m factscribe terms suggest ../paper     --out /tmp/cand-en.tsv
python3 -m factscribe terms suggest ../paper-zh  --out /tmp/cand-zh.tsv
```

### 3.2 条数

| 语料 | 阈值 | 候选条数 | 说明 |
|---|---|---|---|
| `../paper` | `--min-count 3 --min-sections 2` | **20** | 未超 60，无需收紧 |
| `../paper-zh` | `--min-count 3 --min-sections 2` | **97** | 超 60 |
| `../paper-zh` | `--min-count 4 --min-sections 3` | **49** | 收紧后重跑（本记录用这一份） |

中文默认阈值下 97 条，主要来自 2 字通用词（`模型`、`失败`、`任务`）和
少量句子碎片；把出现次数抬到 4、跨节抬到 3 后降到 49 条，前 10 条不变。

### 3.3 `../paper` 前 10 条（默认阈值）

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

### 3.4 `../paper-zh` 前 10 条（收紧 4/3）

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

`flash`、`minimax-m3` 等英文模型名出现在中文语料里是预期行为：语料里确实
有这些拉丁写法，`lang` 列按表面形式判，不按文件语言判。

## 4. 测试

`tests/test_term_suggest.py`：**22 例**（全离线）。覆盖：

* 中文埋点 `剂量反应曲线` / `变异系数` / `预注册` 全部挖出；
* 已入表词不重复出现；
* 英文 `system prompt` / `token budget` 挖出，`the model` 与单词 `model`
  不出现；大小写写法合并；连字符单词候选；
* 中文/英文围栏代码块里的词不参与计数；
* `--min-count` 抬高后弱候选消失；`--min-sections` 过滤局部候选；
* 同一小节重复只算一个 section；`first_location` 行号；
* TSV 列名、JSON 结构、排序规则、双跑字节一致；
* `terms add` 写 `待分类` 行与日期/来源注释、幂等、未知 pick 退出 2、
  写入后 `style --doc` 仍正常解析；
* LaTeX 项目 `sections` 入口与 `verbatim` 遮罩。

全套：`env PYTHONPATH=src python3 -m unittest discover -s tests` →
**585 例 OK**。

## 5. 门禁

```
./scripts/preflight-ci.sh --fast
步骤 3/4：Python 3.10 / 3.11 / 3.12 各 Ran 585 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

`--fast` 直接跑工作区（含本批未提交文件）；提交后的干净克隆门禁另行
在交付回复中记录结果。
