# Contributing to paperkit

Thanks for looking. paperkit is a small, deliberately boring tool: one
stdlib-only Python file, offline tests, no plugins, no services. Most
contributions are "one more gate" or "one more lexical edge case".

**Read `docs/design/SPEC-V1.md` §2.3 first.** paperkit's honesty is its product: it checks
that the bookkeeping is consistent (`book -> evidence -> text`), not that the
science is true. Never make a change that lets the tool report green when it
does not know something.

---

## 1. Ground rules

| Rule | Why |
|---|---|
| **Standard library only.** No new dependencies, ever (dev-time too). | Users can copy the `factscribe/` package into a paper repo and run it. `pip install` must never be required. |
| **Tests are offline.** No network, no `--resolve` in tests (mock the degrade branch instead). | CI runs with no network; a flaky test is worse than no test. |
| **The exit-code contract is frozen.** `0` green / `1` red / `2` config / `3` yellow / `4` internal. | People wire paperkit into CI. Changing a code silently breaks their pipelines. |
| **Fail closed.** Unknown `*cite*` command, unreadable source, missing manifest => report, never skip. | A silent skip is a false green. |
| **No silent passes.** Missing `paperkit.toml`, empty facts/sections, missing bib => exit `2` with a reason. | |

Python `>= 3.10`. Keep `factscribe/` a stdlib-only package; it is imported by
the tests and packaged via `packages = ["factscribe"]` (see `pyproject.toml`).

---

## 2. 新判据准入单

新增或修改任何一条判据，提交前必须填完这张单。少一项就算没过。

| # | 项 | 做法 |
|---|---|---|
| 1 | **触发量** | 在至少四份真实语料上跑，报「每万字触发数」。超过 2/万字即调阈值或降级。 |
| 2 | **逐条判真假** | 把触发的句子逐条抄出来，标真阳性 / 假阳性，**不许只报总数**。 |
| 3 | **假阳性超半即回退** | 单条规则的假阳性超过一半，删掉重做，不许靠调阈值硬救。 |
| 4 | **正反例各三** | 测试里至少三条该触发的真实句子、三条不该触发的真实句子。 |
| 5 | **反向锁** | 写明这条规则在哪份语料上**应当 0 触发**，并把它写成测试。 |
| 6 | **单位写死** | 密度类指标必须写清每千字、每千词还是每句。混用会差十倍。 |

两条教训直接来自实战：

- **计数不等于文风。** 「单句『的』≥3」在真实句子上全是假阳性；改成「连续短修饰成链」才对。
- **误报预算管不住质量。** 一条规则可以低频、便宜、又全错。所以第 2 项是逐条看内容，不是看数量。

## 3. Set up and run

```bash
git clone <repo> && cd paperkit
python3 -m unittest discover -s tests -v     # 93 cases, all offline, ~5 s
```

No install step. If you want the console entry point:

```bash
python3 -m pip install -e .    # or: uv pip install -e .
factscribe --version
```

Acceptance sample — deliberately red, and it must stay that way:

```bash
python3 -m factscribe audit examples/minimal
# => exit 1, exactly 2 red (UNMATCHED_NUMBER 47.3, MISSING_CITE ghost2024)
#    and 7 yellow (unbound numbers, unscanned main.tex, low binding rate)
```

Useful while developing:

```bash
python3 -m factscribe audit examples/minimal --json | python3 -m json.tool
python3 -m factscribe check examples/minimal --strict
```

---

## 4. Where things live

| Path | Contents |
|---|---|
| `factscribe/` | Package: constants, facts/expr, config/TOML, tex scanner, citations, audit/check, rendering, CLI. |
| `tests/test_factscribe.py` | Unit + end-to-end tests; `make_project()` builds a throwaway project, `run()` shells out to the CLI. |
| `tests/test_fixtures.py` | Hostile/benign fixture regression line (SPEC expectations). |
| `tests/fixtures/redteam-b1`, `redteam-b4` | Counterexamples that must stay red. |
| `examples/minimal/` | The 5-minute acceptance sample (see its README). |
| `SPEC.md`, `docs/design/SPEC-V1.md` | Contract and defence boundary. `docs/design/SPEC-V1.md` wins on conflict. |
| `docs/implementation/IMPLEMENTATION*.md` | Where each gate lives, measured readings, known holes. |
| `CHANGELOG.md` | One entry per user-visible change. |

Key entry points in `factscribe/`:

- `scan_tex()` — the single lexical pipeline (mask verbatim/annotations →
  comments → command args → scripts → numbers). Add lexing fixes here.
