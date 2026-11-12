# MiniFactScribe —— FactScribe 的 Mini App

把 FactScribe 的**机械闸门**搬到 MiniMax Code 的 Mini App 面板里，在浏览器本地跑。
不装 Python、不连服务器、不写论文正文。

> **这是一个第三方移植件，不是 FactScribe 的一部分。**
> 它不进入 `factscribe/` 包，不参与本仓库的 Python 打包、测试矩阵与退出码契约。
> 上游 `factscribe/` 的行为、退出码与违规码一律未改。
> 移植件自身的缺陷请开在 `integrations/minifactscribe/` 下的 issue，不要混进上游判据问题。

---

## 它做什么

一句话：**正文里的每个数，能不能回到一份签过字、算过哈希的原始材料。**

Mini App 有五个页签：

| 页签 | 干什么 |
|---|---|
| 正文 | 逐行体检：每个数字按判定着色（绿＝已绑定且对得上，黄＝回得到账但没钉住，红＝回不到账） |
| 事实账 | 只追加的清单。每条事实记一个数、它的来源文件与来源文件的哈希 |
| 引用 | 每条 cite 必须在 bib 里；bib 条目必须有 doi / arXiv / url 之一；可联网查 Crossref / arXiv |
| 改写保护 | 比对改写前后六类不许变的内容：事实标记、数字、引用、公式、表格、交叉引用 |
| 审计 | 红黄牌汇总、可执行处方、可导出报告 |

三个导出：report.md（审计报告）、matrix.md（追溯矩阵）、manifest.json（可复现清单）。

---

## 与上游的对应关系

移植的是语义，不是代码。逐条对齐如下。

### 搬过来的（语义一致）

| 上游 | 这里 |
|---|---|
| factscribe/facts.py 数字归一化 | miniapp/node/audit.mjs 的 NUM_RE / numberKey() |
| 值域＝字面值 ∪ 精确分数商 ∪ 百分号裸值 | factValueKeys()（精确有理数，无隐式四舍五入） |
| 内联绑定 fact{ID} / [[fact:ID]] 是行级硬约束 | prepareLine() / scanCitations() |
| 引用族 fail-closed：任何含 cite 的命令都算引用 | CITE_RE / CITE_KNOWN |
| check：id 唯一、sha256 现算、expr 重算、同值冲突 | auditProject() 的账本自检段 |
| protect：六类保护面 | protectDiff() |
| prescribe：只给可执行改法，不进判据、不产生分数 | PRESCRIPTIONS（不进 issues，不改退出码） |
| 退出码 0 绿 / 1 红 / 2 配置错 / 3 黄 | 同上 |

**来源哈希是现算的**，与上游 sha256_file(disk) 同一个意思：审计时对来源材料正文现算 sha256，
再与账本钉住的值比对。用户改了来源正文而没更新账本 → SOURCE_SHA256_MISMATCH（红）。
存字段、拿旧字段比，是会让这道闸变哑的错法。

**来源字段与来源文件分开判**（与上游同名同义）：事实缺 `source` 字段 → `MISSING_SOURCE_FIELD`；
字段填了、但指向的来源在项目里找不到 → `MISSING_SOURCE`（来源文件不存在）。

### 上游有、这里没有

| 缺什么 | 为什么 |
|---|---|
| tide 涨落闭合 | 改动账要落盘与快照比对，Mini App 侧先不做 |
| style 31 条文风闸 | 文风闸需要独立的分词与句法资源，超出机械闸门的移植范围 |
| verify-pdf / PDF 直读 | Mini App 侧不做 PDF 解析 |
| build / fonts / brief / review / polish / terms | 与「数字与引用」这条主线无关 |
| --json / --strict | 这里固定出 JSON 与 Markdown 两种导出 |
| 退出码 4 / 5 / 7 / 8 | 内部错误 / 完整性 / 陈旧 / 缺失，本移植件不实现 |

### 这里有、上游没有

四个联网核验码。它们不进上游判据，只在联网核验跑过时并入本移植件的判据：

| 码 | 严重级 | 含义 |
|---|---|---|
| CITE_FAKE | 红 | 被引用条目的稳定标识在线查无此文 |
| CITE_SUSPECT | 黄 | 标题与来源对不上 |
| CITE_UNVERIFIED | 黄 | 本轮没核验成（网络 / 限流） |
| RESOLVE_DEGRADED | 黄 | 半数以上条目没核验成，本轮引用存在性等于没验 |

只有**被正文引用过**的条目才升级为红 / 黄。未被引用的条目只显示状态，不判死——
本地 bib 齐全不代表文献存在，但没引用的条目轮不到它。

---

## 跑起来

需要 Node 18+（用到 node:crypto 与 fetch）。零第三方依赖，只用 Node 内置模块与浏览器 API。

### 作为 Mini App 装到 MiniMax Code

把 integrations/minifactscribe/ 整个目录拷进 MiniMax Code 的工作区，用 miniapp init 绑定，
然后 miniapp publish。面板里会出现「事实闸 FactScribe」。

### 单独跑引擎（不依赖 Mini App 宿主）

~~~bash
cd integrations/minifactscribe
node --input-type=module -e '
import { createHash } from "node:crypto";
import { auditProject } from "./miniapp/node/audit.mjs";
import { buildDemoProject } from "./miniapp/node/demo.mjs";
const sha = (t) => createHash("sha256").update(String(t ?? ""), "utf8").digest("hex");
const a = auditProject(buildDemoProject(sha));
console.log(a.verdict, a.exitCode, a.red.map((i) => i.code), a.yellow.map((i) => i.code));
'
~~~

