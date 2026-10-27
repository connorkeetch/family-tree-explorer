"""
parse_gedcom.py  -- dependency-free (stdlib only)

Parses one OR MORE getmyancestors GEDCOM exports into structured per-ancestor
data, deduplicating people across files by FamilySearch ID (FID) and computing
generation depth by BFS up from a chosen root.

Output (under --outdir, default "output", or output/<label>/ if --label given):
  - ancestors.json : full structured records
  - ancestors.csv  : flat table for spreadsheets

Captured per person: FamilySearch ID, name, sex, generation depth from the
root person, birth/death/christening/burial (date + place + lat/long),
source count, memory (OBJE) count, note count, and pedigree links.

MERGING (deeper pulls / second trees)
-------------------------------------
Pass several GEDCOMs and they are merged at the *model* level (no intermediate
GEDCOM is written, so there are no pointer-renumbering bugs):
  * individuals are deduplicated by FID (_FSFTID),
  * families are deduplicated by the (father FID, mother FID) couple,
  * every parent relationship seen in any file is unioned together,
then generations are recomputed by BFS from the ORIGINAL root, so newly
appended ancestors get the right generation numbers. Example:

    python parse_gedcom.py data/full.ged data/deeper16-20.ged --root <YOUR_ROOT_FID>

BIOLOGICAL vs ADOPTIVE LINES
----------------------------
`father_xref` and `mother_xref` are the selected biological slots, including a
missing parent. `parent_xrefs` also retains alternate claims. When FamilySearch
records more than one parent couple for a person (alternate/uncertain fathers, or adoptive +
birth couples), this script chooses the PREFERRED couple deterministically:

  1. an explicit override (see --parent-overrides) always wins, and can even
     *inject* a parent edge that FamilySearch does not link at all;
  2. otherwise a couple whose GEDCOM `FAMC` carries `PEDI birth` (or a blank
     PEDI, which is what getmyancestors emits) beats one tagged `PEDI adopted`
     / step / foster / guardian;
  3. ties break on a stable sort of the parents' FIDs.

IMPORTANT, REAL-DATA CAVEAT: getmyancestors (v1.1.2) emits NO `PEDI` tags at
all -- it captures every couple but never labels which is biological. So on a
real pull the PEDI step (2) never fires; the mechanisms that actually steer the
biological line on real data are (a) starting the FamilySearch pull at the known
biological parent's FID and (b) the injection override in (1). The PEDI logic is
built and unit-tested for hand-edited / future GEDCOMs that DO carry pedigree
tags. See archive/DEEPER_PULL.md and docs/BIOLOGICAL_LINES.md.

Usage:
    python parse_gedcom.py data/full.ged
    python parse_gedcom.py data/full.ged --root <YOUR_ROOT_FID>
    python parse_gedcom.py data/full.ged data/more.ged --root <YOUR_ROOT_FID>
    python parse_gedcom.py data/wife.ged --root <her_FID> --label wife
    python parse_gedcom.py data/wife.ged data/wife_bio.ged \\
        --root <her_FID> --label wife --parent-overrides wife_bio.json
"""

import argparse
import csv
import datetime
import json
import re
import sys
from pathlib import Path

from .analyze_origins import _fold

# ---------------------------------------------------------------------------
# Low-level GEDCOM line parsing
# ---------------------------------------------------------------------------

# A GEDCOM line is:  <level> [@xref@] <TAG> [value]
LINE_RE = re.compile(r"^\s*(\d+)\s+(?:(@[^@]+@)\s+)?(\S+)(?:\s(.*))?$")

# FamilySearch person ID, e.g. XXXX-XXX
FID_RE = re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{3}$")


class Node:
    """A single GEDCOM line plus its nested children."""

    __slots__ = ("level", "tag", "value", "xref", "children")

    def __init__(self, level, tag, value, xref=None):
        self.level = level
        self.tag = tag
        self.value = value or ""
        self.xref = xref          # set only on 0-level record definitions (@I1@ etc.)
        self.children = []

    def kids(self, tag):
        """All direct children with the given tag."""
        return [c for c in self.children if c.tag == tag]

    def first(self, tag):
        """First direct child with the given tag, or None."""
        for c in self.children:
            if c.tag == tag:
                return c
        return None


