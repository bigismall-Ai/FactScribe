# Release checklist — paperkit v1.1.0 (local readiness, not pushed)

Date: 2026-11-08　Scope: make `paperkit-dev/` publishable to GitHub.
No push performed. No other workspace directories were modified.

## 1. Item-by-item

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | LICENSE | ⚠️ **file present, license NOT decided** | `LICENSE` = MIT text with `# TODO: confirm license with owner` header; candidates in §2 |
| 2 | `pyproject.toml` | ✅ | `pip install -e .` → `paperkit-1.1.0`, console script works; single-file `py-modules` (reason in §5) |
| 3 | CI | ✅ file, ⏳ not run on GitHub | `.github/workflows/test.yml`, matrix 3.10/3.11/3.12, offline `unittest discover`, YAML parses |
| 4 | English README | ✅ | `README.en.md` (full translation, "green ≠ true" kept); `README.md` top has `**中文** · [English](README.en.md)` |
| 5 | CHANGELOG | ✅ | `CHANGELOG.md`: 0.1.0 (d0df9a3) → 1.0.0 (b9a66e3 + 9d255bd) → 1.1.0 (6759fa0) |
| 6 | CONTRIBUTING | ✅ | `CONTRIBUTING.md`: run tests, add-a-gate recipe, PR requirements (test mandatory) |
| 7 | Hygiene | ✅ 3 defects found and fixed | see §4 |
| 8 | Version | ✅ | `python3 paperkit.py --version` → `paperkit 1.1.0`; local tag `v1.1.0` |
| 9 | Clean-repo self-check | ✅ | `git archive` → `/tmp/pk-release`, 93 tests OK, sample red as documented; see §3 |

Count: **9/9 files done; 1 open decision (license), 1 post-push verification (CI).**

Extra (not requested, small): `examples/minimal/README.md` — 5-minute walkthrough
with the expected reading and a "make it green" exercise.

## 2. License candidates — one line each

**Do not pick silently. Owner decides.**

| | MIT | Apache-2.0 | AGPL-3.0 |
|---|---|---|---|
| One-line difference | Do anything, just keep the copyright notice. | Same permissiveness **plus** an explicit patent grant and notice/trademark rules. | Strong copyleft **including network use**: anyone offering a modified version as a service must publish its source. |
| Obligations for users | Keep notice; no warranty. | Keep notice + `NOTICE` file; state changes; patent grant is terminated if you sue over patents. | All of Apache's-ish terms **plus** source disclosure for network deployments and derivatives (must stay AGPL). |
| Patent protection | None explicit. | Yes (section 3). | Yes (via GPLv3 base). |
| Fits when | You want maximum adoption of a small tool; nobody will be afraid to copy `paperkit.py` into a repo. | Companies/universities want patent clarity before adopting; you want a lightweight governance signal. | You want to prevent a closed-source hosted "paper checking service" from forking it. |
| Risk | A patent holder could still assert against users. | Slightly more paperwork (NOTICE, change notices). | Deters some corporate users and some package mirrors; not OSI-"business friendly" for everyone. |
| Recommendation for paperkit | **Default** — it is a 3.5k-line offline gate meant to be copied. | Choose if patent exposure matters. | Choose only if the intent is to keep hosted derivatives open. |

`pyproject.toml` references `license = { file = "LICENSE" }`, so replacing
`LICENSE` is enough — no metadata edit needed (a `classifiers` license entry is
deliberately omitted to avoid pinning the choice).

## 3. Clean-repo self-check (raw output)

Archive of the tagged release tree (this checklist included), extracted to an
empty directory (no `.git`, no `__pycache__`, no generated `audit/`, no
`main.pdf`):

