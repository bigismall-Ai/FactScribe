# -*- coding: utf-8 -*-
"""批 115：润色工单 `factscribe polish` 的契约测试（全离线）。

覆盖：

* 手册六节齐全、九条处方全点名、三种验收结论、五条以上禁做反例；
* 手册里出现的每个错误码都在 ``style.CODE_OF`` 的全集里（防写错名）；
* 工作单对 ``style`` 的每一条命中都给条目，且顺序符合处方优先序；
* 没有处方的码逐字标 ``无处方：只提示，不许为它改句子``；
* 有处方的码，处方名能在 ``prescribe --list`` 里查到；
* ``--json`` 结构稳定，输出逐字节确定。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.polish import (CONSTRAINTS, NO_RX_CONSTRAINT,  # noqa: E402
                               NO_RX_LEVEL, NO_RX_NOTE, PLAYBOOK_FILE,
                               build_entries, no_prescription_codes,
                               playbook_text)
from factscribe.prescribe import (LEVELS, load_prescriptions,  # noqa: E402
                                  prescriptions_for)
from factscribe.style import CODE_OF, Finding  # noqa: E402

PROJECT_TOML = """[project]
title = "润色工单测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""

# 故意触发标题（过长/带冒号）、首句复述与插入语破折号四个命中。
STYLE_BODY = r"""\section{提示词对机制：一次很长的对照实验说明}

本节讨论提示词对机制的影响。

模型——在十六次运行里都稳定——只改措辞。
"""

# 干净正文：不触发任何判据。
CLEAN_BODY = r"""\section{对照实验}

这里给出一个可检验的结论：两组读数在十六次运行里相差不超过一。

全部读数由脚本逐次落盘，判卷只看落盘的读数。
"""

# 任务点名的无处方码（全部来自 style 的注册表，处方层不为它们提供改法）。
GIVEN_NO_RX = [
    "RHYTHM_PLATEAU", "SENTENCE_UNIFORMITY", "REPEATED_OPENER",
    "CONNECTIVE_DENSITY", "PARAGRAPH_TEMPLATE", "HEDGE_STACK",
    "EMPTY_ADJECTIVE", "COLLOQUIAL_TRIAD", "TERM_UNREGISTERED",
    "NOMINALIZATION_RATE", "ZH_ASPECT_ZHE", "ZH_COLLOCATION_REDUNDANCY",
    "ZH_DANG_WHEN",
]

CODE_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")


def cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        cwd=str(cwd or ROOT), env=env, capture_output=True, text=True)


def cli_json(*args: str, cwd: Path | None = None) -> dict:
    proc = cli(*args, "--json", cwd=cwd)
    if proc.returncode not in (0, 3):
        raise AssertionError("退出码 %d：%s" % (proc.returncode, proc.stderr))
    return json.loads(proc.stdout)


def make_project(base: Path, body: str = STYLE_BODY) -> Path:
    root = Path(base)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "paperkit.toml").write_text(PROJECT_TOML, encoding="utf-8")
    (root / "sections" / "01_main.tex").write_text(body, encoding="utf-8")
    return root


def fake_result(findings=(), advisories=(), info=()):
    return SimpleNamespace(findings=list(findings), advisories=list(advisories),
                           info=list(info))


def finding(code, file="sections/a.tex", line=1, text="x"):
    return Finding(code=code, file=file, line=line, text=text,
                   suggestion="")


# --------------------------------------------------------------------------
# 1. 手册
# --------------------------------------------------------------------------

