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

## 8. 2026-11-23 第四轮：正文编辑「不跟手」——先实测定位，再按实测修

### 8.1 症状与三个嫌疑（**都先当假设**）

用户反馈：正文页面编辑不跟手（修完此前四项交互问题后仍存在）。开工时列了三个假设：

| # | 嫌疑 | 事前判断 |
|---|---|---|
| 1 | 中文输入法（IME）没被处理：`app.js` 里搜不到 compositionstart／compositionend／isComposing | 方向待证 |
| 2 | 保存后整块替换 DOM（`host.innerHTML = fresh.innerHTML`）把光标甩回块首 | 守卫生效与否待证 |
| 3 | 保存时往编辑宿主里 append「已保存」角标，顶动光标 | 待证 |

三个都用**真浏览器实测**证实或推翻，不靠代码推断。

### 8.2 实测方法（真浏览器，不是代码推断）

* 宿主内嵌浏览器发不出真 IME → 另起**真 Chrome headless（158）＋ CDP**：
  `Input.dispatchKeyEvent` 发**真键盘事件**（不是页面里合成的 `dispatchEvent`），
  `Input.imeSetComposition` 走**真 IME 组合管线**——`compositionstart` →
  `compositionupdate` → `compositionend` 都是浏览器真实派发。
* 页面＝引擎自己服务的 `/`（`factscribe/workbench/static/` 原件，不是拷贝），
  论文根指向副本盘 `/tmp/fs-editoroot`。
* 探针：document 级 `keydown`／`input`／`composition*` 监听 ＋ `MutationObserver`
  ＋ `getSelection()` 读光标（节点名／段内偏移／屏幕坐标／上下文片段）。
* 「保存响应」用 CDP `Fetch` 拦下再放行，把时序钉死：组合进行中 → 点别的段（触发保存）
  → 回到原段 → 起组合 → **放行保存响应**。

### 8.3 修复前实测读数

| 项 | 读数 |
|---|---|
| 英文逐键（60 次真按键） | keydown→input：均值 **0.72ms**／峰值 **4.5ms**；input→paint（下一帧）：均值 **6.99ms**／峰值 **15.13ms** |
| 每键 DOM 变动 | 60 次输入＝**60 条** mutation，**全是** `characterData`；非正文变动 **0 条** |
| 打字前后 DOM 节点数 | 1865 → 1863（**不增长**） |
| 累积卡顿（300 次真按键） | 节点数 **1887 → 1887**；document 监听数 **9 → 9**；每键延迟全程 0.4–1.3ms，**无上升趋势** |
| 真 IME 组合（不被打扰时） | compositionstart → update('zhongwen') → update('中文') → **compositionend('中文')**；正文落地、光标紧跟其后 → **纯组合本身是好的** |
| 组合进行中保存响应回来 | 应答把 `SPAN.save-badge` **append 进正在编辑的宿主** `P#01_intro-p1`（kids 147→148）；正文文本流被顶出角标文字（tail `…xzxSaved`） |
| 组合之后的下一次组合 | 光标落到**角标自己的文本节点**：`node=#text, offset=1, ctx='S'` |
| 整块替换 DOM | 宿主内 childList 变动 2 条（整块换）；但**聚焦中的块被守卫生效地跳过**（只记 `data-stale='1'`），正文与光标不受影响 |
| 同文件连续编辑两段 | 第二段被标 stale 后再保存：**不丢字**、无 BLOCK_STALE（toast 只有 "Saved (original kept as .bak)"） |
| 保存往返 | `POST /api/disk/paper/paper/edit` 单次 **267.5ms**（start 5234.3 → respEnd 5501.8） |
| 响应处理开销 | 整文件兄弟块重建：**1 次调用 / 0.3ms**（01_intro.tex 只有 1 段） |
| 落盘层 | 角标文字**没有**漏进 `.tex`（`grep -c Saved` → 0）——`collectPlain` 跳过 `data-badge` |

### 8.4 三个嫌疑的裁定

| 嫌疑 | 裁定 | 依据 |
|---|---|---|
| 1 IME 未处理 | **成立**（但表现不是「拼音提前上屏」） | App 对组合**零感知**（组合期间照样保存、照样改宿主）；组合进行中保存响应一回来就改宿主，下一次组合的光标被甩进角标 |
| 2 整块替换甩光标 | **基本证伪** | 聚焦中的块被守卫生效跳过；同文件连续编辑不丢字、无 BLOCK_STALE。代码里确实**没有**「替换后恢复光标」这层（守卫前提一旦不成立，光标会被甩掉）→ 只补这层保险，**不动守卫语义** |
| 3 角标顶动光标 | **成立** | 角标插进正文文本流（正文里多出角标文字）；组合进行中下一次组合的光标落进角标文本节点 |
| 附：累积卡顿 | **证伪** | 300 键后节点数、监听数、每键延迟全无变化 |
| 附：英文打字慢 | **证伪** | keydown→input 均值 0.72ms。「不跟手」不是打字本身慢，而是**编辑过程中光标/组合被破坏** |

### 8.5 本轮改了什么（文件:行号；源在 `factscribe/workbench/static/`，载荷由 build.sh 同步）

| 位置 | 改动 |
|---|---|
| `app.js:2011-2021` | 新增 `imeState`（active／blockId／pendingSave／pendingBadge／pendingHtml／stuckTimer）——组合期间的欠账分别记账 |
| `app.js:2023-2057` | 新增 `caretTextOffset(host)`／`restoreCaretOffset(host, offset)`：段内光标偏移的取（Range）与还（TreeWalker） |
| `app.js:2059-2083` | 新增 `flushAfterComposition(blockId)`：组合结束统一补做——芯片重绑 ＋ 欠下的整块替换／角标／保存 |
| `app.js:2085-2094` | 新增 `clearStuckComposition()`：组合超过 5s 的兜底（撤掉「组合中」标记，但**不当场去收**正文） |
| `app.js:2126-2151` | `applyBlockHtml`：组合期间不改这一块（记账 `pendingHtml`）；替换**前**记光标偏移（:2141）、替换**后**按偏移放回（:2148）；补 `bindChipCaret(host)`（:2147）——整块替换后芯片的「点一下把光标放回正文」必须重绑，否则点芯片丢光标 |
| `app.js:2153-2159` | `saveBlockNode`：组合期间**不收正文**（:2157 记账 `pendingSave` 后 return）——此刻 DOM 里是候选中的拼音，收下去会写进 `.tex` |
| `app.js:2302-2350` | `showSavedBadge`：角标改挂 `document.body` 浮层（:2317），**不再 append 进编辑宿主**；组合期间先记账；贴在末行末端，顶到正文列右缘时改塞进末行下方的空档（不出界、不压字） |
| `app.js:5203-5218` | `bind()`：接入 `compositionstart`／`compositionend`（capture 阶段）——组合开始记账、结束补做 |
| `app.css:1478-1481` | `.save-badge` 改成 `position:absolute` ＋ `pointer-events:none`（不吃点击，不会把编辑器点失焦），去掉行内 `margin-left` |

### 8.6 修复后复测读数（同一套场景，真 Chrome）

| 项 | 修复前 | 修复后 |
|---|---|---|
| 组合进行中保存响应回来后，宿主内 | kids 147→148（插进 `SPAN.save-badge`） | kids **1 → 1**，非正文变动 **0 条** |
| 编辑宿主内有没有角标 | 有 | **无** |
| 正文里有没有角标文字 | 有（`…xzxSaved`） | **无**（`…xzxzhongwen`） |
| 组合继续输入后的光标 | 落到角标文本节点 offset 1／ctx 'S' | 跟住组合文本 **offset 36** |
| 整块替换前后光标 | （没有恢复层） | offset／ctx／坐标**全同**（offset 4／ctx '-ins'／x 325.2／y 429.2） |
| 英文逐键 60 键 | 0.72ms 均值 | **0.46ms 均值／0.9ms 峰值**；非正文变动 0；节点 1911→1911 |
| 组合→落盘 | — | compositionend('研究') 正常；`.tex` 里**中文落地**；`grep -c Saved` → **0** |
| 角标几何 | 插在正文流里 | body 浮层：`pointer-events:none`、**不压任何文字**（overlapsText=`[]`）、不出正文列 |

