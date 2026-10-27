"""
resolve_places.py -- ask Jev which present-day country a birthplace is in, for
the places the keyword rules (analyze_origins.infer_nationality) can't map.

    python resolve_places.py --in output/ancestors.json            # enrich in place
    python resolve_places.py --in output/ancestors.json --eval 300 # score Jev on mapped ones

Enriching adds `ai_origin: {label, confidence}` to each person whose place got a
specific-country answer (>= 0.5), rewrites the --in file, and writes a per-place
report to output/place_guesses.json. FamilySearch facts are never touched;
origin_of counts an ai_origin only at >= AI_ACCEPT, and the UI marks it as
AI-mapped. Living people's places are never sent. --eval asks the same question
about places the rules DO map and reports agreement by confidence band.
"""

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import analyze_origins as ao
from .jev import Jev, ask_all
from .privacy import is_likely_living

VAGUE, OTHER, NOT_PLACE = "too vague", "other country", "not a place"
MIN_KEEP = 0.5   # below this an answer isn't even worth showing as a guess

QUESTIONS = {"country": {
    "type": "choice",
    "instructions": (
        "Which present-day country is this birthplace in? Options are named by "
        "nationality ('English' = England, 'Dutch' = the Netherlands). The place may "
        "be written in any language or use a historical name; answer with the "
        "present-day country that contains it."),
    "criteria": {
        **{label: "a place in present-day %s territory" % label
           for label in sorted(ao.NATION_TO_ISO)},
        VAGUE: "only a continent, empire or broad region spanning several present-day "
               "countries (e.g. 'Europe', 'Roman Empire', 'Middle East')",
        OTHER: "a specific real place in a present-day country not among the options",
        NOT_PLACE: "not a geographic location ('?', a ship at sea, a mythical land)",
    },
}}


def guess(jev, place):
    a = jev.ask({"birthplace": place}, QUESTIONS)["country"]
    top = sorted(a["probabilities"].items(), key=lambda kv: -kv[1])[:3]
    return {"label": a["choice"], "confidence": round(a["confidence"], 3),
            "top": [[k, round(v, 3)] for k, v in top]}


def band(conf):
    return "high (>=0.9)" if conf >= 0.9 else "medium (0.5-0.9)" if conf >= 0.5 else "low (<0.5)"


def _rule_origin(p):
    """origin_of by the keyword rules alone -- ignoring any earlier ai_origin, so
    a re-run re-asks the same places and --eval never grades Jev against itself."""
    return ao.origin_of({k: p.get(k) for k in ("birth_place", "christening_place")})


def places_by_status(people):
    """Distinct birthplace strings (birth, else christening) -> (rule label,
    resolved, people count), exactly as the origin models see them."""
    out = {}
    for p in people:
        if is_likely_living(p) or p.get("place_copied"):
            continue
        label, resolved, place = _rule_origin(p)
        if place:
            n = out.get(place, (label, resolved, 0))[2]
            out[place] = (label, resolved, n + 1)
    return out


def enrich(people, jev, workers=8):
    """Attach ai_origin to people whose rule-unmapped place Jev can place.
    Returns {place: guess} for every place asked about."""
    todo = {}
    for p in people:
        p.pop("ai_origin", None)
        _, resolved, place = _rule_origin(p)
        # a birthplace copied from her husband's record isn't hers to map
        if place and not resolved and not is_likely_living(p) and not p.get("place_copied"):
            todo.setdefault(place, []).append(p)
    guesses = run_all(jev, sorted(todo, key=lambda pl: -len(todo[pl])), workers)
    for place, g in guesses.items():
        g["people"] = len(todo[place])
        if g["label"] not in (VAGUE, OTHER, NOT_PLACE) and g["confidence"] >= MIN_KEEP:
            for p in todo[place]:
                p["ai_origin"] = {"label": g["label"], "confidence": g["confidence"]}
    return guesses


def run_all(jev, places, workers):
    """{place: guess} for every place, asked in parallel."""
    return dict(ask_all(jev, lambda pl: (pl, guess(jev, pl)), places, workers))


def evaluate(jev, status, n, workers):
    """Ask about places the rules resolve, stratified by label, and compare."""
    by_label = defaultdict(list)
    for pl, (label, resolved, _) in status.items():
        if resolved:
            by_label[label].append(pl)
    if not by_label:
        print("No eligible rule-mapped places to evaluate.")
        return
    rng = random.Random(0)
    per = max(1, n // len(by_label))
    sample = [pl for lab in sorted(by_label)
              for pl in rng.sample(sorted(by_label[lab]), min(per, len(by_label[lab])))]
    res = run_all(jev, sample, workers)
    agree, total, misses = Counter(), Counter(), []
    for pl, g in res.items():
        b = band(g["confidence"])
        total[b] += 1
        if g["label"] == status[pl][0]:
            agree[b] += 1
        else:
            misses.append((g["confidence"], pl, status[pl][0], g["label"]))
    print("\nEVAL: %d places the rules map, %d labels" % (len(res), len(by_label)))
    print("  overall agreement %.1f%%" % (100 * sum(agree.values()) / len(res)))
    for b in ("high (>=0.9)", "medium (0.5-0.9)", "low (<0.5)"):
        if total[b]:
            print("  %-17s %4d places, %.1f%% agree" % (b, total[b], 100 * agree[b] / total[b]))
    print("  disagreements (confidence, place, rules, jev):")
    for m in sorted(misses, reverse=True)[:25]:
        print("   %.2f  %-55s rules=%-22s jev=%s" % (m[0], m[1][:55], m[2], m[3]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--in", dest="inp", default="output/ancestors.json")
    ap.add_argument("--out", default="output/place_guesses.json")
    ap.add_argument("--cache", default="output/jev_cache.json")
    ap.add_argument("--eval", type=int, metavar="N", help="score Jev on ~N rule-mapped places")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    people = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    jev = Jev(args.cache)

    if args.eval:
        evaluate(jev, places_by_status(people), args.eval, args.workers)
        print("\ncost this run: $%.4f" % jev.cost)
        return

    res = enrich(people, jev, args.workers)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(args.inp).write_text(json.dumps(people, indent=2, ensure_ascii=False), encoding="utf-8")

    ppl, bands = Counter(), Counter()
    for g in res.values():
        ppl[g["label"]] += g["people"]
        bands[band(g["confidence"])] += g["people"]
    counted = sum(1 for p in people if p.get("ai_origin", {}).get("confidence", 0) >= ao.AI_ACCEPT)
    print("%d unmapped places asked (%d people)" % (len(res), sum(bands.values())))
    print("People by answer:", dict(ppl.most_common(25)))
    print("People by confidence:", dict(bands))
    print("%d people now counted via ai_origin (>= %.2f)" % (counted, ao.AI_ACCEPT))
    print("Wrote %s and %s   cost this run: $%.4f" % (args.inp, args.out, jev.cost))


if __name__ == "__main__":
    sys.exit(main())
