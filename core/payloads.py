"""Pure, JSON-ready analysis payloads for the web API.

These reuse the existing stdlib analysis (:mod:`core.analyze_origins`,
:mod:`core.build_fan_chart`, :mod:`core.trace_deadends`) and assemble the exact
data the old self-contained HTML files baked in at generation time -- but as plain
dicts the API can serialize and the SPA can render. **No HTML is produced here.**

The single input everywhere is ``people`` -- the list produced by
:func:`core.parse_gedcom.build_people` (the stable internal contract).
"""
from collections import defaultdict

from . import analyze_origins as ao
from . import build_fan_chart as fc
from .duplicates import SAME
from . import infer_origin as io
from . import privacy
from . import trace_deadends as td

UNTRACED = "(untraced)"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _root_xref(people):
    for p in people:
        if p.get("generation") == 0:
            return p["xref"]
    return None


def _age_at_death(p):
    by_, dy_ = p.get("birth_year"), p.get("death_year")
    if by_ and dy_ and dy_ >= by_ and (dy_ - by_) <= 120:
        return dy_ - by_
    return None


def _origin_objs(pairs):
    return [{"name": n, "pct": round(p, 2)} for n, p in pairs]


def _colors(imm_pairs, w_pairs, h_pairs):
    """Assign palette colors by nationality, in the immigrant->weighted->headcount
    order the old map used, so the map and fan chart share one palette."""
    nats = ([n for n, _ in imm_pairs] + [n for n, _ in w_pairs]
            + [n for n, _ in h_pairs])
    seen, ordered = set(), []
    for n in nats:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    color_of = {n: ao.PALETTE[i % len(ao.PALETTE)] for i, n in enumerate(ordered)}
    color_of[UNTRACED] = "#a9a9a9"
    return color_of


def _analyze(people):
    """Run the three origin models once and derive the shared color map."""
    root = _root_xref(people)
    by = {p["xref"]: p for p in people}
    imm, imm_unt, imm_tot, imm_cyc, unres_i = ao.immigrant_origins(by, root)
    w, unt, tot, cyc, unres_w = ao.weighted_origins(by, root)
    counts, unres_h, considered, no_bp = ao.headcount_origins(people, root)
    imm_pairs, w_pairs, h_pairs = (ao.pct_pairs(imm, imm_tot),
                                   ao.pct_pairs(w, tot),
                                   ao.pct_pairs(counts, considered))
    return {
        "root": root, "by": by,
        "imm": imm, "imm_tot": imm_tot, "w": w, "tot": tot,
        "imm_pairs": imm_pairs, "w_pairs": w_pairs, "h_pairs": h_pairs,
        "imm_unt_pct": 100.0 * imm_unt / imm_tot if imm_tot else 0.0,
        "w_unt_pct": 100.0 * unt / tot if tot else 0.0,
        "considered": considered, "no_bp": no_bp,
        "cycles": sorted(set(cyc) | set(imm_cyc)),
        "unres_i": unres_i, "unres_w": unres_w, "unres_h": unres_h,
        "color_of": _colors(imm_pairs, w_pairs, h_pairs),
    }


def _meta(people):
    direct = [p for p in people if p.get("on_direct_line")]
    root = next((p for p in people if p.get("generation") == 0), None)
    return {
        "root": root["name"] if root else None,
        "root_xref": root["xref"] if root else None,
        "root_fid": root.get("fs_id") if root else None,
        "n_people": len(people),
        "n_direct": len(direct),
        "max_gen": max((p["generation"] for p in direct
                        if p["generation"] is not None), default=0),
        "n_coords": sum(1 for p in people
                        if ao.valid_coord(p.get("birth_lat"), p.get("birth_lon"))),
        "total_sources": sum(p.get("source_count", 0) for p in people),
        "total_memories": sum(p.get("memory_count", 0) for p in people),
        "living_count": privacy.count_living(people),
    }


def tree_meta(people):
    """Public, cheap tree metadata (no origin-model computation)."""
    return _meta(people)


def _unresolved_ranked(a):
    """Unmapped birthplaces ranked by impact (immigrant weight, then headcount)."""
    rows = {}

    def row(place):
        return rows.setdefault(place, {"count": 0, "imm_pct": 0.0})

    for place, n in a["unres_h"].items():
        row(place)["count"] += n
    if a["imm_tot"]:
        for place, wt in a["unres_i"].items():
            row(place)["imm_pct"] += 100.0 * wt / a["imm_tot"]
    for place in a["unres_w"]:
        row(place)
    ranked = sorted(rows.items(),
                    key=lambda kv: (-kv[1]["imm_pct"], -kv[1]["count"], kv[0]))
    return [{"place": p, "count": r["count"], "immigrant_pct": round(r["imm_pct"], 3)}
            for p, r in ranked]


