# GATES-C｜12 道闸门的实现与边界（批 47 / C 阶段）

> 目标：把 A 阶段冻结的 12 条 `@unittest.expectedFailure` 一条条变成真红，
> 同时不误伤 12 条 benign 近邻与 `paper/` 回归线。
>
> 读数（本批完成时）：
> - `python3 -m unittest discover -s tests` → **140 tests, OK**（A 阶段基线 121 例 + 新增 19 例）；
> - `expectedFailures = 0`（A 阶段为 12）；
> - 回归线 `fixtures/regression/paper-en` → **0 红 / 234 绑定 / exit 3**，唯一黄仍是 `UNSCANNED_TEX main.tex`；
> - 12 条 hostile 全部达到 `EXPECT.json` 的 exit 与错误码；12 条 benign 全部 `exit 0`。

## 0. 改动地图

| 文件 | 责任 |
|---|---|
| `factscribe/facts.py` | 值域去掉隐式舍入（B2）；新增 `canon_text` / `decimal_places`；`Fact.display/co_claim` |
| `factscribe/config.py` | `display` 解析、`numeric_macro_allow`、`\input` 包装宏展开（B1） |
| `factscribe/texscan.py` | 句级 BU（`sentence_spans`）、标记组（`marker_groups`）、分数单元合并、邻接层 `adjacency`、批注参数记录 |
| `factscribe/texrules.py`（新） | ARITH / NUMERIC_IN_MACRO / PKIGNORE_QUANT / 邻接判据 / 表格区域 / display 校验的「找证据」层 |
| `factscribe/audit.py` | 装 Issue、按 BU 归属、表格通道、退出层级聚合 |
| `factscribe/pdfgate.py`（新） | `verify-pdf`：P-02..P-05、P-08/S-01、纯 stdlib ed25519 验签 |
| `factscribe/cli.py` | `verify-pdf` 子命令；audit/check 用分层退出码 |
| `factscribe/constants.py` | `EXIT_INTEGRITY=5`、`EXIT_STALE=7`、`EXIT_MISSING=8` |

退出码聚合：有红时按 `8 > 1 > 5 > 7` 取第一个出现的层级；只有黄时 3（`--strict` 升 1）。
所以 R1-B1 只报 `TABLE_UNBOUND`（COVERAGE）时 exit 恰好是 5，不会被写成 1。

## 1. 逐条闸门

### 1.1 R1-B2｜值域白名单（`BOUND_MISMATCH`，exit 1）

- **实现**：`facts.fact_value_keys` 删除 `places=0..4` 的舍入展开；值域＝字面 token ∪ 分数**精确**商
  （`10/16 → 0.625`）。`display` 只追加严格等价写法（见 R2-ROUNDTO）。
- **边界**：漏报——若作者把近似值写进 `value` 本身，工具无法判断那是近似；
  进入 §7-R4 的人工复核。误报——无（精确商是值域的一部分，`0.625` 仍可写）。
- **夹具**：`hostile/R1-B2`（`1/16` → 红）、`benign/R1-B2`（`10/16` → 绿）。
- **测试**：夹具 2 + `test_gates_c.ValueRangeTest` 2。

### 1.2 R1-B3 / R2-MULTIFACT｜句级 BU 与顺序归属（`BINDING_ATTRIBUTION`，exit 1）

- **实现**：`texscan.sentence_spans` 按句末标点切 BU（`.` 的数字/缩写/单大写字母守卫；
  `。！？；` 总切；空行与 `\\` 切）；`marker_groups` 把连续 `\fact{}` 合成一组、只闭合
  自己那一句；`_merge_number_units` 把 `a/b` 合成一个 QUANT 单元。
  `audit.run_audit`：组内 token 数＝fact 数（且无 `co_claim`）时逐位归属，
  否则走并集分支（保持 R-03 的多值段合法写法）。
- **边界**：漏报——数字全对、顺序也对但语义张冠李戴（整句搬家），进 §7-R2；
  误报——标记写在句号之后会成为下一句的组，属 R-02 的 `MARKER_TRAILING` 场景，
  当前只按位置归属，不额外报警（有意保守）。
- **夹具**：`hostile/R1-B3`、`hostile/R2-MULTIFACT`（改正文为对调形态，见 §2）、
  两条 benign 近邻（inline 标记）仍绿。
