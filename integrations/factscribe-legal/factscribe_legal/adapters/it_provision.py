# -*- coding: utf-8 -*-
"""意大利法条卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §5（意大利法条）
  · `ACT_URN` ＋ `ARTICLE_EID` → `local_id`：**直映**，复合形式，原样保留
    （草案 §2.3 的示例 `urn:...;241/art_1`）；
  · 形状 → `kind=provision`、`jurisdiction=it`：**转换**。

本轮只产三个字段。意大利法条官方件无生效区间（AKN 头部只有
`<act name="monovigente">`），`status` 只能取件口径 ⇒ 属第 3 步，见
`integrations/factscribe-legal/docs/legal-card-contract-time-model.md` §2.4。
"""
from .base import (FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   JURISDICTION_IT, KIND_PROVISION, ContractFieldMissing,
                   card_stem, load_json, read_card_fields)

SHAPE = "it_provision"
KIND = KIND_PROVISION
JURISDICTION = JURISDICTION_IT
CARD_SUFFIX = ".it.card.txt"


def load_index(path):
    """读意大利 run 的 `index.json` → dict。"""
    return load_json(path)


def adapt(source, index=None):
    """source：意大利法条证据卡路径；index：run 的 index.json（可空）。"""
    fields = read_card_fields(source)
    act_urn = fields.get("ACT_URN", "").strip()
    eid = fields.get("ARTICLE_EID", "").strip()
    if not act_urn and index:
        act_urn = str(index.get("act_urn") or "").strip()
    if not eid:
        eid = card_stem(source, CARD_SUFFIX)
    if not act_urn or not eid:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID,
                                   "卡上没有 ACT_URN/ARTICLE_EID 行")
    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: "%s/%s" % (act_urn, eid)}
