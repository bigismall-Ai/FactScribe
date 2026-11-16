# -*- coding: utf-8 -*-
"""legal 核验包：把四闸（FR／CN／CASE／IT）组装成核验槽的一个包（M2）。

本模块是「legal 卡」的代码面（SPEC-CHECKS §3.1 一张卡写死五样）：

* ``domain_id = "legal"``（全局唯一；配置节 ``[checks.legal]``）；
* 冻结码表＝本包 README「码表（冻结）」节（``LEGAL_/CN_/CASE_/IT_`` 前缀，
  只增不改名不改义不改 severity）。本批新增三码（§4.4 minor，出处材料
  依赖的 fail-closed 语义）：``LEGAL_DATE_INVALID``（红）、
  ``LEGAL_EVIDENCE_CHANGED``（红）、``LEGAL_EVIDENCE_UNFROZEN``（黄）；
* ``config_keys = {corpus, date, view}``；
* 材料依赖声明（**fail-closed 表**：材料缺失必须亮黄/红，禁止静默绿）：

  ================  =====================================================
  情形               行为
  =================  =====================================================
  corpus 未声明／     黄 ``LEGAL_COVERAGE_GAP``（法律域 0 覆盖，亮出）；
  目录不存在／        FR 闸不跑
  缺 index.json
  有 CN 事项而        黄 ``LEGAL_COVERAGE_GAP``（每闸一条，带事项数）；
  catalog 没拿到      CN 闸不跑
  有 IT 事项而        黄 ``LEGAL_COVERAGE_GAP``（同上）；IT 闸不跑
  it/ 语料没拿到
  date 缺失或非       红 ``LEGAL_DATE_INVALID``（时效类判据全跳过；
  YYYY-MM-DD          参考日是法律域判据的根基，缺它不许「仅建议」）
  CASE 闸             材料全在项目内（runs/<run>/），永远可跑
  =================  =====================================================

* ``verify(cfg, facts, sections, resolve=False) → (red, yellow, hints,
  summary, unresolved)``：纯函数——只读项目与语料，零 LLM、零网络、
  不读系统钟、不写盘。summary 是 legal 域自己的信封（含 ``lines``——
  槽按域分节时的人读域头，core 渲染器只认这个键，不懂域义）。

材料布局约定（卡上写死；真实管线布局按此归拢，合成语料同形）::

    <corpus>/                     # 语料视图（[checks.legal] corpus 指向这里）
      index.json                  # FR 语料索引（provisions 字段；M0 布局照旧）
      <num>.xml / official/…      # FR 官方件（index.json 的 xml_file 相对路径）
      catalog.jsonl.gz|.jsonl     # CN 全库目录（可选；有中国事项才必需）
      it/                         # IT 语料（可选；有意大利事项才必需）
        index.json                #   articles+source_file+哈希（verify-it 现状形状）

import 方向（裁定，M2）：**本模块是 factscribe_legal 里唯一 import 上游
factscribe 的模块**，且只在核验槽点名 legal 时才经 ``checks.load_integration()``
载入（check-package.toml 声明）；其余模块与五子命令保持零上游依赖、可单独
拷走单跑。载入方向＝扩展件 import 宿主；宿主 core 只认 check-package.toml
的声明，不反向依赖——「integrations 独立、可卸载」先例不破。
"""
import os
import re

from factscribe import checks
from factscribe.audit import Issue

from ._toml import load_toml
from .case_verify import verify_case
from .cn_verify import verify_cn
from .it_verify import verify_it
from .verify import PROV_RE, load_citations, load_facts
from .verify import verify as verify_fr

DOMAIN_ID = "legal"
CONFIG_KEYS = frozenset({"corpus", "date", "view"})
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
GATE_ORDER = ("fr", "cn", "case", "it")


def _issue(code, severity, message, location="", token="", context=""):
    """legal Finding 语义 → factscribe 信封 Issue（红黄语义零改动）。"""
    return Issue(code=code, message=message, location=location, token=token,
                 context=context, severity=severity, exit_code=1)


def _coverage_gap(message, location="checks.legal"):
    return _issue("LEGAL_COVERAGE_GAP", "yellow", message, location=location)


def _gate_note(status, red_n, yellow_n, note=""):
    return {"status": status, "red": red_n, "yellow": yellow_n, "note": note}


