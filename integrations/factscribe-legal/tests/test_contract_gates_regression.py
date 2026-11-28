#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""六闸判定的**回归锁**：加了公共层，现有各闸的判定必须逐条一致。

为什么要有这把锁
----------------
统一契约的公共层（`factscribe_legal/adapters/`）是**加在前面的**只读派生层，
不是替换层：各国原有卡片一个字段都不删，现有卡片继续是事实账钉哈希的对象。
因此加了公共层之后，**现有各闸的红黄码必须逐字不变**——这把锁就是那件事的
唯一证据（口径见 `docs/legal-card-contract-draft.md` §1.3「第一步」）。

锁的形状
--------
1. 用**仓内真语料**（`corpus/` 下的真卡、真官方件）搭一个临时项目，事实账
   指向真卡。每闸都有两类事实：
     · 绿项：事实账钉的哈希＝卡的现算哈希（材料没被动过）；
     · 红项：事实账钉的哈希故意写错（⇒ 各闸的「卡自身被改」码）。
   参考日故意取在语料版本日（2026-11-16）之后 ⇒ 法/西/意三闸各出一条黄牌
   （覆盖差 / 版本差），确保这把锁不是「全绿空跑」。
2. 跑全部各闸，把每条 finding 归一成 {code, severity, location, message}，
   排序后落成 JSON 基线（`tests/fixtures/contract_adapters/gates-baseline.json`）。
3. 基线是**改造前**捕获的（公共层还不存在的那一版代码）；每次跑都逐条比对，
   有一条不一样就红。

重录基线（只有改了闸或改了夹具才做）：
    LEGAL_GATES_BASELINE_RECORD=1 python3 -m unittest discover -s integrations/factscribe-legal/tests -v

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from factscribe_legal.case_verify import verify_case  # noqa: E402
from factscribe_legal.cn_verify import verify_cn  # noqa: E402
from factscribe_legal.es_verify import verify_es  # noqa: E402
from factscribe_legal.fr_case_verify import verify_fr_case  # noqa: E402
from factscribe_legal.it_case_verify import verify_it_case  # noqa: E402
from factscribe_legal.it_verify import verify_it  # noqa: E402
from factscribe_legal.verify import verify as verify_fr  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.abspath(os.path.join(HERE, "..", "corpus"))
BASELINE = os.path.join(HERE, "fixtures", "contract_adapters",
                        "gates-baseline.json")

# 参考日故意晚于语料版本日（2026-11-16）⇒ 法/西/意三闸各出一条黄牌。
REFERENCE_DATE = "2026-11-20"

ES_RUN = "run-20261116-es-ley39-2015-procedimiento-administrativo"
IT_RUN = "run-20261116-it-1990n241"
ITCASE_RUN = "run-20261116-itcase-1956_1980"
FRCASE_RUN = "run-20261116-inca"

# 中国案例（legal-case 闸）的材料不在语料视图里，在项目 runs/ 下 ⇒ 这里造
# 一份最小真材料（正文与卡都自洽），让这把锁也覆盖第七道闸。
CN_CASE_SLUG = "张某诉某公司劳动争议案"
CN_CASE_SLUG_BAD = "张某诉某公司劳动争议案二审"
CN_CASE_RUN = "run-20261114-case"
CN_CASE_OFFICIAL = (
    "基本案情：张某于2020年1月入职某公司，2023年10月20日解除劳动合同。\n"
    "　　一、某宝销售公司支付张某违法解除劳动合同赔偿金146160元；\n"
    "　　重庆市第一中级人民法院于2023年10月20日作出（2023）渝01民终7708号民事判决。\n"
)
CN_CASE_FIELDS = {
    "CASE_NO": "（2023）渝01民终7708号",
    "JUDGE_DATE": "2023.10.20",
    "AMOUNTS": "146160",
}


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _facts_toml(facts):
    lines = ['schema = "paperkit-fact/3.0"', ""]
    for f in facts:
        lines += [
            "[[fact]]",
            'id = "%s"' % f["id"],
            'claim = "法律事实（回归夹具）"',
            'value = "%s"' % f["value"],
            'source = "%s"' % f["source"],
            'source_sha256 = "sha256:%s"' % f["sha"],
            'locator = "回归夹具"',
            'confidence = "high"',
            "derived_from = []",
            "",
        ]
    return "\n".join(lines)


def _stage_card(proj, corpus_rel, proj_rel):
    """把真卡拷进项目，返回 (项目内相对路径, 卡现算哈希)。"""
    src = os.path.join(CORPUS, corpus_rel)
    dst = os.path.join(proj, proj_rel)
    _copy(src, dst)
    return proj_rel, _sha256_file(dst)


