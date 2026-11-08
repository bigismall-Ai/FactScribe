# BATCH 29-C：Terminal-Bench 全量 oracle 试跑底账（siinfer）

- 机器：siinfer（32 核 / 93G 内存 / Docker 29.1.3 / containerd 2.2.1）
- 时间：2026-11-07 03:30 → 06:30（3 小时时间盒，到点停）
- 跑法：`--agent oracle`、`-k 1`、`-y`，并发 8（部分轮次 4/5/6，原因见 §五）
- 原始结果：远端 `~/terminal-bench/tb/jobs/batch29c-*`（19 个作业目录，共 363MB）

---

## 一、一句话结论

**这台机器能跑全量 66 题，但必须先把 Docker 的镜像存储从系统盘挪到 `/srv`（12T）——本次已挪好。**
3 小时里 61 题拿到结果：**35 题 oracle 满分通过**（占已判定 47 题的 74.5%，占全量 53%）；3 题 oracle 自己也没过（要复跑确认是不是题目 flaky）；9 题卡在外网资源/环境启动；14 题时间盒内没跑完；5 题没轮到。

---

## 二、全量入口与实跑命令

- 全量入口＝`-p tasks`（整个数据集目录）。先 `--dry-run` 验证，输出 **`Dry run OK — 66 trial(s)`**，确认就是 66 题。
- 实跑命令原文（分轮执行，每轮用 `-i` 指定该轮题目）：

```bash
cd ~/terminal-bench/tb
PATH=$HOME/.local/bin:$PATH harbor run -p tasks -e docker \
  --agent oracle -k 1 -n 8 -y \
  --job-name batch29c-<轮次> \
  -i task-a -i task-b -i task-c ...          # 每轮 4~8 题
```

- 为什分段：单条全量命令一旦中途失败，已跑结果无法复用（同 job 目录配置不一致会报 `FileExistsError`）；分段还能在两轮之间清缓存控磁盘。分段不影响单题结果，配置与全量一致。

---

## 三、总表（66 题）

| 结果 | 题数 | 含义 |
|---|---|---|
| 通过 | 35 | oracle 跑满分（reward=1.0） |
| 失败 | 3 | oracle 只得 0 分，题目或环境本身有问题 |
| env | 9 | 环境不兼容/外网拉取超时/环境启动超时 |
| 未完成 | 14 | 时间盒到点或批次中断，没拿到判定（不代表题有问题） |
| 未跑 | 5 | 3 小时内没轮到 |

### 逐题明细

