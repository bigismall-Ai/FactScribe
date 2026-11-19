# FactScribe

**中文** · [English](README.en.md)

FactScribe 是一道机械闸门，专门拦 AI 写论文时最危险的两类编造：数字没有出处，引用指向不存在的文献。它不写正文，也不改正文。它只回答一件事：这句话里的每个数，能不能回到一份签过字、算过哈希的原始材料。

不依赖模型 SDK，纯标准库，Python ≥ 3.10。

## 身份与安全边界

管的是三件事对不对得上：账有据、据未改、文有绑。

- **账有据**：正文里的每个数字都有一条事实账里的记录，那条记录指向一份原始材料，材料算过 sha256，有人签过字。
- **据未改**：从签字那一刻起，原始材料的哈希没变过。
- **文有绑**：正文里的 `\fact{A1}` 说的是「这一行的数字属于 A1」，审计会逐个数字回账去查。

不管的是另外四件事：

- 结论对不对，不管。
- 写得好不好读，不管。
- 审稿人喜不喜欢，不管。
- 抄没抄别人——只查字面层：逐字照搬**与近字面的机械重合**（多尺度词窗＋句级包含）由 `textreuse` 机械列出；改写、洗稿、AI 拼装属语义层，不在口径内（漏检属语义层）。

一句话记住：**它保证账、据、文三者自洽，且据未被改；它不保证论文的结论为真。** 完整的逐条口径见 [`docs/WHAT-IT-PROVES.md`](docs/WHAT-IT-PROVES.md)，设计侧见 [`docs/design/SPEC-V1.md`](docs/design/SPEC-V1.md)。

### 联网边界

`refs search` 是唯一默认对外联网的命令，它只发查询词，不发正文，也不发本地路径。

其余命令默认全离线。有两处要显式加参数才会发请求的开关：`audit --resolve` 只发 arXiv 与 DOI 编号给解析服务，`fonts --fetch` 下载 Fandol 字体包。

### 安全边界

只对**你自己信任的项目**跑 `build` 与 `audit --build`。`project.build` 是项目声明里的 shell 命令，工具会照原样执行。`audit` 本身不编译。

## 零依赖身份

运行时只依赖 Python 标准库（≥ 3.10）。没有模型 SDK，没有第三方依赖，不调用任何 LLM。`pip install -e .` 只是省事，不装也能用 `PYTHONPATH` 跑。

可选的外部件只有两样，缺了都有明确去处：

| 外部件 | 谁要它 | 缺了怎么办 |
|---|---|---|
| poppler（`pdftotext`/`pdfinfo`/`pdfimages`） | `verify-pdf` 的 PDF 回检层 | 报 `PDF_TOOL_MISSING` 并退出码 8，不静默放行；其余命令照跑 |
| tectonic | `build`、`audit --build` | 报缺引擎并退出码 8；不带 `--build` 的 `audit` 不编译，不需要它 |

中文字体走同一条路：`fonts --fetch` 把 Fandol 字体下到本地缓存，`build` 缺字体时有兜底。`doctor` 会把这几样连同项目状态逐项查一遍，每项给一条修复命令。

## 五分钟上手

```bash
python3 -m factscribe init mypaper && cd mypaper   # 7 个文件：声明、主文件、一节正文、空账、人签清单、refs.bib、README
printf '50 道题里答对 42 道。\n' > results/exp.md   # 造一份原始材料
python3 -m factscribe fact add . \
  --id A1 \
  --claim "实验在 50 道题里答对 42 道" \
  --value "42/50" \
  --source results/exp.md \
  --locator "第 1 行"
```

`fact add` 自动算 `results/exp.md` 的 sha256 并打印一行。**它不替你签**：那行要你亲手抄进 `results/MANIFEST.toml` 的 `[files]`。

正文写上钩子：

```tex
\section{引言}

这项实验在 50 道题里答对 42 道\fact{A1}。
```

```bash
python3 -m factscribe audit .    # 0 红 / 0 黄 → 绿
python3 -m factscribe build .    # 编 PDF（要 tectonic）
```

每一步的细节见 [`docs/QUICKSTART.md`](docs/QUICKSTART.md)，跑出一片红先看 [`docs/TRIAGE.md`](docs/TRIAGE.md)，已有论文要接进来先看 [`docs/ADOPT.md`](docs/ADOPT.md)。

## 二十八个命令

`factscribe` 一共二十八个子命令。下面按写论文的流程分组，不是按内部模块分组。

### 上手

