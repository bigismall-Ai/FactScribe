# -*- coding: utf-8 -*-
"""tests/test_workbench_ai_draft_eol.py —— AI 草稿插入路径的行尾保真。

背景（社区 PR #160 回灌时**同源**发现的第二处）：段落保存那条路
（`save_block`）在 PR #160 里补上了 `textio.restore_newlines`——CRLF 稿子
存一次仍是 CRLF。但**同一条链上的另一条路**——AI 草稿块插入
（`workbench/write.py::_draft_insertion`）——当初是硬编码 `"\\n"` 拼的：
往 CRLF 稿子里插一段 AI 草稿，落盘就是一段 LF 行，同一份稿子两种行尾混着。

修完之后的口径（这里逐条钉住）：

1. **按所在文件的主导行尾补**：CRLF 稿子里插进去的草稿块也是 CRLF；
   LF 稿子里不会被改成 CRLF；混合稿子按主导行尾（多数）补，原来那些
   混合行尾**一个字节都不动**。
2. **草稿正文一个字不改**：只改行尾，不动内容（`%` 的既有转义照旧——
   那是 `_escape_draft` 的既有口径，不是行尾改写）。
3. **提议单与真写回同一份计算**：差异卡上看到的落盘结果，就是人点确认后
   真正写进文件的那一份（两者逐字节相同）。

跑法（仓根）：python3 -m pytest tests/test_workbench_ai_draft_eol.py -q
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.textio import read_text_exact, write_text_exact   # noqa: E402
from factscribe.workbench import write as wb                      # noqa: E402
from factscribe.workbench.projects import disk_sections           # noqa: E402

CONFIG_TOML = """[project]
title = "AI 草稿行尾测试"
authors = ["tester"]
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\newcommand{\\fact}[1]{\\textsuperscript{\\textsf{\\footnotesize[#1]}}}
\\title{AI 草稿行尾测试}
\\author{tester}
\\begin{document}
\\input{sections/01-intro}
\\end{document}
"""

INTRO_TEX = """\\section{引言}

开臂解出 10/16\\fact{A1}。方法与记号见 \\cite{knuth1984}。
"""

FACTS_TOML = """[[fact]]
id = "A1"
claim = "开臂解出"
value = "10/16"
source = "results/data.md"
source_sha256 = "0" * 64
locator = "汇总表"
"""

#: 被写进稿的那段 AI 回复（两行）。
BODY = "第一行草稿\n第二行草稿：口径不变"

REL = "sections/01-intro.tex"


def make_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (root / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (root / "refs.bib").write_text("", encoding="utf-8")
    (root / "sections").mkdir(exist_ok=True)
    write_text_exact(root / "sections" / "01-intro.tex", INTRO_TEX)
    (root / "facts").mkdir(exist_ok=True)
    (root / "facts" / "01-core.toml").write_text(FACTS_TOML, encoding="utf-8")
    return root


class AiDraftEolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factscribe-aidraft-eol-"))
        self.root = make_project(self.tmp / "paper")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ 小工具

    def section_path(self) -> Path:
        return self.root / "sections" / "01-intro.tex"

    def rewrite(self, eol: str) -> str:
        """把章节文件写成给定行尾，返回写进去的**原文**。"""
        path = self.section_path()
        lf = read_text_exact(path).replace("\r\n", "\n")
        if eol == "crlf":
            out = lf.replace("\n", "\r\n")
        elif eol == "mixed":
            # 第一行 CRLF、其余 LF：落单的 CRLF 是少数 → 主导行尾是 LF。
            lines = lf.split("\n")
            out = lines[0] + "\r\n" + "\n".join(lines[1:])
        else:
            out = lf
        write_text_exact(path, out)
        return out

    def para_id(self) -> str:
        blocks = disk_sections(self.root)["blocks"]
        hits = [b for b in blocks
                if b.get("file") == REL and b.get("kind") == "para"]
        self.assertTrue(hits, "样例盘里得有正文段")
        return hits[0]["id"]

    @staticmethod
    def expected_region(marker: str, body_lines: list, eol: str) -> str:
        """草稿块在文件里的样子（与 _draft_region 同一形状，行尾按 eol）。"""
        lines = ["%% FACTSCRIBE-AI-DRAFT-BEGIN %s" % marker,
                 "\\begin{quote}"]
        lines.extend(body_lines)
        lines.append("\\end{quote}")
        lines.append("%% FACTSCRIBE-AI-DRAFT-END %s" % marker)
        return eol.join(lines)

    def insert(self, body: str = BODY) -> str:
        """插一段草稿，返回落盘后的文件全文。"""
        wb.insert_ai_draft(self.root, REL, self.para_id(), body)
        return read_text_exact(self.section_path())

    # ------------------------------------------------------------ 用例

    def test_crlf_paper_keeps_crlf_in_the_inserted_draft(self):
        """CRLF 稿子：草稿块逐行 CRLF，其余正文逐字节不变。"""
        original = self.rewrite("crlf")
        after = self.insert()
        region = self.expected_region("aidraft-1", BODY.split("\n"), "\r\n")
        insertion = "\r\n" + region + "\r\n"
        self.assertIn(insertion, after, "草稿块必须以 CRLF 落盘")
        self.assertEqual(after.replace(insertion, "", 1), original,
                         "除草稿块外，原正文逐字节不变")
        self.assertNotRegex(after, r"(?<!\r)\n", "全文不该出现落单的 LF")

    def test_lf_paper_stays_lf(self):
        """LF 稿子：插完还是 LF，不会被改成 CRLF。"""
        original = self.rewrite("lf")
        after = self.insert()
        region = self.expected_region("aidraft-1", BODY.split("\n"), "\n")
        insertion = "\n" + region + "\n"
        self.assertIn(insertion, after, "草稿块必须以 LF 落盘")
        self.assertEqual(after.replace(insertion, "", 1), original,
                         "除草稿块外，原正文逐字节不变")
        self.assertNotIn("\r\n", after, "LF 稿子不该出现 CRLF")

    def test_mixed_paper_uses_the_dominant_ending(self):
        """混合稿子：新插的行按主导行尾（LF）补，原来那行 CRLF 留着。"""
        original = self.rewrite("mixed")
        after = self.insert()
        region = self.expected_region("aidraft-1", BODY.split("\n"), "\n")
        insertion = "\n" + region + "\n"
        self.assertIn(insertion, after, "草稿块按主导行尾（LF）落盘")
        self.assertEqual(after.replace(insertion, "", 1), original,
                         "原有的混合行尾一个字节都不动")
        first_line = original.split("\n")[0].rstrip("\r")
        self.assertTrue(after.startswith(first_line + "\r\n"),
                        "第一行原本的 CRLF 留着")

    def test_draft_body_is_not_rewritten(self):
        """草稿正文只改行尾，不改内容（% 的既有转义照旧）。"""
        self.rewrite("crlf")
        body = "含百分号 50% 与中文标点：，。以及 3/7 的比值"
        after = self.insert(body)
        self.assertIn("含百分号 50\\% 与中文标点：，。以及 3/7 的比值",
                      after, "草稿正文一个字都不能被改写")
        self.assertNotRegex(after, r"(?<!\r)\n", "全文不该出现落单的 LF")

    def test_proposal_and_real_write_agree_byte_for_byte(self):
        """提议单看到的落盘结果 ＝ 真写回落盘的那一份（逐字节相同）。"""
        self.rewrite("crlf")
        block_id = self.para_id()
        block = wb.find_block(self.root, REL, block_id)
        sha = wb.editable_model(self.root, block)["sha"]
        proposal = wb.propose_ai_draft(self.root, REL, block_id, BODY,
                                       expect_sha=sha)
        wb.insert_ai_draft(self.root, REL, block_id, BODY, expect_sha=sha)
        after = read_text_exact(self.section_path())
        self.assertEqual(after, proposal["after_text"],
                         "差异卡上的落盘结果必须与真写回逐字节相同")
        self.assertIn("第一行草稿\r\n第二行草稿", after,
                      "草稿正文按 CRLF 落盘")


if __name__ == "__main__":
    unittest.main()
