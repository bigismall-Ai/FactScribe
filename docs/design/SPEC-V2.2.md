# SPEC-V2.2｜FactScribe / paperkit 可执行规范

> 状态：蓝队收敛稿（第 2 轮），替代 `docs/design/SPEC-V2.1.md`；v2.1 与 `docs/design/DESIGN-v2.md` 保留为历史靶子。
> 输入：外部红队 `RED-2.md` 18 条（阻断 5／严重 8／一般 5），逐条裁决见 §1.3；`docs/design/SPEC-V2.1.md`（1172 行）；`paper/` 现网语料（48 facts／234 绑定 token／绑定级 0 红，读数见 §20.1）。
> 本版的一句话：**把保证对象从"被扫描到的 token"换成"被渲染出的数字"。**
> 命名说明：实现文件当前名为 `factscribe.py`（Python 模块仍为 `paperkit`）；本文命令统一写 `paperkit`，与实现同一工具。

---

## 0. 先看结论

1. **18 条红队意见：采纳 11、部分采纳 7、纯驳回 0**（逐条见 §1.3）。"部分"的 7 条里共 8 个子条款被明确驳回，每一条都写进 §1.4「已接受风险」——写明"接受什么风险、靠什么缓解"，不硬凑。
2. v2.2 的核心不是"再加规则"，而是**补上 v2.1 缺的那一步**：v2.1 的整条链是 `RAW → PROSE → QUANT token → BU → fact`，全链没有"渲染"这一步，于是宏、计数器、`\numexpr` 产生的数字**从来不进扫描面**。v2.2 加四件事：
   - **渲染面**取代"结论文本"：扫描面＝**闭包内全部会被 `\input` 进 PDF 的文本文件（含 preamble 与 `main.tex` 本身）**。v2.1 的"结论文本＝渲染内容"这句话，与它自己的"PROSE 层＝文件文本"互相矛盾，本版删除该词。
   - **数值可寻址性原则**：宏可以携带 **fact id**，不可以携带**数字**。`\newcommand{\kpi}{\accuracy\fact{A2}}` 合法；`\newcommand{\kpi}{91.4\%}`、`\newcommand{\acc}{9}` 非法。算术/计数器命令族（`\numexpr`、`\the\value`、`\setcounter`、`\pgfmathparse`、`\csname` 等）在正文与 preamble 一律红，白名单需显式登记。
   - **数字不许跨宏拼接**：数字 token 必须由连续字面数字构成；`\foo9`、`9\macro`、`{9}{1.4}` 直接红（判据见 §3.2，含白名单与例外）。
   - **PDF 文本回检**（L2/release 可选但推荐）：把 PDF 里抽出来的每个数字，与"账授权的数字集合"对表；宏/计数器/拼接出来的 `91.4` 在 PDF 里会露出来。
3. v2.2 **明确声明自己只保证什么**：`PASS` 的含义是"渲染面上每一个数字都能定位到一个字面量 token，该 token 属于某个 BU，并被某条账授权；且每条账的引用与记录一致"。它**不**保证"这句话在科学上为真"，也不保证"隐藏的尝试没被藏起来"。报告字段 `strength: "containment_only"` 把这句话写进机器可读输出。
4. **`PASS` 只在 L2 存在。** L0/L1 的"没查出问题"一律记 `UNVERIFIED`（独立退出码 8），CI 判定式写死为 `exit == 0 && verdict == "PASS"`。这是对 v2.1 最狠的一条漏洞（`verdict: PASS`＋`status: unverified`＋`exit 0` 三者并存）的正面修复。
5. 用我们自己的论文当磨刀石：`paper/` 里现成的 5 处 `\pkignore{CTX-xx}`、6 处裸 fact id、124 个表格数字，全部是 v2.2 的**必红/必黄用例**（§21）；同时它 234 条绑定、绑定级 0 红，是**不许被新规则误伤**的回归基线（§20.3）；已知迁移红单列、不混进基线。

---

## 1. 裁决表（第 1 轮 39 条 + 第 2 轮 18 条，逐条不漏）

> 题面写"R-G1..R-G5"，但 `RED-1.md` 实含 R-G1..R-G6（一般级 6 条），本表按 6 条收，合计 22 条与报告摘要一致。
> 结论口径：**采纳**＝按建议改；**部分**＝采纳主判据、驳回其附带手段；**驳回**＝原命题不成立或与架构冲突。

### 1.1 外部红队（RED-1，22 条）

| 编号 | 结论 | 一句话理由 | 改成什么 |
|---|---|---|---|
| R-B1 | 采纳 | 「CI 无 runs/ 必然红→团队关闸」是真实死法；根因是把可复现性与格式门禁捆在一个开关里 | 三档 verdict＋L0/L1/L2 分层（R-12）；`UNVERIFIED` 永不记为 PASS；PDF 由 `release` 把关（R-13） |
| R-B2 | 采纳 | 自动抽取＝原事故重演，且抽取器自证是循环论证 | 抽取器只读、只产**提案**（`facts.proposed.json`），字段白名单、禁自由文本、禁从 log/response 取指标、人批准后入账（R-04、R-11、R-14） |
| R-B3 | **部分** | 采纳「语义必须定义、必须机械校验、禁止隐式舍入」；驳回「正文裸数字一律红、数字只能宏注入」——那会废掉现有 48 条写法且与题面指定的闭包语义冲突 | 定义句级**闭包**语义＋`display` 显式可显示集（R-03、R-04）；注入式留作 v2.2 可选项 |
| R-B4 | **部分** | 采纳两级检测与中文数字覆盖；驳回「无数字可证伪主张也阻断」——那不是机械判据，会变成 LLM 判卷 | 结构剥离＋QUANT 定义＋中文数字/拼写数字（R-01、R-02）；无数字主张只进 `claim_queue.md` 顾问队列，不阻断（§6.3） |
| R-B5 | 采纳 | 代号不可判定＋黑名单可绕＋审计集未定义，三条都成立 | `symbols.json` 登记表＋白名单＋`main.tex` 闭包＋附录一等（R-05、R-09、R-15） |
| R-B6 | 采纳 | 「碎片化」是分布属性，不是词属性；语义相似度不可复现 | `\limitation[fact=]{...}` 受控宏＋位置判据＋句式表＋"具体性豁免"（R-10） |
| R-B7 | **部分** | 采纳 append-only＋证据要求＋共谋检测；驳回「工具内技术只读」——CLI 无法给自己降权，这是部署层的事 | 账本不可原地改、`supersedes`、改动必须带 payload 指针（R-14）；进程隔离进部署清单（R-14 的权限条） |
| R-B8 | **部分** | 采纳 run record／receipt／INVALID；驳回「无服务端 receipt 一律 INVALID」——没有服务端签名设施时会把全部账打成红，重演 R-B1 | 三级 `proof_class`：`server_signed > digest_only > self_report`；缺席＝`UNVERIFIED`，只有**显式矛盾**才红（R-11） |
| R-S1 | 采纳 | 只有 id＋数值相等，等值错配永远查不出 | fact 必填 `metric/scope/condition_hash/dataset/aggregation/n/run_id/observation`（R-04） |
| R-S2 | 采纳 | 信息密度最高的数字在表和图里，句级规则管不到 | 表格必须带生成 spec 或 cell map；图必须带 `.csv`/`.facts.json`；caption 数字照句级规则（R-06） |
| R-S3 | **部分** | 采纳"模型只收渲染片段、报告由独立进程重算"；驳回把"能力边界"写成工具承诺 | 提示词只喂占位符模板与最小词表、fact 自由文本转义、`release` 重算报告（R-11、R-14） |
| R-S4 | 采纳 | 三词黑名单双向失效，且"必填/可选"由工具自评＝永不阻断 | 按"渲染后是否进 PDF"判＋正则族＋人签 `required`（R-08） |
| R-S5 | 采纳 | 产物树没有 PDF＝没有受控的"出 PDF"动作 | 增加 `release`＋`audit/stamp.json`＋PDF 元数据戳；无戳 PDF 可检出（R-13） |
| R-S6 | 采纳 | 审后改稿没有事务绑定，报告必然过期 | `report.inputs{path:sha256}`＋`report_sha256`＋build 前校验（R-13） |
| R-S7 | 采纳 | 整文件哈希会假红，payload-only 又不护日志；规范化未定义 | 哈希对象＝canonical JSON 语义对（JCS），单一权威实现；重跑≠篡改（R-11、R-13） |
| R-S8 | 采纳 | 所有位置型规则都缺章节归属解析器 | `roles.json` 显式角色＋受控 `\sectionrole{}`；正文包含/排除集写死（R-15） |
| R-G1 | **部分** | 采纳"形态检测有地板"并写进保证强度；驳回"因此不该做门禁" | 报告强制 `strength: containment_only`；把保证下沉到"数字只能来自账"而非"句子像不像定量"（R-03、§22） |
| R-G2 | 采纳 | 没有对抗集，规则改动无法区分"修复"与"放宽" | `tests/fixtures/v21/{hostile,benign}/`＋`paper/` 只读夹具（§21） |
| R-G3 | 采纳 | 无错误码的阻断最终会被整体关闭 | 稳定 code 注册表＋`--json` 带 `severity/code/file/line/col/expected/actual/action`（§19） |
| R-G4 | 采纳 | 超时被当"非阻断"＝静默放行 | 超时/异常＝内部错误（exit 4），永不 0；增量按内容哈希缓存（驳回 mtime，不安全）（R-16） |
| R-G5 | **部分** | 采纳"工具生成提案＋人审批＋单一只读账本"；驳回"账本必须由工具从 runs/ 生成"——那正是 R-B2 说的自证 | 提案/批准分离；多版本共享只读账本＋派生视图（R-14） |
| R-G6 | 采纳 | 待办没有责任人/SLA/证据就不是闭环 | `owner/due/status/resolution` 四列；`status=done` 必须有可验证 resolution（R-08） |

### 1.2 内部红队（FS-R1-RED-B，17 条）

| 编号 | 结论 | 一句话理由 | 改成什么 |
|---|---|---|---|
| B1 | 采纳 | `\tableinput` 是作者自己写下的审计隧道，124 个数字全在闸门外 | 闭包自动展开纯 `\input{#1}` 包装宏；表格必须进集并带映射（R-05、R-06） |
| B2 | 采纳 | `places=0..4` 把 `10/16` 的值域撑成 `{1,0.6,0.62,0.625}`，改一个字符仍全绿（已复现） | 删除隐式舍入；值域＝`value` 精确形式∪`display` 显式形式（R-04） |
| B3 | 采纳 | 段落一行→行级绑定＝整段背书，追加假句也绿（已复现） | 绑定单元改句级 BU＋按标记切段；一条 fact 只许一个 setting（R-02、R-03、R-04） |
| B4 | 采纳 | `\pkignore` 参数不检查，塞整句假结论不涨红 | `\pkignore` 参数含 QUANT→`PKIGNORE_QUANT` 红；且不豁免代号（R-07、R-09） |
| S1 | 采纳 | fact id 与禁用代号同命名空间，照字面写会误红 20＋处，打补丁又能洗白 | 正文**禁止裸 fact id**（只许在 `\fact{}` 参数里）；代号规则与 fact 规则正交（R-09） |
| S2 | 采纳 | 代号检查挂在掩码后必然看不见 `CTX-*` | 代号检查跑**原文层**；`\pkignore` 不豁免（R-09） |
| S3 | 采纳 | `\todoq` 是渲染型 PENDING 框，不是注释；`main.tex` 又不在扫描面 | 按渲染判定→红；闭包根＝`main.tex`（R-05、R-08） |
| S4 | 采纳 | 今天 `--strict` 全红且红因与事实无关；黄红同码无法分诊 | `FACT/COVERAGE/ADVISORY` 三 tier＋分离退出码（§6、R-12） |
| S5 | **驳回** | 原命题"CI 必须带产物快照，否则这档只能本机跑"与 L0/L1/L2 分层冲突；L2 只需**摘要清单签名**，不必搬 payload 本体 | 只采纳其相对路径要求：`source_root` 必须相对（`ABSOLUTE_SOURCE_ROOT` 红）；证据缺席记 UNVERIFIED（R-11、R-12） |
| S6 | 采纳 | JSON 迁移四个断崖（数值化/0 变空/行号丢/注释丢）全部实测 | `value` 永远是字符串；`display/num` 双字段；`loc` 由 loader 预扫；`notes` 保留注释；`STALE_LEDGER` 红（R-04、§8.2） |
| S7 | 采纳 | 双轨并存无守卫，旧 toml 静默失效是最坏结果 | `facts.json` 存在时 `facts/**/*.toml` 仍在即红；迁移一次写 json＋删 toml＋打印新旧摘要（R-04） |
| G1 | 采纳 | 本仓真正漏的是拼写数字（ten/five），不是漏标；`_NUM_RE` 的保护只活在注释里 | 数字 token 定义升为规范条款＋拼写数字检测＋`paper/sections` 68 句 golden（R-01、§21） |
| G2 | 采纳 | `human_todo.md` 根本不存在，5 处 `\todoq` 性质不同却无法区分 | 工具生成、人只改 `status/resolution`；`[required]/[optional]`，缺省 required（R-08） |
| G3 | 采纳 | `build` 不读 audit，"禁止出 PDF"在代码里不存在（已复现） | `build`＝排版预览；`release`＝受控产物，前置校验报告新鲜度（R-13） |
| G4 | 采纳 | 规则没有注册表才是真风险，不是行数 | 拆 `src/paperkit/*`＋`tools/bundle.py` 拼回单文件＋`RULES={code:(tier,fn)}`＋每条规则一个真实 fixture（§8.1） |
| G5 | 采纳 | 图内数字是 PDF 里最强的视觉证据，却完全不可达 | 图必须带 `.csv`/`.facts.json`；绘图脚本只从账/数据取数；caption 数字绑定（R-06） |
| G6 | 采纳 | `confidence` 只是装饰，low 标一条编造数字照绿 | `low` 不得进摘要/主结果表；必须附区间＋人签；`LOW_CONF_IN_HEADLINE` 红（R-04） |

### 1.3 外部红队第 2 轮（RED-2，18 条，逐条不漏）

> 结论口径同上：**采纳**＝按建议改；**部分**＝采纳主判据、驳回其附带手段（驳回的子条款逐条落 §1.4）；**驳回**＝原命题不成立或不可实现。

| 编号 | 结论 | 一句话理由 | 改成什么（判据落点） |
|---|---|---|---|
| 2-B1 | 采纳 | v2.1 只做到"被扫到的 token 被授权"，没做到"被印出的数字被授权"，中间差一次宏展开 | 新增 **R-01A 渲染可归责性**（§3.2）：扫描面＝闭包内全部文本（含 preamble）；算术命令族红（`ARITH_IN_BODY`）；宏体含数字红（`NUMERIC_IN_MACRO`，白名单需签名登记）；数字邻接宏/花括号红（`NUM_ADJACENT_MACRO`/`NUM_AFTER_GROUP`）；`\ref` 单列放行；L2 加 `verify-pdf` 文本回检（`PDF_UNACCOUNTED_NUMBER`） |
| 2-B2 | 采纳 | `round_to` 从"描述小数位"越权成"授权半径"，`0.91` 能授权 `5`，且与 §3 的"不许四舍五入"直接冲突 | `display` 改**严格 canon 等价**（`canon(text)==canon(value)`），容差公式整条删除；`round_to` 必须是整数 ≥0 且等于 `text` 的小数位数，否则 `DISPLAY_ROUNDTO_INVALID`（CONFIG）；近似显示移入新字段 `approx_display`，**永不授权**，只出 `DISPLAY_APPROX`（黄） |
| 2-B3 | 部分 | "自洽性检查≠送达性证据"成立；但"工具强制 uid 隔离"CLI 做不到，只能规范＋部署清单＋可检子集 | `runs/`、回执、per-attempt metrics 的写者角色写进规范；`trusted_keys` **必须在项目目录之外**（工具可检：`TRUSTED_KEYS_IN_PROJECT` 红）；回执必须同时钉 `request_sha256`＋`response_sha256`＋`run_id`＋`attempt_index`（`RECEIPT_SCOPE_MISMATCH` 红）；`request_body_sha256` 降级为"payload 摘要"，不进 `proof_class` 任何一栏。**驳回**"工具强制 uid 隔离"（见 §1.4-1） |
| 2-B4 | 采纳 | `exit 0` 同时表示"通过"与"没查"，CI 必然读错；`--min-level l2` 未达标返回 0 是最坏形态 | `UNVERIFIED` 独立 **exit 8**；`--gate`/`--ci` 下非零；`PASS` 只在 L2 且 coverage 全绿时出现；`--strict` ≡ `--gate --level l2`；CI 判定式写死 `exit==0 && verdict=="PASS"`；横幅不得含大写 `PASS` 字样 |
| 2-B5 | 采纳 | 人签的是 id 不是内容，append-only 又允许同一 id 换 value ⇒ 签了等于没签 | 签名对象＝**内容哈希**（`id/value/display/source_sha256/run_id/observation.pointer/condition_hash/aggregation/rules_sha256/config_sha256`）；签名人身份来自密钥而非自填 `by`；`release` 重验；内容哈希变了没新签名 ⇒ `APPROVAL_STALE`（红）；批量批准 >10 条出 `APPROVAL_BATCH_LARGE`（黄） |
| 2-S1 | 部分 | 并集授权确实"不判归属"，A/B 对调可全绿；但"禁止多 fact 组"会废掉多值段的合法表达（规范 §5.1 的示例与夹具都在用） | 组内 token 与 fact **按出现顺序一一对应**（`BINDING_ATTRIBUTION` 红）；数量不等时要求 display 集**两两不交**（`FACT_SET_OVERLAP` 红）＋每条 fact 拥有唯一 token；真·同值用 `co_claim` 显式声明。**驳回**"一组只许一个 fact"（见 §1.4-2） |
| 2-S2 | 采纳 | §19 注册表里没有的码就是不会实现的码；`anchor`/`pair_with`/`paircheck` 是"不存在的缓解" | `anchor`、`pair_with` 进 fact schema 并实现（`ANCHOR_MISSING`、`PAIR_MISSING`）；补 `FACT_SET_OVERLAP`、`APPROVAL_STALE` 等缺失码；加规范自检 `SPEC_LINT`（正文出现的标识符必须在注册表/schema 里）；`DISPLAY_ORDER` **只在 BU 内**比较（驳回跨 BU 全局顺序，见 §1.4-8） |
| 2-S3 | 采纳 | 审计器写 `facts.json` 同时踩 append-only 与 uid 分离，还会立刻把报告变过期 | 删除 `mark f.state=invalid`；新增全局不变量 **`AUDIT_WRITES_NOTHING`**（写集合白名单＝`audit/report.json`、`.paperkit/cache/`、`audit/stamp.json`）；状态变更走 `paperkit ledger invalidate`（人签、append-only） |
| 2-S4 | 采纳 | 证据层循环对象是 marker 驱动，而表/图/`\factblock` 三种绑定天然没有 marker | 定义 **`REF_SET`**＝marker ∪ 表格 cell map ∪ 表格 spec ∪ 图 sidecar ∪ `\factblock` ∪ `pair_with` 的并集；证据层以 `REF_SET` 为循环对象；报告新增 `proof.coverage.unvalidated_facts`，有未验证 fact ⇒ `proof` 封顶 `self_report`（`PROOF_COVERAGE_GAP`） |
| 2-S5 | 部分 | per-attempt 与预注册可做；"证明没被藏起来的 attempt 不存在"在单侧证据下不可判 | `attempts[]` 一等公民；`metrics.json` 必须由 attempts 机械聚合；聚合规则预注册（`SELECTION_UNREGISTERED` 红）；`tool_call_count` 与 attempt 数交叉校验（`ATTEMPT_COUNT_MISMATCH` 红）；`NONCE_ABSENT` L2 升红。**驳回**"证明 attempt 全集"（见 §1.4-3） |
| 2-S6 | 部分 | 文本输入白名单、包装宏语法化、root 签名都能做；"生成内容不可判"是静态审计的天花板 | `project.text_inputs` 默认 `[".tex",".txt",".md"]`，全部入闭包并被扫描；包装宏判定写成可执行语法（保守：出现 `\input` 家族/`\csname`/`#` 即视为包装，未登记即红）；`root_tex` 变更需签名（`ROOT_TEX_CHANGED`）；`\input` 目标不可静态解析 → `INPUT_DYNAMIC_TARGET` 红。**驳回** `INPUT_NONDETERMINISTIC`（见 §1.4-4） |
| 2-S7 | 部分 | stamp 认证的是报告不是文档；`rules.json` 能让 L2 自我降级 | `stamp.compiled` 绑定 `root_tex/root_sha256/jobname/latexmk_inputs[]/pdf_sha256`；`release` 只许编译被审计的 root，范围不等即 `COMPILE_SCOPE_MISMATCH`；新增 `paperkit verify-pdf` 并给出发布脚本契约；升红表写进代码常量，`rules.json` **只能加严**，放宽需 owner 签名且报告列 `downgraded_rules`。**驳回**"arXiv 元数据强制"（见 §1.4-5） |
| 2-S8 | 部分 | "互不相邻的量级簇"与它自己的两个例子矛盾（`3/6` 与 `5/6` 同量级），不可判定；但"一 fact 一 setting"本身是对的 | **废除"量级簇"判据**；改为结构性判据：每条定量 fact 必填 `setting`（可 null），每个 `display` 项可带 `setting`；出现 ≥2 个不同 setting ⇒ `FACT_MULTISETTING`（升 **FACT**，全层红）⇒ 必须拆 `C1a/C1b`。**驳回**原统计判据（见 §1.4-6） |
| 2-G1 | 采纳 | §4.3 与 §5.2 对"逗号影响段边界"的定义互斥，两条路都红但红码不同 | 删除 §4.3 的"逗号影响段边界"半句；段只由标记组切分，且**标记向前覆盖（right-binding）**：组 `G_i` 覆盖"上一个组之后、`G_i` 之前"的文字；最后一个组之后的数字才 `UNBOUND_QUANT`。补 fixture 固定唯一 code |
| 2-G2 | 部分 | 封闭量词表必漏（五例/两轮）；"九成五"按 v2.1 算法只能推出 0.9 | 加 **`X成Y` 算法**（`X*0.1+Y*0.01` ⇒ 0.95）；量词表扩充且 `symbols.json` 可加；表外"数字＋汉字"产 **weak token**，只出 `CJK_QUANT_SUSPECT`（黄）不阻断。**驳回**"任意后接都算量词"（见 §1.4-7） |
| 2-G3 | 采纳 | 同一句在 canon key 与字面两种口径下结论相反 | 所有比较一律用 canon key；`DISPLAY_ORDER` 比较"去重后的 key 序列"，同一 key 的多种写法只占一个位置；`any_unique`/`DUPLICATE_BINDING` 同口径 |
| 2-G4 | 采纳 | oracle 钉在含 B2 漏洞的当前实现上＝任何变严的改动都会被回滚；三字段三语义 | fixture 的 `expected` 一律来自规范条款，当前实现读数只记 `observed`；加规则单调性 review（hostile 由红变绿必须附 `rules_sha256` 变更说明）；报告字段收敛为 `verdict`（唯一裁决）＋`exit`（由 verdict 唯一决定），删除 `status`；横幅去掉 `PASS` 字样 |
| 2-G5 | 采纳 | BU 按文件切 ⇒ 跨文件句子断裂；掩码会改变句界 | 闭包展开后按 `\input` 顺序拼成**全局文本流**再切 BU，文件边界不是句子边界；掩码用**配对花括号**抽取参数（不得越界），掩码区内的 ASCII 句号不参与切句，中文句末符永不被掩码吞掉；跨文件标记按全局位置归属唯一 BU |

