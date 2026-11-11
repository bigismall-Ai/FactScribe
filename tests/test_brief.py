# -*- coding: utf-8 -*-
"""批 126：写作简报 `factscribe brief` 的契约测试（全离线）。

覆盖：

* 五节标题逐字齐全，顺序固定；
* 夹具项目（2 节、3 条 fact、2 条术语）输出含全部 fact id / claim / value；
* 出现 ``\\fact{`` 绑定提示；
* 术语正名与禁用变体都在；
* 节清单按 `main.tex` 的 ``\\input`` 顺序（不是文件名排序）；
* 每节给出当前标题与已有事实条数；
* §2 只列 claim 与 value，不泄露 source 路径；
* ``--section`` 过滤节清单；fact id 前缀过滤不到时全列并在文首说明；
* fact id 前缀能命中时只列命中项；
* 同输入双跑逐字节一致；
* 没有 facts 的项目 exit 2，不输出空简报；
* ``--out`` 落盘内容与 stdout 逐字节一致；
* ``--json`` 结构与 ``--section`` 匹配不到时的报错。
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

PROJECT_TOML = """[project]
title = "写作简报夹具"
sections = "sections/*.tex"
facts = "facts/*.toml"
"""

MAIN_TEX = r"""\documentclass{article}
\begin{document}
\input{sections/02_zeta}
\input{sections/01_alpha}
\end{document}
"""

ALPHA_TEX = r"""\section{Alpha claim}
The rate is 3/4\fact{A1}; the same number appears again as 3/4\fact{A1},
and the baseline is 0.75\fact{A2}.
"""

ZETA_TEX = r"""\section{Zeta result}
Only one fact is used here: 12 runs\fact{B1}.
"""

CLAIMS = {"A1": ("第一条主张", "3/4"), "A2": ("第二条主张", "0.75"),
          "B1": ("第三条主张", "12 次")}


def facts_toml(ids=("A1", "A2", "B1")) -> str:
    blocks = []
    for fid in ids:
        claim, value = CLAIMS.get(fid, ("主张 %s" % fid, "1"))
        blocks.append(
            '[[fact]]\nid = "%s"\nclaim = "%s"\nvalue = "%s"\n'
            'source = "EVIL-SOURCE-%s.md"\n' % (fid, claim, value, fid))
    return "\n".join(blocks)


FACTS_TOML = facts_toml()

GLOSSARY_TSV = """canonical\taliases(en)\taliases(cn)\tcategory\tblocked(cn)
机械闸门\tmechanical gate\t\t论文术语\t机械门
证据送达\tevidence delivery\t\t论文术语\t证据投递
"""


def cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        cwd=str(cwd or ROOT), env=env, capture_output=True, text=True)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_project(base: Path, *, facts: bool = True,
                 glossary: bool = True,
                 fact_ids: tuple = ("A1", "A2", "B1")) -> Path:
    root = Path(base)
    write(root / "paperkit.toml", PROJECT_TOML)
    write(root / "main.tex", MAIN_TEX)
    write(root / "sections" / "01_alpha.tex", ALPHA_TEX)
    write(root / "sections" / "02_zeta.tex", ZETA_TEX)
    if facts:
        write(root / "facts" / "facts.toml", facts_toml(fact_ids))
    else:
        (root / "facts").mkdir(parents=True, exist_ok=True)
    if glossary:
        write(root / "glossary.tsv", GLOSSARY_TSV)
    return root


class BriefTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.project = make_project(self.tmp / "proj")
        self.text = self.run_brief()

    def run_brief(self, *extra: str, project: Path | None = None) -> str:
        proc = cli("brief", str(project or self.project), *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout


# --------------------------------------------------------------------------
# 1. 五节结构
# --------------------------------------------------------------------------

class TestStructure(BriefTestCase):
    def test_five_section_headings_are_exact(self):
        expected = ["## 1. 写作任务", "## 2. 可用主张与数字", "## 3. 术语表",
                    "## 4. 硬约束", "## 5. 验收"]
        positions = [self.text.find(h) for h in expected]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))

    def test_starts_with_markdown_title(self):
        self.assertTrue(self.text.startswith("# 写作简报"))
        self.assertIn("写作简报夹具", self.text.splitlines()[0])


# --------------------------------------------------------------------------
# 2. 可用主张与数字
# --------------------------------------------------------------------------

class TestFacts(BriefTestCase):
    def test_all_fact_ids_present(self):
        for fid in ("A1", "A2", "B1"):
            self.assertIn(fid, self.text)

    def test_all_claims_present(self):
        for claim in ("第一条主张", "第二条主张", "第三条主张"):
            self.assertIn(claim, self.text)

    def test_all_values_present(self):
        for value in ("3/4", "0.75", "12 次"):
            self.assertIn(value, self.text)

    def test_fact_binding_hint(self):
        self.assertIn("\\fact{", self.text)
        self.assertIn("正文必须用", self.text)
        self.assertIn("`\\fact{id}`", self.text)

    def test_source_paths_are_not_listed(self):
        # 这是给写作看的材料，不是审计报告：source 一律不出现。
        self.assertNotIn("EVIL-SOURCE", self.text)


# --------------------------------------------------------------------------
# 3. 术语表
# --------------------------------------------------------------------------

class TestTerms(BriefTestCase):
    def test_canonicals_present(self):
        self.assertIn("机械闸门", self.text)
        self.assertIn("证据送达", self.text)

    def test_blocked_variants_present(self):
        self.assertIn("机械门", self.text)
        self.assertIn("证据投递", self.text)

    def test_single_canonical_rule_is_stated(self):
        self.assertIn("同一概念全篇只用正名", self.text)


# --------------------------------------------------------------------------
# 4. 节清单
# --------------------------------------------------------------------------

class TestSections(BriefTestCase):
    def test_order_follows_main_tex_input(self):
        # main.tex 先 input 02_zeta，再 input 01_alpha；文件名排序恰好相反。
        self.assertLess(self.text.index("02_zeta.tex"),
                        self.text.index("01_alpha.tex"))

    def test_section_titles_present(self):
        self.assertIn("Alpha claim", self.text)
        self.assertIn("Zeta result", self.text)

    def test_fact_count_is_per_section_distinct_bindings(self):
        # 01_alpha 绑定 A1（重复两次）与 A2 → 2 条；02_zeta 绑定 B1 → 1 条。
        # 批 128：表尾多了「篇幅预算」列，没有 [budget] 时写 —。
        rows = [line for line in self.text.splitlines()
                if line.startswith("|") and "sections/" in line]
        alpha = next(r for r in rows if "01_alpha.tex" in r)
        zeta = next(r for r in rows if "02_zeta.tex" in r)
        self.assertTrue(alpha.rstrip().endswith("| 2 | — |"), alpha)
        self.assertTrue(zeta.rstrip().endswith("| 1 | — |"), zeta)


# --------------------------------------------------------------------------
# 5. --section 过滤
# --------------------------------------------------------------------------

class TestSectionFilter(BriefTestCase):
    def test_filter_keeps_only_matching_section(self):
        text = self.run_brief("--section", "01")
        self.assertIn("01_alpha.tex", text)
        self.assertNotIn("02_zeta.tex", text)

    def test_filter_lists_all_facts_with_note_when_prefix_misses(self):
        text = self.run_brief("--section", "01")
        self.assertIn("无法按 id 前缀", text)
        self.assertIn("全列", text)
        # 文首说明：出现在第一节标题之前。
        self.assertLess(text.index("无法按 id 前缀"), text.index("## 1. 写作任务"))
        for fid in ("A1", "A2", "B1"):
            self.assertIn(fid, text)

    def test_filter_hits_fact_prefix(self):
        project = make_project(self.tmp / "prefix", fact_ids=("04a", "04b", "A9"))
        write(project / "sections" / "04_method.tex",
              r"""\section{Method}
