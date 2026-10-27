"""
infer_origin.py -- ESTIMATE an ancestor's ethnic origin from a surname.

Phase 1 of origin inference: the SURNAME signal. A surname's spelling and
affixes hint at an origin -- ``Mc``/``O'`` (Gaelic), ``-sen`` (Scandinavian),
``van``/``von`` (Dutch/German), ``-ski`` (Polish), ``-ez`` (Spanish), and so on.

This is HEURISTIC, not fact. Surnames are noisy evidence of ancestry:
anglicization (Mueller -> Miller), marriage, adoption, and occupational or
toponymic names that recur across borders all break the link between a name and
a bloodline. So:

  * confidence is capped at "medium" -- never "high" (a surname is never proof
    of an *individual's* origin);
  * every guess carries a one-line rationale naming the rule that fired;
  * genuinely ambiguous high-frequency names (Jones/Williams -- Welsh or
    English; Smith -- English or an anglicized Schmidt) are DELIBERATELY left
    out of the dictionary, so we return an honest "unknown" rather than a
    confident wrong answer. Missing a guess is cheaper than a false one.

Labels stay close to ``analyze_origins.NATIONALITY_RULES`` demonyms so the
estimate reads consistently with the rest of the app; where a surname truly
can't choose between two peoples (Gaelic -> Scottish *or* Irish) the label says
so rather than feigning precision.

Returns ``(label, confidence, rationale)`` -- the same contract as
``trace_deadends.likely_origin`` -- so the signals slot together in the UI
(and, later, in a combine step). ``confidence`` is one of
"medium" / "low" / "none".

Phase 2 adds a SECOND, tree-internal signal (``build_surname_index`` +
``tree_surname_origin``): a dead-end probably shares the origin its
same-surname relatives are *documented* to have. That's stronger than the
global dictionary -- it's this family's actual surname usage, grounded in real
birthplaces -- though same surname is not proof of same family for common
names, so it is still capped at "medium".
"""

from collections import Counter

from . import analyze_origins as ao

# ---------------------------------------------------------------------------
# Curated exact surnames (lowercased) -> (label, confidence, rationale).
# Conservative on purpose: only names that lean clearly toward one origin.
# Most Scandinavian/Spanish patronymics are left to the affix rules below.
# ---------------------------------------------------------------------------
_IRISH = "characteristically Irish surname"
_SCOTTISH = "characteristically Scottish surname"
_WELSH = "distinctively Welsh surname"
_GERMAN = "characteristically German surname"
_ITALIAN = "characteristically Italian surname"

SURNAME_DICT = {
    # --- Irish (non-affix) ---
    **{n: ("Irish", "medium", _IRISH) for n in (
        "murphy", "kelly", "walsh", "byrne", "ryan", "doyle", "gallagher",
        "brennan", "lynch", "nolan", "flynn", "mahoney", "donnelly",
        "sullivan", "healy", "boyle", "duffy", "quinn", "rafferty")},
    # --- Scottish (non-affix) ---
    **{n: ("Scottish", "medium", _SCOTTISH) for n in (
        "campbell", "stewart", "stuart", "fraser", "cameron", "ferguson",
        "wallace", "dunbar", "muir", "gordon", "kerr", "douglas", "hamilton",
        "armstrong", "crawford", "sinclair")},
    # --- Welsh (distinctive only; Jones/Williams/Davies omitted as English-ambiguous) ---
    **{n: ("Welsh", "medium", _WELSH) for n in (
        "lloyd", "morgan", "griffith", "griffiths", "powell", "vaughan",
        "pugh", "rhys", "bevan", "meredith")},
    # --- German ---
    **{n: ("German", "medium", _GERMAN) for n in (
        "muller", "mueller", "müller", "schmidt", "schmitt", "schneider",
        "fischer", "meyer", "meier", "wagner", "becker", "hoffmann", "hofmann",
        "schafer", "schaefer", "schäfer", "koch", "bauer", "richter", "schulz",
        "schultz", "zimmermann", "neumann", "schwarz", "krueger", "krüger",
        "hartmann", "schroeder", "schröder", "weiss", "weiß", "wolf", "klein")},
    # --- Italian (non-affix) ---
    **{n: ("Italian", "medium", _ITALIAN) for n in (
        "rossi", "russo", "ferrari", "esposito", "bianchi", "romano", "ricci",
        "greco", "bruno", "gallo", "conti", "giordano", "rizzo", "lombardi",
        "moretti", "caruso", "marino", "costa")},
    # --- Dutch (non-affix; van* handled by the prefix rules) ---
    "de jong": ("Dutch", "medium", "distinctively Dutch surname"),
    "de vries": ("Dutch", "medium", "distinctively Dutch surname"),
    "de boer": ("Dutch", "medium", "distinctively Dutch surname"),
    "de groot": ("Dutch", "medium", "distinctively Dutch surname"),
    "bakker": ("Dutch", "low", "common Dutch surname"),
    "visser": ("Dutch", "low", "common Dutch surname"),
    "mulder": ("Dutch", "low", "common Dutch surname"),
    # --- Spanish (non -ez) ---
    **{n: ("Spanish", "medium", "characteristically Spanish surname") for n in (
        "garcia", "garcía", "torres", "flores", "rivera", "reyes", "morales",
        "castillo", "romero", "vargas", "mendoza", "ramos")},
    # --- Portuguese (mostly not caught by affixes) ---
    **{n: ("Portuguese", "medium", "characteristically Portuguese surname") for n in (
        "silva", "santos", "ferreira", "pereira", "oliveira", "sousa")},
    # --- English (common; capped LOW -- many recur elsewhere / are anglicizations) ---
    **{n: ("English", "low", "common English surname (also found elsewhere)") for n in (
        "taylor", "baker", "clark", "clarke", "wright", "walker", "turner",
        "cooper", "ward", "cook", "carter", "hughes", "bailey", "fletcher",
        "chapman", "webb", "shaw", "barnes")},
}


