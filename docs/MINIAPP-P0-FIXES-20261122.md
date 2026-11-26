# FactScribe MiniApp 五条 P0 修复报告

> **基线**：上一轮已验证的四项修复（分支 `feat/miniapp-align-20261122`，commit `6c39973`）
> **本轮分支**：`feat/miniapp-p0-20261122`（工作树 `.worktrees/miniapp-p0`）
> **依据**：`docs/MINIAPP-ALIGNMENT-AUDIT-20261122.md` §0.2「必须改的几条（P0，五条）」
> **日期**：2026-11-22　**纪律**：未改主检出、未改 `.worktrees/miniapp-host`／`.worktrees/miniapp-align`／`.worktrees/miniapp-audit`；未推远端、未建 PR、未合主线。
> **真跑**：全部读数来自实跑（仓外台架 + 真实论文的临时拷贝），不是读码推断。

---

## 0. 一页纸结论

五条 P0 **全部已修**，逐条都有「成因定位 → 改法 → 实跑读数」：

| P0 | 事项 | 状态 | 落点 | 实跑证据 |
|---|---|---|---|---|
| P0-1 | 文风闸＋双语对账进检查报告 | ✅ | `factscribe/workbench/checkreport.py`＋`server.py`＋前端两张折叠卡 | 报告新增 `gates` 段；界面 3 张卡 → 5 张卡 |
| P0-2 | 提议单替换文本加块形状校验 | ✅ | `factscribe/workbench/write.py:873` | 整文件贴进来：HTTP 400 拒收（原来照单全收、零告警） |
| P0-3 | 修 `rp.empty` 键覆盖 | ✅ | `factscribe/workbench/static/app.js` | 0 发现显示「没有发现：这盘干净。」（原来显示导入提示） |
| P0-4 | 四步链标签/说明改前端 i18n | ✅ | `checkreport.py:285-306`＋`app.js:1389` | EN 界面四步链全英文（原来「1声明ready / 2绑定ready…」） |
| P0-5 | 「打开」记住当前盘 | ✅ | `write.py:1491`＋`projects.py:275-361`＋`app.js:1202` | 切到中文盘后回列表再「打开」，落回中文盘（原来回落英文盘） |

**全仓测试**：`pytest tests/ -q` → **2094 passed / 0 failed**（详见 §7）。
**新增测试**：`tests/test_miniapp_p0.py`（33 例）+ `tests/test_workbench_i18n.py` 补 1 例（重名键契约）。

### 改动落在哪一侧

| 侧 | 文件 | 风险点 |
|---|---|---|
| **Python（factscribe/）** | `workbench/checkreport.py`、`workbench/write.py`、`workbench/projects.py`、`workbench/server.py` | 写回保护链**未改落盘语义**，只在输入端加了一道形状闸；`report_payload` 新增**可选**参数与新字段，旧消费者不受影响 |
| **前端（薄壳/工作台）** | `workbench/static/app.js`、`workbench/static/index.html` | i18n 字典改动面大（中英各 +30 键）；新增两张折叠卡 |
| **构建/载荷** | `miniapp/build.sh`、`miniapp/miniapp/client/*`、`miniapp/miniapp/node/engine/*` | `build.sh` 新增一步 vendoring `style-rules.toml`；载荷内容随之变化（插件发布时需重跑 build） |

---

## 1. P0-1　文风闸＋双语对账进检查报告

### 1.1 成因定位

| 位置 | 问题 |
|---|---|
| `factscribe/workbench/checkreport.py:141-157`（基线） | `report_payload()` 只跑 `run_gate`（audit ＋ 清单门），**没有 style／mirror-check 的任何调用** |
| `factscribe/workbench/checkreport.py`（全文件） | 基线里零处引用 `factscribe.style`／`factscribe.mirror` |
| `factscribe/workbench/server.py:229-270` | `GET /api/disk/<p>/<d>/report` 把整盘路径交给 `report_payload()`，**拿不到「另一个盘」**，所以双语对账无从谈起 |
| `factscribe/workbench/static/index.html:305-360` | 报告模态里只有三张折叠卡：体检／发现／四步链 |
| MCP 工具面 | 八个工具里**没有** style／mirror-check 的只读工具（审计 §2 维度 12） |

