# 社区包重新 vendor —— 回灌 Node 侧行尾层 ＋ 按清单重新 vendor

日期：2026-11-27　｜　分支：`feature/community-revendor-20260127`（基于 `origin/main` `a7f5e012`）
工作树：`.worktrees/community-revendor-20260127`　｜　上游只读：`MiniMax-AI/MiniMax-Code-MiniApps` @ `be73247c`（PR #160 已合并）

> 上游只做了 clone/fetch 与只读比对：**没有 push、没有评论 PR #160、没有改上游任何状态**。
> 主检出 `factscribe-dev` 与其它工作树全程只读（读数见 §6）。

## 0. 结论先说

1. **上游独有的 Node 侧行尾层已回灌进本仓**：`miniapp/miniapp/node/eol.mjs`（163 行）与 `server.mjs` 的 4 处行尾处理（写盘路由 `handleManuscriptWrite`、写前 `toLfOnly`、写后 `restoreSnapshotEndings`、路由分流），逐字节与上游 `be73247c` 一致（`cmp` 通过）。
2. **两套行尾口径不打架**——不是推理，是差分实测：同一批 9 组场景跑两遍（Node 层开／关），8 组落盘字节逐字节相同；剩下 1 组有差别，且是 Node 层更贴合契约（§3）。全部 9 组 `\r\r\n` 计数为 0，LF 稿子没有被翻成 CRLF。
3. **生成物本来就是新的**：重跑 `miniapp/build.sh` 后 `git status` 干净——`factscribe/` → `miniapp/node/engine/factscribe/`、`workbench/static/` → `miniapp/client/`、`style-rules.toml` 三处**零漂移**（§4）。所以本单没有「vendor 生成物」那笔提交，这是实测结论不是漏做。
4. **A6 拿到了硬证据**：同一份 CRLF 稿子插 AI 草稿，本仓版本落盘 818 字节／18 CRLF／0 落单 LF；上游 #160 合并版落盘 811 字节／11 CRLF／**7 落单 LF**（草稿块是 LF）。上游那处硬编码 `"\n"` 确实坏了，这次修回来了（§5）。
5. **上游 PR 的料备好了**：fork 分支工作副本、文件级 diff 摘要（47 文件 ＋5853／−560）、英文 PR 正文全文都在 `/tmp/fork-pkg/`（§7）。**未推远端、未建 PR**。

## 1. 两笔提交（可各自独立回退）

| # | commit | 目的 | 回退方式 |
| --- | --- | --- | --- |
| 1 | `59b014a` feat(miniapp): 回灌上游 Node 侧行尾层 | 把上游 `be73247c` 的 `eol.mjs`＋`server.mjs` 4 处 hunk＋`tests/eol.test.mjs` 拿进本仓 | `git revert 59b014a` |
| 2 | `1ca7dec` chore(miniapp): 包元数据与 README 对齐上游口径 | `plugin.json` 1.2.0／`UncleMoc · BGISMALL`、`LICENSE` 署名、两份 README 的行尾段与实测读数 | `git revert 1ca7dec` |

两笔互不相干：回退第 1 笔只去掉 Node 侧那一层（引擎侧行尾口径原样还在）；回退第 2 笔只动元数据与文档。

## 2. 已盘点清单的落位（A1–A11／B1–B5）

