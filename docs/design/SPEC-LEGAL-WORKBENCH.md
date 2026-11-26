# 法律侧工作台第 ② 步：FR 判例样板页与待批提案通道

> 本件是**规范**（第 ② 步的形状与口径）。第 ① 步的只读接口层见
> `docs/design/SPEC-LEGAL-API.md`（本件的底座）。
> 实现在 `integrations/factscribe-legal/factscribe_legal/{api,views,proposals}.py`
> 与 `factscribe/serve.py`；页面在 `factscribe/workbench/static/legal/`（段落级前端
> 体系里的一个视图，见 §1）。

## 0. 这是什么 / 不是什么

**是**：法律侧工作台的**第一个真页面**——FR 判例样板页。三栏证据链工作台
（左栏语料＝依据，中栏该件＋逐条收据＝主张，右栏问题＋文书段落＝落点），
外加一条**待批提案**通道（只建单、不写盘）。

**不是**：

* 不是判定层。页面显示的红黄码、措辞、退出码语义**全部照抄各闸**
  （第 ① 步的通道已经这么做了，本步一字不改）。
* 不是写路径。**没有** POST verify／facts／ledger-dup-ok；「采纳写回」只
  登记意图，不写任何文件（法律闸本来就没有写路径）。
* 不是第 ③ 步。第 ③ 步（扩六条线、时效统一收口）可以**直接复用**本件的
  通道、收据与页面骨架（见 §9）。

## 1. 前端落点与视觉基准：段落级前端体系

**落点**：`factscribe/workbench/static/legal/`（index.html ＋ legal.css ＋ legal.js）
—**段落级工作台前端静态目录里的一个视图**，不是独立的另一套界面。
core `factscribe serve --ui` 在 `GET /legal` 提供它（静态件在 `GET /legal/<file>`）；
段落级线合并进 main 后，`factscribe/workbench/server.py` 的 `/static/` 路由
也会提供**同一份文件**（`/static/legal/index.html`）。

**视觉与交互的唯一基准＝段落级 miniapp 前端**（`factscribe/workbench/static/`
的 index.html / app.css / app.js，合计 8174 行）。本步的页面按它**逐项复用/对齐**：
色板与组件写法照抄 miniapp `app.css`（逐字节，注明出处行号），交互形态照抄
miniapp `app.js`（证据锁独立只读卡、事实芯片与卡片、提议差异卡、弹层与抽屉、
右栏宽度拖拽、中/EN 语言切换、last_disk 记忆……）。法律侧每个区域 ↔ miniapp 具体
交互的对照表见 §10。

**明确禁止的基准**：`factscribe/web/app.css`（仓库里旧的节级网页前端，5745 行、
蓝灰 `--mcode-*` 色板）——那不是用户认可的界面。**本步第一版误抄了它**
（已按新基准整体重做）；法律页也不许自己另造交互风格。

**落点的四条理由**：

1. **用户数周打磨的是段落级前端**：它是唯一被认可的交互基准，法律页与它同源
   同形态，将来合并才是「一个产品」，不是两个产品贴在一起。
2. **不在 `factscribe/web/`**：节级前端按已定口径第 ④ 步要废弃；挂那儿第 ④ 步
   还得再搬一次。
3. **不另起独立前端目录**：独立目录会与段落级体系分叉（两套色板、两套弹层、
   两套 i18n），合并时还要再搬一次。放在 `workbench/static/legal/` 子目录里，
   文件名与段落级本体的 index.html / app.css / app.js **不冲突**，合并时干净落地。
4. **本步可运行**：段落级线还没并进 main（合并方向也未定），但 core 的 serve
   路由已经能提供这份页面 ⇒ 本步就能跑、能验；等段落级线并进来，页面自动多一个
   `/static/legal/` 入口，两处指向同一份文件。

**静态件基准路径纪律**（第一版踩过的坑，已修）：页面用 `<base href=".">` ＋
**相对**引用 `legal.css` / `legal.js`（index.html:9、:195）。关键事实：

