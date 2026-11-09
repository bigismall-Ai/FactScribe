# 术语归一化与同义词层实施记录（批 90 / 批 91）

> 规范：`docs/design/SPEC-TERMS.md`。
> 批 91 起词表分层（`paper.tsv` ＋ `workspace.tsv`）、`TERM_VARIANT` 换判据、
> `TERM_UNREGISTERED` 默认关闭并走 info 通道；细节见文末「批 91」。
> 只改 `factscribe style` 的比对入口；**未改 `audit` / `protect` 的判据与
> 退出码**。新判据全黄牌，退出码仍为 `0` / `3`；`TERM_UNREGISTERED`
> 只提示，单独出现时退码仍为 `0`。

## 1. 词表规模（批 90；批 91 已分层，见 §7）

- 来源：`../sia-harness/nomenclator/terms/*.yaml`（153 个词册文件）。
- 落位（批 91 起）：`factscribe/terms/workspace.tsv`，运行时不读 `sia-harness`。
- 本次导入实测：**153 个 canonical，465 个表面形式**（canonical 153 ＋
  `en` 字段 153 ＋ 中文别名 159）。
- 生成命令（可重跑，覆盖生成）：

```
env PYTHONPATH=src python3 scripts/import-terms.py
```

文件头注写明来源、生成命令与现算规模；规范与脚本不写死数字。

## 2. 归一化算法

1. **拉丁文**：NFKC → 小写 → 去首尾空白。
2. **中文**：不做分词，正文从左到右做**最长匹配**；同一位置多个候选取
   最长，命中后跳过整个区间。
3. **匹配键**：逐字符 NFKC + 小写后只保留字母、数字、CJK；标点、连字符、
   空白都不进键，因此全半角、标点、空格、连字符差异不参与匹配。
4. **拉丁词边界**：命中后回到原串检查前后字符，前后不得是拉丁字母/数字；
   `id` 不会命中 `did` 内部。中文表面形式不加词边界。
5. `TERM_VARIANT` 的「不同写法」按归一化匹配键计数：`Preregistration`、
   `PRE-REGISTRATION`、`ｐｒｅｒｅｇｉｓｔｒａｔｉｏｎ` 只有一种写法。
6. 白名单（`GLOSSARY.md` ＋ `term-allow.txt`）条目先归一化，再同时以
   匹配键与 canonical 入册。

解析顺序（批 91 修订）：`style-rules.toml` 的 `term_glossary` → 项目根
`glossary.tsv` → 仓内分层词表（`paper.tsv` ＋ `workspace.tsv`）。项目覆盖
只用于项目追加与测试，默认词表仍由本仓自持。

## 3. 三条判据（批 91 修订，以 §8 为准）

| 码 | 算法 | 计数 | 级别 |
|---|---|---|---|
| `TERM_VARIANT` | 单篇内同一 canonical 的不同表面形式数 ≥ `term_variant_min_forms`（默认 2）；报各写法与行号 | 参与，触发即退 3 | 黄 |
| `TERM_UNREGISTERED` | 标题 / 首句的「术语样」候选归一化后不在册（含多词无缝覆盖） | **不参与**；不进 `fired` / `summary.triggered`，单独出现退 0 | 提示 |
| `HEADING_ECHO` / `TERM_FIRST_IN_HEADING` | 先按 canonical 归一，再走原判据；同义词视同同词 | 同原规则 | 黄 |

实现：

- 新模块 `factscribe/terms.py`：TSV 装载、匹配键、trie 最长匹配、白名单归一；
- `factscribe/style.py`：`_glossary_for` / `_term_allowlist` / `_new_content_terms`
  / `_heading_echo` 改按 canonical；新增 `_term_variant_findings` 与
  `_unregistered_findings`；
- `style-rules.toml`：`term_variant_min_forms = 2`，项目覆盖键 `term_glossary`；
- 纯标准库；不改 `audit.py` / `protect.py`。

## 4. 测试

`tests/test_terms.py`：**27 例**（全离线）。覆盖：

- 中文同义归一、拉丁大小写/全半角/连字符、标点与空白不参与匹配；
- 最长匹配边界：`相关工作` 与 `相关工作里`、`机制` 与 `提示词对机制`；
- `TERM_VARIANT` 三写法正例、单写法负例、大小写差异负例、阈值可调、
  不跨文件；
