# SEGMENT｜中文分词底座与 `ZH_LIGHT_VERB_NOUN` 实施读数（批 104）

日期：2026-11-10｜规范：`docs/design/SPEC-SEGMENT.md`｜实施：D 席

## 0. 一句话

分词底座落地：34.9 万条带词频、词性的词表，纯标准库，`../paper-zh`
全文（12,228 个汉字）热跑 **24.2 ms**。`ZH_LIGHT_VERB_NOUN` 在四份验收
语料上 **0 触发**（0.00 条/万字）；另取工作区 3 条真实原句抽检，**3 真
阳性、0 假阳性**。

## 1. 词表

| 项 | 值 |
|---|---|
| 文件 | `factscribe/terms/seg.tsv.gz` |
| 行数 | 349,046 |
| 去重词条 | 349,045（源表只有 `B超` 重复一行） |
| 词频总和 | 60,101,967 |
| gzip 大小 | 1,904,875 字节（约 1.9 MB） |
| gz sha256 | `35e47c1fb9baf2a351a179afb8c22878caa0305e7294c855f05af524f46d51a3` |
| 源文件 | `sia-harness/nomenclator/refsrc/jieba-dict.txt`，sha256 `7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8` |
| 许可 | MIT／结巴分词（jieba）自带词典 |

三列 `词 词频 词性` 原样保留；生成命令与「为什么不用 termbank 179 万
词面」写在 `factscribe/terms/SOURCES.md`。gzip 固定 `mtime=0`、不写文件名，
同源文件字节可复现。

## 2. 算法

正向扫描＋**最大概率切分**（候选集与正向最大匹配相同，长度上限 10 字）：

1. 只对中文段查词表；英文、数字、标点、空白连续成块原样保留，词性空。
2. 中文段建 DAG：每个位置枚举 1…10 字的词表候选，边权
   `log(词频 / 总词频)`；未登录字只有单字边，权固定 `log(1 / 总词频)`。
3. 从右向左取总权最高的路径；同分取较长，再同长取词频高，最后按词面
   定序。路径即切分。

为什么不逐位按词频贪心：词频最高的是单字（`南/京/市` 都比 `南京市`
高），`南京市长江大桥` 会被切成单字串。为什么不逐位取最长：
`研究生命起源` 会被切成 `研究生/命/起源`。整段对数词频和同时避开两种
退化。

### 2.1 歧义用例

| 输入 | 输出 | 说明 |
|---|---|---|
| `研究生命起源` | `研究 / 生命 / 起源` | 不是 `研究生 / 命 / 起源` |
| `南京市长江大桥` | `南京市 / 长江大桥` | 不是 `南京 / 市长 / 江 / 大桥` |
| `龘靐龖`（未登录） | `龘 / 靐 / 龖` | 单字切，词性空 |
| `我在用Python3.10做实验。` | `我 / 在 / 用 / Python3.10 / 做 / 实验 / 。` | 非中文原样保留 |

### 2.2 接口

```python
segment(text) -> list[(token, start, end, pos)]
load(path=None) -> dict[str, tuple[int, str]]
```

- `text[start:end] == token`；
- `pos` 取词表第三列，未登录字/非中文块为 `""`；
- `load()` 惰性加载、同一路径进程内缓存；列数不对、词频非正整数按
  `SegmentError` 报错，不静默跳过。

### 2.3 词性口径（对规范的一处工程修正）

判据里的「名词侧」＝词性 `n` 开头，**外加 `vn`（动名词）**。结巴把
`分析 / 研究 / 评估 / 调整 / 优化` 标成 `vn`；只认 `n` 会让验收例句
`进行了分析` 永远报不出来。纯动词 `v`（`说明 / 讨论 / 支持`）不报。
这条修正写在配置注释、`SPEC-SEGMENT.md` §2.3 和测试
`test_vn_also_counts_as_noun_side` 里。

## 3. 判据 `ZH_LIGHT_VERB_NOUN`（黄）

