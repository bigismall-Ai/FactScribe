# SPEC-V3.0｜FactScribe / paperkit 冻结实施规范

> 状态：**冻结**（第 3 轮收口）。本件是实施依据，不再迭代设计；实施中发现的缺口只能以「ATTACKS 登记 + 下一版」处理，不得在本版内改判据。
> 替代：`docs/design/SPEC-V2.2.md`（保留为历史靶子）。V2.2 中未被本件修改的条款继续有效。
> 输入：外部红队 `RED-3.md` 正文 21 条（问题一 6、问题二 7、问题三 8；按严重度计 阻断 5／严重 9／中 7），逐条裁决见 §1；V2.2 的 36 个夹具与 `paper/` 基线。
> 本版一句话：**把「文本层自洽」降为辅助证据；信任锚移到项目外的签名与双向包含；把「公开答案册」换成「公开判据 + 封存盲测」。**
> 纪律：本件**不写任何 hostile 构造**（回应 3-A/3-E），只写判据、失败等级与 fixture 编号；不改 `paper/`、不改 `sihankor/`。
> **被本件整体替换的 V2.2 条款**：§2.3（退出码）、§3.2 的 PDF 回检段、§15.3（`verify-pdf`）、§16.2（签名对象）、§16.4（整条删除）、§19.2（按本件 §8 增量）、§20.2（删除构造表）、§21（位置表降级为机械生成的 `baseline.lock`）。其余条款继续有效。

---

## 0. 读法与冻结边界

1. **每条判据必须是五元组**：输入、算法、误报/漏报边界、失败等级（code + severity + exit）、对应 fixture 编号。缺任一不算判据。
2. **只有能机械执行的句子才算条款**。「建议」「应当尽量」「可考虑」在本件中不出现；做不到的写进 §7「已接受风险」，不硬凑。
3. **本件不提供攻击配方**。fixture 只给编号与期望 code；具体构造由夹具作者独立编写（§5 T-01），盲测集不入仓（T-06）。
4. **单一实现原则**：数字归一化、token 识别、摘要算法各只有一份实现（§2.6）。源层与 PDF 层调用同一个函数；两套实现漂移按 `CANON_DRIFT`（exit 4）处理。
5. **两处信任锚**：审批公钥在项目外（§4 S-01），发布公钥在项目外（S-09）。工具只能检查路径与权限，不能证明持钥者是人（S-02 写死）。

### 0.1 与 V2.2 的五个实质变化

| # | V2.2 | V3.0 | 回应 |
|---|---|---|---|
| 1 | `verify-pdf` 只做文本层、单向包含 | 每页文本下限＋双向多重集相等＋白名单显式计数＋栅格/图片结构检查 | 1-A/1-B |
| 2 | stamp 只看 PDF 元数据与自洽哈希，`STAMP_UNVERIFIED` advisory | stamp 由项目外公钥验签，签名体含 `report_sha256 + rules_sha256 + assertions_digest + pdf_sha256`；未验过即阻断 | 1-C/1-D |
| 3 | 人签对象是「值」 | 人签对象是「断言」：claim id＋值＋显示形＋句子指纹＋角色＋`input_set_sha256`＋nonce＋时间 | 2-B/2-C |
| 4 | 规则常量在代码里但不进 `rules_sha256` | `rules_sha256` 覆盖生效判定面（含代码常量），并有发布签名 | 2-E |
| 5 | 36 个夹具的构造写在规范正文 | 规范只留判据与 fixture 编号；盲测 12 个项目封存，命中率 ≥80% 才可发布 | 3-A/3-E |

---

## 1. 裁决表（RED-3 正文 21 条，逐条不漏）

> 口径：**采纳**＝按建议改；**部分**＝采纳主判据、驳回其附带手段（驳回项逐条落 §1.3）；**驳回**＝原命题不成立或不可实现。

### 1.1 正文 21 条

| 编号 | 结论 | 一句话理由 | 改成什么（V3.0 落点） |
|---|---|---|---|
| 1-A | **部分** | 「文本层回检不等于渲染结果回检」成立；但「渲染层 OCR/逐页 diff 作为发布闸」引入不可靠依赖，且仍可被更高级的渲染欺骗 | 每页文本下限＋反向包含＋栅格/图片结构检查（P-02/P-03/P-04/P-06）；**驳回** OCR 与渲染 diff 作为闸门（§1.3-R1） |
| 1-B | 采纳 | 单向包含在空集上平凡成立；允许集只有字符串、没有归属 | PDF 层改为**双向多重集相等**；源层用 `(fact, BU, form)` 三元组；白名单显式计数（P-04/P-05、S-03） |
| 1-C | 采纳 | 不验 stamp 签名、不验 report 出处，自洽不等于真实 | `verify-pdf` 必须验项目外公钥签名；`STAMP_UNVERIFIED` 由 advisory 升为阻断（P-08） |
| 1-D | 采纳 | stamp 载体是攻击者可控的 PDF 元数据，字段存在不是外部事实 | 元数据只作指针；stamp 独立存放并强制验签（P-08） |
| 1-E | 采纳 | 归一化函数表未定义，两套归一化必然漂移 | `CANON v3` 写死字符集、顺序、歧义策略；源/PDF 共用一份实现（§2.1、P-07） |
| 1-F | 采纳 | `--warn-only` 等于允许撤掉回检；缺工具与发布闸语义冲突 | `verify-pdf`/`release` 删除降级开关；缺 poppler → exit 2；`release` 禁止 advisory 放行（P-01、P-10） |
| 2-A | **部分** | 私钥可达性未被规定，人签自证闭环成立；但「工具强制 uid 隔离」CLI 做不到 | 私钥边界写进文档与部署清单；工具只查可检子集（路径/权限/登记）；签名动作移出工具（S-01/S-02/S-05）；**驳回**「工具可证明人签」（§1.3-R3） |
| 2-B | 采纳 | 签「值」不签「断言」，换位置不 stale | `approve_target` 加入 `assertions[]`（claim id＋值＋显示形＋句子指纹＋角色＋anchor/pair）（S-03） |
| 2-C | 采纳 | 一次签名永久有效 | `input_set_sha256` 进签名体；加 128-bit nonce＋`signed_at`；重放检测（S-03/S-04） |
| 2-D | **部分** | 「谁签」在校验时不被检查成立；但「数据结构上区分人签与代签」不可实现 | 记录 `key_id/key_origin/signers[]`，未登记 key 阻断；**如实写**「agent 能调用签名接口时无法区分」（S-06/S-02、§7-R3） |
| 2-E | 采纳 | `rules_sha256` 只覆盖配置，代码常量是无签名区 | `rules_sha256` 覆盖规则模块＋常量表；发布清单签名；改工具即 `TOOL_MODIFIED`（S-09） |
| 2-F | **部分** | `numeric_macro_allow` 是判定面，不能与普通 fact 共用一个人签 | 条目结构化受限（只允许尺寸参数形状）＋双 key 签名＋到期（S-08）；共谋风险接受（§7-R5） |
| 2-G | 采纳 | 批量自签成本低、噪声低 | 按 key＋24h 窗口分级：>10 黄、>50 红；headline fact 批量 >5 红（S-07） |
| 3-A | 采纳 | 夹具构造写在规范里＝答案册 | 本件不写构造；只写判据、fixture 编号、期望 code（T-01/T-02） |
| 3-B | 采纳 | 夹具与实现同源，`xfail` 是永久豁免 | 夹具作者与规则实现者分离；`xfail` 必须带 `expires`，逾期 CI 红；盲测集出仓（T-01/T-04/T-06） |
| 3-C | 采纳 | 覆盖度从未被测量，PDF 族零覆盖 | 每个可红/可黄 code 至少 1 hostile＋1 benign 近邻；CI 扫注册表对夹具清单（T-03） |
| 3-D | 采纳 | 成对同源奖励过度拦截、漏测误报 | benign 用真实语料＋变异近邻，独立生成；FP 率进指标（T-05/T-09） |
| 3-E | 采纳 | 没有不告知夹具的盲测 | 12 个 hostile 项目由不知 RED-3 的人/模型独立造；≥80% 命中且关键族全覆盖；不入公开仓（T-06） |
| 3-F | 采纳 | 通过率不是防护力 | 夹具断言 severity/verdict；不可降级清单；按 `attack_family` 出矩阵（T-02/T-09） |
| 3-G | **部分** | 位置公开可被针对性放宽；但完全封存位置会让回归不可调试 | 公开 code＋语义；精确位置进机械生成的 `baseline.lock`，人不可手改；残余风险接受（§7-R4） |
| 3-H | 采纳 | 攻击不记账就变一次性咨询 | `ATTACKS.md` 稳定 id＋状态＋判据＋回归夹具＋封存 holdout id（T-08） |

**小计：采纳 16、部分 5、纯驳回 0；另有 5 个子条款被明确驳回（§1.3）。**

### 1.2 结论表 B/S/M 与正文条目对照（防漏）

| 汇总项 | 对应正文 | V3.0 结论 |
|---|---|---|
| B1 | 1-A/1-B | 采纳（P-02..P-06） |
| B2 | 1-C | 采纳（P-08） |
| B3 | 1-D | 采纳（P-08） |
| B4 | 2-A | 部分（S-01/S-02/S-05） |
| B5 | 3-A | 采纳（T-01） |
| B6 | 2-B | 采纳（S-03） |
| S1 | 1-B | 部分：源层三元组采纳，PDF 层位置归属驳回（§1.3-R2） |
| S2 | 2-A | 部分：key 登记与来源采纳，工具证明人签驳回 |
| S3 | 2-C | 采纳（S-03/S-04） |
| S4 | 2-E | 采纳（S-09） |
| S5 | 3-C | 采纳（T-03） |
| S6 | 3-B | 采纳（T-04） |
| S7 | 3-D | 采纳（T-05） |
| S8 | 3-F | 采纳（T-02/T-09） |
| M1 | 1-E | 采纳（§2.1） |
| M2 | 2-D（`LEDGER_TEXT_COCHANGE`） | **驳回该规则本身**：启发式阈值既可规避又会奖励「改得不整齐」，删除，不再作为任何等级的判据 |
| M3 | 2-F | 部分（S-08） |
| M4 | 2-G | 采纳（S-07） |
| M5 | 3-G | 部分（§7-R4） |
| M6 | 3-H | 采纳（T-08） |

### 1.3 明确驳回的子条款（接受风险 + 缓解）

| # | 被驳回的子条款 | 为什么不可实现/不该做 | 接受的风险 | 缓解 |
|---|---|---|---|---|
| R1 | 1-A 修复方向 3：渲染层 OCR / 与第二份 PDF 逐页 diff 作为闸门 | 无可靠离线 OCR 依赖；渲染 diff 需要同源第二次编译，攻击者同样控制；误报率不可控，规则会被整体关掉 | 已声明图内的未授权数字、矢量描字数字不可判 | 结构化禁止：每页必须有文本层、图片必须声明且计数、正文内禁止内联图片、`\frac` 需登记（P-02/P-03/P-06）；盲测族 BT-01..04；图表人工复核 |
| R2 | 1-B/S1：PDF 层 `(fact, 位置, 形式)` 精确归属 | PDF 文本层丢失语义位置；按句/列归属不可靠，误报会迫使放宽整条规则 | 数字可能被搬到另一句（源层句子指纹能抓改句，抓不到「整句原样搬家」的语义错配） | 源层三元组＋`bu_text_sha256`＋角色；与 `anchor`/`pair_with` 联合；PDF 层只做多重集与页级结构；盲测 BT-06/BT-12 |
| R3 | 2-A：工具强制私钥不可达 / 工具证明「人签」 | CLI 无法给自己降权，也无法证明屏幕前是谁；任何「证明人签」的字段都可被 agent 伪造 | agent 可自签、可把自造公钥塞进项目外 registry | 签名动作移出工具（S-05）；key 登记链＋双人复核；`signing_mode=local_key` 在 L2 阻断；报告如实写 `key_only`；部署清单要求离线/硬件密钥；盲测 BT-07/BT-09 |
| R4 | 3-G：把 `paper/` 基线位置与期望完全封存 | 完全不可见会让回归不可调试，实施者只能猜；反而促使「按总数拟合」 | 公开 code 与语义后，仍可针对具体位置放宽 | 位置由 `baseline.lock` 机械生成、人不可手改；断言按 code 计数与 token 多重集；盲测与性质测试兜底（T-06/T-07） |
| R5 | 2-F：从根上解决「白名单签名者与 fact 签名者同一个人」 | 单机单人项目无法强制角色分离；双签在同一人手里仍可完成 | 同一个 owner 可同时批准 fact 与 `numeric_macro_allow` | 条目形状受限到尺寸参数；双 key＋到期；`numeric_macro_allow` 每次变更进报告并单列；盲测 BT-12 |

> M2（`LEDGER_TEXT_COCHANGE`）不是「部分」，是**整条规则删除**：它既不能证明共谋，又会把「改得整齐」当异常、把「改得零散」当正常。V3.0 不保留该 code。

---

## 2. 公共定义（所有判据的输入）

### 2.1 `CANON v3`：唯一的数字归一化函数

> 源层与 PDF 层必须调用同一个 `quantkey.canon()`。任何第二份正则实现都视为缺陷（`CANON_DRIFT`，exit 4）。

**输入**：UTF-8 文本（源层为 `RAW`，PDF 层为 `pdftotext -layout` 的逐页文本，保留换行与分页符）。

**算法（顺序固定，不得交换）**：

```
C0  按 U+000C 分页；PDF 层记录页码，源层记录 file:line:col。
C1  Unicode NFKC。
C2  不可见字符处理：
      - U+00AD、U+200B..U+200D、U+2060、U+FEFF 删除；
      - 但若删除会使两个数字字符直接相邻，改为插入一个 U+0020（保持 token 断开，fail-closed）。
C3  连字符族 U+2010,U+2011,U+2012,U+2013,U+2014,U+2212 → ASCII "-"。
C4  断行修复（仅 PDF 层，且仅当行尾/行首同时满足）：
      - 行尾 [0-9/.] 且下一行行首 [0-9] → 直接拼接，不插空格；
      - 行尾 "-" 且下一行行首 [0-9] → 删除 "-" 后拼接；
      - 其它情况不拼接。
C5  单位空白（仅 PDF 层）：只删除紧邻 %/‰/k/M/B 单位后缀的空白，
    以及形如「整数 整数 / 整数」中 "/" 两侧的空白（分数排版）；
    **数字与数字之间的空白一律保留为 token 分隔**（防止 "9 1.4" 被拼成 91.4 洗白）。
C6  千分位：仅当 "," 位于数字之间、其后恰好 3 位数字、且第 4 位不是数字时删除。
    例：1,234 → 1234；9,14 → 保持 "9,14"（不猜）。
C7  小数点：默认 "."。project.number_locale = "comma" 时（必须 owner 签名），
    把数字之间的单个 "," 且其后 1..3 位数字改为 "."；同时存在 "." 与 "," 的 token
    判为歧义，key = "amb:<sha1(raw)>"，永不与普通 key 相等。
C8  百分号/千分号：尾部 % → 追加 pct 与 dec/100；尾部 ‰ → 追加 permille 与 dec/1000。
C9  分数 A/B：key = "frac:A/B"；若 B 整除 A 且十进制在 12 位内终止，追加 "dec:<精确值>"。
    例：10/16 → frac:10/16 + dec:0.625；1/3 → 只有 frac:1/3。
C10 十进制：去尾零（0.910 → 0.91；91.0 → 91），保留至少一位整数位。
C11 指数：1.2e-3 → dec:0.0012；1.2E+3 → dec:1200。
C12 单位后缀：k/M/B 换算为十进制；% 按 C8；倍/成/折按 V2.2 R-01 的表。
C13 输出 token：{raw, key(s), span, file/page, line, col}。
```

**等价类（必须同时接受或同时拒绝）**：

| 写法 A | 写法 B | 结果 |
|---|---|---|
| `0.91` | `0.910` | 同 key |
| `10/16` | `0.625` / `62.5%` | 同 key（精确终止才追加 dec） |
| `1,234` | `1234` | 同 key（3 位分组） |
| `９１.４` | `91.4` | 同 key（NFKC） |
| `91,4`（默认 locale） | `91.4` | **不同 key**（fail-closed；要用逗号小数必须显式设 locale 并签名） |
| `9\u200b1.4` | `91.4` | **不同 key**（零宽保留为分隔，防拼接洗白） |
| `0.9` | `0.91` | 不同 key（不许舍入） |

**误报**：数学排版 `\frac{10}{16}` 抽成上下两行时无法稳定还原 → 源层 `COMPUTED_VALUE_UNREGISTERED` 阻断（P-06），不靠 PDF 层猜。
**漏报**：PDF 中字形映射错误、ActualText 篡改导致抽出的字符串与视觉不同 → 由 P-02/P-04 的「缺 token」与 P-03 的「图片/栅格」兜底；纯矢量描字不可判（§7-R1）。
**失败等级**：源层歧义 `CANON_AMBIGUOUS` 黄（若该 token 已绑定则红）；两份实现哈希不一致 `CANON_DRIFT` exit 4。
**fixture**：`FX-CANON-01`（等价类正例）、`FX-CANON-02`（漂移，内部）、`FX-CANON-03`（歧义）。

### 2.2 断言（assertion）

一条断言＝「某条 fact 的某个值，以某种显示形，出现在某个句子的某个位置」。最小字段：

```json
{
  "assertion_id": "sha256(claim_id|bu_id|value_canon|display_form_canon|bu_text_sha256)[:16]",
  "claim_id": "A2",
  "value_canon": "dec:0.625",
  "display_form_canon": "frac:10/16",
  "bu_id": "bu:<file>#<ordinal>",
  "bu_text_sha256": "sha256:...",
  "role": "results",
  "anchor_hits": ["assembly"],
  "pair_ids": ["A3"]
}
```

`bu_text_sha256 = sha256(CANON(把 BU 内连续空白压成一个空格、去注释、把 \fact{} 标记替换为 \x02 后的文本))`。**句子改一个词就变**，这是 2-B 的落地方式。

**「位置」的写法**：签名里用 `bu_id（file#ordinal）`＋`bu_text_sha256`＋`role`，不用 `line/col`。理由：行号会因重排版、插注释、改上一段而漂移；把行号放进签名会产生大量无意义的 `APPROVAL_STALE`，最终迫使团队关掉签名。人类可读 manifest（S-05）显示**当前**行号与句子原文，签名只认 BU 身份与句子指纹；文件路径进签名，文件内位置由 `bu_id` 固定。

### 2.3 摘要定义（全部 JCS-RFC8785）

| 名称 | 覆盖对象 | 谁生成 |
|---|---|---|
| `report_sha256` | `report.json` 去掉 `report_sha256` 字段后的 canonical JSON | 审计器 |
| `assertions_digest` | 全部 fact 的 `assertions[]` 排序后的 canonical JSON | 审计器 |
| `input_set_sha256` | `report.inputs`（路径→sha256）的 canonical JSON | 审计器 |
| `rules_sha256` | §4 S-09 规定的判定面清单（配置＋规则模块＋常量表） | 构建器 |
| `tool_digest` | 发布清单 `release.json` 的 sha256 | 构建器 |
| `target_sha256` | `approve_target` 去掉 `signature` 后的 canonical JSON | 审批准备器 |
| `stamp_sha256` | `stamp.payload` 的 canonical JSON | 发布器 |

**report schema 升为 `paperkit-report/3.0`**，新增必填字段：`tool.digest`、`tool.canon_version`、`tool.canon_sha256`、`assertions_digest`、`pdf_whitelist`、`approvals[]`、`signers[]`、`signing_mode`、`signing_boundary`。缺任一 → `REPORT_SCHEMA_INVALID`（exit 2）。

### 2.4 信任根（都在项目目录之外）

| 文件 | 用途 | 工具可检 | 工具不可检 |
|---|---|---|---|
| `approver_keys.json` | 审批公钥（人签） | 路径不在项目内；非组/世界可写；key 已登记未吊销 | 持钥者是不是人；私钥是否离线 |
| `release_keys.json` | 发布公钥（工具构建） | 同上；与审批 key 分离更好 | 构建机是否被入侵 |
| `facts.approvals/nonces.ndjson` | 审批 nonce 账（append-only） | 重放检测 | 账被整段删除 |
| `audit/stamp.json` | 发布 stamp（PDF 之外） | 签名、绑定、nonce | 签名者身份 |

**路径规则**：任何被引用的 key 文件若 `resolve()` 后位于项目根之下 → `TRUSTED_KEYS_IN_PROJECT` / `STAMP_KEY_UNTRUSTED`（红）。符号链接必须先 resolve 再判断。

### 2.5 退出码（唯一权威表，V3.0 扩展）

| 码 | verdict | 何时 | 阻断 |
|---|---|---|---|
| 0 | `PASS` | L2、无红、无 advisory、coverage 全绿、proof 达标、PDF/stamp 全过 | — |
| 0 | `UNVERIFIED` | 默认模式且 level < L2 | 不阻断（`release` 拒绝） |
| 8 | `UNVERIFIED` | `--gate`/`--ci` 下 level < L2 | 阻断 |
| 1 | `RED(FACT)` | 源层编造/不自洽/断言漂移/签名对象不符 | 阻断 |
| 2 | `RED(CONFIG)` | 配置、用法、工具缺失、工具被改 | 阻断 |
| 3 | `ADVISORY` | 仅黄 | 不阻断（`release` 仍要求 PASS） |
| 4 | `RED(INTERNAL)` | 超时、异常、编码、两份实现漂移 | 阻断 |
| 5 | `RED(COVERAGE\|INTEGRITY)` | 覆盖缺口，或 PDF/stamp 信任链失败 | 阻断（L2/release） |
| 6 | `RED(PROOF)` | `--require-proof` 未达标 | 阻断 |
| 7 | `RED(STALE\|REPLAY)` | 报告/PDF 过期、nonce 重放 | 阻断 |
| 9 | `RED(ATTACK_OPEN)` | `ATTACKS.md` 有 blocking/open 条目 | 阻断 `release` |

