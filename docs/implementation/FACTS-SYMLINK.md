# 账本软链信任根闸（FACT_FILE_OUTSIDE_PROJECT / FACT_FILE_UNRESOLVED）

> 一条修复的落地记录：根因、修前/修后行为、码表理由、读数。代码在
> `factscribe/config.py` 的账本读取段（`load_facts`）＋
> `factscribe/audit.py` 的报告出口；码表在 `docs/design/SPEC-V3.0.md`。

## 一、缺口：账本软链指向项目外 ⇒ 静默读进账里

**根因**：`factscribe/config.py:1529`（修复前）`load_facts` 的头一行

```python
files = sorted(p for p in cfg.root.glob(cfg.facts_glob) if p.is_file())
```

`Path.is_file()` **跟随软链**：`facts/link.toml` 指向项目外的 toml 时，
`is_file()` 仍是 True，于是 `load_toml(path)` 把那个项目外的文件直接读进
事实账。审计从此拿信任根外的数字当账，findings 里却一条码都没有。

**修前实测**（基点 `2e6d46c`，最小 v1 项目）：

| 输入 | 修前读数 |
|---|---|
| `facts/link.toml` → 项目外 toml | `summary.facts=2`（同一个 id 进账两条）、退出码 1、**无任何越界码**（只有无关的 `DUPLICATE_ID`） |
| `facts/link.toml` → 项目内 toml | 正常纳入（这条一直是对的） |
| `facts/a.toml` ↔ `facts/b.toml` 成环 | 被 `is_file()` 静默跳过：无码、无位置、无提示 |
| `facts/dangle.toml` → 不存在的目标 | 同样静默跳过 |

同域的先例：正文侧闭包目标越界早就判红了（`INPUT_OUTSIDE_PROJECT`，红、
exit 5，见 `factscribe/config.py:1783-1794` 的 `add_ref` 记账），**账本侧
这一直是空的**——同一个工具里，闭包越界判红，账本越界静默读入。

## 二、修法：软链真实目标必须落在项目根内

改动收窄在 `factscribe/config.py` 的账本读取段（不碰并行任务在改的 1400 行
附近）与 `factscribe/audit.py` 的报告出口。

1. **记账**（`config.py` 新增 `_facts_link_kind`）：逐个候选用
   `os.path.realpath(str(path), strict=True)` 取真实目标，再与
   `cfg.root.resolve()` 比较——
   - 越出项目根 ⇒ 记 `cfg.outside_facts`（元素 `(相对路径, 真实目标)`）；
   - 成环（`ELOOP`）／断链（`ENOENT`）⇒ 记 `cfg.unresolved_facts`
     （元素 `(相对路径, 原因)`）；
   - 其余照旧入账。

   两个新字段与既有的 `cfg.outside_inputs`／`missing_inputs`／`dynamic_inputs`
   同构（`Config` 里紧挨着），由 `load_facts` 填充。

   **为什么用 `os.path.realpath(strict=True)` 而不是 `Path.resolve()`**：软链
   成环时后者各版本行为不一致——3.10–3.12 抛 `RuntimeError`，3.13+ 不抛，
   跨版本读数会漂；`realpath(strict=True)` 在 3.10–3.14 行为一致（成环抛
   `ELOOP`、断链抛 `ENOENT`、正常目标返回真实路径）。项目根也先 `resolve()`
   再比较——macOS 的 `/private` 前缀会让词法比较误判越界。

2. **判红**（`audit.py` 新增 `_facts_outside_issues`）：`run_audit` 与
   `run_check` 各发一次——
   - `FACT_FILE_OUTSIDE_PROJECT`（红、`exit_code=EXIT_INTEGRITY`＝5），
     位置＝账文件的相对路径（如 `facts/link.toml`）；
   - `FACT_FILE_UNRESOLVED`（红、exit 5），位置同上，消息里点明是成环还是
     断链。

3. **空账不许被改写**：账文件被拒收后账本是空的，但那是「有账没进审计」
   （exit 5），不是「这个项目没有事实账」（配置错，exit 2）。所以
   `run_audit`／`run_check` 的空账守卫加了条件：只有在**没有任何**拒收
   记录时才抛 `ConfigError`（exit 2）；`brief.py`／`report.py`／
   `doctor.py` 的空账消息也改成先说清是哪一种。

4. **指纹口径对齐**：`facts_digest`（`config.py:1968`）原来走
   `_glob_paths`（同样是 `is_file()` 跟随软链），会把项目外目标的内容算进
   账本指纹。现在被账本拒收的文件不进指纹——指纹只覆盖真正进了账本的输入。
   既有项目（无软链）指纹逐字节不变（27 盘对读 0 差异）。

## 三、修后行为（实测）

