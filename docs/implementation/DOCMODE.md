# DOCMODE — `style --doc` 的解析模型与实现记录

批 93。规范：`docs/design/SPEC-DOCMODE.md`。本文件记录实现口径、
修复前后同一文件的读数对比、验收原文与门禁输出。

## 1. 解析模型

```
style --doc FILE...
  └─ cli._cmd_style_doc
       ├─ 按扩展名 mdscan.format_of() 分派：markdown / tex / text
       ├─ 每个文件独立读入 → (路径, 原文)
       ├─ analyze(..., formats={路径: 格式})
       │    └─ style._source_view(原文, 格式)   ← 唯一的格式分派入口
       │         ├─ markdown → mdscan.scan_markdown：等长遮罩 prose + 标题清单
       │         ├─ tex      → prose_of() + _headings()（旧路径，零改动）
       │         └─ text     → 原文 + 无标题
       └─ 判据引擎（阈值、规则、术语层）完全复用，没有第二套规则
```

`style.py` 的改动只有三处接线：

1. `_Doc` 增加 `headings` 字段（标题清单随文档走，不再在判据里回头扫
   LaTeX 命令）；
2. 新增 `_source_view` 格式分派入口；
3. `analyze(..., formats=None)` 参数（默认全 `tex`，旧调用零影响）。

`prescribe.py`、`terms.py`、`tide.py` 未改动。

## 2. 遮罩清单

全部替换为**等长空白**，换行字符保留。顺序如下（前一步遮掉的字符在
后一步已是空白，不会被二次解释）：

| # | 目标 | 边界 | 未闭合时 |
|---|---|---|---|
| 1 | front matter | 文件首行 `---` 到下一 `---` / `...` | 遮到文末 |
| 2 | 围栏代码（``` / ~~~） | 行首≤3 空格；闭合行同字符、长度≥开启串、其后只有空白 | 遮到文末 |
| 3 | HTML 注释 `<!-- ... -->` | 第一个 `-->` | 遮到文末 |
| 4 | 行内代码 `` `...` `` | 反引号串长度相等才闭合，可跨行 | 不遮（不吞后文） |
| 5 | 链接/图片目标 `](...)` | 圆括号可嵌套；只遮括号内 URL，保留链接文字与括号 | 不遮 |
| 6 | 表格行 | 行首≤3 空格后是 `|` 的整行 | 不适用 |

围栏代码按「同字符、长度不小于开启串」闭合，所以 ``` 块里的 ~~~ 行、
~~~ 块里的 ``` 行都按内容处理（嵌套安全）。标题识别在遮罩之后进行，
围栏里形如 `# 注释` 的行不会被误认成标题。

## 3. 行号保持法

遮罩只把非换行字符替换成空格，字符串长度与换行位置都不变。因此：

* `_line_of(prose, pos) = bisect(newlines, pos) + 1` 直接得到**原文行号**；
* 标题清单的 `line` / `end_line` 来自遮罩前逐行扫描的行号；
* 段落、句子、破折号、标题规则共用同一套 `_line_of`，不存在第二套行号
  换算。

修复前三类错位（代码块里的破折号按包裹段落的行号报，出现 3/6/7/10 行）
在 doc 模式下消失；同一文件现在只报第 1 行（标题）与第 3 行（正文）。

## 4. 标题与段落

* 标题：`^(#{1,6})\s+(.*)$`，围栏外、front matter 外；去尾部 `#`；
  标题行在 prose 中整行遮罩，所以标题不会与正文并成一段。
* 段落：沿用 `style` 现有空行切段口径（`min_paragraph_units` 不变）。
  围栏、表格行、front matter 被遮成空白行，段落天然在围栏两侧断开，
  前后两段不会被合并。

## 5. 修复前后：同一文件读数对比

文件（修复前放进一个 `sections/*.md` 的临时项目；修复后直接 `--doc`）：

````markdown
## 这是一个非常非常长的标题用来测试标题长度规则是否生效

正文里有一个插入语破折号——像这样。

```python
# 这行代码里也有长标题和破折号——它不该被检查
x = "——"
```

`行内代码——也不该被检查`
````

### 修复前（旧路径：把 Markdown 当 LaTeX 正文）

```text
DASH_PARENTHETICAL  4   <=0      触发
HEADING_TOO_LONG    0   <=12字/8词  ok

  1. DASH_PARENTHETICAL  sections/doc.md:3
  2. DASH_PARENTHETICAL  sections/doc.md:6
  3. DASH_PARENTHETICAL  sections/doc.md:7
  4. DASH_PARENTHETICAL  sections/doc.md:10
```

