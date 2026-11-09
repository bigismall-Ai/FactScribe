# 术语归一化与同义词层实施记录（批 90）

> 规范：`docs/design/SPEC-TERMS.md`。
> 只改 `factscribe style` 的比对入口；**未改 `audit` / `protect` 的判据与
> 退出码**。新判据全黄牌，退出码仍为 `0` / `3`；`TERM_UNREGISTERED`
> 只提示，单独出现时退码仍为 `0`。

## 1. 词表规模

- 来源：`../sia-harness/nomenclator/terms/*.yaml`（153 个词册文件）。
- 落位：`factscribe/terms/glossary.tsv`，运行时不读 `sia-harness`。
- 本次导入实测：**153 个 canonical，465 个表面形式**（canonical 153 ＋
  `en` 字段 153 ＋ 中文别名 159）。
- 生成命令（可重跑，覆盖生成）：

```
env PYTHONPATH=src python3 scripts/import-terms.py
```

文件头注写明来源、生成命令与现算规模；规范与脚本不写死数字。

## 2. 归一化算法

1. **拉丁文**：NFKC → 小写 → 去首尾空白。
2. **中文**：不做分词，正文从左到右做**最长匹配**；同一位置多个候选取
   最长，命中后跳过整个区间。
3. **匹配键**：逐字符 NFKC + 小写后只保留字母、数字、CJK；标点、连字符、
   空白都不进键，因此全半角、标点、空格、连字符差异不参与匹配。
4. **拉丁词边界**：命中后回到原串检查前后字符，前后不得是拉丁字母/数字；
   `id` 不会命中 `did` 内部。中文表面形式不加词边界。
5. `TERM_VARIANT` 的「不同写法」按归一化匹配键计数：`Preregistration`、
   `PRE-REGISTRATION`、`ｐｒｅｒｅｇｉｓｔｒａｔｉｏｎ` 只有一种写法。
6. 白名单（`GLOSSARY.md` ＋ `term-allow.txt`）条目先归一化，再同时以
   匹配键与 canonical 入册。

解析顺序：`style-rules.toml` 的 `term_glossary` → 项目根 `glossary.tsv` →
仓内 `factscribe/terms/glossary.tsv`。项目覆盖只用于项目追加与测试，默认
词表仍由本仓自持。

## 3. 三条判据

| 码 | 算法 | 计数 | 级别 |
|---|---|---|---|
| `TERM_VARIANT` | 单篇内同一 canonical 的不同表面形式数 ≥ `term_variant_min_forms`（默认 2）；报各写法与行号 | 参与，触发即退 3 | 黄 |
| `TERM_UNREGISTERED` | 标题 / 首句的「术语样」候选归一化后不在册（含多词无缝覆盖） | **不参与**；不进 `fired` / `summary.triggered`，单独出现退 0 | 提示 |
| `HEADING_ECHO` / `TERM_FIRST_IN_HEADING` | 先按 canonical 归一，再走原判据；同义词视同同词 | 同原规则 | 黄 |

实现：

- 新模块 `factscribe/terms.py`：TSV 装载、匹配键、trie 最长匹配、白名单归一；
- `factscribe/style.py`：`_glossary_for` / `_term_allowlist` / `_new_content_terms`
  / `_heading_echo` 改按 canonical；新增 `_term_variant_findings` 与
  `_unregistered_findings`；
- `style-rules.toml`：`term_variant_min_forms = 2`，项目覆盖键 `term_glossary`；
- 纯标准库；不改 `audit.py` / `protect.py`。

## 4. 测试

`tests/test_terms.py`：**27 例**（全离线）。覆盖：

- 中文同义归一、拉丁大小写/全半角/连字符、标点与空白不参与匹配；
- 最长匹配边界：`相关工作` 与 `相关工作里`、`机制` 与 `提示词对机制`；
- `TERM_VARIANT` 三写法正例、单写法负例、大小写差异负例、阈值可调、
  不跨文件；
- `TERM_UNREGISTERED` 标题/首句提示、退码仍 0、白名单归一后命中；
- `HEADING_ECHO` 换同义表述仍报、带新信息不报、垫话同义仍报；
- `TERM_FIRST_IN_HEADING` 同义定义视为已定义、未定义仍报、白名单别名命中；
- 导入脚本可重跑且覆盖生成。

全套测试：**443 例**（本批新增 `tests/test_terms.py` 27 例；验收时基线
含并行批 89b 的测试）。

## 5. 门禁

工作区（含并行批未提交改动）之外的干净基线验证：把本批文件复制到
`HEAD` 的独立 worktree，三个 CI Python 版本均为 `Ran 433 tests OK`。

提交后官方门禁（干净克隆只含已提交文件，HEAD `f4b3d9c`）：

```
env PYTHONPATH=src python3 -m unittest discover -s tests
Ran 443 tests ... OK
./scripts/preflight-ci.sh
步骤 3/4：Python 3.10 / 3.11 / 3.12 各 Ran 443 tests
步骤 4/4：examples/minimal audit exit=1（红，符合预期）
结论：本地等价 CI 全绿——可以推。
```

## 6. `HEADING_ECHO` 漏报修复前后对比

同一夹具（`预注册` 为 canonical，`事前登记` 为其同义词）：

```latex
\section{预注册}

事前登记。
```

| 版本 | `heading_echo` | findings | 说明 |
|---|---|---|---|
| 修复前（HEAD `4069ca9`） | `0` | `[]` | 字面比对把「事前登记」当新信息，**漏报复述** |
| 修复后（本批） | `1` | `HEADING_ECHO`（另 `TERM_VARIANT`：一篇两写法） | 同义词归一到同一 canonical，**仍判复述** |

同一机制修复 `TERM_FIRST_IN_HEADING` 的字面误报：

```latex
\section{预注册流程}

事前登记流程是在收集数据前固定假设与分析计划的做法。
```

| 版本 | `term_first_in_heading` | 说明 |
|---|---|---|
| 修复前 | `1` | 首句用了同义词，字面找不到标题词，**误报未定义** |
| 修复后 | `0` | 同义词命中同一 canonical，视为已定义 |

两处漏洞（`HEADING_ECHO` 漏报、`TERM_FIRST_IN_HEADING` 字面误报）均已修复。
