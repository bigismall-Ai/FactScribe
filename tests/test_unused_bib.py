# -*- coding: utf-8 -*-
"""批 60：UNUSED_BIB 判据（R-11，黄 / exit 3）。

锁六件事：

1. bib 有条目、闭包内从未 `\\cite*` → 黄（exit 3），且报出具体 key；
2. `\\nocite{*}`（整库引用）→ 绿；
3. `\\nocite{key}`（逐条引用）→ 该条不算未用；
4. `bib_allow_unused = ["key"]`（人签白名单）→ 绿；
5. 多条目只报未用的那几条；
6. 空 bib → 绿。

所有样例都在临时目录内合成，不读任何外部盲测集。
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
sys.path.insert(0, str(ROOT))

from factscribe.config import load_config  # noqa: E402

BIB = """@inproceedings{used2020,
  title = {Used Paper},
  doi = {10.1000/used}
}
@inproceedings{stale2020,
  title = {Stale Paper},
  doi = {10.1000/stale}
}
"""

FACT = """[[fact]]
id = "A1"
claim = "样本量"
value = "10"
source = "results/raw.md"
locator = "§一"
confidence = "high"
derived_from = []
"""


def make_project(tmp, body="见 \\cite{used2020}。\n", bib=BIB,
                 allow_unused=None) -> Path:
    root = Path(tmp)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    raw = root / "results" / "raw.md"
    raw.write_text("10\n", encoding="utf-8")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    (root / "facts" / "f.toml").write_text(
        FACT.replace('source = "results/raw.md"',
                     'source = "results/raw.md"\nsource_sha256 = "%s"' % digest),
        encoding="utf-8")
    (root / "sections" / "a.tex").write_text(body, encoding="utf-8")
    (root / "refs.bib").write_text(bib, encoding="utf-8")
    extra = ""
    if allow_unused is not None:
        extra = "bib_allow_unused = [%s]\n" % ", ".join(
            '"%s"' % k for k in allow_unused)
    (root / "paperkit.toml").write_text(
        '[project]\ntitle = "t"\nsections = "sections/*.tex"\n'
        'facts = "facts/*.toml"\nbib = "refs.bib"\n%s' % extra,
        encoding="utf-8")
    (root / "results" / "MANIFEST.toml").write_text(
        '[manifest]\nsigned_by = "test-human"\n'
        'signed_at = "2026-11-08T00:00:00Z"\nversion = 1\n\n[files]\n'
        '"results/raw.md" = "%s"\n' % digest,
        encoding="utf-8")
    return root


def audit(root: Path, *flags):
    proc = subprocess.run([sys.executable, "-m", "factscribe", "audit",
                           str(root), "--json", *flags],
                          cwd=str(ROOT), capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError(proc.stdout[:400] + proc.stderr[:400])
    return proc.returncode, data


def warning_codes(data: dict) -> list[str]:
    return [w["code"] for w in data["warnings"]]


class TestUnusedBib(unittest.TestCase):
    def test_unused_entry_is_yellow_with_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = audit(make_project(tmp))
            self.assertEqual(code, 3, data)
            unused = [w for w in data["warnings"] if w["code"] == "UNUSED_BIB"]
            self.assertEqual(len(unused), 1, data["warnings"])
            self.assertEqual(unused[0]["severity"], "yellow")
            self.assertEqual(unused[0]["token"], "stale2020")
            self.assertTrue(unused[0]["location"].startswith("refs.bib:"))
            self.assertIn("stale2020", unused[0]["message"])
            self.assertEqual(data["summary"]["bib_unused"], ["stale2020"])

    def test_nocite_all_exempts_every_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = audit(make_project(tmp, body="\\nocite{*}\n"))
            self.assertEqual(code, 0, data)
            self.assertNotIn("UNUSED_BIB", warning_codes(data))

    def test_nocite_key_exempts_that_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = audit(make_project(
                tmp, body="\\cite{used2020}\n\\nocite{stale2020}\n"))
            self.assertEqual(code, 0, data)
            self.assertNotIn("UNUSED_BIB", warning_codes(data))

    def test_allow_list_exempts_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = audit(make_project(tmp, allow_unused=["stale2020"]))
            self.assertEqual(code, 0, data)
            self.assertNotIn("UNUSED_BIB", warning_codes(data))

    def test_all_cited_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = audit(make_project(
                tmp, body="\\cite{used2020,stale2020}\n"))
            self.assertEqual(code, 0, data)
            self.assertEqual(data["summary"]["bib_unused"], [])

    def test_partial_unused_reports_only_the_unused(self):
        bib = BIB + """@inproceedings{other2021,
  title = {Other Paper},
  doi = {10.1000/other}
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            code, data = audit(make_project(
                tmp, body="\\cite{used2020,other2021}\n", bib=bib))
            self.assertEqual(code, 3, data)
            unused = [w for w in data["warnings"] if w["code"] == "UNUSED_BIB"]
            self.assertEqual([w["token"] for w in unused], ["stale2020"])
            self.assertEqual(data["summary"]["bib_unused"], ["stale2020"])

    def test_empty_bib_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = audit(make_project(tmp, body="没有引用。\n", bib=""))
            self.assertEqual(code, 0, data)
            self.assertEqual(data["summary"]["bib_entries"], 0)
            self.assertEqual(data["summary"]["bib_unused"], [])

    def test_strict_does_not_change_severity(self):
        """--strict 是全局「黄也当红使」；本码本身仍是 yellow，不改级。"""
        with tempfile.TemporaryDirectory() as tmp:
            code, data = audit(make_project(tmp), "--strict")
            self.assertEqual(code, 1, data)
            unused = [w for w in data["warnings"] if w["code"] == "UNUSED_BIB"]
            self.assertEqual(unused[0]["severity"], "yellow")
            # findings 里仍是 yellow，不是 red
            unresolved = [f for f in data["findings"] if f["code"] == "UNUSED_BIB"]
            self.assertEqual(unresolved[0]["severity"], "yellow")


class TestAllowUnusedConfig(unittest.TestCase):
    """§10 字段表：`bib_allow_unused` 在 v1 与 V3 扁平声明里都能读。"""

    def test_v1_project_reads_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(make_project(tmp, allow_unused=["stale2020"]))
            self.assertEqual(cfg.bib_allow_unused, ["stale2020"])

    def test_v3_flat_schema_reads_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sections").mkdir()
            (root / "sections" / "body.tex").write_text("plain\n", encoding="utf-8")
            (root / "factscribe.toml").write_text(
                'schema = "paperkit-project/3.0"\n'
                'root_tex = "sections/body.tex"\n'
                'bib_allow_unused = ["stale2020", "other2021"]\n',
                encoding="utf-8")
            cfg = load_config(root)
            self.assertTrue(cfg.is_v3)
            self.assertEqual(cfg.bib_allow_unused, ["stale2020", "other2021"])
            self.assertFalse([w for w in cfg.warnings
                              if w["code"] == "CONFIG_UNKNOWN_FIELD"])


if __name__ == "__main__":
    unittest.main()