Readings 1\fact{04a} and 2\fact{04b}; unrelated 3\fact{A9}.
""")
        text = self.run_brief("--section", "04", project=project)
        self.assertIn("04a", text)
        self.assertIn("04b", text)
        self.assertNotIn("`A9`", text)
        self.assertNotIn("无法按 id 前缀", text)

    def test_unknown_section_is_config_error(self):
        proc = cli("brief", str(self.project), "--section", "99")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("99", proc.stderr)

    def test_empty_section_is_config_error(self):
        proc = cli("brief", str(self.project), "--section", "")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")


# --------------------------------------------------------------------------
# 6. 确定性、--out、--json
# --------------------------------------------------------------------------

class TestOutput(BriefTestCase):
    def test_two_runs_are_byte_identical(self):
        first = self.run_brief()
        second = self.run_brief()
        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))

    def test_out_file_matches_stdout(self):
        out = self.tmp / "brief.md"
        proc = cli("brief", str(self.project), "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(out.read_text(encoding="utf-8"), self.text)

    def test_json_shape_is_stable(self):
        proc = cli("brief", str(self.project), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["command"], "brief")
        self.assertEqual(data["status"], "ok")
        self.assertEqual([f["id"] for f in data["facts"]], ["A1", "A2", "B1"])
        self.assertEqual([s["file"] for s in data["sections"]],
                         ["sections/02_zeta.tex", "sections/01_alpha.tex"])
        self.assertEqual([s["facts"] for s in data["sections"]], [1, 2])
        self.assertEqual([t["canonical"] for t in data["terms"]],
                         ["机械闸门", "证据送达"])
        self.assertNotIn("EVIL-SOURCE", proc.stdout)


# --------------------------------------------------------------------------
# 7. 失败面
# --------------------------------------------------------------------------

class TestFailClosed(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_no_facts_exits_2_without_brief(self):
        project = make_project(self.tmp / "empty", facts=False)
        proc = cli("brief", str(project))
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("facts 为空", proc.stderr)

    def test_missing_project_exits_2(self):
        proc = cli("brief", str(self.tmp / "nope"))
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
