# -*- coding: utf-8 -*-
"""批 99：解释性套语判据（全离线）。

规范：`docs/design/SPEC-EXPLAINER.md`。

覆盖：

* `EXPLAINER_DENSITY` 中英文正例、负例、阈值可配；
* 围栏代码与 Markdown 列表项里的套语不报；
* `JUSTIFY_CHAIN` 同段 ≥2 句、连续 ≥2 段收尾两个分支，以及各自的负例；
* 旧版答辩腔的最小复现（「它证明的是…。它不证明…。」）；
* 当前 `docs/WHAT-IT-PROVES.md` 为 0 条；
* 第七条处方 `drop-the-proof` 可由 `prescribe --for` 查到。
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

from factscribe.config import Config  # noqa: E402
from factscribe.prescribe import prescriptions_for  # noqa: E402
from factscribe.style import analyze, load_style_rules  # noqa: E402


def analyze_md(text: str, rules: str = "", fmt: str = "markdown") -> object:
    """把一段文档当独立文件跑 style，返回 StyleResult。"""
    name = "doc.tex" if fmt == "tex" else "doc.md"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if rules:
            (root / "style-rules.toml").write_text(rules, encoding="utf-8")
        loaded, path = load_style_rules(root)
        result = analyze(Config(root=root), [(name, text)], loaded,
                         rules_path=path, formats={name: fmt})
    return result


def codes(result) -> set:
    return {f.code for f in result.findings}


def run_cli(*args: str):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run([sys.executable, "-m", "factscribe", *args],
                          cwd=str(ROOT), capture_output=True, text=True,
                          env=env)


# --------------------------------------------------------------------------
# 样本
# --------------------------------------------------------------------------

# 每段一句解释 + 一句事实：段末不是解释句，因此只可能触发密度，不触发链。
DENSITY_ZH = "\n\n".join(
    "这说明主对照只有十六单。主对照的区间宽到十三到十九单。"
    for _ in range(6))
DENSITY_EN = "\n\n".join(
    "This means the main comparison has sixteen instances. "
    "The interval runs from thirteen to nineteen instances."
    for _ in range(6))
PLAIN_ZH = "\n\n".join(
    "主对照只有十六单。区间宽到十三到十九单，方向比大小可靠。"
    for _ in range(6))

# 同段两句解释：密度用 1000 隔离，确保只在测链。
CHAIN_SAME_PARA = (
    "主对照只有十六单。这意味着区间宽到十三到十九单。"
    "由此可见，方向比大小可靠。"
)
CHAIN_SAME_PARA_NEG = (
    "主对照只有十六单。区间宽到十三到十九单。"
    "这说明区间很宽，方向比大小可靠。"
)
# 连续两段都以解释句收尾；第三段普通，用来验证「连续」不是「出现两次」。
CHAIN_RUN = (
    "主对照只有十六单。这正是区间宽的原因。\n\n"
    "主对照的方向比大小可靠。这正是我们只看方向的原因。\n\n"
    "第三段停在事实上，不做解释。"
)
CHAIN_NOT_ADJACENT = (
    "主对照只有十六单。这正是区间宽的原因。\n\n"
    "中间这段是普通事实，停在区间上。\n\n"
    "主对照的方向比大小可靠。这正是我们只看方向的原因。"
)
# 旧版 f7075f4 的开场句：每句都要跟一个证明。
OLD_PROOF = (
    "它证明的是「账、据、文三者自洽，且据未被改」。\n"
    "它不证明「论文为真」。"
)
CODE_AND_LIST = """正文只留一句普通事实。

```text
这说明代码里的这句话不该被统计。
也就是说，围栏里的套语也不算。
```

- 也就是说，列表项里的套语不算。
- 这意味着第二项也不算。
- 原因在于列表天然等长。

最后一段停在事实上。
"""

BLOCKQUOTE = """> 也就是说，引文里的套语不算。
> 这意味着引文整段都不进统计。
> 这正是引用别人时的话。

正文只有这一句普通事实。
"""

TEX_QUOTE = r"""\section{短标题}

正文只有一句普通事实。

\begin{quote}
这说明引文里的套语不算。这意味着也不算。这正是引用别人的话。
\end{quote}

