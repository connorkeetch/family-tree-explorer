# Development and command-line tools

The [README](../README.md) describes Docker installation. These instructions are
for contributors and people using the analysis library or CLI directly.

## Run from source

Use Python 3.12 and Node.js 22.12 or newer in the Node 22 line. Create a virtual
environment with `python -m venv .venv`. Activate it with
`.venv\Scripts\Activate.ps1` in PowerShell or `source .venv/bin/activate` in a POSIX shell.

```sh
python -m pip install -r api/requirements.txt
python -m uvicorn api.main:app --port 8000
```

In another terminal:

```sh
npm --prefix web ci
npm --prefix web run dev
```

Open http://localhost:5173. Vite proxies `/api` to the backend. Python does not
automatically load `.env`; set optional environment variables explicitly.
Local data and a stable generated secret default to the ignored `api_store/` folder.

## Checks

```sh
python -m unittest discover -s . -p "test_*.py"
npm --prefix web test
npm --prefix web run build
npm --prefix web audit
```

API tests require `api/requirements.txt`; missing optional packages cause explicit
skips, while application startup failures fail the suite. Tests use temporary
databases and synthetic records. The build generates browser dependency notices.

Exercise the final image, container recreation, and backup/restore with:

```sh
docker build -t family-tree:test .
python scripts/smoke_container.py --image family-tree:test
```

The container check uses its own containers, volumes, and fictional records.
CI runs Python/frontend checks on Windows and Linux and container checks on Linux.

## Code layout

| Path | Purpose |
| --- | --- |
| `core/` | GEDCOM parsing and ancestry calculations, using the standard library. |
| `api/` | FastAPI accounts, private per-owner trees, uploads, and analysis. |
| `web/` | React/TypeScript application built with Vite. |
| `scripts/` | Release validation helpers. |
| `tests/fixtures/` and `test_*.py` | Synthetic fixtures and Python checks. |
| `archive/` | Retired deeper-pull tooling, retained for reference. |

## Genealogy CLI

The root Python commands are thin entry points over `core/`. Obtaining a
FamilySearch export is a separate local step. The optional third-party
[getmyancestors](https://github.com/Linekio/getmyancestors) tool is not installed
in the app image. Create `data/` first, then:

```sh
getmyancestors -u YOUR_FS_USERNAME -a 15 -o data/full.ged
python parse_gedcom.py data/full.ged --root YOUR_ROOT_FID
python analyze_origins.py --in output/ancestors.json --outdir output
python trace_deadends.py --in output/ancestors.json
```

Enter your FamilySearch password into that tool's hidden prompt. Keep personal
records and credentials out of source commits; `data/`, `output/`, `.env`, and
`api_store/` are ignored by Git.

`pull_line.py` skips notes and memories while keeping source counts, reducing
requests in a deep direct-line pull. Parse a new full export alone when refreshing:
merging older files preserves their removed claims. Combine exports only when
that merge is intentional.

See [biological-line guidance](BIOLOGICAL_LINES.md) for another root or documented
parent overrides. `resolve_places.py`, `find_duplicates.py`, and `settle_parents.py`
run optional external AI passes; read the README's privacy notes first.
