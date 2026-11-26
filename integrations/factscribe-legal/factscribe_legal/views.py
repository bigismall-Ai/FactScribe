# -*- coding: utf-8 -*-
"""法律侧**读侧视图**（第 ② 步）：单件详情／文书分段／条→事实反查／CLI 清单。

第 ① 步的七路通道给的是**跨域同构的总表**（件清单、收据总表、码表、时效表、
锁）。工作台页面要的是**逐件**与**逐段**的视图——那四条第 ① 步没做，本件补上：

    单件详情     GET /api/legal/corpus/{id}           件详情 ＋ 该件的收据视图
    文书分段     GET /api/legal/document               段落 ＋ 引证标记 ＋ 官方逐字片段
    条→事实反查  GET /api/legal/provision/{num}/facts  哪条事实引了这一条
    CLI 清单     GET /api/legal/cli                    子命令清单（从 argparse 现取）

纪律
----
* **只读**：不写盘、不联网、不碰系统钟、不改任何判定语义、不改退出码。
* **不另造一套**：语料件来自 corpus 扫描、收据来自共用生产逻辑（receipts.py）、
  时效来自 timeliness.py、码表来自 code_table.py——页面看到的每一格都能追回
  第 ① 步的通道。
* **看不到就不写**：取不到的值一律写缺省标记「—」，不编造件数与条款号。
"""
import argparse
import glob
import os
import re

from . import corpus as corpus_mod
from . import lines as lines_mod
from . import receipts as receipts_mod
from ._toml import load_toml
from .case_verify import CASE_CARD_RE
from .cn_verify import CARD_RE as CN_CARD_RE
from .es_verify import _plain_text as _es_plain_text
from .fr_case_verify import CARD_RE as FR_CASE_CARD_RE
from .it_case_verify import _itcase_plain
from .it_verify import _plain_text as _it_plain_text
from .verify import PROV_RE, load_facts

__all__ = ["cli_manifest", "document_segments", "fingerprint_of",
           "item_detail", "provision_facts"]

# 事实来源 → 域（卡后缀定域；法国法条走 PROV_RE 的编号）
_CARD_DOMAIN = (
    (".fr-case.card.txt", "fr-case"),
    (".itcase.card.txt", "it-case"),
    (".case.card.txt", "case"),
    (".cn.card.txt", "cn"),
    (".it.card.txt", "it"),
    (".es.card.txt", "es"),
)

_CARD_SUFFIXES = tuple(suffix for suffix, _ in _CARD_DOMAIN)

# 正文里的账目绑定标记：\fact{ID} 或 \fact{ID}{值}
_MARKER_RE = re.compile(r"\\fact\{([^}]*)\}(?:\s*\{([^}]*)\})?")

# 段分隔（空行；认 CRLF）
_PARA_RE = re.compile(r"\r?\n[ \t]*\r?\n")

# 语料件上可能钉着官方哈希的字段（指纹闸用）
_ITEM_SHA_FIELDS = ("txt_sha256", "xml_sha256", "detail_sha256",
                    "article_sha256", "card_sha256", "source_sha256")


def _read_text(path):
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()
    except OSError:
        return ""


def _read_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return b""


# --------------------------------------------------------------------- 键与域

def fact_domain(src):
    """事实来源 → 域 id（取不到 → 空串）。"""
    src = str(src or "")
    for suffix, domain in _CARD_DOMAIN:
        if src.endswith(suffix):
            return domain
    if PROV_RE.match(src):
        return "fr"
    return ""


def fact_keys(src):
    """事实来源 → 它指向的官方件键集合（法条号／案号／卡名）。"""
    src = str(src or "")
    keys = set()
    domain = fact_domain(src)
    if domain == "fr-case":
        m = FR_CASE_CARD_RE.match(src)
        if m:
            keys.add(m.group("case_id"))
    elif domain == "case":
        m = CASE_CARD_RE.match(src)
        if m:
            keys.add(m.group("slug"))
            keys.add(os.path.basename(m.group("slug")))
    elif domain == "cn":
        m = CN_CARD_RE.match(src)
        if m:
            keys.add(m.group("slug"))
            keys.add(os.path.basename(m.group("slug")))
    elif domain in ("it", "es", "it-case"):
        base = os.path.basename(src)
        for suffix in _CARD_SUFFIXES:
            if base.endswith(suffix):
                keys.add(base[:-len(suffix)])
    elif domain == "fr":
        m = PROV_RE.match(src)
        if m:
            keys.add(m.group("num"))
    return keys


