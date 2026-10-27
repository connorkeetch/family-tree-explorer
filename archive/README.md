# archive/

Superseded tooling, kept for reference. Nothing here is part of the active
pipeline.

## `find_frontier.py` + `DEEPER_PULL.md` — the frontier / collateral deeper-pull

These drove the old two-stage "pull the frontier, then merge deeper generations"
workflow: `find_frontier.py` scanned `ancestors.json` for the edge of a pull and
generated a chunked `pull_deeper.ps1` (getmyancestors `-i <frontier> -a 5`) that
ascended the parents of the deepest direct-line people and merged those **deeper
ancestors** back in. (It pulls direct-line ancestors, not cousins — the frontier
is on the direct line, and `-a` ascends parents only.)

**Superseded (2026-06)** by the single-stage **direct-line** refresh in the
project root:

```powershell
python pull_line.py -u <USER> -a 200 -o data/line_<date>.ged -l data/line_<date>.log --rate-limit 10
python parse_gedcom.py data/line_<date>.ged --root <ROOT_FID>   # parsed ALONE
python analyze_origins.py --in output/ancestors.json --outdir output
```

`pull_line.py` ascends the direct line only (no `-i`), skipping the two
per-item fetch storms (memories + notes) via `FS_SKIP`. Parsing the fresh file
**alone** is the only approach that reflects edits which *remove* data — the
merge path unions parents and keeps the richest record per FID, so it can never
subtract a deleted source or a detached parent.

`find_frontier.py` is still stdlib-only and self-contained; if you ever need the
old incremental deeper-pull (e.g. for a separately-rooted second tree) run it from
the project root as `python archive/find_frontier.py …`.