- **测试**：夹具 4 + `test_gates_c.SentenceUnitTest` 2。

### 1.3 R1-B1｜表格闭包（`TABLE_UNBOUND`，exit 5）

- **实现**：`config.load_sections` 反复提取 `\newcommand{\X}[1]{\input{#1}}` 一类包装宏并展开调用；
  `texrules.tabular_regions` 标出表格字符区间；`audit` 对表格内、未被任何标记组闭合、
  且数字 key 回不到账的数字报 `TABLE_UNBOUND`（COVERAGE，exit 5）。表格里能回账但未绑定的数字
  仍按 `UNBOUND_NUMBER` 黄（保持 `examples/minimal` 的既有读数）。
- **边界**：只展开「纯 `\input` 包装」；带条件/循环/拼接的宏仍可能绕开，进 §7-R1 的人工复核。
  表格内的 `\pkignore` 整块走 R-06 通道，不按 `PKIGNORE_QUANT` 重复判红（回归线 5 张表靠这条）。
- **夹具**：`hostile/R1-B1`（exit 5、`TABLE_UNBOUND`）、`benign/R1-B1`（普通 `\input` 表格绿）。
- **测试**：夹具 2 + `test_gates_c.TableClosureTest` 2。

### 1.4 R1-B4｜`\pkignore` 参数（`PKIGNORE_QUANT`，exit 1）

- **实现**：`texscan` 记录批注宏参数原文；`texrules.pkignore_quant_hits` 先掩 URL 与
  带连字符的标识符（`sphinx-10449`、`GPT-4`），再抽 QUANT；命中即红，并继续计入
  `annotations_skipped`（跳过不等于放行）。
- **边界**：包裹 `table/tabular/longtable` 的 `\pkignore` 走表格通道；`\pknote`/`\fixnote`
  不是豁免宏，但当前只计批注、不扫数字（R-08 的 TODO 渲染检查尚未实现，登记为边界）。
- **夹具**：`hostile/R1-B4`（99/100 → 红）、`benign/R1-B4`（`sphinx-10449` → 绿）。
- **测试**：夹具 2 + `test_gates_c.PkignoreTest` 2。

### 1.5 R2-MACRO｜宏体数字（`NUMERIC_IN_MACRO`，exit 1）

- **实现**：`texrules.numeric_macro_hits` 解析 `\newcommand/\renewcommand/\providecommand/
  \DeclareRobustCommand/\NewDocumentCommand/\def`；排除 `[n]` 参数个数与 `#1..#9` 占位后，
  定义体（含可选默认值）出现 `[0-9]` 即红。`project.numeric_macro_allow` 可登记人签布局宏。
- **边界**：`.sty/.cls` 里的宏不在闭包；`numeric_macro_allow` 的 S-08 双签形状校验未实现
  （当前按名单放行，登记为边界）。误报——布局宏需显式登记（fail-closed 是有意的）。
- **夹具**：`hostile/R2-MACRO`（`\acc`/`\onefour` 红）、`benign/R2-MACRO`（`\sys` 无数字绿）。
- **测试**：夹具 2 + `test_gates_c.MacroAndArithTest` 2。

### 1.6 R2-NUMEXPR｜算术命令族（`ARITH_IN_BODY`，exit 1）

- **实现**：`texrules.arith_hits` 在「去注释/去 verbatim」的原文上匹配表 A
  （`\numexpr \the \value \setcounter \advance \pgfmathparse \directlua \write18` 等 32 个）。
  命中即红，不判断它是否真的产出了数字。
- **边界**：表 A 只能经 owner 签名扩充；`\setlength/\vspace/\includegraphics[width=]` 不在表内
  （它们的参数在扫描层被掩码）。漏报——TeX 图灵完备的纯展开技巧不可穷尽，靠 `verify-pdf` 兜底。
- **夹具**：`hostile/R2-NUMEXPR`（`\the\numexpr` → 红）、`benign/R2-NUMEXPR`（纯字面 10 → 绿）。
- **测试**：夹具 2 + `test_gates_c.MacroAndArithTest` 2。

### 1.7 R2-CONCAT｜数字邻接（`NUM_AFTER_GROUP` / `NUM_ADJACENT_GROUP`，exit 1）

