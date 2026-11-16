#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""西班牙法条专闸（verify-es）的自测：标准库 unittest，网络零依赖。

用一个迷你语料（两篇条文）把闸门的每条判据都跑一遍：形状照 BOE 开放数据
`legislacion-consolidada` by-id 的合并文本 XML（<metadatos> + <texto>/
<bloque id="a1" tipo="precepto">），哈希是真算的，卡是照抓取器同款字段造的。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from factscribe_legal.es_verify import render_es, verify_es  # noqa: E402
from factscribe_legal.verify import verify as verify_fr  # noqa: E402

BOE_XML = """<?xml version="1.0" encoding="utf-8"?>
<response>
  <status>
    <code>200</code>
    <text>ok</text>
  </status>
  <data>
    <metadatos>
      <fecha_actualizacion>20261116T084356Z</fecha_actualizacion>
      <identificador>BOE-A-2015-10565</identificador>
      <ambito codigo="1">Estatal</ambito>
      <rango codigo="1311">Ley</rango>
      <fecha_disposicion>20151001</fecha_disposicion>
      <numero_oficial>39/2015</numero_oficial>
      <titulo>Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo y de Administración Electrónica.</titulo>
      <diario>Boletín Oficial del Estado</diario>
      <fecha_publicacion>20151002</fecha_publicacion>
      <fecha_vigencia>20151003</fecha_vigencia>
      <estado_consolidacion codigo="3">Finalizado</estado_consolidacion>
      <url_eli>https://www.boe.es/eli/es/l/2015/10/02/39</url_eli>
      <url_html_consolidada>https://www.boe.es/buscar/act.php?id=BOE-A-2015-10565</url_html_consolidada>
    </metadatos>
    <texto>
      <bloque id="preambulo" tipo="preambulo">
        <version id_norma="BOE-A-2015-10565" fecha_publicacion="20151002" fecha_vigencia="20151003">
          <p class="parrafo_2">La presente Ley establece el régimen jurídico de la actividad de la Administración.</p>
        </version>
      </bloque>
      <bloque id="a1" tipo="precepto" titulo="Artículo 1">
        <version id_norma="BOE-A-2015-10565" fecha_publicacion="20151002" fecha_vigencia="20151003">
          <p class="articulo">Artículo 1. Objeto de la Ley.</p>
          <p class="parrafo">1. La presente Ley establece el régimen jurídico de la actividad de la Administración.</p>
        </version>
      </bloque>
      <bloque id="a2" tipo="precepto" titulo="Artículo 2">
        <version id_norma="BOE-A-2015-10565" fecha_publicacion="20151002" fecha_vigencia="20151003">
          <p class="articulo">Artículo 2. Ámbito de aplicación.</p>
          <p class="parrafo">1. La presente Ley se aplica a la actuación de la Administración.</p>
          <p class="parrafo">2. El plazo máximo para dictar resolución es de 3 meses.</p>
        </version>
      </bloque>
    </texto>
  </data>
</response>
"""

ACT_ID = "BOE-A-2015-10565"
ACT_TITLE = ("Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo "
             "y de Administración Electrónica.")
ACT_ELI = "https://www.boe.es/eli/es/l/2015/10/02/39"
SOURCE_URL = ("https://www.boe.es/datosabiertos/api/legislacion-consolidada"
              "/id/BOE-A-2015-10565")
VERSION_DATE = "2026-11-16"
REFERENCE_DATE = "2026-11-14"
VALUES = {"a1": "1", "a2": "3"}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _plain(xml_text):
    s = re.sub(r"<[^>]+>", " ", xml_text)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&#13;", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