def build_project(root):
    """搭一个临时项目：事实账指向**仓内真卡**（真官方件在语料侧）。"""
    proj = os.path.join(root, "proj")
    os.makedirs(os.path.join(proj, "facts"), exist_ok=True)
    bad_sha = "0" * 64
    groups = {}

    # ---- 法国法条（卡声明的官方 XML 哈希 vs 语料 XML 现算）----
    fr_rel, fr_sha = _stage_card(proj, "fr/L594-8.card.txt",
                                 "cards/fr/L594-8.card.txt")
    groups["fr"] = [
        {"id": "FR-GREEN", "value": "594", "source": fr_rel, "sha": fr_sha},
        {"id": "FR-TAMPERED", "value": "594", "source": fr_rel, "sha": bad_sha},
    ]

    # ---- 中国法规（卡声明的官方详情哈希 vs 全库目录）----
    cn_name = "中华人民共和国劳动合同法_2c909f.cn.card.txt"
    cn_rel, cn_sha = _stage_card(proj, "cn/cards/" + cn_name,
                                 "cards/cn/" + cn_name)
    groups["cn"] = [
        {"id": "CN-GREEN", "value": "2013-07-01", "source": cn_rel,
         "sha": cn_sha},
        {"id": "CN-TAMPERED", "value": "2013-07-01", "source": cn_rel,
         "sha": bad_sha},
    ]

    # ---- 西班牙法条（官方整件哈希 + 条文切片哈希）----
    es_rel, es_sha = _stage_card(proj, "es/" + ES_RUN + "/a1.es.card.txt",
                                 "cards/es/" + ES_RUN + "/a1.es.card.txt")
    groups["es"] = [
        {"id": "ES-GREEN", "value": "1", "source": es_rel, "sha": es_sha},
        {"id": "ES-TAMPERED", "value": "1", "source": es_rel, "sha": bad_sha},
    ]

    # ---- 意大利法条（官方 AKN 哈希 + 条文切片哈希）----
    it_rel, it_sha = _stage_card(proj, "it/" + IT_RUN + "/art_1.it.card.txt",
                                 "cards/it/" + IT_RUN + "/art_1.it.card.txt")
    groups["it"] = [
        {"id": "IT-GREEN", "value": "1", "source": it_rel, "sha": it_sha},
        {"id": "IT-TAMPERED", "value": "1", "source": it_rel, "sha": bad_sha},
    ]

    # ---- 意大利判例（判决切片哈希 + 正文哈希）----
    itc_name = "ECLI-IT-COST-1956-1.itcase.card.txt"
    itc_rel, itc_sha = _stage_card(proj, "it-case/" + ITCASE_RUN + "/" + itc_name,
                                   "cards/it-case/" + ITCASE_RUN + "/" + itc_name)
    # ⚠️ 意大利判例闸的「卡自身被改」是**卡级**检查（每张卡只做一次，
    #    factscribe_legal/it_case_verify.py:404-409）⇒ 同一张卡上，被改的那条
    #    必须排在前面，否则卡级检查会被先跑的那条吃掉。
    groups["it_case"] = [
        {"id": "ITCASE-TAMPERED", "value": "113", "source": itc_rel,
         "sha": bad_sha},
        {"id": "ITCASE-GREEN", "value": "113", "source": itc_rel,
         "sha": itc_sha},
    ]

    # ---- 法国判例（官方判决 XML/TXT 副本 + 卡内嵌正文）----
    frc_rel, frc_sha = _stage_card(
        proj, "fr-case/" + FRCASE_RUN + "/JURITEXT000006951547.fr-case.card.txt",
        "runs/" + FRCASE_RUN + "/JURITEXT000006951547.fr-case.card.txt")
    for ext in ("xml", "txt"):
        _copy(os.path.join(CORPUS, "fr-case", FRCASE_RUN, "official",
                           "JURITEXT000006951547." + ext),
              os.path.join(proj, "runs", FRCASE_RUN, "official",
                           "JURITEXT000006951547." + ext))
    groups["fr_case"] = [
        {"id": "FRCASE-GREEN", "value": "300000", "source": frc_rel,
         "sha": frc_sha},
        {"id": "FRCASE-TAMPERED", "value": "300000", "source": frc_rel,
         "sha": bad_sha},
    ]

    # ---- 中国案例（材料在项目 runs/ 下，不在语料视图里）----
    # 干净件一份（绿）＋ 官方正文被改过的一份（红：哈希对不上/正文脱钩/值不在）。
    run_dir = os.path.join(proj, "runs", CN_CASE_RUN)
    tampered = CN_CASE_OFFICIAL.replace("146160", "146161")
    case_rels = []
    for slug, official in ((CN_CASE_SLUG, CN_CASE_OFFICIAL),
                           (CN_CASE_SLUG_BAD, tampered)):
        _write(os.path.join(run_dir, "official", slug + ".txt"), official)
        card_fields = dict(CN_CASE_FIELDS)
        # 两张卡都声明**原件**的哈希 ⇒ 被改过的那张必然哈希对不上。
        card_fields["OFFICIAL_TEXT_SHA256"] = _sha256_text(CN_CASE_OFFICIAL)
        card = "# 案例证据卡\n" + "".join("%s: %s\n" % kv
                                          for kv in card_fields.items())
        card += "--- OFFICIAL TEXT ---\n" + CN_CASE_OFFICIAL
        rel = "runs/%s/%s.case.card.txt" % (CN_CASE_RUN, slug)
        _write(os.path.join(proj, rel), card)
        case_rels.append((rel, _sha256_text(card)))
    _write(os.path.join(run_dir, "result.json"),
           json.dumps({"run_id": CN_CASE_RUN,
                       "artifacts": [r for r, _ in case_rels]},
                      ensure_ascii=False))
    _write(os.path.join(run_dir, "record.json"),
           json.dumps({"run_id": CN_CASE_RUN,
                       "facts": ["CNCASE-GREEN", "CNCASE-TAMPERED"]},
                      ensure_ascii=False))
    groups["case"] = [
        {"id": "CNCASE-GREEN", "value": "146160",
         "source": case_rels[0][0], "sha": case_rels[0][1]},
        {"id": "CNCASE-TAMPERED", "value": "146160",
         "source": case_rels[1][0], "sha": case_rels[1][1]},
    ]

    for name, facts in groups.items():
        _write(os.path.join(proj, "facts", "10-%s.toml" % name),
               _facts_toml(facts))
    return proj


