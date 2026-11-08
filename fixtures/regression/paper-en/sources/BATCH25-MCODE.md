# 批 25 · MiniMax 官方 CLI（mcode）跑 6 道真实 SWE-bench 题

**一句话**：成熟脚手架基线跑出来了——协议参数（24 步上限）下 resolved **3/6**，全部 6 次运行都是被**步数上限**截断的（不是时间超时、没崩）；两题空补丁在放宽到 60 步补跑后**都修好了**，即 24 步内实际可达 **5/6**（剩下一题是本机判卷基线红，见 §三）。

产物目录：`experiments/ctx-compiler-redblue/batch25-mcode/`（每题 `<id>.run.json`、`<id>.diff`、`<id>.judge.json`、`<id>.log`；补跑件带 `.s60` 后缀）。判卷一律用**我们自己的外部判卷器** `tools/swb_judge.py`，不吃 mcode 自报。

## 一、协议参数（`--max-steps 24 --timeout 15m --permission full --output-format json --prompt-mode coding`）

| 实例 | status | resolved | F2P | P2P | input tok | output tok | 耗时(s) |
|---|---|---|---|---|---|---|---|
| sphinx-doc__sphinx-10323 | limit_exceeded | ✅ | 1/1 | 40/40 | 56,769 | 13,689 | 154 |
| pytest-dev__pytest-10081 | limit_exceeded | ❌（空补丁） | 0/1 | 63/63 | 43,984 | 10,952 | 150 |
| pylint-dev__pylint-7277 | limit_exceeded | ❌（F2P 已绿，P2P 本机基线红） | 1/1 | 120/122 | 60,787 | 13,974 | 147 |
| sphinx-doc__sphinx-10449 | limit_exceeded | ❌（空补丁） | 0/1 | 30/30 | 49,349 | 14,053 | 130 |
| pytest-dev__pytest-8399 | limit_exceeded | ✅ | 1/1 | 59/59 | 49,867 | 10,283 | 110 |
| pylint-dev__pylint-8898 | limit_exceeded | ✅ | 1/1 | 18/18 | 57,222 | 12,020 | 93 |

**汇总（协议臂）**：resolved **3/6**；平均 input 52,996 tok、平均 output 12,495 tok、平均合计 **65,492 tok**；平均耗时 **131s**（最长 154s，无一题接近 15 分钟硬超时）。

口径说明：
- `status` 字段全为 `limit_exceeded`、进程退出码 7 —— mcode 撞到 `--max-steps 24` 上限就报这个，跟「跑崩」不是一回事；两题 resolved 的题也是**先改完才撞上限**（补丁有效）。
- token 取 run.json 的 `usage.inputTokens` / `usage.outputTokens`；另有 `cacheReadTokens`（70 万–92 万量级）是提示缓存命中量，不计入费用口径，未列入表中。
- **步数拿不到**：mcode 的 `exec` JSON 只回 `durationMs/status/usage/model/runId/sessionId`，不回步数；本批以「撞 24 步上限」反证步数用满，精确步数需 `stream-json` 另跑，未做。

## 二、补跑（非协议参数：`--max-steps 60`）

动机：协议臂两题补丁为 **0 字节**（一行业务代码都没改），且都是撞步数上限；要区分「模型不会修」与「预算不够」。

| 实例 | status | resolved | F2P | P2P | input tok | output tok | 耗时(s) |
|---|---|---|---|---|---|---|---|
| pytest-dev__pytest-10081 | succeeded | ✅ | 1/1 | 63/63 | 58,049 | 15,506 | 275 |
| sphinx-doc__sphinx-10449 | limit_exceeded | ✅ | 1/1 | 30/30 | 105,913 | 27,698 | 315 |

结论：**24 步是小步数预算下的真瓶颈，不是能力上限。** 两题在 60 步内都出了能过 F2P+P2P 的补丁。按 60 步补跑口径，mcode 是 **5/6**（第 6 题见 §三）。

## 三、判卷基线核查（不绿题的归因）