def parse_records(path):
    """Read a GEDCOM file into a list of top-level (level-0) Node trees."""
    records = []
    stack = []  # stack of (level, node)

    with open(path, "r", encoding="utf-8-sig") as fh:
        for raw in fh:
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            m = LINE_RE.match(line)
            if not m:
                # CONC/CONT or malformed; skip silently (we don't need it)
                continue
            level = int(m.group(1))
            xref = m.group(2)
            tag = m.group(3)
            value = m.group(4)

            # On a 0-level definition line the xref is the record id and tag
            # is the record type (INDI/FAM/SOUR/...). On pointer lines the
            # "value" holds the @xref@ pointer instead.
            node = Node(level, tag, value, xref=xref if level == 0 else None)

            # unwind the stack to the parent level
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].children.append(node)
            else:
                records.append(node)
            stack.append((level, node))

    return records


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

NAME_RE = re.compile(r"^(?P<given>.*?)\s*/(?P<surname>[^/]*)/\s*(?P<suffix>.*)$")
YEAR_RE = re.compile(r"(\d{4})")

# Markers that flip a year to BC. Deep FamilySearch lines reach legendary BC
# ancestors, whose dates arrive in many languages and formats: English
# "BC"/"BCE" (often glued to the digits, "3545BCE"), Spanish/Portuguese "a.C."
# (antes de Cristo), Italian "avanti Cristo", and CJK/Korean "before-era" markers
# (西元前 / 公元前 / 紀元前 / 기원전). We anchor the Latin token on a B/A-led era
# *token* bounded by non-letters (so it catches the glued form yet never fires on
# a stray "ac"/"bc" inside a word), and never on a bare "antes"/"before" -- "antes
# de 1305" means "before 1305" (still AD), and "d.C."/"AD" are AD, not BC. A
# leading minus on the year itself ("-3150") is handled separately in extract_year.
BC_RE = re.compile(
    r"(?<![A-Za-z])(?:B\.?C\.?(?:E\.?)?|A\.?C\.?)(?![A-Za-z])"   # BC / BCE / a.C.
    r"|\bv\.?\s?(?:chr|c)\.?(?![A-Za-z])"                        # Dutch/German voor/vor Chr.
    r"|(?:avanti|antes\s+de)\s+cristo"                          # Italian / Spanish, spelled
    r"|[西公]元前|紀元前|기원전",                                # CJK / Korean "before era"
    re.I,
)


def parse_name(value):
    """'Avery /Example/' -> (given, surname, full)."""
    value = value.strip()
    m = NAME_RE.match(value)
    if m:
        given = m.group("given").strip()
        surname = m.group("surname").strip()
        full = " ".join(p for p in (given, surname) if p)
        return given, surname, full or value.replace("/", "").strip()
    return value, "", value


def extract_year(date_str, as_of_year=None):
    """Pull a year from a GEDCOM date, signed so BC is negative.

    Handles 'YYYYMMDD' (compact), '10 September 1924', '1940', 'September 1983',
    and BC dates -- '5626 BC' -> -5626, '0038 AC' -> -38, '0039 avanti Cristo' ->
    -39. Without the sign those legendary dates fold onto the AD axis (5626 BC
    reads as the future year 5626), which is why the birth-year filter spanned
    1..5626 instead of 5626 BC..present. BC years here are zero-padded to four
    digits, so YEAR_RE still grabs them -- and matching only four digits keeps
    'AC' day numbers ('14 de enero de 0038 AC') from being read as the year.

    An AD year past the present is impossible for a birth. In this deep-line data
    those are unmarked-BC patriarchs ('2122') or a non-Gregorian epoch
    ('2358 AM.'); we return None so the UI treats them as undated rather than let
    one set the birth-year slider to a future year. BC years are never future, so
    the ceiling is AD-only. `as_of_year` overrides "now" for deterministic tests.
    Returns int or None.
    """
    if not date_str:
        return None
    s = date_str.strip()
    ceiling = as_of_year if as_of_year is not None else datetime.date.today().year
    if re.fullmatch(r"\d{8}", s):          # 19920423 (always a modern AD date)
        y = int(s[:4])
        return y if y <= ceiling else None
    m = YEAR_RE.search(s)
    if not m:
        return None
    year = int(m.group(1))
    # BC arrives either as an era marker (BC_RE) or as a leading minus sign on the
    # year itself ("-3150"). A minus that follows a digit is a range/date
    # separator ("10-12-1850"), not a sign, so we only honour one at string start
    # or after whitespace.
    i = m.start()
    signed = i > 0 and s[i - 1] == "-" and (i == 1 or s[i - 2].isspace())
    if signed or BC_RE.search(s):
        return -year
    return year if year <= ceiling else None


