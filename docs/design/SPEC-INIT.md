# SPEC-INIT｜上手工件：`init` 生成骨架、`fact add` 记账（批 136）

状态：批 136 冻结（实施依据）。
范围：新增两个 CLI 子命令与模块 `factscribe/scaffold.py`；
不改 `check` / `audit` / `config` / `facts` 的既有判据与退出码；
零第三方依赖（纯标准库）。

一句话：**把「新人进项目」从「复制样例＋手算 sha256＋手写清单」压成两条命令——
`init` 落七个文件，`fact add` 记账并打印该抄哪一行清单；签字永远由人做。**

---

## 1. 为什么需要（问题面）

在批 136 之前，上手只有一条路：`cp -R examples/minimal my-paper`。这条路的
三个坑都由人来扛：

1. **样例自带假账**：`facts/01-core.toml` 是别人的三条事实，改错一个就红；
2. **sha256 要手算**：`source_sha256` 算错或漏写，`check` 直接红
   （`MISSING_SOURCE_SHA256` / `SOURCE_SHA256_MISMATCH`）；
3. **人签清单要手写**：`results/MANIFEST.toml` 的 `[files]` 与 `[manifest]`
   字段格式不熟就写坏。

两条新命令只做「机械记账」，不新增任何判据。`check` / `audit` 仍是唯一的
判定入口；本批不放松、不收紧任何一条。

---

## 2. 命令一：`factscribe init`

```text
python3 -m factscribe init <目录> [--title "..."] [--author "..."] \
    [--lang zh|en] [--force] [--json]
```

| 参数 | 必填 | 语义 |
|---|---|---|
| `directory` | 是 | 目标目录；不存在则连同父目录一起创建 |
| `--title` | 否 | 写进 `[project].title` 与 `main.tex` 的 `\title{}`；缺省按语言取占位标题（`未命名论文` / `Untitled Paper`） |
| `--author` | 否 | 写进 `[project].authors`（单元素数组）与 `main.tex` 的 `\author{}` |
| `--lang` | 否 | `zh`（默认）或 `en`：七个文件的注释与 README 措辞整套切换 |
| `--force` | 否 | 目标目录非空也写；只覆盖本命令的七个同名文件，其他文件不动 |
| `--json` | 否 | stdout 只出 JSON（`command=init`，含 `files` 与 `next`） |

### 2.1 生成面（固定七个文件）

```text
<目录>/
├── paperkit.toml          # [project] title/authors/sections/facts/bib/build/manifest
├── main.tex               # 极简导言区 + \fact 宏 + \input{sections/01-intro}
├── sections/01-intro.tex  # 占位正文；注释里写清「先记账、再绑 \fact{ID}」
├── facts/01-core.toml     # 空账（只有字段说明注释）
├── results/MANIFEST.toml  # 人签清单模板：signed_by / signed_at 留空，[files] 空
├── refs.bib               # 空文件 + 「doi 或 arxiv 必填」的注释
└── README.md              # 四步上手：记账 → 写正文 → 跑审计 → 出报告
```

生成的项目是 **v1 形态**（`[project]` 表、`sections` 是 glob、`facts` 是
glob）——与 `examples/minimal` 同一条判据路，不引入 V3 的 schema 声明。
`refs.bib` 里不写任何 `@type{...}` 模板条目：注释里出现 `@` 会被 bib 解析器
当成真条目，反而制造噪声。

### 2.2 拒绝面（exit 2）

| 情形 | 行为 |
|---|---|
| 目标目录存在且非空（含只有隐藏文件/目录） | 拒绝，提示换空目录或 `--force` |
| 目标路径存在但不是目录 | 拒绝 |
| `--lang` 不在 `zh` / `en` | argparse 用法错（exit 2） |

### 2.3 确定性（冻结约束）

- 不读系统时钟：文件里没有任何「当前时间」；
- 不写绝对路径：文件内容与目标目录在哪无关；
- 模板里的签名时间只用格式占位 `YYYY-MM-DDTHH:MM:SSZ`，不出现具体日期；
- 同参数两次生成 → **逐字节一致**；`--title` 不同 → 内容不同。

### 2.4 输出

人读模式打印一段摘要 + **「下一步（三条命令）」**：

```text
1) python3 -m factscribe fact add <目录> --id A1 --claim "第一句带数字的主张" \
     --value "3/4" --source results/<产物>.md --locator "<位置>"
2) python3 -m factscribe check <目录>
3) python3 -m factscribe matrix <目录>
```

---

## 3. 命令二：`factscribe fact add`

