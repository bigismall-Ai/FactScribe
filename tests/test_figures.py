# -*- coding: utf-8 -*-
"""CARD-G2：账本驱动的图表生成与四面对账（`factscribe figures`）。

正负例成对：人填规格＋现行账本 → 机械出三件套（.tex／随图 .csv／绑定表），
四面对账全绿（exit 0）；规格里出现裸数字、未知图型、缺数据点一律 exit 2
逐条点名；账动过而图未重生成必红（exit 1，逐点点名）。

夹具不依赖真实论文盘：自造最小项目（一条 facts 目录＋一张规格表）。
本模块只服务 figures 子命令，不改 audit/check 的判据与退出码。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe import figures                       # noqa: E402
from factscribe.config import _mini_toml, load_toml  # noqa: E402

CONFIG_TOML = """[project]
title = "Figures Fixture"
authors = ["factscribe"]
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
build = ""
"""

SECTION_TEX = """\\section{Introduction}
\\label{sec:intro}
开臂解决 10 道\\fact{A1}，对比臂解决 8 道\\fact{A3}。
"""

MAIN_TEX = """\\documentclass[11pt]{article}
\\usepackage[UTF8]{ctex}
\\usepackage{graphicx}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\begin{document}
\\input{sections/01-intro.tex}
\\end{document}
"""

BIB = """@misc{chen2023factscore,
  title        = {FactScore},
  author       = {Chen, Li},
  year         = {2023},
  eprint       = {2301.00001},
  archivePrefix = {arXiv}
}
"""

FACTS_TOML = """[[fact]]
id = "A1"
claim = "开臂 resolved"
value = "10/16"
source = "results/swb16.md"
source_sha256 = "sha256:5a8978302c97ea1d41011e54096d4285032f37f8cfdeca935f74576128adce59"
locator = "§二 汇总表 open 行"
confidence = "high"

[[fact]]
id = "A3"
claim = "对比臂 resolved"
value = "8/16"
source = "results/swb16.md"
source_sha256 = "sha256:5a8978302c97ea1d41011e54096d4285032f37f8cfdeca935f74576128adce59"
locator = "§二 汇总表 closed 行"
confidence = "high"
"""

SPEC_TOML = """name = "acc"
kind = "bar"
caption = "两臂在同一组题上的解决数"
xlabel = "臂"
ylabel = "解决比例"
data = ["A1", "A3"]
labels = ["开臂", "对比臂"]
"""


def make_project(root: Path, *, spec: str = SPEC_TOML,
                 facts: str = FACTS_TOML) -> Path:
    """造一个最小项目（够 figures 读，不求能编译）。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (root / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (root / "refs.bib").write_text(BIB, encoding="utf-8")
    (root / "facts").mkdir(exist_ok=True)
    (root / "facts" / "01-core.toml").write_text(facts, encoding="utf-8")
    (root / "sections").mkdir(exist_ok=True)
    (root / "sections" / "01-intro.tex").write_text(SECTION_TEX, encoding="utf-8")
    (root / "results").mkdir(exist_ok=True)
    (root / "results" / "swb16.md").write_text("open 10 of 16\nclosed 8 of 16\n",
                                               encoding="utf-8")
    if spec is not None:
        (root / "figures").mkdir(exist_ok=True)
        (root / "figures" / "acc.fig.toml").write_text(spec, encoding="utf-8")
    return root


def run_cli(*args: str):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", *args]
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


class FiguresTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="factscribe-fig-")
        self.root = make_project(Path(self.tmp) / "proj")

    def gen(self, *extra: str):
        return run_cli("figures", "gen", str(self.root), *extra)

    def check(self, *extra: str):
        return run_cli("figures", "check", str(self.root), *extra)

    def codes(self, proc) -> list:
        try:
            data = json.loads(proc.stdout)
        except (ValueError, TypeError):
            return []
        return [f.get("code") for f in data.get("findings", [])]


