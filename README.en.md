# paperkit — a mechanical gate for numbers and citations in papers (v1)

[中文](README.md) · **English**

For agents (or humans) writing a LaTeX paper who **may not invent numbers and may
not invent citations**. No agent harness, no model SDK, no dependencies: pure
standard library, Python ≥ 3.10.

In one sentence: every number in the prose must be **inline-bound** to a fact in
`facts/` (`\fact{A1}`) and must be a token of that fact's value; every fact must
pin a raw artifact in `results/` by `sha256`, listed in a **human-signed
manifest**; every `\cite`-family command must land on a stable identifier
(`arxiv`/`doi`). If the gate fails, the process exits non-zero.

> **Green = "the book has evidence, the evidence is unchanged, the text is
> bound" — not "the paper is true".** The boundary is spelled out in
> `SPEC-V1.md` §2.3.

## Run it

```bash
python3 paperkit.py check    <project-dir>            # the ledger: id/sha256/manifest/expr/conflicts
python3 paperkit.py audit    <project-dir>            # the core: binding + numbers + citations + coverage
python3 paperkit.py audit    <project-dir> --resolve  # also verify arXiv/DOI online (optional)
python3 paperkit.py matrix   <project-dir>            # write audit/matrix.md
python3 paperkit.py preamble <project-dir>            # write the \fact / \pkignore macros
python3 paperkit.py build    <project-dir>            # run project.build
```

Install it as a command if you prefer (`paperkit check ...`):

```bash
python3 -m pip install -e .    # or: uv pip install -e .
```

Every subcommand supports `--json` (for agents; stdout is JSON only);
`check`/`audit` also support `--strict` (yellow becomes fatal, for CI):

```bash
python3 paperkit.py audit examples/minimal --json
```

Exit codes: `0` green (no red, no yellow); `1` red (violations); `2`
config/usage error; `3` yellow (unverified / unbound / unsigned / conflict /
incomplete coverage — does not kill the run, but is not green); `4` internal
tool error. **Nothing passes silently**: a missing `paperkit.toml`, empty facts,
empty sections or a missing `refs.bib` exits `2` with the reason.

## Project contract

```
<project>/
  paperkit.toml            # project declaration (required)
  facts/*.toml             # fact ledger, append-only, one id per fact
  results/                 # in-project artifacts (read-only); source_root can point outside
  results/MANIFEST.toml    # human-signed manifest: path -> sha256 + signed_by
  sections/*.tex           # prose (recursive glob + \input closure)
  refs.bib                 # references, verified entries only
  audit/                   # generated (matrix.md / preamble.tex, not committed)
```

```toml
[project]
title = "..."
authors = ["..."]
sections = "sections/*.tex"      # recursive by default (also matches sections/**/*.tex)
facts = "facts/*.toml"
bib = "refs.bib"
manifest = "results/MANIFEST.toml"
source_root = "/abs/workspace"   # optional: resolve source against it (default: in-project results/ only)
build = "tectonic -X compile main.tex"   # empty = skip compilation
```

```toml
[[fact]]
id = "A2"
claim = "combined accuracy of both arms"
value = "56.25%"
source = "results/swb16.md"           # relative to source_root (or in-project results/)
source_sha256 = "0147ea0c…"           # recomputed and compared; missing/mismatch = red
locator = "§3 mean row"
confidence = "high"                   # high | med | low
kind = "claim"                        # claim | config (config stays out of the global value domain)
derived_from = ["A1", "A3"]           # non-empty => expr required
expr = "(A1.num + A3.num) / (A1.den + A3.den) * 100"   # arithmetic and parentheses only
supersedes = []
metric = ""
scope = ""
note = ""
```

Manifest `results/MANIFEST.toml` (not generated — a human writes it):

```toml
[manifest]
signed_by = "alice"
signed_at = "2026-11-07T12:00:00Z"
version = 1

[files]
"results/swb16.md" = "0147ea0c…"
```

## How a number "returns to the ledger"