- `TERM_UNREGISTERED` 标题/首句提示、退码仍 0、白名单归一后命中；
- `HEADING_ECHO` 换同义表述仍报、带新信息不报、垫话同义仍报；
- `TERM_FIRST_IN_HEADING` 同义定义视为已定义、未定义仍报、白名单别名命中；
- 导入脚本可重跑且覆盖生成。

全套测试：**443 例**（本批新增 `tests/test_terms.py` 27 例；验收时基线
含并行批 89b 的测试）。

## 5. 门禁

工作区（含并行批未提交改动）之外的干净基线验证：把本批文件复制到
`HEAD` 的独立 worktree，三个 CI Python 版本均为 `Ran 433 tests OK`。

提交后官方门禁（干净克隆只含已提交文件，HEAD `f4b3d9c`）：

```
env PYTHONPATH=src python3 -m unittest discover -s tests
Ran 443 tests ... OK
./scripts/preflight-ci.sh
步骤 3/4：Python 3.10 / 3.11 / 3.12 各 Ran 443 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

## 6. `HEADING_ECHO` 漏报修复前后对比

同一夹具（`预注册` 为 canonical，`事前登记` 为其同义词）：

```latex
\section{预注册}

事前登记。
```

| 版本 | `heading_echo` | findings | 说明 |
|---|---|---|---|
| 修复前（HEAD `4069ca9`） | `0` | `[]` | 字面比对把「事前登记」当新信息，**漏报复述** |
| 修复后（本批） | `1` | `HEADING_ECHO`（另 `TERM_VARIANT`：一篇两写法） | 同义词归一到同一 canonical，**仍判复述** |

同一机制修复 `TERM_FIRST_IN_HEADING` 的字面误报：

```latex
\section{预注册流程}

