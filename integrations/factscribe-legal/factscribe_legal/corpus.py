# -*- coding: utf-8 -*-
"""语料**件清单**扫描（只反映真实可见的件，不编造）。

本件只做一件事：把一个语料视图目录里**真实存在的**官方件逐件列出来，
每件附上它的域、件型、真实元数据、以及**归一后的时效字段**。

两种目录形态都认
----------------
1. **打包形态**（本仓 `corpus/`）：
       fr/index.json          法国法条（provisions）
       fr-case/<run>/index.json  法国判例（cases）
       cn/cards/*.cn.card.txt    中国法规（卡上钉的详情哈希与 sxx）
       it/<run>/index.json       意大利法条（articles）
       es/<run>/index.json       西班牙法条（articles）
       it-case/<run>/index.json  意大利宪法法院判例（judgments）
2. **项目语料视图形态**（`[checks.legal] corpus` 指的那份）：
       index.json             法国法条（provisions）——放在**根**上
       es/index.json          西班牙法条
       it/index.json          意大利法条
       catalog.jsonl.gz       中国全库目录（只列卡，不扫全库）

件口径
------
* 「件」＝一份官方件（一条法条／一个判决／一部法规／一个条文切片）。
* 仓内可见件 = FR 法条 3 ＋ FR 判例 4 ＋ CN 法规 2 ＋ IT 切片 4
  ＋ ES 切片 9 ＋ IT 判例 2（CN 案例 0 件：案例材料在项目 runs/ 里，不在语料视图）。
* **看不到就不列**：扫描不到的件不出现在清单里（不占位、不编造）。

本件只读、零 LLM、零网络、不写盘。
"""
import json
import os

from . import timeliness as tl

__all__ = ["scan_corpus", "scan_all_roots", "item_fields"]

ITEM_FIELDS = ("id", "country", "domain", "kind", "title", "path", "gate",
               "meta", "timeliness")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _card_fields(path):
    """证据卡头部的 `KEY: value` 字段（遇 '--- OFFICIAL TEXT ---' 停）。"""
    out = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("--- OFFICIAL TEXT ---"):
                    break
                if ":" not in line or line.startswith("#"):
                    continue
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def _run_dirs(root, sub):
    """<root>/<sub> 下所有含 index.json 的目录（含 <root>/<sub> 本身）。"""
    base = os.path.join(root, sub)
    if not os.path.isdir(base):
        return []
    out = []
    if os.path.isfile(os.path.join(base, "index.json")):
        out.append(base)
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, "index.json")):
            out.append(d)
    return out


def _item(item_id, country, domain, kind, title, path, gate, meta,
          timeliness_obj):
    return {
        "id": str(item_id or ""),
        "country": str(country or ""),
        "domain": str(domain or ""),
        "kind": str(kind or ""),
        "title": str(title or ""),
        "path": str(path or ""),
        "gate": str(gate or ""),
        "meta": meta or {},
        "timeliness": timeliness_obj,
    }


def _scan_fr(root, index_dir, rel_prefix, items):
    idx = _read_json(os.path.join(index_dir, "index.json")) or {}
    for num, meta in (idx.get("provisions") or {}).items():
        xml_file = meta.get("xml_file") or ("%s.xml" % num)
        rel = os.path.join(rel_prefix, xml_file) if rel_prefix else xml_file
        items.append(_item(
            num, "法国", "fr", "法条", meta.get("code_title") or "", rel,
            "verify",
            {"etat": meta.get("etat", ""),
             "date_debut": meta.get("date_debut", ""),
             "date_fin": meta.get("date_fin", ""),
             "legiarti": meta.get("legiarti", ""),
             "code_id": meta.get("code_id", ""),
             "xml_file": xml_file,
             "pool_asof": idx.get("pool_asof", "")},
            tl.from_interval(
                "fr", "法条", num, meta.get("date_debut", ""),
                meta.get("date_fin", ""), "",
                "法国法条：版本区间完整（date_debut / date_fin），"
                "是七条线里唯一能回答「参考日当天是否生效」的结构。")))


