# -*- coding: utf-8 -*-
"""批 133：证据清单的解冻—重冻（全离线）。

规范：``docs/design/SPEC-EVIDENCE-STAMP.md`` §9。

覆盖：

* ``--unfreeze`` 缺 ``--reason`` → 退出码 2，log 不动；
* 正常解冻写一条 append-only 记录（理由、hash_before、at）；
* ``--at`` 只从命令行来，不读系统时钟；同一个 ``--at`` 双跑逐字节一致；
* 解冻后不改直接 freeze → 幂等，不重复写记录；
* 解冻→改→freeze → 哈希更新，audit 转绿；
* 未解冻直接改 → ``EVIDENCE_SET_CHANGED`` 红；
* 解冻状态 audit → ``EVIDENCE_UNFROZEN`` 黄，消息含最近一次理由；
* 无 lock 且无 log → 不检查；
* ``review`` 对解冻状态只给黄，不进拒绝面。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import load_config  # noqa: E402
from factscribe.evidence import LOG_REL, read_lock, read_log  # noqa: E402

BIB_OK = """@inproceedings{chen2023,
  title = {A Paper},
  doi = {10.18653/v1/2023.emnlp-main.741}
}
"""

RAW = "0/12\n11/12\n12/12\n"

FACTS = """[[fact]]
id = "B1"
claim = "第一批盲测的捕获数"
value = "0/12"
source = "results/raw.md"
source_sha256 = "%(sha)s"
locator = "§1"
confidence = "high"
derived_from = []

[[fact]]
id = "B2"
claim = "第七批盲测的捕获数"
value = "11/12"
source = "results/raw.md"
source_sha256 = "%(sha)s"
locator = "§1"
confidence = "high"
derived_from = []

[[fact]]
id = "B3"
claim = "预注册门槛"
value = "12/12"
source = "results/raw.md"
source_sha256 = "%(sha)s"
locator = "§1"
confidence = "high"
derived_from = []
"""

INTRO = r"""\section{Intro}

The argument below cites \cite{chen2023} and names one surface at a time,
keeping each claim next to the receipt that supports it. A short line follows.
The reader can stop at any paragraph and check the source of every number
without reading the rest of the paper.
"""

BODY = r"""\section{Results}