def extract_place(fact_node):
    """From a fact node (BIRT/DEAT/...), return (place_text, lat, lon)."""
    plac = fact_node.first("PLAC")
    if not plac:
        return None, None, None
    place_text = plac.value.strip() or None
    lat = lon = None
    mapnode = plac.first("MAP")
    if mapnode:
        lati = mapnode.first("LATI")
        long_ = mapnode.first("LONG")
        if lati and lati.value.strip():
            try:
                lat = float(lati.value.strip())
            except ValueError:
                lat = None
        if long_ and long_.value.strip():
            try:
                lon = float(long_.value.strip())
            except ValueError:
                lon = None
    return place_text, lat, lon


def extract_fact(indi_node, tag):
    """Return a dict {date, year, place, lat, lon} for the first fact `tag`."""
    fact = indi_node.first(tag)
    if not fact:
        return None
    date_node = fact.first("DATE")
    date_str = date_node.value.strip() if date_node else None
    place_text, lat, lon = extract_place(fact)
    return {
        "date": date_str,
        "year": extract_year(date_str),
        "place": place_text,
        "lat": lat,
        "lon": lon,
    }


def count_tag(indi_node, tag):
    return len(indi_node.kids(tag))


# ---------------------------------------------------------------------------
# Per-file indexing
# ---------------------------------------------------------------------------

def build_index(records):
    """Index one parsed GEDCOM file into {indi}, {fam}, submitter_name."""
    indi, fam = {}, {}
    submitter_name = None
    for rec in records:
        if rec.tag == "INDI" and rec.xref:
            indi[rec.xref] = rec
        elif rec.tag == "FAM" and rec.xref:
            fam[rec.xref] = rec
        elif rec.tag == "SUBM":
            n = rec.first("NAME")
            if n:
                submitter_name = n.value.strip()
    return indi, fam, submitter_name


def node_fid(node):
    """FamilySearch ID of an INDI node, or None."""
    f = node.first("_FSFTID")
    return f.value.strip() if f and f.value.strip() else None


def identity_of(node, file_idx):
    """Stable cross-file identity for a person: their FID if present, else a
    file-local fallback (so people lacking _FSFTID still parse, just without
    cross-file dedup)."""
    fid = node_fid(node)
    return fid if fid else "F%d:%s" % (file_idx, node.xref)


# ---------------------------------------------------------------------------
# Pedigree (biological vs adoptive) ranking
# ---------------------------------------------------------------------------

# Lower tier == more preferred as the biological couple.
_PEDI_BIOLOGICAL = {"", "birth", "biological", "natural", "genetic"}
_PEDI_NON_BIOLOGICAL = {
    "adopted", "adoptive", "adoption",
    "step", "stepparent",
    "foster",
    "guardian", "guardianship",
    "sealing",            # LDS sealing, not a biological link
}


def pedi_tier(pedi_values):
    """Map a set of (lowercased) PEDI strings for one (child, couple) to a tier.

    0 = biological / blank (getmyancestors emits blank -> treat as the real line)
    1 = unknown / other label
    2 = explicitly non-biological (adopted, step, foster, guardian, ...)
    """
    if not pedi_values:
        pedi_values = {""}
    if any(p in _PEDI_BIOLOGICAL for p in pedi_values):
        return 0
    if any(p in _PEDI_NON_BIOLOGICAL for p in pedi_values):
        return 2
    return 1


def pedi_label(tier):
    return {0: "biological", 1: "unknown", 2: "non-biological"}[tier]


# Age window for a biological parent at the child's birth (year precision).
# Deliberately wide: this only demotes a couple the dates rule out outright.
MIN_PARENT_AGE = 12
MAX_MOTHER_AGE = 55
MAX_FATHER_AGE = 80