def _scan_fr_case(root, run_dir, rel_prefix, items):
    idx = _read_json(os.path.join(run_dir, "index.json")) or {}
    for cid, meta in (idx.get("cases") or {}).items():
        txt_file = meta.get("txt_file") or ("official/%s.txt" % cid)
        rel = os.path.join(rel_prefix, txt_file)
        items.append(_item(
            cid, "法国", "fr-case", "判例", meta.get("titre") or "", rel,
            "verify-fr-case",
            {"date_dec": meta.get("date_dec", ""),
             "juridiction": meta.get("juridiction", ""),
             "nature": meta.get("nature", ""),
             "solution": meta.get("solution", ""),
             "numeros_affaires": meta.get("numeros_affaires", []),
             "card_file": meta.get("card_file", ""),
             "txt_file": txt_file,
             "xml_file": meta.get("xml_file", ""),
             "txt_sha256": meta.get("txt_sha256", ""),
             "xml_sha256": meta.get("xml_sha256", "")},
            tl.from_decision_date(
                "fr-case", "判例", cid, meta.get("date_dec", ""), "",
                "FR 判例是历史件，卡里只有 DATE_DEC / JUDGE_DATE，"
                "没有版本时效语义。")))


def _scan_cn_cards(root, items):
    base = os.path.join(root, "cn", "cards")
    if not os.path.isdir(base):
        base = os.path.join(root, "cn")
        if not os.path.isdir(base):
            return
    for name in sorted(os.listdir(base)):
        if not name.endswith(".cn.card.txt"):
            continue
        path = os.path.join(base, name)
        f = _card_fields(path)
        title = f.get("TITLE") or name[:-len(".cn.card.txt")]
        items.append(_item(
            title, "中国", "cn", "法规", title,
            os.path.relpath(path, root), "verify-cn",
            {"bbbs": f.get("BBBS", ""),
             "sxx": f.get("SXX", ""),
             "gbrq": f.get("GBRQ", ""),
             "sxrq": f.get("SXRQ", ""),
             "flxz": f.get("FLXZ", ""),
             "zdjg": f.get("ZDJG", ""),
             "detail_sha256": f.get("OFFICIAL_DETAIL_SHA256", ""),
             "card_file": name},
            tl.from_status_flag(
                "cn", "法规", title, f.get("SXX", ""), "",
                "中国侧只有 sxx（1废止/2修改/3有效/4未生效），"
                "没有版本区间，回答不了「参考日当天是否有效」。")))


def _scan_it_es(root, sub, country, domain, gate, items):
    for run_dir in _run_dirs(root, sub):
        idx = _read_json(os.path.join(run_dir, "index.json")) or {}
        rel_prefix = os.path.relpath(run_dir, root)
        act_title = idx.get("act_title") or ""
        for aid, meta in (idx.get("articles") or {}).items():
            art_file = meta.get("article_file") or ""
            rel = os.path.join(rel_prefix, art_file) if art_file else rel_prefix
            items.append(_item(
                aid, country, domain, "法条", act_title, rel, gate,
                {"act_id": idx.get("act_id", "") or idx.get("act_urn", ""),
                 "act_title": act_title,
                 "act_eli": idx.get("act_eli", ""),
                 "version_date": idx.get("version_date", ""),
                 "num": meta.get("num", ""),
                 "card_file": meta.get("card_file", ""),
                 "article_file": art_file,
                 "text_chars": meta.get("text_chars", "")},
                tl.from_version_stamp(
                    domain, "法条", aid, idx.get("version_date", ""), "",
                    "%s法条：官方给的是「某个日期的时点版本」"
                    "（version_date），与参考日不一致时是黄不是红。"
                    % country)))


