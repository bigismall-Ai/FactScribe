# FactScribe

**中文** · [English](README.en.md)

FactScribe 是一道机械闸门，专门拦 AI 写论文时最危险的两类编造：数字没有出处，引用指向不存在的文献。它不写正文，也不改正文。它只回答一件事：这句话里的每个数，能不能回到一份签过字、算过哈希的原始材料。

不依赖模型 SDK，纯标准库，Python ≥ 3.10。

## 边界声明

绿只说明三件事：账有据、据未改、文有绑。它不说明论文为真，也不替审稿人判断结论是否成立。完整边界见 `docs/design/SPEC-V1.md` §2.3。

一条读数能支撑什么说法、不能支撑什么说法，见 [`docs/WHAT-IT-PROVES.md`](docs/WHAT-IT-PROVES.md)。

## 装与跑

```bash
python3 -m pip install -e .                    # 可选；不装也能用 PYTHONPATH 跑
python3 -m factscribe audit <项目> --build     # 先编 PDF 再审计
python3 -m factscribe style --doc README.md    # 单篇文风体检
```

## 十四个命令

`factscribe` 一共十四个子命令。事实账是一份只追加的清单，每行记一个数字、它的来源文件与来源文件的哈希。

| 命令 | 干什么 |
|---|---|
| `check` | 查事实账本身：id 唯一、sha256 现算、人签清单、表达式算术、同值冲突 |
| `audit` | 核心校验：内联绑定、数字回账、引用落稳定标识、覆盖报告 |
| `matrix` | 生成追溯矩阵 `audit/matrix.md` |
| `build` | 执行 `factscribe.toml` 里的 `project.build`；中文缺字体时自动改用 Fandol |
| `preamble` | 生成 `audit/preamble.tex` 里的 `\fact` 与 `\pkignore` 宏 |
| `verify-pdf` | PDF 回检：文本层、栅格页、双向多重集、stamp 验签 |
| `style` | 文风闸：只报公式化写作特征，黄牌，不阻断 |
| `protect` | 改写保护面：比对改写前后六类不许变的内容 |
| `tide` | 潮汐式改动账：涨、落、波及面、闭合，全成或全退 |
| `prescribe` | 处方层：只给可执行改法，不进判据、不产生分数 |
| `terms` | 术语候选抽取与人工入表：suggest 提候选，add 只写你勾的 |
| `fonts` | Fandol 中文字体按需下载与本地缓存：`--status` 看状态，`--fetch` 下载 |
| `review` | 改写验收：保护面 + 复检 + 闭合一次判完，给通过、需复核或拒绝 |
| `polish` | 给 LLM 的润色入口：`--print` 出操作手册，`--plan` 出工作单 |
| `fonts` | 中文字体：`--fetch` 下载 Fandol 到本地缓存，`--status` 看是否齐全 |

全部支持 `--json`。`check` 与 `audit` 支持 `--strict`，黄牌也当红牌，供 CI 使用。

## 三道闸

三道闸分别管数字与引用、改写保护、文风与术语。它们可以单独跑，也可以串成一条发布前检查。

第一道是数字与引用。正文写 `\fact{A1}`，就声明这一行的数字属于事实 `A1`；审计会反查，该行每个数字都必须落在 `A1` 的值域里。所有 `\cite` 家族的 key 必须出现在 `refs.bib` 里，bib 条目还要有 `arxiv` 或 `doi`（`@misc` 可用 `url`）。数字归一化后 `1,234` 等于 `1234`，`0.90` 等于 `0.9`，`53k` 等于 `53000`。

第二道是改写保护。保护面指改写前后不许变的六类内容：事实标记、数字、引用、公式、表格、交叉引用。只改标点与断句应当全绿；动了任何一个数字、公式或引用即红，并给出 `文件:行` 与改成了什么。

```bash
python3 -m factscribe protect --before 旧稿/ --after 新稿/
```

第三道是文风与术语。文风闸只报可机械判定的公式化写法，共 31 条判据，其中 4 条是改写复检：`HEADING_ECHO` 查首句是否复述标题，`HEADING_RELATION_CHANGED` 查标题里的对立关系是否被换掉，`HEADING_SUBJECT_LOST` 查旧标题的主语是否丢失，`TERM_VARIANT` 查同一个术语是否在一篇里换着写法。术语层分两册：论文术语 33 条来自 `paper-zh/GLOSSARY.md`，工作区流程词 153 条来自词册。

## 改动账

`tide` 把一次改写当成一笔事务。四个条件全部成立才落账。账只认哈希。涨是改了什么，由两个目录的文件哈希差算出。落是改后的真实文件状态，重新读盘再算哈希，不许人填。波及面由 `\input` 与 `\include` 的反向引用闭包自动计算。闭合要求涨、落、波及面三者对得上。缺一项就全退。不写账本，不写派生视图，退出码 1。

这里没有自报清单。人只能看结果，不能填清单。工具同样不相信任何手写的改动说明，也不接受口头的补充。

## 处方层

`prescribe` 回答的是另一件事：某条判据被触发后，下一步到底怎么改。先看处方。它带 9 条处方，只给已经验证过的改法，并把已知坏改法写成禁做与反例。处方之间冲突时按固定优先序裁决，被压制的处方会明写让位。

这一层不进判据，也不产生分数。它不改 `audit`、`style`、`protect` 的任何判定与退出码。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 绿，无红无黄 |
| 1 | 红，有违例 |
| 2 | 配置或用法错，工具没跑起来 |
| 3 | 黄，跑完了但有未核验或未绑定的项，不判死但不算绿 |
| 4 | 工具内部错误 |

缺 `factscribe.toml`、事实账为空、正文为空、`refs.bib` 缺失，一律退出码 2 并说清原因，不静默放行。

## 已知缺口

剩下的问题如实写在 [`docs/release/KNOWN-GAPS.md`](docs/release/KNOWN-GAPS.md) 里。另有三条结构性边界不打算修：信任根是人签，若 agent 同时伪造账与据，工具无法发现；出题人与实现方同机，盲测只能算弱盲测；不做 OCR，图片承载的定量一律判红。

三条边界都指向同一个定位：工具保证账、据、文三者自洽，且据未被改，不保证论文结论为真。

## 复现与贡献

```bash
python3 -m unittest discover -s tests     # 908 例，全离线
./scripts/preflight-ci.sh                 # 本地等价 CI：干净克隆 + 3.10/3.11/3.12
```

`examples/minimal/` 是验收样例：三条事实、两节正文，故意混入一个编造数字与一个假引用。`audit` 必须只报这两处红。

规范在 `docs/design/`，实现记录在 `docs/implementation/`，历史在 `CHANGELOG.md`。提交前请读 [`CONTRIBUTING.md`](CONTRIBUTING.md)，PR 必须带测试。
