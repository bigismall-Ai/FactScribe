# -*- coding: utf-8 -*-
r"""M1.5 第二批进槽：style（文风闸）与 pdf（PDF 回检层）核验包的行为锁。

规范：docs/design/SPEC-CHECKS.md §3（包契约）、§4.3（core 存量码一字不改
——style/pdf 系码按祖父条款照旧发射，无前缀不补名）、§5.2（点名即跑、
不点名不跑）、§7 M1.5（裁定⑤）。全离线，判据零 LLM。

行为锁纪律（M1.5 与 M1 同一把尺）：本批是「新增可选包」，不迁移任何
既有直跑路径——M1 金样例锁原样通过就是「现状逐字节不变」的证明（不许
重冻）；本件锁的是新包自身的三件事：

* 卡（注册形状）：domain_id／config_keys／描述；[checks.style]／
  [checks.pdf] 键值非法＝配置错 exit 2（fail-closed），未知键＝告警不阻断；
* 判据零改动：槽内发现与独立命令（`factscribe style`／`verify-pdf` 的
  判据本体）同码同severity同读数——style 用独立命令对表，pdf 用
  hostile/benign 夹具的 SPEC 期望对表；
* 材料缺失 fail-closed：pdf 包 main.pdf／report 缺失＝红（8／2→折 1），
  不许静默绿（§3.1 材料依赖声明）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from factscribe import checks  # noqa: E402
from factscribe import pdfgate  # noqa: E402
from factscribe.config import ConfigError, load_config, load_sections  # noqa: E402
from _pdfdep import requires_pdftotext  # noqa: E402

FIXTURES = ROOT / "fixtures"
TRUST_KEYS = FIXTURES / "trust" / "approver_keys.json"

PROJECT_TOML = """[project]
title = "M1.5 槽测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

STYLE_TEX = (
    "\\section{One}\n"
    "本框架——也就是所谓分层调度器——把任务切成小片。\n"
    "每片只做一件事，做完就停下来等人检查，检查完再继续往下走。\n"
    "所有状态都写在明面上，谁改了什么、什么时候改的，账上都有记录可查。\n"
)


def make_project(base: Path, extra_toml: str = "",
                 tex: str = STYLE_TEX) -> Path:
    """最小 v1 项目（文风可触发：插入语破折号；账与引用齐全）。"""
    root = Path(base)
    for d in ("sections", "facts"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(PROJECT_TOML + extra_toml,
                                          encoding="utf-8")
    (root / "sections" / "01_one.tex").write_text(tex, encoding="utf-8")
    (root / "facts" / "one.toml").write_text(
        '[[fact]]\nid = "B1"\nclaim = "一条主张"\nvalue = "42"\n',
        encoding="utf-8")
    (root / "refs.bib").write_text(
        "@article{key1,\n  title = {T},\n  author = {A},\n  year = {2024}\n}\n",
        encoding="utf-8")
    return root


def cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True)


def audit_json(root: Path) -> tuple[int, dict]:
    proc = cli("audit", str(root), "--json")
    return proc.returncode, json.loads(proc.stdout)


def codes_of(items: list[dict], domain: str | None = None) -> list[str]:
    return [i["code"] for i in items
            if domain is None or i.get("domain") == domain]


class M15Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        checks.register_builtins()   # 幂等；保证 paper/style/pdf 卡在册


# --------------------------------------------------------------------------
# 1. 注册卡（§3.1）：两域五样的代码面
# --------------------------------------------------------------------------

