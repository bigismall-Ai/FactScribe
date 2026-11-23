# -*- coding: utf-8 -*-
"""tests/test_workbench_i18n_display.py —— 工作台说明文案的展示层/落盘层分离。

本批修的是端到端验收留下的三处 i18n 缺口：

* P2-1：机器视图「导出与命令」的命令标签与说明（EN 界面下是中文）；
* P2-2：提议单差异卡的正文与告警（EN 界面下是中文）；
* P2-3：追加事实卡的来源显示「Unknown source」。

钉住四件事：

1. **落盘层一字未动**：提议单落盘的 before_text / after_text / warnings 与
   本批之前的逐字原话一致（测试里抄着旧格式串对比）——翻译只发生在展示层；
2. **展示层可翻**：每个展示层字段都带 key ＋ params，英文模板零中文；
3. **目录齐全**：用到的 key 一条不缺（缺一条 → EN 界面回落成中文原话）；
4. **来源不串**：事实的 source（results/ 下的文件）与提议单的来源（mcp）
   是两件事，不能共用一个键（共用过 → 卡片上就是「来源不明」）。

跑法（仓根）：python3 -m pytest tests/test_workbench_i18n_display.py -q
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

from factscribe import i18n  # noqa: E402
from factscribe.config import load_config  # noqa: E402
from factscribe.evidence import (canonical_sha256, entry_count,  # noqa: E402
                                  freeze_evidence, read_lock)
from factscribe.workbench.checkreport import machine_payload  # noqa: E402
from factscribe.workbench.proposal import create_proposal  # noqa: E402
from factscribe.workbench.proposals import display_catalog  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"

#: 中文（CJK 统一表意文字＋全角标点）——EN 文案里出现即红。
CJK_RE = re.compile("[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")

MESSAGES = i18n.WORKBENCH_MESSAGES


# --------------------------------------------------------------------------
# 本批之前的逐字原话（**抄自旧代码**）——落盘层不许漂
# --------------------------------------------------------------------------


def old_declared_summary(declared: dict) -> str:
    lines = []
    for key in sorted(declared):
        ids = ", ".join(str(i) for i in (declared.get(key) or []))
        lines.append("节 %s → %s" % (key, ids or "（无）"))
    return "\n".join(lines) or "（清单为空）"


def old_lock_summary(lock) -> str:
    if not lock:
        return "无（还没冻结过）"
    return "%s（sha256 %s…，%s 条）" % (
        str(lock.get("path") or "audit/evidence.lock"),
        str(lock.get("sha256") or "")[:12],
        int(lock.get("entries") or 0))


#: 本批之前的告警原话（抄自旧代码）。
OLD_WARNINGS = {
    "wb.warn.protect.injected":
        "正文里新写的 %s 已被剥掉：工作台不让人凭空造账本绑定",
    "wb.warn.protect.duplicate":
        "同一个保护面被复制了一次，只保留第一处",
    "wb.warn.protect.restored":
        "被删掉的 %s 标记已按原文位置补回",
    "wb.warn.protect.restoredGeneric":
        "被删掉的 保护 标记已按原文位置补回",
    "wb.warn.shape.noHeading":
        "这一段本身是节标题，但替换文本里没有节标题命令——"
        "采纳后这个标题会消失，请确认这是你要的。",
    "wb.warn.shape.input":
        "替换文本里有 \\input/\\include{%s}——正文段里搬整个文件进来，形状不对。",
    "wb.warn.shape.tooLong":
        "替换文本比原文长很多（%d 字 → %d 字）——确认不是贴错了地方吗？",
}


class Fixture(unittest.TestCase):
    """样例盘副本（测试一律在副本上做，不碰任何正式稿盘）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-i18n-display-"))
        self.disk = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.disk)
        self.state = self.tmp / "state"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def propose(self, kind, **body):
        return create_proposal(self.state, "p", "d", self.disk,
                               dict(body, kind=kind))

    def declared(self) -> dict:
        cfg = load_config(self.disk)
        return dict(getattr(cfg, "evidence_sections", {}) or {})


