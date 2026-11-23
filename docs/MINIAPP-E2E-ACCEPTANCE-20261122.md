# FactScribe 论文侧 Miniapp —— 端到端验收报告

- 日期：2026-11-22
- 被测对象：本机 MiniMax Code 宿主里已 publish 的 `factscribe` 插件（宿主载荷 `~/.minimax/plugins/factscribe`）
- 源码：`/Users/moc/workspaces/SiAgent/factscribe-dev/.worktrees/miniapp-host`（分支 `feat/miniapp-host-seam`，验收前 HEAD `c957154`）
- 验收方式：宿主**内置浏览器**（Electron FilePanel，Chromium）打开宿主分配的 `http://127.0.0.1:61039/workbench`，按用户视角逐项点击；截图落盘 `docs/miniapp-e2e-shots/`
- 结论：**9 条路径全部实际点过，8 条一次通过、1 条（P0）当场修复后复测通过**；用户正式稿盘四个目录**零改动**（末尾复核哈希与基线逐字节一致）；P0 已修并带回归测试，P1/P2 共 5 条已分级记录

---

## 0. 测试台与「不碰用户正式盘」的安排

宿主 Miniapp 运行时把「论文根目录」记在插件私有目录 `~/.minimax/v2/plugin-data/liveboards/factscribe/config.json`。验收分两段：

| 阶段 | 根目录 | 用途 |
|---|---|---|
| 准备 | `/tmp/fs-e2e-root` | paper / paper-zh / minimal / legal-demo 的 `cp -a` 副本；写入类操作全在这里 |
| 验收后 | `/Users/moc/workspaces/SiAgent` | 经宿主自带「首次设置」页**还原**回用户原值（截图 `p0-root-restored.png`） |

副本与原盘逐字节一致（`paper` = `defa32b6721310f902…`、`paper-zh` = `b8f79738e113ca04…`，与原盘哈希相同），所以副本上跑出来的行为等同于正式盘。

**为什么必须用副本**：`「打开」一个盘会把 `[workbench].last_opened / last_disk` 写进该盘自己的 `factscribe.toml`（`workbench/write.py::touch_opened`）。路径 1 要求「打开 paper / paper-zh」，在正式盘上做就等于改了用户的盘。

**正式盘零改动复核（验收末尾实测）**：

| 目录 | 基线 sha256（聚合） | 验收后 sha256 | 结论 |
|---|---|---|---|
| `paper` | `defa32b6721310f9024bd8a8173e8c6505d0acf239c3d4e894577b7aaf70db82` | 同左 | 一致 |
| `paper-zh` | `b8f79738e113ca041dc0eabc12ade3d5c360b9926df50171b257f1f74ad1cd2c` | 同左 | 一致 |
| `paper-b` | `565563fbe515b2a06260bb2ce3770bab766a5f5c8953a443969adcdc37857be2` | 同左 | 一致 |
| `paper-b-zh` | `60e30071204e8614610f5dacf58b4389fa8d2af61025b71dcea259246b2194fe` | 同左 | 一致 |

---

## 1. 逐项验收表

### 路径 1 —— 打开项目与稿盘（paper / paper-zh）＋ last_disk 记忆

| 怎么点的 | 预期 | 实际 | 判定 | 证据 |
|---|---|---|---|---|
| 项目列表点「打开」（paper） | 进英文盘 | 封面「Deliver the Evidence, Not the Rules:」，`盘: paper · 英文盘` | 通过 | `p1-paper-en.png` |
| 左上「中/EN」切到 EN/中文 | 切到 paper-zh | 封面「送达证据，而非规则」，`盘: paper-zh · 中文盘` | 通过 | `p1-paper-zh.png` |
| 回「项目管理」→ 再点「打开」（不指定盘） | 仍停在上次开的盘（paper-zh） | 落在 **paper-zh**；服务端 `paper-zh/factscribe.toml` 写入 `last_disk = "paper-zh"`、`last_opened` 更新 | 通过 | `p1-lastdisk-memory.png` |

> 首轮这项**失败**：见缺陷 P0-1。修复后重测通过（控制台零报错，toast「已打开：…」出现）。

### 路径 2 —— 目录树 → 读某一节正文 → 正文直接可编辑 → 保存 → 重开复读

| 怎么点的 | 预期 | 实际 | 判定 | 证据 |
|---|---|---|---|---|
| 右栏目录点「引言」→ 正文滚到该节 | 定位到 01_intro | 正文块 `[data-block-id="01_intro-p1"]` 就位（`sections/01_intro.tex`） | 通过 | `p2-edit-saved.png` |
| 点进该段、打字「[E2E probe 20261122]」、点别处失焦 | 自动保存，提示已保存 | toast「已保存（原稿留在 .bak）」；磁盘 `01_intro.tex` 出现探针，`01_intro.tex.bak` 生成 | 通过 | 同上 |
| 刷新页面 → 重新打开项目 → 复读该段 | 改动还在 | `probePresent = true`，改动落在段中（位置索引 1160） | 通过 | `p2-reopen-persisted.png` |

> 附带发现（记 P2-4）：探针里的数字被内联绑定闸抓住——见「发现」卡 `红 BOUND_MISMATCH：该段绑定 E8，但数字 20261122 不在其 value 里`，四步链从 4/4 掉到 1/4。这反证了闸会咬人，不是缺陷。

### 路径 3 —— 事实芯片 → 证据卡弹层

| 怎么点的 | 预期 | 实际 | 判定 | 证据 |
|---|---|---|---|---|
| 点正文里的 `✓ A1` 芯片 | 弹出证据卡，字段齐全 | 断言「SWE-bench Verified 子集实例数」／值 16／出处 BATCH23-SWB16.md／定位 §一 总表／置信 high／指纹 8c2fe569／页脚完整源路径 | 通过 | `p3-factcard.png` |
| 点证据卡右上「×」 | 能关 | `#factCard.hidden = true` | 通过 | 同上 |

