# -*- coding: utf-8 -*-
"""追加事实表单（两步）与「指定目标账本文件」能力的测试。

这一组钉四件事：

1. **账本目标**（scaffold）：目标文件必须仍在 facts 的 glob 里，且必须是
   glob 目录下的直接子文件（与 load_facts 的读法一致，否则写了读不到）；
   新建文件要沿用本盘既有账本文件的命名风格，前缀不能撞；不指定时行为
   与从前一字不变（默认那本账）。
2. **只读端点**（fact-form）：已签产物 / 未进清单的产物分组、盘内账本
   文件、命名风格、引擎侧说明（notes ＋ 随载荷下发的 i18n 目录）。
3. **提议-确认**：追加事实的提议单只建单不写盘；人点了「采纳写回」才落到
   **所选**的那本账，落盘内容与差异卡上的预览逐字一致。
4. **i18n**：新加的 wb.form.* 文案双语齐、EN 无中文残留。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe import i18n  # noqa: E402
from factscribe.config import ConfigError, load_config  # noqa: E402
from factscribe.scaffold import (add_fact, ledger_naming, prepare_fact,  # noqa: E402
                                 resolve_ledger)
from factscribe.workbench.readings import fact_form  # noqa: E402
from factscribe.workbench.server import create_server  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"

CJK_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")


def make_disk(root: Path, style: str = "letter") -> Path:
    """造一个测试盘：letter＝a_swebench/b_pilot 风格；index＝01-core 风格。"""
    disk = root / "paper"
    shutil.copytree(MINIMAL, disk)
    for path in (disk / "facts").glob("*.toml"):
        path.unlink()
    if style == "letter":
        (disk / "facts" / "a_swebench.toml").write_text(
            '[[fact]]\nid = "A1"\n', encoding="utf-8")
        (disk / "facts" / "b_pilot.toml").write_text(
            '[[fact]]\nid = "B1"\n', encoding="utf-8")
    else:
        (disk / "facts" / "01-core.toml").write_text(
            '[[fact]]\nid = "A1"\n', encoding="utf-8")
    (disk / "results" / "r.md").write_text("10/16", encoding="utf-8")
    (disk / "results" / "MANIFEST.toml").write_text(
        '[manifest]\nsigned_by = "tester"\nsigned_at = "2026-11-23T00:00:00Z"\n'
        'version = 1\n\n[files]\n"results/r.md" = "deadbeef"\n',
        encoding="utf-8")
    return disk


class LedgerTargetTests(unittest.TestCase):
    """核心能力：落哪本账可以指定，但不许越出 facts 的 glob。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-ledger-target-"))
        self.disk = make_disk(self.tmp, "letter")
        self.cfg = load_config(self.disk)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_behaviour_is_unchanged(self):
        """不指定 → 仍走默认那本账（与从前一字不变）。"""
        prepared = prepare_fact(self.disk, fid="Z1", claim="c", value="10/16",
                                 source="results/r.md")
        self.assertEqual(prepared["ledger"], "facts/01-core.toml")
        self.assertFalse(prepared["ledger_explicit"])

    def test_existing_ledger_is_accepted(self):
        prepared = prepare_fact(self.disk, fid="Z1", claim="c", value="10/16",
                                 source="results/r.md",
                                 ledger="facts/b_pilot.toml")
        self.assertEqual(prepared["ledger"], "facts/b_pilot.toml")
        self.assertTrue(prepared["ledger_explicit"])

    def test_new_ledger_follows_the_disk_style(self):
        """新建账本文件：沿用本盘命名风格，且前缀没被占用。"""
        prepared = prepare_fact(self.disk, fid="Z1", claim="c", value="10/16",
                                 source="results/r.md",
                                 ledger="facts/c_third.toml")
        self.assertEqual(prepared["ledger"], "facts/c_third.toml")

    def test_style_mismatch_is_refused(self):
        """01-core 这类与本盘不符的名字要被拒。"""
        with self.assertRaises(ConfigError) as ctx:
            prepare_fact(self.disk, fid="Z1", claim="c", value="10/16",
                         source="results/r.md", ledger="facts/01-core.toml")
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         "LEDGER_STYLE_MISMATCH")

    def test_taken_prefix_is_refused(self):
        with self.assertRaises(ConfigError) as ctx:
            prepare_fact(self.disk, fid="Z1", claim="c", value="10/16",
                         source="results/r.md", ledger="facts/a_other.toml")
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         "LEDGER_PREFIX_TAKEN")

    def test_outside_the_glob_is_refused(self):
        with self.assertRaises(ConfigError) as ctx:
            prepare_fact(self.disk, fid="Z1", claim="c", value="10/16",
                         source="results/r.md", ledger="other/x.toml")
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         "LEDGER_OUTSIDE_GLOB")

    def test_subdirectory_is_refused(self):
        """写到 glob 目录的子目录里就永远读不到——必须直接子文件。"""
        with self.assertRaises(ConfigError) as ctx:
            prepare_fact(self.disk, fid="Z1", claim="c", value="10/16",
                         source="results/r.md", ledger="facts/sub/x.toml")
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         "LEDGER_NOT_IN_GLOB_DIR")

    def test_absolute_and_parent_paths_are_refused(self):
        for ledger in ("/tmp/evil.toml", "../evil.toml"):
            with self.assertRaises(ConfigError) as ctx:
                prepare_fact(self.disk, fid="Z1", claim="c", value="10/16",
                             source="results/r.md", ledger=ledger)
            self.assertEqual(getattr(ctx.exception, "code", ""),
                             "LEDGER_PATH_INVALID")

    def test_add_fact_writes_into_the_chosen_ledger(self):
        info = add_fact(self.disk, fid="Z1", claim="开臂解出", value="10/16",
                        source="results/r.md", locator="二",
                        ledger="facts/b_pilot.toml")
        self.assertEqual(info["ledger"], "facts/b_pilot.toml")
        text = (self.disk / "facts" / "b_pilot.toml").read_text(encoding="utf-8")
        self.assertIn('id = "Z1"', text)
        self.assertNotIn('id = "Z1"', (self.disk / "facts" / "a_swebench.toml")
                         .read_text(encoding="utf-8"))

    def test_naming_is_read_from_the_disk_itself(self):
        naming = ledger_naming(self.disk, self.cfg)
        self.assertEqual(naming["style"], "letter_topic")
        self.assertEqual(naming["next_prefix"], "c")
        self.assertEqual(naming["used_prefixes"], ["a", "b"])

    def test_index_style_disk_has_its_own_naming(self):
        disk = make_disk(self.tmp / "two", "index")
        naming = ledger_naming(disk, load_config(disk))
        self.assertEqual(naming["style"], "index_topic")
        self.assertEqual(naming["next_prefix"], "02")