# ---------------------------------------------------------------------------
# Affix rules, checked AFTER the dictionary, most-specific first (first match
# wins). Each: (kind, pattern, min_len, label, confidence, rationale).
#   kind     -- "prefix" or "suffix", matched on the cleaned lowercase surname
#   min_len  -- the surname must be at least this long for the rule to fire,
#               so the affix is part of a real name (guards "Macy", "Mason"...)
# ---------------------------------------------------------------------------
AFFIX_RULES = [
    # ---- prefixes ----
    ("prefix", "van der ", 9, "Dutch", "medium", "'van der' is a Dutch toponymic prefix"),
    ("prefix", "van den ", 9, "Dutch", "medium", "'van den' is a Dutch toponymic prefix"),
    ("prefix", "vander", 8, "Dutch", "medium", "'vander' is a Dutch toponymic prefix"),
    ("prefix", "van ", 6, "Dutch", "medium", "'van' is a Dutch/Flemish toponymic prefix"),
    ("prefix", "von der ", 9, "German", "medium", "'von der' is a German nobiliary prefix"),
    ("prefix", "von ", 6, "German", "medium", "'von' is a German nobiliary prefix"),
    ("prefix", "o'", 4, "Irish", "medium", "O'- is an Irish patronymic prefix (\"descendant of\")"),
    ("prefix", "fitz", 6, "Irish (Norman)", "low", "Fitz- is a Norman-Irish patronymic prefix"),
    ("prefix", "mac", 6, "Scottish or Irish", "low", "Mac- is a Gaelic patronymic prefix (Scottish or Irish)"),
    ("prefix", "mc", 5, "Scottish or Irish", "low", "Mc- is a Gaelic patronymic prefix (Scottish or Irish)"),
    ("prefix", "della ", 8, "Italian", "low", "'della' is an Italian toponymic prefix"),
    ("prefix", "di ", 5, "Italian", "low", "'di' is an Italian patronymic prefix"),
    # ---- suffixes (longer / more distinctive first) ----
    ("suffix", "opoulos", 8, "Greek", "medium", "-opoulos is a Greek patronymic suffix"),
    ("suffix", "owicz", 7, "Polish", "medium", "-owicz is a Polish patronymic suffix"),
    ("suffix", "wicz", 6, "Polish", "medium", "-wicz is a Polish patronymic suffix"),
    ("suffix", "czyk", 6, "Polish", "medium", "-czyk is a Polish suffix"),
    ("suffix", "escu", 6, "Romanian", "medium", "-escu is a Romanian patronymic suffix"),
    ("suffix", "akis", 6, "Greek", "medium", "-akis is a Greek (Cretan) patronymic suffix"),
    ("suffix", "sson", 6, "Swedish", "medium", "-sson patronymic is Swedish"),
    ("suffix", "ucci", 6, "Italian", "medium", "-ucci is an Italian suffix"),
    ("suffix", "elli", 6, "Italian", "medium", "-elli is an Italian suffix"),
    ("suffix", "etti", 6, "Italian", "medium", "-etti is an Italian suffix"),
    ("suffix", "ski", 5, "Polish", "medium", "-ski is a Polish adjectival surname suffix"),
    ("suffix", "cki", 5, "Polish", "medium", "-cki is a Polish adjectival surname suffix"),
    ("suffix", "sky", 5, "Polish/Russian", "low", "-sky surname suffix (Polish, Russian or Ashkenazi)"),
    ("suffix", "sen", 5, "Danish or Norwegian", "medium", "-sen patronymic is typically Danish or Norwegian"),
    ("suffix", "ini", 5, "Italian", "low", "-ini is an Italian suffix"),
    ("suffix", "ino", 5, "Italian", "low", "-ino is an Italian suffix"),
    ("suffix", "ić", 5, "Serbian or Croatian", "medium", "-ić is a South-Slavic patronymic suffix"),
    ("suffix", "ič", 5, "Serbian or Croatian", "low", "-ič is a South-Slavic patronymic suffix"),
    ("suffix", "ez", 5, "Spanish", "medium", "-ez patronymic is Spanish"),
    ("suffix", "stein", 7, "German/Ashkenazi", "low", "-stein is a German/Ashkenazi suffix"),
    ("suffix", "baum", 6, "German/Ashkenazi", "low", "-baum is a German/Ashkenazi suffix"),
    ("suffix", "mann", 6, "German", "low", "-mann is a German suffix"),
    ("suffix", "son", 5, "English or Scandinavian", "low",
     "-son patronymic: English, or an anglicized Scandinavian -sen/-sson"),
]


