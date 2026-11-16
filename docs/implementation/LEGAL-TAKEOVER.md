# LEGAL-TAKEOVER｜法律域接管清单

> 日期：2026-11-16
> 起因：法律预研代理被用户销毁，用户裁定**全部接管**。本件是接管盘点结果入仓：
> 资产清单、未了账（松尾账）、接管后维护口径、与 SiAgent 侧的联动指针。
> 盘点纪律：除本件（一个文件、一个 commit）外**全程只读**——未 push、未 merge、未改任何代码。
> 盘点人：G 席接管盘点子代理；解释器＝仓内规范解释器 `.venv`（Python 3.10.20）。

## 0. 结论速览

| 事项 | 结果 |
|---|---|
| fork 分支（remote `fork`＝github.com/UncleMoc/FactScribe，共 41 支） | **全部已并入本地 main**——ancestry（`git branch -r --merged main`）与 patch-id（`git cherry` 每支 `+0/-0`）双证；fork 上**没有**未并的实质工作 |
| fork/main 与本地 main 关系 | fork/main＝`ed878a5`，是本地 main（`f81c514`）的**祖先**，落后 6 commit——落后的恰是法律集成件整批（只推到了 origin，fork 未同步）；**非任务书预估的「同顶 f81c514」**，但无内容丢失 |
| 已合入法律集成件可用性 | 五个子命令（fetch/verify/verify-cn/verify-case/verify-it）`--help` 全通；集成件测试 **50 例 OK（本机 3.10 跳 4 例 tomllib 对照，守卫性行为）**；CI 主矩阵（3.10–3.14）含集成件离线测试行 |
| 松尾账 | 三条：①README 缺 `mark_dup_ok` 说明；②语料抓取脚本与钉版视图**不在本仓、本机未寻获**（随预研代理销毁，位置无据）；③四张码表**均无冻结声明**，且三处码清单不完全一致 |
| 冒烟 | `.venv/bin/python -m factscribe audit examples/minimal --json` → **exit=1**（样例自带 2 红/7 黄，既有行为，非接管引入） |

## 1. 资产清单

### 1.1 已合入件：`integrations/factscribe-legal/`（main 上的法律集成件）

第三方集成件，不进 `factscribe/` 包、不 import 上游、纯标准库；判据边界与设计原理见
`docs/implementation/INTEGRATION-LEGAL.md`（合入件本体文档）。构成：

| 文件 | 责任 |
|---|---|
| `provisions.py` | 法国侧语料读取（LEGI 版本池）、法文数字词→整数、`norm_text` |
| `verify.py` | 法国闸：法条存在性、参考日生效、官方字节哈希、卡片哈希、值出自正文、语料/现行视图一致性 |
| `cn_corpus.py` | 中国侧语料**读取**（FLK catalog 目录树）——注意是读取器，不是抓取器 |
| `cn_verify.py` | 中国法条闸：法规现行有效、条文号存在、官方件未变、卡片链完整 |
| `case_verify.py` | 中国案例闸：案号/日期/金额与官方件一致、卡片正文未分叉、回执链完整 |
| `it_verify.py` | 意大利闸：条文存在、官方 AKN 哈希、条文切片哈希、卡片字段一致、值出自 AKN 正文、参考日版本差 |
| `facts_ledger.py` | 事实账同值检测（`scan_dupes`）与 `dup_ok` 标注（`mark_dup_ok`）——**松尾账 2.1** |
| `_toml.py` | TOML 读取层：3.11+ 用 `tomllib`，3.10 用自带兜底解析器（交叉校验测试锁住） |
| `cli.py` | 五个子命令：`fetch` / `verify` / `verify-cn` / `verify-case` / `verify-it` |
| `tests/` | 50 例离线测试（双向、防假绿、跨版本 TOML 可复现） |

合入批的 commit 链（本地 main＝origin/main＝`f81c514`）：

