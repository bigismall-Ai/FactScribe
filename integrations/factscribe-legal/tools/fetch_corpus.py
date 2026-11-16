#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factscribe-legal 语料抓取器（收编入仓版，v0.1）。

为什么存在
----------
法律五闸（verify / verify-cn / verify-case / verify-it / verify-es）只消费「已钉哈希的官方件」，
原先「取件、钉哈希、建卡、选版」的脚本随预研代理销毁（见 docs/implementation/
LEGAL-TAKEOVER.md 松尾账 2.2）。本件把再取方法收编进仓，消除单点丢失。

三条硬规矩（默认写死，不可绕过）
--------------------------------
1. 礼貌机制：请求间隔取随机数（uniform 2–6 秒，下限 2 秒锁死）；失败/429/5xx
   指数退避（起 30 秒、倍增、封顶 30 分钟），尊重 Retry-After；串行单线程；
   User-Agent 自报身份。
2. 增量可续：state 文件（corpus/state/fetch_state.json）记已取清单与 sha256，
   重跑跳过已取件。
3. 规模闸：默认 sample 模式每源只取少量样例（默认 ≤10 件，本批实跑各取 2–3）；
   bulk 全量必须显式 --bulk 且先打印预计请求数要人确认（--yes 才动）。

TLS 纪律：证书验证**永不关闭**（fail-closed）。若本机 CA 束缺某个信任根
（实测过：macOS 系统 cert.pem 缺 GlobalSign Root R46，api.normattiva.it
2025-10 起的新链验不过），脚本按「系统默认 → 常见系统束 → state/cacert-mozilla.pem
→ certifi」逐个换信任根重试；把 `curl.se/ca/cacert.pem` 下载一份存到
`<corpus>/state/cacert-mozilla.pem` 即愈（state 目录已在 .gitignore 排除该文件）。

用法
----
  # 抽样（本批交付的口径）
  python3 tools/fetch_corpus.py fetch --source fr --mode sample
  python3 tools/fetch_corpus.py fetch --source cn --mode sample
  python3 tools/fetch_corpus.py fetch --source it --mode sample
  python3 tools/fetch_corpus.py fetch --source es --mode sample

  # 全量（以后真要时照此跑；会先打印预计请求数）
  python3 tools/fetch_corpus.py fetch --source fr --mode bulk          # 只出计划
  python3 tools/fetch_corpus.py fetch --source fr --mode bulk --yes    # 确认后开跑
  python3 tools/fetch_corpus.py fetch --source cn --mode bulk --yes
  python3 tools/fetch_corpus.py fetch --source it --mode bulk --yes
  python3 tools/fetch_corpus.py fetch --source es --mode bulk --yes

  # 把语料物化成一个合成小项目（事实账＋证据卡＋paper.tex，供四闸跑读数）
  python3 tools/fetch_corpus.py materialize --project /tmp/fs-legal-demo

  # 重算 manifest（清单＋sha256＋取数时间＋来源 URL，入库防再丢）
  python3 tools/fetch_corpus.py manifest

数据落位（corpus-root，默认本件同级 ../corpus/）
------------------------------------------------
  corpus/
    manifest.json               入库：防再丢的清单
    state/fetch_state.json      入库：增量续抓状态（含礼貌参数留痕）
    fr/                         provisions.py reader 直接吃的形状：
      index.json                  {"pool_asof", "provisions": {num: {...}}}
      <编号>.xml                  官方条文 XML 原字节（权威层）
      <编号>.card.txt             证据卡（含 OFFICIAL_XML_SHA256）
      view_current.jsonl          现行版小视图（{"num","id",...}，verify --view 吃）
      raw/                        不入库：增量包下载与解压区
    cn/
      catalog.jsonl.gz            cn_corpus.load_catalog 直接吃的形状（sample）
      catalog_full.jsonl.gz       bulk 全量时另出，不覆盖 sample
      cards/<slug>.cn.card.txt    证据卡（含 OFFICIAL_DETAIL_SHA256）
      raw/                        不入库：详情 JSON 原始字节（同时逐件入库在 cards 旁）
    it/run-<YYYYMMDD>-it/         it_verify reader 直接吃的形状：
      index.json                  {"act_urn", "source_file", "source_sha256", "articles"...}
      official/act.akn.xml        官方 AKN 整件（权威层）
      official/<eid>.xml          条文切片（与整件字节一致的子串）
      <eid>.it.card.txt           证据卡
    es/run-<YYYYMMDD>-es-<slug>/  es_verify reader 直接吃的形状：
      index.json                  {"act_id", "source_file", "source_sha256", "articles"...}
      official/act.xml            官方 BOE 合并文本整件（权威层）
      official/<block_id>.xml      条文切片（与整件字节一致的子串）
      <block_id>.es.card.txt      证据卡
    case/                        案例库（人民法院案例库）——检索接口需登录，
                                  匿名通道拒绝抓取（见 fetch_case_probe），本批为空。

官方通道（均为开放数据接口，非爬页面；出处 README「语料从哪来」节）
------------------------------------------------------------------
  FR  DILA LEGI 增量包  https://echanges.dila.gouv.fr/OPENDATA/LEGI/      Etalab 开放许可
  CN  国家法律法规数据库 https://flk.npc.gov.cn/（law-search/search/*）    官方公开接口
  IT  Normattiva OpenData https://www.normattiva.it/do/atto/caricaAKN     CC BY 4.0
      （检索经 https://api.normattiva.it/t/normattiva.api 正式 API）
  ES  BOE 开放数据 https://www.boe.es/datosabiertos/api/legislacion-consolidada
      （合并文本 by-id；AEBOE 复用条件，须注明出处）  BOE 复用条款（2024-06-27 决议）
  CN案例 人民法院案例库 https://rmfyalk.court.gov.cn/（需登录，匿名不抓）

退出码：0 全部成功 / 2 用法错或 bulk 未确认 / 3 部分源失败（详见日志）
Python ≥ 3.10，纯标准库。
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import http.cookiejar as http_cookiejar
import io
import json
import os
import random
import re
import shutil
import ssl
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date as _date
from datetime import datetime, timezone

TOOL_VERSION = "0.1"

# ---------------------------------------------------------------------------
# 礼貌机制（默认写死；命令行可调宽但不能低于下限）
# ---------------------------------------------------------------------------
USER_AGENT = ("factscribe-legal-corpus/%s "
              "(legal-citation verification research; sources: FR/CN/IT/ES; "
              "contact: repo issues)"
              % TOOL_VERSION)
MIN_INTERVAL_S = 2.0        # 下限锁死：任何情况下相邻请求至少隔 2 秒
DEFAULT_INTERVAL_MIN = 2.0
DEFAULT_INTERVAL_MAX = 6.0
BACKOFF_START_S = 30.0      # 指数退避起点
BACKOFF_FACTOR = 2.0
BACKOFF_CAP_S = 1800.0      # 单次退避封顶 30 分钟
MAX_ATTEMPTS = 6            # 单个请求最多试 6 次（30+60+120+240+480 ≈ 15.5 分钟）
RETRY_AFTER_CAP_S = 7200.0  # Retry-After 尊重但封顶 2 小时，防异常大值挂死
RETRYABLE_STATUS = (429, 500, 502, 503, 504)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CORPUS_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, os.pardir, "corpus"))
STATE_REL = os.path.join("state", "fetch_state.json")
MANIFEST_NAME = "manifest.json"

FR_BASE = "https://echanges.dila.gouv.fr/OPENDATA/LEGI/"
CN_SEARCH_URL = "https://flk.npc.gov.cn/law-search/search/list"
CN_DETAIL_URL = "https://flk.npc.gov.cn/law-search/search/flfgDetails"
IT_API_BASE = "https://api.normattiva.it/t/normattiva.api"
IT_SEARCH_PATH = "/bff-opendata/v1/api/v1/ricerca/semplice"
IT_ADV_SEARCH_PATH = "/bff-opendata/v1/api/v1/ricerca/avanzata"
IT_AKN_URL = "https://www.normattiva.it/do/atto/caricaAKN"
ES_API_BASE = "https://www.boe.es/datosabiertos/api/legislacion-consolidada"
CASE_HOME_URL = "https://rmfyalk.court.gov.cn/"

# sample 抽样默认目标（规模闸：bulk 之外每源最多取这么多件）
CN_SAMPLE_QUERIES = ["中华人民共和国劳动法", "中华人民共和国劳动合同法",
                     "中华人民共和国产品质量法"]
IT_SAMPLE_ACTS = [("2012", "190"), ("1990", "241")]  # ( anno, numero ) 落空则顺延
# ES sample 样单（BOE 官方标识 → 目录 slug）；每件 1 次请求（by-id 合并文本 XML）。
# BOE 标识形如 BOE-A-<年份>-<序号>（BOE-A-2015-10565 = Ley 39/2015）。
ES_SAMPLE_ACTS = [
    ("BOE-A-2015-10565", "ley39-2015-procedimiento-administrativo"),
    ("BOE-A-2015-10566", "ley40-2015-regimen-local"),
    ("BOE-A-1978-31229", "const1978-constitucion-espanola"),
]

ART_CN_RE = re.compile(r"^第[一二三四五六七八九十百千零〇两]+条$")
ES_BLOQUE_RE = re.compile(rb'<bloque id="([^"]+)"([^>]*)>(.*?)</bloque>', re.S)
ES_META_RE = re.compile(rb"<metadatos>(.*?)</metadatos>", re.S)
ES_ART_ID_RE = re.compile(r"^a(\d+)$")
IT_ARTICLE_RE = re.compile(rb'<article eId="(art_[0-9]+)">(.*?)</article>', re.S)
IT_ARTICLE_EID_RE = re.compile(rb'<article eId="(art_[0-9]+)">')
DILA_INCREMENT_RE = re.compile(r'href="(LEGI_\d{8}-\d{6}\.tar\.gz)"')
DILA_GLOBAL_RE = re.compile(r'href="(Freemium_legi_global_\d{8}-\d{6}\.tar\.gz)"')


class FetchError(RuntimeError):
    """某个源整体失败（如实报备用）。"""


def log(msg):
    print(msg, flush=True)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# 礼貌 HTTP 层