```
$ cd paperkit-dev          # this directory
$ rm -rf /tmp/pk-release && mkdir -p /tmp/pk-release
$ git archive v1.1.0 | tar -x -C /tmp/pk-release   # tagged release tree
$ find /tmp/pk-release -type f | wc -l
38
$ du -sh /tmp/pk-release
340K

$ cd /tmp/pk-release
$ python3 -m unittest discover -s tests
.............................................................................................
----------------------------------------------------------------------
Ran 93 tests in 5.251s

OK

$ python3 paperkit.py --version
paperkit 1.1.0

$ python3 paperkit.py check examples/minimal ; echo "exit=$?"
exit=0

$ python3 paperkit.py audit examples/minimal ; echo "exit=$?"
== paperkit audit ==
project : examples/minimal
facts   : 3 条      sections: 2 个（扫描 2 个 .tex）
numbers : 10 个（bound 4 / unbound 5 / unmatched 1）
notes   : 已跳过 0 处批注（\todoq/\todo/\pkignore 等，内容不参与审计）
cites   : 2 次调用、2 个 key；bib 2 条（命中 1）
coverage: sections/01-intro.tex、sections/02-results.tex
[黄] 7 处（未核验/未绑定/未签名——不判死，但不许当绿）
[红] 2 处（必须修）
[提示] 1 条（非红非黄，不拦）
结论：2 红 / 7 黄 → 红（有违例）（退出码 1）
exit=1

$ python3 paperkit.py audit examples/minimal --json | python3 -c "..."
red   : ['UNMATCHED_NUMBER', 'MISSING_CITE']
yellow: ['UNBOUND_NUMBER' x5, 'UNSCANNED_TEX', 'LOW_BINDING_RATE']
```

Install check from the clean tree (second venv):

```
$ cd /tmp/pk-release && python3 -m venv /tmp/pk-venv2
$ /tmp/pk-venv2/bin/python -m pip install -e .
Building editable for paperkit (pyproject.toml): finished with status 'done'
Successfully installed paperkit-1.1.0
$ /tmp/pk-venv2/bin/paperkit --version
paperkit 1.1.0
$ cd /tmp && /tmp/pk-venv2/bin/paperkit check /tmp/pk-release/examples/minimal ; echo "exit=$?"
exit=0
```

"Runs outside the repo / does not depend on cwd" (project copied elsewhere,
invoked from `/`):

```
$ cp -R examples/minimal /tmp/pk-outside && cd /
$ python3 /path/to/paperkit-dev/paperkit.py audit /tmp/pk-outside ; echo "exit=$?"
== paperkit audit ==
project : /tmp/pk-outside
...
exit=1
```

`paperkit.py` contains no `os.getcwd()` / `Path.cwd()` / `__file__`-relative
project lookup; all paths derive from the `<project>` argument. Verified by the
run above.

## 4. Hygiene findings

Scanned: `grep -rn "/Users/\|/home/\|sk-…\|ghp_\|AKIA\|token=\|password\|secret\|api_key"`
over `*.py *.md *.toml *.tex *.bib *.yml`.

