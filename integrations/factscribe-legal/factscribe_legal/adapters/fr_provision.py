# -*- coding: utf-8 -*-
"""法国法条卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §2（法国法条）
  · `NUM` → `local_id`：**直映**，原样保留（如 `D641-10-1`），不翻译；
  · 形状 → `kind=provision`、`jurisdiction=fr`：**转换**（卡上没有这两个
    字段，由 adapter 按形状填，不写进卡——写进卡就要重钉，草案 §3.2）。

第 3 步的时点字段（status / asof / effective_from / effective_to / status_source）
--------------------------------------------------------------------------
**判据直接复用法国闸的判定，不另写一套**
（`factscribe_legal/provisions.py:100-115` 的 `in_force_at` /
`scheduled_at` / `repealed_at`，时点表 §2.1）：

  * 参考日 `ref` ＝ 调用方传入的 `reference_date`；没传则用卡上
    `POOL_ASOF`（版本池基准日，实读 `corpus/fr/D641-10-1.card.txt:9`
    ＝`2026-11-15`）；
  * `date_fin <= ref` ⇒ `repealed`（已于 DATE_FIN 失效）；
  * `date_debut > ref` ⇒ `unknown`（未来才生效，尚未在效）；
  * `date_debut <= ref < date_fin` ⇒ `in_force`；
  * 区间两字段都空 ⇒ `unknown`。
  ⚠️ **不许用 `ETAT` 判**（`provisions.py:102`：「⚠️ 不能用 etat 判：
  etat=VIGUEUR 的版本可能只是『未来才生效』」）⇒ `ETAT` 留国别专属。
  * `asof` ＝ 卡上 `POOL_ASOF`（映射表 §2：直映，时点版本基准日）；
  * `effective_from` ＝ `DATE_DEBUT`；`effective_to` ＝ `DATE_FIN`
    （`2999-01-01` 是「无终止」哨兵值，**原样保留**，不归一成「—」，
    时点表 §2.1）。

第 4 步的五元组后三位（span / face / how）
----------------------------------------
**取值不另立一套定义**：直接用 `factscribe_legal/receipts.py` 的共用生产逻辑
（`span_in_text` `:60-73`、`classify_how` `:76-85`、`build_receipt`
`:89-100`）与 `factscribe_legal/lines.py` 的七线适配点，卡粒度的投影口径见
`adapters/card_receipts.py`。本形状的「材料在哪」判据：

  * **官方正文**＝卡边上那份官方 XML 的 `BLOC_TEXTUEL` 归一正文——取文口径
    **直接复用** `factscribe_legal/lines.py:285-306` 的 `_fr_official_text`
    （公开出口 `lines.py:249-252` 的 `fr_official_text`）；
  * **卡所钉正文**＝同一段（法国法条卡只钉哈希与元数据、**不内嵌正文**，
    实读 `corpus/fr/D641-10-1.card.txt` 全文无 `--- OFFICIAL TEXT ---` 段）
    ⇒ 卡所钉正文＝官方正文本身；
  * **how**＝逐字核验（`factscribe_legal/lines.py:309-322` 的 `_fr_how` 对
    正文文本取值＝`contains`；本线是**由值推出** how 的一条）。

官方件取不到 ⇒ 三位全「—」：**我们还没接**——法国 171,801 件批量语料在
仓外 blobstore，本层只读仓内已取件的件（卡上 `OFFICIAL_XML` 指向的 XML
不在仓内时就是这个情形）。
"""
import os

from .. import lines
from ..provisions import Provision
from .base import (FIELD_ASOF, FIELD_CANONICAL_ID, FIELD_DECIDED_ON,
                   FIELD_EFFECTIVE_FROM, FIELD_EFFECTIVE_TO, FIELD_FACE,
                   FIELD_HOW, FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   FIELD_SPAN, FIELD_STATUS, FIELD_STATUS_SOURCE,
                   JURISDICTION_FR, KIND_PROVISION, ContractFieldMissing,
                   MISSING, load_json, read_card_fields)
from .card_receipts import project
from .status import STATUS_IN_FORCE, STATUS_REPEALED, STATUS_UNKNOWN, iso_date

SHAPE = "fr_provision"
KIND = KIND_PROVISION
JURISDICTION = JURISDICTION_FR
CARD_SUFFIX = ".card.txt"


def load_index(path):
    """读法国侧的 `fr/index.json` → dict（卡上没有编号时的兜底用）。"""
    return load_json(path)


def adapt(source, index=None, reference_date=None):
    """source：法国法条证据卡路径；index：`fr/index.json` 的 dict（可空）。

    reference_date：参考日（可空）——为空时用卡上 `POOL_ASOF` 兜底。
    """
    fields = read_card_fields(source)
    local_id = fields.get("NUM", "").strip()
    if not local_id:
        # 兜底：卡上没有 NUM 行时，用卡里的官方 XML 文件名到索引里反查编号。
        local_id = _num_from_index(index, fields)
    if not local_id:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID, "卡上没有 NUM 行")

    date_debut = (fields.get("DATE_DEBUT") or "").strip()
    date_fin = (fields.get("DATE_FIN") or "").strip()
    pool_asof = (fields.get("POOL_ASOF") or "").strip()
    ref = str(reference_date or "").strip() or pool_asof

    # 生效判定：复用 provisions.py 的三个方法（不另写一套）
    prov = Provision(num=local_id, date_debut=date_debut, date_fin=date_fin)
    if not ref:
        # 参考日与池基准日都取不到 ⇒ 判不了（时点表 §3.1）
        status = STATUS_UNKNOWN
    elif prov.repealed_at(ref):
        status = STATUS_REPEALED
    elif prov.scheduled_at(ref):
        status = STATUS_UNKNOWN          # 未来才生效 ⇒ unknown（与中国 sxx=4 同构）
    elif prov.in_force_at(ref):
        status = STATUS_IN_FORCE
    else:
        status = STATUS_UNKNOWN

    span, face, how = _span_face_how(source)

    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: local_id,
            FIELD_CANONICAL_ID: "—",      # v0 统一填「—」（映射表 §1）
            FIELD_EFFECTIVE_FROM: iso_date(date_debut) or "—",
            FIELD_EFFECTIVE_TO: iso_date(date_fin) or "—",
            FIELD_STATUS: status,
            FIELD_ASOF: iso_date(pool_asof) or "—",
            FIELD_DECIDED_ON: "—",        # 仅 kind=case 有效
            FIELD_STATUS_SOURCE: ("fr:date_range@%s" % ref) if ref else "fr:date_range",
            FIELD_SPAN: span,
            FIELD_FACE: face,
            FIELD_HOW: how}


def _span_face_how(source):
    """法国法条：卡级五元组后三位（span / face / how）→ 三元组。

    口径逐条写在模块 docstring 的「第 4 步的五元组后三位」一节里。
    """
    body = lines.fr_official_text(lines.LineContext(),
                                  os.path.abspath(str(source)))
    if not body:
        # 官方件不在仓内（我们还没接：法国批量件在仓外 blobstore）
        return MISSING, MISSING, MISSING
    return project(body, body, how=lines._fr_how(body))


def _num_from_index(index, fields):
    if not index:
        return ""
    xml_file = (fields.get("OFFICIAL_XML") or "").strip()
    if not xml_file:
        return ""
    for num, meta in (index.get("provisions") or {}).items():
        if (meta or {}).get("xml_file") == xml_file:
            return str(num)
    return ""
