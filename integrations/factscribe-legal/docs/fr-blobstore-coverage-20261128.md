# 法国法条全量快照（corpus-fr-v1）覆盖统计与对账报告

- 报告日期：2026-11-28
- 本仓：bigismall-Ai/FactScribe
- 快照来源：GitHub Release `corpus-fr-v1`，唯一资产 `blobs.sqlite`
- 逐件索引：`integrations/factscribe-legal/corpus-bulk/fr-blobstore-manifest.jsonl`
  （343,604 行，90,812,996 字节）
- 取件脚本：`integrations/factscribe-legal/scripts/ingest_fr_blobstore.py`（本次新增）

---

## 0. 一句话结论

快照**全量与仓内逐件索引 100% 对得上**：manifest 的 343,604 件**逐件取出、逐件校验**
（sha256、解压后字节数、压缩载荷长度）全部一致，0 件不符；171,801 张证据卡里钉的
`OFFICIAL_XML_SHA256` 也与配套 XML 块**全部一致**。仓内已物化的 3 件法条
（8 个文件）**没有一件与快照逐字节相同**，但这**不是取件后被改动**——它们来自另一份
DILA 增量（2026-11-15 vs 快照的 2026-11-08），法条正文一字未变。全量里**仓内完全
没有的还有 343,596 件**。

---

## 1. 快照形态与字段语义（有一处与通行说法相反，需订正）

块库 `blobs.sqlite`（322,752,512 字节，sha256 `4ae41c52c5866a8eac692453588004e3aef5a27bc2f6943eefbb6adabe156fda`）schema：

```sql
CREATE TABLE blobs(sha16 TEXT PRIMARY KEY, sha256 TEXT NOT NULL, kind TEXT NOT NULL,
  bytes_in INTEGER NOT NULL, bytes_out INTEGER NOT NULL, codec TEXT NOT NULL,
  dict_sha16 TEXT, payload BLOB NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE dicts(sha16 TEXT PRIMARY KEY, bytes BLOB NOT NULL,
  sample_bytes INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE counters(name TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE gc_log(id TEXT NOT NULL, bytes INTEGER NOT NULL, reason TEXT NOT NULL, ...);
```

**字段语义（实测钉死，manifest 的 `bytes`/`bytes_out` 与「压缩/解压」的直觉是反的）**：

| manifest 字段 | 块库列 | 真实含义 | 实测依据 |
|---|---|---|---|
| `sha256` | `sha256` | **解压后**内容的 sha256 | `fr/0-1.card.txt` 解压后 518 B，sha256 与 sha256 列、manifest 三者一致；对 payload 取哈希则不一致 |
| `bytes` | `bytes_in` | **解压后**字节数 | 解压后长度 == `bytes` == `bytes_in`，171,801/171,801 成立 |
| `bytes_out` | `bytes_out` | **压缩后**入库载荷长度 | `LENGTH(payload) == bytes_out`，343,676/343,676 成立 |
| `dict_sha16` | `dict_sha16` | 压缩字典 | 全库法国件用同一块：`79a30ff9f31903a5`（131,072 字节） |
| `codec` | `codec` | `zstd+dict` | 343,635 条 `zstd+dict` + 41 条 `zstd`（无字典，与法国件无关） |

> 也就是说：**压缩后的字节数是 `bytes_out`，解压后的是 `bytes`**。
> 拿 `bytes_out` 去比解压后长度会全部对不上，属字段名与直觉相反，不是数据错。

**块库不带 path**。`path -> sha256` 的对应只存在于仓内 manifest，所以取件必须是
「manifest 定位 + 块库取字节」两步，单靠块库还原不出目录树。

---

## 2. 覆盖统计（只用 manifest，纯本地）

