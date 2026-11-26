# -*- coding: utf-8 -*-
"""工作台段一：项目发现与聚合、章节渲染、HTTP 端点。"""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from factscribe.workbench import projects as wbp
from factscribe.workbench.server import create_server

TOML = """[project]
title = "%s"
sections = "sections/*.tex"
facts = "facts/*.toml"
bib = "refs.bib"
"""

FACT = """[[fact]]
id = "A1"
claim = "resolve rate"
value = "10/16"
source = "results/runs.md"
source_sha256 = "%s"
locator = "table 1"
confidence = "high"
derived_from = []
""" % ("0" * 64)


def _make_disk(root: Path, name: str, title: str,
               tex: str = "\\section{Intro}\nSome text with 10/16.\n") -> Path:
    disk = root / name
    (disk / "sections").mkdir(parents=True)
    (disk / "facts").mkdir(parents=True)
    (disk / "factscribe.toml").write_text(TOML % title, encoding="utf-8")
    (disk / "sections" / "01_intro.tex").write_text(tex, encoding="utf-8")
    (disk / "facts" / "a.toml").write_text(FACT, encoding="utf-8")
    return disk


class DiscoveryTests(unittest.TestCase):
    def test_finds_disks_under_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_disk(root, "paper", "Paper A")
            _make_disk(root, "nested/deeper/paper-b", "Paper B")
            found = wbp.discover_disks(root)
            names = sorted(p.name for p in found)
            self.assertEqual(names, ["paper", "paper-b"])

    def test_depth_limit_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_disk(root, "a/b/c/d/deep", "Deep")
            found = wbp.discover_disks(root, max_depth=2)
            self.assertEqual([p.name for p in found], [])

    def test_language_and_base_name(self):
        self.assertEqual(wbp.disk_language("paper-zh"), "zh")
        self.assertEqual(wbp.disk_language("paper"), "en")
        self.assertEqual(wbp.disk_language("paper-en"), "en")
        self.assertEqual(wbp.disk_base_name("paper-zh"), "paper")
        self.assertEqual(wbp.disk_base_name("paper-b-zh"), "paper-b")


class AggregationTests(unittest.TestCase):
    def test_two_language_disks_pair_into_one_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_disk(root, "paper", "Paper A")
            _make_disk(root, "paper-zh", "Paper A 中文")
            projects = wbp.load_projects(root)
            self.assertEqual(len(projects), 1)
            project = projects[0]
            self.assertEqual(project["id"], "paper")
            self.assertEqual([d["id"] for d in project["disks"]],
                             ["paper", "paper-zh"])
            self.assertEqual([d["lang"] for d in project["disks"]], ["en", "zh"])
            self.assertEqual(project["name"], "Paper A")

    def test_unpaired_disk_is_its_own_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_disk(root, "solo", "Solo Paper")
            projects = wbp.load_projects(root)
            self.assertEqual(len(projects), 1)
            self.assertEqual(len(projects[0]["disks"]), 1)
            self.assertEqual(projects[0]["disks"][0]["id"], "solo")

    def test_counts_per_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_disk(root, "paper", "Paper A")
            projects = wbp.load_projects(root)
            disk = projects[0]["disks"][0]
            self.assertGreaterEqual(disk["sections"], 1)
            self.assertEqual(disk["facts"], 1)

    def test_two_projects_do_not_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_disk(root, "paper", "Paper A")
            _make_disk(root, "paper-zh", "Paper A 中文")
            _make_disk(root, "paper-b", "Paper B")
            _make_disk(root, "paper-b-zh", "Paper B 中文")
            projects = wbp.load_projects(root)
            self.assertEqual(len(projects), 2)
            ids = sorted(p["id"] for p in projects)
            self.assertEqual(ids, ["paper", "paper-b"])


