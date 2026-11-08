# 批 30：τ²-bench 正式适配器与首批实测（retail 10 题 + mock 5 题）

日期：2026-11-07 ｜ 实施：D 席（opencode / DeepSeek-4.1-Flash 子代理）
落位：`experiments/tau2-lab/bridge/`（**未改** `sihankor/` 与 `tau2-bench/` 一行）
时间盒：3 小时

**一句话结论**：适配器跑通，retail 前 10 题我们 **0.900** vs tau2 原装 `llm_agent` 同模型 **0.800**（10 题里我们 9 对、它 8 对）；差距不在分数，而在**成本**——我们每题多烧约 **18% token**（主要是 system 里的工具目录＋章程），另外 mock 暴露一个真实弱点：会“好心”给工具参数补字段，被 DB 哈希判错。样本小且题目重复，**不能据此说我们更强**。

---

## 一、交付物与跑法

| 件 | 作用 | 行数 |
|---|---|---|
| `bridge/sih_agent.py` | 正式适配器（`SihAgent(HalfDuplexAgent)`＋`SihChatPort`） | 326 |
| `bridge/run_batch.py` | 直接调 `run_single_task` 的跑批器（子进程隔离、并发 ≤2、单题 600s 超时） | 263 |
| `bridge/analyze.py` | 读 `results/raw/*.summary.json` 出对照表 | 89 |
| `bridge/results/` | 原始结果、单题摘要、哈希链账本、批日志 | — |

跑法（key 只从 `experiments/s3-blind/.env` 读进环境变量，不落盘）：

```bash
cd experiments/tau2-lab/tau2-bench
source ../../s3-blind/.env
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  OPENAI_API_KEY="$MINIMAX_API_KEY" MINIMAX_API_KEY="$MINIMAX_API_KEY" \
  .venv/bin/python ../bridge/run_batch.py --arm both --task-ids 0-9 --concurrency 2
```

模型：`openai/MiniMax-M3.1-Flash`（`https://api.minimax.cn/v1`），agent 与用户模拟器同模型，temperature 0，`max_steps=60`，seed 42，单次 trial。
两臂：`sih`＝我们的适配器；`reference`＝tau2 自带 `llm_agent`（同模型、同判官），不是榜单上的 GPT-4.1 参考。

---

## 二、适配器结构（关键函数＋行号）

| 位置 | 干什么 |
|---|---|
| `CHARTER` `sih_agent.py:57-71` | 章程＋8 条机械纪律（一轮一事、先问目标、写前确认、不编参数、按政策拒绝等） |
| `SihChatPort.__init__` `:83-91` | 剥掉 litellm 的 `openai/` 前缀，直连 OpenAI 兼容端点 |
| `SihChatPort.complete` `:93-123` | **工具表走批 29A 通道**；HTTP 走我们的 `_http_json`（429/5xx 退避） |
| `SihAgent._tool_catalog` `:155-168` | 从 `tool.openai_schema` 生成人读工具清单（名字/参数/说明） |
| `SihAgent._assemble` `:170-190` | 章程＋`domain_policy` 原文＋工具清单；算 4 个指纹与规模 |
| `SihAgent.get_init_state` `:192-202` | 装配上下文，初始化状态，写 `context.assembled` 账 |
| `SihAgent.generate_next_message` `:204-276` | 收一条 tau2 消息 → 映射全历史 → 调模型 → 映射回 `AssistantMessage`；调用前后各写一条账 |
| `_to_openai_history` `:278-290` | 处理历史里的 `SystemMessage`（并入 system 区） |
| `_to_openai` `:292-314` | tau2 `Message` ↔ OpenAI messages：user 文本 / assistant 文本 / assistant tool_calls / tool 结果 |
| `factory` `:317-325` | tau2 registry 工厂，任务号与账本路径在**调用时**读环境 |

**历史交错**：assistant 带 tool_calls 时只发 `tool_calls`（content=None），工具结果按 `tool_call_id` 逐条展开；`MultiToolMessage` 先摊平成多条 `ToolMessage`（批 28 踩过的坑，已沿用）。
**输出约束**：模型若同时回文本和工具调用，我们丢掉文本只发工具调用（tau2 会拒绝混合消息）；空回复兜底成一句问句。
**账本**：每次模型调用前 `model.requested`（turn、消息数、工具名、renderer_version），后 `model.responded`（action、工具名、prompt/completion tokens、耗时、body_hash）；失败写 `model.failed`。工具执行**不写账**，仍归 tau2，避免双写。15 本该账全部通过哈希链校验。

### 用了批 29-A 的哪个能力

`SihChatPort.complete` 把 `[tool.openai_schema for tool in tools]`（retail 16 张、mock 4 张，**零写死**）塞进
`sih_providers.render_request({..., "tool_specs": [...]})`（`sihankor/runtime/sihruntime/providers.py:395-401`）——
这是批 29A 的“外部工具表原样发出”分支：不查白名单、不并内置表、空表就是不工具。
HTTP 传输与重试复用同文件 `_http_json`（`:530-568`），不另造轮子。
**没有**用 `Engine`，也没有改 `sihankor/` 任何一行（`git -C sihankor status` 里的改动是批 29A 的既有工作树，不是本批新增）。

