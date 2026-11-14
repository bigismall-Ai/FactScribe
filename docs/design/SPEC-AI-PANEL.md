# SPEC-AI-PANEL：MiniFactScribe 的 AI 起草面板

日期：2026-11-13　　状态：v1（单节候选，人工采纳）

MiniFactScribe 的「AI 起草」页签用 mcode 宿主 agent/模型，不接模型 SDK。
输出只进候选区；人采纳后才写工作台项目，并重跑 Python 闸门。

## 1. 前提

- `miniapp/miniapp.json` 声明 `"agentAccess": ["session.run"]`；
- 本地 `factscribe serve` 已连接并载入项目；
- **从论文项目的对话里打开 MiniFactScribe**：页面发起的 session 才绑定当前项目目录；
  Node 发起的 session 用 Mini App 自己的目录。
- 页面通过 `window.mcode.miniapp.host.navigation.getState()` 判断打开位置：
  `view === "conversation"` 才允许 AI；否则显示提示条并禁用 AI（fail-closed）。
  读位置需要清单声明 `hostAccess: ["navigation.read"]`，不读对话内容。
- 页面用 `agent.session()`（不带 id）读当前对话的 `workspaceDir` 与 `isDefaultWorkspace`，
  显示在「工作台」；没有项目文件夹时提示。`session.read` 只用于当前对话，不列其他对话。

## 2. 流程

```
选节 → 拼提示（要求 + 当前节 + 事实账）
     → window.mcode.miniapp.agent.run({ text, requestId }, { onEvent })
     → text.delta 流进候选区
     → 遇到 permission.requested：页面出「允许一次 / 拒绝」，不自动批
     → run 结束，候选区可编辑（只读 textarea）
     → 「采纳并写入本节」→ PUT /api/workbench/sections
     → 自动重跑 /api/workbench/audit
```

- 提示里写死：只能使用账里已有的数字，不得编造；输出完整替换本节的 LaTeX；
- 问卷（`question.requested`）这一版不处理，只提示到聊天侧面板回答；
- 停止按钮调 `agent.cancel(requestId)`。

## 3. 事件

| 事件 | 页面行为 |
|---|---|
| `text.delta` | 追加候选正文 |
| `message.committed` | 用完整消息覆盖候选正文 |
| `tool.started/finished` | 显示工具卡 |
| `permission.requested` | 审批卡；`agent.reply({sessionId, requestId, decision})` |
| `question.requested` | 提示到聊天侧面板回答 |
| `turn.finished` | 结束 streaming 状态 |

打开位置不是 `conversation`（或无法确认）时：顶部提示条说明原因，AI 起草禁用；
工作台的手工读写不受影响。

## 4. 边界

- 不是自动写作：人必须点「采纳」；不采纳就什么都不写；
- 不是第二套判据：采纳后仍走 `factscribe audit`；
- 不改 `dataDir` 作为论文主档的定位；论文仍在工作区；
- 不自动批准工具调用；审批只给 `allowOnce` / `deny`。

## 5. 验收

`integrations/minifactscribe/tests/ui.test.mjs`：manifest 有 `agentAccess` 与
`hostAccess`、面板/按钮存在、页面调用 `agent.run`、处理 `text.delta` /
`permission.requested`、非对话位置 fail-closed、读取当前对话项目文件夹、
采纳后才写工作台。
真实 agent 行为需在 mcode 项目对话里手测。
