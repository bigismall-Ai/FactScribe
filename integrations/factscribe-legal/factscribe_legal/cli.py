"""factscribe-legal 命令行入口。

  factscribe-legal fetch   --corpus <dir> --project <dir> --nums L3121-27 ...
        把语料里的法条**物化**进 FactScribe 项目（连同可钉的哈希），并给出一段
        可直接粘进事实账的 [[fact]] 片段。

  factscribe-legal verify  --project <dir> --corpus <dir> --date YYYY-MM-DD
        跑法律专项校验：法条存在？哈希未变？参考日生效？引用的数字真出自该法条？

  factscribe-legal cn-lead-search / cn-lead-verify / cn-lead-get
        中国判例线索层（第三方文书查，非官方核验）：找案子／案号存在性／取正文。
        不属核验槽——输出首行固定是线索层标注，溯源凭三元组上裁判文书网核对。

  factscribe-legal api <动作>
        只读接口层：吐版本化 JSON 契约（factscribe-legal-api/1.0），七路通道
        ——findings / receipts / corpus / codes / timeliness / summary / proposals。
        默认输出 JSON（--json 同义）；--human 出人读摘要。
        只读：不下任何判定（红黄码照抄各闸），不写盘，退出码 0＝接口可用、
        2＝配置错（项目目录不存在等）；材料缺失不报错，按「skipped」如实标出。
"""
import argparse
import os
import sys

from .provisions import load_corpus
from .verify import render, verify


def cmd_fetch(args):
    """列出语料里这些法条的状态与可钉的哈希，并给出事实账片段。

    事实的 source 指向**证据卡**（派生层），卡里声明官方 XML 的哈希；
    权威层（官方字节）的哈希由本集成现算复核。
    """
    import hashlib
    import os
    corpus = load_corpus(args.corpus)
    print(f"语料：{len(corpus)} 条（{args.corpus}）")
    for num in args.nums:
        prov = corpus.get(num)
        if prov is None:
            print(f"  ! {num} 不在语料里")
            continue
        card = os.path.join(args.corpus, f"{num}.card.txt")
        card_sha = ""
        if os.path.isfile(card):
            with open(card, "rb") as fh:
                card_sha = hashlib.sha256(fh.read()).hexdigest()
        print(f"  ✓ {num}  {prov.legiarti}  {prov.etat}  {prov.date_debut}→{prov.date_fin}")
        print(f"      官方 XML   {prov.xml_file}  sha256 {prov.xml_sha256}")
        if card_sha:
            run = os.path.basename(args.corpus)
            print(f'      事实账片段： source = "runs/{run}/{num}.card.txt"'
                  f'  source_sha256 = "sha256:{card_sha}"')


def cmd_verify(args):
    findings, corpus = verify(args.project, args.corpus, args.date, args.view)
    text, code = render(findings, corpus)
    print(text)
    return code


def cmd_verify_cn(args):
    from .cn_verify import render_cn, verify_cn
    findings = verify_cn(args.project, args.catalog, args.date)
    text, code = render_cn(findings)
    print(text)
    return code


def cmd_verify_case(args):
    from .case_verify import render_case, verify_case
    findings = verify_case(args.project)
    text, code = render_case(findings)
    print(text)
    return code


def cmd_verify_it(args):
    from .it_verify import render_it, verify_it
    findings, index = verify_it(args.project, args.corpus, args.date)
    text, code = render_it(findings, index)
    print(text)
    return code


def cmd_verify_es(args):
    from .es_verify import render_es, verify_es
    findings, index = verify_es(args.project, args.corpus, args.date)
    text, code = render_es(findings, index)
    print(text)
    return code


def cmd_verify_fr_case(args):
    from .fr_case_verify import render_fr_case, verify_fr_case
    findings, stats = verify_fr_case(args.project)
    text, code = render_fr_case(findings, stats)
    print(text)
    return code