错在：长标题没被看见；代码围栏 2 条、行内代码 1 条被计入；行号按包裹
段落算，全部错位。

### 修复后（`style --doc sections/doc.md`）

```text
DASH_PARENTHETICAL  1   <=0      触发
HEADING_TOO_LONG    1   <=12字/8词  触发

  1. DASH_PARENTHETICAL     sections/doc.md:3
     原文：正文里有一个插入语破折号——像这样。
  2. HEADING_TOO_LONG       sections/doc.md:1
     原文：这是一个非常非常长的标题用来测试标题长度规则是否生效
```

现在只剩两条真问题：长标题（第 1 行）与正文里那一处真实插入语破折号
（第 3 行）。代码块与行内代码里的 `——` 零误报。

## 6. 测试

新增 `tests/test_docmode.py`，**27 例**；全仓合计 **523 例**（批前 496）。

覆盖：遮罩等长/换行保持、围栏（含嵌套与未闭合）、行内代码、链接目标与
链接文字、HTML 注释、表格行、front matter、标题解析与尾部 `#`、围栏内
假标题、纯文本、格式判定；端到端覆盖示例的标题与零代码误报、精确行号、
正文破折号、链接文字、表格、front matter、段落不跨围栏、无
`paperkit.toml`、多文件/重复 `--doc`、`.markdown` 扩展名、用法错
（`--doc` + 项目目录、文件不存在）；`.tex` 回归锁对 `examples/minimal`
锁定 metrics、findings、summary 与退出码。

## 7. 验收：README 两条输出（原样）

### `python3 -m factscribe style --doc ../paperkit-dev/README.md`

```text
== factscribe style ==
project : /Users/moc/workspaces/SiAgent/paperkit-dev
正文    : 1 个文件，634 词/字，39 句，18 段
规则    : /Users/moc/workspaces/SiAgent/paperkit-dev/style-rules.toml
阶段    : polished（建议不改，triggers=2，cv=0.53）
判断    : 仅 2 项指标触发（RHYTHM_PLATEAU、TERM_FIRST_IN_HEADING），句长 CV=0.53 在健康区间 [0.45, 0.80]：稿子已到打磨阶段，建议不改。

注意：本工具不评估、也不试图规避任何 AI 检测器；它检测的是可机械判定的公式化写作特征。黄牌只是改写提示，不阻断、不改正文。

指标                    读数      阈值     状态
-----------------------  --------  -------  ----
SENTENCE_LENGTH_EXTREME  0         >60/110  ok
DASH_PARENTHETICAL       0         <=0      ok
HEADING_TOO_LONG         0         <=12字/8词  ok
HEADING_MALFORMED        0         >=1      ok
HEADING_ECHO             0         >=1      ok
HEADING_RELATION_CHANGED  0         >=1      ok
HEADING_SUBJECT_LOST     0         >=1      ok
TERM_FIRST_IN_HEADING    6         >=1      触发
TERM_VARIANT             0         forms>=2  ok
TERM_UNREGISTERED        0         提示       ok
RHYTHM_PLATEAU           1         run>=3   触发
COLLOQUIAL_TRIAD         0         repeat>=2  ok
CONNECTIVE_DENSITY       0         8        ok
EMPTY_ADJECTIVE          0         6        ok
SENTENCE_UNIFORMITY      0.53      0.45-0.8  ok
PARAGRAPH_TEMPLATE       0         0.5      ok
HEDGE_STACK              0         1        ok
REPEATED_OPENER          0         2        ok

[观察] 7 处清单（成品稿：建议不改，以下只作报告）
  1. TERM_FIRST_IN_HEADING  ../paperkit-dev/README.md:12
     原文：装与跑
     改法：标题里的「装与跑」第一次出现时，请在该节首句用一句话定义或点明它是什么（例：预注册是在收集数据前固定假设与分析计划的做法）；复述标题、垫话（如「相关工作里，」）与设问都不算定义。可在 term-allow.txt 登记白名单，只改措辞，不改事实。
  2. TERM_FIRST_IN_HEADING  ../paperkit-dev/README.md:20
     原文：六个命令
     改法：标题里的「六个命令」第一次出现时，请在该节首句用一句话定义或点明它是什么（例：预注册是在收集数据前固定假设与分析计划的做法）；复述标题、垫话（如「相关工作里，」）与设问都不算定义。可在 term-allow.txt 登记白名单，只改措辞，不改事实。
  3. TERM_FIRST_IN_HEADING  ../paperkit-dev/README.md:64
     原文：数字回账
     改法：标题里的「数字回账」第一次出现时，请在该节首句用一句话定义或点明它是什么（例：预注册是在收集数据前固定假设与分析计划的做法）；复述标题、垫话（如「相关工作里，」）与设问都不算定义。可在 term-allow.txt 登记白名单，只改措辞，不改事实。
  4. TERM_FIRST_IN_HEADING  ../paperkit-dev/README.md:83
     原文：黄牌规则
     改法：标题里的「黄牌规则」第一次出现时，请在该节首句用一句话定义或点明它是什么（例：预注册是在收集数据前固定假设与分析计划的做法）；复述标题、垫话（如「相关工作里，」）与设问都不算定义。可在 term-allow.txt 登记白名单，只改措辞，不改事实。
  5. TERM_FIRST_IN_HEADING  ../paperkit-dev/README.md:97
     原文：已知缺口
     改法：标题里的「已知缺口」第一次出现时，请在该节首句用一句话定义或点明它是什么（例：预注册是在收集数据前固定假设与分析计划的做法）；复述标题、垫话（如「相关工作里，」）与设问都不算定义。可在 term-allow.txt 登记白名单，只改措辞，不改事实。
  6. TERM_FIRST_IN_HEADING  ../paperkit-dev/README.md:107
     原文：复现与贡献
     改法：标题里的「复现与贡献」第一次出现时，请在该节首句用一句话定义或点明它是什么（例：预注册是在收集数据前固定假设与分析计划的做法）；复述标题、垫话（如「相关工作里，」）与设问都不算定义。可在 term-allow.txt 登记白名单，只改措辞，不改事实。
  7. RHYTHM_PLATEAU         ../paperkit-dev/README.md:88
     原文：- 与 ：缺人签清单，或有未签产物； - ：事实里的数字没在源文件里出现； - 与 ：账本自相矛盾，或同值多 claim；
     改法：第 88–91 行连续 3 句长度都在 10–19 字：节奏成了平台，在其中插入一句 8–15 字的短句，或把相邻两句合并，让长短有起伏；内容与结构不动

说明：本闸只报「可机械判定的公式化写法」，不评估、也不试图规避任何 AI 检测器；不阻断构建、不改正文。
文档模式：1 个文件（markdown）
```

