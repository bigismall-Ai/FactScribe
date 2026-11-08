# KNOWN GAPS — v1.2.0（盲测冻结时的如实清单）

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

## 二、#9 暴露的已知缺口（不修，如实记）

| 缺口 | 现象 | 影响 | 计划 |
|---|---|---|---|
| `free-derived-expr` | 派生 fact 的 `expr` 与实际值不符时未判红 | 可能放行“算错但自洽”的派生数 | v1.3 |
| `tex-input-dynamic` | `\input{\macro}` 动态目标未被判红 | 可绕过文件闭包 | v1.3 |
| `num-bind-mismatch` | 判红但码为 `UNMATCHED_NUMBER`，非 `BOUND_MISMATCH` | 分诊不便，不误判 | v1.3（码表细化） |

## 三、结构性与已知边界（不打算修）

1. **信任根是人签**：若 agent 同时伪造 `runs/` 与 `facts/`，工具无法发现——只能保证“账、据、文自洽且据未被改”。
2. **强隔离做不到**：出题人与实现方同机，盲测属“弱盲测”（靠纪律，不靠权限）。
3. **PDF 回检依赖 poppler**：缺 `pdftotext` 时明确 `PDF_TOOL_MISSING`（exit 8），不静默放行。
4. **不做 OCR**：图片承载定量一律红，把问题挡在源头。

## 四、判据覆盖面（已实现，供对照）

数字绑定（`UNBOUND_NUMBER`/`BOUND_MISMATCH`/`BINDING_ATTRIBUTION`/`DISPLAY_INCONSISTENT`）、
证据链（`EVIDENCE_CHAIN_BROKEN`/`SOURCE_SHA256_MISMATCH`/`APPROVAL_STALE`）、
TeX 结构（`NUMERIC_IN_MACRO`/`COMPUTED_VALUE_UNREGISTERED`/`INPUT_TARGET_MISSING`）、
断言位置（`FACT_OUT_OF_SPAN`/`FACT_UNUSED_IN_SPAN`/`ASSERTION_DRIFT`）、
引用与常量（`MISSING_CITE`/`UNUSED_BIB`/`NUMBER_AS_CROSSREF`/`UNKNOWN_FACT_MARKER`）、
PDF/stamp（`PDF_PAGE_NO_TEXT`/`PDF_PAGE_RASTERIZED`/`PDF_LEDGER_TOKEN_MISSING`/`PDF_UNACCOUNTED_NUMBER`/`STAMP_KEY_UNTRUSTED`）。
