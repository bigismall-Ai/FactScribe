# 证据清单：解冻与重冻（批 133）

规范：`docs/design/SPEC-EVIDENCE-STAMP.md` §9。实现：`factscribe/evidence.py`
（`LOG_REL`、`read_log` / `append_log` / `log_state` / `unfrozen_info` /
`unfreeze_evidence` / `freeze_evidence`）、`factscribe/cli.py`（`--unfreeze`、
`--reason`、`--at`）、`factscribe/audit.py` 与 `factscribe/review.py`
（黄 `EVIDENCE_UNFROZEN`）。测试：`tests/test_evidence_unfreeze.py`（16 例）。

## 状态机

```
无 lock / 无 log ──freeze──> 已冻结（log: freeze）
已冻结 ──修改清单（未解冻）──> 红 EVIDENCE_SET_CHANGED
已冻结 ──unfreeze --reason──> 解冻（log: unfreeze，黄 EVIDENCE_UNFROZEN）
解冻 ──freeze（未改）──> 已冻结（log: freeze；幂等状态下不重复写）
解冻 + 修改 ──freeze──> 已冻结（lock 更新，audit 转绿）
已冻结且哈希未变 ──freeze──> 幂等（不写 lock、不写 log）
```

确定性：不读系统时钟；时间只从 `--at YYYY-MM-DD` 来，未传写 `""`。

## 验收实录（`../paper-b` 副本，删 main.pdf 以隔离 PDF_STALE）

命令均在 `paperkit-dev/` 下以 `env PYTHONPATH=src python3 -m factscribe ...` 运行。

| # | 步骤 | 退出码 | 关键输出 |
|---|---|---|---|
| 1 | `evidence --suggest <副本>` | 0 | 7 节、103 条 id，TOML 粘进 `paperkit.toml` |
| 2 | `evidence --freeze --reason "初始清单"` | 0 | sha256 `036da978…`，entries 103 |
| 3 | 未解冻改一条 id（`00_abstract`: B1→B2）→ `audit` | 1 | `EVIDENCE_SET_CHANGED` 红，指出 B1 从 `00_abstract` 移走 |
| 4 | `evidence --unfreeze --reason "补 B9，因新增段落" --at 2026-11-11` | 0 | log 追加 `{"action":"unfreeze",...,"hash_before":"036da978950abf48","at":"2026-11-11"}` |
| 5 | 解冻且清单仍有改动 → `audit` | 1 | 红 `EVIDENCE_SET_CHANGED` ＋ 黄 `EVIDENCE_UNFROZEN`（理由随消息） |
| 6 | 改回 `00_abstract` 的 B1（仍未重冻）→ `audit` | 3 | 只有黄 `EVIDENCE_UNFROZEN`，理由「补 B9，因新增段落」 |
| 7 | `evidence --freeze --reason "重冻"` | 0 | 哈希回到 `036da978…`，log 再追加一条 `freeze` |
| 8 | `audit` | 0 | 绿，无 `EVIDENCE_*` finding |

流水账（副本 `audit/evidence-log.ndjson`）：

```json
{"action":"freeze","hash":"036da978950abf48d6014f2526ec25b783060ca2569f332168331de9b660a402","entries":103,"reason":"初始清单"}
{"action":"unfreeze","reason":"补 B9，因新增段落","hash_before":"036da978950abf48","at":"2026-11-11"}
{"action":"freeze","hash":"036da978950abf48d6014f2526ec25b783060ca2569f332168331de9b660a402","entries":103,"reason":"重冻"}
```

## 边界

- 缺 `--reason`（或只有空白）：退出码 2，log 不动；
- 没有 lock 就 `--unfreeze`：退出码 2（无冻可解）；
- `--at` 不是 `YYYY-MM-DD`：退出码 2；
- 已在解冻状态再 `--unfreeze`：幂等，不重复追加；
- 解冻状态在 `review` 里只报黄，不进拒绝面（红才拒绝）。
