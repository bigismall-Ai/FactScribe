#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 FactScribe MiniApp 包打成单文件快照，并做发布前限制自检。

用法（在仓库根执行）：
    python3 scripts/make_miniapp_submit_zip.py

产物：dist/factscribe-miniapp-submit.zip

用途（2026-11-23 改道后）：社区仓库提交走 git 目录形态
（plugins/<github-username>/factscribe/），本脚本产出的 ZIP 不再是提交物，
保留它是给「发版快照／离线分发／将来走官方市场」用——它与社区形态的包内容一致
（同样不含 build.sh、install.sh），并且自带限额自检。

口径来源：MiniMax《插件开发与上架指南》第 2/3/7/9 节（2026-11-23 核对）。
  - ZIP 根目录必须直接含 .minimax-plugin/plugin.json，不再套一层目录；
  - 文件名/路径只用 ASCII 字母数字点下划线连字符，路径用 / 分隔；
  - 不接受符号链接、硬链接、LFS 指针、submodule、包安装生命周期脚本、
    平台专属二进制、依赖可执行位的文件；
  - 文本 UTF-8 无 BOM；JSON 必须是 object 且无重复 key；
  - 限额：ZIP 原始 ≤64 MiB、entries ≤2048、普通文件 ≤1024、单文件解包 ≤16 MiB、
    全部解包 ≤64 MiB、完整路径 ≤512 bytes、单段 ≤128 bytes、深度 ≤16 段。

打包口径（为什么排除两个脚本）：
  - build.sh 依赖 FactScribe 仓源（从仓库根复制引擎），随包分发无法运行；
  - install.sh 是仓内安装脚本，官方市场安装不经过它，且它带可执行位；
  两者只留在仓库 miniapp/ 源目录里，不进提交包。
