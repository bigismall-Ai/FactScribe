# corpus/ —— 法律六闸消费的语料与防再丢清单

本目录是 `tools/fetch_corpus.py` 的产物＋对账清单。各闸 reader 直接吃这里的数据：

| 子目录 | reader | 内容 |
|---|---|---|
| `fr/` | `provisions.py`（verify 闸） | `index.json`＋官方条文 XML＋证据卡＋`view_current.jsonl` 小视图 |
| `cn/` | `cn_corpus.py`（verify-cn 闸） | `catalog.jsonl.gz`＋证据卡＋详情 JSON 原始字节 |
| `it/run-<vigenza>-it-<anno>n<numero>/` | `it_verify.py`（verify-it 闸） | `index.json`＋官方 AKN 整件＋条文切片＋证据卡 |
| `es/run-<YYYYMMDD>-es-<slug>/` | `es_verify.py`（verify-es 闸） | `index.json`＋官方 BOE 合并文本整件＋条文切片＋证据卡 |
| `fr-case/run-<YYYYMMDD>-inca/` | `fr_case_verify.py`（verify-fr-case 闸） | `index.json`＋官方判决 XML＋纯文本还原件＋证据卡＋`ATTRIBUTION.txt`（许可署名） |
| `it-case/run-<YYYYMMDD>-itcase-<tier>/` | `it_case_verify.py`（verify-it-case 闸） | `index.json`＋官方判决切片＋`.itcase.card.txt` 证据卡（Attribution 见 `it-case/ATTRIBUTION.md`） |
| `case/` | `case_verify.py`（verify-case 闸） | **本批为空**：检索接口需登录（见下） |
| `manifest.json` | —— | 防再丢清单：每文件 sha256＋取数时间＋来源 URL |
| `state/fetch_state.json` | —— | 增量续抓状态（已取清单＋sha），重跑自动跳过 |

`manifest.files` 里每个 sha256 都可对账：现算不一致＝该文件与取件时不一致。

## 再取方法

```bash
# 抽样（本批口径；礼貌机制默认写死：uniform 2–6s 间隔、指数退避、串行、自报 UA）
python3 tools/fetch_corpus.py fetch --source all --mode sample

# 全量（先看预计请求数，加 --yes 才真跑）
python3 tools/fetch_corpus.py fetch --source fr --mode bulk            # Freemium 全量包 ≈1.2GB
python3 tools/fetch_corpus.py fetch --source cn --mode bulk            # 全库翻页＋逐部详情
python3 tools/fetch_corpus.py fetch --source it --mode bulk            # 样单内每法 3 请求
python3 tools/fetch_corpus.py fetch --source es --mode bulk            # 样单内每法 1 请求（by-id 整件）
python3 tools/fetch_corpus.py fetch --source fr-case --mode bulk       # INCA 全球判决全量档案 ≈664MB
python3 tools/fetch_corpus.py fetch --source it-case --mode bulk        # 判决档案三档（每档 1 HEAD＋1 GET）

# 把语料物化成合成小项目（事实账＋证据卡＋paper.tex，四闸直接跑）
python3 tools/fetch_corpus.py materialize --project /tmp/fs-legal-demo

# 重算 manifest
python3 tools/fetch_corpus.py manifest
```

参考日用 `--reference-date YYYY-MM-DD`（默认今天；意大利侧取件参数
`dataVigenza`＝参考日当天生效的版本——判版本时效比取件参数，比文本日期戳，
见 INTEGRATION-LEGAL §5.3 的日期纪律）。

## 各源官方通道与限制（2026-11-16 实测）

- **法国** DILA LEGI 增量包（`echanges.dila.gouv.fr/OPENDATA/LEGI/`），
  Etalab 开放许可。sample＝当日增量包；bulk＝`Freemium_legi_global` 全量包（约 1.2GB）。
- **中国法条** 国家法律法规数据库 `flk.npc.gov.cn`（新版接口
  `/law-search/search/list`＋`/law-search/search/flfgDetails?bbbs=`；请求体形经
  官网前端实测核对）。官方详情 JSON **不含条文正文**，只有章→条目录树。
- **意大利** Normattiva：检索走正式 API `api.normattiva.it/t/normattiva.api`
  （`ricerca/avanzata`），取件走 `www.normattiva.it/do/atto/caricaAKN`——必须先
  GET ELI CONSOLIDATED 页建立会话（JSESSIONID＋NCC），再从页面里解析 caricaAKN
  链接取 AKN；www 站拒绝带 `Origin` 头（HTTP 409）。CC BY 4.0。
