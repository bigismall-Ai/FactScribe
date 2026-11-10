# paperkit SPEC v1 —— 红队裁决与新契约

日期：2026-11-07　　对象：`SPEC.md`（v0，红队攻击稿 `/tmp/pk-redteam/RED.md`，29 条）
闸门实现：commit `b9a66e3`（代码 + 测试 + 反例夹具）

---

## 0. 一句话

v0 只检查「正文和账本彼此自洽」；v1 把正文数字**钉到具体的 fact**，把 fact 钉到**带
sha256 的原始产物**，再把原始产物钉到**人签清单**。绿的含义随之下沉为：

> **绿＝「账有据、据未改、文有绑」，不是「论文为真」。**

---

## 1. 红队 29 条逐条裁决

裁决口径：

- **采纳**＝红队指出的缺口成立，v1 已落成机械检查；
- **部分采纳**＝缺口成立，v1 只落了能力范围内/性价比最高的那一半，另一半写进 §7 已知风险；
- **驳回**＝红队给的**修法**会制造更大的洞（缺口本身另行处理）。

| # | 级 | 红队主张（一句） | 裁决 | v1 怎么改 / 为什么不 |
|---|---|---|---|---|
| B1 | 阻断 | 值级匹配退化成数字白名单；子串实现让编造数字全绿 | **采纳** | 匹配改 token 锚定（正则边界 + 数值规范化），正文数字必须**内联绑定**到 fact 并在该 fact.value 里；未绑定命中只算黄，未命中红。`\fact{}` 绑定是硬约束。 |
| B2 | 阻断 | 只写死 `\cite{a,b}`，natbib 全家不被检查 | **采纳** | 抽取改为「任意 `*cite*` 命令 + 可选参数」；未知 `*cite*` 命令 fail-closed 判红（`UNKNOWN_CITE_COMMAND`）；`\nocite{key}` 也核。 |
| B3 | 阻断 | 跳过注释与 `\%` 归一化无顺序规定 | **采纳** | 写死唯一流水线：verbatim/verb/pkignore → 注释（`\%` 先于裸 `%`）→ 命令参数 → 上下标 → 数字。verbatim 内 `%` 不再是注释。 |
| B4 | 阻断 | `sections/*.tex` 单层 glob，嵌套章节整体逃逸 | **采纳** | glob 默认递归（`sections/*.tex` 同时匹配 `sections/**/*.tex`）+ 解析 `\input/\include/\subfile` 闭包；`coverage.files_scanned` 进报告；闭包外 `.tex` 黄。 |
| B5 | 阻断 | `build` 是 shell 字符串 → RCE | **部分采纳** | 规格 v1 改为**argv 数组 + 可执行文件允许列表 + 超时**（§3.2）；代码 v1.0 仍按字符串执行并加 600s 超时，RCE 面列入 §7，v1.1 落。 |
| B6 | 阻断 | `source` 只验存在 → 账与正文同源编造 | **部分采纳** | 已落：`source_sha256` 现算比对 + `results/MANIFEST.toml` 人签清单 + value 数字必须字面出现在 source。未落：工具级 append-only 载体（靠 git/hook，见 §2.3）。 |
| B7 | 阻断 | 派生值无算术校验，`derived_from` 可空 | **采纳** | 派生 fact 必写 `expr`；工具用 `ast` 白名单求值（四则+括号+`ID.num/.den`），与 value 比对；环检测；父被 supersedes 判红。禁 `eval`。 |
| B8 | 阻断 | 退出码混语义，「0=无红」被读成可信 | **采纳** | 0 绿 / 1 红 / 2 配置 / 3 黄 / 4 内部错；报告头出 coverage；JSON 带 `schema_version`/`severity`；文档明写「0≠真」。 |
| C1 | 严重 | 数学模式二难：抽则误报，不抽则漏报 | **部分采纳** | 取第三条路：`^`/`_` 的上下标视为结构量整段掩码；带 `=` 的数值照审。不做「数学模式整体跳过」也不做「数学模式全抽」。 |
| C2 | 严重 | 年份/章节号/图表号让整节变红 | **驳回** | 反对按模式自动豁免（`2019` 既可能是年份也可能是「2019 条数据」，自动豁免会埋真漏洞）。改给**显式出口** `\pkignore{...}`；结构性数字靠上下标掩码与绑定消解。 |
| C3 | 严重 | 超参/尺寸/间距无豁免位 | **部分采纳** | `kind = "config"` 入 schema，config 事实**不进全局值域**（不能当白名单），只可在绑定语境下核销；命令参数已整体豁免。不做「数值+名称成对」的全文 NLP。 |
| C4 | 严重 | 归一化覆盖不到真实写法 | **部分采纳** | 已补：科学计数法整体成 token、`\,`/`~`/`;`/`{ , }` 千分位、`percent`/`pct`、`k/M/B`、`±` 复合值拆两数各自匹配。未补：万/亿、Unicode minus、复合 value 对多数字（记 §7）。 |
| C5 | 严重 | 归一化过度：单位丢失、舍入无政策 | **部分采纳** | `%` 转成 `/100` 的独立值域，不再把 `16%` 当计数 `16` 静默命中（但 value 同时登记裸数别名这点仍是隐患，§7）；舍入政策 v1 取「不猜」：要么精确、要么写 derived expr。显示精度容差留 v2。 |
| C6 | 严重 | 事实使用率只是提示，账本可膨胀成白名单 | **采纳** | 未绑定数字只黄；`LOW_BINDING_RATE`（绑定率<50% 黄）、`DUPLICATE_VALUE`（同值多 claim 黄）、`kind=config` 不进全局值域。 |
| C7 | 严重 | bib 只查字段存在，不查格式/题名，DOI 不 resolve | **部分采纳** | 已补：arXiv 新旧格式/DOI/URL 格式校验，非法即红；arXiv 与 DOI 都能 `--resolve`；未核验升黄。未补：题名/作者相似度比对、默认联网（离线契约优先）。 |
| C8 | 严重 | 可选参数/多 bib/`@string`/crossref/`@misc` 误判 | **部分采纳** | 已补：可选参数、`\bibliography`/`\addbibresource` 多 bib、`@string` 宏、crossref 一层继承、`@misc/@online/@software/@dataset` 允许 `url`。未补：biblatex 全语法。 |
| C9 | 严重 | 冲突靠 claim 全等，`supersedes` 无 schema | **部分采纳** | `supersedes` 已入 schema；冲突优先按 `metric + scope` 结构化分组；冲突从「提示」升为**黄（退出码 3）**。claim 自由文本仍按全等（语义冲突需作者写 metric）。 |
| C10 | 严重 | `[[fact:A2]]` 无宏定义、标记含数字、绑定装饰化 | **采纳** | 定义 `\fact{ID}` 硬约束（标记区不进数字抽取，未知 id 红，行内数字必须匹配）；新增 `paperkit preamble` 生成 `\providecommand{\fact}[1]{}` 等宏。 |
| C11 | 严重 | 值级核销，命题与数字语义错配不可见 | **采纳** | 绑定作用域＝行：该行每个数字必须落在所绑定 fact 的 value 里；未绑定不再能换来绿。多个事实同行需写多个 id。 |
| D1 | 一般 | 默认 UA 被限流 → 全 unverified → 全绿 | **部分采纳** | UA 带版本、超时已有；unverified 升黄、失败率 >50% 再出一条 `RESOLVE_DEGRADED` 黄。缓存/指数退避未做。 |
| D2 | 一般 | unverified 在默认视图看不见 | **采纳** | 黄块置顶、计入退出码 3；`--strict` 把黄当红。 |
| D3 | 一般 | 重复键/重复 DOI/`\nocite{*}` 无处理 | **部分采纳** | 重复 bib key 红；同一稳定标识多 key 黄；`\nocite{*}` 合法放行、`\nocite{key}` 照核。悬空 crossref 未单独报（随缺标识红）。 |
| D4 | 一般 | source 接受 URL/绝对路径/目录；示例自相矛盾 | **采纳** | source 必须是项目内相对路径、落在 `results/` 下、普通文件；示例 `examples/minimal` 已改到 results/。 |
| D5 | 一般 | id 大小写/空白不归一；audit 与 check 依赖未定义 | **部分采纳** | id 判重按大小写不敏感；空白/非法字符直接红（不静默归一）；`audit` 自带 source/账本校验，不依赖先跑 `check`。 |
| D6 | 一般 | 报告无覆盖率/置信度分布，low 与 high 混计 | **采纳** | `summary.coverage`（扫描文件/glob 命中/未扫/facts/parse_errors/sha 钉住）＋ `summary.confidence` 分布进 JSON 与人读头。 |
| D7 | 一般 | `audit/` 不入库，无法证明某提交被审过 | **部分采纳** | JSON 带 `attestation.facts_sha256`、`sources_sha256`、`git_commit`；是否把 attestation 入库仍由人决定（工具不擅自写版本控制）。 |
| D8 | 一般 | 验收钉在「恰好 2 处」，鼓励收紧抽取 | **采纳** | 验收改分层：示例「必须含这 2 处」子集断言 + 红队反例夹具（B1/B4）+ 变体语料（citep/嵌套目录/verbatim/科学计数法）+ 全量单测。 |
| D9 | 一般 | `--json` 无 schema；混排 | **采纳** | 固定 `schema_version`、`severity`、`coverage`；`--json` 时 stdout 只出 JSON，人读文本走非 json 分支。 |
| D10 | 一般 | 最要命的数字在图里 | **部分采纳** | 每个 `\includegraphics` 找不到同名 `.csv` 时出黄 `FIGURE_UNVERIFIED`（显式登记「图里数字未核验」）。不解析 PNG。 |

