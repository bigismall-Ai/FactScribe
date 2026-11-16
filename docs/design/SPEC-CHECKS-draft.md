# SPEC-CHECKS｜核验槽（check contract）修约稿

> 状态：**修约稿（draft，候批）**。本稿是用户裁定四步计划（①合入法律集成件 →
> ②起草本修约稿 → ③论文三闸行为锁死重构进核验槽 → ④法律作为第二个核验包挂槽）
> 的第②步产物，候用户过目；**未批不动 CHANGELOG、不冻结、不合入 main**。
> 起草：G 席，2026-11-16。
>
> 一句话：**内嵌闸＝core 只造一个统一的核验槽；各领域交自己的核验逻辑进槽；
> 论文不是一等公民——它只是第一个交卷的领域（`paper` 包）；法律是第二个（`legal` 包）。**

---

## 0. 一句话

现在的 factscribe 把「论文」的核验逻辑焊死在 core 里（`audit`/`check` 就是论文三闸），
法律维度只能作为旁挂的第三方件单独跑、单独出报告。本稿把方向修约为：

> **core 只保留宪法与一个核验槽；每个领域交一个「核验包」进槽——
> 包声明自己的码表、配置节、材料依赖与 `verify()`；core 统一收发现、统一折算退出码、
> 统一报告信封。论文闸重构为第一个核验包，法律闸注册为第二个。**

---

## 1. 目的与非目标

### 1.1 目的

1. **把「核验」从「论文专属」泛化为「领域可插拔」**：core 宪法只保留最矮的一层
   （§2），一切领域判据走核验槽（§3）。
2. **单命令双域报告**：`factscribe audit` 一次跑完已启用的核验包，一份报告、
   一套退出码（M2，§7）。
3. **机制可反哺**：法律域实证出的器官（语料视图冻结、参考日、两级证据）按实证
   结果择机升 core 通用器官（M3，§7），而不是永远留在域内自生自灭。
4. **兼容不破**：老项目无 `[checks]` 节＝现状行为逐字节不变（§5.2）；
   退出码值永不变化；既有码表一字不改（§4）。

### 1.2 非目标（写死，避免跑偏）

- **不吸收领域抓取器／解析器／改账函数进 core**。法律的 `fetch`（官方件取件）、
  法文数字词解析、`mark_dup_ok`（改账）都留在核验包内；core 不知道任何法域。
- **不做「零级纯外挂维持论」**（法律永远旁挂、两份命令两份报告）——此路线已否决，
  否决理由与例外边界见 §8.2（B 案）。
- **不做 LLM 判据**。核验槽只收纯机械、确定性的 `verify()`；任何模型调用都在槽外，
  与本契约无关（沿用 SPEC.md §5 硬性要求：纯标准库、离线缺省、无 LLM）。
- **不改既有公共 API**：既有退出码值、既有违规码名与语义、既有冻结件字节、
  `factscribe.toml` 形态判定七步（CONFIG-CONTRACT §3）全部不动。
- **不做跨域语义仲裁**。core 只折算退出码，不裁决「paper 说绿、legal 说红听谁的」——
  各域各报各的发现，读报告的人自己合议。绿的含义仍按域各自写死在各自码表的
  「边界」行里（先例：INTEGRATION-LEGAL §3 每闸一条「绿不代表……」）。

---

## 2. core 宪法：四样现状确认 ＋ 核验槽（新增）

### 2.1 现状确认（四样现存宪法级机构）

| # | 宪法级机构 | 现状落点 | 本稿是否改动 |
|---|---|---|---|
| 1 | **只追加事实账＋指纹钉版** | `facts/*.toml` 只追加、改事实＝新增＋`supersedes`（SPEC-V3.0 §11）；`source_sha256` 现算比对（SPEC-V1 §3.3）；`attestation.facts_sha256`（SPEC-V1 §5）；`audit/evidence.lock` 的 `canonical_sha256` | 不动 |
| 2 | **报告信封与退出码语义** | `issues/warnings/hints/summary` 信封（SPEC-V1 §5）；退出码唯一权威表（SPEC-V3.0 §2.5）；「退出码与违规码是公共 API，不随 major 不变」（CHANGELOG 头部原文） | 只增键（§3.2），不改名不删键 |
| 3 | **证据冻结机构** | `[evidence]` → `audit/evidence.lock`（canonical sha256，同输入同哈希）；解冻走只追加日志 `audit/evidence-log.ndjson`（SPEC-EVIDENCE-STAMP §8/§9；`factscribe/evidence.py::canonical_form/canonical_sha256/append_log`） | 推广为多域可用（§6），既有冻结件字节不破坏 |
| 4 | **单一实现不变量（纪律面）** | `canon()` 只有一份；`TOKEN_REGISTRY` 只有一份，报告里的码必须查得到，否则 `UNKNOWN_CODE`（exit 4）（SPEC-V3.0 §2.6） | 不动，并延伸到核验槽（§4） |

