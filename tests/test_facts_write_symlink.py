# -*- coding: utf-8 -*-
"""写侧软链信任根闸：写入落点越出项目根就拒写，界内照旧。

被测口径（SPEC-V3.0 §8.1 的事实账信任根规则，写侧那一半）：

- 事实账的写入落点（`facts/*.toml` 本身，或它所在的目录）经软链解析后
  越出项目根 → **拒绝写入**：`FACT_FILE_OUTSIDE_PROJECT`（red，exit 5，
  与读侧同一码）；软链成环 → `FACT_FILE_UNRESOLVED`（red，exit 5，
  与读侧同一码）。都不是 traceback，也不是 exit 4。
- 拒绝时**不留半截状态**：不删、不覆盖原文件；项目外一个字节都不写；
  临时文件（`.tmp-*`）与 `.bak` 之类的旁路文件也不许落在项目外。
- 正例锁：正常项目、以及指向项目内的软链，行为与修前逐字节一致
  （项目内软链：内容落在软链的真实目标上，软链本身不变）。

同族缺口（其它项目内写盘路径）也一并收口：图表产物、证据冻结件、
待补文献登记表、候选落盘目录、项目声明、矩阵/前言产物——落点越界一律
拒写（`PATH_ESCAPE`，exit 2；这些不是事实账，是另一个对象，不套事实账的码）。

跑法（仓根）：python3 -m unittest discover -s tests
"""
from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import load_config, load_facts  # noqa: E402

MANIFEST_REL = "results/MANIFEST.toml"

FIG_SPEC_TOML = """name = "acc"
kind = "bar"
caption = "两臂在同一组题上的解决数"
xlabel = "臂"
ylabel = "解决比例"
data = ["A1"]
labels = ["开臂"]
"""

FIG_FACT_TOML = """[[fact]]
id = "A1"
claim = "开臂 resolved"
value = "10/16"
source = "results/raw.md"
source_sha256 = "sha256:%s"
locator = "§二"
confidence = "high"
"""


def run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        capture_output=True, text=True, cwd=str(cwd or ROOT),
        env=dict(os.environ, PYTHONPATH=str(ROOT)))


def new_project(tmp: str) -> Path:
    """最小 v1 项目（`init` 落骨架，同参数逐字节一致）。

    段落级线改写说明：main 的 `fact add` **没有**写前的 value 硬闸，
    用例里的 `--value 10/16` 直接写进账。段落级线有 value 硬闸（
    `factscribe/valuecheck.py`：value 里的数字必须在它所指的产物原文里
    逐个按序命中）——这是本线**更严**的已定口径，不是缺陷，保留不动。

    为了让这组用例仍然测「写侧落点闸的界内正例」（而不是被 value 硬闸
    先拦下），这里在骨架的 `results/` 下放一份**含 10 与 16 的产物**：
    value 硬闸据此放行，用例的落点断言一条不减。
    """
    target = Path(tmp) / "proj"
    proc = run("init", str(target), "--title", "Demo", "--lang", "zh")
    assert proc.returncode == 0, proc.stderr
    # 把 10 与 16 写进清单本身（清单就是这组用例 --source 指的文件），
    # value 硬闸据此放行：value「10/16」的两个数字能在源产物里按序命中。
    manifest = target / "results" / "MANIFEST.toml"
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(text + "# 示例：开臂解决 10 道题，对照臂解决 16 道题\n",
                        encoding="utf-8")
    return target


def fact_add(root: Path, *args):
    return run("fact", "add", str(root), *args)


def link(target: Path, link_path: Path) -> None:
    """建软链；建不了（Windows 未开开发者模式等）就跳过用例，不许假装通过。"""
    try:
        os.symlink(str(target), str(link_path))
    except (OSError, NotImplementedError, AttributeError) as exc:
        raise unittest.SkipTest("本机不能建软链：%s" % exc)


def snapshot(base: Path) -> dict:
    """目录快照：普通文件 → 字节；软链 → 链接目标；目录 → 名单。

    用来证明「项目外没有任何文件被创建或修改」——多一个 .tmp-* 或 .bak
    之类的旁路文件，这一项就不相等。
    """
    files, links, dirs = {}, {}, []
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(base).as_posix()
        if path.is_symlink():
            links[rel] = os.readlink(str(path))
        elif path.is_dir():
            dirs.append(rel)
        else:
            files[rel] = path.read_bytes()
    return {"files": files, "links": links, "dirs": dirs}


