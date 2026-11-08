# 批 28：τ²-bench 本机落地与接法调研

日期：2026-11-07 ｜ 实施：D 席（opencode / DeepSeek-4.1-Flash 子代理）
落位：`experiments/tau2-lab/tau2-bench/`（独立 clone，**未改** `sihankor/` 一行）
时间盒：75 分钟（实际约 50 分钟，含样例与接法探针跑通）

**一句话结论**：环境一次装成、样例 28 秒跑通且 reward=1.0；但**我们的运行时不能直接当它的 agent**——差在接口形状、工具集、循环归属三处硬接口；最小可行接法是「在 tau2 的 agent 槽位包一层适配器，借它的环境/用户模拟器/判库，换我们的脑子」，约 0.5–1 人日。

---

## 一、环境

| 项 | 值 |
|---|---|
| 仓库 | `git clone --depth 1 https://github.com/sierra-research/tau2-bench.git` |
| commit | `033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f`（2026-11-04，`Merge pull request #744`） |
| 版本 | `pyproject.toml: name="tau2", version="2.0.0"` |
| Python | **3.12.13**（uv 自动装的托管解释器；本机系统是 3.14.4，**不满足** `requires-python >=3.12,<3.14`） |
| 环境 | `uv sync`（core，不含 voice/knowledge）；一次成功，75 个 distribution；litellm 1.81.11 |
| 代理 | 安装与跑测全程 `unset HTTP_PROXY/HTTPS_PROXY/ALL_PROXY`，直连可用 |
| 目录 | `/Users/moc/workspaces/SiAgent/experiments/tau2-lab/tau2-bench/` |

**版本提醒（重要）**：HEAD 是 **τ-bench 2.0**（含 τ-i18n 六语、τ-Entity/voice），不是 1.x 那版「τ²-bench」。2.0 改了判据口径（见 §二.4 的 reward_basis 分布），**分数与 1.x 榜单不可比**。若要复现论文/旧榜数字，应 `git checkout v1.0.1`。本报告一律以 2.0 HEAD 为准。

跑测试入口：`env -u HTTP_PROXY -u HTTPS_PROXY .venv/bin/tau2 <cmd>`（`.venv` 就在仓内）。

---

## 二、结构（带路径与行号）

### 1. 任务长什么样

定义在 `src/tau2/data_model/tasks.py`：

| 字段 | 类/行 | 说明 |
|---|---|---|
| `id` / `description` | `Task` `tasks.py:560` | 任务号；`description` 里有 purpose/relevant_policies/notes（可空） |
| `user_scenario` | `UserScenario` `tasks.py:52` | **给用户模拟器的剧本**：persona + `StructuredUserInstructions`（domain / reason_for_call / known_info / unknown_info / task_instructions） |
| `initial_state` | `InitialState` `tasks.py:506` | `initialization_data`（改库初值）、`initialization_actions`（预执行动作）、`message_history`（预置对话） |
| `evaluation_criteria` | `EvaluationCriteria` `tasks.py:366` | `actions`（**一条参考轨迹**，用来造 gold DB）、`env_assertions`、`communicate_info`、`nl_assertions`、`reward_basis` |
| `ticket` / `user_tools` / `agent_opener` | `tasks.py:560` 同上 | 单人解题模式票面；本任务可用哪些用户侧工具；脚本化开场白 |

数据集（JSON，实际任务文件）：
- `data/tau2/domains/retail/tasks.json`：114 条；`airline`：50 条；`telecom`：2285 条（`banking_knowledge` / `intake` 另有）。
- 每条任务的 `user_scenario.instructions` 是「用户想要什么」，**agent 看不到**（见 §二.5）。
- 我们跑通的样例就是 retail 的 `id="0"`：换货（键盘＋恒温器），参考轨迹 5 个动作，`initial_state=null`。

**关键认知**：这不是「给你一道题让你做」，而是「给你一个顾客，让你在电话里问出来并办完」。任务目标在用户模拟器手里，不在 agent 上下文里。