### 1.4 已接受风险（8 个被驳回的子条款，写明"接受什么、靠什么缓解"）

| # | 被驳回的子条款 | 为什么不可实现/不该做 | 我们接受的风险 | 缓解措施 |
|---|---|---|---|---|
| 1 | 2-B3：「工具强制 `runs/` 由不同 uid 写、`trusted_keys` 由 owner 独占」 | CLI 进程无法给自己降权；uid/挂载是部署层的事（v2.1 已因此驳回同类命题） | 同一个 agent 可以同时写 `runs/` 与 `facts.json`，并自带密钥 | 规范写死角色表（§13.2）＋部署清单；`trusted_keys` 必须在项目外（工具硬检）；没有项目外密钥时 `proof` 最高 `self_report`，`release` 默认拒绝 |
| 2 | 2-S1：「禁止一个组覆盖多个 fact」 | 会废掉多值段的合法表达（`\fact{A2}\fact{A3}` 是规范 §5.1 的示例形态），并迫使一句拆成多个标记，可读性与迁移成本都不划算 | 组内归属仍依赖作者的书写顺序 | 顺序一一对应判据 + `co_claim` 显式声明 + `anchor`；误序即红，不再"并集放行" |
| 3 | 2-S5：「证明被藏起来的 attempt 不存在」 | 单侧证据无法证明全集；这是证据层的根本上限（v2.1 §13.5 已自陈） | 跑 30 次只报最好的一次，若服务端不配合则不可见 | `attempts[]` 强制 per-attempt＋预注册聚合＋`ATTEMPT_COUNT_MISMATCH`＋回执 `attempt_index`/`nonce`；`NONCE_ABSENT` L2 红 |
| 4 | 2-S6：`INPUT_NONDETERMINISTIC` 的静态判据 | 生成内容与手写内容在字节层不可区分；mtime/哈希只能证明"此刻是什么" | 审计之后、编译之前内容被脚本改写 | `release` 在编译前重哈希**全部** `inputs[]`，不符即 `REPORT_STALE`（exit 7）；stamp 记录 `latexmk_inputs[]` 的哈希 |
| 5 | 2-S7：「stamp 必须进 arXiv 上传元数据」 | 我们控制不了 arXiv 的上传协议 | 有人手工上传一份没 stamp 的 PDF，平台不会拦 | `paperkit verify-pdf` 给出命令级契约＋发布脚本片段（§15.3）；README 写明"平台不拦，只保证可检出" |
| 6 | 2-S8：原「互不相邻的量级簇」判据 | 与规范自己的两个例子矛盾（`3/6` 与 `5/6` 同为 10⁰），实现者必然分叉 | 无（该判据被结构性判据替代） | `setting` 字段成为 schema 必填，`FACT_MULTISETTING` 由结构判定，不靠统计猜测 |
| 7 | 2-G2：「中文数字后接任意汉字都算量词」 | 无词典不可判；会把"九章""三体"之类全打成 QUANT，误报洪水导致规则被关掉 | `五例`、`两轮` 这类表外数量仍只出黄色提示，不阻断 | weak token 只 advisory＋量词表可经 `symbols.json` 扩充＋`CJK_QUANT_SUSPECT` 计数进报告 |
| 8 | 2-S2：「`DISPLAY_ORDER` 扩展到跨 BU 全局顺序」 | 同一 fact 在 related/method/results 多处复用时，全局顺序约束误报率高，且"顺序"对多写法无意义 | 同一 fact 跨 BU 的值顺序不受约束（语义搬运仍可能漏） | BU 内顺序判据 + §5.4 的 `anchor`/`pair_with`/归属判据；剩余风险进 §22 |

---

## 2. 规范总则

### 2.1 术语

| 词 | 定义 |
|---|---|
| **审计闭包 / 渲染面** | 从 `root_tex` 出发，经 `\input/\include/\subfile/\import/\tableinput` 递归可达的全部**文本文件**（`.tex` 与 `project.text_inputs` 白名单内的 `.txt/.md`，见 R-05）；这同时就是"会被编译进 PDF 的字节集合"，含 `main.tex` 本身与 preamble。闭包外、项目内的文本文件＝孤儿。**v2.2 弃用 v2.1 的"结论文本"一词**——它把 preamble 排除在外，与"渲染内容"自相矛盾。 |
| **BU（binding unit，绑定单元）** | 全局文本流（闭包按 `\input` 展开顺序拼接）中的一个句子；中文按 `。！？；`，英文按 `.?!;`＋守卫切分；结构边界（`\\`、空行、`\item`、`\section`）强制切开；上限 600 字符。**文件边界不是句子边界**（§4）。 |
| **QUANT token** | 定量记号，定义见 R-01；不是"数字"。 |
| **渲染可归责性** | 任何最终出现在 PDF 里的数值字符串，必须能定位到被审计文本中的一个**字面量 token**，且该 token 属于某个 BU、被某条 fact 授权（R-01A）。 |
| **数值可寻址性** | 宏可以携带 fact id，不可以携带数字；算术/计数器不得产生正文数字（R-01A）。 |
| **附录** | 角色为 `appendix` 的文件，或 `\appendix` 之后的内容。 |
| **账** | `facts.json`；唯一事实源，append-only。 |
| **证据** | `runs/<run_id>/run.json` 指向的 payload 摘要、送达记录与签名回执（R-11）。 |
| **受控产物** | 由 `paperkit release` 生成、带 `stamp.compiled` 的 PDF；本地 `latexmk` 出的不算。 |
| **verdict** | 唯一裁决字段，取值 `PASS / ADVISORY / UNVERIFIED / RED`；`exit` 由它唯一决定（§2.3）。 |

### 2.2 三层判定与 gate tier

| tier | 含义 | 允许假阳性？ | 典型 code |
|---|---|---|---|
| `FACT` | 编造／不自洽／账坏／渲染不可归责——任何 level 都红 | 不允许，必须可复现 | `UNBOUND_QUANT`、`BOUND_MISMATCH`、`NUMERIC_IN_MACRO`、`BINDING_ATTRIBUTION` |
| `COVERAGE` | 没扫到／没签／没登记——L0 记 deferred，L2 红 | 允许有过渡期 | `ORPHAN_TEX`、`TABLE_UNBOUND`、`TODO_REQUIRED_OPEN` |
| `ADVISORY` | 值得人看，不阻断 | 允许 | `CJK_QUANT_SUSPECT`、`DISPLAY_APPROX`、`IGNORE_NOT_TRACKED` |

**红线：`COVERAGE` 永远不得降级成 `ADVISORY`；`FACT` 永远不得降级成 `COVERAGE`。**

**升红表在代码里，不在配置里。** 哪些 `ADVISORY` 在 L2 升红，是 `rules/__init__.py` 中的常量表 `ESCALATE_AT_L2`；`rules.json` 只能**加严**（把 false 改成 true），放宽需要 owner 签名并在报告里列出 `downgraded_rules`（§14.3）。v2.1 把升红策略放在作者可写的 `rules.json`，等于让 L2 可以自我降级成 L1，本版删除该能力。

### 2.3 退出码（唯一权威表）

| 码 | verdict | 何时 | 是否阻断 |
|---|---|---|---|
| 0 | `PASS` | 执行层＝L2、无任何红、无 advisory、coverage 全绿、`proof` 达标 | — |
| 0 | `UNVERIFIED` | 执行层 < L2（L0/L1），或 `--min-level` 未达；**默认模式** | 不阻断（`release` 拒绝） |
| **8** | `UNVERIFIED` | 同上，但开了 `--gate`/`--ci`（CI 推荐） | **阻断** |
| 1 | `RED`（`FACT`） | 任一 `FACT` 红 | 阻断（所有 level） |
| 2 | `RED`（`CONFIG`） | 配置/用法/账本 parse 错、签名工具缺失 | 阻断 |
| 3 | `ADVISORY` | L2 且只有 advisory，或 `downgraded_rules` 非空 | 不阻断 |
| 4 | `RED`（`INTERNAL`） | 超时、未捕获异常、编码错 | 阻断（永不 0） |
| 5 | `RED`（`COVERAGE`） | L2 下有 `COVERAGE` 红 | 阻断（仅 L2） |
| 6 | `RED`（`PROOF`） | 传了 `--require-proof` 但证据达不到要求的 `proof_class` | 阻断（仅显式开启） |
| 7 | `RED`（`STALE`） | 报告 hash 与磁盘不一致（审后改稿） | 阻断 `release` |

**与 v2.1 的唯一但关键的差别**：`PASS` 与 `UNVERIFIED` 不再共用退出码 0。`UNVERIFIED` 在默认模式仍返回 0（避免 R-B1 的"CI 无 runs/ 必然红"死法），但 CI 契约（§14.4）要求同时检查 `verdict`；开了 `--gate` 就返回 8。

### 2.4 输出横幅（强制）

当执行层 < L2，或 `proof != server_signed`，stdout 首行必须打印（**文本中不得出现大写 `PASS` 字样**，避免 grep 陷阱）：

```
!! 本次只跑了 {Lx}：{未校验任何送达性证据（proof=absent）| 送达性证据仅为 digest_only}；结论为 {unverified|advisory}，不构成通过结论
```

`--json` 时写在 `banner` 字段，同时 `verdict:"UNVERIFIED"`、`level:"L0"`、`proof:"absent"`、`exit:0|8`。缺任一字段视为工具 bug（exit 4）。`status` 字段删除（v2.1 里它与 `verdict` 语义打架）。

---

## 3. 判据 R-01：定量 token（QUANT）的定义

**判定输入**：`PROSE` 层文本（见 R-02 的分层），已做"术语预掩码"。**注意**：QUANT 只回答"这是不是一个数"，不回答"这个数从哪来"——后者由 R-01A（§3.2）管。

**判定算法**

```
1. 归一化：NFKC；零宽字符删除；连字符族 [‐‑‒–—−] → "-"；
   上标数字映射 ⁰¹²³⁴⁵⁶⁷⁸⁹ → 0-9；全角 → 半角。
2. 术语预掩码（最长匹配优先）：symbols.json 的 external 词条、fact id、bib key
   在文本上替换为 \x03 占位（保长度）。→ GPT-4 / LLaMA-3.1-70B / M3.1 / V4.1 /
   pytest-10081 / ISO-8601 不再是 QUANT。
3. 在剩余文本上按顺序匹配：
   FRAC   := DIGIT ("," DIGIT)* "/" DIGIT        # 整体一个 token
   NUM    := DIGIT ("," DIGIT)* ("." DIGIT+)? ([eE][+-]?DIGIT+)?
   SIGN   := 紧邻 NUM 前的 [-+−]（无空格）       # 负数是一个 token
   SUFFIX := 单位表 | [kKMB] | "%" | "percent" | "pct" | 倍 | 成 | 折
   CJK    := 强匹配 [零〇一二两三四五六七八九十百千万亿半]+
            后接 Q_STRONG = (个|种|项|次|条|组|成|折|倍|%|百分点|余|多|近|约)
            且前不接 (第|其|一|二|三|四|五|六|七|八|九|十) 的序数用法
   CJK弱  := 同字符类，后接任意非标点字符，但词不在 Q_STRONG、也不是序数/成语/专名
            （三体、九章、四小龙）→ 只产 weak token
   X成Y   := CJK 数字 + "成" + CJK 数字（九成五、三成五）
            值 = X*0.1 + Y*0.01（九成五=0.95；三成=0.3；三成五=0.35）
   SPELLED:= 英文数词表 (one|two|...|ten|dozen|hundred|thousand)
            必须后接可数名词（tasks|runs|instances|trials|models|datasets）
4. token.key：
   FRAC   → "frac:10/16" 且同时登记 dec:0.625（只此一个十进制，不展开舍入）
   NUM    → 精确十进制规范串（去尾零、去千分位、量级后缀换算）
   %      → "dec:0.968" 且 "pct:96.8"（二者互认，属于单位换算，不是舍入）
   CJK强  → 精确换算（九=9、十余=approx:10+、两倍=2、九成五=0.95）
   CJK弱  → 同换算，但 token.weak=true（只出 CJK_QUANT_SUSPECT，不阻断）
   SPELLED→ 精确整数
5. 每个 token 记 (raw, key, span, file:line:col, kind, weak)。
```

**误报/漏报边界**

- 漏：`第 21 号上下文分片`（中文序数改写）、图片像素里的数字、`\input` 之外动态生成的 `.tex`。前两者声明为**不可判**，靠 R-09 的登记表和人工评审兜底。
- 漏：`近一倍`、`十余`、`几成` 只能识别为 `approx`，不能做等值比较；绑定到 `approximation:true` 的 fact 才算通过，否则 L2 红（`APPROX_UNBOUND`）。
- 误报：年份（在 `\cite{}` 参数内被掩码，裸写 `(2017)` 仍是 QUANT→ 必须绑 fact 或写 `\year{2017}`）；`第 3 章`（序数掩码）；`三个数据集`（CJK 命中，需绑 fact——这是**想要**的行为）。
- 误报：`R^2` 的上标被 `_mask_scripts` 掩掉；但 `×10⁻³` 的 `⁻³` 经上标映射后会变成 `-3`，需在 `_mask_scripts` 之前先抽科学计数法整体，否则 `1.2×10⁻³` 会被拆成 1.2 和 -3。**实现顺序写死：先抽 `NUM[eE][+-]?NUM` 与 `×10^` 复合式，再掩上下标。**
- 分辨率：`0.910` 与 `0.91` 规范键相同（这是同一数值的不同写法，允许）；`0.91` 与 `0.9100` 相同；`91%` 与 `0.91` 相同（单位互认）；`0.9` 与 `0.91` **不同**（不许四舍五入）。
- 漏（2-G2）：`五例`、`两轮` 这类表外量词只产 **weak token** → `CJK_QUANT_SUSPECT`（黄），不阻断；这是有意的取舍（开放匹配会误伤"九章""三体"）。量词表可经 `symbols.json#quantifiers` 扩充。
- 误报防护（2-G2）：`第九章`（序数）、`三组`（强匹配，需绑 fact——想要的行为）、`九成五`（`X成Y` 算法 → 0.95，F28 的期望值现在可从算法导出）。

**失败时退出码**：QUANT 定义本身不产生 issue；它产出的 token 交给 R-03。工具内部对同一 span 产出两个 token（重叠）时 exit 4。

---

### 3.2 判据 R-01A：渲染可归责性（v2.2 新增，回应 2-B1/2-S6）

> v2.1 保证的是"被扫描到的 token 都被账授权"，不是"被渲染出的数字都被账授权"。本节补的就是这一步：**数字必须是字面量，且必须落在被扫描的字节里。**

**判定输入**：闭包内全部文本文件（含 `main.tex` 与 preamble、`\input` 进来的 `.txt/.md`）的原文 `RAW`；宏定义表；`project.numeric_macro_allow`；`project.layout_commands`。

**判定算法**

