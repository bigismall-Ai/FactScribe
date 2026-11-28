#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一契约**公共层 adapter** 的自测：标准库 unittest，网络零依赖。

四块：
  1. **每个 adapter 一条真卡**：给它仓内真实证据卡，断言输出的
     `kind` / `jurisdiction` / `local_id` 逐字正确（六种形状 ＋ 集体协议）。
  2. **第 3 步的时点字段**：`status` 三态、`asof`、`status_source`、
     `effective_from` / `effective_to` / `decided_on`，逐形状逐边界值断言
     （中国 sxx 四值、西班牙不采 `estado_consolidacion`、法国生效区间三分支、
     意大利取件口径、判例不产 status、CCNL 到期日）。
  3. **统一读路径**：有公共层视图时走视图，没有时现场从旧卡推导；
     视图缺字段时从旧卡补齐（视图是缓存，不是唯一真相）。
  4. **fail-closed**：取不到必填字段就报错，不给空值混进统一层。
  5. **第 4 步的卡级五元组后三位**（`span` / `face` / `how`）：每个形状
     一例「取到」、一例「取不到落『—』」；并断言口径与收据五元组**同一个**
     （同一套 `receipts.span_in_text`）。

python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from factscribe_legal import adapters  # noqa: E402
from factscribe_legal.adapters import (card_receipts,  # noqa: E402
                                       cn_provision, es_provision, fr_case,
                                       fr_provision, it_agreement, it_case,
                                       it_provision, status)
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

CN_CARD = "中华人民共和国劳动合同法_2c909f.cn.card.txt"

# 契约三态 ＋ 「这条线不产 status」的缺省（草案 §2.2）
STATUS_VALUES = ("in_force", "repealed", "unknown", MISSING)


def _card(*parts):
    return os.path.join(CORPUS, *parts)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class TestFrenchProvisionAdapter(unittest.TestCase):
    """法国法条：NUM → local_id，直映原样。"""

    def test_card(self):
        out = fr_provision.adapt(_card("fr", "D641-10-1.card.txt"))
        self.assertEqual(out["kind"], "provision")
        self.assertEqual(out["jurisdiction"], "fr")
        self.assertEqual(out["local_id"], "D641-10-1")

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
        out = cn_provision.adapt(_card("cn", "cards", CN_CARD))
        self.assertEqual(out["kind"], "provision")
        self.assertEqual(out["jurisdiction"], "cn")
        self.assertEqual(out["local_id"], "2c909fdd678bf17901678bf74d7106b3")

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
        self.assertEqual(out["kind"], "provision")
        self.assertEqual(out["jurisdiction"], "es")
        self.assertEqual(out["local_id"], "BOE-A-2015-10565/a1")

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
        self.assertEqual(out["kind"], "provision")
        self.assertEqual(out["jurisdiction"], "it")
        self.assertEqual(out["local_id"],
                         "urn:nir:stato:legge:1990-08-07;241/art_1")


class TestItalianCaseAdapter(unittest.TestCase):
    """意大利判例：ECLI → local_id；kind=case。"""

    def test_card(self):
        out = it_case.adapt(_card("it-case", ITCASE_RUN,
                                  "ECLI-IT-COST-1956-1.itcase.card.txt"))
        self.assertEqual(out["kind"], "case")
        self.assertEqual(out["jurisdiction"], "it")
        self.assertEqual(out["local_id"], "ECLI:IT:COST:1956:1")


class TestFrenchCaseAdapter(unittest.TestCase):
    """法国判例：CASE_ID → local_id；kind=case。"""

    def test_card(self):
        out = fr_case.adapt(_card("fr-case", FRCASE_RUN,
                                  "JURITEXT000006951547.fr-case.card.txt"))
        self.assertEqual(out["kind"], "case")
        self.assertEqual(out["jurisdiction"], "fr")
        self.assertEqual(out["local_id"], "JURITEXT000006951547")


class TestItalianAgreementAdapter(unittest.TestCase):
    """集体协议：CNEL 簇码 → local_id；kind=agreement（单独形状）。"""

    def test_inventory_row(self):
        rows = it_agreement.read_inventory(
            os.path.join(BULK_IT, "it-inventory-vigenti.tsv"))
        self.assertEqual(len(rows), 144, "CCNL 清单应 144 簇")
        row = next(r for r in rows if r["code"] == "A011")
        out = it_agreement.adapt(row)
        self.assertEqual(out["kind"], "agreement")
        self.assertEqual(out["jurisdiction"], "it")
        self.assertEqual(out["local_id"], "A011")

    def test_agreement_is_not_a_provision(self):
        """集体协议不塞进法条模板：kind 必须与法条不同。"""
        rows = it_agreement.read_inventory(
            os.path.join(BULK_IT, "it-inventory-vigenti.tsv"))
        out = it_agreement.adapt(rows[0])
        self.assertNotEqual(out["kind"], "provision")
        self.assertEqual(out["kind"], "agreement")


