# paperkit — 论文数字与引用的机械闸门（v1）

给 agent（或人）写 LaTeX 论文，但**不许编数字、不许编引用**。
不依赖 sia-harness，不依赖任何模型 SDK，纯标准库，Python ≥ 3.10。

一句话：正文里的每个数字必须**内联绑定**到 `facts/` 里的一条 fact（`\fact{A1}`），
且是该 fact value 里的 token；每条 fact 必须钉住一个带 `sha256`、并在**人签清单**
里的 `results/` 原始产物；每个 `\cite` 家族命令必须落到稳定标识（`arxiv`/`doi`）。
闸门不通过就非零退出。

> **绿 = 「账有据、据未改、文有绑」，不是「论文为真」。** 边界见 `SPEC-V1.md` §2.3。

## 跑起来

```bash
python3 paperkit.py check    <项目目录>            # 账本身：id/sha256/清单/expr/冲突
python3 paperkit.py audit    <项目目录>            # 核心：绑定 + 数字 + 引用 + 覆盖
python3 paperkit.py audit    <项目目录> --resolve  # 再联网核验 arXiv/DOI（可选）
python3 paperkit.py matrix   <项目目录>            # 生成 audit/matrix.md
python3 paperkit.py preamble <项目目录>            # 生成 \fact / \pkignore 宏
python3 paperkit.py build    <项目目录>            # 跑 project.build
```

全部支持 `--json`（给 agent 用；stdout 只出 JSON）；`check/audit` 还有 `--strict`
（黄也当红，CI 用）：

```bash
python3 paperkit.py audit examples/minimal --json
```

退出码：`0`＝绿（无红无黄）；`1`＝红（违例）；`2`＝配置/用法错；`3`＝黄
（未核验/未绑定/未签名/冲突/覆盖不全，不判死但不算绿）；`4`＝工具内部错误。
**不静默通过**：缺 `paperkit.toml`、facts 为空、sections 为空、`refs.bib` 缺失
→ 退出码 2 并说清原因。

## 目录契约

```
<project>/
  paperkit.toml            # 项目声明（必需）
  facts/*.toml             # 事实账，只追加，一条一个 id
  results/                 # 原始实验产物（只读；facts.source 指过来）
  results/MANIFEST.toml    # 人签清单：路径 -> sha256 + signed_by
  sections/*.tex           # 正文（递归匹配 + \input 闭包）
  refs.bib                 # 参考文献，只放已核实条目
  audit/                   # 生成物（matrix.md / preamble.tex，不入库）
```

```toml
[project]
title = "..."
authors = ["..."]
sections = "sections/*.tex"      # 默认递归（同时匹配 sections/**/*.tex）
facts = "facts/*.toml"
bib = "refs.bib"
manifest = "results/MANIFEST.toml"
build = "tectonic -X compile main.tex"   # 留空＝跳过编译
```

```toml
[[fact]]
id = "A2"
claim = "两臂合计准确率"
value = "56.25%"
source = "results/swb16.md"           # 必须在 results/ 下
source_sha256 = "0147ea0c…"           # 现算比对；缺/不符判红
locator = "§三 平均行"
confidence = "high"                   # high | med | low
kind = "claim"                        # claim | config（config 不进全局值域）
derived_from = ["A1", "A3"]           # 非空 ⇒ expr 必填
expr = "(A1.num + A3.num) / (A1.den + A3.den) * 100"   # 只允许四则/括号
supersedes = []
metric = ""
scope = ""
note = ""
```

人签清单 `results/MANIFEST.toml`（工具不生成，人写）：

```toml
[manifest]
signed_by = "moc"
signed_at = "2026-11-07T12:00:00Z"
version = 1

[files]
"results/swb16.md" = "0147ea0c…"
```

## 数字怎么算「回到账上」

- **先绑后算**：正文写 `\fact{A1}`（或 `[[fact:A1]]`，多 id 用逗号）＝「这一行的
  数字属于 A1」。审计反查：该行**每个**数字都必须在所绑 fact 的 value 值域里，否则
  红 `BOUND_MISMATCH`。
- **不绑不算绿**：没绑定但能命中某条 claim fact → 黄 `UNBOUND_NUMBER`（退出码 3）；
  谁都命中不了 → 红 `UNMATCHED_NUMBER`。
- **token 锚定**：`value = "42"` 只接受 `42`，不吃 `1422`/`4242`/`4.2e-5`。
- **唯一词法流水线**：verbatim/verb/`\pkignore` → 注释（`\%` 不是注释）→ 命令参数
  → 上下标（`R^2`、`x_{12}` 是结构量）→ 数字。
- **归一化**：`1,234`＝`1234`、`0.90`＝`0.9`、`10\%`＝`10%`、`53k`＝`53000`、
  `3.5M`＝`3500000`、`3e-4` 整体成 token、`1\,000\,000`＝`1000000`；
  `value = "10/16"` 接受 `10`、`16`、`0.625`。
- **显式豁免**：`\pkignore{...}` 或 `\begin{pkignore}…\end{pkignore}`（内容照排，
  不进审计）。宏由 `paperkit preamble` 生成。
- 未匹配一律报 `文件:行:列 | 数字 | 所在整行`。

## 引用怎么算「落到稳定标识」

- `\cite / \citep / \citet / \citealp / \citeauthor / \citeyear / \upcite /
  \parencite / \textcite / \autocite / \nocite …` 的 key 都必须在 bib 里，否则
  `MISSING_CITE`（红）；认不出的 `*cite*` 命令 fail-closed：`UNKNOWN_CITE_COMMAND`；
- bib 每条按类型要有 `arxiv`/`doi`（`@misc/@online/@software/@dataset` 可用 `url`），
  且格式必须像真的（arXiv 新旧式 / `10.xxxx/...`），否则 `BAD_STABLE_ID_FORMAT`；
- 支持 `\bibliography`/`\addbibresource` 多 bib、`@string` 宏、crossref 一层继承；
- `--resolve` 时查 arXiv API / doi.org（超时 5 秒）：网络失败 → `unverified`（黄）；
  远端明确说不存在 → `UNRESOLVED_CITE`（红）。

## 黄级提示（退出码 3，不判死但不算绿）

- `UNBOUND_NUMBER`：回得到账但没内联绑定；
- `NO_MANIFEST` / `UNSIGNED_RESULT`：没清单，或 results/ 下有未签文件；
- `VALUE_NOT_IN_SOURCE`：fact 的数字没在 source 里出现；
- `LEDGER_CONFLICT` / `DUPLICATE_VALUE`：账本自相矛盾 / 同值多 claim；
- `UNSCANNED_TEX` / `LOW_BINDING_RATE` / `FIGURE_UNVERIFIED`；
- `CITE_UNVERIFIED` / `RESOLVE_DEGRADED`：联网核验没成。

## 提示（info，不影响退出码）

- `UNUSED_FACT`：账上有、文里没用（正文的 marker 才算「用」）；
- `UNUSED_BIB`：bib 里有、文里没引。

## 测试

```bash
python3 -m unittest discover -s tests -v     # 87 例，全离线，约 5 秒
```

`examples/minimal/` 是验收样例：3 条 fact、2 节 tex，故意混入 **1 个编造数字**
（`47.3 ms`）和 **1 个假引用**（`\cite{ghost2024}`）；`audit` 必须报出且只报这
**2 处红**（另有黄项）。红队 B1/B4 反例在 `tests/fixtures/`，现在都红。

裁决与边界见 `SPEC-V1.md`；改动与已知漏洞见 `IMPLEMENTATION-V1.md`。
