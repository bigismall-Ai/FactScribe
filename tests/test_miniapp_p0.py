# -*- coding: utf-8 -*-
"""tests/test_miniapp_p0.py —— 2026-11-22 体检报告五条 P0 的契约考题。

体检报告（docs/MINIAPP-ALIGNMENT-AUDIT-20261122.md §0.2）列了五条 P0。
这一组把每条的**关键行为**钉成可跑的断言，免得下一轮又滑回去：

1. **P0-1 文风闸＋双语对账进检查报告**：这两道闸在 CLI 里本来就是只读命令
   （factscribe style / mirror-check），miniapp 里零入口。这里断言：
   报告里带着 style / mirror 两份**只读读数**；文风黄牌**不混进主黄牌计数**
   （否则干净稿子凭空多黄牌）；没有第二个盘时对账是「不适用」而不是错。
2. **P0-2 块形状闸**：把整个文件当段落替换文本传进来，引擎照单全收，
   采纳后文件里多一份 section 标题，而指纹闸／保护面重建／花括号配平／
   原子写四道全部放行、零告警。这里断言它**被拒收**，且**正常改稿不受影响**。
3. **P0-3 空态文案**：rp.empty 这个键在同一份 I18N 里定义了四次、后者覆盖
   前者 → 0 发现时显示的是实验报告导入提示。这里断言键已拆开，且**同一份
   字典里不许再出现重名键**（这是这次真正的病根）。
4. **P0-4 四步链 i18n**：后端给结构化 key（label_key / detail_key），
   界面文案由前端翻译。
5. **P0-5「打开」记住当前盘**：打开盘时把 last_disk 记进该盘自己的
   factscribe.toml 的 [workbench] 表，项目索引读回来，「打开」据此取盘。
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import ConfigError, load_toml            # noqa: E402
from factscribe.workbench import checkreport, write as wb       # noqa: E402
from factscribe.workbench.projects import (                     # noqa: E402
    disk_sections, load_projects,
)

#: i18n 键的**定义**（带冒号）——子串计数会把 t() 调用也算进去。
RE_KEY_RE = re.compile(r"'([A-Za-z][A-Za-z0-9_.]*)':")

def count_key_defs(key: str) -> int:
    """一个 i18n 键在字典里被**定义**了几次（不含 t() 调用）。"""
    return sum(1 for m in RE_KEY_RE.findall(JS) if m == key)


STATIC = ROOT / "factscribe" / "workbench" / "static"
JS = (STATIC / "app.js").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")

CONFIG_TOML = """[project]
title = "P0 测试"
authors = ["tester"]
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\title{P0 测试}
\\author{tester}
\\begin{document}
\\input{sections/01-intro}
\\end{document}
"""

INTRO_TEX = """\\section{引言}

开臂解出 10/16\\fact{A1}。方法与记号见 \\cite{knuth1984}，详见 \\ref{sec:two}。

\\subsection{另一节}

\\label{sec:other}

