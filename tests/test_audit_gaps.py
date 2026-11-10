# -*- coding: utf-8 -*-
"""批 97：`audit` 三个已登记缺口（docs/release/KNOWN-GAPS.md 第二节）。

三条判据：
1. `INPUT_DYNAMIC`（红/5）：`\\input/\\include` 的目标含宏、`#`、嵌套花括号
   或为空——静态审计覆盖不了 ⇒ fail-closed 判红；
2. `EXPR_MISMATCH`（红/1）：fact 同时有 value 与 expr 时，`audit` 也要按
   `check` 的数值口径求值比对（此前只有 `check` 判）；
3. `BOUND_MISMATCH` 分诊：该行已绑定定量 fact，但数字不在其值域内 → 报
   `BOUND_MISMATCH`；真的没有 fact 可命中才报 `UNMATCHED_NUMBER`。

跑法（仓根）：env PYTHONPATH=src python3 -m unittest discover -s tests
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BIB_OK = """@inproceedings{chen2023,
  title = {A Paper},
  doi = {10.18653/v1/2023.emnlp-main.741}
}
"""

RESULT_TEXT = ("open 10/16 closed 8/16 alt 11/16; total 56.25%; "
               "scale 1234 and 53000; params 3500000; epoch 42 n 4\n")

FACT_A1 = """[[fact]]
id = "A1"
claim = "开臂 resolved（16 题）"
value = "10/16"
source = "results/raw.md"
locator = "§二"
confidence = "high"
derived_from = []
"""

FACT_A3 = """[[fact]]
id = "A3"
claim = "对比臂 resolved（16 题）"
value = "8/16"
source = "results/raw.md"
locator = "§二"
confidence = "high"
derived_from = []
"""

FACT_A2 = """[[fact]]
id = "A2"
claim = "合计准确率"
value = "56.25%"
source = "results/raw.md"
locator = "§三"
confidence = "med"
derived_from = ["A1", "A3"]
expr = "(A1.num + A3.num) / (A1.den + A3.den) * 100"
"""

FACTS = FACT_A1 + "\n" + FACT_A3 + "\n" + FACT_A2

FACT_42 = """[[fact]]
id = "X1"
claim = "epochs"
value = "42"
source = "results/raw.md"
locator = "§一"
confidence = "low"
derived_from = []
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inject_sha(facts: str, digest: str) -> str:
    return facts.replace('source = "results/raw.md"',
                         'source = "results/raw.md"\nsource_sha256 = "%s"' % digest)


def make_project(tmp, facts=FACTS, sections=None, results_text=RESULT_TEXT,
                 files=None):
    """最小 v1 项目：facts + sections + 人签清单，全部离线。"""
    root = Path(tmp)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    raw = root / "results" / "raw.md"
    raw.write_text(results_text, encoding="utf-8")
    digest = _sha(raw)
    (root / "facts" / "f.toml").write_text(
        _inject_sha(facts, digest), encoding="utf-8")
    for name, text in (sections or {}).items():
        dest = root / "sections" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    (root / "refs.bib").write_text(BIB_OK, encoding="utf-8")
    (root / "paperkit.toml").write_text(
        '[project]\ntitle = "t"\nauthors = ["a"]\n'
        'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
        'bib = "refs.bib"\nbuild = ""\n', encoding="utf-8")
    (root / "results" / "MANIFEST.toml").write_text(
        "[manifest]\nsigned_by = \"test-human\"\n"
        "signed_at = \"2026-11-07T00:00:00Z\"\nversion = 1\n\n[files]\n"
        '"results/raw.md" = "%s"\n' % digest, encoding="utf-8")
    for name, text in (files or {}).items():
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return root


def run(args, cwd=None):
    return subprocess.run([sys.executable, "-m", "factscribe"] + args,
                          capture_output=True, text=True, cwd=cwd or str(ROOT))


def run_json(args):
    proc = run(args)
    return proc.returncode, json.loads(proc.stdout)


def audit(root):
    return run_json(["audit", str(root), "--json"])


def codes(data):
    return [i["code"] for i in data["issues"]]


