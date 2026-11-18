# FactScribe

**English** · [中文](README.md)

FactScribe is a mechanical gate for the two worst kinds of fabrication in AI-written papers: numbers without a source, and citations that point at nothing. It never writes prose, and it never rewrites prose. It answers one question only: can every number in a sentence be traced back to a signed, hashed source?

Standard library only. No model SDK. Python ≥ 3.10.

## Identity and safety boundary

Three things have to line up: the ledger has evidence, the evidence is unchanged, and the prose is bound to it.

- **The ledger has evidence.** Every number in the body has a record in the fact ledger, that record points at a source file, the file has a sha256, and a human signed for it.
- **The evidence is unchanged.** Since the moment of signing, the hash of that source file has not moved.
- **The prose is bound to it.** Writing `\fact{A1}` in the body claims that the numbers on that line belong to `A1`, and the audit walks every number back to the ledger to check.

Four other things are none of its business:

- Whether the conclusions hold: not its job.
- Whether the text reads well: not its job.
- Whether a reviewer likes it: not its job.
- Whether it was plagiarised: the literal layer only — `textreuse` lists passages copied word for word **and near-literal mechanical overlaps** (multi-scale word windows plus sentence containment); rewrites, laundering and AI assembly are semantic-layer and out of scope (a miss belongs to the semantic layer).

One sentence to keep: **the tool keeps ledger, evidence and prose consistent, and it proves the evidence was not changed; it does not prove the paper's conclusions.** The full wording is in [`docs/WHAT-IT-PROVES.md`](docs/WHAT-IT-PROVES.md), the design side in [`docs/design/SPEC-V1.md`](docs/design/SPEC-V1.md).

### Network boundary

`refs search` is the only command that reaches the network by default, and it sends the query terms only. Never prose, never a local path.

Every other command is offline by default. Two switches send a request only when you pass them explicitly: `audit --resolve` sends arXiv and DOI identifiers to the resolver, and `fonts --fetch` downloads the Fandol font package.

### Safety boundary

Run `build` and `audit --build` only on projects you trust yourself. `project.build` is a shell command in the project declaration, and the tool runs it as written. `audit` on its own never compiles.

## Zero dependency identity

The runtime needs the Python standard library and nothing else (≥ 3.10). No model SDK, no third-party dependency, no LLM call anywhere. `pip install -e .` is a convenience; `PYTHONPATH` works just as well.

Only two external pieces are optional, and both degrade in a stated way:

| External piece | Who needs it | What happens without it |
|---|---|---|
| poppler (`pdftotext`/`pdfinfo`/`pdfimages`) | the PDF check layer of `verify-pdf` | reports `PDF_TOOL_MISSING` and exits 8, never a silent pass; every other command keeps working |
| tectonic | `build` and `audit --build` | reports the missing engine and exits 8; `audit` without `--build` never compiles, so it does not need it |

CJK fonts follow the same rule: `fonts --fetch` caches the Fandol fonts locally, and `build` falls back when a font is missing. `doctor` checks all of this, item by item, with a fix command for each.

## Five minutes to first green

```bash
python3 -m factscribe init mypaper && cd mypaper   # 7 files: declaration, main file, one section, empty ledger, manifest, refs.bib, README
printf '50 道题里答对 42 道。\n' > results/exp.md   # make one raw artefact
python3 -m factscribe fact add . \
  --id A1 \
  --claim "实验在 50 道题里答对 42 道" \
  --value "42/50" \
  --source results/exp.md \
  --locator "第 1 行"
```

`fact add` computes the sha256 of `results/exp.md` and prints one line. **It never signs for you**: copy that line into `[files]` of `results/MANIFEST.toml` yourself.

Then hook the body to the ledger:

```tex
\section{引言}

这项实验在 50 道题里答对 42 道\fact{A1}。
```

```bash
python3 -m factscribe audit .    # 0 red / 0 yellow -> green
python3 -m factscribe build .    # compile the PDF (needs tectonic)
```

Step by step lives in [`docs/QUICKSTART.md`](docs/QUICKSTART.md). Read [`docs/TRIAGE.md`](docs/TRIAGE.md) when you hit a wall of red, and [`docs/ADOPT.md`](docs/ADOPT.md) before you bring an existing paper in.

