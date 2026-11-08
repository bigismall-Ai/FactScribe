# FactScribe

**中文** · [English](README.en.md)

FactScribe 是一道闸门，用来拦 AI 写论文时最危险的两类编造：数字没有出处，引用指向不存在的文献。
它不生成正文，也不改正文；它只回答一件事：**这句话里的每个数，能不能回到一份签过字、算过哈希的原始材料。**

不依赖任何模型 SDK，纯标准库，Python ≥ 3.10。

> 绿只说明「账有据、据未改、文有绑」，不说明论文为真。边界见 `docs/design/SPEC-V1.md` §2.3。

## 装与跑

```bash
python3 -m pip install -e .            # 可选；不装也能用 PYTHONPATH 跑
python3 -m factscribe audit  <项目>    # 核心校验
python3 -m factscribe style  <项目>    # 文风体检
```

## 六个命令

| 命令 | 干什么 |
|---|---|
| `check` | 查事实账本身：id 唯一、sha256 现算、人签清单、表达式算术、同值冲突 |
| `audit` | 核心：内联绑定、数字回账、引用落稳定标识、覆盖报告 |
| `protect` | 改写保护面：改写前后比对六类不许变的内容 |
| `style` | 文风体检：只报公式化写法，黄牌，不阻断 |
| `verify-pdf` | PDF 回检：文本层、栅格页、双向多重集、stamp 验签 |
| `matrix` | 生成追溯矩阵 `audit/matrix.md` |

全部支持 `--json`。`check` 与 `audit` 支持 `--strict`，黄牌也当红牌，供 CI 使用。

退出码约定：

| 码 | 含义 |
|---|---|
| 0 | 绿，无红无黄 |
| 1 | 红，有违例 |
| 2 | 配置或用法错 |
| 3 | 黄，未核验或未绑定，不判死但不算绿 |
| 4 | 工具内部错误 |

缺 `factscribe.toml`、事实账为空、正文为空、`refs.bib` 缺失，一律退出码 2 并说清原因，不静默放行。

## 保护面

保护面指的是改写前后**不许变**的六类内容。它防的是"改写顺手把数字或公式改坏"。

| 面 | 内容 |
|---|---|
| 事实标记 | 全文 `\fact{}` 的多重集 |
| 数字 | 归一化后的数字多重集 |
| 引用 | 全部 `\cite` 家族命令的 key |
| 公式 | 行内公式与公式环境的内容哈希 |
| 表格 | `tabular` 每行的单元格数与内容哈希 |
| 交叉引用 | `\label`／`\ref` 的 key 集合 |

```bash
python3 -m factscribe protect --before 旧稿/ --after 新稿/
```

只改标点与断句应当全绿；动了任何一个数字、公式、引用即红，并给出 `文件:行` 与"改成了什么"。

## 数字回账

正文里写 `\fact{A1}`，就表示这一行的数字属于 `A1`。审计会反查：该行每个数字都必须落在 `A1` 的值域里。

| 情形 | 结果 |
|---|---|
| 绑了且命中 | 绿 |
| 没绑但能命中某条事实 | 黄 `UNBOUND_NUMBER` |
| 谁都命中不了 | 红 `UNMATCHED_NUMBER` |
| 绑了但对不上 | 红 `BOUND_MISMATCH` |

归一化口径：`1,234` 等于 `1234`，`0.90` 等于 `0.9`，`10\%` 等于 `10%`，`53k` 等于 `53000`。

## 引用落标识

所有 `\cite` 家族命令的 key 必须出现在 `refs.bib`，否则红 `MISSING_CITE`。
bib 条目按类型必须有 `arxiv` 或 `doi`，`@misc` 类可以用 `url`。
`--resolve` 会联网核验，网络失败记黄，远端明确说不存在记红。

## 黄牌规则

黄牌不阻断构建，但会让退出码变成 3。

- `UNBOUND_NUMBER`：回得到账但没绑定；
- `NO_MANIFEST` 与 `UNSIGNED_RESULT`：缺人签清单，或有未签产物；
- `VALUE_NOT_IN_SOURCE`：事实里的数字没在源文件里出现；
- `LEDGER_CONFLICT` 与 `DUPLICATE_VALUE`：账本自相矛盾，或同值多 claim；
- `CITE_UNVERIFIED`：联网核验没成；
- `UNUSED_FACT` 与 `UNUSED_BIB`：账上有没用上，bib 里有没引用。

文风黄牌共九条，分四类：破折号插入解释、标题过长或格式不对、术语首现在标题、节奏与套话。
每条都给具体行号与改法，工具不改正文。

## 已知缺口

盲测一共九套，真盲三套合计命中 30/36，误报 0。剩余缺口如实写在 `docs/release/KNOWN-GAPS.md`：

- 派生事实的表达式与实际值不符时未判红；
- `\input` 动态目标未判红；
- 部分错误码只影响分诊，不影响判定。

三条结构性边界也写在那里：信任根是人签；同机出题属弱盲测；不做 OCR，图片承载定量一律红。

## 复现与贡献

```bash
python3 -m unittest discover -s tests     # 326 例，全离线
./scripts/preflight-ci.sh                 # 本地等价 CI：干净克隆 + 3.10/3.11/3.12
```

`examples/minimal/` 是验收样例：三条事实、两节正文，故意混入一个编造数字与一个假引用，`audit` 必须只报这两处红。

规范在 `docs/design/`，实现记录在 `docs/implementation/`，历史在 `CHANGELOG.md`。
提交前请读 `CONTRIBUTING.md`，PR 必须带测试。
