#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法律侧**只读接口层**（api 族）的自测：标准库 unittest，零网络、零写仓。

钉住七件事：
  1. 契约形状：版本号 + 七路通道齐全；
  2. **七条线各自的 JSON 出口**（用仓内真语料造临时项目，能跑的几条线都跑）；
  3. 收据五元组：字段固定五元、缺省标记统一、缺省字段正确；
  4. 时效字段：四种来源（区间/状态标志/时点戳/日期）归一成同一形状；
  5. 语料件清单：只列真实可见的件 ＋ 过滤（国家/域/状态）；
  6. 判定码表：与本包 README 的冻结码表**逐条对表**（一个不多一个不少）；
  7. 待批提案：只读返回空数组（不建写路径）。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from factscribe_legal import code_table                      # noqa: E402
from factscribe_legal import receipts                         # noqa: E402
from factscribe_legal import timeliness as tl                  # noqa: E402
from factscribe_legal.api import (API_VERSION, CHANNELS,       # noqa: E402
                                  build_contract, context_from_project)

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "..")
CORPUS = os.path.join(PKG, "corpus")
README = os.path.join(PKG, "README.md")

# 收据五元组（契约的一部分）
RECEIPT_FIELDS = ("id", "sha16", "span", "face", "how")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _sha_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _literal_token(text, min_len=3):
    """从正文里挑一个**原样出现**的数值 token（保证收据 span 定位得到）。"""
    for m in re.finditer(r"\d[\d.,]{%d,}" % (min_len - 1), text or ""):
        return m.group(0)
    return ""


def _fact(proj, name, fid, value, source, sha):
    _write(os.path.join(proj, "facts", name),
           'schema = "paperkit-fact/3.0"\n\n[[fact]]\n'
           'id = "%s"\nclaim = "接口层测试事实"\nvalue = "%s"\n'
           'source = "%s"\nsource_sha256 = "sha256:%s"\n'
           'locator = "test"\nconfidence = "high"\nderived_from = []\n'
           % (fid, value, source, sha))


def _card_text(path):
    text = _read(path)
    marker = "--- OFFICIAL TEXT ---"
    if marker not in text:
        return ""
    return text.split(marker, 1)[1]


# ---------------------------------------------------------------------------
# 临时项目（用仓内真语料造；缺材料的线标 skipped，不造假件）
# ---------------------------------------------------------------------------

def _fr_project(tmp):
    """法国法条：仓内 corpus/fr 的真件（条文 XML ＋ 证据卡）。"""
    import xml.etree.ElementTree as ET
    from factscribe_legal.provisions import norm_text
    proj = os.path.join(tmp, "proj")
    shutil.copytree(os.path.join(CORPUS, "fr"), os.path.join(proj, "corpus-fr"))
    num = "L594-8"
    card = os.path.join(proj, "corpus-fr", num + ".card.txt")
    xml = os.path.join(proj, "corpus-fr", num + ".xml")
    with open(xml, "rb") as fh:
        root = ET.fromstring(fh.read())
    text = norm_text(root.find("BLOC_TEXTUEL"))
    value = _literal_token(text) or "2012"
    _fact(proj, "40-fr.toml", "FR-API-1", value,
          "corpus-fr/%s.card.txt" % num, _sha_file(card))
    return proj


def _cn_project(tmp):
    """中国法规：仓内 corpus/cn 的真卡（官方详情 JSON **无正文**）。"""
    proj = os.path.join(tmp, "proj")
    shutil.copytree(os.path.join(CORPUS, "cn"), os.path.join(proj, "corpus-cn"))
    cards = sorted(os.listdir(os.path.join(proj, "corpus-cn", "cards")))
    card_rel = "corpus-cn/cards/%s" % cards[0]
    card = os.path.join(proj, card_rel)
    fields = {}
    for line in _read(card).splitlines():
        if ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    _fact(proj, "41-cn.toml", "CN-API-1", fields.get("SXRQ", ""),
          card_rel, _sha_file(card))
    return proj