```
30b5a49  integrations/factscribe-legal: add the legal-dimension gate (FR/CN/CASE/IT)
f246965  docs/implementation/INTEGRATION-LEGAL: where the legal gate lives and what it does not judge
22c76a4  ci: run the factscribe-legal integration tests offline
b470e08  changelog: note the factscribe-legal integration
9cd6a2d  Merge feat/integration-factscribe-legal（--no-ff 合入点）
f81c514  fix(tests): tomllib 兼容例补 3.10 跳过守卫   ← main 顶
```

### 1.2 fork 与 41 分支清点表

remote `fork`＝github.com/UncleMoc/FactScribe（上游 origin＝bigismall-Ai/FactScribe）。
判定方法两证：①`git branch -r --merged main`（祖先关系）②`git cherry main fork/<branch>`
（patch-id 逐支比对）——41 支全部 `+0/-0`，即**没有任何一支含 main 缺失的实质工作**。
「跟 main 比多了什么」一列对所有支均为「无」。下表「定性」取该支顶提交主题（合并入 main 的
历史工作内容），供日后考古索引：

| # | 分支 | 定性（顶提交主题） | 跟 main 比多了什么 |
|---|---|---|---|
| 1 | `main` | fork 主干＝`ed878a5`（旧名清扫收尾），落后本地 main 6 commit（=1.1 表整批） | 无（纯落后） |
| 2 | `feat/integration-factscribe-legal` | 法律集成件开发支（经 `9cd6a2d` --no-ff 并入） | 无 |
| 3 | `feat/adoption-notes` | 已有论文接入实测＋doctor 修掉会失败的修复命令 | 无 |
| 4 | `feat/ai-panel` | AI 起草面板（页面发起 agent＋候选区） | 无 |
| 5 | `feat/ai-session-guard` | 非项目对话打开时 fail-closed | 无 |
| 6 | `feat/asset-math-highlight` | 图片预览、MathML 公式、编辑器语法高亮（零依赖） | 无 |
| 7 | `feat/citations` | 引用页（多 bib 汇总、状态与过滤） | 无 |
| 8 | `feat/doctor` | 上手自检＋五分钟教程＋首次分诊表 | 无 |
| 9 | `feat/draft-facts` | 方法论产出→事实账草稿（批处理，不代签） | 无 |
| 10 | `feat/evidence-api` | 证据冻结 API（serve＋mcp） | 无 |
| 11 | `feat/factgate-miniapp` | Mini App 移植件 | 无 |
| 12 | `feat/factgate-ui-clarity` | UI 清晰化（顶提交为同步 main 的 merge） | 无 |
| 13 | `feat/guide` | 章节增删改＋内置示例论文与新手引导 | 无 |
| 14 | `feat/guide-report` | token 可选、网页自动打开、MiniApp 同服务 | 无 |
| 15 | `feat/html-preview` | 预览改网页渲染；证据冻结按钮移右栏顶部 | 无 |
| 16 | `feat/method-workflows` | 方法论→命令的四道工序接法（brief/check/plan/accept） | 无 |
| 17 | `feat/minifactscribe-workbench` | 连接本地工作台（只读 status/brief/audit） | 无 |
| 18 | `feat/preview-fixes` | 事实追加按钮、报告模板、引用增删；预览补渲染 | 无 |
| 19 | `feat/preview-page` | 预览定位到当前节所在页 | 无 |
| 20 | `feat/project-accordion` | 侧栏树与项目页收尾 | 无 |
| 21 | `feat/project-launcher` | 论文项目＝文件夹，一键启动工作台 | 无 |
| 22 | `feat/project-management` | 工作台支持不带项目启动、页面里管理项目 | 无 |
| 23 | `feat/project-page` | 项目页重构（列表＋新建＋引导卡片） | 无 |
| 24 | `feat/remove-draft` | 删旧本地草稿（界面＋Node JS 引擎＋测试） | 无 |
| 25 | `feat/report-p0` | P0 实验报告归一化与事实账导入 | 无 |
| 26 | `feat/report-ui` | 工作台接入实验报告（列表/检查/封存/签收/导入） | 无 |
| 27 | `feat/routing` | 单页分视图（#/workbench、#/reports、#/project） | 无 |
| 28 | `feat/serve` | 本地工作台 HTTP API（factscribe serve） | 无 |
| 29 | `feat/serve-write` | MCP stdio 服务器（factscribe mcp） | 无 |
| 30 | `feat/sidebar` | 侧栏改项目按钮＋章节目录＋事实账；中/EN 与浅/深切换 | 无 |
| 31 | `feat/sidebar-polish` | 侧栏加宽、章节编号、去折叠与竖线 | 无 |
| 32 | `feat/three-col` | 工作台左中右三栏 | 无 |
| 33 | `feat/unified-ui` | 网页与 MiniApp 共用一套界面，宿主检测分区 | 无 |
| 34 | `feat/web-build` | 本地工作台编译 PDF | 无 |
| 35 | `feat/web-fact-form` | 本地工作台事实表单 | 无 |
| 36 | `feat/web-ui` | 本地工作台页面（factscribe web） | 无 |
| 37 | `feat/workbench-redesign` | 工作台改版（90vh 编辑卡、快捷插入、绿色保存） | 无 |
| 38 | `fix/doctor-and-paths` | 配置路径越界与 doctor 的源码仓误判 | 无 |
| 39 | `fix/packaging-and-ledger` | CI preflight 跟上 3.13/3.14 矩阵 | 无 |
| 40 | `fix/single-file-sections` | 单文件章节修复（顶提交为同步 main 的 merge） | 无 |
| 41 | `rename/minifactscribe` | Mini App 移植件 FactGate→MiniFactScribe 改名 | 无 |

