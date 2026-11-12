# -*- coding: utf-8 -*-
"""`factscribe doctor`：环境与项目自检（不是闸门）。

本组测试钉的是契约面：

- 退出码恒为 0（诊断工具）；目录不存在仍是 exit 2（用法错）；
- `--json` 的 checks / summary / next 形状稳定；
- 缺项目声明判 fail，但仍会把环境查完；
- 中文项目缺字体判 warn，英文项目跳过；
- 自检只读，不往项目里写任何文件。
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

LEVELS = {"ok", "warn", "fail"}


def run(*args, env_extra=None, path=None):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    if env_extra:
        env.update(env_extra)
    if path is not None:
        env["PATH"] = str(path)
    return subprocess.run(
        [sys.executable, "-m", "factscribe", *args],
        capture_output=True, text=True, cwd=str(ROOT), env=env)


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.project = self.tmp / "paper"
        r = run("init", str(self.project), "--lang", "en")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _sign_manifest(self, rel: str = "results/data.md") -> None:
        source = self.project / rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("| arm | resolved |\n| open | 10 |\n", encoding="utf-8")
        r = run("fact", "add", str(self.project), "--id", "A1",
                "--claim", "开臂 resolved", "--value", "10/16",
                "--source", rel)
        self.assertEqual(r.returncode, 0, r.stderr)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        (self.project / "results" / "MANIFEST.toml").write_text(
            '[manifest]\nsigned_by = "tester"\nsigned_at = "2026-11-12T00:00:00Z"\n'
            '[files]\n"%s" = "%s"\n' % (rel, digest), encoding="utf-8")

    def _json(self, *args, **kw):
        r = run("doctor", *args, "--json", **kw)
        return r, json.loads(r.stdout)

    def test_signed_project_has_no_failures(self):
        self._sign_manifest()
        r, data = self._json(str(self.project))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(data["summary"]["fail"], 0)
        by_name = {c["name"]: c for c in data["checks"]}
        self.assertEqual(by_name["python"]["level"], "ok")
        self.assertEqual(by_name["project"]["level"], "ok")
        self.assertEqual(by_name["facts"]["level"], "ok")
        self.assertEqual(by_name["manifest"]["level"], "ok")
        self.assertEqual(by_name["sections"]["level"], "ok")

    def test_missing_project_declaration_is_fail_but_exit_zero(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        r, data = self._json(str(empty))
        self.assertEqual(r.returncode, 0, r.stderr)
        by_name = {c["name"]: c for c in data["checks"]}
        self.assertEqual(by_name["project"]["level"], "fail")
        self.assertIn("init", by_name["project"]["fix"])
        # 项目没加载时不假装检查账与章节（少五行噪音）
        self.assertNotIn("facts", by_name)
        self.assertNotIn("manifest", by_name)
        self.assertIn("python", by_name)  # 环境照查

    def test_nonexistent_directory_is_usage_error(self):
        r = run("doctor", str(self.tmp / "nope"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("目录不存在", r.stderr)

    def test_chinese_project_without_fonts_warns(self):
        zh = self.tmp / "zh-paper"
        self.assertEqual(run("init", str(zh)).returncode, 0)
        cache = self.tmp / "font-cache"
        cache.mkdir()
        fakebin = self.tmp / "bin"
        fakebin.mkdir()  # PATH 里什么都没有：fc-match 也不存在
        r, data = self._json(str(zh), env_extra={
            "FACTSCRIBE_FONT_CACHE": str(cache)}, path=fakebin)
        self.assertEqual(r.returncode, 0, r.stderr)
        by_name = {c["name"]: c for c in data["checks"]}
        self.assertEqual(by_name["fonts"]["level"], "warn")
        self.assertIn("fonts --fetch", by_name["fonts"]["fix"])

    def test_english_project_skips_font_requirement(self):
        cache = self.tmp / "font-cache2"
        cache.mkdir()
        fakebin = self.tmp / "bin2"
        fakebin.mkdir()
        r, data = self._json(str(self.project), env_extra={
            "FACTSCRIBE_FONT_CACHE": str(cache)}, path=fakebin)
        self.assertEqual(r.returncode, 0, r.stderr)
        by_name = {c["name"]: c for c in data["checks"]}
        self.assertEqual(by_name["fonts"]["level"], "ok")
        self.assertIn("英文项目", by_name["fonts"]["detail"])

    def test_doctor_is_read_only(self):
        self._sign_manifest()
        before = snapshot(self.project)
        r = run("doctor", str(self.project))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(snapshot(self.project), before)

    def test_json_contract(self):
        r, data = self._json(str(self.project))
        self.assertEqual(r.returncode, 0, r.stderr)
        for key in ("schema_version", "tool", "command", "status", "exit",
                    "project", "checks", "summary", "next"):
            self.assertIn(key, data)
        self.assertEqual(data["command"], "doctor")
        self.assertEqual(data["exit"], 0)
        self.assertEqual(data["status"], "ok")
        for check in data["checks"]:
            self.assertIn(check["level"], LEVELS)
            for key in ("name", "label", "detail", "fix"):
                self.assertIn(key, check)
            if check["level"] != "ok":
                self.assertTrue(check["fix"])
        self.assertEqual(
            data["summary"]["ok"] + data["summary"]["warn"]
            + data["summary"]["fail"], len(data["checks"]))
        self.assertEqual(len(data["next"]), len(set(data["next"])))


if __name__ == "__main__":
    unittest.main()
