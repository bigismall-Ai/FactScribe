# BATCH23 — SWE-bench Verified 16 题 × 2 臂对照

> 数据集：`/tmp/swebench_verified.parquet`（SWE-bench Verified），16 题全部取自批 18 已验证「红→绿」名单。
> 模型：`deepseek-v4.1-flash`（D 席）；`SIH_PLAN=fix_bug_pre`、`SIH_TEST_SELECTOR`＝该题 F2P（空格分隔）、
> `SIH_TEST_PYTHON=/tmp/swb/envs/<id>/bin/python`、`SIH_HTTP_RETRY=8`、端口 `opencode.ai/inference/go/openai/v1`。
> 两臂唯一变量＝`--ctx`。题面＝`instance.json.task`（`problem_statement` 原文，不改写不加提示）。
> 做题时间：2026-11-07 02:59–03:55（32 单全部跑完，无重跑）。

## 〇、结论（先看结果）

- **开臂 resolved 10/16，不开臂 5/16。** 差异全在「开臂修好、不开臂没修好」的 5 单上
  （pylint-4970、pylint-8898、pytest-10081、sphinx-10449、sphinx-10673），**反方向 0 单**。
  符号检验 p≈0.031。
- 扣掉本机基线红的 2 单（pylint-6528、pylint-7277，金补丁同样 resolved=false）：
  **开 10/14，不开 5/14**；F2P 修好 **10/14 vs 6/14**。
- token：开臂均值 **90,431**／中位 **85,928**，不开臂均值 **96,184**／中位 **95,655**——开臂平均省 6%，
  但配对看只有 9/16 单更省（不是全面更省）。调用数 **14.8 vs 15.6**。
- 事故：**无 429、无超时、无上下文装配拒装**（批 21 修掉的 CTX-02 在本批 16 个开臂全数通过）。
  金补丁基线里 sphinx-10435 出现一次**单节点抖动**（`test_latex_images`），复跑即绿，不算基线红。

## 一、16×2 总表

