# FactScribe

**中文** · [English](README.en.md)

AI 写论文，最危险的不是写得不好，是**写得很像真的**：

- 数字是编的——「准确率 94.3%」听着专业，原始实验记录里根本没有这一行；
- 引用是编的——`\citep{smith2023}` 引了一篇根本不存在的论文。

这两种错，**读起来完全正常**。审稿人不会去翻你的实验日志，评审也不会去查每条 DOI，于是它们就留在稿子里，进了会议版本。

FactScribe 就是拦这个的。它是**一道机械闸门**：把正文里每个数字、每条引用，逐个钉回一份签过字、算过哈希的原始材料。数字对不上账，红；引用落不到稳定标识，红。

**它不管**：你的结论对不对、写得好不好读、审稿人喜不喜欢。它也不替你写正文。

不依赖模型 SDK，纯标准库，Python ≥ 3.10。

---

## 目录

- [五分钟上手](#五分钟上手)
- [只想看看论文写得怎么样？](#只想看看论文写得怎么样)
- [论文工作台（Mini App）](#论文工作台mini-app)
- [命令参考](#命令参考)
- [改稿与人工确认](#改稿与人工确认)
- [三道闸](#三道闸)
- [安全与联网边界](#安全与联网边界)
- [可选外部件](#可选外部件)
- [退出码](#退出码)
- [已知缺口](#已知缺口)
- [复现与贡献](#复现与贡献)

---

## 五分钟上手

先造一份最小的论文项目，再往里放一条真数字。

```bash
python3 -m factscribe init mypaper && cd mypaper
```

`init` 生成 7 个文件：项目声明 `factscribe.toml`、主文件 `main.tex`、一节正文 `sections/01-intro.tex`、空账本 `facts/01-core.toml`、人签清单 `results/MANIFEST.toml`、`refs.bib`、项目说明 `README.md`。

接着造一份**原始材料**——实验跑出来的日志、结果文件、统计输出，都算：

```bash
printf '50 道题里答对 42 道。\n' > results/exp.md
```

把它记进事实账：

```bash
python3 -m factscribe fact add . \
  --id A1 \
  --claim "实验在 50 道题里答对 42 道" \
  --value "50/42" \
  --source results/exp.md \
  --locator "第 1 行"
```

> **`--value` 要照产物的原文顺序写数字。** 上面这行产物里先出现 50、后出现 42，所以 value 写 `50/42`；写成 `42/50` 会被拒——数字按出现顺序逐个比对，对不上就是编的。这道闸叫 **value 硬校验**，CLI 的 `fact add`、MCP 的 `factscribe_add_fact`、工作台的「插入事实」三处同一套判据。

`fact add` 会算出 `results/exp.md` 的 sha256 并打印一行。**它不替你签**——那行要你亲手抄进 `results/MANIFEST.toml`：

```toml
[manifest]
signed_by = "你的名字"
signed_at = "2026-11-23T16:00:00Z"
version = 1

[files]
"results/exp.md" = "d5e19855dfdd4d78394a2e721a6939733979998ac3a02f956bd5b90726a34ac4"
```

签完检查一遍账本本身：

```bash
python3 -m factscribe check .    # id 唯一、sha256 现算、人签清单、表达式算术、同值冲突
```

最后在正文里挂上钩子——`\fact{A1}` 的意思是「这一行的数字属于 A1」：

```tex
\section{引言}

这项实验在 50 道题里答对 42 道\fact{A1}。
```

```bash
python3 -m factscribe audit .    # 0 红 / 0 黄 → 绿
python3 -m factscribe build .    # 编 PDF（需要 tectonic）
```

跑出一片红先看 [`docs/TRIAGE.md`](docs/TRIAGE.md)，每一步的细节在 [`docs/QUICKSTART.md`](docs/QUICKSTART.md)，已有论文要接进来先看 [`docs/ADOPT.md`](docs/ADOPT.md)。

---

## 只想看看论文写得怎么样？

不想记账、不想学 LaTeX 宏，只想知道自己这篇稿子现在什么状态——起一个本地网页工作台就够了：

```bash
python3 -m factscribe workbench --root /path/to/你的论文目录
```

它会扫这个目录，把含 `factscribe.toml` 的子目录认成论文项目（同名根目录的两语言盘 `paper` 与 `paper-zh` 会聚合成一个项目），起一个只绑回环的本地服务并自动打开浏览器。页面左边是目录和正文，右边是面板：检查报告、文风闸、双语对账、证据锁、事实账、知识库。

这一条路**只读**，不碰你的盘（打开项目本身会写一次 `last_opened`，那是记录「我上次在这篇上」，不是改内容）。

想在自己的代码里问「这篇稿子现在绿不绿」，用 MCP：`factscribe mcp <项目目录>` 暴露 `status` / `project` / `brief` / `audit` 五个只读工具；`--allow-write` 才多出写章节、追加事实、冻结/解冻证据四个写工具。

---

## 论文工作台（Mini App）

上面那个 `workbench` 命令是给脚本和本地开发用的。想要**在自己的编辑器里写论文**，装 Mini App 版：它是 MiniMax Code 的一个插件，把 FactScribe 的整套闸门搬进聊天窗口旁边的一个页面里。

### 它是什么

一个本地论文工作台页面（路由 `/workbench`）。它不是云服务，不上传你的稿子：Node 薄壳占一个回环端口伺服页面，Python 引擎是**随包附带**的（vendored 在插件里），不用另外装 Python 包。

它和 CLI 是同一套引擎、同一套判据——`audit` 在页面上跑出来的红，和你在命令行跑出来的红是同一批红。

### 怎么装

```bash
cd miniapp
./build.sh          # 从仓源 vendor 引擎 + 同步前端 + 跑包级契约自检
./install.sh        # 同步到 ~/.minimax/plugins/factscribe/
```

`install.sh` 是幂等的，跑多少遍结果一致；`./install.sh --check` 只检查装没装全，不写任何东西。装完重启 MiniMax Code 桌面端。

MiniMax Code 3.1.11 起也可以直接从 Git 仓库导入：贴仓库地址、选中包目录、核对预览即可。

### 怎么打开

重启后对助手说「打开 FactScribe 论文工作台」。首次打开会问你**论文根目录**——任何一个包含 `factscribe.toml` 的目录都算，之后能在设置页改。

### 页面里能做什么

**稿盘与正文**——一个项目可能有几个语言盘（`paper` / `paper-zh`）。左栏是目录，每行后面有一支笔，**点开就能改这一节的标题**；封面标题旁也有一支笔，改的是这个盘入口 `.tex` 里的 `\title{…}`。两条都是独立写盘通道，各带指纹闸与原子写（落盘前留 `.bak`），文件里其余字节一字不动。

**右栏可以拖**——正文左、面板右，中间那条分隔条**拖一下就改左右比例**（240–640px 钳位），松手才记住；双击分隔条回到默认。改完刷新页面还在。

**正文直接就是编辑器**——段落天生可编辑，不用进什么「编辑模式」。正文里的 `\fact{}`、`\cite{}`、`\ref{}` 和绑定了的数字会显示成芯片，你改字它们不动。

**检查报告**——体检摘要加发现清单。四步链的最后一环「出证」读数不变：declared / frozen / entries / sha256 / current_sha256 / mismatch 各自独立。

**文风闸**——只报能机械判定的公式化写法：破折号插入语、标题过长、套话连接词、空泛形容词、同构三点并列、超长句、节奏与句长分布等。它只出黄牌，不阻断，不改正文。

**双语对账**——同一项目两个语言盘之间逐条比事实账的承重字段和 `refs.bib` 条目，漂移逐条列出来。

**证据锁**——独立只读卡：`frozen` / `entries` / `sha256` / `current_sha256` / `mismatch`。冻结之后清单被改过，`mismatch` 会告诉你哪几节、哪几条 fact 动了、为什么红。

**事实账与知识库**——对账本（按 id / 主张 / 值 / 来源搜）、翻项目资料。写任何涉及数字的内容前，先在这儿对账：**账上没有的数字不得编造**。

**助手面板**——跑在 MiniMax Code 自己的模型上，界面中英双语可切。

### 助手没有直接写稿的接口

这是**安全边界**，不是功能缺失。

助手手上只有 **17 个 MCP 工具**：

- **只读 12 个**：`fs_status`（项目与稿盘清单）、`fs_get_outline`（目录树）、`fs_read_section`（读正文）、`fs_get_report`（检查报告）、`fs_get_style`（文风闸）、`fs_mirror_check`（双语对账）、`fs_get_evidence_status`（证据锁）、`fs_get_brief`（写作简报：这节能引哪些已核验的数字）、`fs_get_venue`（版式与刊物要求）、`fs_query_facts`（对事实账）、`fs_search_kb`（搜知识库）、`fs_list_proposals`（看待确认的提议单）；
- **只提议 5 个**：`fs_propose_edit`（改一段正文）、`fs_propose_add_fact`（追加一条事实）、`fs_propose_evidence_freeze` / `fs_propose_evidence_unfreeze`（冻结/解冻证据清单）、`fs_propose_export_bundle`（导出投稿包）。

「提议」的意思是：助手算好一份改动，落成一张**提议单**，**不碰你的盘**。你在页面的「待确认」差异卡里看到改前/改后，**点「采纳写回」才落盘**；不采纳就什么都不写。

每张提议单带一枚 `before_sha` 指纹——如果这期间那段正文在别处被改过（另一个窗口、外部编辑器），采纳会被拒（`BLOCK_STALE`），卡片置灰，账本 sha 不变。

助手也**写不进**自己发明的保护面：正文里凭空多出来的 `\fact{}` / `\cite{}` 会被服务端剥掉并记一条告警。数字只能来自账本里的 `value`，服务端再过一道 value 硬闸。

界面的中英双语**只作用在展示层**。落盘层的散文（`before_text` / `after_text` / `warnings` / `label` / `note`）一字不动，翻译不会渗进你的稿子。

---

## 命令参考

`factscribe` 一共 **29 个**子命令。下面按写论文的流程分组，不是按内部模块分组。

### 上手

| 命令 | 干什么 |
|---|---|
| `init` | 生成最小论文骨架（7 个文件）；同参数两次生成逐字节一致 |
| `doctor` | 上手自检：环境（Python/tectonic/poppler/字体/git）与项目（声明/账/签/冻结）逐项检查，给修复命令；不是闸门，不影响判定 |
| `fonts` | Fandol 中文字体缓存：`--status` 看状态，`--fetch` 下到本地缓存（4 个必需 OTF，约 26.7 MB） |

### 写作

| 命令 | 干什么 |
|---|---|
| `preamble` | 生成 `audit/preamble.tex` 里的 `\fact` 与 `\fsignore` 宏 |
| `brief` | 起草简报：从账生成节清单、可用主张与数字、术语、硬约束、篇幅预算，交给写作模型当依据 |
| `prescribe` | 处方层：某条判据触发后下一步怎么改；13 条处方，只给已验证的改法，不进判据、不产生分数 |
| `terms` | 术语候选：`suggest` 从正文抽候选出 TSV，`add` 只写你 `--pick` 点名的形式 |
| `evidence` | 证据清单：`--suggest` 出可直接粘的 `[evidence]` 块，`--freeze` 冻结，`--unfreeze --reason` 解冻留痕 |

### 对账闸

| 命令 | 干什么 |
|---|---|
| `check` | 查事实账本身：id 唯一、sha256 现算、人签清单、表达式算术、同值冲突 |
| `audit` | 核心校验：内联绑定、数字回账、引用落稳定标识、覆盖报告 |
| `matrix` | 生成追溯矩阵 `audit/matrix.md` |
| `fact` | 记账：`add` 自动算哈希写一条事实（过 value 硬闸），但不替你签清单；`import` 把已签收的报告导进账 |
| `report` | 归一化实验报告：`check` 跑探针取数、`lock` 写锁、`sign` 出审阅卡并签收（见 [`docs/design/SPEC-REPORT-SYNC.md`](docs/design/SPEC-REPORT-SYNC.md)） |
| `verify-pdf` | PDF 回检：文本层、栅格页、双向多重集、stamp 验签 |
| `mirror-check` | 双语双盘账本逐条比对：facts 承重字段＋bib 条目级，漂移逐条列 |
| `textreuse` | 双目录字面重合检测：逐字照搬**与近字面机械重合**（多尺度词窗＋句级包含）逐段列出两侧行区间、重合词数与匹配来源；只查字面层，改写与洗稿不在口径内 |

### 改稿

| 命令 | 干什么 |
|---|---|
| `protect` | 改写保护面：比对改写前后六类不许变的内容 |
| `style` | 文风闸：公式化写法报黄，证据缺钉报红 |
| `tide` | 改动账：涨、落、波及面、闭合，全成或全退；可存快照回滚 |
| `review` | 改写验收：保护面、复检、闭合一次判完，给通过、需复核或拒绝 |
| `polish` | 给 LLM 的润色入口：`--print` 出手册，`--plan` 出工作单 |

### 交付

| 命令 | 干什么 |
|---|---|
| `build` | 编译 PDF；没有配置构建命令时自动用 tectonic，中文缺字体自动兜底 |
| `figures` | 画图管线：人填图规格 `figures/*.fig.toml`，机械出图、随图 CSV 与绑定表；`check` 四面对账 |
| `bundle` | 投稿工件包：闭包收集、清单门、打包加 MANIFEST；期刊差异走项目侧 `bundle-checklist.toml` |

### 接口

| 命令 | 干什么 |
|---|---|
| `serve` | 本地工作台 HTTP API：只绑回环，默认随机 token；默认只读，`--allow-write` 才开放写，`--allow-build` 才允许编译 PDF |
| `mcp` | MCP stdio 服务器：把 `status`、`project`、`evidence_status`、`brief`、`audit` 五个只读工具暴露给 agent；`--allow-write` 才多出写章节、追加事实、冻结/解冻证据四个写工具 |
| `web` | 本地工作台页面：`serve` 同款后端加工作台界面；默认只读，`--allow-write` 才可写，`--allow-build` 才可编译 PDF |
| `workbench` | 工作台网页：扫 `--root` 下的 `factscribe.toml`，把同根名的两语言盘（`paper` 配 `paper-zh`）聚合成项目，起本地服务；正文与状态行读的是真文件。带写接口：正文就地编辑写回（`\fact`/`\cite`/`\ref` 与绑定数字原样保留，保存留 `.bak`）、目录调序/删除（挪 `sections/attic/`）/新建、改章节名与论文标题、段落菜单插入事实、项目新建与编辑 |
| `workbench new` | 新建论文项目：在 `--root` 下落目录骨架（`factscribe.toml`＋`sections/`＋`facts/`＋`README.md`＋`main.tex`），项目目录与实验报告目录写进 `[workbench]` 表；`--lang en/zh/both` 决定建几个语言盘 |

接口契约见 [`docs/design/SPEC-SERVE.md`](docs/design/SPEC-SERVE.md) 与 [`docs/design/SPEC-MCP.md`](docs/design/SPEC-MCP.md)。

### 文献

| 命令 | 干什么 |
|---|---|
| `refs` | 文献登记面：`dedupe` 查 bib 跨条目同 DOI 与同 arXiv id，`register` 核对待补登记表 `refs/todo.toml`（缺字段逐项点名），`search` 联网取候选题录（候选入正式 bib 必须人采，机器不代签） |

除 `mcp` 外都支持 `--json`。`check` 与 `audit` 支持 `--strict`，黄牌也当红牌，供 CI 使用。

---

## 改稿与人工确认

这一条链是 FactScribe 和「让 AI 直接改稿」最大的区别。

**AI 不能直接写你的稿子。** 无论走 CLI 还是 Mini App，AI 想改正文，只有「提议」这一条路：

1. **建单**——助手算出改动，落成一张提议单，**不碰盘**。CLI 侧是 `factscribe workbench` 的提议单接口；Mini App 侧是 5 个 `fs_propose_*` 工具。
2. **看差异**——页面上出现一张差异卡：改前 / 改后并排，附带告警和理由（为什么要这么改）。
3. **人点采纳**——只有人点「采纳写回」，改动才落盘。不点，什么都不发生。
4. **指纹闸**——提议单带 `before_sha`。落盘前再核一次：那段正文是不是已经被别处改过？改过了就**拒写**（`BLOCK_STALE`），卡片置灰，不覆盖别人的字。

落盘那一步走的是和手改正文**同一条**通道：原子写、留 `.bak`（多代轮转，`.bak` 是上一版、`.bak.1` 是上上版，互不覆盖）、保护面不许丢。

账与证据面的四类动作（追加事实、冻结证据、解冻证据、导出投稿包）也走同一条「人点才写」的路，同样带指纹闸。

追加事实额外有一道**账本指纹闸**：提议建单时记下目标账本文件的 sha，采纳时发现账本在别处动过，就拒写并把卡片置灰。

导出投稿包前可以**先看一份清单**——预览只是给你看的，判定权仍在既有清单门，门不过照样不出包。

---

## 三道闸

三道闸分别管数字与引用、改写保护、文风与术语。它们可以单独跑，也可以串成一条发布前检查。

**第一道是数字与引用。** 正文写 `\fact{A1}`，就声明这一行的数字属于事实 `A1`；审计会反查，该行每个数字都必须落在 `A1` 的值域里。所有 `\cite` 家族的 key 必须出现在 `refs.bib` 里，bib 条目还要有 `arxiv` 或 `doi`（`@misc` 可用 `url`）。数字归一化后 `1,234` 等于 `1234`，`0.90` 等于 `0.9`，`53k` 等于 `53000`。

**第二道是改写保护。** 保护面指改写前后不许变的六类内容：事实标记、数字、引用、公式、表格、交叉引用。只改标点与断句应当全绿；动了任何一个数字、公式或引用即红，并给出 `文件:行` 与改成了什么。

```bash
python3 -m factscribe protect --before 旧稿/ --after 新稿/
```

**第三道是文风与术语。** 文风闸只报可机械判定的公式化写法：破折号插入语、标题过长或带解释、套话连接词、空泛形容词、同构三点并列、超长句、节奏与句长分布等。它出黄牌，不阻断，不改正文。改写复检有四条：`HEADING_ECHO` 查首句是否复述标题，`HEADING_RELATION_CHANGED` 查标题里的对立关系是否被换掉，`HEADING_SUBJECT_LOST` 查旧标题的主语是否丢失，`HEADING_SUBSTITUTED` 查是不是只换了冒号没重写。术语层分两册：论文术语 33 条来自 `paper-zh/GLOSSARY.md`，工作区流程词 153 条来自词册。

**改动账**（`tide`）把一次改写当成一笔事务：涨是改了什么（两个目录的文件哈希差），落是改后的真实文件状态（重新读盘再算哈希，不许人填），波及面由 `\input` 与 `\include` 的反向引用闭包自动计算，闭合要求三者对得上。缺一项就全退，退出码 1。这里没有自报清单——人只能看结果，不能填清单。

---

## 安全与联网边界

**默认全离线。** `refs search` 是唯一默认对外联网的命令，它只发查询词，不发正文，也不发本地路径。

有两处要显式加参数才会发请求：`audit --resolve` 只发 arXiv 与 DOI 编号给解析服务，`fonts --fetch` 下载 Fandol 字体包。另外如果你在工作台里配了自定义模型端点，AI 对话会往那个端点发提示词——那是**你自己填的地址**，不是默认行为。

**只对你自己信任的项目跑 `build` 与 `audit --build`。** `project.build` 是项目声明里的 shell 命令，工具会照原样执行。`audit` 本身不编译、不执行它；`--build` 才会。

**联网的事说清楚：** 检查报告、证据锁、事实账这些读数全在本地算，不外传。工作台和 Mini App 都只绑回环地址（`127.0.0.1`）。

**验证一下再信：** `factscribe doctor` 会把环境（Python 版本、tectonic、poppler、字体、git）和项目状态（声明、账、签、冻结）逐项查一遍，每项给一条修复命令。

---

## 可选外部件

运行时只依赖 Python 标准库（≥ 3.10）。没有模型 SDK，没有第三方依赖，不调用任何 LLM。`pip install -e .` 只是省事，不装也能用 `PYTHONPATH` 跑。

可选的外部件只有两样，缺了都有明确去处：

| 外部件 | 谁要它 | 缺了怎么办 |
|---|---|---|
| poppler（`pdftotext`/`pdfinfo`/`pdfimages`） | `verify-pdf` 的 PDF 回检层 | 报 `PDF_TOOL_MISSING` 并退出码 8，不静默放行；其余命令照跑 |
| tectonic | `build`、`audit --build` | 报缺引擎并退出码 8；不带 `--build` 的 `audit` 不编译，不需要它 |

中文字体走同一条路：`fonts --fetch` 把 Fandol 字体包（4 个必需 OTF，约 26.7 MB）下到本地缓存（`~/.cache/factscribe/fonts/fandol`），`build` 缺字体时有系统字体兜底。

---

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 绿，无红无黄 |
| 1 | 红，有违例 |
| 2 | 配置或用法错，工具没跑起来 |
| 3 | 黄，跑完了但有未核验或未绑定的项，不判死但不算绿 |
| 4 | 工具内部错误 |
| 5 | 覆盖缺口 / PDF 与签名信任链失败（如 `\input` 目标不存在，闭包没展开全） |
| 6 | `RED(PROOF)`：`--require-proof` 未达标 |
| 7 | `RED(STALE|REPLAY)`：报告或 PDF 过期、nonce 重放 |
| 8 | 必需工具缺失（PDF 工具链或编译引擎），不静默放行 |
| 9 | `RED(ATTACK_OPEN)`：ATTACKS.md 有 blocking/open 条目 |

缺 `factscribe.toml`、事实账为空、正文为空、`refs.bib` 缺失，一律退出码 2 并说清原因，不静默放行。

退出码闭集以 [`factscribe/checks.py`](factscribe/checks.py) 的 `EXIT_CODE_CLOSED_SET` 为唯一权威表，新增退出码等于修约。

---

## 工作台运行须知

改完代码必须重启。工作台是**常驻进程**：Python 端点与前端静态文件都是启动时加载的。改完代码还看着旧页面／旧行为，多半是**旧进程还在跑**，不是改动没生效。

```bash
# 1）看有没有残留的旧服务进程
ps aux | grep -E "factscribe.*workbench" | grep -v grep

# 2）杀掉残留进程（本地开发机；共享机器上先确认是自己的）
pkill -f "factscribe.*workbench"

# 3）重新起
python3 -m factscribe workbench --root /path/to/papers
```

规矩四条：

1. **改完 Python 或前端代码，一律重启服务再验收**——否则测的是旧进程；
2. 前端静态文件带 `Cache-Control: no-store`，但浏览器仍可能缓存 CSS/JS，刷新不出来就硬刷新（macOS：`Cmd+Shift+R`）；
3. 只读端点：`/api/disk/<项目>/<盘>/report`、`/api/disk/<项目>/<盘>/machine`；`POST /api/disk/<项目>/<盘>/report/rerun` 是**只读重跑**真闸——subprocess 跑 `factscribe audit --json`（不加 `--build`，不编译不落盘），限时 120 秒，跑前跑后对项目目录做哈希对比，**保证零写入**；
4. 写端点：`POST /api/disk/<项目>/<盘>/edit`（正文就地编辑，走指纹闸与保护链）、`POST /api/disk/<项目>/<盘>/action`（`action=pdf|bundle|open_dir`，分别走真编译、真导出、macOS `open`）、`POST /api/disk/<项目>/<盘>/fact/insert`（插入事实绑定）、`GET /api/disk/<项目>/<盘>/pdf`（回传 `main.pdf` 供预览/下载）、`POST /api/project/<项目>/reports/delete`（删导入草稿记录，**报告源文件不动**）。

Mini App 侧的对应纪律：改前端要改**源**（`factscribe/workbench/static/`）再 `./build.sh` 同步，别直接改载荷——三份 `app.js` 副本必须逐字节一致，有测试守着。

---

## 已知缺口

剩下的问题如实写在 [`docs/release/KNOWN-GAPS.md`](docs/release/KNOWN-GAPS.md) 里。以下是**当前真实状态**下已知的、本轮实测确认的缺口。

### 结构性边界（不打算修）

1. **信任根是人签。** 若 agent 同时伪造账与据，工具无法发现——它只能保证「账、据、文自洽且据未被改」。
2. **出题人与实现方同机。** 盲测只能算弱盲测。
3. **不做 OCR。** 图片承载的定量一律判红。
4. **抄没抄别人只查字面层。** 逐字照搬与近字面机械重合由 `textreuse` 机械列出；改写、洗稿、AI 拼装属语义层，不在口径内。

### 工作台保存口径（已实测确认）

从工作台页面保存一段正文时，**该段内部**的两个渲染口径会保留下来，不是逐字还原：

- **段内换行会被压成空格。** 源文件里一段 LaTeX 折了几行，保存后变成一行（段与段之间的空行保留）。这是「渲染层怎么显示，保存层就怎么存」的结果。
- **`---` 会被写成 `—`（em dash）。** LaTeX 的破折号写法在渲染层被归一化成真正的 em dash 字符，保存时写回去的就是这个字符。

这两条只影响**该段正文内部**；文件里其它段落、`\fact` / `\cite` / `\ref` 保护面、绑定的数字都逐字不变。

### 其它当前状态

- **PDF 层在 CI 上不验证。** GitHub runner 装不上 poppler（apt 镜像连不上），workflow 里那步是「尽力而为」，装不上就告警继续；PDF 层 **35 例**自动跳过并在测试尾部显示 `skipped=35`，其余照常跑（实测：藏掉 poppler 后整套 `OK (skipped=35)`）。PDF 层的全量覆盖在本地：`./scripts/preflight-ci.sh`（本机装了 poppler 时 `skipped=0`）。
- **双语双盘靠手工对齐。** `mirror-check` 只报漂移，不同步。
- **处方层不进判据。** 13 条处方只给可执行改法，不改变 `audit` / `style` / `protect` 的任何判定与退出码。

这四条结构性边界都指向同一个定位：账、据、文彼此对得上，据也没有被偷偷换过。至于论文的结论，它不答。

---

## 复现与贡献

```bash
python3 -m unittest discover -s tests     # 2350 例，全离线
./scripts/preflight-ci.sh                 # 本地等价 CI：干净克隆 + 3.10/3.11/3.12/3.13/3.14
```

**CI 不验证 PDF 层**：GitHub runner 装不上 poppler（apt 镜像连不上），workflow 里那步是「尽力而为」，装不上就告警继续；PDF 层 35 例自动跳过并在测试尾部显示 `skipped=35`，其余照常跑。PDF 层的全量覆盖在本地：`./scripts/preflight-ci.sh`（本机装了 poppler 时 `skipped=0`）。

`examples/minimal/` 是验收样例：三条事实、两节正文，故意混入一个编造数字与一个假引用。`audit` 必须只报这两处红。

规范在 `docs/design/`，实现记录在 `docs/implementation/`，历史在 `CHANGELOG.md`。提交前请读 [`CONTRIBUTING.md`](CONTRIBUTING.md)，PR 必须带测试。

---

## 它到底保证什么

完整口径见 [`docs/WHAT-IT-PROVES.md`](docs/WHAT-IT-PROVES.md)，设计侧见 [`docs/design/SPEC-V1.md`](docs/design/SPEC-V1.md)。

一句话：**它保证账、据、文三者自洽，且据未被改；它不保证论文的结论为真。**

审计绿，意思是 0 红 0 黄，这个数字和这条引用都对上了账——**不是「论文没问题」**。