class TestFiguresGen(FiguresTestBase):
    """gen：正例出三件套；规格错 exit 2；解引失败 exit 1。"""

    def test_gen_writes_three_products(self):
        proc = self.gen()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        gen = self.root / "figures" / "gen"
        for name in ("acc.tex", "acc.csv", "acc.bind.toml"):
            self.assertTrue((gen / name).is_file(), "缺 %s" % name)
        self.assertTrue((self.root / "figures" / "bind.toml").is_file(),
                        "缺项目级绑定表 figures/bind.toml")

    def test_counts_equal_on_three_faces(self):
        """三面数据点数 100% 相等（规格＝bind＝csv 行数）。"""
        self.assertEqual(self.gen().returncode, 0)
        spec = load_toml(self.root / "figures" / "acc.fig.toml")
        bind = load_toml(self.root / "figures" / "gen" / "acc.bind.toml")
        csv_lines = (self.root / "figures" / "gen" / "acc.csv").read_text(
            encoding="utf-8").strip().splitlines()
        self.assertEqual(len(spec["data"]), len(bind["point"]))
        self.assertEqual(len(spec["data"]), len(csv_lines) - 1)

    def test_bind_records_fact_id_value_and_source_sha(self):
        """绑定表每个数据点记 fact_id＋生成时的值与 source_sha256。"""
        self.assertEqual(self.gen().returncode, 0)
        bind = load_toml(self.root / "figures" / "gen" / "acc.bind.toml")
        point = bind["point"][0]
        self.assertEqual(point["fact_id"], "A1")
        self.assertEqual(point["value"], "10/16")
        self.assertEqual(point["source_sha256"],
                         "5a8978302c97ea1d41011e54096d4285032f37f8cfdeca935f74576128adce59")

    def test_bind_parses_with_mini_toml_fallback(self):
        """3.10 的 fallback 解析器也读得动产物（数组表 ＋ 内联表数组）。"""
        self.assertEqual(self.gen().returncode, 0)
        for rel in ("figures/gen/acc.bind.toml", "figures/bind.toml"):
            text = (self.root / rel).read_text(encoding="utf-8")
            self.assertEqual(_mini_toml(text), load_toml(self.root / rel), rel)

    def test_tex_carries_only_ledger_numbers(self):
        """图里每个数都来自账（数据点是 fact id 解出来的值）。"""
        self.assertEqual(self.gen().returncode, 0)
        tex = (self.root / "figures" / "gen" / "acc.tex").read_text(encoding="utf-8")
        self.assertIn("pgfplots", tex)
        self.assertIn("(1,10/16)", tex)
        self.assertIn("(2,8/16)", tex)

    def test_csv_is_the_reconciliation_object(self):
        """随图 .csv 是既有 FIGURE_UNVERIFIED 判定的对账物。"""
        self.assertEqual(self.gen().returncode, 0)
        text = (self.root / "figures" / "gen" / "acc.csv").read_text(encoding="utf-8")
        self.assertEqual(text.splitlines()[0], "index,fact_id,label,value")
        self.assertIn("1,A1,开臂,10/16", text)

    def test_bare_number_spec_is_refused(self):
        """规格硬门：裸数字 exit 2，一个都不放行。"""
        (self.root / "figures" / "acc.fig.toml").write_text(
            SPEC_TOML.replace('["A1", "A3"]', '["A1", "56.25"]'), encoding="utf-8")
        proc = self.gen()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("FIG_BARE_NUMBER", proc.stdout)
        self.assertFalse((self.root / "figures" / "gen" / "acc.tex").is_file(),
                         "规格坏了不许半生成")

    def test_unknown_kind_is_refused(self):
        (self.root / "figures" / "acc.fig.toml").write_text(
            SPEC_TOML.replace('kind = "bar"', 'kind = "heatmap"'), encoding="utf-8")
        proc = self.gen()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("FIG_SPEC_BAD_KIND", proc.stdout)

    def test_missing_data_is_refused(self):
        (self.root / "figures" / "acc.fig.toml").write_text(
            SPEC_TOML.replace('data = ["A1", "A3"]\n', ""), encoding="utf-8")
        proc = self.gen()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("FIG_SPEC_NO_POINTS", proc.stdout)

    def test_unknown_fact_id_names_the_id(self):
        """任一数据点解引失败 → exit 1 且报哪个 id。"""
        (self.root / "figures" / "acc.fig.toml").write_text(
            SPEC_TOML.replace('["A1", "A3"]', '["A1", "A9"]'), encoding="utf-8")
        proc = self.gen()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("FIG_FACT_NOT_FOUND", proc.stdout)
        self.assertIn("A9", proc.stdout)

    def test_no_spec_is_skip(self):
        """无图项目跑 gen 得 skip（exit 0）。"""
        shutil_root = Path(self.tmp) / "empty"
        make_project(shutil_root, spec=None)
        proc = run_cli("figures", "gen", str(shutil_root))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("无图可生成", proc.stdout)

    def test_regen_prints_diff_before_overwrite(self):
        """覆盖旧产物前先比对 bind 表差异并打印。"""
        self.assertEqual(self.gen().returncode, 0)
        facts = self.root / "facts" / "01-core.toml"
        facts.write_text(facts.read_text(encoding="utf-8").replace(
            'value = "10/16"', 'value = "12/16"'), encoding="utf-8")
        proc = self.gen()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("覆盖前比对旧绑定表", proc.stdout)
        self.assertIn("12/16", proc.stdout)
        bind = load_toml(self.root / "figures" / "gen" / "acc.bind.toml")
        self.assertEqual(bind["point"][0]["value"], "12/16")

    def test_line_and_table_kinds(self):
        for kind, marker in (("line", "mark=*"), ("table", "tabular")):
            spec = SPEC_TOML.replace('kind = "bar"', 'kind = "%s"' % kind)
            spec = spec.replace('name = "acc"', 'name = "acc%s"' % kind)
            (self.root / "figures" / ("acc%s.fig.toml" % kind)).write_text(
                spec, encoding="utf-8")
        self.assertEqual(self.gen().returncode, 0)
        line = (self.root / "figures" / "gen" / "accline.tex").read_text(encoding="utf-8")
        table = (self.root / "figures" / "gen" / "acctable.tex").read_text(encoding="utf-8")
        self.assertIn("mark=*", line)
        self.assertIn("tabular", table)