### 2. agent 怎么被调用

**它要的是一个 Python 对象，不是 HTTP 服务，也不是命令行。**

- 抽象基类：`src/tau2/agent/base_agent.py:52` `class HalfDuplexAgent`；构造签名 `__init__(tools: list[Tool], domain_policy: str)`（`:70`）。
- 必须实现的两个方法（继承自 `src/tau2/agent/base/participant.py:45,61`）：
  - `get_init_state(message_history) -> State`
  - `generate_next_message(message, state) -> (AssistantMessage, State)`
- 输入只可能是 `UserMessage | ToolMessage | MultiToolMessage`；输出必须是一条 `AssistantMessage`，**要么纯文本、要么纯 tool_calls，不能两者兼有**（校验在 `base_agent.py:177` 与 orchestrator `check_communication_error` `orchestrator.py:689-727`）。
- 循环由 **tau2 的 orchestrator 拥有**：`src/tau2/orchestrator/orchestrator.py:840` 的 `step()` 在 agent / user / env 三个角色间轮转；agent 只被「喂一条消息、要一条回复」。
- 入口：`src/tau2/runner/build.py:99 build_agent()` 从 registry 取工厂，工厂签名为 `factory(tools, domain_policy, **kwargs) -> agent`；参考实现 `LLMAgent` 在 `src/tau2/agent/llm_agent.py:54`，系统提示 `llm_agent.py:24-41`（= 指令 + **整份 domain policy**）。
- registry：`src/tau2/registry.py`（`register_agent_factory`），CLI 的 `--agent` choices 也是从 registry 动态取的（`src/tau2/cli.py:79-83`）。
- **没有 HTTP agent 接口**：`src/tau2/api_service/simulation_service.py` 只暴露 `/api/v1/get_options`、`/get_tasks`、`/run_domain`——是「远程跑整轮评测」，不是「远程当 agent」。自定义 agent 只能在本进程里注册（示例：`examples/agents/minimal_text_agent.py`）；因此接我们的东西要写一个小 runner 脚本，不能直接用 `tau2 run --agent ...`。

### 3. 工具接口

- 工具是**领域工具箱里的 Python 方法**，不是外部服务：如 `src/tau2/domains/retail/tools.py`（16 个工具）、airline 14 个、telecom 13 个 + 用户侧 30 个。
- 声明方式：装饰器 `@is_tool(ToolType.READ | ToolType.WRITE)`，定义在 `src/tau2/environment/toolkit.py:64`；`mutates_state` 默认由类型推出（`:82-88`）。
- 参数 schema：从函数签名 + docstring 解析成 pydantic 模型（`environment/tool.py:74-135`），再导出 OpenAI function schema（`environment/tool.py:140-150`）。**tau2 自己就产出 `{"type":"function","function":{...}}`，与 OpenAI 工具调用格式同构**。
- 副作用：工具直接改**内存里的 JSON DB**（`Environment.use_tool` → `ToolKitBase.use_tool`）；`ToolType` 决定评测回放行为——回放时 read 工具跳过、write 工具重放（`toolkit.py:43-88`、`environment/environment.py:293 set_state`）。
- 策略层约束（「写库前必须让用户明确确认」「一轮只一个工具调用」）**只写在 policy.md 里，靠模型自觉**；orchestrator 只校验「不能文本+工具混发/不能空消息」，不校验「确认」。

### 4. 判卷

入口 `src/tau2/evaluator/evaluator.py:89 evaluate_simulation()`；最终分 = `reward_basis` 里各分项的**乘积**（`evaluator.py:232-268`）。