### 8.7 正式稿盘

| 盘 | 本轮开工时（11:19） | 收工时 | 结论 |
|---|---|---|---|
| `paper` | `e04b204b66fd6290` | `e04b204b66fd6290` | 一致 |
| `paper-zh` | `8f97443f37c60102` | `8f97443f37c60102` | 一致 |
| `paper-b` | `e5bae5a95f753846` | `e5bae5a95f753846` | 一致 |
| `paper-b-zh` | `28d1cc977a2d5fc5` | `28d1cc977a2d5fc5` | 一致 |

本轮引擎全程指向副本盘 `/tmp/fs-editoroot`；正式盘文件 mtime 停在 **11:12:13** 未再变动。
宿主论文根目录已**还原**回 `/Users/moc/workspaces/SiAgent`（还原后停在项目列表页，**没有打开任何正式盘**）。

**一条必须写清的差口**：上一轮记下的 `paper` 基线是 `df6af0599af747c3`，它在
**2026-11-23 11:12:13** 变成了 `e04b204b66fd6290`——差的只有 `factscribe.toml` 里
一行 `last_opened` 时间戳，外加一个 `factscribe.toml.bak` 旁文件。成因是**宿主
「打开磁盘」这个动作本身**（引擎 `factscribe/workbench/write.py::touch_opened` 写
`[workbench].last_opened` 并留 `.bak`），发生在本轮开工前 7 分钟，**不是本轮验收造成的**。
那个 `.bak` 的**前一版内容已不可得**（11:12 那次写把它覆盖了），所以**没有**去改用户的
正式盘凑指纹——如实报告，不擅自动用户盘。

### 8.8 本轮明确**没做**的事

| 事项 | 为什么 |
|---|---|
| 不改「聚焦中的块不替换」这个既有守卫 | 实测证明它是对的（同文件连续编辑不丢字）；本轮只补「替换后恢复光标」这层保险，不动守卫语义 |
| 不把 IME 组合做成「逐键回写」 | 组合期间 DOM 里就是候选文本，回写会打断候选；本轮只在组合期间**不动 DOM、不收正文** |
| 不动落盘层（`collectPlain` 的散文＋token 口径、`\fact`／`\cite` 保护面） | 角标本就被收集时跳过；实测 `.tex` 里没有角标文字 |
| 不动四步链闸门语义、提议单口径、块形状闸、金样例基线 | 已定口径；`tests/golden/audit_findings_baseline.json` 未重冻、未改一个字节 |
| 不改用户正式盘去凑上一轮基线指纹 | 差的只是一个 `last_opened` 时间戳 ＋ 一个 `.bak` 旁文件，且 `.bak` 前一版内容不可得；改用户盘凑指纹比留着一行时间戳更糟 |
| 不把真浏览器那一跑塞进必跑测试 | 依赖 node≥22（内置 WebSocket）与 Chrome，缺任一个就 skip（不拿「跳过」冒充「验过」）；14 条静态断言永远跑 |
| 不删上两轮遗留的副本盘（`/tmp/fs-i18n-root`、`/tmp/fs-factform-root`） | 与本轮无关，留着不动；本轮的 `/tmp/fs-editoroot` 同样留着做证据 |

### 8.9 本轮测试

* 新增 `tests/test_workbench_editing_ime.py`：**18 条**＝14 条静态断言（IME 事件序列／
  组合期不收正文不换 DOM／光标取还与替换后恢复／状态 UI 不落编辑区）＋ 4 条**真浏览器**
  行为（英文逐键延迟与 DOM 变动、组合不被保存响应打断、光标跟住组合文本、整块替换后光标不丢）。
* 新增 `tests/editing_ime_driver.mjs`：真 Chrome ＋ CDP 驱动（真键盘事件／真 IME 组合／
  `Fetch` 拦请求做时序钉死）。
* 全仓 `pytest tests/ -q` ＝ ****2233 passed / 0 failed**（397 subtests，277.57s）**（上一轮 2215，本轮 +18）。

---

## 9. 2026-11-23 第五轮：四项必做收尾（value 硬闸 / 账本指纹闸 / 候选列表改版 / .bak 多份＋刷新不保存）

- 分支：`feat/miniapp-host-seam`（开工 HEAD `e4bbe16`；**未推远端、未建 PR**）
- 范围：四项必做全部落地 ＋ 三项有余力项；第 8/9 条（证据锁读数并进报告／投稿包导出前预览清单）**只记录不实现**——理由与待用户拍板的点见 §9.7
- 验收台：宿主**内嵌浏览器**（Electron FilePanel）打开**已 publish 到本机宿主**的 `factscribe` Miniapp；宿主论文根目录指向 `/tmp/fs-batch5-root`（四盘 `cp -a` 副本），验收后**还原**回 `/Users/moc/workspaces/SiAgent`
- 发布态逐文件比对：**源 → 载荷 → 已发布 104/104 文件逐字节一致，0 差异**（§9.6）
- 全仓 `pytest tests/ -q`＝**2271 passed / 0 failed**（397 subtests，266.17s；上一轮基线 2233，本轮 +38）

### 9.1 四项必做 · 修法（文件）

| 项 | 修法 |
|---|---|
| value 硬校验 | 新增 `factscribe/valuecheck.py`（纯计算）：归一化＝NFKC、LaTeX 百分号、LaTeX 分数命令→`A/B`、去强调标记、千分位逗号去、窄空格当千分位、小数点逗号→小数点；**数字项按出现顺序做子序列匹配**（数值相等、百分号一致、单位不参与比较），无数字项时按归一化子串比；产物非 UTF-8 文本 → `VALUE_SOURCE_NOT_TEXT`。`factscribe/scaffold.py` 新增 `check_value_in_source()`（把既有 `_check_source` 提成公开版 `resolve_source()`，**语义一条没放松**）。`factscribe/workbench/proposals.py::propose_add_fact` **建单前**先过闸（不合格拒建单）；`apply_add_fact` **采纳时**再核一遍。 |
| 追加事实提议单加 before_sha 指纹闸 | `propose_add_fact` 给单子带上 `before_sha`＝**目标账本文件**的 sha256（账本本来不存在时记 `before_absent`）；`apply_add_fact` 采纳前复核账本指纹，不符 → `BLOCK_STALE` 拒写；账本被别处**建出来**（`before_absent` 变有文件）同样拒。 |
| 候选列表改版 | `index.html` 的未签组改 `<details id="afUnsignedFold">`：**默认折叠且不渲染**；summary＝「搜索未签产物」＋标签「未签（需人签后才能作数）」；已签行 title 同时给**清单 sha256** 与**现算 sha256**；全局筛选框同时管两组。 |
| .bak 保留多份 ＋ 刷新不保存 | `factscribe/workbench/write.py`：`atomic_write(path, text, backup=True, keep=1)` 新增 `keep` 与 `backup_paths()`；正文与 main.tex 走 `BACKUP_KEEP=10`（`.bak`＝上一版，`.bak.1/.bak.2…` 轮转**不互相覆盖**）；**配置文件仍 `CONFIG_BACKUP_KEEP=1`**。前端 `app.js`：`input` 事件打脏标记 `data-dirty=1`，`saveBlockNode` 与 `focusout` **都要求脏标记**；保存成功后按文本比对清脏；另加 `beforeunload` 提醒（有未保存编辑才拦）。 |

### 9.2 value 硬闸 · 宿主内嵌浏览器实测读数（副本盘）

| 操作 | 实测读数 | 判定 |
|---|---|---|
| 选已签产物 `experiments/ctx-compiler-redblue/BATCH23-SWB16.md` → value 填 `42` → 点「Create proposal」 | toast 全文：`Could not create the proposal: The value "42" does not match the artifact experiments/ctx-compiler-redblue/BATCH23-SWB16.md: the number(s) 42 were not found (compared one by one, in order; units are not compared). You said the location is "host check locator" - rewrite the value to match the artifact text, or pick another artifact.`；待确认徽标仍 **Pending 0**（**没建出单**） | 通过 |
| 同一产物、value 填 `10/16`（产物里确有）→ 建单 | toast：`Proposal created - open "Pending" and click "Adopt and write back".`；徽标 **Pending 1**；差异卡右栏 TOML 高亮 span：**key 8 / eq 8 / string 7 / array 1 / table 1** | 通过 |
| 既有测试改用**真实样本**而非放宽校验 | `tests/test_workbench_proposals.py`、`tests/test_workbench_i18n_display.py`、`tests/miniapp_mcp_driver.mjs` 的 value 由 `7/8` 改为 `56.25%`（`examples/minimal/results/swb16.md` 里真实存在） | 通过 |