| 实例 | 难度 | 臂 | resolved | F2P | P2P | token | 调用 | 备注 |
|---|---|---|---|---|---|---|---|---|
| pallets__flask-5014 | <15 min | 开 | ✅ | 1/1 | 59/59 | 26,286 | 13 | — |
| pallets__flask-5014 | <15 min | 不开 | ✅ | 1/1 | 59/59 | 53,271 | 16 | — |
| psf__requests-6028 | 15 min-1h | 开 | ❌ | 0/2 | 185/185 | 82,105 | 16 | F2P 未修好 |
| psf__requests-6028 | 15 min-1h | 不开 | ❌ | 0/2 | 185/185 | 64,375 | 11 | F2P 未修好 |
| pylint-dev__pylint-4970 | <15 min | 开 | ✅ | 1/1 | 17/17 | 63,727 | 12 | — |
| pylint-dev__pylint-4970 | <15 min | 不开 | ❌ | 0/1 | 17/17 | 92,683 | 15 | F2P 未修好 |
| pylint-dev__pylint-6528 | 15 min-1h | 开 | ❌ | 0/4 | 169/171 | 136,118 | 17 | 基线红（金补丁同红 2 个 P2P）＋F2P 未修好 |
| pylint-dev__pylint-6528 | 15 min-1h | 不开 | ❌ | 0/4 | 169/171 | 147,369 | 18 | 同上 |
| pylint-dev__pylint-7277 | <15 min | 开 | ❌ | 0/1 | 120/122 | 47,704 | 13 | 基线红＋空补丁（模型自撤回） |
| pylint-dev__pylint-7277 | <15 min | 不开 | ❌ | 1/1 | 120/122 | 45,560 | 15 | 基线红（F2P 其实已修好） |
| pylint-dev__pylint-8898 | 1-4h | 开 | ✅ | 1/1 | 18/18 | 126,537 | 18 | — |
| pylint-dev__pylint-8898 | 1-4h | 不开 | ❌ | 0/1 | 18/18 | 98,627 | 16 | F2P 未修好 |
| pytest-dev__pytest-10051 | 15 min-1h | 开 | ❌ | 0/1 | 14/15 | 56,742 | 13 | F2P 未修好＋P2P 退化 1 |
| pytest-dev__pytest-10051 | 15 min-1h | 不开 | ❌ | 0/1 | 14/15 | 76,973 | 14 | F2P 未修好＋P2P 退化 1 |
| pytest-dev__pytest-10081 | <15 min | 开 | ✅ | 1/1 | 63/63 | 88,368 | 16 | — |
| pytest-dev__pytest-10081 | <15 min | 不开 | ❌ | 1/1 | 62/63 | 80,854 | 16 | P2P 退化 1（F2P 已修好） |
| pytest-dev__pytest-10356 | 1-4h | 开 | ❌ | 0/1 | 0/79 | 116,106 | 14 | 补丁传了不存在的 `consider_mro` 参数→收集期全崩 |
| pytest-dev__pytest-10356 | 1-4h | 不开 | ❌ | 0/1 | 79/79 | 119,415 | 16 | F2P 未修好（P2P 全绿） |
| pytest-dev__pytest-7982 | <15 min | 开 | ✅ | 1/1 | 78/78 | 28,477 | 12 | — |
| pytest-dev__pytest-7982 | <15 min | 不开 | ✅ | 1/1 | 78/78 | 63,349 | 16 | — |
| pytest-dev__pytest-8399 | 15 min-1h | 开 | ✅ | 1/1 | 59/59 | 83,489 | 13 | — |
| pytest-dev__pytest-8399 | 15 min-1h | 不开 | ✅ | 1/1 | 59/59 | 83,886 | 18 | — |
| sphinx-doc__sphinx-10323 | <15 min | 开 | ✅ | 1/1 | 40/40 | 100,485 | 15 | — |
| sphinx-doc__sphinx-10323 | <15 min | 不开 | ✅ | 1/1 | 40/40 | 105,737 | 16 | — |
| sphinx-doc__sphinx-10435 | <15 min | 开 | ✅ | 1/1 | 74/74 | 64,677 | 13 | — |
| sphinx-doc__sphinx-10435 | <15 min | 不开 | ✅ | 1/1 | 74/74 | 130,547 | 17 | — |
| sphinx-doc__sphinx-10449 | <15 min | 开 | ✅ | 1/1 | 30/30 | 119,770 | 16 | — |
| sphinx-doc__sphinx-10449 | <15 min | 不开 | ❌ | 0/1 | 23/30 | 110,119 | 15 | F2P 未修好＋P2P 退化 7 |
| sphinx-doc__sphinx-10614 | 15 min-1h | 开 | ❌ | 0/1 | 5/5 | 169,853 | 18 | F2P 未修好 |
| sphinx-doc__sphinx-10614 | 15 min-1h | 不开 | ❌ | 0/1 | 5/5 | 153,599 | 16 | F2P 未修好 |
| sphinx-doc__sphinx-10673 | 15 min-1h | 开 | ✅ | 1/1 | 9/9 | 136,456 | 18 | — |
| sphinx-doc__sphinx-10673 | 15 min-1h | 不开 | ❌ | 0/1 | 9/9 | 112,573 | 15 | F2P 未修好 |

会话 id 与耗时（同序）：

