# -*- coding: utf-8 -*-
"""批 106：`tide` 的快照与回滚（全离线）。

规范：`docs/design/SPEC-TIDE.md` §12。

要证的只有四件事：

- **存→复原逐字节一致**（文本 / 空文件 / 二进制 / 嵌套目录）；
- **内容寻址去重**（同内容只落一份 blob）；
- **快照ID 确定性**（同一目录连存两次，ID 与清单字节都不变）；
- **失败关闭**（blob 被改、blob 缺失、清单被改 → 一个字节也不写）。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MANIFEST = "manifest.tsv"


def make_tree(root: Path, files: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes)
                      else data.encode("utf-8"))
    return root


def tree_bytes(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(args, cwd=None, **kw):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", *args]
    return subprocess.run(cmd, cwd=str(cwd or ROOT), env=env,
                          capture_output=True, text=True, **kw)


def parse_manifest(path: Path) -> list[tuple[str, str, int]]:
    raw = path.read_text(encoding="utf-8")
    rows = []
    for line in raw.splitlines():
        rel, digest, size = line.split("\t")
        rows.append((rel, digest, int(size)))
    return rows


class SnapshotCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tide-snap-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = self.tmp / "after"
        self.store = self.tmp / "store"

    def save(self, *extra: str):
        return run(["tide", "--after", str(self.src),
                    "--snapshot", str(self.store), *extra])

    def restore(self, snap_id, into: Path, *extra: str):
        return run(["tide", "--restore", snap_id, "--into", str(into),
                    "--snapshot", str(self.store), *extra])

    def snapshot_id(self) -> str:
        dirs = sorted((self.store / "snapshots").iterdir())
        self.assertEqual(len(dirs), 1)
        return dirs[0].name


class TestSave(SnapshotCase):
    def test_manifest_sorted_and_hashed(self) -> None:
        make_tree(self.src, {"b.txt": "bbb", "a.txt": "aaa",
                             "sub/c.tex": "ccc"})
        proc = self.save()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        sid = self.snapshot_id()
        manifest = self.store / "snapshots" / sid / MANIFEST
        rows = parse_manifest(manifest)
        self.assertEqual([r[0] for r in rows],
                         ["a.txt", "b.txt", "sub/c.tex"])
        for rel, digest, size in rows:
            data = (self.src / rel).read_bytes()
            self.assertEqual(digest, sha256_bytes(data))
            self.assertEqual(size, len(data))
        # 快照ID ＝ 清单内容字节的全宽 sha256
        raw = manifest.read_bytes()
        self.assertEqual(sid, sha256_bytes(raw))
        self.assertEqual(len(sid), 64)

    def test_human_shows_short_id_and_counts(self) -> None:
        make_tree(self.src, {"a.txt": "aaa", "b.txt": "bbbb"})
        proc = self.save()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        sid = self.snapshot_id()
        self.assertIn(sid[:16], proc.stdout)
        self.assertIn("文件：2", proc.stdout)
        self.assertNotIn(str(self.tmp), proc.stdout)  # 无绝对路径

    def test_blob_layout_content_addressed(self) -> None:
        make_tree(self.src, {"x/one.txt": "same", "y/two.txt": "same",
                             "z.txt": "other"})
        proc = self.save()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        blobs = sorted((self.store / "blobs").iterdir())
        self.assertEqual(len(blobs), 2)  # same 只落一份
        for blob in blobs:
            self.assertEqual(blob.name, sha256_bytes(blob.read_bytes()))


class TestRoundTrip(SnapshotCase):
    def test_roundtrip_byte_identical(self) -> None:
        binary = bytes(range(256)) * 3
        make_tree(self.src, {
            "main.tex": "\\section{A}\n中文内容\n",
            "chapters/a.tex": "",
            "chapters/data.bin": binary,
            "deep/x/y/z.txt": "tail",
        })
        proc = self.save()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        into = self.tmp / "restored"
        out = self.restore(self.snapshot_id(), into)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(tree_bytes(into), tree_bytes(self.src))

    def test_roundtrip_empty_file(self) -> None:
        make_tree(self.src, {"empty.txt": b""})
        self.assertEqual(self.save().returncode, 0)
        rows = parse_manifest(self.store / "snapshots" / self.snapshot_id()
                              / MANIFEST)
        self.assertEqual(rows, [("empty.txt",
                                 "e3b0c44298fc1c149afbf4c8996fb924"
                                 "27ae41e4649b934ca495991b7852b855", 0)])
        into = self.tmp / "restored"
        self.assertEqual(self.restore(self.snapshot_id(), into).returncode, 0)
        self.assertEqual((into / "empty.txt").read_bytes(), b"")

    def test_roundtrip_binary(self) -> None:
        binary = bytes([0x00, 0xFF, 0x0A, 0x0D, 0x09, 0x80, 0x7F]) * 1000
        make_tree(self.src, {"paper.pdf": binary})
        self.assertEqual(self.save().returncode, 0)
        into = self.tmp / "restored"
        proc = self.restore(self.snapshot_id(), into)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((into / "paper.pdf").read_bytes(), binary)


class TestDedupe(SnapshotCase):
    def test_two_identical_files_share_one_blob(self) -> None:
        make_tree(self.src, {"a.txt": "duplicate", "b.txt": "duplicate",
                             "c.txt": "unique"})
        proc = self.save()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = parse_manifest(self.store / "snapshots" / self.snapshot_id()
                              / MANIFEST)
        by_rel = {rel: digest for rel, digest, _size in rows}
        self.assertEqual(by_rel["a.txt"], by_rel["b.txt"])
        self.assertEqual(len(list((self.store / "blobs").iterdir())), 2)

    def test_second_save_reuses_blobs(self) -> None:
        make_tree(self.src, {"a.txt": "aaa", "b.txt": "bbb"})
        self.assertEqual(self.save().returncode, 0)
        first = {p.name for p in (self.store / "blobs").iterdir()}
        proc = self.save("--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["blobs_new"], 0)
        self.assertEqual(payload["blobs_shared"], 2)
        self.assertEqual({p.name for p in (self.store / "blobs").iterdir()},
                         first)


class TestDeterminism(SnapshotCase):
    def test_same_tree_same_id_and_manifest_bytes(self) -> None:
        make_tree(self.src, {"a.txt": "aaa", "b/c.tex": "ccc"})
        self.assertEqual(self.save().returncode, 0)
        sid1 = self.snapshot_id()
        manifest1 = (self.store / "snapshots" / sid1 / MANIFEST).read_bytes()
        self.assertEqual(self.save().returncode, 0)
        self.assertEqual(self.snapshot_id(), sid1)
        self.assertEqual((self.store / "snapshots" / sid1 / MANIFEST)
                         .read_bytes(), manifest1)

    def test_id_matches_recomputed_manifest_hash(self) -> None:
        make_tree(self.src, {"a.txt": "aaa"})
        self.assertEqual(self.save().returncode, 0)
        sid = self.snapshot_id()
        raw = (self.store / "snapshots" / sid / MANIFEST).read_bytes()
        self.assertEqual(sha256_bytes(raw), sid)
        self.assertNotIn(b"/", raw.replace(b"a.txt", b""))  # 无绝对路径


class TestIgnore(SnapshotCase):
    def test_build_products_not_in_manifest(self) -> None:
        make_tree(self.src, {"main.tex": "x", "main.aux": "aux",
                             "main.log": "log", "main.synctex.gz": "gz"})
        proc = self.save("--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        rows = parse_manifest(self.store / "snapshots" / self.snapshot_id()
                              / MANIFEST)
        self.assertEqual([r[0] for r in rows], ["main.tex"])
        self.assertEqual(payload["files"], 1)
        blobs = {p.name for p in (self.store / "blobs").iterdir()}
        self.assertEqual(blobs, {sha256_bytes(b"x")})

    def test_extra_ignore_glob(self) -> None:
        make_tree(self.src, {"main.tex": "x", "draft.pdf": "pdf"})
        self.assertEqual(self.save("--ignore", "*.pdf").returncode, 0)
        rows = parse_manifest(self.store / "snapshots" / self.snapshot_id()
                              / MANIFEST)
        self.assertEqual([r[0] for r in rows], ["main.tex"])

    def test_default_store_is_dot_tide(self) -> None:
        make_tree(self.src, {"a.txt": "aaa"})
        proc = run(["tide", "--after", str(self.src)], cwd=self.tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        snaps = sorted((self.tmp / ".tide" / "snapshots").iterdir())
        self.assertEqual(len(snaps), 1)
        into = self.tmp / "restored"
        out = run(["tide", "--restore", snaps[0].name[:16],
                   "--into", str(into)], cwd=self.tmp)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual((into / "a.txt").read_bytes(), b"aaa")

    def test_store_inside_source_not_ingested(self) -> None:
        make_tree(self.src, {"a.txt": "aaa"})
        self.store = self.src / "snapstore"   # 非隐藏、在源目录内
        self.assertEqual(self.save().returncode, 0)
        rows = parse_manifest(self.store / "snapshots" / self.snapshot_id()
                              / MANIFEST)
        self.assertEqual([r[0] for r in rows], ["a.txt"])


class TestJson(SnapshotCase):
    def test_save_json_has_id_and_file_count(self) -> None:
        make_tree(self.src, {"a.txt": "aaa", "b.txt": "bb", "c.txt": "c"})
        proc = self.save("--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        sid = self.snapshot_id()
        self.assertEqual(payload["mode"], "snapshot")
        self.assertEqual(payload["snapshot_id"], sid)
        self.assertEqual(payload["snapshot"], sid[:16])
        self.assertEqual(payload["files"], 3)
        self.assertEqual(payload["bytes"], 6)
        self.assertTrue(payload["ok"])

    def test_restore_json_reports_ok(self) -> None:
        make_tree(self.src, {"a.txt": "aaa"})
        self.assertEqual(self.save().returncode, 0)
        into = self.tmp / "restored"
        proc = self.restore(self.snapshot_id(), into, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["mode"], "restore")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["files"], 1)
        self.assertEqual(payload["verified"], 1)
        self.assertEqual(payload["snapshot"], self.snapshot_id()[:16])


class TestFailClosed(SnapshotCase):
    def _first_blob(self) -> Path:
        rows = parse_manifest(self.store / "snapshots" / self.snapshot_id()
                              / MANIFEST)
        return self.store / "blobs" / rows[0][1]

    def test_tampered_blob_fails_closed(self) -> None:
        make_tree(self.src, {"a.txt": "aaaa", "b.txt": "bbbb"})
        self.assertEqual(self.save().returncode, 0)
        blob = self._first_blob()
        original = blob.read_bytes()
        blob.write_bytes(bytes([original[0] ^ 0xFF]) + original[1:])
        into = self.tmp / "restored"
        proc = self.restore(self.snapshot_id(), into, "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["reasons"])
        self.assertFalse(into.exists() and any(into.rglob("*")))

    def test_missing_blob_fails_closed(self) -> None:
        make_tree(self.src, {"a.txt": "aaaa"})
        self.assertEqual(self.save().returncode, 0)
        self._first_blob().unlink()
        into = self.tmp / "restored"
        proc = self.restore(self.snapshot_id(), into, "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertFalse(json.loads(proc.stdout)["ok"])
        self.assertFalse(into.exists() and any(into.rglob("*")))

    def test_tampered_manifest_hash_mismatch_fails_closed(self) -> None:
        make_tree(self.src, {"a.txt": "aaaa"})
        self.assertEqual(self.save().returncode, 0)
        snappath = self.store / "snapshots" / self.snapshot_id()
        manifest = snappath / MANIFEST
        manifest.write_bytes(manifest.read_bytes() + b"evil.txt\tx\t0\n")
        into = self.tmp / "restored"
        proc = self.restore(snappath.name, into, "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertFalse(into.exists() and any(into.rglob("*")))

    def test_manifest_size_mismatch_fails_closed(self) -> None:
        make_tree(self.src, {"a.txt": "aaaa"})
        self.assertEqual(self.save().returncode, 0)
        old = self.store / "snapshots" / self.snapshot_id()
        old_manifest = (old / MANIFEST).read_bytes()
        rel, digest, size = parse_manifest(old / MANIFEST)[0]
        forged = ("%s\t%s\t%d\n" % (rel, digest, size + 3)).encode("utf-8")
        new_id = sha256_bytes(forged)
        new = old.parent / new_id
        new.mkdir()
        (new / MANIFEST).write_bytes(forged)
        shutil.rmtree(old)
        into = self.tmp / "restored"
        proc = self.restore(new_id, into, "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("长度", " ".join(json.loads(proc.stdout)["reasons"]))
        self.assertFalse(into.exists() and any(into.rglob("*")))
        self.assertTrue(old_manifest)  # 原清单只用于对照，未被改写


class TestRestoreMode(SnapshotCase):
    def test_restore_by_short_id(self) -> None:
        make_tree(self.src, {"a.txt": "aaa"})
        self.assertEqual(self.save().returncode, 0)
        sid = self.snapshot_id()
        into = self.tmp / "restored"
        proc = self.restore(sid[:16], into)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((into / "a.txt").read_bytes(), b"aaa")

    def test_restore_keeps_unrelated_files(self) -> None:
        make_tree(self.src, {"a.txt": "new"})
        self.assertEqual(self.save().returncode, 0)
        into = self.tmp / "restored"
        make_tree(into, {"keep.md": "keep", "a.txt": "old"})
        proc = self.restore(self.snapshot_id(), into)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((into / "keep.md").read_bytes(), b"keep")
        self.assertEqual((into / "a.txt").read_bytes(), b"new")

    def test_restore_human_output(self) -> None:
        make_tree(self.src, {"a.txt": "aaa"})
        self.assertEqual(self.save().returncode, 0)
        into = self.tmp / "restored"
        proc = self.restore(self.snapshot_id(), into)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(self.snapshot_id()[:16], proc.stdout)
        self.assertIn("文件：1", proc.stdout)
        self.assertIn("校验：1/1", proc.stdout)

    def test_unknown_snapshot_exit_2(self) -> None:
        proc = self.restore("deadbeefdeadbeef", self.tmp / "restored")
        self.assertEqual(proc.returncode, 2, proc.stdout)

    def test_ambiguous_prefix_exit_2(self) -> None:
        snaps = self.store / "snapshots"
        (snaps / "abc111").mkdir(parents=True)
        (snaps / "abc222").mkdir(parents=True)
        proc = self.restore("abc1", self.tmp / "restored")
        self.assertEqual(proc.returncode, 2, proc.stdout)


class TestCombinedClosureSnapshot(unittest.TestCase):
    """批 109：--before/--after/--snapshot 同给＝先判闭合，闭合才存快照。"""

    MAIN = ("\\documentclass{article}\n"
            "\\begin{document}\n"
            "The run uses 53 tokens.\n"
            "\\end{document}\n")

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tide-combined-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.before = make_tree(self.tmp / "before",
                                {"main.tex": self.MAIN})
        self.after = make_tree(self.tmp / "after",
                               {"main.tex": self.MAIN})
        self.store = self.tmp / "store"
        self.ledger = self.after / "audit" / "tide-events.ndjson"

    def combined(self, *extra: str):
        return run(["tide", "--before", str(self.before),
                    "--after", str(self.after),
                    "--snapshot", str(self.store), *extra])

    def write_after(self, text: str) -> None:
        (self.after / "main.tex").write_text(text, encoding="utf-8")

    def snapshots(self) -> list[Path]:
        snapdir = self.store / "snapshots"
        return sorted(snapdir.iterdir()) if snapdir.is_dir() else []

    def test_closed_change_commits_and_saves_snapshot(self):
        self.write_after(self.MAIN.replace("tokens.", "tokens!"))
        proc = self.combined("--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["mode"], "compare-snapshot")
        self.assertEqual(payload["status"], "commit")
        self.assertTrue(payload["snapshot_saved"])
        self.assertEqual(len(self.snapshots()), 1)
        self.assertEqual(self.snapshots()[0].name, payload["snapshot_id"])
        self.assertTrue(self.ledger.is_file())

    def test_no_change_still_commits_and_saves_snapshot(self):
        proc = self.combined("--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "commit")
        self.assertTrue(payload["snapshot_saved"])
        self.assertEqual(len(self.snapshots()), 1)

    def test_unclosed_does_not_save_snapshot_or_ledger(self):
        self.write_after(self.MAIN.replace("53", "54"))
        proc = self.combined("--json")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "rollback")
        self.assertFalse(payload["snapshot_saved"])
        self.assertIsNone(payload["snapshot"])
        self.assertEqual(self.snapshots(), [])
        self.assertFalse(self.ledger.exists())

    def test_pure_snapshot_says_no_closure_check(self):
        proc = run(["tide", "--after", str(self.after),
                    "--snapshot", str(self.store), "--json"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["mode"], "snapshot")
        self.assertFalse(payload["closure_checked"])
        self.assertIn("未做闭合判定", payload["notice"])
        human = run(["tide", "--after", str(self.after),
                     "--snapshot", str(self.store)])
        self.assertEqual(human.returncode, 0, human.stdout + human.stderr)
        self.assertIn("未做闭合判定", human.stdout)
        self.assertEqual(len(self.snapshots()), 1)


class TestUsage(SnapshotCase):
    def test_usage_errors(self) -> None:
        make_tree(self.src, {"a.txt": "aaa"})
        cases = {
            "保存缺 --after": ["tide", "--snapshot", str(self.store)],
            "恢复缺 --into": ["tide", "--restore", "abcd",
                              "--snapshot", str(self.store)],
            "恢复不许带 --after": ["tide", "--restore", "abcd",
                                    "--into", str(self.tmp / "x"),
                                    "--after", str(self.src),
                                    "--snapshot", str(self.store)],
            "比对缺 --after": ["tide", "--before", str(self.src)],
        }
        for name, args in cases.items():
            with self.subTest(name):
                proc = run(args)
                self.assertEqual(proc.returncode, 2,
                                 "%s：%s" % (name, proc.stdout))


if __name__ == "__main__":
    unittest.main()