def impossible_parent(child_birth, parent_birth, parent_death, is_mother):
    """True when the dates rule this person out as the child's biological parent:
    too young/old at the birth, or dead before it (a father may die up to ~9
    months before, so his death year may trail the birth year by one). Missing
    dates never count against a parent. BC years are negative, so ages still
    subtract correctly."""
    if child_birth is None:
        return False
    if parent_birth is not None:
        age = child_birth - parent_birth
        if age < MIN_PARENT_AGE or age > (MAX_MOTHER_AGE if is_mother else MAX_FATHER_AGE):
            return True
    if parent_death is not None:
        return parent_death < child_birth - (0 if is_mother else 1)
    return False


# ---------------------------------------------------------------------------
# Model-level merge of one or more files
# ---------------------------------------------------------------------------

class Model:
    """FID-keyed merged model built from one or more GEDCOM files.

    Attributes
    ----------
    nodes      : identity -> chosen (richest) INDI Node  (data source per person)
    fid        : identity -> FID string or None
    couples    : (father_id|None, mother_id|None) -> set(child_identity)
    pedi       : (child_identity, couple_key) -> set(lowercased PEDI strings)
    submitter  : submitter name from the first file
    injected   : set of (child_identity, couple_key) added by an override
    missing_overrides : list of (child_id, parent_id) the data did not contain
    """

    def __init__(self):
        self.nodes = {}
        self._candidates = {}      # identity -> list[(file_idx, node)]
        self.fid = {}
        self.couples = {}
        self.pedi = {}
        self.submitter = None
        self.injected = set()
        self.missing_overrides = []
        self._child_couples = {}   # child_identity -> set(couple_key); built in finalize()

    # -- ingest -----------------------------------------------------------
    def add_file(self, file_idx, indi, fam, submitter):
        if submitter and not self.submitter:
            self.submitter = submitter

        # per-file xref -> identity
        x2id = {x: identity_of(n, file_idx) for x, n in indi.items()}

        for xref, node in indi.items():
            ident = x2id[xref]
            self._candidates.setdefault(ident, []).append((file_idx, node))
            if node_fid(node):
                self.fid[ident] = node_fid(node)
            else:
                self.fid.setdefault(ident, None)

        def couple_key(fnode):
            husb = fnode.first("HUSB")
            wife = fnode.first("WIFE")
            father = x2id.get(husb.value.strip()) if husb else None
            mother = x2id.get(wife.value.strip()) if wife else None
            return (father, mother)

        # children listed on the FAM record (no PEDI lives here)
        for fnode in fam.values():
            key = couple_key(fnode)
            for c in fnode.kids("CHIL"):
                cid = x2id.get(c.value.strip())
                if cid is not None:
                    self.couples.setdefault(key, set()).add(cid)

        # children via each person's FAMC pointer -- this is where PEDI lives
        for xref, node in indi.items():
            cid = x2id[xref]
            for famc in node.kids("FAMC"):
                fnode = fam.get(famc.value.strip())
                if not fnode:
                    continue
                key = couple_key(fnode)
                self.couples.setdefault(key, set()).add(cid)
                pedi_node = famc.first("PEDI")
                val = pedi_node.value.strip().lower() if pedi_node else ""
                self.pedi.setdefault((cid, key), set()).add(val)

    # -- overrides --------------------------------------------------------
    def apply_overrides(self, overrides):
        """Inject / force biological parent couples.

        `overrides` maps a child FID -> {"father": FID?, "mother": FID?,
        "pedigree": str?}. The couple edge is CREATED even if FamilySearch never
        linked it (for example, when biological parents
        come back as a disconnected component from a separate pull). The forced
        couple is also marked preferred so it selects the father/mother slots."""
        self.overridden = {}
        for child_fid, spec in (overrides or {}).items():
            father = (spec.get("father") or "").strip() or None
            mother = (spec.get("mother") or "").strip() or None
            key = (father, mother)
            self.overridden[child_fid] = key
            self.couples.setdefault(key, set()).add(child_fid)
            self.pedi.setdefault((child_fid, key), set()).add(
                (spec.get("pedigree") or "biological").lower())
            self.injected.add((child_fid, key))
            # note any referenced person that was not actually pulled
            for pid in (father, mother):
                if pid and pid not in self._candidates and pid != child_fid:
                    self.missing_overrides.append((child_fid, pid))

    # -- finalize ---------------------------------------------------------
    def finalize(self):
        """Pick the richest node per identity and make sure every identity that
        is referenced as a parent exists (as a stub if it was never an INDI)."""
        for ident, cands in self._candidates.items():
            # richest = most sub-lines; tie-break prefers the earlier file
            best = max(cands, key=lambda fn: (len(fn[1].children), -fn[0]))
            self.nodes[ident] = best[1]

        referenced = set()
        for (father, mother), kids in self.couples.items():
            if father:
                referenced.add(father)
            if mother:
                referenced.add(mother)
        for ident in referenced:
            if ident not in self.nodes:
                # parent referenced but never defined as an INDI (e.g. an
                # injected biological parent that was not pulled). Add a stub.
                self.nodes[ident] = None
                self.fid.setdefault(ident, ident if FID_RE.match(ident) else None)

        # index child -> couple keys once, so couples_of() is O(1) per child
        # Scanning all couples for every child would be O(n^2).
        self._child_couples = {}
        for key, kids in self.couples.items():
            for cid in kids:
                self._child_couples.setdefault(cid, set()).add(key)

    # -- queries ----------------------------------------------------------
    def couples_of(self, child_id):
        """All parent-couple keys for a child (deterministically ordered)."""
        keys = self._child_couples.get(child_id, ())
        # stable order: by (father_fid, mother_fid) with None last
        return sorted(keys, key=lambda k: (k[0] or "~", k[1] or "~"))

    def all_parent_ids(self, child_id):
        """Every distinct parent identity across all couples (for BFS / counts).
        Preserves the original 'traverse every ancestral path' behaviour."""
        out = []
        for father, mother in self.couples_of(child_id):
            for p in (father, mother):
                if p and p not in out:
                    out.append(p)
        return out

    def _years(self, ident):
        """(birth-or-christening year, death year) for one identity."""
        node = self.nodes.get(ident)
        if node is None:
            return None, None
        year = lambda tag: (extract_fact(node, tag) or {}).get("year")
        return year("BIRT") or year("CHR"), year("DEAT")

    def rank_couples(self, child_id):
        """(preferred couple, couples tied with it on the evidence).

        getmyancestors keeps a person's parent couples in a set, so FamilySearch's
        own preferred-parents choice never reaches the GEDCOM; we rank instead:
        PEDI tier (birth over adopted), then couples the dates don't rule out,
        then couples naming both parents, then parent FIDs (deterministic). The
        tied set holds every couple as good as the winner on the hard evidence
        (PEDI tier, dates) when 2+ do -- completeness and FID order are only
        tiebreaks, so core.parents lets Jev weigh these first."""
        forced = getattr(self, "overridden", {}).get(child_id)
        couples = self.couples_of(child_id)
        if forced is not None and forced in couples:
            return forced, set()
        if len(couples) < 2:
            return (couples[0] if couples else None), set()

        child_birth = self._years(child_id)[0]

        def evidence(key):
            tier = pedi_tier(self.pedi.get((child_id, key), {""}))
            impossible = any(
                impossible_parent(child_birth, *self._years(p), is_mother=(i == 1))
                for i, p in enumerate(key) if p)
            return (tier, impossible, -sum(1 for p in key if p))

        ev = {key: evidence(key) for key in couples}
        best = min(couples, key=lambda k: (ev[k], k[0] or "~", k[1] or "~"))
        tied = {k for k in couples if ev[k][:2] == ev[best][:2]}
        return best, (tied if len(tied) > 1 else set())

    def preferred_couple(self, child_id):
        """The (father_id, mother_id) couple to treat as biological."""
        return self.rank_couples(child_id)[0]


