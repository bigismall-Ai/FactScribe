# 五分钟上手

目标只有一件事：让一篇最小的论文跑到 `0 红 / 0 黄`，看清「账、据、文」是怎么咬合的。
不解释原理，原理在 [README](../README.md) 与 [SPEC-V1](design/SPEC-V1.md)。

> 手上是**已经写完的论文**？这条路径不适用，先看 [ADOPT.md](ADOPT.md)：
> 把写完的论文接进来是迁移，不是安装；两篇真论文的实测读数也在那里。

## 0. 先自检（30 秒）

在仓库根：

```bash
python3 -m pip install -e .     # 可选；不装也能用 PYTHONPATH 跑
python3 -m factscribe doctor .
```

`✓` 正常，`!` 可以稍后补，`✗` 先修——每条都给了修复命令。
没有项目也能跑；`doctor` 不是闸门，不会拦你。

## 1. 建一个最小项目（10 秒）

```bash
python3 -m factscribe init mypaper
cd mypaper
```

生成 7 个文件：项目声明、主文件、一节正文、空账、人签清单模板、`refs.bib`、README。

## 2. 造一份原始材料（30 秒）

真实项目里这里放实验记录、统计输出、问卷汇总。示范用一行：

```bash
printf '50 道题里答对 42 道。\n' > results/exp.md
```

## 3. 记一条事实（30 秒）

```bash
python3 -m factscribe fact add . \
  --id A1 \
  --claim "实验在 50 道题里答对 42 道" \
  --value "42/50" \
  --source results/exp.md \
  --locator "第 1 行"
```

工具会自动算 `results/exp.md` 的 sha256，并打印一行：

```
"results/exp.md" = "<一串 sha256>"
```

**它不替你签。** 这一行要你亲手抄进清单。

## 4. 人签（1 分钟）

打开 `results/MANIFEST.toml`，填名字、时间，把上一步打印的那一行抄进 `[files]`：

```toml
[manifest]
signed_by = "你的名字"
signed_at = "2026-11-12T10:00:00Z"
version = 1

[files]
"results/exp.md" = "<上一步打印的 sha256>"
```

签名的意思是：**你确认这份原始材料是真的**。工具只能保证它从这一刻起没被改。

## 5. 正文绑定（1 分钟）

把 `sections/01-intro.tex` 换成：

```tex
\section{引言}

这项实验在 50 道题里答对 42 道\fact{A1}。
```

`\fact{A1}` 是钩子：这一行的数字，必须全部落在 `A1` 的 `42/50` 里。

## 6. 审计（30 秒）

```bash
python3 -m factscribe audit .
```

看到这一行就成了：

```
结论：0 红 / 0 黄 → 绿（退出码 0）
```

## 红了怎么办

看 [TRIAGE.md](TRIAGE.md)。第一次的红通常只有两类：

1. 正文有数字没绑 `\fact{}`；
2. `\cite` 的 key 不在 `refs.bib` 里。

## 接下来

| 想做什么 | 用哪条 |
|---|---|
| 起草前拿依据 | `factscribe brief .` |
| 让模型改稿、再验收 | `factscribe polish --plan .` → 改 → `factscribe review --before 旧 --after 新` |
| 环境又缺东西 | `factscribe doctor .` |
| 一次看全部命令 | `python3 -m factscribe --help` |

一句话记住：**`\fact{ID}` 是正文与账之间的钩子；账里每条事实都要有来源、有哈希、有人签。**
