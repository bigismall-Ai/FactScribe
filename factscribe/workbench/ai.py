# -*- coding: utf-8 -*-
"""段四：AI 对话适配层（OpenAI 兼容 `chat/completions`，只用标准库 urllib）。

这一层只干一件事：**把工作台的提问变成一次真的模型调用**。

规矩（段四硬约束）：
  * 不引新依赖——只用 `urllib`＋标准库；
  * 后端地址与模型可配：项目级 `workbench.toml` 的 `[ai]` 节
    （`base_url` / `model` / `api_key`，`api_key` 可选）；
  * 缺省 `base_url=http://127.0.0.1:8220/v1`（本机 Q 席 vLLM）、`model=qwen`；
  * 后端不可达 / 超时（限时 60s）→ 结构化降级：`ok=False, fallback=True`，
    模拟回复的**首行必须**是 `模拟回答（未接模型）`——绝不静默造假。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

#: 缺省后端（本机 Q 席 vLLM）。
DEFAULT_BASE_URL = "http://127.0.0.1:8220/v1"
DEFAULT_MODEL = "qwen"

#: 单次调用的限时（秒）。后端慢也不能把工作台挂死。
TIMEOUT = 60.0

#: 降级回复的首行标记。**不许改**——前端靠它、以及靠 fallback 字段分辨真假。
FALLBACK_MARK = "模拟回答（未接模型）"

#: 项目级配置文件名（`[ai]` 节在里面）。
CONFIG_NAME = "workbench.toml"
AI_SECTION = "ai"

#: 上下文里正文紧凑文本的上限（字符）。
CONTEXT_CHARS = 6000

SYSTEM_PROMPT = (
    "你是 FactScribe 的论文写作助手。只依据给定材料回答，"
    "材料里没有的就说材料里没有，不要编造数字或出处。"
    "回答用中文，简洁分条。"
)

EXPLAIN_SYSTEM_PROMPT = (
    "你是 FactScribe 的论文写作助手。下面给的是当前稿件的检查报告摘要。"
    "请用大白话解读：红黄灯各代表什么、要动手做哪几件、哪些不用管。"
    "不要编造材料里没有的数字。"
)


class AIError(Exception):
    """后端不可达 / 超时 / 返回体不认。调用方据此降级。"""

    def __init__(self, message: str, code: str = "AI_UNAVAILABLE") -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- 配置

def _read_ai_table(path: Path) -> dict:
    """读一个 `workbench.toml` 里的 `[ai]` 节；读不到就当没有。"""
    if not path.is_file():
        return {}
    try:
        from ..config import load_toml
        data = load_toml(path)
    except Exception:  # noqa: BLE001 - 坏配置不该让对话崩掉
        return {}
    table = data.get(AI_SECTION)
    return table if isinstance(table, dict) else {}


def ai_config(disk_path: str | Path) -> dict:
    """这个盘用的 AI 配置。

    找 `workbench.toml` 的顺序：盘目录 → 项目目录（盘的上一级）。
    环境变量 `FACTSCRIBE_AI_BASE_URL` / `FACTSCRIBE_AI_MODEL` /
    `FACTSCRIBE_AI_API_KEY` 优先级最高（临时换机不用改文件）。
    """
    disk = Path(disk_path).expanduser()
    table: dict = {}
    for candidate in (disk, disk.parent):
        found = _read_ai_table(candidate / CONFIG_NAME)
        if found:
            table = found
            break
    base_url = str(table.get("base_url") or "").strip()
    base_url = base_url or os.environ.get("FACTSCRIBE_AI_BASE_URL", "").strip()
    base_url = base_url or DEFAULT_BASE_URL
    model = str(table.get("model") or "").strip()
    model = model or os.environ.get("FACTSCRIBE_AI_MODEL", "").strip()
    model = model or DEFAULT_MODEL
    api_key = str(table.get("api_key") or "").strip()
    api_key = api_key or os.environ.get("FACTSCRIBE_AI_API_KEY", "").strip()
    return {"base_url": base_url.rstrip("/"), "model": model, "api_key": api_key}


# ---------------------------------------------------------------- 调用

def chat_completion(base_url: str, model: str, messages: list[dict],
                    api_key: str = "", timeout: float = TIMEOUT) -> str:
    """打一次 OpenAI 兼容的 `chat/completions`，返回文本。

    任何异常都收敛成 `AIError`——调用方只有「成功」与「降级」两条路。
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {"model": model, "messages": messages, "stream": False,
               "temperature": 0.2}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    if api_key:
        request.add_header("Authorization", "Bearer %s" % api_key)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise AIError("后端返回 HTTP %s" % exc.code, "AI_HTTP_ERROR") from exc
    except urllib.error.URLError as exc:
        raise AIError("连不上后端 %s：%s" % (url, exc.reason)) from exc
    except OSError as exc:  # 超时 / 连接被拒
        raise AIError("连不上后端 %s：%s" % (url, exc)) from exc
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AIError("后端返回的不是 JSON", "AI_BAD_RESPONSE") from exc
    return _extract_text(body)


def _extract_text(body: object) -> str:
    """从 OpenAI 兼容返回体里挖出正文；挖不出就报 `AIError`。"""
    if not isinstance(body, dict):
        raise AIError("后端返回体不是对象", "AI_BAD_RESPONSE")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AIError("后端返回体里没有 choices", "AI_BAD_RESPONSE")
    first = choices[0]
    if not isinstance(first, dict):
        raise AIError("后端返回体里 choices[0] 不是对象", "AI_BAD_RESPONSE")
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        text = message.get("reasoning_content")
        if isinstance(text, str) and text.strip():
            return text.strip()
    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    raise AIError("后端返回体里没有可读文本", "AI_BAD_RESPONSE")


