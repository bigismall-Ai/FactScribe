# -*- coding: utf-8 -*-
"""西班牙法条卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §4（西班牙法条）
  · `ACT_ID` ＋ `BLOCK_ID` → `local_id`：**直映**，复合形式，原样保留
    （草案 §2.3 允许复合，如 `BOE-A-2015-10565/a1`）；
  · 形状 → `kind=provision`、`jurisdiction=es`：**转换**。

第 3 步的时点字段（status / asof / effective_from / effective_to / status_source）
--------------------------------------------------------------------------
**绝对不用 `estado_consolidacion` 判 status**（已定口径，时点表 §2.3）：
实读三个 run 全是 `"Finalizado"`（`corpus/es/*/index.json` 顶层），
而这三个法（1978 宪法、39/2015、40/2015）今天全部现行有效——BOE 语义里
`Finalizado` 指「合并文本的**编纂流程**已结束」，不是「该法已废止」；
拿它判会把三个现行有效的法全判成已失效。
⚠️ 本模块**连读都不读这个字段**（见 `_read_boe_meta` 的白名单），
从机制上杜绝误用。

status 改从「**官方是否仍提供现行合并文本**」判定（时点表 §2.3 已定口径），
信号取**官方整件** `official/act.xml` 的 `<metadatos>` 段（BOE 开放数据
自带的件级效力标志）：

  * `estatus_derogacion`＝`S` ⇒ 官方已标明该法**已废止** ⇒ `repealed`；
  * `estatus_anulacion`＝`S` ⇒ 官方已标明**已撤销** ⇒ `repealed`；
  * `vigencia_agotada`＝`S` ⇒ **效力已耗尽**（已被后续规范取代）⇒ `repealed`；
  * 三个标志皆非 `S`（实读三个 run 全是 `N`，见
    `corpus/es/run-20261116-es-ley39-2015-procedimiento-administrativo/official/act.xml:21-23`）
    ⇒ 官方仍在提供现行合并文本 ⇒ `in_force`；
  * `fecha_vigencia`（生效日）> 参考日 ⇒ 尚未生效 ⇒ `unknown`；
  * 官方整件取不到 / 标志读不出 ⇒ 判不出 ⇒ `unknown`（不猜）。

  ⚠️ 这三个标志**在官方整件里、但没进 `index.json`**（采集器未抽这三个键）
  ⇒ 要实证 `repealed` 支，得先补采集侧。

  * `effective_from` ＝ `fecha_vigencia`（官方 `<fecha_vigencia>`，
    实读 `official/act.xml:20`＝`20161002`；取不到退回 run 的
    `index.json` 顶层同名字段；再取不到填「—」）。
  * `effective_to` ＝ 「—」：合并文本**没有终止日**（时点表 §3.4）。
  * `asof` ＝ 卡上 `REFERENCE_DATE`（取件参考日＝「取件那天的官方现行
    合并文本」，映射表 §4 直映）；没有则退回 `FETCH_DATE`。
  ⚠️ 两个日期别混用（`factscribe_legal/es_verify.py:186-188`）：
  `version_date`（合并文本自身最后更新日）**不是**「这一版何时生效」，
  **不进** `effective_from`。

第 4 步的五元组后三位（span / face / how）
----------------------------------------
**取值不另立一套定义**：直接用 `factscribe_legal/receipts.py` 的共用生产逻辑
与 `factscribe_legal/lines.py` 的七线适配点（卡粒度的投影口径见
`adapters/card_receipts.py`）。本形状的口径：

  * **官方正文**＝条文块**切片件**的纯文本——取件口径**直接复用**
    `factscribe_legal/lines.py:451-480` 的 `_es_receipts`：run 的
    `index.json` 的 `articles[BLOCK_ID].article_file` → `es_verify._plain_text`；
  * **卡所钉正文**＝卡内嵌的官方正文段（取件端点截到 600 字，
    `tools/fetch_corpus.py:1427`；截断记号「…」在定位前剥掉，见
    `adapters/card_receipts.py` 的 `strip_truncation`）；
  * **how**＝逐字（`contains`）——本线是**核验方式常量**的一条
    （`factscribe_legal/lines.py:451-480` 硬编码 `contains`）。

切片件取不到 ⇒ 退回卡内嵌正文（同 `lines.py` 的兜底顺序）；两处都没有 ⇒
span / face「—」（**我们还没接**：仓外批量件没取到）。
"""
import os
import xml.etree.ElementTree as ET

from ..es_verify import _plain_text as _es_plain_text
from .base import (FIELD_ASOF, FIELD_CANONICAL_ID, FIELD_DECIDED_ON,
                   FIELD_EFFECTIVE_FROM, FIELD_EFFECTIVE_TO, FIELD_FACE,
                   FIELD_HOW, FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   FIELD_SPAN, FIELD_STATUS, FIELD_STATUS_SOURCE,
                   JURISDICTION_ES, KIND_PROVISION, ContractFieldMissing,
                   card_stem, load_json, read_card_fields)
from .card_receipts import embedded_text, project, run_index, slice_text
from .status import STATUS_IN_FORCE, STATUS_REPEALED, STATUS_UNKNOWN, iso_date

SHAPE = "es_provision"
KIND = KIND_PROVISION
JURISDICTION = JURISDICTION_ES
CARD_SUFFIX = ".es.card.txt"