- **Bind first, then compute**: `\fact{A1}` in the prose (or `[[fact:A1]]`,
  comma-separated for several ids) means "the numbers on this line belong to
  A1". The audit reverse-checks: **every** number on that line must be in the
  bound fact's value, else red `BOUND_MISMATCH`.
- **Unbound is not green**: a number that resolves to some claim fact but is not
  inline-bound is yellow `UNBOUND_NUMBER` (exit `3`); a number that resolves to
  nothing is red `UNMATCHED_NUMBER`.
- **Token anchoring**: `value = "42"` accepts `42`, not `1422`/`4242`/`4.2e-5`.
- **One lexical pipeline**: verbatim/`\verb`/`\pkignore` → comments (`\%` is not
  a comment) → command arguments → sub/superscripts (`R^2`, `x_{12}` are
  structural) → numbers.
- **Normalisation**: `1,234`=`1234`, `0.90`=`0.9`, `10\%`=`10%`, `53k`=`53000`,
  `3.5M`=`3500000`, `3e-4` is one token, `1\,000\,000`=`1000000`;
  `value = "10/16"` accepts `10`, `16`, `0.625`.
- **Explicit exemption**: `\pkignore{...}` or `\begin{pkignore}…\end{pkignore}`
  (typeset as usual, excluded from the audit). Macros come from
  `paperkit preamble`.
- Every unmatched number is reported as `file:line:col | number | whole line`.

## How a citation "lands on a stable identifier"

- The keys of `\cite / \citep / \citet / \citealp / \citeauthor / \citeyear /
  \upcite / \parencite / \textcite / \autocite / \nocite …` must exist in the
  bib, else `MISSING_CITE` (red); an unrecognised `*cite*` command fails closed:
  `UNKNOWN_CITE_COMMAND`.
- Each bib entry needs `arxiv`/`doi` per its type (`url` is allowed for
  `@misc/@online/@software/@dataset`), in a plausible format (old/new arXiv ids,
  `10.xxxx/...`), else `BAD_STABLE_ID_FORMAT`.
- Supports multiple bibs via `\bibliography`/`\addbibresource`, `@string`
  macros, and one level of crossref inheritance.
- With `--resolve`, arXiv API / doi.org are queried (5 s timeout): network
  failure ⇒ `unverified` (yellow); a definite remote "does not exist" ⇒
  `UNRESOLVED_CITE` (red).

## Yellow findings (exit `3`: not fatal, not green)

- `UNBOUND_NUMBER`: returns to the ledger but is not inline-bound;
- `NO_MANIFEST` / `UNSIGNED_RESULT`: no manifest, or unsigned files in `results/`;
- `VALUE_NOT_IN_SOURCE`: the fact's number does not appear in its source;
- `LEDGER_CONFLICT` / `DUPLICATE_VALUE`: the ledger contradicts itself / the same
  value claimed twice;
- `UNSCANNED_TEX` / `LOW_BINDING_RATE` / `FIGURE_UNVERIFIED`;
- `CITE_UNVERIFIED` / `RESOLVE_DEGRADED`: online verification did not complete.

## Hints (info, never change the exit code)

- `UNUSED_FACT`: on the ledger but never used (only prose markers count as use);
- `UNUSED_BIB`: in the bib but never cited.

## Tests

```bash
python3 -m unittest discover -s tests -v     # 93 cases, offline, ~5 s
```

`examples/minimal/` is the acceptance sample: 3 facts, 2 sections, with **one
fabricated number** (`47.3 ms`) and **one fake citation** (`\cite{ghost2024}`)
planted on purpose; `audit` must report exactly those **2 reds** (plus yellows).
Red-team counterexamples B1/B4 live in `tests/fixtures/` and stay red.

See `examples/minimal/README.md` for a 5-minute walkthrough.
The contract and its boundary are in `SPEC-V1.md`; changes and known holes are in
`IMPLEMENTATION-V1.md` and `IMPLEMENTATION-V2.md`. History: `CHANGELOG.md`.