class TestFiguresCheck(FiguresTestBase):
    """check：四面比对。"""

    def test_four_faces_agree(self):
        self.assertEqual(self.gen().returncode, 0)
        proc = self.check()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("零漂移", proc.stdout)

    def test_ledger_change_without_regen_is_red(self):
        """变异检出：改账上 fact 的 value，不重跑 gen → 逐点点名。"""
        self.assertEqual(self.gen().returncode, 0)
        facts = self.root / "facts" / "01-core.toml"
        facts.write_text(facts.read_text(encoding="utf-8").replace(
            'value = "10/16"', 'value = "12/16"'), encoding="utf-8")
        proc = self.check()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("FIG_VALUE_DRIFT", proc.stdout)
        self.assertIn("A1", proc.stdout)

    def test_source_sha_change_is_red(self):
        self.assertEqual(self.gen().returncode, 0)
        facts = self.root / "facts" / "01-core.toml"
        facts.write_text(facts.read_text(encoding="utf-8").replace(
            "5a8978302c97ea1d41011e54096d4285032f37f8cfdeca935f74576128adce59",
            "0" * 64), encoding="utf-8")
        proc = self.check()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("FIG_SOURCE_DRIFT", proc.stdout)

    def test_tampered_csv_is_red(self):
        """随图 CSV 被改过 → 红。"""
        self.assertEqual(self.gen().returncode, 0)
        csv_path = self.root / "figures" / "gen" / "acc.csv"
        csv_path.write_text(csv_path.read_text(encoding="utf-8").replace(
            "1,A1,开臂,10/16", "1,A1,开臂,99/16"), encoding="utf-8")
        proc = self.check()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("FIG_CSV_ROW_DRIFT", proc.stdout)

    def test_spec_change_without_regen_is_red(self):
        """规格改了（数据点顺序变了）但图没重生成 → 红。"""
        self.assertEqual(self.gen().returncode, 0)
        (self.root / "figures" / "acc.fig.toml").write_text(
            SPEC_TOML.replace('["A1", "A3"]', '["A3", "A1"]').replace(
                '["开臂", "对比臂"]', '["对比臂", "开臂"]'), encoding="utf-8")
        proc = self.check()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("FIG_SPEC_DRIFT", proc.stdout)

    def test_missing_artifacts_is_red(self):
        proc = self.check()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("FIG_ARTIFACT_MISSING", proc.stdout)

    def test_other_fact_change_is_not_a_false_red(self):
        """账上别的 fact 动了、但本图数据点没动 → 不许误红。"""
        self.assertEqual(self.gen().returncode, 0)
        facts = self.root / "facts" / "01-core.toml"
        facts.write_text(facts.read_text(encoding="utf-8") + """
[[fact]]
id = "A9"
claim = "别的量"
value = "3"
source = "results/swb16.md"
source_sha256 = "5a8978302c97ea1d41011e54096d4285032f37f8cfdeca935f74576128adce59"
confidence = "low"
""", encoding="utf-8")
        proc = self.check()
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_json_payload_shape(self):
        self.assertEqual(self.gen().returncode, 0)
        proc = self.check("--json")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        data = json.loads(proc.stdout)
        self.assertEqual(data["command"], "figures-check")
        self.assertEqual(data["exit"], 0)
        item = data["figures"][0]
        self.assertTrue(item["counts_equal"])
        self.assertEqual(item["points_ok"], item["points_total"])


