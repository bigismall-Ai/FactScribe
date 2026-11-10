# SPEC-FONTS — Fandol 中文字体按需下载与本地缓存

批 123。动机：批 120 的中文编译兜底改用系统 `STHEITI.ttf`，本机 PDF 的
字体与 Overleaf（`fontset=fandol`）不一致——数字回检够用，但版式不同。
本规范让编译用**真正的 Fandol 字体**，同时**不把 27 MB 的字体包提交进仓**。

## 1. 为什么不入库

Fandol 官方包 `https://mirrors.ctan.org/fonts/fandol.zip` 约 26.7 MB，
内含四个必需 OTF 与 GUST Font License。字体二进制会永久撑大 Git 历史，
且许可证要求随包保留许可文本。因此采用「按需下载 + 本地缓存」：

```
~/.cache/factscribe/fonts/fandol/        # 默认缓存目录（可用环境变量覆盖）
├── FandolSong-Regular.otf               # 宋
├── FandolHei-Regular.otf                # 黑
├── FandolKai-Regular.otf                # 楷
├── FandolFang-Regular.otf               # 仿
├── FandolSong-Bold.otf  …               # 包内其它文件（有则保留）
├── LICENSE / GUST-Font-License.txt …    # 许可证原文，随包保留
└── SOURCE.txt                           # URL、下载时间、zip 字节数、sha256
```

- 环境变量 `FACTSCRIBE_FONT_CACHE` 可把缓存指到任意目录（测试与多机共用）。
- 仓内**不允许**出现字体文件或 zip；`.gitignore` 已忽略 `*.pdf`，本批再补
  两条兜底规则。

## 2. 命令

```
python3 -m factscribe fonts --status [--json]
python3 -m factscribe fonts --fetch [--url <镜像>] [--force] [--json]
```

### 2.1 `--status`

纯读命令，**永远 exit 0**。人读输出给出缓存路径、完整/缺失、四个字体逐个的
存在与字节数、来源 URL 与下载时间。`--json` 同信息结构化：

```json
{
  "path": "/home/me/.cache/factscribe/fonts/fandol",
  "present": true,
  "complete": true,
  "fonts": [{"name": "FandolSong-Regular.otf", "present": true, "bytes": 6342000}],
  "missing": [],
  "cache_bytes": 26700000,
  "source": {"url": "...", "downloaded": "2026-11-11T...Z",
             "zip_bytes": 26700000, "sha256": "..."}
}
```

### 2.2 `--fetch`

1. 缓存已完整且未给 `--force` → **直接返回**（幂等，不发起网络请求）：
   人读输出「已完整，跳过下载」，`downloaded=false`。
2. 否则用 `urllib.request` 下载（**尊重 `HTTPS_PROXY` 等标准代理变量**），
   流式写进缓存目录的临时 `.part` 文件；记录 zip 字节数、sha256 与耗时。
3. 解压：只把包内四个必需 OTF 与许可/说明文本按 basename 摊平写进缓存，
   不保留 zip 目录树；给 `--url` 也接受 `file://` 与本地路径（离线测试用）。
4. 校验：四个文件缺一即失败（列出缺的名字），**exit 4**；网络错误、非 zip、
   HTTP 4xx/5xx 同样 **exit 4**，**不许静默回退系统字体**。
5. 成功后写 `SOURCE.txt`（URL、UTC 下载时间、zip 字节数、sha256）。

`--force` 重下并覆盖；旧缓存不完整时也自动重下。

### 2.3 退出码

| 情况 | 退出码 |
|---|---|
| `--status` 任意状态 | 0 |
| `--fetch` 成功 / 已完整跳过 | 0 |
| 网络失败 / zip 坏 / 缺任一必需 OTF | 4（`EXIT_INTERNAL`） |
| 用法错（既不给 `--status` 也不给 `--fetch`） | 2（argparse） |

## 3. 构建优先级（改批 120 的自动编译）

编译仍是「先直接编；命中字体错误特征才改临时副本重试」（`SPEC-BUILD` §3.2）。
第二次尝试的字体来源按以下优先级：

| 顺序 | 条件 | 注入 |
|---|---|---|
| 0 | 显式 `--cjk-font <路径>` | 用户点名的字体文件（保持批 120 行为，优先于缓存） |
| 1 | 缓存完整（四个 OTF 齐） | Fandol 四条：`\setCJKmainfont`（宋）、`\setCJKsansfont`（黑）、`\setCJKmonofont`（仿）、`\setCJKfamilyfont{zhkai}`（楷） |
| 2 | 缓存缺失 | 批 120 原样：`fc-match STHeiti` → `fc-match "Heiti SC"` |

注入模板（`Path` 必须以 `/` 结尾）：

```latex
\setCJKmainfont[Path=<缓存目录>/]{FandolSong-Regular.otf}
\setCJKsansfont[Path=<缓存目录>/]{FandolHei-Regular.otf}
\setCJKmonofont[Path=<缓存目录>/]{FandolFang-Regular.otf}
\setCJKfamilyfont{zhkai}[Path=<缓存目录>/]{FandolKai-Regular.otf}
```

- 包内存在 `FandolSong-Bold.otf` / `FandolHei-Bold.otf` 时，注入行追加
  `BoldFont=...`，让 `\textbf` 用真粗体。
- 缓存缺失时输出**明写**「用了系统字体，未用 Fandol」，并提示跑
  `python3 -m factscribe fonts --fetch`。
- 用 Fandol 时输出「字体：Fandol（缓存目录）」。
- 仍然**只改临时副本**：项目里的 `.tex` 逐字节不变（结构保证，不靠自觉）。
- 批 123 起，`build` 子命令的 shell 路（`project.build` 非空）也享受同一
  字体兜底，否则 `paper-zh` 这类 V1 项目永远编不出 Fandol PDF。

## 4. 许可

Fandol 采用 **GUST Font License**（GUST 字体许可，LPPL 兼容的免费许可，
允许嵌入与再分发，要求随字体保留许可文本）。缓存目录里保留 zip 内所有
`LICENSE*`、`COPYING*`、`README*` 文件；不把字体或 zip 提交进仓，因此
GUST 的再分发条款不涉及本仓。

## 5. 边界

- 纯标准库（`urllib`、`zipfile`、`hashlib`、`shutil`）；不引入第三方依赖。
- 不做后台自动下载：`build`/`audit --build` 永不联网，缓存缺失就退回系统字体。
- 不校验 OTF 内部结构，只校验文件名与可读字节（够用；真编失败会报编译错）。
- `fonts --fetch` 并发跑不在承诺内（同目录临时文件会互相覆盖，最后者胜）。