### 路径 4 —— 检查报告（五张卡）＋ EN/ZH 文案切换

| 怎么点的 | 预期 | 实际 | 判定 | 证据 |
|---|---|---|---|---|
| 顶栏「全检一次」→ 展开五张卡（中文界面） | 五张卡都有真读数 | 体检「红 0 · 黄 0」/48 条事实 18 节正文/数字回账 234/234/引用 11/11；发现「0 条·这盘干净」；四步链 3/4；文风闸「黄 1 条」；双语对账「两盘一致」 | 通过 | `p4-report-zh-clean.png` |
| 切 EN → 再「全检一次」 | 文案全英文、无中文残留 | Health / Findings / Four-step chain / Style gate / Bilingual check 全部英文；**残留中文扫描 = 0 命中** | 通过 | `p4-report-en.png` |

> 中文界面那轮的五卡截图见 `p4-report-zh.png`（该轮体检为红 1，是因为我插入的探针数字触发了 `BOUND_MISMATCH`；把副本复原后复跑即回到绿，见 `p4-report-zh-clean.png`）。
> 注意：四步链第 4 步「出证」显示未齐，是**副本环境属性**（副本没有证据冻结流程历史），不是缺陷；原盘自带冻结件时该步为齐。

### 路径 5 —— 机器视图四个分组与绑定读数

| 怎么点的 | 预期 | 实际 | 判定 | 证据 |
|---|---|---|---|---|
| 报告模态切「机器视图」→ 展开四组 | 四个分组标题正常、读数正确 | Ledger 48 rows（账本指纹 8bb13d9c）／Body scan 100% covered（18 节、数字回账 232/232、Unbound 0、Unmatched 0）／Citations & evidence frozen（引用 11/13、冻结件 106 条、指纹 03bd1dae）／Export & commands 4 commands | 通过 | `p5-machine-view.png` |
| 读四组正文 | 绑定状态读数正确 | 同上（EN 盘 232/232，ZH 盘 234/234——两盘数字本来就不同，属数据） | 通过 | 同上 |

> 附带发现：EN 界面下「导出与命令」组的中文命令标签未 i18n（记 P2-1）。

### 路径 6 —— 模型选择下拉（按来源分组、无重复项、思考等级可用）

| 怎么点的 | 预期 | 实际 | 判定 | 证据 |
|---|---|---|---|---|
| 右栏「智能助手」→ 看 Model 下拉 | 按来源分组 | 单组「Host models」，3 项：Host current model / M3.1-Flash / M3 | 通过 | `p6-assistant-models.png` |
| 查重复 | 无重复项 | 重复 value = 0，重复 label = 0（源端 `/api/ai/models` 3 条，另有 `alsoVia` 去重线索，UI 未出现重复项） | 通过 | 同上 |
| 选 M3.1-Flash / M3 / Host current model | 思考等级可用 | M3.1-Flash：8 档（Model default/Default/Low/Medium/High/Extra high/Max/Thinking off）；M3：Model default + Thinking off；Host current model：不支持思考等级 → 控件按设计隐藏 | 通过 | 档位为 DOM 读数（`#aiEffort` 的 options）；面板形态见 `p6-assistant-models.png` |

### 路径 7 —— 助手面板（无多余说明气泡、无「后端：—」占位）

| 怎么点的 | 预期 | 实际 | 判定 | 证据 |
|---|---|---|---|---|
| 打开「智能助手」面板 | 面板干净 | 消息区 `#aiMsgs` 为空（0 条气泡）；无「后端：—」类占位；`#aiSrc` 为空且隐藏；只剩纪律角标 + 三个快捷问句 + 模型行 | 通过 | `p6-assistant-models.png` |

### 路径 8 —— 「待确认」差异卡：四种新单都能建起来 + 采纳后预览＝实际落盘

建单走宿主 MCP 的提议单工具（Agent 侧），页面只负责「待确认」差异卡（写盘必须人在页面点「采纳写回」）。

| 怎么点的 | 预期 | 实际 | 判定 | 证据 |
|---|---|---|---|---|
| `fs_propose_evidence_freeze` | 建单成功、不写盘 | 建成 `prop-...-96bd`，卡上带幂等告警「当前清单与冻结件一致」 | 通过 | `p8-proposals-list.png` |
| `fs_propose_evidence_unfreeze` | 建单成功 | `prop-...-698c` | 通过 | 同上 |
| `fs_propose_add_fact` | 建单成功 | `prop-...-a6ba`（值 16 取自账本既有 A1，未新增任何数字） | 通过 | 同上 |
| `fs_propose_export_bundle` | 建单成功 | `prop-...-07a0` | 通过 | 同上 |
| 刷新页面 → 点「待确认」徽标 | 四张卡都在，每张有 Current / After adopting / 采纳写回 / 驳回 | 徽标显示「Pending 4」，四张卡齐全（Export submission bundle / Unfreeze evidence list / Freeze evidence list / Append fact） | 通过 | `p8-proposals-list.png` |
| 逐张核对「After adopting」与实际落盘 | 预览＝落盘 | 见路径 9 表 | 通过 | 见下 |

### 路径 9 —— 写盘正反两面（含 before_sha 指纹闸）

**反面（未采纳 → 文件逐字节不变）**

