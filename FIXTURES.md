# FIXTURES｜红蓝 hostile 夹具（批 45 / A 阶段建，批 47 / C 阶段全部转正）

> 目的：把 R1/R2/R3 三轮红队里**阻断级且当前实现会漏红**的用例落成可执行回归线，
> 为 C 阶段上闸门提供「改回去就红」的钉子。
>
> 纪律：夹具的期望值来自 **SPEC-V2.2 / SPEC-V3.0 的判据**，不来自当前实现读数。
> C 阶段已把 12 条全部实现，`tests/test_fixtures.py` 里不再有
> `@unittest.expectedFailure`：**expectedFailures = 0**。
>
> 本轮不改 `paper/`、`sihankor/`；实现位置与误报/漏报边界见
> `docs/implementation/GATES-C.md`。

## 目录

```
fixtures/
  hostile/<轮>-<编号>/      # 必须被判红的最小项目
    paperkit.toml
    facts/ledger.toml
    sections/body.tex
    results/run.log + results/MANIFEST.toml
    refs.bib
    main.pdf / audit/…      # 仅 R3 PDF / stamp 组
    EXPECT.json             # SPEC 期望：exit + codes + criteria
  benign/<轮>-<编号>/       # 同结构、合法内容，必须 exit 0
  regression/paper-en/      # paper/ 只读快照（234 绑定、0 红）
  trust/approver_keys.json  # 项目外信任根（只给 benign stamp 用）
```

`EXPECT.json` 字段：`exit`、`codes`、`command`（`audit` 或 `verify-pdf`）、
`criteria`（SPEC 条款）、`attack_family`（T-09 族表）、`expected_verdict`、`note`。

## 12 对夹具

| 编号 | 攻击一句话 | hostile 期望（exit/codes） | 当前实际（批 47 / C） | 对应 SPEC 条款 | 已实现？ |
|---|---|---|---|---|---|
| R1-B2 | `10/16` 的值域被四舍五入放宽，`1/16` 也能绑定同一 fact | 1 / `BOUND_MISMATCH` | **红 1 / `BOUND_MISMATCH`** | V2.2 R-03/R-04（内部 B2） | 是（值域只留精确商） |
| R1-B3 | 同一物理行内两个 fact 值域取并集，A/B 两臂对调仍绿 | 1 / `BINDING_ATTRIBUTION` | **红 1 / `BINDING_ATTRIBUTION`** | V2.2 R-03/R-02（内部 B3） | 是（句级 BU＋顺序归属） |
| R1-B1 | `\tableinput` 包装宏不在 `\input` 闭包，整张表绕开审计 | 5 / `TABLE_UNBOUND` | **红 5 / `TABLE_UNBOUND`** | V2.2 R-05/R-06（内部 B1） | 是（包装宏展开＋表格通道） |
| R1-B4 | `\pkignore{...}` 参数塞整句假结论，被当批注抹掉 | 1 / `PKIGNORE_QUANT` | **红 1 / `PKIGNORE_QUANT`** | V2.2 R-07（内部 B4） | 是 |
| R2-MACRO | 宏体携带 `9`、`1.4`，渲染出账上没有的 `91.4%` | 1 / `NUMERIC_IN_MACRO` | **红 1 / `NUMERIC_IN_MACRO`** | V2.2 R-01A（2-B1） | 是 |
| R2-CONCAT | `9{}1.4\%` 拼接渲染成 `91.4%`，`91.4` 从不是 token | 1 / `NUM_AFTER_GROUP` | **红 1 / `NUM_AFTER_GROUP`（另报 `NUM_ADJACENT_GROUP`）** | V2.2 R-01A | 是（邻接判据＋错码修正） |
| R2-NUMEXPR | `\the\numexpr 9+1\relax` 派生 10，扫描面只有 9/1 | 1 / `ARITH_IN_BODY` | **红 1 / `ARITH_IN_BODY`** | V2.2 R-01A | 是（错码修正） |
| R2-MULTIFACT | 一句两 fact 按出现顺序一一归属；对调后全绿 | 1 / `BINDING_ATTRIBUTION` | **红 1 / `BINDING_ATTRIBUTION`** | V2.2 R-02（2-S1） | 是 |
| R2-ROUNDTO | `display: {text:0.9, round_to:1}` 把 `0.91` 放宽成 `0.9` | 1 / `DISPLAY_INCONSISTENT` | **红 1 / `DISPLAY_INCONSISTENT`** | V2.2 R-04（2-B2） | 是（display 严格 canon） |
| R3-PDF-RASTER | 整页换成一张 850×1100 图片，文本层为空 | 5 / `PDF_PAGE_NO_TEXT` + `PDF_PAGE_RASTERIZED` | **红 5 / 两个 code 都在** | V3.0 P-02/P-03 | 是（`verify-pdf`） |
| R3-PDF-ONEWAY | PDF 只印 `10/16`，账上的 `5/16` 缺失；单向包含放行 | 5 / `PDF_LEDGER_TOKEN_MISSING` | **红 5 / `PDF_LEDGER_TOKEN_MISSING`** | V3.0 P-04/P-05 | 是（双向多重集） |
| R3-STAMP-SELFSIGN | 公钥放在项目内 `keys/`，自签自验 stamp | 5 / `STAMP_KEY_UNTRUSTED` | **红 5 / `STAMP_KEY_UNTRUSTED`** | V3.0 P-08/S-01 | 是（项目外信任根） |