def cmd_verify_it_case(args):
    """意大利宪法法院判例专项校验（语料＝it-case/run-* 判决档案 run 目录）。"""
    from .it_case_verify import render_it_case, verify_it_case
    try:
        findings, index = verify_it_case(args.project, args.corpus)
    except FileNotFoundError as e:
        print("配置错：%s" % e)
        print("提示：--corpus 指向 it-case/run-<YYYYMMDD>-itcase-<tier>/ 目录"
              "（里面要有 index.json）")
        return 2
    except Exception as e:  # noqa: BLE001 —— 兜底：同类异常不许穿透成堆栈
        print("配置错/材料异常：%s" % e)
        print("提示：语料目录或官方件可能损坏。材料坏了应当落成红码 finding"
              "（退出码 1），走到这里说明闸门内部有没兜住的异常，"
              "请把上面这行原文报上去。")
        return 2
    text, code = render_it_case(findings, index)
    print(text)
    return code


# ---- 中国判例线索层（第三方：文书查）——非闸，不进核验槽 ----

def _cn_lead_client(args):
    """按 --config / ./factscribe.toml / 环境变量 / 缺省装配客户端。"""
    from .cn_lead import WenshuChaClient, load_cn_lead_config
    endpoint, key = load_cn_lead_config(getattr(args, "config", None))
    return WenshuChaClient(endpoint=endpoint, api_key=key)


def _cn_lead_error_exit(exc):
    """线索层统一错误面：打印原因，exit 2（fail-closed：拿不到线索不许编）。"""
    print(exc)
    print("线索层失败＝退出码 2（fail-closed）；官方维度请走 verify-case / verify-cn。")
    return 2


def cmd_cn_lead_search(args):
    """cn-lead-search：找案子（一发一页，页顶 3）。有答＝0，含 0 命中。"""
    from .cn_lead import CnLeadError, render_search
    try:
        inner = _cn_lead_client(args).search(args.q, page_size=args.page_size,
                                             page=args.page)
    except CnLeadError as exc:
        return _cn_lead_error_exit(exc)
    print(render_search(inner, args.q))
    return 0


def cmd_cn_lead_verify(args):
    """cn-lead-verify：案号存在性核验。exists＝0，查无/判不出＝1（线索口径）。"""
    from .cn_lead import CnLeadError, render_verify
    try:
        inner = _cn_lead_client(args).verify_case_no(args.case_no)
    except CnLeadError as exc:
        return _cn_lead_error_exit(exc)
    print(render_verify(inner))
    return 0 if (inner.get("verdict") or "") == "exists" else 1


def cmd_cn_lead_get(args):
    """cn-lead-get：取单件元信息/正文。库内查无＝1，其余有答＝0。"""
    from .cn_lead import CnLeadError, render_get
    try:
        inner = _cn_lead_client(args).get_judgment(
            args.case_no, include_body=not args.meta, max_chars=args.max_chars)
    except CnLeadError as exc:
        return _cn_lead_error_exit(exc)
    print(render_get(inner))
    return 0 if inner.get("found") is not False else 1



# ---- 只读接口层（api 族）--------------------------------------------------