## Twenty-eight commands

`factscribe` ships twenty-eight subcommands. They are grouped below by the flow of writing a paper, not by internal module.

### Getting started

| Command | What it does |
|---|---|
| `init` | Scaffolds a minimal paper: declaration, section stub, empty ledger, manifest template, refs.bib; the same arguments produce byte-identical output twice |
| `doctor` | Pre-flight check: environment (Python/tectonic/poppler/fonts/git) and project (declaration/ledger/manifest/freeze), each with a fix command; not a gate, it never changes a verdict |
| `fonts` | Fandol font cache: `--status` to check, `--fetch` to download locally |

### Writing

| Command | What it does |
|---|---|
| `preamble` | Generates the `\fact` and `\fsignore` macros in `audit/preamble.tex` |
| `brief` | Drafting brief: section list, usable claims and numbers, terms, hard constraints and length budget, read off the ledger for a writing model |
| `prescribe` | Prescription layer: what to change once a rule fired; verified fixes only, no criteria, no score |
| `terms` | Term candidates: `suggest` extracts candidates into a TSV, `add` writes only the forms you named with `--pick` |
| `evidence` | Evidence list: `--suggest` prints a paste-ready `[evidence]` block, `--freeze` freezes it, `--unfreeze --reason` thaws it with a record |

### The reconciliation gates

| Command | What it does |
|---|---|
| `check` | Validates the ledger: unique ids, live sha256, signed manifest, expression arithmetic, duplicate values |
| `audit` | Core check: inline binding, number-to-ledger, citation stability, coverage report |
| `matrix` | Writes the traceability matrix to `audit/matrix.md` |
| `fact` | Bookkeeping: `add` computes the hash and writes one fact, it never signs the manifest for you; `import` brings a signed report into the ledger |
| `report` | Normalised experiment reports: `check` runs the probes, `lock` writes the lock, `sign` renders a review card and records the sign-off (see [`docs/design/SPEC-REPORT-SYNC.md`](docs/design/SPEC-REPORT-SYNC.md)) |
| `verify-pdf` | PDF check: text layer, raster pages, bidirectional multiset, stamp signature |
| `mirror-check` | Bilingual dual-disk ledger comparison: load-bearing fact fields plus bib entries, every drift listed |
| `textreuse` | Dual-directory literal overlap: passages copied word for word **and near-literal mechanical overlaps** (multi-scale word windows plus sentence containment), listed per segment with both sides' line ranges, token counts and match source; literal layer only, rewrites are out of scope |

### Revising

| Command | What it does |
|---|---|
| `protect` | Rewrite protection: six classes of content that must not change |
| `style` | Prose gate: formulaic writing in yellow, missing stamped evidence in red |
| `tide` | Change record: rise, fall, blast radius, closure, all or nothing; snapshots for rollback |
| `review` | Rewrite acceptance: protection, re-check and closure in one verdict |
| `polish` | LLM entry point: `--print` for the playbook, `--plan` for the worklist |

### Delivering

| Command | What it does |
|---|---|
| `build` | Compiles the PDF; falls back to tectonic, with a CJK font fallback |
| `figures` | Chart pipeline: human-written specs `figures/*.fig.toml`, mechanical output of the chart, its CSV and its binding table; `check` compares four faces |
| `bundle` | Submission package: closure collection, checklist gate, export plus MANIFEST; journal differences live in the project-side `bundle-checklist.toml` |

### Interfaces

| Command | What it does |
|---|---|
| `serve` | Local workbench HTTP API: loopback only, random token by default; read-only unless `--allow-write`, PDF builds only with `--allow-build` |
| `mcp` | MCP stdio server exposing `status`, `project`, `brief` and `audit` to agents; writes need `--allow-write` |
| `web` | Local workbench page: the `serve` backend plus the workbench UI; read-only unless `--allow-write`, PDF builds only with `--allow-build` |

The contracts live in [`docs/design/SPEC-SERVE.md`](docs/design/SPEC-SERVE.md) and [`docs/design/SPEC-MCP.md`](docs/design/SPEC-MCP.md).

### Literature

| Command | What it does |
|---|---|
| `refs` | Literature registry: `dedupe` finds two keys pointing at one paper (same DOI or arXiv id), `register` checks the to-fill table `refs/todo.toml` and names each missing field, `search` fetches candidate metadata (promotion into the formal bib stays a human act) |

