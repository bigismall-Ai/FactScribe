# -*- coding: utf-8 -*-
"""工作台段二的本地 HTTP 服务（只用标准库）。

段一只有 GET；段二加了写接口（正文写回、章节管理、项目新建/编辑）；
段三加了检查报告与机器视图（只读真闸读数）。

端点：
  GET  /api/projects                              项目 + 盘 + 计数 + 进度
  GET  /api/disk/<project>/<disk>/sections        节列表 + 轻量 HTML
  GET  /api/disk/<project>/<disk>/meta            状态行数据
  GET  /api/disk/<project>/<disk>/assembly        装配清单（main.tex 的 \\input 列表）
  GET  /api/disk/<project>/<disk>/block/<id>      一段的可编辑模型（散文 + 保护面）
  GET  /api/disk/<project>/<disk>/pdf              盘里已编译好的 PDF（预览/下载）
  GET  /api/disk/<project>/<disk>/report          检查报告（体检摘要 + 发现 + 四步链）
  GET  /api/disk/<project>/<disk>/machine         机器视图（账本表/正文扫描/证据链/命令）
  POST /api/disk/<project>/<disk>/edit            写回一段（block=cover-abstract 写摘要）
  POST /api/disk/<project>/<disk>/action          常用功能（pdf / bundle / open_dir）
  POST /api/disk/<project>/<disk>/toc/move        调序
  POST /api/disk/<project>/<disk>/toc/delete      删除（挪 attic）
  POST /api/disk/<project>/<disk>/toc/create      新建一节
  POST /api/disk/<project>/<disk>/report/rerun    只读重跑真闸（限时 120s，零写入）
  POST /api/project/new                           新建论文项目（落盘）
  POST /api/project/update                        改项目（标题等）
  POST /api/project/opened                        记「最近打开」
  POST /api/chat                                  AI 对话（OpenAI 兼容后端；不可达→降级）
  GET  /api/ai/models?project=&disk=              可选模型清单（[ai].models；缺省模型保证在列）
  GET  /api/project/<p>/reports                   报告页的卡（含导入草稿）
  GET  /api/project/<p>/reports/dir               列实验报告目录下的真实文件
  POST /api/project/<p>/reports/upload            上传报告文件进该目录（multipart）
  POST /api/project/<p>/reports/parse             解析报告（预览 + 自动映射）
  POST /api/project/<p>/reports/confirm           写草稿（绝不写活账本）
  GET  /api/project/<p>/knowledge                 知识库文件清单（项目目录里真有的）
  GET  /api/project/<p>/knowledge/preview         看一个文件的内容（文本类直接读）
  POST /api/project/<p>/knowledge/upload          上传进知识库目录（multipart）
  GET  /api/project/<p>/venue                     版式配置（刊物/截稿/语言锁定）
  POST /api/project/<p>/venue                     存版式配置（落 workbench.toml）
  POST /api/disk/<project>/<disk>/draft/insert    AI 草稿块写进稿（该段之后）
  POST /api/disk/<project>/<disk>/draft/delete    删掉一个 AI 草稿块
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
from .write import (ABSTRACT_BLOCK_ID, abstract_block, create_paper_project,
                    create_section, delete_section, editable_model, find_block,
                    move_section, save_abstract, save_block, touch_opened,
                    update_paper_project)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def _parse_multipart_file(content_type: str, raw: bytes) -> tuple[str, bytes]:
    """从 multipart/form-data 里取出第一个文件：(文件名, 字节)。

    只用标准库：`cgi` 在 3.13 已被移除，这里走 `email` 的解析器。
    """
    if not raw:
        return "", b""
    ctype = str(content_type or "")
    if "multipart/form-data" not in ctype:
        return "", b""
    header = ("Content-Type: %s\r\nMIME-Version: 1.0\r\n\r\n" % ctype).encode("utf-8")
    try:
        from email.parser import BytesParser
        from email.policy import default as default_policy

        message = BytesParser(policy=default_policy).parsebytes(header + raw)
    except Exception:  # noqa: BLE001 - 解析不了就当没收到文件
        return "", b""
    for part in message.iter_parts():
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        return str(filename), bytes(payload)
    return "", b""


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

    def project_disks(self, project_id: str) -> list[dict]:
        """这个项目的盘（英文盘在前）。"""
        for project in self.projects():
            if project["id"] == project_id:
                return list(project.get("disks") or [])
        return []

    def project_disk_path(self, project_id: str) -> Path | None:
        """项目的主盘（英文盘优先）：报告目录与草稿都跟着它走。"""
        disks = self.project_disks(project_id)
        if not disks:
            return None
        primary = next((d for d in disks if d.get("lang") == "en"), disks[0])
        return Path(primary["path"])


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
        if route == "/api/ai/models":
            return self._ai_models_get(query)
        if route.startswith("/api/project/"):
            parts = [part for part in route.split("/") if part]
            # /api/project/<project>/reports[/<what>]
            if len(parts) in (4, 5) and parts[3] == "reports":
                return self._reports_get(parts[2], parts[4] if len(parts) > 4 else "",
                                         query)
            # 段六：/api/project/<project>/knowledge[/preview]
            if len(parts) in (4, 5) and parts[3] == "knowledge":
                return self._knowledge_get(parts[2], parts[4] if len(parts) > 4 else "",
                                           query)
            # 段六：/api/project/<project>/venue
            if len(parts) == 4 and parts[3] == "venue":
                return self._venue_get(parts[2])
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
            if what == "pdf":
                return self._serve_pdf(disk_path)
            if what == "report":
                from .checkreport import report_payload
                data = report_payload(disk_path)
                data.update({"project": project_id, "disk": disk_id})
                return self._json(data)
            if what == "machine":
                from .checkreport import machine_payload
                data = machine_payload(disk_path)
                data.update({"project": project_id, "disk": disk_id})
                return self._json(data)
            return self._error(404, "没有这个接口：%s" % what)
        return self._error(404, "没有这个接口：%s" % route)

    def _block_model(self, project_id: str, disk_id: str,
                     disk_path: Path, rel: str) -> dict:
        """一段的可编辑模型：散文（带占位符）＋保护面芯片。"""
        if rel == ABSTRACT_BLOCK_ID:
            # 封面摘要：根文件 abstract 环境（不是 sections/ 下的段）。
            try:
                block = abstract_block(disk_path)
            except ConfigError as exc:
                return {"ok": False, "error": str(exc),
                        "code": getattr(exc, "code", "ABSTRACT_MISSING"),
                        "status": 400}
            data = editable_model(disk_path, block)
            data.update({"ok": True, "project": project_id, "disk": disk_id})
            return data
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

    def _serve_pdf(self, disk_path: Path) -> None:
        """回传盘里已编译好的 PDF（预览/下载用）。"""
        from .actions import PDF_NAME

        target = disk_path / PDF_NAME
        if not target.is_file():
            return self._error(404, "这个盘还没有编译好的 PDF（先点「渲染 PDF」）")
        try:
            body = target.read_bytes()
        except OSError as exc:
            return self._error(404, "读不到 PDF：%s" % exc)
        return self._send(200, body, "application/pdf")

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        """段二：写接口；段四：AI 对话与实验报告导入。"""
        parsed = urlparse(self.path)
        route = unquote(parsed.path)
        # 上传走 multipart：自己读原始字节，别让 _body 吞掉。
        if route.startswith("/api/project/") and route.endswith("/reports/upload"):
            parts = [part for part in route.split("/") if part]
            if len(parts) == 5:
                return self._reports_upload(parts[2])
        if route.startswith("/api/project/") and route.endswith("/knowledge/upload"):
            parts = [part for part in route.split("/") if part]
            if len(parts) == 5:
                return self._knowledge_upload(parts[2])
        body = self._body()
        # 只有这几个接口接受写；其余的路由仍是只读（405，跟段一一致）。
        if route == "/api/chat":
            return self._chat(body)
        if not (route.startswith("/api/disk/") or route.startswith("/api/project/")):
            return self._error(405, "这个接口只有 GET（段一就是只读的）")
        try:
            if route.startswith("/api/disk/"):
                parts = [part for part in route.split("/") if part]
                # 段三：只读重跑（不是写接口，不必是可写盘）。
                if (len(parts) == 6 and parts[4] == "report"
                        and parts[5] == "rerun"):
                    return self._report_rerun(parts[2], parts[3])
                return self._disk_post(route, body)
            if route == "/api/project/new":
                return self._project_new(body)
            if route == "/api/project/update":
                return self._project_update(body)
            if route == "/api/project/opened":
                return self._project_opened(body)
            if route.startswith("/api/project/"):
                parts = [part for part in route.split("/") if part]
                # /api/project/<project>/reports/<what>
                if len(parts) == 5 and parts[3] == "reports":
                    if parts[4] == "parse":
                        return self._reports_parse(parts[2], body)
                    if parts[4] == "confirm":
                        return self._reports_confirm(parts[2], body)
                    if parts[4] == "delete":
                        return self._reports_delete(parts[2], body)
                    return self._error(404, "没有这个报告操作：%s" % parts[4])
                # /api/project/<project>/knowledge/delete
                if len(parts) == 5 and parts[3] == "knowledge" and parts[4] == "delete":
                    return self._knowledge_delete(parts[2], body)
                # /api/project/<project>/venue
                if len(parts) == 4 and parts[3] == "venue":
                    return self._venue_save(parts[2], body)
        except ConfigError as exc:
            return self._error(400, str(exc))
        except (OSError, ValueError) as exc:
            return self._error(400, "写盘失败：%s" % exc)
        return self._error(404, "没有这个接口：%s" % route)

    # ---- 写接口的实现 ----

    def _report_rerun(self, project_id: str, disk_id: str) -> None:
        """段三：只读重跑真闸（subprocess，限时 120s，跑前跑后哈希对比）。"""
        disk = self.index.disk_path(project_id, disk_id)
        if disk is None:
            return self._error(404, "没有这个盘：%s/%s" % (project_id, disk_id))
        from .checkreport import rerun
        result = rerun(disk)
        result.update({"project": project_id, "disk": disk_id})
        return self._json(result)

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
            if not block_id or not isinstance(text, str):
                return self._error(400, "block / text 都要给")
            if block_id == ABSTRACT_BLOCK_ID:
                # 封面摘要：根文件 abstract 环境（id 固定，不带 file）。
                result = save_abstract(disk, text)
                # 条目 36：写回之后对这一块做轻渲染，前端据此原地更新。
                result["block"] = block_id
                result["html"] = self._rerender_block(disk, "", block_id)
                return self._json(result)
            if not rel:
                return self._error(400, "file / block / text 都要给")
            result = save_block(disk, rel, block_id, text)
            # 条目 36：写回之后对这一块做轻渲染，前端据此原地更新。
            result["block"] = block_id
            result["html"] = self._rerender_block(disk, rel, block_id)
            return self._json(result)
        if action == "action":
            return self._disk_action(project_id, disk_id, disk, body)
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
        if action == "draft":
            return self._draft_post(disk, parts[5] if len(parts) > 5 else "", body)
        return self._error(404, "没有这个操作：%s" % action)

    def _rerender_block(self, disk: Path, rel: str, block_id: str) -> str:
        """写回之后，对**这一个块**做轻渲染，返回它的新 html。

        条目 36：前端不再整篇重载，靠这个 html 原地换掉那一块的 DOM。
        """
        from .projects import disk_sections, render_tex

        try:
            if block_id == ABSTRACT_BLOCK_ID:
                for block in disk_sections(disk).get("blocks", []):
                    if block.get("id") == block_id:
                        return str(block.get("html") or "")
                return ""
            if not rel:
                return ""
            path = Path(disk) / rel
            text = path.read_text(encoding="utf-8", errors="replace")
            for block in render_tex(text, stem=Path(rel).stem):
                if block.get("id") == block_id:
                    return str(block.get("html") or "")
        except (OSError, ValueError):
            return ""
        return ""

    def _draft_post(self, disk: Path, what: str, body: dict) -> None:
        """段六：AI 草稿块——写进稿 ＋ 删除。"""
        from .write import delete_ai_draft, insert_ai_draft

        rel = str(body.get("file") or "")
        block_id = str(body.get("block") or "")
        if not rel or not block_id:
            return self._error(400, "file / block 都要给")
        try:
            if what == "insert":
                text = body.get("text")
                if not isinstance(text, str) or not text.strip():
                    return self._error(400, "text 要给（要写进稿的正文）")
                result = insert_ai_draft(disk, rel, block_id, text)
            elif what == "delete":
                result = delete_ai_draft(disk, rel, block_id)
            else:
                return self._error(404, "没有这个草稿操作：%s" % what)
            # 条目 36：把受影响那块的新 html 一并回传，前端原地更新。
            affected = str(result.get("block") or block_id)
            result["html"] = self._rerender_block(disk, rel, affected)
            result["affected"] = affected
        except ConfigError as exc:
            return self._error(400, str(exc))
        except (OSError, ValueError) as exc:
            return self._error(400, "写盘失败：%s" % exc)
        return self._json(result)

    def _disk_action(self, project_id: str, disk_id: str,
                     disk: Path, body: dict) -> None:
        """常用功能：渲染 PDF / 导出投稿包 / 打开项目目录（真做）。"""
        from .actions import export_bundle, open_project_dir, render_pdf

        what = str(body.get("action") or body.get("what") or "").strip()
        try:
            if what == "pdf":
                result = render_pdf(disk)
            elif what == "bundle":
                result = export_bundle(disk)
            elif what == "open_dir":
                result = open_project_dir(disk)
            else:
                return self._error(404, "没有这个动作：%s" % what)
        except ConfigError as exc:
            return self._error(400, str(exc))
        except (OSError, ValueError) as exc:
            return self._error(400, "动作失败：%s" % exc)
        result.update({"project": project_id, "disk": disk_id})
        # 失败也是 200：前端要拿 detail 渲染人话原因（HTTP 码只管路由）。
        return self._json(result, code=200)

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

    # ---- 段四：AI 对话 ----

    def _chat(self, body: dict) -> None:
        """AI 对话：组装上下文 → 打真后端 → 渲染回复。

        后端不可达 / 超时时返回 `ok=False, fallback=True`，模拟回复首行
        标注「模拟回答（未接模型）」——绝不静默造假。
        """
        from .ai import chat

        project_id = str(body.get("project") or "")
        disk_id = str(body.get("disk") or "")
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            return self._error(400, "messages 要给（非空数组）")
        disk = self.index.disk_path(project_id, disk_id)
        if disk is None:
            return self._error(404, "没有这个盘：%s/%s" % (project_id, disk_id))
        quote = body.get("quote")
        if not isinstance(quote, dict):
            quote = None
        mode = str(body.get("mode") or "ask")
        action = str(body.get("action") or "ask")
        # 条目 42：可选 model 字段透传给 chat()（给了非空串就覆盖配置模型）。
        model = str(body.get("model") or "").strip()
        result = chat(disk, messages, quote=quote, mode=mode, action=action,
                      model=model or None)
        result.update({"project": project_id, "disk": disk_id})
        # 降级也是 200：前端要拿 reply 渲染，并靠 fallback 分辨真假。
        return self._json(result, code=200)

    def _ai_models_get(self, query: str) -> None:
        """条目 42：`GET /api/ai/models?project=<id>&disk=<id>`。

        这个盘可选的模型清单（`workbench.toml` 的 `[ai].models`，
        缺省模型保证在列）＋ 缺省模型名。
        """
        from urllib.parse import parse_qs

        from .ai import ai_config, available_models

        params = parse_qs(query or "")
        project_id = (params.get("project") or [""])[0]
        disk_id = (params.get("disk") or [""])[0]
        disk = self.index.disk_path(project_id, disk_id)
        if disk is None:
            return self._error(404, "没有这个盘：%s/%s" % (project_id, disk_id))
        return self._json({"ok": True, "project": project_id, "disk": disk_id,
                           "models": available_models(disk),
                           "model": ai_config(disk)["model"]})

    # ---- 段四：实验报告导入 ----

    def _reports_dir(self, project_id: str) -> Path:
        from .importer import reports_dir

        disk = self.index.project_disk_path(project_id)
        if disk is None:
            raise ConfigError("没有这个项目：%s" % project_id)
        return reports_dir(disk)

    def _reports_get(self, project_id: str, what: str, query: str = "") -> None:
        """`GET /api/project/<p>/reports`（卡）｜`…/reports/dir`（真实文件清单）
        ｜`…/reports/detail?name=`（一条导入记录的详情）。"""
        from .importer import (ImportError_, list_drafts, list_report_files,
                                read_draft)

        try:
            directory = self._reports_dir(project_id)
        except ConfigError as exc:
            return self._error(404, str(exc))
        if what == "dir":
            files = list_report_files(directory)
            return self._json({"ok": True, "project": project_id,
                               "dir": str(directory),
                               "exists": directory.is_dir(),
                               "count": len(files), "files": files})
        if what == "detail":
            from urllib.parse import parse_qs

            params = parse_qs(query or "")
            name = (params.get("name") or [""])[0]
            if not name:
                return self._error(400, "name 要给（导入记录名）")
            disk = self.index.project_disk_path(project_id)
            if disk is None:
                return self._error(404, "没有这个项目：%s" % project_id)
            try:
                data = read_draft(disk, name)
            except ImportError_ as exc:
                return self._error(400, str(exc))
            data.update({"project": project_id})
            return self._json(data)
        if what in ("", "list"):
            disk = self.index.project_disk_path(project_id)
            drafts = list_drafts(disk) if disk else []
            reports = []
            for item in drafts:
                reports.append({
                    "id": item["id"], "name": item["name"], "file": item["file"],
                    "time": item["time"], "bound": item.get("bound", 0),
                    "status": "pending_check", "status_label": "待核对",
                    "from": "import", "draft_path": item["draft_path"],
                })
            return self._json({"ok": True, "project": project_id,
                               "count": len(reports), "reports": reports})
        return self._error(404, "没有这个接口：%s" % what)

    def _reports_upload(self, project_id: str) -> None:
        """上传报告文件（multipart）→ 存进该项目的实验报告目录。"""
        from .importer import REPORT_SUFFIXES, sha256_of

        try:
            directory = self._reports_dir(project_id)
        except ConfigError as exc:
            return self._error(404, str(exc))
        raw = self._raw_body()
        filename, payload = _parse_multipart_file(self.headers.get("Content-Type") or "",
                                                   raw)
        if not filename:
            return self._error(400, "没有收到文件（multipart 字段名要是 file）")
        if Path(filename).suffix.lower() not in REPORT_SUFFIXES:
            return self._error(400, "只认 %s 文件" % " / ".join(REPORT_SUFFIXES))
        safe = Path(filename).name
        try:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / safe
            target.write_bytes(payload)
        except OSError as exc:
            return self._error(400, "存文件失败：%s" % exc)
        return self._json({"ok": True, "project": project_id,
                           "name": safe, "path": str(target),
                           "size": len(payload), "sha256": sha256_of(target)})

    def _reports_parse(self, project_id: str, body: dict) -> None:
        """解析报告 → 行 ＋ 坏行 ＋ 自动映射。"""
        from .importer import ImportError_, parse_report, sha256_of, suggest_mapping

        try:
            directory = self._reports_dir(project_id)
        except ConfigError as exc:
            return self._error(404, str(exc))
        name = str(body.get("name") or body.get("file") or "").strip()
        if not name:
            return self._error(400, "name 要给（报告目录下的文件名）")
        target = (directory / Path(name).name)
        try:
            target.resolve().relative_to(directory.resolve())
        except (OSError, ValueError):
            return self._error(400, "路径越界")
        try:
            parsed = parse_report(target)
        except ImportError_ as exc:
            return self._error(400, str(exc))
        return self._json({
            "ok": True, "project": project_id, "name": target.name,
            "path": str(target), "sha256": sha256_of(target),
            "rows": parsed["rows"], "failed": parsed["failed"],
            "suggested": suggest_mapping(parsed["rows"]),
        })

    def _reports_confirm(self, project_id: str, body: dict) -> None:
        """写草稿：`facts/draft/<报告名>.draft.toml`。绝不写活账本。"""
        from .importer import ImportError_, sha256_of, write_draft

        disk = self.index.project_disk_path(project_id)
        if disk is None:
            return self._error(404, "没有这个项目：%s" % project_id)
        directory = self._reports_dir(project_id)
        name = str(body.get("name") or body.get("file") or "").strip()
        if not name:
            return self._error(400, "name 要给")
        source = directory / Path(name).name
        rows = body.get("rows")
        if not isinstance(rows, list):
            return self._error(400, "rows 要给（数组）")
        mapping = body.get("mapping")
        mapping = mapping if isinstance(mapping, dict) else {}
        report_name = str(body.get("report_name") or "").strip() or source.name
        digest = sha256_of(source) if source.is_file() else ""
        try:
            result = write_draft(disk, report_name, rows, mapping=mapping,
                                 source_path=source, report_sha256=digest)
        except ImportError_ as exc:
            return self._error(400, str(exc))
        result.update({"project": project_id, "source": str(source),
                       "report_sha256": digest})
        return self._json(result)

    def _reports_delete(self, project_id: str, body: dict) -> None:
        """删一条导入记录（草稿）。源报告文件不动。"""
        from .importer import ImportError_, delete_draft

        disk = self.index.project_disk_path(project_id)
        if disk is None:
            return self._error(404, "没有这个项目：%s" % project_id)
        name = str(body.get("name") or body.get("id") or "").strip()
        if not name:
            return self._error(400, "name 要给")
        try:
            result = delete_draft(disk, name)
        except ImportError_ as exc:
            return self._error(404, str(exc))
        result.update({"project": project_id})
        return self._json(result)

    # ---- 段六：知识库 ----

    def _knowledge_disk(self, project_id: str) -> Path:
        disk = self.index.project_disk_path(project_id)
        if disk is None:
            raise ConfigError("没有这个项目：%s" % project_id)
        return disk

    def _knowledge_get(self, project_id: str, what: str, query: str) -> None:
        """`GET /api/project/<p>/knowledge`（清单）｜`…/knowledge/preview`（预览）。"""
        from .knowledge import (KnowledgeError, knowledge_dir, list_files,
                                preview)

        try:
            disk = self._knowledge_disk(project_id)
        except ConfigError as exc:
            return self._error(404, str(exc))
        if what in ("", "list"):
            try:
                folder = str(knowledge_dir(disk))
            except KnowledgeError as exc:
                return self._error(400, str(exc))
            files = list_files(disk)
            return self._json({"ok": True, "project": project_id,
                               "dir": folder, "count": len(files),
                               "files": files})
        if what == "preview":
            from urllib.parse import parse_qs

            params = parse_qs(query or "")
            rel = (params.get("path") or [""])[0]
            if not rel:
                return self._error(400, "path 要给（项目目录里的相对路径）")
            try:
                data = preview(disk, rel)
            except KnowledgeError as exc:
                return self._error(400, str(exc))
            data.update({"project": project_id})
            return self._json(data)
        return self._error(404, "没有这个接口：%s" % what)

    def _knowledge_delete(self, project_id: str, body: dict) -> None:
        """删一个知识库目录里的文件（写闸：只许 knowledge/ 内的）。"""
        from .knowledge import KnowledgeError, delete_file

        try:
            disk = self._knowledge_disk(project_id)
        except ConfigError as exc:
            return self._error(404, str(exc))
        rel = str(body.get("path") or "").strip()
        if not rel:
            return self._error(400, "path 要给（知识库目录里的相对路径）")
        try:
            result = delete_file(disk, rel)
        except KnowledgeError as exc:
            return self._error(400, str(exc))
        result.update({"project": project_id})
        return self._json(result)

    def _knowledge_upload(self, project_id: str) -> None:
        """上传文件进知识库目录（multipart）。"""
        from .knowledge import KnowledgeError, save_upload

        try:
            disk = self._knowledge_disk(project_id)
        except ConfigError as exc:
            return self._error(404, str(exc))
        raw = self._raw_body()
        filename, payload = _parse_multipart_file(self.headers.get("Content-Type") or "",
                                                   raw)
        if not filename:
            return self._error(400, "没有收到文件（multipart 字段名要是 file）")
        try:
            result = save_upload(disk, filename, payload)
        except KnowledgeError as exc:
            return self._error(400, str(exc))
        result.update({"project": project_id})
        return self._json(result)

    # ---- 段六：版式 ----

    def _venue_get(self, project_id: str) -> None:
        """版式配置（刊物 / 截稿 / 语言锁定 / 模板库）。"""
        from .venue import venue_payload

        try:
            disk = self._knowledge_disk(project_id)
        except ConfigError as exc:
            return self._error(404, str(exc))
        lang = self.index.disk_lang(project_id, disk.name)
        payload = venue_payload(disk, lang=lang)
        payload.update({"project": project_id})
        return self._json(payload)

    def _venue_save(self, project_id: str, body: dict) -> None:
        """存版式配置（落进项目级 `workbench.toml` 的 `[venue]` 表）。"""
        from .venue import VenueError, save_venue

        try:
            disk = self._knowledge_disk(project_id)
        except ConfigError as exc:
            return self._error(404, str(exc))
        lang = self.index.disk_lang(project_id, disk.name)
        try:
            result = save_venue(disk,
                                venue=str(body.get("venue") or ""),
                                deadline=str(body.get("deadline") or ""),
                                lang=lang)
        except VenueError as exc:
            return self._error(400, str(exc))
        except (OSError, ValueError) as exc:
            return self._error(400, "写配置失败：%s" % exc)
        result.update({"project": project_id})
        return self._json(result)

    # ---- 原始请求体 ----

    def _raw_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        return self.rfile.read(length) if length > 0 else b""

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