### 9.3 账本指纹闸 · 实测读数

| 操作 | 实测读数 |
|---|---|
| 建单（目标账本 `facts/a_swebench.toml`）后，在**盘外**往同一本账追加一条 `[[fact]] id="EXT3"` | 账本 sha 由 `f405d69d…` → `9ecb7400…` |
| 回页面点「Adopt and write back」 | toast：`This paragraph was changed elsewhere`；卡片 class＝`proposal-card prop-stale`；「Adopt and write back」按钮 **disabled=true**；卡片上多一行 stale 说明 |
| 落盘核对 | `grep -c 'Z90' a_swebench.toml`＝**0**（没写进去）；`EXT3` 仍在；账本 sha 仍 `9ecb7400…`（**没被动过**） |
| 驳回该单 | toast：`Proposal rejected`；徽标回到 **Pending 0** |

### 9.4 候选列表 · 实测读数

| 操作 | 实测读数 |
|---|---|
| 打开「更多 → 事实账 → 追加事实」 | 引擎侧说明：`Artifacts not in the manifest are scanned only 2 level(s) under experiments - 8128 file(s) in total; anything deeper is not listed.` |
| **默认状态**（不碰折叠区） | 已签组 **9 行**；未签折叠区 **closed**，未签列表**渲染 0 行** |
| 展开折叠区 | 未签列表渲染 **120 行**；提示 `8128 in total, showing the first 120; narrow it down with the box above.`；折叠 summary＝`Search unsigned artifacts`，标签＝`Unsigned (a human must sign it before it counts)`；未签行徽标 `Unsigned` |
| 已签行 | 同行带 `title="manifest sha256: 3c4904b1…`／`live sha256: 3c4904b1…"`（清单指纹与现算指纹并列，drift 可见） |
| 筛选框输 `BATCH12` | 已签组 → `Nothing in this group.`；未签组 → **2 行**（`BATCH12-RESULT.md`、`BATCH12-TEST-CTX.md`）——**一个框同时管两组** |

### 9.5 .bak 多份 ＋ 刷新不保存 · 实测读数

| 操作 | 实测读数 |
|---|---|
| 编辑 `01_intro` 第一段 → 失焦保存 | toast：`Saved (original kept as .bak)`；`.tex` 落新版本；`.bak`＝**上一版**（sha `92ca27e2…`）；旧 `.bak` **轮转**成 `.bak.1`（不是被覆盖） |
| 连做三次保存 | 链上 **6 代并存、互不覆盖**：`.tex`(探针 C=1,2=1)／`.bak`(C=0,2=1)／`.bak.1`(探针 1=1)／`.bak.2`／`.bak.3`／`.bak.4`，各代 sha 互不相同 |
| 保存后**刷新页面** | 盘上**零写入**：`find /tmp/fs-batch5-root -newermt '<刷新时刻>' -type f` 为空；`.tex`/`.bak` 的 mtime 仍停在保存那一刻（12:31:00） |
| **只聚焦不编辑**后刷新 | 同样**零写入**（`.tex`/`.bak`/`.bak.1` mtime 全未变）；唯一写入是 `factscribe.toml` 的 `last_opened`——那是**「打开」这个动作**的既有副作用（P2 已记录），不是编辑触发的 |

### 9.6 发布态逐文件比对（源 → 载荷 → 已发布）

| 项 | 读数 |
|---|---|
| 载荷同步 | `miniapp/build.sh` 跑通：文件数 111（上限 1024）／4.8 MiB／契约自检通过／engine import ok／build 完成 **104 个载荷文件** |
| 文件集合 | 载荷 104／已发布 104／交集 104；**只多在载荷 0 个、只多在已发布 0 个** |
| 逐字节 | 交集 104 个文件 **0 差异** |
| 前端三件 | `app.js`(`d710d471…`)／`app.css`(`e0bfdbb0…`)／`index.html`(`243c9165…`)：源＝载荷两份副本＝已发布两份副本，**五处全等** |
| 引擎 | `factscribe/**/*.py` **60 个**文件：源＝载荷＝已发布，**0 不一致**（含新增 `valuecheck.py`） |
| 薄壳 | `node/server.mjs`：载荷＝已发布（`fec65f92…`） |

### 9.7 有余力项（做了）与只记录不做的（第 8/9 条）

**做了的三项**（都是只增不改）：

| 项 | 实测读数 |
|---|---|
| 差异卡 TOML 高亮 | add_fact 卡右栏：**key 8 / eq 8 / string 7 / array 1 / table 1** 个 span（§9.2 同屏） |
| `fs_get_brief` 按 fact id 过滤 | 新增**可选**入参 `fact`，回包加 `focus`（这条事实绑在哪几节）；其余载荷字段不变 |
| 宿主默认模型档位显式成组 | 面板下拉读数：group `Host default`（1 项：`Host current model`，value `host:default`）＋ group `Host models`（2 项：`M3.1-Flash`／`M3`）；**id 与请求载荷不变**，只是展示层分组 |

**只记录、不擅自动的两条**（要用户拍板）：

| 条 | 为什么没做 | 要用户拍板的点 |
|---|---|---|
| 第 8 条：把 `evidence_gate` 的读数（冻结状态／差异／最后一条日志）并进检查报告 | 报告里的「出证」读数来自四步链闸门，并进去会让两个读数源耦合；**四步链闸门语义是已定口径** | 并进去以后，报告的「出证」是否要**显式标注两个来源**（闸门读数 vs `evidence_gate` 读数）？还是要合并成一个？ |
| 第 9 条：投稿包导出前加「预览清单」 | 导出流程已有**清单门**（门不过就不出包）；预览＝再加一条人工确认链，属导出流程口径 | 「预览清单」要做成导出前的**必经闸**（强制）还是**可选**的一步？强制会改导出流程的既有口径 |

### 9.8 正式盘零改动（实测）

| 盘 | 开工前聚合 sha256 | 验收后聚合 sha256 | 结论 |
|---|---|---|---|
| `paper` | `fb03eaf1c3bc9d3c…` | 同左 | 一致 |
| `paper-zh` | `8f16d331bda67c28…` | 同左 | 一致 |
| `paper-b` | `4d5ccf9855f4bf84…` | 同左 | 一致 |
| `paper-b-zh` | `9d1fe50993d38094…` | 同左 | 一致 |

宿主论文根目录**已还原**回 `/Users/moc/workspaces/SiAgent`（`config.json` 写回 ＋ `miniapp restart` 重拉引擎）。
还原后刷新宿主页面，四个正式项目在列（`paper` 18 节 **48 事实**、`paper-b` 10 节 62 事实、`minimal`、`legal-demo`），
`paper` 的 `last_opened` 仍停在 **2026-11-23 11:12**——说明还原过程**没有打开正式盘**，指纹与开工前逐字节一致。

### 9.9 本轮测试

* 新增 `tests/test_workbench_value_guard.py`：**19 条**（归一化命中/不命中、拒建单错因码与 params、非文本产物、指纹闸、外部改动拒写、账本被别处建出拒写、采纳＝预览逐字一致）
* 新增 `tests/test_workbench_save_guard.py`：**15 条**（备份轮转四代、最老淘汰、`save_block` 多代、配置只留一份、前端脏标记/失焦闸/`beforeunload`、候选折叠区静态断言与中英键齐）
* 新增 `tests/test_workbench_brief_focus.py`：**4 条**（brief focus 有/无、未知 id、其余载荷不变）
* 既有测试改用真实样本（不放宽校验）：`tests/test_workbench_proposals.py`、`tests/test_workbench_i18n_display.py`、`tests/miniapp_mcp_driver.mjs`
* 全仓 `pytest tests/ -q`＝**2271 passed / 0 failed**（397 subtests，266.17s；上一轮 2233，本轮 **+38**）

