"""Pydantic response models.

Small response shapes are validated here and included in OpenAPI. Analysis
payloads from :mod:`core.payloads` are returned as plain dicts. The browser's
hand-written mirrors of both live in ``web/src/api/types.ts``.
"""
from typing import Optional

from pydantic import BaseModel


class TreeMeta(BaseModel):
    root: Optional[str] = None
    root_xref: Optional[str] = None
    root_fid: Optional[str] = None
    n_people: int
    n_direct: int
    max_gen: int
    n_coords: int
    total_sources: int
    total_memories: int
    living_count: int
    source_files: Optional[list[str]] = None


class TreeCreated(BaseModel):
    id: str
    meta: TreeMeta


class StartingPerson(BaseModel):
    id: str
    name: str
    year: Optional[int] = None
    place: Optional[str] = None


class ImportPreview(BaseModel):
    people: list[StartingPerson]
    suggested_root: Optional[str] = None
    candidate_count: int
