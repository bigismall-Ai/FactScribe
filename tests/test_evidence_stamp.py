# -*- coding: utf-8 -*-
"""批 131：证据钢印 `[evidence]` 的契约测试（全离线）。

规范：``docs/design/SPEC-EVIDENCE-STAMP.md``。

覆盖：

* 声明了但本节没引用 → ``REQUIRED_EVIDENCE_MISSING`` 红，退出码 1；
* 声明了且引用 → 绿；
* 未声明的节缺事实 → 不报；
* 注释里的 ``\\fact{}`` 不算引用；
* 缺失消息带「节 / id / claim / value」；
* before 有、after 无 → ``EVIDENCE_DROPPED`` 红，不依赖声明；
* 删数字换成 most/nearly 的固定夹具 → 必须红；
* ``--diff`` 的滤重不得吞掉红判据；
* ``review`` 把丢证据算进拒绝面；
* ``brief`` 节清单带「必须引用的事实」列与 id，未声明写 ``—``；
* ``NUMERAL_DENSITY`` 默认阈值为 ``null``（不判），显式配阈值仍生效；
* ``polish --plan`` 在阈值为 ``null`` 时不出该类条目；
* ``[evidence]`` 值非法 → 配置错（退出码 2）。
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

from factscribe.brief import build_brief  # noqa: E402
from factscribe.brief import payload as brief_payload  # noqa: E402
from factscribe.brief import render as render_brief  # noqa: E402
from factscribe.config import load_config, load_sections  # noqa: E402
from factscribe.polish import build_plan  # noqa: E402
from factscribe.style import analyze, load_style_rules  # noqa: E402

PROJECT_TOML = """[project]
title = "证据钢印测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""

FACTS_TOML = """
[[fact]]
id = "B1"
claim = "第一批盲测的捕获数"
value = "0/12"

[[fact]]
id = "B2"
claim = "第七批盲测的捕获数"
value = "11/12"

[[fact]]
id = "B3"
claim = "预注册门槛"
value = "10/12"
"""

SECTION_BOTH = r"""\section{Discussion}

The first sealed set caught nothing, 0/12\fact{B1}, and the seventh caught
11/12\fact{B2}. The two runs share every detector in the implementation.
What differs is what the author had written down before the runs.
A short line follows. The ledger, the schema, and the closed table of codes
all existed before the first failure rather than after it, and the reader can
check each of them against the receipt.
"""

SECTION_B1_ONLY = r"""\section{Discussion}

The first sealed set caught nothing, 0/12\fact{B1}. The seventh set is
described elsewhere in this paper. What differs is what the author had
written down before the runs. A short line follows. The ledger, the schema,
and the closed table of codes all existed before the first failure rather
than after it, and the reader can check each of them against the receipt.
"""

SECTION_PLAIN = r"""\section{Intro}

The argument below names one surface at a time and keeps each claim next to
the receipt that supports it. A short line follows. The reader can stop at any
paragraph and check the source of every number without reading the rest.
"""

# 固定夹具：before 用绑定写死两个数字，after 换成 nearly/most 的定性说法。
EMPTIED_BEFORE = r"""\section{Discussion}

The first sealed set caught nothing, 0/12\fact{B1}, and the seventh caught
11/12\fact{B2}, and the two runs share every detector in the implementation.
What differs is what the author and the implementer had written down before
the runs. A short line follows. The ledger and the closed table of codes all
existed before the first failure rather than after it.
"""

EMPTIED_AFTER = r"""\section{Discussion}

The first sealed set caught nothing and the seventh caught nearly every
planted defect. The two runs share every detector in the implementation.
What differs is what the author and the implementer had written down before
the runs. A short line follows. Most of the sealed sets behaved the same way,
and some of them still carried a clean report.
"""

DENSE = "\\section{Measurement}\n\n" + " ".join(
    ["The quick brown fox jumps over the lazy dog again %d." % (i + 1)
     for i in range(10)]) + "\n"


def cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True)


