# 社区包 PR：上游对齐 ＋ CI 红线排查（2026-11-27）

> 结论：**可以开 PR**。本文件是仓内记录，完整报告与 PR 材料在 Bunny 事项目录
> `artifacts/FactScribe-社区包-上游对齐与CI排查-报告-20261127.md`。

## 1. 上游对齐

上游 `MiniMax-AI/MiniMax-Code-MiniApps` 的 `main` 从 #160 合并（`be73247c`）推进到
`6f01a0f`，中间只有 2 笔提交（`2577af205` #161、`6f01a0f46` #132），
都只动 `minimax-bot`／`minimax-pet`，**没碰我们的目录**。

两路独立查法互相印证：

- GitHub commits API 按 `path=plugins/unclemoc/factscribe` 过滤，最新一笔就是 `be73247c`；
- `git/trees/{sha}?recursive=1` 逐 blob 比对：117 个 blob，**0 增 0 删 0 改**，逐字节相同。

**不需要 rebase。** 以 `6f01a0f` 为新底子重算，文件级 diff 与以 `be73247c` 为底子完全一致：

    47 files changed, +5853 / -560

（口径：上游 `main` 临时分支摆入 PR 内容，`git diff --cached --numstat` 实读。
包内容 = 本仓 `miniapp/` 去掉 `build.sh`／`install.sh` —— 这两个仓内脚本不进社区包，
依据 `artifacts/FactScribe-社区包-改动清单-A1-A11-B1-B5-20261127.md:30`。
去掉后 125 文件／5,354,204 字节。）

上游-only 文件为空表：**本 PR 一个上游文件都不删**；117 个上游文件里 78 个逐字节相同、
39 个被修改、8 个新增。

## 2. 上游闸门实跑（PR 内容摆进上游 `main`）

| 检查 | 读数 |
| --- | --- |
| `node scripts/validate.mjs` | `plugins/unclemoc/factscribe: OK`（**0 error 0 warning**）、`repository: OK`、退出码 0 |
| `node --test "test/**/*.test.mjs"` | **96/96 通过** |
| 包自带 `node --test tests/*.test.mjs` | **32/32 通过**，0 skipped |

上游 CI 跑的就是 `npm run check`（= validate ＋ test，见上游
`.github/workflows/ci.yml`），所以这三条就是上游放行闸的等价实跑。

## 3. CI 红线：根因、是否已修、是否还红

**红的那一条**：run `45779342429`（2026-11-26T07:58:43Z，事件 pull_request，
分支 `feat/unify-engine-paragraph-into-main-20260126`，sha `b893c19da2`）。

8 个 job 红 4 个：python 3.10／3.11／3.13／3.14，都停在 `Unit tests (offline)`，
且**失败的是同一个测试**（四份 job 日志逐份实读）：

    FAIL: test_old_version_is_old (test_miniapp_python_discovery.ProbeClassificationTests)
      File "tests/test_miniapp_python_discovery.py", line 147, in test_old_version_is_old
        self.assertEqual(probe["status"], "old")
    AssertionError: 'broken' != 'old'
    Ran 2563 tests in 289.765s
    FAILED (failures=1)

**根因**：探针把判据挂在了 Node 的 `exit` 事件上。`exit` 只保证「进程退出了」，
不保证管道里的字节已经到父进程；CI runner 上五个矩阵并行、还在装 poppler，
`exit` 常常先于 stdout 的 `data` 到，`out` 还是空的，一个明明吐了版本号的解释器
被判成 `broken` 而不是 `old`。

红的那版源码（`miniapp/miniapp/node/python_discovery.mjs:249`）：

    child_.on('exit', (code) => { ... done({ status: 'broken', ... }); });

**已修**：`672a27a` `fix(miniapp-host): 探针改听 'close'——等 stdout 读完再判版本，别把好解释器误报 broken`
—— 同文件第 259 行改成 `child_.on('close', ...)`，并加回归锁
`tests/test_miniapp_python_discovery.py::test_late_stdout_is_still_read`（+11 行）。

**现在不红**：同一分支的下一条 run `45808221929`（11-26 11:10）= success；
`main` 的 `45846877694`（11-26 15:13）、`45854051675`（11-26 15:56，sha `a7f5e0125`）= success。
历史里其余 23 条红都在 11-14 ~ 11-19 的老分支／老 sha 上，都已被后来的绿 run 覆盖。

**我们这条分支从来没有 CI run**——`feature/community-revendor-20260127` 没 push 过
（`git ls-remote --heads origin 'feature/community-revendor*'` 为空），
所以用户看到的红不是这条分支的红。

**跟本次社区包 PR 无关，而且方向相反**：

1. 放行这道 PR 的是**上游仓**的 CI（`npm ci && npm run check`），我方仓 CI 不参与；
2. 上游闸门按 PR 内容实跑是绿的（§2）；
3. 红的那处（探针判早）正是本 PR 带给上游的修正之一：
   `miniapp/node/python_discovery.mjs`（+11/−1）把 `exit` 换成 `close`。

## 4. A6 实测复核（CRLF 稿子插 AI 草稿）

两套引擎并排跑真路径 `POST /api/disk/<p>/<d>/draft/insert`，今天复核读数：

| | 落盘前 | 落盘后 | 草稿块内 | `\r\r\n` |
| --- | --- | --- | --- | --- |
| **本分支** | 678 B／11 CRLF／0 落单 LF | 833 B／**18 CRLF／0 落单 LF** | 5 CRLF／0 LF | 0 |
| **#160 合并版** | 678 B／11 CRLF／0 落单 LF | 826 B／11 CRLF／**7 落单 LF** | 0 CRLF／5 LF | 0 |

计数与原表（811 B／818 B）**完全一致**；字节数差 15 是本次复核的草稿正文比原来那次长
（两边同步变长，差值恒定 7 字节 = 7 条 LF 换成 CRLF 多出的字节）。

更硬的证据：把本 PR 新增的回归锁 `tests/save-draft-eol.test.mjs` 原样拷到 #160 的包上跑 —— **红**；
跑本分支 —— **绿**：

    # 本分支
    ✔ CRLF 稿子插 AI 草稿：草稿块也是 CRLF，原正文逐字节不变
    ✔ LF 稿子插 AI 草稿：不会被改成 CRLF

    # #160 合并版，同一测试文件、同一批断言
    ✖ CRLF 稿子插 AI 草稿：草稿块也是 CRLF，原正文逐字节不变
      AssertionError: 全文不该出现落单的 LF
    ✔ LF 稿子插 AI 草稿：不会被改成 CRLF

## 5. 还没验的（如实记）

- 上游 CI 没在真 runner 上跑过这条分支（本地跑的是等价闸门）；
- Windows／Linux 真机端到端仍未验；
- 本报告的结论绑定上游 `6f01a0f`，真要开 PR 的那一刻建议再跑一次目录逐 blob 比对；
- 本次全程只读主检出，改动只落 `.worktrees/community-revendor-20260127`。
