"""批 45 / A 阶段：红蓝 hostile 夹具回归线。

每条 hostile 都写死「SPEC 期望」而不是「当前实现读数」：EXPECT.json 的 exit/codes
来自 SPEC-V2.2 / SPEC-V3.0 的条款；当前实现达不到时用 @unittest.expectedFailure
标记（不等于放宽判据）。对应条款写在各用例 docstring 里。

运行：
    python3 -m unittest tests.test_fixtures -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FACTSCRIBE = [sys.executable, "-m", "factscribe"]
FIXTURES = REPO / "fixtures"
sys.path.insert(0, str(REPO / "tests"))

from _pdfdep import requires_pdftotext  # noqa: E402


def _load_expect(case: Path) -> dict:
    return json.loads((case / "EXPECT.json").read_text(encoding="utf-8"))


def _run_audit(case: Path) -> tuple[dict | None, subprocess.CompletedProcess]:
    proc = subprocess.run(
        FACTSCRIBE + ["audit", str(case), "--json"],
        cwd=REPO, capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, proc
    codes = [i.get("code") for i in data.get("issues", [])]
    codes += [w.get("code") for w in data.get("warnings", [])]
    return {
        "exit": data.get("exit", proc.returncode),
        "codes": codes,
        "data": data,
    }, proc


def _run_gate(case: Path, command: str) -> tuple[dict | None, subprocess.CompletedProcess]:
    """跑 PDF/stamp 闸门。当前 CLI 还没有 verify-pdf → 返回 None（未实现）。"""
    if command != "verify-pdf":
        return None, subprocess.CompletedProcess([], 2, "", "unknown fixture command")
    keys = case / "keys/approver_keys.json"
    if not keys.is_file():
        keys = FIXTURES / "trust/approver_keys.json"
    proc = subprocess.run(
        FACTSCRIBE + ["verify-pdf", str(case / "main.pdf"),
         "--report", str(case / "audit/report.json"),
         "--stamp", str(case / "audit/stamp.json"),
         "--keys", str(keys)],
        cwd=REPO, capture_output=True, text=True)
    if proc.returncode == 2 and ("invalid choice" in proc.stderr
                                 or "unrecognized arguments" in proc.stderr):
        return None, proc
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, proc
    codes = [i.get("code") for i in data.get("issues", [])]
    codes += [w.get("code") for w in data.get("warnings", [])]
    return {"exit": data.get("exit", proc.returncode), "codes": codes, "data": data}, proc


class FixtureSchemaTest(unittest.TestCase):
    """EXPECT.json 自身的元测试：hostile 期望必须红，benign 必须绿。"""

    def _cases(self):
        for kind in ("hostile", "benign"):
            for case in sorted((FIXTURES / kind).iterdir()):
                if case.is_dir():
                    yield kind, case

    def test_every_case_has_expect_and_project(self):
        for kind, case in self._cases():
            with self.subTest(case=case.name, kind=kind):
                self.assertTrue((case / "EXPECT.json").is_file(), case)
                self.assertTrue((case / "paperkit.toml").is_file(), case)
                self.assertTrue(any((case / "facts").glob("*.toml")), case)
                self.assertTrue(any((case / "sections").glob("*.tex")), case)

    def test_hostile_expectation_is_red(self):
        for kind, case in self._cases():
            if kind != "hostile":
                continue
            with self.subTest(case=case.name):
                exp = _load_expect(case)
                self.assertIn(exp["exit"], (1, 5, 7, 8), exp)
                self.assertTrue(exp["codes"], "hostile 必须写明期望 code")

    def test_benign_expectation_is_green(self):
        for kind, case in self._cases():
            if kind != "benign":
                continue
            with self.subTest(case=case.name):
                exp = _load_expect(case)
                self.assertEqual(exp["exit"], 0, exp)
                self.assertEqual(exp["codes"], [], exp)


class HostileFixtureTest(unittest.TestCase):
    """12 条 hostile：批 47 / C 阶段后逐条必须红（expectedFailure=0）。"""

    def _assert_hostile(self, name: str) -> None:
        case = FIXTURES / "hostile" / name
        exp = _load_expect(case)
        if exp["command"] == "audit":
            actual, proc = _run_audit(case)
            if actual is None:
                self.fail("audit 没有输出 JSON：%s\n%s" % (proc.stdout[:400], proc.stderr[:400]))
        else:
            actual, proc = _run_gate(case, exp["command"])
            if actual is None:
                self.fail("%s 闸门尚未实现（SPEC 已冻结，C 阶段补）：%s"
                          % (exp["command"], proc.stderr[:200]))
        self.assertEqual(actual["exit"], exp["exit"],
                         "期望 exit=%s，实际 %s；codes=%s"
                         % (exp["exit"], actual["exit"], actual["codes"]))
        for code in exp["codes"]:
            self.assertIn(code, actual["codes"],
                          "缺少期望 code %s（实际 %s）" % (code, actual["codes"]))

    def test_R1_B2_value_range_whitelist(self):
        """SPEC-V2.2 R-03/R-04（内部 B2）：`10/16` 的值域不得授权 `1/16` → BOUND_MISMATCH。"""
        self._assert_hostile("R1-B2")

    def test_R1_B3_line_level_binding(self):
        """SPEC-V2.2 R-03/R-02（内部 B3）：行级绑定整段 → 两 fact 对调应 BINDING_ATTRIBUTION。"""
        self._assert_hostile("R1-B3")

    def test_R1_B1_tableinput_tunnel(self):
        """SPEC-V2.2 R-05/R-06（内部 B1）：`\\tableinput` 包装宏必须展开 → TABLE_UNBOUND（exit 5）。"""
        self._assert_hostile("R1-B1")

    def test_R1_B4_pkignore_fake_conclusion(self):
        """SPEC-V2.2 R-07（内部 B4）：`\\pkignore` 参数含数字必须红 → PKIGNORE_QUANT。"""
        self._assert_hostile("R1-B4")

    def test_R2_macro_body_escape(self):
        """SPEC-V2.2 R-01A：宏体不得携带数字 → NUMERIC_IN_MACRO（渲染可归责）。"""
        self._assert_hostile("R2-MACRO")

    def test_R2_token_concatenation(self):
        """SPEC-V2.2 R-01A：`9`+`1.4` 拼成 91.4 不是 token → NUM_AFTER_GROUP。"""
        self._assert_hostile("R2-CONCAT")

    def test_R2_numexpr_derived(self):
        """SPEC-V2.2 R-01A：`\\numexpr` 派生数不可归责 → ARITH_IN_BODY。"""
        self._assert_hostile("R2-NUMEXPR")

    def test_R2_sentence_multi_fact(self):
        """SPEC-V2.2 R-02（2-S1）：一句多 fact 按出现顺序归属，对调必红 → BINDING_ATTRIBUTION。"""
        self._assert_hostile("R2-MULTIFACT")

    def test_R2_display_round_to(self):
        """SPEC-V2.2 R-04（2-B2）：display 的 `round_to` 不得把 0.91 放宽成 0.9 → DISPLAY_INCONSISTENT。"""
        self._assert_hostile("R2-ROUNDTO")

    @requires_pdftotext
    def test_R3_pdf_raster(self):
        """SPEC-V3.0 P-02/P-03：纯图片页必须红 → PDF_PAGE_NO_TEXT + PDF_PAGE_RASTERIZED（exit 5）。"""
        self._assert_hostile("R3-PDF-RASTER")

    @requires_pdftotext
    def test_R3_pdf_one_way_inclusion(self):
        """SPEC-V3.0 P-04/P-05：ledger ⊆ PDF 的单向包含会放行缺数 → PDF_LEDGER_TOKEN_MISSING（exit 5）。"""
        self._assert_hostile("R3-PDF-ONEWAY")

    @requires_pdftotext
    def test_R3_stamp_self_signed(self):
        """SPEC-V3.0 P-08/S-01：公钥在项目内即不可信 → STAMP_KEY_UNTRUSTED（exit 5）。"""
        self._assert_hostile("R3-STAMP-SELFSIGN")


class BenignFixtureTest(unittest.TestCase):
    """benign 近邻：当前 audit 必须 exit 0；PDF 闸门实现后同样必须 exit 0。"""

    def _assert_benign(self, name: str) -> None:
        case = FIXTURES / "benign" / name
        exp = _load_expect(case)
        actual, proc = _run_audit(case)
        self.assertIsNotNone(actual, "audit 没有输出 JSON：%s\n%s"
                             % (proc.stdout[:400], proc.stderr[:400]))
        self.assertEqual(actual["exit"], 0,
                         "benign 必须绿，实际 exit=%s codes=%s"
                         % (actual["exit"], actual["codes"]))
        if exp["command"] != "audit":
            gate, gproc = _run_gate(case, exp["command"])
            if gate is not None:
                self.assertEqual(gate["exit"], 0,
                                 "benign 闸门必须绿，实际 exit=%s codes=%s"
                                 % (gate["exit"], gate["codes"]))
            # 闸门未实现时不判失败：benign 的当前可执行面就是 audit。


def _make_benign(name: str):
    case = FIXTURES / "benign" / name

    def test(self):
        BenignFixtureTest._assert_benign(self, name)
    test.__doc__ = "benign 近邻 %s：必须 exit 0。" % name
    # 只有带 main.pdf 的夹具才走 PDF 层（要调 pdftotext）；纯 TeX 夹具照常跑。
    if (case / "main.pdf").is_file():
        test = requires_pdftotext(test)
    return test


for _case in sorted((FIXTURES / "benign").iterdir()):
    if _case.is_dir():
        setattr(BenignFixtureTest,
                "test_%s" % _case.name.replace("-", "_"),
                _make_benign(_case.name))


class RegressionPaperTest(unittest.TestCase):
    """`paper/` 只读快照：0 绑定级红、234 个绑定 token 不变。"""

    def test_paper_en_baseline(self):
        case = FIXTURES / "regression" / "paper-en"
        actual, proc = _run_audit(case)
        self.assertIsNotNone(actual, "audit 没有输出 JSON：%s\n%s"
                             % (proc.stdout[:400], proc.stderr[:400]))
        data = actual["data"]
        summary = data["summary"]
        self.assertEqual(len(data.get("issues", [])), 0,
                         "回归夹具出现红：%s" % [(i["code"], i.get("location"))
                                                for i in data.get("issues", [])])
        self.assertEqual(summary["numbers_total"], 234)
        self.assertEqual(summary["numbers_bound"], 234)
        self.assertEqual(summary["numbers_unbound"], 0)
        self.assertEqual(summary["numbers_unmatched"], 0)


if __name__ == "__main__":
    unittest.main()