| 页面 URL | base URL | 相对资源解析成 | 需要服务器托管 |
|---|---|---|---|
| `/legal/`（有尾斜杠） | `/legal/` | `/legal/legal.css` | `GET /legal/<file>` |
| `/legal`（无尾斜杠） | `/` | `/legal.css` | `GET /legal.css`（根上再托管一份） |
| `/static/legal/`（段落级线并进来后） | `/static/legal/` | `/static/legal/legal.css` | 段落级 server 的 `/static/` 路由 |

第一版只托管了 `/legal/<file>`，页面挂在 `/legal`（无尾斜杠）时资源落到
`/legal.css` ⇒ 取不到 ⇒ 脚本从未执行 ⇒ **页面零渲染**（DOM 只有 971 字符）。
现在 core `factscribe serve` 在根上再托管一份 `/legal.css` / `/legal.js`
（serve.py 的 `/legal.` 分支），两个 URL 都拿得到样式与脚本。

## 2. 页面结构：区域 ↔ 数据 ↔ 接口

| 区域 | 用的是**真实读数**（从哪来） | 标「待接接口／示意」的部分 |
|---|---|---|
| 顶栏 | 只读档徽章、令牌（`?token=` 或手粘，**只放内存**） | 「重新核验」按钮**禁用**：没有 POST verify；说明写「核验在命令行跑 `python3 -m factscribe_legal api findings`」 |
| 域级锁状态条 | 四键 corpus／date／index_sha256／view ＋ frozen ＋ matches（`GET /api/legal/summary` → `contract.summary.lock`） | 论文侧冻结锁（`GET /api/evidence`）取不到就写「未取到」；**法律锁＝实线卡、论文锁＝同卡但左边虚线**（miniapp 原生虚线记法，不新增色） |
| KPI 行 | 红牌／黄牌（findings）、收据数（receipts.total）、件数（corpus.total） | 无（全真读数） |
| 左栏·语料库 | 件清单（`GET /api/legal/corpus`）＋过滤（国家／域／件型／时效状态）＋每件的时效状态（`timeliness.state_label`） | 件清单只列**真实可见**的件；FR 全量正文不在仓、IT 灌库 403、CN 案例 0 件 —— 界面不补件 |
| 中栏·件详情 | `GET /api/legal/corpus/{id}`：meta、时效 11 键、ambiguous 候选 | 同 id 多件时列候选让用户按 domain 选 |
| 中栏·逐条收据 | 五元组表（id｜sha16｜span｜face｜how），列头取契约 `fields`，缺省写「—」；点行展开 span/face/how 解释 ＋ fact 的 claim/value/定位 | 收据**按件**取（`corpus/{id}` 的 receipts）；取不到时退回按线分组（`/receipts`） |
| 右栏·问题区 | 问题清单（`GET /api/legal/findings`）＋判定码表（`GET /api/legal/codes`，中文短名取 `label`）；红黄两级；skipped 的线也列出并写明 note | 无 |
| 右栏·文书段落区 | 段落与 `\fact{ID}` 标记（`GET /api/legal/document`）；标记可点，展开官方逐字片段；点标记 ⇄ 点收据双向高亮 | 段落骨架来自项目 `sections`；没有标记的段落照实列，不补连接语 |
| 右栏·条→事实反查 | `GET /api/legal/provision/{num}/facts`：哪条事实引了这一条（收据＋件＋时效） | 条号由用户填（**页面不预置条款号**） |
| 右栏·待批提案 | 建单、列表、采纳（`GET/POST /api/legal/proposals`、`POST /api/legal/proposals/{id}/adopt`） | 「采纳写回」**不写盘**（见 §4） |
| 页脚·CLI 清单 | `GET /api/legal/cli`：12 条子命令（11 条既有 ＋ 第 ① 步的 api 族） | 无 |

**不许编造**：件数、条款号、码数、引文、日期一律不许写死在页面里；取不到
就写「未取到／待接接口」。

## 3. 第 ① 步没做的读侧视图（本步补齐的四条）

