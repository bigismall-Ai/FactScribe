#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法律侧工作台第 ② 步：读侧视图 ＋ 待批提案通道的自测。

钉住八件事：
  1. **七条线各自的页面数据出口**（findings ＋ receipts 都给得出，缺材料的
     标 skipped，不造假件）；
  2. 收据五元组：字段固定五元、缺省字段统一写「—」；
  3. 时效：四种来源在接口层归一成同一形状（11 键）；
  4. 语料过滤（国家／域／件型／时效状态）；
  5. 判定码表完整（码名、中文短名、红黄分级与机读副本一致）；
  6. 读侧视图四条：单件详情／文书分段／条→事实反查／CLI 清单；
  7. 待批提案：**只建单不写盘** ＋ before_sha 指纹闸拒写；
  8. 既有 11 条 CLI 的输出与退出码一字未动（快照对表）。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from factscribe_legal import code_table                       # noqa: E402
from factscribe_legal import proposals                        # noqa: E402
from factscribe_legal import receipts                          # noqa: E402
from factscribe_legal.api import (build_contract,              # noqa: E402
                                  build_view, context_from_project)

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "..")
CORPUS = os.path.join(PKG, "corpus")
RECEIPT_FIELDS = ("id", "sha16", "span", "face", "how")
TIMELINESS_FIELDS = ("domain", "kind", "item_id", "reference_date",
                     "state", "state_label", "effective_from",
                     "effective_to", "source", "source_fields", "note")
LINES = ("fr", "cn", "case", "it", "es", "fr-case", "it-case")


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
    """从正文里挑一个**原样出现**的数值 token（保证 span 定位得到）。"""
    import re
    for m in re.finditer(r"\d[\d.,]{%d,}" % (min_len - 1), text or ""):
        return m.group(0)
    return ""


def _cn_project(tmp):
    """中国法规项目：仓内 corpus/cn 的真卡（官方详情 JSON **无正文**）。"""
    proj = os.path.join(tmp, "cn-proj")
    shutil.copytree(os.path.join(CORPUS, "cn"), os.path.join(proj, "corpus-cn"))
    cards = sorted(os.listdir(os.path.join(proj, "corpus-cn", "cards")))
    card_rel = "corpus-cn/cards/%s" % cards[0]
    card = os.path.join(proj, card_rel)
    fields = {}
    for line in _read(card).splitlines():
        if ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    _write(os.path.join(proj, "facts", "41-cn.toml"),
           'schema = "paperkit-fact/3.0"\n\n[[fact]]\n'
           'id = "CN-API-1"\nclaim = "接口层测试事实"\n'
           'value = "%s"\nsource = "%s"\n'
           'source_sha256 = "sha256:%s"\n'
           'locator = "test"\nconfidence = "high"\nderived_from = []\n'
           % (fields.get("SXRQ", ""), card_rel, _sha_file(card)))
    return proj


def _fr_case_project(tmp):
    """法国判例项目：仓内真件（判决卡 ＋ 官方纯文本还原件）＋ 一条事实 ＋ 段落。"""
    proj = os.path.join(tmp, "proj")
    run = "run-20261116-inca"
    shutil.copytree(os.path.join(CORPUS, "fr-case", run),
                    os.path.join(proj, "runs", run))
    case_id = "JURITEXT000006953017"
    card_rel = "runs/%s/%s.fr-case.card.txt" % (run, case_id)
    card = os.path.join(proj, card_rel)
    official = os.path.join(proj, "runs", run, "official", case_id + ".txt")
    value = _literal_token(_read(official), 4) or "1900"
    _write(os.path.join(proj, "facts", "50-fr-case.toml"),
           'schema = "paperkit-fact/3.0"\n\n[[fact]]\n'
           'id = "FRCASE-1"\nclaim = "判例事实（工作台读侧视图测试）"\n'
           'value = "%s"\nsource = "%s"\n'
           'source_sha256 = "sha256:%s"\n'
           'locator = "test"\nconfidence = "high"\nderived_from = []\n'
           % (value, card_rel, _sha_file(card)))
    _write(os.path.join(proj, "sections", "01_case.tex"),
           "\\section{判例}\n判决要点 \\fact{FRCASE-1}{%s} 见于该案。\n"
           % value)
    _write(os.path.join(proj, "factscribe.toml"),
           '[project]\ntitle = "法律侧工作台读侧视图测试"\n'
           'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n\n'
           '[checks]\npackages = ["paper", "legal"]\n\n'
           '[checks.legal]\ncorpus = "corpus"\ndate = "2026-11-14"\n')
    shutil.copytree(CORPUS, os.path.join(proj, "corpus"))
    return proj, case_id, run