def _clean(surname):
    """Lowercase + trim; keep internal apostrophes/hyphens/spaces for affixes."""
    if not surname:
        return ""
    return surname.strip().lower().strip(".,")


def surname_origin(surname):
    """Estimate an origin from a surname.

    Returns ``(label, confidence, rationale)``. ``confidence`` is "medium",
    "low", or "none" (no usable signal). NEVER "high": a surname alone is not
    proof of an individual's ancestry -- always a hint for research.
    """
    s = _clean(surname)
    if not s:
        return "Unknown", "none", "no surname to reason from"

    if s in SURNAME_DICT:
        return SURNAME_DICT[s]

    for kind, pat, min_len, label, conf, why in AFFIX_RULES:
        if len(s) < min_len:
            continue
        if kind == "prefix" and s.startswith(pat):
            return label, conf, why
        if kind == "suffix" and s.endswith(pat):
            return label, conf, why

    return "Unknown", "none", "surname has no distinctive origin marker"


# ---------------------------------------------------------------------------
# Phase 2: tree-internal surname propagation.
#
# The strongest origin hint for a dead-end is usually inside the same tree: if
# other people who share its surname were *documented* (by their own birthplace)
# as, say, Welsh, the dead-end probably is too. We build the surname->origin
# distribution from people with a resolved OLD-WORLD birthplace nationality
# (New-World labels excluded -- those are what we're trying to look behind), then
# propagate the dominant one. Capped at "medium": same surname is strong evidence
# of the same family in a real pedigree, but not proof for common names.
# ---------------------------------------------------------------------------

# A surname needs at least this many agreeing documented bearers (and this share
# of them) to earn "medium"; otherwise the propagation is "low".
_TREE_MIN_FOR_MEDIUM = 2
_TREE_SHARE_FOR_MEDIUM = 2 / 3


def build_surname_index(people):
    """Map normalized surname -> Counter of DOCUMENTED old-world nationalities
    among tree members with that surname (each from their own birthplace).

    Pass the result to :func:`tree_surname_origin`. Built once per tree.
    """
    idx = {}
    for p in people:
        s = _clean(p.get("surname"))
        if not s:
            continue
        label, resolved, _ = ao.origin_of(p)
        if resolved and label is not None and label not in ao.NEW_WORLD_LABELS:
            idx.setdefault(s, Counter())[label] += 1
    return idx


def tree_surname_origin(surname, index):
    """Estimate origin from same-surname relatives' DOCUMENTED origins.

    Returns ``(label, confidence, rationale)``. "medium" when >= 2 documented
    bearers agree (>= 2/3 share); "low" for a lone bearer or mixed origins;
    "none" when no documented same-surname relative exists in the tree.
    """
    s = _clean(surname)
    counter = index.get(s)
    if not counter:
        return "Unknown", "none", "no documented same-surname relative in your tree"

    total = sum(counter.values())
    label, n = counter.most_common(1)[0]
    share = n / total
    kin = "relative" if n == 1 else "relatives"
    was = "was" if n == 1 else "were"
    why = f"{n} same-surname {kin} in your tree {was} documented as {label}"
    if n >= _TREE_MIN_FOR_MEDIUM and share >= _TREE_SHARE_FOR_MEDIUM:
        return label, "medium", why
    if share < _TREE_SHARE_FOR_MEDIUM:
        why += " (among mixed origins)"
    return label, "low", why


