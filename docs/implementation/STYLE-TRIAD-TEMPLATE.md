# 文风闸：同构排比只认模板式标记（批 110）

> 规范：`docs/design/SPEC-V3.0.md` §13.6。
> 范围：只改 `COLLOQUIAL_TRIAD` 的识别面；阈值键、黄牌档位、退出码契约未改。

## 1. 问题

节奏判据降级后，中文稿只剩 2 条 `COLLOQUIAL_TRIAD`，两条都不是真病灶：

| 位置 | 原文 | 判定 |
|---|---|---|
| `paper-zh/sections/06_ablation.tex:7` | 逐出重复读、调大文件读取可用的份额、抬高会话 token 上限 | 顿号列举的真实实验条件 |
| `paper-zh/sections/06_ablation.tex:13` | 六条约束（尽早交补丁、…、输出保持简短） | 列表被截成三项，解析缺陷 |

旧实现用「`A、B、C`」正则识别中文列举，两个问题同时存在：列举本身被当模板，
且正则只吃三项，六项清单被截断后才与相邻段凑成「同构」。英文同理，
`A, B, and C` 把四份语料里的正常并列全部算成候选。

## 2. 改法

- 只认模板式标记：`首先/其次/最后`、`第一/第二/第三`、`一是/二是/三是`、
  `其一/其二/其三`。标记必须在同一段内按序出现，才算一次三点并列。
- 顿号、逗号列举（中文 `A、B、C`／英文 `A, B, and C`）一律不算；列表项不截断，
  有几项数几项。
- 保留「同一模板指纹在相邻段落重复 ≥2 次」门槛：单段一次不报，非相邻不报，
  不同模板系列不报。
- 序数标记要求后跟分隔符（`第一，`、`第二：`），避免把「第一台机器」这类
  记数当成模板。

## 3. 读数（`paperkit-dev/` 下跑）

```text
$ python3 -m factscribe style ../paper --json        COLLOQUIAL_TRIAD 0（findings 0）
$ python3 -m factscribe style ../paper-zh --json     COLLOQUIAL_TRIAD 0（findings 0）
$ python3 -m factscribe style ../paper-b --json      COLLOQUIAL_TRIAD 0（findings 6，均为标题类）
$ python3 -m factscribe style ../paper-b-zh --json   COLLOQUIAL_TRIAD 0（findings 33，均为标题/破折号类）
```

改前 `COLLOQUIAL_TRIAD`：`paper` 0、`paper-zh` 2、`paper-b` 6、`paper-b-zh` 2；
改后四份都为 0。四条中文命中逐条核对：两条是上述假阳性，另外两条
（`paper-b-zh/sections/01_intro.tex`）也是顿号列举或破折号插入语。

## 4. 测试数

- `tests/test_style_v4.py` 的 `TestColloquialTriad`：4 例改为 6 例——
  相邻两段模板式正例；单段一次、非相邻、不同模板系列三条负例；
  顿号列举负例；六条约束整段计数负例。
- `tests/test_style.py`：三条并列正例改为模板式夹具；英文逗号列举保留为负例；
  阶段判定的触发器夹具补一对模板式段落，维持 `triggers >= 3` 的原意。
- 全套 `env PYTHONPATH=src python3 -m unittest discover -s tests`：763 例全绿。
