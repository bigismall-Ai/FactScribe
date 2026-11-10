# AUDIT-GAPS｜批 97：`audit` 三个已登记缺口

> 依据：`docs/release/KNOWN-GAPS.md` 第二节（v1.2.0 盲测 #9 暴露的三条，原计划 v1.3）。
> 范围：只改 `audit` 的判据与分诊；`check` 的既有 `EXPR_MISMATCH` 口径保持并抽出共用。
> 日期：2026-11-10

---

## 一、三条判据

| # | 判据 | 触发 | 错误码 | 级别 / 退出码 |
|---|---|---|---|---|
| 1 | 动态闭包目标（`tex-input-dynamic`） | `\input{...}` / `\include{...}` 的目标含宏（`\jobname`、`\macro` 等）、`#`、嵌套花括号、花括号未闭合或为空 | `INPUT_DYNAMIC` | 红 / 5 |
| 2 | 派生算式不符（`free-derived-expr`） | fact 同时有 `value` 与 `expr`，expr 求值结果与 value 不一致 | `EXPR_MISMATCH` | 红 / 1 |
| 3 | 绑定后不符（`num-bind-mismatch` 分诊） | 该行已绑定定量 fact，但数字不在其值域内 | `BOUND_MISMATCH`（不再用 `UNMATCHED_NUMBER`） | 红 / 1 |

### 1. 动态闭包目标（fail-closed）

- `\input{\macro}`、`\input{\jobname}`、`\include{sec#1}`、`\input{\foo{bar}}`、
  `\input{a{b}}`、`\input{}`、未闭合的 `\input{foo` 全部判红；报错带 `文件:行` 与**完整原始目标串**
  （例如 `\foo{bar}`，不会被 `[^}]*` 截成 `\foo{bar`）。
- 静态目标（含省略 `.tex` 的写法）行为不变：存在则进闭包，不存在仍报
  `INPUT_TARGET_MISSING`（exit 5）。
- 注释/verbatim 里的 `\input` 不算；`\newcommand{\X}[1]{\input{#1}}` 的宏体是
  **定义**，不是一次实际包含——定义体被掩码，闭包仍由包装宏展开逻辑处理。

### 2. 派生算式不符

- 比较口径复用 `check`：`abs(got - want) > rel * max(1.0, abs(want))`，缺省
  `rel = 1e-9`（相对误差，不新造浮点规则）。
- 显式容差：fact 可写 `expr_tolerance = "1e-6"`（相对误差，非负）；不写则用缺省。
- 报错给两侧数值与误差，例如
  `算出 56.25，与 value='75%'（75）不符：误差 18.8 超过容差 7.5e-08`。
- 无 `expr` 的 fact 行为不变；expr 不可求值仍报 `EXPR_INVALID`（红 / 1）。

### 3. 绑定后不符的分诊

- 数字落在一个**已绑定定量 fact 的行**上，但不在该 fact 的 `value` 里 →
  `BOUND_MISMATCH`；同一行另一句里的数字也按行级绑定分诊。
- 该行没有任何定量 fact 绑定，且任何 fact 都命中不了 → 仍 `UNMATCHED_NUMBER`。
- 未绑定但回得到账的数字仍 `UNBOUND_NUMBER`（黄 / 3）；`--strict` 行为不变。
- 两类都是红、exit 1：**只改分类，不改红/黄级别与退出码**；v3 下同时保留
  `ASSERTION_DRIFT`。

---

## 二、实现位置

| 事项 | 文件 | 函数 / 位置 |
|---|---|---|
| 闭包目标解析（平衡花括号） | `factscribe/config.py` | `_input_arg_end()`（L887）/ `_input_refs()`（L906） |
| 宏定义体掩码 | `factscribe/config.py` | `_mask_macro_defs()`（L928） |
| 动态目标判定 | `factscribe/config.py` | `_dynamic_ref_reason()`（L953） |
| 动态目标记账 | `factscribe/config.py` | `Config.dynamic_inputs`（L212）、`add_raw_ref()`（L1051） |
| `INPUT_DYNAMIC` 判红 | `factscribe/audit.py` | `run_audit()`（L979） |
| expr↔value 比较（check/audit 共用） | `factscribe/audit.py` | `EXPR_REL_TOL`（L75）、`_expr_issues()`（L78） |
| `audit` 面调用 expr 判据 | `factscribe/audit.py` | `run_audit()` 中 `red += _expr_issues(...)` |
| `expr_tolerance` 字段 | `factscribe/facts.py` / `factscribe/config.py` | `Fact.expr_tolerance`（L182）/ `_fact_from_mapping()` |
| 绑定后不符分诊 | `factscribe/audit.py` | `_line_bound_quant()`（L1135）+ `run_audit()` 未分组数字分支（L1188） |

