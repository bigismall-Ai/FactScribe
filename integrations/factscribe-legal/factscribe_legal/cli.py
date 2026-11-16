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

    args = ap.parse_args(argv)
    # 废弃窗口（SPEC-CHECKS 裁定⑥，2026-11-16）：五条子命令保留作调试／
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
    return cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
