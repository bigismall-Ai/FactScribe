# SPEC-TIDE｜潮汐式改动账（批 89）

> 状态：**冻结**（批 89 实施依据）。
> 范围：新增 `factscribe tide` 子命令与新模块 `factscribe/tide.py`。
> 不改 `audit` / `style` / `protect` 的既有判据与退出码；零第三方依赖（纯标准库）。
> 一句话：**改动本身是一个事务；账本由文件哈希派生，不认自报。**

---

## 1. 问题与立场

「改了哪里」现在靠人或模型自报，自报会漏报，而且无法机械核对。本规范把一次改动
定义为一个**事务**：涨（改了什么）与落（改后的真实文件状态）都由两个目录的哈希
对比派生，人不提供任何清单；闭合条件由工具计算，人只能看结果。

推论（本规范的核心立场）：

1. **涨不许人填**：涨来自 `--before` / `--after` 两个目录的文件哈希差。
2. **落不许人填**：落来自改后目录里真实存在的文件（重新读盘、重新算哈希）。
3. **波及面不许人填**：由 `\input{}` / `\include{}` 反向引用闭包自动算。
4. **不闭合就全退**：不写账本、不写派生视图、退出码 1。

---

## 2. 命令

```text
python3 -m factscribe tide --before <目录> --after <目录> [--out <events.ndjson>] [--json]
```

| 参数 | 必填 | 语义 |
|---|---|---|
| `--before` | 是 | 改前目录（必须存在且是目录） |
| `--after` | 是 | 改后目录（必须存在且是目录） |
| `--out` | 否 | 事件账本路径；默认 `<after>/audit/tide-events.ndjson` |
| `--json` | 否 | stdout 只出 JSON |

派生视图 `audit/tide-ledger.md` 只在使用**默认账本落位**（未给 `--out`）时写出，
路径为 `<after>/audit/tide-ledger.md`。给了 `--out` 表示调用方自管产出，只写账本。

退出码：**0 = commit**；**1 = rollback**；**2 = 用法/配置错**（目录不存在、账本不是
合法 NDJSON）；**4 = 工具内部错误**（沿用既有分层，不新增码）。

---

## 3. 库存口径（哪些文件参与）

参与对比的是两个目录下的**普通文件**，路径用相对 POSIX 路径：

- 跳过任一路径段以 `.` 开头的隐藏文件/目录（与 `protect` 的 `_tex_files` 同口径）；
- 跳过顶层 `audit/`（派生目录，避免工具产出被下一趟当成改动，形成自指）；
- 跳过本趟的产出路径本体（`--out` 与派生视图），其余一律入册。

哈希＝文件**字节**的 sha256（十六进制小写）。缺失一侧记 `null`。

> 只对 `.tex` 文件抽取「触及的行区间/章节」；其它文件只记哈希。

---

## 4. 事件模型（events.ndjson）

账本本体是 append-only 的 NDJSON，**一行一事件**，键排序、UTF-8、无时间戳、
无绝对路径。事件三型：

### 4.1 `rise`（涨）

```json
{"event":"rise","tx":"<16位>","path":"chapters/a.tex",
 "before":"<sha256|null>","after":"<sha256|null>",
 "lines":["12-14","20"],"sections":["Method"]}
```

- `before` / `after`＝改前/改后文件字节哈希；不存在的一侧为 `null`（新增/删除）。
- `lines`＝触及的行区间（改后侧行号；整文件新增/删除时为该侧全区间）。
- `sections`＝触及行所在的章节标题（按 `protect._heading_items` 的抽取口径；
  找不到则为空数组）。
- 每个发生变化的文件**恰好一条**，按 `path` 升序。

### 4.2 `fall`（落）

```json
{"event":"fall","tx":"<16位>","path":"chapters/a.tex","exists":true,"sha256":"<sha256|null>"}
```

- `exists`＝改后目录里该路径是否为普通文件。
- `sha256`＝**重新读盘**算出的改后哈希；不存在则为 `null`。
- 每条涨**必须**有对应落（同 `path`），按 `path` 升序。

### 4.3 `verdict`（判定）

```json
{"event":"verdict","tx":"<16位>","status":"commit","paired":true,
 "hash_ok":true,"pass_all":true,"rises":1,"falls":1,
 "affect":["chapters/a.tex","main.tex"]}
```

`status` 只有 `commit` / `rollback`。只有闭合时才写 `commit` 判定；
**rollback 不写任何事件**（全退）。

### 4.4 `tx`（事务号）

`tx`＝对「本事务全部 rise/fall 事件（不含 `tx` 字段）的规范 JSON」取 sha256 的
前 16 位。因此：内容相同 → `tx` 相同 → 账本逐行相同；写账本时按**整行去重**，
同一事务重复跑不会重复追加（append-only 且幂等）。

---

## 5. 涨/落判据

