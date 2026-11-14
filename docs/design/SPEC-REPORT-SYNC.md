# SPEC-REPORT-SYNC：实验报告归一化与事实账同步（v1）

日期：2026-11-14　　状态：设计定稿（红蓝对抗 2 轮 + 圆桌裁决）

目标：让论文里的每个数字，从「人抄进事实账」变成「机器从实验报告里取、再对回原始产物」，
并且把「账抄错」这一类当前闸门抓不到的错误挡住。

## 1. 三层链条

```
原始产物（日志 / JSONL / CSV）
   ↓ 探针（机械取数）
report.toml（归一化报告，带定位与哈希）
   ↓ 人签收一次（审阅卡）
facts/*.toml（事实账，导入生成，不手抄）
   ↓ \fact{id}
论文正文
```

每一层都能回退到上一层；哪一层变了，上一层立刻报出来。

## 2. 目录

```
<workspace>/                     # 工作区根：论文与实验的公共父目录
├─ factscribe.workspace.toml     # 可选标记：id、experiments_root
├─ paper/
│  ├─ paperkit.toml              # 既有字段 + source_root（指工作区根）
│  ├─ sections/*.tex
│  └─ facts/
│     ├─ <legacy>.toml           # 旧账不动
│     └─ <report_id>.toml        # 导入产物（glob 可见）
└─ experiments/<exp>/
   ├─ raw/run-YYYY-MM-DD/…       # 原始产物，只读
   └─ reports/
      ├─ <ID>.report.toml
      ├─ <ID>.lock.json
      ├─ <ID>.signoff.toml
      └─ <ID>.signoff.log        # append-only 签收流水
```

导入产物必须写进 `facts/*.toml`（一级），不能放子目录——现有事实账只读一级 glob。

## 3. `report.toml`