def cmd_api(args):
    """api：只读接口层，吐版本化 JSON 契约（七路通道）。

    退出码：0＝接口可用（本层不下判定，红黄码照抄各闸，不据此改退出码）；
    2＝配置错（项目目录不存在等）。材料缺失不报错——按 skipped 如实标出。
    """
    import json
    from .api import (CHANNELS, build_contract, context_from_project,
                      render_human)
    # 非 UTF-8 控制台（中文 Windows 的 cp936）：编不出来的字符降级成同义
    # ASCII，命令照常跑完、退出码照旧（口径照上游 factscribe/console.py；
    # 本包自带一份，以便独立拷走单跑）。UTF-8 环境下不改变任何一个字节。
    #
    # 只装在**本族**上：既有 11 条子命令的输出与退出码一个字都不许动
    # （它们在 cp936 上的既有崩溃是既有缺陷，本步不碰、不顺手修）。
    from .console import safe_stdio
    safe_stdio()
    action = args.action
    if action != "contract" and action not in CHANNELS:
        print("用法：factscribe-legal api <%s|contract> [...]" % "|".join(CHANNELS),
              file=sys.stderr)
        return 2
    project = args.project or "."
    if not os.path.isdir(project):
        print("配置错：项目目录不存在：%s" % project, file=sys.stderr)
        return 2
    ctx = context_from_project(project,
                               corpus=args.corpus,
                               date=args.date,
                               view=args.view,
                               catalog=args.catalog,
                               itcase=args.itcase)
    filters = {}
    for key in ("country", "domain", "state", "kind", "severity"):
        val = getattr(args, key, None)
        if val:
            filters[key] = val
    line_ids = [args.line] if args.line else None
    channels = None if action == "contract" else [action]
    contract = build_contract(ctx, channels=channels, filters=filters,
                              line_ids=line_ids)
    if args.human:
        print(render_human(contract))
    else:
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="factscribe-legal",
                                 description="给 FactScribe 接上法律维度")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="把法条物化进项目并给出事实账片段")
    f.add_argument("--corpus", required=True, help="语料目录（provisions/）")
    f.add_argument("--project", required=True)
    f.add_argument("--nums", nargs="+", required=True)
    f.set_defaults(func=cmd_fetch)

    v = sub.add_parser("verify", help="法律专项校验")
    v.add_argument("--project", required=True)
    v.add_argument("--corpus", required=True)
    v.add_argument("--date", required=True, help="参考日 YYYY-MM-DD")
    v.add_argument("--view", default="", help="可选：管线的现行版 JSONL，用于交叉验证")
    v.set_defaults(func=cmd_verify)

    c = sub.add_parser("verify-cn", help="中国侧法律专项校验（国家法律法规数据库全库）")
    c.add_argument("--project", required=True)
    c.add_argument("--catalog", required=True, help="catalog.jsonl.gz（FLK 全库）")
    c.add_argument("--date", required=True, help="参考日 YYYY-MM-DD")
    c.set_defaults(func=cmd_verify_cn)

    k = sub.add_parser("verify-case", help="中国案例维度专项校验（官方入库案例正文）")
    k.add_argument("--project", required=True)
    k.set_defaults(func=cmd_verify_case)

    i = sub.add_parser("verify-it", help="意大利法条专项校验（Normattiva 官方 AKN）")
    i.add_argument("--project", required=True)
    i.add_argument("--corpus", required=True, help="语料目录（runs/<run>-it/）")
    i.add_argument("--date", required=True, help="参考日 YYYY-MM-DD")
    i.set_defaults(func=cmd_verify_it)

    e = sub.add_parser("verify-es", help="西班牙法条专项校验（BOE 官方合并文本 XML）")
    e.add_argument("--project", required=True)
    e.add_argument("--corpus", required=True, help="语料目录（es/run-<run>-es-<slug>/）")
    e.add_argument("--date", required=True, help="参考日 YYYY-MM-DD")
    e.set_defaults(func=cmd_verify_es)

    fc = sub.add_parser("verify-fr-case",
                        help="法国判例专项校验（DILA INCA 官方判决 XML）")
    fc.add_argument("--project", required=True)
    fc.set_defaults(func=cmd_verify_fr_case)

    tc = sub.add_parser("verify-it-case", help="意大利宪法法院判例专项校验")
    tc.add_argument("--project", required=True)
    tc.add_argument("--corpus", required=True,
                    help="语料目录（it-case/run-<run>-itcase-<tier>/）")
    tc.set_defaults(func=cmd_verify_it_case)

    # 中国判例线索层（第三方：文书查）——不是闸，不进核验槽；废弃窗口提示
    # 不适用（这三条不是核验入口，[checks] 永不点名线索层）。
    s = sub.add_parser("cn-lead-search",
                       help="中国判例线索检索（第三方文书查；一发一页 ≤5 条，页顶 3）")
    s.add_argument("--q", required=True, help="检索词（简体中文，法律术语优先）")
    s.add_argument("--page-size", type=int, default=5,
                   help="每页条数，硬顶 5（默认 5；评估 Key 禁批量）")
    s.add_argument("--page", type=int, default=1,
                   help="页码，硬顶 3（默认 1；翻页＝换页码重跑本命令）")
    s.add_argument("--config", default=None,
                   help="factscribe.toml 路径（可选 [cn_lead] 节：endpoint/key）")
    s.set_defaults(func=cmd_cn_lead_search)

    lv = sub.add_parser("cn-lead-verify",
                        help="中国案号存在性核验（第三方文书查；非官方证明）")
    lv.add_argument("--case-no", required=True, help="案号，如「（2022）苏0322执保100号」")
    lv.add_argument("--config", default=None,
                   help="factscribe.toml 路径（可选 [cn_lead] 节：endpoint/key）")
    lv.set_defaults(func=cmd_cn_lead_verify)

    g = sub.add_parser("cn-lead-get",
                       help="取单件判论文的库内元信息/正文（第三方文书查）")
    g.add_argument("--case-no", required=True, help="案号，如「（2022）苏0322执保100号」")
    g.add_argument("--meta", action="store_true",
                   help="只取元信息不取正文（省正文配额）")
    g.add_argument("--max-chars", type=int, default=None,
                   help="分段读正文：本次最多取多少字符")
    g.add_argument("--config", default=None,
                   help="factscribe.toml 路径（可选 [cn_lead] 节：endpoint/key）")
    g.set_defaults(func=cmd_cn_lead_get)

    a = sub.add_parser("api", help="只读接口层（JSON 出口；七路通道）")
    a.add_argument("action",
                   choices=["findings", "receipts", "corpus", "codes",
                            "timeliness", "summary", "proposals", "contract"],
                   help="要取哪一路通道（contract＝七路全给）")
    a.add_argument("--project", default=".", help="项目目录（默认当前目录）")
    a.add_argument("--corpus", default=None,
                   help="语料视图目录（缺省取项目 factscribe.toml 的 [checks.legal] corpus）")
    a.add_argument("--date", default=None,
                   help="参考日 YYYY-MM-DD（缺省取 [checks.legal] date）")
    a.add_argument("--view", default=None,
                   help="现行视图 JSONL（缺省取 [checks.legal] view）")
    a.add_argument("--catalog", default=None, help="中国全库目录（可选）")
    a.add_argument("--itcase", default=None, help="意大利判例语料 run 目录（可选）")
    a.add_argument("--line", default=None, help="只看某一条线（fr/cn/case/it/es/fr-case/it-case）")
    a.add_argument("--country", default=None, help="按国家过滤（语料/时效通道）")
    a.add_argument("--domain", default=None, help="按域过滤（语料/时效/码表通道）")
    a.add_argument("--state", default=None, help="按时效状态过滤（in_force/…）")
    a.add_argument("--kind", default=None, help="按件型过滤（法条/法规/判例/案例）")
    a.add_argument("--severity", default=None, help="码表按红黄过滤（red/yellow）")
    a.add_argument("--json", action="store_true",
                   help="输出 JSON（默认就是 JSON；此旗显式同义）")
    a.add_argument("--human", action="store_true", help="输出人读摘要（同源）")
    a.set_defaults(func=cmd_api)

    args = ap.parse_args(argv)
    # 废弃窗口（SPEC-CHECKS 裁定⑥，2026-11-16）：六条子命令保留作调试／
    # 单域入口（不删功能、废弃窗口不限期）——措辞照 README「核验槽时代」
    # 一节的既有文案；正式的跨域报告走 factscribe audit [checks]。
    # 线索层三条（cn-lead-*）不属核验入口，提示不适用且不得占输出首行
    # （红线一：线索层首行必须是线索层标注）。
    # api 族不是单域调试入口（它是只读接口层，stdout 必须是纯 JSON）⇒
    # 不打这条提示，也不在 stdout 混任何别的行。
    if not args.cmd.startswith("cn-lead-") and args.cmd != "api":
        print("提示：本命令是单域调试入口（废弃窗口不限期，功能保留）；"
              "正式报告走 factscribe audit [checks]（单命令双域）。")
    if args.cmd == "fetch":
        return cmd_fetch(args)
    if args.cmd == "verify-cn":
        return cmd_verify_cn(args)
    if args.cmd == "verify-case":
        return cmd_verify_case(args)
    if args.cmd == "verify-it":
        return cmd_verify_it(args)
    if args.cmd == "verify-es":
        return cmd_verify_es(args)
    if args.cmd == "verify-fr-case":
        return cmd_verify_fr_case(args)
    if args.cmd == "verify-it-case":
        return cmd_verify_it_case(args)
    if args.cmd == "cn-lead-search":
        return cmd_cn_lead_search(args)
    if args.cmd == "cn-lead-verify":
        return cmd_cn_lead_verify(args)
    if args.cmd == "cn-lead-get":
        return cmd_cn_lead_get(args)
    if args.cmd == "api":
        return cmd_api(args)
    return cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