**fork 处置建议**：全部已并，历史无损。fork 端 41 支属「可清理」而非「须抢救」——是否删
远端分支属用户/主编排裁量，本盘点不动。fork/main 落后 6 commit，如需镜像一致可把 origin/main
再推到 fork（本次未做，遵守「禁 push」）。

### 1.3 本仓本地分支接管面

| 分支 | 状态 | 内容 |
|---|---|---|
| `spec/check-contract-draft` | **未并入** | `f543f2f`：`docs/design/SPEC-CHECKS-draft.md`（359 行）核验槽修约稿——用户四步走裁定的第②步产物，**候批**（未批不动 CHANGELOG、不冻结、不合 main）；另有 `21d9b8d` 为 tomllib 守卫的孪生提交（树哈希与 `f81c514` 同） |
| `feat/check-slot-m1` | **未并入**（worktree 检出中） | M1 批（论文三闸锁死重构进核验槽）在制面，属四步走第③步 |
| 其余本地支（pr-1、pr-2、feat/host-workspace、feat/sections-crud，共 4 支） | 已并入 | 与 fork 同源历史（本地另有约 39 支与 fork 同名的已并支），无独有工作 |

## 2. 松尾账（接管时点未了的债，逐条含处置建议）

### 2.1 README 缺 `mark_dup_ok` 说明

**事实**：`facts_ledger.py:51` 定义 `mark_dup_ok(project_dir)`（另有 `scan_dupes`）——
扫项目内全部 `facts/*.toml`，给「同值且 claim 不同」的事实**原地**补 `dup_ok = true`
（幂等）；这是上游 R-04 `DUPLICATE_VALUE`（黄）的显式承认通道。
**三无**：README 无一字提及；CLI 不暴露（`cli.py` 仅五个子命令，见 1.1）；测试零引用
（grep 全集成件零命中）。