### `python3 -m factscribe style --doc ../paperkit-dev/README.en.md`

```text
== factscribe style ==
project : /Users/moc/workspaces/SiAgent/paperkit-dev
正文    : 1 个文件，393 词/字，40 句，16 段
规则    : /Users/moc/workspaces/SiAgent/paperkit-dev/style-rules.toml
阶段    : polished（建议不改，triggers=2，cv=0.62）
判断    : 仅 2 项指标触发（RHYTHM_PLATEAU、TERM_FIRST_IN_HEADING），句长 CV=0.62 在健康区间 [0.45, 0.80]：稿子已到打磨阶段，建议不改。

注意：本工具不评估、也不试图规避任何 AI 检测器；它检测的是可机械判定的公式化写作特征。黄牌只是改写提示，不阻断、不改正文。

指标                    读数      阈值     状态
-----------------------  --------  -------  ----
SENTENCE_LENGTH_EXTREME  0         >60/110  ok
DASH_PARENTHETICAL       0         <=0      ok
HEADING_TOO_LONG         0         <=12字/8词  ok
HEADING_MALFORMED        0         >=1      ok
HEADING_ECHO             0         >=1      ok
HEADING_RELATION_CHANGED  0         >=1      ok
HEADING_SUBJECT_LOST     0         >=1      ok
TERM_FIRST_IN_HEADING    3         >=1      触发
TERM_VARIANT             0         forms>=2  ok
TERM_UNREGISTERED        0         提示       ok
RHYTHM_PLATEAU           4         run>=3   触发
COLLOQUIAL_TRIAD         0         repeat>=2  ok
CONNECTIVE_DENSITY       0         8        ok
EMPTY_ADJECTIVE          0         6        ok
SENTENCE_UNIFORMITY      0.62      0.45-0.8  ok
PARAGRAPH_TEMPLATE       0         0.5      ok
HEDGE_STACK              0         1        ok
REPEATED_OPENER          0         2        ok

[观察] 7 处清单（成品稿：建议不改，以下只作报告）
  1. TERM_FIRST_IN_HEADING  ../paperkit-dev/README.en.md:20
     原文：Six commands
     改法：标题里的「Six commands」第一次出现时，请在该节首句用一句话定义或点明它是什么（例：预注册是在收集数据前固定假设与分析计划的做法）；复述标题、垫话（如「相关工作里，」）与设问都不算定义。可在 term-allow.txt 登记白名单，只改措辞，不改事实。
  2. TERM_FIRST_IN_HEADING  ../paperkit-dev/README.en.md:84
     原文：Yellow rules
     改法：标题里的「Yellow rules」第一次出现时，请在该节首句用一句话定义或点明它是什么（例：预注册是在收集数据前固定假设与分析计划的做法）；复述标题、垫话（如「相关工作里，」）与设问都不算定义。可在 term-allow.txt 登记白名单，只改措辞，不改事实。
  3. TERM_FIRST_IN_HEADING  ../paperkit-dev/README.en.md:97
     原文：Known gaps
     改法：标题里的「Known gaps」第一次出现时，请在该节首句用一句话定义或点明它是什么（例：预注册是在收集数据前固定假设与分析计划的做法）；复述标题、垫话（如「相关工作里，」）与设问都不算定义。可在 term-allow.txt 登记白名单，只改措辞，不改事实。
  4. RHYTHM_PLATEAU         ../paperkit-dev/README.en.md:80
     原文：Every family key must exist in , otherwise red . Each bib entry needs or ; entries may use .
     改法：第 80–82 行连续 3 句长度都在 0–9 词：节奏成了平台，在其中插入一句 8–15 词的短句，或把相邻两句合并，让长短有起伏；内容与结构不动
  5. RHYTHM_PLATEAU         ../paperkit-dev/README.en.md:88
     原文：- : traceable but unbound; - and : no signed manifest, or unsigned artifacts; - : a ledger number absent from its source file; - and : self-contradicting ledge…
     改法：第 88–94 行连续 6 句长度都在 0–9 词：节奏成了平台，在其中插入一句 8–15 词的短句，或把相邻两句合并，让长短有起伏；内容与结构不动
  6. RHYTHM_PLATEAU         ../paperkit-dev/README.en.md:102
     原文：- derived facts whose expression disagrees with the stored value; - dynamic targets; - diagnostic-only error codes.
     改法：第 102–105 行连续 3 句长度都在 0–9 词：节奏成了平台，在其中插入一句 8–15 词的短句，或把相邻两句合并，让长短有起伏；内容与结构不动
  7. RHYTHM_PLATEAU         ../paperkit-dev/README.en.md:117
     原文：Specs live in , implementation notes in , history in . Read before opening a pull request. Tests are required.
     改法：第 117–119 行连续 3 句长度都在 0–9 词：节奏成了平台，在其中插入一句 8–15 词的短句，或把相邻两句合并，让长短有起伏；内容与结构不动

说明：本闸只报「可机械判定的公式化写法」，不评估、也不试图规避任何 AI 检测器；不阻断构建、不改正文。
文档模式：1 个文件（markdown）
```

