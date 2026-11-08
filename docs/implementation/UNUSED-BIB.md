# UNUSED-BIB｜批 60：`UNUSED_BIB` 从「提示」转「黄」

> 日期：2026-11-08
> 输入：真盲测 #7 首跑 **11/12**；唯一漏判 `cite-unused-bib`（`refs.bib` 有条目、
> 正文从未 `\cite`，工具只记 info 提示、exit 0）。
> 交付：`UNUSED_BIB` 判黄（exit 3）；`\nocite{*}` / `\nocite{key}` /
> `bib_allow_unused` 三条窄豁免；SPEC §8 码表与 §10 字段表同步；10 例新单测。

## 0. 结论（先看这里）

| 指标 | 改前 | 改后 |
|---|---|---|
| 盲测 #7 `cite-unused-bib` | 提示（exit 0，漏判） | **`UNUSED_BIB` 黄，exit 3** |
| 单测 | 203 全绿 | **213 全绿**（203 + 10 新） |
| 回归夹具 `fixtures/regression/paper-en` | 0 红 / 1 黄 / 234 绑定 | **0 红 / 1 黄（不变）/ 234 绑定** |
| 该夹具 `bib_unused` | —（原来只有 info 提示） | **`[]`**（11 条参考文献全部被引用） |

复现：

```bash
cd /Users/moc/workspaces/SiAgent/paperkit-dev
python3 -m unittest discover -s tests          # 213 例
python3 -m unittest discover -s tests -p "test_unused_bib.py"   # 10 例
python3 -m factscribe audit fixtures/regression/paper-en --json # 0 红；bib_unused=[]
```

## 1. 判据（R-11）

**定义**：`bib` 文件（`project.bib` ＋ 正文 `\bibliography{}`/`\addbibresource{}`
声明的文件）里存在条目 `key`，而**审计闭包内**（所有被扫描的 `.tex`）从未出现
`\cite*` 家族对它的引用 → 每个未引用条目各报一条 `UNUSED_BIB`：

- `severity = yellow`，`exit = 3`（有红时按红优先，不改变既有红项退出码）；
- `location = <bib 文件>:<行>`；`token = <key>`；`message` 内含具体 key
  与两条修法（白名单或 `\nocite{key}`）；
- `--json.summary.bib_unused = [key, ...]`：机器可读的未引用清单，
  `report` 人读面的 `[黄]` 列表逐条列出 key（不是只报数量）。

判据落在 `factscribe/citations.py::unused_bib_entries()`（纯判定）＋
`factscribe/audit.py::run_audit()`（出码）；扫描面在
`factscribe/texscan.py`（`ScanResult.nocite_all`）。

## 2. 三条豁免（窄，写死）

1. **`\nocite{*}`**：整库引用，所有条目都算被引用（`ScanResult.nocite_all`）。
   `\nocite{ * }` 这类空白写法同样命中。
2. **`\nocite{key}`**：逐条引用；`key` 已由扫描器记入 `used_keys`，该条不算未用。
3. **`bib_allow_unused = ["key", ...]`**（人签白名单，SPEC §10 字段表）：
   列出的 key 不算未用；**大小写不敏感**，v1 与 V3 声明都认。
   用途＝正文确实没提、但作者要保留的参考（模板自带条目、复现清单等）。

三条豁免都是「显式声明」而非启发式推断：没有「看起来像背景文献」「条目太旧」
「只有一个条目」之类自动放行——自动放行会把判据重新变成提示。

## 3. severity 决策：固定黄，不升红

| 场景 | 结果 |
|---|---|
| 默认（l0/l1/l2，无红） | `severity=yellow`，exit 3 |
| `--strict` | `severity` 仍为 `yellow`；全局 strict 口径把任何黄项当失败，故 exit 1 |
| 同时存在红项 | 红优先（按红项退出码），`UNUSED_BIB` 仍以黄项列出 |

理由：引用卫生（文献表脏了）与**编造风险**（引用不存在的文献、数字无据）不是
同一类问题。`UNUSED_BIB` 永远不改级为 red；`--strict` 的 exit 1 是全局「黄也
不许过」的操作口，不是本码升红。SPEC §8.1 该行已写明这一口径。

## 4. 误报边界

- **闭包＝被扫描的 `.tex`**：注释里、`\begin{thebibliography}` 里、verbatim 里的
  `\cite` 不算（扫描器本就把它们抹掉）。因此「只在注释里引过」仍判黄。
