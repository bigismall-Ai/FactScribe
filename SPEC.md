# paperkit-dev — 规格（v0，待红蓝对抗）

> **已被 `SPEC-V1.md` 取代（2026-11-07）。** 本件保留为红队攻击对象与历史稿；
> 现行契约与 29 条裁决见 `SPEC-V1.md`，实现记录见 `IMPLEMENTATION-V1.md`。

一个**独立**的论文生产工具：给 agent（或人）写 LaTeX 论文，但**不允许它编数字、编引用**。
不依赖 sia-harness，不依赖任何模型 SDK。

## 1. 要解决的问题

LLM 写论文的通病不是文笔，是**两处不可复核的编造**：

1. **数字**：正文里出现一个数，没人知道它从哪来；
2. **引用**：`\cite{...}` 指向一篇不存在的论文。

本工具把这两件事变成**机械闸门**：数字必须能回到事实账，引用必须能解析到稳定标识。

## 2. 目录与契约

```
<project>/
  paperkit.toml          # 项目声明
  facts/*.toml           # 事实账（只追加；一条一个 id）
  results/               # 原始实验产物（只读，不复制；路径进 facts.source）
  sections/*.tex         # 正文（人或 agent 写）
  refs.bib               # 参考文献（只放已核实条目）
  audit/                 # 生成物（不入库）
```

`paperkit.toml`：

```toml
[project]
title = "..."
authors = ["..."]
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
build = "tectonic main.tex"     # 或留空跳过编译
```

`facts/*.toml`（**只追加**，改事实必须新增一条并标 `supersedes`）：

```toml
[[fact]]
id = "A2"                       # 唯一；正文用 [[fact:A2]] 或 {A2} 引用
claim = "开臂 resolved（16 题）"
value = "10/16"
source = "experiments/demo/BATCH23-SWB16.md"
locator = "§二 汇总表"
confidence = "high"             # high | med | low
derived_from = []               # 若是推算值，列依赖的 fact id
note = ""
```

## 3. 三条命令（MVP）

### `paperkit check`
- 每个 fact：`id` 唯一、`source` 文件存在、`confidence` 合法、`derived_from` 指向存在的 id；
- 冲突检测：同 `claim` 不同 `value` 且都没 `supersedes` → 报**冲突**（不是错，但必须列出）。

### `paperkit audit`（核心）
对 `sections/*.tex`：

1. **数字对账**：抽出所有数字（跳过注释、命令名、`\cite`/`\ref`/`\label` 参数），逐个到 facts 的 `value` 里找；
   - 找不到 → `UNMATCHED`（红）；
   - 归一化：`1,234`＝`1234`、`0.9`＝`0.90`、`10%`＝`10\%`、`53k`＝`53000`；
   - 每个未被匹配的数字必须出报告（文件:行:上下文）。
2. **引用对账**：`\cite{a,b}` 的 key 必须在 `refs.bib`；`refs.bib` 每条必须有 `arxiv` 或 `doi` 字段；
   - 有 `--resolve` 时联网核验 arXiv ID 存在（超时/无网则标 `unverified`，不判红）。
3. **事实使用率**：列出从未被正文引用的 fact（不是错，但提示“账上有、文里没用”）。

退出码：0＝无红；1＝有红；2＝用法/配置错。

### `paperkit matrix`
生成 `audit/matrix.md`：`fact id | claim | value | source | locator | 被哪些节引用`。
这是给审稿人/复现用的追溯面，也是“银标”抽查面。

### `paperkit build`
执行 `project.build`；失败即非零退出。

## 4. 非目标（写清楚，避免跑偏）

- 不生成正文（那是 agent 的事）；
- 不生成参考文献内容（只核验，不编造）；
- 不做查重、不做排版美化；
- 不绑定任何模型或供应商。

## 5. 硬性要求

- 纯标准库（Python ≥3.10）；`--resolve` 之外不联网；
- 所有输出同时支持 `--json`（给 agent 用）与人读文本；
- 任何“未匹配”必须给出**文件:行:上下文**，不许只说“有 3 处不匹配”；
- 不静默通过：配置缺失、facts 为空、sections 为空 → 非零退出并说明。

## 6. 验收（MVP 完成判据）

1. 造一个 3 facts ＋ 2 节 tex 的最小项目：其中**故意混入 1 个编造数字和 1 个不存在的引用**；
2. `check` 绿；`audit` 必须**恰好**报出那 2 处（不多不少）；`matrix` 生成且含 3 行；
3. `build` 能在装了 tectonic 的机器上出 PDF；
4. 全部测试用 `python3 -m unittest` 可跑，不依赖网络。
