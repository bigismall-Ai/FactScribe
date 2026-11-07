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

**误报**：数学排版 `\frac{10}{16}` 抽成上下两行时无法稳定还原 → 源层 `MATH_FRAC_UNVERIFIABLE` 阻断（P-06），不靠 PDF 层猜。
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
> **执行顺序写死**：P-01（工具）→ **P-08（信任链）** → P-02..P-07（页面与数字）→ P-09（新鲜度）。P-08 失败立即退出，**不得**拿未验签的 `report.json` 继续做允许集判定。

### P-01 工具链与版本

| 项 | 内容 |
|---|---|
| 输入 | `PATH` 上的 `pdftotext`、`pdfinfo`、`pdfimages`；PDF 路径 |
| 算法 | 三个命令 `-v` 均退出 0，且 `pdfimages -list <pdf>` 能输出表头（能力探测）；版本字符串写进报告供审计，不作为判定。逐页文本用 `pdftotext -layout PDF -`，按 U+000C 分页；页数必须等于 `pdfinfo` 的 `Pages`。混合页面尺寸时逐页调 `pdfinfo -f i -l i` 取该页尺寸，取不到则用第一页尺寸并在报告记 `PAGE_SIZE_FALLBACK`（黄） |
| 误报/漏报 | 无（工具存在性）；不同发行版输出格式差异只影响解析，不影响判定，解析失败按工具缺失处理 |
| 失败等级 | `PDF_TOOL_MISSING` → 红/CONFIG，exit 2；`release` 直接拒绝 |
| fixture | `FX-PDF-00`（缺工具，mock PATH）、`FX-PDF-00b`（正常）、`FX-PDF-14`（尺寸回退，黄） |

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

### P-06 源头禁止「用图片承载定量」

| 项 | 内容 |
|---|---|
| 输入 | 源层 AST（`\includegraphics` 位置、所在环境、所在 BU）；`report.number_ledger` |
| 算法 | 1) `\includegraphics` 不在 `figure`/`table` 浮动环境内，且所在 BU 还有其它文字 → `INLINE_IMAGE_IN_TEXT`。2) 浮动体内的图必须有 sidecar（R-06）且进 `coverage.figures`；否则 `FIGURE_UNBOUND`。3) 含绑定 token 的 BU 里出现 `\frac/\dfrac/\tfrac` 且未登记 `project.frac_allow` → `MATH_FRAC_UNVERIFIABLE` |
| 误报/漏报 | 误报：行内小图标（logo、checkmark）→ 登记 `project.inline_images_allow`（签名，逐条带理由）。漏报：数字烧进已声明图的像素；矢量描字（§7-R1） |
| 失败等级 | `INLINE_IMAGE_IN_TEXT`/`MATH_FRAC_UNVERIFIABLE` → 红/FACT，exit 1；`FIGURE_UNBOUND` → 红/COVERAGE，exit 5 |
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

## 8. 注册表增量与 fixture 映射

> V2.2 §19.2 的 code 继续有效（tier/exit 不变），本表只列**新增/改级**。每个 code 必须在 `tests/fixtures/v30/` 有至少一个 hostile 与一个 benign 近邻（T-03）。
> 构建时 `tools/registry_merge.py` 把 V2.2 §19.2 与本表合并成唯一 `TOKEN_REGISTRY`；同 code 不同 tier/exit → 构建失败（以本表为准，V2.2 不另建第二份注册表）。
> 表中 `fixture` 列的是 hostile；对应 benign 近邻用同号加 `b` 后缀（如 `FX-PDF-02b`），由 T-03 强制存在；已有 `b` 的条目另配 `c` 近邻。

### 8.1 新增/改级 code