| 怎么点的 | 预期 | 实际 | 判定 | 证据 |
|---|---|---|---|---|
| 建 6 张单（4 种 + 2 张改稿）后，对比目标文件哈希 | 建单不写盘 | `sections/02_related.tex`、`facts/a_swebench.toml`、`audit/evidence.lock`、`audit/evidence-log.ndjson` 哈希**全部未变** | 通过 | 见本节哈希 |
| 提议单 A（改稿）全程不采纳 | 目标文件逐字节不变 | 采纳尝试被闸拦下前后，文件 sha256 均为 `9ec41efa3622c846c728…`；`grep 'proposal A' = 0` | 通过 | `p9-block-stale-refused.png` |

**正面（采纳写回 → 落盘内容＝预览内容）**

| 采纳的单 | 预览说会落什么 | 实际落盘 | 判定 | 证据 |
|---|---|---|---|---|
| Append fact | 向 `facts/01-core.toml` 追加一段 `[[fact]]` | `facts/01-core.toml` 新建并写入该段，逐字与预览一致（id/claim/value/source/source_sha256/locator/confidence/derived_from/note 全同）；封面计数由「48 facts」变「49 facts」 | 通过 | `p9-adopt-unfreeze.png`（同屏可见计数变化） |
| Unfreeze evidence | 冻结件保留，日志追加一条 unfreeze | `audit/evidence-log.ndjson` 追加 `{"action":"unfreeze","reason":"端到端验收…","hash_before":"03bd1daeca04461c","at":"2026-11-22"}`；`audit/evidence.lock` sha 未变；`fs_get_evidence_status` 报 `EVIDENCE_UNFROZEN` 并带同一理由与日期 | 通过 | `p9-adopt-unfreeze.png` |
| Freeze evidence | 写 `audit/evidence.lock`（幂等） | 日志追加 `{"action":"freeze","hash":"03bd1dae…","entries":106,"reason":"端到端验收…"}`；锁文件内容 sha 不变（幂等，与卡上告警一致） | 通过 | 同上 |
| Export submission bundle | 收集正文＋账＋文献＋PDF，过清单门 | 产物落在 `/tmp/fs-e2e-root/paper.bundle/`（39 个文件，含 `MANIFEST.sha256` / `BUNDLE-MANIFEST.json` / `refs.bib` / `main.tex` / sections / appendix / tables） | 通过 | `p9-adopt-bundle.png` |
| Edit proposal B（改稿） | 替换 02_related-p1 段 | 落盘文本与预览逐字一致（段尾出现 `[proposal B: …]`，段长 3951→4053） | 通过 | `p9-block-stale.png` |

**指纹闸（BLOCK_STALE）**

| 怎么点的 | 预期 | 实际 | 判定 | 证据 |
|---|---|---|---|---|
| 建改稿单 → **在目标段内部**改一个字（模拟别的写者）→ 回页面点「采纳写回」 | 拒写，不覆盖别人的字 | toast「This paragraph was changed elsewhere」；卡片置 `prop-stale`、采纳钮变灰；文件 sha 前后一致（`9ec41efa…`）、外部改动仍在、提议文本未落盘（`grep 'proposal A' = 0`）；服务端 `write.py::_check_expect_sha` 抛 `BLOCK_STALE`（HTTP 409），单子落 `status=stale` | 通过 | `p9-block-stale-refused.png` |

> 透明说明：`p9-block-stale.png` 是**第一次尝试**——当时我把「外部改动」加在文件末尾（不在目标段内），段指纹没变，闸自然没响、提议被正常采纳；改正做法（改在目标段内）后才是上面的拒写结果。两次都留了图，便于复核。

---

## 2. 缺陷清单

### P0-1（已修）打开任何项目都抛异常，last_disk 记忆与报告/机器视图一起失效

| 项 | 内容 |
|---|---|
| 现象 | 每次点「打开」都报 `TypeError: Assignment to constant variable.`（浏览器控制台，`app.js:1375`），页面无报错提示，只看到「点了没反应」 |
| 根因 | 提交 `aad2e3e` 给 `loadReport()` 追加 `lang` 参数时写成 `reportPath += …`，而 `reportPath` 声明成 `const` |
| 影响面（比报错大得多） | 异常发生在 `openProject()` → `loadDisk()` 里，整条「打开」链当场断掉：`/api/project/opened` 永不执行 ⇒ **last_disk 永不落盘 ⇒ 「打开」永远回落到英文盘**；`loadReport()` / `loadAssembly()` 也不再执行 ⇒ **检查报告与机器视图是空的** |
| 复现步骤 | 打开宿主 Miniapp → 点任一项目「打开」→ 看浏览器控制台 |
| 修复 | `factscribe/workbench/static/app.js`：`const reportPath` → `let reportPath`（并留注释说明为什么必须是 let）；`miniapp/build.sh` 重新同步三份副本；`miniapp publish` 重新发布到宿主 |
| 回归测试 | 新增 `tests/test_miniapp_client_js.py`（3 条）：① 作用域感知的「const 被重新赋值」静态闸（旧 HEAD 正好命中 1 处，新版 0 处）；② 定点断言 `loadReport()` 的 `reportPath` 是 let；③ 真源与两份副本逐字节一致（防止只修一份、宿主跑的和仓里测的不是同一份） |
| 状态 | **已修 + 已发版 + 已回归**（修前失败、修后 9 条路径全通，控制台零报错） |

### P1 —— 无

### P2（记录，未擅自改）

