# -*- coding: utf-8 -*-
"""统一契约第 3 步：**status 三态**与**asof（时点）**的共用件。

三态（枚举名以契约草案 `docs/legal-card-contract-draft.md` §2.2 为准）
--------------------------------------------------------------------
    in_force   参考日当天现行有效
    repealed   参考日当天不现行有效（已废止、已被新版本取代且新版本已生效等）
    unknown    查了但下不了结论

**三态之外一律填「—」**（＝`factscribe_legal/receipts.py` 的 `MISSING`，
与收据五元组同一个缺省标记，不新造标记形状）——但「—」只用于
**这条线根本不产 status** 的情形（例如判例线：判决作出即固定，
没有「效力」这个维度，见时点表 §2.6）。**取不到判定 ⇒ `unknown`，
不是「—」**：`unknown` 的定义就是「查了但下不了结论」。

缺省标记
--------
本模块的缺省只有一个：**「—」**（`receipts.MISSING`）。asof 取不到任何
官方时点就填它；effective_from/effective_to/decided_on 同理。

判据归属（不可改）
------------------
统一层只定**三态的名字、缺省与字段名**；**判据全部在各国 adapter**，
各国特有断言（中国 sxx 枚举、西班牙 BOE 效力标志、法国生效区间、
意大利取件口径、CCNL 到期日）留在各国——这是契约草案 §1.3「第三步」
与时点表 §3.3 的分工，本模块不许出现「一个通用有效性公式」。

跨域归一层的复用
----------------
仓里已有一层时效归一：`factscribe_legal/timeliness.py`（接口层归一，
判定器内部不动）。它的闭集比契约三态**更细**（多出 `scheduled`、
`amended`、`not_yet_effective`、`version_gap`、`historical`、
`not_applicable`），本模块只做**闭集 → 契约三态**的压平，
压平规则逐条写在下表（**这是第 3 步已拍板的口径**）：

    in_force           ⇒ in_force
    repealed           ⇒ repealed
    scheduled          ⇒ unknown   （未来才生效；与法国 date_debut>ref 同构）
    not_yet_effective  ⇒ unknown   （尚未生效；与中国 sxx=4 同构）
    amended            ⇒ unknown   （已修改不足以证明今天还在适用）
    version_gap        ⇒ unknown   （版本与参考日不一致，不是效力结论）
    historical         ⇒ unknown   （只有裁判日期，无版本时效语义）
    not_applicable     ⇒ unknown
    unknown            ⇒ unknown

⚠️ 关键：**`scheduled`（未来才生效）压成 `unknown` 而不是 `repealed`**
——统一三态里「未来才生效」和「下不了结论」只能都落 `unknown`，
法国侧 `date_debut > ref` 与中国侧 `sxx=4` 走的是同一支。
这样**统一层不比现行闸宽松**（`unknown` 不等于在效），红线语义不被悄悄放宽。
"""
import re

from ..receipts import MISSING  # noqa: F401  （缺省标记统一是「—」，不新造形状）

__all__ = [
    "STATUS_IN_FORCE", "STATUS_REPEALED", "STATUS_UNKNOWN", "STATUSES",
    "STATUS_NA", "TIMELINESS_STATE_MAP", "from_timeliness_state",
    "iso_date", "iso_date_dmy", "MISSING",
]

# ---- 三态（枚举名与契约草案 §2.2 逐字一致）----
STATUS_IN_FORCE = "in_force"
STATUS_REPEALED = "repealed"
STATUS_UNKNOWN = "unknown"

# 三态的值域：只有这三个（＋「—」表示这条线不产 status）
STATUSES = (STATUS_IN_FORCE, STATUS_REPEALED, STATUS_UNKNOWN)

# 「这条线根本不产 status」时的缺省（与 asof/effective_* 的缺省同一个标记）
STATUS_NA = MISSING

# ---- 归一层闭集 → 契约三态（压平规则见模块 docstring）----
TIMELINESS_STATE_MAP = {
    "in_force": STATUS_IN_FORCE,
    "repealed": STATUS_REPEALED,
    "scheduled": STATUS_UNKNOWN,
    "not_yet_effective": STATUS_UNKNOWN,
    "amended": STATUS_UNKNOWN,
    "version_gap": STATUS_UNKNOWN,
    "historical": STATUS_UNKNOWN,
    "not_applicable": STATUS_UNKNOWN,
    "unknown": STATUS_UNKNOWN,
}


def from_timeliness_state(state):
    """归一层的 state 串 → 契约三态（认不出的落 unknown，不落「—」）。"""
    return TIMELINESS_STATE_MAP.get(str(state or "").strip(), STATUS_UNKNOWN)


# ---- 日期归一（各国官方日期写法不一：ISO／紧凑 YYYYMMDD／点斜杠）----

_ISO_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_DMY_RE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")


def iso_date(raw):
    """把官方日期写法归一成 ISO（`YYYY-MM-DD`）；认不出返回空串。

    认得的写法：
      * `2017-05-07`（ISO，法国 DATE_DEBUT/DATE_FIN、中国 SXRQ）；
      * `20161002`（紧凑 YYYYMMDD，西班牙 `fecha_vigencia`、
        意大利 `FETCH_VIGENZA`）；
      * `2016/10/02`、`2016.10.02`（点斜杠分隔的 Y-M-D）。
    """
    s = str(raw or "").strip()
    if not s:
        return ""
    if len(s) == 8 and s.isdigit():
        return "%s-%s-%s" % (s[0:4], s[4:6], s[6:8])
    m = _ISO_RE.match(s)
    if m:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    return ""


def iso_date_dmy(raw):
    """把 `DD/MM/YYYY` 写法归一成 ISO（意大利判例 `DATA_DECISIONE`）。

    实读 `corpus/it-case/run-20261116-itcase-1956_1980/
    ECLI-IT-COST-1956-1.itcase.card.txt:9` 是 `05/06/1956`，
    同卡 `:10` 的 `DATA_DECISIONE_ISO` 已是 `1956-06-05`。
    """
    s = str(raw or "").strip()
    if not s:
        return ""
    m = _DMY_RE.match(s)
    if not m:
        return iso_date(s)
    return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
