"""
analyze_origins.py  -- dependency-free (stdlib only)

Reads output/ancestors.json (produced by parse_gedcom.py) and computes where
your ancestors came from, two ways:

  1. WEIGHTED (DNA-style): each ancestral line is followed up to its most
     distant KNOWN ancestor (a "leaf"); that leaf's birth nationality gets
     (1/2)^generation of "you". Missing parents / unresolved places fall into
     an honest "untraced" bucket. This approximates an ethnicity estimate but
     reflects your PAPER TRAIL, not DNA -- it will not match a DNA test.

  2. HEADCOUNT: of every distinct ancestor with a known birthplace, what % were
     born in each nationality. Each person counted once.

Writes output/origins.json. (The interactive map/fan are now the web app's job;
this module's pure functions feed both the CLI report and core.payloads.)

Nationality is inferred from the free-text place STRING (not coordinates),
because coordinates collapse England/Scotland/Wales/Ireland into "United
Kingdom" and we want that granularity. Coordinates are used only for map pins.

Usage:
    python analyze_origins.py
    python analyze_origins.py --in output/ancestors.json --outdir output
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict, deque
from pathlib import Path

# ---------------------------------------------------------------------------
# Nationality inference (place string -> demonym)
# ---------------------------------------------------------------------------

US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia",
}
US_COUNTRY = {
    "united states", "usa", "us", "united states of america", "u.s.a.",
    "u.s.", "united states  of america",
}
# Postal abbreviations, matched ONLY as the final token ("Cobbs Hall, ..., VA").
# Deliberately omits ambiguous 2-letter codes that collide with common place
# tokens: CO (="County"), IN/OR/ME/DE (prepositions/words), OK, ID, HI, AL.
US_STATE_ABBREV = {
    "az", "ar", "ca", "ct", "fl", "ga", "ia", "il", "ks", "ky", "la", "ma",
    "md", "mi", "mn", "mo", "ms", "mt", "nc", "nd", "ne", "nh", "nj", "nm",
    "nv", "ny", "oh", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "va", "vt",
    "wa", "wi", "wv", "wy",
}

# Ordered (keyword, label) rules checked AFTER the US scan. First match wins.
# Keys are matched against whole comma-separated tokens unless marked substring.
NATIONALITY_RULES = [
    # British Isles -- order matters: Northern Ireland before Ireland.
    (["northern ireland"], "Northern Irish"),
    (["scotland"], "Scottish"),
    (["wales"], "Welsh"),
    (["england", "inglaterra", "engalnd", "ingland"], "English"),
    (["ireland", "irish free state", "kingdom of ireland"], "Irish"),
    (["isle of man", "isla de man"], "Manx"),
    (["channel islands", "jersey", "guernsey", "bailiwick of jersey",
      "bailiwick of guernsey"], "Channel Islander"),
    # Nordics (incl. native-language country names common in old records)
    (["denmark", "danmark"], "Danish"),
    (["norway", "norge", "noreg"], "Norwegian"),
    (["sweden", "sverige"], "Swedish"),
    (["finland", "suomi"], "Finnish"),
    (["iceland"], "Icelandic"),
    # Western / Central Europe (German states + historical Prussian provinces)
    (["germany", "deutschland", "deutsches reich", "german empire",
      "holy roman empire", "alemania", "alemanha", "allemagne",
      "prussia", "preussen", "bavaria", "bayern", "konigreich bayern",
      "königreich bayern", "saxony", "sachsen", "hesse", "hessen",
      "wurttemberg", "wurttemburg", "wuerttemberg", "württemberg",
      "konigreich wurttemberg", "königreich württemberg", "schwarzwaldkreis",
      "baden", "hanover", "hannover", "mecklenburg", "holstein", "schleswig",
      "pomerania", "pommern", "silesia", "schlesien", "westphalia", "westfalen",
      "brandenburg", "oldenburg", "rhineland", "rhineland-palatinate",
      "rheinland-pfalz", "rhine province", "thuringen", "thüringen",
      "heiliges romisches reich", "heiliges römisches reich",
      "römisches reich"], "German"),
    (["france", "frankrijk", "frankreich"], "French"),
    (["netherlands", "holland", "nederland", "pays-bas", "noord-holland",
      "zuid-holland", "noord holland", "zuid holland"], "Dutch"),
    # Before Luxembourg: Belgium has a Luxembourg province ("Arlon, Luxembourg,
    # Belgique"). Native names are safe substrings, unlike those in COUNTRY_LAST_TOKEN.
    (["belgium", "belgique", "belgie", "belgien", "belgica"], "Belgian"),
    (["switzerland", "schweiz", "suisse", "swiss confederation"], "Swiss"),
    (["austria-hungary", "austria hungary"], "Austrian"),
    (["austria", "osterreich", "oesterreich"], "Austrian"),
    (["luxembourg"], "Luxembourgish"),
    (["liechtenstein"], "Liechtensteiner"),
    (["italy", "italia"], "Italian"),
    (["spain", "espana", "españa"], "Spanish"),
    (["portugal"], "Portuguese"),
    (["greece", "hellas"], "Greek"),
    # Central / Eastern Europe
    (["poland", "polska"], "Polish"),
    (["bohemia", "moravia", "czech", "czechia", "czechoslovakia"], "Czech"),
    (["slovakia"], "Slovak"),
    (["hungary", "magyarorszag"], "Hungarian"),
    (["romania", "roumania", "rumania"], "Romanian"),
    (["bulgaria"], "Bulgarian"),
    (["serbia"], "Serbian"),
    (["croatia"], "Croatian"),
    (["slovenia"], "Slovenian"),
    (["ukraine"], "Ukrainian"),
    (["lithuania"], "Lithuanian"),
    (["latvia"], "Latvian"),
    (["estonia"], "Estonian"),
    (["russia", "russian empire"], "Russian"),
    (["turkey"], "Turkish"),
    # Other common immigrant origins to North America
    (["canada", "ontario", "quebec", "nova scotia", "new brunswick"], "Canadian"),
    (["mexico"], "Mexican"),
    (["australia"], "Australian"),
    (["new zealand"], "New Zealander"),
    (["south africa"], "South African"),
    # CJK script can't collide with a Latin toponym, so a substring is safe here
    # (the Latin "china" is last-token only: "Indochina").
    (["中國", "中国"], "Chinese"),
    (["한국", "韓國", "대한민국"], "Korean"),
]

# Bare "United Kingdom" with no constituent nation -> generic British.
UK_GENERIC = {"united kingdom", "uk", "great britain", "britain", "england and wales"}

# Colonial North America. These are the NEW WORLD: a person born here is already
# an American/Canadian, so the immigrant model must climb PAST them to find the
# European who actually crossed the ocean. Matched as substrings (they appear as
# the trailing region in long strings like "Newbury, Essex, Massachusetts Bay
# Colony, British Colonial America"). Canada is checked first so "British North
# America" doesn't get swallowed by the broader American set.
CANADA_COLONIAL = {
    "british north america", "upper canada", "lower canada",
    "province of canada", "new france", "canada east", "canada west", "acadia",
}
US_COLONIAL = {
    "british colonial america", "colonial america", "british america",
    "new england", "massachusetts bay colony", "massachusetts bay",
    "province of massachusetts bay", "connecticut colony",
    "colony of connecticut", "new york colony", "province of new york",
    "plymouth colony", "new plymouth", "rhode island colony",
    "colony of rhode island", "province of pennsylvania",
    "colony of pennsylvania", "province of maine", "province of new hampshire",
    "colony of new jersey", "province of new jersey", "east jersey",
    "west jersey", "colony of virginia", "virginia colony",
    "colony of massachusetts", "province of maryland",
    "carolina colony", "province of carolina",
    "new netherland", "new netherlands", "new amsterdam", "new sweden",
    "new haven colony",
}

# Last-token country abbreviations seen in old GEDCOM place strings, e.g.
# "of Leeds, Yorks., Eng." or "Orbaek, Svendborg, Den." Matched only against the
# FINAL token (after wrapper punctuation is stripped) so they can't misfire on a
# town that merely starts with these letters.
COUNTRY_ABBREV = {
    "eng": "English", "eng.": "English", "engl": "English", "englnd": "English",
    "scot": "Scottish", "scot.": "Scottish", "scotl": "Scottish",
    "wls": "Welsh", "ire": "Irish", "ire.": "Irish", "irel": "Irish",
    "den": "Danish", "den.": "Danish", "denm": "Danish", "denm.": "Danish",
    "danm": "Danish", "dnm": "Danish", "dnmr": "Danish", "dmk": "Danish",
    "swe": "Swedish", "swe.": "Swedish", "sve": "Swedish", "swed": "Swedish",
    "nor": "Norwegian", "nor.": "Norwegian", "fin": "Finnish", "fin.": "Finnish",
    "ger": "German", "ger.": "German", "prus": "German", "prus.": "German",
    "bdn": "German", "wuertt": "German", "wuertt.": "German",
    "neth": "Dutch", "ned": "Dutch",
}

# Country names that are only safe as the FINAL token -- foreign spellings of the
# countries above, plus modern countries the deep (legendary-era) lines reach.
# As substrings they misfire: "franca" in "Villafranca, Italia", "iran" in
# "Miranda", "oman" in "Roman Empire", "india" in "Indiana". Keys are diacritic-
# folded (see _fold), so "França"/"België"/"Türkiye" arrive as "franca"/"belgie"/
# "turkiye". Pre-modern polities (Roman/Byzantine Empire, Babylonia, Gaul) and
# bare continents stay unresolved on purpose: no modern country is honest there.
COUNTRY_LAST_TOKEN = {
    "franca": "French", "francia": "French", "francaise": "French",
    "frankrike": "French", "normandie": "French", "normandy": "French",
    "bretagne": "French", "brittany": "French",
    "espanha": "Spanish", "espagne": "Spanish", "spanien": "Spanish",
    "italie": "Italian", "italien": "Italian",
    "grece": "Greek", "grecia": "Greek", "griechenland": "Greek",
    "turkiye": "Turkish", "turquia": "Turkish", "turquie": "Turkish",
    "portuguesa": "Portuguese",
    "duitsland": "German",
    "niederlande": "Dutch", "holanda": "Dutch",
    "noruega": "Norwegian", "dinamarca": "Danish", "danemark": "Danish",
    "suecia": "Swedish", "rusia": "Russian", "russland": "Russian",
    "hungria": "Hungarian", "polonia": "Polish",
    "irlanda": "Irish", "escocia": "Scottish",
    "wessex": "English", "angleterre": "English",
    "royaume-uni": "British (unspecified)", "reino unido": "British (unspecified)",
    "china": "Chinese",
    "israel": "Israeli", "palestine": "Palestinian", "палестина": "Palestinian",
    "egypt": "Egyptian", "egipto": "Egyptian", "egito": "Egyptian",
    "iraq": "Iraqi", "iraque": "Iraqi", "irak": "Iraqi",
    "armenia": "Armenian", "india": "Indian", "iran": "Iranian",
    "saudi arabia": "Saudi", "arabia saudita": "Saudi",
    "syria": "Syrian", "syrie": "Syrian", "siria": "Syrian",
    "tunisia": "Tunisian", "ethiopia": "Ethiopian", "malta": "Maltese",
    # Plain "Georgia" never gets here (the US scan claims it first); only the
    # accented "Geórgia" does, which folds to "georgia".
    "republic of georgia": "Georgian", "georgia": "Georgian", "albania": "Albanian",
    "mongolia": "Mongolian", "yemen": "Yemeni",
    "azerbaijan": "Azerbaijani", "libya": "Libyan", "libia": "Libyan",
    "pakistan": "Pakistani", "afghanistan": "Afghan", "algeria": "Algerian",
    "belarus": "Belarusian", "hviderusland": "Belarusian", "wit-rusland": "Belarusian",
    "nepal": "Nepali", "korea": "Korean", "south korea": "Korean", "jordan": "Jordanian",
    "cyprus": "Cypriot", "chypre": "Cypriot", "morocco": "Moroccan", "marrocos": "Moroccan",
    "lebanon": "Lebanese", "libano": "Lebanese", "north macedonia": "Macedonian",
}


def _fold(s):
    """Lowercase and strip diacritics, so "Österreich"/"Magyarország" meet the
    ASCII rule keys. ß has no Unicode decomposition, so it's mapped by hand."""
    s = unicodedata.normalize("NFKD", s.lower().replace("ß", "ss"))
    return "".join(c for c in s if not unicodedata.combining(c))


