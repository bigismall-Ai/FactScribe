# 文风闸：RHYTHM_PLATEAU 降为参考读数（批 109）

> 规范：`docs/design/SPEC-V3.0.md` §13.5、§13.10。
> 范围：只改 `factscribe style` 的 `RHYTHM_PLATEAU` 档位与输出分区；
> `SENTENCE_UNIFORMITY` 及其它判据、退出码契约未改。

## 1. 问题（批 108 端到端试跑）

| 证据 | 读数 |
|---|---|
| 中英两节基线共 4 条 `RHYTHM_PLATEAU` 命中 | 3 条是 10 词分桶造成的「长度接近」，不是节奏平台 |
| 四份语料剩余命中 | 英文 17/17、中文 12/14 都是它 |
| 处方覆盖 | 9 条处方没有一条治它 |
| 与已有判据的关系 | 与 `SENTENCE_UNIFORMITY`（句长 CV）测同一件事，后者有健康区间 |

结论：这条规则在现有形态下主要是分桶伪影，且与正式判据重复，不适合继续占黄牌数。

## 2. 改法

- 新增配置项 `rhythm_plateau_level`，默认 `"info"`：
  - `"info"`：读数保留在 `metrics.rhythm_plateau`，条目进 `advisories`；
    不进 findings、不影响退出码、不占黄牌数；
  - `"yellow"`：恢复旧行为（进 findings，可黄牌 exit 3）。
- 人读输出新增 `[参考]` 区，明说「不计数、不影响退出码；节奏的正式判据是
  `SENTENCE_UNIFORMITY`」。
- `--json` 新增顶层 `advisories`，与 `findings` 分开；`metric_details` 带
  `rhythm_plateau_level`。
- `SENTENCE_UNIFORMITY` 在规范里标为节奏的正式判据。

## 3. 读数（`paperkit-dev/` 下跑）

改后：

```text
$ python3 -m factscribe style ../paper --json
exit=0  findings=0  advisories=17（全部 RHYTHM_PLATEAU）

$ python3 -m factscribe style ../paper-zh --json
exit=3  findings=2（全部 COLLOQUIAL_TRIAD）  advisories=12（全部 RHYTHM_PLATEAU）
```

英文黄牌 17 → 0；中文黄牌 14 → 2，且两条都回到真实结构判据
`COLLOQUIAL_TRIAD`。

## 4. 测试数

- 新增 `tests/test_rhythm_plateau_level.py`：5 例
  （默认 info、`"yellow"` 恢复、人读参考区、JSON 分区、非法档位 exit 2）。
- 既有 `tests/test_style.py` 与 `tests/test_style_v4.py` 的节奏正例改为
  显式配置 `rhythm_plateau_level = "yellow"`，负例与其它判据不动。
- 本批不删任何既有测试。