预期读数：red 1，红牌 UNMATCHED_NUMBER / MISSING_CITE / BIB_NO_STABLE_ID，
黄牌若干 UNBOUND_NUMBER / UNUSED_BIB / LOW_BINDING_RATE。

---

## 测试

~~~bash
cd integrations/minifactscribe
node --test tests/
~~~

31 例判据层自测，全离线（`node:test` + `node:assert`，零第三方依赖）。每个判据都有正反两例：
数字归一化与值域、绑定硬约束、引用族 fail-closed、稳定标识、派生事实重算、
来源哈希现算（据未改）、保护面里的事实标记/数字/引用、呈现层折叠、
以及联网核验并入后的派生视图重算。

另有 2 例是**与 Python 原版的一致性锁**（`tests/conformance.test.mjs`）：读上游投影好的
`tests/conformance/project.json`，跑 `auditProject`，核心错误码多重集必须与
`tests/conformance/expected.json` 里 Python 版的读数完全相等。为什么不比、锁哪些码、
怎么重生成，见 `docs/design/SPEC-CONFORMANCE.md`。

上游的 Python 测试矩阵（`python3 -m unittest discover -s tests`）与本移植件的判据各自独立；
两侧唯一的交汇点就是这把一致性锁——它不要求两边逐字相同，只要求对同一份夹具报出同一组码。

另有 7 例暗色主题不变量（`tests/styles.test.mjs`）与 16 例呈现层可读性不变量
（`tests/ui.test.mjs`）：违规码必须有中文短名、内容改过但没重跑审计必须声明结果过期、
判定不能只靠颜色承载、危险动作必须先确认、表单错误要指到字段。四组共 56 例，全部离线。

---

## 演示数据

用的是本仓库 examples/minimal 的同一批数据（MIT 许可）：

- 3 条事实：A1 = 10/16、A3 = 8/16，A2 = 56.25% 是 expr 派生的
- 1 份来源材料 results/swb16.md（哈希现算）
- 2 条上游 bib + 2 条演示用的坏条目

正文沿用上游样例，故意埋的问题与上游一致：

- 47.3,ms —— 账外数字 → UNMATCHED_NUMBER（红）
- cite{ghost2024} —— bib 里没有的 key → MISSING_CITE（红）

另加两项用来演示本移植件独有的能力：一条没有稳定标识的 bib（BIB_NO_STABLE_ID），
一个在线查无此文的 DOI（CITE_FAKE，需联网核验才有）。

上游那份样例的 audit 读数是 2 红 8 黄；这里少一条 UNSCANNED_TEX（没有 main.tex 入口），
多一条 BIB_NO_STABLE_ID，绑定率同为 4/10。

---

## 边界

绿只说明三件事：账有据、据未改、文有绑。**它不说明结论为真**，也不替审稿人判断结论是否成立。

移植件在上游边界之外还有两条自己的边界：

- **联网核验依赖网络。** 没网或被限流时，CITE_FAKE 这类红牌出不来，会退成黄牌。
- **判定层逐条报，呈现层折叠。** 一份材料对应几十条事实时，失配会按来源折叠成一条并列出受影响的 id，
  判定数组与退出码不受影响。KPI 同时给「N 类 / M 条」两个口径。

---

## 目录

~~~
integrations/minifactscribe/
├── README.md                    # 本文件
├── package.json                 # Mini App 包声明
├── icon.png
├── .minimax-plugin/plugin.json  # 插件清单
├── tests/
│   ├── audit.test.mjs           # node:test，31 例，全离线
│   ├── conformance.test.mjs     # 与 Python 原版的一致性锁，2 例
│   ├── styles.test.mjs          # 暗色主题不变量，7 例
│   └── ui.test.mjs              # 呈现层可读性不变量，16 例
└── miniapp/
    ├── miniapp.json             # surface / runtime 配置
    ├── client/                  # 浏览器端：index.html / app.js / styles.css
    └── node/                    # Node 端：audit.mjs（引擎）/ server.mjs（API）/ demo.mjs（演示数据）
~~~

- audit.mjs —— 审计引擎，纯函数，无 I/O
- server.mjs —— REST API 与 dataDir/ 持久化（原子写）
- demo.mjs —— 演示数据
- tests/audit.test.mjs —— 判据层的正反例
- tests/conformance.test.mjs —— 核心错误码与 Python 原版比对（批 138）
- tests/styles.test.mjs —— 暗色主题不变量（主按钮 hover、滚动条配色）
- tests/ui.test.mjs —— 呈现层可读性不变量（中文短名、过期提示、危险动作确认）

## Tested environment

- macOS，MiniMax Code 3.1.14（Mini App 3.1.14）
- Node 24.19
- 零第三方依赖；`node --test tests/` 全离线

## Data & access

- 默认不联网：审计与演示数据都在本地；只有点「联网核验存在性」会访问 Crossref / arXiv。
- 项目数据存在宿主分配的私有 `dataDir`，不写工作区。
- 目前不声明 `agentAccess` / `toolAccess`；以后若声明，会在这里写清 Agent 会读写什么、调用哪些工具。

---

## 许可

本移植件与本仓库同属 MIT。移植自 bigismall-Ai/FactScribe 的部分保留了上游的语义与代码结构，
版权归 FactScribe contributors。