| code | tier | exit | 规则 | fixture |
|---|---|---|---|---|
| `PDF_PAGE_NO_TEXT` | INTEGRITY | 5 | P-02 | FX-PDF-01 |
| `PDF_PAGE_RASTERIZED` | INTEGRITY | 5 | P-03 | FX-PDF-02 |
| `PDF_IMAGE_UNDECLARED` | INTEGRITY | 5 | P-03 | FX-PDF-03 |
| `PDF_PAGE_IMAGE_DOMINANT` | ADVISORY | 3 | P-03 | FX-PDF-10 |
| `PDF_FIGURE_MISSING` | ADVISORY | 3 | P-03 | FX-PDF-10b |
| `PAGE_SIZE_FALLBACK` | ADVISORY | 3 | P-01/P-03 | FX-PDF-14 |
| `PDF_LEDGER_TOKEN_MISSING` | INTEGRITY | 5 | P-04 | FX-PDF-04 |
| `PDF_UNACCOUNTED_NUMBER` | INTEGRITY | 5 | P-05（由 COVERAGE 改级） | FX-PDF-05 |
| `PDF_STRUCTURAL_BUDGET_EXCEEDED` | INTEGRITY | 5 | P-05 | FX-PDF-06 |
| `PDF_WHITELIST_UNPROVENANCED` | INTEGRITY | 5 | P-05 | FX-PDF-07 |
| `PDF_WHITELIST_UNUSED` | ADVISORY | 3 | P-05 | FX-PDF-08 |
| `INLINE_IMAGE_IN_TEXT` | FACT | 1 | P-06 | FX-PDF-09 |
| `MATH_FRAC_UNVERIFIABLE` | FACT | 1 | P-06 | FX-PDF-11 |
| `CANON_AMBIGUOUS` | ADVISORY | 3 | §2.1 | FX-CANON-03 |
| `CANON_DRIFT` | INTERNAL | 4 | P-07 | FX-CANON-02 |
| `STAMP_MISSING` | INTEGRITY | 5 | P-08 | FX-SIG-01 |
| `STAMP_SIGNATURE_INVALID` | INTEGRITY | 5 | P-08 | FX-SIG-02 |
| `STAMP_KEY_UNTRUSTED` | INTEGRITY | 5 | P-08 | FX-SIG-03 |
| `STAMP_REPORT_MISMATCH` | INTEGRITY | 5 | P-08 | FX-SIG-04 |
| `STAMP_PDF_MISMATCH` | STALE | 7 | P-08 | FX-SIG-05 |
| `STAMP_METADATA_MISSING` | INTEGRITY | 5 | P-08 | FX-SIG-06 |
| `STAMP_NONCE_REUSED` | STALE | 7 | S-04 | FX-SIG-07 |
| `STAMP_TIME_INVALID` | STALE | 7 | S-04 | FX-SIG-21 |
| `STAMP_UNVERIFIED` | **删除** | — | 由上面具体 code 替代 | — |
| `APPROVAL_REPLAY` | FACT | 1 | S-04 | FX-SIG-08 |
| `ASSERTION_DRIFT` | FACT | 1 | S-03 | FX-SIG-09 |
| `APPROVAL_MISSING_ASSERTIONS` | FACT | 1 | S-03 | FX-SIG-09b |
| `APPROVAL_MISSING` | COVERAGE | 5 | S-06 | FX-SIG-23 |
| `APPROVAL_MANIFEST_MISSING` | ADVISORY | 3 | S-05 | FX-SIG-22 |
| `KEY_UNREGISTERED` | FACT | 1 | S-01 | FX-SIG-10 |
| `KEY_REVOKED` | FACT | 1 | S-01 | FX-SIG-11 |
| `KEY_PERMISSION_UNVERIFIED` | ADVISORY | 3 | S-01 | FX-SIG-12 |
| `KEY_PERMISSION_UNSAFE` | FACT | 1 | S-01 | FX-SIG-27 |
| `SIGNING_MODE_UNSAFE` | FACT | 1 | S-02 | FX-SIG-13 |
| `SIGNING_API_PRESENT` | CONFIG | 2 | S-02 | FX-SIG-26 |
| `NUMERIC_MACRO_SHAPE_INVALID` | FACT | 1 | S-08 | FX-SIG-14 |
| `NUMERIC_MACRO_DOUBLE_SIGN` | FACT | 1 | S-08 | FX-SIG-15 |
| `NUMERIC_MACRO_EXPIRED` | FACT | 1 | S-08 | FX-SIG-24 |
| `TOOL_MODIFIED` | CONFIG | 2 | S-09 | FX-SIG-16 |
| `TOOL_UNATTESTED` | ADVISORY | 3 | S-09 | FX-SIG-17 |
| `RELEASE_TOOL_UNATTESTED` | INTEGRITY | 5 | S-09 | FX-SIG-17 |
| `APPROVAL_BATCH_CRITICAL` | FACT | 1 | S-07 | FX-SIG-20 |
| `FIXTURE_COVERAGE_GAP` | CONFIG | 2 | T-03 | FX-FIX-02 |
| `XFAIL_EXPIRED` | CONFIG | 2 | T-04 | FX-FIX-03 |
| `FIXTURE_SPECIAL_CASE` | CONFIG | 2 | T-04 | FX-FIX-08 |
| `UNKNOWN_CODE` | INTERNAL | 4 | §2.6 | FX-FIX-06 |
| `ATTACK_OPEN_BLOCKING` | ATTACK | 9 | T-08 | FX-FIX-07 |
| `REPORT_SCHEMA_INVALID` | CONFIG | 2 | S-10 | FX-SIG-25 |

### 8.2 被删除的规则

| 旧 code | 处理 | 原因 |
|---|---|---|
| `LEDGER_TEXT_COCHANGE` | 删除 | 启发式阈值可规避、方向可反；见 §1.2 M2 |
| `STAMP_UNVERIFIED` | 删除，拆成 `STAMP_*` 具体 code | 一个 code 同时表示「没验」与「验不过」无法分诊 |

### 8.3 fixture 总表（实现时按此建目录）

| 组 | 编号 | 覆盖 |
|---|---|---|
| PDF | FX-PDF-00..14 | P-01..P-10 |
| 归一化 | FX-CANON-01..03 | §2.1、P-07 |
| 签名 | FX-SIG-01..27 | S-01..S-10、P-08 |
| 治理 | FX-FIX-01..10、FX-PROP-01..05 | T-01..T-09 |
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

**v1 兼容（不改）**：`[project]` 里 `sections` 是**字符串 glob** 且配了 `facts`
＝ v1，`root_tex` 被忽略，行为与 V2.2 完全一致。v3 的 `sections` 不允许 glob。

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
