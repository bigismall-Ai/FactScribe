#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""西班牙语料的**三个效力标志**：采集侧抽得出来，判定侧读得到。

BOE 官方整件（`official/act.xml` 的 `<metadatos>`）里确实有三个**管效力**
的标志：

  * `estatus_derogacion` ＝ 是否**已废止**（S ＝ 是）；
  * `estatus_anulacion` ＝ 是否**已撤销**（S ＝ 是）；
  * `vigencia_agotada` ＝ **效力是否已耗尽**（已被后续规范取代；S ＝ 是）。

⚠️ `estado_consolidacion` **不是**效力标志（实读三个 run 全是
`Finalizado`，而这三个法今天全部现行有效）——本件顺带钉住「不许拿它
判效力」。

四块：
  1. **采集侧**（`tools/fetch_corpus.py` 的 `_es_meta`）：三个标志抽得
     出来、缺了不炸（空串照填）、可选的两个日期带了就抽；
  2. **真件核对**：三份已采集的官方整件里，新抽的字段与**原文逐字一致**
     （三个都是 `N`）——用独立的 XML 解析（ElementTree）复核，不拿自己的
     正则当证据；
  3. **索引落盘**：采集侧把三个标志写进 run 的 `index.json`（桩 HTTP，
     **零网络**、不碰 BOE）；
  4. **统一契约的西班牙 status**（`adapters/es_provision.py`）：真的读到
     这三个标志（**不是恒 `unknown`**）——官方整件在时以官方件为准；官方
     整件不在时读采集侧写进 `index.json` 的同名字段，出处写进
     `status_source`。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from factscribe_legal.adapters import es_provision  # noqa: E402

import fetch_corpus  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.abspath(os.path.join(HERE, "..", "corpus"))
ES_ROOT = os.path.join(CORPUS, "es")

# 三个管效力的标志（顺序固定，逐条断言用）
EFFECT_FLAGS = ("estatus_derogacion", "estatus_anulacion", "vigencia_agotada")

# 可选字段：官方件不一定带（带了就抽走）
OPTIONAL_DATES = ("fecha_derogacion", "fecha_anulacion")

RUN_LEY39 = "run-20261116-es-ley39-2015-procedimiento-administrativo"
REF_DATE = "2026-11-16"


def _es_runs():
    """仓内三个西班牙 run（目录名）。"""
    return sorted(d for d in os.listdir(ES_ROOT)
                  if os.path.isdir(os.path.join(ES_ROOT, d)))


def _official_xml(run):
    return os.path.join(ES_ROOT, run, "official", "act.xml")


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _xml_tags(path):
    """独立解析官方整件 → {标签: 文本}（只取 <metadatos> 里的直接子标签）。

    用 ElementTree 而不是采集器的正则：复核不能拿自己的解析当证据。
    """
    root = ET.parse(path).getroot()
    meta = None
    for el in root.iter():
        if str(el.tag).split("}")[-1] == "metadatos":
            meta = el
            break
    out = {}
    if meta is None:
        return out
    for child in list(meta):
        tag = str(child.tag).split("}")[-1]
        out[tag] = (child.text or "").strip()
    return out


class _StubHttp:
    """零网络的 HTTP 桩：把仓内官方整件的字节原样喂回去。"""

    def __init__(self, raw):
        self.raw = raw
        self.calls = []

    def request(self, url, method="GET", headers=None, data=None,
                timeout=90, jar=None):
        self.calls.append(url)
        return {"status": 200, "headers": {}, "body": self.raw}