def last_json(text: str) -> dict:
    text = text.strip()
    assert text, "stdout 是空的"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return json.loads(lines[-1])


class TestFactsWriteOutside(unittest.TestCase):
    """写侧越界三类输入：必须拒绝、不得落盘到项目外、不得留下半截文件。"""

    def test_ledger_file_symlink_outside_is_refused(self):
        """账本文件是指向项目外的软链 → 拒写，项目外一个字节都不动。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = new_project(tmp)
            outside = base / "outside-ledger.toml"
            outside.write_text("# 项目外的账本\n", encoding="utf-8")
            ledger = root / "facts" / "01-core.toml"
            ledger.unlink()
            link(outside, ledger)
            before = snapshot(base)
            proc = fact_add(root, "--id", "A1", "--claim", "越界不许写",
                            "--value", "10/16", "--source", MANIFEST_REL,
                            "--json")
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertNotEqual(proc.returncode, 4, "不许退成工具内部错误")
            payload = last_json(proc.stdout)
            self.assertEqual(payload["code"], "FACT_FILE_OUTSIDE_PROJECT")
            self.assertEqual(payload["exit"], 5)
            self.assertEqual(payload["findings"][0]["code"],
                             "FACT_FILE_OUTSIDE_PROJECT")
            self.assertEqual(snapshot(base), before,
                             "项目外有文件被创建或修改")

    def test_facts_dir_symlink_outside_is_refused(self):
        """facts/ 整个是指向项目外的软链 → 新账本会落在项目外，拒写。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = new_project(tmp)
            out_dir = base / "outside-facts"
            out_dir.mkdir()
            shutil.rmtree(root / "facts")
            link(out_dir, root / "facts")
            before = snapshot(base)
            proc = fact_add(root, "--id", "A1", "--claim", "越界不许写",
                            "--value", "10/16", "--source", MANIFEST_REL,
                            "--json")
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertEqual(last_json(proc.stdout)["code"],
                             "FACT_FILE_OUTSIDE_PROJECT")
            self.assertEqual(list(out_dir.iterdir()), [],
                             "项目外被写了文件")
            self.assertEqual(snapshot(base), before)

    def test_broken_symlink_outside_creates_nothing(self):
        """断链软链指向项目外 → 写下去会把项目外的文件凭空造出来，拒写。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = new_project(tmp)
            ghost = base / "ghost-ledger.toml"
            ledger = root / "facts" / "01-core.toml"
            ledger.unlink()
            link(ghost, ledger)
            before = snapshot(base)
            proc = fact_add(root, "--id", "A1", "--claim", "越界不许写",
                            "--value", "10/16", "--source", MANIFEST_REL,
                            "--json")
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertEqual(last_json(proc.stdout)["code"],
                             "FACT_FILE_OUTSIDE_PROJECT")
            self.assertFalse(ghost.exists(), "项目外被凭空造出了文件")
            self.assertEqual(snapshot(base), before)

    def test_symlink_loop_is_refused_as_unresolved(self):
        """成环软链：真实落点算不出来 → 明确报出，不许退成 exit 4。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = new_project(tmp)
            ledger = root / "facts" / "01-core.toml"
            ledger.unlink()
            link(ledger, ledger)
            before = snapshot(base)
            proc = fact_add(root, "--id", "A1", "--claim", "成环不许写",
                            "--value", "10/16", "--source", MANIFEST_REL,
                            "--json")
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertNotEqual(proc.returncode, 4)
            self.assertEqual(last_json(proc.stdout)["code"],
                             "FACT_FILE_UNRESOLVED")
            self.assertEqual(snapshot(base), before)

    def test_workbench_add_fact_refuses_outside(self):
        """工作台／MCP 那个入口也拒写（同一个 add_fact，码与退出码一致）。"""
        from factscribe.config import ConfigError
        from factscribe.workbench import add_fact_data
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = new_project(tmp)
            outside = base / "outside-ledger.toml"
            outside.write_text("# 项目外的账本\n", encoding="utf-8")
            ledger = root / "facts" / "01-core.toml"
            ledger.unlink()
            link(outside, ledger)
            before = snapshot(base)
            with self.assertRaises(ConfigError) as ctx:
                add_fact_data(root, {"id": "A1", "claim": "越界不许写",
                                     "value": "10/16",
                                     "source": MANIFEST_REL}, allow_write=True)
            self.assertEqual(getattr(ctx.exception, "code", ""),
                             "FACT_FILE_OUTSIDE_PROJECT")
            self.assertEqual(getattr(ctx.exception, "exit_code", None), 5)
            self.assertEqual(snapshot(base), before)

    def test_broken_facts_dir_symlink_is_refused_not_internal_error(self):
        """facts/ 是断链软链：落点不可解 → 明确报出，不许退成 exit 4。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = new_project(tmp)
            shutil.rmtree(root / "facts")
            link(base / "nowhere" / "facts", root / "facts")
            before = snapshot(base)
            proc = fact_add(root, "--id", "A1", "--claim", "断链不许写",
                            "--value", "10/16", "--source", MANIFEST_REL,
                            "--json")
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertNotEqual(proc.returncode, 4)
            self.assertEqual(last_json(proc.stdout)["code"],
                             "FACT_FILE_UNRESOLVED")
            self.assertEqual(snapshot(base), before)

    def test_refusal_message_is_readable_and_leaves_no_half_state(self):
        """人读模式的错误形态：说清落点与「没落盘」，不是 traceback。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = new_project(tmp)
            outside = base / "outside-ledger.toml"
            outside.write_text("# 项目外的账本\n", encoding="utf-8")
            ledger = root / "facts" / "01-core.toml"
            ledger.unlink()
            link(outside, ledger)
            before = snapshot(base)
            proc = fact_add(root, "--id", "A1", "--claim", "越界不许写",
                            "--value", "10/16", "--source", MANIFEST_REL)
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertIn("越出项目根", proc.stderr)
            self.assertIn("拒绝写入", proc.stderr)
            # 原文件既没被删也没被改；项目外没有多出 .bak/.tmp 之类旁路文件
            self.assertEqual(snapshot(base), before)
            self.assertTrue(outside.is_file())