class TestFiguresHouseRules(unittest.TestCase):
    """家规：纯标准库、零网络、命令形齐整。"""

    def test_module_imports_only_stdlib(self):
        """figures.py 只许标准库 ＋ 包内相对导入（零第三方依赖）。"""
        text = (ROOT / "factscribe" / "figures.py").read_text(encoding="utf-8")
        stdlib = set(sys.stdlib_module_names)
        for line in text.splitlines():
            m = re.match(r"^(?:from|import)\s+([A-Za-z_][\w.]*)", line)
            if not m:
                continue
            root_mod = m.group(1).split(".")[0]
            if m.group(1).startswith("."):
                continue                      # 包内相对导入
            self.assertIn(root_mod, stdlib, "第三方依赖：%s" % line)

    def test_no_network_call(self):
        text = (ROOT / "factscribe" / "figures.py").read_text(encoding="utf-8")
        for banned in ("urllib", "socket", "requests", "http"):
            self.assertNotIn(banned, text)

    def test_command_is_registered(self):
        out = run_cli("--help").stdout
        self.assertIn("figures", out)
        self.assertIn("figures", run_cli("figures", "--help").stdout)


# --------------------------------------------------------------------------
# G2-FIX：外行手写的最小项目
# --------------------------------------------------------------------------
# 这一组夹具是**手写**的：不碰上面任何仓内 helper（make_project / add_fact
# 都不许），也不写项目声明 factscribe.toml——就是一个外行照着 README 抄的
# 项目：一条只有五个字段的 fact ＋ 一张手写规格表。
#
# G2 验收时正是这份夹具把 `figures gen` 打成 exit 4 的「工具内部错误：
# TypeError: _payload() got multiple values for argument 'code'」。修完必须
# gen/check 全程 exit 0；缺字段/坏 TOML 一律 exit 2 ＋ 命名错误码。
# --------------------------------------------------------------------------

# 手写 fact：只有 id/value/source/source_sha256/locator 五个字段
# （无 claim/kind/note/expr/confidence —— 可选字段缺省，缺必填才拒）。
OUTSIDER_FACT_TOML = """[[fact]]
id = "X1"
value = "42"
source = "s.csv"
source_sha256 = "abc"
locator = "L1"
"""

# 手写规格表（嵌套形态：[figure] 放图型与 caption，[[point]] 放数据点）。
OUTSIDER_FIG_TOML = """[figure]
kind = "bar"
caption = "smoke"
[[point]]
fact_id = "X1"
label = "X1"
"""


def write_outsider_project(root: Path, *, fact: str = OUTSIDER_FACT_TOML,
                            fig: str = OUTSIDER_FIG_TOML) -> Path:
    """手写一个最小项目：**不经任何仓内 helper**，只落盘两个文件。

    没有 factscribe.toml、没有 main.tex、没有 refs.bib——外行手写的东西就这些。
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "facts").mkdir(exist_ok=True)
    (root / "figures").mkdir(exist_ok=True)
    (root / "facts" / "a.toml").write_text(fact, encoding="utf-8")
    (root / "figures" / "demo.fig.toml").write_text(fig, encoding="utf-8")
    return root


class FiguresOutsiderBase(unittest.TestCase):
    """外行手写夹具的公共底座（仍不碰仓内 helper）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="factscribe-fig-outsider-")
        self.root = write_outsider_project(Path(self.tmp) / "proj")

    def gen(self, *extra: str):
        return run_cli("figures", "gen", str(self.root), *extra)

    def check(self, *extra: str):
        return run_cli("figures", "check", str(self.root), *extra)