- `run_check()` — ledger-only checks (ids, sha256, manifest, expr, cycles).
- `run_audit()` — binding, numbers, citations, coverage.
- `Issue(code, message, location, token, context, severity)` — every finding.
- `_exit_code()` / `_payload()` — severity → exit code, human and `--json` output.

---

## 5. Adding a gate (recipe)

1. **Pick a code name**: `UPPER_SNAKE` (`BOUND_MISMATCH`), unique in the file.
2. **Pick a severity** and justify it:
   - `red` — fabricated, self-contradictory, or evidence tampered with
     (must be fixed before the paper can be trusted);
   - `yellow` — unverified / unbound / unsigned / incomplete coverage
     (does not kill the run, but is not green);
   - `info` — advisory, never changes the exit code (`UNUSED_FACT`).
3. **Emit an `Issue`** with a precise location (`file:line:col` when you have
   one), the offending `token`, and a message saying *what* is wrong, *why* it
   matters, and the *one-line fix*. Match the tone of existing findings.
4. **Fail closed**: if you cannot decide, report yellow — never fall through to
   silently OK.
5. **Test both directions** in `tests/test_factscribe.py`:
   - a project that must trigger the new code (assert code, severity, exit code,
     and that the `--json` payload contains it);
   - a project just beside it that must **not** trigger it (no false positive).
   Use `make_project()` + `run_json()`; no network.
6. **Document it**: add the code to `README.md` (red/yellow/info list) and
   `README.en.md`, note the rule in `docs/design/SPEC-V1.md` if it belongs to the contract,
   and add a `CHANGELOG.md` line under `[Unreleased]`.

Example shape:

```python
red.append(Issue(
    "BOUND_MISMATCH",
    "line is bound to %s but contains %s, which is not a token of its value "
    "(fix: change the number or unbind the line)" % (fid, token),
    location="%s:%s:%s" % (rel, line, col),
    token=token,
))
```

Then a test:

```python
def test_bound_line_with_foreign_number_is_red(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = make_project(tmp, sections={"s.tex": "x 42\\fact{A1}\\n"})
        code, data = run_json(["audit", str(root)])
        self.assertEqual(code, 1)
        codes = [i["code"] for i in data["issues"]]      # issues = red
        self.assertIn("BOUND_MISMATCH", codes)
```

---

## 6. Pull requests

A PR is mergeable when:

- [ ] `python3 -m unittest discover -s tests` is green on 3.10, 3.11 and 3.12
      (CI does this; run locally at least once).
- [ ] **Every behaviour change comes with a test.** Bug fix => a test that fails
      before the fix. New gate => red case + non-triggering case.
- [ ] `examples/minimal` still produces exactly 2 red / 7 yellow (or the docs and
      `TestExampleAcceptance` are updated in the same PR).
- [ ] No new dependency, no network call in tests, no `eval`.
- [ ] Exit codes and existing violation codes unchanged (or the change is called
      out as breaking in the PR body).
- [ ] `CHANGELOG.md` updated under `[Unreleased]`.
- [ ] Docs updated when the contract or the output format changes.
- [ ] No generated files committed (`audit/`, `*.pdf`, `__pycache__/` are
      ignored — leave them that way).

Keep PRs small; one gate or one lexical family per PR is ideal. Describe the
failure you saw in real use, the reading before/after, and what you deliberately
did **not** try to catch.

## 7. Commit messages

Short imperative subject, then a body explaining the reading that motivated it:

```
audit: treat \todoq arguments as annotations, not claims

Before: a paper with 4 TODO notes produced 4 false reds.
After: annotations are masked; audit lists annotation_sites in --json.
```

## 8. License

paperkit is published under the license in `LICENSE` (currently a placeholder
pending the owner's decision — do not rely on it yet). By contributing you agree
your work is released under that license.

## Before you push: run the local CI equivalent

```bash
./scripts/preflight-ci.sh          # clean clone + Python 3.10/3.11/3.12 + external deps + acceptance step
./scripts/preflight-ci.sh --linux  # also run inside an ubuntu container on the siinfer host
```

Three CI failures so far came from **environment differences**, not code:

| difference | symptom |
|---|---|
| CI is a clean clone | fixtures referenced experiment files that were never committed → `MISSING_SOURCE` |
| ubuntu has no poppler | PDF tests green on macOS, red on CI |
| the runner has network | a resolver test assumed offline and flipped `unverified → verified` |

The preflight script checks all three locally before you push.

