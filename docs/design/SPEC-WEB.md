# SPEC-WEB：本地工作台页面

日期：2026-11-14　　状态：v2（与 MiniApp 共用同一份界面；只读默认，可写需显式开启）

`factscribe web <项目>` 等于 `serve --ui`：同一个本地 HTTP 服务，既提供 API，
也在 `GET /` 提供工作台页面。这个页面与 MiniFactScribe 的页面是**同一份文件**
（源在 `factscribe/web/`，插件里用 `scripts/sync-miniapp-ui.sh` 同步）；页面自己判断
是在宿主里打开还是在浏览器里打开，据此显示不同的区。

## 0. 一套界面，两种模式

| 模式 | 判定 | 显示 |
|---|---|---|
| MiniApp | `window.mcode.miniapp` 存在 | 全部：正文/事实账/引用/保护/审计草稿、工作台、AI 起草、项目启动 |
| 网页 | 浏览器直接打开 | 只留「工作台」：真实论文项目、事实、证据、编译 PDF、审计 |
| 开发预览 | 网址带 `?dev=1`（`web --dev` 会打出来） | 网页也显示宿主专属区，但启动/草稿/AI 只做界面预览，按钮禁用并说明 |

接口分流：`wb('/project')` 在 MiniApp 走 Node 代理 `/api/workbench/project`，
在网页直连 Python `/api/project`；网页模式的 token 放 `Authorization` 头，
MiniApp 的 token 由 Node 保管、不进页面。

## 0.5 不带项目启动（项目管理模式）

`factscribe web` / `factscribe serve --ui` 的项目参数可省略：

```bash
factscribe web --port 0        # 先起服务，项目稍后在页面里选
```

- 启动时不读任何项目配置，只起服务；页面显示「还没有选论文项目」；
- 页面里的「最近项目」和「加入项目列表」调 `GET /api/projects`、`POST /api/projects`；
  `POST {path}` 校验文件夹（含 `paperkit.toml`）后**切换当前项目**并写登记册；
- `DELETE /api/projects?path=` 只从登记册移除，不动文件夹；移除当前项目后回到「未选择」；
- 未选项目时，项目相关的接口返回 400 `NO_PROJECT`；`/api/capabilities` 仍可用；
- 登记册与 MiniFactScribe 共用 `~/.factscribe/projects.json`（同一格式）。

## 1. 命令

```bash
factscribe web [项目] [--host 127.0.0.1] [--port 0] [--token TOKEN] [--allow-write] [--allow-build] [--dev]
```

启动打印：

```
URL：http://127.0.0.1:<port>
页面：http://127.0.0.1:<port>/?token=<token>
```

页面首次打开会读取 URL 里的 token，存到 `sessionStorage`，然后把它从地址栏移除。
没有 token 时页面显示输入框；token 只用于本机 API。

## 2. 页面

「工作台」页签（两种模式都有）：

| 区块 | 内容 |
|---|---|
| 项目 | MiniApp 模式显示最近项目、一键启动与权限开关；网页模式显示「本机服务」 |
| 章节 | 下拉选节 + 编辑器 + 保存（只读时禁用） |
| 审计 | 结论、红黄 findings、退出码 |
| 事实账 | 表格 + 追加事实表单（ID/主张/值/来源必填） |
| 证据 | 冻结状态、lock 哈希、mismatch/unfrozen，冻结/解冻按钮 |
| 编译 | 编译 PDF、打开 PDF；需 `--allow-build` |

- 启动后自动载入工作台项目并跑一次审计；
- 保存走 `PUT /api/sections`，保存后不自动重审，由「运行审计」按钮触发；
- 审计红黄显示代码、中文短名、位置与消息；只显示前 40 条；
- 事实表单走工作台事实接口（网页 `/api/facts`，MiniApp `/api/workbench/facts`）；ID/主张/值/来源必填，来源可从项目 sources 选；
  追加后刷新事实表并重跑审计；工具只打印该抄进清单的那一行，**不代签**；
- 「编译 PDF」调工作台 build 接口；成功后可「打开 PDF」（`GET /api/pdf`）；
  需要启动时加 `--allow-build`，否则按钮禁用并说明；
- 证据区显示 lock 哈希/条数、mismatch、unfrozen 与最后动作；
- 冻结/解冻走工作台 evidence 接口；解冻必须填理由；
- 网页模式下宿主专属区（草稿、AI、一键启动）隐藏；`?dev=1` 才显示，且只做界面预览；
- 项目管理（最近项目、加入/移除文件夹）两种模式都有；网页里选中即让服务切到该文件夹。

## 3. 安全

- 页面与 API 同源，只绑回环；
- 静态文件只允许 `index.html` / `app.js` / `app.css` 三个固定名字；
- `serve_ui=False` 时 `GET /` 不提供页面；
- 默认只读；`--allow-write` 才启用保存、冻结/解冻；`--allow-build` 才启用编译。

## 4. 非目标

- 不做富文本/Markdown 预览；正文就是 LaTeX 源码；
- 不做 bib 编辑；PDF 编译只在 `--allow-build` 下开放；
- 事实表单只追加，不编辑/删除已有事实；
- 不引入前端构建链或第三方依赖。

## 5. 验收

`tests/test_web.py`（7 例）：首页免 token、静态资源、事实表单、编译默认拒绝、
API 仍要 token、带 token 读项目、`--allow-build` 下编译并下载 PDF；
`integrations/minifactscribe/tests/sync.test.mjs`（4 例）钉住两边界面逐字节一致；
`integrations/minifactscribe/tests/ui.test.mjs` 覆盖模式判定、网页 token、
`--dev` 提示、编译/事实/证据入口。