# NATIONALITY_RULES with folded keys, built once (infer_nationality runs per person).
_RULES_FOLDED = [([_fold(kw) for kw in kws], label) for kws, label in NATIONALITY_RULES]

# "New World" pass-through: the immigrant-origin model keeps climbing UP through
# these and stops at the first ancestor born OUTSIDE this set (the immigrant).
NEW_WORLD_LABELS = {"American (USA)", "Canadian"}


def infer_nationality(place):
    """Return (label, resolved_bool). resolved=False means 'needs review'.

    Strategy (first match wins): modern US -> colonial North America (the New
    World) -> country rules -> last-token abbreviation -> bare UK -> unresolved.
    Country rules match either a whole comma-token OR a substring of the
    normalized string, so comma-free strings ("Kent England") and inline foreign
    names ("..., Inglaterra") resolve; the US/colonial scans run first so the
    homonyms they own ("New England", "New Jersey") can't be miscredited abroad.
    """
    if not place or not place.strip():
        return None, False
    # Tokenize on commas; strip wrapper punctuation (<>, (), [], quotes, trailing
    # dots) and collapse internal whitespace so "<Leeds, Yorks., Eng.>" tokenizes
    # cleanly to ["leeds", "yorks", "eng"].
    tokens = []
    for raw in place.split(","):
        t = re.sub(r"\s+", " ", raw.strip().strip("<>()[]{}\"'. ").strip()).lower()
        if t:
            tokens.append(t)
    tokenset = set(tokens)
    last = tokens[-1] if tokens else ""
    placenorm = re.sub(r"\s+", " ", place.strip().strip("<>()[]{}\"' ").lower())

    # 1) Modern US FIRST -- beats "England, Arkansas", "Sweden, Utah", and the
    #    colonial homonyms ("New England", colony names) checked next.
    if last in US_COUNTRY or (tokenset & US_STATES) or last in US_STATE_ABBREV:
        return "American (USA)", True

    # 2) Colonial North America = the New World, not an Old-World origin. Canada
    #    first so "British North America" isn't eaten by the US "british america".
    for kw in CANADA_COLONIAL:
        if kw in placenorm:
            return "Canadian", True
    for kw in US_COLONIAL:
        if kw in placenorm:
            return "American (USA)", True

    # New South Wales is Australian -- guard before the "wales" rule below.
    if "new south wales" in placenorm:
        return "Australian", True

    # The Old-World steps match diacritic-folded text ("Österreich" meets
    # "osterreich"). Not folded above: "Geórgia" (the country) would fold into
    # the US state. The unresolved hint at the end keeps the original spelling.
    tokenset = {_fold(t) for t in tokens}
    last = _fold(last)
    placenorm = _fold(placenorm)

    # 3) Constituent nations / countries, ordered (token OR substring match).
    for keywords, label in _RULES_FOLDED:
        for kw in keywords:
            if kw in tokenset or kw in placenorm:
                return label, True

    # 4) Last-token abbreviation ("of Leeds, Yorks., Eng.") or country name
    #    ("Bruxelles, België").
    if last in COUNTRY_ABBREV:
        return COUNTRY_ABBREV[last], True
    if last in COUNTRY_LAST_TOKEN:
        return COUNTRY_LAST_TOKEN[last], True

    # 5) Bare UK with no constituent nation.
    if tokenset & UK_GENERIC or last in UK_GENERIC:
        return "British (unspecified)", True

    # 6) Unresolved -- surface for manual mapping. Use last token as a hint.
    return tokens[-1].title() if tokens else None, False


