# -*- coding: utf-8 -*-
r"""核验槽（factscribe/checks.py）机制测试：注册表＋[checks] 解析＋折算＋对表。

规范：docs/design/SPEC-CHECKS-draft.md（§2.2 槽四件事、§3 包契约、
§5 配置与兼容承诺）。全离线，判据零 LLM。

覆盖：

* 注册表：paper 已注册、卡形状、domain_id 形状校验、重复注册拒绝；
* 点名：缺省只跑 paper（裁定③）、显式 paper、未注册 id＝exit 2 并
  点名已注册清单、[checks.<domain>] 未知键＝告警不阻断；
* [checks] 解析：无节不启用、省 packages 同无节、字符串归一、去重、
  非法形状 exit 2、v1/V3 都可挂、V3 顶层已知字段不误告警；
* 退出码折算：值与旧 _aggregate_exit 逐一相同（值永不变化）、
  单一实现（audit 旧名＝同一函数对象）、闭集整表；
* 槽路径信封：域标只增键、by_domain 只增键、与直跑内容逐条相同；
* 每域一把冻结锁：paper 沿用既有锁路径、其他域带域后缀。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe import checks  # noqa: E402
from factscribe import audit as audit_mod  # noqa: E402
from factscribe import constants  # noqa: E402
from factscribe.config import Config, ConfigError, load_config  # noqa: E402
from factscribe.config import load_facts, load_sections  # noqa: E402

PROJECT_TOML = """[project]
title = "槽机制测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""


def make_audit_project(base: Path, extra_toml: str = "") -> Path:
    """最小可审计 v1 项目：1 红（缺 source）＋1 黄（未绑定）＋0 hint。"""
    root = Path(base)
    for d in ("sections", "facts", "results"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(PROJECT_TOML + extra_toml,
                                          encoding="utf-8")
    (root / "sections" / "01_one.tex").write_text(
        "\\section{One}\n"
        "绑定数字 \\fact{B1}{42} 42 结束。\n"
        "未绑定数字 7 在这里。\n"
        "引用 \\cite{key1}。\n",
        encoding="utf-8")
    (root / "facts" / "one.toml").write_text(
        '[[fact]]\nid = "B1"\nclaim = "一条主张"\nvalue = "42"\n',
        encoding="utf-8")
    (root / "refs.bib").write_text(
        "@article{key1,\n  title = {T},\n  author = {A},\n  year = {2024},\n"
        "  doi = {10.1234/abc}\n}\n",
        encoding="utf-8")
    return root


def bare_config(**kw) -> Config:
    return Config(root=Path("."), **kw)


def cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True)


def strip_domain(items: list[dict]) -> list[dict]:
    out = []
    for d in items:
        d = dict(d)
        d.pop("domain", None)
        out.append(d)
    return out


class SlotCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        checks.register_builtins()   # 幂等；保证注册表就位


# --------------------------------------------------------------------------
# 1. 注册表与卡（§3.1）
# --------------------------------------------------------------------------

class TestRegistry(SlotCase):
    def test_paper_is_registered_with_expected_card(self):
        pkg = checks.get_package("paper")
        self.assertIsNotNone(pkg)
        self.assertEqual(pkg.domain_id, "paper")
        self.assertEqual(pkg.config_keys, frozenset())
        self.assertIn("三闸", pkg.description)
        self.assertIn("paper", checks.registered_domains())

    def test_duplicate_registration_rejected(self):
        with self.assertRaises(ConfigError):
            checks.register_package(checks.CheckPackage(
                domain_id="paper", verify=lambda *a, **k: None))

    def test_invalid_domain_id_rejected(self):
        for bad in ("Paper", "", "legal domain", "法域"):
            with self.subTest(domain_id=bad):
                with self.assertRaises(ConfigError):
                    checks.CheckPackage(domain_id=bad,
                                        verify=lambda *a, **k: None)

    def test_valid_domain_id_accepted(self):
        card = checks.CheckPackage(domain_id="legal-x9",
                                   verify=lambda *a, **k: None)
        self.assertEqual(card.domain_id, "legal-x9")


# --------------------------------------------------------------------------
# 2. 点名（§5.2）
# --------------------------------------------------------------------------

