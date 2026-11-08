# BATCH20 — SWE-bench Verified 真题 6 题 × 2 臂对照

> 数据集：SWE-bench Verified（`/tmp/swebench_verified.parquet`），6 题均为批 18 已验证「红→绿」。
> 模型：`deepseek-v4.1-flash`，`SIH_PLAN=fix_bug_pre`，`SIH_TEST_SELECTOR`＝该题 F2P，
> `SIH_TEST_PYTHON=/tmp/swb/envs/<id>/bin/python`；两臂唯一变量＝`--ctx`。
> 做题时间：2026-11-07 01:48–02:11。

## 〇、结论（先看结果）

- **开臂 resolved 4/6；不开臂 resolved 4/6。** 开臂少的两题是**上下文装配器拒装**（0 次模型调用，
  不是模型没修好）；不开臂少的两题是 1 题真没修好（sphinx-10449）＋ 1 题判卷环境问题
  （pylint-7277，F2P 已修好，但 2 个 P2P 节点在本机基线就红，金补丁同样红）。
- 有效样本里（排除 2 次装配拒装）：开臂 4/4；不开臂 4/6。
- 平均 token：开臂 **77,846**（含 2 个 0 token 的拒装单）／**116,769**（仅 4 个有效单）；
  不开臂 **84,690**（6 单全有效）。平均调用数：开臂 **11.0**（有效单 16.0）／不开臂 **15.7**。
- 事故：**无 429、无超时**。两起上下文装配拒装（CTX-02）已定位到根因，详见 §三。

## 一、6×2 对照表

| 实例 | 难度 | 臂 | resolved | F2P | P2P | tokens | 调用数 | 会话 |
|---|---|---|---|---|---|---|---|---|
| sphinx-doc__sphinx-10323 | <15 min | 开 | ✅ | 1/1 | 40/40 | 69,601 | 13 | s93f429c3af |
| sphinx-doc__sphinx-10323 | <15 min | 不开 | ✅ | 1/1 | 40/40 | 105,746 | 16 | s52aeb9cfa3 |
| pytest-dev__pytest-10081 | <15 min | 开 | ✅ | 1/1 | 63/63 | 92,755 | 17 | s55fdef136a |
| pytest-dev__pytest-10081 | <15 min | 不开 | ✅ | 1/1 | 63/63 | 98,752 | 16 | s18300cf620 |
| pylint-dev__pylint-7277 | <15 min | 开 | ❌² | 1/1 | 120/122 | 40,557 | 13 | s0a5c96569d |
| pylint-dev__pylint-7277 | <15 min | 不开 | ❌² | 1/1 | 120/122 | 50,826 | 14 | se8b451b996 |
| sphinx-doc__sphinx-10449 | <15 min | 开 | ✅ | 1/1 | 30/30 | 210,809 | 20 | s999075ec12 |
| sphinx-doc__sphinx-10449 | <15 min | 不开 | ❌ | 0/1 | 30/30 | 104,199 | 15 | s9d5dc34ca3 |
| pytest-dev__pytest-8399 | 15 min-1h | 开 | ✅ | 1/1 | 59/59 | 75,813 | 17 | s4b0264eec |
| pytest-dev__pytest-8399 | 15 min-1h | 不开 | ✅ | 1/1 | 59/59 | 53,516 | 16 | s0a1f54619c |
| pylint-dev__pylint-8898 | 1-4h | 开 | ✅ | 1/1 | 18/18 | 93,911 | 14 | s88d9cf2e2e |
| pylint-dev__pylint-8898 | 1-4h | 不开 | ✅ | 1/1 | 18/18 | 95,099 | 17 | sadab9c3abf |

¹ 上下文装配器 CTX-02 拒装，写手一步未跑（模型 0 调用、0 token）。空补丁送判卷得 F2P 0/1、P2P 120/122。
² F2P 已修好（1/1）；resolved=false 只因 2 个 P2P 节点红，而**金补丁判卷同样红**（同 2 节点），
   属本机判卷基线问题，不是模型修复引入的退化。
³ 同 ¹：CTX-02 拒装；空补丁判卷 F2P 0/1、P2P 59/59。

## 二、汇总

| 口径 | 开臂 | 不开臂 |
|---|---|---|
| resolved（全 6 单） | **4/6** | **4/6** |
| resolved（修 bug 后补跑，全部有效） | **5/6** | 4/6 |
| F2P 修好（不看基线红的 P2P） | **6/6** | 5/6 |
| 平均 token（全 6 单） | **77,846** | **84,690** |
| 平均 token（仅有效单） | **116,769**（n=4） | 84,690（n=6） |
| 平均调用数（全 6 单） | **11.0** | **15.7** |
| 平均调用数（仅有效单） | **16.0**（n=4） | 15.7（n=6） |

配对看（4 对有效样本）：

