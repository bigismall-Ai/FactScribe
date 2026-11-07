# paperkit v2 实现记录（批 36：三处落地摩擦）

日期：2026-11-07　　实现者：批 36 实施工（D 席 / opencode）
基线：`9d255bd`（v1.0.0，87 例）　　本批：v1.1.0，93 例

本批不改闸门口径（红/黄/绑定的判定逻辑原样保留），只修「工具让写作变难」的三处
落地摩擦。三处都落在 `paperkit.py` 与 `tests/test_paperkit.py`。

---

## 1. D1 批注宏不该当正文审

**症状**：`sections/*.tex` 里的 `\todoq{...}`／`\todo{...}` 是作者写给作者的问题，
不是论文命题；audit 按旧逻辑只抹命令名、留下参数内容，于是批注里的数字（`15`、
`4.3`、`p~0.03`）被当正文判红（4 红全部来自批注）。

**改法**

- 新增 `_ANNOTATION_CMDS = (todoq, todo, pkignore, pknote, fixme, note, tbd)`；
  `_mask_envs_and_verb` 在剥注释之前把它们**连同可选参数与必选参数**整块抹成空白
  （保留行列号）。`\todo[inline,color=...]{...}` 的可选参数一并吞掉。
- 跳过必须可见：`ScanResult.annotations` 记录 `(宏名, 行号)`；
  `run_audit` 汇总为 `summary.annotations_skipped` 与 `summary.annotation_sites`；
  人读输出新增一行
  `notes : 已跳过 N 处批注（\todoq/\todo/\pkignore 等，内容不参与审计）`。
- 注释行里的批注不计入（先判该行 `%` 之前没有宏调用），避免把注释掉的 todo 算成跳过。
- 行内 `\pkignore{...}` 的旧行为不变（照排、不进审计），只是现在也计入「已跳过」。

**边界**：跳过 ≠ 放行。批注外的同一数字照旧判红（负例测试钉死）。

## 2. D2 数字贴单位要能抽

**症状**：`131s`、`2220s`、`53000token` 这类「数字紧贴量纲」漏抽。旧 `_NUM_RE` 的
`(?![\w])` 要求数字后不能跟字母，于是 `131s` 整体不匹配；账上 C3（131 秒）、
G4（507 秒，最慢 2220）因 source 里写作 `131s` / `2220s` 而报黄 `VALUE_NOT_IN_SOURCE`，
写作规矩只好要求作者写成 `131\ \text{s}`。

**改法**

- `_NUM_RE` 的数字后新增单位分支 `_UNIT_RE`：
  `s/ms/min/mins/sec/secs/h/hr/hrs/tok/toks/token/tokens/GB/GiB/MB/MiB/KB/KiB/TB/TiB/x/×`。
- 长单位排前（`tokens` 先于 `tok`、`ms` 先于 `s`），量级 `[kKMB]` 排在单位之后：
  `5MB` 按单位、`5M` 仍是量级 5,000,000。
- `number_key()` 只对 `_MAGNITUDE`（k/m/b）换算；单位只表量纲、不改数值。
- 数字前仍是 `(?<![\w.])`：`R2`、`H2O`、`v2`、`ctex2017` 不算数字；`1st`/`3rd` 也不会
  被 `s` 单位误吃（单位后仍有 `(?![\w])`）。

**副作用（正收益）**：`check` 的 C3/G4 两条 `VALUE_NOT_IN_SOURCE` 黄自然消失，
`source` 文本里的 `131s`/`2220s` 现在能回查到 131/2220。

## 3. D3 来源不该被迫搬家

**症状**：v1 强制 `source` 落在项目 `paper/results/` 下；批 35 为过闸把 45 份原始产物
复制进 `results/`，出现两份副本、靠 `origin` 字段人工追溯。

**改法**

- `paperkit.toml` 的 `[project]` 新增可选 `source_root`（默认空＝v1 旧口径）：
  `source` 相对 `source_root` 解析，sha256 与人签清单照旧逐条校验。
- 新函数 `source_base(cfg)` / `source_path(cfg, f)`；`verify_sources` 与 `check` 的
  `sources_ok` 统计都走它。
