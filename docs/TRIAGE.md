# 第一次跑 audit 红了怎么办

先记住三条：

1. **红 = 必须修**（编造、不自洽、账坏了）；**黄 = 看一眼，可以先不管**。
2. 报告末尾那行 `退出码` 才是结论：`0` 绿、`1` 红、`3` 黄、`5` 覆盖缺口。
3. 修的顺序有讲究：**账 → 签 → 引用 → 正文数字 → 文风**。账错了，后面全对不上。

## 一、先修这些（红）

| 错误码 | 它在说什么 | 怎么修 |
|---|---|---|
| `UNMATCHED_NUMBER` | 这个数字谁都对不上：行内没绑定，也不在任何 fact 的值域里 | 先回 `results/` 找到它的出处 → `fact add` → 数字后加 `\fact{ID}`；确实不是数据（年份、章节号、页码）用 `\pkignore{...}` 显式豁免 |
| `BOUND_MISMATCH` | 这行绑了 `A1`，但这个数字不在 `A1` 的值域里 | 绑定写错了，或账里的 `value` 过时了；先核对账 |
| `MISSING_CITE` | `\cite` 的 key 在 `refs.bib` 里不存在 | 补 bib 条目，或删掉这条引用 |
| `BIB_NO_STABLE_ID` | bib 条目没有 `doi` / `arxiv`（`@misc` 要 `url`） | 补稳定标识；查不到的文献不要引 |
| `BAD_STABLE_ID_FORMAT` | 标识符格式不对（arXiv 新旧号、DOI 写法） | 按报错改成合法写法 |
| `SOURCE_NOT_SIGNED` | 这条事实的来源没进人签清单 | 把 `fact add` 打印的哈希行抄进 `results/MANIFEST.toml`，写 `signed_by` |
| `SOURCE_SHA256_MISMATCH` | 签过之后 `results/` 里的文件被改了 | 改动合理 → 重新抄哈希并重签；不合理 → 恢复原文件 |
| `MISSING_SOURCE_SHA256` | 账里的 fact 没记来源哈希 | 用 `fact add` 重记，别手写 |
| `MANIFEST_HASH_MISMATCH` | 清单里的哈希与文件现值不符 | 同上：先确认改动是不是你要的 |
| `MANIFEST_UNSIGNED` | 清单没有 `signed_by` | 填名字和时间；没人签的清单不算锚 |
| `REQUIRED_EVIDENCE_MISSING` | `[evidence]` 说这节必须有某条 fact，正文里没有 | 补 `\fact{}`，或改 `[evidence]` 声明后重新冻结 |
| `EVIDENCE_DROPPED` | 冻结的清单里删掉了一条 | 不是有意删就加回来；有意删就 `evidence --unfreeze --reason "…"` 后重冻 |
| `INPUT_TARGET_MISSING` / `INPUT_DYNAMIC` | `\input` 的目标不存在，或用了宏/`#` 等静态解析不了 | 改成明确的文件路径；覆盖不了的目标工具不放过（fail-closed） |
| `EXPR_MISMATCH` | 派生事实的算式结果与 `value` 不一致 | 改 `value`、改 `expr`，或明确容差 |

## 二、看完可以暂缓（黄 / 提示）

| 错误码 | 它在说什么 | 建议 |
|---|---|---|
| `UNBOUND_NUMBER` | 数字能回到账，但没写 `\fact{ID}` | 补绑定；顺手确认绑的是不是对的那条 |
| `UNUSED_BIB` | bib 有条目没被引用 | 删掉，或经人签登记进 `bib_allow_unused` |
| `VALUE_NOT_IN_SOURCE` | fact 的 `value` 在 `source` 里找不到 | 查 `locator`；可能是转录时抄错了 |
| `NO_MANIFEST` / `UNSIGNED_RESULT` | 没有清单 / `results/` 下有文件没签 | 补签；这是「弱证据」，不是造假 |
| `LOW_BINDING_RATE` | 绑定率低于 50% | 看是不是账本膨胀、正文大量数字没绑 |
| `DUPLICATE_VALUE` | 同一个数值挂在多条 claim 上 | 合并事实，或人签 `dup_ok` |
| `UNUSED_FACT` | 账上有、正文没用（提示级） | 删除或合并；不影响退出码 |
| `FIGURE_UNVERIFIED` | 图里的数字没有随图 `.csv` | 补 csv，或接受「图未核验」 |
| 文风码（`HEADING_ECHO`、`PARAGRAPH_TEMPLATE` 等） | 表达公式化，不阻断 | 用 `prescribe --for <码>` 看改法，最后一次集中改 |

## 三、可以不管

| 项 | 为什么 |
|---|---|
| `RHYTHM_PLATEAU`、`NUMERAL_DENSITY` | 提示级（info），不参与红黄统计 |
| `TERM_UNREGISTERED` | 默认关闭，只有加 `--report-unregistered` 才出现 |
| 文风黄牌本身 | 它是改写建议，不是事实错误；`--strict` 下才当红 |

## 四、CI 里怎么用

```bash
python3 -m factscribe audit . --strict   # 黄也当红：未核验不许过
```

日常改稿别加 `--strict`，否则会被文风黄牌淹没；发布前再加。

## 五、还是红着，按这个顺序排查

1. `factscribe doctor .` —— 环境或项目结构缺东西；
2. `factscribe check .` —— 账本身坏没坏（id、哈希、清单、算式）；
3. `factscribe audit .` —— 账与正文对不对得上；
4. 单条红看 `prescribe --for <错误码>` —— 有没有现成改法。

每一步都只回答一个问题，别跳步。
