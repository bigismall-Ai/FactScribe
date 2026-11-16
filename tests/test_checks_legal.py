# -*- coding: utf-8 -*-
r"""legal 核验包（M2）：发现注册＋卡形状＋fail-closed＋槽内行为。

规范：docs/design/SPEC-CHECKS-draft.md §3（包契约）、§5（配置）、§7 M2。
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
* 冻结锁：audit/evidence-legal.lock 与 paper 的 audit/evidence.lock 互不干扰
  （在 TestLegalEvidenceLock）。
"""
from __future__ import annotations

import hashlib
import json
import os
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
        self.assertIn("四闸", pkg.description)
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
        root = build_legal_project(
            self.tmp / "p", '\n[checks.legal]\nview = "out/view.jsonl"\n')
        cfg = load_config(root)
        checks.resolve_packages(cfg)
        legal_warns = [w for w in cfg.warnings
                       if w.get("location", "").startswith(
                           "factscribe.toml [checks.legal]")]
        self.assertEqual(legal_warns, [])
        root2 = build_legal_project(
            self.tmp / "p2", '\n[checks.legal]\nfoo = "bar"\n')
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

    def test_demo_human_report_has_domain_sections_legal_last(self):
        proc = self._audit(DEMO, human=True)
        text = proc.stdout
        self.assertIn("---- 核验域：legal ----", text)
        self.assertIn("gates   : fr 红0/黄0（ran）", text)
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


if __name__ == "__main__":
    unittest.main()
