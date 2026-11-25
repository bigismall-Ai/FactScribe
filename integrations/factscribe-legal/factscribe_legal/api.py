# -*- coding: utf-8 -*-
"""法律侧**只读接口层**：版本化 JSON 契约（七路通道）。

契约版本
--------
    version ＝ "factscribe-legal-api/1.0"（本件的 API_VERSION）

七路通道
--------
    findings    七条线各自的判定结果（码名/红黄/位置/措辞照抄各闸，不改写）
    receipts    统一五元组收据（id｜sha16｜span｜face｜how）
    corpus      语料件清单（只列真实可见的件；可按国家/域/状态过滤）
    codes       判定码表（码名＋中文短名＋红黄分级）
    timeliness  跨域统一时效字段（四种来源归一成同一形状）
    summary     各域 status/red/yellow ＋ 域级锁四键
    proposals   待批提案（本步只读 ⇒ 恒为空数组）

只读纪律
--------
本件**只读**：不写项目文件、不写语料、不建任何落盘动作、不碰系统钟、
零 LLM、零网络。接口层**不做判定**：红黄码照抄各闸，退出码语义不因本层改变。

本件不 import 上游 factscribe（宿主）⇒ 可以单独拷走单跑。
"""
import json
import os

from . import code_table
from . import corpus as corpus_mod
from . import lines as lines_mod
from . import lock as lock_mod
from . import receipts as receipts_mod
from . import timeliness as tl

__all__ = ["API_VERSION", "CHANNELS", "ApiContext", "build_contract",
           "context_from_project", "load_project_config", "render_human"]

API_VERSION = "factscribe-legal-api/1.0"

# 七路通道（契约的骨架；顺序即文档里的顺序）
CHANNELS = ("findings", "receipts", "corpus", "codes", "timeliness",
            "summary", "proposals")

# 本仓打包语料的根（相对本文件：integrations/factscribe-legal/corpus）
PACKAGED_CORPUS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "corpus")


class ApiContext:
    """接口层的只读上下文（全是从配置与目录结构读出来的路径与参考日）。"""

    def __init__(self, project_dir="", corpus_dir="", corpus_rel="", date="",
                 view="", catalog="", itcase_dir="", corpus_roots=None):
        self.project_dir = str(project_dir or "")
        self.corpus_dir = str(corpus_dir or "")
        self.corpus_rel = str(corpus_rel or "")
        self.date = str(date or "")
        self.view = str(view or "")
        self.catalog = str(catalog or "")
        self.itcase_dir = str(itcase_dir or "")
        self.corpus_roots = list(corpus_roots or [])

    def line_context(self):
        return lines_mod.LineContext(
            project_dir=self.project_dir,
            corpus_dir=self.corpus_dir,
            date=self.date,
            view=self.view,
            catalog=self.catalog,
            itcase_dir=self.itcase_dir)

    def roots(self):
        """要扫的语料根（项目语料视图 ＋ 本仓打包语料；去重、保序）。"""
        out = []
        for root in list(self.corpus_roots) + [self.corpus_dir,
                                               PACKAGED_CORPUS]:
            if root and root not in out and os.path.isdir(root):
                out.append(root)
        return out


def load_project_config(project_dir):
    """读项目的 factscribe.toml → [checks.legal] 表（缺则空表）。"""
    from ._toml import load_toml
    path = os.path.join(str(project_dir or ""), "factscribe.toml")
    if not os.path.isfile(path):
        return {}
    try:
        data = load_toml(path)
    except Exception:  # noqa: BLE001 —— 配置坏了不该穿透成堆栈
        return {}
    checks = data.get("checks") or {}
    table = checks.get("legal") or {}
    return table if isinstance(table, dict) else {}