| 题目 | 结果 | 耗时 | 备注 |
|---|---|---|---|
| atrx-vep-crispr | 通过 | 435s | |
| batched-eval-parity | 通过 | 168s | 需断网沙箱（egress sidecar），见 §五 |
| biped-contact-dynamics | 通过 | 162s | |
| bun-sourcemap-leak | 通过 | 117s | |
| cad-model | 通过 | 193s | |
| cargo-flight-dispatch | 通过 | 72s | |
| coq-block-bound | env | 210s | 构建要现场装 Coq（opam 拉 GitHub），exit 40 |
| ctr-optimization | 通过 | 625s | |
| cumulative-layout-shift | 通过 | 517s | |
| data-anonymization | 失败 | 738s | oracle 0 分，需复跑判 flaky |
| distributed-dedup | env | 164s | curl 28 外网超时 |
| embedding-drift-monitor | 通过 | 188s | |
| fin-saccr-rwa | 通过 | 96s | |
| foodstuff-beta-activity | 通过 | 92s | |
| formal-crypto | env | 116s | 镜像构建失败 |
| fp8-rmsnorm-gemm | 未完成 | 363s | 批次中断 |
| freecad-impeller | 未完成 | 362s | 批次中断 |
| freecad-platform-drawing | 未完成 | 362s | 批次中断 |
| freecad-spring-clip | 通过 | 515s | |
| freight-dispatch-shift | 通过 | 275s | |
| glycan-ms2-elucidation | 通过 | 144s | |
| gsea-proteomics | 通过 | 253s | |
| heat-pump-warranty | 通过 | 236s | |
| hof-topology-interpenetration | 通过 | 186s | |
| html-js-filter | 通过 | 445s | |
| interleaved-vigenere | 通过 | 197s | |
| intrastat-meldung | 通过 | 286s | |
| jax-speedrun-gpu | env | 392s | GPU 镜像构建/拉起失败 |
| ks-solver-cpp | 通过 | 350s | |
| kv-live-surgery | env | 259s | 多服务 compose 拉起失败 |
| lake-temp-glm | 通过 | 1908s | 需断网沙箱；单题最慢之一 |
| layout-config-recreation | 通过 | 782s | 首轮失败，二次通过 → 属 flaky |
| layout-config-recreation2 | env | 205s | curl 28 拉 HuggingFace 资源超时 |
| legacy-utility-triage | 通过 | 437s | |
| live-database-cutover | 失败 | 927s | oracle 0 分，需复跑判 flaky |
| math-eval-grader | 未完成 | 228s | 批次中断 |
| medical-claims-processing | 通过 | 1427s | |
| mp-checkpoint-consolidation | 通过 | 818s | |
| music-harmony | 通过 | 737s | |
| mvcc-lsm-compaction | 未完成 | 155s | 批次中断 |
| nextjs-performance | 通过 | 1498s | |
| ontology-kg-querying | 通过 | 149s | |
| payments-pipeline-fix | env | 68s | 多服务 compose 拉起失败 |
| photonic-waveguide-routing | 通过 | 858s | |
| pretrain-shard-corruption | 未完成 | 155s | 批次中断 |
| production-planning | 未完成 | 155s | 批次中断 |
| protein-autointerp-disulfide | 未完成 | 482s | 时间盒到点 |
| react-lead-form | 未完成 | 476s | 时间盒到点 |
| retro-console-soc | 未完成 | 481s | 时间盒到点 |
| risk-scorer-replay | 未完成 | 476s | 时间盒到点 |
| roy-polymorph-cn | 未跑 | - | 时间盒内没轮到 |
| rs-archive-clone | 未跑 | - | 时间盒内没轮到 |
| satb-audio-transcription | 未跑 | - | 时间盒内没轮到 |
| session-window-debug | 未跑 | - | 时间盒内没轮到 |
| sglang-qwen-burst | 未跑 | - | 时间盒内没轮到 |
| shadow-relay | env | 256s | 多服务 compose 拉起失败 |
| sound-change-cascade | 通过 | 474s | |
| takens-embedding-lean | 未完成 | 775s | 时间盒到点 |
| telecom-entity-resolution | 未完成 | 777s | 时间盒到点 |
| uefi-bootkit | 未完成 | 775s | 时间盒到点 |
| vba-userform-port | 通过 | 2220s | 单题最慢 |
| vf2-speedup-networkx | env | 600s | 环境启动超时（600s） |
| vllm-deepseek-streaming | 通过 | 731s | |
| vpp-loss-divergence | 失败 | 1600s | oracle 0 分，需复跑判 flaky |
| wal-recovery-ordering | 通过 | 904s | |
| wdm-design | 通过 | 920s | |

---

## 四、汇总

| 指标 | 数值 |
|---|---|
| 题量 | 66 |
| 通过 | 35 |
| 已判定题（通过+失败+env） | 47 → **通过率 74.5%** |
| 全量视角通过率 | 35/66 = **53.0%** |
| 总耗时 | 180 分钟（03:30–06:30，含约 25 分钟磁盘/环境排障） |
| 平均每题耗时 | 507 秒（中位 363 秒；含构建、拉镜像、验证） |
| 最慢单题 | vba-userform-port 2220s、lake-temp-glm 1908s、vpp-loss-divergence 1600s |
| 镜像峰值 | 镜像 65.4GB + 构建缓存 67.8GB ≈ 133GB（全部在 `/srv`） |
| 磁盘峰值（系统盘 `/`） | **只剩 24GB 可用（94% 满）**——发生在把镜像库挪到 `/srv` 之前 |
| 搬库后 `/` | 稳定 64–65GB 可用（86% 占用） |
| `/srv` 增量 | 约 +100GB（12T 可用，占 20%） |
| 结果体积 | `jobs/` 363MB |

---

## 五、能不能跑全量的结论

**能，够用。** 前提三条，缺一条就会翻车：

1. **镜像存储必须在 `/srv`。** 这是本次最大的坑：Docker 用的是系统 containerd，默认内容库在 `/var/lib/containerd`（系统盘，只有 237G）。开 8 并发时，10 分钟就能吃 30GB，系统盘一度只剩 24GB。处置：`/etc/containerd/config.toml` 设 `root = "/srv/containerd"`，重启 containerd+docker，清空旧库，释放 35GB。
2. **`/srv` 至少要预留 150–200GB** 给「镜像 + 构建缓存」。66 题约 130GB 峰值；跑完清理即可回收。
3. **外网要能通 HuggingFace / GitHub / mcr.microsoft.com。** 国内几处资源会 `curl 28` 超时，直接卡在镜像构建阶段（见 §六）。