# ---------------------------------------------------------------------------
# Root selection + generations
# ---------------------------------------------------------------------------

def resolve_root(model, root_arg, files_first_indi=None):
    """Resolve the root *identity* from --root (a FID or an @xref@) or, failing
    that, the descendant-most person (has parents, is nobody's parent)."""
    if root_arg:
        arg = root_arg.strip()
        if FID_RE.match(arg):
            # by FID
            for ident, fid in model.fid.items():
                if fid == arg:
                    return ident
            sys.exit("Root FID %s not found in the data." % arg)
        # legacy @xref@: interpret against the FIRST file's xrefs
        if files_first_indi and arg in files_first_indi:
            return identity_of(files_first_indi[arg], 0)
        sys.exit("Root %s not found. Pass a FamilySearch ID like XXXX-XXX." % arg)

    # heuristic: someone who is a child but never a parent
    is_parent = set()
    for (father, mother) in model.couples:
        if father:
            is_parent.add(father)
        if mother:
            is_parent.add(mother)
    is_child = set()
    for kids in model.couples.values():
        is_child |= kids
    candidates = [i for i in model.nodes if i in is_child and i not in is_parent]
    if len(candidates) == 1:
        return candidates[0]
    if model.submitter:
        for ident in (candidates or model.nodes):
            node = model.nodes.get(ident)
            nm = node.first("NAME") if node else None
            if nm and parse_name(nm.value)[2].lower() == model.submitter.lower():
                return ident
    if candidates:
        return sorted(candidates, key=lambda i: model.fid.get(i) or i)[0]
    return next(iter(sorted(model.nodes)), None)


