# 上手工件实施记录（批 136）

> 规范：`docs/design/SPEC-INIT.md`。
> 新增 `factscribe init` / `factscribe fact add` 两个子命令与模块
> `factscribe/scaffold.py`；**未改** `check` / `audit` / `config` / `facts`
> 的判据、错误码与退出码；`README.md` 未动；零第三方依赖（纯标准库）。

一句话：新项目从「复制样例 + 手算 sha256 + 手写清单」变成
`init` 一条 → `fact add` 一条 → 看输出的两行提示。工具只记账，不签字。

## 1. 交付物

| 路径 | 内容 |
|---|---|
| `factscribe/scaffold.py` | 七文件模板（zh/en）、确定性落盘、`fact add` 校验/算 sha256/追加 |
| `factscribe/cli.py` | 注册 `init` 与 `fact add`（唯一改动的既有文件） |
| `tests/test_init.py` | 20 例：生成面、拒绝面、确定性、双语、输出与 `--json` |
| `tests/test_fact_add.py` | 19 例：正常添加、sha256、追加不覆盖、五类拒绝、不代签、端到端 |
| `docs/design/SPEC-INIT.md` | 命令契约、确定性约束、拒绝面、与 `check` 的衔接 |
| `docs/implementation/INIT.md` | 本件 |

## 2. 实现选择（以及为什么）

| 决定 | 理由 |
|---|---|
| 模板用 `__TITLE__` 等占位符 + `str.replace`，不用 `str.format`/f-string | LaTeX 模板里全是 `{}`，格式化会把 `\fact{ID}` 吃成 KeyError |
| `write_bytes(text.encode("utf-8"))` | 固定 LF、无 BOM；逐字节可比对 |
| 标题/作者进 `.tex` 前过 `tex_escape` | 作者名里 `&`、`%`、`_` 不会把 `main.tex` 搞坏；`paperkit.toml` 用 `toml_string` 原样保留 |
| `--locator` 设为可选 | 验收命令（SPEC 第四节）不带它；强制会让真跑 exit 2。空 locator 不影响 `check` 判据，但 SPEC 与 README 都建议填 |
| `--source` 额外校验「必须在 `results/` 下」 | 只查「项目内存在」会把 `check` 必红的账写进去（`SOURCE_OUTSIDE_RESULTS`）；配了 `source_root` 时按 `audit.source_base` 同口径放行 |
| id 判重走 `load_facts` 的 `id_key` | 与 `check` 的 `DUPLICATE_ID`（大小写不敏感）同口径，不在 CLI 里另造一套 |
| 追加用字节拼接而非「读文本—重写」 | 旧条目字节原样保留（`test_second_fact_keeps_the_first_block_intact` 直接判前缀） |
| 空账也允许 `init` 成功，`check` 才报「facts 为空」 | 账的判据留在闸门里；`init` 不是闸门 |
| V3 项目拒绝 `fact add` | V3 的证据是审批目标 + `runs/`，没有 `results/MANIFEST.toml`；按 v1 写法追加会误导 |

## 3. 验收（真跑，macOS / Python 3.14.4）

命令与输出逐字如下（仓根 `paperkit-dev/` 执行，`PYTHONPATH=src`）：

### 3.1 `init`

```text
$ python3 -m factscribe init /tmp/newpaper --title "Demo" --author "张三"
已生成最小项目：/tmp/newpaper（lang=zh，7 个文件）
  paperkit.toml
  main.tex
  sections/01-intro.tex
  facts/01-core.toml
  results/MANIFEST.toml
  refs.bib
  README.md

下一步（三条命令）：
  1) python3 -m factscribe fact add /tmp/newpaper --id A1 --claim "第一句带数字的主张" --value "3/4" --source results/<产物>.md --locator "<位置>"
  2) python3 -m factscribe check /tmp/newpaper
  3) python3 -m factscribe matrix /tmp/newpaper
（exit 0）
```

### 3.2 `fact add`