- 越过 `source_root`（含符号链接逃逸，`resolve()` 判定）→ 红
  `SOURCE_OUTSIDE_SOURCE_ROOT`；未配 `source_root` 时仍是红 `SOURCE_OUTSIDE_RESULTS`，
  旧项目与旧测试不受影响。
- `results/` 未签文件扫描保持原样（项目内产物区照旧点名）；清单 `[files]` 的键
  ＝facts 里的 `source` 串（本论文＝`experiments/ctx-compiler-redblue/...`）。

**论文项目落地**：`paper/paperkit.toml` 加
`source_root = "/Users/moc/workspaces/SiAgent"`；8 个 facts 文件的 48 条 `source`
改回 `experiments/ctx-compiler-redblue/...`，删掉全部 `origin` 字段；
`paper/results/` 下 9 份 BATCH 副本删除；`results/MANIFEST.toml` 按新键重算 sha256
（值与 facts 里已钉的一致）。复制不再必要。

## 4. CJK 缺字警告根因（204 → 0）

- 现象：`tectonic main.tex` 每轮报 `Missing character ... in font ec-lmbx10`。
- 根因：**来自 `paper/main.tex` 的 `\todoq` 宏定义**，不是各 section。
  `\newcommand{\todoq}[1]{\todo[inline,color=yellow!30]{\textbf{待回答：}#1}}`
  把 4 个中文字符 `待回答：` 写进每个批注框；文档只加载 `fontenc[T1]+lmodern`，
  没有 CJK 字体。当时 17 个 `\todoq` × 4 字 × 3 遍 TeX 排版 = **204 条**，
  与报数完全对上（section 里的批注正文本身是英文）。
- 修法：宏标签改成 ASCII `PENDING:`（`paper/main.tex`）。重编后
  `Missing character` 0 条、`could not represent` 0 条；PDF 正常出。
- 若将来正文真的要排中文，需要 `ctex`/`xeCJK` + 中文字体，这不在本批范围。

## 5. 验证读数（2026-11-07）

| 命令 | 结果 |
|---|---|
| `python3 paperkit.py check ../paper` | 0 红 / 1 黄（D1,H1 的 `LEDGER_CONFLICT`，刻意保留的双口径）→ 退出码 3 |
| `python3 paperkit.py audit ../paper` | 0 红 / 8 黄（全部 `UNSCANNED_TEX`：appendix、tables、main.tex 不在 `sections/*.tex` 闭包）→ 退出码 3；`numbers 0 个`、`已跳过 17 处批注` |
| `python3 paperkit.py build ../paper` | 成功，退出码 0，出 `paper/main.pdf`（26.9 KiB） |
| `python3 -m unittest discover -s tests` | **93 例全绿**（原 87 + 新增 6） |

audit 的 8 条黄可解释：正文目前只有批注骨架，appendix/tables 不在审计闭包里（工具
按设计点名，不静默放行）。正文开写后这批黄会随 `\fact{}` 绑定与表格复述消失。

## 6. 新增测试（三条各 1 正 1 负）

| 用例 | 断言 |
|---|---|
| `test_d1_annotation_numbers_are_skipped` | `\todoq{47.3 15 4.3}` + `\todo[..]{0.03}` → 0 红、`annotations_skipped==2`、`numbers_total==0` |
| `test_d1_real_number_next_to_annotation_still_red` | 批注外的 `47.3` → 红 `UNMATCHED_NUMBER`，跳过计数仍为 1 |
| `test_d2_number_with_unit_suffix_is_extracted` | `131s` 绑定 `value="131 秒"` → 0 红、bound 1（同时验证 source 里 `131s` 回查通过） |
| `test_d2_letter_leading_digits_are_not_numbers` | `R2 H2O v2` 抽不出数，只有 `47s` 红 |
| `test_d3_source_under_source_root_is_ok` | `source_root` 外置 `data/raw.md` → audit 0 红 |
| `test_d3_source_escaping_source_root_is_red` | 符号链接逃出 `source_root` → 红 `SOURCE_OUTSIDE_SOURCE_ROOT` |

## 7. 兼容性

- 未配 `source_root` 的项目行为与 v1 完全一致（`SOURCE_OUTSIDE_RESULTS` 保留）。
- JSON 只**增**字段（`annotations_skipped`、`annotation_sites`），不改既有字段。
- 版本号 `1.1.0`，`schema_version` 仍 `1.0`（增量字段，向后兼容）。
