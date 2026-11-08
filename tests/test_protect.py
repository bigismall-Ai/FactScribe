# -*- coding: utf-8 -*-
"""批 83：改写保护面比对 `factscribe protect` 的判据测试（全离线）。

保护面清单见 SPEC-V3.0 §14：事实标记、数字、引用、公式、表格、交叉引用
六条硬面（变了即红），外加标题重命名与文件增删两条软面（黄）。
本模块只服务 protect 子命令，不改 audit/style 的判据与退出码。
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

BASE = r"""\section{Introduction}\label{sec:intro}

This run reports 53 tokens over 12 minutes, as shown in
Table~\ref{tab:runs} and~\cite{smith2020}.
The accuracy is 62.5\% and is bound to \fact{A1}.
Inline mathematics $a+b=c$ states the identity.
\begin{equation}
E = mc^2
\end{equation}
\begin{tabular}{ll}
Run & Tokens \\
R1 & 53 \\
R2 & 12 \\
\end{tabular}
"""


def make_tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def run_protect(before: Path, after: Path, *extra: str):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", "protect",
           "--before", str(before), "--after", str(after), *extra]
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


def payload(proc) -> dict:
    return json.loads(proc.stdout)


def codes(proc) -> set:
    return {f["code"] for f in payload(proc)["findings"]}


class ProtectCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.before = make_tree(self.tmp / "before", {"main.tex": BASE})
        self.after = make_tree(self.tmp / "after", {"main.tex": BASE})

    def tearDown(self):
        self._tmp.cleanup()

    def rewrite(self, text: str, rel: str = "main.tex") -> None:
        (self.after / rel).write_text(text, encoding="utf-8")

    def assert_clean(self):
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual(payload(proc)["findings"], [])


# --------------------------------------------------------------------------
# 全绿与噪声边界
# --------------------------------------------------------------------------

class TestNoise(ProtectCase):
    def test_identical_trees_are_green(self):
        self.assert_clean()

    def test_punctuation_and_sentence_split_only(self):
        self.rewrite(BASE.replace(
            "This run reports 53 tokens over 12 minutes, as shown in\n"
            "Table~\\ref{tab:runs} and~\\cite{smith2020}.",
            "This run reports 53 tokens over 12 minutes; see\n"
            "Table~\\ref{tab:runs} and~\\cite{smith2020}."))
        self.assert_clean()

    def test_number_spacing_is_normalized(self):
        self.rewrite(BASE.replace("53 tokens", "53~tokens")
                     .replace("62.5\\%", "62.5 \\%"))
        self.assert_clean()

    def test_same_cite_key_with_other_command(self):
        self.rewrite(BASE.replace("\\cite{smith2020}", "\\citep{smith2020}"))
        self.assert_clean()

    def test_math_whitespace_reflow(self):
        self.rewrite(BASE.replace("$a+b=c$", "$a + b = c$"))
        self.assert_clean()

    def test_table_whitespace_reflow(self):
        self.rewrite(BASE.replace("R1 & 53", "R1   &   53"))
        self.assert_clean()

    def test_ref_style_change_keeps_key(self):
        self.rewrite(BASE.replace("\\ref{tab:runs}", "\\eqref{tab:runs}"))
        self.assert_clean()

    def test_commented_fact_is_ignored(self):
        self.rewrite(BASE + "% \\fact{A9} commented out\n")
        self.assert_clean()

    def test_empty_directories_are_green(self):
        before = make_tree(self.tmp / "empty-a", {})
        after = make_tree(self.tmp / "empty-b", {})
        proc = run_protect(before, after, "--json")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(payload(proc)["findings"], [])


# --------------------------------------------------------------------------
# 六条硬保护面：各 1 正 1 负
# --------------------------------------------------------------------------

class TestFactSurface(ProtectCase):
    def test_fact_change_is_red(self):
        self.rewrite(BASE.replace("\\fact{A1}", "\\fact{A2}"))
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("PROTECT_FACT_CHANGED", codes(proc))
        f = next(x for x in payload(proc)["findings"]
                 if x["code"] == "PROTECT_FACT_CHANGED")
        self.assertEqual(f["file"], "main.tex")
        self.assertEqual(f["line"], 5)
        self.assertEqual((f["before"], f["after"]), ("A1", "A2"))
        self.assertIn("改成了", f["message"])

    def test_fact_kept_while_prose_changes(self):
        self.rewrite(BASE.replace(
            "The accuracy is 62.5\\% and is bound to \\fact{A1}.",
            "As the ledger shows, accuracy reaches 62.5\\% (\\fact{A1})."))
        self.assert_clean()

    def test_fact_body_number_is_still_protected(self):
        before = make_tree(self.tmp / "body-a", {
            "main.tex": "The bound value \\fact{A1}{53} is shown.\n"})
        after = make_tree(self.tmp / "body-b", {
            "main.tex": "The bound value \\fact{A1}{54} is shown.\n"})
        proc = run_protect(before, after, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("PROTECT_NUMBER_CHANGED", codes(proc))


class TestNumberSurface(ProtectCase):
    def test_one_number_change_reports_position(self):
        self.rewrite(BASE.replace("reports 53 tokens", "reports 54 tokens"))
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("PROTECT_NUMBER_CHANGED", codes(proc))
        f = next(x for x in payload(proc)["findings"]
                 if x["code"] == "PROTECT_NUMBER_CHANGED")
        self.assertEqual((f["file"], f["line"]), ("main.tex", 3))
        self.assertIn("53", f["before"])
        self.assertIn("54", f["after"])
        self.assertEqual(f["file"], "main.tex")
        self.assertEqual(f["line"], 3)

    def test_thousand_separator_is_normalized(self):
        before = make_tree(self.tmp / "num-a", {
            "main.tex": "The run used 1,234 tokens and 53k samples.\n"})
        after = make_tree(self.tmp / "num-b", {
            "main.tex": "The run used 1234 tokens and 53000 samples.\n"})
        proc = run_protect(before, after, "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(payload(proc)["findings"], [])


class TestCiteSurface(ProtectCase):
    def test_cite_key_change_is_red(self):
        self.rewrite(BASE.replace("\\cite{smith2020}", "\\cite{smith2021}"))
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("PROTECT_CITE_CHANGED", codes(proc))
        f = next(x for x in payload(proc)["findings"]
                 if x["code"] == "PROTECT_CITE_CHANGED")
        self.assertEqual((f["before"], f["after"]), ("smith2020", "smith2021"))

    def test_cite_key_kept(self):
        self.rewrite(BASE.replace("and~\\cite{smith2020}", "and \\cite{smith2020}"))
        self.assert_clean()


class TestMathSurface(ProtectCase):
    def test_inline_math_change_is_red(self):
        self.rewrite(BASE.replace("$a+b=c$", "$a+b=d$"))
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("PROTECT_MATH_CHANGED", codes(proc))
        f = next(x for x in payload(proc)["findings"]
                 if x["code"] == "PROTECT_MATH_CHANGED")
        self.assertEqual(f["file"], "main.tex")
        self.assertIn("公式", f["message"])

    def test_environment_math_change_is_red(self):
        self.rewrite(BASE.replace("E = mc^2", "E = mc^3"))
        proc = run_protect(self.before, self.after, "--json")
        self.assertIn("PROTECT_MATH_CHANGED", codes(proc))

    def test_math_kept_while_prose_changes(self):
        self.rewrite(BASE.replace(
            "Inline mathematics $a+b=c$ states the identity.",
            "Inline mathematics $a+b=c$ gives the identity used above."))
        self.assert_clean()


class TestTableSurface(ProtectCase):
    def test_added_table_row_is_red(self):
        self.rewrite(BASE.replace("R2 & 12 \\\\", "R2 & 12 \\\\\nR3 & 7 \\\\"))
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("PROTECT_TABLE_CHANGED", codes(proc))
        f = next(x for x in payload(proc)["findings"]
                 if x["code"] == "PROTECT_TABLE_CHANGED")
        self.assertIn("多出", f["message"])
        self.assertEqual(f["file"], "main.tex")
        self.assertGreater(f["line"], 0)

    def test_cell_count_change_is_red(self):
        self.rewrite(BASE.replace("R1 & 53 \\\\", "R1 & 53 & extra \\\\"))
        proc = run_protect(self.before, self.after, "--json")
        self.assertIn("PROTECT_TABLE_CHANGED", codes(proc))
        f = next(x for x in payload(proc)["findings"]
                 if x["code"] == "PROTECT_TABLE_CHANGED")
        self.assertIn("列数", f["message"])

    def test_table_kept(self):
        self.rewrite(BASE.replace("Run & Tokens", "Run  &  Tokens"))
        self.assert_clean()


class TestLabelSurface(ProtectCase):
    def test_label_key_change_is_red(self):
        self.rewrite(BASE.replace("\\ref{tab:runs}", "\\ref{tab:other}"))
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("PROTECT_LABEL_CHANGED", codes(proc))
        f = next(x for x in payload(proc)["findings"]
                 if x["code"] == "PROTECT_LABEL_CHANGED")
        self.assertEqual((f["before"], f["after"]), ("tab:runs", "tab:other"))

    def test_label_kept(self):
        self.rewrite(BASE.replace("Table~\\ref{tab:runs}", "Table \\ref{tab:runs}"))
        self.assert_clean()


# --------------------------------------------------------------------------
# 软面：标题改名与文件集合
# --------------------------------------------------------------------------

class TestSoftSurfaces(ProtectCase):
    def test_heading_rename_is_yellow(self):
        self.rewrite(BASE.replace("\\section{Introduction}", "\\section{Overview}"))
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 3)
        self.assertIn("PROTECT_HEADING_RENAMED", codes(proc))
        f = next(x for x in payload(proc)["findings"]
                 if x["code"] == "PROTECT_HEADING_RENAMED")
        self.assertEqual(f["severity"], "yellow")
        self.assertEqual((f["before"], f["after"]), ("Introduction", "Overview"))

    def test_added_heading_is_not_a_rename(self):
        before = make_tree(self.tmp / "head-a", {
            "main.tex": "\\section{One}\nAlpha prose.\n\\section{Two}\nBeta prose.\n"})
        after = make_tree(self.tmp / "head-b", {
            "main.tex": "\\section{One}\nAlpha prose.\n"
                        "\\section{Inserted}\nGamma prose.\n"
                        "\\section{Two}\nBeta prose.\n"})
        proc = run_protect(before, after, "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(payload(proc)["findings"], [])

    def test_allow_renames_downgrades_heading_to_info(self):
        self.rewrite(BASE.replace("\\section{Introduction}", "\\section{Overview}"))
        proc = run_protect(self.before, self.after, "--json", "--allow-renames")
        self.assertEqual(proc.returncode, 0)
        f = payload(proc)["findings"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["code"], "PROTECT_HEADING_RENAMED")
        self.assertEqual(f[0]["severity"], "info")

    def test_added_file_is_yellow(self):
        make_tree(self.after, {"extra.tex": "A new appendix.\n"})
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 3)
        self.assertIn("PROTECT_FILE_SET_CHANGED", codes(proc))
        f = next(x for x in payload(proc)["findings"]
                 if x["code"] == "PROTECT_FILE_SET_CHANGED")
        self.assertIn("extra.tex", f["message"])
        self.assertIn("多出", f["message"])

    def test_removed_file_is_yellow(self):
        make_tree(self.before, {"extra.tex": "An old appendix.\n"})
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 3)
        f = next(x for x in payload(proc)["findings"]
                 if x["code"] == "PROTECT_FILE_SET_CHANGED")
        self.assertIn("少了", f["message"])

    def test_red_wins_over_yellow(self):
        self.rewrite(BASE.replace("\\fact{A1}", "\\fact{A2}"))
        make_tree(self.after, {"extra.tex": "new\n"})
        proc = run_protect(self.before, self.after, "--json")
        self.assertEqual(proc.returncode, 1)
        both = codes(proc)
        self.assertIn("PROTECT_FACT_CHANGED", both)
        self.assertIn("PROTECT_FILE_SET_CHANGED", both)


# --------------------------------------------------------------------------
# 契约：JSON 字段、退出码、用法错
# --------------------------------------------------------------------------

class TestContract(ProtectCase):
    def test_json_fields_and_summary(self):
        self.rewrite(BASE.replace("reports 53 tokens", "reports 54 tokens"))
        proc = run_protect(self.before, self.after, "--json")
        data = payload(proc)
        self.assertEqual(data["command"], "protect")
        self.assertEqual(data["exit"], 1)
        self.assertEqual(data["allow_renames"], False)
        self.assertTrue(data["before"].endswith("before"))
        self.assertTrue(data["after"].endswith("after"))
        self.assertGreaterEqual(data["summary"]["red"], 1)
        for f in data["findings"]:
            for key in ("severity", "code", "file", "line",
                        "message", "before", "after"):
                self.assertIn(key, f)

    def test_missing_directory_is_config_error(self):
        proc = run_protect(self.tmp / "nope", self.after)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("不存在", proc.stderr)

    def test_human_output_has_file_line_detail(self):
        self.rewrite(BASE.replace("\\cite{smith2020}", "\\cite{smith2021}"))
        proc = run_protect(self.before, self.after)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("main.tex:4", proc.stdout)
        self.assertIn("smith2020", proc.stdout)
        self.assertIn("smith2021", proc.stdout)


if __name__ == "__main__":
    unittest.main()
