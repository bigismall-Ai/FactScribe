# -*- coding: utf-8 -*-
"""独立核对点名的「三条既有残余 ＋ 一处措辞」——每条一个会在缺陷重现时失败的用例。

四条都是**既有**缺陷（不是本批引入），但确实存在：

A  符号链接章节会崩：软链文件被 `sections/*.tex` glob 收进去时，
   `factscribe/config.py` 的 `p.resolve().relative_to(...)` 抛未捕获的
   ValueError ⇒ 直接 traceback、exit 4。修法：不能裸崩；软链指向项目外判为
   越界（INPUT_OUTSIDE_PROJECT、红、exit 5），指向项目内正常纳入闭包；
   成环不许当成「不存在」静默跳过。

B  全角百分号 ％(U+FF05) 不被当作百分号：全仓没有任何 ％ 处理。F3 把全角小数点
   拉齐后，`５６．２５％` 被读成绝对值 56.25 而不是百分数 0.5625——会误判数字。
   修法：与该文件对半角 % 的既有处理保持一致（全角 ％＝半角 %），不另立规则；
   且不改变既有判定口径。

C  README 退出码说明与实际不符：README.md 说「tectonic 缺失 → 退出码 8」，
   实测 `build`／`audit --build` 走 `project.build` 的 shell 命令时是 exit 1
   （shell 127）；exit 8 的真实路径在 pdfgate（verify-pdf 缺 poppler → exit 8）。

D  `--no-token` 帮助词偏松：写「只允许本监听地址的同源请求」，但实现是**无
   Origin 头的请求一律放行**（命令行、Node 代理都走这条）。精确口径在
   docs/design/SPEC-SERVE.md（--no-token 的同源口径）。对齐帮助词，不改实现。

跑法（仓根）：python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import factscribe  # noqa: E402

BS = chr(92)

BIB_OK = """@inproceedings{chen2023,
  title = {A Paper},
  doi = {10.18653/v1/2023.emnlp-main.741}
}
"""

FACT_PCT = """[[fact]]
id = "P1"
claim = "合计准确率"
value = "56.25%"
source = "results/raw.md"
locator = "§三"
confidence = "med"
derived_from = []
"""

FACT_BARE = """[[fact]]
id = "P1"
claim = "合计准确率"
value = "56.25"
source = "results/raw.md"
locator = "§三"
confidence = "med"
derived_from = []
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_project(tmp, facts, sections, results_text, build=""):
    """最小 v1 项目：facts + sections + refs.bib + 人签清单；全部离线。"""
    root = Path(tmp)
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    raw = root / "results" / "raw.md"
    raw.write_text(results_text, encoding="utf-8")
    digest = _sha(raw)
    (root / "facts" / "f.toml").write_text(
        facts.replace('source = "results/raw.md"',
                      'source = "results/raw.md"\nsource_sha256 = "%s"' % digest),
        encoding="utf-8")
    for name, text in sections.items():
        dest = root / "sections" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    (root / "refs.bib").write_text(BIB_OK, encoding="utf-8")
    (root / "factscribe.toml").write_text(
        '[project]\ntitle = "t"\nauthors = ["a"]\n'
        'sections = "sections/*.tex"\nfacts = "facts/*.toml"\n'
        'bib = "refs.bib"\nbuild = "%s"\n' % build, encoding="utf-8")
    (root / "results" / "MANIFEST.toml").write_text(
        "[manifest]\nsigned_by = \"test-human\"\n"
        "signed_at = \"2026-11-07T00:00:00Z\"\nversion = 1\n\n[files]\n"
        '"results/raw.md" = "%s"\n' % digest, encoding="utf-8")
    return root


def run(args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, "-m", "factscribe"] + args,
                          capture_output=True, text=True, cwd=str(ROOT), env=e)


def audit(root):
    proc = run(["audit", str(root), "--json"])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {}
    return proc.returncode, data, proc.stderr


def codes(data):
    return [i["code"] for i in data.get("issues", [])]


