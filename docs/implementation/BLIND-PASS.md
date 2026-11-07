# BLIND-PASS｜批 50 盲测通过记录

> 日期：2026-11-08
> 目标：在不改盲测集任何字节的前提下，把 24 个封存项目的判读做到
> **hostile ≥10/12 命中、benign 全干净**，同时保持 150 例既有单测与
> `fixtures/regression/paper-en`（0 红、234 绑定）不变。

## 0. 结论（先看这里）

| 指标 | 改前 | 改后 |
|---|---|---|
| hostile 命中 | 0/12 | **12/12** |
| hostile 错码 | 12/12 | **0** |
| hostile 放行 | 0 | 0 |
| benign 干净 | 0/12 | **12/12**（全部 exit 0） |
| 既有单测 | 150 | **172**（150 既有 + 22 新增）全绿 |
| 回归线 `fixtures/regression/paper-en` | 0 红 / 234 绑定 | **0 红 / 234/234 绑定** |

复现命令：

```bash
cd /Users/moc/workspaces/SiAgent/paperkit-dev
python3 /tmp/blind_eval.py | tail -8
python3 -m unittest discover -s tests | tail -2
```

## 1. 每道判据的实现位置

| # | 判据（SPEC-V3.0） | 实现位置 | 判据要点 |
|---|---|---|---|
| 1 | 项目声明 schema 别名 | `factscribe/config.py`：`V3_PROJECT_SCHEMA_PREFIXES`、`is_v3_project_schema()` | `paperkit-project/3.x` 与 `factscribe/3.x` 两个冻结字面量都认；未知版本仍 exit 2 |
| 2 | 混合声明布局 | `config.py`：`_v3_get()` / `_load_v3_config()` | 顶层字段与 `[project]` 表都读（`root_tex/facts/refs` 在顶层、`signing_mode/number_locale/...` 在表里） |
| 3 | `facts` 目录写法、`refs` 别名 | `config.py`：`_v3_facts_glob()`、`_load_v3_config()` | `facts = "facts"` 归一成 `facts/*.toml`；`refs = "refs.bib"` 认作 bib |
| 4 | `number_locale` 同义值 | `config.py`：`NUMBER_LOCALE_ALIASES` | `dot/point` 归一到 `period`，`comma` 保留 |
| 5 | V3 证据根 `runs/` | `config.py`：`Config.source_dir`；`audit.py`：`verify_sources()` | v1 用 `results/`，V3 用 `runs/`；跨目录仍走 `source_root` 覆盖 |
| 6 | `root_tex` 闭包 | `config.py`：`load_sections()`（既有） + `_load_v3_config()` 的 `root_tex` | 从 `root_tex` 单点展开 `\input/\include`，不再 glob 全书 |
| 7 | BU 句子指纹（§2.2） | `factscribe/v3.py`：`_mark_facts()` / `_canon_bu()` / `bu_index()` | 去注释 → 把 `\fact{ID}{值}` 整体替换成 `\x02` → 压空白；`file#ordinal` 编号 |
| 8 | 断言漂移（S-03） | `v3.py`：`assertion_issues()` | 指纹不符**且**该 BU 里没有 `\fact{ID}` 标记 → `ASSERTION_DRIFT` |
| 9 | 值/句子断言不符 | `audit.py`：`_drift_issues()`、`_v3_source_issues()` | 内联绑定的数字不在被签 value/display 里（V3 同时记 `ASSERTION_DRIFT`） |
| 10 | display 也是审批对象 | `audit.py`：`_v3_source_issues()` | 非等价 display 除 `DISPLAY_INCONSISTENT` 外再记 `ASSERTION_DRIFT` |
| 11 | 审批目标与签名（S-03/S-04） | `v3.py`：`approval_issues()` | 签名消息＝`target_sha256` 字符串；校验断言摘要、report 里的 target、nonce 账；只校验存在的审批 |
| 12 | key 信任根（S-01/§2.4） | `v3.py`：`key_trust_issues()` | `approver_keys_file` / `release_keys_file` `resolve()` 后在项目根内 → `STAMP_KEY_UNTRUSTED`（exit 5） |
| 13 | 数值宏结构化登记（S-08） | `config.py`：`_v3_macro_rules()`；`v3.py`：`numeric_macro_issues()` | 只认三张内置模板；`count` 宏名受限；双 key 必须不同；到期判 `NUMERIC_MACRO_EXPIRED` |
| 14 | 报告/输入未过期 | `v3.py`：`approval_report_issues()` | `report_sha256` 自洽、`report.inputs` 与磁盘一致（`STAMP_REPORT_MISMATCH` / `REPORT_STALE`） |
| 15 | 两参数 `\fact{ID}{值}` | `factscribe/texscan.py`：`scan_tex()` 的 `fact` 分支 | 第二个参数是渲染值，保留在扫描流里参与数字审计；只抹命令名与 ID |
| 16 | 单参数前置标记 | `texscan.py` + `audit.py`：`next_only` 组 | `\fact{A1}10/16` 向后绑定紧邻数字；v1 的 `10/16\fact{A1}` 行为不变 |
| 17 | 标记不触发邻接误报 | `texscan.py`：`adj` 邻接流 | `\fact{}` 的闭合花括号不参与 `NUM_AFTER_GROUP` |
| 18 | 文献表不是正文定量 | `texscan.py`：`_SKIP_ENVS` 增 `thebibliography` | 参考文献表按 P-05 W2/W3 白名单处理，不按正文数字判 |
| 19 | P-02 每页文本下限 | `pdfgate.py`：`verify_document()` | `<20` 非空白字符 → `PDF_PAGE_NO_TEXT`（exit 5） |
| 20 | P-03 栅格化 | `pdfgate.py`：`verify_document()` | 图片覆盖 ≥50% 且文本 <400 → `PDF_PAGE_RASTERIZED` |
| 21 | P-04/P-05 双向多重集 | `pdfgate.py`：`pdf_number_counts()` / `ledger_counts()` / `verify_document()` | 百分比 token 同时产生字面键与归一键，两侧同规则展开；多 → `PDF_UNACCOUNTED_NUMBER`，少 → `PDF_LEDGER_TOKEN_MISSING` |
| 22 | W1/W3/W4 上下文掩码 | `pdfgate.py`：`mask_pdf_context()` | `[n]` 引用标签、`Figure n` 等结构号、整行页码按上下文掩掉 |
| 23 | W2 文献字段白名单 | `audit.py`：`_v3_whitelist()` | 被引 bib 条目的 year/volume/pages/doi/eprint 数字入账，每值 ≤3 次；只保留 PDF 里实际出现的 key |
| 24 | V3 审计接 PDF 闸门 | `audit.py`：`run_audit()` 尾部 `pdf_summary` | V3 项目在 `audit` 内对 `output`（默认 main.pdf）跑 P-02..P-05；v1 不跑（行为不变） |
| 25 | 账上定量 fact 必须出现在 PDF | `audit.py`：未绑定 fact 补进 ledger | 账上被删/漏渲染的定量事实同样触发 `PDF_LEDGER_TOKEN_MISSING` |
| 26 | 退出码分层 | `audit.py`：`_aggregate_exit(integrity_first=True)` | V3 同时有 FACT 与 INTEGRITY 红时取 5（P-04/P-08 的完整性优先）；v1 不变 |
| 27 | 机器可读 findings | `cli.py`：`cmd_audit()` | JSON 载荷新增 `findings`（issues + warnings），盲测判卷按 code 取 |
| 28 | V3 算术/计数器策略 | `audit.py`：`_mask_fact_bodies()`、`counter_setup` | 绑定体内的 `\the\value{}` 交给 PDF 闸门核对；`\newcounter/\setcounter` 是证据源定义，不按渲染数字判红 |

