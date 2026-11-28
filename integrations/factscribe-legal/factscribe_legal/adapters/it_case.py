# -*- coding: utf-8 -*-
"""意大利宪法法院判例卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §6（意大利判例）
  · `ECLI` → `local_id`：**直映**，原样保留（如 `ECLI:IT:COST:1956:1`）；
  · 形状 → `kind=case`、`jurisdiction=it`：**转换**。

判例没有「在效/失效」概念 ⇒ 三态对 `kind=case` **不适用**（统一层填「—」），
见 `integrations/factscribe-legal/docs/legal-card-contract-time-model.md` §2.6；本轮不落 `status`。
"""
from .base import (FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   JURISDICTION_IT, KIND_CASE, ContractFieldMissing,
                   card_stem, load_json, read_card_fields)

SHAPE = "it_case"
KIND = KIND_CASE
JURISDICTION = JURISDICTION_IT
CARD_SUFFIX = ".itcase.card.txt"


def load_index(path):
    """读意大利判例 run 的 `index.json` → dict。"""
    return load_json(path)


def adapt(source, index=None):
    """source：意大利判例证据卡路径；index：run 的 index.json（可空）。"""
    fields = read_card_fields(source)
    ecli = fields.get("ECLI", "").strip()
    if not ecli and index:
        # 兜底：卡上没有 ECLI 行时，用卡文件名主干到索引里反查。
        judgments = index.get("judgments") or {}
        meta = judgments.get(card_stem(source, CARD_SUFFIX)) or {}
        ecli = str(meta.get("ecli") or "").strip()
    if not ecli:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID, "卡上没有 ECLI 行")
    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: ecli}
