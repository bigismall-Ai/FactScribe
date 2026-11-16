# -*- coding: utf-8 -*-
r"""legal 核验包（M2）：发现注册＋卡形状＋fail-closed＋槽内行为。

规范：docs/design/SPEC-CHECKS.md §3（包契约）、§5（配置）、§7 M2。
适配器居 integrations/factscribe-legal/factscribe_legal/checks_adapter.py，
core 只按 check-package.toml 的声明发现载入（core 不 import integrations）。

覆盖：

* 发现注册：load_integration 幂等、卡形状（config_keys＝{corpus,date,view}）、
  解析点名即注册、无主 id 仍 exit 2；
* fail-closed：corpus 未声明／目录缺／index.json 缺 ⇒ 黄 LEGAL_COVERAGE_GAP
  且不许全绿；date 缺/非法 ⇒ 红 LEGAL_DATE_INVALID；有事项而材料缺 ⇒ 黄亮出；
* 域内正判：合成语料上合法引用零发现、引用缺语料法条 ⇒ LEGAL_PROV_UNKNOWN；
* 槽内行为：summary 挂在 summary["legal"]、by_domain 归属、退出码走
  aggregate_exit 单一入口；
* ES 独立桶（2026-11-16 批，TestESBucket）：gates 行五桶并列
  fr｜cn｜case｜it｜es；ES 事项（.es.card.txt 卡＋art-es- 引用）归 es 桶、
  不再被 PROV_RE／art- 兜底误并进 fr 桶（反例回归钉）；缺 es/ 语料
  fail-closed 黄 LEGAL_COVERAGE_GAP；ES 判定走 ES_ 码表独立分节；
* 冻结锁：audit/evidence-legal.lock 与 paper 的 audit/evidence.lock 互不干扰
  （在 TestLegalEvidenceLock）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGAL = ROOT / "integrations" / "factscribe-legal"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(LEGAL))

from factscribe import checks  # noqa: E402
from factscribe.config import Config, ConfigError, load_config  # noqa: E402
from factscribe.config import load_facts, load_sections  # noqa: E402

XML_TEXT = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ARTICLE>\n"
            "  <BLOC_TEXTUEL><CONTENU>\n"
            "    <p>Toute duree hebdomadaire de travail ne peut depasser "
            "35 heures.</p>\n"
            "  </CONTENU></BLOC_TEXTUEL>\n"
            "</ARTICLE>\n")

INDEX = {
    "pool_asof": "2026-11-14",
    "provisions": {
        "L3121-27": {
            "legiarti": "LEGIARTI000006331684",
            "code_id": "LEGITEXT000006072050",
            "etat": "VIGUEUR",
            "date_debut": "2008-05-01",
            "date_fin": "",
            "xml_file": "L3121-27.xml",
        },
    },
}

FACTS_TOML = ('[[fact]]\n'
              'id = "FR-HOURS"\n'
              'claim = "法国标准周工时"\n'
              'value = "35"\n'
              'source = "results/corpus-legal/L3121-27.xml"\n'
              'source_sha256 = "sha256:%s"\n')

SECTION_TEX = ("\\section{Demo}\n"
               "法国每周工时 \\fact{FR-HOURS}{35} 小时。\n"
               "引用 \\cite{key1}。\n")

BIB = ("@article{key1,\n  title = {T},\n  author = {A},\n  year = {2024},\n"
       "  doi = {10.1234/abc}\n}\n")

PROJECT_TOML = """[project]
title = "legal 槽测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"

[checks]
packages = ["paper", "legal"]

