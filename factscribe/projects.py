# -*- coding: utf-8 -*-
"""论文项目登记册（与 MiniApp 共用同一份文件）。

一个论文项目＝一个含 `paperkit.toml` 的文件夹。登记册固定在
`~/.factscribe/projects.json`，只存路径、显示名、上次使用时间与解释器设置，
不复制正文、不写项目文件夹。

MiniApp 侧（Node）读写同一个文件，格式必须保持一致：
`{version, projects: [{path, name, lastOpenedAt}], lastPath, python, pythonpath}`。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_VERSION = 1
MAX_PROJECTS = 30
CONFIG_NAME = "paperkit.toml"


def home_dir() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


def factscribe_dir() -> Path:
    return home_dir() / ".factscribe"


def registry_path() -> Path:
    return factscribe_dir() / "projects.json"


def empty_registry() -> dict:
    return {"version": REGISTRY_VERSION, "projects": [], "lastPath": "",
            "python": "", "pythonpath": ""}


def normalize_registry(raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    rows = data.get("projects")
    rows = rows if isinstance(rows, list) else []
    seen: set[str] = set()
    projects = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        projects.append({"path": path,
                         "name": str(row.get("name") or ""),
                         "lastOpenedAt": str(row.get("lastOpenedAt") or "")})
    return {"version": REGISTRY_VERSION,
            "projects": projects,
            "lastPath": str(data.get("lastPath") or ""),
            "python": str(data.get("python") or ""),
            "pythonpath": str(data.get("pythonpath") or "")}


def read_registry() -> dict:
    try:
        return normalize_registry(json.loads(registry_path().read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        # 没有登记册、或被手改坏：当空册，不因此拒绝启动
        return empty_registry()


def write_registry(registry: dict) -> None:
    directory = factscribe_dir()
    directory.mkdir(parents=True, exist_ok=True)
    file = registry_path()
    tmp = file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(normalize_registry(registry), ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, file)


def resolve_project(raw: str | os.PathLike[str] | None) -> Path:
    """展开 `~`、要求绝对路径、必须是含 paperkit.toml 的文件夹；返回真实路径。"""
    from .config import ConfigError, load_config

    text = str(raw or "").strip()
    if not text:
        raise ConfigError("请填论文项目文件夹", code="PROJECT_INVALID")
    if text == "~":
        expanded = home_dir()
    elif text.startswith("~/"):
        expanded = home_dir() / text[2:]
    else:
        expanded = Path(text)
    if not expanded.is_absolute():
        raise ConfigError("请填绝对路径（以 / 开头）：%s" % text,
                          code="PROJECT_INVALID")
    if not expanded.exists():
        raise ConfigError("文件夹不存在：%s" % expanded, code="PROJECT_INVALID")
    if not expanded.is_dir():
        raise ConfigError("不是文件夹：%s" % expanded, code="PROJECT_INVALID")
    root = expanded.resolve()
    if not (root / CONFIG_NAME).exists():
        raise ConfigError("这个文件夹不是论文项目：缺 %s（%s）" % (CONFIG_NAME, root),
                          code="PROJECT_INVALID")
    load_config(root)  # 坏配置在这里就报，别等界面加载到一半才炸
    return root


def project_name(path: str | os.PathLike[str]) -> str:
    from .config import ConfigError, load_config

    root = Path(path)
    try:
        cfg = load_config(root)
        name = (cfg.name or cfg.title or "").strip()
    except ConfigError:
        name = ""
    return name or root.name


def upsert_project(registry: dict, path: str | os.PathLike[str],
                   name: str = "") -> dict:
    reg = normalize_registry(registry)
    root = str(Path(path).resolve())
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry = {"path": root, "name": name or project_name(root), "lastOpenedAt": when}
    rest = [p for p in reg["projects"] if p["path"] != root]
    reg["projects"] = ([entry] + rest)[:MAX_PROJECTS]
    reg["lastPath"] = root
    return reg


def remove_project(registry: dict, path: str) -> dict:
    reg = normalize_registry(registry)
    reg["projects"] = [p for p in reg["projects"] if p["path"] != path]
    if reg["lastPath"] == path:
        reg["lastPath"] = ""
    return reg
