# SPEC-V2.2｜FactScribe / paperkit 可执行规范

> 状态：蓝队收敛稿（第 2 轮），替代 `SPEC-V2.1.md`；v2.1 保留为历史靶子，`DESIGN-v2.md` 保留为更早的靶子。
> 输入：外部红队 `RED-2.md` 18 条（阻断 5／严重 8／一般 5），逐条裁决见 §1.3；`SPEC-V2.1.md`（1172 行）；`paper/` 现网语料（48 facts／234 绑定 token／0 红，读数见 §20.2）。
> 本版的一句话：**把保证对象从"被扫描到的 token"换成"被渲染出的数字"。**

---

## 0. 先看结论

1. **18 条红队意见：采纳 11、部分采纳 7、纯驳回 0**（逐条见 §1.3）。"部分"的 7 条里共 8 个子条款被明确驳回，每一条都写进 §1.4「已接受风险」——写明"接受什么风险、靠什么缓解"，不硬凑。
2. v2.2 的核心不是"再加规则"，而是**补上 v2.1 缺的那一步**：v2.1 的整条链是 `RAW → PROSE → QUANT token → BU → fact`，全链没有"渲染"这一步，于是宏、计数器、`\numexpr` 产生的数字**从来不进扫描面**。v2.2 加三件事：
   - **渲染面**取代"结论文本"：扫描面＝**闭包内全部会被 `\input` 进 PDF 的文本文件（含 preamble 与 `main.tex` 本身）**。v2.1 的"结论文本＝渲染内容"这句话，与它自己的"PROSE 层＝文件文本"互相矛盾，本版删除该词。
   - **数值可寻址性原则**：宏可以携带 **fact id**，不可以携带**数字**。`\newcommand{\kpi}{\accuracy\fact{A2}}` 合法；`\newcommand{\kpi}{91.4\%}`、`\newcommand{\acc}{9}` 非法。算术/计数器命令族（`\numexpr`、`\the\value`、`\setcounter`、`\pgfmathparse`、`\csname` 等）在正文与 preamble 一律红，白名单需显式登记。
   - **数字不许跨宏拼接**：数字 token 必须由连续字面数字构成；`\foo9`、`9\macro`、`{9}{1.4}` 直接红（判据见 §3.2，含白名单与例外）。
   - **PDF 文本回检**（L2/release 可选但推荐）：把 PDF 里抽出来的每个数字，与"账授权的数字集合"对表；宏/计数器/拼接出来的 `91.4` 在 PDF 里会露出来。
3. v2.2 **明确声明自己只保证什么**：`PASS` 的含义是"渲染面上每一个数字都能定位到一个字面量 token，该 token 属于某个 BU，并被某条账授权；且每条账的引用与记录一致"。它**不**保证"这句话在科学上为真"，也不保证"隐藏的尝试没被藏起来"。报告字段 `strength: "containment_only"` 把这句话写进机器可读输出。
4. **`PASS` 只在 L2 存在。** L0/L1 的"没查出问题"一律记 `UNVERIFIED`（独立退出码 8），CI 判定式写死为 `exit == 0 && verdict == "PASS"`。这是对 v2.1 最狠的一条漏洞（`verdict: PASS`＋`status: unverified`＋`exit 0` 三者并存）的正面修复。
5. 用我们自己的论文当磨刀石：`paper/` 里现成的 5 处 `\pkignore{CTX-xx}`、6 处裸 fact id、124 个表格数字，全部是 v2.2 的**必红/必黄用例**（§21）；同时它 234 条绑定、0 红，是**不许被新规则误伤**的回归基线（§20.2）。

---

## 1. 裁决表（39 条，逐条不漏）

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
| 2-S1 | 部分 | 并集授权确实"不判归属"，A/B 对调可全绿；但"禁止多 fact 组"会废掉现网合法写法 | 组内 token 与 fact **按出现顺序一一对应**（`BINDING_ATTRIBUTION` 红）；数量不等时要求 display 集**两两不交**（`FACT_SET_OVERLAP` 红）＋每条 fact 拥有唯一 token；真·同值用 `co_claim` 显式声明。**驳回**"一组只许一个 fact"（见 §1.4-2） |
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
| 1 | 2-B3：「工具强制 `runs/` 由不同 uid 写、`trusted_keys` 由 owner 独占」 | CLI 进程无法给自己降权；uid/挂载是部署层的事（v2.1 已因此驳回同类命题） | 同一个 agent 可以同时写 `runs/` 与 `facts.json`，并自带密钥 | 规范写死角色表（§13.6）＋部署清单；`trusted_keys` 必须在项目外（工具硬检）；没有项目外密钥时 `proof` 最高 `self_report`，`release` 默认拒绝 |
| 2 | 2-S1：「禁止一个组覆盖多个 fact」 | 会废掉现网 34 处合法写法（`\fact{A2}\fact{A3}`），迁移成本远超收益 | 组内归属仍依赖作者的书写顺序 | 顺序一一对应判据 + `co_claim` 显式声明 + `anchor`；误序即红，不再"并集放行" |
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
| 0 | `PASS` | 执行层＝L2、无任何红、coverage 全绿、`proof` 达标 | — |
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
!! 本次只跑了 L0（静态面）：未校验任何送达性证据（proof=absent）；结论为 unverified，不构成通过结论
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
                    DeclareDocumentCommand|DeclareRobustCommand) 抓到的每个定义体：
     若体中出现 [0-9]，且宏名 ∉ project.numeric_macro_allow → RED(NUMERIC_IN_MACRO)
   numeric_macro_allow 每条形如 {name, reason, signed_by}；
   登记的数值宏只允许用于 preamble 的布局参数或 `\includegraphics` 的 width=；
   出现在任何 BU 内 → RED(NUMERIC_MACRO_IN_BODY)。

C. NUM_ADJACENT_MACRO / NUM_AFTER_GROUP（红，FACT）
   对每个 QUANT token 的 RAW span [s,e)：
     L = RAW[s-1]；R = RAW[e]
     ① RAW[:s] 以 \\[A-Za-z]+$ 结尾（宏名紧贴 token）且宏 ∉ SAFE → RED(NUM_ADJACENT_MACRO)
     ② RAW[e:] 以 \\[A-Za-z]+ 开头（宏紧跟 token）且宏 ∉ SAFE → RED(NUM_ADJACENT_MACRO)
     ③ L == '}'（数字紧跟一个闭合组，{9}{1.4} 形态）      → RED(NUM_AFTER_GROUP)
   SAFE = {fact, ref, eqref, autoref, cref, Cref, label, cite, citep, citet, citealp}
   判据含义：数字 token 必须由**连续字面数字**构成，左右不得是宏调用或闭合组。

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
- 漏：`.sty`/`.cls` 内部定义的宏（不在项目闭包）；纯展开技巧（`\expandafter` 以外的 `\csname` 构造已被 A 覆盖，但 TeX 图灵完备，理论上不可穷尽）；位图里的数字（不做 OCR）。
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