**处置建议**：README 补「事实账维护」一节——写清三点：库级函数（无 CLI，调用形
`python3 -c "from factscribe_legal.facts_ledger import mark_dup_ok; mark_dup_ok('.')"`）；
**原地改账语义**（直接改写 `facts/*.toml`，跑前自担备份）；幂等可重跑。顺带补一条测试
（当前零覆盖），并同批修一处措辞漂移：README 第 9 行自称对比对象还是旧名「paperkit」
（仓现行名＝factscribe，见 P-095 旧名清扫批）。

### 2.2 语料面：官方件从哪来、钉版视图存哪、抓取脚本在不在仓

**官方通道**（README「语料从哪来」节已记，均为开放数据通道非爬页面）：

| 法域 | 通道 | 形态 | 许可 |
|---|---|---|---|
| 法国 | DILA LEGI 增量包（echanges.dila.gouv.fr/OPENDATA/LEGI/） | 官方条文 XML | Etalab 开放许可 |
| 中国法条 | 国家法律法规数据库（FLK）详情 JSON | 官方 JSON（不含条文正文） | 官方公开接口 |
| 中国案例 | 人民法院案例库入库案例正文 | 官方正文＋回执链 | 官方用户协议 |
| 意大利 | Normattiva OpenData API（caricaAKN） | 官方 AKN XML | CC BY 4.0 |

**抓取脚本不在本仓**：全仓 grep 仅 `cn_corpus.py`（读取器）；README 明言「取件、钉哈希、
建卡、选版的脚本在各自的工程仓里」——**该工程仓随预研代理一并销毁，位置无据可查**
（本机 `mdfind`＋`find /Users/moc` 深度 4 搜 `catalog_full.jsonl.gz`、`merged_current.jsonl`、
`run-*-legal`、`*legifrance*` 均零命中）。

**钉版视图同样不在**：四闸消费的运行时产物（`runs/<run>-legal/`＝official XML＋证据卡＋
index.json、`out/legifrance/view_*/merged_current.jsonl`、`out/cn/catalog_full.jsonl.gz`、
`runs/<run>-it/`）均为路径约定、不入 git；本机未寻获任何实例。

**影响面**：`verify`（法）、`verify-cn`、`verify-it` 需语料/目录/视图才能真跑；
`verify-case` 只需项目内卡片与官方件；**离线 50 例测试不依赖任何外部语料**（所以测试与
CI 不受影响）。

**处置建议**：①先向用户确认工程仓有无另存（回收站／远端备份）；②若无，按上表官方通道
**重建抓取脚本**（许可均允许重取；注意 INTEGRATION-LEGAL §5.3 日期纪律——取件必须带
参考日参数 `dataVigenza`，判版本时效比取件参数而非文本日期戳）；③重建后**把抓取脚本收编
入仓**（集成件「只消费钉好哈希的官方件」的纪律不变，但脚本本身入仓，消除再次单点丢失）；
④重建前语料目录缺失属预期失败，不要把「跑不了真语料」误判为闸坏。

### 2.3 四张码表全集与冻结状态

**冻结状态：尚无任何冻结声明**（集成件内 grep 冻结/frozen/FREEZE 零命中）——码表当前是
「双向测试事实上锁住」，不是「声明冻结」。且三处清单不完全一致：README 表、
INTEGRATION-LEGAL 表各列 11/11/8/10 码，`verify.py` docstring 另声明一条
`LEGAL_FACT_NOT_PROVISION`（**无发射点**，grep 全文件仅 docstring 一处）。
接管基线以**发射点**为准：

