# SPEC-TERMS｜术语归一化与同义词层

> 状态：**冻结**（批 90，批 91 修订术语层）。本件只规定 `factscribe style`
> 的术语比对层，不改 `audit` / `protect` 的判据与退出码，也不改其它 spec 文件。
> 新判据全黄牌，退出码仍为 `0` / `3`；只提示的 `TERM_UNREGISTERED`
> 默认关闭，打开后只进 `info` 通道，不参与计数门槛，退出码仍为 `0`。

## 0. 问题

`HEADING_ECHO` 与 `TERM_FIRST_IN_HEADING` 过去按**字面**比对：

- 首句把「预注册」换成「事前登记」，工具以为没有解释；
- 同一概念在一篇里出现三种写法，工具看不见；
- 模型自造新词，没人拦。

本层把「表面形式」压到**规范形（canonical）**再比对，并维护两条术语
判据。批 91 修正了批 90 的两个实测缺陷：词表换错源（工作区流程词覆盖
不到论文、宽松别名误报）与 `TERM_UNREGISTERED` 噪声过大。

## 1. 词表（批 91 分层）

### 1.1 落位与列

两层，UTF-8、Tab 分隔：

| 层 | 文件 | 来源 | 用途 |
|---|---|---|---|
| 论文术语 | `factscribe/terms/paper.tsv` | `paper-zh/GLOSSARY.md`（英文 \| 中文 \| 备注） | 查词 ＋ `TERM_VARIANT` |
| 工作区流程词 | `factscribe/terms/workspace.tsv` | `../sia-harness/nomenclator/terms/*.yaml` | 只查词，不参与 `TERM_VARIANT` |

列：

```
canonical	aliases(en)	aliases(cn)	category	blocked(cn)
```

- `canonical`：规范形，一词一行。
- `aliases(en)` / `aliases(cn)`：同一概念的拉丁文 / 中文表面形式，`|` 分隔。
- `category`：缺省写 `未分类`。
- `blocked(cn)`（可选，论文表用）：备注里「不写「X」「Y」」声明的**禁用
  变体**。它们仍进匹配表（同义归一时视同正名），但 `TERM_VARIANT` 单独
  按禁用变体报。
- 空行与 `#` 开头的注释行忽略；首行列名不作数据；canonical 自身自动视为
  一个表面形式。

### 1.2 生成

两个脚本都可重跑、**覆盖生成**：

```
env PYTHONPATH=src python3 scripts/import-glossary.py [--source <GLOSSARY.md>] [--out <输出>]
env PYTHONPATH=src python3 scripts/import-terms.py [--source <词册目录>] [--out <输出>]
```

- `import-glossary.py` 解析 Markdown 表格（英文 \| 中文 \| 备注），把
  「不写「X」」写进 `blocked(cn)`；并列概念（如「指针／对象存储」）拆成
  两条术语；来源缺失时跳过并提示（退出码 0）。
- `import-terms.py` 导入工作区流程词，默认输出 `workspace.tsv`。
- 文件头注写明来源、生成命令与现算规模；数量现算，文档不写死数字。

### 1.3 项目覆盖（测试与项目追加用）

解析顺序：

1. `style-rules.toml` 的 `term_glossary`（相对项目根解析）；
2. 项目根 `glossary.tsv`（存在则用，视为论文术语表）；
3. 仓内分层词表：`paper.tsv` 在前、`workspace.tsv` 在后。

同名表面形式以 `paper.tsv` 为准（匹配键先到先得）。项目根放同名文件可
覆盖仓内词表，但不改变「仓内自持默认词表」的定位。

## 2. 归一化

### 2.1 拉丁文

表面形式与正文都做：**NFKC → 小写 → 去首尾空白**。

### 2.2 中文

不做分词，改用**最长匹配**扫描：从左到右，每个位置取能匹配的最长表面
形式；同一位置多个候选时取最长，命中后跳过整个命中区间。无命中则前进
一个字符。

### 2.3 标点与全半角

标点、空白、连字符与全半角差异**不参与匹配**：匹配键由 NFKC + 小写后
仅保留字母、数字、CJK 字符与单个空格得到；标点与连字符丢弃，连续空白
压缩为一个空格。因此：

- `pre-registration`、`Pre Registration`、`ｐｒｅｒｅｇｉｓｔｒａｔｉｏｎ`
  命中同一表面形式；
- 中文词内部的标点不阻断命中。

拉丁表面形式保留词边界：命中起点前、终点后不得是字母或数字，避免
`id` 命中 `did` 内部。中文表面形式不加词边界（中文无空格分词）。

`TERM_VARIANT` 计「不同表面形式」时使用归一化后的匹配键，所以大小写、
全半角、连字符差异不产生新形式。

