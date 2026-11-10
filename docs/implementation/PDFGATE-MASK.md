# PDFGATE-MASK｜结构性 token 白名单（批 121）

> 问题：P-05 的「PDF 数字多重集 ⊆ ledger ∪ 人签白名单」把排版器生成的
> 章节号、图表编号、文献年份、页码当成账外数字，真实论文必然满屏红。
>
> 口径：白名单**从源文件推导**，不从 PDF 文本反推；只放行结构形态，
> 不进 `number_ledger`，不影响 `check`。

## 1. 四类来源

| 类别 | 来源 | 计算 |
|---|---|---|
| 章节号 | `main.tex` + `\input/\include` 闭包（`config.load_sections`） | `texscan._document_texts()` 按编译序展开（父文件 `\input` 前后文本落在子文件两侧）；`section_number_tokens()` 按 LaTeX 规则推进 `section/subsection/subsubsection` 计数器。`\section*` 不编号也不推进；`\appendix` 之后的章节是字母，不产数字 token |
| 浮动体编号 | 同一闭包 | `float_number_tokens()` 统计 `figure`/`figure*`、`table`/`table*`、`equation`/`align`/`eqnarray`/`gather`/`multline`；取各类计数最大值产出 `1..N`。`equation*`/`align*` 不编号，不计数 |
| 年份 | `refs.bib`（含正文 `\bibliography/\addbibresource` 声明的多 bib） | `bib_year_tokens()` 抽每个 entry 的 `year` 字段（`(19|20)\d{2}`） |
| 页码 | 磁盘 PDF | `pdfgate` 用 `pdfinfo Pages`（`page_count`）补 `1..P`；不采信报告里的页数 |

V1 项目没有 `root_tex` 时，`audit` 若发现 `main.tex` 存在，会把它作为
**仅用于排序**的壳文件加进结构推导（不改审计闭包），以免按文件名把
`appendix/` 排到正文前面。

## 2. 判定

`pdfgate.verify_document()`：

```
allowed = ledger_counts + signed_pdf_whitelist_counts
for key, actual in pdf_counts:
    surplus = actual - allowed[key]
    if surplus <= 0: continue
    if key in structural_keys:      # sections / floats / years / pages
        structural_masked[key] += surplus
    else:
        PDF_UNACCOUNTED_NUMBER
```

- 只掩「盈余」：账上已授权的出现次数仍按 ledger 记账，不会把正文数字
  重复计成结构量。
- `PDF_LEDGER_TOKEN_MISSING` 用未减弱的总多重集判，结构白名单不参与。
- 输出：`summary.pdf.structural_masked`（总数）与
  `summary.pdf.structural_masked_by`（按类别）；`verify-pdf --json` 同样带
  `structural_masked` / `structural_masked_by`。人读报告加一行
  `pdf : …；结构性 token 掩掉 N 个（…）`。

## 3. 边界

- **同形风险**：结构量是裸数字形态（`2` 既是章节号也可能是正文计数）。
  当前按 token 放行，账上已有的明文不受影响；这属于有意的形态白名单，
  不是语义豁免。要收紧只能靠 ledger 覆盖正文数字，不能靠放宽相等判定。
- 章节号只认实际标题序列；PDF 里出现序列外的 `9.9` 仍红。
- 年份只认 bib 的 `year` 字段；bib 没有的年份仍红。
- 页码恒按实际页数，报告伪造页数不会扩大放行面。

## 4. 读数（批 121）

| 项目 | 修改前 `PDF_UNACCOUNTED_NUMBER` | 修改后 | 掩掉 token（章节/年份/页码） |
|---|---|---|---|
| `paper-b` | 41 | 0 | 56（35 / 17 / 4） |
| `paper-b-zh` | 45 | 0 | 83（55 / 17 / 11） |
| `paper`（回归） | 0 红 | 0 红 | 未启用（V1 无 PDF 回检） |
| `paper-zh`（回归） | 0 红 | 0 红 | 未启用（V1 无 PDF 回检） |

测试：`tests/test_pdfgate_masking.py` 21 例（源层 10 + PDF 10 + audit JSON 1）。
全量 `python3 -m unittest discover -s tests` → 879 tests OK。
