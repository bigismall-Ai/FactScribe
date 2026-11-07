# -*- coding: utf-8 -*-
"""paperkit 测试：全部离线（--resolve 不测联网路径，只测它的降级分支靠 mock）。

跑法（仓根）：python3 -m unittest discover -s tests -v
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import paperkit  # noqa: E402

CLI = ROOT / "paperkit.py"

BIB_OK = """@inproceedings{chen2023,
  title = {A Paper},
  doi = {10.18653/v1/2023.emnlp-main.741}
}
"""

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
"""

FACTS = FACT_A1 + "\n" + FACT_A3 + "\n" + FACT_A2


def make_project(tmp, facts=FACTS, sections=None, bib=BIB_OK, build=""):
    root = Path(tmp)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "results" / "raw.md").write_text("open 10/16 closed 8/16\n", encoding="utf-8")
    (root / "facts" / "f.toml").write_text(facts, encoding="utf-8")
    if sections:
        for name, text in sections.items():
            (root / "sections" / name).write_text(text, encoding="utf-8")
    if bib is not None:
        (root / "refs.bib").write_text(bib, encoding="utf-8")
    (root / "paperkit.toml").write_text(
        '[project]\ntitle = "t"\nauthors = ["a"]\n'
        'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
        'bib = "refs.bib"\nbuild = "%s"\n' % build,
        encoding="utf-8")
    return root


def run(args, cwd=None):
    return subprocess.run([sys.executable, str(CLI)] + args,
                          capture_output=True, text=True, cwd=cwd)


def run_json(args):
    p = run(args)
    return p.returncode, json.loads(p.stdout)


class TestNumberNormalization(unittest.TestCase):
    def test_thousands_separator(self):
        self.assertEqual(paperkit.number_key("1,234"), "1234")

    def test_trailing_zero(self):
        self.assertEqual(paperkit.number_key("0.90"), paperkit.number_key("0.9"))

    def test_percent(self):
        self.assertEqual(paperkit.number_key("10", None, True), "0.1")

    def test_percent_equivalent_forms(self):
        # 数字层：10% 与 10\% 都归一成 0.1
        self.assertEqual(paperkit.number_key("10", None, True), "0.1")
        a = paperkit.scan_tex(r"准确率 10\% 而已")
        na = [n["key"] for n in paperkit._extract_numbers(a.masked, "x")]
        self.assertEqual(na, ["0.1"])
        # 账目层：value="10%" 同时接受 0.1 与裸 10
        keys = paperkit.fact_value_keys("10%")
        self.assertIn("0.1", keys)
        self.assertIn("10", keys)

    def test_bare_percent_starts_comment_like_tex(self):
        # 裸 % 在 TeX 里就是注释起点：后面的数字不该进审计
        s = paperkit.scan_tex("达到 10% 但后面 99 是注释")
        self.assertEqual([n["token"] for n in paperkit._extract_numbers(s.masked, "x")], ["10"])

    def test_kilo(self):
        self.assertEqual(paperkit.number_key("53", "k"), "53000")

    def test_mega(self):
        self.assertEqual(paperkit.number_key("3.5", "M"), "3500000")

    def test_fraction_value_accepts_parts_and_quotient(self):
        keys = paperkit.fact_value_keys("10/16")
        self.assertIn("10", keys)
        self.assertIn("16", keys)
        self.assertIn("0.625", keys)

    def test_range_value_accepts_both_ends(self):
        keys = paperkit.fact_value_keys("10--16")
        self.assertIn("10", keys)
        self.assertIn("16", keys)


class TestTexMasking(unittest.TestCase):
    def nums(self, tex):
        s = paperkit.scan_tex(tex)
        return [n["token"] for n in paperkit._extract_numbers(s.masked, tex)]

    def test_comment_ignored(self):
        self.assertEqual(self.nums("% 早期版本 99.9\\% 是错的\n正文 3 个"), ["3"])

    def test_cite_ref_label_input_ignored(self):
        tex = (r"\cite{a2020,b2021} \ref{sec:2} \label{tab:3} \input{sections/01-x} 7")
        self.assertEqual(self.nums(tex), ["7"])

    def test_command_name_digits_ignored(self):
        self.assertEqual(self.nums(r"\foo2 后面 5 个"), ["5"])

    def test_tabular_columns_ignored(self):
        tex = r"\begin{tabular}{p{2cm}l}10\end{tabular}"
        self.assertEqual(self.nums(tex), ["10"])

    def test_includegraphics_option_ignored(self):
        self.assertEqual(self.nums(r"\includegraphics[width=3.5cm]{fig-2024}"), [])

    def test_fact_marker_ignored_and_bound(self):
        s = paperkit.scan_tex(r"解决 10 道\fact{A1}")
        self.assertEqual([n["token"] for n in paperkit._extract_numbers(s.masked, "x")], ["10"])
        self.assertEqual(s.bindings.get(1), ["A1"])

    def test_wiki_marker(self):
        s = paperkit.scan_tex(r"解决 10 道 [[fact:A1]]")
        self.assertEqual([n["token"] for n in paperkit._extract_numbers(s.masked, "x")], ["10"])
        self.assertEqual(s.markers, [("A1", 1)])

    def test_escaped_percent_is_not_comment(self):
        self.assertEqual(self.nums(r"10\% 与 20\%"), ["10%", "20%"])


