# Pulling deeper: generations 15 → 20+ (and beyond)

> **ARCHIVED (2026-06).** This is the old **frontier / collateral** deeper-pull
> workflow (`find_frontier.py` → generated `pull_deeper.ps1` → merge). It is
> **superseded** by the single-stage direct-line refresh —
> `python pull_line.py -a 200 …` parsed **alone** (see the project root and
> `pull_line.py`). Kept for reference; the tool now lives at
> `archive/find_frontier.py`, so prefix the `find_frontier.py` commands below
> with `archive/`.

This archived example assumes a hypothetical tree stopping at generation 15
and explains how to extend it without re-pulling existing ancestors. **You run every
FamilySearch command yourself** — the scripts here only prepare commands and
merge the results. No credentials are ever stored, printed, or committed.

## Why the tree stops at generation 15

It is **not** a limit in our code. `parse_gedcom.py` assigns generations by
breadth-first search up from the root and handled 15 generations fine.

The ceiling comes from the original `getmyancestors` pull's **ascend depth**
(`-a`). `getmyancestors` ascends exactly `-a` generations and then stops:

```python
# getmyancestors.py
for i in range(args.ascend):          # args.ascend == 15 for the original pull
    todo = tree.add_parents(todo) - done
```

For example, **every person at generation 15 might be a leaf** (zero known
parents), making a clean wall. Shallower
generations have a natural *mix* of leaves and dead-ends; a flat wall at exactly
15 is the signature of `-a 15`. There is **no hard cap on `-a`** in
getmyancestors — `-a 20` would work — so the only question is *how* to go deeper
efficiently.

## Two ways to go deeper

### Option A — just re-pull with a bigger `-a` (simple, wasteful)

```powershell
getmyancestors -u <YOUR_FS_USERNAME> -a 20 -o data/full.ged
# (password is prompted with hidden entry; omit -u too to be prompted for both)
python parse_gedcom.py data/full.ged --root <YOUR_ROOT_FID>
```

This works, but it re-fetches **all** known people every time, which is
slow and hammers the FamilySearch API. Fine as a one-off; bad for repeated
deepening.

### Option B — pull only the frontier, then merge (recommended)

Fetch parents **only** for the people at the edge of the current pull, then
merge the new ancestors into the existing tree. This is incremental, repeatable,
and only fetches *new* people.

#### Step 1 — find the frontier and generate the pull commands

```powershell
python find_frontier.py --in output/ancestors.json --source-ged data/full.ged
```

This writes (under `output/`, gitignored):

- `frontier_fids.txt` — the FamilySearch IDs at the edge (the example's gen-15 leaves);
- `pull_deeper.ps1` — a PowerShell script with the chunked `getmyancestors` pulls
  (≤ 400 IDs each, to stay under the Windows command-line limit) followed by the
  merge + re-parse. It contains no credentials; it reads them from `.env`.

#### Step 2 — put your credentials in `.env` (once)

So you aren't prompted for every chunk, the script reads your login from a
`.env` file. Copy the template and fill it in:

```powershell
copy .env.example .env
notepad .env        # set FS_USERNAME and FS_PASSWORD, save
```

`.env` is **gitignored** — it is never committed. Any value you leave blank or
as the placeholder is prompted for instead (password hidden). If your password
has spaces or `# = "` characters, wrap it in double quotes.

> Security note: to avoid re-typing, the password is passed to `getmyancestors`
> via its `-p` flag, so it is briefly visible to other processes **on your own
> machine** while a pull runs. It is never sent anywhere else or committed. If
> you would rather not store it on disk, leave `FS_PASSWORD` blank/placeholder
> and the script will prompt for it once per run with hidden entry.

#### Step 3 — run the generated script

```powershell
.\.venv\Scripts\Activate.ps1
.\output\pull_deeper.ps1
```

Each chunk fetches 5 more generations (`-a 5`) for its frontier IDs into
`data/deeper_me_partNN.ged`, using the credentials from `.env`.

The script finishes by merging everything and rewriting `ancestors.json`:

```powershell
$parts = Get-ChildItem data/deeper_me_part*.ged | ForEach-Object { $_.FullName }
python parse_gedcom.py data/full.ged $parts --root <YOUR_ROOT_FID>
```

#### Step 4 — re-run the analysis

```powershell
python analyze_origins.py --in output/ancestors.json --outdir output
```

## How the merge works

`parse_gedcom.py` accepts **multiple GEDCOMs** and merges them at the model
level (it never writes an intermediate GEDCOM, so there are no dangling-pointer
bugs):

- individuals are **deduplicated by FamilySearch ID** (`_FSFTID`);
- families are deduplicated by the `(father FID, mother FID)` couple;
- every parent relationship found in any file is unioned together;
- generations are recomputed by BFS **from the original root** (`--root <YOUR_ROOT_FID>`),
  so the newly appended ancestors get the correct generation numbers (16, 17, …).

`--root` takes a **FamilySearch ID** (e.g. `XXXX-XXX`), which is stable even
though the internal `@xref@` ids are renumbered by the merge.

> **Alternative merge tool.** `getmyancestors` ships with `mergemyancestors`,
> which merges GEDCOMs by the same FID/couple keys and writes a single combined
> `.ged`. If you prefer one merged artifact, you can run
> `mergemyancestors -i data/full.ged data/deeper_me_part*.ged -o data/merged.ged`
> and then `parse_gedcom.py data/merged.ged --root <YOUR_ROOT_FID>`. Our multi-file
> parse does the equivalent in one step.

### Verifying a merge

After a merge, the summary printed by `parse_gedcom.py` should show the total
count **grow** and the max generation increase. Two invariants always hold and
are worth a sanity check:

- **No duplicate FIDs.** Merging is keyed on FID, so a person pulled in two
  files appears once. (Self-test: merging `full.ged` with itself yields the same
  count and zero duplicate FIDs.)
- **Counts grow by only the new people.** Re-pulling existing people does not
  inflate the total.

## Repeating the cycle (going from 20 → 25 → …)

Each pass pushes the wall out by your `-a` value. To go deeper again, just point
`find_frontier.py` at the **updated** `ancestors.json` — it auto-detects the new
deepest generation and collects that frontier:

```powershell
python find_frontier.py --in output/ancestors.json --source-ged data/full.ged
.\output\pull_deeper.ps1
```

Keep the `data/deeper_me_part*.ged` files from previous passes; the merge step
re-reads all of them, so the tree accumulates rather than resets. Returns
diminish as you go deeper (more leaves are genuine dead-ends — see
[trace_deadends.py](../trace_deadends.py) and `output/deadends.json`), but the
mechanism is the same at any depth.