| 闸 | 红（发射点在括注文件内） | 黄 |
|---|---|---|
| `verify`（法） | `LEGAL_PROV_UNKNOWN`、`LEGAL_PROV_NOT_IN_FORCE`、`LEGAL_PROV_HASH_MISMATCH`、`LEGAL_CARD_SHA256_MISMATCH`、`LEGAL_CARD_NO_HASH`、`LEGAL_QUOTE_MISMATCH`（verify.py） | `LEGAL_PROV_SCHEDULED`、`LEGAL_PROV_REPEALED`、`LEGAL_PROV_VIEW_MISMATCH`、`LEGAL_PROV_AMBIGUOUS`、`LEGAL_COVERAGE_GAP` |
| `verify-cn` | `CN_PROV_UNKNOWN`、`CN_PROV_NOT_IN_FORCE`、`CN_ARTICLE_NOT_FOUND`、`CN_CARD_MISSING`、`CN_CARD_NO_HASH`、`CN_CARD_SHA256_MISMATCH`、`CN_OFFICIAL_HASH_MISMATCH`、`CN_VALUE_MISMATCH`（cn_verify.py） | — |
| `verify-case` | `CASE_OFFICIAL_MISSING`、`CASE_CARD_MISSING`、`CASE_OFFICIAL_HASH_MISMATCH`、`CASE_NO_MISMATCH`、`CASE_DATE_MISMATCH`、`CASE_AMOUNT_MISMATCH`、`CASE_VALUE_NOT_IN_OFFICIAL`、`CASE_CARD_TEXT_DIVERGED`、`CASE_CHAIN_BROKEN`（case_verify.py） | — |
| `verify-it` | `IT_PROV_UNKNOWN`、`IT_CARD_MISSING`、`IT_CARD_NO_HASH`、`IT_CARD_SHA256_MISMATCH`、`IT_SOURCE_HASH_MISMATCH`、`IT_ARTICLE_HASH_MISMATCH`、`IT_ARTICLE_NOT_IN_SOURCE`、`IT_CARD_FIELD_MISMATCH`、`IT_QUOTE_MISMATCH`（it_verify.py） | `IT_VERSION_GAP` |

文档声明态额外一条：`LEGAL_FACT_NOT_PROVISION`（verify.py docstring，「事实声称来源是
法条但 source 指向的不是 provisions/」）——**已声明未发射**；要么补实现要么从 docstring
摘除，任选其一，接管后第一批文档修缮时处理。

**处置建议**：①接管基线期**不动码表**；②修约方向＝核验槽「码表注册制」（SPEC-CHECKS-draft
候批稿：各核验包声明自己的码表进统一注册表，core 统一收发现）——未批前本件码表按兵不动；
③注册制落地前若确需改码，先在 INTEGRATION-LEGAL.md 加「码表变更记录」节逐条留痕，
同时同步 README 表，防三处清单继续漂移。

## 3. 接管后维护口径

1. **上游零改动纪律不变**：`factscribe/` 一行不改；集成件不 import 上游、纯标准库、
   退出码沿用冻结契约（0 绿 / 1 红 / 2 配置错 / 3 黄）。
2. **码表**：未声明冻结前以双向测试为闸（每条红码「必须触发＋不该触发」两用例）；
   修约走核验槽注册制方向（§2.3 建议③）。
3. **语料视图钉版是核心资产**：官方字节哈希钉进 index.json 与证据卡、卡哈希再被事实账
   `source_sha256` 钉住——两层证据模型（卡层＋官方字节层）不重叠、缺一不可。视图丢失可
   经官方通道重取（许可允许），但**版本选点必须带参考日参数**重现（§2.2 建议②）。
4. **fetched 语料在仓外**：现行路径约定＝`runs/<run>-legal|<run>-it/`、
   `out/cn/catalog_full.jsonl.gz`、`out/legifrance/view_<date>/merged_current.jsonl`
   （README 用法节）。再取方法＝先补工程仓存档，无存档则重建脚本（§2.2）。
5. **验证命令**（接管人自验四件套，均在仓根跑）：
   ```bash
   .venv/bin/python -m unittest discover -s integrations/factscribe-legal/tests   # 50 例
   .venv/bin/python -m factscribe audit examples/minimal --json; echo $?           # 冒烟 exit=1
   env PYTHONPATH=integrations/factscribe-legal .venv/bin/python -m factscribe_legal verify --help  # 五子命令逐一
   git branch -r --merged main | grep -c 'fork/'                                   # 分支并况
   ```

