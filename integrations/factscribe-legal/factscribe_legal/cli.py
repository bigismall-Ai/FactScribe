"""factscribe-legal 命令行入口。

  factscribe-legal fetch   --corpus <dir> --project <dir> --nums L3121-27 ...
        把语料里的法条**物化**进 FactScribe 项目（连同可钉的哈希），并给出一段
        可直接粘进事实账的 [[fact]] 片段。

  factscribe-legal verify  --project <dir> --corpus <dir> --date YYYY-MM-DD
        跑法律专项校验：法条存在？哈希未变？参考日生效？引用的数字真出自该法条？
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

    args = ap.parse_args(argv)
    # 废弃窗口（SPEC-CHECKS 裁定⑥，2026-11-16）：六条子命令保留作调试／
    # 单域入口（不删功能、废弃窗口不限期）——措辞照 README「核验槽时代」
    # 一节的既有文案；正式的跨域报告走 factscribe audit [checks]。
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
    return cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