# ---------------------------------------------------------------- 上下文

def _strip_html(text: str) -> str:
    import re
    out = re.sub(r"<[^>]+>", " ", str(text or ""))
    return " ".join(out.split())


def disk_text(disk_path: str | Path, limit: int = CONTEXT_CHARS) -> str:
    """当前盘的正文紧凑文本（标题 + 段落，纯文本）。"""
    from .projects import disk_sections

    try:
        data = disk_sections(Path(disk_path))
    except Exception:  # noqa: BLE001 - 读不到盘就当空正文
        return ""
    pieces: list[str] = []
    for block in data.get("blocks") or []:
        title = str(block.get("title") or "").strip()
        if title:
            pieces.append("## %s" % title)
        body = _strip_html(block.get("html") or "")
        if body:
            pieces.append(body)
    text = "\n".join(pieces)
    if len(text) > limit:
        text = text[:limit] + "\n…（正文已截断）"
    return text


def report_summary(disk_path: str | Path) -> str:
    """检查报告摘要（解读模式用）。读不到就当没有。"""
    from .checkreport import report_payload

    try:
        payload = report_payload(Path(disk_path))
    except Exception:  # noqa: BLE001
        return ""
    if not payload.get("ok"):
        return ""
    health = payload.get("health") or {}
    findings = payload.get("findings") or []
    chain = payload.get("chain") or []
    lines = [
        "体检：红 %s，黄 %s，提醒 %s，事实 %s，章节 %s，状态 %s。" % (
            health.get("red", 0), health.get("yellow", 0),
            health.get("hints", 0), health.get("facts", 0),
            health.get("sections", 0), health.get("status", "?")),
        "发现 %s 条：" % len(findings),
    ]
    for item in findings[:20]:
        lines.append("- [%s] %s：%s" % (
            item.get("severity", ""), item.get("code", ""),
            item.get("message", "") or item.get("title", "")))
    if chain:
        lines.append("四步链：" + "；".join(
            "%s=%s" % (step.get("key", ""), step.get("state", "")) for step in chain))
    return "\n".join(lines)


def build_context(disk_path: str | Path, quote: dict | None = None,
                  mode: str = "ask") -> str:
    """组装喂给模型的上下文：正文 ＋ 可选引用段 ＋ 可选检查报告摘要。"""
    blocks: list[str] = []
    if mode == "explain":
        summary = report_summary(disk_path)
        if summary:
            blocks.append("【检查报告摘要】\n" + summary)
    text = disk_text(disk_path)
    if text:
        blocks.append("【当前稿件正文】\n" + text)
    if quote:
        section = str(quote.get("section") or "").strip()
        quoted = str(quote.get("text") or "").strip()
        if quoted:
            head = "【用户引用的段落%s】" % ("（%s）" % section if section else "")
            blocks.append(head + "\n" + quoted)
    return "\n\n".join(blocks)


# ---------------------------------------------------------------- 降级

def simulated_reply(question: str = "", reason: str = "") -> str:
    """模拟回复。**首行必须是** `模拟回答（未接模型）`。"""
    lines = [FALLBACK_MARK,
             "后端没连上，下面这段不是模型的回答，只是占位，别当结论用。"]
    if reason:
        lines.append("（原因：%s）" % reason)
    if question:
        lines.append("（收到的提问：%s）" % question)
    lines.append("把 workbench.toml 的 [ai].base_url 指到能用的后端，再问一次。")
    return "\n".join(lines)


def _last_question(messages: list[dict]) -> str:
    for item in reversed(messages or []):
        if isinstance(item, dict) and item.get("role") == "user":
            return str(item.get("content") or "").strip()
    return ""


# ---------------------------------------------------------------- 主入口

def chat(disk_path: str | Path, messages: list[dict],
         quote: dict | None = None, mode: str = "ask",
         timeout: float = TIMEOUT) -> dict:
    """工作台的 AI 入口。

    返回结构**恒定**：
      `{"ok", "fallback", "reply", "model", "base_url", "code", "error"}`

    成功时 `ok=True, fallback=False`；后端不可达 / 超时 / 返回体不认时
    `ok=False, fallback=True`，且 `reply` 首行是 `模拟回答（未接模型）`。
    """
    config = ai_config(disk_path)
    history = [m for m in (messages or [])
               if isinstance(m, dict) and m.get("role")
               and isinstance(m.get("content"), str)]
    question = _last_question(history)
    context = build_context(disk_path, quote=quote, mode=mode)
    system = EXPLAIN_SYSTEM_PROMPT if mode == "explain" else SYSTEM_PROMPT
    payload: list[dict] = [{"role": "system", "content": system}]
    if context:
        payload.append({"role": "system", "content": context})
    payload.extend(history)
    try:
        reply = chat_completion(config["base_url"], config["model"], payload,
                                api_key=config["api_key"], timeout=timeout)
    except AIError as exc:
        return {
            "ok": False, "fallback": True,
            "reply": simulated_reply(question, str(exc)),
            "model": config["model"], "base_url": config["base_url"],
            "code": exc.code, "error": str(exc),
        }
    return {
        "ok": True, "fallback": False, "reply": reply,
        "model": config["model"], "base_url": config["base_url"],
        "code": "", "error": "",
    }
