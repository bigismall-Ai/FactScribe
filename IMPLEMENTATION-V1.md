# paperkit v1 实现记录

日期：2026-11-07　　实现者：蓝队（批 34，D 席 / opencode）
规格：`SPEC-V1.md`；闸门代码 commit `b9a66e3`。

---

## 0. 交付

```
paperkit-dev/
  paperkit.py                     # 单文件 CLI，纯标准库；v1.0.0
  SPEC-V1.md                      # 29 条裁决 + 新契约 + 边界
  IMPLEMENTATION-V1.md            # 本件
  tests/test_paperkit.py          # 87 例 unittest（原 46 + 新 41），全离线
  tests/fixtures/redteam-b1/      # 红队 B1 反例（短 value + 编造数字）
  tests/fixtures/redteam-b4/      # 红队 B4 反例（嵌套章节）
  examples/minimal/               # 已升级：source_sha256 + 人签 MANIFEST + expr
```

命令：`check / audit / matrix / build / preamble`，全部支持 `--json`；`check/audit`
另有 `--strict`（黄当红）。退出码 0/1/2/3/4。

---

## 1. 落了哪几道闸

| # | 闸门 | 代码落点 | 判定 | 测试（正/负） |
|---|---|---|---|---|
| 1 | 内联绑定 + 行内数字 ⊆ fact.value | `scan_tex`（`\fact`/`[[fact:]]` 绑定）、`run_audit`（`BOUND_MISMATCH`） | 绑定不符 = 红；未绑定命中 = 黄 `UNBOUND_NUMBER`；未绑定且未命中 = 红 `UNMATCHED_NUMBER` | `TestV1InlineBinding` 5 例（黄/严格/红/token 等值/config 不入白名单）＋原 `test_bound_line_*` 2 例 |
| 2 | `source_sha256` + 人签清单 + value 回查 | `sha256_file`、`verify_sources`、`Facts.source_sha256` | 缺 sha/不符 = 红；未签/清单不符 = 红；缺清单/未签文件 = 黄；value 数字不在 source = 黄 | `TestV1SourceAnchoring` 6 例；示例 check 绿 |
| 3 | 引用抽取覆盖 natbib 全家 | `_CITE_RE`/`_CITE_KNOWN`/`_CITE_IGNORE`、`run_audit` | 未知 `*cite*` 命令 fail-closed 红；`\nocite{key}` 也核；可选参数正确跳过 | `TestV1Citations` 10 例（citep/citet/citeauthor/nocite/未知命令/坏 arXiv/url 条目/重复 key/重复 DOI/@string+crossref） |
| 4 | 退出码分层 + `severity` | `_exit_code`、`_payload`、`cmd_*` | `0` 绿 / `1` 红 / `2` 配置 / `3` 黄 / `4` 内部错；JSON 带 `schema_version`、`severity`、`coverage` | `TestV1ExitAndJson` 5 例；原「不静默通过」5 例仍全绿 |
| 5 | `derived` 的 `expr` 求值 | `eval_expr`（ast 白名单，禁 eval）、`_cycles`、`run_check` | 无 expr = 红；算不对 = 红；环 = 红；父被 supersedes = 红；算式越界（调用/属性）= 红 | `TestV1DerivedExpr` 6 例（ok/不符/缺 expr/ast 拦截/环/superseded 父） |
| 6 | 红队反例夹具 | `tests/fixtures/redteam-b1|b4` | 见 §2 | `TestRedTeamCounterexamples` 2 例 |

附带落的：B3 词法流水线（verbatim/verb/pkignore → 注释 → 命令 → 上下标 → 数字）、
B4 递归 glob + `\input` 闭包 + `UNSCANNED_TEX`/coverage、C4 科学计数法/千分位/
`percent`、C3 `kind=config`、C6 `LOW_BINDING_RATE`/`DUPLICATE_VALUE`、C7 标识格式
校验、C8 多 bib/`@string`/crossref、C9 `supersedes`/metric 冲突（黄）、C10
`paperkit preamble`、D4 source 必须 `results/` 下、D5 id 归一判重、D6/D7 coverage +
attestation、D10 图无 CSV 黄。

---

## 2. 红队 B1/B4 现在是不是真的红

**是。** 夹具是真实项目目录，测试直接跑 CLI：

```
$ python3 paperkit.py audit tests/fixtures/redteam-b1 --json | ...
exit 1 red [('UNMATCHED_NUMBER','1422'), ('UNMATCHED_NUMBER','4.2e-5'), ('UNMATCHED_NUMBER','4242')]

$ python3 paperkit.py audit tests/fixtures/redteam-b4 --json | ...
exit 1 red [('UNMATCHED_NUMBER','3.7%','sections/chapters/intro.tex:2:29'),
             ('UNMATCHED_NUMBER','12',  'sections/chapters/intro.tex:2:69')]
```