### 1.2 改法

**只读调用路径**（查清结果）：

* `factscribe style` → `factscribe/cli.py:1771 cmd_style` → `factscribe/style.py:3068 analyze(cfg, sections, rules, …)`，
  规则来自 `factscribe/style.py:713 load_style_rules_info(project_root, None)`（只读 TOML）。
* `factscribe mirror-check` → `factscribe/cli.py:1333 cmd_mirror_check` → `factscribe/mirror.py:302 check(disk_a, disk_b)`
  → `factscribe/mirror.py:354 drift_dicts(result)`（只读两个盘的事实账与文献）。

两条都是**纯库接口**，不需要 subprocess，也不需要新 MCP 工具。

**引擎侧**（`factscribe/workbench/checkreport.py`）：

* 新增 `_style_gate(cfg, sections)`（:187）：跑 `analyze()`，把 style 的 `Finding` 映射成报告里那条 finding 的**同一套字段**
  （code／severity／message／location／token／context），并给出 `status`（ok／yellow／red／error）与 `summary`。
* 新增 `_mirror_gate(disk, sibling)`（:217）：跑 `mirror.check()`，给出 `status`（ok／drift／na／error）、`drift` 明细与 `summary`。
  没有第二个盘时是 **na（不适用）**，不是错。
* `report_payload(disk, sibling_disk=None)`（:317）新增一个**可选**参数，返回体新增 `gates` 段（:374）。
  **主体检（health）与发现清单（findings）完全不变** —— 文风黄牌**不混进主黄牌计数**
  （审计 §0.2 明写「并入报告后黄牌数会涨……需要先把文风黄牌与审计黄牌分开计数，否则会吓人」）。
* `factscribe/workbench/server.py:162` 新增 `ProjectIndex.sibling_disk_path()`（优先另一个语言的盘），
  报告路由（:282）把它传进去。

**界面落位设计**（与既有契约不冲突）：

* **不并入「发现」清单**，另起两张**折叠卡**，与体检／发现／四步链并列（`index.html:362` `#cardStyle`、:372 `#cardMirror`）。
  理由：主红黄徽标的口径必须稳定（审计与清单门），文风读数单独成卡，用户一眼能分清「闸的红黄」与「文风的黄」。
* 文风卡：徽标＝命中条数（黄 n 条／红 n 条／没有文风命中）；卡内复用现成的 `findingRowHtml` 行列出命中（含位置）。
* 双语对账卡：徽标＝两盘一致／n 处漂移／本项目只有一个盘；卡内逐条列漂移（code／target／id／field＋两侧值）。
* 两张卡底部都有一行「只读读数：不改稿、不改盘。」——把「不触发任何改写」写进界面。
* 折叠卡的展开/收起是通用绑定（`app.js` 里 `$$('.rc-fold-h')`），新卡自动继承，零新增交互代码。

**构建侧**：`miniapp/build.sh` 新增一步，把仓根的 `style-rules.toml` 一起 vendoring 进 `<engine>/`。
理由：文风闸的规则查找顺序是「项目根 → **发行包根** → 包内」，发行包根＝`<engine>/`；少了它，
miniapp 的文风读数会退回内置默认值，与仓里 CLI 的读数不一致（`light_verbs.article_verbs` 等键有差异）。
vendoring 后薄壳侧实测：`rules path: <engine>/style-rules.toml  source: repo` ✅

### 1.3 实跑验证

**接口层**（沙箱 `/tmp/fs-p0-live/after`，真论文 paper-b 的临时拷贝）：

| 读数 | 基线（8891） | 本轮（8892） |
|---|---|---|
| 报告顶层键 | `['chain','disk','evidence','findings','generated_at','health','ok','project']` | 同上 **＋ `gates`** |
| `gates.style` | — | `{'status':'ok','red':0,'yellow':0,'count':0}` |
| `gates.mirror` | — | `{'status':'ok','count':0}`（paper-b ↔ paper-b-zh 逐条比对） |
| 单语项目（`paper`）的 mirror | — | `{'status':'na','note':'MIRROR_NO_SIBLING'}` |
| 有文风命中的盘（`paper`） | — | `style: yellow 1 条 → SECTION_OVERLAP sections/06_ablation.tex:13` |

