# paperkit MVP 实现记录

> **v1 见 `IMPLEMENTATION-V1.md`。** 本件是 v0/MVP 的历史记录，
> 其中「值级匹配」「46 例」「source 只验存在」等口径已被 v1 取代。

日期：2026-11-07　　实现者：paperkit contributors
规格：`SPEC.md`（v0）；本件只记「做了什么、跑了什么、哪里还不行」。

## 0. 交付清单

```
paperkit-dev/
  paperkit.py               # 单文件 CLI，纯标准库（~1000 行）
  tests/test_paperkit.py    # 46 例 unittest，全离线
  examples/minimal/         # SPEC §6 验收样例（3 facts + 2 节 tex + 1 编造数字 + 1 假引用）
  README.md
  IMPLEMENTATION.md
  .gitignore
```

四个命令全部实现并跑通：`check` / `audit` / `matrix` / `build`，都支持 `--json`。

## 1. 命令示例

```bash
cd paperkit-dev

python3 paperkit.py check  examples/minimal          # 账本身
python3 paperkit.py audit  examples/minimal          # 核心闸门
python3 paperkit.py audit  examples/minimal --json   # 给 agent
python3 paperkit.py audit  examples/minimal --resolve # 再联网核 arXiv/DOI（可选）
python3 paperkit.py matrix examples/minimal          # 写 audit/matrix.md
python3 paperkit.py build  examples/minimal          # 跑 project.build
```

退出码：`0` 无红 / `1` 有红（或 build 失败）/ `2` 配置或用法错。

## 2. 验收输出原文

### 2.1 `check` —— 绿，退出码 0

```
== paperkit check ==
project : examples/minimal
facts   : 3 条（id 3 个，source 均在位 3 条）

[红] 0 处 —— 账本身干净

[冲突] 0 组

结论：绿（退出码 0）
```

### 2.2 `audit` —— **恰好 2 处红**，退出码 1

```
== paperkit audit ==
project : examples/minimal
facts   : 3 条      sections: 2 个
numbers : 10 个（matched 5 / bound 4 / unmatched 1）
cites   : 2 次调用、2 个 key；bib 2 条（命中 1）

[红] 2 处（必须修）
  1. UNMATCHED_NUMBER   sections/02-results.tex:17:17  →  47.3
     数字 47.3 回不到任何 fact.value
     行: 上一轮离线复跑把端到端时延压到 47.3\,ms，这个数字还没有进事实账，
  2. MISSING_CITE       sections/02-results.tex:19:14  →  ghost2024
     引用了 bib 里不存在的 key 'ghost2024'
     行: 相关工作另见 \cite{ghost2024}，这是一条不存在的条目。

[提示] 1 条（非红，不拦）
 - UNUSED_BIB       refs.bib:11 bib 里有、文里没引：'lewis2020rag'

结论：2 处红（退出码 1）
```

对照 SPEC §6：编造数字 = `47.3 ms`（第 17 行）、假引用 = `\cite{ghost2024}`（第 19 行），
**两条报出、一条不多**。注释里的假数字（`99.9\%`，intro 第 2 行）被正确跳过；
`\begin{tabular}{lcc}`、`\cite{...}` 参数里的字符没被误判成数字。

`--resolve` 实跑（联网，代理 `127.0.0.1:7897`）：

```
联网核验：
 - chen2023factscore  doi=10.18653/v1/2023.emnlp-main.741 -> verified（doi.org handle 命中）

结论：2 处红（退出码 1）
```

联网核验既没多报也没少报（没连上时降级 `unverified` 只提示）。

### 2.3 `matrix` —— 3 行，退出码 0

```
== paperkit matrix ==
写盘：examples/minimal/audit/matrix.md
行数：3（每行一条 fact）
# Fact 追溯矩阵

- 项目：paperkit 最小验收样例
- 生成：paperkit 0.1.0-mvp
- facts：3 条；sections：2 个

| fact id | claim | value | source | locator | confidence | 被引用次数 | 被哪些节引用 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | 开臂 resolved（16 题） | 10/16 | results/swb16.md | §二 汇总表 open 行 | high | 1 | sections/01-intro.tex |
| A3 | 对比臂 resolved（16 题） | 8/16 | results/swb16.md | §二 汇总表 closed 行 | high | 1 | sections/01-intro.tex |
| A2 | 两臂合计准确率 | 56.25% | results/swb16.md | §三 平均行 | med | 1 | sections/01-intro.tex |

## 提示

- 账上有、文里没用：无
- 正文引用只在 marker（`\fact{A1}` 或 `[[fact:A1]]`）里计数。
```

### 2.4 `build` —— 出 PDF，退出码 0

```
$ tectonic -X compile main.tex
note: Writing `main.pdf` (42.7177734375 KiB)
构建成功：退出码 0
```

`examples/minimal/main.pdf` 实存 43 KB（首次编译要联网下 bundle，约 1 分半；
本机 `export HTTPS_PROXY=http://127.0.0.1:7897`）。

## 3. 测试结果

```bash
$ python3 -m unittest discover -s tests
..............................................
----------------------------------------------------------------------
Ran 46 tests in 2.083s

OK
```

全离线。覆盖：

