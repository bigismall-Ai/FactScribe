# -*- coding: utf-8 -*-
"""scripts/workbench_e2e.py —— 工作台端到端自检（仓内唯一正本）。

以前这些脚本散在 /tmp 里跑完就丢，仓里没有一份能复跑的。现在收敛成这一份：

    python3 scripts/workbench_e2e.py            # 默认 dry：不真开访达
    python3 scripts/workbench_e2e.py --real-open # 真开（会弹访达窗口！）

**dry 是默认**：脚本自己设 `FACTSCRIBE_NO_OPEN=1`，`open_project_dir`
只回报路径、不调 macOS 的 `open`（条目 32 的闸门）。要真开才加 `--real-open`。

跑什么（都打真后端，不打桩）：

1. 项目发现 ＋ 盘清单；
2. 章节块 ＋ 可编辑模型；
3. AI 对话（后端不可达 → 降级口径：首行「模拟回答（未接模型）」）；
4. 知识库清单 ＋ 预览 ＋ 上传 ＋ 进上下文；
5. 版式配置存盘 ＋ 截止徽标；
6. AI 草稿块：写进稿 → 读 tex 验证标记与正文分离 → 删掉；
7. 「打开项目目录」：dry 模式下 `opened=false`（不弹访达）。

退出码 0＝全过；非 0＝有断言没过。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

#: 「别真开」闸（条目 32）——脚本默认自己设上。
NO_OPEN_ENV = "FACTSCRIBE_NO_OPEN"

FAILURES: list[str] = []
STEPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    STEPS.append("%s %s%s" % ("PASS" if ok else "FAIL", label,
                              ("  —— " + detail) if detail else ""))
    if not ok:
        FAILURES.append(label)


def _make_disk(root: Path, name: str = "paper") -> Path:
    disk = root / name
    (disk / "sections").mkdir(parents=True)
    (disk / "facts").mkdir(parents=True)
    (disk / "factscribe.toml").write_text(
        '[project]\ntitle = "e2e"\nsections = "sections/*.tex"\n'
        'facts = "facts/*.toml"\nbib = "refs.bib"\n', encoding="utf-8")
    (disk / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\input{sections/01-intro}\n\\end{document}\n", encoding="utf-8")
    (disk / "sections" / "01-intro.tex").write_text(
        "\\section{Intro}\n\nWe solved 10/16 arms.\n", encoding="utf-8")
    (disk / "notes.md").write_text("# notes\n\n口径在此。\n", encoding="utf-8")
    return disk


def _get(base: str, path: str):
    try:
        with urllib.request.urlopen(base + path, timeout=30) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _post(base: str, path: str, body: dict):
    request = urllib.request.Request(
        base + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _upload(base: str, path: str, filename: str, payload: bytes):
    boundary = "----factscribee2e"
    body = ("--%s\r\n" % boundary).encode()
    body += ('Content-Disposition: form-data; name="file"; filename="%s"\r\n'
             % filename).encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += payload + ("\r\n--%s--\r\n" % boundary).encode()
    request = urllib.request.Request(
        base + path, data=body, method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
    with urllib.request.urlopen(request, timeout=30) as res:
        return res.status, json.loads(res.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="工作台端到端自检")
    parser.add_argument("--real-open", action="store_true",
                        help="真调 macOS open（会弹访达窗口！默认不真开）")
    parser.add_argument("--root", default="", help="工作区根目录（默认临时目录）")
    args = parser.parse_args(argv)

    if args.real_open:
        os.environ.pop(NO_OPEN_ENV, None)
        mode = "REAL-OPEN（会弹访达）"
    else:
        os.environ[NO_OPEN_ENV] = "1"
        mode = "DRY（不真开）"

    from factscribe.workbench.server import create_server

    tmp = None
    if args.root:
        root = Path(args.root).expanduser()
    else:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
    _make_disk(root)

    server, _index = create_server(root, host="127.0.0.1", port=0, ttl=0.0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        # 1) 项目发现
        status, data = _get(base, "/api/projects")
        check("项目发现", status == 200 and data.get("count", 0) >= 1,
              "count=%s" % data.get("count"))

        # 2) 章节块 ＋ 模型
        status, data = _get(base, "/api/disk/paper/paper/sections")
        blocks = data.get("blocks") or []
        para = next((b for b in blocks if b["kind"] == "para"), None)
        check("章节块", status == 200 and para is not None,
              "blocks=%d" % len(blocks))
        if para:
            status, model = _get(
                base, "/api/disk/paper/paper/block/%s" % para["id"])
            check("可编辑模型", status == 200 and model.get("ok") is True)

        # 3) AI 对话（后端不可达 → 明牌降级）
        status, data = _post(base, "/api/chat", {
            "project": "paper", "disk": "paper",
            "messages": [{"role": "user", "content": "继续"}],
            "quote": {"text": "We solved 10/16 arms."},
            "action": "continue", "mode": "paper"})
        reply = str(data.get("reply") or "")
        check("AI 对话降级口径", data.get("fallback") is True
              and reply.startswith("模拟回答（未接模型）"), reply[:24])

        # 4) 知识库：清单 ＋ 预览 ＋ 上传
        status, data = _get(base, "/api/project/paper/knowledge")
        paths = [f["path"] for f in data.get("files") or []]
        check("知识库清单", status == 200 and "notes.md" in paths,
              "%d files" % len(paths))
        status, data = _get(base, "/api/project/paper/knowledge/preview?path=notes.md")
        check("知识库预览", status == 200 and "口径" in str(data.get("text")))
        status, data = _upload(base, "/api/project/paper/knowledge/upload",
                               "ref.md", "口径补充。\n".encode("utf-8"))
        check("知识库上传", status == 200 and data.get("ok") is True)
        check("上传落在 knowledge/", (root / "paper" / "knowledge" / "ref.md").is_file())

        # 5) 版式
        status, data = _post(base, "/api/project/paper/venue",
                             {"venue": "ACL 2026", "deadline": "2026-05-15"})
        check("版式存盘", status == 200 and data.get("venue") == "ACL 2026")
        check("版式落 workbench.toml",
              "[venue]" in (root / "paper" / "workbench.toml").read_text(encoding="utf-8"))

        # 6) AI 草稿块：写进稿 → 验证标记与正文分离 → 删掉
        tex = root / "paper" / "sections" / "01-intro.tex"
        original = tex.read_text(encoding="utf-8")
        status, data = _post(base, "/api/disk/paper/paper/draft/insert", {
            "file": para["file"], "block": para["id"], "text": "AI 草稿正文。"})
        check("写进稿", status == 200 and data.get("ok") is True)
        after = tex.read_text(encoding="utf-8")
        check("tex 里有 AI 标记",
              "FACTSCRIBE-AI-DRAFT-BEGIN" in after and "FACTSCRIBE-AI-DRAFT-END" in after)
        check("草稿与正文分离",
              "We solved 10/16 arms." in after and "AI 草稿正文。" in after)
        status, data = _post(base, "/api/disk/paper/paper/draft/delete", {
            "file": para["file"], "block": data.get("block")})
        check("删掉草稿块", status == 200 and data.get("ok") is True)
        check("文件复原", tex.read_text(encoding="utf-8") == original)

        # 7) 打开项目目录：dry 模式不真开
        status, data = _post(base, "/api/disk/paper/paper/action",
                             {"action": "open_dir"})
        opened = data.get("opened")
        if args.real_open:
            check("真开模式：调了 open（结果由系统定）", status == 200,
                  "opened=%s" % opened)
        else:
            check("dry 模式：opened=false（没弹访达）",
                  status == 200 and opened is False and bool(data.get("path")),
                  "opened=%s code=%s" % (opened, data.get("code")))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if tmp is not None:
            tmp.cleanup()

    print("工作台端到端自检 —— %s" % mode)
    for line in STEPS:
        print("  " + line)
    print("—— %d/%d 通过" % (len(STEPS) - len(FAILURES), len(STEPS)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
