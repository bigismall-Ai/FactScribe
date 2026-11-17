# -*- coding: utf-8 -*-
"""tests/test_bundle.py —— 投稿工件包（`factscribe bundle`，CARD-G4）。

正负例成对：
* 闭包悬空（main.tex 里塞 \\input{ghost.tex}）→ 清单门拦，exit 1；
* 图缺随图 .csv → 清单门点名不过，exit 1；
* bib 缺唯一键条目 → 清单门点名不过，exit 1；
* 配置写错（kind 不合法／缺字段／坏正则）→ exit 2 并点名哪条；
* 配置生效（附加检查项 ＋ 排除声明）→ 门行为按配置走；
* MANIFEST 逐行可复算；事后改一件 → --verify exit 1 并点名。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe import bundle                                    # noqa: E402
from factscribe.config import load_config                       # noqa: E402

CONFIG_TOML = """[project]
title = "手写最小项目"
authors = ["outsider"]
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\title{手写最小项目}
\\author{outsider}
\\begin{document}
\\input{sections/01-intro}
\\end{document}
"""

SECTION_TEX = """\\section{结果}
开臂解决 10 道\\fact{A1}，对比臂解决 8 道\\fact{A3}。
方法与记号见 \\cite{knuth1984}。
\\begin{figure}[t]
  \\centering
  \\includegraphics{figures/gen/acc.pdf}
  \\caption{两臂解决数}
\\end{figure}
"""

BIB = """@article{knuth1984,
  title   = {Literate Programming},
  author  = {Knuth, Donald E.},
  journal = {The Computer Journal},
  year    = {1984},
  doi     = {10.1093/comjnl/27.2.97}
}
"""

SPEC_TOML = """name = "acc"
kind = "bar"
caption = "两臂解决数"
xlabel = "臂"
ylabel = "解决数"
data = ["A1", "A3"]
labels = ["开臂", "对比臂"]
"""

DATA_MD = """# 汇总表