| 实例 | 开 会话/耗时 | 不开 会话/耗时 |
|---|---|---|
| pallets__flask-5014 | s8aae8e12f7 / 35s | sc60ebe46a3 / 48s |
| psf__requests-6028 | sb9203efc36 / 95s | s98b1706e40 / 109s |
| pylint-dev__pylint-4970 | s2fb3640c75 / 41s | s89688c9f03 / 53s |
| pylint-dev__pylint-6528 | s2b401b025e / 136s | sd4ba9648e0 / 63s |
| pylint-dev__pylint-7277 | s5c2b7f0927 / 45s | s800ee87bfb / 54s |
| pylint-dev__pylint-8898 | sd3815cc957 / 86s | sd1301fc41b / 100s |
| pytest-dev__pytest-10051 | s24ef0d6c6b / 43s | sbb59997890 / 44s |
| pytest-dev__pytest-10081 | s4abc254361 / 49s | s37cd6e19b4 / 45s |
| pytest-dev__pytest-10356 | sa2d39efea1 / 90s | s02e069b7d7 / 55s |
| pytest-dev__pytest-7982 | s2dfe534c19 / 33s | s1c9ba0d146 / 36s |
| pytest-dev__pytest-8399 | s070f8104e6 / 61s | s5d8719a0b9 / 65s |
| sphinx-doc__sphinx-10323 | s9b0614d006 / 52s | s571819a84a / 55s |
| sphinx-doc__sphinx-10435 | s06fb9e6d6d / 72s | se8e4d1fffe / 150s |
| sphinx-doc__sphinx-10449 | s8cd0c598f0 / 112s | s067b676361 / 48s |
| sphinx-doc__sphinx-10614 | s81e44cfdf8 / 201s | s6c6d2f8dea / 189s |
| sphinx-doc__sphinx-10673 | sff4ba5bf81 / 125s | s22fb37128f / 134s |

## 二、汇总

| 口径 | 开臂 | 不开臂 |
|---|---|---|
| resolved（全 16） | **10/16** | **5/16** |
| resolved（排除 2 单基线红，n=14） | **10/14** | **5/14** |
| F2P 修好（全 16） | 10/16 | 7/16 |
| F2P 修好（排除 2 单基线红，n=14） | **10/14** | **6/14** |
| token 均值（n=16） | **90,431** | **96,184** |
| token 中位（n=16） | **85,928** | **95,655** |
| 调用均值（n=16） | **14.8** | **15.6** |
| 耗时均值／中位 | 80s／67s | 78s／55s |
| 总 token | 1,446,900 | 1,538,937 |

配对视角（16 对）：

- token：开臂更省 **9/16** 对，更贵 7/16 对；合计省 92,037 token（全批 2,985,837）。
- 结果：5 对**开成不开败**（pylint-4970、pylint-8898、pytest-10081、sphinx-10449、sphinx-10673），
  **0 对开败不开成**，其余 11 对同结果。
- 两臂都失败的 6 单里，4 单是「模型没修好」（requests-6028、pytest-10051、pytest-10356、sphinx-10614），
  2 单是基线红（pylint-6528、pylint-7277）。

## 三、按难度分层（排除 2 单基线红）

| 难度 | 题数 | 开 resolved | 不开 resolved | 开 token 均值 | 不开 token 均值 |
|---|---|---|---|---|---|
| <15 min | 7 | **7/7** | 4/7 | 70,256 | 90,937 |
| 15 min-1h | 5 | **2/5** | 1/5 | 105,729 | 98,281 |
| 1-4h | 2 | **1/2** | 0/2 | 121,322 | 109,021 |

读法：**难度越高、上下文收益越明显但绝对成功率越低**。简单档（<15 min）开臂 7/7 全清，且 token 反而省 23%；
中档两臂都吃力（2/5 vs 1/5），开臂还更贵；最难档只有 pylint-8898 靠开臂拿下（126,537 token），
pytest-10356 两臂都没修好（开臂的补丁还写错 API 把 P2P 全打红）。

## 四、事故清单

### 1. 无传输事故

全批 32 单：**0 次 429、0 次网络重试、0 次超时**（最长单 sphinx-10614 开臂 201 秒，阈值 900 秒）。
所有非零退出码都是 `AGT-08 验收未过（门或证据不是 pass）`，与外部判卷结论一致。

### 2. 无上下文装配拒装（批 21 的修复成立）

16 个开臂全部正常装配（`ctx_schema=ctx@2`、`ctx_profile=long_horizon_bugfix`），
批 20 的 CTX-02（测试源码以空白结尾导致 CTX-05 子串校验拒装）本批 **0 次复现**。