# ---------------------------------------------------------------------------
# Phase 3: combine the independent signals into ONE verdict.
#
# The three signals speak different dialects -- "English (New England)" (place),
# "English or Scandinavian" (surname), "English" (relatives) -- so we reduce each
# label to a set of ethnic tokens and look for consensus by intersection. The
# rule that matters: AGREEMENT across independent signals is the only way to earn
# "high" confidence (beyond a lone signal that was already high, e.g. a strong
# colony prior). Conflicting signals are surfaced, not hidden, and never boosted.
# ---------------------------------------------------------------------------

# Display demonym per ethnic token (the combined-verdict headline).
_DEMONYM = {
    "scots-irish": "Scots-Irish", "english": "English", "scottish": "Scottish",
    "irish": "Irish", "welsh": "Welsh", "german": "German", "dutch": "Dutch",
    "scandinavian": "Scandinavian", "danish": "Danish", "norwegian": "Norwegian",
    "swedish": "Swedish", "french": "French", "italian": "Italian",
    "spanish": "Spanish", "portuguese": "Portuguese", "polish": "Polish",
    "greek": "Greek",
}
# Matched as substrings, most-specific first so "scots-irish" is consumed before
# "irish"/"scottish" can match the remainder.
_TOKENS_ORDERED = [
    "scots-irish", "scandinavian", "portuguese", "norwegian", "english",
    "scottish", "irish", "welsh", "german", "dutch", "danish", "swedish",
    "french", "italian", "spanish", "polish", "greek",
]
_CONF_N = {"none": 0, "low": 1, "medium": 2, "high": 3}
_CONF_S = {0: "none", 1: "low", 2: "medium", 3: "high"}


def _ethnic_tokens(label):
    """The set of ethnic tokens named in a guess label (order-safe extraction)."""
    s = (label or "").lower()
    found = set()
    for tok in _TOKENS_ORDERED:
        if tok in s:
            found.add(tok)
            s = s.replace(tok, " ")  # consume so 'irish' can't re-match 'scots-irish'
    return found


def combine_origin(place, surname, tree):
    """Reconcile the place / surname / relatives signals into one verdict.

    Each argument is a ``(label, confidence, rationale)`` triple (use
    ``(_, "none", _)`` for a signal that didn't fire). Returns::

        {"label", "confidence", "agreement", "rationale": [{basis,label,confidence,why}]}

    ``agreement`` is True when >= 2 independent signals point at the same ethnic
    token. Confidence is boosted only on agreement; a lone signal keeps its own
    level (so a strong colony prior can still read "high" by itself), and signals
    that disagree are reported in ``rationale`` without inflating the verdict.
    """
    named = (("place",) + tuple(place), ("surname",) + tuple(surname), ("relatives",) + tuple(tree))
    active = [(b, l, c, w) for (b, l, c, w) in named if c != "none"]
    breakdown = [{"basis": b, "label": l, "confidence": c, "why": w} for (b, l, c, w) in active]

    if not active:
        return {"label": "Unknown", "confidence": "none", "agreement": False, "rationale": []}
    if len(active) == 1:
        _b, l, c, _w = active[0]
        return {"label": l, "confidence": c, "agreement": False, "rationale": breakdown}

    sig_tokens = [(b, c, _ethnic_tokens(l)) for (b, l, c, _w) in active]
    support = {}  # token -> list of supporter confidences (numeric)
    for b, c, toks in sig_tokens:
        for t in toks:
            support.setdefault(t, []).append(_CONF_N[c])

    best_tok, sup = max(
        support.items(), key=lambda kv: (len(kv[1]), sum(kv[1])), default=(None, []))

    if best_tok is not None and len(sup) >= 2:
        n_sup, others, max_sup = len(sup), len(active) - len(sup), max(sup)
        if n_sup >= 3:
            score = 3                      # corroborated by every signal
        elif others == 0:
            score = min(3, max_sup + 1)    # both active signals agree, none dissent
        else:
            score = max_sup                # 2 agree but a third points elsewhere: hold, don't boost
        return {
            "label": _DEMONYM.get(best_tok, best_tok.title()),
            "confidence": _CONF_S[max(1, min(3, score))],
            "agreement": True,
            "rationale": breakdown,
        }

    # No two signals share a token: report the strongest, flag the disagreement.
    _b, l, c, _w = max(active, key=lambda s: _CONF_N[s[2]])
    return {"label": l, "confidence": c, "agreement": False, "rationale": breakdown}
