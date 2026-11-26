# -*- coding: utf-8 -*-
"""3.10 严格解析器 ＋ 闭包越界判红：两条修复叠加后的行为。

两条修复落在同一个项目上：
- 3.10 那条：`factscribe/config.py::_mini_toml` 从宽松档转严格档，坏 TOML
  一律抛错（经 ConfigError → exit 2，配置错）；
- 广扫 F1：闭包目标越出项目根时记进 `cfg.outside_inputs`，audit 判红
  INPUT_OUTSIDE_PROJECT（exit 5，覆盖缺口）。

叠加后的口径：越界的 \\input 必须报 INPUT_OUTSIDE_PROJECT（exit 5），不许先被
TOML 解析器拒成 exit 2 的配置错 —— 那是两回事：配置错说的是「文件读不动」，
覆盖缺口说的是「有内容没进审计」，混成一个码就把缺口盖住了。

用例在任何解释器上都能跑：把 `factscribe.config._tomllib` 置空即可强制走 3.10
的兜底解析器路径（不必真有 3.10 解释器），与 tests/test_toml_compat.py 的
做法一致。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 强制 3.10 路径：tomllib 置空，load_toml 就走仓内兜底解析器 _mini_toml。
FORCE_310 = (
    "import sys\n"
    "import factscribe.config as c\n"
    "c._tomllib = None\n"
    "from factscribe.cli import main\n"
    "sys.argv = ['factscribe'] + sys.argv[1:]\n"
    "sys.exit(main())\n"
)

BIB_OK = """@inproceedings{chen2023,
  title = {A Paper},
  doi = {10.18653/v1/2023.emnlp-main.741}
}
"""

FACT_TOML = """[[fact]]
id = "A1"
claim = "开臂 resolved（16 题）"
value = "10/16"
source = "results/raw.md"
source_sha256 = "%s"
locator = "§二"
confidence = "high"
derived_from = []
"""


def make_project(root: Path, sections: dict[str, str],
                 facts_toml: str | None = None) -> Path:
    """最小 v1 项目（合法 TOML）；facts_toml 非空时用它替换事实账。"""
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    raw = root / "results" / "raw.md"
    raw.write_text("open 10/16 closed 8/16; total 56.25%\n", encoding="utf-8")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    (root / "facts" / "f.toml").write_text(
        facts_toml if facts_toml is not None else FACT_TOML % digest,
        encoding="utf-8")
    for name, text in sections.items():
        dest = root / "sections" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    (root / "refs.bib").write_text(BIB_OK, encoding="utf-8")
    (root / "factscribe.toml").write_text(
        '[project]\ntitle = "t"\nauthors = ["a"]\n'
        'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
        'bib = "refs.bib"\nbuild = ""\n', encoding="utf-8")
    (root / "results" / "MANIFEST.toml").write_text(
        "[manifest]\nsigned_by = \"test-human\"\n"
        "signed_at = \"2026-11-07T00:00:00Z\"\nversion = 1\n\n[files]\n"
        '"results/raw.md" = "%s"\n' % digest, encoding="utf-8")
    return root


def audit(root: Path, force_310: bool = False):
    cmd = ([sys.executable, "-c", FORCE_310] if force_310
           else [sys.executable, "-m", "factscribe"])
    proc = subprocess.run(cmd + ["audit", str(root), "--json"],
                          capture_output=True, text=True, cwd=str(ROOT))
    return proc


class TestToml310AndClosureOutside(unittest.TestCase):
    """3.10 严格解析器 ＋ add_ref 越界判红：叠加后的行为。"""

    def _outside_project(self, tmp: str) -> Path:
        root = make_project(Path(tmp) / "proj",
                            {"a.tex": "\\input{../../outside.tex}\n"
                                      "\\cite{chen2023}\n"})
        (Path(tmp) / "outside.tex").write_text(
            "\\section{外部节}\n这里有一个没进账的数字 987654321。\n",
            encoding="utf-8")
        return root

    def test_outside_input_is_red_under_310_parser(self):
        r"""3.10 路径：越界 \input 报 INPUT_OUTSIDE_PROJECT（exit 5）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._outside_project(tmp)
            proc = audit(root, force_310=True)
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            data = json.loads(proc.stdout)
            codes = [i["code"] for i in data["issues"]]
            self.assertEqual(codes, ["INPUT_OUTSIDE_PROJECT"], data)
            self.assertEqual(data["issues"][0]["severity"], "red")

    def test_outside_input_is_not_reported_as_toml_config_error(self):
        """不许先被 TOML 解析器拒成 exit 2 —— 那是配置错，不是覆盖缺口。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._outside_project(tmp)
            proc = audit(root, force_310=True)
            self.assertNotEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertNotIn("TOML 解析失败", proc.stdout + proc.stderr)

    def test_same_verdict_on_both_parser_paths(self):
        """3.10 兜底解析器与 3.11+ tomllib：同一份项目同一个结论。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._outside_project(tmp)
            p310 = audit(root, force_310=True)
            pstd = audit(root, force_310=False)
            self.assertEqual(p310.returncode, pstd.returncode)
            self.assertEqual(
                [i["code"] for i in json.loads(p310.stdout)["issues"]],
                [i["code"] for i in json.loads(pstd.stdout)["issues"]])

    def test_forced_310_path_really_uses_the_strict_parser(self):
        """对照：强制 3.10 路径下坏 TOML 必须 exit 2（不许放行）。

        这条锁住「上面几条确实跑在 _mini_toml 上」——否则越界用例可能是
        空转（根本没走兜底解析器）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp) / "proj",
                                {"a.tex": "\\cite{chen2023}\n"},
                                facts_toml='[[fact]\nid = "A1"\n')
            proc = audit(root, force_310=True)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("TOML 解析失败", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
