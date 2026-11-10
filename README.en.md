# FactScribe

**English** · [中文](README.md)

FactScribe is a mechanical gate for the two worst kinds of fabrication in AI-written papers: numbers without a source, and citations that point at nothing. It never writes prose, and it never rewrites prose. It answers one question only: can every number in a sentence be traced back to a signed, hashed source?

Standard library only. No model SDK. Python ≥ 3.10.

## Boundary statement

Green means three things hold: the ledger has evidence, the evidence is unchanged, and the prose is bound to it. It does not mean the paper is true, nor that a reviewer should accept its conclusions. See `docs/design/SPEC-V1.md` §2.3.

What a reading does and does not support is spelled out in [`docs/WHAT-IT-PROVES.md`](docs/WHAT-IT-PROVES.md).

## Install and run

```bash
python3 -m pip install -e .                    # optional; PYTHONPATH works too
python3 -m factscribe audit <project>          # core check
python3 -m factscribe style --doc README.md    # prose check for one file
```

## Eleven commands

`factscribe` ships eleven subcommands, and each one solves a single narrow problem. A fact ledger is an append-only list that records every number, its source file, and the hash of that file.

| Command | What it does |
|---|---|
| `check` | Validates the fact ledger: unique ids, live sha256, signed manifest, expression arithmetic, duplicate values |
| `audit` | Core check: inline binding, number-to-ledger, citation stability, coverage report |
| `matrix` | Writes the traceability matrix to `audit/matrix.md` |
| `build` | Runs `project.build` from `factscribe.toml` |
| `preamble` | Generates the `\fact` and `\pkignore` macros in `audit/preamble.tex` |
| `verify-pdf` | PDF check: text layer, raster pages, bidirectional multiset, stamp signature |
| `style` | Prose gate: reports formulaic writing only, yellow, never blocking |
| `protect` | Rewrite protection: compares six classes of content that must not change |
| `tide` | Change ledger: rise, fall, blast radius, closure, all or nothing |
| `prescribe` | Prescription layer: executable fixes only, no criteria, no score |
| `terms` | Term candidates for human pick, then `add`; no automatic merge |

All commands accept `--json`. `check` and `audit` accept `--strict`, which treats yellow as red for CI.

## Three gates

The three gates cover numbers and citations, rewrite protection, and prose with terms. You can run them separately. Chaining all three gives a release check.

The first gate binds numbers and citations. Writing `\fact{A1}` declares that the numbers on that line belong to fact `A1`, and the audit requires every one of them to fall inside the fact's value domain. Every `\cite` family key must exist in `refs.bib`, and each entry needs `arxiv` or `doi`, while `@misc` entries may use `url`. Normalisation makes `1,234` equal `1234`, `0.90` equal `0.9`, and `53k` equal `53000`.

The second gate is the protection surface, meaning the six classes of content that a rewrite must not touch: fact markers, numbers, citations, math, tables, and labels. Punctuation-only edits should stay green. One changed number, formula, or citation is red, and the report gives file, line, and what changed.

```bash
python3 -m factscribe protect --before old/ --after new/
```

The third gate is the prose gate. It reports only mechanically checkable formulaic writing, across 25 rules. Four of them are rewrite rechecks: `HEADING_ECHO` catches a first sentence that restates its heading, `HEADING_RELATION_CHANGED` catches a swapped contrast word, `HEADING_SUBJECT_LOST` catches a dropped subject from an old heading, and `TERM_VARIANT` catches one term written several ways. The term layer has two lists: 33 paper terms from `paper-zh/GLOSSARY.md`, and 153 workspace process terms from the term registry.

## Change record

`tide` treats one rewrite as a transaction, and all four conditions must hold before it commits. The ledger trusts hashes, not a written summary.

Rise is what changed, derived from the file hashes of two directories. Fall is the real state after the edit, read from disk and hashed again. Blast radius is computed from the reverse `\input` and `\include` closure. Closure requires rise, fall, and blast radius to agree. If any piece is missing, everything rolls back: no ledger, no derived view, exit code 1.

There is no self-reported change list here. A person can read the result but cannot fill in the list, and the tool does not accept a hand-written note either.

## Prescription layer

`prescribe` answers a different question: once a rule fires, how should the text actually change? It carries 9 prescriptions. Each one gives a verified fix and records known bad fixes as forbidden moves with counterexamples. When two prescriptions conflict, a fixed priority order decides, and the losing one says so.

This layer adds no criteria and produces no score. It leaves every decision and exit code in `audit`, `style`, and `protect` untouched.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Green: no red, no yellow |
| 1 | Red: violations found |
| 2 | Configuration or usage error, the tool did not start |
| 3 | Yellow: finished, but unverified or unbound items remain; not fatal, not green |
| 4 | Internal tool error |

A missing `factscribe.toml`, an empty ledger, empty prose, or a missing `refs.bib` exits 2 with a reason. Nothing passes silently.

## Known gaps

The remaining issues are recorded in [`docs/release/KNOWN-GAPS.md`](docs/release/KNOWN-GAPS.md). Three structural limits will stay. The trust root is a human signature, so an agent that forges both the ledger and the evidence cannot be caught. Author and implementer share one machine, so blind tests are weak blinding. There is no OCR, so any number carried by an image is red.

All three limits point at the same promise. The tool keeps ledger, evidence, and prose consistent, and it proves the evidence was not changed. It does not prove the paper's conclusions.

## Reproduce and contribute

```bash
python3 -m unittest discover -s tests     # 660 tests, fully offline
./scripts/preflight-ci.sh                 # local CI: clean clone + 3.10/3.11/3.12
```

`examples/minimal/` is the acceptance sample: three facts, two sections, one fabricated number, and one fake citation. `audit` must report exactly those two reds.

Specs live in `docs/design/`, implementation notes in `docs/implementation/`, and history in `CHANGELOG.md`. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request, and bring tests with it.
