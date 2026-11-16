# SPEC-CHECKS｜核验槽（check contract）

> 状态：**已批（2026-11-16 用户裁定九条建议）**。本稿前身为修约稿
> （draft，候批，commit `8c75695`），是用户裁定四步计划（①合入法律集成件 →
> ②起草本修约稿 → ③论文三闸行为锁死重构进核验槽 → ④法律作为第二个核验包挂槽）
> 的第②步产物；2026-11-16 用户对稿内九条开放问题逐条裁定（§9 裁定记录），
> 稿子转正为规范，裁定③（裸 `[checks]` 走槽）与裁定⑥（legal 废弃窗口提示）
> 随转正批实施，CHANGELOG 同批解冻补记。起草：G 席，2026-11-16；转正：同日。
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
  法文数字词解析、`mark_dup_ok`（改账，裁定⑦定位为写径维护工具
  `ledger_maint`，M2 已落地）都留在核验包外；core 不知道任何法域。
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

## 2. core 宪法：四样现状确认 ＋ 核验槽（第五样，新增）

### 2.1 现状确认（四样现存宪法级机构）

| # | 宪法级机构 | 现状落点 | 本稿是否改动 |
|---|---|---|---|
| 1 | **只追加事实账＋指纹钉版** | `facts/*.toml` 只追加、改事实＝新增＋`supersedes`（SPEC-V3.0 §11）；`source_sha256` 现算比对（SPEC-V1 §3.3）；`attestation.facts_sha256`（SPEC-V1 §5）；`audit/evidence.lock` 的 `canonical_sha256` | 不动 |
| 2 | **报告信封与退出码语义** | `issues/warnings/hints/summary` 信封（SPEC-V1 §5）；退出码唯一权威表（SPEC-V3.0 §2.5）；「退出码与违规码是公共 API，不随 major 不变」（CHANGELOG 头部原文） | 只增键（§3.2），不改名不删键 |
| 3 | **证据冻结机构** | `[evidence]` → `audit/evidence.lock`（canonical sha256，同输入同哈希）；解冻走只追加日志 `audit/evidence-log.ndjson`（SPEC-EVIDENCE-STAMP §8/§9；`factscribe/evidence.py::canonical_form/canonical_sha256/append_log`） | 推广为多域可用（§6），既有冻结件字节不破坏 |
| 4 | **单一实现不变量（纪律面）** | `canon()` 只有一份；`TOKEN_REGISTRY` 只有一份，报告里的码必须查得到，否则 `UNKNOWN_CODE`（exit 4）（SPEC-V3.0 §2.6） | 不动，并延伸到核验槽（§4） |

> 计数注（裁定①，2026-11-16）：宪法计数＝**「四样现状＋核验槽为第五样」**。
> 上表四样为现状确认（第 4 样＝单一实现不变量，占宪法第四样位）；
> 核验槽是新增的第五样（§2.2）——不做「四样含槽、不变量降为纪律」的收窄。

### 2.2 核验槽接口（宪法第五样）

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
- **跨域重码禁止**（裁定④，2026-11-16）：一个现象一个 code，两域不得两码同形——
  域前缀制（§4.3）是手段，本条是法令。新码注册进槽时跨域查重，与他域存量码
  同名的注册按修约级错误拒绝；存量各表已因前缀制天然无撞，本条把惯例升为禁令。
  域内「现象→唯一 code」映射（CODES-AND-CHAIN §1.3）全域通用化。core 的
  `TOKEN_REGISTRY` 只查「code 是否注册过、severity/exit 是否与注册一致」，
  查不到仍 `UNKNOWN_CODE`（exit 4，SPEC-V3.0 §2.6 不变量延伸到槽）。

### 4.2 全局退出码值永不变化（全闭集 0–9 入宪，裁定②）

- 退出码是**全局唯一**的公共 API：**0–9 全量值↔语义配对闭集**以 SPEC-V3.0 §2.5
  为唯一权威表，**永不变化**（裁定②，2026-11-16：全闭集入宪，不取
  「0/1/2/3/5/7/8」收窄枚举；4（RED(INTERNAL)）/6（RED(PROOF)）/
  9（RED(ATTACK_OPEN)）三值语义照权威表）。CHANGELOG 头部承诺的本稿化。
- 代码面＝`factscribe/checks.py::EXIT_CODE_CLOSED_SET`（M1 起整表补名，
  本稿对表）：新增退出码＝修约（major）。
