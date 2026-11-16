#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factscribe_legal 的自测（标准库 unittest，不依赖上游）。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from factscribe_legal.provisions import (Provision, fr_number_to_int,  # noqa: E402
                                         norm_text)
from factscribe_legal.verify import verify  # noqa: E402


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class TestFrenchNumbers(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(fr_number_to_int("trente-cinq"), 35)
        self.assertEqual(fr_number_to_int("quinze"), 15)
        self.assertEqual(fr_number_to_int("soixante"), 60)

    def test_compound(self):
        self.assertEqual(fr_number_to_int("quatre-vingt-dix"), 90)
        self.assertEqual(fr_number_to_int("soixante-douze"), 72)
        self.assertEqual(fr_number_to_int("vingt-et-un"), None)   # 未收录写法

    def test_unknown(self):
        self.assertIsNone(fr_number_to_int("banane"))


class TestProvision(unittest.TestCase):
    def _p(self, **kw):
        base = dict(num="L3121-27", date_debut="2008-05-01", date_fin="2999-01-01")
        base.update(kw)
        return Provision(**base)

    def test_in_force(self):
        p = self._p()
        self.assertTrue(p.in_force_at("2026-11-14"))
        self.assertFalse(p.in_force_at("2008-04-30"))   # 生效前
        self.assertFalse(p.in_force_at("2999-01-01"))   # 失效当天

    def test_scheduled_and_repealed(self):
        p = self._p(date_debut="2029-03-01", date_fin="2999-01-01")
        self.assertTrue(p.scheduled_at("2026-11-14"))
        self.assertFalse(p.in_force_at("2026-11-14"))
        q = self._p(date_debut="2020-01-01", date_fin="2025-01-01")
        self.assertTrue(q.repealed_at("2026-11-14"))
        self.assertFalse(q.in_force_at("2026-11-14"))

    def test_contains_number_arabic(self):
        p = self._p(text="La durée légale est fixée à 35 heures par semaine.")
        self.assertTrue(p.contains_number("35"))
        self.assertFalse(p.contains_number("3"))   # 不能命中 35 里的 3

    def test_contains_number_french_word(self):
        p = self._p(text="La durée légale est fixée à trente-cinq heures par semaine.")
        self.assertTrue(p.contains_number("35"))
        self.assertFalse(p.contains_number("36"))

    def test_contains_number_not_in_text(self):
        p = self._p(text="La durée légale est fixée à trente-cinq heures par semaine.")
        self.assertFalse(p.contains_number("40"))


class TestVerify(unittest.TestCase):
    def _project(self, tmp, fact_source="provisions/L3121-27.xml",
                 fact_sha=None, value="35", cite="art:L3121-27"):
        os.makedirs(os.path.join(tmp, "facts"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "sections"), exist_ok=True)
        with open(os.path.join(tmp, "facts", "01.toml"), "w", encoding="utf-8") as f:
            f.write(f'''[[fact]]
id = "P1"
claim = "法定正常工时"
value = "{value}"
source = "{fact_source}"
source_sha256 = "sha256:{fact_sha or '0' * 64}"
confidence = "high"
derived_from = []
''')
        with open(os.path.join(tmp, "sections", "01.tex"), "w", encoding="utf-8") as f:
            f.write("\\section{X}\nCite \\cite{" + cite + "}.\n")

    def _corpus(self, tmp, etat="VIGUEUR", d0="2008-05-01", d1="2999-01-01"):
        import hashlib
        import json
        cdir = os.path.join(tmp, "corpus")
        os.makedirs(cdir, exist_ok=True)
        raw = (f"<ARTICLE><META><META_COMMUN><ID>LEGIARTI000037329915</ID></META_COMMUN>"
               f"</META><META_SPEC><META_ARTICLE><NUM>L3121-27</NUM><ETAT>{etat}</ETAT>"
               f"<DATE_DEBUT>{d0}</DATE_DEBUT><DATE_FIN>{d1}</DATE_FIN></META_ARTICLE></META_SPEC>"
               f"<BLOC_TEXTUEL><p>La durée légale est fixée à trente-cinq heures par semaine."
               f"</p></BLOC_TEXTUEL></ARTICLE>").encode("utf-8")
        with open(os.path.join(cdir, "L3121-27.xml"), "wb") as f:
            f.write(raw)
        sha = hashlib.sha256(raw).hexdigest()
        with open(os.path.join(cdir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"code_id": "X", "provisions": {
                "L3121-27": {"num": "L3121-27", "legiarti": "LEGIARTI000037329915",
                             "code_id": "X", "etat": etat, "date_debut": d0,
                             "date_fin": d1, "xml_file": "L3121-27.xml",
                             "xml_sha256": sha, "text_sha256": "", "xml_bytes": len(raw)}}}, f)
        return cdir, sha

    def test_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir, sha = self._corpus(tmp)
            self._project(tmp, fact_sha=sha)
            findings, _ = verify(tmp, cdir, "2026-11-14")
            self.assertEqual([f.code for f in findings if f.severity == "red"], [])

    def test_hash_mismatch_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir, _sha = self._corpus(tmp)
            self._project(tmp, fact_sha="f" * 64)
            findings, _ = verify(tmp, cdir, "2026-11-14")
            self.assertIn("LEGAL_PROV_HASH_MISMATCH", [f.code for f in findings])

    def test_quote_mismatch_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir, sha = self._corpus(tmp)
            self._project(tmp, fact_sha=sha, value="40")
            findings, _ = verify(tmp, cdir, "2026-11-14")
            self.assertIn("LEGAL_QUOTE_MISMATCH", [f.code for f in findings])

    def test_unknown_provision_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir, sha = self._corpus(tmp)
            self._project(tmp, fact_sha=sha, cite="art:L9999-1")
            findings, _ = verify(tmp, cdir, "2026-11-14")
            self.assertIn("LEGAL_PROV_UNKNOWN", [f.code for f in findings])

    def test_not_in_force_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir, sha = self._corpus(tmp, d0="2029-01-01")
            self._project(tmp, fact_sha=sha)
            findings, _ = verify(tmp, cdir, "2026-11-14")
            codes = [f.code for f in findings]
            self.assertIn("LEGAL_PROV_SCHEDULED", codes)

    def test_repealed_is_yellow(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir, sha = self._corpus(tmp, d0="2008-05-01", d1="2025-01-01")
            self._project(tmp, fact_sha=sha)
            findings, _ = verify(tmp, cdir, "2026-11-14")
            f = [x for x in findings if x.code == "LEGAL_PROV_REPEALED"]
            self.assertTrue(f)
            self.assertEqual(f[0].severity, "yellow")


class TestMultiLevelSourcePath(unittest.TestCase):
    """回归：source 是 runs/<run_id>/<num>.card.txt 这类多级路径时，
    事实不能被跳过（曾经因为正则只匹配一级目录而整批被跳过 ⇒ 假绿）。"""

    def _corpus(self, tmp):
        import hashlib
        import json
        cdir = os.path.join(tmp, "corpus")
        os.makedirs(os.path.join(cdir, "official"), exist_ok=True)
        raw = (b"<ARTICLE><META><META_COMMUN><ID>LEGIARTI000037329915</ID></META_COMMUN>"
               b"</META><META_SPEC><META_ARTICLE><NUM>L3121-27</NUM><ETAT>VIGUEUR</ETAT>"
               b"<DATE_DEBUT>2008-05-01</DATE_DEBUT><DATE_FIN>2999-01-01</DATE_FIN>"
               b"</META_ARTICLE></META_SPEC><BLOC_TEXTUEL><p>fixee a trente-cinq heures."
               b"</p></BLOC_TEXTUEL></ARTICLE>")
        with open(os.path.join(cdir, "official", "L3121-27.xml"), "wb") as f:
            f.write(raw)
        sha = hashlib.sha256(raw).hexdigest()
        with open(os.path.join(cdir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"provisions": {"L3121-27": {
                "num": "L3121-27", "legiarti": "LEGIARTI000037329915",
                "code_id": "X", "etat": "VIGUEUR", "date_debut": "2008-05-01",
                "date_fin": "2999-01-01", "xml_file": "official/L3121-27.xml",
                "xml_sha256": sha, "text_sha256": "", "xml_bytes": len(raw)}}}, f)
        return cdir, sha

    def _project(self, tmp, value="35", declared=None):
        run = os.path.join(tmp, "runs", "run-test")
        os.makedirs(run, exist_ok=True)
        card = ("NUM: L3121-27\nOFFICIAL_XML: official/L3121-27.xml\n"
                f"OFFICIAL_XML_SHA256: {declared or self._sha}\n"
                "--- OFFICIAL TEXT ---\ntrente-cinq heures\n")
        with open(os.path.join(run, "L3121-27.card.txt"), "w", encoding="utf-8") as f:
            f.write(card)
        with open(os.path.join(tmp, "facts", "01.toml"), "w", encoding="utf-8") as f:
            f.write(f'''[[fact]]
id = "P1"
claim = "c"
value = "{value}"
source = "runs/run-test/L3121-27.card.txt"
source_sha256 = "sha256:{self._sha}"
confidence = "high"
derived_from = []
''')

    def setUp(self):
        import hashlib
        self._sha = hashlib.sha256(b"x").hexdigest()

    def test_multilevel_source_is_inspected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir, sha = self._corpus(tmp)
            os.makedirs(os.path.join(tmp, "facts"), exist_ok=True)
            self._project(tmp, declared=sha)
            findings, _ = verify(tmp, cdir, "2026-11-14")
            # 事实被看到了（值 35 在正文里 ⇒ 不该报 quote mismatch）
            self.assertEqual([f.code for f in findings if f.code == "LEGAL_QUOTE_MISMATCH"], [])

    def test_multilevel_source_bad_value_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir, sha = self._corpus(tmp)
            os.makedirs(os.path.join(tmp, "facts"), exist_ok=True)
            self._project(tmp, value="40", declared=sha)
            findings, _ = verify(tmp, cdir, "2026-11-14")
            self.assertIn("LEGAL_QUOTE_MISMATCH", [f.code for f in findings])

    def test_card_declared_hash_mismatch_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir, sha = self._corpus(tmp)
            os.makedirs(os.path.join(tmp, "facts"), exist_ok=True)
            self._project(tmp, declared="f" * 64)
            findings, _ = verify(tmp, cdir, "2026-11-14")
            self.assertIn("LEGAL_PROV_HASH_MISMATCH", [f.code for f in findings])


class TestCoverageAndUniqueness(unittest.TestCase):
    """版本池覆盖度与「参考日唯一生效版本」两条判据。"""

    def _make(self, tmp, pool_asof, versions):
        import hashlib
        import json
        cdir = os.path.join(tmp, "corpus")
        os.makedirs(cdir, exist_ok=True)
        raw = (b"<ARTICLE><META><META_COMMUN><ID>LEGIARTI000037329915</ID></META_COMMUN>"
               b"</META><META_SPEC><META_ARTICLE><NUM>L3121-27</NUM><ETAT>VIGUEUR</ETAT>"
               b"<DATE_DEBUT>2008-05-01</DATE_DEBUT><DATE_FIN>2999-01-01</DATE_FIN>"
               b"</META_ARTICLE></META_SPEC><BLOC_TEXTUEL><p>trente-cinq heures"
               b"</p></BLOC_TEXTUEL></ARTICLE>")
        with open(os.path.join(cdir, "L3121-27.xml"), "wb") as f:
            f.write(raw)
        sha = hashlib.sha256(raw).hexdigest()
        with open(os.path.join(cdir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"pool_asof": pool_asof, "provisions": {"L3121-27": {
                "num": "L3121-27", "legiarti": "LEGIARTI000037329915",
                "code_id": "X", "etat": "VIGUEUR", "date_debut": "2008-05-01",
                "date_fin": "2999-01-01", "xml_file": "L3121-27.xml",
                "xml_sha256": sha, "text_sha256": "", "xml_bytes": len(raw),
                "versions": versions}}}, f)
        os.makedirs(os.path.join(tmp, "facts"), exist_ok=True)
        return cdir

    def test_gap_is_yellow(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir = self._make(tmp, "2026-11-13", [
                {"legiarti": "A", "etat": "VIGUEUR", "date_debut": "2008-05-01",
                 "date_fin": "2999-01-01"}])
            findings, _ = verify(tmp, cdir, "2026-11-14")
            f = [x for x in findings if x.code == "LEGAL_COVERAGE_GAP"]
            self.assertTrue(f)
            self.assertEqual(f[0].severity, "yellow")
            self.assertIn("1 天", f[0].message)

    def test_no_gap_when_pool_covers(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir = self._make(tmp, "2026-11-14", [
                {"legiarti": "A", "etat": "VIGUEUR", "date_debut": "2008-05-01",
                 "date_fin": "2999-01-01"}])
            findings, _ = verify(tmp, cdir, "2026-11-14")
            self.assertEqual([x.code for x in findings if x.code == "LEGAL_COVERAGE_GAP"], [])

    def test_ambiguous_versions_is_yellow(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir = self._make(tmp, "2026-11-14", [
                {"legiarti": "A", "etat": "VIGUEUR", "date_debut": "2008-05-01",
                 "date_fin": "2999-01-01"},
                {"legiarti": "B", "etat": "VIGUEUR", "date_debut": "2020-01-01",
                 "date_fin": "2999-01-01"}])
            findings, _ = verify(tmp, cdir, "2026-11-14")
            self.assertIn("LEGAL_PROV_AMBIGUOUS", [x.code for x in findings])


class TestCaseDimension(unittest.TestCase):
    """第 5 层（中国案例维度）的自测：闸门自己也要有测试。"""

    OFFICIAL = ("基本案情\n　　张某于2015年4月1日入职某公司。同年3月，张某怀孕。\n"
                "　　一、某宝销售公司支付张某工资人民币6766.5元；\n"
                "　　二、某宝销售公司支付张某房屋销售佣金45102元；\n"
                "　　三、某宝销售公司支付张某违法解除劳动合同赔偿金146160元；\n"
                "　　重庆市第一中级人民法院于2023年10月20日作出（2023）渝01民终7708号民事判决。\n")

    def _project(self, tmp, official=None, card_overrides=None, record_ids=None):
        import hashlib
        import json
        off = official if official is not None else self.OFFICIAL
        run = os.path.join(tmp, "runs", "run-20261114-case")
        offdir = os.path.join(run, "official")
        os.makedirs(offdir, exist_ok=True)
        slug = "张某诉某公司劳动争议案"
        with open(os.path.join(offdir, slug + ".txt"), "w", encoding="utf-8") as f:
            f.write(off)
        fields = {
            "CASE_NO": "（2023）渝01民终7708号",
            "JUDGE_DATE": "2023.10.20",
            "AMOUNTS": "6766.5, 45102, 146160",
            "OFFICIAL_TEXT_SHA256": hashlib.sha256(off.encode("utf-8")).hexdigest(),
        }
        fields.update(card_overrides or {})
        card = "# 案例证据卡\n" + "".join(f"{k}: {v}\n" for k, v in fields.items())
        card += "--- OFFICIAL TEXT ---\n" + off
        card_path = os.path.join(run, slug + ".case.card.txt")
        with open(card_path, "w", encoding="utf-8") as f:
            f.write(card)
        os.makedirs(os.path.join(tmp, "facts"), exist_ok=True)
        fact_src = f"runs/run-20261114-case/{slug}.case.card.txt"
        sha = hashlib.sha256(card_path.encode("utf-8")).hexdigest()
        toml = ('schema = "paperkit-fact/3.0"\n\n[[fact]]\nid = "CASE1-AMT-COMP"\n'
                'claim = "违法解除劳动合同赔偿金"\nvalue = "146160"\n'
                f'source = "{fact_src}"\nsource_sha256 = "sha256:{sha}"\n'
                'locator = "测试"\nconfidence = "high"\nderived_from = []\n')
        with open(os.path.join(tmp, "facts", "04-case.toml"), "w", encoding="utf-8") as f:
            f.write(toml)
        with open(os.path.join(run, "result.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": "run-20261114-case", "artifacts": [fact_src]},
                      f, ensure_ascii=False)
        ids = record_ids if record_ids is not None else ["CASE1-AMT-COMP"]
        with open(os.path.join(run, "record.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": "run-20261114-case", "facts": ids}, f, ensure_ascii=False)
        return tmp

    def test_clean_is_green(self):
        from factscribe_legal.case_verify import verify_case
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp)
            findings = verify_case(tmp)
            self.assertEqual([x.code for x in findings], [], findings)

    def test_official_text_tampered_is_red(self):
        from factscribe_legal.case_verify import verify_case
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp)
            p = os.path.join(tmp, "runs", "run-20261114-case", "official",
                             "张某诉某公司劳动争议案.txt")
            s = _read(p).replace("146160", "146161")
            _write(p, s)
            findings = verify_case(tmp)
            self.assertIn("CASE_OFFICIAL_HASH_MISMATCH", [x.code for x in findings])

    def test_card_amount_inflated_is_red(self):
        """卡片里的金额被改大（且账里的哈希同步改）⇒ 必须判红，不能只黄。"""
        from factscribe_legal.case_verify import verify_case
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp)
            p = os.path.join(tmp, "runs", "run-20261114-case",
                             "张某诉某公司劳动争议案.case.card.txt")
            s = _read(p).replace("146160", "999999")
            _write(p, s)
            findings = verify_case(tmp)
            self.assertIn("CASE_AMOUNT_MISMATCH", [x.code for x in findings])

    def test_card_embedded_text_diverged_is_red(self):
        from factscribe_legal.case_verify import verify_case
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp)
            p = os.path.join(tmp, "runs", "run-20261114-case",
                             "张某诉某公司劳动争议案.case.card.txt")
            s = _read(p).replace("基本案情", "基本案由")
            _write(p, s)
            findings = verify_case(tmp)
            self.assertIn("CASE_CARD_TEXT_DIVERGED", [x.code for x in findings])

    def test_value_not_in_official_is_red(self):
        from factscribe_legal.case_verify import verify_case
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp)
            f = os.path.join(tmp, "facts", "04-case.toml")
            s = _read(f).replace('value = "146160"', 'value = "888888"')
            _write(f, s)
            findings = verify_case(tmp)
            self.assertIn("CASE_VALUE_NOT_IN_OFFICIAL", [x.code for x in findings])

    def test_date_normalisation_accepts_chinese_format(self):
        """卡片写 2023.10.20，正文写 2023年10月20日 ⇒ 必须判为存在。"""
        from factscribe_legal.case_verify import _date_present, _dates_in
        d = _dates_in(self.OFFICIAL)
        self.assertTrue(_date_present("2023.10.20", self.OFFICIAL, d))
        self.assertTrue(_date_present("2023-10-20", self.OFFICIAL, d))
        self.assertFalse(_date_present("2024.10.20", self.OFFICIAL, d))

    def test_evidence_chain_broken_is_red(self):
        from factscribe_legal.case_verify import verify_case
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp, record_ids=["CASE1-NOPE"])
            findings = verify_case(tmp)
            self.assertIn("CASE_CHAIN_BROKEN", [x.code for x in findings])


if __name__ == "__main__":
    unittest.main()
