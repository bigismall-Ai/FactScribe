# -*- coding: utf-8 -*-
"""批 58：多码原则 + 两条新判据（FACT_UNUSED_IN_SPAN / DUPLICATE_VALUE）。

覆盖 SPEC-V3.0 §8 的多码原则与 §8.1／§11.1 的两条判据：

1. 正文只剩指代、数字落在 `\\appendix` → `FACT_UNUSED_IN_SPAN`（黄）＋
   `ASSERTION_DRIFT`（红）——「一个现象两个码」不再只报第一个；
2. 正文句带数字、附录只是同值复述 → 良性，零告警；
3. `role` 是正文角色、标记只在附录 → `FACT_OUT_OF_SPAN` ＋ `ASSERTION_DRIFT`；
4. 两条 fact 的 value 归一化后相同、claim 不同 → `DUPLICATE_VALUE`（黄，exit 3）；
5. 三条豁免：`dup_ok = true`、组内 `supersedes`、派生值（`derived_from`）。

所有样例都在临时目录里合成，不读任何封存盲测集。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TOML = """[project]
name = "synthetic"
root_tex = "sections/main.tex"
facts = "facts"
bib = "refs.bib"
level = "l1"
number_locale = "period"
"""

MAIN = """\\documentclass{article}
\\begin{document}

%s

\\end{document}
"""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_project(root: Path, body: str, facts: list[dict]) -> Path:
    """合成一个 l1 的 V3 项目：每条 fact 一个 run + 回执。"""
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(TOML, encoding="utf-8")
    (root / "sections" / "main.tex").write_text(MAIN % body, encoding="utf-8")
    (root / "refs.bib").write_text("", encoding="utf-8")

    blocks = ['schema = "paperkit-fact/3.0"']
    for idx, fact in enumerate(facts, start=1):
        run_id = fact.pop("_run", "run-%02d" % idx)
        run_dir = root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        src = run_dir / "result.json"
        src.write_text(json.dumps({"run_id": run_id,
                                   "summary": {"rate": 0.625}}), encoding="utf-8")
        (run_dir / "record.json").write_text(json.dumps(
            {"run_id": run_id, "source": "runs/%s/result.json" % run_id,
             "source_sha256": "sha256:" + _digest(src),
             "facts": [fact["id"]]}), encoding="utf-8")
        blocks.append("[[fact]]")
        for key, value in fact.items():
            if key == "display":
                blocks.append("display = [%s]" % ", ".join(
                    "'%s'" % v for v in value))
            elif isinstance(value, bool):
                blocks.append("%s = %s" % (key, "true" if value else "false"))
            elif isinstance(value, list):
                blocks.append("%s = [%s]" % (key, ", ".join(
                    '"%s"' % v for v in value)))
            else:
                blocks.append('%s = "%s"' % (key, value))
        blocks.append('source = "runs/%s/result.json"' % run_id)
        blocks.append('run_id = "%s"' % run_id)
        blocks.append('source_sha256 = "sha256:%s"' % _digest(src))
        blocks.append('confidence = "high"')
        blocks.append("")
    (root / "facts" / "facts.toml").write_text("\n".join(blocks), encoding="utf-8")
    return root


def audit(root: Path):
    proc = subprocess.run([sys.executable, "-m", "factscribe", "audit",
                           str(root), "--json"],
                          cwd=str(ROOT), capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError(proc.stdout[:400] + proc.stderr[:400])
    codes = {str(f.get("code")) for f in data.get("findings", [])}
    return proc.returncode, codes


BODY_POINTER = """\\section{Results}
The resolved rate is \\fact{A1} as detailed in Appendix~\\ref{app:rate}.

\\appendix
\\section{Rate details}\\label{app:rate}
On assembly, the resolved rate reaches \\fact{A1}{62.5\\%} under the frozen harness.
"""

BODY_BENIGN = """\\section{Results}
On assembly, the resolved rate reaches \\fact{A1}{62.5\\%} under the frozen harness.

\\appendix
\\section{Rate details}\\label{app:rate}
The same rate is restated here: \\fact{A1}{62.5\\%}.
"""

BODY_MOVED = """\\section{Results}
The resolved rate is reported in Appendix~\\ref{app:rate}.

