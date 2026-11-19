# -*- coding: utf-8 -*-
"""工作台段四：实验报告导入走真文件。

被测路径（真 HTTP）：

  GET  /api/project/<p>/reports/dir      列报告目录下的真实文件
  POST /api/project/<p>/reports/upload   上传（multipart）进报告目录
  POST /api/project/<p>/reports/parse    解析（行形 ＋ 坏行容错）
  POST /api/project/<p>/reports/confirm  写草稿

最要紧的一条：**导入绝不写活账本** `facts/*.toml`——导入前后账本哈希一致，
草稿只落在 `facts/draft/<报告名>.draft.toml`。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from factscribe.workbench import importer
from factscribe.workbench.server import create_server

REPO = Path(__file__).resolve().parents[1]
SAMPLES = [REPO / "examples" / "minimal", REPO / "fixtures" / "legal-demo"]

REPORT_TOML = """\
[[metric]]
id = "blind_pairs"
claim = "盲评对数"
value = "10"
source = "table2"

[[metric]]
id = "j1_guided"
claim = "JUDGE-1 判引导稿胜"
value = "9"
source = "table2"

[[metric]]
id = "drift"
claim = "中英盘漂移"
value = "0"
source = "mirror"
"""

REPORT_JSON = """\
[
  {"id": "pairs", "claim": "盲评对数", "value": "10", "source": "t2"},
  {"id": "no_value_here", "claim": "只有断言"}
]
"""


def _dir_manifest(root: Path, skip: tuple = ()) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = Path(dirpath) / name
            rel = str(full.relative_to(root))
            if any(rel.startswith(prefix) for prefix in skip):
                continue
            try:
                out[rel] = hashlib.sha256(full.read_bytes()).hexdigest()
            except OSError:
                out[rel] = ""
    return out


def _ledger_manifest(root: Path) -> dict:
    """活账本 `facts/*.toml` 的哈希（不含 facts/draft/）。"""
    facts = root / "facts"
    out = {}
    if not facts.is_dir():
        return out
    for path in sorted(facts.glob("*.toml")):
        out[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _sample_copy(tmp: Path) -> Path:
    for sample in SAMPLES:
        if sample.is_dir():
            dst = tmp / sample.name
            shutil.copytree(sample, dst)
            return dst
    raise unittest.SkipTest("仓库里没有可用的真项目样本")


class _ServerCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.project = _sample_copy(self.tmp)
        self.server, self.index = create_server(self.tmp)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self._tmp.cleanup)
        project = self.index.projects()[0]
        self.project_id = project["id"]
        self.disk_id = project["disks"][0]["id"]
        self.disk_path = Path(project["disks"][0]["path"])
        self.reports_dir = importer.reports_dir(self.disk_path)

    # ---- HTTP 小工具 ----

    def _url(self, suffix: str) -> str:
        return "http://127.0.0.1:%d/api/project/%s/reports%s" % (
            self.port, self.project_id, suffix)

    def _get_json(self, suffix: str):
        with urllib.request.urlopen(self._url(suffix), timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, suffix: str, payload: dict):
        request = urllib.request.Request(
            self._url(suffix),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_multipart(self, suffix: str, filename: str, payload: bytes):
        boundary = "----factscribe-test-boundary"
        body = (
            ("--%s\r\n" % boundary).encode("utf-8")
            + ('Content-Disposition: form-data; name="file"; filename="%s"\r\n'
               % filename).encode("utf-8")
            + b"Content-Type: application/octet-stream\r\n\r\n"
            + payload + ("\r\n--%s--\r\n" % boundary).encode("utf-8"))
        request = urllib.request.Request(
            self._url(suffix), data=body,
            headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary},
            method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class TestReportDirEndpoint(_ServerCase):
    def test_dir_lists_real_files(self):
        """列的是报告目录下的真实文件。"""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        (self.reports_dir / "blind69.report.toml").write_text(
            REPORT_TOML, encoding="utf-8")
        (self.reports_dir / "notes.txt").write_text("不是报告", encoding="utf-8")
        data = self._get_json("/dir")
        self.assertTrue(data["ok"])
        names = [item["name"] for item in data["files"]]
        self.assertIn("blind69.report.toml", names)
        self.assertNotIn("notes.txt", names)  # 只认 toml / json
        for item in data["files"]:
            self.assertTrue(Path(item["path"]).is_file())

    def test_dir_missing_is_empty_not_error(self):
        """目录不存在：结构化空清单，不 500。"""
        data = self._get_json("/dir")
        self.assertTrue(data["ok"])
        self.assertEqual(data["files"], [])
        self.assertFalse(data["exists"])


class TestReportImportFlow(_ServerCase):
    def test_three_step_flow_writes_draft_only(self):
        """三步走通：列目录 → 解析 → 写草稿；活账本零改动。"""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        report = self.reports_dir / "blind69.report.toml"
        report.write_text(REPORT_TOML, encoding="utf-8")

        ledger_before = _ledger_manifest(self.project)
        tree_before = _dir_manifest(self.project, skip=("facts/draft",))

        # ① 列目录
        listing = self._get_json("/dir")
        self.assertIn("blind69.report.toml",
                      [item["name"] for item in listing["files"]])

        # ② 解析
        parsed = self._post_json("/parse", {"name": "blind69.report.toml"})
        self.assertTrue(parsed["ok"])
        self.assertEqual(len(parsed["rows"]), 3)
        self.assertEqual(parsed["rows"][0]["id"], "blind_pairs")
        self.assertEqual(parsed["rows"][0]["value"], "10")
        self.assertEqual(parsed["failed"], [])
        self.assertTrue(parsed["sha256"])
        self.assertEqual([s["id"] for s in parsed["suggested"]],
                         [row["id"] for row in parsed["rows"]])

        # ③ 确认绑定 → 写草稿
        mapping = {row["id"]: row["id"] for row in parsed["rows"]}
        confirmed = self._post_json("/confirm", {
            "name": "blind69.report.toml",
            "report_name": "盲评批次69",
            "rows": parsed["rows"],
            "mapping": mapping,
        })
        self.assertTrue(confirmed["ok"])
        self.assertEqual(confirmed["count"], 3)
        draft = Path(confirmed["draft_path"])
        self.assertTrue(draft.is_file())
        self.assertEqual(draft.parent.name, "draft")
        self.assertEqual(draft.parent.parent.name, "facts")
        self.assertTrue(draft.name.endswith(".draft.toml"))

        # 草稿内容：provenance ＋ confidence=low ＋ 状态「待核对」
        text = draft.read_text(encoding="utf-8")
        self.assertIn("confidence = \"low\"", text)
        self.assertIn("status = \"待核对\"", text)
        self.assertIn("[fact.provenance]", text)
        self.assertIn(parsed["sha256"], text)
        self.assertIn(str(report), text)
        self.assertEqual(text.count("[[fact]]"), 3)

        # 活账本零改动
        self.assertEqual(_ledger_manifest(self.project), ledger_before)
        self.assertEqual(_dir_manifest(self.project, skip=("facts/draft",)),
                         tree_before)

    def test_draft_is_not_loaded_as_live_ledger(self):
        """草稿不吃进事实账（`facts/*.toml` 的 glob 不跨目录）。"""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        (self.reports_dir / "r1.report.toml").write_text(
            REPORT_TOML, encoding="utf-8")
        parsed = self._post_json("/parse", {"name": "r1.report.toml"})
        self._post_json("/confirm", {"name": "r1.report.toml",
                                     "rows": parsed["rows"],
                                     "mapping": {}})
        from factscribe.config import load_config, load_facts
        cfg = load_config(self.disk_path)
        ids = {fact.id for fact in load_facts(cfg)}
        self.assertNotIn("blind_pairs", ids)

    def test_parse_reports_bad_rows(self):
        """坏行要列出来，不能吞。"""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        broken = self.reports_dir / "broken.report.toml"
        broken.write_text(
            '[[metric]]\nid = "ok_one"\nvalue = "1"\n\n'
            '[[metric]]\nclaim = "没有 id"\nvalue = "2"\n', encoding="utf-8")
        parsed = self._post_json("/parse", {"name": "broken.report.toml"})
        self.assertTrue(parsed["ok"])
        self.assertEqual([row["id"] for row in parsed["rows"]], ["ok_one"])
        self.assertTrue(parsed["failed"])
        self.assertIn("id", parsed["failed"][0]["error"])

    def test_parse_json_report(self):
        """json 报告也认。"""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        (self.reports_dir / "r.json").write_text(REPORT_JSON, encoding="utf-8")
        parsed = self._post_json("/parse", {"name": "r.json"})
        self.assertTrue(parsed["ok"])
        self.assertEqual(len(parsed["rows"]), 2)
        self.assertEqual(parsed["rows"][0]["id"], "pairs")

    def test_upload_lands_in_reports_dir(self):
        """上传：multipart 落进报告目录。"""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        data = self._post_multipart("/upload", "up.report.toml",
                                    REPORT_TOML.encode("utf-8"))
        self.assertTrue(data["ok"])
        target = Path(data["path"])
        self.assertTrue(target.is_file())
        self.assertEqual(target.parent, self.reports_dir.resolve())
        self.assertTrue(data["sha256"])
        listing = self._get_json("/dir")
        self.assertIn("up.report.toml",
                      [item["name"] for item in listing["files"]])

    def test_upload_rejects_bad_extension(self):
        """不是 toml / json 的不接受。"""
        try:
            self._post_multipart("/upload", "evil.sh", b"#!/bin/sh\n")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)
            body = json.loads(exc.read().decode("utf-8"))
            self.assertFalse(body["ok"])
            return
        self.fail("应当 400")

    def test_reports_list_shows_pending_card(self):
        """报告页的卡：状态「待核对」、来自导入。"""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        (self.reports_dir / "r1.report.toml").write_text(
            REPORT_TOML, encoding="utf-8")
        parsed = self._post_json("/parse", {"name": "r1.report.toml"})
        self._post_json("/confirm", {"name": "r1.report.toml",
                                     "rows": parsed["rows"],
                                     "mapping": {}})
        data = self._get_json("")
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 1)
        card = data["reports"][0]
        self.assertEqual(card["status"], "pending_check")
        self.assertEqual(card["status_label"], "待核对")
        self.assertEqual(card["from"], "import")
        self.assertEqual(card["bound"], 3)  # 草稿里真有 3 条
        self.assertTrue(card["draft_path"].endswith(".draft.toml"))

    def test_confirm_requires_rows(self):
        """没给 rows → 400，不崩。"""
        try:
            self._post_json("/confirm", {"name": "x.report.toml"})
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)
            return
        self.fail("应当 400")


class TestImporterUnit(unittest.TestCase):
    """解析器本身（不依赖 HTTP）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_parse_toml_rows(self):
        path = self.tmp / "r.toml"
        path.write_text(REPORT_TOML, encoding="utf-8")
        parsed = importer.parse_report(path)
        self.assertEqual(len(parsed["rows"]), 3)
        self.assertEqual(parsed["rows"][1]["claim"], "JUDGE-1 判引导稿胜")
        self.assertEqual(parsed["rows"][1]["source"], "table2")

    def test_parse_missing_file(self):
        with self.assertRaises(importer.ImportError_):
            importer.parse_report(self.tmp / "nope.toml")

    def test_write_draft_path_is_outside_ledger(self):
        disk = self.tmp / "paper"
        (disk / "facts").mkdir(parents=True)
        result = importer.write_draft(disk, "r1.report.toml",
                                      [{"id": "a", "claim": "c", "value": "1"}])
        draft = Path(result["draft_path"])
        self.assertEqual(draft.parent, disk / "facts" / "draft")
        self.assertFalse((disk / "facts" / "r1.report.toml").exists())

    def test_draft_path_strips_suffix(self):
        disk = self.tmp / "paper"
        self.assertEqual(importer.draft_path(disk, "r1.report.toml").name,
                         "r1.report.draft.toml")
        self.assertEqual(importer.draft_path(disk, "r2.json").name,
                         "r2.draft.toml")


if __name__ == "__main__":
    unittest.main()
