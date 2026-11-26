# -*- coding: utf-8 -*-
"""tests/test_workbench_venue.py —— 工作台段六：版式面。

覆盖四组（段六交付自查项 c）：

1. **配置落盘**：目标刊物 ＋ 截稿日期写进项目级 `workbench.toml` 的 `[venue]` 表；
   改一个字，其余行一个字都不动。
2. **截止徽标逻辑**：到期前 7 天内带提醒徽标；过期另说；没填不提醒。
3. **语言锁定**：中文稿不能换成英文刊——改版式不改语言盘（条目 24 口径）。
4. **模板库**：内置 article 占位模板一枚，标注「模板库建设中」。
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench import venue                       # noqa: E402
from factscribe.workbench.server import create_server       # noqa: E402

BS = chr(92)

CONFIG_TOML = """[project]
title = "版式测试"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

MAIN_TEX = """\\documentclass{article}
\\begin{document}
\\input{sections/01-intro}
\\end{document}
"""

INTRO_TEX = """\\section{引言}

开臂解出 10/16\\fact{A1}。
"""


def _make_disk(root: Path, name: str = "paper") -> Path:
    disk = root / name
    (disk / "sections").mkdir(parents=True)
    (disk / "facts").mkdir(parents=True)
    (disk / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (disk / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (disk / "sections" / "01-intro.tex").write_text(INTRO_TEX, encoding="utf-8")
    return disk


class VenueConfigTests(unittest.TestCase):
    """配置读写：落盘 ＋ 不动别的行。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.addCleanup(self._tmp.cleanup)

    def test_save_writes_venue_table(self):
        result = venue.save_venue(self.disk, venue="ACL 2026",
                                   deadline="2026-05-15")
        self.assertTrue(result["ok"])
        self.assertEqual(result["venue"], "ACL 2026")
        self.assertEqual(result["deadline"], "2026-05-15")
        text = (self.disk / "workbench.toml").read_text(encoding="utf-8")
        self.assertIn("[venue]", text)
        self.assertIn('venue = "ACL 2026"', text)
        self.assertIn('deadline = "2026-05-15"', text)

    def test_save_keeps_ai_table(self):
        (self.disk / "workbench.toml").write_text(
            '[ai]\nbase_url = "http://127.0.0.1:9/v1"\nmodel = "qwen"\n',
            encoding="utf-8")
        venue.save_venue(self.disk, venue="ACL 2026", deadline="2026-05-15")
        text = (self.disk / "workbench.toml").read_text(encoding="utf-8")
        self.assertIn("[ai]", text)
        self.assertIn("base_url", text)
        self.assertIn("[venue]", text)

    def test_save_preserves_unrelated_lines(self):
        (self.disk / "workbench.toml").write_text(
            '[ai]\nmodel = "qwen"\n\n# 人的注释，不许动\n', encoding="utf-8")
        venue.save_venue(self.disk, venue="ACL 2026", deadline="2026-05-15")
        text = (self.disk / "workbench.toml").read_text(encoding="utf-8")
        self.assertIn("# 人的注释，不许动", text)

    def test_save_twice_updates_in_place(self):
        venue.save_venue(self.disk, venue="ACL 2026", deadline="2026-05-15")
        venue.save_venue(self.disk, venue="EMNLP 2026", deadline="2026-06-01")
        text = (self.disk / "workbench.toml").read_text(encoding="utf-8")
        self.assertIn('venue = "EMNLP 2026"', text)
        self.assertNotIn('venue = "ACL 2026"', text)
        headers = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("[")]
        self.assertEqual(headers.count("[venue]"), 1)

    def test_save_writes_knowledge_dir_default(self):
        venue.save_venue(self.disk, venue="ACL 2026", deadline="2026-05-15")
        text = (self.disk / "workbench.toml").read_text(encoding="utf-8")
        self.assertIn("[workbench]", text)
        self.assertIn('knowledge_dir = "knowledge"', text)

    def test_invalid_deadline_is_rejected(self):
        with self.assertRaises(venue.VenueError):
            venue.save_venue(self.disk, venue="ACL", deadline="not-a-date")
        self.assertFalse((self.disk / "workbench.toml").exists())

    def test_read_venue_round_trips(self):
        venue.save_venue(self.disk, venue="ACL 2026", deadline="2026-05-15")
        table = venue.read_venue(self.disk)
        self.assertEqual(table["venue"], "ACL 2026")
        self.assertEqual(table["deadline"], "2026-05-15")


class DeadlineBadgeTests(unittest.TestCase):
    """截稿提醒徽标：到期前 7 天内带提醒。"""

    def test_no_deadline_no_badge(self):
        state = venue.deadline_state("")
        self.assertIsNone(state["days_left"])
        self.assertFalse(state["due_soon"])
        self.assertFalse(state["overdue"])

    def test_far_deadline_no_badge(self):
        today = date(2026, 1, 1)
        state = venue.deadline_state("2026-06-01", today=today)
        self.assertEqual(state["days_left"], 151)
        self.assertFalse(state["due_soon"])

    def test_seven_days_left_has_badge(self):
        today = date(2026, 1, 1)
        state = venue.deadline_state("2026-01-08", today=today)
        self.assertEqual(state["days_left"], 7)
        self.assertTrue(state["due_soon"])

    def test_one_day_left_has_badge(self):
        today = date(2026, 1, 1)
        state = venue.deadline_state("2026-01-02", today=today)
        self.assertTrue(state["due_soon"])

    def test_today_deadline_has_badge(self):
        today = date(2026, 1, 1)
        state = venue.deadline_state("2026-01-01", today=today)
        self.assertEqual(state["days_left"], 0)
        self.assertTrue(state["due_soon"])

    def test_eight_days_left_no_badge(self):
        today = date(2026, 1, 1)
        state = venue.deadline_state("2026-01-09", today=today)
        self.assertFalse(state["due_soon"])

    def test_overdue_is_flagged(self):
        today = date(2026, 1, 10)
        state = venue.deadline_state("2026-01-01", today=today)
        self.assertEqual(state["days_left"], -9)
        self.assertTrue(state["overdue"])
        self.assertFalse(state["due_soon"])

    def test_invalid_deadline_is_flagged(self):
        state = venue.deadline_state("乱写")
        self.assertIsNone(state["days_left"])
        self.assertTrue(state.get("invalid"))

    def test_real_today_is_used_by_default(self):
        target = (date.today() + timedelta(days=3)).isoformat()
        state = venue.deadline_state(target)
        self.assertTrue(state["due_soon"])


class LangLockTests(unittest.TestCase):
    """语言锁定：改版式不改语言盘（条目 24 口径）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.addCleanup(self._tmp.cleanup)

    def test_chinese_disk_is_locked(self):
        lock = venue.lang_lock("zh")
        self.assertTrue(lock["locked"])
        self.assertIn("中文稿不能换成英文刊", lock["note"])

    def test_english_disk_is_not_locked(self):
        lock = venue.lang_lock("en")
        self.assertFalse(lock["locked"])
        self.assertIn("语言盘", lock["note"])

    def test_payload_carries_lock(self):
        payload = venue.venue_payload(self.disk, lang="zh")
        self.assertTrue(payload["lang_lock"]["locked"])

    def test_save_does_not_change_language_disk(self):
        venue.save_venue(self.disk, venue="ACL 2026", deadline="2026-05-15",
                         lang="zh")
        # 盘目录名不变（语言盘是身份的一部分）。
        self.assertTrue(self.disk.is_dir())
        self.assertEqual(self.disk.name, "paper")
        text = (self.disk / "workbench.toml").read_text(encoding="utf-8")
        self.assertNotIn("lang", text.replace("language", ""))


class TemplateLibraryTests(unittest.TestCase):
    """模板库：内置 article 占位模板一枚。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.disk = _make_disk(self.root)
        self.addCleanup(self._tmp.cleanup)

    def test_one_builtin_article_template(self):
        payload = venue.venue_payload(self.disk)
        templates = payload["templates"]
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0]["id"], "article")
        self.assertEqual(templates[0]["note"], "模板库建设中")
        self.assertTrue(templates[0]["builtin"])


class VenueEndpointTests(unittest.TestCase):
    """HTTP 全链：读版式 ＋ 存版式。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _make_disk(self.root)
        self.server, self.index = create_server(self.root, port=0, ttl=0.0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=30) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def _post(self, path, body):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_get_returns_defaults(self):
        status, data = self._get("/api/project/paper/venue")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["venue"], "")
        self.assertIsNone(data["days_left"])
        self.assertFalse(data["due_soon"])
        self.assertEqual(data["warn_days"], 7)
        self.assertEqual(len(data["templates"]), 1)

    def test_post_saves_to_workbench_toml(self):
        status, data = self._post("/api/project/paper/venue",
                                  {"venue": "ACL 2026", "deadline": "2026-05-15"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["venue"], "ACL 2026")
        target = self.root / "paper" / "workbench.toml"
        self.assertTrue(target.is_file())
        text = target.read_text(encoding="utf-8")
        self.assertIn("[venue]", text)
        self.assertIn('venue = "ACL 2026"', text)

    def test_post_rejects_bad_deadline(self):
        status, data = self._post("/api/project/paper/venue",
                                  {"venue": "ACL", "deadline": "明天"})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])
        self.assertIn("YYYY-MM-DD", data["error"])

    def test_saved_deadline_drives_badge(self):
        soon = (date.today() + timedelta(days=3)).isoformat()
        status, data = self._post("/api/project/paper/venue",
                                  {"venue": "ACL", "deadline": soon})
        self.assertEqual(status, 200)
        self.assertTrue(data["due_soon"])
        self.assertEqual(data["days_left"], 3)

    def test_unknown_project_is_404(self):
        status, _ = self._get("/api/project/nope/venue")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