> V3.0 把「PDF 完整性」归入 5，而不是 3。`STAMP_UNVERIFIED` 不再是 advisory：要么验过（0），要么阻断（5）。

### 2.6 单一实现不变量（CI 强制）

1. `quantkey.canon()` 只有一份；`pdfgate` 与 `texscan` 都 import 它。
2. `TOKEN_REGISTRY`（所有 code→tier/exit/rule）只有一份；报告里的 code 必须能在注册表查到，否则 `UNKNOWN_CODE`（exit 4）。
3. `RULES` 表把 code 映射到函数；`SPEC_LINT` 检查正文标识符→注册表→schema 三处闭合。
4. 源层与 PDF 层的 tokenizer 版本号与哈希写进 report；不一致 `CANON_DRIFT`（exit 4）。
5. `canon_version`、阈值、表 A、`SAFE`、`ESCALATE_AT_L2` 全部进 `rules_sha256` 的常量清单。

---

## 3. PDF 回检（P-01..P-10）

> 运行位置：只有 L2 与 `release`。输入永远是**磁盘上的最终 PDF 字节**，不是内存对象；签名前不重新编译。
> **执行顺序写死**：P-01（工具）→ **P-08（信任链）** → **P-01S（PDF 新鲜度）** → P-02..P-07（页面与数字）→ P-09（新鲜度）。P-08 失败立即退出，**不得**拿未验签的 `report.json` 继续做允许集判定；P-01S 命中即跳过整个 PDF 层，**不得**用过期的 PDF 做数字比对。

### P-01 工具链与版本

| 项 | 内容 |
|---|---|
| 输入 | `PATH` 上的 `pdftotext`、`pdfinfo`、`pdfimages`；PDF 路径 |
| 算法 | 三个命令 `-v` 均退出 0，且 `pdfimages -list <pdf>` 能输出表头（能力探测）；版本字符串写进报告供审计，不作为判定。逐页文本用 `pdftotext -layout PDF -`，按 U+000C 分页；页数必须等于 `pdfinfo` 的 `Pages`。混合页面尺寸时逐页调 `pdfinfo -f i -l i` 取该页尺寸，取不到则用第一页尺寸并在报告记 `PAGE_SIZE_FALLBACK`（黄） |
| 误报/漏报 | 无（工具存在性）；不同发行版输出格式差异只影响解析，不影响判定，解析失败按工具缺失处理 |
| 失败等级 | `PDF_TOOL_MISSING` → 红/CONFIG，exit 2；`release` 直接拒绝 |
| fixture | `FX-PDF-00`（缺工具，mock PATH）、`FX-PDF-00b`（正常）、`FX-PDF-14`（尺寸回退，黄） |

### P-01S PDF 新鲜度：`PDF_STALE`（旧 PDF 不得当答案提示）

| 项 | 内容 |
|---|---|
| 输入 | 磁盘 `main.pdf` 的 mtime；审计闭包内全部 `.tex`（含 `\input` 展开）、`.bib`（含正文声明的多 bib）、`facts/*.toml` 的 mtime |
| 算法 | 若 PDF 存在且 mtime **早于**闭包内任一源文件的 mtime → `PDF_STALE`。命中即**整个 PDF 层跳过**（不抽页文本、不做 P-02..P-05 数字比对），只报这一条：旧 PDF 里的数字不许继续当「这一节该写什么」的提示 |
| 为什么用 mtime | PDF 编译非确定性（时间戳、对象顺序、ID），内容哈希每次都不同；mtime 是「这份 PDF 是不是这批源编出来的」的可用近似。源文件的内容锚仍由 facts 的 `source_sha256` / 审批对象负责 |
| 误报/漏报 | 误报：`touch` 源文件但没改内容、或从归档解出旧 mtime 的源 → 重编一次即消。漏报：把源文件 mtime 伪造成旧值（mtime 不是内容锚，防篡改靠 P-08 与审批对象） |
| 失败等级 | `PDF_STALE` → 红/INTEGRITY，exit 5；消息写明「PDF 比源文件旧，先重编」 |
| 边界 | 项目没有 PDF → 不报（缺 PDF 不属本判据）；`--build` 先编再判，天然不命中；`verify-pdf` 单独回检不带闭包源，不判本条 |
| fixture | `tests/test_pdf_stale.py`（tex/bib/facts 变新、无 PDF、`--build`、过期 PDF 的数字不参与比对） |

### P-02 每页必须有可抽取文本层（零文本页 → 红）

| 项 | 内容 |
|---|---|
| 输入 | 每页文本 `T_i`，页数 `N` |
| 算法 | `c_i = len(re.sub(r"\s","",T_i))`；对每一页，若 `c_i < 20` → 该页 `PDF_PAGE_NO_TEXT`。逐页列出页码，不只报总数 |
| 误报/漏报 | 误报：空白页、无 caption 的整页图。**处理方式是改文档**：整页图必须带 caption/说明文字（≥20 非空白字符）；空白页必须删除。漏报：页面上有 20 字说明但正文被整页栅格化 → 由 P-03 抓 |
| 失败等级 | `PDF_PAGE_NO_TEXT` → 红/INTEGRITY，exit 5 |
| fixture | `FX-PDF-01`（整页光栅）、`FX-PDF-01b`（带 caption 的整页图，绿） |

### P-03 栅格化与图片结构

| 项 | 内容 |
|---|---|
| 输入 | `pdfimages -list` 行（page,num,type,width,height,x-ppi,y-ppi）；`pdfinfo` 每页尺寸；`report.coverage.figures`；签名的 `project.image_budget_extra` |
| 算法 | 1) 只统计 `type=="image"`（排除 `smask`）。2) 每张图显示面积占比 `a = ((w/xppi)*(h/yppi)) / (page_w_in*page_h_in)`；ppi 缺失时按 `w*h/(page_w_pt*page_h_pt)` 估算。3) `cov_i = Σa`（上限 1）。4) `cov_i ≥ 0.50 且 c_i < 400` → `PDF_PAGE_RASTERIZED`。5) `cov_i ≥ 0.50 且 c_i ≥ 400` → `PDF_PAGE_IMAGE_DOMINANT`（黄，人工看）。6) `image_count > len(report.coverage.figures) + image_budget_extra` → `PDF_IMAGE_UNDECLARED`。7) 声明了图但 PDF 一张图都没有 → `PDF_FIGURE_MISSING`（黄） |
| 误报/漏报 | 误报：一个图由多个 image 对象组成（矢量 PDF 转位图、alpha mask 已排除）；处理：把图拍平，或在签名配置里提高 `image_budget_extra`（人决定，agent 不能签）。漏报：把数字烧进一张已声明图的像素里；纯矢量描字。均进 §7-R1 |
| 失败等级 | `PDF_PAGE_RASTERIZED`/`PDF_IMAGE_UNDECLARED` → 红/INTEGRITY，exit 5；`PDF_PAGE_IMAGE_DOMINANT`/`PDF_FIGURE_MISSING` → 黄，exit 3 |
| fixture | `FX-PDF-02`（整页栅格）、`FX-PDF-03`（未声明图片）、`FX-PDF-03b`（合法图＋sidecar）、`FX-PDF-10`（图片主导但带长 caption，黄）、`FX-PDF-10b`（声明了图但 PDF 无图，黄） |

### P-04 反向包含：`ledger ⊆ PDF`（多重集）

| 项 | 内容 |
|---|---|
| 输入 | `report.number_ledger`（每条绑定 token 一条，含 fact id、raw、`keys[]`、file/page、line、col；**表格 cell、图 caption、`\factblock` 内的绑定 token 同样入账**，ledger 的定义从「BU 内 token」扩展为「所有被授权出现的 token」）；PDF 全部数字 token |
| 算法 | `pdf_counts = Counter(k for t in PDF for k in canon_keys(t))`；`ledger_counts = Counter(k for e in number_ledger for k in e.keys)`。对每个 key，若 `pdf_counts[k] < ledger_counts[k]` → `PDF_LEDGER_TOKEN_MISSING`，报 `expected/actual`、缺的 fact id 与源位置。**注意是多重集**：一个 token 被引用两次，PDF 必须出现两次；一个 token 有多个 key（如 `62.5%` 同时产生 pct 与 dec），两侧都按 `keys[]` 展开 |
| 误报/漏报 | 误报：`\frac` 上下排版、数学符号拼接、表格跨页断行 → 由 C4 断行修复与 P-06 的 `\frac` 限制处理；仍误报时只能改文档，不能放宽本判据。漏报：把 ledger 数字整批删掉并伪造 report（report 被 stamp 签名，见 P-08，不可能无 key 完成） |
| 失败等级 | `PDF_LEDGER_TOKEN_MISSING` → 红/INTEGRITY，exit 5 |
| fixture | `FX-PDF-04`（整页栅格导致全缺）、`FX-PDF-04b`（单个数字被图片替代）、`FX-PDF-04c`（合法重复引用，绿） |

### P-05 正向包含：`PDF ⊆ ledger ∪ 白名单`（多重集，白名单显式计数）

| 项 | 内容 |
|---|---|
| 输入 | PDF 全部数字 token；`report.number_ledger`；`report.pdf_whitelist`（被 stamp 签名）；`report.inputs` |
| 算法 | 1) 先做标识符掩码（§2.1 的 `symbols.external`＋URL/DOI/arXiv 正则），避免把 `GPT-4`、版本号、URL 当数字。2) `allowed_counts = ledger_counts + whitelist_counts`。3) 对每个 key：`pdf_counts[k] == allowed_counts[k]`。多 → `PDF_UNACCOUNTED_NUMBER`；少 → `PDF_LEDGER_TOKEN_MISSING`（P-04）。4) 白名单每条必须有 `{key,count,category,source}`；缺 source、count 与条目数不符、或 key 不在 PDF → `PDF_WHITELIST_UNPROVENANCED`。5) 输出白名单计数表：页号 N、文献 entry 数 B、`\ref` 目标 R、结构号 S、常量 C |
| 白名单类别 | **W1 页码**：`count = N`（或签名配置 `first_page_numbered=false` 时为 N−1）；只允许实际页码值。**W2 文献**：从 `refs.bib` 每个 entry 的字段（year/volume/number/pages/doi/eprint 等）抽数字 token，按 entry 计数（同一 entry 同一值最多 3 次，覆盖 year/volume/pages 的重复渲染）；**不按页范围豁免**；未被 `\cite`/`\nocite` 引用的 entry 由既有引用规则处理。**W3 引用编号**：`\cite` 产生的编号，count = 源层 `\cite` 出现次数；每条带 bib key。**W4 结构与图表号**：`\ref` 目标＋章节/公式/图表编号，必须匹配上下文模式（行首编号、`Figure|Table|Section|Eq.` 前缀、行尾 `(n)`、`[n]`、行首 `n.`/`n)` 列表号）；count 不得超过 `pages+sections+figures+tables+equations+refs` 的预算，超预算 → `PDF_STRUCTURAL_BUDGET_EXCEEDED`。**W5 常量**：日期、arXiv 号、许可证号等，逐条 `{value,reason,source,signed_by}`，count 必填 |
| 误报/漏报 | 误报：真实论文里大量列表编号、公式编号、引用编号 → 由 W4 上下文模式＋预算处理；仍误报时补白名单条目（人签），不放宽相等判定。漏报：把未授权数字伪装成页码/引用号；预算与盲测兜底（§7-R4） |
| 失败等级 | `PDF_UNACCOUNTED_NUMBER`/`PDF_WHITELIST_UNPROVENANCED`/`PDF_STRUCTURAL_BUDGET_EXCEEDED` → 红/INTEGRITY，exit 5；`PDF_WHITELIST_UNUSED` → 黄，exit 3 |
| fixture | `FX-PDF-05`（未授权数字）、`FX-PDF-05b`（额度内结构号，绿）、`FX-PDF-06`（结构号超预算）、`FX-PDF-07`（白名单缺出处）、`FX-PDF-08`（白名单声明了但未出现，黄） |

> **为什么是相等而不是包含**：只做 `ledger ⊆ PDF` 会让「已授权数字被无限重复、搬到任意语境」放行；只做 `PDF ⊆ ledger` 会让空文本层平凡通过。相等把两边都钉住。代价是白名单必须精确，这是有意的：白名单是**人签的声明**，不是自动放行。

### P-05S 结构性 token 白名单（源层推导）

真实论文的 PDF 里，章节号、图表编号、参考文献年份与页码是排版器生成的**结构量**，不在 `number_ledger` 上。若按 P-05 一律判「账外数字」，判据对任何真实论文都会红，等于不可用。P-05S 在数字比对前从**源文件**推导四类结构性 token，只放行这些形态：

| 类别 | 来源（源层，不从 PDF 反推） | 形态 |
|---|---|---|
| 章节号 | `main.tex` 经 `\input/\include` 展开后的编译序；`\section/\subsection/\subsubsection` 的层级与顺序 | `1`、`1.1`、`1.1.1`、`2`…（`\section*` 不编号；`\appendix` 之后是字母，不产数字） |
| 浮动体编号 | 统计 `figure`/`figure*`/`table`/`table*` 与 `equation`/`align` 等编号公式环境 | `1..N`（N 取各类计数最大值；`equation*`/`align*` 不编号，不计数） |
| 年份 | `refs.bib` 每个 entry 的 `year` 字段 | 4 位年份（`2018`、`2024`…） |
| 页码 | PDF **实际页数** `pdfinfo Pages` | `1..P` |

- **实现位置**：`texscan.structural_whitelist()` 在源解析阶段产出 `{sections, floats, years}`，`audit` 随 `report.structural_whitelist` 交给 `pdfgate.verify_document()`；页码由 `pdfgate` 按实际页数补 `1..P`。
- **判定**：`pdf_counts[k]` 超过 `ledger_counts[k] + pdf_whitelist[k]` 的**盈余**，若 `k` 属上述四类则**不判红**，计入 `structural_masked`（按类别分账）；不属于则照旧报 `PDF_UNACCOUNTED_NUMBER`。
- **边界**：这是 token 形态白名单，不是语义豁免。正文数据数字只有与结构量同形时才会被同时掩掉；账上已有的正文明细不受影响。白名单**不进** `number_ledger`、**不影响** `check`，也不替代人签 `pdf_whitelist`。
- **读数（批 121）**：`paper-b` 的 `PDF_UNACCOUNTED_NUMBER` 41 → 0（掩 56 个 token：章节 35 / 年份 17 / 页码 4）；`paper-b-zh` 45 → 0（掩 83 个：章节 55 / 年份 17 / 页码 11）。`paper` 与 `paper-zh` 回归仍 0 红。

### P-06 源头禁止「用图片承载定量」

| 项 | 内容 |
|---|---|
| 输入 | 源层 AST（`\includegraphics` 位置、所在环境、所在 BU）；`report.number_ledger` |
| 算法 | 1) `\includegraphics` 不在 `figure`/`table` 浮动环境内，且所在 BU 还有其它文字 → `INLINE_IMAGE_IN_TEXT`。2) 浮动体内的图必须有 sidecar（R-06）且进 `coverage.figures`；否则 `FIGURE_UNBOUND`。3) 含绑定 token 的 BU 里出现 `\frac/\dfrac/\tfrac` 且未登记 `project.frac_allow` → `COMPUTED_VALUE_UNREGISTERED` |
| 误报/漏报 | 误报：行内小图标（logo、checkmark）→ 登记 `project.inline_images_allow`（签名，逐条带理由）。漏报：数字烧进已声明图的像素；矢量描字（§7-R1） |
| 失败等级 | `INLINE_IMAGE_IN_TEXT`/`COMPUTED_VALUE_UNREGISTERED` → 红/FACT，exit 1；`FIGURE_UNBOUND` → 红/COVERAGE，exit 5 |
| fixture | `FX-PDF-09`（行内图片＋数字）、`FX-PDF-09b`（合法浮动图）、`FX-PDF-11`（`\frac` 承载绑定值） |

**判定（写死）**：不做 OCR，不做渲染层数字识别。正文与表格里的定量必须走文本层；图片只允许作为 `figure`/`table` 浮动体出现，必须有 sidecar（数据→图），图中的定量由 sidecar 从账取数生成。图内烧死的数字视为「不可判」，进 §7-R1，靠人工复核与盲测兜底。

### P-07 归一化实现一致性

| 项 | 内容 |
|---|---|
| 输入 | `report.tool.canon_version`、`report.tool.canon_sha256`；`verify-pdf` 自身模块哈希 |
| 算法 | 重算 `quantkey.py` 的 sha256 与 `canon_version`；与 report/stamp 中的值比对。不一致 → 终止 |
| 误报/漏报 | 无；这是防止「源层删零宽、PDF 层不删」这类漂移 |
| 失败等级 | `CANON_DRIFT` → 红/INTERNAL，exit 4 |
| fixture | `FX-CANON-02`（注入旧 canon 版本） |

### P-08 stamp / report 出处校验（1-C/1-D 的正面修复）

| 项 | 内容 |
|---|---|
| 输入 | `paper.pdf` 字节；`audit/report.json`；`audit/stamp.json`；`approver_keys.json`（项目外）；可选 `nonces.ndjson` |
| 算法 | 1) stamp schema 必须 `paperkit-stamp/3.0`；2) 用 **项目外公钥**验 ed25519 签名，签名体＝`JCS(stamp.payload)`；3) `sha256(pdf)` 必须等于 `payload.compiled.pdf_sha256`；4) `sha256(report)` 必须等于 `payload.report_sha256`；5) `report.rules_sha256 == payload.rules_sha256`、`report.assertions_digest == payload.assertions_digest`、`report.input_set_sha256 == payload.input_set_sha256`、`report.tool.digest == payload.tool_digest`；6) `report.verdict=="PASS"` 且 `report.level=="L2"`；7) PDF 元数据必须含 `paperkit-stamp:<report_sha256>` 且与报告一致（元数据只是指针，不是信任源）；8) nonce 未在账中出现过；9) `signed_at ≥ report.generated_at − 5min` 且 `≤ now + 10min` |
| 误报/漏报 | 误报：PDF 被第三方工具重存（元数据/字节变化）→ 必然失败，这是有意的：重存即不是发布件，必须重新 release。漏报：owner key 被盗（§7-R3） |
| 失败等级 | `STAMP_MISSING`/`STAMP_SIGNATURE_INVALID`/`STAMP_KEY_UNTRUSTED`/`STAMP_REPORT_MISMATCH`/`STAMP_METADATA_MISSING`/`STAMP_TIME_INVALID` → 红/INTEGRITY，exit 5；`STAMP_PDF_MISMATCH`/`STAMP_NONCE_REUSED` → 红/STALE，exit 7。PDF 被重存时先因字节变化命中 `STAMP_PDF_MISMATCH`（7），因此元数据缺失只在「字节未变但元数据被改」的构造里出现，统一按 5 处理 |
| fixture | `FX-SIG-01..07`、`FX-SIG-21` |

**stamp 签名体（写死）**：

```json
{
  "schema": "paperkit-stamp/3.0",
  "report_sha256": "sha256:...",
  "rules_sha256": "sha256:...",
  "assertions_digest": "sha256:...",
  "input_set_sha256": "sha256:...",
  "tool_digest": "sha256:...",
  "compiled": {
    "root_tex": "main.tex", "root_sha256": "sha256:...", "jobname": "main",
    "latexmk_inputs": [{"path": "main.tex", "sha256": "sha256:..."}],
    "pdf_sha256": "sha256:...", "pdf_pages": 18, "pdf_bytes": 812345
  },
  "nonce": "base64:...",
  "signed_at": "2026-11-08T12:00:00Z",
  "signer_key_id": "ed25519:OWNER-2026"
}
```

### P-09 report 新鲜度与 TOCTOU

| 项 | 内容 |
|---|---|
| 输入 | `report.inputs`（全部源文件/配置/facts/bib 哈希）；release 前磁盘现值 |
| 算法 | `release` 在编译前重算全部 inputs；任一不符 → `REPORT_STALE`（7）。编译后再次哈希 PDF 并写 stamp；编译与哈希之间不得再跑任何改写 PDF 的步骤 |
| 误报/漏报 | 误报：编译产生 `.aux` 等非输入文件不影响；只比 `inputs` 清单。漏报：审计后、编译前源文件被改且同时改回（TOCTOU 窗口）——stamp 的 `input_set_sha256` 与哈希只能覆盖编译时刻，接受 |
| 失败等级 | `REPORT_STALE` → 红/STALE，exit 7 |
| fixture | `FX-PDF-12`（审后改源再 release） |

### P-10 禁止降级开关

| 项 | 内容 |
|---|---|
| 输入 | `verify-pdf`/`release` 的命令行 |
| 算法 | 两个命令都不接受 `--warn-only`、`--advisory`、`--allow-unverified`；未知参数 → 用法错误 exit 2。`release` 内部先跑 `audit --level l2 --gate`，`verdict != PASS` 直接拒绝，不生成 stamp。`audit` 的 PDF 检查在 L2 无条件开启 |
| 误报/漏报 | 无；这是防「回检被降级成黄」 |
| 失败等级 | 用法错误 → exit 2；`release` 拒绝 → 沿用 audit 的 1/5/6 |
| fixture | `FX-PDF-12b`（传 `--warn-only`，必须 exit 2） |

---

## 4. 签名模型（S-01..S-10，写死边界）

### S-01 信任根与 key 登记

