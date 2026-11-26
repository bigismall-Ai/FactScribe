# SPEC-MINIAPP-V2：提议单改稿（AI 提议 → 人确认才写回）

日期：2026-11-22　　状态：v2（本批实现）

## 0. 这一批要解决的三件事

1. **v1 的承诺要兑现**。`miniapp/README.md` 写着「v2 的写稿也走「提议单 → 人确认」」，
   但代码侧零实现：`factscribe/` 全仓搜 `proposal|提议单` 只有英文散文命中。
2. **有个真漏洞**。`write.py:915 insert_ai_draft` **不比对块指纹**（`/draft/insert` 绕开
   整条保护链），页面 AI 面板的「写进稿」按钮是**无确认直写稿**。
3. **差异卡不存在**。前端零 diff UI（`index.html` 无 diff 元素，`app.js` 搜 `diff` 只有英文散文）。

## 1. 模型：提议单是状态，不是论文

- 一个提议单＝一条**待人确认**的改稿意图。
- 落盘在**状态目录**，不在论文目录里：论文目录不因为「有人提了个建议」而变脏。
- 状态目录解析顺序：`--state-dir` 参数 → `$FACTSCRIBE_STATE_DIR` → `~/.factscribe/state`。
  Mini App 由薄壳显式传宿主分配的 dataDir；浏览器模式落在工具自己的家目录。
- 文件：`<state>/proposals/<id>.json`，id 形如 `prop-20261122-103355-a1b2`。
- 记录字段：`version,id,kind,project,disk,file,block,before_sha,before_text,proposed_text,
  after_text,warnings,source,rationale,created_at,status`。
- `kind`：`block_edit`（替换一段）／`ai_draft`（在锚段后插入草稿块）。
- `status`：`pending` → `applied` / `rejected` / `stale`。

## 2. 落盘只有一条路（复用既有保护链，不另写）

**提议阶段（只算不写）**：`find_block` → `_check_expect_sha` → `scan` → `_rebuild` →
`_balanced_ok`。算出的 `after_text` 就是**真正会落盘的那一份**，差异卡展示它 → 所见即落盘。

**确认阶段（真写）**：`block_edit` 走 `save_block(..., expect_sha=before_sha)`；
`ai_draft` 走 `insert_ai_draft(..., expect_sha=锚段指纹)`。

两阶段各过一次指纹闸：从助手给稿到人点确认之间，正文若被别处改过 → `BLOCK_STALE`（409），
**不覆盖**。落盘仍是 `atomic_write`（`.tmp`→`fsync`→`rename`）＋ `.bak`，
路径闸照旧：只写 `sections/**.tex` 与根 `main.tex`；`facts/` `audit/` `results/` `runs/` 只读。

## 3. 接口（`/api/disk/<project>/<disk>/…`）

| 方法 | 路径 | 请求 | 返回 |
|---|---|---|---|
| POST | `.../proposal` | `{kind?,file,block,text,source?,rationale?}` | `{ok,proposal}`（**不碰正文**） |
| GET | `.../proposal` | — | `{ok,count,proposals[]}`（默认只列 pending） |
| GET | `.../proposal/<id>` | — | `{ok,proposal}` |
| POST | `.../proposal/<id>/confirm` | — | `{ok,applied,warnings,html,blocks}`（落盘） |
| POST | `.../proposal/<id>/reject` | — | `{ok,proposal}`（丢弃，不写正文） |

错误码：`PROPOSAL_NOT_FOUND`(404)、`PROPOSAL_ALREADY_RESOLVED`(409)、
`PROPOSAL_TEXT_EMPTY`(400)、`PROPOSAL_ID_INVALID`(400)、`BLOCK_STALE`(409，沿用)。

## 4. MCP 工具面（薄壳 +2 个；仍不给直写工具）

- `fs_propose_edit` `{project,disk,block|file,text,rationale?}` → 建单，返回 id/摘要/警告。
- `fs_list_proposals` `{project,disk?}` → 列待确认提议。
- **采纳只能由人在页面点**：工具面没有 apply，助手拿不到「直接改正文」的接口。

## 5. 页面

- 左栏头部出现「待确认 N」徽标（有待确认提议时）→ 打开差异卡模态。
- 每条提议一张卡：左＝现状，右＝采纳后（逐行标增删），底部「采纳写回」「拒绝」。
- 采纳后：toast ＋ 应用新鲜 blocks ＋ 自动重跑检查报告（`/report/rerun`）。
- AI 面板「写进稿」改道：建 `ai_draft` 提议单，不再直写稿；直写路径保留但 UI 不再调用。
- 提议已过期（正文被改过）→ 卡上显示「这段在别处已被改动」，不提供采纳。
- **中/EN 界面语言开关常显**：它独立于工作台专属工具组（`.lh-lang`），项目管理页、
  新建页、工作台页都在；首启设置页也有一枚（zh/en 两套文案，不落浏览器存储）。

## 6. 边界

- 提议单不是事实账：写不进 `facts/`，也不改 `audit/`。
- 提议单不进论文目录：不污染 git。
- 助手仍然没有直接写正文的接口。
- 过期即拒写，不静默覆盖。

## 7. 验收

- `tests/test_workbench_proposal.py`（unittest）：建单不改正文（字节级）、提议单落在状态目录、
  指纹不符 → BLOCK_STALE、确认后按保护链落盘且留 .bak、拒绝后文件不变、
  提议后正文被改 → 确认时 409、新写的 `\fact{}` 被剥并告警、ai_draft 确认后落草稿块。
- 前端契约断言（沿用 `tests/test_workbench_layout.py` 的字符串钉法）。
- 仓外 harness 扩展：提议 → 差异卡 → 采纳 → 正文真变。
- 宿主实测：助手建提议 → 页面见差异卡 → 人采纳 → 审计重跑。