README 仍是旧稿，出现黄牌是预期行为——这一批要的是「它终于看见了」：
下划线代码围栏、表格、行内代码都已遮罩，标题与正文按原文行号分别检查。

## 8. 门禁输出

### `env PYTHONPATH=src python3 -m unittest discover -s tests`

```text
----------------------------------------------------------------------
Ran 523 tests in 35.126s

OK
```

### `./scripts/preflight-ci.sh --fast`

```text
== 步骤 1/4：外部依赖（CI 装了 poppler；本机没有则 PDF 测试会红）
   ✓ pdftotext：/opt/homebrew/bin/pdftotext
   ✓ pdfinfo：/opt/homebrew/bin/pdfinfo
   ✓ PDF 工具齐备

== 步骤 2/4：干净克隆（--fast：跳过，直接用工作区）

== 步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12）
   ✓ Python 3.10：Ran 523 tests
   ✓ Python 3.11：Ran 523 tests
   ✓ Python 3.12：Ran 523 tests

== 步骤 4/4：验收样例必须 exit 1（workflow 的硬断言）
   ✓ examples/minimal audit exit=1（红，符合预期）

== 结论
   本地等价 CI 全绿——可以推。
```

另在 `./scripts/preflight-ci.sh`（干净克隆，只含已提交文件）下复跑，
3.10 / 3.11 / 3.12 三档各 Ran 523 tests，验收样例 `examples/minimal`
audit exit=1，结论全绿。
