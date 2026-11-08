# CODES-AND-CHAIN｜批 56：错误码表冻结 + 证据链完整性

> 日期：2026-11-08
> 对应规范：`docs/design/SPEC-V3.0.md` §8（错误码总表）、§11.6（证据链）、§11.4（退出码）。
> 对应盲测：#5 首跑 8/12（valid 12/12 零误红）。本轮补 3 处码表缺口 + 1 处真漏判。
> 纪律：**#5 已被读过，仅作诊断，不作盲测结论**。本报告不把 #5 读数当发布依据。

## 0. 结论（先看这里）

| 事项 | 结果 |
|---|---|
| 错误码表是否并入 §8 | **是**。V2.2 §19.2 全部旧码 + V3.0/§11 全部码 + 本批新增码，一张表逐条列全（码名/含义/触发/severity/exit） |
| 新增专属码 | `COMPUTED_VALUE_UNREGISTERED`、`NUMBER_AS_CROSSREF`、`EVIDENCE_CHAIN_BROKEN`；`FACT_SCHEMA_INVALID` 固定 exit 2 |
| 旧码合并 | `MATH_FRAC_UNVERIFIABLE`→`COMPUTED_VALUE_UNREGISTERED`；`FACT_EVIDENCE_MISSING`→`EVIDENCE_CHAIN_BROKEN`；`UNBOUND_QUANT`→`UNBOUND_NUMBER`；`FACT_UNKNOWN_ID`→`UNKNOWN_FACT_MARKER` |
| 证据链判据 | **已落地**（§11.6）；三节任一断开即红；benign 1 例 + hostile 7 例（含断在每一节） |
| 单测 | **194 例全绿**（既有 184 + 新增 10） |
| 回归线 `fixtures/regression/paper-en` | **0 红**（28 个 fixture 测试全绿） |
| #5 诊断（原始只读集） | invalid：0 放行、9/12 命中旧 EXPECT、3 个旧码名不符；valid：12/12 因缺 `record.json` 被新链判红（#5 早于 §11.6） |
| #5 诊断（补回执的临时副本） | invalid：9/12 命中旧 EXPECT、0 放行、3 个旧码名不符；valid：**12/12 干净** |

## 1. 码表 diff

完整表见 `docs/design/SPEC-V3.0.md` §8（§8.1 核心码、§8.2 V2.2 沿用码、§8.3 diff、§8.4 唯一映射）。
这里只列本轮改动。

### 1.1 新增（3 个专属码）

| code | 含义 | 触发条件 | severity | exit |
|---|---|---|---|---|
| `COMPUTED_VALUE_UNREGISTERED` | 现场计算生成且未登记的数字 | `\frac/\dfrac/\tfrac/\numexpr/\dimexpr/\inteval` 产生的 token；`\frac` 未在该行 `frac_allow` 登记 | red | 1 |
| `NUMBER_AS_CROSSREF` | 手写结构编号当数据 | `Table/Figure/Section/Eq./Algorithm/Appendix` 等后跟字面数字，且未用 `\ref` | yellow | 3 |
| `EVIDENCE_CHAIN_BROKEN` | 证据链断节 | `source`／运行记录／`source_sha256`／`record.json`／回执 `facts[]` 任一节断开（更具体码优先） | red | 1 |

### 1.2 固定/改名/合并

| 处理 | 旧/新 | 说明 |
|---|---|---|
| 固定 | `FACT_SCHEMA_INVALID` | 未知 facts `schema`（含 `2.9` 降级）固定 **exit 2（CONFIG）**，不是 3；并写进 `--json.findings` |
| 改名 | `MATH_FRAC_UNVERIFIABLE` → `COMPUTED_VALUE_UNREGISTERED` | `\frac` 与 `\numexpr` 统一口径；旧码不再发射 |
| 改名 | `FACT_EVIDENCE_MISSING` → `EVIDENCE_CHAIN_BROKEN` | 证据缺失从黄（3）升红（1）：链断即红 |
| 合并 | `UNBOUND_QUANT` → `UNBOUND_NUMBER` | 同一现象只保留一个码 |
| 合并 | `FACT_UNKNOWN_ID` → `UNKNOWN_FACT_MARKER` | 同一现象只保留一个码 |
| 沿用 | `UNKNOWN_FACT_MARKER` | `\fact{A9}` 指向账上不存在的 id；已有码继续用 |
| 删除 | `LEDGER_TEXT_COCHANGE` | V3.0 §1.2 M2 整条删除 |
| 删除 | `STAMP_UNVERIFIED` | 拆成具体 `STAMP_*` 码 |

### 1.3 唯一映射检查

判卷只看 §8.4 的「现象 → 唯一 code」表。关键几条：