# A Jev place->country answer (person["ai_origin"], attached by resolve_places for
# places the rules can't map) counts as resolved at or above this confidence --
# 95% agreed with the rules there in the eval. Below it, it's display-only.
AI_ACCEPT = 0.9


def origin_detail(person):
    """origin_of plus a 4th value: True when the label came from the AI answer.
    A wife whose birthplace was copied from her husband's record
    (parse_gedcom.mark_unnamed_wives) has no documented origin of her own."""
    if person.get("place_copied"):
        return None, False, None, False
    for key in ("birth_place", "christening_place"):
        place = person.get(key)
        if place:
            label, resolved = infer_nationality(place)
            if label is not None:
                ai = person.get("ai_origin")
                if not resolved and ai and ai["confidence"] >= AI_ACCEPT:
                    return ai["label"], True, place, True
                return label, resolved, place, False
    return None, False, None, False


def origin_of(person):
    """Best birthplace-origin for a person: birth -> christening -> none.

    Returns (label, resolved, place_used). Death/burial intentionally excluded.
    Rules always win; a confident AI answer only fills a place they can't map.
    """
    return origin_detail(person)[:3]


# ---------------------------------------------------------------------------
# Weighted (DNA-style) model
# ---------------------------------------------------------------------------

def parent_slots(person):
    """Selected (father, mother), retaining empty slots and legacy records."""
    if "father_xref" in person or "mother_xref" in person:
        return person.get("father_xref"), person.get("mother_xref")
    parents = (person.get("parent_xrefs") or [])[:2]
    return tuple(parents + [None] * (2 - len(parents)))