Every command except `mcp` accepts `--json`. `check` and `audit` accept `--strict`, which treats yellow as red for CI.

## Four new commands in practice

One small example per new subcommand.

### mirror-check

The two paper disks, Chinese and English, are aligned by hand. Change one side, forget the other, and no tool says a word until the two ledgers no longer match.

```bash
python3 -m factscribe mirror-check paper-b paper-b-zh
```

The fact ledgers are matched by id and compared field by field over the load-bearing fields (claim, value, display, source, source_sha256, locator, expr, derived_from, kind); `refs.bib` is compared entry by entry (title, author, year, doi, arXiv id). Every drift is listed: disk, file, id, field, and the value on both sides. Exit code 0 means no drift, 1 means drift.

The exempt face is not judged: body text, the `main.tex` preamble, `GLOSSARY.md`, generated artefacts, and a fact's confidence and note. The command is read-only; it writes nothing and syncs nothing.

### refs

```bash
python3 -m factscribe refs dedupe .                  # cross-entry duplicate: same DOI or arXiv id reports REF_DUP_ID
python3 -m factscribe refs register .                # checks the to-fill table refs/todo.toml and names each missing field
python3 -m factscribe refs search "fact scoring" --source crossref   # the only default network action: the query terms only
```

`search` drops the raw response into `refs/candidates/` next to a JSON envelope that pins its sha256, and prints a numbered list for a human to choose from. `--pick 3` writes the chosen candidate into the registry table `refs/todo.toml` and never touches `refs.bib`: promotion into the formal bib stays a human act.

### figures

If the numbers on a figure have to lead back to the ledger, nobody should type them into a plotting tool by hand. The human writes the spec:

```toml
name = "acc"
kind = "bar"
caption = "两臂在同一组题上的解决数"
xlabel = "臂"
ylabel = "解决比例"
data = ["A1", "A3"]
labels = ["开臂", "对比臂"]
```

```bash
python3 -m factscribe figures gen .     # writes figures/gen/acc.tex, acc.csv (per-figure data), acc.bind.toml (binding table)
python3 -m factscribe figures check .   # four faces: spec, binding table, per-figure CSV, current ledger
```

A data point may only cite a fact id. A bare number in the spec is a configuration error, exit 2, and no half-written artefacts appear. If the ledger moved and the figure was not regenerated, `figures check` turns red and names every point.

### bundle

A submission ships dozens of files. Leave one out (usually a per-figure CSV or the evidence freeze file) and the reviewer gets an unreproducible package; ship one too many and nobody notices.

```bash
python3 -m factscribe bundle .                          # collect, gate, export (the package lands outside the project)
python3 -m factscribe bundle --verify mypaper.bundle    # recompute the MANIFEST.sha256 of a package
```

Three steps. Collection: the `\input` and `\include` closure from `main.tex`, plus refs.bib, figures/, tables/, facts/, the signed copies under runs/ and the three audit files. Checklist gate: every item judged mechanically (closure complete, every figure has its per-figure CSV, no bib entry missing a unique key, evidence.lock present and not stale, audit reports no red); any failing item exits 1 and lists every item, each in one of three states: pass, fail, waived. Export: the package directory plus `MANIFEST.sha256` (checkable with `shasum -a 256 -c`) plus `BUNDLE-MANIFEST.json` (the inventory: what was collected, what is only listed).

Journal differences live in the project-side `bundle-checklist.toml`, and the tool names no journal:

```toml
# an extra check: kind is one of exists / glob_min / regex
[[check]]
name = "匿名版存在"
kind = "exists"
path = "anonymous/main.tex"

# an exclusion: the whole file stays out of the package
[[exclude]]
file = "sections/ack.tex"
```

The full sample lives in [`examples/bundle-checklist.toml`](examples/bundle-checklist.toml).

## Three gates

The three gates cover numbers and citations, rewrite protection, and prose with terms. You can run them separately. Chaining all three gives a release check.

The first gate binds numbers and citations. Writing `\fact{A1}` declares that the numbers on that line belong to fact `A1`, and the audit requires every one of them to fall inside the fact's value domain. Every `\cite` family key must exist in `refs.bib`, and each entry needs `arxiv` or `doi`, while `@misc` entries may use `url`. Normalisation makes `1,234` equal `1234`, `0.90` equal `0.9`, and `53k` equal `53000`.