# ---------------------------------------------------------------------------
# 第 3 步：status 三态 ＋ asof ＋ 配套字段
# ---------------------------------------------------------------------------

class TestChineseSxxFourValues(unittest.TestCase):
    """中国 sxx 四种取值 ⇒ 三态（已拍板口径）。

    3（现行有效）⇒ in_force；1（已废止）⇒ repealed；
    4（尚未生效）⇒ unknown；2（已修改）⇒ unknown。
    """

    def _card_with_sxx(self, sxx):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "s.cn.card.txt")
        body = ["# 中国法规证据卡", "TITLE: 测试法规",
                "BBBS: 2c909fdd678bf17901678bf74d7106b3",
                "GBRQ: 2012-12-28", "SXRQ: 2013-07-01"]
        if sxx is not None:
            body.append("SXX: %s" % sxx)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(body) + "\n")
        return path

    def test_sxx_3_is_in_force(self):
        out = cn_provision.adapt(self._card_with_sxx(3))
        self.assertEqual(out["status"], "in_force")
        self.assertEqual(out["status_source"], "cn:sxx=3")

    def test_sxx_1_is_repealed(self):
        out = cn_provision.adapt(self._card_with_sxx(1))
        self.assertEqual(out["status"], "repealed")
        self.assertEqual(out["status_source"], "cn:sxx=1")

    def test_sxx_4_is_unknown_not_repealed(self):
        """尚未生效 ⇒ unknown（**不是** repealed，也**不是** in_force）。"""
        out = cn_provision.adapt(self._card_with_sxx(4))
        self.assertEqual(out["status"], "unknown")
        self.assertNotEqual(out["status"], "repealed")
        self.assertNotEqual(out["status"], "in_force")

    def test_sxx_2_is_unknown(self):
        """已修改不足以证明今天还在适用 ⇒ unknown。"""
        out = cn_provision.adapt(self._card_with_sxx(2))
        self.assertEqual(out["status"], "unknown")

    def test_missing_sxx_is_unknown(self):
        out = cn_provision.adapt(self._card_with_sxx(None))
        self.assertEqual(out["status"], "unknown")
        self.assertEqual(out["status_source"], "cn:sxx")

    def test_real_card_is_in_force(self):
        out = cn_provision.adapt(_card("cn", "cards", CN_CARD))
        self.assertEqual(out["status"], "in_force")
        self.assertEqual(out["status_source"], "cn:sxx=3")

    def test_effective_from_is_sxrq_not_gbrq(self):
        """生效日用 SXRQ（施行日），**不是** GBRQ（公布日）。"""
        out = cn_provision.adapt(self._card_with_sxx(3))
        self.assertEqual(out["effective_from"], "2013-07-01")
        self.assertNotEqual(out["effective_from"], "2012-12-28")

    def test_effective_to_is_missing(self):
        """官方详情不给失效日 ⇒ effective_to 填「—」（不许拿 status 反推）。"""
        out = cn_provision.adapt(self._card_with_sxx(1))
        self.assertEqual(out["effective_to"], MISSING)

    def test_asof_is_snapshot_date_when_catalog_present(self):
        """asof ＝ 官方全库快照日（全库目录记录的 fetched_at）。"""
        catalog = cn_provision.load_index(os.path.join(CORPUS, "cn",
                                                        "catalog.jsonl.gz"))
        out = cn_provision.adapt(_card("cn", "cards", CN_CARD), index=catalog)
        self.assertEqual(out["asof"], "2026-11-16")

    def test_asof_is_missing_without_catalog(self):
        out = cn_provision.adapt(_card("cn", "cards", CN_CARD))
        self.assertEqual(out["asof"], MISSING)