def _ancestor_weights(people_by_xref, root_xref, absorbs):
    """Total weight arriving at each reachable ancestor, computed ONCE per node
    (O(n + edges)) instead of once per root->ancestor PATH.

    Weight starts at 1.0 on the root and halves to each of the up-to-two
    biological parent slots. ``absorbs(person)`` returning True marks a node that
    keeps its weight and passes nothing upward (the immigrant model's "first
    foreign-born ancestor" sink).

    Returns (W, processed, cut):
      W[xref]       total weight that reached that node,
      processed     every reachable node, in topological order,
      cut           (child, parent) edges dropped because the parent is also the
                    child's descendant (a pedigree cycle -- bad data). Only that
                    one edge is cut, so the rest of the line above still resolves;
                    the caller books the child's half-share on it as untraced.

    This replaces the old recursive path-walk, which is exponential on a
    pedigree-collapsed tree: an ancestor reachable by K distinct paths from the
    root was recomputed K times, and K explodes in the deep shared-tree tail
    (a single mid-tree person could spawn a multi-hour walk).
    """
    from collections import deque

    def parents_of(x):
        person = people_by_xref.get(x)
        if person is None or absorbs(person):
            return []                 # missing person or sink -> propagates to nobody
        return [p for p in parent_slots(person) if p in people_by_xref]

    # Iterative DFS from the root. An edge to a node still on the DFS path closes
    # a loop: cut exactly that edge (what the old path-walk did) and keep the rest,
    # leaving a DAG. Recursion would overflow on 150-generation lines.
    kept = defaultdict(list)          # xref -> in-tree parents it feeds
    child_count = defaultdict(int)    # how many kept edges feed each node
    cut = []
    on_path = {root_xref}
    stack = [(root_xref, iter(parents_of(root_xref)))]
    while stack:
        x, it = stack[-1]
        p = next(it, None)
        if p is None:
            stack.pop()
            on_path.discard(x)
        elif p in on_path:
            cut.append((x, p))
        else:
            kept[x].append(p)
            child_count[p] += 1
            if child_count[p] == 1:   # first visit
                on_path.add(p)
                stack.append((p, iter(parents_of(p))))

    # Topological (Kahn) propagation: a node settles once every child has fed it.
    W = defaultdict(float)
    W[root_xref] = 1.0
    queue = deque([root_xref])        # the root is the only in-degree-0 source
    processed = []
    while queue:
        n = queue.popleft()
        processed.append(n)
        half = W[n] / 2.0
        for p in kept[n]:
            W[p] += half
            child_count[p] -= 1
            if child_count[p] == 0:
                queue.append(p)
    return W, processed, cut


def weighted_origins(people_by_xref, root_xref):
    weights = defaultdict(float)
    untraced = 0.0
    unresolved = defaultdict(float)   # place string -> weight stuck there

    W, processed, cut = _ancestor_weights(
        people_by_xref, root_xref, lambda person: False)

    for n in processed:
        person = people_by_xref[n]
        w = W[n]
        parents = [p for p in parent_slots(person) if p]
        if not parents:                       # LEAF -> assign its nationality
            label, resolved, _place = origin_of(person)
            if label is not None and resolved:
                weights[label] += w
            else:
                untraced += w
                if person.get("birth_place"):
                    unresolved[person["birth_place"]] += w
        else:
            # Weight to in-tree parents already flowed into their W. Every slot
            # that is absent or points outside the tree is a half-weight dead-end
            # -> untraced (exactly the old per-parent walk, minus the recursion).
            in_tree = sum(1 for p in parents if p in people_by_xref)
            untraced += (w / 2.0) * (2 - in_tree)

    for child, _p in cut:                     # pedigree cycle (bad data): only the
        untraced += W[child] / 2.0            # looping parent slot is lost
    total = sum(weights.values()) + untraced
    return weights, untraced, total, [p for _c, p in cut], dict(unresolved)


# ---------------------------------------------------------------------------
# Immigrant-origin model (climb each line to the FIRST non-US/Canada ancestor)
# ---------------------------------------------------------------------------