class TestEsMetaExtraction(unittest.TestCase):
    """采集侧：`_es_meta` 抽三个效力标志（＋可选两个日期）。"""

    XML = """<?xml version="1.0" encoding="utf-8"?>
<response><data><metadatos>
  <identificador>BOE-A-2015-10565</identificador>
  <fecha_vigencia>20161002</fecha_vigencia>
  <estatus_derogacion>N</estatus_derogacion>
  <estatus_anulacion>N</estatus_anulacion>
  <vigencia_agotada>N</vigencia_agotada>
  <estado_consolidacion codigo="3">Finalizado</estado_consolidacion>
</metadatos></data></response>"""

    def test_three_flags_are_extracted(self):
        meta = fetch_corpus._es_meta(self.XML.encode("utf-8"))
        for tag in EFFECT_FLAGS:
            self.assertEqual(meta.get(tag), "N", "%s 没抽出来" % tag)

    def test_missing_flags_are_empty_string_not_crash(self):
        """官方件没带这三个标志 ⇒ 空串照填（不炸、不猜）。"""
        xml = ("<response><data><metadatos><identificador>X</identificador>"
               "</metadatos></data></response>")
        meta = fetch_corpus._es_meta(xml.encode("utf-8"))
        for tag in EFFECT_FLAGS + OPTIONAL_DATES:
            self.assertEqual(meta.get(tag), "", "%s 不该凭空有值" % tag)

    def test_optional_dates_extracted_when_present(self):
        xml = ("<response><data><metadatos>"
               "<estatus_derogacion>S</estatus_derogacion>"
               "<fecha_derogacion>20240101</fecha_derogacion>"
               "<fecha_anulacion>20240202</fecha_anulacion>"
               "</metadatos></data></response>")
        meta = fetch_corpus._es_meta(xml.encode("utf-8"))
        self.assertEqual(meta.get("estatus_derogacion"), "S")
        self.assertEqual(meta.get("fecha_derogacion"), "20240101")
        self.assertEqual(meta.get("fecha_anulacion"), "20240202")

    def test_estado_consolidacion_is_not_an_effect_flag(self):
        """结构性保证：`estado_consolidacion` 不在三个效力标志里。"""
        self.assertNotIn("estado_consolidacion", EFFECT_FLAGS)
        self.assertNotIn("estado_consolidacion",
                         es_provision.BOE_META_TAGS)


class TestRealOfficialFiles(unittest.TestCase):
    """三份已采集的官方整件：新抽字段与原文逐字一致。"""

    def test_flags_match_source_text(self):
        runs = _es_runs()
        self.assertEqual(len(runs), 3, "预期三个西班牙 run，实得 %s" % runs)
        for run in runs:
            meta = fetch_corpus._es_meta(_read_bytes(_official_xml(run)))
            source = _xml_tags(_official_xml(run))
            for tag in EFFECT_FLAGS:
                self.assertEqual(meta.get(tag), source.get(tag, ""),
                                 "%s 的 %s 与官方原文不一致" % (run, tag))
                self.assertIn(tag, source, "官方整件里没有 %s" % tag)

    def test_all_real_flags_are_n(self):
        """三个 run 官方原文都是 N（三个法今天全部现行有效）。"""
        for run in _es_runs():
            meta = fetch_corpus._es_meta(_read_bytes(_official_xml(run)))
            for tag in EFFECT_FLAGS:
                self.assertEqual(meta.get(tag), "N",
                                 "%s 的 %s 不是 N" % (run, tag))

    def test_optional_dates_absent_in_real_files(self):
        """现行件官方原文不带废止日／撤销日 ⇒ 抽出来是空串（不是编造）。"""
        for run in _es_runs():
            meta = fetch_corpus._es_meta(_read_bytes(_official_xml(run)))
            for tag in OPTIONAL_DATES:
                self.assertEqual(meta.get(tag), "",
                                 "%s 的 %s 不该有值" % (run, tag))


class TestIndexCarriesFlags(unittest.TestCase):
    """采集侧把三个标志写进 run 的 `index.json`（桩 HTTP，零网络）。"""

    def test_fetch_es_writes_flags_into_index(self):
        raw = _read_bytes(_official_xml(RUN_LEY39))
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        corpus_root = os.path.join(tmp, "corpus")
        state = fetch_corpus.State(
            os.path.join(corpus_root, fetch_corpus.STATE_REL))
        stub = _StubHttp(raw)
        backup = fetch_corpus.ES_SAMPLE_ACTS
        fetch_corpus.ES_SAMPLE_ACTS = [("BOE-A-2015-10565",
                                        "ley39-2015-procedimiento-administrativo")]
        try:
            rc = fetch_corpus.fetch_es(stub, corpus_root, state, 2, "sample",
                                       REF_DATE, True)
        finally:
            fetch_corpus.ES_SAMPLE_ACTS = backup
        self.assertEqual(rc, 0)
        self.assertEqual(len(stub.calls), 1, "样单只应发 1 次请求")
        idx_path = os.path.join(corpus_root, "es",
                                "run-20261116-es-%s" % "ley39-2015-procedimiento-administrativo",
                                "index.json")
        with open(idx_path, encoding="utf-8") as fh:
            index = json.load(fh)
        for tag in EFFECT_FLAGS:
            self.assertEqual(index.get(tag), "N",
                             "索引里没有 %s（或值不对）" % tag)
        for tag in OPTIONAL_DATES:
            self.assertIn(tag, index, "索引里缺 %s 这个键" % tag)