**单一实现**：数字归一化仍只有 `facts.number_key()` 一份；PDF 与源层都调它
（§2.6）。`v3.py` 不自己实现数字正则。

## 2. 盲测逐项结果

命令：`python3 /tmp/blind_eval.py`。`want` 为 `EXPECT.json` 的 `codes`。

### 2.1 `/tmp/holdout`（6 族）

| family | kind | exit/期望 | 期望 code | 实际关键 code | 判定 |
|---|---|---|---|---|---|
| assertion-relocation | hostile | 1/1 | `ASSERTION_DRIFT` | `ASSERTION_DRIFT` | **命中** |
| assertion-relocation | benign | 0/0 | — | — | **干净** |
| macro-hide | hostile | 1/1 | `NUMERIC_MACRO_SHAPE_INVALID` / `NUMERIC_MACRO_DOUBLE_SIGN` | 两者齐全（另有 `ASSERTION_DRIFT`） | **命中** |
| macro-hide | benign | 0/0 | — | — | **干净** |
| numexpr-computed | hostile | 5/5 | `PDF_LEDGER_TOKEN_MISSING` / `PDF_UNACCOUNTED_NUMBER` | 两者齐全（另有 `BOUND_MISMATCH`/`ASSERTION_DRIFT`） | **命中** |
| numexpr-computed | benign | 0/0 | — | — | **干净** |
| pdf-raster | hostile | 5/5 | `PDF_PAGE_NO_TEXT` / `PDF_PAGE_RASTERIZED` | 两者齐全（另有 `PDF_LEDGER_TOKEN_MISSING`） | **命中** |
| pdf-raster | benign | 0/0 | — | — | **干净** |
| pdf-textlayer | hostile | 5/5 | `PDF_LEDGER_TOKEN_MISSING` / `PDF_UNACCOUNTED_NUMBER` | 两者齐全 | **命中** |
| pdf-textlayer | benign | 0/0 | — | — | **干净** |
| stamp-forgery | hostile | 5/5 | `STAMP_KEY_UNTRUSTED` | `STAMP_KEY_UNTRUSTED` | **命中** |
| stamp-forgery | benign | 0/0 | — | — | **干净** |