def collect_findings(proj, root):
    """跑全部各闸，把判定结果归一成可比对的清单。"""
    out = {}
    fr_findings, _corpus = verify_fr(proj, os.path.join(CORPUS, "fr"),
                                     REFERENCE_DATE,
                                     os.path.join(CORPUS, "fr",
                                                  "view_current.jsonl"))
    out["fr"] = fr_findings
    out["cn"] = verify_cn(proj, os.path.join(CORPUS, "cn",
                                             "catalog.jsonl.gz"),
                          REFERENCE_DATE)
    out["es"] = verify_es(proj, os.path.join(CORPUS, "es", ES_RUN),
                          REFERENCE_DATE)[0]
    out["it"] = verify_it(proj, os.path.join(CORPUS, "it", IT_RUN),
                          REFERENCE_DATE)[0]
    out["it_case"] = verify_it_case(proj, os.path.join(CORPUS, "it-case",
                                                      ITCASE_RUN))[0]
    out["fr_case"] = verify_fr_case(proj)[0]
    out["case"] = verify_case(proj)
    return dict((k, _normalize(v, root)) for k, v in out.items())


def _normalize(findings, root):
    """归一成 {code, severity, location, message}，排序后可比对。

    临时目录路径统一替换成 <TMP>（否则基线随 tmp 目录变，逐字节比不了）。
    """
    rows = []
    for f in findings:
        msg = str(f.message).replace(os.path.abspath(root), "<TMP>")
        rows.append({"code": f.code, "severity": f.severity,
                     "location": f.location, "message": msg})
    rows.sort(key=lambda r: (r["code"], r["severity"], r["location"],
                              r["message"]))
    return rows


def record_baseline(path=BASELINE):
    """跑一遍各闸，把结果落成基线文件（改造前捕获的那一版）。"""
    with tempfile.TemporaryDirectory() as root:
        proj = build_project(root)
        gates = collect_findings(proj, root)
    doc = {
        "note": ("改造前捕获的六闸判定基线；公共层（factscribe_legal/adapters/）"
                 "落地后必须逐条一致。改动闸或改动夹具才重录。"),
        "reference_date": REFERENCE_DATE,
        "gates": gates,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    return doc


class TestGatesUnchanged(unittest.TestCase):
    """六闸判定结果与改造前逐条一致。"""

    def test_gate_verdicts_match_baseline(self):
        record = os.environ.get("LEGAL_GATES_BASELINE_RECORD") == "1"
        with tempfile.TemporaryDirectory() as root:
            proj = build_project(root)
            gates = collect_findings(proj, root)
        if record:
            doc = record_baseline()
            self.assertEqual(doc["gates"], gates)
            return
        self.assertTrue(os.path.exists(BASELINE),
                        "基线文件不在：%s" % BASELINE)
        with open(BASELINE, encoding="utf-8") as fh:
            base = json.load(fh)
        self.assertEqual(base.get("reference_date"), REFERENCE_DATE)
        for name in sorted(base["gates"]):
            self.assertIn(name, gates, "闸 %s 没跑到" % name)
            self.assertEqual(base["gates"][name], gates[name],
                             "闸 %s 的判定与改造前不一致" % name)

    def test_baseline_is_not_empty(self):
        """基线不能是空的——空锁等于没锁。"""
        with open(BASELINE, encoding="utf-8") as fh:
            base = json.load(fh)
        total = sum(len(v) for v in base["gates"].values())
        self.assertGreater(total, 0, "基线里一条判定都没有")
        reds = [f for v in base["gates"].values() for f in v
                if f["severity"] == "red"]
        yellows = [f for v in base["gates"].values() for f in v
                   if f["severity"] == "yellow"]
        self.assertGreater(len(reds), 0, "基线里没有红牌")
        self.assertGreater(len(yellows), 0, "基线里没有黄牌")


if __name__ == "__main__":
    if os.environ.get("LEGAL_GATES_BASELINE_RECORD") == "1":
        doc = record_baseline()
        for name, rows in sorted(doc["gates"].items()):
            print("%-9s %d 条" % (name, len(rows)))
    else:
        unittest.main()