# ---------------------------------------------------------------------------
class PoliteHttp:
    """串行、随机间隔、指数退避、自报身份的 HTTP 客户端。

    每次**请求之前**都先睡一个 uniform(min,max) 随机间隔（含本进程第一发——
    上一轮抓取的最后一发可能就在刚才，间隔一律拉开）。429/5xx/网络瞬断按
    30s、60s、120s… 倍增退避，Retry-After 头给得更大就尊重它（封顶 2 小时）。
    """

    def __init__(self, interval_min=DEFAULT_INTERVAL_MIN,
                 interval_max=DEFAULT_INTERVAL_MAX, ca_extra_paths=None):
        self.interval_min = max(float(interval_min), MIN_INTERVAL_S)
        if float(interval_min) < MIN_INTERVAL_S:
            log("[polite] 请求间隔下限 %ss 锁死，--interval-min 已被抬到下限" % MIN_INTERVAL_S)
        self.interval_max = max(float(interval_max), self.interval_min)
        self.request_count = 0
        self.gap_log = []          # 每次随机间隔实值（礼貌机制自证用）
        # CA 束候选：默认 → 常见系统路径 → 语料目录里的 Mozilla 束 → certifi。
        # ⚠️ 证书验证永不关闭（fail-closed）；只是逐个换「信任根来源」。
        #   本机踩过的坑：macOS 系统 cert.pem 与部分 venv OpenSSL 缺
        #   GlobalSign Root R46（api.normattiva.it 2025 年换的新链），
        #   放一份 curl.se/ca/cacert.pem 到 <corpus>/state/cacert-mozilla.pem 即愈。
        self._ca_paths = []
        for p in ["/etc/ssl/certs/ca-certificates.crt",   # Debian/Ubuntu
                  "/etc/pki/tls/cert.pem",                # RHEL/Fedora
                  "/etc/ssl/cert.pem",                    # macOS
                  ] + list(ca_extra_paths or []):
            if p and p not in self._ca_paths:
                self._ca_paths.append(p)
        self._ctx_candidates = None
        self._ctx_idx = 0
        self._ctx = None

    def _contexts(self):
        if self._ctx_candidates is None:
            cands = [("系统默认", ssl.create_default_context())]
            for p in self._ca_paths:
                if os.path.exists(p):
                    try:
                        cands.append(("束 %s" % os.path.basename(p),
                                      ssl.create_default_context(cafile=p)))
                    except ssl.SSLError:
                        pass
            try:
                import certifi
                cands.append(("certifi",
                              ssl.create_default_context(cafile=certifi.where())))
            except ImportError:
                pass
            self._ctx_candidates = cands
            self._ctx_idx = 0
            self._ctx = cands[0][1]
        return self._ctx_candidates

    def _next_context(self):
        cands = self._contexts()
        if self._ctx_idx + 1 < len(cands):
            self._ctx_idx += 1
            self._ctx = cands[self._ctx_idx][1]
            return cands[self._ctx_idx][0]
        return None

    def _polite_gap(self, url):
        gap = random.uniform(self.interval_min, self.interval_max)
        self.gap_log.append(round(gap, 2))
        log("[gap]    sleeping %.2fs (uniform %.2f–%.2fs)  before %s"
            % (gap, self.interval_min, self.interval_max, url))
        time.sleep(gap)

    @staticmethod
    def _retry_after(headers):
        v = headers.get("Retry-After") if headers else None
        if not v:
            return None
        v = v.strip()
        if re.fullmatch(r"\d+", v):
            return min(float(v), RETRY_AFTER_CAP_S)
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(v)
            delta = (dt - datetime.now(timezone.utc)).total_seconds()
            return max(0.0, min(delta, RETRY_AFTER_CAP_S))
        except Exception:
            return None

    def request(self, url, method="GET", headers=None, data=None, timeout=90,
                jar=None):
        """返回 dict(status, headers, body)。失败按退避重试，穷尽即抛 FetchError。

        jar：可选 http.cookiejar.CookieJar —— Normattiva 的 ELI 页→caricaAKN
        两步要同一个 servlet 会话（JSESSIONID + NCC 亲和），传同一只 jar 即可。
        """
        last_err = None
        attempt = 0
        self._contexts()  # 初始化 CA 束候选（验证始终开启）
        while attempt < MAX_ATTEMPTS:
            self._polite_gap(url)
            self.request_count += 1
            try:
                req = urllib.request.Request(
                    url, data=data, method=method,
                    headers={"User-Agent": USER_AGENT, **(headers or {})})
                handlers = [urllib.request.HTTPSHandler(context=self._ctx)]
                if jar is not None:
                    handlers.append(urllib.request.HTTPCookieProcessor(jar))
                opener = urllib.request.build_opener(*handlers)
                with opener.open(req, timeout=timeout) as resp:
                    body = resp.read()
                    log("[req]    %s %s -> %s (%d bytes)"
                        % (method, url, resp.status, len(body)))
                    return {"status": resp.status, "headers": dict(resp.headers),
                            "body": body, "final_url": resp.geturl()}
            except urllib.error.HTTPError as e:
                last_err = e
                log("[req]    %s %s -> HTTP %s" % (method, url, e.code))
                if e.code in RETRYABLE_STATUS:
                    ra = self._retry_after(e.headers)
                    delay = min(BACKOFF_CAP_S,
                                BACKOFF_START_S * (BACKOFF_FACTOR ** (attempt - 1)))
                    if ra is not None and ra > delay:
                        delay = ra
                        why = "retry-after=%.0fs" % ra
                    else:
                        why = "exponential"
                    if attempt < MAX_ATTEMPTS:
                        log("[backoff] HTTP %s on attempt %d/%d -> sleep %.0fs (%s)"
                            % (e.code, attempt, MAX_ATTEMPTS, delay, why))
                        time.sleep(delay)
                        continue
                    break
                # 4xx 其它（403/404…）：不重试，如实报错
                detail = e.read(400).decode("utf-8", "replace") if e.fp else ""
                raise FetchError("HTTP %s（不重试）：%s %s :: %s"
                                 % (e.code, method, url, detail))
            except urllib.error.URLError as e:
                reason = getattr(e, "reason", None)
                if isinstance(reason, ssl.SSLCertVerificationError):
                    label = self._next_context()
                    if label is not None:
                        log("[tls]    证书验证失败（当前 CA 束不含该信任根）"
                            "-> 换候选：%s（验证始终开启，绝不关闭）" % label)
                        continue  # 不算退避：换信任根立即重试同一请求
                attempt += 1
                last_err = e
                delay = min(BACKOFF_CAP_S,
                            BACKOFF_START_S * (BACKOFF_FACTOR ** (attempt - 1)))
                log("[backoff] %s: %s on attempt %d/%d -> sleep %.0fs"
                    % (type(e).__name__, str(e)[:120], attempt, MAX_ATTEMPTS, delay))
                if attempt < MAX_ATTEMPTS:
                    time.sleep(delay)
                    continue
                break
            except Exception as e:  # 网络瞬断类
                last_err = e
                delay = min(BACKOFF_CAP_S,
                            BACKOFF_START_S * (BACKOFF_FACTOR ** (attempt - 1)))
                log("[backoff] %s: %s on attempt %d/%d -> sleep %.0fs"
                    % (type(e).__name__, str(e)[:120], attempt, MAX_ATTEMPTS, delay))
                if attempt < MAX_ATTEMPTS:
                    time.sleep(delay)
                    continue
                break
        raise FetchError("请求穷尽 %d 次：%s %s（最后错误：%s）"
                         % (MAX_ATTEMPTS, method, url, last_err))

    def get_json(self, url, headers=None):
        r = self.request(url, headers={"Accept": "application/json, text/plain, */*",
                                       **(headers or {})})
        return json.loads(r["body"].decode("utf-8"))

    def post_json(self, url, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        r = self.request(url, method="POST", data=body,
                         headers={"Accept": "application/json, text/plain, */*",
                                  "Content-Type": "application/json;charset=utf-8",
                                  **(headers or {})})
        return json.loads(r["body"].decode("utf-8"))

    def download(self, url, dest_path, headers=None):
        r = self.request(url, headers=headers or {})
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as fh:
            fh.write(r["body"])
        return r


# ---------------------------------------------------------------------------
# state（增量续抓）与 manifest（防再丢清单）
# ---------------------------------------------------------------------------
class State:
    def __init__(self, path):
        self.path = path
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                self.d = json.load(fh)
        else:
            self.d = {"version": 1, "politeness": {
                "interval": "uniform %.1f-%.1fs (floor %ss locked)" % (
                    DEFAULT_INTERVAL_MIN, DEFAULT_INTERVAL_MAX, MIN_INTERVAL_S),
                "backoff": "start %.0fs x%.1f cap %.0fs, Retry-After respected" % (
                    BACKOFF_START_S, BACKOFF_FACTOR, BACKOFF_CAP_S),
                "user_agent": USER_AGENT,
            }, "sources": {}}

    def src(self, source):
        return self.d["sources"].setdefault(source, {"items": {}, "notes": {}})

    def fetched(self, source, item_id):
        return self.src(source)["items"].get(item_id)

    def mark(self, source, item_id, url, sha256, bytes_=None, **extra):
        rec = {"url": url, "sha256": sha256, "fetched_at": now_iso()}
        if bytes_ is not None:
            rec["bytes"] = bytes_
        rec.update(extra)
        self.src(source)["items"][item_id] = rec

    def note(self, source, key, value):
        self.src(source)["notes"][key] = value

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.d, fh, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, self.path)


