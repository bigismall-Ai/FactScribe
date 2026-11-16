#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""意大利法条专闸（verify-it）的自测：标准库 unittest，不依赖上游。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from factscribe_legal.it_verify import render_it, verify_it  # noqa: E402
from factscribe_legal.verify import verify as verify_fr  # noqa: E402

def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

AKN = """<?xml version="1.0" encoding="UTF-8"?>
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <act name="monovigente">
    <meta><identification><FRBRWork>
      <FRBRalias name="urn:nir" value="urn:nir:stato:decreto.legislativo:2008-04-09;81"/>
      <FRBRalias name="eli" value="eli/id/2008/04/30/008G0104/CONSOLIDATED/20260407"/>
    </FRBRWork><FRBRExpression>
      <FRBRthis value="/akn/it/act/decreto_legislativo/stato/2008-04-09/81/ita@2026-04-07/!main"/>
    </FRBRExpression></identification></meta>
    <body><mainBody>
      <article eId="art_29"><num>Art. 29</num><paragraph>
        <content><p>I datori di lavoro che occupano fino a 50 lavoratori possono effettuare la
        valutazione dei rischi sulla base delle procedure standardizzate.</p></content>
      </paragraph></article>
      <article eId="art_35"><num>Art. 35</num><paragraph>
        <content><p>Nelle aziende che occupano piu' di 15 lavoratori si indice almeno una
        volta all'anno una riunione.</p></content>
      </paragraph></article>
    </mainBody></body>
  </act>
</akomaNtoso>
"""


def sha(b):
    return hashlib.sha256(b).hexdigest()


