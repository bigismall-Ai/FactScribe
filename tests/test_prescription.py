# -*- coding: utf-8 -*-
"""批 92：处方层 `factscribe prescribe` 的契约测试（全离线）。

规范：`docs/design/SPEC-PRESCRIPTION.md`。

覆盖：

* `--list` 六条、六段齐全、优先序与错误码绑定齐全；
* 五个既有判据码都能 `--for <CODE>` 查到；
* 处方文字不进 `style` 的 findings，`style` 也不导入处方模块；
* 冲突优先序：序号小的胜，被压制者输出「让位」；
* 每条处方的「验收命令」第一块可直接执行；
* 每条处方都有反例与「旧 → 新」示例。
"""
from __future__ import annotations

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
sys.path.insert(0, str(ROOT))

from factscribe.config import ConfigError  # noqa: E402
from factscribe.prescribe import (LEVELS, LEVEL_LABELS,  # noqa: E402
                                  SECTION_KEYS, PrescriptionError,
                                  load_prescriptions, load_priority,
                                  parse_rule, render_bundle,
                                  resolve_conflicts)
from factscribe.style import CODE_OF  # noqa: E402

# 既有判据码：每条都必须能被 `--for` 查到。
FIVE_CODES = ["HEADING_ECHO", "HEADING_MALFORMED", "TERM_FIRST_IN_HEADING",
              "DASH_PARENTHETICAL", "HEADING_SUBJECT_LOST",
              "EXPLAINER_DENSITY", "JUSTIFY_CHAIN",
              "LIGHT_VERB_NOMINALIZATION", "ZH_DE_STACK"]

ALL_NAMES = ["heading-shorten", "term-first-sentence", "dash-rewrite",
             "heading-malformed", "heading-subject-keep",
             "section-completeness", "drop-the-proof",
             "unbury-the-verb", "cut-the-de"]

PROJECT_TOML = """[project]
title = "处方层隔离测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""

# 故意触发多条文风判据：长标题、带冒号、首句复述、插入语破折号。
STYLE_BODY = r"""\section{提示词对机制：一个很长的解释性标题}

本节讨论提示词对机制。