def _canonical_jsonl(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def write_gzip_jsonl(path, records):
    """gzip JSONL（gzip mtime 钉 0，字节可复现）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    raw = ("".join(_canonical_jsonl(r) + "\n" for r in records)).encode("utf-8")
    with open(path, "wb") as fh:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
            gz.write(raw)


def collect_files(root, rel_ignore_prefixes=("raw/",)):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "raw")
        for name in sorted(filenames):
            if name == MANIFEST_NAME:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if any(rel.startswith(p) for p in rel_ignore_prefixes):
                continue
            if rel == "state/cacert-mozilla.pem":
                continue  # 第三方信任束，不入库也不入账（会过时）
            out.append(rel)
    return out


def build_manifest(corpus_root, state, reference_date):
    files = []
    for rel in collect_files(corpus_root):
        full = os.path.join(corpus_root, rel)
        files.append({"path": rel, "sha256": sha256_file(full),
                      "bytes": os.path.getsize(full)})
    manifest = {
        "manifest_version": 1,
        "tool": "tools/fetch_corpus.py %s" % TOOL_VERSION,
        "generated_at": now_iso(),
        "reference_date": reference_date,
        "politeness": state.d.get("politeness", {}),
        "sources": state.d.get("sources", {}),
        "files": files,
        "how_to_refetch": {
            "sample": "python3 tools/fetch_corpus.py fetch --source all --mode sample",
            "bulk_fr": "python3 tools/fetch_corpus.py fetch --source fr --mode bulk --yes "
                       "(先不带 --yes 看预计请求/体积)",
            "bulk_cn": "python3 tools/fetch_corpus.py fetch --source cn --mode bulk --yes",
            "bulk_it": "python3 tools/fetch_corpus.py fetch --source it --mode bulk --yes",
            "bulk_es": "python3 tools/fetch_corpus.py fetch --source es --mode bulk --yes",
            "note": "state/fetch_state.json 记了已取清单与 sha256；重跑自动跳过已取件。"
                    "manifest.files 的 sha256 可对账：对不上即该文件与取件时不一致。",
        },
    }
    path = os.path.join(corpus_root, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    return manifest


# ---------------------------------------------------------------------------
# FR —— DILA LEGI 增量包 → provisions.py reader 形状
# ---------------------------------------------------------------------------
FR_PREFER_CODE = "Code du travail"


def _dila_text(el, path):
    node = el.find(path)
    return (node.text or "").strip() if node is not None else ""


def parse_dila_article(xml_bytes):
    """解析 DILA 单条条文 XML；不是条文文件返回 None。"""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    if root.tag != "ARTICLE":
        return None
    meta = root.find("META")
    if meta is None:
        return None
    commun = meta.find("META_COMMUN")
    spec = meta.find("META_SPEC")
    art = spec.find("META_ARTICLE") if spec is not None else None
    if art is None:
        return None
    legiarti = ""
    if commun is not None:
        lien = commun.find("LIEN_ARTICLE")
        legiarti = (lien.get("id") if lien is not None else "") or \
                   _dila_text(commun, "ID")
    bloc = root.find("BLOC_TEXTUEL")
    text = ""
    if bloc is not None:
        text = " ".join(t.strip() for t in bloc.itertext() if t.strip())
    code_id, code_title = "", ""
    ctx = root.find("CONTEXTE")  # CONTEXTE 挂在 ARTICLE 根下（实测非 META_SPEC 内）
    if ctx is not None:
        texte = ctx.find("TEXTE")
        if texte is not None:
            # 现行版 TITRE_TXT：属_CODES 族时 c_titre_txt=Code xxx，其余常为 c_titre_court
            for titre in texte.findall("TITRE_TXT"):
                if (titre.get("id_txt") or titre.get("id") or "").startswith("LEGITEXT"):
                    code_id = titre.get("id_txt") or titre.get("id") or ""
                    code_title = titre.get("c_titre_txt") \
                        or titre.get("c_titre_court") or ""
                    break
    return {
        "legiarti": legiarti,
        "num": _dila_text(art, "NUM"),
        "etat": _dila_text(art, "ETAT"),
        "date_debut": _dila_text(art, "DATE_DEBUT"),
        "date_fin": _dila_text(art, "DATE_FIN"),
        "code_id": code_id, "code_title": code_title,
        "text": text,
    }


def fr_list_increments(http):
    r = http.request(FR_BASE, headers={"Accept": "text/html"})
    html = r["body"].decode("utf-8", "replace")
    incs = sorted(set(DILA_INCREMENT_RE.findall(html)))
    globals_ = sorted(set(DILA_GLOBAL_RE.findall(html)))
    return incs, globals_


def _safe_extract(tar_path, dest):
    """解压到 dest（新空目录）；成员路径逐个校验防越界。"""
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    dest_abs = os.path.abspath(dest)
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            target = os.path.abspath(os.path.join(dest, member.name))
            if not target.startswith(dest_abs + os.sep):
                raise FetchError("tar 成员越界：%s" % member.name)
            tar.extract(member, dest)
    return dest


def fetch_fr(http, corpus_root, state, max_items, mode, reference_date, yes):
    fr_dir = os.path.join(corpus_root, "fr")
    raw_dir = os.path.join(fr_dir, "raw")
    os.makedirs(fr_dir, exist_ok=True)

    incs, globals_ = fr_list_increments(http)
    if not incs:
        raise FetchError("DILA 目录里没找到增量包（LEGI_*.tar.gz）")
    if mode == "bulk":
        plan = ["FR bulk：Freemium_legi_global 全量包（%s 附近，约 1.2GB）" %
                (globals_[-1] if globals_ else "未列出"),
                "  预计请求：1 次列表（已发）+ 1 次下载 + 解压后逐条本地处理（无更多请求）"]
        for line in plan:
            log("[plan]  " + line)
        if not yes:
            if sys.stdin.isatty():
                if input("确认开跑？[y/N] ").strip().lower() not in ("y", "yes"):
                    log("[abort] 未确认，停止（--yes 可跳过询问）")
                    return 3
            else:
                log("[abort] bulk 需显式 --yes 才动（当前非交互终端）")
                return 2
        name = globals_[-1]
        dest = os.path.join(raw_dir, name)
        if os.path.exists(dest):
            log("[skip]  全量包已在本地：%s" % dest)
        else:
            http.download(FR_BASE + name, dest)
        extract = _safe_extract(dest, os.path.join(raw_dir, "extract-global"))
        pool_asof = name.split("_")[3][:8]
        return _fr_materialize(extract, fr_dir, state, max_items=None,
                               bulk=True, pool_asof=pool_asof,
                               source_url=FR_BASE + name)

    # ---- sample：最新增量包 ----
    inc = incs[-1]
    inc_url = FR_BASE + inc
    log("[pick]   FR 最新增量：%s" % inc)
    tar_path = os.path.join(raw_dir, inc)
    prev = state.fetched("fr", "increment:" + inc)
    if prev and os.path.exists(tar_path):
        log("[skip]  增量包已取过（state 命中），不重复下载：%s" % inc)
    else:
        http.download(inc_url, tar_path)
        state.mark("fr", "increment:" + inc, inc_url, sha256_file(tar_path),
                   os.path.getsize(tar_path))
    extract = _safe_extract(tar_path, os.path.join(raw_dir, "extract-" + inc[:-7]))
    pool_asof = "%s-%s-%s" % (inc.split("_")[1][0:4], inc.split("_")[1][4:6],
                              inc.split("_")[1][6:8])
    return _fr_materialize(extract, fr_dir, state, max_items=max_items,
                           bulk=False, pool_asof=pool_asof, source_url=inc_url)


def _fr_materialize(extract_dir, fr_dir, state, max_items, bulk, pool_asof,
                    source_url=""):
    cands = []
    seen_files = 0
    for dirpath, _dirs, files in os.walk(extract_dir):
        for name in files:
            if not name.endswith(".xml"):
                continue
            seen_files += 1
            path = os.path.join(dirpath, name)
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
            except OSError:
                continue
            info = parse_dila_article(raw)
            if not info or not info["num"] or not info["legiarti"]:
                continue
            info["raw"] = raw
            cands.append(info)
    log("[scan]   增量内共 %d 个 XML，其中条文 %d 条" % (seen_files, len(cands)))
    if not bulk:
        # 确定性选样：编号干净的条文优先（码式 L123-45 / R12 / 纯数字），
        # 排除附件表格（Annexe…、带空格编号）与超长正文；现行有效且正文带数字。
        def _rank(c):
            num = c["num"]
            style = 0 if re.fullmatch(r"[A-Z]\d+(?:-\d+)*", num) else \
                (1 if num.isdigit() else 9)
            return (c["code_title"] != FR_PREFER_CODE, style,
                    len(c["text"]), c["code_title"], num)
        cands.sort(key=_rank)
        picked, seen_num = [], set()
        for c in cands:
            if c["etat"] != "VIGUEUR" or not c["text"]:
                continue
            if not re.search(r"\d", c["text"]):
                continue
            if not re.fullmatch(r"[A-Za-z0-9-]+", c["num"]):
                continue  # 文件名要能当路径；带空格/括号的编号留给 bulk
            if len(c["text"]) > 20000:
                continue  # 附件大表不进 sample
            if c["num"] in seen_num:
                continue
            seen_num.add(c["num"])
            picked.append(c)
            if max_items and len(picked) >= max_items:
                break
    else:
        cands.sort(key=lambda c: (c["code_title"], c["num"]))
        picked = cands
    if not picked:
        raise FetchError("增量里没有可用的现行条文（多半是空批；换一天重跑即可）")

    index_path = os.path.join(fr_dir, "index.json")
    index = {"pool_asof": pool_asof, "generator": "fetch_corpus.py " + TOOL_VERSION}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as fh:
            old = json.load(fh)
        index["pool_asof"] = max(old.get("pool_asof") or "", pool_asof)
        index["provisions"] = old.get("provisions", {})
    else:
        index["provisions"] = {}
    provisions = index["provisions"]
    view = {}
    view_path = os.path.join(fr_dir, "view_current.jsonl")
    if os.path.exists(view_path):
        with open(view_path, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                view[r["num"]] = r

    added = 0
    for c in picked:
        num = c["num"]
        if num in provisions:
            log("[skip]  fr:%s 已在 index 里，不覆盖（重取请删 corpus/fr 重跑）" % num)
            continue
        xml_name = "%s.xml" % re.sub(r"[^A-Za-z0-9_-]", "_", num)
        xml_path = os.path.join(fr_dir, xml_name)
        with open(xml_path, "wb") as fh:
            fh.write(c["raw"])
        xml_sha = sha256_bytes(c["raw"])
        card = _fr_card(num, c, xml_name, c["raw"], pool_asof, source_url)
        card_path = os.path.join(fr_dir, "%s.card.txt" % num)
        with open(card_path, "w", encoding="utf-8") as fh:
            fh.write(card)
        provisions[num] = {
            "legiarti": c["legiarti"], "code_id": c["code_id"],
            "etat": c["etat"], "date_debut": c["date_debut"],
            "date_fin": c["date_fin"], "xml_file": xml_name,
            "code_title": c["code_title"],
        }
        view[num] = {"num": num, "id": c["legiarti"], "etat": c["etat"],
                     "date_debut": c["date_debut"], "date_fin": c["date_fin"],
                     "num_param": num}
        state.mark("fr", num,
                   url="dila://increment/%s#%s" % (pool_asof, c["legiarti"]),
                   sha256=xml_sha, bytes_=len(c["raw"]),
                   legiarti=c["legiarti"], etat=c["etat"],
                   date_debut=c["date_debut"], date_fin=c["date_fin"])
        added += 1
        log("[ok]    fr:%s (%s, %s, %s→%s)"
            % (num, c["legiarti"], c["etat"], c["date_debut"], c["date_fin"]))

    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    with open(view_path, "w", encoding="utf-8") as fh:
        for num in sorted(view):
            fh.write(_canonical_jsonl(view[num]) + "\n")
    state.note("fr", "pool_asof", index["pool_asof"])
    state.note("fr", "last_run", now_iso())
    log("[done]  FR：本次新增 %d 条，index 现有 %d 条（pool_asof=%s）"
        % (added, len(provisions), index["pool_asof"]))
    return 0


def _fr_card(num, c, xml_name, raw, pool_asof, source_url=""):
    return "\n".join([
        "# 法国法条证据卡（派生件；官方 XML 原字节的哈希钉在这里）",
        "NUM: %s" % num,
        "CODE_ID: %s" % c["code_id"],
        "CODE_TITLE: %s" % c["code_title"],
        "LEGIARTI: %s" % c["legiarti"],
        "ETAT: %s" % c["etat"],
        "DATE_DEBUT: %s" % c["date_debut"],
        "DATE_FIN: %s" % c["date_fin"],
        "POOL_ASOF: %s" % pool_asof,
        "OFFICIAL_XML: %s" % xml_name,
        "OFFICIAL_XML_BYTES: %d" % len(raw),
        "TEXT_CHARS: %d" % len(c["text"]),
        "OFFICIAL_XML_SHA256: %s" % sha256_bytes(raw),
        "SOURCE: %s" % (source_url or
                        "DILA LEGI 开放数据增量包 echanges.dila.gouv.fr/OPENDATA/LEGI/"),
    ]) + "\n"


# ---------------------------------------------------------------------------
# CN —— 国家法律法规数据库（flk.npc.gov.cn law-search/search/*）
# ---------------------------------------------------------------------------
def _cn_clean_title(t):
    return re.sub(r"</?em[^>]*>", "", t or "").strip()


def cn_search(http, query, page=1, size=20):
    """POST /law-search/search/list —— 请求体形抄自官网前端（2026-11-16 实测）。"""
    payload = {
        "searchContent": query, "searchType": 2, "searchRange": 2,
        "flfgCodeId": [], "zdjgCodeId": [], "sxx": [], "gbrqYear": [],
        "gbrq": [], "sxrq": [],
        "orderByParam": {"order": "-1", "sort": ""},
        "pageNum": page, "pageSize": size,
    }
    resp = http.post_json(CN_SEARCH_URL, payload,
                          headers={"Origin": "https://flk.npc.gov.cn",
                                   "Referer": "https://flk.npc.gov.cn/search"})
    if resp.get("code") != 200:
        raise FetchError("FLK 搜索失败：code=%s msg=%s" % (resp.get("code"),
                                                          resp.get("msg")))
    return resp


def cn_detail(http, bbbs):
    url = CN_DETAIL_URL + "?bbbs=" + urllib.request.quote(bbbs)
    r = http.request(url, headers={"Accept": "application/json, text/plain, */*",
                                   "Origin": "https://flk.npc.gov.cn",
                                   "Referer": "https://flk.npc.gov.cn/detail"})
    return url, r["body"]


def cn_walk_articles(node, out):
    """详情 JSON 的 content 树 → 全部「第X条」节点标题（保序去重）。"""
    if not isinstance(node, dict):
        return
    title = (node.get("title") or "").strip()
    if ART_CN_RE.match(title) and title not in out:
        out.append(title)
    for child in node.get("children") or []:
        cn_walk_articles(child, out)


def fetch_cn(http, corpus_root, state, max_items, mode, reference_date, yes):
    cn_dir = os.path.join(corpus_root, "cn")
    cards_dir = os.path.join(cn_dir, "cards")
    os.makedirs(cards_dir, exist_ok=True)

    if mode == "bulk":
        first = cn_search(http, "", page=1, size=20)
        total = int(first.get("total") or 0)
        pages = (total + 19) // 20
        log("[plan]  CN bulk：全库约 %d 部法规" % total)
        log("[plan]   预计请求：列表翻页 %d 次 + 详情 %d 次 = %d 次"
            % (pages, total, pages + total))
        if not yes:
            if sys.stdin.isatty():
                if input("确认开跑？[y/N] ").strip().lower() not in ("y", "yes"):
                    log("[abort] 未确认，停止（--yes 可跳过询问）")
                    return 3
            else:
                log("[abort] bulk 需显式 --yes 才动（当前非交互终端）")
                return 2
        out_name = "catalog_full.jsonl.gz"
        records = []
        for page in range(1, pages + 1):
            rows = (first if page == 1 else cn_search(http, "", page=page)).get("rows") or []
            for row in rows:
                bbbs = row.get("bbbs") or ""
                if not bbbs:
                    continue
                rec = _cn_fetch_one(http, state, bbbs, cards_dir, row_hint=row)
                if rec:
                    records.append(rec)
        write_gzip_jsonl(os.path.join(cn_dir, out_name), records)
        state.note("cn", "catalog_full", out_name)
        state.note("cn", "last_run", now_iso())
        log("[done]  CN bulk：catalog %s 共 %d 条" % (out_name, len(records)))
        return 0

    # ---- sample：固定查询序取现行有效法规 ----
    records = []
    got = 0
    for query in CN_SAMPLE_QUERIES:
        if got >= max_items:
            break
        resp = cn_search(http, query, page=1, size=10)
        rows = resp.get("rows") or []
        # 选代表：标题与查询**完全同名**的现行版优先（verify-cn 本就按标题精确索引）；
        # 同名多版本再按 sxx 3(有效) 优先、公布日新者优先（与 cn_corpus._prefer 同口径）。
        def _key(r):
            clean = _cn_clean_title(r.get("title"))
            return (clean == query, r.get("sxx") == 3,
                    r.get("gbrq") or "0000-00-00")
        rows = sorted(rows, key=_key, reverse=True)
        if not rows:
            log("[warn]  CN 查询无结果：%s" % query)
            continue
        top = rows[0]
        bbbs = top["bbbs"]
        if state.fetched("cn", bbbs):
            log("[skip]  cn:%s 已取过（state 命中），直接复用" % bbbs)
            rec = _cn_record_from_state(state, bbbs, cards_dir)
        else:
            rec = _cn_fetch_one(http, state, bbbs, cards_dir, row_hint=top)
        if not rec:
            continue
        if any(r["bbbs"] == bbbs for r in records):
            continue
        records.append(rec)
        got += 1
        log("[ok]    cn:%s《%s》sxx=%s gbrq=%s sxrq=%s 条数=%d"
            % (bbbs[:13] + "…", rec["title"], rec["sxx"], rec["gbrq"],
               rec["sxrq"], rec["n_articles"]))
    if not records:
        raise FetchError("CN sample 没抓到任何法规")
    write_gzip_jsonl(os.path.join(cn_dir, "catalog.jsonl.gz"), records)
    state.note("cn", "catalog", "catalog.jsonl.gz")
    state.note("cn", "last_run", now_iso())
    log("[done]  CN：catalog.jsonl.gz 共 %d 条（sample）" % len(records))
    return 0


def _cn_fetch_one(http, state, bbbs, cards_dir, row_hint=None):
    url, raw = cn_detail(http, bbbs)
    resp = json.loads(raw.decode("utf-8"))
    if resp.get("code") != 200:
        raise FetchError("FLK 详情失败 bbbs=%s：code=%s msg=%s"
                         % (bbbs, resp.get("code"), resp.get("msg")))
    data = resp.get("data") or {}
    title = (data.get("title") or
             _cn_clean_title((row_hint or {}).get("title")) or "").strip()
    arts = []
    cn_walk_articles(data.get("content") or {}, arts)
    detail_sha = sha256_bytes(raw)
    rec = {
        "bbbs": bbbs, "title": title,
        "sxx": data.get("sxx"), "gbrq": data.get("gbrq") or "",
        "sxrq": data.get("sxrq") or "", "office": data.get("zdjgName") or "",
        "flxz": data.get("flxz") or "",
        "n_articles": len(arts), "articles": arts,
        "detail_url": url, "detail_sha256": detail_sha,
        "detail_bytes": len(raw), "fetched_at": now_iso(),
    }
    slug = "%s_%s" % (title, bbbs[:6])
    slug = re.sub(r"[\\/:*?\"<>|\s]", "_", slug)
    with open(os.path.join(cards_dir, slug + ".cn.card.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join([
            "# 中国法规证据卡（派生件；官方详情 JSON 原字节哈希钉在这里）",
            "TITLE: %s" % title,
            "BBBS: %s" % bbbs,
            "OFFICIAL_DETAIL_SHA256: %s" % detail_sha,
            "SXX: %s" % data.get("sxx"),
            "GBRQ: %s" % (data.get("gbrq") or ""),
            "SXRQ: %s" % (data.get("sxrq") or ""),
            "FLXZ: %s" % (data.get("flxz") or ""),
            "ZDJG: %s" % (data.get("zdjgName") or ""),
            "DETAIL_BYTES: %d" % len(raw),
            "SOURCE_URL: %s" % url,
        ]) + "\n")
    with open(os.path.join(cards_dir, slug + ".cn.detail.json"), "wb") as fh:
        fh.write(raw)
    state.mark("cn", bbbs, url=url, sha256=detail_sha, bytes_=len(raw),
               title=title, sxx=data.get("sxx"), gbrq=rec["gbrq"],
               sxrq=rec["sxrq"], n_articles=len(arts), card_file=slug + ".cn.card.txt")
    return rec


def _cn_record_from_state(state, bbbs, cards_dir):
    prev = state.fetched("cn", bbbs)
    card_file = prev.get("card_file") or ""
    detail_path = os.path.join(cards_dir, card_file.replace(".cn.card.txt",
                                                            ".cn.detail.json"))
    arts = []
    if os.path.exists(detail_path):
        with open(detail_path, "rb") as fh:
            data = (json.loads(fh.read().decode("utf-8")).get("data") or {})
        cn_walk_articles(data.get("content") or {}, arts)
    return {"bbbs": bbbs, "title": prev.get("title") or "",
            "sxx": prev.get("sxx"), "gbrq": prev.get("gbrq") or "",
            "sxrq": prev.get("sxrq") or "", "office": "",
            "flxz": "", "n_articles": len(arts), "articles": arts,
            "detail_url": prev.get("url") or "",
            "detail_sha256": prev.get("sha256") or "",
            "detail_bytes": prev.get("bytes"), "fetched_at": prev.get("fetched_at")}


# ---------------------------------------------------------------------------
# IT —— Normattiva OpenData（检索走正式 API，AKN 走 caricaAKN）
# ---------------------------------------------------------------------------
def _it_headers():
    return {"Origin": "https://dati.normattiva.it",
            "Referer": "https://dati.normattiva.it/",
            "Accept": "application/json, text/plain, */*"}


def it_search_act(http, anno, numero):
    """ricerca/avanzata 按(年,号)精确定位；返回 (codiceRedazionale, dataGU, 标题)。"""
    payload = {"annoProvvedimento": anno, "numeroProvvedimento": numero,
               "orderType": "recente",
               "paginazione": {"paginaCorrente": 1, "numeroElementiPerPagina": 10}}
    resp = http.post_json(IT_API_BASE + IT_ADV_SEARCH_PATH, payload,
                          headers=_it_headers())
    rows = resp.get("listaAtti") or []
    for row in rows:
        blob = " ".join(str(row.get(k) or "") for k in
                        ("denominazioneAtto", "descrizioneAtto", "titoloAtto"))
        if numero in blob and anno in blob:
            return row.get("codiceRedazionale") or "", row.get("dataGU") or "", \
                row.get("denominazioneAtto") or blob[:80]
    if rows:
        row = rows[0]
        return row.get("codiceRedazionale") or "", row.get("dataGU") or "", \
            row.get("denominazioneAtto") or "atto"
    raise FetchError("IT 检索落空：%s/%s（ricerca/avanzata 无结果）" % (anno, numero))


def it_fetch_akn(http, codice_redaz, data_gu, data_vigenza):
    """取整件 AKN XML。dataGU 传 YYYY-MM-DD，data_vigenza 传 YYYYMMDD 紧凑形。

    官方网站的正确打开姿势（2026-11-16 实测；与官方 OpenData 消费者一致）：
    ① 先 GET ELI CONSOLIDATED 页建立 servlet 会话（JSESSIONID + NCC 亲和；
       Set-Cookie 由 CookieJar 接住）；② 从页面里解析出**唯一一条**
       caricaAKN 链接（其 dataGU/codiceRedaz/dataVigenza 必须与本次取件参数
       一致，防串件）；③ 带同一会话 GET 该链接拿 AKN XML。
    ⚠️ www 站拒绝 OpenData 门户的 Origin 头（HTTP 409），全程不带 Origin。
    """
    eli_url = ("https://www.normattiva.it/eli/id/%s/%s/%s/%s/CONSOLIDATED/%s"
               % (data_gu[0:4], data_gu[5:7], data_gu[8:10],
                  urllib.request.quote(codice_redaz, safe=""), data_vigenza))
    jar = http_cookiejar.CookieJar()
    web_headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                   "Accept-Language": "it-IT,it;q=0.9,en;q=0.7"}
    r = http.request(eli_url, headers=web_headers, jar=jar)
    if not r.get("final_url", eli_url).startswith("https://www.normattiva.it/"):
        raise FetchError("ELI 页跳出了官方域：%s -> %s" % (eli_url, r["final_url"]))
    html = r["body"].decode("utf-8", "replace")
    from html import unescape
    from urllib.parse import parse_qs
    links = [unescape(x) for x in
             re.findall(r'href="(/do/atto/caricaAKN\?[^"]+)"', html)]
    wanted = None
    for link in set(links):
        q = parse_qs(link.split("?", 1)[1] if "?" in link else "")
        if (q.get("dataGU", [""])[0] == data_gu.replace("-", "")
                and q.get("codiceRedaz", [""])[0] == codice_redaz
                and q.get("dataVigenza", [""])[0] == data_vigenza):
            wanted = link
            break
    if not wanted:
        raise FetchError("ELI 页里没有参数一致的 caricaAKN 链接（dataGU=%s "
                         "codiceRedaz=%s dataVigenza=%s）；页面里共 %d 条 "
                         "caricaAKN 链接" % (data_gu, codice_redaz, data_vigenza,
                                             len(set(links))))
    akn_url = "https://www.normattiva.it" + wanted
    r2 = http.request(akn_url, jar=jar,
                      headers={"Accept": "application/xml, text/xml, */*",
                               "Accept-Language": "it-IT,it;q=0.9",
                               "Referer": eli_url})
    body = r2["body"]
    if b"<akomaNtoso" not in body[:4000]:
        raise FetchError("caricaAKN 返回的不是 AKN/XML：%s :: %s"
                         % (akn_url, body[:200].decode("utf-8", "replace")))
    return akn_url, body


def _it_meta_from_akn(raw):
    """从 AKN 头部提取 urn:nir / eli / 版本日 / 标题。"""
    head = raw[:6000].decode("utf-8", "replace")
    urn = eli = ""
    m = re.search(r'<FRBRalias\s+name="urn:nir"\s+value="([^"]+)"', head) or \
        re.search(r'value="urn:nir:[^"]+"[^>]*name="urn:nir"', head)
    if m:
        urn = m.group(1)
    m = re.search(r'<FRBRalias\s+name="eli"\s+value="([^"]+)"', head)
    if m:
        eli = m.group(1)
    version_date = ""
    m = re.search(r"/CONSOLIDATED/(\d{8})", eli)
    if m:
        d = m.group(1)
        version_date = "%s-%s-%s" % (d[:4], d[4:6], d[6:8])
    else:
        m = re.search(r"ita@(\d{4}-\d{2}-\d{2})", head)
        if m:
            version_date = m.group(1)
    m = re.search(r"<docTitle>.*?<p[^>]*>(.*?)</p>", head, re.S)
    title = re.sub(r"<[^>]+>", " ", m.group(1)).strip() if m else ""
    title = re.sub(r"\s+", " ", title)
    return urn, eli, version_date, title


def fetch_it(http, corpus_root, state, max_items, mode, reference_date, yes):
    ref_compact = reference_date.replace("-", "")

    acts = IT_SAMPLE_ACTS
    if mode == "bulk":
        log("[plan]  IT bulk：默认样单 %d 部法律整件（可改 IT_SAMPLE_ACTS 扩单）" % len(acts))
        log("[plan]   预计请求：每部 3 次（检索 1 + ELI 页 1 + caricaAKN 1）= %d 次"
            % (len(acts) * 3))
        if not yes:
            if sys.stdin.isatty():
                if input("确认开跑？[y/N] ").strip().lower() not in ("y", "yes"):
                    log("[abort] 未确认，停止（--yes 可跳过询问）")
                    return 3
            else:
                log("[abort] bulk 需显式 --yes 才动（当前非交互终端）")
                return 2

    # 每部法独立 run 目录（verify-it 的 --corpus 一目录一法）
    for anno, numero in acts:
        run_id = "run-%s-it-%sn%s" % (ref_compact, anno, numero)
        run_dir = os.path.join(corpus_root, "it", run_id)
        off_dir = os.path.join(run_dir, "official")
        os.makedirs(off_dir, exist_ok=True)
        idx_path = os.path.join(run_dir, "index.json")

        item_id = "act:%s/%s@%s" % (anno, numero, ref_compact)
        if state.fetched("it", item_id) and os.path.exists(idx_path) and \
                os.path.exists(os.path.join(off_dir, "act.akn.xml")):
            log("[skip]  it:%s 已取过（state 命中）：%s" % (item_id, run_id))
            continue
        log("[pick]  IT act: anno=%s numero=%s vigenza=%s" % (anno, numero, ref_compact))
        codice_redaz, data_gu, titolo = it_search_act(http, anno, numero)
        if not codice_redaz or not data_gu:
            raise FetchError("IT 检索结果缺 codiceRedazionale/dataGU：%s/%s"
                             % (anno, numero))
        log("[ok]    IT 检索命中：codiceRedaz=%s dataGU=%s《%s》"
            % (codice_redaz, data_gu, titolo[:60]))
        akn_url, raw = it_fetch_akn(http, codice_redaz, data_gu, ref_compact)
        urn, eli, version_date, doc_title = _it_meta_from_akn(raw)
        act_path = os.path.join(off_dir, "act.akn.xml")
        with open(act_path, "wb") as fh:
            fh.write(raw)
        state.mark("it", item_id, url=akn_url, sha256=sha256_bytes(raw),
                   bytes_=len(raw), codice_redazionale=codice_redaz,
                   data_gu=data_gu, act_urn=urn, act_title=titolo, run=run_id)
        # 条文切片 + 卡（sample：编号序取前 max_items 条可用的；排除超长附件表）
        eids = sorted({m.group(1).decode() for m in
                       IT_ARTICLE_EID_RE.finditer(raw)},
                      key=lambda e: int(e.split("_")[1]))
        articles = {}
        n_picked = 0
        for eid in eids:
            if mode == "sample" and n_picked >= max_items:
                break
            m = re.search(rb'<article eId="' + eid.encode() + rb'">(.*?)</article>',
                          raw, re.S)
            if not m:
                continue
            blob = m.group(0)
            text = re.sub(r"<[^>]+>", " ", blob.decode("utf-8", "replace"))
            text = re.sub(r"\s+", " ", text).strip()
            if mode == "sample" and len(text) > 20000:
                log("[skip]  it:%s 正文 %d chars 超长（附件表类），sample 跳过"
                    % (eid, len(text)))
                continue
            with open(os.path.join(off_dir, "%s.xml" % eid), "wb") as fh:
                fh.write(blob)
            card = "\n".join([
                "# 意大利法条证据卡（派生件；官方 AKN 整件与条文切片哈希钉在这里）",
                "ACT_URN: %s" % urn,
                "ACT_ELI: %s" % eli,
                "ARTICLE_EID: %s" % eid,
                "ARTICLE_NUM: %s" % eid.split("_")[1],
                "CODICE_REDAZIONALE: %s" % codice_redaz,
                "VERSION_DATE: %s" % version_date,
                "FETCH_VIGENZA: %s" % ref_compact,
                "REFERENCE_DATE: %s" % reference_date,
                "SOURCE_FILE: official/act.akn.xml",
                "OFFICIAL_XML_SHA256: %s" % sha256_bytes(raw),
                "ARTICLE_SHA256: %s" % sha256_bytes(blob),
                "TEXT_CHARS: %d" % len(text),
                "LICENCE: CC BY 4.0 (Normattiva OpenData)",
                "ATTRIBUTION: Fonte: Normattiva, Istituto Poligrafico e Zecca dello Stato",
                "--- OFFICIAL TEXT ---",
                text[:600] + ("…" if len(text) > 600 else ""),
                "",
            ])
            card_path = os.path.join(run_dir, "%s.it.card.txt" % eid)
            with open(card_path, "w", encoding="utf-8") as fh:
                fh.write(card)
            articles[eid] = {
                "eid": eid, "num": eid.split("_")[1],
                "article_file": "official/%s.xml" % eid,
                "article_sha256": sha256_bytes(blob),
                "article_bytes": len(blob),
                "text_sha256": sha256_bytes(text.encode("utf-8")),
                "text_chars": len(text),
                "card_file": "%s.it.card.txt" % eid,
                "card_sha256": sha256_file(card_path),
            }
            state.mark("it", "%s:%s" % (item_id, eid), url=akn_url + "#" + eid,
                       sha256=sha256_bytes(blob), bytes_=len(blob),
                       run=run_id, article_file="official/%s.xml" % eid)
            n_picked += 1
            log("[ok]    it:%s 切片+卡（%d chars）" % (eid, len(text)))
        index = {
            "act_key": "%s/%s" % (anno, numero),
            "act_urn": urn or ("urn:nir:stato:legge:%s-%s-%s;%s"
                               % (data_gu[0:4], data_gu[4:6], data_gu[6:8], numero)),
            "act_eli": eli,
            "act_title": doc_title or titolo,
            "source_file": "official/act.akn.xml",
            "source_sha256": sha256_bytes(raw),
            "source_bytes": len(raw),
            "codice_redazionale": codice_redaz,
            "data_gu": data_gu,
            "version_date": version_date,
            "fetch_vigenza": ref_compact,
            "fetch_reference_date": reference_date,
            "reference_date": reference_date,
            "articles": articles,
        }
        with open(idx_path, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        log("[done]  IT：%s 条文卡 %d 张，整件 %d bytes"
            % (run_id, len(articles), len(raw)))
    state.note("it", "last_run", now_iso())
    state.note("it", "runs", sorted(
        d for d in os.listdir(os.path.join(corpus_root, "it"))
        if d.startswith("run-")))
    return 0


# ---------------------------------------------------------------------------
# ES —— BOE 开放数据（legislacion-consolidada by-id：合并文本 XML 整件）
# ---------------------------------------------------------------------------
# 官方通道实测（2026-11-16）：
#   GET https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{BOE-A-…}
#   → Accept: application/xml 时返回整件合并文本 XML（<metadatos> + <texto>）。
#   ⚠️ 不带 Accept（或带 application/json）会被官方拒（400「No soportado ningún
#   mime type de la cabecera Accept」）；带 application/xml 即通。
#   ⚠️ 任务书里写的 api.boe.es 域名不存在（DNS NXDOMAIN），真域名是 www.boe.es。
# 整件里每个 <bloque id="a7" tipo="precepto" titulo="Artículo 7"> 是一个条文块；
# 切片取整件字节的**原样子串**（m.start():m.end()），保证与官方件脱钩可查。
ES_LICENCE = ("Condiciones de reutilización de la AEBOE (Resolución de la "
              "Agencia de 27 de junio de 2024)")
ES_ATTRIBUTION = ("Fuente de los datos: Agencia Estatal Boletín Oficial del "
                  "Estado (https://www.boe.es/)")


def _es_plain(xml_text):
    """XML 片段 → 纯文本（去标签、解实体、压空白）。"""
    s = re.sub(r"<[^>]+>", " ", xml_text)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&#13;", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _es_attr(attrs, name):
    m = re.search((r'%s="([^"]*)"' % name).encode(), attrs)
    return m.group(1).decode("utf-8", "replace") if m else ""


def _es_meta(raw):
    """从 <metadatos> 里取法件元数据（字段缺了也不炸，空串照填）。"""
    m = ES_META_RE.search(raw)
    blob = m.group(1) if m else b""

    def _g(tag):
        mm = re.search((r"<%s[^>]*>(.*?)</%s>" % (tag, tag)).encode(),
                       blob, re.S)
        if not mm:
            return ""
        return _es_plain(mm.group(1).decode("utf-8", "replace"))

    return {
        "identificador": _g("identificador"),
        "titulo": _g("titulo"),
        "fecha_actualizacion": _g("fecha_actualizacion"),
        "fecha_disposicion": _g("fecha_disposicion"),
        "fecha_publicacion": _g("fecha_publicacion"),
        "fecha_vigencia": _g("fecha_vigencia"),
        "numero_oficial": _g("numero_oficial"),
        "rango": _g("rango"),
        "estado_consolidacion": _g("estado_consolidacion"),
        "url_eli": _g("url_eli"),
        "url_html_consolidada": _g("url_html_consolidada"),
    }


def _es_date(compact):
    """20261116T084356Z → 2026-11-16（空串照回空串）。"""
    d = (compact or "")[:8]
    if len(d) != 8 or not d.isdigit():
        return ""
    return "%s-%s-%s" % (d[0:4], d[4:6], d[6:8])


def es_fetch_act(http, act_id):
    """取 BOE 合并文本整件（by-id）。一次请求拿整件（metadatos + 全部 bloque）。"""
    url = "%s/id/%s" % (ES_API_BASE, urllib.request.quote(act_id, safe=""))
    r = http.request(url, headers={"Accept": "application/xml",
                                   "Accept-Language": "es-ES,es;q=0.9"})
    body = r["body"]
    if b"<metadatos>" not in body[:20000]:
        raise FetchError("BOE by-id 返回的不是合并文本 XML：%s :: %s"
                         % (url, body[:200].decode("utf-8", "replace")))
    return url, body


def fetch_es(http, corpus_root, state, max_items, mode, reference_date, yes):
    es_root = os.path.join(corpus_root, "es")
    os.makedirs(es_root, exist_ok=True)
    acts = ES_SAMPLE_ACTS
    if mode == "bulk":
        log("[plan]  ES bulk：样单 %d 部西班牙法律整件（可改 ES_SAMPLE_ACTS 扩单）"
            % len(acts))
        log("[plan]   预计请求：每部 1 次（by-id 合并文本 XML）= %d 次" % len(acts))
        if not yes:
            if sys.stdin.isatty():
                if input("确认开跑？[y/N] ").strip().lower() not in ("y", "yes"):
                    log("[abort] 未确认，停止（--yes 可跳过询问）")
                    return 3
            else:
                log("[abort] bulk 需显式 --yes 才动（当前非交互终端）")
                return 2

    for act_id, slug in acts:
        run_id = "run-%s-es-%s" % (reference_date.replace("-", ""), slug)
        run_dir = os.path.join(es_root, run_id)
        off_dir = os.path.join(run_dir, "official")
        os.makedirs(off_dir, exist_ok=True)
        idx_path = os.path.join(run_dir, "index.json")

        item_id = "act:%s@%s" % (act_id, reference_date)
        if state.fetched("es", item_id) and os.path.exists(idx_path) and \
                os.path.exists(os.path.join(off_dir, "act.xml")):
            log("[skip]  es:%s 已取过（state 命中）：%s" % (item_id, run_id))
            continue
        log("[pick]  ES act: %s" % act_id)
        url, raw = es_fetch_act(http, act_id)
        meta = _es_meta(raw)
        version_date = _es_date(meta.get("fecha_actualizacion"))
        act_path = os.path.join(off_dir, "act.xml")
        with open(act_path, "wb") as fh:
            fh.write(raw)
        state.mark("es", item_id, url=url, sha256=sha256_bytes(raw),
                   bytes_=len(raw), act_id=act_id,
                   act_title=meta.get("titulo"), run=run_id,
                   version_date=version_date)

        # 条文切片 + 卡（sample：取编号条文 a<N>，按条号序；排除超长附件表）
        articles = {}
        picked = 0
        for m in ES_BLOQUE_RE.finditer(raw):
            bid = m.group(1).decode("utf-8")
            attrs = m.group(2)
            tipo = _es_attr(attrs, "tipo")
            title = _es_attr(attrs, "titulo")
            am = ES_ART_ID_RE.match(bid)
            if tipo != "precepto" or not am:
                continue   # 只收编号条文（a1、a2…）；标题块/附则/单条另计
            if mode == "sample" and picked >= max_items:
                break
            blob = raw[m.start():m.end()]     # 原样切片（与整件字节一致）
            text = _es_plain(blob.decode("utf-8", "replace"))
            if mode == "sample" and len(text) > 20000:
                log("[skip]  es:%s 正文 %d chars 超长（附件表类），sample 跳过"
                    % (bid, len(text)))
                continue
            with open(os.path.join(off_dir, "%s.xml" % bid), "wb") as fh:
                fh.write(blob)
            card = "\n".join([
                "# 西班牙法条证据卡（派生件；官方 BOE 合并文本整件与条文切片哈希钉在这里）",
                "ACT_ID: %s" % (meta.get("identificador") or act_id),
                "ACT_ELI: %s" % meta.get("url_eli"),
                "ACT_TITLE: %s" % meta.get("titulo"),
                "ACT_NUMBER: %s" % meta.get("numero_oficial"),
                "BLOCK_ID: %s" % bid,
                "ARTICLE_NUM: %s" % am.group(1),
                "ARTICLE_TITLE: %s" % title,
                "VERSION_DATE: %s" % version_date,
                "FETCH_DATE: %s" % reference_date,
                "REFERENCE_DATE: %s" % reference_date,
                "SOURCE_FILE: official/act.xml",
                "SOURCE_URL: %s" % url,
                "OFFICIAL_XML_SHA256: %s" % sha256_bytes(raw),
                "ARTICLE_SHA256: %s" % sha256_bytes(blob),
                "TEXT_CHARS: %d" % len(text),
                "TEXT_STATUS: texto consolidado de carácter meramente informativo",
                "LICENCE: %s" % ES_LICENCE,
                "ATTRIBUTION: %s" % ES_ATTRIBUTION,
                "FETCHED_AT: %s" % now_iso(),
                "--- OFFICIAL TEXT ---",
                text[:600] + ("…" if len(text) > 600 else ""),
                "",
            ])
            card_path = os.path.join(run_dir, "%s.es.card.txt" % bid)
            with open(card_path, "w", encoding="utf-8") as fh:
                fh.write(card)
            articles[bid] = {
                "block_id": bid,
                "num": am.group(1),
                "title": title,
                "article_file": "official/%s.xml" % bid,
                "article_sha256": sha256_bytes(blob),
                "article_bytes": len(blob),
                "text_sha256": sha256_bytes(text.encode("utf-8")),
                "text_chars": len(text),
                "card_file": "%s.es.card.txt" % bid,
                "card_sha256": sha256_file(card_path),
            }
            state.mark("es", "%s:%s" % (item_id, bid), url=url + "#" + bid,
                       sha256=sha256_bytes(blob), bytes_=len(blob),
                       run=run_id, article_file="official/%s.xml" % bid)
            picked += 1
            log("[ok]    es:%s %s（%d chars）" % (bid, title or "artículo", len(text)))
        if not articles:
            raise FetchError("ES 抓到的整件里没有编号条文（%s）" % act_id)
        index = {
            "act_id": meta.get("identificador") or act_id,
            "act_eli": meta.get("url_eli"),
            "act_title": meta.get("titulo"),
            "act_number": meta.get("numero_oficial"),
            "act_range": meta.get("rango"),
            "estado_consolidacion": meta.get("estado_consolidacion"),
            "fecha_disposicion": meta.get("fecha_disposicion"),
            "fecha_publicacion": meta.get("fecha_publicacion"),
            "fecha_vigencia": meta.get("fecha_vigencia"),
            "url_html_consolidada": meta.get("url_html_consolidada"),
            "source_url": url,
            "source_file": "official/act.xml",
            "source_sha256": sha256_bytes(raw),
            "source_bytes": len(raw),
            "version_date": version_date,
            "fetch_reference_date": reference_date,
            "reference_date": reference_date,
            "articles": articles,
        }
        with open(idx_path, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        log("[done]  ES：%s 条文卡 %d 张，整件 %d bytes"
            % (run_id, len(articles), len(raw)))
    state.note("es", "last_run", now_iso())
    state.note("es", "runs", sorted(
        d for d in os.listdir(es_root) if d.startswith("run-")))
    return 0


# ---------------------------------------------------------------------------
# CASE —— 人民法院案例库：匿名通道不可用，如实报备（不硬闯）
# ---------------------------------------------------------------------------
def fetch_case_probe(http, corpus_root, state, max_items, mode, reference_date, yes):
    case_dir = os.path.join(corpus_root, "case")
    os.makedirs(case_dir, exist_ok=True)
    prev = state.fetched("case", "reachability")
    if prev:
        log("[skip]  case: 可达性已探过（state 命中）：%s" % prev.get("verdict"))
    else:
        r = http.request(CASE_HOME_URL, headers={"Accept": "text/html"})
        html = r["body"].decode("utf-8", "replace")
        verdict = ("reachable" if "人民法院案例库" in html else "unexpected-content")
        state.mark("case", "reachability", url=CASE_HOME_URL,
                   sha256=sha256_bytes(r["body"]), bytes_=len(r["body"]),
                   verdict=verdict)
    verdict = (state.fetched("case", "reachability") or {}).get("verdict", "?")
    log("[gate]  案例源（人民法院案例库）检索接口 /cpws_al_api/api/cpwsAl/search "
        "要求登录（前端明示「您还未登录，请先登录」）。")
    log("[gate]  按礼貌与合规纪律：匿名通道不硬闯、不代抓登录后内容。")
    log("[gate]  站点可达性：%s。要真取入库案例正文，请注册个人账号后，"
        "在浏览器里人工检索需要的案例并导出正文，放到 corpus/case/official/<slug>.txt，"
        "再重跑 materialize（脚本会补卡与回执链）。" % verdict)
    state.note("case", "last_run", now_iso())
    return 0


# ---------------------------------------------------------------------------
# materialize —— 把语料物化成合成小项目（四闸直接吃）
# ---------------------------------------------------------------------------
def _pick_number(text, minimum=10):
    """从正文里挑一个确定性的「确实存在」的数值（引用示例用）。"""
    nums = [int(n) for n in re.findall(r"(?<![\d.,])(\d{2,})(?![\d.,])", text)]
    nums = sorted({n for n in nums if n >= minimum})
    if nums:
        mid = nums[len(nums) // 2]
        return str(mid)
    nums = [int(n) for n in re.findall(r"(?<![\d.,])(\d)(?![\d.,])", text)]
    return str(sorted(nums)[0]) if nums else None


def materialize(corpus_root, project_dir):
    os.makedirs(os.path.join(project_dir, "facts"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "cards"), exist_ok=True)
    facts_fr, facts_cn, facts_it, facts_es = [], [], [], []
    tex_lines = ["% 合成小项目：由 tools/fetch_corpus.py materialize 生成",
                 "% 事实账引用的是真官方件的钉哈希证据卡（两层证据模型）", ""]

    def rel(path):
        return os.path.relpath(path, project_dir).replace(os.sep, "/")

    # ---- FR ----
    fr_dir = os.path.join(corpus_root, "fr")
    idx_path = os.path.join(fr_dir, "index.json")
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as fh:
            index = json.load(fh)
        pool_asof = index.get("pool_asof") or ""
        for num in sorted(index.get("provisions", {})):
            meta = index["provisions"][num]
            xml_path = os.path.join(fr_dir, meta.get("xml_file") or (num + ".xml"))
            if not os.path.exists(xml_path):
                continue
            with open(xml_path, "rb") as fh:
                raw = fh.read()
            try:
                bloc = ET.fromstring(raw).find("BLOC_TEXTUEL")
            except ET.ParseError:
                continue
            text = " ".join(t.strip() for t in bloc.itertext() if t.strip()) \
                if bloc is not None else ""
            card_src = os.path.join(fr_dir, "%s.card.txt" % num)
            if not os.path.exists(card_src):
                log("[warn]  fr:%s 没有证据卡，跳过（先重跑 fetch --source fr）" % num)
                continue
            card_dst = os.path.join(project_dir, "cards", "%s.card.txt" % num)
            shutil.copyfile(card_src, card_dst)
            val = _pick_number(text)
            if val is None:
                continue
            fid = "FR-" + re.sub(r"[^A-Za-z0-9]", "-", num)
            facts_fr.append([
                "[[fact]]",
                'id = "%s"' % fid,
                'claim = "%s 第 %s 条正文数值（官方件引用示例）"'
                % (meta.get("code_title") or "法国法条", num),
                'value = "%s"' % val,
                'source = "%s"' % rel(card_dst),
                'source_sha256 = "sha256:%s"' % sha256_file(card_dst),
                'locator = "%s (LEGIARTI %s, %s→%s)"'
                % (num, meta.get("legiarti"), meta.get("date_debut"),
                   meta.get("date_fin")),
                'confidence = "high"',
                "derived_from = []",
                'note = "官方 XML sha256 %s"' % sha256_bytes(raw),
                "",
            ])
            tex_lines.append(r"法国侧引用示例：\cite{art:%s}（值 %s）。"
                             % (num, val))
    if facts_fr:
        with open(os.path.join(project_dir, "facts", "10-fr-provisions.toml"),
                  "w", encoding="utf-8") as fh:
            fh.write('schema = "paperkit-fact/3.0"\n\n' + "\n".join("\n".join(b) for b in facts_fr))

    # ---- CN ----
    cat_path = os.path.join(corpus_root, "cn", "catalog.jsonl.gz")
    if os.path.exists(cat_path):
        with gzip.open(cat_path, "rt", encoding="utf-8") as fh:
            records = [json.loads(line) for line in fh]
        cards_dir = os.path.join(corpus_root, "cn", "cards")
        for rec in records:
            bbbs = rec["bbbs"]
            card_src = None
            if os.path.isdir(cards_dir):
                for name in sorted(os.listdir(cards_dir)):
                    if name.endswith("_%s.cn.card.txt" % bbbs[:6]):
                        card_src = os.path.join(cards_dir, name)
                        break
            if not card_src:
                log("[warn]  cn:%s 没有证据卡，跳过" % bbbs[:13])
                continue
            card_dst = os.path.join(project_dir, "cards",
                                    os.path.basename(card_src))
            shutil.copyfile(card_src, card_dst)
            base_id = "CN-" + bbbs[-6:].upper()
            cards = []
            if rec.get("gbrq"):
                cards.append(("-GBRQ", "公布日期", rec["gbrq"]))
            if rec.get("sxrq"):
                cards.append(("-SXRQ", "施行日期", rec["sxrq"]))
            if rec.get("n_articles"):
                cards.append(("-N", "条文条数", str(rec["n_articles"])))
            for suffix, what, val in cards:
                facts_cn.append([
                    "[[fact]]",
                    'id = "%s%s"' % (base_id, suffix),
                    'claim = "《%s》%s"' % (rec["title"], what),
                    'value = "%s"' % val,
                    'source = "%s"' % rel(card_dst),
                    'source_sha256 = "sha256:%s"' % sha256_file(card_dst),
                    'locator = "《%s》（FLK bbbs %s）"' % (rec["title"], bbbs),
                    'confidence = "high"',
                    "derived_from = []",
                    "",
                ])
            tex_lines.append(r"中国侧引用示例：\cite{art-%s}。" % rec["title"])
    if facts_cn:
        with open(os.path.join(project_dir, "facts", "20-cn-provisions.toml"),
                  "w", encoding="utf-8") as fh:
            fh.write('schema = "paperkit-fact/3.0"\n\n' + "\n".join("\n".join(b) for b in facts_cn))

    # ---- IT ----
    # verify-it 一目录一法；多法语料时取「条文卡最多」的那个 run 物化（确定性：
    # 同数取名字序），其余 run 留在语料里可单独 --corpus 验证。
    it_root = os.path.join(corpus_root, "it")
    if os.path.isdir(it_root):
        candidates = []
        for name in sorted(d for d in os.listdir(it_root) if d.startswith("run-")):
            idx = os.path.join(it_root, name, "index.json")
            if os.path.exists(idx):
                with open(idx, encoding="utf-8") as fh:
                    d = json.load(fh)
                candidates.append((-len(d.get("articles") or {}), name))
        if candidates:
            candidates.sort()
            run_name = candidates[0][1]
            run_dir = os.path.join(it_root, run_name)
            with open(os.path.join(run_dir, "index.json"), encoding="utf-8") as fh:
                index = json.load(fh)
            log("[pick]  IT run for facts: %s" % run_name)
            for eid in sorted(index.get("articles", {}),
                              key=lambda e: int(e.split("_")[1])):
                meta = index["articles"][eid]
                art_path = os.path.join(run_dir, meta.get("article_file"))
                if not os.path.exists(art_path):
                    continue
                card_src = os.path.join(run_dir, "%s.it.card.txt" % eid)
                if not os.path.exists(card_src):
                    continue
                with open(art_path, "rb") as fh:
                    raw = fh.read()
                text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace"))
                text = re.sub(r"\s+", " ", text).strip()
                card_dst = os.path.join(project_dir, "cards", "%s.it.card.txt" % eid)
                shutil.copyfile(card_src, card_dst)
                val = _pick_number(text)
                if val is None:
                    continue
                facts_it.append([
                    "[[fact]]",
                    'id = "IT-%s"' % eid.replace("art_", ""),
                    'claim = "%s 第 %s 条正文数值（官方件引用示例）"'
                    % (index.get("act_title") or "意大利法条", eid.split("_")[1]),
                    'value = "%s"' % val,
                    'source = "%s"' % rel(card_dst),
                    'source_sha256 = "sha256:%s"' % sha256_file(card_dst),
                    'locator = "%s (%s)"' % (eid, index.get("act_urn")),
                    'confidence = "high"',
                    "derived_from = []",
                    "",
                ])
                tex_lines.append(r"意大利侧引用示例：\cite{art-it-%s}（值 %s）。"
                                 % (eid, val))
    if facts_it:
        with open(os.path.join(project_dir, "facts", "30-it-provisions.toml"),
                  "w", encoding="utf-8") as fh:
            fh.write('schema = "paperkit-fact/3.0"\n\n' + "\n".join("\n".join(b) for b in facts_it))

    # ---- ES ----
    # verify-es 一目录一法；多法语料时取「条文卡最多」的那个 run 物化（确定性：
    # 同数取名字序），其余 run 留在语料里可单独 --corpus 验证。
    es_root = os.path.join(corpus_root, "es")
    if os.path.isdir(es_root):
        candidates = []
        for name in sorted(d for d in os.listdir(es_root) if d.startswith("run-")):
            idx = os.path.join(es_root, name, "index.json")
            if os.path.exists(idx):
                with open(idx, encoding="utf-8") as fh:
                    d = json.load(fh)
                candidates.append((-len(d.get("articles") or {}), name))
        if candidates:
            candidates.sort()
            run_name = candidates[0][1]
            run_dir = os.path.join(es_root, run_name)
            with open(os.path.join(run_dir, "index.json"), encoding="utf-8") as fh:
                index = json.load(fh)
            log("[pick]  ES run for facts: %s" % run_name)
            for bid in sorted(index.get("articles", {}),
                              key=lambda b: int(b[1:]) if b[1:].isdigit() else 0):
                meta = index["articles"][bid]
                art_path = os.path.join(run_dir, meta.get("article_file"))
                if not os.path.exists(art_path):
                    continue
                card_src = os.path.join(run_dir, "%s.es.card.txt" % bid)
                if not os.path.exists(card_src):
                    continue
                with open(art_path, "rb") as fh:
                    raw = fh.read()
                text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace"))
                text = re.sub(r"\s+", " ", text).strip()
                card_dst = os.path.join(project_dir, "cards", "%s.es.card.txt" % bid)
                shutil.copyfile(card_src, card_dst)
                val = _pick_number(text)
                if val is None:
                    continue
                facts_es.append([
                    "[[fact]]",
                    'id = "ES-%s"' % bid,
                    'claim = "%s 第 %s 条正文数值（官方件引用示例）"'
                    % (index.get("act_title") or "西班牙法条", meta.get("num")),
                    'value = "%s"' % val,
                    'source = "%s"' % rel(card_dst),
                    'source_sha256 = "sha256:%s"' % sha256_file(card_dst),
                    'locator = "%s (%s)"' % (bid, index.get("act_id")),
                    'confidence = "high"',
                    "derived_from = []",
                    "",
                ])
                tex_lines.append(r"西班牙侧引用示例：\cite{art-es-%s}（值 %s）。"
                                 % (bid, val))
    if facts_es:
        with open(os.path.join(project_dir, "facts", "40-es-provisions.toml"),
                  "w", encoding="utf-8") as fh:
            fh.write('schema = "paperkit-fact/3.0"\n\n' + "\n".join("\n".join(b) for b in facts_es))

    # ---- CASE（有真实官方正文才物化）----
    case_off = os.path.join(corpus_root, "case", "official")
    if os.path.isdir(case_off):
        for name in sorted(os.listdir(case_off)):
            if not name.endswith(".txt"):
                continue
            slug = name[:-4]
            run = "run-%s-case" % slug[:12]
            prj_run = os.path.join(project_dir, "runs", run)
            os.makedirs(os.path.join(prj_run, "official"), exist_ok=True)
            off_dst = os.path.join(prj_run, "official", "%s.txt" % slug)
            shutil.copyfile(os.path.join(case_off, name), off_dst)
            text = open(off_dst, encoding="utf-8").read()
            amounts = sorted(set(re.findall(r"(?<![\d.,])\d[\d,]{2,}(?:\.\d+)?(?![\d.,])",
                                            text)))[:5]
            dates = sorted(set(re.findall(r"\d{4}年\d{1,2}月\d{1,2}日", text)))[:3]
            case_no = ""
            m = re.search(r"[（(][\d]{4}[）)][^。；\n]{0,30}号", text)
            if m:
                case_no = m.group(0)
            judge_date = ""
            m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
            if m:
                judge_date = "%s.%02d.%02d" % (m.group(1), int(m.group(2)),
                                               int(m.group(3)))
            card = "\n".join([
                "# 中国案例证据卡（派生件；官方正文哈希钉在这里）",
                "SLUG: %s" % slug,
                "CASE_NO: %s" % case_no,
                "JUDGE_DATE: %s" % judge_date,
                "AMOUNTS: %s" % ",".join(amounts),
                "OFFICIAL_TEXT_SHA256: %s" % sha256_file(off_dst),
                "SOURCE: 人民法院案例库（入库案例正文）",
                "--- OFFICIAL TEXT ---",
                text.rstrip("\n"),
                "",
            ])
            card_path = os.path.join(prj_run, "%s.case.card.txt" % slug)
            with open(card_path, "w", encoding="utf-8") as fh:
                fh.write(card)
            facts_case = []
            fid = "CASE-" + re.sub(r"[^A-Za-z0-9]", "", slug)[:12].upper() + "-NO"
            facts_case.append([
                "[[fact]]",
                'id = "%s"' % fid,
                'claim = "案号"', 'value = "%s"' % case_no,
                'source = "runs/%s/%s.case.card.txt"' % (run, slug),
                'source_sha256 = "sha256:%s"' % sha256_file(card_path),
                'locator = "人民法院案例库 %s"' % slug,
                'confidence = "high"',
                "derived_from = []",
                "",
            ])
            with open(os.path.join(project_dir, "facts", "40-case.toml"),
                      "w", encoding="utf-8") as fh:
                fh.write('schema = "paperkit-fact/3.0"\n\n' + "\n".join("\n".join(b) for b in facts_case))
            with open(os.path.join(prj_run, "result.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"run_id": run, "tool": "fetch_corpus.py"}, fh)
            with open(os.path.join(prj_run, "record.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"run_id": run, "facts": [fid]}, fh)
            tex_lines.append(r"案例侧引用示例：%s。" % (case_no or slug))
            break  # 一件够测闸

    with open(os.path.join(project_dir, "paper.tex"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(tex_lines) + "\n")

    def _count(blocks):
        return sum(b.count("[[fact]]") for b in blocks)
    log("[done]  materialize：%s" % project_dir)
    log("        facts: FR %d + CN %d + IT %d + ES %d 条；paper.tex 引用 %d 行"
        % (_count(facts_fr), _count(facts_cn), _count(facts_it), _count(facts_es),
           len(tex_lines) - 3))
    log("        五闸验证命令：")
    log("          PYTHONPATH=<integrations/factscribe-legal> python3 -m factscribe_legal verify "
        "--project %s --corpus <corpus>/fr --date <参考日> --view <corpus>/fr/view_current.jsonl"
        % project_dir)
    log("          ... verify-cn   --project %s --catalog <corpus>/cn/catalog.jsonl.gz --date <参考日>"
        % project_dir)
    log("          ... verify-it   --project %s --corpus <corpus>/it/<run> --date <参考日>"
        % project_dir)
    log("          ... verify-es   --project %s --corpus <corpus>/es/<run> --date <参考日>"
        % project_dir)
    log("          ... verify-case --project %s" % project_dir)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="fetch_corpus.py",
        description="factscribe-legal 语料抓取器（礼貌机制默认写死）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="抓语料（默认 sample 小样例）")
    f.add_argument("--source", required=True,
                   choices=["fr", "cn", "it", "es", "case", "all"])
    f.add_argument("--mode", default="sample", choices=["sample", "bulk"])
    f.add_argument("--max-per-source", type=int, default=10,
                   help="sample 模式每源最多取几件（默认 10）")
    f.add_argument("--interval-min", type=float, default=DEFAULT_INTERVAL_MIN,
                   help="随机间隔下限（默认 2s；低于 2s 会被抬到 2s）")
    f.add_argument("--interval-max", type=float, default=DEFAULT_INTERVAL_MAX,
                   help="随机间隔上限（默认 6s）")
    f.add_argument("--reference-date", default=_date.today().isoformat(),
                   help="参考日 YYYY-MM-DD（IT dataVigenza 用；默认今天）")
    f.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT)
    f.add_argument("--bulk-yes", "--yes", dest="yes", action="store_true",
                   help="bulk 确认开关（sample 模式不需要）")
    f.set_defaults(yes=False)

    m = sub.add_parser("materialize", help="把语料物化成合成小项目")
    m.add_argument("--project", required=True)
    m.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT)

    mf = sub.add_parser("manifest", help="重算 manifest（清单+sha256+URL）")
    mf.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT)
    mf.add_argument("--reference-date", default=_date.today().isoformat())

    args = ap.parse_args(argv)
    if args.cmd == "materialize":
        return materialize(args.corpus_root, args.project)
    if args.cmd == "manifest":
        state = State(os.path.join(args.corpus_root, STATE_REL))
        mf_json = build_manifest(args.corpus_root, state, args.reference_date)
        log("[done]  manifest：%d 个文件入账 -> %s"
            % (len(mf_json["files"]),
               os.path.join(args.corpus_root, MANIFEST_NAME)))
        return 0

    if args.max_per_source < 1:
        ap.error("--max-per-source 至少 1")
    if args.mode == "bulk" and args.source == "case":
        ap.error("case 源没有 bulk（检索接口需登录，见 fetch_case_probe）")

    http = PoliteHttp(args.interval_min, args.interval_max,
                      ca_extra_paths=[os.path.join(
                          os.path.abspath(args.corpus_root), "state",
                          "cacert-mozilla.pem")])
    corpus_root = os.path.abspath(args.corpus_root)
    state = State(os.path.join(corpus_root, STATE_REL))
    log("== fetch_corpus %s | mode=%s source=%s ref=%s ==" %
        (TOOL_VERSION, args.mode, args.source, args.reference_date))
    log("[polite] UA=%s" % USER_AGENT)
    log("[polite] interval=uniform %.2f–%.2fs（下限 %ss 锁死）, "
        "backoff=%.0fs×%.0f cap=%.0fs, serial, Retry-After respected"
        % (http.interval_min, http.interval_max, MIN_INTERVAL_S,
           BACKOFF_START_S, BACKOFF_FACTOR, BACKOFF_CAP_S))

    sources = ["fr", "cn", "it", "es", "case"] if args.source == "all" \
        else [args.source]
    runners = {"fr": fetch_fr, "cn": fetch_cn, "it": fetch_it, "es": fetch_es,
               "case": fetch_case_probe}
    failures = []
    for src in sources:
        log("---- source: %s ----" % src)
        try:
            rc = runners[src](http, corpus_root, state, args.max_per_source,
                              args.mode, args.reference_date, args.yes)
            if rc != 0:
                failures.append((src, "计划被拒/中止（rc=%d）" % rc))
        except FetchError as e:
            failures.append((src, str(e)))
            log("[FAIL]  %s：%s" % (src, e))
        state.save()
    build_manifest(corpus_root, state, args.reference_date)
    log("[manifest] 已写 %s" % os.path.join(corpus_root, MANIFEST_NAME))
    if http.gap_log:
        sample = ", ".join("%.2f" % g for g in http.gap_log[:8])
        log("[polite] 本次随机间隔实值（前 %d 发）：%s%s"
            % (min(8, len(http.gap_log)), sample,
               " …" if len(http.gap_log) > 8 else ""))
    log("[polite] 共发出 %d 个请求，全程串行" % http.request_count)
    if failures:
        for src, why in failures:
            log("[RESULT] %s = 失败：%s" % (src, why))
        return 3
    for src in sources:
        log("[RESULT] %s = ok" % src)
    return 0


if __name__ == "__main__":
    sys.exit(main())
