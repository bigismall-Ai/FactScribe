# SPEC-EVIDENCE-STAMP｜证据钢印：人钉清单、机器执行（批 131）

状态：批 131 冻结（实施依据）。
范围：`paperkit.toml` 新增可选节 `[evidence]`；`style` 新增两条**红**判据
`REQUIRED_EVIDENCE_MISSING` / `EVIDENCE_DROPPED`；`review` 把两条判据算进
拒绝面；`brief` 节清单加「必须引用的事实」列；`NUMERAL_DENSITY` 默认阈值
改为 `null`（不判，实现与配置保留）。
**不改** `protect` 既有判据与退出码；零第三方依赖（纯标准库）。

一句话：**人声明「哪一节必须出现哪几个事实」，机器照单钉死；原来有、现在
没有的绑定一律算丢，不依赖声明。**

## 1. 为什么要有

实测（批 131 复现）：一次循环里，模型为了降低「数字密度」，把
`sections/09_discussion.tex` 的核心数字全删了，换成 `nearly every`、
`most of them`、`some`。审计仍然绿——那些事实在别节还在用；数字密度也
从「偏高」回到「健康」。但这一节的论证被抽空了。

结论：**机器判不了「哪个数字重要」，但能判「人钉进去的数字还在不在、
值对不对」。** 所以把人判断的结果写成清单，机器照着钉。

三层分工：

| 层 | 判什么 | 判据 |
|---|---|---|
| 全篇 | 数字、事实标记、引用、公式、表格、交叉引用改没改、少没少 | `protect`（既有） |
| 单节 | 人声明「本节必须引用」的 fact id 在不在本节 | `REQUIRED_EVIDENCE_MISSING` |
| 单节 × 改写前后 | 改前本节有的 `\fact{id}`，改后本节还有没有 | `EVIDENCE_DROPPED` |

`protect` 与证据钢印的分工见 §5；两者互补，不互相替代。

## 2. 配置（`[evidence]`，可选）

```toml
[evidence]
"09_discussion" = ["B1", "B2", "B3", "B4", "B8"]
```

- 键＝**节文件名去扩展名**（`sections/09_discussion.tex` → `09_discussion`），
  与 `[budget.sections]` 同一套键口径；
- 值＝该节**必须出现**的 fact id 列表（人写的；机器不推导、不排序、不补全）；
- 没有 `[evidence]` 时 `REQUIRED_EVIDENCE_MISSING` 不跑（向后兼容）；
- 值不是字符串数组、或数组里有空/非字符串条目 ⇒ 配置错（退出码 2），不猜；
- 声明的节键在项目里找不到对应节文件：**不判**（与 `[budget.sections]` 的
  未知键同口径），但读数会出现在
  `metric_details.evidence_sections_unknown` 里，便于人发现拼错；
- 同一节重复声明同一 id：按一条处理（存在性判据）。

`style` / `brief` / `polish --plan` 读的是同一份 `[evidence]`，不存在第二份
抄写。

## 3. 判据一 `REQUIRED_EVIDENCE_MISSING`（红）

| 项 | 值 |
|---|---|
| 错误码 | `REQUIRED_EVIDENCE_MISSING` |
| 严重级别 | 红（`red`），阻断，`style` 退出码 1 |
| 前置 | 该项目写了 `[evidence]`，且该节键能对上已装载的节文件 |
| 触发 | 声明的 fact id 在本节正文里找不到对应的 `\fact{id}` |
| 粒度 | 一个缺失的 id 一条 finding |

- 只查**声明过的节**；没声明的节一个 id 都不查；
- 「正文里」按 `texscan.scan_tex` 的 markers 判：注释、verbatim、批注宏里
  的 `\fact{...}` 不算引用（与本工具其它数字判据同一套遮罩）；
- V3 的 `\fact{ID}{value}` 与 v1 的 `10/12\fact{ID}` 都认（同一个 marker 表）；
- 消息固定给出四项：**节 / 缺哪个 id / 该 id 的 claim / 该 id 的 value**；
  账里根本没有这个 id 时，claim/value 位置写「账里没有这条 fact」——仍然红
  （人钉了一个不存在的 id，不可能是绿的）；
- id 匹配按大小写不敏感（与账本 `id_key` 同口径）；报错里保留人写的原样；
- `file` 是该节文件，`line` 为 1（缺的是「整节没有这条」，不是某一行少了字）；
- `suggestion` 说明「把该 id 的 `\fact{}` 绑定补回本节正文」，并写明禁做：
  不许改 id、不许改数字、不许把论点搬到别节冒充。

## 4. 判据二 `EVIDENCE_DROPPED`（红）

| 项 | 值 |
|---|---|
| 错误码 | `EVIDENCE_DROPPED` |
| 严重级别 | 红（`red`），阻断，`style --diff` / `review` 退出码 1 |
| 前置 | 有 `before`（`style --diff <改前目录>`，或 `review --before/--after`） |
| 触发 | 某节在 before 里有 `\fact{id}`，after 里没有 |
| 依赖 | **不依赖 `[evidence]` 声明**：只要原来有、现在没有，就是丢了 |

- 逐节比对（按项目内相对路径对齐；before 有、after 整节文件没了，也算全丢）；
- 一个丢掉的 id 一条 finding；`file` 为 after 的节文件，`line` 为 1；
- 消息里给 id，并在能查到账时附 claim/value（after 账优先，其次 before 账）；
- 只在 `style --diff` / `review` 运行；单跑 `style`（没有 before）不产生本码；
- **不被 `filter_new_findings` 吞掉**：这是闸门的红，不是「新增文风违规」。
  `style --diff` 的基线分析不会产生本码，滤重时也必须显式保留，否则
  `--diff` 模式反而比单跑更松。

