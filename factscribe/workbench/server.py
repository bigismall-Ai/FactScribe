# -*- coding: utf-8 -*-
"""工作台段二的本地 HTTP 服务（只用标准库）。

段一只有 GET；段二加了写接口（正文写回、章节管理、项目新建/编辑）。

端点：
  GET  /api/projects                              项目 + 盘 + 计数 + 进度
  GET  /api/disk/<project>/<disk>/sections        节列表 + 轻量 HTML
  GET  /api/disk/<project>/<disk>/meta            状态行数据
  GET  /api/disk/<project>/<disk>/assembly        装配清单（main.tex 的 \\input 列表）
  GET  /api/disk/<project>/<disk>/block/<id>      一段的可编辑模型（散文 + 保护面）
  POST /api/disk/<project>/<disk>/edit            写回一段
  POST /api/disk/<project>/<disk>/toc/move        调序
  POST /api/disk/<project>/<disk>/toc/delete      删除（挪 attic）
  POST /api/disk/<project>/<disk>/toc/create      新建一节
  POST /api/project/new                           新建论文项目（落盘）
  POST /api/project/update                        改项目（标题等）
  POST /api/project/opened                        记「最近打开」
  GET  /                                           前端单页
  GET  /static/<name>                             前端静态文件
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..config import ConfigError
from .projects import MAX_DEPTH, disk_meta, disk_sections, load_projects
from .write import (create_paper_project, create_section, delete_section,
                    editable_model, find_block, move_section, save_block,
                    touch_opened, update_paper_project)

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

    def writable_disk(self, project_id: str, disk_id: str) -> Path | None:
        """写操作的目标盘：必须在这个根目录下面（只写页面打开过的项目）。"""
        path = self.disk_path(project_id, disk_id)
        if path is None:
            return None
        try:
            path.resolve().relative_to(self.root.resolve())
        except (OSError, ValueError):
            return None
        return path


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
            # /api/disk/<project>/<disk>/<what>[/<arg>]
            if len(parts) not in (5, 6):
                return self._error(404, "路径不对：/api/disk/<project>/<disk>/<sections|meta|assembly|block>")
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
            if what == "assembly":
                from .write import read_assembly
                data = read_assembly(disk_path)
                data.update({"ok": True, "project": project_id, "disk": disk_id})
                return self._json(data)
            if what == "block" and len(parts) == 6:
                rel = parts[5]
                return self._json(self._block_model(project_id, disk_id,
                                                    disk_path, rel))
            return self._error(404, "没有这个接口：%s" % what)
        return self._error(404, "没有这个接口：%s" % route)

    def _block_model(self, project_id: str, disk_id: str,
                     disk_path: Path, rel: str) -> dict:
        """一段的可编辑模型：散文（带占位符）＋保护面芯片。"""
        blocks = disk_sections(disk_path)["blocks"]
        target = next((b for b in blocks if b["id"] == rel), None)
        if target is None:
            return {"ok": False, "error": "没有这一段：%s" % rel, "code": 404}
        from .write import Block
        block = Block(file=target.get("file", ""), block_id=target["id"],
                      kind=target["kind"], start=target["start"],
                      end=target["end"], raw=target.get("raw", ""),
                      title=target.get("title", ""))
        data = editable_model(disk_path, block)
        data.update({"ok": True, "project": project_id, "disk": disk_id})
        return data

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        """段二：写接口。"""
        parsed = urlparse(self.path)
        route = unquote(parsed.path)
        body = self._body()
        # 只有这几个接口接受写；其余的路由仍是只读（405，跟段一一致）。
        if not (route.startswith("/api/disk/") or route.startswith("/api/project/")):
            return self._error(405, "这个接口只有 GET（段一就是只读的）")
        try:
            if route.startswith("/api/disk/"):
                return self._disk_post(route, body)
            if route == "/api/project/new":
                return self._project_new(body)
            if route == "/api/project/update":
                return self._project_update(body)
            if route == "/api/project/opened":
                return self._project_opened(body)
        except ConfigError as exc:
            return self._error(400, str(exc))
        except (OSError, ValueError) as exc:
            return self._error(400, "写盘失败：%s" % exc)
        return self._error(404, "没有这个接口：%s" % route)

    # ---- 写接口的实现 ----

    def _disk_post(self, route: str, body: dict) -> None:
        parts = [part for part in route.split("/") if part]
        # /api/disk/<project>/<disk>/<action>[/<arg>]
        if len(parts) < 5:
            return self._error(404, "路径不对")
        project_id, disk_id, action = parts[2], parts[3], parts[4]
        disk = self.index.writable_disk(project_id, disk_id)
        if disk is None:
            return self._error(404, "没有这个盘（或不在根目录下）：%s/%s"
                               % (project_id, disk_id))
        if action == "edit":
            rel = str(body.get("file") or "")
            block_id = str(body.get("block") or "")
            text = body.get("text")
            if not rel or not block_id or not isinstance(text, str):
                return self._error(400, "file / block / text 都要给")
            result = save_block(disk, rel, block_id, text)
            return self._json(result)
        if action == "assembly":
            from .write import read_assembly
            return self._json({"ok": True, **read_assembly(disk)})
        if action == "toc":
            what = parts[5] if len(parts) > 5 else ""
            if what == "move":
                result = move_section(disk, str(body.get("file") or ""),
                                      str(body.get("direction") or ""))
            elif what == "delete":
                result = delete_section(disk, str(body.get("file") or ""))
            elif what == "create":
                result = create_section(disk, str(body.get("title") or ""),
                                        slug=str(body.get("slug") or ""),
                                        after=str(body.get("after") or ""))
            else:
                return self._error(404, "没有这个目录操作：%s" % what)
            return self._json(result)
        return self._error(404, "没有这个操作：%s" % action)

    def _project_new(self, body: dict) -> None:
        root = self.index.root
        result = create_paper_project(
            root,
            slug=str(body.get("slug") or ""),
            title=str(body.get("title") or ""),
            langs=body.get("langs") or ["en"],
            journal=str(body.get("journal") or ""),
            template=str(body.get("template") or ""),
            question=str(body.get("question") or ""),
            project_dir=str(body.get("project_dir") or ""),
            reports_dir=str(body.get("reports_dir") or ""))
        self.index.projects(refresh=True)
        return self._json(result)

    def _project_update(self, body: dict) -> None:
        disk = self.index.writable_disk(str(body.get("project") or ""),
                                         str(body.get("disk") or ""))
        if disk is None:
            return self._error(404, "没有这个盘")
        result = update_paper_project(
            disk,
            title=str(body.get("title") or ""),
            journal=str(body.get("journal") or ""),
            template=str(body.get("template") or ""),
            question=str(body.get("question") or ""),
            reports_dir=str(body.get("reports_dir") or ""),
            last_disk=str(body.get("last_disk") or ""))
        self.index.projects(refresh=True)
        return self._json(result)

    def _project_opened(self, body: dict) -> None:
        disk = self.index.writable_disk(str(body.get("project") or ""),
                                         str(body.get("disk") or ""))
        if disk is None:
            return self._error(404, "没有这个盘")
        result = touch_opened(disk)
        self.index.projects(refresh=True)
        return self._json({"ok": True, **result})

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

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
