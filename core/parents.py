"""
parents.py -- let Jev settle parent conflicts the dates can't.

    python settle_parents.py --in output/ancestors.json            # decide + annotate
    python settle_parents.py --in output/ancestors.json --eval 200 # real couple vs decoy

When a child has 2+ parent couples that survive every code check (parse_gedcom
marks them `tied`), the parser falls back to FID order -- arbitrary. Jev reads
what code can't: naming customs (Mads Erichsen is Erik's son), whether the
places fit together, how the ages sit. Each conflict is asked twice with the
couples in reverse order and the probabilities averaged, since option order can
sway Jev.

If the winning couple's averaged probability reaches ACT, it becomes the
preferred couple (parent_xrefs / father_xref / mother_xref / pedigree
re-pointed); otherwise the parser's choice stands. Either way the child gets
`ai_parents` {claims, prob, decided, changed} so the UI can say the parents were
picked by AI or are contested. FamilySearch facts are never edited -- only which
of its claims we follow. Living people are never sent.
"""

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .analyze_origins import _fold
from .duplicates import _year
from .jev import Jev, ask_all
from .parse_gedcom import impossible_parent
from .privacy import ai_name, is_likely_living

# From --eval on the real tree (2026-09-25), real couple vs same-surname decoy:
# p >= 0.9 -> 95.6% right (68 trials); 0.8-0.9 -> 74%; below -> ~62%. Danish
# patronymic children vs a Danish decoy: p >= 0.9 -> 100% (45). Below the bar the
# parser's pick stands and the child shows as contested.
ACT = 0.9
UNCLEAR = "unclear"
INSTRUCTIONS = (
    "A family tree has several parent couples claimed for this child. Which couple "
    "is most likely the child's real parents? Weigh naming customs (a Scandinavian "
    "son named Pedersen or Petersson is the son of a Peder; a daughter Nielsdatter "
    "is the daughter of a Niels; English children usually carry the father's "
    "surname), whether the parents' places fit the child's, and the ages given.")


def _who(p):
    if p is None or is_likely_living(p):
        return "not recorded"
    return {"name": ai_name(p), "born": _year(p.get("birth_year")),
            "birthplace": (None if p.get("place_copied") else p.get("birth_place")) or "unknown",
            "died": _year(p.get("death_year"))}


def _couple(c, by, child_year):
    f, m = by.get(c["father_xref"]), by.get(c["mother_xref"])
    ages = []
    for role, p in (("father", f), ("mother", m)):
        if (p and not is_likely_living(p) and child_year is not None
                and p.get("birth_year") is not None):
            ages.append("%s aged %d at the birth" % (role, child_year - p["birth_year"]))
    return {"father": _who(f), "mother": _who(m), "ages": "; ".join(ages) or "unknown"}


def ask_couples(jev, child, couples, by):
    """Averaged P(real parents) per couple (aligned with `couples`), asked in
    forward and reverse order. Returns (probs, p_unclear)."""
    labels = ["couple_" + chr(65 + i) for i in range(len(couples))]
    q = {"parents": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": {
        **{lab: "the parents described in " + lab for lab in labels},
        UNCLEAR: "the records don't favour any couple"}}}
    probs, unclear = [0.0] * len(couples), 0.0
    for order in (list(range(len(couples))), list(range(len(couples)))[::-1]):
        state = {"child": {"name": ai_name(child), "sex": child.get("sex") or "?",
                           "born": _year(child.get("birth_year")),
                           "birthplace": (None if child.get("place_copied")
                                          else child.get("birth_place")) or "unknown"}}
        for lab, i in zip(labels, order):
            state[lab] = _couple(couples[i], by, child.get("birth_year"))
        got = jev.ask(state, q)["parents"]["probabilities"]
        for lab, i in zip(labels, order):
            probs[i] += got.get(lab, 0.0) / 2
        unclear += got.get(UNCLEAR, 0.0) / 2
    return probs, unclear


def contested(people):
    """(child, its tied couple records) for every child whose parents the
    parser chose by FID order alone. Living children are left alone."""
    out = []
    for p in people:
        tied = [c for c in p.get("parent_couples") or [] if c.get("tied")]
        if len(tied) > 1 and not is_likely_living(p):
            out.append((p, tied))
    return out


def _repoint(p, c):
    """Make couple record `c` the child's preferred couple, as the parser would."""
    for x in p["parent_couples"]:
        x["preferred"] = x is c
    pair = [x for x in (c["father_xref"], c["mother_xref"]) if x]
    p["parent_xrefs"] = pair + [x for x in p.get("parent_xrefs") or [] if x not in pair]
    p["father_xref"], p["mother_xref"] = c["father_xref"], c["mother_xref"]
    p["pedigree"] = c["pedigree"]


