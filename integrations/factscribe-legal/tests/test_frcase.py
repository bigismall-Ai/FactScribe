#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法国判例专闸（verify-fr-case）的自测：标准库 unittest，网络零依赖。

三块：
  1. **真件复跑**：仓内 `corpus/fr-case/` 的 4 件真判决（DILA INCA 官方字节）
     造临时项目 ⇒ 闸全绿；逐码触发（改哈希/删件/改值/改案号/改日期/改内嵌段）。
  2. **法式归一单测**：`300.000`→300000、`3 500`→3500、`1 234,56`→1234.56、
     NBSP 变体、`01-16.595`↔`01-16595`、法文月名日期双向。
  3. **抓取层**：本地造一个假 tar.gz 前缀（零网络）⇒ 前缀解包、XML 抽取、
     索引生成；Range 被忽略时必须 fail-closed（拒绝下载全量）。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import hashlib
import io
import json
import os
import random
import re
import shutil
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from factscribe_legal.fr_case_reader import (fr_date_to_iso,  # noqa: E402
                                            fr_numbers_in, norm_case_no,
                                            norm_fr_number, parse_meta, to_plain)
from factscribe_legal.fr_case_verify import (render_fr_case,  # noqa: E402
                                             verify_fr_case)
from factscribe_legal.verify import verify as verify_fr  # noqa: E402

import fetch_corpus  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_DIR = os.path.join(HERE, "..", "corpus", "fr-case")
RUN_NAME = "run-20261116-inca"