| # | 项 | 落位 | 本仓证据 |
| --- | --- | --- | --- |
| A1 | 探针改听 `close` | `miniapp/miniapp/node/python_discovery.mjs:259` | 与上游同文件只差这一处 |
| A2 | 段落级前端三样能力 | `miniapp/miniapp/client/{app.js,index.html,app.css}` | 相对上游 ＋361／−1 行 |
| A3 | 引擎侧行尾保真与指纹同源 | `factscribe/textio.py`、`workbench/write.py`、`workbench_dataplayer.py` | 已在 main，随 vendor 进包 |
| A4 | 严格 3.10 TOML 兜底解析器 | `factscribe/config.py:136 _MiniTomlParser` | 已在 main，随 vendor 进包 |
| A5 | 事实账软链信任根 | `factscribe/safepath.py`（新文件）、`facts.py`、`scaffold.py`、`cli.py` | 码：`FACT_FILE_OUTSIDE_PROJECT`／`FACT_FILE_UNRESOLVED`，exit 5 |
| A6 | 草稿块行尾按文件主导行尾 | `factscribe/workbench/write.py:1371-1375` | 随 vendor 进包；§5 有实测 |
| A7 | 判定码闭集补齐 | `factscribe/constants.py`（`ASSET_NOT_FOUND` 已登记） | 随 vendor 进包 |
| A8 | `serve --ui` 404 | `factscribe/serve.py` | 随 vendor 进包 |
| A9 | 新底座三文件 | `factscribe/safepath.py`、`factscribe/workbench.py`、`factscribe/workbench/assets.py` | 已在 main，随 vendor 进包 |
| A10 | 状态码透传 8 例回归锁 | `miniapp/tests/save-status-passthrough.test.mjs` | 本仓新增，随包发布 |
| A11 | 草稿行尾回归锁 | `miniapp/tests/save-draft-eol.test.mjs` | 本仓新增，随包发布 |
| B1 | 上游独有 `eol.mjs` | 回灌进本仓 `miniapp/miniapp/node/eol.mjs` | 与上游逐字节相同 |
| B2 | 上游独有 Node 侧写盘路由 | 回灌进本仓 `server.mjs`（＋208 行） | 与上游 `server.mjs` 逐字节相同 |
| B3 | 上游独有 `tests/eol.test.mjs`（16 例） | 回灌进本仓 `miniapp/tests/eol.test.mjs` | 与上游逐字节相同 |
| B4 | 包元数据（1.2.0／`UncleMoc · BGISMALL`） | `miniapp/.minimax-plugin/plugin.json` | 与上游同口径 |
| B5 | `LICENSE` 署名 `UncleMoc (BGISMALL)` | `miniapp/LICENSE` | 与上游同口径 |

## 3. 两套行尾口径会不会重复摆行尾 —— 差分实测

### 3.1 方法

同一批场景跑两遍，一遍带 Node 侧行尾层，一遍把它的路由拦截止（`const writeMatch = null;`，其余一字不改），
其余（引擎、样例盘、请求体、落盘位置）完全相同，比落盘字节。

场景 3 种稿子 × 2 种操作 × 2 种正文改动 ＝ 9 组：
CRLF／LF／混合行尾 × {段落保存（正文改／不改）、AI 草稿插入}。

### 3.2 读数

| 场景 | 落盘前 | 落盘后（Node 层开） | 落盘后（Node 层关） | 开 vs 关 |
| --- | --- | --- | --- | --- |
| crlf-edit-same | 11 CRLF | 11 CRLF / 0 LF | 同左 | **逐字节相同** |
| crlf-edit-change | 11 CRLF | 12 CRLF / 0 LF | 同左 | **逐字节相同** |
| lf-edit-same | 0 CRLF / 11 LF | 0 CRLF / 11 LF | 同左 | **逐字节相同** |
| lf-edit-change | 0 CRLF / 11 LF | 0 CRLF / 12 LF | 同左 | **逐字节相同** |
| mixed-edit-same | 1 CRLF / 10 LF | 1 CRLF / 10 LF | 同左 | **逐字节相同** |
| mixed-edit-change | 1 CRLF / 10 LF | 1 CRLF / 11 LF | 1 CRLF / 11 LF（行尾落点不同） | **有差别** |
| crlf-draft | 11 CRLF | 18 CRLF / 0 LF | 同左 | **逐字节相同** |
| lf-draft | 0 CRLF / 11 LF | 0 CRLF / 18 LF | 同左 | **逐字节相同** |
| mixed-draft | 1 CRLF / 10 LF | 1 CRLF / 17 LF | 同左 | **逐字节相同** |

- 全部 9 组：`\r\r\n` 计数 **0**（没有「CRLF 摆两次」）；LF 稿子没有被翻成 CRLF（没有「LF 摆回 CRLF」）。
- **结论：不会重复摆行尾。** 9 组里 8 组 Node 层是**纯兜底**（引擎已经处理好时它一个字节都不改）。

### 3.3 唯一有差别的那组：不是打架，是补位

`mixed-edit-change`（混合行尾＋改了正文）：

