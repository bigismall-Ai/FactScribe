# SPEC-TERM-SUGGEST — 术语候选抽取与人工入表

批 98。状态：**冻结**。

## 0. 问题与边界

`paper.tsv` 目前只有 33 条论文术语（来自 `paper-zh/GLOSSARY.md`）。词表覆盖
不足时，`TERM_VARIANT` 只能对着少数几个词判，等于没开。人工通读正文找
术语又太慢，因此需要一条**纯统计＋规则、零 LLM**的机械流水线：

```
正文语料 → terms suggest（挖候选）→ 人勾选 → terms add（写进 paper.tsv）
```

本规范只新增 `terms` 子命令与 `factscribe/term_suggest.py`；**不改**
`terms.py` 的归一化、`style.py` 的判据、`audit` / `protect` 的退出码。
本层**不自动入表、不自动合并同义词、不做中文分词、不做词性标注、不做
语义相似度**，也不联网。

## 1. 命令

```
python3 -m factscribe terms suggest <目录> [--min-count 3] [--min-sections 2]
                                   [--out candidates.tsv] [--json]
python3 -m factscribe terms add --from candidates.tsv --pick <表面形式>[,<表面形式>...]
```

* `suggest` 只读语料，stdout 出 TSV；`--out` 额外落盘。
* `add` 只接受**人工 `--pick` 点名的表面形式**，不从候选里自动挑。
* 两个动作都接受 `--glossary <TSV>`：指定既有词表（默认仓内分层词表
  `paper.tsv` ＋ `workspace.tsv`），供项目覆盖与测试使用。
* 退出码：`0` 成功；`2` 用法/配置错（目录不存在、候选文件坏、`--pick`
  不在候选里）；`4` 工具内部错误。本层不产生红黄判定。

## 2. 语料范围

1. 目录里有 `paperkit.toml`：按该项目的 `sections` 配置 ＋ `\input/\include`
   闭包取文件（复用 `config.load_config` / `load_sections`），即「会被编译
   进正文的源文件」。
2. 没有 `paperkit.toml`：递归扫描 `.tex` / `.md` / `.markdown` / `.txt`；
   跳过隐藏目录与 `audit`、`figures`、`results`、`tables`、`build`、`dist`、
   `node_modules`、`__pycache__`、`.venv`。
3. 文件路径排序后处理，保证结果与文件系统枚举顺序无关。

## 3. 遮罩与小节

* `.tex`、`.md` 一律走既有解析入口 `style._source_view`（`tex` 用
  `prose_of`，`markdown` 用 `mdscan.scan_markdown`），**不另写遮罩**。
  注释、围栏代码、行内代码、数学、表格、链接目标等先被抹成等长空白，
  因此代码块里的词不参与计数。
* 小节＝标题分隔的区间：LaTeX 认 `\section` / `\subsection` /
  `\subsubsection` / `\paragraph`，Markdown 认 `#`–`######`。第一个标题
  之前的内容算第 0 小节；没有标题的文件整篇算一个小节。
* 小节标识＝`相对路径#序号`；`sections` 列是候选出现的**不同小节数**，
  同一小节出现多次只算一次。
* 行号按遮罩后正文的换行数计算，与原文行号一致（遮罩等长）。

## 4. 中文候选（`lang=zh`）

1. 取连续 CJK 片段（`[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+`）。
2. 先按多字虚词/套话切分（`以及`、`并且`、`但是`、`因为`、`所以`、
   `如果`、`从而`、`对于`、`通过`、`进行`、`可以`、`我们`、`这个`、
   `一个`、`一种`、`什么`、`同样` 等），再按单字虚词切分
   （`的了着过和与及或而但则就都也还又再很更最把被让使是在对向从由并
   即若因这那哪吗呢吧啊呀哦嗯之其所以为于`）。