`schema = "factscribe/report@1"`

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema` | ✔ | 固定串 |
| `id` | ✔ | 报告 id，`[A-Za-z0-9._-]`，禁 `..` |
| `status` | ✔ | `final` / `partial` / `superseded` |
| `generated_at` | ✔ | ISO8601，不进摘要 |
| `generator` | ✔ | `kind/name/version/argv/script_sha256` |
| `population.id` | ✔ | 同报告共享；`filter` 推迟 P1 |
| `metrics[]` | ✔ | 指标数组 |
| `metrics[].id` | ✔ | 报告内唯一 |
| `metrics[].value` | ✔ | 规范形式：count 写整数；ratio 写 `"n/d"`；percent 写 0–100 |
| `metrics[].value_type` | ✔ | `count` / `ratio` / `percent` / `float` |
| `metrics[].precision` | ✔（percent/float） | 十进制位 |
| `metrics[].sources[]` | ✔ | 按 value_type 的必需集合 |
| `sources[].role` | ✔ | `value` / `numerator` / `denominator` / `cross_check` |
| `sources[].probe` | ✔ | 内置 `jsonl.count` / `jsonl.count_where` / `csv.cell` |
| `sources[].path` | ✔ | 工作区相对路径 |
| `sources[].locator` | ✔ | 单一规范定位串（探针 + 参数 + 定位） |
| `sources[].kind` | ✔ | `machine` / `human_text`（后者只能 cross_check） |

必需 source 集合：

- `count` → `role=value` 一条；
- `ratio` → `numerator` + `denominator` 各一条（没有 value 源）；
- `percent` / `float` → `role=value` 一条。

值比较走有理数，不走浮点。

## 4. 锁文件 `<ID>.lock.json`

字段：`schema`、`report_id`、`report_sha256`、`workspace_id`、`locked_at`、
`inputs[]{path,sha256,size,role}`、`semantic_digest`、`evidence_digest`、
`probe_results[]{probe,impl_sha256,locator,value,intermediate_counts}`。

写完即冻结；机器逐项复算，任何一项对不上就红。

## 5. 签收

`report sign` 渲染一张 6 行审阅卡：

1. 指标名；2. 值；3. 来源文件与定位；4. 口径一句话；5. 中间计数；6. 人要回答的一个问题。

签的是 `card_digest` + `semantic_digest` + `evidence_digest` + `lock_sha256` + `probe_impl_digest`，
不是文件名。签收记录 append-only，改报告只追加新条目。

身份分离的边界：agent 有 shell 就无法机械区分人签与 agent 签。v1 只提供
「提高伪造成本 + 全程留痕」，不作密码学保证。

## 6. 命令

| 命令 | 语义 | 退出码 |
|---|---|---|
| `report check <ws> [--report <p>]` | 报告域 R1–R8 | 0/1/2 |
| `report lock <ws> --report <p>` | 写锁文件 | 0/1/2 |
| `report sign <ws> --report <p> [--by <u>]` | 审阅卡 + 签收；无 TTY → 2 | 0/1/2 |
| `fact import <ws> --report <p> [--dry-run]` | 带签收门，写 `facts/<report_id>.toml` | 0/1/2 |
| `audit <project>` | 账域 R9–R16 + 覆盖率 | 0/1/2/5/7/8 |

缺工作区：`report` / `fact` → 2；`audit` → 0，但 JSON 必带 `provenance_coverage`
与 `advisory_gaps`。

## 7. 校验规则

| 编号 | 规则 | 级别 |
|---|---|---|
| R1 | 必填字段、枚举、schema | 红 1 |
| R2 | metric id 唯一 + 白名单 | 红 1 |
| R3 | 值规范与 value_type 一致 | 红 1 |
| R4 | 路径安全（工作区内、拒 symlink、超限报错） | 红 1 |
| R5 | 探针重算 == value（±1 末位） | 红 1 |
| R6 | 必需 source 集合齐备，每 role 恰一主源 | 红 1 |
| R7 | 锁与磁盘一致（报告哈希 / 输入哈希 / evidence_digest） | 红 1 |
| R8 | 摘要完备性：三摘要重算一致 | 红 1 |
| R9 | 被正文引用的 fact，其报告签收有效 | 红 5 |
| R10 | 报告 status：partial → 黄，superseded → 红 | 黄 / 红 5 |
| R11 | 导入事实 value == metric.value；raw 哈希 == 磁盘 | 红 1 |
| R12 | 内容锚：带 probe 的由 R5 替代字面回查；旧事实不变 | 红 1 |
| R13 | 派生事实：上游须 imported 且带 report/metric；上游变则 stale | 红 7 |
| R14 | 重复 fact id（大小写不敏感） | 红 1 |
| R15 | 溯源覆盖：required 下含数字事实缺 report/metric | 红 5 |
| R16 | advisory：cross_check 不符、partial 被引、人工溯源 | 黄 |
| R17 | 来源归属：导入事实的 source 必须是该指标声明的某个来源文件 | 红 1 |

## 8. 兼容

- 旧 `facts/*.toml` 不加新字段照常审计；新字段一律可选；
- 导入事实的 id 为 `<report_id>.<metric_id>`（点号在 v1/v3 的 id 规则里都合法）；
- `source` 仍指向原始产物，报告引用放新字段；
- 未配 `source_root` 的项目行为不变。

## 9. 分期

- **P0**：工作区与路径口径 → schema → 3 个探针 → check / lock / sign → import（带门）
  → audit 扩展 R9/R11/R14/R15 → 退出码与 JSON 契约；
- **P1**：population.filter、runs/missing/stale、派生事实收口、另 4 个探针、human_text 降级；
- **P2**：自定义探针作主源（逐报告绑实现哈希 + 签收）、raw 清单、探针缓存；
- **P3**：归档包、论文侧 diff、报告 diff。

## 10. 明确不解决

1. 密码学级人机不可伪造的签收；
2. 原始产物由谁跑、是否跑全（只验哈希与重算，不验出处）；
3. 跨报告口径一致性；
4. 存量账自动迁移；
5. percent/float 进 expr 派生（v1 禁止）；
6. 人工转录数值（人只确认指针）；
7. 自定义脚本作主来源（只作 cross_check，进 advisory）；
8. 报告/论文 diff 与归档实现（P3）；
9. 多个 run 合并产物的 denominator（v1 要求单一合并产物）；
10. 截图 / 自由文本日志的自动解析。

## 11. 验收（机械可执行）

- A1 缺字段 / 枚举越界 / 重复 metric id → `report check` 退出 1；
- A2 改 value 不改源 → R5 红；
- A3 改 locator → R8 红且 import 退出 1；
- A4 删 signoff → import 退出 1、audit 退出 5；
- A5 篡改 raw 一行 → R7 红；
- A6 改导入事实的 source_sha256 → R11 红；
- A7 两报告同 metric_id → 导入后 id 带前缀，重复即 R14 红；
- A8 导入后账本条数恰 +1（证明 glob 可见）；
- A9 正文有未绑 fact 的数字 → 覆盖率下降，required 模式退出 5；
- A10 上游值改动 → R13 红且码 7；
- A11 扰动测试：逐字段改动，凡影响输出者必须改变对应 digest；
- A12 新子命令退出码只 ∈ {0,1,2}；无 TTY 的 sign → 2；
- A13 缺工作区：report/fact → 2；audit → 0 且 JSON 带覆盖率字段；
- A14 回归：旧账不加新字段仍可 audit，现有全部测试绿；
- A15 探针边界：JSONL 空行、解析失败、CSV 表头缺失/多命中都按红处理。

---

## 12. v1.1 自审修订（红蓝对抗，第二轮）

自审时发现前一版有三处结构性错误，本节**优先于上文**。

### 12.1 不另起一套证据链，接入已有 v3 链

仓库里已经有 v3 证据链（`SPEC-V3.0 §11.6`）：

- fact 的 `observation = {run_id, pointer}`；
- 运行目录里的 `record.json`（`run_id` + `source` + `source_sha256` + `facts[]`）；
- 审计码 `EVIDENCE_CHAIN_BROKEN`。

原方案另造 `report/lock/signoff` 三件套，会出现两套真相。修订：

- `report.toml` 的定位直接用 `observation.pointer`（JSON Pointer），不新造 `locator` 语法；
- `report lock` 产出/校验运行目录的 `record.json`，而不是平行的锁文件；
- 签收信息进 `record.json` 的可选块 `approval`（`card_digest` / `signed_by` / `signed_at` / `probe_impl_digest`），
  旧回执照常通过（缺 `approval` 不等红，只降级为 advisory）。

### 12.2 不碰现有 `metric` 字段

`metric` 已参与 `DUPLICATE_VALUE` 的冲突分组（`(metric, scope)`）。导入事实若复用，
会把不同报告的指标混进同一组。修订：新增可选字段 **`report_metric`**，`metric` 语义一字不动。

### 12.3 定位必须可复核，不能只给行号

- 探针定位优先语义锚：JSON Pointer、CSV「表头列名 + 行键」；
- 行号只作辅助，必须与 `source_sha256` 同时存在才有效；
- 审阅卡必须显示：探针名、定位表达式、**命中行数 / 总行数 / 未命中原因**、定位处 **±5 行原文**；
- 禁止没有中间计数的 `count_where`：写不出「总行数、命中数、过滤条件」的定位直接红。

### 12.4 摘要规范化（digest@1）

- 只对显式列出的字段做摘要，按字段名排序；
- 字符串 NFC 归一；路径统一 POSIX 相对、大小写敏感；
- **禁止浮点进摘要**：数值一律用规范化十进制字符串；
- 摘要算法与字段表带版本号，仓库内放固定测试向量（同输入必同摘要）。

### 12.5 签收与导入

- 只有 `status = "final"` 的报告可导入；`partial` 只允许 `--dry-run`；
- `record.json` 的 `approval` 必须存在且 `card_digest` 与当前卡片一致，否则 `fact import` 退出 1；
- 签收流水按 `prev_sha256` 串成哈希链，允许截断检测；
- `report sign --card-out <file>` 供无 TTY 环境（网页、CI）使用；网页里由人点击确认；
- 身份边界仍如实写明：有 shell 的 agent 技术上可伪造，v1 只提高成本与留痕。

### 12.6 导入落地

- 报告命名空间：`<experiment>.<report_id>`，避免不同实验同名报告互撞；
- 导入写 `facts/<experiment>.<report_id>.toml`，文件首行写托管标记与来源报告摘要；
- 重申：只写 `facts/*.toml` 一级，子目录现有 glob 看不见；
- 重导入幂等：内容一致则不动；文件被手改过（与上次导入记录不符）则拒绝并提示；
- 原子替换（临时文件 + rename）。

### 12.7 值的两种形态

- 报告里 `value` 是规范形（`ratio` 写 `n/d`，`percent` 写 0–100）；
- 新增必填 `display`：论文里真正显示的字符串（如 `62.5\%`）；
- 导入时账的 `value` 取 `display`，数值比较用规范形；
- 0 分母、千分位、BOM、CRLF 一律按红处理，不做猜测。

### 12.8 性能与边界

- 单文件上限 2 GiB，超限报错不截断；哈希流式计算；
- 探针结果按 `文件哈希 + 探针名 + 实现哈希 + 定位` 缓存（P1）；
- 多 run 取平均在 v1 仍不支持：要求先合并成单一产物；P2 用 `runs[]` + 明确聚合规则解决。

### 12.9 修订后的 P0 范围

1. `observation.pointer` 机器校验（JSON / JSONL）；
2. CSV 单元探针（表头 + 行键）；
3. `record.json` 生成与校验（复用 v3 链）；
4. `report check` / `report lock` / `report sign --card-out` / `fact import`；
5. 审计新增：引用事实的 `approval` 有效性、`report_metric` 重复、导入值与报告一致、覆盖率（默认 advisory）。

多 run 平均、自定义探针、归档打包、论文 diff 全部推后。


---

## 13. P0 实现状态（2026-11-14）

已落地（`factscribe/report.py` + CLI + 审计接入，测试见 `tests/test_report_core.py`、
`tests/test_report_cli.py`）：

- `report check` / `report lock` / `report sign --card-out` / `fact import`；
- 4 个探针：`jsonl.count`、`jsonl.count_where`、`csv.cell`、`json.pointer`；
- digest@1、锁文件、签收卡片、哈希链流水；
- 导入事实（`report` / `report_metric` 可选字段，旧账零变化）；
- 审计规则：`REPORT_MISSING` / `REPORT_METRIC_MISSING` / `REPORT_NOT_SIGNED` /
  `REPORT_METRIC_MISMATCH` / `REPORT_SOURCE_MISMATCH`；
- 审阅卡不截断；`--card-out` 只能写工作区内。

与本节前面设计的偏差（P0 暂缓，不是取消）：

1. 尚未生成/复用 v3 的 `record.json`：P0 用报告同目录的 `<ID>.lock.json`，
   v3 证据链对齐放到 P1；
2. `provenance_coverage`（R15）未实现，P1；
3. `partial` 目前只允许 `--dry-run`（已实现为硬门），报告状态机仍按 R10 设计；
4. 报告改动后要先删旧锁与签收才能重签，尚未提供一条命令完成；
5. 多 run 平均、自定义探针、归档、论文 diff：按 §9 分期。


## 14. P0.5 工作台界面（2026-11-14）

- `GET /api/reports`：列出工作区里的报告、状态、是否封存/签收；
- `POST /api/reports/action`：`check` / `lock` / `sign` / `import`；写动作要 `--allow-write`；
- MiniApp 经 Node 代理 `/api/workbench/reports`；
- 工作台页签新增「实验报告」块：报告下拉、四个按钮、签收人输入、审阅卡逐行显示；
  只读服务禁用写动作并说明原因；签收不替用户填名字；
- 报告仍由脚本或 agent 编写，界面不提供新建/编辑。