| 分项 | 实现 | 判法 |
|---|---|---|
| `DB` | `evaluator/evaluator_env.py:23` | 用 agent 整条轨迹在**新环境**里重放，得到 predicted DB；用 `evaluation_criteria.actions` 在另一个新环境里重放，得到 gold DB；**比两者的 DB 哈希**（`evaluator_env.py:115-131`）。`actions` 不是硬性动作序列（除非 basis 含 ACTION）。 |
| `ENV_ASSERTION` | 同上 `:136-148` | 在 predicted 环境上逐条跑断言，全过才 1.0 |
| `COMMUNICATE` | `evaluator/evaluator_communicate.py` | 默认**语义 LLM 判官**（`--communicate-scorer semantic`），可退回子串匹配 |
| `NL_ASSERTION` | `evaluator/evaluator_nl_assertions.py` | 每条断言一次 LLM 判真；没有断言时中性 1.0 |
| `ACTION` | `evaluator/evaluator_action.py:68` | 参考动作是否都出现过（airline/retail/telecom **默认不用**） |

本轮实测各域 `reward_basis` 分布（读 `tasks.json` 统计）：

| 域 | 任务数 | reward_basis |
|---|---|---|
| retail | 114 | `DB+NL_ASSERTION` 112 条、`DB` 2 条；112 条里 **40 条有真实 `nl_assertions`（要 LLM 判官）**，72 条为空（等价只看 DB，样例 task 0 属于这一类） |
| airline | 50 | `DB+COMMUNICATE` 50 条 |
| telecom | 2285 | `ENV_ASSERTION` 2253 条、`ENV_ASSERTION+ACTION` 32 条；每条都有 `initial_state` |

判卷**完全不看模型自报**，也不看你走了哪条路——只看环境终态/断言/说过的话。这一点与我们 `tests_pass` 口径同源（结果导向），但「终态」是内存 DB 而非工作区文件。

### 5. 用户模拟器

- 是**另一个 LLM**：`src/tau2/user/user_simulator.py:61 class UserSimulator`；系统提示由 `build_user_system_prompt`（`:38-59`）拼「全局模拟守则 + persona + 任务剧本」。
- 走 litellm 的 `generate()`（`user_simulator.py:193-201`），模型来自 `--user-llm`，**任何 litellm 支持的模型都能换**（含本地 vLLM/OpenAI 兼容端点；我们用 MiniMax 实测通过）。
- 终止标记：用户输出含 `###STOP###`（`user_simulator_base.py` 的 STOP 常量，`user_simulator.py:142-155`），orchestrator 收到即 `USER_STOP`。
- 也可换 `DummyUser`（solo 模式，agent 自己扮演双方，`user_simulator.py:228`）。

---

## 三、样例跑通记录

### 命令原文（key 只从 `.env` 读入环境变量，未落任何文件）

```bash
cd /Users/moc/workspaces/SiAgent/experiments/tau2-lab/tau2-bench
source /Users/moc/workspaces/SiAgent/experiments/s3-blind/.env
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  OPENAI_API_KEY="$MINIMAX_API_KEY" MINIMAX_API_KEY= \
  .venv/bin/tau2 run --domain retail --num-tasks 1 --num-trials 1 \
  --agent llm_agent \
  --agent-llm openai/MiniMax-M3.1-Flash \
  --agent-llm-args '{"temperature":0,"api_base":"https://api.minimax.cn/v1"}' \
  --user-llm openai/MiniMax-M3.1-Flash \
  --user-llm-args '{"temperature":0,"api_base":"https://api.minimax.cn/v1"}' \
  --max-steps 60 --communicate-scorer substring \
  --save-to batch28-retail
```

### 结果

| 项 | 值 |
|---|---|
| 任务 | retail `id="0"`（换货；订单 `#W2378156`） |
| 结果 | **reward = 1.0**；DB 1.0；NL_ASSERTION 1.0（无断言，中性）；参考动作 5/5 命中（仅诊断） |
| 终止 | `USER_STOP`（用户说 ###STOP###），正常收尾 |
| 耗时 | **28.08 s**（03:21:08 → 03:21:36） |
| 对话 | 26 条消息，8 次工具调用 |
| Token | agent：12 次调用，84,929 prompt + 2,389 completion；user：5 次调用，6,894 + 356；**合计 94,568 tokens** |
| 花费 | litellm 报价 `$0.0000`（MiniMax 不在它的价目表，**不是真免费**，只说明未计费） |
| 产物 | `data/simulations/batch28-retail/results.json`（含全文对话、每次调用 usage、reward 分解） |

