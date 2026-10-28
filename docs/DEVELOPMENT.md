# Development and command-line tools

The [README](../README.md) describes Docker installation. These instructions are
for contributors and people using the analysis library or CLI directly.

## Run from source

Use Python 3.12 and Node.js 22.12 or newer in the Node 22 line. Create a virtual
environment with `python -m venv .venv`. Activate it with
`.venv\Scripts\Activate.ps1` in PowerShell or `source .venv/bin/activate` in a POSIX shell.

```sh
python -m pip install -r api/requirements.txt
python -m uvicorn api.main:app --reload --port 8000
```

In another terminal:

```sh
npm --prefix web ci
npm --prefix web run dev
```

Open http://localhost:5173. Vite proxies `/api` to the backend. Python does not
automatically load `.env`; set optional environment variables explicitly.
Local data and a stable generated secret default to the ignored `api_store/` folder.
The backend restarts when you save Python changes; Vite refreshes frontend changes.

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

## Follow a record from file to screen

Use the fictional [example GEDCOM](../web/public/example.ged) while developing.
Import it in the app and choose Avery Example as the starting person.

1. [UploadPage.tsx](../web/src/pages/UploadPage.tsx) previews the file, asks for
   the starting person, then calls `api.upload()` in
   [client.ts](../web/src/api/client.ts).
2. [api/main.py](../api/main.py) handles the upload. It calls
   `core.parse_gedcom.build_people()` to turn GEDCOM records into the shared
   people list, then [api/store.py](../api/store.py) saves that list and metadata.
   Raw uploaded files are discarded.
3. Analysis requests read the saved people list. [core/payloads.py](../core/payloads.py)
   builds the JSON for the map, family chart, and research views.
4. [DashboardPage.tsx](../web/src/pages/DashboardPage.tsx) loads those responses,
   applies the view's filters, and passes the data to `web/src/viz/` and
   `web/src/components/`.

The stored person uses descriptive names such as `birth_year` and
`on_direct_line`. Browser payloads use `year` and `dir`; `gen` means generations
from the starting person, `nat` is the origin label, `src` is the source count,
and `xref` identifies a person within that tree. Follow the mapping in
`core/payloads.py` rather than changing a stored field to match a screen label.

## Change a field or calculation

For example, `living_count` follows this path:

`core.privacy.count_living()` → `core.payloads._meta()` → `api.schemas.TreeMeta`
→ `web/src/api/types.ts: TreeMeta`.

For a displayed field, use the typed API response in the relevant page or component.

- For a field parsed from GEDCOM, start in `core/parse_gedcom.py`. For a value
  calculated from existing records, start in `core/payloads.py` or its calculation
  helper. Keep display-only changes in the frontend.
- If an endpoint uses a response model, update `api/schemas.py` too: fields absent
  from that model are removed from its response. All browser response types in
  `web/src/api/types.ts` are hand-written, so update the matching interface.
- Check callers before changing or removing a JSON field. Analysis functions are
  also exported from `core/__init__.py`; an unused browser field may still be part
  of the API or library contract. New stored fields must work with older saved
  trees, which do not acquire those fields until reimported.
- Keep parsing, parent selection, and origin inference in Python. The browser
  recalculates filter-dependent summaries in `web/src/lib/insights.ts`; country
  shading and summaries retain the whole-tree scope. Label that scope in the UI.
- The API retains precomputed `stats` and `sankey` fields for library/API callers.
  The interface derives filtered summaries from people and immigrant rows instead.
  Pedigree completeness comes from the full family-chart parent links so repeated
  ancestors fill every documented position. Keep migration grouping rules aligned
  with the shared cases in `tests/fixtures/migration.json`.

Start with the tests nearest the change: `test_parse_gedcom.py` for parsing,
`test_payloads.py` for analysis responses, `test_api.py` for response validation
and account isolation, and the relevant `web/*.test.cjs` file for frontend behavior.
Use synthetic records for new cases. Run the full checks above before submitting.

For frontend tests, reuse the loader, hook runner, and tree helpers in
`web/test-helpers.cjs` rather than copying a new test harness. These are focused
unit tests; they do not render a browser or replace a keyboard/mobile walkthrough
when changing interactions or layout.

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