| 现象 | 唯一 code |
|---|---|
| 未知 facts `schema` | `FACT_SCHEMA_INVALID`（exit 2） |
| `\frac`/`\numexpr` 未登记 | `COMPUTED_VALUE_UNREGISTERED` |
| 手写 `Table 3` 当数据 | `NUMBER_AS_CROSSREF` |
| `\fact{A9}` 指向不存在 id | `UNKNOWN_FACT_MARKER` |
| 无 source/observation | `EVIDENCE_CHAIN_BROKEN` |
| source 文件不存在 | `MISSING_SOURCE` |
| source 哈希不符 | `SOURCE_SHA256_MISMATCH` |
| 缺 `record.json`／run_id 不符／`facts[]` 不含本 fact | `EVIDENCE_CHAIN_BROKEN` |
| 回执指向账上不存在的 id | `EVIDENCE_CHAIN_BROKEN` |

「更具体码优先」是唯一映射的实现规则：链的某节已有更具体码（`MISSING_SOURCE`、`SOURCE_SHA256_MISMATCH`）时不再叠出 `EVIDENCE_CHAIN_BROKEN`，避免一个现象两个码。

## 2. 证据链完整性（§11.6）

### 2.1 定义

```
facts.source ──①──> runs/ 里的运行记录 ──②──> 回执 runs/<run_id>/record.json ──③──> 账上的 fact id
```

| 节 | 检查 | 通过条件 | 断开的码 |
|---|---|---|---|
| ① 指针 | `facts.source` 非空，解析后是 `runs/` 下的普通文件 | 文件存在 | 无 source/observation → `EVIDENCE_CHAIN_BROKEN`；文件不存在 → `MISSING_SOURCE` |
| ② 内容锚 | `source_sha256` 与文件现算 sha256 相等 | 64 位 hex 相同（忽略 `sha256:` 前缀） | 缺 sha → `EVIDENCE_CHAIN_BROKEN`；值不符 → `SOURCE_SHA256_MISMATCH` |
| ③ 回执 | 与运行记录同目录的 `record.json` 存在、可解析、`run_id` 对齐、`facts[]` 含本 fact id | 全部成立 | `EVIDENCE_CHAIN_BROKEN` |

`record.json` 唯一规范形态：

```json
{
  "run_id": "run-01",
  "source": "runs/run-01/result.json",
  "source_sha256": "sha256:...",
  "facts": ["A1", "A2"]
}
```

反向指针：`record.json` 的 `facts[]` 里列出的每个 id 必须在账上存在；悬空即 `EVIDENCE_CHAIN_BROKEN`。

### 2.2 实现位置

- `factscribe/audit.py::verify_sources()` → `_evidence_chain_issues()`（v3 才调用）。
- `record.json` 与运行记录**同目录**，因此 `runs/run-01/result.json` → `runs/run-01/record.json`。
- v1 不受影响：仍走 `results/` + `MANIFEST.toml`。
- `l0/l1` 也执行（源层就能断链），不等到 L2。

### 2.3 正负测试

新文件 `tests/test_evidence_chain.py`（10 例）：

| 用例 | 期望 |
|---|---|
| 链完整（benign） | exit 0，无 finding |
| 断①：无 source/observation | exit 1，`EVIDENCE_CHAIN_BROKEN` |
| 断①：source 文件不存在 | exit 1，`MISSING_SOURCE` |
| 断②：哈希不符 | exit 1，`SOURCE_SHA256_MISMATCH` |
| 断③：缺 `record.json` | exit 1，`EVIDENCE_CHAIN_BROKEN` |
| 断③：`facts[]` 不含本 fact | exit 1，`EVIDENCE_CHAIN_BROKEN` |
| 断③：回执 run_id 不符 | exit 1，`EVIDENCE_CHAIN_BROKEN` |
| `\frac` 未登记 | exit 1，`COMPUTED_VALUE_UNREGISTERED` |
| 手写 `Table 3` | exit 3，`NUMBER_AS_CROSSREF` |
| 未知 facts schema | exit 2，`FACT_SCHEMA_INVALID` 出现在 findings |

## 3. #5 诊断

> **#5 已被读过，仅作诊断，不作盲测结论。** 下列读数只用于定位本轮改动的效果，不能当作发布命中率。

### 3.1 原始只读集 `/tmp/holdout5`（未改一字节）

