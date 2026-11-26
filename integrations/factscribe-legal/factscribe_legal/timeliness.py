# -*- coding: utf-8 -*-
"""时效字段的**跨域统一映射层**（接口层归一；各域判定器内部不动）。

为什么要有这一层
------------------
七条线各自判时效的材料形态完全不同：

    fr      法国法条    生效**区间**（date_debut / date_fin）
    cn      中国法规    现行**状态标志**（sxx：1废止/2修改/3有效/4未生效）
    it      意大利法条  **时点版本戳**（version_date）
    es      西班牙法条  **时点版本戳**（version_date）
    fr-case 法国判例    **裁判日期**（date_dec；历史件，无版本时效语义）
    it-case 意大利判例  **裁判日期**（data_decisione；同上）
    case    中国案例    无时效材料（官方件是案例正文稿）

判定器**内部不动**（仍按各自现状判定、仍发各自的码、退出码语义不变）；
本层只在**接口层**把上面四种来源归一成**同一个时效字段形状**输出，
让跨域比较与后续扩线天然同构。

统一形状（每个条件一条）
------------------------
    {
      "domain":         域 id（fr/cn/it/es/fr-case/it-case/case）
      "kind":           件型（法条/法规/判例/案例）
      "item_id":        件 id（法条号／案号／ECLI…）
      "reference_date": 参考日（YYYY-MM-DD；空＝未定）
      "state":          时效状态（闭集，见 STATES）
      "state_label":    状态中文名
      "effective_from": 生效起（ISO；无则空串）
      "effective_to":   生效止（ISO；无则空串）
      "source":         来源形态（区间/状态标志/时点戳/日期/无）
      "source_fields":  来源字段名（逐条写清，便于反查）
      "note":           一句话口径说明
    }

状态闭集（`state`）
---------------------
    in_force          参考日当天生效／现行有效
    scheduled         已排期、参考日尚未生效
    repealed          参考日当天已废止
    amended           已修改（非现行有效）
    not_yet_effective 尚未生效
    version_gap       时点版本与参考日不一致（IT/ES 的黄码口径）
    historical        历史件（只有日期，无版本时效语义）
    unknown           材料里没有时效字段
    not_applicable    该域不适用时效
"""

__all__ = ["STATES", "STATE_LABELS", "SOURCES", "FIELDS", "HINT",
           "strip_hint", "from_interval", "from_status_flag",
           "from_version_stamp", "from_decision_date", "from_none"]

FIELDS = ("domain", "kind", "item_id", "reference_date", "state",
          "state_label", "effective_from", "effective_to", "source",
          "source_fields", "note")

STATE_LABELS = {
    "in_force": "参考日当天生效",
    "scheduled": "已排期、参考日尚未生效",
    "repealed": "参考日当天已废止",
    "amended": "已修改（非现行有效）",
    "not_yet_effective": "尚未生效",
    "version_gap": "时点版本与参考日不一致",
    "historical": "历史件（只有日期，无版本时效语义）",
    "unknown": "无时效字段",
    "not_applicable": "该域不适用时效",
}

STATES = tuple(sorted(STATE_LABELS))

# 四种来源形态（写进 `source` 与 `source_fields`，便于反查）
SOURCES = {
    "interval": ("区间", ("date_debut", "date_fin")),
    "status_flag": ("状态标志", ("sxx",)),
    "version_stamp": ("时点戳", ("version_date",)),
    "decision_date": ("日期", ("date_dec",)),
    "none": ("无", ()),
}

# 中国侧 sxx 状态标志 → 统一状态
CN_SXX_STATE = {
    1: "repealed",
    2: "amended",
    3: "in_force",
    4: "not_yet_effective",
}


HINT = "参考日未定（时效判据不跑）"


def strip_hint(note):
    """把「参考日未定」这句提示从口径说明里摘掉。

    参考日回填时用：件先按「参考日未定」造一遍（状态 unknown），
    之后拿到真实参考日要重算状态——那句提示是**当时**的口径；
    参考日定了以后还留着，note 就会和同一条里的 reference_date 字段
    自相矛盾（说「参考日未定」，字段却有值）。
    """
    text = str(note or "").strip()
    if HINT not in text:
        return text
    text = text.replace("；" + HINT, "")
    text = text.replace(HINT, "")
    return text.strip().rstrip("；").strip()


