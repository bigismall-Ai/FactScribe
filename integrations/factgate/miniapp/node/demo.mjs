// 事实闸 · 演示数据
// 素材：FactScribe 仓库的 examples/minimal（MIT, github.com/bigismall-Ai/FactScribe）
// 这是上游那份 5 分钟验收样例的同一批数据：3 条事实（其中 A2 是 expr 派生）、
// 2 条 bib、1 份来源材料 results/swb16.md。
//
// 故意埋的问题与上游一致：
//   · 编造数字 47.3（账外）        → UNMATCHED_NUMBER（红）
//   · 假引用 key ghost2024          → MISSING_CITE（红）
// 另外补两项 Mini App 独有的演示：
//   · 无稳定标识的 bib 条目          → BIB_NO_STABLE_ID（红）
//   · 在线查无此文的 DOI             → CITE_FAKE（红，需联网核验才有）

export const DEMO_SOURCE_TEXT = `# SWB16 复跑记录（原始产物，只读；路径由 facts.source 指过来）

日期：2026-11-06
题目集：SWB16（16 题，固定）

## 一 口径

- open 臂：允许工具调用；
- closed 臂：不允许工具调用；
- 同一 prompt、同一评分脚本，单次复跑。

## 二 汇总表

| arm    | resolved | total |
|--------|----------|-------|
| open   | 10       | 16    |
| closed | 8        | 16    |

## 三 平均行

两臂合计：(10 + 8) / (16 + 16) = 56.25%

## 四 未纳入的读数

离线复跑测过一次端到端时延，产物不全、未复核，**不入事实账、正文不得引用**。
`;

export const DEMO_MANUSCRIPT = `\\section{Introduction}

把一句话需求变成一篇能复现的论文，难的从来不是文笔，而是两类没人能复核的
断言：一个查不到出处的数字，和一条指向不存在论文的引用。

开臂（允许工具调用的那一臂）在 16 道题里解决 10 道\\fact{A1}。
对比臂在同一组题上解决 8 道\\fact{A3}。
两臂合计的准确率为 56.25\\%\\fact{A2}，与 A1、A3 推算的记录一致。

\\section{Results}

\\begin{table}[t]
\\centering
\\begin{tabular}{lcc}
\\hline
arm & resolved & total \\\\
\\hline
open   & 10 & 16 \\\\
closed &  8 & 16 \\\\
\\hline
\\end{tabular}
\\caption{两臂在同一组 16 道题上的解决数。}
\\end{table}

上一轮离线复跑把端到端时延压到 47.3\\,ms，这个数字还没有进事实账，
审计应当把它拦下来；可复核的做法见 \\cite{chen2023factscore}。
相关工作另见 \\cite{ghost2024}，这是一条不存在的条目。

工程实现上还有一类工具 \\cite{toolkit2023}，值得单独说明。

另有一项未完成的对照 \\cite{pretend2025}，我们把它放在这里作为一个提醒：
本地条目齐全，不代表它真的存在。
`;

export const DEMO_BIB = `% 只放已核实条目：每条必须有 arxiv 或 doi，否则 audit 判红。

@inproceedings{chen2023factscore,
  title     = {FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation},
  author    = {Chen, Sewon and others},
  booktitle = {Proceedings of EMNLP},
  year      = {2023},
  doi       = {10.18653/v1/2023.emnlp-main.741}
}

@article{lewis2020rag,
  title   = {Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks},
  author  = {Lewis, Patrick and others},
  journal = {NeurIPS},
  year    = {2020},
  arxiv   = {2005.11401}
}

@article{pretend2025,
  title = {A Study That Does Not Exist: On Scaling Laws for Prompt-Only Agents},
  author = {Anonymous, A. and Anonymous, B.},
  journal = {Journal of Nonexistent Results},
  year = {2025},
  doi = {10.1234/fake.2024.99999}
}

@misc{toolkit2023,
  title = {An Engineering Toolkit for Long-Horizon Coding Agents},
  author = {Doe, J. and Roe, R.},
  year = {2023},
  note = {工业界白皮书，未公开发表}
}
`;

// 与上游 examples/minimal/facts/01-core.toml 同一批事实。
// A2 是派生事实：expr 由 A1、A3 推算出来，审计会重算并与 value 比对。
export const DEMO_FACTS = [
  {
    id: 'A1',
    claim: '开臂 resolved（16 题）',
    value: '10/16',
    locator: '§二 汇总表 open 行',
    confidence: 'high',
    notes: '开臂＝允许工具调用的那一臂',
  },
  {
    id: 'A3',
    claim: '对比臂 resolved（16 题）',
    value: '8/16',
    locator: '§二 汇总表 closed 行',
    confidence: 'high',
    notes: '对比臂＝不允许工具调用',
  },
  {
    id: 'A2',
    claim: '两臂合计准确率',
    value: '56.25%',
    locator: '§三 平均行',
    confidence: 'med',
    derivedFrom: ['A1', 'A3'],
    expr: '(A1.num + A3.num) / (A1.den + A3.den) * 100',
    notes: '推算值，非实验直接读数；(10+8)/(16+16)',
  },
];

export function buildDemoProject(sha256) {
  const sourceSha = sha256(DEMO_SOURCE_TEXT);
  return {
    name: 'minimal（演示）',
    note:
      '演示数据取自 FactScribe 仓库的 examples/minimal（MIT 许可）。' +
      '同一批事实、来源材料与 bib；正文沿用上游样例，故意埋入 1 个编造数字（47.3）、' +
      '1 条假引用 key（ghost2024），另加 1 条无稳定标识的 bib 与 1 个在线查无此文的 DOI。',
    manuscript: DEMO_MANUSCRIPT,
    bib: DEMO_BIB,
    sources: [
      {
        id: 'results/swb16.md',
        name: 'SWB16 复跑记录（原始产物，只读）',
        text: DEMO_SOURCE_TEXT,
        sha256: sourceSha,
      },
    ],
    facts: DEMO_FACTS.map((f) => ({
      id: f.id,
      claim: f.claim,
      value: f.value,
      source: 'results/swb16.md',
      sourceSha256: sourceSha,
      locator: f.locator,
      confidence: f.confidence,
      derivedFrom: f.derivedFrom || [],
      expr: f.expr || '',
      dupOk: false,
      notes: f.notes || '',
    })),
    protect: { before: '', after: '' },
  };
}
