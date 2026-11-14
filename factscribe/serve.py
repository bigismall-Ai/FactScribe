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
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import ConfigError, load_config
from .projects import (ProjectCreateError, create_project, factscribe_dir,
                       project_description, project_name, read_registry,
                       remove_project, resolve_project, upsert_project,
                       write_registry)
from .constants import EXIT_OK, VERSION
from .report import ReportError, _payload, _severity_of
from .reportapi import report_action_data, reports_data
from .samples import SampleError, install_guide_sample, is_guide_path
from .workbench import (SectionError, add_fact_data, audit_data, brief_data,
                        create_section_data, delete_section_data,
                        evidence_status_data, freeze_evidence_data,
                        project_data, rename_section_data, status_data,
                        unfreeze_evidence_data, write_section_data)

LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
WEB_DIR = Path(__file__).resolve().parent / "web"
_STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    # 开发模式预览用；正常界面不请求它
    "/demo.json": ("demo.json", "application/json; charset=utf-8"),
}


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

    def _send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code: int, error_code: str, message: str,
               **extra) -> None:
        err = {"code": error_code, "message": message}
        err.update(extra)
        self._send(code, {"ok": False, "error": err})

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
        project = self.server.project  # type: ignore[attr-defined]
        if project is None:
            raise ConfigError(
                "还没有选论文项目；先调 POST /api/projects 或在页面里选一个文件夹",
                code="NO_PROJECT")
        return project

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
        if self.server.serve_ui and path in _STATIC:  # type: ignore[attr-defined]
            name, content_type = _STATIC[path]
            try:
                self._send_bytes((WEB_DIR / name).read_bytes(), content_type)
            except OSError:
                self._error(500, "INTERNAL", "UI 文件缺失：%s" % name)
            return
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
                project = self.server.project  # type: ignore[attr-defined]
                cfg = load_config(project) if project is not None else None
                self._send(200, self._base(
                    "capabilities", engine="python", files=True,
                    workbench=True, version=VERSION,
                    root=str(cfg.root) if cfg else None,
                    project=(cfg.name or cfg.title) if cfg else None,
                    api=["health", "capabilities", "status", "brief", "audit",
                         "projects", "reports"]))
                return
            if path == "/api/projects":
                self._projects_view()
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
            if path == "/api/evidence":
                data = evidence_status_data(self._project())
                self._send(200, self._base("evidence", **data))
                return
            if path == "/api/reports":
                data = reports_data(self._project())
                self._send(200, self._base("reports", **data))
                return
            if path == "/api/pdf":
                self._pdf()
                return
            self._error(404, "NOT_FOUND", "没有这个接口：%s" % path)
        except ConfigError as exc:
            code = getattr(exc, "code", "CONFIG_INVALID")
            self._error(403 if code == "READ_ONLY" else 400, code, str(exc))
        except ReportError as exc:
            # 报告层的失败（路径越界、没过 check、锁对不上……）：400 + 机器码。
            self._error(400, exc.code, exc.message)
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
            if path == "/api/projects":
                self._projects_add()
                return
            if path == "/api/projects/create":
                self._projects_create()
                return
            if path == "/api/audit":
                self._audit()
                return
            if path == "/api/facts":
                self._add_fact()
                return
            if path == "/api/samples/guide":
                self._sample_guide()
                return
            if path in ("/api/sections/create", "/api/sections/rename",
                        "/api/sections/delete"):
                self._sections_crud(path)
                return
            if path == "/api/evidence/freeze":
                body = self._body()
                data = freeze_evidence_data(
                    self._project(), str(body.get("reason") or ""),
                    self.server.allow_write)  # type: ignore[attr-defined]
                self._send(200, self._base("evidence_freeze", **data))
                return
            if path == "/api/evidence/unfreeze":
                body = self._body()
                data = unfreeze_evidence_data(
                    self._project(), str(body.get("reason") or ""),
                    str(body.get("at") or ""),
                    self.server.allow_write)  # type: ignore[attr-defined]
                self._send(200, self._base("evidence_unfreeze", **data))
                return
            if path in ("/api/reports/action", "/api/reports"):
                # 两个路径同一件事：/api/reports/action 是正路，/api/reports
                # 是别名——同一份界面在网页与 MiniApp 里用同一个 URL 调它。
                body = self._body()
                data = report_action_data(
                    self._project(), body,
                    self.server.allow_write)  # type: ignore[attr-defined]
                self._send(200, self._base("reports_action", **data))
                return
            if path == "/api/build":
                self._build()
                return
            self._error(404, "NOT_FOUND", "没有这个接口：%s" % path)
        except SectionError as exc:
            # 章节增删改：409 = 冲突（已存在 / 还被正文引用），403 = 只读。
            self._error(exc.status, exc.code, str(exc), **exc.extra)
        except ProjectCreateError as exc:
            # 新建项目：409 = 目标目录不空；400 = 参数不对（slug/父目录…）。
            self._error(exc.status, exc.code, str(exc))
        except SampleError as exc:
            # 示例安装：500 = 包里没有示例 / 复制失败。
            self._error(exc.status, exc.code, str(exc))
        except ConfigError as exc:
            code = getattr(exc, "code", "CONFIG_INVALID")
            self._error(403 if code == "READ_ONLY" else 400, code, str(exc))
        except ReportError as exc:
            # 报告层的失败（路径越界、没过 check、锁对不上……）：400 + 机器码。
            self._error(400, exc.code, exc.message)
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
        except ReportError as exc:
            # 报告层的失败（路径越界、没过 check、锁对不上……）：400 + 机器码。
            self._error(400, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001
            self._error(500, "INTERNAL",
                        "%s: %s" % (type(exc).__name__, exc))

    # ------------------------------------------------------------------ data

    def _pdf(self) -> None:
        cfg = load_config(self._project())
        target = (cfg.root / cfg.output).resolve()
        try:
            target.relative_to(cfg.root.resolve())
        except ValueError:
            self._error(400, "CONFIG_INVALID", "PDF 越出项目根")
            return
        if not target.is_file() or target.suffix.lower() != ".pdf":
            self._error(404, "PDF_MISSING", "还没有 PDF：%s" % cfg.output)
            return
        self._send_bytes(target.read_bytes(), "application/pdf")

    def _build(self) -> None:
        if not self.server.allow_build:  # type: ignore[attr-defined]
            self._error(403, "BUILD_DISABLED",
                        "编译需要启动时加 --allow-build")
            return
        from .cli import run_build_step  # 延迟导入，避免 cli↔serve 循环
        cfg = load_config(self._project())
        code, out, info = run_build_step(cfg, font_fallback=True)
        tail = out[-4000:] if out else ""
        pdf = cfg.root / cfg.output
        size = int((info or {}).get("pdf_bytes") or 0)
        if not size and pdf.is_file():
            size = pdf.stat().st_size
        data = {
            "output": cfg.output,
            "pdf_bytes": size,
            "output_text": tail,
        }
        payload = self._base("build", code, **data)
        payload["ok"] = code == EXIT_OK
        # 编译失败也是 200：失败原因在 exit / output_text，不是传输错误。
        self._send(200, payload)

    def _project_view(self) -> None:
        data = project_data(self._project(), self.server.allow_write,  # type: ignore[attr-defined]
                            self.server.allow_build)  # type: ignore[attr-defined]
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

    def _sample_guide(self) -> None:
        """装内置示例论文到 `~/.factscribe/samples/guide`。

        不需要 `--allow-write`：它只写自己的示例目录，一个字也不碰用户的论文。
        目标目录固定；不存在就整份复制，已存在且 reset=true 就先删再复制。
        """
        body = self._body()
        data = install_guide_sample(reset=bool(body.get("reset")))
        self._send(200, self._base("samples_guide", **data))

    def _sections_crud(self, path: str) -> None:
        """章节增删改：create / rename / delete。"""
        body = self._body()
        write = self.server.allow_write  # type: ignore[attr-defined]
        project = self._project()
        if path.endswith("/create"):
            data = create_section_data(
                project, str(body.get("file") or ""), body.get("text"), write)
            self._send(200, self._base("sections_create", **data))
            return
        if path.endswith("/rename"):
            data = rename_section_data(
                project, str(body.get("from") or ""),
                str(body.get("to") or ""), write)
            self._send(200, self._base("sections_rename", **data))
            return
        data = delete_section_data(
            project, str(body.get("file") or ""),
            bool(body.get("force")), write)
        self._send(200, self._base("sections_delete", **data))

    # ------------------------------------------------------------ 项目管理

    @staticmethod
    def _project_rows(registry: dict) -> list:
        """登记册的每一项补上 `description` 与 `guide`。

        `description` 读项目自己的声明（改了 paperkit.toml 立刻见效）；
        `guide` 标出内置示例论文——列表里要把它挑出去。
        """
        rows = []
        for item in registry.get("projects") or []:
            row = dict(item)
            row["description"] = project_description(item.get("path") or "")
            row["guide"] = is_guide_path(item.get("path") or "")
            rows.append(row)
        return rows

    def _projects_view(self) -> None:
        registry = read_registry()
        current = self.server.project  # type: ignore[attr-defined]
        self._send(200, self._base(
            "projects", dir=str(factscribe_dir()),
            current=str(current) if current else None,
            projects=self._project_rows(registry),
            lastPath=registry["lastPath"],
            python=registry["python"], pythonpath=registry["pythonpath"]))

    def _projects_create(self) -> None:
        """新建论文项目：落骨架 → 补声明 → 登记册置顶。

        会写盘，所以要 `--allow-write`；只生成骨架，不编译。
        """
        self._require_write()
        body = self._body()
        authors = body.get("authors")
        if isinstance(authors, str):
            authors = [a for a in (x.strip() for x in authors.split(",")) if a]
        elif not isinstance(authors, list):
            authors = []
        data = create_project(
            title=str(body.get("title") or ""),
            parent=str(body.get("parent") or ""),
            slug=str(body.get("slug") or ""),
            authors=authors,
            description=str(body.get("description") or ""),
            lang=str(body.get("lang") or "zh"),
            sections=str(body.get("sections") or ""),
            facts=str(body.get("facts") or ""),
            bib=str(body.get("bib") or ""),
            root_tex=str(body.get("root_tex") or ""),
            build=str(body.get("build") or ""),
            source_root=str(body.get("source_root") or ""),
            output=str(body.get("output") or ""),
        )
        root = Path(data["path"])
        self.server.project = root  # type: ignore[attr-defined]
        registry = read_registry()
        self._send(200, self._base(
            "projects_create",
            project={"path": data["path"], "name": data["name"],
                     "description": data["description"]},
            created=True, files=data["files"],
            projects=self._project_rows(registry),
            lastPath=registry["lastPath"],
            python=registry["python"], pythonpath=registry["pythonpath"]))

    def _projects_add(self) -> None:
        body = self._body()
        registry = read_registry()
        if "python" in body:
            python = str(body.get("python") or "").strip()
            if python and not re.fullmatch(r"[\w./-]+", python):
                raise ConfigError(
                    "Python 解释器只填命令名或绝对路径，不能带空格或参数",
                    code="PROJECT_INVALID")
            registry["python"] = python
        if "pythonpath" in body:
            pythonpath = str(body.get("pythonpath") or "").strip()
            if pythonpath and not re.fullmatch(r"[\w./:~-]+", pythonpath):
                raise ConfigError(
                    "包路径只填绝对路径（多个用 : 分隔），不能带空格或参数",
                    code="PROJECT_INVALID")
            registry["pythonpath"] = pythonpath
        if "path" in body:
            root = resolve_project(body.get("path"))
            name = project_name(root)
            registry = upsert_project(registry, root, name)
            self.server.project = root  # type: ignore[attr-defined]
            write_registry(registry)
            self._send(200, self._base(
                "project_add", project={"path": str(root), "name": name},
                projects=self._project_rows(registry),
                lastPath=registry["lastPath"],
                python=registry["python"], pythonpath=registry["pythonpath"]))
            return
        write_registry(registry)
        self._send(200, self._base(
            "projects", projects=self._project_rows(registry),
            lastPath=registry["lastPath"], python=registry["python"],
            pythonpath=registry["pythonpath"]))

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib signature
        path = urlparse(self.path).path
        if not self._authorized():
            self._error(401, "UNAUTHORIZED",
                        "需要 Bearer token（Authorization 或 X-FactScribe-Token）")
            return
        try:
            if path == "/api/projects":
                target = (parse_qs(urlparse(self.path).query).get("path") or [""])[0]
                registry = remove_project(read_registry(), str(target))
                write_registry(registry)
                current = self.server.project  # type: ignore[attr-defined]
                if current is not None and str(current) == str(target):
                    self.server.project = None  # type: ignore[attr-defined]
                self._send(200, self._base(
                    "project_remove", projects=self._project_rows(registry),
                    lastPath=registry["lastPath"]))
                return
            self._error(404, "NOT_FOUND", "没有这个接口：%s" % path)
        except ConfigError as exc:
            code = getattr(exc, "code", "CONFIG_INVALID")
            self._error(403 if code == "READ_ONLY" else 400, code, str(exc))
        except ReportError as exc:
            # 报告层的失败（路径越界、没过 check、锁对不上……）：400 + 机器码。
            self._error(400, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001
            self._error(500, "INTERNAL", "%s: %s" % (type(exc).__name__, exc))

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

    def __init__(self, address, project: Path | None, token: str,
                 allow_write: bool = False, serve_ui: bool = False,
                 allow_build: bool = False):
        self.project = project
        self.token = token
        self.allow_write = allow_write
        self.serve_ui = serve_ui
        self.allow_build = allow_build
        super().__init__(address, _Handler)


def create_server(project: Path | str | None = None, *, host: str = "127.0.0.1",
                  port: int = 0, token: str | None = None,
                  allow_write: bool = False, serve_ui: bool = False,
                  allow_build: bool = False
                  ) -> tuple[WorkbenchServer, str]:
    """建服务但不启动；返回 (server, token)。项目不合法时抛 ConfigError。

    不给项目＝「项目管理」模式：先起服务，由页面从登记册里选文件夹再切过来。
    """
    if host not in LOOPBACK_HOSTS:
        raise ConfigError(
            "serve 只允许本机回环地址（127.0.0.1 / localhost），收到 %r；"
            "远程访问不在本命令范围内" % host)
    root: Path | None = None
    if project is not None:
        root = Path(project).expanduser()
        if not root.is_dir():
            raise ConfigError("项目目录不存在：%s" % root)
        root = root.resolve()
        load_config(root)  # 提前校验；坏配置在启动时就 exit 2
    actual_token = token or secrets.token_urlsafe(24)
    server = WorkbenchServer((host, int(port)), root, actual_token,
                             allow_write=allow_write, serve_ui=serve_ui,
                             allow_build=allow_build)
    return server, actual_token