形态：`进行|作出|加以|给予|予以` ＋ 可选体标记（`了/着/过`） ＋ 可选
`的` ＋ 名词侧 token。按条报，阈值 `>= 1`，**不设密度闸**；只出黄牌，
`style` 退出码仍为 3。

- 中间夹数量词/形容词/副词不报（`进行了三次测试`、`进行了不恰当的修正`）；
- 名词后紧跟另一个名词/动词时，视为修饰语不报（`进行了专门优化` 的
  `专门` 虽被标成 `n`，中心词是 `优化`）；
- 白名单：`进行中`、`进行时`、`作出决定`，写在
  `style-rules.toml [zh_light_verb_noun].exempt_phrases`；
- 报告必给「动作其实是什么」：`进行了分析` → `分析了`，
  `进行了调整` → `调整了`。

### 3.1 准入单（CONTRIBUTING.md 第 2 节，逐项）

#### 1）四份语料触发量（每万字）

| 语料 | 计数单元（词/字） | `ZH_LIGHT_VERB_NOUN` 条数 | 每万字 | 预算上限（≤2/万字） |
|---|---:|---:|---:|---:|
| `../paper` | 6,961 | 0 | 0.00 | 1 |
| `../paper-zh` | 10,969 | 0 | 0.00 | 2 |
| `../paper-b` | 5,983 | 0 | 0.00 | 1 |
| `../paper-b-zh` | 9,592 | 0 | 0.00 | 1 |

复算命令（仓根 `paperkit-dev/`）：

```bash
python3 -m factscribe style ../paper --json
python3 -m factscribe style ../paper-zh --json
python3 -m factscribe style ../paper-b --json
python3 -m factscribe style ../paper-b-zh --json
```

#### 2）逐条抄出触发的句子，标真/假阳性

四份验收语料：**0 条命中，逐条表为空**（不是只报总数，是确实没有句子
可抄）。四份语料本身都不使用「进行/作出/加以/给予/予以＋名词」这套
写法；`paper`、`paper-b` 是英文。

为了不让「0 命中」掩盖精度，另取工作区文档里的**真实原句**做抽检
（不是四份验收语料，不计入上表）：

| # | 原句 | 出处 | 判定 |
|---|---|---|---|
| 1 | 对方案进行了调整。 | `experiments/rewrite-survey/repos/human-writing/human-writing/references/forum-prose.md:160`（原文引例） | 真阳性：`调整` 是 `vn`，动作是「调整了」 |
| 2 | 文件中的函数插件按照功能进行了分类。 | `experiments/rewrite-survey/repos/gpt_academic/docs/self_analysis.md:103` | 真阳性：`分类` 是 `n`，动作是「分类了」 |
| 3 | 针对 Word 文档的特点进行了优化。 | `experiments/rewrite-survey/repos/gpt_academic/docs/features/academic/word_summary.md:5` | 真阳性：`优化` 是 `vn`，动作是「优化了」 |

同一抽检里的「不该报」原句（均 0 触发）：

| # | 原句 | 出处 | 为什么不报 |
|---|---|---|---|
| 1 | 如果您在上传图片后进行了多轮其他对话，可能需要重新上传图片才能继续针对该图片提问。 | `.../docs/features/basic_operations.md:150` | `多轮` 是数量词 `m`，夹在中间 |
| 2 | 对专业术语进行了不恰当的“修正”。 | `.../docs/features/academic/latex_proofread.md:156` | 中间有形容词「不恰当的」 |
| 3 | 针对 Markdown 文档的特性进行了专门优化。 | `.../docs/features/programming/markdown_translate.md:9` | `专门` 是修饰语，中心词 `优化` 在后面 |

#### 3）假阳性超半即回退

四份验收语料：0 命中，0 假阳性。真实原句抽检：3 条命中，3 条真阳性，
0 条假阳性（0%）。**未触发回退条件。**

#### 4）正反例各三条

测试 `tests/test_syntax.py::TestZhLightVerbNoun`：

- 正例三条：`对方案进行了调整`、`研究团队对数据进行了分析`、
  `文件中的函数插件按照功能进行了分类`（另有 `公司对产品进行了优化`）；
