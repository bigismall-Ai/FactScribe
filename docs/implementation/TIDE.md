# 潮汐式改动账实施记录（批 89）

> 规范：`docs/design/SPEC-TIDE.md`。
> 新增 `factscribe tide` 子命令与新模块 `factscribe/tide.py`；
> **未改 `audit` / `style` / `protect` 的判据与退出码**；零第三方依赖（纯标准库）。

一句话：**改动本身是一个事务；涨、落、波及面全部由文件哈希派生，人不提供清单。**

## 1. 判据表

| 判据 | 定义 | 正例 | 反例 |
|---|---|---|---|
| 涨（rise） | 两目录同名文件字节 sha256 不等（含一侧缺失） | 只改标点：一条 rise，哈希改变 | （构造上恒成立） |
| 落（fall） | 对每条涨，在改后目录**重新读盘**记 `exists` 与真实 sha256 | 改文件：`exists=true` 且哈希=实际 | 删文件：`exists=false` |
| `paired` | 涨与落按路径一一对应；账本既有事务的 rise 必须被同事务 fall 覆盖 | 1 涨 1 落 | 手写账本里孤立 rise（无 fall） |
| `hash_ok` | 每条落都能由实际文件复算（`exists` 且哈希相等）；账本既有落须与改前目录一致（账链连续） | 改文件后重新落盘 | 删文件；手写账本哈希与实际不符 |
| `pass_all` | 波及面内 `protect` 硬面零红（复用 `protect.compare`，只取 `severity=red`） | 只改标点/措辞 | 53 → 54（数字红） |
| 波及面 | 变化文件 ∪ 沿 `\input`/`\include` 反向引用的传递闭包 | 改 `chapters/a.tex`，`main.tex` 入面 | 未被引用的文件不入面 |

**闭合**＝ `paired ∧ hash_ok ∧ pass_all`。

- 闭合：状态 `commit`，追加 `rise → fall → verdict` 事件，写派生视图，退出码 0。
- 不闭合：状态 `rollback`，**不写账本、不写派生视图**，退出码 1；`--json` 仍给
  完整计算面（涨/落/波及面/三项判定/未闭合原因/硬面发现）。

## 2. 波及面算法

1. 两个目录的每个 `.tex` 用 `protect._code_view` 去注释/verbatim（与保护面同一套遮罩）。
2. 正则 `\\(?:input|include)\s*\{([^}]*)\}` 抽引用；目标去空白、无扩展名补 `.tex`，
   **先按项目根相对解析**（LaTeX 默认），不中再按引用文件目录相对解析。
3. 建反向边 `target → 引用者`（改前改后两棵树合并，删除场景也能追到引用者）。
4. 从变化文件集合 BFS 求闭包，按路径升序输出；派生视图里每个文件列**它自己**的
   波及面（单点闭包）。

波及面在命令行上**没有任何注入点**。

## 3. 账本

- `events.ndjson`，append-only，一行一事件（`rise` / `fall` / `verdict`），键排序、
  相对路径、无时间戳。
- `tx`＝本事务 rise/fall 内容的 sha256 前 16 位；账本写入按**整行去重**，
  同一事务重复跑不会重复追加（append-only 且幂等）。
- 默认落位 `<after>/audit/tide-events.ndjson`；`--out` 可改。
  派生视图 `audit/tide-ledger.md` 仅在未给 `--out` 时写出。
- `hash_ok` 的账链连续性：账本里既有的最新落记录描述的是「改前状态」，
  必须与 `--before` 目录实际内容一致；不一致＝账本被改过或目录与账本脱节。

## 4. 库存口径与确定性

- 参与对比：普通文件；跳过隐藏路径、顶层 `audit/`（派生目录防自指）与本趟产出本体。
- `.tex` 额外记触及行区间（改后侧行号，纯删除用改前侧）与所在章节标题
  （`protect._heading_items` 口径）。
- 同一输入双跑逐字节一致：所有集合显式排序、无时间戳/随机数/绝对路径。

## 5. 测试数

`tests/test_tide.py`：**30 例**，覆盖

| 组 | 例数 | 要点 |
|---|---|---|
| commit（标点/哈希/行区间/章节/NDJSON 排序/自定义 out/append-only） | 8 | 涨落配对、`paired/hash_ok/pass_all` 全真 |
| pass_all rollback | 4 | 数字变红、零落盘、硬面发现、既有账本不动 |
| hash_ok rollback | 4 | 删文件（落的目标缺失）、自报账本哈希造假 |
| paired rollback | 2 | 账本孤立 rise；无改动时平凡配对 |
| 新增文件 | 2 | `before=null`、软黄不阻断 |
| 波及面 | 4 | `\input`/`\include`、传递闭包、无关文件不入面 |
| 确定性 | 3 | 同跑双次、两棵新树、产出无绝对路径 |
| 用法错 | 2 | 目录缺失、账本非 NDJSON → exit 2 |