| Finding | Action |
|---|---|
| 1 absolute personal path: `IMPLEMENTATION-V2.md:69` `source_root = "/Users/<user>/workspaces/..."` | Replaced with `/abs/workspace` and wording de-identified |
| Internal paths `experiments/ctx-compiler-redblue/...`, `paper/results/` in SPEC/IMPLEMENTATION docs | Replaced with `experiments/demo/...` (historical docs keep the engineering story, not the workspace layout) |
| Internal batch/seat notes ("批 34", "D 席 / opencode") in `IMPLEMENTATION*.md`, `paperkit.py` comments, one test docstring | Neutralised to `paperkit contributors` / `v1.1` |
| Example signer name `signed_by = "moc"` in README, README.en, SPEC-V1 | Changed to `alice` (it is an example, tests don't depend on it) |
| **`tests/fixtures/redteam-*/results/run.log` was ignored by `*.log` but pinned by its MANIFEST** | Real packaging bug: a clean clone could not reproduce the fixture reading. Fixed with `!tests/fixtures/**/results/*.log`; both files are now tracked and present in the archive |
| `paperkit.egg-info/` created by `pip install -e .` was untracked | Added `*.egg-info/`, `build/`, `dist/` to `.gitignore` |
| `__pycache__/`, `*.py[cod]`, `.venv/` | Already ignored; archive contains none |
| `examples/minimal/main.pdf`, `examples/minimal/audit/` | Generated, ignored, untracked (not in archive) |
| Secrets (`sk-…`, `ghp_…`, `AKIA…`, private keys, `token=`) | None found (the only `token=` hits are the `Issue(token=…)` Python keyword) |
| `examples/minimal` self-explanatory? | Yes now: `examples/minimal/README.md` walks through facts → manifest → bound lines → the 2 planted lies, with expected reading and a fix exercise. 5-minute path: `check` (exit 0) → `audit` (exit 1, 2 red) |

## 5. Packaging decision (item 2)

Kept the single file, packaged as `py-modules`:

- `paperkit.py` is 87 KB / stdlib-only **on purpose** — it is meant to be copied
  into a paper repo and run with `python3 paperkit.py` and no install.
- Tests `import paperkit` from the repo root and shell out to `paperkit.py`;
  a package split would touch imports for zero user benefit.
- `pyproject.toml` therefore declares `py-modules = ["paperkit"]`,
  `scripts.paperkit = "paperkit:main"`, and reads the version from
  `paperkit.VERSION` (single source of truth, no duplicated `1.1.0`).
- Verified: editable install + console script from a clean archive.

## 6. Push to GitHub — exact command sequence

Prerequisite: create an **empty** repository on GitHub (no README, no
`.gitignore`, no license — otherwise the first push is rejected as non-fast-forward).

```bash
cd paperkit-dev

# 0) License must be decided first. Replace LICENSE with the chosen full text:
#    MIT: fetch https://opensource.org/license/mit
#    Apache-2.0: https://www.apache.org/licenses/LICENSE-2.0.txt
#    AGPL-3.0: https://www.gnu.org/licenses/agpl-3.0.txt
#    then remove the "# TODO: confirm license with owner" header lines.
git add LICENSE RELEASE-CHECKLIST.md
git commit -m "license: <MIT|Apache-2.0|AGPL-3.0>; release checklist"
git tag -f v1.1.0            # tag has never been pushed, safe to move

# 1) Add the remote (SSH shown; HTTPS alternative below)
git remote add origin git@github.com:<owner>/paperkit.git
git branch -M main

# 2) First push (branch + tag)
git push -u origin main
git push origin v1.1.0

# 3) Verify
git remote -v
git ls-remote --heads origin
git ls-remote --tags origin
```

HTTPS alternative for step 1 (needs a PAT with `repo` scope as the password):

```bash
git remote add origin https://github.com/<owner>/paperkit.git
```

If the first push is rejected because the web repo was initialised with files:

```bash
git fetch origin
git rebase origin/main      # or: git pull --rebase origin main
git push -u origin main
```

Optional, before the first push only — make the history read cleanly for
outsiders (commit messages currently say "batch 36"):

```bash
git rebase -i --root        # reword messages; then git tag -f v1.1.0
```

## 7. Remaining notes / open items

1. **License is the only decision blocking a "proper" publication** — a
   placeholder MIT file is not a license choice. Until it is replaced, GitHub
   will label the repo as MIT (detected text) while a TODO header says otherwise.
2. **CI has not executed yet** (no remote). Locally validated: YAML parses,
   and the exact CI steps (version, 93 tests, sample must exit 1) all pass by
   hand in `/tmp/pk-release`.
3. CI deliberately does **not** `pip install` (offline constraint); the install
   path is proven locally in two venvs instead.
4. No badges in READMEs — they need the final `<owner>/<repo>` URL. Add after
   the first push:
   `![tests](https://github.com/<owner>/paperkit/actions/workflows/test.yml/badge.svg)`
5. `examples/minimal` uses a synthetic 16-question set ("SWB16"); no real
   experiment data, no personal data. `results/swb16.md` is fabricated-but-
   consistent by design.
6. This checklist is a release-process document. If you do not want it public,
   drop it from the published tree before pushing:
   `git rm --cached RELEASE-CHECKLIST.md && echo RELEASE-CHECKLIST.md >> .git/info/exclude && git commit -m "release: drop internal checklist"`.
7. Version string is `paperkit 1.1.0` (argparse's `prog + version` form); the
   bare `1.1.0` is also present in the same line and in `--json`.