### OpenAI 兼容性验证（单测先行）

- 纯对话：`model="openai/MiniMax-M3.1-Flash"` + `api_base="https://api.minimax.cn/v1"` → 1.6 s 正常返回。
- **工具调用**：给一个 `get_order` function schema，模型正确回了 `tool_calls[0].function = {"name":"get_order","arguments":"{\"order_id\":\"W123\"}"}` → **完全兼容，可直接喂 tau2**。
- 结论：MiniMax 走 litellm 的 `openai/` 前缀 + `api_base` 即可，agent 和 user 两侧都成立；无需另装适配。

**判官模型的坑（比 agent 侧更容易卡）**：
- `COMMUNICATE` 的语义判官可配（`--communicate-judge`，默认 `gpt-5.5`，见 `config.py:57`），能指 MiniMax 或退回 `--communicate-scorer substring`。
- `NL_ASSERTION` 的判官是**写死的常量** `DEFAULT_LLM_NL_ASSERTIONS = "gpt-5.4-mini-2026-03-17"`（`config.py:49`），`tau2 run` 不暴露覆盖开关。retail 112 条里 **40 条**带真实 NL 断言 → 只有 MiniMax key 时这 40 条跑不了；要么在 runner 里 monkeypatch 该常量指向 MiniMax（判官口径会变，须在报告里注明），要么先只跑无断言的 72 条。

### 接法可行性探针（已跑通，非纸面推演）

为验证「在 tau2 的 agent 槽位包一层」这条路，写了一个最小探针 `experiments/tau2-lab/bridge/probe_agent.py`（约 140 行，**未改** tau2 源码）：

- 注册自定义 agent 工厂 → `run_single_task(TextRunConfig(agent="sih_probe"), retail task 0)`；
- 手工做 `tau2 Message` ↔ OpenAI chat messages 双向映射；
- 工具直接 `[t.openai_schema for t in tools]`；
- 模型仍走 MiniMax。

结果：**reward=1.0，26 条消息，`USER_STOP`**，与参考 agent 同题同分。两个真实坑已踩到并修好，接正式适配器时直接沿用：

1. tau2 的工具结果不是单条 `ToolMessage`，而是 `MultiToolMessage` 包一组（`data_model/message.py`），必须展开成多条 `role=tool`，否则 MiniMax 报 `tool call and result not match`；
2. `llm_args` 里已带 `api_base` 时不要再重复传，否则 litellm 报 `multiple values for keyword argument 'api_base'`。

这说明**路 A 的骨架是通的**，剩下的只是把探针里的朴素 system prompt 换成我们的上下文装配与账本。

---

## 四、接法结论（三问三答）

### 问 1：我们的运行时能不能直接当它的 agent？

**不能。** 三处都是硬接口，不是配置问题：

1. **接口形状**：tau2 要的是进程内 Python 对象，实现 `generate_next_message(message, state)`（`base_agent.py:52` + `participant.py:45`）。我们的运行时是「引擎 + CLI + OpenAI 兼容 provider 端口」，没有这个两方法契约。
2. **工具集**：tau2 把 13–16 个领域工具当参数传进来；我们的 provider 渲染器只认自己写死的 `TOOL_SCHEMAS`（`providers.py:27`），`tool_specs()` 对不认识的名字**静默丢弃**（`providers.py:258-268`）；引擎的工具分派也写死在 `read_file/dump/propose_patch/run_tests/git_commit`（`engine.py:1112-1175`）。换句话说，我们的 `OpenAICompatible` 能发请求，但它只会渲染「bugfix 工具历史」，渲染不了 tau2 的「用户话轮 + 助手话轮 + 工具结果」交错对话（`providers.py:271-324`）。
3. **循环归属**：tau2 的 orchestrator 拥有循环（`orchestrator.py:840`），agent 只是一次次的「下一步生成器」；我们的 Engine 拥有的是「预检→调查→落盘→独立验收→人签提交」的线性计划（`engine.py:60-92`），带审批与证据。两套循环不能嵌套。