| family | kind | exit | 判定 | 关键 code |
|---|---|---:|---|---|
| assertion-appendix-orphan | invalid | 1 | HIT | `EVIDENCE_CHAIN_BROKEN`, `UNBOUND_NUMBER` |
| assertion-appendix-orphan | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN`（缺回执） |
| assertion-context-swap | invalid | 1 | HIT | `BOUND_MISMATCH`, `ASSERTION_DRIFT` |
| assertion-context-swap | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |
| binding-bare-number | invalid | 1 | HIT | `UNBOUND_NUMBER` |
| binding-bare-number | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |
| binding-rounding-tolerance | invalid | 1 | HIT | `DISPLAY_INCONSISTENT`, `ASSERTION_DRIFT` |
| binding-rounding-tolerance | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |
| cite-number-as-data | invalid | 1 | 旧码名不符 | `NUMBER_AS_CROSSREF`（旧 EXPECT 写 `UNBOUND_NUMBER`） |
| cite-number-as-data | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |
| evidence-chain-missing | invalid | 1 | 旧码名不符 | `EVIDENCE_CHAIN_BROKEN`（旧 EXPECT 写 `FACT_EVIDENCE_MISSING`） |
| evidence-chain-missing | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |
| evidence-source-tampered | invalid | 1 | HIT | `SOURCE_SHA256_MISMATCH` |
| evidence-source-tampered | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |
| free-duplicate-id | invalid | 1 | HIT | `DUPLICATE_ID` |
| free-duplicate-id | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |
| free-schema-downgrade | invalid | 2 | HIT | `FACT_SCHEMA_INVALID`（本轮修好：进 findings） |
| free-schema-downgrade | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |
| ref-unknown-fact-key | invalid | 1 | HIT | `UNKNOWN_FACT_MARKER` |
| ref-unknown-fact-key | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |
| tex-frac-computed | invalid | 1 | 旧码名不符 | `COMPUTED_VALUE_UNREGISTERED`（旧 EXPECT 写 `MATH_FRAC_UNVERIFIABLE`） |
| tex-frac-computed | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |
| tex-macro-carrier | invalid | 1 | HIT | `NUMERIC_MACRO_SHAPE_INVALID` |
| tex-macro-carrier | valid | 1 | FALSE-RED | `EVIDENCE_CHAIN_BROKEN` |

**汇总（原始 #5）**：

- invalid：**0 放行**；按旧 EXPECT 字面比对 **9/12 命中 + 3 个旧码名不符**。
- 3 个「不符」全部是本轮按新码表改名的结果：
  - `cite-number-as-data`：旧 `UNBOUND_NUMBER` → 新 `NUMBER_AS_CROSSREF`；
  - `evidence-chain-missing`：旧 `FACT_EVIDENCE_MISSING`（黄 3）→ 新 `EVIDENCE_CHAIN_BROKEN`（红 1）；
  - `tex-frac-computed`：旧 `MATH_FRAC_UNVERIFIABLE` → 新 `COMPUTED_VALUE_UNREGISTERED`。
- valid：12/12 被 `EVIDENCE_CHAIN_BROKEN` 判红。原因不是判据误报，而是 **#5 生成时还没有 §11.6，所有项目都没有 `record.json`**。

### 3.2 补回执的临时副本 `/tmp/holdout5-with-records`（隔离链变量）

为确认 valid 全红只由「缺回执」造成，把 #5 复制到临时目录（原集不动），按每个运行记录补出同目录 `record.json`（`run_id`、`source`、`source_sha256`、`facts[]` 均按实际文件生成），再跑同一实现：

| 指标 | 读数 |
|---|---|
| invalid 放行 | **0/12** |
| invalid 按旧 EXPECT 命中 | **9/12** |
| invalid 旧码名不符 | 3/12（同上三条，纯码表改名） |
| valid 干净 | **12/12** |
| valid 误红 | **0/12** |

结论：新链判据本身没有把 benign 判红；原始 #5 的 12 个 valid 全红是「旧题缺回执」，补上回执即恢复 12/12 干净。下一轮盲测出题必须按 §11.6 带 `record.json`。

## 4. 复现命令

```bash
cd /Users/moc/workspaces/SiAgent/paperkit-dev

# 单测（194 例）
python3 -m unittest discover -s tests

# 夹具/回归线（paper-en 0 红）
python3 -m unittest discover -s tests -p 'test_fixtures.py'

# #5 诊断（只读原集；结果见 §3.1）
python3 - <<'PY'
import json, subprocess, sys
from pathlib import Path
ROOT = Path('/Users/moc/workspaces/SiAgent/paperkit-dev')
for fam in sorted(p for p in Path('/tmp/holdout5').iterdir() if p.is_dir()):
    for kind in ('invalid', 'valid'):
        proj = fam / kind
        if not proj.is_dir():
            continue
        p = subprocess.run([sys.executable, '-m', 'factscribe', 'audit', str(proj), '--json'],
                           cwd=ROOT, capture_output=True, text=True)
        data = json.loads(p.stdout or '{}')
        codes = [f.get('code') for f in data.get('findings', [])]
        print(fam.name, kind, p.returncode, codes)
PY
```

## 5. 残余与下一轮

1. `record.json` 是新增约定；旧项目（含 #5）需要补回执，否则 v3 会红。这是有意的制动，不提供静默豁免。
2. `NUMBER_AS_CROSSREF` 目前是黄（3）：它表示「手写结构编号，不是数据，也不能替代 `\ref`」。如果下一轮要求把它升红，只改 §8.1 的 severity/exit，不改判据。
3. `FACT_SCHEMA_INVALID` 固定 exit 2；`--json.findings` 已同步，判卷器不再只读顶层 `code`。
4. 盲测纪律不变：#5 已被读过，只能作诊断；发布结论必须用新生成、未读过的盲测集。