class TestPlaybook(unittest.TestCase):
    def setUp(self):
        self.text = playbook_text()

    def test_has_six_numbered_sections(self):
        headings = re.findall(r"^## (\d)\. ", self.text, re.M)
        self.assertEqual(headings, ["1", "2", "3", "4", "5", "6"])
        # 六节之外不再有二级标题（手册结构冻结）。
        self.assertEqual(len(re.findall(r"^## ", self.text, re.M)), 6)

    def test_names_all_nine_prescriptions(self):
        names = sorted(load_prescriptions())
        self.assertEqual(len(names), 9)
        for name in names:
            with self.subTest(name=name):
                self.assertIn("`%s`" % name, self.text)

    def test_three_review_verdicts_with_exit_codes(self):
        for verdict in ("通过", "需复核", "拒绝"):
            with self.subTest(verdict=verdict):
                self.assertIn(verdict, self.text)
        for code in ("退出码 0", "退出码 3", "退出码 1"):
            self.assertIn(code, self.text)
        self.assertIn("review --before", self.text)

    def test_at_least_five_forbidden_rewrites_with_counterexamples(self):
        self.assertGreaterEqual(self.text.count("反例"), 5)
        markers = [
            "摘要。",                              # 复述标题
            "`提示词对机制` → `提示词`",            # 删对比对象
            "Prompt versus mechanism",            # 替换关系词
            "相关工作里，",                        # 垫话
            "什么是",                              # 设问开头
            "最后一臂的，是五次运行的任务的。",      # 为过规则改僵
        ]
        for marker in markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)

    def test_every_counterexample_wrong_form_is_present(self):
        """每个反例的「错误写法」都要在手册里可核对（不靠模型猜）。"""
        bad_forms = [
            "摘要。",                              # 复述标题
            "`提示词`",                            # 删对比对象
            "Prompt or mechanism",                # 替换关系词
            "相关工作里，预注册很重要。",            # 垫话
            "什么是预注册？",                       # 设问开头
            "最后一臂的，是五次运行的任务的。",      # 为过规则改僵
            "结论、一项草稿阶段的干预",              # 换标点过关
            "一项草稿阶段`",                        # 只删词留残句
        ]
        for bad in bad_forms:
            with self.subTest(bad=bad):
                self.assertIn(bad, self.text)

    def test_forbids_passing_by_swapping_punctuation(self):
        """被判定违规的标点不许换成另一种标点蒙混过关（批 116 反规避）。"""
        self.assertIn("禁止换标点过关", self.text)
        # 反例：冒号换顿号，标题结构没变。
        self.assertIn(
            "`结论：一项草稿阶段的干预` → `结论、一项草稿阶段的干预`",
            self.text)
        # 正例：冒号标题改写成名词短语。
        self.assertIn(
            "`结论：一项草稿阶段的干预` → `草稿阶段的干预`",
            self.text)
        self.assertIn("顿号", self.text)

    def test_forbids_passing_by_swapping_prepositions(self):
        """冒号标题不许用 as/with/for/of 介词顶替（批 118 英文实测）。"""
        self.assertIn("禁止换标点过关", self.text)
        self.assertIn("禁止换介词过关", self.text)
        for prep in ("`as`", "`with`", "`for`", "`of`"):
            with self.subTest(prep=prep):
                self.assertIn(prep, self.text)
        # 反例：三条英文介词顶替。
        bad_forms = [
            "`Design: A Contract Before a Judge` → "
            "`Design as a Contract Before a Judge`",
            "`Method: Indicators, Bidirectional Rules, and Stage` → "
            "`Method with Indicators, Bidirectional Rules, and Stage`",
            "`Experiment: Three Comparisons and a Blind Protocol` → "
            "`Experiment with Three Comparisons and a Blind Protocol`",
        ]
        for bad in bad_forms:
            with self.subTest(bad=bad):
                self.assertIn(bad, self.text)

    def test_has_english_noun_phrase_positive_examples(self):
        """英文正解至少两条：删类别词，重写成名词短语（批 118）。"""
        positives = [
            "`Results: The Gate Wins on Drafts and Loses on Polished Text` → "
            "`Gate Wins on Drafts, Loses on Polished Text`",
            "`Conclusion: A Draft-Stage Intervention` → "
            "`A Draft-Stage Intervention`",
            "`Design: A Contract Before a Judge` → `Contract-first design`",
        ]
        for good in positives:
            with self.subTest(good=good):
                self.assertIn(good, self.text)
        self.assertGreaterEqual(len(positives), 2)

    def test_forbids_deleting_words_without_rewrite(self):
        """压长度不许只删词留残句（批 116 反规避）。"""
        self.assertIn("禁止只删词不重写", self.text)
        self.assertIn("残句", self.text)
        # 反例：删掉中心词，只剩定语。
        self.assertIn(
            "`结论：一项草稿阶段的干预` → `一项草稿阶段`", self.text)
        # 正例：删掉类别词，剩下的仍是完整名词短语。
        self.assertIn(
            "`结论：一项草稿阶段的干预` → `一项草稿阶段的干预`", self.text)

    def test_every_code_in_playbook_exists_in_style_registry(self):
        # 全集 = style 注册表 ∪ 处方绑定的码；手册不许出现这两个来源之外的码。
        universe = set(CODE_OF.values())
        for prescription in load_prescriptions().values():
            universe |= set(prescription.target_codes)
        found = set(CODE_RE.findall(self.text))
        self.assertTrue(found, "手册应当提到具体错误码")
        unknown = sorted(found - universe)
        self.assertEqual(unknown, [],
                         "手册里出现不存在的错误码：%s" % unknown)

    def test_names_the_six_protected_surfaces(self):
        for token in ("\\fact{", "数字", "\\cite", "公式", "表格行",
                      "\\label", "\\ref", "\\eqref"):
            with self.subTest(token=token):
                self.assertIn(token, self.text)

    def test_stop_rule_is_explicit(self):
        self.assertIn("3 轮", self.text)
        self.assertIn("改不动", self.text)

    def test_no_prescription_rule_is_quoted_exactly(self):
        self.assertIn(NO_RX_NOTE, self.text)

    def test_print_writes_the_data_file_byte_for_byte(self):
        proc = cli("polish", "--print")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, playbook_text())
        self.assertEqual(proc.stdout,
                         PLAYBOOK_FILE.read_text(encoding="utf-8"))

    def test_print_needs_no_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = cli("polish", "--print", cwd=Path(tmp))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("润色操作手册", proc.stdout)


