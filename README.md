# paperkit — 论文数字与引用的机械闸门（MVP）

给 agent（或人）写 LaTeX 论文，但**不许编数字、不许编引用**。
不依赖 sia-harness，不依赖任何模型 SDK，纯标准库，Python ≥ 3.10。

一句话：正文里的每个数字必须能回到 `facts/` 账；每个 `\cite{...}` 必须能在
`refs.bib` 里落到一个稳定标识（`arxiv` 或 `doi`）。闸门不通过就非零退出。

## 跑起来

```bash
python3 paperkit.py check  <项目目录>            # 账本身干不干净
python3 paperkit.py audit  <项目目录>            # 核心：数字 + 引用对账
python3 paperkit.py audit  <项目目录> --resolve  # 再联网核验 arXiv/DOI（可选）
python3 paperkit.py matrix <项目目录>            # 生成 audit/matrix.md
python3 paperkit.py build  <项目目录>            # 跑 project.build
```

四个命令都支持 `--json`（给 agent 用；stdout 只出 JSON）：

```bash
python3 paperkit.py audit examples/minimal --json
```

退出码：`0`＝无红；`1`＝有红（或 build 失败）；`2`＝配置/用法错。
**不静默通过**：缺 `paperkit.toml`、facts 为空、sections 为空、`refs.bib` 缺失
→ 退出码 2 并说清原因。

## 目录契约

```
<project>/
  paperkit.toml          # 项目声明（必需）
  facts/*.toml           # 事实账，只追加，一条一个 id
  results/               # 原始实验产物（只读，facts.source 指过来）
  sections/*.tex         # 正文（审计对象）
  refs.bib               # 参考文献，只放已核实条目
  audit/                 # 生成物（matrix.md 等，不入库）
```

```toml
[project]
title = "..."
authors = ["..."]
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
build = "tectonic main.tex"     # 留空＝跳过编译
```

```toml
[[fact]]
id = "A2"
claim = "开臂 resolved（16 题）"
value = "10/16"
source = "results/swb16.md"
locator = "§二 汇总表"
confidence = "high"             # high | med | low
derived_from = []               # 推算值就列依赖的 fact id
note = ""
```

## 数字怎么算「回到账上」

- **跳过**：`%` 注释、`\cite/\ref/\label/\input/\begin/\end/includegraphics/...`
  的参数、命令名里的数字（`\foo2`）、`\begin{tabular}{p{2cm}l}` 这种列格式；
- **归一化**：`1,234`＝`1234`、`0.90`＝`0.9`、`10\%`＝`10%`、`53k`＝`53000`、
  `3.5M`＝`3500000`；百分数按原值折半（`56.25%` 也接受裸 `56.25`）；
- **值可以是区间/分数**：`value = "10--16"` 接受两端；`value = "10/16"` 接受
  `10`、`16`、`0.625`（并按 0~4 位小数容忍四舍五入）；
- **显式绑定**：正文写 `\fact{A1}`（或 `[[fact:A1]]`）＝「这一行的数字属于 A1」。
  审计会反查：该行每个数字都必须真的在 A1 的 value 里，否则仍判红
  （`BOUND_MISMATCH`）。`\fact` 要在导言区自定义，例如：
  ```latex
  \newcommand{\fact}[1]{\textsuperscript{\textsf{\footnotesize[#1]}}}
  ```
- 未匹配一律报 `文件:行:列 | 数字 | 所在整行`，不许只说「有 3 处不匹配」。

## 引用怎么算「落到稳定标识」

- `\cite{a,b}` 的 key 必须在 `refs.bib`，否则 `MISSING_CITE`（红）；
- bib 每条必须有 `arxiv` 或 `doi` 字段，否则 `BIB_NO_STABLE_ID`（红）；
- `--resolve` 时查 arXiv API / doi.org（超时 5 秒）：网络失败 → `unverified`
  （只提示，不判红）；远端明确说不存在 → `UNRESOLVED_CITE`（红）。

## 非红提示

- `UNUSED_FACT`：账上有、文里没用（正文的 marker 才算「用」）；
- `UNUSED_BIB`：bib 里有、文里没引；
- `CITE_UNVERIFIED`：`--resolve` 没连上。

## 测试

```bash
python3 -m unittest discover -s tests -v     # 46 例，全离线，约 2 秒
```

`examples/minimal/` 是 SPEC §6 的验收样例：3 条 fact、2 节 tex，故意混入
**1 个编造数字**（`47.3 ms`）和 **1 个假引用**（`\cite{ghost2024}`）。
`audit` 必须恰好报这 2 处。

已知限制见 `IMPLEMENTATION.md`。