class TestContractStatusReadsFlags(unittest.TestCase):
    """统一契约的西班牙 status：真的读到三个标志（不是恒 unknown）。"""

    def _card(self, tmp, with_official=False, flags=None):
        """造一个最小西班牙 run（卡 + 可选官方整件），返回 (卡路径, 索引)。"""
        run_dir = os.path.join(tmp, "run-es-test")
        os.makedirs(run_dir, exist_ok=True)
        card_path = os.path.join(run_dir, "a1.es.card.txt")
        with open(card_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "# 西班牙法条证据卡（测试夹具）",
                "ACT_ID: BOE-A-2015-10565",
                "BLOCK_ID: a1",
                "ARTICLE_NUM: 1",
                "VERSION_DATE: %s" % REF_DATE,
                "FETCH_DATE: %s" % REF_DATE,
                "REFERENCE_DATE: %s" % REF_DATE,
                "SOURCE_FILE: official/act.xml",
                "",
            ]))
        if with_official:
            os.makedirs(os.path.join(run_dir, "official"), exist_ok=True)
            parts = ["<response><data><metadatos>",
                     "<fecha_vigencia>20161002</fecha_vigencia>"]
            for tag in EFFECT_FLAGS:
                parts.append("<%s>%s</%s>" % (tag, flags.get(tag, "N"), tag))
            parts.append("</metadatos></data></response>")
            with open(os.path.join(run_dir, "official", "act.xml"), "w",
                      encoding="utf-8") as fh:
                fh.write("\n".join(parts))
        index = {"act_id": "BOE-A-2015-10565",
                 "fecha_vigencia": "20161002",
                 "fetch_reference_date": REF_DATE}
        index.update(flags or {})
        return card_path, index

    def test_real_runs_are_in_force_not_unknown(self):
        """三个真 run：status 判得出来（in_force），不是恒 unknown。"""
        for run in _es_runs():
            card = os.path.join(ES_ROOT, run, "a1.es.card.txt")
            if not os.path.exists(card):
                continue
            out = es_provision.adapt(card)
            self.assertEqual(out["status"], "in_force",
                             "%s 判成了 %s" % (run, out["status"]))
            self.assertNotEqual(out["status"], "unknown")
            self.assertTrue(out["status_source"].startswith("es:"))

    def test_index_carried_flags_decide_status(self):
        """官方整件不在本地 ⇒ 读采集侧写进索引的三个标志 ⇒ in_force。"""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        card, index = self._card(tmp, flags={"estatus_derogacion": "N",
                                             "estatus_anulacion": "N",
                                             "vigencia_agotada": "N"})
        out = es_provision.adapt(card, index=index)
        self.assertEqual(out["status"], "in_force")
        self.assertEqual(out["status_source"], "es:index_flags@%s" % REF_DATE)

    def test_index_carried_flag_s_is_repealed(self):
        """索引里任一标志为 S ⇒ repealed（出处写进 status_source）。"""
        for tag in EFFECT_FLAGS:
            tmp = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, tmp, True)
            card, index = self._card(tmp, flags={tag: "S"})
            out = es_provision.adapt(card, index=index)
            self.assertEqual(out["status"], "repealed",
                             "%s=S 没判成 repealed" % tag)
            self.assertIn("index_%s" % tag, out["status_source"])

    def test_official_file_wins_over_index(self):
        """官方整件与索引都有 ⇒ 以官方件为准（官方字节是权威）。"""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        card, index = self._card(tmp, with_official=True,
                                 flags={"estatus_derogacion": "N",
                                        "estatus_anulacion": "N",
                                        "vigencia_agotada": "N"})
        index["estatus_derogacion"] = "S"      # 索引里说是废止
        out = es_provision.adapt(card, index=index)
        self.assertEqual(out["status"], "in_force",
                         "官方件说 N 时不该被索引里的 S 盖掉")
        self.assertTrue(out["status_source"].startswith("es:fecha_vigencia"))

    def test_nothing_available_is_unknown(self):
        """官方整件与索引都没有标志 ⇒ 判不出 ⇒ unknown（不猜）。"""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        card, index = self._card(tmp)
        out = es_provision.adapt(card, index=index)
        self.assertEqual(out["status"], "unknown")