class ContractTextTests(Fixture):
    """① 落盘层一字未动。"""

    def test_freeze_keeps_the_original_chinese_text(self):
        declared = self.declared()
        digest = canonical_sha256(declared)
        entries = entry_count(declared)
        lock = read_lock(self.disk)
        record = self.propose("evidence_freeze", reason="留底")
        old_before = ("当前清单（[evidence] 声明）：%d 节 / %d 条\n%s\n冻结件：%s"
                      % (len(declared), entries, old_declared_summary(declared),
                         old_lock_summary(lock)))
        old_after = ("冻结件将写入 %s：\n%d 节 / %d 条\n%s\ncanonical_sha256 = %s"
                     "\n冻结理由：%s"
                     % (str((lock or {}).get("path") or "audit/evidence.lock"),
                        len(declared), entries, old_declared_summary(declared),
                        digest, "留底"))
        self.assertEqual(record["before_text"], old_before)
        self.assertEqual(record["after_text"], old_after)

    def test_unfreeze_keeps_the_original_chinese_text(self):
        freeze_evidence(self.disk, {}, "先冻")
        lock = read_lock(self.disk)
        declared = self.declared()
        record = self.propose("evidence_unfreeze", reason="要改清单")
        old_before = ("冻结件：%s\n清单：%d 节 / %d 条\n%s\n状态：已冻结"
                      % (old_lock_summary(lock), len(declared),
                         entry_count(declared), old_declared_summary(declared)))
        old_after = ("冻结件保留（%s），但清单进入「解冻」状态\n"
                     "日志将追加一条 unfreeze 记录到 audit/evidence-log.ndjson\n"
                     "解冻理由：%s"
                     % (str(lock.get("sha256") or "")[:12], "要改清单"))
        self.assertEqual(record["before_text"], old_before)
        self.assertEqual(record["after_text"], old_after)

    def test_add_fact_keeps_the_original_chinese_text(self):
        record = self.propose("add_fact", id="Z9", claim="新增主张",
                              value="7/8", source="results/swb16.md",
                              locator="line 3", confidence="high")
        ledger = str((record.get("fact") or {}).get("ledger") or "")
        old_before = ("账本 %s：当前没有 id=Z9 的事实\n（这条将追加到账本末尾）"
                      % (ledger or "（未定位）"))
        old_after = ("将向账本 %s 追加一条事实：\n%s"
                     % (ledger or "（未定位）", record["proposed_text"]))
        self.assertEqual(record["before_text"], old_before)
        self.assertEqual(record["after_text"], old_after)

    def test_bundle_keeps_the_original_chinese_text(self):
        record = self.propose("export_bundle")
        self.assertEqual(
            record["before_text"],
            "投稿包：还没导出过（本提议会真收集一次并过清单门）")
        self.assertEqual(
            record["after_text"],
            "将导出投稿包：正文 ＋ 事实账 ＋ 参考文献 ＋ PDF\n"
            "清单门逐条核对；门不过就不出包（提议单留在待确认，人可重提）")

    def test_the_warning_texts_are_unchanged(self):
        from factscribe.workbench.write import _warn

        samples = {
            "wb.warn.protect.injected": {"dropped": "\\fact{X9}"},
            "wb.warn.protect.duplicate": {},
            "wb.warn.protect.restored": {"label": "\\fact{A1}"},
            "wb.warn.protect.restoredGeneric": {},
            "wb.warn.shape.noHeading": {},
            "wb.warn.shape.input": {"file": "results/x.md"},
            "wb.warn.shape.tooLong": {"old": 10, "new": 40},
        }
        for key, params in samples.items():
            old = OLD_WARNINGS[key]
            if "%s" in old:
                old = old % (params.get("dropped") or params.get("label")
                             or params.get("file"))
            if "%d" in old:
                old = old % (params.get("old"), params.get("new"))
            warning = _warn(key, params)
            self.assertEqual(warning["text"], old,
                             "%s 的中文原话变了" % key)
            self.assertEqual(warning["key"], key)
            self.assertEqual(warning["params"], params)