最后一句停在事实上。
"""

DENSITY_HIGH = "[thresholds]\nexplainer_density = 1000.0\n"
CHAIN_ISOLATED = "[thresholds]\nexplainer_density = 1000.0\n"
CHAIN_SENTENCES_3 = (
    "[thresholds]\nexplainer_density = 1000.0\n"
    "justify_chain_min_sentences = 3\n"
)


# --------------------------------------------------------------------------
# 1. EXPLAINER_DENSITY
# --------------------------------------------------------------------------

class TestExplainerDensity(unittest.TestCase):
    def test_positive_chinese(self):
        result = analyze_md(DENSITY_ZH)
        self.assertIn("EXPLAINER_DENSITY", codes(result))
        self.assertGreater(result.metrics["explainer_density"],
                           result.thresholds["explainer_density"])

    def test_positive_english(self):
        result = analyze_md(DENSITY_EN)
        self.assertIn("EXPLAINER_DENSITY", codes(result))

    def test_negative_plain_prose(self):
        result = analyze_md(PLAIN_ZH)
        self.assertNotIn("EXPLAINER_DENSITY", codes(result))
        self.assertEqual(result.metrics["explainer_density"], 0.0)

    def test_threshold_from_toml_changes_verdict(self):
        base = analyze_md(DENSITY_ZH)
        raised = analyze_md(DENSITY_ZH, DENSITY_HIGH)
        self.assertIn("EXPLAINER_DENSITY", codes(base))
        self.assertNotIn("EXPLAINER_DENSITY", codes(raised))

    def test_mid_sentence_phrase_not_counted(self):
        body = "\n\n".join(
            "主对照只有十六单，这意味着区间宽到十三到十九单。"
            for _ in range(6))
        result = analyze_md(body)
        self.assertNotIn("EXPLAINER_DENSITY", codes(result))

    def test_code_block_and_list_not_counted(self):
        result = analyze_md(CODE_AND_LIST)
        self.assertNotIn("EXPLAINER_DENSITY", codes(result))
        self.assertEqual(result.metrics["explainer_density"], 0.0)

    def test_blockquote_not_counted(self):
        result = analyze_md(BLOCKQUOTE)
        self.assertNotIn("EXPLAINER_DENSITY", codes(result))
        self.assertEqual(result.metrics["explainer_density"], 0.0)

    def test_old_proof_opening_reproduces(self):
        result = analyze_md(OLD_PROOF)
        self.assertIn("EXPLAINER_DENSITY", codes(result))

    def test_latex_quote_environment_not_counted(self):
        result = analyze_md(TEX_QUOTE, fmt="tex")
        self.assertNotIn("EXPLAINER_DENSITY", codes(result))
        self.assertNotIn("JUSTIFY_CHAIN", codes(result))
        self.assertEqual(result.metrics["explainer_density"], 0.0)
        self.assertEqual(result.metrics["justify_chain"], 0)


# --------------------------------------------------------------------------
# 2. JUSTIFY_CHAIN
# --------------------------------------------------------------------------

class TestJustifyChain(unittest.TestCase):
    def test_same_paragraph_two_sentences(self):
        result = analyze_md(CHAIN_SAME_PARA, CHAIN_ISOLATED)
        self.assertIn("JUSTIFY_CHAIN", codes(result))
        self.assertEqual(result.metrics["justify_chain"], 1)

    def test_same_paragraph_single_sentence_negative(self):
        result = analyze_md(CHAIN_SAME_PARA_NEG, CHAIN_ISOLATED)
        self.assertNotIn("JUSTIFY_CHAIN", codes(result))

    def test_consecutive_paragraphs_close_with_explainer(self):
        result = analyze_md(CHAIN_RUN, CHAIN_ISOLATED)
        self.assertIn("JUSTIFY_CHAIN", codes(result))
        self.assertEqual(result.metrics["justify_chain"], 1)

    def test_non_adjacent_paragraphs_negative(self):
        result = analyze_md(CHAIN_NOT_ADJACENT, CHAIN_ISOLATED)
        self.assertNotIn("JUSTIFY_CHAIN", codes(result))

    def test_same_paragraph_threshold_configurable(self):
        result = analyze_md(CHAIN_SAME_PARA, CHAIN_SENTENCES_3)
        self.assertNotIn("JUSTIFY_CHAIN", codes(result))

    def test_old_proof_opening_is_a_chain(self):
        result = analyze_md(OLD_PROOF)
        self.assertIn("JUSTIFY_CHAIN", codes(result))

    def test_code_block_and_list_not_counted(self):
        result = analyze_md(CODE_AND_LIST, CHAIN_ISOLATED)
        self.assertNotIn("JUSTIFY_CHAIN", codes(result))
        self.assertEqual(result.metrics["justify_chain"], 0)

    def test_blockquote_not_counted(self):
        result = analyze_md(BLOCKQUOTE, CHAIN_ISOLATED)
        self.assertNotIn("JUSTIFY_CHAIN", codes(result))
        self.assertEqual(result.metrics["justify_chain"], 0)

    def test_current_proves_doc_is_clean(self):
        text = (ROOT / "docs" / "WHAT-IT-PROVES.md").read_text(encoding="utf-8")
        result = analyze_md(text)
        self.assertNotIn("EXPLAINER_DENSITY", codes(result))
        self.assertNotIn("JUSTIFY_CHAIN", codes(result))
        self.assertEqual(result.metrics["explainer_density"], 0.0)
        self.assertEqual(result.metrics["justify_chain"], 0)


# --------------------------------------------------------------------------
# 3. 处方
# --------------------------------------------------------------------------

class TestDropTheProofPrescription(unittest.TestCase):
    def test_both_codes_map_to_drop_the_proof(self):
        for code in ("EXPLAINER_DENSITY", "JUSTIFY_CHAIN"):
            with self.subTest(code=code):
                found = prescriptions_for(code)
                self.assertEqual([p.name for p in found], ["drop-the-proof"])

    def test_cli_for_code(self):
        proc = run_cli("prescribe", "--for", "EXPLAINER_DENSITY", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        names = [item["name"] for item in payload["prescriptions"]]
        self.assertEqual(names, ["drop-the-proof"])

    def test_prescription_has_counterexample_and_acceptance(self):
        text = prescriptions_for("EXPLAINER_DENSITY")[0].text
        self.assertIn("数字全对，结论照样可能是错的。这是最常见的一种误会。",
                      text)
        self.assertGreaterEqual(text.count("数字全对，结论照样可能是错的。"), 2)
        self.assertIn("style --doc", text)
        self.assertIn("EXPLAINER_DENSITY", text)
        self.assertIn("JUSTIFY_CHAIN", text)


if __name__ == "__main__":
    unittest.main()
