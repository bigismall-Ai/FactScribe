# SPEC-SERVE：本地工作台 HTTP API

日期：2026-11-13　　状态：v1（只读首版）

`factscribe serve` 把已有的 config / facts / brief / audit 暴露成本机 HTTP，
让 Mini FactScribe、本地页面或外部 agent 读结构化结果，不再解析 CLI 文本。

它不是新引擎，也不是新判据：所有判定仍由现有 Python 代码给出。

## 1. 命令

```bash
factscribe serve <项目> [--host 127.0.0.1] [--port 0] [--token TOKEN] [--json]
```

- `--host` 只接受 `127.0.0.1` / `localhost`；其他地址 exit 2。
- `--port 0` 让系统分配；启动行打印实际端口。
- 不给 `--token` 时生成 24 字节随机 token（每次启动都变）。
- `--json` 只让**启动行**出 JSON；服务仍阻塞，`Ctrl+C` 停止。

启动行：

```json
{"event":"listening","ok":true,"url":"http://127.0.0.1:54321",
 "token":"…","project":"/abs/path","api":["/api/health","/api/capabilities",
 "/api/status","/api/brief","/api/audit"]}
```

## 2. 安全边界

- 只绑回环，不做远程服务；
- 除 `/api/health` 外都要 token：`Authorization: Bearer <token>`、
  `X-FactScribe-Token: <token>` 或 `?token=`（仅本地调试；日志可能记录 URL）；
- 不写项目文件；serve 只读，audit 不落盘；
- 不做 CORS；推荐由 Mini FactScribe 的 Node 服务做同机代理，避免浏览器跨源。

## 3. 接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 无鉴权存活检查：`{ok,tool,version,service}` |
| GET | `/api/capabilities` | `engine:"python"`、`files:true`、`workbench:true`、项目名与根路径 |
| GET | `/api/status` | 事实数、节数、配置形态与告警；不跑审计 |
| GET | `/api/brief[?section=PREFIX]` | 写作简报；载荷与 `brief --json` 同源 |
| POST | `/api/audit` | 全量审计；载荷与 `audit --json` 同源 |

成功响应统一带：

```json
{"schema_version":"1.0","tool":"factscribe","version":"…",
 "command":"serve","status":"ok|red|yellow","severity":"…","exit":0,
 "endpoint":"…","ok":true,...}
```

- **audit 的 HTTP 状态恒为 200**：红黄是判定结果，写在 `exit` 与
  `findings` 里，不是传输失败。
- 顶层 `ok` 只表示**请求执行了**；闸门结论看 `status` / `exit` / `findings`。
  不要拿 `ok:true` 当绿。
- 错误响应：

```json
{"ok":false,"error":{"code":"CONFIG_INVALID","message":"…"}}
```

HTTP 400 = 配置/项目错；401 = token 缺失或不符；404 = 未知接口；
500 = 未预期异常。

## 4. 非目标

- 不提供写接口（`write_section`、`add_fact` 等在后续批次）；
- 不做 UI；UI 由 Mini FactScribe / 本地页面负责；
- 不代理模型调用；agent 走 CLI / MCP / 宿主 `context.agent`；
- 不改退出码与错误码语义。

## 5. 验收

`tests/test_serve.py`（9 例）：health 免鉴权、401、status/brief/audit 形状、
红判定的 HTTP 200、未知接口 404、坏项目/非回环拒绝、只读不写项目。