**界面层**（ego-browser，1680×1020，真实 Chromium）：

* 基线报告模态：**3 张卡**（体检／发现／四步链）。
* 本轮报告模态：**5 张卡**（＋文风闸「黄 1 条」＋双语对账「两盘一致」）。
* 截图：`docs/miniapp-p0-shots/before-report-zh.png` ↔ `after-report-zh.png`；
  `after-report-gates-zh.png`／`after-report-gates-en.png`（两张新卡特写）。

### 1.4 与既有契约的关系

* **不冲突**：主体检判定面没动；`factscribe style`／`mirror-check` 两条 CLI 命令语义没动；MCP 八个工具没动。
* **MCP 工具面**：审计 P1 的 R11「助手侧补 `fs_get_style`／`fs_mirror_check`」**本轮没做**——P0-1 的要求是
  「并入检查报告」，助手侧补工具属 P1，且助手拿到的上下文（`factscribe/workbench/ai.py:300 report_summary`）
  仍只含体检摘要与四步链。**留在待办**（见 §9）。
* **性能**：报告接口多花约 0.3–0.5 秒（style 0.14s + mirror 0.1s + 两侧盘读账）。报告是一次性模态，可接受；
  若日后嫌慢，可在引擎侧加短 TTL 缓存（本轮没做，见 §9）。

---

## 2. P0-2　提议单替换文本加「块形状」校验

### 2.1 成因定位

**根因**：`factscribe/workbench/write.py:880-909`（基线）—— `propose_block_edit()` 对替换文本只查三样：
非空、块指纹（`expect_sha`）、花括号配平。**没有「块形状」这一道**。

**为什么四道保护链全部放行**：

| 闸 | 为什么没拦住 |
|---|---|
| 指纹闸 | 比的是**被替换块**的指纹，替换文本多长都不管 |
| 保护面重建 | `_rebuild()` 只把 `\\fact{}`／`\\cite{}`／绑定数字当芯片处理，`\\section{…}` 是普通散文，原样留下 |
| 花括号配平 | `\\section{Introduction}` 的花括号是配平的 |
| 原子写 | 只是写文件的方式，不看内容 |

**为什么「整份文件」会静默通过**：`projects.render_tex()` 把 `\\section{…}`／`\\subsection{…}`／`\\subsubsection{…}`
**各自切成一个块**（`projects.py:342 _HEADING_RE`）。于是正文段落块的 raw 里**永远不含节标题**——
一旦替换文本里冒出一个节标题，就一定是**别的块的**。

### 2.2 改法

新增 `factscribe/workbench/write.py:873 _block_shape_guard(block, text, disk_root, code)`，
在 `save_block()`（:959）与 `propose_block_edit()`（:999）**两处都调**（MCP 与页面两条路同源，
直接保存那条路同样有这个洞）。

**拦的三条（硬闸，抛 ConfigError）**：

1. **正文段（para／abstract／ai_draft）的替换文本里出现节标题命令** → 拒收。
   消息点名是哪一条标题、哪一段，并给出可操作的下一步。
2. **标题块（section／subsection）的替换文本里出现一个以上节标题** → 拒收。
3. **替换文本里的 `\\label{}` 与同文件**别的块**重名** → 拒收（LaTeX 锚必须全篇唯一）。

**告警的两条（软闸，只提示不拦）**：标题块的替换文本里没有节标题（写下去标题会消失）；
替换文本比原文长出很多（多半贴错了地方）。

**判据的取法**：标题命令集**与 `render_tex` 的切块命令集严格同集**（section／subsection／subsubsection），
所以「正文段里出现节标题」＝「混进了别的块的节标题」这条推断是闭合的，不会误伤合法的行内用法。

### 2.3 实跑验证

**先复现（基线 `6c39973`）**：`/tmp/fs-p0/repro_p0_2.py` 把 `paper-b/sections/01_intro.tex` 整份
（6030 字符，含 `\\section{Introduction}`）当作 `01_intro-p1` 的替换文本：