**计数：采纳 14（B1/B2/B3/B4/B7/B8/C6/C10/C11/D2/D4/D6/D8/D9）；部分采纳 14（B5/B6/C1/C3/C4/C5/C7/C8/C9/D1/D3/D5/D7/D10）；驳回 1（C2）。**

---

## 2. 核心质疑：「绿 = 自洽，自洽 ≠ 真」

红队的总攻成立：v0 里账本、正文、`results/` 可以由同一次生成写出，闸门只验三者彼此
一致。v1 不假装能解决「真」，只做一件事：**把「自洽」换成「可追溯到一个被锁定的
内容锚」**，并把不在此列的东西明确标黄。

### 2.1 一层防线：内容锚定绑定链

```
人签清单 results/MANIFEST.toml（signed_by + [files] 路径→sha256）
   │  ① 清单锁住 results/ 里每个文件的字节
   ▼
原始产物 results/*.md（sha256 = 清单里那个值）
   │  ② fact.source_sha256 现算比对
   ▼
事实账 facts/*.toml（value + source + locator + confidence + expr）
   │  ③ value 里的数字必须字面出现在 source 里（内容回查）
   ▼
正文 \fact{ID} ... 数字
   │  ④ 绑定是硬约束：该行每个数字都必须在该 fact.value 的值域里
   ▼
闸门：0 绿 / 1 红 / 3 黄
```

