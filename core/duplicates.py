"""
duplicates.py -- find people FamilySearch holds twice (two IDs, one person).

    python find_duplicates.py --in output/ancestors.json           # score + annotate
    python find_duplicates.py --in output/ancestors.json --eval 60 # order-swap check

Code proposes candidates: records sharing a normalized first given name, surname
and birth year (and not a different sex). Jev scores each pair on an ordered
scale -- different / possibly the same / the same person -- plus two yes/no
companions (same parents? same birthplace?, allowing spelling variants) that
explain the verdict. A child claiming both records as parents is a hard fact and
comes from code, not the model.

Pairs scoring >= POSSIBLE land on both records as `ai_dups` [{xref, score,
parents, place, shared_child}]; duplicates_payload turns them into a review list
with FamilySearch links. Nothing is merged here -- the fix belongs on
FamilySearch, where the user can merge the two records. Living people are never
candidates, and a living child's name is never sent.
"""

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from .analyze_origins import _fold
from .jev import Jev, ask_all
from .privacy import ai_name, is_likely_living

POSSIBLE = 0.5      # nearest level >= 1 ("possibly the same")
SAME = 1.5          # nearest level 2 ("the same person")
MAX_BLOCK = 6       # a big name/year block (common names) caps at 15 pairs

QUESTIONS = {
    "same": {
        "type": "score",
        "instructions": "Do record_a and record_b describe the same person?",
        "criteria": [
            "two different people",
            "possibly the same person: the records conflict or are too thin to tell",
            "the same person recorded twice",
        ],
    },
    "parents": {
        "type": "noul",
        "instructions": "Do record_a and record_b name the same parents, allowing for "
                        "spelling variants? Answer no if either record's parents are unknown.",
    },
    "place": {
        "type": "noul",
        "instructions": "Do record_a and record_b give the same birthplace, allowing for "
                        "spelling variants and more or less detail? Answer no if either "
                        "birthplace is unknown.",
    },
}


def _norm(s):
    return re.sub(r"[^a-z ]", "", _fold(s or "")).strip()


def _year(y):
    return "unknown" if y is None else ("%d BC" % -y if y < 0 else "%d AD" % y)


def candidates(people):
    """Candidate pairs (a, b): same first given name, surname and birth year,
    distinct FamilySearch IDs, not a different recorded sex, not a couple, neither
    living. The sex and couple checks matter: old records often name a wife after
    her husband ("Mrs. Charles Baker" -> a female "Charles Baker" in the mother
    slot) -- a real, unnamed person, not a duplicate."""
    couples = {frozenset((c["father_xref"], c["mother_xref"]))
               for p in people for c in p.get("parent_couples") or []
               if c["father_xref"] and c["mother_xref"]}
    blocks = defaultdict(list)
    for p in people:
        given = _norm(p.get("given")).split()
        surname = _norm(p.get("surname"))
        if given and surname and p.get("birth_year") is not None and not is_likely_living(p):
            blocks[(given[0], surname, p["birth_year"])].append(p)
    pairs = []
    for block in blocks.values():
        block = block[:MAX_BLOCK]
        for i, a in enumerate(block):
            for b in block[i + 1:]:
                sexes = {a.get("sex"), b.get("sex")} - {None, "", "U"}
                if (a.get("fs_id") != b.get("fs_id") and len(sexes) < 2
                        and frozenset((a["xref"], b["xref"])) not in couples):
                    pairs.append((a, b))
    return pairs


def _record(p, by, kids):
    name = lambda x: ai_name(by.get(x))
    return {
        "name": ai_name(p),
        "born": _year(p.get("birth_year")),
        "birthplace": (None if p.get("place_copied") else p.get("birth_place")) or "unknown",
        "died": _year(p.get("death_year")),
        "deathplace": p.get("death_place") or "unknown",
        "father": name(p.get("father_xref")),
        "mother": name(p.get("mother_xref")),
        "children": [ai_name(by[c]) for c in kids.get(p["xref"], [])[:4]
                     if not is_likely_living(by[c])],
    }