class TestInputDynamic(unittest.TestCase):
    """缺口一：动态闭包目标必须红（INPUT_DYNAMIC），静态目标行为不变。"""

    def _one(self, body, files=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": body}, files=files)
            return audit(root)

    def test_input_macro_target_is_red(self):
        code, data = self._one("\\input{\\chaptername}\n")
        self.assertEqual(code, 5, data)
        self.assertEqual(codes(data), ["INPUT_DYNAMIC"])
        issue = data["issues"][0]
        self.assertEqual(issue["severity"], "red")
        self.assertEqual(issue["token"], "\\chaptername")
        self.assertRegex(issue["location"], r"^sections/a\.tex:\d+$")

    def test_include_jobname_target_is_red(self):
        code, data = self._one("\\include{\\jobname}\n")
        self.assertEqual(code, 5, data)
        self.assertEqual(codes(data), ["INPUT_DYNAMIC"])
        self.assertEqual(data["issues"][0]["token"], "\\jobname")

    def test_hash_parameter_target_is_red(self):
        code, data = self._one("\\input{sections/sec#1}\n")
        self.assertEqual(code, 5, data)
        self.assertEqual(codes(data), ["INPUT_DYNAMIC"])
        self.assertEqual(data["issues"][0]["token"], "sections/sec#1")

    def test_nested_braces_target_is_red_and_keeps_raw_string(self):
        code, data = self._one("\\input{\\foo{bar}}\n")
        self.assertEqual(code, 5, data)
        self.assertEqual(codes(data), ["INPUT_DYNAMIC"])
        # 原始目标串必须完整，不能被截成 "\foo{bar"
        self.assertEqual(data["issues"][0]["token"], "\\foo{bar}")

    def test_empty_target_is_red(self):
        code, data = self._one("\\input{}\n")
        self.assertEqual(code, 5, data)
        self.assertEqual(codes(data), ["INPUT_DYNAMIC"])

    def test_unbalanced_target_is_red(self):
        code, data = self._one("\\input{foo\n")
        self.assertEqual(code, 5, data)
        self.assertEqual(codes(data), ["INPUT_DYNAMIC"])

    def test_static_target_without_tex_suffix_is_clean(self):
        code, data = self._one(
            "\\input{extra}\n\\cite{chen2023}\n",
            files={"sections/extra.tex": "no numbers here\n"})
        self.assertEqual(code, 0, data)
        self.assertEqual(data["issues"], [])

    def test_static_missing_target_keeps_old_code(self):
        code, data = self._one("\\input{nothere}\n")
        self.assertEqual(code, 5, data)
        self.assertEqual(codes(data), ["INPUT_TARGET_MISSING"])

    def test_commented_dynamic_input_is_ignored(self):
        code, data = self._one(
            "% \\input{\\macro}\n正文没有数字 \\cite{chen2023}\n")
        self.assertEqual(code, 0, data)
        self.assertEqual(data["issues"], [])

    def test_wrapper_macro_definition_is_not_dynamic(self):
        body = ("\\newcommand{\\extrainput}[1]{\\input{#1}}\n"
                "\\extrainput{extra}\n\\cite{chen2023}\n")
        code, data = self._one(
            body, files={"sections/extra.tex": "no numbers here\n"})
        self.assertEqual(code, 0, data)
        self.assertEqual(data["issues"], [])


class TestExprMismatchInAudit(unittest.TestCase):
    """缺口二：`audit` 也要判 expr 与 value 不符（此前只有 check 判）。"""

    def _one(self, facts, results_text=RESULT_TEXT):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=facts,
                                sections={"a.tex": "\\cite{chen2023}\n"},
                                results_text=results_text)
            return audit(root)

    def test_audit_flags_expr_mismatch_with_both_numbers_and_error(self):
        bad = FACT_A2.replace('"56.25%"', '"75%"')
        code, data = self._one(FACT_A1 + "\n" + FACT_A3 + "\n" + bad,
                               results_text=RESULT_TEXT + " 75%\n")
        self.assertEqual(code, 1, data)
        self.assertEqual(codes(data), ["EXPR_MISMATCH"])
        issue = data["issues"][0]
        self.assertEqual(issue["token"], "A2")
        self.assertRegex(issue["location"], r"^facts/f\.toml:\d+$")
        # 两侧数值与误差都要出现在报错里
        self.assertIn("56.25", issue["message"])
        self.assertIn("75", issue["message"])
        self.assertIn("误差", issue["message"])

    def test_audit_accepts_correct_expr(self):
        code, data = self._one(FACTS)
        self.assertEqual(code, 0, data)
        self.assertEqual(data["issues"], [])

    def test_explicit_tolerance_is_honoured(self):
        near = (FACT_A2.replace('"56.25%"', '"56.2500001%"')
                + 'expr_tolerance = "1e-6"\n')
        code, data = self._one(FACT_A1 + "\n" + FACT_A3 + "\n" + near,
                               results_text=RESULT_TEXT + " 56.2500001%\n")
        self.assertEqual(code, 0, data)
        self.assertEqual(data["issues"], [])

    def test_default_tolerance_still_catches_same_value_without_override(self):
        near = FACT_A2.replace('"56.25%"', '"56.2500001%"')
        code, data = self._one(FACT_A1 + "\n" + FACT_A3 + "\n" + near,
                               results_text=RESULT_TEXT + " 56.2500001%\n")
        self.assertEqual(code, 1, data)
        self.assertEqual(codes(data), ["EXPR_MISMATCH"])

    def test_invalid_expr_is_red_not_a_crash(self):
        broken = (FACT_A1 + "\n" + FACT_A3 + "\n"
                  + FACT_A2.replace("A3.num", "GHOST.num")
                  .replace("A3.den", "GHOST.den"))
        code, data = self._one(broken)
        self.assertEqual(code, 1, data)
        self.assertIn("EXPR_INVALID", codes(data))

    def test_fact_without_expr_is_unchanged(self):
        code, data = self._one(FACT_A1 + "\n" + FACT_A3)
        self.assertEqual(code, 0, data)
        self.assertEqual(data["issues"], [])