class TestBackfilledIndexes(unittest.TestCase):
    """存量三份 index.json（离线补齐后）：标志在、且与官方原文一致。

    补齐是**离线**做的（用仓内已有的 `official/act.xml` 重算，没打官方接口），
    所以这里能断言：索引里的三个标志 ＝ 官方原文的值，且索引仍然指着**没被动过**
    的官方整件。
    """

    def test_index_carries_the_three_flags(self):
        for run in _es_runs():
            with open(os.path.join(ES_ROOT, run, "index.json"),
                      encoding="utf-8") as fh:
                index = json.load(fh)
            source = _xml_tags(_official_xml(run))
            for tag in EFFECT_FLAGS:
                self.assertIn(tag, index, "%s 的索引里没有 %s" % (run, tag))
                self.assertEqual(index.get(tag), source.get(tag, ""),
                                 "%s 的 %s 与官方原文不一致" % (run, tag))

    def test_index_still_points_at_untouched_official_file(self):
        """补齐只加键：官方整件的哈希声明仍与盘上原文一致。"""
        for run in _es_runs():
            with open(os.path.join(ES_ROOT, run, "index.json"),
                      encoding="utf-8") as fh:
                index = json.load(fh)
            self.assertEqual(index.get("source_sha256"),
                             hashlib.sha256(_read_bytes(_official_xml(run))).hexdigest(),
                             "%s 的官方整件哈希声明对不上" % run)

    def test_manifest_entries_match_disk(self):
        """清单（manifest.json）对得上：三条 ES 索引条目 ＝ 盘上实际字节。"""
        manifest_path = os.path.join(CORPUS, "manifest.json")
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        entries = {f["path"]: f for f in manifest.get("files") or []}
        for run in _es_runs():
            rel = os.path.join("es", run, "index.json")
            self.assertIn(rel, entries, "清单里没有 %s" % rel)
            raw = _read_bytes(os.path.join(ES_ROOT, run, "index.json"))
            self.assertEqual(entries[rel]["bytes"], len(raw))
            self.assertEqual(entries[rel]["sha256"],
                             hashlib.sha256(raw).hexdigest())


