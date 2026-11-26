# 写侧软链信任根闸（账本落点越界就拒写）

> 一条修复的落地记录：写侧链路、落点闸、码表理由、读数、边界。代码在
> `factscribe/safepath.py`（新增，落点闸）＋ 六个写盘点；读侧那条同族缺口
> 见 `docs/implementation/FACTS-SYMLINK.md`（并行分支
> `fix/facts-symlink-outside-20261125`，提交 017d9e6）。

## 一、缺口：写入目标是指向项目外的软链 ⇒ 写入跟着软链落到项目外

**根因（写侧）**：`factscribe/scaffold.py` 的 `add_fact`（账本追加）
在修前是这样落盘的：

```python
ledger = _ledger_path(root, cfg)          # facts/01-core.toml（固定名）
...
ledger.write_bytes(existing + sep + block.encode("utf-8"))   # 跟软链走
```

`Path.write_bytes()` **跟随软链**：`facts/01-core.toml` 指向项目外的文件时，
写入就落在项目外；`facts/` 整个是指向项目外的软链时，新账本也建在项目外。
写侧此前**没有任何落点闸**——同一族里读侧（audit）已经判红
（`FACT_FILE_OUTSIDE_PROJECT`，red / exit 5），写侧却一路放行。

**读侧那条与本条是同一现象的两端**：同一个对象（事实账文件的真实目标）、
同一条信任根规则（SPEC-V3.0 §11.1「账文件必须在项目根内」）、同一个
`realpath` 判定口径；读侧在**读**的时候判红，写侧要在**写**的时候先拦住。

**修前实测**（基点 `2e6d46c`，最小 v1 项目，`fact add`）：

| 输入 | 修前行为 |
|---|---|
| `facts/01-core.toml` → 项目外 toml | **写入成功**，项目外的文件被追加了 `[[fact]]`；退出码 0 |
| `facts/` → 项目外目录 | **写入成功**，项目外凭空多出 `01-core.toml`；退出码 0 |
| `facts/01-core.toml` → 项目外不存在的路径（断链） | **写入成功**，项目外凭空造出那个文件；退出码 0 |
| `facts/01-core.toml` ↔ 自身（成环） | 退成 **exit 4**（`FileExistsError`／ELOOP 的内部错误） |
| 项目内软链 | 正常写入（这条一直是对的） |

## 二、写侧链路：谁会写账本、怎么写

| 入口 | 落点 | 机制 | 修前能否越界 |
|---|---|---|---|
| `factscribe fact add`（CLI） | `facts/01-core.toml`（固定名，`scaffold.py:497` `_ledger_path`） | `ledger.write_bytes()`：**非原子**（直接截断重写），无临时文件、无 `.bak` | **能**（文件级＋目录级） |
| MCP `factscribe_add_fact` | 同上 | 同上（同一条 `add_fact`） | **能** |
| 本机工作台 `POST /api/facts` | 同上 | 同上（同一条 `add_fact`） | **能** |
| `factscribe fact import` | `facts/<experiment>.<report_id>.toml`（`cli.py:1128`） | `_write_atomic`：同目录临时文件 + `os.replace` | 目录级**能**（文件级不会：`replace` 换掉软链本身，不穿透） |

三条入口（CLI / MCP / 工作台）共用 `factscribe/scaffold.py::add_fact`，
所以**一处闸就够**；`fact import` 是另一条独立的写盘路径，另设闸。

**原子性与旁路文件**：`fact add` 的落盘**不是**原子的（`write_bytes`
先截断再写），但它**不产生任何旁路文件**——没有临时文件、没有 `.bak`。
本仓引擎里没有 `last_opened` / `.bak` 这类旁路写盘路径（它们在 MiniApp
宿主侧 `workbench/write.py::touch_opened`，不在本仓本基点）；仓里唯一的
`.bak` 字样是 `tests/test_tide.py` 的测试夹具。因此「旁路文件跟着软链
出去」在本仓的实际形态是**临时文件**：`fact import` 的 `_write_atomic`
把临时文件写在目标同目录，目录是软链时临时文件与产物一起落到项目外——
落点闸把这一类一并挡住。

**为什么不动「非原子」**：改成 tmp+rename 会改变「软链在项目内」时的行为
（`os.replace` 会把软链换成普通文件，软链就消失了），与「正常项目行为
一字不变」冲突；且非原子是既有口径、不属本族缺口。本条只保证**拒绝时**
不留半截状态（拒绝发生在任何写动作之前，不删、不覆盖、不建临时文件）。

