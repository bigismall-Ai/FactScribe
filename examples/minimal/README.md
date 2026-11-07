# minimal — the 5-minute acceptance sample

A fake-but-consistent mini paper. It is **supposed to fail**, and it fails for
exactly the two reasons we document. Run it from the repository root:

```bash
python3 paperkit.py check examples/minimal    # exit 0  — the ledger is intact
python3 paperkit.py audit examples/minimal    # exit 1  — 2 red, 7 yellow
```

Expected audit reading (v1.1.0):

```
numbers : 10（bound 4 / unbound 5 / unmatched 1）
cites   : 2 calls, 2 keys; bib 2 entries (1 used)
[red] 2
  UNMATCHED_NUMBER  sections/02-results.tex:17:17 → 47.3   (fabricated latency)
  MISSING_CITE      sections/02-results.tex:19:14 → ghost2024 (citation that does not exist)
[yellow] 7  — unbound numbers in the table, unscanned main.tex, low binding rate
```

## What to look at, in order

1. `facts/01-core.toml` — three facts. `A1 = 10/16`, `A3 = 8/16`, and `A2` is
   derived from them with `expr = "(A1.num + A3.num) / (A1.den + A3.den) * 100"`.
   Each fact pins `results/swb16.md` by `source_sha256` (recomputed every run).
2. `results/MANIFEST.toml` — the human signature over that artifact. Delete it
   and `check` turns yellow (`NO_MANIFEST`); change one byte of
   `results/swb16.md` and both commands turn red (sha mismatch).
3. `sections/01-intro.tex` — the happy path: `10\fact{A1}`, `8\fact{A3}`,
   `56.25\%\fact{A2}`. Every number sits on a line bound to the fact that owns
   it, so those lines are green.
4. `sections/02-results.tex` — the two planted lies: `47.3\,ms` (no fact has it)
   and `\cite{ghost2024}` (not in `refs.bib`). The table above them is *unbound*
   (yellow), which is the difference between "we know" and "we hope".
5. `refs.bib` — every entry carries `doi` or `arxiv`; one entry is unused
   (`UNUSED_BIB`, info).

## Make it green (exercise)

Fix the sample in place, then re-run `audit`:

1. Add a fact for the latency, with a real `source` + `source_sha256`, and bind
   the line: `47.3\,ms\fact{A4}`. (Or delete the sentence.)
2. Delete `\cite{ghost2024}` or add the entry to `refs.bib`.
3. Bind the table cells: put `\fact{A1}` / `\fact{A3}` on the rows.
4. `main.tex` is outside `sections/*.tex`, hence `UNSCANNED_TEX`; either narrow
   the glob or accept the warning.

`audit --strict` is the CI form: any yellow becomes a non-zero exit.

## Copy it as a starting point

```bash
cp -R examples/minimal my-paper
cd my-paper
python3 ../paperkit.py check .
```

Then replace `facts/`, `results/` and `sections/` with your own, and write a
fresh `results/MANIFEST.toml` (`signed_by` = you). Do not reuse the sample's
hashes.