```text
$ python3 -m factscribe fact add /tmp/newpaper --id A1 --claim "示例" \
    --value "3/4" --source results/MANIFEST.toml
已写入 fact A1：示例 = 3/4（source results/MANIFEST.toml）
别忘了把这一行加进 results/MANIFEST.toml 并签上你的名字："results/MANIFEST.toml" = "627444f101eb303fa330c4eb014eed35804bd28a8fc8c1685169ca8d9e835a2a"
（exit 0）
```

`627444…` 与 `sha256sum /tmp/newpaper/results/MANIFEST.toml` 一致；
`results/MANIFEST.toml` 之后逐字节未变（`[files]` 仍为空）。

### 3.3 `check`

```text
$ python3 -m factscribe check /tmp/newpaper
== paperkit check ==
project : /tmp/newpaper
facts   : 1 条（id 1 个，source 均在位 1 条，sha 钉住 1 条）

[黄] 2 处（账本自相矛盾/未签名/未核验——必须列出来给人看）
  1. VALUE_NOT_IN_SOURCE    facts/01-core.toml:18  →  A1
     fact 'A1' 的 value 数字 3、4 没有出现在 source 里（内容回查失败）
  2. MANIFEST_NO_TIMESTAMP  results/MANIFEST.toml
     清单 results/MANIFEST.toml 缺 signed_at（签的时间点）

[红] 2 处
  1. MANIFEST_UNSIGNED      results/MANIFEST.toml
     清单 results/MANIFEST.toml 没有 signed_by——没人签的清单不算锚
  2. SOURCE_NOT_SIGNED      facts/01-core.toml:18  →  A1
     fact 'A1' 的 source results/MANIFEST.toml 不在人签清单里——没人确认过它

结论：红（有违例）（退出码 1）
```

**为什么不是绿（也不是纯黄）**：`check` 的既有口径把「清单没有
`signed_by`」判**红**（`audit.py` 的 `MANIFEST_UNSIGNED`，`tests/test_factscribe.py`
钉死了它在 `issues` 里），本批不改判据。两条黄另有出处：

- `VALUE_NOT_IN_SOURCE`：验收样例故意拿 `3/4` 去对一个清单文件，文本里当然
  没有 `3`、`4` 这两个数——这正是「value 要在 source 里查得到」的提示；
- `MANIFEST_NO_TIMESTAMP`：`signed_at` 留空。

把 `results/` 换成真产物、把该行抄进 `[files]` 并签上 `signed_by` / `signed_at`
之后，同样的账就会转绿。`init` 的 README 四步与 `fact add` 的第二行提示都在
指这一步。

## 4. 测试

```bash
env PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_init.py'     # 20 例
env PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_fact_add.py' # 19 例
env PYTHONPATH=src python3 -m unittest discover -s tests                       # 1106 例全绿
./scripts/preflight-ci.sh                                                      # 干净克隆 + 3.10/3.11/3.12
```

`test_init.py` 覆盖：七文件齐全、父目录自动创建、TOML 回读与 v1 形态、空账 +
空签名、`main.tex` 宏/`\input`、标题作者转义、非空目录/隐藏文件/目标是文件
三类拒绝、`--force` 覆盖且保留他人文件、双跑逐字节一致、换标题即不同、无绝对
路径、无具体日期、zh/en 两套措辞、未知语言、三条下一步命令、`--json` 成功面与
错误面。

`test_fact_add.py` 覆盖：字段落位、sha256 等于现算、confidence 默认、两行提示、
「不代签」字节级断言、缺账文件自建、`--json`、追加不覆盖、derived 记录父项与
算式、note、id 重复（含大小写）、source 不存在、source 越出 `results/`、绝对
路径、`--derived-from` 缺 `--expr`、id 格式、confidence 非法、locator 可省略、
端到端 `init → fact add → check`（打印 `结论：` 并点名 `MANIFEST_UNSIGNED` /
`VALUE_NOT_IN_SOURCE`）。

## 5. 兼容与边界

- Python 3.10 起可用：只用 `argparse` / `pathlib` / `hashlib` / `re`，
  没有 3.11+ 语法；生成的 TOML 同时能被 `tomllib` 与 `config._mini_toml` 读回；
- 既有命令零行为变化：`cli.py` 只加两个 parser 与两个 handler；
- `examples/minimal` 未动，验收步（audit exit=1）不受影响；
- `README.md` 未改（主控处理）。
