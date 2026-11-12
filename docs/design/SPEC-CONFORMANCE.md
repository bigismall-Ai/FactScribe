# SPEC-CONFORMANCE｜Python 原版 ↔ JS 移植件的一致性锁（批 138）

状态：批 138 冻结（实施依据）。
范围：只新增一致性锁的四件东西（夹具、投影脚本、两侧测试、本规范）；
**不改 Python 判据**（`factscribe/audit.py` 一行没动），也不改 JS 移植件的判据。

一句话：**同一份固定项目，Python 版和 JS 版判出的核心错误码多重集必须完全
相等；谁先漂了，锁就响。**

---

## 1. 为什么锁（问题面）

`integrations/minifactscribe/miniapp/node/audit.mjs` 是第三方把 `factscribe/audit.py`
的审计语义重写了一遍，导出 `auditProject(project)`。它自带 26 个用例，但全部
是**对着自己的实现**断言的——从来没有和 Python 原版比对过。

两份实现不比对会发生什么：JS 侧某个码少判一次（或多判一次），它自己的 26 个
用例可能全绿，而两边对同一篇论文给出不同结论。这种漂移不会「崩」，只会悄悄
分家——等发现时，已经没人说得清哪边是对的。

所以本批不加判据，只加**对比面**：把同一份项目同时喂给两边，看它们报的码是
不是同一组。

---

## 2. 锁什么（契约）

| 锁 | 不锁 |
|---|---|
| 核心错误码的**多重集**（哪几个码、各几次） | 行号、列号、`token` 原文、消息措辞 |
| 夹具的红必须还在（三类红不许消失） | 问题出现的先后顺序 |
| 投影输出逐字节稳定 | 退出码的细粒度差异（只要求两侧都判红） |

为什么不比文本：两边的文本模型不同。同一个数，JS 记 `47.3ms`（把单位含在
token 里），Python 记 `47.3`；行号在 JS 侧是「拼好的正文」的行号，Python 侧是
「单个节文件」的行号。比这些等于给移植件加一道它本来就不该背的债。

多重集相等是**双向**的：Python 多报一个核心码、JS 少报一个，都算失败。

---

## 3. 投影契约（`scripts/conformance-dump.py`）

Python 侧读磁盘目录，JS 侧读一个内存对象——两边接口不同，所以中间必须有
**唯一一条投影路**。脚本读夹具目录，往 stdout 吐一份 `project.json`：

```json
{
  "name": "...",
  "manuscript": "<所有节按 main.tex 的 \\input 顺序拼接>",
  "bib": "<refs.bib 原文>",
  "sources": [{"id": "results/x.md", "text": "...", "sha256": "..."}],
  "facts": [{"id": "", "claim": "", "value": "", "source": "",
             "sourceSha256": "", "locator": "", "confidence": "",
             "derivedFrom": [], "expr": ""}]
}
```

确定性约定（守不住它，逐字节比对就没有意义）：

- `facts` 按 `id`（casefold）排序，`sources` 按 `id` 排序；
- 输出里没有时间戳、随机数、绝对路径（`name` 取项目标题，缺省取目录名）；
- JSON 固定 `indent=2`、UTF-8、末尾一个换行；
- 脚本**只读**夹具，不写任何文件；
- `sources[].sha256` 算的是**投影出去那段文本**的 UTF-8 字节（文件本身是
  UTF-8 时等于文件哈希）——因为 JS 侧对 `text` 现算哈希，两边必须算同一串字节。

`sources` 只投影账上真正引用到的来源。这带来一条边界：**「source 指向一个
不存在的文件」这个场景投影不出来**（没办法给出不存在的文本），所以该场景
不在一致性锁的覆盖范围内，仍由两侧各自的测试管。

---

## 4. 夹具（`tests/conformance/fixture/`）

一个最小 v1 项目，故意留红，**别顺手修绿**：

| 行 | 触发 | 码 |
|---|---|---|
| `sections/10-claims.tex` 第 2 句：`解决 11 道\fact{A1}`，而 A1 的 value 是 `10/16` | 绑了，但值对不上 | `BOUND_MISMATCH` ×1（红） |
| `sections/20-notes.tex`：`47.3\,ms` 没有账 | 账外数字 | `UNMATCHED_NUMBER` ×1（红） |
| `sections/20-notes.tex`：`\cite{ghost2024}`，bib 里没有 | 悬空引用 | `MISSING_CITE` ×1（红） |
| `sections/10-claims.tex`：`88` 回得到 A3，但没内联绑定 | 只算黄 | `UNBOUND_NUMBER` ×1（黄） |

夹具自包含：`main.tex`（成文，只含导言区与 `\input`）、`sections/`、
`refs.bib`、`facts/`、`results/run.md` 与 `results/MANIFEST.toml`（人签清单，
哈希与 `results/run.md` 一致）。

