# -*- coding: utf-8 -*-
"""统一法律卡片契约（v0 草案）公共层的**共用件**。

下文简称的三份文档（仓内路径）：
  * 草案 ＝ `integrations/factscribe-legal/docs/legal-card-contract-draft.md`
  * 映射表＝ `integrations/factscribe-legal/docs/legal-card-contract-mapping.md`
  * 时点表＝ `integrations/factscribe-legal/docs/legal-card-contract-time-model.md`
}

定位（三条，不可改）
--------------------
1. **加在前面的公共层**，不是替换层：各国原有卡片一个字段都不删；现有卡片
   继续是事实账钉哈希的对象（`factscribe_legal/verify.py:157-160` 的
   `LEGAL_CARD_SHA256_MISMATCH`、`factscribe_legal/cn_verify.py:83-86`、
   `factscribe_legal/es_verify.py:155-163` 等处依赖这一点）。
   ⚠️ 口径（勿再误读）：**卡是事实账钉哈希的对象，重排语料后需重钉**——
   重算一遍 sha256、重写事实账即可，**不是「重排就回不来」**。
   真正不可行的只有「拉平各国官方格式」：那些字段在官方数据里就不存在
   （草案 §1.2）。
2. **只读派生**：本层不写任何语料文件；公共层坏了删掉重算即可，不污染数据
   （草案 §2.1）。
3. **判定不动**：现有各闸的红黄码逐字不变（回归锁：
   `tests/test_contract_gates_regression.py`，基线在公共层落地**前**捕获）。

第 1、2 步落三个零歧义字段：`kind` / `jurisdiction` / `local_id`。
这三个字段在六种语料形状里全是直映（映射表 §2-§8）⇒ 零转换、零歧义。

第 3 步（已落）落**时点字段**：`status`（三态）、`asof`、`status_source`、
`effective_from` / `effective_to`、`decided_on`，外加 `canonical_id`
（v0 统一填「—」，映射表 §1）。**三态的枚举名与字段名逐字照抄契约草案
§2.2**（`in_force` / `repealed` / `unknown`；三态之外填「—」）。
**判据全部在各国 adapter**（契约草案 §1.3「第三步」），本层只定名字与缺省，
共用件见 `adapters/status.py`。

第 4 步（**已落**）落**收据五元组的后三位**：`span` / `face` / `how`。
取值**不另立一套定义**——直接用仓里已有的共用生产逻辑
`factscribe_legal/receipts.py`（`build_receipt` / `span_in_text` /
`classify_how`，缺省标记 `MISSING`）与 `factscribe_legal/lines.py` 的七线
适配点（`lines.py:22-38`）。事实级收据是**按事实**产出、统一契约是
**按卡**产出，卡粒度的投影口径见 `adapters/card_receipts.py` 的 docstring；
各形状的「材料在哪」判据仍在各国 adapter（`_span_face_how`）。

与既有模块的分工
----------------
* `factscribe_legal.corpus`：件清单扫描（域／件型／时效的**展示面**）；
* `factscribe_legal.timeliness`：时效字段的跨域归一（**判定面**）；
* `factscribe_legal.receipts`：收据五元组的共用生产逻辑；
* 本包：**统一契约字段**的派生面——只回答「这是什么件、在哪个法域、它自己
  的号是多少」。三条面互不覆盖，也不互相改写。
"""
import json
import os

# 缺省标记与收据五元组**同一个**（不新造标记形状；草案 §2.2 与
# factscribe_legal/receipts.py 的 MISSING 同为 "—"）。
from ..receipts import MISSING  # noqa: F401

__all__ = [
    "CARD_CONTRACT_VERSION", "MISSING",
    "KIND_PROVISION", "KIND_CASE", "KIND_AGREEMENT", "KINDS",
    "JURISDICTION_FR", "JURISDICTION_CN", "JURISDICTION_ES",
    "JURISDICTION_IT", "JURISDICTIONS",
    "FIELD_KIND", "FIELD_JURISDICTION", "FIELD_LOCAL_ID",
    "FIELD_CANONICAL_ID", "FIELD_EFFECTIVE_FROM", "FIELD_EFFECTIVE_TO",
    "FIELD_STATUS", "FIELD_ASOF", "FIELD_DECIDED_ON", "FIELD_STATUS_SOURCE",
    "FIELD_SPAN", "FIELD_FACE", "FIELD_HOW",
    "FIELDS",
    "ContractFieldMissing", "parse_card_fields", "read_card_fields",
    "load_json", "card_stem", "view_key", "load_view", "view_record",
]

# 统一契约版本（0.1 ＝ 第 1、2 步的三个字段；0.2 ＝ 第 3 步的时点字段
# ＋ 第 4 步的五元组后三位；加了字段再升版）
CARD_CONTRACT_VERSION = "factscribe-legal-card/0.2"

# ---- 证据类型（契约 §2.2 的 kind）----
KIND_PROVISION = "provision"   # 法条／法规
KIND_CASE = "case"             # 判例
KIND_AGREEMENT = "agreement"   # 集体协议（单独形状，不塞进法条模板）
KINDS = (KIND_PROVISION, KIND_CASE, KIND_AGREEMENT)

