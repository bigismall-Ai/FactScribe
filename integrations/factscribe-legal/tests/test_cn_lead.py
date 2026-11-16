#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中国判例线索层（cn_lead / 文书查）的离线回归。

夹具：tests/fixtures/cn_lead/*.json＝2026-11-17 真端点响应录制后脱敏
（人名/公司名 → 某某；案号/法院/省份/日期是公开司法元数据，保留保形状）。

全离线原则：
  * 解析/渲染/礼貌间隔/参数名——回放夹具（monkeypatch 客户端 _post）；
  * 网络错 fail-closed——打环回 127.0.0.1:9（关闭端口，秒拒，不外联）；
  * CLI 错误面——空检索词/坏配置路径两条离线子进程路径；
  * 不打真端点（真端点冒烟是一次性人工验收，读数记在 README/验收单，不进套）。

  python3 -m unittest discover -s integrations/factscribe-legal/tests -v
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PKG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PKG_ROOT)

from factscribe_legal import cli  # noqa: E402
from factscribe_legal.cn_lead import (  # noqa: E402
    DEFAULT_ENDPOINT, DEFAULT_PUBLIC_KEY, ENV_ENDPOINT, ENV_KEY, LEAD_LINE,
    CnLeadError, CnLeadNetworkError, CnLeadParamError, WenshuChaClient,
    load_cn_lead_config, render_get, render_search, render_verify,
)

FIXDIR = Path(__file__).parent / "fixtures" / "cn_lead"


def load_fixture(name):
    return (FIXDIR / name).read_bytes()


def replay_client(fixture_name, sleeps=None, sent=None, timeout=30.0):
    """回放式客户端：_post 换成读夹具；sleep/rand 注入免真睡。"""
    client = WenshuChaClient(timeout=timeout,
                             sleep_fn=(lambda s: sleeps.append(s)) if sleeps is not None
                             else (lambda s: None),
                             rand_fn=lambda a, b: a)
    raw = load_fixture(fixture_name)

    def fake_post(method, params, req_id):
        if sent is not None:
            sent.append({"method": method, "params": params, "id": req_id})
        return raw

    client._post = fake_post
    return client


class TestClientParsing(unittest.TestCase):
    """夹具回放：信封→内嵌 JSON 的解析与业务面参数。"""

    def test_search_parse_shape(self):
        inner = replay_client("search_ok.json").search("交通事故")
        self.assertIn("results", inner)
        self.assertIn("_coverage", inner)
        self.assertIn("_quota", inner)
        self.assertEqual(inner["pageSize"], 2)
        self.assertEqual(len(inner["results"]), 2)
        first = inner["results"][0]
        for key in ("caseNo", "court", "date", "province"):
            self.assertIn(key, first)

    def test_verify_parse_shape(self):
        inner = replay_client("verify_ok.json").verify_case_no("（2022）苏0322执保100号")
        self.assertEqual(inner["verdict"], "exists")
        self.assertIn("trace", inner)
        self.assertIn("records_with_this_case_number", inner)

    def test_get_meta_parse_shape(self):
        inner = replay_client("get_meta_ok.json").get_judgment(
            "（2022）苏0322执保100号", include_body=False)
        self.assertTrue(inner["found"])
        self.assertIn("matches", inner)
        self.assertIsNone(WenshuChaClient.extract_body(inner))  # 元信息无正文键

    def test_verify_param_name_is_caseno(self):
        # 设计红线：服务参数名是 caseNo（不是 caseNumber）——发错名白扣评估额度。
        sent = []
        replay_client("verify_ok.json", sent=sent).verify_case_no("（2020）京01民初1号")
        self.assertEqual(sent[0]["params"]["arguments"],
                         {"caseNo": "（2020）京01民初1号"})

    def test_search_clamps_page_size_and_page(self):
        sent = []
        replay_client("search_ok.json", sent=sent).search(
            "交通事故", page_size=50, page=99)
        args = sent[0]["params"]["arguments"]
        self.assertEqual(args["pageSize"], 5)   # 硬顶 5
        self.assertEqual(args["page"], 3)       # 页顶 3

    def test_empty_q_rejected_before_any_call(self):
        sent = []
        client = replay_client("search_ok.json", sent=sent)
        with self.assertRaises(CnLeadParamError):
            client.search("   ")
        self.assertEqual(sent, [])              # 没打服务就拒——不计费路径前置

    def test_politeness_random_interval_before_second_call(self):
        sleeps = []
        client = replay_client("search_ok.json", sleeps=sleeps)
        client.search("交通事故")
        self.assertEqual(sleeps, [])            # 首发不睡
        client.search("交通事故")
        self.assertEqual(len(sleeps), 1)
        self.assertGreaterEqual(sleeps[0], 2.0)  # 随机间隔 ≥2 秒

    def test_param_error_is_param_error_and_no_retry(self):
        # 服务 isError=true＝参数错误不计费；fail-closed＝恰好一发，绝不重试。
        # （夹具录的是「q 为空」参数错；空 q 已被本地前置闸拦下不打服务，
        #   所以这里用非空 q 走到传输层再回放服务侧参数错响应。）
        client = replay_client("param_error.json")
        with self.assertRaises(CnLeadParamError) as ctx:
            client.search("x")
        self.assertIn("不计费", str(ctx.exception))
        self.assertEqual(client._calls, 1)


class TestFailClosed(unittest.TestCase):
    """网络/信封坏＝明确报错，不静默不重试。"""

    def test_loopback_refused_raises_network_error(self):
        client = WenshuChaClient(endpoint="http://127.0.0.1:9/mcp", timeout=2.0)
        with self.assertRaises(CnLeadNetworkError):
            client.search("交通事故")

    def test_protocol_error_envelope_raises_network_error(self):
        bad = json.dumps({"jsonrpc": "2.0", "id": 1,
                          "error": {"code": -32600, "message": "bad"}}).encode()
        client = WenshuChaClient()
        client._post = lambda method, params, req_id: bad
        with self.assertRaises(CnLeadNetworkError):
            client.search("交通事故")

    def test_sse_payload_unwrapped(self):
        inner_text = json.loads(load_fixture("search_ok.json").decode("utf-8"))
        sse = ("event: message\ndata: " +
               json.dumps({"jsonrpc": "2.0", "id": 1,
                           "result": inner_text["result"]},
                          ensure_ascii=False)).encode("utf-8")
        client = WenshuChaClient()
        client._post = lambda method, params, req_id: sse
        inner = client.search("交通事故")
        self.assertIn("results", inner)

    def test_config_file_missing_raises(self):
        with self.assertRaises(CnLeadError):
            load_cn_lead_config("/nonexistent/factscribe.toml")

    def test_cn_lead_table_must_be_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "factscribe.toml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("[cn_lead]\n")
            # 空表合法；写坏类型才红
            self.assertEqual(load_cn_lead_config(path), (None, None))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("[cn_lead]\nkey = 3\n")
            with self.assertRaises(CnLeadError):
                load_cn_lead_config(path)


class TestConfigPrecedence(unittest.TestCase):
    """Key 只从 config/环境读：优先级 环境变量 > toml [cn_lead] > 缺省。"""

    def _toml_with_section(self, tmp):
        path = os.path.join(tmp, "factscribe.toml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('[cn_lead]\nendpoint = "https://cfg.example/mcp"\n'
                     'key = "cfg_key"\n')
        return path

    def test_default_when_nothing_set(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with mock.patch.dict(os.environ, {}, clear=False):
                    os.environ.pop(ENV_ENDPOINT, None)
                    os.environ.pop(ENV_KEY, None)
                    self.assertEqual(load_cn_lead_config(None), (None, None))
            finally:
                os.chdir(cwd)

    def test_toml_section_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._toml_with_section(tmp)
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(ENV_ENDPOINT, None)
                os.environ.pop(ENV_KEY, None)
                endpoint, key = load_cn_lead_config(path)
        self.assertEqual(endpoint, "https://cfg.example/mcp")
        self.assertEqual(key, "cfg_key")

    def test_env_beats_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._toml_with_section(tmp)
            with mock.patch.dict(os.environ, {ENV_ENDPOINT: "https://env.example/mcp",
                                              ENV_KEY: "env_key"}):
                endpoint, key = load_cn_lead_config(path)
        self.assertEqual(endpoint, "https://env.example/mcp")
        self.assertEqual(key, "env_key")

    def test_default_public_key_is_demo_key(self):
        # 缺省＝公共端点＋公共测试 Key（README 载明：生产用须申请专属 Key）
        self.assertEqual(DEFAULT_ENDPOINT, "https://mcp.wenshucha.com/mcp")
        self.assertEqual(DEFAULT_PUBLIC_KEY, "wsc_demo_public")

    def test_no_key_literal_beyond_public_demo(self):
        # 验收门 g 自证：模块级 KEY 常量只允许 DEFAULT_PUBLIC_KEY（公共测试
        # Key）与 ENV_KEY（环境变量名）两处赋值；CLI 里一个 Key 字面量都不许
        # 有——专属 Key 只走 config/环境。
        import re
        src = (Path(PKG_ROOT) / "factscribe_legal" / "cn_lead.py").read_text(
            encoding="utf-8")
        key_assigns = re.findall(r"^([A-Z_]*KEY)\s*=", src, re.M)
        self.assertEqual(sorted(set(key_assigns)),
                         ["DEFAULT_PUBLIC_KEY", "ENV_KEY"])
        cli_src = (Path(PKG_ROOT) / "factscribe_legal" / "cli.py").read_text(
            encoding="utf-8")
        self.assertNotIn("wsc_", cli_src)


class TestRenderLeadLine(unittest.TestCase):
    """红线一：三种报告首行与末行都必须是线索层标注，逐字固定。"""

    def _inner(self, name):
        env = json.loads(load_fixture(name).decode("utf-8"))
        return json.loads(env["result"]["content"][0]["text"])

    def test_first_and_last_line_is_lead_line(self):
        for text in (render_search(self._inner("search_ok.json"), "交通事故"),
                     render_verify(self._inner("verify_ok.json")),
                     render_get(self._inner("get_meta_ok.json"))):
            lines = text.splitlines()
            self.assertEqual(lines[0], LEAD_LINE)
            self.assertEqual(lines[-1], LEAD_LINE)

    def test_quota_and_coverage_surfaced(self):
        text = render_search(self._inner("search_ok.json"), "交通事故")
        self.assertIn("配额（", text)
        self.assertIn("数据口径：", text)
        self.assertIn("口径注意：", text)

    def test_verify_verdict_mapping(self):
        text = render_verify(self._inner("verify_ok.json"))
        self.assertIn("库内存在（线索）", text)
        self.assertIn("不是官方证明", text)

    def test_verify_unknown_verdict_not_confirmed(self):
        text = render_verify({"verdict": "weird", "caseNo": "x"})
        self.assertIn("未确认", text)

    def test_search_zero_hits_says_not_found_is_not_nonexistent(self):
        text = render_search({"results": [], "total": 0, "page": 1,
                              "pageSize": 5, "_quota": {}, "_coverage": {}},
                             "不存在的词")
        self.assertIn("查不到≠不存在", text)

    def test_get_with_body_extraction(self):
        inner = self._inner("get_meta_ok.json")
        inner["body"] = "本院认为，……（库内清洗件正文）"
        text = render_get(inner)
        self.assertIn("---- 正文（库内清洗件，非官方原件）----", text)
        self.assertIn("本院认为", text)


class _FakeClient:
    """CLI 面注入替身：不发网络包。"""

    def __init__(self, inner=None, error=None):
        self.inner = inner
        self.error = error
        self.calls = []

    def _maybe_raise(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if self.error is not None:
            raise self.error
        return self.inner

    def search(self, q, page_size=5, page=1):
        return self._maybe_raise("search", q=q, page_size=page_size, page=page)

    def verify_case_no(self, case_no):
        return self._maybe_raise("verify", caseNo=case_no)

    def get_judgment(self, case_no, include_body=True, max_chars=None):
        return self._maybe_raise("get", caseNo=case_no, include_body=include_body)


class TestCliInProcess(unittest.TestCase):
    """CLI 面注入假客户端：退出码与首行标注。"""

    def _run_main(self, argv, client):
        out = io.StringIO()
        with mock.patch.object(cli, "_cn_lead_client", return_value=client), \
                contextlib.redirect_stdout(out):
            code = cli.main(argv)
        return code, out.getvalue()

    def _verify_inner(self):
        env = json.loads(load_fixture("verify_ok.json").decode("utf-8"))
        return json.loads(env["result"]["content"][0]["text"])

    def test_search_ok_exit0_first_line_lead(self):
        env = json.loads(load_fixture("search_ok.json").decode("utf-8"))
        inner = json.loads(env["result"]["content"][0]["text"])
        code, out = self._run_main(
            ["cn-lead-search", "--q", "交通事故"], _FakeClient(inner))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], LEAD_LINE)

    def test_verify_exists_exit0_not_exists_exit1(self):
        code, out = self._run_main(
            ["cn-lead-verify", "--case-no", "（2022）苏0322执保100号"],
            _FakeClient(self._verify_inner()))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], LEAD_LINE)
        not_found = dict(self._verify_inner(), verdict="not_found")
        code, out = self._run_main(
            ["cn-lead-verify", "--case-no", "x"], _FakeClient(not_found))
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], LEAD_LINE)   # 红也要带标注

    def test_verify_unrecognized_verdict_exit1(self):
        weird = dict(self._verify_inner(), verdict="huh")
        code, _ = self._run_main(
            ["cn-lead-verify", "--case-no", "x"], _FakeClient(weird))
        self.assertEqual(code, 1)

    def test_get_not_found_exit1(self):
        code, out = self._run_main(
            ["cn-lead-get", "--case-no", "x"],
            _FakeClient({"found": False, "caseNo": "x"}))
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], LEAD_LINE)

    def test_network_error_exit2_fail_closed(self):
        code, out = self._run_main(
            ["cn-lead-search", "--q", "交通事故"],
            _FakeClient(error=CnLeadNetworkError("连不上文书查服务")))
        self.assertEqual(code, 2)
        self.assertIn("fail-closed", out)
        self.assertNotIn(LEAD_LINE, out)   # 失败面没有报告体，不冒充线索

    def test_param_error_exit2(self):
        code, out = self._run_main(
            ["cn-lead-search", "--q", "交通事故"],
            _FakeClient(error=CnLeadParamError("参数错误不计费")))
        self.assertEqual(code, 2)
        self.assertIn("不计费", out)

    def test_no_deprecation_notice_on_cn_lead(self):
        # 线索层不是核验入口：废弃窗口提示不得占首行（红线一）。
        env = json.loads(load_fixture("search_ok.json").decode("utf-8"))
        inner = json.loads(env["result"]["content"][0]["text"])
        _, out = self._run_main(
            ["cn-lead-search", "--q", "交通事故"], _FakeClient(inner))
        self.assertNotIn("单域调试入口", out)


class TestCliSubprocessOffline(unittest.TestCase):
    """子进程面（只走不联网的错误路径）。"""

    def run_cli(self, *args):
        env = dict(os.environ)
        env.pop(ENV_ENDPOINT, None)
        env.pop(ENV_KEY, None)
        return subprocess.run(
            [sys.executable, "-m", "factscribe_legal", *args],
            cwd=PKG_ROOT, env=env, capture_output=True, text=True)

    def test_empty_q_exit2_without_network(self):
        proc = self.run_cli("cn-lead-search", "--q", "  ")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("不计费", proc.stdout)

    def test_missing_config_exit2(self):
        proc = self.run_cli("cn-lead-verify", "--case-no", "x",
                            "--config", "/nonexistent/factscribe.toml")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("配置文件不存在", proc.stdout)

    def test_help_three_subcommands(self):
        for cmd in ("cn-lead-search", "cn-lead-verify", "cn-lead-get"):
            with self.subTest(cmd=cmd):
                proc = self.run_cli(cmd, "--help")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("usage:", proc.stdout)
                self.assertNotIn("单域调试入口", proc.stdout)  # --help 不掺提示行


if __name__ == "__main__":
    unittest.main()