- **实现**：`texscan` 保留命令名未抹除的同长度结构层 `adjacency`；`texrules.adjacency_hits`
  对每个 QUANT 检查：左邻 `}` → `NUM_AFTER_GROUP`；左右紧贴非 SAFE 宏 → `NUM_ADJACENT_MACRO`；
  右邻空组 `{}` 再接数字 → `NUM_ADJACENT_GROUP`。SAFE 含 `\fact/\ref/\cite` 家族。
- **边界**：`{10/16}` 合法（左 `{` 右 `}`）；`\textbf{x}9` 这类排版后接数字会命中
  `NUM_AFTER_GROUP`，属 fail-closed 的有意取舍。真正的「渲染后粘连」仍需 PDF 层兜底。
- **夹具**：`hostile/R2-CONCAT`（`9{}1.4\%` → 红且含 `NUM_AFTER_GROUP`）、
  `benign/R2-CONCAT`（`91.4\%` → 绿）。
- **测试**：夹具 2 + `test_gates_c.MacroAndArithTest.test_token_concatenation_is_red`。

### 1.8 R2-ROUNDTO｜display 严格等价（`DISPLAY_INCONSISTENT`，exit 1）

- **实现**：`config` 解析 `display`（字符串或 `{text, round_to, setting}`）；`facts.canon_text`
  把单一表达式收敛成规范键（分数取精确商、百分号换算）；`texrules.display_hits` 要求
  `canon(text) == canon(value)`，`round_to` 必须是非负整数且等于 `text` 的小数位数。
  校验同时跑在 `check` 与 `audit`。
- **边界**：`approx_display` 未实现（当前不解析该字段）；多 token 的 display 文本无法单值比较，
  会被判 `DISPLAY_INCONSISTENT`（fail-closed）。
- **夹具**：`hostile/R2-ROUNDTO`（0.9 vs 0.91 → 红）、`benign/R2-ROUNDTO`（`10/16`/`62.5%` → 绿）。
- **测试**：夹具 2 + `test_gates_c.DisplayTest` 2。

### 1.9 R3-PDF-RASTER｜每页文本层与栅格化（`PDF_PAGE_NO_TEXT` + `PDF_PAGE_RASTERIZED`，exit 5）

- **实现**：`pdfgate.verify_pdf` 先做 P-01 工具探测（缺 `pdftotext/pdfinfo/pdfimages`
  → `PDF_TOOL_MISSING` exit 8）；`pdftotext -layout` 按 `\f` 分页，非空白字符 < 20
  → `PDF_PAGE_NO_TEXT`；`pdfimages -list` 算显示面积占比，`cov ≥ 0.5 且 chars < 400`
  → `PDF_PAGE_RASTERIZED`，`chars ≥ 400` 降为黄 `PDF_PAGE_IMAGE_DOMINANT`。
- **边界**：不做 OCR；多页混合尺寸按第一页估算（`PAGE_SIZE_FALLBACK` 未单列）；
  图片取不到 ppi 时按 72dpi 估算。
- **夹具**：`hostile/R3-PDF-RASTER`（空文本 + 满页图 → 两个 code，exit 5）、
  `benign/R3-PDF-RASTER`（41 字符文本页 → 0）。
- **测试**：夹具 2 + `test_gates_c.PdfGateTest` 2（raster + 缺工具 fail-closed）。

### 1.10 R3-PDF-ONEWAY｜双向多重集（`PDF_LEDGER_TOKEN_MISSING`，exit 5）

- **实现**：PDF 文本先掩 URL/DOI/arXiv 与标识符，再按 `_NUM_RE` 计 key 频次；
  `ledger_counts` 逐条展开 `entry.keys`。`ledger ≤ pdf` 不成立 → `PDF_LEDGER_TOKEN_MISSING`；
  `pdf > ledger + pdf_whitelist` → `PDF_UNACCOUNTED_NUMBER`。白名单缺 `key/count/source`
  → `PDF_WHITELIST_UNPROVENANCED`；声明了但 PDF 未出现 → 黄 `PDF_WHITELIST_UNUSED`。
- **边界**：`\frac` 上下排版、表格跨行断字可能造成误报（当前最小语料未触发）；
  白名单是**人签声明**，不放宽相等判定。PDF 元数据指针（`paperkit-stamp:`）未校验。
