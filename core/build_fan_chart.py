"""Fan-chart data helpers.

The interactive fan chart now lives in the web SPA (web/src/viz/FanChart.tsx);
the static self-contained HTML generator was retired. This module keeps only the
pure record-building helpers that :func:`core.payloads.fan_payload` reuses to
shape the per-person records the chart renders. Stdlib only.
"""
from .analyze_origins import origin_detail, origin_of, parent_slots, settlement_of

UNTRACED = "(untraced)"
GRAY = "#a9a9a9"


def nat_of(person):
    label, resolved, _ = origin_of(person)
    return label if (label and resolved) else UNTRACED


def short_place(place):
    if not place:
        return ""
    parts = [t.strip() for t in place.split(",") if t.strip()]
    return ", ".join(parts[-2:]) if len(parts) > 2 else place.strip()


def parents_of(person, by_xref):
    """Selected father/mother; old records fall back to sex then position."""
    if "father_xref" in person or "mother_xref" in person:
        return tuple(x if x in by_xref else None for x in parent_slots(person))
    pxr = [x for x in (person.get("parent_xrefs") or []) if x in by_xref][:2]
    father = next((x for x in pxr if by_xref[x].get("sex") == "M"), None)
    mother = next((x for x in pxr if by_xref[x].get("sex") == "F"), None)
    if father is None and mother is None and pxr:        # no sex info -> positional
        father = pxr[0]
        mother = pxr[1] if len(pxr) > 1 else None
    elif len(pxr) == 2:                                  # one sex known -> other is leftover
        if father is None:
            father = next((x for x in pxr if x != mother), None)
        if mother is None:
            mother = next((x for x in pxr if x != father), None)
    return father, mother


def build_records(people, by_xref, color_of, branch_of=None, dna_of=None):
    """Per-person fan-chart records. ``branch_of``/``dna_of`` (from
    analyze_origins.branch_tags / dna_lines) let the SPA dim wedges that don't
    match the active branch/DNA filter."""
    branch_of = branch_of or {}
    dna_of = dna_of or {}
    recs = {}
    for xref, p in by_xref.items():
        father, mother = parents_of(p, by_xref)
        nat = nat_of(p)
        # US state of birth (American births only) so the SPA's state filter can
        # dim non-matching wedges the same way branch/DNA do -- mirrors the `st`
        # field on core.payloads' person rows.
        st = settlement_of(p) if nat == "American (USA)" else None
        name = p.get("name") or " ".join(
            t for t in (p.get("given"), p.get("surname")) if t).strip() or "?"
        recs[xref] = {
            "n": name,
            "g": (p.get("given") or name.split(" ")[0] or "?"),
            "s": p.get("sex") or "",
            "y": p.get("birth_year"),
            "dy": p.get("death_year"),
            "p": short_place(p.get("birth_place")),
            "nat": nat,
            "c": color_of.get(nat, GRAY),
            "fid": p.get("fs_id"),
            "fa": father,
            "mo": mother,
            "gen": p.get("generation"),
            "br": branch_of.get(xref, ""),
            "dna": dna_of.get(xref, ""),
            "st": st or "",
        }
        if origin_detail(p)[3]:          # country came from the AI place reading
            recs[xref]["ai"] = 1
    return recs
