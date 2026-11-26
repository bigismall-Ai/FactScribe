# -*- coding: utf-8 -*-
"""legal 判定码表（冻结）的**机读副本**——`codes` 通道的数据源。

权威源是本包 README 的「码表（冻结）」节（`LEGAL_/CN_/CASE_/IT_/ES/
FR_CASE/ITCASE_` 各域一前缀，只增不改名不改义不改 severity）。本件把那
张表抄成机读数据，供只读接口层的 `codes` 通道直接吐。

纪律
----
* **本件与 README 必须逐条一致**：`tests/test_api.py` 里有一条测试把两边
  对表（码名集合、严重度、逐条不多不少）。改了一边忘了另一边 ⇒ 测试红。
* 码名只增不改：**新增码必须同时改本件与 README**（并按仓内既有做法在
  CHANGELOG 里记一笔）。
* 中文短名是**接口层的展示名**（供工作台按名字渲染），不是判定语义；
  判定语义仍以 README 冻结表与各闸实现为准。
* 严重度只有两档：`red`（必须修）／`yellow`（声明·补正后可绿）。

域前缀与闸的对应（`domain` 字段）
------------------------------------
    fr      法国法条        verify
    cn      中国法规        verify-cn
    case    中国案例        verify-case
    it      意大利法条      verify-it
    es      西班牙法条      verify-es
    fr-case 法国判例        verify-fr-case
    it-case 意大利宪法法院判例  verify-it-case
    slot    核验槽挂槽层    （五闸之外的三个挂槽码）
"""

__all__ = ["CODES", "CODE_FIELDS", "as_dicts", "by_code", "counts", "domains"]

CODE_FIELDS = ("code", "severity", "label", "domain", "gate")

