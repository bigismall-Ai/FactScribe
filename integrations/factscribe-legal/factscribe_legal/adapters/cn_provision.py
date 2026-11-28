# -*- coding: utf-8 -*-
"""中国法规卡 → 统一契约字段（读侧派生，不改卡）。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §3（中国法规）
  · `BBBS` → `local_id`：**直映**，原样保留（国家法律法规数据库版本标识）；
  · 形状 → `kind=provision`、`jurisdiction=cn`：**转换**。中国侧一张卡
    ＝一部法规（**法规级**不是条文级，官方详情 JSON 不含条文正文，
    见 `factscribe_legal/cn_corpus.py:4-10`）⇒ 归 provision。

第 3 步的时点字段（status / asof / effective_from / effective_to / status_source）
--------------------------------------------------------------------------
**status：`SXX` 状态标志的枚举映射**（枚举含义见
`factscribe_legal/cn_verify.py:91-93`：1 废止 / 2 修改 / 3 有效 / 4 未生效；
时点表 §2.2 已定口径）：

    3（现行有效）⇒ `in_force`
    1（已废止）  ⇒ `repealed`
    4（尚未生效）⇒ `unknown`   （未来才生效，与法国 `date_debut>ref` 同构）
    2（已修改）  ⇒ `unknown`   （「已修改」不足以证明今天还在适用）
    缺失/其余    ⇒ `unknown`

  枚举本体**复用**仓里已有的跨域归一层 `factscribe_legal/timeliness.py`
  （`CN_SXX_STATE`，`timeliness.py:81-86`；入口
  `from_status_flag`，`:164-176`），本模块只做
  **归一层闭集 → 契约三态**的压平（`adapters/status.py` 的
  `from_timeliness_state`），**不另写一套枚举**。

  ⚠️ **关键区分**：「挑代表版本时的排序」与「这条今天算不算有效」是两件事。
  `factscribe_legal/cn_corpus.py:56-63` 的 `_prefer`（`{3:3, 2:2, 4:1, 1:0}`）
  管的是「同题多条里挑哪条当代表」，**排序保持不动**；本模块只管有效无效。
  现行闸 `cn_verify.py:89-93`（`sxx != 3` ⇒ 红牌）**保持不动**——
  它答「这条能不能引」（红线），status 答「今天算不算有效」（描述）。
  ⇒ 统一层落 `unknown` **不比现行闸宽松**（unknown ≠ 在效）。

  * `effective_from` ＝ 卡上 `SXRQ`（施行日＝生效起；映射表 §3 直映）。
  ⚠️ `GBRQ`（公布日）**不是**生效日，不进 `effective_from`（时点表 §2.2）。
  * `effective_to` ＝ 「—」：官方详情只给 `sxrq`，**不给失效日**
  （时点表 §2.2 盲区）⇒ 不许拿 status 反推日期（时点表 §3.4）。
  * `asof` ＝ **中国 `asof`（时点锚点）已定**：中国侧卡片本身不记参考日 ⇒
    `asof` 取**全库目录** `corpus/cn/catalog.jsonl.gz` 里该卡 `local_id`
    （=`BBBS`）对应条目的 `fetched_at` 的**日期部分**（UTC 截断；实读
    `2026-11-16T04:58:11Z` ⇒ `2026-11-16`）。理由：`sxx` 是**官方全库快照
    那一刻**的状态标志，锚点就是快照日（同法国 `POOL_ASOF`／西班牙
    `REFERENCE_DATE`／意大利 `FETCH_VIGENZA` 一类锚点）。
    **这不是跨卡推断**——经的是卡片自带的 `local_id`（BBBS）这把键，直连它
    自己的目录条目。目录缺该 BBBS 或目录不可得 ⇒ 填「—」。
    落地见本模块的 `_asof_from_index`。

第 4 步的五元组后三位（span / face / how）
----------------------------------------
**取值不另立一套定义**：直接用 `factscribe_legal/receipts.py` 的共用生产逻辑
与 `factscribe_legal/lines.py` 的七线适配点（卡粒度的投影口径见
`adapters/card_receipts.py`）。本形状的口径：

  * **官方数据里没有这个概念**：官方详情 JSON **不含条文正文**——中国侧一张
    卡＝一部法规（**法规级不是条文级**，`factscribe_legal/cn_corpus.py:4-10`；
    `factscribe_legal/lines.py:22-38` 的 cn 行）⇒ **span / face 缺省**，
    与 `factscribe_legal/lines.py:348-359` 的 `_cn_receipts` 同一口径；
  * **how**＝`catalog`（目录树·详情元数据对账）——本线是**核验方式常量**
    的一条（`factscribe_legal/lines.py:348-359` 硬编码 `catalog`）。

⇒ 三位里只有 **how** 取得到；span / face 一律「—」（缺省标记与收据五元组
同一个，`factscribe_legal/receipts.py:34`）。
"""
from ..cn_corpus import load_catalog
from ..timeliness import from_status_flag
from .base import (FIELD_ASOF, FIELD_CANONICAL_ID, FIELD_DECIDED_ON,
                   FIELD_EFFECTIVE_FROM, FIELD_EFFECTIVE_TO, FIELD_FACE,
                   FIELD_HOW, FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   FIELD_SPAN, FIELD_STATUS, FIELD_STATUS_SOURCE,
                   JURISDICTION_CN, KIND_PROVISION, ContractFieldMissing,
                   MISSING, read_card_fields)