| 编号 | 现象 | 证据 / 定位 | 影响 | 状态 |
|---|---|---|---|---|
| P2-1 | EN 界面下「机器视图 › 导出与命令」四行命令说明仍是中文 | `factscribe/workbench/checkreport.py:559` 硬编码中文 label；EN 界面截图 `p5-machine-view.png` | 英文界面出现中文（文案不完整），不影响功能 | **已修（2026-11-23）**，见 §6 |
| P2-2 | 提议单差异卡的内容（Current / After adopting）由引擎生成，中文硬编码 ⇒ EN 界面下卡片文字仍是中文（卡片标题已 i18n） | `factscribe/workbench/proposals.py`（`before_text/after_text` 生成处）；`p8-proposals-list.png` | 同上 | **已修（2026-11-23）**，见 §6 |
| P2-3 | 「Append fact」卡的来源标注显示「Unknown source」（其余三类显示「From assistant」） | MCP `fs_propose_add_fact` 建单未带 source 字段，UI 无从标注 | 溯源信息缺失（展示层） | **已修（2026-11-23）**，见 §6 |
| P2-4 | `.bak` 只有一格深：第二次保存会把 `.bak` 覆盖成上一版（已编辑版），「原稿留在 .bak」的承诺在连续两次保存后不成立；且**刷新页面会触发一次自动保存** | 实测：首存后 `.bak` 为原稿；刷新页面后再看，`.bak` 已是编辑版（探针文本在 .bak 里） | 误改后无法从 .bak 回到最初原稿；刷新会多一次写盘 | 记录 |
| P2-5 | 追加事实默认落到 `facts/01-core.toml`，而本项目既有账本命名是 `a_/b_/c_…`；采纳后会**新增一个账本文件** | `proposals.py::propose_add_fact` 预览即如此写；`facts/01-core.toml` 已生成 | 账本文件分裂（虽能被 `facts/*.toml` 通配收进来，但命名不一致） | 记录 |

> 另有一条**环境属性**（非缺陷）：`cp -a` 出来的盘没有证据冻结流程历史，所以副本上四步链第 4 步「出证」显示未齐（106/106 但未齐）；原盘自带冻结件时该步为齐。

### 需要用户拍板的口径级事项（本轮未动）

- 无。本轮没有改动任何已定口径（四步链闸门语义、提议单形状校验、双 Profile 契约），也没有重冻 `tests/golden/audit_findings_baseline.json`。
- 若要修 P2-1/P2-2（i18n 补齐），需要动引擎侧文案表与 `?lang=` 传参口径，属「改已定口径」的边界，建议先拍板再做。
- 2026-11-23：用户拍板「那就做 i18n」，P2-1/P2-2/P2-3 已按 §6 补齐。**未改任何已定口径**：四步链闸门语义、提议单形状校验（块形状闸）、双 Profile、P-152、金样例基线，一律未动；翻译只发生在**展示层**，落盘层与 MCP 契约字段一字未改。

---

## 3. 未覆盖到的部分与原因

| 未覆盖 | 原因 |
|---|---|
| 助手面板**实发一轮对话**（点「发送」跑通宿主 Agent 回合） | 需要真实模型调用与长时等待；本轮只验到面板形态、模型清单、思考等级可用，未实发 |
| 顶栏「导出 PDF」「打开目录」「＋新建项目」「＋新建章节」、右栏「更多」里的知识库上传与版式（选刊）配置 | 不在本次 9 条必经路径内；未逐个实跑（不计入判定） |
| 提议单的「驳回」按钮 | 只验了「采纳写回」正反两面；驳回路径未点（建单与采纳已覆盖主要风险面） |
| i18n 逐键全量核对 | 本轮只按要求核了「报告五卡 + 机器视图 + 提议单卡」的残留，未做全键位穷举 |
| 窄屏 / 移动端布局 | 宿主内嵌浏览器为固定桌面视口（2000×1125 device px），无移动端形态 |
| PDF 闸（出证第 4 步）在副本上的通过态 | 副本缺冻结流程历史，见上文「环境属性」 |

---

## 4. 证据文件

- 截图：`docs/miniapp-e2e-shots/`（18 张，已统一降采样到 1280 宽，共约 6.0 MiB）。原件（2000 宽）落在宿主浏览器落盘目录 `~/.minimax/v2/assets/2026/11/22/`。
- 日志与读数：本报告表格中的每一项数字都取自当次实跑（浏览器 DOM/网络读数、宿主控制台、磁盘 sha256、MCP 只读工具返回），没有读代码推断的代替值。
- 复现要点：宿主内嵌浏览器打开 `http://127.0.0.1:61039/workbench`（端口由宿主分配，随运行态变）；测试副本在 `/tmp/fs-e2e-root`（`cp -a` 自正式盘）。

## 5. 本轮改动

| 文件 | 改动 |
|---|---|
| `factscribe/workbench/static/app.js` | `const reportPath` → `let reportPath`（P0-1） |
| `miniapp/miniapp/client/app.js`、`miniapp/miniapp/node/engine/factscribe/workbench/static/app.js` | `miniapp/build.sh` 同步产物 |
| `tests/test_miniapp_client_js.py` | 新增回归闸（3 条） |
| `docs/MINIAPP-E2E-ACCEPTANCE-20261122.md`、`docs/miniapp-e2e-shots/` | 本报告与证据 |

---

## 6. 2026-11-23 补修轮：i18n 三处缺口（已修 + 实跑复验）

- 分支：`feat/miniapp-host-seam`（HEAD `e6c5640` → 本轮提交；**未推远端、未建 PR**）
- 范围：**只修 i18n 三处**（P2-1 / P2-2 / P2-3）；P2-4 / P2-5 与其余 P2 不在本次范围内
- 验收台：宿主**内置浏览器**（Electron FilePanel）打开已 publish 的 `factscribe`
  Miniapp；宿主论文根目录指向 `/tmp/fs-i18n-root`（`cp -a` 自四个正式盘的副本），
  验收后**还原**回 `/Users/moc/workspaces/SiAgent`

