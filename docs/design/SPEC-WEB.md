# SPEC-WEB：本地工作台页面

日期：2026-11-13　　状态：v1（只读默认，可写需显式开启）

`factscribe web <项目>` 等于 `serve --ui`：同一个本地 HTTP 服务，既提供 API，
也在 `GET /` 提供三栏页面。页面只依赖本仓静态文件，不引入前端框架。

## 1. 命令

```bash
factscribe web <项目> [--host 127.0.0.1] [--port 0] [--token TOKEN] [--allow-write] [--allow-build]
```

启动打印：

```
URL：http://127.0.0.1:<port>
页面：http://127.0.0.1:<port>/?token=<token>
```

页面首次打开会读取 URL 里的 token，存到 `sessionStorage`，然后把它从地址栏移除。
没有 token 时页面显示输入框；token 只用于本机 API。

## 2. 页面

三栏布局：

| 区域 | 内容 |
|---|---|
| 左 | 章节列表（项目闭包内 `.tex`），点选加载 |
| 中 | 当前章节编辑器；保存按钮；只读时禁用 |
| 右 | 审计结论与 findings、事实账表 + 追加事实表单、证据冻结状态与按钮 |

- 启动后自动载入 `/api/project` 并跑一次 `/api/audit`；
- 保存走 `PUT /api/sections`，保存后不自动重审，由「运行审计」按钮触发；
- 审计红黄显示代码、中文短名、位置与消息；只显示前 40 条；
- 事实表单走 `POST /api/facts`；ID/主张/值/来源必填，来源可从项目 sources 选；
  追加后刷新事实表并重跑审计；工具只打印该抄进清单的那一行，**不代签**；
- 顶部「编译 PDF」调 `POST /api/build`；成功后可「打开 PDF」（`GET /api/pdf`）；
  需要启动时加 `--allow-build`，否则按钮禁用并说明；
- 证据区显示 lock 哈希/条数、mismatch、unfrozen 与最后动作；
- 冻结/解冻走 `POST /api/evidence/*`；解冻必须填理由。

## 3. 安全

- 页面与 API 同源，只绑回环；
- 静态文件只允许 `index.html` / `app.js` / `app.css` 三个固定名字；
- `serve_ui=False` 时 `GET /` 不提供页面；
- 默认只读；`--allow-write` 才启用保存、冻结/解冻；`--allow-build` 才启用编译。

## 4. 非目标

- 不做富文本/Markdown 预览；正文就是 LaTeX 源码；
- 不做 bib 编辑、PDF 编译（仍走 CLI / MiniFactScribe）；
- 事实表单只追加，不编辑/删除已有事实；
- 不引入前端构建链或第三方依赖。

## 5. 验收

`tests/test_web.py`（7 例）：首页免 token、静态资源、事实表单、编译默认拒绝、
API 仍要 token、带 token 读项目、`--allow-build` 下编译并下载 PDF；
`tests/test_packaging.py` 覆盖 `web/*` 是否随 wheel 发布。