## 三、修法：一个落点闸，两个入口

新增 `factscribe/safepath.py`（判定口径只有一份，写侧与读侧同一套
`realpath` 规则）：

- `guard_facts_write(root, target)`：**事实账**专用。越界 →
  `FACT_FILE_OUTSIDE_PROJECT`（red / exit 5）；软链成环／落点不可解 →
  `FACT_FILE_UNRESOLVED`（red / exit 5）。两个码都是**读侧已登记的**，
  severity 与 exit **一律不动**。
- `guard_project_write(root, target)`：**其它项目内写盘**用。越界 →
  `PATH_ESCAPE`（仓里既有的写侧越界码，章节写回／资产通道在用），exit 2。

判定规则：

1. 落点存在（含软链、含断链）→ 解析它的真实目标；
2. 落点还不存在 → 解析它爹目录的真实位置，再拼上文件名（目录是软链的话，
   新文件就落在软链那边）；
3. 软链成环 → 真实目标不可解（`ELOOP`）→ 判「不可解」，拒写；
4. 落点的爹目录本身是断链软链 → 落点不可解（否则 `mkdir` 会抛
   `FileExistsError` → 退成 exit 4）。

用 `os.path.realpath(strict=True)` 而不是 `Path.resolve()`：后者在软链
成环时 3.10–3.12 抛 `RuntimeError`、3.13+ 不抛，跨版本读数会漂（读侧同因，
本条沿用同一口径）。项目根也先 `realpath` 再比较——macOS 的 `/private`
前缀会让词法比较误判越界。

**闸只加不改写**：落点合法时，写盘调用一个字没动（仍写原路径、仍写穿
软链），所以「指向项目内的软链」落点与内容逐字节不变。

## 四、仓内写盘路径清单（全部盘过）

「解析结果」＝写入目标的真实位置相对项目根的判定。

| # | 写盘路径 | 目标 | 机制 | 软链解析结果 | 修前 | 现状 |
|---|---|---|---|---|---|---|
| W1 | `fact add`（CLI／MCP／工作台） | `facts/01-core.toml` | `write_bytes` | 文件或目录是软链 → 跟出去 | **能** | 已修（`scaffold.py:546`） |
| W2 | `fact import` | `facts/<exp>.<rep>.toml` | tmp + replace | 文件级换掉软链；目录级跟出去 | 目录级能 | 已修（`cli.py:1134`） |
| W3 | 图表产物 | `figures/gen/*`、`figures/bind.toml` | `write_text` | 目录或文件是软链 → 跟出去 | **能** | 已修（`figures.py:894`） |
| W4 | 证据冻结件 | `audit/evidence.lock` | `write_text` | 同上 | **能** | 已修（`evidence.py:277`） |
| W5 | 待补文献登记表 | `refs/todo.toml` | tmp + replace | 目录级跟出去 | 目录级能 | 已修（`refs.py:959`） |
| W6 | 检索候选落盘 | `refs/candidates/*` | tmp + replace | 目录级跟出去 | 目录级能 | 已修（`refs.py:881`） |
| W7 | 项目声明改写 | `<项目>/factscribe.toml` | `write_text_exact` | 文件是软链 → 跟出去 | **能** | 已修（`projects.py:239`） |
| W8 | 矩阵产物 | `audit/matrix.md` | `write_text` | 目录级跟出去 | **能** | 已修（`cli.py:1541`） |
| W9 | 前言产物 | `audit/preamble.tex` | `write_text` | 同上 | **能** | 已修（`cli.py:1559`） |
| W10 | 构建字体补丁 | 构建副本里的入口 tex | `write_text_exact` | 副本保留入口软链（`copytree(symlinks=True)`）→ 跟出去 | **能** | 已修（`buildpdf.py` `_write_font_patch`） |
| W11 | 章节写回 | `<项目>/sections/*.tex` | tmp + replace（目标先 resolve） | 目标 resolve 后越出项目根 → 已拒（`PATH_ESCAPE`）；`_section_path` 另拒路径里的软链 | 否 | 已有闸（`workbench.py:169`、`:230`），本次未改 |
| W12 | 章节增删改名 | 同上 | — | `_section_path` 逐段拒软链 | 否 | 已有闸，本次未改 |
| W13 | 报告锁／签收产物 | 工作区 `<ws>/reports/*` | tmp + replace | `_resolve_in_ws` 拒软链与越界 | 否 | 已有闸；且工作区是**另一个信任根**（不是论文项目），本次未改 |
| W14 | `tide` 差分账／派生视图 | 用户指定的 `--after`／`--out` 目录 | 多种 | 落点由用户指定 | — | **不属本族**：写到用户指定的盘外路径是设计意图，本次未改 |
| W15 | `bundle` 导出产物 | 用户指定的导出目录 | `copyfile` | 同上 | — | **不属本族**（设计意图），本次未改 |
| W16 | 登记册 | `~/.factscribe/registry.json` | tmp + replace | — | — | **不属本族**：用户级登记册，不是项目内写盘 |
| W17 | 样例安装 | `~/.factscribe/samples/…` | `copytree` | — | — | **不属本族**（同上） |
| W18 | 字体安装 | 用户指定字体目录 | — | — | — | **不属本族**（同上） |
| W19 | `brief --out`／`terms --out`／`matrix --out` | 用户指定路径 | `write_text` | 落点由用户指定 | — | **不属本族**（设计意图）；**默认落点**已修（W8/W9） |
| W20 | `.bak`／`last_opened` 旁路 | — | — | — | — | **本仓无此路径**（在 MiniApp 宿主侧 `workbench/write.py::touch_opened`，不在本基点）；等价形态（临时文件）已由落点闸覆盖 |
| W21 | `init` 项目骨架 | 七个固定文件（含 `facts/01-core.toml`） | `write_bytes` | 文件或目录是软链 → 跟出去 | **能** | 已修（`scaffold.py` `init_project`：七个落点先全查一遍再落盘，不留半副骨架） |

