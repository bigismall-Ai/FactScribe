# -*- coding: utf-8 -*-
"""批 136：`factscribe fact add` 往账上追加一条事实。

契约面：

- 校验：id 不与现有重复（大小写不敏感）；`--source` 必须存在于项目内
  （v1：results/ 下）；
- **自动算 sha256** 写进 `source_sha256`；
- 追加到 `facts/01-core.toml`（没有就创建），**不覆盖**已有条目；
- 输出两行：已写入的 fact（id/claim/value）＋「该抄哪一行进人签清单」；
- **工具不代签**：人签清单一个字节都不改；
- 给了 `--derived-from` 就必须给 `--expr`，否则 exit 2。

另含一条端到端：init → fact add → check 能跑通并给出可读结论。

跑法（仓根）：env PYTHONPATH=src python3 -m unittest discover -s tests
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

from factscribe.config import load_config, load_facts, load_toml  # noqa: E402

MANIFEST_REL = "results/MANIFEST.toml"


def run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        capture_output=True, text=True, cwd=str(cwd or ROOT),
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))


def new_project(tmp: str, lang: str = "zh") -> Path:
    target = Path(tmp) / "proj"
    proc = run("init", str(target), "--title", "Demo", "--lang", lang)
    assert proc.returncode == 0, proc.stderr
    return target


def add(root: Path, *args):
    return run("fact", "add", str(root), *args)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestFactAddHappyPath(unittest.TestCase):
    """正常添加：字段落位、sha256 自动算、输出两行提示。"""

    def test_appends_first_fact_with_all_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            proc = add(root, "--id", "A1", "--claim", "示例",
                       "--value", "3/4", "--source", MANIFEST_REL,
                       "--locator", "§一", "--confidence", "high")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            facts = load_facts(load_config(root))
            self.assertEqual(len(facts), 1)
            f = facts[0]
            self.assertEqual(f.id, "A1")
            self.assertEqual(f.claim, "示例")
            self.assertEqual(f.value, "3/4")
            self.assertEqual(f.source, MANIFEST_REL)
            self.assertEqual(f.locator, "§一")
            self.assertEqual(f.confidence, "high")
            self.assertEqual(f.derived_from, [])

    def test_sha256_is_computed_from_the_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            raw = root / "results" / "swb16.md"
            raw.write_text("open 10/16\nclosed 8/16\n", encoding="utf-8")
            proc = add(root, "--id", "A1", "--claim", "开臂",
                       "--value", "10/16", "--source", "results/swb16.md",
                       "--locator", "§二")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            f = load_facts(load_config(root))[0]
            self.assertEqual(f.source_sha256, sha(raw))
            self.assertIn(sha(raw), proc.stdout)

    def test_locator_is_optional(self):
        """验收命令里没带 --locator——它不能是必需参数（但建议填）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            proc = add(root, "--id", "A1", "--claim", "c", "--value", "1",
                       "--source", MANIFEST_REL)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(load_facts(load_config(root))[0].locator, "")

    def test_confidence_defaults_to_med(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            self.assertEqual(add(root, "--id", "A1", "--claim", "c",
                                 "--value", "1", "--source", MANIFEST_REL,
                                 "--locator", "x").returncode, 0)
            self.assertEqual(load_facts(load_config(root))[0].confidence, "med")

    def test_prints_two_hints_and_never_signs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            before = (root / MANIFEST_REL).read_bytes()
            proc = add(root, "--id", "A1", "--claim", "示例",
                       "--value", "3/4", "--source", MANIFEST_REL,
                       "--locator", "§一")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
            self.assertEqual(len(lines), 2, proc.stdout)
            self.assertIn("A1", lines[0])
            self.assertIn("示例", lines[0])
            self.assertIn("3/4", lines[0])
            self.assertIn("别忘了", lines[1])
            self.assertIn(MANIFEST_REL, lines[1])
            self.assertIn(sha(root / MANIFEST_REL), lines[1])
            # 「不代签」：清单逐字节未动，[files] 里没被偷偷塞进一行
            self.assertEqual((root / MANIFEST_REL).read_bytes(), before)
            self.assertEqual(load_toml(root / MANIFEST_REL)["files"], {})

    def test_creates_ledger_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            (root / "facts" / "01-core.toml").unlink()
            proc = add(root, "--id", "A1", "--claim", "c", "--value", "1",
                       "--source", MANIFEST_REL, "--locator", "x")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((root / "facts" / "01-core.toml").is_file())
            self.assertEqual(len(load_facts(load_config(root))), 1)

    def test_json_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            proc = add(root, "--id", "A1", "--claim", "示例", "--value", "3/4",
                       "--source", MANIFEST_REL, "--locator", "§一", "--json")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual(data["command"], "fact")
            self.assertEqual(data["action"], "add")
            self.assertEqual(data["id"], "A1")
            self.assertEqual(data["source"], MANIFEST_REL)
            self.assertIn("manifest_line", data)


class TestFactAddAppendOnly(unittest.TestCase):
    """追加不覆盖：第二条只加在末尾，第一条逐字节不动。"""

    def test_second_fact_keeps_the_first_block_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            add(root, "--id", "A1", "--claim", "第一条", "--value", "10/16",
                "--source", MANIFEST_REL, "--locator", "§二")
            first_text = (root / "facts" / "01-core.toml").read_text(encoding="utf-8")
            add(root, "--id", "A3", "--claim", "第二条", "--value", "8/16",
                "--source", MANIFEST_REL, "--locator", "§二")
            second_text = (root / "facts" / "01-core.toml").read_text(encoding="utf-8")
            self.assertTrue(second_text.startswith(first_text), second_text)
            facts = load_facts(load_config(root))
            self.assertEqual([f.id for f in facts], ["A1", "A3"])
            self.assertEqual([f.claim for f in facts], ["第一条", "第二条"])

    def test_derived_fact_records_parents_and_expr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            add(root, "--id", "A1", "--claim", "a", "--value", "10/16",
                "--source", MANIFEST_REL, "--locator", "x")
            add(root, "--id", "A3", "--claim", "b", "--value", "8/16",
                "--source", MANIFEST_REL, "--locator", "x")
            proc = add(root, "--id", "A2", "--claim", "合计", "--value", "56.25%",
                       "--source", MANIFEST_REL, "--locator", "§三",
                       "--derived-from", "A1,A3",
                       "--expr", "(A1.num + A3.num) / (A1.den + A3.den) * 100")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            f = {x.id: x for x in load_facts(load_config(root))}["A2"]
            self.assertEqual(f.derived_from, ["A1", "A3"])
            self.assertIn("A1.num", f.expr)
            self.assertTrue(f.is_derived)

    def test_note_is_written_when_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            add(root, "--id", "A1", "--claim", "c", "--value", "1",
                "--source", MANIFEST_REL, "--locator", "x", "--note", "备注一句")
            self.assertEqual(load_facts(load_config(root))[0].note, "备注一句")


class TestFactAddRefusals(unittest.TestCase):
    """校验失败一律 exit 2，且账本不被写坏。"""

    def test_duplicate_id_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            base = ("--claim", "c", "--value", "1", "--source", MANIFEST_REL,
                    "--locator", "x")
            self.assertEqual(add(root, "--id", "A1", *base).returncode, 0)
            before = (root / "facts" / "01-core.toml").read_bytes()
            proc = add(root, "--id", "A1", "--claim", "dup", "--value", "2",
                       "--source", MANIFEST_REL, "--locator", "y")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("已存在", proc.stderr)
            self.assertEqual((root / "facts" / "01-core.toml").read_bytes(), before)

    def test_duplicate_id_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            add(root, "--id", "a1", "--claim", "c", "--value", "1",
                "--source", MANIFEST_REL, "--locator", "x")
            proc = add(root, "--id", "A1", "--claim", "c", "--value", "1",
                       "--source", MANIFEST_REL, "--locator", "x")
            self.assertEqual(proc.returncode, 2)

    def test_missing_source_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            proc = add(root, "--id", "A1", "--claim", "c", "--value", "1",
                       "--source", "results/nope.md", "--locator", "x")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("不存在", proc.stderr)
            self.assertEqual(load_facts(load_config(root)), [])

    def test_source_outside_results_is_refused(self):
        """v1 的 source 只许在 results/ 下——否则 check 必红，别写进账。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            (root / "data.md").write_text("10/16\n", encoding="utf-8")
            proc = add(root, "--id", "A1", "--claim", "c", "--value", "10/16",
                       "--source", "data.md", "--locator", "x")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("results/", proc.stderr)

    def test_absolute_source_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            proc = add(root, "--id", "A1", "--claim", "c", "--value", "1",
                       "--source", str(root / MANIFEST_REL), "--locator", "x")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("相对路径", proc.stderr)

    def test_derived_from_without_expr_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            proc = add(root, "--id", "A2", "--claim", "c", "--value", "1",
                       "--source", MANIFEST_REL, "--locator", "x",
                       "--derived-from", "A1,A3")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("--expr", proc.stderr)
            self.assertEqual(load_facts(load_config(root)), [])

    def test_bad_id_format_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            proc = add(root, "--id", "1A", "--claim", "c", "--value", "1",
                       "--source", MANIFEST_REL, "--locator", "x")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("不合法", proc.stderr)

    def test_bad_confidence_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            proc = add(root, "--id", "A1", "--claim", "c", "--value", "1",
                       "--source", MANIFEST_REL, "--locator", "x",
                       "--confidence", "certain")
            self.assertEqual(proc.returncode, 2)


class TestInitAddCheckEndToEnd(unittest.TestCase):
    """端到端：init → fact add → check 跑通，给出可读结论与原因。"""

    def test_init_add_then_check_speaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            added = add(root, "--id", "A1", "--claim", "示例", "--value", "3/4",
                        "--source", MANIFEST_REL, "--locator", "§一")
            self.assertEqual(added.returncode, 0, added.stderr)
            proc = run("check", str(root))
            # check 是判据命令：0 绿 / 1 红 / 3 黄；这里只要求它「真的跑完」，
            # 不是 2（配置坏）也不是 4（工具内部错误）。
            self.assertIn(proc.returncode, (0, 1, 3), proc.stdout + proc.stderr)
            self.assertIn("== paperkit check ==", proc.stdout)
            self.assertIn("结论：", proc.stdout)
            self.assertIn("facts   : 1 条", proc.stdout)
            # 现在应报的正是「清单没人签」与「value 不在 source 里」：
            self.assertIn("MANIFEST_UNSIGNED", proc.stdout)
            self.assertIn("VALUE_NOT_IN_SOURCE", proc.stdout)
            self.assertIn("退出码 %d" % proc.returncode, proc.stdout)


if __name__ == "__main__":
    unittest.main()