def compute_generations(root, model):
    """BFS upward from root through ALL parent couples. {identity: min gen}."""
    gen = {root: 0}
    queue = [root]
    while queue:
        cur = queue.pop(0)
        for p in model.all_parent_ids(cur):
            cand = gen[cur] + 1
            if p not in gen or cand < gen[p]:
                gen[p] = cand
                queue.append(p)
    return gen


# ---------------------------------------------------------------------------
# Build people records
# ---------------------------------------------------------------------------

def assign_xrefs(model, root):
    """Deterministic identity -> @xref@. Root is @I1@; the rest sort by FID."""
    others = sorted((i for i in model.nodes if i != root),
                    key=lambda i: (model.fid.get(i) or "~", str(i)))
    ordered = ([root] if root in model.nodes else []) + others
    return {ident: "@I%d@" % (n + 1) for n, ident in enumerate(ordered)}


def build_people(paths, root_arg=None, overrides=None):
    files = [build_index(parse_records(p)) for p in paths]
    model = Model()
    for i, (indi, fam, submitter) in enumerate(files):
        model.add_file(i, indi, fam, submitter)
    if overrides:
        model.apply_overrides(overrides)
    model.finalize()

    root = resolve_root(model, root_arg, files_first_indi=files[0][0] if files else None)
    gen = compute_generations(root, model)
    xref = assign_xrefs(model, root)

    people = []
    for ident, node in model.nodes.items():
        name_node = node.first("NAME") if node else None
        given, surname, full = parse_name(name_node.value) if name_node else ("", "", "")
        sex_node = node.first("SEX") if node else None
        birth = extract_fact(node, "BIRT") if node else None
        death = extract_fact(node, "DEAT") if node else None
        chris = extract_fact(node, "CHR") if node else None
        burial = extract_fact(node, "BURI") if node else None

        all_parents = model.all_parent_ids(ident)
        preferred, tied = model.rank_couples(ident)
        couples = model.couples_of(ident)

        # Keep every claim for inspection; explicit father/mother fields select
        # the biological slots without filling a missing one from another couple.
        ordered_parents = []
        if preferred:
            for p in preferred:           # (father, mother)
                if p:
                    ordered_parents.append(p)
        for p in all_parents:
            if p not in ordered_parents:
                ordered_parents.append(p)

        father_id = preferred[0] if preferred else None
        mother_id = preferred[1] if preferred else None

        # describe every couple for transparency / debugging
        couple_records = []
        for key in couples:
            tier = pedi_tier(model.pedi.get((ident, key), {""}))
            couple_records.append({
                "father_xref": xref.get(key[0]) if key[0] else None,
                "mother_xref": xref.get(key[1]) if key[1] else None,
                "father_fid": model.fid.get(key[0]) if key[0] else None,
                "mother_fid": model.fid.get(key[1]) if key[1] else None,
                "pedigree": pedi_label(tier),
                "preferred": key == preferred,
                # tied with the preferred couple on every check (FID order chose)
                "tied": key in tied,
                "injected": (ident, key) in model.injected,
            })

        people.append({
            "xref": xref[ident],
            "fs_id": model.fid.get(ident),
            "given": given,
            "surname": surname,
            "name": full,
            "sex": sex_node.value.strip() if sex_node else None,
            "generation": gen.get(ident),          # None if not on the direct line
            "on_direct_line": ident in gen,
            "birth_date": birth["date"] if birth else None,
            "birth_year": birth["year"] if birth else None,
            "birth_place": birth["place"] if birth else None,
            "birth_lat": birth["lat"] if birth else None,
            "birth_lon": birth["lon"] if birth else None,
            "death_date": death["date"] if death else None,
            "death_year": death["year"] if death else None,
            "death_place": death["place"] if death else None,
            "death_lat": death["lat"] if death else None,
            "death_lon": death["lon"] if death else None,
            "christening_place": chris["place"] if chris else None,
            "burial_place": burial["place"] if burial else None,
            "source_count": count_tag(node, "SOUR") if node else 0,
            "memory_count": count_tag(node, "OBJE") if node else 0,
            "note_count": count_tag(node, "NOTE") if node else 0,
            "num_parents_known": len(all_parents),
            "parent_xrefs": [xref[p] for p in ordered_parents],
            "father_xref": xref.get(father_id) if father_id else None,
            "mother_xref": xref.get(mother_id) if mother_id else None,
            "pedigree": pedi_label(pedi_tier(model.pedi.get((ident, preferred), {""})))
                        if preferred else None,
            "num_parent_couples": len(couples),
            "parent_couples": couple_records,
            "is_leaf": len(all_parents) == 0,
        })

    mark_unnamed_wives(people)
    # sort by generation then name for readability
    people.sort(key=lambda p: (p["generation"] if p["generation"] is not None else 999,
                               p["surname"], p["given"]))
    return people, xref[root], model