class RenderTests(unittest.TestCase):
    def test_comment_is_dropped(self):
        blocks = wbp.render_tex("% hidden note\n\\section{A}\nBody text.\n")
        text = " ".join(b.get("html", "") for b in blocks)
        self.assertNotIn("hidden note", text)

    def test_section_becomes_heading(self):
        blocks = wbp.render_tex("\\section{Introduction}\nHello.\n")
        kinds = [b["kind"] for b in blocks]
        self.assertIn("section", kinds)
        head = next(b for b in blocks if b["kind"] == "section")
        self.assertEqual(head["title"], "Introduction")
        self.assertEqual(head["level"], 1)

    def test_paragraph_is_wrapped_and_escaped(self):
        blocks = wbp.render_tex("a < b & c\n")
        para = next(b for b in blocks if b["kind"] == "para")
        self.assertTrue(para["html"].startswith("<p>"))
        self.assertIn("&lt;", para["html"])
        self.assertIn("&amp;", para["html"])

    def test_commands_are_protected_chips(self):
        """条目 43：页面即编辑器——命令不再被「渲染态」剥掉，
        而是带 token 的保护面芯片（与编辑态所见一致）。"""
        blocks = wbp.render_tex("Value \\textbf{bold} and \\label{x:1} end.\n")
        text = " ".join(b.get("html", "") for b in blocks)
        self.assertIn('class="prot-chip"', text)
        self.assertIn("data-token=", text)
        self.assertIn('contenteditable="false"', text)
        self.assertIn("[x:1]", text)           # \\label 以芯片显示，参数可见
        self.assertNotIn("<b>bold</b>", text)  # 不再另出一套排版态

    def test_fact_chip_is_rendered(self):
        """条目 43：事实芯片带保护面身份（fc＋prot-chip＋data-token）。"""
        blocks = wbp.render_tex("Rate 10/16\\fact{A1} here.\n")
        text = " ".join(b.get("html", "") for b in blocks)
        self.assertIn('data-fact="A1"', text)
        self.assertIn('class="fc prot-chip"', text)
        self.assertIn("data-token=", text)
        self.assertIn("✓ A1", text)

    def test_sections_endpoint_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            disk = _make_disk(root, "paper", "Paper A")
            data = wbp.disk_sections(disk, lang="en")
            self.assertIn("blocks", data)
            self.assertEqual(data["count"], len(data["blocks"]))
            self.assertTrue(any(b["kind"] == "section" for b in data["blocks"]))

    def test_meta_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            disk = _make_disk(root, "paper", "Paper A")
            meta = wbp.disk_meta(disk, lang="en")
            self.assertEqual(meta["facts"], 1)
            self.assertGreaterEqual(meta["sections"], 1)
            self.assertIn("last_build", meta)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _make_disk(self.root, "paper", "Paper A")
        _make_disk(self.root, "paper-zh", "Paper A 中文")
        self.server, self.index = create_server(self.root, port=0, ttl=0.0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as res:
            return res.status, res.read().decode("utf-8")

    def test_index_page_is_served(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("<html", body)

    def test_projects_endpoint(self):
        status, body = self._get("/api/projects")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 1)
        project = data["projects"][0]
        self.assertEqual(project["id"], "paper")
        self.assertEqual([d["id"] for d in project["disks"]], ["paper", "paper-zh"])
        self.assertIn("facts", project["disks"][0])
        self.assertIn("sections", project["disks"][0])

    def test_sections_endpoint(self):
        status, body = self._get("/api/disk/paper/paper/sections")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(data["project"], "paper")
        self.assertEqual(data["disk"], "paper")
        self.assertIsInstance(data["blocks"], list)
        self.assertTrue(any(b["kind"] == "section" for b in data["blocks"]))

    def test_meta_endpoint(self):
        status, body = self._get("/api/disk/paper/paper-zh/meta")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(data["facts"], 1)
        self.assertIn("last_build", data)

    def test_unknown_disk_is_404(self):
        try:
            self._get("/api/disk/paper/nope/sections")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)
        else:
            self.fail("未知盘应当 404")

    def test_write_methods_are_rejected(self):
        request = urllib.request.Request(self.base + "/api/projects",
                                         data=b"{}", method="POST")
        try:
            urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 405)
        else:
            self.fail("段一只读：POST 应当 405")


if __name__ == "__main__":
    unittest.main()