class FactFormReadingTests(unittest.TestCase):
    """只读读数：挑产物要用的三组料。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-fact-form-"))
        self.disk = make_disk(self.tmp, "letter")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reading_has_the_three_groups(self):
        data = fact_form(self.disk)
        self.assertTrue(data["ok"])
        self.assertTrue(data["manifest_signed"])
        self.assertEqual([row["path"] for row in data["signed"]],
                         ["results/r.md"])
        self.assertTrue(data["signed"][0]["drift"])
        self.assertEqual([row["path"] for row in data["ledgers"]],
                         ["facts/a_swebench.toml", "facts/b_pilot.toml"])
        self.assertEqual(data["ledger_style"], "letter_topic")
        self.assertEqual(data["ledger_next_prefix"], "c")
        self.assertIn("ledger_style_pattern", data)

    def test_reading_ships_the_engine_side_catalog(self):
        data = fact_form(self.disk)
        self.assertTrue(data["notes"])
        for part in data["notes"]:
            self.assertIn(part["key"], data["i18n"])
        self.assertIn("wb.form.fact.err.LEDGER_STYLE_MISMATCH", data["i18n"])

    def test_reading_never_writes(self):
        before = sorted(p.name for p in (self.disk / "facts").iterdir())
        fact_form(self.disk)
        after = sorted(p.name for p in (self.disk / "facts").iterdir())
        self.assertEqual(before, after)


class FactFormEndpointTests(unittest.TestCase):
    """真实 HTTP 路径：端点 + 提议单 + 采纳落所选的账。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-fact-form-endpoint-"))
        self.paper = make_disk(self.tmp, "letter")
        self.state = self.tmp / "state"
        self.server, self.index = create_server(str(self.tmp), port=0,
                                                state_dir=str(self.state))
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        data = self.get("/api/projects")
        project = (data.get("projects") or [])[0]
        disk = (project.get("disks") or [])[0]
        self.project, self.disk = project["id"], disk["id"]
        self.proposal = "/api/disk/%s/%s/proposal" % (self.project, self.disk)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, method="POST",
                                     data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_fact_form_endpoint_returns_the_reading(self):
        data = self.get("/api/disk/%s/%s/fact-form" % (self.project, self.disk))
        self.assertTrue(data["ok"])
        self.assertEqual(data["project"], self.project)
        self.assertEqual(data["disk"], self.disk)
        self.assertEqual(len(data["signed"]), 1)
        self.assertEqual(data["ledger_style"], "letter_topic")
        self.assertIn("i18n", data)

    def test_proposal_only_queues_and_adopt_writes_the_chosen_ledger(self):
        body = {"kind": "add_fact", "source": "page",
                "fact": {"id": "Z9", "claim": "开臂解出", "value": "10/16",
                         "source": "results/r.md", "locator": "二",
                         "ledger": "facts/b_pilot.toml"}}
        record = self.post(self.proposal, body)["proposal"]
        self.assertEqual(record["kind"], "add_fact")
        self.assertEqual(record["fact"]["ledger"], "facts/b_pilot.toml")
        self.assertTrue(record["fact"]["ledger_explicit"])
        # 只建单：账上一个字都没动。
        self.assertNotIn('id = "Z9"',
                         (self.paper / "facts" / "b_pilot.toml").read_text(
                             encoding="utf-8"))
        # 差异卡上的预览就是真正会落盘的那几行。
        self.assertIn("[[fact]]", record["proposed_text"])

        applied = self.post(self.proposal + "/" + record["id"] + "/confirm", {})
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["applied"]["ledger"], "facts/b_pilot.toml")
        text = (self.paper / "facts" / "b_pilot.toml").read_text(encoding="utf-8")
        self.assertIn(record["proposed_text"], text)
        self.assertNotIn('id = "Z9"',
                         (self.paper / "facts" / "a_swebench.toml").read_text(
                             encoding="utf-8"))

    def test_bad_ledger_comes_back_with_a_machine_code(self):
        body = {"kind": "add_fact", "source": "page",
                "fact": {"id": "Z9", "claim": "c", "value": "1",
                         "source": "results/r.md",
                         "ledger": "facts/01-core.toml"}}
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post(self.proposal, body)
        self.assertEqual(ctx.exception.code, 400)
        payload = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(payload.get("err_code"), "LEDGER_STYLE_MISMATCH")

    def test_source_outside_the_disk_is_refused(self):
        """source 的强制校验没被放松：手打一个不存在的路径照样拒。"""
        body = {"kind": "add_fact", "source": "page",
                "fact": {"id": "Z9", "claim": "c", "value": "1",
                         "source": "results/nope.md",
                         "ledger": "facts/b_pilot.toml"}}
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post(self.proposal, body)
        self.assertEqual(ctx.exception.code, 400)