| 项 | 内容 |
|---|---|
| 输入 | `--keys <approver_keys.json>`（verify-pdf 必填）或 `project.approver_keys_file`（绝对路径）；key 登记链 |
| 算法 | 1) 文件 `resolve()` 后不得位于项目根内，否则 `TRUSTED_KEYS_IN_PROJECT`。2) 权限位 `mode & 0o022 == 0`；否则 `KEY_PERMISSION_UNSAFE`（红）。3) 文件 owner 与运行 uid 不同时无法判断写权限，报 `KEY_PERMISSION_UNVERIFIED`（黄）。4) 每条 key：`key_id`、`alg=ed25519`、32 字节公钥、`owner_label`、`registered_at`、`registered_by`、`origin∈{offline,hardware,hsm}`、`revoked_at`。5) `registered_by` 必须是已登记、未吊销的 key；首个 bootstrap key 由部署文档钉死，工具不认「自签 root」。6) 未登记 → `KEY_UNREGISTERED`；已吊销 → `KEY_REVOKED` |
| 误报/漏报 | 误报：key 轮换后旧签名 → 必须重签（有意）。漏报：agent 把自造公钥写进项目外 registry；登记链只能增加成本，不能证明人（§7-R3） |
| 失败等级 | `KEY_UNREGISTERED`/`KEY_REVOKED`/`KEY_PERMISSION_UNSAFE` → 红/FACT，exit 1；`KEY_PERMISSION_UNVERIFIED` → 黄，exit 3 |
| fixture | `FX-SIG-10`、`FX-SIG-11`、`FX-SIG-12`、`FX-SIG-27` |

### S-02 私钥边界（文档要求，工具无法强制）

**写死原文（必须原样进 README、`--help`、报告 `signing_boundary` 字段）：**

> 本工具**不能**验证签名私钥是否在 agent 可达范围之外，也**不能**证明屏幕前签名的是人。若 agent 能读取私钥、能调用签名命令、或能写 `approver_keys.json`，则本工具在数据上**无法区分人签与 agent 代签**；它能证明的只有「某个已登记公钥对应的私钥签过这份字节」。人签保证是**部署事实**，不是工具事实。

| 项 | 内容 |
|---|---|
| 输入 | `project.signing_mode ∈ {offline_manifest, local_key}` |
| 算法 | `local_key` 在 L2/release → `SIGNING_MODE_UNSAFE` 阻断。`offline_manifest` 要求存在 `approvals/<id>.manifest.md` 与外部产生的 `.sig`；工具本身**不调用** `ssh-keygen -Y sign`、`minisign -S` 或任何签名 API（CI 扫描源码，出现即 `SIGNING_API_PRESENT` exit 2） |
| 误报/漏报 | 误报：开发期用本地 key 调试 → 用 L0/L1，不跑 release。漏报：声明 `offline_manifest` 但实际本地签；工具无法发现（§7-R3） |
| 失败等级 | `SIGNING_MODE_UNSAFE` → 红/FACT，exit 1；`SIGNING_API_PRESENT` → 红/CONFIG，exit 2 |
| fixture | `FX-SIG-13`（local_key）、`FX-SIG-13b`（离线 manifest，绿）、`FX-SIG-26`（源码出现签名 API） |

### S-03 审批对象＝断言（不是值）

| 项 | 内容 |
|---|---|
| 输入 | `facts.json`、`roles.json`、源层绑定、`report.inputs`、`report.number_ledger` |
| 算法 | 生成 `approve_target`（下方 JSON），`target_sha256 = sha256(JCS(target 去掉 signature))`；外部对 `target_sha256` 签名；`ledger approve` 只生成 target 与 manifest，不生成签名 |
| 误报/漏报 | 误报：改标点/换行也会让 `bu_text_sha256` 变 → 需重签；这是 2-B 要求的代价，批次签名可一次覆盖多条。漏报：整句原样搬到另一节（文本不变、角色变）→ `role` 进断言可抓；原样搬到同角色另一位置 → 接受（§7-R2） |
| 失败等级 | `APPROVAL_STALE`/`ASSERTION_DRIFT`/`APPROVAL_MISSING_ASSERTIONS` → 红/FACT，exit 1 |
| fixture | `FX-SIG-09`、`FX-SIG-19`、`FX-SIG-19b`（合法重签，绿） |

```json
{
  "schema": "approve/3.0",
  "id": "A2",
  "value": "10/16",
  "display": ["10/16", "62.5%"],
  "quantitative": true,
  "setting": null,
  "source_sha256": "sha256:...",
  "run_id": "B23-SWB16-on",
  "observation": {"run_id": "B23-SWB16-on", "pointer": "/summary/on_resolved"},
  "condition_hash": "sha256:...",
  "aggregation": {"stat": "count", "n": 16, "over": ["instance"]},
  "co_claim": [], "anchor": ["assembly"], "pair_with": ["A3"],
  "assertions": [ /* §2.2 的数组，按 assertion_id 排序 */ ],
  "assertions_digest": "sha256:...",
  "input_set_sha256": "sha256:...",
  "rules_sha256": "sha256:...",
  "config_sha256": "sha256:...",
  "tool_digest": "sha256:...",
  "nonce": "base64:...",
  "signed_at": "2026-11-08T12:00:00Z",
  "key_id": "ed25519:OWNER-2026",
  "signature": "base64:..."
}
```

**判定**：重算 target，与签名文件旁的 `target.json` 比；`target_sha256` 不同 → `APPROVAL_STALE`。`input_set_sha256` 覆盖闭包全部文本＋facts＋bib＋配置，**正文任何改动都会让全部审批 stale**；这是 2-C 的正面回答。发布前的正常流程是：正文冻结 → 生成全部 target/manifest → 人离线批量签 → release。

### S-04 nonce 与时间戳（防复用）

| 项 | 内容 |
|---|---|
| 输入 | `approve_target.nonce/signed_at`；`facts.approvals/nonces.ndjson`；stamp 的 `nonce/signed_at` |
| 算法 | 1) nonce = 16 字节 CSPRNG，base64；2) 每条批准与每个 stamp 的 nonce 写入 append-only 账；3) 账中已存在 → `APPROVAL_REPLAY`（批准）/`STAMP_NONCE_REUSED`（stamp）；4) `signed_at` ISO-8601 Z；批准 `≤ now+10min`；stamp `≥ report.generated_at−5min` 且 `≤ now+10min`，否则 `STAMP_TIME_INVALID` |
| 误报/漏报 | 误报：时钟漂移 → 放宽到 ±10 分钟；漏报：整段删除 nonce 账（§7-R3） |
| 失败等级 | `APPROVAL_REPLAY` → 红/FACT，exit 1；`STAMP_NONCE_REUSED`/`STAMP_TIME_INVALID` → 红/STALE，exit 7 |
| fixture | `FX-SIG-08`、`FX-SIG-07`、`FX-SIG-21` |

### S-05 人可读清单（签名前必须看的东西）

| 项 | 内容 |
|---|---|
| 输入 | 单条 fact 的断言集 |
| 算法 | `paperkit ledger approve <id> --prepare` 生成 `approvals/<id>.manifest.md`，必须含：fact id、值、全部 display、claim 文本、source 路径＋sha256、run_id＋pointer、**每条断言的句子原文**（不是只给位置）、BU 指纹、角色、anchor/pair、`assertions_digest`、`input_set_sha256`、nonce、待签 target 路径。人读完后在离线环境签 `target_sha256` |
| 误报/漏报 | 误报：无。漏报：人没看就签；工具只能要求 manifest 存在（`APPROVAL_MANIFEST_MISSING`），不能证明人读过 |
| 失败等级 | `APPROVAL_MANIFEST_MISSING` → 黄，exit 3（L2 升红 exit 1） |
| fixture | `FX-SIG-22`、`FX-SIG-22b`（完整 manifest，绿） |

### S-06 报告里的签名账（谁签的、哪些 key 出现）

| 项 | 内容 |
|---|---|
| 输入 | `report.approvals[]`、`report.signers[]`、`report.key_registry_sha256`、`report.signing_mode` |
| 算法 | 每条 `{fact_id,key_id,key_origin,signed_at,nonce,assertion_digest,target_sha256}`；`signers[]` 去重；release 重验全部；L2 缺失批准 → `APPROVAL_MISSING`（红/COVERAGE）。报告固定字段 `signing_boundary: "key_only"` |
| 误报/漏报 | 误报：无用 fact 没有批准 → 只对 `REF_SET` 内的 fact 要求批准。漏报：所有 key 都是 agent 自造 → 由登记链与部署兜底（§7-R3） |
| 失败等级 | `APPROVAL_MISSING` → 红/COVERAGE，exit 5；`KEY_UNREGISTERED` → 1 |
| fixture | `FX-SIG-23`、`FX-SIG-06b`（正常签名账，绿） |

### S-07 批量批准分级

| 项 | 内容 |
|---|---|
| 输入 | 同一 `key_id` 在 24h 窗口内的批准条数；fact 的 `headline` 标记与 `role` |
| 算法 | >10 → `APPROVAL_BATCH_LARGE`（黄）；>50 → `APPROVAL_BATCH_CRITICAL`（红）；`headline:true` 或角色 `abstract/results` 的 fact 在同一窗口 >5 → `APPROVAL_BATCH_CRITICAL`（红）。按 key 汇总，不按显式 batch id（防拆批） |
| 误报/漏报 | 误报：首次迁移一次签 48 条 → 必须分批并在报告里单列；这是有意的减速带。漏报：agent 自己签（§7-R3） |
| 失败等级 | `APPROVAL_BATCH_LARGE` → 黄，exit 3；`APPROVAL_BATCH_CRITICAL` → 红/FACT，exit 1 |
| fixture | `FX-SIG-20`、`FX-SIG-20b` |

### S-08 `numeric_macro_allow` 结构化＋双签

| 项 | 内容 |
|---|---|
| 输入 | `project.numeric_macro_allow[]`；宏定义体 |
| 算法 | 每条 `{name, parameter_kind∈{length,width,count}, body_regex, reason, signed_by:[key,key], expires}`。`body_regex` 必须**逐字等于**三张内置模板之一（长度/宽度/计数），不允许自定义任意正则；否则 `NUMERIC_MACRO_SHAPE_INVALID`。`parameter_kind` 必须与模板一致：`length/width` 只允许 `^[0-9.]+ *\\(linewidth|textwidth|columnwidth|paperwidth|baselineskip|baselineskip|ex|em|pt|mm|cm|in)$`；`count` 只允许纯整数且宏名以 `num/width/height/size` 结尾。两条 `signed_by` 必须不同 key；相同 → `NUMERIC_MACRO_DOUBLE_SIGN`。过期 → `NUMERIC_MACRO_EXPIRED`（L2 红） |
| 误报/漏报 | 误报：合法布局宏形状多样 → 用 `body_regex` 显式登记。漏报：两个 key 串谋把数值宏登记成「布局」（§7-R5） |
| 失败等级 | `NUMERIC_MACRO_SHAPE_INVALID`/`NUMERIC_MACRO_DOUBLE_SIGN`/`NUMERIC_MACRO_EXPIRED` → 红/FACT，exit 1 |
| fixture | `FX-SIG-14`、`FX-SIG-15`、`FX-SIG-24`（过期） |

### S-09 `rules_sha256` 覆盖生效判定面 + 发布签名

| 项 | 内容 |
|---|---|
| 输入 | 配置（paperkit.toml、rules.json、symbols.json、roles.json、disclaimer_patterns.json、canon 表）；**全部运行时代码** `src/paperkit/**/*.py`（含 `cli/api/report/build/pdfgate/signatures`，不含 tests/tools）；常量（`ESCALATE_AT_L2`、表 A、`SAFE`、`CANON_VERSION`、全部阈值） |
| 算法 | 1) 构建器计算 `rules_sha256 = sha256(JCS(清单))`；2) 生成 `release.json`（version、rules_sha256、artifact sha256、build_id），用**发布私钥**（项目外）签名；3) 工具启动时重算自身模块哈希，与 `release.json` 比；不符 → `TOOL_MODIFIED`；4) 无 `release.json` → `TOOL_UNATTESTED`（黄；release 路径拒绝） |
| 误报/漏报 | 误报：开发版无签名 → 只在 release 拒绝。漏报：攻击者同时改代码、改嵌入式哈希、并用发布私钥重签 → 需要发布私钥，超出本工具边界（§7-R3） |
| 失败等级 | `TOOL_MODIFIED` → 红/CONFIG，exit 2；`TOOL_UNATTESTED` → 黄，exit 3；release 下 `RELEASE_TOOL_UNATTESTED` → 红/INTEGRITY，exit 5 |
| fixture | `FX-SIG-16`（改常量）、`FX-SIG-17`（无 release.json）、`FX-SIG-17b`（签名发布，绿） |

### S-10 明确写死：代签不可区分

> 若签名接口可被 agent 调用（本地 `ssh-keygen`、`minisign`、任何暴露的 HTTP 签名服务），本工具**没有**任何数据结构能区分「人签」与「agent 代签」。`key_id` 只证明「这个私钥签了」，不证明「谁在用它」。报告的 `signers[]`、`KEY_UNREGISTERED`、批量阈值都只是**提高成本**，不是身份证明。唯一的结构性缓解是：私钥不在 agent 可达的机器/进程/网络命名空间内，签名在离线或硬件设备上完成，工具只验签。

| 项 | 内容 |
|---|---|
| 输入 | `report.signers[]`、`report.signing_boundary` |
| 算法 | 报告固定写 `signing_boundary:"key_only"`；README/`--help`/stderr 横幅三处同一句话（S-02 原文） |
| 误报/漏报 | 不适用（声明性条款） |
| 失败等级 | 缺该字段 → `REPORT_SCHEMA_INVALID` exit 2 |
| fixture | `FX-SIG-25`（字段缺失，配置红） |

---

## 5. 盲测与夹具治理（T-01..T-09）

### T-01 公开判据 / 封存构造（3-A）

| 项 | 内容 |
|---|---|
| 规则 | 规范、README、CHANGELOG 只写判据、code、severity、fixture 编号；**不写**任何 hostile 的可复制构造。公开回归夹具由「夹具作者」编写，不由该规则的实现者编写；同一人不得同时改规则与对应 hostile 夹具（双人复核，单人项目用两个独立会话/模型并留记录） |
| 验收 | `python3 tools/spec_lint.py --no-construction` 扫规范与 README：出现「完整攻击配方」特征（可执行的构造块、`pdftoppm` 命令块等）→ 失败 |
| fixture | `FX-FIX-01`（元测试：注入构造块必须被 lint 抓到） |

### T-02 夹具 schema v3

```toml
id = "FX-PDF-02"
criteria = ["P-03"]
attack_family = "PDF_RASTER"        # 见 T-09 的族表
kind = "hostile"                     # hostile | benign | near_miss | paper
corpus = "synthetic"                 # synthetic | paper
expected = [
  { code = "PDF_PAGE_RASTERIZED", severity = "red", min = 1, max = 3 },
]
expected_verdict = "RED"
expected_exit = 5
xfail = { owner = "moc", reason = "迁移期", expires = "2026-12-31" }  # 可缺省
```

- **必须断言 severity 与 verdict**，不能只断言 code（3-F）。
- `min/max` 是**计数区间**，不是精确数字；禁止为了对数字而改计数语义。
- `paper` 类夹具只断言绑定级红 0 与 token 多重集，不把当前实现读数当 oracle（V2.2 2-G4 继续有效）。

### T-03 覆盖完备性（3-C/S5）

| 项 | 内容 |
|---|---|
| 规则 | `TOKEN_REGISTRY` 中每个 `severity ∈ {red, yellow}` 的 code，必须至少 1 个 hostile＋1 个 benign 近邻；缺 → `FIXTURE_COVERAGE_GAP`（CI exit 2）。每次跑出 `attack_family × code` 矩阵 |
| 验收 | `python3 tools/coverage_matrix.py --fail-on-gap` 退出 0，并打印 `covered/total` 与缺口清单 |
| fixture | `FX-FIX-02`（删一条夹具后元测试必须失败） |

### T-04 `xfail` 到期（3-B/S6）

| 项 | 内容 |
|---|---|
| 规则 | `xfail` 必须有 `owner/reason/expires`；到期日 < 今天 → CI 红 `XFAIL_EXPIRED`。只允许登记**迁移期已知红**，数量冻结在 `migration.lock`；新增攻击不得以 xfail 进入。源码与规则中不得出现夹具 id/path 字面量（`FX-*`、`BT-*`、红队编号）做分支；CI 扫到 → `FIXTURE_SPECIAL_CASE`（exit 2） |
| 验收 | `python3 tools/fixture_lint.py --strict` 退出 0；把任一 `expires` 改成昨天 → 必须 exit 2；在规则里注入 `if "FX-" in path` → 必须 exit 2 |
| fixture | `FX-FIX-03`、`FX-FIX-08` |

### T-05 benign 语料与近邻变异（3-D/S7）

| 项 | 内容 |
|---|---|
| 规则 | benign 集＝`paper/` 真实快照＋变异近邻（N1 改宏名、N2 拆字面量、N3 数字搬到相邻合法句、N4 改排版、N5 改成表格 cell、N6 改数字书写形式）。近邻由独立生成器产出，不由 hostile 作者手挑。任何新规则必须报告：在 `paper/` 上的 FP 数、在近邻集上的 FP 率 |
| 验收 | `python3 tools/benign_probe.py --corpus paper+mutants` 输出 `fp_rate`；FP > 2% 的 BU 时该规则不得为 L0 红，除非 owner 签名豁免 |
| fixture | `FX-FIX-04`、`FX-FIX-05` |

### T-06 盲测集（3-E，本版主答案）

| 项 | 内容 |
|---|---|
| 定义 | **12 个 hostile 项目**（`BT-01..BT-12`），由人、或一个**只读本规范、未读 RED-3、未看实现与夹具**的模型独立构造；不告知实现者内容；每个项目是一个可运行的 `/tmp` 项目（源＋facts＋可选 runs＋目标 PDF/产物） |
| 冻结时机 | 实现冻结（`rules_sha256` 与 `tool_digest` 锁定）之后生成；运行前只公开每个项目的 id 与期望族，不公开构造 |
| 存放 | 仓外目录 `$PAPERKIT_HOLDOUT`；仓内只放 `HOLDOUT.lock`（每个项目的 sha256＋期望 code 的 hash）。永不入公开仓、永不贴 CI 日志；只公布聚合分数 |
| 通过线 | **总命中率 ≥ 80%（≥10/12）**，且关键族 `PDF_RASTER`、`PDF_TEXT_EVASION`、`STAMP_FORGERY`、`ASSERTION_MOVE` **每族至少 1 个命中**。低于 → 闸门不可用，回炉；旧盲测集降级为公开回归，下一轮重新生成新集 |
| 命令 | `python3 tools/blind.py --holdout "$PAPERKIT_HOLDOUT" --report holdout-report.json`；退出 0 才算通过 |
| 防泄漏 | 盲测项目哈希进 `HOLDOUT.lock`；实现者提交前不得读 `$PAPERKIT_HOLDOUT`；CI 只上传聚合 JSON |

**12 个盲测项目的族分配（只给族，不给构造）**：

| id | 族 | 期望挡住的东西（语义） |
|---|---|---|
| BT-01 | PDF_RASTER | 整页/多页被栅格化，文本层空 |
| BT-02 | PDF_RASTER | 单个数字被小图替代 |
| BT-03 | PDF_TEXT_EVASION | 文本层被字体映射/覆盖手段抹掉 |
| BT-04 | PDF_TEXT_EVASION | 数字以矢量路径绘制 |
| BT-05 | PDF_LEDGER_GAP | 账上数字在 PDF 中缺失（漏渲染/漏引用） |
| BT-06 | ASSERTION_MOVE | 值不变，句子语境被换 |
| BT-07 | STAMP_FORGERY | 自造 report＋自造 stamp，无项目外 key |
| BT-08 | STAMP_FORGERY | 只用 PDF 元数据自证 stamp |
| BT-09 | SIG_REPLAY | 旧签名复用/换 target |
| BT-10 | SIG_ASSERTION | 断言缺句子指纹或指纹不覆盖改动 |
| BT-11 | NORMALIZATION | 全角/逗号/零宽/千分位混淆 |
| BT-12 | WHITELIST_ABUSE | 用页码/文献/图表号/常量洗白未授权数字 |

### T-07 性质测试（不告知考题的定律，3-E 第三层）

| 性质 | 内容 | 验收 |
|---|---|---|
| P1 | 对任意受控语料：`PDF 数字多重集 == ledger 多重集 + 白名单多重集`；且每页文本 ≥20 字符 | 生成器跑 100 组，违例即失败 |
| P2 | `canon` 等价类封闭：同一等价类的两种写法要么同时接受、要么同时拒绝；`0.9` 与 `0.91` 永不相等 | 表驱动＋随机插入不可见字符/全角/分组 |
| P3 | 任一 fact 值或断言句子改动 ⇒ `target_sha256` 必变；任一正文改动 ⇒ `input_set_sha256` 必变 | 对每个字段做单字段变异，断言 digest 变化 |
| P4 | 任一 hostile 由红变绿 ⇒ 必须伴随 `rules_sha256` 变化；否则 `RULE_CHANGE_UNREVIEWED` | CI 对比基线 |
| P5 | 白名单每条都有 `source` 与 `count`；任缺一 ⇒ 失败 | schema 校验＋生成器 |

fixture：`FX-PROP-01..05`（性质测试套件，不是可复用构造夹具）。

### T-08 攻击记分板 `ATTACKS.md`（3-H/M6）

| 字段 | 内容 |
|---|---|
| `id` | `AT-<FAM>-<nn>`，稳定不复用 |
| `title` | 一句话，不含可复制构造 |
| `family` | 与 T-09 同一族表 |
| `opened/closed` | 日期 |
| `status` | `open` / `fixed` / `accepted-risk` |
| `criterion` | 本规范的条款号（如 P-04） |
| `regression_fixture` | `FX-...`（公开回归） |
| `holdout_id` | `BT-...`（构造封存） |
| `fix_commit` | git sha |
| `verified_by` | 谁跑的盲测/回归 |