"""
from __future__ import annotations

import json
import os
import re
import struct
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "miniapp")
OUT = os.path.join(REPO, "dist", "factscribe-miniapp-submit.zip")

EXCLUDE_FILES = {"build.sh", "install.sh"}
EXCLUDE_DIRS = {"__pycache__", ".git", "node_modules", ".pytest_cache"}
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".DS_Store")
ZIP_DATE = (2026, 11, 23, 0, 0, 0)
TEXT_EXTS = {
    ".json", ".md", ".txt", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".csv", ".tsv",
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css",
    ".sh", ".pyi", ".rst", ".in",
}

SEG_RE = re.compile(r"^[A-Za-z0-9._-]+$")
WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

LIMITS = {
    "zip_bytes": 64 * 1024 * 1024,
    "entries": 2048,
    "files": 1024,
    "single_file": 16 * 1024 * 1024,
    "total": 64 * 1024 * 1024,
    "path_bytes": 512,
    "segment_bytes": 128,
    "depth": 16,
}


def collect() -> list[tuple[str, str]]:
    """返回 (绝对路径, 包内相对路径) 列表；相对路径用 / 分隔、无前导 ./。"""
    items: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(SRC):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            if name in EXCLUDE_FILES or name.endswith(EXCLUDE_SUFFIX):
                continue
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, SRC).replace(os.sep, "/")
            items.append((abs_path, rel))
    return sorted(items, key=lambda kv: kv[1])


def build(items: list[tuple[str, str]]) -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for abs_path, rel in items:
            info = zipfile.ZipInfo(rel, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # unix
            info.external_attr = 0o644 << 16  # 普通文件、无可执行位
            with open(abs_path, "rb") as fh:
                zf.writestr(info, fh.read())


def check_source(items: list[tuple[str, str]]) -> list[str]:
    """打包前对源文件做内容层检查（BOM／UTF-8／JSON object 且无重复键／无凭据）。"""
    problems: list[str] = []
    secret_re = re.compile(
        r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,}"
        r"|AKIA[0-9A-Z]{16}|(?i:bearer\s+[A-Za-z0-9._-]{20,})"
        r"|(?i:(api[_-]?key|secret|password)\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']))"
    )
    for abs_path, rel in items:
        raw = open(abs_path, "rb").read()
        ext = os.path.splitext(rel)[1].lower()
        is_text = ext in TEXT_EXTS
        if is_text and raw.startswith(b"\xef\xbb\xbf"):
            problems.append(f"BOM: {rel}")
        if is_text:
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError:
                problems.append(f"非 UTF-8 文本: {rel}")
        if rel.endswith(".json"):
            def hook(pairs, _rel=rel):
                keys = [k for k, _ in pairs]
                dups = sorted({k for k in keys if keys.count(k) > 1})
                if dups:
                    raise ValueError(f"重复 key {dups} in {_rel}")
                return dict(pairs)

            try:
                obj = json.loads(raw.decode("utf-8"), object_pairs_hook=hook)
            except Exception as exc:
                problems.append(f"JSON 解析失败: {rel}: {exc}")
            else:
                if not isinstance(obj, dict):
                    problems.append(f"JSON 不是 object: {rel}")
        if is_text:
            text = raw.decode("utf-8", "replace")
            for i, line in enumerate(text.splitlines(), 1):
                if secret_re.search(line):
                    problems.append(f"疑似凭据: {rel}:{i}")
    return problems


def check_icon(items: list[tuple[str, str]]) -> list[str]:
    """icon 必须真实存在、扩展名与字节一致。"""
    problems: list[str] = []
    manifest_path = os.path.join(SRC, ".minimax-plugin", "plugin.json")
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
    icon = manifest.get("icon")
    if not icon:
        return ["manifest 无 icon 字段"]
    if "darkIcon" in manifest:
        problems.append("manifest 声明了 darkIcon（当前生产发布不接受）")
    icon_abs = os.path.join(SRC, icon)
    if not os.path.isfile(icon_abs):
        return [f"icon 文件不存在: {icon}"]
    head = open(icon_abs, "rb").read(16)
    ext = os.path.splitext(icon)[1].lower()
    magic_ok = {
        ".png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": head.startswith(b"\xff\xd8\xff"),
        ".jpeg": head.startswith(b"\xff\xd8\xff"),
        ".webp": head[:4] == b"RIFF" and head[8:12] == b"WEBP",
    }.get(ext, False)
    if not magic_ok:
        problems.append(f"icon 字节与扩展名不符: {icon}（magic={head[:8].hex()}）")
    # docs/ 下的配图是社区形态允许的（PR 用截图），不算「多余图标」；
    # 其余位置的额外图片仍按多余图标报。
    extra_images = [
        rel for _, rel in items
        if os.path.splitext(rel)[1].lower() in MIME_BY_EXT
        and rel != icon
        and not rel.startswith("docs/")
    ]
    if extra_images:
        problems.append(f"包内有多余图标文件: {extra_images}")
    return problems


def audit(items: list[tuple[str, str]]) -> dict:
    """对产出的 ZIP 做发布前限制实测。"""
    problems: list[str] = []
    seen_lower: dict[str, str] = {}
    file_count = 0
    total_unpacked = 0
    max_file = ("", 0)
    max_path = ("", 0)
    max_seg = ("", 0)
    max_depth = ("", 0)

    with zipfile.ZipFile(OUT) as zf:
        infos = zf.infolist()
        zip_bytes = os.path.getsize(OUT)
        if zip_bytes > LIMITS["zip_bytes"]:
            problems.append(f"ZIP 原始大小超限: {zip_bytes}")
        if len(infos) > LIMITS["entries"]:
            problems.append(f"entries 超限: {len(infos)}")
        for info in infos:
            name = info.filename
            if info.flag_bits & 0x1:
                problems.append(f"加密 ZIP: {name}")
            if name.startswith("/") or ".." in name.split("/"):
                problems.append(f"绝对路径或路径穿越: {name}")
            if "\\" in name:
                problems.append(f"反斜杠路径: {name}")
            if not name.isascii():
                problems.append(f"非 ASCII 文件名: {name}")
            if info.create_system == 3 and (info.external_attr >> 16) & 0o170000 == 0o120000:
                problems.append(f"符号链接: {name}")
            if info.create_system == 3 and ((info.external_attr >> 16) & 0o111):
                problems.append(f"依赖可执行位: {name}")
            low = name.lower()
            if low in seen_lower:
                problems.append(f"大小写冲突: {name} 与 {seen_lower[low]}")
            seen_lower[low] = name
            segs = name.split("/")
            if len(segs) > LIMITS["depth"]:
                problems.append(f"路径深度超限: {name}")
            for seg in segs:
                if not SEG_RE.match(seg):
                    problems.append(f"路径段不合规: {name}")
                if seg.split(".")[0].upper() in WIN_RESERVED:
                    problems.append(f"Windows 保留名: {name}")
            if len(name.encode("utf-8")) > LIMITS["path_bytes"]:
                problems.append(f"完整路径超限: {name}")
            for seg in segs:
                if len(seg.encode("utf-8")) > LIMITS["segment_bytes"]:
                    problems.append(f"路径段超限: {name}")
            if info.is_dir():
                continue
            file_count += 1
            size = info.file_size
            total_unpacked += size
            if size > LIMITS["single_file"]:
                problems.append(f"单文件超限: {name}")
            if size > max_file[1]:
                max_file = (name, size)
            if len(name.encode("utf-8")) > max_path[1]:
                max_path = (name, len(name.encode("utf-8")))
            for seg in segs:
                if len(seg.encode("utf-8")) > max_seg[1]:
                    max_seg = (seg, len(seg.encode("utf-8")))
            if len(segs) > max_depth[1]:
                max_depth = (name, len(segs))

    if file_count > LIMITS["files"]:
        problems.append(f"普通文件数超限: {file_count}")
    if total_unpacked > LIMITS["total"]:
        problems.append(f"解包总大小超限: {total_unpacked}")

    return {
        "zip_path": OUT,
        "zip_bytes": os.path.getsize(OUT),
        "entries": len(infos),
        "files": file_count,
        "unpacked_total_bytes": total_unpacked,
        "max_file": max_file,
        "max_path_bytes": max_path,
        "max_segment_bytes": max_seg,
        "max_depth": max_depth,
        "has_manifest_at_root": any(i.filename == ".minimax-plugin/plugin.json" for i in infos),
        "top_level_entries": sorted({i.filename.split("/")[0] for i in infos}),
        "problems": problems,
    }


def main() -> int:
    items = collect()
    src_problems = check_source(items) + check_icon(items)
    if src_problems:
        print("源检查未通过：")
        for p in src_problems:
            print("  -", p)
        return 1
    build(items)
    report = audit(items)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["problems"]:
        print("ZIP 自检未通过：")
        for p in report["problems"]:
            print("  -", p)
        return 1
    print("提交包自检通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
