# -*- coding: utf-8 -*-
"""卡级**收据五元组**（`span` / `face` / `how`）的投影共用件（第 4 步）。

是什么
------
统一契约的 `span` / `face` / `how` 是**收据五元组的后三位**
（契约草案 §2.2；映射表 §1 的「已定收据五元组的其余三位」）。收据五元组
由**两个已有件**生产，本件**不新写一套**：

  * `factscribe_legal/receipts.py`：`span_in_text`（`:60-73`）、
    `classify_how`（`:76-85`）、`build_receipt`（`:89-100`）、
    缺省标记 `MISSING`（`:34`，＝「—」）；
  * `factscribe_legal/lines.py`：七条线的适配点（适配表 `:22-38`）——
    「材料在哪、命中面怎么定、怎么核验」。

事实级收据是**按事实**产出的（一条事实一条收据，`lines.py` 各
`_xxx_receipts` 遍历 `load_facts`）；统一契约是**按卡**产出的（一张卡
一条契约记录）⇒ 本件只做一件事：**把上面那两个共用的生产逻辑用在卡粒度上**。

卡级口径（逐条对应 receipts.py 的字段定义，**不新造语义**）
----------------------------------------------------------
  * 「值」＝**这张卡自己钉住的官方正文**：
      - 卡内嵌了官方正文段（`--- OFFICIAL TEXT ---` 之后）⇒ 就用它；
      - 卡没内嵌正文（法国法条卡只钉哈希与元数据）⇒ 用官方件里与卡对应的
        那段正文（法国法条＝官方 XML 的 `BLOC_TEXTUEL` 归一正文）。
  * 「官方正文」＝**该线适配点所用的那份官方文本**（`lines.py` 各线那一份）：
      法国法条＝`BLOC_TEXTUEL` 归一正文；西班牙/意大利法条＝条文切片正文；
      意大利判例＝判决切片正文；法国判例＝官方纯文本还原件全文。
  * `span` ＝ `receipts.span_in_text(值, 官方正文)`——**原文坐标的首次命中
    区间**，取不到填「—」。
  * `face` ＝ `lines._face_of(值, 正文面, 全文面)`——`body` / `résumé` /
    「—」。
  * `how`  ＝ **该线适配点定的核验方式**：`contains`（逐字）／`numnorm`
    （数字·日期归一）／`catalog`（目录树·详情元数据对账）／「—」。它在该线是
    **常量**（西班牙/意大利法条＝`contains`、中国法规＝`catalog`）还是
    **由值推出**（法国法条、两条判例线），照抄 `lines.py`，不另立。

取不到（官方材料没取到／官方数据里没有这个概念／本层还没接）⇒ **一律填
`receipts.MISSING`（「—」）**，缺省兜底统一走 `receipts.build_receipt`
一个函数——不各线各写一遍。

本件只读、零 LLM、零网络、不写盘。
"""
import os

from .. import lines
from .. import receipts
from .base import CARD_TEXT_MARKER

__all__ = ["TRUNCATION_MARK", "strip_truncation", "embedded_text",
           "read_bytes", "read_text", "run_index", "slice_text", "project"]

# 取件端点写卡时的截断记号（`tools/fetch_corpus.py:1215`/`:1427`/`:1814`
# 的 `text[:600] + ("…" if len(text) > 600 else "")`）——它**不是**官方正文，
# 定位时必须剥掉，否则永远命中不了。
TRUNCATION_MARK = "…"


def strip_truncation(text):
    """剥掉取件端点的截断记号「…」（连带首尾换行）——还原成官方正文。

    只剥**结尾**那一个记号；剥完为空则原样返回（不越剥）。
    ⚠️ 首尾换行也要剥：卡里正文段前面那个换行**不是**官方正文的一部分
    （`factscribe_legal/lines.py:185-191` 的 `_embedded_official_text` 同样
    剥首行换行）——留着会让原文坐标整体偏移一位。
    """
    out = str(text or "").strip("\n")
    if out.endswith(TRUNCATION_MARK):
        out = out[:-1]
    return out


def embedded_text(path):
    """卡内嵌的官方正文段（`--- OFFICIAL TEXT ---` 之后，已剥截断记号）。

    卡没内嵌正文段 ⇒ 空串（调用方按「这张卡不携带正文」处理）。
    """
    text = read_text(path)
    if not text or CARD_TEXT_MARKER not in text:
        return ""
    return strip_truncation(text.split(CARD_TEXT_MARKER, 1)[1])


def read_bytes(path):
    """读一个二进制文件；读不到 ⇒ 空串（材料没拿到，不是异常）。"""
    try:
        with open(str(path), "rb") as fh:
            return fh.read()
    except OSError:
        return b""


def read_text(path):
    """读一个文本文件；读不到 ⇒ 空串（材料没拿到，不是异常）。"""
    try:
        with open(str(path), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def run_index(card_path, index=None):
    """该卡所属 run 目录的 `index.json` → dict。

    调用方传了 `index` 就用它；没传就读**卡所在目录**下的 `index.json`
    ——与 `factscribe_legal/lines.py:216-228` 的 `_index_articles` 同一套
    约定（语料目录本身就是 run 目录，index.json 在它根上）。读不到 ⇒ {}。
    """
    if isinstance(index, dict) and index:
        return index
    path = os.path.join(os.path.dirname(os.path.abspath(str(card_path))),
                        "index.json")
    try:
        import json
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def slice_text(card_path, meta, reader):
    """条文/判决**切片件**的正文 → str。

    * `meta`：run 的 `index.json` 里那一条（取 `article_file` 或
      `slice_file`；两者都是相对 run 目录的路径）；
    * `reader`：bytes → str 的纯文本函数（该线 `lines.py` 用的那一个：
      `es_verify._plain_text` / `it_verify._plain_text` /
      `it_case_verify._itcase_plain`）。

    文件不在（**我们还没接**：仓外批量件没取到）⇒ 空串。
    """
    meta = meta or {}
    rel = meta.get("article_file") or meta.get("slice_file") or ""
    if not rel:
        return ""
    path = os.path.join(os.path.dirname(os.path.abspath(str(card_path))), rel)
    raw = read_bytes(path)
    if not raw:
        return ""
    try:
        return reader(raw)
    except Exception:            # noqa: BLE001 —— 材料坏了不许穿透成堆栈
        return ""


def project(value, official_text, how=None, body_text=None):
    """卡级五元组（`span` / `face` / `how`）——取值算法与事实级**同一个**。

    * `span` ＝ `receipts.span_in_text(值, 官方正文)`（原文坐标首次命中区间）；
    * `face` ＝ `lines._face_of(值, 正文面, 全文面)`（body / résumé / 「—」）；
    * `how`  ＝ 该线 `lines.py` 适配点定的核验方式（不给 ⇒ 「—」）。

    「值」或「官方正文」任一取不到 ⇒ `span` / `face` 落「—」；`how` 仍按
    该线口径给（它多半是该线的核验方式常量，不由正文可得性决定；由值推出来
    的线则此时连值都没有 ⇒ 传 `how=None` 即「—」）。

    缺省兜底统一走 `receipts.build_receipt`（`:89-100`）——**不各线各写一遍**。
    """
    if value and official_text:
        span = receipts.span_in_text(value, official_text)
        face = lines._face_of(
            value,
            official_text if body_text is None else body_text,
            official_text)
    else:
        span = face = None
    rec = receipts.build_receipt("", "", span, face, how)
    return rec["span"], rec["face"], rec["how"]