class TestFactsWriteInside(unittest.TestCase):
    """正例：正常项目与项目内软链，行为一字不变。"""

    def test_plain_project_writes_the_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            proc = fact_add(root, "--id", "A1", "--claim", "示例",
                            "--value", "10/16", "--source", MANIFEST_REL)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            facts = load_facts(load_config(root))
            self.assertEqual([f.id for f in facts], ["A1"])

    def test_in_project_symlink_keeps_its_shape(self):
        """项目内软链：内容落在软链的真实目标上，软链本身不变。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            ledger = root / "facts" / "01-core.toml"
            real = root / "facts" / "real-core.toml"
            ledger.unlink()
            link(real, ledger)
            proc = fact_add(root, "--id", "A1", "--claim", "示例",
                            "--value", "10/16", "--source", MANIFEST_REL)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(ledger.is_symlink(), "软链被写成了普通文件")
            self.assertEqual(os.readlink(str(ledger)), str(real))
            # 内容落在软链的真实目标上（glob 会同时看到软链与真实文件，
            # 那是读侧的口径，不在本用例断言范围内）
            self.assertIn('id = "A1"', real.read_text(encoding="utf-8"))

    def test_in_project_symlink_content_matches_plain_write(self):
        """正例锁：项目内软链写出来的内容与「同内容的普通文件」逐字节相同。"""
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            plain = new_project(tmp_a)
            proc = fact_add(plain, "--id", "A1", "--claim", "示例",
                            "--value", "10/16", "--source", MANIFEST_REL)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            linked = new_project(tmp_b)
            ledger = linked / "facts" / "01-core.toml"
            real = linked / "facts" / "real-core.toml"
            ledger.unlink()
            link(real, ledger)
            proc = fact_add(linked, "--id", "A1", "--claim", "示例",
                            "--value", "10/16", "--source", MANIFEST_REL)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(real.read_bytes(),
                             (plain / "facts" / "01-core.toml").read_bytes())

    def test_in_project_dir_symlink_writes_through(self):
        """项目内的目录软链：照旧写进去（落点还在项目根内）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            data = root / "data"
            (data / "facts").mkdir(parents=True)
            shutil.rmtree(root / "facts")
            link(data / "facts", root / "facts")
            proc = fact_add(root, "--id", "A1", "--claim", "示例",
                            "--value", "10/16", "--source", MANIFEST_REL)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            written = data / "facts" / "01-core.toml"
            self.assertTrue(written.is_file())
            self.assertIn('id = "A1"', written.read_text(encoding="utf-8"))


