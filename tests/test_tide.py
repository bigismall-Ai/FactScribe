# -*- coding: utf-8 -*-
"""批 89：潮汐式改动账 `factscribe tide` 的判据测试（全离线）。

规范：`docs/design/SPEC-TIDE.md`。改动＝事务：
涨（哈希差）＋落（改后真实文件）＋波及面（\\input/\\include 反向闭包）；
闭合＝paired ∧ hash_ok ∧ pass_all，全成或全退。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MAIN = r"""\documentclass{article}
\begin{document}
\input{chapters/a}
\end{document}
"""

CHAPTER = r"""\section{Method}\label{sec:method}
The run uses 53 tokens and \cite{smith2020}.
"""

CHAPTER_PUNCT = r"""\section{Method}\label{sec:method}
The run uses 53 tokens, and \cite{smith2020}!
"""

CHAPTER_NUMBER = r"""\section{Method}\label{sec:method}
The run uses 54 tokens and \cite{smith2020}.
"""


def make_tree(root: Path, files: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_tide(before: Path, after: Path, *extra: str):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", "tide",
           "--before", str(before), "--after", str(after), *extra]
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


def payload(proc) -> dict:
    return json.loads(proc.stdout)


def ledger_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.before = make_tree(self.tmp / "before", {
            "main.tex": MAIN, "chapters/a.tex": CHAPTER})
        self.after = make_tree(self.tmp / "after", {
            "main.tex": MAIN, "chapters/a.tex": CHAPTER})

    def tearDown(self):
        self._tmp.cleanup()

    def rewrite(self, rel: str, text: str) -> None:
        (self.after / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.after / rel).write_text(text, encoding="utf-8")

    def delete(self, rel: str) -> None:
        (self.after / rel).unlink()

    def commit(self, *extra: str) -> dict:
        proc = run_tide(self.before, self.after, "--json", *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        data = payload(proc)
        self.assertEqual(data["status"], "commit", data)
        return data

    def rollback(self, *extra: str) -> dict:
        proc = run_tide(self.before, self.after, "--json", *extra)
        self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
        data = payload(proc)
        self.assertEqual(data["status"], "rollback", data)
        return data


# --------------------------------------------------------------------------
# 涨/落：只改标点应闭合
# --------------------------------------------------------------------------

class TestCommit(Base):
    def test_punctuation_change_commits(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        data = self.commit()
        self.assertTrue(data["criteria"]["paired"])
        self.assertTrue(data["criteria"]["hash_ok"])
        self.assertTrue(data["criteria"]["pass_all"])

    def test_rise_records_real_before_and_after_hashes(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        data = self.commit()
        rise = data["rises"][0]
        self.assertEqual(rise["path"], "chapters/a.tex")
        self.assertEqual(rise["before"],
                         sha256_file(self.before / "chapters/a.tex"))
        self.assertEqual(rise["after"],
                         sha256_file(self.after / "chapters/a.tex"))
        self.assertNotEqual(rise["before"], rise["after"])

    def test_rise_records_touched_lines_and_section(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        rise = self.commit()["rises"][0]
        self.assertTrue(rise["lines"])
        self.assertIn("Method", rise["sections"])

    def test_falls_pair_one_to_one_with_rises(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        data = self.commit()
        self.assertEqual([r["path"] for r in data["rises"]],
                         [f["path"] for f in data["falls"]])
        self.assertTrue(all(f["exists"] for f in data["falls"]))
        self.assertTrue(all(f["sha256"] for f in data["falls"]))

    def test_punctuation_keeps_protect_hard_surface_green(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        data = self.commit()
        self.assertEqual(data["findings"], [])

    def test_commit_writes_append_only_ledger_and_derived_view(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        self.commit()
        ledger = self.after / "audit" / "tide-events.ndjson"
        self.assertTrue(ledger.is_file())
        events = ledger_lines(ledger)
        self.assertEqual(events[-1]["event"], "verdict")
        self.assertEqual(events[-1]["status"], "commit")
        view = self.after / "audit" / "tide-ledger.md"
        self.assertTrue(view.is_file())
        text = view.read_text(encoding="utf-8")
        self.assertIn("chapters/a.tex", text)
        self.assertIn("main.tex", text)          # 波及面列
        self.assertNotIn(str(self.tmp), text)    # 禁绝对路径

    def test_events_are_sorted_ndjson_one_per_line(self):
        make_tree(self.before / "chapters", {"z.tex": CHAPTER})
        make_tree(self.after / "chapters", {"z.tex": CHAPTER_PUNCT})
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        self.commit()
        events = ledger_lines(self.after / "audit" / "tide-events.ndjson")
        rises = [e for e in events if e["event"] == "rise"]
        self.assertEqual([e["path"] for e in rises],
                         sorted(e["path"] for e in rises))
        self.assertEqual([e["event"] for e in events],
                         ["rise"] * len(rises) + ["fall"] * len(rises)
                         + ["verdict"])

    def test_custom_out_writes_ledger_only(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        out = self.tmp / "custom" / "events.ndjson"
        self.commit("--out", str(out))
        self.assertTrue(out.is_file())
        self.assertFalse((self.after / "audit" / "tide-ledger.md").exists())
        # 自定义产出路径不许被当成下一趟的改动
        line = json.dumps({"event": "verdict", "tx": "0" * 16,
                           "status": "commit", "paired": True,
                           "hash_ok": True, "pass_all": True,
                           "rises": 0, "falls": 0, "affect": []})
        out.write_text(line + "\n", encoding="utf-8")
        self.commit("--out", str(out))
        self.assertEqual(out.read_text(encoding="utf-8").splitlines()[0], line)

    def test_ledger_is_append_only(self):
        old = json.dumps({"event": "verdict", "tx": "0" * 16,
                          "status": "commit", "paired": True, "hash_ok": True,
                          "pass_all": True, "rises": 0, "falls": 0,
                          "affect": []}, sort_keys=True)
        out = self.tmp / "events.ndjson"
        out.write_text(old + "\n", encoding="utf-8")
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        self.commit("--out", str(out))
        lines = out.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], old)
        self.assertGreater(len(lines), 1)


# --------------------------------------------------------------------------
# pass_all：改数字 → 保护面红 → rollback
# --------------------------------------------------------------------------

class TestPassAllRollback(Base):
    def test_number_change_rolls_back(self):
        self.rewrite("chapters/a.tex", CHAPTER_NUMBER)
        data = self.rollback()
        self.assertFalse(data["criteria"]["pass_all"])
        self.assertTrue(data["criteria"]["paired"])
        self.assertTrue(data["criteria"]["hash_ok"])

    def test_number_change_writes_nothing(self):
        self.rewrite("chapters/a.tex", CHAPTER_NUMBER)
        self.rollback()
        self.assertFalse((self.after / "audit" / "tide-events.ndjson").exists())
        self.assertFalse((self.after / "audit" / "tide-ledger.md").exists())

    def test_number_change_reports_hard_finding(self):
        self.rewrite("chapters/a.tex", CHAPTER_NUMBER)
        data = self.rollback()
        codes = {f["code"] for f in data["findings"]}
        self.assertIn("PROTECT_NUMBER_CHANGED", codes)
        self.assertTrue(all(f["severity"] == "red" for f in data["findings"]))

    def test_rollback_does_not_touch_existing_ledger(self):
        old = json.dumps({"event": "verdict", "tx": "0" * 16,
                          "status": "commit", "paired": True, "hash_ok": True,
                          "pass_all": True, "rises": 0, "falls": 0,
                          "affect": []}, sort_keys=True) + "\n"
        out = self.tmp / "events.ndjson"
        out.write_text(old, encoding="utf-8")
        self.rewrite("chapters/a.tex", CHAPTER_NUMBER)
        self.rollback("--out", str(out))
        self.assertEqual(out.read_text(encoding="utf-8"), old)


# --------------------------------------------------------------------------
# hash_ok：删除 / 自报造假
# --------------------------------------------------------------------------

class TestHashOkRollback(Base):
    def test_deleted_file_rolls_back(self):
        (self.before / "chapters" / "gone.tex").write_text(CHAPTER,
                                                           encoding="utf-8")
        data = self.rollback()
        self.assertFalse(data["criteria"]["hash_ok"])
        fall = next(f for f in data["falls"] if f["path"] == "chapters/gone.tex")
        self.assertFalse(fall["exists"])
        self.assertIsNone(fall["sha256"])

    def test_deleted_file_leaves_no_ledger(self):
        (self.before / "chapters" / "gone.tex").write_text(CHAPTER,
                                                           encoding="utf-8")
        self.rollback()
        self.assertFalse((self.after / "audit" / "tide-events.ndjson").exists())

    def test_forged_ledger_hash_rolls_back(self):
        forged = json.dumps({"event": "fall", "tx": "deadbeefdeadbeef",
                             "path": "chapters/a.tex", "exists": True,
                             "sha256": "0" * 64}, sort_keys=True) + "\n"
        out = self.tmp / "events.ndjson"
        out.write_text(forged, encoding="utf-8")
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        data = self.rollback("--out", str(out))
        self.assertFalse(data["criteria"]["hash_ok"])
        self.assertTrue(data["criteria"]["pass_all"])

    def test_forged_ledger_is_left_untouched(self):
        forged = json.dumps({"event": "fall", "tx": "deadbeefdeadbeef",
                             "path": "chapters/a.tex", "exists": True,
                             "sha256": "0" * 64}, sort_keys=True) + "\n"
        out = self.tmp / "events.ndjson"
        out.write_text(forged, encoding="utf-8")
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        self.rollback("--out", str(out))
        self.assertEqual(out.read_text(encoding="utf-8"), forged)


# --------------------------------------------------------------------------
# paired：自报账本里孤立的涨
# --------------------------------------------------------------------------

class TestPairedRollback(Base):
    def test_orphan_rise_in_ledger_rolls_back(self):
        forged = json.dumps({"event": "rise", "tx": "feedfacefeedface",
                             "path": "chapters/a.tex", "before": None,
                             "after": "0" * 64, "lines": [], "sections": []},
                            sort_keys=True) + "\n"
        out = self.tmp / "events.ndjson"
        out.write_text(forged, encoding="utf-8")
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        data = self.rollback("--out", str(out))
        self.assertFalse(data["criteria"]["paired"])

    def test_rise_without_any_change_pairs_trivially(self):
        data = self.commit()
        self.assertEqual(data["rises"], [])
        self.assertTrue(data["criteria"]["paired"])


# --------------------------------------------------------------------------
# 新增文件
# --------------------------------------------------------------------------

class TestAddedFile(Base):
    def test_added_file_commits(self):
        self.rewrite("chapters/b.tex", CHAPTER)
        data = self.commit()
        rise = next(r for r in data["rises"] if r["path"] == "chapters/b.tex")
        self.assertIsNone(rise["before"])
        self.assertIsNotNone(rise["after"])
        fall = next(f for f in data["falls"] if f["path"] == "chapters/b.tex")
        self.assertTrue(fall["exists"])
        self.assertEqual(fall["sha256"], sha256_file(self.after / "chapters/b.tex"))

    def test_added_tex_soft_yellow_does_not_roll_back(self):
        self.rewrite("chapters/b.tex", CHAPTER)
        data = self.commit()
        self.assertTrue(data["criteria"]["pass_all"])
        self.assertEqual(data["findings"], [])


# --------------------------------------------------------------------------
# 波及面：\input / \include 反向闭包
# --------------------------------------------------------------------------

class TestAffect(Base):
    def test_referrer_enters_affect(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        data = self.commit()
        self.assertIn("chapters/a.tex", data["affect"])
        self.assertIn("main.tex", data["affect"])

    def test_affect_is_transitive(self):
        make_tree(self.before, {"chapters/a.tex":
                                "\\section{Method}\n\\input{sections/b}\n"})
        make_tree(self.after, {"chapters/a.tex":
                               "\\section{Method}\n\\input{sections/b}\n"})
        make_tree(self.before, {"sections/b.tex": CHAPTER})
        make_tree(self.after, {"sections/b.tex": CHAPTER_PUNCT})
        data = self.commit()
        self.assertEqual(data["affect"], ["chapters/a.tex", "main.tex",
                                          "sections/b.tex"])

    def test_unrelated_file_not_in_affect(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        make_tree(self.before, {"chapters/other.tex": CHAPTER})
        make_tree(self.after, {"chapters/other.tex": CHAPTER})
        data = self.commit()
        self.assertNotIn("chapters/other.tex", data["affect"])

    def test_include_command_counts_too(self):
        make_tree(self.before, {"main.tex":
                                "\\include{chapters/a}\n"})
        make_tree(self.after, {"main.tex":
                               "\\include{chapters/a}\n"})
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        data = self.commit()
        self.assertIn("main.tex", data["affect"])


# --------------------------------------------------------------------------
# 忽略规则：LaTeX 构建产物默认不入账
# --------------------------------------------------------------------------

LATEX_ARTIFACTS = ("main.aux", "main.log", "main.out", "main.blg", "main.bbl",
                   "main.fls", "main.fdb_latexmk", "main.synctex.gz",
                   "main.toc", "main.lof", "main.lot", "main.nav",
                   "main.snm", "main.vrb")


class TestIgnore(Base):
    def test_default_ignores_added_artifacts(self):
        for rel in LATEX_ARTIFACTS:
            self.rewrite(rel, "junk\n")
        data = self.commit()
        self.assertEqual(data["rises"], [])
        self.assertEqual(data["falls"], [])
        self.assertEqual(len(data["ignored"]), len(LATEX_ARTIFACTS))

    def test_default_ignores_modified_artifacts(self):
        for rel in ("main.aux", "main.log", "main.out", "main.blg"):
            (self.before / rel).write_text("old\n", encoding="utf-8")
            (self.after / rel).write_text("new\n", encoding="utf-8")
        data = self.commit()
        self.assertEqual(data["rises"], [])

    def test_default_ignores_deleted_artifacts(self):
        # 缺陷复现：改前目录有构建产物、改后没有——旧行为判 rollback
        for rel in ("main.aux", "main.blg", "main.out"):
            (self.before / rel).write_text("junk\n", encoding="utf-8")
        data = self.commit()
        self.assertEqual(data["rises"], [])
        self.assertEqual(data["reasons"], [])

    def test_ignored_artifacts_are_listed(self):
        (self.before / "main.aux").write_text("old\n", encoding="utf-8")
        (self.after / "main.aux").write_text("new\n", encoding="utf-8")
        data = self.commit()
        self.assertEqual(data["ignored"], ["main.aux"])

    def test_non_ignored_extensions_still_counted(self):
        self.rewrite("refs.bib", "@book{x}\n")
        self.rewrite("notes.md", "# n\n")
        self.rewrite("paperkit.toml", "build = ''\n")
        self.rewrite("figures/f.pdf", "%PDF-1.4\n")
        self.rewrite("main.aux", "artifact\n")
        data = self.commit()
        self.assertEqual([r["path"] for r in data["rises"]],
                         ["figures/f.pdf", "notes.md", "paperkit.toml",
                          "refs.bib"])

    def test_ignore_glob_appends_to_defaults(self):
        (self.before / "chapters" / "a.tex.bak").write_text("x\n",
                                                            encoding="utf-8")
        (self.before / "notes.tmp").write_text("x\n", encoding="utf-8")
        self.rewrite("main.aux", "artifact\n")
        # 不传 --ignore：删除的 .bak/.tmp 是涨而无落 → rollback
        self.rollback()
        data = self.commit("--ignore", "*.bak", "--ignore", "*.tmp")
        self.assertEqual(data["rises"], [])
        self.assertIn("*.bak", data["ignore"])
        self.assertIn("*.tmp", data["ignore"])

    def test_no_default_ignore_restores_rollback(self):
        (self.before / "main.aux").write_text("junk\n", encoding="utf-8")
        data = self.rollback("--no-default-ignore")
        self.assertFalse(data["criteria"]["hash_ok"])
        self.assertTrue(any("main.aux" in r for r in data["reasons"]))
        self.assertEqual(data["ignore"], [])

    def test_no_default_ignore_keeps_explicit_globs(self):
        (self.before / "main.aux").write_text("junk\n", encoding="utf-8")
        data = self.commit("--no-default-ignore", "--ignore", "*.aux")
        self.assertEqual(data["rises"], [])

    def test_ignored_files_do_not_change_affect(self):
        # 被 \input 的 .tex 变了 → 主文件仍在波及面；忽略项不进波及面
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        self.rewrite("main.aux", "artifact\n")
        data = self.commit()
        self.assertEqual(data["affect"], ["chapters/a.tex", "main.tex"])
        self.assertNotIn("main.aux", data["affect"])

    def test_ignored_file_not_reported_as_protect_finding(self):
        self.rewrite("chapters/a.tex", CHAPTER_NUMBER)
        (self.before / "main.aux").write_text("old\n", encoding="utf-8")
        data = self.rollback()
        self.assertEqual({f["code"] for f in data["findings"]},
                         {"PROTECT_NUMBER_CHANGED"})


# --------------------------------------------------------------------------
# 确定性
# --------------------------------------------------------------------------

class TestDeterminism(Base):
    def test_same_run_twice_is_byte_identical(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        first = run_tide(self.before, self.after, "--json")
        second = run_tide(self.before, self.after, "--json")
        self.assertEqual(first.returncode, 0)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)
        ledger = self.after / "audit" / "tide-events.ndjson"
        one = ledger.read_bytes()
        self.assertEqual(one, ledger.read_bytes())

    def test_two_fresh_trees_are_byte_identical(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        self.commit()
        led1 = (self.after / "audit" / "tide-events.ndjson").read_bytes()
        view1 = (self.after / "audit" / "tide-ledger.md").read_bytes()

        other = self.tmp / "other"
        b2 = make_tree(other / "before", {"main.tex": MAIN,
                                          "chapters/a.tex": CHAPTER})
        a2 = make_tree(other / "after", {"main.tex": MAIN,
                                         "chapters/a.tex": CHAPTER_PUNCT})
        proc = run_tide(b2, a2, "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        led2 = (a2 / "audit" / "tide-events.ndjson").read_bytes()
        view2 = (a2 / "audit" / "tide-ledger.md").read_bytes()
        self.assertEqual(led1, led2)
        self.assertEqual(view1, view2)

    def test_artifacts_contain_no_absolute_paths(self):
        self.rewrite("chapters/a.tex", CHAPTER_PUNCT)
        self.commit()
        ledger = (self.after / "audit" / "tide-events.ndjson").read_text(
            encoding="utf-8")
        view = (self.after / "audit" / "tide-ledger.md").read_text(
            encoding="utf-8")
        for text in (ledger, view):
            self.assertNotIn(str(self.tmp), text)
            self.assertNotIn(str(self.after), text)


class TestUsage(unittest.TestCase):
    def test_missing_directory_is_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_tide(Path(tmp) / "nope", Path(tmp), "--json")
            self.assertEqual(proc.returncode, 2, proc.stderr + proc.stdout)
            self.assertEqual(payload(proc)["status"], "error")

    def test_broken_ledger_is_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_tree(root / "b", {"main.tex": MAIN})
            make_tree(root / "a", {"main.tex": MAIN})
            out = root / "events.ndjson"
            out.write_text("not json\n", encoding="utf-8")
            proc = run_tide(root / "b", root / "a", "--out", str(out), "--json")
            self.assertEqual(proc.returncode, 2, proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main()
