# -*- coding: utf-8 -*-
"""CARD-G5：双语双盘账本逐条比对（`factscribe mirror-check`）。

正负例成对：同一对双盘，改承重字段／删一条／改 bib 一律红（exit 1），
合法差异（单盘人签置信升级、sections 正文、main.tex 导言区、GLOSSARY.md
单盘独有件）一律不红（exit 0），结构错 exit 2。

判据口径见 CARD-G5 §3/§5 与 FACTS-SCHEMA.md §11.1（承重字段清单与
归一化口径）。本模块只服务 mirror-check 子命令，不改 audit/check 的判据
与退出码。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe import mirror                     # noqa: E402
from factscribe.config import ConfigError         # noqa: E402

CONFIG_TOML = """schema = "factscribe-project/3.0"

[project]
name = "Mirror Fixture"
root_tex = "main.tex"
facts = "facts"
bib = "refs.bib"
level = "l1"
"""

MAIN_TEX = """\\documentclass{article}
\\begin{document}
\\input{sections/01-intro.tex}
\\end{document}
"""

SECTION_TEX = """\\section{Introduction}
\\label{sec:intro}
The hit rate is \\fact{A1}{10/16} on the first run.
"""

BIB = """@article{smith2020,
  title     = {A Study of Things},
  author    = {Smith, John and Doe, Jane},
  year      = {2020},
  doi       = {10.1000/xyz123}
}

@misc{chen2021,
  title        = {Another Study},
  author       = {Chen, Li},
  year         = {2021},
  eprint       = {2101.00001},
  archivePrefix = {arXiv}
}
"""

FACTS_TOML = """schema = "factscribe-fact/3.0"

[[fact]]
id = "A1"
claim = "首次命中率"
value = "10/16"
source = "runs/run-01/summary.json"
source_sha256 = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
locator = "§二 表 1"
confidence = "med"
note = "首跑记录"

[[fact]]
id = "A2"
claim = "误红合计"
value = "0/36"
source = "runs/run-01/summary.json"
source_sha256 = "2222222222222222222222222222222222222222222222222222222222222222"
locator = "§二 汇总行"
confidence = "high"

[[fact]]
id = "B1"
claim = "派生量"
value = "5"
derived_from = ["A1"]
expr = "A1.num / A1.den"
source = "runs/run-01/summary.json"
source_sha256 = "3333333333333333333333333333333333333333333333333333333333333333"
confidence = "low"
"""


def make_disk(root: Path, *, facts: str = FACTS_TOML, bib: str = BIB,
              section: str = SECTION_TEX, main_tex: str = MAIN_TEX,
              glossary: bool = False) -> Path:
    """造一个最小可读的双语盘（够 mirror-check 读，不求能编译）。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (root / "main.tex").write_text(main_tex, encoding="utf-8")
    (root / "refs.bib").write_text(bib, encoding="utf-8")
    (root / "facts").mkdir(exist_ok=True)
    (root / "facts" / "01-core.toml").write_text(facts, encoding="utf-8")
    (root / "sections").mkdir(exist_ok=True)
    (root / "sections" / "01-intro.tex").write_text(section, encoding="utf-8")
    if glossary:
        (root / "GLOSSARY.md").write_text("# 术语表\n\n只在这一盘存在。\n",
                                         encoding="utf-8")
    return root


def run_mirror(disk_a: Path, disk_b: Path, *extra: str):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "factscribe", "mirror-check",
           str(disk_a), str(disk_b), *extra]
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          capture_output=True, text=True)


