# 已有论文怎么接进来

一句话：**这是迁移，不是安装。** [QUICKSTART](QUICKSTART.md) 那条五分钟路径适用于新项目；
已经写完的论文，要先补账、补签、补引用标识，工作量取决于原始数据还在不在。

## 先看实测，再决定要不要迁

拿两篇 arXiv 原文（只读接入，原文件不动）跑第一次 `audit`：

| 论文 | .tex | 数字 | 引用 | 首次读数 |
|---|---|---|---|---|
| Attention Is All You Need（1706.03762） | 10 | 301 | 76 次 / 40 个 key（写在正文 `thebibliography` 里） | **399 红 / 11 黄**，0.26 秒 |
| LoRA（2106.09685） | 3 | 1277 | 两个 `.bib`，92 条没有 doi/arxiv | **1479 红 / 19 黄** |

红的构成很集中：

| 来源 | Attention | LoRA |
|---|---|---|
| 表格 cell（`TABLE_UNBOUND`） | 183 | 1011 |
| 正文数字（`UNMATCHED_NUMBER`） | 118 | 266 |
| 引用（`MISSING_CITE` / `BIB_NO_STABLE_ID`） | 76 | 92 |

**这不是工具坏了，是它按设计拒收「没有根的稿子」。** 它只能证明「数字能回到一份你签过的原始材料」；
如果原始材料已经没了，迁移到绿是不可能的。

## 什么情况值得迁

| 情况 | 建议 |
|---|---|
| 原始数据还在（日志、CSV、统计输出），表格能重新生成 | 可迁，按节推进 |
| 还要继续改这篇论文 | 可迁；迁一次，后面的改动都受保护 |
| 只剩 PDF / Word / 别人的稿子 | **不迁**；新论文从 `init` 开始 |
| 只有一节要改 | 只把这一节纳入审计，别碰全文 |

## 接入顺序（手动，六步）

**1. 备份。** `init --force` 会覆盖它自己那 7 个同名文件；真实论文里常见冲突是 `README.md`、
`refs.bib`、`main.tex`。先复制一份。

**2. 补配置文件。**

```bash
python3 -m factscribe init <项目> --force
```

**3. 清理占位文件。** 删掉 init 生成的 `main.tex` 和 `sections/01-intro.tex`——你的论文有自己的主文件，
留着它们会被当成正文扫进去。

**4. 改 `paperkit.toml`。**

```toml
[project]
title = "你的标题"
sections = "*.tex"          # 根目录；只改一节时用 "sections/05*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
build = ""
manifest = "results/MANIFEST.toml"
```

配置里的 `bib` 必须存在（`init` 会给一个空 `refs.bib`）。正文 `\bibliography{a,b}` 声明到的其他 `.bib`
会自动加入，**不用先合并**；只有配置与正文都没声明、却想额外加一本时，才需要显式处理。

`sections` 写 glob（例 `"*.tex"`）或单个文件（例 `"ms.tex"`）都行；单文件也按 v1 处理，
`fact add` 可用。只有同时出现 `output` / `level` 等 V3 标记字段时，才会按 V3 解析。

**5. 补引用标识。** 两种常见情况：

- 文献写在 `\begin{thebibliography}` 里：工具只认 `refs.bib`，要先把条目导出成 BibTeX；
- `.bib` 里只有 `url` / `journal = {arXiv:...}`：补 `arxiv` 或 `doi` 字段（`@misc` 可用 `url`）。

**6. 跑 `audit`，按 [TRIAGE](TRIAGE.md) 的顺序修**：账 → 签 → 引用 → 正文数字 → 表格 → 文风。

## 表格是最大的一堵墙

一篇实验论文的多数数字在表里（LoRA 实测 1011 格）。工具要求表格满足三者之一：

1. **生成式**（推荐）：表头写 `% paperkit:generated spec=tables/t1.spec.json`，审计用同一渲染器
   从账重算每格；
2. **映射式**：`% paperkit:table-map {"12":{"on":"A2"}}`（行号 → 列 → fact）；
3. **内联式**：单元格写 `91.4\fact{A2}`。

没有映射就是 `TABLE_UNBOUND`。逐格手写不现实，**能迁的前提是表格能从账重新生成**。

## 现实做法：只迁正在改的那一节

```toml
sections = "sections/05*.tex"
```

只审计这一节，其他节不进来。改完再扩大范围。

实测（Attention 论文只圈 `introduction.tex`）：读数从 399 红降到 **15 红 / 11 黄**，
其中 13 条是引用、9 条是「其余 .tex 未纳入」的黄牌，正文数字为 0。

**说清楚边界**：这是工作单，不是证书。没纳入的文件不在覆盖内，不能拿这一节的绿灯去证明全文。

## 判断标准

问自己一句：**这些数字的原始出处还在我手上吗？**

- 在 → 值得迁，按节推进；
- 不在 → 不迁；把闸门用在下一篇，从第一天就记账。