# ---- 法域（契约 §2.2 的 jurisdiction）----
JURISDICTION_FR = "fr"
JURISDICTION_CN = "cn"
JURISDICTION_ES = "es"
JURISDICTION_IT = "it"
JURISDICTIONS = (JURISDICTION_FR, JURISDICTION_CN, JURISDICTION_ES,
                 JURISDICTION_IT)

# ---- 字段名（契约 §2.2；**逐字照抄契约草案的字段名**，不另造）----
FIELD_KIND = "kind"
FIELD_JURISDICTION = "jurisdiction"
FIELD_LOCAL_ID = "local_id"
FIELD_CANONICAL_ID = "canonical_id"
FIELD_EFFECTIVE_FROM = "effective_from"
FIELD_EFFECTIVE_TO = "effective_to"
FIELD_STATUS = "status"
FIELD_ASOF = "asof"
FIELD_DECIDED_ON = "decided_on"
FIELD_STATUS_SOURCE = "status_source"

# 第 4 步：收据五元组的后三位（契约草案 §2.2；逐字照抄，不另造字段名）
FIELD_SPAN = "span"
FIELD_FACE = "face"
FIELD_HOW = "how"

# 第 1、2 步的三个直映字段 ＋ 第 3 步的时点字段（status/asof 及其配套）
# ＋ 第 4 步的五元组后三位（span/face/how）。
# ⚠️ instrument/provision_no/text_sha256/official_ref/source_* 等契约字段属
#    后续步，本轮不落。
FIELDS = (FIELD_KIND, FIELD_JURISDICTION, FIELD_LOCAL_ID,
          FIELD_CANONICAL_ID, FIELD_EFFECTIVE_FROM, FIELD_EFFECTIVE_TO,
          FIELD_STATUS, FIELD_ASOF, FIELD_DECIDED_ON, FIELD_STATUS_SOURCE,
          FIELD_SPAN, FIELD_FACE, FIELD_HOW)

# 卡片正文段的起始标记：解析卡头字段时到此为止（正文里也有冒号，不能混进去）
CARD_TEXT_MARKER = "--- OFFICIAL TEXT ---"


class ContractFieldMissing(ValueError):
    """契约必填字段取不到（kind / jurisdiction / local_id 任一）。

    本层 fail-closed：宁可报错，也不把空值或占位值混进统一层
    （与现有各闸 fail-closed 的口径一致，草案 §2.5 通用校验第 3 条）。
    """

    def __init__(self, shape, field, detail=""):
        self.shape = shape
        self.field = field
        super().__init__("统一契约字段取不到：形状 %s 的 %s%s"
                         % (shape, field, ("（%s）" % detail) if detail else ""))


def parse_card_fields(card_text):
    """解析卡片头部的 `KEY: VALUE` 行（遇 `--- OFFICIAL TEXT ---` 停）。

    与 `factscribe_legal/corpus.py` 的 `_card_fields` 同一口径：
    跳过 `#` 注释行，按**第一个冒号**切（值里还有冒号，例如 URL）。
    """
    out = {}
    for line in str(card_text or "").splitlines():
        if line.startswith(CARD_TEXT_MARKER):
            break
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


def read_card_fields(path):
    """读一张证据卡的头部字段。"""
    with open(str(path), encoding="utf-8") as fh:
        return parse_card_fields(fh.read())


def load_json(path):
    """读一个 JSON 文件（index / clusters 等）→ dict。"""
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def card_stem(path, suffix):
    """卡文件名去掉形状后缀后的主干（如 `a1.es.card.txt` → `a1`）。"""
    name = os.path.basename(str(path))
    if suffix and name.endswith(suffix):
        return name[:-len(suffix)]
    return os.path.splitext(name)[0]


# ---------------------------------------------------------------------------
# 公共层视图（读侧派生缓存，可随时重建、可丢弃）
# ---------------------------------------------------------------------------

def view_key(source, corpus_root=None):
    """视图记录的键：卡片相对语料根的 POSIX 路径。

    语料根没给时用绝对路径（同一台机器内仍唯一）。
    """
    path = os.path.abspath(str(source))
    if corpus_root:
        root = os.path.abspath(str(corpus_root))
        try:
            path = os.path.relpath(path, root)
        except ValueError:      # 跨盘（Windows）时 relpath 会抛
            pass
    return path.replace(os.sep, "/")


def load_view(path):
    """读公共层视图（JSONL，一行一张卡的契约字段）→ {键: 记录}。

    视图是**派生缓存**：有就用，没有就现场从旧卡推导（统一层不依赖它）。
    """
    out = {}
    if not path or not os.path.exists(str(path)):
        return out
    with open(str(path), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            key = str(rec.get("card") or "").strip()
            if key:
                out[key] = rec
    return out


def view_record(shape, card_rel, fields):
    """造一条视图记录（写视图时用；字段取不齐的填缺省标记）。"""
    rec = {"card": str(card_rel), "shape": str(shape)}
    for name in FIELDS:
        rec[name] = fields.get(name) or MISSING
    return rec
