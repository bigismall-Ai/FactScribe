#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法国法条全量快照（blobstore）按需取件脚本。

快照形态
--------
GitHub Release 'corpus-fr-v1' 的唯一资产 blobs.sqlite 是一份**内容寻址**的块库：
每行一件（一条法条的官方 XML 原字节、它的证据卡，或整库的 index.json /
view_current.jsonl），按 sha256 寻址，载荷用 zstd + 训练字典压缩。

块库本身**不带 path**。path -> sha256 的对应关系只存在于仓内逐件索引
integrations/factscribe-legal/corpus-bulk/fr-blobstore-manifest.jsonl。
所以取件必须是「manifest 定位 + 块库取字节」两步，不能只靠块库还原目录树。

字段语义（以块库 schema 为准，与 manifest 一一对应）
----------------------------------------------------
- sha256    : **解压后**内容的 sha256（内容寻址的地址）
- bytes     : **解压后**字节数（块库列名 bytes_in）
- bytes_out : **压缩后**入库字节数（块库列名 bytes_out，等于载荷长度）
- codec     : zstd+dict；字典在块库 dicts 表里，键是 dict_sha16
- kind      : fr-law-card / fr-law-xml / fr-law-index / fr-law-view

四步管线（各自可单测）
----------------------
1. 取块 fetch_payload   : 按 sha256 / sha16 从块库读出压缩载荷
2. 解压 decompress      : zstd + 字典 -> 原字节
3. 校验 verify_sha256   : sha256 对不上**必须报错**（Sha256Mismatch），不静默跳过
4. 落盘 write_blob      : 按 manifest 的 path 写到 --out-dir 下，拒绝越界路径

依赖
----
zstandard（只有解压要用）。本仓 CI 是「纯标准库、离线」矩阵，故：
- 运行期缺 zstandard -> 报错并给出可直接复制的 uv run --with zstandard 命令；
- 单测不硬依赖它：解压步支持注入解压后端做接线测试，真实 zstd 往返测试在
  缺 zstandard 时自动跳过。

用法
----
    # 按 path 列表批量取件（避免全量解包）
    python3 ingest_fr_blobstore.py \
        --blobs /path/to/blobs.sqlite \
        --manifest integrations/factscribe-legal/corpus-bulk/fr-blobstore-manifest.jsonl \
        --paths-file want.txt --out-dir /tmp/fr-out

    # 抽样校验（只算不落盘）
    python3 ingest_fr_blobstore.py --blobs ... --manifest ... --sample 20 --verify-only

    # 只按 sha256 取一件
    python3 ingest_fr_blobstore.py --blobs ... --sha256 60e75fce... --out-dir /tmp/x