链上每一环都是**机械可验**的，信任根只有一个：**人签清单的那一刻**。这层防线的效果：

- agent 想编一个数字，必须先让它进入一个 `results/` 文件，且该文件被人签过；
- 签过之后再改文件 → sha256 立刻红；
- fact 的值不来自所签文件 → value 回查黄；
- 正文数字不绑或绑错 → 未绑定黄 / 绑定不符红；
- 账与文互相对得上但都不在清单里 → 黄（而不是绿）。

### 2.2 它把「全绿伪造」收窄成什么

v0 的双杀反例（RED.md 附录：`results/` 自己写、账自己写、正文自己写）在 v1 里：

- 没有 `MANIFEST.toml` → 黄（退出码 3，CI 不得当绿）；
- 有清单但 `signed_by` 空 → 红；
- 清单里的哈希与文件不符 → 红；
- `value = "42"` 但 source 里没有 42 → 黄；
- 正文 `12%`/`42 ms`/`3 epochs` 不绑定 → 分别黄或红；
- `\citep{hallucinated2023}` → 红（键不存在）。

**结论：伪造不再是「零成本全绿」，而必须变成「让一个人签一份自己没看过的编造产物」。**
这是工具能守住的最后一米，再往前就不是工具能解决的了。

### 2.3 防不住的边界（诚实清单）

