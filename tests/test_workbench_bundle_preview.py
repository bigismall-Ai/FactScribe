# -*- coding: utf-8 -*-
"""投稿包导出前的**可选预览**（清单给出去，一个字节都不写）。

这一组钉四件事：

1. **口径与真导出同源**：预览里每一件的路径/指纹/大小，与真导出写进包里的
   逐字一致（同一条 ``_artifact_bytes`` 路）。
2. **判定权仍在清单门**：门不过 → 预览说 ``would_export=False``，理由与真
   导出**同一个**；真导出照样不出包。预览不改导出口径，只把结论先给人看。
3. **预览是可选的一步**：预览不写盘（包目录压根不出现）。
4. **既有导出语义不变**：真导出该收什么收什么、门不过照样 exit_code=1。

跑法（仓根）：python3 -m pytest tests/test_workbench_bundle_preview.py -q
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import load_config  # noqa: E402
from factscribe.bundle import run_bundle  # noqa: E402
from factscribe.workbench.actions import export_bundle, preview_bundle  # noqa: E402

MINIMAL = ROOT / "examples" / "minimal"

GHOST_BIB = (
    "\n@article{ghost2024,\n"
    "  title = {A Ghost Reference},\n"
    "  author = {Ghost, A.},\n"
    "  journal = {J. Ghost},\n"
    "  year = {2024},\n"
    "  doi = {10.0000/ghost2024}\n"
    "}\n"
)


def make_disk(root: Path, gate_passes: bool) -> Path:
    """造一个测试盘。gate_passes=True 时把样例盘那两处红修掉（门才过）。"""
    disk = root / "paper"
    shutil.copytree(MINIMAL, disk)
    if not gate_passes:
        return disk
    bib = disk / "refs.bib"
    bib.write_text(bib.read_text(encoding="utf-8") + GHOST_BIB,
                   encoding="utf-8")
    res = disk / "sections" / "02-results.tex"
    res.write_text(res.read_text(encoding="utf-8").replace("47.3", "10"),
                   encoding="utf-8")
    return disk


class BundlePreviewTests(unittest.TestCase):
    """导出前预览：只算不写，判定权仍在清单门。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-bundle-preview-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_gate_fails_preview_says_so_and_nothing_is_written(self):
        disk = make_disk(self.tmp, gate_passes=False)
        preview = preview_bundle(disk)
        self.assertTrue(preview["ok"])
        self.assertFalse(preview["would_export"], "门不过就不该说会导出")
        self.assertGreater(preview["failed"], 0)
        self.assertEqual(preview["exit_code"], 1)
        # 预览一个字节都不写：包目录压根不出现
        self.assertFalse(Path(str(preview["bundle_dir"])).exists())
        # 真导出：同一个结论，照样不出包
        out = export_bundle(disk)
        self.assertFalse(out["ok"])
        self.assertEqual(out["exit_code"], 1)
        self.assertEqual(out["error"], preview["failure_reason"])
        self.assertFalse(Path(str(out["bundle_dir"])).exists())

    def test_preview_matches_the_exported_bundle_byte_for_byte(self):
        disk = make_disk(self.tmp, gate_passes=True)
        preview = preview_bundle(disk)
        self.assertTrue(preview["would_export"], preview.get("failure_reason"))
        self.assertEqual(preview["failed"], 0)
        self.assertGreater(preview["file_count"], 0)
        self.assertFalse(Path(str(preview["bundle_dir"])).exists(),
                         "预览不写盘")

        out = export_bundle(disk)
        self.assertTrue(out["ok"], out.get("error"))
        bundle = Path(str(out["bundle_dir"]))
        self.assertTrue(bundle.is_dir())
        for entry in preview["files"]:
            path = bundle / entry["path"]
            self.assertTrue(path.is_file(), "包里少了一件：%s" % entry["path"])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, entry["sha256"],
                             "预览与真导出必须逐字一致：%s" % entry["path"])
            self.assertEqual(path.stat().st_size, entry["bytes"])

    def test_preview_does_not_change_the_export_verdict(self):
        """先预览再导出：两次结论必须一模一样（预览不许改口径）。"""
        disk = make_disk(self.tmp, gate_passes=True)
        first = preview_bundle(disk)
        second = preview_bundle(disk)
        self.assertEqual(first["would_export"], second["would_export"])
        self.assertEqual(first["failed"], second["failed"])
        self.assertEqual([f["sha256"] for f in first["files"]],
                         [f["sha256"] for f in second["files"]])
        out = export_bundle(disk)
        self.assertTrue(out["ok"])
        self.assertEqual(out["exit_code"], first["exit_code"])

    def test_run_bundle_preview_writes_nothing(self):
        disk = make_disk(self.tmp, gate_passes=True)
        cfg = load_config(disk)
        out_dir = self.tmp / "out"
        result = run_bundle(cfg, out_dir=out_dir, preview=True)
        self.assertTrue(result["preview"])
        self.assertTrue(result["would_export"])
        self.assertFalse(out_dir.exists(), "预览一个字节都不写")
        self.assertGreater(len(result["files"]), 0)


if __name__ == "__main__":
    unittest.main()
