# -*- coding: utf-8 -*-
"""法国判例卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §7（法国判例）
  · `CASE_ID` → `local_id`：**直映**，原样保留（如 `JURITEXT000006951547`）；
  · 形状 → `kind=case`、`jurisdiction=fr`：**转换**。

第 3 步的时点字段：**本线不产 status**（status 填「—」）
--------------------------------------------------------------------------
判断理由（与意大利判例同构，理由逐条见 `it_case.py` 的 docstring）：

  1. 判例没有「效力」这个时间维度：判决作出即固定，不随参考日变化
     （时点表 §2.6）⇒ 契约三态问的「参考日当天现行不现行有效」对判决不成立；
  2. 仓里也没有能判「是否仍可被引用」的字段：实读
     `factscribe_legal/fr_case_verify.py:153-154`，判例闸只认
     `OFFICIAL_XML_SHA256` / `OFFICIAL_TXT_SHA256` 两个哈希声明，
     **全文无任何 status 字段消费**；卡上只有判决日与审判法院
     （`JURITEXT000006951547.fr-case.card.txt:4-8`）；
  3. ⇒ 「这条线根本不产 status」⇒ 填**「—」**（契约草案 §2.2）。

  ⚠️ 判决日归 `decided_on`（映射表 §7：`DATE_DEC` → `decided_on`），
  **不占用** `effective_from` / `effective_to` / `asof`。
"""
from .base import (FIELD_ASOF, FIELD_CANONICAL_ID, FIELD_DECIDED_ON,
                   FIELD_EFFECTIVE_FROM, FIELD_EFFECTIVE_TO, FIELD_JURISDICTION,
                   FIELD_KIND, FIELD_LOCAL_ID, FIELD_STATUS,
                   FIELD_STATUS_SOURCE, JURISDICTION_FR, KIND_CASE,
                   ContractFieldMissing, card_stem, load_json, read_card_fields)
from .status import iso_date

SHAPE = "fr_case"
KIND = KIND_CASE
JURISDICTION = JURISDICTION_FR
CARD_SUFFIX = ".fr-case.card.txt"


def load_index(path):
    """读法国判例 run 的 `index.json` → dict。"""
    return load_json(path)


def adapt(source, index=None, reference_date=None):
    """source：法国判例证据卡路径；index：run 的 index.json（可空）。

    reference_date：参考日（可空）——本线不产 status，故不消费。
    """
    fields = read_card_fields(source)
    case_id = fields.get("CASE_ID", "").strip()
    if not case_id and index:
        case_id = card_stem(source, CARD_SUFFIX)
    if not case_id:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID, "卡上没有 CASE_ID 行")

    decided_on = iso_date(fields.get("DATE_DEC")) or iso_date(fields.get("JUDGE_DATE"))

    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: case_id,
            FIELD_CANONICAL_ID: "—",      # v0 统一填「—」（映射表 §1）
            FIELD_EFFECTIVE_FROM: "—",    # 判例无生效区间
            FIELD_EFFECTIVE_TO: "—",
            FIELD_STATUS: "—",            # 本线不产 status（三态不适用）
            FIELD_ASOF: "—",              # 没有 status ⇒ 没有判定锚点
            FIELD_DECIDED_ON: decided_on or "—",
            FIELD_STATUS_SOURCE: "—"}