The first sealed set caught nothing, 0/12\fact{B1}, and the seventh caught
11/12\fact{B2}. The two runs share every detector in the implementation.
What differs is what the author had written down before the runs. A short
line follows, and the reader can check each of them against the receipt.
"""


def cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True)


def cli_json(*args: str) -> tuple[subprocess.CompletedProcess, dict]:
    proc = cli(*args, "--json")
    data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return proc, data


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def evidence_block(evidence: dict) -> str:
    lines = ["[evidence]"]
    for key, ids in evidence.items():
        lines.append('"%s" = [%s]'
                     % (key, ", ".join('"%s"' % i for i in ids)))
    return "\n".join(lines)


def rewrite_evidence(root: Path, evidence: dict) -> None:
    cfg_text = (root / "paperkit.toml").read_text(encoding="utf-8")
    head = cfg_text.split("[evidence]")[0].rstrip()
    write(root / "paperkit.toml",
          head + "\n\n" + evidence_block(evidence) + "\n")


def make_project(base: Path, *, evidence: dict | None = None) -> Path:
    """最小 v1 项目：可审计、人签清单齐、正文干净。"""
    root = Path(base)
    raw = root / "results" / "raw.md"
    write(raw, RAW)
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    write(root / "facts" / "f.toml", FACTS % {"sha": digest})
    write(root / "refs.bib", BIB_OK)
    write(root / "results" / "MANIFEST.toml",
          '[manifest]\nsigned_by = "test-human"\n'
          'signed_at = "2026-11-07T00:00:00Z"\nversion = 1\n\n[files]\n'
          '"results/raw.md" = "%s"\n' % digest)
    write(root / "sections" / "01_intro.tex", INTRO)
    write(root / "sections" / "02_body.tex", BODY)
    text = ('[project]\ntitle = "t"\nauthors = ["a"]\n'
            'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
            'bib = "refs.bib"\nbuild = ""\n')
    if evidence is not None:
        text += "\n" + evidence_block(evidence) + "\n"
    write(root / "paperkit.toml", text)
    return root


class UnfreezeCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def project(self, name: str, **kwargs) -> Path:
        return make_project(self.tmp / name, **kwargs)

    def freeze(self, root: Path, *extra: str) -> subprocess.CompletedProcess:
        return cli("evidence", "--freeze", str(root), *extra)

    def unfreeze(self, root: Path, *extra: str) -> subprocess.CompletedProcess:
        return cli("evidence", "--unfreeze", str(root), *extra)

    def log_path(self, root: Path) -> Path:
        return root / LOG_REL

    def records(self, root: Path) -> list[dict]:
        return read_log(root)

    def audit(self, root: Path):
        return cli_json("audit", str(root))

    def code(self, data: dict, code: str) -> list[dict]:
        return [f for f in data.get("findings", [])
                if f.get("code") == code]


# --------------------------------------------------------------------------
# 1. --unfreeze 的硬门槛
# --------------------------------------------------------------------------

class TestUnfreezeArguments(UnfreezeCase):
    def test_missing_reason_exits_2_and_leaves_log_alone(self):
        root = self.project("no-reason", evidence={"02_body": ["B1"]})
        self.assertEqual(self.freeze(root).returncode, 0)
        before = self.log_path(root).read_bytes()
        proc = self.unfreeze(root)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("reason", proc.stderr.lower())
        self.assertEqual(self.log_path(root).read_bytes(), before)

    def test_blank_reason_is_rejected(self):
        root = self.project("blank-reason", evidence={"02_body": ["B1"]})
        self.assertEqual(self.freeze(root).returncode, 0)
        proc = self.unfreeze(root, "--reason", "   ")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("reason", proc.stderr.lower())

    def test_unfreeze_without_freeze_exits_2(self):
        root = self.project("never-frozen", evidence={"02_body": ["B1"]})
        proc = self.unfreeze(root, "--reason", "想改")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("冻结", proc.stderr)

    def test_bad_at_is_rejected(self):
        root = self.project("bad-at", evidence={"02_body": ["B1"]})
        self.assertEqual(self.freeze(root).returncode, 0)
        proc = self.unfreeze(root, "--reason", "想改", "--at", "2026/11/11")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("YYYY-MM-DD", proc.stderr)


# --------------------------------------------------------------------------
# 2. 解冻记录
# --------------------------------------------------------------------------

class TestUnfreezeLog(UnfreezeCase):
    def frozen(self, name: str = "log") -> Path:
        root = self.project(name, evidence={"02_body": ["B1", "B2"]})
        self.assertEqual(self.freeze(root, "--reason", "初始清单").returncode, 0)
        return root

    def test_unfreeze_appends_reason_and_hash_before(self):
        root = self.frozen()
        lock = read_lock(root)
        proc = self.unfreeze(root, "--reason", "补 B9，因新增段落")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        records = self.records(root)
        self.assertEqual([r["action"] for r in records], ["freeze", "unfreeze"])
        last = records[-1]
        self.assertEqual(last["reason"], "补 B9，因新增段落")
        self.assertEqual(last["hash_before"], lock["sha256"][:16])
        self.assertEqual(last["at"], "")

    def test_at_is_recorded_verbatim(self):
        root = self.frozen()
        proc = self.unfreeze(root, "--reason", "补 B9", "--at", "2026-11-11")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.records(root)[-1]["at"], "2026-11-11")

    def test_at_two_runs_are_byte_identical(self):
        first = self.frozen("at-a")
        second = self.frozen("at-b")
        args = ("--reason", "补 B9", "--at", "2026-11-11")
        p1 = self.unfreeze(first, *args)
        p2 = self.unfreeze(second, *args)
        self.assertEqual((p1.returncode, p2.returncode), (0, 0))
        self.assertEqual(self.log_path(first).read_bytes(),
                         self.log_path(second).read_bytes())
        self.assertEqual(p1.stdout, p2.stdout)

    def test_repeated_unfreeze_does_not_duplicate(self):
        root = self.frozen()
        self.assertEqual(self.unfreeze(root, "--reason", "补 B9").returncode, 0)
        self.assertEqual(self.unfreeze(root, "--reason", "补 B9").returncode, 0)
        records = self.records(root)
        self.assertEqual([r["action"] for r in records], ["freeze", "unfreeze"])


# --------------------------------------------------------------------------
# 3. 重冻与幂等
# --------------------------------------------------------------------------

class TestRefreeze(UnfreezeCase):
    def frozen(self, name: str = "refreeze") -> Path:
        root = self.project(name, evidence={"02_body": ["B1", "B2"]})
        self.assertEqual(self.freeze(root, "--reason", "初始清单").returncode, 0)
        return root

    def test_freeze_writes_record_with_hash_entries_reason(self):
        root = self.frozen()
        records = self.records(root)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["action"], "freeze")
        self.assertEqual(rec["hash"], read_lock(root)["sha256"])
        self.assertEqual(rec["entries"], 2)
        self.assertEqual(rec["reason"], "初始清单")

    def test_second_freeze_is_idempotent_and_does_not_duplicate(self):
        root = self.frozen()
        first = self.log_path(root).read_bytes()
        lock = (root / "audit" / "evidence.lock").read_bytes()
        proc = self.freeze(root, "--reason", "再冻一次")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.log_path(root).read_bytes(), first)
        self.assertEqual((root / "audit" / "evidence.lock").read_bytes(), lock)

    def test_freeze_after_unfreeze_without_change_closes_state(self):
        root = self.frozen()
        self.assertEqual(self.unfreeze(root, "--reason", "补 B9").returncode, 0)
        proc = self.freeze(root, "--reason", "重冻")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        records = self.records(root)
        self.assertEqual([r["action"] for r in records],
                         ["freeze", "unfreeze", "freeze"])
        self.assertEqual(records[-1]["reason"], "重冻")
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 0, data)
        self.assertEqual(self.code(data, "EVIDENCE_UNFROZEN"), [])

    def test_edit_after_unfreeze_then_refreeze_updates_hash_and_green(self):
        root = self.frozen()
        old = read_lock(root)["sha256"]
        self.assertEqual(self.unfreeze(root, "--reason", "补 B3").returncode, 0)
        rewrite_evidence(root, {"02_body": ["B1", "B2", "B3"]})
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 1, data)
        self.assertEqual(len(self.code(data, "EVIDENCE_SET_CHANGED")), 1)
        self.assertEqual(self.freeze(root, "--reason", "重冻").returncode, 0)
        new = read_lock(root)["sha256"]
        self.assertNotEqual(old, new)
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 0, data)
        self.assertEqual(self.code(data, "EVIDENCE_SET_CHANGED"), [])
        self.assertEqual(self.code(data, "EVIDENCE_UNFROZEN"), [])


# --------------------------------------------------------------------------
# 4. 未解冻就改 / 解冻状态
# --------------------------------------------------------------------------

class TestAuditStates(UnfreezeCase):
    def frozen(self, name: str = "states") -> Path:
        root = self.project(name, evidence={"02_body": ["B1", "B2"]})
        self.assertEqual(self.freeze(root).returncode, 0)
        return root

    def test_change_without_unfreeze_is_red(self):
        root = self.frozen()
        rewrite_evidence(root, {"02_body": ["B1", "B3"]})
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 1, data)
        hits = self.code(data, "EVIDENCE_SET_CHANGED")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "red")
        self.assertEqual(self.code(data, "EVIDENCE_UNFROZEN"), [])

    def test_unfrozen_state_is_yellow_and_carries_reason(self):
        root = self.frozen()
        self.assertEqual(
            self.unfreeze(root, "--reason", "补 B9，因新增段落").returncode, 0)
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 3, data)
        hits = self.code(data, "EVIDENCE_UNFROZEN")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "yellow")
        self.assertIn("补 B9，因新增段落", hits[0]["message"])

    def test_no_lock_and_no_log_is_not_checked(self):
        root = self.project("nothing", evidence={"02_body": ["B1"]})
        self.assertFalse(self.log_path(root).exists())
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 0, data)
        self.assertEqual(self.code(data, "EVIDENCE_UNFROZEN"), [])
        self.assertEqual(self.code(data, "EVIDENCE_SET_CHANGED"), [])

    def test_review_keeps_unfrozen_yellow_out_of_reject(self):
        before = self.project("review-before", evidence={"02_body": ["B1"]})
        after = self.project("review-after", evidence={"02_body": ["B1"]})
        self.assertEqual(self.freeze(after).returncode, 0)
        self.assertEqual(self.unfreeze(after, "--reason", "补 B9").returncode, 0)
        proc, data = cli_json("review", "--before", str(before),
                              "--after", str(after))
        self.assertEqual(proc.returncode, 0, data)
        self.assertEqual(data["verdict"], "pass")
        self.assertEqual(data["evidence_unfrozen"]["code"],
                         "EVIDENCE_UNFROZEN")
        self.assertIn("补 B9", data["evidence_unfrozen"]["message"])
        self.assertFalse(any("EVIDENCE_UNFROZEN" in r
                             for r in data["reasons"]), data["reasons"])


if __name__ == "__main__":
    unittest.main()
