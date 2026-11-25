# -*- coding: utf-8 -*-
r"""F4 全仓扫描续集：用户内容载体的换行保真（读不翻译、写不翻译）。

首轮（F4，tests/test_newline_fidelity.py）盯的是**已知清单**里的几个写
盘点；这一轮按「全仓枚举」做：把仓内所有对用户内容载体（正文 .tex、
.bib、factscribe.toml、事实账 facts/*.toml、术语表）的文本读写点逐个
分档，漏网的补齐，每条留下可复核的证据。

四组证据：

1. **接口层读**：正文经 config 装载（load_sections）后行尾仍是原样
   （CRLF 不被翻译成 LF）——引擎下发给编辑器的必须是真字节。
2. **分析层不漂**：同一项目，.tex 用 LF 与用 CRLF 两版，审计发现逐条
   相同、退出码相同——读侧改成不翻译之后，分析口径没有被带偏。
3. **写回逐字节**：正文、.bib、factscribe.toml、事实账改写、潮汐账本
   追写这几条链，落盘字节与原始字节逐字节相同；被改的那一行也不换行尾。
4. **参数证据**：目标调用点确实以 newline="" 打开文件（写侧），读侧确实
   按原样读（newline=""）。

**Windows 真机端到端仍未验证**：本机是 macOS，仓库 CI 矩阵只有 ubuntu。
POSIX 上默认文本模式的换行翻译是恒等变换，所以「Windows 上会变成
CRLF/CRLFCRLF」这一段是**机制链核实**（源码 + CPython 文档语义），不是
本机实跑。

跑法（仓根）：python3 -m unittest discover -s tests -p "test_newline_fidelity_sweep.py"
"""
from __future__ import annotations

import builtins
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "integrations" / "factscribe-legal"))

from factscribe.audit import _aggregate_exit, run_audit  # noqa: E402
from factscribe.config import load_config, load_facts, load_sections  # noqa: E402
from factscribe.projects import _rewrite_project_table  # noqa: E402
from factscribe.terms import load_glossary  # noqa: E402
from factscribe.textio import read_text_exact, to_lf  # noqa: E402
from factscribe.tide import _append_ledger  # noqa: E402
from factscribe.workbench import project_data  # noqa: E402
from factscribe_legal.ledger_maint import mark_dup_ok  # noqa: E402

FACTSCRIBE_TOML_TEXT = (
    "[project]\r\n"
    "title = \"换行保真测试\"\r\n"
    "sections = \"sections/*.tex\"\r\n"
    "facts = \"facts/*.toml\"\r\n"
    "bib = \"refs.bib\"\r\n"
)
FACTSCRIBE_TOML = FACTSCRIBE_TOML_TEXT.encode("utf-8")

FACT_TOML = (
    b"[[fact]]\n"
    b"id = \"A1\"\n"
    b"claim = \"accuracy\"\n"
    b"value = \"56.25%\"\n"
    b"source = \"results/one.md\"\n"
    b"locator = \"L1\"\n"
    b"confidence = \"high\"\n"
)

LF_TEX = (b"\\section{Intro}\n"
          b"\n"
          b"We measured 42.0\\% accuracy in the study.\n"
          b"We cite \\cite{missing2020}.\n")


def _crlf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def make_project(base: Path, tex_bytes: bytes = LF_TEX,
                 toml_bytes: bytes = FACTSCRIBE_TOML) -> Path:
    """造一个最小项目：正文 .tex（给定字节）、事实账、bib、声明。"""
    root = base / "paper"
    (root / "sections").mkdir(parents=True)
    (root / "facts").mkdir(parents=True)
    (root / "results").mkdir(parents=True)
    (root / "factscribe.toml").write_bytes(toml_bytes)
    (root / "facts" / "01-core.toml").write_bytes(FACT_TOML)
    (root / "results" / "one.md").write_bytes(b"evidence\n")
    (root / "sections" / "01-intro.tex").write_bytes(tex_bytes)
    (root / "refs.bib").write_bytes(
        b"@article{alpha2020,\r\n  title = {Alpha},\r\n"
        b"  doi = {10.1000/alpha}\r\n}\r\n")
    return root


class _OpenRecorder:
    """记录所有 open() 调用：路径、模式、newline 参数。"""

    def __init__(self):
        self.calls = []
        self._real_open = builtins.open

    def __call__(self, file, mode="r", *args, **kwargs):
        self.calls.append((str(file), mode, kwargs.get("newline", None)))
        return self._real_open(file, mode, *args, **kwargs)

    def for_path(self, path: Path):
        return [(mode, newline) for (f, mode, newline) in self.calls
                if os.path.abspath(f) == os.path.abspath(str(path))]