def immigrant_origins(people_by_xref, root_xref):
    """Each line is climbed until the first ancestor born OUTSIDE the US/Canada.

    That immigrant's nationality gets (1/2)^generation of weight; the line then
    stops (a Danish grandparent makes that quarter Danish regardless of his own
    parents). Lines that stay US/Canada-born to a dead-end -- or whose immigrant
    has an unmapped birthplace -- land in 'untraced' (origin not yet identified).
    """
    origins = defaultdict(float)
    untraced = 0.0
    unresolved = defaultdict(float)

    def is_immigrant(person):
        label, resolved, _place = origin_of(person)
        return resolved and label is not None and label not in NEW_WORLD_LABELS

    W, processed, cut = _ancestor_weights(people_by_xref, root_xref, is_immigrant)

    for n in processed:
        person = people_by_xref[n]
        w = W[n]
        label, resolved, _place = origin_of(person)
        # Found the immigrant: born outside the New World, place we can name.
        if resolved and label is not None and label not in NEW_WORLD_LABELS:
            origins[label] += w
            continue
        # Record an unmapped foreign-looking place so we can classify it later
        # (the weight still climbed -- _ancestor_weights propagated through here).
        if label is not None and not resolved and person.get("birth_place"):
            unresolved[person["birth_place"]] += w
        # US/Canada-born OR unknown birthplace: weight kept climbing to parents.
        parents = [p for p in parent_slots(person) if p]
        if not parents:                      # dead-end, never left the New World
            untraced += w
        else:
            in_tree = sum(1 for p in parents if p in people_by_xref)
            untraced += (w / 2.0) * (2 - in_tree)

    for child, _p in cut:
        untraced += W[child] / 2.0
    total = sum(origins.values()) + untraced
    return origins, untraced, total, [p for _c, p in cut], dict(unresolved)


# ---------------------------------------------------------------------------
# Headcount model
# ---------------------------------------------------------------------------

def headcount_origins(people, root_xref):
    counts = defaultdict(int)
    unresolved = defaultdict(int)
    no_birthplace = 0
    considered = 0
    for p in people:
        if p["xref"] == root_xref:
            continue
        label, resolved, _ = origin_of(p)
        if label is None:
            no_birthplace += 1
            continue
        considered += 1
        if resolved:
            counts[label] += 1
        else:
            unresolved[p.get("birth_place") or label] += 1
    return dict(counts), dict(unresolved), considered, no_birthplace


# ---------------------------------------------------------------------------
# Map (self-contained Leaflet HTML)
# ---------------------------------------------------------------------------

PALETTE = [
    "#e6194B", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
    "#f032e6", "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9A6324",
    "#800000", "#aaffc3", "#808000", "#000075", "#a9a9a9", "#ffe119",
]


# Demonym label -> ISO3, to join the data to the country polygons.
# UK constituents merge to GBR on the filled map (pins/bars keep the detail).
NATION_TO_ISO = {
    "American (USA)": "USA", "Canadian": "CAN", "Mexican": "MEX",
    "English": "GBR", "Scottish": "GBR", "Welsh": "GBR",
    "Northern Irish": "GBR", "British (unspecified)": "GBR",
    "Channel Islander": "GBR", "Manx": "IMN", "Irish": "IRL",
    "Danish": "DNK", "Norwegian": "NOR", "Swedish": "SWE",
    "Finnish": "FIN", "Icelandic": "ISL",
    "German": "DEU", "French": "FRA", "Dutch": "NLD", "Belgian": "BEL",
    "Swiss": "CHE", "Austrian": "AUT", "Italian": "ITA", "Spanish": "ESP",
    "Portuguese": "PRT", "Polish": "POL", "Czech": "CZE", "Hungarian": "HUN",
    "Russian": "RUS", "Australian": "AUS", "New Zealander": "NZL",
    "South African": "ZAF",
    "Greek": "GRC", "Romanian": "ROU", "Bulgarian": "BGR", "Serbian": "SRB",
    "Croatian": "HRV", "Slovenian": "SVN", "Slovak": "SVK", "Ukrainian": "UKR",
    "Lithuanian": "LTU", "Latvian": "LVA", "Estonian": "EST",
    "Luxembourgish": "LUX", "Liechtensteiner": "LIE", "Turkish": "TUR",
    "Chinese": "CHN", "Israeli": "ISR", "Palestinian": "PSE", "Egyptian": "EGY",
    "Iraqi": "IRQ", "Armenian": "ARM", "Indian": "IND", "Iranian": "IRN",
    "Saudi": "SAU", "Syrian": "SYR", "Tunisian": "TUN", "Ethiopian": "ETH",
    "Maltese": "MLT", "Georgian": "GEO", "Albanian": "ALB", "Mongolian": "MNG",
    "Yemeni": "YEM", "Azerbaijani": "AZE", "Libyan": "LBY", "Pakistani": "PAK",
    "Afghan": "AFG", "Algerian": "DZA", "Belarusian": "BLR", "Nepali": "NPL",
    "Korean": "KOR", "Jordanian": "JOR", "Cypriot": "CYP", "Moroccan": "MAR",
    "Lebanese": "LBN", "Macedonian": "MKD",
}


def country_aggregates(people, root_xref, imm_weights, imm_total, deep_weights, deep_total):
    """Aggregate all three models to ISO3 codes for the choropleth join."""
    counts = defaultdict(int)
    for p in people:
        if p["xref"] == root_xref:
            continue
        label, resolved, _ = origin_of(p)
        if label and resolved:
            iso = NATION_TO_ISO.get(label)
            if iso:
                counts[iso] += 1
    immw = defaultdict(float)
    if imm_total:
        for label, w in imm_weights.items():
            iso = NATION_TO_ISO.get(label)
            if iso:
                immw[iso] += 100.0 * w / imm_total
    deepw = defaultdict(float)
    if deep_total:
        for label, w in deep_weights.items():
            iso = NATION_TO_ISO.get(label)
            if iso:
                deepw[iso] += 100.0 * w / deep_total
    data = {}
    for iso in set(counts) | set(immw) | set(deepw):
        data[iso] = {"count": counts.get(iso, 0),
                     "immw": round(immw.get(iso, 0.0), 2),
                     "deepw": round(deepw.get(iso, 0.0), 2)}
    return data