| 判据 | 定义 | 失败语义 |
|---|---|---|
| 涨 | `before_hash(path) != after_hash(path)`（含一侧缺失） | —— |
| 落 | 对每条涨，按 `path` 在改后目录重新读盘，记录 `exists` 与真实 sha256 | 目标缺失 ⇒ 该落 `exists=false` |
| `paired` | 涨集合与落集合按 `path` 一一对应（双向包含） | 无落＝漏报 |
| `hash_ok` | 每条落的 `sha256` 都能由实际文件内容复算出来，即 `exists=true` 且 `sha256 == sha256(实际字节)`；删除（目标不存在）即不可复算 | 落不实 |
| `pass_all` | 波及面内 `protect` 的**硬面零红**（复用 `protect.compare`，只取 `severity=red` 的发现；黄/信息不算红） | 保护面破了 |

`paired` 还包括**账本自洽**：账本里既有的每个事务，其 rise 路径必须被同事务的
fall 覆盖（手写账本里孤立的涨＝漏报）。

`hash_ok` 还包括**账链连续性**：账本里既有的 fall 记录描述的是「改前状态」。
对本事务涨涉及的路径，账本里**最新**的一条既有 fall（非本事务）必须与
`--before` 目录的实际内容一致；不一致说明账本被改过或目录与账本脱节。

---

## 6. 波及面（Affect）

`Affect` ＝ 变化文件本身 ∪ 所有 `\input{}` / `\include{}` 引用它的文件，沿反向
引用做**传递闭包**（被引用的章节改了，引用它的主文件也在波及面内）。

算法：

1. 对 `--before` 与 `--after` 两个目录的每个 `.tex`，用 `protect._code_view`
   去掉注释/verbatim（与保护面同一套遮罩），再用
   `\\(?:input|include)\s*\{([^}]*)\}` 抽引用。
2. 目标名归一：去空白；无扩展名补 `.tex`；**先按项目根相对解析**（LaTeX 默认），
   不中再按引用文件所在目录相对解析，两条都 `posixpath.normpath` 归一。
3. 建反向边 `target → 引用者`（两目录合并，删除场景也能追到引用者）。
4. 从变化文件集合出发做 BFS，得到波及面，按路径升序输出。

波及面**只由工具计算**，命令行没有任何注入点。

---

## 7. 闭合与全退

```text
闭合 = paired ∧ hash_ok ∧ pass_all
```

- **闭合** ⇒ `status=commit`，追加事件（rise → fall → verdict），写派生视图，
  退出码 0。
- **任一不成立** ⇒ `status=rollback`，**不写账本、不写派生视图**，退出码 1。
  `--json` 仍输出完整计算面（涨/落/波及面/三项判定/未闭合原因/硬面发现），
  供人排查，但磁盘上不产生任何「已提交」痕迹。

无涨的事务：`paired/hash_ok/pass_all` 平凡为真，状态 commit，账本不动
（无事可记），派生视图照写（零行表）。

---

## 8. 派生视图 `audit/tide-ledger.md`

仅在闭合且未给 `--out` 时写出。逐条列：文件、改前/改后哈希前 8 位、波及面、
三项判定。示例：

```markdown
# 潮汐账（tide ledger）

- 事务：3f2a1c9d8e7b6a50
- 涨：1   落：1   波及面：2   事件：3
- 判定：paired ✓   hash_ok ✓   pass_all ✓
- 状态：commit

| 文件 | 改前(前8) | 改后(前8) | 波及面 | paired | hash_ok | pass_all |
|---|---|---|---|---|---|---|
| chapters/a.tex | 11223344 | 55667788 | chapters/a.tex、main.tex | ✓ | ✓ | ✓ |
```

`—` 表示该侧不存在。表格按文件路径升序。

---

## 9. 确定性

同一输入双跑**逐字节一致**：

- 禁时间戳、禁随机数、禁绝对路径（账本与派生视图里只有相对 POSIX 路径）；
- 所有集合输出显式排序（文件按路径、事件按 rise → fall → verdict）；
- JSON 键排序（`sort_keys=True`）、UTF-8、`ensure_ascii=False`；
- 同一事务重复写入按整行去重，账本 append-only、幂等。

---

## 10. 边界（写死，不许解释）

| 情况 | 结果 |
|---|---|
| `--before`/`--after` 不存在或不是目录 | `CONFIG_INVALID`，退出码 2 |
| 账本存在但不是合法 NDJSON / 事件缺字段 | `CONFIG_INVALID`，退出码 2 |
| 删除文件 | `hash_ok` 假（落的目标不存在）→ rollback |
| 新增文件 | 涨 `before=null`；落 `exists=true`；normally commit |
| 新增 `.tex` 只触发 `protect` 的黄（文件集合） | 不算红，`pass_all` 真 |
| 只改标点/措辞 | 保护面绿 → commit |
| 改数字/公式/引用/表格/交叉引用/事实标记 | `pass_all` 假 → rollback |
| 手写账本里哈希与实际不符 | 账链连续性假 → rollback，账本原样不动 |
| 手写账本里孤立 rise（无 fall） | `paired` 假 → rollback |

---

## 11. 与既有模块的关系

- 抽取逻辑**复用** `factscribe/protect.py`：`_code_view`、`_heading_items`、
  `compare`（硬面判据与退出码完全不动）。
- 本规范不改 `audit` / `style` / `protect` 任何既有判据；`tide` 是并列的
  新子命令，唯一新增的 CLI 注册项。