W1–W10、W21 是同一族（写盘落点越出项目根），已一并修掉；W11–W13 本来就有闸；
W14–W19 写在用户指定的位置，是设计意图，不属本族；W20 不在本仓。

## 五、码表：复用读侧既有码，不新开

**结论**：事实账写侧越界**复用**读侧已登记的 `FACT_FILE_OUTSIDE_PROJECT`
（红、exit 5），落点不可解复用 `FACT_FILE_UNRESOLVED`（红、exit 5）；
**severity 与 exit 一律不动**（既有码不改级、不改退出码）。

**理由**（SPEC-V3.0 §8「每个 code 必须唯一映射一个现象」＋§8.4
「现象 → 唯一 code」）：

1. **同一对象**：写侧要写的那个文件，就是读侧判红的那个文件——事实账
   （`facts/*.toml`，`facts/01-core.toml` 是它的固定名之一）。不是另一个
   对象。
2. **同一现象**：判据都是「该文件的真实目标越出项目根」。写侧多出来的只是
   **阶段不同**（读侧是读的时候判红，写侧是写的时候先拦）。
3. **§8.4 是反向唯一**：现象 → 唯一 code。同一现象配两个码就破了这条；
   反过来，同一码跨两个阶段发出（读侧判红、写侧拒写）才是合规的。
4. **既有码的 severity/exit 不动**：读侧把这两个码定成 red / exit 5，
   写侧沿用，不改成 exit 2 也不改成 exit 1。

**其它项目内写盘**（W3–W10、W21）**不套事实账的码**：那些不是事实账（是图表、
登记表、冻结件、声明文件），是另一个对象；它们复用仓里既有的写侧越界码
`PATH_ESCAPE`（章节写回 `workbench.py`、资产通道 `serve.py` 在用），
exit 2（配置/用法层）。**没有新开码，也没有私造码形**。

**本分支不重复登记那两个码**：它们的 §8.1／§8.3／§8.4／§11.1／§11.4
与中英 README 登记在并行分支 `fix/facts-symlink-outside-20261125`（017d9e6），
本分支再抄一遍会在合并时产生同一行的文本冲突。合并后码表即该码的一行
登记，写侧拒写是它的第二个触发面（同一现象）。若审核要求本分支自带登记，
从 017d9e6 取那五行原样搬入即可（合并时取并集措辞）。

**命令层的退出码**：写盘被拒时事实账走 `exit 5`（信任链失败），不是
exit 2（配置错）也不是 exit 4（内部错误）。为此 `ConfigError` 多了可选项
`exit_code`（`cli.py:2147` 按它分层），人读前缀按退出码分（exit 2 仍是
「配置/用法错」，exit 5 是「信任链失败」），`--json` 里 `exit`／`code`／
`findings` 三处一致。