def jitter(value, seed, scale=0.012):
    """Deterministic small offset so co-located ancestors don't fully overlap."""
    h = (hash(seed) % 1000) / 1000.0 - 0.5
    return value + h * scale * 2


def valid_coord(lat, lon):
    """True only for a usable, in-range, non-null-island coordinate.

    Guards against missing values, out-of-range junk, and the (0, 0) point that
    bad geocoders emit -- any of which would otherwise drop a phantom pin in the
    Gulf of Guinea or throw off fitBounds.
    """
    return (lat is not None and lon is not None
            and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0
            and not (lat == 0 and lon == 0))


def branch_tags(people):
    """Tag each direct-line ancestor to a gen-1 branch and a gen-2 grandparent.

    Returns (branch_of, gp_of, root_xref) where:
      branch_of[xref] = "P" (father's side) or "M" (mother's side)
      gp_of[xref]     = "FF"|"FM"|"MF"|"MM" (paternal/maternal grand-father/mother)

    Assignment follows the selected biological father and mother slots,
    first-path-wins via breadth-first search from the root. This mirrors the
    weighted / immigrant origin models exactly, so the per-branch counts line up
    with them; and because pedigree collapse means one ancestor can sit on more
    than one line, a shared ancestor is tagged by whichever side's BFS reached
    them first (counts are therefore approximate, by design).

    Ancestors reachable ONLY through extra (3rd+) parent records -- the
    FamilySearch over-attachment artifacts -- are deliberately left untagged so
    callers can surface them as their own bucket instead of silently dropping or
    misattributing them.
    """
    direct = {p["xref"]: p for p in people if p.get("on_direct_line")}
    root = next((p for p in people if p.get("generation") == 0), None)
    branch_of, gp_of = {}, {}
    if root is None:
        return branch_of, gp_of, None
    seen = {root["xref"]}
    q = deque()
    for slot, par in enumerate(parent_slots(root)):
        if par in direct and par not in seen:
            seen.add(par)
            branch_of[par] = "P" if slot == 0 else "M"
            q.append(par)
    while q:
        x = q.popleft()
        side = branch_of[x]               # "P"/"M" -- always set for queued nodes
        gp = gp_of.get(x, "")             # "" until we pass the gen-1 parents
        for slot, par in enumerate(parent_slots(direct[x])):
            if par not in direct or par in seen:
                continue
            seen.add(par)
            branch_of[par] = side
            # x is a gen-1 parent exactly when gp is still "": its parents are the
            # gen-2 grandparents and get a fresh code; everyone deeper inherits.
            gp_of[par] = gp or (("F" if side == "P" else "M") + ("F" if slot == 0 else "M"))
            q.append(par)
    return branch_of, gp_of, root["xref"]


def pedigree_collapse(people):
    """Distinguish GENUINE pedigree collapse from data-quality over-attachment.

    Returns (collapse_xrefs, couples, over_attached) where:
      collapse_xrefs : set of distinct selected parents
                       of >= 2 distinct direct-line children -- i.e. downstream
                       cousins married, so this ancestor genuinely sits on more
                       than one of your lines. Counting one person once across
                       many positions UNDER-fills the tree; it can never push a
                       generation's headcount past 2^g.
      couples        : [((father_xref, mother_xref), n_lines), ...] sorted by
                       n_lines desc -- the convergence couples behind the above.
      over_attached  : list of direct-line people with > 2 parent_xrefs --
                       un-merged FamilySearch duplicates. These EXTRA parent
                       records are what inject surplus slots and make a
                       generation's known count exceed 2^g. A separate, opposite
                       phenomenon from genuine collapse.
    """
    direct = {p["xref"]: p for p in people if p.get("on_direct_line")}
    kids = defaultdict(set)        # parent xref -> distinct direct children
    couple_kids = defaultdict(set)  # (father, mother) -> distinct direct children
    for x, p in direct.items():
        slots = parent_slots(p)
        for par in slots:
            if par in direct:
                kids[par].add(x)
        if len(slots) == 2 and slots[0] in direct and slots[1] in direct:
            couple_kids[(slots[0], slots[1])].add(x)
    collapse_xrefs = {par for par, ch in kids.items() if len(ch) >= 2}
    couples = sorted(
        ((c, len(ch)) for c, ch in couple_kids.items() if len(ch) >= 2),
        key=lambda ck: (-ck[1], ck[0]))
    over_attached = [p for p in direct.values()
                     if len(p.get("parent_xrefs") or []) > 2]
    return collapse_xrefs, couples, over_attached


def dna_lines(people):
    """Trace the two strictly-single-sex direct lines from the root.

    Patrilineal (Y-DNA path): father's father's father's ... -- always parent
    slot 0. Matrilineal (mtDNA path): mother's mother's mother's ... -- always
    parent slot 1. These are the lines a Y-chromosome or mitochondrial DNA test
    actually follows.

    Returns (dna_of, y_line, mt_line):
      dna_of[xref] = "Y", "mt", or "Ymt" (the last only if pedigree collapse
                     somehow lands one person on both single-sex lines)
      y_line / mt_line = ordered person dicts, closest ancestor first.

    NB: with Scandinavian -sen patronymics the SURNAME changes almost every
    generation up the male line, so the surname is not a proxy for the Y line --
    this follows the biological father-chain regardless of surname.
    """
    by = {p["xref"]: p for p in people}
    root = next((p for p in people if p.get("generation") == 0), None)
    dna_of = {}
    if root is None:
        return dna_of, [], []

    def walk(slot):
        line, cur, seen = [], root, set()
        while cur is not None:
            slots = parent_slots(cur)
            nxt = slots[slot]
            if nxt not in by or nxt in seen:
                break
            seen.add(nxt)
            cur = by[nxt]
            line.append(cur)
        return line

    y_line, mt_line = walk(0), walk(1)
    for p in y_line:
        dna_of[p["xref"]] = "Y"
    for p in mt_line:
        dna_of[p["xref"]] = dna_of.get(p["xref"], "") + "mt"
    return dna_of, y_line, mt_line


