# -*- coding: utf-8 -*-
"""意大利集体协议（CCNL）清单 → 统一契约字段（读侧派生）。

**单独形状**：CNNL 这套**不是卡片**——无 `.card.txt`、无官方件副本、无正文，
引用单位是「协议 § 条款／附件／等级表」而不是条文号（草案 §2.4、
映射表 §8）⇒ `kind=agreement`，不塞进法条模板。

映射依据：`integrations/factscribe-legal/docs/legal-card-contract-mapping.md` §8（意大利集体协议）
  · `code`（CNEL 簇码，如 `A011`）→ `local_id`：**直映**，原样保留；
  · 形状 → `kind=agreement`、`jurisdiction=it`：**转换**。

本轮只产三个字段。`status`（到期日 ≠ 失效日）属第 3 步，见
`integrations/factscribe-legal/docs/legal-card-contract-time-model.md` §2.5。
"""
import csv
import json

from .base import (FIELD_JURISDICTION, FIELD_KIND, FIELD_LOCAL_ID,
                   JURISDICTION_IT, KIND_AGREEMENT, ContractFieldMissing)

SHAPE = "it_agreement"
KIND = KIND_AGREEMENT
JURISDICTION = JURISDICTION_IT


def read_inventory(path):
    """读 `it-inventory-vigenti.tsv` → 行 dict 列表（首行表头，制表符分隔）。"""
    rows = []
    with open(str(path), encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = None
        for cells in reader:
            if not cells or not any(c.strip() for c in cells):
                continue
            if header is None:
                header = [c.strip() for c in cells]
                continue
            rows.append(dict(zip(header, [c.strip() for c in cells])))
    return rows


def load_index(path):
    """读 `it-clusters.json` → dict。"""
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def adapt(source, index=None):
    """source：清单行 dict（键＝表头名）；index：it-clusters.json（可空）。"""
    if not isinstance(source, dict):
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID,
                                   "集体协议不是卡片，source 必须是清单行")
    code = str(source.get("code") or "").strip()
    if not code and index:
        # 兜底：用协议全称到 clusters.json 里反查簇码。
        title = str(source.get("title") or "").strip()
        for cluster in (index.get("clusters") or []):
            if str((cluster or {}).get("title") or "").strip() == title:
                code = str(cluster.get("code") or "").strip()
                break
    if not code:
        raise ContractFieldMissing(SHAPE, FIELD_LOCAL_ID, "清单行没有 code 列")
    return {FIELD_KIND: KIND,
            FIELD_JURISDICTION: JURISDICTION,
            FIELD_LOCAL_ID: code}