[checks.legal]
corpus = "results/corpus-legal"
date = "2026-11-14"
"""


def build_legal_project(base: Path, extra_toml: str = "") -> Path:
    """最小双域项目：合成语料＋事实账＋正文。

    语料放 results/ 下（paper 的 source 必须在 results/ 或 source_root 内；
    两层证据共用同一份字节：paper 钉卡/文件哈希，legal 钉官方字节哈希）。
    paper 域预期一黄 NO_MANIFEST（合成项目没有人签清单）。
    extra_toml 追加键**不带表头**：模板末表是 [checks.legal]，裸键落该表——
    重复 [checks.legal] 表头是非法 TOML（3.11+ tomllib 严判重表，3.10 旧兜底
    解析器宽容会掩盖）。
    """
    root = Path(base)
    for d in ("sections", "facts", "results/corpus-legal"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "results/corpus-legal" / "L3121-27.xml").write_text(
        XML_TEXT, encoding="utf-8")
    (root / "results/corpus-legal" / "index.json").write_text(
        json.dumps(INDEX, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    sha = hashlib.sha256(
        (root / "results/corpus-legal" / "L3121-27.xml").read_bytes()).hexdigest()
    (root / "facts" / "one.toml").write_text(FACTS_TOML % sha,
                                             encoding="utf-8")
    (root / "sections" / "01_one.tex").write_text(SECTION_TEX, encoding="utf-8")
    (root / "refs.bib").write_text(BIB, encoding="utf-8")
    (root / "factscribe.toml").write_text(PROJECT_TOML + extra_toml,
                                          encoding="utf-8")
    return root


def legal_of(payload: dict, sev: str) -> list[dict]:
    return [f for f in payload.get(sev, [])
            if f.get("domain") == "legal"]


def codes_of(items: list[dict]) -> list[str]:
    return [i["code"] for i in items]


# --------------------------------------------------------------------------
# ES 离线合成样例（照 legal-demo／verify-es 形状：<corpus>/es/ 一目录一法，
# 形状同 integrations/factscribe-legal/tests/test_spain.py 的迷你 BOE 语料；
# 哈希全部现算，离线确定性）。
# --------------------------------------------------------------------------

ES_BOE_XML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<response><status><code>200</code><text>ok</text></status><data>\n'
    '<metadatos><identificador>BOE-A-2015-10565</identificador>'
    '<titulo>Ley 39/2015</titulo>'
    '<fecha_actualizacion>20261116T084356Z</fecha_actualizacion></metadatos>\n'
    '<texto>\n'
    '<bloque id="a2" tipo="precepto" titulo="Articulo 2">\n'
    '<version id_norma="BOE-A-2015-10565" fecha_publicacion="20151002" '
    'fecha_vigencia="20151003">\n'
    '<p class="articulo">Articulo 2. Ambito de aplicacion.</p>\n'
    '<p class="parrafo">2. El plazo maximo para dictar resolucion es de '
    '3 meses.</p>\n'
    '</version>\n'
    '</bloque>\n'
    '</texto>\n'
    '</data></response>\n'
).encode("utf-8")

ES_ACT_ID = "BOE-A-2015-10565"
ES_CARD_REL = "results/corpus-legal/es/a2.es.card.txt"


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build_es_view(root: Path, corpus_rel: str = "results/corpus-legal",
                  fetch_reference_date: str = "2026-11-14") -> Path:
    """给项目装上 ES 语料视图（<corpus>/es/：index.json＋官方整件＋切片＋卡）。"""
    es = root / corpus_rel / "es"
    off = es / "official"
    off.mkdir(parents=True, exist_ok=True)
    (off / "act.xml").write_bytes(ES_BOE_XML)
    blob = re.search(rb'<bloque id="a2"[^>]*>.*?</bloque>',
                     ES_BOE_XML, re.S).group(0)
    (off / "a2.xml").write_bytes(blob)
    text = re.sub(r"\s+", " ",
                  re.sub(r"<[^>]+>", " ", blob.decode("utf-8"))).strip()
    card = "\n".join([
        "# 西班牙法条证据卡（离线合成；官方 BOE 整件与条文切片哈希钉在这里）",
        "ACT_ID: %s" % ES_ACT_ID,
        "ACT_TITLE: Ley 39/2015",
        "BLOCK_ID: a2",
        "ARTICLE_NUM: 2",
        "VERSION_DATE: 2026-11-16",
        "REFERENCE_DATE: %s" % fetch_reference_date,
        "SOURCE_FILE: official/act.xml",
        "OFFICIAL_XML_SHA256: %s" % _sha_bytes(ES_BOE_XML),
        "ARTICLE_SHA256: %s" % _sha_bytes(blob),
        "TEXT_CHARS: %d" % len(text),
        "--- OFFICIAL TEXT ---",
        text,
        "",
    ])
    (es / "a2.es.card.txt").write_text(card, encoding="utf-8")
    index = {
        "act_id": ES_ACT_ID,
        "act_title": "Ley 39/2015",
        "source_file": "official/act.xml",
        "source_sha256": _sha_bytes(ES_BOE_XML),
        "version_date": "2026-11-16",
        "fetch_reference_date": fetch_reference_date,
        "articles": {
            "a2": {
                "block_id": "a2", "num": "2",
                "article_file": "official/a2.xml",
                "article_sha256": _sha_bytes(blob),
                "article_bytes": len(blob),
                "card_file": "a2.es.card.txt",
                "card_sha256": _sha_bytes(card.encode("utf-8")),
            },
        },
    }
    (es / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return es


def add_es_fact(root: Path, value: str = "3",
                source: str = ES_CARD_REL) -> None:
    """加一条指向 ES 证据卡的事实（卡在则钉卡哈希，照两层证据模型）。"""
    lines = ['[[fact]]',
             'id = "ES-A2"',
             'claim = "西班牙行政程序法答复最长期限（合成）"',
             'value = "%s"' % value,
             'source = "%s"' % source]
    card = root / source
    if card.is_file():
        lines.append('source_sha256 = "sha256:%s"'
                     % _sha_bytes(card.read_bytes()))
    (root / "facts" / "40-es.toml").write_text("\n".join(lines) + "\n",
                                               encoding="utf-8")


def add_es_citation(root: Path, key: str = "art-es-a2") -> None:
    (root / "sections" / "02_es.tex").write_text(
        "\\section{ES}\n西班牙侧引用 \\cite{%s}。\n" % key, encoding="utf-8")


class LegalSlotCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        checks.load_integration("legal")   # 幂等；保证 legal 卡在册


class TestDiscoveryAndCard(LegalSlotCase):
    def test_load_integration_is_idempotent_and_registers(self):
        checks.load_integration("legal")
        pkg = checks.get_package("legal")
        self.assertIsNotNone(pkg)
        self.assertIn("legal", checks.registered_domains())

    def test_card_shape_matches_contract(self):
        pkg = checks.get_package("legal")
        self.assertEqual(pkg.domain_id, "legal")
        self.assertEqual(pkg.config_keys, frozenset({"corpus", "date", "view"}))
        self.assertIn("五闸", pkg.description)
        self.assertTrue(callable(pkg.verify))

    def test_resolve_names_legal_and_paper_in_order(self):
        root = build_legal_project(self.tmp / "p")
        cfg = load_config(root)
        domains = [p.domain_id for p in checks.resolve_packages(cfg)]
        self.assertEqual(domains, ["paper", "legal"])

    def test_unowned_id_still_config_error(self):
        cfg = Config(root=Path("."), checks_packages=["astro"])
        with self.assertRaises(ConfigError):
            checks.resolve_packages(cfg)

    def test_known_keys_raise_no_warning_unknown_key_warns(self):
        # 追加键不带表头（落模板末表 [checks.legal]）——重复表头是非法 TOML。
        root = build_legal_project(
            self.tmp / "p", '\nview = "out/view.jsonl"\n')
        cfg = load_config(root)
        checks.resolve_packages(cfg)
        legal_warns = [w for w in cfg.warnings
                       if w.get("location", "").startswith(
                           "factscribe.toml [checks.legal]")]
        self.assertEqual(legal_warns, [])
        root2 = build_legal_project(
            self.tmp / "p2", '\nfoo = "bar"\n')
        cfg2 = load_config(root2)
        checks.resolve_packages(cfg2)
        self.assertTrue(any(
            w["code"] == "CONFIG_UNKNOWN_FIELD" and w.get("field") == "foo"
            for w in cfg2.warnings))


class TestFailClosed(LegalSlotCase):
    def _run_audit(self, root: Path) -> tuple[int, dict]:
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        proc = subprocess.run(
            [sys.executable, "-m", "factscribe", "audit", str(root), "--json"],
            cwd=str(ROOT), env=env, capture_output=True, text=True)
        return proc.returncode, json.loads(proc.stdout)

    def test_undeclared_corpus_is_yellow_and_not_silent_green(self):
        root = build_legal_project(self.tmp / "p1")
        toml = (root / "factscribe.toml").read_text(encoding="utf-8")
        toml = toml.replace('corpus = "results/corpus-legal"\n', "")
        (root / "factscribe.toml").write_text(toml, encoding="utf-8")
        code, payload = self._run_audit(root)
        self.assertEqual(code, 3)   # paper 一黄＋legal 覆盖缺口黄——不许绿
        legal_y = legal_of(payload, "warnings")
        self.assertIn("LEGAL_COVERAGE_GAP", codes_of(legal_y))
        self.assertEqual(payload["summary"]["by_domain"]["legal"],
                         {"red": 0, "yellow": 1, "hints": 0})
        self.assertEqual(payload["summary"]["legal"]["gates"]["fr"]["status"],
                         "skipped")

    def test_missing_corpus_dir_is_yellow(self):
        root = build_legal_project(self.tmp / "p2")
        shutil.rmtree(root / "results" / "corpus-legal")
        code, payload = self._run_audit(root)
        # paper 也会因源文件丢失而红（两层证据各自钉同一份字节）；这里锁的是
        # legal 域必须亮出覆盖缺口黄，不许静默绿——退出码非绿即可。
        self.assertNotEqual(code, 0)
        self.assertIn("LEGAL_COVERAGE_GAP",
                      codes_of(legal_of(payload, "warnings")))

    def test_missing_or_bad_date_is_red(self):
        for name, replace in (
                ("nodate", 'date = "2026-11-14"\n'),
                ("baddate", 'date = "2026-11-14"')):
            root = build_legal_project(self.tmp / name)
            toml = (root / "factscribe.toml").read_text(encoding="utf-8")
            if replace.endswith("\n"):
                toml = toml.replace(replace, "")
            else:
                toml = toml.replace(replace, 'date = "20261114"')
            (root / "factscribe.toml").write_text(toml, encoding="utf-8")
            with self.subTest(name=name):
                code, payload = self._run_audit(root)
                self.assertEqual(code, 1)   # 红：参考日是时效判据的根基
                self.assertIn("LEGAL_DATE_INVALID",
                              codes_of(legal_of(payload, "issues")))

    def test_cn_items_without_catalog_fail_closed(self):
        root = build_legal_project(self.tmp / "p3")
        (root / "facts" / "cn.toml").write_text(
            '[[fact]]\nid = "CN-1"\nclaim = "一部中国法规"\nvalue = "42"\n'
            'source = "results/runs/run1/fta.cn.card.txt"\n', encoding="utf-8")
        code, payload = self._run_audit(root)
        self.assertIn("LEGAL_COVERAGE_GAP",
                      codes_of(legal_of(payload, "warnings")))
        gates = payload["summary"]["legal"]["gates"]
        self.assertEqual(gates["cn"]["status"], "skipped")
        self.assertEqual(gates["cn"]["note"], "catalog 没拿到")


class TestSlotBehavior(LegalSlotCase):
    def test_legal_summary_nests_and_by_domain_attributes(self):
        root = build_legal_project(self.tmp / "p")
        cfg = load_config(root)
        facts = load_facts(cfg)
        sections = load_sections(cfg)
        red, yellow, hints, summary, unresolved = checks.run_packages(
            cfg, facts, sections)
        # paper 一黄（NO_MANIFEST：合成项目没有人签清单）；legal 零发现
        self.assertEqual(summary["by_domain"],
                         {"paper": {"red": 0, "yellow": 1, "hints": 0},
                          "legal": {"red": 0, "yellow": 0, "hints": 0}})
        nested = summary["legal"]
        self.assertEqual(nested["domain"], "legal")
        self.assertEqual(nested["corpus"], "results/corpus-legal")
        self.assertEqual(nested["date"], "2026-11-14")
        self.assertEqual(nested["gates"]["fr"]["status"], "ran")
        self.assertEqual(nested["gates"]["case"]["status"], "ran")
        self.assertEqual(nested["gates"]["it"]["status"], "na")
        self.assertTrue(nested["lines"])
        self.assertEqual(unresolved, [])
        # 合法语料上合法引用：legal 域零发现；paper 一黄；折算单一入口
        self.assertEqual(len(red), 0)
        self.assertEqual(len(yellow), 1)
        code = checks.aggregate_exit(red, yellow, integrity_first=cfg.is_v3)
        self.assertEqual(code, 3)

    def test_slot_findings_match_standalone_gate_run(self):
        """M2 行为锁（离线替身）：挂槽与独立子命令同项目同读数。

        真语料跑不通（P-100，抓取脚本丢失），用合成语料当离线替身：
        独立 verify 子命令与槽内 legal 域对同一项目读数必须一致（全绿）。
        """
        root = build_legal_project(self.tmp / "p")
        cfg = load_config(root)
        # 独立闸跑（pre-M2 形态）：五子命令照旧可用
        env = dict(os.environ, PYTHONPATH=str(LEGAL))
        proc = subprocess.run(
            [sys.executable, "-m", "factscribe_legal", "verify",
             "--project", str(root),
             "--corpus", str(root / "results" / "corpus-legal"),
             "--date", "2026-11-14"],
            cwd=str(LEGAL), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        # 槽内同项目：legal 域同读数（零发现；paper 的 NO_MANIFEST 黄不计）
        red, yellow, _h, _s, _u = checks.run_packages(
            cfg, load_facts(cfg), load_sections(cfg))
        legal_red = [i for i in red if getattr(i, "domain", "") == "legal"]
        legal_yellow = [i for i in yellow if getattr(i, "domain", "") == "legal"]
        self.assertEqual((len(legal_red), len(legal_yellow)), (0, 0))

    def test_unknown_provision_is_red_in_slot(self):
        root = build_legal_project(self.tmp / "p")
        (root / "facts" / "two.toml").write_text(
            '[[fact]]\nid = "FR-BAD"\nclaim = "不存在的法条"\nvalue = "12"\n'
            'source = "results/corpus-legal/L9999-99.xml"\n', encoding="utf-8")
        cfg = load_config(root)
        red, yellow, _h, summary, _u = checks.run_packages(
            cfg, load_facts(cfg), load_sections(cfg))
        self.assertTrue(any(i.code == "LEGAL_PROV_UNKNOWN" for i in red))
        self.assertEqual(summary["by_domain"]["legal"]["red"], 1)


# --------------------------------------------------------------------------
# ES 独立桶（2026-11-16 批）：gates 行五桶并列 fr｜cn｜case｜it｜es；
# ES 事项不再被 _gate_scope 的 PROV_RE／art- 兜底误并进 fr 桶（回归钉）；
# 缺 es/ 语料 fail-closed；ES 判定走 ES_ 码表独立分节。
# --------------------------------------------------------------------------

FIVE_BUCKET_LINE = ("gates   : fr 红0/黄0（ran） ｜ cn 红0/黄0（na） ｜ "
                    "case 红0/黄0（ran） ｜ it 红0/黄0（na） ｜ "
                    "es 红0/黄0（ran）")


class TestESBucket(LegalSlotCase):
    def _slot(self, root):
        cfg = load_config(root)
        red, yellow, _h, summary, _u = checks.run_packages(
            cfg, load_facts(cfg), load_sections(cfg))
        return red, yellow, summary

    def test_es_bucket_runs_independent_section(self):
        """ran 态：ES 视图在、ES 卡被 ES 闸独立判定，gates 行五桶并列。"""
        root = build_legal_project(self.tmp / "p")
        build_es_view(root)
        add_es_fact(root)
        red, yellow, summary = self._slot(root)
        gates = summary["legal"]["gates"]
        self.assertEqual(gates["es"]["status"], "ran")
        self.assertEqual(gates["es"]["note"], "1 条事项")
        self.assertEqual(gates["es"]["red"], 0)   # 合成语料合法引用零发现
        self.assertEqual(summary["legal"]["lines"][1], FIVE_BUCKET_LINE)
        # summary 归属：ES 零发现不增 legal 域计数（paper 的 NO_MANIFEST 不计）
        self.assertEqual(summary["by_domain"]["legal"],
                         {"red": 0, "yellow": 0, "hints": 0})

    def test_es_items_not_merged_into_fr_bucket(self):
        """反例回归钉：.es.card.txt 与 art-es- 引用不得进 fr 桶计数。

        修复前：PROV_RE 兜底把 ES 卡并进 fr、art- 前缀把 art-es- 引用并进
        fr——fr 的「N 条事项」把 ES 事项算进去。本例 FR 1 条＋ES 卡 1 条＋
        ES 引用 1 条：fr 必须＝1，es 必须＝2。
        """
        root = build_legal_project(self.tmp / "p")
        add_es_fact(root)
        add_es_citation(root)
        from factscribe_legal.checks_adapter import _gate_scope
        scope = _gate_scope(str(root))
        self.assertEqual(scope["fr"], 1)
        self.assertEqual(scope["es"], 2)
        _red, _yellow, summary = self._slot(root)
        gates = summary["legal"]["gates"]
        self.assertEqual(gates["fr"]["status"], "ran")
        self.assertEqual(gates["fr"]["note"], "1 条事项")   # 不含 ES 事项
        self.assertEqual(gates["es"]["status"], "skipped")

    def test_es_missing_material_fails_closed(self):
        """有 ES 事项而 es/ 语料没拿到 ⇒ 黄 LEGAL_COVERAGE_GAP，不许静默绿。"""
        root = build_legal_project(self.tmp / "p")
        add_es_fact(root)
        add_es_citation(root)
        _red, yellow, summary = self._slot(root)
        legal_y = [i for i in yellow if getattr(i, "domain", "") == "legal"]
        self.assertTrue(any(i.code == "LEGAL_COVERAGE_GAP"
                            and "西班牙" in i.message for i in legal_y))
        gates = summary["legal"]["gates"]
        self.assertEqual(gates["es"]["status"], "skipped")
        self.assertEqual(gates["es"]["note"], "es/ 语料没拿到")
        from factscribe.checks import aggregate_exit
        self.assertEqual(aggregate_exit([], legal_y), 3)   # 黄＝3，非绿

    def test_es_quote_mismatch_is_red_in_legal_domain(self):
        """ES 判定走 ES_ 码表独立分节：值不在条文正文 ⇒ ES_QUOTE_MISMATCH 红。"""
        root = build_legal_project(self.tmp / "p")
        build_es_view(root)
        add_es_fact(root, value="999")   # 条文正文里没有 999
        red, _yellow, summary = self._slot(root)
        legal_red = [i for i in red if getattr(i, "domain", "") == "legal"]
        self.assertIn("ES_QUOTE_MISMATCH", [i.code for i in legal_red])
        self.assertEqual(summary["by_domain"]["legal"]["red"], 1)
        gates = summary["legal"]["gates"]
        self.assertEqual((gates["es"]["status"], gates["es"]["red"]),
                         ("ran", 1))

    def test_es_gate_skips_when_date_invalid(self):
        """date 非法 ⇒ LEGAL_DATE_INVALID 红，ES 闸与时效闸一起 skip。"""
        root = build_legal_project(self.tmp / "p")
        build_es_view(root)
        add_es_fact(root)
        toml = (root / "factscribe.toml").read_text(encoding="utf-8")
        toml = toml.replace('date = "2026-11-14"', 'date = "20261114"')
        (root / "factscribe.toml").write_text(toml, encoding="utf-8")
        red, _yellow, summary = self._slot(root)
        legal_red = [i for i in red if getattr(i, "domain", "") == "legal"]
        self.assertIn("LEGAL_DATE_INVALID", [i.code for i in legal_red])
        gates = summary["legal"]["gates"]
        self.assertEqual(gates["es"]["status"], "skipped")
        self.assertEqual(gates["es"]["note"], "date 未定，时效判据全跳过")

    def test_es_na_when_no_items_and_no_material(self):
        """na 态：无 ES 事项且无 es/ 材料 ⇒ na「0 事项」（语义照 CN/IT）。"""
        root = build_legal_project(self.tmp / "p")
        _red, _yellow, summary = self._slot(root)
        gates = summary["legal"]["gates"]
        self.assertEqual(gates["es"]["status"], "na")
        self.assertEqual(gates["es"]["note"], "0 事项")


# --------------------------------------------------------------------------
# 端到端（提交在仓的合成演示项目 fixtures/legal-demo）：单命令双域报告
# --------------------------------------------------------------------------

DEMO = ROOT / "fixtures" / "legal-demo"


class TestDualDomainEndToEnd(LegalSlotCase):
    """验收门 f/g 的常驻面：无 [checks] 单域不变；点名 legal 双域分节；
    缺语料 fail-closed 亮出；未注册包名 exit 2。"""

    def _audit(self, root, human=False):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        cmd = [sys.executable, "-m", "factscribe", "audit", str(root)]
        if not human:
            cmd.append("--json")
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env,
                              capture_output=True, text=True)
        return proc

    def _variant(self, name, mutate):
        root = self.tmp / name
        shutil.copytree(DEMO, root)
        mutate(root)
        return root

    def test_demo_fixture_dual_domain_json(self):
        proc = self._audit(DEMO)
        self.assertEqual(proc.returncode, 1)   # paper 一红（UNMATCHED_NUMBER 7）
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["summary"]["by_domain"],
                         {"paper": {"red": 1, "yellow": 1, "hints": 0},
                          "legal": {"red": 0, "yellow": 0, "hints": 0}})
        for f in payload["findings"]:
            self.assertIn(f.get("domain"), ("paper", "legal"))
        self.assertEqual(payload["summary"]["legal"]["gates"]["fr"]["status"],
                         "ran")
        self.assertEqual(payload["summary"]["legal"]["date"], "2026-11-14")

    def test_demo_es_bucket_ran_and_five_bucket_gates_line(self):
        """验收门 f（ran 态）：legal 节 gates 行五桶并列，ES 桶 ran。"""
        payload = json.loads(self._audit(DEMO).stdout)
        gates = payload["summary"]["legal"]["gates"]
        self.assertEqual(gates["es"]["status"], "ran")
        self.assertEqual(gates["es"]["note"], "1 条事项")
        self.assertEqual(gates["es"]["red"], 0)
        self.assertEqual(payload["summary"]["legal"]["lines"][1],
                         FIVE_BUCKET_LINE)

    def test_demo_without_es_material_es_is_na(self):
        """验收门 f（na 态）：拆掉 ES 材料＋事项 ⇒ es 桶 na「0 事项」。"""
        def drop_es(root):
            shutil.rmtree(root / "results" / "corpus-legal" / "es")
            (root / "facts" / "40-es.toml").unlink()
        root = self._variant("no-es", drop_es)
        payload = json.loads(self._audit(root).stdout)
        gates = payload["summary"]["legal"]["gates"]
        self.assertEqual(gates["es"]["status"], "na")
        self.assertEqual(gates["es"]["note"], "0 事项")

    def test_demo_human_report_has_domain_sections_legal_last(self):
        proc = self._audit(DEMO, human=True)
        text = proc.stdout
        self.assertIn("---- 核验域：legal ----", text)
        self.assertIn("gates   : fr 红0/黄0（ran）", text)
        self.assertIn("es 红0/黄0（ran）", text)   # 五桶并列的人读形状
        self.assertLess(text.index("[黄] 1 处"),
                        text.index("---- 核验域：legal ----"))
        self.assertIn("结论：1 红 / 1 黄 → 红（有违例）（退出码 1）", text)

    def test_no_checks_section_is_single_domain_unchanged(self):
        def strip_checks(root):
            toml = (root / "factscribe.toml").read_text(encoding="utf-8")
            head = toml.split("[checks]", 1)[0]
            (root / "factscribe.toml").write_text(head, encoding="utf-8")
        root = self._variant("plain", strip_checks)
        proc_plain = self._audit(root)
        self.assertEqual(proc_plain.returncode, 1)
        payload = json.loads(proc_plain.stdout)
        self.assertNotIn("by_domain", payload["summary"])
        self.assertNotIn("domain", payload["findings"][0])
        self.assertNotIn("核验域", self._audit(root, human=True).stdout)
        # findings 内容与双域跑的 paper 部分逐条相同（去 domain 键后）
        proc_dual = self._audit(DEMO)
        dual = json.loads(proc_dual.stdout)
        strip = lambda fs: sorted((f["severity"], f["code"],
                                   f.get("location", ""), f["message"])
                                  for f in fs if f.get("domain") == "paper")
        self.assertEqual(strip(dual["findings"]),
                         sorted((f["severity"], f["code"],
                                 f.get("location", ""), f["message"])
                                for f in payload["findings"]))

    def test_missing_corpus_fails_closed_in_dual_report(self):
        def drop_corpus(root):
            toml = (root / "factscribe.toml").read_text(encoding="utf-8")
            toml = toml.replace('corpus = "results/corpus-legal"\n', "")
            (root / "factscribe.toml").write_text(toml, encoding="utf-8")
        root = self._variant("nocorpus", drop_corpus)
        proc = self._audit(root)
        payload = json.loads(proc.stdout)
        legal_y = [f for f in payload["warnings"]
                   if f.get("domain") == "legal"]
        self.assertIn("LEGAL_COVERAGE_GAP", codes_of(legal_y))
        text = self._audit(root, human=True).stdout
        self.assertIn("法律域 0 覆盖", text)

    def test_legal_only_run_renders_without_paper_header(self):
        def legal_only(root):
            toml = (root / "factscribe.toml").read_text(encoding="utf-8")
            toml = toml.replace('packages = ["paper", "legal"]',
                                'packages = ["legal"]')
            (root / "factscribe.toml").write_text(toml, encoding="utf-8")
        root = self._variant("legalonly", legal_only)
        proc = self._audit(root)
        self.assertEqual(proc.returncode, 0)   # 只跑 legal：全绿
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["summary"]["by_domain"],
                         {"legal": {"red": 0, "yellow": 0, "hints": 0}})
        self.assertNotIn("paper", payload["summary"]["by_domain"])
        text = self._audit(root, human=True).stdout
        self.assertIn("---- 核验域：legal ----", text)
        self.assertNotIn("numbers :", text)   # paper 头块不出现

    def test_unregistered_package_is_exit_two(self):
        def name_astro(root):
            toml = (root / "factscribe.toml").read_text(encoding="utf-8")
            toml = toml.replace('packages = ["paper", "legal"]',
                                'packages = ["paper", "astro"]')
            (root / "factscribe.toml").write_text(toml, encoding="utf-8")
        root = self._variant("astro", name_astro)
        proc = self._audit(root)
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "CONFIG_INVALID")
        self.assertIn("astro", payload["findings"][0]["message"])
        self.assertIn("已注册", payload["findings"][0]["message"])


# --------------------------------------------------------------------------
# 每域一把冻结锁（裁定⑨）：audit/evidence-legal.lock 与 paper 锁互不干扰
# --------------------------------------------------------------------------

from factscribe_legal.checks_adapter import (canonical_form,  # noqa: E402
                                             canonical_sha256,
                                             unfreeze_evidence_lock,
                                             write_evidence_lock)


class TestLegalEvidenceLock(LegalSlotCase):
    def _run_slot(self, root):
        cfg = load_config(root)
        red, yellow, _h, summary, _u = checks.run_packages(
            cfg, load_facts(cfg), load_sections(cfg))
        legal = [i for i in red + yellow
                 if getattr(i, "domain", "") == "legal"]
        return cfg, legal, summary

    def test_lock_path_is_domain_scoped_and_deterministic(self):
        root = build_legal_project(self.tmp / "p1")
        a = write_evidence_lock(root, corpus="results/corpus-legal",
                                date="2026-11-14", view="")
        b = write_evidence_lock(root, corpus="results/corpus-legal",
                                date="2026-11-14", view="")
        self.assertEqual(a["path"], "audit/evidence-legal.lock")
        self.assertEqual(a["sha256"], b["sha256"])
        lock = root / "audit" / "evidence-legal.lock"
        self.assertTrue(lock.is_file())
        # 适配器的锁件路径与槽的唯一权威函数同源（裁定⑨）
        self.assertEqual(checks.evidence_lock_path(root, "legal"), lock)
        self.assertFalse((root / "audit" / "evidence.lock").exists(),
                         "legal 锁不许碰 paper 的锁件")

    def test_canonical_form_is_closed_set_and_order_free(self):
        f1 = canonical_form("c", "2026-11-14", "v", "ab" * 32)
        self.assertEqual(f1,
                         "corpus\tc\n"
                         "date\t2026-11-14\n"
                         "index_sha256\t" + "ab" * 32 + "\n"
                         "view\tv")
        self.assertEqual(canonical_sha256("c", "2026-11-14", "v", "ab" * 32),
                         canonical_sha256("c", "2026-11-14", "v", "ab" * 32))

    def test_frozen_project_runs_without_evidence_findings(self):
        root = build_legal_project(self.tmp / "p2")
        write_evidence_lock(root, corpus="results/corpus-legal",
                            date="2026-11-14")
        _cfg, legal, _summary = self._run_slot(root)
        self.assertEqual([i.code for i in legal], [])

    def test_date_flip_after_freeze_is_red(self):
        root = build_legal_project(self.tmp / "p3")
        write_evidence_lock(root, corpus="results/corpus-legal",
                            date="2026-11-14")
        toml = (root / "factscribe.toml").read_text(encoding="utf-8")
        toml = toml.replace('date = "2026-11-14"', 'date = "2026-11-15"')
        (root / "factscribe.toml").write_text(toml, encoding="utf-8")
        _cfg, legal, _summary = self._run_slot(root)
        self.assertIn("LEGAL_EVIDENCE_CHANGED", [i.code for i in legal])
        self.assertTrue(all(i.severity == "red"
                            for i in legal
                            if i.code == "LEGAL_EVIDENCE_CHANGED"))

    def test_corpus_change_after_freeze_is_red(self):
        root = build_legal_project(self.tmp / "p4")
        write_evidence_lock(root, corpus="results/corpus-legal",
                            date="2026-11-14")
        idx = root / "results" / "corpus-legal" / "index.json"
        data = json.loads(idx.read_text(encoding="utf-8"))
        data["pool_asof"] = "2026-11-01"   # 换了语料视图（索引字节变）
        idx.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                  sort_keys=True) + "\n", encoding="utf-8")
        _cfg, legal, _summary = self._run_slot(root)
        self.assertIn("LEGAL_EVIDENCE_CHANGED", [i.code for i in legal])

    def test_unfreeze_is_yellow_then_refreeze_clears_it(self):
        root = build_legal_project(self.tmp / "p5")
        write_evidence_lock(root, corpus="results/corpus-legal",
                            date="2026-11-14")
        unfreeze_evidence_lock(root, reason="换语料", at="2026-11-16")
        _cfg, legal, _summary = self._run_slot(root)
        self.assertIn("LEGAL_EVIDENCE_UNFROZEN", [i.code for i in legal])
        self.assertTrue(all(i.severity == "yellow"
                            for i in legal
                            if i.code == "LEGAL_EVIDENCE_UNFROZEN"))
        write_evidence_lock(root, corpus="results/corpus-legal",
                            date="2026-11-14")
        _cfg, legal, _summary = self._run_slot(root)
        self.assertNotIn("LEGAL_EVIDENCE_UNFROZEN", [i.code for i in legal])
        self.assertNotIn("LEGAL_EVIDENCE_CHANGED", [i.code for i in legal])

    def test_paper_lock_check_unaffected_by_legal_lock(self):
        # paper 的 audit/evidence.lock 不存在 ⇒ paper 不判 EVIDENCE_SET_CHANGED；
        # legal 锁只在自己域里说话（互不干扰）。
        root = build_legal_project(self.tmp / "p6")
        write_evidence_lock(root, corpus="results/corpus-legal",
                            date="2026-11-14")
        cfg, facts, sections = (lambda c: (c, load_facts(c),
                                           load_sections(c)))(load_config(root))
        red, yellow, _h, _s, _u = checks.run_packages(cfg, facts, sections)
        paper = [i for i in red + yellow
                 if getattr(i, "domain", "") == "paper"]
        self.assertNotIn("EVIDENCE_SET_CHANGED", [i.code for i in paper])
        legal = [i for i in red + yellow
                 if getattr(i, "domain", "") == "legal"]
        self.assertNotIn("EVIDENCE_SET_CHANGED", [i.code for i in legal])


if __name__ == "__main__":
    unittest.main()