def _case_project(tmp):
    """中国案例：仓内 0 件 ⇒ 本地造一件（官方正文 + 卡 + 证据链）。"""
    proj = os.path.join(tmp, "proj")
    official = ("基本案情\n　　张某于2015年4月1日入职某公司。\n"
                "　　一、某宝销售公司支付张某违法解除劳动合同赔偿金146160元；\n"
                "　　重庆市第一中级人民法院于2023年10月20日作出（2023）渝01民终7708号"
                "民事判决。\n")
    run = os.path.join(proj, "runs", "run-20261114-case")
    slug = "张某诉某公司劳动争议案"
    _write(os.path.join(run, "official", slug + ".txt"), official)
    fields = {"CASE_NO": "（2023）渝01民终7708号",
              "JUDGE_DATE": "2023.10.20",
              "AMOUNTS": "146160",
              "OFFICIAL_TEXT_SHA256": hashlib.sha256(
                  official.encode("utf-8")).hexdigest()}
    card = "# 案例证据卡\n" + "".join("%s: %s\n" % kv for kv in fields.items())
    card += "--- OFFICIAL TEXT ---\n" + official
    card_rel = "runs/run-20261114-case/%s.case.card.txt" % slug
    _write(os.path.join(proj, card_rel), card)
    _fact(proj, "42-case.toml", "CASE-API-1", "146160", card_rel,
          _sha_file(os.path.join(proj, card_rel)))
    _write(os.path.join(run, "result.json"),
           json.dumps({"run_id": "run-20261114-case"}, ensure_ascii=False))
    _write(os.path.join(run, "record.json"),
           json.dumps({"run_id": "run-20261114-case",
                       "facts": ["CASE-API-1"]}, ensure_ascii=False))
    return proj


def _it_project(tmp):
    """意大利法条：仓内 corpus/it 的真件。"""
    proj = os.path.join(tmp, "proj")
    run = "run-20261116-it-1990n241"
    shutil.copytree(os.path.join(CORPUS, "it", run),
                    os.path.join(proj, "corpus-it"))
    card_rel = "corpus-it/art_1.it.card.txt"
    card = os.path.join(proj, card_rel)
    value = _literal_token(_card_text(card)) or "1"
    _fact(proj, "43-it.toml", "IT-API-1", value, card_rel, _sha_file(card))
    return proj


def _es_project(tmp):
    """西班牙法条：仓内 corpus/es 的真件。"""
    proj = os.path.join(tmp, "proj")
    run = "run-20261116-es-ley39-2015-procedimiento-administrativo"
    shutil.copytree(os.path.join(CORPUS, "es", run),
                    os.path.join(proj, "corpus-es"))
    card_rel = "corpus-es/a1.es.card.txt"
    card = os.path.join(proj, card_rel)
    value = _literal_token(_card_text(card)) or "1"
    _fact(proj, "44-es.toml", "ES-API-1", value, card_rel, _sha_file(card))
    return proj


def _fr_case_project(tmp):
    """法国判例：仓内 corpus/fr-case 的真判决。"""
    proj = os.path.join(tmp, "proj")
    run = "run-20261116-inca"
    shutil.copytree(os.path.join(CORPUS, "fr-case", run),
                    os.path.join(proj, "runs", run))
    case_id = "JURITEXT000006953017"
    card_rel = "runs/%s/%s.fr-case.card.txt" % (run, case_id)
    card = os.path.join(proj, card_rel)
    body = _read(os.path.join(proj, "runs", run, "official",
                              "%s.txt" % case_id))
    value = _literal_token(body.split("[CONTENU]")[-1]) or "1166"
    _fact(proj, "45-frcase.toml", "FRCASE-API-1", value, card_rel,
          _sha_file(card))
    return proj


