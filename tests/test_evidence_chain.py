# -*- coding: utf-8 -*-
"""批 56：证据链完整性（SPEC §11.6）与新错误码映射的正负测试。

链的三节：
1. `facts.source` 指向 `runs/` 里的运行记录（文件存在）；
2. `source_sha256` 与磁盘现算一致（哈希匹配）；
3. 同目录 `record.json` 回执存在、run_id 对齐、`facts[]` 指向账上存在的 id。

断任一节必须红；benign 链完整必须绿。
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

SUMMARY = '{"run_id": "run-01", "summary": {"on_resolved": 0.625}}\n'

PROJECT = """[project]
name = "chain"
root_tex = "sections/main.tex"
facts = "facts"
bib = "refs.bib"
level = "l1"
number_locale = "period"
signing_mode = "offline_manifest"
"""


def make_project(tmp: str, *, source: bool = True, sha: bool = True,
                 record: bool = True, record_facts=("A1",),
                 record_run_id: str = "run-01",
                 body: str = "On assembly, the rate is \\fact{A1}{62.5\\%}.\n") -> Path:
    root = Path(tmp)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "runs" / "run-01").mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(PROJECT, encoding="utf-8")
    (root / "sections" / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n" + body
        + "\\end{document}\n", encoding="utf-8")
    (root / "refs.bib").write_text("", encoding="utf-8")
    data = root / "runs" / "run-01" / "result.json"
    data.write_text(SUMMARY, encoding="utf-8")
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    lines = [
        'schema = "paperkit-fact/3.0"',
        "[[fact]]",
        'id = "A1"',
        'claim = "On assembly, the rate is 62.5%."',
        'value = "62.5%"',
        'display = ["62.5\\\\%"]',
        'confidence = "high"',
    ]
    if source:
        lines.append('source = "runs/run-01/result.json"')
    if sha:
        lines.append('source_sha256 = "sha256:%s"' % digest)
    (root / "facts" / "facts.toml").write_text("\n".join(lines) + "\n",
                                               encoding="utf-8")
    if record:
        rec = {"run_id": record_run_id,
               "source": "runs/run-01/result.json",
               "source_sha256": "sha256:" + digest,
               "facts": list(record_facts)}
        (root / "runs" / "run-01" / "record.json").write_text(
            json.dumps(rec), encoding="utf-8")
    return root


def run_audit(project: Path):
    proc = subprocess.run([sys.executable, "-m", "factscribe", "audit",
                           str(project), "--json"],
                          cwd=str(ROOT), capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError(proc.stdout[:400] + proc.stderr[:400])
    return proc.returncode, data


def codes_of(data: dict) -> set[str]:
    return {str(f.get("code")) for f in data.get("findings", [])}


class EvidenceChainTest(unittest.TestCase):
    def test_complete_chain_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = run_audit(make_project(tmp))
            self.assertEqual(code, 0, data.get("findings"))
            self.assertEqual(codes_of(data), set())

    def test_break_node_1_no_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = run_audit(make_project(tmp, source=False))
            self.assertEqual(code, 1, data.get("findings"))
            self.assertIn("EVIDENCE_CHAIN_BROKEN", codes_of(data))

    def test_break_node_1_source_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            (root / "runs" / "run-01" / "result.json").unlink()
            code, data = run_audit(root)
            self.assertEqual(code, 1, data.get("findings"))
            self.assertIn("MISSING_SOURCE", codes_of(data))

    def test_break_node_2_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            fact = root / "facts" / "facts.toml"
            text = fact.read_text(encoding="utf-8")
            text = text.replace('source_sha256 = "sha256:',
                                'source_sha256 = "sha256:0000')
            fact.write_text(text, encoding="utf-8")
            code, data = run_audit(root)
            self.assertEqual(code, 1, data.get("findings"))
            self.assertIn("SOURCE_SHA256_MISMATCH", codes_of(data))

    def test_break_node_3_record_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = run_audit(make_project(tmp, record=False))
            self.assertEqual(code, 1, data.get("findings"))
            self.assertIn("EVIDENCE_CHAIN_BROKEN", codes_of(data))

    def test_break_node_3_record_points_elsewhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = run_audit(make_project(tmp, record_facts=("A2",)))
            self.assertEqual(code, 1, data.get("findings"))
            self.assertIn("EVIDENCE_CHAIN_BROKEN", codes_of(data))

    def test_break_node_3_record_run_id_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, data = run_audit(make_project(tmp, record_run_id="run-99"))
            self.assertEqual(code, 1, data.get("findings"))
            self.assertIn("EVIDENCE_CHAIN_BROKEN", codes_of(data))


class NewCodeMappingTest(unittest.TestCase):
    def test_unregistered_frac_is_computed_value(self):
        body = ("On assembly, the rate is \\fact{A1}{62.5\\%}, "
                "i.e. $\\frac{5}{8}$ of the suite.\n")
        with tempfile.TemporaryDirectory() as tmp:
            code, data = run_audit(make_project(tmp, body=body))
            self.assertEqual(code, 1, data.get("findings"))
            self.assertIn("COMPUTED_VALUE_UNREGISTERED", codes_of(data))

    def test_handwritten_table_number_is_crossref(self):
        body = ("On assembly, the rate is \\fact{A1}{62.5\\%}. "
                "See Table 3 for the breakdown.\n")
        with tempfile.TemporaryDirectory() as tmp:
            code, data = run_audit(make_project(tmp, body=body))
            self.assertEqual(code, 3, data.get("findings"))
            self.assertIn("NUMBER_AS_CROSSREF", codes_of(data))

    def test_unknown_fact_schema_is_in_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            (root / "facts" / "facts.toml").write_text(
                'schema = "factscribe-fact/2.9"\n[[fact]]\n'
                'id = "A1"\nclaim = "x"\nvalue = "62.5%"\n',
                encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "factscribe", "audit",
                                   str(root), "--json"],
                                  cwd=str(ROOT), capture_output=True, text=True)
            data = json.loads(proc.stdout)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("FACT_SCHEMA_INVALID", codes_of(data))


if __name__ == "__main__":
    unittest.main()