```
A. ARITH_IN_BODY（红，FACT）
   在闭包全部原文（含 preamble 与宏体）上匹配命令族表 A；
   命中即红，无论它是否真的产生了数字。
   表 A（首版，代码常量，只能经 owner 签名扩充）：
     \numexpr \dimexpr \inteval \the \value \arabic \roman \Roman \alph \Alph
     \fnsymbol \setcounter \addtocounter \stepcounter \refstepcounter \newcounter
     \count \newcount \advance \multiply \divide \number \romannumeral
     \csname \expandafter \pgfmathparse \pgfmathresult \pgfmathsetmacro
     \pgfmathtruncatemacro \directlua \luadirect \write18
   注：`\setlength`/`\addtolength`/`\vspace`/`\hspace`/`\includegraphics[width=]`/
       `\scalebox`/`\fontsize`/`tabular` 列格式 **不在表 A**——它们吃数字但不产生正文数字，
       其参数在 PROSE 层被掩码（R-02）。

B. NUMERIC_IN_MACRO（红，FACT）
   对 DEF_RE = \\(newcommand|renewcommand|providecommand|def|NewDocumentCommand|
                    DeclareDocumentCommand|DeclareRobustCommand) 抓到的每个定义语句：
     检查范围 = 可选默认值 [default] + 定义体 {body}；
     排除参数个数 [n] 本身（那是结构参数，不是渲染数字）。
     若范围内出现 [0-9]，且宏名 ∉ project.numeric_macro_allow → RED(NUMERIC_IN_MACRO)
   numeric_macro_allow 每条形如 {name, reason, signed_by}；
   登记的数值宏只允许用于 preamble 的布局参数或 `\includegraphics` 的 width=；
   出现在任何 BU 内 → RED(NUMERIC_MACRO_IN_BODY)。

C. NUM_ADJACENT_MACRO / NUM_AFTER_GROUP（红，FACT）
   对每个 QUANT token 的 RAW span [s,e)：
     L = RAW[s-1]；R = RAW[e]
     ① RAW[:s] 以 \\[A-Za-z]+$ 结尾（宏名紧贴 token）且宏 ∉ SAFE → RED(NUM_ADJACENT_MACRO)
     ② RAW[e:] 以 \\[A-Za-z]+ 开头（宏紧跟 token）且宏 ∉ SAFE → RED(NUM_ADJACENT_MACRO)
     ③ L == '}'（数字紧跟一个闭合组，{9}{1.4} 形态）      → RED(NUM_AFTER_GROUP)
     ④ R == '{' 且该花括号组为空（{}），且组后紧跟数字     → RED(NUM_ADJACENT_GROUP)
        （9{}1.4 渲染成 91.4；空组是"零宽连接器"）
   SAFE = {fact, ref, eqref, autoref, cref, Cref, label, cite, citep, citet, citealp}
   判据含义：数字 token 必须由**连续字面数字**构成，左右不得是宏调用或闭合组。
   花括号判据有方向：`{10/16}` 合法（L=`{`、R=`}`）；`{9}{1.4}` 非法（第二个 token 的 L=`}`）。
   判据不是"禁花括号"，而是"禁数字紧跟一个闭合组"——因为闭合组后面再写数字，渲染时会直接粘上。

D. number_ledger（读出口）
   每个被 BU 授权的 token 记 (raw, key, file, line, col) 进 report.number_ledger，
   供 `verify-pdf` 回检与人工复核使用。
```

**为什么这一条能落地（而不是空话）**

- (a) 宏体逃逸：`\newcommand{\acc}{9}` 命中 B；`\newcommand{\kpi}{\acc\onefour\%}` 的调用点渲染出 `91.4`，但 `\acc`/`\onefour` 已在 B 里红，且 D 的 PDF 回检会把 `91.4` 抓出来。
- (b) token 拼接：`9`+`1.4` 无论写成 `\foo9`、`9\macro` 还是 `{9}{1.4}`，都命中 C 的 ①②③；即使绕过，PDF 里出现 `91.4` 而 ledger 里没有 `91.4` → D 红。
- (c) 计数器/算术：`\setcounter`/`\numexpr`/`\the\value` 命中 A 整族，不依赖"是否真的产生了数字"这一不可判问题。
- `\ref` 的取舍：`\ref` 一族进 SAFE（跨越引用是结构编号，禁掉会误伤每篇论文）。**边界写死**：`\ref` 不得承载定量主张；工具不检查这一点，只由 PDF 回检把 `\ref` 产生的编号列入允许集。这是**设计取舍**，不是漏。

**误报/漏报边界**

- 误报：`\providecommand{\fact}[1]{}`、`\newcommand{\todoq}[1]{}`、`\newcommand{\sys}{\textsc{Sih}}` 定义体无数字 → 不触发（本仓实测）。
- 误报：`\newcommand{\figwidth}{0.9\linewidth}` 之类布局宏 → 显式登记进 `numeric_macro_allow`（带理由与签名）；未登记即红是**有意**的 fail-closed。
- 漏：`.sty`/`.cls` 内部定义的宏（不在项目闭包）；纯展开技巧（TeX 图灵完备，理论上不可穷尽，例如用零宽间距命令拼接）；位图里的数字（不做 OCR）。
- 兜底：`verify-pdf` 的 `PDF_UNACCOUNTED_NUMBER`。

**PDF 文本回检（L2/release，推荐开启）**

```
paperkit verify-pdf paper.pdf --report audit/report.json [--warn-only]
 1. pdftotext -layout 抽文本；缺 pdftotext → PDF_TOOL_MISSING（exit 2）
 2. 抽所有 NUM 形态的字面数字串
 3. 允许集 = report.number_ledger.raw ∪ canon 渲染形
             ∪ \ref 目标编号 ∪ 页码 ∪ project.pdf_constants（日期、arXiv 号等，需登记）
 4. 任一 PDF 数字不在允许集 → PDF_UNACCOUNTED_NUMBER（L2 红；--warn-only 时黄）
```

- 误报：断字/字距把 `10/16` 抽成 `10/ 16` → 比较前归一化（去空白与软连字符）；仍可能误报，故给 `pdf_constants` 与 `--warn-only`。
- 漏：图内位图文字、矢量图里的标注（PDF 文本层可能取不到）。

**失败时退出码**：`ARITH_IN_BODY`/`NUMERIC_IN_MACRO`/`NUMERIC_MACRO_IN_BODY`/`NUM_ADJACENT_MACRO`/`NUM_AFTER_GROUP`/`NUM_ADJACENT_GROUP` → 1；`PDF_UNACCOUNTED_NUMBER` → 5（`--warn-only` → 3）；`PDF_TOOL_MISSING` → 2。

**fixture**：`hostile/2-B1/`（宏体拼接＋计数器＋`\numexpr`＋`9{}1.4` 四个子例）、`benign/2-B1/`（无数字宏、`\ref`、正常绑定）；PDF 回检用 `paper/main.pdf` 当 benign。

---

## 4. 判据 R-02：BU 切分与中文无空格问题

**判定输入**：闭包内全部文本文件，按 `\input` 展开顺序拼成的**一条全局文本流** `G`，外加并行 source map（每字符回到 file:line:col）。**文件边界不是句子边界**（2-G5）。

**判定算法**

```
0) 全局流：depth-first 展开闭包，\input 展开位置即拼接位置；文件切换点只记 source map，
   不产生 BU 边界。跨文件的一句话是一个 BU。
1) 分层（同一份文本四个视图，长度不变，行列号不漂）：
   RAW   原样
   SPLIT RAW 掩掉：% 注释、\begin{verbatim|lstlisting|minted|comment} 整块、
         \verb、\cite/\ref/\label/\includegraphics/\fact 的参数、
         tabular 列格式参数、布局命令的数值参数
         （\setlength/\addtolength/\vspace/\hspace/\scalebox/\fontsize）。
   PROSE 在 SPLIT 上把术语预掩码与 \fact 标记替换为 \x02/\x03 占位
   ANNO  在 PROSE 上额外标出 \todoq/\todo/\pknote/\fixnote 的位置（不掩掉内容）
   SYMB  在 PROSE 上额外掩掉 \fact{} 参数（用于 R-09 的裸 id 检查）

   掩码规则（2-G5 的修复）：
   - 参数抽取一律用**配对花括号**，不用贪婪正则；掩码不得跨出参数右括号，
     因此参数后面的句末标点永远不会被吞。
   - 掩码区内：中文句末符 。！？； 永不掩掉（照常切句）；ASCII 句号 . 一律视为
     非句末（bib key、缩写、URL 里的点不切句）。
   - 不变式（单测强制）：对任意 fixture，sentence_boundaries(SPLIT) 的中文句末位置
     与 sentence_boundaries(RAW) 相同。

2) 切句（在 SPLIT 上跑）：
   1) 硬边界：\n\s*\n、"\\\\"、\item、\section、\subsection、\paragraph
   2) 句末：。！？； 与 . ! ? ;
      英文 "." 的守卫（任一成立则不是句末）：
        - 前字符是数字且后字符是数字（3.14）
        - 前是单个大写字母（J. Smith）
        - 前是缩写表 {et al, Fig, Eq, Sec, vs, e.g, i.e, approx, No, Ref}
        - 后字符是 ")" 且前是数字
   3) 中文逗号「，」**不切句、也不切段**（2-G1：段只由标记组切分，见 R-03）
   4) BU 长度 > 600：在最近的「，/；」处切开，发 SPAN_TOO_LONG（advisory）

3) \fact 标记按**全局位置**归属到唯一 BU；若文件最后一个非空行是 \fact 组、
   且下一文件的首个 token 是 QUANT → MARKER_TRAILING（黄）。
   绑定仍按全局流计算：那个数字照样 UNBOUND_QUANT（红）——
   禁止"在文件 A 末尾写标记、给文件 B 的数字用"。
```

**中文无空格怎么切**：不依赖空格。句末标点＋守卫已经把中文散文切成句；`\fact{}` 位置由 sentinel 保留，因此"标记属于哪一句"是纯位置问题，与分词无关。中文数字/量词由 R-01 的 `CJK` 规则单独识别，不参与切句。

**误报/漏报边界**

- 误报：`Fig. 3` 被缩写在守卫里挡掉；`et al.` 同理。
- 漏：无标点的长排比句（作者用逗号写完整段）会被当成一句，绑定变宽 → 由 `SPAN_TOO_LONG` 提示，不红。
- 漏：`。` 后面没有空格仍会切（中文正确）；英文 `foo.Bar` 不切（可能漏一句）——由 600 字符上限兜底。
- 已知不可判：公式环境 `\begin{equation}` 内部不做句切，整块视为一个 BU（数学里的数字同样要绑 fact，见 R-06）。
- 误报防护（2-G5）：`\emph{...}`/`\footnote{...}` 的参数用配对花括号掩码，右括号后的 `.` 仍是句末（v2.1 的贪婪正则会吞掉它）。
- 去重：文件末尾的孤立标记只报 `MARKER_TRAILING`，不再重复报 `FACT_WITHOUT_QUANT`。

**失败时退出码**：切分异常（source map 与文本长度不一致、掩码前后中文句末位置不一致）→ exit 4。

**fixture**：`hostile/2-G5/`、`benign/2-G5/`（跨文件句子）；`hostile/2-G1/`、`benign/2-G1/`（逗号右绑）；`benign/2-G3/`（掩码内句号不切句）。

---

## 5. 判据 R-03：`\fact{id}` 的语义（本规范的核心）

### 5.1 语义定义

> `\fact{ID}` 是一个**闭包声明**：它声明"本 BU 内、由我覆盖的每一个 QUANT token，都出现在 ID 的可显示集里"。
> 它不是"这里有个事实"的装饰，也不是"这句话大概和 ID 有关"的标签。

`value` 本身的 token 集合永远是基线；`display` 只能追加**与 value 数值相等**的写法（同一数值的不同表示，如 `10/16` 与 `62.5%`），不能追加近似值或舍入值。

**覆盖范围＝"段"（segment，右绑）**：一个 `\fact` 组闭合**它前一个标记组之后、它自己之前**的那一段文字。连续书写、中间只有空白/标点的多个 `\fact{}` 算**一个组**（`\fact{A2}\fact{A3}`），共同闭合同一段。**逗号不切段**（2-G1）：`…91.4\fact{A2}，其余 42…\fact{A3}` 里 `42` 归 `A3`；只有"最后一个组之后再出现数字"才是 `UNBOUND_QUANT`。

| 写法 | 覆盖范围 | 说明 |
|---|---|---|
| `... 10/16 and 5/16\fact{A2}\fact{A3}。` | 组 `{A2,A3}` 覆盖整段；**第 1 个数归 A2、第 2 个数归 A3**（按出现顺序） | 一段多值（归属可判定） |
| `... 5/6 and 4/6\fact{B1}, ... 210.8k ... 104.2k\fact{B3}.` | `B1` 覆盖前半段（`5/6`、`4/6`）；`B3` 覆盖后半段（`210.8k`、`104.2k`） | 一句多断言（本仓 05_eval 实句，token 数≠fact 数 → 走并集分支） |
| `... 达到 0.91\fact{F-04}，其余 42\fact{F-05}` | `0.91` 归 `F-04`，`42` 归 `F-05`（右绑） | 相邻断言 |
| `... 达到 0.91\fact{F-04}，其余 42。` | `42` 在最后一个组之后 → `UNBOUND_QUANT` | 尾段裸数 |

- 标记出现在 BU 开头（段为空）→ `FACT_OUT_OF_SPAN`（红）。
- 最后一个标记组之后的尾段若还有 QUANT → `UNBOUND_QUANT`（红）。
- 段内 0 个 token → `FACT_WITHOUT_QUANT`（advisory，例如 `\fact{E9}` 的机制陈述）。
- **行不是绑定单位**：即使一个自然段占一整行（本仓 `paper/sections/*.tex` 的排版事实），段也只到上一个标记为止；同一行里标记之后新写的数字照样红。这是 B3 的正面修复。
- **块形式**（表格/多行构造用，可选）：`\factblock{ID} ... \factend{ID}`，块内每个 QUANT 都必须在该 fact 的集合里；`\factblock` 只能用于 `tabular` 或独立段落，不许嵌套；块内的 fact 自动进 `REF_SET`（R-11）。

### 5.2 判定算法

```
for bu in BUS(global_stream):
    groups = marker_groups(bu)         # 按位置分组；组内成员只隔空白/标点
    segs   = split_before(groups)      # len(segs) == len(groups)+1
    if not groups:
        for t in QUANT(bu): RED(UNBOUND_QUANT, t)
        continue

    for g, seg in zip(groups, segs[:-1]):
        toks = QUANT(seg)              # 已做术语预掩码
        if not toks:
            ADVISORY(FACT_WITHOUT_QUANT, g); continue
        quant_ids = [f for f in g.ids if f.quantitative]   # 顺序＝书写顺序
        if not quant_ids:
            RED(NONQUANT_BACKS_QUANT, g)   # 只有机制陈述来背数字
            continue

        if len(toks) == len(quant_ids) and not any_co_claim(quant_ids):
            # ① 归属分支（2-S1）：第 k 个 token 归第 k 个 fact
            for t, fid in zip(toks, quant_ids):
                if t.key not in display_set(fid):
                    RED(BINDING_ATTRIBUTION, t, fid)
        else:
            # ② 并集分支：要求 display 集两两不交，再查唯一性
            for a, b in pairs(quant_ids):
                if display_set(a) & display_set(b) and not co_claim(a, b):
                    RED(FACT_SET_OVERLAP, a, b)
            allowed = union(display_set(f) for f in quant_ids)
            for t in toks:
                if t.key not in allowed:
                    RED(BOUND_MISMATCH, t, g.ids, expected=allowed)
            for fid in quant_ids:
                owns = [t for t in toks if t.key in display_set(fid)]
                if not owns:
                    RED(FACT_UNUSED_IN_SPAN, fid)
                elif not any_unique(owns, toks, fid):
                    others = union(display_set(f) for f in g.ids if f != fid)
                    if display_set(fid) <= others:
                        ADVISORY(DUPLICATE_BINDING, fid)   # 真·同值佐证（或 co_claim）
                    else:
                        RED(FACT_UNUSED_IN_SPAN, fid)      # 挂名凑数

    # 尾段（最后一个组之后）不许有裸数
    for t in QUANT(segs[-1]): RED(UNBOUND_QUANT, t)
```

`any_unique(owns, toks, fid)`：段内存在某个 token，其 key 在 `allowed(fid)` 里、但不在同组其它 fact 的 allowed 里。它保证"每条被点名的 fact 至少负责一个别家负不了的数"。**`any_unique` 只用于分支 ②；分支 ① 用位置归属，不再依赖唯一性。**

`co_claim`：fact 字段 `co_claim: ["H3"]`，必须**双向声明**（A 声明 B、B 声明 A），否则 `CO_CLAIM_ASYMMETRIC`（红）。作用：两条 fact 本来就是同一个数（如 `C1`/`H3` 都覆盖 `3/6 vs 5/6`）时，免掉 `FACT_SET_OVERLAP`，降为 `DUPLICATE_BINDING` advisory。

**为什么这样能抓 A/B 对调（2-S1）**：`The plain arm resolves 5/16 while our arm resolves 10/16\fact{A2}\fact{A3}` 里 token 顺序 `[5/16, 10/16]`、fact 顺序 `[A2(10/16), A3(5/16)]` ⇒ 第 1 个 token 不在 A2 的集合里 ⇒ `BINDING_ATTRIBUTION` 红。把两臂对调后 token 顺序也变，仍然红——**归属由位置固定，不再由并集放行**。

### 5.3 多值、顺序与"一 fact 一 setting"

- **顺序（2-G3）**：一条 fact 的 `display` 是**有序列表**。若同一 BU 内某 fact 被用了 k≥2 个**不同的 canon key**，它们在句中出现的先后必须与 `display` 中这些 key 的先后一致，否则 `DISPLAY_ORDER`（红）。同一 key 的多种写法（`62.5%` 与 `10/16`）只占一个位置，不计入 k。若实现从 `value` 派生顺序（旧账迁移期），派生顺序必须等于 `value` 中 token 的出现顺序。
- **一 fact 一 setting（2-S8，结构性判据）**：每条 `quantitative:true` 的 fact **必须**有 `setting` 字段（string 或 null）；每个 `display` 项可带 `setting`，缺省继承 fact 的 `setting`。若一条 fact 的 `value` 与其 `display` 项出现 **≥2 个不同的 setting 值** ⇒ `FACT_MULTISETTING`（**FACT，全层红**），必须拆成两条 fact。
  - 本仓 `C1 = "3/6（24 步上限）；60 步 → 5/6"` 是标准反例：`24 步` 与 `60 步` 是两个 setting ⇒ 迁移拆 `C1a/C1b`。
  - 原"互不相邻的量级簇"判据**废除**（2-S8：它与自己的两个例子矛盾，不可判定）。
- 一条 fact 只覆盖一个断言；同一 fact 可以出现在多个 BU（重复引用合法）。
- `quantitative:false` 的 fact（如 E9 的机制陈述）不参与授权、不要求"拥有"数字，只作上下文标注；但如果一段有数字而该组**全是**非定量 fact → `NONQUANT_BACKS_QUANT`（红）。本仓 `06_ablation.tex:8` 的 `0/3\fact{E1}\fact{E9}` 合法（E1 定量、E9 标注）；若写成 `0/3\fact{E9}` 则红。

### 5.4 误报/漏报边界

- **不漏**：数字拼错、数字来自别的 fact、整句新编但数字不在账上、把 `10/16` 改成 `1/16`、**组内 A/B 对调**（归属判据）、**宏/计数器/拼接产生的数字**（R-01A）。
- **会漏（必须承认）**：数字全对、归属也对，但**语义张冠李戴**——`\fact{A2}`（开臂 10/16）写在"plain arm resolved 10/16"这一句里，而该句没有别的臂的数可供对照。闭包只证明"10/16 是账上的数"，不证明"它属于这个臂"。
  - 缓解 1（**已实现，非空话**）：`anchor` 字段。fact 可声明 `anchor: ["assembly"]`，要求该字符串在本 BU 内字面出现；启用后缺失 → `ANCHOR_MISSING`（红）。默认关闭，论文正式稿建议开。
  - 缓解 2（**已实现**）：`pair_with: ["A2"]`。L2 检查成对 fact 的标记出现在同一个 BU；缺失 → `PAIR_MISSING`（红）。
  - 缓解 3：`DISPLAY_ORDER`（BU 内）＋ `BINDING_ATTRIBUTION`（顺序）＋ R-01A 的邻接判据。
  - 剩余风险进 §13.6 与 §22 的"不承诺"清单。
