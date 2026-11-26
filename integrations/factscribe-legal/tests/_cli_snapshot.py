# -*- coding: utf-8 -*-
"""既有 11 条子命令的**输出与退出码快照**（第 ② 步：证明它们一字未动）。

第 ① 步只加了第 12 条（api 族）。本件把 11 条既有命令的

* --help 文本（命令面：参数、说明一字不改）、
* stdout（人读输出逐字节）、
* 退出码（语义不动）

固化成快照（cli_baseline.json），测试时现跑现比：任何一条变了就红。

快照**只从基线树生成过一次**（第 ① 步的 feat/legal-readonly-api-20260126
@ 23acded）——它的作用就是「与第 ① 步交付时逐字节相同」。

用法（生成，从基线树跑）：

    python3 integrations/factscribe-legal/tests/_cli_snapshot.py \
        --pkg-root <基线树>/integrations/factscribe-legal \
        --repo-root <基线树> --write

用法（自检，只打印差异）：

    python3 integrations/factscribe-legal/tests/_cli_snapshot.py
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PKG_ROOT = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT_REPO_ROOT = os.path.abspath(os.path.join(DEFAULT_PKG_ROOT, "..", ".."))
BASELINE = os.path.join(HERE, "cli_baseline.json")

# 11 条既有子命令（第 12 条 api 族是第 ① 步新加的，不进这份快照）。
# 参数一律用相对路径或仓内相对位置：输出里的绝对路径会被归一成占位符。
CASES = (
    ("fetch", ["fetch", "--corpus", "results/corpus-legal",
               "--project", ".", "--nums", "L3121-27"]),
    ("verify", ["verify", "--project", ".", "--corpus", "results/corpus-legal",
                "--date", "2026-11-14"]),
    ("verify-cn", ["verify-cn", "--project", ".",
                   "--catalog", "results/corpus-legal/catalog.jsonl.gz",
                   "--date", "2026-11-14"]),
    ("verify-case", ["verify-case", "--project", "."]),
    ("verify-it", ["verify-it", "--project", ".",
                   "--corpus", "<CORPUS_IT>",
                   "--date", "2026-11-14"]),
    ("verify-es", ["verify-es", "--project", ".",
                   "--corpus", "results/corpus-legal/es",
                   "--date", "2026-11-14"]),
    ("verify-fr-case", ["verify-fr-case", "--project", "."]),
    ("verify-it-case", ["verify-it-case", "--project", ".",
                        "--corpus", "<CORPUS_ITCASE>"]),
    ("cn-lead-search", ["cn-lead-search", "--q", "测试案",
                         "--config", "no-such-cn-lead.toml"]),
    ("cn-lead-verify", ["cn-lead-verify", "--case-no", "（2022）苏0322执保100号",
                         "--config", "no-such-cn-lead.toml"]),
    ("cn-lead-get", ["cn-lead-get", "--case-no", "（2022）苏0322执保100号",
                     "--config", "no-such-cn-lead.toml"]),
)


def _norm(text, tmp, repo):
    """把机器相关的绝对路径换成占位符（两边树跑出来的可比）。"""
    return (text.replace(tmp, "<TMP>").replace(repo, "<REPO>")
            .replace(os.sep, "/"))


def _expand(argv, pkg_root):
    """把语料占位符换成仓内打包语料的真实路径（输出里会被归一成 <REPO>）。"""
    mapping = {
        "<CORPUS_IT>": os.path.join(pkg_root, "corpus", "it",
                                    "run-20261116-it-1990n241"),
        "<CORPUS_ITCASE>": os.path.join(pkg_root, "corpus", "it-case",
                                        "run-20261116-itcase-1956_1980"),
    }
    return [mapping.get(a, a) for a in argv]


def _run(argv, cwd, pkg_root, tmp, repo):
    env = dict(os.environ, PYTHONPATH=pkg_root)
    proc = subprocess.run([sys.executable, "-m", "factscribe_legal", *argv],
                          cwd=cwd, env=env, capture_output=True, text=True)
    stderr = _norm(proc.stderr, tmp, repo)
    if "Traceback (most recent call last)" in stderr:
        # 堆栈里的行号会随无关改动漂移 ⇒ 只记「有堆栈」这一事实。
        stderr = "<TRACEBACK>"
    return {"exit": proc.returncode,
            "stdout": _norm(proc.stdout, tmp, repo),
            "stderr": stderr}


def collect(pkg_root=DEFAULT_PKG_ROOT, repo_root=DEFAULT_REPO_ROOT):
    """现跑 11 条命令 → 快照数据。"""
    demo = os.path.join(repo_root, "fixtures", "legal-demo")
    tmp = tempfile.mkdtemp(prefix="legal-cli-snap-")
    try:
        proj = os.path.join(tmp, "proj")
        shutil.copytree(demo, proj)
        rows = []
        for name, argv in CASES:
            help_out = _run([name, "--help"], proj, pkg_root, tmp, repo_root)
            run_out = _run(_expand(argv, pkg_root), proj, pkg_root, tmp,
                            repo_root)
            rows.append({
                "name": name,
                "help": help_out["stdout"],
                "help_exit": help_out["exit"],
                "exit": run_out["exit"],
                "stdout": run_out["stdout"],
                "stderr": run_out["stderr"],
            })
        return rows
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg-root", default=DEFAULT_PKG_ROOT)
    ap.add_argument("--repo-root", default=DEFAULT_REPO_ROOT)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    rows = collect(args.pkg_root, args.repo_root)
    if args.write:
        with open(BASELINE, "w", encoding="utf-8") as fh:
            json.dump({"schema": "factscribe-legal-cli-baseline/1.0",
                       "note": ("既有 11 条子命令的 --help／stdout／退出码快照；"
                                "只从第 ① 步基线树（23acded）生成过一次。"
                                "第 12 条 api 族不在其中。"),
                       "cases": rows}, fh, ensure_ascii=False, indent=2,
                      sort_keys=True)
            fh.write("\n")
        print("cli_baseline: 写入 %d 条命令的快照 → %s"
              % (len(rows), BASELINE))
        return 0
    with open(BASELINE, encoding="utf-8") as fh:
        base = json.load(fh)
    bad = 0
    for old, new in zip(base["cases"], rows):
        if old != new:
            bad += 1
            print("DIFF %s" % old["name"])
            for key in ("help", "exit", "stdout", "stderr"):
                if old.get(key) != new.get(key):
                    print("  变了：%s" % key)
    print("cli_snapshot: %d/%d 条一致" % (len(rows) - bad, len(rows)))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
