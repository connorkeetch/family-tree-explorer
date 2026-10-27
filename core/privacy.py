"""Living-person privacy.

A genealogy tree mixes the long-dead with the recently- or still-living.
FamilySearch forbids *publicly* sharing living persons' data, so we (a) detect
likely-living people and (b) provide a redaction transform for any non-owner /
public view. The owner always sees their own full tree; redaction is applied
wherever data would leave the owner's private view.

"Likely living" = no recorded death AND born within PRESUMED_LIVING_YEARS (the
common genealogy / FamilySearch ~110-year rule). People with no dates at all are
treated as deceased — overwhelmingly true for ancestors, and it avoids
over-redacting distant generations that simply lack a recorded death date.
"""
import datetime

PRESUMED_LIVING_YEARS = 110

_REDACTED_NAME = "Living person"
_REDACT_NULL_FIELDS = (
    "birth_date", "birth_place", "christening_place",
    "death_date", "death_place", "burial_place",
    "birth_lat", "birth_lon",
)


def _year(as_of_year=None):
    return as_of_year if as_of_year is not None else datetime.date.today().year


def is_likely_living(person, as_of_year=None):
    """True if the person has no recorded death and was born < ~110 years ago."""
    if (person.get("death_year") or person.get("death_date")
            or person.get("death_place") or person.get("burial_place")):
        return False
    birth_year = person.get("birth_year")
    if birth_year is None:
        return False
    return (_year(as_of_year) - birth_year) < PRESUMED_LIVING_YEARS


def count_living(people, as_of_year=None):
    y = _year(as_of_year)
    return sum(1 for p in people if is_likely_living(p, y))


def ai_name(person):
    """Names safe to send: placeholder wives can contain a living spouse's name."""
    if not person or is_likely_living(person) or person.get("wife_of"):
        return "unknown"
    return person.get("name") or "unknown"


def redact_people(people, as_of_year=None):
    """Return a COPY with likely-living people's identifying fields removed.

    Hides name, exact birthplace, dates, coordinates, and FamilySearch ID; keeps
    structural fields (xref, parent links, generation, sex, birth_year) so the
    tree shape and aggregate analysis still work. Use for any public / shared
    (non-owner) view. Deceased people are passed through unchanged.
    """
    y = _year(as_of_year)
    out = []
    for p in people:
        if not is_likely_living(p, y):
            out.append(p)
            continue
        r = dict(p)
        r["name"] = _REDACTED_NAME
        r["given"] = ""
        r["surname"] = ""
        r["fs_id"] = None
        for key in _REDACT_NULL_FIELDS:
            if key in r:
                r[key] = None
        r["redacted"] = True
        out.append(r)
    return out