def _find_catalog(corpus_dir):
    """语料视图里的中国全库目录（catalog.jsonl.gz 或 .jsonl）。"""
    if not corpus_dir:
        return ""
    for ext in (".jsonl.gz", ".jsonl"):
        cand = os.path.join(corpus_dir, "catalog" + ext)
        if os.path.isfile(cand):
            return cand
    return ""


def _find_itcase(corpus_dir):
    """语料视图里的意大利判例 run 目录（it-case/<run>/index.json）。"""
    if not corpus_dir:
        return ""
    base = os.path.join(corpus_dir, "it-case")
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            d = os.path.join(base, name)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "index.json")):
                return d
    # 语料视图根本身就是那份判例语料（打包形态：it-case/<run> 是 run 目录）
    try:
        with open(os.path.join(corpus_dir, "index.json"), encoding="utf-8") as fh:
            if "judgments" in json.load(fh):
                return corpus_dir
    except (OSError, ValueError):
        pass
    return ""


def context_from_project(project_dir, corpus=None, date=None, view=None,
                         catalog=None, itcase=None, corpus_roots=None):
    """按项目目录装配上下文（CLI 与 HTTP 路由共用这一条路径）。

    配置来源优先级：显式参数 ＞ 项目 factscribe.toml 的 [checks.legal]。
    """
    root = str(project_dir or "")
    table = load_project_config(root)
    corpus_rel = str(corpus if corpus is not None else table.get("corpus") or "")
    corpus_dir = (os.path.join(root, corpus_rel) if corpus_rel
                  and not os.path.isabs(corpus_rel) else corpus_rel)
    date_val = str(date if date is not None else table.get("date") or "")
    view_val = str(view if view is not None else table.get("view") or "")
    catalog_val = (str(catalog) if catalog else _find_catalog(corpus_dir))
    itcase_val = str(itcase) if itcase else _find_itcase(corpus_dir)
    return ApiContext(project_dir=root, corpus_dir=corpus_dir,
                      corpus_rel=corpus_rel, date=date_val, view=view_val,
                      catalog=catalog_val, itcase_dir=itcase_val,
                      corpus_roots=list(corpus_roots or []))


# ---------------------------------------------------------------------------
# 七路通道
# ---------------------------------------------------------------------------

def _channel_findings(results):
    lines_out = []
    total = red = yellow = 0
    for res in results:
        items = res.finding_dicts()
        lines_out.append({
            "line": res.line.id,
            "label": res.line.label,
            "country": res.line.country,
            "kind": res.line.kind,
            "gate": res.line.gate,
            "status": res.status,
            "note": res.note,
            "red": res.red,
            "yellow": res.yellow,
            "items": items,
        })
        total += len(items)
        red += res.red
        yellow += res.yellow
    return {"total": total, "red": red, "yellow": yellow, "lines": lines_out}


def _channel_receipts(results):
    lines_out = []
    total = 0
    for res in results:
        lines_out.append({
            "line": res.line.id,
            "label": res.line.label,
            "country": res.line.country,
            "kind": res.line.kind,
            "gate": res.line.gate,
            "status": res.status,
            "total": len(res.receipts),
            "items": res.receipts,
        })
        total += len(res.receipts)
    return {"total": total, "fields": list(receipts_mod.RECEIPT_FIELDS),
            "missing_marker": receipts_mod.MISSING, "lines": lines_out}


def _scan_all_items(ctx):
    """扫全部语料根 → 件清单（真实件；去重按 root+域+id）。"""
    seen = set()
    items = []
    for root in ctx.roots():
        for it in corpus_mod.scan_corpus(root, ctx.date):
            # 去重键含 path：同一个条文 id 在不同 run 下是**不同的件**
            # （仓内 IT 切片 4 件里有两件都叫 art_2，分属两个 run）
            key = (root, it.get("path"), it.get("domain"), it.get("id"))
            if key in seen:
                continue
            seen.add(key)
            item = dict(it)
            item["root"] = root
            items.append(item)
    return items


