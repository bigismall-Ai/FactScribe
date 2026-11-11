# 写作简报实施记录（批 126）

> 规范：`docs/design/SPEC-BRIEF.md`。
> 新增 `factscribe brief` 子命令与模块 `factscribe/brief.py`；
> **未改** `facts` / `terms` / `config` / `audit` / `style` / `polish` 的判据与退出码；
> 零第三方依赖（纯标准库）。

一句话：`brief` 把「写这篇论文草稿要遵守的全部约束」从账里生成成一份
Markdown，交给写作模型当依据；它不判断文字好坏，只把账里的材料与红线摆齐。

## 1. 交付物

| 路径 | 内容 |
|---|---|
| `factscribe/brief.py` | 节清单（按主文件 `\input` 顺序）、事实过滤、术语表、五节渲染、JSON 载荷 |
| `factscribe/cli.py` | 注册 `brief` 子命令（唯一改动的既有文件） |
| `tests/test_brief.py` | 23 例契约测试 |
| `docs/design/SPEC-BRIEF.md` | 五节定义、与 `polish` / `audit` 的分工 |
| `docs/implementation/BRIEF.md` | 本件 |

## 2. 复用与边界

| 要的东西 | 复用实现 | 本批做了什么 |
|---|---|---|
| 项目声明 / 节闭包 | `config.load_config` / `load_sections` | 只挑「节」文件并排序 |
| 事实 | `config.load_facts` | 原样列 `id / claim / value`，不推导、不列 source |
| 术语 | `terms.load_glossary`（项目 `glossary.tsv` 优先，与 `style` 同序） | 列正名、别名、禁用变体 |
| 标题 | `style._headings` | 取文件第一个 section/chapter 标题 |
| 该节事实条数 | `texscan.scan_tex(...).markers` | 按不同 fact id 计数 |
| 节顺序 | 自读主文件 `\input` / `\include`（先用 `texrules` 剥注释） | 仅此一处新解析；`audit/preamble` 不算节 |

节文件的判定顺序：显式 `sections = [...]` → `sections/*.tex` 约定 →
主文件输入里去掉 `audit/` 的条目。这样 V3 里 `sections_glob` 被 `root_tex`
占位时仍能认出真正的节。

## 3. 真实材料读数

命令均在 `paperkit-dev/` 仓根执行：

```bash
python3 -m factscribe brief ../paper-b    > /tmp/brief-b.md
python3 -m factscribe brief ../paper-b-zh > /tmp/brief-bzh.md
```

两篇都退出 `0`、输出 150 行；**各 62 条事实、8 个节**。

### 3.1 节清单与事实条数（paper-b / paper-b-zh 结构相同）

| # | 文件 | 当前标题（en / zh） | 已有事实条数 |
|---|---|---|---|
| 1 | `sections/00_abstract.tex` | （无标题） / （无标题） | 6 |
| 2 | `sections/01_intro.tex` | Introduction / 引言 | 12 |
| 3 | `sections/02_related.tex` | Related Work / 相关工作 | 0 |
| 4 | `sections/03_design.tex` | Contract-first design / 契约先于评判的设计 | 4 |
| 5 | `sections/04_style_case.tex` | The Style Gate on Polished Prose / 文风闸面对定稿 | 58 |
| 6 | `sections/05_blind.tex` | Blind Tests / 盲测 | 12 |
| 7 | `sections/06_limits.tex` | Limitations / 局限 | 4 |
| 8 | `sections/07_conclusion.tex` | Conclusion / 结论 | 7 |

顺序与 `main.tex` 的 `\input` 一致；`00_abstract` 没有 `\section`，按规范写
`（无标题）`。

### 3.2 「可用主张与数字」前 5 条（人工可读性抽查）

```text
| `B1` | 第一套盲测首跑命中 | 0/12（首跑，#1） |
| `B2` | 第七套盲测首跑命中（首次过线） | 11/12（首跑，#7） |
| `B3` | 三套真盲合计命中与比例 | 30/36（83%） |
| `B4` | valid 项目误红合计 | 0/36（valid 误红） |
| `B5` | 第八套首跑命中 | 10/12（#8 首跑） |
```

中文版前 5 条逐字相同（两篇的 fact 账共用同一批 id/claim/value）。

### 3.3 确定性与路径卫生

```text
$ python3 -m factscribe brief ../paper-b > /tmp/brief-b.md
$ python3 -m factscribe brief ../paper-b > /tmp/brief-b2.md
$ diff /tmp/brief-b.md /tmp/brief-b2.md     # 无输出
$ grep -c "EVIL\|/Users/" /tmp/brief-b.md /tmp/brief-bzh.md
0
0
```

无时间戳、无绝对路径；source 路径一次都没出现。

### 3.4 节过滤实测

```text
$ python3 -m factscribe brief ../paper-b --section 04
> 本节简报的事实无法按 id 前缀 `04` 过滤（账里的 id 不以节前缀命名），
> 故「可用主张与数字」全列 62 条。
```

节清单只剩 `sections/04_style_case.tex`；事实全列并把原因写在文首（账里的
id 是 `B1` / `S3a` 这类，不以节号开头）。

## 4. 测试读数

```text
$ env PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_brief.py'
Ran 23 tests ... OK
```

覆盖：五节标题逐字与顺序、全部 fact id/claim/value、`\fact{` 提示、术语正名
与禁用变体、`\input` 顺序（夹具故意与文件名排序相反）、每节事实计数（重复
绑定只算一条）、source 不泄露、`--section` 的三种情形（过滤节、前缀不命中
全列并说明、前缀命中只列命中项）、双跑逐字节一致、`--out` 与 stdout 一致、
`--json` 结构、无 facts / 空 `--section` / 未知 `--section` / 缺项目四种
fail-closed。

## 5. 已知限制

- 「该节已有事实条数」统计的是**绑定次数去重后的 id 数**，不是「账上属于该节
  的条数」——账里没有「事实归属哪一节」的字段，本批不新造归属关系。
- 事实表按账本装载顺序（`facts/*.toml` 文件名排序 → 文件内顺序），不按 id
  重排；写作时可直接顺读，但不会得到字母序。
- 两篇真材料共用同一份英文 `name`（`paperkit.toml` 只写了英文名），所以
  中文简报的项目名仍是英文；这是账里的事实，简报不翻译。
- 词表按仓内 `paper.tsv`（33 条）；项目若另放 `glossary.tsv` 会自动优先，
  与 `style` 一致。