- 误报：一个 BU 里有多组数、只有尾部一个 `\fact{A11}\fact{A12}`——每组各自右绑，token 数≠fact 数时走并集分支（本仓 `05_eval.tex:25` 实句），不误报。
- 误报：`\fact{}` 包住非数字句（E9）→ advisory，不红。

### 5.5 失败时退出码

| code | tier | exit |
|---|---|---|
| `UNBOUND_QUANT` | FACT | 1 |
| `BOUND_MISMATCH` | FACT | 1 |
| `BINDING_ATTRIBUTION` | FACT | 1 |
| `FACT_SET_OVERLAP` | FACT | 1 |
| `CO_CLAIM_ASYMMETRIC` | FACT | 1 |
| `FACT_UNUSED_IN_SPAN` | FACT | 1 |
| `FACT_OUT_OF_SPAN` | FACT | 1 |
| `NONQUANT_BACKS_QUANT` | FACT | 1 |
| `DISPLAY_ORDER` | FACT | 1 |
| `MARKER_TRAILING` | ADVISORY | 3 |
| `FACT_WITHOUT_QUANT` | ADVISORY | 3 |
| `DUPLICATE_BINDING` | ADVISORY | 3 |
| `FACT_AMBIGUOUS_BINDING` | ADVISORY | 3 |
| `FACT_MULTISETTING` | **FACT** | 1 |
| `SPAN_TOO_LONG` | ADVISORY | 3 |

**fixture**：`hostile/2-S1/`、`benign/2-S1/`（归属）；`hostile/2-S2/`、`benign/2-S2/`（anchor/pair）；`hostile/2-S8/`、`benign/2-S8/`（setting）；`hostile/2-G1/`、`benign/2-G1/`（右绑）；`hostile/2-G3/`、`benign/2-G3/`（canon key 顺序）。

---

## 6. 判据 R-04：账本 schema 与值域

### 6.1 `facts.json` 结构

```json
{
  "schema": "fact/2.2",
  "digest_prev": "sha256:...",
  "facts": [
    {
      "id": "A2",
      "claim": "开臂 resolved（全 16 题）",
      "value": "10/16",
      "display": ["10/16", "62.5%"],
      "quantitative": true,
      "unit": "count",
      "metric": "resolved",
      "scope": "swb16",
      "dataset": "swe-bench-verified",
      "subset": "b23-16",
      "condition_hash": "sha256:...",
      "aggregation": {"stat": "count", "n": 16, "over": ["instance"]},
      "setting": null,
      "co_claim": [],
      "anchor": [],
      "pair_with": [],
      "run_id": "B23-SWB16-on",
      "observation": {"run_id": "B23-SWB16-on", "pointer": "/summary/on_resolved"},
      "source": "experiments/ctx-redblue/BATCH23-SWB16.md",
      "source_sha256": "2c36...",
      "locator": "§二 汇总",
      "confidence": "high",
      "kind": "claim",
      "state": "valid",
      "supersedes": [],
      "derived_from": [],
      "expr": "",
      "notes": ["全部来自批 18 已验证红→绿的实例"]
    }
  ]
}
```

### 6.2 必填与类型（强制校验）

- `value` **永远是字符串**。JSON number → `VALUE_NOT_STRING`（红，exit 2）。理由：`0` 会被 `str(... or "")` 吞成空串、`10/16` 无法表示（内部 S6）。
- `quantitative:false` 时 `value` 可散文（E9 这类机制陈述）；`true` 时 `value` 必须含 ≥1 个 QUANT token，否则 `VALUE_NOT_QUANT`（红）。
- **冲突裁决**：`value` 是唯一基线，`display` 只用于人读。二者不一致时**以 value 为准并判红**（`DISPLAY_INCONSISTENT`），不存在"并集放行"。
- `display[]`：`quantitative:true` 时必填；每项是 `"10/16"`（字符串简写）或 `{"text":"96.8%","round_to":1,"setting":"cap-60"}`。**每一项都必须与 `value` 严格等价**：`canon(text) == canon(value)`，否则 `DISPLAY_INCONSISTENT`（红）。`round_to` 若出现，必须是整数 `≥ 0` 且等于 `text` 的小数位数，否则 `DISPLAY_ROUNDTO_INVALID`（红，CONFIG）。
  - **容差公式整条删除**（2-B2）。v2.1 的 `|canon(text) − canon(value)| ≤ 0.5×10^-round_to` 把 `round_to` 从"描述"变成"授权半径"：`value:0.91` + `round_to:1` 可授权正文 `0.9`，`round_to:0` 可授权 `1`，`round_to:-1` 可授权 `5`。本版一律不允许。
  - **近似显示**若确实需要，写进新字段 `approx_display: [{"text":"~0.9"}]`；它**永不进入授权集**，只在正文出现该近似值时出 `DISPLAY_APPROX`（黄）。
- **值域**＝`{canon(value)} ∪ {canon(d.text) for d in display}`，全部是严格等价形式。没有隐式舍入，没有"商的白名单"（删除 `fact_value_keys` 的 `places=0..4` 循环）。
- **`setting` 必填**（`quantitative:true` 时，string 或 null）；`display` 项可带自己的 `setting`；出现 ≥2 个不同 setting ⇒ `FACT_MULTISETTING`（红，见 R-03）。
- **`co_claim` / `anchor` / `pair_with` / `approx_display`** 为可选字段；`co_claim` 必须双向声明（`CO_CLAIM_ASYMMETRIC` 红）；`anchor` 非空时启用 `ANCHOR_MISSING`；`pair_with` 非空时启用 L2 的 `PAIR_MISSING`。
- 字段依赖：`derived_from` 非空 ⇒ `expr` 必填（沿用 v1）；`quantitative:true && L1` ⇒ `observation` 必填；`state:"invalid"` ⇒ `invalid_reason` 必填。
- `confidence:"low"` ⇒ 该 fact 不得出现在 `abstract`/`results` 角色的正文里；且必须 `variance`/区间字段（`LOW_CONF_IN_HEADLINE` 红）。
- 账本卫生（沿用 v1）：`DUPLICATE_ID`、`LEDGER_CONFLICT`、`DUPLICATE_VALUE`。`DUPLICATE_VALUE` 从"黄"升为"黄＋提示拆分"，因为它是 R-03 值域白名单的温床。
- **`STALE_LEDGER`**：`facts.json` 存在且 `facts/**/*.toml` 仍存在 → 红（exit 1）。迁移完成后 toml 必须删。

### 6.3 抽取（runs → 账）的边界

- 抽取器只写 `facts.proposed.json`，**不写** `facts.json`；批准是人的动作：`paperkit ledger approve <id> --key <key_id>` 对**内容哈希**签名（§16.2），不是"按 id 点一下"。
- 抽取字段白名单：只允许 `run.json` 的 `metrics` 与 grader 输出；**禁止**从 `*.log`、`response.json`、模型自述文本取指标（`EXTRACT_FORBIDDEN_SOURCE`，exit 2，抽取器自身报错）。
- `facts.json` 不含自由文本字段给 LLM 读；`notes` 不进入提示词（由组装层过滤）。
- 无数字的可证伪主张（"均优于基线"）→ 写 `claim_queue.md`，人工逐条确认/驳回；**不阻断**。这是 R-B4 的降级处理，也是我们接受"形态检测有地板"的代价。

### 6.4 误报/漏报边界

- 漏：**被正确签名的错误值**。审计只能证明"账与正文一致、签名与内容哈希一致"，不能证明"账与 payload 一致"——后者靠 R-11 的 observation，再往上一层靠人。**但"0.91 改成 0.19 却复用旧签名"不再漏**：内容哈希变了，`APPROVAL_STALE` 红（2-B5）。
- 误报：`value:"0/3（F13）"` 这类带标签的旧值 → `VALUE_HAS_PROSE`（advisory），迁移时拆成 `value:"0/3"` + `setting:"F13"`。
- 误报：`value:"请求体里搜不到 _asciidoc_row"`（E9）→ 未标 `quantitative:false` 时红；迁移补标记即可。

**失败时退出码**：schema/类型/依赖错 → 2（配置错，工具没跑起来）；账本内部矛盾 → 1；`STALE_LEDGER` → 1。

**fixture**：`hostile/2-B2/`、`benign/2-B2/`（display 严格等价）；`hostile/2-B5/`、`benign/2-B5/`（签名粒度）。

---

## 7. 判据 R-05：审计文件集＝渲染面闭包

### 7.1 判定输入

`project.root_tex`（默认 `main.tex`，**变更需签名**）、`project.text_inputs`（默认 `[".tex",".txt",".md"]`，非文本扩展名默认拒绝）、`project.expand`（额外可展开宏）、项目内全部文本文件。

### 7.2 算法

```
# 0) 先建宏表：name -> {n_args, body, def_file}
#    定义体从"直接输入引用"扫描中剥离；定义体里的 \input 只参与 may_input 判定
queue = [root_tex]; seen = {}
while queue:
    f = pop(); text = read(f); seen.add(f)
    code = strip_def_bodies(text)

    # ① 直接的 \input 家族
    for (cmd, arg) in INPUT_REF_RE.finditer(code):
        record_input_decl(f, cmd, arg)          # 每一次出现都进"输入声明表"
        if '#' in arg: RED(INPUT_DYNAMIC_TARGET, f, arg); continue
        target = resolve(arg, relative_to=[project.root, f.parent])
        if not exists(target):                RED(INPUT_TARGET_MISSING)
        elif outside(project.root):           RED(INPUT_OUTSIDE_PROJECT)
        elif ext(target) not in TEXT_INPUTS:  INFO(INPUT_NON_TEXT, target)   # .sty/.cls/图片
        else: push(target)

    # ② 包装宏的调用点（宏名来自宏表；体里出现过 input 家族痕迹的才算候选）
    for call in WRAPPER_CALL_RE.finditer(code):
        m = macro_table.get(call.name)
        if m is None or not may_input(m.body): continue
        if call.name not in project.expand:
            RED(UNREGISTERED_INPUT_WRAPPER, f, call.name); continue
        body = substitute(m.body, parse_args(code, call))
        for (cmd, arg) in INPUT_REF_RE.finditer(body):
            record_input_decl(f, cmd, arg)
            target = resolve(arg, relative_to=[project.root, f.parent])
            if not exists(target): RED(INPUT_TARGET_MISSING)
            elif outside(project.root): RED(INPUT_OUTSIDE_PROJECT)
            elif ext(target) in TEXT_INPUTS: push(target)

# 包装宏判定：可执行语法，不是"举例"
DEF_RE = \\(newcommand|renewcommand|providecommand|def|NewDocumentCommand|
          DeclareDocumentCommand|DeclareRobustCommand)\s*\{?\\([A-Za-z@]+)
may_input(body) = body 中出现 \input|\include|\subfile|\import|\tableinput|
                  \InputIfFileExists|\@@input|\csname|\expandafter 的字面
若 may_input(body) 且宏名 ∉ project.expand → RED(UNREGISTERED_INPUT_WRAPPER)
EXPANDABLE = {input, include, subfile, import, includeonly}
           ∪ {宏 X | may_input(body(X)) 且 X ∈ project.expand}
# \import{A}{B} 解析为 A/B；\subfile 与 \include 同 \input；\includeonly 只影响编译，不影响闭包
```

- **包装宏一律白名单**（2-S6）：不做"能自动识别就自动展开"的启发式；漏检方向必须是"多扫/假红"，不能是"静默漏"。`\newcommand{\tbl}[2]{\input{#1/#2}}`、`\NewDocumentCommand`、`\def`、可选参数、带 `\ifx` 的写法，只要体里有 `\input` 家族痕迹就要求登记。
- **非 `.tex` 文本输入**（2-S6）：`\input{results_body.txt}` 必须进闭包并按文本扫描，不得"记 info 跳过"；`.sty/.cls/图片` 才是 info。
- **输入声明表**：任何 `\input` 家族命令的出现都进表；表外目标或无法解析的目标（含 `#`）→ 红。
- **`root_tex` 变更**（2-S6）：从 `main.tex` 改到别的文件，或 `project.root_tex` 与签名记录不一致 → `ROOT_TEX_CHANGED`（红，需 owner 签名；签名体含新 root 的哈希）。v2.1 把 `root_tex` 当普通配置项，等于给了一条"把真文章挪到审计闭包外"的路。
- 闭包外、项目内的文本文件 → `ORPHAN_TEX`（COVERAGE；L0 黄，L2 红）。
- `audit/report.json` 的 `coverage.closure` 必须列出全部文件与哈希；`coverage.orphans` 必须为空才可能 PASS。
- 附录是**一等公民**：`appendix/*.tex` 必须在闭包里（`\input` 可达），否则 `APPENDIX_UNREACHABLE` 红——否则"代号迁附录"等于"迁出审计范围"。

### 7.3 误报/漏报边界

- 漏：用 `\directlua`/`\write18` 在编译期生成的文本（`release` 检测到直接红 `SHELL_ESCAPE` / `ARITH_IN_BODY`）。
- 漏：**审计之后、编译之前**文件被脚本改写。静态审计只保证"审计时刻的字节"；`release` 在编译前重哈希全部 `inputs[]`，不符即 `REPORT_STALE`（exit 7）。这是 §1.4-4 接受的风险。
- 漏：同一文件被 `\includeonly` 排除 → 仍在闭包里（保守，会多扫，不误放）。
- 误报：`\input{foo}` 指向 `.sty`、`.cls` 或图片 → 记 `INPUT_NON_TEXT`（info），不入文本扫描面。
- 误报：`\verb|\input{x}|` 里的字符串 → PROSE 已掩 verbatim。
- 误报：`\input` 出现在注释里 → 注释先被剥离，不进输入声明表。

**失败时退出码**：`INPUT_TARGET_MISSING`/`INPUT_DYNAMIC_TARGET`/`UNREGISTERED_INPUT_WRAPPER`/`INPUT_OUTSIDE_PROJECT`/`APPENDIX_UNREACHABLE`/`ROOT_TEX_CHANGED` → 5（L0 记 deferred→3）；`ORPHAN_TEX` → 5（L2）/3（L0）。

**fixture**：`hostile/2-S6/`、`benign/2-S6/`（`.txt` 输入、包装宏、root 变更）。

---

## 8. 判据 R-06：表格与图

### 8.1 表格（三级放行，缺一即红）

一个含 `\begin{tabular}` 的文件必须满足下列之一：

1. **生成式**（推荐）：文件头有 `% paperkit:generated spec=tables/t1_main.spec.json`。`spec.json` 形如
   ```json
   {"rows":[{"key":"pallets_flask-5014","cells":{"on":"A2","on_tokens":"A11"}}],
    "renderer":"tools/make_tables.py@sha256:..."}
   ```
   审计用**同一渲染器**从 facts 重算每格文本，与 `.tex` 逐格比对；不一致 → `TABLE_DRIFT`（红）。这证明"表＝账"，而不是"表里有几个合法数字"。
2. **映射式**：`% paperkit:table-map {"12":{"on":"A2"}}`（行号→列→fact）。逐格校验 token ∈ `display_set(fact)`。
3. **内联式**：单元格里写 `91.4\fact{A2}`（段内唯一 token，按 R-03 绑定）。

三者皆无 → `TABLE_UNBOUND`（COVERAGE；L0 黄，L2 红）。

**所有三种方式都必须以 fact id 为锚**（2-S4）：spec/映射的每个 cell 必须给 fact id；内联式必须带 `\fact{}`。出现"裸字面量单元格"且无映射 → `TABLE_BARE_LITERAL`（COVERAGE，L2 红）。这样表格里的 fact 天然进入 `REF_SET`（R-11），证据层会真的去查它引用的 run。

### 8.2 图

- 每张 `\includegraphics` 必须同名 sidecar：`figures/f2_swebench.csv` 或 `.facts.json`（`{series:[{point, fact}], renderer_sha256}`）。
- sidecar 里每个 `fact` 必须存在且进 `REF_SET`（2-S4）；缺 fact 字段 → `FIGURE_UNBOUND`。
- caption 是 BU，里面的数字照 R-03 绑定（本仓的 "two baseline-red instances" 是拼写数字，走 R-01 的 SPELLED）。
- 绘图脚本必须从 sidecar/账取数——**这一点工具无法验证**，只能校验 `renderer_sha256` 与 sidecar 存在。明确写进"不承诺"。

### 8.3 边界

- 漏：图里坐标轴刻度/标注的数字（PDF 内文本），不做 OCR。
- 误报：`\multicolumn{2}{c}` 的 `2` 是结构参数（已掩码）。
- 误报：行名里的 `pylint-6528` 是实例 id（术语预掩码）。

**失败时退出码**：`TABLE_DRIFT`/`TABLE_UNBOUND`（L2）/`FIGURE_UNBOUND`（L2）→ 5；`FIGURE_UNVERIFIED`（无 csv）→ 3。

---

## 9. 判据 R-07：`\pkignore` 与其它豁免宏

- `\pkignore{X}` 只允许包**非定量标识符/短标签**（如 `sphinx-10449`）。
- **例外：`\pkignore` 包裹 `table/tabular` 整块时，走 R-06 的表格通道**（生成式/映射式/内联式），不按"参数含 QUANT"报 `PKIGNORE_QUANT`。否则本仓 5 张表会被同一条规则重复判红，而表格真正需要的是 cell→fact 映射，不是豁免。
- 参数区间内抽 QUANT：命中 ≥1 个 → `PKIGNORE_QUANT`（**红**，exit 1）。B4 的 `\pkignore{We resolved 99 of 100 tasks...}` 必红。
- `\pkignore` **不豁免** R-09 代号检查、不豁免 R-08 的 TODO 渲染检查（回应内部 S2）。
- 允许的豁免宏只有 `\pkignore`；`\pknote`/`\fixnote` 视为渲染型批注（R-08）。
- 每次使用必须登记进 `human_todo.md`（`class: ignore`，`required: no`），未登记 → `IGNORE_NOT_TRACKED`（advisory）。
- 必须计数：报告 `counts.pkignore` 给出总次数；`counts.pkignore != human_todo.md 中 class=ignore 的行数` → `IGNORE_NOT_TRACKED`（advisory，L2 升红）。
- `\newcommand{\pkignore}` 的定义体若含 `#1` 之外的渲染内容 → `EXEMPTION_MACRO_SUSPECT`（红）。

**边界**：`\pkignore{CTX-15}` 里 `CTX-15` 被 R-09 抓；若作者把它包成 `\pkignore{\texttt{CTX-15}}`，仍在原文层可见 → 仍抓。

**退出码**：1。

---

## 10. 判据 R-08：TODO/PENDING 按"渲染后是否进 PDF"判

### 10.1 分类器

```
render_class(macro):
  \todo, \todoq, \missingfigure, \fixme, \tbd, \pknote
     → render，除非 preamble 有 \usepackage[...,disable]{todonotes} 且无 \todonotesenable
  % 注释里的 TODO/PENDING/FIXME/待补... → comment（不进 PDF）
  verbatim/lstlisting/minted 内 → code（不进正文）
  \texttt{...} 内 → inline（进 PDF，仍算正文）
  \title/\author/\thanks 内 → render（进 PDF）
```

