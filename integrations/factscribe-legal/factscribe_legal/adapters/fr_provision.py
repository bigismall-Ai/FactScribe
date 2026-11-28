# -*- coding: utf-8 -*-
"""法国法条卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §2（法国法条）
  · `NUM` → `local_id`：**直映**，原样保留（如 `D641-10-1`），不翻译；
  · 形状 → `kind=provision`、`jurisdiction=fr`：**转换**（卡上没有这两个
    字段，由 adapter 按形状填，不写进卡——写进卡就要重钉，草案 §3.2）。

本轮只产三个字段；`status`/`asof` 见第 3 步（TODO 见
`integrations/factscribe-legal/docs/legal-card-contract-time-model.md` §2.1）。
"""
from .base import (FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   JURISDICTION_FR, KIND_PROVISION, ContractFieldMissing,
                   load_json, read_card_fields)

SHAPE = "fr_provision"
KIND = KIND_PROVISION
JURISDICTION = JURISDICTION_FR
CARD_SUFFIX = ".card.txt"


def load_index(path):
    """读法国侧的 `fr/index.json` → dict（卡上没有编号时的兜底用）。"""
    return load_json(path)


def adapt(source, index=None):
    """source：法国法条证据卡路径；index：`fr/index.json` 的 dict（可空）。"""
    fields = read_card_fields(source)
    local_id = fields.get("NUM", "").strip()
    if not local_id:
        # 兜底：卡上没有 NUM 行时，用卡里的官方 XML 文件名到索引里反查编号。
        local_id = _num_from_index(index, fields)
    if not local_id:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID, "卡上没有 NUM 行")
    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: local_id}


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