- **未知 cite 命令**（如 `\fancycite{x}`）不产生引用计数：该命令本身已判红
  `UNKNOWN_CITE_COMMAND`（fail-closed），其参数被抹掉，条目仍算未引用。
- **同一 key 定义多次**：`DUPLICATE_BIB_KEY` 已判红；未引用清单按 key 去重，
  不因重复定义重复报黄。
- **多 bib 文件**：`total` 合并；只报真正未被任何闭包文件引用的条目。
- **空 bib（0 条目）**：无条目可报，绿。
- **v1 与 v3 同判**：判据不依赖证据模型，两边都跑；`bib_allow_unused` 两边都认。
- **不误伤已引用文献**：paper-en 的 11 条全部被引用，`bib_unused=[]`。

## 5. 回归线与测试变化

### 5.1 回归夹具

`fixtures/regression/paper-en`：**0 红不变**；原有 1 黄
（`UNSCANNED_TEX main.tex`，历史存量）不变；新增的 `bib_unused` 为 `[]`——
论文的 11 条参考文献全部在正文引用，没有从「提示」变「黄」。

### 5.2 已有测试的改动（诚实账）

判据从 info 变黄后，**凡是「bib 非空但正文不引用」的合成测试项目都会新增一条黄**。
为了让 203 例继续全绿，改动了三处**测试脚手架**，不改任何既有判据：

1. `tests/test_factscribe.py::make_project` 默认 `bib` 由 `BIB_OK` 改为空串
   （「存在一份合法但不含条目的 bib」）；真正测引用的用例显式传 `bib=BIB_OK`
   （`test_clean_numbers_and_cites`、`test_resolve_failure_degrades_to_unverified`）。
2. `test_string_macro_and_crossref` 由 `\cite{child2021}` 改为
   `\cite{child2021,parent2020}`：该例的本意是 crossref/`@string` 解析，
   parent 未被引用会额外触发新判据；引用两个 key 保持原意且仍然绿。
3. `tests/test_config_shapes.py::write_base` 的 `refs.bib` 改为空文件
   （配置读取测试与引用无关）。

其余 200 例一字未改。`fixtures/benign/*`、`fixtures/hostile/*` 全部原样通过——
说明它们本来就没有「bib 有、正文不引」的条目。

## 6. 新测试（10 例，`tests/test_unused_bib.py`）

| # | 场景 | 期望 |
|---|---|---|
| 1 | bib 2 条、只引 1 条 | exit 3；`UNUSED_BIB` 仅报 `stale2020`，token/location/message 含 key |
| 2 | `\nocite{*}` | exit 0 |
| 3 | `\nocite{stale2020}` 逐条 | exit 0 |
| 4 | `bib_allow_unused = ["stale2020"]` | exit 0 |
| 5 | 两条都引用 | exit 0；`bib_unused=[]` |
| 6 | 3 条、引 2 条、部分未用 | 只报未用的 1 条；`bib_unused=[stale2020]` |
| 7 | 空 bib | exit 0；`bib_entries=0` |
| 8 | `--strict` | exit 1，但 `severity` 仍为 `yellow` |
| 9 | v1 配置读 `bib_allow_unused` | 字段生效 |
| 10 | V3 扁平声明读 `bib_allow_unused` | 字段生效且无 `CONFIG_UNKNOWN_FIELD` |

## 7. 改动文件

- `factscribe/citations.py`：新增 `unused_bib_entries()`。
- `factscribe/texscan.py`：`ScanResult.nocite_all`，识别 `\nocite{*}`。
- `factscribe/config.py`：`Config.bib_allow_unused`（v1/V3 双读，进已知字段表）。
- `factscribe/audit.py`：`UNUSED_BIB` 由 hint 改为 yellow 出码；`summary.bib_unused`。
- `docs/design/SPEC-V3.0.md`：§8.1 码表补触发条件/豁免/severity 口径；§10 字段表补 `bib_allow_unused`。
- `tests/test_unused_bib.py`：10 例新测试。
- `tests/test_factscribe.py`、`tests/test_config_shapes.py`：测试脚手架适配（见 §5.2）。

## 8. 已知未做

- `docs/implementation/IMPLEMENTATION.md` 里的历史样例输出仍把 `UNUSED_BIB`
  画在「[提示]」段——那是批 36 的历史快照，保留原样；现行口径以本文与
  SPEC §8.1 为准。
- 未实现「引用次数过少/自引异常」等更大范围的引用卫生判据（超出本次工单）。