### 6.1 修法：展示层与落盘层分离

翻译**只作用在展示层**。系统生成的说明文案拆成两层：

| 层 | 形态 | 谁生成 | 落盘吗 |
|---|---|---|---|
| 展示层 | `key` ＋ `params`（模板目录随载荷发出去） | 引擎给 key/params | 否 |
| 契约／落盘层 | `before_text` / `after_text` / `warnings` / `label` / `note` | 引擎按**中文**目录渲染 | 是（字段值一字未动） |

* 目录落在 `factscribe/i18n.py::WORKBENCH_MESSAGES`（`wb.*`）——与 `finding.*`
  同一套 `render` / `catalog_for` 机制，只是目录分开（真闸的话 vs 工作台的话）；
* 中文模板＝旧硬编码中文**逐字**（测试里抄着旧格式串逐条比对，漂一条就红）；
* 前端按 `state.lang` 渲染（`catalogMsg()` / `renderParts()`，与 `findingMsg()`
  同一条路）；目录缺哪条就回落到中文原话（宁可显示原话，也不半中半英）。

### 6.2 三处缺口的修法

| 缺口 | 根因 | 修法 |
|---|---|---|
| P2-1 | `checkreport.py` 把四条命令标签与说明写死中文 | 标签带 `label_key`、说明带 `note_key`，中文原值仍留在 `label`/`note`（兼容只读旧消费者）；机器视图载荷带 `i18n` 目录子集 |
| P2-2 | `proposals.py` 直接拼中文 `before_text`/`after_text`；`write.py` 的告警也是中文 | 四种新单的正文/告警拆成 `display`（key＋params）；改稿/草稿单的告警同样拆成 key＋params，`warnings` 字段仍是 `list[str]`（形状不动） |
| P2-3 | MCP `fs_propose_add_fact` 把事实的 `source` 平铺进建单体，**覆盖**了提议单的来源 `mcp` ⇒ 卡片显示「来源不明」 | 事实字段改装在 `fact` 子对象里（MCP 工具的**入参 schema 一字未动**）；服务端新旧两种形状都认 |

### 6.3 实跑复验读数（宿主内置浏览器，副本盘）

| 项 | 怎么点的 | 实测读数 | 判定 |
|---|---|---|---|
| EN 机器视图「导出与命令」 | 切 EN → 打开 paper → 全检一次 → 机器视图 → 展开该组 | 四条标签＝`Full gate check (read-only)` / `Ledger check (read-only)` / `Traceability matrix (writes audit/matrix.md)` / `Evidence freeze (writes audit/evidence.lock)`；说明＝`This view is read-only: …`；**CJK 命中 0** | 通过 |
| EN 提议单（4 新 + 既有 edit） | 待确认徽标 → 逐张卡片读 DOM | 五张卡的 Current / After adopting / 告警**全英文**，**CJK 命中 0**（含 edit 卡告警 `The deleted cmd marker was restored…`） | 通过 |
| EN 追加事实卡来源 | 同上 | `From assistant`（修前是 `Unknown source`） | 通过 |
| ZH 机器视图 + 提议单 | 点「中」切到 paper-zh | 四条标签与说明回中文；五张卡正文/告警回中文；来源＝`来自助手` | 通过 |
| 落盘＝预览 | 采纳「追加事实」 | `facts/01-core.toml` 里的 `[[fact]]` 段与卡片预览**逐字一致**（预览 303 字节 ＋ 文件末尾换行） | 通过 |
| 不采纳＝零写入 | 另外三张单不采纳 | `audit/evidence.lock` `5e4e33bc8a00133c` / `audit/evidence-log.ndjson` `9b16ff9c41b260da` 前后一致；无投稿包目录 | 通过 |
| BLOCK_STALE 拒写 | 改稿单 → 段内外部改动 → 点采纳 | toast `This paragraph was changed elsewhere`；`sections/01_intro.tex` 哈希前后一致；提议文本未落盘（`grep 'i18n probe'`＝0）；外部改动仍在 | 通过 |
| 控制台 | 全程 | 零 warn / 零 error | 通过 |

### 6.4 正式稿盘零改动（实测）

四个正式盘的聚合 sha256 与本轮开工前**逐字节一致**：

| 目录 | 基线 | 验收后 | 结论 |
|---|---|---|---|
| `paper` | `defa32b6721310f9` | 同左 | 一致 |
| `paper-zh` | `b8f79738e113ca04` | 同左 | 一致 |
| `paper-b` | `565563fbe515b2a0` | 同左 | 一致 |
| `paper-b-zh` | `60e30071204e8614` | 同左 | 一致 |

本轮所有写操作都在 `/tmp/fs-i18n-root` 副本上；宿主论文根目录已**还原**回
`/Users/moc/workspaces/SiAgent`；测试用的提议单已逐张「驳回」，不留待确认单。

### 6.5 本轮改动清单

