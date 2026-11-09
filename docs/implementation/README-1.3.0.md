# README 1.3.0 实施记录（批 95）

日期：2026-11-10
范围：重写 `README.md` 与 `README.en.md`，版本升到 1.3.0，`scripts/check-readme.py` 改为调用 `style --doc`。

## 一、改动清单

| 文件 | 改动 |
|---|---|
| `README.md` | 按十节结构重写；命令表补齐 10 条；新增改动账、处方层、退出码 0–4、18 条文风判据与术语层读数 |
| `README.en.md` | 与中文同构重写，标题压到 8 词以内，所有数字取自实跑 |
| `factscribe/constants.py` | `VERSION = "1.3.0"` |
| `CHANGELOG.md` | 新增 `## [1.3.0] - 2026-11-10`，只记用户可见变化 |
| `scripts/check-readme.py` | 文风与标题检查委托给 `style --doc`；保留命令名、链接、测试数三项事实检查 |
| `docs/implementation/README-1.3.0.md` | 本实施记录（不随提交门禁入仓） |

## 二、事实来源（开工实跑）

```text
python3 -m factscribe --version      -> factscribe 1.2.0（升版前）
python3 -m factscribe --help         -> 10 个子命令
python3 -m factscribe prescribe --list -> 6 条处方
env PYTHONPATH=src python3 -m unittest discover -s tests -> Ran 538 tests, OK
```

命令清单：`check` `audit` `matrix` `build` `preamble` `verify-pdf` `style` `protect` `tide` `prescribe`。

术语表：`factscribe/terms/paper.tsv` 33 个 canonical、76 个表面形式；`factscribe/terms/workspace.tsv` 153 个 canonical、465 个表面形式。

## 三、两条 `style --doc` 的最终读数

### README.md

```text
阶段    : polished（建议不改，triggers=0，cv=0.68）
判断    : 仅 0 项指标触发（无），句长 CV=0.68 在健康区间 [0.45, 0.80]
[黄] 0 处——所有指标在阈值内。
文档模式：1 个文件（markdown）
退出码：0
```

### README.en.md

```text
阶段    : polished（建议不改，triggers=0，cv=0.53）
判断    : 仅 0 项指标触发（无），句长 CV=0.53 在健康区间 [0.45, 0.80]
[黄] 0 处——所有指标在阈值内。
文档模式：1 个文件（markdown）
退出码：0
```

18 项指标在两次运行中全部为 ok，包括 `RHYTHM_PLATEAU`、`COLLOQUIAL_TRIAD`、`TERM_FIRST_IN_HEADING`、`TERM_VARIANT`、`HEADING_ECHO`、`DASH_PARENTHETICAL`。

## 四、`check-readme.py` 的检查项

1. 调用 `python3 -m factscribe style --doc README.md README.en.md`，要求退出码 0；本脚本不再复制文风判据。
2. 对照 `factscribe --help`，确认 10 个命令真实存在。
3. 确认两份 README 都写齐 10 个命令。
4. 相对链接的目标文件必须存在。
5. README 写的测试数必须等于实跑数（中文 `538 例`、英文 `538 tests` 都识别）。

实跑输出：

```text
[文风与标题：交给 style --doc]
  ✓ style --doc 两份 README 均为 0 条
  ✓ 命令 check / audit / matrix / build / preamble
  ✓ 命令 verify-pdf / style / protect / tide / prescribe
[README.md]
  ✓ 十个命令已写齐（10 条）
  ✓ README.md 链接检查完成
[README.en.md]
  ✓ 十个命令已写齐（10 条）
  ✓ README.en.md 链接检查完成
  ✓ 测试数 538

结论：全过
```

## 五、门禁输出

```text
env PYTHONPATH=src python3 -m unittest discover -s tests
Ran 538 tests in 21.267s
OK
```

`./scripts/preflight-ci.sh`（干净克隆 + 3.10/3.11/3.12）：

```text
✓ pdftotext / pdfinfo 齐备
✓ 克隆到临时目录（HEAD 87857d3）
✓ Python 3.10：Ran 538 tests
✓ Python 3.11：Ran 538 tests
✓ Python 3.12：Ran 538 tests
✓ examples/minimal audit exit=1（红，符合预期）
本地等价 CI 全绿——可以推。
```

另跑 `./scripts/preflight-ci.sh --fast`，在含本批改动的工作区上同样三版本全绿。
