# -*- coding: utf-8 -*-
"""本地工作台 HTTP API（`factscribe serve`）。

只做一件事：把已有引擎（config / facts / brief / audit）暴露成本机 HTTP，
让 Mini FactScribe、本地页面或外部 agent 用同一套结构化结果，不再解析 CLI 文本。

边界：

* 只绑回环地址（127.0.0.1 / localhost）；不做远程服务；
* 默认生成随机 Bearer token，所有 `/api/*`（除 health）都要带；
* 只读：serve 不写项目文件，audit 不落盘；
* 不新增判据、不改退出码：audit 的 `exit` 字段就是命令行同一判定。
"""
from __future__ import annotations

import hmac
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .audit import _aggregate_exit, run_audit
from .brief import build_brief, payload as brief_payload
from .config import ConfigError, load_config, load_facts, load_sections
from .constants import EXIT_OK, VERSION
from .report import _config_block, _payload, _severity_of

LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}


class _Handler(BaseHTTPRequestHandler):
    server_version = "factscribe/%s" % VERSION

    def log_message(self, fmt, *args):  # noqa: N802 - stdlib signature
        """不往 stderr 刷每请求日志；需要时由宿主读响应。"""

    # ------------------------------------------------------------------ utils

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code: int, error_code: str, message: str) -> None:
        self._send(code, {"ok": False,
                          "error": {"code": error_code,
                                    "message": message}})

    def _authorized(self) -> bool:
        token = self.server.token  # type: ignore[attr-defined]
        supplied = self.headers.get("X-FactScribe-Token", "")
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
        if not supplied:
            supplied = (parse_qs(urlparse(self.path).query).get("token") or [""])[0]
        return bool(supplied) and hmac.compare_digest(supplied, token)

    def _project(self) -> Path:
        return self.server.project  # type: ignore[attr-defined]

    def _base(self, endpoint: str, code: int = EXIT_OK, **fields) -> dict:
        payload = _payload("serve", _severity_of(code), code,
                           endpoint=endpoint, **fields)
        payload["ok"] = True
        return payload

    # ------------------------------------------------------------------ routes

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send(200, {"ok": True, "tool": "factscribe",
                             "version": VERSION, "service": "workbench"})
            return
        if not self._authorized():
            self._error(401, "UNAUTHORIZED",
                        "需要 Bearer token（Authorization 或 X-FactScribe-Token）")
            return
        try:
            if path == "/api/capabilities":
                cfg = load_config(self._project())
                self._send(200, self._base(
                    "capabilities", engine="python", files=True,
                    workbench=True, version=VERSION, root=str(cfg.root),
                    project=cfg.name or cfg.title,
                    api=["health", "capabilities", "status", "brief", "audit"]))
                return
            if path == "/api/status":
                self._status()
                return
            if path == "/api/brief":
                query = parse_qs(urlparse(self.path).query)
                section = (query.get("section") or [None])[0]
                self._brief(section)
                return
            self._error(404, "NOT_FOUND", "没有这个接口：%s" % path)
        except ConfigError as exc:
            self._error(400, getattr(exc, "code", "CONFIG_INVALID"), str(exc))
        except Exception as exc:  # noqa: BLE001 - 服务不许把异常变成空响应
            self._error(500, "INTERNAL",
                        "%s: %s" % (type(exc).__name__, exc))

    def do_POST(self) -> None:  # noqa: N802 - stdlib signature
        path = urlparse(self.path).path
        if not self._authorized():
            self._error(401, "UNAUTHORIZED",
                        "需要 Bearer token（Authorization 或 X-FactScribe-Token）")
            return
        try:
            if path == "/api/audit":
                self._audit()
                return
            self._error(404, "NOT_FOUND", "没有这个接口：%s" % path)
        except ConfigError as exc:
            self._error(400, getattr(exc, "code", "CONFIG_INVALID"), str(exc))
        except Exception as exc:  # noqa: BLE001
            self._error(500, "INTERNAL",
                        "%s: %s" % (type(exc).__name__, exc))

    # ------------------------------------------------------------------ data

    def _status(self) -> None:
        cfg = load_config(self._project())
        facts = load_facts(cfg)
        sections = load_sections(cfg)
        payload = self._base(
            "status", project=cfg.name or cfg.title, root=str(cfg.root),
            facts=len(facts), sections=len(sections),
            facts_glob=cfg.facts_glob, sections_glob=cfg.sections_glob,
            config=_config_block(cfg), config_warnings=list(cfg.warnings))
        self._send(200, payload)

    def _brief(self, section: str | None) -> None:
        brief = build_brief(self._project(), section)
        payload = self._base("brief", **brief_payload(brief))
        cfg = load_config(self._project())
        payload["config"] = _config_block(cfg)
        payload["config_warnings"] = list(cfg.warnings)
        self._send(200, payload)

    def _audit(self) -> None:
        cfg = load_config(self._project())
        facts = load_facts(cfg)
        sections = load_sections(cfg)
        red, yellow, hints, summary, unresolved = run_audit(
            cfg, facts, sections, resolve=False)
        code = _aggregate_exit(red, yellow, False,
                               integrity_first=cfg.is_v3)
        payload = self._base(
            "audit", code,
            summary=summary,
            findings=[i.as_dict() for i in red] + [w.as_dict() for w in yellow],
            issues=[i.as_dict() for i in red],
            warnings=[w.as_dict() for w in yellow],
            hints=[h.as_dict() for h in hints],
            coverage=summary.get("coverage", {}),
            resolved=unresolved,
            build={"ran": False, "ok": True, "pdf_bytes": 0})
        payload["config"] = _config_block(cfg)
        payload["config_warnings"] = list(cfg.warnings)
        # HTTP 永远是 200：红黄是判定结果，走 payload.exit，不是传输失败。
        self._send(200, payload)


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, project: Path, token: str):
        self.project = project
        self.token = token
        super().__init__(address, _Handler)


def create_server(project: Path | str, *, host: str = "127.0.0.1",
                  port: int = 0, token: str | None = None
                  ) -> tuple[WorkbenchServer, str]:
    """建服务但不启动；返回 (server, token)。项目不合法时抛 ConfigError。"""
    if host not in LOOPBACK_HOSTS:
        raise ConfigError(
            "serve 只允许本机回环地址（127.0.0.1 / localhost），收到 %r；"
            "远程访问不在本命令范围内" % host)
    root = Path(project).expanduser()
    if not root.is_dir():
        raise ConfigError("项目目录不存在：%s" % root)
    root = root.resolve()
    load_config(root)  # 提前校验；坏配置在启动时就 exit 2
    actual_token = token or secrets.token_urlsafe(24)
    server = WorkbenchServer((host, int(port)), root, actual_token)
    return server, actual_token