### 9.10 本轮明确**没动**的东西

| 事项 | 怎么保证没动 |
|---|---|
| 四步链闸门语义 | `checkreport._chain_steps` 未改 |
| 提议单形状校验（块形状闸） | `_block_shape_guard` 未改 |
| 双 Profile 契约 / P-152 | 未触及任何判定面 |
| `Issue.as_dict()` 的形状 / 金样例基线 | 未改；`tests/golden/audit_findings_baseline.json` **未重冻、未改一个字节** |
| `scaffold._check_source` 的既有校验 | 一条没放松（`resolve_source()` 只是把既有逻辑提成公开版，`check_value_in_source()` 是**新增**的一道闸） |
| CLI `fact add` 直写通道 | 未动——value 硬闸只加在「提议-确认」这条路上；直写通道的口径留到缺口清单 §11.4 |
| 落盘层散文＋token 口径、绑定数字保护面 | 未动 |
| 配置文件备份份数 | 仍 `CONFIG_BACKUP_KEEP=1`（只有正文与 main.tex 走多份） |
| MCP 工具既有入参 schema | `fs_*` 一字未动（只给 `fs_get_brief` 加了**可选** `fact`） |

### 9.11 一条**实测到但没深挖**的既有现象（如实记）

在 `\fact{E5}` 芯片旁放探针 `[HOSTBAK1]`：**第一次**保存落盘是完整的（`grep -o HOSTBAK1` 命中 1）；
**第二次**保存往返后那个尾数字 `1` 不见了（落盘成 `[HOSTBAK]`），页面 DOM 里也同样没有它。
这落在**绑定数字保护层**的既有范围（本轮一行没动），与上一轮 §2 记的「探针里的数字被内联绑定闸抓住」同类。
**根因本轮没查**——保护层属落盘层口径，需单独开一轮定位，本轮不猜、不改。

## 10. 2026-11-23 第六轮：四项必做（A 保存逐字保留 / B 直写通道 value 硬闸 / C 证据锁独立卡 / D 导出前可选预览）

> 本轮开工 HEAD `2fdf3bf`（分支 `feat/miniapp-host-seam`）。正式稿盘**一个字节都没动**
> （见 §10.8）；一切实测都在 `/tmp` 副本盘上做。

### 10.1 四项必做 · 修法（文件）

| 项 | 修法 | 文件 |
|---|---|---|
| **A** 保存会改内容 | 客户端：块指纹（`state.blockSha`）**只在 DOM 真被换成服务端新文时**才推进（`applyBlockHtml` 接管指纹；`saveBlockNode`／`reloadBlocks` 在「块仍被聚焦、用户又打了字」时不推进）。服务端：占位符序号在当前扫描里不存在 → **拒写**（`EDIT_TOKEN_MISMATCH`，HTTP 409）而不是静默丢弃；另加一道「保护面不许丢」的兜底 | `factscribe/workbench/static/app.js`、`factscribe/workbench/write.py`、`factscribe/workbench/server.py` |
| **B** 直写通道 value 硬闸 | `scaffold.prepare_fact()` 在 `_check_source` 之后加 `check_value_in_source()`——CLI `fact add`、MCP `factscribe_add_fact`、serve `/api/facts`、采纳写回**共用同一道闸与同一句文案**（同一个 `factscribe/valuecheck.py`） | `factscribe/scaffold.py` |
| **C** 证据锁独立卡 | 报告载荷新增顶层 `evidence_lock`（冻结与否／条目数／两个指纹／差异明细／最后一条日志），来源与 MCP `fs_get_evidence_status` 同源（`readings.evidence_gate`）；四步链 `_chain_steps` **一字未动** | `factscribe/workbench/checkreport.py`、`factscribe/workbench/static/index.html`、`factscribe/workbench/static/app.js` |
| **D** 导出前可选预览 | `bundle.run_bundle(preview=True)`：**只算不写**，与真导出共用同一个 `_artifact_bytes`（路径/指纹/大小同一口径）；清单门判定一字不改（门不过照样不出包） | `factscribe/bundle.py`、`factscribe/workbench/actions.py`、`factscribe/workbench/server.py`、`factscribe/workbench/static/app.js` |

### 10.2 A「保存会改内容」· 真浏览器复现与修复前后读数

**现象（上一轮 §9.11 如实记的，本轮查清了）**：在 `\fact{E5}` 芯片旁放探针 `[HOSTBAK1]`，第一次保存落盘完整，第二次保存往返后内容被改。

**机制（两层，缺一不可）**

1. **客户端把块指纹推进早了**（`app.js::saveBlockNode`）：块指纹＝「这份 DOM 是哪一版文件渲染出来的」。保存应答回来时若那一块**仍被聚焦**（保存途中用户又点了回来），DOM 不重绘——里面那份保护面序号还是**旧版**的；旧口径却照样推进指纹，等于告诉服务端「我这份 DOM 对得上当前文件」。下一轮保存就带着**过期序号**混过指纹闸。
2. **服务端对「序号对不上」是静默丢弃**（`write.py::_rebuild`）：占位符序号在当前扫描里不存在时，旧口径是 `continue`——那枚保护面被**静默丢掉**，用户没打过的字就此被改掉。

**为什么序号会整体错位**：绑定数字令牌是**派生**的。正文 `…left the resolve count at 0/3\fact{E5}…` 里，`0/3` **紧邻** `\fact{}` 才算绑定令牌；插进探针后 `0/3` 不再紧邻，这枚令牌整段消失，后面所有保护面序号**整体前移一位**（实测：`0/3` 的令牌没了，`\fact{E5}` 的序号从 1 变成 0）。

**真浏览器实测**（副本盘 `/tmp/fs-a-root/paper`，真 Chrome ＋ CDP；驱动 `tests/save_probe_driver.mjs` 的 `stale` 模式：拦下 `/edit` 的请求、飞行途中把光标放回块里再放行，模拟「保存完又点了回来」）：

| 读数 | 修复前（旧前端 ＋ 旧服务端） | 修复后 |
|---|---|---|
| 第一次保存落盘 | `…left the resolve count at 0/3[HOSTBAK1]\fact{E5}, and per-round output…` | 同左 |
| 第二次保存落盘 | `…pt left the resolve count at \fact{E5}Z[HOSTBAK1]0/2, and per-round output grew…` | **同左（两次落盘逐字节相同）** |
| 两次请求的 `expect_sha` | `055edf89…` → `240fc2f7…`（指纹被提前推进） | `055edf89…` → `055edf89…`（**不推进**） |
| 落盘被改？ | **是**：`0/3` 被换成 `\fact{E5}`，凭空多出 `0/2` | **否** |

修复后第二轮保存被**指纹闸拒写**（客户端发的是旧指纹）→ 页面提示「这段在别处已被改动」并原地重载新文：**内容一个字节都没被改**。
（代价要说清：那一轮飞行途中新打的字会丢——这是 BLOCK_STALE 的**既有语义**「未保存的字会丢」，不是内容被改。）

**修法分两层，各自都必要**：

* 客户端（第一道）：指纹只在 DOM 真被换成服务端新文时推进（`applyBlockHtml(blockId, html, sha)` 接管；组合进行中的延后重绘也带着指纹一起延后）。
* 服务端（第二道，兜底）：`write.py::_rebuild` 遇到「序号在当前扫描里不存在」→ 抛 `EDIT_TOKEN_MISMATCH`（HTTP 409，附新鲜块让前端重载），**不再静默丢保护面**；另加 `_guard_surface_kept()`：重建后若少了命令类保护面（`\fact{}`／`\cite{}`／公式／环境……），同样拒写。
  * 绑定数字令牌（num）是**派生**的，插字就可能整段消失——那是合法编辑，**不在**这道兜底里（否则会拦下正常保存）。

（本轮后来又追加了两处同族修复：**派生令牌被按文字误认领**（§10.12）与**账本变了导致保护面序号整体错位**（§10.13，结构闸）。）

### 10.3 A · 全插入点扫描（精确口径）