def _it_case_project(tmp):
    """意大利宪法法院判例：仓内 corpus/it-case 的真判决。"""
    proj = os.path.join(tmp, "proj")
    run = "run-20261116-itcase-1956_1980"
    shutil.copytree(os.path.join(CORPUS, "it-case", run),
                    os.path.join(proj, "corpus-itcase"))
    card_rel = "corpus-itcase/ECLI-IT-COST-1956-1.itcase.card.txt"
    card = os.path.join(proj, card_rel)
    value = _literal_token(_card_text(card)) or "1"
    _fact(proj, "46-itcase.toml", "ITCASE-API-1", value, card_rel,
          _sha_file(card))
    return proj


# ---------------------------------------------------------------------------
# 1. 契约形状
# ---------------------------------------------------------------------------

class TestContractShape(unittest.TestCase):
    """版本号 ＋ 七路通道齐全。"""

    def test_version_and_seven_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _fr_project(tmp)
            ctx = context_from_project(proj, corpus="corpus-fr",
                                       date="2026-11-14")
            contract = build_contract(ctx)
        self.assertEqual(contract["version"], API_VERSION)
        self.assertEqual(contract["schema"], API_VERSION)
        self.assertTrue(contract["read_only"])
        for channel in CHANNELS:
            self.assertIn(channel, contract, "缺通道：%s" % channel)
        self.assertEqual(len(CHANNELS), 7)

    def test_proposals_is_empty_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _fr_project(tmp)
            ctx = context_from_project(proj, corpus="corpus-fr",
                                       date="2026-11-14")
            contract = build_contract(ctx, channels=["proposals"])
        self.assertEqual(contract["proposals"]["items"], [])
        self.assertEqual(contract["proposals"]["total"], 0)
        self.assertIn("第 ② 步", contract["proposals"]["note"])

    def test_channel_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _fr_project(tmp)
            ctx = context_from_project(proj, corpus="corpus-fr",
                                       date="2026-11-14")
            contract = build_contract(ctx, channels=["codes"])
        self.assertIn("codes", contract)
        self.assertNotIn("findings", contract)
        self.assertNotIn("receipts", contract)


# ---------------------------------------------------------------------------
# 2. 七条线各自的 JSON 出口
# ---------------------------------------------------------------------------

class TestSevenLinesJsonExit(unittest.TestCase):
    """七条线各自能出 JSON；跑不了的线如实标 skipped（不崩、不造假件）。"""

    CASES = (
        ("fr", _fr_project, "corpus-fr"),
        ("cn", _cn_project, "corpus-cn"),
        ("case", _case_project, None),
        ("it", _it_project, "corpus-it"),
        ("es", _es_project, "corpus-es"),
        ("fr-case", _fr_case_project, None),
        ("it-case", _it_case_project, "corpus-itcase"),
    )

    def test_each_line_has_json_exit(self):
        for line_id, builder, corpus in self.CASES:
            with self.subTest(line=line_id):
                with tempfile.TemporaryDirectory() as tmp:
                    proj = builder(tmp)
                    ctx = context_from_project(proj, corpus=corpus,
                                               date="2026-11-14")
                    contract = build_contract(ctx, channels=["findings",
                                                             "receipts"])
                lines = {ln["line"]: ln
                         for ln in contract["findings"]["lines"]}
                self.assertIn(line_id, lines)
                self.assertEqual(lines[line_id]["status"], "ran",
                                 "%s 线应当跑起来：%s"
                                 % (line_id, lines[line_id]["note"]))
                for item in lines[line_id]["items"]:
                    self.assertIn(item["severity"], ("red", "yellow"))
                    self.assertTrue(item["code"])
                    self.assertTrue(item["message"])
                receipts = {ln["line"]: ln
                            for ln in contract["receipts"]["lines"]}
                self.assertIn(line_id, receipts)
                self.assertGreaterEqual(receipts[line_id]["total"], 1,
                                        "%s 线应当有收据" % line_id)

    def test_missing_material_is_skipped_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _case_project(tmp)
            ctx = context_from_project(proj, date="2026-11-14")
            contract = build_contract(ctx, channels=["findings"])
        lines = {ln["line"]: ln for ln in contract["findings"]["lines"]}
        self.assertEqual(lines["it"]["status"], "skipped")
        self.assertTrue(lines["it"]["note"])
        self.assertEqual(lines["it"]["red"], 0)
        self.assertEqual(lines["it"]["yellow"], 0)


