# 法律侧工作台第 ② 步：FR 判例样板页与待批提案通道

> 本件是**规范**（第 ② 步的形状与口径）。第 ① 步的只读接口层见
> `docs/design/SPEC-LEGAL-API.md`（本件的底座）。
> 实现在 `integrations/factscribe-legal/factscribe_legal/{api,views,proposals}.py`
> 与 `factscribe/serve.py`；页面在 `integrations/factscribe-legal/web/`。

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

## 1. 前端落点：为什么在 `integrations/factscribe-legal/web/`

**结论**：法律侧页面放在**法律集成件自己的前端目录**
`integrations/factscribe-legal/web/`（index.html ＋ legal.css ＋ legal.js），
由 core `factscribe serve --ui` 在 `GET /legal`（静态件在 `GET /legal/<file>`）
提供。**不挂 `factscribe/web/`**（节级前端，按已定口径第 ④ 步要废弃；
挂那儿第 ④ 步还得再搬一次），**也不挂 `factscribe/workbench/static/`**。

理由（逐条）：

1. **不在将被废弃的 `factscribe/web/`**：第 ④ 步要废弃的是节级前端；
   法律侧页面若寄住在那里，第 ④ 步要连带搬一次——白搬。
2. **不在段落级前端 `factscribe/workbench/static/`**：那一支（引擎统一
   第②步）**还没并进 main**，而且并进方向（走 C：miniapp 与本仓同一套引擎）
   **尚未拍板**；挂过去的后果是「本步的页面在本步不可运行」（这工作树里
   没有 `factscribe/workbench/` 这个包，页面也没有 serve 面），且合并方向
   一变就要再搬一次。
3. **法律域的事归法律集成件**：语料、收据、时效、码表、域级锁全在
   `integrations/factscribe-legal` 里；页面与它的通道同源同仓，第 ③ 步
   扩线时页面直接复用，不用跨仓找数据。
4. **将来要迁到段落级前端也可以**：迁的代价是「移动目录 ＋ 改一条 serve
   路由」（`factscribe/serve.py` 的 `_legal_ui`），页面本身不用动。

落点被拒的代价记一笔：如果第 ③ 步决定把法律侧并进段落级工作台，这一步
的工作**不浪费**——通道、契约、测试都留在集成件里，页面换个目录即可。

## 2. 页面结构：区域 ↔ 数据 ↔ 接口

| 区域 | 用的是**真实读数**（从哪来） | 标「待接接口／示意」的部分 |
|---|---|---|
| 顶栏 | 只读档徽章、令牌（`?token=` 或手粘，**只放内存**） | 「重新核验」按钮**禁用**：没有 POST verify；说明写「核验在命令行跑 `python3 -m factscribe_legal api findings`」 |
| 域级锁状态条 | 四键 corpus／date／index_sha256／view ＋ frozen ＋ matches（`GET /api/legal/summary` → `contract.summary.lock`） | 论文侧冻结锁（`GET /api/evidence`）取不到就写「未取到」；**法律锁蓝实心边条、论文锁灰虚线边条**（视觉区分） |
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
| GET | `/legal`、`/legal/<file>` | 第 ② 步：页面静态件 |
| — | `POST /api/legal/verify`、`/api/legal/facts`、`/api/legal/ledger/dup-ok` | **仍未挂**（404） |

## 6. 测试与闸门

* 新增 `integrations/factscribe-legal/tests/test_workbench.py`（20 例）：
  七条线页面数据出口、五元组缺省、时效 11 键四域归一、语料过滤（件必须
  真实在盘）、码表完整、四条读侧视图、提议存储 ＋ 指纹闸（真口径：改事实账
  的钉版哈希 ⇒ 指纹变 ⇒ 采纳被拒）、既有 11 条 CLI 快照对表。
* 新增 `integrations/factscribe-legal/tests/_cli_snapshot.py` ＋
  `cli_baseline.json`：**既有 11 条命令的 --help／stdout／退出码快照**，
  只从第 ① 步基线树（23acded）生成过一次。
* 新增 `tests/test_serve_legal_workbench.py`（13 例）：HTTP 层的四条读侧
  视图、提案建单／采纳／指纹不符 409、写路径仍 404、页面静态件。
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
