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

---

## 9. 快照与回滚（批 106）

> 规范：`docs/design/SPEC-TIDE.md` §12。
> 一句话：**改完存一份快照；回滚＝先全校验再把快照逐字节写回，任何一处不符就一个字节也不写。**

### 9.1 为什么

比对模式只回答「改了什么」，不回答「改坏了怎么退」。原来退回去靠人手备份目录——
备份是否完整、是否同一版本、混进没混进构建产物，全靠人记。快照把这件事变成
内容寻址的机械事实：清单＋blob，ID 是清单字节的哈希，恢复前逐条复算。

### 9.2 布局

```text
<库根>/snapshots/<快照ID>/manifest.tsv   # 相对路径 \t sha256 \t 字节数，按路径升序
<库根>/blobs/<sha256>                    # 内容寻址，同内容只存一份
```

- 快照ID＝`manifest.tsv` **字节**的 sha256（64 位全宽）；对外显示前 16 位。
- 恢复接受全宽或任意唯一前缀（4–64 位十六进制）；前缀命中多个快照即配置错。
- 清单无时间戳、无绝对路径、无随机数；行尾 `\n`，UTF-8。
- blob 与清单都走「临时文件 + 原子替换」，不会留下半个文件。

### 9.3 保存

1. 扫 `--after` 目录（普通文件；跳过隐藏路径与符号链接；复用比对侧忽略表）；
2. 每文件算 sha256 与字节数，拼出按路径升序的清单；
3. 逐个写 `blobs/<sha256>`：已存在且长度相同即复用（**去重**），否则写；
4. 清单字节取 sha256 → 快照ID → 写 `snapshots/<ID>/manifest.tsv`。

先写 blob 后写清单：清单存在即代表整份快照可还原；中途失败只会留下无主 blob，
不会被任何快照引用。库根若落在被快照目录内，扫树时整库跳过（快照不自吞）。
`--before` 在保存模式下不参与——快照是纯内容副本，不判断「改了什么」。

### 9.4 恢复（失败关闭）

顺序写死，前四步全部通过之前**不创建目标目录、不写任何文件**：

1. 解析快照ID（前缀唯一命中），清单必须存在；
2. `sha256(清单字节)` 必须等于快照目录名（**清单被改过即失败**）；
3. 清单逐行校验：三字段、安全相对路径（无开头 `/`、无 `..`、无空段）、
   64 位小写十六进制哈希、非负整数长度、路径升序且不重复；
4. 逐条验 blob：存在、长度等于清单、`sha256(blob)` 等于清单；
5. 全过后才建目录逐文件写（原子替换），写完回读复算 sha256 与长度。

校验失败＝**整份不落**，退出码 1，`--json` 给 `ok=false` 与逐条 `reasons`；
结构性错误（快照不存在、前缀歧义、清单格式坏）＝`CONFIG_INVALID`，退出码 2。
`--into` 里不在清单中的文件不动，清单中的文件被覆盖。

### 9.5 读数（真实语料 `../paper`，库根落临时目录）

```text
$ python3 -m factscribe tide --after ../paper --snapshot /tmp/tide-store
== factscribe tide 快照 ==
快照ID：281996f4be561df7（全宽 281996f4…cc9f4a）
文件：50   字节：328448
blob：新增 50   复用 0
清单：snapshots/281996f4…cc9f4a/manifest.tsv
忽略：5 项（main.aux、main.bbl、main.blg、main.log、main.out）
EXIT=0

$ python3 -m factscribe tide --restore 281996f4be561df7 --into /tmp/tide-restored --snapshot /tmp/tide-store
== factscribe tide 快照还原 ==
快照ID：281996f4be561df7（全宽 281996f4…cc9f4a）
文件：50   字节：328448
校验：50/50 通过
结果：已还原 50 个文件（写后逐字节复算通过）
EXIT=0
```

还原后对两棵树做逐文件字节比对（同一忽略表）：50 个文件的键集合与每个文件的字节
**全部一致**。

改掉其中一个 blob 的字节后再恢复：

```text
$ python3 -m factscribe tide --restore 281996f4be561df7 --into /tmp/tide-tampered --snapshot /tmp/tide-store
校验：49/50 通过
结果：失败关闭，未写任何文件
原因：
- 哈希不符：appendix/c_debuglog.tex（blob 被改过）
EXIT=1
```

目标目录根本没有被创建——失败关闭不是「删掉写坏的」，而是「验不过就不动笔」。

`--json` 里保存侧有 `mode="snapshot"`、`snapshot_id`（全宽）、`snapshot`（前 16 位）、
`files`、`bytes`、`blobs_new`、`blobs_shared`；恢复侧有 `mode="restore"`、
`files`、`verified`、`written`、`ok`、`reasons`。

### 9.6 测试数

`tests/test_tide_snapshot.py`：**26 例**（全离线，走真实 CLI）：

| 组 | 例数 | 要点 |
|---|---|---|
| 保存 | 3 | 清单按路径升序且逐条哈希/长度正确；人读输出含 16 位 ID 与文件数；blob 名＝内容哈希 |
| 往返 | 3 | 文本＋嵌套＋空文件＋二进制一次全比；空文件 sha256＝`e3b0c442…`、长度 0；大二进制逐字节 |
| 去重 | 2 | 两个相同文件共用一个 blob；第二趟保存 `blobs_new=0` |
| 确定性 | 2 | 连存两次 ID 与清单字节不变；ID＝清单字节重算的 sha256 |
| 忽略 | 4 | `.aux/.log/.synctex.gz` 不进清单也不进 blob 库；`--ignore` 追加；库根在源目录内不自吞；缺省库根 `./.tide` 可存可恢复 |
| JSON | 2 | 保存侧 ID/文件数/字节数；恢复侧 `ok/verified/files` |
| 失败关闭 | 4 | blob 内容被改、blob 缺失、清单被改（哈希不符）、清单长度被改（ID 同步换名）→ 均退出码 1、目标目录零写入 |
| 恢复 | 5 | 16 位前缀恢复；不动无关文件；人读读数；未知 ID → 2；前缀歧义 → 2 |
| 用法 | 1 | 保存缺 `--after`、恢复缺 `--into`、恢复带 `--after`、比对缺 `--after` 均 → 2 |

### 9.7 门禁输出

```text
$ env PYTHONPATH=src python3 -m unittest discover -s tests
Ran 708 tests in 38.9s
OK

$ ./scripts/preflight-ci.sh --fast
步骤 1/4：外部依赖 ......... ✓ pdftotext / pdfinfo 齐备
步骤 2/4：干净克隆（--fast：跳过，直接用工作区）
步骤 3/4：测试矩阵 ......... ✓ 3.10 / 3.11 / 3.12 各 Ran 708 tests
步骤 4/4：验收样例 ......... ✓ examples/minimal audit exit=1
本地等价 CI 全绿。
```

> 读数说明：708 是当次全套例数（本批 26 例 + 并行批新增），随仓内其它批变动而变；
> 本批自己的准数是 `test_tide_snapshot.py` 的 26 例。