def _convert(findings):
    """闸的 findings → (red, yellow) 两串 Issue（码、severity、文案零改动）。"""
    reds, yellows = [], []
    for f in findings:
        issue = _issue(f.code, f.severity, f.message, location=f.location,
                       context=f.detail)
        (reds if f.severity == "red" else yellows).append(issue)
    return reds, yellows


def _gate_scope(project_dir):
    """按各闸既有归属规则数「事项」：事实账指向各域卡的 source 数＋正文引用数。

    与四闸自身的归属判据同一套（INTEGRATION-LEGAL §5.1：靠文件名后缀，
    不靠卡内标记），只用于「材料没拿到时该不该 fail-closed」的计数。
    """
    scope = {"fr": 0, "cn": 0, "case": 0, "it": 0}
    for fact in load_facts(project_dir):
        src = str(fact.get("source") or "")
        if src.endswith(".cn.card.txt"):
            scope["cn"] += 1
        elif src.endswith(".case.card.txt"):
            scope["case"] += 1
        elif src.endswith(".it.card.txt"):
            scope["it"] += 1
        elif PROV_RE.match(src):
            scope["fr"] += 1
    for key, _rel, _line in load_citations(project_dir):
        if re.search(r"[\u4e00-\u9fff]", key):
            scope["cn"] += 1
        elif key.startswith("art-it-"):
            scope["it"] += 1
        elif key.startswith("art:") or key.startswith("art-"):
            scope["fr"] += 1
    return scope