模型——在十六次运行里都稳定——只改措辞。
"""


def cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", "prescribe", *args]
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


def cli_json(*args: str) -> dict:
    proc = cli(*args, "--json")
    if proc.returncode != 0:
        raise AssertionError("prescribe 退出码 %d：%s"
                             % (proc.returncode, proc.stderr))
    return json.loads(proc.stdout)


def make_project(base: Path) -> Path:
    root = Path(base)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "paperkit.toml").write_text(PROJECT_TOML, encoding="utf-8")
    (root / "sections" / "01_main.tex").write_text(STYLE_BODY, encoding="utf-8")
    return root


def run_style(root: Path) -> dict:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    proc = subprocess.run(
        [sys.executable, "-m", "factscribe", "style", str(root), "--json"],
        cwd=str(ROOT), env=env, capture_output=True, text=True)
    if proc.returncode not in (0, 3):
        raise AssertionError("style 退出码 %d：%s" % (proc.returncode, proc.stderr))
    return json.loads(proc.stdout)


def first_acceptance_command(text: str) -> str:
    """取「验收命令」段的第一块围栏代码。"""
    m = re.search(r"^## 验收命令\s*$([\s\S]*?)(?=^## |\Z)", text, re.M)
    if not m:
        raise AssertionError("缺少「验收命令」段")
    blocks = re.findall(r"```[A-Za-z0-9_-]*\n([\s\S]*?)```", m.group(1))
    if not blocks:
        raise AssertionError("「验收命令」段没有围栏代码")
    return blocks[0].strip()


# --------------------------------------------------------------------------
# 1. 清单与六段结构
# --------------------------------------------------------------------------

class TestListAndShape(unittest.TestCase):
    def test_list_returns_exactly_six(self):
        payload = cli_json("--list")
        names = [item["name"] for item in payload["prescriptions"]]
        self.assertEqual(sorted(names), sorted(ALL_NAMES))

    def test_every_prescription_has_all_six_sections(self):
        prescriptions = load_prescriptions()
        self.assertEqual(len(prescriptions), 9)
        for name, p in prescriptions.items():
            with self.subTest(name=name):
                self.assertEqual(set(p.fields), set(SECTION_KEYS))
                for key in SECTION_KEYS:
                    self.assertTrue(p.fields[key].strip(),
                                    "第 %r 段为空：%s" % (key, name))

    def test_list_json_has_fields_priority_and_codes(self):
        payload = cli_json("--list")
        for item in payload["prescriptions"]:
            with self.subTest(name=item["name"]):
                self.assertEqual(set(item["fields"]), set(SECTION_KEYS))
                self.assertTrue(item["target_codes"])
                self.assertIn(item["priority"]["level"], LEVELS)
                self.assertEqual(item["priority"]["number"],
                                 LEVELS[item["priority"]["level"]])
                self.assertTrue(item["path"].endswith("RULE.md"))

    def test_human_list_names_every_prescription(self):
        proc = cli("--list")
        self.assertEqual(proc.returncode, 0)
        for name in ALL_NAMES:
            self.assertIn(name, proc.stdout)

    def test_every_prescription_binds_at_least_one_code(self):
        for name, p in load_prescriptions().items():
            with self.subTest(name=name):
                self.assertTrue(p.target_codes)
                for code in p.target_codes:
                    self.assertRegex(code, r"^[A-Z][A-Z0-9_]+$")

    def test_five_existing_codes_are_covered(self):
        covered = set()
        for p in load_prescriptions().values():
            covered.update(p.target_codes)
        for code in FIVE_CODES:
            self.assertIn(code, covered)


# --------------------------------------------------------------------------
# 2. --for <错误码>
# --------------------------------------------------------------------------

class TestForCode(unittest.TestCase):
    def test_each_existing_code_resolves(self):
        for code in FIVE_CODES:
            with self.subTest(code=code):
                payload = cli_json("--for", code)
                names = [item["name"] for item in payload["prescriptions"]]
                self.assertTrue(names, "没有处方绑定 %s" % code)
                for item in payload["prescriptions"]:
                    self.assertIn(code, item["target_codes"])

    def test_heading_echo_maps_to_term_first_sentence(self):
        payload = cli_json("--for", "HEADING_ECHO")
        names = [item["name"] for item in payload["prescriptions"]]
        self.assertIn("term-first-sentence", names)

    def test_heading_subject_lost_maps_to_subject_keep(self):
        payload = cli_json("--for", "HEADING_SUBJECT_LOST")
        names = [item["name"] for item in payload["prescriptions"]]
        self.assertIn("heading-subject-keep", names)

    def test_unknown_code_is_empty_not_an_error(self):
        proc = cli("--for", "NO_SUCH_CODE")
        self.assertEqual(proc.returncode, 0)
        payload = cli_json("--for", "NO_SUCH_CODE")
        self.assertEqual(payload["prescriptions"], [])
        self.assertEqual(payload["exit"], 0)
        self.assertIn("没有处方", proc.stdout)

    def test_for_heading_malformed_only_matching(self):
        payload = cli_json("--for", "HEADING_MALFORMED")
        self.assertTrue(payload["prescriptions"])
        for item in payload["prescriptions"]:
            self.assertIn("HEADING_MALFORMED", item["target_codes"])


# --------------------------------------------------------------------------
# 3. CLI 原文输出与用法错
# --------------------------------------------------------------------------

class TestCliOutput(unittest.TestCase):
    def test_single_name_prints_rule_text_verbatim(self):
        for name in ALL_NAMES:
            with self.subTest(name=name):
                path = ROOT / "factscribe" / "patterns" / name / "RULE.md"
                expected = path.read_text(encoding="utf-8").strip()
                proc = cli(name)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), expected)

    def test_single_name_json_carries_text_and_sections(self):
        payload = cli_json("heading-shorten")
        self.assertEqual(len(payload["prescriptions"]), 1)
        item = payload["prescriptions"][0]
        self.assertEqual(item["name"], "heading-shorten")
        self.assertEqual(set(item["fields"]), set(SECTION_KEYS))
        self.assertIn("## 必做", item["text"])

    def test_unknown_name_exits_config_error(self):
        proc = cli("no-such-prescription")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no-such-prescription", proc.stderr)

    def test_no_arguments_exits_config_error(self):
        proc = cli()
        self.assertEqual(proc.returncode, 2)


# --------------------------------------------------------------------------
# 4. 与判据完全隔离
# --------------------------------------------------------------------------

class TestIsolation(unittest.TestCase):
    def test_prescription_text_never_appears_in_style_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_style(make_project(Path(tmp)))
        dump = json.dumps(payload["findings"], ensure_ascii=False)
        for name in ALL_NAMES:
            self.assertNotIn(name, dump)
        for marker in ("## 必做", "## 禁做", "## 验收命令"):
            self.assertNotIn(marker, dump)

    def test_style_finding_codes_stay_in_style_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_style(make_project(Path(tmp)))
        codes = {f["code"] for f in payload["findings"]}
        self.assertTrue(codes)
        self.assertLessEqual(codes, set(CODE_OF.values()))

    def test_style_works_without_patterns_data(self):
        """把 patterns/ 整块删掉再跑 style：findings、指标、退出码必须逐项相同。

        这是「处方不参与判据」的行为证明：判据不读处方数据，也不因处方
        在不在场而改变。
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            project = make_project(tmp / "project")
            normal = run_style(project)
            package = tmp / "nopatterns"
            shutil.copytree(ROOT / "factscribe", package / "factscribe",
                            ignore=shutil.ignore_patterns("__pycache__",
                                                          "patterns"))
            env = dict(os.environ, PYTHONPATH=str(package))
            proc = subprocess.run(
                [sys.executable, "-m", "factscribe", "style",
                 str(project), "--json"],
                cwd=str(package), env=env, capture_output=True, text=True)
            self.assertIn(proc.returncode, (0, 3), proc.stderr)
            stripped = json.loads(proc.stdout)
        self.assertEqual(stripped["findings"], normal["findings"])
        self.assertEqual(stripped["metrics"], normal["metrics"])
        self.assertEqual(stripped["exit"], normal["exit"])

    def test_prescribe_json_has_no_findings_or_scores(self):
        payload = cli_json("--list")
        for key in ("findings", "score", "scores", "grade", "passed",
                    "pass_rate"):
            self.assertNotIn(key, payload)
        self.assertEqual(payload["exit"], 0)
        self.assertEqual(payload["severity"], "ok")

    def test_style_sources_do_not_mention_prescribe(self):
        for name in ("style.py", "terms.py", "tide.py"):
            source = (ROOT / "factscribe" / name).read_text(encoding="utf-8")
            self.assertNotIn("prescribe", source.lower())