class TestBoundMismatchTriage(unittest.TestCase):
    """缺口三：只改“绑定后不符”的分类，红/黄级别与退出码不变。"""

    def _one(self, body, facts=FACTS):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=facts,
                                sections={"a.tex": body})
            return audit(root)

    def test_bound_line_wrong_number_is_bound_mismatch(self):
        # 同一行绑定 A1，数字 42 在另一句里——行级绑定仍是 A1
        code, data = self._one("10 道\\fact{A1}。42 道\n")
        self.assertEqual(code, 1, data)
        self.assertEqual(codes(data), ["BOUND_MISMATCH"])
        self.assertEqual(data["issues"][0]["token"], "42")
        self.assertEqual(data["issues"][0]["severity"], "red")
        self.assertNotIn("UNMATCHED_NUMBER", codes(data))

    def test_bound_line_multiple_wrong_numbers_all_bound_mismatch(self):
        code, data = self._one("10 道\\fact{A1}。42 道和 99 道\n")
        self.assertEqual(code, 1, data)
        self.assertEqual(codes(data), ["BOUND_MISMATCH", "BOUND_MISMATCH"])
        self.assertEqual({i["token"] for i in data["issues"]}, {"42", "99"})

    def test_no_fact_at_all_still_unmatched_number(self):
        code, data = self._one("noise 1422 here\n")
        self.assertEqual(code, 1, data)
        self.assertEqual(codes(data), ["UNMATCHED_NUMBER"])
        self.assertNotIn("BOUND_MISMATCH", codes(data))

    def test_number_known_globally_but_not_bound_stays_yellow(self):
        # 42 在账上（X1），但没有内联绑定：仍按旧口径黄 UNBOUND_NUMBER
        facts = FACT_A1 + "\n" + FACT_42
        code, data = self._one(
            "10 道\\fact{A1}。we run 42 epochs \\cite{chen2023}\n", facts=facts)
        self.assertEqual(code, 3, data)
        self.assertEqual(data["issues"], [])
        self.assertEqual([w["code"] for w in data["warnings"]], ["UNBOUND_NUMBER"])

    def test_exit_code_and_severity_unchanged(self):
        old_code, old = self._one("42 道\n", facts=FACT_A1)
        new_code, new = self._one("10 道\\fact{A1}。42 道\n", facts=FACT_A1)
        self.assertEqual(old_code, new_code)          # 都是红 1
        self.assertEqual(old["issues"][0]["severity"],
                         new["issues"][0]["severity"])
        self.assertEqual(old["issues"][0]["code"], "UNMATCHED_NUMBER")


class TestMinimalRegression(unittest.TestCase):
    """回归锁：examples/minimal 仍 exit 1，恰好两处红。"""

    def test_examples_minimal_still_exactly_two_red(self):
        root = ROOT / "examples" / "minimal"
        code, data = audit(root)
        self.assertEqual(code, 1, data)
        self.assertEqual(data["summary"]["red"], 2)
        self.assertEqual(codes(data), ["UNMATCHED_NUMBER", "MISSING_CITE"])
        self.assertEqual([i["token"] for i in data["issues"]],
                         ["47.3", "ghost2024"])


class TestStableReportFields(unittest.TestCase):
    """新错误码在 JSON / findings / 人读报表里的字段必须稳定。"""

    def test_input_dynamic_json_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "\\input{\\macro}\n"})
            code, data = audit(root)
        self.assertEqual(code, 5)
        issue = data["issues"][0]
        for key in ("severity", "code", "message", "location", "token"):
            self.assertIn(key, issue)
        self.assertEqual(issue["severity"], "red")
        self.assertIn(issue, data["findings"])
        self.assertRegex(issue["location"], r"^sections/a\.tex:\d+$")
        self.assertEqual(issue["token"], "\\macro")

    def test_expr_mismatch_json_fields(self):
        bad = FACT_A2.replace('"56.25%"', '"75%"')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, facts=FACT_A1 + "\n" + FACT_A3 + "\n" + bad,
                sections={"a.tex": "no numbers here\n"},
                results_text=RESULT_TEXT + " 75%\n")
            code, data = audit(root)
        self.assertEqual(code, 1)
        issue = data["issues"][0]
        for key in ("severity", "code", "message", "location", "token"):
            self.assertIn(key, issue)
        self.assertEqual(issue["severity"], "red")
        self.assertIn("误差", issue["message"])

    def test_human_report_prints_new_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "\\include{\\jobname}\n"})
            proc = run(["audit", str(root)])
        self.assertEqual(proc.returncode, 5, proc.stdout)
        self.assertIn("INPUT_DYNAMIC", proc.stdout)


if __name__ == "__main__":
    unittest.main()