def settle(people, jev, workers=8):
    """Ask Jev about every contested child; re-point the confident ones. Safe to
    re-run: the parser's own pick is remembered (`parse_pick`) and restored when
    Jev isn't confident."""
    by = {p["xref"]: p for p in people}
    items = contested(people)
    answers = ask_all(jev, lambda it: ask_couples(jev, it[0], it[1], by), items, workers)
    tally = Counter()
    for (p, cs), (probs, _) in zip(items, answers):
        base = next((c for c in cs if c.get("parse_pick")), None) or next(c for c in cs if c["preferred"])
        base["parse_pick"] = True
        win = max(range(len(cs)), key=lambda i: probs[i])
        decided = probs[win] >= ACT
        target = cs[win] if decided else base
        if not target["preferred"]:
            _repoint(p, target)
        p["ai_parents"] = {"claims": len(cs), "prob": round(probs[win], 3),
                           "decided": decided, "changed": target is not base}
        tally["changed" if target is not base else "kept" if decided else "contested"] += 1
    return tally


def _surname(p):
    return re.sub(r"[^a-z]", "", _fold((p or {}).get("surname") or ""))


def evaluate(people, jev, n, workers):
    """Children with one undisputed, complete couple: pit the real couple against
    a decoy -- another couple whose father shares the real father's surname and
    era, and whose ages fit the child -- asked in both orders. Accuracy by the
    winner's probability tells us where ACT can sit. Decoys are easier than the
    real conflicts (those are often near-duplicates), so read it as an upper bound."""
    by = {p["xref"]: p for p in people}
    couples = {}
    for p in people:
        for c in p.get("parent_couples") or []:
            f, m = by.get(c["father_xref"]), by.get(c["mother_xref"])
            if f and m and f.get("birth_year") is not None and m.get("birth_year") is not None:
                couples[(c["father_xref"], c["mother_xref"])] = c
    by_surname = defaultdict(list)
    for c in couples.values():
        by_surname[_surname(by[c["father_xref"]])].append(c)

    rng = random.Random(0)
    kids = [p for p in people if len(p.get("parent_couples") or []) == 1
            and (p["parent_couples"][0]["father_xref"], p["parent_couples"][0]["mother_xref"]) in couples
            and p.get("birth_year") is not None and not is_likely_living(p)]
    trials = []
    for p in rng.sample(kids, len(kids)):
        real = p["parent_couples"][0]
        fy = by[real["father_xref"]]["birth_year"]

        def fits(c):
            f, m = by[c["father_xref"]], by[c["mother_xref"]]
            return (c is not real and c["father_fid"] != real["father_fid"]
                    and abs(f["birth_year"] - fy) <= 25
                    and not impossible_parent(p["birth_year"], f["birth_year"], f.get("death_year"), False)
                    and not impossible_parent(p["birth_year"], m["birth_year"], m.get("death_year"), True))

        pool = [c for c in by_surname[_surname(by[real["father_xref"]])] if fits(c)]
        if pool:
            trials.append((p, real, rng.choice(pool)))
        if len(trials) >= n:
            break

    res = ask_all(jev, lambda t: ask_couples(jev, t[0], [t[1], t[2]], by), trials, workers)
    bands = [(0.9, "p >= 0.9"), (0.8, "0.8-0.9"), (0.7, "0.7-0.8"), (0.0, "< 0.7")]
    total, right = Counter(), Counter()
    patro_total = patro_right = 0
    for (p, _, _), (probs, _) in zip(trials, res):
        top = max(probs)
        b = next(name for lo, name in bands if top >= lo)
        ok = probs[0] > probs[1]
        total[b] += 1
        right[b] += ok
        if re.search(r"(sen|son|datter|dotter)$", _surname(p)):
            patro_total += 1
            patro_right += ok
    print("\nEVAL: real couple vs same-surname decoy, %d children" % len(trials))
    print("  overall: %.1f%% pick the real couple" % (100 * sum(right.values()) / len(trials)))
    for _, b in bands:
        if total[b]:
            print("  %-9s %4d trials, %.1f%% correct" % (b, total[b], 100 * right[b] / total[b]))
    if patro_total:
        print("  patronymic children: %d trials, %.1f%% correct" % (patro_total, 100 * patro_right / patro_total))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--in", dest="inp", default="output/ancestors.json")
    ap.add_argument("--cache", default="output/jev_cache.json")
    ap.add_argument("--eval", type=int, metavar="N", help="real-vs-decoy check on N children")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    people = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    jev = Jev(args.cache)
    if args.eval:
        evaluate(people, jev, args.eval, args.workers)
        print("cost this run: $%.4f" % jev.cost)
        return
    tally = settle(people, jev, args.workers)
    Path(args.inp).write_text(json.dumps(people, indent=2, ensure_ascii=False), encoding="utf-8")
    print("%d contested children: %d re-pointed by Jev, %d confirmed the parser's pick, "
          "%d left contested (below %.2f)" % (sum(tally.values()), tally["changed"],
                                              tally["kept"], tally["contested"], ACT))
    print("Wrote %s   cost this run: $%.4f" % (args.inp, jev.cost))


if __name__ == "__main__":
    sys.exit(main())