# --------------------------------------------------------------------------
# 5. 冲突优先序
# --------------------------------------------------------------------------

class TestPriority(unittest.TestCase):
    def test_priority_matches_spec(self):
        self.assertEqual(LEVELS, {"facts": 1, "structure": 2, "heading": 3,
                                  "term": 4, "style": 5})
        self.assertEqual(LEVEL_LABELS, {"facts": "事实与数字",
                                        "structure": "结构完整",
                                        "heading": "标题指向内容",
                                        "term": "术语首现解释",
                                        "style": "文句风格"})

    def test_conflict_pairs_have_different_numbers(self):
        config = load_priority()
        for pair in config.conflicts:
            with self.subTest(pair=pair):
                self.assertNotEqual(config.number_of(pair["a"]),
                                    config.number_of(pair["b"]))
                self.assertTrue(pair.get("reason"))

    def test_lower_number_wins_and_loser_yields(self):
        result = resolve_conflicts(["heading-shorten",
                                    "heading-subject-keep"])
        self.assertEqual(result["order"][0], "heading-subject-keep")
        self.assertIn("heading-shorten", result["suppressed"])
        info = result["suppressed"]["heading-shorten"]
        self.assertEqual(info["by"], "heading-subject-keep")
        self.assertLess(info["winner_number"], info["loser_number"])

    def test_rendered_bundle_explicitly_says_yield(self):
        text = render_bundle(["heading-shorten", "heading-subject-keep"])
        self.assertIn("让位", text)
        self.assertLess(text.index("heading-subject-keep"),
                        text.index("heading-shorten"))

    def test_non_conflicting_bundle_has_no_yield_note(self):
        text = render_bundle(["dash-rewrite", "term-first-sentence"])
        self.assertNotIn("让位", text)

    def test_cli_multi_name_shows_yield(self):
        proc = cli("heading-shorten", "heading-subject-keep")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("让位", proc.stdout)
        self.assertLess(proc.stdout.index("heading-subject-keep"),
                        proc.stdout.index("heading-shorten"))