规则：`status=fixed` 必须有回归夹具且通过；`status=accepted-risk` 必须在本件 §7 有对应行；`open` 且 blocking → `release` 返回 9。

fixture：`FX-FIX-09`（`ATTACKS.md` schema 与状态一致性元测试）。

### T-09 指标口径（3-F/S8）

| 指标 | 定义 | 门槛 |
|---|---|---|
| 按族召回率 | 每个 `attack_family` 命中的 hostile / 该族总数 | 总 ≥80%；关键族每族 ≥1 |
| 真实语料误报率 | `paper/`＋近邻集上被误判的 BU 数 / 总 BU 数 | ≤2%；超过则该规则降为 advisory 或补精确白名单 |
| 未知 code 率 | 报告里出现但注册表没有的 code 数 | 必须为 0（`UNKNOWN_CODE` exit 4） |
| 降级率 | `verdict=ADVISORY` 但 code 在 `NON_DOWNGRADABLE` 清单里的次数 | 必须为 0（3-F 第 2 条） |

**族表（唯一口径，夹具与盲测共用）**：

| family | 含义 |
|---|---|
| `PDF_RASTER` | 整页/局部栅格化、图片承载数字 |
| `PDF_TEXT_EVASION` | 文本层被字体映射/ActualText/矢量路径规避 |
| `PDF_LEDGER_GAP` | 账上数字在 PDF 中缺失 |
| `PDF_WHITELIST_ABUSE` | 用页码/文献/结构号/常量洗白 |
| `STAMP_FORGERY` | 自造 report/stamp、元数据自证 |
| `SIG_REPLAY` | 旧签名复用、换 target |
| `SIG_ASSERTION` | 断言缺句子指纹、指纹不覆盖改动 |
| `NORMALIZATION` | 全角/逗号/零宽/千分位混淆 |
| `SOURCE_BINDING` | 归属、顺序、值域、宏/拼接 |
| `COVERAGE_INPUT` | 闭包、表格、图、证据链 |

关键族（T-06 必须每族至少命中 1 个）：`PDF_RASTER`、`PDF_TEXT_EVASION`、`STAMP_FORGERY`、`SIG_ASSERTION`。

fixture：`FX-FIX-10`（指标报告字段与矩阵形状的元测试）。

---

## 6. 实施顺序（A 夹具 → B 拆模块 → C 上闸门）

> 每阶段结束必须能独立回滚；B 阶段**零行为变化**是硬门：golden 输出逐字节比对，不允许「顺手修个 bug」。

### 6.1 阶段 A：夹具与基线（预计 8 小时）

| 任务 | 内容 | 工时 |
|---|---|---|
| A1 | 定义 `case.toml` v3 schema、`fixture_lint.py`、`spec_lint.py`（含 `--no-construction`） | 2h |
| A2 | 把 V2.2 设计的 36 个夹具落成 `tests/fixtures/v30/`（未实现的按判据补齐），补 `criteria/attack_family/expected severity`；RED-1/RED-2/RED-3 的新 hostile 由夹具作者独立编写（只给判据编号） | 2h |
| A3 | `paper/` 只读快照＋`baseline.lock`（token 多重集、绑定级红 0、code 计数）；快照用 `copytree` 到 tmp，永不改原目录 | 2h |
| A4 | `coverage_matrix.py`、`benign_probe.py`、`xfail` 到期检查、`migration.lock` | 2h |

**验收命令**：

```bash
python3 -m unittest discover -s tests -v
python3 tools/fixture_lint.py --strict
python3 tools/coverage_matrix.py --allow-gaps   # A 阶段允许缺口，但必须打印
```

**退出标准**：36＋新增夹具可枚举；每个 `case.toml` 的 `criteria` 能对回本件条款号；`baseline.lock` 机械生成且可复现。

### 6.2 阶段 B：拆模块（预计 14 小时，零行为变化）

**模块表（文件 → 职责 → 依赖方向）**：

| 文件 | 职责 | 只依赖 |
|---|---|---|
| `src/paperkit/models.py` | `Fact/Issue/BU/Token/Approval/Stamp` 数据类；无逻辑 | stdlib |
| `src/paperkit/quantkey.py` | `CANON v3`、token 识别、等价类、key 派生 | models |
| `src/paperkit/texscan.py` | 全局流、掩码、BU 切分、邻接判据、source map | models, quantkey |
| `src/paperkit/closure.py` | 闭包、`\input` 家族、包装宏、root 钉定 | models, texscan |
| `src/paperkit/ledger.py` | schema 2.2/3.0、append-only、display、setting、批准账 | models, quantkey |
| `src/paperkit/signatures.py` | JCS、ed25519 验签、key 登记链、nonce 账 | models, stdlib |
| `src/paperkit/rules/*.py` | 每条规则一个文件；规则之间**零 import**；`__init__.py` 的 `RULES` 表 | models, quantkey |
| `src/paperkit/report.py` | 报告装配、inputs、digests、banner | models |
| `src/paperkit/pdfgate.py` | poppler 封装、逐页文本、图片面积、双向多重集 | models, quantkey |
| `src/paperkit/build.py` | release、stamp、编译范围、元数据写入 | report, signatures, pdfgate |
| `src/paperkit/api.py` | `audit/check/release/verify-pdf` 编排 | rules, ledger, report, pdfgate, build |
| `src/paperkit/cli.py` | argv、退出码、人类/JSON 输出 | api, models |
| `tools/bundle.py` | 按拓扑序拼回单文件 `factscribe.py` | stdlib |

**依赖方向（单向，禁止回指）**：

```
cli → api → {rules/*, report, pdfgate, build}
                 ↓
        {texscan, closure, ledger, signatures, quantkey}
                 ↓
              models → stdlib
```

> B 阶段的边界：`quantkey/texscan/closure/ledger/rules/report/cli` 从现有单文件搬出；`signatures.py`、`pdfgate.py` 只建空壳与类型（函数体 `NotImplementedError`，不接入 `audit` 路径），C 阶段再填。这样 B 阶段不会有任何新判定进入执行路径，golden 才能逐字节一致。`bundle.py --check` 校验的是「bundle 后的单文件与 src 运行结果一致」，不是源码逐字节相同。

**零行为变化验收**：

```bash
# 拆前：记录 golden（generated_at/绝对路径/version 归一化）
python3 tools/golden.py --record --out tests/golden/v1
# 拆后：
python3 tools/golden.py --verify tests/golden/v1
python3 tools/bundle.py --check          # bundle 源码与 src 行为一致
python3 -m unittest discover -s tests -v # 用例数、通过数、每例 code 完全一致
```

`golden.py` 只允许归一化 `generated_at`、`tool.version`、临时目录前缀；其它字节必须相同。任一 diff → 阶段 B 失败，回滚。

### 6.3 阶段 C：上闸门（预计 36 小时）

| 任务 | 判据 | 正/负测试 | 工时 |
|---|---|---|---|
| C1 | §2.1 CANON＋P-04/P-05 文本双向多重集 | `FX-CANON-*`、`FX-PDF-04/05*` | 8h |
| C2 | P-02/P-03/P-06 页面/栅格/图片/`\frac` | `FX-PDF-01/02/03/09/10/11` | 5h |
| C3 | P-08/S-01..S-04 stamp 与审批签名链 | `FX-SIG-01..13` | 8h |
| C4 | S-05..S-07 manifest、nonce、批量 | `FX-SIG-19..23` | 5h |
| C5 | S-08/S-09 规则哈希、工具证明、发布签名 | `FX-SIG-14..17` | 4h |
| C6 | T-03/T-04/T-06 盲测 harness、CI、xfail 到期、夹具特判扫描 | `FX-FIX-01..08`、`BT-01..12` | 4h |
| C7 | 注册表、`ATTACKS.md`、README 边界文案、`SPEC_LINT` 全绿 | 元测试 | 2h |

**验收命令（C 阶段完成门）**：

```bash
# paper/ 只读：先复制到临时目录，所有写操作只发生在副本
PK_TMP="$(mktemp -d)/pk-paper"; cp -R paper "$PK_TMP"
python3 -m unittest discover -s tests -v
python3 tools/fixture_lint.py --strict
python3 tools/coverage_matrix.py --fail-on-gap
python3 tools/benign_probe.py --corpus paper+mutants --max-fp 0.02
python3 tools/golden.py --verify tests/golden/v1
python3 factscribe.py audit --level l2 --gate "$PK_TMP"
python3 factscribe.py release "$PK_TMP" --keys ~/.config/paperkit/approver_keys.json
python3 factscribe.py verify-pdf "$PK_TMP/main.pdf" \
  --report "$PK_TMP/audit/report.json" --stamp "$PK_TMP/audit/stamp.json" \
  --keys ~/.config/paperkit/approver_keys.json
python3 tools/blind.py --holdout "$PAPERKIT_HOLDOUT" --report holdout-report.json
python3 tools/spec_lint.py --no-construction
```

**发布门**：最后三条（verify-pdf、blind ≥80%、spec_lint）任一失败即不可发布；`ATTACKS.md` 有 blocking/open 条目 → exit 9。

### 6.4 总工时与并行

| 阶段 | 工时 | 可并行 |
|---|---|---|
| A 夹具 | 8h | 与 B 的 models/quantkey 可并行（夹具只依赖判据文本） |
| B 拆模块 | 14h | 与 A 部分并行；B 完成前不动规则语义 |
| C 上闸门 | 36h | C1/C2 与 C3/C4 可两路并行（都依赖 B） |
| **合计** | **58h（约 7.5 人日）**；含 10% 缓冲 64h | 不建议压缩 C3/C1 |

---

## 7. 已接受风险（不可实现项的正面交代）

| # | 风险 | 为什么接受 | 缓解 | 盲测/回归 |
|---|---|---|---|---|
| R1 | 图内数字、矢量描字、ActualText/字体映射导致的视觉-文本不一致 | 无离线 OCR；渲染 diff 不可靠；工具不能读像素语义 | 每页文本下限、图片声明与计数、正文禁内联图、`\frac` 限制、图表 sidecar、人工复核 | BT-01..04；P-02/P-03/P-06 |
| R2 | 值被搬到另一句但文本完全不变（整句搬家） | PDF 层无位置归属；源层只能对句子指纹与角色负责 | 断言含 `bu_text_sha256`＋role＋anchor/pair；`ASSERTION_DRIFT` | BT-06；S-03 |
| R3 | agent 自签、私钥可达、自造 key 登记 | CLI 无法降权，无法证明人 | 离线 manifest、key 登记链、双签、批量阈值、nonce、部署清单；报告写 `key_only` | BT-07..10；S-01..S-10 |
| R4 | 白名单/文献/结构号洗白；`paper/` 位置针对性放宽 | 完全封存位置不可调试；白名单必须允许页码/文献号 | 白名单逐条 source＋计数、结构号预算、`baseline.lock` 机械生成、盲测 | BT-12；P-05 |
| R5 | `numeric_macro_allow` 双签者串谋；同一 owner 同时管 fact 与白名单 | 单机单人无法强制角色分离 | 形状受限、到期、双 key、报告单列、盲测 | BT-12；S-08 |
| R6 | 发布私钥/审批私钥被盗或构建机被入侵 | 密钥安全是部署事实 | 发布签名、key 吊销、nonce、离线签名、审计日志 | BT-07；S-09 |
| R7 | 持钥人盲签（没读 report/manifest 就签） | 工具不能证明人读过什么 | manifest 必须含句子原文、diff 摘要、`input_set_sha256`；批量阈值；发布前人工 checklist | BT-09；S-05 |
| R8 | 本地 `latexmk` 绕过发布流程直接出 PDF | 工具不控制编译入口 | stamp 只让「非发布件」可检出；平台/上传脚本自行拒绝无 stamp PDF；README 写死 | BT-07；P-08 |

**不承诺清单（沿用 V2.2 §22，并补两条）**：

1. 不承诺断言为真；只承诺「PDF 里的数字能对上被签过的断言与账」。
2. 不承诺送达；没有项目外服务端回执时 `proof` 封顶 `self_report`。
3. 不承诺抓语义改写、图内字、矢量描字。
4. 不承诺阻止本地出 PDF；stamp 只让绕过可检出。
5. 不承诺账本本身正确；被正确签名的错误值无法靠审计消除。
6. 不承诺「绿＝可投稿」。
7. 不承诺穷尽 TeX。
8. 不承诺发现被藏起来的 attempt。
9. **不承诺证明人签**（S-02/S-10 原文）。
10. **不承诺图像内容与数据一致**；只承诺图像被声明、计数、有 sidecar 与人工复核。

---

## 8. 错误码总表（唯一注册表）

> 本节是**唯一权威码表**：V2.2 §19.2 的码不再另建第二份注册表，全部并入本表。
> 合并规则：同一 code 在 §8.1 与 §8.2 出现时，以 §8.1 的 tier/exit 为准；§8.2 对应行标「见 §8.1」。
> 每个 code 必须唯一映射一个现象。
>
> **多码原则（批 58，取代「只报第一条」）**：当多条判据同时成立时，**全部报出**，
> 不得只报第一条；`EXPECT` 命中其中任一码即算命中。「只能按最具体的码报一次」
> 只约束**同一判据内部的阶梯**（例如证据链在多个节点断开时，按最具体的那个
> 节点报一次），不约束**跨判据并发**——「正文断言被搬进附录」同时满足
> `FACT_OUT_OF_SPAN` 与 `ASSERTION_DRIFT` 时，两个码都要出现在 findings 里。
> `severity=red` 进红账；`yellow` 进黄账；`info` 只进配置告警，不驱动 exit。

### 8.1 核心码（V3.0 + §11 + 批 56 新增）

> 「本批新增/改名」标 ⟡：`COMPUTED_VALUE_UNREGISTERED`、`NUMBER_AS_CROSSREF`、`EVIDENCE_CHAIN_BROKEN`。
> `MATH_FRAC_UNVERIFIABLE` 与 `FACT_EVIDENCE_MISSING` 不再作为独立码：前者并入 `COMPUTED_VALUE_UNREGISTERED`，后者并入 `EVIDENCE_CHAIN_BROKEN`（见 §8.3）。

