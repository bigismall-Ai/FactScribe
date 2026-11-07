# -*- coding: utf-8 -*-
"""paperkit 测试：全部离线（--resolve 不测联网路径，只测它的降级分支靠 mock）。

跑法（仓根）：python3 -m unittest discover -s tests -v
"""

import hashlib
import json
import re
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

# 原始产物：所有 fixture 的 fact.value 数字都必须字面出现在这里（value 回查闸）
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


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _inject_sha(facts, digest):
    return facts.replace('source = "results/raw.md"',
                         'source = "results/raw.md"\nsource_sha256 = "%s"' % digest)


def _write_manifest(root, files, signed=True):
    lines = ["[manifest]"]
    if signed:
        lines += ['signed_by = "test-human"', 'signed_at = "2026-11-07T00:00:00Z"']
    lines += ["version = 1", "", "[files]"]
    for rel, digest in sorted(files.items()):
        lines.append('"%s" = "%s"' % (rel, digest))
    (root / "results" / "MANIFEST.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_project(tmp, facts=FACTS, sections=None, bib=BIB_OK, build="",
                 results_text=RESULT_TEXT, manifest=True):
    root = Path(tmp)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    raw = root / "results" / "raw.md"
    raw.write_text(results_text, encoding="utf-8")
    digest = _sha(raw)
    (root / "facts" / "f.toml").write_text(_inject_sha(facts, digest), encoding="utf-8")
    if sections:
        for name, text in sections.items():
            dest = root / "sections" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
    if bib is not None:
        (root / "refs.bib").write_text(bib, encoding="utf-8")
    (root / "paperkit.toml").write_text(
        '[project]\ntitle = "t"\nauthors = ["a"]\n'
        'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
        'bib = "refs.bib"\nbuild = "%s"\n' % build,
        encoding="utf-8")
    if manifest:
        _write_manifest(root, {"results/raw.md": digest})
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

    def test_conflict_listed_and_yellow(self):
        rival = FACT_A1.replace('"A1"', '"A9"').replace('"10/16"', '"11/16"')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1 + "\n" + rival)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 3)          # v1：账本自相矛盾＝黄，不判死但不再算绿
            self.assertEqual(len(data["conflicts"]), 1)
            self.assertIn("A1", data["conflicts"][0]["ids"])
            self.assertIn("LEDGER_CONFLICT", [w["code"] for w in data["warnings"]])

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
                tmp,
                sections={"a.tex": "56.25\\% 与 10/16 与 53k 与 1,234 与 3.5M\\fact{A1,A3,A2,B1,B2}\n"},
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
            self.assertEqual(data["summary"]["numbers_unbound"], 0)

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
                red, yellow, hints, summary, resolved = paperkit.run_audit(
                    cfg, paperkit.load_facts(cfg), paperkit.load_sections(cfg), resolve=True)
                self.assertEqual(red, [])
                self.assertEqual(resolved[0]["status"], "unverified")
                self.assertIn("CITE_UNVERIFIED", [h.code for h in hints])
                self.assertIn("CITE_UNVERIFIED", [y.code for y in yellow])
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