# ---------------------------------------------------------------------------
# Wives recorded under their husband's name
# ---------------------------------------------------------------------------

# Old registers often name a wife after her husband ("Mrs. Charles Baker"), and
# the record can reach FamilySearch as a woman called "Charles Baker", sometimes
# with his birthplace copied in too.
_WIFE_PREFIX = re.compile(
    r"^(mrs|mistress|fru|frau|madame|mme|wife of|wife|hustru|sra|senora|vrouw|mevrouw)\b")
_GENERIC_PLACE = {"", "unitedkingdom", "uk", "unitedstates", "usa"}


def _plain(s):
    return re.sub(r"[^a-z ]", "", _fold(s or "")).strip()


def _place_tokens(place):
    """{'leinster', 'ireland'} from "of Leinster, Ireland" -- letters only, a
    leading "of" dropped, bare country-of-record suffixes ignored."""
    toks = (re.sub(r"^of\b", "", _fold(t).strip()) for t in place.split(","))
    return {re.sub(r"[^a-z]", "", t) for t in toks} - _GENERIC_PLACE


def mark_unnamed_wives(people):
    """Flag mothers whose recorded name is a placeholder for their husband's.

    A mother named exactly like the father she's paired with is renamed "Wife of
    <his name>" for display (FamilySearch's name kept in `fs_name`; the
    placeholder given/surname cleared so it doesn't inflate his surname); one
    named "Mrs. ..." / "Wife of ..." keeps her name. Either way she gets
    `wife_of` = his xref, and `place_copied` when her birthplace is his or a
    vaguer version of it ("Ireland" for "Leinster, Ireland") -- his fact, not
    hers, so the origin models don't count it."""
    by = {p["xref"]: p for p in people}
    for child in people:
        for c in child.get("parent_couples") or []:
            f, m = by.get(c["father_xref"]), by.get(c["mother_xref"])
            if not f or not m or m.get("wife_of"):
                continue
            name = _plain(m.get("name"))
            copy = bool(name) and name == _plain(f.get("name"))
            if not (copy or _WIFE_PREFIX.match(name)):
                continue
            m["wife_of"] = f["xref"]
            if copy:
                m["fs_name"] = m["name"]
                m["name"] = "Wife of " + f["name"]
                m["given"] = m["surname"] = ""
            mp, fp = m.get("birth_place"), f.get("birth_place")
            if mp and fp and _place_tokens(mp) <= _place_tokens(fp):
                m["place_copied"] = True


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

CSV_FIELDS = [
    "fs_id", "name", "given", "surname", "sex", "generation", "on_direct_line",
    "birth_year", "birth_date", "birth_place", "birth_lat", "birth_lon",
    "death_year", "death_date", "death_place", "death_lat", "death_lon", "burial_place",
    "source_count", "memory_count", "note_count",
    "num_parents_known", "num_parent_couples", "pedigree", "is_leaf",
]