def cli_json(*args: str) -> tuple[subprocess.CompletedProcess, dict]:
    proc = cli(*args, "--json")
    data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return proc, data


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_project(base: Path, sections: dict[str, str],
                 evidence: dict | None = None,
                 evidence_raw: str | None = None,
                 rules: str | None = None) -> Path:
    """最小 v1 项目：sections 是 {相对项目根的路径: 正文}。"""
    root = Path(base)
    text = PROJECT_TOML
    if evidence_raw is not None:
        text += "\n" + evidence_raw.strip() + "\n"
    elif evidence is not None:
        lines = ["[evidence]"]
        for key, ids in evidence.items():
            lines.append('"%s" = [%s]'
                         % (key, ", ".join('"%s"' % i for i in ids)))
        text += "\n" + "\n".join(lines) + "\n"
    write(root / "paperkit.toml", text)
    write(root / "facts" / "facts.toml", FACTS_TOML)
    for rel, body in sections.items():
        write(root / rel, body)
    if rules is not None:
        write(root / "style-rules.toml", rules)
    return root


def run_style(project: Path):
    cfg = load_config(project)
    rules, rules_path = load_style_rules(cfg.root)
    return analyze(cfg, load_sections(cfg), rules, rules_path=rules_path)


def codes(result) -> set:
    return {f.code for f in result.findings}


def evidence_findings(result, code: str) -> list:
    return [f for f in result.findings if f.code == code]


class EvidenceCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def body_project(self, name: str, **kwargs) -> Path:
        sections = kwargs.pop("sections", None) or {
            "sections/01_intro.tex": SECTION_PLAIN,
            "sections/02_body.tex": SECTION_BOTH,
        }
        return make_project(self.tmp / name, sections, **kwargs)


# --------------------------------------------------------------------------
# 1. REQUIRED_EVIDENCE_MISSING
# --------------------------------------------------------------------------

class TestRequiredEvidence(EvidenceCase):
    def test_declared_but_not_cited_is_red_exit_1(self):
        project = self.body_project(
            "missing", sections={
                "sections/01_intro.tex": SECTION_PLAIN,
                "sections/02_body.tex": SECTION_B1_ONLY},
            evidence={"02_body": ["B1", "B2"]})
        proc, data = cli_json("style", str(project))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(data["severity"], "red")
        hits = [f for f in data["findings"]
                if f["code"] == "REQUIRED_EVIDENCE_MISSING"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "red")
        self.assertEqual(hits[0]["file"], "sections/02_body.tex")

    def test_message_carries_section_id_claim_and_value(self):
        project = self.body_project(
            "message", sections={
                "sections/01_intro.tex": SECTION_PLAIN,
                "sections/02_body.tex": SECTION_B1_ONLY},
            evidence={"02_body": ["B1", "B2"]})
        result = run_style(project)
        hit = evidence_findings(result, "REQUIRED_EVIDENCE_MISSING")[0]
        self.assertIn("02_body", hit.text)
        self.assertIn("B2", hit.text)
        self.assertIn("第七批盲测的捕获数", hit.text)
        self.assertIn("11/12", hit.text)

    def test_declared_and_cited_is_green(self):
        project = self.body_project(
            "green", evidence={"02_body": ["B1", "B2"]})
        proc, data = cli_json("style", str(project))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("REQUIRED_EVIDENCE_MISSING",
                         {f["code"] for f in data["findings"]})

    def test_undeclared_section_without_facts_is_not_reported(self):
        project = self.body_project(
            "undeclared", sections={
                "sections/01_intro.tex": SECTION_PLAIN,
                "sections/02_body.tex": SECTION_BOTH,
                "sections/03_extra.tex": SECTION_PLAIN},
            evidence={"02_body": ["B1", "B2"]})
        result = run_style(project)
        self.assertNotIn("REQUIRED_EVIDENCE_MISSING", codes(result))

    def test_fact_inside_comment_does_not_count(self):
        body = SECTION_B1_ONLY + "\n% 11/12\\fact{B2} 只存在于注释里\n"
        project = self.body_project(
            "comment", sections={
                "sections/01_intro.tex": SECTION_PLAIN,
                "sections/02_body.tex": body},
            evidence={"02_body": ["B1", "B2"]})
        result = run_style(project)
        hits = evidence_findings(result, "REQUIRED_EVIDENCE_MISSING")
        self.assertEqual([f.text.split("（")[0].split()[-1] for f in hits],
                         ["B2"])

    def test_unknown_declared_section_is_readout_not_red(self):
        project = self.body_project(
            "typo", evidence={"02_body": ["B1", "B2"],
                              "09_typo": ["B3"]})
        result = run_style(project)
        self.assertNotIn("REQUIRED_EVIDENCE_MISSING", codes(result))
        self.assertEqual(
            result.metric_details.get("evidence_sections_unknown"),
            ["09_typo"])