class TestV1InlineBinding(unittest.TestCase):
    """闸 1：正文数字必须内联绑定，且是该 fact.value 里的 token。"""

    def test_unbound_number_is_yellow_not_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_42, sections={"a.tex": "we run 42 epochs\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 3, data)                 # 黄：回得到账但没绑定
            self.assertEqual(data["issues"], [])
            self.assertIn("UNBOUND_NUMBER", [w["code"] for w in data["warnings"]])

    def test_strict_upgrades_yellow_to_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_42, sections={"a.tex": "we run 42 epochs\n"})
            code, _ = run_json(["audit", str(root), "--json", "--strict"])
            self.assertEqual(code, 1)

    def test_unbound_number_with_no_fact_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_42, sections={"a.tex": "noise 1422 here\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertEqual([i["code"] for i in data["issues"]], ["UNMATCHED_NUMBER"])

    def test_token_equality_not_substring(self):
        # value=42 不能吃下 1422 / 4242 / 4.2e-5
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, facts=FACT_42,
                sections={"a.tex": "1422 42 4242 4.2e-5\\fact{X1}\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertEqual({i["code"] for i in data["issues"]}, {"BOUND_MISMATCH"})
            self.assertEqual({i["token"] for i in data["issues"]},
                             {"1422", "4242", "4.2e-5"})

    def test_config_fact_cannot_be_global_whitelist(self):
        cfg_fact = FACT_42.replace('claim = "epochs"', 'claim = "epochs"\nkind = "config"')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=cfg_fact, sections={"a.tex": "we run 42 epochs\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)        # config 不进全局值域 -> 未绑定即红
            self.assertEqual([i["code"] for i in data["issues"]], ["UNMATCHED_NUMBER"])


class TestV1SourceAnchoring(unittest.TestCase):
    """闸 2：source_sha256 + 人签清单 + value 回查。"""

    def test_sha_mismatch_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "16 题里解决 10 道\\fact{A1}\n"})
            (root / "results" / "raw.md").write_text("tampered\n", encoding="utf-8")
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)
            codes = {i["code"] for i in data["issues"]}
            self.assertIn("SOURCE_SHA256_MISMATCH", codes)
            self.assertIn("MANIFEST_HASH_MISMATCH", codes)

    def test_missing_sha_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            p = root / "facts" / "f.toml"
            p.write_text(re.sub(r"^source_sha256 = .*$\n?", "", p.read_text(encoding="utf-8"),
                                flags=re.M), encoding="utf-8")
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("MISSING_SOURCE_SHA256", [i["code"] for i in data["issues"]])

    def test_missing_manifest_is_yellow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, manifest=False)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 3)
            self.assertIn("NO_MANIFEST", [w["code"] for w in data["warnings"]])

    def test_manifest_unsigned_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            digest = _sha(root / "results" / "raw.md")
            _write_manifest(root, {"results/raw.md": digest}, signed=False)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("MANIFEST_UNSIGNED", [i["code"] for i in data["issues"]])

    def test_source_outside_results_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            notes = root / "notes"
            notes.mkdir()
            (notes / "x.md").write_text("10/16\n", encoding="utf-8")
            digest = _sha(notes / "x.md")
            (root / "facts" / "f.toml").write_text(
                FACT_A1.replace('source = "results/raw.md"',
                                'source = "notes/x.md"\nsource_sha256 = "%s"' % digest),
                encoding="utf-8")
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("SOURCE_OUTSIDE_RESULTS", [i["code"] for i in data["issues"]])

    def test_value_not_in_source_is_yellow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1.replace('"10/16"', '"77"'))
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 3, data)
            self.assertIn("VALUE_NOT_IN_SOURCE", [w["code"] for w in data["warnings"]])


