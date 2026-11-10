# 批 112 实施记录：标题末尾英文句点（HEADING_MALFORMED）

> 规范：`docs/design/SPEC-V3.0.md` §13.3。
> 只改 `factscribe style` 的 `HEADING_MALFORMED` 判定；未改其它判据与退出码
> （仍只出黄牌 exit 3，永不 exit 1）。

## 1. 缺陷

批 84 的规则本意是「标题不带句号」，但旧正则只收中文句号 `。`，
英文句点 `.` 不报。最小复现：

```latex
\paragraph{Generation systems.} 正文一句。
\section{Results.} 正文。
```

修复前 `style` 输出 `[]`。后果是 `paper-b` 英文稿里 5 个
`\paragraph{...}` 标题带句点被放过，中英两版标题不一致。

## 2. 改法

- 标题（`\section`/`\subsection`/`\subsubsection`/`\paragraph`/
  `\subparagraph` 与 Markdown `#`）末尾为 `.` → 报 `HEADING_MALFORMED`；
- 豁免常见缩写结尾：`al.`、`e.g.`、`i.e.`、`vs.`、`etc.`、`Fig.`、
  `Eq.`、`No.`、`cf.`、`Dr.`、`et al.`（大小写不敏感）；
- 豁免表进配置：`style-rules.toml` 顶层 `heading_period_exempt`，
  项目根同名文件可覆盖；
- 中文句号 `。` 与其它标点的既有判据逐字节不变。

## 3. 读数（修复后）

| 语料 | findings 合计 | `HEADING_MALFORMED` | 说明 |
|---|---|---|---|
| `../paper` | 17 | 17 | 英文稿的 `\paragraph{...}` 句点标题，修复前被整条漏报 |
| `../paper-zh` | 0 | 0 | 中文版回归不变 |
| `../paper-b` | 11 | 10 | 修复前 6 条（1 `HEADING_TOO_LONG`＋5 冒号）；新增 5 条英文句点 |
| `/tmp/pb/en` | 5 → 0 | 5 → 0 | 清理 5 个标题句点后回 0 |

注：任务书的验收预期写「`paper` 仍 0」，实测 `../paper` 是英文稿，
`04_mechanisms.tex` 有 17 个 `\paragraph{...}` 标题带英文句点；修复前为 0
正是因为本缺口把它们全部漏掉。修复后按新判据报 17 条，属规则本意的正确
读数，不是回归。`paper-zh` 仍为 0。

## 4. 清理与保护面（只在 /tmp 副本）

`/tmp/pb/en/sections/02_related.tex` 的 5 个标题只删末尾句点、不改词：

| 改前 | 改后 |
|---|---|
| `Generation systems.` | `Generation systems` |
| `Prose as a statistical object.` | `Prose as a statistical object` |
| `Provenance and reproducibility.` | `Provenance and reproducibility` |
| `Blind evaluation.` | `Blind evaluation` |
| `Position.` | `Position` |

复跑：

```
python3 -m factscribe style /tmp/pb/en --json          # 0 条
python3 -m factscribe protect --before ../paper-b --after /tmp/pb/en --allow-renames  # 红 0 黄 0，exit 0
python3 -m factscribe tide --before ../paper-b --after /tmp/pb/en --snapshot /tmp/pb/lib  # commit，exit 0
```

`tide` 首次复跑报 `hash_ok ✗`：`/tmp/pb/en/audit/` 里留着批 111 的事务账，
其「落」记录写的是上一轮改后状态（不是本轮改前 `paper-b`），账链与新事务
的改前目录对不上。该账在 /tmp 试车副本上，本轮以新事务重开账本后闭合
（涨 3、落 3、波及面 4、事件 7、快照已存）。

## 5. 测试

`tests/test_style_v4.py::TestHeadingMalformed` 新增 6 例：

- `\section{Results.}` / `\paragraph{Generation systems.}` → 报；
- `\paragraph{Related work}`、`\paragraph{et al.}`、`\section{Results}` → 不报；
- Markdown `## Results.` → 报；`## Results` → 不报。