- 核验包**不产生退出码**：包只报 findings，退出码由槽按权威表折算
  （任一域红 ⇒ 1；仅黄 ⇒ 3；仅 advisory/配置告警 ⇒ 0 或 3 按 §2.5；配置错 ⇒ 2）。
  法律件现状自带 0/1/2/3 的独立退出码在 M2 挂槽后停用（其语义恰好与折算规则重合，
  无行为跳变；独立子命令保留＝废弃窗口，裁定⑥，见 §9.6）。

### 4.3 跨域码命名空间

- **新入槽域的码必须带域前缀**：`<DOMAIN>_` 开头（`LEGAL_QUOTE_MISMATCH`、
  `CN_PROV_UNKNOWN`、`IT_VERSION_GAP` 均已是此形）。前缀＝`domain_id` 大写，
  一包多子闸时每个子闸的前缀都要在码表冻结（legal 的 `LEGAL_`/`CN_`/`CASE_`/`IT_`
  即为范本）。
- **core 存量码一字不改**（无前缀的 `UNMATCHED_NUMBER` 等照旧）；core 新增码
  建议也走前缀（如 `CORE_`），避免与未来域撞名。

### 4.4 码表冻结的修约程序（裁定④，已批入宪）

| 动作 | 级别 | 程序 |
|---|---|---|
| 纯新增码 | minor | 码表追加一行＋CHANGELOG `[Unreleased]/Added` 一行＋双向测试各一例 |
| 改名/改义/改 severity | **major（BREAKING）** | 旧码保留发射一个废弃窗口期或直接随 major 移除；CHANGELOG `**Breaking**` 条目；先例照「protocol literals 硬切」批 |
| 删码（现象消失） | major | 同上 |
| **跨域重码** | **禁止** | 不在程序表内、直接是禁令（裁定④）：注册查重，撞名即拒（§4.1） |

---

## 5. 配置：`factscribe.toml` 的 `[checks]` 节

### 5.1 形状