**合计**：12 对（12 hostile + 12 benign）。批 47 / C 阶段后**漏红 0 条、错码 0 条**；
12 条 hostile 全部达到 `EXPECT.json` 的 exit 与 code，12 条 benign 近邻仍全部 `exit 0`。

## 回归夹具

`fixtures/regression/paper-en/` 是 `paper/` 的必要文件快照（facts / sections / appendix /
tables / figures / refs.bib / main.tex / results/MANIFEST.toml），`source_root = "../../../.."`
指向工作区根（相对路径，仓内可移植），原始产物不搬家。读数见 `fixtures/regression/EXPECTED.md`：

- **0 红 / 234 个数字全部内联绑定 / 0 未绑定 / 0 未回账**
- exit 3：唯一黄是 `UNSCANNED_TEX main.tex`（main.tex 按任务要求保留但不在 `sections` glob 内；
  属于覆盖提示，不是绑定级红）

## 运行

```bash
cd paperkit-dev
python3 -m unittest discover -s tests -p "test_fixtures.py" -v
```

当前读数（批 47 / C 阶段）：

- `tests/test_fixtures.py`：**28 tests, OK（expected failures=0）**；
- 全套 `python3 -m unittest discover -s tests`：**140 tests, OK**；
- 回归线 `fixtures/regression/paper-en`：0 红 / 234 全绑定 / exit 3（唯一黄 `UNSCANNED_TEX main.tex`）。

## 说明

1. **expectedFailure 不是豁免**：它只表示「SPEC 已冻结、实现未到」。新增攻击不得以
   expectedFailure 进仓（T-04）；C 阶段已把 12 条装饰器全部删除。
2. R3 的 PDF 是纯 Python 生成的最小 PDF：raster 页为整页图片（poppler 实测
   `850×1100 @100ppi`，覆盖率 1.0），one-way 页为 Helvetica 文本页（可用
   `pdftotext -layout` 核对数字）。stamp 用真实 ed25519 私钥签署；benign 的公钥位于
   项目外 `fixtures/trust/`，hostile 的公钥在项目内 `keys/`。
3. **夹具订正（C 阶段）**：R1-B3 与 R2-MULTIFACT 的 hostile 原稿把「数字出现顺序」
   写成了与标记顺序一致，等于没有攻击（按 R-03 的顺序归属会直接放行）。C 阶段按
   它们各自 `EXPECT.json` 的 note（「A/B 对调必红」）把正文改成对调后的形态，
   期望值（exit 1 / `BINDING_ATTRIBUTION`）不变。这是补攻击，不是放宽判据。
4. R1-B1 hostile 的 `\newcommand{\tableinput}[1]` 里 `[1]` 现在按宏定义结构参数
   整体吞掉，不再产生一条假 `UNMATCHED_NUMBER` 噪声；表格通道只报 `TABLE_UNBOUND`。
5. `verify-pdf` 缺 poppler 时明确报 `PDF_TOOL_MISSING`（exit 8），不静默放行；
   R3 的 benign 在闸门可用时会自动加跑（测试已实现）。