class TestCheck(unittest.TestCase):
    def test_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(data["summary"]["red"], 0)
            self.assertEqual(data["summary"]["facts"], 3)

    def test_duplicate_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1 + "\n" + FACT_A1)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            codes = [i["code"] for i in data["issues"]]
            self.assertIn("DUPLICATE_ID", codes)

    def test_missing_source(self):
        bad = FACT_A1.replace("results/raw.md", "results/nope.md")
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=bad)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("MISSING_SOURCE", [i["code"] for i in data["issues"]])

    def test_bad_confidence(self):
        bad = FACT_A1.replace('"high"', '"very-high"')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=bad)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("BAD_CONFIDENCE", [i["code"] for i in data["issues"]])

    def test_bad_derived_from(self):
        bad = FACT_A2.replace('["A1", "A3"]', '["A1", "A9"]')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1 + "\n" + FACT_A3 + "\n" + bad)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("BAD_DERIVED_FROM", [i["code"] for i in data["issues"]])

    def test_conflict_listed_but_not_red(self):
        rival = FACT_A1.replace('"A1"', '"A9"').replace('"10/16"', '"11/16"')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1 + "\n" + rival)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 0)          # 冲突不是错
            self.assertEqual(len(data["conflicts"]), 1)
            self.assertIn("A1", data["conflicts"][0]["ids"])

    def test_supersedes_silences_conflict(self):
        new = (FACT_A1.replace('"A1"', '"A9"').replace('"10/16"', '"11/16"')
               .replace("derived_from = []", 'derived_from = []\nsupersedes = ["A1"]'))
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1 + "\n" + new)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(data["conflicts"], [])


class TestAudit(unittest.TestCase):
    def test_clean_numbers_and_cites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, sections={"a.tex": "16 题里解决 10 道\\fact{A1}，见 \\cite{chen2023}。"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 0, data)
            self.assertEqual(data["summary"]["red"], 0)

    def test_unmatched_number_has_file_line_column_and_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "编造的数字 47.3 在这里\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertEqual(len(data["issues"]), 1)
            issue = data["issues"][0]
            self.assertEqual(issue["code"], "UNMATCHED_NUMBER")
            self.assertEqual(issue["token"], "47.3")
            self.assertRegex(issue["location"], r"^sections/a\.tex:1:\d+$")
            self.assertIn("编造的数字", issue["context"])

    def test_percent_and_fraction_and_kilo_matched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, sections={"a.tex": "56.25\\% 与 10/16 与 53k 与 1,234 与 3.5M\n"},
                # 加两条只为提供 1234 / 53000 / 3500000
                facts=FACTS + """
[[fact]]
id = "B1"
claim = "规模"
value = "1234--53000"
source = "results/raw.md"
locator = "§四"
confidence = "low"
derived_from = []

[[fact]]
id = "B2"
claim = "总参数"
value = "3500000"
source = "results/raw.md"
locator = "§四"
confidence = "low"
derived_from = []
""")
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 0, data)

    def test_bound_line_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "16 题里解决 10 道\\fact{A1}\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 0, data)
            self.assertEqual(data["summary"]["numbers_bound"], 2)

    def test_bound_line_mismatch_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "16 题里解决 42 道\\fact{A1}\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)
            codes = [i["code"] for i in data["issues"]]
            self.assertEqual(codes, ["BOUND_MISMATCH"])
            self.assertEqual(data["issues"][0]["token"], "42")

    def test_unknown_fact_marker_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "10 道\\fact{A99}\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("UNKNOWN_FACT_MARKER", [i["code"] for i in data["issues"]])

    def test_missing_cite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "见 \\cite{ghost2024}。\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertEqual([i["code"] for i in data["issues"]], ["MISSING_CITE"])
            self.assertEqual(data["issues"][0]["token"], "ghost2024")
            self.assertRegex(data["issues"][0]["location"], r"^sections/a\.tex:1:\d+$")

    def test_bib_entry_without_stable_id(self):
        bib = BIB_OK + "\n@misc{noid2021,\n  title = {No Id}\n}\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "见 \\cite{noid2021}。\n"}, bib=bib)
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("BIB_NO_STABLE_ID", [i["code"] for i in data["issues"]])

    def test_unused_fact_is_hint_not_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, sections={"a.tex": "16 题里解决 10 道\\fact{A1}\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 0, data)
            hints = [h["code"] for h in data["hints"]]
            self.assertIn("UNUSED_FACT", hints)

    def test_resolve_failure_degrades_to_unverified(self):
        # 进程内打桩：subprocess 里改不了全局，故直接调 run_audit
        orig_ax, orig_doi = paperkit._resolve_arxiv, paperkit._resolve_doi
        paperkit._resolve_arxiv = lambda _id: ("unverified", "离线（测试桩）")
        paperkit._resolve_doi = lambda _id: ("unverified", "离线（测试桩）")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = make_project(tmp, sections={"a.tex": "见 \\cite{chen2023}。\n"})
                cfg = paperkit.load_config(root)
                red, hints, summary, resolved = paperkit.run_audit(
                    cfg, paperkit.load_facts(cfg), paperkit.load_sections(cfg), resolve=True)
                self.assertEqual(red, [])
                self.assertEqual(resolved[0]["status"], "unverified")
                self.assertIn("CITE_UNVERIFIED", [h.code for h in hints])
        finally:
            paperkit._resolve_arxiv, paperkit._resolve_doi = orig_ax, orig_doi


class TestNotSilentlyPassing(unittest.TestCase):
    def test_missing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = run(["audit", tmp])
            self.assertEqual(p.returncode, 2)
            self.assertIn("paperkit.toml", p.stderr)

    def test_empty_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts="# 空账\n", sections={"a.tex": "10\n"})
            for cmd in ("check", "audit", "matrix"):
                p = run([cmd, str(root)])
                self.assertEqual(p.returncode, 2, cmd)
                self.assertIn("facts 为空", p.stderr)

    def test_empty_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            for cmd in ("audit", "matrix"):
                p = run([cmd, str(root)])
                self.assertEqual(p.returncode, 2, cmd)
                self.assertIn("sections 为空", p.stderr)

    def test_missing_bib(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "10\\fact{A1}\n"}, bib=None)
            p = run(["audit", str(root)])
            self.assertEqual(p.returncode, 2)
            self.assertIn("refs.bib", p.stderr)

    def test_missing_project_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            (root / "paperkit.toml").write_text('[project]\ntitle = "t"\n', encoding="utf-8")
            p = run(["check", str(root)])
            self.assertEqual(p.returncode, 2)
            self.assertIn("project.sections", p.stderr)