- `render` ⇒ `TODO_IN_PDF`（**红**，exit 1），并强制进 `human_todo.md`，`required` 缺省 **true**（fail-closed）。
- `comment`/`code` ⇒ `TODO_COMMENT`（advisory，exit 3），也进 `human_todo.md`，`required:false`。
- 词表（正则族，大小写不敏感，词边界）：`TODO|PENDING|FIXME|TBD|TK|XXX|WIP|待补|待填|待确认|待定|待核|未完成|not final|to be (verified|confirmed|written)`。
- `\todoq[required]{...}` / `\todoq[optional]{...}`：人显式声明；工具**不得**自评。缺省 required。
- **空宏判定**：若批注宏的定义体为空（`\newcommand{\todoq}[1]{}`）或只展开为不可见内容，则其调用按 `comment`/`disabled` 处理 → `TODO_COMMENT`（黄），**不**报 `TODO_IN_PDF`。判据是"渲染后是否进 PDF"，不是"宏名像不像 TODO 宏"。

### 10.2 `human_todo.md`（工具生成，人只改两列）

```markdown
<!-- paperkit:todo v1 -->
| id | source | macro | class | required | owner | due | status | resolution |
|---|---|---|---|---|---|---|---|---|
| T-0001 | main.tex:29 | \title | render | yes | moc | 2026-11-15 | open | |
| T-0002 | sections/00_abstract.tex:12 | %TODO | comment | no | moc | — | open | |
```

- 工具拥有 `id/source/macro/class/required`；人拥有 `owner/due/status/resolution`。
- `required:yes && status!=done` → `TODO_REQUIRED_OPEN`（COVERAGE，L2 红；L0 黄）。
- `status:done && resolution 为空` → `TODO_CLOSED_WITHOUT_EVIDENCE`（红）。
- `resolution` 必须是可验证事件：命令、run_id、sha256、或 `n/a: <理由>`。
- 源里已消失但 `status:open` 的行 → `TODO_ORPHANED`（advisory）。

### 10.3 边界

- 误报：论文主题就是"代码 Agent 的 TODO 标记"，方法节要展示 `\texttt{TODO}`。放行条件：出现在 `verbatim/lstlisting` 或 `appendix` 角色，或 `symbols.json#quoted_literals` 登记。正文散文里裸写 `TODO` 仍红——这是有意的保守。
- 漏：`\todoq` 被 `\iffalse ... \fi` 包住（TeX 条件）。检测 `\iffalse` 块并标 `CONDITIONAL_TEXT`（advisory）。
- 误报：`todonotes` 的 `disable` 选项下 `\todo` 不进 PDF → 降为 advisory。
- 本仓 `main.tex:27` 的 `\newcommand{\todoq}[1]{\todo[...]{\textbf{PENDING: }#1}}`：宏定义体含 `PENDING` → `TODO_MACRO_DEF`（advisory）；每处调用 → 红。

**退出码**：`TODO_IN_PDF`→1；`TODO_REQUIRED_OPEN`→5（L2）/3（L0）；`TODO_CLOSED_WITHOUT_EVIDENCE`→1；`TODO_COMMENT`→3。

---

## 11. 判据 R-09：内部代号（白名单制）

### 11.1 判定输入

- `RAW` 层文本（**不是** `PROSE`——否则 `\pkignore` 里看不见，内部 S2）。
- `symbols.json`：
  ```json
  {"schema":"symbols/1",
   "external":[{"token":"GPT-4","kind":"model","citation":"openai2023gpt4"},
               {"token":"ISO-8601","kind":"standard"},
               {"token":"pytest-10081","kind":"instance","citation":"..."}],
   "internal":[{"token":"CTX-15","natural":"section-kind invariant",
                "locations":["appendix"]}],
   "quoted_literals":["TODO","PENDING"]}
  ```
- fact id 全集、bib key 全集（自动并入白名单）。
- **注意白名单的边界**：fact id 进白名单，只表示它不会被报成 `CODENAME_UNREGISTERED`；它仍受 `NAKED_FACT_ID` 约束——正文里裸写 `E5` 是红，只有出现在 `\fact{E5}` 的参数里才合法。这样"注册一条同名 fact 来洗白真代号"的路被堵死（内部 S1）。

### 11.2 算法

```
for span in RAW_minus_masked_args(file):
    norm = NFKC; dash_map; strip ZWSP
    for m in CODENAME_RE.finditer(norm):
        tok = m.group(0)
        if tok in fact_ids:      RED(NAKED_FACT_ID)        # 只许出现在 \fact{} 参数里
        elif tok in bib_keys:    continue
        elif tok in external:    continue
        elif tok in internal:    RED(CODENAME_IN_BODY) unless role==appendix
        else:                    RED(CODENAME_UNREGISTERED)
```

`CODENAME_RE = (?<![A-Za-z0-9])([A-Z]{1,4})[-_‑ ]?(\d{1,4})([a-z]?)(?![A-Za-z0-9])`

- **正文**：闭包减 appendix 角色减 `\appendix` 之后减 code env。
- **附录**：允许 `internal` 代号出现；未登记的代号 → `CODENAME_UNREGISTERED`（advisory；L2 红）。
- `\fact{}` 参数先掩码，所以 `\fact{E5}` 不触发。
- `\pkignore` 不豁免。

### 11.3 白名单默认值与迁移

默认白名单＝fact id ∪ bib key ∪ `symbols.json.external`。首版 `external` 必须至少收：`GPT-4`、`GPT-4o`、`LLaMA-3.1-70B`、`M3.1`、`V4.1`、`BERT-3`、`ISO-8601`、`COVID-19`、`SHA-256`、`HTTP-2`、`ATIS-2`、`pytest-10081`、`sphinx-10449`（按本仓出现补全）。

### 11.4 边界

- **抓不到**：`CTX21`（能抓到，`CTX` + 无分隔 + 数字）、`CTX_21`（能）、`CTX‑21`（能）、`CTX 21`（默认 `loose_separator=true` 能）、`ＣＴＸ-２１`（NFKC 后能）、`CTX-021`（能）。
- **抓不到**：`第 21 号上下文分片` 这类语义改写；PNG 里印的字；`ctx-21`（小写——若项目要求，可把 `case_insensitive` 打开，但会误伤 `sha-256`，默认关）。
- **误报**：外部专名未登记（`XYZ-3` 数据集）→ 红，但消息带"请登记到 symbols.json 并给引用"的动作指引；这是 fail-closed 的代价，登记成本一行。
- 与 R-03 的交叉：`GPT-4` 未登记时既是代号红又是 QUANT 红。去重规则：同一 span 只报**优先级最高**的一条（`CODENAME_*` > `UNBOUND_QUANT`），避免一条错两处噪音。

**退出码**：`CODENAME_IN_BODY`/`CODENAME_UNREGISTERED`/`NAKED_FACT_ID` → 1；附录未登记 → 3（L2 升 1）。

---

## 12. 判据 R-10：免责碎片化

### 12.1 输入

- 句子级 BU＋角色（R-15）。
- `disclaimer_patterns.json`（可配置，首版见 §12.4）。
- `\limitation[fact=ID]{...}` 宏。

### 12.2 三条可执行规则

1. **写作期（结构，不靠语义）**
   - 非 `limitations`/`threats` 角色里出现 `\limitation` → `LIMITATION_OUTSIDE`（**红**）。
   - `limitations` 角色里出现**未包宏**的免责句（pattern 命中）→ `LIMITATION_UNMACROED`（advisory，L2 红）。
2. **内容期（回指）**
   - `\limitation[fact=F-11]{...}` 的 fact 必须存在且 `state:valid`；否则 `LIMITATION_BAD_FACT`（红）。
   - 无 `fact=` 的项 → `LIMITATION_UNBOUND`（advisory，L2 红）——"空洞免责"。
3. **分布期（碎片化）**
   - 句子归一化键 `key = lower(strip(\ref{} / 数字 / 标点 / 空白))`。
   - 同一 key 在 **Results 之外**出现 ≥2 次 → `DISCLAIMER_FRAGMENTED`（advisory，exit 3）；≥3 次 → L2 升红。
   - 同一 key 出现在 **Results 之内** → `DISCLAIMER_IN_RESULTS`（红），**但**满足下列任一豁免：
     - 该 BU 含至少一个已绑定的 QUANT（"具体性豁免"：带数据的限定不算套话）；
     - pattern 的 `class == "scope_claim"`（如 "we make no claim of superiority"）→ 降 advisory；
     - 该句是 `\limitation{}` 且位于 threats/limitations 角色。
   - `\ref{sec:limitations}` 出现在 Results（引用式逃逸）→ `LIMITATION_POINTER_IN_RESULTS`（advisory；同一节 ≥2 次升红）。

> 配置开关 `disclaimer.strict_results`（默认 `false`）：置 `true` 时关闭上面三条豁免，Results 内命中即红。默认关闭是因为本仓有正当的 `we make no claim of superiority`（05_eval 第 40 行）；关掉豁免会制造假红，进而导致规则被整体关掉（R-B6 的连锁反应）。

### 12.3 误报/漏报边界

- 误报：审稿人**要求**的范围声明（"仅覆盖 3 个数据集"）——含数字且已绑定 → 具体性豁免。
- 误报：`within noise`、`carries no weight beyond direction` 在 Results 里是正当的统计限定 → 归 `scope_claim` 类，advisory。
- 漏：完全换词（"the reader should temper expectations"）→ 句式表可扩，但永远有地板；这是 advisory 而非红的根本原因。
- 漏：把免责写成 figure caption 或 footnote → caption 是 BU、footnote 是正文，仍覆盖。
- 不做：语义相似度/embedding 聚类（不可复现，模型一换结论就变）。

### 12.4 首版句式表（每个 pattern 必带 class）

| id | class | 触发词（正则，示例） |
|---|---|---|
| D01 | result_hedge | 可能/或许/也许/一定程度上/某种程度上/in some sense/to some extent |
| D02 | result_hedge | 受限于/限于篇幅/有待进一步/尚不能排除/不宜过度解读 |
| D03 | result_hedge | future work/left for future/remains open/we leave ... open |
| D04 | result_hedge | 并非普适/不能推广/not general/does not generalize |
| D05 | scope_claim | we make no claim/make no claim of superiority/not evidence of |
| D06 | scope_claim | within noise/carries no weight/point estimate/one run per arm |
| D07 | boilerplate | 需要注意的是/值得指出的是/it should be noted/it is worth noting |
| D08 | boilerplate | 总而言之/综上所述/in summary（在 Results 内重复时） |

**退出码**：`LIMITATION_OUTSIDE`→1；`DISCLAIMER_IN_RESULTS`→1；`DISCLAIMER_FRAGMENTED`→3（L2 ≥3 次→5）；`LIMITATION_UNBOUND`→3（L2→5）。

---

## 13. 判据 R-11：送达性证据层（回应 R-B8 / 2-B3 / 2-S3 / 2-S4 / 2-S5）

### 13.1 run record（`runs/<run_id>/run.json`，schema `fs-run/2`）

```json
{
  "schema": "fs-run/2",
  "run_id": "B23-SWB16-on-0007",
  "created_at": "2026-10-02T09:14:11Z",
  "writer": {"role": "grader", "uid": "svc-grader", "key_id": "ed25519:AAA..."},
  "runner_sha256": "sha256:...",
  "signed_by": "ed25519:AAA...",
  "record_signature": "base64:...",
  "model": {"name": "DeepSeek V4.1 Flash", "version": "2026-09"},
  "condition_hash": "sha256:...",

  "payload": {"request_body_sha256": "sha256:...", "response_body_sha256": "sha256:..."},
  "delivered": true,
  "attempt_count": 3,
  "tool_call_count": 7,

  "request": {"canonicalization": "jcs-rfc8785", "body_bytes": 1832,
              "body_path": "request.json", "body_sha256": "sha256:..."},
  "response": {"body_sha256": "sha256:...", "body_path": "response.json"},

  "delivery": {
    "evidence": "server_receipt",
    "receipt_id": "srv-7f3a...",
    "received_at": "2026-10-02T09:14:12Z",
    "receipt": {
      "request_body_sha256": "sha256:...",
      "response_body_sha256": "sha256:...",
      "run_id": "B23-SWB16-on-0007",
      "attempt_index": 2
    },
    "signature": {"alg": "ed25519", "key_id": "ed25519:AAA...", "sig": "base64:..."}
  },
  "attempts": [
    {"index": 0, "metrics_path": "attempts/0.json", "metrics_sha256": "sha256:...", "seed": 7, "nonce": "n-0f3a"},
    {"index": 1, "metrics_path": "attempts/1.json", "metrics_sha256": "sha256:...", "seed": 8, "nonce": "n-1b77"},
    {"index": 2, "metrics_path": "attempts/2.json", "metrics_sha256": "sha256:...", "seed": 9, "nonce": "n-2c19"}
  ],
  "aggregation": {"stat": "mean", "n": 3, "over": ["attempt"], "selection_rule": "all",
                  "sha256": "sha256:..."},
  "metrics": {"path": "metrics.json", "sha256": "sha256:...", "derived_from": "attempts"},
  "tool_calls": [{"index": 0, "tool": "bash", "args_sha256": "sha256:..."}],
  "observation": {"path": "observed.json", "sha256": "sha256:...",
                  "extractor": {"role": "extractor", "uid": "svc-extract", "key_id": "ed25519:BBB..."}}
}
```

**字段语义（哪些是证据，哪些只是自洽性）**

- `payload.request_body_sha256` / `payload.response_body_sha256`：**只叫 payload 摘要**。它们等于 `request.body_sha256`/`response.body_sha256` 只证明"同一个文件里两个字段自洽"，**不构成送达性证据，不得出现在 `proof_class` 任何一栏的判定里**（2-B3 第 4 条）。
- `delivery.receipt`：**必须同时钉 `request_body_sha256`、`response_body_sha256`、`run_id`、`attempt_index`**。缺任一项、或任一项与 run.json 不符 → `RECEIPT_SCOPE_MISMATCH`（红）。v2.1 只钉 request，等于"回执证明请求发出过，响应仍可任意"——指标恰恰来自响应。
- `delivery.signature`：对 `receipt` 的 canonical JSON（JCS）做 detached ed25519 签名。验签密钥必须来自**项目目录之外**的 `project.trusted_keys_file`（绝对路径）。密钥文件在项目内、或被 `paperkit.toml` 指向项目内路径 → `TRUSTED_KEYS_IN_PROJECT`（红）。缺密钥 → `proof` 最高 `digest_only`。
- `runner_sha256`：跑出 metrics 的 grader/runner 程序哈希，必须等于 `project.runner_sha256`（登记在签名配置里），否则 L2 `RUNNER_UNPINNED`（COVERAGE，5）。
- `signed_by` / `record_signature`：对 canonical run.json（去掉这两个字段）的 detached 签名。签名者若与服务端回执同一密钥，**不额外提升** `proof`；若是 owner 密钥，可用于 `digest_only` 的摘要清单。未签名 → `proof` 最高 `self_report`。
- `attempts[]`：**一等公民**（2-S5）。`metrics.json` 只能是由 attempts 机械聚合的派生文件；审计重算 `aggregation` 并与 `metrics` 比对，不符 → `AGGREGATION_MISMATCH`（红）。
- `aggregation.selection_rule ∈ {all, mean, median, weighted_mean}`。缺失，或值为 `best|max|min|first|top-k` → `SELECTION_UNREGISTERED`（红）。
- `attempt_count == len(attempts)`，且 `tool_call_count >= attempt_count`（每次 attempt 至少一次调用），否则 `ATTEMPT_COUNT_MISMATCH`（红）。
- `delivery.evidence ∈ {server_receipt, relay_receipt, client_log, none}`；`evidence:"none"` 而 `delivered:true` → `RUN_RECORD_INVALID`。
- 所有摘要字段必须是 `sha256:` 前缀的 64 位十六进制。

### 13.2 角色表（谁写什么——写进规范，不只写进部署清单）

| 产物 | 应写者 | 工具能核什么 |
|---|---|---|
| `runs/<id>/run.json` | grader / 中继进程 | 回执签名、`writer.uid` 与 `observation.extractor.uid` 不同、attempt 数交叉校验 |
| 回执（`delivery`） | 服务端 / 中继 | ed25519 验签（密钥在项目外）＋四项摘要绑定 |
| `attempts/*.json` | grader | 聚合重算、`attempt_count`、nonce 存在性 |
| `observed.json` | 独立抽取进程 | digest、`extractor.uid ≠ writer.uid`（字段自报，见 §13.6） |
| `facts.json` | owner（人签） | 内容哈希签名（§16.2） |
| `sections/*.tex` | 写作 agent | — |

**部署清单（不可由工具代替）**：写作进程的 cwd 只挂载 `sections/` 可写；`runs/`、`facts.json`、`audit/report.json` 对写作进程只读；`trusted_keys_file` 由 owner 持有，写作进程无读权限。

### 13.3 fact 侧

`observation: {run_id, pointer}` 指向 `runs/<id>/observed.json`（记录时从 payload 抽出的观测快照，digest 钉在 run.json 里），**不**指向可能被重写的原始 payload。

### 13.4 校验算法（L1）——**审计器只读**

```
REF_SET = marker_refs ∪ table_map_refs ∪ table_spec_refs
        ∪ figure_sidecar_refs ∪ factblock_refs ∪ pair_with_refs     # 2-S4

for f in REF_SET:
    r = load(runs/f.observation.run_id/run.json)      # 缺 -> PROOF_MISSING(unverified)
    schema_ok(r) or RED(RUN_RECORD_INVALID)
    sha256(observed.json) == r.observation.sha256     or RED(OBSERVATION_DIGEST_MISMATCH)
    resolve_pointer(observed.json, f.observation.pointer) exists
        or RED(OBSERVATION_POINTER_MISSING)
    value_at_pointer == f.value (精确，按 R-01 规范键)   or RED(OBSERVATION_VALUE_MISMATCH)
    if r.delivered != true:
        RED(INVALID_FACT_CITED)                       # 只报，不改账
        # v2.1 的 mark f.state=invalid 删除（2-S3）：
        # 审计器写 facts.json 会断 digest 链、立刻让报告过期
    if r.delivery.receipt missing any of 4 fields:
        RED(RECEIPT_SCOPE_MISMATCH)
    if r.delivery.evidence == "server_receipt":
        verify(r.delivery.signature, trusted_keys_out_of_band)
            or RED(RECEIPT_SIGNATURE_INVALID)
        # 且 receipt.request_body_sha256/response_body_sha256/run_id/attempt_index 四项全等
    elif r.delivery.evidence == "client_log":
        proof = min(proof, self_report)
    if r.attempt_count != len(r.attempts): RED(ATTEMPT_COUNT_MISMATCH)
    if r.aggregation.selection_rule not in REGISTERED: RED(SELECTION_UNREGISTERED)
    if recompute(r.attempts, r.aggregation) != reads(r.metrics): RED(AGGREGATION_MISMATCH)
    if r.runner_sha256 != project.runner_sha256: RED(RUNNER_UNPINNED)
    if r.signed_by and r.record_signature:
        verify(r.record_signature, key=r.signed_by) or RED(RUN_RECORD_INVALID)
    else:
        proof = min(proof, self_report)
    if r.observation.extractor.uid == r.writer.uid: proof = min(proof, self_report)

# 覆盖承诺（2-S4）
if any(f in REF_SET not validated):
    proof = min(proof, self_report)
    RED(PROOF_COVERAGE_GAP)      # COVERAGE tier

# 全局不变量（2-S3）
AUDIT_WRITES_NOTHING：
  允许写 = {audit/report.json, .paperkit/cache/**, audit/stamp.json(仅 release)}
  越界写 → exit 4
```

