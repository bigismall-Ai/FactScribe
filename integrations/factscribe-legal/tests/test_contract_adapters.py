#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一契约**公共层 adapter** 的自测：标准库 unittest，网络零依赖。

三块：
  1. **每个 adapter 一条真卡**：给它仓内真实证据卡，断言输出的
     `kind` / `jurisdiction` / `local_id` 逐字正确（六种形状 ＋ 集体协议）。
  2. **统一读路径**：有公共层视图时走视图，没有时现场从旧卡推导；
     视图缺字段时从旧卡补齐（视图是缓存，不是唯一真相）。
  3. **fail-closed**：取不到必填字段就报错，不给空值混进统一层。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from factscribe_legal import adapters  # noqa: E402
from factscribe_legal.adapters import (cn_provision, es_provision,  # noqa: E402
                                       fr_case, fr_provision, it_agreement,
                                       it_case, it_provision)
from factscribe_legal.adapters.base import (FIELDS, MISSING,  # noqa: E402
                                            ContractFieldMissing,
                                            load_view, view_key, view_record)
from factscribe_legal.receipts import MISSING as RECEIPT_MISSING  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.abspath(os.path.join(HERE, "..", "corpus"))
BULK_IT = os.path.abspath(os.path.join(HERE, "..", "corpus-bulk-it"))

ES_RUN = "run-20261116-es-ley39-2015-procedimiento-administrativo"
IT_RUN = "run-20261116-it-1990n241"
ITCASE_RUN = "run-20261116-itcase-1956_1980"
FRCASE_RUN = "run-20261116-inca"


def _card(*parts):
    return os.path.join(CORPUS, *parts)