# --------------------------------------------------------------------------
# 2. EVIDENCE_DROPPED
# --------------------------------------------------------------------------

class TestEvidenceDropped(EvidenceCase):
    def make_pair(self, after_body: str, *, evidence: dict | None = None,
                  before_body: str = SECTION_BOTH):
        before = make_project(
            self.tmp / "before",
            {"sections/02_body.tex": before_body})
        after = make_project(
            self.tmp / "after", {"sections/02_body.tex": after_body},
            evidence=evidence)
        return before, after

    def test_before_has_after_does_not_is_red_exit_1(self):
        before, after = self.make_pair(SECTION_B1_ONLY)
        proc, data = cli_json("style", str(after), "--diff", str(before))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        hits = [f for f in data["findings"]
                if f["code"] == "EVIDENCE_DROPPED"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "red")
        self.assertIn("B2", hits[0]["text"])

    def test_no_drop_is_green(self):
        before, after = self.make_pair(SECTION_BOTH)
        proc, data = cli_json("style", str(after), "--diff", str(before))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("EVIDENCE_DROPPED",
                         {f["code"] for f in data["findings"]})

    def test_dropped_does_not_need_evidence_declaration(self):
        before, after = self.make_pair(SECTION_B1_ONLY)
        self.assertNotIn("[evidence]", (after / "paperkit.toml").read_text())
        result = analyze(
            load_config(after),
            load_sections(load_config(after)),
            load_style_rules(after)[0],
            before=(load_config(before), load_sections(load_config(before))))
        self.assertIn("EVIDENCE_DROPPED", codes(result))

    def test_numbers_replaced_by_most_and_nearly_is_red(self):
        # 实测复现：数字被删，换成 nearly every / most / some。
        before = make_project(
            self.tmp / "loop-before",
            {"sections/09_discussion.tex": EMPTIED_BEFORE})
        after = make_project(
            self.tmp / "loop-after",
            {"sections/09_discussion.tex": EMPTIED_AFTER},
            evidence={"09_discussion": ["B1", "B2"]})
        proc, data = cli_json("style", str(after), "--diff", str(before))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        found = {f["code"] for f in data["findings"]}
        self.assertIn("EVIDENCE_DROPPED", found)
        self.assertIn("REQUIRED_EVIDENCE_MISSING", found)
        dropped = {f["text"] for f in data["findings"]
                   if f["code"] == "EVIDENCE_DROPPED"}
        self.assertTrue(any("B1" in text for text in dropped))

    def test_diff_filtering_does_not_swallow_red_gate(self):
        # before 也没有 B2：基线分析同样报 REQUIRED_EVIDENCE_MISSING；
        # --diff 的滤重必须保留红判据，否则 diff 模式比单跑更松。
        before = make_project(
            self.tmp / "filter-before",
            {"sections/02_body.tex": SECTION_B1_ONLY},
            evidence={"02_body": ["B1", "B2"]})
        after = make_project(
            self.tmp / "filter-after",
            {"sections/02_body.tex": SECTION_B1_ONLY},
            evidence={"02_body": ["B1", "B2"]})
        proc, data = cli_json("style", str(after), "--diff", str(before))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("REQUIRED_EVIDENCE_MISSING",
                      {f["code"] for f in data["findings"]})

    def test_review_rejects_on_dropped_evidence(self):
        before, after = self.make_pair(SECTION_B1_ONLY)
        proc = cli("review", "--before", str(before), "--after", str(after))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("EVIDENCE_DROPPED", proc.stdout)