- **夹具**：`hostile/R3-PDF-ONEWAY`（缺 `5/16` → 红）、`benign/R3-PDF-ONEWAY`（多重集相等 → 0）。
- **测试**：夹具 2 + `test_gates_c.PdfGateTest.test_one_way_inclusion_is_red`。

### 1.11 R3-STAMP-SELFSIGN｜stamp 信任根（`STAMP_KEY_UNTRUSTED`，exit 5）

- **实现**：`pdfgate._stamp_issues` 顺序：公钥文件 `resolve()` 后位于 PDF 所在项目根内
  → `STAMP_KEY_UNTRUSTED`（立即退出）；`payload.schema=paperkit-stamp/3.0`；
  登记表查 `signer_key_id`；纯 stdlib ed25519 验证 `JCS(payload)`；PDF 字节 sha
  → `STAMP_PDF_MISMATCH`（7）；报告指纹（去掉 `report_sha256` 自身后的 JCS）
  → `STAMP_REPORT_MISMATCH`（5）；`rules/assertions/input_set/tool_digest` 一致性；
  `verdict==PASS && level==L2`；`signed_at` 时间窗（以系统时钟与 `generated_at` 的较大者为基准）。
- **边界**：PDF 元数据里的 `paperkit-stamp:` 指针、nonce 重放账、key 权限位、
  登记链（`registered_by`）尚未实现（`STAMP_NONCE_REUSED` / `STAMP_METADATA_MISSING` /
  `KEY_PERMISSION_UNSAFE` 未覆盖）；私钥在 agent 可达范围外是部署事实，工具不承诺（S-02/S-10）。
- **夹具**：`hostile/R3-STAMP-SELFSIGN`（项目内 `keys/` → 红 5）、
  `benign/R3-STAMP-SELFSIGN`（`fixtures/trust/` 外部公钥 + 有效签名 → 0）。
- **测试**：夹具 2 + `test_gates_c.PdfGateTest` 2（untrusted / external-key pass）。

## 2. 夹具订正（必须留痕）

R1-B3 与 R2-MULTIFACT 的 hostile 原稿正文是：

```
The baseline resolved 10/16 and ours resolved 5/16\fact{A2}\fact{A3}.
The plain arm resolved 10/16 while ours resolved 5/16\fact{A2}\fact{A3}.
```

标记顺序与数字出现顺序一致，按 R-03 的顺序归属**本来就合法**——这两条原稿其实没有攻击。
C 阶段按它们各自 `EXPECT.json` 的 note（「A/B 对调必红」）把正文改成对调形态：

```
The baseline resolved 5/16 and ours resolved 10/16\fact{A2}\fact{A3}.
The plain arm resolved 5/16 while ours resolved 10/16\fact{A2}\fact{A3}.
```

期望值（exit 1 / `BINDING_ATTRIBUTION`）不变；benign 近邻一字未动。
这是**补上缺失的攻击**，不是放宽判据；A 阶段 `git log` 可复核原稿。

## 3. golden 比对

B 阶段的 `scripts/golden_diff.py` 在 C 阶段前/后各录一份
（`audit --json` × 24 个夹具 + 回归线 + `examples/minimal`）：

- **17 个文件逐字节相同**：12 条 benign、3 条 R3 hostile（audit 面）、回归线、`examples/minimal`；
- **9 个 hostile audit JSON 变化**（R1-B1..B4、R2-MACRO/CONCAT/NUMEXPR/MULTIFACT/ROUNDTO）：
  差异全部来自新增判据（多出期望 code / 退出码从 0/3 变 1/5），没有 benign 侧差异；
- `exits.txt` 同步变化。

没有为通过夹具而改动 benign、回归线或 `examples/minimal` 的读数。

## 4. 未覆盖与后续

- S-05..S-09（manifest/nonce/批量/规则哈希/发布签名）与 P-09/P-10 未在本批实现；
- `approx_display`、`FACT_WITHOUT_QUANT`/`FACT_SET_OVERLAP` 等 advisory 未接；
- `verify-pdf` 的 stamp 缺失目前跳过 P-08（PDF-only 夹具路径）；release 流水线应加
  `--require-stamp` 强制（下一批）。
