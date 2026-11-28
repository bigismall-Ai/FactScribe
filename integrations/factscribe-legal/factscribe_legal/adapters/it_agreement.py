# -*- coding: utf-8 -*-
"""意大利集体协议（CCNL）清单 → 统一契约字段（读侧派生）。

**单独形状**：CNEL 这套**不是卡片**——无 `.card.txt`、无官方件副本、无正文，
引用单位是「协议 § 条款／附件／等级表」而不是条文号（草案 §2.4、
映射表 §8）⇒ `kind=agreement`，不塞进法条模板。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §8（意大利集体协议）
  · `code`（CNEL 簇码，如 `A011`）→ `local_id`：**直映**，原样保留；
  · 形状 → `kind=agreement`、`jurisdiction=it`：**转换**。

第 3 步的时点字段（status / asof / effective_from / effective_to / status_source）
--------------------------------------------------------------------------
**到期日 ≠ 失效日**（时点表 §2.5）——这是本线唯一的语义陷阱：

  * 源字段：`corpus-bulk-it/it-inventory-vigenti.tsv` 第 7、8 列
    （`inizio_storia`、`scadenza_ultimo_accordo`）；实读 144 行两列全非空
    （示例 `A011`：`1979-06-25` / `2029-12-31`）；
  * `scadenza_ultimo_accordo` 是「**末次协议**的到期日」，**不是**该协议的
    失效日——集体协议续签不改变 `local_id`，到期日过了只能说明
    「末次协议文本过期」，**不能判该 CCNL 已废止** ⇒ 过期落 `unknown`，
    **不落 `repealed`**；
  * status 取值：
      - 到期日 ≥ 参考日 ⇒ `in_force`；
      - 到期日 < 参考日 ⇒ `unknown`（末次协议文本过期，判不出是否还在用）；
      - 到期日为空 ⇒ `unknown`；
      - 没有参考日可依时 ⇒ 依「官方清单本身」判：清单来自 CNEL 档案的
        「**现行或超期有效**」专区（`corpus-bulk-it/ATTRIBUTION` 自述，
        144 簇全是），清单**不含已废止协议** ⇒ `in_force`，
        `status_source` 标 `it:cnel_vigenti`（取件口径，非逐条官方判定）。
  * `effective_from` ＝ `inizio_storia`（协议起始日）；
    `effective_to` ＝ `scadenza_ultimo_accordo`（末次协议到期日，
    **不是**失效日）；
  * `asof` ＝ `scadenza_ultimo_accordo`（本线唯一与「是否还在用」直接
    相关的官方时点，也是 status 判定的锚点）；取不到则退回
    `inizio_storia`；再取不到填「—」。

第 4 步的五元组后三位（span / face / how）：**三位全「—」**
----------------------------------------------------
  * **我们还没接**：仓内 CCNL 材料**只有元数据**（清单 TSV / 簇表 /
    manifest，**无全文**），官方全文取件端点「已探明但**本层不调用**」
    （`corpus-bulk-it/ATTRIBUTION`：链接层只取列表与链接；且全文再分发
    未清权，**全文 PDF 不得对外再分发**）⇒ 没有正文可定位 ⇒ span / face「—」；
  * **how** 也「—」：`factscribe_legal/lines.py:75-83` 的七条线里**没有 CCNL
    这一条** ⇒ 本层**没有可复用的核验方式**（不借用中国线的 `catalog`
    ——那是中国法规那条线的口径）。

⇒ 将来把 CCNL 接成第八条线（调用官方全文端点）时，how 随该线一起定。
"""
import csv
import json

from .base import (FIELD_ASOF, FIELD_CANONICAL_ID, FIELD_DECIDED_ON,
                   FIELD_EFFECTIVE_FROM, FIELD_EFFECTIVE_TO, FIELD_FACE,
                   FIELD_HOW, FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   FIELD_SPAN, FIELD_STATUS, FIELD_STATUS_SOURCE,
                   JURISDICTION_IT, KIND_AGREEMENT, ContractFieldMissing,
                   MISSING)
from .status import STATUS_IN_FORCE, STATUS_UNKNOWN, iso_date


def _span_face_how():
    """集体协议（CCNL）：卡级五元组后三位（span / face / how）→ 三元组。

    口径逐条写在模块 docstring 的「第 4 步的五元组后三位」一节里。
    """
    # 仓内只有元数据、官方全文端点本层不调用 ⇒ 三位全「—」
    return MISSING, MISSING, MISSING


SHAPE = "it_agreement"
KIND = KIND_AGREEMENT
JURISDICTION = JURISDICTION_IT


def read_inventory(path):
    """读 `it-inventory-vigenti.tsv` → 行 dict 列表（首行表头，制表符分隔）。"""
    rows = []
    with open(str(path), encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = None
        for cells in reader:
            if not cells or not any(c.strip() for c in cells):
                continue
            if header is None:
                header = [c.strip() for c in cells]
                continue
            rows.append(dict(zip(header, [c.strip() for c in cells])))
    return rows


def load_index(path):
    """读 `it-clusters.json` → dict。"""
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def adapt(source, index=None, reference_date=None):
    """source：清单行 dict（键＝表头名）；index：it-clusters.json（可空）。

    reference_date：参考日（可空）——有则与到期日比；无则依官方清单本身判。
    """
    if not isinstance(source, dict):
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID,
                                   "集体协议不是卡片，source 必须是清单行")
    code = str(source.get("code") or "").strip()
    if not code and index:
        # 兜底：用协议全称到 clusters.json 里反查簇码。
        title = str(source.get("title") or "").strip()
        for cluster in (index.get("clusters") or []):
            if str((cluster or {}).get("title") or "").strip() == title:
                code = str(cluster.get("code") or "").strip()
                break
    if not code:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID, "清单行没有 code 列")

    scadenza = iso_date(source.get("scadenza_ultimo_accordo"))
    inizio = iso_date(source.get("inizio_storia"))
    ref = str(reference_date or "").strip()

    if not scadenza:
        status = STATUS_UNKNOWN
        status_source = "it:scadenza_ultimo_accordo"
    elif ref and scadenza < ref:
        # 末次协议文本已过期 ⇒ 判不出该 CCNL 是否还在用（不是 repealed！）
        status = STATUS_UNKNOWN
        status_source = "it:scadenza_ultimo_accordo@%s" % ref
    else:
        status = STATUS_IN_FORCE
        status_source = ("it:scadenza_ultimo_accordo@%s" % ref) if ref else "it:cnel_vigenti"

    span, face, how = _span_face_how()

    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: code,
            FIELD_CANONICAL_ID: "—",      # v0 统一填「—」（映射表 §1）
            FIELD_EFFECTIVE_FROM: inizio or "—",
            FIELD_EFFECTIVE_TO: scadenza or "—",
            FIELD_STATUS: status,
            FIELD_ASOF: scadenza or inizio or "—",
            FIELD_DECIDED_ON: "—",        # 仅 kind=case 有效
            FIELD_STATUS_SOURCE: status_source,
            FIELD_SPAN: span,
            FIELD_FACE: face,
            FIELD_HOW: how}