| 指标 | 读数 |
|---|---|
| manifest 总行数 | 343,604（0 行解析失败，9 个字段的组合 343,604/343,604 全同） |
| kind 分布 | `fr-law-card` 171,801 ／ `fr-law-xml` 171,801 ／ `fr-law-index` 1 ／ `fr-law-view` 1 |
| 唯一 path | 343,604（**重复 0**） |
| 唯一 sha256 | 343,604（**同一 sha256 挂在多个 path 上的：0**） |
| `dedup` 标志 | 343,604 条全为 `false`（即无重复内容被复用） |
| 唯一 sha16 | 343,604；且**恒等于 sha256 的前 16 位**（块库全库 343,676 行同样成立） |
| 解压后字节合计 | **964,360,396** B（≈919 MiB） |
| 压缩载荷合计 | **216,529,485** B（≈206 MiB） |
| 分 kind 解压/压缩 | xml 806,219,865 / 142,669,557；card 90,392,394 / 69,126,399；index 44,309,973 / 2,552,258；view 23,438,164 / 2,181,271 |

### 2.1 命名与编号规则

path 形如 `fr/<法条号主干>.xml` 与 `fr/<法条号主干>.card.txt`，
**主干 = 法条号把非 `[A-Za-z0-9-]` 的字符逐位换成一个 `_`**（一位对一位，不合并）。

例：`(1 à 4)` → `_1___4_`；`D641-10-1` → `D641-10-1`；`R 421-80` → `R_421-80`；
`ANNEXE 22  32` → `ANNEXE_22__32`。该规则在**全部 171,801 条**上成立（见 §5.2）。

命名族分布（按件，card+xml 各算一件）：

| 族 | 件数 | 占比 |
|---|---|---|
| 字母开头（法令类 L/R/D/A…） | 290,688 | 84.6% |
| 其它（含 `_` 等） | 20,272 | 5.9% |
| 数字多段（`1-1-1`） | 20,137 | 5.9% |
| 数字-数字（`0-1`） | 9,965 | 2.9% |
| 纯数字（`01`） | 2,540 | 0.7% |
| index.json / view_current.jsonl | 2 | — |

字母开头的首字母分布：R 139,350 ／ L 83,148 ／ D 47,866 ／ A 15,808 ／ C 804 ／ T 648
／ G 504 ／ S 428 ／ P 352 ／ M 312 ／ U 204 ／ O 198 ／ E 172 ／ N 146 ／ X 136 ／ Q 114
／ V 114 ／ I 112 ／ J 82 ／ W 80 ／ B 46 ／ Y 44 ／ F 14 ／ H 4 ／ K 2。
带 `_bis` 1,005、`_quater` 626、`_ter` 487。

**分卷/编号规则**：第一段（`-` 前）就是法典分部号，共 **43,377** 个不同前缀；
**每个前缀下 `.card.txt` 与 `.xml` 严格 1:1 配对**（前缀计数无一例外）。
按 `-` 分段深度：1 段 38,264 ／ 2 段 241,596 ／ 3 段 60,790 ／ 4 段 2,822 ／ 5 段 124
／ 6 段 4 ／ 7 段 2。

---

## 3. 与仓内已物化 `corpus/fr/` 的重叠与对账

仓内 `integrations/factscribe-legal/corpus/fr/` 共 8 个文件。这 8 个文件名**全部**在
manifest 里有同名 path，但**逐字节一致的 0 件**：

| 仓内文件 | 仓内 sha256(前16) | 快照同路径 sha256(前16) | 字节数 仓内→快照 | 结论 |
|---|---|---|---|---|
| D641-10-1.xml | 19f51c1ce269eab2 | 430080b3a2ea7c98 | 4,361 → 3,901 | 不同增量 |
| D641-10-1.card.txt | fca8182f7fbd8866 | 083177218cecb29d | 522 → 536 | 不同增量 |
| L594-8.xml | bf4fef200d935d11 | 3b1cbbdcf3c6146e | 3,286 → 3,285 | 不同增量（差 1 字节空白） |
| L594-8.card.txt | 786130fa0c8a6fac | 4efe8ac910f4393e | 504 → 518 | 不同增量 |
| R557-6-14-1.xml | b122036c5474bd86 | 55e44d74de267da3 | 3,020 → 3,019 | 不同增量（差 1 字节空白） |
| R557-6-14-1.card.txt | 0b912fe11f9f5a60 | ee5a993462ace2df | 514 → 528 | 不同增量 |
| index.json | a1570c2925054470 | c880aeb01f498d82 | 866 → 44,309,973 | 仓内是 3 条版，快照是 171,801 条全量版 |
| view_current.jsonl | b823ceba6eabb174 | 408ce720d3b435c5 | 415 → 23,438,164 | 仓内是 3 行，快照是 171,801 行 |

