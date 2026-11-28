# -*- coding: utf-8 -*-
"""中国法规卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §3（中国法规）
  · `BBBS` → `local_id`：**直映**，原样保留（国家法律法规数据库版本标识）；
  · 形状 → `kind=provision`、`jurisdiction=cn`：**转换**。中国侧一张卡
    ＝一部法规（**法规级**不是条文级，官方详情 JSON 不含条文正文，
    见 `factscribe_legal/cn_corpus.py:4-10`）⇒ 归 provision。

本轮只产三个字段。

TODO（第 3 步 · 待用户拍板，本轮**不自行决定**）
------------------------------------------------
中国 `SXX=2`（修改）在统一三态里落 `in_force` 还是 `unknown`，两处现有口径
相反，本轮不碰：
  * 现行闸判**红**：`factscribe_legal/cn_verify.py:89-93`（`sxx != 3` ⇒
    `CN_PROV_NOT_IN_FORCE`）；
  * 取代表偏好却把 2 排在废止之上：`factscribe_legal/cn_corpus.py:56-63`
    （`_prefer` 的 `{3:3, 2:2, 4:1, 1:0}`）。
口径见 `integrations/factscribe-legal/docs/legal-card-contract-time-model.md` §2.2（含建议与代价）与
`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §3 的 status 行。拍板后在本模块补
`status` 字段，并在 `integrations/factscribe-legal/docs/legal-card-contract-draft.md` §1.3「第三步」处
记录该差异。
"""
from ..cn_corpus import load_catalog
from .base import (FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   JURISDICTION_CN, KIND_PROVISION, ContractFieldMissing,
                   read_card_fields)

SHAPE = "cn_provision"
KIND = KIND_PROVISION
JURISDICTION = JURISDICTION_CN
CARD_SUFFIX = ".cn.card.txt"


def load_index(catalog_path):
    """读中国全库目录（`catalog.jsonl.gz`）→ {bbbs: record}。"""
    return load_catalog(catalog_path)


def adapt(source, index=None):
    """source：中国法规证据卡路径；index：全库目录 {bbbs: record}（可空）。"""
    fields = read_card_fields(source)
    local_id = fields.get("BBBS", "").strip()
    if not local_id:
        # 兜底：卡上没有 BBBS 行时，用卡上的法规名到全库目录里反查版本标识。
        local_id = _bbbs_from_index(index, fields)
    if not local_id:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID, "卡上没有 BBBS 行")
    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: local_id}


def _bbbs_from_index(index, fields):
    if not index:
        return ""
    title = (fields.get("TITLE") or "").strip()
    if not title:
        return ""
    for bbbs, rec in index.items():
        if str((rec or {}).get("title") or "").strip() == title:
            return str(bbbs)
    return ""