- 反例三条：`他加以说明后离开`（`说明` 是 `v`）、`我们进行了三次测试`
  （数量词夹在中间）、`这个问题讨论了三次，讨论仍在进行`（句末无名词）；
- 白名单三条：`会议进行时，请不要打扰`、`项目正在进行中`、
  `董事会作出决定`；另有修饰语反例 `进行了专门优化`。

#### 5）哪份语料应 0 触发

英文语料 `../paper`、`../paper-b` 应 **0 触发**（没有中文轻动词）。
写成反向锁测试：

- `test_english_corpus_never_triggers`：英文句 `The team performed an
  analysis...` 的指标恒为 0；
- `test_sentence_end_without_noun_negative`：`讨论仍在进行。` 0 触发。

实测四份语料均为 0；其中两份英文是设计上的硬 0。

#### 6）单位写死

单位：**条**。每出现一处「轻动词＋（体标记）＋（的）＋名词侧」算一条，
按条报，不折算成每千字/每千词/每句；阈值 `zh_light_verb_noun = 1`，
没有密度闸。

## 4. 耗时

对 `../paper-zh` 全部 20 个 `.tex` 文件拼接后跑一次 `segment()`：

| 项 | 读数 |
|---|---:|
| 原始字符 | 25,937 |
| 汉字字符 | 12,228 |
| 输出 token | 9,358 |
| 冷跑（含 gzip 加载） | 197.6 ms |
| 热跑（同进程第二次） | 24.2 ms |

测量环境：本机 Python 3.14.4，单线程；文件按路径排序后拼接，不含读盘
时间以外的预处理。冷跑是一次性成本，`style` 一次进程只付一次。

## 5. 门禁输出

### 5.1 单元测试

```text
$ env PYTHONPATH=src python3 -m unittest discover -s tests
Ran 708 tests in 32.956s

OK
```

新增 22 例：`tests/test_segment.py` 10 例，`tests/test_syntax.py`
`TestZhLightVerbNoun` 12 例；`tests/test_docmode.py` 的指标快照同步加
`zh_light_verb_noun` 键。

### 5.2 preflight

工作区直跑：

```text
$ ./scripts/preflight-ci.sh --fast
步骤 1/4：外部依赖  ✓ pdftotext  ✓ pdfinfo
步骤 2/4：干净克隆（--fast：跳过，直接用工作区）
步骤 3/4：Python 3.10：Ran 708 tests
           Python 3.11：Ran 708 tests
           Python 3.12：Ran 708 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

提交后干净克隆（只含已提交文件）：

```text
$ ./scripts/preflight-ci.sh
步骤 1/4：外部依赖  ✓ pdftotext  ✓ pdfinfo
步骤 2/4：干净克隆（只含已提交文件）
步骤 3/4：Python 3.10：Ran 708 tests
           Python 3.11：Ran 708 tests
           Python 3.12：Ran 708 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

### 5.3 四份语料读数

| 语料 | 文件 | 词/字 | 句 | 段 | 退出码 | `ZH_LIGHT_VERB_NOUN` |
|---|---:|---:|---:|---:|---:|---:|
| `../paper` | 18 | 6,961 | 397 | 96 | 3 | 0 |
| `../paper-zh` | 18 | 10,969 | 426 | 96 | 3 | 0 |
| `../paper-b` | 10 | 5,983 | 358 | 78 | 3 | 0 |
| `../paper-b-zh` | 10 | 9,592 | 372 | 78 | 3 | 0 |

退出码 3 来自各篇既有的其他黄牌判据，与本批无关。

## 6. 已知边界

- 词性错标会直接变成判据误判：`专门` 被标成 `n` 就是例子，现用
  「名词后紧跟实词即视为修饰语」压住；更复杂的「进行＋长定语＋名词」
  一律不报（精度优先，漏报可接受）。
- `vn` 被当作名词侧是工程修正；如果换词表把 `vn` 改回纯 `v`，正例会
  集体消失，测试会红。
- 分词器不处理繁简转换、不做新词发现；未登录词只能单字切。