def _tree(root):
    """目录清单（相对路径 ＋ 大小）：用来证明「没写盘」。"""
    out = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root)
            try:
                out[rel] = os.path.getsize(path)
            except OSError:
                out[rel] = -1
    return out


class WorkbenchViewTest(unittest.TestCase):
    """读侧视图 ＋ 页面数据出口。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="legal-wb-")
        cls.proj, cls.case_id, cls.run_id = _fr_case_project(cls._tmp)
        cls.ctx = context_from_project(cls.proj)
        cls.contract = build_contract(cls.ctx)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    # -- 1. 七条线各自的页面数据出口 ------------------------------------
    def test_seven_lines_have_page_exports(self):
        findings = self.contract["findings"]["lines"]
        receipts = self.contract["receipts"]["lines"]
        self.assertEqual([ln["line"] for ln in findings], list(LINES))
        self.assertEqual([ln["line"] for ln in receipts], list(LINES))
        for ln in findings:
            self.assertIn(ln["status"], ("ran", "skipped", "na"))
            self.assertTrue(ln["label"])
            if ln["status"] == "skipped":
                self.assertTrue(ln["note"], "skipped 必须写清原因")
        for ln in receipts:
            self.assertTrue(ln["fields"] if "fields" in ln else True)

    def test_receipt_channel_has_five_fields_and_missing_marker(self):
        receipts = self.contract["receipts"]
        self.assertEqual(list(receipts["fields"]), list(RECEIPT_FIELDS))
        self.assertEqual(receipts["missing_marker"], "—")
        for ln in receipts["lines"]:
            for row in ln["items"]:
                for field in RECEIPT_FIELDS:
                    self.assertIn(field, row)
                    self.assertIsInstance(row[field], str)
                    self.assertTrue(row[field], "缺省也要写「—」不是空串")

    def test_cn_line_has_no_body_face(self):
        """CN 官方件无正文 ⇒ span/face 取缺省标记（不是新造的形状）。"""
        with tempfile.TemporaryDirectory() as tmp:
            proj = _cn_project(tmp)
            ctx = context_from_project(proj, corpus="corpus-cn",
                                       date="2026-11-14")
            contract = build_contract(ctx)
        cn = [ln for ln in contract["receipts"]["lines"]
              if ln["line"] == "cn"]
        self.assertTrue(cn and cn[0]["items"], "CN 线没有收据")
        for row in cn[0]["items"]:
            self.assertEqual(row["span"], receipts.MISSING)
            self.assertEqual(row["face"], receipts.MISSING)
            self.assertEqual(row["how"], "catalog")

    # -- 2. 时效四域归一 ------------------------------------------------
    def test_timeliness_is_eleven_keys_for_every_domain(self):
        items = self.contract["timeliness"]["items"]
        self.assertTrue(items)
        for item in items:
            self.assertEqual(tuple(item.keys()), TIMELINESS_FIELDS)
            self.assertIn(item["state"], self.contract["timeliness"]["states"])

    def test_timeliness_maps_four_domains(self):
        items = self.contract["timeliness"]["items"]
        by_domain = {}
        for item in items:
            by_domain.setdefault(item["domain"], []).append(item)
        for domain in ("fr", "cn", "it", "es", "fr-case"):
            if domain not in by_domain:
                continue
            item = by_domain[domain][0]
            self.assertEqual(item["source"],
                             {"fr": "区间", "cn": "状态标志", "it": "时点戳",
                              "es": "时点戳", "fr-case": "日期"}[domain])
            self.assertTrue(item["source_fields"])

    # -- 3. 语料过滤 ----------------------------------------------------
    def test_corpus_filters(self):
        items = self.contract["corpus"]["items"]
        self.assertTrue(items)
        for country in ("法国", "中国", "意大利", "西班牙"):
            kept = build_contract(self.ctx, channels=["corpus"],
                                  filters={"country": country})
            for item in kept["corpus"]["items"]:
                self.assertEqual(item["country"], country)
        only_fr = build_contract(self.ctx, channels=["corpus"],
                                 filters={"domain": "fr-case"})
        self.assertTrue(only_fr["corpus"]["items"])
        for item in only_fr["corpus"]["items"]:
            self.assertEqual(item["domain"], "fr-case")
        kinds = {item["kind"] for item in items}
        for kind in kinds:
            kept = build_contract(self.ctx, channels=["corpus"],
                                  filters={"kind": kind})
            for item in kept["corpus"]["items"]:
                self.assertEqual(item["kind"], kind)

    def test_corpus_items_are_real_files(self):
        """件清单里的 path 必须真实存在（不占位、不编造）。"""
        for item in self.contract["corpus"]["items"]:
            root = item.get("root") or ""
            path = os.path.join(root, item.get("path") or "")
            self.assertTrue(os.path.exists(path),
                            "件不在盘上：%s" % item.get("path"))

    # -- 4. 码表完整性 --------------------------------------------------
    def test_code_table_is_complete(self):
        codes = self.contract["codes"]
        self.assertEqual(codes["total"], code_table.counts()["total"])
        self.assertEqual(codes["red"], code_table.counts()["red"])
        self.assertEqual(codes["yellow"], code_table.counts()["yellow"])
        for item in codes["items"]:
            self.assertTrue(item["label"], "码 %s 缺中文短名" % item["code"])
            self.assertIn(item["severity"], ("red", "yellow"))
        names = [item["code"] for item in codes["items"]]
        self.assertEqual(len(names), len(set(names)))

    # -- 5. 读侧视图四条 ------------------------------------------------
    def test_item_detail_has_receipts_of_that_item(self):
        detail = build_view(self.ctx, "corpus_item", item_id=self.case_id)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["view"], "corpus_item")
        self.assertEqual(detail["item"]["id"], self.case_id)
        self.assertEqual(detail["item"]["domain"], "fr-case")
        self.assertTrue(detail["receipts"]["items"], "这件没有收据")
        for row in detail["receipts"]["items"]:
            for field in RECEIPT_FIELDS:
                self.assertIn(field, row)
            self.assertIn("fact", row)
        self.assertIn("timeliness", detail["item"])

    def test_item_detail_of_unknown_id_is_none(self):
        self.assertIsNone(build_view(self.ctx, "corpus_item",
                                     item_id="没有这件-000"))

    def test_document_segments_link_markers_to_receipts(self):
        doc = build_view(self.ctx, "document")
        self.assertEqual(doc["view"], "document")
        self.assertTrue(doc["paragraphs"])
        marked = [p for p in doc["paragraphs"] if p["markers"]]
        self.assertTrue(marked, "段落里没有引证标记")
        marker = marked[0]["markers"][0]
        self.assertEqual(marker["fact_id"], "FRCASE-1")
        self.assertTrue(marker["receipt"], "标记没有收据")
        self.assertTrue(marker["official"]["text"], "标记没有官方逐字片段")
        self.assertIn(marker["official"]["span"], marker["receipt"]["span"])

    def test_provision_facts_reverse_lookup(self):
        out = build_view(self.ctx, "provision_facts", num=self.case_id)
        self.assertEqual(out["view"], "provision_facts")
        self.assertEqual(out["total"], 1)
        row = out["items"][0]
        self.assertEqual(row["fact_id"], "FRCASE-1")
        self.assertTrue(row["receipt"])
        self.assertTrue(row["location"].startswith("facts/"))
        self.assertIsNotNone(row["corpus_item"])
        self.assertIsNotNone(row["timeliness"])

    def test_cli_manifest_lists_every_subcommand(self):
        out = build_view(self.ctx, "cli")
        self.assertEqual(out["view"], "cli")
        names = [item["name"] for item in out["items"]]
        for name in ("fetch", "verify", "verify-cn", "verify-case", "verify-it",
                     "verify-es", "verify-fr-case", "verify-it-case",
                     "cn-lead-search", "cn-lead-verify", "cn-lead-get", "api"):
            self.assertIn(name, names)
        for item in out["items"]:
            self.assertTrue(item["group"])
            self.assertTrue(item["help"])


class ProposalTest(unittest.TestCase):
    """待批提案：只建单不写盘 ＋ before_sha 指纹闸拒写。"""

    def setUp(self):
        proposals.clear()
        self._tmp = tempfile.mkdtemp(prefix="legal-prop-")
        self.proj, self.case_id, self.run_id = _fr_case_project(self._tmp)
        self.ctx = context_from_project(self.proj)

    def tearDown(self):
        proposals.clear()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _target(self):
        return {"scope": "receipt", "fact_id": "FRCASE-1",
                "item_id": self.case_id}

    def test_create_is_only_a_sheet_and_writes_no_file(self):
        before = _tree(self.proj)
        record = proposals.create("receipt_quote", self._target(),
                                  {"note": "想复核这个值"}, "",
                                  {"source": "测试", "current": "abc123"})
        self.assertTrue(record["id"].startswith("P-"))
        self.assertEqual(record["status"], "proposed")
        self.assertEqual(record["before_sha"], "abc123")
        self.assertFalse(record["decision"]["write_path"])
        self.assertEqual(_tree(self.proj), before, "建单不许写盘")

    def test_adopt_passes_gate_when_fingerprint_matches(self):
        record = proposals.create("receipt_quote", self._target(), {}, "",
                                  {"source": "测试", "current": "abc123"})
        adopted = proposals.adopt(record["id"],
                                  {"source": "测试", "current": "abc123"})
        self.assertEqual(adopted["status"], "adopted_pending")
        self.assertFalse(adopted["decision"]["write_path"])
        self.assertIn("第 ③ 步", adopted["decision"]["reason"])

    def test_adopt_is_refused_when_fingerprint_changed(self):
        record = proposals.create("receipt_quote", self._target(), {}, "",
                                  {"source": "测试", "current": "abc123"})
        with self.assertRaises(proposals.ProposalError) as ctx:
            proposals.adopt(record["id"],
                           {"source": "测试", "current": "deadbeef"})
        self.assertEqual(ctx.exception.code, "PROPOSAL_STALE")
        self.assertEqual(proposals.get(record["id"])["status"], "rejected")

    def test_stale_fingerprint_is_refused_at_creation(self):
        with self.assertRaises(proposals.ProposalError) as ctx:
            proposals.create("receipt_quote", self._target(), {}, "wrong-sha",
                             {"source": "测试", "current": "abc123"})
        self.assertEqual(ctx.exception.code, "PROPOSAL_STALE")
        self.assertEqual(proposals.list_all(), [])

    def test_real_fingerprint_changes_when_target_changes(self):
        """真口径：事实账钉的哈希被改 ⇒ 指纹变了 ⇒ 采纳被拒。"""
        from factscribe_legal.api import create_proposal
        record = create_proposal(self.ctx, "receipt_quote",
                                 self._target(), {}, "")
        self.assertTrue(record["before_sha"])
        fact = os.path.join(self.proj, "facts", "50-fr-case.toml")
        text = _read(fact).replace(record["before_sha"], "0" * 16)
        _write(fact, text)
        from factscribe_legal.api import adopt_proposal
        with self.assertRaises(proposals.ProposalError) as ctx:
            adopt_proposal(self.ctx, record["id"])
        self.assertEqual(ctx.exception.code, "PROPOSAL_STALE")

    def test_channel_shows_the_sheets(self):
        contract = build_contract(self.ctx, channels=["proposals"])
        self.assertEqual(contract["proposals"]["total"], 0)
        proposals.create("receipt_quote", self._target(), {}, "", None)
        contract = build_contract(self.ctx, channels=["proposals"])
        self.assertEqual(contract["proposals"]["total"], 1)
        self.assertIn("第 ② 步", contract["proposals"]["note"])


class ExistingCliUnchangedTest(unittest.TestCase):
    """既有 11 条 CLI：输出与退出码一字未动（快照对表）。"""

    def test_eleven_subcommands_match_the_baseline(self):
        sys.path.insert(0, HERE)
        import _cli_snapshot
        with open(_cli_snapshot.BASELINE, encoding="utf-8") as fh:
            base = json.load(fh)
        current = _cli_snapshot.collect()
        self.assertEqual(len(current), 11)
        for old, new in zip(base["cases"], current):
            with self.subTest(cmd=old["name"]):
                self.assertEqual(new["exit"], old["exit"], "退出码变了")
                self.assertEqual(new["stdout"], old["stdout"], "输出变了")
                self.assertEqual(new["stderr"], old["stderr"])
                self.assertEqual(new["help"], old["help"], "命令面变了")


if __name__ == "__main__":
    unittest.main()
