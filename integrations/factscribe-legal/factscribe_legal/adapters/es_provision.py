# -*- coding: utf-8 -*-
"""西班牙法条卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §4（西班牙法条）
  · `ACT_ID` ＋ `BLOCK_ID` → `local_id`：**直映**，复合形式，原样保留
    （草案 §2.3 允许复合，如 `BOE-A-2015-10565/a1`）；
  · 形状 → `kind=provision`、`jurisdiction=es`：**转换**。

本轮只产三个字段。

TODO（第 3 步 · 待用户拍板，本轮**不自行决定**）
------------------------------------------------
`estado_consolidacion` **不能**当废止标志：实读三个 run 全是
`"Finalizado"`（`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §4 的 index 顶层），
而这三个法（1978 宪法、39/2015、40/2015）今天全部现行有效
⇒ `"Finalizado"` 在 BOE 语义里指「合并文本的**编纂流程**已结束」，不是
「该法已废止」；若当废止标志，会把三个现行有效的法全判成已失效。
口径见 `integrations/factscribe-legal/docs/legal-card-contract-time-model.md` §2.3 与
`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §4 的 status 行。
拍板前本层的 `status` 一律不落，`estado_consolidacion` 留国别专属。
"""
from .base import (FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   JURISDICTION_ES, KIND_PROVISION, ContractFieldMissing,
                   card_stem, load_json, read_card_fields)

SHAPE = "es_provision"
KIND = KIND_PROVISION
JURISDICTION = JURISDICTION_ES
CARD_SUFFIX = ".es.card.txt"


def load_index(path):
    """读西班牙 run 的 `index.json` → dict（卡上缺字段时的兜底用）。"""
    return load_json(path)


def adapt(source, index=None):
    """source：西班牙法条证据卡路径；index：run 的 index.json（可空）。"""
    fields = read_card_fields(source)
    act_id = fields.get("ACT_ID", "").strip()
    block_id = fields.get("BLOCK_ID", "").strip()
    if not act_id and index:
        act_id = str(index.get("act_id") or "").strip()
    if not block_id:
        block_id = card_stem(source, CARD_SUFFIX)
    if not act_id or not block_id:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID,
                                   "卡上没有 ACT_ID/BLOCK_ID 行")
    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: "%s/%s" % (act_id, block_id)}
