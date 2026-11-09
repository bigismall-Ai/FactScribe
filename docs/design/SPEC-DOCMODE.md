# SPEC-DOCMODE — `style --doc`：Markdown 一等公民

批 93。动机：现有 `style` 只认识 LaTeX 项目（必须 `paperkit.toml`，只扫
`sections/*.tex`）。把 Markdown 文件塞进项目跑，实测出现四类错误：

1. 长标题不报 `HEADING_TOO_LONG`（Markdown `#` 标题不被识别）；
2. 代码围栏里的 `——` 被当成正文插入语破折号；
3. 行内代码里的 `——` 同样误报；
4. 标题、正文、代码围栏被当成同一段，行号错位。

本规范给 `style` 增加一个**无需项目配置**的文档入口，并把 Markdown
解析做成独立的可测模块。

## 1. 入口

```
python3 -m factscribe style --doc <文件> [<文件> ...]
python3 -m factscribe style --doc a.md --doc b.md
```

* `--doc` 可重复，也可一次给多个文件（`nargs="+"`，两种写法等价）。
* doc 模式**不需要** `paperkit.toml`，也不读 `sections`/`facts` 配置。
* `--doc` 与位置参数「项目目录」同时给出＝用法错，退出码 2。
* doc 模式不支持 `--diff`（改写前目录属于项目形态），同时给出＝用法错，退出码 2。
* 其它选项（`--json`、`--prompt`、`--rules`、`--report-unregistered`）照常可用。
* 规则文件查找以**当前工作目录**为项目根（`style-rules.toml` → 仓根 → 内置默认值）。

## 2. 格式判定

按文件扩展名逐个判定，一次调用可以混合多种格式：

| 扩展名 | 解析器 |
|---|---|
| `.md` / `.markdown` | Markdown（§3–§6） |
| `.tex` | 现有 LaTeX 解析（`prose_of` + `_headings`） |
| 其它 | 纯文本（不遮罩、无标题） |

`.tex` 走旧路径时行为**逐字节不变**：prose、标题、findings、指标与退出码
都与本批之前相同（回归锁见 `tests/test_docmode.py`）。

## 3. 遮罩（mask）

遮罩把目标区间替换为**等长空白**（换行字符保留），因此任何位置都能直接
换算回原文行号。遮罩清单与顺序：

1. **front matter**：文件第一行是 `---` 时，遮到下一个 `---`（或 `...`）
   行末；没有闭合行则遮到文末。只在文件开头生效。
2. **围栏代码**：行首（最多 3 个空格缩进）的 ``` 或 ~~~（长度 ≥3）开始，
   到同字符、长度 ≥ 开启串、其后只有空白的行结束；**未闭合则到文末**。
   围栏内的一切（包括 `#` 开头的行）都不参与后续规则。
3. **HTML 注释** `<!-- ... -->`：整块遮罩；未闭合则到文末。
4. **行内代码**：`` `...` ``（反引号串长度相等才闭合），可跨行；
   未闭合的行内反引号不遮（宁可漏遮，也不吞掉后文）。
5. **链接与图片目标**：`](...)` 中圆括号内的 URL（含可选 title）遮罩，
   **保留链接文字**与两侧括号；括号可嵌套。
6. **表格行**：行首（最多 3 个空格缩进）为 `|` 的整行遮罩。

遮罩在标题抽取之前完成：围栏里形如 `# 注释` 的行不会被误认成标题。

## 4. 标题

* 语法：`^(#{1,6})\s+(.*)$`；标题行必须在围栏外、front matter 外。
* 去尾部 `#`（`## 标题 ##` → `标题`），再去首尾空白。
* 标题行在 prose 中整行遮罩（与 LaTeX 路径一致），因此句子/段落统计
  不会把标题算成正文；标题规则另走标题清单。
* 标题的 `line` / `end_line` 都是该标题在原文中的行号。

## 5. 段落

* prose 按空行切段（沿用 `style` 现有口径，`min_paragraph_units` 不变）。
* **不跨围栏**：围栏整体遮成空白行，段落天然被围栏隔开；围栏前、后的
  两段不会被合并成一段。
* 表格行、front matter 同样被遮成空白行，不参与段落。

## 6. 行号

遮罩等长替换、换行原样保留，所以 `_line_of(prose, pos)` 直接等于原文行号。
测试逐条断言：报告行号必须等于原文件中该文本所在行。

## 7. 判据面

doc 模式**不跑** LaTeX 专属判据（`\fact` 绑定、`\cite`、`\input` 闭包、
tabular 等表格环境——这些属于 `audit`，`style` 本就不含；doc 模式也不
引入）。实际运行：

* 四条标题规则：`HEADING_TOO_LONG`、`HEADING_MALFORMED`、
  `HEADING_ECHO`、`TERM_FIRST_IN_HEADING`；
* 句级规则：`DASH_PARENTHETICAL`、`CONNECTIVE_DENSITY`、
  `EMPTY_ADJECTIVE`、`HEDGE_STACK`、`SENTENCE_LENGTH_EXTREME`、
  `RHYTHM_PLATEAU`、`PARAGRAPH_TEMPLATE`、`REPEATED_OPENER`、
  `SENTENCE_UNIFORMITY`、`COLLOQUIAL_TRIAD`；
* 术语层：`TERM_VARIANT`（含 Markdown 标题）与可选 `TERM_UNREGISTERED`。
* Markdown 标题常是整句（README 尤其如此）。`TERM_FIRST_IN_HEADING` 在
  doc 模式沿用 `TERM_UNREGISTERED` 的收紧候选面（中文 2–7 字、两侧虚词/
  标点边界；拉丁 ≥2 词），避免把整句按分隔字切成伪术语；LaTeX 路径的
  候选抽取不变。

## 8. 退出码

与项目模式一致：`0` 无问题、`3` 黄牌、`2` 用法错/文件不存在。doc 模式
仍不返回 `1`（`style` 永不判红）。

## 9. 实现边界

* 新模块 `factscribe/mdscan.py`：遮罩、标题、段落所需的解析界面。
* `factscribe/style.py` 只加一个格式分派入口（`analyze(..., formats=...)`）；
  规则与阈值逻辑零改动。
* `factscribe/cli.py` 只加 `--doc` 参数与 doc 分支。
* `prescribe.py`、`terms.py`、`tide.py` 不动。
