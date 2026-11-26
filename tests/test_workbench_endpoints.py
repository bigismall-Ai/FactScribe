# -*- coding: utf-8 -*-
"""工作台的新端点（宿主调的那条路）：证据锁／简报／版式／模型声明。

真起工作台 HTTP 服务，走**真实协议路径**断言：

- GET /api/disk/<p>/<d>/evidence   证据锁读数；
- GET /api/disk/<p>/<d>/brief      写作简报读数（可引用／已绑／未绑）；
- GET /api/project/<p>/venue       版式配置；
- GET /api/ai/models               带共用声明 catalog；
- POST …/proposal（kind=evidence_freeze）→ 只建单，不写冻结件；
- POST …/proposal/<id>/confirm     → 人点才写。

跑法（仓根）：python3 -m pytest tests/test_workbench_endpoints.py -q
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.workbench.server import create_server  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"


class WorkbenchEndpointBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-wb-endpoints-"))
        self.paper = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.paper)
        self.state = self.tmp / "state"
        self.server, self.index = create_server(str(self.tmp), port=0,
                                                state_dir=str(self.state))
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.project, self.disk = self._first_disk()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _first_disk(self):
        data = self.get("/api/projects")
        project = (data.get("projects") or [])[0]
        disk = (project.get("disks") or [])[0]
        return project["id"], disk["id"]

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, method="POST", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def disk_path(self, *parts):
        return "/api/disk/%s/%s/%s" % (self.project, self.disk, "/".join(parts))


class ReadingEndpointTests(WorkbenchEndpointBase):
    """只读端点。"""

    def test_evidence_endpoint_returns_the_reading(self):
        data = self.get(self.disk_path("evidence"))
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("project"), self.project)
        self.assertEqual(data.get("disk"), self.disk)
        for key in ("frozen", "entries", "sha256", "mismatch", "unfrozen",
                    "diff", "last_log"):
            self.assertIn(key, data)

    def test_brief_endpoint_returns_the_reading(self):
        data = self.get(self.disk_path("brief"))
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("sections"))
        self.assertTrue(data.get("facts"))
        for row in data["sections"]:
            self.assertIn("usable", row)
            self.assertIn("bound", row)
            self.assertIn("unbound", row)

    def test_brief_endpoint_honours_the_section_filter(self):
        data = self.get(self.disk_path("brief") + "?section=01")
        self.assertEqual(data.get("section"), "01")
        for row in data.get("sections") or []:
            self.assertIn("01", str(row.get("file")))

    def test_venue_endpoint_returns_the_reading(self):
        data = self.get("/api/project/%s/venue" % self.project)
        self.assertTrue(data.get("ok"))
        for key in ("venue", "deadline", "days_left", "lang_lock", "templates"):
            self.assertIn(key, data)

    def test_models_endpoint_carries_the_shared_catalog(self):
        data = self.get("/api/ai/models?project=%s&disk=%s"
                        % (self.project, self.disk))
        self.assertTrue(data.get("ok"))
        catalog = data.get("catalog")
        self.assertIsInstance(catalog, dict, "模型档位共用声明没给回")
        self.assertTrue(catalog.get("models"))
        for entry in catalog["models"]:
            for key in ("id", "kind", "label", "model", "efforts",
                        "defaultEffort"):
                self.assertIn(key, entry)
        # 旧字段一个字都不许少。
        self.assertIn("models", data)
        self.assertIn("model", data)


class ProposalEndpointTests(WorkbenchEndpointBase):
    """提议单端点：只建单 → 人点才写。"""

    def test_create_proposal_does_not_write_the_lock(self):
        data = self.post(self.disk_path("proposal"),
                         {"kind": "evidence_freeze", "reason": "留底"})
        proposal = data.get("proposal") or {}
        self.assertEqual(proposal.get("kind"), "evidence_freeze")
        self.assertTrue(proposal.get("id"))
        self.assertFalse((self.paper / "audit" / "evidence.lock").exists(),
                         "建单不许写冻结件")

    def test_confirm_applies_the_proposal(self):
        data = self.post(self.disk_path("proposal"),
                         {"kind": "evidence_freeze", "reason": "留底"})
        pid = (data.get("proposal") or {}).get("id")
        self.assertTrue(pid)
        result = self.post(self.disk_path("proposal", pid, "confirm"), {})
        self.assertTrue(result.get("ok"))
        self.assertTrue((self.paper / "audit" / "evidence.lock").is_file())

    def test_list_proposals_shows_the_pending_card(self):
        self.post(self.disk_path("proposal"),
                  {"kind": "evidence_freeze", "reason": "留底"})
        data = self.get(self.disk_path("proposal"))
        self.assertEqual(data.get("count"), 1)
        row = (data.get("proposals") or [])[0]
        self.assertEqual(row.get("kind"), "evidence_freeze")
        self.assertTrue(row.get("before_text"))
        self.assertTrue(row.get("after_text"))


if __name__ == "__main__":
    unittest.main()