def _keep_item(item, filters):
    filters = filters or {}
    if filters.get("country") and item.get("country") != filters["country"]:
        return False
    if filters.get("domain") and item.get("domain") != filters["domain"]:
        return False
    if filters.get("line") and item.get("domain") != filters["line"]:
        return False
    state = filters.get("state")
    if state and (item.get("timeliness") or {}).get("state") != state:
        return False
    kind = filters.get("kind")
    if kind and item.get("kind") != kind:
        return False
    return True


def _channel_corpus(ctx, items, filters):
    kept = [it for it in items if _keep_item(it, filters)]
    return {"total": len(kept), "roots": ctx.roots(),
            "filters": dict(filters or {}), "items": kept}


def _channel_codes(filters):
    items = code_table.as_dicts()
    filters = filters or {}
    if filters.get("domain"):
        items = [i for i in items if i["domain"] == filters["domain"]]
    if filters.get("line"):
        items = [i for i in items if i["domain"] == filters["line"]]
    if filters.get("severity"):
        items = [i for i in items if i["severity"] == filters["severity"]]
    counts = code_table.counts()
    return {"total": len(items), "red": counts["red"], "yellow": counts["yellow"],
            "table_total": counts["total"], "items": items}


def _channel_timeliness(items, filters):
    kept = []
    for it in items:
        if not _keep_item(it, filters):
            continue
        t = it.get("timeliness")
        if t:
            kept.append(t)
    return {"total": len(kept), "states": list(tl.STATES), "items": kept}


def _lock_view(ctx):
    """域级锁四键（现算 ＋ 锁件里的值 ＋ 是否一致）。"""
    index_sha = lock_mod.index_sha256(ctx.corpus_dir)
    current = lock_mod.canonical_sha256(ctx.corpus_rel, ctx.date, ctx.view,
                                        index_sha)
    frozen = lock_mod.read_lock(ctx.project_dir)
    view = {
        "path": lock_mod.LOCK_REL,
        "keys": list(lock_mod.LOCK_KEYS),
        "corpus": ctx.corpus_rel,
        "date": ctx.date,
        "view": ctx.view,
        "index_sha256": index_sha,
        "current_canonical_sha256": current,
        "frozen": bool(frozen.get("frozen")),
        "frozen_canonical_sha256": frozen.get("canonical_sha256", ""),
        "frozen_keys": {k: frozen.get(k, "") for k in lock_mod.LOCK_KEYS},
        "last_action": lock_mod.log_last_action(ctx.project_dir),
    }
    if not view["frozen"]:
        view["matches"] = None
    else:
        view["matches"] = (view["frozen_canonical_sha256"] == current)
    if frozen.get("error"):
        view["error"] = frozen["error"]
    return view


def _channel_summary(ctx, results):
    lines_out = []
    red = yellow = 0
    for res in results:
        lines_out.append({"line": res.line.id, "label": res.line.label,
                          "status": res.status, "note": res.note,
                          "red": res.red, "yellow": res.yellow})
        red += res.red
        yellow += res.yellow
    return {"domain": "legal", "red": red, "yellow": yellow, "hints": 0,
            "corpus": ctx.corpus_rel, "date": ctx.date, "view": ctx.view,
            "lines": lines_out, "lock": _lock_view(ctx)}


def _channel_proposals():
    return {
        "total": 0,
        "items": [],
        "note": ("待批提案通道属第 ② 步（UI 与提议存储）：本步只读，"
                 "恒返回空数组，不建任何写路径。"),
    }


# ---------------------------------------------------------------------------
# 契约装配
# ---------------------------------------------------------------------------