class TestFiguresOutsiderMinimalProject(FiguresOutsiderBase):
    """外行手写的最小项目：gen/check 全程 exit 0（不许再是 exit 4）。"""

    def test_gen_is_not_internal_error(self):
        """G2-FIX 主用例：同一份手写夹具，修前 exit 4，修后 exit 0。"""
        proc = self.gen()
        blob = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, blob)
        self.assertNotIn("工具内部错误", blob)
        self.assertNotIn("TypeError", blob)

    def test_check_is_not_internal_error(self):
        proc = self.gen()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.check()
        blob = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, blob)
        self.assertNotIn("工具内部错误", blob)
        self.assertNotIn("TypeError", blob)

    def test_gen_writes_three_products(self):
        self.assertEqual(self.gen().returncode, 0)
        gen = self.root / "figures" / "gen"
        for name in ("demo.tex", "demo.csv", "demo.bind.toml"):
            self.assertTrue((gen / name).is_file(), "缺 %s" % name)
        self.assertTrue((self.root / "figures" / "bind.toml").is_file(),
                        "缺项目级绑定表 figures/bind.toml")

    def test_check_is_green_after_gen(self):
        self.assertEqual(self.gen().returncode, 0)
        proc = self.check()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("零漂移", proc.stdout)

    def test_five_field_fact_is_enough(self):
        """五字段 fact（无 kind/note/expr/claim/confidence）够用：值能回账。"""
        self.assertEqual(self.gen().returncode, 0)
        bind = load_toml(self.root / "figures" / "gen" / "demo.bind.toml")
        point = bind["point"][0]
        self.assertEqual(point["fact_id"], "X1")
        self.assertEqual(point["value"], "42")

    def test_no_project_declaration_is_needed(self):
        """没有 factscribe.toml 也跑得起来（figures 只读 facts/ 与 figures/）。"""
        self.assertFalse((self.root / "factscribe.toml").exists())
        proc = self.gen()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.check().returncode, 0)

    def test_flat_handwritten_spec_also_works(self):
        """外行也可能写成扁平形态（顶层键）——同样 exit 0，图名取文件名。"""
        (self.root / "figures" / "demo.fig.toml").write_text(
            'kind = "bar"\ncaption = "smoke"\ndata = ["X1"]\nlabels = ["X1"]\n',
            encoding="utf-8")
        proc = self.gen()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((self.root / "figures" / "gen" / "demo.tex").is_file())

    def test_identifier_like_label_is_not_a_bare_number(self):
        """标签 "X1" 是标识符不是账外数字——照抄 fact id 不该被当裸数字拒收。"""
        proc = self.gen()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("FIG_BARE_NUMBER", proc.stdout)

    def test_check_before_gen_is_red_not_crash(self):
        """没生成过就 check → 红（exit 1）点名缺产物，不是 exit 4。"""
        proc = self.check()
        blob = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 1, blob)
        self.assertIn("FIG_ARTIFACT_MISSING", proc.stdout)
        self.assertNotIn("TypeError", blob)

    def test_ledger_change_without_regen_is_red(self):
        """账改过而图没重生成 → 逐点点名（外行项目同样适用）。"""
        self.assertEqual(self.gen().returncode, 0)
        facts = self.root / "facts" / "a.toml"
        facts.write_text(facts.read_text(encoding="utf-8").replace(
            'value = "42"', 'value = "43"'), encoding="utf-8")
        proc = self.check()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("FIG_VALUE_DRIFT", proc.stdout)
        self.assertIn("X1", proc.stdout)


