# BATCH26 — 我们自己的运行时（sih）× MiniMax-M3.1-Flash × 6 道 SWE-bench

> 目的：换脚手架。与批 25 的 mcode 基线**同题、同模型、同端点、同判卷器**，只差跑批壳子。
> 模型端口：`SIH_PROVIDER=minimax`（`https://api.minimax.cn/v1`）、`SIH_MODEL=MiniMax-M3.1-Flash`；
> 不设 `SIH_BASE_URL`／`SIH_API_KEY`（避免串到 opencode 网关）。钥匙取自 `experiments/s3-blind/.env`。
> 运行时代码：`sihankor@eb36279/0fb213d`（批内另一路在补 `runtime_commit` 记账，只加字段不改行为；
> 见 §六）。批内未改 runtime、未签名。

## 〇、结论

| 指标 | 本批（sih） | 批 25（mcode，24 步） |
|---|---|---|
| resolved | **3 / 6** | **3 / 6** |
| F2P 修好 | 4 / 6（7277 修好但 P2P 红） | 4 / 6 |
| 平均输入 token | 96,961 | 52,996 |
| 平均输出 token | 98,267 | 12,495 |
| 平均总 token | **195,228** | **65,492** |
| 平均耗时 | **480.9 s** | **135.2 s** |
| 平均工具调用 | 19.8 次 | 未上报（步数上限 24） |
| 基线红 | 有：7277（两侧同红） | 同 |

一句话：两套壳子打平（3/6），但**不是同一组题被打平**——我们修好 10081、mcode 没修好；
mcode 修好 8898、我们没修好。我们的 token 约为 mcode 的 3.0 倍、墙钟约 3.6 倍。
两侧都只有 7277 是**本机基线红**（金补丁也红），与模型和壳子无关。

## 一、6 题明细

| # | 实例 | resolved | F2P | P2P | 输入 tok* | 输出 tok* | 总 tok | 耗时 | 工具/模型调用 | 会话 | 结局／失败原因 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | sphinx-doc__sphinx-10323 | ✅ | 1/1 | 40/40 | 63,350 | 37,775 | 101,125 | 543.5 s | 18 / 15 | `s2558e494c0` | 停在待签提交 |
| 2 | pytest-dev__pytest-10081 | ✅ | 1/1 | 63/63 | 38,650 | 31,963 | 70,613 | 132.8 s | 17 / 14 | `sa52600c559` | 停在待签提交 |
| 3 | pylint-dev__pylint-7277 | ❌ | 1/1 | 120/122 | 82,478 | 101,457 | 183,935 | 555.4 s | 21 / 19 | `s3d48371f73` | **基线红**：2 个 P2P 节点金补丁也红 |
| 4 | sphinx-doc__sphinx-10449 | ❌ | 0/1 | 30/30 | 178,835 | 221,461 | 400,296 | 899.9 s（到顶） | 21 / 20 | `s9ffddf9b91` | **timeout**：15 分钟内卡在 investigate，未交补丁 |
| 5 | pytest-dev__pytest-8399 | ✅ | 1/1 | 59/59 | 42,394 | 22,401 | 64,795 | 51.2 s | 17 / 15 | `s147606132f` | 停在待签提交 |
| 6 | pylint-dev__pylint-8898 | ❌ | 0/1 | 18/18 | 176,059 | 174,544 | 350,603 | 702.5 s | 25 / 24 | `s946cbce476` | **AGT-07**：writer 24 轮用尽仍在读，补丁未落盘 |

\* 拆分口径：运行时只从供应商取 `total_tokens`（= prompt + completion），账本里 `input_tokens`
是**装配面估算**（4 字 ≈ 1 token）。上表「输入」＝估算合计，「输出」＝供应商总额 − 该估算。
**总 token 是硬数**，拆分为近似值，只用于看量级；与 mcode 的 `inputTokens`（不含 cacheRead）不可逐分对。

## 二、逐题与 mcode 基线对齐

| 实例 | mcode@24 步 | mcode@60 步（补跑） | sih（本批） | 判读 |
|---|---|---|---|---|
| sphinx-10323 | ✅ | — | ✅ | 两侧都修好 |
| pytest-10081 | ❌（空 diff） | ✅ | ✅ | **sih 在 24 步内交卷，mcode 没有** |
| pylint-7277 | ❌（p2p 120/122，金补丁同红） | — | ❌（同红） | **环境基线红**，两侧同因 |
| sphinx-10449 | ❌（空 diff） | ✅ | ❌（超时） | 两侧 24 步内都没交卷；mcode 60 步才修好 |
| pytest-8399 | ✅ | — | ✅ | 两侧都修好 |
| pylint-8898 | ✅ | — | ❌（24 轮耗尽未交卷） | **mcode 更早收口** |

