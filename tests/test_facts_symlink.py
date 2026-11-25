# -*- coding: utf-8 -*-
"""账本侧软链信任根闸：越界判红、界内照旧、成环／断链明确报出。

被测口径（SPEC-V3.0 §8.1 本批新增两码）：
- `FACT_FILE_OUTSIDE_PROJECT`（red，exit 5）：facts/*.toml 的真实目标越出
  项目根。账本不收它——此前 `p.is_file()` 跟随软链直接读入，审计拿信任根外
  的数字当账，且没有任何码（fail-open）。
- `FACT_FILE_UNRESOLVED`（red，exit 5）：facts/*.toml 的软链成环或断链，真实
  目标不可解。此前被 `is_file()` 静默跳过（无码、无位置）。

正例锁：指向项目内的软链照旧入账，审计读数与「同内容的普通文件」逐项相同。

用例在任何解释器上都能跑（3.10–3.14 同一条结论）：软链判定走
`os.path.realpath(strict=True)`，跨版本行为一致。
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

BIB_OK = """@inproceedings{chen2023,
  title = {A Paper},
  doi = {10.18653/v1/2023.emnlp-main.741}
}
"""

FACT_TOML = """[[fact]]
id = "A1"
claim = "开臂 resolved（16 题）"
value = "10/16"
source = "results/raw.md"
source_sha256 = "%s"
locator = "§二"
confidence = "high"
derived_from = []
"""

TEX = "\\fact{A1} 开臂 10/16。\\cite{chen2023}\n"

FINDING_KEYS = ("findings", "issues", "warnings", "hints")


def make_project(root: Path) -> Path:
    """最小 v1 项目（合法 TOML）：一个合法事实 + 一节正文 + 一条 bib。"""
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    raw = root / "results" / "raw.md"
    raw.write_text("open 10/16 closed 8/16; total 56.25%\n", encoding="utf-8")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    (root / "facts" / "f.toml").write_text(FACT_TOML % digest, encoding="utf-8")
    (root / "sections" / "a.tex").write_text(TEX, encoding="utf-8")
    (root / "refs.bib").write_text(BIB_OK, encoding="utf-8")
    (root / "factscribe.toml").write_text(
        '[project]\ntitle = "t"\nauthors = ["a"]\n'
        'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
        'bib = "refs.bib"\nbuild = ""\n', encoding="utf-8")
    (root / "results" / "MANIFEST.toml").write_text(
        "[manifest]\nsigned_by = \"test-human\"\n"
        "signed_at = \"2026-11-07T00:00:00Z\"\nversion = 1\n\n[files]\n"
        '"results/raw.md" = "%s"\n' % digest, encoding="utf-8")
    return root


def audit(root: Path, cmd: str = "audit"):
    proc = subprocess.run(
        [sys.executable, "-m", "factscribe", cmd, str(root), "--json"],
        capture_output=True, text=True, cwd=str(ROOT))
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = None
    return proc, payload


def codes(payload, key="issues"):
    return [(i.get("code"), i.get("severity"), i.get("location"))
            for i in (payload.get(key) or [])]


def link(target: Path, link_path: Path) -> None:
    """建软链；建不了（Windows 未开开发者模式等）就跳过用例，不许假装通过。"""
    try:
        os.symlink(str(target), str(link_path))
    except (OSError, NotImplementedError, AttributeError) as exc:
        raise unittest.SkipTest("本机不能建软链：%s" % exc)


class TestFactsSymlinkTrustRoot(unittest.TestCase):
    """账本软链三类输入：界外判红、界内照旧、不可解明确报出；三类都不崩。"""

    # ---- 1. 界外软链：判红、明确 code 与位置、且不进账 ----

    def test_outside_symlink_is_red_with_code_and_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp) / "proj")
            out = Path(tmp) / "outside.toml"
            out.write_text((root / "facts" / "f.toml").read_text(encoding="utf-8"),
                           encoding="utf-8")
            link(out, root / "facts" / "link.toml")
            proc, payload = audit(root)
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            hits = [c for c in codes(payload) if c[0] == "FACT_FILE_OUTSIDE_PROJECT"]
            self.assertEqual(len(hits), 1, payload)
            self.assertEqual(hits[0][1], "red")
            self.assertEqual(hits[0][2], "facts/link.toml")

    def test_outside_symlink_is_not_loaded_into_the_ledger(self):
        """界外文件不许进账：此前读进来 facts=2（两条 A1）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp) / "proj")
            out = Path(tmp) / "outside.toml"
            out.write_text((root / "facts" / "f.toml").read_text(encoding="utf-8"),
                           encoding="utf-8")
            link(out, root / "facts" / "link.toml")
            proc, payload = audit(root)
            self.assertEqual(payload["summary"]["facts"], 1, payload)
            self.assertNotIn("DUPLICATE_ID", [c[0] for c in codes(payload)], payload)

    def test_outside_only_ledger_is_not_masked_as_empty_ledger(self):
        """账被拒收后不许退化成「空账」配置错（exit 2）——那是两回事。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp) / "proj")
            out = Path(tmp) / "outside.toml"
            out.write_text((root / "facts" / "f.toml").read_text(encoding="utf-8"),
                           encoding="utf-8")
            (root / "facts" / "f.toml").unlink()
            link(out, root / "facts" / "link.toml")
            proc, payload = audit(root)
            self.assertNotEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("FACT_FILE_OUTSIDE_PROJECT",
                          [c[0] for c in codes(payload)], payload)

    # ---- 2. 界内软链：正常纳入，行为与修复前一字不差 ----

    def test_inside_symlink_is_included_like_a_plain_file(self):
        """正例锁：界内软链的审计读数与同内容普通文件逐项相同。"""
        with tempfile.TemporaryDirectory() as tmp:
            plain = make_project(Path(tmp) / "plain")
            linky = make_project(Path(tmp) / "linky")
            data = linky / "data"
            data.mkdir()
            real = data / "real.toml"
            real.write_text((linky / "facts" / "f.toml").read_text(encoding="utf-8"),
                            encoding="utf-8")
            (linky / "facts" / "f.toml").unlink()
            link(real, linky / "facts" / "link.toml")
            p1, d1 = audit(plain)
            p2, d2 = audit(linky)
            self.assertEqual(p1.returncode, p2.returncode, p2.stdout + p2.stderr)
            self.assertEqual(d1["summary"]["facts"], d2["summary"]["facts"])
            for key in FINDING_KEYS:
                self.assertEqual(d1[key], d2[key], key)

    def test_inside_symlink_still_counts_as_a_fact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp) / "proj")
            data = root / "data"
            data.mkdir()
            real = data / "real.toml"
            real.write_text((root / "facts" / "f.toml").read_text(encoding="utf-8"),
                            encoding="utf-8")
            (root / "facts" / "f.toml").unlink()
            link(real, root / "facts" / "link.toml")
            proc, payload = audit(root)
            self.assertEqual(payload["summary"]["facts"], 1, payload)
            self.assertEqual(
                [c[0] for c in codes(payload) if c[0].startswith("FACT_FILE")], [])

    # ---- 3. 成环：明确报出，不静默丢 ----

    def test_symlink_cycle_is_reported_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp) / "proj")
            link(root / "facts" / "b.toml", root / "facts" / "a.toml")
            link(root / "facts" / "a.toml", root / "facts" / "b.toml")
            proc, payload = audit(root)
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            hits = [c for c in codes(payload) if c[0] == "FACT_FILE_UNRESOLVED"]
            self.assertEqual(len(hits), 2, payload)
            self.assertEqual([c[2] for c in hits], ["facts/a.toml", "facts/b.toml"])
            for _code, severity, _loc in hits:
                self.assertEqual(severity, "red")

    def test_symlink_cycle_keeps_the_legal_facts(self):
        """成环的那两个文件没进账，但同目录的合法账本照旧入账。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp) / "proj")
            link(root / "facts" / "b.toml", root / "facts" / "a.toml")
            link(root / "facts" / "a.toml", root / "facts" / "b.toml")
            proc, payload = audit(root)
            self.assertEqual(payload["summary"]["facts"], 1, payload)

    # ---- 4. 断链：明确报出（软链不可解的另一半） ----

    def test_dangling_symlink_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp) / "proj")
            link(root / "facts" / "nope.toml", root / "facts" / "dangle.toml")
            proc, payload = audit(root)
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            hits = [c for c in codes(payload) if c[0] == "FACT_FILE_UNRESOLVED"]
            self.assertEqual(len(hits), 1, payload)
            self.assertEqual(hits[0][2], "facts/dangle.toml")

    # ---- 5. 三类输入都不崩（不许 exit 4 内部错误） ----

    def test_none_of_the_three_inputs_crashes_the_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp) / "proj")
            out = Path(tmp) / "outside.toml"
            out.write_text((root / "facts" / "f.toml").read_text(encoding="utf-8"),
                           encoding="utf-8")
            link(out, root / "facts" / "link.toml")
            link(root / "facts" / "b.toml", root / "facts" / "a.toml")
            link(root / "facts" / "a.toml", root / "facts" / "b.toml")
            proc, payload = audit(root)
            self.assertNotEqual(proc.returncode, 4, proc.stdout + proc.stderr)
            self.assertIsNotNone(payload, proc.stdout + proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    # ---- 6. check 面同样判红（不许只在 audit 报） ----

    def test_check_command_reports_the_outside_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp) / "proj")
            out = Path(tmp) / "outside.toml"
            out.write_text((root / "facts" / "f.toml").read_text(encoding="utf-8"),
                           encoding="utf-8")
            link(out, root / "facts" / "link.toml")
            proc, payload = audit(root, cmd="check")
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertIn("FACT_FILE_OUTSIDE_PROJECT",
                          [c[0] for c in codes(payload)], payload)


if __name__ == "__main__":
    unittest.main()