class TestResolve(SlotCase):
    def test_default_is_paper_only(self):
        # 无 [checks]：cfg.checks_packages 为空 → 只跑 paper（裁定③）
        cfg = bare_config()
        packages = checks.resolve_packages(cfg)
        self.assertEqual([p.domain_id for p in packages], ["paper"])

    def test_explicit_paper_resolves(self):
        cfg = bare_config(checks_packages=["paper"])
        packages = checks.resolve_packages(cfg)
        self.assertEqual([p.domain_id for p in packages], ["paper"])

    def test_unknown_package_is_config_error_naming_registry(self):
        cfg = bare_config(checks_packages=["legal"])
        with self.assertRaises(ConfigError) as ctx:
            checks.resolve_packages(cfg)
        self.assertEqual(ctx.exception.code, "CONFIG_INVALID")
        self.assertIn("legal", str(ctx.exception))
        self.assertIn("paper", str(ctx.exception))   # 点名已注册清单

    def test_unknown_key_in_domain_section_warns_but_resolves(self):
        cfg = bare_config(checks_packages=["paper"],
                          checks_tables={"paper": {"corpus": "runs/x"}})
        packages = checks.resolve_packages(cfg)
        self.assertEqual([p.domain_id for p in packages], ["paper"])
        codes = [w["code"] for w in cfg.warnings]
        self.assertIn("CONFIG_UNKNOWN_FIELD", codes)

    def test_unregistered_domain_section_warns_and_is_ignored(self):
        cfg = bare_config(checks_packages=["paper"],
                          checks_tables={"legal": {"corpus": "runs/x"}})
        packages = checks.resolve_packages(cfg)
        self.assertEqual([p.domain_id for p in packages], ["paper"])
        hit = [w for w in cfg.warnings
               if w["code"] == "CONFIG_UNKNOWN_FIELD"
               and "legal" in w["message"]]
        self.assertEqual(len(hit), 1)


# --------------------------------------------------------------------------
# 3. [checks] 配置解析（config.py，[budget]/[evidence] 先例口径）
# --------------------------------------------------------------------------

