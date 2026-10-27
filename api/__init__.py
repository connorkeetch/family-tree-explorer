"""FastAPI web layer for the family-tree app.

Thin HTTP surface over :mod:`core`: accept a GEDCOM upload, parse it once via
``core.build_people``, persist the structured people list, and serve the analysis
payloads (:mod:`core.payloads`) as JSON for the SPA. Auth + a real database land
in Phase 3; FamilySearch OAuth ingest in Phase 4.
"""