class TestFactImportOutside(unittest.TestCase):
    """`fact import` 的落点闸：写出去的账本文件也不许落在项目外。"""

    def test_import_into_outside_symlinked_dir_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ws = base / "ws"
            (ws / "experiments" / "e" / "raw").mkdir(parents=True)
            (ws / "reports").mkdir(parents=True)
            paper = ws / "paper"
            (paper / "sections").mkdir(parents=True)
            (paper / "facts").mkdir(parents=True)
            (paper / "factscribe.toml").write_text(
                '[project]\ntitle = "t"\nsections = "sections/*.tex"\n'
                'facts = "facts/*.toml"\nsource_root = "../experiments/e/raw"\n',
                encoding="utf-8")
            (paper / "refs.bib").write_text("", encoding="utf-8")
            (paper / "sections" / "01-intro.tex").write_text(
                "本节没有数字。\n", encoding="utf-8")
            raw = ws / "experiments" / "e" / "raw"
            (raw / "result.json").write_text(
                json.dumps({"run": "r1", "summary": {"rate": 56.25}}),
                encoding="utf-8")
            report = ws / "reports" / "r.report.toml"
            report.write_text(
                'schema = "factscribe/report@1"\nid = "r"\n'
                'experiment = "e"\nstatus = "final"\n'
                'generated_at = "2026-11-06T10:00:00Z"\n'
                'population = { id = "p" }\n\n'
                '[[metric]]\nid = "open.rate"\nclaim = "开臂准确率"\n'
                'value = "56.25"\nvalue_type = "percent"\nprecision = 2\n'
                'display = "56.25%"\nsources = [\n'
                '  { role = "value", path = "experiments/e/raw/result.json",'
                ' probe = "json.pointer", pointer = "/summary/rate" },\n]\n',
                encoding="utf-8")
            self.assertEqual(run("report", "lock", str(ws),
                                 "--report", str(report)).returncode, 0)
            self.assertEqual(run("report", "sign", str(ws),
                                 "--report", str(report),
                                 "--by", "测试员").returncode, 0)
            out_dir = base / "outside-facts"
            out_dir.mkdir()
            shutil.rmtree(paper / "facts")
            link(out_dir, paper / "facts")
            before = snapshot(base)
            proc = run("fact", "import", str(ws), "--report", str(report),
                       "--json")
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertEqual(last_json(proc.stdout)["error"]["code"],
                             "FACT_FILE_OUTSIDE_PROJECT")
            self.assertEqual(list(out_dir.iterdir()), [],
                             "项目外被写了文件")
            self.assertEqual(snapshot(base), before)