# ---------------------------------------------------------------------------
# 3. 收据五元组：形状与缺省标记
# ---------------------------------------------------------------------------

class TestReceiptQuintuple(unittest.TestCase):
    """字段固定五元；缺省标记统一；六条新接入线的形状。"""

    def _receipts(self, tmp, builder, corpus):
        proj = builder(tmp)
        ctx = context_from_project(proj, corpus=corpus, date="2026-11-14")
        contract = build_contract(ctx, channels=["receipts"])
        for ln in contract["receipts"]["lines"]:
            if ln["items"]:
                return ln["line"], ln["items"]
        return None, []

    def test_fields_are_exactly_five(self):
        for line_id, builder, corpus in TestSevenLinesJsonExit.CASES:
            with self.subTest(line=line_id):
                with tempfile.TemporaryDirectory() as tmp:
                    line, items = self._receipts(tmp, builder, corpus)
                    self.assertEqual(line, line_id)
                    for it in items:
                        self.assertEqual(tuple(it.keys()), RECEIPT_FIELDS)
                        self.assertEqual(len(it), 5)

    def test_cn_line_has_no_body_face_and_span(self):
        """中国侧官方件无正文 ⇒ span/face 取缺省标记（不是新造的形状）。"""
        with tempfile.TemporaryDirectory() as tmp:
            line, items = self._receipts(tmp, _cn_project, "corpus-cn")
        self.assertEqual(line, "cn")
        self.assertTrue(items)
        for it in items:
            self.assertEqual(it["span"], receipts.MISSING)
            self.assertEqual(it["face"], receipts.MISSING)
            self.assertEqual(it["how"], "catalog")
            self.assertTrue(it["sha16"])

    def test_sha16_is_first16_of_pinned_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _fr_project(tmp)
            ctx = context_from_project(proj, corpus="corpus-fr",
                                       date="2026-11-14")
            contract = build_contract(ctx, channels=["receipts"])
            items = [it for ln in contract["receipts"]["lines"]
                     for it in ln["items"]]
        self.assertTrue(items)
        for it in items:
            self.assertRegex(it["sha16"], r"^[0-9a-f]{16}$")

    def test_span_is_located_in_official_text(self):
        """能定位的线：span 必须是 s-e 且命中面是 body。"""
        for line_id, builder, corpus in (("fr", _fr_project, "corpus-fr"),
                                         ("it", _it_project, "corpus-it"),
                                         ("es", _es_project, "corpus-es"),
                                         ("fr-case", _fr_case_project, None)):
            with self.subTest(line=line_id):
                with tempfile.TemporaryDirectory() as tmp:
                    line, items = self._receipts(tmp, builder, corpus)
                self.assertTrue(items, "%s 线应当有收据" % line_id)
                for it in items:
                    self.assertRegex(it["span"], r"^\d+-\d+$")
                    self.assertEqual(it["face"], "body")

    def test_missing_marker_is_dash_everywhere(self):
        self.assertEqual(receipts.MISSING, "—")
        self.assertEqual(receipts.RECEIPT_FIELDS, RECEIPT_FIELDS)

    def test_span_tolerates_nbsp_and_newline(self):
        """span 算法容忍 NBSP／窄空格／换行（法国判例线收据算法的口径）。"""
        text = "Article 1\u00a0—\u202fdu 30 heures et 35 heures"
        span = receipts.span_in_text("30 heures et 35 heures", text)
        self.assertNotEqual(span, receipts.MISSING)
        start, end = span.split("-")
        self.assertEqual(text[int(start):int(end)],
                         "30 heures et 35 heures")

    def test_receipt_shape_helper_fills_missing(self):
        row = receipts.build_receipt("F-1", "sha256:" + "ab" * 32)
        self.assertEqual(tuple(row.keys()), RECEIPT_FIELDS)
        self.assertEqual(row["sha16"], "ab" * 8)
        self.assertEqual(row["span"], receipts.MISSING)
        self.assertEqual(row["face"], receipts.MISSING)
        self.assertEqual(row["how"], receipts.MISSING)


