# README 全量对表重写 实施记录（P-139 收口）

日期：2026-11-18
范围：重写 `README.md` 与 `README.en.md`（任务＝文档，零功能代码改动），`docs/WHAT-IT-PROVES.md` 安全边界一节补一行，扩充 `scripts/check-readme.py` 的防再犯绊线。版本号不动。

## 一、改动清单

| 文件 | 改动 |
|---|---|
| `README.md` | 全量重写：身份与安全边界、零依赖身份、五分钟上手、二十七命令按流程分七组、四件新功能各一段小例、退出码补 8、测试数改实测 |
| `README.en.md` | 与中文同构重写 |
| `docs/WHAT-IT-PROVES.md` | 安全边界一节补一行：`refs search` 的联网范围 |
| `scripts/check-readme.py` | 新增两项绊线：命令表与 `--help` 双向对表、联网边界声明行存在性 |
| `CHANGELOG.md` | `## [Unreleased]` 下新增 `### Docs` 三条 |
| `docs/implementation/README-P139.md` | 本实施记录 |

## 二、事实来源（开工实跑）

```text
python3 -m factscribe --help          -> 27 个子命令
python3 -m factscribe prescribe --list -> 13 条处方
factscribe/terms/paper.tsv             -> 33 个 canonical
factscribe/terms/workspace.tsv         -> 153 个 canonical
python3 -m unittest discover -s tests  -> Ran 1595 tests, OK
同一条命令、PATH 里遮掉 poppler        -> Ran 1595 tests, OK (skipped=36)
```

零依赖身份的两处外部件与各自的降级口，取自 `factscribe/constants.py`（`EXIT_MISSING = 8`）、`factscribe/buildpdf.py`（缺引擎 → `PDF_TOOL_MISSING`，exit 8）、`factscribe/pdfgate.py`（缺 poppler → `PDF_TOOL_MISSING`，exit 8，不静默放行）与 `factscribe/doctor.py`（逐项给修复命令）。

联网面的实测口径：`factscribe/audit.py`（`--resolve` 发 arXiv/DOI 编号）、`factscribe/refs.py`（`search` 只发查询词）、`factscribe/fonts.py`（`--fetch` 下字体包）——全仓只有这三处 `urllib.request`。所以 README 的口径是「`refs search` 是唯一**默认**联网的命令」，另两处是显式开关，README 与 `WHAT-IT-PROVES.md` 都照此写。

## 三、两份 README 的命令分组清单

| 组 | 命令 |
|---|---|
| 上手 | `init` `doctor` `fonts` |
| 写作 | `preamble` `brief` `prescribe` `terms` `evidence` |
| 对账闸 | `check` `audit` `matrix` `fact` `report` `verify-pdf` `mirror-check` |
| 改稿 | `protect` `style` `tide` `review` `polish` |
| 交付 | `build` `figures` `bundle` |
| 接口 | `serve` `mcp` `web` |
| 文献 | `refs` |

合计 27 条，与 `factscribe --help` 的子命令集逐条对上。

## 四、绊线扩充

`scripts/check-readme.py` 新增两项（既有五项检查不动）：

1. **双向对表**：既有项是「`--help` 的子命令必须一条不落写进 README」。新增项反向再查一遍：README 命令表里写了、而 `--help` 里没有的命令名，红。命令表行的取法是「第一格整格就是一个反引号包住的命令名」（可带子动作，如 `fact import`，取第一个词做主命令）；表头行、分隔行、格里的路径与句子都不算。
2. **联网边界声明行存在性**：两份 README 必须各有一行同时点到 `refs search`、唯一、联网（中英文各认一套关键词：`唯一|only` 与 `联网|network`）。删掉那一行即红。

两项都只读文件，零网络，零依赖。

### 反例演练（演完恢复）

| 演练 | 手法 | 期望 | 实测 |
|---|---|---|---|
| 删一行命令 | 从 `README.md` 删掉 `matrix` 那一行 | 红 | 红（`命令未写入：matrix`），退出码 1 |
| 多写一个命令 | 在 `README.en.md` 的命令表里加一行 `notacommand` | 红（反向对表） | 红（`命令表多写了 --help 里没有的命令：notacommand`），退出码 1 |
| 删声明行 | 从 `README.md` 删掉「唯一联网命令」那一行 | 红 | 红（`缺「唯一联网命令」声明行`），退出码 1 |

三次演练结束后原文件都已还原（`git diff` 只剩本轮该有的改动）。

## 五、门禁输出

```text
$ python3 scripts/check-readme.py
[文风与标题：交给 style --doc]
  ✓ style --doc 两份 README 均为 0 条
  ✓ --help 里有 27 个子命令
[README.md]
  ✓ 命令已写齐（27 条）
  ✓ 命令表无多余命令（27 条）
  ✓ 「唯一联网命令」声明行在位
  ✓ README.md 链接检查完成
[README.en.md]
  ✓ 命令已写齐（27 条）
  ✓ 命令表无多余命令（27 条）
  ✓ 「唯一联网命令」声明行在位
  ✓ README.en.md 链接检查完成
  ✓ 测试数 1595

结论：全过
```

两份 README 的 `style --doc` 读数：阶段 `polished`（建议不改），指标触发 0 条，退出码 0。中途一次 `SECTION_OVERLAP` 黄牌（英文 README 的「Known gaps」尾段与「Identity and safety boundary」段撞了同一句承诺，已改写措辞），改后复跑归零。