The second gate is the protection surface, meaning the six classes of content that a rewrite must not touch: fact markers, numbers, citations, math, tables, and labels. Punctuation-only edits should stay green. One changed number, formula, or citation is red, and the report gives file, line, and what changed.

```bash
python3 -m factscribe protect --before old/ --after new/
```

The third gate is the prose gate. It reports only mechanically checkable formulaic writing: dash parentheticals, headings that are too long or carry an explanation, stock connectives, empty adjectives, three-part lists repeated across paragraphs, overlong sentences, rhythm and sentence-length spread. It only shows yellow cards; it does not block and it does not touch the text. Four rules are rewrite rechecks: `HEADING_ECHO` catches a first sentence that restates its heading, `HEADING_RELATION_CHANGED` catches a swapped contrast word, `HEADING_SUBJECT_LOST` catches a dropped subject from an old heading, and `HEADING_SUBSTITUTED` catches a colon swapped for something else without a rewrite. The term layer has two lists: 33 paper terms from `paper-zh/GLOSSARY.md`, and 153 workspace process terms from the term registry.

## Change record

`tide` treats one rewrite as a transaction, and all four conditions must hold before it commits. The ledger trusts hashes, not a written summary.

Rise is what changed, derived from the file hashes of two directories. Fall is the real state after the edit, read from disk and hashed again. Blast radius is computed from the reverse `\input` and `\include` closure. Closure requires rise, fall, and blast radius to agree. If any piece is missing, everything rolls back: no ledger, no derived view, exit code 1.

There is no self-reported change list here. A person can read the result but cannot fill in the list, and the tool does not accept a hand-written note either. The spec lives in [`docs/design/SPEC-TIDE.md`](docs/design/SPEC-TIDE.md).

## Prescription layer

`prescribe` answers a different question: once a rule fires, how should the text actually change? It carries 13 prescriptions. Each one gives a verified fix and records known bad fixes as forbidden moves with counterexamples. When two prescriptions conflict, a fixed priority order decides, and the losing one says so. The spec lives in [`docs/design/SPEC-PRESCRIPTION.md`](docs/design/SPEC-PRESCRIPTION.md).

This layer adds no criteria and produces no score. It leaves every decision and exit code in `audit`, `style`, and `protect` untouched.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Green: no red, no yellow |
| 1 | Red: violations found |
| 2 | Configuration or usage error, the tool did not start |
| 3 | Yellow: finished, but unverified or unbound items remain; not fatal, not green |
| 4 | Internal tool error |
| 8 | A required tool is missing (PDF toolchain or build engine), never a silent pass |

A missing `factscribe.toml`, an empty ledger, empty prose, or a missing `refs.bib` exits 2 with a reason. Nothing passes silently.

## Known gaps

The remaining issues are recorded in [`docs/release/KNOWN-GAPS.md`](docs/release/KNOWN-GAPS.md). Three structural limits will stay. The trust root is a human signature, so an agent that forges both the ledger and the evidence cannot be caught. Author and implementer share one machine, so blind tests are weak blinding. There is no OCR, so any number carried by an image is red.

All three limits point at the same promise: the account, the material and the text stay in agreement, and the material was not swapped behind your back. None of that says a word about whether the conclusions hold.

## Reproduce and contribute

```bash
python3 -m unittest discover -s tests     # 1637 tests, fully offline
./scripts/preflight-ci.sh                 # local CI: clean clone + 3.10/3.11/3.12
```

**CI does not verify the PDF layer.** The GitHub runner cannot install poppler (the apt mirror is unreachable), so the install step is best-effort: it warns and continues. The 36 PDF-layer tests then skip themselves (`skipped=` in the test summary) and everything else still runs. Full PDF-layer coverage lives locally: `./scripts/preflight-ci.sh` (`skipped=0` when poppler is installed).

`examples/minimal/` is the acceptance sample: three facts, two sections, one fabricated number, and one fake citation. `audit` must report exactly those two reds.

Specs live in `docs/design/`, implementation notes in `docs/implementation/`, and history in `CHANGELOG.md`. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request, and bring tests with it.