class TestCards(M15Case):
    def test_style_card_shape(self):
        pkg = checks.get_package("style")
        self.assertIsNotNone(pkg)
        self.assertEqual(pkg.domain_id, "style")
        self.assertEqual(pkg.config_keys,
                         frozenset({"rules", "stage",
                                    "report_unregistered", "report_abbrev"}))
        self.assertIn("文风", pkg.description)
        self.assertIn("style", checks.registered_domains())

    def test_pdf_card_shape(self):
        pkg = checks.get_package("pdf")
        self.assertIsNotNone(pkg)
        self.assertEqual(pkg.domain_id, "pdf")
        self.assertEqual(pkg.config_keys,
                         frozenset({"pdf", "report", "stamp", "keys"}))
        self.assertIn("PDF", pkg.description)
        self.assertIn("pdf", checks.registered_domains())

    def test_new_builtins_change_no_default(self):
        # 缺省（无 [checks]）点名仍只 paper——style/pdf 进册不搭车（§5.2）
        cfg = load_config(make_project(self.tmp / "p"))
        domains = [p.domain_id for p in checks.resolve_packages(cfg)]
        self.assertEqual(domains, ["paper"])

    def test_domain_sections_known_keys_no_warning(self):
        root = make_project(
            self.tmp / "p",
            '\n[checks]\npackages = ["style", "pdf"]\n'
            '\n[checks.style]\nstage = "revision"\n'
            "\n[checks.pdf]\nkeys = %r\n" % str(TRUST_KEYS))
        cfg = load_config(root)
        checks.resolve_packages(cfg)
        hits = [w for w in cfg.warnings
                if w["code"] == "CONFIG_UNKNOWN_FIELD"
                and str(w.get("location", "")).startswith("factscribe.toml [checks.")]
        self.assertEqual(hits, [])

    def test_domain_sections_unknown_key_warns_not_blocks(self):
        root = make_project(
            self.tmp / "p",
            '\n[checks]\npackages = ["style", "pdf"]\n'
            "\n[checks.style]\ncorpus = \"runs/x\"\n"
            "\n[checks.pdf]\ndate = \"2026-11-16\"\n")
        cfg = load_config(root)
        packages = checks.resolve_packages(cfg)
        self.assertEqual([p.domain_id for p in packages], ["style", "pdf"])
        fields = {w.get("field") for w in cfg.warnings
                  if w["code"] == "CONFIG_UNKNOWN_FIELD"}
        self.assertIn("corpus", fields)
        self.assertIn("date", fields)


# --------------------------------------------------------------------------
# 2. style 包：键值校验（fail-closed）＋判据零改动对表
# --------------------------------------------------------------------------

class TestStylePackage(M15Case):
    def _cfg(self, name: str, extra: str = ""):
        root = make_project(self.tmp / name, extra)
        return load_config(root), root

    def test_bad_stage_value_is_config_error(self):
        cfg, _root = self._cfg("bad-stage", '\n[checks.style]\nstage = "nope"\n')
        with self.assertRaises(ConfigError):
            checks.get_package("style").verify(cfg, [], [])

    def test_bad_flag_type_is_config_error(self):
        cfg, _root = self._cfg(
            "bad-flag", "\n[checks.style]\nreport_abbrev = \"yes\"\n")
        with self.assertRaises(ConfigError):
            checks.get_package("style").verify(cfg, [], [])

    def test_bad_rules_path_is_config_error(self):
        # rules 指到不存在的文件：独立命令同样的配置错语义（缺件不静默）
        cfg, _root = self._cfg(
            "bad-rules", '\n[checks.style]\nrules = "no-such-rules.toml"\n')
        with self.assertRaises(ConfigError):
            checks.get_package("style").verify(cfg, [], [])

    def test_findings_match_standalone_style_command(self):
        """行为锁：槽内 style 域与独立 `factscribe style` 同项目同读数。"""
        cfg, root = self._cfg("parity", '\n[checks]\npackages = ["style"]\n')
        facts = []          # style 不读账：verify 的 facts 形参占位即可
        sections = load_sections(cfg)
        red, yellow, hints, summary, unresolved = \
            checks.get_package("style").verify(cfg, facts, sections)
        self.assertEqual(unresolved, [])
        standalone = json.loads(
            cli("style", str(root), "--json").stdout)
        # 黄码多重集逐条相同（DASH_PARENTHETICAL×2）
        self.assertEqual(sorted(i.code for i in yellow),
                         sorted(f["code"] for f in standalone["findings"]))
        self.assertEqual(sorted(i.code for i in red),
                         sorted(f["code"] for f in standalone["findings"]
                                if f["severity"] == "red"))
        self.assertEqual(sorted(h.code for i in [0] for h in hints),
                         sorted([f["code"] for f in standalone.get("info", [])]
                                + [f["code"] for f in standalone.get("advisories", [])]))
        # 位置逐条相同（file:line）
        self.assertEqual(sorted((i.location, i.code) for i in yellow),
                         sorted(("%s:%d" % (f["file"], f["line"]),
                                 f["code"])
                                for f in standalone["findings"]))
        # summary 是 style 域自己的信封（带 lines 人读域头）
        self.assertEqual(summary["domain"], "style")
        self.assertTrue(summary.get("lines"))
        self.assertEqual(summary["triggered"], standalone["summary"]["triggered"])

    def test_evidence_stamp_is_red_and_exit_one_in_slot(self):
        """证据钢印红（exit 1）在槽内不降级：[evidence] 声明的节缺 \\fact。"""
        root = make_project(
            self.tmp / "stamp",
            '\n[checks]\npackages = ["style"]\n'
            '\n[evidence]\n01_one = ["B1"]\n')
        exit_code, payload = audit_json(root)
        self.assertEqual(exit_code, 1)
        reds = payload["issues"]
        self.assertTrue(reds)
        for item in reds:
            self.assertEqual(item.get("domain"), "style")
        self.assertIn("REQUIRED_EVIDENCE_MISSING", codes_of(reds))
        self.assertEqual(payload["summary"]["by_domain"]["style"]["red"],
                         len(reds))

    def test_stage_revision_config_reaches_judgement(self):
        # [checks.style].stage="revision" 真的改判定面（NUMERAL_DENSITY 降
        # info）——键值从槽配置透传到 analyze，不是摆设。NUMERAL_DENSITY
        # 需显式阈值（默认 null＝不判），项目内 style-rules.toml 给 40。
        tex = ("\\section{One}\n"
               "系统处理了 128 个请求，其中 120 个成功。\n"
               "剩下 8 个失败，都记录在案。失败原因分别是超时与校验错。\n")
        rules = '[thresholds]\nnumeral_density = 40.0\n'
        draft_cfg, draft_root = self._cfg("stage-draft")
        (draft_root / "sections" / "01_one.tex").write_text(
            tex, encoding="utf-8")
        (draft_root / "style-rules.toml").write_text(rules, encoding="utf-8")
        draft = checks.get_package("style").verify(
            draft_cfg, [], load_sections(draft_cfg))
        rev_cfg, rev_root = self._cfg(
            "stage-rev", '\n[checks.style]\nstage = "revision"\n')
        (rev_root / "sections" / "01_one.tex").write_text(
            tex, encoding="utf-8")
        (rev_root / "style-rules.toml").write_text(rules, encoding="utf-8")
        revision = checks.get_package("style").verify(
            rev_cfg, [], load_sections(rev_cfg))
        # draft 档 NUMERAL_DENSITY 计黄；revision 档降 info（进 hints）
        draft_yellow = [i.code for i in draft[1]]
        rev_yellow = [i.code for i in revision[1]]
        self.assertIn("NUMERAL_DENSITY", draft_yellow)
        self.assertNotIn("NUMERAL_DENSITY", rev_yellow)
        self.assertIn("NUMERAL_DENSITY", [h.code for h in revision[2]])

    def test_slot_run_is_deterministic(self):
        """确定性（§3.3）：同输入字节 ⇒ 同 findings 字节。"""
        root = make_project(self.tmp / "det",
                            '\n[checks]\npackages = ["style", "pdf"]\n')
        first = cli("audit", str(root), "--json").stdout
        second = cli("audit", str(root), "--json").stdout
        self.assertEqual(first, second)


