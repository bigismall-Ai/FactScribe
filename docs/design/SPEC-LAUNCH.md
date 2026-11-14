# SPEC-LAUNCH：论文项目登记册与一键启动工作台

日期：2026-11-14　　状态：v1

MiniFactScribe 不再要求用户先开终端。工作台页签选一个**论文项目文件夹**，
点「启动并连接」，Node 用固定命令拉起 `factscribe serve`，读首行 JSON 握手，
退出时收掉子进程。

## 1. 论文项目＝文件夹

- 一个论文项目就是一个含 `paperkit.toml` 的文件夹；
- 切换项目＝改文件夹；读写与审计只对当前文件夹生效；
- 校验（每次启动都重跑，不信任上次结论）：存在、是目录、含 `paperkit.toml`；
  `~` 展开后要求绝对路径；符号链接解析成真实路径再登记；
- 显示名取 `[project] title` / `name`，读不到用文件夹名。

## 2. 登记册：`~/.factscribe/projects.json`

```json
{
  "version": 1,
  "projects": [{ "path": "/abs/paper", "name": "论文标题", "lastOpenedAt": "2026-11-14T..." }],
  "lastPath": "/abs/paper",
  "python": "",
  "pythonpath": ""
}
```

- 同一份登记册也由 Python（`factscribe/projects.py`）读写：网页里选项目、MiniApp 里选项目，
  改的是同一个文件，格式一致；
- 放家里而不是 `dataDir`：dataDir 由宿主创建、位置不透明且可能变化，重装插件就丢；
- 权限 0600；只存路径、显示名、上次使用时间，不存正文；
- 置顶最近使用、去重、上限 30 条；坏文件当空册，不因此拒绝启动；
- 用户可随时删这个文件，等价于「清空最近项目」。

## 3. 一键启动

```
python3 -m factscribe serve <文件夹> --port 0 --json [--allow-write] [--allow-build]
```

- `spawn` 固定参数、`shell: false`；页面传来的字段只能填进项目路径与两个布尔开关，
  不会变成命令、管道或环境变量；
- 端口始终 `0`（系统分配），token 由 Python 自己生成，不来自页面；
- 读 stdout 第一行 `event=listening` 的 JSON，拿到 `url` / `token` / `project`，20 秒超时；
- 解释器候选：`FACTSCRIBE_PYTHON` → 登记册 `python` → `python3`；
  都失败再试 PATH 上的 `factscribe`。只有「解释器/模块找不到」才换形状，
  其它错误直接报 stderr（不静默降级）；
- 源码未安装时用登记册 `pythonpath` 设 `PYTHONPATH`，一次显式设置，不是任意环境注入。

## 4. 生命周期

- 启动的服务归 Node 进程管：换项目时先停旧的，再起新的；
- 「停止工作台」`SIGTERM`，3 秒后 `SIGKILL`；
- `dispose()` 一并收子进程（宿主只停入口进程，不替你发现孤儿）；
- 一键启动的 URL/token 标 `managed` 落盘；宿主重启后不再恢复——旧进程已经死了，
  不能让界面假装还连着。手动连接的保存行为不变。

## 5. 权限开关

- 默认只读；
- 「允许写章节与事实」→ `--allow-write`；
- 「允许编译 PDF」→ `--allow-build`；
- 两个开关都不默认勾选；启动结果里显示实际模式（只读 / 可写 / 可编译）。

## 6. 接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/projects` | 列出登记册、上次项目、解释器设置 |
| POST | `/api/projects` | `{path}` 加入；`{python}` / `{pythonpath}` 保存解释器设置 |
| DELETE | `/api/projects?path=` | 从列表移除（不动文件夹） |
| POST | `/api/workbench/start` | `{path, allowWrite, allowBuild}` 启动并连接 |
| POST | `/api/workbench/stop` | 停掉子进程；幂等 |

错误码：`PROJECT_INVALID`（400，路径不是论文项目）、`WORKBENCH_STARTING`（409）、
`WORKBENCH_START_FAILED`（502，带 stderr 尾巴）。

## 7. 验收

- `tests/projects.test.mjs`：文件夹校验、名称回退、登记册置顶/去重/限量/坏文件、
  固定参数、假解释器握手与停止、错误解释器提示；
- `tests/server-routes.test.mjs`：加入/列出/移除、启动前校验 400、解释器与包路径
  不接受参数、未启动状态与幂等停止；
- 真实链路（手动，需本机装 factscribe）：起 `serve` → `/api/health` 200 → 停止后进程消失。
