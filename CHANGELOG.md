# Changelog

All notable changes to paperkit. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

paperkit is a pre-1.0-grade tool in behaviour but its gate contract is already
frozen (see `SPEC-V1.md` §5): exit codes and violation codes are the public API
and will not change without a major version bump.

## [Unreleased]

Nothing yet.

## [1.1.0] — 2026-11-07

Batch: three "the gate makes writing harder than it should" fixes. No change to
the red/yellow/binding judgement itself.

### Added
- `source_root` in `paperkit.toml`: resolve `fact.source` against an external
  workspace (e.g. a results directory outside the paper repo) while still
  enforcing `source_sha256`. Without it, sources must live in `results/`.
- Unit-suffixed numbers are understood as one token: `53k`, `3.5M`, `1.2B`,
  plus `3e-4`-style exponents, so `value = "53000"` can bind `53k`.
- Annotation macros are skipped wholesale (`\todoq`, `\todo`, `\pknote`,
  `\fixme`, `\note`, `\tbd`, `\pkignore`): their arguments are author notes, not
  paper claims, and no longer produce false reds. Audit reports the skipped
  annotation sites.

### Changed
- `--json` payload gains annotation bookkeeping (`annotations_skipped`,
  `annotation_sites`).
- Test suite 87 → 93 cases.

### Docs
- `IMPLEMENTATION-V2.md`: what changed and why, with before/after readings.

## [1.0.0] — 2026-11-07

### Added
- **Inline binding**: `\fact{A1}` (or `[[fact:A1,A3]]`) binds a line's numbers to
  facts. Every number on a bound line must be a token of that fact's `value`,
  else `BOUND_MISMATCH` (red). Numbers that resolve to a fact but are not bound
  are `UNBOUND_NUMBER` (yellow); numbers that resolve to nothing are
  `UNMATCHED_NUMBER` (red).
- **Provenance chain**: `source_sha256` is recomputed on every run; a missing or
  mismatching hash is red. `results/MANIFEST.toml` is a human-signed list of
  `path -> sha256`; unsigned artifacts are yellow (`UNSIGNED_RESULT`), a missing
  manifest is yellow (`NO_MANIFEST`).
- **Value literal check**: `VALUE_NOT_IN_SOURCE` (yellow) when a fact's number
  does not appear in its cited source.
- **Citation family coverage**: every `*cite*` command is extracted (with
  optional arguments), unknown `*cite*` commands fail closed
  (`UNKNOWN_CITE_COMMAND`); bib entries need `arxiv`/`doi` (or `url` for
  `@misc/@online/@software/@dataset`) in a plausible format
  (`BAD_STABLE_ID_FORMAT`); missing keys are `MISSING_CITE` (red).
- **Exit-code contract**: `0` green, `1` red, `2` config/usage error, `3`
  yellow, `4` internal error. Nothing passes silently: missing config, empty
  facts, empty sections and missing bib are config errors with a reason.
- **Derived facts**: `derived_from` requires `expr`; evaluation is a whitelisted
  AST walk (no `eval`), arithmetic only; cycles and superseded-parent references
  are checked. `LEDGER_CONFLICT` / `DUPLICATE_VALUE` are yellow.
- **Recursive sections**: `sections/*.tex` also matches `sections/**/*.tex`, plus
  the `\input` closure; tex files outside the audit closure are reported
  (`UNSCANNED_TEX`).
- **Single lexical pipeline**: verbatim/`\verb` → comments (`\%` is not a
  comment) → command arguments → sub/superscripts (`R^2`, `x_{12}` are
  structural) → numbers. Normalisation: `1,234`=`1234`, `0.90`=`0.9`,
  `10\%`=`10%`, `1\,000\,000`=`1000000`; `value = "10/16"` accepts `10`, `16`,
  `0.625`.
- `--resolve` (opt-in): check arXiv/DOI online (5 s timeout); network failure is
  `CITE_UNVERIFIED` (yellow), a definite "does not exist" is `UNRESOLVED_CITE`
  (red).
- `matrix` and `preamble` subcommands; `--json` on every subcommand;
  `--strict` on `check`/`audit` to promote yellow to failure (for CI).
- Red-team fixtures `tests/fixtures/redteam-b1`, `redteam-b4`.
- `SPEC-V1.md` (29-item red-team verdicts, defence boundary §2.3),
  `IMPLEMENTATION-V1.md` (where each gate lives, known holes).

### Changed
- README rewritten for v1 (exit codes, manifest, preamble).

## [0.1.0] — 2026-11-07

### Added
- First working version: `check` / `audit` / `matrix` / `build` subcommands.
- Fact ledger (`facts/*.toml`, append-only, one id per fact) with `claim`,
  `value`, `source`, `locator`, `confidence`, `kind`.
- Number scanning of `sections/*.tex`, citation extraction against `refs.bib`,
  coverage report, `--json` output.
- 46 tests and `examples/minimal/` acceptance sample (3 facts, 2 sections, one
  fabricated number and one fake citation that must be caught).
- `SPEC.md` / `IMPLEMENTATION.md`.
