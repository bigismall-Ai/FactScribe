# SPEC-REVIEW｜改写验收一条命令（批 114）

> 状态：**冻结**（批 114 实施依据）。
> 范围：新增 `factscribe review` 子命令与新模块 `factscribe/review.py`。
> 不改 `protect` / `style` / `tide` 的既有判据与退出码；零第三方依赖（纯标准库）。
> 一句话：**review 是 `protect + style --diff + tide` 的组合，不新增判据。**

---

## 1. 问题与立场

改写流程现在是三条命令分开跑：`protect` 看「不许变的内容变了没有」，
`style --diff` 看「改写有没有引入新的公式化写法」，`tide` 看「这次改动闭不闭合」。
分开跑有两类漏洞：

1. 跑了一条、忘了另一条，就以为改写通过了；
2. 三条各自有退出码，人只读最后一条，等于把前面的红吞掉。

`review` 把三条**同一次跑完**，并给出一个 fail-closed 的最终判定：

- 任一项失败都**不许假装通过**；
- 输出必须**逐项列明细**（哪几处红、哪个码哪一行、闭合三项各自真假），
  不许只给一个总结论。

---

## 2. 命令

```text
python3 -m factscribe review --before <旧目录> --after <新目录> \
    [--snapshot <库目录>] [--allow-new N] [--json]
```

| 参数 | 必填 | 语义 |
|---|---|---|
| `--before` | 是 | 改写前目录（必须存在且是目录） |
| `--after` | 是 | 改写后目录（必须存在且是目录） |
| `--snapshot` | 否 | 判定为「通过」时保存快照的库根；其余判定不存 |
| `--allow-new` | 否 | 允许的新增 style 违规条数（默认 0，不能为负） |
| `--json` | 否 | stdout 只出 JSON |

命令别名说明（同时写进 `--help`）：
`review` 是 `protect + style --diff + tide` 的组合，**不新增判据**。

---

## 3. 三项判据与底层命令的对应

| review 判据 | 复用的底层实现 | 取什么 |
|---|---|---|
| **保护面** | `protect.compare(before, after)` | 全部 findings；`severity=red` 者参与拒绝 |
| **复检（新增违规）** | `style.analyze(...)` ＋ `style.filter_new_findings` | 改前没有、改后有 的 findings |
| **闭合** | `tide.run_tide(before, after)` | `paired` / `hash_ok` / `pass_all` 三条件 |

三条底层命令的判据与退出码一律不变。`review` 只做编排与汇总。

补充口径：

- 保护面的**黄**（文件集合变化、章节标题重命名）不单独拒绝；只有**红**拒绝。
  文件删除会由 `tide` 的 `hash_ok` 判为不闭合，从而拒绝。
- `style` 的改前基线用同一套规则（`load_style_rules(<after 根>)`）计算，
  与 `style --diff` 完全同路径；`before=` 参数照旧启用标题关系词/主语丢失比对。
- `tide` 的账本写到临时目录：`review` 对文档树**只读**，不往 `--after/audit/`
  写账本或派生视图。`review` 判定的是「这一对目录」的闭合，不并入历史账链。
- 目录缺 `paperkit.toml`、`--allow-new` 为负等用法问题按既有分层返回 2
  （工具没跑起来），不伪装成「拒绝」。

---

## 4. 判定表与退出码

| 情形 | 判定 | 退出码 |
|---|---|---|
| 保护面有红 | **拒绝**（`reject`） | 1 |
| tide 不闭合（`paired ∧ hash_ok ∧ pass_all` 不全真） | **拒绝**（`reject`） | 1 |
| 新增违规 > `--allow-new`（默认 0） | **需复核**（`needs_review`） | 3 |
| 三项全过 | **通过**（`pass`） | 0 |

优先级：**拒绝 > 需复核 > 通过**。保护面红与 tide 不闭合任一成立即拒绝，
不再降级成「需复核」。用法/配置错仍走 2，工具内部错误走 4（沿用既有分层）。

---

## 5. 输出契约

### 5.1 人读输出

必须逐项列，不许只给总结论：

1. 最终判定与退出码；
2. **保护面**：红几条，逐条 `文件:行 码 说明`；
3. **复检**：改前基线几条 → 新增几条（允许几条），逐条 `码 文件:行 原文`；
4. **闭合**：`paired` / `hash_ok` / `pass_all` 各自 ✓/✗，涨/落/波及面计数，
   未闭合原因；
5. **快照**：保存了哪个 ID / 因判定不通过未保存。

### 5.2 JSON

stdout 只出 JSON。除公共字段（`schema_version` / `tool` / `version` /
`command` / `status` / `severity` / `exit`）外，含：

```json
{
  "verdict": "pass | reject | needs_review",
  "verdict_label": "通过 / 拒绝 / 需复核",
  "reasons": ["..."],
  "protect": {"red": 0, "yellow": 0, "info": 0, "total": 0,
              "findings": [{"severity": "...", "code": "...", "file": "...",
                            "line": 0, "message": "...", "before": "...",
                            "after": "..."}]},
  "style": {"new_findings": 0, "allow_new": 0, "baseline_findings": 0,
            "rejected": false, "findings": [{"code": "...", "file": "...",
                                              "line": 0, "text": "..."}]},
  "tide": {"closed": true, "status": "commit",
           "paired": true, "hash_ok": true, "pass_all": true,
           "criteria": {"paired": true, "hash_ok": true, "pass_all": true},
           "rises": 0, "falls": 0, "affect": 0, "reasons": []},
  "snapshot": {"requested": false, "saved": false, "id": null,
               "short": null, "files": null, "bytes": null, "store": null}
}
```

### 5.3 快照

`--snapshot <库目录>` 只在最终判定为 `pass` 时调用
`tide.save_snapshot(after, store)`；`reject` / `needs_review` 一律不落快照。
JSON 里 `snapshot.requested` 与 `snapshot.saved` 分开记，便于区分「没要」与
「要了但因判定不通过没存」。

---

## 6. 测试

`tests/test_review.py` 覆盖：无改动通过、数字改动拒绝并点名
`PROTECT_NUMBER_CHANGED`、新增标题格式问题需复核并给码与行号、
`--allow-new 1` 放行同一情形、删文件因 tide 不闭合拒绝、JSON 三项明细与
最终判定、三种判定各一条真实目录对、快照只在通过时保存、人读输出逐项列、
`review` 不写文档树账本、`--help` 写明别名、用法错返回 2。