# ---------------------------------------------------------------------------
# Settlement region inference (for the migration Sankey)
# ---------------------------------------------------------------------------

# Trailing US postal abbreviation -> modern state name. (US_STATE_ABBREV above is
# only a membership set; here we need the actual name to label a Sankey node.)
ABBREV_TO_STATE = {
    "az": "Arizona", "ar": "Arkansas", "ca": "California", "ct": "Connecticut",
    "fl": "Florida", "ga": "Georgia", "ia": "Iowa", "il": "Illinois",
    "ks": "Kansas", "ky": "Kentucky", "la": "Louisiana", "ma": "Massachusetts",
    "md": "Maryland", "mi": "Michigan", "mn": "Minnesota", "mo": "Missouri",
    "ms": "Mississippi", "mt": "Montana", "nc": "North Carolina",
    "nd": "North Dakota", "ne": "Nebraska", "nh": "New Hampshire",
    "nj": "New Jersey", "nm": "New Mexico", "nv": "Nevada", "ny": "New York",
    "oh": "Ohio", "pa": "Pennsylvania", "ri": "Rhode Island",
    "sc": "South Carolina", "sd": "South Dakota", "tn": "Tennessee",
    "tx": "Texas", "ut": "Utah", "va": "Virginia", "vt": "Vermont",
    "wa": "Washington", "wi": "Wisconsin", "wv": "West Virginia", "wy": "Wyoming",
}
# Colonial-era region name (substring of the normalized place) -> modern state.
# Ordered: more specific strings first so "new york colony" wins before a bare
# "york" county could mislead. Lets the New England Puritan settlements resolve
# to Massachusetts/Connecticut instead of a vague "colonial America".
COLONIAL_TO_STATE = [
    ("massachusetts bay", "Massachusetts"), ("province of massachusetts", "Massachusetts"),
    ("plymouth colony", "Massachusetts"), ("new plymouth", "Massachusetts"),
    ("connecticut colony", "Connecticut"), ("colony of connecticut", "Connecticut"),
    ("new haven", "Connecticut"),
    ("rhode island colony", "Rhode Island"), ("colony of rhode island", "Rhode Island"),
    ("new netherland", "New York"), ("new amsterdam", "New York"),
    ("new york colony", "New York"), ("province of new york", "New York"),
    ("new sweden", "Delaware"),
    ("province of pennsylvania", "Pennsylvania"), ("colony of pennsylvania", "Pennsylvania"),
    ("province of maine", "Maine"),
    ("province of new hampshire", "New Hampshire"),
    ("colony of new jersey", "New Jersey"), ("province of new jersey", "New Jersey"),
    ("east jersey", "New Jersey"), ("west jersey", "New Jersey"),
    ("colony of virginia", "Virginia"), ("virginia colony", "Virginia"),
    ("province of maryland", "Maryland"),
    ("carolina colony", "North Carolina"), ("province of carolina", "North Carolina"),
]


# US state names longest-first (then alphabetical) for the substring fallback in
# settlement_of. Iterating the US_STATES *set* directly is non-deterministic
# (per-process string-hash order), so a messy place naming two states (e.g.
# "...Province of Maine, Massachusetts Bay...") would flip between runs. Fixed
# longest-first order is deterministic AND prefers the specific name, so e.g.
# "West Virginia" wins over the "Virginia" it contains.
_US_STATES_BY_LEN = tuple(sorted(US_STATES, key=lambda s: (-len(s), s)))


def settlement_of(person):
    """Best modern US-state (or Canada) settlement label for a New-World birth.

    Returns a short region label ("Massachusetts", "Utah", "Canada") or None.
    Resolves clean state tokens, state-name substrings, colonial region names
    (so "Massachusetts Bay Colony" -> Massachusetts), and trailing postal codes.
    Used to label the destination side of the migration Sankey and the per-state
    breakdown/filter; deterministic so those counts don't drift between runs.
    """
    place = person.get("birth_place") or person.get("christening_place")
    if not place:
        return None
    norm = re.sub(r"\s+", " ", place.lower())
    toks = []
    for raw in place.split(","):
        t = raw.strip().strip("<>()[]{}\"'. ").lower()
        if t:
            toks.append(t)
    # 1) clean state token
    for t in toks:
        if t in US_STATES:
            return t.title()
    # 2) state-name substring ("Massachusetts Bay Colony"), longest match first
    #    (deterministic; "West Virginia" beats the "Virginia" inside it)
    for st in _US_STATES_BY_LEN:
        if st in norm:
            return st.title()
    # 3) colonial region -> modern state
    for kw, st in COLONIAL_TO_STATE:
        if kw in norm:
            return st
    # 4) trailing postal abbreviation
    if toks and toks[-1] in ABBREV_TO_STATE:
        return ABBREV_TO_STATE[toks[-1]]
    # 5) Canada (broad) -- keep the Sankey honest about cross-border settlement
    for kw in CANADA_COLONIAL:
        if kw in norm:
            return "Canada"
    if "canada" in norm:
        return "Canada"
    return None