# --------------------------------------------------------------------------
# 6. 验收命令、反例与示例
# --------------------------------------------------------------------------

class TestRulesQuality(unittest.TestCase):
    def test_every_acceptance_command_runs(self):
        for name, p in load_prescriptions().items():
            command = first_acceptance_command(p.text)
            with self.subTest(name=name, command=command):
                env = dict(os.environ, PYTHONPATH=str(ROOT))
                proc = subprocess.run(command, shell=True, cwd=str(ROOT),
                                      env=env, capture_output=True, text=True)
                self.assertIn(proc.returncode, (0, 3),
                              "%s 的验收命令退出码 %d：%s"
                              % (name, proc.returncode, proc.stderr[-500:]))

    def test_every_rule_has_counterexample(self):
        for name, p in load_prescriptions().items():
            with self.subTest(name=name):
                blocked = p.fields["禁做（含反例）"]
                self.assertIn("反例", blocked)
                self.assertIn("→", blocked)

    def test_every_rule_has_old_to_new_example(self):
        for name, p in load_prescriptions().items():
            with self.subTest(name=name):
                example = p.fields["改写示例（旧 → 新）"]
                self.assertIn("旧", example)
                self.assertIn("新", example)
                self.assertIn("→", example)

    def test_heading_shorten_keeps_contrast_object(self):
        text = load_prescriptions()["heading-shorten"].text
        self.assertIn("对比对象", text)
        self.assertIn("提示词对机制", text)
        self.assertIn("提示词", text)

    def test_heading_malformed_forbids_relation_substitution(self):
        text = load_prescriptions()["heading-malformed"].text
        self.assertIn("versus", text)
        self.assertIn("or", text)
        self.assertIn("关系词", text)

    def test_term_first_rejects_echo_filler_and_question(self):
        text = load_prescriptions()["term-first-sentence"].text
        for marker in ("复述", "垫话", "设问"):
            self.assertIn(marker, text)

    def test_section_completeness_transcribes_xtragpt_checkpoints(self):
        text = load_prescriptions()["section-completeness"].text
        self.assertIn("XtraGPT", text)
        self.assertIn("本节做什么", text)
        self.assertIn("结论", text)


# --------------------------------------------------------------------------
# 7. 解析器 fail-closed
# --------------------------------------------------------------------------

class TestParserFailClosed(unittest.TestCase):
    def _write_rule(self, tmp: Path, body: str) -> Path:
        path = tmp / "demo" / "RULE.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    GOOD = ("# demo\n\n## 治的判据\n\n- 错误码：HEADING_ECHO\n\n"
            "## 必做\n\n做事。\n\n## 禁做（含反例）\n\n反例：a → b\n\n"
            "## 改写示例（旧 → 新）\n\n旧 a → 新 b\n\n"
            "## 验收命令\n\n```bash\ntrue\n```\n")

    def test_missing_section_raises(self):
        broken = self.GOOD.replace("## 必做\n\n做事。\n\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_rule(Path(tmp), broken)
            with self.assertRaises(PrescriptionError):
                parse_rule(path)

    def test_missing_code_binding_raises(self):
        broken = self.GOOD.replace("- 错误码：HEADING_ECHO\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_rule(Path(tmp), broken)
            with self.assertRaises(PrescriptionError):
                parse_rule(path)

    def test_good_rule_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_rule(Path(tmp), self.GOOD)
            parsed = parse_rule(path)
        self.assertEqual(parsed.name, "demo")
        self.assertEqual(parsed.target_codes, ("HEADING_ECHO",))

    def test_prescription_error_is_config_error(self):
        self.assertTrue(issubclass(PrescriptionError, ConfigError))


# --------------------------------------------------------------------------
# 8. 规范与文档
# --------------------------------------------------------------------------

class TestSpecDoc(unittest.TestCase):
    def test_spec_lists_six_prescriptions_and_priority(self):
        text = (ROOT / "docs" / "design" / "SPEC-PRESCRIPTION.md").read_text(
            encoding="utf-8")
        for name in ALL_NAMES:
            self.assertIn(name, text)
        for label in LEVEL_LABELS.values():
            self.assertIn(label, text)
        self.assertIn("让位", text)
        self.assertIn("SECTION_INCOMPLETE", text)


if __name__ == "__main__":
    unittest.main()
