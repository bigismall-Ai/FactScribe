# 词表来源

这三份是**数据**，不是代码。本仓不实现制品导入器，也不解析 `termbank.tb` 的二进制格式。

## termbank-core.tsv

- 内容：词库核心层，`status = draft` 的 151 条，字段 `id/cn/en/aliases/slot/status`。
- 来源：`sia-harness/nomenclator/termbank.tb`（库版本 18，总条目 2,206,115）。
- 生成：在 `sia-harness` 侧用 Python 3.14 读制品后一次性导出；本仓只保留结果。
- 用途：术语表候选。**不自动进** `paper.tsv`，要人勾。

## cilin-groups.tsv.gz

- 内容：9,995 组同义词类，每行 `组号 \t 成员1|成员2|...`。
- 来源：`sia-harness/nomenclator/refsrc/CoreSynonym.txt`（哈工大《同义词词林》扩展版，HanLP 分发面）。
- 为什么不用 termbank：制品压缩时把组结构拍平成单词行，**组信息丢失**；只能回原料取。
- 用途：只做「疑似同义」提示。词林分的是**概念近义**，不是可互换；自动合并会重演 `成本` / `预算` 那类误报。

## 为什么不复制整个 termbank.tb

1. 13 MB 自研二进制，读取依赖 Python 3.14 的 `compression.zstd`；本仓最低支持 3.10。
2. 其中 179 万条是无词频、无词性的词面，分词价值低于 `jieba-dict`（34.9 万条，带词频与词性）。
3. 真正有增量的是核心层与同义词组，两者合计不到 260 KB。

需要更多词面时，复制 `jieba-dict.txt` 并另存一份来源说明，不要再引入二进制制品。
