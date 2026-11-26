# -*- coding: utf-8 -*-
"""tests/test_code_closed_set.py —— 判定码闭集入宪的核对考题。

两条：

1. **闭集齐**：引擎里每一处会抛的判定码都在 `factscribe/constants.py` 的
   `CODE_CLOSED_SET` 里——不许有码散落在外（第三方与上游社区包要照着
   这张表对照）。
2. **段落级那 13 个在册**：第 ② 步并入段落级线时补登的 13 个判定码，
   一个都不许漏；且它们**只登记不触发**——全部落在写侧（提议单／段落
   写回／value 硬闸），审计那条路上一个都不会抛（27 盘 cmp 与金样例
   逐字节未动就是这件事的实测证据）。
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT)
import sys
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from factscribe.constants import CODE_CLOSED_SET, PARAGRAPH_ONLY_CODES  # noqa: E402

CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
ERRORS = ("ConfigError", "SectionError", "ProjectCreateError",
          "SampleError", "ReportError", "ProposalError")


def _scan_codes() -> set:
    """机械扫出引擎会抛的每一个判定码（与生成闭集那套口径同一条）。"""
    found: set = set()
    for pkg in (ROOT / "factscribe", ROOT / "integrations" / "factscribe-legal"):
        if not pkg.is_dir():
            continue
        for path in sorted(pkg.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            table: dict = {}
            for node in ast.walk(tree):
                if (isinstance(node, ast.Assign) and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)):
                    table.setdefault(node.targets[0].id, node.value.value)

            def resolve(value):
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
                if isinstance(value, ast.Name) and value.id in table:
                    return table[value.id]
                return None

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = node.args
                    pos = list(args.posonlyargs) + list(args.args)
                    pad = [None] * (len(pos) - len(args.defaults))
                    pairs = (list(zip(pos, pad + list(args.defaults)))
                             + list(zip(list(args.kwonlyargs), args.kw_defaults)))
                    for arg, default in pairs:
                        if arg.arg != "code" or default is None:
                            continue
                        code = resolve(default)
                        if code and CODE_RE.match(code):
                            found.add(code)
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = (func.id if isinstance(func, ast.Name)
                        else (func.attr if isinstance(func, ast.Attribute) else None))
                values = [k.value for k in node.keywords if k.arg == "code"]
                if name in ERRORS and len(node.args) >= 2:
                    values.append(node.args[1])
                for value in values:
                    code = resolve(value)
                    if code and CODE_RE.match(code):
                        found.add(code)
    return found


class CodeClosedSetTests(unittest.TestCase):

    def test_every_code_is_in_the_closed_set(self):
        """引擎里每一个判定码都得在闭集里（在册不多、在册不少）。"""
        found = _scan_codes()
        missing = sorted(found - set(CODE_CLOSED_SET))
        self.assertEqual(missing, [], "这些判定码没登记进闭集")
        extra = sorted(set(CODE_CLOSED_SET) - found)
        self.assertEqual(extra, [], "闭集里有引擎已经不再抛的码（过期的登记）")

    def test_paragraph_only_codes_are_registered(self):
        """段落级线独有的 13 个判定码都在册。"""
        self.assertEqual(len(PARAGRAPH_ONLY_CODES), 13)
        missing = sorted(PARAGRAPH_ONLY_CODES - set(CODE_CLOSED_SET))
        self.assertEqual(missing, [], "段落级那 13 个码没登记进闭集")


if __name__ == "__main__":
    unittest.main()