同时校验 `facts.json` 引用的每个 `source`：`source_sha256` 必须等于该 source 文件现值；若 source 是某个 run 的 payload，则 `source_sha256 == run.request.body_sha256`。

### 13.5 `proof_class` 与信任边界

| class | 谁签发 | 能证明 | 不能证明 |
|---|---|---|---|
| `server_signed` | 服务端/中继回执，签名密钥在**项目外** | 这个 request **和这个 response** 到达过服务端（四项摘要绑定），且 run_id/attempt 对得上 | 服务端真的跑了这个模型（除非回执含模型 id）；指标真的由这次响应产生（除非回执含 metrics 摘要） |
| `digest_only` | 发布作业签名的摘要清单 | 账上引用的 payload 与清单里的摘要一致 | payload 本体存在；是否真的发出 |
| `self_report` | 客户端日志 / 同源进程所写 | 客户端*声称*发了 | 任何送达性 |
| `absent` | 无 | 无 | 全部 |

报告 `proof` ＝ `REF_SET` 里**最弱**的一级；有任一 fact 未被验证 ⇒ 封顶 `self_report`。`release` 要求 `proof ∈ project.require_proof_class`（默认 `["server_signed","digest_only"]`）。

**写死的边界（必须原样进 README 与报告）**：

> 本工具**不能发现**"同一个 agent 同时伪造 `runs/` 与 `facts.json`，并自带密钥写进 `trusted_keys`"这种攻击。
> 它只能保证：**回执签名对得上、回执绑定的 request/response 与账上摘要一致、attempt 集合自洽**。
> 它**不能**证明：payload 真的被发出过；服务端真的处理了它；指标真的由这次响应产生；agent 没有藏起其它 attempt。
> `trusted_keys` 在项目外、`runs/` 由另一 uid 写，是**部署前提**，不是工具能强制的性质（v2.1 已因 CLI 无法降权而驳回同类命题，本版维持）。

### 13.6 误报/漏报边界

- 误报：run record 晚于 fact 生成（先有账后有记录）→ `PROOF_MISSING` 只在 L2 红；L1 记 unverified。
- 漏：`delivered:true` 但服务端从未收到（客户端伪造）——见 §13.5。
- 漏：**被藏起来的 attempt**（跑 30 次只写 1 条）。若服务端回执只覆盖最后一次、且工具调用记录也被同一进程伪造，则不可见。缓解：`ATTEMPT_COUNT_MISMATCH`、预注册 `selection_rule`、nonce（`NONCE_ABSENT` 在 L2 升红）。这是 §1.4-3 接受的风险。
- 漏：`observed.json` 由与 run 同 uid 的进程抽取（字段自报）。缓解：uid 相同 ⇒ `proof` 封顶 `self_report`；声明本身可伪造，这是证据层的上限。
- 漏：缓存复用旧 metrics 且 attempt 相同——nonce 存在时可区分；`NONCE_ABSENT` 在 L2 红。
- **缺席 ≠ 矛盾**：没有 run record → `PROOF_MISSING`（unverified），**不**是红；只有记录里明确 `delivered:false` 或摘要不符才红。这条是防止内部 S5 的"48 条全红"重演。

**退出码**：`RUN_RECORD_INVALID`/`INVALID_FACT_CITED`/`OBSERVATION_*`/`RECEIPT_*`/`ATTEMPT_COUNT_MISMATCH`/`SELECTION_UNREGISTERED`/`AGGREGATION_MISMATCH`/`TRUSTED_KEYS_IN_PROJECT` → 1；`PROOF_MISSING` → 0（默认）/8（`--gate`）；`PROOF_COVERAGE_GAP` → 5（L2）/3（L0）；`--require-proof` 下 → 6；`AUDIT_WRITES_NOTHING` → 4。

**fixture**：`hostile/2-B3/`、`benign/2-B3/`（回执与密钥）；`hostile/2-S3/`、`benign/2-S3/`（审计只读）；`hostile/2-S4/`、`benign/2-S4/`（`REF_SET`）；`hostile/2-S5/`、`benign/2-S5/`（attempt 聚合）。

---

## 14. 判据 R-12：分层（L0/L1/L2）与反滥用

### 14.1 三层

| 层 | 跑什么 | 需要 runs/ | 典型场景 |
|---|---|---|---|
| **L0** | 静态：QUANT、`\fact` 闭包、闭包覆盖、R-01A 渲染可归责性、表/图映射、`\pkignore`、TODO 渲染、代号、免责、账本 schema、STALE_LEDGER | 否 | 本地写作、PR 快速反馈 |
| **L1** | L0 ＋ run record／observation／摘要／INVALID／attempt 聚合 | 是（或摘要清单） | 投稿前、实验批次结算 |
| **L2** | L1 ＋ coverage 全绿＋`REF_SET` 全覆盖＋报告新鲜度＋`proof_class` 达标＋**PDF 回检** | 是 | CI 发布门、`release` |

`--level l0|l1|l2`；默认 auto：有 `runs/` → l1，否则 l0。

**`PASS` 只在 L2 存在。** L0/L1 无论多干净，`verdict` 都是 `UNVERIFIED`——因为"审计集完整"这个承诺（coverage）在 L0/L1 是 deferred 的，而 §0 的保证依赖它。

### 14.2 阻断规则（写死）

```
if any FACT red:                 verdict=RED;  exit=1        # 任何层
if any CONFIG/INTERNAL error:    verdict=RED;  exit=2|4
if level < L2:
    verdict = UNVERIFIED
    exit = 8 if (--gate or --ci or --min-level > level) else 0
    print_banner("本次只跑了 Lx ...")        # 不含大写 PASS
elif coverage not clean:         verdict=RED;  exit=5
elif proof not sufficient:       verdict=RED;  exit=5|6
elif advisories or downgraded:   verdict=ADVISORY; exit=3
else:                            verdict=PASS; exit=0
```

- `--min-level l2` 未达标 ⇒ **exit 8**（v2.1 这里是 0，是本轮最危险的一条）。
- `--strict` ≡ `--gate --level l2`（语义从"尽量严"变成"必须是 PASS，否则非零"）。
- `--gate`/`--ci` 只改 `UNVERIFIED` 的退出码，不改别的判定。
- `--require-proof` 把 `PROOF_MISSING` 从 8 升到 6。

### 14.3 反滥用规则（2-B4 / 2-G4）

1. **`UNVERIFIED` 不得计入 PASS**：JSON 的 `verdict` 字段、人类输出、CI 判定式三处一致。
2. **必须打印"本次只跑了 Lx"**：横幅是契约的一部分（`banner` 字段进 JSON），且**不得含大写 `PASS` 字样**。
3. **`release` 强制 L2**：`release` 内部先跑 `audit --level l2 --gate`，`verdict != PASS` 直接拒绝（exit 1/5/6），不生成 stamp。
4. **升红表是代码常量**（`ESCALATE_AT_L2`），`rules.json` 只能把 false 改成 true。任何放宽必须在 `rules.json` 里带 `signed_by` 与 `reason`，且报告列出 `downgraded_rules: [...]`，`verdict` 至少为 `ADVISORY`（exit 3）。
5. **单调性 review**：任何使 hostile fixture 由红变绿的改动，必须在同一 PR 里更新 `rules_sha256` 的说明与 §21/§20.1 的期望值；CI 检查 `rules_sha256` 变了但 fixture 期望没变 → `RULE_CHANGE_UNREVIEWED`（红，CONFIG）。

### 14.4 CI 契约（写死，发布脚本必须照抄）

```bash
paperkit audit --level l2 --gate --json > audit.json
rc=$?
[ $rc -eq 0 ] || exit $rc          # 红/未达层原样透传（1/5/6/8）
python3 -c 'import json,sys; sys.exit(0 if json.load(open("audit.json"))["verdict"]=="PASS" else 1)'
```

判定式：**`exit == 0 && verdict == "PASS"`**。只读 exit 或只读 verdict 都不够；任何"stdout 含 PASS"的 grep 都是错的（横幅已去除该字样）。

### 14.5 边界

- 误报：团队把 `--strict` 理解成"全绿"，看到 `UNVERIFIED` 以为失败 → 横幅＋报告 `verdict` 双写，且 `release` 拒绝，语义清晰。
- 漏：CI 只跑 L0 却对外宣称"审计通过" → `report.level` 与 `report.proof` 落在 JSON 里；`--gate` 下 exit 8；`release` 强制 L2。
- 误报：L1 有 runs/ 但都是 `self_report` → `proof=self_report`，L2 时 `PROOF_CLASS_INSUFFICIENT`（COVERAGE，5）。`--require-proof` 只影响 exit 6 的显式开关。

**fixture**：`hostile/2-B4/`、`benign/2-B4/`（L0 未达层 vs L2 全绿）；`hostile/2-G4/`、`benign/2-G4/`（verdict/exit/横幅）。

**退出码**：见 §2.3。

---

## 15. 判据 R-13：TOCTOU、报告新鲜度与 `release`

### 15.1 `audit/report.json`

```json
{
  "schema": "paperkit-report/2.2",
  "tool": {"version": "2.2.0", "rules_sha256": "sha256:..."},
  "generated_at": "2026-11-08T10:00:00Z",
  "level": "L2",
  "verdict": "PASS|ADVISORY|UNVERIFIED|RED",
  "red_class": "FACT|CONFIG|COVERAGE|PROOF|STALE|INTERNAL|null",
  "exit": 0,
  "proof": "digest_only",
  "strength": "containment_only",
  "banner": "本次只跑了 L2 ...",
  "downgraded_rules": [],
  "inputs": {
    "main.tex": "sha256:...",
    "sections/05_eval.tex": "sha256:...",
    "results_body.txt": "sha256:...",
    "tables/t1_main.tex": "sha256:...",
    "facts.json": "sha256:...",
    "refs.bib": "sha256:...",
    "paperkit.toml": "sha256:...",
    "symbols.json": "sha256:...",
    "roles.json": "sha256:...",
    "rules.json": "sha256:...",
    "trusted_keys_file": "sha256:..."
  },
  "input_set_sha256": "sha256:...",
  "number_ledger": [
    {"raw":"10/16","key":"frac:10/16","file":"sections/05_eval.tex","line":17,"col":57}
  ],
  "report_sha256": "sha256:...",
  "counts": {"files": 18, "facts": 48, "quant": 355, "bound": 355, "unbound": 0},
  "issues": [
    {"code":"UNBOUND_QUANT","rule":"R-03","tier":"FACT","severity":"red",
     "file":"sections/05_eval.tex","line":17,"col":57,
     "token":"12.3","expected":["10/16","62.5%"],"actual":"12.3",
     "message":"...","action":"绑定到 A2 或改写","span_id":"s-0042"}
  ],
  "coverage": {"root":"main.tex","closure":["..."],"orphans":[],"tables":["..."],
                "figures":["..."],"ref_set":["A2","A3"],"unvalidated":[]},
  "proof_summary": {"runs": 12, "valid": 10, "invalid": 1, "missing": 1,
                     "attempts": 3, "referenced_facts": 42, "validated_facts": 40}
}
```

- `inputs` 必须覆盖**审计读过的每一个文件**（含配置文件、闭包内全部文本文件、facts、bib、`rules.json`、`trusted_keys_file`）。
- `verdict` 唯一；`exit` 由它唯一决定（§2.3）；`status` 字段不存在。
- `report_sha256 = sha256(canonical_json(payload 去掉 report_sha256))`。
- `audit --check-fresh audit/report.json`：重算 `inputs`，任一不符 → exit 7，并列出差异文件。

### 15.2 `release` 与 stamp（2-S7）

```
release:
 1) audit --level l2 --gate           # verdict 必须是 PASS，否则拒绝
 2) 重哈希全部 inputs[]（TOCTOU）      # 任一不符 → REPORT_STALE(7)
 3) 只编译被审计的 root_tex           # root 变更需签名；否则 ROOT_TEX_CHANGED
 4) 记录实际编译输入清单 jobname/latexmk_inputs[]（编译钩子或 .fls 解析）
 5) 生成 audit/stamp.json：
    {
      "report_sha256": "...", "input_set_sha256": "...",
      "tool_version": "2.2.0",
      "compiled": {
        "root_tex": "main.tex", "root_sha256": "sha256:...",
        "jobname": "main",
        "latexmk_inputs": [{"path":"main.tex","sha256":"..."},
                           {"path":"sections/05_eval.tex","sha256":"..."}],
        "pdf_sha256": "sha256:..."
      },
      "signed_by": "owner-key-id", "signature": "base64:..."
    }
 6) verify-pdf（见 15.3）
 7) 写 PDF 元数据戳（\hypersetup{pdfkeywords={paperkit-stamp:<report_sha256>}}）
```

- **审计范围与产物范围必须相等**（2-S7）：`latexmk_inputs` 里出现任何不在 `report.coverage.closure ∪ 非文本输入` 里的文件 → `COMPILE_SCOPE_MISMATCH`（红，`release` 拒绝）。这就堵住"审 `main.tex`、编 `release.tex`"。
- `paperkit build` **只做排版预览**：不检查报告；输出 PDF 头注释 `% UNSTAMPED PREVIEW`。
- 无 stamp 的 PDF → `STAMP_MISSING`（`release` 拒绝；`verify-pdf` 非零）。
- **边界**：本地 `latexmk` 永远能绕过。stamp 的作用是"可检出"，不是"不可能"。这是诚实的能力边界，写进 README（§1.4-5）。

### 15.3 `verify-pdf` 契约（强制检出点，2-S7 的最小可行实现）

```bash
# 发布脚本必须调用；退出码即发布闸
paperkit verify-pdf paper.pdf --report audit/report.json
# 0 = stamp 有效且 PDF 内数字全部可归责
# 5 = PDF_UNACCOUNTED_NUMBER 或 STAMP_MISSING（COVERAGE）
# 3 = 仅 STAMP_UNVERIFIED（advisory，可放行但要人看）
# 7 = PDF 内 stamp 与当前报告不一致（报告过期或被换）
```

检查项：
1. PDF 元数据里的 `paperkit-stamp:<report_sha256>` 存在且等于 `report.report_sha256`；
2. `stamp.compiled.pdf_sha256 == sha256(paper.pdf)`；
3. PDF 文本里抽出的每个数字都在允许集内（R-01A 的 `PDF_UNACCOUNTED_NUMBER`）。

**平台边界**：arXiv 不检查这个戳。人工上传一份没 stamp 的 PDF，平台不会拦。我们只能保证"可检出"，并给出上面这段脚本；这是 §1.4-5 接受的风险。

**退出码**：`REPORT_STALE`→7；`release` 在 `verdict!=PASS`→1/5/6；`COMPILE_SCOPE_MISMATCH`→1；`STAMP_MISSING`→5；`STAMP_UNVERIFIED`→3；`PDF_UNACCOUNTED_NUMBER`→5。

**fixture**：`hostile/2-S7/`、`benign/2-S7/`（stamp 绑定编译面、rules 只加严）。

---

## 16. 判据 R-14：账本变更、签名与权限

### 16.1 append-only

- `facts.json` 的每条 fact 带 `state` 与 `supersedes`；修改＝追加新条目 + 旧条目 `state:"superseded"`。原地改 `value` → `LEDGER_MUTATED`（红，通过 `digest_prev` 链检测）。
- `facts.json` 顶部 `digest_prev` = 上一版文件的 sha256；`paperkit ledger append` 自动维护。链断 → `LEDGER_CHAIN_BROKEN`（红）。
- 每次变更记录 `{by, at, reason, evidence: {run_id, pointer}}`；缺 reason/evidence → `LEDGER_EDIT_UNEVIDENCED`（红）。
- **审计器只读**（2-S3）：`AUDIT_WRITES_NOTHING`。`delivered:false` 不改 fact 状态；状态变更只能走 `paperkit ledger invalidate <id> --key <key_id>`（人签、append-only、写新条目）。

### 16.2 签名的对象＝内容哈希（2-B5）

`paperkit ledger approve <id> --key <key_id>` 的签名对象是：

```
approve_target = sha256(canonical_json(JCS, {
  id, value, display[], source_sha256, run_id,
  observation: {run_id, pointer}, condition_hash, aggregation,
  setting, co_claim, anchor, pair_with,
  rules_sha256,          # 审计上下文，防止"改规则后重放旧签名"
  config_sha256          # paperkit.toml + symbols.json + roles.json + disclaimer_patterns.json
}))
```

- 签名是 detached ed25519（`ssh-keygen -Y sign` 或 `minisign`）；签名文件 `facts.approvals/<id>@<target-prefix>.sig`。
- **签名人身份来自密钥**（`key_id`），`by` 字段降级为"显示名"，不参与判定。
- `release` 时**重验全部签名**（一次签名可被复用一万次，除非签名体含 `input_set_sha256`；`release` 另外把 `input_set_sha256` 写进 stamp）。
- 新追加的 fact 条目若 `approve_target` 与旧条目不同且没有对应新签名 → `APPROVAL_STALE`（红）。这是 2-B5 的核心：人签的是"A2 = 0.91"，不是"A2"。
- `rules.json`/`symbols.json`/`roles.json`/`disclaimer_patterns.json` 同样需要 owner 签名，因为它们直接改变判定面；未签名 → `CONFIG_UNSIGNED`（黄，L2 红）。
- 一次批准 >10 条 → `APPROVAL_BATCH_LARGE`（黄），报告单列批次。

### 16.3 签名工具缺失

L0/L1 不需要签名工具；L2/release 需要。缺 `ssh-keygen`/`minisign` → `SIGNATURE_TOOL_MISSING`（CONFIG，exit 2），**不得**静默降级为"未签名也算过"。

### 16.4 共谋检测（advisory）

同一次提交里 `facts.json` 与正文的 diff 行集合重合度 > 0.6 且涉及同一 fact id → `LEDGER_TEXT_COCHANGE`（advisory；L2 需人签）。

### 16.5 权限

- 本工具**不**提供进程级只读（驳回理由见 §1）。部署清单要求：写作进程的 cwd 只挂载 `sections/` 可写；`facts.json`/`audit/report.json`/`runs/` 由 owner 只读、写作进程另一 uid；报告由独立进程重算。
- `paperkit release` 检测 `facts.json` 的 mtime 是否早于本次 audit 启动（并发改账）→ `LEDGER_CONCURRENT_EDIT`（红）。
- **`runs/` 进权限清单**（2-B3）：v2.1 的 uid 分离清单只覆盖 `sections/` vs `facts.json`，漏掉了证据链的根。本版明确：`runs/` 由 grader 写，写作进程只读。

**退出码**：`LEDGER_MUTATED`/`LEDGER_CHAIN_BROKEN`/`LEDGER_EDIT_UNEVIDENCED`/`LEDGER_CONCURRENT_EDIT`/`APPROVAL_STALE`/`CO_CLAIM_ASYMMETRIC`→1；`APPROVAL_BATCH_LARGE`/`CONFIG_UNSIGNED`→3（L2 的 `CONFIG_UNSIGNED`→5）；`SIGNATURE_TOOL_MISSING`→2。

---

## 17. 判据 R-15：章节角色（位置型规则的地基）

### 17.1 输入

`roles.json`（显式，不猜标题）＋可选 `\sectionrole{results}` 受控宏。