> 计数注：用户裁定口径「core 宪法只保留四样＝事实账＋指纹钉版、报告信封与退出码、
> 证据冻结机构、核验槽接口」。上表第 4 样（单一实现不变量）按本稿行文单列是为了
> 现状可对照；**终稿四样定数以裁定口径为准**——单一实现不变量作为贯穿前三样的
> 实现纪律，不占宪法位数。

### 2.2 核验槽接口（新增的宪法面）

core 新增且仅新增一个机构：**核验槽（check slot）**。槽只做四件事：

1. **点名**：按 `[checks]` 配置决定本次跑哪些核验包（§5）；
2. **收发现**：调用每个包的 `verify(project, facts, evidence) → findings`（§3），
   把 findings 按信封形状收拢；
3. **折算退出码**：按 §2.5 权威表统一折算（任一包红 ⇒ 1；仅黄 ⇒ 3；……），
   包自身不产生退出码；
4. **出报告**：一份信封、按域分节（§3.2）。

槽之外的一切判据逻辑都不在 core：**论文三闸从此是 `paper` 核验包的实现细节，
core 不再为任何具体领域保留判据代码**（M1 重构后的终态）。

---

## 3. 核验包契约

### 3.1 注册形状（一张卡写死五样）

每个核验包向槽注册一张卡，五样缺一不可：

| 项 | 类型 | 约束 | 先例 |
|---|---|---|---|
| `domain_id` | string | 全局唯一小写 id（`paper`、`legal`）；即配置节名与码表命名空间的来源 | 法律件四闸已在用 `LEGAL_`/`CN_`/`CASE_`/`IT_` 前缀分域 |
| **冻结码表** | 文件 | 本域全部 code ＋ severity ＋ 一句触发条件＋一句边界（「绿不代表……」）；冻结后只增不改名不改义（§4） | SPEC-V3.0 §8、CODES-AND-CHAIN §1 |
| **config 节名** | `[checks.<domain_id>]` | 键集由包自己的卡声明；未知键走 `CONFIG_UNKNOWN_FIELD` 告警、不改退出码（CONFIG-CONTRACT §4 纪律） | `[budget]`/`[evidence]` 可选节先例 |
| **出处材料依赖声明** | 清单 | 包声明它消费哪些证据工件（如 legal：`runs/<run>-legal` 语料视图 `index.json`＋官方件＋证据卡＋参考日；paper：facts＋sections＋bib＋manifest/evidence.lock）；**材料缺失必须 fail-closed 出黄/红，不许静默绿**（防「空集伪装全绿」，INTEGRATION-LEGAL §6） | `LEGAL_COVERAGE_GAP`/`IT_VERSION_GAP` 先例 |
| **`verify(project, facts, evidence) → findings`** | 纯函数 | 输入＝项目只读视图＋冻结事实账＋冻结证据集＋本域配置节；输出＝findings 列表（§3.2）；**不许改账、不许写盘、不许联网、不许读系统钟**（参考日等时间输入一律来自配置或材料，先例：`evidence --unfreeze --at`、legal `--date`） | legal 四闸 verify 的现状函数形 |

一个包可含多个子闸（legal 一包四闸 FR/CN/CASE/IT），但**每个子闸的码前缀都在
同一张冻结码表里列明**（§4.3）。

### 3.2 发现形状（与 core 信封对齐）

findings 每条＝信封里一条 issue/warning/hint，字段照 SPEC-V1 §5 的既有形状，
**只增一个键**：

```json
{"domain": "legal", "severity": "red", "code": "LEGAL_QUOTE_MISMATCH",
 "location": "facts/01-fr.toml:14", "token": "…", "context": "…", "message": "…"}
```

