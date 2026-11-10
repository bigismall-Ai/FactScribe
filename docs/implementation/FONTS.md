# FONTS — Fandol 按需下载与构建注入实测（批 123）

规范：`docs/design/SPEC-FONTS.md`。本文件只记实测数，不重复规范条文。

## 1. 环境

| 项 | 值 |
|---|---|
| 机器 | macOS（darwin），Python 3.14.4（门禁另跑 3.10/3.11/3.12） |
| 引擎 | `/opt/homebrew/bin/tectonic`，Tectonic 0.17.0 |
| 网络 | 需经本机代理（`HTTPS_PROXY=http://127.0.0.1:7897`），`urllib` 直接尊重该变量 |
| 缓存目录 | `/Users/moc/.cache/factscribe/fonts/fandol`（`FACTSCRIBE_FONT_CACHE` 未改） |

## 2. 真实下载

```
$ env HTTPS_PROXY=http://127.0.0.1:7897 python3 -m factscribe fonts --fetch
== factscribe fonts ==
下载完成：https://mirrors.ctan.org/fonts/fandol.zip（26,688,406 字节，80.69 秒）
缓存目录：/Users/moc/.cache/factscribe/fonts/fandol
状态：完整（4/4）
  ✓ FandolSong-Regular.otf          4,947,904 字节
  ✓ FandolHei-Regular.otf           5,808,908 字节
  ✓ FandolKai-Regular.otf           7,790,552 字节
  ✓ FandolFang-Regular.otf          6,961,384 字节
来源：https://mirrors.ctan.org/fonts/fandol.zip
下载：2026-11-10T17:02:08Z（zip 26,688,406 字节）
缓存体积：25,545,403 字节
```

- 首次下载 80.69 秒，只解四个必需 OTF 与 `COPYING`/`README`。
- 补上包内粗体（`FandolSong-Bold.otf`、`FandolHei-Bold.otf`）后 `--force`
  重取一次：54.50 秒，**最终缓存 34,904,963 字节（33.3 MiB）**，仍远小于
  提交进 git 的代价。
- `SOURCE.txt` 记录 URL、UTC 下载时间、zip 字节数与 sha256
  （`9278f01b…5005a`）；`COPYING` 即 GUST Font License 原文，随包保留。

## 3. `fonts --status`

```
$ python3 -m factscribe fonts --status
== factscribe fonts ==
缓存目录：/Users/moc/.cache/factscribe/fonts/fandol
状态：完整（4/4）
  ✓ FandolSong-Regular.otf          4,947,904 字节
  ✓ FandolHei-Regular.otf           5,808,908 字节
  ✓ FandolKai-Regular.otf           7,790,552 字节
  ✓ FandolFang-Regular.otf          6,961,384 字节
来源：https://mirrors.ctan.org/fonts/fandol.zip
下载：2026-11-10T17:02:08Z（zip 26,688,406 字节）
缓存体积：34,904,963 字节
```

`--json` 给出 `path/present/complete/fonts[]/missing[]/cache_bytes/source`。
第二次 `--fetch` 直接输出「已完整，跳过下载」，不发起网络请求（幂等，测试用
`SOURCE.txt` 的 `st_mtime_ns` 断言）。

## 4. 真实构建 `paper-zh`

`paper-zh` 是 V1 项目，`project.build = "tectonic main.tex"`；本机 tectonic
没有系统级 Fandol，第一次 shell 编译仍报字体错，随后走临时副本注入 Fandol：

```
$ python3 -m factscribe build ../paper-zh
== paperkit build ==
引擎：/opt/homebrew/bin/tectonic
尝试：2 次
产出：../paper-zh/main.pdf（17 页，458688 字节）
字体：Fandol（/Users/moc/.cache/factscribe/fonts/fandol）
exit 0
```

- 注入只发生在临时副本：`paper-zh/main.tex` 仍是
  `\documentclass[UTF8,11pt,fontset=fandol]{ctexart}`，mtime 停在 11-09，
  文件里没有 `\setCJKmainfont`。
- PDF 从批 120 的系统字体版 306,031 字节（17 页）变成 458,688 字节；
  版式与 Overleaf 的 `fontset=fandol` 对齐。

### 4.1 PDF 里确实是 Fandol

```
$ pdffonts paper-zh/main.pdf
name                                 type        encoding    emb sub uni object ID
IHAIZV+FandolSong-Regular-Identity-H CID Type 0C Identity-H  yes yes no   4  0
BZIVMZ+LMRoman12-Regular-Identity-H  CID Type 0C Identity-H  yes yes yes  6  0
IXFAWU+FandolSong-Bold-Identity-H    CID Type 0C Identity-H  yes yes no   8  0
...
```

正文中文用 `FandolSong-Regular`，标题粗体用 `FandolSong-Bold`（真粗体，
不是合成）。文档没有用到黑/楷/仿，所以 PDF 里不出现后三个；注入行仍在
临时 `main.tex` 里（`--keep-temp` 可查四条 `\setCJK*`）。

## 5. 闸门 `audit --build`

```
$ python3 -m factscribe audit ../paper-zh --build
facts   : 48 条      sections: 18 个（扫描 18 个 .tex）
numbers : 234 个（bound 234 / unbound 0 / unmatched 0）
cites   : 13 次调用、11 个 key；bib 11 条（命中 11）
[黄] 1 处：UNSCANNED_TEX  main.tex
[红] 0 处
结论：0 红 / 1 黄 → 黄（退出码 3）
build  : 已编译（458688 字节）
exit 3
```

退出码与批 122 一致（3，既有黄），未因换字体变红。

## 6. 测试与门禁

- 新增 `tests/test_fonts.py` 17 例，全离线：本地 zip 夹具（可造缺字体、
  坏 zip、许可文件）、`file://` 与本地路径、幂等/`--force`、网络拒绝、
  `--status` 两态、构建注入 Fandol / 系统字体两分支、源 `.tex` 逐字节不变。
- 全量：`Ran 908 tests ... OK`（0 失败）。
- `./scripts/preflight-ci.sh`：见提交说明；干净克隆与 3.10/3.11/3.12
  矩阵全绿（字体文件不在仓内，缓存缺失时测试全部走本地夹具，不联网）。
