# BUILD-PDF — `build` 自动编译实测读数（批 120）

规范：`docs/design/SPEC-BUILD.md`。本文件只记实测数，不重复规范条文。

## 1. 环境

| 项 | 值 |
|---|---|
| 机器 | macOS（darwin），Python 3.14.4（门禁另跑 3.10/3.11/3.12） |
| 引擎 | `/opt/homebrew/bin/tectonic`，Tectonic 0.17.0 |
| 字体兜底 | `fc-match -f "%{file}" STHeiti` → `/System/Library/AssetsV2/com_apple_MobileAsset_Font8/53fe5be564086fefc7523ccd0a31200acf92e0e5.asset/AssetData/STHEITI.ttf` |
| 两个验收项目的 `project.build` | V3 扁平声明不含 `build`，配置层按空串处理 → 走自动路径 |

## 2. 两次真实 build

```
$ python3 -m factscribe build ../paper-b
== paperkit build ==
引擎：/opt/homebrew/bin/tectonic
尝试：1 次
产出：../paper-b/main.pdf（13 页，79370 字节）
exit 0
```

```
$ python3 -m factscribe build ../paper-b-zh
== paperkit build ==
引擎：/opt/homebrew/bin/tectonic
尝试：2 次
产出：../paper-b-zh/main.pdf（13 页，264525 字节）
exit 0
```

- 英文项目一次过（`mode=direct`）。
- 中文项目第一次命中
  `CTeX fontset 'fandol' could not be found` → 临时副本改 `fontset=none` +
  插 `\setCJKmainfont[Path=…/,BoldFont=STHEITI.ttf]{STHEITI.ttf}` → 第二次过
  （`mode=temp-cjk-font`）。字体行里 `Path` 必须以 `/` 结尾，否则 fontspec 会
  拼成 `…/AssetDataSTHEITI.ttf` 并报 `The font "STHEITI" cannot be found`
  （本批实测踩到一次，已修）。
- 页数由纯标准库 `pdf_page_count` 从 PDF 字节数出：tectonic 的输出是 PDF 1.5，
  页对象压在 FlateDecode 流里，明文搜不到 `/Type /Page`；实现改为先解压流再数
  （13 页与 `pdfinfo` 一致）。
- 项目目录只多出 `main.pdf`；`.aux/.log` 全在临时副本里，默认已清理。
  `--keep-temp` 会保留并打印路径，实测副本里能看到改过的 `main.tex`
  与未改的原 `main.tex` 两相对照。

PDF 确实被重写了（重编前 → 重编后）：

| 项目 | 重编前 | 重编后 |
|---|---|---|
| paper-b | 79472 字节（11-09） | 79370 字节（本批） |
| paper-b-zh | 298995 字节（11-09） | 264525 字节（本批） |

## 3. 两次 audit 读数

```
$ python3 -m factscribe audit ../paper-b
facts   : 62 条      sections: 10 个（扫描 10 个 .tex）
numbers : 191 个（bound 191 / unbound 0 / unmatched 0）
[黄] 0 处
[红] 41 处（必须修）
exit 5

$ python3 -m factscribe audit ../paper-b-zh
facts   : 62 条      sections: 10 个（扫描 10 个 .tex）
numbers : 194 个（bound 194 / unbound 0 / unmatched 0）
[黄] 0 处
[红] 45 处（必须修）
exit 5
```

**红没有消失。** 41/45 条全部是 `PDF_UNACCOUNTED_NUMBER`，且重编前后红数
完全一样（重编前也各是 41 / 45）。所以这些红**不是 PDF 过期**造成的，重编
解决不了；逐类原因如下（`paper-b` 计数，`paper-b-zh` 同构）：

| 类 | 条数（b / zh） | 例子 key | 原因 |
|---|---|---|---|
| 章节号 | 33 / 34 | `3.1`…`6.4`、`1`、`7` | `article` 把 `\section` 排成行首「数字␣␣标题」（`3.1   Three Read-Only Inputs`）。`pdfgate` 的 W4 结构号掩码 `_STRUCT_LINE_RE` 只认 `^\s*(\d+)[.)]\s`——要求数字后跟点/括号，不认这种版式；`.tex` 侧没有这些数字（章节号是排版生成的），账本自然没有。 |
| 作者-年份引用 | 5 / 5 | `2018`、`2023`…`2026` | W3 只掩 `[12]` 这种纯数字引用标签；本项目用 `[Kobak et al., 2025]` / `Kobak et al., 2025` 的 author-year 形式，年份原样落进 PDF 数字流。文献表的年份走 W2 白名单，但白名单对同一 key 最多放 3 次，实际条目更多。 |
| 日期/卷期数 | 3 / 6 | `9`、`10`、`11`（zh 还有 `8`、`12`、`13`） | ISO 日期 `accessed 2026-11-09`、标题日期 `November 10, 2026`、文献的 `115(11)` 被 PDF 数字扫描拆成裸数字；账本里没有对应 token。 |

这四类都是 **PDF 回检闸的上下文掩码缺口**（W1/W3/W4 + W2 上限），属于
`pdfgate` 的另行一批；批 120 的交付边界是「build 能把 PDF 编出来并写回」，
不含改判据。

## 4. 测试

- 新增 `tests/test_build_pdf.py`：20 例，全离线（假 tectonic 脚本模拟
  成功 / `fontset` 报错后成功 / 硬失败 / 引擎缺失），覆盖：
  - 非空 `project.build` 原行为不变（不走引擎，引擎缺失也不影响）；
  - 自动路径成功、PDF 页数/字节数、`--json` 字段、临时目录默认清理与
    `--keep-temp` 保留；
  - 源 `main.tex` 构建前后逐字节一致、项目里不落 `.aux/.log`；
  - `fontset` 失败触发临时副本改造后重试、项目内 `.tex` 不被改、
    `--cjk-font` 生效；
  - `main.tex` 缺失 exit 2、引擎缺失 exit 8（`PDF_TOOL_MISSING`）、
    编译失败 exit 4 且只留末 20 行；
  - `pdf_page_count` 明文 / FlateDecode 流 / 非 PDF，`rewrite_cjk_font`
    插入位置与缺 `\documentclass` 的报错。
- 原有 `test_build_empty_skips` 按新契约改为
  `test_build_empty_without_tex_is_config_error`（空 build + 无 `main.tex`
  → exit 2，不再静默跳过）。
- 全量：`Ran 858 tests ... OK`（0 失败）。
