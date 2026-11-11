# -*- coding: utf-8 -*-
"""批 132：证据清单可由 LLM 产出，但由机器冻结（全离线）。

规范：``docs/design/SPEC-EVIDENCE-STAMP.md`` §8。

覆盖：

* ``evidence --suggest`` 的输出可被 TOML 解析，且与正文 ``\\fact{}`` 引用一致；
* 节内 id 按首次出现顺序、去重；同输入两跑逐字节一致；
* ``--json`` 结构稳定；
* ``--suggest`` 的 stdout 只有 TOML（可直接重定向、直接粘配置），摘要走掉；
* ``--suggest`` 的 stdout 可被 ``tomllib`` 直接解析，且不含中文摘要；
* 摘要出现在 stderr；``--json`` 的 stdout 是纯 JSON 且带统计字段；
* stdout 直接追加到 ``paperkit.toml`` 后 ``--freeze`` 仍 exit 0（批 134 回归）。
* ``evidence --freeze`` 写 ``audit/evidence.lock``：哈希与 entries；
* 双跑同哈希；键序/重复 id 不同但规范化相同 → 同哈希；
* 改一个 id / 加一节 / 挪一条 / 删一条 → ``EVIDENCE_SET_CHANGED`` 红，
  消息指出新增、删除、移动的具体 id；
* 删掉 lock → 不检查；
* 旧式两行 lock（无 ``[sections]``）仍判红；
* ``review`` 把清单被改算进拒绝面；
* ``brief`` 直接取 ``[evidence]``，没有则用 suggest 结果并标「未冻结」。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:  # 3.11+；3.10 没有 tomllib，退回工具自己的解析器
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10
    tomllib = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.brief import build_brief, render as render_brief  # noqa: E402
from factscribe.config import (load_config, load_sections,  # noqa: E402
                               load_toml)
from factscribe.evidence import (canonical_sha256,  # noqa: E402
                                 read_lock, suggest_evidence)

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

EXTRA = r"""\section{Limits}

The pre-registered threshold was 12/12\fact{B3}. A short line follows, and
the reader can check the receipt without reading the rest of the paper.
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


def parse_toml(text: str, base: Path) -> dict:
    """3.10 没有 tomllib：借工具自己的 load_toml 解析（同一口径）。"""
    path = Path(base) / "_parse.toml"
    write(path, text)
    return load_toml(path)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def evidence_block(evidence: dict) -> str:
    lines = ["[evidence]"]
    for key, ids in evidence.items():
        lines.append('"%s" = [%s]' % (key, ", ".join('"%s"' % i for i in ids)))
    return "\n".join(lines)


def make_project(base: Path, *, evidence: dict | None = None,
                 sections: dict | None = None) -> Path:
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
    for rel, body in (sections or {
            "sections/01_intro.tex": INTRO,
            "sections/02_body.tex": BODY}).items():
        write(root / rel, body)
    text = ('[project]\ntitle = "t"\nauthors = ["a"]\n'
            'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
            'bib = "refs.bib"\nbuild = ""\n')
    if evidence is not None:
        text += "\n" + evidence_block(evidence) + "\n"
    write(root / "paperkit.toml", text)
    return root


class FreezeCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def project(self, name: str, **kwargs) -> Path:
        return make_project(self.tmp / name, **kwargs)

    def suggest(self, root: Path) -> dict:
        cfg = load_config(root)
        return suggest_evidence(load_sections(cfg))

    def lock_path(self, root: Path) -> Path:
        return root / "audit" / "evidence.lock"

    def freeze(self, root: Path) -> subprocess.CompletedProcess:
        return cli("evidence", "--freeze", str(root))

    def audit(self, root: Path):
        return cli_json("audit", str(root))


# --------------------------------------------------------------------------
# 1. suggest
# --------------------------------------------------------------------------

class TestSuggest(FreezeCase):
    def test_output_parses_and_matches_body(self):
        root = self.project("suggest")
        proc = cli("evidence", "--suggest", str(root))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        block = parse_toml(proc.stdout, self.tmp)
        self.assertEqual(block["evidence"]["02_body"], ["B1", "B2"])
        self.assertNotIn("01_intro", block["evidence"])
        direct = self.suggest(root)
        self.assertEqual(direct["02_body"], ["B1", "B2"])

    def test_ids_follow_first_appearance_and_dedup(self):
        body = BODY + "\nThe same 0/12\\fact{B1} is cited again here.\n"
        root = self.project("order", sections={
            "sections/01_intro.tex": INTRO,
            "sections/02_body.tex": body})
        block = parse_toml(cli("evidence", "--suggest", str(root)).stdout,
                           self.tmp)
        self.assertEqual(block["evidence"]["02_body"], ["B1", "B2"])

    def test_two_runs_are_byte_identical(self):
        root = self.project("deterministic")
        first = cli("evidence", "--suggest", str(root))
        second = cli("evidence", "--suggest", str(root))
        self.assertEqual(first.stdout, second.stdout)

    def test_json_shape_is_stable(self):
        root = self.project("json")
        proc, data = cli_json("evidence", "--suggest", str(root))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["command"], "evidence")
        self.assertEqual(data["action"], "suggest")
        self.assertEqual([row["section"] for row in data["sections"]],
                         ["02_body"])
        self.assertEqual(data["sections"][0]["ids"], ["B1", "B2"])
        self.assertEqual(parse_toml(data["toml"], self.tmp)["evidence"],
                         {"02_body": ["B1", "B2"]})
        self.assertNotIn(str(root), json.dumps(data, ensure_ascii=False))

    def test_no_facts_yields_empty_parseable_block(self):
        root = self.project("empty", sections={
            "sections/01_intro.tex": INTRO})
        proc = cli("evidence", "--suggest", str(root))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(parse_toml(proc.stdout, self.tmp), {"evidence": {}})