- `domain` 是本稿唯一新增的键；旧消费者按「新增键忽略」常规口径不受影响，
  报告 schema 字面量维持 `factscribe-report/3.x` 前缀兼容（CONFIG-CONTRACT §2 口径）。
- `severity` 仍只有 `red|yellow|info` 三值；包不许发明新严重度。
- 人读报告在黄块置顶等既有版式内按域分节；`summary` 增加 `by_domain`
  计数（只增键）。

### 3.3 纯机械、零 LLM、确定性

- **纯机械零 LLM**：verify 内部只许标准库＋确定性算法；不 import 模型 SDK。
- **确定性**：同一输入字节 ⇒ 同一 findings 字节（排序稳定、无系统钟、无随机）。
  这是金样例 fixture 锁（§7 M1）能「逐条相同」的前提。
- **自测纪律**沿用两先例：每条红码「必须触发＋不该触发」双向用例（CONTRIBUTING §5、
  legal 50 例）；防假绿回归（空集不许伪装全绿）。

---

## 4. 码表注册制

### 4.1 每域一张码表、各自冻结

- 每个域一张码表，入册位置：core 自带域在 `docs/design/SPEC-V3.0.md` §8 总表；
  外来域在包内（如 `integrations/factscribe-legal/` 的 README/码表节）并在 §8 总表
  只增一行指针。
- 冻结语义：**只增不改名不改义不改 severity**。先例：CODES-AND-CHAIN 的合并/改名
  （`UNBOUND_QUANT`→`UNBOUND_NUMBER` 等）是 major 级修约动作，本制生效后此类动作
  在域码表上同样要过 §4.4 程序。
- 跨域重码（同一现象两域两码）**允许**：域自治；「现象→唯一 code」映射
  （CODES-AND-CHAIN §1.3）只在域内成立。core 的 `TOKEN_REGISTRY` 只查「code 是否
  注册过、severity/exit 是否与注册一致」，查不到仍 `UNKNOWN_CODE`（exit 4，
  SPEC-V3.0 §2.6 不变量延伸到槽）。

### 4.2 全局退出码值永不变化

- 退出码是**全局唯一**的公共 API：值与语义的配对闭集以 SPEC-V3.0 §2.5 为唯一
  权威表，**永不变化**（CHANGELOG 头部承诺的本稿化）。
- 核验包**不产生退出码**：包只报 findings，退出码由槽按权威表折算
  （任一域红 ⇒ 1；仅黄 ⇒ 3；仅 advisory/配置告警 ⇒ 0 或 3 按 §2.5；配置错 ⇒ 2）。
  法律件现状自带 0/1/2/3 的独立退出码在 M2 挂槽后停用（其语义恰好与折算规则重合，
  无行为跳变；独立子命令保留与否见 §9.6）。
- > 裁定枚举口径为「0/1/2/3/5/7/8 永不变化」；§2.5 权威表另有 4（内部错）/
  > 6（proof）/9（attack open）三值。本稿建议**全闭集入宪**（永不变化的是
  > 「值↔语义配对」），是否收窄按裁定枚举执行，列入 §9.2 候拍板。

### 4.3 跨域码命名空间

- **新入槽域的码必须带域前缀**：`<DOMAIN>_` 开头（`LEGAL_QUOTE_MISMATCH`、
  `CN_PROV_UNKNOWN`、`IT_VERSION_GAP` 均已是此形）。前缀＝`domain_id` 大写，
  一包多子闸时每个子闸的前缀都要在码表冻结（legal 的 `LEGAL_`/`CN_`/`CASE_`/`IT_`
  即为范本）。
- **core 存量码一字不改**（无前缀的 `UNMATCHED_NUMBER` 等照旧）；core 新增码
  建议也走前缀（如 `CORE_`），避免与未来域撞名。

### 4.4 码表冻结的修约程序（默认案，候批）

| 动作 | 级别 | 程序 |
|---|---|---|
| 纯新增码 | minor | 码表追加一行＋CHANGELOG `[Unreleased]/Added` 一行＋双向测试各一例 |
| 改名/改义/改 severity | **major（BREAKING）** | 旧码保留发射一个废弃窗口期或直接随 major 移除；CHANGELOG `**Breaking**` 条目；先例照「protocol literals 硬切」批 |
| 删码（现象消失） | major | 同上 |

---

## 5. 配置：`factscribe.toml` 的 `[checks]` 节

### 5.1 形状

