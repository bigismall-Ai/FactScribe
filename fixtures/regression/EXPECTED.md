# 回归夹具读数｜paper-en

> 快照来源：`paper/`（只读，未改动）。复制范围：`facts/`、`sections/`、`appendix/`、
> `tables/`、`figures/`、`refs.bib`、`main.tex`、`results/MANIFEST.toml`。
> `source_root` 改为相对路径 `../../../..`（工作区根，等价于原绝对路径），
> 原始产物留在 `experiments/ctx-compiler-redblue/`，夹具因此在仓内可移植。

## 命令

```bash
cd paperkit-dev
python3 factscribe.py audit fixtures/regression/paper-en --json
```

## 读数（2026-11-08）

| 项 | 值 |
|---|---|
| exit | **3**（唯一的黄，不是红） |
| facts | 48 |
| sections（闭包内文件） | 18 |
| numbers_total | **234** |
| numbers_bound | **234** |
| numbers_unbound | 0 |
| numbers_unmatched | 0 |
| 红（绑定级） | **0** |
| 黄 | 1：`UNSCANNED_TEX main.tex` |

## 判读

- **0 红、234 绑定**是本回归线的硬断言（`tests/test_fixtures.py::RegressionPaperTest`）。
- `main.tex` 不在 `sections = "*/[0-9a-d]*.tex"` 的 glob 内，故报 `UNSCANNED_TEX` 黄。
  按任务要求保留 `main.tex` 以便后续闭包规则使用；这是覆盖提示，不是绑定级红。
- 快照只读：测试与审计都不得写回 `paper/` 或本目录。