另外还有一条语义上的反差不该忽略：**tau2 不把任务目标给 agent**（目标在用户模拟器剧本里），而我们所有上下文注入的前提是「任务书 + 仓库 + 失败证据都在手边」。这是两种任务范式。

### 问 2：最小可行接法是什么？两条路的工作量与保真度

**推荐路 A：在 tau2 的 agent 槽位写适配器（换脑子，不换循环）。**

- 位置：`experiments/tau2-lab/bridge/sih_agent.py`（**只在新 clone 的实验目录里**，不改 `sihankor/`）。
- 做法：`class SihAgent(HalfDuplexAgent)`，约 150–250 行：
  1. `get_init_state`：用我们的上下文装配思路拼系统提示（charter/约束 + `domain_policy` + 工具清单），状态里存 tau2 的 `Message` 列表；
  2. 每轮把 tau2 `Message` 历史映射成 OpenAI messages（assistant 文本 / assistant tool_calls / tool 结果 / user 文本）；
  3. 工具直接用 `tool.openai_schema`（tau2 已经给好，`environment/tool.py:140`），零转换；
  4. 调我们的 OpenAI 兼容端口（可复用 `providers.OpenAICompatible._http_json` 的传输层，或直接 litellm），把返回映射成 `AssistantMessage`（纯文本 xor `ToolCall[]`）；
  5. 可选：调用前后各写一条我们的账本事件（复用 `ledger.py`），工具执行仍归 tau2（**绝不能在我们的网关里执行**，否则状态双写）。
- 跑法：不能用 `tau2 run`（CLI 的 choices 在启动时就固化了），写一个 `run_single_task(TextRunConfig(agent="sih_agent", ...), task)` 的小 runner（模板见 `examples/agents/minimal_text_agent.py`）。
- **已验证**：上面 `bridge/probe_agent.py` 就是这个骨架的 140 行版本，20 分钟内跑出同题 1.0。正式适配器只多「上下文装配 + 账本」两件事。
- **工作量**：mock/retail 打通 0.5–1 人日；三域 + 账本落痕 2–3 人日。
- **保真度：100%**——环境、用户模拟器、判库全是 tau2 原装，分数与榜单可比。

**路 B：把 tau2 的环境/工具搬进我们的循环（换循环，不换脑子）。**

- 需要：进程内工具桥（把 13–16 个领域工具暴露给 `engine` 的固定分派器，或改分派器支持动态工具集）、对话状态机（替代我们的线性计划）、用户模拟器接入、判库复刻。
- **工作量：1–2 周**，且 `engine.py` 的计划/审批/证据模型与「顾客服务话轮」根本不匹配，改到最后等于重写一个运行时。
- **保真度：中高但需自证**——除非逐字节复刻 DB 重放与哈希，否则分数不可比。

**路 C：只借数据集与判库，自己写循环**：2–4 周，最差，不建议（判库的核心就是环境重放，环境不搬走，判库也搬不走）。

### 问 3：上下文注入在这个基准上还有没有意义？

**tau2 的上下文形状**（以 retail 为例，实测）：

| 层 | 内容 | 规模 |
|---|---|---|
| system | agent 指令 + **整份 policy.md** | retail 6,699 字符、airline 7,676、telecom 23,318 |
| tools | OpenAI function schema 列表 | retail 16、airline 14、telecom 13（另有 30 个用户侧工具） |
| history | 完整话轮（user / assistant / tool 交错） | 样例 26 条；单轮 prompt 峰值约 5.1k tokens |
| 任务目标 | **不在 agent 侧**，在用户模拟器 | — |