测试：`tests/test_audit_gaps.py`，**25 例**（三个缺口各有正负例；另有
`examples/minimal` 恰好两红回归锁、新码 JSON/报表字段稳定、旧码不再用于绑定后不符）。

---

## 三、门禁输出

### 全量单测

```text
$ env PYTHONPATH=src python3 -m unittest discover -s tests
Ran 563 tests in 29.626s
OK
```

### `scripts/preflight-ci.sh --fast`

```text
== 步骤 1/4：外部依赖（CI 装了 poppler；本机没有则 PDF 测试会红）
   ✓ pdftotext：/opt/homebrew/bin/pdftotext
   ✓ pdfinfo：/opt/homebrew/bin/pdfinfo
   ✓ PDF 工具齐备
== 步骤 2/4：干净克隆（--fast：跳过，直接用工作区）
== 步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12）
   ✓ Python 3.10：Ran 563 tests
   ✓ Python 3.11：Ran 563 tests
   ✓ Python 3.12：Ran 563 tests
== 步骤 4/4：验收样例必须 exit 1（workflow 的硬断言）
   ✓ examples/minimal audit exit=1（红，符合预期）
== 结论
   本地等价 CI 全绿——可以推。
```

干净克隆版 `./scripts/preflight-ci.sh`（默认，克隆本批提交后跑同一矩阵）：

```text
== 步骤 1/4：外部依赖（CI 装了 poppler；本机没有则 PDF 测试会红）
   ✓ pdftotext：/opt/homebrew/bin/pdftotext
   ✓ pdfinfo：/opt/homebrew/bin/pdfinfo
   ✓ PDF 工具齐备
== 步骤 2/4：干净克隆（只含已提交文件——夹具缺源文件这里就会暴露）
   ✓ 克隆到 …/factscribe-ci.Z1hkmf/repo（HEAD 本批提交）
== 步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12）
   ✓ Python 3.10：Ran 563 tests
   ✓ Python 3.11：Ran 563 tests
   ✓ Python 3.12：Ran 563 tests
== 步骤 4/4：验收样例必须 exit 1（workflow 的硬断言）
   ✓ examples/minimal audit exit=1（红，符合预期）
== 结论
   本地等价 CI 全绿——可以推。
```

---

## 四、两篇论文复跑读数

| 项目 | 命令 | exit | 红 | 黄 | 新红 |
|---|---|---|---|---|---|
| `paper/` | `audit ../paper` | 3 | **0** | 1（`UNSCANNED_TEX` main.tex，既有） | 无 |
| `paper-zh/` | `audit ../paper-zh` | 3 | **0** | 1（`UNSCANNED_TEX` main.tex，既有） | 无 |

两篇论文仍然 0 红；没有新增红项需要逐条判断真问题/误报。唯一黄项是既有的
「`main.tex` 不在审计闭包」提示，与本批三条判据无关。

`examples/minimal` 回归：exit 1，恰好两红
`UNMATCHED_NUMBER 47.3` + `MISSING_CITE ghost2024`，与冻结读数一致。

---

## 五、边界与未动项

- 动态目标只覆盖 `\input/\include/\subfile/\import` 家族；`\csname` 构造的
  命令名不在本批范围（仍由其它规则处理）。
- `expr_tolerance` 是相对误差；绝对容差不在本批引入（避免第二套浮点规则）。
- `BOUND_MISMATCH` 分诊只作用于原本会报 `UNMATCHED_NUMBER` 的红项；
  黄级 `UNBOUND_NUMBER` 的分类与级别不变。