| code | 含义 | 触发条件（唯一映射） | severity | exit | 规则 |
|---|---|---|---|---|---|
| ⟡ COMPUTED_VALUE_UNREGISTERED | 现场计算生成且未登记的数字 | `\frac/\dfrac/\tfrac/\numexpr/\dimexpr/\inteval` 产生 token；`\frac` 未在该行的 `frac_allow` 登记 | red | 1 | P-06／§2.1 |
| ⟡ NUMBER_AS_CROSSREF | 把手写结构编号当数据 | `Table/Figure/Section/Eq./Algorithm/Appendix` 等后跟字面数字，且没有 `\ref` 稳定标识 | yellow | 3 | P-05 W4／§11.2 |
| ⟡ EVIDENCE_CHAIN_BROKEN | 证据链断节 | `source`／运行记录／`source_sha256`／`record.json`／回执 `facts[]` 任一节缺失或不符（更具体码优先） | red | 1 | §11.6 |
| FACT_SCHEMA_INVALID | facts 文件 schema 不认识 | `schema` 不是 `paperkit-fact/3.x` 或 `factscribe-fact/3.x`；大小写敏感 | red | 2 | §11.1 |
| FACT_CONTAINER_INVALID | facts 容器形态错 | `fact` 不是 `[[fact]]` 表数组，或条目不是表 | red | 2 | §11.1 |
| FACT_ID_MISSING | fact 缺 id | 条目录入时没有非空 `id` | red | 2 | §11.1 |
| BAD_ID_FORMAT | fact id 格式不合法 | `id` 不匹配 `^[A-Za-z0-9._-]+$`（v3） | red | 1 | §11.1 |
| DUPLICATE_ID | fact id 重复 | 跨文件按 `casefold()` 后重复 | red | 1 | §11.1 |
| SOURCE_SHA256_MISMATCH | 源文件哈希不符 | `source_sha256` 去 `sha256:` 前缀后 ≠ 磁盘现算 | red | 1 | §11.1／§11.6 |
| MISSING_SOURCE_SHA256 | 缺 source_sha256（v1） | v1 fact 有 source 但没有内容锚 | red | 1 | §11.1 |
| MISSING_SOURCE | source 文件不存在 | `source` 解析后的路径不是普通文件 | red | 1 | §11.6 |
| BAD_SOURCE_PATH | source 路径非法 | URL、绝对路径或含 `..` 越界 | red | 1 | §11.1 |
| SOURCE_OUTSIDE_RUNS | source 不在 runs/ 下 | v3 未配 `source_root`，source 越出 `runs/` | red | 1 | §11.6 |
| SOURCE_OUTSIDE_RESULTS | source 不在 results/ 下 | v1 未配 `source_root`，source 越出 `results/` | red | 1 | v1 沿用 |
| SOURCE_OUTSIDE_SOURCE_ROOT | source 越出 source_root | 配置了 `source_root` 但路径仍越界 | red | 1 | v1／v3 |
| UNREADABLE_SOURCE | source 读不了 | OSError／UnicodeDecodeError | red | 1 | §11.6 |
| VALUE_NOT_IN_SOURCE | value 数字未在 source 出现 | 非派生 claim 的值域回查失败 | yellow | 3 | §11.1 |
| UNBOUND_NUMBER | 数字回得到账但未内联绑定 | 该 token 在账的值域内，但所在句没有覆盖它的 `\fact{}` | yellow | 3 | §11.2 |
| UNMATCHED_NUMBER | 数字回不到任何 fact | token 不在任何 fact 的 value/display 值域内，且不属于更具体码 | red | 1 | §11.2 |
| UNKNOWN_FACT_MARKER | 引用不存在的 fact id | `\fact{ID}` 的 ID 不在账上 | red | 1 | §11.2 |
| BOUND_MISMATCH | 绑定数字不在值域内 | 被 `\fact{}` 覆盖的 token 不在该 fact 的 value/display 值域 | red | 1 | §11.2 |
| BINDING_ATTRIBUTION | 顺序归属不符 | 一句多 fact 时第 k 个 token 不属第 k 条 fact | red | 1 | §11.2 |
| NONQUANT_BACKS_QUANT | 非定量 fact 背定量数字 | 标记组里没有定量 fact，却有数字 token | red | 1 | §11.2 |
| TABLE_UNBOUND | 表格 cell 回不到账 | 表格内数字不在任何 fact 值域，且没有 cell→fact 映射 | red | 5 | R-06 |
| INPUT_TARGET_MISSING | 闭包目标缺失 | `\input`/`\include`/`\subfile` 展开时目标文件（含自动补 `.tex`）不存在 | red | 5 | R-05 |
| UNSCANNED_TEX | tex 未被扫描 | 文件在 glob 命中集但不在审计闭包 | yellow | 3 | R-05 |
| LOW_BINDING_RATE | 内联绑定率过低 | 绑定率 < 50% 且分母 ≥ 4 | yellow | 3 | R-03 |
| ARITH_IN_BODY | 算术/计数器命令产生数字 | v1 的 `\the/\value/\setcounter` 等；v3 的 `\numexpr/\dimexpr/\inteval` 改报 COMPUTED_VALUE_UNREGISTERED | red | 1 | R-01A |
| NUMERIC_IN_MACRO | 宏定义体携带数字 | `\newcommand` 等宏体出现数字且未登记 | red | 1 | R-01A |
| NUM_ADJACENT_MACRO | 数字与宏相邻拼接 | 数字 token 紧邻宏调用，可能拼成新数 | red | 1 | R-01A |
| NUM_AFTER_GROUP | 数字紧跟分组 | 数字后紧接 `{}` 分组，可能被拼接 | red | 1 | R-01A |
| NUM_ADJACENT_GROUP | 数字与分组相邻 | 数字与 `{}` 分组相邻且会被拼成新数 | red | 1 | R-01A |
| DISPLAY_INCONSISTENT | display 与 value 不等价 | 两者按 `canon_text` 不收敛到同一规范键 | red | 1 | §11.3 |
| DISPLAY_ROUNDTO_INVALID | round_to 与 display 不符 | `round_to` ≠ display 文本的小数位 | red | 2 | §11.3 |
| ASSERTION_DRIFT | 断言漂移 | 句子指纹、值域或 display 与已签断言不符 | red | 1 | S-03 |
| APPROVAL_STALE | 审批对象过期 | target/inputs/source_sha256 与签名时不同 | red | 1 | S-03 |
| APPROVAL_MISSING_ASSERTIONS | 审批缺断言 | approve_target 没有 `assertions[]` | red | 1 | S-03 |
| APPROVAL_MISSING | L2 缺批准 | `REF_SET` 内 fact 没有有效批准 | red | 5 | S-06 |
| APPROVAL_MANIFEST_MISSING | 缺人读 manifest | `approvals/<id>.manifest.md` 不存在 | yellow | 3（L2 升 1） | S-05 |
| APPROVAL_REPLAY | 审批 nonce 重放 | nonce 已在 `nonces.ndjson` | red | 1 | S-04 |
| APPROVAL_BATCH_LARGE | 同 key 24h 批签 >10 | 按 key 汇总，不按 batch id | yellow | 3 | S-07 |
| APPROVAL_BATCH_CRITICAL | 批签 >50 或头条 >5 | 同 key 24h；`headline`/abstract/results 更严 | red | 1 | S-07 |
| KEY_UNREGISTERED | 公钥未登记 | key_id 不在 registry | red | 1 | S-01 |
| KEY_REVOKED | 公钥已吊销 | registry 有 `revoked_at` | red | 1 | S-01 |
| KEY_PERMISSION_UNSAFE | key 权限不安全 | `mode & 0o022 != 0` | red | 1 | S-01 |
| KEY_PERMISSION_UNVERIFIED | key 权限不可判 | owner 与运行 uid 不同 | yellow | 3 | S-01 |
| SIGNING_MODE_UNSAFE | 签名模式不安全 | `local_key` 在 L2/release | red | 1 | S-02 |
| SIGNING_API_PRESENT | 源码出现签名 API | 扫描到 `ssh-keygen -Y sign`/`minisign` 等 | red | 2 | S-02 |
| NUMERIC_MACRO_SHAPE_INVALID | 数值宏登记形状不符 | `body_regex` 不逐字命中内置模板，或 `parameter_kind` 不符 | red | 1 | S-08 |
| NUMERIC_MACRO_DOUBLE_SIGN | 数值宏双签同 key | 两条 `signed_by` 相同 | red | 1 | S-08 |
| NUMERIC_MACRO_EXPIRED | 数值宏登记过期 | `expires` 早于今天（L2 红） | red | 1 | S-08 |
| TOOL_MODIFIED | 工具被改 | 自身模块哈希 ≠ `release.json` | red | 2 | S-09 |
| TOOL_UNATTESTED | 工具无发布证明 | 缺 `release.json` | yellow | 3 | S-09 |
| RELEASE_TOOL_UNATTESTED | release 路径缺工具证明 | release 时无签名发布清单 | red | 5 | S-09 |
| REPORT_SCHEMA_INVALID | 报告 schema 缺字段 | 缺 report/3.0 必填字段 | red | 2 | S-10 |
| REPORT_STALE | 报告过期 | `report.inputs` 与磁盘现值不符 | red | 7 | P-09 |
| STAMP_MISSING | 缺发布 stamp | `audit/stamp.json` 不存在 | red | 5 | P-08 |
| STAMP_SIGNATURE_INVALID | stamp 验签失败 | 项目外公钥验 ed25519 失败 | red | 5 | P-08 |
| STAMP_KEY_UNTRUSTED | stamp key 不可信 | key 文件位于项目内或未登记 | red | 5 | P-08 |
| STAMP_REPORT_MISMATCH | stamp 与 report 不符 | report/rules/assertions/inputs/tool 摘要不符 | red | 5 | P-08 |
| STAMP_PDF_MISMATCH | stamp 与 PDF 字节不符 | `sha256(pdf)` ≠ `payload.compiled.pdf_sha256` | red | 7 | P-08 |
| STAMP_METADATA_MISSING | PDF 元数据指针缺失 | 缺 `paperkit-stamp:<report_sha256>` | red | 5 | P-08 |
| STAMP_NONCE_REUSED | stamp nonce 重放 | nonce 已在账本 | red | 7 | S-04 |
| STAMP_TIME_INVALID | stamp 时间窗不符 | `signed_at` 越出规定窗口 | red | 7 | S-04 |
| PDF_TOOL_MISSING | 缺 PDF 工具链 | `pdftotext/pdfinfo/pdfimages` 不可用 | red | 2 | P-01 |
| PDF_PAGE_NO_TEXT | 页面无可抽取文本层 | 该页非空白字符 < 20 | red | 5 | P-02 |
| PDF_PAGE_RASTERIZED | 页面被栅格化 | 图片覆盖 ≥ 50% 且文本 < 400 | red | 5 | P-03 |
| PDF_IMAGE_UNDECLARED | 图片未声明 | 图片数 > `coverage.figures + image_budget_extra` | red | 5 | P-03 |
| PDF_PAGE_IMAGE_DOMINANT | 图片主导页面 | 图片覆盖 ≥ 50% 且文本 ≥ 400 | yellow | 3 | P-03 |
| PDF_FIGURE_MISSING | 声明了图但 PDF 无图 | `coverage.figures` 非空而 PDF 图片数为 0 | yellow | 3 | P-03 |
| PAGE_SIZE_FALLBACK | 页尺寸回退 | 逐页 `pdfinfo` 取不到，回退第一页 | yellow | 3 | P-01 |
| PDF_LEDGER_TOKEN_MISSING | PDF 缺账上 token | `pdf_counts[k] < ledger_counts[k]` | red | 5 | P-04 |
| PDF_UNACCOUNTED_NUMBER | PDF 多出未授权数字 | `pdf_counts[k] > ledger+whitelist` | red | 5 | P-05 |
| PDF_STRUCTURAL_BUDGET_EXCEEDED | 结构号超预算 | W4 编号数超过 pages+sections+figures+tables+equations+refs | red | 5 | P-05 |
| PDF_WHITELIST_UNPROVENANCED | 白名单缺出处 | 白名单条目缺 `source`/`count`，或 key 不在 PDF | red | 5 | P-05 |
| PDF_WHITELIST_UNUSED | 白名单声明未出现 | 白名单条目在 PDF 中计数为 0 | yellow | 3 | P-05 |
| INLINE_IMAGE_IN_TEXT | 正文内联图片 | `\includegraphics` 不在浮动体内且所在 BU 有其它文字 | red | 1 | P-06 |
| CANON_AMBIGUOUS | 数字歧义 | 同时出现 `.` 与 `,` 的小数 token；已绑定时升红 | yellow | 3（已绑定 1） | §2.1 |
| CANON_DRIFT | 归一化实现漂移 | 源层/PDF 层 canon 版本或哈希不一致 | red | 4 | P-07 |
| UNKNOWN_CODE | 报告含未注册码 | 报告里的 code 不在 `TOKEN_REGISTRY` | red | 4 | §2.6 |
| FIXTURE_COVERAGE_GAP | 夹具覆盖缺口 | 可红/可黄 code 缺 hostile 或 benign 近邻 | red | 2 | T-03 |
| XFAIL_EXPIRED | xfail 过期 | `expires` < 今天 | red | 2 | T-04 |
| FIXTURE_SPECIAL_CASE | 规则特判夹具 | 源码/规则出现 `FX-*`/`BT-*` 字面量分支 | red | 2 | T-04 |
| RULE_CHANGE_UNREVIEWED | 规则变更未复核 | hostile 由红转绿但 `rules_sha256` 未变 | red | 2 | T-07 |
| ATTACK_OPEN_BLOCKING | blocking 攻击未关闭 | `ATTACKS.md` 有 blocking/open | red | 9 | T-08 |
| SPEC_LINT | 规范自检失败 | 正文标识符未在注册表/schema 中闭合 | red | 2 | §19.3 |
| CONFIG_INVALID | 配置错误兜底 | 未归类的配置/用法错 | red | 2 | §10 |
| CONFIG_UNKNOWN_FIELD | 未知配置字段（提示） | 字段不在 §10.1/§10.2 闭集，忽略但记 info | info | 0 | §10.4 |
| CONFIG_ALIAS | 配置别名归一（提示） | 旧名/同义值被归一 | info | 0 | §10.2 |
| CONFIG_SCHEMA_IMPLICIT | 隐式 schema（提示） | 未写 schema 但按 v3 读 | info | 0 | §10.2 |
| BAD_CONFIDENCE | confidence 取值非法 | 不是 high/med/low | red | 1 | §11.1 |
| BAD_KIND | kind 取值非法 | 不是 claim/config | red | 1 | §11.1 |
| BAD_SUPERSEDES | supersedes 指向不存在 | 父 fact id 不在账上 | red | 1 | §11.1 |
| BAD_DERIVED_FROM | derived_from 指向不存在 | 派生父 id 不在账上 | red | 1 | §11.1 |
| EMPTY_VALUE | value 为空 | `value` 去空白后为空 | red | 2 | §11.1 |
| EXPR_INVALID | 派生算式非法 | 含四则/括号/id/`.num/.den` 之外的字符 | red | 1 | §11.1 |
| EXPR_MISMATCH | 派生结果与 value 不符 | `expr` 求值 ≠ `value` | red | 1 | §11.1 |
| DERIVED_CYCLE | 派生关系成环 | `derived_from` 图有环 | red | 1 | §11.1 |
| MISSING_EXPR | 派生事实缺算式 | 有 `derived_from` 但无 `expr` | red | 1 | §11.1 |
| MISSING_SOURCE_FIELD | v1 fact 缺 source | v1 条目录入时没有 source | red | 1 | v1 沿用 |
| SUPERSEDED_PARENT | 父 fact 已失效 | `supersedes` 指向已被替换的条目 | red | 1 | §11.1 |
| DUPLICATE_VALUE | 同值重复入账（第二张授权票） | 两条 `kind=claim` 的 fact，`value` 按 `canon_text` 归一后相同、`claim` 不同，且未写 `dup_ok=true`、组内无 `supersedes`、非派生值（§11.1） | yellow | 3 | R-04 |
| LEDGER_CONFLICT | 账本冲突 | 同 id/同值出现不一致 | yellow | 3 | R-04 |
| BIB_FILE_MISSING | bib 文件缺失 | 正文声明的 bib 不存在 | red | 1 | R-05 |
| BIB_NO_STABLE_ID | bib 缺稳定标识 | 条目无 DOI/arXiv（v3 记 info，v1 红） | info（v1 red） | 0（v1 1） | R-11 |
| BAD_STABLE_ID_FORMAT | 稳定标识格式非法 | DOI/arXiv 不能解析成真实标识 | red | 1 | R-11 |
| MISSING_CITE | 引用 key 不在 bib | `\cite{}` 的 key 无条目 | red | 1 | R-11 |
| DUPLICATE_BIB_KEY | bib key 重复 | 同一 key 定义多次 | red | 1 | R-11 |
| DUPLICATE_STABLE_ID | 稳定标识挂多个 key | 同一 DOI/arXiv 对应多个条目 | yellow | 3 | R-11 |
| UNRESOLVED_CITE | 引用远端不存在 | `--resolve` 明确返回 not_found | red | 1 | R-11 |
| CITE_UNVERIFIED | 引用远端未核验 | `--resolve` 超时/限流 | yellow | 3 | R-11 |
| UNKNOWN_CITE_COMMAND | 未知引用命令 | 不在 natbib 家族的引用命令 | red | 1 | R-11 |
| UNUSED_BIB | bib 条目未引用 | bib 里有条目、审计闭包内从未被 `\cite*` 家族引用（`\nocite{key}` 算引用；`\nocite{*}` 或 `bib_allow_unused` 命中的条目豁免）。**severity 固定 yellow，L2/`--strict` 不改级**（引用卫生不是编造风险；`--strict` 只按全局口径把黄项当失败，`severity` 仍是 yellow） | yellow | 3 | R-11 |
| UNUSED_FACT | fact 未被正文使用 | 账上 fact 没有对应断言 | yellow | 3 | R-03 |
| UNSIGNED_RESULT | 结果未签 | 结果文件没有签名 | red | 1 | R-11 |
| FIGURE_UNVERIFIED | 图未核验 | 图只声明未核验 | yellow | 3 | R-06 |
| NO_MANIFEST | 缺人签清单 | v1 `manifest` 文件不存在 | yellow | 3 | R-14 |
| MANIFEST_INVALID | 人签清单无效 | TOML 解析失败或无 `[manifest]` | red | 1 | R-14 |
| MANIFEST_UNSIGNED | 人签清单未签 | 缺 `signed_by` | red | 1 | R-14 |
| MANIFEST_HASH_MISMATCH | 清单哈希不符 | 清单记录的哈希 ≠ 现算 | red | 1 | R-14 |
| MANIFEST_NO_FILES | 清单无文件 | `[files]` 为空 | red | 1 | R-14 |
| MANIFEST_NO_TIMESTAMP | 清单无时间戳 | 缺 `signed_at` | red | 1 | R-14 |
| RESOLVE_DEGRADED | 联网核验大面积失败 | unverified 占比 > 50% 且条目 ≥ 3 | yellow | 3 | R-11 |
| SOURCE_NOT_SIGNED | source 未签 | source 不在人签清单里 | red | 1 | R-14 |
| PKIGNORE_QUANT | \pkignore 内出现定量 | 被豁免文本里含数字 | red | 1 | R-07 |

**§8.1 注·`UNSCANNED_TEX` 的「有东西可扫」口径（批 135）**：闭包外的
`.tex` 不是一律报黄，只报**确有可审计内容**的。判定：去掉注释、去掉
`\begin{document}` 之前的一切之后，须**同时**满足三条才豁免——

1. 正文为空或只剩空白/命令（结构参数不算正文）；
2. 没有阿拉伯数字 token（口径同 `_extract_numbers`，命令参数不算）；
3. 没有 `\fact{}`、没有 `\cite` 家族、没有 `\label`/`\ref` 家族。

任一条不满足而文件又不在闭包里 → 照旧报黄（`severity` 不变，fail-closed）。
典型豁免例：只含 `\documentclass[11pt]`、`margin=1in`、`\usepackage` 与
`\input` 的主文件——它没有可审计内容，报「未扫描」是噪声。

### 8.2 V2.2 §19.2 沿用码（逐条列全）

> 未在 §8.1 列出的旧码全部继续有效；`severity` 由 tier 机械派生：ADVISORY→yellow，其余→red。
> 标「见 §8.1」的行表示该 code 已在 §8.1 改级或被替换，以 §8.1 为准。

| code | 含义 | 触发条件 | severity | exit | 规则 |
|---|---|---|---|---|---|
| UNBOUND_QUANT | 定量数字未内联绑定 | 数字回得到账但没有 fact 标记覆盖 | 见 §8.1（合并到 `UNBOUND_NUMBER`） | 见 §8.1 | R-03 |
| BOUND_MISMATCH | 绑定数字不在值域 | 被标记覆盖的 token 不在 value/display 内 | 见 §8.1 | 见 §8.1 | R-03 |
| BINDING_ATTRIBUTION | 顺序归属不符 | 一句多 fact 时第 k 个数字不属第 k 条 | 见 §8.1 | 见 §8.1 | R-03（2-S1） |
| FACT_SET_OVERLAP | 标记组 fact 集合重叠 | 同句多组指向有交集 | red | 1 | R-03（2-S1） |
| CO_CLAIM_ASYMMETRIC | co_claim 非对称 | 只有一侧声明 co_claim | red | 1 | R-03 |
| FACT_UNUSED_IN_SPAN | 正文里只剩指代 | 定量 fact 的 `\fact{}` 留在正文，但正文该句没有任何数字承载它、数字只在 `\appendix` 之后出现（带标记或同值裸数字皆算；另记 `ASSERTION_DRIFT`，多码原则见 §8 开头） | yellow | 3 | R-03 |
| FACT_OUT_OF_SPAN | fact 出现在不应出现的跨度 | `role` ∈ 正文角色（abstract/introduction/methods/results/discussion/conclusion/background/related/analysis），而它的标记只在 `\appendix` 之后出现（另记 `ASSERTION_DRIFT`） | red | 1 | R-03 |
| NONQUANT_BACKS_QUANT | 非定量 fact 背定量数字 | 机制陈述授权数字 | 见 §8.1 | 见 §8.1 | R-03 |
| FACT_UNKNOWN_ID | 引用账上不存在的 fact id | id 缺失 | 见 §8.1（合并到 `UNKNOWN_FACT_MARKER`） | 见 §8.1 | R-03 |
| DISPLAY_ORDER | display 顺序不符 | 出现顺序与规范不一致 | red | 1 | R-03 |
| ANCHOR_MISSING | 断言缺 anchor | 需要锚点的角色没有 anchor | red | 1 | R-03（2-S2） |
| PAIR_MISSING | 缺 pair_with 对端 | 成对断言不完整 | red | 1 | R-03（2-S2） |
| MARKER_TRAILING | 尾随标记未绑定 | 标记在句末/数字后没有闭合 | yellow | 3 | R-02 |
| FACT_WITHOUT_QUANT | fact 无定量值 | 定量句里出现无值 fact | yellow | 3 | R-03 |
| DUPLICATE_BINDING | 同一 token 被多条 fact 绑定 | 重复绑定 | yellow | 3 | R-03 |
| FACT_AMBIGUOUS_BINDING | 归属歧义 | 同一数字可归多条 fact | yellow | 3 | R-03 |
| FACT_MULTISETTING | 同一位置多次设定 fact | 多重赋值 | red | 1 | R-03（2-S8，结构性判据） |
| SPAN_TOO_LONG | 绑定跨度超句界 | 跨句绑定 | yellow | 3 | R-02 |
| DISPLAY_INCONSISTENT | display 与 value 不等价 | 值域不收敛 | 见 §8.1 | 见 §8.1 | R-04 |
| DISPLAY_ROUNDTO_INVALID | round_to 与 display 不符 | 舍入声明错 | 见 §8.1 | 见 §8.1 | R-04（2-B2） |
| DISPLAY_APPROX | display 是近似形 | 约等号/近似写法 | yellow | 3 | R-04 |
| VALUE_NOT_STRING | value 不是字符串 | 类型错 | red | 2 | R-04 |
| VALUE_NOT_QUANT | value 不是可解析数字 | 非定量 | red | 1 | R-04 |
| STALE_LEDGER | 账与源不一致 | 账过期 | red | 1 | R-04 |
| `DUPLICATE_ID` / `LEDGER_CONFLICT` / `DUPLICATE_VALUE` | id/账/值重复或冲突 | 重复或冲突 | red / yellow | 1 / 3 | R-04（v1 沿用） |
| LEDGER_MUTATED | 账本被事后改写 | append-only 被破坏 | red | 1 | R-14 |
| LEDGER_CHAIN_BROKEN | 账本哈希链断 | 链断 | red | 1 | R-14 |
| LEDGER_EDIT_UNEVIDENCED | 账本编辑无证据 | 缺 reason/evidence | red | 1 | R-14 |
| LEDGER_CONCURRENT_EDIT | 并发编辑冲突 | 版本冲突 | red | 1 | R-14 |
| APPROVAL_STALE | 审批对象过期 | inputs/source 变化 | 见 §8.1 | 见 §8.1 | R-14（2-B5） |
| LEDGER_TEXT_COCHANGE | 账与正文同步改动（已删除） | 启发式不可判 | — | — | R-14（已删除） |
| APPROVAL_BATCH_LARGE | 同 key 24h 批签 >10 | 批量 | 见 §8.1 | 见 §8.1 | R-14 |
| CONFIG_UNSIGNED | 配置未签 | L2 | yellow | 3 / 5 | R-14 |
| SIGNATURE_TOOL_MISSING | 缺签名工具 | 环境 | red | 2 | R-14 |
| INPUT_TARGET_MISSING | 闭包输入缺失 | \input 目标不存在 | red | 5 | R-05 |
| INPUT_OUTSIDE_PROJECT | 闭包输入越界 | 路径越出项目 | red | 5 | R-05 |
| INPUT_DYNAMIC_TARGET | 输入目标动态不可解析 | 宏/变量 | red | 5 | R-05（2-S6） |
| UNREGISTERED_INPUT_WRAPPER | 未登记输入包装宏 | 自定义 \input | red | 5 | R-05（2-S6） |
| ROOT_TEX_CHANGED | root_tex 被改 | 起点变化 | red | 5 | R-05（2-S6） |
| ORPHAN_TEX | 孤儿 tex | 未被闭包引用 | red | 5 | R-05 |
| APPENDIX_UNREACHABLE | 附录不可达 | 闭包缺口 | red | 5 | R-05 |
| UNSCANNED_TEX | tex 未被扫描 | glob/闭包缺口 | 见 §8.1 | 见 §8.1 | R-05 |
| TABLE_UNBOUND | 表格 cell 回不到账 | 表格未映射 | 见 §8.1 | 见 §8.1 | R-06 |
| TABLE_DRIFT | 表格与账漂移 | cell 值不符 | red | 5 | R-06 |
| TABLE_BARE_LITERAL | 表格裸字面量 | 未绑定 | red | 5 | R-06（2-S4） |
| FIGURE_UNBOUND | 图未声明/sidecar 缺失 | 图无绑定 | red | 5 | R-06 |
| FIGURE_UNVERIFIED | 图未核验 | 仅声明 | 见 §8.1 | 见 §8.1 | R-06 |
| PKIGNORE_QUANT | \pkignore 内出现定量 | 豁免区藏数 | 见 §8.1 | 见 §8.1 | R-07 |
| EXEMPTION_MACRO_SUSPECT | 豁免宏可疑 | 宏可执行 | red | 1 | R-07 |
| IGNORE_NOT_TRACKED | 忽略项未跟踪 | 缺台账 | yellow | 3 | R-07 |
| TODO_IN_PDF | PDF 含 TODO | 未完成标记 | red | 1 | R-08 |
| TODO_MACRO_DEF | TODO 宏定义 | 宏 | yellow | 3 | R-08 |
| TODO_REQUIRED_OPEN | 必需 TODO 仍开 | 未关闭 | red | 5 | R-08 |
| TODO_CLOSED_WITHOUT_EVIDENCE | TODO 关闭无证据 | 缺证据 | red | 1 | R-08 |
| TODO_NOT_TRACKED | TODO 未跟踪 | 缺台账 | red | 5 | R-08 |
| TODO_COMMENT | TODO 在注释 | 注释 | yellow | 3 | R-08 |
| TODO_ORPHANED | TODO 孤立 | 无归属 | yellow | 3 | R-08 |
| CODENAME_IN_BODY | 内部代号进正文 | 代号 | red | 1 | R-09 |
| CODENAME_UNREGISTERED | 代号未登记 | 未注册 | red | 1 | R-09 |
| NAKED_FACT_ID | 裸 fact id 进正文 | 未渲染 | red | 1 | R-09 |
| LIMITATION_OUTSIDE | 局限声明位置错 | 不在指定节 | red | 1 | R-10 |
| DISCLAIMER_IN_RESULTS | 免责声明进结果 | 位置错 | red | 1 | R-10 |
| LIMITATION_BAD_FACT | 局限绑定错误 fact | 值不符 | red | 1 | R-10 |
| DISCLAIMER_FRAGMENTED | 免责声明碎片化 | 被拆分 | yellow | 3 | R-10 |
| LIMITATION_UNBOUND | 局限未绑定 | 缺标记 | yellow | 3 | R-10 |
| LIMITATION_POINTER_IN_RESULTS | 局限指针进结果 | 位置 | yellow | 3 | R-10 |
| RUN_RECORD_INVALID | 运行记录无效 | 缺字段/evidence none | red | 1 | R-11 |
| INVALID_FACT_CITED | 引用无效 fact | 状态 invalid | red | 1 | R-11 |
| OBSERVATION_DIGEST_MISMATCH | observation 摘要不符 | 哈希 | red | 1 | R-11 |
| OBSERVATION_POINTER_MISSING | observation pointer 缺失 | 路径 | red | 1 | R-11 |
| OBSERVATION_VALUE_MISMATCH | observation 值与 fact 不符 | 值 | red | 1 | R-11 |
| RECEIPT_SCOPE_MISMATCH | 回执范围不符 | request/response/run/attempt 四字段不全 | red | 1 | R-11（2-B3） |
| RECEIPT_SIGNATURE_INVALID | 回执签名无效 | 验签失败 | red | 1 | R-11（2-B3） |
| TRUSTED_KEYS_IN_PROJECT | 信任根在项目内 | key 路径位于项目内 | red | 1 | R-11（2-B3） |
| RUNNER_UNPINNED | 运行器未钉版本 | 环境 | red | 5 | R-11 |
| ATTEMPT_COUNT_MISMATCH | 尝试数与记录不符 | 计数 | red | 1 | R-11（2-S5） |
| SELECTION_UNREGISTERED | 选择规则未登记 | 选样 | red | 1 | R-11（2-S5） |
| AGGREGATION_MISMATCH | 聚合与记录不符 | 统计 | red | 1 | R-11（2-S5） |
| PROOF_MISSING | 缺证明 | 未提供 proof | none | 0 / 8 | R-11 |
| PROOF_COVERAGE_GAP | 证明覆盖缺口 | 部分未证 | red | 5 | R-11（2-S4） |
| PROOF_CLASS_INSUFFICIENT | 证明等级不足 | self_report | red | 5 | R-11 |
| AUDIT_WRITES_NOTHING | 审计不写任何东西 | 产物缺失 | red | 4 | R-11（2-S3） |
| REPORT_STALE | 报告过期 | inputs 变 | 见 §8.1 | 见 §8.1 | R-13 |
| SECTION_ROLE_UNKNOWN | 节角色未知 | 无法识别 | red | 5 | R-15 |
| SHELL_ESCAPE | shell 逃逸 | 命令执行 | red | 1 | R-05 |
| ARITH_IN_BODY | 算术/计数器命令产生数字 | \the/\setcounter 等 | 见 §8.1 | 见 §8.1 | R-01A（2-B1） |
| NUMERIC_IN_MACRO | 宏体携带数字 | 宏定义 | 见 §8.1 | 见 §8.1 | R-01A（2-B1） |
| NUMERIC_MACRO_IN_BODY | 未登记数值宏在正文 | 宏调用 | red | 1 | R-01A |
| NUM_ADJACENT_MACRO | 数字与宏相邻拼接 | 邻接 | 见 §8.1 | 见 §8.1 | R-01A（2-B1） |
| NUM_AFTER_GROUP` / `NUM_ADJACENT_GROUP | R-01A（2-B1） | R-01A（2-B1） | red | 1 | R-01A（2-B1） |
| PDF_UNACCOUNTED_NUMBER | PDF 多出未授权数字 | 多重集多 | 见 §8.1 | 见 §8.1 | R-01A（2-B1） |
| PDF_TOOL_MISSING | 缺 PDF 工具 | PATH | 见 §8.1 | 见 §8.1 | R-01A |
| LOW_CONF_IN_HEADLINE | 头条 fact 置信度低 | confidence | red | 1 | R-04 |
| VALUE_HAS_PROSE | value 混入散文 | 非纯数字 | yellow | 3 | R-04 |
| ABSOLUTE_SOURCE_ROOT | source_root 绝对路径 | 路径 | red | 1 | R-04 / S5 |
| EXTRACT_FORBIDDEN_SOURCE | 禁止的提取源 | 来源 | red | 2 | R-04 |
| SPELLED_QUANT | 英文拼写数字 | ten 等 | yellow | 3 / 1 | R-01 |
| CJK_QUANT_SUSPECT | 中文数字可疑 | 中文数词 | yellow | 3 | R-01 |
| APPROX_UNBOUND | 约数未绑定 | ~/approx | red | 1 | R-01 |
| QUANT_TOKEN_OVERLAP | 定量 token 重叠 | 内部 | red | 4 | R-01 |
| LIMITATION_UNMACROED | 局限未宏化 | 手写 | yellow | 3 / 5 | R-10 |
| CONDITIONAL_TEXT | 条件文本 | \if | yellow | 3 | R-08 |
| NONCE_ABSENT | 缺 nonce | 审批/stamp | yellow | 3 / 1 | R-11（2-S5） |
| STAMP_MISSING | 缺 stamp | 发布件 | 见 §8.1 | 见 §8.1 | R-13 |
| STAMP_UNVERIFIED | stamp 未验（V3 已删除） | 由具体 STAMP_* 替代 | — | — | R-13（已删除） |
| COMPILE_SCOPE_MISMATCH | 编译范围不符 | inputs | red | 1 | R-13（2-S7） |
| SPEC_LINT | 规范自检失败 | 标识符未登记 | 见 §8.1 | 见 §8.1 | §19.3（2-S2） |
| RULE_CHANGE_UNREVIEWED | 规则变更未复核 | hostile 转绿 | 见 §8.1 | 见 §8.1 | §14.3（2-G4） |
| `SOURCE_SHA256_MISMATCH` / `MISSING_SOURCE` / `SOURCE_NOT_SIGNED` | source 哈希不符 / 文件缺失 / 未签 | 证据锚断 | red | 1 | v1 沿用 |