```toml
[checks]
# 点名本次要跑的核验包（顺序无关）；省略＝默认 ["paper"]（裁定③：节在场即走槽）
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

### 5.2 兼容承诺（给老用户的宪法保证；裁定③后三态口径）

| 情形 | 行为 |
|---|---|
| **无 `[checks]` 节** | 直跑（不走槽），只跑内建 `paper` 判据，**全部行为与现状逐字节不变**（退出码、findings、人读输出逐字节一致，无 `domain` 键、无 `by_domain`）——实现模式照 `[budget]`/`[evidence]` 先例：`checks_defined=False` ⇒ 对应判据不跑、行为与之前完全一致（config.py 批 128/131 注释原文口径） |
| `[checks]` 存在但省 `packages` | **走槽**（裁定③，2026-11-16），默认 `packages = ["paper"]`：发现本体与退出码和直跑逐条相同，差异只有两处只增键——每条发现多 `domain` 键、`summary` 多 `by_domain` 计数 |
| `packages` 显式点名 | 按点名跑（未注册 id ⇒ exit 2，CONFIG，报错点名该 id 与已注册域清单） |
| `[checks.<domain>]` 键集错误 | 该域 `CONFIG_UNKNOWN_FIELD` 告警（info），不改退出码；键值非法（如日期格式）按该域卡的 fail-closed 出黄/红 |

> 裁定③说明：M1 初版实现是「裸节＝同无节直跑」；2026-11-16 用户批准九条建议时
> 把裸节语义修订为「走槽默认 paper」（已批即实施）。受影响面＝输出多 `domain`/
> `by_domain` 两个只增键；金样例行为锁（§7 M1）已在锁的 26 个项目均无
> `[checks]` 节，重冻后逐项目发现本体与退出码逐条相同（重冻理由记在基线
> `note` 字段）。

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

## 7. 迁移计划（M0–M1.5–M3）

> 用户已裁定「全部要做」四步；本节是四步的工程展开。每步一条行为锁，
> 锁不过不进下一步。M0/M1/M2 已完成（落点见各节）；M1.5 已批待排（裁定⑤）。

### M0　合入法律件为独立维（已完成）

`integrations/factscribe-legal/` 已按 minifactscribe 先例合入 main
（合并提交 `9cd6a2d`，纯增量不碰核心）：独立子命令、独立码表
（`LEGAL_`/`CN_`/`CASE_`/`IT_`）、50 例离线自测、上游 core 零改动。
它现在的形态＝**第一个候任核验包的实体样本**：本稿 §3 的契约形状就是
照它现有形状总结的，M2 挂槽不需要它改判据，只改注册与入口。

### M1　论文三闸行为锁死重构进槽（已完成，落点 feat/check-slot-m1）

- **范围**：论文三闸——数字绑定闸（G1 族：`BOUND_MISMATCH`/`UNBOUND_NUMBER`/
  `UNMATCHED_NUMBER` 等，SPEC-V1 §4）、源头闸（G2 族：sha/清单/回查/证据链）、
  引用闸（G3 族：cite/bib）——从 `factscribe/audit.py` 的 `run_audit`/
  `run_check`/`verify_sources` 重构为 core 自带的第一个核验包 `paper`。
  落点：核验槽机构 `factscribe/checks.py`（commit `8a43775`）、`[checks]`
  解析与 audit 挂槽（commit `2b18442`）、金样例冻结（commit `cb79d60`）
  与常驻行为锁＋机制 34 例（commit `0c80c6d`）。
- **行为锁（金样例 fixture 锁）**：重构前先固化「发现清单金样例」——
  `examples/minimal` 与 `fixtures/`（benign/hostile/regression/trust）在
  `audit --json` 下的 findings 逐条（domain 除外，重构前无此键）落成快照；
  **重构前后快照逐条相同**才算过锁。退出码、码表、报告信封三样同锁。
- G5（派生）/G6（覆盖）/G7（闭包）/P 层（PDF 回检）：**第二批进槽**
  （裁定⑤，2026-11-16），见 M1.5。

### M1.5　文风 G5–G7 与 PDF 层第二批进槽（已完成，落点 feat/check-slot-m15）

裁定⑤（2026-11-16）：派生算式（G5）、覆盖豁免（G6）、闭包（G7）与
PDF 回检层（P 层）作为 `paper` 包的第二批进槽。排期待 M3 实证排期一并定；
进槽时照 §3 契约注册（同一张卡、同一套行为锁纪律：迁移前先冻结这批判据的
发现清单金样例，迁移前后逐条相同）。

落地形态（2026-11-16，M1.5 批）：按编排令注册为**两个独立域**进槽——
`style`（文风闸：公式化写作特征黄牌＋证据钢印红；判据在 `style.analyze`，
物理位置不动）与 `pdf`（PDF 回检层：文本层/栅格化/双向数字多重集/stamp
信任链；判据在 `pdfgate.verify_pdf`，材料依赖＝main.pdf＋编译产物，缺失按
现行语义 fail-closed 不静默绿）。两域只被 `[checks].packages` 显式点名时
才跑；缺省（无节／裸节默认 `["paper"]`，裁定③）行为逐字节不变——**M1
金样例锁原样通过，本批不重冻**。码为存量无前缀码（style 系各码与
`PDF_*`/`STAMP_*` 系），按 §4.3「core 存量码一字不改」祖父条款照旧发射。
G5–G7 的 audit 侧判据（派生/覆盖/闭包）在 M1 已随 `run_audit` 进 paper 包
（见 M1 节），本批不再搬动。落点：`factscribe/checks.py::register_builtins`
（commit `20c2fd2` style 包、`104f5e8` pdf 包）、三态矩阵扩展与两域行为锁
`tests/test_checks_slot.py`＋`tests/test_checks_m15.py`（commit `1da5c02`）。

### M2　legal 注册为第二核验包、单命令双域报告（已完成）

- legal 按本稿 §3 契约注册（domain_id `legal`、码表冻结、`[checks.legal]` 键集卡、
  材料依赖声明、verify 入槽入口），判据与码表零改动（commit `2d5fe8c`）；
- `factscribe audit` 按 `[checks]` 点名单命令跑双域，一份报告按域分节、
  一套退出码（§4.2 折算）（commit `d8adf94`）；
- 行为锁：legal 挂槽前后，同一测试项目（INTEGRATION-LEGAL §0 的真实项目读数：
  FR 0红/1黄、CN/CASE/IT 0红0黄）的 findings 逐条相同，仅多出 `domain` 键。
- 配套（同批）：改账函数出核验定位 `ledger_maint`（裁定⑦，commit `ca32252`）、
  每域一把冻结锁落 legal `audit/evidence-legal.lock`（裁定⑨，commit `d1c350b`）、
  legal README 换 factscribe 口径与核验包注册形态文档（commit `a06ebb5`）。

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
| `[checks]` 裸节从「同无节直跑」修订为「走槽默认 paper」（裁定③） | 否 | 差异只有 `domain`/`by_domain` 两个只增键，发现本体与退出码逐条相同；受影响者仅「写了裸 `[checks]` 节」的 M1 过渡期项目 |
| findings 信封新增 `domain` 键、summary 新增 `by_domain` | 否 | 只增键不改名不删键；报告 schema 维持 `factscribe-report/3.x` 前缀兼容 |
| legal 码表入 §8 总表 | 否 | 只增码、带域前缀、与 core 存量码零冲突 |
| 论文三闸重构进槽（行为锁通过） | 否 | 对外可观察行为逐条不变（§7 M1 锁） |
| 退出码任何值或值↔语义配对的改动 | **是** | CHANGELOG 头部承诺；§4.2（全闭集 0–9，裁定②） |
| core 存量码改名/改义/改 severity/删码 | **是** | 同上＋CODES-AND-CHAIN 先例；须 major（§4.4，裁定④） |
| 跨域重码 | **禁止** | 裁定④：不是程序问题，是禁令（§4.1） |
| 既有冻结件 canonical 形态变更 | **是** | §6 第 2 条；canonical sha256 变＝旧锁全废 |

### 8.2 备选方案否决记录

**A 案：把法律硬编码进 core audit（在 core 里加 `LEGAL_*` 判据）——否。**
理由：① 违反用户裁定的宪法边界（core 宪法＝四样现状＋核验槽为第五样，
不为具体领域留判据；「论文不是一等公民」的同一逻辑反过来禁止法律成为 core
的特权域）；② 码表会被焊死：`LEGAL_` 族进 core §8 总表后，法律语料的修约节奏
（语料视图月更、参考日常变）与论文闸的冻结节奏（公共 API、major 才动）绑死；
③ 50 例法律自测并入上游发布门，法律语料问题会阻塞论文工具发版，
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

## 9. 九裁定记录（2026-11-16，用户批准九条建议；每条：问题→裁定→落点）

1. **宪法计数控口**（原开放问题：四样含槽还是四样现状＋槽为第五样）
   → **裁定①：四样现状＋核验槽为第五样**（单一实现不变量占第四样位，不降纪律）。
   落点：本稿 §2.1 计数注、§2.2 标题（本转正批改稿）。
2. **退出码闭集口径**（原开放问题：枚举 0/1/2/3/5/7/8 还是全闭集）
   → **裁定②：全闭集 0–9 入宪**（值↔语义配对永不变化；4/6/9 语义以
   SPEC-V3.0 §2.5 权威表为准）。
   落点：`factscribe/checks.py::EXIT_CODE_CLOSED_SET` 整表补名（M1，commit
   `8a43775`）、`tests/test_checks_slot.py::test_closed_set_table_and_constants`
   （commit `0c80c6d`）、本稿 §4.2 对表（本转正批改稿）。
3. **`[checks]` 缺省语义**（原开放问题：裸节同无节还是要求显式点名）
   → **裁定③：节存在但省 `packages` ⇒ 默认 `["paper"]` 且走槽**（对 M1 现实现
   「裸节＝同无节直跑」的行为修订，已批即实施）。
   落点：`factscribe/cli.py::cmd_audit` 挂槽条件改 `checks_defined`（转正批）、
   `factscribe/checks.py::resolve_packages` 缺省 `["paper"]`、
   `factscribe/config.py::_parse_checks` 文档面、三态对表测试
   `tests/test_checks_slot.py`（无节直跑／裸节走槽／显式点名）、金样例重冻
   `tests/golden/audit_findings_baseline.json`＋`scripts/audit_golden_dump.py`
   note 记重冻理由（转正批 commit）。
4. **码表修约程序**（原开放问题：默认案是否入宪＋跨域重码是否允许）
   → **裁定④：程序入宪——纯增＝minor、改名/改义/改 severity/删＝major；
   跨域重码禁止**（不许「同一现象两域两码」）。
   落点：本稿 §4.1 禁令、§4.4 程序表（本转正批改稿）。
5. **G5/G6/G7 与 P 层的归属**（原开放问题：M1 只迁三闸，其余留 core 直跑还是第二批进槽）
   → **裁定⑤：第二批进槽**（M1.5，已批待排；本批不写码）。
   落点：本稿 §7 M1.5（本转正批改稿）。
6. **legal 独立子命令的去留**（原开放问题：保留还是随槽收编）
   → **裁定⑥：保留功能，进废弃窗口**——CLI 各子命令输出加一行提示
   （「单域调试入口……正式报告走 factscribe audit [checks]」，措辞照 M2 README
   既有文案），废弃窗口不限期。
   落点：`integrations/factscribe-legal/factscribe_legal/cli.py`（转正批 commit）、
   `integrations/factscribe-legal/tests/test_cli.py`（转正批新增）、
   README「核验槽时代」既有文案。
7. **改账函数的定位**（原开放问题：`mark_dup_ok` 类改账是否立卡、放哪）
   → **裁定⑦：改账是写径不是核验——独立账务维护工具**（与 `fact add` 同层），
   核验包 `verify()` 只读。
   落点：已落地——`integrations/factscribe-legal/factscribe_legal/ledger_maint.py`
   （M2，commit `ca32252`）、`tests/test_legal_maint.py`。
8. **核验包的安装形态**（原开放问题：integrations/ 入仓注册还是 pip 命名空间分发）
   → **裁定⑧：`integrations/<pkg>/` 入仓注册**（沿 minifactscribe、
   factscribe-legal 两先例）。
   落点：已采纳，M2 落地——`integrations/factscribe-legal/check-package.toml`
   ＋`factscribe/checks.py::load_integration` 约定路径发现（commit `2d5fe8c`）。
9. **域级冻结锁件形态**（原开放问题：每域一锁还是一锁多节）
   → **裁定⑨：每域一把**（`audit/evidence-<domain>.lock`；paper 沿用既有
   `audit/evidence.lock` 字节不破坏）。
   落点：已落地——`factscribe/checks.py::evidence_lock_path`（commit `8a43775`）、
   legal 锁 `audit/evidence-legal.lock`＋unfreeze 流水账（M2，commit `d1c350b`）。

---

## 附：本稿引用的仓内文件（基线＝feat/check-slot-m1@a06ebb5）

- `docs/design/SPEC-V1.md` §3/§4/§5（三闸判据、G1–G7、退出码与 `--json` 信封）
- `docs/design/SPEC-V3.0.md` §2.5（退出码唯一权威表，0–9 全闭集）、§2.6
  （单一实现不变量）、§8（错误码总表）、§10（项目配置冻结）、§11.6（证据链）
- `docs/design/SPEC.md` §5（硬性要求：纯标准库、离线、零 LLM）
- `docs/design/SPEC-EVIDENCE-STAMP.md` §8/§9（证据钢印冻结/解冻）
- `docs/implementation/CONFIG-CONTRACT.md`（契约表、别名闭集、形态判定七步、
  未知字段告警纪律）
- `docs/implementation/CODES-AND-CHAIN.md`（码表冻结、合并/改名先例、唯一映射）
- `docs/implementation/INTEGRATION-LEGAL.md`（法律件自我定位、四闸码表、
  边界声明、三条工程纪律）
- `integrations/factscribe-legal/README.md`（第二个核验包的现成样本：
  码表形状、材料依赖、退出码沿用、防假绿自测；「核验槽时代」废弃窗口文案）
- `integrations/minifactscribe/README.md`（第三方件先例与其适用边界）
- `factscribe/config.py`（`Config` 形状；`[budget]` 批 128 / `[evidence]` 批 131
  「节不出现＝判据不跑、行为与之前完全一致」的兼容先例；`_parse_checks` 三态）
- `factscribe/checks.py`（核验槽机构：注册表、`EXIT_CODE_CLOSED_SET`、
  `resolve_packages`、`run_packages`、`evidence_lock_path`、`load_integration`）
- `factscribe/audit.py`（paper 包判据——G1/G2/G3 三闸的实现细节）
- `factscribe/evidence.py`（`canonical_form`/`canonical_sha256`/`write_lock`/
  `append_log`——冻结机构推广的底座）
- `tests/golden/audit_findings_baseline.json`＋`scripts/audit_golden_dump.py`
  （金样例行为锁；note 字段记冻结/重冻理由）
- `CHANGELOG.md` 头部（「exit codes and violation codes are the public API …
  without a major version bump」）

---

*本稿只修约「核验怎么挂槽」，不改「绿＝账有据、据未改、文有绑」的任何一条
域内含义；各域「绿不代表内容为真」的边界声明仍是引用其结论时的必附句。*