| 命令 | 干什么 |
|---|---|
| `init` | 生成最小论文骨架：项目声明、正文占位、空账、人签清单模板、refs.bib；同参数两次生成逐字节一致 |
| `doctor` | 上手自检：环境（Python/tectonic/poppler/字体/git）与项目（声明/账/签/冻结）逐项检查，给修复命令；不是闸门，不影响判定 |
| `fonts` | Fandol 中文字体缓存：`--status` 看状态，`--fetch` 下到本地缓存 |

### 写作

| 命令 | 干什么 |
|---|---|
| `preamble` | 生成 `audit/preamble.tex` 里的 `\fact` 与 `\fsignore` 宏 |
| `brief` | 起草简报：从账生成节清单、可用主张与数字、术语、硬约束、篇幅预算，交给写作模型当依据 |
| `prescribe` | 处方层：某条判据触发后下一步怎么改；只给可执行改法，不进判据、不产生分数 |
| `terms` | 术语候选：`suggest` 从正文抽候选出 TSV，`add` 只写你 `--pick` 点名的形式 |
| `evidence` | 证据清单：`--suggest` 出可直接粘的 `[evidence]` 块，`--freeze` 冻结，`--unfreeze --reason` 解冻留痕 |

### 对账闸

| 命令 | 干什么 |
|---|---|
| `check` | 查事实账本身：id 唯一、sha256 现算、人签清单、表达式算术、同值冲突 |
| `audit` | 核心校验：内联绑定、数字回账、引用落稳定标识、覆盖报告 |
| `matrix` | 生成追溯矩阵 `audit/matrix.md` |
| `fact` | 记账：`add` 自动算哈希写一条事实，但不替你签清单；`import` 把已签收的报告导进账 |
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
| `mcp` | MCP stdio 服务器：把 `status`、`project`、`brief`、`audit` 暴露给 agent；`--allow-write` 才开放写章节与追加事实 |
| `web` | 本地工作台页面：`serve` 同款后端加工作台界面；默认只读，`--allow-write` 才可写，`--allow-build` 才可编译 PDF |
| `workbench` | 工作台网页：扫 `--root` 下的 `factscribe.toml`，把同根名的两语言盘（`paper` 配 `paper-zh`）聚合成项目，起本地服务；正文与状态行读的是真文件。段二起带写接口：正文就地编辑写回（`\fact`/`\cite`/`\ref` 与绑定数字原样保留，保存留 `.bak`）、目录调序/删除（挪 `sections/attic/`）/新建、项目新建与编辑 |
| `workbench new` | 新建论文项目：在 `--root` 下落目录骨架（`factscribe.toml`＋`sections/`＋`facts/`＋`README.md`＋`main.tex`），项目目录与实验报告目录写进 `[workbench]` 表 |

接口契约见 [`docs/design/SPEC-SERVE.md`](docs/design/SPEC-SERVE.md) 与 [`docs/design/SPEC-MCP.md`](docs/design/SPEC-MCP.md)。

### 文献

| 命令 | 干什么 |
|---|---|
| `refs` | 文献登记面：`dedupe` 查 bib 跨条目同 DOI 与同 arXiv id，`register` 核对待补登记表 `refs/todo.toml`（缺字段逐项点名），`search` 联网取候选题录（候选入正式 bib 必须人采，机器不代签） |

除 `mcp` 外都支持 `--json`。`check` 与 `audit` 支持 `--strict`，黄牌也当红牌，供 CI 使用。

## 四件新东西怎么用

下面四段各是一个新子命令的最小例子。

### mirror-check

两个论文盘（中文盘与英文盘）的账本是手工对齐的，改一边忘了另一边，没有工具会说话，直到两边对不上。

```bash
python3 -m factscribe mirror-check paper-b paper-b-zh
```

事实账按 id 逐条比承重字段（claim、value、display、source、source_sha256、locator、expr、derived_from、kind），`refs.bib` 逐条比（title、author、year、doi、arXiv id）。漂移逐条列：盘、文件、id、字段、两侧值。退出码 0 是零漂移，1 是有漂移。

豁免面不判漂：正文、`main.tex` 导言区、`GLOSSARY.md`、生成物，以及 fact 的 confidence 与 note。命令只读，不写盘，也不同步。

### refs

```bash
python3 -m factscribe refs dedupe .                  # bib 跨条目查重：同 DOI 或同 arXiv id 报 REF_DUP_ID
python3 -m factscribe refs register .                # 核对待补登记表 refs/todo.toml，缺字段逐项点名
python3 -m factscribe refs search "fact scoring" --source crossref   # 唯一默认联网：只发查询词
```

