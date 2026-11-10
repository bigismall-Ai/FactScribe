# EXPLAINER｜解释性套语判据实施记录（批 99）

规范：`docs/design/SPEC-EXPLAINER.md`。本件记录判据、阈值来源、四个对照
读数、测试数与门禁输出。

## 1. 判据

| 指标 | 错误码 | 判定 | 默认阈值 |
|---|---|---|---|
| `explainer_density` | `EXPLAINER_DENSITY` | 句首解释性套语密度，`>` 触发 | 6.0 / 千词（字） |
| `justify_chain` | `JUSTIFY_CHAIN` | 同段 ≥2 句、或连续 ≥2 段以解释句收尾 | 结构条件，≥1 处即报 |

两条都是黄牌：只进 `findings`，退出码仍是 0（无触发）/3（黄牌），
不改 `audit`、`protect` 的判据。

实现位置：

- `factscribe/style.py`：`_explainer_opener` / `_strip_opener` 两个纯函数；
  `analyze()` 里「1b. 解释性套语」一段；指标、触发、人读报告三处接线；
- `style-rules.toml`：`[explainers]` 词表 + `[thresholds]` 三个阈值；
- `factscribe/patterns/drop-the-proof/RULE.md`：第七条处方；
- `factscribe/patterns/priority.toml`：`drop-the-proof = "style"`。

遮罩沿用既有路径：Markdown 围栏、行内代码、列表行、引文行与 LaTeX
verbatim/公式/图表在 `prose` 里已经是等长空白；列表另存 `list_prose`，
只给超长句用，不进本判据。引文面的两处补丁是本批加的：`mdscan.py`
补 Markdown 引文行（`>`）整行遮罩，`style.py` 的 `_SKIP_ENV_RE` 补
LaTeX `quote`/`quotation`/`verse` 环境。原实现只遮代码、表格与列表；
补上之后，引文里的套语对所有句级规则都不再计入作者口径。

## 2. 阈值来源

- 密度阈值 **6.0** 与既有 `empty_adjective = 6.0` 同量级，低于
  `connective_density = 8.0`：解释性套语比顺序连接词更刺眼，允许的密度
  应更低。
- 实测留出的判别余量：旧版样本 17.44，当前版本 0.00，两篇论文
  0.57（paper）与 0.09（paper-zh）。6.0 落在旧版与论文之间，距论文
  约 10 倍、距旧版约 2.9 倍。
- 链阈值 **2 句 / 2 段**是规范写死的结构条件，不是经验数：单次解释是
  正常行文，连续两次才是反射。两者都进了 `[thresholds]`，可调；测试
  验证了「调到 3 句后同段两句不再报」。

## 3. 词表与实现增补

规范给了中文 13 词、英文 8 词的初版清单，并允许实现时增删。实测后：

- 中文补 **`它证明`、`它不证明`**：阳性样本（f7075f4）的答辩腔不是靠
  「也就是说」，而是靠「它证明的是……。它不证明……。」这种举证式自述。
  两词在 `paper/` 与 `paper-zh/` 的命中均为 0。
- 中文补 **`可见`**：`由此可见` 的短形，论文里出现 1 次，密度远低于阈值，
  未产生 finding。
- 英文清单按规范原样保留，包括 `That is`。它在 `paper/` 有 4 次句首命中
  （见 §4.3），都是「That is the difference…」这类指示代词主语，不是
  解释套语；因密度 0.57 远低于 6.0，未触发、未产生 finding。阈值承担了
  精度保护，词表不为此收窄。

## 4. 四个对照的读数

### 4.1 阳性：旧版 `docs/WHAT-IT-PROVES.md`（f7075f4）

```
git show f7075f4:docs/WHAT-IT-PROVES.md > /tmp/old-proves.md
env PYTHONPATH=src python3 -m factscribe style --doc /tmp/old-proves.md
```

- 退出码：**3**（黄牌）
- `EXPLAINER_DENSITY`：**3 条**，密度 **17.44** / 千字（172 字）
  - 第 7 行「它证明的是『账、据、文三者自洽，且据未被改』。」
  - 第 8 行「它不证明『论文为真』。」
  - 第 46 行「这正是文献里说的『高稳定与强位置偏好并存』。」
- `JUSTIFY_CHAIN`：**1 条**（第 8 行；同段两句以举证套语开头）

结论：旧版的「每句都跟一个证明」被两条规则同时抓到。

### 4.2 阴性：当前 `docs/WHAT-IT-PROVES.md`

```
env PYTHONPATH=src python3 -m factscribe style --doc docs/WHAT-IT-PROVES.md
```

- 退出码：**0**
- `EXPLAINER_DENSITY`：**0 条**，密度 **0.00**（293 字）
- `JUSTIFY_CHAIN`：**0 条**