class TestV1Citations(unittest.TestCase):
    """闸 3：natbib 全家桶 + fail-closed + 标识格式。"""

    def _audit(self, tex, bib=BIB_OK):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": tex}, bib=bib)
            return run_json(["audit", str(root), "--json"])

    def test_citep_checked(self):
        code, data = self._audit("见 \\citep{ghost2024}。\n")
        self.assertEqual(code, 1)
        self.assertEqual([i["code"] for i in data["issues"]], ["MISSING_CITE"])

    def test_citet_with_optional_args_checked(self):
        code, data = self._audit("见 \\citet[see][p.~3]{ghost2024}。\n")
        self.assertEqual(code, 1)
        self.assertEqual(data["issues"][0]["token"], "ghost2024")

    def test_citeauthor_checked(self):
        code, data = self._audit("\\citeauthor{ghost2024} 说过。\n")
        self.assertEqual(code, 1)
        self.assertEqual(data["issues"][0]["code"], "MISSING_CITE")

    def test_nocite_key_checked(self):
        code, data = self._audit("\\nocite{ghost2024}\n")
        self.assertEqual(code, 1)
        self.assertEqual(data["issues"][0]["token"], "ghost2024")

    def test_unknown_cite_command_fails_closed(self):
        code, data = self._audit("\\fancycite{chen2023}\n")
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN_CITE_COMMAND", [i["code"] for i in data["issues"]])

    def test_bad_arxiv_format_is_red(self):
        bib = "@article{bad2024,\n title = {X},\n arxiv = {not-an-id}\n}\n"
        code, data = self._audit("\\cite{bad2024}\n", bib=bib)
        self.assertEqual(code, 1)
        self.assertIn("BAD_STABLE_ID_FORMAT", [i["code"] for i in data["issues"]])

    def test_misc_with_url_is_ok(self):
        bib = "@misc{web2020,\n title = {Docs},\n url = {https://example.com/x}\n}\n"
        code, data = self._audit("\\cite{web2020}\n", bib=bib)
        self.assertEqual(code, 0, data)

    def test_duplicate_bib_key_is_red(self):
        bib = BIB_OK + "\n" + BIB_OK
        code, data = self._audit("\\cite{chen2023}\n", bib=bib)
        self.assertEqual(code, 1)
        self.assertIn("DUPLICATE_BIB_KEY", [i["code"] for i in data["issues"]])

    def test_duplicate_stable_id_is_yellow(self):
        bib = BIB_OK + ("\n@article{other2023,\n title = {Same},\n"
                        " doi = {10.18653/v1/2023.emnlp-main.741}\n}\n")
        code, data = self._audit("\\cite{chen2023}\n", bib=bib)
        self.assertEqual(code, 3)
        self.assertIn("DUPLICATE_STABLE_ID", [w["code"] for w in data["warnings"]])

    def test_string_macro_and_crossref(self):
        bib = ("@string{jm = {Journal of ML}}\n"
               "@proceedings{parent2020,\n doi = {10.1000/parent}\n}\n"
               "@inproceedings{child2021,\n crossref = {parent2020},\n"
               " title = {Child}, journal = jm\n}\n")
        code, data = self._audit("\\cite{child2021}\n", bib=bib)
        self.assertEqual(code, 0, data)


class TestV1DerivedExpr(unittest.TestCase):
    """闸 5：derived 必须写 expr，工具用 ast 白名单求值。"""

    def test_expr_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 0, data)

    def test_expr_mismatch_is_red(self):
        bad = FACT_A2.replace('"56.25%"', '"75%"')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1 + "\n" + FACT_A3 + "\n" + bad)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("EXPR_MISMATCH", [i["code"] for i in data["issues"]])

    def test_missing_expr_is_red(self):
        bad = re.sub(r"^expr = .*$\n?", "", FACT_A2, flags=re.M)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1 + "\n" + FACT_A3 + "\n" + bad)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("MISSING_EXPR", [i["code"] for i in data["issues"]])

    def test_expr_ast_whitelist_blocks_calls(self):
        bad = FACT_A2.replace(
            'expr = "(A1.num + A3.num) / (A1.den + A3.den) * 100"',
            'expr = "__import__(\'os\').system(\'echo pwn\')"')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1 + "\n" + FACT_A3 + "\n" + bad)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("EXPR_INVALID", [i["code"] for i in data["issues"]])

    def test_derived_cycle_is_red(self):
        c1 = ('[[fact]]\nid = "C1"\nclaim = "c1"\nvalue = "2"\n'
              'source = "results/raw.md"\nlocator = ""\nconfidence = "low"\n'
              'derived_from = ["C2"]\nexpr = "C2 + 1"\n')
        c2 = ('[[fact]]\nid = "C2"\nclaim = "c2"\nvalue = "1"\n'
              'source = "results/raw.md"\nlocator = ""\nconfidence = "low"\n'
              'derived_from = ["C1"]\nexpr = "C1 - 1"\n')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=c1 + "\n" + c2)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("DERIVED_CYCLE", [i["code"] for i in data["issues"]])

    def test_superseded_parent_is_red(self):
        newer = (FACT_A1.replace('"A1"', '"A9"').replace('"10/16"', '"11/16"')
                 .replace("derived_from = []", 'derived_from = []\nsupersedes = ["A1"]'))
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1 + "\n" + newer + "\n" + FACT_A2)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("SUPERSEDED_PARENT", [i["code"] for i in data["issues"]])