## 5. 与 `protect` 的分工

`protect` 是**全篇多重集**比对：整篇少了一个数字、改了一个数字、少了一个
`\fact{}` 都会被它抓住。它的盲区正好是这次的实测场景——同一事实在别节还
在用，所以全篇多重集没变，单节却空了。

`EVIDENCE_DROPPED` 是**单节 × 改前后**的存在性比对：同一事实在别节留着也
不算数，被抽空的那一节必须自己报出来。

`REQUIRED_EVIDENCE_MISSING` 是**人钉的清单**：它不管改没改，只问「人说过
必须在这节出现的事实，这节现在有没有」。它补的是 `protect` 管不到的
「从一开始就没写进去」和「改写前就已经缺」两种情况。

三者都红、都退出码 1；`review` 的拒绝面同时包含三者。

## 6. 为什么机器不判「哪个数字重要」

机器能机械判断的只有三件事：**绑定在不在、值对不对、和账本一致不一致**。
「这个数字是不是本节论证的承重墙」需要读懂论证，属于人的判断。让机器猜
「重要性」会得到两种坏结果：把背景数字当承重墙（误伤，逼模型删证据），
或把承重墙当背景（漏判，正是本批要修的事）。

所以本批把人的判断固化成一份**清单**（`[evidence]`），机器只执行清单。
清单可以改，但改清单是人的动作、留在配置里、可审计；机器不在运行时替人
决定哪个数字重要。

## 7. `NUMERAL_DENSITY` 降级（默认 `null`）

同一实测的另一半：模型删证据的动机，是 `NUMERAL_DENSITY` 的黄牌在说
「数字太密」。这条判据把「数字多」当成病，而数字多往往正是论文的证据面。

改法：

- `style-rules.toml` 的 `thresholds.numeral_density` 默认值改为 `null`；
- `null` ＝ **不判**：照常计算 `metrics.numeral_density` 与逐节读数
  （`metric_details.numeral_density_sections`，`threshold` 记 `null`），
  但不产生 `NUMERAL_DENSITY` finding、不进 `fired`、不影响退出码；
- **实现与配置都保留**：人显式写 `[thresholds] numeral_density = 40`
  （或任何非负数字）就恢复旧行为，边界与阶段开关（`--stage revision`
  降为 info）一字不改；
- `polish --plan` 在阈值为 `null` 时自然不再输出该类条目（它只消费
  `style` 的 findings）；
- 文档与规则文件里写明原因：**它会诱导删证据**。降级不等于否定「读者
  感觉」那一批判据，只否定「默认把数字密度当病」这个默认值。

## 8. 谁提清单、谁冻结（批 132）

批 131 的 `[evidence]` 只认人手写。实测结论：**清单该引哪些 fact，LLM 判得
比人准**，不该强制人抄一遍。分工改为：**谁都能提清单（人、LLM、工具），
但清单一旦冻结，改动必须留痕且可见。**

### 8.1 `evidence --suggest <项目>`

- 扫描各节正文，按 `\fact{id}` 的出现顺序去重，列出**该节实际引用了哪些
  fact id**；
- 输出一段可直接粘进 `paperkit.toml` 的 `[evidence]` TOML 块（非 `--json`
  时 stdout **只有这段 TOML**，方便重定向）；
- 只做「现状快照」：不判断该不该引、不补全、不排序正文引用顺序之外的东西；
- 确定性：同一份正文两次输出逐字节一致；节键按名字排序，节内 id 按首次
  出现顺序。

### 8.2 `evidence --freeze <项目>`

读当前 `[evidence]`，写 `audit/evidence.lock`：

```toml
# 冻结时间由使用者填写（不用系统时钟，保持确定性）
canonical_sha256 = "..."
entries = 8

[sections]
"02_body" = ["B1", "B2"]
```

- **规范化口径**：节名去空白后按大小写不敏感排序；节内 fact id 去空白、
  按大小写不敏感去重、再按大小写不敏感排序；用 `节名<TAB>id,id` 拼行、
  行间 `\n`、无尾换行，UTF-8 编码后取 sha256；
- `entries` ＝ 规范化后全部 id 的条数；
- `[sections]` 是哈希的明文底稿，只用于**给人看差异**；判红只看
  `canonical_sha256`。旧式只有两行的 lock 仍能判红，但差异只能写
  「冻结件没有 [sections] 映射」；
- 不写系统时钟：冻结时间由使用者手工填注释，保证同输入同文件。

### 8.3 冻结后的检查

`audit` 与 `review` 都读 `audit/evidence.lock`：

| 情况 | 行为 |
|---|---|
| lock 不存在 | 不检查（向后兼容） |
| 规范化哈希相等 | 不判 |
| 哈希不等 | 红 `EVIDENCE_SET_CHANGED`，退出码 1 |

红消息必须给出两份清单的差异：**新增**哪些 id、**删除**哪些 id、
**移动**了哪些 id（同一 id 从一节挪到另一节）。`review` 把它算进拒绝面。

原则：**机器不判断「该不该引」，只判断「冻结后有没有被改」。** 改清单是
允许的，但必须重新 `--freeze`，让 diff 留在 git 里。

### 8.4 `brief` 同步

简报的「必须引用的事实」列直接取 `[evidence]`；某节没有声明时，用
`--suggest` 的即时结果填上，并在单元格标注「（未冻结）」。冻结与否不改变
该列来源口径：声明优先，未声明才回落到现状快照。
