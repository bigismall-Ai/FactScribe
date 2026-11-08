# 事实账 schema 冻结与实现对齐（批 54）

> 对应规范：`docs/design/SPEC-V3.0.md` §11（本次新增，冻结）。
> 处理对象：`facts/*.toml` 与 `\fact{}` 绑定；不含 `factscribe.toml`（§10 已冻结）。

## 一、为什么有这一批

盲测 #4（24 个封存项目，`/tmp/holdout4`）首跑 **0/12 invalid 命中、0/12
valid 干净**：配置面（`[project]` + `root_tex`）已经对上了，但事实账写成

```toml
schema = "paperkit-fact/3.0"
[[fact]]
id = "A1"
...
```

实现把「有 `schema` 头」直接当成「一文件一条的扁平表」，于是整张表被当成
一条 fact 读，`id` 落在 `fact` 数组里读不到 → 24 个项目一起报
`缺 id（不准匿名入账）`，exit 2。这是**契约缺口**：§10 只冻了项目声明，
`facts/*.toml` 的形态、`display` 缺省、`\fact{}` 语义都没有写死。

本批做两件事：把 schema 写进规范 §11；实现按 §11 对齐，再重跑同一份盲测。

## 二、冻结的 schema（抄自 SPEC-V3.0 §11.1）

```toml
schema = "paperkit-fact/3.0"   # 可选

[[fact]]
id = "A2"                    # 必需，唯一，[A-Za-z0-9._-]
claim = "..."                # 必需
value = "10/16"              # 必需；数字的规范形态
display = "10/16"            # 可选；与 value 严格等价（也接受数组）
source = "runs/run-01/result.json"
source_sha256 = "sha256:..."  # 必需；允许带 sha256: 前缀
locator = "§二 表 1"          # 可选
confidence = "high"           # high|med|low
derived_from = ["A1"]         # 可选；派生时必填
expr = "..."                  # 可选；派生算式（仅四则+括号）
note = ""
```

| 字段 | 必需 | 取值/类型 | 归一口径 |
|---|---|---|---|
| `id` | 是 | `[A-Za-z0-9._-]+` | 去空白；判重/引用按 `casefold()` |
| `claim` | 是 | string | 原文 |
| `value` | 是 | string | 规范数字形；分数取精确商 |
| `display` | 否 | string 或 string[] | 缺省回填 `[value]`；LaTeX 转义先还原再比较 |
| `source` | 与 `observation` 二选一 | 项目内相对路径 | 存在时核 `source_sha256` |
| `observation` | 与 `source` 二选一 | `{run_id, pointer}` | 有 `runs/<run_id>/summary.json` 时自动取作 source |
| `source_sha256` | 是 | 64 hex，可带 `sha256:` | 去前缀、小写化后比较 |
| `locator` | 否 | string | 人读定位 |
| `confidence` | 否 | high\|med\|low | 空串缺省（`check` 要求显式合法值） |
| `derived_from` | 有 `expr` 时 | string[] | 父 id；必须存在且不成环 |
| `expr` | 有 `derived_from` 时 | string | 四则+括号+id+`.num/.den`，禁 `eval` |
| `note` | 否 | string | 自由文本 |

容器形态：`[[fact]]` 数组（可多条）；无 `fact` 键时允许「一文件一条、顶层
扁平」的兼容形态。未知字段忽略；未知 `schema` → exit 2。

`\fact{}` 语义（§11.2）：两种写法 `\fact{ID}` 与 `\fact{ID}{display}`；
标记绑定到**同一句**（BU 到句末），句内每个数字必须落在绑定 fact 的
`value`/`display` token 集内；否则 `BOUND_MISMATCH`（v1）＋`ASSERTION_DRIFT`（v3）。
多 id 组按 token 数一一归属，或取并集（有 `co_claim` 时）。

`display` ≠ `value` 允许，但必须严格等价：`10/16` ≡ `0.625` ≡ `62.5%` ≡
`62.5\%`；`0.9` ≠ `0.91`（无舍入容差）。不等价 → `DISPLAY_INCONSISTENT`
（v3 另记 `ASSERTION_DRIFT`）。

## 三、错误码映射（§11.4）

| 情形 | code | tier | exit | 实现位置 |
|---|---|---|---|---|
| 缺 `id` | `FACT_ID_MISSING` | CONFIG | 2 | `factscribe/config.py::_fact_from_mapping` |
| `id` 重复（大小写不敏感） | `DUPLICATE_ID` | FACT | 1 | `factscribe/audit.py::run_check` / `run_audit` |
| `id` 格式不合法（v3） | `BAD_ID_FORMAT` | FACT | 1 | `factscribe/audit.py`（v1 规则不变） |
| 未知 fact `schema` | `FACT_SCHEMA_INVALID` | CONFIG | 2 | `factscribe/config.py::load_facts` |
| `fact` 不是表数组 | `FACT_CONTAINER_INVALID` | CONFIG | 2 | `factscribe/config.py::load_facts` |
| `source_sha256` 与现算不符 | `SOURCE_SHA256_MISMATCH` | FACT | 1 | `factscribe/audit.py::verify_sources`（v3 另记 `APPROVAL_STALE`） |
| `source_sha256` 缺失（v1） | `MISSING_SOURCE_SHA256` | FACT | 1 | `factscribe/audit.py::verify_sources`（v3 源层不强制） |
| 既无 `source` 也无 `observation`/`source_sha256` | `EVIDENCE_CHAIN_BROKEN`（批 56 起；原 `FACT_EVIDENCE_MISSING`） | FACT | 1 | `factscribe/audit.py::verify_sources`（§11.6） |
| `display` 与 `value` 不等价 | `DISPLAY_INCONSISTENT` | FACT | 1 | `factscribe/texrules.py::display_hits` |
| `display` 缺省 | 无（回填 `value`，不判 R-04） | — | — | `factscribe/config.py::_fact_from_mapping` |