按「**重建结果必须逐字节等于「原文＋探针」**」这条口径，把探针放进 `01_intro-p1` 的**每一个字符位置**各跑两轮（**5303** 个可插位置；本轮**最终代码**跑的读数）：

| 轮次 | 读数 |
|---|---|
| 正常路径（客户端 DOM 已重绘） | 重建结果 **逐字节等于**「原文＋探针」——**0 处内容不一致**；另有 **2 处被拒写**（`EDIT_TOKEN_MISMATCH`）：探针插进 `\$` 转义中间（`\` 与 `$` 之间），LaTeX 结构自此改变，保护面兜底不落盘 |
| stale 路径（客户端 DOM 没重绘、仍发旧序号，**故意绕过指纹闸**） | **0 处拒写、4 处不一致**：按旧序号重建时，芯片与它的绑定数字换了位置（`…$\times$\fact{D1} (\$0.0486\fact{D1}…` → `…$\times$ ($\fact{D1}0.0486…`） |

**stale 那 4 处为什么真流程里不会落盘**：这轮扫描是**绕过指纹闸**直接调重建层的（故意模拟「客户端那份 DOM 是旧版渲染的」）。真流程里客户端每次保存都带着 `expect_sha`（＝它那份 DOM 对应的块指纹）：指纹闸先过不去 → 409 `BLOCK_STALE` → 页面原地重载新文，**内容一个字节都不会被改**（真浏览器实测见 §10.2）。另外 §10.13 的「结构闸」又把「账本变了 → 保护面数量变 → 序号整体错位」这一路也拒写了。

口径说明（避免自欺）：早先一版扫描拿「重扫后的可见文字」比对，口径本身有洞——把探针插进 `\$` 转义中间，LaTeX 结构就变了（`\$` 变成「反斜杠 ＋ 真美元符」），那是**用户自己的编辑**，不是保存改的。改成逐字节比对「原文＋探针」后，这两处假阳性消失。

### 10.4 B · 直写通道的 value 硬闸（副本盘实跑）

`factscribe fact add`（直写通道）现在与「提议-确认」**同一道闸、同一句文案**：

| 操作 | 读数 |
|---|---|
| `fact add --id ZB1 --value 42 --source results/swb16.md` | 拒：`value「42」里的数字在产物 results/swb16.md 里找不到：42（数字按出现顺序逐个比对，单位不参与比对）……`；**账本零改动** |
| `fact add --id ZB2 --value 10/16 --source results/swb16.md` | 写入：`已写入 fact ZB2：真实值 = 10/16`；账本 4 条（A1/A3/A2/ZB2，**没有 ZB1**） |

MCP `factscribe_add_fact` 与 serve `/api/facts` 走的是同一个 `prepare_fact()`——既有测试（`tests/test_mcp.py`、`tests/test_serve.py`）改用**真实样本**（`42` → `10`，产物 `results/swb16.md` 里真有这个数）后转绿，**没有放宽校验**。

### 10.5 C · 证据锁独立卡（真界面读数）

| 读数 | 值 |
|---|---|
| 报告载荷顶层键 | `chain`、`evidence`（旧的两个键**逐字不变**）＋ **新增** `evidence_lock` |
| `evidence_lock` 读数（副本盘 paper） | `frozen=true`／`entries=106`／`sha256=03bd1dae…`／`current_sha256=03bd1dae…`（一致）／`mismatch=null`／`diff{added:[],removed:[],moved:[]}`／`last_log{action:freeze,…}` |
| 四步链 | `Declare 48/48`、`Bind 232/232`、`Reconcile 232/232`、`Certify 106/106`——**与加卡之前逐字一致**（`chain` 与 `evidence` 两个键的载荷 diff 为空） |
| 页面 | 第六张折叠卡「证据锁」：徽标 `frozen`，正文给出「Evidence freeze／entries 106／fingerprint 03bd1dae／log action=freeze」 |
| 页面调用次数 | **不多一次**——卡片随报告载荷一起来（`reportEvidenceLock()` 只读 `state.report.evidence_lock`，不发请求） |
| MCP 既有工具 | `fs_get_report` 的实现是**自行整形载荷**（不透传未知键）→ 引擎报告里多一个键，**MCP 工具的输出形状一个字没变** |

### 10.6 D · 投稿包导出前的可选预览（真界面读数）

| 读数 | 值 |
|---|---|
| 预览端点 | `GET /api/disk/<project>/<disk>/bundle-preview`（只读）→ `would_export=true`、`failed=0`、`file_count=36`、清单门 5 过 0 不过 0 豁免 |
| 预览模态 | 「36 files to be collected」＋清单门读数＋逐件（路径 · 指纹 · 字节数）；两个钮：**「继续导出」**／**「跳过预览，直接导出」**（**可选**，可跳过） |
| 预览写不写盘 | **一个字节都不写**（预览后包目录压根不出现） |
| 导出口径 | **一字未改**：清单门判定照旧；门不过 → `would_export=false`、`exit_code=1`、**不出包**（实测：删掉一张随图 `.csv` → 预览说不过，真导出同样不过，包目录前后都不存在） |
| 预览 vs 真导出 | 副本盘 paper 上预览列的 36 件，与真导出写进包里的**逐件 sha256 一致** |

### 10.7 发布态逐文件比对（源 → 载荷 → 已发布）

| 项 | 读数 |
|---|---|
| `miniapp/build.sh` | 跑通：文件数 111（上限 1024）／4.8 MiB／契约自检通过／engine import ok／**104 个载荷文件** |
| 前端三件 | `app.js`(`60c615fb…`)／`app.css`(`e0bfdbb0…`)／`index.html`(`7dd179f5…`)：源＝载荷两份副本＝已发布两份副本，**五处全等** |
| 引擎 | `diff -r factscribe <已发布>/miniapp/node/engine/factscribe`（排除 `__pycache__`）：**0 差异**（含 `write.py` 改动、`checkreport.py`、`bundle.py`、`scaffold.py`） |

### 10.8 正式盘零改动（实测）

| 盘 | 开工前聚合 sha256 | 验收后聚合 sha256 | 结论 |
|---|---|---|---|
| `paper` | `fb03eaf1c3bc9d3…` | `fb03eaf1c3bc9d3…` | 一致 |
| `paper-zh` | `8f16d331bda67c28…` | `8f16d331bda67c28…` | 一致 |
| `paper-b` | `4d5ccf9855f4bf84…` | `4d5ccf9855f4bf84…` | 一致 |
| `paper-b-zh` | `9d1fe50993d38094…` | `9d1fe50993d38094…` | 一致 |

（聚合口径与上一轮同一条：逐文件「相对路径 ＋ 文件 sha256」串起来再 sha256。）
另外：四盘 `find -newermt '2026-11-23 11:50' -type f` **为空**；`paper` 的 `last_opened` 仍停在 **2026-11-23 11:12:13**（没打开过正式盘）。
宿主论文根目录仍是 `/Users/moc/workspaces/SiAgent`（`config.json` 未改），publish 后已 `miniapp restart` 重拉引擎。

### 10.9 本轮测试

| 项 | 读数 |
|---|---|
| 新增 `tests/test_workbench_save_fidelity.py` | **14 条**（连续两次保存逐字稳定；stale DOM 拒写且文件逐字节不变；序号不存在 → 拒写不静默丢；保护面不许丢；**正文同名数字不许被认成别处的绑定令牌**（§10.12）；**结构闸**：保护面数量对不上 → 拒写、对得上 → 放行（§10.13）；前端指纹与 `expect_tokens` 口径的静态断言） |
| 新增 `tests/test_workbench_evidence_lock_card.py` | **7 条**（独立卡；与 `evidence_gate` 同源；冻结读数；清单变了报差异；四步链形状不变；MCP 输出形状不变；页面不多一次调用） |
| 新增 `tests/test_workbench_bundle_preview.py` | **4 条**（门不过：预览与真导出同一结论、都不出包；门过：预览与包内文件逐件 sha256 一致；预览不写盘；两次预览结论一致） |
| 补强 `tests/test_fact_add.py` | **+2 条**（value 不在产物里被拒且账本零改动；人手手写的坏 value 仍被审计报 `VALUE_NOT_IN_SOURCE`） |
| 新增 `tests/save_probe_driver.mjs` | 真浏览器驱动（`normal`／`stale` 两种模式） |
| 既有测试改用真实样本（**不放宽校验**） | `tests/test_workbench_fact_form.py`（value `"1"` → `"10/16"`）、`tests/test_mcp.py` 与 `tests/test_serve.py`（`"42"` → `"10"`）、`tests/test_doctor.py`（产物补上 `16`）、`tests/test_method_workflow.py`（产物补上 closed 臂 `8`） |
| 用例总数 | 基线（HEAD `2fdf3bf`）**2271** → 本轮 **2298**（**+27**：A 14 ＋ B 2 ＋ C 7 ＋ D 4），**0 减少** |
| 全仓 `pytest tests/ -q` | **2298 passed / 0 failed**（397 subtests，301.00s） |

### 10.10 本轮明确**没动**的东西

| 事项 | 怎么保证没动 |
|---|---|
| 四步链闸门语义 | `checkreport._chain_steps` 未改；`chain` 与 `evidence` 两个键的载荷逐字不变（实测 diff 为空） |
| 提议单形状校验（块形状闸） | `_block_shape_guard` 未改 |
| 双 Profile 契约 / P-152 | 未触及任何判定面 |
| `Issue.as_dict()` 的形状 / 金样例基线 | 未改、未重冻（`tests/golden/audit_findings_baseline.json` 一个字节没动） |
| `scaffold._check_source` 的既有校验 | 一条没放松（`check_value_in_source()` 是**新增**的一道闸） |
| 落盘层散文＋token 口径 | token 格式、占位符口径、保护面三条口径一字未改；只把「序号对不上」从静默丢弃改成拒写 |
| 绑定数字保护面 | 口径未动（`num` 仍是派生令牌）；新增兜底只管命令类保护面 |
| MCP 工具既有入参 schema | `fs_*` 一字未动；`fs_get_report` 的输出形状也没变（它自行整形载荷） |
| 导出口径（清单门） | 一字未改；预览只是可选的一步 |
| 配置文件备份份数 | 仍 `CONFIG_BACKUP_KEEP=1` |
| 正式稿盘 | 四个盘聚合 sha256 与开工基线**逐位一致**；`last_opened` 未动；宿主论文根目录未改 |

### 10.11 记着、没擅自动的

* **stale 场景下飞行途中新打的字会丢**：客户端在块仍被聚焦时不能整块重绘（会吞掉新字）；要保住它得做客户端↔服务端的合并重写（rebase），风险大于收益。沿用既有 BLOCK_STALE 语义「未保存的字会丢」——本轮优先保证「**内容不被改**」。
* **探针尾数字单独消失**（`[HOSTBAK1]` → `[HOSTBAK]`）这一形态：修掉的是同一机制族（保护面序号整体错位 → 保存改内容），真浏览器复现出来的是 `0/3` 被换成 `\fact{E5}`、凭空多出 `0/2`。那一形态要求探针里那个数字**本身**是一枚绑定令牌（账本里有这个值，或它紧邻 `\fact{}` 且其后只跟空白）——四个盘的账本里**没有裸值 `1`**，所以在本工作树**未能单独复现**：如实记，不把没复现的说成复现了。

### 10.12 A 追加修 · 派生数字令牌被误认领（保存把芯片旁的数删掉）

前两层修完（§10.2）之后，正常路径仍有一处会改内容：**派生**出来的绑定数字令牌（`num`）会被按**文字**认领。

**机制**（`write.py::_absorb_verbatim`）：服务端重建时会把正文里「原样抄回」的保护面认回来（判据＝逐字相同）。它把**命令类**保护面（`\fact{}`／`\cite{}`…）与**派生**的绑定数字令牌（`num`）一视同仁。绑定数字令牌是**派生**的（紧邻 `\fact{}` 或与账本同值），它的字面在正文里本来就可能出现——正文写「还是 8 题」，那个 `8` 就被认成别处那枚 `num` 令牌：令牌被搬到正文位置，**芯片旁边的绑定数字整段消失**，用户没打过的字被改掉。

**实测**（副本盘 `paper` 的 `01_intro-p1`）：第一次保存后正文是 `…left the resolve count at 0/3[HOSTBAK1]\fact{E5}…`；第二次保存（客户端 DOM 已按新文重绘）后变成 `…left the resolve count at \fact{E2}…`——`E2` 那枚 `num` 令牌前的 `0/3` 没了。

**修法**：`_absorb_verbatim` **不再按文字认领 `num` 令牌**——派生令牌只认占位符。命令类保护面的认领口径、token 格式、散文＋token 口径一字未动。

**回归测试**（`tests/test_workbench_save_fidelity.py`，先红后绿）：正文里的同名数字不许被认成别处的令牌（一次保存都不许挪）；探针打散令牌后连续两次保存逐字稳定。

### 10.13 A 追加修 · 结构闸（客户端报「这份 DOM 是哪一版**结构**渲染出来的」）

指纹闸管的是「哪一版**内容**」；还有一路是「哪一版**结构**」：账本变了（新事实的 value 出现在正文里 → 同一段原文多出绑定数字令牌），同一段原文的**保护面数量**就变了 → 客户端那份 DOM 里的占位符序号**整体错位** → 按旧序号重建，用户没打过的字被改掉。指纹闸抓不到它（块原文一个字没变，指纹照样对得上）。

**修法**：客户端把「这份 DOM 里有几枚保护面芯片」跟着一块儿报上来（`state.blockTokens` → 请求里的 `expect_tokens`），服务端拿当前扫描的保护面数一对，对不上就**拒写**（`EDIT_TOKEN_COUNT_MISMATCH`，HTTP 409，附新鲜块让前端重载）。不传这个字段就不做这道检查（老客户端／脚本调用不受影响）。

**实测**：

| 项 | 读数 |
|---|---|
| 四个盘（副本）逐块比对「渲染 html 芯片数」vs「服务端扫描保护面数」 | 可编辑块 **112 段正文 ＋ 4 段摘要全等**；114 个标题块（`section`／`subsection`）html 为空（页面上没有可编辑 DOM，客户端不会保存它们）→ 不参与这道闸 |
| HTTP 实测 | 故意报 `expect_tokens=999` → **409 `EDIT_TOKEN_COUNT_MISMATCH`**；报正确数量 → **200 落盘** |
| 真浏览器 `normal` 路 | 两次保存照旧通过（`expect_sha` 正常推进 `055edf89…` → `240fc2f7…`），探针区逐字保留 |
| 真浏览器 `stale` 路 | 第二轮撞指纹闸被拒写（`expect_sha` 两次都是 `055edf89…`），**落盘文件两次逐字节相同** |

### 10.14 一个**既有**现象（如实记：不是本轮引入）

保存一段时，落盘的是**页面上看到的那份文字**：渲染层把段内换行压成空格、把 `---` 写成 `—`（`projects._inline`／`render_prot_html` 的既有口径），所以第一次保存会把**该段内**的这几处规范化。实测（`01_intro-p1`）：段内 **45 处换行 → 空格**、**4 处 `---` → `—`**；**块外一个字节没动**（文件其余部分逐字节相同）。

这是「页面即编辑器」这条既有设计带来的（`projects.py` 与 `app.js::collectPlain` 本轮一字未改，HEAD `2fdf3bf` 就是这样），**不是本轮引入**。含义：用户**看得见**的字（数字、芯片、探针）逐字保留；看不见的空白与连字符按既有口径规范化。想要连空白也逐字保留，得让落盘层按原文偏移回填未改动的散文——那是改「落盘层散文＋token 口径」，本轮明确不动。

## 11. 2026-11-23 第七轮：三个用户诉求（章节名/论文标题 · 右栏可拖 · \fact 插入）

- 分支：`feat/miniapp-host-seam`（开工 HEAD `71e824b`；**未推远端、未建 PR、未 sign**）
- 三个诉求：① 标题与章节名称怎么改 ② 右栏「职能助手」太窄，要能自由拖动改左右比例 ③ `\fact{…}`／`\cite{…}` 等保护面命令手写费劲
- 验收台：**真 Chrome（headless）＋ CDP**（真鼠标事件／真键盘事件，不是页面里合成的 `dispatchEvent`），驱动 `tests/miniapp_ui_driver.mjs`；盘＝`examples/minimal` 的 `/tmp` 副本
- 三件事**串行**做（碰同一批前端文件），核心层另开**三条独立写盘通道**，不借道 `/edit`

### 11.1 现状查证（读码核实，不是推断）

| 诉求 | 核实到的现状 | 处置 |
|---|---|---|
| ① 标题与章节名 | 封面标题 `#coverTitle` **只读**，值＝`state.meta.name`＝该盘入口 .tex 的 `\title{…}`（`projects.py::_tex_title_parts`，按 `\` 分主/副标题）；核心**没有**写入口 .tex `\title{}` 的能力（CLI 全子命令已核对）；Miniapp「编辑项目」表单里的「论文标题」写的是 `factscribe.toml` 的 `[project].title`（`update_paper_project`）——与封面显示的**不是同一层**（既有口径错位，本轮不动） | 章节名：**核心已有**能力（`write.py::_block_shape_guard` 专为 heading 块写）但 Miniapp 没暴露 → 接进来；论文标题：核心无 writer → 按核心约定新写 `set_disk_title`，与封面读侧共用同一处定位（`title_command_span`） |
| ② 右栏宽度 | 右栏是 **Miniapp 自己渲染**的：`index.html` 的 `<aside class="navpanel" id="navPanel">`（三面互斥：目录／智能助手／更多），CSS `position:fixed;right:0;width:320px`、`.shell{padding-right:336px}`；宿主框架**没有**「职能助手」字样（宿主 `app.asar` 与 `~/.minimax` 全搜 **0 命中**）→ 用户所指＝Miniapp 右栏的「智能助手」面板 | 宿主侧无配置入口 → **在本页实现分隔条**（拖动改左右比例、刷新后保留、上下限） |
| ③ 保护面 | 芯片由服务端烤进 html（`<span class="fc prot-chip" data-token=… contenteditable="false">`）；客户端 `collectPlain()` 只收「散文＋token」；服务端 `write.py::_rebuild` 用 `_strip_injected`（`_INJECT_RE`）**剥掉**客户端散文里新写的 `\fact{…}`／`\cite{…}`／`\ref{…}` 等（并告警）→ **手打标签今天根本写不进去**（痛点属实） | 两条路取风险最低的一条：做「插入事实」面板（数字来自账本＋过既有 value 硬闸）；**不做**纯前端命令补全——补出来的 `\fact{}` 会被服务端剥掉，等于假功能 |

### 11.2 核心层：三条**独立**写盘通道

三条都不碰 `/edit` 的「散文＋token」写回（那条通道会把标题命令整条写掉，也会把客户端新写的 `\fact{}` 剥掉）。共同纪律：**只动那一处**，其余字节一字不改；指纹闸（`expect_sha` 对不上 → `BLOCK_STALE` 拒写）；原子写＋`.bak` 轮转。

| 通道 | 位置 | 改什么 | 闸 |
|---|---|---|---|
| `rename_section()` | `factscribe/workbench/write.py:1640` | 只改 `\section{…}`／`\subsection{…}` 花括号里那一段（`_rewrite_heading_title`，`write.py:1626`），文件其余字节不动 | `_check_expect_sha`（块指纹）＋ 必须是 heading 块 |
| `set_disk_title()` | `factscribe/workbench/write.py:1674` | 盘自己入口 .tex 的 `\title{主 \\ 副}`；定位与读侧**同源**（`projects.title_command_span`，`projects.py:165`；读侧 `_tex_title_parts` 已改为复用它，行为逐字不变） | `_short_sha(raw) != expect_sha` → 拒写；文本按既有约定 `scaffold.tex_escape` 转义 |
| `insert_fact_binding()` | `factscribe/workbench/write.py:1772` | 在正文里那个数字后面插 `\fact{id}` 标记 | 三道铁律：① 事实**必须在账上**（否则 `FACT_NOT_IN_LEDGER`）② value **必须过既有 value 硬闸**（`scaffold.check_value_in_source` ＋ `resolve_source`，与「追加事实」同一道，未改判据）③ 数字**只能来自账本 value 原文**（正文已有这个数 → 只补标记 mode=`marker`；没有 → 连数字带标记插段末 mode=`value`）；同段已有同事实标记 → `FACT_ALREADY_BOUND` |

落点判据与 audit 的内联绑定**同一套**（`facts.fact_value_keys` ＋ `number_key` ＋ `literal_tokens`），优先取 value 字面写出的第一个数字（分数取分子，与样例稿写法一致）。

配套：`server.py` 新增 `POST …/toc/rename`（:573）、`POST …/title`（:585）、`POST …/fact/insert`（:594）、`GET …/facts`（:353），写接口统一走 `_write_error()`（机器码＋槽位，409/400 分流，:742）与 `_fresh_shas()`（:749）；`readings.facts_list()`（:285）只读列账，复用机器视图的账本表（`checkreport._ledger_rows`），不另算。

### 11.3 前端三个入口 ＋ 分隔条

| 入口 | 位置 | 说明 |
|---|---|---|
| 目录行 ✎（改章节名） | `app.js:2609`／:2623，`index.html:475`（`#modalRename`） | 每行一支笔（调序/删除是**按文件**的，改名是**按这一节**的）→ 走 `tocAction('toc/rename', …, expect_sha)` |
| 封面标题旁的 ✎（改论文标题） | `app.js:1305`／:1314，`index.html:145` | 改的是**这个盘自己入口文件**里的标题命令；带 `state.meta.title_sha`（`projects.disk_meta` 新增，:1146）→ 成功后重读 meta 刷封面 |
| 段落 ⋯ 菜单「插入事实」 | `app.js:2667`／:2691／:2717，`index.html:165`＋:504` | 读 `GET …/facts` 列账上事实 → 选中后 POST `…/fact/insert`，用回包 `blocks`＋`shas` 原地重绘（芯片重绑） |
| 右栏分隔条 | `app.js:5793`（`initNavSplitter`）、`app.css:1021`／:1568、`index.html:173` | 宽度走 CSS 变量 `--nav-w`；pointer 事件拖动时实时变；**松手**才记进 `localStorage['factscribe.navw']`；双击回默认；`240 ≤ 宽 ≤ 640`，正文至少留 420 |

> 宽度持久化用 localStorage（界面偏好，与项目数据无关；与既有「中/EN」开关同一做法）。
> 松手时记的是**本轮生效宽度** `currentNavWidth`，不是回头读存储里的旧值——旧写法会把刚拖出来的宽度弹回 320（已实测复现并修掉）。

### 11.4 真浏览器实跑读数（真 Chrome ＋ CDP，真鼠标/真键盘）

盘＝`examples/minimal` 的 /tmp 副本（账上追加一条测试事实 `A4`：value=16，产物 `results/swb16.md` 里确有 16）。

| 项 | 怎么做的 | 实测读数 | 判定 |
|---|---|---|---|
| 改章节名 | 目录行点 ✎ → 弹窗填「E2E 章节名」→ 保存 | 目录：`["Introduction","Results"]` → **`["E2E 章节名","Results"]`**；弹窗开合正常；落盘 `\section{E2E 章节名}` | 通过 |
| 改论文标题 | 封面点 ✎ → 填主标题/副标题 → 保存 | 封面：`"factscribe 最小验收样例 / Disk: paper-demo"` → **`"E2E 论文标题 / E2E 副标题"`**；落盘 `\title{E2E 论文标题 \\ E2E 副标题}` | 通过 |
| 拖分隔条 | 真鼠标按住分隔条左移 160px | 宽度 **320 → 481**（`--side-w` 同步为 497px）；pointer 事件计数 down=1／move=9／up=1；`localStorage['factscribe.navw'] = "481"` | 通过 |
| 刷新后保留 | 刷新页面 → 重新打开这篇稿子 | 宽度**仍是 481**，存储仍是 "481" | 通过 |
| 上下限 | 拖到最左／最右 | 最宽 **640**、最窄 **240**；正文左栏仍 **1184px**（没被拖没） | 通过 |
| 插入事实 | 段落 ⋯ 菜单 → 插入事实 → 选 A4 | 芯片数 **6 → 7**；面板列出账上 4 条（`A1/A3/A2/A4`）；toast「Fact marker inserted」；落盘：`开臂…在 16\fact{A4} 道题里解决 10 道\fact{A1}。` | 通过 |

### 11.5 落盘复核（副本盘上的实际字节）

~~~text
main.tex:      \title{E2E 论文标题 \\ E2E 副标题}
01-intro.tex:  \section{E2E 章节名}
01-intro.tex:  开臂（允许工具调用的那一臂）在 16\fact{A4} 道题里解决 10 道\fact{A1}。
bak 存在:      True True          ← 两侧 .bak 都生成了
~~~

三处的共同点：**只动那一处**——改章节名没有碰同一节里的 `\fact{A1}`／`\fact{A3}`／`\label{sec:intro}`；改标题没有碰 `main.tex` 的其余部分（导言区、`\newcommand{\fact}`、`\input` 链一字未动）；插事实没有碰这一段的其他句子。

### 11.6 发布态三方一致（源 → 载荷 → 已发布插件）

| 项 | 读数 |
|---|---|
| 载荷同步 | `miniapp/build.sh` 跑通：文件数 **111**（上限 1024）／**4.9 MiB**（上限 64 MiB）／契约自检通过／engine import ok／**104 个载荷文件** |
| 前端三件 | `app.js`（`3098c8a2…`）／`app.css`（`4068f1f5…`）／`index.html`（`71f8d65d…`）：源＝载荷＝已发布，**三方逐字节一致** |
| 引擎 | `factscribe/**` **98 个文件**：源 vs 载荷 **0 差异**；载荷 vs 已发布 **0 差异**（含新增的 `readings.facts_list` 与三条写盘通道） |
| 载荷整棵 vs 已发布整棵 | **104 / 104 文件，0 差异** |

### 11.7 正式稿盘四盘零改动（实测）

以第五轮（11:50）的快照 `/tmp/fs-batch5-root`（四盘 `cp -a` 副本）为对照，**逐文件**比 sha256：

| 盘 | 对照结果 | 结论 |
|---|---|---|
| `paper-b` | 33 / 33 文件**逐字节全等** | 零改动 |
| `paper-b-zh` | 33 / 33 文件**逐字节全等** | 零改动 |
| `paper-zh` | 除 `factscribe.toml` ＋ `factscribe.toml.bak` 外**全等** | 正文/账本/证据/文献零改动 |
| `paper` | 副本多 5 个 `01_intro.tex.bak*`（第五轮在副本上做保存测试留下的），且副本的 `01_intro.tex`／`a_swebench.toml` **含探针与测试事实**（`[HOSTBAKC]`／`[E2E-batch5-A]`／`id="Z10"` 等），**官方盘里没有** | 差异方向是**副本被写过**，官方盘保留原样 |

官方盘今日被写过的文件只有 4 个（都在 `paper` 与 `paper-zh`）：

~~~text
15:02:31  paper/factscribe.toml
15:02:31  paper/factscribe.toml.bak
15:02:39  paper-zh/factscribe.toml
15:02:39  paper-zh/factscribe.toml.bak
~~~

差异**只有一行**（引擎 `write.touch_opened` 写的打开时间戳，属**已知副作用**，非 bug）：

~~~text
< last_opened = "2026-11-23T11:12:13+08:00"     ← 上一版仍保留在 .bak 里
> last_opened = "2026-11-23T15:02:31+08:00"
~~~

正文、事实账、证据链、文献、`main.tex`：**一个字节都没动**（逐文件 sha256 比对，见上表）。

### 11.8 本轮测试

* 新增 `tests/test_workbench_title_fact_binding.py`：**20 条**（改名只动标题命令／指纹闸拒写／标题改的是入口 .tex 且与读侧同源／插入事实三道铁律各一条／`render_tex` 块偏移回归锁／真起服务的端点用例）
* 新增 `tests/test_miniapp_ui_features.py`：**35 条**＝**30 条静态断言**（三个入口的结构、指纹闸、双语文案齐不齐、客户端不许拼 `\fact{}`）＋ **5 条真浏览器行为**（改名／改标题／拖宽与刷新保留／上下限／插入事实）
* 新增 `tests/miniapp_ui_driver.mjs`：真 Chrome ＋ CDP 驱动（真鼠标按下-移动-松开、真键盘输入、刷新复测）
* 改 `tests/test_workbench_layout.py`：条目 40 案二的静态闸原钉着硬编码 `padding-right:336px`%；右栏宽度改由 `--nav-w` 驱动后，闸改成钉「`padding-right:calc(var(--nav-w,320px) + 16px)`」＋「`:root{--nav-w:320px}`」——**让位宽度仍与侧栏同源**，只是不再写死（这是本轮唯一被改的既有测试断言）
* 全仓 `pytest tests/ -q`＝**2353 passed / 0 failed**（上一轮基线 2298，本轮 **+55**）

### 11.9 本轮明确**没做**的事

| 事项 | 为什么 |
|---|---|
| 不做纯前端「`\fact{…}` 命令补全」 | 补出来的标记会被服务端 `_strip_injected` 剥掉——做成是个**假功能**；要做就得动 `_rebuild`／`_strip_injected` 那条落盘层口径（已定口径） |
| 不动 `[project].title`（项目表单的「论文标题」） | 它与封面显示的 `\title{}` 本来就不是同一层（既有口径错位）；本轮只补「改封面那一条」的入口，既有表单**一字不改** |
| 不动 `/edit` 通道的散文＋token 写回与 `\fact`／`\cite` 保护面 | 三条新通道各自独立，绕开它而不是改它 |
| 不动四步链闸门语义、提议单形状校验（块形状闸）、双 Profile 契约、`_check_source` 校验语义、`Issue.as_dict()` 形状 | 已定口径，一律未动；`tests/golden/audit_findings_baseline.json` **未重冻、未改一个字节** |
| 不给「插入事实」加人工确认步 | 它不是改稿通道：插的是**账上已有**的事实标记，不改用户写的散文；指纹闸 ＋ value 硬闸两道已经在服务端把住 |
| 不删前几轮遗留的 /tmp 副本盘 | 与本轮无关，留着不动 |

### 11.10 顺带修掉的一个**既有**缺陷 ＋ 只记录不修的一个

**D-1（已修）`render_tex` 块尾截断**——含环境标记（`\begin{…}`）的段落，块尾会被截在半截命令上（因为 `flush()` 拿「缓冲区长度」倒推块尾，而环境标记不进缓冲区却占文件位置）；写回偏移随之错位（实测曾把事实标记插到 `\cite{chen2023factscore}` 中间）。

| 读数 | 修前（HEAD `71e824b`） | 修后（工作树） |
|---|---|---|
| `02-results.tex` 的 para 块 `start/end` | **18 / 296** | **18 / 348** |
| 块原文长度 | 278（尾部停在 `\cite{che`） | **330**（尾部完整到 `\cite{ghost2024}`） |
| 是否含完整的 `chen2023factscore}` | **否** | **是** |

修法只改偏移计算（新增 `buffer_end`／`region_open` 两个跟踪量），**块结构不变**（块数、kind、id 全同），不触及任何已定口径。回归锁在 `tests/test_workbench_title_fact_binding.py::RenderSpanTest`。

**D-2（只记录，本轮不修）空行分段从未生效**——`projects.py:789` 的 `if char == "\n" and source[index:index + 2] == "\n":` 拿 **2 字符**的字面量去比 **1 字符**的 `char`，恒假。实测：`01-intro.tex` 里两段散文（中间一个空行）被合并成**同一个** para 块（块数只有 [section, para]，块内 `\n\n` 有 2 处＝3 段并作一段）。

本轮**没有**动它：修它会大幅改变块结构与编辑粒度（一个章节文件＝一个可编辑段），属**独立的产品决策**，不是本轮能顺手带过去的——需要用户拍板是否要按空行分段（以及分段后保存/指纹/审计的粒度怎么跟着变）。

---