| 文件 | 改动 |
|---|---|
| `factscribe/i18n.py` | 新增 `WORKBENCH_MESSAGES`（`wb.*` 双语模板）＋ `part`/`literal`/`render_parts`/`parts_keys`；`template_for`/`render`/`catalog_for` 改为可传目录 |
| `factscribe/workbench/proposals.py` | 四种新单的正文/告警拆成 `display`（key＋params）；中文原话由目录渲染（逐字不变）＋ `display_catalog()` |
| `factscribe/workbench/write.py` | 保护面/块形状告警拆成 key＋params（`warnings` 仍是 `list[str]`） |
| `factscribe/workbench/checkreport.py` | 机器视图命令标签/说明带 `label_key`/`note_key`；载荷带 `i18n` 子集 |
| `factscribe/workbench/proposal.py` | 追加事实的 `fact` 子对象（来源不串） |
| `factscribe/workbench/server.py` | 提议单列表响应带 `i18n` 目录子集 |
| `factscribe/workbench/static/app.js` | `catalogMsg()`/`renderParts()`；差异对比用**渲染后**的文本；告警按 lang 渲染 |
| `miniapp/miniapp/node/server.mjs` | `fs_propose_add_fact` 的事实字段装进 `fact` 子对象（修来源覆盖） |
| `tests/test_workbench_i18n_display.py`（新） | 中文原话逐字不变、EN 零中文、目录齐全、展示层＝落盘层、来源不串、机器视图 key、前端接线 |
| `tests/miniapp_mcp_driver.mjs` / `tests/test_miniapp_mcp_tools.py` | MCP 协议面读回提议单，断言追加事实单的来源＝`mcp` |
| `miniapp/miniapp/client/app.js`、`miniapp/miniapp/node/engine/factscribe/**` | `miniapp/build.sh` 同步产物（契约自检通过：110 文件 / 4.7 MiB） |

全仓 `pytest tests/ -q`＝**2193 passed / 0 failed**（397 subtests；基线 2170，本轮 +23）。
新增测试：`tests/test_workbench_i18n_display.py`（19 条：中文原话逐字不变 ＋ EN 零中文 ＋ 目录齐全 ＋ 展示层＝落盘层 ＋ 来源不串 ＋ 机器视图 key ＋ 前端接线）＋ `tests/test_miniapp_mcp_tools.py`（+1 条：MCP 协议面读回提议单，来源＝`mcp`）。

### 6.6 本轮明确**没动**的东西

| 事项 | 怎么保证没动 |
|---|---|
| 四步链闸门语义 | `checkreport._chain_steps` 未改 |
| 提议单形状校验（块形状闸） | `_block_shape_guard` 的判定与硬闸未改，只把告警文案拆成 key＋params |
| 双 Profile 契约 / P-152 | 未触及任何判定面 |
| `Issue.as_dict()` 的形状 | 未改（金样例逐字节锁） |
| `tests/golden/audit_findings_baseline.json` | **未重冻、未改一个字节** |
| 既有提议单字段（`before_text`/`after_text`/`warnings`/…） | 逐字不变（测试抄旧格式串比对）；只**加**了 `display` 字段 |
| MCP 工具的入参 schema | `fs_propose_*` 的入参一字未动（`fact` 子对象只是服务端内部形状） |
| 其余 P2（P2-4 `.bak` 深度 / P2-5 账本命名） | 仍记录，未擅改 |

## 7. 2026-11-23 第三轮：追加事实的两步表单（新增能力，实跑通过）

### 7.1 这一轮补的是什么

界面上原本**没有**追加事实的入口：MCP 侧的 `fs_propose_add_fact` 能建单，
但页面只能 list／confirm／reject，不能自己建单。更要紧的是核心侧只能把事实
写进**固定那本账**（`facts/01-core.toml`）——与本盘的主题账本文件
（`facts/a_swebench.toml` … `facts/h_conflicts.toml`）对不上。

这一轮补三件：

1. **核心新增「指定目标账本文件」能力**（`factscribe/scaffold.py` 的
   `resolve_ledger`）：目标文件必须仍在项目声明的 facts glob 里，且必须是
   该 glob 目录下的**直接子文件**（与 `load_facts` 的读法一致——写到子目录里
   就永远读不到）；新建文件要沿用**本盘既有账本文件的命名风格**（风格从盘内
   现有账本文件推断，不跨盘借），前缀不得与现有账本文件撞；不指定时行为与
   从前一字不变（仍是默认那本账）。同一能力贯通 CLI（`fact add --ledger`）
   与 MCP／serve（`ledger` 字段）。
2. **新增只读端点** `GET /api/disk/<p>/<d>/fact-form`：给表单备料——
   **已签产物**（人签清单那组，附清单 sha256 与现算 sha256 的比对：签过
   之后被改过的标出来）、**未进清单的产物**（清单里那些产物**所在的目录**下
   存在但没进清单的文件）、**盘内现有账本文件** ＋ 本盘命名风格 ＋ 下一个
   可用前缀。
3. **两步表单**（右栏「更多」→ 事实账 → 追加事实）：① 挑产物 ② 说清这条
   数字 ＋ 落哪本账。走既有「提议-确认」通道：表单**只建单**，落盘由人在
   差异卡上点「采纳写回」。

### 7.2 三条界面口径（都守住了）

| 口径 | 怎么守住的 | 实跑读数 |
|---|---|---|
| 界面不让用户碰哈希 | 表单**没有**哈希输入框；`source_sha256` 由 `scaffold.prepare_fact` 现算后落进事实条目 | 卡片上 `source_sha256 = "2c367edb…"`，与清单里 BATCH23-SWB16.md 的 sha256 一致 |
| 不提供手打 source 路径的入口 | 只能从两组候选里选，没有路径输入框 | 选中后 `#afSrc` 自动填成 `experiments/ctx-compiler-redblue/BATCH23-SWB16.md` |
| 落哪本账不给默认 | 第二步必须从盘内现有账本文件里选（或按本盘风格新建）；未选时「建提议单」按钮 disabled | 8 本账 ＋「新建一个账本文件」；未选时按钮 disabled=true |

### 7.3 实跑读数（宿主内置浏览器，副本盘 `/tmp/fs-factform-root`）

**第一步（挑产物，EN 界面）**