## 4. 与 SiAgent 侧的联动指针

- **P-081**（`.backlog` seq110，挂账）：法律域未来方向＝「数字/引用对账闸门」方法论接入
  法条＋判例＋案件对比启示；立名动工前按词册纪律探公开锚（候选：cite-checking／
  Shepard's signal＝判例效力核验成熟实务；case-based reasoning）。
- **P-084 教训**（seq113）：旧名清扫改字节 → paper-b/paper-b-zh 各 47 条 fact 的
  `source_sha256` 失配（红 94 处）；`supersedes` 追加路对 sha 钉定**结构性不通**（sha 判红
  不豁免＋证据链回执钉 id），规定动作＝**原地改锚**（只改失配行、diff 验证零杂改）。
  接管后凡动官方件或证据卡字节，事实账 `source_sha256` 必同步重签。
- **SPEC-CHECKS-draft**（本仓分支 `spec/check-contract-draft`，`f543f2f`，候批）：核验槽
  修约稿——core 只造统一核验槽，论文三闸重构为第一个核验包（paper），**法律件注册为第二个
  （legal）**；内含「码表注册制」节＝本件码表修约的方向锚。未批不动 CHANGELOG、不冻结、
  不合 main。
- **四步走与 M0 收官**（`.backlog` P-099，seq128，账面当前最新）：用户拍板四步全部要做——
  ①M0 法律集成件合入 main（`9cd6a2d`＋守卫 `f81c514`＋四门重验＋推送 `ed878a5..f81c514`，
  已收官）②SPEC-CHECKS-draft 修约稿（落分支候批）③M1 论文三闸锁死重构（`feat/check-slot-m1`
  在制）④M2 法律挂槽双域报告。附两课：门禁必须用仓内规范解释器（3.14 系统解释器曾误绿）；
  并行子代理各分独立 git worktree。
- 账号勘误：接管任务书引「P-098 后的注册制」；`.backlog` 账面 **P-098＝facetbench 飞轮批**、
  **四步走拍板＝P-099**——注册制方向本体见 SPEC-CHECKS-draft.md，挂账号以 P-099 为准
  （盘点时点账面 seq 128 止）。
- 本次接管裁定（销毁法律预研代理、全部接管）尚待主编排按候办账纪律落 `.backlog`，本件
  不代记。

## 5. 接管时点验证读数（2026-11-16，解释器＝仓内 `.venv` Python 3.10.20）

- **五子命令 `--help` 全通**（`usage:` 行均正常输出，argparse 零异常）：
  `fetch`（`--corpus --project --nums`）、`verify`（`--project --corpus --date [--view]`）、
  `verify-cn`（`--project --catalog --date`）、`verify-case`（`--project`）、
  `verify-it`（`--project --corpus --date`）。
- **集成件测试**：`Ran 50 tests ... OK (skipped=4)`——4 跳全是「本解释器没有 tomllib
  （3.10），跳过对照」的守卫性行为（`f81c514` 所补），CI 3.11+ 全跑；上游自身回归
  1357 例读数见 P-099（本批未重跑上游全套）。
- **CI 矩阵**：`.github/workflows/test.yml` 主矩阵 python `["3.10","3.11","3.12","3.13","3.14"]`
  五版，集成件离线测试行在 test.yml:61-62（`python -m unittest discover -s
  integrations/factscribe-legal/tests -v`，注释明言放进主矩阵是有意的——3.10 兜底解析器
  的回归线）；另有 node 矩阵行。
- **冒烟**：`.venv/bin/python -m factscribe audit examples/minimal --json` → `"status":
  "red"`, `"exit": 1`（2 红＝UNMATCHED_NUMBER/MISSING_CITE，7 黄；样例自带，非接管引入）。
- **分支双证**：41 支 `git branch -r --merged main` 全中；`git cherry` 逐支 `+0/-0`。