接口形状（返回体都是 `{version, view, ...}`，嵌在 core payload 的
`contract` 键下，与七路通道同一个信封）：

### 3.1 单件详情 `GET /api/legal/corpus/{id}?domain=`

```json
{"version": "...", "view": "corpus_item", "id": "L3121-27",
 "ambiguous": false,
 "candidates": [{"id": "", "domain": "", "path": "", "root": "", "title": "", "kind": ""}],
 "item": {"id": "", "country": "", "domain": "", "kind": "", "title": "",
          "path": "", "gate": "", "meta": {}, "timeliness": {}, "root": ""},
 "receipts": {"fields": ["id","sha16","span","face","how"],
              "missing_marker": "—", "total": 1,
              "items": [{"id": "", "sha16": "", "span": "", "face": "", "how": "",
                         "fact": {"id": "", "claim": "", "value": null,
                                  "source": "", "location": "", "file": ""}}],
              "line": "fr", "gate": "verify", "note": ""},
 "note": ""}
```

件与收据的关联口径：**同域 ＋ 键相交**（键＝法条号／案号／卡名／文件名），
见 `factscribe_legal/views.py` 的 `fact_keys`／`item_keys`。

### 3.2 文书分段 `GET /api/legal/document`

```json
{"version": "...", "view": "document", "total": 2,
 "sections": ["sections/01_one.tex"],
 "paragraphs": [{"index": 0, "file": "sections/01_one.tex", "text": "...",
   "markers": [{"fact_id": "FR-HOURS", "value": "35", "claim": "...",
                "source": "...", "location": "facts/one.toml:FR-HOURS",
                "receipt": {"id": "", "sha16": "", "span": "", "face": "", "how": ""},
                "official": {"text": "", "span": "", "face": "", "source": ""}}]}],
 "note": "..."}
```

段来自项目 `factscribe.toml` 的 `sections`；标记是正文里的 `\fact{ID}`；
`official.text` 是**与该条收据 span 同源**的那份官方正文按区间切出来的
逐字片段（不是另找的一份）。

### 3.3 条→事实反查 `GET /api/legal/provision/{num}/facts`

```json
{"version": "...", "view": "provision_facts", "num": "L3121-27", "total": 1,
 "items": [{"fact_id": "", "claim": "", "value": null, "source": "",
            "location": "facts/one.toml:FR-HOURS",
            "receipt": {"id": "", "sha16": "", "span": "", "face": "", "how": ""},
            "corpus_item": {"id": "", "title": "", "path": "", "domain": ""},
            "timeliness": {}}],
 "note": ""}
```

### 3.4 CLI 清单 `GET /api/legal/cli`

```json
{"version": "...", "view": "cli", "total": 12,
 "items": [{"name": "verify-fr-case", "group": "核验入口（闸）",
            "help": "...", "args": [{"name": "--project", "required": true, "help": "..."}]}],
 "note": "..."}
```

清单**从 argparse 现取**（`cli.build_parser()`），不另抄一份——命令面漂移
会当场被抓（既有 11 条命令另有快照对表，见 §6）。

## 4. 待批提案通道：行为定义

**只建单、不写盘。** 提议单存在**服务进程内存**里（`proposals.py` 的模块级
存储 ＋ 线程锁）：

* 服务重启 ⇒ 在途提议单全失（这是「不写盘」的必然结果）；
* 项目目录、语料、锁件**一个字节都不动**；
* 命令行另起进程时读到的是**本进程**的存储（通常为空）——通道的 note 里
  说明白，不假装有单。

### 4.1 单子的形状

```json
{"id": "P-0001", "kind": "receipt_quote",
 "target": {"scope": "receipt", "fact_id": "F-...", "item_id": "..."},
 "before_sha": "d606875ac0cec22d", "after_sha": "",
 "payload": {}, "status": "proposed",
 "decision": {"action": "none", "write_path": false, "reason": "..."},
 "fingerprint": {"source": "...", "current": "...", "matches": true}}
```