class MirrorFixture(unittest.TestCase):
    """基类：每个用例一对临时双盘。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def pair(self, **kw) -> tuple:
        a = make_disk(self.tmp / "paper-a", **kw)
        b = make_disk(self.tmp / "paper-b", **kw)
        return a, b


class TestCleanPairs(MirrorFixture):
    """正例：两侧一致或只有合法差异 → 零漂移（exit 0）。"""

    def test_identical_disks_have_no_drift(self):
        a, b = self.pair()
        result = mirror.check(a, b)
        self.assertEqual(result.drifts, [])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.facts_a, 3)
        self.assertEqual(result.facts_b, 3)
        self.assertEqual(result.bib_a, 2)
        self.assertEqual(result.bib_b, 2)

    def test_confidence_upgrade_in_one_disk_is_not_drift(self):
        """单盘人签置信升级是合法动作（CARD-G5 §3 豁免语义）。"""
        a, b = self.pair()
        upgraded = FACTS_TOML.replace('confidence = "med"', 'confidence = "high"')
        (b / "facts" / "01-core.toml").write_text(upgraded, encoding="utf-8")
        result = mirror.check(a, b)
        self.assertEqual(result.drifts, [])
        self.assertEqual(result.exit_code, 0)

    def test_note_difference_is_not_drift(self):
        """note 是自由备注，不在承重字段清单里。"""
        a, b = self.pair()
        changed = FACTS_TOML.replace('note = "首跑记录"', 'note = "改过的备注"')
        (b / "facts" / "01-core.toml").write_text(changed, encoding="utf-8")
        self.assertEqual(mirror.check(a, b).drifts, [])

    def test_sections_text_difference_is_not_drift(self):
        """正文翻译差异是合法差异（豁免面）。"""
        a, b = self.pair()
        (b / "sections" / "01-intro.tex").write_text(
            "\\section{引言}\n\\label{sec:intro}\n首次命中率为 \\fact{A1}{10/16}。\n",
            encoding="utf-8")
        self.assertEqual(mirror.check(a, b).drifts, [])

    def test_main_tex_preamble_difference_is_not_drift(self):
        """文档类与导言区差异（article vs ctexart）是合法差异。"""
        a, b = self.pair()
        (b / "main.tex").write_text(
            "\\documentclass{ctexart}\n\\begin{document}\n"
            "\\input{sections/01-intro.tex}\n\\end{document}\n",
            encoding="utf-8")
        self.assertEqual(mirror.check(a, b).drifts, [])

    def test_glossary_only_in_one_disk_is_not_drift(self):
        """GLOSSARY.md 是单盘独有件（豁免面）。"""
        a = make_disk(self.tmp / "paper-a")
        b = make_disk(self.tmp / "paper-b", glossary=True)
        self.assertEqual(mirror.check(a, b).drifts, [])

    def test_cli_exit_0_on_clean_pair(self):
        a, b = self.pair()
        proc = run_mirror(a, b)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("零漂移", proc.stdout)


class TestDriftDetection(MirrorFixture):
    """负例：承重字段漂移、条目缺失必须红（exit 1）并点名到 id/key。"""

    def test_value_drift_is_red_and_names_id(self):
        a, b = self.pair()
        changed = FACTS_TOML.replace('value = "10/16"', 'value = "11/16"')
        (b / "facts" / "01-core.toml").write_text(changed, encoding="utf-8")
        result = mirror.check(a, b)
        self.assertEqual(result.exit_code, 1)
        # value 与随之变化的 display（display 缺省回填 value，SPEC §11.1）都红。
        self.assertEqual([d.field for d in result.drifts], ["value", "display"])
        drift = result.drifts[0]
        self.assertEqual(drift.kind, "field")
        self.assertEqual(drift.target, "fact")
        self.assertEqual(drift.key, "A1")
        self.assertEqual(drift.field, "value")
        self.assertEqual(drift.a_value, "10/16")
        self.assertEqual(drift.b_value, "11/16")
        self.assertEqual(drift.code, mirror.CODE_FIELD_DRIFT)

    def test_claim_drift_is_red(self):
        a, b = self.pair()
        changed = FACTS_TOML.replace('claim = "首次命中率"',
                                     'claim = "首次命中率（改写）"')
        (b / "facts" / "01-core.toml").write_text(changed, encoding="utf-8")
        result = mirror.check(a, b)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.drifts[0].field, "claim")
        self.assertEqual(result.drifts[0].key, "A1")

    def test_source_sha256_drift_is_red(self):
        """同 id 不同源 sha＝不同物（卡片 §3 的判据口径）。"""
        a, b = self.pair()
        changed = FACTS_TOML.replace(
            "sha256:1111111111111111111111111111111111111111111111111111111111111111",
            "sha256:9999999999999999999999999999999999999999999999999999999999999999")
        (b / "facts" / "01-core.toml").write_text(changed, encoding="utf-8")
        result = mirror.check(a, b)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.drifts[0].field, "source_sha256")
        self.assertEqual(result.drifts[0].key, "A1")

    def test_sha256_prefix_form_is_not_drift(self):
        """`sha256:` 前缀可有可无（§11.1 归一化 2）——不算漂。"""
        a, b = self.pair()
        changed = FACTS_TOML.replace(
            "sha256:1111111111111111111111111111111111111111111111111111111111111111",
            "1111111111111111111111111111111111111111111111111111111111111111")
        (b / "facts" / "01-core.toml").write_text(changed, encoding="utf-8")
        self.assertEqual(mirror.check(a, b).drifts, [])

    def test_deleted_fact_is_missing_mirror(self):
        """删一条 fact → 缺镜像族报该 id。"""
        a, b = self.pair()
        without_b1 = FACTS_TOML.split("[[fact]]\nid = \"B1\"")[0]
        (b / "facts" / "01-core.toml").write_text(without_b1, encoding="utf-8")
        result = mirror.check(a, b)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(len(result.drifts), 1)
        drift = result.drifts[0]
        self.assertEqual(drift.kind, "missing")
        self.assertEqual(drift.key, "B1")
        self.assertEqual(drift.code, mirror.CODE_MISSING_MIRROR)
        self.assertTrue(drift.a_present)
        self.assertFalse(drift.b_present)

    def test_fact_only_in_disk_b_is_extra_mirror(self):
        a, b = self.pair()
        extra = FACTS_TOML + """