```
已签产物组：9 条（清单里那组，全部 drift=false，附 12 位 sha 短指纹）
未进清单组：8124 条（扫描范围＝清单产物所在目录 experiments 下 2 层，耗时 0.045s）
引擎侧说明（EN）："Artifacts not in the manifest are scanned only 2 level(s) under
  experiments - 8124 file(s) in total; anything deeper is not listed."
界面提示："8124 in total, showing the first 120; narrow it down with the box above."
```

文件名筛选实测：输入 `BATCH12` → 已签组 0 条、未签组 2 条（按路径子串筛）。

**第二步（说清这条数字 ＋ 落哪本账）**

```
账本命名风格（EN）："Ledger naming style on this disk: single-letter prefix +
  underscore topic (e.g. a_swebench.toml)"
账本清单：facts/a_swebench.toml 13 facts ｜ b_pilot 3 ｜ c_crossmodel 7 ｜ d_cost 6
  ｜ e_gates 9 ｜ f_tau2 4 ｜ g_terminalbench 3 ｜ h_conflicts 3 ＋「新建一个账本文件」
新建文件名占位（EN）："e.g. i_topic.toml"（本盘下一个可用前缀 i）
```

**建单（只建单，不写盘）**

```
toast（EN）：Proposal created - open "Pending" and click "Adopt and write back".
差异卡来源：From page     类型：Append fact
改前：Ledger facts/e_gates.toml: there is no fact with id=Z1 yet
      (it will be appended at the end of the ledger)
改后：One fact will be appended to ledger facts/e_gates.toml: ＋ [[fact]] 片段
```

建单后盘上核对：**8 本账里没有任何一本含 `id = "Z1"`**；`audit/evidence.lock`
（`5e4e33bc…`）与 `audit/evidence-log.ndjson`（`9b16ff9c…`）前后一致；没有
投稿包目录。

**采纳写回（落盘＝预览，逐字一致）**

```
toast（EN）：Adopted and written back      待确认徽标：1 → 0，卡片清空
落盘文件：/tmp/fs-factform-root/paper/facts/e_gates.toml（**所选的那本账**）
文件末尾与卡片预览逐字一致：True（预览 313 字节）
其余 7 本账：无 Z1；factscribe.toml：只差 last_opened（打开动作的既有副作用）
```

**四步链读数（跑全检，副本盘）**

