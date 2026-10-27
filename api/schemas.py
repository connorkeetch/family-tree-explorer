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


class TreeCreated(BaseModel):
    id: str
    meta: TreeMeta