# 四件真判决的正文里确实存在的数值（法式归一后的规范形）
VALUES = {
    "JURITEXT000006953017": "1166",
    "JURITEXT000007100000": "499",
    "JURITEXT000007471838": "3500",
    "JURITEXT000006951547": "300000",
}
# 点千分位的写法（归一后应与 VALUES 一致）
DOT_THOUSANDS = "300000"


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _index():
    with open(os.path.join(CORPUS_DIR, RUN_NAME, "index.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


def make_project(tmp, case_ids=None):
    """照 corpus/fr-case 造一个临时项目（事实账指向判例证据卡）。"""
    index = _index()
    cases = index["cases"]
    ids = list(case_ids) if case_ids else sorted(cases)
    proj = os.path.join(tmp, "proj")
    prun = os.path.join(proj, "runs", RUN_NAME)
    os.makedirs(os.path.join(prun, "official"), exist_ok=True)
    os.makedirs(os.path.join(proj, "facts"), exist_ok=True)
    src = os.path.join(CORPUS_DIR, RUN_NAME)
    facts = ['schema = "paperkit-fact/3.0"', ""]
    for cid in ids:
        meta = cases[cid]
        shutil.copyfile(os.path.join(src, meta["xml_file"]),
                        os.path.join(prun, "official", "%s.xml" % cid))
        shutil.copyfile(os.path.join(src, meta["txt_file"]),
                        os.path.join(prun, "official", "%s.txt" % cid))
        shutil.copyfile(os.path.join(src, meta["card_file"]),
                        os.path.join(prun, meta["card_file"]))
        card_path = os.path.join(prun, meta["card_file"])
        facts += [
            "[[fact]]",
            'id = "F-%s"' % cid,
            'claim = "判决正文数值（官方件引用示例）"',
            'value = "%s"' % VALUES[cid],
            'source = "runs/%s/%s"' % (RUN_NAME, meta["card_file"]),
            'source_sha256 = "sha256:%s"' % sha_file(card_path),
            'confidence = "high"',
            "derived_from = []",
            "",
        ]
    _write(os.path.join(proj, "facts", "50-fr-case.toml"), "\n".join(facts))
    return proj


def repin_card(proj, case_id):
    """改完卡片后同步改事实账钉的哈希（模拟「攻击者连账一起改」）。"""
    facts_path = os.path.join(proj, "facts", "50-fr-case.toml")
    card_rel = "runs/%s/%s.fr-case.card.txt" % (RUN_NAME, case_id)
    card_path = os.path.join(proj, card_rel)
    text = _read(facts_path)
    text = re.sub(r'(source = "%s"\nsource_sha256 = "sha256:)[0-9a-f]{64}' % re.escape(card_rel),
                  lambda m: m.group(1) + sha_file(card_path), text)
    _write(facts_path, text)


class TestFrCaseRealCorpus(unittest.TestCase):
    """仓内 4 件真判决：逐件建项目跑闸。"""

    def test_each_real_case_is_green(self):
        index = _index()
        for cid in sorted(index["cases"]):
            with self.subTest(case=cid):
                with tempfile.TemporaryDirectory() as tmp:
                    proj = make_project(tmp, [cid])
                    findings, stats = verify_fr_case(proj)
                    self.assertEqual([f.code for f in findings], [],
                                     f"{cid} 应当全绿：{[f.code for f in findings]}")
                    text, code = render_fr_case(findings, stats)
                    self.assertEqual(code, 0)
                    self.assertIn("绿", text)
                    self.assertEqual(stats["cards"], 1)

    def test_all_real_cases_together_are_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp)
            findings, stats = verify_fr_case(proj)
            self.assertEqual([f.code for f in findings], [],
                             f"应当全绿：{[f.code for f in findings]}")
            self.assertEqual(stats["cards"], 4)
            self.assertEqual(stats["facts"], 4)

    def test_values_are_really_in_official_text(self):
        """值本身必须真在官方正文里（法式归一后命中）——防「测试自己骗自己」。"""
        index = _index()
        for cid, val in VALUES.items():
            txt = _read(os.path.join(CORPUS_DIR, RUN_NAME, "official",
                                     "%s.txt" % cid))
            self.assertIn(norm_fr_number(val), fr_numbers_in(txt),
                          "%s 的值 %s 不在官方正文里" % (cid, val))
        # 点千分位与空格千分位归一到同一形
        self.assertEqual(norm_fr_number("300.000"), norm_fr_number(DOT_THOUSANDS))

    def test_iso_and_french_date_both_match(self):
        """ISO 与法文月名两种日期写法都要能命中同一件判决。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            facts_path = os.path.join(proj, "facts", "50-fr-case.toml")
            text = _read(facts_path)
            text = text.replace('value = "3500"',
                                'value = "29 septembre 2004"')
            _write(facts_path, text)
            findings, _ = verify_fr_case(proj)
            self.assertEqual([f.code for f in findings], [],
                             f"法文日期应命中：{[f.code for f in findings]}")


class TestFrCaseCodes(unittest.TestCase):
    """逐码触发：每个 FR_ 码至少一例红。"""

    def _codes(self, proj):
        findings, _ = verify_fr_case(proj)
        return [f.code for f in findings]

    def test_card_missing_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            os.remove(os.path.join(proj, "runs", RUN_NAME,
                                   "JURITEXT000007471838.fr-case.card.txt"))
            self.assertIn("FR_CASE_CARD_MISSING", self._codes(proj))

    def test_official_missing_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            os.remove(os.path.join(proj, "runs", RUN_NAME, "official",
                                   "JURITEXT000007471838.xml"))
            self.assertIn("FR_CASE_OFFICIAL_MISSING", self._codes(proj))

    def test_official_txt_missing_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            os.remove(os.path.join(proj, "runs", RUN_NAME, "official",
                                   "JURITEXT000007471838.txt"))
            self.assertIn("FR_CASE_OFFICIAL_MISSING", self._codes(proj))

    def test_card_without_hash_is_red(self):
        """卡里缺哈希声明 ⇒ 红（不能当「无声明即无事」）。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            card = os.path.join(proj, "runs", RUN_NAME,
                                "JURITEXT000007471838.fr-case.card.txt")
            _write(card, re.sub(r"^OFFICIAL_XML_SHA256:.*$", "",
                                _read(card), flags=re.M))
            repin_card(proj, "JURITEXT000007471838")
            self.assertIn("FR_CASE_CARD_NO_HASH", self._codes(proj))

    def test_official_tampered_is_red(self):
        """官方纯文本还原件被改一字节 ⇒ 红（fail-closed）。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            p = os.path.join(proj, "runs", RUN_NAME, "official",
                             "JURITEXT000007471838.txt")
            with open(p, "rb") as fh:
                raw = bytearray(fh.read())
            raw[100] = ord("X")
            with open(p, "wb") as fh:
                fh.write(bytes(raw))
            self.assertIn("FR_CASE_OFFICIAL_HASH_MISMATCH", self._codes(proj))

    def test_official_xml_tampered_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            p = os.path.join(proj, "runs", RUN_NAME, "official",
                             "JURITEXT000007471838.xml")
            with open(p, "rb") as fh:
                raw = bytearray(fh.read())
            raw[200] = ord("X")
            with open(p, "wb") as fh:
                fh.write(bytes(raw))
            self.assertIn("FR_CASE_OFFICIAL_HASH_MISMATCH", self._codes(proj))

    def test_card_tampered_is_red(self):
        """卡自身被改（事实账钉的哈希没同步）⇒ 红。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            card = os.path.join(proj, "runs", RUN_NAME,
                                "JURITEXT000007471838.fr-case.card.txt")
            _write(card, _read(card).replace("Rejet", "Rejet (modifié)"))
            self.assertIn("FR_CASE_CARD_SHA256_MISMATCH", self._codes(proj))

    def test_value_not_in_official_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            facts = os.path.join(proj, "facts", "50-fr-case.toml")
            _write(facts, _read(facts).replace('value = "3500"',
                                               'value = "999999"'))
            self.assertIn("FR_CASE_VALUE_NOT_IN_OFFICIAL", self._codes(proj))

    def test_case_no_mismatch_is_red(self):
        """卡里的案号与官方元数据对不上 ⇒ 红（连账一起改也拦得住）。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            card = os.path.join(proj, "runs", RUN_NAME,
                                "JURITEXT000007471838.fr-case.card.txt")
            _write(card, _read(card).replace("CASE_NO: 01-16.595",
                                             "CASE_NO: 98-10.525"))
            repin_card(proj, "JURITEXT000007471838")
            codes = self._codes(proj)
            self.assertIn("FR_CASE_NO_MISMATCH", codes)
            self.assertNotIn("FR_CASE_CARD_SHA256_MISMATCH", codes)

    def test_case_no_dot_form_is_accepted(self):
        """`01-16595`（官方去点写法）与 `01-16.595` 等价 ⇒ 不报红。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            card = os.path.join(proj, "runs", RUN_NAME,
                                "JURITEXT000007471838.fr-case.card.txt")
            _write(card, _read(card).replace("CASE_NO: 01-16.595",
                                             "CASE_NO: 01-16595"))
            repin_card(proj, "JURITEXT000007471838")
            self.assertNotIn("FR_CASE_NO_MISMATCH", self._codes(proj))

    def test_date_mismatch_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            card = os.path.join(proj, "runs", RUN_NAME,
                                "JURITEXT000007471838.fr-case.card.txt")
            _write(card, _read(card).replace("JUDGE_DATE: 2004-09-29",
                                             "JUDGE_DATE: 2019-01-31"))
            repin_card(proj, "JURITEXT000007471838")
            codes = self._codes(proj)
            self.assertIn("FR_CASE_DATE_MISMATCH", codes)
            self.assertNotIn("FR_CASE_CARD_SHA256_MISMATCH", codes)

    def test_card_text_diverged_is_red(self):
        """卡内嵌的官方正文与 official/*.txt 不一致 ⇒ 红。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, ["JURITEXT000007471838"])
            card = os.path.join(proj, "runs", RUN_NAME,
                                "JURITEXT000007471838.fr-case.card.txt")
            _write(card, _read(card).replace("3 500 euros", "9 999 euros"))
            repin_card(proj, "JURITEXT000007471838")
            codes = self._codes(proj)
            self.assertIn("FR_CASE_CARD_TEXT_DIVERGED", codes)
            self.assertNotIn("FR_CASE_CARD_SHA256_MISMATCH", codes)

    def test_french_gate_skips_fr_case_cards(self):
        """法国判例卡不能让法国法条闸误判红（跨域隔离）。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp)
            fr_corpus = os.path.join(proj, "runs", "run-test-fr")
            os.makedirs(fr_corpus, exist_ok=True)
            with open(os.path.join(fr_corpus, "index.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"provisions": {}}, fh)
            findings, _corpus = verify_fr(proj, fr_corpus, "2026-11-16")
            self.assertEqual([f.code for f in findings], [],
                             f"法国法条闸不应因判例卡报错：{[f.code for f in findings]}")


class TestFrenchNormalization(unittest.TestCase):
    """法式归一单测（数字/日期/案号）。"""

    def test_thousands_separator_is_dot(self):
        self.assertEqual(norm_fr_number("300.000"), "300000")
        self.assertEqual(norm_fr_number("450.000"), "450000")
        self.assertEqual(norm_fr_number("1.234.567"), "1234567")

    def test_thousands_separator_is_space(self):
        self.assertEqual(norm_fr_number("3 500"), "3500")
        self.assertEqual(norm_fr_number("1 234 567"), "1234567")

    def test_nbsp_variants(self):
        self.assertEqual(norm_fr_number("1 234,56"), "1234.56")
        self.assertEqual(norm_fr_number("1 234,56"), "1234.56")
        self.assertEqual(norm_fr_number("3 500"), "3500")

    def test_comma_is_decimal_point(self):
        self.assertEqual(norm_fr_number("1 234,56"), "1234.56")
        self.assertEqual(norm_fr_number("1234,56"), "1234.56")
        self.assertEqual(norm_fr_number("1.234,56"), "1234.56")

    def test_plain_integer(self):
        self.assertEqual(norm_fr_number("42"), "42")
        self.assertEqual(norm_fr_number(" 42 "), "42")
        self.assertEqual(norm_fr_number(""), "")

    def test_case_number_dot_form(self):
        self.assertEqual(norm_case_no("01-16.595"), "01-16595")
        self.assertEqual(norm_case_no("01-16595"), "01-16595")
        self.assertEqual(norm_case_no("89-15.059"), "89-15059")

    def test_french_month_dates_both_ways(self):
        self.assertEqual(fr_date_to_iso("29 septembre 2004"), "2004-09-29")
        self.assertEqual(fr_date_to_iso("30 Juillet 1900"), "1900-07-30")
        self.assertEqual(fr_date_to_iso("15 Décembre 2006"), "2006-12-15")
        self.assertEqual(fr_date_to_iso("9 octobre 1990"), "1990-10-09")
        self.assertEqual(fr_date_to_iso("2004-09-29"), "2004-09-29")
        self.assertEqual(fr_date_to_iso("1 février 2020"), "2020-02-01")
        self.assertEqual(fr_date_to_iso("pas une date"), "")

    def test_plain_text_is_deterministic(self):
        with open(os.path.join(CORPUS_DIR, RUN_NAME, "official",
                               "JURITEXT000007471838.xml"), "rb") as fh:
            xml = fh.read()
        self.assertEqual(to_plain(xml), to_plain(xml))
        meta = parse_meta(xml)
        self.assertEqual(meta["id"], "JURITEXT000007471838")
        self.assertEqual(meta["date_dec"], "2004-09-29")
        self.assertEqual(meta["numeros_affaires"], ["01-16595"])


class FakeHttp:
    """零网络的假 HTTP：目录索引 + Range 前缀（206）。"""

    def __init__(self, index_html, prefix_bytes, honour_range=True):
        self.index_html = index_html
        self.prefix_bytes = prefix_bytes
        self.honour_range = honour_range
        self.calls = []

    def request(self, url, method="GET", headers=None, data=None, timeout=90,
                jar=None):
        self.calls.append((method, url, dict(headers or {})))
        if url.rstrip("/").endswith("INCA"):
            body = self.index_html.encode("utf-8")
            return {"status": 200, "headers": {}, "body": body, "final_url": url}
        rng = (headers or {}).get("Range", "")
        if not self.honour_range or not rng:
            body = self.prefix_bytes        # 服务器忽略了 Range ⇒ 200 全量
            return {"status": 200, "headers": {}, "body": body, "final_url": url}
        m = re.match(r"bytes=0-(\d+)", rng)
        end = int(m.group(1)) if m else len(self.prefix_bytes) - 1
        body = self.prefix_bytes[:end + 1]
        return {"status": 206, "headers": {"Content-Range": "bytes 0-%d/%d"
                                           % (end, len(self.prefix_bytes))},
                "body": body, "final_url": url}


def _fake_tar_gz():
    """本地造一个假 tar.gz：装两件真判决 XML ＋ 一个非 XML 文件 ＋ 尾部填充。

    尾部填充让「只拿到前缀」也能把前两件判决完整解出来（真实档案同理：
    前缀里的判决 XML 是完整的，截断发生在后面）。
    """
    buf = io.BytesIO()
    index = _index()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for cid in ["JURITEXT000006953017", "JURITEXT000007471838"]:
            meta = index["cases"][cid]
            with open(os.path.join(CORPUS_DIR, RUN_NAME, meta["xml_file"]),
                      "rb") as fh:
                data = fh.read()
            info = tarfile.TarInfo("inca/global/civile/JURI/TEXT/%s.xml" % cid)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        note = b"not a decision\n"
        info = tarfile.TarInfo("inca/global/README.txt")
        info.size = len(note)
        tar.addfile(info, io.BytesIO(note))
        # 尾部填充用**不可压缩**的伪随机字节（否则 gzip 一压就没了，
        # 前缀根本切不到填充区）
        pad = random.Random(42).randbytes(200000)
        info = tarfile.TarInfo("inca/global/padding.bin")
        info.size = len(pad)
        tar.addfile(info, io.BytesIO(pad))
    return buf.getvalue()


class TestFetchLayerOffline(unittest.TestCase):
    """抓取层：本地假 tar 前缀 ⇒ 解包/抽取/索引生成（零网络）。"""

    INDEX_HTML = ('<html><body><a href="?C=N;O=D">x</a>'
                  '<a href="Freemium_inca_global_20261108-140000.tar.gz">z</a>'
                  '</body></html>')

    def test_prefix_extraction_and_index(self):
        tar_bytes = _fake_tar_gz()
        prefix = tar_bytes[:int(len(tar_bytes) * 0.8)]   # 假装只拿到前缀
        http = FakeHttp(self.INDEX_HTML, prefix)
        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = os.path.join(tmp, "corpus")
            state = fetch_corpus.State(os.path.join(corpus_root,
                                                    fetch_corpus.STATE_REL))
            rc = fetch_corpus.fetch_fr_case(http, corpus_root, state, 4,
                                            "sample", "2026-11-16", False)
            self.assertEqual(rc, 0)
            run_dir = os.path.join(corpus_root, "fr-case", "run-20261116-inca")
            with open(os.path.join(run_dir, "index.json"), encoding="utf-8") as fh:
                index = json.load(fh)
            self.assertEqual(index["source_archive_url"],
                             "https://echanges.dila.gouv.fr/OPENDATA/INCA/"
                             "Freemium_inca_global_20261108-140000.tar.gz")
            self.assertEqual(index["archive_path"],
                             "Freemium_inca_global_20261108-140000.tar.gz")
            self.assertIn("licence", index)
            self.assertTrue(index["cases"], "索引里应有判决")
            self.assertIn("JURITEXT000006953017", index["cases"])
            self.assertIn("JURITEXT000007471838", index["cases"])
            for cid, meta in index["cases"].items():
                xml = os.path.join(run_dir, meta["xml_file"])
                txt = os.path.join(run_dir, meta["txt_file"])
                card = os.path.join(run_dir, meta["card_file"])
                self.assertTrue(os.path.exists(xml))
                self.assertTrue(os.path.exists(txt))
                self.assertTrue(os.path.exists(card))
                self.assertEqual(sha_file(xml), meta["xml_sha256"])
                self.assertEqual(sha_file(txt), meta["txt_sha256"])
                card_text = _read(card)
                self.assertIn("OFFICIAL_XML_SHA256: %s" % meta["xml_sha256"],
                              card_text)
                self.assertIn("OFFICIAL_TXT_SHA256: %s" % meta["txt_sha256"],
                              card_text)
            self.assertTrue(os.path.exists(os.path.join(corpus_root, "fr-case",
                                                        "ATTRIBUTION.txt")))
            # 抓取状态也记上了（增量续抓）
            self.assertTrue(state.fetched("fr-case",
                                          "JURITEXT000007471838"))

    def test_range_ignored_fails_closed(self):
        """服务器忽略 Range（200 全量）⇒ 必须报错拒绝下载全量档案。"""
        tar_bytes = _fake_tar_gz()
        http = FakeHttp(self.INDEX_HTML, tar_bytes, honour_range=False)
        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = os.path.join(tmp, "corpus")
            state = fetch_corpus.State(os.path.join(corpus_root,
                                                    fetch_corpus.STATE_REL))
            with self.assertRaises(fetch_corpus.FetchError) as ctx:
                fetch_corpus.fetch_fr_case(http, corpus_root, state, 4,
                                           "sample", "2026-11-16", False)
            self.assertIn("Range", str(ctx.exception))

    def test_bulk_needs_explicit_yes(self):
        """bulk 模式必须显式 --yes（非交互终端直接拒）。"""
        http = FakeHttp(self.INDEX_HTML, _fake_tar_gz())
        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = os.path.join(tmp, "corpus")
            state = fetch_corpus.State(os.path.join(corpus_root,
                                                    fetch_corpus.STATE_REL))
            rc = fetch_corpus.fetch_fr_case(http, corpus_root, state, 4,
                                            "bulk", "2026-11-16", False)
            self.assertEqual(rc, 2)

    def test_prefix_stream_reads_real_archive_layout(self):
        """档案内路径照抄（用于署名里的「档案 URL＋档案内路径」）。"""
        found = fetch_corpus._fr_case_stream_xmls
        self.assertTrue(callable(found))
        with tempfile.TemporaryDirectory() as tmp:
            tar_path = os.path.join(tmp, "prefix.tar.gz")
            with open(tar_path, "wb") as fh:
                fh.write(_fake_tar_gz())
            got = fetch_corpus._fr_case_stream_xmls(tar_path, want=2)
            self.assertEqual(len(got), 2)
            for member, data in got:
                self.assertTrue(member.endswith(".xml"))
                self.assertIn(b"TEXTE_JURI_JUDI", data[:4096])


if __name__ == "__main__":
    unittest.main()