def item_keys(item):
    """语料件 → 它自己的键集合（id、路径文件名、卡名）。"""
    keys = set()
    if item.get("id"):
        keys.add(str(item.get("id")))
    path = str(item.get("path") or "")
    if path:
        base = os.path.basename(path)
        keys.add(base.rsplit(".", 1)[0] if "." in base else base)
    meta = item.get("meta") or {}
    for field in ("card_file", "txt_file", "xml_file", "article_file",
                  "slice_file"):
        val = str(meta.get(field) or "")
        if not val:
            continue
        base = os.path.basename(val)
        keys.add(base.rsplit(".", 1)[0] if "." in base else base)
        for suffix in _CARD_SUFFIXES:
            if base.endswith(suffix):
                keys.add(base[:-len(suffix)])
    return keys


def link_facts(item, facts):
    """哪些事实指向这件（同域 ＋ 键相交）。"""
    domain = item.get("domain")
    ikeys = item_keys(item)
    out = []
    for fact in facts:
        if fact_domain(fact.get("source")) != domain:
            continue
        if ikeys & fact_keys(fact.get("source")):
            out.append(fact)
    return out


# ----------------------------------------------------------------- 收据索引

def receipt_index(ctx, line_ids=None):
    """{事实 id: [{"line","gate","receipt"}]}——收据来自共用生产逻辑。"""
    out = {}
    for res in lines_mod.collect(ctx.line_context(), line_ids):
        for rec in res.receipts:
            out.setdefault(str(rec.get("id")), []).append(
                {"line": res.line.id, "gate": res.line.gate, "receipt": rec})
    return out


# --------------------------------------------------------------- 官方正文取文

def official_text_for(ctx, item, fact):
    """官方正文（与该条收据的 span 同源的那份文本）→ (text, 相对路径)。

    取不到 → (None, "")。**不猜**：取不到就留空，让页面写「未取到」。
    """
    src = str(fact.get("source") or "")
    domain = (item or {}).get("domain") or fact_domain(src)
    if domain == "fr-case":
        m = FR_CASE_CARD_RE.match(src)
        if not m:
            return None, ""
        run, case_id = m.group("run"), m.group("case_id")
        rel = os.path.join("runs", run, "official", case_id + ".txt")
        text = _read_text(os.path.join(ctx.project_dir, rel))
        return (text, rel.replace(os.sep, "/")) if text else (None, "")
    if domain == "case":
        m = CASE_CARD_RE.match(src)
        if not m:
            return None, ""
        run, slug = m.group("run"), m.group("slug")
        rel = os.path.join("runs", run, "official", slug + ".txt")
        text = _read_text(os.path.join(ctx.project_dir, rel))
        return (text, rel.replace(os.sep, "/")) if text else (None, "")
    if domain == "fr":
        text = lines_mod.fr_official_text(ctx, src)
        return (text, src) if text else (None, "")
    if domain in ("it", "es", "it-case"):
        root = str((item or {}).get("root") or "")
        rel = str((item or {}).get("path") or "")
        if not root or not rel:
            return None, ""
        raw = _read_bytes(os.path.join(root, rel))
        if not raw:
            return None, ""
        if domain == "it":
            text = _it_plain_text(raw.decode("utf-8", "replace"))
        elif domain == "es":
            text = _es_plain_text(raw.decode("utf-8", "replace"))
        else:
            text = _itcase_plain(raw)
        return (text, rel.replace(os.sep, "/")) if text else (None, "")
    return None, ""


def _slice_span(text, span):
    """按收据的 span 区间切出官方逐字片段（span 取不到 → 空串）。"""
    raw = str(span or "")
    if not raw or raw == receipts_mod.MISSING:
        return ""
    m = re.match(r"^(\d+)-(\d+)$", raw)
    if not m:
        return ""
    start, end = int(m.group(1)), int(m.group(2))
    if start < 0 or end > len(text) or start >= end:
        return ""
    return text[start:end]


# ------------------------------------------------------------------- 单件详情

def _items(ctx):
    return corpus_mod.scan_all_roots(ctx.roots(), ctx.date)


def _find_items(ctx, item_id, domain=""):
    out = []
    for item in _items(ctx):
        if str(item.get("id")) != str(item_id):
            continue
        if domain and item.get("domain") != domain:
            continue
        out.append(item)
    return out