B1 的机制：`value = "42"` 只接受 token `42`；`1422/4.2e-5/4242` 在 token 锚定下
一个都进不来，且没有内联绑定，于是红。B4 的机制：`sections/*.tex` 递归命中
`sections/chapters/intro.tex`，该文件里的编造数字不再逃逸。

（`42` 本身在 B1 里落到黄 `UNBOUND_NUMBER`：它确实回得到账，但没被绑定——v1 不再
把这种「回得到账」当绿。）

---

## 3. 测试结果

```
$ python3 -m unittest discover -s tests
Ran 87 tests in ~5s
OK
```

- 原 46 例：**全部保持通过**（其中 4 处做了不改变测试意图的适配，见 §4）；
- 新增 41 例：绑定 5、源头 6、引用 10、派生 6、词法 7、退出码/卫生/preamble 5、
  红队反例 2。

`examples/minimal` 实跑：

```
check  -> 0 绿（3 facts，sha 钉住 3，清单已签）
audit  -> 1 红（47.3 + ghost2024，恰好 2 处）＋ 7 黄（表格 5 个未绑定数字、
          main.tex 不在闭包、绑定率 4/10）
matrix -> 3 行
```

---

## 4. 对原有 46 例的适配（为什么必须动）

1. **`test_conflict_listed_but_not_red` → `..._and_yellow`**：断言 `0` 改 `3`。
   v1 把「账本自相矛盾」从「不是错」升为黄（SPEC-V1 C9/B8：冲突必须非 0，否则 CI
   无法对最致命的问题设闸）。这是唯一一处**断言语义**变化。
2. **`test_percent_and_fraction_and_kilo_matched`**：正文末尾补
   `\fact{A1,A3,A2,B1,B2}`，断言不变（仍要 0）。v1 里未绑定数字只算黄，不补绑定
   就会退出 3——这是闸门本身的设计，不是测试放水。
3. **`test_supersedes_silences_conflict`**：事实集从 `A1 + A9 + A2` 改为 `A1 + A9`。
   A2 从被 supersedes 的 A1 推算，v1 会出 `SUPERSEDED_PARENT` 红；该用例只想验
   「supersedes 封冲突」，故去掉无关的 A2。
4. **fixture 升级**：`make_project` 现在自动写 `source_sha256` 与
   `results/MANIFEST.toml`；`FACT_A2` 补 `expr`；`run_audit` 返回值从 4 元组变 5 元组
   （多一个 `yellow` 列表），resolve 用例跟着改解包。都是契约升级，不是结论放宽。

---

## 5. 仍然存在的已知漏洞（按危险度）

1. **信任根是「人签」**：人盖章式签署 agent 生成的 `results/`，链上全绿而内容可能是
   编的。工具只保证「签后未改」。
2. **语义不对账**：value 回查只证明数字在 source 里出现过，不证明它对应 claim 说的
   那件事；绑定作用域是「行」，跨行命题错配看不见。
3. **引用只验标识**：默认不联网、不比对题名/作者；格式合法但内容编造的 DOI 在默认
   路径放行。
4. **`build` 仍是 shell 字符串**（B5 只落了规格）：跑陌生仓库的 `paperkit build`
   等于执行任意命令。v1.1 改 argv + 允许列表。
5. **图里数字**：无 `.csv` 只出黄，不解析 PNG/PDF；表内纯排版数字仍需绑定或
   `\pkignore`。
6. **分词边界**：`10 000` 可能被合并；万/亿、Unicode minus、复合 value 对多数字
   未覆盖；`kind=config` 的 value 仍保留裸数别名。
7. **账本 append-only 靠 git**：工具不做哈希链/签名，改写历史仍可绕过。
8. **不做舍入容差**：`0.9483` 的账不接受正文 `95%`；要显示精度就写 derived expr
   或精确值。
9. **`audit/` 不入库**：JSON 里有 `attestation`（账本/产物哈希、commit），但把
   attestation 提交进仓库仍由人决定。

---

## 6. 复现命令

```bash
cd paperkit-dev
python3 -m unittest discover -s tests            # 87 例，全离线
python3 paperkit.py check  examples/minimal      # 0
python3 paperkit.py audit  examples/minimal      # 1（2 红 7 黄）
python3 paperkit.py audit  examples/minimal --json
python3 paperkit.py audit  examples/minimal --strict   # 黄也拦
python3 paperkit.py preamble examples/minimal    # 写 audit/preamble.tex
python3 paperkit.py audit  tests/fixtures/redteam-b1   # 1
python3 paperkit.py audit  tests/fixtures/redteam-b4   # 1
```