| 实例 | 开 token | 不开 token | 开调用 | 不开调用 |
|---|---|---|---|---|
| sphinx-10323 | 69,601 | 105,746 | 13 | 16 |
| pytest-10081 | 92,755 | 98,752 | 17 | 16 |
| sphinx-10449 | 210,809 | 104,199 | 20 | 15 |
| pylint-8898 | 93,911 | 95,099 | 14 | 17 |

开臂在 3/4 对里 token 更省；sphinx-10449 开臂多花了约 1 倍 token（20 次调用、310 秒），
但也是唯一一题「开臂修好、不开臂没修好」。

## 三、事故与异常（如实记录）

### 1. 管线文档的取 diff 命令取到空补丁（已绕过，不改 runtime）

`BATCH19-SWB-PIPELINE.md` §五第 4 步写 `git diff`，但 `apply_patch` 走 `git apply --index`，
模型改动是**已暂存**状态，纯 `git diff` 取到 0 字节。首单（sphinx-10323 开臂）因此把空补丁
送判卷，误判 resolved=false。改用 `git diff HEAD` 后重判为 **resolved=true（1/1、40/40）**。
本批所有 diff 均用 `git diff HEAD` 取；这是文档/取数口径问题，已在本目录 `run_one.py` 里注明。

### 2. 两起 CTX-02 上下文装配拒装（开臂，0 模型调用）

- `pylint-dev__pylint-7277` 开臂（会话 s00f3915691）
- `pytest-dev__pytest-8399` 开臂（会话 sd19df876fc）

报错原文：

```
装配器拒装：小节 test:<symbol> 的 content 不是 filtered_from 原文子串
（过滤只许取原文子集，不许编造；空白不算内容；CTX-05）
```

根因（已定位，未修）：`runtime/sihruntime/context.py` 的 `test_evidence_section()` 里
`text = str(evidence.get("text") or "").strip()` 会**去掉渲染文本末尾的空白**；而物件库里
该节原文是 JSON，末尾空白被转义保留在闭引号前。两题被选中的失败测试源码恰好以空白结尾
（7277 以 9 个空格结尾；8399 以 `\nE   ` 结尾），strip 后 `json.dumps(text)` 不再是原文子串，
装配器按 CTX-05 拒装。属**确定性 bug**，重跑同样会失败；写手一步未跑，不应计入「模型没修好」。
其余 4 个开臂实例的测试源码不以空白结尾，未触发。

### 3. pylint-7277 的 P2P 基线问题（不开臂）

不开臂补丁 F2P 1/1 通过，但 P2P 有 2 节点红：
`tests/test_self.py::TestRunTC::test_do_not_import_files_from_local_directory[args0]` 与 `[args1]`。
用**金补丁**重判，同样恰好这 2 个节点 FAILED（f2p 1/1、p2p 120/122）。说明不是模型改坏，
而是本机判卷环境/基线问题（该两例依赖本机 `sys.path` 形状）。故该单 resolved=false 不代表修复失败。

### 4. 429 / 超时

- 全批 **无 429**、**无单题超时**（最长 sphinx-10449 开臂 310 秒，阈值 720 秒）。
- 两臂之间均 sleep 20 秒；两臂使用同一 agents 文件、同预算、同题面（`instance.json.task` 原文）、同选择器。

## 四、产物

本目录：

- `<ID>-<arm>.diff`：会话工作区 `git diff HEAD`（模型补丁）
- `<ID>-<arm>.judge.json`：`swb_judge.py --json` 原始输出（F2P/P2P 逐节点）
- `<ID>-<arm>.run.json`：单次运行指标（tokens、调用数、会话、耗时、判卷摘要、失败原因）
- `<ID>-<arm>.log`：`sih run` 完整 stdout
- `run_one.py`：跑单题单臂的驱动（含 `git diff HEAD` 修正说明）
- `run_batch.sh` / `batch.log`：本批编排与总日志
- `summarize.py`：由 `*.run.json` 重算上表

会话根：`/tmp/swb/sih/.sessions/<sid>/`（账本 `ledger.ndjson`、工作区 `work/`）。


## 五、批 21 补跑（修掉 CTX-02 之后）

两单原本因装配拒装 0 调用，修好 `test_evidence_section` 的 `.strip()` 后重跑：

| 实例 | resolved | F2P | P2P | token | 调用 | 会话 |
|---|---|---|---|---|---|---|
| pylint-dev__pylint-7277（开） | ❌（基线红） | 1/1 | 120/122 | 40,557 | 13 | s0a5c96569d |
| pytest-dev__pytest-8399（开） | ✅ | 1/1 | 59/59 | 75,813 | 17 | s4b0264eec |

**最终 6×2**：开 **5/6**（F2P 6/6）｜不开 **4/6**（F2P 5/6）；token 均值 97.3k vs 84.7k；调用 15.5 vs 15.7。

唯一的真实差异是 `sphinx-10449`：开臂修好（210.8k），不开臂没修好（104.2k，F2P 0/1）——**这一单是上下文带来的收益，代价是两倍 token**。