---

## 三、retail 前 10 题结果

| task | reward(我们) | reward(reference) | token(我们) | token(ref) | 轮数(我们/ref) | 工具调用(我们/ref) | 备注 |
|---|---|---|---|---|---|---|---|
| 0 | **1.0** | 1.0 | 123,885 | 119,723 | 7 / 8 | 11 / 7 | 换货，同分 |
| 1 | **1.0** | 1.0 | 140,246 | 116,702 | 7 / 8 | 9 / 8 | 同上场景变体 |
| 2 | **1.0** | 1.0 | 126,570 | 103,588 | 4 / 4 | 11 / 10 | 有 NL 断言（判官＝MiniMax） |
| 3 | **1.0** | 1.0 | 139,120 | 102,398 | 5 / 4 | 11 / 10 | 同上 |
| 4 | **1.0** | 1.0 | 170,219 | 77,713 | 6 / 5 | 13 / 11 | 同上（我们 token 最高） |
| 5 | 0.0 | 0.0 | 128,112 | 167,804 | 6 / 7 | 9 / 12 | **双方都错**：条件式确认脚本 |
| 6 | **1.0** | 0.0 | 136,587 | 113,008 | 5 / 6 | 11 / 9 | 我们一次确认→只换台灯，正好命中 gold |
| 7 | **1.0** | 1.0 | 127,960 | 96,989 | 6 / 5 | 9 / 10 | — |
| 8 | **1.0** | 1.0 | 128,984 | 115,836 | 6 / 6 | 9 / 9 | — |
| 9 | **1.0** | 1.0 | 113,892 | 122,258 | 5 / 6 | 9 / 10 | 用户中途改主意，我们跟住了 |

| 指标（均值，n=10） | 我们 | reference | 差 |
|---|---|---|---|
| **reward** | **0.900**（9/10 全对） | **0.800**（8/10 全对） | +0.10（1 题，噪声级） |
| token 合计 | **133,558** | 113,602 | **+17.6%** |
| ├ 输入 | 122,623 | 101,574 | +20.7% |
| └ 输出 | 2,551 | 2,750 | −7.2% |
| 每次 agent 调用输入 token | 21,513 | 17,216 | +25.0% |
| 轮数（agent LLM 调用） | 5.7 | 5.9 | −0.2 |
| 工具调用 | 10.2 | 9.6 | +0.6 |
| 耗时 | 35.2 s | 31.5 s | +11.7% |

**两个失败/分差的真实原因**：

- **task 5（双方 0）**：脚本是“若 agent 要确认→只换台灯；若要**第二次**确认→改为退水壶”。gold 终态是“退水壶”。双方都只确认了一次、按客户当轮说法换了台灯 → DB 与 gold 不符。**不是调错工具，也不是违规**，是基准的条件式对话脚本要求“再问一次”，而我们和 reference 都没问第二次。
- **task 6（我们 1、它 0）**：gold 是“只换台灯”。我们问了一次确认、客户也说只换台灯 → 命中；reference 的客户模拟器当轮说“两个都办”，它就换了两个 → DB 不符。用户模拟器同一剧本两次跑法不同，**这一分是随机性送的**，不算能力优势。

**失败归类（按“是政策/问清问题，还是调错工具”）**：

| 失分件 | 归类 | 明细 |
|---|---|---|
| 我们 retail task 5 | **对话策略**（不是调错工具、不是违反政策） | 确认只做了一次；脚本要求第二次确认才转“退水壶” |
| reference retail task 5 | 同上 | 同因，且它最后还多做了“退水壶＋转人工”，终态更偏 |
| reference retail task 6 | **没跟住用户改口** | 客户说“两个都办”，它照办；gold 只换台灯 |
| 我们 mock create_task_1_with_env_assertions | **调错参数**（工具对、参数多余） | 多传 `description`，终态哈希不符 |
| 我们 mock update_task_1 | **非 agent 责任** | 用户模拟器自己 dismiss 通知，改了 user DB |

本批 **没有**出现“该拒绝却硬办 / 该查政策不查”的政策违反型失败。

---

## 四、加跑 mock 5 题（时间允许）

| task | 我们 | reference | 我们 token | ref token | 备注 |
|---|---|---|---|---|---|
| create_task_1 | 1.0 | 1.0 | 11,232 | 7,872 | — |
| create_task_1_with_env_assertions | **0.0** | 1.0 | 9,042 | 9,132 | 我们给 `create_task` 多传了 `description`，DB 哈希不符 |
| create_task_1_nl_eval | 1.0 | 1.0 | 17,738 | 20,095 | — |
| update_task_1 | **0.0** | 1.0 | 10,051 | 5,368 | 用户模拟器自己调了 `dismiss_notification`，改了 user DB；不是 agent 的错 |
| update_task_with_message_history | 1.0 | 1.0 | 6,051 | 5,360 | — |