class TestSpanishDoesNotUseEstadoConsolidacion(unittest.TestCase):
    """西班牙：**不用** `estado_consolidacion` 判 status（已拍板口径）。

    实读三个 run 全是 `"Finalizado"` 而三法今天全部现行有效
    ⇒ 拿它判会把三个现行有效的法全判成已失效。
    """

    CARD = ("# 西班牙法条证据卡\n"
            "ACT_ID: BOE-A-2015-10565\n"
            "BLOCK_ID: a1\n"
            "VERSION_DATE: 2026-11-16\n"
            "FETCH_DATE: 2026-11-16\n"
            "REFERENCE_DATE: 2026-11-16\n"
            "SOURCE_FILE: official/act.xml\n")

    def _run(self, estado="Finalizado", derogacion="N", anulacion="N",
             agotada="N", fecha_vigencia="20161002", with_official=True):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        card = os.path.join(tmp, "a1.es.card.txt")
        with open(card, "w", encoding="utf-8") as fh:
            fh.write(self.CARD)
        if with_official:
            xml = ["<data><metadatos>",
                   "<fecha_disposicion>20151001</fecha_disposicion>",
                   "<fecha_publicacion>20151002</fecha_publicacion>"]
            if fecha_vigencia:
                xml.append("<fecha_vigencia>%s</fecha_vigencia>"
                           % fecha_vigencia)
            xml.append("<estatus_derogacion>%s</estatus_derogacion>"
                       % derogacion)
            xml.append("<estatus_anulacion>%s</estatus_anulacion>" % anulacion)
            xml.append("<vigencia_agotada>%s</vigencia_agotada>" % agotada)
            xml.append('<estado_consolidacion codigo="3">%s'
                       '</estado_consolidacion>' % estado)
            xml.append("</metadatos></data>")
            _write(os.path.join(tmp, "official", "act.xml"), "\n".join(xml))
        return card

    def test_estado_consolidacion_is_never_read(self):
        """结构性保证：白名单里**没有** estado_consolidacion（连读都不读）。"""
        self.assertNotIn("estado_consolidacion", es_provision.BOE_META_TAGS)

    def test_finalizado_with_live_flags_is_in_force(self):
        """官方仍提供现行合并文本（三个标志皆 N）⇒ in_force。"""
        out = es_provision.adapt(self._run(estado="Finalizado"))
        self.assertEqual(out["status"], "in_force")

    def test_derogado_estado_does_not_change_verdict(self):
        """estado_consolidacion 即使写成废止类值，判定也不变 ⇒ 证明没用它。"""
        live = es_provision.adapt(self._run(estado="Finalizado"))
        fake = es_provision.adapt(self._run(estado="Derogado"))
        self.assertEqual(live["status"], "in_force")
        self.assertEqual(fake["status"], "in_force")
        self.assertEqual(live["status"], fake["status"])

    def test_estatus_derogacion_s_is_repealed(self):
        out = es_provision.adapt(self._run(derogacion="S"))
        self.assertEqual(out["status"], "repealed")
        self.assertIn("estatus_derogacion", out["status_source"])

    def test_estatus_anulacion_s_is_repealed(self):
        out = es_provision.adapt(self._run(anulacion="S"))
        self.assertEqual(out["status"], "repealed")

    def test_vigencia_agotada_s_is_repealed(self):
        """效力已耗尽（已被后续规范取代）⇒ repealed。"""
        out = es_provision.adapt(self._run(agotada="S"))
        self.assertEqual(out["status"], "repealed")
        self.assertIn("vigencia_agotada", out["status_source"])

    def test_not_yet_effective_is_unknown(self):
        """fecha_vigencia 晚于参考日 ⇒ 尚未生效 ⇒ unknown（不是 repealed）。"""
        out = es_provision.adapt(self._run(fecha_vigencia="20300101"))
        self.assertEqual(out["status"], "unknown")
        self.assertNotEqual(out["status"], "repealed")

    def test_missing_official_file_is_unknown(self):
        """官方整件取不到 ⇒ 判不出「官方是否仍提供现行合并文本」⇒ unknown。"""
        out = es_provision.adapt(self._run(with_official=False))
        self.assertEqual(out["status"], "unknown")

    def test_real_card_is_in_force_with_fecha_vigencia(self):
        out = es_provision.adapt(_card("es", ES_RUN, "a1.es.card.txt"))
        self.assertEqual(out["status"], "in_force")
        self.assertEqual(out["effective_from"], "2016-10-02")
        self.assertEqual(out["asof"], "2026-11-16")
        self.assertEqual(out["effective_to"], MISSING)

    def test_all_three_real_runs_are_in_force(self):
        """三个 run（1978 宪法 / 39-2015 / 40-2015）今天全部现行有效。"""
        root = os.path.join(CORPUS, "es")
        for run in sorted(os.listdir(root)):
            card = os.path.join(root, run, "a1.es.card.txt")
            if not os.path.exists(card):
                continue
            out = es_provision.adapt(card)
            self.assertEqual(out["status"], "in_force",
                             "%s 不该判成非 in_force" % run)