class TestFrenchProvisionAdapter(unittest.TestCase):
    """法国法条：NUM → local_id，直映原样。"""

    def test_card(self):
        out = fr_provision.adapt(_card("fr", "D641-10-1.card.txt"))
        self.assertEqual(out, {"kind": "provision", "jurisdiction": "fr",
                               "local_id": "D641-10-1"})

    def test_all_french_cards(self):
        names = sorted(n for n in os.listdir(os.path.join(CORPUS, "fr"))
                       if n.endswith(".card.txt"))
        self.assertTrue(names, "仓内没有法国法条卡")
        for name in names:
            out = fr_provision.adapt(_card("fr", name))
            self.assertEqual(out["kind"], "provision")
            self.assertEqual(out["jurisdiction"], "fr")
            self.assertEqual(out["local_id"], name[:-len(".card.txt")])

    def test_index_fallback_when_num_missing(self):
        """卡上没有 NUM 行时，用官方 XML 文件名到 index 里反查编号。"""
        index = fr_provision.load_index(os.path.join(CORPUS, "fr",
                                                     "index.json"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "broken.card.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 法国法条证据卡\nOFFICIAL_XML: D641-10-1.xml\n")
            out = fr_provision.adapt(path, index=index)
        self.assertEqual(out["local_id"], "D641-10-1")


class TestChineseProvisionAdapter(unittest.TestCase):
    """中国法规：BBBS → local_id，直映原样；kind=provision（法规级）。"""

    def test_card(self):
        name = "中华人民共和国劳动合同法_2c909f.cn.card.txt"
        out = cn_provision.adapt(_card("cn", "cards", name))
        self.assertEqual(out, {
            "kind": "provision", "jurisdiction": "cn",
            "local_id": "2c909fdd678bf17901678bf74d7106b3"})

    def test_catalog_fallback_when_bbbs_missing(self):
        catalog = cn_provision.load_index(os.path.join(CORPUS, "cn",
                                                        "catalog.jsonl.gz"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "broken.cn.card.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 中国法规证据卡\nTITLE: 中华人民共和国劳动合同法\n")
            out = cn_provision.adapt(path, index=catalog)
        self.assertEqual(out["local_id"], "2c909fdd678bf17901678bf74d7106b3")


class TestSpanishProvisionAdapter(unittest.TestCase):
    """西班牙法条：ACT_ID/BLOCK_ID 复合号，原样保留。"""

    def test_card(self):
        out = es_provision.adapt(_card("es", ES_RUN, "a1.es.card.txt"))
        self.assertEqual(out, {"kind": "provision", "jurisdiction": "es",
                               "local_id": "BOE-A-2015-10565/a1"})

    def test_other_blocks_are_distinct(self):
        a2 = es_provision.adapt(_card("es", ES_RUN, "a2.es.card.txt"))
        self.assertEqual(a2["local_id"], "BOE-A-2015-10565/a2")
        self.assertNotEqual(a2["local_id"],
                            es_provision.adapt(_card("es", ES_RUN,
                                                     "a1.es.card.txt"))["local_id"])


class TestItalianProvisionAdapter(unittest.TestCase):
    """意大利法条：ACT_URN/ARTICLE_EID 复合号，原样保留。"""

    def test_card(self):
        out = it_provision.adapt(_card("it", IT_RUN, "art_1.it.card.txt"))
        self.assertEqual(out, {
            "kind": "provision", "jurisdiction": "it",
            "local_id": "urn:nir:stato:legge:1990-08-07;241/art_1"})


class TestItalianCaseAdapter(unittest.TestCase):
    """意大利判例：ECLI → local_id；kind=case。"""

    def test_card(self):
        out = it_case.adapt(_card("it-case", ITCASE_RUN,
                                  "ECLI-IT-COST-1956-1.itcase.card.txt"))
        self.assertEqual(out, {"kind": "case", "jurisdiction": "it",
                               "local_id": "ECLI:IT:COST:1956:1"})


class TestFrenchCaseAdapter(unittest.TestCase):
    """法国判例：CASE_ID → local_id；kind=case。"""

    def test_card(self):
        out = fr_case.adapt(_card("fr-case", FRCASE_RUN,
                                  "JURITEXT000006951547.fr-case.card.txt"))
        self.assertEqual(out, {"kind": "case", "jurisdiction": "fr",
                               "local_id": "JURITEXT000006951547"})


class TestItalianAgreementAdapter(unittest.TestCase):
    """集体协议：CNEL 簇码 → local_id；kind=agreement（单独形状）。"""

    def test_inventory_row(self):
        rows = it_agreement.read_inventory(
            os.path.join(BULK_IT, "it-inventory-vigenti.tsv"))
        self.assertEqual(len(rows), 144, "CCNL 清单应 144 簇")
        row = next(r for r in rows if r["code"] == "A011")
        out = it_agreement.adapt(row)
        self.assertEqual(out, {"kind": "agreement", "jurisdiction": "it",
                               "local_id": "A011"})

    def test_agreement_is_not_a_provision(self):
        """集体协议不塞进法条模板：kind 必须与法条不同。"""
        rows = it_agreement.read_inventory(
            os.path.join(BULK_IT, "it-inventory-vigenti.tsv"))
        out = it_agreement.adapt(rows[0])
        self.assertNotEqual(out["kind"], "provision")
        self.assertEqual(out["kind"], "agreement")


class TestUnifiedReadPath(unittest.TestCase):
    """统一读路径：有视图走视图，没视图现场从旧卡推导。"""

    def setUp(self):
        self.card = _card("fr", "D641-10-1.card.txt")
        self.root = os.path.dirname(os.path.dirname(self.card))

    def test_without_view_derives_from_card(self):
        out = adapters.adapt("fr_provision", self.card)
        self.assertEqual(out["local_id"], "D641-10-1")

    def test_view_is_used_when_present(self):
        rec = view_record("fr_provision", view_key(self.card, self.root),
                          {"kind": "provision", "jurisdiction": "fr",
                           "local_id": "VIEW-0001"})
        out = adapters.adapt("fr_provision", self.card,
                             view={rec["card"]: rec}, corpus_root=self.root)
        self.assertEqual(out["local_id"], "VIEW-0001")

    def test_view_missing_field_falls_back_to_card(self):
        rec = view_record("fr_provision", view_key(self.card, self.root),
                          {"kind": "provision", "jurisdiction": "fr",
                           "local_id": ""})
        out = adapters.adapt("fr_provision", self.card,
                             view={rec["card"]: rec}, corpus_root=self.root)
        self.assertEqual(out["local_id"], "D641-10-1")

    def test_load_view_reads_jsonl(self):
        rec = view_record("fr_provision", "fr/D641-10-1.card.txt",
                          {"kind": "provision", "jurisdiction": "fr",
                           "local_id": "D641-10-1"})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "contract-view.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            view = load_view(path)
        self.assertIn("fr/D641-10-1.card.txt", view)
        self.assertEqual(view["fr/D641-10-1.card.txt"]["local_id"],
                         "D641-10-1")

    def test_unknown_shape_raises(self):
        with self.assertRaises(KeyError):
            adapters.adapt("no_such_shape", self.card)

    def test_output_has_only_the_three_fields(self):
        out = adapters.adapt("fr_provision", self.card)
        self.assertEqual(sorted(out), sorted(FIELDS))
        self.assertEqual(FIELDS, ("kind", "jurisdiction", "local_id"))


class TestFailClosed(unittest.TestCase):
    """取不到必填字段 ⇒ 报错，不给空值混进统一层。"""

    def test_wrong_shape_card_raises(self):
        """把中国卡喂给法国 adapter ⇒ 必须报错，不能蒙一个 kind 出来。"""
        name = "中华人民共和国劳动合同法_2c909f.cn.card.txt"
        with self.assertRaises(ContractFieldMissing):
            fr_provision.adapt(_card("cn", "cards", name))

    def test_empty_card_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.card.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 只有注释\n")
            with self.assertRaises(ContractFieldMissing):
                fr_provision.adapt(path)

    def test_agreement_needs_a_row(self):
        with self.assertRaises(ContractFieldMissing):
            it_agreement.adapt("not-a-row")


class TestContractConstants(unittest.TestCase):
    def test_missing_marker_is_the_receipt_one(self):
        """缺省标记与收据五元组同一个（不新造标记形状）。"""
        self.assertEqual(MISSING, RECEIPT_MISSING)
        self.assertEqual(MISSING, "—")

    def test_every_shape_has_an_adapter(self):
        self.assertEqual(len(adapters.ADAPTERS), 7)
        for shape, module in adapters.ADAPTERS.items():
            self.assertEqual(module.SHAPE, shape)
            self.assertIn(module.KIND, adapters.KINDS)
            self.assertIn(module.JURISDICTION, adapters.JURISDICTIONS)


class TestCorpusUntouched(unittest.TestCase):
    """公共层是只读派生的：跑完 adapter，卡片一个字节都不能变。"""

    def test_cards_unchanged_after_adapt(self):
        targets = [
            _card("fr", "D641-10-1.card.txt"),
            _card("cn", "cards",
                  "中华人民共和国劳动合同法_2c909f.cn.card.txt"),
            _card("es", ES_RUN, "a1.es.card.txt"),
            _card("it", IT_RUN, "art_1.it.card.txt"),
            _card("it-case", ITCASE_RUN, "ECLI-IT-COST-1956-1.itcase.card.txt"),
            _card("fr-case", FRCASE_RUN,
                  "JURITEXT000006951547.fr-case.card.txt"),
        ]
        before = dict((p, _sha256_file(p)) for p in targets)
        for path in targets:
            adapters.adapt_shape(_shape_of(path), path)
        for path in targets:
            self.assertEqual(_sha256_file(path), before[path],
                             "adapter 改动了卡片：%s" % path)


def _shape_of(path):
    if path.endswith(".cn.card.txt"):
        return "cn_provision"
    if path.endswith(".es.card.txt"):
        return "es_provision"
    if path.endswith(".it.card.txt"):
        return "it_provision"
    if path.endswith(".itcase.card.txt"):
        return "it_case"
    if path.endswith(".fr-case.card.txt"):
        return "fr_case"
    return "fr_provision"


def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    unittest.main()