class TestOtherProjectWrites(unittest.TestCase):
    """同族缺口：其它项目内写盘路径的落点闸（PATH_ESCAPE，exit 2）。"""

    def make_fig_project(self, root: Path) -> Path:
        import hashlib
        root.mkdir(parents=True, exist_ok=True)
        (root / "factscribe.toml").write_text(
            '[project]\ntitle = "t"\nsections = "sections/*.tex"\n'
            'facts = "facts/*.toml"\nbib = "refs.bib"\nbuild = ""\n',
            encoding="utf-8")
        (root / "refs.bib").write_text("", encoding="utf-8")
        (root / "sections").mkdir(exist_ok=True)
        (root / "sections" / "01-intro.tex").write_text(
            "开臂解决 10 道。\n", encoding="utf-8")
        (root / "results").mkdir(exist_ok=True)
        raw = root / "results" / "raw.md"
        raw.write_text("open 10 of 16\n", encoding="utf-8")
        digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        (root / "facts").mkdir(exist_ok=True)
        (root / "facts" / "01-core.toml").write_text(
            FIG_FACT_TOML % digest, encoding="utf-8")
        (root / "figures").mkdir(exist_ok=True)
        (root / "figures" / "acc.fig.toml").write_text(FIG_SPEC_TOML,
                                                       encoding="utf-8")
        return root

    def test_figures_products_outside_are_refused(self):
        from factscribe.config import ConfigError
        from factscribe.figures import generate
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_fig_project(base / "proj")
            out_dir = base / "outside-figures"
            out_dir.mkdir()
            shutil.rmtree(root / "figures" / "gen", ignore_errors=True)
            link(out_dir, root / "figures" / "gen")
            before = snapshot(base)
            with self.assertRaises(ConfigError) as ctx:
                generate(root)
            self.assertEqual(getattr(ctx.exception, "code", ""),
                             "PATH_ESCAPE")
            self.assertEqual(list(out_dir.iterdir()), [],
                             "项目外被写了文件")
            self.assertEqual(snapshot(base), before)

    def test_evidence_lock_outside_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = new_project(tmp)
            out_dir = base / "outside-audit"
            out_dir.mkdir()
            link(out_dir, root / "audit")
            before = snapshot(base)
            proc = run("evidence", "--freeze", str(root), "--json")
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertNotEqual(proc.returncode, 4)
            self.assertEqual(list(out_dir.iterdir()), [],
                             "项目外被写了文件")
            self.assertEqual(snapshot(base), before)

    def test_init_skeleton_outside_symlink_is_refused(self):
        """init 落骨架时落点不许越出项目根（账本那条是软链就拒写）。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "newproj"
            (target / "facts").mkdir(parents=True)
            outside = base / "outside-init.toml"
            outside.write_text("ORIGINAL\n", encoding="utf-8")
            link(outside, target / "facts" / "01-core.toml")
            before = snapshot(base)
            proc = run("init", str(target), "--force", "--title", "D",
                       "--lang", "zh", "--json")
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertNotEqual(proc.returncode, 4, "不许退成工具内部错误")
            self.assertEqual(last_json(proc.stdout)["code"],
                             "FACT_FILE_OUTSIDE_PROJECT")
            self.assertEqual(snapshot(base), before,
                             "项目外有文件被创建或修改")

    def test_build_font_patch_outside_is_refused(self):
        """构建的字体补丁不许写到项目外（入口文件是软链指到项目外时）。"""
        from factscribe.buildpdf import _write_font_patch
        from factscribe.config import ConfigError
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = new_project(tmp)
            outside = base / "outside-main.tex"
            outside.write_text("\\documentclass{article}\n", encoding="utf-8")
            entry = root / "main.tex"
            entry.unlink()
            link(outside, entry)
            work = base / "build"
            work.mkdir()
            copy = work / "main.tex"
            # copytree(symlinks=True) 的效果：副本原样保留这条软链
            link(outside, copy)
            before = outside.read_bytes()
            with self.assertRaises(ConfigError) as ctx:
                _write_font_patch(root, "main.tex", copy, "patched\n")
            self.assertEqual(getattr(ctx.exception, "code", ""),
                             "PATH_ESCAPE")
            self.assertEqual(outside.read_bytes(), before,
                             "项目外被写了文件")

    def test_refs_todo_outside_is_refused(self):
        from factscribe.config import ConfigError
        from factscribe.refs import _append_ref
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = new_project(tmp)
            out_dir = base / "outside-refs"
            out_dir.mkdir()
            link(out_dir, root / "refs")
            before = snapshot(base)
            with self.assertRaises(ConfigError) as ctx:
                _append_ref(root, {"slug": "s", "title": "t", "authors": ["a"],
                                    "year": "2026", "venue_or_id": "v",
                                    "planned_key": "k", "section": "§一"})
            self.assertEqual(getattr(ctx.exception, "code", ""),
                             "PATH_ESCAPE")
            self.assertEqual(list(out_dir.iterdir()), [],
                             "项目外被写了文件")
            self.assertEqual(snapshot(base), before)


class TestUnresolvableLandingPoint(unittest.TestCase):
    """落点「不可解」的判定必须跨平台同一口径（Windows 真机暴露的缺陷 D1）。

    Windows 上 `os.path.realpath(strict=True)` 对成环软链抛的是
    `OSError(winerror=1921 ERROR_CANT_RESOLVE_FILENAME, errno=22 EINVAL)`，
    **不是** POSIX 的 `ELOOP`（Windows 的 `errno.ELOOP` 常量是 10062，
    跟这里收到的 errno 不是同一个东西）。原来的闸按 `exc.errno == errno.ELOOP` 判 →
    Windows 上必然漏判 → 写侧成环退成 exit 4（工具内部错误），而不是
    `FACT_FILE_UNRESOLVED` / exit 5（真机实测，2026-11-25）。

    这里的用例用**注入异常**的方式做成平台无关的单元测试：同一份代码在
    POSIX 与 Windows 上都必须判成同一个码、同一个退出码。真实软链那条路
    由 `TestFactsWriteOutside.test_symlink_loop_is_refused_as_unresolved` 覆盖
    （在 Windows 上它走的就是 winerror=1921 那条真路，不是注入）。
    """

    @staticmethod
    def _windows_cycle_error():
        """Windows 真机上成环时 strict realpath 抛的那个错（实测值）。"""
        exc = OSError(22, "系统无法辨识文件名。")
        exc.winerror = 1921
        return exc

    @staticmethod
    def _posix_cycle_error():
        return OSError(errno.ELOOP, "Too many levels of symbolic links")

    def _guard_with(self, exc):
        """让落点解析抛出给定的错，看闸怎么判（返回异常）。"""
        from factscribe import safepath
        with mock.patch("factscribe.safepath._real", side_effect=exc):
            safepath.guard_facts_write(Path("/tmp/proj"),
                                       Path("/tmp/proj/facts/01-core.toml"))

    def test_windows_cycle_error_is_refused_as_unresolved(self):
        """Windows 成环错（winerror=1921）→ FACT_FILE_UNRESOLVED / exit 5。"""
        from factscribe.safepath import WriteRefused
        with self.assertRaises(WriteRefused) as ctx:
            self._guard_with(self._windows_cycle_error())
        self.assertEqual(ctx.exception.code, "FACT_FILE_UNRESOLVED")
        self.assertEqual(ctx.exception.exit_code, 5)
        self.assertIn("成环", str(ctx.exception))

    def test_posix_cycle_error_is_refused_as_unresolved(self):
        """POSIX 成环错（ELOOP）→ 同一个码、同一个退出码（不许两平台分叉）。"""
        from factscribe.safepath import WriteRefused
        with self.assertRaises(WriteRefused) as ctx:
            self._guard_with(self._posix_cycle_error())
        self.assertEqual(ctx.exception.code, "FACT_FILE_UNRESOLVED")
        self.assertEqual(ctx.exception.exit_code, 5)

    def test_any_other_oserror_is_refused_not_internal_error(self):
        """解不出来就判不可解（fail-closed），不许裸崩成 exit 4。"""
        from factscribe.safepath import WriteRefused
        with self.assertRaises(WriteRefused) as ctx:
            self._guard_with(OSError(errno.EACCES, "Permission denied"))
        self.assertEqual(ctx.exception.code, "FACT_FILE_UNRESOLVED")
        self.assertEqual(ctx.exception.exit_code, 5)

    def test_project_write_gate_uses_the_same_judgment(self):
        """同族的其它项目内写盘闸：同一口径（PATH_ESCAPE，exit 2），不许裸崩。"""
        from factscribe.config import ConfigError
        from factscribe import safepath
        with mock.patch("factscribe.safepath._real",
                       side_effect=self._windows_cycle_error()):
            with self.assertRaises(ConfigError) as ctx:
                safepath.guard_project_write(Path("/tmp/proj"),
                                             Path("/tmp/proj/audit/x.md"),
                                             what="矩阵产物")
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         "PATH_ESCAPE")

    def test_cli_exits_five_with_unresolved_code(self):
        """命令层：写侧落点不可解 → exit 5 + FACT_FILE_UNRESOLVED（不是 exit 4）。"""
        import contextlib
        import io
        from factscribe import cli
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project(tmp)
            buf = io.StringIO()
            with mock.patch("factscribe.safepath._real",
                           side_effect=self._windows_cycle_error()):
                with contextlib.redirect_stdout(buf):
                    code = cli.main(["fact", "add", str(root),
                                     "--id", "A1", "--claim", "成环不许写",
                                     "--value", "10/16",
                                     "--source", MANIFEST_REL, "--json"])
            self.assertEqual(code, 5, buf.getvalue())
            self.assertNotEqual(code, 4, "不许退成工具内部错误")
            payload = last_json(buf.getvalue())
            self.assertEqual(payload["code"], "FACT_FILE_UNRESOLVED")
            self.assertEqual(payload["exit"], 5)


if __name__ == "__main__":
    unittest.main()