class TestFrenchDateRange(unittest.TestCase):
    """法国：复用 provisions.py 的区间判定，三分支逐个断言。"""

    def _card(self, date_debut="2017-05-07", date_fin="2999-01-01",
              etat="VIGUEUR", pool_asof="2026-11-15"):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "x.card.txt")
        body = ["# 法国法条证据卡", "NUM: X-1", "CODE_ID: LEGI"]
        if etat is not None:
            body.append("ETAT: %s" % etat)
        if date_debut:
            body.append("DATE_DEBUT: %s" % date_debut)
        if date_fin:
            body.append("DATE_FIN: %s" % date_fin)
        if pool_asof:
            body.append("POOL_ASOF: %s" % pool_asof)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(body) + "\n")
        return path

    def test_in_force_inside_interval(self):
        out = fr_provision.adapt(self._card(), reference_date="2026-11-20")
        self.assertEqual(out["status"], "in_force")

    def test_repealed_when_date_fin_passed(self):
        out = fr_provision.adapt(self._card(date_fin="2020-01-01"),
                                reference_date="2026-11-20")
        self.assertEqual(out["status"], "repealed")

    def test_future_start_is_unknown(self):
        """date_debut > 参考日 ⇒ 未来才生效 ⇒ unknown（不是 repealed）。"""
        out = fr_provision.adapt(self._card(date_debut="2030-01-01"),
                                reference_date="2026-11-20")
        self.assertEqual(out["status"], "unknown")
        self.assertNotEqual(out["status"], "repealed")

    def test_etat_vigueur_does_not_decide(self):
        """ETAT=VIGUEUR 但区间还没开始 ⇒ 仍是 unknown（不许用 ETAT 判）。"""
        out = fr_provision.adapt(self._card(date_debut="2030-01-01",
                                            etat="VIGUEUR"),
                                reference_date="2026-11-20")
        self.assertEqual(out["status"], "unknown")

    def test_no_interval_is_unknown(self):
        out = fr_provision.adapt(self._card(date_debut=None, date_fin=None),
                                reference_date="2026-11-20")
        self.assertEqual(out["status"], "unknown")

    def test_no_reference_date_falls_back_to_pool_asof(self):
        """不传参考日 ⇒ 用卡上 POOL_ASOF 兜底（时点版本基准日）。"""
        out = fr_provision.adapt(self._card(pool_asof="2026-11-15"))
        self.assertEqual(out["status"], "in_force")
        self.assertEqual(out["asof"], "2026-11-15")

    def test_sentinel_date_fin_is_kept(self):
        """2999-01-01 是「无终止」哨兵值，原样保留，不归一成「—」。"""
        out = fr_provision.adapt(self._card())
        self.assertEqual(out["effective_to"], "2999-01-01")
        self.assertEqual(out["effective_from"], "2017-05-07")

    def test_real_card(self):
        out = fr_provision.adapt(_card("fr", "D641-10-1.card.txt"))
        self.assertEqual(out["status"], "in_force")
        self.assertEqual(out["status_source"], "fr:date_range@2026-11-15")


class TestItalianProvisionStatus(unittest.TestCase):
    """意大利法条：官方件无生效区间 ⇒ 取件口径的弱口径 in_force。"""

    def test_real_card(self):
        out = it_provision.adapt(_card("it", IT_RUN, "art_1.it.card.txt"))
        self.assertEqual(out["status"], "in_force")
        self.assertEqual(out["status_source"], "it:asof_semantics@2026-11-16")
        self.assertEqual(out["asof"], "2026-11-16")

    def test_no_effective_interval(self):
        """官方层没有生效区间 ⇒ effective_from/effective_to 都是「—」。"""
        out = it_provision.adapt(_card("it", IT_RUN, "art_1.it.card.txt"))
        self.assertEqual(out["effective_from"], MISSING)
        self.assertEqual(out["effective_to"], MISSING)

    def test_without_fetch_dates_status_is_unknown(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "art_1.it.card.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# 意大利法条证据卡\n"
                     "ACT_URN: urn:nir:stato:legge:1990-08-07;241\n"
                     "ARTICLE_EID: art_1\n")
        out = it_provision.adapt(path)
        self.assertEqual(out["status"], "unknown")
        self.assertEqual(out["asof"], MISSING)


class TestCaseLinesProduceNoStatus(unittest.TestCase):
    """判例线：判决没有「效力」维度 ⇒ 不产 status，status 填「—」。"""

    def test_italian_case(self):
        out = it_case.adapt(_card("it-case", ITCASE_RUN,
                                  "ECLI-IT-COST-1956-1.itcase.card.txt"))
        self.assertEqual(out["status"], MISSING)
        self.assertEqual(out["status_source"], MISSING)
        self.assertEqual(out["asof"], MISSING)
        self.assertEqual(out["decided_on"], "1956-06-05")

    def test_french_case(self):
        out = fr_case.adapt(_card("fr-case", FRCASE_RUN,
                                  "JURITEXT000006951547.fr-case.card.txt"))
        self.assertEqual(out["status"], MISSING)
        self.assertEqual(out["status_source"], MISSING)
        self.assertEqual(out["asof"], MISSING)
        self.assertEqual(out["decided_on"], "2006-12-15")

    def test_decision_date_never_used_as_effective_from(self):
        """判决日归 decided_on，**不占用** effective_from。"""
        out = it_case.adapt(_card("it-case", ITCASE_RUN,
                                  "ECLI-IT-COST-1956-1.itcase.card.txt"))
        self.assertEqual(out["effective_from"], MISSING)
        self.assertNotEqual(out["effective_from"], out["decided_on"])


