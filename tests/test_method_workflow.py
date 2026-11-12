"""方法论产物 → 事实账草稿：批处理脚本的端到端测试。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "method-workflows" / "draft-facts.py"


def run(args, cwd=None):
    env = {"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    return subprocess.run([sys.executable, *args], cwd=cwd or ROOT, env=env,
                          capture_output=True, text=True)


class DraftFactsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        r = run(["-m", "factscribe", "init", str(self.tmp)])
        self.assertEqual(r.returncode, 0, r.stderr)
        (self.tmp / "results" / "swb16.md").write_text(
            "| arm | resolved | total |\n| open | 10 | 16 |\n", encoding="utf-8")
        self.tsv = self.tmp / "claims.tsv"

    def write_tsv(self, rows: str):
        self.tsv.write_text(
            "id\tclaim\tvalue\tsource\tlocator\tconfidence\texpr\tderived_from\n" + rows,
            encoding="utf-8")

    def test_writes_facts_and_manifest_lines(self):
        self.write_tsv(
            "A1\t开臂 resolved\t10/16\tresults/swb16.md\t§二\thigh\t\t\n"
            "A2\t对比臂 resolved\t8/16\tresults/swb16.md\t§二\thigh\t\t\n")
        r = run([str(SCRIPT), str(self.tmp), str(self.tsv)])
        self.assertEqual(r.returncode, 0, r.stderr)
        facts = (self.tmp / "facts" / "01-core.toml").read_text(encoding="utf-8")
        self.assertEqual(facts.count("[[fact]]"), 2)
        self.assertIn("A1", facts)
        self.assertIn("A2", facts)
        # 同一来源只提示一次，且工具不代签
        self.assertEqual(r.stdout.count("MANIFEST.toml"), 1)
        self.assertIn("不代签", r.stdout)

    def test_missing_source_fails_before_writing(self):
        self.write_tsv("A1\t坏行\t1/2\tresults/nope.md\t§一\thigh\t\t\n")
        r = run([str(SCRIPT), str(self.tmp), str(self.tsv)])
        self.assertEqual(r.returncode, 1)
        self.assertIn("source 不存在", r.stderr)
        facts = self.tmp / "facts" / "01-core.toml"
        if facts.exists():
            self.assertEqual(facts.read_text(encoding="utf-8").count("[[fact]]"), 0)

    def test_derived_without_expr_rejected(self):
        self.write_tsv("A1\t派生\t56.25%\tresults/swb16.md\t§三\thigh\t\tA2\n")
        r = run([str(SCRIPT), str(self.tmp), str(self.tsv)])
        self.assertEqual(r.returncode, 1)
        self.assertIn("derived_from", r.stderr)

    def test_dry_run_writes_nothing(self):
        self.write_tsv("A1\t开臂\t10/16\tresults/swb16.md\t§二\thigh\t\t\n")
        r = run([str(SCRIPT), str(self.tmp), str(self.tsv), "--dry-run"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRY", r.stdout)
        facts = self.tmp / "facts" / "01-core.toml"
        if facts.exists():
            self.assertEqual(facts.read_text(encoding="utf-8").count("[[fact]]"), 0)


if __name__ == "__main__":
    unittest.main()
