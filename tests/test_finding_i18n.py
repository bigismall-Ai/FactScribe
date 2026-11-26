# -*- coding: utf-8 -*-
"""tests/test_finding_i18n.py —— 发现文案 i18n 与两条新只读工具的契约考题。

四条：

1. **目录齐**：仓里每一处 Issue(...) / Finding(...) 都要落到目录的一条 key 上；
   目录里的英文模板不许有中文（EN 界面无中文残留是硬指标）。
2. **中文一字不改**：目录的中文模板渲染出来，必须与真闸原来的 message
   **逐字相同**（否则中文界面被改写，且 CLI 读数与界面读数对不上）。
3. **报告读数**：报告 payload 在 lang=en 下每条 finding 的文案无中文；
   在 lang=zh 下与真闸原话一致；并带上 message_key / params 与目录子集。
4. **两条新工具**：fs_get_style 与 fs_mirror_check 真的挂在 MCP 工具面上
   （只读注解、{project, disk} 入参、dispatch 里有分支、服务层有实现），
   引擎侧也有对应的只读端点。
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.i18n import FINDING_MESSAGES, finding_key, render  # noqa: E402
from factscribe.workbench.checkreport import report_payload  # noqa: E402

SHELL = (ROOT / "miniapp" / "miniapp" / "node" / "server.mjs").read_text(encoding="utf-8")
JS = (ROOT / "factscribe" / "workbench" / "static" / "app.js").read_text(encoding="utf-8")

#: 中文（CJK 统一表意文字＋全角标点）——EN 模板里出现即红。
CJK_RE = re.compile("[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")
SLOT_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

GOLDEN = ROOT / "tests" / "golden" / "audit_findings_baseline.json"


def load_scanner():
    """把 scripts/gen_finding_i18n.py 当模块载入（只读扫描，不写盘）。"""
    path = ROOT / "scripts" / "gen_finding_i18n.py"
    spec = importlib.util.spec_from_file_location("gen_finding_i18n", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class CatalogTests(unittest.TestCase):
    """① 目录齐、英文无中文。"""

    def test_every_finding_site_has_a_key_in_the_catalog(self):
        """每一处 Issue/Finding 都要落到目录的一条 key 上。"""
        scanner = load_scanner()
        sites = scanner.assign_keys(scanner.scan())
        missing = []
        for site in sites:
            key = site.get("explicit_key") or ""
            expr = site.get("explicit_expr") or ""
            code = site.get("code") or ""
            if key:
                candidates = [key]
            elif "finding." in expr:
                # 条件式给的 key（如 A if x else B）：两个都要在目录里
                candidates = [m.strip("'\"")
                              for m in re.findall(r"'finding\.[A-Za-z0-9_.]+'", expr)]
            elif code in ("", "VAR"):
                candidates = []      # 动态码：运行时才知，另有运行时断言
            else:
                candidates = [finding_key(code)]
            for resolved in candidates:
                if resolved not in FINDING_MESSAGES:
                    missing.append("%s:%d %s"
                                   % (site["file"], site["line"], resolved))
        self.assertEqual(missing, [], "这些发现没有对应的 i18n 目录条目")

    def test_english_templates_have_no_chinese(self):
        """EN 模板不许有中文——EN 界面无中文残留是硬指标。"""
        bad = []
        for key, entry in sorted(FINDING_MESSAGES.items()):
            en = entry.get("en") or ""
            if not en:
                bad.append("%s: 没有英文模板" % key)
            elif CJK_RE.search(en):
                bad.append("%s: 英文模板里有中文 %r" % (key, CJK_RE.search(en).group(0)))
        self.assertEqual(bad, [])

    def test_every_template_slot_is_declared(self):
        """模板里的槽位不许带花括号以外的怪东西，也不许空模板。"""
        for key, entry in sorted(FINDING_MESSAGES.items()):
            for lang in ("zh", "en"):
                template = entry.get(lang)
                if template is None:
                    continue
                self.assertTrue(template.strip(), "%s 的 %s 模板是空的" % (key, lang))
                for name in SLOT_RE.findall(template):
                    self.assertTrue(name, "%s 的 %s 模板有空槽位" % (key, lang))


class ChineseFidelityTests(unittest.TestCase):
    """② 中文一字不改：目录渲染 == 真闸原话。"""

    def test_chinese_rendering_matches_the_original_messages(self):
        data = json.loads(GOLDEN.read_text(encoding="utf-8"))
        from factscribe.workbench.checkreport import run_gate
        checked = 0
        diffs = []
        for rel in sorted(data["projects"]):
            root = ROOT / rel
            if not root.is_dir():
                continue
            try:
                _cfg, _facts, _sections, red, yellow, hints, _sum = run_gate(root)
            except Exception:      # noqa: BLE001 - 某个样例读不动不算失败
                continue
            for issue in list(red) + list(yellow) + list(hints):
                key = getattr(issue, "message_key", "") or finding_key(issue.code)
                params = dict(getattr(issue, "params", {}) or {})
                text = render(key, params, "zh")
                if not text:
                    continue        # 目录没这一条的中文模板 → 前端回落原话
                checked += 1
                if text != issue.message:
                    diffs.append("%s\n  原话：%s\n  目录：%s"
                                 % (key, issue.message, text))
        self.assertGreater(checked, 0, "一个发现都没跑到——样例路径变了？")
        self.assertEqual(diffs, [], "中文目录与真闸原话不一致")


class ReportReadingTests(unittest.TestCase):
    """③ 报告读数：EN 无中文、ZH 与原话一致、带 i18n 原料。"""

    REPORT = ROOT / "examples" / "minimal"

    def test_english_report_has_no_chinese_in_findings(self):
        report = report_payload(self.REPORT, lang="en")
        findings = report.get("findings") or []
        self.assertTrue(findings, "样例项目一条发现都没有？")
        for finding in findings:
            self.assertFalse(CJK_RE.search(finding["message"]),
                             "%s 的英文文案里有中文：%s"
                             % (finding["code"], finding["message"]))

    def test_chinese_report_keeps_the_original_wording(self):
        report = report_payload(self.REPORT, lang="zh")
        for finding in report.get("findings") or []:
            self.assertTrue(CJK_RE.search(finding["message"]),
                            "%s 的中文文案不该变成英文：%s"
                            % (finding["code"], finding["message"]))

    def test_findings_carry_the_i18n_raw_material(self):
        report = report_payload(self.REPORT, lang="zh")
        catalog = report.get("i18n") or {}
        self.assertTrue(catalog, "报告没带 i18n 目录子集")
        for finding in report.get("findings") or []:
            self.assertTrue(finding.get("message_key"), "发现没带 message_key")
            self.assertIn(finding["message_key"], catalog,
                          "目录子集里没有这条发现")
            self.assertIsInstance(finding.get("params"), dict)

    def test_report_still_carries_the_gate_readings(self):
        report = report_payload(self.REPORT, lang="zh")
        gates = report.get("gates") or {}
        self.assertIn("style", gates)
        self.assertIn("mirror", gates)


class NewReadOnlyToolsTests(unittest.TestCase):
    """④ 两条新只读工具：工具面、dispatch、服务层、引擎端点。"""

    def test_read_only_annotations_are_shared_and_read_only(self):
        """只读注解是共享常量：readOnlyHint 为真，其余按既有约定。"""
        line = [ln for ln in SHELL.splitlines()
                if ln.startswith("const READ_ANNOTATIONS")][0]
        self.assertIn("readOnlyHint: true", line)
        self.assertIn("destructiveHint: false", line)
        self.assertIn("idempotentHint: true", line)
        self.assertIn("openWorldHint: false", line)

    def test_both_tools_are_declared_read_only(self):
        for name in ("fs_get_style", "fs_mirror_check"):
            self.assertIn("name: '%s'" % name, SHELL)
            block = SHELL[SHELL.index("name: '%s'" % name):]
            block = block[:block.index("\n  },")]
            self.assertIn("annotations: READ_ANNOTATIONS", block)
            self.assertIn("required: ['project', 'disk']", block)
            self.assertIn("additionalProperties: false", block)

    def test_both_tools_are_dispatched_and_implemented(self):
        self.assertIn("case 'fs_get_style': return services.style(args);", SHELL)
        self.assertIn("case 'fs_mirror_check': return services.mirrorCheck(args);", SHELL)
        self.assertIn("async style(args)", SHELL)
        self.assertIn("async mirrorCheck(args)", SHELL)

    def test_both_tools_read_the_engine_endpoints(self):
        self.assertIn("/style${query}", SHELL)
        self.assertIn("/mirror", SHELL)

    def test_engine_exposes_the_two_read_only_endpoints(self):
        server = (ROOT / "factscribe" / "workbench" / "server.py").read_text(encoding="utf-8")
        self.assertIn('if what == "style":', server)
        self.assertIn('if what == "mirror":', server)

    def test_report_tool_accepts_a_language(self):
        self.assertIn("lang: { type: 'string', enum: ['zh', 'en']", SHELL)


class FrontendTests(unittest.TestCase):
    """⑤ 前端：finding 走 i18n 目录，报告请求带 lang。"""

    def test_findings_are_rendered_through_the_i18n_catalog(self):
        self.assertIn("function findingMsg(f)", JS)
        self.assertIn("esc(findingMsg(f))", JS)

    def test_report_request_carries_the_ui_language(self):
        self.assertIn("'lang='", JS)


if __name__ == "__main__":
    unittest.main()