class TestItalianAgreementStatus(unittest.TestCase):
    """集体协议：到期日 ≠ 失效日 ⇒ 过期落 unknown（**不落** repealed）。"""

    def _row(self, scadenza="2029-12-31", inizio="1979-06-25"):
        return {"code": "A011", "title": "CCNL 测试",
                "inizio_storia": inizio, "scadenza_ultimo_accordo": scadenza}

    def test_real_row_is_in_force(self):
        rows = it_agreement.read_inventory(
            os.path.join(BULK_IT, "it-inventory-vigenti.tsv"))
        row = next(r for r in rows if r["code"] == "A011")
        out = it_agreement.adapt(row, reference_date="2026-11-16")
        self.assertEqual(out["status"], "in_force")
        self.assertEqual(out["effective_from"], "1979-06-25")
        self.assertEqual(out["effective_to"], "2029-12-31")
        self.assertEqual(out["asof"], "2029-12-31")

    def test_expired_is_unknown_not_repealed(self):
        """末次协议到期日过了 ⇒ unknown（不能据此判废止）。"""
        out = it_agreement.adapt(self._row(scadenza="2020-01-01"),
                                reference_date="2026-11-16")
        self.assertEqual(out["status"], "unknown")
        self.assertNotEqual(out["status"], "repealed")

    def test_missing_expiry_is_unknown(self):
        out = it_agreement.adapt(self._row(scadenza=""))
        self.assertEqual(out["status"], "unknown")

    def test_all_rows_have_dates(self):
        """实读 144 行两列全非空。"""
        rows = it_agreement.read_inventory(
            os.path.join(BULK_IT, "it-inventory-vigenti.tsv"))
        for row in rows:
            self.assertTrue(row.get("inizio_storia"), row.get("code"))
            self.assertTrue(row.get("scadenza_ultimo_accordo"), row.get("code"))


class TestStatusContractShape(unittest.TestCase):
    """三态值域、缺省标记、字段集——统一层的硬约束。"""

    def _all_real(self):
        """七个形状的真实产出（判例/协议用仓内真件）。"""
        catalog = cn_provision.load_index(os.path.join(CORPUS, "cn",
                                                        "catalog.jsonl.gz"))
        rows = it_agreement.read_inventory(
            os.path.join(BULK_IT, "it-inventory-vigenti.tsv"))
        row = next(r for r in rows if r["code"] == "A011")
        return [
            fr_provision.adapt(_card("fr", "D641-10-1.card.txt")),
            cn_provision.adapt(_card("cn", "cards", CN_CARD), index=catalog),
            es_provision.adapt(_card("es", ES_RUN, "a1.es.card.txt")),
            it_provision.adapt(_card("it", IT_RUN, "art_1.it.card.txt")),
            it_case.adapt(_card("it-case", ITCASE_RUN,
                                "ECLI-IT-COST-1956-1.itcase.card.txt")),
            fr_case.adapt(_card("fr-case", FRCASE_RUN,
                                "JURITEXT000006951547.fr-case.card.txt")),
            it_agreement.adapt(row),
        ]

    def test_status_never_outside_the_closed_set(self):
        """status 只能是三态 ＋「—」（不许出现 not_in_force 之类）。"""
        for out in self._all_real():
            self.assertIn(out["status"], STATUS_VALUES, out)

    def test_no_not_in_force_value_anywhere(self):
        """枚举名以契约草案 §2.2 为准：没有 not_in_force。"""
        for out in self._all_real():
            self.assertNotEqual(out["status"], "not_in_force")
        self.assertEqual(status.STATUSES,
                         ("in_force", "repealed", "unknown"))

    def test_status_source_always_present(self):
        """status_source 要能回答「谁判的、凭什么判的」⇒ 不许为空。

        ⚠️ 判例线不产 status ⇒ status_source 同为「—」（与 status 对齐）。
        """
        for out in self._all_real():
            self.assertTrue(out["status_source"], out)
            if out["status"] == MISSING:
                self.assertEqual(out["status_source"], MISSING, out)
            else:
                self.assertNotEqual(out["status_source"], MISSING, out)

    def test_missing_marker_is_the_receipt_one(self):
        """缺省标记与收据五元组同一个（不新造标记形状）。"""
        self.assertEqual(MISSING, RECEIPT_MISSING)
        self.assertEqual(MISSING, "—")

    def test_asof_missing_uses_the_same_marker(self):
        """asof 取不到 ⇒ 同一个「—」，不是别的形状。"""
        out = it_case.adapt(_card("it-case", ITCASE_RUN,
                                  "ECLI-IT-COST-1956-1.itcase.card.txt"))
        self.assertEqual(out["asof"], MISSING)
        self.assertEqual(out["asof"], RECEIPT_MISSING)

    def test_field_set_matches_contract(self):
        """字段名逐字照抄契约草案 §2.2（本轮落的那几个）。"""
        self.assertEqual(sorted(FIELDS), sorted([
            "kind", "jurisdiction", "local_id", "canonical_id",
            "effective_from", "effective_to", "status", "asof",
            "decided_on", "status_source", "span", "face", "how"]))

    def test_every_adapter_returns_all_fields(self):
        for out in self._all_real():
            self.assertEqual(sorted(out), sorted(FIELDS))

    def test_canonical_id_is_missing_in_v0(self):
        """canonical_id v0 统一填「—」（官方数据里无此字段）。"""
        for out in self._all_real():
            self.assertEqual(out["canonical_id"], MISSING)


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
                           "local_id": "VIEW-0001", "status": "in_force",
                           "asof": "2026-11-15"})
        out = adapters.adapt("fr_provision", self.card,
                             view={rec["card"]: rec}, corpus_root=self.root)
        self.assertEqual(out["local_id"], "VIEW-0001")
        self.assertEqual(out["status"], "in_force")

    def test_view_missing_field_falls_back_to_card(self):
        rec = view_record("fr_provision", view_key(self.card, self.root),
                          {"kind": "provision", "jurisdiction": "fr",
                           "local_id": ""})
        out = adapters.adapt("fr_provision", self.card,
                             view={rec["card"]: rec}, corpus_root=self.root)
        self.assertEqual(out["local_id"], "D641-10-1")
        self.assertEqual(out["status"], "in_force")

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

    def test_output_has_the_contract_fields(self):
        out = adapters.adapt("fr_provision", self.card)
        self.assertEqual(sorted(out), sorted(FIELDS))