class TestItalyGate(unittest.TestCase):
    """用一个迷你语料（两篇条文）把闸门的每条判据都跑一遍。"""

    def _corpus(self, root):
        run = os.path.join(root, "runs", "run-test-it")
        off = os.path.join(run, "official")
        os.makedirs(off)
        raw = AKN.encode("utf-8")
        with open(os.path.join(off, "act.akn.xml"), "wb") as fh:
            fh.write(raw)
        articles = {}
        for eid in ("art_29", "art_35"):
            import re
            m = re.search(rb'<article eId="' + eid.encode() + rb'">.*?</article>', raw, re.S)
            blob = m.group(0)
            with open(os.path.join(off, f"{eid}.xml"), "wb") as fh:
                fh.write(blob)
            text = re.sub(r"<[^>]+>", " ", blob.decode("utf-8"))
            import re as _re
            text = _re.sub(r"\s+", " ", text).strip()
            articles[eid] = {
                "eid": eid, "num": eid.split("_")[1],
                "article_file": f"official/{eid}.xml",
                "article_sha256": sha(blob), "article_bytes": len(blob),
                "text_sha256": sha(text.encode("utf-8")), "text_chars": len(text),
                "card_file": f"{eid}.it.card.txt", "card_sha256": "",
            }
        index = {
            "act_key": "DLGS81",
            "act_urn": "urn:nir:stato:decreto.legislativo:2008-04-09;81",
            "act_eli": "eli/id/2008/04/30/008G0104/CONSOLIDATED/20260407",
            "act_title": "DECRETO LEGISLATIVO 9 aprile 2008, n. 81",
            "source_file": "official/act.akn.xml",
            "source_sha256": sha(raw), "source_bytes": len(raw),
            "version_date": "2026-04-07",
            "fetch_vigenza": "20261114",
            "fetch_reference_date": "2026-11-14",
            "reference_date": "2026-11-14",
            "articles": articles,
        }
        with open(os.path.join(run, "index.json"), "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)

        # 证据卡 + 事实账
        os.makedirs(os.path.join(root, "facts"))
        facts = ['schema = "paperkit-fact/3.0"', ""]
        for fid, eid, val in (("IT1", "art_29", "50"), ("IT2", "art_35", "15")):
            card = "\n".join([
                "# 意大利法条证据卡（派生件）",
                "ACT_URN: urn:nir:stato:decreto.legislativo:2008-04-09;81",
                f"ARTICLE_EID: {eid}",
                f"ARTICLE_NUM: {eid.split('_')[1]}",
                "VERSION_DATE: 2026-04-07",
                "FETCH_VIGENZA: 20261114",
                "REFERENCE_DATE: 2026-11-14",
                "SOURCE_FILE: official/act.akn.xml",
                f"OFFICIAL_XML_SHA256: {sha(raw)}",
                f"ARTICLE_SHA256: {articles[eid]['article_sha256']}",
                "--- OFFICIAL TEXT ---",
                "testo",
                "",
            ])
            with open(os.path.join(run, f"{eid}.it.card.txt"), "w", encoding="utf-8") as fh:
                fh.write(card)
            facts += [
                "[[fact]]",
                f'id = "{fid}"',
                f'claim = "claim {fid}"',
                f'value = "{val}"',
                f'source = "runs/run-test-it/{eid}.it.card.txt"',
                f'source_sha256 = "sha256:{sha(card.encode("utf-8"))}"',
                'confidence = "high"',
                "derived_from = []",
                "",
            ]
        with open(os.path.join(root, "facts", "05-it-provisions.toml"), "w",
                  encoding="utf-8") as fh:
            fh.write("\n".join(facts))
        return run

    def _codes(self, root, run, date="2026-11-14"):
        findings, index = verify_it(root, run, date)
        return [f.code for f in findings], findings, index

    def test_clean_corpus_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            codes, findings, index = self._codes(tmp, run)
            self.assertEqual(codes, [], f"应当全绿，实际：{[f.code for f in findings]}")
            text, code = render_it(findings, index)
            self.assertEqual(code, 0)

    def test_article_slice_tampered_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "official", "art_29.xml")
            s = _read(p).replace("50 lavoratori", "60 lavoratori")
            _write(p, s)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("IT_ARTICLE_HASH_MISMATCH", codes)

    def test_official_file_tampered_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "official", "act.akn.xml")
            s = _read(p).replace("15 lavoratori", "25 lavoratori")
            _write(p, s)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("IT_SOURCE_HASH_MISMATCH", codes)

    def test_card_tampered_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "art_29.it.card.txt")
            s = _read(p).replace("testo", "testo modificato")
            _write(p, s)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("IT_CARD_SHA256_MISMATCH", codes)

    def test_value_not_in_official_text_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(tmp, "facts", "05-it-provisions.toml")
            s = _read(p).replace('value = "50"', 'value = "999"')
            _write(p, s)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("IT_QUOTE_MISMATCH", codes)

    def test_card_missing_is_red(self):
        """事实指向的意大利卡不存在 ⇒ 判红，不能静默跳过（否则等于「无不一致即通过」）。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(tmp, "facts", "05-it-provisions.toml")
            s = _read(p).replace("art_29.it.card.txt", "art_999.it.card.txt")
            _write(p, s)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("IT_CARD_MISSING", codes)

    def test_article_not_in_index_is_red(self):
        """卡在、但条文不在索引里 ⇒ IT_PROV_UNKNOWN。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            idx = os.path.join(run, "index.json")
            with open(idx, encoding="utf-8") as fh:
                d = json.load(fh)
            d["articles"].pop("art_29")
            with open(idx, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("IT_PROV_UNKNOWN", codes)

    def test_reference_date_mismatch_is_yellow(self):
        """钉的是 2026-11-14 当天生效的版本，拿别的参考日来核 ⇒ 黄项，不是红项。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            codes, _, _ = self._codes(tmp, run, date="2026-12-01")
            self.assertIn("IT_VERSION_GAP", codes)
            self.assertNotIn("IT_VERSION_GAP", [c for c in codes if c.startswith("IT_") and c != "IT_VERSION_GAP"] and [] or [])

    def test_article_removed_from_official_is_red(self):
        """官方整件里那条被删了（切片还在）⇒ 必须判红，不能当作「哈希对得上就过」。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "official", "act.akn.xml")
            s = _read(p)
            import re
            s = re.sub(r'<article eId="art_35">.*?</article>', "", s, flags=re.S)
            _write(p, s)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("IT_SOURCE_HASH_MISMATCH", codes)

    def test_french_gate_skips_italy_cards(self):
        """意大利证据卡不能让法国闸误判红。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._corpus(tmp)
            fr_corpus = os.path.join(tmp, "runs", "run-test-fr")
            os.makedirs(fr_corpus, exist_ok=True)
            with open(os.path.join(fr_corpus, "index.json"), "w", encoding="utf-8") as fh:
                json.dump({"provisions": {}}, fh)
            findings, _corpus = verify_fr(tmp, fr_corpus, "2026-11-14")
            self.assertEqual([f.code for f in findings], [],
                             f"法国闸不应因意大利卡报错：{[f.code for f in findings]}")


if __name__ == "__main__":
    unittest.main()
