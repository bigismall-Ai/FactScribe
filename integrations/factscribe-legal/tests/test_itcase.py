#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""意大利宪法法院判例专闸（verify-it-case）的自测：标准库 unittest，网络零依赖。

用一个迷你合成档案（2 件判决）把闸门的每条判据都跑一遍：形状照 Corte
costituzionale 开放数据的判决档案 XML（根 <elenco_pronunce>，每件判决一个
<pronuncia>，内含 <pronuncia_testata> / <pronuncia_testo>），切片＝档案字节的
原样子串，哈希是真算的，卡是照抓取器同款字段造的。

另有一组「真件 fixture」用例：对入库的真判决 run 目录跑 verify 全绿，并锁住
「index.text_sha256 ＝ 闸侧现推 sha256」（确定性锁）与 testata 已知值。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from factscribe_legal.it_case_verify import (  # noqa: E402
    _itcase_plain, render_it_case, verify_it_case,
)
from factscribe_legal.verify import verify as verify_fr  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LEGAL = os.path.dirname(HERE)
CORPUS = os.path.join(LEGAL, "corpus")
FIXTURE_RUN = os.path.join(CORPUS, "it-case", "run-20261116-itcase-1956_1980")

TIER = "1956_1980"
SOURCE_URL = ("https://dati.cortecostituzionale.it/opendata/distribuzione/"
              "CC_OpenPronunce_1956_1980.zip")
LAST_MODIFIED = "Mon, 16 Nov 2026 04:11:54 GMT"
REFERENCE_DATE = "2026-11-16"

