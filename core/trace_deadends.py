"""
trace_deadends.py -- where does the immigrant-origin model run out of road?

The immigrant-origin model climbs each of your ancestral lines until it reaches
the first ancestor born outside the US/Canada (the immigrant), then stops. Some
lines never get there: they dead-end on a New-World-born ancestor who has no
recorded parents. The weight on those lines is what the map calls "origin not
yet identified" (~11.6%).

This script re-walks that exact model (it imports origin_of / NEW_WORLD_LABELS
from analyze_origins, so it can't drift) and, instead of dumping the leftover
into one bucket, records WHERE and WHY each line ends:

  reason            meaning
  ----------------  --------------------------------------------------------
  new-world leaf    born in US/Canada (incl. colonial), no parents recorded
  unknown-place     no birthplace at all, no parents recorded
  unresolved-place  birthplace we couldn't classify, no parents recorded
  copied-place      a wife whose only birthplace is her husband's, copied in
  one parent only   one parent recorded, the other missing (half the line)
  missing record    parent referenced but the individual isn't in the file
  cycle             pedigree loop in the data (bad record)

The crucial split: a dead-end at the PULL DEPTH (generation 15, the wall your
`-a 15` download stopped at) is probably ARTIFICIAL -- FamilySearch may well
have those parents; you just didn't fetch them. A dead-end SHALLOWER than that
is GENUINE: the pull would have grabbed the parents if they existed, so their
absence means the paper trail truly ends there.

Usage:
    python trace_deadends.py
    python trace_deadends.py --in output/ancestors.json --max-gen 15 --top 40
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from . import analyze_origins as ao


# ---------------------------------------------------------------------------
# Likely-origin estimate for a colonial-American brick wall.
#
# These are HISTORICAL PRIORS, not facts: colonial colonies each drew from
# specific parts of Europe, so the colony where a line dead-ends is a strong
# hint at the undocumented immigrant's origin. Ordered most-specific first
# (frontier counties before the general state they sit in). Each rule:
#   (keywords matched as substrings of the lowercased place,
#    estimate label, confidence, one-line rationale)
# ---------------------------------------------------------------------------
REGION_RULES = [
    (["massachusetts", "connecticut", "rhode island", "plymouth",
      "new hampshire", "new haven", "province of maine"],
     "English (New England)", "high",
     "New England was settled almost entirely by English Puritans"),
    (["new netherland", "new amsterdam", "albany", "rensselaer",
      "schenectady", "esopus", "bergen, "],
     "Dutch (Hudson Valley)", "medium",
     "the Hudson Valley / New Netherland was Dutch-settled"),
    (["mohawk", "tryon", "schoharie", "palatine"],
     "German (Mohawk/Palatine NY)", "medium",
     "the Mohawk Valley (Tryon Co.) was settled by Palatine Germans"),
    (["lancaster", "berks", "bethel", "germantown", "lebanon",
      "northampton"],
     "German (Pennsylvania)", "medium",
     "SE Pennsylvania (Lancaster/Berks) was Palatine German -- 'PA Dutch'"),
    (["frederick, virginia", "frederick county", "augusta", "shenandoah",
      "rockingham", "rockbridge", "botetourt"],
     "Scots-Irish / German (VA frontier)", "medium",
     "the Virginia frontier (Shenandoah Valley) was Scots-Irish & German"),
    (["north carolina", "south carolina", "carolina"],
     "Scots-Irish (Carolina backcountry)", "low",
     "the Carolina backcountry was heavily Scots-Irish; the coast more English"),
    (["virginia", "maryland"],
     "English (Tidewater VA/MD)", "medium",
     "Virginia/Maryland Tidewater planters were predominantly English"),
    (["philadelphia", "pennsylvania"],
     "Mixed (English/German/Scots-Irish)", "low",
     "colonial Pennsylvania mixed English/Welsh Quakers, Germans & Scots-Irish"),
    (["georgia"],
     "Mixed (English/Scots-Irish)", "low",
     "colonial Georgia drew English and Scots-Irish settlers"),
    (["new jersey", "delaware"],
     "Mixed (English/Dutch)", "low",
     "the Delaware Valley mixed English, Dutch and Swedish settlers"),
]


def likely_origin(place):
    """Estimate the undocumented immigrant origin behind a colonial dead-end.

    Returns (label, confidence, rationale). For a non-place (no birthplace) or
    a place we can't pin to a colony, returns an honest 'unknown'. The colony
    keywords are substrings ("berks", "lancaster", "lebanon"), so a place that
    resolves to an Old-World country never reaches them -- "Berkshire, England"
    isn't Palatine German.
    """
    if not place or not place.strip():
        return "Unknown (no birthplace recorded)", "none", "no place to reason from"
    label, resolved = ao.infer_nationality(place)
    if resolved and label not in ao.NEW_WORLD_LABELS:
        return "Unknown (outside colonial America)", "none", "the colony priors only cover New-World births"
    p = place.lower()
    for keywords, est, conf, why in REGION_RULES:
        if any(kw in p for kw in keywords):
            return est, conf, why
    if resolved:
        return "Unknown (unspecified American)", "none", "New-World birth, colony not identifiable"
    return "Unknown (place not identifiable)", "none", "birthplace too vague to reason from"


def trace_deadends(people_by_xref, root_xref):
    """Trace the immigrant model once per person; aggregate dead-end events.

    Each event: {xref, name, surname, gen, depth, place, reason, weight}.
    Depth is the shortest kept path to the person. Summing the weights
    reproduces the model's total 'untraced' fraction.
    """
    if root_xref not in people_by_xref:
        return [_ev(None, {}, -1, 1.0, "missing record")]

    def immigrant(person):
        label, resolved, _ = ao.origin_of(person)
        return resolved and label is not None and label not in ao.NEW_WORLD_LABELS

    weights, processed, cut = ao._ancestor_weights(people_by_xref, root_xref, immigrant)
    cut_edges = set(cut)
    depths = {root_xref: 0}
    events = {}

    def emit(xref, weight, reason):
        key = xref, reason
        if key not in events:
            events[key] = _ev(xref, people_by_xref[xref], depths[xref], 0.0, reason)
        events[key]["weight"] += weight

    for xref in processed:
        person = people_by_xref[xref]
        if immigrant(person):
            continue
        weight = weights[xref]
        parents = [p for p in ao.parent_slots(person) if p]
        if not parents:
            label, resolved, _ = ao.origin_of(person)
            if resolved and label in ao.NEW_WORLD_LABELS:
                reason = "new-world leaf"
            elif person.get("place_copied"):
                reason = "copied-place"
            elif person.get("birth_place"):
                reason = "unresolved-place"
            else:
                reason = "unknown-place"
            emit(xref, weight, reason)
            continue
        for parent in parents:
            if (xref, parent) in cut_edges:
                emit(xref, weight / 2.0, "cycle")
            elif parent not in people_by_xref:
                emit(xref, weight / 2.0, "missing record")
            else:
                depths[parent] = min(depths.get(parent, depths[xref] + 1), depths[xref] + 1)
        if len(parents) == 1:
            emit(xref, weight / 2.0, "one parent only")
    return list(events.values())


def _ev(xref, person, depth, weight, reason):
    return {
        "xref": xref,
        "name": person.get("name") or "(unknown)",
        "surname": person.get("surname") or "",
        "gen": person.get("generation"),
        "depth": depth,
        "place": person.get("birth_place") or person.get("christening_place"),
        "reason": reason,
        "weight": weight,
    }


def main():
    ap = argparse.ArgumentParser(description="Explain the immigrant-model 'untraced' weight")
    ap.add_argument("--in", dest="infile", default="output/ancestors.json")
    ap.add_argument("--max-gen", type=int, default=None,
                    help="pull depth (default: inferred as the deepest generation present)")
    ap.add_argument("--top", type=int, default=40, help="how many dead-end ancestors to list")
    args = ap.parse_args()

    if not Path(args.infile).exists():
        sys.exit(f"Not found: {args.infile}. Run parse_gedcom.py first.")
    people = json.loads(Path(args.infile).read_text(encoding="utf-8"))
    by_xref = {p["xref"]: p for p in people}
    roots = [p for p in people if p.get("generation") == 0]
    if not roots:
        sys.exit("No root (generation 0) person found.")
    root_xref = roots[0]["xref"]

    gens_present = [p["generation"] for p in people if p.get("generation") is not None]
    max_gen = args.max_gen if args.max_gen is not None else (max(gens_present) if gens_present else 0)

    events = trace_deadends(by_xref, root_xref)
    total = sum(e["weight"] for e in events)

    print(f"\n=== WHERE THE IMMIGRANT MODEL RUNS OUT OF ROAD: {roots[0]['name']} ===")
    print(f"pull depth (wall) = generation {max_gen}")
    print(f"untraced weight total = {total:.4f}  ({100 * total:.1f}% of you)")

    # ---- weight by generation, with the wall flagged ----
    by_gen = defaultdict(float)
    for e in events:
        by_gen[e["gen"] if e["gen"] is not None else -1] += e["weight"]
    print("\n--- untraced weight by generation of the dead-end ancestor ---")
    print("    (gen = how many generations back the line ends)")
    for g in sorted(by_gen):
        glabel = "unknown gen" if g == -1 else f"gen {g:>2}"
        flag = "  <- PULL WALL (pull deeper to extend)" if g == max_gen else (
            "  <- genuine dead-end" if g >= 1 else "")
        bar = "#" * max(1, round(100 * by_gen[g])) if by_gen[g] > 0.005 else ""
        print(f"  {glabel}  {100 * by_gen[g]:5.1f}%  {bar}{flag}")

    # ---- wall vs genuine split ----
    wall = sum(e["weight"] for e in events if e["gen"] == max_gen)
    genuine = sum(e["weight"] for e in events if e["gen"] is not None and e["gen"] < max_gen)
    unknown = sum(e["weight"] for e in events if e["gen"] is None)
    print("\n--- the headline split ---")
    print(f"  {100 * wall:5.1f}%  hits the gen-{max_gen} PULL WALL  -> likely artificial; a deeper pull may extend these")
    print(f"  {100 * genuine:5.1f}%  GENUINE dead-ends (gen < {max_gen}) -> records truly end; needs research, not a re-pull")
    if unknown > 0.0005:
        print(f"  {100 * unknown:5.1f}%  dead-end ancestor had no generation recorded")

    # ---- reason breakdown ----
    by_reason = defaultdict(float)
    for e in events:
        by_reason[e["reason"]] += e["weight"]
    print("\n--- why lines end (all generations) ---")
    for reason, w in sorted(by_reason.items(), key=lambda kv: -kv[1]):
        print(f"  {100 * w:5.1f}%  {reason}")

    # ---- the genuine dead-ends, aggregated per ancestor (pedigree collapse: an
    #      ancestor on several lines sums), ranked by stranded weight ----
    agg = defaultdict(lambda: {"weight": 0.0, "name": "", "gen": None, "place": None, "reason": ""})
    for e in events:
        if e["gen"] is not None and e["gen"] < max_gen:
            a = agg[e["xref"]]
            a["weight"] += e["weight"]
            a["name"], a["gen"], a["place"], a["reason"] = e["name"], e["gen"], e["place"], e["reason"]
    ranked = sorted(agg.values(), key=lambda a: -a["weight"])
    print(f"\n--- top {args.top} GENUINE dead-end ancestors (records end before the wall) ---")
    print("    gen   % of you  reason            ancestor / last known birthplace")
    for a in ranked[:args.top]:
        place = a["place"] or "(no birthplace recorded)"
        print(f"  gen {a['gen']:>2}  {100 * a['weight']:6.2f}%  {a['reason']:<16}  {a['name']}  --  {place}")
    n_genuine = sum(1 for a in ranked if a["weight"] > 0)
    print(f"\n  {n_genuine} distinct ancestors are genuine dead-ends; "
          f"top {min(args.top, n_genuine)} shown.")

    # ---- likely-origin estimate (historical priors; ALL untraced weight) ----
    est_w = defaultdict(float)
    est_conf = {}
    est_why = {}
    for e in events:
        label, conf, why = likely_origin(e["place"])
        est_w[label] += e["weight"]
        est_conf[label] = conf
        est_why[label] = why
    conf_w = defaultdict(float)
    for label, w in est_w.items():
        conf_w[est_conf[label]] += w
    print(f"\n--- LIKELY origin of the untraced {100 * total:.1f}% "
          f"(historical priors, NOT documented) ---")
    for label, w in sorted(est_w.items(), key=lambda kv: -kv[1]):
        tag = est_conf[label]
        print(f"  {100 * w:5.1f}%  [{tag:^6}] {label}")
        print(f"           why: {est_why[label]}")
    print("  ----")
    for tag in ("high", "medium", "low", "none"):
        if conf_w.get(tag, 0) > 0.0005:
            print(f"  {100 * conf_w[tag]:5.1f}%  total at {tag} confidence")
    print("\n  Read as: of the untraced slice, this much PROBABLY traces to each")
    print("  origin based on which colony the line dead-ends in. Treat 'low' and")
    print("  'none' as hints for research, not conclusions.")

    # ---- machine-readable companion ----
    outdir = Path(args.infile).parent
    (outdir / "deadends.json").write_text(json.dumps({
        "pull_wall_gen": max_gen,
        "untraced_total_pct": round(100 * total, 3),
        "wall_pct": round(100 * wall, 3),
        "genuine_pct": round(100 * genuine, 3),
        "by_generation_pct": {str(g): round(100 * by_gen[g], 3) for g in sorted(by_gen)},
        "by_reason_pct": {r: round(100 * w, 3) for r, w in by_reason.items()},
        "likely_origin_pct": {
            label: {"pct_of_you": round(100 * w, 3),
                    "confidence": est_conf[label], "rationale": est_why[label]}
            for label, w in sorted(est_w.items(), key=lambda kv: -kv[1])},
        "likely_origin_by_confidence_pct": {
            tag: round(100 * conf_w[tag], 3) for tag in conf_w},
        "genuine_deadends": [
            dict({"xref": x, "name": a["name"], "gen": a["gen"],
                  "pct_of_you": round(100 * a["weight"], 4),
                  "reason": a["reason"], "birthplace": a["place"]},
                 **dict(zip(("likely_origin", "confidence"), likely_origin(a["place"])[:2])))
            for x, a in sorted(agg.items(), key=lambda kv: -kv[1]["weight"]) if a["weight"] > 0],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {outdir}/deadends.json")


if __name__ == "__main__":
    main()
