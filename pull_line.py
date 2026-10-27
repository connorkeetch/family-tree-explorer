"""pull_line.py -- getmyancestors WITHOUT the per-item fetch storms (memories +
notes). Faster, far fewer HTTP requests, much less 429 throttling. Sources are
kept (they feed the per-person source counts).

WHY
---
getmyancestors has TWO unconditional fetch storms, each one HTTP request per
item, with NO CLI flag to turn either off:

  * MEMORIES -- getmyancestors/classes/tree.py, Indi.add_data, the
    `for evidence in data.get("evidence", [])` loop hitting
    `/platform/memories/memories/<id>` (one request PER memory).
  * NOTES -- the final "Downloading notes..." phase in getmyancestors.main
    (`download_stuff`) schedules Indi.get_notes / Fam.get_notes for EVERY person
    and couple, each hitting `/platform/tree/persons/<fid>/notes` (and the
    couple-relationships equivalent) -- one request per person AND per family.

On a deep ascend these two dominate the request count and are the main cause of
FamilySearch 429 throttling -- they are what made the earlier pulls crawl.

This wrapper short-circuits those URLs inside Session.get_url, so:
  * memories and notes are skipped entirely (no request; no OBJE/NOTE records), but
  * persons, relationships, and SOURCES
    (`/platform/tree/persons/<fid>/sources`) are fetched exactly as normal.

Both note call sites guard their result (`if notes:` in tree.py), so returning
None is a clean no-op -- the person/couple simply ends up with zero notes. Same
for memories. Nothing else regresses.

WHAT TO SKIP
------------
Controlled by the FS_SKIP env var (comma-separated; default "memories,notes"):
    FS_SKIP=memories,notes   skip both (default -- fastest)
    FS_SKIP=memories         skip memories only (still fetch notes)
    FS_SKIP=notes            skip notes only (still fetch memories)
    FS_SKIP=                 skip nothing (behaves like plain getmyancestors)

Every getmyancestors argument passes straight through. Omit -i to start from your
own FamilySearch person and ascend your DIRECT line only (no -i = single root =
no cousins). Ascend as far as the tree goes:

    python pull_line.py -u <USER> -a 200 -o data/line.ged -l data/line.log --rate-limit 10

-a 200 means "as far back as it goes": the ascend stops on its own when a line
reaches a person with no parents (Adam/Eve included, however deep the line runs).
"""

import os

from getmyancestors.classes.session import Session
from getmyancestors.getmyancestors import main

# Each entry maps a skip name to a predicate over the request URL; a match means
# "don't fetch -- return None". Memories live under /memories/memories/<id> (a
# substring match, robust to anything trailing). Notes are the only endpoints
# ending in /notes (persons and couple-relationships); we strip any query string
# and trailing slash before the suffix check so it stays correct even if a
# locale/token param or trailing "/" is ever appended -- and it still won't catch
# /sources or /changes.
_MATCHERS = {
    "memories": lambda url: "/memories/memories/" in url,
    "notes": lambda url: url.split("?")[0].rstrip("/").endswith("/notes"),
}
_requested = {
    s.strip().lower()
    for s in os.environ.get("FS_SKIP", "memories,notes").split(",")
    if s.strip()
}
_SKIP = [pred for name, pred in _MATCHERS.items() if name in _requested]

_orig_get_url = Session.get_url


def _get_url_filtered(self, url, *args, **kwargs):
    # Drop the skipped per-item fetches; everything else (incl. /sources) passes.
    if url and any(match(url) for match in _SKIP):
        return None
    return _orig_get_url(self, url, *args, **kwargs)


Session.get_url = _get_url_filtered


if __name__ == "__main__":
    main()