1. **人签 ≠ 人看**：信任根是 `signed_by`。人若盖章式签署 agent 刚生成的 `results/`，
   链上全绿而内容仍可能是编的。工具只保证「从签过那刻起没被改」。
2. **字面出现 ≠ 语义正确**：value 回查只证明「这个数字在这份文件里出现过」，不证明它
   就是 `claim` 说的那件事。`10/16` 出现在文件里，不代表这 16 道题就是那 16 道题。
3. **绑定粒度是「行」**：一行里写两个事实、或一段话横跨多条 fact 时，仍可能把 A 的数
   挂到 B 的命题上。v1 用「多 id 联合值域」缓解，不做句法级作用域。
4. **引用只验标识，不验内容**：默认离线、不比对题名/作者。格式合法但语义编造的 DOI
   在默认路径仍放行（除非 `--resolve` 且远端确实不存在）。
5. **图/表里的数字不在覆盖内**：没有随图 `.csv` 时只出黄；`matrix.md` 也不解析图。
6. **分词是启发式**：`10 000` 可能被合并成一万；万/亿、Unicode minus、复合值（`12.4±3.1`）
   仍有边界；`kind=config` 的 value 同时登记裸数别名是已知宽松点。
7. **账本「只追加」靠 git**：工具不写 VCS、不做哈希链签名；改写历史仍可绕过。
8. **`build` 仍是 shell 字符串（v1.0）**：`paperkit build` 会执行仓库里的任意命令，
   只在你会信任该仓库时才跑（规格 v1 已要求 argv 允许列表，v1.1 落）。
9. **绿不代表可复现**：它只说明「账有据、据未改、文有绑」；实验设计、统计口径、
   结论正确性都不在闸门能力范围内。

---

## 3. v1 契约

### 3.1 目录

```
<project>/
  paperkit.toml
  facts/*.toml
  results/                   # 原始产物；清单在这里
    MANIFEST.toml            # 人签清单（工具不生成）
  sections/*.tex             # 递归匹配，且自动展开 \input 闭包
  refs.bib                   # 可再加 \addbibresource 声明的其他 bib
  audit/                     # 生成物（matrix.md / preamble.tex），不入库
```

### 3.2 `paperkit.toml`

```toml
[project]
title = "..."
authors = ["..."]
sections = "sections/*.tex"      # 默认递归（等价于同时匹配 sections/**/*.tex）
facts = "facts/*.toml"
bib = "refs.bib"
manifest = "results/MANIFEST.toml"   # 可省，默认此路径
build = "tectonic -X compile main.tex"  # v1.0 兼容字符串；v1.1 改 argv 数组 + 允许列表
```

### 3.3 `facts/*.toml`（schema v1）