CONFIG 类错误的 `--json` 形态新增 `code` 键；`message` 明确指向 §11.1。

## 四、实现位置（逐文件）

| 文件 | 改动 |
|---|---|
| `factscribe/config.py` | `schema`＋`[[fact]]` 同时存在时按数组读；`source`/`observation` 缺省推导；v3 `display` 还原 LaTeX 并缺省回填 `value`；缺 `id` 错误码 `FACT_ID_MISSING` 并指向 §11.1；`ConfigError` 带 `code` |
| `factscribe/facts.py` | 新增 `latex_display()`：`\%`→`%`、`\,`→`,`、`\;`/`\:`/`\~`→空格、`\!`→空 |
| `factscribe/texrules.py` | `display_hits()` 跳过 auto 回填项（按定义等价） |
| `factscribe/audit.py` | `run_audit` 补 `DUPLICATE_ID` 与 v3 `BAD_ID_FORMAT`；v3 允许 `observation` 承载证据（无本地 source 时不误红） |
| `factscribe/v3.py` | S-08 的 `body_regex` 接受 §4 正文那张模板的 `\(...` 转义写法（与 `(?:...` 同一形状） |
| `factscribe/cli.py` | `ConfigError` 的 JSON payload 带 `code` |
| `docs/design/SPEC-V3.0.md` | 新增 §11（schema／`\fact{}`／display 等价／错误码／最小示例） |

v1 兼容：`[[fact]]` 旧账、id 格式、display 判定、`MISSING_SOURCE_SHA256`
全部走原路径；184 例单测全绿。

## 五、盲测 #4 逐项结果（只跑 `/tmp/holdout4`，未改题）

判读口径与 `/tmp/blind_eval.py` 完全一致：invalid 命中＝exit≠0 且命中
EXPECT 的码（空码集只要求 exit≠0）；valid 干净＝exit∈{0,3} 且无红。

| 族 | invalid | 结果 | valid | 结果 |
|---|---|---|---|---|
| assert-appendix-move | 1 | HIT（ASSERTION_DRIFT） | 0 | CLEAN |
| assert-role-moved | 0 | **MISS** | 0 | CLEAN |
| cite-no-stable-id | 0 | **MISS** | 0 | CLEAN |
| cite-number-as-data | 1 | HIT（DISPLAY_INCONSISTENT/ASSERTION_DRIFT） | 0 | CLEAN |
| evid-macro-expired | 1 | HIT（NUMERIC_MACRO_EXPIRED） | 0 | CLEAN |
| evid-source-hash | 1 | HIT（SOURCE_SHA256_MISMATCH/APPROVAL_STALE） | 0 | CLEAN |
| free-macro-double-sign | 1 | HIT（NUMERIC_MACRO_DOUBLE_SIGN） | 0 | CLEAN |
| free-missing-root | 2 | HIT（缺起点 exit 2） | 0 | CLEAN |
| num-marker-mismatch | 1 | HIT（BOUND_MISMATCH/ASSERTION_DRIFT） | 0 | CLEAN |
| num-unmarked | 1 | HIT（UNBOUND_NUMBER/ASSERTION_DRIFT） | 0 | CLEAN |
| tex-computed-value | 1 | HIT（ARITH_IN_BODY/NUMERIC_IN_MACRO） | 0 | CLEAN |
| tex-macro-shape | 1 | HIT（NUMERIC_MACRO_SHAPE_INVALID） | 0 | CLEAN |

**合计：invalid 命中 10/12（MISS 2、WRONG-CODE 0）；valid 干净 12/12（FALSE-RED 0）。**

两个 MISS 是检测缺口，不是 schema 缺口：

1. `assert-role-moved`：值不变、整句从 Results 搬到 Discussion，fact 声明
   `role="results"`。现实现没有「role ↔ 章节标题」的判据（S-03 把 role 放进
   approve_target，但源层未比对章节）；按纪律不在本批临时造码。
2. `cite-no-stable-id`：被 `\cite` 的 bib entry 缺 DOI/eprint/URL。V3.0 §8
   只列「新增/改级」code，V2.2 §19.2 的引用缺稳定标识码未随本件给出；
   出题人也因此写 `codes: []`。需要先补 code 才能判红。

同轮全量（holdout1–4）复跑：hostile HIT 30/32、MISS 2、WRONG-CODE 0；
benign CLEAN 32/32、FALSE-RED 0（本轮修掉的 3 个误红全部来自 holdout4 的
`numeric_macro_allow` 模板转义差异）。

## 六、验收

```bash
cd paperkit-dev
python3 -m unittest discover -s tests          # 184 tests, OK
python3 /tmp/blind_eval.py | tail -8           # holdout1-4 聚合
python3 /tmp/holdout4_only.py                  # 只统计 holdout4
```

- 单测：**184/184 通过**。
- holdout4：**invalid 10/12 命中；valid 12/12 干净**。
- 无硬编码盲测项目名；未读/未改 `/tmp/holdout4`（只读挂载）。