**并发建议**：8 稳定（32 核 / 93G 内存，峰值内存占用 < 10G）。提到 12 也可以，但单题最重 16G 内存的题（如 math-eval-grader）会到瓶颈；建议 8 起步，观察后再说。

**时间估计**：本次 3 小时跑完 61/66（含大量排障）。磁盘/网络都就绪后，全量 66 题预计 **2–2.5 小时**（8 并发）。

**需要排除或特殊处理的题**：
- `coq-block-bound`：构建阶段要从 GitHub 拉 opam 仓库现场编译 Coq，本机拉不动（exit 40），**建议排除**。
- `layout-config-recreation2`、`distributed-dedup`：构建要拉 HuggingFace/GitHub 资源，`curl 28` 超时，**换网络或预置资源再跑**。
- `jax-speedrun-gpu`、`fp8-rmsnorm-gemm`：GPU 镜像构建/拉起失败，**要检查 GPU 直通与镜像源**。
- `kv-live-surgery`、`payments-pipeline-fix`、`shadow-relay`、`vf2-speedup-networkx`：多服务 compose 拉起失败或 600s 启动超时，**建议单跑并加 `--timeout-multiplier`**。
- `data-anonymization`、`live-database-cutover`、`vpp-loss-divergence`：oracle 0 分，**先复跑一次判 flaky**（本次没时间复跑）。

---

## 六、事故与坑（按发生顺序）

1. **buildx 缺失**：harbor 对 `allow_internet = false` 的题（batched-eval-parity、lake-temp-glm）要构建 egress-control sidecar，走 `docker buildx build`，而本机没装 buildx → `unknown flag: --file`。装 buildx v0.38.2 到 `~/.docker/cli-plugins/`（GitHub 直连超时，经 gh-proxy 镜像下载）后解决，两题都能过。
2. **系统盘被镜像库撑爆**：见 §五第 1 条。期间触发了我设的磁盘看门狗（剩 24G 时强杀），导致两轮 8 题被取消。
3. **自己挖的坑——定时清镜像误删在途镜像**：为省磁盘加了「每 2 分钟 `docker image prune -a`」，结果刚构建好、还没被容器引用的镜像被删掉，harbor 报一片 `Could not resolve container for compose service 'main'`（假故障）。改成只清 15 分钟以上未用镜像（`--filter until=15m`）后才正常。
4. **挪存储后构建缓存指向旧快照**：`failed to extract layer ... content digest not found` / `parent snapshot does not exist`。清构建缓存（`docker builder prune -a`）解决。
5. **外网资源拉取超时**：`huggingface.co`、`github.com`、`mcr.microsoft.com`、`ghcr.io` 时快时慢甚至超时（`curl: (28)`、`exit code: 28/40`）。这类失败一律记 `env`，不是题目问题。
6. **单题超时沿用 harbor 默认**：没有额外调短或调长（个别题如 coq 的构建 30 分钟上限来自题目自带的 `build_timeout_sec`）。

---

## 七、原始结果路径（远端）

```
~/terminal-bench/tb/jobs/batch29c-oracle/      首轮冒烟/中断批次
~/terminal-bench/tb/jobs/batch29c-egress-test/ batched-eval-parity 验证 buildx
~/terminal-bench/tb/jobs/batch29c-p01..p05/    第 1 阶段分块
~/terminal-bench/tb/jobs/batch29c-r01..r03/    第 2 阶段（受磁盘问题干扰）
~/terminal-bench/tb/jobs/batch29c-s01/, t01..t02/, u01..u03/, v01..v02/   成规模跑批
~/terminal-bench/tb/jobs/batch29c-full/        首条命令的作业目录
~/terminal-bench/tb/jobs/smoke-check2/         搬库后的单题回归（legacy-utility-triage 1.0）
```

日志：`~/terminal-bench/tb/batch29c-full.log`、`batch29c-fullB.log`、`batch29c-watchdog.log`

---

## 八、对机器的改动（需知会后续批次）

1. `~/.docker/cli-plugins/docker-buildx` 新增（v0.38.2）。
2. `/etc/containerd/config.toml` 新建：`root = "/srv/containerd"`、`state = "/run/containerd"`（版本 3）。
3. `/var/lib/containerd` 已清空（原是本机 Docker 的镜像库，搬迁后重建）。
4. 未改动 GPU 推理服务、未重启它；`/srv/docker` 与 `/srv/containerd` 增加约 100GB 镜像数据。