```toml
[checks]
# 点名本次要跑的核验包（顺序无关）；缺省＝只跑 paper
packages = ["paper", "legal"]

# 每包自己的节，键集由该包的卡声明（§3.1）；未知键＝告警不阻断
[checks.legal]
corpus = "runs/run-20261114-legal"     # 语料视图目录（含 index.json）
date   = "2026-11-14"                  # 参考日；不读系统钟
view   = "out/legifrance/view_20261114/merged_current.jsonl"
```

- `[checks]` 是**新增可选顶层节**：不参与 CONFIG-CONTRACT §3 的形态判定七步，
  形态 A/B/C/v1 照旧；v1 老项目同样可以挂 `[checks]`。
- `[checks.legal]` 的键集是 legal 包卡上的契约，不是 core 的；core 只透传该表。

### 5.2 兼容承诺（给老用户的宪法保证）

| 情形 | 行为 |
|---|---|
| **无 `[checks]` 节** | 只跑内建 `paper` 包，**全部行为与现状逐字节不变**（退出码、findings、人读输出逐字节一致）——实现模式照 `[budget]`/`[evidence]` 先例：`checks_defined=False` ⇒ 对应判据不跑、行为与之前完全一致（config.py 批 128/131 注释原文口径） |
| `[checks]` 存在但省 `packages` | 同无节（只跑 paper） |
| `packages` 含未注册域 id | exit 2（CONFIG），报错点名该 id 与已注册域清单 |
| `[checks.<domain>]` 键集错误 | 该域 `CONFIG_UNKNOWN_FIELD` 告警（info），不改退出码；键值非法（如日期格式）按该域卡的 fail-closed 出黄/红 |

---

## 6. 证据冻结机构推广

现状冻结机构只认一种工件：`[evidence]` 的「节 → fact id 清单」
（`canonical_form`＝节名排序＋id 排序去重，`canonical_sha256` 唯一指纹，
锁件 `audit/evidence.lock`，解冻只追加日志）。推广为：

1. **evidence set 允许每维工件**：核验包可声明自己的冻结工件——如 legal 的
   **语料视图 id**（`runs/run-20261114-legal`）、语料索引哈希、参考日。
   包内现状已有等价机制（`index.json` 钉哈希、`OFFICIAL_XML_SHA256` 声明），
   M2 起改挂 core 冻结机构统一登记。
2. **canonical_form 扩展但既有冻结件字节不破坏**：既有「节\tid 清单」的规范化
   形态**一个字节都不改**；新维度**新增自己的锁件与 canonical 形态**
   （如 `audit/evidence-legal.lock`，canonical 形态由 legal 的卡写死），
   不给旧 canonical_form 加新字段。
3. **同一套纪律**：不论域，冻结三件套不变——canonical sha256 同输入同哈希、
   锁件可复核、解冻必须过只追加日志并出 `EVIDENCE_UNFROZEN`；
   冻结集与现状不符仍红 `EVIDENCE_SET_CHANGED`（SPEC-EVIDENCE-STAMP §9 语义全域通用）。
4. M3 视第二域实证，把「域级冻结工件」中已通用的器官（语料视图 id、参考日类型）
   升为 core 冻结机构的内建维度；升法走 §4.4 修约程序。

---

## 7. 迁移计划（M0–M3）

> 用户已裁定「全部要做」四步；本节是四步的工程展开。每步一条行为锁，
> 锁不过不进下一步。

### M0　合入法律件为独立维（已完成）

`integrations/factscribe-legal/` 已按 minifactscribe 先例合入 main
（合并提交 `9cd6a2d`，纯增量不碰核心）：独立子命令、独立码表
（`LEGAL_`/`CN_`/`CASE_`/`IT_`）、50 例离线自测、上游 core 零改动。
它现在的形态＝**第一个候任核验包的实体样本**：本稿 §3 的契约形状就是
照它现有形状总结的，M2 挂槽不需要它改判据，只改注册与入口。

### M1　论文三闸行为锁死重构进槽

- **范围**：论文三闸——数字绑定闸（G1 族：`BOUND_MISMATCH`/`UNBOUND_NUMBER`/
  `UNMATCHED_NUMBER` 等，SPEC-V1 §4）、源头闸（G2 族：sha/清单/回查/证据链）、
  引用闸（G3 族：cite/bib）——从 `factscribe/audit.py` 的 `run_audit`/
  `run_check`/`verify_sources` 重构为 core 自带的第一个核验包 `paper`。