3. 切出的片段长度为 **2–8 字**才收；纯数字、纯标点天然不会进入 CJK 片段。
4. 长于 8 字的片段**整段丢弃**（不滑窗），避免用重叠 n-gram 制造大量
   子串噪声；宁缺毋滥，人工勾选时再补。

## 5. 英文候选（`lang=en`）

1. 逐行取 `[A-Za-z][A-Za-z0-9'’-]*` 词元；只有词元之间仅隔空格/制表符时
   才属于同一短语（标点、换行即断句）。
2. 以功能词表（冠词、代词、介词、连词、助动词、常见动词）为断点，取
   连续实词串。
3. 实词串按 **1–4 词**切块；2–4 词块全部收，单块只有满足下列之一才收：
   * 首字母大写；或
   * 词内带连字符；
   * 多词短语本身已满足（第 1 条硬条件只约束单词候选）。
4. 计数键用 `terms.key_of`（NFKC＋小写＋去标点/连字符/空白差异），因此
   `system prompt` / `System Prompt` / `system-prompt` 合并；展示表面形式
   取出现次数最多的写法，同数取字典序最小者。

## 6. 过滤、打分与排序

候选必须同时满足：

* `count >= --min-count`（默认 3）；
* `sections >= --min-sections`（默认 2）；
* 归一化匹配键**不在**既有词表（默认 `paper.tsv` ＋ `workspace.tsv`，
  `--glossary` 可覆盖）的任一表面形式里。

打分与排序：

```
score = count × sections
排序：score 降序，同分按 surface 字典序升序
```

排序键完全确定，双跑逐字节一致。`first_location` 取扫描顺序中第一次
出现的位置，格式 `相对路径:行号`（路径用 `/`）。

## 7. 输出

TSV，UTF-8，首行列名：

```
surface	lang	count	sections	first_location	score
```

`--json` 输出同一份行数据：

```json
{
  "tool": "terms",
  "action": "suggest",
  "root": "<目录>",
  "min_count": 3,
  "min_sections": 2,
  "candidates": [
    {"surface": "...", "lang": "zh", "count": 6, "sections": 3,
     "first_location": "sections/03_system.tex:12", "score": 18}
  ],
  "count": 1
}
```

## 8. `terms add`

* 读 `--from` 的候选 TSV，只处理 `--pick` 点名的表面形式；`--pick` 可重复，
  也可一次用逗号分隔多个。
* 匹配用归一化键：拉丁大小写/连字符差异视为同一形式；中文精确同形。
* 每命中一条，向词表追加一行：`canonical=表面形式`、两个别名列为空、
  `category=待分类`、`blocked` 为空。**不写 alias、不合并同义词。**
* 追加前写一行注释：`# terms add <YYYY-MM-DD>：来源 <--from 路径>`。
* 已在该词表里的表面形式跳过（幂等，不重复写）。全部 `--pick` 都找不到
  ＝用法错（退出码 2）。
* 写入后词表必须仍能被 `terms.parse_glossary` 正常解析，`style` 照常运行。

## 9. 非目标

* 不自动改 `paper.tsv`（除 `add` 的人工点名外）；
* 不判断候选「是不是真术语」，只按统计排序供人勾；
* 不做中文分词/词性标注/同义词聚类；
* 不引入第三方依赖；
* 不改 `style` / `audit` / `protect` 的任何判据与退出码。

## 10. 验收

* `tests/test_term_suggest.py` ≥ 14 例：中文/英文正例、泛词负例、代码块遮罩、
  阈值、已入表排除、`add` 后仍可解析、双跑字节一致、JSON 结构、错误退出码。
* 实测 `../paper` 与 `../paper-zh`：默认阈值下候选超过 60 条时，收紧
  `--min-count` / `--min-sections` 重跑，并在实施记录里写明条数与前 10 条。
* 门禁：

```
env PYTHONPATH=src python3 -m unittest discover -s tests
./scripts/preflight-ci.sh
```
