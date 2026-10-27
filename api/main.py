"""FastAPI application: accounts, GEDCOM upload, and per-user analysis endpoints."""
import logging
import os
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

import anyio
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

import core
from core.duplicates import find_duplicates
from core.jev import Jev
from core.parents import settle
from core.parse_gedcom import build_people
from core.resolve_places import enrich

from . import store
from .auth import current_user, router as auth_router
from .config import https_only, session_secret
from .db import SessionLocal, get_db, init_db
from .models import User
from .schemas import TreeCreated

# Cap the merged upload size. Default 512 MiB comfortably fits the full real
# tree (~147k people ≈ 366 MB); override with MAX_UPLOAD_MB for larger pulls.
# Fall back to the default on a non-integer value rather than crashing at import.
try:
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "512"))
except ValueError:
    MAX_UPLOAD_MB = 512
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

app = FastAPI(title="Kinwhere API", version="0.2.0")

# The default secret is generated once in persistent app data; remote deployments
# can provide SESSION_SECRET explicitly.
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    same_site="lax",
    https_only=https_only(),
)
# allow_credentials so the SPA's cookie rides along (same-origin via the Vite
# proxy in dev; set explicit origins because credentialed CORS can't use "*").
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

# Create tables at import (idempotent) so the app works with or without lifespan.
init_db()


@lru_cache(maxsize=1)
def _jev() -> Jev:
    """One shared client (one cache, one lock) for every upload."""
    return Jev(Path(os.environ.get("JEV_CACHE", Path(tempfile.gettempdir()) / "jev_cache.json")))


def _enrich(people: list[dict]) -> None:
    """Jev passes -- map birthplaces the rules can't place, settle parent
    conflicts the dates can't, then score possible duplicate records (after
    parents, since it compares father/mother names) -- only when the server has
    OPENROUTER_API_KEY. Best effort: a Jev outage must never fail an upload."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        return
    for step in (enrich, settle, find_duplicates):
        try:
            step(people, _jev())
        except Exception:
            logging.exception("Jev %s failed; storing the tree without it", step.__name__)


def _people_or_404(db: Session, user: User, tree_id: str) -> list[dict]:
    people = store.get_people(db, user.id, tree_id)
    if people is None:
        raise HTTPException(status_code=404, detail="tree not found")
    return people


def _import_tree(paths: list[str], root: str | None, owner_id: int) -> dict:
    try:
        people, _root_xref, _model = build_people(paths, root)
    except (SystemExit, Exception) as exc:
        raise HTTPException(status_code=400, detail=f"could not parse GEDCOM: {exc}") from exc
    if not people:
        raise HTTPException(status_code=400, detail="no people found in the upload")
    _enrich(people)
    # Parsing, JSON serialization and the session stay on the worker thread.
    with SessionLocal() as db:
        return store.create_tree(db, owner_id, people)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/trees", response_model=TreeCreated)
async def create_tree(
    files: list[UploadFile] = File(...),
    root: str | None = Form(default=None),
    user: User = Depends(current_user),
) -> dict:
    """Parse + merge uploaded GEDCOM(s) and store the result against this user.

    Raw uploads are parsed then discarded; only the structured people list is kept.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="ged_"))
    paths: list[str] = []
    total = 0
    try:
        for i, f in enumerate(files):
            dest = tmpdir / f"upload_{i}.ged"
            # Stream to disk in 1 MiB chunks so a multi-hundred-MB upload isn't
            # buffered whole in RAM, and abort as soon as the running total
            # crosses the cap rather than after reading the entire file. Use an
            # async file handle so the write doesn't block the event loop
            # (FastAPI runs on AnyIO; the writes go to a worker thread).
            async with await anyio.open_file(dest, "wb") as out:
                while chunk := await f.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"upload too large (limit {MAX_UPLOAD_MB} MB)",
                        )
                    await out.write(chunk)
            paths.append(str(dest))
        if not paths:
            raise HTTPException(status_code=400, detail="no files uploaded")
        return await anyio.to_thread.run_sync(
            _import_tree, paths, (root or "").strip() or None, user.id)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.get("/api/trees")
def list_my_trees(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return store.list_trees(db, user.id)


@app.delete("/api/trees/{tree_id}")
def delete_my_tree(
    tree_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    if not store.delete_tree(db, user.id, tree_id):
        raise HTTPException(status_code=404, detail="tree not found")
    return {"ok": True}


@app.get("/api/trees/{tree_id}/export")
def export_tree(
    tree_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> JSONResponse:
    """Owner-only data export: the full structured tree as a JSON download."""
    people = _people_or_404(db, user, tree_id)
    payload = {"meta": core.tree_meta(people), "people": people}
    return JSONResponse(
        payload,
        headers={"Content-Disposition": f'attachment; filename="tree-{tree_id}.json"'},
    )


@app.get("/api/trees/{tree_id}/meta")
def get_meta(tree_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return core.tree_meta(_people_or_404(db, user, tree_id))


@app.get("/api/trees/{tree_id}/origins")
def get_origins(tree_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return core.origins_summary(_people_or_404(db, user, tree_id))


@app.get("/api/trees/{tree_id}/map")
def get_map(tree_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return core.map_payload(_people_or_404(db, user, tree_id))


@app.get("/api/trees/{tree_id}/fan")
def get_fan(tree_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return core.fan_payload(_people_or_404(db, user, tree_id))


@app.get("/api/trees/{tree_id}/deadends")
def get_deadends(tree_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return core.deadends_payload(_people_or_404(db, user, tree_id))


@app.get("/api/trees/{tree_id}/duplicates")
def get_duplicates(tree_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return core.duplicates_payload(_people_or_404(db, user, tree_id))


# ---- Serve the built SPA (single-origin production) ----------------------
# Dev: the SPA runs on Vite (:5173) and proxies /api here. Prod: this app serves
# the Vite build so the API and UI share one origin (no CORS; the session cookie
# just works). The catch-all is registered LAST so it never shadows /api routes.
_WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def spa(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not found")
    try:
        requested = Path(full_path)
        if requested.drive or requested.root:
            raise HTTPException(status_code=404, detail="not found")
        public = _WEB_DIST.resolve()
        candidate = (public / requested).resolve()
        if not candidate.is_relative_to(public):
            raise HTTPException(status_code=404, detail="not found")
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = (public / "index.html").resolve()
        if not index.is_relative_to(public):
            raise HTTPException(status_code=404, detail="not found")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    return FileResponse(index)


if _WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_WEB_DIST / "assets")), name="assets")
    app.get("/{full_path:path}")(spa)
