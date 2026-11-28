# -*- coding: utf-8 -*-
"""统一法律卡片契约的**公共层 adapter**（第 1、2、3 步）。

是什么
------
一个**加在前面的只读派生层**：输入＝现有卡片＋index（或 catalog/manifest），
输出＝统一契约字段字典。各国原有卡片一个字段都不删，现有卡片继续是事实账
钉哈希的对象（`factscribe_legal/verify.py:157-160` 等处依赖这一点）。

六个形状各一个 adapter（草案 §1.3「第一步」；形状清单见映射表 §2-§8）：

    形状              kind         jurisdiction  local_id 来源
    ----------------  -----------  ------------  -----------------------------
    fr_provision      provision    fr            NUM
    cn_provision      provision    cn            BBBS
    es_provision      provision    es            ACT_ID/BLOCK_ID
    it_provision      provision    it            ACT_URN/ARTICLE_EID
    it_case           case         it            ECLI
    fr_case           case         fr            CASE_ID
    it_agreement      agreement    it            code（CNEL 簇码）

第 1、2 步落的三个直映字段：`kind` / `jurisdiction` / `local_id`
——它们在六种形状里**全是直映**，零转换、零歧义（映射表 §2-§8）。

第 3 步（**已落**）落的时点字段：`status`（三态）、`asof`、
`status_source`、`effective_from` / `effective_to`、`decided_on`，
外加 `canonical_id`（v0 统一填「—」）。
**字段名与三态的枚举名逐字照抄契约草案 §2.2**
（`in_force` / `repealed` / `unknown`；三态之外填「—」）。

读路径（有视图 / 没视图都吃）
---------------------------
`adapt()` 同时兼容两种情况：
  * **有公共层视图**（`view=` 给了，或用 `load_view()` 读出来的字典）：
    直接取视图里的字段；
  * **只有旧卡**：现场从旧卡推导。
⇒ 公共层坏了删掉重算即可，不污染数据（草案 §2.1）。

判据归属（**不可改**）
----------------------
统一层只定**三态的名字、缺省与字段名**；**判据全部在各国 adapter**
（草案 §1.3「第三步」）。已定口径（2026-11-28 用户拍板）：

1. **中国 `SXX` 的 status 判定**：`3` ⇒ `in_force`；`1`（已废止）⇒ `repealed`；
   `4`（尚未生效）⇒ `unknown`；`2`（已修改）⇒ `unknown`
   （「已修改」不足以证明今天还在适用）。枚举含义见
   `factscribe_legal/cn_verify.py:91-93`，现行闸 `sxx != 3` 判红
   （`factscribe_legal/cn_verify.py:89-93`）**保持不动**。
   ⚠️ 关键区分：`factscribe_legal/cn_corpus.py:56-63` 的 `_prefer`（`3>2>4>1`）
   管的是「同题多条挑哪条当代表」，**排序保持不动**；status 只管有效无效，
   两者不冲突。落地在 `cn_provision.py`。
2. **西班牙 status**：**不用 `estado_consolidacion`**（三个法全是 `"Finalizado"`
   而它们今天都现行有效，拿它判必错）。改从「官方是否仍提供现行合并文本」判定，
   信号取官方整件 `official/act.xml` 的件级效力标志
   （`estatus_derogacion` / `estatus_anulacion` / `vigencia_agotada`），
   判不出落 `unknown`。⚠️ 两个日期别混用（`factscribe_legal/es_verify.py:189-196`）：
   `fetch_reference_date`（取件参考日）可比，`version_date`（合并文本自身最后更新日）
   不是「这一版何时生效」。落地在 `es_provision.py`。
3. **法国 status**：**复用闸里的判定，不另写一套**
   （`factscribe_legal/provisions.py:100-115` 的 `in_force_at` /
   `scheduled_at` / `repealed_at`）。落地在 `fr_provision.py`。
4. **意大利法条 status**：官方 AKN 无生效区间 ⇒ 只能记**取件口径**的
   `in_force`（弱口径），用 `status_source` 标出不是官方效力判定。落地在
   `it_provision.py`。
5. **判例线（法国／意大利）不产 status** ⇒ 填「—」（判例没有「效力」这个
   时间维度，判决作出即固定；仓内也没有可判「是否仍可被引用」的字段）。
   判决日归 `decided_on`。落地在 `it_case.py` / `fr_case.py`。
6. **集体协议**：到期日 ≠ 失效日 ⇒ 过期落 `unknown`，**不落 `repealed`**。
   落地在 `it_agreement.py`。
7. **五元组**（`span`/`face`/`how`）：**直接与收据五元组对齐**——
   引用仓里已有的共用生产逻辑 `factscribe_legal/receipts.py`（`build_receipt`，
   缺省标记统一为「—」）与 `factscribe_legal/lines.py`（七条线各自的适配点，
   产出同构的五元组），取不到填「—」，**不另立一套定义**。落地在第 4 步。
"""
from . import (base, cn_provision, es_provision, fr_case, fr_provision,
               it_agreement, it_case, it_provision, status)