class TestV1Lexing(unittest.TestCase):
    """B3/C1/C4 的分词契约：唯一流水线。"""

    def nums(self, tex):
        s = paperkit.scan_tex(tex)
        return [n["token"] for n in paperkit._extract_numbers(s.masked, tex)]

    def test_verbatim_percent_is_not_comment(self):
        tex = "\\begin{verbatim}\nprecision = 50% (raw log)\n\\end{verbatim}\n后面 10 个"
        self.assertEqual(self.nums(tex), ["10"])

    def test_pkignore_explicit_exemption(self):
        self.assertEqual(self.nums(r"年份 2024 \pkignore{2024} 与 10 个"), ["2024", "10"])

    def test_superscript_subscript_are_structural(self):
        tex = r"We report $R^2 = 0.91$, $N = 1{,}024$, $\alpha = 0.05$, $x_{12}$."
        self.assertEqual(self.nums(tex), ["0.91", "1024", "0.05"])

    def test_scientific_notation_is_one_token(self):
        self.assertEqual(self.nums("lr 3e-4 and 4.2e-5"), ["3e-4", "4.2e-5"])
        self.assertEqual(paperkit.number_key("3e-4"), "0.0003")

    def test_latex_thin_space_thousands(self):
        self.assertEqual(self.nums(r"a corpus of 1\,000\,000 tokens"), ["1000000"])

    def test_percent_word(self):
        self.assertEqual(self.nums("grew by 3.4 percent"), ["3.4%"])
        self.assertEqual(paperkit.number_key("3.4", None, True), "0.034")

    def test_cite_optional_args_are_masked(self):
        s = paperkit.scan_tex(r"\citep[see][p.~3]{chen2023}")
        self.assertEqual([n["token"] for n in paperkit._extract_numbers(s.masked, "x")], [])


class TestV1ExitAndJson(unittest.TestCase):
    def test_json_schema_and_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "16 题里解决 10 道\\fact{A1}\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 0, data)
            self.assertEqual(data["schema_version"], "1.0")
            self.assertEqual(data["severity"], "ok")
            self.assertEqual(data["status"], "ok")

    def test_yellow_exit_code_and_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_42, sections={"a.tex": "42 epochs\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 3)
            self.assertEqual(data["severity"], "yellow")
            self.assertTrue(all(w["severity"] == "yellow" for w in data["warnings"]))
            self.assertTrue(all(i["severity"] == "red" for i in data["issues"]))

    def test_unscanned_tex_is_yellow_with_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, sections={"a.tex": "16 题里解决 10 道\\fact{A1}\n"})
            (root / "notes").mkdir()
            (root / "notes" / "extra.tex").write_text("stray 999\n", encoding="utf-8")
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 3)
            self.assertIn("UNSCANNED_TEX", [w["code"] for w in data["warnings"]])
            self.assertIn("sections/a.tex", data["coverage"]["files_scanned"])

    def test_duplicate_value_hygiene(self):
        rival = FACT_A1.replace('"A1"', '"A9"').replace('"开臂 resolved（16 题）"', '"另一件事"')
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, facts=FACT_A1 + "\n" + rival)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 3)
            self.assertIn("DUPLICATE_VALUE", [w["code"] for w in data["warnings"]])

    def test_preamble_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            code, data = run_json(["preamble", str(root), "--json"])
            self.assertEqual(code, 0)
            text = (root / "audit" / "preamble.tex").read_text(encoding="utf-8")
            self.assertIn(r"\providecommand{\fact}", text)


