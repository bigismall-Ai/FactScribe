# -*- coding: utf-8 -*-
"""两条 MCP 面与 CLI 的 finding 文案口径（G4 / G5）。

钉住：

- CLI 的 MCP 面（factscribe_audit）：每条 finding 都带 message_key ＋ params
  （i18n 原料）；lang=en 出英文版，缺省还是中文原话；
- CLI 的 audit --json：**不给 --lang 就是现在的样子**（金样例逐字节锁着
  那条路的四个数组）；给了 --lang 才渲染并补 i18n 原料；
- CLI 的 style --json：findings 形状只增键（message_key ＋ params ＋
  message），默认中文、--lang en 出英文。

跑法（仓根）：python3 -m pytest tests/test_cli_lang.py -q
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CJK_RE = re.compile("[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")
MINIMAL = ROOT / "examples" / "minimal"


def run_cli(*args) -> dict:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    proc = subprocess.run([sys.executable, "-m", "factscribe", *args],
                          cwd=str(ROOT), env=env, capture_output=True,
                          text=True)
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise AssertionError("CLI 没给回 JSON：%s\n%s"
                             % (proc.stdout[-800:], proc.stderr[-800:]))


class AuditJsonLangTests(unittest.TestCase):
    """audit --json 的 --lang。"""

    def test_default_shape_is_unchanged(self):
        data = run_cli("audit", str(MINIMAL), "--json")
        for item in data.get("findings") or []:
            # 金样例锁着这条路的四个数组：默认形状一个字都不许多。
            self.assertNotIn("message_key", item)
            self.assertNotIn("params", item)

    def test_english_reading_has_no_chinese(self):
        data = run_cli("audit", str(MINIMAL), "--json", "--lang", "en")
        findings = data.get("findings") or []
        self.assertTrue(findings, "一条发现都没有？")
        for item in findings:
            self.assertFalse(CJK_RE.search(item.get("message") or ""),
                             "%s 的英文文案里有中文：%s"
                             % (item.get("code"), item.get("message")))
            self.assertTrue(item.get("message_key"))
            self.assertIsInstance(item.get("params"), dict)

    def test_explicit_chinese_keeps_the_gate_wording(self):
        zh = run_cli("audit", str(MINIMAL), "--json")
        explicit = run_cli("audit", str(MINIMAL), "--json", "--lang", "zh")
        self.assertEqual([f.get("message") for f in zh.get("findings") or []],
                         [f.get("message")
                          for f in explicit.get("findings") or []])
        for item in explicit.get("findings") or []:
            self.assertTrue(item.get("message_key"))


class StyleJsonLangTests(unittest.TestCase):
    """style --json 的 --lang ＋ 只增键。"""

    def test_findings_carry_the_i18n_raw_material(self):
        data = run_cli("style", str(MINIMAL), "--json")
        findings = data.get("findings") or []
        self.assertTrue(findings, "一条文风发现都没有？")
        for item in findings:
            self.assertTrue(item.get("message_key"))
            self.assertIsInstance(item.get("params"), dict)
            self.assertIn("message", item)

    def test_english_style_reading_has_no_chinese(self):
        data = run_cli("style", str(MINIMAL), "--json", "--lang", "en")
        findings = data.get("findings") or []
        self.assertTrue(findings, "一条文风发现都没有？")
        for item in findings:
            self.assertFalse(CJK_RE.search(item.get("message") or ""),
                             "%s 的英文文案里有中文：%s"
                             % (item.get("code"), item.get("message")))


class McpFaceTests(unittest.TestCase):
    """CLI 的 MCP 面（factscribe_audit 走的数据层）。"""

    def test_mcp_face_carries_message_key_and_params(self):
        from factscribe.workbench_dataplayer import audit_data

        data = audit_data(MINIMAL)
        findings = data.get("findings") or []
        self.assertTrue(findings, "一条发现都没有？")
        for item in findings:
            self.assertTrue(item.get("message_key"))
            self.assertIsInstance(item.get("params"), dict)

    def test_mcp_face_english_reading(self):
        from factscribe.workbench_dataplayer import audit_data

        data = audit_data(MINIMAL, "en")
        for item in data.get("findings") or []:
            self.assertFalse(CJK_RE.search(item.get("message") or ""),
                             "%s 的英文文案里有中文：%s"
                             % (item.get("code"), item.get("message")))

    def test_mcp_face_default_is_the_gate_wording(self):
        from factscribe.workbench_dataplayer import audit_data

        zh = audit_data(MINIMAL)
        for item in zh.get("findings") or []:
            self.assertTrue(CJK_RE.search(item.get("message") or ""),
                            "中文面不该变成英文：%s" % item.get("message"))


class ModelCatalogTests(unittest.TestCase):
    """G6：模型档位共用声明。"""

    def test_catalog_shape_matches_the_miniapp_panel(self):
        from factscribe.workbench.ai import model_catalog

        catalog = model_catalog(MINIMAL)
        self.assertEqual(catalog.get("source"), "engine")
        self.assertTrue(catalog.get("models"))
        for entry in catalog["models"]:
            for key in ("id", "kind", "label", "model", "efforts",
                        "defaultEffort"):
                self.assertIn(key, entry)
            self.assertEqual(entry["kind"], "engine")
            self.assertTrue(entry["id"].startswith("engine:"))


if __name__ == "__main__":
    unittest.main()