- **中国案例** 人民法院案例库 `rmfyalk.court.gov.cn`：检索接口要求登录，
  **匿名通道不抓**。要补数据：注册个人账号后人工检索需要的入库案例、导出正文
  放 `case/official/<slug>.txt`，再跑 `materialize`（脚本会补卡与回执链）。
- **西班牙** BOE 开放数据 `www.boe.es/datosabiertos/api/legislacion-consolidada`
  （`by-id`，官方标识形如 `BOE-A-2015-10565`）：⚠️ 必须带 `Accept: application/xml`
  （官方对别的 mime 头回 400「No soportado ningún mime type…」）；⚠️ 域名是
  `www.boe.es`，`api.boe.es` **不存在**（DNS NXDOMAIN）。整件＝合并文本 XML，
  条文＝`<bloque id="a7" tipo="precepto">` 块。复用须注明出处（AEBOE 复用条件）。
- **法国判例** DILA 开放数据 INCA 全球判决档案
  `echanges.dila.gouv.fr/OPENDATA/INCA/`（stock `Freemium_inca_global_*.tar.gz`
  全量约 664MB）。sample＝**只取 12MB 前缀**（1 次目录索引 ＋ 1 次 HTTP Range
  206），流式解 tar.gz 到够数即停，不下载全量；bulk＝整包下载（须 `--yes`）。
  每件判决一个 XML（`TEXTE_JURI_JUDI` ＋ LEGIFRANCE DTD），正文完整。
  许可：**licence ouverte v2.0**（Etalab/DILA）⇒ 署名三件套＝发布方 DILA ＋
  源 URL（档案 URL＋档案内路径）＋下载日期，见 `fr-case/ATTRIBUTION.txt`。
- **意大利宪法法院判例** Corte costituzionale 开放数据
  `dati.cortecostituzionale.it/opendata/distribuzione/CC_OpenPronunce_*.zip`
  （三档：1956–1980／1981–2000／2001–oggi；ZIP 套 ZIP，档内是**逐年**的判决档案
  XML，根标签 `elenco_pronunce`，每件判决一个 `<pronuncia>`）：⚠️ 主站
  `www.cortecostituzione.it` 有 WAF 403，开放数据子域匿名直链可下；⚠️ 该服务器
  **虽回 `Accept-Ranges` 但忽略 Range 头**（断点续传无效，实测下行约 18KB/s，
  单发超时须放宽）；抓取器有本地复用逻辑（`raw/` 里 zip 完整即不发请求）。
  CC BY-SA 3.0（署名＋相同方式共享；见 `it-case/ATTRIBUTION.md`）。

## TLS 注意

证书验证永不关闭。若本机 CA 束缺信任根（实测：macOS 系统 cert.pem 缺
GlobalSign Root R46，`api.normattiva.it` 2025-10 起的新链验不过），放一份
`curl.se/ca/cacert.pem` 到本目录 `state/cacert-mozilla.pem`（该文件不入库），
脚本会自动换用。

## 本批内容（2026-11-16，sample）

- FR 3 条：Code rural D641-10-1、Code de l'environnement L594-8 与 R557-6-14-1
  （来源增量包 LEGI_20261115-205552.tar.gz，pool_asof=2026-11-15）
- CN 2 部：《中华人民共和国劳动法》（107 条树，sxx=3）、《中华人民共和国劳动合同法》
  （98 条树，sxx=3）
- IT 2 法 4 切片：Legge 190/2012（现行版仅余 art.1–2，取 art.2）、
  Legge 241/1990（art.1–3）
- ES 3 法 9 切片：Ley 39/2015（BOE-A-2015-10565，art.1–3）、
  Ley 40/2015（BOE-A-2015-10566，art.1–3）、
  Constitución Española（BOE-A-1978-31229，art.1–3）
- FR-CASE 4 件判决（`fr-case/run-20261116-inca/`，取自
  `Freemium_inca_global_20261108-140000.tar.gz`，下载日期 2026-11-16）：
  Cour de cassation 1900-07-30（JURITEXT000006953017）、1990-10-09
  （JURITEXT000007100000）、2004-09-29（JURITEXT000007471838，正文含
  «3 500 euros»）、Tribunal de grande instance de Paris 2006-12-15
  （JURITEXT000006951547，正文含 «300.000 euros»＝30 万）
- IT-CASE 2 判决（1956_1980 档）：`ECLI:IT:COST:1956:1`（裁判日 05/06/1956）、
  `ECLI:IT:COST:1956:2`（裁判日 14/06/1956）——真判决原字节切片＋两张
  `.itcase.card.txt` 证据卡；来源包 sha256 见 `it-case/ATTRIBUTION.md`
- CASE：无（需登录，见上）