- **Node 层关**：标题行 `\section{Introduction}` 原来的 CRLF 变成了 LF；新插入的行拿到了 CRLF。
- **Node 层开**：标题行保住原来的 CRLF；新插入的行按文件主导行尾（该文件 LF 多）落 LF。

为什么会这样（逐行核到引擎）：被改的块是**标题块**，`block.raw` 只含标题文字、**不含它后面的那个行尾分隔符**。
引擎的 `restore_newlines`（`factscribe/textio.py:157`）是**块级**的：`original` 为空行尾时 `inherited.get(index)` 取到空串，
`or extra` 于是换成 fallback（文件主导行尾），标题行尾就此丢掉。Node 侧的 `restoreOriginalEndings` 是**整文件级**的，
它按「内容没变的行 → 沿用原文件那一行的行尾」重新摆，把标题行的 CRLF 摆回来了。

**收敛口径**：引擎侧为准、Node 侧只在引擎没管到的地方兜底。这条差分正是兜底生效的证据——
Node 层没有覆盖引擎的任何正确决定（其余 8 组逐字节相同），它补的是引擎块级视野看不到的那一处。
上游 `server.mjs` 的写盘路由只拦 `/edit` 与 `/proposal/<id>/confirm`，**不拦** AI 草稿插入（`/draft/insert`），
所以草稿路径只走引擎侧，不受 Node 层影响。

## 4. 生成物零漂移

```
$ cd miniapp && ./build.sh
[1/4] vendor Python 引擎：factscribe/ → miniapp/node/engine/factscribe/
[2/4] 同步前端：workbench/static/ 三件 → miniapp/client/（零改动拷贝）
[3/4] 契约自检（miniapp/ 全目录）
  文件数：127（上限 1024）
  总体积：5.1 MiB（上限 64 MiB）
  契约自检通过。
[4/4] 引擎自检：vendored 包可被 import（-B：不往载荷里写 __pycache__）
  engine import ok
build 完成：112 个载荷文件。

$ git status --short      # build.sh 跑完，工作树**一个字节都没变**

$ diff -rq factscribe miniapp/miniapp/node/engine/factscribe   → 0 条差异
$ cmp factscribe/workbench/static/{index.html,app.js,app.css} miniapp/miniapp/client/…  → 3/3 一致
$ cmp style-rules.toml miniapp/miniapp/node/engine/style-rules.toml  → 一致
```

**读数含义**：本仓 `origin/main`（`a7f5e012`）上的生成物本来就是新的，重跑 `build.sh` 是幂等的，
所以本单**没有**「重新 vendor 生成物」那笔提交——这是实测结论，不是漏做。生成物随第 1、2 笔提交一起进仓。

手写件逐份人工确认：`plugin.json`、`LICENSE`、`README.md`、`README.zh-CN.md`、`node/server.mjs`、
`node/python_discovery.mjs`、`node/eol.mjs`、`tests/*.test.mjs` —— build.sh 一律不碰这九类，
本单只动了其中五类（`plugin.json`／`LICENSE`／两份 README／`server.mjs`），其余保持与上游或 main 同字节。

## 5. A6 专项：CRLF 稿子插 AI 草稿（实测证据）

同一份 CRLF 稿子（样例盘 `sections/01-intro.tex`，678 字节／11 CRLF），走真实路径
`POST /api/disk/<project>/<disk>/draft/insert`，两边都跑真引擎：

| | 落盘前 | 落盘后 | 草稿块内 | `\r\r\n` | 草稿块外与落盘前逐字节相同 |
| --- | --- | --- | --- | --- | --- |
| **本仓版本** | 678 B／11 CRLF／0 落单 LF | **818 B／18 CRLF／0 落单 LF** | 5 CRLF／0 LF | 0 | **是** |
| **上游 be73247c** | 678 B／11 CRLF／0 落单 LF | 811 B／11 CRLF／**7 落单 LF** | **0 CRLF／5 LF** | 0 | 否 |

上游那版把草稿块整块写成 LF（`workbench/write.py` 里 `_draft_region` 用 `"\n".join(lines)`），
同一份稿子保存后变成一半 CRLF 一半 LF。本仓版本按**所在文件的主导行尾**落草稿块（
`workbench/write.py:1371-1375`，`eol = dominant_newline(source)`），草稿块是 CRLF，全文再无落单 LF。

