# -*- coding: utf-8 -*-
"""tests/test_miniapp_python_discovery.py —— Python 解释器发现：Windows 形态 + 三类失败分得开。

起因：用户在 Windows 上明明装了 Python，Mini App 却报「没找到 python3」。
根因有两条，都在这份考题里盯着：

1. 老候选表里**没有任何 Windows 形态**——没有 py 启动器、没有 python3.12 这类
   版本化命令、没有 %LOCALAPPDATA% 下的安装路径。用户装了 3.10+ 但不在 PATH
   （或只有 py 启动器），一律判成「没找到」。
2. 探测失败被**一刀切成「不存在」**——版本不够（exit 1）与命令不存在（ENOENT）
   走同一条路，于是装了 3.9 的用户收到「装好 Python ≥3.10 再来」这种没法定位的话。

读数全部来自**真跑**：驱动脚本 tests/miniapp_python_discovery.mjs 用真 spawn
跑探针（拿假解释器脚本吐 3.9 / 3.12 / 退出码 1 / 根本不存在），结果写成 JSON，
这里逐条断言。node 不在 PATH 就跳过。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tests" / "miniapp_python_discovery.mjs"
SERVER = ROOT / "miniapp" / "miniapp" / "node" / "server.mjs"
DISCOVERY = ROOT / "miniapp" / "miniapp" / "node" / "python_discovery.mjs"

# 老实现的非 Windows 候选顺序——这次改动不许动它。
OLD_UNIX_ORDER = [
    "python3",
    "python",
    "/usr/bin/python3",
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
]

# 引擎要求的最低版本（不许放宽）。
MIN_PYTHON = "3.10"


@unittest.skipUnless(shutil.which("node"), "node 不在 PATH")
class DiscoveryResultTests(unittest.TestCase):
    """真跑 Node 驱动脚本，整份 JSON 供下面各组断言共用。"""

    result: dict

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="fs-pydisc-")
        result_path = Path(cls.tmp) / "result.json"
        env = dict(os.environ)
        env["FS_RESULT_PATH"] = str(result_path)
        proc = subprocess.run(
            ["node", str(DRIVER)], capture_output=True, text=True, timeout=300, env=env,
        )
        if not result_path.is_file():
            raise AssertionError(
                "驱动脚本没产出结果（exit=%s）\nstdout:\n%s\nstderr:\n%s"
                % (proc.returncode, proc.stdout[-3000:], proc.stderr[-3000:])
            )
        cls.result = json.loads(result_path.read_text(encoding="utf-8"))
        cls.proc = proc
        if not cls.result.get("ok"):
            raise AssertionError("驱动脚本自报失败：%s" % cls.result.get("errors"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def labels(self, key):
        return [item["label"] for item in self.result[key]]

    def kinds(self, key):
        return {item["label"]: item["kind"] for item in self.result[key]}


class CandidateTableTests(DiscoveryResultTests):
    """① 候选表（纯函数）：macOS/Linux 顺序不变，Windows 形态补齐。"""

    def test_macos_order_unchanged(self):
        self.assertEqual(self.result["macCandidates"], OLD_UNIX_ORDER)

    def test_linux_order_unchanged(self):
        self.assertEqual(self.result["linuxCandidates"], OLD_UNIX_ORDER)

    def test_fs_python_stays_first(self):
        """用户显式指定的解释器永远排第一（macOS 与 Windows 都一样）。"""
        self.assertEqual(self.result["macCandidatesWithEnv"][0], "/custom/python3")
        self.assertEqual(self.result["macKinds"][0], "env")

    def test_windows_has_py_launcher(self):
        labels = self.labels("winCandidates")
        self.assertIn("py", labels)
        self.assertIn("py -3", labels)
        self.assertIn("py.exe", labels)

    def test_windows_has_versioned_py_launcher_forms(self):
        labels = self.labels("winCandidates")
        for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
            self.assertIn("py -" + version, labels)

    def test_windows_has_versioned_commands(self):
        labels = self.labels("winCandidates")
        self.assertIn("python", labels)
        self.assertIn("python.exe", labels)
        for version in ("3.10", "3.12", "3.14"):
            self.assertIn("python" + version, labels)

    def test_windows_has_localappdata_paths(self):
        """Windows 常见安装目录拼出来的绝对路径必须在候选里，且标成 path 类。"""
        labels = self.labels("winCandidates")
        kinds = self.kinds("winCandidates")
        target = r"C:\Users\mo\AppData\Local\Programs\Python\Python312\python.exe"
        self.assertIn(target, labels)
        self.assertEqual(kinds[target], "path")

    def test_windows_paths_cover_310_and_above_only(self):
        """绝对路径候选只给 3.10 及以上——版本要求不许放宽。"""
        for path in self.result["winPaths"]:
            self.assertIn("Python31", path)
            for low in ("Python38", "Python39", "Python27"):
                self.assertNotIn(low, path)

    def test_windows_program_files_and_system_drive(self):
        paths = self.result["winPaths"]
        self.assertTrue(any(p.startswith("C:\\Program Files\\Python312") for p in paths))
        self.assertTrue(any(p.startswith("C:\\Python312") for p in paths))

    def test_candidates_are_command_plus_args(self):
        """候选是 {command, args} 结构（py -3 这类前缀参数必须带得动）。"""
        for item in self.result["winCandidates"]:
            self.assertIn("kind", item)


class ProbeClassificationTests(DiscoveryResultTests):
    """② 探针把「命令不存在」与「版本过低」分成两类（真 spawn 读数）。"""

    def test_missing_command_is_missing(self):
        self.assertEqual(self.result["probe"]["missing"]["status"], "missing")

    def test_old_version_is_old(self):
        probe = self.result["probe"]["tooOld"]
        self.assertEqual(probe["status"], "old")
        self.assertEqual(probe["version"], "3.9")

    def test_new_version_is_ready(self):
        probe = self.result["probe"]["ready"]
        self.assertEqual(probe["status"], "ready")
        self.assertEqual(probe["version"], "3.12")

    def test_unreadable_command_is_broken(self):
        """命令在、但读不出版本（Windows Store 别名那种）——第三类，不许混进「没装」。"""
        self.assertEqual(self.result["probe"]["broken"]["status"], "broken")

    def test_probe_works_on_real_interpreter(self):
        """探针脚本对真 Python 也有效（本机的 python3）。"""
        probe = self.result["realProbe"]
        self.assertIn(probe["status"], ("ready", "old"))
        self.assertIsNotNone(probe.get("version"))


class DiscoveryScenarioTests(DiscoveryResultTests):
    """③ 三种 Windows 现场各得到什么结果/什么文案。"""

    def test_only_py_launcher_is_found(self):
        """现场：只装了 py 启动器。"""
        self.assertTrue(self.result["onlyPy"]["ok"])
        self.assertEqual(self.result["onlyPy"]["command"], "py")

    def test_py_launcher_prefix_args_are_carried(self):
        """现场：只有 py -3 才认得（裸 py 不可用）——前缀参数必须带进命令。"""
        self.assertTrue(self.result["pyLauncher"]["ok"])
        self.assertEqual(self.result["pyLauncher"]["args"], ["-3"])

    def test_python_outside_path_is_found_by_absolute_path(self):
        """现场：装了 3.12 但没进 PATH——靠 LOCALAPPDATA 拼出的绝对路径找到。"""
        self.assertTrue(self.result["offPath"]["ok"])
        self.assertEqual(self.result["offPath"]["kind"], "path")
        self.assertEqual(self.result["offPath"]["command"], self.result["offPath"]["expectedPath"])

    def test_advice_names_the_path_and_fs_python(self):
        """「装了但不在 PATH」要说清：用的是哪个绝对路径、怎么固定它。"""
        advice = self.result["advice"]
        self.assertIn("FS_PYTHON", advice)
        self.assertIn(self.result["offPath"]["expectedPath"], advice)

    def test_too_old_message_reports_version_and_path(self):
        """现场：装了 3.9——文案必须报出实测版本号与它来自哪个可执行文件。"""
        message = self.result["tooOld"]["message"]
        self.assertIn("3.9", message)
        self.assertIn(r"C:\Python39\python.exe", message)
        self.assertIn(MIN_PYTHON, message)

    def test_too_old_message_explains_why_and_how(self):
        message = self.result["tooOld"]["message"]
        self.assertIn("3.9 及以下跑不了", message)
        self.assertIn("FS_PYTHON", message)

    def test_too_old_message_lists_install_way(self):
        message = self.result["tooOld"]["message"]
        self.assertIn("python.org", message)
        self.assertIn("Add python.exe to PATH", message)

    def test_nothing_found_message_covers_all_three_causes(self):
        """现场：什么都没装——文案要覆盖「怎么装」与「装了却没进 PATH」。"""
        message = self.result["nothing"]["message"]
        self.assertIn(MIN_PYTHON, message)
        self.assertIn("python.org", message)
        self.assertIn("Add python.exe to PATH", message)
        self.assertIn("FS_PYTHON", message)
        self.assertIn("brew install python@3.12", message)

    def test_store_alias_is_called_out(self):
        """命令在但读不出版本＝Microsoft Store 的 python 别名，文案要点名它。"""
        message = self.result["alias"]["message"]
        self.assertIn("Microsoft Store", message)
        self.assertIn("应用执行别名", message)

    def test_bad_fs_python_is_named(self):
        message = self.result["badEnv"]["message"]
        self.assertIn(r"C:\Python312\python.exe", message)
        self.assertIn("FS_PYTHON", message)


class ServerWiringTests(unittest.TestCase):
    """④ 静态契约：探测与拉起引擎共用同一套「命令＋前缀参数」；文案两处同源。"""

    @classmethod
    def setUpClass(cls):
        cls.server = SERVER.read_text(encoding="utf-8")
        cls.discovery = DISCOVERY.read_text(encoding="utf-8")

    def test_server_imports_discovery_module(self):
        self.assertIn("from './python_discovery.mjs'", self.server)
        self.assertIn("discoverPython", self.server)

    def test_probe_and_spawn_share_command_and_args(self):
        """拉起引擎必须用发现结果里的 command＋args（py -3 这类前缀不能丢）。"""
        self.assertIn("const python = discovery.command;", self.server)
        self.assertIn("const pythonArgs = discovery.args;", self.server)
        self.assertIn("spawn(python, [...pythonArgs,", self.server)

    def test_old_probe_helper_is_gone(self):
        """老的 runProbe（裸命令＋写死参数）不许留在原地。"""
        self.assertNotIn("runProbe", self.server)

    def test_failure_message_is_shared_by_start_and_setup_page(self):
        """引擎启动失败与设置页诊断都走同一个文案函数，两处口径不许漂。"""
        self.assertGreaterEqual(self.server.count("pythonFailureMessage("), 2)

    def test_old_misleading_text_is_removed(self):
        """老那句「没找到 python3：……装好 Python ≥3.10 再来」不许留在设置页。"""
        self.assertNotIn("没找到 python3：FactScribe 的引擎是 Python 写的，装好 Python", self.server)

    def test_setup_page_reprobes_after_a_failed_probe(self):
        """用户刚装完 Python、刷新首启页就该看到新结论——失败态要重探一次。"""
        self.assertIn("pythonDiscovery({ refresh: true })", self.server)
        self.assertIn("if (options && options.refresh) pythonProbe = null;", self.server)

    def test_setup_page_does_not_cache_stale_python_verdict(self):
        """首启页的 Python 结论不许被页面缓存冻住。"""
        self.assertNotIn("pageCache", self.server)

    def test_discovery_module_exports_pure_candidates(self):
        """候选生成必须是纯函数（platform/env 进，候选表出）。"""
        self.assertIn("export function pythonCandidates(platform, env = {})", self.discovery)

    def test_version_requirement_not_lowered(self):
        """版本要求锁死 ≥3.10。"""
        self.assertIn("export const MIN_PYTHON = [3, 10]", self.discovery)


if __name__ == "__main__":
    unittest.main()