* `kind`：`receipt_quote`／`corpus_item`／`fact_claim`（闭集）。
* `status`：`proposed`／`adopted_pending`／`rejected`（闭集）。
* `decision.write_path` **恒为 false**（没有写路径）。

### 4.2 指纹闸（拒写）

指纹＝目标**当时**的哈希前 16 位：

| scope | 指纹来源 |
|---|---|
| `receipt` | 该条收据的 `sha16`（事实账钉的来源哈希前 16 位） |
| `item` | 语料件 meta 上钉的官方哈希前 16 位（txt/xml/detail/article/card） |
| `fact` | 事实账 `source_sha256` 前 16 位 |

* **建单时**：客户端若自带 `before_sha`，必须与现算一致，否则**拒建**
  （409 `PROPOSAL_STALE`）——目标已被改过 ⇒ 这张单从一开始就不该存在。
* **采纳时**：现算指纹与单上的 `before_sha` 比；对不上 ⇒ **拒写**
  （409 `PROPOSAL_STALE`，单子转 `rejected` 并记下原因）；对得上 ⇒
  单子转 `adopted_pending`，**只登记意图，不写任何文件**。

### 4.3 「采纳写回」按钮当前的行为（页面上的实话）

按钮点下去会调 `POST /api/legal/proposals/{id}/adopt`：

* 指纹对得上 ⇒ 单子状态变 `adopted_pending`，页面显示
  「已登记采纳意图（未写盘：法律闸无写路径，等第 ③ 步真写路径）」；
* 指纹对不上 ⇒ 后端回 409，页面**如实显示后端原文**（PROPOSAL_STALE）。

**它不写任何文件**：没有 POST facts，没有 POST ledger/dup-ok，没有真写路径。
页面不出现「采纳并写回事实账」这类按钮。

## 5. 路由总表（core `factscribe serve`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/legal/findings` etc.（七路） | 第 ① 步既有 |
| GET | `/api/legal/corpus/{id}` | 第 ② 步补 |
| GET | `/api/legal/document` | 第 ② 步补 |
| GET | `/api/legal/provision/{num}/facts` | 第 ② 步补 |
| GET | `/api/legal/cli` | 第 ② 步补 |
| GET | `/api/legal/proposals` | 第 ② 步：现在返回在途提议单 |
| POST | `/api/legal/proposals` | 第 ② 步：建单（**不写盘**） |
| POST | `/api/legal/proposals/{id}/adopt` | 第 ② 步：采纳（**不写盘**；指纹不过 → 409） |
| GET | `/legal`、`/legal/` | 第 ② 步：页面静态件（同一份文件） |
| GET | `/legal/<file>` | 第 ② 步：页面引用的静态件（`/legal/legal.css`） |
| GET | `/legal.css`、`/legal.js` | 第 ② 步：**根上再托管一份**——`/legal` 无尾斜杠时相对资源解析到这里（见 §1） |
| — | `POST /api/legal/verify`、`/api/legal/facts`、`/api/legal/ledger/dup-ok` | **仍未挂**（404） |

## 6. 测试与闸门

* 新增 `integrations/factscribe-legal/tests/test_workbench.py`（20 例）：
  七条线页面数据出口、五元组缺省、时效 11 键四域归一、语料过滤（件必须
  真实在盘）、码表完整、四条读侧视图、提议存储 ＋ 指纹闸（真口径：改事实账
  的钉版哈希 ⇒ 指纹变 ⇒ 采纳被拒）、既有 11 条 CLI 快照对表。
* 新增 `integrations/factscribe-legal/tests/_cli_snapshot.py` ＋
  `cli_baseline.json`：**既有 11 条命令的 --help／stdout／退出码快照**，
  只从第 ① 步基线树（23acded）生成过一次。--help 做**空白归一**，钉命令面
  （参数、顺序、说明）不钉排版；边界：argparse 在 **3.10 改了段名**
  （`optional arguments:` → `options:`），所以这份快照跨 **3.10–3.14** 成立，
  **3.9 不在支持矩阵内**（CI/preflight 只跑 3.10–3.14）。
