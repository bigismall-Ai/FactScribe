# -*- coding: utf-8 -*-
"""批 93：`style --doc` Markdown 一等公民测试（全离线）。

缺陷复现（先写测试，后实现）：

* 长 Markdown 标题必须报 ``HEADING_TOO_LONG``；
* 围栏代码与行内代码里的 ``——`` 一条都不许报；
* 报告行号必须等于原文件行号；
* 链接目标、表格行、front matter 不参与句级规则；
* 围栏未闭合不崩，按到文末处理；
* 段落不跨围栏；
* 无 ``paperkit.toml`` 也能跑；
* ``.tex`` 仍走旧路径（examples/minimal 逐项回归锁）；
* ``--doc`` 与项目目录同时给出 = 用法错（exit 2）。

规范见 ``docs/design/SPEC-DOCMODE.md``。
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

from factscribe.mdscan import (format_of, scan_markdown,  # noqa: E402
                              scan_plain)

SAMPLE = """## 这是一个非常非常长的标题用来测试标题长度规则是否生效

正文里有一个插入语破折号——像这样。

```python
# 这行代码里也有长标题和破折号——它不该被检查
x = "——"
```

`行内代码——也不该被检查`
"""


def run_cli(cwd, *args, stdin=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        cwd=str(cwd), capture_output=True, text=True, env=env, input=stdin)


def style_doc(tmp: Path, text: str, name: str = "doc.md", *extra: str):
    path = Path(tmp) / name
    path.write_text(text, encoding="utf-8")
    proc = run_cli(tmp, "style", "--doc", name, "--json", *extra)
    payload = None
    if proc.stdout.strip():
        payload = json.loads(proc.stdout)
    return proc, payload


def codes(payload):
    return [f["code"] for f in payload["findings"]]


class MarkdownMaskTest(unittest.TestCase):
    """遮罩：等长、保留换行、不误伤周边文字。"""

    def test_mask_keeps_length_and_newlines(self):
        scan = scan_markdown(SAMPLE)
        self.assertEqual(len(scan.prose), len(SAMPLE))
        self.assertEqual(scan.prose.count("\n"), SAMPLE.count("\n"))

    def test_fenced_code_is_blanked(self):
        scan = scan_markdown(SAMPLE)
        # 正文里那一处合法破折号保留；围栏里的两条必须消失。
        self.assertEqual(scan.prose.count("——"), 1)
        self.assertNotIn('x = "', scan.prose)

    def test_inline_code_is_blanked(self):
        scan = scan_markdown("前文 `代码——内容` 后文\n")
        self.assertEqual(scan.prose.count("——"), 0)
        self.assertIn("前文", scan.prose)
        self.assertIn("后文", scan.prose)

    def test_heading_parsed_and_stripped(self):
        scan = scan_markdown("## 标题 ##\n\n正文内容。\n")
        self.assertEqual([h["title"] for h in scan.headings], ["标题"])
        self.assertEqual(scan.headings[0]["line"], 1)
        # 标题行不进正文（不会与后文并成一段）
        self.assertEqual(scan.prose.splitlines()[0].strip(), "")

    def test_heading_inside_fence_not_a_heading(self):
        scan = scan_markdown("```\n## 这是一个很长的假标题\n```\n\n正文。\n")
        self.assertEqual(scan.headings, [])

    def test_link_target_masked_but_text_kept(self):
        scan = scan_markdown("[链接文字](http://a——b) 后面\n")
        self.assertNotIn("——", scan.prose)
        self.assertIn("链接文字", scan.prose)

    def test_html_comment_blanked(self):
        scan = scan_markdown("前<!-- 注释——内容 -->后\n")
        self.assertNotIn("——", scan.prose)
        self.assertNotIn("注释", scan.prose)

    def test_table_row_blanked(self):
        scan = scan_markdown("| a——b | c |\n普通段落。\n")
        self.assertNotIn("——", scan.prose)
        self.assertIn("普通段落", scan.prose)

    def test_front_matter_blanked(self):
        scan = scan_markdown(
            "---\ntitle: 标题——副标题\n# 不是标题\n---\n\n正文。\n")
        self.assertNotIn("——", scan.prose)
        self.assertEqual(scan.headings, [])
        self.assertIn("正文", scan.prose)

    def test_unclosed_fence_runs_to_eof(self):
        scan = scan_markdown("正文。\n\n```\n——未闭合\n——还在代码里\n")
        self.assertNotIn("——", scan.prose)
        self.assertEqual(len(scan.prose), len("正文。\n\n```\n——未闭合\n——还在代码里\n"))

    def test_plain_text_untouched(self):
        scan = scan_plain("一段——纯文本\n")
        self.assertIn("——", scan.prose)
        self.assertEqual(scan.headings, [])

    def test_list_lines_blanked_but_text_kept_in_list_view(self):
        text = ("## 标题\n\n"
                "- 第一项内容足够长\n"
                "- 第二项内容足够长\n"
                "\n"
                "正文段落——在这里。\n")
        scan = scan_markdown(text)
        # 等长、换行不漂：行号仍可换算
        self.assertEqual(len(scan.prose), len(text))
        self.assertEqual(scan.prose.count("\n"), text.count("\n"))
        # 列表行不参与句级统计
        self.assertNotIn("第一项", scan.prose)
        self.assertIn("正文段落", scan.prose)
        # 列表视图里保留列表内容（供超长句规则单独判）
        self.assertIn("第一项", scan.list_prose)
        self.assertNotIn("正文段落", scan.list_prose)
        self.assertEqual(len(scan.list_spans), 2)

    def test_list_marker_styles_all_masked(self):
        text = ("- 短横线项内容\n"
                "* 星号项内容\n"
                "+ 加号项内容\n"
                "1. 数字项内容\n"
                "10. 两位数项内容\n")
        scan = scan_markdown(text)
        for marker in ("短横线", "星号", "加号", "数字项", "两位数"):
            self.assertNotIn(marker, scan.prose)

    def test_nested_and_indented_continuation_masked(self):
        text = ("- 第一项\n"
                "  缩进续行\n"
                "  - 嵌套项\n"
                "续行也算列表\n"
                "\n"
                "正文段落。\n")
        scan = scan_markdown(text)
        for piece in ("第一项", "缩进续行", "嵌套项", "续行也算"):
            self.assertNotIn(piece, scan.prose)
        self.assertIn("正文段落", scan.prose)

    def test_format_of(self):
        self.assertEqual(format_of("a.md"), "markdown")
        self.assertEqual(format_of("a.MARKDOWN"), "markdown")
        self.assertEqual(format_of("a.tex"), "tex")
        self.assertEqual(format_of("a.txt"), "text")


class MarkdownStyleCliTest(unittest.TestCase):
    """端到端：`style --doc` 的判据、行号、退出码。"""

    def test_sample_reports_long_heading_and_no_code_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, payload = style_doc(Path(tmp), SAMPLE)
            self.assertEqual(proc.returncode, 3, proc.stderr)
            # 只应剩两条真问题：长标题 + 正文里那一处真实插入语破折号。
            self.assertEqual(sorted(codes(payload)),
                             ["DASH_PARENTHETICAL", "HEADING_TOO_LONG"])
            headings = [f for f in payload["findings"]
                        if f["code"] == "HEADING_TOO_LONG"]
            self.assertEqual(len(headings), 1)
            self.assertEqual(headings[0]["line"], 1)
            self.assertIn("非常非常长", headings[0]["text"])

    def test_code_fence_and_inline_code_dash_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, payload = style_doc(Path(tmp), SAMPLE)
            # 正文那一处计入；围栏 2 条 + 行内代码 1 条都不许计入。
            self.assertEqual(payload["metrics"]["dash_parenthetical"], 1)
            dashes = [f for f in payload["findings"]
                      if f["code"] == "DASH_PARENTHETICAL"]
            self.assertEqual([d["line"] for d in dashes], [3])

    def test_body_dash_reported_with_exact_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = "## Overview\n\n正文里有一个插入语破折号——像这样。\n"
            _, payload = style_doc(Path(tmp), text)
            self.assertEqual(codes(payload), ["DASH_PARENTHETICAL"])
            self.assertEqual(payload["findings"][0]["line"], 3)

    def test_link_text_dash_reported_target_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ("## Overview\n\n"
                    "这是一句有[插入语——说明](http://a——b)的正文。\n")
            _, payload = style_doc(Path(tmp), text)
            dashes = [f for f in payload["findings"]
                      if f["code"] == "DASH_PARENTHETICAL"]
            self.assertEqual(len(dashes), 1, payload["findings"])
            self.assertEqual(dashes[0]["line"], 3)

    def test_table_row_not_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ("## Overview\n\n"
                    "| 一——二 | 三 |\n"
                    "|---|---|\n"
                    "正文没有破折号。\n")
            _, payload = style_doc(Path(tmp), text)
            self.assertNotIn("DASH_PARENTHETICAL", codes(payload))

    def test_front_matter_not_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ("---\ntitle: 标题——副标题\n---\n\n"
                    "## Overview\n\n正文没有破折号。\n")
            _, payload = style_doc(Path(tmp), text)
            self.assertNotIn("DASH_PARENTHETICAL", codes(payload))

    def test_paragraphs_do_not_cross_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ("第一段有一些内容写得足够长可以成为一段。\n"
                    "```\n代码\n```\n"
                    "第二段也有一些内容写得足够长可以成为一段。\n")
            _, payload = style_doc(Path(tmp), text)
            self.assertEqual(payload["summary"]["paragraphs"], 2,
                             payload["paragraphs"])
            lines = sorted(p["line"] for p in payload["paragraphs"])
            self.assertEqual(lines[0], 1)
            self.assertGreaterEqual(lines[1], 4)   # 围栏之后，未被合并

    def test_unclosed_fence_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ("## 短标题\n\n正文。\n\n```\n"
                    "——未闭合的代码\n——第二行\n")
            proc, payload = style_doc(Path(tmp), text)
            self.assertIn(proc.returncode, (0, 3), proc.stderr)
            self.assertNotIn("DASH_PARENTHETICAL", codes(payload))

    def test_runs_without_paperkit_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse((Path(tmp) / "paperkit.toml").exists())
            proc, payload = style_doc(Path(tmp), SAMPLE)
            self.assertNotEqual(proc.returncode, 2, proc.stderr)
            self.assertEqual(payload["summary"]["files"], 1)

    def test_multiple_doc_flags_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.md").write_text("## 短标题\n\n正文。\n",
                                            encoding="utf-8")
            (Path(tmp) / "b.txt").write_text("纯文本——保留。\n",
                                             encoding="utf-8")
            proc = run_cli(tmp, "style", "--doc", "a.md", "--doc", "b.txt",
                           "--json")
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["summary"]["files"], 2)
            # 纯文本不遮罩：破折号照报；.md 走 Markdown 解析
            self.assertEqual(payload["metrics"]["dash_parenthetical"], 1)

    def test_markdown_extension_and_other_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, payload = style_doc(Path(tmp), SAMPLE, "doc.markdown")
            self.assertIn("HEADING_TOO_LONG", codes(payload))
            self.assertEqual(payload["metrics"]["dash_parenthetical"], 1)
            self.assertNotEqual(proc.returncode, 2)

    def test_usage_error_doc_plus_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.md").write_text("## t\n", encoding="utf-8")
            proc = run_cli(tmp, "style", "--doc", "x.md", ".")
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_missing_doc_file_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli(tmp, "style", "--doc", "nope.md")
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)


class ListScopeTest(unittest.TestCase):
    """批 94：列表不进句级统计；术语规则只在册词。"""

    README_LIST = (
        "## 黄牌规则\n\n"
        "黄牌不阻断构建，但会让退出码变成 3。\n\n"
        "- `UNBOUND_NUMBER`：回得到账但没绑定；\n"
        "- `NO_MANIFEST` 与 `UNSIGNED_RESULT`：缺人签清单，或有未签产物；\n"
        "- `VALUE_NOT_IN_SOURCE`：事实里的数字没在源文件里出现；\n"
        "- `LEDGER_CONFLICT` 与 `DUPLICATE_VALUE`：账本自相矛盾，"
        "或同值多 claim；\n"
        "- `CITE_UNVERIFIED`：联网核验没成；\n"
        "\n"
        "文风黄牌共九条，分四类：破折号插入解释、标题过长或格式不对、"
        "术语首现在标题、节奏与套话。\n")

    def test_equal_length_list_has_no_rhythm_plateau(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, payload = style_doc(Path(tmp), self.README_LIST)
            self.assertNotIn("RHYTHM_PLATEAU", codes(payload))
            self.assertEqual(payload["metrics"]["rhythm_plateau"], 0)

    def test_long_sentence_inside_list_still_reported(self):
        long_sentence = " ".join(["the model output value"] * 18)
        text = ("## Overview\n\n"
                "- " + long_sentence + ".\n")
        with tempfile.TemporaryDirectory() as tmp:
            _, payload = style_doc(Path(tmp), text)
            self.assertIn("SENTENCE_LENGTH_EXTREME", codes(payload))
            hit = next(f for f in payload["findings"]
                       if f["code"] == "SENTENCE_LENGTH_EXTREME")
            self.assertEqual(hit["line"], 3)

    def test_line_numbers_accurate_after_list_mask(self):
        text = ("## 标题\n\n"
                "- 第一项内容足够长\n"
                "- 第二项内容足够长\n"
                "- 第三项内容足够长\n"
                "\n"
                "正文里有一个插入语破折号——像这样。\n")
        with tempfile.TemporaryDirectory() as tmp:
            _, payload = style_doc(Path(tmp), text)
            dashes = [f for f in payload["findings"]
                      if f["code"] == "DASH_PARENTHETICAL"]
            self.assertEqual([f["line"] for f in dashes], [7])

    def test_dash_inside_list_not_reported(self):
        text = ("## 标题\n\n"
                "- 列表里的破折号——不该报\n"
                "\n"
                "正文没有破折号。\n")
        with tempfile.TemporaryDirectory() as tmp:
            _, payload = style_doc(Path(tmp), text)
            self.assertNotIn("DASH_PARENTHETICAL", codes(payload))

    def test_unregistered_heading_term_not_reported(self):
        text = "## 黄牌规则\n\n黄牌不阻断构建，但会让退出码变成 3。\n"
        with tempfile.TemporaryDirectory() as tmp:
            _, payload = style_doc(Path(tmp), text)
            self.assertNotIn("TERM_FIRST_IN_HEADING", codes(payload))
            self.assertEqual(payload["metrics"]["term_first_in_heading"], 0)

    def test_registered_heading_term_still_reported(self):
        text = ("## 预注册\n\n"
                "我们报告十六次远程运行的读数与全部原始日志。\n")
        with tempfile.TemporaryDirectory() as tmp:
            _, payload = style_doc(Path(tmp), text)
            self.assertIn("TERM_FIRST_IN_HEADING", codes(payload))
            hit = next(f for f in payload["findings"]
                       if f["code"] == "TERM_FIRST_IN_HEADING")
            self.assertEqual(hit["line"], 1)


class TexPathRegressionTest(unittest.TestCase):
    """`.tex` 走旧路径：examples/minimal 的读数与退出码逐项锁定。"""

    EXPECTED_METRICS = {
        "abbrev_first_use": 0,
        "colloquial_triad": 0,
        "connective_density": 0.0,
        "dash_parenthetical": 1,
        "empty_adjective": 0.0,
        "explainer_density": 0.0,
        "heading_echo": 0,
        "heading_malformed": 0,
        "heading_relation_changed": 0,
        "heading_subject_lost": 0,
        "heading_too_long": 0,
        "hedge_stack": 0,
        "justify_chain": 0,
        "light_verb_nominalization": 0,
        "nominalization_rate": 0.0,
        "paragraph_template": 0.0,
        "repeated_opener": 0,
        "rhythm_plateau": 1,
        "sentence_length_extreme": 0,
        "sentence_uniformity": 1.0,
        "term_first_in_heading": 0,
        "term_unregistered": 0,
        "term_variant": 0,
        "wordiness_bloat": 0,
        "zh_aspect_zhe": 0.0,
        "zh_collocation_redundancy": 0,
        "zh_dang_when": 0,
        "zh_de_stack": 0,
        "zh_due_to_make": 0,
        "zh_postposed_condition": 0,
        "zh_light_verb_noun": 0,
    }

    def test_examples_minimal_unchanged(self):
        proc = run_cli(ROOT, "style", "examples/minimal", "--json")
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(payload["metrics"], self.EXPECTED_METRICS)
        self.assertEqual(
            [(f["code"], f["file"], f["line"]) for f in payload["findings"]],
            [("DASH_PARENTHETICAL", "sections/01-intro.tex", 6)])
        # 批 109：RHYTHM_PLATEAU 默认只作参考读数，不进 findings。
        self.assertEqual(
            [(f["code"], f["file"], f["line"])
             for f in payload["advisories"]],
            [("RHYTHM_PLATEAU", "sections/01-intro.tex", 9)])
        self.assertEqual(payload["summary"], {
            "files": 2, "words": 198, "sentences": 8, "paragraphs": 3,
            "triggered": 1, "findings": 1, "exit_code": 3,
            "stage": "polished", "advice": "report_only"})

    def test_tex_doc_extension_uses_latex_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.tex").write_text(
                "\\section{短标题}\n\n正文里有一个破折号——像这样。\n",
                encoding="utf-8")
            proc = run_cli(tmp, "style", "--doc", "a.tex", "--json")
            payload = json.loads(proc.stdout)
            self.assertEqual(proc.returncode, 3, proc.stderr)
            self.assertIn("DASH_PARENTHETICAL", codes(payload))


if __name__ == "__main__":
    unittest.main()