---

## 5. 怎么重生成（改了夹具或判据之后）

两侧测试读的是**提交进仓的** `project.json` 和 `expected.json`，所以夹具一动，
这两个文件必须跟着动，否则测试会红——这正是设计意图（防「改了夹具忘了重生成」）。

```bash
# ① 重生成投影（夹具或投影脚本一改就要重跑）
python3 scripts/conformance-dump.py tests/conformance/fixture \
  > tests/conformance/project.json

# ② 重生成期望读数（只在「有意改夹具 / 有意改判据」时做）
python3 -m factscribe audit tests/conformance/fixture --json   # 先亲眼看一遍码
python3 - <<'PY'
import json, subprocess, sys
from collections import Counter
core = json.load(open('tests/conformance/expected.json'))['core_codes']
d = json.loads(subprocess.run(
    [sys.executable, '-m', 'factscribe', 'audit',
     'tests/conformance/fixture', '--json'],
    capture_output=True, text=True).stdout)
codes = [i['code'] for i in d['issues']] + [w['code'] for w in d['warnings']]
got = {k: v for k, v in sorted(Counter(c for c in codes if c in set(core)).items())}
print(json.dumps(got, ensure_ascii=False, indent=2))
PY
```

把 ② 打印的 `codes` 贴回 `expected.json`，再跑一遍门禁。

**规矩三条：**

1. 不许为了「让测试过」去改 Python 判据。判据只有一条路能改：先改 SPEC / 判据
   本身，再重生成读数。
2. 改夹具导致两侧读数变了，要在提交信息里写清「夹具为什么改」。
3. 如果发现 **JS 判得和 Python 不一样**：不许把 JS 改成「和 Python 一样但没人
   评审」的顺手改；先如实记进 §7 的差异清单，再决定是修 JS、还是把该码移出
   核心清单。

---

## 6. 核心码清单（机器可读副本在 `expected.json` 的 `core_codes`）

入选条件：**两侧都实现，且在夹具家族上实测多重集相等**（批 138 逐码探针验证）。

| 码 | 严重度 | 夹具触发 | 说明 |
|---|---|---|---|
| `UNMATCHED_NUMBER` | 红 | ✅ ×1 | 数字回不到任何 `fact.value` |
| `BOUND_MISMATCH` | 红 | ✅ ×1 | 内联绑定是硬约束，数字不在绑定 fact 的值域里 |
| `MISSING_CITE` | 红 | ✅ ×1 | 引用 bib 里不存在的 key |
| `UNBOUND_NUMBER` | 黄 | ✅ ×1 | 回得到账但没内联绑定 |
| `UNKNOWN_FACT_MARKER` | 红 | — | 正文 `\fact{ID}` 指向账上不存在的 id |
| `UNKNOWN_CITE_COMMAND` | 红 | — | 认不出的 `*cite*` 命令（引用族 fail-closed） |
| `DUPLICATE_BIB_KEY` | 红 | — | bib 里同一个 key 定义多次 |
| `BIB_NO_STABLE_ID` | 红 | — | 被引条目既无 doi 也无 arxiv/url |
| `UNUSED_BIB` | 黄 | — | bib 有、正文没引 |
| `SOURCE_SHA256_MISMATCH` | 红 | — | 账上钉的哈希与材料现算不符 |
| `EXPR_MISMATCH` | 红 | — | 派生 fact 的 `expr` 与 `value` 不符 |
| `EXPR_INVALID` | 红 | — | `expr` 不可求值 |
| `LOW_BINDING_RATE` | 黄 | — | 内联绑定率低于 50%（样本量 ≥4 才判） |
| `DUPLICATE_ID` | 红 | — | fact id 重复（大小写不敏感）；见 §7 D8 的级联注意 |

「夹具触发」打 — 的码，锁的是**「不该出现」**：夹具若哪天让 JS 侧凭空多报一个
`BIB_NO_STABLE_ID`，多重集会立刻不等。所以它们入清单不是摆设。

新增一个核心码的流程：先在两侧各造一例验证读数相等 → 加进 `core_codes` →
确认夹具与 `expected.json` 一致 → 跑门禁。

---

## 7. 已知差异清单（如实记录，不是待办清单）

下面每一处都是**实测或读码确认**的差异。它们的共同点是：不影响本夹具的四个
核心码，但意味着「同名码在两侧可能不是同一件事」。这些码因此**不进核心清单**。