# --------------------------------------------------------------------------
# 1b. 批 134：suggest 的输出流契约（stdout 只有 TOML，摘要不进 stdout）
# --------------------------------------------------------------------------

class TestSuggestStreams(FreezeCase):
    """实测缺陷回归：摘要混进 stdout 会让 TOML 解析失败、后续命令 exit 2。"""

    def run_suggest(self, root: Path, *extra: str):
        return cli("evidence", "--suggest", str(root), *extra)

    def test_stdout_parses_as_toml_without_preprocessing(self):
        root = self.project("streams-pure")
        proc = self.run_suggest(root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        if tomllib is not None:
            block = tomllib.loads(proc.stdout)
        else:  # pragma: no cover - 3.10
            block = parse_toml(proc.stdout, self.tmp)
        self.assertEqual(block["evidence"]["02_body"], ["B1", "B2"])

    def test_stdout_carries_no_chinese_summary(self):
        root = self.project("streams-no-cn")
        proc = self.run_suggest(root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.startswith("[evidence]\n"), proc.stdout[:40])
        self.assertIsNone(re.search(r"[\u4e00-\u9fff]", proc.stdout),
                          proc.stdout[:200])

    def test_summary_goes_to_stderr(self):
        root = self.project("streams-stderr")
        proc = self.run_suggest(root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("扫描", proc.stderr)
        self.assertIn("共 2 条 id", proc.stderr)
        self.assertNotIn("扫描", proc.stdout)

    def test_json_stdout_is_pure_json_with_stats(self):
        root = self.project("streams-json")
        proc = self.run_suggest(root, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        data = json.loads(proc.stdout)
        self.assertEqual(data["scanned"], 2)
        self.assertEqual(data["sections_with_facts"], 1)
        self.assertEqual(data["facts"], 2)
        self.assertIn("共 2 条 id", data["summary"])
        self.assertIn("未冻结", data["summary"])
        self.assertEqual(parse_toml(data["toml"], self.tmp)["evidence"],
                         {"02_body": ["B1", "B2"]})

    def test_appended_stdout_is_accepted_by_freeze(self):
        """验收形态：重定向 → 追加配置 → freeze，必须 exit 0。"""
        root = self.project("streams-append")
        proc = self.run_suggest(root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        cfg_path = root / "paperkit.toml"
        write(cfg_path,
              cfg_path.read_text(encoding="utf-8") + proc.stdout)
        frozen = self.freeze(root)
        self.assertEqual(frozen.returncode, 0, frozen.stderr)
        self.assertEqual(read_lock(root)["entries"], 2)


# --------------------------------------------------------------------------
# 2. freeze
# --------------------------------------------------------------------------

class TestFreeze(FreezeCase):
    def test_writes_sha_entries_and_sections(self):
        root = self.project("freeze", evidence={
            "01_intro": ["B1"], "02_body": ["B1", "B2"]})
        proc = self.freeze(root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lock = read_lock(root)
        self.assertIsNotNone(lock)
        self.assertEqual(lock["entries"], 3)
        cfg = load_config(root)
        self.assertEqual(lock["sha256"], canonical_sha256(cfg.evidence_sections))
        data = load_toml(self.lock_path(root))
        self.assertEqual(data["sections"]["02_body"], ["B1", "B2"])

    def test_two_freezes_are_byte_identical(self):
        root = self.project("freeze-twice", evidence={"02_body": ["B2", "B1"]})
        self.assertEqual(self.freeze(root).returncode, 0)
        first = self.lock_path(root).read_bytes()
        self.assertEqual(self.freeze(root).returncode, 0)
        self.assertEqual(self.lock_path(root).read_bytes(), first)

    def test_normalization_makes_order_and_duplicates_irrelevant(self):
        a = self.project("norm-a", evidence={"02_body": ["B2", "B1"]})
        b = self.project("norm-b", evidence={"02_body": ["B1", "B2", "B1"]})
        self.assertEqual(self.freeze(a).returncode, 0)
        self.assertEqual(self.freeze(b).returncode, 0)
        self.assertEqual(read_lock(a)["sha256"], read_lock(b)["sha256"])

    def test_freeze_without_evidence_is_stable(self):
        root = self.project("freeze-none")
        proc = self.freeze(root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(read_lock(root)["entries"], 0)
        self.assertEqual(read_lock(root)["sections"], {})

    def test_json_reports_path_sha_and_entries(self):
        root = self.project("freeze-json", evidence={"02_body": ["B1"]})
        proc, data = cli_json("evidence", "--freeze", str(root))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["action"], "freeze")
        self.assertEqual(data["entries"], 1)
        self.assertEqual(data["path"], "audit/evidence.lock")
        self.assertEqual(len(data["sha256"]), 64)


# --------------------------------------------------------------------------
# 3. 冻结后的检查
# --------------------------------------------------------------------------

class TestLockCheck(FreezeCase):
    def frozen(self, name: str, evidence: dict) -> Path:
        root = self.project(name, evidence=evidence)
        self.assertEqual(self.freeze(root).returncode, 0)
        return root

    def rewrite_evidence(self, root: Path, evidence: dict) -> None:
        cfg_text = (root / "paperkit.toml").read_text(encoding="utf-8")
        head = cfg_text.split("[evidence]")[0].rstrip()
        write(root / "paperkit.toml",
              head + "\n\n" + evidence_block(evidence) + "\n")

    def lock_code(self, data: dict) -> list:
        return [f for f in data["findings"]
                if f["code"] == "EVIDENCE_SET_CHANGED"]

    def test_unchanged_set_is_green(self):
        root = self.frozen("green", {"02_body": ["B1", "B2"]})
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 0, data)
        self.assertEqual(self.lock_code(data), [])

    def test_change_one_id_is_red_and_names_it(self):
        root = self.frozen("changed", {"02_body": ["B1", "B2"]})
        self.rewrite_evidence(root, {"02_body": ["B1", "B3"]})
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 1, data)
        hits = self.lock_code(data)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "red")
        self.assertIn("B3", hits[0]["message"])
        self.assertIn("B2", hits[0]["message"])

    def test_missing_lock_is_not_checked(self):
        root = self.project("no-lock", evidence={"02_body": ["B1"]})
        self.assertFalse(self.lock_path(root).exists())
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 0, data)
        self.assertEqual(self.lock_code(data), [])

    def test_adding_a_section_changes_hash(self):
        root = self.frozen("added-section", {"02_body": ["B1"]})
        self.rewrite_evidence(root, {"02_body": ["B1"], "01_intro": ["B1"]})
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 1, data)
        self.assertIn("01_intro", self.lock_code(data)[0]["message"])

    def test_moving_an_id_between_sections_is_reported(self):
        root = self.frozen("moved", {"01_intro": ["B1"], "02_body": ["B2"]})
        self.rewrite_evidence(root, {"01_intro": ["B2"], "02_body": ["B1"]})
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 1, data)
        message = self.lock_code(data)[0]["message"]
        self.assertIn("移动", message)
        self.assertIn("B1", message)
        self.assertIn("B2", message)

    def test_removing_an_id_is_reported(self):
        root = self.frozen("removed", {"02_body": ["B1", "B2"]})
        self.rewrite_evidence(root, {"02_body": ["B1"]})
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 1, data)
        message = self.lock_code(data)[0]["message"]
        self.assertIn("删除", message)
        self.assertIn("B2", message)

    def test_legacy_two_line_lock_still_red(self):
        root = self.project("legacy", evidence={"02_body": ["B1"]})
        write(self.lock_path(root),
              '# 冻结时间由使用者填写（不用系统时钟，保持确定性）\n'
              'canonical_sha256 = "%s"\nentries = 1\n'
              % ("0" * 64))
        proc, data = self.audit(root)
        self.assertEqual(proc.returncode, 1, data)
        message = self.lock_code(data)[0]["message"]
        self.assertIn("哈希", message)

    def test_review_rejects_on_changed_set(self):
        before = self.project("review-before", evidence={"02_body": ["B1"]})
        after = self.frozen("review-after", {"02_body": ["B1"]})
        self.rewrite_evidence(after, {"02_body": ["B2"]})
        proc, data = cli_json("review", "--before", str(before),
                              "--after", str(after))
        self.assertEqual(proc.returncode, 1, data)
        self.assertEqual(data["verdict"], "reject")
        self.assertTrue(any("EVIDENCE_SET_CHANGED" in r
                            for r in data["reasons"]), data["reasons"])


# --------------------------------------------------------------------------
# 4. brief 同步
# --------------------------------------------------------------------------

class TestBriefSync(FreezeCase):
    def test_brief_uses_declared_evidence(self):
        root = self.project("brief-declared",
                            evidence={"02_body": ["B1", "B2"]})
        text = render_brief(build_brief(root))
        row = next(line for line in text.splitlines() if "02_body.tex" in line)
        self.assertIn("B1", row)
        self.assertIn("B2", row)
        self.assertNotIn("未冻结", row)

    def test_brief_falls_back_to_suggestion_and_marks_unfrozen(self):
        root = self.project("brief-suggest")
        text = render_brief(build_brief(root))
        row = next(line for line in text.splitlines() if "02_body.tex" in line)
        self.assertIn("B1", row)
        self.assertIn("B2", row)
        self.assertIn("未冻结", row)


if __name__ == "__main__":
    unittest.main()