# --------------------------------------------------------------------------
# 2. 命中 → 条目（单元）
# --------------------------------------------------------------------------

class TestEntriesUnit(unittest.TestCase):
    def test_no_prescription_codes_are_marked_and_never_given_a_fix(self):
        entries = build_entries(fake_result(
            findings=[finding("RHYTHM_PLATEAU"), finding("SENTENCE_UNIFORMITY")],
            advisories=[finding("RHYTHM_PLATEAU", line=2)]))
        self.assertEqual(len(entries), 3)  # 同 (码, 文件, 行) 不重复
        for entry in entries:
            with self.subTest(code=entry.code):
                self.assertEqual(entry.prescription, NO_RX_NOTE)
                self.assertEqual(entry.constraint, NO_RX_CONSTRAINT)
                self.assertIn("不许为它改句子", entry.constraint)

    def test_prescribed_codes_resolve_to_their_prescription(self):
        entries = build_entries(fake_result(findings=[
            finding("HEADING_TOO_LONG"), finding("DASH_PARENTHETICAL"),
            finding("ZH_DE_STACK"), finding("HEADING_ECHO")]))
        got = {e.code: e.prescription for e in entries}
        self.assertEqual(got["HEADING_TOO_LONG"], "heading-shorten")
        self.assertEqual(got["DASH_PARENTHETICAL"], "dash-rewrite")
        self.assertEqual(got["ZH_DE_STACK"], "cut-the-de")
        self.assertEqual(got["HEADING_ECHO"], "term-first-sentence")

    def test_constraint_table_covers_every_prescription(self):
        self.assertEqual(sorted(CONSTRAINTS), sorted(load_prescriptions()))
        for name, text in CONSTRAINTS.items():
            with self.subTest(name=name):
                self.assertTrue(text.strip())
                self.assertTrue(text.endswith("。"))

    def test_entries_sorted_by_priority_then_location(self):
        entries = build_entries(fake_result(
            findings=[finding("DASH_PARENTHETICAL", line=9),
                      finding("RHYTHM_PLATEAU", line=1),
                      finding("HEADING_TOO_LONG", line=5),
                      finding("HEADING_MALFORMED", line=2)],
            advisories=[finding("SENTENCE_UNIFORMITY", line=1)]))
        levels = [e.prescription for e in entries]
        expected = ["heading-malformed", "heading-shorten",
                    "dash-rewrite", NO_RX_NOTE, NO_RX_NOTE]
        self.assertEqual(levels, expected)
        self.assertEqual([e.index for e in entries], [1, 2, 3, 4, 5])

    def test_no_prescription_universe_matches_style_registry(self):
        codes = no_prescription_codes()
        self.assertEqual(sorted(codes), sorted(set(codes)))
        self.assertTrue(set(codes) <= set(CODE_OF.values()))
        for code in GIVEN_NO_RX:
            with self.subTest(code=code):
                self.assertIn(code, codes)
                self.assertEqual(prescriptions_for(code), [])

    def test_every_style_code_is_either_prescribed_or_marked(self):
        prescriptions = load_prescriptions()
        for code in sorted(set(CODE_OF.values())):
            with self.subTest(code=code):
                matched = prescriptions_for(code, prescriptions)
                if matched:
                    self.assertTrue(matched)
                else:
                    self.assertIn(code, no_prescription_codes(prescriptions))


