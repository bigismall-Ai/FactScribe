# 证据清单：建议块的输出流契约（批 134）

规范：`docs/design/SPEC-EVIDENCE-STAMP.md` §8.1。实现：`factscribe/evidence.py`
（`render_toml` / `suggest_summary`）、`factscribe/cli.py`（`--suggest`）。
测试：`tests/test_evidence_freeze.py` 的 `TestSuggestStreams`（5 例）。

## 修的是什么

`evidence --suggest <项目>` 的产物设计目标是**可直接粘进 `paperkit.toml`**。
一旦 stdout 里混进人类摘要（「扫描 N 节……」），重定向得到的文件就不是
合法 TOML：`cat >> paperkit.toml` 之后所有读配置的命令都 exit 2。

契约（现在由测试锁住）：

| 通道 | 内容 |
|---|---|
| stdout（默认） | **只有** `[evidence]` TOML 块，可 `> /tmp/x.toml` 或直接追加 |
| stderr（默认） | 一行人类摘要：扫描节数、有引用的节数、id 条数（未冻结） |
| stdout（`--json`） | **只有** JSON；摘要进 `summary` 字段，统计进 `scanned` / `sections_with_facts` / `facts` |
| stderr（`--json`） | 空 |

实现上摘要只经 `suggest_summary()` 生成一次，默认形写 stderr、JSON 形写进
`summary` 字段——stdout 的 TOML 与 JSON 两条路都不混人类文本。

## 验收实录

命令均在 `paperkit-dev/` 下以当前工作区代码运行（`../paper-b` 为真实项目）。

| # | 命令 | 读数 |
|---|---|---|
| 1 | `python3 -m factscribe evidence --suggest ../paper-b > /tmp/x.toml 2>/tmp/x.err` | exit 0；`/tmp/x.err` 一行「扫描 10 节，7 节有 fact 引用，共 103 条 id（未冻结）」 |
| 2 | `python3 -c "import tomllib;print(len(tomllib.load(open('/tmp/x.toml','rb'))['evidence']))"` | `7` |
| 3 | `cp -R ../paper-b /tmp/ev3 && cat /tmp/x.toml >> /tmp/ev3/paperkit.toml && python3 -m factscribe evidence --freeze /tmp/ev3` | exit 0，`entries` 103，`canonical_sha256` `036da978…` |

失败形态（批 134 报告里的现象）：摘要若在 stdout 第一行，第 2 步的
`tomllib` 直接抛 `TOMLDecodeError`，第 3 步 exit 2。回归测试
`test_appended_stdout_is_accepted_by_freeze` 按这条验收路径造项目并断言
`--freeze` exit 0。

## 批 134 核对结论

批 132 落地时默认形的摘要已经写在 stderr（`cli.py` 的 `print(..., file=sys.stderr)`），
在本批开始时的 HEAD（`c3adcb4`，批 133）上按上述三条验收原样复跑，读数为
7 / 7 / exit 0，**报告中的缺陷未能复现**——最可能的原因是复现时把
stderr 并进了同一终端或同一文件（`2>&1` / `&>`），屏幕上看像 stdout 的第一行。

因此本批不做「把 stderr 改回 stderr」的空改动，改为把隐式行为升成显式
契约：摘要统一由 `suggest_summary()` 生成，默认形只写 stderr、JSON 形只写
`summary` 字段；`--json` 补 `scanned` / `sections_with_facts` 统计字段；五条
回归测试钉住上表四个通道，以后谁再往 stdout 加人类文字，测试立刻红。

## 为什么不是「只在文档里写一句」

输出流是机器接口：重定向、管道、CI 都按字节消费。摘要与 TOML 共用一个
通道，等于把「给人看的字」混进「给机器吃的文件」——这类缺陷在终端里
看不出来（stderr 与 stdout 都印在屏幕上），只有重定向后才炸。批 134 的
五条测试分别盯住：stdout 可 `tomllib.loads`、stdout 无中文、摘要必在
stderr、`--json` 纯 JSON 且带统计、追加后 `--freeze` 仍 exit 0。
