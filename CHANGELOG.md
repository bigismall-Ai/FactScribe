# Changelog

All notable changes to paperkit. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

paperkit is a pre-1.0-grade tool in behaviour but its gate contract is already
frozen (see `SPEC-V1.md` §5): exit codes and violation codes are the public API
and will not change without a major version bump.

## [Unreleased]

### Added
- `serve`: a local workbench HTTP API (`factscribe serve <project>`) for Mini FactScribe, local pages and external agents. It exposes the existing Python engine instead of a second one: `GET /api/health` (no token), `/api/capabilities`, `/api/status`, `/api/brief`, and `POST /api/audit`, each returning the same structured payload as the CLI (`brief --json` / `audit --json`). It binds loopback only (`127.0.0.1` / `localhost`; anything else is exit 2), generates a random 24-byte Bearer token unless `--token` is given, is read-only (no project writes; audit is not persisted), and keeps audit verdicts in `payload.exit` with HTTP 200 so red is not confused with a transport failure. Contract: `docs/design/SPEC-SERVE.md`; coverage: `tests/test_serve.py` (9 cases). Command count moves from 19 to 20.
- `docs/ADOPT.md`: adopting a finished paper is a migration, not an install, and the page starts with measured readings instead of reassurance. Two real arXiv sources were brought in read-only: Attention Is All You Need (1706.03762) scans 301 numbers and 76 citation calls into **399 red / 11 yellow in 0.26 s**, with 183 of the reds coming from table cells and 76 from an inline `thebibliography`; LoRA (2106.09685) scans 1277 numbers into **1479 red / 19 yellow**, 1011 of them table cells and 92 entries without a stable identifier. The page then gives the six-step migration, the three legal table bindings, the honest rule that a paper whose raw data is gone cannot be migrated, and the "one section at a time" work-order pattern with its coverage caveat.
- `doctor`: a pre-flight check for people who are about to run the gate and do not know what is missing. One command (`factscribe doctor [project]`) reports environment (Python ≥ 3.10, `tectonic`, poppler's `pdftotext`/`pdfinfo`/`pdfimages`, CJK fonts, git) and project readiness (project declaration, section closure, fact ledger, signed manifest coverage, evidence freeze), each with a one-line explanation and a copy-paste fix. It is deliberately **not** a gate: no criteria, no findings, exit code always 0 (a missing directory is still a usage error, exit 2), so it can never be confused with a verdict. Chinese projects are checked for fonts; English projects skip that check. `--json` exposes `checks[]`, `summary` and a deduplicated `next[]`. Coverage: `tests/test_doctor.py` (8 cases, including read-only, the two font paths, and the existing-paper branch). Docs: `docs/QUICKSTART.md` (five-minute first run) and `docs/TRIAGE.md` (what to fix first when the first audit is red), both linked from both READMEs; command count moves from 18 to 19.
- A conformance lock between the Python original and the JS port (batch 138). `tests/conformance/fixture/` is a small self-contained project that deliberately trips three reds (`UNMATCHED_NUMBER`, `BOUND_MISMATCH`, `MISSING_CITE`) plus one yellow (`UNBOUND_NUMBER`); `scripts/conformance-dump.py` projects it into a deterministic `tests/conformance/project.json` (manuscript joined in `\input` order, bib text, sources with sha256, facts), and both sides compare their **core code multiset** against `tests/conformance/expected.json`. `tests/test_conformance.py` asserts the Python reading and that the committed projection is byte-identical to a fresh one; `integrations/minifactscribe/tests/conformance.test.mjs` asserts the same multiset from `auditProject(project)`. Line numbers, `token` text and message wording are deliberately out of scope — the two text models differ. Known divergences (same code name, different meaning: `MISSING_SOURCE`, `BAD_SOURCE_PATH`; Python-only judgement faces such as manifests, coverage, tables and macros) are listed in the spec rather than papered over. Spec: `docs/design/SPEC-CONFORMANCE.md`.
- `evidence --unfreeze` and the re-freeze flow (batch 133). The frozen list is not read-only, but changing it now goes through a deliberate two-step: `evidence --unfreeze <project> --reason "..."` records why the list is being opened in `audit/evidence-log.ndjson` (append-only: action, reason, `hash_before` in 16 hex chars, and an optional `--at YYYY-MM-DD`; the tool never reads the system clock), then `evidence --freeze --reason "..."` writes the lock and a matching `freeze` record. Missing or blank `--reason` exits 2 and leaves the log untouched. While the last record is `unfreeze`, `audit` and `review` report yellow `EVIDENCE_UNFROZEN` with the latest reason (review keeps it out of the reject face); a changed list whose lock was not updated stays red `EVIDENCE_SET_CHANGED`. Re-freezing an unchanged, already-frozen list is idempotent and writes nothing; re-freezing after an unfreeze appends one `freeze` record and closes the state. Spec: `docs/design/SPEC-EVIDENCE-STAMP.md` §9.
- `evidence --suggest` / `evidence --freeze` and the frozen-set check (batch 132). The per-section "must cite" list no longer has to be written by hand: `--suggest` scans each section's `\fact{id}` markers in appearance order and prints a paste-ready `[evidence]` block, and `--freeze` writes `audit/evidence.lock` with a canonical sha256 (sections sorted, ids sorted, whitespace stripped) plus the plaintext section map. `audit` and `review` compare the current list with the lock: any change is red `EVIDENCE_SET_CHANGED`, and the message names the added, removed and moved ids. A missing lock means no check. The machine still does not judge which facts ought to be cited; it only judges whether a frozen list was edited. `brief` takes the column from `[evidence]` and falls back to the live suggestion marked "未冻结" when a section has no declaration. Spec: `docs/design/SPEC-EVIDENCE-STAMP.md` §8.
- `style` / `review` / `brief`: evidence stamp (batch 131). A project can list, per section, the fact ids that must appear there: `[evidence]` maps a section stem to an id array (`"09_discussion" = ["B1", "B2"]`). `REQUIRED_EVIDENCE_MISSING` is red (exit 1) when a declared section has no `\fact{id}` for a listed id, and the message carries the section, the id, and that id's claim and value. `EVIDENCE_DROPPED` is red in `style --diff` and `review` when a section had a `\fact{id}` before and no longer has it; it does not depend on `[evidence]`. Neither code is suppressed by the diff filter. `review` counts both in its reject face, `brief` adds a "must cite" column to the section list, and `metric_details.evidence` carries the readout. `protect` stays the whole-paper multiset check; the stamp is the per-section presence check, because a fact that survives elsewhere no longer proves the argument in the section that was emptied. Spec: `docs/design/SPEC-EVIDENCE-STAMP.md`.
- `style`: three readability proxy criteria (batch 129), all yellow and exit-code neutral. `NUMERAL_DENSITY` counts Arabic numeral tokens per 1000 English words / Chinese characters (default 40 at the time; off by default since batch 131) and reports "this section N numerals / threshold M / density X"; it is draft-stage only; `style --stage revision` downgrades it to `info` because deleting numbers trips `PROTECT_NUMBER_CHANGED` during rewrite acceptance. `SECTION_OVERLAP` compares 8-word / 12-character shingles between section and subsection blocks (default 12%, shorter block as denominator). `WE_ACTION_DENSITY` counts sentences whose subject is we/我们 and whose predicate is an action verb (default 15%); `we propose` and 「我们提出」 are excluded. Three matching prescriptions (`thin-the-numbers`, `merge-overlap`, `shift-to-implication`) are added to the prescription layer and to `polish --plan`.
- `audit`: `PDF_STALE` (red, exit 5) rejects a `main.pdf` older than any `.tex`/`.bib`/`facts/*.toml` in the audit closure (batch 127). A stale PDF is skipped entirely: its numbers no longer feed the P-04/P-05 multiset comparison, because a model can read the previous PDF and copy the numbers it "should" write instead of deriving them from evidence. `--build` compiles first, so it never trips this check; a project without a PDF is not affected.
- `fonts`: on-demand Fandol font cache (batch 123). `fonts --status` reports the cache at `~/.cache/factscribe/fonts/fandol` (override with `FACTSCRIBE_FONT_CACHE`); `fonts --fetch` downloads the 26.7 MB CTAN package with `urllib` (proxy-aware), extracts the four required OTFs (Song/Hei/Kai/Fang) plus licence text and bold variants, writes `SOURCE.txt`, and exits 4 on network failure or a missing font. Nothing is committed to git.
- `segment`: a stdlib-only Chinese tokenizer with part-of-speech tags, backed by the jieba dictionary (349,046 entries, copied as data under `factscribe/terms/seg.tsv.gz`).
- `style`: `ZH_LIGHT_VERB_NOUN` reports Chinese light-verb + noun constructions (`进行了分析` → `分析了`) with the action verb spelled out; item-counted, no density gate.
- `style`: five B-tier syntax rules (batch 105). `NOMINALIZATION_RATE` counts English nominalization per 100 words after stripping the document's five most frequent types (reported in `metric_details.nominalization_stripped`). `ZH_ASPECT_ZHE` counts verb + 着 per 1000 Chinese characters, excluding lexicalised forms. `ZH_DANG_WHEN` reports `当……的时候/之后/时`. `ZH_COLLOCATION_REDUNDANCY` reports ten redundant collocations with a deletion fix. `ABBREV_FIRST_USE` reports an abbreviation whose first use has no expansion; it is **off by default** and only runs under `style --report-abbrev` because all four corpora exceed the 2-per-10,000-word false-positive budget.

### Changed
- The Mini App now lives at `integrations/minifactscribe/` and presents itself as **MiniFactScribe** (plugin id `minifactscribe`, surface path `/minifactscribe`). FactScribe stays the engine; the app name makes the layer explicit instead of pretending the UI is the whole product. The old `factgate` name was an internal port label that had leaked into the UI. Static assets, REST routes, logger event names, the Node test paths and the conformance docs were updated in one sweep; the browser falls back to the old `factgate.tab` localStorage key so an existing tab preference survives. Installed copies under the old plugin id keep their own data directory and must be reinstalled under the new id; nothing in the Python package changed.
- CI: the Python matrix now includes 3.13 and 3.14 (previously 3.10–3.12), because `requires-python = ">=3.10"` has no upper bound and the project is developed on 3.14. A separate `wheel install` job builds a real wheel, installs it into a fresh venv and runs `prescribe --list` plus a Chinese `style --doc`, so the runtime-data packaging gap cannot come back silently.
- `style`: `NUMERAL_DENSITY` is off by default (batch 131). The built-in threshold is `null` (do not judge); the metric and the per-section readout are still computed, but no finding is produced, nothing enters `fired`, and the exit code is unchanged. The implementation and configuration remain: an explicit non-negative number in `[thresholds] numeral_density` restores the old behaviour, and `polish --plan` simply stops emitting those entries while the threshold is null. Reason: the criterion induced evidence deletion — a model lowered the density by replacing core numbers with "nearly every" / "most of them" / "some", leaving the audit green and the section's argument empty.
- `style` / `review` / `audit`: a project can no longer switch a criterion off by editing its own rules file (batch 130). `numeral_density_stage` is no longer read from `style-rules.toml` — the stage comes only from `style --stage draft|revision` (default `draft`), and a project that sets the key gets a `RULES_OVERRIDE_IGNORED` warning listing the ignored keys. Other keys (word lists, thresholds) stay overridable. When a project-level `style-rules.toml` is present, all three commands compare it key by key with the built-in defaults and print "this project overrides N rule keys" with the key names (informational, not a finding); `review` prints the line in its summary too. Reproduced from a real run where a model wrote `numeral_density_stage = "off"` instead of revising the prose.
- `build`: Chinese font fallback now prefers a complete local Fandol cache and injects `\setCJKmainfont`/`\setCJKsansfont`/`\setCJKmonofont`/`\setCJKfamilyfont{zhkai}` into the temporary copy only (batch 123). A missing cache keeps the batch-120 system-font fallback and says so in the output; an explicit `--cjk-font` still wins. The `build` shell path (non-empty `project.build`) now gets the same fallback, so V1 projects can produce a Fandol PDF.
- `style`: `HEADING_MALFORMED` now also rejects a heading ending in an English period (batch 112), matching the existing Chinese full stop rule. Headings ending in a common abbreviation (`al.`, `e.g.`, `i.e.`, `vs.`, `etc.`, `Fig.`, `Eq.`, `No.`, `cf.`, `Dr.`, `et al.`) are exempt; the list lives in `style-rules.toml` as `heading_period_exempt`. Run-in headings (`\paragraph`/`\subparagraph`) are exempt from the trailing-period rule (batch 113): the LaTeX convention puts the heading and body in one paragraph, separated by a period. Other punctuation in run-in headings and trailing periods in all other headings still report.
- `style`: `COLLOQUIAL_TRIAD` now recognises only template markers (`首先/其次/最后`, `第一/第二/第三`, `一是/二是/三是`, `其一/其二/其三`) and still requires the same template in adjacent paragraphs (batch 110). Comma or `、` enumerations no longer count, and list items are counted in full instead of being truncated to three; all four corpora drop to zero hits.
- `style`: `ZH_DANG_WHEN` now reports only when one paragraph contains at least two `当……的时候/之后/时` occurrences (batch 107). A single occurrence is normal Chinese, and counts do not accumulate across paragraphs. When it fires, every hit in that paragraph is listed with its position.
- `style`: `RHYTHM_PLATEAU` is informational by default (batch 109). Its reading stays in `metrics.rhythm_plateau` and is listed under `advisories`, but it does not enter `findings`, does not affect the exit code, and does not count as a yellow card; set `rhythm_plateau_level = "yellow"` to restore the old behaviour. `SENTENCE_UNIFORMITY` is the formal rhythm criterion.
- `tide`: when `--before`, `--after`, and `--snapshot` are all given, closure is judged first and the snapshot is saved only if it closes (batch 109). If it does not close, the command exits 1 and writes neither a snapshot nor a ledger entry. A pure `--snapshot` run now says explicitly that no closure check was performed.

### Fixed
- Packaging: a built wheel was missing every runtime data file. `pyproject.toml` declared `packages = ["factscribe"]` but no `package-data`, so `pip install` (non-editable) produced a package that imported fine and then failed at runtime: `prescribe` exited 2 on a missing `patterns/priority.toml`, and `style` on Chinese text raised `SegmentError` because `terms/seg.tsv.gz` was absent. Editable installs (`pip install -e .`, `PYTHONPATH`) hid this because they read the source tree. `[tool.setuptools.package-data]` now ships `terms/*` and `patterns/*`; a built wheel went from 36 to 57 files and `prescribe --list` / Chinese `style` were verified inside a fresh venv. Locked by `tests/test_packaging.py` (every non-`.py` file under `factscribe/` must match a declared glob) and a new `wheel install` CI job that builds, installs and runs the two data-dependent commands.
- `doctor`: no longer hands an existing paper the bare `init` command, which refuses a non-empty directory (exit 2) and left the advice impossible to follow. When the project declaration is missing, the check now distinguishes three cases: an empty directory (plain `init`), a directory with a root-level paper main file containing `\documentclass` (says it looks like a finished paper, points at `docs/ADOPT.md`, and recommends `init --force` only after naming the existing files that would be overwritten so they can be backed up first), and any other non-empty directory (says `init` needs an empty directory and does **not** suggest `--force`). The third case matters because running `doctor` inside a source repository full of nested fixture `.tex` files used to suggest `init --force` at the repo root, which would have clobbered its README. Coverage: the existing-paper and source-repo cases in `tests/test_doctor.py`.
- `fact add`: the ledger path is now derived from the project's `facts` glob instead of always being `facts/01-core.toml`. A project that declared `facts = "ledger/*.toml"` used to get its new fact written to a file outside the glob — `load_facts` never saw it, so the fact silently vanished from `check`/`audit`. The command now writes into the glob's fixed directory, and refuses with a clear message when the glob has no determinable directory. Coverage: `tests/test_fact_add.py`.
- `init --force`: overwriting is no longer silent. The command reports the existing files it replaced (human line plus `--json.overwritten`), so a paper's `README.md` or `refs.bib` cannot be clobbered without the operator seeing it. Coverage: `tests/test_init.py`.
- Configuration paths: v1 `sections` / `facts` and V3 `facts` now must be project-relative; absolute paths and `..` are a config error (exit 2) that names the key. Before, `sections = "../elsewhere/*.tex"` globbed outside the project and then crashed with a raw `ValueError` (exit 4), while a `facts` pattern outside the root was read as a ledger without any complaint. `bib` / `manifest` keep their old behaviour (a shared `../refs.bib` still works). `_glob_paths` also refuses any match that resolves outside the root as a second line of defence. Coverage: `tests/test_config_paths.py` (three cases). Docs: `docs/WHAT-IT-PROVES.md` now states the security boundary that `build` / `audit --build` execute `project.build` as a shell command and that `--resolve` only sends citation identifiers (not prose or local paths).
- Config shape: `[project] sections = "ms.tex"` (a single file, not a glob) with `facts` is now read as v1. The shape detector used to see the `sections` key, fall through to the V3 branch and then `fact add` refused with "only v1 is supported" — even though the user had a plain v1 project and just wanted the audit to start from one main file. Single-string sections now stays v1 unless a real V3 marker (`root_tex`, `output`, `level`, …) is present. Coverage: two shape cases in `tests/test_config_shapes.py` and an end-to-end `fact add` case in `tests/test_fact_add.py`. `docs/ADOPT.md` no longer tells people to add a `*` just to avoid this trap.
- `factgate` (JS port): the two source codes stop sharing one name (batch 139). `MISSING_SOURCE` used to mean "the fact has no `source` field"; it now means "`source` points at a source that is not in the project", which is the Python original's meaning, and a missing field reports `MISSING_SOURCE_FIELD` instead. `PRESCRIPTIONS` gains an entry for the new code, and the port no longer emits `BAD_SOURCE_PATH` at all (it has no path/URL model; that code stays Python-only). Divergence rows D1/D1b in `docs/design/SPEC-CONFORMANCE.md` are marked fixed; a doc-level assertion in `tests/test_conformance.py` keeps them honest. Coverage: five cases in `integrations/factgate/tests/audit.test.mjs`.
- `audit`: `UNSCANNED_TEX` no longer fires on a `.tex` that has nothing to scan (batch 135). A root file that is only a preamble and `\input`s was reported "not in the audit closure" every run — a noisy yellow in `paper/` and `paper-zh/`. The code now reports only files that really carry auditable content: after dropping comments and everything before `\begin{document}`, a file is exempt only when its body is blank/commands-only, holds no Arabic numeral token (same extraction as the numbers ledger, command arguments excluded), and has no `\fact{}`, no `\cite` family and no `\label`/`\ref`. Any file that fails one of those while outside the closure still reports yellow, and an unreadable file still reports (fail-closed). Coverage: `tests/test_unscanned.py` (10 cases). Spec: `docs/design/SPEC-V3.0.md` §8.1 note.
- `evidence --suggest`: the stdout stream is pinned to the paste-ready `[evidence]` block, with regression tests for the failure mode where a human summary lands on stdout and every later command exits 2 on the unparseable config (batch 134). The summary now comes from one `suggest_summary()` call and is written only to stderr in the default form and only to the `summary` field in `--json`; the JSON payload also gains `scanned` and `sections_with_facts`. Coverage: stdout parses with `tomllib`, contains no Chinese, the summary is on stderr, `--json` stdout is pure JSON, and appending stdout to `paperkit.toml` still lets `--freeze` exit 0. Record: `docs/implementation/EVIDENCE-FREEZE.md`.

## [1.3.0] - 2026-11-10

### Added
- `tide`: a transactional change record. Rise, fall, blast radius and closure are all derived from file hashes; if anything does not close, nothing is written and the command exits 1.
- `prescribe`: six executable prescriptions with forbidden moves and counterexamples. This layer adds no criteria and produces no score.
- `style --doc`: Markdown and plain-text documents can be checked without a `paperkit.toml` project.
- Term layer: 33 paper terms and 153 workspace process terms, with variant detection and synonym normalisation.
- Rewrite rechecks: `HEADING_ECHO`, `HEADING_RELATION_CHANGED`, `HEADING_SUBJECT_LOST`, and `TERM_VARIANT`.

### Changed
- Both READMEs rewritten against measured facts: ten commands, 18 prose rules, 563 tests, and the 1.3.0 exit-code table.
- `scripts/check-readme.py` now delegates prose and heading checks to `style --doc` instead of keeping a second copy of the rules.

### Fixed
- `audit`: dynamic `\input`/`\include` targets (macros, `#`, nested braces, empty) are now red `INPUT_DYNAMIC` (exit 5) instead of silently escaping the file closure.
- `audit`: a derived fact whose `expr` disagrees with its `value` is now red `EXPR_MISMATCH` (with both numbers and the error); `expr_tolerance` allows an explicit relative tolerance.
- `audit`: a number on a line already bound to a quantitative fact is now `BOUND_MISMATCH` when it is outside that fact's value; `UNMATCHED_NUMBER` is reserved for numbers no fact can claim. Red/yellow level and exit codes unchanged.

## [1.2.0] - 2026-11-09

### Added
- `style` subcommand: nine yellow rules for formulaic prose (dash, heading length and form, term in heading, rhythm, filler). Never blocks, never rewrites.
- `protect` subcommand: compares six protected surfaces between two drafts (facts, numbers, citations, math, tables, labels); anything changed is red.
- `verify-pdf`: text-layer and raster checks, bidirectional number multiset, stamp verification.
- `scripts/preflight-ci.sh`: clean-clone CI equivalent across Python 3.10/3.11/3.12.
- `scripts/check-readme.py`: README self-check with the same rules.

### Changed
- Blind-test results and remaining gaps documented in `docs/release/KNOWN-GAPS.md`.
- README rewritten to match v1.2.0 (short headings, no parenthetical dashes, verified commands and counts).

## [Unreleased]

### Added
- `protect` subcommand (batch 83): **rewrite protection-surface comparison**.
  `factscribe protect --before DIR --after DIR` recursively pairs `*.tex` files
  and reports anything on the protected surfaces that changed. Hard surfaces
  (red, exit 1): `\fact{}` markers, numbers (same tokenizer/`number_key` as
  `audit`, so `1,234`≡`1234`, `53k`≡`53000`), cite keys, math content hashes
  (inline/display/equation/align, whitespace-insensitive), tabular row cell
  counts + hashes, and label/ref keys. Soft surfaces (yellow, exit 3): heading
  text (downgraded to info by `--allow-renames`) and file additions/removals.
  Every finding gives `file:line: what was added/removed/changed`, never just a
  count. `tests/test_protect.py` (33 cases),
  `docs/implementation/PROTECT.md`. `audit`/`style` criteria and exit codes
  unchanged.
- `style` subcommand (batch 64): a **style-gate prototype** that flags
  mechanically checkable formulaic writing (connective density, sentence-length
  uniformity, empty adjectives, triads, paragraph templates, hedge stacks,
  repeated openers, extreme sentence length). It emits **yellow only** (exit 3),
  never blocks or edits the text, and explicitly does **not** evaluate or attempt
  to evade any AI detector. Output is file:line + original + concrete suggestion;
  `--json` for machines; `--prompt` emits a ≤400-character rewrite instruction
  for an LLM. Thresholds/vocabulary live in `style-rules.toml`
  (project → repo → built-in fallback). `tests/test_style.py` (26 cases),
  `docs/implementation/STYLE-GATE.md` (definitions, threshold rationale,
  zero-model baselines for `paper/` and `paper-zh/`). `check`/`audit` semantics
  and exit codes unchanged.
- `INPUT_TARGET_MISSING` (red/5, R-05): `\input`/`\include`/`\subfile`
  closure targets are now checked for existence (`.tex` auto-appended);
  a missing target is red (exit 5) instead of silently dropped. Targets inside
  comments/verbatim are ignored. Registered in SPEC §8.1.
- `UNUSED_BIB` (yellow/3, R-11): a bib entry that the scan closure never cites is
  now a yellow finding (previously an info hint). Exemptions: `\nocite{*}`,
  per-key `\nocite{key}`, and the new `bib_allow_unused = ["key", ...]` field
  (SPEC §10). Severity stays yellow even under `--strict`/L2; `--json.summary.bib_unused`
  lists the exact keys. `tests/test_unused_bib.py` (10 cases) and
  `docs/implementation/UNUSED-BIB.md`.
- SPEC §8「多码原则」: when several criteria hold at once, **all** codes are
  reported (no more "report only the first"); `EXPECT` matches if any one is
  present. "Most specific code only" now applies only inside a single
  criterion's ladder (e.g. evidence-chain nodes).
- `FACT_UNUSED_IN_SPAN` (yellow/3): a quantitative fact's `\fact{}` stays in the
  body but the body sentence carries no number for it, the number living only
  after `\appendix`; also reports `ASSERTION_DRIFT` (multi-code), so the
  composite run exits 1. `FACT_OUT_OF_SPAN` (red/1) is now reported alongside
  `ASSERTION_DRIFT` when a body-role fact's markers live only in the appendix.
- `DUPLICATE_VALUE` now also fires on the `audit` path (v3), not just `check`:
  two `kind=claim` facts whose `value` normalises to the same number
  (`canon_text`) with different `claim`s. New `dup_ok = true` field (§11.1)
  exempts a pair, as do an in-group `supersedes` and derived values.
- `tests/test_multi_code.py` (9 cases) and
  `docs/implementation/MULTI-CODE-AND-TWO-RULES.md` (holdout #6 diagnosis,
  false-positive boundaries).
- SPEC §8「错误码总表（唯一注册表）」: V2.2 §19.2 + V3.0 + §11 codes merged into
  one table with meaning/trigger/severity/exit; §8.4 pins one code per phenomenon.
  New dedicated codes: `COMPUTED_VALUE_UNREGISTERED`, `NUMBER_AS_CROSSREF`,
  `EVIDENCE_CHAIN_BROKEN`; `FACT_SCHEMA_INVALID` is pinned to exit 2 and now
  appears in `--json.findings`.
- SPEC §11.6「证据链完整性」: `facts.source` → `runs/` record → same-directory
  `record.json` → fact id; any broken node is red (`EVIDENCE_CHAIN_BROKEN`),
  with more specific `MISSING_SOURCE` / `SOURCE_SHA256_MISMATCH` taking precedence.
- `tests/test_evidence_chain.py` (10 cases: benign chain + breaks at each node)
  and `docs/implementation/CODES-AND-CHAIN.md` (code diff, chain criterion,
  holdout #5 diagnostic).

- V3.0 evidence model in `factscribe/v3.py`: `runs/` as the source root,
  `root_tex`-rooted closure, BU sentence fingerprints, assertion/approval
  verification, external key roots (`STAMP_KEY_UNTRUSTED`), and structured
  `numeric_macro_allow` shape/double-sign/expiry checks.
- V3 `audit` now runs the PDF gate (P-02..P-05) against the project `output`
  and emits P-04/P-05 multiset findings (W1/W2/W3/W4 accounted explicitly).
- JSON payload gains `findings` (issues + warnings) for machine scoring.
- Project schema aliases: `paperkit-project/3.x` and `factscribe/3.x`; mixed
  flat/`[project]` declarations; `facts` directory form; `number_locale = "dot"`.
- Two-argument `\fact{ID}{value}` is audited as rendered text; single-argument
  forward markers (`\fact{ID}10/16`) bind the following token.
- `tests/test_v3_evidence.py` (22 positive/negative criterion tests) and
  `docs/implementation/BLIND-PASS.md` (blind-pass record).
- SPEC §10「项目配置（冻结）」: one canonical `[project]` shape, a closed alias
  table (flat `schema` / `[project]+root_tex` / `[project]+sections`, `dot`→
  `period`, `refs`→`bib`, `title`→`name`), frozen defaults (`level=l1`,
  `sections` derived from `root_tex`), and unknown-field warnings in
  `config_warnings` (`docs/implementation/CONFIG-CONTRACT.md`).
- `factscribe/livetext.py`: source-layer "is the signed assertion actually
  live?" rules — markers hidden in macro bodies, in discarded macro arguments
  (`\newcommand{\ignore}[1]{}`), in `\iffalse` blocks, sentences with a marker
  but no literal number, and results relocated into `\appendix` are all
  `ASSERTION_DRIFT`; quantitative facts with no live marker also get
  `APPROVAL_MISSING_ASSERTIONS`.
- `source_sha256` accepts the canonical `sha256:` prefix; in V3 a mismatch also
  reports `APPROVAL_STALE` (S-03: it is part of `approve_target`).
- SPEC §11「事实账与 `\fact{}` 绑定（冻结）」: `facts/*.toml` may carry a
  `schema` header **and** a `[[fact]]` array (the holdout #4 form); `display`
  defaults to `[value]` and LaTeX escapes are normalized before strict
  equivalence; V3 facts may anchor evidence via `observation` without a local
  `source` path; error codes frozen (`FACT_ID_MISSING`, `DUPLICATE_ID`,
  `FACT_SCHEMA_INVALID`, `FACT_CONTAINER_INVALID`, `FACT_EVIDENCE_MISSING`).
- `numeric_macro_allow[].body_regex` accepts the §4 S-08 template in both
  `\(...` and `(?:...` spellings (same built-in shape).
- `docs/implementation/FACTS-SCHEMA.md`: schema table, error-code mapping,
  implementation locations, blind-test #4 per-item record.

### Changed
- SPEC §8.2: `FACT_UNUSED_IN_SPAN` is now yellow/3 (was red/1);
  `FACT_OUT_OF_SPAN` and `DUPLICATE_VALUE` triggers are spelled out.
- `style` (batch 71): adds `stage_assessment`
  (`draft|polished` / `rewrite|report_only`). Draft (`triggers >= 3` or
  `cv < 0.45`) keeps the itemised rewrite prompt; polished reports only and
  `--prompt` emits the single sentence
  `指标健康，建议不改；强行改写有降低自然度风险`. Blind reviews showed the
  rewrite prompt helps LLM drafts but harms polished prose. See SPEC-V3.0 §12
  and `docs/implementation/STYLE-V3.md`.

### Fixed
- `style` (batch 71): `\$` is now treated as a literal dollar sign, not the
  start of math mode. Previously a price such as `\$0.0486` masked the rest of
  the paragraph/file, undercounting words, sentences, paragraphs, rhythm
  plateaus and shifting sentence-length CV. `\(...\)`, `\[...\]` and the
  `\\[2pt]` line break now share the same escape-first rule. Corrected
  baselines: `paper/` 6390→6924 words and 368→397 sentences; `paper-zh/`
  10059→10893 words and 390→421 sentences. `tests/test_style.py` (256 cases).

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