## 六、修后行为（实测，基点 2e6d46c → 本分支）

| 输入 | 修前 | 修后 |
|---|---|---|
| 账本文件 → 项目外 | 写入成功，项目外被追加 `[[fact]]`，exit 0 | 拒写：`FACT_FILE_OUTSIDE_PROJECT`、exit 5；**项目外一个字节都没动**（目录快照逐文件比对相等） |
| `facts/` → 项目外目录 | 写入成功，项目外凭空多出 `01-core.toml`，exit 0 | 拒写：`FACT_FILE_OUTSIDE_PROJECT`、exit 5；项目外目录**空** |
| 账本 → 项目外不存在的路径（断链） | 写入成功，项目外被凭空造出文件 | 拒写：`FACT_FILE_OUTSIDE_PROJECT`、exit 5；那个文件**没有被造出来** |
| 账本 ↔ 自身（成环） | exit 4（内部错误） | 拒写：`FACT_FILE_UNRESOLVED`、exit 5（不是 exit 4、不是 traceback） |
| `facts/` 是断链软链 | exit 4（`FileExistsError`） | 拒写：`FACT_FILE_UNRESOLVED`、exit 5 |
| 指向项目内的软链（文件级） | 正常写入 | 正常写入：**软链仍是软链**，内容落在软链的真实目标上，与「同内容的普通文件」逐字节相同 |
| 指向项目内的软链（目录级） | 正常写入 | 正常写入：内容落在项目内被链接的目录里 |
| 正常项目（无软链） | 正常写入 | 正常写入（读数一字未变） |
| `init` 落骨架（账本是软链） | 写入成功，项目外被覆盖 | 拒写：`FACT_FILE_OUTSIDE_PROJECT`、exit 5；**骨架一个文件都没落**（七个落点先全查一遍，不留半副骨架） |

三类越界输入都不崩：没有 traceback，退出码不是 4。

## 七、测试

新增 `tests/test_facts_write_symlink.py`（17 例）：

- 写侧越界三类输入（账本文件软链／目录软链／断链／成环）：必须拒绝、
  不得落盘到项目外、不得留下半截文件（断言方式是**整棵目录树快照逐项
  相等**：多一个 `.tmp-*` 或 `.bak` 都不相等）；
- 正例：正常项目、项目内文件软链、项目内目录软链——行为不变，且项目内
  软链写出来的内容与「同内容的普通文件」逐字节相同；
- 同族缺口：`fact import`、图表产物、证据冻结件、待补文献登记表、`init`
  项目骨架、构建字体补丁——落点越界一律拒写；
- 错误形态：JSON 里 `code`／`exit`／`findings` 三处一致；人读模式说清
  落点与「没落盘」。

**同一份测试指向基点会红**（干净克隆 `2e6d46c`，同一份
`tests/test_facts_write_symlink.py`）：

```
Ran 17 tests —— FAILED (failures=12, errors=1)
```

红的 13 例＝全部越界/不可解用例（账本文件软链、目录软链、断链、成环、
断链目录、人读错误形态、工作台／MCP 入口、`fact import`、图表、证据锁、
登记表、`init` 骨架；其中构建字体补丁那例在基点是 ERROR——基点连这层闸的
入口都没有）；
绿的 4 例＝正例（正常项目、项目内文件软链 ×2、项目内目录软链）——正例在
修前修后都绿，正是「行为一字不变」的证据。修后 17 例全绿。

## 八、读数

- 主套件矩阵（解释器路径写死，不让 uv 解析到项目 `.venv`；本机 poppler
  与 `pdftoppm` 在位，PDF 层真跑）：

  | Python | 全量 | skip |
  |---|---|---|
  | 3.10.20 | 1719 例 OK | 2（`test_toml_compat.py` 的 tomllib 版本闸，不是 PDF 层） |
  | 3.11.16 | 1719 例 OK | 0 |
  | 3.12.13 | 1719 例 OK | 0 |
  | 3.13.14 | 1719 例 OK | 0 |
  | 3.14.6 | 1719 例 OK | 0（4 条 ResourceWarning 在基点同样出现，非本次引入） |

- legal 集成套件（`integrations/factscribe-legal/tests`）：3.10–3.14 各
  166 例全绿（3.10 有 4 例 skip，是该套件自己的版本闸）。