def verify_legal(cfg, facts, sections, resolve: bool = False):
    """legal 核验包的 verify（协议 v1）：跑四闸，fail-closed 收材料缺口。"""
    del facts, sections, resolve          # 闸自己按项目约定读账与正文
    table = dict((getattr(cfg, "checks_tables", {}) or {}).get(DOMAIN_ID)
                 or {})
    project_dir = str(cfg.root)
    red, yellow, hints = [], [], []
    gates = {g: _gate_note("na", 0, 0, "0 事项") for g in GATE_ORDER}

    corpus_rel = str(table.get("corpus") or "").strip()
    date = str(table.get("date") or "").strip()
    view_rel = str(table.get("view") or "").strip()

    # ---- 参考日（fail-closed：缺/非法＝红，时效类三闸全跳过）----
    if not DATE_RE.match(date):
        red.append(_issue(
            "LEGAL_DATE_INVALID", "red",
            "[checks.legal] 的 date 缺失或不是 YYYY-MM-DD（现值 %r）——"
            "参考日是法律域时效判据的根基，缺它不许跑也不许只给建议"
            "（fail-closed）" % (date or "空"),
            location="factscribe.toml [checks.legal] date", token=date))
        gates["date"] = _gate_note("invalid", 1, 0, "date 缺失或非法")
        date = ""

    # ---- 语料视图（fail-closed：缺＝黄，0 覆盖亮出）----
    corpus_dir = ""
    cn_catalog = ""
    it_material_ok = cn_material_ok = False
    if not corpus_rel:
        yellow.append(_coverage_gap(
            "[checks.legal] 没有声明 corpus——法律域 0 覆盖（fail-closed："
            "语料视图是出处材料的唯一声明位，缺它不许静默绿）"))
    elif not os.path.isdir(os.path.join(project_dir, corpus_rel)) or \
            not os.path.exists(os.path.join(project_dir, corpus_rel,
                                            "index.json")):
        yellow.append(_coverage_gap(
            "语料视图 %s 不可用（目录或 index.json 不存在）——法律域 0 覆盖"
            "（fail-closed）" % corpus_rel))
    else:
        corpus_dir = os.path.join(project_dir, corpus_rel)
        it_material_ok = os.path.exists(
            os.path.join(corpus_dir, "it", "index.json"))
        for ext in (".jsonl.gz", ".jsonl"):
            cand = os.path.join(corpus_dir, "catalog" + ext)
            if os.path.exists(cand):
                cn_catalog = cand
                cn_material_ok = True
                break

    scope = _gate_scope(project_dir)

    # ---- FR 闸（法国：法条存在／参考日生效／官方字节哈希／值出自正文）----
    if corpus_dir and date:
        try:
            fr_findings, _corpus = verify_fr(project_dir, corpus_dir, date,
                                             view_rel or None)
        except FileNotFoundError as exc:
            yellow.append(_coverage_gap(
                "FR 语料读不了（%s）——法国闸 0 覆盖（fail-closed）" % exc))
            gates["fr"] = _gate_note("skipped", 0, 0, "语料读不了")
        else:
            r, y = _convert(fr_findings)
            red += r
            yellow += y
            gates["fr"] = _gate_note("ran", len(r), len(y),
                                     "%d 条事项" % scope["fr"])
    else:
        gates["fr"] = _gate_note(
            "skipped", 0, 0,
            "语料不可用" if not corpus_dir else "date 未定，时效判据全跳过")

    # ---- CN 闸（中国法条：现行有效／条文号存在／官方件未变）----
    if cn_material_ok and date:
        r, y = _convert(verify_cn(project_dir, cn_catalog, date))
        red += r
        yellow += y
        gates["cn"] = _gate_note("ran", len(r), len(y), "%d 条事项" % scope["cn"])
    elif not cn_material_ok and scope["cn"] > 0:
        yellow.append(_coverage_gap(
            "事实账/正文有 %d 条中国法条事项，但语料视图里没有 catalog"
            "（<corpus>/catalog.jsonl.gz）——中国闸 0 覆盖（fail-closed）"
            % scope["cn"]))
        gates["cn"] = _gate_note("skipped", 0, 0, "catalog 没拿到")
    else:
        gates["cn"] = _gate_note(
            "skipped" if cn_material_ok else "na", 0, 0,
            "date 未定，时效判据全跳过" if cn_material_ok else "0 事项")

    # ---- IT 闸（意大利：官方 AKN 哈希／切片哈希／值出自条文）----
    if it_material_ok and date:
        it_findings, _index = verify_it(project_dir,
                                        os.path.join(corpus_dir, "it"), date)
        r, y = _convert(it_findings)
        red += r
        yellow += y
        gates["it"] = _gate_note("ran", len(r), len(y), "%d 条事项" % scope["it"])
    elif not it_material_ok and scope["it"] > 0:
        yellow.append(_coverage_gap(
            "事实账/正文有 %d 条意大利事项，但语料视图里没有 it/ 语料"
            "（<corpus>/it/index.json）——意大利闸 0 覆盖（fail-closed）"
            % scope["it"]))
        gates["it"] = _gate_note("skipped", 0, 0, "it/ 语料没拿到")
    else:
        gates["it"] = _gate_note(
            "skipped" if it_material_ok else "na", 0, 0,
            "date 未定，时效判据全跳过" if it_material_ok else "0 事项")

    # ---- CASE 闸（中国案例：案号/日期/金额与官方件一致；材料全在项目内）----
    r, y = _convert(verify_case(project_dir))
    red += r
    yellow += y
    gates["case"] = _gate_note("ran", len(r), len(y), "%d 条事项" % scope["case"])

    summary = {
        "domain": DOMAIN_ID,
        "red": len(red),
        "yellow": len(yellow),
        "hints": 0,
        "corpus": corpus_rel,
        "date": date,
        "view": view_rel,
        "gates": gates,
        "lines": [
            "corpus  : %s    参考日: %s    view: %s" % (
                corpus_rel or "（未声明）", date or "（未定）",
                view_rel or "—"),
            "gates   : " + " ｜ ".join(
                "%s 红%d/黄%d（%s）" % (g, gates[g]["red"], gates[g]["yellow"],
                                       gates[g]["status"])
                for g in GATE_ORDER),
        ],
    }
    return red, yellow, hints, summary, []


# --------------------------------------------------------------------------
# 注册：把 legal 卡挂进核验槽（幂等；本模块被 checks.load_integration
# import 时自动挂卡——check-package.toml 声明的 adapter 就是本模块）。
# --------------------------------------------------------------------------

_CARD = checks.CheckPackage(
    domain_id=DOMAIN_ID,
    verify=verify_legal,
    config_keys=CONFIG_KEYS,
    description="法律四闸 FR/CN/CASE/IT：法条存在、参考日生效、官方字节未改、"
                "值真出自法条（integrations/factscribe-legal；材料缺失 fail-closed）",
)


def register() -> None:
    if checks.get_package(DOMAIN_ID) is None:
        checks.register_package(_CARD)


register()