# ---------------------------------------------------------------------------
# 4. 时效字段：四种来源归一成同一形状
# ---------------------------------------------------------------------------

class TestTimeliness(unittest.TestCase):
    """跨域统一形状；四种来源各一例。"""

    SHAPE = ("domain", "kind", "item_id", "reference_date", "state",
             "state_label", "effective_from", "effective_to", "source",
             "source_fields", "note")

    def test_fr_interval_maps_to_in_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _fr_project(tmp)
            ctx = context_from_project(proj, corpus="corpus-fr",
                                       date="2026-11-14")
            contract = build_contract(ctx, channels=["timeliness"])
        rows = [it for it in contract["timeliness"]["items"]
                if it["domain"] == "fr"]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(tuple(row.keys()), self.SHAPE)
            self.assertEqual(row["source"], "区间")
            self.assertEqual(row["source_fields"], ["date_debut", "date_fin"])
            self.assertEqual(row["state"], "in_force")
            self.assertEqual(row["reference_date"], "2026-11-14")

    def test_cn_status_flag_maps_to_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _cn_project(tmp)
            ctx = context_from_project(proj, corpus="corpus-cn",
                                       date="2026-11-14")
            contract = build_contract(ctx, channels=["timeliness"])
        rows = [it for it in contract["timeliness"]["items"]
                if it["domain"] == "cn"]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["source"], "状态标志")
            self.assertEqual(row["source_fields"], ["sxx"])
            self.assertEqual(row["state"], "in_force")
            self.assertEqual(row["effective_from"], "")

    def test_it_es_version_stamp_maps_to_gap(self):
        for builder, corpus, domain in ((_it_project, "corpus-it", "it"),
                                         (_es_project, "corpus-es", "es")):
            with self.subTest(domain=domain):
                with tempfile.TemporaryDirectory() as tmp:
                    proj = builder(tmp)
                    ctx = context_from_project(proj, corpus=corpus,
                                               date="2026-11-14")
                    contract = build_contract(ctx, channels=["timeliness"])
                rows = [it for it in contract["timeliness"]["items"]
                        if it["domain"] == domain]
                self.assertTrue(rows)
                for row in rows:
                    self.assertEqual(row["source"], "时点戳")
                    self.assertEqual(row["source_fields"], ["version_date"])
                    self.assertEqual(row["state"], "version_gap")

    def test_case_date_maps_to_historical(self):
        for builder, corpus, domain in ((_fr_case_project, None, "fr-case"),
                                         (_it_case_project, "corpus-itcase",
                                          "it-case")):
            with self.subTest(domain=domain):
                with tempfile.TemporaryDirectory() as tmp:
                    proj = builder(tmp)
                    ctx = context_from_project(proj, corpus=corpus,
                                               date="2026-11-14")
                    contract = build_contract(ctx, channels=["timeliness"])
                rows = [it for it in contract["timeliness"]["items"]
                        if it["domain"] == domain]
                self.assertTrue(rows)
                for row in rows:
                    self.assertEqual(row["source"], "日期")
                    self.assertEqual(row["state"], "historical")
                    self.assertTrue(row["effective_from"])

    def test_case_line_has_no_timeliness_material(self):
        """中国案例官方件不含时效材料 ⇒ not_applicable（不是 unknown）。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = _case_project(tmp)
            ctx = context_from_project(proj, date="2026-11-14")
            contract = build_contract(ctx, channels=["timeliness"])
        rows = [it for it in contract["timeliness"]["items"]
                if it["domain"] == "case"]
        for row in rows:
            self.assertEqual(row["state"], "not_applicable")


# ---------------------------------------------------------------------------
# 5. 语料件清单：真实件 ＋ 过滤
# ---------------------------------------------------------------------------

class TestCorpusChannel(unittest.TestCase):
    """只列真实可见的件；可按国家/域/状态过滤。"""

    def _items(self):
        ctx = context_from_project("fixtures/legal-demo")
        contract = build_contract(ctx, channels=["corpus"])
        return contract["corpus"]["items"]

    def test_packaged_corpus_items_are_real(self):
        items = self._items()
        counts = {}
        for it in items:
            counts[it["domain"]] = counts.get(it["domain"], 0) + 1
        # 仓内真件分布：FR 法条 3／FR 判例 4／CN 法规 2／IT 切片 4／
        # ES 切片 9／IT 判例 2（CN 案例 0 件：材料在项目 runs/ 里）
        self.assertGreaterEqual(counts.get("fr", 0), 3)
        self.assertGreaterEqual(counts.get("fr-case", 0), 4)
        self.assertGreaterEqual(counts.get("cn", 0), 2)
        self.assertGreaterEqual(counts.get("it", 0), 4)
        self.assertGreaterEqual(counts.get("es", 0), 9)
        self.assertGreaterEqual(counts.get("it-case", 0), 2)
        for it in items:
            self.assertTrue(it["id"])
            self.assertIn(it["country"], ("法国", "中国", "意大利", "西班牙"))
            self.assertTrue(it["path"])

    def test_filter_by_country(self):
        ctx = context_from_project("fixtures/legal-demo")
        contract = build_contract(ctx, channels=["corpus"],
                                  filters={"country": "法国"})
        for it in contract["corpus"]["items"]:
            self.assertEqual(it["country"], "法国")
        self.assertTrue(contract["corpus"]["items"])

    def test_filter_by_domain_and_state(self):
        ctx = context_from_project("fixtures/legal-demo")
        contract = build_contract(ctx, channels=["corpus"],
                                  filters={"domain": "fr-case"})
        self.assertTrue(contract["corpus"]["items"])
        for it in contract["corpus"]["items"]:
            self.assertEqual(it["domain"], "fr-case")
        contract = build_contract(ctx, channels=["corpus"],
                                  filters={"state": "historical"})
        self.assertTrue(contract["corpus"]["items"])
        for it in contract["corpus"]["items"]:
            self.assertEqual(it["timeliness"]["state"], "historical")


# ---------------------------------------------------------------------------
# 6. 判定码表：与 README 冻结表逐条对表
# ---------------------------------------------------------------------------

class TestCodeTable(unittest.TestCase):
    """机读副本与 README 的冻结码表必须逐条一致（一个不多一个不少）。"""

    def _readme_codes(self):
        rows = []
        for line in _read(README).splitlines():
            if not line.startswith("|"):
                continue
            cells = line.split("|")
            if len(cells) < 4:
                continue
            head = cells[1].strip()
            if head.startswith("`verify"):
                # README 的闸表行：第 2 格＝红码，第 3 格＝黄码
                for cell, sev in ((cells[2], "红"), (cells[3], "黄")):
                    for code in re.findall(r"`([A-Z][A-Z0-9_]+)`", cell):
                        rows.append((code, sev))
            elif head.startswith("`") and cells[2].strip() in ("红", "黄"):
                rows.append((head.strip("`"), cells[2].strip()))
        return rows

    def test_table_matches_readme_exactly(self):
        readme = self._readme_codes()
        mine = [(code, "红" if sev == "red" else "黄")
                for code, sev, _label, _domain, _gate in code_table.CODES]
        self.assertEqual(len(mine), len(set(c for c, _ in mine)),
                         "码表里有重名码")
        self.assertEqual(sorted(mine), sorted(readme),
                         "机读码表与 README 冻结码表不一致")
        self.assertGreater(len(mine), 0)

    def test_severity_distribution(self):
        counts = code_table.counts()
        self.assertEqual(counts["total"], len(code_table.CODES))
        self.assertEqual(counts["red"] + counts["yellow"], counts["total"])
        self.assertGreater(counts["red"], 0)
        self.assertGreater(counts["yellow"], 0)

    def test_every_code_has_chinese_label(self):
        for item in code_table.as_dicts():
            self.assertTrue(item["label"])
            self.assertIn(item["severity"], ("red", "yellow"))
            self.assertTrue(item["domain"])
            self.assertTrue(item["gate"])

    def test_codes_channel_matches_table(self):
        ctx = context_from_project("fixtures/legal-demo")
        contract = build_contract(ctx, channels=["codes"])
        self.assertEqual(contract["codes"]["total"], len(code_table.CODES))
        self.assertEqual(contract["codes"]["table_total"], len(code_table.CODES))
        self.assertEqual(len(contract["codes"]["items"]), len(code_table.CODES))


# ---------------------------------------------------------------------------
# 7. CLI 出口（JSON 是 stdout 唯一内容）
# ---------------------------------------------------------------------------

class TestCliApiExit(unittest.TestCase):
    """api 族：stdout 是纯 JSON；既有 11 条子命令不受影响。"""

    def _run(self, args, cwd=None):
        env = dict(os.environ)
        env["PYTHONPATH"] = PKG + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run([sys.executable, "-m", "factscribe_legal"] + args,
                              cwd=cwd, env=env, capture_output=True, text=True)

    def test_api_stdout_is_pure_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _fr_project(tmp)
            proc = self._run(["api", "codes", "--project", proj])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["version"], API_VERSION)
        self.assertIn("codes", payload)

    def test_api_missing_project_is_exit_2(self):
        proc = self._run(["api", "summary", "--project", "/nonexistent-dir"])
        self.assertEqual(proc.returncode, 2)

    def test_existing_subcommands_still_present(self):
        proc = self._run(["--help"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for name in ("fetch", "verify", "verify-cn", "verify-case", "verify-it",
                     "verify-es", "verify-fr-case", "verify-it-case",
                     "cn-lead-search", "cn-lead-verify", "cn-lead-get", "api"):
            self.assertIn(name, proc.stdout)


# ---------------------------------------------------------------------------
# 8. 时效口径说明：参考日定了，就别再写「参考日未定」
# ---------------------------------------------------------------------------

class TestTimelinessNote(unittest.TestCase):
    """note 里的口径说明必须与 reference_date 字段一致（不许自相矛盾）。

    件是按「参考日未定」先造一遍（状态 unknown），之后回填真实参考日重算；
    那句「参考日未定」的提示是**当时**的口径，参考日定了以后必须抹掉。
    """

    def test_hint_present_when_reference_date_missing(self):
        obj = tl.from_interval("fr", "法条", "L1", "2012-01-07", "2999-01-01", "",
                               "法国法条：版本区间完整。")
        self.assertEqual(obj["state"], "unknown")
        self.assertIn(tl.HINT, obj["note"])

    def test_strip_hint_removes_only_the_hint(self):
        self.assertEqual(tl.strip_hint("法国法条：版本区间完整。；" + tl.HINT),
                         "法国法条：版本区间完整。")
        self.assertEqual(tl.strip_hint("普通说明"), "普通说明")
        self.assertEqual(tl.strip_hint(tl.HINT), "")

    def test_contract_notes_have_no_stale_hint(self):
        ctx = context_from_project("fixtures/legal-demo")
        self.assertTrue(ctx.date, "夹具应带参考日")
        contract = build_contract(ctx, channels=["corpus", "timeliness"])
        for item in contract["corpus"]["items"]:
            self.assertNotIn(tl.HINT, item["timeliness"]["note"])
        for item in contract["timeliness"]["items"]:
            self.assertNotIn(tl.HINT, item["note"])
            self.assertEqual(item["reference_date"], ctx.date)


if __name__ == "__main__":
    unittest.main()
