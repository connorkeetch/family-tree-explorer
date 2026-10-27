"""One-off migration: re-sign BC birth/death years in stored trees.

Background: extract_year used to drop the era marker, so "5626 BC" was stored as
+5626 and the birth-year filter spanned 1..5626 (the BC line folded onto the AD
axis). parse_gedcom.extract_year now signs BC negative and nulls impossible
future years. Trees parsed before that fix still hold the old positive values --
this re-derives birth_year/death_year in place from each person's stored *_date
using the SAME fixed function (no logic duplication) and recomputes tree meta, so
the slider reads e.g. "5626 BC .. 1992" without anyone re-uploading a GEDCOM.

Idempotent: a second run reports zero changes. Dry-run by default; pass --apply
to write. Scope with --tree-id / --owner-id, else every tree is processed.

Run (prod):  DATABASE_URL=<postgres-url> python -m api.migrate_bc_years --apply
Preview:     DATABASE_URL=<postgres-url> python -m api.migrate_bc_years
"""
import argparse

import core
from core.parse_gedcom import extract_year

from .db import SessionLocal
from .models import Tree


def resign_people(people):
    """Re-derive birth_year/death_year from the stored dates.

    Returns (new_people, n_birth_changed, n_death_changed). Only the two year
    fields are rewritten; every person dict is shallow-copied into a fresh list
    so SQLAlchemy's JSON column sees the change on reassignment.
    """
    nb = nd = 0
    out = []
    for p in people:
        q = dict(p)
        by = extract_year(p.get("birth_date"))
        dy = extract_year(p.get("death_date"))
        if by != p.get("birth_year"):
            q["birth_year"] = by
            nb += 1
        if dy != p.get("death_year"):
            q["death_year"] = dy
            nd += 1
        out.append(q)
    return out, nb, nd


def _span(people):
    ys = [p.get("birth_year") for p in people if p.get("birth_year") is not None]
    return (min(ys), max(ys)) if ys else (None, None)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Re-sign BC years in stored trees.")
    ap.add_argument("--apply", action="store_true",
                    help="write changes (default: dry-run preview)")
    ap.add_argument("--tree-id", help="limit to a single tree id")
    ap.add_argument("--owner-id", type=int, help="limit to a single owner id")
    args = ap.parse_args(argv)

    db = SessionLocal()
    try:
        q = db.query(Tree)
        if args.tree_id:
            q = q.filter(Tree.id == args.tree_id)
        if args.owner_id:
            q = q.filter(Tree.owner_id == args.owner_id)

        touched = total_b = total_d = 0
        for t in q.all():
            people = t.people or []
            old_lo, old_hi = _span(people)
            new_people, nb, nd = resign_people(people)
            if not (nb or nd):
                print(f"tree {t.id}: no change ({len(people)} people)")
                continue
            new_lo, new_hi = _span(new_people)
            touched += 1
            total_b += nb
            total_d += nd
            print(f"tree {t.id} (owner {t.owner_id}, {len(people)} people): "
                  f"birth {nb} / death {nd} re-signed | "
                  f"span {old_lo}..{old_hi} -> {new_lo}..{new_hi}")
            if args.apply:
                t.people = new_people
                t.meta = core.tree_meta(new_people)

        if args.apply:
            db.commit()
            print(f"APPLIED: {touched} tree(s) updated "
                  f"({total_b} birth, {total_d} death years re-signed).")
        else:
            print(f"DRY-RUN: would update {touched} tree(s) "
                  f"({total_b} birth, {total_d} death years). Re-run with --apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