### 3.1 这 8 件「对不上」的性质：**不同 DILA 增量，不是取件后被改**

证据（三件全部同构）：

- 卡片字段逐项相同（NUM / CODE_ID / CODE_TITLE / LEGIARTI / ETAT / DATE_DEBUT / DATE_FIN），
  只差三处：`POOL_ASOF`（仓内 `2026-11-15` vs 快照 `20261108`）、
  `SOURCE`（仓内 `LEGI_20261115-205552.tar.gz` vs 快照
  `Freemium_legi_global_20261108-140000.tar.gz`）、以及被钉进去的 XML 哈希与字节数。
- **`TEXT_CHARS` 三件完全相同**（364 / 414 / 179）——法条正文一字未改。
- XML 逐行 diff：D641-10-1 只**多了 2 条 2026-11-09 的 `<LIEN>` 引文**（Arrêté du
  9 novembre 2026）加几个空行；L594-8 与 R557-6-14-1 只差 1 个空行。

即：**仓内那 3 件比快照更新**（仓内取自 11-15 增量，快照取自 11-08 增量），
法条正文相同，差异是增量带来的新增引文与空白。**不是取件后被改动**。

### 3.2 还缺多少

- **仓内完全没有的（连同名 path 都没有）：343,596 件**（占 99.997%）
  - 法条 XML 未物化 **171,798** 件
  - 证据卡未物化 **171,798** 件
  - 全量 index.json（171,801 条版）未物化 1 件
  - 全量 view_current.jsonl（171,801 行版）未物化 1 件
- 同名但内容来自另一增量：**8 件**（上表）
- 同名且逐字节一致：**0 件**

---

## 4. 块库里比 manifest 多出来的 72 块

块库共 343,676 行，manifest 343,604 行。差 **72**：

- **41 条 `text`**：无字典的 zstd，内容是 `"A\n\nalpha"`、`"Home\n\nroot\n/a"`
  这类冒烟测试短串；块库 `counters` 表记 `dedup_hits=41`，`gc_log` 记
  `smoke-test cleanup (it-cc batch subagent)`——是它线子代理留下的残块。
- **31 条 `cn-flk-tree`**：中国线 FLK 树接口的 JSON 响应（用另一块字典
  `cbbc21a85ac31669`），created_at 2026-11-08～2026-11-17，**与法国语料无关**。

**manifest 里的 sha256 在块库中缺失：0 个。块库内 sha256 全唯一（0 重复内容）。**
即：没有「manifest 声称有、块库里拿不到」的洞；多出来的 72 块是旁线残块，
**建议在取件脚本里按 manifest 的 path 驱动取件，天然不会碰它们**。

---

## 5. 取件与验证读数

### 5.1 抽样验证（用本次交付的脚本 CLI）

```bash
uv run --with zstandard python3 integrations/factscribe-legal/scripts/ingest_fr_blobstore.py \
  --blobs /private/tmp/fs-fr-blobstore/blobs.sqlite \
  --manifest integrations/factscribe-legal/corpus-bulk/fr-blobstore-manifest.jsonl \
  --sample 60 --verify-only --json
```

- **命中率 60/60 = 100%**；失败 0；sha256 不符 0；索引里找不到 0。
- kind 覆盖：`fr-law-card` 29 ／ `fr-law-xml` 29 ／ `fr-law-index` 1 ／ `fr-law-view` 1
- 覆盖 **59 个不同 path 前缀**（`D129`、`L123`、`L133`、`321`、`ANNEXE_22__32`、
  `7_ter_A`、`Annexe_II___Tableau_n__39` 等）
- 解压后合计 67,884,843 B；压缩载荷合计 4,766,954 B

### 5.2 全量逐块对账（把抽样换成全量，7.3 秒）