- **行为锁（金样例 fixture 锁）**：重构前先固化「发现清单金样例」——
  `examples/minimal` 与 `fixtures/`（benign/hostile/regression/trust）在
  `audit --json` 下的 findings 逐条（domain 除外，重构前无此键）落成快照；
  **重构前后快照逐条相同**才算过锁。退出码、码表、报告信封三样同锁。
- G5（派生）/G6（覆盖）/G7（闭包）/P 层（PDF 回检）是否随第二批进槽：
  不在 M1 范围，列 §9.5 候拍板。

### M2　legal 注册为第二核验包、单命令双域报告

- legal 按本稿 §3 契约注册（domain_id `legal`、码表冻结、`[checks.legal]` 键集卡、
  材料依赖声明、verify 入口），判据与码表零改动；
- `factscribe audit` 按 `[checks]` 点名单命令跑双域，一份报告按域分节、
  一套退出码（§4.2 折算）；
- 行为锁：legal 挂槽前后，同一测试项目（INTEGRATION-LEGAL §0 的真实项目读数：
  FR 0红/1黄、CN/CASE/IT 0红0黄）的 findings 逐条相同，仅多出 `domain` 键。

### M3　语料视图等器官按第二域实证择机升 core

以 legal 半年实证为准：把双域都需要的器官（域级冻结工件、参考日类型、
材料依赖声明的统一校验）升 core 通用器官；每次升级过 §4.4 修约程序并留
CHANGELOG 痕。哪些升、哪些留域内，届时按实证读数另立裁定稿。

---

## 8. 兼容 / BREAKING 判定表 ＋ 备选方案否决记录

### 8.1 判定表

| 改动 | BREAKING？ | 依据 |
|---|---|---|
| 新增 `[checks]` 可选节及其解析 | 否 | 无节＝现状逐字节不变（§5.2）；可选节先例 `[budget]`/`[evidence]` 均按非 BREAKING 落过 |
| findings 信封新增 `domain` 键、summary 新增 `by_domain` | 否 | 只增键不改名不删键；报告 schema 维持 `factscribe-report/3.x` 前缀兼容 |
| legal 码表入 §8 总表 | 否 | 只增码、带域前缀、与 core 存量码零冲突 |
| 论文三闸重构进槽（行为锁通过） | 否 | 对外可观察行为逐条不变（§7 M1 锁） |
| 退出码任何值或值↔语义配对的改动 | **是** | CHANGELOG 头部承诺；§4.2 |
| core 存量码改名/改义/改 severity/删码 | **是** | 同上＋CODES-AND-CHAIN 先例；须 major |
| 既有冻结件 canonical 形态变更 | **是** | §6 第 2 条；canonical sha256 变＝旧锁全废 |

### 8.2 备选方案否决记录

**A 案：把法律硬编码进 core audit（在 core 里加 `LEGAL_*` 判据）——否。**
理由：① 违反用户裁定的宪法边界（core 只保留四样，不为具体领域留判据；
「论文不是一等公民」的同一逻辑反过来禁止法律成为 core 的特权域）；
② 码表会被焊死：`LEGAL_` 族进 core §8 总表后，法律语料的修约节奏（语料视图
月更、参考日常变）与论文闸的冻结节奏（公共 API、major 才动）绑死；
③ 50 例法律自测并入上游 1356 例发布门，法律语料问题会阻塞论文工具发版，
反之亦然；④ core 从此知道「法条」「法域」，宪法面破洞。

**B 案：法律永久纯外挂（维持 integrations/ 独立子命令，不挂槽）——否。**
理由：① **用户体验**：两条命令（`audit` ＋ `verify`）两份报告两套退出码，
CI 与判卷都要各自合流，「单命令双域报告」做不到；挂槽后一份信封、一套
退出码语义，红即红。② **机制无法反哺 core**：两级证据、语料视图冻结、参考日、
材料依赖声明这些法律域实证出的器官永远留在域内，第三个领域（医学指南、
产品规格……）来时只能从零再造一遍而不是复用；裁定四步里的 M3「择机升 core」
在纯外挂路线下无处着落。③ minifactscribe 先例不适用：它是**移植件**（另一套
运行时搬运输层），legal 是**同一条证据链上的第二个判定维**——共享同一本事实账
与同一个 `source_sha256`，天然该挂同一槽。否决边界：legal 在 M2 前继续按
独立件跑（M0 现状），B 案否决的是「永久」而非「过渡」。

