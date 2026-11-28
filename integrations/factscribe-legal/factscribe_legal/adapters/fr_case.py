# -*- coding: utf-8 -*-
"""法国判例卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §7（法国判例）
  · `CASE_ID` → `local_id`：**直映**，原样保留（如 `JURITEXT000006951547`）；
  · 形状 → `kind=case`、`jurisdiction=fr`：**转换**。

判例没有「在效/失效」概念 ⇒ 三态对 `kind=case` **不适用**（统一层填「—」），
见 `integrations/factscribe-legal/docs/legal-card-contract-time-model.md` §2.6；本轮不落 `status`。
"""
from .base import (FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   JURISDICTION_FR, KIND_CASE, ContractFieldMissing,
                   card_stem, load_json, read_card_fields)

SHAPE = "fr_case"
KIND = KIND_CASE
JURISDICTION = JURISDICTION_FR
CARD_SUFFIX = ".fr-case.card.txt"


def load_index(path):
    """读法国判例 run 的 `index.json` → dict。"""
    return load_json(path)


def adapt(source, index=None):
    """source：法国判例证据卡路径；index：run 的 index.json（可空）。"""
    fields = read_card_fields(source)
    case_id = fields.get("CASE_ID", "").strip()
    if not case_id and index:
        case_id = card_stem(source, CARD_SUFFIX)
    if not case_id:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID, "卡上没有 CASE_ID 行")
    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: case_id}