class DisplayLayerTests(Fixture):
    """② 展示层可翻：key ＋ params，英文零中文。"""

    def records(self) -> list:
        return [
            self.propose("evidence_freeze", reason="keep it"),
            self.propose("export_bundle"),
            self.propose("add_fact", id="Z9", claim="driver claim",
                         value="7/8", source="results/swb16.md",
                         confidence="high"),
        ]

    def test_every_display_field_is_key_plus_params(self):
        for record in self.records():
            display = record.get("display") or {}
            self.assertIn("before", display)
            self.assertIn("after", display)
            for field in ("before", "after"):
                for item in display[field]:
                    self.assertIsInstance(item, dict)
                    if "text" in item:
                        # 契约内容（落盘的那一份）：逐字保留、不翻译。
                        self.assertIsInstance(item["text"], str)
                        continue
                    self.assertTrue(item.get("key"),
                                    "展示层文案缺 key：%r" % (item,))
                    self.assertIsInstance(item.get("params"), dict)

    def test_the_display_layer_renders_back_to_the_persisted_text(self):
        """展示层按中文渲染 == 落盘层那份（两层不会漂）。"""
        for record in self.records():
            display = record.get("display") or {}
            self.assertEqual(
                i18n.render_parts(display["before"], "zh", MESSAGES),
                record["before_text"])
            self.assertEqual(
                i18n.render_parts(display["after"], "zh", MESSAGES),
                record["after_text"])

    def test_the_english_rendering_has_no_chinese(self):
        for record in self.records():
            display = record.get("display") or {}
            for field in ("before", "after"):
                text = i18n.render_parts(display[field], "en", MESSAGES)
                self.assertFalse(
                    CJK_RE.search(text),
                    "%s 的英文正文里有中文：%s" % (field, text))

    def test_every_key_used_is_in_the_catalog(self):
        keys = set()
        for record in self.records():
            display = record.get("display") or {}
            for field in ("before", "after"):
                keys |= i18n.parts_keys(display[field])
            for item in display.get("warnings") or []:
                keys |= i18n.parts_keys([item])
        self.assertTrue(keys)
        missing = sorted(key for key in keys if key not in MESSAGES)
        self.assertEqual(missing, [],
                         "目录里缺这些 key（EN 界面会回落成中文）：%s" % missing)

    def test_the_catalog_ships_with_the_proposals(self):
        records = self.records()
        catalog = display_catalog(records)
        self.assertTrue(catalog, "提议单列表没带上文案目录")
        for key, entry in catalog.items():
            self.assertIn("zh", entry)
            self.assertIn("en", entry)

    def test_the_english_templates_have_no_chinese(self):
        for key, entry in MESSAGES.items():
            self.assertFalse(CJK_RE.search(entry.get("en") or ""),
                             "%s 的英文模板里有中文" % key)
            self.assertTrue((entry.get("zh") or "").strip(),
                            "%s 的中文模板空了" % key)
            self.assertTrue((entry.get("en") or "").strip(),
                            "%s 的英文模板空了" % key)

    def test_the_english_rendering_of_the_warnings_has_no_chinese(self):
        record = self.propose("evidence_freeze", reason="keep it")
        display = record.get("display") or {}
        parts = display.get("warnings") or []
        self.assertTrue(parts, "冻结单该带一条告警")
        text = "；".join(i18n.render_parts([item], "en", MESSAGES)
                         for item in parts)
        self.assertFalse(CJK_RE.search(text),
                          "英文告警里有中文：%s" % text)


class MachineViewTests(Fixture):
    """③ 机器视图「导出与命令」：标签与说明走 i18n。"""

    def test_the_command_labels_keep_their_chinese_and_carry_keys(self):
        payload = machine_payload(self.disk)
        group = (payload.get("groups") or {}).get("export") or {}
        commands = group.get("commands") or []
        self.assertEqual(len(commands), 4)
        old_labels = ["真闸体检（只读）", "账本体检（只读）",
                      "追溯矩阵（写 audit/matrix.md）",
                      "证据冻结（写 audit/evidence.lock）"]
        for command, old in zip(commands, old_labels):
            self.assertEqual(command.get("label"), old)
            self.assertTrue(command.get("label_key"),
                            "命令标签没带 label_key：%r" % command)
        self.assertEqual(
            group.get("note"),
            "本视图只读；上面前两条是只读命令，后两条会写盘，需人自己跑。")
        self.assertTrue(group.get("note_key"), "说明没带 note_key")

    def test_the_machine_payload_ships_the_catalog(self):
        payload = machine_payload(self.disk)
        catalog = payload.get("i18n") or {}
        self.assertTrue(catalog, "机器视图没带文案目录")
        for key, entry in catalog.items():
            self.assertIn("zh", entry)
            self.assertIn("en", entry)
            self.assertFalse(CJK_RE.search(entry.get("en") or ""),
                             "%s 的英文模板里有中文" % key)

    def test_the_english_command_labels_have_no_chinese(self):
        payload = machine_payload(self.disk)
        group = (payload.get("groups") or {}).get("export") or {}
        catalog = payload.get("i18n") or {}
        for command in group.get("commands") or []:
            text = i18n.render(command["label_key"], {}, "en", catalog)
            self.assertFalse(CJK_RE.search(text),
                              "命令标签的英文里有中文：%s" % text)
        note = i18n.render(group["note_key"], {}, "en", catalog)
        self.assertFalse(CJK_RE.search(note), "说明的英文里有中文：%s" % note)


