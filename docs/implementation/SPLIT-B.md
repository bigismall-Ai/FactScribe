# SPLIT-B — 单文件 `factscribe.py` 拆包（零行为变化）

批 46 / B 阶段。目标：把 2186 行单文件拆成 `factscribe/` 包，行为逐字节不变，
只移动代码，不改任何判据。

## 1. 模块表

| 文件 | 职责 | 行数 |
|---|---|---:|
| `factscribe/constants.py` | 版本、schema 版本、退出码分层、严重级别常量 | 20 |
| `factscribe/facts.py` | 数字归一化（`number_key`/`literal_tokens`/`fact_value_keys`）、`Fact`、expr 求值、`sha256_file` | 269 |
| `factscribe/config.py` | `ConfigError`、TOML（3.11 `tomllib` + 迷你解析器）、`Config`、facts/sections 装载、路径与 git 信息 | 345 |
| `factscribe/texscan.py` | TeX 遮罩（verbatim/verb/批注/注释/上下标/命令参数）、`scan_tex`、`_extract_numbers` | 380 |
| `factscribe/citations.py` | natbib 引用家族、`BibEntry`、bib 解析、重复检测 | 145 |
| `factscribe/audit.py` | `Issue`、源头锚定、`verify_sources`、`run_check`、联网核验、`run_audit` | 697 |
| `factscribe/report.py` | `render_matrix`、`PREAMBLE_TEXT`、人读渲染、JSON 载荷 | 199 |
| `factscribe/cli.py` | `run_build`、argparse、子命令、退出码、`main` | 162 |
| `factscribe/__init__.py` | 各子模块名字原样再导出（含下划线私有名），保持 `import factscribe` 属性面 | 25 |
| `factscribe/__main__.py` | `python -m factscribe` 入口 | 10 |

拆分时新增 `constants.py`（建议边界外的一件）：版本/退出码/严重级别被
`audit`、`report`、`cli` 共用，独立成件可避免子模块互相 import 顶层包造成环。

依赖方向（无环）：

```
constants
  ↑
facts ──> config ──> citations
  ↑         ↑           ↑
  └──> texscan ─────────┤
            ↑           │
            └──> audit ─┘
                   ↑
                 report
                   ↑
                  cli
```

`__init__` 只做再导出，不承载逻辑。外部脚本 `import factscribe` 后仍可使用
拆分前的全部名字（测试用到的 `number_key`、`scan_tex`、`_extract_numbers`、
`_resolve_arxiv`、`_resolve_doi` 等均在其中）。

## 2. 兼容入口

- `python3 -m factscribe ...` 与拆分前 `python3 factscribe.py ...` 等价；
- 根目录 `factscribe.py` 已删除，避免与同名包冲突；
- `pyproject.toml` 入口改为 `factscribe = "factscribe.cli:main"`，包声明为
  `packages = ["factscribe"]`，版本从 `factscribe.constants.VERSION` 读取；
- 测试改为用 `python3 -m factscribe` 唤起子进程（判据未动，只换调用路径）。

## 3. golden 比对

拆包前冻结（`/tmp/golden-before`）：

```bash
for d in fixtures/hostile/*/ fixtures/benign/*/ examples/minimal/; do
  python3 factscribe.py audit "$d" --json > "/tmp/golden-before/$(echo $d | tr '/' '_').json" 2>&1
  echo "$?" >> /tmp/golden-before/exits.txt
done
python3 factscribe.py audit ../paper --json > /tmp/golden-before/paper.json 2>&1
python3 factscribe.py check ../paper --json > /tmp/golden-before/paper-check.json 2>&1
```

拆包后用同一脚本、同一命令换 `python3 -m factscribe` 重跑（`/tmp/golden-after`），
再用 `scripts/golden_diff.py`（归一化绝对路径与时间字段）比对：

```
golden_diff: 28 identical, 0 different, 28 files
```

28 个文件 = 27 份 JSON（12 hostile + 12 benign + `examples/minimal` + `../paper`
的 audit/check）+ 1 份 `exits.txt`。原始 `diff -rq` 也是 0 差异（比归一化更强）。

额外对照（旧单文件 `/tmp/factscribe_single.py` 对 `python3 -m factscribe`）：

- 全部 25 个 fixture 目录 × `audit`/`check` 人读输出：逐字节一致，退出码一致；
- `--help`、`matrix`、`preamble` 输出与写盘内容：一致；
- `examples/minimal` audit 读数：2 红 / 7 黄，退出码 1，与拆前一致。

## 4. 测试读数

```
Ran 121 tests in 9.586s

OK (expected failures=12)
```

121 例全过；expectedFailure 仍恰好 12 条（没有意外通过、没有意外报错）。

## 5. 同步更新

- `.github/workflows/test.yml`：两处命令改 `python -m factscribe`；
- `README.md` / `README.en.md` / `CONTRIBUTING.md` / `examples/minimal/README.md`：
  命令改 `python3 -m factscribe` / `factscribe`，并更新「单文件」相关表述；
- `pyproject.toml`：scripts 与 packages/version；
- 新增 `scripts/golden_diff.py`：golden 比对工具（忽略路径与时间字段）。

## 6. 边界

- 未改 `paper/`、`sihankor/`；未 push（认证问题未解决），只提交。
- 打包构建（`pip wheel`）因本机离线且未装 setuptools 未实跑；`pyproject.toml`
  使用标准 setuptools 写法，`python3 -c "import factscribe"` 与 `python3 -m factscribe`
  均可用。