# (码名, 严重度, 中文短名, 域, 闸)
CODES = (
    # ---- fr：法国法条（verify）----
    ("LEGAL_PROV_UNKNOWN", "red", "法条不在语料里", "fr", "verify"),
    ("LEGAL_PROV_NOT_IN_FORCE", "red", "参考日当天不生效", "fr", "verify"),
    ("LEGAL_PROV_HASH_MISMATCH", "red", "官方字节被改过", "fr", "verify"),
    ("LEGAL_CARD_NO_HASH", "red", "证据卡缺哈希声明", "fr", "verify"),
    ("LEGAL_CARD_SHA256_MISMATCH", "red", "证据卡自身被改过", "fr", "verify"),
    ("LEGAL_QUOTE_MISMATCH", "red", "值不在法条正文里", "fr", "verify"),
    ("LEGAL_PROV_SCHEDULED", "yellow", "引的是待生效版本", "fr", "verify"),
    ("LEGAL_PROV_REPEALED", "yellow", "引的是已废止版本", "fr", "verify"),
    ("LEGAL_PROV_VIEW_MISMATCH", "yellow", "语料版不是现行视图", "fr", "verify"),
    ("LEGAL_PROV_AMBIGUOUS", "yellow", "参考日多版本并存", "fr", "verify"),
    ("LEGAL_COVERAGE_GAP", "yellow", "语料覆盖有缺口", "fr", "verify"),
    # ---- cn：中国法规（verify-cn）----
    ("CN_CARD_MISSING", "red", "证据卡缺失", "cn", "verify-cn"),
    ("CN_PROV_UNKNOWN", "red", "法规不在目录里", "cn", "verify-cn"),
    ("CN_CARD_NO_HASH", "red", "证据卡缺哈希声明", "cn", "verify-cn"),
    ("CN_OFFICIAL_HASH_MISMATCH", "red", "官方详情被改过", "cn", "verify-cn"),
    ("CN_CARD_SHA256_MISMATCH", "red", "证据卡自身被改过", "cn", "verify-cn"),
    ("CN_PROV_NOT_IN_FORCE", "red", "参考日不现行有效", "cn", "verify-cn"),
    ("CN_VALUE_MISMATCH", "red", "值与官方条文不符", "cn", "verify-cn"),
    ("CN_ARTICLE_NOT_FOUND", "red", "条文号找不到", "cn", "verify-cn"),
    # ---- case：中国案例（verify-case）----
    ("CASE_CARD_MISSING", "red", "证据卡缺失", "case", "verify-case"),
    ("CASE_OFFICIAL_MISSING", "red", "官方正文缺失", "case", "verify-case"),
    ("CASE_OFFICIAL_HASH_MISMATCH", "red", "官方正文被改过", "case", "verify-case"),
    ("CASE_VALUE_NOT_IN_OFFICIAL", "red", "值不在官方正文里", "case", "verify-case"),
    ("CASE_AMOUNT_MISMATCH", "red", "金额与官方不符", "case", "verify-case"),
    ("CASE_CARD_TEXT_DIVERGED", "red", "卡内正文分叉", "case", "verify-case"),
    ("CASE_NO_MISMATCH", "red", "案号与官方不符", "case", "verify-case"),
    ("CASE_DATE_MISMATCH", "red", "裁判日期不符", "case", "verify-case"),
    ("CASE_CHAIN_BROKEN", "red", "证据链断了一跳", "case", "verify-case"),
    # ---- it：意大利法条（verify-it）----
    ("IT_SOURCE_HASH_MISMATCH", "red", "整件哈希不符", "it", "verify-it"),
    ("IT_CARD_MISSING", "red", "证据卡缺失", "it", "verify-it"),
    ("IT_CARD_NO_HASH", "red", "证据卡缺哈希声明", "it", "verify-it"),
    ("IT_PROV_UNKNOWN", "red", "条文不在整件里", "it", "verify-it"),
    ("IT_ARTICLE_HASH_MISMATCH", "red", "切片哈希不符", "it", "verify-it"),
    ("IT_ARTICLE_NOT_IN_SOURCE", "red", "切片不属于该件", "it", "verify-it"),
    ("IT_CARD_FIELD_MISMATCH", "red", "卡字段与索引不符", "it", "verify-it"),
    ("IT_CARD_SHA256_MISMATCH", "red", "证据卡自身被改过", "it", "verify-it"),
    ("IT_QUOTE_MISMATCH", "red", "值不在条文里", "it", "verify-it"),
    ("IT_VERSION_GAP", "yellow", "版本基准落后参考日", "it", "verify-it"),
    # ---- es：西班牙法条（verify-es）----
    ("ES_SOURCE_HASH_MISMATCH", "red", "整件哈希不符", "es", "verify-es"),
    ("ES_CARD_MISSING", "red", "证据卡缺失", "es", "verify-es"),
    ("ES_CARD_NO_HASH", "red", "证据卡缺哈希声明", "es", "verify-es"),
    ("ES_PROV_UNKNOWN", "red", "条文不在整件里", "es", "verify-es"),
    ("ES_ARTICLE_HASH_MISMATCH", "red", "切片哈希不符", "es", "verify-es"),
    ("ES_ARTICLE_NOT_IN_SOURCE", "red", "切片不属于该件", "es", "verify-es"),
    ("ES_CARD_FIELD_MISMATCH", "red", "卡字段与索引不符", "es", "verify-es"),
    ("ES_CARD_SHA256_MISMATCH", "red", "证据卡自身被改过", "es", "verify-es"),
    ("ES_QUOTE_MISMATCH", "red", "值不在条文里", "es", "verify-es"),
    ("ES_VERSION_GAP", "yellow", "版本基准落后参考日", "es", "verify-es"),
    # ---- fr-case：法国判例（verify-fr-case）----
    ("FR_CASE_CARD_MISSING", "red", "证据卡缺失", "fr-case", "verify-fr-case"),
    ("FR_CASE_OFFICIAL_MISSING", "red", "官方判决缺失", "fr-case", "verify-fr-case"),
    ("FR_CASE_CARD_NO_HASH", "red", "证据卡缺哈希声明", "fr-case", "verify-fr-case"),
    ("FR_CASE_OFFICIAL_HASH_MISMATCH", "red", "官方字节被改过", "fr-case", "verify-fr-case"),
    ("FR_CASE_CARD_SHA256_MISMATCH", "red", "证据卡自身被改过", "fr-case", "verify-fr-case"),
    ("FR_CASE_VALUE_NOT_IN_OFFICIAL", "red", "值不在官方正文里", "fr-case", "verify-fr-case"),
    ("FR_CASE_NO_MISMATCH", "red", "案号与官方不符", "fr-case", "verify-fr-case"),
    ("FR_CASE_DATE_MISMATCH", "red", "裁判日期不符", "fr-case", "verify-fr-case"),
    ("FR_CASE_CARD_TEXT_DIVERGED", "red", "卡内正文分叉", "fr-case", "verify-fr-case"),
    # ---- it-case：意大利宪法法院判例（verify-it-case）----
    ("ITCASE_CARD_MISSING", "red", "证据卡缺失", "it-case", "verify-it-case"),
    ("ITCASE_CARD_NO_HASH", "red", "证据卡缺哈希声明", "it-case", "verify-it-case"),
    ("ITCASE_PROV_UNKNOWN", "red", "判决不在索引里", "it-case", "verify-it-case"),
    ("ITCASE_SLICE_HASH_MISMATCH", "red", "切片哈希不符", "it-case", "verify-it-case"),
    ("ITCASE_CARD_SHA256_MISMATCH", "red", "证据卡自身被改过", "it-case", "verify-it-case"),
    ("ITCASE_CARD_FIELD_MISMATCH", "red", "卡字段与索引不符", "it-case", "verify-it-case"),
    ("ITCASE_CARD_TEXT_DIVERGED", "red", "卡内正文分叉", "it-case", "verify-it-case"),
    ("ITCASE_VALUE_NOT_IN_OFFICIAL", "red", "值不在官方正文里", "it-case", "verify-it-case"),
    ("ITCASE_NO_MISMATCH", "red", "案号与官方不符", "it-case", "verify-it-case"),
    ("ITCASE_DATE_MISMATCH", "red", "裁判日期不符", "it-case", "verify-it-case"),
    # ---- slot：核验槽挂槽层（五闸之外）----
    ("LEGAL_DATE_INVALID", "red", "参考日缺失或非法", "slot", "核验槽挂槽"),
    ("LEGAL_EVIDENCE_CHANGED", "red", "语料证据已变更", "slot", "核验槽挂槽"),
    ("LEGAL_EVIDENCE_UNFROZEN", "yellow", "锁已解冻未重冻", "slot", "核验槽挂槽"),
)


def as_dicts():
    """码表 → 逐条字典（`codes` 通道的形状）。"""
    return [{"code": c, "severity": s, "label": lb, "domain": d, "gate": g}
            for c, s, lb, d, g in CODES]


def by_code():
    """码名 → 字典（查单条码用）。"""
    return {c: {"code": c, "severity": s, "label": lb, "domain": d, "gate": g}
            for c, s, lb, d, g in CODES}


def counts():
    """按严重度计数（形如 {"red": n, "yellow": m, "total": n+m}）。"""
    out = {"red": 0, "yellow": 0, "total": len(CODES)}
    for _c, sev, _lb, _d, _g in CODES:
        if sev in out:
            out[sev] += 1
    return out


def domains():
    """码表里出现过的域（按首次出现顺序）。"""
    seen = []
    for _c, _s, _lb, d, _g in CODES:
        if d not in seen:
            seen.append(d)
    return seen
