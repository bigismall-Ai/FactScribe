# -*- coding: utf-8 -*-
"""工作台段一的本地 HTTP 服务（只用标准库）。

只读：只提供 GET，把项目聚合结果与章节渲染结果交给前端。
端点：
  GET /api/projects                              项目 + 盘 + 计数
  GET /api/disk/<project>/<disk>/sections        节列表 + 轻量 HTML
  GET /api/disk/<project>/<disk>/meta            状态行数据
  GET /                                           前端单页
  GET /static/<name>                             前端静态文件
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .projects import MAX_DEPTH, disk_meta, disk_sections, load_projects

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


class ProjectIndex:
    """项目索引：短 TTL 缓存，避免每次请求都重扫磁盘。"""

    def __init__(self, root: str | Path, max_depth: int = MAX_DEPTH,
                 ttl: float = 2.0) -> None:
        self.root = Path(root).expanduser()
        self.max_depth = max_depth
        self.ttl = ttl
        self._lock = threading.Lock()
        self._stamp = 0.0
        self._projects: list[dict] = []

    def projects(self, refresh: bool = False) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            if not refresh and self._projects and (now - self._stamp) < self.ttl:
                return self._projects
            self._projects = load_projects(self.root, max_depth=self.max_depth)
            self._stamp = now
            return self._projects

    def disk_path(self, project_id: str, disk_id: str) -> Path | None:
        for project in self.projects():
            if project["id"] != project_id:
                continue
            for disk in project["disks"]:
                if disk["id"] == disk_id:
                    return Path(disk["path"])
        return None

    def disk_lang(self, project_id: str, disk_id: str) -> str:
        for project in self.projects():
            if project["id"] != project_id:
                continue
            for disk in project["disks"]:
                if disk["id"] == disk_id:
                    return str(disk.get("lang") or "")
        return ""


class WorkbenchHandler(BaseHTTPRequestHandler):
    """只读 JSON + 静态文件。"""

    server_version = "FactScribeWorkbench/1"
    index: ProjectIndex  # 由 create_server 注入

    # ---- 基础输出 ----

    def log_message(self, fmt, *args):  # noqa: D102 - 安静一点
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: object, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _error(self, code: int, message: str) -> None:
        self._json({"ok": False, "error": message, "code": code}, code=code)

    # ---- 路由 ----

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 的约定
        parsed = urlparse(self.path)
        route = unquote(parsed.path)
        query = parsed.query
        if route in ("/", "/index.html"):
            return self._static("index.html")
        if route.startswith("/static/"):
            return self._static(route[len("/static/"):])
        if route == "/api/projects":
            refresh = "refresh=1" in query
            projects = self.index.projects(refresh=refresh)
            return self._json({"ok": True, "root": str(self.index.root),
                               "count": len(projects), "projects": projects})
        if route.startswith("/api/disk/"):
            parts = [part for part in route.split("/") if part]
            # /api/disk/<project>/<disk>/<what>
            if len(parts) != 5:
                return self._error(404, "路径不对：/api/disk/<project>/<disk>/<sections|meta>")
            project_id, disk_id, what = parts[2], parts[3], parts[4]
            disk_path = self.index.disk_path(project_id, disk_id)
            if disk_path is None:
                return self._error(404, "没有这个盘：%s/%s" % (project_id, disk_id))
            lang = self.index.disk_lang(project_id, disk_id)
            if what == "sections":
                data = disk_sections(disk_path, lang=lang)
                data.update({"ok": True, "project": project_id, "disk": disk_id,
                             "lang": lang})
                return self._json(data)
            if what == "meta":
                data = disk_meta(disk_path, lang=lang)
                data.update({"ok": True, "project": project_id, "disk": disk_id})
                return self._json(data)
            return self._error(404, "没有这个接口：%s" % what)
        return self._error(404, "没有这个接口：%s" % route)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802 - 段一只读
        self._error(405, "段一只有只读接口，不接受写操作")

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST

    # ---- 静态文件 ----

    def _static(self, name: str) -> None:
        target = (STATIC_DIR / name).resolve()
        try:
            target.relative_to(STATIC_DIR)
        except ValueError:
            return self._error(403, "路径越界")
        if not target.is_file():
            return self._error(404, "没有这个文件：%s" % name)
        try:
            body = target.read_bytes()
        except OSError:
            return self._error(404, "读不到文件：%s" % name)
        ctype = STATIC_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, body, ctype)


def create_server(root: str | Path, host: str = "127.0.0.1", port: int = 0,
                  max_depth: int = MAX_DEPTH, ttl: float = 2.0,
                  verbose: bool = False):
    """起服务；返回 (server, index)。server.server_address 有真实端口。"""
    index = ProjectIndex(root, max_depth=max_depth, ttl=ttl)

    class Handler(WorkbenchHandler):
        pass

    Handler.index = index
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.verbose = verbose  # type: ignore[attr-defined]
    return server, index
