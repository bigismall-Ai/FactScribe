# -*- coding: utf-8 -*-
"""意大利宪法法院判例卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §6（意大利判例）
  · `ECLI` → `local_id`：**直映**，原样保留（如 `ECLI:IT:COST:1956:1`）；
  · 形状 → `kind=case`、`jurisdiction=it`：**转换**。

第 3 步的时点字段：**本线不产 status**（status 填「—」）
--------------------------------------------------------------------------
判断理由（不是「懒得填」，是判定「这一维度不适用」）：

  1. **判例没有「效力」这个时间维度**：判决作出即固定，不随参考日变化
     （时点表 §2.6）。契约三态问的是「参考日当天现行不现行有效」，
     这个问题对判决不成立。
  2. **仓里也没有任何能判「是否仍可被引用」的字段**：实读
     `factscribe_legal/it_case_verify.py:295-296`，判例闸只认
     `OFFICIAL_XML_SHA256` / `TEXT_SHA256` 两个哈希声明，**全文无任何
     status 字段消费**（grep `status|vigour|in_force|repeal` 零命中）；
     卡上只有判决日与签署人（`ECLI-IT-COST-1956-1.itcase.card.txt:4-11`）。
  3. ⇒ 这不是「查了但下不了结论」的 `unknown`，而是「**这条线根本不产
     status**」⇒ 按契约草案 §2.2 填**「—」**（与收据五元组同一个缺省标记）。

  ⚠️ 判决日**不占用** `effective_from` / `effective_to`（那是生效日），
  也不占用 `asof`（asof 是「status 相对于哪个时点」，本线没有 status）：
  判决日归契约草案另设的 `decided_on` 字段承接（时点表 §2.6 末段）。
"""
from .base import (FIELD_ASOF, FIELD_CANONICAL_ID, FIELD_DECIDED_ON,
                   FIELD_EFFECTIVE_FROM, FIELD_EFFECTIVE_TO, FIELD_JURISDICTION,
                   FIELD_KIND, FIELD_LOCAL_ID, FIELD_STATUS,
                   FIELD_STATUS_SOURCE, JURISDICTION_IT, KIND_CASE,
                   ContractFieldMissing, card_stem, load_json, read_card_fields)
from .status import iso_date, iso_date_dmy

SHAPE = "it_case"
KIND = KIND_CASE
JURISDICTION = JURISDICTION_IT
CARD_SUFFIX = ".itcase.card.txt"


def load_index(path):
    """读意大利判例 run 的 `index.json` → dict。"""
    return load_json(path)


def adapt(source, index=None, reference_date=None):
    """source：意大利判例证据卡路径；index：run 的 index.json（可空）。

    reference_date：参考日（可空）——本线不产 status，故不消费。
    """
    fields = read_card_fields(source)
    ecli = fields.get("ECLI", "").strip()
    if not ecli and index:
        # 兜底：卡上没有 ECLI 行时，用卡文件名主干到索引里反查。
        judgments = index.get("judgments") or {}
        meta = judgments.get(card_stem(source, CARD_SUFFIX)) or {}
        ecli = str(meta.get("ecli") or "").strip()
    if not ecli:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID, "卡上没有 ECLI 行")

    decided_on = iso_date(fields.get("DATA_DECISIONE_ISO")) \
        or iso_date_dmy(fields.get("DATA_DECISIONE"))

    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: ecli,
            FIELD_CANONICAL_ID: "—",      # v0 统一填「—」（映射表 §1）
            FIELD_EFFECTIVE_FROM: "—",    # 判例无生效区间
            FIELD_EFFECTIVE_TO: "—",
            FIELD_STATUS: "—",            # 本线不产 status（三态不适用）
            FIELD_ASOF: "—",              # 没有 status ⇒ 没有判定锚点
            FIELD_DECIDED_ON: decided_on or "—",
            FIELD_STATUS_SOURCE: "—"}
