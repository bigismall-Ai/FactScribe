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
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .audit import _aggregate_exit, run_audit, source_path
from .brief import build_brief, payload as brief_payload
from .config import ConfigError, load_config, load_facts, load_sections
from .constants import EXIT_OK, VERSION
from .scaffold import add_fact
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
        cfg = load_config(self._project())
        facts = load_facts(cfg)
        sections = load_sections(cfg)
        source_rows = {}
        for fact in facts:
            src = fact.source.strip()
            if not src or src in source_rows:
                continue
            text = ""
            try:
                base = source_path(cfg, "").resolve()
                path = source_path(cfg, src).resolve()
                path.relative_to(base)
                text = path.read_text(encoding="utf-8")
            except (OSError, ValueError, UnicodeDecodeError):
                text = ""
            source_rows[src] = {"id": src, "name": src,
                                "text": text,
                                "sha256": fact.source_sha256}
        bib_path = cfg.root / cfg.bib
        try:
            bib = bib_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            bib = ""
        payload = self._base(
            "project", read_only=not self.server.allow_write,  # type: ignore[attr-defined]
            project=cfg.name or cfg.title, root=str(cfg.root),
            sections=[{"file": rel, "text": text} for rel, text in sections],
            facts=[{
                "id": f.id, "claim": f.claim, "value": f.value,
                "source": f.source, "sourceSha256": f.source_sha256,
                "locator": f.locator, "confidence": f.confidence,
                "derivedFrom": list(f.derived_from), "expr": f.expr,
                "dupOk": f.dup_ok, "notes": f.note,
            } for f in facts],
            sources=list(source_rows.values()), bib=bib)
        payload["config"] = _config_block(cfg)
        payload["config_warnings"] = list(cfg.warnings)
        self._send(200, payload)

    def _write_section(self) -> None:
        self._require_write()
        cfg = load_config(self._project())
        body = self._body()
        rel = str(body.get("file") or "").strip()
        text = body.get("text")
        if not rel:
            raise ConfigError("file 必填：要写哪一节")
        if not isinstance(text, str):
            raise ConfigError("text 必须是字符串")
        sections = dict(load_sections(cfg))
        if rel not in sections:
            raise ConfigError("file 不在审计闭包内：%s" % rel)
        if not rel.endswith(".tex"):
            raise ConfigError("只允许写 .tex 章节：%s" % rel)
        root = cfg.root.resolve()
        target = (cfg.root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise ConfigError("章节越出项目根：%s" % rel)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
        self._send(200, self._base("write_section", file=rel,
                                   bytes=len(text.encode("utf-8"))))

    def _add_fact(self) -> None:
        self._require_write()
        cfg = load_config(self._project())
        body = self._body()
        info = add_fact(
            cfg.root,
            fid=str(body.get("id") or ""),
            claim=str(body.get("claim") or ""),
            value=str(body.get("value") or ""),
            source=str(body.get("source") or ""),
            locator=str(body.get("locator") or ""),
            confidence=str(body.get("confidence") or "med"),
            expr=str(body.get("expr") or ""),
            derived_from=body.get("derived_from") or body.get("derivedFrom"),
            note=str(body.get("note") or ""))
        self._send(200, self._base("add_fact", **info))

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