## 3. 三条判据

### 3.1 `TERM_VARIANT`（黄牌，参与计数）

- **输入**：单个文档的全部正文与全部标题；**只在 `paper.tsv` 的条目上判**。
- **算法**（优先禁用变体）：
  1. `paper.tsv` 条目的 `blocked(cn)` 中任一禁用变体出现 → 即报；
  2. 否则同一 canonical 在文档内出现 ≥ `thresholds.term_variant_min_forms`
     （默认 `2`）种**中文**表面形式 → 报。英文列是同一术语的译法，不按
     中文用词一致性计数。
- **输出**：一条 finding，列出 canonical、各写法与各自行号；禁用变体条目
  写明「哪一行用了哪个变体、正名是什么」。
- **边界**：同一写法重复出现只算一种；只在单篇内比较，不跨文件；
  `workspace.tsv` 的流程词不参与（宽松别名如 `成本`→`预算` 不算变体）；
  未在册的表面形式不参与（由 `TERM_UNREGISTERED` 提示）。
- **失败等级**：黄牌；有本项触发时退出码 `3`。

### 3.2 `TERM_UNREGISTERED`（提示，默认关闭，不参与计数）

- **开关**：默认关闭（`style-rules.toml` `term_unregistered = false`）；
  只由 `style --report-unregistered` 显式打开。
- **输入**：只查**标题**，不查首句。
- **候选**：
  - 中文：CJK 2–7 字，两侧是标点/空白/行首尾；不与任何在册命中重叠；
  - 拉丁：≥2 个连续词（可含连字符），同样不与在册命中重叠；
  - 以虚词（的/了/和/与/在/对/是/把/被/而/或）开头或结尾的候选不收；
    内部夹着强句法助词（让/把/被/是/的/了/而/或/且/却）的候选不收。
- **算法**：候选归一化后完整落在词表内（含由多个在册词无缝覆盖）即不报；
  否则出一条提示。
- **通道**：结果单独进 `info`，**不进 `findings`、不计入 `summary.findings`
  与 `fired`**；不影响任何计数门槛与退出码（单独出现仍为 `0`）。

### 3.3 既有规则改按 canonical 比对

- `HEADING_ECHO`：首句与标题先做术语归一；命中的表面形式替换为
  canonical 后再算「新实义」。同义词不再被当成新信息，因此换成同义
  表述**仍判为复述**。
- `TERM_FIRST_IN_HEADING`：标题候选词取其 canonical；首句内出现同一
  canonical 即视为已定义。未在册的候选词退回原有的字面包含判断。
- 白名单 `GLOSSARY.md` + `term-allow.txt` 两层照旧；条目先做归一化，
  再与候选词的归一化键 / canonical 比对。

## 4. 配置

`factscribe/style-rules.toml` 增加：

```toml
# 项目术语表覆盖（相对项目根）；缺省用仓内分层词表
# （paper.tsv 参与 TERM_VARIANT，workspace.tsv 只查词）
# term_glossary = "glossary.tsv"

# TERM_UNREGISTERED 默认关闭；只由 --report-unregistered 打开
term_unregistered = false

[thresholds]
# 同一 canonical 在一篇里出现多少种不同中文表面形式才报 TERM_VARIANT
term_variant_min_forms = 2
```

## 5. 边界与非目标

- 不改 `audit`、`protect` 的判据与退出码；
- 不改正文、不阻断、不评估任何 AI 检测器；
- 不做中文分词、不做词性标注、不做语义相似度（只认同义词表内的等价）；
- 不运行时读取 `sia-harness`；导入是一次性的，之后本仓自持；
- 同形异义（不同 canonical 共用同一表面形式）按词表顺序先到先得，
  导入脚本对冲突直接报错退出，避免静默错归。

## 6. 验收

- `tests/test_terms.py` ≥ 34 例，覆盖同义归一、最长匹配边界、拉丁大小写
  与全半角、`TERM_VARIANT` 正负例（含禁用变体与 workspace 别名不报）、
  `TERM_UNREGISTERED` 默认关闭/只进 info/不影响退码、候选形态收紧、
  `HEADING_ECHO` 换同义表述仍报、白名单归一后命中、两个导入脚本可重跑。
- 验收读数：原文 `paper/` 与 `paper-zh/` 的 `TERM_UNREGISTERED`、
  `TERM_VARIANT` 均为 `0`；v4 改写件的 6 条真实退步（EN-06、EN-10、
  ZH-04、ZH-06、ZH-08、ZH-09）在 `--diff` 中一条不丢。
- 门禁：

```
env PYTHONPATH=src python3 -m unittest discover -s tests
./scripts/preflight-ci.sh
```