对 manifest 的**全部 343,604 件**做取块→解压→校验：

- **对上 343,604 ／ 对不上 0**
- 分 kind 解压字节合计与 §2 表**逐位相同**
- 证据卡内钉的 `OFFICIAL_XML_SHA256` vs 配套 XML 块 sha256：**对上 171,801 ／ 对不上 0 ／ 缺配对 0**

### 5.3 path ↔ index.json 键的对应规则（**已确定，不需再等快照**）

- `fr/index.json`：`generator="fetch_corpus.py 0.1"`、`pool_asof="20261108"`、
  `provisions` **171,801 条**，每条 = `{code_id, code_title, date_debut, date_fin,
  etat, legiarti, xml_file}`，**键就是法条号**（如 `D641-10-1`、`(1 à 4)`）。
- `provisions[法条号].xml_file` **171,801/171,801** 命中 manifest 的 XML path；
  由它推出卡片 path 也 **171,801/171,801** 命中。
- §2.1 的 slug 规则把「法条号」映射到「文件名主干」，**171,801/171,801 成立**。
- `fr/view_current.jsonl`：**171,801 行**，字段恒为
  `{date_debut, date_fin, etat, id, num, num_param}`；`num` 与 `provisions` 的键
  **完全同集**，`id` == `provisions[].legiarti` **171,801/171,801**，
  日期/状态不一致 **0** 条。
- 涉及法典（`code_id`）**1,085** 部；`legiarti` 全唯一；`etat` 分布：
  VIGUEUR 81,942 ／ MODIFIE 37,156 ／ ABROGE 39,541 ／ TRANSFERE 4,959 ／
  VIGUEUR_DIFF 4,096 ／ ABROGE_DIFF 1,694 ／ PERIME 1,107 ／ MODIFIE_MORT_NE 1,036
  ／ ANNULE 180 ／ DISJOINT 32 ／ DEPLACE 7 ／ 空 51。

---

## 6. 逐件来源账本（`manifest.json`）缺失的处理方案

ATTRIBUTION 写明逐件级来源与取数时间记在「取件批的 manifest.json（留盘账本，随
corpus-bulk 数据目录存工作机，不入仓）」。该文件**不在仓、本机也没有**。

### 6.1 能从快照反推出来的（够重建账本的绝大部分）

账本条目形如 `dila://increment/20261108#LEGIARTI<id> ＋ sha256`，三段都可复原：

| 账本要素 | 从哪来 | 可靠性 |
|---|---|---|
| 增量号 `20261108` | `index.json.pool_asof` ＋ 每张卡的 `POOL_ASOF: 20261108` ＋ `SOURCE: …Freemium_legi_global_20261108-140000.tar.gz` ＋ ATTRIBUTION 的包名 | 4 处独立一致 |
| 逐件 `LEGIARTI<id>` | `index.json.provisions[法条号].legiarti`；`view_current.jsonl` 的 `id` 是同一集合 | 171,801/171,801 互相吻合，且 LEGIARTI 全唯一 |
| 逐件 `sha256` | manifest 的块级 sha256；每张卡内 `OFFICIAL_XML_SHA256` 钉的正是配套 XML 的哈希 | 171,801/171,801 交叉核对通过 |
| 条文↔卡片配对 | `xml_file` → `fr/<xml_file>` 与 `fr/<stem>.card.txt` | 171,801/171,801 |
| 件的类别与字节数 | `kind`／`bytes`／`bytes_out` | 343,604/343,604 |

**方案**：以「仓内 manifest（path↔sha256↔字节）」为骨架，补上
「`index.json.provisions[].legiarti` + 增量号 20261108」这一列，即可**完整重建**
一份等价的逐件来源账本：

```
path=fr/<slug(法条号)>.xml   dila://increment/20261108#LEGIARTI000034616245  sha256=<manifest sha256>
```

重建时**不需要反解 slug**：`index.json` 的键就是法条号，直接
`provisions[法条号].xml_file` → manifest path → sha256 即可。唯一性已核：
法条号 171,801 个、`xml_file` 171,801 个、`legiarti` 171,801 个，
`(法条号, xml_file)` 对 171,801 个——三者都是严格一一，账本无二义。