class TestFailClosed(unittest.TestCase):
    """取不到必填字段 ⇒ 报错，不给空值混进统一层。"""

    def test_wrong_shape_card_raises(self):
        """把中国卡喂给法国 adapter ⇒ 必须报错，不能蒙一个 kind 出来。"""
        with self.assertRaises(ContractFieldMissing):
            fr_provision.adapt(_card("cn", "cards", CN_CARD))

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

    def test_status_fields_do_not_mask_fail_closed(self):
        """加了 status/asof 之后，**必填字段取不到仍然报错**（不被兜底吞掉）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.cn.card.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 中国法规证据卡\nSXX: 3\nSXRQ: 2013-07-01\n")
            with self.assertRaises(ContractFieldMissing):
                cn_provision.adapt(path)
            with self.assertRaises(ContractFieldMissing):
                es_provision.adapt(path)

    def test_fail_closed_error_carries_shape_and_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.it.card.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 只有注释\n")
            with self.assertRaises(ContractFieldMissing) as ctx:
                it_provision.adapt(path)
        self.assertEqual(ctx.exception.shape, "it_provision")
        self.assertEqual(ctx.exception.field, "local_id")


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

    def test_status_constants_match_the_contract(self):
        self.assertEqual(adapters.STATUS_IN_FORCE, "in_force")
        self.assertEqual(adapters.STATUS_REPEALED, "repealed")
        self.assertEqual(adapters.STATUS_UNKNOWN, "unknown")
        self.assertEqual(adapters.STATUS_NA, MISSING)


class TestCorpusUntouched(unittest.TestCase):
    """公共层是只读派生的：跑完 adapter，卡片一个字节都不能变。"""

    def test_cards_unchanged_after_adapt(self):
        targets = [
            _card("fr", "D641-10-1.card.txt"),
            _card("cn", "cards", CN_CARD),
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


# ---------------------------------------------------------------------------
# 第 4 步：卡级收据五元组后三位（span / face / how）
# ---------------------------------------------------------------------------

class TestCardReceiptProjection(unittest.TestCase):
    """卡级 `span` / `face` / `how`：每个形状「取到」＋「取不到落『—』」两例。

    口径（与收据五元组**同一个**，不另立定义）：
      * 「值」＝**这张卡自己钉住的官方正文**；
      * 「官方正文」＝该线 `factscribe_legal/lines.py` 适配点所用的那份官方文本；
      * `span`＝`receipts.span_in_text`、`face`＝`lines._face_of`、
        `how`＝该线适配点定的核验方式；
      * 取不到 ⇒ 缺省标记「—」（＝`factscribe_legal/receipts.py:34` 的
        `MISSING`，与收据五元组同一个）。
    """

    # 值域（factscribe_legal/receipts.py:13-17 的字段定义）
    FACE_VALUES = ("body", "résumé", MISSING)
    HOW_VALUES = ("contains", "numnorm", "catalog", MISSING)

    # ---------------- 法国法条 ----------------

    def test_fr_provision_present(self):
        """法国法条：卡所钉正文＝官方 XML 的 BLOC_TEXTUEL 归一正文（364 字）。"""
        out = fr_provision.adapt(_card("fr", "D641-10-1.card.txt"))
        self.assertEqual(out["span"], "0-364")
        self.assertEqual(out["face"], "body")
        self.assertEqual(out["how"], "contains")

    def test_fr_provision_missing_official_xml(self):
        """官方件不在仓内 ⇒ 三位全「—」（**我们还没接**：法国批量件在仓外）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.card.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 法国法条证据卡\nNUM: X-1\nOFFICIAL_XML: X.xml\n")
            out = fr_provision.adapt(path)
        self.assertEqual(out["span"], MISSING)
        self.assertEqual(out["face"], MISSING)
        self.assertEqual(out["how"], MISSING)

    # ---------------- 中国法规 ----------------

    def test_cn_provision_how_is_catalog(self):
        """中国法规：how＝catalog（目录树·详情元数据对账；lines.py 的 cn 行）。"""
        out = cn_provision.adapt(_card("cn", "cards", CN_CARD))
        self.assertEqual(out["how"], "catalog")

    def test_cn_provision_span_face_missing_no_article_text(self):
        """官方详情 JSON 无条文正文 ⇒ span/face「—」（**官方数据里没有这个概念**）。"""
        out = cn_provision.adapt(_card("cn", "cards", CN_CARD))
        self.assertEqual(out["span"], MISSING)
        self.assertEqual(out["face"], MISSING)

    # ---------------- 西班牙法条 ----------------

    def test_es_provision_present(self):
        out = es_provision.adapt(_card("es", ES_RUN, "a1.es.card.txt"))
        self.assertEqual(out["span"], "0-600")
        self.assertEqual(out["face"], "body")
        self.assertEqual(out["how"], "contains")

    def test_es_provision_missing_official_material(self):
        """卡不内嵌正文且切片件没取到 ⇒ span/face「—」（how 仍是该线常量）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a1.es.card.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 西班牙法条证据卡\n"
                         "ACT_ID: BOE-A-2015-10565\nBLOCK_ID: a1\n")
            out = es_provision.adapt(path)
        self.assertEqual(out["span"], MISSING)
        self.assertEqual(out["face"], MISSING)
        self.assertEqual(out["how"], "contains")

    def test_es_provision_falls_back_to_embedded_text(self):
        """切片件不在仓内 ⇒ 退回卡内嵌正文（同 lines.py 的兜底顺序）。"""
        card = _card("es", ES_RUN, "a1.es.card.txt")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a1.es.card.txt")
            shutil.copyfile(card, path)
            out = es_provision.adapt(path)
        self.assertNotEqual(out["span"], MISSING)
        self.assertTrue(out["span"].startswith("0-"), out["span"])
        self.assertEqual(out["face"], "body")

    # ---------------- 意大利法条 ----------------

    def test_it_provision_present(self):
        out = it_provision.adapt(_card("it", IT_RUN, "art_1.it.card.txt"))
        self.assertEqual(out["span"], "0-600")
        self.assertEqual(out["face"], "body")
        self.assertEqual(out["how"], "contains")

    def test_it_provision_missing_official_material(self):
        """卡不内嵌正文且切片件没取到 ⇒ span/face「—」（how 仍是该线常量）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "art_1.it.card.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 意大利法条证据卡\n"
                         "ACT_URN: urn:nir:stato:legge:1990-08-07;241\n"
                         "ARTICLE_EID: art_1\n")
            out = it_provision.adapt(path)
        self.assertEqual(out["span"], MISSING)
        self.assertEqual(out["face"], MISSING)
        self.assertEqual(out["how"], "contains")

    # ---------------- 意大利判例 ----------------

    def test_it_case_present(self):
        out = it_case.adapt(_card("it-case", ITCASE_RUN,
                                  "ECLI-IT-COST-1956-1.itcase.card.txt"))
        self.assertEqual(out["span"], "0-599")
        self.assertEqual(out["face"], "body")
        self.assertEqual(out["how"], "contains")

    def test_it_case_missing_official_material(self):
        """卡不内嵌正文且判决切片件没取到 ⇒ 三位全「—」（how 由值推出，值也没了）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "E.itcase.card.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 意大利宪法法院判例证据卡\n"
                         "ECLI: ECLI:IT:COST:1956:1\n")
            out = it_case.adapt(path)
        self.assertEqual(out["span"], MISSING)
        self.assertEqual(out["face"], MISSING)
        self.assertEqual(out["how"], MISSING)

    # ---------------- 法国判例 ----------------

    def test_fr_case_present(self):
        """法国判例：判决正文段在官方还原件**全文**里的坐标（330-13669）。"""
        out = fr_case.adapt(_card("fr-case", FRCASE_RUN,
                                  "JURITEXT000006951547.fr-case.card.txt"))
        self.assertEqual(out["span"], "330-13669")
        self.assertEqual(out["face"], "body")
        self.assertEqual(out["how"], "contains")

    def test_fr_case_missing_official_txt(self):
        """官方还原件不在仓内 ⇒ 三位全「—」。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "C.fr-case.card.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 法国判例证据卡\n"
                         "CASE_ID: C1\nOFFICIAL_TXT: official/C1.txt\n")
            out = fr_case.adapt(path)
        self.assertEqual(out["span"], MISSING)
        self.assertEqual(out["face"], MISSING)
        self.assertEqual(out["how"], MISSING)

    # ---------------- 集体协议（CCNL） ----------------

    def test_agreement_all_three_missing(self):
        """CCNL：仓内只有元数据、官方全文端点本层不调用 ⇒ 三位全「—」。"""
        rows = it_agreement.read_inventory(
            os.path.join(BULK_IT, "it-inventory-vigenti.tsv"))
        row = next(r for r in rows if r["code"] == "A011")
        out = it_agreement.adapt(row)
        self.assertEqual(out["span"], MISSING)
        self.assertEqual(out["face"], MISSING)
        self.assertEqual(out["how"], MISSING)

    def test_agreement_has_no_line_to_borrow_how_from(self):
        """CCNL 在 lines.py 的七条线里没有对应的一条 ⇒ how 不借用他线口径。"""
        from factscribe_legal import lines
        ids = [ln.id for ln in lines.LINES]
        self.assertNotIn("agreement", ids)
        self.assertNotIn("ccnl", ids)
        self.assertEqual(len(ids), 7)

    # ---------------- 跨形状 ----------------

    def _all_real(self):
        """七个形状的真实产出（判例/协议用仓内真件）。"""
        catalog = cn_provision.load_index(
            os.path.join(CORPUS, "cn", "catalog.jsonl.gz"))
        rows = it_agreement.read_inventory(
            os.path.join(BULK_IT, "it-inventory-vigenti.tsv"))
        row = next(r for r in rows if r["code"] == "A011")
        return [
            ("fr_provision",
             fr_provision.adapt(_card("fr", "D641-10-1.card.txt"))),
            ("cn_provision",
             cn_provision.adapt(_card("cn", "cards", CN_CARD), index=catalog)),
            ("es_provision",
             es_provision.adapt(_card("es", ES_RUN, "a1.es.card.txt"))),
            ("it_provision",
             it_provision.adapt(_card("it", IT_RUN, "art_1.it.card.txt"))),
            ("it_case",
             it_case.adapt(_card("it-case", ITCASE_RUN,
                                 "ECLI-IT-COST-1956-1.itcase.card.txt"))),
            ("fr_case",
             fr_case.adapt(_card("fr-case", FRCASE_RUN,
                                 "JURITEXT000006951547.fr-case.card.txt"))),
            ("it_agreement", it_agreement.adapt(row)),
        ]

    def test_every_shape_fills_the_three_fields(self):
        for shape, out in self._all_real():
            for name in ("span", "face", "how"):
                self.assertIn(name, out, shape)
                self.assertTrue(out[name], "%s 的 %s 是空的" % (shape, name))

    def test_face_and_how_stay_in_their_value_domains(self):
        """face ∈ {body, résumé,「—」}；how ∈ {contains, numnorm, catalog,「—」}。"""
        for shape, out in self._all_real():
            self.assertIn(out["face"], self.FACE_VALUES, shape)
            self.assertIn(out["how"], self.HOW_VALUES, shape)

    def test_span_format_is_offset_range_or_missing(self):
        """span 形如 "s-e"（原文坐标区间）；取不到 ⇒ 「—」。"""
        for shape, out in self._all_real():
            if out["span"] == MISSING:
                continue
            self.assertRegex(out["span"], r"^\d+-\d+$", shape)

    def test_span_uses_the_same_primitive_as_the_receipt(self):
        """卡级 span 用的就是收据那套 span_in_text（**不是另写一套**）。"""
        from factscribe_legal import receipts
        from factscribe_legal.es_verify import _plain_text as es_plain
        card = _card("es", ES_RUN, "a1.es.card.txt")
        value = card_receipts.embedded_text(card)
        with open(os.path.join(os.path.dirname(card), "official", "a1.xml"),
                  encoding="utf-8") as fh:
            official = es_plain(fh.read())
        out = es_provision.adapt(card)
        self.assertEqual(out["span"], receipts.span_in_text(value, official))

    def test_truncation_marker_is_stripped_before_locating(self):
        """卡内嵌正文尾部的「…」是取件端点的截断记号（tools/fetch_corpus.py:1427），
        **不是**官方正文 ⇒ 定位前剥掉。"""
        card = _card("es", ES_RUN, "a1.es.card.txt")
        with open(card, encoding="utf-8") as fh:
            raw = fh.read()
        self.assertIn(card_receipts.TRUNCATION_MARK, raw)
        self.assertFalse(card_receipts.embedded_text(card)
                         .endswith(card_receipts.TRUNCATION_MARK))
        self.assertEqual(card_receipts.strip_truncation("abc…"), "abc")

    def test_missing_marker_is_the_receipt_one(self):
        """三字段取不到 ⇒ 用收据五元组同一个「—」，不新造标记形状。"""
        from factscribe_legal.receipts import MISSING as RECEIPT_MISSING
        self.assertEqual(MISSING, RECEIPT_MISSING)
        self.assertEqual(MISSING, "—")


if __name__ == "__main__":
    unittest.main()