class OriginTests(Fixture):
    """④ 来源不串：事实的 source 与提议单的来源是两件事。"""

    def fact_body(self) -> dict:
        return {"id": "Z9", "claim": "driver claim", "value": "7/8",
                "source": "results/swb16.md", "locator": "line 3",
                "confidence": "high"}

    def test_the_fact_source_does_not_clobber_the_proposal_origin(self):
        """新式（fact 子对象）：提议单的来源是 mcp，事实的来源是结果文件。"""
        record = self.propose("add_fact", source="mcp",
                               fact=self.fact_body())
        self.assertEqual(record.get("source"), "mcp",
                         "追加事实的提议单来源被事实的 source 覆盖了")
        self.assertEqual((record.get("fact") or {}).get("source"),
                         "results/swb16.md", "事实自己的来源丢了")
        self.assertIn("Z9", record["after_text"])

    def test_the_flat_legacy_body_still_works(self):
        """旧式（平铺）仍认：事实字段照旧读，来源就是那个平铺值。"""
        record = self.propose("add_fact", **self.fact_body())
        self.assertEqual((record.get("fact") or {}).get("source"),
                         "results/swb16.md")
        self.assertIn("Z9", record["after_text"])

    def test_the_other_four_kinds_keep_their_origin(self):
        for kind in ("evidence_freeze", "evidence_unfreeze",
                     "export_bundle"):
            body = {"source": "mcp"}
            if kind == "evidence_unfreeze":
                freeze_evidence(self.disk, {}, "先冻")
                body["reason"] = "要改清单"
            if kind == "evidence_freeze":
                body["reason"] = "留底"
            record = self.propose(kind, **body)
            self.assertEqual(record.get("source"), "mcp",
                             "%s 的来源不对" % kind)


class ProposalShapeTests(Fixture):
    """⑤ 提议单的形状：只增键，不改既有字段。"""

    def test_the_old_fields_are_still_there(self):
        common = ("kind", "file", "block", "before_sha", "before_text",
                  "proposed_text", "after_text", "warnings", "source",
                  "rationale")
        for record in (self.propose("evidence_freeze", reason="留底"),
                       self.propose("export_bundle")):
            for key in common:
                self.assertIn(key, record)
            self.assertIsInstance(record["warnings"], list)
            for warning in record["warnings"]:
                self.assertIsInstance(warning, str)
            self.assertIn("display", record)


class FrontendWiringTests(unittest.TestCase):
    """⑥ 前端接线：按界面语言渲染，不许退回中文硬编码。

    行为由浏览器实跑验；这里钉住「接线」——页面确实在用展示层的
    key ＋ params，而不是继续拿中文原话当最终答案。
    """

    def setUp(self):
        self.src = (ROOT / "factscribe" / "workbench" / "static"
                     / "app.js").read_text(encoding="utf-8")

    def test_the_proposal_card_renders_the_display_layer(self):
        self.assertIn("renderParts(display.before, catalog, row.before_text)",
                      self.src)
        self.assertIn("renderParts(display.after, catalog, row.after_text)",
                      self.src)

    def test_the_machine_view_uses_the_label_keys(self):
        self.assertIn("catalogMsg(catalog, c.label_key", self.src)
        self.assertIn("catalogMsg(catalog, ex.note_key", self.src)

    def test_the_proposal_catalog_comes_from_the_payload(self):
        self.assertIn("state.proposalCatalog = (data && data.i18n) || {};",
                      self.src)

if __name__ == "__main__":
    unittest.main()