# 迷你合成档案：两件判决（形状照 Corte costituzionale 判决档案 XML）。
#   判决一：正文含意语日期「11 gennaio 1956」、金额「1.000,00」，
#           ECLI 被 NBSP 拆开（ECLI:IT:COST: 1956:1）
#   判决二：正文含被跨行拆开的 ECLI（ECLI:IT:COST:&#13;⏎ 1956:2）
#           与被跨行拆开的案号（n.&#13;⏎ 12）
ARCHIVE = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<elenco_pronunce>
<pronuncia><pronuncia_testata><anno_pronuncia>1956</anno_pronuncia>\
<numero_pronuncia>1</numero_pronuncia><ecli>ECLI:IT:COST:1956:1</ecli>\
<tipologia_pronuncia>S</tipologia_pronuncia><presidente>DE NICOLA</presidente>\
<relatore_pronuncia>Gaetano Azzariti</relatore_pronuncia><redattore_pronuncia/>\
<data_decisione>11/01/1956</data_decisione><data_deposito>20/01/1956</data_deposito>\
</pronuncia_testata><pronuncia_testo><collegio><titolo>LA CORTE COSTITUZIONALE\
</titolo></collegio><epigrafe><titolo>SENTENZA</titolo></epigrafe><testo>\
<paragrafo>La Corte ha deciso in data 11 gennaio 1956 per la somma di \
&#13;\n 1.000,00 euro e per l&#39;apposizione del giudice. \
Riferimento ECLI:IT:COST: 1956:\
&#13;\n 1.</paragrafo></testo><dispositivo>\
<paragrafo>Palazzo della Consulta, l&#39;11 gennaio 1956.</paragrafo>\
</dispositivo></pronuncia_testo></pronuncia>
<pronuncia><pronuncia_testata><anno_pronuncia>1956</anno_pronuncia>\
<numero_pronuncia>2</numero_pronuncia><ecli>ECLI:IT:COST:1956:2</ecli>\
<tipologia_pronuncia>S</tipologia_pronuncia><presidente>DE NICOLA</presidente>\
<relatore_pronuncia>Giuseppe Cappi</relatore_pronuncia><redattore_pronuncia/>\
<data_decisione>14/06/1956</data_decisione><data_deposito>23/06/1956</data_deposito>\
</pronuncia_testata><pronuncia_testo><collegio><titolo>LA CORTE COSTITUZIONALE\
</titolo></collegio><epigrafe><titolo>SENTENZA</titolo></epigrafe><testo>\
<paragrafo>La sentenza reca il numero ECLI:IT:COST:\
&#13;\n 1956:2 e la data 14 giugno 1956. Importo complessivo 2.500,50 euro. \
Il ricorso è stato deciso con sentenza n.\
&#13;\n 12 del 1956. Identificativo RIF\u00a02026\u00a0001.</paragrafo></testo>\
<dispositivo><paragrafo>Roma, 14 giugno 1956.</paragrafo></dispositivo>\
</pronuncia_testo></pronuncia>
</elenco_pronunce>
"""

SLICE_RE = re.compile(rb"<pronuncia>.*?</pronuncia>", re.S)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _load_fetcher():
    """把 tools/fetch_corpus.py 直接当脚本载入（仓内工具与包同目录树，
    脚本直跑不 import 包——照 es `_es_plain` 先例）。"""
    spec = importlib.util.spec_from_file_location(
        "fetch_corpus_itcase",
        os.path.join(LEGAL, "tools", "fetch_corpus.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestItCaseGate(unittest.TestCase):
    """用一个迷你合成档案（两件判决）把闸门的每条判据都跑一遍。"""

    def _corpus(self, root, archive=None):
        """按档案字节造 run 形语料（index＋切片＋卡＋事实账）。"""
        raw = ARCHIVE.encode("utf-8") if archive is None else archive
        run = os.path.join(root, "runs", "run-test-itcase")
        off = os.path.join(run, "official")
        os.makedirs(off, exist_ok=True)
        judgments = {}
        for blob in SLICE_RE.findall(raw):
            root_el = None
            try:
                import xml.etree.ElementTree as ET
                root_el = ET.fromstring(blob)
            except Exception:  # noqa: BLE001
                continue
            tt = root_el.find("pronuncia_testata")
            ecli = (tt.find("ecli").text or "").strip()
            slug = ecli.replace(":", "-")
            slice_rel = "official/%s.xml" % slug
            with open(os.path.join(run, slice_rel), "wb") as fh:
                fh.write(blob)
            text = _itcase_plain(blob)
            card_rel = "%s.itcase.card.txt" % slug
            card_path = os.path.join(run, card_rel)
            _write(card_path, self._card(slug, blob, text))
            judgments[slug] = {
                "ecli": ecli,
                "anno": (tt.find("anno_pronuncia").text or "").strip(),
                "numero": (tt.find("numero_pronuncia").text or "").strip(),
                "tipologia": (tt.find("tipologia_pronuncia").text or "").strip(),
                "presidente": (tt.find("presidente").text or "").strip(),
                "relatore": (tt.find("relatore_pronuncia").text or "").strip(),
                "data_decisione": (tt.find("data_decisione").text or "").strip(),
                "data_deposito": (tt.find("data_deposito").text or "").strip(),
                "slice_file": slice_rel,
                "slice_sha256": sha(blob),
                "slice_bytes": len(blob),
                "text_sha256": sha(text.encode("utf-8")),
                "text_chars": len(text),
                "card_file": card_rel,
                "card_sha256": sha(_read(card_path).encode("utf-8")),
            }
        index = {
            "tier": TIER,
            "source_url": SOURCE_URL,
            "source_zip_sha256": "",
            "source_zip_bytes": 14887390,
            "source_zip_last_modified": LAST_MODIFIED,
            "fetch_reference_date": REFERENCE_DATE,
            "generator": "tools/fetch_corpus.py",
            "judgments": judgments,
        }
        with open(os.path.join(run, "index.json"), "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=1, sort_keys=True)
        self._facts(root, run, judgments)
        return run

    def _card(self, slug, blob, text):
        """证据卡（字段序照抓取器同款）。"""
        import xml.etree.ElementTree as ET
        tt = ET.fromstring(blob).find("pronuncia_testata")

        def g(tag):
            el = tt.find(tag)
            return (el.text or "").strip() if el is not None else ""

        dd = g("data_decisione")
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", dd)
        iso = "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1))) if m else ""
        return "\n".join([
            "# 意大利宪法法院判例证据卡（派生件；官方判决切片哈希钉在这里）",
            "ECLI: %s" % g("ecli"),
            "ANNO_PRONUNCIA: %s" % g("anno_pronuncia"),
            "NUMERO_PRONUNCIA: %s" % g("numero_pronuncia"),
            "TIPOLOGIA: %s" % g("tipologia_pronuncia"),
            "PRESIDENTE: %s" % g("presidente"),
            "RELATORE: %s" % g("relatore_pronuncia"),
            "DATA_DECISIONE: %s" % dd,
            "DATA_DECISIONE_ISO: %s" % iso,
            "DATA_DEPOSITO: %s" % g("data_deposito"),
            "SOURCE_FILE: official/%s.xml" % slug,
            "SOURCE_URL: %s#%s" % (SOURCE_URL, slug),
            "OFFICIAL_XML_SHA256: %s" % sha(blob),
            "TEXT_SHA256: %s" % sha(text.encode("utf-8")),
            "TEXT_CHARS: %d" % len(text),
            "LICENCE: Creative Commons CC BY-SA 3.0 (Corte costituzionale, dati aperti)",
            "ATTRIBUTION: Fonte: Corte costituzionale della Repubblica italiana",
            "FETCHED_AT: 2026-11-16T14:19:43Z",
            "--- OFFICIAL TEXT ---",
            text[:600] + ("…" if len(text) > 600 else ""),
            "",
        ])

    def _facts(self, root, run, judgments):
        """事实账：每判决两 fact（ECLI 字面＋裁判日 ISO）。"""
        os.makedirs(os.path.join(root, "facts"), exist_ok=True)
        lines = ['schema = "paperkit-fact/3.0"', ""]
        for slug in sorted(judgments):
            meta = judgments[slug]
            card_path = os.path.join(run, meta["card_file"])
            card_sha = sha(_read(card_path).encode("utf-8"))
            dd = meta["data_decisione"]
            m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", dd)
            iso = "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1))) if m else ""
            base = "ITCASE-%s-%s" % (meta["anno"], meta["numero"])
            lines += [
                "[[fact]]",
                'id = "%s-ECLI"' % base,
                'claim = "意大利宪法法院判决 ECLI（官方件引用示例）"',
                'value = "%s"' % meta["ecli"],
                'source = "runs/run-test-itcase/%s"' % meta["card_file"],
                'source_sha256 = "sha256:%s"' % card_sha,
                'confidence = "high"',
                "derived_from = []",
                "",
                "[[fact]]",
                'id = "%s-DATE"' % base,
                'claim = "意大利宪法法院判决裁判日（官方件引用示例）"',
                'value = "%s"' % iso,
                'source = "runs/run-test-itcase/%s"' % meta["card_file"],
                'source_sha256 = "sha256:%s"' % card_sha,
                'confidence = "high"',
                "derived_from = []",
                "",
            ]
            if slug == "ECLI-IT-COST-1956-2":
                # 只在正文里以「被 NBSP 拆开」的形态存在的标识：归一后是
                # 「RIF 2026 001」，紧致形才是「RIF2026001」⇒ 锁住紧致比较
                lines += [
                    "[[fact]]",
                    'id = "%s-PROTO"' % base,
                    'claim = "判决卷宗标识（正文里被 NBSP 拆开）"',
                    'value = "RIF2026001"',
                    'source = "runs/run-test-itcase/%s"' % meta["card_file"],
                    'source_sha256 = "sha256:%s"' % card_sha,
                    'confidence = "high"',
                    "derived_from = []",
                    "",
                ]
        with open(os.path.join(root, "facts", "50-itcase.toml"), "w",
                  encoding="utf-8") as fh:
            fh.write("\n".join(lines))

    def _codes(self, root, run):
        findings, index = verify_it_case(root, run)
        return [f.code for f in findings], findings, index

    # ---- 净语料 ----
    def test_clean_corpus_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            codes, findings, index = self._codes(tmp, run)
            self.assertEqual(codes, [], f"应当全绿，实际：{codes}")
            text, code = render_it_case(findings, index)
            self.assertEqual(code, 0)
            self.assertIn("绿", text)

    # ---- 切片改坏 ----
    def test_slice_tampered_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "official", "ECLI-IT-COST-1956-2.xml")
            with open(p, "rb") as fh:
                blob = fh.read()
            with open(p, "wb") as fh:
                fh.write(blob.replace(b"2.500,50", b"9.999,99"))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ITCASE_SLICE_HASH_MISMATCH", codes)

    # ---- 切片被改坏到 XML 不再合法：红码落定，不许异常穿透 ----
    def test_slice_broken_xml_is_red_not_crash(self):
        """官方切片标签名内插字节（`<ecli>`→`<Xecli>`，XML 非法）⇒ 红码 finding。

        闸门必须**哈希先行**：先对账再推正文，材料坏了落闭集内的红码，
        不许把 ET.ParseError 抛穿 CLI（那样只有堆栈、没有 finding）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "official", "ECLI-IT-COST-1956-1.xml")
            with open(p, "rb") as fh:
                blob = fh.read()
            broken = blob.replace(b"<ecli>", b"<Xecli>", 1)
            self.assertNotEqual(broken, blob, "切片没改到（文件里没有 <ecli>）")
            with open(p, "wb") as fh:
                fh.write(broken)
            try:
                codes, findings, _ = self._codes(tmp, run)
            except Exception as e:  # noqa: BLE001
                self.fail(f"官方件改坏不许把异常抛给 CLI：{e!r}")
            self.assertEqual(set(codes), {"ITCASE_SLICE_HASH_MISMATCH"},
                             f"应当只落哈希红码：{codes}")
            self.assertTrue(all(f.severity == "red" for f in findings),
                            "红码必须是 red 级")

    # ---- 哈希声明与坏切片一致（索引同坏）：仍是红码，不抛异常 ----
    def test_broken_xml_with_consistent_hash_is_red(self):
        """索引与卡都声明了坏切片的哈希（数据自身坏）⇒ 红码＋「解析失败」文案。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            slug = "ECLI-IT-COST-1956-1"
            p = os.path.join(run, "official", "%s.xml" % slug)
            with open(p, "rb") as fh:
                blob = fh.read()
            broken = blob.replace(b"<ecli>", b"<Xecli>", 1)
            self.assertNotEqual(broken, blob, "切片没改到（文件里没有 <ecli>）")
            with open(p, "wb") as fh:
                fh.write(broken)
            bad_sha = sha(broken)

            # 索引：切片哈希跟着坏切片走（索引与切片一致地坏）
            idx_path = os.path.join(run, "index.json")
            with open(idx_path, encoding="utf-8") as fh:
                d = json.load(fh)
            d["judgments"][slug]["slice_sha256"] = bad_sha
            with open(idx_path, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False)

            # 卡：官方件哈希声明跟着坏切片走（并把事实账钉的卡哈希同步过去）
            card_path = os.path.join(run, "%s.itcase.card.txt" % slug)
            old_card_sha = sha(_read(card_path).encode("utf-8"))
            card = _read(card_path).replace(
                "OFFICIAL_XML_SHA256: %s" % sha(blob),
                "OFFICIAL_XML_SHA256: %s" % bad_sha)
            _write(card_path, card)
            facts_path = os.path.join(tmp, "facts", "50-itcase.toml")
            _write(facts_path, _read(facts_path).replace(
                old_card_sha, sha(_read(card_path).encode("utf-8"))))

            try:
                codes, findings, _ = self._codes(tmp, run)
            except Exception as e:  # noqa: BLE001
                self.fail(f"索引同坏也不许把异常抛给 CLI：{e!r}")
            self.assertEqual(set(codes), {"ITCASE_SLICE_HASH_MISMATCH"},
                             f"应当只落哈希红码：{codes}")
            msgs = [f.message for f in findings
                    if f.code == "ITCASE_SLICE_HASH_MISMATCH"]
            self.assertTrue(any("解析失败" in m for m in msgs),
                            f"应当有「解析失败」文案：{msgs}")

    # ---- 卡改坏（钉哈希不符）----
    def test_card_tampered_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "ECLI-IT-COST-1956-1.itcase.card.txt")
            _write(p, _read(p).replace("DE NICOLA", "DE NICOLA X"))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ITCASE_CARD_SHA256_MISMATCH", codes)

    # ---- 卡缺哈希声明 ----
    def test_card_without_hash_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "ECLI-IT-COST-1956-1.itcase.card.txt")
            _write(p, re.sub(r"^OFFICIAL_XML_SHA256:.*$", "", _read(p), flags=re.M))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ITCASE_CARD_NO_HASH", codes)

    # ---- 卡字段与索引对不上 ----
    def test_card_field_mismatch_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "ECLI-IT-COST-1956-1.itcase.card.txt")
            _write(p, _read(p).replace("NUMERO_PRONUNCIA: 1",
                                       "NUMERO_PRONUNCIA: 7"))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ITCASE_CARD_FIELD_MISMATCH", codes)

    # ---- 卡内嵌正文被改 ----
    def test_embedded_text_tampered_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "ECLI-IT-COST-1956-1.itcase.card.txt")
            _write(p, _read(p).replace("11 gennaio 1956", "12 gennaio 1955"))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ITCASE_CARD_TEXT_DIVERGED", codes)

    # ---- 卡缺失 ----
    def test_card_missing_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(tmp, "facts", "50-itcase.toml")
            _write(p, _read(p).replace("ECLI-IT-COST-1956-1.itcase.card.txt",
                                       "ECLI-IT-COST-1956-9.itcase.card.txt"))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ITCASE_CARD_MISSING", codes)

    # ---- 卡 ECLI 不在索引 ----
    def test_ecli_not_in_index_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            idx = os.path.join(run, "index.json")
            with open(idx, encoding="utf-8") as fh:
                d = json.load(fh)
            d["judgments"].pop("ECLI-IT-COST-1956-1")
            with open(idx, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ITCASE_PROV_UNKNOWN", codes)

    # ---- 事实值在正文找不到 ----
    def test_value_not_in_official_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(tmp, "facts", "50-itcase.toml")
            _write(p, _read(p).replace('value = "ECLI:IT:COST:1956:1"',
                                       'value = "999"'))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ITCASE_VALUE_NOT_IN_OFFICIAL", codes)

    # ---- 金额三种写法都算绿 ----
    def test_italian_amount_forms_are_green(self):
        for value in ("1000.00", "1.000,00", "1000,00"):
            with tempfile.TemporaryDirectory() as tmp:
                run = self._corpus(tmp)
                p = os.path.join(tmp, "facts", "50-itcase.toml")
                _write(p, _read(p).replace(
                    'value = "ECLI:IT:COST:1956:1"', 'value = "%s"' % value))
                codes, _, _ = self._codes(tmp, run)
                self.assertEqual(codes, [],
                                 f"金额写法 {value} 应当归一后命中：{codes}")

    # ---- 日期归一：ISO fact 对正文意语月名 ----
    def test_italian_month_date_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(tmp, "facts", "50-itcase.toml")
            # 判决一的裁判日是 11/01/1956，正文写「11 gennaio 1956」
            _write(p, _read(p).replace('value = "1956-01-11"',
                                       'value = "1956-01-11"'))
            codes, _, _ = self._codes(tmp, run)
            self.assertEqual(codes, [], f"意语月名日期应当归一命中：{codes}")

    def test_wrong_date_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(tmp, "facts", "50-itcase.toml")
            _write(p, _read(p).replace('value = "1956-01-11"',
                                       'value = "1956-01-12"'))
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ITCASE_VALUE_NOT_IN_OFFICIAL", codes)

    def test_card_date_not_in_text_is_red(self):
        """卡里的裁判日期在正文找不到 ⇒ ITCASE_DATE_MISMATCH。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            p = os.path.join(run, "ECLI-IT-COST-1956-1.itcase.card.txt")
            card = _read(p)
            card = card.replace("DATA_DECISIONE: 11/01/1956",
                                "DATA_DECISIONE: 03/03/1953")
            card = card.replace("DATA_DECISIONE_ISO: 1956-01-11",
                                "DATA_DECISIONE_ISO: 1953-03-03")
            _write(p, card)
            codes, _, _ = self._codes(tmp, run)
            self.assertIn("ITCASE_DATE_MISMATCH", codes)

    # ---- NBSP／跨行 ECLI 与案号 ----
    def test_nbsp_and_broken_line_are_green(self):
        """正文里 ECLI 被 NBSP 与换行拆开，归一后仍须命中（事实值是 ECLI 字面）。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            findings, index = verify_it_case(tmp, run)
            self.assertEqual([f.code for f in findings], [],
                             "NBSP／跨行文本应当归一后命中")
            # 判决一：ECLI 被 NBSP 拆开
            p1 = os.path.join(run, "official", "ECLI-IT-COST-1956-1.xml")
            with open(p1, "rb") as fh:
                blob1 = fh.read()
            self.assertIn(b"ECLI:IT:COST:\xc2\xa0", blob1)
            # 判决二：ECLI 被跨行拆开、案号被跨行拆开
            p2 = os.path.join(run, "official", "ECLI-IT-COST-1956-2.xml")
            with open(p2, "rb") as fh:
                blob2 = fh.read()
            self.assertIn(b"ECLI:IT:COST:&#13;\n", blob2)
            self.assertIn(b"n.&#13;\n 12 del 1956", blob2)
            # 归一后：NBSP 与换行都成了空格 ⇒ 正文里那处 ECLI 是断开的
            self.assertIn("ECLI:IT:COST: 1956: 1", _itcase_plain(blob1))
            self.assertIn("ECLI:IT:COST: 1956:2", _itcase_plain(blob2))
            self.assertIn("RIF 2026 001", _itcase_plain(blob2))
            # 紧致形里标识才是完整的（这是「正文里明明有」不被误判成「找不到」的依据）
            self.assertIn("ECLI:IT:COST:1956:1",
                          re.sub(r"\s+", "", _itcase_plain(blob1)))
            self.assertIn("ECLI:IT:COST:1956:2",
                          re.sub(r"\s+", "", _itcase_plain(blob2)))
            self.assertIn("RIF2026001",
                          re.sub(r"\s+", "", _itcase_plain(blob2)))

    # ---- 跨域互不误伤 ----
    def test_french_gate_skips_itcase_cards(self):
        """意大利判例证据卡不能让法国闸误判红。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._corpus(tmp)
            fr_corpus = os.path.join(tmp, "runs", "run-test-fr")
            os.makedirs(fr_corpus, exist_ok=True)
            with open(os.path.join(fr_corpus, "index.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"provisions": {}}, fh)
            findings, _corpus = verify_fr(tmp, fr_corpus, REFERENCE_DATE)
            self.assertEqual([f.code for f in findings], [],
                             f"法国闸不应因意大利判例卡报错："
                             f"{[f.code for f in findings]}")

    def test_itcase_gate_skips_spain_cards(self):
        """西班牙证据卡不进意大利判例闸。"""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._corpus(tmp)
            es_card = os.path.join(run, "a1.es.card.txt")
            _write(es_card, "\n".join([
                "# 西班牙法条证据卡",
                "ACT_ID: BOE-A-2015-10565",
                "BLOCK_ID: a1",
                "OFFICIAL_XML_SHA256: %s" % sha(b"x"),
                "ARTICLE_SHA256: %s" % sha(b"y"),
                "",
            ]))
            os.makedirs(os.path.join(tmp, "facts"), exist_ok=True)
            with open(os.path.join(tmp, "facts", "40-es-provisions.toml"), "w",
                      encoding="utf-8") as fh:
                fh.write("\n".join([
                    'schema = "paperkit-fact/3.0"', "",
                    "[[fact]]",
                    'id = "ES-a1"',
                    'claim = "claim a1"',
                    'value = "3"',
                    'source = "runs/run-test-itcase/a1.es.card.txt"',
                    'source_sha256 = "sha256:%s"' % sha(b"z"),
                    'confidence = "high"',
                    "derived_from = []",
                    "",
                ]))
            codes, _, _ = self._codes(tmp, run)
            self.assertEqual(codes, [], f"意大利判例闸不应认西班牙卡：{codes}")


class TestItCaseFixture(unittest.TestCase):
    """真件 fixture（入库的两件真判决）。"""

    def test_fixture_run_is_green(self):
        findings, index = verify_it_case(FIXTURE_RUN, FIXTURE_RUN)
        self.assertEqual([f.code for f in findings], [],
                         f"真件 fixture 应当全绿：{[f.code for f in findings]}")

    def test_fixture_index_text_sha_matches_gate(self):
        """确定性锁：index.text_sha256 ＝ 闸侧现推 sha256（逐字节同）。"""
        with open(os.path.join(FIXTURE_RUN, "index.json"), encoding="utf-8") as fh:
            index = json.load(fh)
        for slug, meta in index["judgments"].items():
            with open(os.path.join(FIXTURE_RUN, meta["slice_file"]), "rb") as fh:
                blob = fh.read()
            self.assertEqual(sha(blob), meta["slice_sha256"],
                             f"{slug} 切片哈希与索引不符")
            self.assertEqual(sha(_itcase_plain(blob).encode("utf-8")),
                             meta["text_sha256"], f"{slug} 正文哈希与索引不符")

    def test_fetcher_plain_matches_gate_plain(self):
        """抓取器内联的 _itcase_plain 与闸模块的同款算法：同输入同 sha。"""
        fc = _load_fetcher()
        with open(os.path.join(FIXTURE_RUN, "index.json"), encoding="utf-8") as fh:
            index = json.load(fh)
        for slug, meta in index["judgments"].items():
            with open(os.path.join(FIXTURE_RUN, meta["slice_file"]), "rb") as fh:
                blob = fh.read()
            self.assertEqual(fc._itcase_plain(blob), _itcase_plain(blob),
                             f"{slug} 抓取器与闸的纯文本不一致")
            self.assertEqual(sha(fc._itcase_plain(blob).encode("utf-8")),
                             meta["text_sha256"])

    def test_fixture_testata_known_values(self):
        """testata 字段＝已知值。"""
        want = {
            "ECLI-IT-COST-1956-1": ("ECLI:IT:COST:1956:1", "05/06/1956", "1956", "1"),
            "ECLI-IT-COST-1956-2": ("ECLI:IT:COST:1956:2", "14/06/1956", "1956", "2"),
        }
        with open(os.path.join(FIXTURE_RUN, "index.json"), encoding="utf-8") as fh:
            index = json.load(fh)
        for slug, (ecli, dd, anno, numero) in want.items():
            meta = index["judgments"].get(slug)
            self.assertIsNotNone(meta, f"fixture 缺判决 {slug}")
            self.assertEqual(meta["ecli"], ecli)
            self.assertEqual(meta["data_decisione"], dd)
            self.assertEqual(meta["anno"], anno)
            self.assertEqual(meta["numero"], numero)

    def test_fixture_bytes_are_untouched(self):
        """官方件原字节（逐字节对账）。"""
        want = {
            "ECLI-IT-COST-1956-1.xml":
                "1b014aa29ce05def5c2f054a9caddb0307739fcf6803668f18b704446df86141",
            "ECLI-IT-COST-1956-2.xml":
                "5b882166e27cff9c4d2ec74dabf1d7367fc099953c538fa8c50b20c7f770f773",
        }
        for name, digest in want.items():
            path = os.path.join(FIXTURE_RUN, "official", name)
            with open(path, "rb") as fh:
                self.assertEqual(sha(fh.read()), digest, f"{name} 原字节被改过")

    def test_fixture_attribution_file_exists(self):
        """Attribution 文件在位（署名＋许可＋同方式共享声明）。"""
        path = os.path.join(CORPUS, "it-case", "ATTRIBUTION.md")
        self.assertTrue(os.path.exists(path), "缺 ATTRIBUTION.md")
        text = _read(path)
        self.assertIn("CC BY-SA 3.0", text)
        self.assertIn("Corte costituzionale", text)
        self.assertIn("相同方式共享", text)
        for name, digest in (("ECLI-IT-COST-1956-1.xml", None),
                             ("ECLI-IT-COST-1956-2.xml", None)):
            self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
