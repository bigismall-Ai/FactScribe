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

第 4 步的五元组后三位（span / face / how）
----------------------------------------
**取值不另立一套定义**：直接用 `factscribe_legal/receipts.py` 的共用生产逻辑
与 `factscribe_legal/lines.py` 的七线适配点（卡粒度的投影口径见
`adapters/card_receipts.py`）。本形状的口径：

  * **官方正文**＝判决**切片件**的纯文本——取件口径**直接复用**
    `factscribe_legal/lines.py:539-570` 的 `_it_case_receipts`：run 的
    `index.json` 的 `judgments` 段里按 ECLI 对上，取 `slice_file` →
    `it_case_verify._itcase_plain`；
  * **卡所钉正文**＝卡内嵌的官方正文段（取件端点截到 600 字，
    `tools/fetch_corpus.py:1814`；截断记号「…」在定位前剥掉，见
    `adapters/card_receipts.py` 的 `strip_truncation`）；
  * **how**＝该线**由值推出**（`factscribe_legal/lines.py:539-570` 用
    `receipts.classify_how(value)`）⇒ 对正文文本取值＝`contains`；值取不到
    ⇒ `classify_how` 自己给「—」（与收据五元组同一个缺省标记）。

切片件取不到 ⇒ 退回卡内嵌正文（同 `lines.py` 的兜底顺序）；两处都没有 ⇒
span / face / how 全「—」（**我们还没接**：仓外批量件没取到）。
"""
from .. import receipts
from ..it_case_verify import _itcase_plain
from .base import (FIELD_ASOF, FIELD_CANONICAL_ID, FIELD_DECIDED_ON,
                   FIELD_EFFECTIVE_FROM, FIELD_EFFECTIVE_TO, FIELD_FACE,
                   FIELD_HOW, FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   FIELD_SPAN, FIELD_STATUS, FIELD_STATUS_SOURCE,
                   JURISDICTION_IT, KIND_CASE, ContractFieldMissing,
                   card_stem, load_json, read_card_fields)
from .card_receipts import embedded_text, project, run_index, slice_text
from .status import iso_date, iso_date_dmy


def _span_face_how(source, fields, index=None):
    """意大利判例：卡级五元组后三位（span / face / how）→ 三元组。

    口径逐条写在模块 docstring 的「第 4 步的五元组后三位」一节里。
    """
    judgments = run_index(source, index).get("judgments") or {}
    ecli = (fields.get("ECLI") or "").strip()
    meta = {}
    for key, item in judgments.items():
        item = item or {}
        if ecli and (item.get("ecli") or "") != ecli and key != ecli:
            continue
        meta = item
        break
    text = slice_text(source, meta, _slice_reader)
    value = embedded_text(source)
    if not text:
        # 切片件取不到 ⇒ 退回卡内嵌正文（同 lines.py 的兜底顺序）
        text = value
    return project(value, text, how=receipts.classify_how(value))


def _slice_reader(raw):
    """切片件的纯文本（`factscribe_legal/it_case_verify.py` 的 `_itcase_plain`；
    `factscribe_legal/lines.py:539-570` 同一套：它**吃字节**不喂字符串）。"""
    return _itcase_plain(raw)


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

    span, face, how = _span_face_how(source, fields, index)

    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: ecli,
            FIELD_CANONICAL_ID: "—",      # v0 统一填「—」（映射表 §1）
            FIELD_EFFECTIVE_FROM: "—",    # 判例无生效区间
            FIELD_EFFECTIVE_TO: "—",
            FIELD_STATUS: "—",            # 本线不产 status（三态不适用）
            FIELD_ASOF: "—",              # 没有 status ⇒ 没有判定锚点
            FIELD_DECIDED_ON: decided_on or "—",
            FIELD_STATUS_SOURCE: "—",
            FIELD_SPAN: span,
            FIELD_FACE: face,
            FIELD_HOW: how}
