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
| P2-1 | EN 界面下「机器视图 › 导出与命令」四行命令说明仍是中文 | `factscribe/workbench/checkreport.py:559` 硬编码中文 label；EN 界面截图 `p5-machine-view.png` | 英文界面出现中文（文案不完整），不影响功能 | 记录 |
| P2-2 | 提议单差异卡的内容（Current / After adopting）由引擎生成，中文硬编码 ⇒ EN 界面下卡片文字仍是中文（卡片标题已 i18n） | `factscribe/workbench/proposals.py`（`before_text/after_text` 生成处）；`p8-proposals-list.png` | 同上 | 记录 |
| P2-3 | 「Append fact」卡的来源标注显示「Unknown source」（其余三类显示「From assistant」） | MCP `fs_propose_add_fact` 建单未带 source 字段，UI 无从标注 | 溯源信息缺失（展示层） | 记录 |
| P2-4 | `.bak` 只有一格深：第二次保存会把 `.bak` 覆盖成上一版（已编辑版），「原稿留在 .bak」的承诺在连续两次保存后不成立；且**刷新页面会触发一次自动保存** | 实测：首存后 `.bak` 为原稿；刷新页面后再看，`.bak` 已是编辑版（探针文本在 .bak 里） | 误改后无法从 .bak 回到最初原稿；刷新会多一次写盘 | 记录 |
| P2-5 | 追加事实默认落到 `facts/01-core.toml`，而本项目既有账本命名是 `a_/b_/c_…`；采纳后会**新增一个账本文件** | `proposals.py::propose_add_fact` 预览即如此写；`facts/01-core.toml` 已生成 | 账本文件分裂（虽能被 `facts/*.toml` 通配收进来，但命名不一致） | 记录 |

> 另有一条**环境属性**（非缺陷）：`cp -a` 出来的盘没有证据冻结流程历史，所以副本上四步链第 4 步「出证」显示未齐（106/106 但未齐）；原盘自带冻结件时该步为齐。

### 需要用户拍板的口径级事项（本轮未动）

- 无。本轮没有改动任何已定口径（四步链闸门语义、提议单形状校验、双 Profile 契约），也没有重冻 `tests/golden/audit_findings_baseline.json`。
- 若要修 P2-1/P2-2（i18n 补齐），需要动引擎侧文案表与 `?lang=` 传参口径，属「改已定口径」的边界，建议先拍板再做。

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