class TestMatrix(unittest.TestCase):
    def test_three_rows_and_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                sections={
                    "a.tex": "16 题里解决 10 道\\fact{A1}\n",
                    "b.tex": "对比臂 8 道\\fact{A3}，合计 56.25\\%\\fact{A2}\n",
                })
            code, data = run_json(["matrix", str(root), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(len(data["rows"]), 3)
            text = (root / "audit" / "matrix.md").read_text(encoding="utf-8")
            self.assertIn("被引用次数", text)
            row = {r["id"]: r for r in data["rows"]}
            self.assertEqual(row["A1"]["citations"], 1)
            self.assertEqual(row["A1"]["sections"], ["sections/a.tex"])
            self.assertEqual(row["A2"]["citations"], 1)
            self.assertEqual(text.count("| high |"), 2)
            self.assertEqual(text.count("| med |"), 1)


class TestBuild(unittest.TestCase):
    def test_build_runs_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, build="sh -c 'echo built > out.txt'")
            code, data = run_json(["build", str(root), "--json"])
            self.assertEqual(code, 0, data)
            self.assertTrue((root / "out.txt").is_file())

    def test_build_failure_is_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, build="false")
            p = run(["build", str(root)])
            self.assertEqual(p.returncode, 1)
            self.assertIn("构建失败", p.stdout)

    def test_build_empty_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, build="")
            code, data = run_json(["build", str(root), "--json"])
            self.assertEqual(code, 0)
            self.assertIn("跳过编译", data["output"])


class TestExampleAcceptance(unittest.TestCase):
    """SPEC §6：最小项目必须 check 绿、audit 恰好 2 红、matrix 3 行。"""

    def setUp(self):
        self.root = ROOT / "examples" / "minimal"

    def test_check_green(self):
        code, data = run_json(["check", str(self.root), "--json"])
        self.assertEqual(code, 0, data)
        self.assertEqual(data["summary"]["red"], 0)

    def test_audit_exactly_two(self):
        code, data = run_json(["audit", str(self.root), "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(data["summary"]["red"], 2)
        self.assertEqual([i["code"] for i in data["issues"]],
                         ["UNMATCHED_NUMBER", "MISSING_CITE"])
        self.assertEqual(data["issues"][0]["token"], "47.3")
        self.assertEqual(data["issues"][1]["token"], "ghost2024")

    def test_matrix_three_rows(self):
        code, data = run_json(["matrix", str(self.root), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(len(data["rows"]), 3)


if __name__ == "__main__":
    unittest.main()
