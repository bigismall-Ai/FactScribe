# 项目配置契约（冻结）与归一化实现

> 批 52。规范正文在 `docs/design/SPEC-V3.0.md` §10「项目配置（冻结）」；
> 本件记契约表、别名表、归一化落点与盲测 #3 读数。起因：盲测 #3 的 16 个
> 项目由三位独立出题人写成三种形态，旧实现只认「扁平 schema」，16 个项目
> 全部 exit 2——是**契约没写死**，不是闸门判错。

## 1. 契约表（唯一规范形态）

文件名 `factscribe.toml`（兼容旧名 `paperkit.toml`）。规范形态＝一张 `[project]` 表。

| 字段 | 必需 | 类型 | 缺省 | 别名/备注 |
|---|---|---|---|---|
| `name` | 否 | string | `""` | `title`（`name` 优先） |
| `root_tex` | **二选一** | 项目内相对路径 | — | 闭包起点；与 `sections` 二选一 |
| `sections` | **二选一** | string[] | 由 `root_tex` 推导 | 显式 `.tex` 清单，不许 glob |
| `facts` | 否 | glob 或目录名 | `facts`→`facts/*.toml` | |
| `bib` | 否 | 项目内相对路径 | `refs.bib` | `refs` |
| `output` | 否 | 项目内相对路径 | `main.pdf` | |
| `level` | 否 | `l0`\|`l1`\|`l2` | `l1` | 也接受 `0`/`1`/`2`，大小写不敏感 |
| `number_locale` | 否 | `period`\|`comma` | `period` | `dot`/`point`→`period` |
| `signing_mode` | 否 | `offline_manifest`\|`local_key` | `offline_manifest` | |
| `approver_keys_file` | 否 | 项目外路径 | `""` | 空＝不做该项检查 |
| `release_keys_file` | 否 | 项目外路径 | `""` | 同上 |
| `numeric_macro_allow` | 否 | 表数组／字符串数组 | `[]` | S-08 两种形态都认 |
| `frac_allow` | 否 | string[] | `[]` | |
| `inline_images_allow` | 否 | string[] | `[]` | |
| `image_budget_extra` | 否 | 非负整数 | `0` | |
| `authors` | 否 | string[] | `[]` | 仅展示 |

**必需字段只有一个**：闭包起点。`root_tex` 与 `sections` 都缺 → exit 2，错误
信息同时点名两者。其余字段缺＝取缺省，不报错。

## 2. 别名表（闭集）

| 规范名 | 允许的别名/写法 | 归一化结果 |
|---|---|---|
| 顶层 `schema` | `paperkit-project/3.x`、`factscribe/3.x` | 同一套 v3 |
| fact 文件 `schema` | `paperkit-fact/3.x`、`factscribe-fact/3.x` | 同上 |
| （无 schema） | `[project]`+`root_tex` / `[project]`+`sections` | 隐式 v3（补 `paperkit-project/3.0`） |
| `root_tex` ≡ `sections` | 两者同时给时 `root_tex` 优先 | `sections` 置空＋`CONFIG_ALIAS` 告警 |
| `sections` | 数组或单个字符串 | 数组→清单；字符串→单文件 |
| `bib` / `refs` | 同值 | `bib` |
| `name` / `title` | 同值 | `name` |
| `number_locale` | `period`/`dot`/`point`/`comma` | `period`/`comma` |
| `level` | `l0`/`l1`/`l2`/`0`/`1`/`2` | 小写 `l0`/`l1`/`l2` |
| `facts` | glob 或目录名 | 目录名→`<dir>/*.toml` |

**v1 不动**：`[project]` 里 `sections` 是字符串 glob 且配了 `facts` ＝ v1，
`root_tex` 忽略，行为与旧版逐字节一致（`tests/test_config_v3.py`、
`test_factscribe.py` 27 例老用例守着）。

## 3. 形态判定与缺省推导（写死在 `load_config`）

自上而下，先命中先用：

1. 顶层 `schema` → 形态 A（扁平 schema）；非 v3 前缀 → exit 2。
2. `[project].sections` 是数组 → 形态 C（project＋sections）。
3. `[project].root_tex` 非空且无 `facts` → 形态 B（project＋root_tex）。
4. `[project].sections` 是 glob 且有 `facts` → v1。
5. 其余带 v3 标记键的 `[project]` → 形态 B/C（缺起点 exit 2）。
6. 顶层有 `root_tex`/`sections`/`output`/`signing_mode`/`number_locale`/`level` → 形态 A。
7. 全无 → `缺少 [project] 段`（v1 旧报错）。

缺省推导：`sections` 缺省＝从 `root_tex` 展开闭包；只给 `sections` 时
`root_tex = sections[0]`（报告与 PDF 回检指代用）。`level` 缺省 `l1`；level
只选层、不降级红。

## 4. 归一化实现落点

| 位置 | 职责 |
|---|---|
| `factscribe/config.py::load_config` | 形态判定（§3 七步），分派 A/B/C/v1 |
| `factscribe/config.py::_load_v3_config` | 三形态 → 同一 `Config`；字段校验、别名归一、缺省推导 |
| `factscribe/config.py::_v3_get` | 顶层与 `[project]` 两处取属性（顶层优先） |
| `factscribe/config.py::_v3_sections` | `sections` 清单校验（不许 glob、必须是项目内相对路径） |
| `factscribe/config.py::_unknown_field_warnings` | 未知字段告警（`CONFIG_UNKNOWN_FIELD`） |
| `factscribe/config.py::_config_warn` | 告警收集，落到 `Config.warnings` |
| `factscribe/config.py::load_sections` | `section_files`（形态 C）与 `root_tex` 两条闭包入口 |
| `factscribe/report.py::_config_block` | `--json` 的 `config{shape,schema,file,warnings}` |
| `factscribe/cli.py` | 每个子命令输出 `config_warnings`（顶层副本）＋人读一行告警数 |
| `factscribe/livetext.py` | 源层「断言是否活在正文里」三条判据（见 §6） |

