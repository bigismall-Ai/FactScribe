# -*- coding: utf-8 -*-
"""意大利法条卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §5（意大利法条）
  · `ACT_URN` ＋ `ARTICLE_EID` → `local_id`：**直映**，复合形式，原样保留
    （草案 §2.3 的示例 `urn:...;241/art_1`）；
  · 形状 → `kind=provision`、`jurisdiction=it`：**转换**。

第 3 步的时点字段（status / asof / effective_from / effective_to / status_source）
--------------------------------------------------------------------------
**意大利官方件没有生效区间**——这是已知缺口，不是没查：

  * 官方件实读 `corpus/it/run-20261116-it-1990n241/official/act.akn.xml`：
    AKN 头部是 `<act name="monovigente">`（monovigente＝单一生效版本），
    全文 `datatype="xsd:date"` 只有两处，**没有任何 vigenza／生效区间属性**
    （时点表 §2.4）；
  * 全文里 `ABROGATO` 只出现在条文正文里（「PERIODO ABROGATO DAL …」
    这种条款级批注），**不是件级效力标志**；`Entrata in vigore della legge:
    2-9-1990` 是正文里的一句生效条款，**不是结构化字段**，不拿它当效力判定；
  * 卡上 `VERSION_DATE`（`2026-04-21`）是**文本日期戳**（合并文本自身最后
    更新日，同 `factscribe_legal/it_verify.py:178-179` 的口径），**不是**生效日；
  * `FETCH_VIGENZA`（`20261116`）与 `REFERENCE_DATE`（`2026-11-16`）是
    **取件参数**（`dataVigenza`），语义＝「参考日当天生效的版本」
    （`corpus/README.md:40-42`）。

  ⇒ **status 只能记弱口径**：取件那天取到的就是该日生效版 ⇒ `in_force`
  （时点表 §2.4／§3.6），并用 `status_source` 标出这是**取件口径不是官方
  效力判定**；拿不到取件参考日 ⇒ `unknown`。
  ⇒ `effective_from` / `effective_to` 一律「—」（官方层没有生效区间，
  **不许拿 status 反推日期**，时点表 §3.4）。
  ⇒ `asof` ＝ `FETCH_VIGENZA`（紧凑 YYYYMMDD ⇒ `2026-11-16`），
    没有则退回 `REFERENCE_DATE`，再没有填「—」。
"""
from .base import (FIELD_ASOF, FIELD_CANONICAL_ID, FIELD_DECIDED_ON,
                   FIELD_EFFECTIVE_FROM, FIELD_EFFECTIVE_TO, FIELD_JURISDICTION,
                   FIELD_KIND, FIELD_LOCAL_ID, FIELD_STATUS,
                   FIELD_STATUS_SOURCE, JURISDICTION_IT, KIND_PROVISION,
                   ContractFieldMissing, card_stem, load_json, read_card_fields)
from .status import STATUS_IN_FORCE, STATUS_UNKNOWN, iso_date

SHAPE = "it_provision"
KIND = KIND_PROVISION
JURISDICTION = JURISDICTION_IT
CARD_SUFFIX = ".it.card.txt"


def load_index(path):
    """读意大利 run 的 `index.json` → dict。"""
    return load_json(path)


def adapt(source, index=None, reference_date=None):
    """source：意大利法条证据卡路径；index：run 的 index.json（可空）。

    reference_date：参考日（可空）——取件参考日以卡上 `FETCH_VIGENZA` /
    `REFERENCE_DATE` 为准（那才是「取件那天生效的版本」的口径）。
    """
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

    fetch_vig = (fields.get("FETCH_VIGENZA") or "").strip()
    ref_date = (fields.get("REFERENCE_DATE") or "").strip()
    asof = iso_date(fetch_vig) or iso_date(ref_date)

    if asof:
        # 取件口径：那天取到的就是那天生效的版本（弱口径，非官方效力判定）
        status = STATUS_IN_FORCE
        status_source = "it:asof_semantics@%s" % asof
    else:
        status = STATUS_UNKNOWN
        status_source = "it:asof_semantics"

    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: "%s/%s" % (act_urn, eid),
            FIELD_CANONICAL_ID: "—",      # v0 统一填「—」（映射表 §1）
            FIELD_EFFECTIVE_FROM: "—",    # 官方件无生效区间（时点表 §2.4）
            FIELD_EFFECTIVE_TO: "—",
            FIELD_STATUS: status,
            FIELD_ASOF: asof or "—",
            FIELD_DECIDED_ON: "—",        # 仅 kind=case 有效
            FIELD_STATUS_SOURCE: status_source}
