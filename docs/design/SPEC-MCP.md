# SPEC-MCP：把本地工作台挂成 MCP stdio 服务器

日期：2026-11-13　　状态：v1（读 + 受限写）

`factscribe mcp <项目>` 用 MCP stdio 协议，把 `serve` 同一套 workbench 数据层
（status / project / brief / audit，可选写章节/追加事实）暴露给 agent。
不新增判据；所有结果仍由 Python 原函数给出。

## 1. 命令

```bash
factscribe mcp <项目> [--allow-write]
```

- 由客户端作为子进程启动；stdio 上只走 JSON-RPC，诊断走 stderr；
- 默认只读；`--allow-write` 才在 `tools/list` 里出现写工具；
- 项目路径在启动时固定；越界路径不会因为 agent 的参数而改变。

客户端（概念示例，字段名按各客户端为准）：

```json
{
  "mcpServers": {
    "factscribe": {
      "command": "python3",
      "args": ["-m", "factscribe", "mcp", "/abs/path/to/paper", "--allow-write"]
    }
  }
}
```

## 2. 协议

- JSON-RPC 2.0，一行一条消息；
- `initialize` 返回 `protocolVersion: "2024-11-05"`、
  `capabilities.tools`、`serverInfo.name = "factscribe"`；
- 支持 `ping`、`tools/list`、`tools/call`、`shutdown`、`exit`；
- 通知（`notifications/initialized` 等）不回包；
- 未知方法返回 `-32601`；解析错 `-32700`；非法请求 `-32600`。

`tools/call` 成功：

```json
{"content":[{"type":"text","text":"{…JSON…}"}],"isError":false}
```

工具自身失败（只读、参数错、项目错）也走 `result`，`isError:true`，
不把服务打死；消息里带错误码（如 `READ_ONLY`）。

## 3. 工具

只读始终提供：

| 工具 | 作用 |
|---|---|
| `factscribe_status` | 事实数、节数、配置形态、`read_only` |
| `factscribe_project` | 节（file/text）、事实、来源、bib |
| `factscribe_brief` | 写作简报；可选 `section` 前缀 |
| `factscribe_audit` | 机械闸门；`exit` 0/1/3，附 `summary` / `findings` |

`--allow-write` 才加入：

| 工具 | 作用 |
|---|---|
| `factscribe_write_section` | 写审计闭包内的 `.tex`；临时文件 + 原子替换 |
| `factscribe_add_fact` | 追加事实；同 `fact add`，**不代签** |

写工具与 `serve --allow-write` 共用同一实现（`factscribe/workbench.py`），
不会出现“HTTP 能写、MCP 不能写”的第二套规则。

## 4. 安全

- stdio，不监听端口、不联网；
- 项目路径启动时固定；工具参数只能选闭包内的文件；
- 默认只读；写工具不出现，调用也返回 `READ_ONLY`；
- `add_fact` 仍要求 source 在项目内 `results/`（或显式 `source_root`），
  自动算 sha256，但绝不改人签清单。

## 5. 验收

`tests/test_mcp.py`（6 例）：initialize、只读 tools/list、status/audit、
只读写工具拒绝、未知方法、可写模式写章节 + 追加事实。