```toml
[[fact]]
id = "A2"                 # 必填；字母开头，[A-Za-z0-9_.:-]，大小写不敏感判重
claim = "两臂合计准确率"
value = "56.25%"
source = "results/swb16.md"        # 必须：项目内相对路径 + 在 results/ 下 + 普通文件
source_sha256 = "0147ea0c…"        # 必须：源文件现算 sha256，必须与清单一致
locator = "§三 平均行"             # 给人看的锚点；v1 不机械校验（§2.3）
confidence = "high"                # high | med | low
kind = "claim"                     # claim（进全局值域）| config（只在绑定语境下核销）
derived_from = ["A1", "A3"]        # 非空 ⇒ expr 必填
expr = "(A1.num + A3.num) / (A1.den + A3.den) * 100"   # 只允许四则/括号/ID.num/ID.den
expr_tolerance = "1e-6"            # 可选：expr↔value 的相对容差；缺省沿用 1e-9
supersedes = []                    # 改事实＝新增一条并指向旧 id
metric = ""                        # 可选：结构化冲突分组键
scope = ""                         # 可选：metric 的作用域（数据集/切分）
note = ""
```

### 3.4 正文绑定

- 绑定写成 `\fact{ID}`（或 `[[fact:ID]]`，多 id 用逗号），**作用于同一行**；
- 该行每个数字都必须是所绑定 fact 的 `value` 的 token（数值规范化后等值）；
- 该行已绑定定量 fact、但数字不在其值域内 → 红 `BOUND_MISMATCH`（不管数字在
  同一句还是同一行的另一句）；退出码仍是 1，红级不变；
- 该行没有任何绑定、且谁都命中不了 → 红 `UNMATCHED_NUMBER`；
- 未绑定但能命中某条 claim fact → 黄 `UNBOUND_NUMBER`；
- 未知 id → 红 `UNKNOWN_FACT_MARKER`；
- 显式豁免区：`\pkignore{...}` 与 `\begin{pkignore}…\end{pkignore}`（内容照排，不进审计）；
- 宏由 `paperkit preamble` 生成到 `audit/preamble.tex`，正文导言区 `\input` 即可。

### 3.5 人签清单

```toml
[manifest]
signed_by = "alice"                    # 必填；空 ⇒ 红 MANIFEST_UNSIGNED
signed_at = "2026-11-07T12:00:00Z"   # 缺 ⇒ 黄
version = 1

[files]
"results/swb16.md" = "0147ea0c…"     # 路径相对项目根；sha256 必须与现文件一致
```

规则：fact 用到的 source 不在清单 → 红；清单哈希不符 → 红；`results/` 下有文件没进
清单 → 黄。缺清单 → 黄（不是绿）。

### 3.6 v1.3 补的三条判据（KNOWN-GAPS 第二节）

| 判据 | 触发 | 结果 | 退出码 |
|---|---|---|---|
| 动态闭包目标 | `\input{...}` / `\include{...}` 的目标含宏（`\jobname`、`\macro` 等）、`#`、嵌套花括号，或为空 | 红 `INPUT_DYNAMIC`；报 `文件:行` 与**原始目标串** | 5 |
| 派生算式不符 | fact 同时有 `value` 与 `expr`，expr 求值结果与 value 不一致 | 红 `EXPR_MISMATCH`；报两侧数值与误差 | 1 |
| 绑定后不符 | 该行已绑定定量 fact，但数字不在其值域内 | 红 `BOUND_MISMATCH`（不再是 `UNMATCHED_NUMBER`） | 1 |

三条的边界：

1. **动态目标 fail-closed**：静态审计覆盖不了的目标不许绿。静态目标（含省略 `.tex`
   的写法）行为不变；目标不存在仍走 `INPUT_TARGET_MISSING`。注释/verbatim 里的
   `\input` 不算；`\newcommand{\X}[1]{\input{#1}}` 的宏体是定义、不是实际包含。
2. **表达式容差**：沿用 `check` 既有的数值比较口径——相对误差 `1e-9`（以 value 为
   基准，`max(1, |value|)`）。fact 可写 `expr_tolerance = "1e-6"` 显式放宽/收紧；
   不新造第二套浮点规则。没有 `expr` 的 fact 行为不变；expr 不可求值仍报
   `EXPR_INVALID`。