class TestFiguresOutsiderRejections(FiguresOutsiderBase):
    """缺字段/坏 TOML 的规范拒收：一律 exit 2 ＋ 命名错误码＋点名。

    不许「工具内部错误」裸异常逃逸到用户面前（G2-FIX）。
    """

    def assert_refused(self, proc, code: str):
        blob = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 2, blob)
        self.assertIn(code, proc.stdout)
        self.assertNotIn("工具内部错误", blob)
        self.assertNotIn("TypeError", blob)

    def test_fact_missing_id_is_refused(self):
        """缺必填 id → exit 2，点名缺哪个字段。"""
        (self.root / "facts" / "a.toml").write_text(
            '[[fact]]\nvalue = "42"\nsource = "s.csv"\n'
            'source_sha256 = "abc"\nlocator = "L1"\n', encoding="utf-8")
        self.assert_refused(self.gen(), "FACT_ID_MISSING")

    def test_fact_missing_value_is_refused(self):
        """缺必填 value → exit 2，点名缺哪个字段。"""
        (self.root / "facts" / "a.toml").write_text(
            '[[fact]]\nid = "X1"\nsource = "s.csv"\n'
            'source_sha256 = "abc"\nlocator = "L1"\n', encoding="utf-8")
        proc = self.gen()
        self.assert_refused(proc, "FIG_SPEC_UNPLOTTABLE")
        self.assertIn("value", proc.stdout)

    def test_broken_fact_toml_is_refused(self):
        """账本 TOML 坏掉 → exit 2 ＋ 命名错误码，不许 exit 4。"""
        (self.root / "facts" / "a.toml").write_text(
            '[[fact]]\nid = "X1\nvalue = "42"\n', encoding="utf-8")
        proc = self.gen()
        self.assert_refused(proc, "FIG_FACTS_INVALID")
        self.assertIn("a.toml", proc.stdout)

    def test_broken_spec_toml_is_refused(self):
        """规格表 TOML 坏掉 → exit 2 ＋ 命名错误码。"""
        (self.root / "figures" / "demo.fig.toml").write_text(
            '[figure]\nkind = "bar\n', encoding="utf-8")
        self.assert_refused(self.gen(), "FIG_SPEC_BAD_DATA")

    def test_spec_missing_kind_is_refused(self):
        """规格缺图型 → exit 2，点名缺哪个字段。"""
        (self.root / "figures" / "demo.fig.toml").write_text(
            '[figure]\ncaption = "smoke"\n[[point]]\nfact_id = "X1"\n',
            encoding="utf-8")
        self.assert_refused(self.gen(), "FIG_SPEC_BAD_KIND")

    def test_spec_missing_points_is_refused(self):
        """规格缺数据点 → exit 2，点名缺哪个字段。"""
        (self.root / "figures" / "demo.fig.toml").write_text(
            '[figure]\nkind = "bar"\ncaption = "smoke"\n', encoding="utf-8")
        self.assert_refused(self.gen(), "FIG_SPEC_NO_POINTS")

    def test_point_missing_fact_id_is_refused(self):
        """数据点没写 fact_id → exit 2，点名缺哪个字段。"""
        (self.root / "figures" / "demo.fig.toml").write_text(
            '[figure]\nkind = "bar"\ncaption = "smoke"\n[[point]]\nlabel = "X1"\n',
            encoding="utf-8")
        self.assert_refused(self.gen(), "FIG_SPEC_BAD_DATA")

    def test_bare_number_still_refused(self):
        """裸数字仍然 exit 2（硬门不许松）。"""
        (self.root / "figures" / "demo.fig.toml").write_text(
            '[figure]\nkind = "bar"\ncaption = "smoke"\n[[point]]\nfact_id = "56.25"\n',
            encoding="utf-8")
        self.assert_refused(self.gen(), "FIG_BARE_NUMBER")

    def test_free_number_in_caption_is_refused(self):
        """caption 里的**账外自由数字**仍然 exit 2（"X1" 这种标识符不算）。"""
        (self.root / "figures" / "demo.fig.toml").write_text(
            '[figure]\nkind = "bar"\ncaption = "Figure 1"\n[[point]]\nfact_id = "X1"\n',
            encoding="utf-8")
        self.assert_refused(self.gen(), "FIG_BARE_NUMBER")

    def test_identifier_digits_in_label_are_allowed(self):
        """标签里的标识符数字（X1）不算账外数字——照抄 fact id 是正道。"""
        (self.root / "figures" / "demo.fig.toml").write_text(
            '[figure]\nkind = "bar"\ncaption = "smoke"\n'
            '[[point]]\nfact_id = "X1"\nlabel = "X1"\n', encoding="utf-8")
        proc = self.gen()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("FIG_BARE_NUMBER", proc.stdout)

    def test_refused_spec_writes_no_artifacts(self):
        """规格坏了不许半生成（一个字都不许落盘）。"""
        (self.root / "figures" / "demo.fig.toml").write_text(
            '[figure]\nkind = "heatmap"\ncaption = "smoke"\n[[point]]\nfact_id = "X1"\n',
            encoding="utf-8")
        self.assert_refused(self.gen(), "FIG_SPEC_BAD_KIND")
        self.assertFalse((self.root / "figures" / "gen" / "demo.tex").is_file())
        self.assertFalse((self.root / "figures" / "bind.toml").is_file())

    def test_check_also_refuses_broken_input(self):
        """check 与 gen 同一套拒收口径。"""
        (self.root / "facts" / "a.toml").write_text("[[fact]]\nid = \n", encoding="utf-8")
        self.assert_refused(self.check(), "FIG_FACTS_INVALID")


if __name__ == "__main__":
    unittest.main()
