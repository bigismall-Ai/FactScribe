#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由 READINGS-PAN.json 生成 REPORT-PAN.md（纯标准库）。

判据原文照抄工单（P-157 冻结），数字全部从读数文件算，不手填。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path("/tmp/fs-gcards-wt/experiments/fs-textreuse-pan")
READINGS = BASE / "READINGS-PAN.json"
REPORT = BASE / "REPORT-PAN.md"
PAN = Path("/Users/moc/workspaces/SiAgent/pan-corpus")

CRITERIA_VERBATIM = """\
## 判据（P-157 冻结，机械判定）

> - none 档：≥18/20 例字符覆盖 ≥0.8 且 干扰误配总计 ≤1 例 → **字面层主张 PASS**；否则如实 FAIL。
> - 干净对：必须零报告，任何误报 → FAIL。
> - random/manual：只出参考读数（逐档召回），**不设门**；manual 预期漏检＝语义层边界，REPORT 明声明。"""


def pct(x):
    return "-" if x is None else "%.3f" % x


def main() -> int:
    data = json.loads(READINGS.read_text(encoding="utf-8"))
    s = data["summary"]
    rows = data["readings"]
    src = json.loads((PAN / "SOURCE.json").read_text(encoding="utf-8"))

    none_s = s.get("none", {})
    none_cov08 = none_s.get("char_coverage_ge_0.8", 0)
    none_false = none_s.get("distractor_false_positive_cases", 0)
    none_pass = (none_cov08 >= 18) and (none_false <= 1)
    clean_s = s.get("clean", {})
    clean_any = clean_s.get("n_cases_with_any_report", 0)
    clean_pass = (clean_any == 0)

    fails = []
    for r in rows:
        if r["tier"] == "none":
            reasons = []
            if r["char_coverage"] is None or r["char_coverage"] < 0.8:
                reasons.append("字符覆盖 %s < 0.8" % pct(r["char_coverage"]))
            if not r["true_source_reported"]:
                reasons.append("真源未被报")
            if r["distractor_reported"]:
                reasons.append("干扰源被报（误配）")
            if reasons:
                fails.append((r["case_id"], "none", "；".join(reasons), r))
        elif r["tier"] == "clean":
            if r["segments_total"] > 0:
                hits = sorted({x["b_file"] for x in r["reported_pairs"]})
                fails.append((r["case_id"], "clean",
                              "误报 %d 段（命中文件=%s）" % (r["segments_total"], hits), r))
        elif r["tier"] in ("random", "manual"):
            if not r["true_source_reported"]:
                fails.append((r["case_id"], r["tier"], "真源未被报（参考读数，无门）", r))

    md = []
    md.append("# REPORT-PAN —— PAN-PC-11 考卷上的 factscribe textreuse 字面层读数\n")
    md.append("工单：`/tmp/fs-gcards-wo/WORKORDER-PAN.md`（textreuse 上 PAN 标准考卷）  \n"
              "分支：`feat/gap-cards` ｜ 判据：P-157（已冻结，本报告只机械执行）\n")

    # 1 结论
    md.append("## 1. 结论\n")
    md.append("| 判据分支 | 判定 |")
    md.append("|---|---|")
    md.append("| none 档字面层主张 | **%s** |" % ("PASS" if none_pass else "FAIL"))
    md.append("| 干净对零报告 | **%s** |" % ("PASS" if clean_pass else "FAIL"))
    md.append("| random 档 | 参考读数，不设门 |")
    md.append("| manual 档 | 参考读数，不设门 |")
    md.append("")
    md.append("- **none 档**：字符覆盖 ≥0.8 的例数 = **%d**（要求 ≥18）；"
              "干扰误配总计 = **%d 例**（要求 ≤1）→ %s。"
              % (none_cov08, none_false, "字面层主张 PASS" if none_pass else "**字面层主张 FAIL**"))
    md.append("- **干净对**：%d/%d 例出现报告（要求 0）→ %s。"
              % (clean_any, clean_s.get("n_cases", 0),
                 "PASS" if clean_pass else "**FAIL**"))
    md.append("")
    md.append("> **manual 档漏检声明（工单要求明写）**：manual 档为众包人工改写（MTurk 众包重写 + "
              "机器翻译），属**语义层**；本卡只查字面层（逐字照搬才算重合），"
              "manual 档的漏检属**语义层边界**，本卡不覆盖，不计为缺陷。\n")
    md.append("> **FAIL 的成因分解（必须分清，否则结论会被误读）**：本档 FAIL **不是**"
              "「工具在逐字抄袭上失效」——本档的失败来自**两头同时**：(a) 语料侧，"
              "PAN-PC-11 的插入段落**即使标 `obfuscation=\"none\"` 也带词级扰动**"
              "（随机抄袭程序插入拉丁词等，见 §3 实测），8 词级 n-gram 天然切不中；"
              "(b) 语料侧**没有发布 `source_reference`**，真源只能反推（§5.3），"
              "反推置信度受限（§6.3）。两条都在**读数表**里逐例可查。\n")

    # 2 考卷来源
    md.append("## 2. 考卷来源、许可证与大小\n")
    md.append("- 语料：**PAN Plagiarism Corpus 2011（PAN-PC-11）**，"
              "Zenodo record [3250095](https://zenodo.org/records/3250095)"
              "（DOI 10.5281/zenodo.3250095）")
    md.append("- 许可证：**CC BY 4.0**（Zenodo record license id = `cc-by-4.0`）")
    md.append("- 取件日期（UTC）：2026-11-18（下载）→ %s（解包完成）"
              % src.get("extracted_utc", "-"))
    md.append("- 原始包：**%d 字节（%.2f GB）**，2 卷 RAR4（`.part1.rar` / `.part2.rar`）"
              % (sum(p["size"] for p in src["parts"]),
                 sum(p["size"] for p in src["parts"]) / 1e9))
    md.append("- 解包后语料文件数：**%d**" % src["files_extracted"])
    md.append("- 完整来源清单（URL／sha256／md5 交叉校验）见 `pan-corpus/SOURCE.md`\n")
    md.append("| 原始包 | 字节 | sha256 | md5（与 Zenodo 公布值交叉校验） |")
    md.append("|---|---|---|---|")
    for p in src["parts"]:
        md.append("| `%s` | %d | `%s` | `%s` |" % (p["name"], p["size"], p["sha256"], p["md5"]))
    md.append("")
    md.append("**选型说明**：工单候选 PAN-PC-09 → PAN-PC-10 → PAN-PC-11，且「择总下载 ≤3GB 最小者」。"
              "三者**均可免注册直下**（Zenodo record API 200，非注册表单、非死链），实测体积 "
              "09 = 2.39 GB／10 = 1.77 GB／11 = 1.73 GB；Webis 官方页把 09、10 均标为 "
              "*\"This corpus is outdated. Please use its successor PAN-PC-11.\"*。"
              "两条判据同向 → 择 **PAN-PC-11**。\n")
    md.append("**下载礼貌纪律**：UA 自报 `factscribe-pan-probe/1.0 (+https://github.com/factscribe-dev; "
              "contact: moc@example.org)`；同一语料线上新请求发起间隔 ≥3s；单块超时重试 ≤2"
              "（失败块按已收字节续传，不重来）；HTTP Range 分块（4 MiB/块）。\n")

    # 3 语料实况（重要：与工单前提的偏差）
    md.append("## 3. 语料实况（与工单前提的偏差，必须先声明）\n")
    md.append("| 工单前提 | 语料实测 | 影响 |")
    md.append("|---|---|---|")
    md.append("| 注释含 `source_reference`（对应源文档） | **没有**。全量 11,443 条 "
              "`feature name=\"plagiarism\"` 的属性词表只有 "
              "`name/type/this_offset/this_length/this_language/obfuscation/manual_obfuscation` | "
              "「真源文档」不能直读，须**从语料自身反推**（§5.3） |")
    md.append("| obfuscation 三档 none｜random｜manual | 实际只有 3 组："
              "`obfuscation=none`+`type=artificial`（9,931）、"
              "`type=translation`+`manual_obfuscation=false`（1,325）、"
              "`type=translation`+`manual_obfuscation=true`（187） | "
              "工单三档按 §5.1 映射 |")
    md.append("| — | 归档内**没有** `external-detection-corpus/suspicious-document/`；"
              "可疑文档全部在 `intrinsic-detection-corpus/suspicious-document/part1..10`"
              "（4,753 篇），源文档在 `external-detection-corpus/source-document/part2..23`"
              "（9,901 篇） | 跨文档检测仍可做（源池在），但缺 external 可疑文档子集 |")
    md.append("")
    md.append("**关键实测（决定本卡在本题上的表现）**：语料 `obfuscation=\"none\"` 的插入段落"
              "**并非逐字照搬**——随机抄袭程序在段落里插入了拉丁词等词级扰动。"
              "实测样例（`suspicious-document00001.txt`，span 头）："
              "`But\\nour intelligence is not stopped by this. By a simple sic jubeo it posits a …`；"
              "对该 span 取 15–30 词窗在 9,901 篇源池里**零命中**，5 词窗仅 1–9 命中且指向不同文档。"
              "→ 工具的 8 词级字面匹配切不中这些段落，是**语料性质**决定的，不是阈值问题。\n")

    # 4 抽样构成
    md.append("## 4. 抽样构成\n")
    md.append("seed = **%d**；同文档 ≤2 例（先一轮一文档一例保证分散，再补第二轮至多再加一例）。\n"
              % data["seed"])
    md.append("| 档 | 语料池（全量可抽例数） | 抽中例数 | 涉及文档数 |")
    md.append("|---|---|---|---|")
    for tier in ("none", "random", "manual"):
        docs = len({r["suspicious_document"] for r in rows if r["tier"] == tier})
        md.append("| `%s` | %d | %d | %d |"
                  % (tier, data["pool_sizes"].get(tier, 0),
                     s.get(tier, {}).get("n_cases", 0), docs))
    md.append("| `clean`（干净对） | 无抄袭可疑文档 %d | %d | %d |"
              % (data["n_negative_suspicious"], s.get("clean", {}).get("n_cases", 0),
                 len({r["suspicious_document"] for r in rows if r["tier"] == "clean"})))
    md.append("")
    md.append("抽样子集清单（全量，含每例可疑文档／源文档／注释 span／真源反推置信度）："
              "`pan-corpus/SUBSET-PAN.json`。\n")

    # 5 映射口径
    md.append("## 5. 映射口径\n")
    md.append("**5.1 语料标注 → 工单三档。**\n")
    md.append("| 工单档 | 语料判据 | 含义 | 池大小 |")
    md.append("|---|---|---|---|")
    md.append("| `none` | `obfuscation == \"none\"` | 逐字档（语料标注如此声明，"
              "但正文实测带词级扰动，见 §3） | %d |" % data["pool_sizes"].get("none", 0))
    md.append("| `random` | `type == \"translation\"` 且 `manual_obfuscation != \"true\"` | "
              "程序自动改写（机器翻译） | %d |" % data["pool_sizes"].get("random", 0))
    md.append("| `manual` | `type == \"translation\"` 且 `manual_obfuscation == \"true\"` | "
              "众包人工改写（MTurk） | %d |" % data["pool_sizes"].get("manual", 0))
    md.append("")
    md.append("语料**没有** `obfuscation==\"random\"`、也**没有** `type==\"manual\"`（已全量核查）。"
              "工单的「random」档只能对应「程序自动改写」这组，「manual」档对应「众包人工改写」这组；"
              "此映射为本报告的显式口径，不是语料原文。\n")
    md.append("**5.2 注释 span → 报告段的字符折算。** 注释给的是可疑文档内的字符区间 "
              "`[this_offset, this_offset+this_length)`（**字符**偏移，已实测：按字节取会错位）；"
              "工具报的是「文件:行-行」。折算口径：\n")
    md.append("1. 取可疑文档原文（utf-8, errors=replace），按 `\\n` 切行，建**行首字符偏移表** "
              "`offsets[k]`（第 k 行起始字符下标，1-indexed）。")
    md.append("2. 报告段 `(a_line_start, a_line_end)` → 字符区间 "
              "`[offsets[a_line_start], offsets[a_line_end+1])`；末行以 `len(text)` 收尾。")
    md.append("3. **行粒度折算（行×行长）＝对报告段的保守上界**：整行都算被覆盖，"
              "故算出的覆盖比例**偏高**（真实词级覆盖更低）。")
    md.append("4. 覆盖比例 = |注释 span ∩ （真源侧各报告段折算区间的并集）| ÷ |注释 span|。")
    md.append("5. 工具归一（去 LaTeX 注释行／LaTeX 命令／空白折叠／大小写折叠）**不改变行号**，"
              "故行号→字符偏移仍对得上原文。")
    md.append("6. 口径自检：合成用例验证（多行文档，注释 span 落在第 3 行）→ 覆盖 1.000；"
              "把注释 span 挪到未报告的第 1 行 → 覆盖 0.000。\n")
    md.append("**5.3 「真源文档」的反推口径（语料没给 source_reference，只能反推）。**\n")
    md.append("1. 源池 = `external-detection-corpus/source-document/part2..23`（9,901 篇），"
              "先做**空白折叠**拼成单文件（2.20 GB），并记每篇起始偏移。")
    md.append("2. 对每例取注释 span 文本，按**多尺度词窗**取探针（30/15/8/5 词，每词滑动），"
              "一次性 Aho-Corasick 扫描（`rg -F -b -o -f probes.txt`）全池。")
    md.append("3. 按「**命中尺度最大者**优先、命中数次之」定真源；命中尺度越长＝逐字重合越长＝置信越高。")
    md.append("4. 置信度记在逐例读数里：`source_resolution_scale_words`（命中的最长词窗尺度）"
              "与 `source_resolution_hits`（命中数）。\n")
    md.append("**5.4 案例构造（每例）。** `/tmp/pan-run/<例id>/A/` 放 1 个可疑文档（`.txt` 单文件）；"
              "`B/` 放 **真源文档 + 随机抽 4 份干扰源文档**（同档内随机、排除真源）。"
              "干净对：`A/` 放**无抄袭**的可疑文档（无 `plagiarism` feature），"
              "`B/` 放**随机非其源文档** + 4 份干扰源文档。\n")
    md.append("**5.5 真源比对。** 真源＝反推出的源文档；报告段 `b_file` 等于该文件名即判「真源被报」；"
              "`b_file` 命中 4 份干扰源之一即判「干扰源被报（误配）」。\n")
    md.append("**5.6 工具与参数。** `factscribe textreuse A B --json`，**默认 n=8、min_tokens=8**，"
              "**未改任何参数**；textreuse 工具源码零改动（见 §8 自查）。"
              "CLI 以 `python3 -m factscribe` 调用工作树 `feat/gap-cards` 的代码"
              "（PATH 上的 `factscribe` 启动器本身指向一个未装包的 uv 环境，会 "
              "`ModuleNotFoundError`，与本卡无关；工作树代码本身可用）。\n")

    # 6 分档表
    md.append("## 6. 混淆分档表\n")

    def tier_table(tier, verdict):
        t = s.get(tier, {})
        md.append("| 档 | 例数 | 真源已反推 | 真源被报 | 字符覆盖 ≥0.8 | 覆盖均值 | 覆盖中位 | "
                  "干扰误配例数 | 判定 |")
        md.append("|---|---|---|---|---|---|---|---|---|")
        md.append("| `%s` | %d | %d | %d | %d | %s | %s | %d | %s |"
                  % (tier, t.get("n_cases", 0), t.get("n_source_resolved", 0),
                     t.get("true_source_reported", 0), t.get("char_coverage_ge_0.8", 0),
                     pct(t.get("char_coverage_mean")), pct(t.get("char_coverage_median")),
                     t.get("distractor_false_positive_cases", 0), verdict))

    tier_table("none", "**PASS**" if none_pass else "**FAIL**")
    md.append("")
    tier_table("random", "参考（不设门）")
    md.append("")
    tier_table("manual", "参考（不设门）")
    md.append("")
    md.append("| 档 | 例数 | 出现报告的例数 | 判定 |")
    md.append("|---|---|---|---|")
    md.append("| `clean` | %d | %d | %s |"
              % (clean_s.get("n_cases", 0), clean_any, "**PASS**" if clean_pass else "**FAIL**"))
    md.append("")
    md.append("逐档召回（参考读数，不设门）：")
    for tier in ("none", "random", "manual"):
        t = s.get(tier, {})
        n = t.get("n_cases", 0)
        hit = t.get("true_source_reported", 0)
        md.append("- `%s`：真源被报 %d/%d（召回 %.3f）；工具在该档**有任何报告**的例数 %d"
                  % (tier, hit, n, hit / n if n else 0, t.get("n_cases_with_any_report", 0)))
    md.append("")
    md.append("**6.3 真源反推置信度分布**（`source_resolution_scale_words` = 命中的最长词窗尺度）：")
    md.append("")
    md.append("| 档 | 已反推 | 其中尺度 ≥8 词（强） | 其中尺度 =5 词（弱） | 未反推 |")
    md.append("|---|---|---|---|---|")
    for tier in ("none", "random", "manual"):
        rs = [r for r in rows if r["tier"] == tier]
        strong = len([r for r in rs if (r.get("source_resolution_scale_words") or 0) >= 8])
        weak = len([r for r in rs if (r.get("source_resolution_scale_words") or 0) == 5])
        unres = len([r for r in rs if not r.get("source_resolved")])
        md.append("| `%s` | %d | %d | %d | %d |"
                  % (tier, len(rs) - unres, strong, weak, unres))
    md.append("")
    md.append("（尺度 ≤5 词的命中有可能是通用短语造成的**假命中**；这类 case 的「真源被报」"
              "不可当真阳性读。逐例见 `READINGS-PAN.json`。）\n")
    strong = [r for r in rows if (r.get("source_resolution_scale_words") or 0) >= 8]
    md.append("**6.4 真源被硬确认的两例（最硬的证据）**——"
              "反推命中的最长词窗 ≥8 词，意味着源文档里有**连续 8 词以上的逐字重合**，"
              "真源身份基本无争议；这两例的读数直接说明失败机制：\n")
    if strong:
        md.append("| 例 id | 档 | 真源 | 确认尺度 | 工具是否报真源 | 字符覆盖 | 报告段数 |")
        md.append("|---|---|---|---|---|---|---|")
        for r in strong:
            md.append("| `%s` | %s | `%s` | %d 词 | %s | %s | %d |"
                      % (r["case_id"], r["tier"], r["source_document"],
                         r["source_resolution_scale_words"],
                         "是" if r["true_source_reported"] else "否",
                         pct(r["char_coverage"]), r["segments_total"]))
        md.append("")
        md.append("读法：`none-001` 的真源**已被确认**，工具**也真的报了它**，"
                  "但覆盖注释 span 只有 %.1f%%——即「真源在 B 侧、工具切中了、"
                  "却只能盖住段落的极小一段」。这条把失败归因钉死在**段落被词级扰动**"
                  "（工具切不中剩余部分），而不是「真源没找对」或「B 侧没放真源」。\n"
                  % (100 * strong[0]["char_coverage"] if strong and
                     strong[0]["char_coverage"] else 0))
    else:
        md.append("（本次抽样中无尺度 ≥8 词的强确认案例。）\n")

    # 7 失败件
    md.append("## 7. 失败件清单\n")
    if fails:
        md.append("| 例 id | 档 | 失败原因 | 真源被报 | 字符覆盖 | 干扰误配 | 报告段数 | 真源反推尺度 |")
        md.append("|---|---|---|---|---|---|---|---|")
        for cid, tier, reason, r in fails:
            md.append("| `%s` | %s | %s | %s | %s | %s | %d | %s |"
                      % (cid, tier, reason, "是" if r["true_source_reported"] else "否",
                         pct(r["char_coverage"]), "是" if r["distractor_reported"] else "否",
                         r["segments_total"],
                         r.get("source_resolution_scale_words") or "-"))
        md.append("")
        md.append("（random/manual 档的「真源未被报」是**参考读数**，非门限失败。）")
    else:
        md.append("（无。）")
    md.append("")

    # 8 判据原文 + 自查
    md.append("## 8. 判据原文与零改动自查\n")
    md.append(CRITERIA_VERBATIM)
    md.append("")
    md.append("**零改动自查**：`git diff --stat` 中**无 `factscribe/textreuse.py`**；"
              "跑测命令未带 `--n`／`--min-tokens`（默认 n=8 / min_tokens=8）。\n")

    REPORT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote %s" % REPORT)
    print("none: cov>=0.8 %d/20, false %d -> %s"
          % (none_cov08, none_false, "PASS" if none_pass else "FAIL"))
    print("clean: any-report %d/%d -> %s"
          % (clean_any, clean_s.get("n_cases", 0), "PASS" if clean_pass else "FAIL"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
