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

from .config import ConfigError, load_config
from .constants import EXIT_OK, VERSION
from .report import _payload, _severity_of
from .workbench import (add_fact_data, audit_data, brief_data, project_data,
                        status_data, write_section_data)

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

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 8 * 1024 * 1024:
            raise ConfigError("请求体超过 8 MiB")
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConfigError("请求体必须是 UTF-8 JSON")
        if not isinstance(data, dict):
            raise ConfigError("请求体必须是 JSON 对象")
        return data

    def _require_write(self) -> None:
        if not self.server.allow_write:  # type: ignore[attr-defined]
            raise ConfigError(
                "serve 当前是只读模式；写接口需要 --allow-write",
                code="READ_ONLY")

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
            if path == "/api/project":
                self._project_view()
                return
            self._error(404, "NOT_FOUND", "没有这个接口：%s" % path)
        except ConfigError as exc:
            code = getattr(exc, "code", "CONFIG_INVALID")
            self._error(403 if code == "READ_ONLY" else 400, code, str(exc))
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
            if path == "/api/facts":
                self._add_fact()
                return
            self._error(404, "NOT_FOUND", "没有这个接口：%s" % path)
        except ConfigError as exc:
            code = getattr(exc, "code", "CONFIG_INVALID")
            self._error(403 if code == "READ_ONLY" else 400, code, str(exc))
        except Exception as exc:  # noqa: BLE001
            self._error(500, "INTERNAL",
                        "%s: %s" % (type(exc).__name__, exc))

    def do_PUT(self) -> None:  # noqa: N802 - stdlib signature
        path = urlparse(self.path).path
        if not self._authorized():
            self._error(401, "UNAUTHORIZED",
                        "需要 Bearer token（Authorization 或 X-FactScribe-Token）")
            return
        try:
            if path == "/api/sections":
                self._write_section()
                return
            self._error(404, "NOT_FOUND", "没有这个接口：%s" % path)
        except ConfigError as exc:
            code = getattr(exc, "code", "CONFIG_INVALID")
            self._error(403 if code == "READ_ONLY" else 400, code, str(exc))
        except Exception as exc:  # noqa: BLE001
            self._error(500, "INTERNAL",
                        "%s: %s" % (type(exc).__name__, exc))

    # ------------------------------------------------------------------ data

    def _project_view(self) -> None:
        data = project_data(self._project(), self.server.allow_write)  # type: ignore[attr-defined]
        self._send(200, self._base("project", **data))

    def _write_section(self) -> None:
        body = self._body()
        data = write_section_data(
            self._project(), str(body.get("file") or ""),
            body.get("text"), self.server.allow_write)  # type: ignore[attr-defined]
        self._send(200, self._base("write_section", **data))

    def _add_fact(self) -> None:
        body = self._body()
        data = add_fact_data(self._project(), body,
                             self.server.allow_write)  # type: ignore[attr-defined]
        self._send(200, self._base("add_fact", **data))

    def _status(self) -> None:
        data = status_data(self._project(), self.server.allow_write)  # type: ignore[attr-defined]
        self._send(200, self._base("status", **data))

    def _brief(self, section: str | None) -> None:
        data = brief_data(self._project(), section)
        self._send(200, self._base("brief", **data))

    def _audit(self) -> None:
        data = audit_data(self._project())
        code = int(data.pop("exit"))
        data["build"] = {"ran": False, "ok": True, "pdf_bytes": 0}
        # HTTP 永远是 200：红黄是判定结果，走 payload.exit，不是传输失败。
        self._send(200, self._base("audit", code, **data))

class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, project: Path, token: str,
                 allow_write: bool = False):
        self.project = project
        self.token = token
        self.allow_write = allow_write
        super().__init__(address, _Handler)


def create_server(project: Path | str, *, host: str = "127.0.0.1",
                  port: int = 0, token: str | None = None,
                  allow_write: bool = False
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
    server = WorkbenchServer((host, int(port)), root, actual_token,
                             allow_write=allow_write)
    return server, actual_token