结论：当前对话体版本 0 条，规则没有回头误伤改好的稿子。

### 4.3 误报控制：`style ../paper`

```
env PYTHONPATH=src python3 -m factscribe style ../paper --json
```

- 全文 6,961 词、96 段；`explainer_density = 0.57`，`justify_chain = 0`
- **本条规则新增 findings：0 条**（改前 17 条 `RHYTHM_PLATEAU`，改后仍 17 条）
- 原始句首命中 4 处（均未达阈值，未出 finding）：
  1. `sections/02_related.tex:26` "That is the difference we press: …"
  2. `sections/05_eval.tex:44` "That is schema conformance, …"
  3. `sections/06_ablation.tex:25` "That is why we treat the card …"
  4. `sections/07_threats.tex:14` "That is a designed way to fail."
- 人工判断：① ② ④ 是指示代词作主语的事实陈述，**不是解释套语**，
  密度护栏已挡住；③ 是「That is why」解释句，若单独成段收尾会算链，
  但它所在段落不是连续解释收尾，故不报。**四条都不应改正文**。

### 4.4 误报控制：`style ../paper-zh`

```
env PYTHONPATH=src python3 -m factscribe style ../paper-zh --json
```

- 全文 10,969 字、96 段；`explainer_density = 0.09`，`justify_chain = 0`
- **本条规则新增 findings：0 条**（改前 14 条＝12 `RHYTHM_PLATEAU` +
  2 `COLLOQUIAL_TRIAD`；改后仍是这 14 条）
- 原始句首命中 1 处（未达阈值）：
  1. `sections/02_related.tex:26`「这正是我们要强调的差别：合规是接口属性，
     不是指令。」
- 人工判断：句首「这正是」确属解释性套语，但该段只有一次、且句末不是
  解释句，不构成反射链；密度 0.09 远低于 6.0。**不报是对的**，正文不必改。

两个误报对照的新增条数都是 **0 ≤ 5**。

## 5. 测试

新增 `tests/test_explainer.py`，**21 例**：

- `EXPLAINER_DENSITY`：中文正例 / 英文正例 / 纯事实负例 / 阈值调到 1000
  后不报 / 句中短语不计 / 代码块与列表不报 / 引文不报 / 旧版开场句复现 /
  LaTeX `quote` 环境不报（9 例）；
- `JUSTIFY_CHAIN`：同段两句 / 同段单句负例 / 连续两段收尾 / 不相邻负例 /
  同段阈值调到 3 句后不报 / 旧版开场句成链 / 代码块与列表不报 / 引文不报 /
  当前 `docs/WHAT-IT-PROVES.md` 为 0 条（9 例）；
- 处方：两条码都映射到 `drop-the-proof` / CLI `--for` 可查 /
  反例与验收命令在文（3 例）。

为容纳新指标与引文遮罩，同步改了三处既有断言：

- `tests/test_docmode.py`：`EXPECTED_METRICS` 增加两个键（`explainer_density`、
  `justify_chain`），样例读数不变；
- `tests/test_prescription.py`：处方数 6 → 7，`ALL_NAMES` 与可查错误码清单
  加入新条目；
- `factscribe/mdscan.py`、`factscribe/style.py`：补引文遮罩（原有代码/
  表格/列表/公式遮罩不变）。

测试总数：**597 → 618**（两份 README 的读数已同步）。

## 6. 门禁输出

```
$ env PYTHONPATH=src python3 -m unittest discover -s tests
Ran 618 tests in 33.1s
OK

$ ./scripts/preflight-ci.sh --fast
✓ Python 3.10：Ran 618 tests
✓ Python 3.11：Ran 618 tests
✓ Python 3.12：Ran 618 tests
✓ examples/minimal audit exit=1（红，符合预期）
本地等价 CI 全绿——可以推。
```

另按任务要求跑了未加 `--fast` 的干净克隆版。提交后克隆 `HEAD 97246e2`，
Python 3.10/3.11/3.12 各 `Ran 618 tests`，验收步 `audit exit=1`，全绿。
（提交前也跑过一次：当时干净克隆 HEAD 126d4e9，不含本批未提交改动，
所以是 597 例；两次结论一致。）

## 7. 交付清单

- `docs/design/SPEC-EXPLAINER.md`（新）
- `tests/test_explainer.py`（新）
- `factscribe/style.py`、`style-rules.toml`、`factscribe/mdscan.py`（引文遮罩）
- `factscribe/patterns/drop-the-proof/RULE.md`（新）
- `factscribe/patterns/priority.toml`
- `docs/design/SPEC-PRESCRIPTION.md`（六条 → 七条，补 §5.7）
- `tests/test_docmode.py`、`tests/test_prescription.py`
- `README.md`、`README.en.md`（判据数 18 → 20，测试数 597 → 618）
- 本件