| 组 | 解决数 |
|---|---|
| 开臂 | 10 |
| 对比臂 | 8 |
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_project(root: Path) -> Path:
    """外行手写最小项目：facts/fig/refs 全手写，不经仓内 helper。

    （source_sha256 用标准库现算——这正是「外行」能照着做的最小动作。）
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (root / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (root / "refs.bib").write_text(BIB, encoding="utf-8")
    (root / "sections").mkdir(exist_ok=True)
    (root / "sections" / "01-intro.tex").write_text(SECTION_TEX, encoding="utf-8")
    (root / "results").mkdir(exist_ok=True)
    (root / "results" / "data.md").write_text(DATA_MD, encoding="utf-8")
    (root / "figures").mkdir(exist_ok=True)
    (root / "figures" / "acc.fig.toml").write_text(SPEC_TOML, encoding="utf-8")
    digest = _sha256(root / "results" / "data.md")
    (root / "facts").mkdir(exist_ok=True)
    (root / "facts" / "01-core.toml").write_text(
        '[[fact]]\n'
        'id = "A1"\n'
        'claim = "开臂解决数"\n'
        'value = "10"\n'
        'source = "results/data.md"\n'
        'source_sha256 = "%s"\n'
        'locator = "汇总表 开臂 行"\n'
        '\n'
        '[[fact]]\n'
        'id = "A3"\n'
        'claim = "对比臂解决数"\n'
        'value = "8"\n'
        'source = "results/data.md"\n'
        'source_sha256 = "%s"\n'
        'locator = "汇总表 对比臂 行"\n' % (digest, digest),
        encoding="utf-8")
    return root


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(**__import__("os").environ, PYTHONPATH=str(ROOT))
    return subprocess.run([sys.executable, "-m", "factscribe", *args],
                          cwd=str(ROOT), env=env, capture_output=True, text=True)


class BundleBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factscribe-bundle-"))
        self.root = make_project(self.tmp / "proj")
        self.out = self.tmp / "pkg"
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def gen(self) -> subprocess.CompletedProcess:
        return run_cli("figures", "gen", str(self.root))

    def bundle(self, *extra: str) -> subprocess.CompletedProcess:
        return run_cli("bundle", str(self.root), "--out", str(self.out), *extra)

    def verify(self, *extra: str) -> subprocess.CompletedProcess:
        return run_cli("bundle", "--verify", str(self.out), *extra)

    def payload(self, proc: subprocess.CompletedProcess) -> dict:
        return json.loads(proc.stdout)


# --------------------------------------------------------------------------
# 正例：端到端跑通
# --------------------------------------------------------------------------

class BundleHappyPathTest(BundleBase):
    def test_gen_bundle_verify_all_exit_zero(self):
        """外行手写项目：gen → bundle → verify 全程 exit 0。"""
        self.assertEqual(self.gen().returncode, 0)
        proc = self.bundle()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((self.out / bundle.MANIFEST_NAME).is_file())
        self.assertTrue((self.out / bundle.INVENTORY_NAME).is_file())
        self.assertEqual(self.verify().returncode, 0)

    def test_manifest_lines_match_bundle_files(self):
        """MANIFEST 行数＝包内文件数（不含 MANIFEST 自身）。"""
        self.gen()
        self.assertEqual(self.bundle().returncode, 0)
        lines = (self.out / bundle.MANIFEST_NAME).read_text(
            encoding="utf-8").splitlines()
        lines = [x for x in lines if x.strip()]
        files = [p for p in self.out.rglob("*")
                 if p.is_file() and p.name != bundle.MANIFEST_NAME]
        self.assertEqual(len(lines), len(files))

    def test_manifest_lines_are_shasum_checkable(self):
        """MANIFEST 每行就是 ``shasum -a 256`` 的格式，可逐行复算。"""
        self.gen()
        self.assertEqual(self.bundle().returncode, 0)
        for line in (self.out / bundle.MANIFEST_NAME).read_text(
                encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, _, rel = line.partition("  ")
            self.assertEqual(len(digest), 64)
            self.assertEqual(digest, _sha256(self.out / rel))

    def test_closure_files_are_all_in_the_package(self):
        """闭包内每个源文件在包里都有对应物。"""
        self.gen()
        self.assertEqual(self.bundle().returncode, 0)
        for rel in ("main.tex", "sections/01-intro.tex", "refs.bib",
                    "facts/01-core.toml", "figures/gen/acc.csv"):
            self.assertTrue((self.out / rel).is_file(), rel)

    def test_source_project_is_untouched(self):
        """bundle 只读源盘：源项目一个字节都不动。"""
        self.gen()
        before = {p.relative_to(self.root).as_posix(): _sha256(p)
                  for p in sorted(self.root.rglob("*")) if p.is_file()}
        self.assertEqual(self.bundle().returncode, 0)
        after = {p.relative_to(self.root).as_posix(): _sha256(p)
                 for p in sorted(self.root.rglob("*")) if p.is_file()}
        self.assertEqual(before, after)

    def test_audit_readings_unchanged_after_bundle(self):
        """打包前后源项目的 audit 读数一致（包默认落在项目外）。"""
        self.gen()
        before = run_cli("audit", str(self.root), "--json").stdout
        self.assertEqual(self.bundle().returncode, 0)
        after = run_cli("audit", str(self.root), "--json").stdout
        self.assertEqual(before, after)

    def test_json_payload_reports_gate_items(self):
        """--json 逐项给出 pass/fail 与理由（卡 §5 预注册）。"""
        self.gen()
        proc = self.bundle("--json")
        data = self.payload(proc)
        self.assertEqual(data["exit"], 0)
        codes = {item["code"] for item in data["gate"]}
        for code in ("BUNDLE_CLOSURE", "BUNDLE_FIGURE_CSV", "BUNDLE_BIB",
                     "BUNDLE_EVIDENCE_LOCK", "BUNDLE_AUDIT"):
            self.assertIn(code, codes)
        for item in data["gate"]:
            self.assertIn(item["status"], ("pass", "fail", "waived"))
            self.assertTrue(item["detail"])

    def test_figure_csv_item_is_waived_without_figures(self):
        """没有图时该项豁免（豁免不拦）。"""
        (self.root / "sections" / "01-intro.tex").write_text(
            "\\section{结果}\n开臂解决 10 道\\fact{A1}。\n", encoding="utf-8")
        (self.root / "refs.bib").write_text("", encoding="utf-8")
        proc = self.bundle("--json")
        data = self.payload(proc)
        item = [i for i in data["gate"] if i["code"] == "BUNDLE_FIGURE_CSV"][0]
        self.assertEqual(item["status"], "waived")


# --------------------------------------------------------------------------
# 负例：变异必拦
# --------------------------------------------------------------------------

class BundleMutationTest(BundleBase):
    def test_missing_figure_csv_is_blocked(self):
        """删一张图的随图 .csv → 清单门点名不过 exit 1。"""
        self.gen()
        (self.root / "figures" / "gen" / "acc.csv").unlink()
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 1)
        data = self.payload(proc)
        item = [i for i in data["gate"] if i["code"] == "BUNDLE_FIGURE_CSV"][0]
        self.assertEqual(item["status"], "fail")
        self.assertIn("acc", item["detail"])
        self.assertIn("随图数据", item["detail"])
        self.assertFalse((self.out / bundle.MANIFEST_NAME).exists())

    def test_dangling_input_is_blocked(self):
        """main.tex 里塞悬空 \\input{ghost.tex} → 闭包拦截 exit 1。"""
        self.gen()
        main = self.root / "main.tex"
        main.write_text(main.read_text(encoding="utf-8").replace(
            "\\input{sections/01-intro}",
            "\\input{sections/01-intro}\n\\input{ghost.tex}"), encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 1)
        data = self.payload(proc)
        item = [i for i in data["gate"] if i["code"] == "BUNDLE_CLOSURE"][0]
        self.assertEqual(item["status"], "fail")
        self.assertIn("ghost.tex", item["detail"])
        self.assertFalse((self.out / bundle.MANIFEST_NAME).exists())

    def test_missing_bib_entry_is_blocked(self):
        """引用了 bib 里没有的 key → 清单门点名不过 exit 1。"""
        self.gen()
        (self.root / "refs.bib").write_text(
            "@article{other1999,\n  title = {Other},\n  year = {1999},\n"
            "  doi = {10.1000/other}\n}\n", encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 1)
        data = self.payload(proc)
        item = [i for i in data["gate"] if i["code"] == "BUNDLE_BIB"][0]
        self.assertEqual(item["status"], "fail")
        self.assertIn("MISSING_CITE", item["detail"])

    def test_verify_detects_tampered_file(self):
        """事后改一件 → --verify exit 1 并点名哪件。"""
        self.gen()
        self.assertEqual(self.bundle().returncode, 0)
        (self.out / "refs.bib").write_text("% tampered\n", encoding="utf-8")
        proc = self.verify("--json")
        self.assertEqual(proc.returncode, 1)
        data = self.payload(proc)
        self.assertIn("refs.bib", data["mismatched"])

    def test_verify_detects_missing_and_extra_files(self):
        """件数对表：包里少一件/多一件都要点名。"""
        self.gen()
        self.assertEqual(self.bundle().returncode, 0)
        (self.out / "refs.bib").unlink()
        (self.out / "stray.txt").write_text("x\n", encoding="utf-8")
        proc = self.verify("--json")
        self.assertEqual(proc.returncode, 1)
        data = self.payload(proc)
        self.assertIn("refs.bib", data["missing"])
        self.assertIn("stray.txt", data["extra"])

    def test_verify_rejects_directory_without_manifest(self):
        """不是工件包 → exit 1。"""
        empty = self.tmp / "empty"
        empty.mkdir()
        proc = run_cli("bundle", "--verify", str(empty))
        self.assertEqual(proc.returncode, 1)


# --------------------------------------------------------------------------
# 期刊差异配置接口（项目侧 bundle-checklist.toml）
# --------------------------------------------------------------------------

class BundleChecklistTest(BundleBase):
    def test_extra_check_passes_and_fails_by_config(self):
        """附加检查项：存在即过，不存在即不过（门行为按配置走）。"""
        self.gen()
        (self.root / bundle.CHECKLIST_NAME).write_text(
            '[[check]]\nname = "匿名版存在"\nkind = "exists"\n'
            'path = "anonymous/main.tex"\n', encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 1)
        data = self.payload(proc)
        item = [i for i in data["gate"] if i["code"] == "BUNDLE_CUSTOM_1"][0]
        self.assertEqual(item["status"], "fail")
        self.assertIn("匿名版存在", item["name"])
        # 补上文件 → 过
        (self.root / "anonymous").mkdir()
        (self.root / "anonymous" / "main.tex").write_text("% 匿名版\n",
                                                          encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 0)
        data = self.payload(proc)
        item = [i for i in data["gate"] if i["code"] == "BUNDLE_CUSTOM_1"][0]
        self.assertEqual(item["status"], "pass")

    def test_glob_min_check(self):
        """glob 计数下限：命中数不够即不过。"""
        self.gen()
        (self.root / bundle.CHECKLIST_NAME).write_text(
            '[[check]]\nname = "随图 CSV 不少于 3 个"\nkind = "glob_min"\n'
            'glob = "figures/gen/*.csv"\nmin = 3\n', encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 1)
        item = [i for i in self.payload(proc)["gate"]
                if i["code"] == "BUNDLE_CUSTOM_1"][0]
        self.assertEqual(item["status"], "fail")

    def test_regex_check(self):
        """正则匹配：命中即过，不命中即不过。"""
        self.gen()
        (self.root / bundle.CHECKLIST_NAME).write_text(
            '[[check]]\nname = "版权声明在"\nkind = "regex"\n'
            'file = "main.tex"\npattern = "\\\\\\\\title"\n', encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 0)
        item = [i for i in self.payload(proc)["gate"]
                if i["code"] == "BUNDLE_CUSTOM_1"][0]
        self.assertEqual(item["status"], "pass")

    def test_file_exclusion_keeps_item_out_of_package(self):
        """排除项（文件模式）：该件不进包。"""
        self.gen()
        (self.root / bundle.CHECKLIST_NAME).write_text(
            '[[exclude]]\nfile = "refs.bib"\n', encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 0)
        self.assertFalse((self.out / "refs.bib").exists())
        self.assertIn("refs.bib", self.payload(proc)["excluded"])

    def test_line_exclusion_strips_lines_from_package(self):
        """排除项（行模式）：命中行不进包内容。"""
        self.gen()
        (self.root / bundle.CHECKLIST_NAME).write_text(
            '[[exclude]]\nfile = "main.tex"\n'
            'pattern = "\\\\\\\\author\\\\{[^}]*\\\\}"\n', encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 0)
        text = (self.out / "main.tex").read_text(encoding="utf-8")
        self.assertNotIn("\\author{outsider}", text)
        self.assertIn("\\title", text)

    def test_broken_checklist_exits_two_and_names_the_rule(self):
        """配置写错 → exit 2 并点名是哪一条。"""
        self.gen()
        (self.root / bundle.CHECKLIST_NAME).write_text(
            '[[check]]\nname = "坏项"\nkind = "wat"\n', encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 2)
        data = self.payload(proc)
        self.assertIn("kind", data["message"])
        self.assertIn("坏项", data["message"])

    def test_checklist_missing_field_exits_two(self):
        """附加检查项缺字段 → exit 2 点名。"""
        self.gen()
        (self.root / bundle.CHECKLIST_NAME).write_text(
            '[[check]]\nname = "缺路径"\nkind = "exists"\n', encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("path", self.payload(proc)["message"])

    def test_unknown_key_in_check_exits_two(self):
        """附加检查项有未知键 → exit 2 点名。"""
        self.gen()
        (self.root / bundle.CHECKLIST_NAME).write_text(
            '[[check]]\nname = "多键"\nkind = "exists"\npath = "main.tex"\n'
            'journal = "IEEE"\n', encoding="utf-8")
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("journal", self.payload(proc)["message"])


# --------------------------------------------------------------------------
# runs/：只收已签收副本
# --------------------------------------------------------------------------

class BundleRunsTest(BundleBase):
    def _make_runs(self, signed: bool) -> None:
        runs = self.root / "runs" / "batch72"
        runs.mkdir(parents=True)
        (runs / "summary.json").write_text('{"n": 1}\n', encoding="utf-8")
        if signed:
            (runs / "summary.signoff.toml").write_text(
                'schema = "factscribe/report-signoff@1"\n', encoding="utf-8")

    def test_signed_run_is_collected(self):
        """已签收副本进包。"""
        self.gen()
        self._make_runs(signed=True)
        self.assertEqual(self.bundle().returncode, 0)
        self.assertTrue((self.out / "runs" / "batch72" / "summary.json").is_file())

    def test_unsigned_run_is_listed_only(self):
        """未签收的 runs 只进清单、不进包。"""
        self.gen()
        self._make_runs(signed=False)
        proc = self.bundle("--json")
        self.assertEqual(proc.returncode, 0)
        data = self.payload(proc)
        self.assertFalse((self.out / "runs" / "batch72" / "summary.json").exists())
        self.assertEqual(len(data["listed_only"]), 1)
        self.assertIn("batch72", data["listed_only"][0]["group"])

    def test_runs_mode_full_collects_unsigned(self):
        """--runs-mode full → 未签收的也收。"""
        self.gen()
        self._make_runs(signed=False)
        self.assertEqual(self.bundle("--runs-mode", "full").returncode, 0)
        self.assertTrue((self.out / "runs" / "batch72" / "summary.json").is_file())


# --------------------------------------------------------------------------
# 模块级单测（不经 CLI）
# --------------------------------------------------------------------------

class BundleUnitTest(BundleBase):
    def test_default_out_dir_is_outside_project(self):
        """默认包目录在项目外：源项目的审计读数才不会被包的 .tex 副本搅动。"""
        cfg = load_config(self.root)
        out = bundle.default_out_dir(cfg)
        root = cfg.root.resolve()
        self.assertFalse(out == root or root in out.parents)
        self.assertEqual(out.parent, root.parent)

    def test_verify_reports_ok_for_fresh_bundle(self):
        self.gen()
        result = bundle.run_bundle(load_config(self.root), out_dir=self.out)
        self.assertEqual(result["exit_code"], 0)
        check = bundle.verify_bundle(self.out)
        self.assertTrue(check["ok"])
        self.assertEqual(check["exit_code"], 0)

    def test_gate_items_have_three_states(self):
        """清单门条目只有过／不过／豁免三态。"""
        self.gen()
        result = bundle.run_bundle(load_config(self.root), out_dir=self.out)
        for item in result["gate"]:
            self.assertIn(item["status"], ("pass", "fail", "waived"))


if __name__ == "__main__":
    unittest.main()