[[fact]]
id = "C9"
claim = "只在中盘"
value = "7"
source = "runs/run-01/summary.json"
source_sha256 = "4444444444444444444444444444444444444444444444444444444444444444"
confidence = "low"
"""
        (b / "facts" / "01-core.toml").write_text(extra, encoding="utf-8")
        result = mirror.check(a, b)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.drifts[0].kind, "extra")
        self.assertEqual(result.drifts[0].key, "C9")
        self.assertEqual(result.drifts[0].code, mirror.CODE_EXTRA_MIRROR)

    def test_bib_doi_drift_is_red_and_names_key(self):
        a, b = self.pair()
        changed = BIB.replace("10.1000/xyz123", "10.1000/xyz999")
        (b / "refs.bib").write_text(changed, encoding="utf-8")
        result = mirror.check(a, b)
        self.assertEqual(result.exit_code, 1)
        drift = result.drifts[0]
        self.assertEqual(drift.target, "bib")
        self.assertEqual(drift.key, "smith2020")
        self.assertEqual(drift.field, "doi")
        self.assertEqual(drift.a_value, "10.1000/xyz123")
        self.assertEqual(drift.b_value, "10.1000/xyz999")

    def test_bib_arxiv_drift_is_red(self):
        a, b = self.pair()
        changed = BIB.replace("eprint       = {2101.00001}",
                              "eprint       = {2101.00002}")
        (b / "refs.bib").write_text(changed, encoding="utf-8")
        result = mirror.check(a, b)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.drifts[0].key, "chen2021")
        self.assertEqual(result.drifts[0].field, "arxiv")

    def test_bib_arxiv_field_rename_is_not_drift(self):
        """eprint 与 arxiv 是同一个 arXiv id 的两种写法——不算漂。"""
        a, b = self.pair()
        changed = BIB.replace("eprint       = {2101.00001}",
                              "arxiv        = {2101.00001}")
        (b / "refs.bib").write_text(changed, encoding="utf-8")
        self.assertEqual(mirror.check(a, b).drifts, [])

    def test_bib_entry_only_in_disk_b_is_extra_mirror(self):
        a, b = self.pair()
        extra = BIB + """
@misc{zhao2022,
  title = {Third Study},
  author = {Zhao, Wei},
  year = {2022},
  doi = {10.1000/abc}
}
"""
        (b / "refs.bib").write_text(extra, encoding="utf-8")
        result = mirror.check(a, b)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.drifts[0].kind, "extra")
        self.assertEqual(result.drifts[0].key, "zhao2022")

    def test_cli_exit_1_and_reports_both_sides(self):
        a, b = self.pair()
        changed = FACTS_TOML.replace('value = "10/16"', 'value = "11/16"')
        (b / "facts" / "01-core.toml").write_text(changed, encoding="utf-8")
        proc = run_mirror(a, b)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("A1", proc.stdout)
        self.assertIn("value", proc.stdout)
        self.assertIn("10/16", proc.stdout)
        self.assertIn("11/16", proc.stdout)


class TestStructureErrors(MirrorFixture):
    """结构错不静默：exit 2 并说原因。"""

    def test_missing_facts_dir_raises_config_error(self):
        a = make_disk(self.tmp / "paper-a")
        b = make_disk(self.tmp / "paper-b")
        (b / "facts" / "01-core.toml").unlink()
        (b / "facts").rmdir()
        with self.assertRaises(ConfigError) as ctx:
            mirror.check(a, b)
        self.assertTrue(ctx.exception.code.startswith("MIRROR_"))

    def test_cli_exit_2_when_disk_has_no_facts_dir(self):
        a = make_disk(self.tmp / "paper-a")
        b = make_disk(self.tmp / "paper-b")
        (b / "facts" / "01-core.toml").unlink()
        (b / "facts").rmdir()
        proc = run_mirror(a, b)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("事实账", proc.stderr)

    def test_cli_exit_2_when_disk_missing(self):
        a = make_disk(self.tmp / "paper-a")
        proc = run_mirror(a, self.tmp / "nope")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_cli_exit_2_on_usage_error(self):
        """参数给少了 → 用法错 exit 2。"""
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        proc = subprocess.run([sys.executable, "-m", "factscribe", "mirror-check"],
                              cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)


class TestJsonPayload(MirrorFixture):
    """--json 形态：机器可读，漂移逐条可取。"""

    def test_json_payload_lists_drift_items(self):
        a, b = self.pair()
        changed = FACTS_TOML.replace('value = "10/16"', 'value = "11/16"')
        (b / "facts" / "01-core.toml").write_text(changed, encoding="utf-8")
        proc = run_mirror(a, b, "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["command"], "mirror-check")
        self.assertEqual(payload["exit"], 1)
        self.assertEqual(payload["status"], "drift")
        self.assertEqual(payload["summary"]["drift_count"], 2)
        item = payload["drift"][0]
        self.assertEqual(item["code"], mirror.CODE_FIELD_DRIFT)
        self.assertEqual(item["id"], "A1")
        self.assertEqual(item["field"], "value")
        self.assertEqual(item["disk_a"]["value"], "10/16")
        self.assertEqual(item["disk_b"]["value"], "11/16")

    def test_json_payload_on_clean_pair(self):
        a, b = self.pair()
        proc = run_mirror(a, b, "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["exit"], 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["drift"], [])
        self.assertEqual(payload["summary"]["facts_a"], 3)


if __name__ == "__main__":
    unittest.main()