| 步骤 | 追加前 | 追加后 | 变化 |
|---|---|---|---|
| 声明（facts/*.toml 条目） | 48 / 48 | **49 / 49** | **＋1** |
| 绑定（正文里 \fact{} 绑住的数） | 232 / 232 | **233 / 233** | **＋1** |
| 回账（正文数字回对账本） | 232 / 232 | **233 / 233** | **＋1** |
| 出证（证据冻结 ＋ PDF 门） | 106 / 106 partial | 106 / 106 partial | 不变 |

体检：0 red · 0 yellow；事实数读数 48 → 49。

> 绑定那一步的说明：页面**按设计**不让人凭空造账本绑定——正文里新写的
> `\fact{…}` 会被保护面剥掉（`wb.warn.protect.injected`）。所以「正文绑定」
> 是在**副本盘正文源文件**里直接写的（`sections/05_eval.tex`：
> `…none in the other direction\fact{A7} (sign test p=0.031\fact{Z1}).`），
> 不是页面操作的产物。正式稿盘一个字节都没动。

**新建账本文件（沿用本盘风格）**

```
选「新建一个账本文件」＋ 填 i_e2e.toml → 建单
改前：Ledger facts/i_e2e.toml: there is no fact with id=Z2 yet
      (this ledger file does not exist yet; it will be created on adoption)
驳回后：全部文件逐字节一致；facts/i_e2e.toml **没有**被创建；Z2 不在任何账里；
        evidence.lock / evidence-log.ndjson 不变；没有投稿包目录
同款单再走一次并采纳 → facts/i_e2e.toml 按 letter_topic 风格建成（i 前缀未占用），
        落盘片段与卡片预览逐字一致；Z2 只落在这本新账里
```

**表单输入校验（ZH 界面）**

```
新文件名 01-core.toml（与本盘风格不符）→ toast「这个文件名不合本盘的命名风格。」
新文件名 a_dup.toml（前缀已被 a_swebench 占用）→ toast「这个前缀已被本盘现有账本文件占用。」
两次都没有建出单（待确认卡片数 0），表单保持打开
```

校验规则由服务端随表单下发（`ledger_style_pattern` ＋ `ledger_used_prefixes`），
页面照它先挡一次；服务端仍是唯一权威（它会再拒一次，并带机器可读的错因码
`LEDGER_STYLE_MISMATCH`／`LEDGER_PREFIX_TAKEN`／`LEDGER_OUTSIDE_GLOB`／
`LEDGER_NOT_IN_GLOB_DIR`／`LEDGER_PATH_INVALID`，界面据此翻语言）。

**EN 界面零中文残留（实测）**

```
工作台 chrome（顶栏 ＋ 右栏三面 ＋ 四个模态 ＋ toast ＋ 证据卡）CJK 命中：0
唯一命中是语言钮本身的「中」（设计如此，与既有守卫测试同口径）
追加事实表单、差异卡、toast、引擎侧说明：全 EN，无中文
检查报告模态里的中文来自**中文盘账本的内容**（双语对账表在逐条对比 paper-zh
的 claim 原文）＋ 一条既有的全角分隔符「A ｜ B」，不是本轮新增面
```

**ZH 界面正常（实测）**

```
切到中文盘 paper-zh → 追加事实表单：
  引擎侧说明回中文：「未进清单的产物只扫到 experiments 下 2 层，一共 8124 个文件；更深的不在候选里。」
  组标题：已签产物 ｜ 未进清单的产物 ｜ 落哪本账
  命名风格：「本盘账本命名风格：单字母前缀 ＋ 下划线主题（例 a_swebench.toml）」
  建单 toast：「已建单：去「待确认」里点「采纳写回」。」
  差异卡：来自页面 ｜ 追加事实 ｜「账本 facts/e_gates.toml：当前没有 id=Z9 的事实」
  驳回 toast：「已拒绝这条提议」
驳回后：中文盘的 facts/ 与 audit/ **逐字节**与正式盘一致；Z9 不在任何账里
```

**控制台与网络**

```
console warn/error：0 条（整轮实跑后复查仍为 0）
network failed/4xx/5xx：0 条
```

### 7.4 正式稿盘零改动（实测）

| 盘 | 开工前聚合 sha256 | 验后聚合 sha256 | 结论 |
|---|---|---|---|
| `paper` | `df6af0599af747c3` | `df6af0599af747c3` | 一致 |
| `paper-zh` | `8f97443f37c60102` | `8f97443f37c60102` | 一致 |
| `paper-b` | `e5bae5a95f753846` | `e5bae5a95f753846` | 一致 |
| `paper-b-zh` | `28d1cc977a2d5fc5` | `28d1cc977a2d5fc5` | 一致 |

宿主论文根目录已**还原**回 `/Users/moc/workspaces/SiAgent`（引擎进程参数
`--root /Users/moc/workspaces/SiAgent`），本轮所有写操作都在
`/tmp/fs-factform-root` 副本上做。

### 7.5 本轮改动清单

| 文件 | 改动 |
|---|---|
| `factscribe/scaffold.py` | 新增 `resolve_ledger`／`ledger_naming`／`ledger_files`：指定目标账本文件（限 facts glob 内的直接子文件；新文件沿用本盘命名风格、前缀不撞）；`prepare_fact`／`add_fact` 加 `ledger` 参数（缺省行为不变），回传 `ledger_explicit` |
| `factscribe/cli.py` | `fact add --ledger FILE`（目标账本文件） |
| `factscribe/mcp.py` | `factscribe_add_fact` 的入参加可选 `ledger` |
| `factscribe/workbench_dataplayer.py` | `add_fact_data` 透传 `ledger` |
| `factscribe/workbench/readings.py` | 新增 `fact_form()` 只读读数（已签／未签产物分组、账本文件、命名风格、引擎侧说明） |
| `factscribe/workbench/server.py` | 新增 `GET /api/disk/<p>/<d>/fact-form`；`_error` 增 `err_code`（机器可读错因，界面据此翻语言） |
| `factscribe/workbench/proposals.py` | 追加事实提议单带上目标账本（`fact.ledger` ＋ `fact.ledger_explicit`）；新建账本文件时改前补一句「采纳时新建」 |
| `factscribe/i18n.py` | 新增 `wb.form.fact.note.*`（清单未签／产物被改／扫描范围／无账本…）与 `wb.form.fact.err.*`（五个账本错因）双语模板；`wb.prop.addFact.before.newLedger` |
| `factscribe/workbench/static/index.html` | 右栏「更多」新增「事实账」段；新增 `#modalFact` 两步模态（挑产物 → 说清这条数字 ＋ 落哪本账） |
| `factscribe/workbench/static/app.js` | 追加事实表单逻辑（读数、筛选、校验、建单）；`ff.*` 双语字典；`state.af` |
| `factscribe/workbench/static/app.css` | 表单样式（候选列表、徽标、账本选择） |
| `tests/test_workbench_fact_form.py`（新） | 22 条：账本目标校验（风格／前缀／glob／子目录／路径）、`fact_form` 读数、真实 HTTP 端点、提议单落所选账本、错误码、CLI／MCP 入口、wb.form 文案双语且 EN 无中文 |
| `tests/test_workbench_layout.py` | 面板节标题计数 5 → 6（新增「事实账」段沿用同一条 `.np-pane-h`，色值闸不变） |
| `miniapp/miniapp/client/**`、`miniapp/miniapp/node/engine/factscribe/**` | `miniapp/build.sh` 同步产物（契约自检通过：110 文件 / 4.8 MiB） |

全仓 `pytest tests/ -q`＝**2215 passed / 0 failed**（397 subtests；上一轮基线
2193，本轮 +22）。

### 7.6 本轮明确**没做**的事

| 事项 | 为什么 |
|---|---|
| 不做「实验报告 → 事实」的自动桥 | 本批只补界面表单；既有的 `wizardModal` 导入向导写的是草稿块，不是事实账，两者不混同 |
| 不新增「value 必须在产物里」的硬校验 | 会破坏既有 MCP 驱动测试（value `7/8`）。本轮只把它写成**界面提示**（`ff.f.valueHint`：value 必须是产物里的原文），不拦 |
| 不给 add_fact 提议单加 before_sha 指纹闸 | 追加事实是**只追加**账本，改动的是新增片段而非既有内容；加闸会改变既有提议单口径，超出本批 |
| 不动 `scaffold._check_source` 的任何一条校验 | source 必填／项目内相对路径／不收 URL／不越出 source_root／文件必须存在——一条没放松（实测：手打不存在的路径照样 400） |
| 不动四步链闸门语义、块形状闸、双 Profile 契约、金样例基线 | 已定口径；`tests/golden/audit_findings_baseline.json` 未重冻、未改一个字节 |
| 不把界面 chrome 与引擎侧文案混在一处 | 界面 chrome 走 app.js 既有静态字典（步骤标题／字段标签／按钮），引擎侧文案（清单未签／产物被改／扫描范围／账本错因）走 `wb.*` 目录随端点载荷下发，两条都是既有机制 |
| 不删上轮遗留的 `/tmp/fs-i18n-root` 副本盘 | 与本轮无关，留着不动 |