```text
python3 -m factscribe fact add <目录> --id A1 --claim "..." --value "10/16" \
    --source results/swb16.md [--locator "§二"] [--confidence high] \
    [--expr "..."] [--derived-from A1,A3] [--note "..."] [--json]
```

| 参数 | 必填 | 语义 |
|---|---|---|
| `project` | 否 | 项目目录，默认当前目录 |
| `--id` | 是 | 账本键；v1 口径：字母开头，后接字母/数字/`_` `.` `:` `-`，不许空白 |
| `--claim` | 是 | 一句话主张（人话） |
| `--value` | 是 | 正文要绑的数字原文（`10/16` / `56.25%` / `42`） |
| `--source` | 是 | 项目内原始产物相对路径；v1 必须落在 `results/` 下（配了 `project.source_root` 时按它解析，与 `audit` 同口径） |
| `--locator` | 否 | 数字在 `source` 里的位置；强烈建议填（样例与验收命令允许省略） |
| `--confidence` | 否 | `high` / `med` / `low`，默认 `med` |
| `--derived-from` | 否 | 父 fact id，逗号分隔；给了就**必须**同时给 `--expr` |
| `--expr` | 否 | 推算式，例 `(A1.num + A3.num) / (A1.den + A3.den) * 100` |
| `--note` | 否 | 备注（可选） |

### 3.1 校验（全在写盘之前）

1. 项目声明可读（先跑 `init`；V3 项目明确拒绝——本批只服务 v1 骨架）；
2. `facts/01-core.toml` 若已存在，先 `load_toml` 证明没写坏，再追加；
3. `--id` 格式合法且不与现有 id 重复（**大小写不敏感**，与 `check` 的
   `DUPLICATE_ID` 同口径）；
4. `--claim` / `--value` 非空；`--confidence` 在闭集内；
5. `--source` 不接受 URL / 绝对路径 / `..` 越界，且文件必须存在；
6. `--derived-from` 非空而没有 `--expr` → exit 2（推算式是机器复核的唯一依据）。

### 3.2 落账

- **自动算 sha256**：对 `source` 的字节现算，写进 `source_sha256`（小写十六进制）；
- 追加到 `facts/01-core.toml` 末尾（没有该文件就创建，先写字段说明头）；
- 追加**只加不改**：已有条目的字节原样保留，新块前留一个空行；
- 字段顺序固定：`id / claim / value / source / source_sha256 / locator /
  confidence / derived_from / expr? / note?`；
- 字符串按 TOML 基本字符串转义（反斜杠、双引号、换行、制表符），与
  `config` 的 mini 解析器兼容（3.10 回退路径同样能读回）。

### 3.3 输出（两行，且**不代签**）

```text
已写入 fact A1：示例 = 3/4（source results/MANIFEST.toml）
别忘了把这一行加进 results/MANIFEST.toml 并签上你的名字："results/MANIFEST.toml" = "<sha256>"
```

第二行给出可直接粘贴的 `[files]` 行；**工具绝不改人签清单**——
`signed_by`、`signed_at`、`[files]` 一个字节都不动。签不签、怎么签是人的事。

---

## 4. 退出码

沿用既有分层（`constants.py`）：

| 码 | 含义 |
|---|---|
| `0` | 生成/追加成功 |
| `2` | 配置或用法错：目录非空、source 不存在/越界、id 重复、缺 `--expr`、参数非法 |
| `4` | 工具内部错误（未预期异常） |

`init` / `fact add` **不是闸门**：没有红/黄/绿三态，只有「写成了」和「没写」。

---

## 5. 与 `check` 的衔接（不改判据）

`init` + `fact add` 之后跑 `check`，读数按既有口径解释：

- `MANIFEST_UNSIGNED`：清单 `signed_by` 空 → **红**（既有口径；本批不改）；
- `MANIFEST_NO_TIMESTAMP`：`signed_at` 空 → 黄；
- `SOURCE_NOT_SIGNED`：该 source 还没抄进 `[files]` → 红；
- `VALUE_NOT_IN_SOURCE`：`value` 的字面数字没出现在 source 文本里 → 黄
  （验收样例用 `3/4` 对一个清单文件，必然命中这一条）。

也就是说：**新项目第一次 `check` 不绿是设计内的**——它精确指出「还差人签字」
与「这个数在 source 里查不到」。这正是本工具想说的事，不是 `init` 的缺陷。

---

## 6. 非目标

- 不改 `README.md`（主控统一处理）；本批只出 `docs/` 两份文档；
- 不新增判据、不改 `audit` / `check` 的错误码语义；
- 不生成 `.gitignore`、不联网、不调用外部命令；
- 不做 V3 项目的骨架（V3 有更严的审批目标模型，另批处理）。
