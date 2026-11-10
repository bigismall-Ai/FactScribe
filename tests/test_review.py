# -*- coding: utf-8 -*-
"""批 114：`factscribe review`——改写验收一条命令（全离线）。

规范：`docs/design/SPEC-REVIEW.md`。

要证的只有四件事：

- 三项判据各自独立生效：保护面红 → 拒绝（1）、tide 不闭合 → 拒绝（1）、
  新增 style 违规超 --allow-new → 需复核（3）、全过 → 通过（0）；
- 输出逐项列明细，不许只给一个总结论；
- --snapshot 只在「通过」时落快照；
- review 是 protect + style --diff + tide 的组合，不新增判据。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOML = """[project]
title = "t"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""

BASE = (
    "\\section{Results}\n"
    "This run reports 53 tokens over 12 minutes in total, and the pipeline "
    "is stable.\n"
)
HEADING_BAD = BASE.replace("\\section{Results}",
                           "\\section{Results: A New View}")
NUMBER_BAD = BASE.replace("53 tokens", "54 tokens")


def run_review(*args: str):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", "review", *args]
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


def payload(proc) -> dict:
    return json.loads(proc.stdout)


def make_project(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "paperkit.toml").write_text(TOML, encoding="utf-8")
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


class ReviewCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="review-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def pair(self, before: dict[str, str], after: dict[str, str]):
        b = make_project(self.tmp / "before", before)
        a = make_project(self.tmp / "after", after)
        return b, a

    def review(self, before: Path, after: Path, *extra: str):
        return run_review("--before", str(before), "--after", str(after),
                          *extra)

    # ---------------------------------------------------------------- 判定
    def test_no_change_passes(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": BASE})
        proc = self.review(b, a)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("判定：通过", proc.stdout)

    def test_number_change_rejects_with_protect_code(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": NUMBER_BAD})
        proc = self.review(b, a, "--json")
        self.assertEqual(proc.returncode, 1)
        data = payload(proc)
        self.assertEqual(data["verdict"], "reject")
        self.assertEqual(data["protect"]["red"], 1)
        codes = {f["code"] for f in data["protect"]["findings"]}
        self.assertIn("PROTECT_NUMBER_CHANGED", codes)

    def test_new_heading_needs_review_with_code_and_line(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": HEADING_BAD})
        proc = self.review(b, a, "--json")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        data = payload(proc)
        self.assertEqual(data["verdict"], "needs_review")
        self.assertEqual(data["style"]["new_findings"], 1)
        finding = data["style"]["findings"][0]
        self.assertEqual(finding["code"], "HEADING_MALFORMED")
        self.assertEqual(finding["file"], "sections/01.tex")
        self.assertEqual(finding["line"], 1)

    def test_allow_new_permits_the_same_heading_change(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": HEADING_BAD})
        proc = self.review(b, a, "--allow-new", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("判定：通过", proc.stdout)

    def test_deleted_file_rejects_on_tide(self):
        b, a = self.pair(
            {"sections/01.tex": BASE,
             "sections/02.tex": "\\section{Extra}\n"
                                "Another sentence with enough words to stand "
                                "on its own.\n"},
            {"sections/01.tex": BASE})
        proc = self.review(b, a, "--json")
        self.assertEqual(proc.returncode, 1)
        data = payload(proc)
        self.assertEqual(data["verdict"], "reject")
        self.assertFalse(data["tide"]["closed"])
        self.assertIn("tide 未闭合", "；".join(data["reasons"]))

    def test_reject_beats_needs_review(self):
        # 数字变了（保护面红）＋标题也变坏（新增违规）：先判拒绝，不给 3。
        after = HEADING_BAD.replace("53 tokens", "54 tokens")
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": after})
        proc = self.review(b, a, "--json")
        self.assertEqual(proc.returncode, 1)
        data = payload(proc)
        self.assertEqual(data["verdict"], "reject")
        self.assertGreaterEqual(data["style"]["new_findings"], 1)

    # ---------------------------------------------------------------- JSON
    def test_json_has_three_details_and_final_verdict(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": NUMBER_BAD})
        proc = self.review(b, a, "--json")
        data = payload(proc)
        self.assertEqual(data["command"], "review")
        self.assertEqual(data["verdict"], "reject")
        self.assertEqual(data["verdict_label"], "拒绝")
        self.assertIn("reasons", data)
        self.assertEqual(set(data["protect"]) >=
                         {"red", "yellow", "info", "findings"}, True)
        self.assertEqual(set(data["style"]) >=
                         {"new_findings", "allow_new", "findings"}, True)
        self.assertEqual(set(data["tide"]) >=
                         {"closed", "paired", "hash_ok", "pass_all"},
                         True)
        self.assertEqual(data["tide"]["criteria"],
                         {"paired": data["tide"]["paired"],
                          "hash_ok": data["tide"]["hash_ok"],
                          "pass_all": data["tide"]["pass_all"]})

    def test_json_snapshot_block_is_explicit(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": BASE})
        proc = self.review(b, a, "--json")
        data = payload(proc)
        self.assertEqual(data["snapshot"], {
            "requested": False, "saved": False, "id": None, "short": None,
            "files": None, "bytes": None, "store": None})

    # ------------------------------------------------ 三种判定各一条真目录对
    def test_verdict_pair_pass(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": BASE})
        proc = self.review(b, a, "--json")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(payload(proc)["verdict"], "pass")

    def test_verdict_pair_reject(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": NUMBER_BAD})
        proc = self.review(b, a, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload(proc)["verdict"], "reject")

    def test_verdict_pair_needs_review(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": HEADING_BAD})
        proc = self.review(b, a, "--json")
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(payload(proc)["verdict"], "needs_review")

    # ---------------------------------------------------------------- 快照
    def test_snapshot_saved_only_on_pass(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": BASE})
        store = self.tmp / "store"
        proc = self.review(b, a, "--snapshot", str(store), "--json")
        self.assertEqual(proc.returncode, 0)
        data = payload(proc)
        self.assertTrue(data["snapshot"]["saved"])
        self.assertTrue((store / "snapshots" / data["snapshot"]["id"] /
                         "manifest.tsv").is_file())

    def test_snapshot_not_saved_on_needs_review(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": HEADING_BAD})
        store = self.tmp / "store"
        proc = self.review(b, a, "--snapshot", str(store), "--json")
        self.assertEqual(proc.returncode, 3)
        data = payload(proc)
        self.assertFalse(data["snapshot"]["saved"])
        self.assertFalse((store / "snapshots").exists())

    def test_snapshot_not_saved_on_reject(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": NUMBER_BAD})
        store = self.tmp / "store"
        proc = self.review(b, a, "--snapshot", str(store), "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(payload(proc)["snapshot"]["saved"])
        self.assertFalse((store / "snapshots").exists())

    # ---------------------------------------------------------------- 输出
    def test_human_lists_each_item(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": NUMBER_BAD})
        proc = self.review(b, a)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("保护面：红 1", proc.stdout)
        self.assertIn("sections/01.tex", proc.stdout)
        self.assertIn("PROTECT_NUMBER_CHANGED", proc.stdout)
        self.assertIn("复检（只算新增）", proc.stdout)
        self.assertIn("闭合：paired", proc.stdout)
        self.assertIn("hash_ok", proc.stdout)
        self.assertIn("pass_all", proc.stdout)

    def test_human_needs_review_shows_code_and_line(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": HEADING_BAD})
        proc = self.review(b, a)
        self.assertEqual(proc.returncode, 3)
        self.assertIn("HEADING_MALFORMED", proc.stdout)
        self.assertIn("sections/01.tex:1", proc.stdout)
        self.assertIn("判定：需复核", proc.stdout)

    # ---------------------------------------------------------------- 只读
    def test_review_does_not_write_ledger_into_after(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": BASE})
        proc = self.review(b, a)
        self.assertEqual(proc.returncode, 0)
        self.assertFalse((a / "audit" / "tide-events.ndjson").exists())
        self.assertFalse((a / "audit" / "tide-ledger.md").exists())

    # ---------------------------------------------------------------- 用法
    def test_help_documents_alias(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        proc = subprocess.run(
            [sys.executable, "-m", "factscribe", "review", "--help"],
            cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("protect + style --diff + tide", proc.stdout)
        self.assertIn("不新增判据", proc.stdout)

    def test_missing_directory_is_config_error(self):
        b = make_project(self.tmp / "before", {"sections/01.tex": BASE})
        proc = self.review(b, self.tmp / "does-not-exist")
        self.assertEqual(proc.returncode, 2)

    def test_negative_allow_new_is_config_error(self):
        b, a = self.pair({"sections/01.tex": BASE},
                         {"sections/01.tex": BASE})
        proc = self.review(b, a, "--allow-new", "-1")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