def _with_hint(note):
    """参考日未定时的口径说明：**保留域注释**，补一句「参考日未定」。

    （域注释是这条素材的口径说明，不许被参考日的状态覆盖掉。）
    """
    text = str(note or "").strip()
    if not text:
        return HINT
    if HINT in text:
        return text
    return text + "；" + HINT


def _shape(domain, kind, item_id, reference_date, state, source, note,
           effective_from="", effective_to=""):
    src_label, src_fields = SOURCES[source]
    return {
        "domain": str(domain or ""),
        "kind": str(kind or ""),
        "item_id": str(item_id or ""),
        "reference_date": str(reference_date or ""),
        "state": state,
        "state_label": STATE_LABELS.get(state, state),
        "effective_from": str(effective_from or ""),
        "effective_to": str(effective_to or ""),
        "source": src_label,
        "source_fields": list(src_fields),
        "note": str(note or ""),
    }


def from_interval(domain, kind, item_id, date_debut, date_fin,
                  reference_date, note=""):
    """法国法条：生效**区间** → 统一形状。

    区间口径照法国闸的现行判定（`date_debut <= 参考日 < date_fin` 算当天
    生效；`etat` 不参与——etat=VIGUEUR 的版本可能只是「未来才生效」）。
    """
    begin = str(date_debut or "").strip()
    end = str(date_fin or "").strip()
    ref = str(reference_date or "").strip()
    if not begin and not end:
        return _shape(domain, kind, item_id, ref, "unknown", "interval",
                      note or "语料里没有生效区间字段", "", "")
    if not ref:
        return _shape(domain, kind, item_id, ref, "unknown", "interval",
                      _with_hint(note), begin, end)
    if begin > ref:
        state = "scheduled"
    elif end and end <= ref:
        state = "repealed"
    else:
        state = "in_force"
    return _shape(domain, kind, item_id, ref, state, "interval", note, begin, end)


def from_status_flag(domain, kind, item_id, sxx, reference_date, note=""):
    """中国法规：现行**状态标志** → 统一形状。

    sxx：1废止 / 2修改 / 3有效 / 4未生效。中国侧官方件没有版本区间，
    回答不了「参考日当天是否有效」——这是官方发布形态决定的，不是缺口。
    """
    ref = str(reference_date or "").strip()
    try:
        flag = int(sxx)
    except (TypeError, ValueError):
        flag = None
    state = CN_SXX_STATE.get(flag, "unknown")
    return _shape(domain, kind, item_id, ref, state, "status_flag", note)


def from_version_stamp(domain, kind, item_id, version_date, reference_date,
                       note=""):
    """意大利／西班牙法条：**时点版本戳** → 统一形状。

    官方开放数据给的是「某个日期的时点版本」⇒ 与参考日不一致时是
    `version_gap`（黄码口径：参考日的版本没拿到，不是红）。
    """
    stamp = str(version_date or "").strip()
    ref = str(reference_date or "").strip()
    if not stamp:
        return _shape(domain, kind, item_id, ref, "unknown", "version_stamp",
                      note or "语料里没有版本戳字段")
    if not ref:
        return _shape(domain, kind, item_id, ref, "unknown", "version_stamp",
                      _with_hint(note), stamp, "")
    state = "in_force" if stamp == ref else "version_gap"
    return _shape(domain, kind, item_id, ref, state, "version_stamp", note,
                  stamp, "")


def from_decision_date(domain, kind, item_id, decision_date, reference_date,
                       note=""):
    """判例（法国／意大利）：**裁判日期** → 统一形状。

    判例是历史件：只有裁判日期，没有「版本区间」语义 ⇒ 一律 `historical`。
    """
    day = str(decision_date or "").strip()
    ref = str(reference_date or "").strip()
    if not day:
        return _shape(domain, kind, item_id, ref, "unknown", "decision_date",
                      note or "官方件里没有裁判日期字段")
    return _shape(domain, kind, item_id, ref, "historical", "decision_date",
                  note, day, "")


def from_none(domain, kind, item_id, reference_date, note=""):
    """该域无时效材料（中国案例）→ 统一形状。"""
    return _shape(domain, kind, item_id, reference_date, "not_applicable",
                  "none", note or "该域官方件不含时效材料")