### 3. 金补丁基线：2 单稳定红、1 单抖动

| 实例 | 金补丁 F2P | 金补丁 P2P | 判定 |
|---|---|---|---|
| pylint-dev__pylint-6528 | 4/4 | 169/171 | **稳定基线红**（复跑同 2 节点） |
| pylint-dev__pylint-7277 | 1/1 | 120/122 | **稳定基线红**（同批 20 结论） |
| sphinx-doc__sphinx-10435 | 1/1 | 73/74 → 复跑 74/74 | **抖动**，非基线红 |

两单稳定红是同一对节点：`tests/test_self.py::TestRunTC::test_do_not_import_files_from_local_directory`
与 `..._with_pythonpath`——依赖本机 `sys.path` 形状，与模型改动无关。
sphinx-10435 第一次金补丁判卷 `tests/test_build_latex.py::test_latex_images` FAILED，复跑即绿，
两支模型臂也都 74/74 全绿：记为本机判卷**单节点抖动**，不扣分。

### 4. pylint-7277 开臂产出空补丁（模型自撤回，不是取补丁 bug）

账本 `s5c2b7f0927` 实录：模型两次 `propose_patch`——第一版真的改了 `pylint/__init__.py`
（`new_sha=f38a486…`），第二版把内容**改回原文**（`new_sha=ef00ba3…`＝原 sha、`changed=false`）；
随后 `AGT-07`「本步补丁版数到顶（2）」机械收口，**按最后一版（＝原文）交验收** → 落盘 0 字节。
`git diff HEAD` 取到 0 字节是**正确**结果（工作树确实干净），已核实无已暂存残留。
属模型行为，非管线缺陷；但暴露一条值得记的机制风险：**版本上限收口取「最后一版」，
模型最后一版是撤回时，等于把已做好的修复丢掉**。

### 5. pytest-10356 开臂把 79 个 P2P 全打红（模型幻觉 API）

补丁写 `get_unpacked_marks(obj, consider_mro=False)`，而该版本函数签名只有 `obj`
（`src/_pytest/mark/structures.py:358`），`TypeError` 发生在收集期 → 79 个节点全部 `MISSING`。
纯模型错误（同一题不开臂的补丁 P2P 79/79 全绿）。

### 6. 其余失败均为「模型没修好」的常规失败

- `psf__requests-6028`：两臂都只改了 `rebuild_proxies` 的 `if username and password` → `if username`，
  没覆盖该题真正要的 `prepend_scheme_if_needed`，F2P 0/2。
- `pytest-dev__pytest-10051`：开臂改 `records.clear()`、不开臂调不存在的 `handler.clear()`，
  两臂都既没修好 F2P 又各打红 1 个 P2P。
- `sphinx-10449` 不开臂：改了 `typehints.py` 但 `suppress_rtype` 传参方向错，F2P 0/1 且打红 7 个 P2P。
- `sphinx-10614`：两臂都没命中 `inheritance_diagram` 的渲染路径，F2P 0/1（P2P 5/5 未退化）。

## 五、产物

`experiments/ctx-compiler-redblue/batch23/`：

- `<ID>-<arm>.diff`：会话工作区 `git diff HEAD`（模型补丁）
- `<ID>-<arm>.judge.json`：`swb_judge.py --json` 原始输出（F2P/P2P 逐节点）
- `<ID>-<arm>.run.json`：单次运行指标（token、调用、会话、耗时、判卷摘要、失败原因）
- `<ID>-<arm>.log`：`sih run` 完整 stdout
- `<ID>-gold.judge.json` / `gold-baseline.log`：金补丁基线判卷（先跑，用于区分「没修好」与「基线红」）
- `ids.txt`／`run_one.py`／`run_batch.sh`／`summarize.py`／`batch.log`：题目清单、单题驱动、编排、汇总
- 会话根：`/tmp/swb/sih/.sessions/<sid>/`（账本 `ledger.ndjson`、工作区 `work/`）

复算：`python3 summarize.py`（由 `*.run.json` 重算上表）。