def item_detail(ctx, item_id, domain=""):
    """单件详情 ＋ 该件的收据视图。找不到 → None。"""
    cands = _find_items(ctx, item_id, domain)
    if not cands:
        return None
    item = cands[0]
    facts = load_facts(ctx.project_dir)
    linked = link_facts(item, facts)
    index = receipt_index(ctx, [item.get("domain")])
    rows = []
    for fact in linked:
        for entry in index.get(str(fact.get("id"))) or []:
            row = dict(entry["receipt"])
            row["fact"] = {
                "id": fact.get("id", ""),
                "claim": fact.get("claim", ""),
                "value": fact.get("value"),
                "source": fact.get("source", ""),
                "location": "%s:%s" % (fact.get("_file", ""), fact.get("id", "")),
                "file": fact.get("_file", ""),
            }
            rows.append(row)
    line = lines_mod.line_by_id(item.get("domain")) or lines_mod.LINES[0]
    return {
        "version": "factscribe-legal-api/1.0",
        "view": "corpus_item",
        "id": str(item_id),
        "ambiguous": len(cands) > 1,
        "candidates": [{"id": c.get("id", ""), "domain": c.get("domain", ""),
                        "path": c.get("path", ""), "root": c.get("root", ""),
                        "title": c.get("title", ""),
                        "kind": c.get("kind", "")} for c in cands],
        "item": item,
        "receipts": {
            "fields": list(receipts_mod.RECEIPT_FIELDS),
            "missing_marker": receipts_mod.MISSING,
            "total": len(rows),
            "items": rows,
            "line": line.id,
            "gate": line.gate,
            "note": "",
        },
        "note": "",
    }


# ------------------------------------------------------------------- 文书分段

def _project_sections(project_dir):
    """项目配置里的 sections 图案 → 实际文件列表（相对项目目录的排序）。"""
    path = os.path.join(str(project_dir or ""), "factscribe.toml")
    if not os.path.isfile(path):
        return []
    try:
        data = load_toml(path)
    except Exception:  # noqa: BLE001 —— 配置坏了不该穿透成堆栈
        return []
    project = data.get("project") or {}
    pattern = str(project.get("sections") or "").strip()
    if not pattern:
        return []
    if not os.path.isabs(pattern):
        pattern = os.path.join(str(project_dir), pattern)
    return sorted(glob.glob(pattern))


def document_segments(ctx):
    """文书分段：段落 ＋ 引证标记 ＋ 官方逐字片段（与收据同源）。"""
    files = _project_sections(ctx.project_dir)
    facts = load_facts(ctx.project_dir)
    by_id = {}
    for fact in facts:
        by_id.setdefault(str(fact.get("id")), fact)
    needed = []
    for fact in facts:
        domain = fact_domain(fact.get("source"))
        if domain and domain not in needed:
            needed.append(domain)
    index = receipt_index(ctx, needed) if needed else {}
    items = _items(ctx)
    paragraphs = []
    rel_files = []
    for path in files:
        text = _read_text(path)
        if not text:
            continue
        rel = os.path.relpath(path, ctx.project_dir).replace(os.sep, "/")
        rel_files.append(rel)
        for chunk in _PARA_RE.split(text):
            body = chunk.strip()
            if not body:
                continue
            markers = []
            for hit in _MARKER_RE.finditer(body):
                fact_id = (hit.group(1) or "").strip()
                value = (hit.group(2) or "").strip()
                marker = {"fact_id": fact_id, "value": value}
                fact = by_id.get(fact_id)
                if fact is not None:
                    marker["claim"] = fact.get("claim", "")
                    marker["source"] = fact.get("source", "")
                    marker["location"] = "%s:%s" % (fact.get("_file", ""),
                                                    fact_id)
                    entries = index.get(fact_id) or []
                    if entries:
                        receipt = dict(entries[0]["receipt"])
                        marker["receipt"] = receipt
                        item = _item_for_fact(items, fact)
                        official, official_rel = official_text_for(ctx, item,
                                                                  fact)
                        excerpt = _slice_span(official, receipt.get("span"))
                        if official is not None:
                            marker["official"] = {
                                "text": excerpt,
                                "span": receipt.get("span", ""),
                                "face": receipt.get("face", ""),
                                "source": official_rel,
                            }
                markers.append(marker)
            paragraphs.append({"index": len(paragraphs), "file": rel,
                               "text": body, "markers": markers})
    return {
        "version": "factscribe-legal-api/1.0",
        "view": "document",
        "total": len(paragraphs),
        "sections": rel_files,
        "paragraphs": paragraphs,
        "note": ("段落来自项目 factscribe.toml 的 sections；标记是正文里的"
                 "\\fact{ID}。没有 sections 或没有标记的段落照实列出，"
                 "不补连接语。"),
    }


def _item_for_fact(items, fact):
    """这条事实指向哪个语料件（找不到 → None）。"""
    domain = fact_domain(fact.get("source"))
    keys = fact_keys(fact.get("source"))
    for item in items:
        if item.get("domain") != domain:
            continue
        if keys & item_keys(item):
            return item
    return None


# --------------------------------------------------------------- 条→事实反查