回归锁：`miniapp/tests/save-draft-eol.test.mjs`（2 例）把这条钉住——CRLF 稿插草稿后
`/(?<!\r)\n/` 必须一个都不匹配，且除草稿块外原正文逐字节不变。

## 6. 闸门读数

| 闸门 | 读数 |
| --- | --- |
| Node 20.20.2 本仓 `miniapp/tests/` | 32/32 全绿，0 fail，**0 skipped** |
| Node 22.23.5 本仓 `miniapp/tests/` | 32/32 全绿，0 fail，**0 skipped** |
| Node 26.7.0 本仓 `miniapp/tests/` | 32/32 全绿，0 fail，**0 skipped** |
| 构造出的社区包目录（`/tmp/fork-pkg/plugins/unclemoc/factscribe`） | Node 20／22／26 各 32/32 全绿，**0 skipped** |
| 社区包结构 vs 上游 `be73247c` | 完全同构（只多我们那 2 份测试） |
| 社区包契约自检 | 125 文件／5.1 MiB／无软链／路径纯 ASCII／**通过** |
| Python 3.10–3.14 核心套件（`unittest discover -s tests`） | 见 §6.1 |
| Python 3.10–3.14 法律套件（`discover -s integrations/factscribe-legal/tests`） | 各 **216 例全绿**；3.10 上 4 例按设计跳过（§6.2） |
| `scripts/preflight-ci.sh` | 见 §6.1 |
| `scripts/check-readme.py` | 见 §6.1 |
| `tests/golden/audit_findings_baseline.json` vs `a7f5e012` | sha256 `fdf772ab9783bb34a21fd34a674f36195797acb6b39d8ced033c013f23844d40`，**逐字节一致** |
| 27 盘 `audit --json` 逐盘 cmp（26 锁内 ＋ `fixtures/legal-demo`） | **27/27 逐字节相同**（含退出码） |

### 6.1 核心套件与 preflight 的实跑读数

`scripts/preflight-ci.sh`（干净克隆 + 五版本矩阵 + 验收步）实跑：**exit 0，全绿**。

```
== 步骤 1/4：外部依赖 ==
   ✓ pdftotext：/opt/homebrew/bin/pdftotext
   ✓ pdfinfo：/opt/homebrew/bin/pdfinfo
   ✓ PDF 工具齐备
== 步骤 2/4：干净克隆（只含已提交文件） ==
   ✓ 克隆到 …/factscribe-ci.OLZVpB/repo（HEAD 1ca7dec）
== 步骤 3/4：测试矩阵（CI 是 3.10 / 3.11 / 3.12 / 3.13 / 3.14） ==
   ✓ Python 3.10：Ran 2605 tests
   ✓ Python 3.11：Ran 2605 tests
   ✓ Python 3.12：Ran 2605 tests
   ✓ Python 3.13：Ran 2605 tests
   ✓ Python 3.14：Ran 2605 tests
== 步骤 4/4：验收样例必须 exit 1 ==
   ✓ examples/minimal audit exit=1（红，符合预期）
== 结论 ==
   本地等价 CI 全绿——可以推。
PREFLIGHT_EXIT=0
```

五个版本**都没有出现 `skipped=` 计数**（preflight 在本机有 poppler 时会把任何跳过判为红），
即核心套件在 3.10–3.14 上 **skipped=0**。

`scripts/check-readme.py`（同一干净克隆上跑）：**exit 0，全过**——`style --doc` 两份 README 均 0 条、
28 个子命令全写齐且无多余、联网边界声明行在位、链接检查完成、**测试数 2605**（与实跑一致）。

### 6.2 法律套件在 Python 3.10 上的 4 例跳过——按设计，且与本单无关

`test_toml_compat.TestMiniParserMatchesStdlib` 的 4 例跳过原因写在用例里：
「本解释器没有 tomllib（3.10），跳过对照」——3.10 没有标准库 `tomllib`，没有对照物可比。
在 `origin/main`（`a7f5e012`）上跑同一条命令，读数**完全一样**（3.10 → `OK (skipped=4)`；
3.11／3.12／3.13／3.14 → `OK`，无跳过）。**这不是本单引入的**，也不是靠 skip 掩盖失败：
被跳的是「与标准库对照」这一档，3.10 上其余 212 例照跑。