| 输入 | 修前 | 修后 |
|---|---|---|
| 界外软链（另有合法账本） | 静默读入、facts=2、无越界码 | 判红 `FACT_FILE_OUTSIDE_PROJECT`、位置 `facts/link.toml`、exit 5；合法账照旧入账（facts=1） |
| 界外软链（唯一账本） | 静默读入、facts=1、exit 3 | 判红 + 位置 + exit 1（v1 折算：另有 `UNKNOWN_FACT_MARKER`/`UNMATCHED_NUMBER` 红码在，`checks.py:80` 的折算按既有优先级取 1；v3 项目 `integrity_first=True` ⇒ exit 5）；**不再被改写成 exit 2 的「空账」** |
| 界内软链 | 正常纳入 | 正常纳入，审计读数与同内容的普通文件**逐项相同**（正例锁） |
| 成环软链 | 静默丢弃 | 判红 `FACT_FILE_UNRESOLVED`（环上两条各一条）、exit 5 |
| 断链软链 | 静默丢弃 | 判红 `FACT_FILE_UNRESOLVED`、exit 5 |
| `facts/` 整个目录是软链（指向项目外） | 静默读入 | 判红 `FACT_FILE_OUTSIDE_PROJECT`、位置 `facts/x.toml` |

三类输入都不崩：没有 traceback，退出码不是 4。

## 四、码表：新增两码，不复用 `INPUT_OUTSIDE_PROJECT`

| code | 含义 | 触发条件（唯一映射） | severity | exit | 规则 |
|---|---|---|---|---|---|
| FACT_FILE_OUTSIDE_PROJECT | 事实账文件越出项目根 | `facts/*.toml` 的真实目标越出项目根（软链指向项目外，或经软链目录绕出去） | red | 5 | §11.1／R-04 |
| FACT_FILE_UNRESOLVED | 事实账软链不可解 | `facts/*.toml` 的软链成环或断链——真实目标不可解，内容不可知 | red | 5 | §11.1／R-04 |

**为什么新开而不复用**：`INPUT_OUTSIDE_PROJECT` 的含义是「**闭包**输入
越界」（规则 R-05，登记在 §8.2 沿用码表），发生在正文闭包展开时；账本文件
越界是另一个现象（§11.1 事实账形态／R-04 信任根）。SPEC-V3.0 §8 开宗明义
「**每个 code 必须唯一映射一个现象**」，把两个现象并进一个码就违反了这张表
的约束，也会让判卷（§8.4 唯一映射表）分不清是正文越界还是账本越界。

**为什么严重度红、exit 5**：与正文侧闭包越界同级——都是「有内容没进审计」。
README 的 exit 5 条目原文就是「红，覆盖缺口或信任链失败……这是『有内容没进
审计』」；§2.5 权威表把 5 定义为 `RED(COVERAGE|INTEGRITY)`。

登记位置（按 SPEC 表形状，不私造码形）：§8.1 核心码表、§8.3 本批码表 diff
（两条「新增」，并写明不复用 `INPUT_OUTSIDE_PROJECT` 的理由）、§8.4 唯一映射
表、§11.1 事实账形态（新增「信任根」条款）、§11.4 错误码与退出码写死表
（tier=INTEGRITY、exit=5、实现位置）；README.md 与 README.en.md 的 exit 5
覆盖面与空账说明同步。

**未动**：既有码的 severity/exit 一律没改；`tests/conformance/expected.json`
的 `core_codes`（Python↔JS 双实现一致锁）不新增条目——新码没有 JS 侧实现。

## 五、读数

- 测试：新增 `tests/test_facts_symlink.py`（10 例）。同一份测试指向修前基点
  `2e6d46c` 跑：**6 例红**（缺陷重现），修后 **10 例全绿**。
- 矩阵：3.10／3.11／3.12／3.13／3.14 全量各 **1712 例全绿**
  （3.10 有 2 例 skip，是 `tests/test_toml_compat.py` 的 tomllib 版本闸，
  不是 PDF 层；poppler 与 pdftoppm 在位，PDF 层真跑）。
- legal 集成套件：**166 例全绿**。
- node 集成件：**158 例全过**（`node --test tests/*.test.mjs`）。
- 金样例基线 `tests/golden/audit_findings_baseline.json`：**逐字节未动**，
  sha256 `fdf772ab9783bb34a21fd34a674f36195797acb6b39d8ced033c013f23844d40`。
- 27 个 fixture/example 盘逐盘 `audit --json` 对读（修前基点 vs 本分支）：
  **判定 0 变化**，27 份输出逐行相同（退出码＋findings/issues/warnings/hints
  ＋facts 计数逐项比对）；27 盘 `facts_digest` 对读同样 **0 差异**。

## 六、边界与未验证项

- **未推远端、未建 PR、未跑 gh、未动 origin/main 与其它工作树**；只做了本地
  commit。
- **Windows 真机端到端未验证**（本机 macOS）。软链用例在不能建软链的机器上
  按 `SkipTest` 跳过（与 `tests/test_report_core.py::test_symlink_rejected`
  同一纪律），不许假绿。
- **读侧已闭合，写侧还有一条同族缺口**（本次未修，超出本任务范围）：
  `fact add` 的落盘目标是固定名 `facts/facts.toml`（`scaffold.py:514`），
  若该文件本身是指向项目外的软链，写入会跟着软链落到项目外——那是写信任，
  不是读信任。