\\appendix
\\section{Rate details}\\label{app:rate}
On assembly, the resolved rate reaches \\fact{A1}{62.5\\%} under the frozen harness.
"""

FACT_A1 = {"id": "A1", "claim": "On assembly, the resolved rate is 62.5%.",
           "value": "62.5%", "display": ["62.5\\%"], "role": "results"}


class FactUnusedInSpanTest(unittest.TestCase):
    def test_pointer_only_body_is_unused_in_span(self):
        """正文只剩指代、数字只在附录 → FACT_UNUSED_IN_SPAN（黄）＋ASSERTION_DRIFT。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), BODY_POINTER, [dict(FACT_A1)])
            code, codes = audit(root)
        self.assertIn("FACT_UNUSED_IN_SPAN", codes)
        self.assertIn("ASSERTION_DRIFT", codes)      # 多码：一个现象全报
        self.assertNotEqual(code, 0)

    def test_body_carries_number_and_appendix_repeats_is_benign(self):
        """良性近邻：正文句带数字，附录只是同值复述 → 零告警。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), BODY_BENIGN, [dict(FACT_A1)])
            code, codes = audit(root)
        self.assertEqual(codes, set())
        self.assertEqual(code, 0)

    def test_moved_to_appendix_reports_out_of_span(self):
        """role 是正文角色、标记只在附录 → FACT_OUT_OF_SPAN ＋ ASSERTION_DRIFT。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), BODY_MOVED, [dict(FACT_A1)])
            code, codes = audit(root)
        self.assertIn("FACT_OUT_OF_SPAN", codes)
        self.assertIn("ASSERTION_DRIFT", codes)
        self.assertEqual(code, 1)


BODY_DUPLICATE = """\\section{Results}
On assembly, the resolved rate reaches \\fact{A1}{62.5\\%} under the frozen harness.

\\section{Second batch}
On the second batch, the resolved rate is again \\fact{A2}{62.5\\%} under the same harness.
"""


def _fact(fid: str, claim: str, value: str, display: str, **extra) -> dict:
    fact = {"id": fid, "claim": claim, "value": value, "display": [display]}
    fact.update(extra)
    return fact


class DuplicateValueTest(unittest.TestCase):
    def test_two_facts_same_value_different_claim_is_yellow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), BODY_DUPLICATE, [
                _fact("A1", "On assembly, the resolved rate is 62.5%.",
                      "62.5%", "62.5\\%"),
                _fact("A2", "On the second batch, the resolved rate is 62.5%.",
                      "62.5%", "62.5\\%"),
            ])
            code, codes = audit(root)
        self.assertIn("DUPLICATE_VALUE", codes)
        self.assertEqual(code, 3)

    def test_normalised_spellings_still_count_as_same_value(self):
        """`62.5%` 与 `0.625` 归一后同值：换写法绕不过去。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp),
                                BODY_DUPLICATE.replace("62.5\\%} under the same",
                                                       "0.625} under the same"),
                                [
                                    _fact("A1", "On assembly, the resolved rate is 62.5%.",
                                          "62.5%", "62.5\\%"),
                                    _fact("A2", "On the second batch, the resolved rate is 0.625.",
                                          "0.625", "0.625"),
                                ])
            code, codes = audit(root)
        self.assertIn("DUPLICATE_VALUE", codes)
        self.assertEqual(code, 3)

    def test_dup_ok_exempts_the_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), BODY_DUPLICATE, [
                _fact("A1", "On assembly, the resolved rate is 62.5%.",
                      "62.5%", "62.5\\%"),
                _fact("A2", "On the second batch, the resolved rate is 62.5%.",
                      "62.5%", "62.5\\%", dup_ok=True),
            ])
            code, codes = audit(root)
        self.assertNotIn("DUPLICATE_VALUE", codes)
        self.assertEqual(code, 0)

    def test_supersedes_exempts_the_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), BODY_DUPLICATE, [
                _fact("A1", "On assembly, the resolved rate is 62.5%.",
                      "62.5%", "62.5\\%"),
                _fact("A2", "On the second batch, the resolved rate is 62.5%.",
                      "62.5%", "62.5\\%", supersedes=["A1"]),
            ])
            code, codes = audit(root)
        self.assertNotIn("DUPLICATE_VALUE", codes)

    def test_derived_fact_is_not_a_second_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), BODY_DUPLICATE, [
                _fact("A1", "On assembly, the resolved rate is 62.5%.",
                      "62.5%", "62.5\\%"),
                _fact("A2", "On the second batch, the same rate.",
                      "62.5%", "62.5\\%", derived_from=["A1"], expr="A1"),
            ])
            code, codes = audit(root)
        self.assertNotIn("DUPLICATE_VALUE", codes)

    def test_same_claim_same_value_is_not_duplicate_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), BODY_DUPLICATE, [
                _fact("A1", "On assembly, the resolved rate is 62.5%.",
                      "62.5%", "62.5\\%"),
                _fact("A2", "On assembly, the resolved rate is 62.5%.",
                      "62.5%", "62.5\\%"),
            ])
            code, codes = audit(root)
        self.assertNotIn("DUPLICATE_VALUE", codes)


if __name__ == "__main__":
    unittest.main()