## 7. 给上游的 PR：备料（未推、未建）

`/tmp/fork-pkg/` 里的东西：

| 文件 | 内容 |
| --- | --- |
| `plugins/unclemoc/factscribe/` | 社区包最终形态（125 个文件，与上游同构） |
| `PR_BODY.md` | **英文 PR 正文全文**（130 行） |
| `DIFF-SUMMARY.md` | 相对上游 `be73247c` 的**文件级 diff 摘要**（逐文件 ＋／− 行数） |
| `CHANGE-LIST.md` | A1–A11／B1–B5 逐项落位表 |

fork 分支工作副本：`/tmp/upstream-miniapps` 的 `feature/factscribe-revendor-20260127`（基于 `be73247c`，提交 `4dadd3f`）。

**相对上游 `be73247c` 的文件级 diff 摘要：47 个文件，＋5853／−560**

| 类别 | 件数 | ＋／− |
| --- | ---: | --- |
| 手写·前端 `miniapp/client/` | 3 | ＋361／−1 |
| 手写·Node 薄壳 `miniapp/node/*.mjs` | 1 | ＋11／−1 |
| 手写·测试 `tests/` | 2（新增） | ＋512／−0 |
| 手写·文档 `README*` | 2 | ＋62／−32 |
| 生成物·vendored 引擎 `miniapp/node/engine/factscribe/**` | 39 | ＋4907／−526 |
| **合计** | **47** | **＋5853／−560** |

新增文件 8 个：`safepath.py`、`workbench.py`、`workbench/assets.py`、
`workbench/static/legal/{index.html,legal.css,legal.js}`、`tests/save-draft-eol.test.mjs`、
`tests/save-status-passthrough.test.mjs`。

**上游那份 `node/server.mjs`／`node/eol.mjs`／`plugin.json`／`LICENSE` 在这份 diff 里没有出现**——
因为本仓已经带着同样的字节过去，回灌是「对齐」而不是「改动」，没有把上游刚合的代码回退掉。

## 8. 漏点与未覆盖（自报）

1. **Windows／Linux 真机没跑**。Windows 解释器发现只有单元测试覆盖，候选表是按平台字符串生成的
   （31–37 条，看设了哪些环境变量），不是在 Windows 上量出来的。
2. **上游 CI 没在这条分支上真跑过**（上游 runner 未跑）。
3. **Node 层每次保存都要给整个稿盘做文本文件快照**（上限 500 个文件／单文件 2 MiB）。大稿盘上这是额外的
   一次全盘读，属于上游引入的代价，本单没有改动它，也没有测过超大稿盘的表现。
4. **`toLfOnly` 会把客户端明确给的 CRLF 抹成 LF**：引擎侧原本的规矩是「客户端明确给了 CRLF 就原样保留」，
   走 Node 层时这条被上游口径盖掉（行尾以磁盘原文件为准）。浏览器本来就恒发 LF，实际踩不到；
   非浏览器调用方（脚本、测试）若刻意发 CRLF，行为与引擎单跑时不同——**本单没有为此写用例**。
5. **「混合行尾」只测了「首行 CRLF、其余 LF」这一种形态**。更复杂的混合形态（多段 CRLF/LF 交错）没单独造例。
6. **`plugin.json` 版本号停在 1.2.0**（按本单口径「对齐上游」）。这条 PR 是功能增量，若要在包里体现版本跃升，
   应改成 1.3.0——**对外发布口径等用户拍板**，本单没有自作主张改。
7. **上游 be73247c 之后 main 上若有新提交**，本单的 diff 基线就是 be73247c；开 PR 前要重新对一次。
8. **法律侧的 4 例跳过**：见 §6.2，是 3.10 没有 `tomllib` 的结构性跳过，与本单无关，但**没有**被本单消除。
9. **`fixtures/legal-demo` 不在金样例锁里**（27 盘里的第 27 盘是它），它与 `origin/main` 逐字节相同，但没有基线文件锁着。
