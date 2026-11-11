# -*- coding: utf-8 -*-
"""批 135：`UNSCANNED_TEX` 只报「确有可审计内容」的闭包外 `.tex`。

只含导言区命令与 `\\input` 的主文件没东西可扫——报「未扫描」是噪声。
豁免口径（写死，见 `texscan.has_auditable_content`）：去掉注释、去掉
`\\begin{document}` 之前的一切之后，须**同时**满足

1. 正文为空或只剩空白/命令；
2. 没有阿拉伯数字 token（按现有数字抽取口径，命令参数不算）；
3. 没有 `\\fact{}`、没有 `\\cite` 家族、没有 `\\label`/`\\ref` 家族。

任一条不满足而文件又不在闭包里 → 照旧报黄（fail-closed 不变）。

跑法（仓根）：env PYTHONPATH=src python3 -m unittest discover -s tests
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

BIB_OK = """@inproceedings{chen2023,
  title = {A Paper},
  doi = {10.18653/v1/2023.emnlp-main.741}
}
"""

FACTS = """[[fact]]
id = "X1"
claim = "epochs"
value = "42"
source = "results/raw.md"
locator = "§一"
confidence = "low"
derived_from = []
"""

SECTION_OK = "run 42\\fact{X1}\\cite{chen2023}\n"

PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage[T1]{fontenc}
\providecommand{\fact}[1]{}
\begin{document}
\maketitle
\input{sections/a}
\end{document}
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_project(tmp, extra=None):
    """最小 v1 项目：一条 fact、一个章节、一个闭包外的 .tex（extra）。"""
    root = Path(tmp)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    raw = root / "results" / "raw.md"
    raw.write_text("epochs 42\n", encoding="utf-8")
    digest = _sha(raw)
    (root / "facts" / "f.toml").write_text(
        FACTS.replace('source = "results/raw.md"',
                      'source = "results/raw.md"\nsource_sha256 = "%s"' % digest),
        encoding="utf-8")
    (root / "sections" / "a.tex").write_text(SECTION_OK, encoding="utf-8")
    (root / "refs.bib").write_text(BIB_OK, encoding="utf-8")
    (root / "results" / "MANIFEST.toml").write_text(
        "[manifest]\nsigned_by = \"test-human\"\n"
        "signed_at = \"2026-11-07T00:00:00Z\"\nversion = 1\n\n[files]\n"
        '"results/raw.md" = "%s"\n' % digest, encoding="utf-8")
    (root / "paperkit.toml").write_text(
        '[project]\ntitle = "t"\nauthors = ["a"]\n'
        'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
        'bib = "refs.bib"\nbuild = ""\n', encoding="utf-8")
    for name, bytes_ in (extra or {}).items():
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(bytes_, bytes):
            dest.write_bytes(bytes_)
        else:
            dest.write_text(bytes_, encoding="utf-8")
    return root


def audit(root):
    proc = subprocess.run(
        [sys.executable, "-m", "factscribe", "audit", str(root), "--json"],
        capture_output=True, text=True, cwd=str(ROOT),
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))
    return proc.returncode, json.loads(proc.stdout)


def codes(data):
    # `issues` 只装红/致命，黄项在 `warnings` 里；本组测试按「出没出现」判。
    return [i["code"] for i in data.get("issues", []) + data.get("warnings", [])]


class TestUnscannedTexNoise(unittest.TestCase):
    """豁免：没有可审计内容的闭包外 .tex 不报。"""

    def _one(self, extra):
        with tempfile.TemporaryDirectory() as tmp:
            return audit(make_project(tmp, extra))

    def test_preamble_only_main_file_is_clean(self):
        """只有导言区命令与 \\input 的主文件 → 不报（本批要修的那条噪声）。"""
        code, data = self._one({"main.tex": PREAMBLE})
        self.assertEqual(code, 0, data)
        self.assertEqual(codes(data), [])

    def test_comment_numbers_do_not_count_as_content(self):
        """注释里的数字不算「有内容」。"""
        code, data = self._one({
            "main.tex": PREAMBLE + "% 2020 年的草稿，1234 个 token\n",
            "notes.tex": "% 42\\fact{X1}\\cite{chen2023}\n",
        })
        self.assertEqual(code, 0, data)
        self.assertEqual(codes(data), [])

    def test_command_argument_digits_do_not_count(self):
        """命令参数里的数字（11pt、1in）不算「有内容」。"""
        code, data = self._one({
            "layout.tex": "\\vspace{1in}\\fontsize{11}{13}\\selectfont\n",
        })
        self.assertEqual(code, 0, data)
        self.assertEqual(codes(data), [])

    def test_command_only_section_file_is_clean(self):
        """没有 \\begin{document} 的章节件，只有命令也没有内容 → 不报。"""
        code, data = self._one({
            "extra/empty.tex": "\\section{Intro}\n\\vspace{1in}\n"})
        self.assertEqual(code, 0, data)
        self.assertEqual(codes(data), [])


class TestUnscannedTexFailClosed(unittest.TestCase):
    """仍有可审计内容而文件不在闭包里 → 照旧报黄（exit 3）。"""

    def _one(self, extra):
        with tempfile.TemporaryDirectory() as tmp:
            return audit(make_project(tmp, extra))

    def test_body_number_outside_closure_is_still_reported(self):
        code, data = self._one({"extra/tables.tex": "\\begin{tabular}{ll}42 & x\\\\end{tabular}\n"})
        self.assertEqual(code, 3, data)
        self.assertEqual(codes(data), ["UNSCANNED_TEX"])
        self.assertEqual(data["warnings"][0]["location"], "extra/tables.tex")

    def test_fact_marker_outside_closure_is_still_reported(self):
        code, data = self._one({"extra/draft.tex": "文字\\fact{X1}没有数字\n"})
        self.assertEqual(code, 3, data)
        self.assertEqual(codes(data), ["UNSCANNED_TEX"])

    def test_cite_outside_closure_is_still_reported(self):
        code, data = self._one({"extra/related.tex": "前人工作\\cite{chen2023}\n"})
        self.assertEqual(code, 3, data)
        self.assertEqual(codes(data), ["UNSCANNED_TEX"])

    def test_label_and_ref_outside_closure_are_still_reported(self):
        for body in ("\\label{sec:x}\n", "见第\\ref{sec:x}节\n"):
            with self.subTest(body=body):
                code, data = self._one({"extra/x.tex": body})
                self.assertEqual(code, 3, data)
                self.assertEqual(codes(data), ["UNSCANNED_TEX"])

    def test_prose_without_numbers_outside_closure_is_still_reported(self):
        """正文有字就报（条件一不放宽）——fail-closed。"""
        code, data = self._one({"extra/prose.tex": "We thank the reviewers.\n"})
        self.assertEqual(code, 3, data)
        self.assertEqual(codes(data), ["UNSCANNED_TEX"])

    def test_unreadable_file_is_still_reported(self):
        """读不了的文件照旧报（不因豁免而静默放行）。"""
        code, data = self._one({"extra/bad.tex": b"\xff\xfe\x00bad"})
        self.assertEqual(code, 3, data)
        self.assertEqual(codes(data), ["UNSCANNED_TEX"])


if __name__ == "__main__":
    unittest.main()