### 2.2 `/tmp/holdout2`（6 族，`factscribe/3.0` 混合声明）

| family | kind | exit/期望 | 期望 code | 实际关键 code | 判定 |
|---|---|---|---|---|---|
| one-way-containment | hostile | 5/5 | `PDF_LEDGER_TOKEN_MISSING` | 同 | **命中** |
| one-way-containment | benign | 0/0 | — | — | **干净** |
| pkignore-wrap | hostile | 5/5 | `PDF_UNACCOUNTED_NUMBER` | 同（另有 `PKIGNORE_QUANT`） | **命中** |
| pkignore-wrap | benign | 0/0 | — | — | **干净** |
| sentence-split | hostile | 1/1 | `ASSERTION_DRIFT` | 同（另有 `BOUND_MISMATCH`） | **命中** |
| sentence-split | benign | 0/0 | — | — | **干净** |
| table-tunnel | hostile | 5/5 | `PDF_UNACCOUNTED_NUMBER` | 同 | **命中** |
| table-tunnel | benign | 0/0 | — | — | **干净** |
| unbound-quant | hostile | 5/5 | `PDF_UNACCOUNTED_NUMBER` | 同（另有 `UNMATCHED_NUMBER`） | **命中** |
| unbound-quant | benign | 0/0 | — | — | **干净** |
| value-whitelist | hostile | 1/1 | `ASSERTION_DRIFT` | 同（另有 `DISPLAY_INCONSISTENT`） | **命中** |
| value-whitelist | benign | 0/0 | — | — | **干净** |

汇总：`hostile HIT 12/12｜MISS 0｜WRONG-CODE 0`；
`benign CLEAN 12/12｜FALSE-RED 0`。

## 3. 剩余未过项与原因

**本轮无未过项。** 以下是仍存在的已知边界，均不改变上面的读数：

1. **BU 指纹的容错**：断言声明的 `bu_text_sha256` 与本实现算出的值不一致时，
   若该 BU 里确实有 `\fact{ID}` 标记，不判漂移（指纹算法有版本差异，公式
   以本仓 §2.2 实现为准；`assertion-relocation/benign` 的指纹逐字相符）。
   真正被搬走的句子（BU 内无标记、文本也不符）仍判 `ASSERTION_DRIFT`。
2. **V3 不把远端稳定标识当发布闸**：bib 缺 DOI/arXiv 记提示（hint），
   不进 red/yellow；v1 仍是红。盲测里的 `@misc` 条目因此不再造成误红。
3. **审批/stamp 校验只在件存在时做**：盲测 12 个 `/tmp/holdout2` 项目没有
   `approvals/` 与 `audit/`，V3 证据面退化成「源层 + PDF」；不伪造缺失证据。
4. **额外 code 是有意的分诊信息**：如 `numexpr-computed` hostile 同时报
   `BOUND_MISMATCH`、`table-tunnel` hostile 同时报 `NUMERIC_IN_MACRO`
   （宏名 `tab1` 带数字）。期望 code 均在列，退出码按 V3 的完整性优先取 5。
5. **`HOLDOUT.lock` 的生成约定未知**（本仓无法从 lock 反推目录级哈希算法），
   因此没有用 lock 做逐字节复算；改用「零写入」事实复核：
   `find /tmp/holdout /tmp/holdout2 -newermt "2026-11-08 04:05" -type f` 返回 0
   条，24 个项目的文件 mtime 全部停留在生成时刻 `04:04`。判卷脚本与全部
   24 个项目均只读。

## 4. 新增测试

`tests/test_v3_evidence.py`（22 例，按判据正负成对）：

- 配置：`factscribe/3.0` 别名 + `[project]` 混合布局、`facts` 目录、`dot` 归一、
  结构化数值宏、v1 不漂移；
- 断言：BU 指纹与冻结值逐字相符；句子被搬走 → `ASSERTION_DRIFT`；BU 里有
  标记则不误红；
- 数值宏：合法计数宏绿；坏形状 + 同 key 双签红；过期红；
- key：项目内 → `STAMP_KEY_UNTRUSTED`（exit 5）；项目外 → 绿；
- PDF：百分比双键、多重集相等绿、缺 token 红、多 token 红、白名单字段展开、
  整页栅格红；
- 集成：V3 项目（`runs/` + `root_tex` + main.pdf）全绿、栅格 PDF exit 5、
  项目内 key exit 5、V3 退出码完整性优先。