def score_pairs(people, jev, pairs, workers=8, swap=False):
    """Ask Jev about each pair; returns [{a, b, score, parents, place, shared_child}]."""
    by = {p["xref"]: p for p in people}
    kids = defaultdict(list)
    for c in people:
        for par in c.get("parent_xrefs") or []:
            kids[par].append(c["xref"])

    def one(pair):
        a, b = pair
        ra, rb = _record(a, by, kids), _record(b, by, kids)
        if swap:
            ra, rb = rb, ra
        ans = jev.ask({"record_a": ra, "record_b": rb}, QUESTIONS)
        return {"a": a["xref"], "b": b["xref"],
                "score": round(ans["same"]["score"], 3),
                "parents": round(ans["parents"]["noul"], 2),
                "place": round(ans["place"]["noul"], 2),
                "shared_child": bool(set(kids[a["xref"]]) & set(kids[b["xref"]]))}

    return ask_all(jev, one, pairs, workers)


def find_duplicates(people, jev, workers=8):
    """Score every candidate pair -- asked in both record orders and averaged,
    since Jev's verdict can lean on which record comes first -- and attach
    `ai_dups` to both records of each pair scoring >= POSSIBLE. Returns all
    scored pairs."""
    for p in people:
        p.pop("ai_dups", None)
    pairs = candidates(people)
    results = score_pairs(people, jev, pairs, workers)
    for r, s in zip(results, score_pairs(people, jev, pairs, workers, swap=True)):
        for k in ("score", "parents", "place"):
            r[k] = round((r[k] + s[k]) / 2, 3)
    by = {p["xref"]: p for p in people}
    for r in results:
        if r["score"] >= POSSIBLE:
            for me, other in ((r["a"], r["b"]), (r["b"], r["a"])):
                by[me].setdefault("ai_dups", []).append({
                    "xref": other, "score": r["score"], "parents": r["parents"],
                    "place": r["place"], "shared_child": r["shared_child"]})
    return results


def evaluate(people, jev, n, workers):
    """Order-swap consistency: ask each sampled pair as (a, b) and as (b, a).
    A verdict that flips with record order isn't one to act on."""
    pairs = candidates(people)
    sample = random.Random(0).sample(pairs, min(n, len(pairs)))
    fwd = score_pairs(people, jev, sample, workers)
    rev = score_pairs(people, jev, sample, workers, swap=True)
    level = lambda s: min(int(s + 0.5), 2)
    same = sum(level(f["score"]) == level(r["score"]) for f, r in zip(fwd, rev))
    gap = sum(abs(f["score"] - r["score"]) for f, r in zip(fwd, rev)) / len(fwd)
    print("\nEVAL (order swap) on %d of %d candidate pairs:" % (len(fwd), len(pairs)))
    print("  same verdict level both ways: %.1f%%" % (100 * same / len(fwd)))
    print("  mean score shift: %.3f (scale 0-2)" % gap)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--in", dest="inp", default="output/ancestors.json")
    ap.add_argument("--out", default="output/duplicates.json")
    ap.add_argument("--cache", default="output/jev_cache.json")
    ap.add_argument("--eval", type=int, metavar="N", help="order-swap check on N pairs")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    people = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    jev = Jev(args.cache)
    if args.eval:
        evaluate(people, jev, args.eval, args.workers)
        print("cost this run: $%.4f" % jev.cost)
        return

    res = find_duplicates(people, jev, args.workers)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(args.inp).write_text(json.dumps(people, indent=2, ensure_ascii=False), encoding="utf-8")
    same = sum(r["score"] >= SAME for r in res)
    maybe = sum(POSSIBLE <= r["score"] < SAME for r in res)
    print("%d candidate pairs: %d likely the same person, %d possibly, %d different"
          % (len(res), same, maybe, len(res) - same - maybe))
    print("Wrote %s and %s   cost this run: $%.4f" % (args.inp, args.out, jev.cost))


if __name__ == "__main__":
    sys.exit(main())
