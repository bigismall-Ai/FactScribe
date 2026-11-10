# SPEC-BUILD — `factscribe build` 自动编译 PDF

批 120。动机：V3 项目声明（`paperkit-project/3.x`）不读 `[project].build`，
`factscribe build` 因此永远走「跳过编译」分支，PDF 停在旧字节上。实测后果：
`factscribe audit` 把旧 PDF 与当前账本对多重集，报出一串
`PDF_UNACCOUNTED_NUMBER`（exit 5），而工具没有任何一句话提示「PDF 该重编了」。

本规范让 `build` 在 `project.build` 为空时**自动编译**：用本机 `tectonic`
编 `main.tex`，把 `main.pdf` 写回项目目录。**项目里的任何 `.tex` 都不改**。

## 1. 入口与判定

```
python3 -m factscribe build <项目> [--engine tectonic] [--cjk-font <路径>]
                            [--keep-temp] [--json]
```

判定顺序（只有两条路，互斥）：

| `project.build` | 行为 |
|---|---|
| 非空 | **保持原行为**：按 shell 字符串执行（`SPEC-V1` B5），超时 600 秒；退出码沿用 0/1 |
| 为空 | 走本规范的自动编译路径（§2–§5） |

V3 项目声明没有 `build` 字段，配置层按空串处理，因此 V3 项目天然走自动路径。

## 2. 自动路径的前置检查

1. `main.tex`（V3 的 `root_tex`）不存在 → 明确报错，**exit 2**（配置/用法错），
   消息里点名缺的是哪个文件。不允许静默跳过。
2. 本机找不到引擎（`shutil.which(<engine>)` 为空）→ **exit 8**
   （`PDF_TOOL_MISSING`），消息里必须出现 `PDF_TOOL_MISSING` 字样与
   `--engine` 提示。不允许静默跳过。
3. `--engine` 既接受命令名（在 `PATH` 里找），也接受绝对路径。

## 3. 编译过程

### 3.1 只在临时副本上编

每次尝试都在 `tempfile.mkdtemp(prefix="factscribe-build-")` 下的**项目副本**
里执行：

```
tectonic -X compile main.tex        # cwd = <temp>/project
```

项目目录里只允许出现最终 `main.pdf`（`cfg.output`）；`.aux/.log/.toc` 等中间
产物全部留在临时副本里。这样「不改源文件」是结构保证，不靠自觉。

### 3.2 字体兜底（中文）

本机没有 CTeX 的 fandol 字体时，第一次编译会报
`CTeX fontset 'fandol' could not be found`。判定为字体问题的输出特征
（大小写不敏感，任一命中）：

- `fontset`
- `could not be found`
- `fontspec error`

命中后**只改临时副本**：

1. 把 `\documentclass[...]` 里的 `fontset=<值>` 替换为 `fontset=none`；
2. 在 `\documentclass` 行之后插入一行
   `\setCJKmainfont[Path=<字体目录>,BoldFont=<文件名>]{<文件名>}`。

字体文件按以下顺序取：

| 顺序 | 来源 |
|---|---|
| 1 | `--cjk-font <路径>`（必须是已存在的文件） |
| 2 | `fc-match -f "%{file}" STHeiti` |
| 3 | `fc-match -f "%{file}" "Heiti SC"` |

三条都拿不到 → **exit 4**，输出里带「CJK 字体未找到」与上一次编译的末 20 行。

### 3.3 重试次数

最多两次：第一次「直接编」；只有命中 §3.2 的特征才做第二次「临时副本改造后
再编」。其它失败（缺宏包、语法错）不重试，直接按 §4 报错。

## 4. 结果与退出码

成功：

- 把临时副本里的 `main.pdf` 复制回项目目录的 `cfg.output`；
- 打印引擎、尝试次数、页数、字节数；
- `--json` 追加字段：`engine`（实际可执行文件路径）、`engine_requested`、
  `attempts`（数组，每项含 `attempt/mode/returncode/ok`）、`pdf_path`、
  `pdf_bytes`、`pdf_pages`、`temp_dir`（仅 `--keep-temp` 时保留路径）。

失败：

| 情况 | 退出码 |
|---|---|
| `main.tex` 缺失 | 2（`EXIT_CONFIG`） |
| 引擎缺失 | 8（`EXIT_MISSING`，`PDF_TOOL_MISSING`） |
| 编译失败 / 字体兜底失败 / 退出码 0 但无 PDF | 4（`EXIT_INTERNAL`） |
| `project.build` 非空且 shell 失败 | 1（原行为不变） |

编译失败时输出**最后 20 行**合并输出（stdout＋stderr），不截断关键报错。

## 5. 临时目录

- 默认：`finally` 里 `shutil.rmtree`，不留垃圾；
- `--keep-temp`：保留并打印路径（`--json` 的 `temp_dir` 同值），供人工看改造
  后的 `main.tex`。

## 6. 边界

- 纯标准库；子进程只调 `tectonic` 与 `fc-match`，不做网络请求（`tectonic`
  自己的 bundle 缓存不在此列）。
- 不读 `audit/`、不判报告新鲜度——`build` 仍是排版预览，发布路径另论。
- 同一项目并发跑 `build` 不在本规范承诺内（临时目录各自独立，回写最后者胜）。
- 项目内符号链接在副本里按链接复制（`copytree(symlinks=True)`），不改指向。

## 7. 闸门命令的 `--build`（批 122）

`audit` 与 `verify-pdf` 增加开关 `--build`，把「编 PDF」与「回检」合成一步，
避免审的是旧 PDF。编译逻辑不另写一套，直接走 §1–§5 的同一入口。

```
python3 -m factscribe audit <项目> --build [--json]
python3 -m factscribe verify-pdf <pdf> --report <report> [--build]
                                     [--project <项目>] [--json]
```

| 情况 | 行为 |
|---|---|
| 传 `--build` | 先按 §1 判定：`project.build` 非空按 shell 跑；为空走 §2–§5 自动路径。编译成功后才继续审计/回检 |
| 编译失败 | 立即中止，不再输出审计结论；退出码沿用 build 的（shell 路 1，自动路 2/8/4） |
| 不传 `--build` | 行为完全不变：不探测、不调用引擎，CI 上没有 TeX 也不受影响 |

两点补充：

1. **字体兜底延伸到 shell 路**：`project.build` 非空但败在 §3.2 的字体特征
   上时，闸门会复用自动路径的临时副本兜底重试（只改副本，项目里的 `.tex`
   不动）。这是 `audit`/`verify-pdf --build` 专有的宽容；`build` 子命令的
   shell 路仍保持批 120 的原行为。
2. **`verify-pdf` 的项目目录**：默认取 PDF 的上一级目录；PDF 不在项目根时
   用 `--project <项目>` 指定。

`--json` 增补字段（两个命令同形）：

```json
"build": {"ran": true, "ok": true, "pdf_bytes": 79370}
```

- 未传 `--build`：`{"ran": false, "ok": true, "pdf_bytes": 0}`；
- 编译失败：`ran=true`、`ok=false`、`pdf_bytes=0`，并另给 `build_output`
  人读原始输出。
