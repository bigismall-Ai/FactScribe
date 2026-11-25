# F4 全仓扫描：用户内容载体的换行保真（读写点清单与读数）

本件是 F4 首轮（fix/f4-f7-newline-root-20261125，已并入 fix/defect-integration-20261125）
的续集。首轮按**已知清单**改了写盘侧与几个读盘点；本轮按「全仓枚举」做——
把仓内所有对用户内容载体的文本读写点逐个分档，漏网的补齐，每条留下可复核的证据。

## 一、判定口径

**用户内容载体** ＝ 用户手编 ＋ 工具会写回 ＋ 写回必须逐字节相同。正文 .tex、
.bib、factscribe.toml、事实账 facts/*.toml、术语表、用户文件副本都算。

**机器产物** ＝ 工具自己生成、自己消费，格式由工具定：JSON 报告、审计矩阵、证据锁、
清单 manifest、日志、派生卡片 md、字体缓存、语料/词库 TSV、.git 内部文件。

对用户内容载体，读侧与写侧**都要**不翻译换行：

* **写侧**不翻译 —— Windows 上默认文本模式把 '\n' 翻成 '\r\n'，已带 '\r\n' 的
  会被写成 '\r\r\n'（CR 被复制，内容损坏）。
* **读侧**不翻译 —— 默认文本模式做通用换行翻译（universal newlines），'\r\n' 被读成
  '\n'；读入→编辑→写回跑一遍，正文的行尾就被悄悄换掉了。

读到的文本若要进**分析层**（审计、闸门、文风、简报、诊断、术语、复用、保护面），
分析层是按行做事的（正则里用 $ 锚行尾），因此在分析入口**显式** to_lf 归一：
归一的是内存副本，磁盘字节一个不动；归一后与改前的「通用换行翻译」口径逐条相同
（正则命中、行号、发现条数都不漂）。这一层若不显式归一，行尾锚定的正则会在
CRLF 上失配——发现条数会漂，那是把 bug 换了一个。

## 二、用户内容载体：本轮补齐的点（读侧＋写侧）

| file:line | 原来 | 改成 | 为什么算用户内容 |
|---|---|---|---|
| factscribe/config.py:1848-1850 | _read_text 用 path.read_text | read_text_exact | 全仓读用户 .tex 的总入口；通用换行翻译把 CRLF 吃成 LF，接口层下发给编辑器的已不是用户原字节 |
| factscribe/config.py:1432 | _locate_id_line 用 read_text | read_text_exact | 事实账 facts/*.toml（用户手编）；只数行，CRLF→LF 是 1:1，行号不变 |
| factscribe/config.py:1820/1829/1834 | _read_text 直接喂解析 | to_lf(_read_text(...)) | 闭包展开的 \input 解析是分析层 |
| factscribe/audit.py:548 | full.read_text | to_lf(read_text_exact(full)) | 事实的 source 产物（用户文件）；只做数字比对 |
| factscribe/audit.py:966 | _read_text | to_lf(_read_text(...)) | 闭包外 .tex 的 UNSCANNED_TEX 判定 |
| factscribe/audit.py:1499 | main.tex 用 read_text | to_lf(read_text_exact(...)) | 主文件（PDF 结构性白名单） |
| factscribe/audit.py:324 / :1343 | text.split("\n") | split_lines(text) | 行号取行：split("\n") 在 CRLF 上会把 '\r' 留在行尾 |
| factscribe/checks.py:510 | run_packages 直接用 sections | 入口 to_lf 归一 | 核验槽的分析入口 |
| factscribe/style.py:3073 | analyze 直接用 sections | 入口 to_lf 归一 | 文风分析入口 |
| factscribe/style.py:1496 | 术语白名单文件 read_text | read_text_exact | 用户自写的白名单文件 |
| factscribe/brief.py:125 | root_file.read_text | to_lf(read_text_exact(...)) | 主文件（\input 顺序） |
| factscribe/brief.py:236 | load_sections 直接用 | 入口 to_lf 归一 | 简报是分析层 |
| factscribe/bundle.py:307/362/472 | read_text | to_lf(read_text_exact(...)) | 闭包 .tex（清单门、图环境、checklist 指向的文件） |
| factscribe/protect.py:576/577 | read_text(errors=replace) | to_lf(read_text_exact(...)) | before/after 两份正文（保护面比对） |
| factscribe/doctor.py:58/70/222 | read_text | read_text_exact＋to_lf | 项目 .tex（诊断读） |
| factscribe/projects.py:427 | cfg_file.read_text | read_text_exact | factscribe.toml（项目声明）；写侧 F4 已改 |
| factscribe/term_suggest.py:63/76/488 | read_text | read_text_exact＋to_lf | 项目源文件与术语表 |
| factscribe/terms.py:299 | path.read_text | read_text_exact | 词表 TSV（术语表；splitlines 对 CRLF 安全） |
| factscribe/textreuse.py:458 | read_text(errors=replace) | to_lf(read_text_exact(...)) | .tex/.md 复用分析 |
| factscribe/texscan.py:619/622 | split("\n") | split_lines(...) | 数字抽取按行切 |
| factscribe/cli.py:1599 | --doc 读用户文档 | to_lf(read_text_exact(...)) | --doc 指向的用户文档 |
| factscribe/tide.py:328/359 | 账本 read_text | read_text_exact | 潮汐账本（append-only，长在用户盘里） |
| factscribe/tide.py:367 | path.open("a") 追写 | newline="" ＋ dominant_newline | 追写不能造出「一半 LF 一半 CRLF」的混合行尾 |
| integrations/factscribe-legal/factscribe_legal/ledger_maint.py:30/37/39/42 | 默认文本模式读写 | newline="" ＋ 按账本自身行尾 | **原地改写 facts/*.toml**（事实账）——Windows 上读写两头都翻译，账本原字节被改掉 |
| integrations/factscribe-legal/factscribe_legal/facts_ledger.py:15/36 | 正则只认 \n | 正则认 \r?\n ＋ newline="" | CRLF 账本原来会被判成「没有事实块」→ 同值检测静默漏检 |
| integrations/factscribe-legal/factscribe_legal/verify.py:89 | 默认文本模式读 .tex | newline="" | 扫 \cite{}（正则与行尾无关） |
| integrations/factscribe-legal/factscribe_legal/cn_verify.py:138 | 默认文本模式读 .tex | newline="" | 取某一行（「第X条」检索与行尾无关） |

## 三、机器产物：保持现状（工具自产自销，格式由工具定）

JSON 报告与信封、审计矩阵、证据锁与流水账、清单 manifest、实验日志、派生卡片 md、
字体缓存、语料/词库 TSV、.git 内部文件、截图/中间物。逐点（读侧或写侧）：

| file:line | 对象 | 依据 |
|---|---|---|
| factscribe/report.py:449/891-893/904/945/1028 | 探针源与报告信封 | _read_text 只服务探针计数/取值，报告由工具定格式 |
| factscribe/report.py:1262/1368-1373/1427/1479/1520/1527/1536 | 证据锁、原子写、流水账、卡片 md | 同上；写入侧只在内存里拼 "\n" |
| factscribe/figures.py:772/919 | 派生卡片 md | _write 写的不是用户手编内容 |
| factscribe/evidence.py:276/326/344 | 证据锁与流水账 | 写侧已钉 newline="\n" |
| factscribe/v3.py:215/229/270 | 签名、非ces 日志 | 机器产物 |
| factscribe/fonts.py:62/113/162 | 字体缓存 | 机器产物 |
| factscribe/pdfgate.py:331、factscribe/refs.py:827/1021 | JSON 与二进制 | 机器产物 |
| factscribe/segment.py:66 | gzip 语料 | 语料库 |
| factscribe/bundle.py:754/766/793 | INVENTORY/MANIFEST | 包内清单（工具定格式） |
| factscribe/cli.py:1529/1544/1894/1990 | matrix.md、preamble.tex、简报 md、术语候选 tsv | 工具生成的报告 |
| factscribe/projects.py:90/101 | 项目登记册 JSON | 工具自产自销 |
| factscribe/polish.py:103、factscribe/audit.py:412/471 | 仓内 PLAYBOOK 与 JSON 记录 | 仓内规则与记录 |
| factscribe/scaffold.py:405/579/587 | 新文件与事实账追加 | 走 write_bytes，**本来就是逐字节** |
| factscribe/tide.py:607 | 派生账本视图 md | 工具生成 |
| scripts/*、experiments/* | 开发脚本与实验产物 | 一次性工具与实验输出；其中 ingest_fr_blobstore.py 等写的是语料目录 |
| integrations/minifactscribe/miniapp/client/app.js | 前端 | 浏览器侧，textarea 的 value 本身归一为 LF |

## 四、miniapp 线（feat/miniapp-host-seam）：口径不同，另立分支

这条线的接口层契约写在 integrations/minifactscribe/tests/eol.test.mjs 的注释里：

* HTML 规范规定 textarea 的 value 归一为 LF——真 Chrome 实测，浏览器拿不到 CRLF；
* 引擎的读路径做通用换行翻译，接口层给的就是 LF；
* **行尾的真相只在磁盘上的原文件里，所以由 Node 代理在保存时按原风格摆回去**。

所以「接口层给 LF」是这条线的**契约**，不是缺陷。把 F4 的 _sections_exact 带进
workbench_dataplayer 后，eol 的真引擎端到端用例红了（断言接口层 CRLF 数＝0），
已按契约改回 load_sections。这条线上真正的漏网是**写侧与内部读改写**：

| file:line | 原来 | 改成 |
|---|---|---|
| factscribe/workbench_dataplayer.py:145 | tmp.write_text(text, encoding="utf-8") | write_text_exact(tmp, text)（newline=""） |
| factscribe/workbench_dataplayer.py:299 | target.write_text(content, ...) | write_text_exact(target, content) |
| factscribe/workbench/write.py:886/910/1146/1216/1360/1386/1424/1450/1498/1528/1568/1663/1705/1832 | read_text | read_text_exact | 块编辑链（社区包 /api/disk/.../edit）：代理把原文件行尾摆回来后送进引擎，引擎这一侧的读必须与之一致，否则错位偏移会把别的行的字节改掉 |
| factscribe/workbench/write.py:1465/1476/1584/1912 | splitlines() ＋ "\n".join | split_keepends ＋ dominant_newline 逐行拼回 | 装配文件调序/删节/建节、factscribe.toml 改表：原来那套会把 CRLF 的文件悄悄改成 LF |
| factscribe/workbench/write.py:1561 | 新建节固定 "\n\n" | 用盘里占多数的行尾 | CRLF 的盘不补出 LF 行 |
| factscribe/workbench/{knowledge,importer,projects,server,venue}.py | 默认文本模式 | read_text_exact / write_text_exact | 知识库文件、导入草稿、项目与版式配置 |

### 4.1 第二轮：共享模块的换行保真补齐（只取 F4，不动 F7 口径）

首轮带进本线的那个 F4 提交里，F4（换行保真）与 F7（citeedit/citeview
统一项目根口径）混在同一批文件里。为了不踩本线自己的 refs/citations
口径，那批改动整体撤掉了——连带把几个**纯换行**的改动也一起撤了。本轮
按「只取 F4、绝不碰 F7 口径」重做，逐点如下：

| file:line | 原来 | 改成 | 为什么算用户内容 |
|---|---|---|---|
| factscribe/citeedit.py:76-83 | 原子写用 open(tmp,"w") | write_text_exact(tmp, text) | bib 是用户手编的参考文献；Windows 上默认文本模式会把已有的 '\r\n' 写成 '\r\r\n' |
| factscribe/citeedit.py:157/213 | target.read_text／path.read_text | read_text_exact | 加条目、删条目前后读原字节，不做通用换行翻译 |
| factscribe/citations.py:68 | path.read_text | read_text_exact | bib 解析读原样 |
| factscribe/citeview.py:53-60 | path.read_text | read_text_exact | 参考文献页读正文 |
| factscribe/reportapi.py:310-317 | open(tmp,"w") | write_text_exact | 报告模板里用户填的数字与注释逐字落盘 |
| factscribe/buildpdf.py:215/222/236/243 | read_text／write_text | read_text_exact／write_text_exact | PDF 临时副本与源 .tex 逐字节对应 |
| factscribe/serve.py:604 | tex.read_text | read_text_exact | 章节标题（PDF 页码定位） |
| factscribe/projects.py:198-270/366-395 | read_text().splitlines() ＋ write_text("\n".join) | split_keepends ＋ dominant_newline ＋ write_text_exact | factscribe.toml 改写：只改那一个键，别的行与行尾都不动 |

另有一条**镜像不同步**的发现：vendored 引擎镜像
（miniapp/miniapp/node/engine/factscribe/）是 build.sh 从仓根 factscribe/
整目录拷过去的直拷本。上一轮撤销 F7 部分时只改了源、没重跑 build.sh，
于是镜像里留着已撤销的 F7 版本——citations／citeedit／citeview／
reportapi／projects／buildpdf／serve 共 7 个文件与源不一致。本轮重跑
miniapp/build.sh，镜像与源逐字节一致（契约自检＋引擎自检通过）。

## 五、测试与读数

### 新增用例

* tests/test_newline_fidelity_sweep.py（14 例，集成分支）：接口层读保住 CRLF；
  CRLF 版与 LF 版同一项目的审计发现逐条相同、退出码相同；factscribe.toml／
  事实账／潮汐账本写回逐字节；读调用点确实以 newline="" 打开；POSIX 上 LF
  读法与默认文本模式逐字符相同；F4 首轮的 15 例一条未改松。
* tests/test_newline_fidelity_miniapp.py（5 例 → 12 例，miniapp 线）：块编辑链 CRLF／
  混合行尾保存后逐字节一致；下发给客户端的块原文 CRLF 原样在；读写调用点
  不翻译换行；dataplayer 存节逐字节一致。**修复前这 5 例有 3 例红**
  （CRLF 被写成 LF），修复后全绿。第二轮又加 7 例（共享模块）：bib 原子写
  保持原有字节、bib 写盘调用点以 newline="" 打开、CRLF 的 bib 照样解析出
  条目、citeview 读正文保留 CRLF、factscribe.toml 改写保留 CRLF 且其它行
  一个字节不动、报告写盘逐字节、PDF 临时副本调用点用 write_text_exact。

### 读数

* 集成分支：Python 3.10 全量 1716 例 OK（skipped=2）；3.11–3.14 全量各 1716 例 OK；
  legal 集成套件 166 例 OK；node 158 例全过；
  金样例基线 tests/golden/audit_findings_baseline.json **逐字节未动**
  （golden_check 26 盘逐字节相同）；
  27 盘逐盘对读（基点 2e6d46c vs 本分支，audit --json 全量 payload＋退出码）
  **判定 0 变化**。
* miniapp 线（共享模块补齐后）：python 3.11 全量 2396 例 OK；3.10 全量
  2396 例 4 条红，与基点 e6cf221 同集（本线未带 3.10 TOML 严格档那条修复），
  非本轮引入；node 176 例全过（含 eol 真引擎端到端 18 例）；
  miniapp/build.sh 契约自检＋引擎自检通过。

## 六、未验证的边界（诚实记着）

**Windows 真机端到端仍未验证。** 手边没有 Windows 机器；本机是 macOS，POSIX 上
默认文本模式的换行翻译是恒等变换，仓库 CI 矩阵（.github/workflows/test.yml）
也只有 ubuntu。所以「Windows 上会变成 CRLF／CRLFCRLF」这一段是**机制链核实**
（CPython 文档语义 ＋ 源码逐点核对），不是本机实跑。

另有一条结构性事实值得记着：仓库**没有 .gitattributes**，Windows 上
Git-for-Windows 默认 core.autocrlf=true 会把 .tex/.bib/facts/*.toml 检出成
CRLF——这正是「用户内容载体在 Windows 上是 CRLF」的来源。

再记两条 miniapp 线上实测到、但**本轮没有动**的：

* **本线既有的项目根缺陷（早于本轮，基点同样复现）**：项目根有两种拼法时
  （macOS 的 /var → /private/var、Windows 的映射盘），citation_add_data 会抛
  ValueError——parse_bib 的 path.relative_to(root) 对不上（基点 e6cf221 与
  本分支同一处、同一报错，非本轮引入）。上游用 F7 的 _rel_under_root 修掉了，
  但那条口径与本线的 refs/citations 契约冲突，本轮不在这条线上动它，
  留给本线属主定夺。
* **bib 追加条目的行尾**：新增条目内部用 "\n"（与上游同口径），所以 CRLF 的
  bib 追加后会多出 LF 行；**原有字节一个都没动**（有用例断言），本轮不改。