class TestRedTeamCounterexamples(unittest.TestCase):
    """红队 B1/B4 的反例夹具：v1 里必须真的红。"""

    def setUp(self):
        self.fix = ROOT / "tests" / "fixtures"

    def test_b1_fabricated_numbers_now_red(self):
        code, data = run_json(["audit", str(self.fix / "redteam-b1"), "--json"])
        self.assertEqual(code, 1, data)
        toks = {i["token"] for i in data["issues"]}
        self.assertTrue({"1422", "4.2e-5", "4242"} <= toks, toks)
        self.assertEqual([i["code"] for i in data["issues"]],
                         ["UNMATCHED_NUMBER"] * 3)

    def test_b4_nested_sections_now_red(self):
        code, data = run_json(["audit", str(self.fix / "redteam-b4"), "--json"])
        self.assertEqual(code, 1, data)
        locs = [i["location"] for i in data["issues"]]
        self.assertTrue(any(l.startswith("sections/chapters/intro.tex:") for l in locs), locs)
        self.assertEqual({i["token"] for i in data["issues"]}, {"3.7%", "12"})


class TestBatch36Friction(unittest.TestCase):
    """批 36 的三处落地摩擦：批注宏、数字贴单位、source_root。"""

    # ---- D1：批注宏不是正文 ----
    def test_d1_annotation_numbers_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, sections={"a.tex": "\\todoq{编造 47.3 与 15 与 4.3}\n"
                                        "\\todo[inline,color=red!20]{p~0.03}\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 0, data)
            self.assertEqual(data["summary"]["red"], 0)
            self.assertEqual(data["summary"]["annotations_skipped"], 2)
            self.assertEqual(data["summary"]["numbers_total"], 0)

    def test_d1_real_number_next_to_annotation_still_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, sections={"a.tex": "\\todoq{编造 47.3}\n真的 47.3 在这里\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertEqual([i["code"] for i in data["issues"]], ["UNMATCHED_NUMBER"])
            self.assertEqual(data["issues"][0]["token"], "47.3")
            self.assertEqual(data["summary"]["annotations_skipped"], 1)

    # ---- D2：数字贴单位 ----
    def test_d2_number_with_unit_suffix_is_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                facts="""[[fact]]
id = "T1"
claim = "耗时"
value = "131 秒"
source = "results/raw.md"
locator = "§一"
confidence = "high"
""",
                results_text="run took 131s, 53000 tokens, 5GB\n",
                sections={"a.tex": "耗时 131s\\fact{T1}\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 0, data)
            self.assertEqual(data["summary"]["numbers_bound"], 1)

    def test_d2_letter_leading_digits_are_not_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp, sections={"a.tex": "R2 H2O v2 都不是数字，但 47s 是\n"})
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertEqual([i["token"] for i in data["issues"]], ["47s"])

    # ---- D3：source_root ----
    def _external(self, tmp, source_root=None, symlink=False):
        tmp = Path(tmp)
        root = tmp / "paper"
        make_project(root, sections={"a.tex": "10/16\\fact{A1}\n"}, manifest=False)
        (root / "results" / "raw.md").unlink()
        src = tmp / "data" / "raw.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(RESULT_TEXT, encoding="utf-8")
        digest = _sha(src)
        (root / "facts" / "f.toml").write_text(
            '[[fact]]\nid = "A1"\nclaim = "x"\nvalue = "10/16"\n'
            'source = "data/raw.md"\nsource_sha256 = "%s"\n'
            'locator = "§"\nconfidence = "high"\n' % digest, encoding="utf-8")
        base = Path(source_root) if source_root else tmp
        if symlink:
            (base / "data").mkdir(parents=True, exist_ok=True)
            link = base / "data" / "raw.md"
            if not link.exists():
                link.symlink_to(src)
        (root / "paperkit.toml").write_text(
            '[project]\ntitle = "t"\nsections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
            'bib = "refs.bib"\nbuild = ""\nsource_root = "%s"\n' % base,
            encoding="utf-8")
        _write_manifest(root, {"data/raw.md": digest})
        return root

    def test_d3_source_under_source_root_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._external(tmp)
            code, data = run_json(["audit", str(root), "--json"])
            self.assertEqual(code, 0, data)
            self.assertEqual(data["summary"]["red"], 0)

    def test_d3_source_escaping_source_root_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._external(tmp, source_root=Path(tmp) / "scope", symlink=True)
            code, data = run_json(["check", str(root), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("SOURCE_OUTSIDE_SOURCE_ROOT",
                          [i["code"] for i in data["issues"]])


if __name__ == "__main__":
    unittest.main()