# ---------------------------------------------------------------------------
# Origins summary (the old origins.json, as an API response)
# ---------------------------------------------------------------------------

def origins_summary(people):
    a = _analyze(people)
    country_data = ao.country_aggregates(
        people, a["root"], a["imm"], a["imm_tot"], a["w"], a["tot"])
    return {
        "meta": _meta(people),
        "models": {
            "immigrant": {"breakdown": _origin_objs(a["imm_pairs"]),
                          "untraced_pct": round(a["imm_unt_pct"], 2)},
            "weighted": {"breakdown": _origin_objs(a["w_pairs"]),
                         "untraced_pct": round(a["w_unt_pct"], 2)},
            "headcount": {"breakdown": _origin_objs(a["h_pairs"]),
                          "considered": a["considered"], "no_birthplace": a["no_bp"]},
        },
        "colors": a["color_of"],
        "country_data": country_data,
        "cycles": a["cycles"],
        "unresolved_places": _unresolved_ranked(a),
    }


# ---------------------------------------------------------------------------
# Map payload (everything the interactive Leaflet map + filters + panels used)
# ---------------------------------------------------------------------------

def map_payload(people):
    a = _analyze(people)
    color_of = dict(a["color_of"])
    root = a["root"]

    direct = {p["xref"]: p for p in people if p.get("on_direct_line")}
    branch_of, gp_of, _root_b = ao.branch_tags(people)
    direct_child = {}
    for c in direct.values():
        if c["xref"] != root and c["xref"] not in branch_of:
            continue
        for par in ao.parent_slots(c):
            if par in direct:
                direct_child[par] = c

    def foreign(P):
        lbl, res, _ = ao.origin_of(P)
        return (res and lbl is not None and lbl not in ao.NEW_WORLD_LABELS), lbl

    immigrant_xref = set()
    immigrant_headcount = defaultdict(int)
    for xref, P in direct.items():
        isf, lbl = foreign(P)
        if not isf:
            continue
        C = direct_child.get(xref)
        if C is not None and not foreign(C)[0]:
            immigrant_xref.add(xref)
            immigrant_headcount[lbl] += 1

    dna_of, y_line, mt_line = ao.dna_lines(people)

    # ---- canonical per-person rows ----------------------------------------
    # ONE row per person (root, direct line, and collaterals alike), carrying
    # every field any view needs. The SPA filters THIS array once and derives the
    # map pins, the selection bars, the insights cards, and the migration flows
    # from the result -- so a single control (now including a generation range)
    # narrows every view at once, with no server round-trip. Coordinates are
    # present-only: a row has lat/lon iff it has a usable birthplace, dlat/dlon
    # iff a usable deathplace (the map's birth/death pin toggle picks which).
    # See web/src/lib/insights.ts for the matching client-side derivations.
    people_rows = []
    for p in people:
        label, resolved, place, via_ai = ao.origin_detail(p)
        nat = label if (label and resolved) else UNTRACED
        xref = p["xref"]
        row = {
            "name": p.get("name") or "?", "nm": (p.get("name") or "").lower(),
            "surname": (p.get("surname") or "").strip(),
            "xref": xref, "fid": p.get("fs_id"),
            "gen": p.get("generation"), "sex": p.get("sex") or "",
            "nat": nat, "iso": ao.NATION_TO_ISO.get(nat, ""),
            "color": color_of.get(nat, "#a9a9a9"),
            "br": branch_of.get(xref, ""), "gp": gp_of.get(xref, ""),
            "dna": dna_of.get(xref, ""),
            "imm": xref in immigrant_xref, "dir": bool(p.get("on_direct_line")),
            "year": p.get("birth_year"), "age": _age_at_death(p),
            "src": p.get("source_count", 0) or 0, "mem": p.get("memory_count", 0) or 0,
        }
        # US state of birth, for the by-state breakdown + filter (only when the
        # resolved birth origin is American, so it stays consistent with the
        # country filter). settlement_of reuses the same birth->christening place
        # and colonial/abbrev parsing the migration Sankey uses; under an American
        # origin it can only return a US state (the Canada branch is unreachable),
        # so it's a US-state-or-None. Present-only to keep the payload lean.
        st = ao.settlement_of(p) if nat == "American (USA)" else None
        if st:
            row["st"] = st
        # Jev's answer for a place the rules couldn't map (resolve_places). `used`
        # = it's what `nat` shows; otherwise it's a display-only guess. Either way
        # the UI marks it as AI-derived, never as a FamilySearch fact.
        ai = p.get("ai_origin")
        if ai and (via_ai or not resolved):   # a rule match makes a stale answer moot
            row["ai"] = {"label": ai["label"], "conf": ai["confidence"], "used": via_ai}
        # Contested parents: FamilySearch holds 2+ parent couples that no date or
        # completeness check separates (core.parents asks Jev to pick; without
        # it the parser's record-ID order stands). Present-only.
        tied = sum(1 for c in p.get("parent_couples") or [] if c.get("tied"))
        if tied > 1:
            row["pc"] = p.get("ai_parents") or {"claims": tied, "prob": None,
                                                 "decided": False, "changed": False}
        # A wife recorded under her husband's name (parse_gedcom.mark_unnamed_wives):
        # the name on record, and whether her birthplace is just his, copied in --
        # then it isn't pinned either, or the map would show his birthplace twice.
        if p.get("wife_of"):
            row["wife"] = {"fs_name": p.get("fs_name") or p.get("name"),
                           "copied": bool(p.get("place_copied"))}
        if ao.valid_coord(p.get("birth_lat"), p.get("birth_lon")) and not p.get("place_copied"):
            row["lat"] = ao.jitter(p["birth_lat"], xref)
            row["lon"] = ao.jitter(p["birth_lon"], xref, 0.016)
            row["place"] = place or p.get("birth_place")
        if ao.valid_coord(p.get("death_lat"), p.get("death_lon")):
            row["dlat"] = ao.jitter(p["death_lat"], xref)
            row["dlon"] = ao.jitter(p["death_lon"], xref, 0.016)
            row["dplace"] = p.get("death_place")
            row["dyear"] = p.get("death_year")
        people_rows.append(row)

    # ---- migration arcs: immigrant birthplace -> first New-World child's ----
    arcs = []
    for xref, P in direct.items():
        if not ao.valid_coord(P.get("birth_lat"), P.get("birth_lon")):
            continue
        plabel, pres, _ = ao.origin_of(P)
        if not (pres and plabel and plabel not in ao.NEW_WORLD_LABELS):
            continue
        C = direct_child.get(xref)
        if not C or not ao.valid_coord(C.get("birth_lat"), C.get("birth_lon")):
            continue
        clabel, cres, _ = ao.origin_of(C)
        child_new_world = (C.get("generation") == 0) or (cres and clabel in ao.NEW_WORLD_LABELS)
        if not child_new_world:
            continue
        arcs.append({
            "from": [ao.jitter(P["birth_lat"], xref), ao.jitter(P["birth_lon"], xref, 0.016)],
            "to": [ao.jitter(C["birth_lat"], C["xref"]), ao.jitter(C["birth_lon"], C["xref"], 0.016)],
            "fn": P["name"], "tn": C["name"], "nat": plabel,
            "color": color_of.get(plabel, "#888"), "year": P.get("birth_year"),
            "br": branch_of.get(xref, ""), "sex": P.get("sex") or "",
            "dna": dna_of.get(xref, ""), "gen": P.get("generation"),
        })

    # ---- per-immigrant rows (a superset of arcs -- no coordinate requirement) -
    # Powers the migration Sankey and the immigration-by-decade insight, both now
    # filter-reactive. `settlement` is the first New-World child's region label.
    immigrants = []
    for xref in immigrant_xref:
        P = direct[xref]
        olbl = ao.origin_of(P)[0]
        child = direct_child.get(xref)
        settle = (ao.settlement_of(child) if child else None) or "(region unknown)"
        immigrants.append({
            "origin": olbl, "settlement": settle, "nat": olbl,
            "color": color_of.get(olbl, "#6b7280"),
            "year": P.get("birth_year"), "gen": P.get("generation"),
            "br": branch_of.get(xref, ""), "sex": P.get("sex") or "",
            "dna": dna_of.get(xref, ""),
            "name": P.get("name") or "?", "xref": xref, "fid": P.get("fs_id"),
        })

    span_years = [r["year"] for r in people_rows if r["year"] is not None]
    yr_lo = min(span_years) if span_years else 1800
    yr_hi = max(span_years) if span_years else 2000
    gens = [r["gen"] for r in people_rows if r["gen"] is not None]

    # nationality tallies for the country dropdown: direct-line ancestors only,
    # matching the "current selection" population the bars summarize.
    nat_counts = defaultdict(int)
    for r in people_rows:
        if r["dir"] and r["gen"] != 0:
            nat_counts[r["nat"]] += 1

    # US-state tallies for the by-state dropdown + breakdown, same direct-line
    # population as nat_counts. A full-tree, unfiltered list so the dropdown's
    # options stay stable as other filters narrow (the breakdown card re-derives
    # the live, filter-reactive numbers client-side from the people array).
    state_counts = defaultdict(int)
    for r in people_rows:
        if r["dir"] and r["gen"] != 0 and r.get("st"):
            state_counts[r["st"]] += 1

    return {
        "meta": _meta(people),
        "colors": color_of,
        "models": {
            "immigrant": {"breakdown": _origin_objs(a["imm_pairs"]),
                          "untraced_pct": round(a["imm_unt_pct"], 2)},
            "weighted": {"breakdown": _origin_objs(a["w_pairs"]),
                         "untraced_pct": round(a["w_unt_pct"], 2)},
            "headcount": {"breakdown": _origin_objs(a["h_pairs"]),
                          "considered": a["considered"]},
        },
        "people": people_rows,
        "arcs": arcs,
        "immigrants": immigrants,
        "ranges": {
            "yr_lo": yr_lo, "yr_hi": yr_hi,
            "dec_lo": (yr_lo // 10) * 10, "dec_hi": (yr_hi // 10) * 10,
            "has_years": bool(span_years),
            "gen_lo": min(gens) if gens else 0, "gen_hi": max(gens) if gens else 0,
            "src_max": max((r["src"] for r in people_rows), default=0),
            "mem_max": max((r["mem"] for r in people_rows), default=0),
        },
        "nat_counts": dict(sorted(nat_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "state_counts": dict(sorted(state_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "immigrant_count": len(immigrant_xref),
        "country_data": ao.country_aggregates(
            people, root, a["imm"], a["imm_tot"], a["w"], a["tot"]),
        "country_details": _country_details(
            people, branch_of, immigrant_xref, direct_child),
        "sankey": _sankey(direct, direct_child, immigrant_xref, color_of),
        "stats": _stats(people, direct, direct_child, immigrant_xref,
                        immigrant_headcount, y_line, mt_line, color_of),
    }


def _country_details(people, branch_of, immigrant_xref, direct_child):
    """Per-ISO3 deep-dive powering the map's country-detail modal.

    Aggregates EVERY ancestor born in each country (resolved nationality -> ISO3),
    UNFILTERED. UK constituents fold into GBR to match the choropleth, but the
    per-nationality split is kept so the modal can lead with it. Built from the
    full ``people`` list (not the map pins), so unmapped ancestors still count
    toward earliest/latest, the per-generation histogram, and top places.

    Returns {iso3: {nats, total, by_gen, earliest, latest, imm, imm_span, settle,
    branch, surnames, places, median_life, life_n}} -- tuple lists for nats/by_gen/
    settle/surnames/places; earliest/latest are objects or null.
    """
    acc = {}

    def blank():
        return {"nats": defaultdict(int), "total": 0, "by_gen": defaultdict(int),
                "earliest": None, "latest": None, "imm": 0, "imm_years": [],
                "settle": defaultdict(int), "branch": {"P": 0, "M": 0},
                "surnames": defaultdict(int), "places": defaultdict(int),
                "lifespans": []}

    for p in people:
        if p.get("generation") == 0:
            continue
        lbl, res, place = ao.origin_of(p)
        if not (lbl and res):
            continue
        iso = ao.NATION_TO_ISO.get(lbl)
        if not iso:
            continue
        d = acc.setdefault(iso, blank())
        d["nats"][lbl] += 1
        d["total"] += 1
        g = p.get("generation")
        if g is not None:
            d["by_gen"][g] += 1
        y = p.get("birth_year")
        if y is not None:
            rec = {"year": y, "gen": g, "name": p.get("name") or "?",
                   "place": place or p.get("birth_place")}
            if d["earliest"] is None or y < d["earliest"]["year"]:
                d["earliest"] = rec
            if d["latest"] is None or y > d["latest"]["year"]:
                d["latest"] = rec
        side = branch_of.get(p["xref"])
        if side in ("P", "M"):
            d["branch"][side] += 1
        sur = (p.get("surname") or "").strip()
        if sur:
            d["surnames"][sur] += 1
        if p.get("birth_place"):
            d["places"][p["birth_place"].strip()] += 1
        a = _age_at_death(p)
        if a is not None:
            d["lifespans"].append(a)
        if p["xref"] in immigrant_xref:
            d["imm"] += 1
            if y is not None:
                d["imm_years"].append(y)
            child = direct_child.get(p["xref"])
            s = ao.settlement_of(child) if child else None
            if s:
                d["settle"][s] += 1

    out = {}
    for iso, d in acc.items():
        if d["total"] <= 0:
            continue
        # Emit [k, v] LISTS (not tuples) so the JSON wire shape and the TS
        # [string, number][] types match the in-memory object exactly.
        def ranked(counter, n=None):
            items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
            return [[k, v] for k, v in (items[:n] if n else items)]

        out[iso] = {
            "nats": ranked(d["nats"]),
            "total": d["total"],
            "by_gen": [[g, c] for g, c in sorted(d["by_gen"].items())],
            "earliest": d["earliest"], "latest": d["latest"],
            "imm": d["imm"],
            "imm_span": ([min(d["imm_years"]), max(d["imm_years"])]
                         if d["imm_years"] else None),
            "settle": ranked(d["settle"], 6),
            "branch": d["branch"],
            "surnames": ranked(d["surnames"], 10),
            "places": ranked(d["places"], 8),
            "median_life": round(_median(d["lifespans"]), 1) if d["lifespans"] else None,
            "life_n": len(d["lifespans"]),
        }
    return out


def _sankey(direct, direct_child, immigrant_xref, color_of):
    """Immigrant origin -> first New-World settlement flows (small ones folded)."""
    raw = defaultdict(int)
    for xref in immigrant_xref:
        olbl, ores, _ = ao.origin_of(direct[xref])
        if not (olbl and ores):
            continue
        child = direct_child.get(xref)
        settle = (ao.settlement_of(child) if child else None) or "(region unknown)"
        raw[(olbl, settle)] += 1
    o_tot, s_tot = defaultdict(int), defaultdict(int)
    for (o, s), c in raw.items():
        o_tot[o] += c
        s_tot[s] += c
    keep_o = {o for o, t in o_tot.items() if t >= 10}
    keep_s = {s for s, t in s_tot.items() if t >= 8 and not s.startswith("(")}
    flows = defaultdict(int)
    for (o, s), c in raw.items():
        oo = o if o in keep_o else "Other origins"
        ss = s if (s.startswith("(") or s in keep_s) else "Other states"
        flows[(oo, ss)] += c
    rows = [{"origin": o, "settlement": s, "count": c,
             "color": color_of.get(o, "#6b7280")}
            for (o, s), c in sorted(flows.items(), key=lambda kv: -kv[1])]
    total = sum(flows.values())
    settled = sum(c for (o, s), c in flows.items() if not s.startswith("("))
    return {"flows": rows, "total": total, "settled": settled}


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    m = n // 2
    return float(s[m]) if n % 2 else (s[m - 1] + s[m]) / 2.0


def _stats(people, direct, direct_child, immigrant_xref, immigrant_headcount,
           y_line, mt_line, color_of):
    """The side-panel analytics: completeness, surnames, pedigree collapse, DNA
    lines, immigration-by-decade, longevity. Pure data, no markup."""
    # pedigree completeness (known vs 2^gen per generation)
    by_gen = defaultdict(int)
    for p in people:
        if p.get("on_direct_line"):
            g = p.get("generation")
            if g is not None and g >= 1:
                by_gen[g] += 1
    completeness = [{"gen": g, "known": by_gen.get(g, 0), "expected": 2 ** g}
                    for g in range(1, (max(by_gen) if by_gen else 0) + 1)]

    # surname distribution (top 12), colored by dominant origin
    sur_count = defaultdict(int)
    sur_origin = defaultdict(lambda: defaultdict(int))
    for p in people:
        if not p.get("on_direct_line") or p.get("generation") == 0:
            continue
        s = (p.get("surname") or "").strip() or "(unknown)"
        sur_count[s] += 1
        lbl, res, _ = ao.origin_of(p)
        if lbl and res:
            sur_origin[s][lbl] += 1
    surnames = []
    for s, c in sorted(sur_count.items(), key=lambda kv: (-kv[1], kv[0]))[:12]:
        doms = sur_origin.get(s)
        dom = max(doms.items(), key=lambda kv: kv[1])[0] if doms else None
        surnames.append({"surname": s, "count": c,
                         "color": color_of.get(dom, "#6b7280")})

    # genuine pedigree collapse vs over-attachment
    collapse_xrefs, collapse_couples, over_attached = ao.pedigree_collapse(people)
    couples = []
    for (fx, mx), n in collapse_couples[:10]:
        F, M = direct.get(fx), direct.get(mx)
        couples.append({
            "father": F.get("name") if F else "?",
            "mother": M.get("name") if M else "?",
            "fa_xref": fx, "fa_fid": (F or {}).get("fs_id"),
            "mo_xref": mx, "mo_fid": (M or {}).get("fs_id"),
            "lines": n, "gen": (F or {}).get("generation"),
        })
    collapse = {"n_collapse": len(collapse_xrefs), "n_over_attached": len(over_attached),
                "couples": couples}

    # direct DNA lines (patrilineal Y, matrilineal mt)
    def dna_line(line):
        rows = []
        for p in line:
            lbl, res, _ = ao.origin_of(p)
            rows.append({
                "name": p.get("name"), "surname": p.get("surname") or "",
                "year": p.get("birth_year"), "gen": p.get("generation"),
                "fid": p.get("fs_id"), "xref": p.get("xref"),
                "nat": lbl if (lbl and res) else None,
                "color": color_of.get(lbl if (lbl and res) else "", "#6b7280"),
            })
        return rows
    y_origin = next((ao.origin_of(p)[0] for p in reversed(y_line)
                     if ao.origin_of(p)[1]), None)
    mt_origin = next((ao.origin_of(p)[0] for p in reversed(mt_line)
                      if ao.origin_of(p)[1]), None)
    dna = {"y_line": dna_line(y_line), "mt_line": dna_line(mt_line),
           "y_origin": y_origin, "mt_origin": mt_origin}

    # immigration by decade (the immigrant set, bucketed by birth decade & origin)
    imm_rows = []
    imm_undated = 0
    dec_nat = defaultdict(lambda: defaultdict(int))
    for xref in immigrant_xref:
        P = direct[xref]
        lbl, res, _ = ao.origin_of(P)
        if not (lbl and res):
            continue
        y = P.get("birth_year")
        if y is None:
            imm_undated += 1
            continue
        dec_nat[(y // 10) * 10][lbl] += 1
    for dec in sorted(dec_nat):
        for nat, c in sorted(dec_nat[dec].items(), key=lambda kv: -kv[1]):
            imm_rows.append({"decade": dec, "nat": nat, "count": c,
                             "color": color_of.get(nat, "#6b7280")})
    immigration = {"by_decade": imm_rows, "undated": imm_undated,
                   "total": len(immigrant_xref)}

    # longevity: median lifespan by birth century and by origin
    life_cent, life_nat = defaultdict(list), defaultdict(list)
    n_life = 0
    for p in people:
        if p.get("generation") == 0:
            continue
        age = _age_at_death(p)
        if age is None:
            continue
        n_life += 1
        by = p.get("birth_year")
        if by:
            life_cent[(by // 100) * 100].append(age)
        lbl, res, _ = ao.origin_of(p)
        if lbl and res:
            life_nat[lbl].append(age)
    longevity = {
        "n": n_life,
        "by_century": [{"label": f"{c}s", "median": round(_median(v), 1), "n": len(v)}
                       for c, v in sorted(life_cent.items()) if len(v) >= 15],
        "by_origin": [{"label": k, "median": round(_median(v), 1), "n": len(v),
                       "color": color_of.get(k, "#4363d8")}
                      for k, v in sorted(life_nat.items(),
                                         key=lambda kv: -_median(kv[1])) if len(v) >= 20],
    }

    return {"completeness": completeness, "surnames": surnames,
            "collapse": collapse, "dna": dna, "immigration": immigration,
            "longevity": longevity}


# ---------------------------------------------------------------------------
# Fan chart payload (radial pedigree, re-rootable in the browser)
# ---------------------------------------------------------------------------

def _place_prior(person, place, by):
    """The place signal for a dead-end's origin estimate: td.likely_origin --
    except for a wife whose birthplace was copied from her husband's record
    (parse_gedcom.mark_unnamed_wives), whose likeliest origin is his documented
    one, since most couples married within their own region. Still an estimate."""
    if person.get("place_copied"):
        label, resolved, _ = ao.origin_of(by.get(person.get("wife_of")) or {})
        if resolved and label:
            return (label, "medium", "recorded under her husband's name with his birthplace "
                    "copied in; most couples married locally, so his origin is likeliest")
    return td.likely_origin(place)


def fan_payload(people):
    a = _analyze(people)
    by_xref = {p["xref"]: p for p in people}
    branch_of, _gp, _root = ao.branch_tags(people)
    dna_of, _y, _mt = ao.dna_lines(people)
    recs = fc.build_records(people, by_xref, a["color_of"], branch_of, dna_of)

    # Attach an ESTIMATED origin to the wedges where the trail goes cold: a record
    # is a dead-end (no parent present in the fan) whose own birthplace doesn't
    # resolve to a documented old-world origin. Those are exactly the rim wedges a
    # user wonders about; documented ancestors keep their sourced nationality and
    # get no guess. Same reconciled estimate the dead-ends card uses (place +
    # surname + relatives), so the two views never disagree.
    surname_idx = io.build_surname_index(people)
    for xref, rec in recs.items():
        if (rec.get("fa") and rec["fa"] in recs) or (rec.get("mo") and rec["mo"] in recs):
            continue  # has a parent in the fan -> not a dead-end; follow the line
        person = by_xref.get(xref) or {}
        label, resolved, _ = ao.origin_of(person)
        if resolved and label is not None and label not in ao.NEW_WORLD_LABELS:
            continue  # origin is documented -> no guess needed
        place = _place_prior(person, person.get("birth_place") or person.get("christening_place"),
                             by_xref)
        sur = io.surname_origin(person.get("surname"))
        tree = io.tree_surname_origin(person.get("surname"), surname_idx)
        est = io.combine_origin(place, sur, tree)
        if est["confidence"] != "none":
            rec["est"] = est

    return {
        "meta": _meta(people),
        "root": a["root"],
        "colors": a["color_of"],
        "recs": recs,
    }


# ---------------------------------------------------------------------------
# Dead-ends payload (where the immigrant model runs out of road)
# ---------------------------------------------------------------------------

def deadends_payload(people, max_gen=None, top=40):
    by = {p["xref"]: p for p in people}
    root = _root_xref(people)
    gens = [p["generation"] for p in people if p.get("generation") is not None]
    wall = max_gen if max_gen is not None else (max(gens) if gens else 0)

    events = td.trace_deadends(by, root)
    total = sum(e["weight"] for e in events)

    by_reason = defaultdict(float)
    by_gen = defaultdict(float)
    for e in events:
        by_reason[e["reason"]] += e["weight"]
        by_gen[e["gen"] if e["gen"] is not None else -1] += e["weight"]

    # genuine dead-ends (shallower than the pull wall), aggregated per ancestor
    agg = {}
    for e in events:
        if e["gen"] is not None and e["gen"] < wall:
            a = agg.setdefault(e["xref"], {"weight": 0.0, "name": e["name"],
                                           "xref": e["xref"], "gen": e["gen"],
                                           "place": e["place"], "reason": e["reason"]})
            a["weight"] += e["weight"]
    ranked = sorted(agg.values(), key=lambda r: -r["weight"])[:top]

    # Likely-origin ESTIMATES (historical settlement priors from trace_deadends --
    # which colony a line dead-ends in hints at the undocumented immigrant's origin).
    # These are NOT documented facts, so each carries a confidence + one-line
    # rationale and the SPA marks them unmistakably as guesses (see StatsPanel). We
    # ship a per-ancestor guess AND an aggregate over ALL untraced weight, mirroring
    # the CLI's deadends.json (the prior implementation that never reached the web).
    # Per dead-end we run THREE independent estimators -- place priors (Phase 0),
    # surname etymology (Phase 1), and same-surname relatives documented in the
    # tree (Phase 2) -- then reconcile them into one verdict (Phase 3,
    # `origin_estimate`). The individual signals stay on the row too: they are the
    # verdict's "why". The surname index is built once from the whole tree.
    surname_idx = io.build_surname_index(people)

    def _estimate(r):
        surname = (by.get(r["xref"]) or {}).get("surname")
        place = _place_prior(by.get(r["xref"]) or {}, r["place"], by)
        sur = io.surname_origin(surname)
        tree = io.tree_surname_origin(surname, surname_idx)
        return {
            "likely_origin": place[0], "confidence": place[1], "rationale": place[2],
            "surname_origin": sur[0], "surname_confidence": sur[1], "surname_rationale": sur[2],
            "tree_origin": tree[0], "tree_confidence": tree[1], "tree_rationale": tree[2],
            "origin_estimate": io.combine_origin(place, sur, tree),
        }

    est_w, est_conf, est_why = defaultdict(float), {}, {}
    for e in events:
        label, conf, why = _place_prior(by.get(e["xref"]) or {}, e["place"], by)
        est_w[label] += e["weight"]
        est_conf[label], est_why[label] = conf, why
    conf_w = defaultdict(float)
    for label, w in est_w.items():
        conf_w[est_conf[label]] += w

    return {
        "meta": _meta(people),
        "wall_generation": wall,
        "untraced_pct": round(100.0 * total, 2),
        "wall_pct": round(100.0 * sum(e["weight"] for e in events if e["gen"] == wall), 2),
        "genuine_pct": round(100.0 * sum(
            e["weight"] for e in events if e["gen"] is not None and e["gen"] < wall), 2),
        "by_reason": {k: round(100.0 * v, 2) for k, v in
                      sorted(by_reason.items(), key=lambda kv: -kv[1])},
        "by_generation": {(str(g) if g != -1 else "unknown"): round(100.0 * w, 2)
                          for g, w in sorted(by_gen.items())},
        "top_genuine": [{"name": r["name"], "xref": r["xref"],
                         "fid": (by.get(r["xref"]) or {}).get("fs_id"),
                         "gen": r["gen"], "place": r["place"],
                         "reason": r["reason"], "pct": round(100.0 * r["weight"], 3),
                         **_estimate(r)}
                        for r in ranked],
        # ESTIMATED origins of the untraced slice -- not from the user's tree.
        "likely_origin": [
            {"label": label, "pct": round(100.0 * w, 2),
             "confidence": est_conf[label], "rationale": est_why[label]}
            for label, w in sorted(est_w.items(), key=lambda kv: -kv[1])],
        "likely_origin_by_confidence": {
            tag: round(100.0 * w, 2)
            for tag, w in sorted(conf_w.items(), key=lambda kv: -kv[1])},
    }


# ---------------------------------------------------------------------------
# Possible duplicate records (core.duplicates attaches `ai_dups` via Jev)
# ---------------------------------------------------------------------------

def duplicates_payload(people, top=100):
    """Review list of records FamilySearch likely holds twice. `same` groups
    records linked by a likely-same verdict (one person entered 2+ times);
    `possible` lists weaker single pairs. Closest generations first -- those
    are the ones worth fixing. AI judgments, never merged here."""
    by = {p["xref"]: p for p in people}
    pairs = {}
    for p in people:
        for d in p.get("ai_dups") or []:
            if d["xref"] in by:
                pairs.setdefault(frozenset((p["xref"], d["xref"])), d)

    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    for key, d in pairs.items():
        if d["score"] >= SAME:
            a, b = sorted(key)
            parent[find(b)] = find(a)

    def ref(x):
        p = by[x]
        return {"name": p.get("name") or "?", "xref": x, "fid": p.get("fs_id"),
                "year": p.get("birth_year"), "gen": p.get("generation"),
                "place": p.get("birth_place")}

    groups, possible = defaultdict(lambda: {"score": 0.0, "shared_child": False}), []
    for key, d in pairs.items():
        a, b = sorted(key)
        if d["score"] >= SAME:
            g = groups[find(a)]
            g["score"] = max(g["score"], d["score"])
            g["shared_child"] = g["shared_child"] or d["shared_child"]
        elif find(a) != find(b):          # skip pairs already inside one group
            possible.append({"score": d["score"], "shared_child": d["shared_child"],
                             "parents": d["parents"], "place": d["place"],
                             "records": [ref(a), ref(b)]})
    members = defaultdict(list)
    for x in {x for key in pairs for x in key}:
        if find(x) in groups:
            members[find(x)].append(x)
    same = [{**g, "records": sorted((ref(x) for x in members[root]), key=lambda r: r["fid"] or "")}
            for root, g in groups.items()]

    gen = lambda row: min((r["gen"] for r in row["records"] if r["gen"] is not None), default=999)
    same.sort(key=lambda g: (gen(g), -g["score"]))
    possible.sort(key=lambda r: (gen(r), -r["score"]))
    return {"n_same": len(same), "n_same_records": sum(len(g["records"]) for g in same),
            "n_possible": len(possible), "same": same[:top], "possible": possible[:top]}