# 官方整件里**只读这些标签**：效力标志 + 时点标签。
# ⚠️ 故意**不含** `estado_consolidacion`（编纂流程状态，不能判效力）。
BOE_META_TAGS = ("estatus_derogacion", "estatus_anulacion", "vigencia_agotada",
                 "fecha_vigencia", "fecha_publicacion", "fecha_disposicion")

# 效力标志的中文说明（写进 status_source 的取值里，便于反查）
BOE_FLAG_LABELS = {
    "estatus_derogacion": "已废止",
    "estatus_anulacion": "已撤销",
    "vigencia_agotada": "效力已耗尽",
}


def load_index(path):
    """读西班牙 run 的 `index.json` → dict（卡上缺字段时的兜底用）。"""
    return load_json(path)


def adapt(source, index=None, reference_date=None):
    """source：西班牙法条证据卡路径；index：run 的 index.json（可空）。

    reference_date：参考日（可空）——没传则用卡上 `REFERENCE_DATE`（取件参考日）。
    """
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

    meta = _read_boe_meta(_official_path(source, fields))
    span, face, how = _span_face_how(source, fields, index)
    index = index if isinstance(index, dict) else {}

    # 生效日：官方整件优先，退回 run 的 index.json 顶层同名字段
    fecha_vigencia = iso_date(meta.get("fecha_vigencia")) or \
        iso_date(index.get("fecha_vigencia"))
    ref = str(reference_date or "").strip() \
        or (fields.get("REFERENCE_DATE") or "").strip() \
        or (fields.get("FETCH_DATE") or "").strip() \
        or str(index.get("fetch_reference_date") or "").strip()

    status, status_source = _judge(meta, fecha_vigencia, ref)

    asof = iso_date(fields.get("REFERENCE_DATE")) \
        or iso_date(fields.get("FETCH_DATE")) \
        or iso_date(index.get("fetch_reference_date")) or "—"

    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: "%s/%s" % (act_id, block_id),
            FIELD_CANONICAL_ID: "—",      # v0 统一填「—」（映射表 §1）
            FIELD_EFFECTIVE_FROM: fecha_vigencia or "—",
            FIELD_EFFECTIVE_TO: "—",      # 合并文本没有终止日（时点表 §3.4）
            FIELD_STATUS: status,
            FIELD_ASOF: asof,
            FIELD_DECIDED_ON: "—",        # 仅 kind=case 有效
            FIELD_STATUS_SOURCE: status_source,
            FIELD_SPAN: span,
            FIELD_FACE: face,
            FIELD_HOW: how}


def _span_face_how(source, fields, index=None):
    """西班牙法条：卡级五元组后三位（span / face / how）→ 三元组。

    口径逐条写在模块 docstring 的「第 4 步的五元组后三位」一节里。
    """
    meta = (run_index(source, index).get("articles") or {}).get(
        (fields.get("BLOCK_ID") or "").strip()) or {}
    text = slice_text(source, meta, _slice_reader)
    value = embedded_text(source)
    if not text:
        # 切片件取不到 ⇒ 退回卡内嵌正文（同 lines.py 的兜底顺序）
        text = value
    return project(value, text, how="contains")


def _slice_reader(raw):
    """切片件的纯文本（`factscribe_legal/es_verify.py` 的 `_plain_text`；
    `factscribe_legal/lines.py:451-480` 同一套解码方式）。"""
    return _es_plain_text(raw.decode("utf-8", "replace"))


def _judge(meta, fecha_vigencia, ref):
    """判 status 三态。返回 (status, status_source)。

    判据：官方整件是否仍提供现行合并文本（BOE 的件级效力标志）
    ＋ 生效日与参考日的先后。
    """
    if not meta:
        # 官方整件取不到 ⇒ 判不出「官方是否仍提供现行合并文本」⇒ unknown
        return STATUS_UNKNOWN, "es:boe_consolidated"
    for tag in ("estatus_derogacion", "estatus_anulacion", "vigencia_agotada"):
        value = str(meta.get(tag) or "").strip().upper()
        if value == "S":
            return STATUS_REPEALED, "es:boe_%s=S" % tag
    if not fecha_vigencia:
        return STATUS_UNKNOWN, "es:fecha_vigencia"
    if ref and fecha_vigencia > ref:
        # 尚未生效（与法国 date_debut>ref、中国 sxx=4 同构）⇒ unknown
        return STATUS_UNKNOWN, "es:fecha_vigencia@%s" % ref
    return STATUS_IN_FORCE, ("es:fecha_vigencia@%s" % ref) if ref else "es:fecha_vigencia"


def _official_path(source, fields):
    """官方整件路径：卡上 `SOURCE_FILE`（相对 run 目录）。"""
    rel = (fields.get("SOURCE_FILE") or "").strip()
    if not rel:
        return ""
    return os.path.join(os.path.dirname(os.path.abspath(str(source))), rel)


def _read_boe_meta(path):
    """读官方整件 `<metadatos>` 段里的时点/效力标签 → {标签: 文本}。

    只读 `BOE_META_TAGS` 白名单里的标签：**`estado_consolidacion` 不在
    白名单**（它是编纂流程状态，不能判效力，时点表 §2.3）。
    """
    if not path or not os.path.exists(str(path)):
        return {}
    try:
        root = ET.parse(str(path)).getroot()
    except (ET.ParseError, OSError, ValueError):
        return {}
    wanted = set(BOE_META_TAGS)
    out = {}
    for el in root.iter():
        tag = str(el.tag).split("}")[-1]
        if tag in wanted and tag not in out:
            text = str(el.text or "").strip()
            if text:
                out[tag] = text
    return out
