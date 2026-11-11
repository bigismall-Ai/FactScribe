# KNOWN GAPS — v1.2.0 盲测冻结清单（v1.3.0 已修三条）

> 依据：三套**真盲**测（#7/#8/#9，出完即跑、不返工）。
> 判读规则（预注册）：invalid 命中 ≥10/12 且 valid 零误红。

## 一、盲测读数

| 集 | 封存哈希（前16） | 首跑命中 | valid 误红 | 结论 |
|---|---|---|---|---|
| #7 | `944f81279520ca6f` | **11/12** | 0/12 | 过线 |
| #8 | `47ed0da6d4e93fd3` | **10/12** | 0/12 | 过线 |
| #9 | `1939c2f929c6f846` | **9/12** | 0/12 | **未过线** |
| 合计 | — | **30/36（83%）** | **0/36** | 三套里两套过线 |

**停止线**：预注册「最多 #8/#9 两套」，已用完；此后冻结，不再对着盲测调参。

## 二、#9 暴露的已知缺口（v1.3 已修）

| 缺口 | v1.2 现象 | v1.3 修复 | 错误码 | 落点 |
|---|---|---|---|---|
| `tex-input-dynamic` | `\input{\macro}` / `\input{\jobname}` 动态目标未被判红，可绕过文件闭包 | 目标含宏、`#`、嵌套花括号或为空 → 红（fail-closed）；静态目标行为不变 | `INPUT_DYNAMIC`（红/5） | `factscribe/config.py` `_input_refs` / `_dynamic_ref_reason`；`factscribe/audit.py` `run_audit` |
| `free-derived-expr` | 派生 fact 的 `expr` 与实际值不符时 `audit` 未判红（只有 `check` 判） | `audit` 也按既有数值口径求值比对；报两侧数值与误差；可写 `expr_tolerance` 显式容差 | `EXPR_MISMATCH`（红/1）；expr 不可求值仍 `EXPR_INVALID` | `factscribe/audit.py` `_expr_issues`（`check`/`audit` 共用） |
| `num-bind-mismatch` | 已绑定但数值对不上时报 `UNMATCHED_NUMBER`，语义错位 | 该行已绑定定量 fact → `BOUND_MISMATCH`；真的无 fact 可命中才 `UNMATCHED_NUMBER`；红/黄级别与退出码不变 | `BOUND_MISMATCH`（红/1） / `UNMATCHED_NUMBER`（红/1） | `factscribe/audit.py` `run_audit` 的未分组数字分诊 |

**验证**：`tests/test_audit_gaps.py`（25 例）锁三条判据的正负例、`examples/minimal`
恰好两红、新码 JSON 字段稳定，以及旧码 `UNMATCHED_NUMBER` 不再用于“绑定后不符”。
实现记录见 `docs/implementation/AUDIT-GAPS.md`。

## 三、结构性与已知边界（不打算修）

1. **信任根是人签**：若 agent 同时伪造 `runs/` 与 `facts/`，工具无法发现——只能保证“账、据、文自洽且据未被改”。
2. **强隔离做不到**：出题人与实现方同机，盲测属“弱盲测”（靠纪律，不靠权限）。
3. **PDF 回检依赖 poppler**：缺 `pdftotext` 时明确 `PDF_TOOL_MISSING`（exit 8），不静默放行。
   **CI 不验证 PDF 层**：GitHub runner 装不上 poppler（apt 镜像连不上），workflow 里装 poppler 是「尽力而为」，
   装不上则 PDF 层 31 例自动跳过（`tests/_pdfdep.py` 的 `requires_pdftotext`，输出带 `skipped=`）、其余照跑；
   本机 `./scripts/preflight-ci.sh` 覆盖全量（有 poppler 时 `skipped=0`）。
4. **不做 OCR**：图片承载定量一律红，把问题挡在源头。

## 四、判据覆盖面（已实现，供对照）

数字绑定（`UNBOUND_NUMBER`/`BOUND_MISMATCH`/`BINDING_ATTRIBUTION`/`DISPLAY_INCONSISTENT`）、
证据链（`EVIDENCE_CHAIN_BROKEN`/`SOURCE_SHA256_MISMATCH`/`APPROVAL_STALE`）、
TeX 结构（`NUMERIC_IN_MACRO`/`COMPUTED_VALUE_UNREGISTERED`/`INPUT_TARGET_MISSING`/`INPUT_DYNAMIC`）、
派生算式（`EXPR_MISMATCH`/`EXPR_INVALID`）、
断言位置（`FACT_OUT_OF_SPAN`/`FACT_UNUSED_IN_SPAN`/`ASSERTION_DRIFT`）、
引用与常量（`MISSING_CITE`/`UNUSED_BIB`/`NUMBER_AS_CROSSREF`/`UNKNOWN_FACT_MARKER`）、
PDF/stamp（`PDF_PAGE_NO_TEXT`/`PDF_PAGE_RASTERIZED`/`PDF_LEDGER_TOKEN_MISSING`/`PDF_UNACCOUNTED_NUMBER`/`STAMP_KEY_UNTRUSTED`）。
