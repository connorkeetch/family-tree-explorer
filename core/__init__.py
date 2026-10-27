"""core -- the family-tree analysis library.

The genealogy pipeline's pure logic lives here so it can be imported by the web
API (and still by the thin root-level CLI shims). The stable internal contract is
the ``ancestors`` person list produced by :func:`core.parse_gedcom.build_people`;
everything else derives from it.

Ingest adapters produce that list (GEDCOM today; FamilySearch API later) and
:mod:`core.payloads` turns it into JSON-ready dicts for the API / SPA.
"""

from .parse_gedcom import build_people, write_outputs  # noqa: F401
from .payloads import (  # noqa: F401
    tree_meta,
    origins_summary,
    map_payload,
    fan_payload,
    deadends_payload,
    duplicates_payload,
)
from .privacy import (  # noqa: F401
    is_likely_living,
    count_living,
    redact_people,
)

__all__ = [
    "build_people",
    "write_outputs",
    "tree_meta",
    "origins_summary",
    "map_payload",
    "fan_payload",
    "deadends_payload",
    "duplicates_payload",
    "is_likely_living",
    "count_living",
    "redact_people",
]