### 8.3 本批码表 diff（新增/改名/删除）

| 处理 | code | 说明 |
|---|---|---|
| **新增** | `COMPUTED_VALUE_UNREGISTERED` | `\frac/\numexpr` 等现场计算生成且未登记的数字。替代 V3.0 §8.1 的 `MATH_FRAC_UNVERIFIABLE`（后者不再单独发射）。 |
| **新增** | `NUMBER_AS_CROSSREF` | 手写 `Table 3`/`Figure 2` 这类结构编号当数据；不再落到 `UNBOUND_NUMBER`。 |
| **新增** | `EVIDENCE_CHAIN_BROKEN` | 证据链三节任一断开；替代 §11.4 的 `FACT_EVIDENCE_MISSING`（后者不再单独发射）。 |
| **改名/合并** | `MATH_FRAC_UNVERIFIABLE` → `COMPUTED_VALUE_UNREGISTERED` | 一个现象一个码；`\frac` 未登记与 `\numexpr` 未登记统一口径。 |
| **改名/合并** | `FACT_EVIDENCE_MISSING` → `EVIDENCE_CHAIN_BROKEN` | 证据缺失从黄升红：链断即红（§11.6）。 |
| **合并** | `UNBOUND_QUANT` → `UNBOUND_NUMBER` | 同一现象（数字回得到账但未内联绑定）只保留 `UNBOUND_NUMBER`。 |
| **合并** | `FACT_UNKNOWN_ID` → `UNKNOWN_FACT_MARKER` | 同一现象（引用账上不存在的 id）只保留 `UNKNOWN_FACT_MARKER`。 |
| **沿用** | `UNKNOWN_FACT_MARKER` | 引用缺稳定标识（`\fact{A9}` 指向不存在的 id）沿用旧码。 |
| **固定** | `FACT_SCHEMA_INVALID` | 未知 facts schema 固定 **exit 2**（CONFIG），不是 3；并在 `--json.findings` 里出现。 |
| **删除** | `LEDGER_TEXT_COCHANGE` | V3.0 §1.2 M2 整条删除。 |
| **删除** | `STAMP_UNVERIFIED` | 拆成具体 `STAMP_*` 码。 |

### 8.4 唯一映射（判卷只看这张表）

| 现象 | 唯一 code | severity/exit |
|---|---|---|
| 未知 facts `schema`（含 `2.9` 降级） | `FACT_SCHEMA_INVALID` | red / 2 |
| `\frac`/`\numexpr` 现场计算且未登记 | `COMPUTED_VALUE_UNREGISTERED` | red / 1 |
| 手写 `Table 3`/`Figure 2` 当数据 | `NUMBER_AS_CROSSREF` | yellow / 3 |
| `\fact{A9}` 指向账上不存在的 id | `UNKNOWN_FACT_MARKER` | red / 1 |
| 无 `source`/`observation`，链第 1 节断 | `EVIDENCE_CHAIN_BROKEN` | red / 1 |
| `source` 文件不存在 | `MISSING_SOURCE` | red / 1 |
| `source_sha256` 与现算不符 | `SOURCE_SHA256_MISMATCH` | red / 1 |
| 缺 `record.json`／run_id 不符／`facts[]` 不含本 fact | `EVIDENCE_CHAIN_BROKEN` | red / 1 |
| 回执 `facts[]` 指向账上不存在的 id | `EVIDENCE_CHAIN_BROKEN` | red / 1 |
| 数字回得到账但句内无标记 | `UNBOUND_NUMBER` | yellow / 3 |
| 数字回不到任何 fact 且不属于上面任何专属码 | `UNMATCHED_NUMBER` | red / 1 |
| 定量 fact 在正文只剩指代、数字只在附录 | `FACT_UNUSED_IN_SPAN`（另记 `ASSERTION_DRIFT`） | yellow / 3（红码在，整体 exit 1） |
| 正文角色事实的标记只在 `\appendix` 之后 | `FACT_OUT_OF_SPAN`（另记 `ASSERTION_DRIFT`） | red / 1 |
| 两条 fact 同值不同 claim（无 `dup_ok`/`supersedes`） | `DUPLICATE_VALUE` | yellow / 3 |

### 8.5 fixture 总表（实现时按此建目录）

| 组 | 编号 | 覆盖 |
|---|---|---|
| PDF | FX-PDF-00..14 | P-01..P-10 |
| 归一化 | FX-CANON-01..03 | §2.1、P-07 |
| 签名 | FX-SIG-01..27 | S-01..S-10、P-08 |
| 治理 | FX-FIX-01..10、FX-PROP-01..05 | T-01..T-09 |
| 事实账 | FX-FACT-01..05 | §11、证据链三节 |
| 真实语料 | FX-PAPER-01..03 | 绑定 token 多重集、0 红、已知迁移红 |
| 盲测 | BT-01..12 | 封存，不入仓 |

---

## 9. 实施者检查单（照着做，不用再读别处）

1. 先跑 A 阶段，确认 `fixture_lint` 与 `baseline.lock` 可复现。
2. B 阶段只搬代码，不改判定；`golden.py --verify` 必须逐字节过。
3. C1 先做 `CANON` 与 token 注册表；任何第二份正则立刻删。
4. C3 先做「验签失败即阻断」，再做 manifest；不要先做签名字段再补验证。
5. 每个新 code 先写 hostile 与 benign 近邻，再写实现；`coverage_matrix --fail-on-gap` 是门。
6. `paper/` 只读快照；任何测试不得写原目录。
7. 盲测集只在实现冻结后跑；跑之前不读、不猜、不改。
8. 最后跑 §6.3 的八条命令；缺一条不算完成。

---

## 10. 项目配置（冻结）

> 本节冻结项目声明的**唯一规范形态**、**允许的别名**与**缺省值/优先级**。
> 起因：盲测 #3 的 16 个项目由三位独立出题人写成三种形态（扁平 schema／
> `[project]`+`root_tex`／`[project]`+`sections`），实现只认第一种，16 个项目
> 全部 exit 2——这是契约缺口，不是判据缺口。规范没写死的写法，实现不许猜；
> 写在这里，实现与夹具同表。

### 10.1 唯一规范形态

项目声明文件名固定为 `factscribe.toml`（兼容旧名 `paperkit.toml`，同解析）。
规范形态＝**一张 `[project]` 表**：

```toml
[project]
name = "demo"
root_tex = "sections/main.tex"
facts = "facts"
bib = "refs.bib"
level = "l1"
number_locale = "dot"
```

| 字段 | 必需 | 类型 | 缺省 | 说明 |
|---|---|---|---|---|
| `name` | 否 | string | `""` | 项目名（别名 `title`；两者都给时 `name` 赢） |
| `root_tex` | **二选一** | 项目内相对路径 | — | 审计闭包起点；闭包＝该文件＋`\input/\include/\subfile` 递归 |
| `sections` | **二选一** | string[]（显式清单） | 由 `root_tex` 推导 | 与 `root_tex` 二选一；给了数组就逐个展开闭包，**不许 glob** |
| `facts` | 否 | glob 或目录名 | `facts`（＝`facts/*.toml`） | 事实账文件 |
| `bib` | 否 | 项目内相对路径 | `refs.bib` | 参考文献（别名 `refs`） |
| `output` | 否 | 项目内相对路径 | `main.pdf` | 最终 PDF（PDF 回检用） |
| `level` | 否 | `l0`\|`l1`\|`l2` | `l1` | 只选层，不降级红（见 §10.3） |
| `number_locale` | 否 | `period`\|`comma` | `period` | 小数点约定（别名见 §10.2） |
| `signing_mode` | 否 | `offline_manifest`\|`local_key` | `offline_manifest` | S-02 |
| `approver_keys_file` | 否 | 项目外路径 | `""`（不检查） | 审批公钥登记（§2.4） |
| `release_keys_file` | 否 | 项目外路径 | `""`（不检查） | 发布公钥登记（§2.4） |
| `numeric_macro_allow` | 否 | 表数组或字符串数组 | `[]` | S-08；两种形态都认 |
| `frac_allow` | 否 | string[] | `[]` | P-06 的 `\frac` 登记 |
| `inline_images_allow` | 否 | string[] | `[]` | P-06 的行内小图登记 |
| `bib_allow_unused` | 否 | string[] | `[]` | R-11：`UNUSED_BIB` 的人签白名单（列出的 bib key 不算未引用；大小写不敏感） |
| `image_budget_extra` | 否 | 非负整数 | `0` | 图片预算宽限（人签） |
| `authors` | 否 | string[] | `[]` | 仅展示 |

**必需字段只有一个**：闭包起点（`root_tex` 或 `sections`）。两者都缺 →
`RED(CONFIG)`，exit 2，错误信息必须**同时点名 `root_tex` 与 `sections`**。
其余字段缺失一律取上表缺省值，不报错。

### 10.2 允许的别名（逐条，闭集）

| 规范名 | 允许的别名/写法 | 归一化结果 |
|---|---|---|
| 顶层 `schema` | `paperkit-project/3.x`、`factscribe/3.x` | 视为同一套 v3 声明 |
| fact 文件 `schema` | `paperkit-fact/3.x`、`factscribe-fact/3.x` | 同上 |
| （无 schema） | `[project]` + `root_tex`／`[project]` + `sections` | 隐式 v3，schema 补为 `paperkit-project/3.0` |
| `root_tex` | 与 `sections` 二选一；两者都给时 `root_tex` 优先 | `sections` 置空并记 `CONFIG_ALIAS` 告警 |
| `sections` | 数组或单个字符串 | 数组→显式清单；单字符串→单文件 |
| `bib` | `refs` | 同值 |
| `name` | `title` | 同值 |
| `number_locale` | `period`、`dot`、`point`、`comma` | `dot`/`point`→`period`；`comma`→`comma` |
| `level` | `l0`/`l1`/`l2`（大小写不敏感）、`0`/`1`/`2` | 小写 `l0`/`l1`/`l2` |
| `facts` | glob 或目录名 | 目录名→`<dir>/*.toml` |
| `numeric_macro_allow[].body_regex` | `\(linewidth...` 与 `(?:linewidth...` 两种转义写法（baselineskip 重复一次也算） | 视为同一张内置模板（§4 S-08） |

**v1 兼容（不改）**：`[project]` 里 `sections` 是**字符串 glob** 且配了 `facts`
＝ v1，`root_tex` 被忽略，行为与 V2.2 完全一致。v3 的 `sections` 不允许 glob。
`bib_allow_unused` 在 v1 与 v3 都认（同一字段、同一语义，§8.1 `UNUSED_BIB`）。

### 10.3 形态判定（自上而下，先命中先用）

1. 顶层有 `schema` → 形态 A（扁平 schema）；不是 v3 前缀 → exit 2。
2. `[project].sections` 是数组 → 形态 C（project + sections）。
3. `[project].root_tex` 非空且没配 `facts` → 形态 B（project + root_tex）。
4. `[project].sections` 是 glob 字符串且有 `facts` → v1（行为不变）。
5. 其余带 v3 标记键的 `[project]` → 形态 B/C（字段校验，缺起点 exit 2）。
6. 顶层出现 `root_tex`/`sections`/`output`/`signing_mode`/`number_locale`/`level`
   → 形态 A（schema 缺省）。
7. 什么都没有 → `缺少 [project] 段`（v1 的旧报错）。

缺省推导写死：`sections` 缺省＝从 `root_tex` 展开闭包；只给 `sections` 时
`root_tex` 取 `sections[0]`（供报告与 PDF 回检指代）。`level` 缺省 `l1`。
`level` 只决定跑哪些层（l0/l1＝源层，l2＝＋PDF/stamp），**不降级任何红**；
level<l2 且无红无黄时的 verdict 按 §2.5 记 `UNVERIFIED`（默认模式 exit 0；
`--gate` exit 8）。

### 10.4 未知字段：忽略但绝不静默

不在 §10.1／§10.2 字段表里的键一律**忽略**（不参与判据、不改退出码），但
必须在 `--json` 的配置面列出告警：

- `config.warnings[]`：`{code: CONFIG_UNKNOWN_FIELD|CONFIG_ALIAS|CONFIG_SCHEMA_IMPLICIT,
  severity: "info", message, field, location}`；
- `config_warnings[]`：同上列表的顶层副本，方便只读一个键的消费者；
- 人读输出同步一行「配置告警 N 条」。

`warnings`（check/audit 的顶层键）**继续是黄项列表**，不复用——复用会把
「配置归一化提示」混进判据面，破坏「黄项驱动 exit 3」的语义。

### 10.5 最小可复制示例（8 行）

```toml
[project]
name = "demo"
root_tex = "sections/main.tex"
facts = "facts"
bib = "refs.bib"
level = "l1"
number_locale = "dot"
```

---

## 11. 事实账与 `\fact{}` 绑定（冻结）

> 本节冻结**事实账文件**的唯一规范形态与 `\fact{}` 的绑定语义。
> 起因：盲测 #4 的 24 个项目全部按 §10 写对了项目声明，但事实账
> 用 `schema` 头＋`[[fact]]` 数组时被实现当成「一文件一条的扁平表」，
> 24 个项目一起报「缺 id」——§10 只冻了 `factscribe.toml`，没冻
> `facts/*.toml`。写在这里，实现与夹具同表，下一轮出题直接照抄。

### 11.1 facts 文件形态（写死）

- 文件名/位置：`project.facts` 指定（缺省 `facts`＝`facts/*.toml`）。
- `schema` 头可选，允许 `paperkit-fact/3.x` 与 `factscribe-fact/3.x`；
  其它 `schema` → `FACT_SCHEMA_INVALID`（CONFIG，exit 2）。
- 账体是 **`[[fact]]` 表数组**（一个文件可以有多条）。没有 `fact` 键时，
  允许「一文件一条、顶层扁平」的兼容形态（v3 下要求出现 `id` 或 `value`）。
- 未知字段**忽略**（前向兼容），不进判据、不改退出码。
- v1 的 `[[fact]]` 账继续按原样读，行为不变。

**唯一规范形态（可直接复制）**：

```toml
schema = "paperkit-fact/3.0"   # 可选；不写也按 v3 读（配 §10 的 [project]）

[[fact]]
id = "A2"                    # 必需，唯一，[A-Za-z0-9._-]
claim = "..."                # 必需
value = "10/16"              # 必需；数字的规范形态
display = "10/16"            # 可选；与 value 必须严格等价（也可写成数组）
source = "runs/run-01/result.json"
source_sha256 = "sha256:..."  # 必需；允许带 sha256: 前缀
locator = "§二 表 1"          # 可选
confidence = "high"           # high|med|low
derived_from = ["A1"]         # 可选；派生时必填
expr = "..."                  # 可选；派生算式（仅四则+括号）
note = ""
```

| 字段 | 必需 | 类型/取值 | 说明 |
|---|---|---|---|
| `id` | **是** | `^[A-Za-z0-9._-]+$` | 入账键；**全项目唯一**，按大小写不敏感判重 |
| `claim` | **是** | string | 一句话断言（报告/审批清单的人读面） |
| `value` | **是** | string | 数字的规范形态（`10/16`、`62.5%`、`0.625` 都是合法写法） |
| `display` | 否 | string 或 string[] | 渲染形；缺省回填 `[value]`；每一项必须与 `value` 严格等价 |
| `source` | 否* | 项目内相对路径 | 证据文件；给了就核 `source_sha256`，且必须在 `runs/`（v3）或 `source_root` 下 |
| `source_sha256` | **是** | `sha256:<64hex>` 或 `<64hex>` | 内容锚；`sha256:` 前缀可带可不带，大小写不敏感 |
| `locator` | 否 | string | 人在源里的定位（页码/小节/表号） |
| `confidence` | 否 | `high`\|`med`\|`low` | 缺省空串；`check` 要求显式合法值 |
| `derived_from` | 由 `expr` 定 | string[] | 派生事实的父 id 列表 |
| `expr` | 由 `derived_from` 定 | string | 只允许四则运算、括号、fact id 与 `.num/.den` |
| `role` | 否 | 正文角色名 | `abstract`/`introduction`/`methods`/`results`/`discussion`/`conclusion`/`background`/`related`/`analysis`；声明后若标记只在 `\appendix` 之后 → `FACT_OUT_OF_SPAN` |
| `dup_ok` | 否 | bool | 显式承认「本值与另一条 fact 本来就是同一个数」，`DUPLICATE_VALUE` 的人签豁免；缺省 `false` |
| `note` | 否 | string | 自由备注 |