### 6.2 反推不出来的（就这一样）

**逐件的「取数时间」——每件从 DILA 拉下来的墙钟时刻，快照里没有。**

快照里能拿到的只有三档更粗的时间：

- 包级下载日期 **2026-11-16（UTC）**（ATTRIBUTION）；
- 增量号 **20261108**（数据自身的 as-of）；
- 块入库时刻 `blobs.created_at`，法国件集中在 **2026-11-17T06:32:14Z～06:35:59Z**
  （约 4 分钟内写完）——这是「写进块库的时刻」，不是「从 DILA 拉的时刻」。

若原 manifest.json 记的是逐件抓取时刻，那部分**只能退到上面三档粒度**，无法逐件复原。
**建议**：账本里把该列写成可继承的两级结构
（`source.increment=20261108` + `source.package_downloaded_at=2026-11-16` +
`source.blob_written_at=<该块 created_at>`），并注明逐件抓取时刻已随原文件丢失；
这样下游（合同层、五元组收据）引用的是可核的字段，不引用不可核的。

---

## 7. 取件脚本用法

新增 `integrations/factscribe-legal/scripts/ingest_fr_blobstore.py`，四步各自可测：
取块 `fetch_payload` → 解压 `decompress` → 校验 `verify_sha256` → 落盘 `write_blob`。

- **sha256 对不上必须报错**（`Sha256Mismatch`），CLI 退出码 4，绝不静默跳过；
  实测「块在、查得到、但内容哈希对不上」这一最危险形态被单测锁住，且**不落盘**。
- 落盘路径拒绝绝对路径与 `..`，不许越出 `--out-dir`。
- 只取指定 path 列表，避免全量解包：

```bash
uv run --with zstandard python3 integrations/factscribe-legal/scripts/ingest_fr_blobstore.py \
  --blobs /private/tmp/fs-fr-blobstore/blobs.sqlite \
  --manifest integrations/factscribe-legal/corpus-bulk/fr-blobstore-manifest.jsonl \
  --paths-file want.txt --out-dir /tmp/fr-out
```

- 取块走块库主键 `sha16`（`sha256` 列**没有索引**，按 sha256 直查等于每件全表扫；
  本次全量对账优化前就是被这一点拖到超时，改走主键后 343,604 件 7.3 秒跑完）。

单测：`integrations/factscribe-legal/tests/test_fr_blobstore_ingest.py`，31 例。

```bash
# CI 口径（纯标准库，2 例真实 zstd 往返自动跳过）
python3 -m unittest discover -s integrations/factscribe-legal/tests -p 'test_fr_blobstore_ingest.py' -v
# 带真实 zstd
uv run --with zstandard python3 -m unittest discover -s integrations/factscribe-legal/tests -p 'test_fr_blobstore_ingest.py' -v
```

---

## 8. 复现与快照落点

- 快照落点（**仓外**）：`/private/tmp/fs-fr-blobstore/blobs.sqlite`
- 字节数：322,752,512（与 GitHub release 的 content-length 一致）
- sha256：`4ae41c52c5866a8eac692453588004e3aef5a27bc2f6943eefbb6adabe156fda`
- 下载：本机直连 GitHub 只有 ~20 KB/s（不可用），走本机代理 `127.0.0.1:7897`
  实测 ~5 MB/s，63 秒下完；代理未出现 TLS 问题。

## 9. 口径与未覆盖说明

- 本报告全部读数来自**本地** manifest + 已下载快照，**未联网核对 DILA 源站**。
- ATTRIBUTION 里「17GB 级解包」指的是官方 `Freemium_legi_global` 全量包解开后的规模
  （含大量非条文文件与全法典树），与本快照的条文本体 964 MB 不是同一口径；
  **本报告没有下载 1.26 GB 源包**，因此「快照 171,801 对 == 源包全部法条」这一条**未验证**。
- 源包里可能存在但未被本快照收录的法条，本次无从判定（需要源包才能查）。