另一段说点别的。
"""

FACTS_TOML = """[[fact]]
id = "A1"
claim = "开臂解出"
value = "10/16"
source = "results/data.md"
source_sha256 = "{sha}"
locator = "汇总表"
"""


def make_disk(path: Path, value: str = "10/16") -> Path:
    """造一个最小可用的论文盘。"""
    path.mkdir(parents=True, exist_ok=True)
    (path / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (path / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (path / "refs.bib").write_text("", encoding="utf-8")
    (path / "sections").mkdir(exist_ok=True)
    (path / "sections" / "01-intro.tex").write_text(INTRO_TEX, encoding="utf-8")
    (path / "facts").mkdir(exist_ok=True)
    (path / "facts" / "01-core.toml").write_text(
        FACTS_TOML.format(sha="0" * 64).replace("10/16", value),
        encoding="utf-8")
    return path


class DiskCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factscribe-p0-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = make_disk(self.tmp / "paper")

    def para_ids(self, rel: str = "sections/01-intro.tex") -> list[str]:
        blocks = disk_sections(self.root)["blocks"]
        return [b["id"] for b in blocks
                if b.get("file") == rel and b["kind"] == "para"]

    def heading_id(self, rel: str = "sections/01-intro.tex") -> str:
        blocks = disk_sections(self.root)["blocks"]
        hits = [b["id"] for b in blocks
                if b.get("file") == rel and b["kind"] in ("section", "subsection")]
        return hits[0]


# ==========================================================================
# P0-2　块形状闸
# ==========================================================================

class BlockShapeGateTests(DiskCase):
    """P0-2：替换文本里混进别的块的节标题 → 拒收；正常改稿不受影响。"""

    def whole_file(self) -> str:
        return (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")

    def test_whole_file_as_paragraph_replacement_is_rejected(self):
        """把整份文件当段落替换文本 → 拒收，并说清是哪一条节标题。"""
        para = self.para_ids()[0]
        with self.assertRaises(ConfigError) as ctx:
            wb.propose_block_edit(self.root, "sections/01-intro.tex", para,
                                  self.whole_file())
        self.assertEqual(ctx.exception.code, "PROPOSAL_SHAPE_MISMATCH")
        message = str(ctx.exception)
        self.assertIn("\\section{引言}", message)
        self.assertIn(para, message)

    def test_rejected_proposal_leaves_the_file_untouched(self):
        """拒收发生在建单阶段：正文一个字节都不动。"""
        para = self.para_ids()[0]
        target = self.root / "sections" / "01-intro.tex"
        before = target.read_bytes()
        with self.assertRaises(ConfigError):
            wb.propose_block_edit(self.root, "sections/01-intro.tex", para,
                                  self.whole_file())
        self.assertEqual(target.read_bytes(), before)

    def test_normal_paragraph_replacement_still_works(self):
        """正常改一段：照旧通过，措辞真的换掉了。"""
        para = self.para_ids()[0]
        model = wb.editable_model(
            self.root, wb.find_block(self.root, "sections/01-intro.tex", para))
        edited = model["plain"].replace("开臂解出", "开臂最终解出")
        record = wb.propose_block_edit(self.root, "sections/01-intro.tex", para,
                                       edited)
        self.assertIn("开臂最终解出", record["after_text"])
        self.assertEqual(record["warnings"], [])

    def test_normal_save_block_still_works(self):
        """直接保存（页面的正文编辑）也照旧通过。"""
        para = self.para_ids()[0]
        model = wb.editable_model(
            self.root, wb.find_block(self.root, "sections/01-intro.tex", para))
        edited = model["plain"].replace("开臂解出", "开臂最终解出")
        result = wb.save_block(self.root, "sections/01-intro.tex", para, edited)
        after = (self.root / "sections" / "01-intro.tex").read_text(encoding="utf-8")
        self.assertIn("开臂最终解出", after)
        self.assertTrue(result["sha"])

    def test_save_block_also_rejects_the_whole_file(self):
        """同一条形状闸也守着直接保存这条路。"""
        para = self.para_ids()[0]
        target = self.root / "sections" / "01-intro.tex"
        before = target.read_bytes()
        with self.assertRaises(ConfigError) as ctx:
            wb.save_block(self.root, "sections/01-intro.tex", para,
                          self.whole_file())
        self.assertEqual(ctx.exception.code, "EDIT_SHAPE_MISMATCH")
        self.assertEqual(target.read_bytes(), before)

    def test_heading_block_rejects_two_headings(self):
        """标题块：一份替换文本只该对应一个标题。"""
        heading = self.heading_id()
        with self.assertRaises(ConfigError) as ctx:
            wb.propose_block_edit(self.root, "sections/01-intro.tex", heading,
                                  "\\section{甲}\n\\section{乙}\n")
        self.assertEqual(ctx.exception.code, "PROPOSAL_SHAPE_MISMATCH")

    def test_heading_block_accepts_one_heading(self):
        """标题块正常改标题：照旧通过。"""
        heading = self.heading_id()
        record = wb.propose_block_edit(self.root, "sections/01-intro.tex",
                                       heading, "\\section{引言（改）}\n")
        self.assertIn("引言（改）", record["after_text"])

    def test_duplicate_label_is_rejected(self):
        """替换文本里的锚与同文件别的块重名 → 拒收（LaTeX 锚要唯一）。"""
        para = self.para_ids()[0]
        with self.assertRaises(ConfigError) as ctx:
            wb.propose_block_edit(self.root, "sections/01-intro.tex", para,
                                  "\\label{sec:other}\n新的一段。\n")
        self.assertEqual(ctx.exception.code, "PROPOSAL_SHAPE_MISMATCH")
        self.assertIn("sec:other", str(ctx.exception))


# ==========================================================================
# P0-1　文风闸＋双语对账进检查报告
# ==========================================================================

class GateReadingsTests(DiskCase):
    """P0-1：检查报告里多出 style / mirror 两份只读读数。"""

    def test_report_carries_style_and_mirror_readings(self):
        payload = checkreport.report_payload(self.root)
        self.assertTrue(payload.get("ok"), payload)
        gates = payload.get("gates")
        self.assertIsInstance(gates, dict)
        self.assertIn("style", gates)
        self.assertIn("mirror", gates)
        self.assertIn("status", gates["style"])
        self.assertIn("status", gates["mirror"])

    def test_style_reading_has_shape_of_findings(self):
        gate = checkreport.report_payload(self.root)["gates"]["style"]
        self.assertIn(gate["status"], ("ok", "yellow", "red", "error"))
        for item in gate["findings"]:
            for key in ("code", "severity", "message", "location"):
                self.assertIn(key, item)

    def test_style_hits_do_not_inflate_the_main_counts(self):
        """文风黄牌不混进主体检计数（否则干净稿子凭空多黄牌）。"""
        payload = checkreport.report_payload(self.root)
        yellow = sum(1 for f in payload["findings"] if f["severity"] == "yellow")
        red = sum(1 for f in payload["findings"] if f["severity"] == "red")
        self.assertEqual(payload["health"]["yellow"], yellow)
        self.assertEqual(payload["health"]["red"], red)

    def test_mirror_is_not_applicable_without_a_sibling(self):
        """单盘项目：对账是「不适用」，不是错。"""
        gate = checkreport.report_payload(self.root)["gates"]["mirror"]
        self.assertEqual(gate["status"], "na")
        self.assertTrue(gate["ok"])
        self.assertEqual(gate["note"], "MIRROR_NO_SIBLING")

    def test_mirror_reports_zero_drift_for_matching_disks(self):
        sibling = make_disk(self.tmp / "paper-zh")
        gate = checkreport.report_payload(self.root,
                                          sibling_disk=sibling)["gates"]["mirror"]
        self.assertEqual(gate["status"], "ok")
        self.assertEqual(gate["count"], 0)

    def test_mirror_reports_drift_when_the_ledgers_diverge(self):
        """两盘事实账不一致 → 对账读数报漂移（不改盘，只读数）。"""
        sibling = make_disk(self.tmp / "paper-zh", value="10/17")
        gate = checkreport.report_payload(self.root,
                                          sibling_disk=sibling)["gates"]["mirror"]
        self.assertEqual(gate["status"], "drift")
        self.assertGreaterEqual(gate["count"], 1)
        self.assertTrue(gate["drift"])

    def test_gate_errors_carry_machine_codes_not_chinese(self):
        """闸的报错给机器码：界面文案由前端翻译（EN 界面不许半中半英）。"""
        sibling = self.tmp / "not-a-disk"
        gate = checkreport.report_payload(self.root,
                                          sibling_disk=sibling)["gates"]["mirror"]
        self.assertEqual(gate["status"], "error")
        self.assertTrue(gate["error"])
        self.assertFalse(any("\u4e00" <= ch <= "\u9fff" for ch in gate["error"]))


class GateUiTests(unittest.TestCase):
    """P0-1 的界面落位：两张折叠卡。"""

    def test_two_extra_fold_cards_exist(self):
        self.assertIn('id="cardStyle"', HTML)
        self.assertIn('id="cardMirror"', HTML)
        self.assertIn('id="badgeStyle"', HTML)
        self.assertIn('id="badgeMirror"', HTML)

    def test_frontend_renders_both_gates(self):
        self.assertIn("function renderGateCards()", JS)
        self.assertIn("gates.style", JS)
        self.assertIn("gates.mirror", JS)

    def test_gate_cards_are_localised(self):
        for key in ("rp.style", "rp.mirror", "rp.styleOk", "rp.mirrorOk"):
            self.assertIn("'%s'" % key, JS)


# ==========================================================================
# P0-3　空态文案（rp.empty 键覆盖）
# ==========================================================================

class EmptyStateKeyTests(unittest.TestCase):
    """P0-3：0 发现要说「这盘干净」，不是「点右上角导入实验报告」。"""

    def test_the_ambiguous_key_is_gone(self):
        self.assertNotIn("'rp.empty'", JS)

    def test_findings_and_reports_have_separate_empty_keys(self):
        for key in ("rp.findingsEmpty", "rp.reportsEmpty", "rp.chainEmpty"):
            self.assertEqual(count_key_defs(key), 2,
                             "%s 应当中英各一条" % key)

    def test_findings_card_uses_the_findings_empty_key(self):
        """发现卡与发现明细模态走 findingsEmpty。"""
        self.assertIn("t('rp.findingsEmpty')", JS)

    def test_reports_list_uses_the_reports_empty_key(self):
        """实验报告列表走 reportsEmpty。"""
        self.assertIn("t('rp.reportsEmpty')", JS)

    def test_no_duplicate_keys_in_either_dictionary(self):
        """病根：同一份 I18N 对象里同一个键定义了多次（后者覆盖前者）。"""
        for lang in ("zh", "en"):
            start = JS.index("%s: {" % lang)
            end = JS.index("\n  },", start)
            block = JS[start:end]
            keys = RE_KEY_RE.findall(block)
            seen = set()
            dupes = sorted({k for k in keys if k in seen or seen.add(k)})
            self.assertEqual(dupes, [], "%s 字典里有重名键：%s" % (lang, dupes))


# ==========================================================================
# P0-4　四步链标签/说明改前端 i18n
# ==========================================================================

class ChainI18nTests(unittest.TestCase):
    """P0-4：后端给结构化 key，界面文案由前端翻译。"""

    def test_chain_steps_carry_structured_keys(self):
        steps = checkreport._chain_steps({}, None, 3)
        self.assertEqual([s["key"] for s in steps],
                         ["declare", "bind", "reconcile", "certify"])
        for step in steps:
            self.assertTrue(step["label_key"])
            self.assertTrue(step["detail_key"])

    def test_legacy_fields_are_kept_for_the_mcp_contract(self):
        """MCP 工具的对外形状不变：旧的 label / detail 还在。"""
        steps = checkreport._chain_steps({}, None, 3)
        for step in steps:
            self.assertTrue(step["label"])
            self.assertTrue(step["detail"])

    def test_frontend_translates_chain_labels(self):
        self.assertIn("step.label_key", JS)
        self.assertIn("step.detail_key", JS)

    def test_both_dictionaries_have_the_chain_keys(self):
        for key in ("chain.declare", "chain.bind", "chain.reconcile",
                    "chain.certify", "chain.declare.detail",
                    "chain.certify.detail"):
            self.assertEqual(count_key_defs(key), 2, key)


# ==========================================================================
# P0-5　「打开」记住当前盘
# ==========================================================================

class LastDiskTests(DiskCase):
    """P0-5：记住上次开的是哪个盘，并读回来。"""

    def test_touch_opened_records_last_disk_in_the_disk_config(self):
        """写面：写进**被打开的那个盘自己的** factscribe.toml。"""
        wb.touch_opened(self.root)
        data = load_toml(self.root / "factscribe.toml")
        table = data.get("workbench") or {}
        self.assertEqual(table.get("last_disk"), self.root.name)
        self.assertTrue(table.get("last_opened"))

    def test_touch_opened_does_not_touch_facts_or_sections(self):
        """写面：只改配置，不碰事实账与正文。"""
        facts = self.root / "facts" / "01-core.toml"
        section = self.root / "sections" / "01-intro.tex"
        before = (facts.read_bytes(), section.read_bytes())
        wb.touch_opened(self.root)
        self.assertEqual((facts.read_bytes(), section.read_bytes()), before)

    def test_project_reports_the_last_opened_disk(self):
        """读面：项目层给出 last_disk＝最近打开过的那个盘。"""
        parent = self.tmp
        make_disk(parent / "paper-zh")
        wb.touch_opened(self.root)
        projects = load_projects(parent)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["last_disk"], self.root.name)

    def test_project_falls_back_to_english_disk_without_a_marker(self):
        """没打开过 → 回落英文盘（与旧行为一致）。"""
        parent = self.tmp
        make_disk(parent / "paper-zh")
        projects = load_projects(parent)
        self.assertEqual(projects[0]["last_disk"], "paper")

    def test_the_newest_opened_disk_wins(self):
        """开过两个盘 → 以最近打开的那个为准。"""
        parent = self.tmp
        zh = make_disk(parent / "paper-zh")
        wb.touch_opened(self.root)
        wb.touch_opened(zh)
        projects = load_projects(parent)
        self.assertEqual(projects[0]["last_disk"], "paper-zh")

    def test_frontend_opens_the_remembered_disk(self):
        self.assertIn("project.last_disk", JS)


if __name__ == "__main__":
    unittest.main()