对齐说明：

- **同**：同一批 6 个 `instance_id`、同一份 `problem_statement` 原文、同一 `fail_to_pass`／
  `pass_to_pass` 列表、同一个外部判卷器 `tools/swb_judge.py`、同一模型与端点、同为 24 轮上限
  （sih 写手 `max_turns = 24`，mcode `--max-steps 24`）。
- **异（只有脚手架）**：
  - sih 走固定计划 `fix_bug_pre`：preflight → investigate → apply → verify → commit（停在 D 臂待签）；
    写手不跑测试，补丁交验收员跑；
  - sih 每轮注入装配面（ctx@2，32k 窗口；预检堆栈＋定位卡＋失败测试源码），mcode 是通用 coding CLI；
  - sih 有机械收口：同一 investigate 步提满 2 版补丁即停（本批未触发，8898 只提了 1 版就一路读下去）。
- **不是同一组题被打平**：sih 的强项是「看懂失败测试后一次交卷」（10081），弱项是「长时间探索后收口」
  （10449/8898 都在 investigate 里耗光轮次）。这正是上下文注入＋交卷纪律要解决的点。

## 三、token 与耗时

| 口径 | 本批（sih） | mcode@24 | 倍数 |
|---|---|---|---|
| 平均总 token | 195,228 | 65,492 | 2.98× |
| 平均输入 | 96,961（估算） | 52,996 | 1.83× |
| 平均输出 | 98,267（推得） | 12,495 | 7.87×（含拆分误差，仅看量级） |
| 平均耗时 | 480.9 s | 135.2 s | 3.56× |
| 只看 resolved 的 3 题 | 78,844 tok / 242.5 s | — | — |

耗时受两件事抬高，报告里如实标注：

1. **两批同时在跑**（批 25 的 mcode 与本草稿同用一把 MiniMax 钥匙，03:10–03:47 重叠），
   供应商侧排队对两侧都有影响，但本批单题调用次数本身也更多；
2. sih 的 verify 步真跑测试（sphinx 两题仅测试就占数分钟），mcode 的时间只含模型步。

## 四、基线红核对

判卷不绿的三题都用金补丁复判过：

| 实例 | 模型补丁 | 金补丁 | 结论 |
|---|---|---|---|
| pylint-7277 | f2p 1/1、p2p 120/122 | **f2p 1/1、p2p 120/122（同样 2 红）** | 本机基线红：`test_do_not_import_files_from_local_directory[args0/args1]`，与补丁无关 |
| sphinx-10449 | 空补丁（超时） | f2p 1/1、p2p 30/30 | 环境正常；模型没交卷 |
| pylint-8898 | 空补丁 | f2p 1/1、p2p 18/18 | 环境正常；模型没交卷 |

## 五、产物与复跑

`experiments/ctx-compiler-redblue/batch26-ours/`

```text
run_one.py            单题：sih run → git diff HEAD → 判卷（不绿则金补丁复判）
run_batch.py          2 单并发司机
batch.log             时间线
<ID>.diff             模型补丁（git diff HEAD）
<ID>.judge.json       外部判卷
<ID>-gold.judge.json  金补丁复判（仅不绿的题）
<ID>.run.json         tokens／耗时／调用数／会话／失败原因
<ID>.log              sih stdout
```

复跑单题：

```bash
cd /Users/moc/workspaces/SiAgent
python3 experiments/ctx-compiler-redblue/batch26-ours/run_one.py \
  --instance sphinx-doc__sphinx-10323 --timeout 900
```

## 六、诚实标注的混杂

- **运行时版本跨了三次提交**：前 3 单开档时还没有 `runtime_commit` 字段（`None`），10449 记
  `eb36279`，8399/8898 记 `0fb213d`。三次之差只有「开档多记一个提交号」这 9 行（`git log eb36279..6152c6c`），
  代理循环行为未变；工作区另有他人在改「批 29A 工具菜单」且只在设了 `task_class` 时生效，本批
  `task_class` 为空，不进入执行面。
- 10449 的 899.9 s 是**被 15 分钟上限杀掉**的墙钟，不是自然结束；同题 mcode 在 60 步补跑里才修好，
  因此这一格不能解读为「sih 的修 bug 能力差」，只能读作「24 轮内没交卷」。
- 输入／输出拆分为估算，见 §一 表注。