逐条对照我们那套：

| 我们的件 | 能否搬 | 判断 |
|---|---|---|
| **定位卡**（哪个函数/哪一行/为什么错） | ❌ 搬不过去 | 没有代码、没有栈、没有仓库。勉强能类比成「policy 条款卡」，但只有 telecom 的 23k 政策有检索价值；漏一条规范性条款就掉分，风险大于收益。**retail/airline 不做。** |
| **失败测试证据** | ❌ 搬不过去 | 没有测试可跑。最接近的信号是工具报错（`ToolMessage.error`）和用户纠正，tau2 已经自动回灌，不需要我们加。 |
| **机械闸门** | ⚠️ 部分能搬，且是**最值得搬的一块** | (a)「一轮一动作」tau2 已内建（`--enforce-communication-protocol` → `orchestrator.py:689-727`）；(b)「任何写库前必须用户明确确认」**只有 policy 文字、没有强制**。包一层 ~50 行：拦 `ToolType.WRITE`（`toolkit.py:43`），检查最近一条用户消息是否含肯定答复，否则把调用退回成 `ToolMessage(error=True)`。这是真正的运行时闸门，但会改变榜单口径，只能作为**单独的实验臂**。 |
| **账本/审计** | ✅ 能搬 | tau2 的 `results.json` 已有全文对话 + usage + reward 分解，事后转成我们的 `ledger.ndjson` 即可，零侵入。 |
| **上下文预算/压缩** | ⚠️ 价值低 | 样例峰值才 5.1k prompt tokens，不是瓶颈；我们的「指针卡/结果投影」能省 token，但对分数预计无感。 |

结论：**在这个基准上，我们那套「给修 bug 的模型喂定位信息」的核心价值不成立**，因为任务范式是「信息在用户嘴里，不在文件里」。能搬的只有治理侧的机械闸门与账本，且闸门要单独立臂。

---

## 五、下一步建议

1. **不接我们的 Engine，先接「脑子」**：以 `bridge/probe_agent.py` 为起点扩成 `bridge/sih_agent.py`，先在 retail 上跑 5–10 条，和原装 `llm_agent` 同题对比（同模型、同 seed）。这是唯一能在一人日内拿到「我们的上下文策略到底有没有用」的路径。成本约 1 天。
2. **先 retail，后 airline，暂缓 telecom**：retail 114 条（72 条只看 DB、40 条要 NL 判官），最好调；airline 50 条要过 COMMUNICATE（需要判官模型）；telecom 2285 条、23k 政策、30 个用户工具，是第一版的地雷。
3. **闸门单独立臂**：把「写库前必须确认」做成 `--enforce-write-confirmation` 包装层，作为实验臂 B，不与榜单分数混算。
4. **判官依赖要提前定**：`--communicate-scorer semantic` 可配 `--communicate-judge`（能指 MiniMax）或退回 `substring`；但 `NL_ASSERTION` 判官写死 `gpt-5.4-mini`（`config.py:49`），retail 有 40 条要用它——先跑无 NL 断言的 72 条，或在 runner 里显式 monkeypatch 并标注「判官已换，分数不与榜单比」。
5. **版本锁死**：论文/旧榜对比用 `v1.0.1`，新能力/多语用 2.0 HEAD；两套分数不可混。建议在 `experiments/tau2-lab/` 里各留一个 clone 或 worktree 并记 commit。

**总判断**：能接，而且成本不高——但接的是「tau2 的评测骨架 + 我们的模型/上下文策略」，不是「tau2 进我们的运行时」。如果目标是把 τ² 当作我们运行时的任务类别，正确做法是给 `tasks.toml` 增一个 `tool_agent` 类别，并让执行器走 tau2 的 orchestrator；把 `Engine` 本身塞进去，投入产出不成立。