**失败时退出码**：`ARITH_IN_BODY`/`NUMERIC_IN_MACRO`/`NUMERIC_MACRO_IN_BODY`/`NUM_ADJACENT_MACRO`/`NUM_AFTER_GROUP` → 1；`PDF_UNACCOUNTED_NUMBER` → 5（`--warn-only` → 3）；`PDF_TOOL_MISSING` → 2。

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

3) \fact 标记按**全局位置**归属到唯一 BU；文件末尾的孤立标记（后面没有任何正文）
   → MARKER_TRAILING（黄）。禁止"在文件 A 末尾写标记、给文件 B 的数字用"。
```

**中文无空格怎么切**：不依赖空格。句末标点＋守卫已经把中文散文切成句；`\fact{}` 位置由 sentinel 保留，因此"标记属于哪一句"是纯位置问题，与分词无关。中文数字/量词由 R-01 的 `CJK` 规则单独识别，不参与切句。

**误报/漏报边界**

- 误报：`Fig. 3` 被缩写在守卫里挡掉；`et al.` 同理。
- 漏：无标点的长排比句（作者用逗号写完整段）会被当成一句，绑定变宽 → 由 `SPAN_TOO_LONG` 提示，不红。
- 漏：`。` 后面没有空格仍会切（中文正确）；英文 `foo.Bar` 不切（可能漏一句）——由 600 字符上限兜底。
- 已知不可判：公式环境 `\begin{equation}` 内部不做句切，整块视为一个 BU（数学里的数字同样要绑 fact，见 R-06）。
- 误报防护（2-G5）：`\emph{...}`/`\footnote{...}` 的参数用配对花括号掩码，右括号后的 `.` 仍是句末（v2.1 的贪婪正则会吞掉它）。

**失败时退出码**：切分异常（source map 与文本长度不一致、掩码前后中文句末位置不一致）→ exit 4。

---

## 5. 判据 R-03：`\fact{id}` 的语义（本规范的核心）

### 5.1 语义定义

> `\fact{ID}` 是一个**闭包声明**：它声明"本 BU 内、由我覆盖的每一个 QUANT token，都出现在 ID 的可显示集里"。
> 它不是"这里有个事实"的装饰，也不是"这句话大概和 ID 有关"的标签。

`value` 本身的 token 集合永远是基线；`display` 只能追加**与 value 数值相等**的写法（同一数值的不同表示，如 `10/16` 与 `62.5%`），不能追加近似值或舍入值。

**覆盖范围＝"段"（segment）**：一个 `\fact` 组闭合**它前一个标记组之后、它自己之前**的那一段文字。连续书写、中间只有空白/标点的多个 `\fact{}` 算**一个组**（`\fact{A2}\fact{A3}`），共同闭合同一段。

| 写法 | 覆盖范围 | 说明 |
|---|---|---|
| `... 10/16 and 5/16\fact{A2}\fact{A3}。` | 组 `{A2,A3}` 覆盖整段；A2 认领 `10/16`，A3 认领 `5/16` | 一段多值 |
| `... 5/6 and 4/6\fact{B1}, ... 210.8k ... 104.2k\fact{B3}.` | `B1` 覆盖前半段（`5/6`、`4/6`）；`B3` 覆盖后半段（`210.8k`、`104.2k`） | 一句多断言（本仓 05_eval 实句） |
| `... 达到 0.91\fact{F-04}，其余...` | 段内只有 `0.91`；逗号之后若还有数，那一段无标记→红 | 相邻断言 |

- 标记出现在 BU 开头（段为空）→ `FACT_OUT_OF_SPAN`（红）。
- 最后一个标记组之后的尾段若还有 QUANT → `UNBOUND_QUANT`（红）。
- 段内 0 个 token → `FACT_WITHOUT_QUANT`（advisory，例如 `\fact{E9}` 的机制陈述）。
- **行不是绑定单位**：即使一个自然段占一整行（本仓 `paper/sections/*.tex` 的排版事实），段也只到上一个标记为止；同一行里标记之后新写的数字照样红。这是 B3 的正面修复。
- **块形式**（表格/多行构造用，可选）：`\factblock{ID} ... \factend{ID}`，块内每个 QUANT 都必须在该 fact 的集合里；`\factblock` 只能用于 `tabular` 或独立段落，不许嵌套。

### 5.2 判定算法

```
for bu in BUS(file):
    groups = marker_groups(bu)         # 按位置分组；组内成员只隔空白/标点
    segs   = split_by(groups)          # len(segs) == len(groups)+1
    if not groups:
        for t in QUANT(bu): RED(UNBOUND_QUANT, t)
        continue

    for g, seg in zip(groups, segs[:-1]):
        toks = QUANT(seg)              # 已做术语预掩码
        if not toks:
            ADVISORY(FACT_WITHOUT_QUANT, g); continue
        quant_ids = [f for f in g.ids if f.quantitative]
        if not quant_ids:
            RED(NONQUANT_BACKS_QUANT, g)   # 只有机制陈述来背数字
            continue
        allowed = union(display_set(f) for f in quant_ids)
        for t in toks:
            if t.key not in allowed:
                RED(BOUND_MISMATCH, t, g.ids, expected=allowed)

        # 每个被点名的定量 fact 必须"拥有"段内至少一个数
        for fid in quant_ids:
            owns = [t for t in toks if t.key in display_set(fid)]
            if not owns:
                RED(FACT_UNUSED_IN_SPAN, fid)
            elif not any_unique(owns, toks, fid):
                others = union(display_set(f) for f in g.ids if f != fid)
                if display_set(fid) <= others:
                    ADVISORY(DUPLICATE_BINDING, fid)   # 真·同值佐证
                else:
                    RED(FACT_UNUSED_IN_SPAN, fid)      # 挂名凑数

    # 尾段（最后一个组之后）不许有裸数
    for t in QUANT(segs[-1]): RED(UNBOUND_QUANT, t)
```

`any_unique(owns, toks, fid)`：段内存在某个 token，其 key 在 `allowed(fid)` 里、但不在同组其它 fact 的 allowed 里。它保证"每条被点名的 fact 至少负责一个别家负不了的数"，掐死"挂一排 id 让整段通过"；当两条 fact 本来同值时（如 `C1` 与 `H3` 都覆盖 `3/6 vs 5/6`）降为 `DUPLICATE_BINDING` advisory，不误红。

### 5.3 多值、顺序与"一 fact 一 setting"

- 一条 fact 的 `display` 是**有序列表**。若同一 BU 内某 fact 被用了 k≥2 个值，它们在句中出现的先后必须与 `display` 顺序一致，否则 `DISPLAY_ORDER`（红）。这条挡住"A 臂/B 臂对调"里最容易机械发现的一半。
- **一条 fact 只许一个 setting。** 判定：`value`/`display` 的 token 集合若出现 ≥2 个"互不相邻的量级簇"（如 `3/6` 与 `5/6`，或 `24` 与 `60`），且 fact 没有 `setting` 字段 → `FACT_MULTISETTING`（advisory；被正文引用时 L2 升红，强制拆分）。
  - 本仓 `C1 = "3/6（24 步上限）；60 步 → 5/6"` 是标准反例 → 迁移拆 `C1a/C1b`。
- 一条 fact 只覆盖一个断言；同一 fact 可以出现在多个 BU（重复引用合法）。
- `quantitative:false` 的 fact（如 E9 的机制陈述）不参与授权、不要求"拥有"数字，只作上下文标注；但如果一段有数字而该组**全是**非定量 fact → `NONQUANT_BACKS_QUANT`（红）。本仓 `06_ablation.tex:8` 的 `0/3\fact{E1}\fact{E9}` 合法（E1 定量、E9 标注）；若写成 `0/3\fact{E9}` 则红。

### 5.4 误报/漏报边界

- **不漏**：数字拼错、数字来自别的 fact、整句新编但数字不在账上、把 `10/16` 改成 `1/16`（B2 的实测漏洞在这条下必红）。
- **会漏（必须承认）**：数字全对但**语义张冠李戴**——`\fact{A2}`（开臂 10/16）写在"plain arm resolved 10/16"这一句里。闭包只证明"10/16 是账上的数"，不证明"它属于这个臂"。
  - 缓解 1：`display` 顺序 + 邻接约束，降低跨句搬运。
  - 缓解 2：fact 可声明 `anchor: ["assembly"]`（必须在该 BU 内字面出现），启用后 `ANCHOR_MISSING` 红；默认关闭，论文正式稿建议开。
  - 缓解 3：L2 的 `paircheck` 对 `pair_with` 成对 fact 检查同句共现。
  - 剩余风险进 §13.5 与 §22 的"不承诺"清单。
- 误报：一个 BU 里有多组数、只有尾部一个 `\fact{A11}\fact{A12}`——闭包仍成立（`paper/sections/05_eval.tex:25` 实句；段式原型重放 0 违例），不误报。
- 误报：`\fact{}` 包住非数字句（E9）→ advisory，不红。

### 5.5 失败时退出码

| code | tier | exit |
|---|---|---|
| `UNBOUND_QUANT` | FACT | 1 |
| `BOUND_MISMATCH` | FACT | 1 |
| `FACT_UNUSED_IN_SPAN` | FACT | 1 |
| `FACT_OUT_OF_SPAN` | FACT | 1 |
| `NONQUANT_BACKS_QUANT` | FACT | 1 |
| `DISPLAY_ORDER` | FACT | 1 |
| `FACT_WITHOUT_QUANT` | ADVISORY | 3 |
| `DUPLICATE_BINDING` | ADVISORY | 3 |
| `FACT_AMBIGUOUS_BINDING` | ADVISORY | 3 |
| `FACT_MULTISETTING` | ADVISORY（L2 升 FACT） | 3 / 1 |
| `SPAN_TOO_LONG` | ADVISORY | 3 |

---

## 6. 判据 R-04：账本 schema 与值域

### 6.1 `facts.json` 结构

```json
{
  "schema": "fact/2.1",
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
- `display[]`：`quantitative:true` 时必填；每项要么是 `"10/16"` 这种字面量，要么是 `{"text":"96.8%","round_to":1}`。`round_to` 必须显式；校验 `|canon(text) − canon(value)| ≤ 0.5×10^-round_to`，否则 `DISPLAY_INCONSISTENT`（红）。
- **删除 `fact_value_keys` 的 `places=0..4` 循环**（内部 B2）。值域＝`{canon(value)} ∪ {canon(d) for d in display}`。没有隐式舍入，没有"商的白名单"。
- 字段依赖：`derived_from` 非空 ⇒ `expr` 必填（沿用 v1）；`quantitative:true && L1` ⇒ `observation` 必填；`state:"invalid"` ⇒ `invalid_reason` 必填。
- `confidence:"low"` ⇒ 该 fact 不得出现在 `abstract`/`results` 角色的正文里；且必须 `variance`/区间字段（`LOW_CONF_IN_HEADLINE` 红）。
- 账本卫生（沿用 v1）：`DUPLICATE_ID`、`LEDGER_CONFLICT`、`DUPLICATE_VALUE`。`DUPLICATE_VALUE` 从"黄"升为"黄＋提示拆分"，因为它是 R-03 值域白名单的温床。
- **`STALE_LEDGER`**：`facts.json` 存在且 `facts/**/*.toml` 仍存在 → 红（exit 1）。迁移完成后 toml 必须删。

### 6.3 抽取（runs → 账）的边界

- 抽取器只写 `facts.proposed.json`，**不写** `facts.json`；批准是人的动作（`paperkit ledger approve --ids ...` 写入 append 记录）。
- 抽取字段白名单：只允许 `run.json` 的 `metrics` 与 grader 输出；**禁止**从 `*.log`、`response.json`、模型自述文本取指标（`EXTRACT_FORBIDDEN_SOURCE`，exit 2，抽取器自身报错）。
- `facts.json` 不含自由文本字段给 LLM 读；`notes` 不进入提示词（由组装层过滤）。
- 无数字的可证伪主张（"均优于基线"）→ 写 `claim_queue.md`，人工逐条确认/驳回；**不阻断**。这是 R-B4 的降级处理，也是我们接受"形态检测有地板"的代价。

### 6.4 误报/漏报边界

- 漏：账本本身的录入错误（0.91 打成 0.19）。审计只能证明"账与正文一致"，不能证明"账与 payload 一致"——后者靠 R-11 的 observation，再往上一层靠人签。
- 误报：`value:"0/3（F13）"` 这类带标签的旧值 → `VALUE_HAS_PROSE`（advisory），迁移时拆成 `value:"0/3"` + `setting:"F13"`。
- 误报：`value:"请求体里搜不到 _asciidoc_row"`（E9）→ 未标 `quantitative:false` 时红；迁移补标记即可。

**失败时退出码**：schema/类型/依赖错 → 2（配置错，工具没跑起来）；账本内部矛盾 → 1；`STALE_LEDGER` → 1。

---

## 7. 判据 R-05：审计文件集＝`main.tex` 递归闭包

### 7.1 判定输入

`project.root_tex`（默认 `main.tex`）、`project.expand`（额外可展开宏）、项目内全部 `.tex`。

### 7.2 算法

```
queue = [root_tex]; seen = {}
while queue:
    f = pop(); text = read(f); seen.add(f)
    for m in EXPAND_RE.finditer(text):
        cmd, arg = m.group(1), m.group(2)
        if cmd not in EXPANDABLE:
            RED(UNREGISTERED_INPUT_WRAPPER, f, cmd)   # 认不出的 *input* 家族
            continue
        target = resolve(arg, relative_to=[project.root, f.parent])
        if not exists(target): RED(INPUT_TARGET_MISSING)
        elif outside(project.root): RED(INPUT_OUTSIDE_PROJECT)
        else: push(target)