"""

import argparse
import hashlib
import json
import os
import random
import sqlite3
import sys
import urllib.parse

# ---------------------------------------------------------------- 退出码

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_SHA_MISMATCH = 4
EXIT_ERROR = 1


# ---------------------------------------------------------------- 异常

class BlobstoreError(Exception):
    """取件管线基类错误。"""


class MissingDependency(BlobstoreError):
    """缺运行期依赖（zstandard）。"""


class BlobNotFound(BlobstoreError):
    """块库里没有这一件。"""


class DictionaryNotFound(BlobstoreError):
    """块库里没有这块压缩字典。"""


class DecompressError(BlobstoreError):
    """解压失败：载荷损坏、或字典不对。"""


class Sha256Mismatch(BlobstoreError):
    """解压后的内容 sha256 与索引记录不一致——取到的字节变了，必须报错。

    绝不允许静默跳过：内容寻址库里 sha256 不符就说明取件链被改过，
    继续落盘等于把不可信字节写进语料仓。
    """

    def __init__(self, expected, actual, path=None):
        self.expected = expected
        self.actual = actual
        self.path = path
        where = ("（path=%s）" % path) if path else ""
        super().__init__(
            "sha256 对不上%s：期望 %s，实得 %s" % (where, expected, actual))


class PathEscape(BlobstoreError):
    """落盘路径越出输出目录。"""


# ---------------------------------------------------------------- 块库

# 两种只读 URI：先常规只读（走 fcntl 文件锁），失败再免锁的 immutable 只读
_OPEN_MODES = (
    ("?mode=ro", "常规只读（走 fcntl 文件锁）"),
    ("?mode=ro&immutable=1", "只读免锁（immutable，声明文件内容不会变）"),
)


def open_blobstore(db_path, connect=None):
    """只读打开块库。

    先试 mode=ro。sqlite 走 fcntl 文件锁，在部分沙箱/受保护目录下拿不到锁，
    会直接抛 sqlite3.OperationalError: unable to open database file，
    取件第一步就走不下去。失败时回退 mode=ro&immutable=1：免锁，并声明文件
    内容不会变——适合「只读打开一份自己下载、自己校验过 sha256 的静态快照」
    这个场景（块库是 GitHub release 的一次性资产，下载后就不再变）。

    两次都失败才报错，报错里把两次尝试各自的原因都写清楚。

    connect 是可注入的连接工厂（签名同 sqlite3.connect），供单测构造
    「mode=ro 失败、回退成功」这类情形；缺省用 sqlite3.connect。
    """
    if not os.path.isfile(db_path):
        raise FileNotFoundError("块库文件不存在：%s" % db_path)
    connector = connect or sqlite3.connect
    quoted = urllib.parse.quote(os.path.abspath(db_path))
    attempts = []
    for suffix, note in _OPEN_MODES:
        uri = "file:" + quoted + suffix
        conn = None
        try:
            conn = connector(uri, uri=True)
            conn.row_factory = sqlite3.Row
            # connect() 不一定当场报错（有的环境是首次读才报），
            # 所以探一下，确保「打不开」在这里就暴露，而不是拖到取件中途。
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            if attempts:
                print("[提示] 块库改用 %s 打开（常规只读失败：%s）"
                      % (note, attempts[0][2]), file=sys.stderr)
            return conn
        except sqlite3.Error as exc:
            attempts.append((suffix, note, "%s: %s" % (type(exc).__name__, exc)))
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
    detail = "\n  ".join(
        "尝试 %s（%s）失败 -> %s" % (suffix, note, err)
        for suffix, note, err in attempts)
    raise BlobstoreError("打开块库失败，两种只读方式都试过了：\n  " + detail)


def fetch_payload(conn, sha256=None, sha16=None):
    """取块：按 sha16（块库主键）或 sha256 取压缩载荷的原字节。

    载荷长度等于索引里的 bytes_out。

    取块要走主键：块库除了主键和 kind 上有索引，**sha256 列没有索引**，
    按 sha256 直查等于每件一次全表扫。所以先用 sha16 命中主键，再核
    sha256 列对不对；对不上就退回按 sha256 列找（慢，但兜底正确）。

    找不到抛 BlobNotFound；块库登记的 sha256 与要求的不一致抛 Sha256Mismatch。
    """
    if not sha256 and not sha16:
        raise ValueError("必须给 sha256 或 sha16 之一")
    row = None
    if sha16:
        row = conn.execute(
            "SELECT sha16, sha256, payload FROM blobs WHERE sha16 = ?",
            (sha16.lower(),)).fetchone()
    else:
        want = sha256.lower()
        # 块库约定：sha16 就是 sha256 的前 16 位（实测全库成立）
        row = conn.execute(
            "SELECT sha16, sha256, payload FROM blobs WHERE sha16 = ?",
            (want[:16],)).fetchone()
        if row is not None and row["sha256"].lower() != want:
            row = None
        if row is None:
            row = conn.execute(
                "SELECT sha16, sha256, payload FROM blobs WHERE sha256 = ?",
                (want,)).fetchone()
    if row is None:
        raise BlobNotFound(
            "块库里没有这一件：sha256=%s sha16=%s" % (sha256, sha16))
    if sha256 and row["sha256"].lower() != sha256.lower():
        raise Sha256Mismatch(sha256.lower(), row["sha256"].lower())
    return bytes(row["payload"])


def load_dictionary(conn, dict_sha16=None):
    """取压缩字典。dict_sha16 为空时取块库里唯一的那一块字典。"""
    if dict_sha16:
        row = conn.execute(
            "SELECT bytes FROM dicts WHERE sha16 = ?", (dict_sha16.lower(),)
        ).fetchone()
        if row is None:
            raise DictionaryNotFound(
                "块库里没有字典 %s（dicts 表现有：%s）"
                % (dict_sha16, list_dict_ids(conn)))
        return bytes(row["bytes"])
    rows = conn.execute("SELECT sha16 FROM dicts ORDER BY sha16").fetchall()
    if not rows:
        raise DictionaryNotFound("块库里没有任何字典（dicts 表为空）")
    if len(rows) > 1:
        raise DictionaryNotFound(
            "块库里有 %d 块字典，必须指明用哪块：%s"
            % (len(rows), ", ".join(r["sha16"] for r in rows)))
    row = conn.execute(
        "SELECT bytes FROM dicts WHERE sha16 = ?", (rows[0]["sha16"],)).fetchone()
    return bytes(row["bytes"])


def list_dict_ids(conn):
    """列出块库里的字典 id（给报错信息用）。"""
    return [r["sha16"] for r in
            conn.execute("SELECT sha16 FROM dicts ORDER BY sha16").fetchall()]


# ---------------------------------------------------------------- 解压

def _zstd_backend():
    """拿 zstandard 后端；缺依赖时给一句能直接抄的命令。"""
    try:
        import zstandard
    except ImportError as exc:
        raise MissingDependency(
            "缺 zstandard 依赖。装好再跑，或直接用：\n"
            "  uv run --with zstandard python3 %s ..." % os.path.basename(__file__)
        ) from exc
    return zstandard


def decompress(payload, dictionary=None, *, decompressor=None):
    """解压：zstd + 字典 -> 原字节。

    decompressor 是可注入的解压后端（签名 (payload, dictionary) -> bytes），
    供单测在没有 zstandard 的环境里测接线；None 表示走真实 zstd。
    """
    if decompressor is not None:
        try:
            return decompressor(payload, dictionary)
        except BlobstoreError:
            raise
        except Exception as exc:
            raise DecompressError("解压失败：%s" % exc) from exc
    zstd = _zstd_backend()
    try:
        kwargs = {}
        if dictionary:
            kwargs["dict_data"] = zstd.ZstdCompressionDict(dictionary)
        dctx = zstd.ZstdDecompressor(**kwargs)
        dobj = dctx.decompressobj()
        plain = dobj.decompress(payload)
        plain += dobj.flush()
    except Exception as exc:
        raise DecompressError("解压失败：%s" % exc) from exc
    return plain


# ---------------------------------------------------------------- 校验

def verify_sha256(data, expected_sha256, path=None):
    """校验解压后的内容；sha256 对不上抛 Sha256Mismatch。

    返回实际 sha256。expected 为空时只算不校（不应出现在正常路径上）。
    """
    actual = hashlib.sha256(data).hexdigest()
    if expected_sha256:
        expected = expected_sha256.lower()
        if actual != expected:
            raise Sha256Mismatch(expected, actual, path)
    return actual


def verify_lengths(data, payload, entry, path=None):
    """校验字节数与索引一致。

    bytes     = 解压后字节数（块库 bytes_in）
    bytes_out = 压缩后载荷长度（块库 bytes_out）
    """
    if "bytes" in entry and entry["bytes"] is not None:
        if len(data) != int(entry["bytes"]):
            raise BlobstoreError(
                "解压后字节数对不上（path=%s）：索引 %s，实得 %d"
                % (path, entry["bytes"], len(data)))
    if "bytes_out" in entry and entry["bytes_out"] is not None:
        if len(payload) != int(entry["bytes_out"]):
            raise BlobstoreError(
                "压缩载荷长度对不上（path=%s）：索引 %s，实得 %d"
                % (path, entry["bytes_out"], len(payload)))


# ---------------------------------------------------------------- 落盘

def write_blob(out_dir, rel_path, data):
    """按相对 path 落盘；拒绝越界路径。返回落盘后的绝对路径。"""
    if not rel_path:
        raise ValueError("落盘 path 不能为空")
    if os.path.isabs(rel_path):
        raise PathEscape("落盘 path 不能是绝对路径：%s" % rel_path)
    parts = rel_path.replace("\\", "/").split("/")
    if any(p in ("..", "") for p in parts):
        raise PathEscape("落盘 path 非法（含 .. 或空段）：%s" % rel_path)
    root = os.path.realpath(out_dir)
    target = os.path.realpath(os.path.join(root, *parts))
    if target != root and not target.startswith(root + os.sep):
        raise PathEscape("落盘 path 越出输出目录：%s" % rel_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as fh:
        fh.write(data)
    return target


# ---------------------------------------------------------------- 索引

def load_manifest_index(manifest_path):
    """读逐件索引 manifest.jsonl -> {path: entry}。"""
    index = {}
    with open(manifest_path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError as exc:
                raise BlobstoreError(
                    "索引第 %d 行不是合法 JSON：%s" % (lineno, exc)) from exc
            path = rec.get("path")
            if path:
                index[path] = rec
    return index


def sample_entries(index, count, seed=20261128):
    """从索引里分层抽样：按 kind 轮转抽，尽量覆盖到每个 kind。"""
    buckets = {}
    for path, entry in index.items():
        buckets.setdefault(entry.get("kind", ""), []).append((path, entry))
    rng = random.Random(seed)
    for items in buckets.values():
        items.sort(key=lambda item: item[0])
        rng.shuffle(items)
    picked = []
    kinds = sorted(buckets)
    pos = 0
    while len(picked) < count and any(buckets[k] for k in kinds):
        kind = kinds[pos % len(kinds)]
        if buckets[kind]:
            picked.append(buckets[kind].pop())
        pos += 1
        if pos > count * (len(kinds) + 2) + 1000:
            break
    return picked


# ---------------------------------------------------------------- 取件

def extract_one(conn, entry, dictionary, out_dir, *,
                decompressor=None, verify_only=False):
    """取一件：取块 -> 解压 -> 校验 -> 落盘。返回结果 dict。"""
    path = entry.get("path", "")
    payload = fetch_payload(conn, sha256=entry.get("sha256"),
                            sha16=entry.get("sha16"))
    data = decompress(payload, dictionary, decompressor=decompressor)
    verify_lengths(data, payload, entry, path)
    verify_sha256(data, entry.get("sha256"), path)
    result = {
        "path": path,
        "kind": entry.get("kind", ""),
        "sha256": entry.get("sha256", ""),
        "bytes": len(data),
        "bytes_out": len(payload),
        "written": "",
    }
    if not verify_only:
        if not out_dir:
            raise BlobstoreError("要落盘就必须给 --out-dir")
        result["written"] = write_blob(out_dir, path, data)
    return result


# ---------------------------------------------------------------- CLI

def _read_paths_file(path):
    """从文本文件读 path 列表（每行一个，# 开头是注释）。"""
    paths = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            paths.append(line)
    return paths