`search` 把原始响应落进 `refs/candidates/`，旁边一份钉住 sha256 的 JSON 信封，编号列给人挑。`--pick 3` 把挑中的候选写进登记表 `refs/todo.toml`，不碰 `refs.bib`：入正式 bib 仍要人采。

### figures

图上的数字要是能回到账，图就不该由人往绘图工具里手抄。人只填图规格：

```toml
name = "acc"
kind = "bar"
caption = "两臂在同一组题上的解决数"
xlabel = "臂"
ylabel = "解决比例"
data = ["A1", "A3"]
labels = ["开臂", "对比臂"]
```

```bash
python3 -m factscribe figures gen .     # 出 figures/gen/acc.tex、acc.csv（随图数据）、acc.bind.toml（绑定表）
python3 -m factscribe figures check .   # 四面对账：规格 ↔ 绑定表 ↔ 随图 CSV ↔ 现行账本
```

数据点只许引 fact id。规格里出现裸数字就是配置错，退出码 2，且不生成半套产物。账上的值或 source_sha256 动过而图没重生成，`figures check` 必红，并逐个数据点点名。

### bundle

投稿要交几十个文件。少交一个（常见的是随图 CSV 或证据冻结文件），审稿人拿到的是不可复现的包；多交一个，没人说得清。

```bash
python3 -m factscribe bundle .                          # 收集 → 清单门 → 打包（默认落在项目外）
python3 -m factscribe bundle --verify mypaper.bundle    # 复算包目录的 MANIFEST.sha256
```

三步。收集：`main.tex` 起的 `\input` 与 `\include` 闭包，加上 refs.bib、figures/、tables/、facts/、runs/ 的已签收副本、audit/ 三件。清单门：逐项机械判（闭包完整、每图有随图 CSV、bib 无缺唯一键条目、evidence.lock 在场且未过期、audit 现跑无红），任一项不过就退出码 1 并逐项列出，每项三态：过、不过、豁免。导出：包目录加 `MANIFEST.sha256`（`shasum -a 256 -c` 可验）加 `BUNDLE-MANIFEST.json`（清单：收了哪些、哪些只记不收）。

期刊差异走项目侧的 `bundle-checklist.toml`，工具代码里零期刊专名：

```toml
# 附加检查项：kind 是 exists / glob_min / regex 三形之一
[[check]]
name = "匿名版存在"
kind = "exists"
path = "anonymous/main.tex"

# 排除声明：整件不进包
[[exclude]]
file = "sections/ack.tex"
```

完整样例见 [`examples/bundle-checklist.toml`](examples/bundle-checklist.toml)。

## 三道闸

三道闸分别管数字与引用、改写保护、文风与术语。它们可以单独跑，也可以串成一条发布前检查。

第一道是数字与引用。正文写 `\fact{A1}`，就声明这一行的数字属于事实 `A1`；审计会反查，该行每个数字都必须落在 `A1` 的值域里。所有 `\cite` 家族的 key 必须出现在 `refs.bib` 里，bib 条目还要有 `arxiv` 或 `doi`（`@misc` 可用 `url`）。数字归一化后 `1,234` 等于 `1234`，`0.90` 等于 `0.9`，`53k` 等于 `53000`。

第二道是改写保护。保护面指改写前后不许变的六类内容：事实标记、数字、引用、公式、表格、交叉引用。只改标点与断句应当全绿；动了任何一个数字、公式或引用即红，并给出 `文件:行` 与改成了什么。

```bash
python3 -m factscribe protect --before 旧稿/ --after 新稿/
```

第三道是文风与术语。文风闸只报可机械判定的公式化写法：破折号插入语、标题过长或带解释、套话连接词、空泛形容词、同构三点并列、超长句、节奏与句长分布等。它出黄牌，不阻断，不改正文。改写复检有四条：`HEADING_ECHO` 查首句是否复述标题，`HEADING_RELATION_CHANGED` 查标题里的对立关系是否被换掉，`HEADING_SUBJECT_LOST` 查旧标题的主语是否丢失，`HEADING_SUBSTITUTED` 查是不是只换了冒号没重写。术语层分两册：论文术语 33 条来自 `paper-zh/GLOSSARY.md`，工作区流程词 153 条来自词册。

## 改动账

`tide` 把一次改写当成一笔事务。四个条件全部成立才落账。账只认哈希。涨是改了什么，由两个目录的文件哈希差算出。落是改后的真实文件状态，重新读盘再算哈希，不许人填。波及面由 `\input` 与 `\include` 的反向引用闭包自动计算。闭合要求涨、落、波及面三者对得上。缺一项就全退。不写账本，不写派生视图，退出码 1。

