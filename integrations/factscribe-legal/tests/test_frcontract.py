#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判例事实账引文契约（P-166 收编）的自测：标准库 unittest，网络零依赖。

四块：
  1. **value 逐字契约**（FR_CASE_VALUE_NOT_QUOTE，红）：案号形/过短 ⇒ 红；
     数字/日期型 value 走 numnorm 对账，不受契约约束。
  2. **拼接/截断**（FR_CASE_STITCH_UNMARKED，红）：无标记且两面皆不连续命中 ⇒ 红；
     带标记拼接逐片段分类——片段缺失红、全正文绿、含仅摘要段片段走面声明。
  3. **分面 quote_face**（FR_CASE_QUOTE_FACE_UNDECLARED，黄）：仅摘要段命中且
     未声明面 ⇒ 黄；claim/note 字样或 quote_face 字段声明 ⇒ 绿；
     旁车 faces.json 优先（钉 txt 哈希），坏旁车回落 XML 现算。
  4. **收据式三区报告**：✅ 收据闭环（每条事实一行）→ ⚠️ 黄码区 → 🔴 红码区
     → 尾部固定边界声明；退出码语义不变（红 1 > 黄 3 > 绿 0）。
  另钉还原契约：br_aware_text 的 `<p>` 递归取文不得改变 INCA 语料的
  to_plain 输出（official/*.txt 字节稳定＝哈希对账的地基）。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import json
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from factscribe_legal.fr_case_reader import (build_card,  # noqa: E402
                                             faces_sidecar_json,
                                             parse_meta, read_faces_sidecar,
                                             sha256_bytes, to_plain,
                                             to_plain_faces)
from factscribe_legal.fr_case_verify import (render_fr_case,  # noqa: E402
                                             verify_fr_case)

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_DIR = os.path.join(HERE, "..", "corpus", "fr-case")
RUN_NAME = "run-20261116-inca"
BOUNDARY = ("边界声明：本闸只核验引用真实、在库、逐字、面内、账据一致；"
            "法律判断正确性不在核验范围。")

# 合成判决的正文段（判例域逐字引文/拼接测试的底料；含一个法式数字锚点）
BODY_PARAS = [
    "LA COUR DE CASSATION, CHAMBRE SOCIALE, a rendu l'arrêt suivant :",
    "Sur le premier moyen, pris en sa première branche : il est fait grief "
    "à l'arrêt attaqué d'avoir décidé que l'indemnité de fin de contrat "
    "était due au salarié malgré la requalification opérée.",
    "Attendu que selon l'article L. 1243-8 du code du travail, le salarié a "
    "droit à une indemnité de fin de contrat lorsque la relation "
    "contractuelle se poursuit en contrat à durée indéterminée.",
    "Mais attendu que la cour d'appel, statuant souverainement, a exactement "
    "décidé que le contrat comportait la définition précise de son motif et "
    "que le salarié avait droit à l'indemnité de précarité ;",
    "L'indemnité est égale à 3 500 euros selon la convention collective "
    "applicable en l'espèce.",
    "Par ces motifs, rejette le pourvoi.",
]
# 合成判决的摘要段（SOMMAIRE/ANA）——不在正文里，是面界测试的关键底料
SOMMAIRE_TXT = ("ANA : requalification du contrat à durée déterminée en contrat "
                "à durée indéterminée et indemnité de fin de contrat due au "
                "salarié dont le contrat était dépourvu de motif précis.")
CASE_ID = "JURITEXT000000000001"
RUN_SYNTH = "run-synth"


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _sha_file(path):
    with open(path, "rb") as fh:
        return sha256_bytes(fh.read())


def synth_judgment_xml(body_paras=None, sommaire=SOMMAIRE_TXT,
                       cid=CASE_ID, case_no="01-16.595",
                       date="2004-09-29"):
    """合成一份 DILA 形状的判决 XML（CONTENU 内包 <p>——fr-cass 全量件形状）。"""
    paras = BODY_PARAS if body_paras is None else body_paras
    root = ET.Element("TEXTE_JURI_JUDI")
    meta = ET.SubElement(root, "META")
    mc = ET.SubElement(meta, "META_COMMUN")
    ET.SubElement(mc, "ID").text = cid
    ET.SubElement(mc, "ORIGINE").text = "JURI"
    ET.SubElement(mc, "NATURE").text = "ARRET"
    ms = ET.SubElement(meta, "META_SPEC")
    mj = ET.SubElement(ms, "META_JURI")
    ET.SubElement(mj, "TITRE").text = (
        "Cour de cassation, chambre sociale, 29 septembre 2004, %s" % case_no)
    ET.SubElement(mj, "DATE_DEC").text = date
    ET.SubElement(mj, "JURIDICTION").text = "Cour de cassation"
    ET.SubElement(mj, "NUMERO").text = "50001001"
    ET.SubElement(mj, "SOLUTION").text = "Rejet"
    mjj = ET.SubElement(ms, "META_JURI_JUDI")
    nas = ET.SubElement(mjj, "NUMEROS_AFFAIRES")
    ET.SubElement(nas, "NUMERO_AFFAIRE").text = case_no.replace(".", "")
    ET.SubElement(mjj, "FORMATION").text = "CHAMBRE_SOCIALE"
    texte = ET.SubElement(root, "TEXTE")
    bloc = ET.SubElement(texte, "BLOC_TEXTUEL")
    contenu = ET.SubElement(bloc, "CONTENU")
    for p in paras:
        ET.SubElement(contenu, "p").text = p
    if sommaire:
        ET.SubElement(texte, "SOMMAIRE").text = sommaire
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def fact_block(d):
    """dict → TOML [[fact]] 块（json 转义＝TOML 基本串转义的常用子集）。"""
    lines = ["[[fact]]"]
    for k, v in d.items():
        lines.append("%s = %s" % (k, json.dumps(v, ensure_ascii=False)))
    lines.append("")
    return "\n".join(lines)


def make_synth_project(tmp, facts, body_paras=None, sommaire=SOMMAIRE_TXT,
                       cid=CASE_ID, run=RUN_SYNTH):
    """合成判决 → 官方件三件套＋事实账（闸吃的完整临时项目）。

    facts：list of dict（id/claim/value/...）；source 与 source_sha256 由本函数
    统一填好（指向合成卡并钉哈希），调用方只给业务字段。
    """
    xml_bytes = synth_judgment_xml(body_paras=body_paras, sommaire=sommaire,
                                   cid=cid)
    text, _faces = to_plain_faces(xml_bytes)
    txt_bytes = text.encode("utf-8")
    prun = os.path.join(tmp, "runs", run)
    _write(os.path.join(prun, "official", "%s.xml" % cid),
           xml_bytes.decode("utf-8"))
    _write(os.path.join(prun, "official", "%s.txt" % cid), text)
    meta = parse_meta(xml_bytes)
    card = build_card(meta, text, xml_bytes, txt_bytes)
    card_rel = "runs/%s/%s.fr-case.card.txt" % (run, cid)
    _write(os.path.join(tmp, card_rel), card)
    blocks = ['schema = "paperkit-fact/3.0"', ""]
    for d in facts:
        d = dict(d)
        d.setdefault("source", card_rel)
        d.setdefault("source_sha256", "sha256:" + sha256_bytes(card.encode("utf-8")))
        d.setdefault("confidence", "high")
        d.setdefault("derived_from", [])
        blocks.append(fact_block(d))
    _write(os.path.join(tmp, "facts", "50-fr-case.toml"), "\n".join(blocks))
    return tmp


def run_gate(proj):
    findings, stats = verify_fr_case(proj)
    text, code = render_fr_case(findings, stats)
    return findings, stats, text, code


def codes_of(proj):
    findings, _stats, _text, _code = run_gate(proj)
    return [f.code for f in findings]


def _body_chunks():
    """两段取自不同正文段的连续片段（拼接测试底料：各自真实、相连即假）。"""
    return BODY_PARAS[1][30:150], BODY_PARAS[3][30:150]


class TestValueQuoteContract(unittest.TestCase):
    """① value 逐字契约：案号形/过短 ⇒ 红；数字/日期型照走 numnorm。"""

    def test_case_no_shape_value_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "案号当引文", "value": "01-16.595"}])
            self.assertIn("FR_CASE_VALUE_NOT_QUOTE", codes_of(proj))
            _f, _s, _text, code = run_gate(proj)
            self.assertEqual(code, 1)

    def test_case_no_without_dot_is_red_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "案号当引文", "value": "01-16595"}])
            self.assertIn("FR_CASE_VALUE_NOT_QUOTE", codes_of(proj))

    def test_short_value_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "短语当引文", "value": "Rejet du pourvoi"}])
            self.assertIn("FR_CASE_VALUE_NOT_QUOTE", codes_of(proj))

    def test_numeric_value_goes_numnorm_not_contract(self):
        """数字锚点（3 500 → 3500）是既有闸合法值型，不触发逐字契约。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "金额（数字锚点）", "value": "3500"}])
            self.assertEqual([c for c in codes_of(proj)
                              if c.startswith("FR_CASE_VALUE")], [])
            findings, stats, _text, code = run_gate(proj)
            self.assertEqual(code, 0)
            self.assertEqual(stats["receipts"][0]["how"], "numnorm")
            self.assertEqual(stats["receipts"][0]["face"], "—")

    def test_date_value_goes_numnorm_not_contract(self):
        """日期（ISO↔法文月名双向）是既有闸合法值型，不受长度约束。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "裁判日期", "value": "29 septembre 2004"}])
            self.assertEqual(codes_of(proj), [])
            _f, stats, _t, _c = run_gate(proj)
            self.assertEqual(stats["receipts"][0]["how"], "numnorm")

    def test_long_quote_from_body_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "正文逐字引文", "value": BODY_PARAS[2]}])
            self.assertEqual(codes_of(proj), [])
            _f, stats, _t, _c = run_gate(proj)
            self.assertEqual(stats["receipts"][0]["face"], "body")
            self.assertEqual(stats["receipts"][0]["how"], "contains")
            self.assertNotEqual(stats["receipts"][0]["span"], "—")
            self.assertRegex(stats["receipts"][0]["span"], r"^\d+-\d+$")


class TestStitch(unittest.TestCase):
    """② 拼接/截断：无标记两面皆不连续命中 ⇒ 红；带标记逐片段分类。"""

    def test_unmarked_stitch_is_red(self):
        """两段真引文无标记直接连读＝拼接 ⇒ 红（本码专抓；伪造由既有闸另判）。"""
        a, b = _body_chunks()
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "拼接引文", "value": a + " " + b}])
            codes = codes_of(proj)
            self.assertIn("FR_CASE_STITCH_UNMARKED", codes)
            self.assertNotIn("FR_CASE_VALUE_NOT_QUOTE", codes)

    def test_marked_stitch_with_missing_fragment_is_red(self):
        a, _b = _body_chunks()
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "半真半假拼接",
                 "value": a + " […] ce fragment n'existe nulle part ZZZ"}])
            self.assertIn("FR_CASE_STITCH_UNMARKED", codes_of(proj))

    def test_marked_stitch_all_body_fragments_is_green(self):
        a, b = _body_chunks()
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "标记拼接（全正文）",
                 "value": a + " […] " + b}])
            self.assertEqual(codes_of(proj), [])
            _f, stats, _t, _c = run_gate(proj)
            self.assertEqual(stats["receipts"][0]["face"], "body")


class TestQuoteFace(unittest.TestCase):
    """③ 分面 quote_face：摘要段引文未声明面 ⇒ 黄；声明 ⇒ 绿（按全文对账）。"""

    def test_resume_quote_undeclared_is_yellow_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "Cass. soc., 29 septembre 2004",
                 "value": SOMMAIRE_TXT}])
            codes = codes_of(proj)
            self.assertIn("FR_CASE_QUOTE_FACE_UNDECLARED", codes)
            self.assertNotIn("FR_CASE_STITCH_UNMARKED", codes)
            self.assertNotIn("FR_CASE_VALUE_NOT_IN_OFFICIAL", codes)
            _f, _s, _text, code = run_gate(proj)
            self.assertEqual(code, 3)

    def test_resume_quote_declared_via_claim_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "官方摘要 (résumé) : requalification",
                 "value": SOMMAIRE_TXT}])
            self.assertEqual(codes_of(proj), [])
            _f, stats, _t, _c = run_gate(proj)
            self.assertEqual(stats["receipts"][0]["face"], "résumé")

    def test_resume_quote_declared_via_note_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "Cass. soc., 29 septembre 2004",
                 "note": "citation du sommaire officiel",
                 "value": SOMMAIRE_TXT}])
            self.assertEqual(codes_of(proj), [])

    def test_resume_quote_declared_via_quote_face_field_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "Cass. soc., 29 septembre 2004",
                 "quote_face": "résumé", "value": SOMMAIRE_TXT}])
            self.assertEqual(codes_of(proj), [])

    def test_quote_face_body_field_does_not_excuse_resume_quote(self):
        """quote_face="body" 不是摘要段声明——声称正文却引在摘要段照旧报黄。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "Cass. soc., 29 septembre 2004",
                 "quote_face": "body", "value": SOMMAIRE_TXT}])
            self.assertIn("FR_CASE_QUOTE_FACE_UNDECLARED", codes_of(proj))

    def test_marked_body_plus_resume_undeclared_yellow_declared_green(self):
        a, _b = _body_chunks()
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "混合拼接未声明",
                 "value": a + " […] " + SOMMAIRE_TXT}])
            self.assertIn("FR_CASE_QUOTE_FACE_UNDECLARED", codes_of(proj))
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "混合拼接（正文＋摘要，已声明面）",
                 "value": a + " […] " + SOMMAIRE_TXT}])
            # 同一 claim 不含面字样——用 note 声明
            proj2 = make_synth_project(tmp, [
                {"id": "S1", "claim": "混合拼接（正文＋摘要）",
                 "note": "second fragment résumé",
                 "value": a + " […] " + SOMMAIRE_TXT}])
            self.assertEqual(codes_of(proj2), [])


class TestFacesSidecar(unittest.TestCase):
    """旁车 official/<ID>.faces.json：钉 txt 哈希、优先生效；坏旁车回落现算。"""

    def test_sidecar_roundtrip(self):
        xml_bytes = synth_judgment_xml()
        text, faces = to_plain_faces(xml_bytes)
        payload = faces_sidecar_json(xml_bytes, sha256_bytes(text.encode("utf-8")))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.faces.json")
            _write(path, payload)
            self.assertEqual(read_faces_sidecar(path, text), faces)

    def test_sidecar_overrides_xml_compute(self):
        """旁车把全文标成正文 ⇒ 摘要段引文按 body 放行（旁车优先于现算）。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "Cass. soc., 29 septembre 2004",
                 "value": SOMMAIRE_TXT}])
            txt_path = os.path.join(proj, "runs", RUN_SYNTH, "official",
                                    CASE_ID + ".txt")
            txt = _read(txt_path)
            payload = json.dumps({
                "version": 1, "body": [[0, len(txt)]],
                "text_chars": len(txt),
                "txt_sha256": sha256_bytes(txt.encode("utf-8")),
            }, ensure_ascii=False)
            _write(os.path.join(proj, "runs", RUN_SYNTH, "official",
                                CASE_ID + ".faces.json"), payload)
            self.assertEqual(codes_of(proj), [])

    def test_sidecar_with_wrong_hash_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "Cass. soc., 29 septembre 2004",
                 "value": SOMMAIRE_TXT}])
            payload = json.dumps({"version": 1, "body": [[0, 99999]],
                                  "text_chars": 99999,
                                  "txt_sha256": "0" * 64})
            _write(os.path.join(proj, "runs", RUN_SYNTH, "official",
                                CASE_ID + ".faces.json"), payload)
            self.assertIn("FR_CASE_QUOTE_FACE_UNDECLARED", codes_of(proj))

    def test_corrupt_sidecar_json_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "Cass. soc., 29 septembre 2004",
                 "value": SOMMAIRE_TXT}])
            _write(os.path.join(proj, "runs", RUN_SYNTH, "official",
                                CASE_ID + ".faces.json"), "{not json")
            self.assertIn("FR_CASE_QUOTE_FACE_UNDECLARED", codes_of(proj))


class TestReceiptRender(unittest.TestCase):
    """④ 收据式三区报告：收据闭环 → 黄码区 → 红码区 → 边界声明；退出码不变。"""

    def test_green_report_has_all_zones_and_boundary_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "S1", "claim": "正文引文", "value": BODY_PARAS[2]},
                {"id": "S2", "claim": "金额", "value": "3500"}])
            findings, stats, text, code = run_gate(proj)
            self.assertEqual(code, 0)
            self.assertEqual(len(stats["receipts"]), 2)
            self.assertIn("✅ 收据闭环", text)
            self.assertIn("⚠️ 黄码区：0 条", text)
            self.assertIn("🔴 红码区：0 条", text)
            self.assertIn("S1｜%s｜" % stats["receipts"][0]["sha16"], text)
            self.assertIn(BOUNDARY, text)
            self.assertTrue(text.strip().endswith(BOUNDARY))

    def test_mixed_report_zones_and_exit_code(self):
        a, _b = _body_chunks()
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_synth_project(tmp, [
                {"id": "OK1", "claim": "正文引文", "value": BODY_PARAS[2]},
                {"id": "RED1", "claim": "案号当引文", "value": "01-16.595"},
                {"id": "YEL1", "claim": "Cass. soc., 29 septembre 2004",
                 "value": SOMMAIRE_TXT},
                {"id": "RED2", "claim": "拼接", "value": a + " " + BODY_PARAS[2]},
            ])
            findings, stats, text, code = run_gate(proj)
            self.assertEqual(code, 1)
            self.assertEqual(len(stats["receipts"]), 4)
            self.assertIn("⚠️ 黄码区：1 条", text)
            # RED2（无标记拼接）双红并存：STITCH_UNMARKED＋既有 NOT_IN_OFFICIAL
            self.assertIn("🔴 红码区：3 条（必须修）", text)
            self.assertIn("FR_CASE_VALUE_NOT_QUOTE", text)
            self.assertIn("FR_CASE_STITCH_UNMARKED", text)
            self.assertIn("FR_CASE_QUOTE_FACE_UNDECLARED", text)
            self.assertIn("FR_CASE_VALUE_NOT_IN_OFFICIAL", text)
            # 红码区每条带原因（→ 行）
            self.assertIn("→", text)
            self.assertTrue(text.strip().endswith(BOUNDARY))

    def test_render_without_stats_still_three_zones(self):
        text, code = render_fr_case([])
        self.assertEqual(code, 0)
        self.assertIn("✅ 收据闭环", text)
        self.assertIn(BOUNDARY, text)


class TestRestorePins(unittest.TestCase):
    """还原契约钉版：<p> 递归不得改变 INCA 语料输出（official txt 字节稳定）。"""

    def test_to_plain_still_matches_repo_corpus_txt(self):
        """INCA 四件：to_plain(xml) 与仓内 official txt 逐字节一致（钉死）。"""
        with open(os.path.join(CORPUS_DIR, RUN_NAME, "index.json"),
                  encoding="utf-8") as fh:
            index = json.load(fh)
        for cid, meta in sorted(index["cases"].items()):
            with open(os.path.join(CORPUS_DIR, RUN_NAME, meta["xml_file"]),
                      "rb") as fh:
                raw = fh.read()
            txt = _read(os.path.join(CORPUS_DIR, RUN_NAME, meta["txt_file"]))
            self.assertEqual(to_plain(raw), txt, cid)

    def test_to_plain_faces_matches_repo_corpus_txt(self):
        """to_plain_faces 的文本面与 to_plain 逐字节一致，且区间落在 txt 内。

        INCA 语料含 TGI 判决（正文不含「LA COUR」），正文断言只做通用形状：
        正文非空，且摘要段（[SOMMAIRE] 行有内容者）不落在正文区间里。
        """
        with open(os.path.join(CORPUS_DIR, RUN_NAME, "index.json"),
                  encoding="utf-8") as fh:
            index = json.load(fh)
        for cid, meta in sorted(index["cases"].items()):
            with open(os.path.join(CORPUS_DIR, RUN_NAME, meta["xml_file"]),
                      "rb") as fh:
                raw = fh.read()
            txt = _read(os.path.join(CORPUS_DIR, RUN_NAME, meta["txt_file"]))
            text, faces = to_plain_faces(raw)
            self.assertEqual(text, txt, cid)
            self.assertTrue(faces, cid + " 应有正文区间")
            for s, e in faces:
                self.assertTrue(0 <= s < e <= len(txt), cid)
            body = "\n".join(txt[s:e] for s, e in faces)
            self.assertGreater(len(body), 100, cid)
            for line in txt.splitlines():
                if line.startswith("[SOMMAIRE]") and line[len("[SOMMAIRE]"):].strip():
                    self.assertNotIn(line[len("[SOMMAIRE] "):].strip(), body,
                                     cid + " 摘要段不得落进正文区间")

    def test_p_paragraph_recursion_and_body_ranges(self):
        """fr-cass 形状（CONTENU 内包 <p>）：段落文本必须取全，区间罩住正文。"""
        xml_bytes = synth_judgment_xml()
        text, faces = to_plain_faces(xml_bytes)
        self.assertEqual(len(faces), 1)
        s, e = faces[0]
        self.assertEqual(text[s:e], "\n".join(BODY_PARAS))
        self.assertIn("[CONTENU]", text)
        self.assertIn("[SOMMAIRE] " + SOMMAIRE_TXT, text)
        self.assertGreater(text.index("[SOMMAIRE]"), e)
        # 正文区间外＝摘要段（面界的机械含义）
        self.assertNotIn(SOMMAIRE_TXT, text[s:e])


class TestRealCorpusStillGreen(unittest.TestCase):
    """真件复跑（INCA）：新契约不得把既有绿卷打红（数字锚点值型豁免）。"""

    def test_numeric_fact_values_stay_green(self):
        with open(os.path.join(CORPUS_DIR, RUN_NAME, "index.json"),
                  encoding="utf-8") as fh:
            index = json.load(fh)
        cases = index["cases"]
        values = {
            "JURITEXT000006953017": "1166",
            "JURITEXT000007100000": "499",
            "JURITEXT000007471838": "3500",
            "JURITEXT000006951547": "300000",
        }
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, "proj")
            prun = os.path.join(proj, "runs", RUN_NAME)
            os.makedirs(os.path.join(prun, "official"), exist_ok=True)
            os.makedirs(os.path.join(proj, "facts"), exist_ok=True)
            src = os.path.join(CORPUS_DIR, RUN_NAME)
            blocks = ['schema = "paperkit-fact/3.0"', ""]
            for cid in sorted(cases):
                meta = cases[cid]
                for key in ("xml_file", "txt_file", "card_file"):
                    _write(os.path.join(prun, meta[key]),
                           _read(os.path.join(src, meta[key])))
                card_rel = "runs/%s/%s" % (RUN_NAME, meta["card_file"])
                blocks.append(fact_block({
                    "id": "F-%s" % cid,
                    "claim": "判决正文数值（官方件引用示例）",
                    "value": values[cid],
                    "source": card_rel,
                    "source_sha256": "sha256:" + _sha_file(os.path.join(proj, card_rel)),
                }))
            _write(os.path.join(proj, "facts", "50-fr-case.toml"),
                   "\n".join(blocks))
            findings, _stats, text, code = run_gate(proj)
            self.assertEqual([f.code for f in findings], [],
                             str([f.code for f in findings]))
            self.assertEqual(code, 0)
            self.assertEqual(len(_stats["receipts"]), 4)
            for r in _stats["receipts"]:
                self.assertEqual(r["how"], "numnorm")


if __name__ == "__main__":
    unittest.main()