def build_parser():
    p = argparse.ArgumentParser(
        description="法国法条全量快照（blobstore）按需取件：按 sha256 取块、"
                    "zstd+字典解压、校验 sha256、按 path 落盘。")
    p.add_argument("--blobs", required=True, help="blobs.sqlite 路径")
    p.add_argument("--manifest", help="逐件索引 fr-blobstore-manifest.jsonl 路径")
    p.add_argument("--paths-file", help="要取的 path 列表文件（每行一个 path）")
    p.add_argument("--path", action="append", default=[],
                   help="要取的 path（可重复）")
    p.add_argument("--sha256", action="append", default=[],
                   help="直接按 sha256 取件（可重复；path 需靠索引反查）")
    p.add_argument("--sample", type=int, default=0,
                   help="从索引里分层抽 N 件（按 kind 轮转）")
    p.add_argument("--sample-seed", type=int, default=20261128,
                   help="抽样随机种子（默认 20261128，保证可复现）")
    p.add_argument("--out-dir", help="落盘根目录（不给就只校验不落盘）")
    p.add_argument("--dict", help="压缩字典文件（不给就从块库 dicts 表取）")
    p.add_argument("--dict-sha16", help="用块库里哪块字典")
    p.add_argument("--verify-only", action="store_true",
                   help="只取件校验，不落盘")
    p.add_argument("--json", action="store_true", help="按 JSON 输出汇总")
    p.add_argument("--quiet", action="store_true", help="不打印逐件明细")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        conn = open_blobstore(args.blobs)
    except (OSError, sqlite3.Error, BlobstoreError) as exc:
        print("打开块库失败：%s" % exc, file=sys.stderr)
        return EXIT_ERROR

    try:
        index = {}
        if args.manifest:
            try:
                index = load_manifest_index(args.manifest)
            except (OSError, BlobstoreError) as exc:
                print("读索引失败：%s" % exc, file=sys.stderr)
                return EXIT_ERROR

        wanted = []          # [(path, entry)]，entry 可为 None
        for p in args.path:
            wanted.append((p, index.get(p)))
        if args.paths_file:
            try:
                for p in _read_paths_file(args.paths_file):
                    wanted.append((p, index.get(p)))
            except OSError as exc:
                print("读 path 列表失败：%s" % exc, file=sys.stderr)
                return EXIT_ERROR
        if args.sample:
            for p, entry in sample_entries(index, args.sample, args.sample_seed):
                wanted.append((p, entry))
        for sha in args.sha256:
            entry = None
            for p, rec in index.items():
                if rec.get("sha256") == sha.lower():
                    entry = rec
                    break
            wanted.append((entry["path"] if entry else "", entry or
                           {"sha256": sha.lower(), "path": "", "kind": ""}))
        if not wanted:
            print("没指定要取什么：给 --path / --paths-file / --sha256 / --sample",
                  file=sys.stderr)
            return EXIT_USAGE

        # 字典：显式文件优先；其次显式 dict_sha16；
        # 再从本次要取的件上收集 dict_sha16（唯一就用它）；最后才让块库自己决定。
        dictionary = None
        try:
            if args.dict:
                with open(args.dict, "rb") as fh:
                    dictionary = fh.read()
            else:
                dict_sha16 = args.dict_sha16
                if not dict_sha16:
                    used = {e.get("dict_sha16") for _, e in wanted if e and e.get("dict_sha16")}
                    if len(used) == 1:
                        dict_sha16 = used.pop()
                dictionary = load_dictionary(conn, dict_sha16)
        except (OSError, BlobstoreError) as exc:
            print("取字典失败：%s" % exc, file=sys.stderr)
            return EXIT_ERROR

        ok, failed, missing = [], [], []
        for path, entry in wanted:
            if entry is None:
                missing.append(path)
                continue
            try:
                result = extract_one(conn, entry, dictionary, args.out_dir,
                                     verify_only=args.verify_only or not args.out_dir)
                ok.append(result)
                if not args.quiet:
                    print("[ok] %s（%s，解压 %d B / 压缩 %d B）"
                          % (result["path"], result["kind"],
                             result["bytes"], result["bytes_out"]))
            except Sha256Mismatch as exc:
                failed.append({"path": path, "error": str(exc),
                               "expected": exc.expected, "actual": exc.actual})
                print("[sha256 不符] %s：%s" % (path, exc), file=sys.stderr)
            except BlobstoreError as exc:
                failed.append({"path": path, "error": str(exc)})
                print("[失败] %s：%s" % (path, exc), file=sys.stderr)

        summary = {
            "blobs": os.path.abspath(args.blobs),
            "manifest": os.path.abspath(args.manifest) if args.manifest else "",
            "out_dir": os.path.abspath(args.out_dir) if args.out_dir else "",
            "attempted": len(wanted),
            "ok": len(ok),
            "failed": len(failed),
            "missing_in_manifest": len(missing),
            "sha256_mismatch": len([f for f in failed if "expected" in f]),
            "bytes_total": sum(r["bytes"] for r in ok),
            "bytes_out_total": sum(r["bytes_out"] for r in ok),
            "ok_detail": ok,
            "failed_detail": failed,
            "missing_detail": missing[:50],
        }
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print("—— 汇总 ——")
            print("尝试 %d 件：成功 %d，失败 %d（其中 sha256 不符 %d），索引里找不到 %d"
                  % (summary["attempted"], summary["ok"], summary["failed"],
                     summary["sha256_mismatch"], summary["missing_in_manifest"]))
            print("解压后合计 %d 字节；压缩载荷合计 %d 字节"
                  % (summary["bytes_total"], summary["bytes_out_total"]))
        if failed:
            return EXIT_SHA_MISMATCH if summary["sha256_mismatch"] else EXIT_ERROR
        return EXIT_OK
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