# --------------------------------------------------------------------------
# 3. 工作单（CLI，用临时项目）
# --------------------------------------------------------------------------

class TestPlanCLI(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = make_project(Path(self._tmp.name) / "paper")

    def plan_json(self) -> dict:
        return cli_json("polish", "--plan", str(self.project))

    def test_plan_covers_every_style_finding(self):
        style = cli_json("style", str(self.project))
        plan = self.plan_json()
        planned = {(e["code"], e["file"], e["line"]) for e in plan["entries"]}
        self.assertTrue(style["findings"], "夹具应当触发判据")
        for item in style["findings"]:
            key = (item["code"], item["file"], item["line"])
            with self.subTest(code=item["code"], line=item["line"]):
                self.assertIn(key, planned)
        self.assertEqual(plan["summary"]["total"], len(plan["entries"]))
        self.assertEqual(plan["summary"]["total"],
                         plan["summary"]["prescribed"]
                         + plan["summary"]["no_prescription"])

    def test_plan_order_follows_priority(self):
        plan = self.plan_json()
        prescriptions = load_prescriptions()
        ranks = []
        for entry in plan["entries"]:
            if entry["prescription"] == NO_RX_NOTE:
                ranks.append(NO_RX_LEVEL)
                continue
            matched = prescriptions_for(entry["code"], prescriptions)
            self.assertTrue(matched)
            ranks.append(matched[0].level_number)
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual([e["index"] for e in plan["entries"]],
                         list(range(1, len(plan["entries"]) + 1)))

    def test_plan_prescription_names_exist_in_prescribe_list(self):
        listed = {item["name"] for item in cli_json("prescribe", "--list")
                  ["prescriptions"]}
        plan = self.plan_json()
        used = {e["prescription"] for e in plan["entries"]}
        self.assertTrue(used)
        for name in used - {NO_RX_NOTE}:
            with self.subTest(name=name):
                self.assertIn(name, listed)

    def test_plan_json_shape_is_stable(self):
        payload = self.plan_json()
        self.assertEqual(
            set(payload),
            {"schema_version", "tool", "version", "command", "status",
             "severity", "exit", "project", "summary", "entries"})
        self.assertEqual(payload["command"], "polish")
        self.assertEqual(payload["exit"], 0)
        self.assertEqual(set(payload["summary"]),
                         {"total", "prescribed", "no_prescription"})
        for entry in payload["entries"]:
            with self.subTest(index=entry["index"]):
                self.assertEqual(
                    set(entry),
                    {"index", "file", "line", "code", "prescription",
                     "constraint"})
                self.assertIsInstance(entry["line"], int)
                self.assertTrue(entry["constraint"].strip())

    def test_plan_output_is_byte_deterministic(self):
        first = cli("polish", "--plan", str(self.project))
        second = cli("polish", "--plan", str(self.project))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        first_json = cli("polish", "--plan", str(self.project), "--json")
        second_json = cli("polish", "--plan", str(self.project), "--json")
        self.assertEqual(first_json.stdout, second_json.stdout)

    def test_clean_project_gets_an_empty_plan(self):
        clean = make_project(Path(self._tmp.name) / "clean", CLEAN_BODY)
        proc = cli("polish", "--plan", str(clean))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("没有命中", proc.stdout)
        payload = cli_json("polish", "--plan", str(clean))
        self.assertEqual(payload["entries"], [])
        self.assertEqual(payload["summary"]["total"], 0)

    def test_plan_defaults_to_current_directory(self):
        proc = cli("polish", "--plan", cwd=self.project)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("条目：", proc.stdout)

    def test_polish_without_mode_is_a_usage_error(self):
        proc = cli("polish")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--print", proc.stderr)

    def test_print_and_plan_are_mutually_exclusive(self):
        proc = cli("polish", "--print", "--plan", str(self.project))
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