class TestConfigParse(SlotCase):
    def _load(self, name: str, extra: str) -> Config:
        return load_config(make_audit_project(self.tmp / name, extra))

    def test_no_checks_section_is_not_defined(self):
        cfg = self._load("none", "")
        self.assertFalse(cfg.checks_defined)
        self.assertEqual(cfg.checks_packages, [])
        self.assertEqual(cfg.checks_tables, {})

    def test_bare_checks_section_defined_without_packages(self):
        cfg = self._load("bare", "\n[checks]\n")
        self.assertTrue(cfg.checks_defined)
        self.assertEqual(cfg.checks_packages, [])

    def test_packages_string_is_coerced_to_list(self):
        cfg = self._load("str", '\n[checks]\npackages = "paper"\n')
        self.assertEqual(cfg.checks_packages, ["paper"])

    def test_packages_deduped_order_preserved(self):
        cfg = self._load("dup",
                         '\n[checks]\npackages = ["paper", "paper"]\n')
        self.assertEqual(cfg.checks_packages, ["paper"])

    def test_non_string_package_entry_is_config_error(self):
        with self.assertRaises(ConfigError):
            self._load("bad-entry",
                       "\n[checks]\npackages = [1]\n")

    def test_checks_non_table_is_config_error(self):
        # 顶层 `checks = "paper"`（非表）：必须写在 [project] 之前才是顶层键
        root = self.tmp / "bad-table"
        root.mkdir(parents=True)
        for d in ("sections", "facts"):
            (root / d).mkdir()
        (root / "factscribe.toml").write_text(
            'checks = "paper"\n\n' + PROJECT_TOML, encoding="utf-8")
        (root / "sections" / "01_one.tex").write_text("x\n", encoding="utf-8")
        (root / "facts" / "one.toml").write_text(
            '[[fact]]\nid = "B1"\nclaim = "c"\nvalue = "1"\n', encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(root)

    def test_non_table_top_level_key_warns_not_blocks(self):
        cfg = self._load("scalar", '\n[checks]\npackages = ["paper"]\n'
                                  'foo = "bar"\n')
        self.assertEqual(cfg.checks_packages, ["paper"])
        self.assertEqual(cfg.checks_tables, {})
        codes = [w["code"] for w in cfg.warnings]
        self.assertIn("CONFIG_UNKNOWN_FIELD", codes)

    def test_domain_subtable_is_passed_through_verbatim(self):
        cfg = self._load("table",
                         '\n[checks]\npackages = ["paper"]\n'
                         "\n[checks.paper]\ncorpus = \"runs/x\"\n")
        self.assertEqual(cfg.checks_tables, {"paper": {"corpus": "runs/x"}})

    def test_v3_top_level_checks_is_a_known_field(self):
        root = self.tmp / "v3"
        root.mkdir()
        (root / "factscribe.toml").write_text(
            'schema = "factscribe-project/3.0"\n'
            'name = "V3 槽测试"\n'
            'root_tex = "main.tex"\n'
            'facts = "facts"\n'
            "\n[checks]\npackages = [\"paper\"]\n",
            encoding="utf-8")
        cfg = load_config(root)
        self.assertTrue(cfg.checks_defined)
        self.assertEqual(cfg.checks_packages, ["paper"])
        # 顶层 [checks] 不许被未知字段扫描误告警
        stray = [w for w in cfg.warnings
                 if w["code"] == "CONFIG_UNKNOWN_FIELD"
                 and w.get("field") == "checks"]
        self.assertEqual(stray, [])


# --------------------------------------------------------------------------
# 4. 退出码折算（值永不变化；单一实现）
# --------------------------------------------------------------------------

class _Issue:
    """折算面的最小替身：只要 exit_code。"""

    def __init__(self, exit_code: int):
        self.exit_code = exit_code


class TestAggregateExit(SlotCase):
    def test_empty_is_zero(self):
        self.assertEqual(checks.aggregate_exit([], []), 0)

    def test_yellow_only_is_three(self):
        self.assertEqual(checks.aggregate_exit([], [_Issue(1)]), 3)

    def test_yellow_with_strict_is_one(self):
        self.assertEqual(checks.aggregate_exit([], [_Issue(1)], strict=True), 1)

    def test_red_priority_order(self):
        for code, want in ((8, 8), (1, 1), (5, 5), (7, 7)):
            with self.subTest(code=code):
                self.assertEqual(
                    checks.aggregate_exit([_Issue(code)], []), want)

    def test_red_mixed_takes_highest_priority(self):
        self.assertEqual(
            checks.aggregate_exit([_Issue(5), _Issue(8)], []), 8)
        self.assertEqual(
            checks.aggregate_exit([_Issue(7), _Issue(1)], []), 1)

    def test_integrity_first_lifts_five(self):
        self.assertEqual(
            checks.aggregate_exit([_Issue(5), _Issue(8)], [],
                                  integrity_first=True), 5)
        self.assertEqual(
            checks.aggregate_exit([_Issue(8)], [], integrity_first=True), 8)

    def test_red_with_unknown_exit_code_falls_back_to_one(self):
        self.assertEqual(checks.aggregate_exit([_Issue(6)], []), 1)

    def test_single_implementation_old_alias_is_same_object(self):
        # audit._aggregate_exit 只是指向槽折算的再导出别名（单一实现不变量）
        self.assertIs(audit_mod._aggregate_exit, checks.aggregate_exit)

    def test_closed_set_table_and_constants(self):
        self.assertEqual(set(checks.EXIT_CODE_CLOSED_SET),
                         {0, 1, 2, 3, 4, 5, 6, 7, 8, 9})
        self.assertEqual(constants.EXIT_PROOF, 6)
        self.assertEqual(constants.EXIT_ATTACK_OPEN, 9)


# --------------------------------------------------------------------------
# 5. 槽路径信封：域标与 by_domain 只增键、内容与直跑逐条相同
# --------------------------------------------------------------------------

class TestRunPackages(SlotCase):
    def _project(self, name: str, extra: str = ""):
        root = make_audit_project(self.tmp / name, extra)
        cfg = load_config(root)
        facts = load_facts(cfg)
        sections = load_sections(cfg)
        return cfg, facts, sections

    def test_slot_envelope_matches_direct_run(self):
        cfg, facts, sections = self._project("slot")
        direct = audit_mod.run_audit(cfg, facts, sections)
        slot = checks.run_packages(cfg, facts, sections)
        d_red, d_yellow, d_hints, d_summary, d_unresolved = direct
        s_red, s_yellow, s_hints, s_summary, s_unresolved = slot
        self.assertEqual(
            [i.as_dict() for i in d_red],
            strip_domain([i.as_dict() for i in s_red]))
        self.assertEqual(
            [i.as_dict() for i in d_yellow],
            strip_domain([i.as_dict() for i in s_yellow]))
        self.assertEqual(
            [i.as_dict() for i in d_hints],
            strip_domain([i.as_dict() for i in s_hints]))
        self.assertEqual(d_unresolved, s_unresolved)
        # summary 只多 by_domain 一键
        self.assertEqual(set(s_summary) - set(d_summary), {"by_domain"})
        self.assertEqual(s_summary["by_domain"],
                         {"paper": {"red": len(d_red),
                                    "yellow": len(d_yellow),
                                    "hints": len(d_hints)}})
        # 退出码同值（折算只在槽，值永不变化）
        self.assertEqual(
            checks.aggregate_exit(d_red, d_yellow, integrity_first=cfg.is_v3),
            checks.aggregate_exit(s_red, s_yellow, integrity_first=cfg.is_v3))

    def test_domain_issue_stamps_domain_first_and_delegates(self):
        cfg, facts, sections = self._project("stamp")
        red = audit_mod.run_audit(cfg, facts, sections)[0]
        stamped = checks.DomainIssue("paper", red[0])
        d = stamped.as_dict()
        self.assertEqual(list(d)[0], "domain")
        self.assertEqual(d["domain"], "paper")
        self.assertEqual(stamped.exit_code, red[0].exit_code)
        self.assertEqual(stamped.code, red[0].code)
        self.assertEqual(stamped.message, red[0].message)


# --------------------------------------------------------------------------
# 6. 端到端（子进程）：无节 vs 显式 paper 的行为对表（验收门 g）
# --------------------------------------------------------------------------

class TestEndToEnd(SlotCase):
    def _run(self, name: str, extra: str):
        root = make_audit_project(self.tmp / name, extra)
        proc = cli("audit", str(root), "--json")
        payload = json.loads(proc.stdout)
        return proc.returncode, payload

    def test_explicit_paper_matches_default_modulo_domain_key(self):
        exit_plain, plain = self._run("e2e-plain", "")
        exit_slot, slot = self._run(
            "e2e-slot", '\n[checks]\npackages = ["paper"]\n')
        self.assertEqual(exit_plain, exit_slot)
        self.assertEqual(exit_plain, 1)   # 该项目带红（缺 source）
        for key in ("findings", "issues", "warnings", "hints"):
            self.assertEqual(strip_domain(plain[key]), strip_domain(slot[key]))
            if slot[key]:
                for item in slot[key]:
                    self.assertEqual(item.get("domain"), "paper")
        self.assertEqual(set(slot["summary"]) - set(plain["summary"]),
                         {"by_domain"})
        self.assertEqual(slot["summary"]["by_domain"], {"paper": {
            "red": len(plain["issues"]),
            "yellow": len(plain["warnings"]),
            "hints": len(plain["hints"]),
        }})

    def test_bare_checks_section_is_byte_identical_to_no_section(self):
        # §5.2：节存在但省 packages ⇒ 同无节（逐字节）
        exit_plain, plain = self._run("bare-plain", "")
        root = make_audit_project(self.tmp / "bare-section", "\n[checks]\n")
        proc = cli("audit", str(root), "--json")
        exit_bare = proc.returncode
        self.assertEqual(exit_plain, exit_bare)
        self.assertEqual(json.dumps(plain, ensure_ascii=False, sort_keys=True),
                         json.dumps(json.loads(proc.stdout),
                                    ensure_ascii=False, sort_keys=True))


# --------------------------------------------------------------------------
# 7. 每域一把冻结锁（裁定⑨）
# --------------------------------------------------------------------------

class TestEvidenceLockPath(SlotCase):
    def test_paper_keeps_legacy_lock_path(self):
        self.assertEqual(checks.evidence_lock_path(Path("/p"), "paper"),
                         Path("/p/audit/evidence.lock"))

    def test_empty_domain_defaults_to_paper(self):
        self.assertEqual(checks.evidence_lock_path(Path("/p"), ""),
                         Path("/p/audit/evidence.lock"))

    def test_other_domain_gets_own_lock(self):
        self.assertEqual(checks.evidence_lock_path(Path("/p"), "legal"),
                         Path("/p/audit/evidence-legal.lock"))


if __name__ == "__main__":
    unittest.main()