def _scan_it_case(root, items):
    for run_dir in _run_dirs(root, "it-case"):
        idx = _read_json(os.path.join(run_dir, "index.json")) or {}
        rel_prefix = os.path.relpath(run_dir, root)
        for jid, meta in (idx.get("judgments") or {}).items():
            slice_file = meta.get("slice_file") or ""
            rel = os.path.join(rel_prefix, slice_file) if slice_file else rel_prefix
            items.append(_item(
                jid, "意大利", "it-case", "判例",
                meta.get("ecli") or jid, rel, "verify-it-case",
                {"ecli": meta.get("ecli", ""),
                 "anno": meta.get("anno", ""),
                 "numero": meta.get("numero", ""),
                 "data_decisione": meta.get("data_decisione", ""),
                 "data_deposito": meta.get("data_deposito", ""),
                 "slice_file": slice_file,
                 "card_file": meta.get("card_file", ""),
                 "text_chars": meta.get("text_chars", "")},
                tl.from_decision_date(
                    "it-case", "判例", jid, meta.get("data_decisione", ""), "",
                    "意大利宪法法院判例是历史件：只有裁判日期，"
                    "没有版本时效语义。")))


def scan_corpus(root, reference_date=""):
    """扫一个语料视图目录 → 件清单（真实件；看不到的不列）。"""
    items = []
    if not root or not os.path.isdir(root):
        return items
    # 形态 2：FR 索引在根上
    if os.path.isfile(os.path.join(root, "index.json")):
        idx = _read_json(os.path.join(root, "index.json")) or {}
        if "provisions" in idx:
            _scan_fr(root, root, "", items)
    # 形态 1：FR 索引在 fr/ 下
    for d in _run_dirs(root, "fr"):
        _scan_fr(root, d, os.path.relpath(d, root), items)
    for d in _run_dirs(root, "fr-case"):
        _scan_fr_case(root, d, os.path.relpath(d, root), items)
    _scan_cn_cards(root, items)
    _scan_it_es(root, "it", "意大利", "it", "verify-it", items)
    _scan_it_es(root, "es", "西班牙", "es", "verify-es", items)
    _scan_it_case(root, items)
    # 参考日回填（时效判据要参考日；参考日未定则状态为 unknown）
    if reference_date:
        for it in items:
            it["timeliness"] = _with_reference(it["timeliness"], reference_date,
                                              it.get("meta") or {})
    return items


def scan_all_roots(roots, reference_date=""):
    """扫多个语料根 → 件清单（真实件；去重键含 path）。

    同名不同 run 是**不同的件**（去重键含 path：仓内 IT 切片 4 件里有两件
    都叫 art_2，分属两个 run）。
    """
    seen = set()
    items = []
    for root in list(roots or []):
        for it in scan_corpus(root, reference_date):
            key = (root, it.get("path"), it.get("domain"), it.get("id"))
            if key in seen:
                continue
            seen.add(key)
            item = dict(it)
            item["root"] = root
            items.append(item)
    return items


def _with_reference(obj, reference_date, meta=None):
    """给已归一的时效对象回填参考日（状态重算，形态不变）。"""
    if not obj:
        return obj
    meta = meta or {}
    src = obj.get("source")
    ref = str(reference_date or "")
    domain = obj.get("domain")
    kind = obj.get("kind")
    item_id = obj.get("item_id")
    # 回填前那遍是按「参考日未定」造的（note 里带着这句提示）；
    # 参考日定了以后它就是过期口径，抹掉再重算，免得 note 自相矛盾。
    note = tl.strip_hint(obj.get("note", ""))
    if src == "区间":
        return tl.from_interval(domain, kind, item_id,
                                obj.get("effective_from", ""),
                                obj.get("effective_to", ""), ref, note)
    if src == "状态标志":
        return tl.from_status_flag(domain, kind, item_id, meta.get("sxx", ""),
                                   ref, note)
    if src == "时点戳":
        return tl.from_version_stamp(domain, kind, item_id,
                                      obj.get("effective_from", ""), ref, note)
    if src == "日期":
        return tl.from_decision_date(domain, kind, item_id,
                                     obj.get("effective_from", ""), ref, note)
    return obj