3. **分诊只改分类**：`BOUND_MISMATCH` 与 `UNMATCHED_NUMBER` 都是红、exit 1；
   未绑定但回得到账的 `UNBOUND_NUMBER` 仍是黄、exit 3。该行没有定量 fact 绑定时，
   才退回 `UNMATCHED_NUMBER`。

---

## 4. 闸门判定细则（v1.0 实现）

| 闸 | 触发 | 结果 |
|---|---|---|
| G1 内联绑定 | 行内数字 ∈ 绑定 fact 值域 | 绿；不在 → `BOUND_MISMATCH` 红 |
| G1' 未绑定 | 命中全局 claim 值域 | `UNBOUND_NUMBER` 黄（不再换绿） |
| G1'' 未绑定 | 行内无绑定且谁都命中不了 | `UNMATCHED_NUMBER` 红 |
| G2 源头 | 缺 sha / sha 不符 | `MISSING_SOURCE_SHA256` / `SOURCE_SHA256_MISMATCH` 红 |
| G2' 清单 | 未签/未列/哈希不符/无 signed_by | `SOURCE_NOT_SIGNED` / `MANIFEST_HASH_MISMATCH` / `MANIFEST_UNSIGNED` 红；`NO_MANIFEST` / `UNSIGNED_RESULT` 黄 |
| G2'' 回查 | value 数字不在 source | `VALUE_NOT_IN_SOURCE` 黄 |
| G3 引用 | `*cite*` 全家 + 可选参数；未知命令 fail-closed | `MISSING_CITE` / `UNKNOWN_CITE_COMMAND` / `BAD_STABLE_ID_FORMAT` 红 |
| G4 退出码 | 见 §5 | 0 / 1 / 2 / 3 / 4 / 5 |
| G5 派生 | 无 expr / expr 算不对 / 成环 / 父被 supersedes | `MISSING_EXPR` / `EXPR_MISMATCH` / `EXPR_INVALID` / `DERIVED_CYCLE` / `SUPERSEDED_PARENT` 红（`audit` 与 `check` 同判） |
| G6 覆盖 | 闭包外 `.tex`；绑定率 <50%；重复 value；同值多 bib | `UNSCANNED_TEX` / `LOW_BINDING_RATE` / `DUPLICATE_VALUE` / `DUPLICATE_STABLE_ID` 黄 |
| G7 闭包 | 目标不存在 / 目标动态不可解析 | `INPUT_TARGET_MISSING` / `INPUT_DYNAMIC` 红，exit 5 |

---

## 5. 退出码与 `--json`

| 码 | 含义 | CI 建议 |
|---|---|---|
| 0 | 绿：完整覆盖，无红无黄 | 可继续；**不等于内容为真** |
| 1 | 红：违例 | 阻断 |
| 2 | 配置/用法错（工具没跑起来） | 修配置，别当「论文造假」 |
| 3 | 黄：未核验/未绑定/未签名/冲突/覆盖不全 | 默认阻断（或 `--strict` 变 1） |
| 4 | 工具内部错误 | 报 bug |

```json
{
  "schema_version": "1.0",
  "command": "audit",
  "status": "yellow",
  "severity": "yellow",
  "exit": 3,
  "issues":  [{"severity": "red", "code": "...", "location": "file:line:col", "token": "...", "context": "..."}],
  "warnings":[{"severity": "yellow", "code": "...", "...": "..."}],
  "hints":   [{"severity": "info", "...": "..."}],
  "summary": {"red": 0, "yellow": 1, "numbers_bound": 4,
              "coverage": {"files_scanned": [], "files_unscanned": [], "sha_pinned": 3},
              "confidence": {"high": 2, "med": 1, "low": 0},
              "attestation": {"facts_sha256": "...", "git_commit": "..."}}
}
```

`--json` 时 stdout **只**输出 JSON；人读文本只在非 json 模式输出。

---

## 6. 验收（v1，分层）

1. **示例子集断言**：`examples/minimal` 的 `audit` 必须报出 `47.3`（未进账）与
   `ghost2024`（不存在），且退出码 1；其余黄项允许存在。
