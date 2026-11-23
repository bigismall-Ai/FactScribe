# -*- coding: utf-8 -*-
"""写作简报按 fact id 定位（fs_get_brief 的可选 fact 参数）。

给一个事实 id，简报就多回一条 focus：这条事实绑在哪几节、每节绑没绑、
claim／value／出处各是什么。**只增不改**：不给 fact 时，载荷与从前逐字节
一致（sections／facts／counts 一个字没动）。

跑法（仓根）：python3 -m pytest tests/test_workbench_brief_focus.py -q
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench.readings import brief_reading  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"


class BriefFocusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-brief-focus-"))
        self.disk = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.disk)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_without_a_fact_the_payload_is_unchanged(self):
        plain = brief_reading(self.disk)
        self.assertNotIn("focus", plain)
        self.assertIn("sections", plain)
        self.assertIn("facts", plain)
        self.assertIn("counts", plain)

    def test_a_fact_id_gives_the_binding_map(self):
        data = brief_reading(self.disk, fact="A1")
        focus = data.get("focus") or {}
        self.assertEqual(focus.get("fact"), "A1")
        self.assertTrue(focus.get("found"))
        self.assertTrue(focus.get("sections"))
        self.assertIn("claim", focus)
        self.assertIn("value", focus)

    def test_an_unknown_fact_is_reported_not_guessed(self):
        data = brief_reading(self.disk, fact="NOPE")
        focus = data.get("focus") or {}
        self.assertFalse(focus.get("found"))
        self.assertEqual(focus.get("claim"), "")

    def test_the_rest_of_the_payload_is_still_there(self):
        with_fact = brief_reading(self.disk, fact="A1")
        plain = brief_reading(self.disk)
        self.assertEqual(with_fact.get("facts"), plain.get("facts"))
        self.assertEqual(with_fact.get("counts"), plain.get("counts"))


if __name__ == "__main__":
    unittest.main()