from .base import (CARD_CONTRACT_VERSION, FIELDS, FIELD_ASOF,
                   FIELD_CANONICAL_ID, FIELD_DECIDED_ON, FIELD_EFFECTIVE_FROM,
                   FIELD_EFFECTIVE_TO, FIELD_JURISDICTION, FIELD_KIND,
                   FIELD_LOCAL_ID, FIELD_STATUS, FIELD_STATUS_SOURCE,
                   JURISDICTIONS, KINDS, KIND_AGREEMENT, KIND_CASE,
                   KIND_PROVISION, MISSING, ContractFieldMissing, load_view,
                   read_card_fields, view_key, view_record)
from .status import (STATUS_IN_FORCE, STATUS_NA, STATUS_REPEALED,  # noqa: F401
                     STATUS_UNKNOWN, STATUSES, from_timeliness_state, iso_date,
                     iso_date_dmy)

__all__ = [
    "CARD_CONTRACT_VERSION", "MISSING", "FIELDS",
    "FIELD_KIND", "FIELD_JURISDICTION", "FIELD_LOCAL_ID", "FIELD_CANONICAL_ID",
    "FIELD_EFFECTIVE_FROM", "FIELD_EFFECTIVE_TO", "FIELD_STATUS", "FIELD_ASOF",
    "FIELD_DECIDED_ON", "FIELD_STATUS_SOURCE",
    "KIND_PROVISION", "KIND_CASE", "KIND_AGREEMENT", "KINDS",
    "JURISDICTIONS", "ContractFieldMissing",
    "STATUS_IN_FORCE", "STATUS_REPEALED", "STATUS_UNKNOWN", "STATUSES",
    "STATUS_NA",
    "ADAPTERS", "SHAPES", "adapt", "adapt_shape", "load_view", "view_key",
    "view_record",
]

# 形状 → adapter 模块（每法域/类型一个）
ADAPTERS = {
    fr_provision.SHAPE: fr_provision,
    cn_provision.SHAPE: cn_provision,
    es_provision.SHAPE: es_provision,
    it_provision.SHAPE: it_provision,
    it_case.SHAPE: it_case,
    fr_case.SHAPE: fr_case,
    it_agreement.SHAPE: it_agreement,
}

SHAPES = tuple(sorted(ADAPTERS))


def adapt(shape, source, index=None, view=None, corpus_root=None,
          reference_date=None):
    """统一读路径：视图里有就取视图里的，没有就现场从旧卡推导。

    * shape：形状 id（见 `ADAPTERS` 的键）；
    * source：证据卡路径（`it_agreement` 形状则是清单行 dict）；
    * index：同形状的 index / catalog / clusters（可空）；
    * view：公共层视图 {键: 记录}（可空，用 `load_view()` 读出来）；
    * corpus_root：视图键的相对根（可空）；
    * reference_date：参考日（可空）——**status 判定的输入**
      （时点表 §3.1；各形状没传时用自己卡上的基准日兜底）。

    返回的字典是契约草案 §2.2 的字段集合（本轮：第 1、2 步的三个直映字段
    ＋ 第 3 步的时点字段）。
    """
    module = ADAPTERS.get(shape)
    if module is None:
        raise KeyError("未知形状：%s（已知：%s）"
                       % (shape, "、".join(SHAPES)))
    rec = _view_record(shape, source, view, corpus_root)
    if rec is None:
        return module.adapt(source, index=index, reference_date=reference_date)
    fields = {}
    for name in FIELDS:
        value = str(rec.get(name) or "").strip()
        fields[name] = value if value else MISSING
    if all(fields[name] != MISSING for name in FIELDS):
        return fields
    # 视图缺字段 ⇒ 现场从旧卡补齐（视图是缓存，不是唯一真相）
    derived = module.adapt(source, index=index, reference_date=reference_date)
    for name in FIELDS:
        if fields[name] == MISSING:
            fields[name] = derived[name]
    return fields


def adapt_shape(shape, source, index=None, reference_date=None):
    """只从旧卡推导（不查视图）——公共层视图不存在时的现场路径。"""
    return adapt(shape, source, index=index, reference_date=reference_date)


def _view_record(shape, source, view, corpus_root):
    if not view:
        return None
    if shape == it_agreement.SHAPE:
        code = str((source or {}).get("code") or "").strip()
        return view.get("it_agreement:%s" % code) if code else None
    if not isinstance(source, str):
        return None
    return view.get(view_key(source, corpus_root))
