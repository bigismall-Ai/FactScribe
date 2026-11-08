# FactScribe

**English** · [中文](README.md)

FactScribe is a gate for the two kinds of fabrication that matter most in AI-written papers: numbers with no source, and citations that point at nothing.
It does not write or rewrite prose. It answers one question: **can every number in this sentence be traced back to a signed, hashed source?**

Standard library only. No model SDK. Python ≥ 3.10.

> Green means the ledger, the sources and the prose agree, and the sources are unmodified. It does not mean the paper is true. See `docs/design/SPEC-V1.md` §2.3.

## Install and run

```bash
python3 -m pip install -e .            # optional; PYTHONPATH works too
python3 -m factscribe audit  <project> # core check
python3 -m factscribe style  <project> # prose lint
```

## Six commands

| Command | What it does |
|---|---|
| `check` | Validates the fact ledger: unique ids, live sha256, signed manifest, expression arithmetic, duplicate values |
| `audit` | The core check: inline binding, number-to-ledger, citation stability, coverage |
| `protect` | Rewrite protection: compares six classes of content that must not change |
| `style` | Prose lint: formulaic-writing signals only, yellow, never blocking |
| `verify-pdf` | PDF check: text layer, rasterised pages, bidirectional multiset, stamp signature |
| `matrix` | Writes the traceability matrix to `audit/matrix.md` |

All commands accept `--json`. `check` and `audit` accept `--strict`, which treats yellow as red for CI.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Green |
| 1 | Red: violations |
| 2 | Configuration or usage error |
| 3 | Yellow: unverified or unbound; not fatal, not green |
| 4 | Internal error |

A missing `factscribe.toml`, an empty ledger, empty prose, or a missing `refs.bib` exits 2 with a reason. Nothing passes silently.

## Protection surface

The protection surface is the six classes of content that a rewrite must not touch.

| Surface | Content |
|---|---|
| Fact markers | Multiset of every `\fact{}` |
| Numbers | Normalised number multiset |
| Citations | Keys of every `\cite` family command |
| Math | Content hash of inline and display math |
| Tables | Cell count and content hash per `tabular` row |
| Labels | Key sets of `\label` and `\ref` |

```bash
python3 -m factscribe protect --before old/ --after new/
```

Punctuation-only edits should stay green. A changed number, formula or citation is red, with file, line and what changed.

## How numbers are checked

Writing `\fact{A1}` declares that the numbers on that line belong to fact `A1`.
The audit requires every number on that line to fall inside the fact's value domain.

| Case | Result |
|---|---|
| Bound and matched | Green |
| Unbound but matches a fact | Yellow `UNBOUND_NUMBER` |
| Matches nothing | Red `UNMATCHED_NUMBER` |
| Bound but mismatched | Red `BOUND_MISMATCH` |

Normalisation: `1,234` equals `1234`, `0.90` equals `0.9`, `10\%` equals `10%`, `53k` equals `53000`.

## How citations are checked

Every `\cite` family key must exist in `refs.bib`, otherwise red `MISSING_CITE`.
Each bib entry needs `arxiv` or `doi`; `@misc` entries may use `url`.
With `--resolve`, a network failure is yellow and a definite remote miss is red.

## Yellow rules

Yellow findings never block a build and turn the exit code into 3.

- `UNBOUND_NUMBER`: traceable but unbound;
- `NO_MANIFEST` and `UNSIGNED_RESULT`: no signed manifest, or unsigned artifacts;
- `VALUE_NOT_IN_SOURCE`: a ledger number absent from its source file;
- `LEDGER_CONFLICT` and `DUPLICATE_VALUE`: self-contradicting ledger, or one value under two claims;
- `CITE_UNVERIFIED`: resolution did not complete;
- `UNUSED_FACT` and `UNUSED_BIB`: unused ledger entries and uncited bib keys.

The prose lint has nine yellow rules in four groups: parenthetical dashes, heading length and form, a term's first appearance in a heading, and rhythm or filler.

## Known gaps

Nine blind sets were run. The three truly blind ones caught 30 of 36 cases with zero false alarms.
The remaining gaps are listed in `docs/release/KNOWN-GAPS.md`:

- derived facts whose expression disagrees with the stored value;
- dynamic `\input` targets;
- diagnostic-only error codes.

The same file states three structural limits: the trust root is a human signature; same-machine authoring is weak blinding; there is no OCR, so numbers carried by images are red.

## Reproduce and contribute

```bash
python3 -m unittest discover -s tests     # 326 tests, fully offline
./scripts/preflight-ci.sh                 # local CI: clean clone + 3.10/3.11/3.12
```

`examples/minimal/` is the acceptance sample: three facts, two sections, one fabricated number and one fake citation. `audit` must report exactly those two reds.

Specs live in `docs/design/`, implementation notes in `docs/implementation/`, history in `CHANGELOG.md`.
Read `CONTRIBUTING.md` before opening a pull request. Tests are required.
