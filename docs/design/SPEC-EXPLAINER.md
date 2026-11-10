# SPEC-EXPLAINER｜解释性套语与反射式解释

状态：批 99 定稿。两条判据全黄牌，只提示、不阻断，退出码不变
（0＝无触发，3＝黄牌）。

## 0. 要抓的毛病

用户原话：「每句话都要跟一个证明」。表现是断言之后立刻补一句解释，段落
结尾总要收个尾，读起来像答辩。

现有判据里，`CONNECTIVE_DENSITY` 只查 `首先/其次/此外` 这类顺序连接词，
`PARAGRAPH_TEMPLATE` 只查段末的 `因此/综上`。两者都管不到「这说明…」
「也就是说…」「这正是…」这类**解释性套语**——句子本身没有连接两个论点，
只是在替上一句补理由。

## 1. `EXPLAINER_DENSITY`

句首出现解释性套语，密度超过阈值即报。

- 判定单位：句。只看句首（允许前置引号、括号、Markdown 强调符）。
- 密度算法与 `CONNECTIVE_DENSITY` 一致：
  `命中句数 × 1000 / 正文词（字）数`。
- 阈值：`[thresholds].explainer_density`，默认 `6.0`；`>` 触发。

### 1.1 默认词表（`[explainers]`，可在 `style-rules.toml` 覆盖）

中文初版：

```
这说明 这意味着 也就是说 换句话说 换言之 说白了 简单说 原因在于
这是因为 之所以 由此可见 正因如此 这就是为什么 这正是 可见
```

英文初版：

```
This means  That is  In other words  This is because  The reason is
Which is why  This shows that  It follows that
```

**实现时增补（有实读支撑）**：中文词表补入 `它证明`、`它不证明`。
起因是阳性对照：旧版 `docs/WHAT-IT-PROVES.md`（f7075f4）的答辩腔不是
靠「也就是说」，而是靠「它证明的是…。它不证明…。」这种**举证式自述**
成句。两词在 `paper/` 与 `paper-zh/` 的实测命中为 0（见
`docs/implementation/EXPLAINER.md`），不会引入论文侧误报。

词表只收「替上一句补解释／补举证」的固定说法，不收普通因果连词
（因为、由于）——那属于正常论证，不属答辩腔。

## 2. `JUSTIFY_CHAIN`

反射式解释，不是单次使用。满足任一条件即报：

1. **连续 ≥2 个段落**的末句都以解释性套语开头；
2. **同一段内有 ≥2 句**以解释性套语开头。

阈值（`[thresholds]`，可配）：

- `justify_chain_min_sentences = 2`（同段句数）
- `justify_chain_min_paragraphs = 2`（连续段数）

判定单位是「处」：同一段的多句解释报一处；一段连续的解释收尾报一处。

## 3. 明确不判

- 引文（`>` 块、`quote` 环境）里的套语不判；
- 围栏代码块、`verbatim`/`lstlisting`/`minted` 里的套语不判；
- 列表项（Markdown `-`/`*`/`+`/`1.` 及其续行）里的套语不判；
- 注释、公式、图表、文献表沿用现有遮罩，不参与统计。

做法与既有判据一致：这些区间在 `prose` 里已被等长遮罩成空白，句级扫描
天然看不到它们；列表另存 `list_prose`，只给超长句用，不进本判据。

## 4. 指标与错误码

| 指标 | 错误码 | 方向 | 默认阈值 |
|---|---|---|---|
| `explainer_density` | `EXPLAINER_DENSITY` | `>` | 6.0 / 千词（字） |
| `justify_chain` | `JUSTIFY_CHAIN` | `>=` | 1 处（结构条件 ≥2 句 / ≥2 段） |

两条都是黄牌：只进 `findings`，不改 `audit`/`protect` 判据，不阻断构建。

## 5. 处方

第七条处方 `drop-the-proof` 治这两条判据，六段结构见
`factscribe/patterns/drop-the-proof/RULE.md`，并在
`docs/design/SPEC-PRESCRIPTION.md` §5.7 登记。

## 6. 验收

- `tests/test_explainer.py` ≥12 例：两条规则正负例、列表/代码块不报、
  阈值可配、处方可查；
- 阳性：`git show f7075f4:docs/WHAT-IT-PROVES.md` 至少报 1 条；
- 阴性：当前 `docs/WHAT-IT-PROVES.md` 0 条；
- 误报控制：`style ../paper`、`style ../paper-zh` 各新增 ≤5 条。

```
env PYTHONPATH=src python3 -m unittest discover -s tests
```
