"""中文侧语料：国家法律法规数据库（flk.npc.gov.cn）全库 → 可钉哈希的本地目录。

与法国侧的结构差异（决定了判据不同）：
  法国：条文有 `date_debut/date_fin` **区间**，官方 XML **含正文**
  中国：法规给 `sxx` **当前状态标志** + `gbrq/sxrq` 两个日期；详情 JSON 给**章→条目录树**，**不含条文正文**

⇒ 中国侧可核的是：
  ① 该法规在参考日是否现行有效（sxx）
  ② 引用的**条文号是否真的存在于该法规的目录树里**（中国版的"出处核验"）
  ③ 官方详情字节的哈希是否未变
"""
import gzip
import hashlib
import json
import os
import re


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_catalog(catalog_path):
    """读 catalog.jsonl.gz → {bbbs: record}"""
    out = {}
    if not os.path.exists(catalog_path):
        return out
    with gzip.open(catalog_path, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["bbbs"]] = r
    return out


def index_records(catalog):
    """按标题建索引（同名多版本时取现行有效的那一版，其次取最新公布日）。"""
    by_title = {}
    for bb, r in catalog.items():
        t = (r.get("title") or "").strip()
        if not t:
            continue
        cur = by_title.get(t)
        if cur is None or _prefer(r, cur):
            by_title[t] = r
    return by_title


def _prefer(a, b):
    """a 是否比 b 更该作为代表：现行有效 > 已修改 > 其它；同则比较公布日。"""
    order = {3: 3, 2: 2, 4: 1, 1: 0}
    sa = order.get(a.get("sxx"), 0)
    sb = order.get(b.get("sxx"), 0)
    if sa != sb:
        return sa > sb
    return (a.get("gbrq") or "") > (b.get("gbrq") or "")


ART_RE = re.compile(r"^(第[一二三四五六七八九十百千零〇两]+条)")


def article_key(title):
    """从目录树节点标题里取「第X条」；取不到返回 None。"""
    t = (title or "").strip()
    m = ART_RE.match(t)
    return m.group(1) if m else None


def find_article(record, art_title):
    """在法规的目录树里找某条；返回 (命中?, 条标题)"""
    arts = record.get("articles") or []
    for a in arts:
        if a.strip() == art_title.strip():
            return True, a
    return False, None