`BT`BT`BT`
基线：>>> 已通过：after_text 长度 6030  warnings: []
      >>> 落盘后文件长度: 6121  \\section{ 份数: 2     ← 采纳后多一份节标题，零告警
      RESULT=ACCEPTED_AND_WRITTEN
本轮：>>> 已拒收 code=PROPOSAL_SHAPE_MISMATCH
      >>> 消息: 替换文本里混进了别的块的节标题（\\section{Introduction}）——这一段是正文段落（01_intro-p1），不带节标题。你是不是把整个文件贴进来了？请只改这一段的文字。
      RESULT=REJECTED
`BT`BT`BT`

**MCP 工具面**（真起薄壳，走 `fs_propose_edit` 工具，仓外临时拷贝）：

| | 基线（miniapp-align） | 本轮（miniapp-p0） |
|---|---|---|
| 整文件当替换文本 | `ok: true`，建单成功，`warnings: []` | `ok: false`，`code: bad_request`，消息点名 `\\section{Introduction}` |
| 正常替换 | 建单成功 | 建单成功（**不受影响**） |
| 正文文件是否被动 | 未动 | 未动 |

**HTTP 面**（工作台 `POST /api/disk/<p>/<d>/proposal`）：基线 HTTP 200 建单；本轮 **HTTP 400** ＋同一条人话消息。

### 2.4 回归测试

`tests/test_miniapp_p0.py::BlockShapeGateTests`（8 例）：

* 整文件当段落替换文本 → 拒收（code ＋ 消息点名标题与段 id）
* 拒收时正文零字节变动
* **正常段落替换照旧通过**（`after_text` 含新措辞、`warnings == []`）
* **正常 `save_block` 照旧通过**（文件里真的换了字）
* `save_block` 同样拒收整文件（`EDIT_SHAPE_MISMATCH`）
* 标题块给两个标题 → 拒收；标题块给一个标题 → 通过
* 替换文本锚与别的块重名 → 拒收

---

## 3. P0-3　修 `rp.empty` 键覆盖

### 3.1 成因定位

`factscribe/workbench/static/app.js`——同一个 %BT!I18N` 对象里 `rp.empty` **定义了四次**，全在 depth=2：
基线 `app.js:51`（检查报告块）、`111`（实验报告块）、`337`（EN 检查报告块）、`399`（EN 实验报告块）。
JS 对象字面量**后者覆盖前者**，所以实际生效的是实验报告那块：
**0 发现时显示「该项目还没有报告，点右上角『导入实验报告』」**（中英皆错）。

**顺带查出的同类病根**：`rp.loadErr` 与 `rp.loading` 同样各定义两次，且**两次的值不同**——
检查报告块的 `rp.loadErr` 是「读检查报告失败」，被实验报告块的「读实验报告失败」覆盖。
审计只盯住了 `rp.empty`（因为它最显眼），但病根是「一个字典对象里允许重名键」。

### 3.2 改法

* 拆键（`app.js:51/52`、`126`、`352/353`、`430`）：
  * `rp.findingsEmpty`（发现卡与发现明细模态）
  * `rp.chainEmpty`（四步链卡空态）
  * `rp.reportsEmpty`（实验报告列表）
  * `rp.loadingReports` / `rp.loadErrReports`（实验报告面专用）
* 四处引用改走新键（`app.js:1494`、`1526`、`1619`、`2692/2696/2701`）。
* **把「同一份字典里不许有重名键」钉成契约**：`tests/test_workbench_i18n.py` 新增
  `test_no_duplicate_keys_in_a_dictionary`（zh/en 各查一遍）。

**现在 zh 与 en 两份字典各 479 个键，0 重名**（改前 zh/en 各有 3 个重名键）。

### 3.3 实跑验证

界面（ego-browser，中英各一张）：

| | 基线 | 本轮 |
|---|---|---|
| ZH 0 发现 | 「该项目还没有报告，点右上角『导入实验报告』。」 | **「没有发现：这盘干净。」** |
| EN 0 发现 | "No reports for this project yet — import one from the top-right button." | **"No findings — this disk is clean."** |

截图：`before-report-zh.png` ↔ `after-report-zh.png`；`before-report-en.png` ↔ `after-report-en.png`。

---

## 4. P0-4　四步链标签/说明改前端 i18n

### 4.1 成因定位

* 后端：`factscribe/workbench/checkreport.py` 的 `_chain_steps()`（基线 :157-175）把
  **「声明／绑定／回账／出证」与「facts/*.toml 里的事实条数」等说明硬编码成中文**塞进 JSON。
* 前端：`factscribe/workbench/static/app.js` 的 `chainStepHtml()`（基线 :1353）只把**状态词**
  （就绪／ready）走 `t()`，标签与说明直接用后端给的字符串 → EN 界面下半中半英。

### 4.2 改法

* **后端给结构化 key**：每一步新增 `label_key`（`chain.declare`…）与 `detail_key`（`chain.declare.detail`…）
  （`checkreport.py:285-306`）。
* **旧字段保留**：`label`／`detail` 仍在（**MCP 工具的对外形状不变**，`fs_get_report` 原样透传 chain，
  老消费者不破）。前端**优先用 key**，拿不到 key 时才回落旧字段。
* **前端负责翻译**：`app.js:1389 chainStepHtml()` 改走 `t(step.label_key)` / `t(step.detail_key)`；
  中英各补 8 个 `chain.*` 键。
* **附加闸的报错也给机器码**（`STYLE_FAILED` / `MIRROR_NO_SIBLING` / `MIRROR_CONFIG_INVALID`），
  界面文案由前端 i18n 出——**后端不往界面塞中文**（EN 界面不许半中半英）。

### 4.3 实跑验证

EN 界面四步链（DOM 读数）：

| | 基线 | 本轮 |
|---|---|---|
| 标题行 | `1声明ready` `2绑定ready` `3回账ready` `4出证ready` | `1Declareready` `2Bindready` `3Reconcileready` `4Certifyready` |
| 说明行 | `62 / 62 · facts/*.toml 里的事实条数` | `62 / 62 · fact entries in facts/*.toml` |
|  | `191 / 191 · 正文里 \\fact{} 绑定的数字` | `191 / 191 · numbers bound by \\fact{} in the body` |
|  | `103 / 103 · 证据冻结与 PDF 闸` | `103 / 103 · evidence freeze and the PDF gate` |

ZH 界面保持中文（`1声明就绪` …），两侧一致。
截图：`before-report-en.png` ↔ `after-report-en.png`（EN）、`after-report-zh.png`（ZH）。

### 4.4 回归测试

`tests/test_miniapp_p0.py::ChainI18nTests`（4 例）：四步都有 `label_key`／`detail_key`；
旧字段仍在（MCP 契约）；前端确实用 key 翻译；中英两份字典都有这 8 个键。

---

## 5. P0-5　「打开」记住当前盘

### 5.1 成因定位

* 前端：`factscribe/workbench/static/app.js` 的 `openProject(projectId, diskId)`（基线 :1131-1141）
  在没指定盘时**每次都回落英文盘**：`project.disks.find(d => d.lang === 'en') || project.disks[0]`。
* 后端：项目数据里**根本没有「当前盘」这个字段**。
  `write.py:1385 touch_opened()` 只写 `[workbench].last_opened`（时间戳），不记盘；
  `projects.py:275 aggregate()` 也只回 `last_opened`。
* 批准设计条目⑩要的是「打开按实时状态取盘（缺省英文盘＋存在性校验）」——**方向是对的，缺的是那个「实时状态」**。

### 5.2 改法

**写面**（`factscribe/workbench/write.py:1491 touch_opened()`）：
打开一个盘时，除了 `last_opened`，再写一条 `[workbench].last_disk = <该盘自己的盘号>`。
写的是**被打开的那个盘自己的 `factscribe.toml`**，`[workbench]` 同一张表、**同一次原子写**（同一个 `.bak`），
不碰 `facts/` 与正文。

**读面**（`factscribe/workbench/projects.py`）：
* `_disk_last_disk()`（:275）读每个盘自己的标记；
* `aggregate()`（:361）给项目层算 `last_disk`：判据＝**盘自己的标记指向自己**且 `last_opened` 最新；
  没有标记（从没在这个工作台打开过）就回落英文盘 → 第一个盘（与旧行为一致）。
* 次序用 `(_opened_sort_key, _config_mtime, id)` 三元组：`last_opened` 只到秒，**同一秒内**先后切两个盘时，
  靠配置文件 mtime（原子写会更新，精度到纳秒）定先后——否则「同秒切盘」会记错。

**前端**（`app.js:1202`）：`openProject()` 没指定盘时，先找 `project.last_disk`（存在性校验：盘还在吗），
找不到才回落英文盘 → 第一个盘。

**语言开关那一路**（条目⑭「开关连正文一起切」）**自动同步**：它本来就调 `openProject(project.id, disk.id)`，
而 `openProject` 会 POST `/api/project/opened` → `touch_opened` → 标记就写下了。

### 5.3 它写了什么、写到哪（用户最关心的一条）

| 项 | 值 |
|---|---|
| 写哪个文件 | **被打开的那个盘自己的** `factscribe.toml`，例如 `paper-b-zh/factscribe.toml` |
| 写哪张表 | `[workbench]` 表 |
| 写什么 | `last_disk = "paper-b-zh"`（该盘自己的盘号＝目录名） |
| 怎么写 | 既有 `rewrite_table()` 原子写（同目录 `.tmp` → rename），**每次留一个 `.bak`** |
| 会不会碰别的 | **不会**：不碰 `facts/`、不碰 `sections/`、不碰正文、不碰主检出的其它文件 |
| 用户怎么撤销 | 删掉 `[workbench]` 里的 `last_disk` 一行即可（或用 `.bak` 恢复） |

实测（沙箱）：

`BT`BT`BT`
AFTER 中文盘配置 [workbench]:
[workbench]
last_opened = "2026-11-22T15:10:03+08:00"
last_disk = "paper-b-zh"
BEFORE 中文盘配置 [workbench]:     ← 基线只写时间戳
[workbench]
last_opened = "2026-11-22T15:10:03+08:00"
`BT`BT`BT`

**界面实跑**（ego-browser）：打开项目 → 切「中」→ 回项目列表 → 再点「打开」：

| | 基线 | 本轮 |
|---|---|---|
| 重新打开落到的盘 | 英文盘（TOC：*Introduction / Related Work…*） | **中文盘**（TOC：*引言 / 相关工作…*） |

截图：`before-lastdisk-reopen.png` ↔ `after-lastdisk-reopen.png`。

### 5.4 回归测试

`tests/test_miniapp_p0.py::LastDiskTests`（6 例）：标记写进被打开的盘自己的配置；
**写面不碰 facts/ 与 sections/**；项目层回报 `last_disk`；没打开过 → 回落英文盘；
开过两个盘 → 最近的那个赢；前端确实用 `project.last_disk`。

---

## 6. 改了什么、没改什么

### 6.1 Python 侧（factscribe/）——都配了测试

| 文件 | 改动 | 对应测试 |
|---|---|---|
| `workbench/write.py` | 新增 `_block_shape_guard`（块形状闸，:862-947）；`save_block`／`propose_block_edit` 各调一次；`touch_opened` 多写一条 `last_disk`（:1491） | `test_miniapp_p0.py::BlockShapeGateTests`（8）、`::LastDiskTests`（6） |
| `workbench/checkreport.py` | 新增 `_style_gate`／`_mirror_gate`；`report_payload` 加可选参数与 `gates` 段；四步链加 `label_key`／`detail_key` | `test_miniapp_p0.py::GateReadingsTests`（7）、`::ChainI18nTests`（4） |
| `workbench/projects.py` | 新增 `_disk_last_disk`／`_opened_sort_key`／`_config_mtime`；`aggregate` 回报项目级 `last_disk` | `test_miniapp_p0.py::LastDiskTests` |
| `workbench/server.py` | 新增 `ProjectIndex.sibling_disk_path`；报告路由传 sibling | `test_miniapp_p0.py::GateReadingsTests` |

**契约语义没变**：写回保护链（指纹闸 → 保护面重建 → 花括号配平 → 原子写 ＋ `.bak`）的**次序与语义一字未改**，
形状闸是**输入端**的一道新闸；`report_payload` 的新参数**可选**、新字段**新增**，旧消费者不受影响；
MCP 八个工具的对外行为没变（四步链只**多了** `label_key`／`detail_key`，旧字段仍在）。

### 6.2 前端 / 薄壳

| 文件 | 改动 |
|---|---|
| `factscribe/workbench/static/app.js` | i18n 字典（拆 3 个键、拆 2 个重名键、新增 30 个中英键）；`chainStepHtml` 走 i18n；新增 `reportGates`／`renderGateCards`／`mirrorDriftHtml`；`openProject` 用 `project.last_disk` |
| `factscribe/workbench/static/index.html` | 报告模态新增两张折叠卡（`#cardStyle`／`#cardMirror`） |
| `miniapp/build.sh` | 新增一步 vendoring `style-rules.toml` 到 `<engine>/` |

薄壳（`miniapp/miniapp/node/server.mjs`）**未改一行**——它只做代理，形状闸在引擎侧，两条路（MCP 与页面）同源生效。

### 6.3 载荷

`miniapp/build.sh` 已跑过：`miniapp/miniapp/client/*` 与 `miniapp/miniapp/node/engine/*` 已与事实源同步
（`tests/test_miniapp_align.py::PayloadInSyncTests` 是这条不变式的考题，现在通过）。
**插件发布前需要重跑 `miniapp/build.sh`**（载荷内容变了：前端三件 ＋ Python 引擎 ＋ 新增一个 `style-rules.toml`）。

---

## 7. 全仓测试

`BT`BT`BT`
$ python3 -m pytest tests/ -q
2094 passed, 397 subtests passed in 251.26s
`BT`BT`BT`

* 环境：Python 3.14.4 ／ pytest 9.0.3 ／ macOS 26.6.2 (darwin 25.6.0, arm64)
* 新增：`tests/test_miniapp_p0.py`（33 例，五条 P0 各一组）；`tests/test_workbench_i18n.py` ＋1 例（重名键契约）
* 改动前基线：`2092 passed / 2 failed`——两条失败是 `PayloadInSyncTests`（载荷同步不变式），
  原因是前端改了还没跑 `miniapp/build.sh`；跑完 build 后转绿。

---

## 8. 实跑台账（可复现）

**台架**：两个真实工作台实例，同一批真实论文的**两份临时拷贝**，**绝不写真目录**。

`BT`BT`BT`
# 基线（上一轮的四项修复）
python3 -m factscribe workbench --root /tmp/fs-p0-live/before --port 8891 \\
        --json --no-browser --state-dir /tmp/fs-p0-live/state-before
# 本轮
python3 -m factscribe workbench --root /tmp/fs-p0-live/after  --port 8892 \\
        --json --no-browser --state-dir /tmp/fs-p0-live/state-after
`BT`BT`BT`

沙箱内容：`paper`／`paper-zh`／`paper-b`／`paper-b-zh`（真实论文的 `cp -Rp` 拷贝，保 mtime——
不保 mtime 的话 PDF 会变成「过期」，读数就不可比了）。

**真实论文目录未被本轮改动**（校验：`paper-b/factscribe.toml` 的 md5 全程为
`55da1e82a58e310bc23257f18210b33f`；`[workbench]` 表里**没有** `last_disk`，说明本轮没写它）。
（该目录里 14:09／14:13 的 `last_opened` 与 `.bak` 是**上一轮审计会话**留下的，本轮之前。）

**MCP 面**：`/tmp/fs-p0/mcp_p0_2.mjs` 真起薄壳（`mod.start()`），POST `/mcp/factscribe` 的 JSON-RPC
`tools/call`，调 `fs_read_section` 拿段 id、调 `fs_propose_edit` 建单。

**截图清单**（`docs/miniapp-p0-shots/`）：

| 文件 | 内容 |
|---|---|
| `before-report-zh.png` | 基线 · 中文 · 检查报告（3 张卡，0 发现说错话，四步链中文） |
| `before-report-en.png` | 基线 · 英文 · 检查报告（四步链标签是中文） |
| `after-report-zh.png` | 本轮 · 中文 · 检查报告（5 张卡，0 发现说对话） |
| `after-report-en.png` | 本轮 · 英文 · 检查报告（四步链全英文） |
| `after-report-gates-zh.png` | 本轮 · 文风闸与双语对账两张新卡（中文） |
| `after-report-gates-en.png` | 本轮 · 文风闸与双语对账两张新卡（英文） |
| `after-report-style-yellow.png` | 本轮 · 文风闸真的有黄牌命中（SECTION_OVERLAP） |
| `before-lastdisk-zh-disk.png` / `before-lastdisk-reopen.png` | 基线 · 切到中文盘后回列表再打开 → **落回英文盘** |
| `after-lastdisk-zh-disk.png` / `after-lastdisk-reopen.png` | 本轮 · 同一路径 → **落回中文盘** |

---

## 9. 仍未解决 / 有争议的点

1. **发现的 message 仍是后端中文**。P0-4 只管四步链标签与说明；「发现」清单里每条 finding 的 `message`
   来自 audit／style 闸的后端中文串，EN 界面里仍是中文（截图 `after-report-en.png` 里
   `PDF_STALE` 那条是中文）。**要彻底解决得给 finding 加 i18n key 或错误码表**，是一条独立的活，
   本轮没做——超出 P0-4 的范围，且牵动 audit／style／mirror 三个模块的 message 生成。
2. **MCP 工具面没有 `fs_get_style`／`fs_mirror_check`**（审计 P1 的 R11）。助手拿到的上下文里
   仍只有体检摘要与四步链，看不到文风与双语对账。本轮只做了「并进检查报告」这半边。
3. **`textreuse` 与 `tide` 仍无入口**。审计 §2 维度 5 把这两条与 style／mirror 并列为「miniapp 零入口」，
   但 P0-1 的正文只点了 style 与 mirror-check。理由：`textreuse` 要**两个目录**才有意义
   （中英两盘互查＝查字面重合），语义上成立但**噪声不可控**（翻译本就会重用专名）；
   `tide` 是**改前／改后**的改动账，单盘报告里没有「改前」这个参照物
   （要快照才有），属**差分类**闸而非**单盘读数**闸。两条都没并进来。
   若要并，`textreuse` 建议做成**独立折叠卡**（不并进发现清单），`tide` 需要先定快照语义。
4. **报告接口多花 0.3–0.5 秒**（style + mirror 各跑一遍）。可接受，但盘更大时会线性变慢；
   必要时加短 TTL 缓存。
5. **四步链仍保留后端中文 `label`／`detail`**（为不破 MCP 对外形状）。代价是后端仍有一份中文文案，
   将来若要「后端彻底无中文」，得走一次 MCP schema 变更（要用户点头）。
6. **`last_disk` 的落点是「被打开的那个盘自己的配置」**，而不是「项目级的单一记录」。
   好处是每个盘自洽、不依赖跨盘写权限；代价是**读的时候要扫同项目所有盘**才能算出项目级当前盘
   （`aggregate()` 已经在扫了，成本可忽略）。项目卡上**没有**加「当前盘」标记——
   批准设计条目⑬ 明确「项目卡只留打开＋编辑」，加标记会与它冲突。
7. **顺带发现（不在本轮五条里，未改）**：`factscribe/workbench/projects.py:700` 的切段条件
   `source[index:index + 2] == "\n"` **恒为假**（拿 2 字符的切片比 1 字符的串），
   于是「空行分段」这条逻辑**从来没生效过**——每个章节文件里，两个标题之间的整段正文是**一个块**。
   这解释了为什么 `paper-b` 的 01_intro 只有一个正文块（5939 字符）。
   这是既有实现的长期潜伏缺陷，不是本轮引入；**改它会改变块边界（＝写回粒度）**，
   属于契约级变更，**本轮没动**，留待单独立项。
8. **样式/规则文件被 vendoring 进载荷**：`miniapp/build.sh` 多了一步。这让插件载荷多一个文件
   （当前载荷 107 个文件／4.5 MiB，离 1024／64 MiB 上限很远）。若发布流程有别的打包脚本，要同步这一处。