def warn_codes(data):
    return [i["code"] for i in data.get("warnings", [])]


def path_without(*names):
    """PATH 里去掉任何含这些可执行文件的目录（用来测「工具缺失」）。"""
    keep = []
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if not p:
            continue
        try:
            entries = set(os.listdir(p))
        except OSError:
            keep.append(p)
            continue
        if not any(n in entries for n in names):
            keep.append(p)
    keep.append("/usr/bin")
    keep.append("/bin")
    return os.pathsep.join(dict.fromkeys(keep))


# ---------------------------------------------------------------------------
# A：符号链接章节
# ---------------------------------------------------------------------------

HAVE_SYMLINK = hasattr(os, "symlink")


class TestSymlinkSections(unittest.TestCase):
    """A：软链章节不许裸崩；越界判红，界内纳入闭包，成环不静默跳过。"""

    @unittest.skipUnless(HAVE_SYMLINK, "本平台不支持软链")
    def test_outside_symlink_is_red_not_traceback(self):
        """软链指向项目外 ⇒ INPUT_OUTSIDE_PROJECT（红、exit 5），不是 exit 4 崩掉。

        修前：`p.resolve().relative_to(...)` 抛未捕获 ValueError ⇒ traceback、
        exit 4。
        """
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "ext.tex").write_text(
                BS + "section{Ext}" + chr(10) + "外面有个数字 99。" + chr(10),
                encoding="utf-8")
            root = make_project(
                Path(tmp) / "proj", FACT_PCT,
                {"b.tex": BS + "section{B}" + chr(10) + "这里没有数字。" + chr(10)},
                "total 56.25%" + chr(10))
            os.symlink(str(outside / "ext.tex"),
                       str(root / "sections" / "a.tex"))
            code, data, err = audit(root)
            self.assertNotEqual(code, 4, "不许再裸崩成 exit 4：" + err)
            self.assertEqual(code, 5, data)
            self.assertIn("INPUT_OUTSIDE_PROJECT", codes(data))
            issue = [i for i in data["issues"]
                     if i["code"] == "INPUT_OUTSIDE_PROJECT"][0]
            self.assertEqual(issue["severity"], "red")
            self.assertIn("越出项目根", issue["message"])
            self.assertEqual(issue["location"], "sections/a.tex")

    @unittest.skipUnless(HAVE_SYMLINK, "本平台不支持软链")
    def test_outside_symlink_as_only_section_still_reports_outside(self):
        """只有这一节、且它越界时：判红越界（exit 5），不许改写成「sections 为空」。

        「没正文」（exit 2）与「有正文没进审计」（exit 5）是两回事，混成一个码
        就把覆盖缺口盖住了。
        """
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "ext.tex").write_text(
                BS + "section{Ext}" + chr(10) + "外面有个数字 99。" + chr(10),
                encoding="utf-8")
            root = make_project(
                Path(tmp) / "proj", FACT_PCT,
                {"b.tex": BS + "section{B}" + chr(10) + "这里没有数字。" + chr(10)},
                "total 56.25%" + chr(10))
            os.symlink(str(outside / "ext.tex"),
                       str(root / "sections" / "a.tex"))
            os.remove(root / "sections" / "b.tex")
            code, data, err = audit(root)
            self.assertEqual(code, 5, data)
            self.assertIn("INPUT_OUTSIDE_PROJECT", codes(data))
            self.assertNotIn("CONFIG_INVALID", codes(data))

    @unittest.skipUnless(HAVE_SYMLINK, "本平台不支持软链")
    def test_inside_symlink_is_included_in_closure(self):
        """软链指向项目内 ⇒ 正常纳入闭包（照旧扫到），不许误伤。"""
        with tempfile.TemporaryDirectory() as tmp:
            body = (BS + "section{Real}" + chr(10) + "这里没有数字。"
                    + BS + "cite{chen2023}" + chr(10))
            root = make_project(
                Path(tmp) / "proj", FACT_PCT, {"real.tex": body},
                "total 56.25%" + chr(10))
            os.symlink(str(root / "sections" / "real.tex"),
                       str(root / "sections" / "a.tex"))
            cfg = factscribe.load_config(root)
            rels = [rel for rel, _ in factscribe.load_sections(cfg)]
            self.assertIn("sections/a.tex", rels)
            code, data, err = audit(root)
            self.assertEqual(code, 0, data)
            self.assertEqual(codes(data), [])
            self.assertEqual(warn_codes(data), [])
            scanned = data["coverage"]["files_scanned"]
            self.assertIn("sections/a.tex", scanned)

    @unittest.skipUnless(HAVE_SYMLINK, "本平台不支持软链")
    def test_symlink_loop_does_not_crash_and_is_not_silently_dropped(self):
        """软链成环：不许裸崩；那一节读不出内容 ⇒ 覆盖报告要点名（不许静默跳过）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                Path(tmp) / "proj", FACT_PCT,
                {"real.tex": BS + "section{R}" + chr(10)
                 + "这里没有数字。" + chr(10)},
                "total 56.25%" + chr(10))
            os.symlink(str(root / "sections" / "b.tex"),
                       str(root / "sections" / "a.tex"))
            os.symlink(str(root / "sections" / "a.tex"),
                       str(root / "sections" / "b.tex"))
            code, data, err = audit(root)
            self.assertNotEqual(code, 4, "软链成环不许裸崩成 exit 4：" + err)
            self.assertNotEqual(code, 0, "读不出来的节不许当没这回事")
            self.assertIn("UNSCANNED_TEX", warn_codes(data))
            unscanned = [i["location"] for i in data.get("warnings", [])
                         if i["code"] == "UNSCANNED_TEX"]
            self.assertIn("sections/a.tex", unscanned)


# ---------------------------------------------------------------------------
# B：全角百分号
# ---------------------------------------------------------------------------

class TestFullwidthPercent(unittest.TestCase):
    """B：全角 ％(U+FF05) 与半角 % 等价；与裸数不等价；不误伤既有半角行为。"""

    def test_fullwidth_percent_is_a_percent(self):
        """５６．２５％ 是百分数（0.5625），不是绝对值 56.25。

        修前：全角 ％ 不进百分号组 ⇒ pct=False ⇒ key 是 56.25。
        """
        toks = factscribe.literal_tokens("５６．２５％")
        self.assertEqual(len(toks), 1)
        self.assertTrue(toks[0][2], "全角 ％ 必须被当成百分号")

    def test_fullwidth_percent_equals_halfwidth(self):
        """全角 ％ 与半角 % 的归一键完全相同。"""
        def keys(text):
            return {factscribe.number_key(raw, suffix or None, pct)
                    for raw, suffix, pct in factscribe.literal_tokens(text)}
        self.assertEqual(keys("５６．２５％"), keys("56.25%"))
        self.assertEqual(keys("５６．２５％"), {"0.5625"})

    def test_fullwidth_percent_is_not_the_bare_number(self):
        """与裸数不等价：56.25％ ≠ 56.25。"""
        self.assertEqual(factscribe.canon_text("５６．２５％"), "0.5625")
        self.assertEqual(factscribe.canon_text("56.25%"), "0.5625")
        self.assertEqual(factscribe.canon_text("56.25"), "56.25")
        self.assertNotEqual(factscribe.canon_text("５６．２５％"),
                            factscribe.canon_text("56.25"))
        self.assertEqual(factscribe.fact_value_keys("５６．２５％"),
                         factscribe.fact_value_keys("56.25%"))
        self.assertNotEqual(factscribe.fact_value_keys("５６．２５％"),
                            factscribe.fact_value_keys("56.25"))

    def test_halfwidth_percent_behaviour_unchanged(self):
        """既有半角口径一字不动（防误伤）：% 仍是百分数，且仍接受字面值。"""
        self.assertTrue(factscribe.literal_tokens("56.25%")[0][2])
        self.assertEqual(factscribe.number_key("56.25", None, True), "0.5625")
        self.assertEqual(factscribe.number_key("56.25", None, False), "56.25")
        self.assertEqual(factscribe.fact_value_keys("56.25%"),
                         {"0.5625", "56.25"})
        self.assertEqual(factscribe.fact_value_keys("56.25"), {"56.25"})

    def test_extracted_number_keeps_percent_shape(self):
        """正文层抽出来的数字：全角 ％ 与半角 % 同形同键。"""
        text = "准确率为 56.25％"
        scan = factscribe.scan_tex(text)
        nums = factscribe._extract_numbers(scan.masked, text)
        self.assertEqual(len(nums), 1)
        self.assertTrue(nums[0]["pct"])
        self.assertEqual(nums[0]["key"], "0.5625")

    def test_body_fullwidth_percent_binds_to_percent_ledger(self):
        """正文写全角 ％、账上写百分数形式 ⇒ 绑得上，判绿。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                Path(tmp) / "proj", FACT_PCT,
                {"a.tex": "两臂合计的准确率为 ５６．２５％" + BS + "fact{P1}" + chr(10)
                 + BS + "cite{chen2023}" + chr(10)},
                "total 56.25%" + chr(10))
            code, data, err = audit(root)
            self.assertEqual(code, 0, data)
            self.assertEqual(codes(data), [])

    def test_body_fullwidth_percent_does_not_bind_to_bare_ledger(self):
        """正文写 56.25％、账上写裸数 56.25 ⇒ 不许当成同一个数蒙过去。

        修前：全角 ％ 不算百分号 ⇒ key 是 56.25 ⇒ 正好落进裸数账的值域 ⇒ 误判绿。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                Path(tmp) / "proj", FACT_BARE,
                {"a.tex": "两臂合计的准确率为 56.25％" + BS + "fact{P1}" + chr(10)
                 + BS + "cite{chen2023}" + chr(10)},
                "total 56.25" + chr(10))
            code, data, err = audit(root)
            self.assertEqual(code, 1, data)
            self.assertIn("BOUND_MISMATCH", codes(data))


# ---------------------------------------------------------------------------
# C：README 退出码说明
# ---------------------------------------------------------------------------

class TestReadmeExitCodes(unittest.TestCase):
    """C：README 中英两份的退出码说明必须与实测一致。"""

    def _tectonic_row(self, name):
        text = (ROOT / name).read_text(encoding="utf-8")
        rows = [ln for ln in text.splitlines() if ln.startswith("| tectonic |")]
        self.assertEqual(len(rows), 1, "%s 的外部件表里没有 tectonic 行" % name)
        return rows[0]

    def _poppler_row(self, name):
        text = (ROOT / name).read_text(encoding="utf-8")
        rows = [ln for ln in text.splitlines() if ln.startswith("| poppler")]
        self.assertEqual(len(rows), 1, "%s 的外部件表里没有 poppler 行" % name)
        return rows[0]

    def test_build_with_missing_engine_exits_1(self):
        """实测：project.build 走 shell 时，缺 tectonic ⇒ shell 127 ⇒ 退出码 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                Path(tmp) / "proj", FACT_PCT,
                {"a.tex": BS + "section{A}" + chr(10) + "这里没有数字。" + chr(10)},
                "total 56.25%" + chr(10),
                build="tectonic main.tex")
            proc = run(["build", str(root)],
                       env={"PATH": path_without("tectonic")})
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_verify_pdf_with_missing_poppler_exits_8(self):
        """实测：exit 8 的真实路径在 pdfgate（verify-pdf 缺 poppler）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                Path(tmp) / "proj", FACT_PCT,
                {"a.tex": BS + "section{A}" + chr(10) + "这里没有数字。" + chr(10)},
                "total 56.25%" + chr(10))
            pdf = root / "main.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
            report = root / "audit" / "report.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("{}", encoding="utf-8")
            proc = run(["verify-pdf", str(pdf), "--report", str(report), "--json"],
                       env={"PATH": path_without("pdftotext", "pdfinfo", "pdfimages")})
            self.assertEqual(proc.returncode, 8, proc.stdout + proc.stderr)
            self.assertIn("PDF_TOOL_MISSING", proc.stdout)

    def test_readme_zh_documents_measured_exit_codes(self):
        """中文 README：tectonic 那行要写清「哪条命令退几」，不许再一律说 8。"""
        row = self._tectonic_row("README.md")
        self.assertIn("退出码 1", row)
        self.assertIn("退出码 8", row)
        self.assertNotIn("报缺引擎并退出码 8", row)
        self.assertIn("退出码 8", self._poppler_row("README.md"))

    def test_readme_en_documents_measured_exit_codes(self):
        """英文 README 与中文对齐。"""
        row = self._tectonic_row("README.en.md")
        self.assertIn("exit code is **1**", row)
        self.assertIn("exits **8**", row)
        self.assertNotIn("reports the missing engine and exits 8", row)
        self.assertIn("exits 8", self._poppler_row("README.en.md"))


# ---------------------------------------------------------------------------
# D：--no-token 帮助词
# ---------------------------------------------------------------------------

class TestNoTokenHelp(unittest.TestCase):
    """D：--no-token 帮助词必须与实现及 SPEC-SERVE.md 一致（不改实现）。"""

    def _help(self, cmd):
        proc = run([cmd, "--help"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return "".join(proc.stdout.split())      # 去掉换行与空白，避开折行

    def test_serve_help_matches_origin_semantics(self):
        text = self._help("serve")
        self.assertIn("Origin", text)
        self.assertIn("CROSS_ORIGIN", text)
        self.assertIn("不带Origin的请求一律放行", text)
        self.assertNotIn("只允许本监听地址的同源请求", text)

    def test_spec_states_the_same_semantics(self):
        """口径来源：docs/design/SPEC-SERVE.md（--no-token 的同源语义）。

        旧的 `factscribe web` 子命令已按第 ④ 步退场，规格随之从
        SPEC-WEB.md 挪到 SPEC-SERVE.md；措辞不许走样。
        """
        lines = (ROOT / "docs" / "design" / "SPEC-SERVE.md").read_text(
            encoding="utf-8").splitlines()
        hits = [line for line in lines
                if "带 `Origin` 的请求必须是本监听地址" in line]
        self.assertTrue(hits, "SPEC-SERVE.md 里没有 --no-token 的同源口径")
        text = "".join(hits[0].split()).replace("`", "")
        self.assertIn("带Origin的请求必须是本监听地址", text)


class TestNoTokenRuntimeSemantics(unittest.TestCase):
    """D 的行为面：无 Origin 放行、带外域 Origin 403 CROSS_ORIGIN（实现不动）。"""

    @classmethod
    def setUpClass(cls):
        from factscribe.serve import create_server
        cls.server, cls.token = create_server(
            ROOT / "examples" / "minimal", port=0, require_token=False)
        cls.port = cls.server.server_address[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _get(self, path, origin=None):
        headers = {}
        if origin is not None:
            headers["Origin"] = origin
        req = urllib.request.Request(self.base + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
            finally:
                exc.close()
            return exc.code, json.loads(body) if body else {}

    def test_request_without_origin_is_allowed(self):
        """命令行／Node 代理走的就是「没有 Origin 头」这条路 ⇒ 放行。"""
        status, data = self._get("/api/health")
        self.assertEqual(status, 200, data)

    def test_foreign_origin_is_rejected(self):
        """带 Origin 但不是本监听地址 ⇒ 403 CROSS_ORIGIN。"""
        status, data = self._get("/api/health",
                                  origin="http://evil.example.com")
        self.assertEqual(status, 403, data)
        self.assertEqual(data["error"]["code"], "CROSS_ORIGIN")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