# --------------------------------------------------------------------------
# 3. pdf 包：材料缺失 fail-closed ＋ 夹具对表
# --------------------------------------------------------------------------

class TestPdfPackage(M15Case):
    def _project(self, name: str, extra: str = "") -> Path:
        root = make_project(self.tmp / name,
                            extra or '\n[checks]\npackages = ["pdf"]\n',
                            tex="\\section{One}\n正文一回事。\n")
        return root

    def test_missing_report_fails_closed(self):
        """材料缺失不许静默绿：没 report ⇒ 红（REPORT_SCHEMA_INVALID，
        槽内折 1；缺 poppler 的环境则 PDF_TOOL_MISSING=8——两级都是 fail-closed）。"""
        root = self._project("no-report")
        exit_code, payload = audit_json(root)
        self.assertTrue(payload["issues"], "材料缺失必须出红，不许零发现")
        for item in payload["issues"]:
            self.assertEqual(item.get("domain"), "pdf")
        if pdfgate.missing_tools():
            self.assertEqual(codes_of(payload["issues"]), ["PDF_TOOL_MISSING"])
            self.assertEqual(exit_code, 8)
        else:
            self.assertEqual(codes_of(payload["issues"]),
                             ["REPORT_SCHEMA_INVALID"])
            # 折算边界：存量 exit_code=2 的红在槽内按全局口径折 1
            self.assertEqual(exit_code, 1)

    def test_missing_pdf_fails_closed_with_exit_eight(self):
        """report 在而 main.pdf 缺 ⇒ PDF_TOOL_MISSING（8）：有工具时
        pdftotext 读不到件、没工具时缺工具链——两条路都落同一红码。"""
        root = self._project("no-pdf")
        (root / "audit").mkdir()
        (root / "audit" / "report.json").write_text(
            json.dumps({"number_ledger": [], "pdf_whitelist": [],
                        "structural_whitelist": {}}), encoding="utf-8")
        exit_code, payload = audit_json(root)
        self.assertEqual(exit_code, 8)
        self.assertEqual(codes_of(payload["issues"]), ["PDF_TOOL_MISSING"])
        self.assertEqual(payload["issues"][0].get("domain"), "pdf")

    def test_bad_config_value_is_config_error(self):
        root = self._project(
            "bad-pdf-key", '\n[checks]\npackages = ["pdf"]\n'
                           "\n[checks.pdf]\npdf = 3\n")
        cfg = load_config(root)
        with self.assertRaises(ConfigError):
            checks.get_package("pdf").verify(cfg, [], [])

    @requires_pdftotext
    def test_hostile_pdfoxeway_via_slot_matches_spec(self):
        """hostile R3-PDF-ONEWAY 走槽：PDF_LEDGER_TOKEN_MISSING 红（exit 5），
        与 EXPECT.json 的 SPEC 期望同码同值（判据零改动的对表）。"""
        root = self.tmp / "oneway"
        shutil.copytree(FIXTURES / "hostile" / "R3-PDF-ONEWAY", root)
        with open(root / "factscribe.toml", "a", encoding="utf-8") as fh:
            fh.write('\n[checks]\npackages = ["pdf"]\n')
        exit_code, payload = audit_json(root)
        self.assertEqual(exit_code, 5)
        self.assertEqual(codes_of(payload["issues"], "pdf"),
                         ["PDF_LEDGER_TOKEN_MISSING",
                          "PDF_LEDGER_TOKEN_MISSING"])
        self.assertEqual(payload["summary"]["by_domain"]["pdf"]["red"], 2)

    @requires_pdftotext
    def test_benign_pdfoxeway_via_slot_is_green(self):
        """benign R3-PDF-ONEWAY 走槽：零发现 exit 0——回检不冤枉干净件。"""
        root = self.tmp / "oneway-benign"
        shutil.copytree(FIXTURES / "benign" / "R3-PDF-ONEWAY", root)
        with open(root / "factscribe.toml", "a", encoding="utf-8") as fh:
            fh.write('\n[checks]\npackages = ["pdf"]\n')
        exit_code, payload = audit_json(root)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["issues"], [])
        self.assertEqual(payload["summary"]["by_domain"]["pdf"],
                         {"red": 0, "yellow": 0, "hints": 0})

    @requires_pdftotext
    def test_stamp_without_keys_fails_closed(self):
        """有 stamp 没 keys＝STAMP_KEY_UNTRUSTED（5）：信任链缺件不许过
        （verify-pdf「--stamp 有则必须先验」的现行语义原样进槽）。"""
        root = self.tmp / "selfsign"
        shutil.copytree(FIXTURES / "hostile" / "R3-STAMP-SELFSIGN", root)
        with open(root / "factscribe.toml", "a", encoding="utf-8") as fh:
            fh.write('\n[checks]\npackages = ["pdf"]\n')
        exit_code, payload = audit_json(root)
        self.assertEqual(exit_code, 5)
        self.assertEqual(codes_of(payload["issues"], "pdf"),
                         ["STAMP_KEY_UNTRUSTED"])

    @requires_pdftotext
    def test_stamp_with_trusted_keys_passes_chain(self):
        """keys 指到项目外信任根（[checks.pdf].keys）：信任链过、页面判定
        接棒——benign 夹具照 EXPECT 期望全绿（键值非法＝配置错的另一面：
        配对了就是正常闸）。"""
        root = self.tmp / "selfsign-benign"
        shutil.copytree(FIXTURES / "benign" / "R3-STAMP-SELFSIGN", root)
        with open(root / "factscribe.toml", "a", encoding="utf-8") as fh:
            fh.write('\n[checks]\npackages = ["pdf"]\n'
                     "\n[checks.pdf]\nkeys = %r\n" % str(TRUST_KEYS))
        exit_code, payload = audit_json(root)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["issues"], [])

    def test_summary_declares_materials(self):
        """summary 明示材料面：pdf/report/stamp/keys 与红黄计数——「查没查、
        拿什么查」摆在明面上，不是空集伪装全绿（§3.1）。"""
        root = self._project("summary")
        (root / "audit").mkdir()
        (root / "audit" / "report.json").write_text("{not-json",
                                                    encoding="utf-8")
        _exit, payload = audit_json(root)
        summary = payload["summary"]
        self.assertEqual(summary.get("domain"), "pdf")
        self.assertEqual(summary.get("pdf"), "main.pdf")
        self.assertEqual(summary.get("report"), "audit/report.json")
        self.assertEqual(summary.get("stamp"), "无")
        self.assertTrue(summary.get("lines"))


if __name__ == "__main__":
    unittest.main()
