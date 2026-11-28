# -*- coding: utf-8 -*-
"""统一法律卡片契约的**公共层 adapter**（第 1、2 步）。

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

本轮只产 `kind` / `jurisdiction` / `local_id` 三个字段——它们在六种形状里
**全是直映**，零转换、零歧义（映射表 §2-§8）。

读路径（有视图 / 没视图都吃）
---------------------------
`adapt()` 同时兼容两种情况：
  * **有公共层视图**（`view=` 给了，或用 `load_view()` 读出来的字典）：
    直接取视图里的字段；
  * **只有旧卡**：现场从旧卡推导。
⇒ 公共层坏了删掉重算即可，不污染数据（草案 §2.1）。

TODO（第 3、4 步 · 待用户拍板，本轮**不自行决定**）
----------------------------------------------------
1. **中国 `SXX=2`（修改）**落 `in_force` 还是 `unknown`：两处现有口径相反
   （`factscribe_legal/cn_verify.py:89-93` 判红 vs
   `factscribe_legal/cn_corpus.py:56-63` 把 2 排在废止之上）。
   口径见 `integrations/factscribe-legal/docs/legal-card-contract-time-model.md` §2.2。TODO 落在
   `cn_provision.py`。
2. **西班牙 `estado_consolidacion`** 不能当废止标志（三个法全是
   `"Finalizado"` 而它们今天都现行有效）。口径见
   `integrations/factscribe-legal/docs/legal-card-contract-time-model.md` §2.3。TODO 落在
   `es_provision.py`。
3. **五元组**（`span`/`face`/`how`）在非法国判例闸是**补产**还是统一填
   「—」：口径见 `integrations/factscribe-legal/docs/legal-card-contract-draft.md` §1.3「第四步」与
   映射表 §9.2 规律三。
   ⚠️ 现状提示（不替用户拍板，只报事实）：本仓已有**共用**的五元组生产逻辑
   ——`factscribe_legal/receipts.py`（`build_receipt`、缺省标记统一为「—」）
   与 `factscribe_legal/lines.py`（七条线各自的适配点，产出同构的五元组）。
   ⇒ 真正待定的是「统一契约的 `span`/`face`/`how` 与收据五元组怎么对齐」，
   而不是「有没有五元组」。拍板后在本模块补契约字段。
"""
from . import (base, cn_provision, es_provision, fr_case, fr_provision,
               it_agreement, it_case, it_provision)
from .base import (CARD_CONTRACT_VERSION, FIELDS, FIELD_JURISDICTION,
                   FIELD_KIND, FIELD_LOCAL_ID, JURISDICTIONS, KINDS,
                   KIND_AGREEMENT, KIND_CASE, KIND_PROVISION, MISSING,
                   ContractFieldMissing, load_view, read_card_fields,
                   view_key, view_record)

__all__ = [
    "CARD_CONTRACT_VERSION", "MISSING", "FIELDS",
    "FIELD_KIND", "FIELD_JURISDICTION", "FIELD_LOCAL_ID",
    "KIND_PROVISION", "KIND_CASE", "KIND_AGREEMENT", "KINDS",
    "JURISDICTIONS", "ContractFieldMissing",
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


def adapt(shape, source, index=None, view=None, corpus_root=None):
    """统一读路径：视图里有就取视图里的，没有就现场从旧卡推导。

    * shape：形状 id（见 `ADAPTERS` 的键）；
    * source：证据卡路径（`it_agreement` 形状则是清单行 dict）；
    * index：同形状的 index / catalog / clusters（可空）；
    * view：公共层视图 {键: 记录}（可空，用 `load_view()` 读出来）；
    * corpus_root：视图键的相对根（可空）。

    返回的字典**只有** `kind` / `jurisdiction` / `local_id` 三个键
    （本轮第 1、2 步的口径）。
    """
    module = ADAPTERS.get(shape)
    if module is None:
        raise KeyError("未知形状：%s（已知：%s）"
                       % (shape, "、".join(SHAPES)))
    rec = _view_record(shape, source, view, corpus_root)
    if rec is None:
        return module.adapt(source, index=index)
    fields = {}
    for name in FIELDS:
        value = str(rec.get(name) or "").strip()
        fields[name] = value if value else MISSING
    if all(fields[name] != MISSING for name in FIELDS):
        return fields
    # 视图缺字段 ⇒ 现场从旧卡补齐（视图是缓存，不是唯一真相）
    derived = module.adapt(source, index=index)
    for name in FIELDS:
        if fields[name] == MISSING:
            fields[name] = derived[name]
    return fields


def adapt_shape(shape, source, index=None):
    """只从旧卡推导（不查视图）——公共层视图不存在时的现场路径。"""
    return adapt(shape, source, index=index)


def _view_record(shape, source, view, corpus_root):
    if not view:
        return None
    if shape == it_agreement.SHAPE:
        code = str((source or {}).get("code") or "").strip()
        return view.get("it_agreement:%s" % code) if code else None
    if not isinstance(source, str):
        return None
    return view.get(view_key(source, corpus_root))