```json
{"schema":"roles/1",
 "default":"body",
 "files":{"sections/00_abstract.tex":"abstract",
          "sections/01_intro.tex":"intro",
          "sections/03_system.tex":"method",
          "sections/04_mechanisms.tex":"method",
          "sections/05_eval.tex":"results",
          "sections/06_ablation.tex":"results",
          "sections/07_threats.tex":"limitations",
          "sections/08_conclusion.tex":"conclusion",
          "appendix/a_tasks.tex":"appendix",
          "appendix/b_repro.tex":"appendix"},
 "inline":{"\\sectionrole{...}": true}}
```

- 角色 ∈ `abstract|intro|related|method|results|discussion|limitations|conclusion|appendix|body`。
- 文件级角色优先；`\sectionrole{}` 可在文件内覆盖后续内容。
- 闭包内有 `.tex` 未在 `roles.json` 且无 `\sectionrole` → `SECTION_ROLE_UNKNOWN`（COVERAGE；L0 黄，L2 红）。
- **正文包含集**：abstract、intro、related、method、results、discussion、conclusion、body；含脚注、caption、表格、数学。
- **正文排除集**：appendix 角色、`\appendix` 之后、`verbatim/lstlisting/minted`、`\bibliography` 段。
- `limitations` 允许免责；`results` 受 R-10 约束；`method` 允许代号？不——代号在所有正文角色都红（附录才放行）。

### 17.2 边界

- 误报：作者把 limitations 写在 `07_threats.tex`，标题叫 "Threats to Validity"——用 `roles.json` 显式解决，名字随便叫。
- 漏：同一文件里前半 method 后半 results（`\sectionrole` 可覆盖；不写则按文件级，可能误判一处分界）。
- 误报：`\input` 展开后的角色继承——子文件默认继承父文件角色，除非自己在 `roles.json` 里有条目。

**退出码**：`SECTION_ROLE_UNKNOWN`→5（L2）/3（L0）。

---

## 18. 判据 R-16：超时、增量、异常

- **超时＝失败**：`audit` 默认 120s；超时 → exit 4，消息含"超时不是跳过"。禁止 fail-open。
- **增量缓存**：`.paperkit/cache/`，键＝`hash(文件内容) + rules_sha256 + level`；**不用 mtime**（驳回内部建议的 mtime 跳过：checkout 会重置 mtime，导致漏扫）。
- 缓存命中只跳过"文件级静态规则"，**不跳过**跨文件规则（闭包、重复 value、代号全局统计）。
- 并行：文件级并行（`--jobs N`，默认 CPU 数一半）；汇总阶段串行，保证 issue 顺序稳定（按 file,line,col,code 排序）。
- 异常一律 exit 4，并在 JSON 里带 traceback 摘要；**绝不**把异常降级成 advisory。

---

## 19. 报告与错误码（`--json`）

### 19.1 issue 形状（所有 code 统一）

```json
{"code":"BOUND_MISMATCH","rule":"R-03","tier":"FACT","severity":"red",
 "file":"sections/05_eval.tex","line":17,"col":57,"end_col":61,
 "token":"1/16","expected":["10/16","62.5%"],"actual":"1/16",
 "message":"该句绑定 A2，但 1/16 不在 A2 的可显示集里",
 "action":"改回 10/16，或把该数登记为 A2 的 display",
 "span_id":"s-0042"}
```

人类输出必须按 tier 分组（`[红/FACT]`、`[红/COVERAGE]`、`[黄]`），并在首行打印横幅（若 `UNVERIFIED`），结尾打印 `verdict: <...>`、`level: <Lx>`、`exit: <n>`、`strength: containment_only` 与 `proof: <class>`。

### 19.2 错误码注册表（首版，稳定不改名）

| code | tier | exit | 规则 |
|---|---|---|---|
| `UNBOUND_QUANT` | FACT | 1 | R-03 |
| `BOUND_MISMATCH` | FACT | 1 | R-03 |
| `BINDING_ATTRIBUTION` | FACT | 1 | R-03（2-S1） |
| `FACT_SET_OVERLAP` | FACT | 1 | R-03（2-S1） |
| `CO_CLAIM_ASYMMETRIC` | FACT | 1 | R-03 |
| `FACT_UNUSED_IN_SPAN` | FACT | 1 | R-03 |
| `FACT_OUT_OF_SPAN` | FACT | 1 | R-03 |
| `NONQUANT_BACKS_QUANT` | FACT | 1 | R-03 |
| `FACT_UNKNOWN_ID` | FACT | 1 | R-03 |
| `DISPLAY_ORDER` | FACT | 1 | R-03 |
| `ANCHOR_MISSING` | FACT | 1 | R-03（2-S2） |
| `PAIR_MISSING` | FACT | 1 | R-03（2-S2） |
| `MARKER_TRAILING` | ADVISORY | 3 | R-02 |
| `FACT_WITHOUT_QUANT` | ADVISORY | 3 | R-03 |
| `DUPLICATE_BINDING` | ADVISORY | 3 | R-03 |
| `FACT_AMBIGUOUS_BINDING` | ADVISORY | 3 | R-03 |
| `FACT_MULTISETTING` | **FACT** | 1 | R-03（2-S8，结构性判据） |
| `SPAN_TOO_LONG` | ADVISORY | 3 | R-02 |
| `DISPLAY_INCONSISTENT` | FACT | 1 | R-04 |
| `DISPLAY_ROUNDTO_INVALID` | CONFIG | 2 | R-04（2-B2） |
| `DISPLAY_APPROX` | ADVISORY | 3 | R-04 |
| `VALUE_NOT_STRING` | CONFIG | 2 | R-04 |
| `VALUE_NOT_QUANT` | FACT | 1 | R-04 |
| `STALE_LEDGER` | FACT | 1 | R-04 |
| `DUPLICATE_ID` / `LEDGER_CONFLICT` / `DUPLICATE_VALUE` | FACT / ADVISORY | 1 / 3 | R-04（v1 沿用） |
| `LEDGER_MUTATED` | FACT | 1 | R-14 |
| `LEDGER_CHAIN_BROKEN` | FACT | 1 | R-14 |
| `LEDGER_EDIT_UNEVIDENCED` | FACT | 1 | R-14 |
| `LEDGER_CONCURRENT_EDIT` | FACT | 1 | R-14 |
| `APPROVAL_STALE` | FACT | 1 | R-14（2-B5） |
| `LEDGER_TEXT_COCHANGE` | ADVISORY | 3 | R-14 |
| `APPROVAL_BATCH_LARGE` | ADVISORY | 3 | R-14 |
| `CONFIG_UNSIGNED` | ADVISORY（L2 升 COVERAGE） | 3 / 5 | R-14 |
| `SIGNATURE_TOOL_MISSING` | CONFIG | 2 | R-14 |
| `INPUT_TARGET_MISSING` | COVERAGE | 5 | R-05 |
| `INPUT_OUTSIDE_PROJECT` | COVERAGE | 5 | R-05 |
| `INPUT_DYNAMIC_TARGET` | COVERAGE | 5 | R-05（2-S6） |
| `UNREGISTERED_INPUT_WRAPPER` | COVERAGE | 5 | R-05（2-S6） |
| `ROOT_TEX_CHANGED` | COVERAGE | 5 | R-05（2-S6） |
| `ORPHAN_TEX` | COVERAGE | 5 | R-05 |
| `APPENDIX_UNREACHABLE` | COVERAGE | 5 | R-05 |
| `UNSCANNED_TEX` | COVERAGE | 5 | R-05 |
| `TABLE_UNBOUND` | COVERAGE | 5 | R-06 |
| `TABLE_DRIFT` | COVERAGE | 5 | R-06 |
| `TABLE_BARE_LITERAL` | COVERAGE | 5 | R-06（2-S4） |
| `FIGURE_UNBOUND` | COVERAGE | 5 | R-06 |
| `FIGURE_UNVERIFIED` | ADVISORY | 3 | R-06 |
| `PKIGNORE_QUANT` | FACT | 1 | R-07 |
| `EXEMPTION_MACRO_SUSPECT` | FACT | 1 | R-07 |
| `IGNORE_NOT_TRACKED` | ADVISORY | 3 | R-07 |
| `TODO_IN_PDF` | FACT | 1 | R-08 |
| `TODO_MACRO_DEF` | ADVISORY | 3 | R-08 |
| `TODO_REQUIRED_OPEN` | COVERAGE | 5 | R-08 |
| `TODO_CLOSED_WITHOUT_EVIDENCE` | FACT | 1 | R-08 |
| `TODO_NOT_TRACKED` | COVERAGE | 5 | R-08 |
| `TODO_COMMENT` | ADVISORY | 3 | R-08 |
| `TODO_ORPHANED` | ADVISORY | 3 | R-08 |
| `CODENAME_IN_BODY` | FACT | 1 | R-09 |
| `CODENAME_UNREGISTERED` | FACT | 1 | R-09 |
| `NAKED_FACT_ID` | FACT | 1 | R-09 |
| `LIMITATION_OUTSIDE` | FACT | 1 | R-10 |
| `DISCLAIMER_IN_RESULTS` | FACT | 1 | R-10 |
| `LIMITATION_BAD_FACT` | FACT | 1 | R-10 |
| `DISCLAIMER_FRAGMENTED` | ADVISORY | 3 | R-10 |
| `LIMITATION_UNBOUND` | ADVISORY | 3 | R-10 |
| `LIMITATION_POINTER_IN_RESULTS` | ADVISORY | 3 | R-10 |
| `RUN_RECORD_INVALID` | FACT | 1 | R-11 |
| `INVALID_FACT_CITED` | FACT | 1 | R-11 |
| `OBSERVATION_DIGEST_MISMATCH` | FACT | 1 | R-11 |
| `OBSERVATION_POINTER_MISSING` | FACT | 1 | R-11 |
| `OBSERVATION_VALUE_MISMATCH` | FACT | 1 | R-11 |
| `RECEIPT_SCOPE_MISMATCH` | FACT | 1 | R-11（2-B3） |
| `RECEIPT_SIGNATURE_INVALID` | FACT | 1 | R-11（2-B3） |
| `TRUSTED_KEYS_IN_PROJECT` | FACT | 1 | R-11（2-B3） |
| `RUNNER_UNPINNED` | COVERAGE | 5 | R-11 |
| `ATTEMPT_COUNT_MISMATCH` | FACT | 1 | R-11（2-S5） |
| `SELECTION_UNREGISTERED` | FACT | 1 | R-11（2-S5） |
| `AGGREGATION_MISMATCH` | FACT | 1 | R-11（2-S5） |
| `PROOF_MISSING` | —（verdict=UNVERIFIED） | 0 / 8 | R-11 |
| `PROOF_COVERAGE_GAP` | COVERAGE | 5 | R-11（2-S4） |
| `PROOF_CLASS_INSUFFICIENT` | COVERAGE | 5 | R-11 |
| `AUDIT_WRITES_NOTHING` | INTERNAL | 4 | R-11（2-S3） |
| `REPORT_STALE` | —（RED/STALE） | 7 | R-13 |
| `SECTION_ROLE_UNKNOWN` | COVERAGE | 5 | R-15 |
| `SHELL_ESCAPE` | FACT | 1 | R-05 |
| `ARITH_IN_BODY` | FACT | 1 | R-01A（2-B1） |
| `NUMERIC_IN_MACRO` | FACT | 1 | R-01A（2-B1） |
| `NUMERIC_MACRO_IN_BODY` | FACT | 1 | R-01A |
| `NUM_ADJACENT_MACRO` | FACT | 1 | R-01A（2-B1） |
| `NUM_AFTER_GROUP` / `NUM_ADJACENT_GROUP` | FACT | 1 | R-01A（2-B1） |
| `PDF_UNACCOUNTED_NUMBER` | COVERAGE | 5 | R-01A（2-B1） |
| `PDF_TOOL_MISSING` | CONFIG | 2 | R-01A |
| `LOW_CONF_IN_HEADLINE` | FACT | 1 | R-04 |
| `VALUE_HAS_PROSE` | ADVISORY | 3 | R-04 |
| `ABSOLUTE_SOURCE_ROOT` | FACT | 1 | R-04 / S5 |
| `EXTRACT_FORBIDDEN_SOURCE` | CONFIG | 2 | R-04 |
| `SPELLED_QUANT` | ADVISORY（L2 升 FACT） | 3 / 1 | R-01 |
| `CJK_QUANT_SUSPECT` | ADVISORY | 3 | R-01 |
| `APPROX_UNBOUND` | FACT | 1 | R-01 |
| `QUANT_TOKEN_OVERLAP` | INTERNAL | 4 | R-01 |
| `LIMITATION_UNMACROED` | ADVISORY（L2 升 COVERAGE） | 3 / 5 | R-10 |
| `CONDITIONAL_TEXT` | ADVISORY | 3 | R-08 |
| `NONCE_ABSENT` | ADVISORY（L2 升 FACT） | 3 / 1 | R-11（2-S5） |
| `STAMP_MISSING` | COVERAGE | 5 | R-13 |
| `STAMP_UNVERIFIED` | ADVISORY | 3 | R-13 |
| `COMPILE_SCOPE_MISMATCH` | FACT | 1 | R-13（2-S7） |
| `SPEC_LINT` | CONFIG | 2 | §19.3（2-S2） |
| `RULE_CHANGE_UNREVIEWED` | CONFIG | 2 | §14.3（2-G4） |
| `SOURCE_SHA256_MISMATCH` / `MISSING_SOURCE` / `SOURCE_NOT_SIGNED` | FACT | 1 | v1 沿用 |

**已删除/更名的码**（避免两套实现分叉）：`RECEIPT_DIGEST_MISMATCH` → `RECEIPT_SCOPE_MISMATCH`；`RETRY_ATTEMPT_MISMATCH` → `ATTEMPT_COUNT_MISMATCH`；`FACT_MULTISETTING` 从 ADVISORY 升 FACT；`status` 字段删除。

### 19.3 规范自检（`SPEC_LINT`，2-S2）

CI 跑 `paperkit spec-lint SPEC-V2.2.md src/paperkit/`：
1. 抽取正文里所有反引号标识符（`[A-Z][A-Z0-9_]{3,}` 与 snake_case 字段名）；
2. 凡出现在"判据/算法/边界"段落、但既不在 §19.2 注册表、也不在 schema 字段表、也没有 `INFO(` 声明的标识符 → `SPEC_LINT`（exit 2）；
3. 凡在 §5/§8/§13 被称作"缓解/检查"的名词，必须在注册表里有对应 code，否则构建失败。
4. 非 issue 标识符：INFO 级（如 `INPUT_NON_TEXT`）登记在 `INFO_CODES`，**明确驳回**的标识符（如 `INPUT_NONDETERMINISTIC`）登记在 `REJECTED_IDS` 并附 §1.4 行号；两张表都参与 `SPEC_LINT`，但都不进 issue 注册表。

这条直接回应 2-S2：**"§19 注册表里没有的码，就是不会实现的码"**。v2.1 的 `anchor`/`pair_with`/`paircheck` 之所以是空话，就是因为没有这条自检。

---

## 20. 实施顺序（先冻结夹具，再重构）

> 沿用第 1 轮结论并加一条硬约束：**夹具的 `expected` 来自本规范的条款，不来自当前实现读数**（2-G4）。当前读数只记进 `observed` 字段。

### 20.1 第一步（0.5–1 天）：冻结回归面

1. 把 `paper/` 打成只读快照（测试里 `shutil.copytree` 到 tmp，**永不**改原目录）。
2. 锁定读数并写进 `tests/fixtures/v22/paper/baseline.json`：
   `facts 48 / 绑定 token 234 (bound 234, unbound 0) / 绑定级红 0 / advisory 11`；
   另记当前 `--strict` 的 exit（预期 1 或 8，取决于实现阶段），**只作 observed**。
3. 建 `tests/fixtures/v22/{hostile,benign}/`；每条 fixture 一个目录，含：
   `main.tex`（或待测文件）、`facts.json`、可选 `runs/`、`case.toml`：
   ```toml
   id = "2-B1"
   kind = "hostile"
   expected_codes = ["NUMERIC_IN_MACRO"]
   expected_exit = 1
   expected_verdict = "RED"
   rule = "R-01A"
   red_team = "2-B1"
   rationale = "宏体携带数字，渲染出账上没有的数"
   ```
4. 命名规范：`fixtures/hostile/2-B1/`、`fixtures/benign/2-B1/`（相对 `tests/fixtures/v22/`）。

**完成判据**：`pytest` 能枚举 36 个用例；每个 `case.toml` 的 `expected` 能对回本规范的一个条款编号。

### 20.2 对抗集：18 条各 1 hostile + 1 benign

| 红队条 | hostile 目录 | 构造 | 期望 | benign 目录 | 构造 | 期望 |
|---|---|---|---|---|---|---|
| 2-B1 | `hostile/2-B1/` | `\newcommand{\acc}{9}`＋`\newcommand{\onefour}{1.4}`＋`\newcommand{\kpi}{\acc\onefour\%}`；正文 `\kpi\fact{A2}` | `NUMERIC_IN_MACRO` 红（×2） | `benign/2-B1/` | `\providecommand{\fact}[1]{}`、`\newcommand{\sys}{\textsc{Sih}}`；正文 `10/16\fact{A2}` | 不红 |
| 2-B2 | `hostile/2-B2/` | value `0.91` ＋ display `{"text":"0.9","round_to":1}`；另一例 `round_to:-1` | `DISPLAY_INCONSISTENT` / `DISPLAY_ROUNDTO_INVALID` 红 | `benign/2-B2/` | value `10/16` ＋ display `["10/16","62.5%"]` | 不红 |
| 2-B3 | `hostile/2-B3/` | agent 自签回执、公钥写进项目内 `keys/`；回执缺 `response_body_sha256` | `TRUSTED_KEYS_IN_PROJECT`＋`RECEIPT_SCOPE_MISMATCH` 红 | `benign/2-B3/` | `evidence:"client_log"`、`delivered:true`、无签名 | 不红，`proof=self_report` |
| 2-B4 | `hostile/2-B4/` | `--level l0` 且无 issue；`--min-level l2` 且无 `runs/` | `verdict=UNVERIFIED`；默认 exit 0、`--gate` exit 8 | `benign/2-B4/` | L2 全绿（有 runs、proof 达标） | `verdict=PASS`、exit 0 |
| 2-B5 | `hostile/2-B5/` | `A2` 从 `0.91` 追加为 `0.19`，复用旧签名 | `APPROVAL_STALE` 红 | `benign/2-B5/` | 内容哈希签名，未改动 | 不红 |
| 2-S1 | `hostile/2-S1/` | `plain arm 10/16 while ours 5/16\fact{A2}\fact{A3}`（A2=10/16，A3=5/16） | `BINDING_ATTRIBUTION` 红 | `benign/2-S1/` | `10/16 and 5/16\fact{A2}\fact{A3}`（顺序与账一致） | 不红 |
| 2-S2 | `hostile/2-S2/` | `anchor:["assembly"]` 但 BU 无该词；`pair_with:["A2"]` 但同句无 A2 标记 | `ANCHOR_MISSING`＋`PAIR_MISSING` 红 | `benign/2-S2/` | anchor 与 pair 都在同句 | 不红 |
| 2-S3 | `hostile/2-S3/` | `delivered:false` 的 run，正文引用该 fact | `INVALID_FACT_CITED` 红；`facts.json` 哈希前后不变；无 `LEDGER_CHAIN_BROKEN` | `benign/2-S3/` | `delivered:true` | 不红 |
| 2-S4 | `hostile/2-S4/` | 表格内联 `10/16\fact{A2}`，A2 的 run `delivered:false` | `INVALID_FACT_CITED` 红（走 `REF_SET`） | `benign/2-S4/` | 表格内联指向有效 run | 不红 |
| 2-S5 | `hostile/2-S5/` | `tool_call_count:30`、`attempts` 只有 1 条、`selection_rule:"best"` | `SELECTION_UNREGISTERED`＋`ATTEMPT_COUNT_MISMATCH` 红 | `benign/2-S5/` | 3 条 attempts、`selection_rule:"mean"`、聚合可重算 | 不红 |
| 2-S6 | `hostile/2-S6/` | `\input{body.txt}` 含 `91.4%`；`\NewDocumentCommand` 包装 `\input` 未登记 | 文本入闭包（`UNBOUND_QUANT` 或绑定红）；`UNREGISTERED_INPUT_WRAPPER` 红 | `benign/2-S6/` | `\input{body.txt}` 只有散文；`\input{styles/layout.sty}` | 不红（`.sty` 记 info） |
| 2-S7 | `hostile/2-S7/` | `rules.json` 关掉 3 项 L2 升红；stamp 的 `root_tex` 与审计 root 不同 | 报告列 `downgraded_rules` 且 `verdict=ADVISORY`；`COMPILE_SCOPE_MISMATCH` 红 | `benign/2-S7/` | stamp 的 `compiled.root_tex == report.coverage.root` | 不红 |
| 2-S8 | `hostile/2-S8/` | 一条 fact 的 `value`/`display` 出现 `setting:"24-step"` 与 `"60-step"` | `FACT_MULTISETTING` 红 | `benign/2-S8/` | `10/16`＋`62.5%`，同一 setting | 不红 |
| 2-G1 | `hostile/2-G1/` | `91.4\fact{A2}，其余 42。`（42 在最后一个组之后） | `UNBOUND_QUANT`（唯一 code） | `benign/2-G1/` | `91.4\fact{A2}，其余 42\fact{A5}` | 不红（42 归 A5） |
| 2-G2 | `hostile/2-G2/` | `五例`、`两轮`、`准确率达九成五` 未绑 | `CJK_QUANT_SUSPECT` 黄；`九成五` → `UNBOUND_QUANT`（key 0.95） | `benign/2-G2/` | `第九章`；`三组\fact{A6}` | 不红 |
| 2-G3 | `hostile/2-G3/` | 同一 fact 两个不同 key，顺序与 display 相反 | `DISPLAY_ORDER` 红 | `benign/2-G3/` | `62.5% (i.e. 10/16)\fact{A2}`（同一 key 两种写法） | 不红 |
| 2-G4 | `hostile/2-G4/` | L0 干净报告的 JSON 与 stdout | `verdict=UNVERIFIED`；stdout 不含大写 `PASS` | `benign/2-G4/` | L2 干净报告 | `verdict=PASS`、`exit=0`、无 `status` 字段 |
| 2-G5 | `hostile/2-G5/` | 句子跨两文件；标记放在第一个文件末尾 | 该句是一个 BU；标记 `MARKER_TRAILING` 黄；第二个文件的数 `UNBOUND_QUANT` 红 | `benign/2-G5/` | 句子跨两文件，数字与标记都在第二文件 | 不红（按一个 BU 绑定） |