def pct_pairs(counts_dict, total):
    if total <= 0:
        return []
    pairs = [(k, 100.0 * v / total) for k, v in counts_dict.items()]
    pairs.sort(key=lambda kv: kv[1], reverse=True)
    return pairs


def main():
    ap = argparse.ArgumentParser(description="Analyze ancestral origins from ancestors.json")
    ap.add_argument("--in", dest="infile", default="output/ancestors.json")
    ap.add_argument("--outdir", default="output")
    args = ap.parse_args()

    if not Path(args.infile).exists():
        sys.exit(f"Not found: {args.infile}. Run parse_gedcom.py first.")
    people = json.loads(Path(args.infile).read_text(encoding="utf-8"))
    by_xref = {p["xref"]: p for p in people}

    roots = [p for p in people if p.get("generation") == 0]
    if not roots:
        sys.exit("No root (generation 0) person found.")
    root_xref = roots[0]["xref"]

    # immigrant origin (headline model): first non-US/Canada ancestor per line
    imm, imm_untraced, imm_total, imm_cycles, unres_i = immigrant_origins(by_xref, root_xref)
    immigrant_pct = pct_pairs(imm, imm_total)
    immigrant_untraced_pct = 100.0 * imm_untraced / imm_total if imm_total else 0.0

    # weighted (deepest-known origin)
    weights, untraced, total, cycles, unres_w = weighted_origins(by_xref, root_xref)
    weighted_pct = pct_pairs(weights, total)
    untraced_pct = 100.0 * untraced / total if total else 0.0

    # headcount
    counts, unres_h, considered, no_bp = headcount_origins(people, root_xref)
    head_pct = pct_pairs(counts, considered)

    # per-country aggregates (ISO3) for the choropleth
    country_data = country_aggregates(people, root_xref, imm, imm_total, weights, total)

    # metadata for the map
    direct = [p for p in people if p.get("on_direct_line")]
    meta = {
        "root": roots[0]["name"],
        "n_people": len(people),
        "n_direct": len(direct),
        "max_gen": max((p["generation"] for p in direct if p["generation"] is not None), default=0),
        "n_coords": sum(1 for p in people if valid_coord(p.get("birth_lat"), p.get("birth_lon"))),
        "total_sources": sum(p.get("source_count", 0) for p in people),
        "total_memories": sum(p.get("memory_count", 0) for p in people),
    }

    # ---- console report ----
    print(f"\n=== ANCESTRAL ORIGINS for {meta['root']} ===")
    print(f"{meta['n_people']} people, {meta['n_direct']} on direct line, to generation {meta['max_gen']}")
    print(f"\n--- IMMIGRANT ORIGIN (first non-US/Canada ancestor per line), total={imm_total:.4f} ---")
    for name, p in immigrant_pct:
        print(f"  {p:5.1f}%  {name}")
    print(f"  {immigrant_untraced_pct:5.1f}%  (origin not yet identified -- traced only to N. America)")
    print(f"\n--- DEEPEST-KNOWN ORIGIN (weighted), total weight={total:.4f} ---")
    for name, p in weighted_pct:
        print(f"  {p:5.1f}%  {name}")
    print(f"  {untraced_pct:5.1f}%  (untraced / unknown)")
    print(f"\n--- HEADCOUNT ({considered} ancestors with known birthplace) ---")
    for name, p in head_pct:
        print(f"  {p:5.1f}%  {name}")
    if no_bp:
        print(f"  ({no_bp} ancestors had no usable birthplace)")
    if cycles:
        print(f"\n[!] Pedigree cycles detected at: {sorted(set(cycles))}")
    # Aggregate unmapped birthplaces with an impact signal so the ones worth
    # writing rules for float to the top: headcount (# distinct ancestors) plus
    # the immigrant-model weight (% of "you") that the place is stranding.
    unresolved_rows = {}

    def _u(place):
        return unresolved_rows.setdefault(place, {"count": 0, "imm_pct": 0.0})

    for place, n in unres_h.items():
        _u(place)["count"] += n
    if imm_total:
        for place, w in unres_i.items():
            _u(place)["imm_pct"] += 100.0 * w / imm_total
    for place in unres_w:                  # surface deepest-model-only places too
        _u(place)
    unresolved_ranked = sorted(
        unresolved_rows.items(),
        key=lambda kv: (-kv[1]["imm_pct"], -kv[1]["count"], kv[0]))
    if unresolved_ranked:
        print(f"\n[review] {len(unresolved_ranked)} birthplaces could not be mapped to a nationality")
        print("         (ranked by impact -- add the top ones to NATIONALITY_RULES):")
        for place, r in unresolved_ranked:
            imp = f"{r['imm_pct']:5.1f}% wt" if r["imm_pct"] >= 0.05 else "     -- "
            print(f"    {r['count']:>3}x {imp}  {place}")

    # ---- files ----
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "origins.json").write_text(json.dumps({
        "meta": meta,
        "immigrant_origin_pct": immigrant_pct,
        "immigrant_origin_untraced_pct": immigrant_untraced_pct,
        "deepest_known_pct": weighted_pct,
        "deepest_known_untraced_pct": untraced_pct,
        "headcount_pct": head_pct,
        "cycles": sorted(set(cycles) | set(imm_cycles)),
        "unresolved_places": [
            {"place": p, "count": r["count"], "immigrant_pct": round(r["imm_pct"], 3)}
            for p, r in unresolved_ranked],
        "country_data": country_data,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {outdir}/origins.json")


if __name__ == "__main__":
    main()