| 组 | 例数 | 覆盖点 |
|---|---|---|
| 数字归一化 | 7 | `1,234` / `0.90` / `10%` / `53k` / `3.5M` / 分数 / 区间 |
| tex 掩码 | 8 | 注释、`\cite\ref\label\input` 参数、命令名数字、tabular 列格式、`\fact` / `[[fact:]]` 绑定、`\%` 不是注释 |
| check | 7 | 干净、重复 id、source 缺失、confidence 非法、derived_from 悬空、冲突单列、supersedes 封冲突 |
| audit | 9 | 干净、未匹配带 文件:行:列+整行、百分比/分数/千分位/k/M、绑定成功、绑定不符判红、未知 marker、假引用、bib 无稳定标识、未用 fact 只提示、resolve 降级 |
| 不静默通过 | 5 | 缺配置、facts 空、sections 空、bib 缺、缺 project 键（均退出码 2） |
| matrix | 1 | 3 行、被引用次数、分节归属 |
| build | 3 | 跑命令、失败非零、留空跳过 |
| 验收样例 | 3 | check 绿 / audit 恰好 2 红且码序正确 / matrix 3 行 |

## 4. 关键实现取舍

1. **两遍掩码、长度不变**：第一遍把注释与转义原地抹成空格（保留换行），第二遍
   抹命令名与结构参数。因为全程不做字符串拼接、偏移不变，所以 `文件:行:列`
   是真的行列号，可以直接给人看。
2. **跳过清单是白名单** `_SKIP_ARGS`：`cite* / ref* / label / input / include /
   includegraphics / begin / end / bibitem / documentclass / usepackage / url /
   href / setlength / setcounter / multicolumn / resizebox ...`，其中
   `begin`/`end` 吞两个参数（`{tabular}` + `{p{2cm}l}`），`href`/`multicolumn`
   吞两个。命令名整体吞掉，于是 `\foo2` 里的 `2` 不算数字。
3. **归一化到 Decimal 规范串**：量级后缀紧贴数字才生效（`47.3 ms` 不会被读成
   毫），百分号允许有空格（`10 \%` 掩码后就是 `10 %`）；账目层的 `value`
   同时登记「字面数字」和「分数之商」两套键。
4. **绑定语义**：`\fact{A1}` 是「这一行的数字整体归属于 A1」，审计反查该行
   每个数字都在 A1 的 value 里；不在就红（`BOUND_MISMATCH`）。这样「绑定」
   不是免检牌，而是更严的检查。
5. **红/提示分栏**：未用 fact、未用 bib、resolve 连不上都只进提示，不进退出码；
   冲突在 `check` 里单列（SPEC 明说不是错）。

## 5. 已知限制（按重要性排）

1. **数字是词法级「回得到账」，不是「回到对的那条账」**。只要 `10` 出现在
   任何一条 fact.value 里就算过；同一数字被两条 fact 共用时 audit 无法判断
   正文指的是哪一条（此时应写 `\fact{}` 绑定）。这是 MVP 刻意的低门槛。
2. **四舍五入容忍是刻意放宽的**：`1/3` 的账接受 `0.33`/`0.333`…（0~4 位小数），
   一条被截断过的数可能因此混过。
3. **裸 `%` 在 TeX 里是注释起点**：正文写 `10%` 会把后半行吞成注释，只有数字
   活下来（`10` 仍能与 `value = "10%"` 匹配，因为账目层登记了裸数字）。
   要保百分比语义请写 `10\%`。
4. **不做 LaTeX 语义解析**：不展开宏、不进 `\input` 递归（只审 glob 命中的
   `sections/*.tex`）、不区分数学/正文。白名单外的可选参数（如 `\footnote[3]`）
   里的数字会被计入；遇到就加进 `_SKIP_ARGS`。
5. **表格/公式没有豁免**：表格里的纯排版数字（列宽、字号）也会被审计，要么
   走白名单，要么在正文里用 `\fact{}` 说清归属。
6. **「用没用」只认 marker**：只有 `\fact{A1}` / `[[fact:A1]]` 算使用；只靠数字
   命中的 fact 会报 `UNUSED_FACT`（假阳性提示，不判红，不改退出码）。
7. **bib 解析是手写正则**：覆盖常见 `@type{key, field = {..}}`；`@string` 宏、
   `#` 拼接、`month = jan` 这类宏不解析（本工具只要 `arxiv`/`doi` 字段）。
8. **`--resolve` 是真联网**：无网/超时 5 秒降级 `unverified`。离线时假引用只能
   靠「bib 里没有这个 key」拦，不能靠「arXiv 上不存在」拦。
9. **`build` 用 `shell=True` 原样执行 `project.build`**，不做沙箱——契约上只该
   写编译命令。
10. **Python 3.10 没有 `tomllib`**，内置 `_mini_toml` 只支持本契约用到的子集
    （`[table]`、`[[array of tables]]`、字符串、数组、数字、布尔）；复杂 TOML
    请用 3.11+。
11. 只认 UTF-8；`col` 是**字符**列（CJK 正文里不是字节列）。
12. 未实现 SPEC 之外的东西：不生成正文、不生成 bib 条目、不查重、不排版美化。

## 6. 与 SPEC 的偏差

无功能偏差。两处补齐说明：

- SPEC §2 写正文用 `[[fact:A2]]` 或 `{A2}` 引用；实现采用 `\fact{A2}`（任务书
  指定）+ `[[fact:A2]]` 两种，**没有**支持裸 `{A2}`——它和普通 LaTeX 分组无法
  区分，误判风险大于收益。
- SPEC §3 的「事实使用率」实现为 `matrix` 的「被引用次数」列 + `audit` 的
  `UNUSED_FACT` 提示，两处同一口径（只认 marker）。
