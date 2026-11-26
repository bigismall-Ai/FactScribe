# Attribution —— 意大利宪法法院判例语料（it-case）

本目录（`integrations/factscribe-legal/corpus/it-case/`）下的官方判决样例与其派生件
（切片、证据卡、索引）均来自**意大利宪法法院（Corte costituzionale della Repubblica
italiana）开放数据**。

## 署名（Attribution）

> **Fonte: Corte costituzionale della Repubblica italiana — dati aperti
> (dati.cortecostituzionale.it, pagina "Scarica i dati")**

- 官方通道（匿名直链可下；主站 `www.cortecostituzione.it` 有 WAF 403，本批未用主站）：
  `https://dati.cortecostituzionale.it/opendata/distribuzione/CC_OpenPronunce_1956_1980.zip`
- 下载页：`https://dati.cortecostituzionale.it/Scarica_i_dati/Scarica_i_dati`
- 证据卡内每张都带 `ATTRIBUTION:` 行（与本文件同一署名）。

## 许可与原文引用

官方下载页原文（逐字引用）：

> «I dati disponibili in vari formati sono rilasciati con licenza Creative Commons
> (CC BY SA 3.0) per il libero riuso.»

即：**Creative Commons CC BY-SA 3.0**（署名—相同方式共享）。

## 同方式共享声明

> 本目录下的官方判决样例与其派生件（切片、证据卡、索引）以 CC BY-SA 3.0 提供
> （署名＋相同方式共享）；该等样例以 CC BY-SA 3.0 提供，仓库其余部分许可不受影响。

## 本批入库的两件 fixture（取件日 2026-11-16）

| 文件 | sha256 | 取件日 |
|---|---|---|
| `run-20261116-itcase-1956_1980/official/ECLI-IT-COST-1956-1.xml` | `1b014aa29ce05def5c2f054a9caddb0307739fcf6803668f18b704446df86141` | 2026-11-16 |
| `run-20261116-itcase-1956_1980/official/ECLI-IT-COST-1956-2.xml` | `5b882166e27cff9c4d2ec74dabf1d7367fc099953c538fa8c50b20c7f770f773` | 2026-11-16 |

- 判决一：`ECLI:IT:COST:1956:1`（sentenza，1956 年第 1 号，裁判日 05/06/1956）
- 判决二：`ECLI:IT:COST:1956:2`（sentenza，1956 年第 2 号，裁判日 14/06/1956）

派生件（同目录根部，随官方件一起以 CC BY-SA 3.0 提供）：
`ECLI-IT-COST-1956-1.itcase.card.txt`、`ECLI-IT-COST-1956-2.itcase.card.txt`、`index.json`。

## 来源包（真件跑门用）

| 档 | 直链 | 体积 | Last-Modified | sha256 |
|---|---|---|---|---|
| 1956–1980 | `.../CC_OpenPronunce_1956_1980.zip` | 14 887 390 B | `Mon, 16 Nov 2026 04:11:54 GMT` | `8e9319be3ca4077e620d4c5b19a304ffc5b6dc18b97ff47702b9e38d8471439b` |
| 1981–2000 | `.../CC_OpenPronunce_1981_2000.zip` | 36 154 053 B | `Mon, 16 Nov 2026 04:11:57 GMT` | （本批未取） |
| 2001–oggi | `.../CC_OpenPronunce_2001_oggi.zip` | 57 545 646 B | `Mon, 16 Nov 2026 04:12:00 GMT` | （本批未取） |

官方包内容＝逐年判决档案 XML（1956_1980 档＝`Cc_Opendata_Pronunce_1956.xml` …
`Cc_Opendata_Pronunce_1980.xml`，共 25 份；根标签 `elenco_pronunce`）。

## 口径声明

- 本目录只含**宪法法院**一审（宪法性裁判）判决；不含民刑普通法院、不含最高法院
  （官方开放数据本身即不含，见下载页数据集清单）。
- 入库的两件 fixture 是「探查期取回的单件判决文件」（物理行尾 CRLF→LF 归一＋
  `<elenco_pronunce>` 包装）；抓取器真跑从官方包切出的是**档案字节的原样子串**
  （物理 CRLF 行尾、无包装）。两者的确定性纯文本 `text_sha256` 完全相同，
  可互为确定性锁；差异记录在 `corpus/state/fetch_state.json` 的
  `sources.it-case.notes.fixture_normalization`。
- 仓库其余部分（`factscribe/` 核心、`integrations/factscribe-legal/` 的其余部分等）许可不受影响。
