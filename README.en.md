# FactScribe

**English** · [中文](README.md)

The most dangerous thing about an AI-written paper is not that it reads badly. It is that it reads *plausibly*:

- **the numbers are invented** — "94.3% accuracy" sounds professional, and there is no such line in your experiment log;
- **the citations are invented** — `\citep{smith2023}` points at a paper that does not exist.

Both mistakes look completely normal while you read them. A reviewer will not go dig through your experiment logs, and a committee will not chase every DOI. So they stay in the manuscript, and they ship.

FactScribe is the gate that stops them. It is a **mechanical gate**: it pins every number and every citation in the prose back to a source file that a human signed for and that carries a hash. A number that does not match the ledger is red. A citation that does not resolve to a stable identifier is red.

**What it does not do**: judge whether your conclusions hold, whether the prose reads well, or whether a reviewer will like it. It does not write your manuscript either.

Standard library only. No model SDK. Python ≥ 3.10.

---

## Contents

- [Five minutes to first green](#five-minutes-to-first-green)
- [I only want to see how my paper looks](#i-only-want-to-see-how-my-paper-looks)
- [The Paper Workbench (Mini App)](#the-paper-workbench-mini-app)
- [Command reference](#command-reference)
- [Revising, with a human in the loop](#revising-with-a-human-in-the-loop)
- [Three gates](#three-gates)
- [Safety and network boundary](#safety-and-network-boundary)
- [Optional external pieces](#optional-external-pieces)
- [Exit codes](#exit-codes)
- [Known gaps](#known-gaps)
- [Reproduce and contribute](#reproduce-and-contribute)

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
| tectonic | `build` and `audit --build` | with a `project.build` shell command, a missing engine makes the shell report "command not found" (127), so the build fails and the exit code is **1**; when `project.build` is empty (tectonic is invoked automatically) it reports `PDF_TOOL_MISSING` and exits **8**; `audit` without `--build` never compiles, so it does not need it |

CJK fonts follow the same rule: `fonts --fetch` caches the Fandol fonts locally, and `build` falls back when a font is missing. `doctor` checks all of this, item by item, with a fix command for each.

## Five minutes to first green

Start with a minimal paper project, then put one real number in it.

```bash
python3 -m factscribe init mypaper && cd mypaper
```

`init` writes 7 files: the project declaration `factscribe.toml`, the main file `main.tex`, one section `sections/01-intro.tex`, an empty ledger `facts/01-core.toml`, the human sign-off manifest `results/MANIFEST.toml`, `refs.bib`, and a project `README.md`.

Next, make a **raw artefact** — an experiment log, a results file, a statistics dump, anything:

```bash
printf '50 道题里答对 42 道。\n' > results/exp.md
```

Record it in the fact ledger:

```bash
python3 -m factscribe fact add . \
  --id A1 \
  --claim "实验在 50 道题里答对 42 道" \
  --value "50/42" \
  --source results/exp.md \
  --locator "第 1 行"
```

> **`--value` must spell the numbers in the order the artefact has them.** The artefact above shows 50 first and 42 second, so the value is `50/42`; writing `42/50` is refused — the numbers are compared in order of appearance, and a mismatch means the number was made up. This gate is the **value hard check**, and it is the same rule in all three places it lives: the CLI's `fact add`, the MCP tool `factscribe_add_fact`, and the workbench's "insert fact".

`fact add` computes the sha256 of `results/exp.md` and prints one line. **It never signs for you** — copy that line into `results/MANIFEST.toml` yourself:

```toml
[manifest]
signed_by = "your name"
signed_at = "2026-11-23T16:00:00Z"
version = 1

[files]
"results/exp.md" = "d5e19855dfdd4d78394a2e721a6939733979998ac3a02f956bd5b90726a34ac4"
```

Then check the ledger itself:

```bash
python3 -m factscribe check .    # unique ids, live sha256, signed manifest, expression arithmetic, duplicate values
```

Finally hook the prose to the ledger — `\fact{A1}` means "the numbers on this line belong to A1":

```tex
\section{引言}

这项实验在 50 道题里答对 42 道\fact{A1}。
```

```bash
python3 -m factscribe audit .    # 0 red / 0 yellow -> green
python3 -m factscribe build .    # compile the PDF (needs tectonic)
```

Step by step lives in [`docs/QUICKSTART.md`](docs/QUICKSTART.md). Read [`docs/TRIAGE.md`](docs/TRIAGE.md) when you hit a wall of red, and [`docs/ADOPT.md`](docs/ADOPT.md) before you bring an existing paper in.

---

## I only want to see how my paper looks

If you do not want to keep a ledger and do not want to learn LaTeX macros, and you just want to know where your manuscript stands, start the local web workbench:

```bash
python3 -m factscribe workbench --root /path/to/your/papers
```

It scans that directory, treats every subdirectory containing `factscribe.toml` as a paper project (two language disks that share a root name, `paper` and `paper-zh`, are grouped into one project), starts a loopback-only local server and opens the browser. The left side holds the table of contents and the body; the right panel holds the check report, the prose gate, the bilingual comparison, the evidence lock, the fact ledger and the knowledge base.

That path is **read-only** and does not touch your disk (opening a project records one `last_opened`, which is a note that you were last in this paper, not an edit).

To ask "is this manuscript green right now" from your own code, use MCP: `factscribe mcp <project-dir>` exposes five read-only tools — `status`, `project`, `evidence_status`, `brief`, `audit`. `--allow-write` adds four write tools: write section, add fact, freeze evidence, unfreeze evidence.

---

## The Paper Workbench (Mini App)

The `workbench` command above is for scripts and local development. If you want to **write your paper inside your editor**, install the Mini App version: it is a MiniMax Code plugin that moves the whole gate into a page next to your chat window.

### What it is

A local paper workbench page (route `/workbench`). It is not a cloud service and it does not upload your manuscript: a thin Node shell takes a loopback port and serves the page, and the Python engine **source ships inside the package** (vendored into the plugin), so there is nothing to `pip install`. The engine is written in Python, so the machine still needs a Python ≥3.10 interpreter; the next section shows how to get one.

It is the same engine and the same criteria as the CLI — the reds you see in the page are the same reds you get in the terminal.

### How to install it

```bash
cd miniapp
./build.sh          # vendor the engine from the repo source, sync the front end, run the package contract self-check
./install.sh        # sync into ~/.minimax/plugins/factscribe/
```

`install.sh` is idempotent — running it many times gives the same result; `./install.sh --check` only reports whether the install is complete and writes nothing. Restart the MiniMax Code desktop app when it finishes.

MiniMax Code 3.1.11 and later can also import the package straight from a Git repository: paste the repository URL, pick the package directory, and confirm the preview.

### Python interpreter

The engine is written in Python, so the machine needs a **Python ≥3.10** interpreter. The engine source ships inside the package, so there is nothing to `pip install`; the interpreter is yours to install. The Mini App looks for one itself, and the settings page states what it found, what is missing and whether the version is high enough.

On Windows:

1. Download the 3.10 or newer installer from [python.org/downloads/windows](https://www.python.org/downloads/windows/). Leave 3.9 and older alone; the reason is below.
2. Tick **Add python.exe to PATH** during the install. Open a fresh command prompt afterwards and run `py -3 --version`; it should print something like `Python 3.12.x`.
3. A `py` launcher on its own is enough. The Mini App tries `py`, then `py -3`, then `py -3.14` down to `py -3.10`.
4. An interpreter outside PATH is found as well. The usual locations `%LOCALAPPDATA%\Programs\Python\Python3xx\`, `%PROGRAMFILES%\Python3xx\` and `C:\Python3xx\` are probed one by one.
5. If it still finds nothing, point the `FS_PYTHON` environment variable at the absolute path:

   ```bat
   setx FS_PYTHON "C:\Users\you\AppData\Local\Programs\Python\Python312\python.exe"
   ```

   Restart MiniMax Code afterwards; the settings page probes again.

One Windows trap: the Microsoft Store ships a `python` placeholder alias that takes over the command and looks like an installation that cannot run. If Python is really installed, turn `python` and `python3` off under "Settings → Apps → App execution aliases".

**Why 3.9 does not work.** The engine needs ≥3.10: on 3.10 it falls back to the TOML parser bundled with the engine, on 3.11 and newer it uses the standard library `tomllib`. Python 3.9 and older cannot run this engine, so the Mini App reports the highest version it found (3.9) and which executable it came from instead of saying that Python is missing. An old version can stay installed next to 3.10 or newer; the two do not conflict.

macOS and Linux behave as before: the Mini App tries `python3`, `python`, `/usr/bin/python3`, `/opt/homebrew/bin/python3` and `/usr/local/bin/python3` in that order, and `FS_PYTHON` can point at an absolute path there too. On macOS run `brew install python@3.12`; on Debian and Ubuntu run `sudo apt install python3.12 python3.12-venv`.

### How to open it

After the restart, ask the agent to "Open the FactScribe paper workbench". On first use the page asks for your **paper root directory** — any directory containing a `factscribe.toml` counts — and you can change it later from the settings page.

### What the page does

**Disks and body text** — a project may hold several language disks (`paper` / `paper-zh`). The table of contents sits on the left, and every row has a pen next to it: **click it to rename that section**. There is another pen beside the cover title, and it edits the `\title{…}` command in that disk's own entry file. Those are two separate write channels, each with its own fingerprint gate and atomic write (a `.bak` is left behind), and every other byte of the file stays untouched.

**The right panel is draggable** — body text on the left, panel on the right, and the divider **changes the ratio when you drag it** (clamped to 240–640px). The width is remembered only when you let go; double-clicking the divider restores the default. It survives a page reload.

**The body is the editor** — paragraphs are editable in place; there is no "enter edit mode" step. `\fact{}`, `\cite{}`, `\ref{}` and bound numbers show up as chips, and your typing does not disturb them.

**Check report** — the health summary plus the findings list. The readings of the last step of the four-step chain (evidence) are unchanged: declared / frozen / entries / sha256 / current_sha256 / mismatch each stand on their own.

**Prose gate** — reports only mechanically checkable formulaic writing: dash parentheticals, overlong headings, stock connectives, empty adjectives, three-part lists repeated across paragraphs, overlong sentences, rhythm and sentence-length spread. It only shows yellow cards; it does not block and it does not touch the text.

**Bilingual comparison** — compares the two language disks of one project entry by entry over the load-bearing fact fields and the `refs.bib` entries, and lists every drift.

**Evidence lock** — a separate read-only card: `frozen` / `entries` / `sha256` / `current_sha256` / `mismatch`. If the list moved after the freeze, `mismatch` tells you which sections and which facts changed, and why it is red.

**Fact ledger and knowledge base** — query the ledger (by id / claim / value / source), and browse the project files. Before you write anything involving a number, reconcile here first: **a number that is not in the ledger must not be invented**.

**Assistant panel** — runs on MiniMax Code's own model, with a Chinese / English interface switch.

### The assistant has no interface for writing your manuscript

That is a **safety boundary**, not a missing feature.

The assistant holds exactly **17 MCP tools**:

- **12 read-only**: `fs_status` (projects and disks), `fs_get_outline` (the section tree), `fs_read_section` (read body text), `fs_get_report` (check report), `fs_get_style` (prose gate), `fs_mirror_check` (bilingual drift), `fs_get_evidence_status` (evidence lock), `fs_get_brief` (writing brief: which verified numbers this section may cite), `fs_get_venue` (venue and layout requirements), `fs_query_facts` (query the ledger), `fs_search_kb` (search the knowledge base), `fs_list_proposals` (list pending proposals);
- **5 propose-only**: `fs_propose_edit` (rewrite one passage), `fs_propose_add_fact` (append one fact), `fs_propose_evidence_freeze` / `fs_propose_evidence_unfreeze` (freeze / unfreeze the evidence list), `fs_propose_export_bundle` (export the submission package).

"Propose" means: the assistant computes the change and writes a **proposal record**, and **your disk is not touched**. You see the before and after side by side in a diff card in the page, and **only clicking "Adopt" writes it to disk**. If you do not click, nothing is written at all.

Every proposal carries a `before_sha` fingerprint. If the passage changed elsewhere in the meantime (another window, an external editor), the adoption is refused (`BLOCK_STALE`), the card goes grey, and the ledger sha does not move.

The assistant also **cannot write in** a protection surface of its own making: a `\fact{}` or `\cite{}` that appears out of nowhere in the prose is stripped by the server and recorded as a warning. Numbers can only come from the `value` in the ledger, and the server runs them past the value hard check again.

The bilingual interface **applies to the display layer only**. The prose that lands on disk (`before_text` / `after_text` / `warnings` / `label` / `note`) is unchanged, word for word, so no translation can leak into your manuscript.

---

## Command reference

`factscribe` ships **29** subcommands. They are grouped below by the flow of writing a paper, not by internal module.

### Getting started

| Command | What it does |
|---|---|
| `init` | Scaffolds a minimal paper (7 files); the same arguments produce byte-identical output twice |
| `doctor` | Pre-flight check: environment (Python/tectonic/poppler/fonts/git) and project (declaration/ledger/manifest/freeze), each with a fix command; not a gate, it never changes a verdict |
| `fonts` | Fandol font cache: `--status` to check, `--fetch` to download locally (4 required OTFs, about 26.7 MB) |

### Writing

| Command | What it does |
|---|---|
| `preamble` | Generates the `\fact` and `\fsignore` macros in `audit/preamble.tex` |
| `brief` | Drafting brief: section list, usable claims and numbers, terms, hard constraints and length budget, read off the ledger for a writing model |
| `prescribe` | Prescription layer: what to change once a rule fired; 13 verified fixes, no criteria, no score |
| `terms` | Term candidates: `suggest` extracts candidates into a TSV, `add` writes only the forms you named with `--pick` |
| `evidence` | Evidence list: `--suggest` prints a paste-ready `[evidence]` block, `--freeze` freezes it, `--unfreeze --reason` thaws it with a record |

### The reconciliation gates

| Command | What it does |
|---|---|
| `check` | Validates the ledger: unique ids, live sha256, signed manifest, expression arithmetic, duplicate values |
| `audit` | Core check: inline binding, number-to-ledger, citation stability, coverage report |
| `matrix` | Writes the traceability matrix to `audit/matrix.md` |
| `fact` | Bookkeeping: `add` computes the hash and writes one fact (past the value hard check), it never signs the manifest for you; `import` brings a signed report into the ledger |
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
| `mcp` | MCP stdio server exposing five read-only tools — `status`, `project`, `evidence_status`, `brief`, `audit` — to agents; `--allow-write` adds write section, add fact, freeze evidence and unfreeze evidence |
| `web` | Local workbench page: the `serve` backend plus the workbench UI; read-only unless `--allow-write`, PDF builds only with `--allow-build` |
| `workbench` | Workbench page: scans `--root` for `factscribe.toml`, groups disks that share a root name into one project (`paper` pairs with `paper-zh`); body text and the status line come from the real files. It also writes: in-place paragraph editing (with `\fact`/`\cite`/`\ref` and bound numbers kept verbatim, `.bak` kept on save), section reorder/delete (moved to `sections/attic/`)/create, renaming a section and the paper title, inserting a fact binding from the paragraph menu, project create and edit |
| `workbench new` | Create a paper project: writes the skeleton under `--root` (`factscribe.toml` + `sections/` + `facts/` + `README.md` + `main.tex`); project directory and experiment report directory go into the `[workbench]` table; `--lang en/zh/both` picks how many language disks to create |

The contracts live in [`docs/design/SPEC-SERVE.md`](docs/design/SPEC-SERVE.md) and [`docs/design/SPEC-MCP.md`](docs/design/SPEC-MCP.md).

### Literature

| Command | What it does |
|---|---|
| `refs` | Literature registry: `dedupe` finds two keys pointing at one paper (same DOI or arXiv id), `register` checks the to-fill table `refs/todo.toml` and names each missing field, `search` fetches candidate metadata (promotion into the formal bib stays a human act) |

Every command except `mcp` accepts `--json`. `check` and `audit` accept `--strict`, which treats yellow as red for CI.

---

## Revising, with a human in the loop

This is the biggest difference between FactScribe and "let the AI edit my paper".

**The AI cannot write your manuscript directly.** Whether you use the CLI or the Mini App, there is exactly one route for the AI to change prose: it **proposes**.

1. **Build the proposal.** The assistant computes the change and writes a proposal record, **without touching the disk**. On the CLI side that is the `factscribe workbench` proposal API; on the Mini App side it is the five `fs_propose_*` tools.
2. **Look at the diff.** A diff card appears in the page: before and after side by side, with the warnings and the reason for the change.
3. **The human adopts.** Only clicking "Adopt" writes the change to disk. If you do not click, nothing happens.
4. **The fingerprint gate.** The proposal carries a `before_sha`. Before writing, the passage is checked again: has it been changed elsewhere? If so the write is **refused** (`BLOCK_STALE`), the card goes grey, and nobody else's words get overwritten.

The write itself goes through the **same channel** as editing by hand: atomic write, a `.bak` left behind (generations rotate — `.bak` is the previous version, `.bak.1` the one before that, and they never overwrite each other), and no protection surface may be dropped.

The four ledger and evidence actions (append a fact, freeze evidence, unfreeze evidence, export the submission package) travel the same "a human clicks before anything is written" route, with the same fingerprint gate.

Appending a fact carries an extra **ledger fingerprint gate**: the proposal records the sha of the target ledger file, and if the ledger moved elsewhere in the meantime, the adoption is refused and the card goes grey.

Before exporting a submission package you can **look at the inventory first** — the preview is only for you to read; the manifest gate still decides, and nothing is exported when it does not pass.

---

## Three gates

The three gates cover numbers and citations, rewrite protection, and prose with terms. You can run them separately. Chaining all three gives a release check.

**The first gate binds numbers and citations.** Writing `\fact{A1}` declares that the numbers on that line belong to fact `A1`, and the audit requires every one of them to fall inside the fact's value domain. Every `\cite` family key must exist in `refs.bib`, and each entry needs `arxiv` or `doi`, while `@misc` entries may use `url`. Normalisation makes `1,234` equal `1234`, `0.90` equal `0.9`, and `53k` equal `53000`.

**The second gate is the protection surface**, meaning the six classes of content that a rewrite must not touch: fact markers, numbers, citations, math, tables, and labels. Punctuation-only edits should stay green. One changed number, formula, or citation is red, and the report gives file, line, and what changed.

```bash
python3 -m factscribe protect --before old/ --after new/
```

**The third gate is the prose gate.** It reports only mechanically checkable formulaic writing: dash parentheticals, headings that are too long or carry an explanation, stock connectives, empty adjectives, three-part lists repeated across paragraphs, overlong sentences, rhythm and sentence-length spread. It only shows yellow cards; it does not block and it does not touch the text. Four rules are rewrite rechecks: `HEADING_ECHO` catches a first sentence that restates its heading, `HEADING_RELATION_CHANGED` catches a swapped contrast word, `HEADING_SUBJECT_LOST` catches a dropped subject from an old heading, and `HEADING_SUBSTITUTED` catches a colon swapped for something else without a rewrite. The term layer has two lists: 33 paper terms from `paper-zh/GLOSSARY.md`, and 153 workspace process terms from the term registry.

**The change record** (`tide`) treats one rewrite as a transaction: rise is what changed (the file hashes of two directories), fall is the real state after the edit (read from disk and hashed again — a human may not fill it in), blast radius is computed from the reverse `\input` and `\include` closure, and closure requires all three to agree. If any piece is missing, everything rolls back: no ledger, no derived view, exit code 1. There is no self-reported change list here — a person can read the result but cannot fill in the list.

---

## Safety and network boundary

**Offline by default.** `refs search` is the only command that reaches the network by default, and it sends the query terms only. Never prose, never a local path.

Two switches send a request only when you pass them explicitly: `audit --resolve` sends arXiv and DOI identifiers to the resolver, and `fonts --fetch` downloads the Fandol font package. And if you configure a custom model endpoint in the workbench, the AI chat sends your prompt to that endpoint — an address **you** typed, not the default behaviour.

**Run `build` and `audit --build` only on projects you trust yourself.** `project.build` is a shell command in the project declaration, and the tool runs it as written. `audit` on its own never compiles and never executes it; only `--build` does.

**What leaves your machine:** nothing from the check report, the evidence lock or the fact ledger — all of it is computed locally. The workbench and the Mini App both bind to the loopback address (`127.0.0.1`) only.

**Verify before you trust it.** `factscribe doctor` checks the environment (Python version, tectonic, poppler, fonts, git) and the project state (declaration, ledger, manifest, freeze) item by item, with a fix command for each.

---

## Optional external pieces

The runtime needs the Python standard library and nothing else (≥ 3.10). No model SDK, no third-party dependency, no LLM call anywhere. `pip install -e .` is a convenience; `PYTHONPATH` works just as well.

Only two external pieces are optional, and both degrade in a stated way:

| External piece | Who needs it | What happens without it |
|---|---|---|
| poppler (`pdftotext`/`pdfinfo`/`pdfimages`) | the PDF check layer of `verify-pdf` | reports `PDF_TOOL_MISSING` and exits 8, never a silent pass; every other command keeps working |
| tectonic | `build` and `audit --build` | reports the missing engine and exits 8; `audit` without `--build` never compiles, so it does not need it |

CJK fonts follow the same rule: `fonts --fetch` caches the Fandol package (4 required OTFs, about 26.7 MB) under `~/.cache/factscribe/fonts/fandol`, and `build` falls back to a system font when one is missing.

---

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Green: no red, no yellow |
| 1 | Red: violations found |
| 2 | Configuration or usage error, the tool did not start |
| 3 | Yellow: finished, but unverified or unbound items remain; not fatal, not green |
| 4 | Internal tool error |
| 5 | Red: coverage gap or trust-chain failure — a closure input that is missing, points outside the project, or cannot be resolved statically; a facts-ledger file that points outside the project or whose symlink cannot be resolved; and PDF/signature trust-chain failures. Not an ordinary violation: it means content never entered the audit |
| 8 | A required tool is missing (PDF toolchain or build engine), never a silent pass |
| 9 | `RED(ATTACK_OPEN)`: ATTACKS.md has a blocking/open entry |

The exit-code set is closed over 0–9; the authoritative table is §2.5 of [`docs/design/SPEC-V3.0.md`](docs/design/SPEC-V3.0.md). The table above lists the codes this repository can actually exit with; the remaining ones (6 proof not met, 7 stale/replay, 9 attack surface open) are not produced by any command yet.

A missing `factscribe.toml`, an empty ledger, empty prose, or a missing `refs.bib` exits 2 with a reason. Nothing passes silently. A ledger file that points outside the project, or whose symlink cannot be resolved, is rejected by the ledger and reported red (exit 5). It is never downgraded to an empty ledger.

The closed set of exit codes has one authority: `EXIT_CODE_CLOSED_SET` in [`factscribe/checks.py`](factscribe/checks.py). Adding an exit code is a change to the contract.

---

## Workbench runtime notes (restart after every code change)

The workbench is a **resident process**: the Python endpoints and the front-end static files are loaded at startup. If you changed code and still see the old page or the old behaviour, the usual cause is **an old process still running**, not a change that failed to take effect.

```bash
# 1) look for a stale workbench process
ps aux | grep -E "factscribe.*workbench" | grep -v grep

# 2) kill it (local dev machine; on a shared machine confirm it is yours first)
pkill -f "factscribe.*workbench"

# 3) start it again
python3 -m factscribe workbench --root /path/to/papers
```

Four rules:

1. **After changing Python or front-end code, restart the service before you verify** — otherwise you are testing the old process;
2. Static files are served with `Cache-Control: no-store`, but a browser may still cache CSS/JS; if a refresh does not show the change, force a hard reload (macOS: `Cmd+Shift+R`);
3. The read-only endpoints are `/api/disk/<project>/<disk>/report` and `/api/disk/<project>/<disk>/machine`, and `POST /api/disk/<project>/<disk>/report/rerun` is a **read-only re-run** of the real gate: a subprocess runs `factscribe audit --json` (no `--build`, so nothing is compiled and nothing is written), bounded to 120 seconds, with a before/after hash comparison of the project directory to **prove zero writes**;
4. The write endpoints are `POST /api/disk/<project>/<disk>/edit` (in-place paragraph editing, past the fingerprint gate and the protection chain), `POST /api/disk/<project>/<disk>/action` (`action=pdf|bundle|open_dir` — a real `buildpdf.auto_build` compile, a real `bundle.run_bundle` export, and macOS `open` for the project folder), `POST /api/disk/<project>/<disk>/fact/insert` (insert a fact binding), `GET /api/disk/<project>/<disk>/pdf` (serves the disk's `main.pdf` for preview/download), and `POST /api/project/<project>/reports/delete` (drops an imported draft record — **the report source file is left alone**).

On the Mini App side the rule is the same: change the **source** (`factscribe/workbench/static/`) and then run `./build.sh` to sync — never edit the payload directly, because the three `app.js` copies must stay byte-identical and a test enforces it.

---

## Known gaps

The remaining issues are recorded in [`docs/release/KNOWN-GAPS.md`](docs/release/KNOWN-GAPS.md). Below is the **current real state**, confirmed by measurement on this branch.

### Structural limits (will stay)

1. **The trust root is a human signature.** If an agent forges both the ledger and the evidence, the tool cannot catch it — it only guarantees that ledger, evidence and prose agree, and that the evidence was not swapped.
2. **Author and implementer share one machine.** Blind tests are weak blinding.
3. **There is no OCR.** Any number carried by an image is red.
4. **Plagiarism is checked at the literal layer only.** `textreuse` lists passages copied word for word and near-literal mechanical overlaps; rewrites, laundering and AI assembly are semantic-layer and out of scope.

### Workbench save semantics (measured)

When you save a passage from the workbench page, two rendering conventions **inside that passage** are preserved rather than restored byte for byte:

- **Line breaks inside the passage collapse into spaces.** A LaTeX paragraph folded over several lines in the source file becomes one line after saving (the blank lines between paragraphs are kept). It follows from "whatever the render layer shows is what the save layer stores".
- **`---` is written back as `—` (an em dash).** The LaTeX dash convention is normalised to a real em dash character at the render layer, and that character is what gets written back.

Both affect the **inside of that one passage** only. Other paragraphs in the file, the `\fact` / `\cite` / `\ref` protection surfaces and the bound numbers are all unchanged.

### Other current state

- **CI does not verify the PDF layer.** The GitHub runner cannot install poppler (the apt mirror is unreachable), so that step is best-effort: it warns and continues. **35** PDF-layer tests then skip themselves (`skipped=35` in the test summary) and everything else still runs — measured by hiding poppler from the suite, which reports `OK (skipped=35)`. Full PDF-layer coverage lives locally: `./scripts/preflight-ci.sh` (`skipped=0` when poppler is installed).
- **Bilingual disks are aligned by hand.** `mirror-check` reports drift; it does not sync.
- **The prescription layer adds no criteria.** The 13 prescriptions only give executable fixes; they change no verdict and no exit code in `audit`, `style` or `protect`.

All the structural limits point at the same promise: the account, the material and the text stay in agreement, and the material was not swapped behind your back. None of that says a word about whether the conclusions hold.

---

## Reproduce and contribute

```bash
python3 -m unittest discover -s tests     # 1764 tests, fully offline
./scripts/preflight-ci.sh                 # local CI: clean clone + 3.10/3.11/3.12
```

**CI does not verify the PDF layer.** The GitHub runner cannot install poppler (the apt mirror is unreachable), so the install step is best-effort: it warns and continues. The 35 PDF-layer tests then skip themselves (`skipped=35` in the test summary) and everything else still runs. Full PDF-layer coverage lives locally: `./scripts/preflight-ci.sh` (`skipped=0` when poppler is installed).

`examples/minimal/` is the acceptance sample: three facts, two sections, one fabricated number, and one fake citation. `audit` must report exactly those two reds.

Specs live in `docs/design/`, implementation notes in `docs/implementation/`, and history in `CHANGELOG.md`. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request, and bring tests with it.

---

## What it actually guarantees

The full wording is in [`docs/WHAT-IT-PROVES.md`](docs/WHAT-IT-PROVES.md), the design side in [`docs/design/SPEC-V1.md`](docs/design/SPEC-V1.md).

One sentence: **the tool keeps ledger, evidence and prose consistent, and it proves the evidence was not changed; it does not prove the paper's conclusions.**

A green audit means 0 red and 0 yellow — every number and every citation matched the ledger. It does **not** mean the paper is fine.