### 20.3 `paper/` 作为回归夹具（不是 oracle）

- `tests/fixtures/v22/paper/` 是只读快照；断言三条：
  1. **绑定 token 数 = 234**（位置集合与冻结快照逐 token 相等）；
  2. **绑定级红 = 0**（`UNBOUND_QUANT`/`BOUND_MISMATCH`/`BINDING_ATTRIBUTION`/`FACT_UNUSED_IN_SPAN` 全 0）；
  3. 已知迁移红（`C1` 拆分、124 个 `TABLE_UNBOUND`、5 处 `CTX`、6 处裸 id、TODO）**逐条登记为 `xfail(strict=True)`**，转正一条删一条。
- **不要把 0 红当 oracle**：这些期望值来自 §21 的条款；冻结读数只证明"新规则没有把旧语料误伤"。

### 20.4 模块拆分顺序（先坐标，后规则，最后输出契约）

| 顺序 | 模块 | 为什么先做 | 完成判据 |
|---|---|---|---|
| 1 | `texscan.py`（全局流、掩码、BU、QUANT、邻接） | 它是所有规则的**坐标系**；坐标系错了，后面每条规则都在错的位置上判 | `paper/` 234 个 token 位置与快照逐一相等；掩码前后中文句末位置不变 |
| 2 | `closure.py`（渲染面、文本输入、包装宏、root 签名） | 它决定"哪些字节算数"；漏一个文件，后面全白做 | 5 张表、`main.tex`、preamble、`.txt` 全部入集；孤儿为 0 |
| 3 | `ledger.py`（schema 2.2、display 严格等价、setting、签名链） | 它是**授权源**；值域不收紧，R-03 再准也没用 | `C1` 拆分预演通过；`0.91/0.9` 用例必红 |
| 4 | `rules/quant.py`（R-01/R-01A/R-03） | 核心判据；依赖 1–3 | 18 个 hostile 全红、18 个 benign 全绿；`paper/` 绑定级红 0 |
| 5 | `rules/coverage.py` + `rules/proof.py`（R-05/R-06/R-11） | `REF_SET` 依赖表格/图解析；证据层依赖账本 | `delivered:false` 经表格/图/`\factblock` 三条路都能抓到 |
| 6 | `report.py` + `cli.py`（verdict/exit/CI/横幅） | **最后做**：退出码语义依赖前面全部判定；先做会把"什么算红"写死错 | 12 条 exit 矩阵（L0/L1/L2 × 干净/黄/红/未达层）全绿 |
| 7 | `build.py` + `verify-pdf`（release/stamp） | 只在发布路径用；依赖 6 | `paper/main.pdf` 能通过 `verify-pdf`；换入口编译必红 |

**依赖方向（单向，禁止回指）**：
`cli → {audit, check, report, build} → rules/* → {texscan, ledger, bib, closure} → stdlib`。
规则之间**零 import**；共享结构体放 `models.py`（Fact、Issue、BU、Token）。`tools/bundle.py` 仍按拓扑序拼回单文件，产出的 `paperkit.py` 与拆分前逐字节等价（或仅版本号差异）。

### 20.5 后续步骤（规则已有坐标后）

1. **表格/图**：先内联式与映射式，生成式随 `tools/make_tables.py` 加 spec 输出；`TABLE_BARE_LITERAL` 上线。
2. **豁免宏/TODO/代号/免责/角色**：按 §9–§12、§17 原顺序，规则之间零耦合。
3. **账本 JSON 迁移**：`value` 保字符串；`C1` 拆 `C1a/C1b`；`E9` 标 `quantitative:false`；`display` 写严格等价形式；同一次提交删 `facts/*.toml`。
4. **证据层**：只为**实际存在**的证据写 run record；`delivered` 未知就写 `client_log`，不伪造 `server_receipt`。
5. **CI**：PR 跑 `--level l0`（快）；tag 跑 `--level l2 --gate`；`release` 强制 L2 + `verify-pdf`。

**总工期估计：10–13 个工作日**（不含历史 run record 补录；比 v2.1 多 2 天，主要是 R-01A 与签名链）。

---

## 21. 用我们自己的论文当回归夹具（必红/必绿清单）

> 全部来自 `paper/` 现网文件；测试里复制到 tmp 后跑，原目录只读。
> **位置以 v2.1 快照为准；`paper/` 在轮次之间已改动（标题/作者已不是 TODO），所以执行时以 §20.1 冻结的 `tests/fixtures/v22/paper/` 为准，本表用于说明"每条规则在真实语料上期望看到什么"。**
> "必红"＝v2.2 必须报出该 code；"必绿/必黄"＝不得误红。

| # | 位置 | 输入 | 期望 | 说明 |
|---|---|---|---|---|
| F01 | `main.tex:29` | `\title{TODO: Title...}` | `TODO_IN_PDF` 红 | 渲染进 PDF；当前完全没扫到（内部 S3） |
| F02 | `main.tex:31` | `\author{TODO: Author\thanks{TODO: ...}}` | `TODO_IN_PDF` 红 ×2 | 同上 |
| F03 | `main.tex:27` | `\newcommand{\todoq}[1]{\todo[...]{\textbf{PENDING: }#1}}` | `TODO_MACRO_DEF` 黄 | 宏定义体，不单独渲染 |
| F04 | `sections/01_intro.tex:14-16` | 3 × `\todoq{...}` | `TODO_IN_PDF` 红 ×3 + `TODO_REQUIRED_OPEN` | 缺省 required |
| F05 | `sections/02_related.tex:6-7` | 2 × `\todoq{...}` | 红 ×2 | 同上 |
| F06 | `sections/00_abstract.tex:12-21` | 5 × `% TODO(n):` | `TODO_COMMENT` 黄，**不红** | 注释不进 PDF（防误红） |
| F07 | `sections/03_system.tex:51,57,61,66,71` | `\pkignore{CTX-15}` 等 5 处 | `CODENAME_IN_BODY` 红 ×5 | 首版 `symbols.json` 把 CTX-xx 登记为 internal；掩码层看不见（内部 S2） |
| F08 | 合成（基于 03_system） | `\pkignore{We resolved 99 of 100 tasks.}` | `PKIGNORE_QUANT` 红 | B4 原反例 |
| F09 | `sections/04_mechanisms.tex:97` | `0/3 (E5 \fact{E5})` | `NAKED_FACT_ID` 红 | 正文裸 id |
| F10 | `sections/04_mechanisms.tex:142` | `(D2 ...)(D3 ...)(D1 ...)(H1 ...)(D6 ...)` | `NAKED_FACT_ID` 红 ×5 | 同上 |
| F11 | `tables/t1_main.tex` 等 5 表 | 124 个数字，无映射 | `TABLE_UNBOUND`（L2 红；L0 黄） | B1 的隧道 |
| F12 | 合成（t1 副本） | 把 `26,286` 改成 `26,000` | `TABLE_DRIFT` 红 | 有映射后仍抓得到 |
| F13 | `sections/05_eval.tex:17` | `10/16` 改成 `1/16`（A2/A3 不动） | `BOUND_MISMATCH` 红 | **今天 0 红**（B2 已复现）；v2.2 必抓 |
| F14 | 合成（05_eval 段末追加） | `... resolved 24 of 60 tasks\fact{C1}.` | `FACT_MULTISETTING`（**FACT 红，全层**）→ 拆 C1 后 `BOUND_MISMATCH` | 2-S8 的结构性判据 |
| F15 | `sections/05_eval.tex:40` | `we make no claim of superiority` | `DISCLAIMER_IN_RESULTS` **黄**（scope_claim） | 防误红：正当范围声明 |
| F16 | 合成（05_eval 插入） | `本结果可能受限于样本规模。`（无数字） | `DISCLAIMER_IN_RESULTS` 红 | 套话在 Results |
| F17 | `sections/07_threats.tex` | 正常 limitations 段 | 不红；未包 `\limitation` 的句子 → `LIMITATION_UNMACROED` 黄 | 角色判定 |
| F18 | `paperkit.toml:8` | `source_root = "/Users/moc/..."` | `ABSOLUTE_SOURCE_ROOT` 红 | CI 不可移植（S5） |
| F19 | `facts/e_gates.toml:3-6` | 注释记录如何绕过 DUPLICATE_VALUE | 迁移后 `notes[]` 原文保留 | S6 的"知识丢失" |
| F20 | `facts/c_crossmodel.toml` C1 | `3/6（24 步上限）；60 步 → 5/6` | `FACT_MULTISETTING`（**FACT 红**） | 一 fact 两 setting；必须拆 C1a/C1b |
| F21 | `sections/05_eval.tex:29` | `\pkignore{sphinx-10449}` | 不红（登记 `external.instance`） | 合法豁免 |
| F22 | `sections/05_eval.tex:15` | `one such run is present` | **已知漏**（`one` 后接 `such`，不触发）；记入 §22 | 拼写数字的边界（G1） |
| F23 | `sections/05_eval.tex:48` | `The run is ten tasks and a single trial` | `SPELLED_QUANT` 黄（L2 红） | G1 |
| F24 | `sections/01_intro.tex` | `如图 3`/`Table 2` 类交叉引用 | 不红 | `\ref` 参数已掩码 |
| F25 | `refs.bib` | `Vaswani et al. (2017)` 类引用年份 | 不红 | `\cite` 参数已掩码 |
| F26 | 全仓 | `GPT-4`/`LLaMA-3.1-70B`/`M3.1`/`V4.1` | 不红（`symbols.json` 登记） | 防误红（B5） |
| F27 | 合成 | `\mbox{0.91}` 未绑定 | `UNBOUND_QUANT` 红 | 形态逃逸（G1） |
| F28 | 合成 | `准确率达九成五` | `UNBOUND_QUANT` 红（key=0.95，由 X成Y 算法导出） | 中文数字（B4/2-G2） |
| F29 | 合成 | `相差 −0.03` | 能识别负号并绑定 | Unicode 负号（B4） |
| F30 | 合成 run | `run.json` 里 `delivered:false`，正文引用该 fact | `INVALID_FACT_CITED` 红 | R-B8 事故原型 |
| F31 | 合成 | 账本改 `value` 不 append | `LEDGER_MUTATED` 红 | R-B7 回填 |
| F32 | 合成 | `facts.json` 与 `facts/*.toml` 并存 | `STALE_LEDGER` 红 | S7 |
| F33 | 合成 | 审完改 `05_eval.tex` 再 `build` | `REPORT_STALE` / release 拒绝 | S6 |
| F34 | 合成 | `\tableinput` 改成 `\newcommand{\tbl}[1]{\input{x/#1}}` 未登记 | `UNREGISTERED_INPUT_WRAPPER` 红 | 隧道变异 |

**必红清单的用法**：`pytest tests/test_v21_hostile.py` 逐条断言 code；任何一条从红变绿，CI 直接挂——这就是 R-G2 要的"防止规则被一路调松"。

---

## 22. 本规范不承诺什么（写进 README 与每次报告）

1. **不承诺断言为真。** 只承诺"渲染面上的数字都能定位到被账授权的字面量、账与记录一致"。报告字段 `strength: containment_only`。
2. **不承诺送达。** 没有项目外的服务端签名密钥时，客户端可同时伪造 payload 与"已送达"；见 §13.5。
3. **不承诺抓得到语义改写。** `第 21 号分片`、图片里的字、完全换词的免责，都在检测地板以下。
4. **不承诺阻止本地出 PDF。** stamp 只能让"绕过门禁的 PDF"可检出，不能让它不存在。
5. **不承诺账本本身正确。** 被正确签名的错误值（0.91 签成 0.19）无法靠审计消除；能抓的是"改了内容却复用旧签名"（`APPROVAL_STALE`）。
6. **不承诺"绿＝可投稿"。** 绿只说明机械面干净；科学判断仍归人。
7. **不承诺穷尽 TeX。** 我们禁止的是**已知会产生数字的整族命令**（R-01A 表 A）和**数字跨宏拼接的语法形态**；TeX 是图灵完备的，理论上仍有绕过方式。`verify-pdf` 的文本回检是第二道网，不覆盖位图文字。
8. **不承诺发现被藏起来的 attempt。** 见 §13.6 与 §1.4-3；这是单侧证据的根本上限。

---

## 附录 A｜与 DESIGN-v2 的差异一览

| v2 | v2.2 | 原因 |
|---|---|---|
| `\fact{id}` 未定义语义 | 句级闭包＋显式 display＋组内归属 | R-B3 / B2 / B3 / 2-S1 |
| 审计 `sections/*.tex` | 渲染面闭包（含 preamble 与文本输入） | R-B5 / B1 / 2-S6 |
| 数字只看 token | 渲染可归责性（宏/计数器/邻接） | 2-B1 |
| `display` 可近似 | 严格 canon 等价，近似单列且不授权 | 2-B2 |
| 禁 `TODO/PENDING/FIXME` 三词 | 渲染判定＋正则族＋人签 required | R-S4 / S3 / G2 |
| 禁内部代号（黑名单） | 白名单＋登记表＋正文/附录分治 | R-B5 / S1 / S2 |
| 禁碎片化免责（语义） | 位置＋宏＋句式表＋具体性豁免 | R-B6 / S8 |
| `--strict` 一档 | L0/L1/L2＋四值 verdict＋UNVERIFIED 独立 exit 8 | R-B1 / S4 / S5 / 2-B4 |
| `runs/` 带 sha256 | run record＋角色分离＋回执钉 response＋per-attempt＋签名 | R-B8 / S7 / 2-B3 / 2-S5 |
| 人签按 id | 人签内容哈希（含 rules_sha256） | 2-B5 |
| 报告无 schema | verdict/exit 唯一＋inputs 哈希＋number_ledger | R-G3 / R-S6 / 2-G4 |
| 单文件 2184 行 | 模块＋bundle＋RULES 注册表＋SPEC_LINT | G4 / 2-S2 |

## 附录 B｜关键实测（本机）

```text
paper/ 冻结基线（v2.2 第 0 步，本次复核）：
  facts 48（facts/*.toml，尚未迁 facts.json）
  绑定 token 234（与 v2.1 的 231 相差 3，系轮次之间正文改动；以冻结快照为准）
  绑定级红 0（UNBOUND_QUANT / BOUND_MISMATCH / BINDING_ATTRIBUTION / FACT_UNUSED_IN_SPAN）
  paper/ 中多 fact 相邻标记（\fact{A}\fact{B}）出现 0 次 → 2-S1 的归属判据不误伤现网
  paper/ 中算术/计数器命令（\numexpr/\setcounter/\the\value/...）出现 0 次
  paper/ 中宏定义体含数字：0 处（\fact/\pkignore/\sys/\todoq 均为空体或纯文本）
  数字紧跟宏（SAFE 之外）0 处；唯一命中 0.55\linewidth 位于 \includegraphics 参数内，已被掩码
  数字紧跟闭合组（}digits）0 处 → NUM_AFTER_GROUP 不误伤现网
  paper/main.tex 的 \providecommand{\fact}[1]{} 与 \pkignore 不触发 NUMERIC_IN_MACRO
  paper/tables/*.tex 数字 124（t1 48 / t2 26 / t3 28 / t4 13 / t5 9），当前全在审计集外
  paper/sections/03_system.tex 五处 \pkignore{CTX-xx} 在掩码层不可见
  paper/tables/*.tex 整表包在 \pkignore 内 → 按 R-07 例外走 R-06 表格通道，不报 PKIGNORE_QUANT

v2.1 已复现、v2.2 保留为夹具的行为：
  删掉 fact_value_keys 的 places=0..4 循环后：paper/ 仍 0 红 → 值域收紧不误伤 48 条
  把 05_eval.tex 的 10/16 改成 1/16（A2/A3 标记不动）：仍 0 红 → B2 漏洞属实
  按段式绑定重放 paper/sections：token 位置与现网 numbers_total 一致 → 句级分段不误伤
```

> 注：上表"0 次/0 处"是 `grep` 级复核，不是审计器输出；`C1` 的两 setting 问题不在其中（它在 `facts/`，迁移时拆）。

## 附录 C｜待用户/工程拍板的 3 件事

1. **`\fact{}` 是否升级为取值宏**（数字只能由账注入）。v2.2 仍选闭包语义（兼容现有 48 条），但新增 R-01A 已经把"宏携带数字"这条路封死；若愿意重写正文，注入式可再上一档，代价是正文大改。
2. **`proof_class` 的达标线**：投稿版是否接受 `digest_only`，还是必须 `server_signed`（需要项目外的服务端回执设施）。这决定 §13.2 的部署成本。
3. **表格改造**：5 张表是否统一走 `spec.json` 生成（推荐），还是先用手工 cell map 过渡。前者能证明"表＝账"，后者只能证明"表里的数在账上"。