| mock（n=5） | 我们 | reference |
|---|---|---|
| reward 均值 | **0.600** | **1.000** |
| token 均值 | 10,823 | 9,565 |
| 轮数均值 | 2.8 | 2.8 |

**读法**：mock 的两个 0 分，一个是我们的真弱点（参数“好心加料”），一个是基准自身的用户侧工具污染（用户模拟器动 user DB，gold 不含这些副作用，谁碰上谁红）。后者说明 mock 域不适合当主战场，retail/airline 更干净。

---

## 五、结论：我们这套在“工具＋策略”类任务上相对 reference 差在哪

1. **工具选择：不差。** 10 题里没有一次“该调 A 调成 B”的失败；读工具链（认证→查单→查商品→算差价→写）两臂相同。唯一真实的工具侧弱点是**参数纪律**：mock 里自发补了 `description`，被 DB 哈希判错。τ² 的判卷是**终态精确比对**，多一个字段就等于错。这是适配器要补的一条硬规则，不是模型笨。
2. **政策遵守：本批没看到差距。** retail 10 题没有出现“该拒绝却硬办/该换货却退款”的违规；task 5 的失败是“确认次数”与脚本预期错位，不是违反政策。
3. **问不问用户：都问，方式不同。** 两臂都会先要邮箱、再退到姓名＋邮编认证。我们的机械规则把“写前确认”变成稳定行为（task 6 因此命中），但也会在“脚本要求第二次确认”的场景（task 5）显得不够“追问”。**这不是理解力差距，是对话策略选择**。
4. **真正的差距是成本，不是分数**：每题多 **17.6%** token、每次调用输入多 **25%**。主要来自 system 里的**工具目录（16 个工具全文）＋章程**（我们的 system 约 11.2k 字符，tau2 约 7k 政策）；工具其实已经通过 API `tools` 字段发过一遍，目录是重复信息。次要来自我们平均多 0.6 次工具调用带来的历史累积。
5. **样本不足以谈胜负**：10 题实际只有 3 类场景（0/1、2/3/4、5–9 重复），单 trial，且 task 5/6 的用户模拟器行为本身不稳定。**0.900 vs 0.800 是噪声级差异，不能当成“我们更好”**。

---

## 六、下一步

1. **先修参数纪律（半天）**：章程加一条“工具参数只填客户明确给出或工具返回的字段，不补 description/默认值/占位串”，并在 `_to_openai` 前做一次轻量参数白名单裁剪（按 `openai_schema.parameters.properties`）。mock 的 `description` 失败就是这类。
2. **把机械闸门搬进来，但单独立臂（1 天）**：现在“写前确认”只靠章程文字。按批 28 的建议做 ~50 行运行时闸门——拦 `ToolType.WRITE`，检查最近一条用户消息是否有明确肯定，否则把调用退回成 `ToolMessage(error=True)`。**不与榜单分数混算**，作为实验臂 B；task 5 正好是它的用武之地（强制再确认会改变轨迹）。
3. **扩域顺序：airline → telecom，暂缓 mock**。airline 50 题、`DB+COMMUNICATE`，需要把语义判官指向 MiniMax 并在报告里注明；telecom 2285 题、23k 政策＋30 个用户工具，是第二版地雷，等闸门与参数纪律稳定后再上。
4. **上下文瘦身（半天）**：工具目录从“全量说明”降为“名字＋一句话”，或直接删掉（工具 schema 已在 API 侧）。预计省 10–15% 输入 token，先把成本拉回 reference 水平，再看分数是否掉。
5. **统计口径**：下一批至少 3 个 seed × 20 个不重复场景，报均值与区间；否则单 trial 的 ±1 题分差没有解释力。

---

## 七、纪律与残留风险

- `sihankor/` 与 `tau2-bench/` 均**未改一行**；`tau2-bench` 工作树干净。
- key 只经环境变量传递，仓库内无 key；`results/` 只存对话、token、reward 与账本。
- **判官换了**：retail 的 3 条 NL 断言默认判官是 `gpt-5.4-mini`，本批在 runner 里显式换成 MiniMax（`run_batch.py:138-140`）。两臂同判官，横向可比；**分数不与官方榜单比**。本批这 3 题两臂都过，未造成分差。
- 单题超时 600s 由父进程强杀；本批无超时。并发 2。
- 产物：`results/raw/*.json`（完整轨迹）、`*.summary.json`（摘要）、`results/ledgers/*.ndjson`（哈希链账本，15 本全部校验通过）、`results/analysis.md`、`results/batch*.log`。

**末行回显**：本批不涉及工作区注入面（`briefing sync` 未跑），故不附持有指纹；如需批结算，请在主编排侧统一执行。
