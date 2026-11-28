#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法国法条全量快照取件脚本的单测（标准库 unittest，不依赖上游）。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v

本仓 CI 是「纯标准库、离线」矩阵，故解压步用**可注入的解压后端**做接线测试；
真实 zstd + 字典往返测试在环境缺 zstandard 时自动跳过（本地用
uv run --with zstandard python3 -m unittest ... 可把那一档也跑起来）。
"""

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import ingest_fr_blobstore as ing  # noqa: E402

try:
    import zstandard as _zstd  # noqa: E402
except ImportError:  # pragma: no cover - 看环境有没有
    _zstd = None


SCHEMA = """
CREATE TABLE blobs(
  sha16 TEXT PRIMARY KEY, sha256 TEXT NOT NULL, kind TEXT NOT NULL,
  bytes_in INTEGER NOT NULL, bytes_out INTEGER NOT NULL, codec TEXT NOT NULL,
  dict_sha16 TEXT, payload BLOB NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE dicts(
  sha16 TEXT PRIMARY KEY, bytes BLOB NOT NULL,
  sample_bytes INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
"""


def _sha16(sha256):
    return sha256[:16]


def _make_store(dirpath, blobs=(), dicts=()):
    """造一个只含必要表的假块库。

    blobs 每项：(sha256, kind, payload, bytes_in, bytes_out, dict_sha16)
    dicts 每项：(sha16, bytes)
    """
    os.makedirs(dirpath, exist_ok=True)
    db = os.path.join(dirpath, "blobs.sqlite")
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    for sha256, kind, payload, bytes_in, bytes_out, dict_sha16 in blobs:
        conn.execute(
            "INSERT INTO blobs VALUES (?,?,?,?,?,?,?,?,?)",
            (_sha16(sha256), sha256, kind, bytes_in, bytes_out,
             "zstd+dict", dict_sha16, payload, "2026-11-17T00:00:00Z"))
    for sha16, dbytes in dicts:
        conn.execute(
            "INSERT INTO dicts VALUES (?,?,?,?)",
            (sha16, dbytes, 0, "2026-11-17T00:00:00Z"))
    conn.commit()
    conn.close()
    return db


class TestFetchPayload(unittest.TestCase):
    """第 1 步：取块。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.payload = b"\x28\xb5\x2f\xfd compressed bytes"
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.db = _make_store(
            self.tmp.name,
            blobs=[(self.sha, "fr-law-card", self.payload, 100, len(self.payload),
                    "79a30ff9f31903a5")],
            dicts=[("79a30ff9f31903a5", b"DICTBYTES")])

    def test_fetch_by_sha256(self):
        conn = ing.open_blobstore(self.db)
        self.addCleanup(conn.close)
        got = ing.fetch_payload(conn, sha256=self.sha)
        self.assertEqual(got, self.payload)

    def test_fetch_by_sha16(self):
        conn = ing.open_blobstore(self.db)
        self.addCleanup(conn.close)
        got = ing.fetch_payload(conn, sha16=_sha16(self.sha))
        self.assertEqual(got, self.payload)

    def test_fetch_missing_raises(self):
        conn = ing.open_blobstore(self.db)
        self.addCleanup(conn.close)
        with self.assertRaises(ing.BlobNotFound):
            ing.fetch_payload(conn, sha256="0" * 64)

    def test_fetch_needs_one_key(self):
        conn = ing.open_blobstore(self.db)
        self.addCleanup(conn.close)
        with self.assertRaises(ValueError):
            ing.fetch_payload(conn)

    def test_open_readonly(self):
        conn = ing.open_blobstore(self.db)
        self.addCleanup(conn.close)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("DELETE FROM blobs")


class TestDictionary(unittest.TestCase):
    """压缩字典取用。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_load_by_id(self):
        db = _make_store(self.tmp.name, dicts=[("79a30ff9f31903a5", b"D1")])
        conn = ing.open_blobstore(db)
        self.addCleanup(conn.close)
        self.assertEqual(ing.load_dictionary(conn, "79a30ff9f31903a5"), b"D1")

    def test_load_single_auto(self):
        db = _make_store(self.tmp.name, dicts=[("79a30ff9f31903a5", b"D1")])
        conn = ing.open_blobstore(db)
        self.addCleanup(conn.close)
        self.assertEqual(ing.load_dictionary(conn), b"D1")

    def test_load_ambiguous_raises(self):
        db = _make_store(self.tmp.name,
                         dicts=[("aaa", b"D1"), ("bbb", b"D2")])
        conn = ing.open_blobstore(db)
        self.addCleanup(conn.close)
        with self.assertRaises(ing.DictionaryNotFound):
            ing.load_dictionary(conn)

    def test_load_missing_raises(self):
        db = _make_store(self.tmp.name, dicts=[("aaa", b"D1")])
        conn = ing.open_blobstore(db)
        self.addCleanup(conn.close)
        with self.assertRaises(ing.DictionaryNotFound):
            ing.load_dictionary(conn, "zzz")


class TestDecompress(unittest.TestCase):
    """第 2 步：解压。"""

    def test_injected_backend_is_used(self):
        seen = {}

        def fake(payload, dictionary):
            seen["payload"] = payload
            seen["dictionary"] = dictionary
            return b"PLAIN"

        out = ing.decompress(b"RAW", b"DICT", decompressor=fake)
        self.assertEqual(out, b"PLAIN")
        self.assertEqual(seen["payload"], b"RAW")
        self.assertEqual(seen["dictionary"], b"DICT")

    def test_backend_error_is_wrapped(self):
        def boom(payload, dictionary):
            raise RuntimeError("坏载荷")

        with self.assertRaises(ing.DecompressError):
            ing.decompress(b"RAW", None, decompressor=boom)

    @unittest.skipUnless(_zstd, "环境缺 zstandard，跳过真实 zstd 往返")
    def test_real_zstd_with_dict_roundtrip(self):
        samples = [b"Code civil article 1" * 50, b"LEGIARTI000012345678"]
        zdict = _zstd.ZstdCompressionDict(b"".join(samples))
        cctx = _zstd.ZstdCompressor(dict_data=zdict)
        raw = b"Code civil article 1" * 100
        packed = cctx.compress(raw)
        plain = ing.decompress(packed, b"".join(samples))
        self.assertEqual(plain, raw)

    @unittest.skipUnless(_zstd, "环境缺 zstandard，跳过缺字典报错")
    def test_real_zstd_missing_dict_raises(self):
        """载荷确实用了字典时，缺字典/错字典都必须报错（不许静默解出错字节）。"""
        samples = b"CODE_CIVIL_ARTICLE_UNIFORM_SAMPLE_TEXT" * 20
        zdict = _zstd.ZstdCompressionDict(samples)
        raw = b"CODE_CIVIL_ARTICLE_UNIFORM_SAMPLE_TEXT" * 40
        packed = _zstd.ZstdCompressor(dict_data=zdict).compress(raw)
        with self.assertRaises(ing.DecompressError):
            ing.decompress(packed, None)
        with self.assertRaises(ing.DecompressError):
            ing.decompress(packed, b"OTHER_DICT_BYTES_HERE_XXXX")


class TestVerify(unittest.TestCase):
    """第 3 步：校验。"""

    def test_verify_ok(self):
        data = b"hello"
        sha = hashlib.sha256(data).hexdigest()
        self.assertEqual(ing.verify_sha256(data, sha), sha)

    def test_mismatch_raises(self):
        with self.assertRaises(ing.Sha256Mismatch) as ctx:
            ing.verify_sha256(b"hello", "0" * 64, path="fr/x.xml")
        self.assertEqual(ctx.exception.expected, "0" * 64)
        self.assertEqual(ctx.exception.actual,
                         hashlib.sha256(b"hello").hexdigest())
        self.assertIn("fr/x.xml", str(ctx.exception))

    def test_empty_expected_only_computes(self):
        self.assertEqual(ing.verify_sha256(b"hello", ""),
                         hashlib.sha256(b"hello").hexdigest())


class TestWrite(unittest.TestCase):
    """第 4 步：落盘。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_write_creates_file(self):
        target = ing.write_blob(self.tmp.name, "fr/0-1.card.txt", b"HI")
        self.assertTrue(os.path.isfile(target))
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"HI")

    def test_write_rejects_absolute(self):
        with self.assertRaises(ing.PathEscape):
            ing.write_blob(self.tmp.name, "/etc/passwd", b"x")

    def test_write_rejects_dotdot(self):
        with self.assertRaises(ing.PathEscape):
            ing.write_blob(self.tmp.name, "../outside.txt", b"x")

    def test_write_rejects_empty(self):
        with self.assertRaises(ValueError):
            ing.write_blob(self.tmp.name, "", b"x")


class TestExtractOne(unittest.TestCase):
    """四步串起来：取块 -> 解压 -> 校验 -> 落盘。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plain = b"DEPLAINED CONTENT"
        self.sha = hashlib.sha256(self.plain).hexdigest()
        self.payload = b"COMPRESSED"
        self.db = _make_store(
            self.tmp.name,
            blobs=[(self.sha, "fr-law-card", self.payload,
                    len(self.plain), len(self.payload), "79a30ff9f31903a5")],
            dicts=[("79a30ff9f31903a5", b"DICTBYTES")])
        self.conn = ing.open_blobstore(self.db)
        self.addCleanup(self.conn.close)
        self.entry = {
            "path": "fr/0-1.card.txt",
            "kind": "fr-law-card",
            "sha256": self.sha,
            "bytes": len(self.plain),
            "bytes_out": len(self.payload),
        }

    def _backend(self):
        return lambda payload, dictionary: self.plain

    def test_end_to_end(self):
        out_dir = os.path.join(self.tmp.name, "out")
        res = ing.extract_one(self.conn, self.entry, b"DICTBYTES", out_dir,
                               decompressor=self._backend())
        self.assertEqual(res["path"], "fr/0-1.card.txt")
        self.assertEqual(res["bytes"], len(self.plain))
        self.assertEqual(res["bytes_out"], len(self.payload))
        with open(res["written"], "rb") as fh:
            self.assertEqual(fh.read(), self.plain)

    def test_sha_mismatch_raises_and_writes_nothing(self):
        """块库行里声称的 sha256 与解压后内容的真实 sha256 不符 -> 必须报错、且不落盘。

        这是内容寻址库里最危险的形态：块在、也查得到，但内容已经不是登记的那份。
        """
        claimed = "1" * 64
        db2 = _make_store(
            self.tmp.name + "/2",
            blobs=[(claimed, "fr-law-card", self.payload, len(self.plain),
                    len(self.payload), "79a30ff9f31903a5")],
            dicts=[("79a30ff9f31903a5", b"DICTBYTES")])
        conn2 = ing.open_blobstore(db2)
        self.addCleanup(conn2.close)
        bad = dict(self.entry, sha256=claimed)
        out_dir = os.path.join(self.tmp.name, "out")
        with self.assertRaises(ing.Sha256Mismatch):
            ing.extract_one(conn2, bad, b"DICTBYTES", out_dir,
                            decompressor=self._backend())
        self.assertFalse(os.path.exists(out_dir))

    def test_length_mismatch_raises(self):
        out_dir = os.path.join(self.tmp.name, "out")
        bad = dict(self.entry, bytes=999)
        with self.assertRaises(ing.BlobstoreError):
            ing.extract_one(self.conn, bad, b"DICTBYTES", out_dir,
                            decompressor=self._backend())

    def test_verify_only_does_not_write(self):
        res = ing.extract_one(self.conn, self.entry, b"DICTBYTES", None,
                               decompressor=self._backend(), verify_only=True)
        self.assertEqual(res["written"], "")


class TestManifestIndex(unittest.TestCase):
    """逐件索引的读取与抽样。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write_manifest(self, rows):
        path = os.path.join(self.tmp.name, "manifest.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    def test_load_index(self):
        path = self._write_manifest([
            {"path": "fr/a.xml", "kind": "fr-law-xml", "sha256": "a" * 64},
            {"path": "fr/a.card.txt", "kind": "fr-law-card", "sha256": "b" * 64},
        ])
        index = ing.load_manifest_index(path)
        self.assertEqual(len(index), 2)
        self.assertEqual(index["fr/a.xml"]["kind"], "fr-law-xml")

    def test_bad_line_raises(self):
        path = os.path.join(self.tmp.name, "bad.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json}\n")
        with self.assertRaises(ing.BlobstoreError):
            ing.load_manifest_index(path)

    def test_sample_covers_kinds(self):
        index = {}
        for i in range(10):
            index["fr/x%d.xml" % i] = {"kind": "fr-law-xml"}
            index["fr/x%d.card.txt" % i] = {"kind": "fr-law-card"}
        index["fr/index.json"] = {"kind": "fr-law-index"}
        picked = ing.sample_entries(index, 6, seed=1)
        self.assertEqual(len(picked), 6)
        kinds = {entry["kind"] for _, entry in picked}
        self.assertIn("fr-law-xml", kinds)
        self.assertIn("fr-law-card", kinds)


class TestCli(unittest.TestCase):
    """命令行入口。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _store_and_manifest(self, manifest_sha=None):
        """造块库+索引。

        块库行里登记的 sha256 与 manifest 里的一致（= manifest_sha 或内容的真实哈希）；
        载荷解压后恒为 plain。所以 manifest_sha 给错值时，就是
        「块在、查得到、但内容哈希对不上」的形态。
        """
        plain = b"DEPLAINED CONTENT"
        real_sha = hashlib.sha256(plain).hexdigest()
        claimed = manifest_sha or real_sha
        payload = b"COMPRESSED"
        db = _make_store(
            self.tmp.name,
            blobs=[(claimed, "fr-law-card", payload, len(plain), len(payload),
                    "79a30ff9f31903a5")],
            dicts=[("79a30ff9f31903a5", b"DICTBYTES")])
        mf = os.path.join(self.tmp.name, "manifest.jsonl")
        with open(mf, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "path": "fr/0-1.card.txt", "kind": "fr-law-card",
                "sha256": claimed,
                "bytes": len(plain), "bytes_out": len(payload),
            }) + "\n")
        return db, mf, plain

    def test_no_target_returns_usage(self):
        db, mf, _ = self._store_and_manifest()
        code = ing.main(["--blobs", db, "--manifest", mf])
        self.assertEqual(code, ing.EXIT_USAGE)

    def test_missing_blob_file(self):
        code = ing.main(["--blobs", os.path.join(self.tmp.name, "nope.sqlite"),
                         "--path", "fr/x.xml"])
        self.assertEqual(code, ing.EXIT_ERROR)

    def test_sha_mismatch_exit_code(self):
        """索引里的 sha256 与实际内容不符 -> 退出码是 sha 不符那一档，且不落盘。"""
        db, mf, plain = self._store_and_manifest(manifest_sha="2" * 64)
        out_dir = os.path.join(self.tmp.name, "out")
        # 换成假的解压后端：CLI 这一路不依赖 zstandard 也能跑通到校验步
        orig = ing.decompress
        ing.decompress = lambda payload, dictionary, decompressor=None: plain
        try:
            code = ing.main(["--blobs", db, "--manifest", mf,
                             "--path", "fr/0-1.card.txt", "--out-dir", out_dir,
                             "--json"])
        finally:
            ing.decompress = orig
        self.assertEqual(code, ing.EXIT_SHA_MISMATCH)
        self.assertFalse(os.path.exists(out_dir))

    def test_ok_path_exit_code(self):
        """sha256 对得上 -> 退出码 0，并按 path 落盘。"""
        db, mf, plain = self._store_and_manifest()
        out_dir = os.path.join(self.tmp.name, "out")
        orig = ing.decompress
        ing.decompress = lambda payload, dictionary, decompressor=None: plain
        try:
            code = ing.main(["--blobs", db, "--manifest", mf,
                             "--path", "fr/0-1.card.txt", "--out-dir", out_dir,
                             "--json"])
        finally:
            ing.decompress = orig
        self.assertEqual(code, ing.EXIT_OK)
        with open(os.path.join(out_dir, "fr", "0-1.card.txt"), "rb") as fh:
            self.assertEqual(fh.read(), plain)


class _FakeConn:
    """假连接：够 open_blobstore 的探测与断言用。"""

    def __init__(self, fail_on_execute=False):
        self.row_factory = None
        self.fail_on_execute = fail_on_execute
        self.closed = False
        self.executed = []

    def execute(self, sql, *args):
        self.executed.append(sql)
        if self.fail_on_execute:
            raise sqlite3.OperationalError("unable to open database file")
        return self

    def fetchone(self):
        return ("blobs",)

    def close(self):
        self.closed = True


class TestOpenBlobstoreFallback(unittest.TestCase):
    """打开块库：mode=ro 失败要能回退到 immutable 只读。

    背景：sqlite 的 mode=ro 要走 fcntl 文件锁，在部分沙箱/受保护目录下
    拿不到锁，直接抛 "unable to open database file"，取件第一步就走不下去。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = _make_store(
            self.tmp.name,
            blobs=[("a" * 64, "fr-law-card", b"PAYLOAD", 7, 7, "79a30ff9f31903a5")],
            dicts=[("79a30ff9f31903a5", b"DICTBYTES")])

    def test_mode_ro_success_does_not_fall_back(self):
        """常规只读能开就不该多走一趟。"""
        calls = []

        def connector(target, uri=False):
            calls.append(target)
            return _FakeConn()

        conn = ing.open_blobstore(self.db, connect=connector)
        self.addCleanup(conn.close)
        self.assertEqual(len(calls), 1)
        self.assertIn("mode=ro", calls[0])
        self.assertNotIn("immutable", calls[0])

    def test_falls_back_to_immutable_when_mode_ro_fails(self):
        """mode=ro 抛错 -> 回退 mode=ro&immutable=1，并真的能用。"""
        calls = []

        def connector(target, uri=False):
            calls.append(target)
            if len(calls) == 1:
                raise sqlite3.OperationalError("unable to open database file")
            return _FakeConn()

        conn = ing.open_blobstore(self.db, connect=connector)
        self.addCleanup(conn.close)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("immutable", calls[0])
        self.assertIn("mode=ro&immutable=1", calls[1])
        self.assertTrue(conn.executed)

    def test_immutable_uri_really_opens_a_real_store(self):
        """回退用的 URI 形态要真能打开一个真实 sqlite 文件。"""
        real_connect = sqlite3.connect
        calls = []

        def connector(target, uri=False):
            calls.append(target)
            if len(calls) == 1:
                raise sqlite3.OperationalError("unable to open database file")
            return real_connect(target, uri=True)

        conn = ing.open_blobstore(self.db, connect=connector)
        self.addCleanup(conn.close)
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM blobs").fetchone()[0], 1)

    def test_probe_failure_triggers_fallback(self):
        """connect 成功但首次读就报错（有的环境是首次读才报锁错）-> 同样要回退。"""
        calls = []

        def connector(target, uri=False):
            calls.append(target)
            if len(calls) == 1:
                return _FakeConn(fail_on_execute=True)
            return _FakeConn()

        conn = ing.open_blobstore(self.db, connect=connector)
        self.addCleanup(conn.close)
        self.assertEqual(len(calls), 2)
        self.assertIn("mode=ro&immutable=1", calls[1])

    def test_both_attempts_fail_reports_both_reasons(self):
        """两种都失败 -> 报错，且两种尝试各自的原因都在错误信息里。"""
        calls = []

        def connector(target, uri=False):
            calls.append(target)
            if len(calls) == 1:
                raise sqlite3.OperationalError("unable to open database file")
            raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(ing.BlobstoreError) as ctx:
            ing.open_blobstore(self.db, connect=connector)
        self.assertEqual(len(calls), 2)
        msg = str(ctx.exception)
        self.assertIn("unable to open database file", msg)
        self.assertIn("database is locked", msg)
        self.assertIn("mode=ro", msg)
        self.assertIn("immutable", msg)

    def test_missing_file_still_raises_before_connecting(self):
        """文件不存在时不要去试两种 URI，直接报缺文件。"""
        calls = []

        def connector(target, uri=False):
            calls.append(target)
            return _FakeConn()

        with self.assertRaises(FileNotFoundError):
            ing.open_blobstore(os.path.join(self.tmp.name, "nope.sqlite"),
                               connect=connector)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