| # | 码 / 行为 | Python 原版 | JS 移植件 | 处理 |
|---|---|---|---|---|
| D1 | `MISSING_SOURCE` | 指 **来源文件不存在**（`source` 指向的文件不是普通文件） | 指 **来源文件不存在**（`source` 指向的来源 id 不在投影里） | **已修（批 139）**：两侧同为「来源文件不存在」；语义已对齐，但尚无夹具探针实测，暂不入核心 |
| D1b | 缺 `source` 字段 | 报 `MISSING_SOURCE_FIELD` | 报 `MISSING_SOURCE_FIELD` | **已修（批 139）**：码名与含义同 Python；同上，待夹具探针验证后再议入核心 |
| D1c | `BAD_SOURCE_PATH` | 指 URL / 绝对路径 / `..` 越界（路径**合法性**） | 不判：JS 拿到的投影里没有文件系统，「来源 id 找不到」已改报 `MISSING_SOURCE` | 只剩 Python 有（JS 无路径模型），**不入核心** |
| D2 | `NUMBER_AS_CROSSREF` | 只在 V3 项目判；v1 项目里手写「表 3」落 `UNMATCHED_NUMBER` | 每次审计都判（黄） | **不入核心**（V3 专属 vs 全量） |
| D3 | `TABLE_UNBOUND` | v1 对 tabular 里回不到账的数字给专属码（exit 5） | 没有表格概念，按普通数字判 `UNMATCHED_NUMBER` | **不入核心** |
| D4 | `UNUSED_FACT` | 是 hint（info）：不进 red/yellow、不改退出码 | 是黄牌，进 yellow | **不入核心**（严重度不同） |
| D5 | `DUPLICATE_VALUE` | v1 的 `audit` 不判（只在 `check`、以及 V3 的 `audit` 判） | 每次 `audit` 都判（黄） | **不入核心**（准入面不同） |
| D6 | `VALUE_NOT_IN_SOURCE` | v1 会做「value 数字要字面出现在 source 文本里」的复核（黄） | 没有这条判据（只有 sha256 现算） | Python 独有，**不入核心** |
| D7 | 清单/覆盖/宏/闭包类码 | `NO_MANIFEST`、`MANIFEST_UNSIGNED`、`MANIFEST_HASH_MISMATCH`、`SOURCE_NOT_SIGNED`、`UNSIGNED_RESULT`、`UNSCANNED_TEX`、`ARITH_IN_BODY`、`NUMERIC_IN_MACRO`、`COMPUTED_VALUE_UNREGISTERED`、`INPUT_TARGET_MISSING`、`INPUT_DYNAMIC` 等 | 不实现：JS 侧拿到的 `project` 里没有清单、文件树、宏定义这些概念 | Python 独有，**不入核心** |
| D8 | `DUPLICATE_ID` 的级联 | 重复条目**仍**把 value 计入全局值域（`key_to_facts`） | 撞到重复 id 就 `continue`，该条的值域**不参与**回账 | 码本身计数相等（可入核心），但**同一夹具里若混入重复 id，`BOUND_MISMATCH` / `UNMATCHED_NUMBER` 计数会分家**（实测 3 vs 1）。夹具不含重复 id |
| D9 | `BAD_ID_FORMAT` | v1 的 `audit` 不判（只在 `check` 判）；V3 才判 id 形状 | 只判「id 为空」 | 准入口不同，**不入核心** |
| D10 | `EMPTY_VALUE` / `BAD_KIND` / `BAD_CONFIDENCE` | 只在 `check` 判 | 无 | Python 独有（audit 面），**不入核心** |
| D11 | 文本模型 | `47.3`（单位留在正文里） | `47.3ms`（单位含进 token） | 按契约**不比 token** |
| D12 | 行号 | 单节文件内的行号 | 拼接后正文的行号 | 按契约**不比位置** |

结论：两侧在**核心码**上判得一样（本夹具 4/4 相同）；差异集中在「清单/覆盖/
宏/表格/V3 审批」这些 JS 侧本来就没有模型的面上。这不是移植件偷懒——它拿到的
输入里压根没有这些信息。要不要补，是另一批的事，不在本锁的判据里。

---

## 8. 测试与门禁

| 位置 | 断言 |
|---|---|
| `tests/test_conformance.py` | ① `factscribe audit <夹具> --json` 的核心码多重集 == `expected.json`；② 重跑投影脚本，输出与已提交的 `project.json` **逐字节**一致；③ 投影确定性、无本机绝对路径 |
| `integrations/minifactscribe/tests/conformance.test.mjs` | 读 `project.json` → `auditProject` → 同一份核心码多重集 == `expected.json`（Python 读数） |

两侧都离线可跑：Python 侧只跑本地审计（不联网、不编译），JS 侧只读两个 JSON。

门禁（批 138 验收）：

```bash
env PYTHONPATH=src python3 -m unittest discover -s tests
node --test integrations/minifactscribe/tests/*.test.mjs
./scripts/preflight-ci.sh
```

锁的灵敏度也验过：把 `expected.json` 里任一计数 +1，Python 侧 3 个用例红 1 个、
JS 侧 2 个用例红 1 个——两边都会响，不是空转的绿灯。