from .status import from_timeliness_state, iso_date

SHAPE = "cn_provision"
KIND = KIND_PROVISION
JURISDICTION = JURISDICTION_CN
CARD_SUFFIX = ".cn.card.txt"


def load_index(catalog_path):
    """读中国全库目录（`catalog.jsonl.gz`）→ {bbbs: record}。"""
    return load_catalog(catalog_path)


def adapt(source, index=None, reference_date=None):
    """source：中国法规证据卡路径；index：全库目录 {bbbs: record}（可空）。

    reference_date：参考日（可空）——中国侧的 `SXX` 是官方**当前状态标志**，
    与参考日无关（本模块不拿参考日判 status），故本形不消费该入参。
    """
    fields = read_card_fields(source)
    local_id = fields.get("BBBS", "").strip()
    if not local_id:
        # 兜底：卡上没有 BBBS 行时，用卡上的法规名到全库目录里反查版本标识。
        local_id = _bbbs_from_index(index, fields)
    if not local_id:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID, "卡上没有 BBBS 行")

    sxx = (fields.get("SXX") or "").strip()
    # 枚举复用归一层（timeliness.CN_SXX_STATE），本模块只做闭集压平
    state = from_status_flag("cn", KIND, local_id, sxx, "")["state"]
    status = from_timeliness_state(state)

    span, face, how = _span_face_how()

    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: local_id,
            FIELD_CANONICAL_ID: "—",      # v0 统一填「—」（映射表 §1）
            FIELD_EFFECTIVE_FROM: iso_date(fields.get("SXRQ")) or "—",
            FIELD_EFFECTIVE_TO: "—",      # 官方不给失效日（时点表 §2.2）
            FIELD_STATUS: status,
            FIELD_ASOF: _asof_from_index(index, local_id),
            FIELD_DECIDED_ON: "—",        # 仅 kind=case 有效
            FIELD_STATUS_SOURCE: ("cn:sxx=%s" % sxx) if sxx else "cn:sxx",
            FIELD_SPAN: span,
            FIELD_FACE: face,
            FIELD_HOW: how}


def _span_face_how():
    """中国法规：卡级五元组后三位（span / face / how）→ 三元组。

    口径逐条写在模块 docstring 的「第 4 步的五元组后三位」一节里。
    """
    # 官方详情 JSON 无条文正文 ⇒ span/face 缺省；how＝目录对账（常量）
    return MISSING, MISSING, "catalog"


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


def _asof_from_index(index, local_id):
    """asof ＝ 官方全库快照日（全库目录记录 `fetched_at` 的日期）。

    `sxx` 说的是「官方全库快照那一刻的状态」，锚点就是这个快照日。
    取不到（全库目录没给或没有这条记录）⇒ 填「—」。
    """
    if not index:
        return "—"
    rec = index.get(local_id) or {}
    stamp = str((rec or {}).get("fetched_at") or "").strip()
    return iso_date(stamp[:10]) or "—"