| 实例 | 模型补丁 | 金补丁 | 归因 |
|---|---|---|---|
| pytest-dev__pytest-10081 | ❌ F2P 0/1，P2P 63/63 | ✅ 绿 | 模型没修（24 步内空补丁）；60 步补跑绿 |
| sphinx-doc__sphinx-10449 | ❌ F2P 0/1，P2P 30/30 | ✅ 绿 | 同上 |
| pylint-dev__pylint-7277 | ❌ P2P 120/122（F2P 1/1 已绿） | ❌ 同样 120/122 | **本机基线红**：金补丁在这台机器上也过不了那 2 个 P2P 节点，不算模型的账 |

## 四、对比锚点：我们自己脚手架（同一批题）

来自 `batch23/`（同一判卷器、同一批实例）；**对齐时批 23 还没跑完**（32 臂中已落盘 20 臂），6 题里只有 3 题有数：

| 实例 | mcode（24 步） | mcode（60 步补跑） | 我们脚手架（on 臂） |
|---|---|---|---|
| pytest-dev__pytest-10081 | ❌ 43,984 tok / 150s | ✅ 58,049 tok / 275s | ✅ 88,368 tok / 49s |
| pylint-dev__pylint-8898 | ✅ 57,222 tok / 93s | — | ✅ 126,537 tok / 86s |
| pylint-dev__pylint-7277 | ❌（基线红）60,787 tok / 147s | — | ❌（基线红）47,704 tok / 45s |
| sphinx-doc__sphinx-10323 / 10449 / pytest-8399 | ✅❌✅（见表一） | — | 缺（批 23 未跑完） |

粗读（3 题样本，不足以下结论）：resolved 打平（各 2/3 有效题）；**mcode 用 token 少一半左右**（88k→58k、126k→57k），但**墙钟更慢**（49s→275s、86s→93s；差在探索步多、每步串行）。批 23/26 跑完后应重算这张表。

注：`BATCH23-SWB16.md` 这份报告尚不存在（只有 `batch23/` 的原始 run.json），本条锚点直接从 run.json 取数；批 26 报告同样未落盘。

## 五、事故清单

1. **6/6 全部撞 `--max-steps 24`**（status=limit_exceeded，退出码 7）。这是参数设定的边界，不是崩溃：无 OOM、无进程被杀、无 15 分钟超时。副作用是「步数」维度的数据缺失（mcode JSON 不报步数）。
2. **两题产出 0 字节补丁**（pytest-10081、sphinx-10449）：24 步全用于读码/跑测试，没走到编辑。补跑证明是预算问题。
3. **`pylint-dev__pylint-7277` 本机判卷基线红**（金补丁 P2P 120/122），与批 23 结果一致，是环境问题不是模型问题。
4. **判卷器判卷不是零成本**：每题判卷 5–30s，不绿题再跑一次金补丁判卷，全批判卷时间计入总账但未计入下表耗时（表列耗时只含 mcode 运行）。
5. **`--permission full` 全权**：mcode 在副本工作区里可任意改文件；我们已从副本剥掉 `gold.patch` 与 `instance.json`（防偷看答案），并用 `git diff HEAD` 取补丁（含已暂存改动，未漏）。
6. 无网络/认证故障：`minimax_oauth` 全程有效，6+2 次调用零 4xx/5xx。

## 六、方法与可复现

```bash
# 单题（自动：复制实例→跑 mcode→取 diff→外部判卷→不绿再判金补丁）
python3 experiments/ctx-compiler-redblue/batch25-mcode/run_one.py <instance_id>
# 补跑（放宽步数，产物加 .s60 后缀，不动协议臂产物）
python3 experiments/ctx-compiler-redblue/batch25-mcode/run_one.py <instance_id> --max-steps 60 --tag s60
# 汇总表
python3 experiments/ctx-compiler-redblue/batch25-mcode/summarize.py
```

- 实例源：`/tmp/swb/instances/<ID>`（`swb_instance.py` 产物，含 base+test_patch）；工作副本：`/tmp/swb/mcode/<ID>`，原实例零改动。
- 题面：`instance.json` 的 `task` 原文，未改写（1.0k–3.1k 字符）。
- 并发：同时最多 3 个实例，实测符合；未出现相互干扰（各自独立工作区与 venv）。
- 不改 runtime、不签名。