def write_outputs(people, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "ancestors.json").write_text(
        json.dumps(people, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(outdir / "ancestors.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for p in people:
            w.writerow(p)


def print_summary(people, root_xref, model):
    direct = [p for p in people if p["on_direct_line"]]
    by_gen = {}
    for p in direct:
        by_gen.setdefault(p["generation"], []).append(p)
    root = next((p for p in people if p["xref"] == root_xref), None)
    print(f"\nRoot person : {root['name'] if root else root_xref} "
          f"({root['fs_id'] if root else '?'})")
    print(f"Individuals : {len(people)}  (direct-line: {len(direct)})")
    print(f"Max generation reached: {max((p['generation'] for p in direct), default=0)}")
    print("\nPer-generation completeness (direct line):")
    print(f"{'gen':>3} {'have':>5} {'expect':>6} {'w/birthplace':>13} {'w/coords':>9} {'leaves':>7}")
    for g in sorted(by_gen):
        ppl = by_gen[g]
        with_place = sum(1 for p in ppl if p["birth_place"])
        with_coord = sum(1 for p in ppl if p["birth_lat"] is not None)
        leaves = sum(1 for p in ppl if p["is_leaf"])
        print(f"{g:>3} {len(ppl):>5} {2**g:>6} {with_place:>13} {with_coord:>9} {leaves:>7}")
    total_src = sum(p["source_count"] for p in people)
    total_mem = sum(p["memory_count"] for p in people)
    with_mem = sum(1 for p in people if p["memory_count"] > 0)
    print(f"\nSources (links) : {total_src}")
    print(f"Memories (OBJE) : {total_mem} across {with_mem} people")

    multi = [p for p in people if p["num_parent_couples"] > 1]
    nonbio = [p for p in people if p["pedigree"] and p["pedigree"] != "biological"]
    if multi:
        print(f"\nPeople with >1 parent couple : {len(multi)} "
              f"(biological couple chosen deterministically; see parent_couples)")
    if nonbio:
        print(f"People whose preferred couple is non-biological : {len(nonbio)}")
    if model.injected:
        print(f"Injected biological edges (overrides) : {len(model.injected)}")
    if model.missing_overrides:
        print("\n[!] Overrides referenced FIDs not present in the pulled data "
              "(no ancestor data for them -- pull starting at that FID):")
        for child, parent in model.missing_overrides:
            print(f"      child {child}  ->  missing parent {parent}")
    print("\nBirthplaces present:",
          sum(1 for p in people if p["birth_place"]), "/", len(people))


def load_overrides(path):
    """Load a parent-override JSON file.

    Format: {"<childFID>": {"father": "<FID>", "mother": "<FID>",
                            "pedigree": "biological"}, ...}
    father/mother are individually optional; pedigree defaults to biological.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        sys.exit("--parent-overrides must be a JSON object keyed by child FID.")
    return data


def main():
    ap = argparse.ArgumentParser(
        description="Parse + merge getmyancestors GEDCOM(s) to structured data.")
    ap.add_argument("gedcom", nargs="+", help="path(s) to .ged file(s); multiple are merged by FID")
    ap.add_argument("--outdir", help="output directory [output, or output/<label>]")
    ap.add_argument("--label", help="name this tree -> output/<label>/ (e.g. 'wife')")
    ap.add_argument("--root", help="root person, a FamilySearch ID (e.g. XXXX-XXX) or @xref@")
    ap.add_argument("--parent-overrides", dest="overrides",
                    help="JSON file forcing/injecting biological parent couples")
    args = ap.parse_args()

    for g in args.gedcom:
        if not Path(g).exists():
            sys.exit(f"File not found: {g}")

    outdir = args.outdir or (f"output/{args.label}" if args.label else "output")
    overrides = load_overrides(args.overrides) if args.overrides else None

    people, root_xref, model = build_people(args.gedcom, args.root, overrides)
    write_outputs(people, outdir)
    print_summary(people, root_xref, model)
    print(f"\nWrote {outdir}/ancestors.json and {outdir}/ancestors.csv")


if __name__ == "__main__":
    main()