EXPANDABLE = {input, include, subfile, import, includeonly}
           ∪ {宏 X | \newcommand{\X}[1]{ <仅由 EXPANDABLE 命令与 #1 组成> }}
           ∪ project.expand
```

- **纯 `\input{#1}` 包装宏自动展开**：`paper/main.tex` 的 `\tableinput` 正是这种，因此 5 张表自动进集（回应 B1）。复杂包装（`\input{prefix/#1}`）必须写进 `project.expand`，否则红。
- 闭包外、项目内的 `.tex` → `ORPHAN_TEX`（COVERAGE；L0 黄，L2 红）。
- `audit/report.json` 的 `coverage.closure` 必须列出全部文件与哈希；`coverage.orphans` 必须为空才可能 PASS。
- 附录是**一等公民**：`appendix/*.tex` 必须在闭包里（`\input` 可达），否则 `APPENDIX_UNREACHABLE` 红——否则"代号迁附录"等于"迁出审计范围"（R-B5 的击穿点）。

### 7.3 误报/漏报边界

- 漏：用 `\directlua`/`\write18` 在编译期生成的 `.tex`（声明不支持，`release` 里检测到 `\write18` 直接红 `SHELL_ESCAPE`）。
- 漏：同一文件被 `\includeonly` 排除 → 仍在闭包里（保守，会多扫，不误放）。
- 误报：`\input{foo}` 指向 `.sty` 或图片 → 只把 `.tex` 入闭包，其余记 info。
- 误报：`\verb|\input{x}|` 里的字符串 → PROSE 已掩 verbatim。

**失败时退出码**：`INPUT_TARGET_MISSING`/`UNREGISTERED_INPUT_WRAPPER`/`INPUT_OUTSIDE_PROJECT`/`APPENDIX_UNREACHABLE` → 5（L0 记 deferred→3）；`ORPHAN_TEX` → 5（L2）/3（L0）。

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

### 8.2 图

- 每张 `\includegraphics` 必须同名 sidecar：`figures/f2_swebench.csv` 或 `.facts.json`（`{series:[{point, fact}], renderer_sha256}`）。
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

## 13. 判据 R-11：送达性证据层（回应 R-B8）

### 13.1 run record（`runs/<run_id>/run.json`）

```json
{
  "schema": "fs-run/1",
  "run_id": "B23-SWB16-on-0007",
  "created_at": "2026-10-02T09:14:11Z",
  "model": {"name": "DeepSeek V4.1 Flash", "version": "2026-09"},
  "condition_hash": "sha256:...",

  "request_body_sha256": "sha256:...",
  "response_sha256": "sha256:...",
  "delivered": true,
  "tool_call_count": 7,

  "request": {
    "canonicalization": "jcs-rfc8785",
    "body_bytes": 1832,
    "body_path": "request.json",
    "body_sha256": "sha256:..."
  },
  "response": {"body_sha256": "sha256:...", "body_path": "response.json"},
  "delivery": {
    "evidence": "server_receipt",
    "receipt_id": "srv-7f3a...",
    "received_at": "2026-10-02T09:14:12Z",
    "server_payload_sha256": "sha256:...",
    "attempt_index": 0
  },
  "tool_calls": [{"index": 0, "tool": "bash", "args_sha256": "sha256:..."}],
  "metrics": {"path": "metrics.json", "sha256": "sha256:...", "attempt_index": 0},
  "observation": {"path": "observed.json", "sha256": "sha256:..."}
}
```

字段一个都不能少。**顶层四个字段是硬要求且必须与嵌套字段一致**：
- `request_body_sha256` 必须等于 `request.body_sha256`（若 payload 本体存在，还要等于 `sha256(canonical_json(request.json))`）；
- `response_sha256` 必须等于 `response.body_sha256`；
- `delivered` 必须是 bool，且与 `delivery.evidence != "none"` 自洽（`evidence:"none"` 而 `delivered:true` → `RUN_RECORD_INVALID`）；
- `tool_call_count` 必须是 int，且等于 `len(tool_calls)`。
- `delivery.evidence ∈ {server_receipt, relay_receipt, client_log, none}`；其它值 → `RUN_RECORD_INVALID`。
四个摘要字段必须是 `sha256:` 前缀的 64 位十六进制。

### 13.2 fact 侧

`observation: {run_id, pointer}`。指向 `runs/<id>/observed.json`（记录时从 payload 抽出的观测快照，digest 钉在 run.json 里），**不**指向可能被重写的原始 payload。

### 13.3 校验算法（L1）

```
for f in facts_used_in_body:
    r = load(runs/f.observation.run_id/run.json)      # 缺 -> PROOF_MISSING(unverified)
    schema_ok(r) or RED(RUN_RECORD_INVALID)
    sha256(observed.json) == r.observation.sha256     or RED(OBSERVATION_DIGEST_MISMATCH)
    resolve_pointer(observed.json, f.observation.pointer) exists
        or RED(OBSERVATION_POINTER_MISSING)
    value_at_pointer == f.value (精确，按 R-01 规范键)   or RED(OBSERVATION_VALUE_MISMATCH)
    if r.delivery.delivered != true:
        mark f.state=invalid; RED(INVALID_FACT_CITED)   # 正文引用了 INVALID
    if r.delivery.attempt_index != r.metrics.attempt_index:
        RED(RETRY_ATTEMPT_MISMATCH)                     # 重试覆盖
    if r.delivery.evidence == "server_receipt":
        r.delivery.server_payload_sha256 == r.request.body_sha256 or RED(RECEIPT_DIGEST_MISMATCH)
    elif r.delivery.evidence == "client_log":
        # 自报：不红，但降 proof
        proof = min(proof, self_report)
```

同时校验 `facts.json` 引用的每个 `source`：`source_sha256` 必须等于该 source 文件现值；若 source 是某个 run 的 payload，则 `source_sha256 == run.request.body_sha256`。

### 13.4 `proof_class` 与降级

| class | 谁签发 | 能证明 | 不能证明 |
|---|---|---|---|
| `server_signed` | 服务端/中继回执，签名密钥在 `project.trusted_keys` | 请求到达过服务端，且服务端收到的 payload 摘要＝账上摘要 | 服务端真的跑了这个模型（除非回执含模型 id） |
| `digest_only` | 发布作业签名的摘要清单 | 账上引用的 payload 与清单里的摘要一致 | payload 本体存在；是否真的发出 |
| `self_report` | 客户端日志 | 客户端*声称*发了 | 任何送达性 |
| `absent` | 无 | 无 | 全部 |

报告 `proof` ＝ 正文用到的 fact 里**最弱**的一级。`release` 要求 `proof ∈ project.require_proof_class`（默认 `["server_signed","digest_only"]`）。

### 13.5 这条防不住什么（必须原样写进 README 与报告）

> 它只能证明：**账上引用的 payload 摘要，与被记录的 payload 摘要一致**。
> 它**不能**证明：payload 真的被发出去了；服务端真的处理了它；指标真的由这次响应产生（除非 `server_receipt` 且回执绑定 response id）。
> 没有服务端签名时，客户端可以同时伪造 payload 和"已送达"记录——审计会一致地通过。这是本层的**根本上限**，不是实现缺陷。

### 13.6 误报/漏报边界

- 误报：run record 晚于 fact 生成（先有账后有记录）→ `RUN_RECORD_MISSING` 只在 L2 红；L1 记 unverified。
- 漏：`delivered:true` 但服务端从未收到（客户端伪造）——见 §13.5。
- 漏：缓存复用旧 metrics 且 attempt_index 相同——无法与"这次真的跑了"区分，除非 grader 带 run 内随机 nonce。建议 grader 加 `nonce`，v2.1 记为 `NONCE_ABSENT`（advisory）。
- **缺席 ≠ 矛盾**：没有 run record → `PROOF_MISSING`（unverified），**不**是红；只有记录里明确 `delivered:false` 或摘要不符才红。这条是防止内部 S5 的"48 条全红"重演。

**退出码**：`RUN_RECORD_INVALID`/`INVALID_FACT_CITED`/摘要不符→1；`PROOF_MISSING`→0（status=unverified）；`--require-proof` 下→6。

---

## 14. 判据 R-12：`--strict` 分层（L0/L1/L2）

### 14.1 三层

| 层 | 跑什么 | 需要 runs/ | 典型场景 |
|---|---|---|---|
| **L0** | 静态：QUANT、`\fact` 闭包、闭包覆盖、表/图映射、`\pkignore`、TODO 渲染、代号、免责、账本 schema、STALE_LEDGER | 否 | 本地写作、PR 快速反馈 |
| **L1** | L0 ＋ run record／observation／摘要／INVALID | 是（或摘要清单） | 投稿前、实验批次结算 |
| **L2** | L1 ＋ coverage 全绿＋报告新鲜度＋`proof_class` 达标＋advisory 升红策略 | 是 | CI 发布门 |

`--level l0|l1|l2`；默认 auto：有 `runs/` → l1，否则 l0。`--strict` ≡ `--min-level l2`。

### 14.2 阻断规则（写死）

```
if level < requested:
    verdict = UNVERIFIED
    exit = 0                      # 关键：不因环境缺失而红
    print_banner("本次只跑了 L0 ...")
if level == L2:
    FACT red      -> 1
    COVERAGE red  -> 5
    STALE         -> 7
    advisory      -> 3 或按 rules.json 升红
else:
    FACT red      -> 1            # 事实红在任何层都阻断
    COVERAGE      -> 3 (deferred)
```

`--require-proof` 把 `PROOF_MISSING` 从 0 升到 6（opt-in，给要"零自报"的团队）。

### 14.3 边界

- 误报：团队把 `--strict` 理解成"全绿"，看到 `UNVERIFIED` 以为失败 → 横幅＋报告 `verdict` 字段双写，且 `release` 拒绝，语义清晰。
- 漏：CI 只跑 L0 却对外宣称"审计通过" → `report.level` 与 `report.proof` 落在 JSON 里，发布脚本必须检查；`release` 强制 L2。
- 误报：L1 有 runs/ 但都是 `self_report` → `proof=self_report`，`--strict` 在 L2 时因 `require_proof_class` 不满足 → 6？不：`proof` 不达标记 `PROOF_CLASS_INSUFFICIENT`（COVERAGE，5）。`--require-proof` 只影响 exit 6 的显式开关。

**退出码**：见 §2.3。

---

## 15. 判据 R-13：TOCTOU、报告新鲜度与 `release`

### 15.1 `audit/report.json`

```json
{
  "schema": "paperkit-report/2.1",
  "tool": {"version": "2.1.0", "rules_sha256": "sha256:..."},
  "generated_at": "2026-11-08T10:00:00Z",
  "level": "L1",
  "verdict": "PASS|ADVISORY|UNVERIFIED|FACT_RED|COVERAGE_RED",
  "proof": "digest_only",
  "strength": "containment_only",
  "banner": "本次只跑了 L0 ...",
  "inputs": {
    "main.tex": "sha256:...",
    "sections/05_eval.tex": "sha256:...",
    "tables/t1_main.tex": "sha256:...",
    "facts.json": "sha256:...",
    "refs.bib": "sha256:...",
    "paperkit.toml": "sha256:...",
    "symbols.json": "sha256:...",
    "roles.json": "sha256:..."
  },
  "input_set_sha256": "sha256:...",
  "report_sha256": "sha256:...",
  "counts": {"files": 18, "facts": 48, "quant": 355, "bound": 355, "unbound": 0},
  "issues": [
    {"code":"UNBOUND_QUANT","rule":"R-03","tier":"FACT","severity":"red",
     "file":"sections/05_eval.tex","line":17,"col":57,
     "token":"12.3","expected":["10/16","62.5%"],"actual":"12.3",
     "message":"...","action":"绑定到 A2 或改写","span_id":"s-0042"}
  ],
  "coverage": {"root":"main.tex","closure":["..."],"orphans":[],"tables":["..."],"figures":["..."]},
  "proof_summary": {"runs": 12, "valid": 10, "invalid": 1, "missing": 1}
}
```

- `inputs` 必须覆盖**审计读过的每一个文件**（含配置文件、闭包内全部 tex、facts、bib、runs 的 run.json）。
- `report_sha256 = sha256(canonical_json(payload 去掉 report_sha256))`。
- `audit --check-fresh audit/report.json`：重算 `inputs`，任一不符 → exit 7，并列出差异文件。

### 15.2 `release` 与 stamp

```
release = audit --strict --level l2
        → 必须 verdict==PASS 且 proof 达标
        → 生成 audit/stamp.json {report_sha256, input_set_sha256, tool_version, built_at}
        → 生成 audit/stamp.tex（\hypersetup{pdfkeywords={paperkit-stamp:<...>}}）
        → 编译 → pdf_sha256 入 stamp
        → 校验 PDF 元数据含 stamp（pdftotext/pdfinfo；缺工具则记 STAMP_UNVERIFIED advisory）
```

- `paperkit build` **只做排版预览**：不检查报告；输出 PDF 头注释 `% UNSTAMPED PREVIEW`（通过 `\pdfinfo` 写 `/Subject`）。
- 无 stamp 的 PDF → `STAMP_MISSING`（`release` 拒绝；对外发布脚本检查）。
- **边界**：本地 `latexmk` 永远能绕过。stamp 的作用是"可检出"，不是"不可能"。这是诚实的能力边界，写进 README。

**退出码**：`REPORT_STALE`→7；`release` 在 `verdict!=PASS`→1/5/6；`STAMP_UNVERIFIED`→3。

---

## 16. 判据 R-14：账本变更与权限

- **append-only**：`facts.json` 的每条 fact 带 `state` 与 `supersedes`；修改＝追加新条目 + 旧条目 `state:"superseded"`。原地改 `value` → `LEDGER_MUTATED`（红，通过 `digest_prev` 链检测）。
- `facts.json` 顶部 `digest_prev` = 上一版文件的 sha256；`paperkit ledger append` 自动维护。链断 → `LEDGER_CHAIN_BROKEN`（红）。
- 每次变更记录 `{by, at, reason, evidence: {run_id, pointer}}`；缺 reason/evidence → `LEDGER_EDIT_UNEVIDENCED`（红）。
- **共谋检测（advisory）**：同一次提交里 `facts.json` 与正文的 diff 行集合重合度 > 0.6 且涉及同一 fact id → `LEDGER_TEXT_COCHANGE`（advisory；L2 需人签）。
- **权限**：本工具**不**提供进程级只读（驳回理由见 §1）。部署清单要求：写作进程的 cwd 只挂载 `sections/` 可写；`facts.json`/`audit/report.json` 由 owner 只读、写作进程另一 uid；报告由独立进程重算。`paperkit release` 检测 `facts.json` 的 mtime 是否早于本次 audit 启动（并发改账）→ `LEDGER_CONCURRENT_EDIT`（红）。

**退出码**：`LEDGER_MUTATED`/`LEDGER_CHAIN_BROKEN`/`LEDGER_EDIT_UNEVIDENCED`/`LEDGER_CONCURRENT_EDIT`→1。

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

人类输出必须按 tier 分组（`[红/FACT]`、`[红/COVERAGE]`、`[黄]`），并在结尾打印 `strength: containment_only` 与 `proof: <class>`。

### 19.2 错误码注册表（首版，稳定不改名）

| code | tier | exit | 规则 |
|---|---|---|---|
| `UNBOUND_QUANT` | FACT | 1 | R-03 |
| `BOUND_MISMATCH` | FACT | 1 | R-03 |
| `FACT_UNUSED_IN_SPAN` | FACT | 1 | R-03 |
| `FACT_OUT_OF_SPAN` | FACT | 1 | R-03 |
| `NONQUANT_BACKS_QUANT` | FACT | 1 | R-03 |
| `FACT_UNKNOWN_ID` | FACT | 1 | R-03 |
| `DISPLAY_ORDER` | FACT | 1 | R-03 |
| `DISPLAY_INCONSISTENT` | FACT | 1 | R-04 |
| `VALUE_NOT_STRING` | CONFIG | 2 | R-04 |
| `VALUE_NOT_QUANT` | FACT | 1 | R-04 |
| `STALE_LEDGER` | FACT | 1 | R-04 |
| `LEDGER_MUTATED` | FACT | 1 | R-14 |
| `LEDGER_CHAIN_BROKEN` | FACT | 1 | R-14 |
| `LEDGER_EDIT_UNEVIDENCED` | FACT | 1 | R-14 |
| `LEDGER_CONCURRENT_EDIT` | FACT | 1 | R-14 |
| `INPUT_TARGET_MISSING` | COVERAGE | 5 | R-05 |
| `INPUT_OUTSIDE_PROJECT` | COVERAGE | 5 | R-05 |
| `UNREGISTERED_INPUT_WRAPPER` | COVERAGE | 5 | R-05 |
| `ORPHAN_TEX` | COVERAGE | 5 | R-05 |
| `APPENDIX_UNREACHABLE` | COVERAGE | 5 | R-05 |
| `UNSCANNED_TEX` | COVERAGE | 5 | R-05 |
| `TABLE_UNBOUND` | COVERAGE | 5 | R-06 |
| `TABLE_DRIFT` | COVERAGE | 5 | R-06 |
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
| `RECEIPT_DIGEST_MISMATCH` | FACT | 1 | R-11 |
| `RETRY_ATTEMPT_MISMATCH` | FACT | 1 | R-11 |
| `PROOF_MISSING` | —（status=unverified） | 0/6 | R-11 |
| `PROOF_CLASS_INSUFFICIENT` | COVERAGE | 5 | R-11 |
| `REPORT_STALE` | — | 7 | R-13 |
| `SECTION_ROLE_UNKNOWN` | COVERAGE | 5 | R-15 |
| `SHELL_ESCAPE` | FACT | 1 | R-05 |
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
| `NONCE_ABSENT` | ADVISORY | 3 | R-11 |
| `STAMP_MISSING` | COVERAGE | 5 | R-13 |
| `STAMP_UNVERIFIED` | ADVISORY | 3 | R-13 |
| `SPAN_TOO_LONG` / `FACT_AMBIGUOUS_BINDING` / `FACT_WITHOUT_QUANT` / `DUPLICATE_BINDING` / `FACT_MULTISETTING` | ADVISORY | 3 | R-03/R-04 |
| `SOURCE_SHA256_MISMATCH` / `MISSING_SOURCE` / `SOURCE_NOT_SIGNED` | FACT | 1 | v1 沿用 |

---

## 20. 实施顺序（工程上先做什么）

### 20.1 第一步（0.5–1 天）：冻结回归面，不改一行行为

**先做夹具，再做重构。** 没有基线，任何"修规则"都无法区分修复与放宽（R-G2）。

1. 把 `paper/` 打成只读快照（测试里 `shutil.copytree` 到 tmp，**永不**改原目录）。
2. 锁定当前读数：`facts 48 / sections 9 / numbers 231 (bound 231, unbound 0, unmatched 0) / 0 红 11 黄 / exit 3`；`--strict` exit 1（已知，待 v2.1 改为 L0 group）。
3. 建 `tests/fixtures/v21/`：
   - `hostile/`：未绑定量句、`1/16` 篡改、`\pkignore` 假结论、`\todoq` 渲染、`TODO: Title`、`CTX-15`、裸 `E5`、表格逃逸、`delivered:false`、账本回填、中文数字句；
   - `benign/`：`如图 3`、`(2017)`、`sha256`、`GPT-4`、`LLaMA-3.1-70B`、合法 hedging、`% TODO` 注释（应黄不应红）。`p > 0.05` 不是 benign——它是定量主张，必须绑 `kind:config` 的 fact；`\mbox{0.91}` 归 hostile（R-01 的形态逃逸）。
4. 每条 fixture 写 `case.toml`：期望 code、severity、exit、理由、对应红队编号。

**完成判据**：`pytest` 能跑 §21 的 34 条 fixture（映射覆盖 39 条红队意见），全部按"当前实现"的读数通过（允许 expected-fail 标记 `xfail(strict=True)`，v2.1 逐条点亮）。

### 20.2 第二步（1–2 天）：拆单文件，零行为变化

`paperkit.py` 2184 行不能再往里塞 1000 行。拆开发面、保发布面（回应 G4）：

```
src/paperkit/
  __init__.py        # VERSION、main 导出
  cli.py             # argparse、exit code、--json 外壳       → 依赖 audit/check/report/build
  config.py          # Config、paperkit.toml、roles/symbols 加载
  ledger.py          # facts.json 读写、schema、digest 链、append   → 仅 stdlib
  texscan.py         # 分层、source map、BU 切分、QUANT、marker    → 仅 stdlib
  closure.py         # main.tex 闭包、包装宏展开、orphan          → 依赖 texscan
  bib.py             # 原样搬
  rules/__init__.py  # RULES = {code: (tier, fn)}
  rules/quant.py     # R-01..R-04
  rules/coverage.py  # R-05/R-06
  rules/annotations.py # R-07/R-08
  rules/symbols.py   # R-09
  rules/disclaimer.py# R-10
  rules/proof.py     # R-11
  rules/roles.py     # R-15
  report.py          # report.json、stamp、canonical hashing、freshness
  build.py           # build/release
tools/bundle.py      # 按拓扑序拼回单文件 paperkit.py（保留"可复制单文件"承诺）
```

**依赖方向（单向，禁止回指）**：
`cli → {audit, check, report, build} → rules/* → {texscan, ledger, bib, closure} → stdlib`。
规则之间**零 import**；共享结构体放 `models.py`（Fact、Issue、BU、Token）。

**完成判据**：`tools/bundle.py` 产出的 `paperkit.py` 与拆分前逐字节等价（或仅版本号差异），`paper/` 基线读数完全不变。

### 20.3 第三步（2–3 天）：先修值域与绑定（B2/B3）

这两条不修，后面所有规则都建在沙上。

1. 删 `fact_value_keys` 的 `places` 循环；加 `display` 校验。
2. `_extract_numbers` 改 token 流（FRAC 整体一个 token，不拆 10/16）。
3. `scan_tex` 增加 marker 位置与分组（连续标记算一组），`bindings` 从"行→ids"改成"BU→段→ids"。
4. `run_audit` 的判定从"行并集"改 R-03 的闭包算法。
5. 回归：`paper/` 应仍 **0 红**（异常：`\fact{E9}` 的无数字句 → advisory）。**已实测：删掉舍入循环后本仓仍 0 红**，说明迁移不会误伤现有 48 条。

### 20.4 第四步（2 天）：闭包 + 表格 + 豁免宏 + TODO

1. `closure.py`：根 `main.tex`；纯 `\input{#1}` 包装宏自动展开（`\tableinput` 立刻生效）。
2. 表格：先支持"内联式"与"映射式"，生成式随 `tools/make_tables.py` 改造（它已经在生成表，加一行 spec 输出即可）。
3. `\pkignore` 参数抽数 → 红。
4. TODO 渲染判定 + `human_todo.md` 生成/回流。
5. 此时 `paper/` 的预期读数：`UNSCANNED_TEX` 消失（换成 124 个 `TABLE_UNBOUND` 或映射后的绿）、5 处 `CTX` 红、5 处 `\todoq` 红、2 处 title/author 红、6 处裸 fact id 红。**这就是"自己的论文当磨刀石"的第一批读数。**

### 20.5 第五步（1–2 天）：代号 + 免责 + 角色

1. `symbols.json` 首版（收本仓全部合法外部专名）。
2. `roles.json` 首版（把 9 个 section + 2 个 appendix 显式映射）。
3. 免责 pattern 表 + `\limitation` 宏。
4. 裸 fact id 规则上线；`paper/` 的 04_mechanisms 两行必须改写（"the fifth cut" 之类）。

### 20.6 第六步（2 天）：账本 JSON 迁移

1. `paperkit ledger migrate --from "facts/*.toml" --to facts.json --dry-run`：逐条 diff＋新旧摘要。
2. 迁移规则（回应 S6/S7）：
   - `value` 保持**字符串**；`0/3（F13）` → `value:"0/3"` + `setting:"F13"`；
   - `note` → `notes[]`（保留 `e_gates.toml` 那段"如何绕过自家闸门"的知识）；
   - `E9` 标 `quantitative:false`；
   - `C1` 拆 `C1a`（24 步）/`C1b`（60 步），正文 `\fact{C1}` 改成对应 id；
   - `display` 只在必要时写（`10/16` 可同时给 `62.5%`）。
3. 同一次提交删 `facts/*.toml`；`STALE_LEDGER` 守卫上线。
4. `paperkit.toml`：`facts = "facts.json"`、`root_tex = "main.tex"`、`source_root = ".."`（相对路径）。
5. **`\fact{}` 的语法与其余 47 个 id 全部不变**；正文唯一必须改的标记是 `C1` → `C1a`/`C1b`（按句意选），以及 §21 里那 6 处裸 id 的改写。这让迁移可回滚、可逐条 review。
6. **完成判据**：`audit --level l0` 的 red 集合＝§21 的必红清单，**没有意外红**。

### 20.7 第七步（2 天）：证据层 + 分层 + 报告

1. `run.json` schema 校验、`observed.json` 指针校验。
2. 为现有 `experiments/ctx-compiler-redblue/batch23/` 生成记录：**只写实际存在的证据**，`delivered` 未知就写 `null`/`evidence:"client_log"`，不伪造 `server_receipt`。结果必然是 `proof=absent/self_report` → 报告 `UNVERIFIED`。这是诚实读数，不是失败。
3. L0/L1/L2 + 横幅 + exit 码 + `report.inputs` + `--check-fresh`。
4. `release` + stamp（先做 `report_sha256` 校验，PDF 元数据戳可后补）。

### 20.8 第八步（1 天）：CI 与对抗集固化

1. `.github/workflows`：PR 跑 L0（快，< 30s）；tag 跑 L2 + `--require-proof`（有摘要清单时）。
2. `hostile/benign` 全绿；`paper/` 的 must-red 清单作为 `xfail` 逐条转正。
3. 文档：README 顶部三行写明 `PASS = containment_only`、`UNVERIFIED ≠ PASS`、`stamp 可检出不可阻止`。

**总工期估计：8–11 个工作日**（不含 `run.json` 历史数据的补录）。

---

## 21. 用我们自己的论文当回归夹具（必红/必绿清单）

> 全部来自 `paper/` 现网文件；测试里复制到 tmp 后跑，原目录只读。
> "必红"＝v2.1 必须报出该 code；"必绿/必黄"＝不得误红。

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
| F13 | `sections/05_eval.tex:17` | `10/16` 改成 `1/16`（A2/A3 不动） | `BOUND_MISMATCH` 红 | **今天 0 红**（B2 已复现）；v2.1 必抓 |
| F14 | 合成（05_eval 段末追加） | `... resolved 24 of 60 tasks\fact{C1}.` | `FACT_MULTISETTING`（L2 红）→ 拆 C1 后 `BOUND_MISMATCH` | B3 原反例 |
| F15 | `sections/05_eval.tex:40` | `we make no claim of superiority` | `DISCLAIMER_IN_RESULTS` **黄**（scope_claim） | 防误红：正当范围声明 |
| F16 | 合成（05_eval 插入） | `本结果可能受限于样本规模。`（无数字） | `DISCLAIMER_IN_RESULTS` 红 | 套话在 Results |
| F17 | `sections/07_threats.tex` | 正常 limitations 段 | 不红；未包 `\limitation` 的句子 → `LIMITATION_UNMACROED` 黄 | 角色判定 |
| F18 | `paperkit.toml:8` | `source_root = "/Users/moc/..."` | `ABSOLUTE_SOURCE_ROOT` 红 | CI 不可移植（S5） |
| F19 | `facts/e_gates.toml:3-6` | 注释记录如何绕过 DUPLICATE_VALUE | 迁移后 `notes[]` 原文保留 | S6 的"知识丢失" |
| F20 | `facts/c_crossmodel.toml` C1 | `3/6（24 步上限）；60 步 → 5/6` | `FACT_MULTISETTING` | 一 fact 两 setting |
| F21 | `sections/05_eval.tex:29` | `\pkignore{sphinx-10449}` | 不红（登记 `external.instance`） | 合法豁免 |
| F22 | `sections/05_eval.tex:15` | `one such run is present` | **已知漏**（`one` 后接 `such`，不触发）；记入 §22 | 拼写数字的边界（G1） |
| F23 | `sections/05_eval.tex:48` | `The run is ten tasks and a single trial` | `SPELLED_QUANT` 黄（L2 红） | G1 |
| F24 | `sections/01_intro.tex` | `如图 3`/`Table 2` 类交叉引用 | 不红 | `\ref` 参数已掩码 |
| F25 | `refs.bib` | `Vaswani et al. (2017)` 类引用年份 | 不红 | `\cite` 参数已掩码 |
| F26 | 全仓 | `GPT-4`/`LLaMA-3.1-70B`/`M3.1`/`V4.1` | 不红（`symbols.json` 登记） | 防误红（B5） |
| F27 | 合成 | `\mbox{0.91}` 未绑定 | `UNBOUND_QUANT` 红 | 形态逃逸（G1） |
| F28 | 合成 | `准确率达九成五` | `UNBOUND_QUANT` 红 | 中文数字（B4） |
| F29 | 合成 | `相差 −0.03` | 能识别负号并绑定 | Unicode 负号（B4） |
| F30 | 合成 run | `run.json` 里 `delivered:false`，正文引用该 fact | `INVALID_FACT_CITED` 红 | R-B8 事故原型 |
| F31 | 合成 | 账本改 `value` 不 append | `LEDGER_MUTATED` 红 | R-B7 回填 |
| F32 | 合成 | `facts.json` 与 `facts/*.toml` 并存 | `STALE_LEDGER` 红 | S7 |
| F33 | 合成 | 审完改 `05_eval.tex` 再 `build` | `REPORT_STALE` / release 拒绝 | S6 |
| F34 | 合成 | `\tableinput` 改成 `\newcommand{\tbl}[1]{\input{x/#1}}` 未登记 | `UNREGISTERED_INPUT_WRAPPER` 红 | 隧道变异 |

**必红清单的用法**：`pytest tests/test_v21_hostile.py` 逐条断言 code；任何一条从红变绿，CI 直接挂——这就是 R-G2 要的"防止规则被一路调松"。

---

## 22. 本规范不承诺什么（写进 README 与每次报告）

1. **不承诺断言为真。** 只承诺"数字被账授权、账与记录一致"。报告字段 `strength: containment_only`。
2. **不承诺送达。** 没有服务端签名时，客户端可同时伪造 payload 与"已送达"；见 §13.5。
3. **不承诺抓得到语义改写。** `第 21 号分片`、图片里的字、完全换词的免责，都在检测地板以下。
4. **不承诺阻止本地出 PDF。** stamp 只能让"绕过门禁的 PDF"可检出，不能让它不存在。
5. **不承诺账本本身正确。** 人工录入错误（0.91/0.19）只能靠 observation＋人签降低，不能靠审计消除。
6. **不承诺"绿＝可投稿"。** 绿只说明机械面干净；科学判断仍归人。

---

## 附录 A｜与 DESIGN-v2 的差异一览

| v2 | v2.1 | 原因 |
|---|---|---|
| `\fact{id}` 未定义语义 | 句级闭包＋显式 display | R-B3 / B2 / B3 |
| 审计 `sections/*.tex` | `main.tex` 递归闭包 | R-B5 / B1 |
| 禁 `TODO/PENDING/FIXME` 三词 | 渲染判定＋正则族＋人签 required | R-S4 / S3 / G2 |
| 禁内部代号（黑名单） | 白名单＋登记表＋正文/附录分治 | R-B5 / S1 / S2 |
| 禁碎片化免责（语义） | 位置＋宏＋句式表＋具体性豁免 | R-B6 / S8 |
| `--strict` 一档 | L0/L1/L2＋三档 verdict | R-B1 / S4 / S5 |
| `runs/` 带 sha256 | run record＋observation＋proof_class | R-B8 / S7 |
| 报告无 schema | 稳定 code＋inputs 哈希＋report_sha256 | R-G3 / R-S6 |
| 单文件 2184 行 | 模块＋bundle＋RULES 注册表 | G4 |

## 附录 B｜关键实测（本机，2026-11-08）

```text
paper/ 基线：facts 48 / sections 9 / numbers 231 (bound 231, unbound 0, unmatched 0)
             0 红 / 11 黄 / exit 3
删掉 fact_value_keys 的 places=0..4 循环后：仍 0 红 → 值域收紧不误伤现有 48 条
把 05_eval.tex 的 10/16 改成 1/16（A2/A3 标记不动）：仍 0 红 → B2 漏洞属实
按 R-03 的"段式绑定"写原型重放 paper/sections：231 个 token、0 违例
   （与现网 numbers_total=231 完全一致 → 句级分段不会误伤现有语料；
    唯一需要迁移处理的是 E9 这类 quantitative:false 的机制标注）
paper/tables/*.tex 数字总数：124（t1 48 / t2 26 / t3 28 / t4 13 / t5 9），当前全在审计集外
paper/sections/03_system.tex 五处 \pkignore{CTX-xx} 在掩码层不可见
paper/main.tex:29/31 的 TODO 因 main.tex 不在 sections glob 内而完全未扫
```

## 附录 C｜待用户/工程拍板的 3 件事

1. `\fact{}` 是否升级为**取值宏**（数字只能由账注入）。v2.1 选闭包语义以兼容现有 48 条；若愿意重写正文，v2.2 可换成注入式，检测强度再上一档。
2. `proof_class` 的达标线：投稿版是否接受 `digest_only`，还是必须 `server_signed`（需要服务端回执设施）。
3. 表格改造：5 张表是否统一走 `spec.json` 生成（推荐），还是先用手工 cell map 过渡。