* 新增 `tests/test_serve_legal_workbench.py`（16 例）：HTTP 层的四条读侧
  视图、提案建单／采纳／指纹不符 409、写路径仍 404、页面静态件；其中三例是
  **第一版那个阻断缺陷的回归锁**：`/legal` 与 `/legal/` 都出页面且都带
  `<base href=".">`、根上与目录下两处静态件都在、色板不许回退 `--mcode-*`。
* 真后端验收（本地实跑）：无头 Chrome 渲染 `/legal` 与 `/legal/`，两者 DOM
  **逐字节一致**；读数——语料 27 件、KPI（0 红／0 黄／2 收据／27 件）、收据
  五元组 `FR-HOURS｜d606875ac0cec22d｜66-68｜body｜numnorm`、码表 70 行、
  点收据行展开成功、建单 `P-0001` → 采纳 `adopted_pending`（write_path=false）、
  中/EN 切换生效、右栏拖拽 392px→300px 并落 localStorage、零 JS 错误。
  红/黄两级卡片用**注入的合成 findings**（仅测试台，非仓库读数）验过：红卡底
  `#fbeee7`、黄卡底 `#fdf7ea`；仓库里 27 盘的 findings 全为 0，真实盘触发不了。
* 闸门：Python 3.10–3.14 全矩阵、legal 套件、node 套件、金样例逐字节、
  27 盘 audit --json 逐盘 cmp、preflight、check-readme。

## 7. 数据纪律（不变）

* 零编造：件数、条款号、码数、引文一律来自接口；取不到写「—」或「未取到」。
* 零写盘：页面与接口层都不写真实文件（提议单只在内存）。
* 不改判定语义：码名、措辞、严重度、退出码语义全照抄各闸。
* 不动金样例基线：本步不进 audit 路径，27 盘逐盘逐字节不变。

## 8. 本步未做的事（如实列明）

* **没有真写路径**：提议单只建单不写盘；采纳只登记意图（第 ③ 步才有真写回）。
* **没有自由文本搜索**：论文侧本来也没有，本步保持一致。
* **没有批量操作**：论文侧同样没有。
* **没有 DOM 锚点**：收据行 ⇄ 段落标记的联动是「选中即高亮」，不是真跳源码行
  （与第 ① 步记下的 G15 同一个坑）。
* **FR 全量正文不在仓、IT 灌库 403、CN 案例 0 件**：界面再���，没料就是没料。

## 9. 第 ③ 步（扩六条线、时效统一收口）可以直接复用什么

* **七路通道的形状**（findings/receipts/corpus/codes/timeliness/summary/
  proposals）——扩线时只加适配点，不改形状。
* **收据五元组的共用生产逻辑**（`receipts.py`）——六条线照同一套接。
* **时效的 11 键统一形状**（`timeliness.py`）——第 ③ 步做「统一收口」时，
  形状已经是跨域同构的，收口只改判定侧。
* **本步补的四条读侧视图**——第 ③ 步扩到六条线后，页面不用重写：
  件清单、收据、问题、段落、反查都按域取数，换域即可。
* **提议单与指纹闸**——第 ③ 步接真写路径时，闸门逻辑直接复用：
  建单 ＋ 指纹比对 ＋ 拒写，只是把「登记意图」换成「真写」。
* **域级锁四键与 canonical 形态**（`lock.py`）——锁面不用重做。
* **CLI 清单出口**——第 ③ 步加命令时清单自动跟着 argparse 走。

## 10. 法律页 ↔ 段落级 miniapp 前端：逐项对照

左列＝本单落点（`factscribe/workbench/static/legal/`），右列＝**段落级前端本体**
（`.worktrees/miniapp-host/factscribe/workbench/static/` 的 index.html / app.css / app.js）。
所有色值与组件写法照抄 miniapp，legal.css:16-42 的每个变量都注明了出处行号。