# --------------------------------------------------------------------------
# 3. brief 同步
# --------------------------------------------------------------------------

class TestBriefEvidenceColumn(EvidenceCase):
    def test_brief_lists_required_evidence_column(self):
        project = self.body_project(
            "brief", evidence={"02_body": ["B1", "B2"]})
        brief = build_brief(project)
        text = render_brief(brief)
        self.assertIn("必须引用的事实", text)
        row = next(line for line in text.splitlines()
                   if "02_body.tex" in line)
        self.assertIn("B1", row)
        self.assertIn("B2", row)

    def test_brief_writes_dash_without_declaration(self):
        project = self.body_project("brief-none")
        brief = build_brief(project)
        text = render_brief(brief)
        row = next(line for line in text.splitlines()
                   if "01_intro.tex" in line)
        self.assertTrue(row.rstrip().endswith("| — |"), row)
        data = brief_payload(brief)
        rows = {s["file"]: s["evidence"] for s in data["sections"]}
        self.assertEqual(rows["sections/01_intro.tex"], [])

    def test_brief_payload_carries_declared_ids(self):
        project = self.body_project(
            "brief-json", evidence={"02_body": ["B1", "B2"]})
        data = brief_payload(build_brief(project))
        rows = {s["file"]: s["evidence"] for s in data["sections"]}
        self.assertEqual(rows["sections/02_body.tex"], ["B1", "B2"])


# --------------------------------------------------------------------------
# 4. NUMERAL_DENSITY 降级
# --------------------------------------------------------------------------

class TestNumeralDensityDefaultNull(EvidenceCase):
    def test_default_threshold_is_null_and_does_not_fire(self):
        project = make_project(self.tmp / "dense",
                               {"sections/01_body.tex": DENSE})
        result = run_style(project)
        self.assertIsNone(result.thresholds["numeral_density"])
        self.assertNotIn("NUMERAL_DENSITY", codes(result))
        self.assertGreater(result.metrics["numeral_density"], 40.0)

    def test_explicit_threshold_still_fires(self):
        project = make_project(
            self.tmp / "dense-explicit",
            {"sections/01_body.tex": DENSE},
            rules="[thresholds]\nnumeral_density = 40\n")
        result = run_style(project)
        self.assertEqual(result.thresholds["numeral_density"], 40)
        self.assertIn("NUMERAL_DENSITY", codes(result))

    def test_polish_plan_has_no_numeral_entry_when_null(self):
        project = make_project(self.tmp / "dense-plan",
                               {"sections/01_body.tex": DENSE})
        plan = build_plan(project)
        self.assertNotIn("NUMERAL_DENSITY",
                         {entry.code for entry in plan.entries})

    def test_polish_plan_keeps_numeral_entry_when_configured(self):
        project = make_project(
            self.tmp / "dense-plan-explicit",
            {"sections/01_body.tex": DENSE},
            rules="[thresholds]\nnumeral_density = 40\n")
        plan = build_plan(project)
        entries = {e.code: e for e in plan.entries}
        self.assertIn("NUMERAL_DENSITY", entries)
        self.assertEqual(entries["NUMERAL_DENSITY"].prescription,
                         "thin-the-numbers")


# --------------------------------------------------------------------------
# 5. 配置校验
# --------------------------------------------------------------------------

class TestEvidenceConfig(EvidenceCase):
    def test_non_array_value_is_config_error(self):
        project = self.body_project(
            "bad", evidence_raw='[evidence]\n"02_body" = "B1"\n')
        proc, _data = cli_json("style", str(project))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_non_string_entry_is_config_error(self):
        project = self.body_project(
            "bad-entry", evidence_raw='[evidence]\n"02_body" = [1, 2]\n')
        proc, _data = cli_json("style", str(project))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