\* `source` 与 `observation` 至少给一个：v3 允许只写
`observation = { run_id, pointer }`＋`source_sha256`（S-03 的 approve_target
形态）。若 `runs/<run_id>/summary.json` 存在，则自动取作 `source` 并核哈希。
两者都缺、或推导不出 `runs/` 里的运行记录 → `EVIDENCE_CHAIN_BROKEN`（红，exit 1），
定义见 §11.6。

**归一化（写死）**：

1. `id` 去首尾空白后入账；判重与引用解析都按 `casefold()`。
2. `source_sha256` 去掉可选的 `sha256:` 前缀后与现算 64 位小写 hex 比较。
3. `display` 是**渲染形**：比较前先还原 LaTeX 转义（`\%`→`%`、`\,`→`,`、
   `\;`/`\:`/`\~`→空格、`\!`→空）。`value` 不还原，按规范数字形写。
4. `display` 缺省时回填 `value`，这条回填**不参与** R-04 的等价判定
   （按定义等价），也不许被 `\fact{}` 之外的地方当成额外授权。
5. 一个文件里的多条 fact 按出现顺序读；重复 `id` 不在读取期合并。
6. `dup_ok` 是布尔豁免位，不参与数字归一化；它只关掉 `DUPLICATE_VALUE`，
   不改变 `value` 的值域，也不授权多写一次数字。

### 11.2 `\fact{id}` 的语义（写死）

两种写法都认：

- `\fact{ID}`：单参数标记，绑定**同一句**里的数字；
- `\fact{ID}{display}`：双参数标记，第二个参数是要渲染的数字，仍留在
  扫描流里参与数字审计（`display` 参数只是渲染，不单独授权）。

绑定规则（句级 BU）：

1. **标记到句末**：标记所属 BU＝它所在的那一句；句子边界由既有
   `sentence_spans` 定义（`。！？.!?` 与换行段），跨句不继承。
2. **段内每个数字都必须落在绑定 fact 的 value token 集内**：句内未被
   任何标记覆盖的数字 → `UNBOUND_NUMBER`（黄）；被覆盖但不在
   `value`/`display` 的 token 集内 → `BOUND_MISMATCH`（红，v1 口径）；
   v3 同时记 `ASSERTION_DRIFT`（句子与账的断言漂移）。
3. 一个标记组里有多个 id 时：token 数与 fact 数相等且无 `co_claim` →
   按书写顺序一一归属（`BINDING_ATTRIBUTION`）；否则整段取并集。
4. 标记了账上没有的 id → `UNKNOWN_FACT_MARKER`（红）。
5. 只有非定量 fact 来背数字 → `NONQUANT_BACKS_QUANT`（红）。
6. `\fact` 标记本身不产生数字；同句多个标记按出现顺序闭合，不跨句借数。

### 11.3 `display` 与 `value` 允许不同吗（写死）

**允许，但必须严格等价**：两者按 `canon_text` 收敛到同一个规范键才放行。
等价类示例：`10/16` ≡ `0.625` ≡ `62.5%` ≡ `62.5\%`（LaTeX 转义先还原）；
**不等价**：`0.9` ≠ `0.91`（没有四舍五入容差）、`1/16` ≠ `10/16`。

- 不等价 → `DISPLAY_INCONSISTENT`（红，exit 1）；v3 同时记 `ASSERTION_DRIFT`。
- `round_to` 若给出，必须等于 display 文本的小数位数，否则
  `DISPLAY_ROUNDTO_INVALID`（红）。
- 缺省回填的 display 按定义等价，不判 R-04。

### 11.4 错误码与退出码（写死）

| 情形 | code | tier | exit | 实现位置 |
|---|---|---|---|---|
| 缺 `id` | `FACT_ID_MISSING` | CONFIG | **2** | `config.py::_fact_from_mapping`（`ConfigError.code`） |
| `id` 重复（大小写不敏感） | `DUPLICATE_ID` | FACT | **1** | `audit.py::run_check` 与 `run_audit` 各判一次 |
| `id` 格式不合法（v3） | `BAD_ID_FORMAT` | FACT | **1** | `audit.py`（v3 用 §11.1 字符集；v1 规则不变） |
| 未知 fact `schema` | `FACT_SCHEMA_INVALID` | CONFIG | **2** | `config.py::load_facts` |
| `fact` 不是表数组 | `FACT_CONTAINER_INVALID` | CONFIG | **2** | `config.py::load_facts` |
| `source_sha256` 与现算不符 | `SOURCE_SHA256_MISMATCH` | FACT | **1** | `audit.py::verify_sources`（v3 另记 `APPROVAL_STALE`） |
| `source_sha256` 缺失（v1） | `MISSING_SOURCE_SHA256` | FACT | **1** | `audit.py::verify_sources`；v3 源层由 §11.6 证据链强制 |
| 既无 `source` 也无 `observation`，或证据链任一节断开（v3） | `EVIDENCE_CHAIN_BROKEN` | FACT | **1** | `audit.py::verify_sources`→`_evidence_chain_issues`（§11.6） |
| `display` 与 `value` 不等价 | `DISPLAY_INCONSISTENT` | FACT | **1** | `texrules.py::display_hits` |
| `display` 缺省 | 无（回填 `value`） | — | — | `config.py::_fact_from_mapping` |

CONFIG 类错误在 `--json` 里以 `{"status":"error","exit":2,"code":"..."}` 呈现，
`message` 必须指向本节（§11.1）。

### 11.5 最小可复制示例（完整项目）

`factscribe.toml`：

```toml
[project]
name = "demo"
root_tex = "sections/main.tex"
facts = "facts"
bib = "refs.bib"
level = "l1"
number_locale = "period"
```

`facts/facts.toml`：

```toml
schema = "paperkit-fact/3.0"

[[fact]]
id = "A1"
claim = "On assembly, the resolved rate is 62.5%."
value = "62.5%"
display = ["62.5\\%"]
quantitative = true
role = "results"
run_id = "run-01"
source = "runs/run-01/result.json"
observation = { run_id = "run-01", pointer = "/summary/on_resolved" }
source_sha256 = "sha256:4b250136cab46bfdd9d94b8136247b0700e2eb93783ae3bf1c1e62b5f8746a5a"
```

`runs/run-01/result.json`：

```json
{"run_id": "run-01", "summary": {"on_resolved": 0.625}}
```

`runs/run-01/record.json`（回执，与运行记录同目录）：

```json
{
  "run_id": "run-01",
  "source": "runs/run-01/result.json",
  "source_sha256": "sha256:4b250136cab46bfdd9d94b8136247b0700e2eb93783ae3bf1c1e62b5f8746a5a",
  "facts": ["A1"]
}
```

> 示例里的 `source_sha256` 必须按 `result.json` 的实际字节重算后写死；照抄示例哈希而文件不同 → `SOURCE_SHA256_MISMATCH`。

`sections/main.tex`：

```tex
\documentclass{article}
\begin{document}
\section{Results}
On assembly, the resolved rate reaches \fact{A1}{62.5\%}~\cite{smith2020}.
\end{document}
```

### 11.6 证据链完整性（写死）

一条 v3 fact 的证据必须连成三节链；**断任一节即红**：

```
facts.source ──①──> runs/ 里的运行记录 ──②──> 回执 runs/<run_id>/record.json ──③──> 账上的 fact id
```

| 节 | 检查 | 通过条件 | 断开的码 |
|---|---|---|---|
| ① 指针 | `facts.source` 非空，解析后是 `runs/` 下的普通文件 | 文件存在 | 无 source/observation → `EVIDENCE_CHAIN_BROKEN`；文件不存在 → `MISSING_SOURCE` |
| ② 内容锚 | `source_sha256` 与文件现算 sha256 相等 | 64 位 hex 相同（`sha256:` 前缀忽略） | 缺 `source_sha256` → `EVIDENCE_CHAIN_BROKEN`；值不符 → `SOURCE_SHA256_MISMATCH` |
| ③ 回执 | 与运行记录**同目录**的 `record.json` 存在、可解析、`run_id` 对齐、`facts[]` 含本 fact id | 全部成立 | `EVIDENCE_CHAIN_BROKEN` |

**`record.json` 唯一规范形态**（与运行记录同目录，如 `runs/run-01/record.json`）：

```json
{
  "run_id": "run-01",
  "source": "runs/run-01/result.json",
  "source_sha256": "sha256:...",
  "facts": ["A1", "A2"]
}
```

- `run_id` 必须等于运行目录名（或 fact 的 `run_id`）。
- `facts[]` 必须列出所有由该运行记录背书的 fact id；列出的 id 必须在账上存在，否则反向指针断。
- `source`/`source_sha256` 若给出，必须与 fact 的 `source`/现算哈希一致。

**唯一映射**：① 的文件存在性用更具体的 `MISSING_SOURCE`，② 的哈希不符用更具体的
`SOURCE_SHA256_MISMATCH`；只有没有更具体码的节点（无 source、缺哈希、缺回执、
run_id 不符、`facts[]` 不含本 fact、反向指针悬空）才统一报 `EVIDENCE_CHAIN_BROKEN`。
不允许同一现象同时出两个码。

**适用范围**：只对 v3 生效；v1 仍走 `results/`＋`MANIFEST.toml` 旧路径，行为不变。
`l0/l1` 也执行本节（源层就能断链），不等到 L2。

**fixture**：`FX-FACT-01`（benign，链完整）、`FX-FACT-02`（断①：无 source）、
`FX-FACT-03`（断②：哈希不符）、`FX-FACT-04`（断③：缺 `record.json`）、
`FX-FACT-05`（断③：`facts[]` 指向不存在的 id）。

---

## 12. 文风闸阶段判断（批 71 增补）

`factscribe style` 在指标之外必须输出 `stage_assessment`，用来决定「要不要给
改写指令」。依据是三轮盲评：文风闸对 LLM 初稿有效（盲评 9/10），对已打磨稿
有害（3–5/24 被盲评判为改写后更差）。

### 12.1 输出

```json
{"stage": "draft|polished", "advice": "rewrite|report_only",
 "reason": "...", "triggers": 3, "cv": 0.52}
```

- `triggers`：触发指标项数（`fired` 的长度），不是 findings 条数；
- `cv`：句长（词/字）标准差除以均值；阶段判断用原始 CV，句数少于
  `uniformity_min_sentences` 时也照算（指标侧的 1.0「不判」哨兵不参与）。

### 12.2 判据（写死）

| 条件 | stage | advice | 输出行为 |
|---|---|---|---|
| `triggers >= 3` 或 `cv < 0.45` | `draft` | `rewrite` | 给逐条改写清单（沿用 V2） |
| `triggers <= 2` 且 `0.45 <= cv <= 0.80` | `polished` | `report_only` | 明确输出「建议不改」 |
| `triggers <= 2` 且 `cv > 0.80` | `polished` | `report_only` | 句长散落不是公式化特征，只报告 |

### 12.3 `--prompt` 约束

`advice=report_only` 时，`--prompt` **只输出一句**：

```text
指标健康，建议不改；强行改写有降低自然度风险
```

不得输出任何逐条改写指令（不得出现 `文件:行 → 改法`、编号条目、「逐条」、
「rewrite」类指令）。`draft` 时保持 V2 行为，输出 ≤400 字的逐条清单。

### 12.4 人读报告

人读报告必须显示阶段（`polished（建议不改）` / `draft（建议改写）`）与判断
理由；`report_only` 下的具体清单标为 `[观察]`，并注明「建议不改，以下只作
报告」。退出码语义不变：无触发 0，有触发 3，永不 1。

### 12.5 验收

- 测试覆盖三种组合（多触发 / 低 CV / 健康稿）各 1 例；
- `report_only` 的 `--prompt` 恰好等于上述一句、不含改写条目；
- 真实基线：`paper/` 与 `paper-zh/` 均判 `polished/report_only`；
- 同一份 `\$` 修复后的基线读数见 `docs/implementation/STYLE-V3.md`。

---

## 13. 文风规则 v4（批 82 增补）

> 本节只约束 `factscribe style` 子命令。**不改 `audit` 的判据与退出码**：文风闸
> 正式判据只出黄牌（exit 3），永不返回 1；参考读数（如默认档的
> `RHYTHM_PLATEAU`）单独列出，不计数、不影响退出码。阈值、档位与词表全部来自
> `style-rules.toml`，改文件即改判定；本节与仓根 `style-rules.toml` 同表。

### 13.0 共同输入与输出

- **输入**：`project.*` 收齐的正文 `.tex`（`load_sections` 闭包）。先经
  `prose_of()` 做等长遮罩：公式、图表、文献表、verbatim、批注宏、引用与
  标题命令都不参与正文统计，但**换行保留**，因此任何位置都能换算回源文件行号。
- **标题规则**（13.2–13.4）单独扫描源文件的 `\part/\chapter/\section/
  \subsection/\subsubsection/\paragraph`，不用遮罩后的正文。`\title{}` 是论文
  主标题，**三条规定全部豁免**。
- **输出**：每条 finding 固定五字段＋严重级别：
  `code / severity / file / line / text / suggestion`。severity 恒为 `yellow`。
  同一位置多条规则各出各的条目。
- **退出码**：无黄牌 0，有黄牌 3，永不 1；`--json` 与 `--prompt` 同步反映同一
  批黄牌（`--prompt` 只列黄牌，且明确不改正文事实）。

### 13.1 `DASH_PARENTHETICAL`（黄）

| 项 | 判据 |
|---|---|
| 输入 | 遮罩后的正文 |
| 算法 | 匹配 `——` 与 `—`（整段 `——` 算一处）；左右最近的非空 token 都是数字（含 `第 3——5 章`）判数值范围，排除；左侧 24 字内出现 `p.`/`pp.`/`page(s)`/`第 N` 且右侧以数字开头判文献页码，排除；数学环境在遮罩阶段已消失 |
| 阈值 | `thresholds.dash_budget`，默认 `0`；出现数 `>` 预算即触发，**逐处报** |
| 误报边界 | 数值范围、文献页码、数学环境里的 `-`/`—` 不报；ASCII `--` 不匹配，永不报 |
| 漏报边界 | 行首/行尾单独一个 `—` 仍按插入语报（保守方向）；无 |
| 对应码 | `DASH_PARENTHETICAL` |
| 建议文案 | 按优先级给三种改法：①改成逗号从属句；②改用括号；③拆成独立一句 |

### 13.2 `HEADING_TOO_LONG`（黄）

| 项 | 判据 |
|---|---|
| 输入 | 源文件的章节标题（`\title{}` 豁免） |
| 算法 | 中文标题按汉字数、英文标题按词数计；混排按汉字多于拉丁词判中文 |
| 阈值 | `thresholds.heading_max_chars_zh` 默认 `12`；`thresholds.heading_max_words_en` 默认 `8`；严格大于才报 |
| 误报边界 | `\title{}` 豁免；标题里的数学/命令参数先剥掉再计数 |
| 漏报边界 | 纯数字标题按中文口径计汉字数（0），不报；无 |
| 对应码 | `HEADING_TOO_LONG` |

### 13.3 `HEADING_MALFORMED`（黄）

| 项 | 判据 |
|---|---|
| 输入 | 源文件的章节标题（`\title{}` 豁免） |
| 算法 | 标题含中文/英文冒号 `：:`、破折号 `——`/`—`、括号解释 `（…）`/`(…)`、问号 `？?`、句号 `。`/英文句点 `.`、叹号 `！!` 即报。标题末尾的英文句点与中文句号同判；LaTeX 的 `\section`/`\subsection`/`\subsubsection`/`\paragraph`/`\subparagraph` 与 Markdown `#` 标题同一口径 |
| 阈值 | 出现即报（单点） |
| 误报边界 | 论文主标题 `\title{}` 除外；连字符 `-`（如 `End-to-End`）不算破折号；标题以常见缩写结尾时不判句点（批量 112）：`al.`、`e.g.`、`i.e.`、`vs.`、`etc.`、`Fig.`、`Eq.`、`No.`、`cf.`、`Dr.`、`et al.`，大小写不敏感，表在 `style-rules.toml` 的 `heading_period_exempt` 可覆盖；**行内标题（run-in heading）豁免末尾句点**（批量 113）：LaTeX 惯例把 `\paragraph`/`\subparagraph` 的标题与正文排在同一段、以英文句点分隔，故 `\paragraph{Motivation.}` 合法不报；该豁免只放行末尾 `.`，冒号/问号/括号解释照旧报，`\section` 等非行内标题与 Markdown `#` 末尾句点照旧报。中英两版标题是否统一（中文 `\paragraph{动机}` 不带句点、英文带句点）由作者决定，工具不强制 |
| 漏报边界 | 无标点但语义是问句的标题不报；属启发式接受 |
| 对应码 | `HEADING_MALFORMED` |

### 13.4 `TERM_FIRST_IN_HEADING`（黄，启发式）

| 项 | 判据 |
|---|---|
| 输入 | 源文件的章节标题＋该节首句（标题后第一句正文） |
| 算法 | 从标题抽「术语样」词：中文按 `的/和/与/及/在/对/从/为/是` 切段后取 ≥4 字段；英文取连续非停用词 ≥2 词的短语。候选术语不在该节首句出现即报。大小写不敏感、去首尾空白 |
| 阈值 | 出现即报（单点） |
| 白名单 | 两层：①项目内 `GLOSSARY.md`；②用户自维护的纯文本（默认 `term-allow.txt`，一行一个词）。文件清单由 `term_allow_files` 配置，默认 `["GLOSSARY.md", "term-allow.txt"]`。解析：忽略空行与 `#` 注释行、去首尾空白、大小写不敏感。白名单命中不报 |
| 误报边界 | 只黄不红；无分词器，中文按分隔字粗切；首句包含候选词即视为已定义 |
| 漏报边界 | 标题术语与首句用同义词替换时不报；属启发式接受 |
| 对应码 | `TERM_FIRST_IN_HEADING` |

### 13.5 `RHYTHM_PLATEAU`（默认 info，参考读数）

> 批 109 起默认降为 **informational**。理由有两条，均来自批 108 端到端试跑的实测：
>
> 1. **分桶伪影**：旧判据把句子长度按 10 词（字）分桶，连续 3 句落在同一桶就算
>    「平台」。中英两节基线共 4 条命中，3 条是这种「长度接近」造成的量化假象；
>    四份语料剩余命中也几乎全是它（英文 17/17、中文 12/14）。
> 2. **与正式判据重复**：它与 `SENTENCE_UNIFORMITY`（句长 CV）测的是同一件事，
>    而后者有明确健康区间 `[0.45, 0.80]`，能区分「太平」与「散」。
>
> **节奏的正式判据是 `SENTENCE_UNIFORMITY`**。`RHYTHM_PLATEAU` 保留为参考读数：
> 读数仍在 `metrics.rhythm_plateau`，条目进 `advisories`（人读输出的 `[参考]`
> 区），**不进 findings、不影响退出码、不占黄牌数**。把配置项
> `rhythm_plateau_level` 设为 `"yellow"` 可恢复旧黄牌行为。

| 项 | 判据 |
|---|---|
| 输入 | 段内句子长度序列 |
| 算法 | 同一段连续 ≥N 句长度落在同一 `rhythm_plateau_window` 词区间 |
| 档位 | `rhythm_plateau_level`：`"info"`（默认，参考读数）／`"yellow"`（旧行为，进 findings） |
| 阈值 | `thresholds.rhythm_plateau_run` 默认 `3`；`rhythm_plateau_window` 默认 `10` |
| 误报边界 | 不跨段；短句/长句交界自然打断平台；**分桶伪影与 CV 重复是本条默认降级的直接原因** |
| 对应码 | `RHYTHM_PLATEAU` |

### 13.6 `COLLOQUIAL_TRIAD`（黄，替代旧 `TRIAD_DENSITY`）

| 项 | 判据 |
|---|---|
| 输入 | 相邻段落的句子 |
| 算法 | 只认模板式标记：同一段内按序出现 `首先/其次/最后`、`第一/第二/第三`、`一是/二是/三是`、`其一/其二/其三` 之一，记一次模板式三点并列；按模板系列取指纹，**只有同指纹在相邻段落重复**才计入 |
| 阈值 | `thresholds.colloquial_triad_repeats` 默认 `2`：相邻段落的同构三点并列累计出现 ≥2 次即触发 |
| 误报边界 | 顿号、逗号列举（真实实验条件、约束清单、`A, B, and C`）一律不算；单段单次、非相邻、或模板系列不同不报；列表项整体计数，六条约束不会被截成三条 |
| 漏报边界 | 英文模板式序数（`First/Second/Third`）与中文逗号分隔的模板变体不判；接受 |
| 对应码 | `COLLOQUIAL_TRIAD` |

### 13.7 `CONNECTIVE_DENSITY`（黄，保留）

| 项 | 判据 |
|---|---|
| 输入 | 遮罩后正文的句子 |
| 算法 | 句首/分句首的套话连接词（`connectives` 表）计数，按每千词（字）折算密度 |
| 阈值 | `thresholds.connective_density` 默认 `8.0`，严格大于才报 |
| 误报边界 | 句中定语用法（`overall accuracy`）不算；大小写不敏感 |
| 对应码 | `CONNECTIVE_DENSITY` |

### 13.8 `EMPTY_ADJECTIVE`（黄，保留）

