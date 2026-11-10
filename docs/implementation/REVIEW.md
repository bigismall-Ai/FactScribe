# 改写验收一条命令实施记录（批 114）

> 规范：`docs/design/SPEC-REVIEW.md`。
> 新增 `factscribe review` 子命令与新模块 `factscribe/review.py`；
> **未改 `protect` / `style` / `tide` 的判据与退出码**；零第三方依赖（纯标准库）。

一句话：`review` 是 `protect + style --diff + tide` 的组合，不新增判据。

## 1. 判据表

| 项 | 复用实现 | 判定 | 退出码 |
|---|---|---|---|
| 保护面 | `protect.compare(before, after)` | 有 `severity=red` → **拒绝** | 1 |
| 复检 | `style.analyze` + `style.filter_new_findings` | 新增违规 > `--allow-new` → **需复核** | 3 |
| 闭合 | `tide.run_tide(before, after)` | `paired ∧ hash_ok ∧ pass_all` 不全真 → **拒绝** | 1 |
| 全过 | — | **通过** | 0 |

优先级：拒绝 > 需复核 > 通过。目录不存在、`--allow-new` 为负等用法错返回 2；
工具内部错误返回 4（沿用既有分层）。

`tide` 账本写到临时目录，`review` 对文档树只读；`--snapshot` 只在最终判定为
`pass` 时落快照。

## 2. 验收读数（真实语料）

命令均在 `paperkit-dev/` 仓根执行。

| # | 命令 | 判定 | 退出码 |
|---|---|---|---|
| 1 | `review --before ../paper --after /tmp/presc-regen/en` | 通过 | 0 |
| 2 | `review --before ../paper-zh --after /tmp/presc-regen/zh` | 通过 | 0 |
| 3 | `review --before ../paper --after ../paper` | 通过 | 0 |
| 4 | `review --before ../paper --after /tmp/negctl` | 拒绝 | 1 |

读数摘要：

```text
# 1 en
verdict=pass   protect_red=0  new=0  tide_closed=True
criteria={'paired': True, 'hash_ok': True, 'pass_all': True}

# 2 zh
verdict=pass   protect_red=0  new=0  tide_closed=True
criteria={'paired': True, 'hash_ok': True, 'pass_all': True}

# 3 同一目录
verdict=pass   protect_red=0  new=0  tide_closed=True
criteria={'paired': True, 'hash_ok': True, 'pass_all': True}

# 4 改过数字的阴性对照
verdict=reject  protect_red=1  new=0  tide_closed=False
criteria={'paired': True, 'hash_ok': True, 'pass_all': False}
```

第 4 条的人读输出逐项点名了红的位置与闭合三项：

```text
判定：拒绝（退出码 1）
原因：保护面有 1 条红：PROTECT_NUMBER_CHANGED；tide 未闭合：波及面内保护面有 1 条红：PROTECT_NUMBER_CHANGED

保护面：红 1   黄 0   信息 0
  [红] PROTECT_NUMBER_CHANGED sections/07_threats.tex:8: 数字 "16" 改成了 "17"

复检（只算新增）：改前 0 处 → 新增 0 处（允许 0）
  （没有新增违规）

闭合：paired ✓   hash_ok ✓   pass_all ✗
  涨 1   落 1   波及面 2
  - 波及面内保护面有 1 条红：PROTECT_NUMBER_CHANGED
```

快照验收：

```text
# 通过 + --snapshot：落快照
exit=0  {"requested": true, "saved": true, "short": "55b36d77611690e0",
         "files": 52, "bytes": 331488, "store": "/tmp/review-snap"}

# 拒绝 + --snapshot：不落快照（store 目录也不创建）
exit=1  {"requested": true, "saved": false, "id": null, ...}
```

## 3. 测试

`tests/test_review.py`：**20 例**，覆盖

| 组 | 例数 | 要点 |
|---|---|---|
| 判定 | 6 | 无改动通过；数字改动拒绝并点名 `PROTECT_NUMBER_CHANGED`；新增标题格式问题需复核并给码与行号；`--allow-new 1` 放行；删文件因 tide 不闭合拒绝；拒绝优先于需复核 |
| JSON | 2 | 三项明细 + 最终判定；snapshot 块显式区分 requested/saved |
| 三种判定目录对 | 3 | pass / reject / needs_review 各一条真实目录对 |
| 快照 | 3 | 通过才存；需复核不存；拒绝不存 |
| 输出 | 2 | 人读逐项列保护面位置、复检、闭合三条件；需复核给码与行号 |
| 只读 | 1 | `review` 不往 `--after/audit/` 写账本 |
| 用法 | 3 | `--help` 写明别名；目录不存在返回 2；负 `--allow-new` 返回 2 |

门禁读数：

- `env PYTHONPATH=src python3 -m unittest discover -s tests`：**791 例全绿**
  （本机 Python 3.14；`tests/test_review.py` 含 20 例）；
- `./scripts/preflight-ci.sh`：**全绿**（干净克隆本批提交 `08bce66`，
  816 例 × 3.10/3.11/3.12）；
- `./scripts/preflight-ci.sh --fast`：**全绿**（工作区含本批改动，
  816 例 × 3.10/3.11/3.12）。

## 4. 文件

- 新增：`factscribe/review.py`（编排层，不改底层判据）；
- 改动：`factscribe/cli.py`（注册 `review` 子命令与 `--help` 别名说明）；
- 新增：`tests/test_review.py`；
- 新增：`docs/design/SPEC-REVIEW.md`、`docs/implementation/REVIEW.md`。

README 命令表本批未改（由主控统一处理）。