2. **反例夹具必须红**（`tests/fixtures/`）：
   - `redteam-b1`：短 value `42` + 正文 `1422 / 4.2e-5 / 4242` → 三个 `UNMATCHED_NUMBER`；
   - `redteam-b4`：`sections/chapters/intro.tex` 里的 `3.7% / 12` → 必须报出该文件。
3. **变体语料**：`\citep/\citet/\citeauthor/\nocite`、可选参数、嵌套目录、verbatim、
   科学计数法、千分位、上下标各至少 1 正 1 负（见 `tests/test_paperkit.py`）。
4. **全量单测**：`python3 -m unittest discover -s tests` 87 例全绿、全离线。
5. 不再使用「恰好 2 处、一处不多」作为验收总判据（它奖励漏报，红队 D8）。

---

## 7. 已知风险 / 明确不做（v1.0）

1. `build` 仍是 shell 字符串（B5 只落了规格，代码 v1.1 落 argv 允许列表）。
2. 清单之外没有 append-only 载体（B6 的账本部分靠 git，不在工具内）。
3. `kind=config` 的 value 仍登记裸数别名；百分比的单位歧义（计数 vs 比率）未彻底解决。
4. 不做舍入容差：`0.9483` 的账不接受正文 `95%`（要么写精确值，要么写 derived）。
5. 不比对 bib 题名/作者；默认不联网；`--resolve` 无缓存/退避。
6. 图里数字只黄不核；不解析 PNG/PDF。
7. 绑定作用域＝行，不是句法/段落级；`locator` 不做机械定位。
8. 万/亿、Unicode minus、复合 value 对多数字未覆盖。
9. 语义真值、实验可复现性、结论正确性：**不在本工具能力范围**。

---

## 8. 裁决 → commit 留痕

| 裁决 | 落点 | commit |
|---|---|---|
| B1 / C11 / C10（绑定与命题级） | `paperkit.py` `scan_tex`/`run_audit`；`\fact` 硬约束；`preamble` 命令 | `b9a66e3` |
| B2 / C8 / D3（引用与 bib） | `_CITE_RE`/`_CITE_KNOWN`/fail-closed；`parse_bib` @string/crossref/多 bib；`valid_stable_id` | `b9a66e3` |
| B3 / C1 / C4（词法流水线） | `_mask_envs_and_verb`/`_mask_scripts`/`_NUM_RE`/`_extract_numbers` | `b9a66e3` |
| B4 / B8 / D6 / D7 / D9（覆盖/退出码/报告） | `_glob_paths`/`load_sections`/`all_tex_files`；`_exit_code`；`coverage`/`attestation`/schema | `b9a66e3` |
| B6 / D4（源头锚定） | `verify_sources`/`sha256_file`/清单校验；示例改 `results/` | `b9a66e3` |
| B7（派生算术） | `eval_expr`/`_cycles`/`MISSING_EXPR`/`SUPERSEDED_PARENT` | `b9a66e3` |
| C6 / C9 / D5（账本卫生） | `kind`/`metric`/`scope`；`LOW_BINDING_RATE`/`DUPLICATE_VALUE`；id 判重 | `b9a66e3` |
| D2 / D8（验收与黄级） | 黄块置顶、`--strict`；反例夹具与变体测试 | `b9a66e3` |
| C2（驳回自动豁免） | 只落显式 `\pkignore`，无自动年份豁免 | `b9a66e3` |
| B5 / C3 / C5 / C7 / D1 / D10（部分采纳的剩余半） | 只落规格与本文件 §7，代码留 v1.1 | 本件（文档） |
| 本裁决表与契约 | `SPEC-V1.md` / `IMPLEMENTATION-V1.md` | 本件入库 commit（`git log -- SPEC-V1.md`） |

---

*本规格只承诺「可追溯」，不承诺「为真」。任何把绿读成「已核实真伪」的用法都超出了
工具的能力边界。*