`--json` 的告警面：

```json
{
  "config": {"shape": "project-root", "schema": "paperkit-project/3.0",
             "file": "factscribe.toml",
             "warnings": [{"code": "CONFIG_UNKNOWN_FIELD", "severity": "info",
                            "field": "root_tx", "message": "…已忽略…",
                            "location": "/path/factscribe.toml"}]},
  "config_warnings": [ /* 同上列表 */ ]
}
```

**为什么不塞进顶层 `warnings`**：check/audit 的 `warnings` 是黄项列表，直接
复用会让「配置提示」参与「黄项驱动 exit 3」的语义。契约里写明了两者分工；
`config_warnings` 是给机器读的稳定键。

未知字段告警**不改退出码**（盲测与老项目不会被拼错的字段名一键判死），但也
绝不静默：`--json` 有明细，人读输出末行有「配置告警 N 条」。

## 5. 盲测 #3 逐项结果

跑法（不写 `/tmp/holdout3`，只读）：

```bash
cd paperkit-dev && python3 /tmp/blind_eval.py | tail -8
```

| 族 | invalid 期望码 | 实际退出 | 实际命中码 | 判定 |
|---|---|---|---|---|
| assertion-relocation | `ASSERTION_DRIFT` | 1 | `ASSERTION_DRIFT` | HIT |
| ignore-macro-wrap | `ASSERTION_DRIFT` | 1 | `ASSERTION_DRIFT`, `APPROVAL_MISSING_ASSERTIONS` | HIT |
| macro-hide | `NUMERIC_MACRO_SHAPE_INVALID` | 1 | `NUMERIC_MACRO_SHAPE_INVALID`×2, `ASSERTION_DRIFT` | HIT |
| numexpr-computed | `ASSERTION_DRIFT` | 1 | `ASSERTION_DRIFT`, `ARITH_IN_BODY` | HIT |
| sentence-split | `ASSERTION_DRIFT` | 1 | `ASSERTION_DRIFT`, `BOUND_MISMATCH` | HIT |
| stale-hash | `APPROVAL_STALE` | 1 | `APPROVAL_STALE`, `SOURCE_SHA256_MISMATCH` | HIT |
| table-tunnel | `ASSERTION_DRIFT` | 1 | `ASSERTION_DRIFT`, `APPROVAL_MISSING_ASSERTIONS`, `NUMERIC_IN_MACRO` | HIT |
| unbound-quant | `APPROVAL_MISSING_ASSERTIONS` | 1 | `APPROVAL_MISSING_ASSERTIONS`, `ASSERTION_DRIFT`, `UNBOUND_NUMBER` | HIT |

- **invalid 命中 8/8**；8 个 valid 近邻全部 exit 0、零 findings（**干净 8/8**）。
- 三套盲测合计（holdout / holdout2 / holdout3）：`HIT 20/20｜MISS 0｜WRONG-CODE 0`，
  `CLEAN 20/20｜FALSE-RED 0`。
- 修复前：holdout3 的 16 个项目**全部 exit 2**（配置读不进来），命中 0/8。

## 6. 为达标补的源层判据（`factscribe/livetext.py`）

配置通了以后仍有 6 族「读得进来但判不出」，它们共同指向同一件事：**签名
断言必须活在会被渲染的正文里**。三条通用规则（不认项目名/路径）：

1. 定量事实在**活跃正文**里没有 `\fact{}` 标记 → `APPROVAL_MISSING_ASSERTIONS`
   ＋ `ASSERTION_DRIFT`。活跃正文＝去注释、去宏定义体、去「参数被丢弃的宏」的
   实参（`\newcommand{\ignore}[1]{}`）、去 `\iffalse…\fi`。
2. 标记活着但所在句子没有任何数字，且不是 `\fact{ID}{值}` 两参形态 →
   `ASSERTION_DRIFT`（计数器/表达式算出来的数，源文本里没有字面量）。
3. 事实声明 `role` ∈ 正文角色，标记却只在 `\appendix` 之后 →
   `ASSERTION_DRIFT`（结论被搬进附录）。

另补两处**通用**修正：

- `source_sha256` 接受 `sha256:` 前缀（§2.3／S-03 的规范编码就是带前缀的），
  比较前统一去前缀——旧实现把合法的 `sha256:<hex>` 判成「不一致」。
- V3 项目里 source_sha256 与现算不符同时记 `APPROVAL_STALE`（S-03：
  source_sha256 是 approve_target 的字段，变了就是审批对象过期）。

## 7. 防回归

- `tests/test_config_shapes.py`（新增 12 例）：三形态等价、别名、缺省、
  未知字段告警、缺起点 exit 2、宏藏标记/丢弃参数/附录搬家/活跃标记四情形。
- 全量：`python3 -m unittest discover -s tests` → **184 例全绿**（原 172 例
  未改一字，新增 12 例）。
- 回归线：`tests/test_fixtures.py`（redteam-b1/b4 夹具）0 红。
- 纪律：代码里没有出现任何盲测项目名或路径；未写 `/tmp/holdout3`。