| 法律页区域 | 本单落点（file:line） | miniapp 基准（file:line） |
|---|---|---|
| 三栏骨架 | legal.css:160 `.layout`／:189 `.main`／:201 `.col-right` | app.css:255 `.shell`／:259 `.doc`／:289 `.colright` |
| 左栏语料栏 | legal.css:163-188（`.sidebar`） | app.css:257-260 `.rail`（268px 宽、`#faf9f4`） |
| 顶栏工具条 | index.html:12-36、legal.css:66-96 | app.css:444-454（`.tb-brand`/`.tb-btn`/`.lang-seg`）、index.html:13,16 |
| 中/EN 语言切换 | index.html:25、legal.js:1220-1334（`applyLang`/`initLang`） | app.js:4064、5379-5385、index.html:24-30 |
| 域级证据锁状态条 | index.html:41-66、legal.js:284-360、legal.css:98-159 | app.js:1875-1882（证据锁独立只读卡）、app.css:292（`.rcard`） |
| KPI 行 | legal.js:663-684、legal.css:170-176 | app.css:305-310（`.recon` 药丸）、app.css:14-18（`.st`） |
| 左栏·语料清单 | legal.js:395-476、legal.css:165-188 | app.css:266-269（`.pm-proj`／`.pmbtn.on` 反色记法） |
| 中栏·件详情 | legal.js:477-562、legal.css:236-250 | app.css:134-136（`.ycard` 的两列栅格） |
| 中栏·逐条收据（五元组） | legal.js:563-662、legal.css:251-259、legal.css:127-131 | app.css:127-131（`table.mt`）、app.css:132-137（`.ycard` 展开卡） |
| 右栏·问题区（红黄两级） | legal.js:685-739、legal.css:392-419 | app.css:74-75（`.note.ref`/`.note.cost`）、app.css:301-303（`.st.ok`/`.st.warn`）、app.css:322（坏字色 `#9a3b1e`） |
| 右栏·文书段落区 | legal.js:787-862、legal.css:264-276 | app.js:1079（段落块渲染）、app.css:57-59（`.cite`） |
| 右栏·待批提案（建单／差异卡／采纳） | legal.js:911-990（渲染）、:1021-1077（建单/采纳）、legal.css:318-326 | app.js:4908-5268（提议差异卡）、app.css:1521-1523（`.proposal-card`） |
| 右栏宽度可拖 | index.html:170、legal.js:1329-1360、legal.css:206-211 | app.js:5757-5827、app.css:1568-1575、index.html:174 |
| 弹层／抽屉／toast（样式已抄，本页暂无弹层需求） | legal.css:366-382 | app.css:113-121（backdrop/drawer）、app.css:149-152（toast） |
| 颜色与组件写法 | legal.css:16-42（`:root`，逐条注出处行号） | app.css:4,9-19,116,292,301-303,322 |

**本单新增（miniapp 无对应物，因为法律侧的数据形状不同）**：

* 条→事实反查面板（`GET /api/legal/provision/{num}/facts`）——miniapp 没有「按条
  查事实」这回事（它的事实是段落内的芯片）。
* CLI 清单面板（`GET /api/legal/cli`）——miniapp 是 GUI，没有 CLI 清单页。
* 域级锁四键状态条——miniapp 的证据锁卡是**论文侧那把**；法律侧这把是
  corpus/date/index_sha256/view 四键闭集，形状不同。
* 收据五元组表——miniapp 是事实芯片（单值）；法律侧一条收据是
  id｜sha16｜span｜face｜how 五元组，只能列表格。

**本单不适用（明确不做假动作）**：正文即编辑、AI 改写、模型选择、保护面插入
事实、保存链路四层探针、候选区写盘（法律闸无写路径）。

**本单不适用（基准里根本没有）**：深色模式。miniapp app.css 只有一套纸面色板
（全文无 `prefers-color-scheme`），所以第一版的「深色」开关已撤掉——不自造暗色。

**部分适用**：中/EN 只切**静态外壳**（34 键，legal.js:1221-1298）；接口返回的
文案（码的中文短名、后端注记、错误原文）保持后端原样——替后端翻译会掩盖口径。