---

## 9. 开放问题清单（候用户拍板）

1. **宪法四样的计数控口**：本稿现状确认列了四样（§2.1，含单一实现不变量）＋
   槽为新增；裁定口径是「四样含核验槽」。建议终稿按裁定口径：四样＝事实账＋指纹、
   信封＋退出码、冻结机构、核验槽；单一实现不变量降为贯穿纪律。**待确认。**
2. **退出码闭集口径**：裁定枚举「0/1/2/3/5/7/8 永不变化」；§2.5 权威表另有
   4/6/9。建议全闭集（值↔语义配对）入宪。**待确认。**
3. **`[checks]` 缺省语义**：节存在但省 `packages` ⇒ 只跑 paper（本稿默认案，
   §5.2）还是要求显式？建议默认案。**待确认。**
4. **码表修约程序**：§4.4 默认案（纯增＝minor；改名/改义/改 severity/删＝major）。
   跨域重码允许（域内唯一映射）是否接受。**待确认。**
5. **G5/G6/G7 与 P 层的归属**：M1 只迁三闸；派生算式、覆盖豁免、闭包、PDF 回检
   留 core 直跑还是作为 `paper` 包第二批进槽？建议 M3 后按实证另裁。**待确认。**
6. **legal 独立子命令的去留**：M2 挂槽后，`python3 -m factscribe_legal verify …`
   保留（供无 factscribe 环境的工程仓单跑）还是随槽收编？建议保留一个废弃窗口。
   **待确认。**
7. **改账函数的定位**：`mark_dup_ok` 类会**改写事实账**（补 `dup_ok = true`）——
   改账是写径不是核验，不该出现在 `verify()` 里。建议定位为独立账务维护工具
   （与 `fact add` 同层），核验包内只读；是否随 M2 一并立卡。**待确认。**
8. **核验包的安装形态**：外来域包走 `integrations/<pkg>/` 入仓注册（建议案，
   沿两先例）还是 pip 命名空间分发。**待确认。**
9. **域级冻结锁件形态**：每域一锁（`audit/evidence-<domain>.lock`，建议案）还是
   一锁多节。建议案利于「既有冻结件字节不破坏」。**待确认。**

---

## 附：本稿引用的仓内文件（起草时点，基线＝main@9cd6a2d）

- `docs/design/SPEC-V1.md` §3/§4/§5（三闸判据、G1–G7、退出码与 `--json` 信封）
- `docs/design/SPEC-V3.0.md` §2.5（退出码唯一权威表）、§2.6（单一实现不变量）、
  §8（错误码总表）、§10（项目配置冻结）、§11.6（证据链）
- `docs/design/SPEC.md` §5（硬性要求：纯标准库、离线、零 LLM）
- `docs/design/SPEC-EVIDENCE-STAMP.md` §8/§9（证据钢印冻结/解冻）
- `docs/implementation/CONFIG-CONTRACT.md`（契约表、别名闭集、形态判定七步、
  未知字段告警纪律）
- `docs/implementation/CODES-AND-CHAIN.md`（码表冻结、合并/改名先例、唯一映射）
- `docs/implementation/INTEGRATION-LEGAL.md`（法律件自我定位、四闸码表、
  边界声明、三条工程纪律）
- `integrations/factscribe-legal/README.md`（第二个核验包的现成样本：
  码表形状、材料依赖、退出码沿用、防假绿自测）
- `integrations/minifactscribe/README.md`（第三方件先例与其适用边界）
- `factscribe/config.py`（`Config` 形状；`[budget]` 批 128 / `[evidence]` 批 131
  「节不出现＝判据不跑、行为与之前完全一致」的兼容先例）
- `factscribe/audit.py`（`run_audit`/`run_check`/`verify_sources`——M1 重构对象）
- `factscribe/evidence.py`（`canonical_form`/`canonical_sha256`/`write_lock`/
  `append_log`——冻结机构推广的底座）
- `CHANGELOG.md` 头部（「exit codes and violation codes are the public API …
  without a major version bump」）

---

*本稿只修约「核验怎么挂槽」，不改「绿＝账有据、据未改、文有绑」的任何一条
域内含义；各域「绿不代表内容为真」的边界声明仍是引用其结论时的必附句。*