| 项 | 判据 |
|---|---|
| 输入 | 遮罩后正文的句子 |
| 算法 | `empty_adjectives` 表中的空泛形容词计数，每千词（字）折算密度；`exempt_phrases` 内的搭配排除 |
| 阈值 | `thresholds.empty_adjective` 默认 `6.0`，严格大于才报 |
| 误报边界 | `statistically significant`、`robust standard error` 等术语搭配不报 |
| 对应码 | `EMPTY_ADJECTIVE` |

### 13.9 `SENTENCE_LENGTH_EXTREME`（黄，保留窄版）

| 项 | 判据 |
|---|---|
| 输入 | 单句长度 |
| 算法 | 英文 >60 词或中文 >110 字，**且句内无任何断点**（从句引导词、分号、破折号、括号等）才报 |
| 阈值 | `thresholds.sentence_length_extreme_en` 默认 `60`；`..._zh` 默认 `110` |
| 误报边界 | 长而有结构的句子是专家写法，不报 |
| 对应码 | `SENTENCE_LENGTH_EXTREME` |

### 13.10 阈值总表（与 `style-rules.toml` 同表）

| TOML 键 | 类型 | 默认 | 服务规则 |
|---|---|---|---|
| `thresholds.dash_budget` | 非负整数 | `0` | `DASH_PARENTHETICAL` |
| `thresholds.heading_max_chars_zh` | 非负数字 | `12` | `HEADING_TOO_LONG` |
| `thresholds.heading_max_words_en` | 非负数字 | `8` | `HEADING_TOO_LONG` |
| `thresholds.colloquial_triad_repeats` | 非负数字 | `2` | `COLLOQUIAL_TRIAD` |
| `thresholds.rhythm_plateau_run` | 非负数字 | `3` | `RHYTHM_PLATEAU` |
| `thresholds.rhythm_plateau_window` | 非负数字 | `10` | `RHYTHM_PLATEAU` |
| `thresholds.connective_density` | 非负数 | `8.0` | `CONNECTIVE_DENSITY` |
| `thresholds.empty_adjective` | 非负数 | `6.0` | `EMPTY_ADJECTIVE` |
| `thresholds.sentence_length_extreme_en` | 非负数字 | `60` | `SENTENCE_LENGTH_EXTREME` |
| `thresholds.sentence_length_extreme_zh` | 非负数字 | `110` | `SENTENCE_LENGTH_EXTREME` |
| `rhythm_plateau_level` | 字符串 | `"info"` | `RHYTHM_PLATEAU`（`"yellow"` 恢复黄牌） |
| `term_allow_files` | 字符串数组 | `["GLOSSARY.md", "term-allow.txt"]` | `TERM_FIRST_IN_HEADING` |

`thresholds` 里出现未知键不报错（向前兼容）；已知键必须是数字且非负，否则
`CONFIG_INVALID`（exit 2）。

### 13.11 不采用（写死，避免后人再加）

以下五条在 v4 评审中被明确否决，**不得再实现**：

1. **排比限两项**——三项并列本身不是问题，重复的同构排比才是（13.6）。
2. **冒号只许引原话**——冒号在正文里可合法引出列表或定义。
3. **长句必拆**——长而有结构的句子是专家写法（13.9）。
4. **标题数量限制**——章节数量由论文结构决定，不是文风指标。
5. **引用式长标题白名单**——已撤销，改由用户自维护 `term_allow_files` 处理。

### 13.12 验收

- `tests/test_style_v4.py`：每条规则至少 3 例（正例/负例/白名单或豁免例）；
- 阈值来自 `style-rules.toml` 的验证（改阈值即改判定）；
- `dash_budget` 调大后不再报；数值范围 `1--2`、文献页码、数学环境里的 `-` 不计；
- 标题术语命中白名单不报；
- `python3 -m unittest discover -s tests` 与 `./scripts/preflight-ci.sh` 全绿。

---

## 14. 改写保护面（批 83 增补）

> 本节只约束 `factscribe protect` 子命令。**不改 `audit` / `style` 的判据与
> 退出码**。用途：文档被改写（换句、润色、重排）之后，机械比对「不许变」的
> 内容有没有被动过——凡保护面上的东西变了就报红，只改措辞则全绿。

### 14.1 命令

```bash
python3 -m factscribe protect --before <目录A> --after <目录B> [--json] [--allow-renames]
```

两个目录各自递归收集 `*.tex`（跳过隐藏目录与隐藏文件），按相对路径配对比较。
不做配置加载：保护面是独立旁路，不要求项目里有 `paperkit.toml`。

### 14.2 保护面（硬，变了即红）

| 项 | 抽取规则 | 码 |
|---|---|---|
| 事实标记 | 全文 `\fact{...}` 的 id 多重集（含 `[[fact:...]]`；注释/verbatim/批注宏里的不算） | `PROTECT_FACT_CHANGED` |
| 数字 | 与 `audit` 同一 tokenizer（`texscan.scan_tex` → `_extract_numbers`）抽出的数字多重集，按 `number_key` 归一（`1,234` ≡ `1234`，`53k` ≡ `53000`，`62.5\%` ≡ `0.625`） | `PROTECT_NUMBER_CHANGED` |
| 引用 | `\cite`/`\citep`/`\citet`/`\citealp`/`\citeauthor`/`\nocite` 等 cite 家族命令的 key 多重集 | `PROTECT_CITE_CHANGED` |
| 公式 | 行内 `$...$`、`$$...$$`、`\[...\]`、`equation/align`（含星号）环境的内容哈希；内容**去掉全部空白**后做 sha256 | `PROTECT_MATH_CHANGED` |
| 表格 | `tabular`（含 `tabular*`）环境里每一行的单元格数 + 行内容哈希（单元格按 `&` 切分、去空白后哈希） | `PROTECT_TABLE_CHANGED` |
| 交叉引用 | `\label{}`／`\ref{}`／`\eqref{}` 的 key 集合，按命令分别比较 | `PROTECT_LABEL_CHANGED` |

多重集（multiset）判等：同一数字/标记写两次，删掉一次也算变；集合语义的
交叉引用只判「键在不在」，不判出现次数。

### 14.3 软面（黄）

| 项 | 抽取规则 | 码 |
|---|---|---|
| 章节标题文字 | `\part`/`\chapter`/`\section`/`\subsection`/`\subsubsection`/`\paragraph` 的标题文字按出现顺序配对；标题层级不同或数量不同不判重命名 | `PROTECT_HEADING_RENAMED` |
| 文件集合 | 相对路径下 `.tex` 文件的新增/删除 | `PROTECT_FILE_SET_CHANGED` |

- 标题变化默认**黄**；带 `--allow-renames` 时降为**信息**（不进黄计数）。
- 新增/删除文件恒为黄（改名等于一删一增，也报）。

### 14.4 判定与输出

- 任一条红 → exit 1；只有黄 → exit 3；全同（或只剩信息）→ exit 0。
- 每条发现必须给 `文件:行: 多/少/改成了什么`，不许只报总数。行号规则：
  - 「改成了」用**改写前**位置，消息里注明改后行号；
  - 「多出」用改写后位置；「少了」用改写前位置。
- 人读输出每行形如：

```text
[红] PROTECT_NUMBER_CHANGED sections/03.tex:12: 数字 "53" 改成了 "54"（改后第 12 行）
[黄] PROTECT_HEADING_RENAMED sections/03.tex:5: 标题 "Experiments" 改成了 "Evaluation"（改后第 5 行）
```

- `--json` 的 `findings[]` 固定字段：`severity / code / file / line / message /
  before / after`；顶层给 `before/after/summary/exit`。
- 目录不存在或不是目录 → `CONFIG_INVALID`（exit 2），不许当成「全同」。

### 14.5 误报边界（写死）

- 只改标点、断句、换行、空格、同义措辞 → 全绿（公式内容哈希去空白，数字按
  `number_key` 归一）。
- 注释、verbatim、`\pkignore`/`\todo` 等批注宏里的内容不参与保护面。
- 表格只读 `tabular` 家族；`booktabs` 的横线命令不产生单元格。
- 数字保护面会把表格 cell、公式里被 `audit` 抽到的数字一并计入；这是
  「多报不漏报」的保守方向，确属改写噪声时用 `--allow-renames` 只降标题，
  不降数字。
- `\multicolumn` 的跨列不折成实际列数；单元格数按 `&` 切分（保守方向）。

### 14.6 验收

- `tests/test_protect.py`：六条硬保护面各 1 正 1 负；只改标点全绿；改一个
  数字报位置；`\fact{A1}`→`\fact{A2}` 报；加表行报；文件增删黄；
  `--allow-renames` 时标题变化不黄。
- `python3 -m unittest discover -s tests` 与 `./scripts/preflight-ci.sh` 全绿。

---

## 15. 改写后复检（批 87 增补）

> 本节只约束 `factscribe style` 子命令。**不改 `audit` / `protect` 的判据与退出码**；
> 新增规则全部黄牌，退出码仍只有 0（无新违规）与 3（有黄牌），永不返回 1。
> 起因：批 84 用 v4 规则改写两篇论文，盲评发现 6 处退步。v4 的 `TERM_FIRST_IN_HEADING`
> 只查「词在不在首句」，于是**复述标题、加垫话、删关系词**都能过关；v4 也没有
> 「这次编辑引入了什么新病」的回路。

### 15.0 共同输入与输出

- 输入同 §13.0：`prose_of()` 等长遮罩后的正文；标题规则单独扫描源文件标题。
- **首句**＝标题结束后第一个非空句子。标题若没有自己的正文（下一节标题先出现），
  本节不判 `HEADING_ECHO`；行内 `\paragraph` 与首句同在一行时仍算本节正文。
- **改写前目录**：`style <after> --diff <before>`。`before` 必须是可加载的
  paperkit 项目（含 `paperkit.toml`），相对路径按当前工作目录解析；缺失或坏配置
  → `CONFIG_INVALID`（exit 2）。
- 每条 finding 固定六字段：`code / severity / file / line / text / suggestion`；
  severity 恒为 `yellow`。

### 15.1 `HEADING_ECHO`（黄）

| 项 | 判据 |
|---|---|
| 输入 | 该节标题＋标题后第一个非空句 |
| 算法 | 取首句实义词减去标题实义词、再减去 `[heading_echo]` 的泛化词，得到「新实义」；数量 `< heading_echo_min_new_terms` 即报。英文按词（大小写、所有格、常见复数归一），中文按字（先删停用短语/停用字与泛化词）。另两种伪满足直接报：①首句以标题开头后紧跟垫话（中文 `里/中/方面/来说/而言/要先/先要/先问/首先要/需要先/本节讨论/这里讨论…`；英文 `is about/is concerned with/is discussed/we discuss/this section/here we…`）；②纯设问（「什么是 X？」这类没有新实义的设问，会先被上面的阈值分支抓住） |
| 阈值 | `thresholds.heading_echo_min_new_terms` 默认 `1`；严格小于才报 |
| 误报边界 | 真正的定义式/断言式首句会引入新实义，不报；例：「预注册是在收集数据前固定假设与分析计划的做法」「Preregistration is fixing the hypotheses and the analysis plan before data collection」 |
| 漏报边界 | 同义改写或用代词替换标题词时不报；属启发式接受 |
| 对应码 | `HEADING_ECHO` |
| 建议文案 | 「首句只是复述标题；改成一句定义或可检验的断言（例：预注册是在收集数据前固定假设与分析计划的做法）。复述标题、垫话（「相关工作里，」）与设问都不算定义。」 |

泛化词（`[heading_echo] generic_terms_en/generic_terms_zh`）只用于「新实义」计数，
例如 `limitations` / `限制` 不算新实义；标题本身仍然保留这些词。

### 15.2 `TERM_FIRST_IN_HEADING` 文案修订（判定逻辑不变）

- **删除**旧建议里的 `本节讨论 X` 范例——它本身就是复述式，会教模型写垫话。
- 定义式范例改为：「预注册是在收集数据前固定假设与分析计划的做法」。
- 建议文案**明写禁止三种伪满足**：复述标题、垫话（「相关工作里，」）、设问。
- 判定逻辑（术语抽取、首句包含、白名单、单点阈值）不变；复述式首句由
  §15.1 的 `HEADING_ECHO` 接手报黄。

### 15.3 `HEADING_RELATION_CHANGED`（黄，需 `--before`）

| 项 | 判据 |
|---|---|
| 输入 | 改写前/后的标题，按文件、按标题出现顺序配对；命令层级（`\section`/`\subsection`…）不同则不配对 |
| 算法 | 从标题抽**对立关系词**集合（`heading_relation_words`，默认 `versus / vs / not / without / 对 / 而非 / 不是`；英文按词边界，中文按结构）。旧集合里有词在新集合中不存在（被删除或被替换）→ 报。只新增（旧集合为空）不报；标题文字完全未变则不判。同组同义关系词归一后比较（比较组 `versus/vs/对`、否定组 `not/不是`、排除组 `without/而非`）。 |
| 阈值 | 出现即报（单点） |
| 误报边界 | 只改措辞、保留原关系词不报；删除 `and / or / 与 / 及 / 、` 这类**并列连接**不报（它们不承载对立关系）；中文 `对` 只认「A 对 B」里的介词，`对照 / 针对 / 面对 / 对比 / 对于 / 相对 / 绝对` 等词内部不报；标题层级/数量变化时不强行配对 |
| 漏报边界 | 同组同义关系词互换（比较组 `versus / vs / 对`；否定组 `not / 不是`；排除组 `without / 而非`）不报；跨组替换（如 `versus`→`not`）仍报；启发式接受 |
| 对应码 | `HEADING_RELATION_CHANGED` |

### 15.4 `HEADING_SUBJECT_LOST`（黄，需 `--before`）

| 项 | 判据 |
|---|---|
| 输入 | 改写前/后的标题＋改后该节首句 |
| 算法 | **只在旧标题本身是对比结构时启用**：英文 `X versus/vs Y`；中文 `X 对 Y`、`X 与 Y 对比/相比/比较`、`X 而非 Y`、`X 不是 Y`。抽对比双方的**对象实义成分**：中文按分隔字切段（去停用字/短语与泛化词，保留 ≥2 字段），英文按词（去停用词/泛化词/关系词，轻量复数归一，保留 ≥2 字符）。某对象在新标题与改后首句里**都不出现** → 报。序数词（`one/two/three/four`、`一二三四`）、单字词、对比结构之外的修饰语一律忽略。标题文字完全未变则不判 |
| 阈值 | 出现即报（单点；一个标题一条，列出全部丢失对象） |
| 误报边界 | 非对比标题（并列连接、普通名词短语）不报；对象在新标题保留、或在新首句里写回来，都不报；改写前目录缺失时不运行 |
| 漏报边界 | 同义词替换（`机制`→`机理`）不报；启发式接受 |
| 降级说明 | **不降为 `info`**：它与 §15.3 不完全重合——关系词可以保留而对象被换掉（如 `A versus B` → `A versus C`），此时只有本条能报 |
| 对应码 | `HEADING_SUBJECT_LOST` |

### 15.4b `HEADING_SUBSTITUTED`（黄，需 `--before`）

只抓「旧标题冒号 → 标点/介词 token，其余逐字不动」的伪装改写。旧标题含
冒号、新标题不含冒号，且把冒号换成 `、` / `，` / `,` / `（` / `）` 之一后
逐字相同，或换成 `as` / `with` / `for` / `of` 之一后相同（大小写不敏感）
即报；真重写、删类别词、删句号、除冒号外还改了别的词都不报。完整判据、
不报边界与真实读数见 `docs/design/SPEC-SYNTAX-C.md`。与手册第 8 条
「禁止换标点过关、也禁止换介词过关」同源。对应码 `HEADING_SUBSTITUTED`。

### 15.5 `style --diff <before 目录>`

| 项 | 判据 |
|---|---|
| 命令 | `factscribe style <after> --diff <before> [--json] [--rules …]` |
| 算法 | 先按常规跑改后全文，再按同一规则跑改前全文；按 `(code, file, 规范化 text)` 做**多重集差**，只留下改后多出来的条目。改前有、改后同样有 → 不报；改前有、改后更多 → 只报多出来的条目 |
| 输出 | `findings/fired/summary/exit_code` 都以「新增」为准；改后全文指标仍原样输出；`--json` 顶层多一个 `diff` 块：`{"before": "...", "baseline_findings": N, "new_findings": M}` |
| 退出码 | 无新增 → 0；有新增 → 3；永不 1 |
| 兼容 | **不传 `--diff` 时行为与 v4 完全一致**（除 §15.1/§15.2 的新增与文案）；`HEADING_RELATION_CHANGED`、`HEADING_SUBJECT_LOST` 与 `HEADING_SUBSTITUTED` 只在传 `--diff` 时运行 |

### 15.6 明确不实现（写死）

1. **标题语义相似度模型**——需要向量/模型，违背零 LLM 与可机械复算。
2. **LLM 判分**——不引入任何模型调用；本闸保持离线、确定性。

### 15.7 阈值总表（与 `style-rules.toml` 同表）

| TOML 键 | 类型 | 默认 | 服务规则 |
|---|---|---|---|
| `thresholds.heading_echo_min_new_terms` | 非负整数 | `1` | `HEADING_ECHO` |
| `heading_relation_words` | 字符串数组 | `["versus","vs","not","without","对","而非","不是"]` | `HEADING_RELATION_CHANGED` |
| `heading_echo.generic_terms_en` | 字符串数组 | 见 `style-rules.toml` | `HEADING_ECHO` |
| `heading_echo.generic_terms_zh` | 字符串数组 | 见 `style-rules.toml` | `HEADING_ECHO` |
| `heading_echo.meta_openers_en` | 字符串数组 | 见 `style-rules.toml` | `HEADING_ECHO` |
| `heading_echo.meta_openers_zh` | 字符串数组 | 见 `style-rules.toml` | `HEADING_ECHO` |
| `heading_substitute.punctuation` | 字符串数组 | `["、","，",",","（","）"]` | `HEADING_SUBSTITUTED` |
| `heading_substitute.prepositions` | 字符串数组 | `["as","with","for","of"]` | `HEADING_SUBSTITUTED` |

### 15.8 验收

- `tests/test_style_v5.py`：四条新判据各 ≥3 例（正例/负例/边界）；
- 批 84 的 6 个真实退步（EN-06、EN-10、ZH-04、ZH-06、ZH-08、ZH-09）各一个
  3–5 行 LaTeX 最小复现夹具，断言被对应规则抓到；
- 真正的定义式首句（中英各一）不被 `HEADING_ECHO` 报；
- `--diff`：改前改后都不违规 → 不报；改前有、改后更多 → 只报新增；CLI 退出码 0/3；
- 阈值可配：`heading_echo_min_new_terms`、`heading_relation_words` 改文件即改判定；
- 对 `/tmp/v4-regen/en` 与 `/tmp/v4-regen/zh` 跑 `--diff` 能抓到上述 6 例；
  v5b 收紧后，两条复检规则的新增告警从 EN 8 / ZH 15 降到 EN 2 / ZH 5
  （EN ≤4、ZH ≤6）；`paper/`、`paper-zh/`、`paper-b/`、`paper-b-zh/` 原文
  三条新码全 0；
- 「排除并列连接删除 / 非对比标题不判对象丢失」的负例锁：`Debug log`、
  `Invariants`、`Attribution`、`容量假设` 等实例不再报；
- `python3 -m unittest discover -s tests` 与 `./scripts/preflight-ci.sh` 全绿。

---

## 附录 A｜V2.2 → V3.0 差异速查

| 主题 | V2.2 | V3.0 |
|---|---|---|
| PDF 文本 | 单页/单向包含 | 每页下限＋双向多重集＋白名单计数 |
| PDF 图片 | 声明「不做 OCR」 | 声明＋计数＋页面栅格阈值；正文禁内联图 |
| stamp | PDF 元数据＋自洽哈希；advisory | PDF 外签名文件＋项目外公钥；阻断 |
| report 出处 | 未要求 | stamp 签 `report_sha256/rules_sha256/assertions_digest` |
| 人签对象 | 值＋上下文哈希 | 值＋断言（句子指纹/角色/anchor/pair）＋input_set＋nonce |
| 私钥 | 未规定 | 写死文档边界＋`signing_mode`；工具不签名 |
| rules 哈希 | 配置 | 配置＋规则模块＋常量；发布签名 |
| 夹具 | 36 个构造写在正文 | 只写判据；公开回归＋封存盲测 12 项目 |
| 通过标准 | 36 全绿 | 盲测 ≥80%＋关键族＋FP≤2%＋unknown code=0 |
| 攻击账 | 无 | `ATTACKS.md`＋`expires`＋exit 9 |

## 附录 B｜本机可复现的最小验收（实施后）

```bash
cd paperkit-dev
PK_TMP="$(mktemp -d)/pk-paper"; cp -R paper "$PK_TMP"   # paper/ 只读，写只发生在副本
python3 -m unittest discover -s tests -v
python3 tools/fixture_lint.py --strict
python3 tools/coverage_matrix.py --fail-on-gap
python3 tools/benign_probe.py --corpus paper+mutants --max-fp 0.02
python3 tools/golden.py --verify tests/golden/v1
python3 factscribe.py audit --level l2 --gate "$PK_TMP"
python3 factscribe.py release "$PK_TMP" --keys "$HOME/.config/paperkit/approver_keys.json"
python3 factscribe.py verify-pdf "$PK_TMP/main.pdf" \
  --report "$PK_TMP/audit/report.json" --stamp "$PK_TMP/audit/stamp.json" \
  --keys "$HOME/.config/paperkit/approver_keys.json"
python3 tools/blind.py --holdout "$PAPERKIT_HOLDOUT" --report holdout-report.json
python3 tools/spec_lint.py --no-construction
```

预期：前六条退出 0；`release`/`verify-pdf` 退出 0 且 `verdict=PASS`；`blind` 总命中 ≥10/12 且关键族各 ≥1；`spec_lint` 退出 0。任一不符，按对应阶段回炉，不得改判据凑绿。