def build_contract(ctx, channels=None, filters=None, line_ids=None):
    """装配完整契约（只读）。channels 给了就只装那几路。"""
    wanted = set(channels) if channels else set(CHANNELS)
    out = {
        "version": API_VERSION,
        "schema": API_VERSION,
        "generated_by": "factscribe-legal api",
        "read_only": True,
        "project": ctx.project_dir,
        "reference_date": ctx.date,
    }
    results = []
    items = []
    if "findings" in wanted or "receipts" in wanted or "summary" in wanted:
        results = lines_mod.collect(ctx.line_context(), line_ids)
    if "corpus" in wanted or "timeliness" in wanted:
        items = _scan_all_items(ctx)
    if "findings" in wanted:
        out["findings"] = _channel_findings(results)
    if "receipts" in wanted:
        out["receipts"] = _channel_receipts(results)
    if "corpus" in wanted:
        out["corpus"] = _channel_corpus(ctx, items, filters)
    if "codes" in wanted:
        out["codes"] = _channel_codes(filters)
    if "timeliness" in wanted:
        out["timeliness"] = _channel_timeliness(items, filters)
    if "summary" in wanted:
        out["summary"] = _channel_summary(ctx, results)
    if "proposals" in wanted:
        out["proposals"] = _channel_proposals()
    return out


def render_human(contract):
    """把契约渲染成人读摘要（与 JSON 同源；给人看，不给机器解析）。"""
    out = ["== factscribe-legal api（只读接口层）==",
           "契约版本：%s    参考日：%s" % (contract.get("version", ""),
                                        contract.get("reference_date", "") or "（未定）")]
    findings = contract.get("findings")
    if findings:
        out.append("")
        out.append("判定结果：%d 条（红 %d / 黄 %d）"
                   % (findings.get("total", 0), findings.get("red", 0),
                      findings.get("yellow", 0)))
        for ln in findings.get("lines", []):
            out.append("  %-8s %-12s %-8s 红%d/黄%d  %s"
                       % (ln.get("line"), ln.get("label"), ln.get("status"),
                          ln.get("red", 0), ln.get("yellow", 0),
                          ln.get("note", "") or ""))
    receipts = contract.get("receipts")
    if receipts:
        out.append("")
        out.append("收据（id｜sha16｜span｜face｜how）：%d 条"
                   % receipts.get("total", 0))
        for ln in receipts.get("lines", []):
            for it in ln.get("items", []):
                out.append("  %s｜%s｜%s｜%s｜%s"
                           % (it.get("id", "—"), it.get("sha16", "—"),
                              it.get("span", "—"), it.get("face", "—"),
                              it.get("how", "—")))
    corpus = contract.get("corpus")
    if corpus:
        out.append("")
        out.append("语料件清单：%d 件" % corpus.get("total", 0))
    codes = contract.get("codes")
    if codes:
        out.append("")
        out.append("判定码表：%d 个（红 %d / 黄 %d）"
                   % (codes.get("total", 0), codes.get("red", 0),
                      codes.get("yellow", 0)))
    timeliness = contract.get("timeliness")
    if timeliness:
        out.append("")
        out.append("时效（跨域统一形状）：%d 条" % timeliness.get("total", 0))
        for it in timeliness.get("items", []):
            out.append("  %-10s %-22s %-16s %s"
                       % (it.get("domain"), it.get("item_id"),
                          it.get("state"), it.get("source")))
    summary = contract.get("summary")
    if summary:
        lock = summary.get("lock") or {}
        out.append("")
        out.append("域级锁：%s（%s）"
                   % ("已冻结" if lock.get("frozen") else "未冻结",
                      "一致" if lock.get("matches") else
                      ("不一致" if lock.get("matches") is False else "—")))
        out.append("  四键：corpus=%s｜date=%s｜index_sha256=%s｜view=%s"
                   % (lock.get("corpus", "") or "—",
                      lock.get("date", "") or "—",
                      (lock.get("index_sha256", "") or "—")[:16],
                      lock.get("view", "") or "—"))
    proposals = contract.get("proposals")
    if proposals:
        out.append("")
        out.append("待批提案：%d 条（%s）" % (proposals.get("total", 0),
                                            proposals.get("note", "")))
    return "\n".join(out)