class TestSpainGate(unittest.TestCase):
    """用一个迷你语料（两篇条文）把闸门的每条判据都跑一遍。"""

    def _corpus(self, root, raw=None, slices=None):
        """按官方整件字节重建语料（index＋切片＋卡＋事实账）。

        raw：官方整件字节；slices：指定时用给定的切片字节（模拟「整件里那条
        已被删、切片还在」）。
        """
        if raw is None:
            raw = BOE_XML.encode("utf-8")
        run = os.path.join(root, "runs", "run-test-es")
        off = os.path.join(run, "official")
        os.makedirs(off, exist_ok=True)
        with open(os.path.join(off, "act.xml"), "wb") as fh:
            fh.write(raw)
        articles = {}
        for bid, num in (("a1", "1"), ("a2", "2")):
            if slices is not None and bid in slices:
                blob = slices[bid]
            else:
                m = re.search(rb'<bloque id="' + bid.encode() + rb'"[^>]*>.*?</bloque>',
                              raw, re.S)
                blob = m.group(0)
            with open(os.path.join(off, "%s.xml" % bid), "wb") as fh:
                fh.write(blob)
            text = _plain(blob.decode("utf-8"))
            tm = re.search(rb'titulo="([^"]*)"', blob)
            articles[bid] = {
                "block_id": bid, "num": num,
                "title": tm.group(1).decode("utf-8") if tm else "",
                "article_file": "official/%s.xml" % bid,
                "article_sha256": sha(blob), "article_bytes": len(blob),
                "text_sha256": sha(text.encode("utf-8")), "text_chars": len(text),
                "card_file": "%s.es.card.txt" % bid, "card_sha256": "",
            }
        index = {
            "act_id": ACT_ID,
            "act_eli": ACT_ELI,
            "act_title": ACT_TITLE,
            "act_number": "39/2015",
            "act_range": "Ley",
            "estado_consolidacion": "Finalizado",
            "fecha_disposicion": "20151001",
            "fecha_publicacion": "20151002",
            "fecha_vigencia": "20151003",
            "url_html_consolidada": "https://www.boe.es/buscar/act.php?id=BOE-A-2015-10565",
            "source_url": SOURCE_URL,
            "source_file": "official/act.xml",
            "source_sha256": sha(raw),
            "source_bytes": len(raw),
            "version_date": VERSION_DATE,
            "fetch_reference_date": REFERENCE_DATE,
            "reference_date": REFERENCE_DATE,
            "articles": articles,
        }
        with open(os.path.join(run, "index.json"), "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)
        self._cards_and_facts(root, run, raw, articles)
        return run

    def _cards_and_facts(self, root, run, raw, articles):
        """证据卡 + 事实账（卡字段照抓取器同款；事实钉卡哈希）。"""
        os.makedirs(os.path.join(root, "facts"), exist_ok=True)
        facts = ['schema = "paperkit-fact/3.0"', ""]
        for bid in sorted(articles):
            meta = articles[bid]
            with open(os.path.join(run, meta["article_file"]), "rb") as fh:
                blob = fh.read()
            text = _plain(blob.decode("utf-8"))
            card = "\n".join([
                "# 西班牙法条证据卡（派生件；官方 BOE 合并文本整件与条文切片哈希钉在这里）",
                "ACT_ID: %s" % ACT_ID,
                "ACT_ELI: %s" % ACT_ELI,
                "ACT_TITLE: %s" % ACT_TITLE,
                "ACT_NUMBER: 39/2015",
                "BLOCK_ID: %s" % bid,
                "ARTICLE_NUM: %s" % meta["num"],
                "ARTICLE_TITLE: %s" % meta["title"],
                "VERSION_DATE: %s" % VERSION_DATE,
                "FETCH_DATE: %s" % REFERENCE_DATE,
                "REFERENCE_DATE: %s" % REFERENCE_DATE,
                "SOURCE_FILE: official/act.xml",
                "SOURCE_URL: %s" % SOURCE_URL,
                "OFFICIAL_XML_SHA256: %s" % sha(raw),
                "ARTICLE_SHA256: %s" % sha(blob),
                "TEXT_CHARS: %d" % len(text),
                "TEXT_STATUS: texto consolidado de carácter meramente informativo",
                "LICENCE: Condiciones de reutilización de la AEBOE",
                "ATTRIBUTION: Fuente de los datos: Agencia Estatal Boletín Oficial del Estado",
                "FETCHED_AT: 2026-11-16T09:00:00Z",
                "--- OFFICIAL TEXT ---",
                text[:600],
                "",
            ])
            card_path = os.path.join(run, meta["card_file"])
            _write(card_path, card)
            meta["card_sha256"] = sha(card.encode("utf-8"))
            facts += [
                "[[fact]]",
                'id = "ES-%s"' % bid,
                'claim = "claim %s"' % bid,
                'value = "%s"' % VALUES[bid],
                'source = "runs/run-test-es/%s.es.card.txt"' % bid,
                'source_sha256 = "sha256:%s"' % sha(card.encode("utf-8")),
                'confidence = "high"',
                "derived_from = []",
                "",
            ]
        with open(os.path.join(root, "facts", "40-es-provisions.toml"), "w",
                  encoding="utf-8") as fh:
            fh.write("\n".join(facts))

    def _codes(self, root, run, date=REFERENCE_DATE):
        findings, index = verify_es(root, run, date)
        return [f.code for f in findings], findings, index

    def test_clean_corpus_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            codes, findings, index = self._codes(tmp, run)
            self.assertEqual(codes, [], f"应当全绿，实际：{codes}")
            text, code = render_es(findings, index)
            self.assertEqual(code, 0)
            self.assertIn("绿", text)

    def test_article_slice_tampered_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "official", "a2.xml")
            _write(p, _read(p).replace("3 meses", "4 meses"))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ES_ARTICLE_HASH_MISMATCH", codes)

    def test_official_file_tampered_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "official", "act.xml")
            _write(p, _read(p).replace("3 meses", "4 meses"))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ES_SOURCE_HASH_MISMATCH", codes)

    def test_card_tampered_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "a1.es.card.txt")
            _write(p, _read(p).replace("Objeto de la Ley", "Objeto distinto"))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ES_CARD_SHA256_MISMATCH", codes)

    def test_card_without_hash_is_red(self):
        """证据卡缺哈希声明 ⇒ 红（不能当「无声明即无事」）。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "a1.es.card.txt")
            card = re.sub(r"^ARTICLE_SHA256:.*$", "", _read(p), flags=re.M)
            _write(p, card)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ES_CARD_NO_HASH", codes)

    def test_card_field_mismatch_is_red(self):
        """卡里声明的法件标识与索引对不上 ⇒ 红。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "a1.es.card.txt")
            _write(p, _read(p).replace("ACT_ID: %s" % ACT_ID,
                                       "ACT_ID: BOE-A-1999-00000"))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ES_CARD_FIELD_MISMATCH", codes)

    def test_value_not_in_official_text_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(tmp, "facts", "40-es-provisions.toml")
            _write(p, _read(p).replace('value = "3"', 'value = "999"'))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ES_QUOTE_MISMATCH", codes)

    def test_card_missing_is_red(self):
        """事实指向的西班牙卡不存在 ⇒ 判红，不能静默跳过（否则等于「无不一致即通过」）。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(tmp, "facts", "40-es-provisions.toml")
            _write(p, _read(p).replace("a1.es.card.txt", "a999.es.card.txt"))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ES_CARD_MISSING", codes)

    def test_article_not_in_index_is_red(self):
        """卡在、但条文不在索引里 ⇒ ES_PROV_UNKNOWN。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            idx = os.path.join(run, "index.json")
            with open(idx, encoding="utf-8") as fh:
                d = json.load(fh)
            d["articles"].pop("a1")
            with open(idx, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ES_PROV_UNKNOWN", codes)

    def test_reference_date_mismatch_is_yellow(self):
        """钉的是取件那天的合并文本，拿别的参考日来核 ⇒ 黄项，不是红项。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            codes, findings, _ = self._codes(tmp, run, date="2026-12-01")
            self.assertIn("ES_VERSION_GAP", codes)
            self.assertEqual([c for c in codes if c != "ES_VERSION_GAP"], [],
                             f"版本时点差只许出黄项：{codes}")
            self.assertEqual([f.severity for f in findings
                              if f.code == "ES_VERSION_GAP"], ["yellow"])

    def test_article_removed_from_official_is_red(self):
        """官方整件里那条被删了（切片还在）⇒ 必须判红，不能当作「哈希对得上就过」。"""
        with tempfile.TemporaryDirectory() as tmp:
            raw = BOE_XML.encode("utf-8")
            m = re.search(rb'<bloque id="a2"[^>]*>.*?</bloque>', raw, re.S)
            keep = {"a1": re.search(rb'<bloque id="a1"[^>]*>.*?</bloque>',
                                    raw, re.S).group(0),
                    "a2": m.group(0)}
            raw2 = raw[:m.start()] + raw[m.end():]
            run = self._corpus(tmp, raw=raw2, slices=keep)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ES_ARTICLE_NOT_IN_SOURCE", codes)

    def test_unknown_citation_is_red(self):
        """正文里 \\cite{art-es-a999} 指向语料里没有的条文 ⇒ 红。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            tex = os.path.join(tmp, "paper.tex")
            _write(tex, "Ejemplo: \\cite{art-es-a999}.\n")
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ES_PROV_UNKNOWN", codes)

    def test_known_citation_is_clean(self):
        """正文里 \\cite{art-es-a1} 指向语料里有的条文 ⇒ 不报红。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            tex = os.path.join(tmp, "paper.tex")
            _write(tex, "Ejemplo: \\cite{art-es-a1}.\n")
            codes, _, _ = self._codes(tmp, run)
            self.assertNotIn("ES_PROV_UNKNOWN", codes)

    def test_french_gate_skips_spain_cards(self):
        """西班牙证据卡不能让法国闸误判红。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._corpus(tmp)
            fr_corpus = os.path.join(tmp, "runs", "run-test-fr")
            os.makedirs(fr_corpus, exist_ok=True)
            with open(os.path.join(fr_corpus, "index.json"), "w", encoding="utf-8") as fh:
                json.dump({"provisions": {}}, fh)
            findings, _corpus = verify_fr(tmp, fr_corpus, REFERENCE_DATE)
            self.assertEqual([f.code for f in findings], [],
                             f"法国闸不应因西班牙卡报错：{[f.code for f in findings]}")


if __name__ == "__main__":
    unittest.main()