事前登记流程是在收集数据前固定假设与分析计划的做法。
```

| 版本 | `term_first_in_heading` | 说明 |
|---|---|---|
| 修复前 | `1` | 首句用了同义词，字面找不到标题词，**误报未定义** |
| 修复后 | `0` | 同义词命中同一 canonical，视为已定义 |

两处漏洞（`HEADING_ECHO` 漏报、`TERM_FIRST_IN_HEADING` 字面误报）均已修复。

---

# 批 91：词表分层与噪声治理

> 规范：`docs/design/SPEC-TERMS.md`。只改 `factscribe style` 的术语层；
> `audit` / `protect` 的判据与退出码未动。

## 7. 词表分层

批 90 直接拿 nomenclator 的 153 条**工作区流程词**当术语表，实测覆盖不到
论文，且流程词的宽松别名会制造误报。批 91 拆成两层：

| 层 | 文件 | 来源 | 用途 |
|---|---|---|---|
| 论文术语 | `factscribe/terms/paper.tsv` | `paper-zh/GLOSSARY.md`（英文 \| 中文 \| 备注） | 查词 ＋ `TERM_VARIANT` |
| 工作区流程词 | `factscribe/terms/workspace.tsv` | `sia-harness/nomenclator/terms/*.yaml` | 只查词，不参与 `TERM_VARIANT` |

- 合并查询：`paper.tsv` 在前、`workspace.tsv` 在后；同名表面形式以
  `paper.tsv` 为准（`Glossary` 的匹配键先到先得）。
- `paper.tsv` 第五列 `blocked(cn)` 是备注里「不写「X」「Y」」声明的
  **禁用变体**。禁用变体仍进匹配表（同义归一时视同正名），但
  `TERM_VARIANT` 单独按禁用变体报。
- 生成命令（可重跑；来源缺失时跳过并提示，退出码 0）：

```
env PYTHONPATH=src python3 scripts/import-glossary.py   # 论文术语
env PYTHONPATH=src python3 scripts/import-terms.py      # 工作区流程词
```

本次生成：`paper.tsv` **33 个 canonical**、`workspace.tsv` 153 个。
「指针／对象存储」这类并列概念按两条术语拆开，避免同一 canonical 的假变体；
「不用「解决」」是用法建议，不是「不写」声明，不进口术语层的禁用变体。

## 8. 三处改动

1. **`terms.py` 分层装载**：`Term` 增 `source` / `blocked`；`load_glossary()`
   默认合并 `paper.tsv` ＋ `workspace.tsv`；`parse_glossary` 读第五列
   `blocked(cn)`；新增 `paper_terms`。项目根 `glossary.tsv` 视为论文术语表。
2. **`TERM_VARIANT` 换判据**：只在 `paper.tsv` 条目上判；禁用变体出现即报
   （优先），否则同一 canonical 的中文表面形式 ≥ `term_variant_min_forms`。
   报出条目含「哪一行用了哪个变体、正名是什么」。英文列是译法，不按中文
   用词一致性计数。
3. **`TERM_UNREGISTERED` 降噪**：默认关闭（`style-rules.toml`
   `term_unregistered = false`），只由 `--report-unregistered` 打开；打开后
   只查标题、不查首句；候选收紧为 CJK 2–7 字（两侧标点/空白/边界、不与更长
   命中重叠、排除虚词边缘与句法助词）、拉丁 ≥2 词；结果单独走 `info` 通道，
   不进 `findings` 计数、不改变退出码。

## 9. 验收读数

```
python3 -m factscribe style ../paper --json
python3 -m factscribe style ../paper-zh --json
python3 -m factscribe style /tmp/v4-regen/en --diff ../paper --json
python3 -m factscribe style /tmp/v4-regen/zh --diff ../paper-zh --json
```

| 项目 | `TERM_UNREGISTERED` | `TERM_VARIANT` | 结论 |
|---|---|---|---|
| `../paper`（原文） | **0** | **0** | 默认关闭；无误报 |
| `../paper-zh`（原文） | **0** | **0** | 默认关闭；无误报 |
| `/tmp/v4-regen/en`（diff） | 0 | 0 | 6 条真实退步全保 |
| `/tmp/v4-regen/zh`（diff） | 0 | 0 | 6 条真实退步全保 |

6 条真实退步（EN-06、EN-10、ZH-04、ZH-06、ZH-08、ZH-09）在 diff 里一条
未丢：EN 的 `HEADING_ECHO`（07_threats:8）与 `HEADING_RELATION_CHANGED`
（04_mechanisms:96）；ZH 的 3 条 `HEADING_ECHO`（02_related:3、
04_mechanisms:53、07_threats:8）与 `HEADING_RELATION_CHANGED` /
`HEADING_SUBJECT_LOST`（04_mechanisms:39，ZH-04 同一处两项）。

## 10. 误报前后对比

| 现象 | 批 90（`HEAD c80eff1`） | 批 91 |
|---|---|---|
| 原文 `paper/` 的 `TERM_UNREGISTERED` | 指标 164（报告上限只显示 20 条），全为 `任务挑选用`、`好让时间线留档` 一类句子碎片 | **0**（默认关；打开只查标题、走 info） |
| 原文 `paper-zh/` 的 `TERM_VARIANT` | 4 条：`成本／预算`、`数据／日志`（nomenclator 宽松别名） | **0** |
| v4 改写件 `zh` 的 `TERM_VARIANT` | 1 条假变体：`成本：预算（第29行）、成本` | **0** |

`成本` 与 `预算` 现在仍在 `workspace.tsv` 里用于查词与同义归一，但因为
`workspace.tsv` 不参与 `TERM_VARIANT`，不再被报成「同一概念的两种写法」。
`预注册` / `事前登记` 这类论文术语由 `paper.tsv` 判定：只用正名不报；
禁用变体出现则报出变体行号与正名；`HEADING_ECHO` 的同义归一继续生效。

## 11. 测试与门禁

`tests/test_terms.py`：**42 例**（批 90 的 27 例 ＋ 批 91 新增 15 例）。
新增覆盖：

- `预注册` ＋ 禁用变体 `事前登记` → `TERM_VARIANT`，报出正名与行号；
- 只用正名不报；`成本` / `预算`（只在 `workspace.tsv`）不报；
- `TERM_UNREGISTERED` 默认不出、打开后只进 `info`、不改 findings 计数与退出码；
- 垃圾候选（`好让时间线留档`）不报，术语样标题（`剂量反应曲线`）才报；
- CJK 2–7 字、虚词边缘、长串、拉丁单字/多词边界；
- `paper.tsv` 禁用变体归一后，`HEADING_ECHO` 仍能抓「换同义词复述标题」；
- `import-glossary.py` 可重跑、解析 `不写「X」`、缺失来源跳过。

全量：`env PYTHONPATH=src python3 -m unittest discover -s tests` → **458 例 OK**。