class _PatchedOpen:
    def __init__(self, recorder: _OpenRecorder):
        self._recorder = recorder
        self._real = builtins.open

    def __enter__(self):
        builtins.open = self._recorder
        return self._recorder

    def __exit__(self, *exc):
        builtins.open = self._real
        return False


class InterfaceReadTest(unittest.TestCase):
    """接口层读：行尾不能在下发到编辑器之前就被翻译掉。"""

    def test_load_sections_keeps_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), tex_bytes=_crlf(LF_TEX))
            cfg = load_config(root)
            sections = dict(load_sections(cfg))
            text = sections["sections/01-intro.tex"]
            self.assertIn("\r\n", text)
            self.assertEqual(len(text.splitlines()), len(LF_TEX.splitlines()))

    def test_project_data_serves_original_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), tex_bytes=_crlf(LF_TEX))
            data = project_data(root)
            served = [row["text"] for row in data["sections"]
                      if row["file"] == "sections/01-intro.tex"][0]
            self.assertIn("\r\n", served)
            self.assertEqual(served.count("\r\n"), LF_TEX.count(b"\n"))

    def test_read_call_site_opens_with_newline_empty(self):
        """读侧证据：目标调用点是以 newline="" 打开的（不翻译）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), tex_bytes=_crlf(LF_TEX))
            cfg = load_config(root)
            recorder = _OpenRecorder()
            with _PatchedOpen(recorder):
                load_sections(cfg)
            calls = recorder.for_path(root / "sections" / "01-intro.tex")
            self.assertTrue(calls, "正文没有经过 open() 读盘")
            for mode, newline in calls:
                self.assertEqual(newline, "",
                                 "读用户内容必须以 newline=\"\" 打开（不翻译换行）")


class AnalysisInvarianceTest(unittest.TestCase):
    """分析层不漂：CRLF 版与 LF 版的判定必须逐条相同。"""

    def _audit_surface(self, root: Path):
        cfg = load_config(root)
        facts = load_facts(cfg)
        sections = load_sections(cfg)
        red, yellow, hints, summary, unresolved = run_audit(
            cfg, facts, sections, resolve=False)
        code = _aggregate_exit(red, yellow, False,
                               integrity_first=cfg.is_v3)
        rows = [i.as_dict() for i in list(red) + list(yellow) + list(hints)]
        return code, rows

    def test_audit_findings_identical_for_crlf_twin(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            lf_root = make_project(base / "lf", tex_bytes=LF_TEX)
            crlf_root = make_project(base / "crlf", tex_bytes=_crlf(LF_TEX))
            lf_code, lf_rows = self._audit_surface(lf_root)
            crlf_code, crlf_rows = self._audit_surface(crlf_root)
            self.assertTrue(lf_rows, "这个用例本该有发现，否则比对是空的")
            self.assertEqual(lf_code, crlf_code)
            self.assertEqual(lf_rows, crlf_rows)

    def test_brief_identical_for_crlf_twin(self):
        from factscribe.brief import build_brief
        from factscribe.brief import payload as brief_payload
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            lf_root = make_project(base / "lf", tex_bytes=LF_TEX)
            crlf_root = make_project(base / "crlf", tex_bytes=_crlf(LF_TEX))
            lf = brief_payload(build_brief(lf_root))
            crlf = brief_payload(build_brief(crlf_root))
            self.assertEqual(json.dumps(lf, ensure_ascii=False, sort_keys=True),
                             json.dumps(crlf, ensure_ascii=False, sort_keys=True))


class WriteBackTest(unittest.TestCase):
    """写回逐字节：改一行也不许动别的字节、更不许换行尾。"""

    def test_factscribe_toml_rewrite_keeps_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "factscribe.toml"
            path.write_bytes(FACTSCRIBE_TOML)
            before = path.read_bytes()
            _rewrite_project_table(path, {"description": '"new"'})
            after = path.read_bytes()
            self.assertNotEqual(before, after)
            self.assertIn(b'description = "new"\r\n', after)
            kept_before = [ln for ln in before.split(b"\r\n") if ln]
            kept_after = [ln for ln in after.split(b"\r\n") if ln]
            for line in kept_before:
                if line.startswith(b"description"):
                    continue
                self.assertIn(line, kept_after)
            self.assertEqual(after.count(b"\n"), after.count(b"\r\n"))

    def test_legal_ledger_rewrite_keeps_crlf(self):
        """legal 集成件的原地改账：facts/*.toml 的 CRLF 不能被改掉。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            (root / "facts").mkdir(parents=True)
            body = (
                b"[[fact]]\r\n"
                b"id = \"A1\"\r\n"
                b"claim = \"accuracy\"\r\n"
                b"value = \"56.25%\"\r\n"
                b"source = \"results/one.md\"\r\n"
                b"locator = \"L1\"\r\n"
                b"\r\n"
                b"[[fact]]\r\n"
                b"id = \"A2\"\r\n"
                b"claim = \"another claim\"\r\n"
                b"value = \"56.25%\"\r\n"
                b"source = \"results/one.md\"\r\n"
                b"locator = \"L2\"\r\n"
            )
            ledger = root / "facts" / "01-core.toml"
            ledger.write_bytes(body)
            changed = mark_dup_ok(str(root))
            self.assertTrue(changed, "同值事实应当被标 dup_ok")
            after = ledger.read_bytes()
            self.assertIn(b"dup_ok = true\r\n", after)
            self.assertEqual(after.count(b"\n"), after.count(b"\r\n"),
                             "不能混进裸 LF 行尾")
            for line in (b'id = "A1"', b'claim = "another claim"',
                         b'value = "56.25%"'):
                self.assertIn(line, after)

    def test_legal_ledger_scan_detects_crlf_facts(self):
        """读侧：CRLF 的事实账照样能扫出同值事实（正则认两种行尾）。"""
        from factscribe_legal.facts_ledger import scan_dupes
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            (root / "facts").mkdir(parents=True)
            (root / "facts" / "01-core.toml").write_bytes(
                b"[[fact]]\r\nid = \"A1\"\r\nvalue = \"1\"\r\nclaim = \"x\"\r\n"
                b"\r\n[[fact]]\r\nid = \"A2\"\r\nvalue = \"1\"\r\nclaim = \"y\"\r\n")
            dupes, allfacts = scan_dupes(str(root))
            self.assertEqual(len(allfacts), 2)
            # 同值同组的两条事实各自入列（一条 claim 不同 ⇒ 整组是同值组）
            self.assertEqual(len(dupes), 2)

    def test_tide_ledger_append_keeps_crlf(self):
        """潮汐账本追写：行尾跟账本自身走，不造混合行尾。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tide-events.ndjson"
            path.write_bytes(b'{"event": "rise", "tx": "a1"}\r\n')
            _append_ledger(path, [{"event": "rise", "tx": "a2"}])
            after = path.read_bytes()
            self.assertEqual(after.count(b"\n"), after.count(b"\r\n"))
            self.assertTrue(after.endswith(b"\r\n"))
            self.assertEqual(len(after.splitlines()), 2)

    def test_glossary_read_is_crlf_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "glossary.tsv"
            path.write_bytes("accuracy\tacc\t准确率\tmetrics\t\r\n".encode("utf-8"))
            glossary = load_glossary(path)
            self.assertEqual(len(glossary.terms), 1)
            self.assertEqual(glossary.terms[0].canonical, "accuracy")


class PosixBehaviourTest(unittest.TestCase):
    """macOS/Linux 上行为不变：LF 文件的读法与默认文本模式逐字符相同。"""

    def test_lf_read_identical_to_default_text_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.tex"
            path.write_bytes(LF_TEX)
            self.assertEqual(read_text_exact(path), path.read_text(encoding="utf-8"))

    def test_to_lf_is_identity_on_lf_text(self):
        self.assertEqual(to_lf(LF_TEX.decode("utf-8")), LF_TEX.decode("utf-8"))

    def test_split_lines_ignores_crlf_only(self):
        from factscribe.textio import split_lines
        self.assertEqual(split_lines("a\r\nb\nc"), ["a", "b", "c"])

    def test_existing_fidelity_suite_not_loosened(self):
        """首轮的用例不许被改松——文件仍在且原样。"""
        first = ROOT / "tests" / "test_newline_fidelity.py"
        self.assertTrue(first.is_file())
        text = first.read_text(encoding="utf-8")
        self.assertIn("def test_crlf_round_trip_is_byte_identical", text)
        self.assertIn("def test_write_call_sites_open_with_newline_empty", text)


if __name__ == "__main__":
    unittest.main()