四条判据（`paired`、`hash_ok`、`pass_all`，以及涨/落这对派生事实）都各有正反例。

## 6. 门禁输出

```text
$ env PYTHONPATH=src python3 -m unittest discover -s tests
Ran 406 tests in 20.411s
OK

$ ./scripts/preflight-ci.sh
步骤 1/4：外部依赖 ......... ✓ pdftotext / pdfinfo 齐备
步骤 2/4：干净克隆 ......... ✓
步骤 3/4：测试矩阵 ......... ✓ Python 3.10 / 3.11 / 3.12（各 406 tests）
步骤 4/4：验收样例 ......... ✓ examples/minimal audit exit=1
结论：本地等价 CI 全绿——可以推。
```

## 7. 已知边界（如实写）

- **删除即 rollback**：规范要求「落＝改后文件存在且哈希可复算」，删除没有改后状态，
  因此一律 `hash_ok=false`。删除必须走显式流程（先记废名再走批量），不在本账内闭环。
- **账链连续性**要求 `--before` 与账本上一笔状态一致；目录在账外被改动会被判红——
  这是设计意图（账与目录脱节必须暴露），不是误报。
- 顶层 `audit/` 不入账（派生目录）；若项目把正文放 `audit/` 需改名。
- 只抽 `\input`/`\include`；`\subfile`、`\import` 等不追（未在规范内）。

## 8. 忽略规则（批 89b）

**问题**：真实论文目录里 `main.aux` / `main.blg` / `main.out` 是 LaTeX 编译中间产物，
改前有、改后没有（或反之）。旧口径把它们当普通文件入账，落的目标缺失 → `hash_ok=false`
→ 永远是 `rollback`，真实改写闭不了合。

**默认忽略表**（只按后缀，`fnmatch` 对相对路径匹配，`*` 可跨目录）：

| 后缀 | 用途 |
|---|---|
| `.aux` `.log` `.out` `.blg` `.bbl` `.fls` `.fdb_latexmk` `.synctex.gz` | 编译/参考文献/同步中间产物 |
| `.toc` `.lof` `.lot` `.nav` `.snm` `.vrb` | 目录/图表索引/beamer 中间产物 |

- 只有这些后缀被忽略；`.tex` `.bib` `.md` `.toml` `.pdf` 等**照常入账**。
- 忽略的文件**不产生涨、不产生落、不进波及面**，也不会出现在 `protect` 硬面发现里。
- 忽略表在扫树（`_scan`）阶段生效，早于哈希比对——波及面的 `\input` 反查只看入账文件，
  因此忽略项不会把主文件挤出波及面，也不会把无关文件拉进来。

**开关**：

| 开关 | 语义 |
|---|---|
| `--ignore <glob>` | 在默认表之上**追加**一条忽略规则；可重复写多条 |
| `--no-default-ignore` | 关掉默认表（排查「是不是被忽略吃掉了」用）；此时 `--ignore` 仍生效 |

**读数**：输出新增一行 `入账文件：N   忽略：M`（`--json` 里是 `rises` 长度与
`ignored` 列表、生效规则在 `ignore`）。`ignored` 只列「两棵树之间真有差异」的被忽略文件，
两棵树完全相同的产物不会占用这个数。

**验收（`paperkit-dev/` 下跑）**：

```text
$ python3 -m factscribe tide --before ../paper --after /tmp/v4-regen/en
事务：2ec2b0c4f7a35a71    状态：commit
涨：9   落：9   波及面：10   事件：19
入账文件：9   忽略：4
判定：paired ✓   hash_ok ✓   pass_all ✓
忽略明细：main.aux、main.blg、main.log、main.out
EXIT=0

$ python3 -m factscribe tide --before ../paper-zh --after /tmp/v4-regen/zh
事务：560a62fe8614f236    状态：commit
涨：11   落：11   波及面：12   事件：23
入账文件：11   忽略：0
判定：paired ✓   hash_ok ✓   pass_all ✓
EXIT=0
```

批 89b 新增 `tests/test_tide.py::TestIgnore` **10 例**（默认表增/删/改、忽略明细、
非忽略后缀仍入账、`--ignore` 追加、`--no-default-ignore` 回退到 rollback、
`--no-default-ignore` 保留显式 glob、忽略项不改波及面、忽略项不进保护面发现），
全套 40 例。