class TestSpainStatusTriState(unittest.TestCase):
    """已定口径的回归锁（三条）：

    1. status 三态闭集固定 `in_force` / `repealed` / `unknown`，
       **不写** `not_in_force`；
    2. `unknown` **不等于在效**——判不出「官方是否仍提供现行合并文本」时
       落 `unknown`，不许拿 `fecha_vigencia` 顶成 `in_force`；
    3. 官方件优先（**逐字段**），采集侧索引兜底路径与之一致；
       `status_source` 取值按既有口径（`<域>:<判据>`，兜底路径另标出处）。
    """

    TRI_STATE = ("in_force", "repealed", "unknown")
    BASE_SOURCES = {"es:boe_consolidated", "es:fecha_vigencia",
                    "es:index_flags", "es:boe+index_flags"}
    FLAG_SOURCES = {"es:%s_%s=S" % (carrier, tag)
                    for carrier in ("boe", "index") for tag in EFFECT_FLAGS}
    REF_SUFFIXABLE = ("es:fecha_vigencia", "es:index_flags",
                      "es:boe+index_flags")

    def _card(self, tmp, official_flags=None, index_flags=None,
              fecha="20161002"):
        """最小西班牙 run：卡 ＋ 可选官方整件（只写给定的标志）＋ 索引。"""
        run_dir = os.path.join(tmp, "run-es-test")
        os.makedirs(os.path.join(run_dir, "official"), exist_ok=True)
        card_path = os.path.join(run_dir, "a1.es.card.txt")
        with open(card_path, "w", encoding="utf-8") as fh:
            fh.write(chr(10).join([
                "ACT_ID: BOE-A-2015-10565",
                "BLOCK_ID: a1",
                "FETCH_DATE: %s" % REF_DATE,
                "REFERENCE_DATE: %s" % REF_DATE,
                "SOURCE_FILE: official/act.xml",
                "",
            ]))
        if official_flags is not None:
            parts = ["<data><metadatos>"]
            if fecha:
                parts.append("<fecha_vigencia>%s</fecha_vigencia>" % fecha)
            for tag, value in official_flags.items():
                parts.append("<%s>%s</%s>" % (tag, value, tag))
            parts.append("</metadatos></data>")
            with open(os.path.join(run_dir, "official", "act.xml"), "w",
                      encoding="utf-8") as fh:
                fh.write(chr(10).join(parts))
        index = {"act_id": "BOE-A-2015-10565",
                 "fetch_reference_date": REF_DATE}
        if fecha:
            index["fecha_vigencia"] = fecha
        index.update(index_flags or {})
        return card_path, index

    def _adapt(self, **kwargs):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        card, index = self._card(tmp, **kwargs)
        return es_provision.adapt(card, index=index)

    def test_status_is_always_in_tri_state(self):
        """任何场景都只能落三态（没有 not_in_force）。"""
        cases = [
            dict(official_flags={t: "N" for t in EFFECT_FLAGS}),
            dict(official_flags={"estatus_derogacion": "S"}),
            dict(index_flags={t: "N" for t in EFFECT_FLAGS}),
            dict(index_flags={"vigencia_agotada": "S"}),
            dict(),
            dict(official_flags={"estatus_derogacion": "N"}),
            dict(fecha="20300101",
                 official_flags={t: "N" for t in EFFECT_FLAGS}),
        ]
        for case in cases:
            out = self._adapt(**case)
            self.assertIn(out["status"], self.TRI_STATE,
                          "status 跑出了三态闭集：%s" % out["status"])
            self.assertNotEqual(out["status"], "not_in_force")

    def test_partial_flags_is_unknown_not_in_force(self):
        """三个标志没齐 ⇒ 判不出 ⇒ unknown（**不是** in_force）。"""
        out = self._adapt(official_flags={"estatus_derogacion": "N"})
        self.assertEqual(out["status"], "unknown")
        self.assertNotEqual(out["status"], "in_force")

    def test_known_flag_s_wins_even_if_set_is_partial(self):
        """已知有一个标志是 S ⇒ repealed（这是证据，不是"没发现问题"）。"""
        out = self._adapt(official_flags={"vigencia_agotada": "S"})
        self.assertEqual(out["status"], "repealed")
        self.assertIn("boe_vigencia_agotada", out["status_source"])

    def test_official_value_wins_field_by_field(self):
        """官方件给的值一律用它：官方 N 压过索引 S。"""
        out = self._adapt(official_flags={t: "N" for t in EFFECT_FLAGS},
                          index_flags={"estatus_derogacion": "S"})
        self.assertEqual(out["status"], "in_force")
        out = self._adapt(official_flags={"estatus_derogacion": "S"},
                          index_flags={t: "N" for t in EFFECT_FLAGS})
        self.assertEqual(out["status"], "repealed")

    def test_index_fills_fields_official_did_not_give(self):
        """官方件只给一部分 ⇒ 缺的字段由索引补（兜底），出处两边都标。"""
        out = self._adapt(official_flags={"estatus_derogacion": "N"},
                          index_flags={t: "N" for t in EFFECT_FLAGS})
        self.assertEqual(out["status"], "in_force")
        self.assertTrue(out["status_source"].startswith("es:boe+index_flags"),
                        out["status_source"])

    def test_status_source_is_in_closed_set(self):
        """status_source 取值按既有口径（不在闭集里就是跑偏了）。"""
        cases = [
            dict(official_flags={t: "N" for t in EFFECT_FLAGS}),
            dict(official_flags={"estatus_derogacion": "S"}),
            dict(index_flags={t: "N" for t in EFFECT_FLAGS}),
            dict(index_flags={"estatus_anulacion": "S"}),
            dict(),
            dict(official_flags={"estatus_derogacion": "N"},
                 index_flags={t: "N" for t in EFFECT_FLAGS}),
            dict(fecha="20300101",
                 official_flags={t: "N" for t in EFFECT_FLAGS}),
        ]
        allowed = self.BASE_SOURCES | self.FLAG_SOURCES
        for case in cases:
            src = self._adapt(**case)["status_source"]
            hit = src in allowed or any(
                src.startswith(s + "@") for s in self.REF_SUFFIXABLE)
            self.assertTrue(hit, "status_source 跑出了闭集：%s" % src)


if __name__ == "__main__":
    unittest.main()
