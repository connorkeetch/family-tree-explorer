"""Pydantic response models.

Only the small, stable response shapes are modelled here (handy for OpenAPI and
the SPA's generated types). The large analysis payloads from :mod:`core.payloads`
are returned as plain dicts -- modelling every nested field would be churn while
the SPA shape is still settling; the SPA mirrors them with hand-written TS types.
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