class FactFormI18nTests(unittest.TestCase):
    """新加的引擎侧文案：双语齐、EN 不留中文。"""

    def test_every_form_key_has_both_languages(self):
        keys = [k for k in i18n.WORKBENCH_MESSAGES
                if k.startswith("wb.form.fact.")]
        self.assertTrue(keys)
        for key in keys:
            entry = i18n.WORKBENCH_MESSAGES[key]
            self.assertTrue(entry.get("zh"), key)
            self.assertTrue(entry.get("en"), key)

    def test_english_side_has_no_cjk(self):
        for key in i18n.WORKBENCH_MESSAGES:
            if not key.startswith("wb.form.fact."):
                continue
            self.assertEqual(CJK_RE.findall(
                i18n.WORKBENCH_MESSAGES[key]["en"]), [], key)




class LedgerEntryPointTests(unittest.TestCase):
    """同一项能力在另外两个入口也通：CLI 的 --ledger 与 MCP 的 ledger。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-ledger-entry-"))
        self.disk = make_disk(self.tmp, "letter")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cli_accepts_the_ledger_option(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        proc = subprocess.run(
            [sys.executable, "-m", "factscribe", "fact", "add",
             str(self.disk), "--id", "Z9", "--claim", "开臂解出",
             "--value", "10/16", "--source", "results/r.md",
             "--locator", "二", "--ledger", "facts/b_pilot.toml", "--json"],
            cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["ledger"], "facts/b_pilot.toml")
        text = (self.disk / "facts" / "b_pilot.toml").read_text(encoding="utf-8")
        self.assertIn('id = "Z9"', text)

    def test_mcp_write_path_accepts_the_ledger_field(self):
        from factscribe.workbench_dataplayer import add_fact_data
        info = add_fact_data(self.disk, {
            "id": "Z9", "claim": "开臂解出", "value": "10/16",
            "source": "results/r.md", "locator": "二",
            "ledger": "facts/b_pilot.toml"}, allow_write=True)
        self.assertEqual(info["ledger"], "facts/b_pilot.toml")
        text = (self.disk / "facts" / "b_pilot.toml").read_text(encoding="utf-8")
        self.assertIn('id = "Z9"', text)

if __name__ == "__main__":
    unittest.main()