def provision_facts(ctx, num):
    """条→事实反查：哪条事实引了这一条（收据 ＋ 件 ＋ 时效）。"""
    wanted = str(num or "").strip()
    facts = load_facts(ctx.project_dir)
    items = _items(ctx)
    index = receipt_index(ctx) if facts else {}
    rows = []
    for fact in facts:
        if wanted not in fact_keys(fact.get("source")):
            continue
        item = _item_for_fact(items, fact)
        entries = index.get(str(fact.get("id"))) or []
        rows.append({
            "fact_id": fact.get("id", ""),
            "claim": fact.get("claim", ""),
            "value": fact.get("value"),
            "source": fact.get("source", ""),
            "location": "%s:%s" % (fact.get("_file", ""), fact.get("id", "")),
            "receipt": dict(entries[0]["receipt"]) if entries else None,
            "corpus_item": ({"id": item.get("id", ""),
                             "title": item.get("title", ""),
                             "path": item.get("path", ""),
                             "domain": item.get("domain", "")}
                            if item else None),
            "timeliness": (item.get("timeliness") if item else None),
        })
    return {
        "version": "factscribe-legal-api/1.0",
        "view": "provision_facts",
        "num": wanted,
        "total": len(rows),
        "items": rows,
        "note": "",
    }


# ------------------------------------------------------------------- CLI 清单

def _subparsers(parser):
    """{子命令名: (短帮助文本, 子解析器)}——短帮助取父解析器里的登记项。"""
    out = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            short = {ch.dest: str(ch.help or "")
                     for ch in getattr(action, "_choices_actions", [])}
            for name, sub in action.choices.items():
                out[name] = (short.get(name, ""), sub)
    return out


def _group_of(name):
    if name.startswith("cn-lead-"):
        return "线索层（第三方检索，非官方核验）"
    if name == "api":
        return "接口层（只读 JSON 出口）"
    if name == "fetch":
        return "取件（把法条物化进项目）"
    return "核验入口（闸）"


def cli_manifest():
    """CLI 清单：从 argparse 现取（不另抄一份，避免与真实命令漂移）。"""
    from . import cli as cli_mod
    parser = cli_mod.build_parser()
    choices = _subparsers(parser)
    items = []
    for name in sorted(choices):
        short_help, sub = choices[name]
        args = []
        for action in sub._actions:
            if not action.option_strings:
                continue
            args.append({"name": action.option_strings[0],
                         "required": bool(action.required),
                         "help": str(action.help or "")})
        items.append({"name": name, "group": _group_of(name),
                      "help": short_help or str(sub.description or ""),
                      "args": args})
    return {
        "version": "factscribe-legal-api/1.0",
        "view": "cli",
        "total": len(items),
        "items": items,
        "note": ("子命令清单从 argparse 现取：既有 11 条命令的输出与退出码"
                 "一字未动；api 族是第 12 条（只读 JSON 出口）。"),
    }


# ------------------------------------------------------------------- 指纹闸

def fingerprint_of(ctx, target):
    """现算目标指纹 → {"source": 来源说明, "current": 指纹值}。

    * scope=receipt：那条收据的 sha16（事实账钉的来源哈希前 16 位）；
    * scope=item：语料件 meta 上钉的官方哈希前 16 位；
    * scope=fact：事实账钉的 source_sha256 前 16 位。

    取不到 → current 为空串（此时采纳一律拒写：核对不了就不写）。
    """
    target = target or {}
    scope = str(target.get("scope") or "")
    if scope == "receipt":
        fact_id = str(target.get("fact_id") or "")
        index = receipt_index(ctx)
        for entry in index.get(fact_id) or []:
            rec = entry["receipt"]
            return {"source": "收据 %s 的 sha16（事实账钉的来源哈希前 16 位）"
                               % fact_id,
                    "current": str(rec.get("sha16") or "")}
        return {"source": "收据 %s 的 sha16" % fact_id, "current": ""}
    if scope == "item":
        item_id = str(target.get("item_id") or "")
        cands = _find_items(ctx, item_id, str(target.get("domain") or ""))
        if not cands:
            return {"source": "语料件 %s 的官方哈希" % item_id, "current": ""}
        meta = cands[0].get("meta") or {}
        for field in _ITEM_SHA_FIELDS:
            val = str(meta.get(field) or "").strip().lower()
            if val:
                return {"source": "语料件 %s 的 meta.%s" % (item_id, field),
                        "current": val[:16]}
        return {"source": "语料件 %s 的官方哈希" % item_id, "current": ""}
    if scope == "fact":
        fact_id = str(target.get("fact_id") or "")
        for fact in load_facts(ctx.project_dir):
            if str(fact.get("id")) != fact_id:
                continue
            sha = str(fact.get("source_sha256") or "").strip().lower()
            if sha.startswith("sha256:"):
                sha = sha[len("sha256:"):]
            return {"source": "事实 %s 的 source_sha256 前 16 位" % fact_id,
                    "current": sha[:16]}
        return {"source": "事实 %s 的 source_sha256" % fact_id, "current": ""}
    return {"source": "未识别的目标作用域（%s）" % (scope or "空"),
            "current": ""}