这里没有自报清单。人只能看结果，不能填清单。工具同样不相信任何手写的改动说明，也不接受口头的补充。规范见 [`docs/design/SPEC-TIDE.md`](docs/design/SPEC-TIDE.md)。

## 处方层

`prescribe` 回答的是另一件事：某条判据被触发后，下一步到底怎么改。先看处方。它带 13 条处方，只给已经验证过的改法，并把已知坏改法写成禁做与反例。处方之间冲突时按固定优先序裁决，被压制的处方会明写让位。规范见 [`docs/design/SPEC-PRESCRIPTION.md`](docs/design/SPEC-PRESCRIPTION.md)。

这一层不进判据，也不产生分数。它不改 `audit`、`style`、`protect` 的任何判定与退出码。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 绿，无红无黄 |
| 1 | 红，有违例 |
| 2 | 配置或用法错，工具没跑起来 |
| 3 | 黄，跑完了但有未核验或未绑定的项，不判死但不算绿 |
| 4 | 工具内部错误 |
| 8 | 必需工具缺失（PDF 工具链或编译引擎），不静默放行 |

缺 `factscribe.toml`、事实账为空、正文为空、`refs.bib` 缺失，一律退出码 2 并说清原因，不静默放行。

## 工作台运行须知（改完代码必须重启）

工作台是**常驻进程**：Python 端点与前端静态文件都是启动时加载的。改完代码
还看着旧页面／旧行为，多半是**旧进程还在跑**，不是改动没生效。

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
2. 前端静态文件带 `Cache-Control: no-store`，但浏览器仍可能缓存 CSS/JS，
   刷新不出来就硬刷新（macOS：`Cmd+Shift+R`）；
3. 段三新增的端点是**只读**的（`/api/disk/<项目>/<盘>/report`、
   `/api/disk/<项目>/<盘>/machine`），
   `POST /api/disk/<项目>/<盘>/report/rerun` 是**只读重跑**真闸：
   subprocess 跑 `factscribe audit --json`（不加 `--build`，不编译不落盘），
   限时 120 秒，跑前跑后对项目目录做哈希对比，**保证零写入**；
4. 段五起，框架改成「左正文 ＋ 右固定导航面板（320px，可整体收起）」，
   右缘三竖标与右栏三标签退役。新增端点：
   `POST /api/disk/<项目>/<盘>/action`（`action=pdf|bundle|open_dir`，
   分别走 `buildpdf.auto_build` 真编译、`bundle.run_bundle` 真导出、
   macOS `open` 唤起访达）、
   `GET /api/disk/<项目>/<盘>/pdf`（回传盘里的 `main.pdf` 供预览/下载）、
   `POST /api/project/<项目>/reports/delete`（删导入草稿记录，
   **报告源文件不动**）；`POST /api/disk/<项目>/<盘>/edit` 的
   `block=cover-abstract` 写封面摘要（根文件 `abstract` 环境），
   走段二同一条保护通道（`\fact` 芯片原样保留、原子写、留 `.bak`）。

## 已知缺口

剩下的问题如实写在 [`docs/release/KNOWN-GAPS.md`](docs/release/KNOWN-GAPS.md) 里。另有三条结构性边界不打算修：信任根是人签，若 agent 同时伪造账与据，工具无法发现；出题人与实现方同机，盲测只能算弱盲测；不做 OCR，图片承载的定量一律判红。

三条边界都指向同一个定位：账、据、文彼此对得上，据也没有被偷偷换过。至于论文的结论，它不答。

## 复现与贡献

```bash
python3 -m unittest discover -s tests     # 1657 例，全离线
./scripts/preflight-ci.sh                 # 本地等价 CI：干净克隆 + 3.10/3.11/3.12
```

**CI 不验证 PDF 层**：GitHub runner 装不上 poppler（apt 镜像连不上），workflow 里那步是「尽力而为」，装不上就告警继续；PDF 层用例（36 例）自动跳过并在测试尾部显示 `skipped=`，其余照常跑。PDF 层的全量覆盖在本地：`./scripts/preflight-ci.sh`（本机装了 poppler 时 `skipped=0`）。

`examples/minimal/` 是验收样例：三条事实、两节正文，故意混入一个编造数字与一个假引用。`audit` 必须只报这两处红。

规范在 `docs/design/`，实现记录在 `docs/implementation/`，历史在 `CHANGELOG.md`。提交前请读 [`CONTRIBUTING.md`](CONTRIBUTING.md)，PR 必须带测试。