- node 集成件（旧宿主 `integrations/minifactscribe/` 的 158 例）：第 ④ 步随旧宿主
  删除，这条读数留作历史；现行 node 用例在 `miniapp/tests/`。
- 金样例基线 `tests/golden/audit_findings_baseline.json` 逐字节未动：
  `sha256 = fdf772ab9783bb34a21fd34a674f36195797acb6b39d8ced033c013f23844d40`。
- 27 个 fixture/example 盘（`examples/minimal` ＋ `fixtures/benign/*` 12 ＋
  `fixtures/hostile/*` 12 ＋ `fixtures/legal-demo` ＋
  `fixtures/regression/paper-en`）逐盘 `audit --json` 对读基点（基点
  `2e6d46c` 的同盘输出）：**判定 0 变化**，27 份输出逐行相同。
- 验收样例 `examples/minimal` 的 `audit` 仍是 exit 1（红，符合预期）。

## 九、边界

- **未推远端、未建 PR、未跑 gh、未动 `origin/main`、未动主检出与其它工作树。**
  本分支基于 `2e6d46c`，工作树 `.worktrees/facts-write-symlink`，分支
  `fix/facts-write-symlink-outside-20261125`。
- **Windows 真机端到端未验证**（本机 macOS）。软链用例在不能建软链的机器上
  按 `SkipTest` 跳过，不许假绿。
- 读侧那条（017d9e6）与本条是同一族的两端，两条分支都要并进集成线；码表
  登记只在读侧那条，本分支不重复登记（见第五节）。
- 构建的字体补丁（W10）只做了落点闸的单元级覆盖：本地没有 tectonic，也没有
  触发字体兜底的环境，端到端的那一段没跑。

## 十、Windows 真机复验补的一条（2026-11-25）：不可解的判据改成语义口径

本条原来说「软链成环 → 抛 OSError(ELOOP)」——**这条前提只在 POSIX 成立**。
Windows 真机（10.0.1.9，ACP=936）实测：

| 软链形态 | `os.path.realpath(strict=True)` 在 Windows 上 | 在 POSIX 上 |
|---|---|---|
| 正常 | 返回真实路径 | 同 |
| 断链 | `OSError(winerror=2, errno=2 ENOENT)` | `ENOENT` |
| **成环** | `OSError(winerror=1921, errno=22 EINVAL)` | `OSError(ELOOP)` |

> Windows 的 `errno.ELOOP` 常量是 **10062**，跟这里收到的 errno（22）
> 不是一回事，所以原来那句 `if exc.errno != errno.ELOOP: raise` 在 Windows 上
> **必然漏判**：写侧成环 → OSError 裸崩 → 命令层退成 **exit 4**（工具内部错误），
> 而不是 `FACT_FILE_UNRESOLVED` / **exit 5**。

修法（判据从 errno 白名单改成**语义**）：

* `strict realpath 抛错 = 落点解不出来 = 不可解`（成环只是其中最常见的一种，
  文案按能判出来的形态说；判不出就说「算不出来」，不编原因）；
* 事实账入口 → `FACT_FILE_UNRESOLVED`（red，exit 5）；其它项目内写盘入口 →
  `PATH_ESCAPE`（exit 2）。**两个码都是既有的，不新开**（第五节）。
* 两个入口在 POSIX 上的**原话一个字没动**（成环时事实账那条仍写
  「是成环软链，真实落点算不出来——拒绝写入（没有落盘，也没有改原文件）」）。

新增用例（`tests/test_facts_write_symlink.py::TestUnresolvableLandingPoint`，5 例）：
用**注入异常**的方式把「Windows 成环错（winerror=1921 / errno=EINVAL）」
「POSIX 成环错（ELOOP）」「别的 OSError（EACCES）」三种失败形态喂给闸，
断言三者判成**同一个码、同一个退出码**；另有一条走命令层（`cli.main`），
断言 exit **5** + `FACT_FILE_UNRESOLVED`（不是 exit 4）。
真实软链那条真路仍由 `test_symlink_loop_is_refused_as_unresolved` 覆盖——
在 Windows 上它走的就是 winerror=1921 那条真路。

**见红再改绿**：同一份新用例指向修前基点（`88d757d`）跑 → 4 红（1 failure
＋ 3 errors，报错正是 `OSError: [Errno 22] 系统无法辨识文件名。` 与 exit 4）；
修后全绿。Windows 真机复验读数见同批的《FactScribe Windows 真机验证报告》。

