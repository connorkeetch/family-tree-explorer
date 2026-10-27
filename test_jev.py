"""
test_jev.py -- the Jev client's disk cache and the passes that use it: place
enrichment, parent conflicts and the duplicate finder (no network: _post / ask
are stubbed).

Run:  python test_jev.py
"""
import tempfile
import unittest
from pathlib import Path

from core import analyze_origins as ao
from core.jev import Jev
from core.duplicates import _record, candidates, find_duplicates
from core.parents import ACT, ask_couples, settle
from core.payloads import duplicates_payload
from core.resolve_places import enrich, evaluate, places_by_status


class TestCache(unittest.TestCase):
    def test_repeat_and_reload_hit_the_cache(self):
        path = Path(tempfile.mkdtemp()) / "cache.json"
        calls = []

        def fake_post(body):
            calls.append(body)
            return {"answers": {"q": {"noul": 0.9}}, "usage": {"cost": 0.001}}

        jev = Jev(path)
        jev._post = fake_post
        q = {"q": {"type": "noul", "instructions": "Is this a place?"}}
        self.assertEqual(jev.ask({"birthplace": "Kyiv"}, q), {"q": {"noul": 0.9}})
        jev.ask({"birthplace": "Kyiv"}, q)
        self.assertEqual(len(calls), 1)                 # second ask was cached
        jev.ask({"birthplace": "Lviv"}, q)
        self.assertEqual(len(calls), 2)                 # different state -> new call
        jev.save()

        again = Jev(path)
        again._post = fake_post
        again.ask({"birthplace": "Kyiv"}, q)
        self.assertEqual(len(calls), 2)                 # survives a reload
        self.assertEqual(again.cost, 0.0)


class TestRetry(unittest.TestCase):
    def test_dropped_connection_is_retried(self):
        import http.client, io, json as _json
        from unittest import mock
        replies = [http.client.RemoteDisconnected("closed"),
                   io.BytesIO(_json.dumps({"answers": {"q": {"noul": 1}}}).encode())]

        def urlopen(req, timeout):
            r = replies.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        jev = Jev(Path(tempfile.mkdtemp()) / "c.json")
        jev._key = "test"
        with mock.patch("urllib.request.urlopen", urlopen), mock.patch("time.sleep"):
            self.assertEqual(jev.ask({"s": 1}, {"q": {}}), {"q": {"noul": 1}})
        self.assertEqual(replies, [])

    def test_cloudflare_520_is_retried_but_400_is_not(self):
        import io, json as _json, urllib.error
        from unittest import mock
        err = lambda code: urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"{}"))
        ok = io.BytesIO(_json.dumps({"answers": {"q": {"noul": 1}}}).encode())
        for first, expect_ok in ((err(520), True), (err(400), False)):
            replies = [first, ok]

            def urlopen(req, timeout):
                r = replies.pop(0)
                if isinstance(r, Exception):
                    raise r
                return r

            jev = Jev(Path(tempfile.mkdtemp()) / "c.json")
            jev._key = "test"
            with mock.patch("urllib.request.urlopen", urlopen), mock.patch("time.sleep"):
                if expect_ok:
                    self.assertEqual(jev.ask({"s": 1}, {"q": {}}), {"q": {"noul": 1}})
                else:
                    self.assertRaises(RuntimeError, jev.ask, {"s": 2}, {"q": {}})


class FakeJev:
    """Answers from a {place: (label, confidence)} table; records what was asked."""

    def __init__(self, table):
        self.table, self.asked, self.cost = table, [], 0.0

    def ask(self, state, questions):
        place = state["birthplace"]
        self.asked.append(place)
        label, conf = self.table[place]
        return {"country": {"choice": label, "confidence": conf, "probabilities": {label: conf}}}

    def save(self):
        pass


def person(xref, place, birth_year=1500):
    return {"xref": xref, "birth_place": place, "birth_year": birth_year}


class TestEnrich(unittest.TestCase):
    def test_enrich_then_origin_of(self):
        people = [
            person("@A@", "Rouergue, West Francia"),       # confident -> counted
            person("@B@", "Rouergue, West Francia"),       # same place, asked once
            person("@C@", "Loch Lomond, Eireann"),         # medium -> guess only
            person("@D@", "Europe"),                       # too vague -> nothing
            person("@E@", "Kent, England"),                # rules map it -> not asked
            person("@F@", "Seoul, Hanguk", birth_year=1990),  # likely living -> not sent
        ]
        jev = FakeJev({"Rouergue, West Francia": ("French", 0.99),
                       "Loch Lomond, Eireann": ("Scottish", 0.6),
                       "Europe": ("too vague", 1.0)})
        enrich(people, jev, workers=1)
        self.assertEqual(sorted(jev.asked),
                         ["Europe", "Loch Lomond, Eireann", "Rouergue, West Francia"])
        by = {p["xref"]: p for p in people}
        self.assertEqual(ao.origin_of(by["@A@"])[:2], ("French", True))
        self.assertEqual(ao.origin_of(by["@B@"])[:2], ("French", True))
        self.assertFalse(ao.origin_of(by["@C@"])[1])               # 0.6 isn't counted...
        self.assertEqual(by["@C@"]["ai_origin"]["label"], "Scottish")  # ...but kept to show
        self.assertNotIn("ai_origin", by["@D@"])
        self.assertEqual(ao.origin_of(by["@E@"])[:2], ("English", True))
        self.assertNotIn("ai_origin", by["@F@"])

    def test_rules_beat_a_stale_ai_origin(self):
        p = person("@A@", "Kent, England")
        p["ai_origin"] = {"label": "French", "confidence": 1.0}
        self.assertEqual(ao.origin_of(p)[:2], ("English", True))


class FakeDupJev:
    """Same person iff both records name the same (known) father; the score
    leans on record order, so the both-orders average is observable."""

    cost = 0.0

    def __init__(self):
        self.asked = []

    def ask(self, state, questions):
        a, b = state["record_a"], state["record_b"]
        self.asked.append((a["birthplace"], b["birthplace"]))
        same = a["father"] == b["father"] != "unknown"
        score = (1.8 if a["birthplace"] < b["birthplace"] else 1.4) if same else 0.2
        return {"same": {"score": score}, "parents": {"noul": float(same)}, "place": {"noul": 0.5}}

    def save(self):
        pass


def rec(xref, name, year, sex="M", place=None, father=None, parents=(), couples=()):
    given, surname = name.split(" ")
    return {"xref": xref, "fs_id": xref.strip("@") + "-FID", "name": name, "given": given,
            "surname": surname, "birth_year": year, "sex": sex, "birth_place": place,
            "father_xref": father, "mother_xref": None, "parent_xrefs": list(parents),
            "parent_couples": [{"father_xref": f, "mother_xref": m} for f, m in couples],
            "generation": 3}


class TestDuplicates(unittest.TestCase):
    def setUp(self):
        self.people = [
            rec("@D@", "Tom Hill", 1600),
            rec("@A1@", "John Hill", 1630, place="Kent", father="@D@"),
            rec("@A2@", "John Hill", 1630, place="Surrey", father="@D@"),
            rec("@A3@", "John Hill", 1630, place="York"),
            rec("@C@", "Ann Hill", 1660, parents=("@A1@", "@A2@")),      # claims both
            # a wife recorded under her husband's name -- a couple, not a duplicate
            rec("@H@", "Charles Baker", 1680),
            rec("@W@", "Charles Baker", 1680, sex=""),
            rec("@K@", "Mary Baker", 1710, parents=("@H@", "@W@"), couples=[("@H@", "@W@")]),
            rec("@S@", "Jens Pedersen", 1730),
            rec("@T@", "Jens Pedersen", 1730, sex="F"),                  # different sex
            rec("@L1@", "Anna Berg", 2000, sex="F"),                     # living
            rec("@L2@", "Anna Berg", 2000, sex="F"),
        ]

    def test_candidates(self):
        got = {frozenset((a["xref"], b["xref"])) for a, b in candidates(self.people)}
        self.assertEqual(got, {frozenset(("@A1@", "@A2@")), frozenset(("@A1@", "@A3@")),
                               frozenset(("@A2@", "@A3@"))})

    def test_find_then_payload(self):
        jev = FakeDupJev()
        find_duplicates(self.people, jev, workers=1)
        self.assertEqual(len(jev.asked), 6)                   # 3 pairs, both orders
        by = {p["xref"]: p for p in self.people}
        [d] = by["@A1@"]["ai_dups"]
        self.assertEqual((d["xref"], d["score"], d["shared_child"]), ("@A2@", 1.6, True))
        self.assertNotIn("ai_dups", by["@A3@"])               # 0.2: different person
        out = duplicates_payload(self.people)
        self.assertEqual((out["n_same"], out["n_possible"]), (1, 0))
        self.assertEqual({r["xref"] for r in out["same"][0]["records"]}, {"@A1@", "@A2@"})


class FakeParentsJev:
    """Backs whichever couple has the named father, at `p`, in any option order."""

    cost = 0.0

    def __init__(self, father, p):
        self.father, self.p, self.calls = father, p, 0

    def ask(self, state, questions):
        self.calls += 1
        labels = [k for k in state if k.startswith("couple_")]
        hit = [k for k in labels if state[k]["father"] != "not recorded"
               and state[k]["father"]["name"] == self.father]
        rest = (1 - self.p) / (len(labels) - 1)
        return {"parents": {"probabilities": {k: self.p if k in hit else rest for k in labels}}}

    def save(self):
        pass


def family(child_year=1682):
    """Mads Erichsen with two tied couples; the parser (FID order) chose Jens."""
    def pc(f, m, preferred):
        return {"father_xref": f, "mother_xref": m, "father_fid": f, "mother_fid": m,
                "pedigree": "biological", "preferred": preferred, "tied": True, "injected": False}
    people = [rec("@J@", "Jens Thornoe", 1640), rec("@F@", "Fru Erichsen", 1640, sex="F"),
              rec("@E@", "Erik Matzen", 1658), rec("@K@", "Karen Madsdatter", 1660, sex="F"),
              rec("@M@", "Mads Erichsen", child_year)]
    m = people[-1]
    m.update(parent_couples=[pc("@J@", "@F@", True), pc("@E@", "@K@", False)],
             parent_xrefs=["@J@", "@F@", "@E@", "@K@"], father_xref="@J@", mother_xref="@F@")
    return people, m


class TestParents(unittest.TestCase):
    def test_confident_answer_repoints_and_rerun_is_stable(self):
        people, m = family()
        jev = FakeParentsJev("Erik Matzen", 0.95)
        self.assertEqual(settle(people, jev, workers=1)["changed"], 1)
        self.assertEqual(jev.calls, 2)                              # both orders
        self.assertEqual((m["father_xref"], m["mother_xref"]), ("@E@", "@K@"))
        self.assertEqual(m["parent_xrefs"][:2], ["@E@", "@K@"])
        self.assertEqual(m["ai_parents"], {"claims": 2, "prob": 0.95, "decided": True, "changed": True})
        settle(people, jev, workers=1)                              # re-run: same answer,
        self.assertTrue(m["ai_parents"]["changed"])                 # still vs the parser's pick

    def test_unsure_answer_keeps_or_restores_the_parsers_pick(self):
        people, m = family()
        settle(people, FakeParentsJev("Erik Matzen", 0.95), workers=1)
        settle(people, FakeParentsJev("Erik Matzen", ACT - 0.2), workers=1)
        self.assertEqual(m["father_xref"], "@J@")                   # restored
        self.assertFalse(m["ai_parents"]["decided"])

    def test_living_child_is_not_sent(self):
        people, m = family(child_year=1990)
        jev = FakeParentsJev("Erik Matzen", 0.95)
        settle(people, jev, workers=1)
        self.assertEqual(jev.calls, 0)
        self.assertNotIn("ai_parents", m)


class TestAIPrivacy(unittest.TestCase):
    class CaptureJev:
        def __init__(self):
            self.states = []

        def ask(self, state, questions):
            self.states.append(state)
            return {"parents": {"probabilities": {"couple_A": 0.95, "couple_B": 0.05}}}

    def test_living_parent_details_and_ages_never_leave(self):
        import copy
        import datetime
        import json

        year = datetime.date.today().year
        father = {"xref": "f", "name": "Living father", "birth_year": year - 35,
                  "birth_place": "Private father place"}
        mother = {"xref": "m", "name": "Living mother", "birth_year": year - 33,
                  "birth_place": "Private mother place"}
        historic = {"xref": "h", "name": "Documented ancestor", "birth_year": 1800,
                    "death_year": 1870, "birth_place": "Denmark"}
        child = {"name": "Deceased infant", "birth_year": year - 2, "death_year": year - 1}
        by = {p["xref"]: p for p in (father, mother, historic)}
        before = copy.deepcopy(by)
        couples = [{"father_xref": "f", "mother_xref": "m"},
                   {"father_xref": "h", "mother_xref": None}]
        jev = self.CaptureJev()
        ask_couples(jev, child, couples, by)
        for state in jev.states:
            private = next(c for key, c in state.items()
                           if key.startswith("couple_") and c["father"] == "not recorded")
            self.assertEqual(private, {"father": "not recorded", "mother": "not recorded", "ages": "unknown"})
        sent = json.dumps(jev.states)
        self.assertNotIn("Living father", sent)
        self.assertNotIn("Living mother", sent)
        self.assertNotIn("Private", sent)
        self.assertNotIn(str(year - 35), sent)
        self.assertNotIn(str(year - 33), sent)
        self.assertIn("Documented ancestor", sent)
        self.assertIn("Denmark", sent)
        self.assertEqual(by, before)

    def test_duplicate_record_omits_living_parents_and_children(self):
        import datetime
        year = datetime.date.today().year
        living = {"xref": "living", "name": "Private relative", "birth_year": year - 30}
        deceased = {"xref": "dead", "name": "Known relative", "birth_year": 1800}
        p = {"xref": "p", "name": "Deceased record", "birth_year": 1900, "death_year": 1980,
             "father_xref": "living", "mother_xref": "living"}
        result = _record(p, {"living": living, "dead": deceased}, {"p": ["living", "dead"]})
        self.assertEqual((result["father"], result["mother"]), ("unknown", "unknown"))
        self.assertEqual(result["children"], ["Known relative"])
        self.assertEqual(result["name"], "Deceased record")

    def test_placeholder_spouse_aliases_and_copied_places_are_not_sent(self):
        import json
        wife = {"xref": "w", "name": "Wife of Private spouse", "wife_of": "living",
                "birth_place": "Private copied place", "place_copied": True,
                "birth_year": 1900, "death_year": 1980}
        child = {"xref": "c", "name": "Known child", "father_xref": "w", "mother_xref": "w"}
        by = {"w": wife, "c": child}
        own = _record(wife, by, {})
        relatives = _record(child, by, {"c": ["w"]})
        self.assertEqual(own["name"], "unknown")
        self.assertEqual(own["birthplace"], "unknown")
        self.assertEqual((relatives["father"], relatives["mother"], relatives["children"]),
                         ("unknown", "unknown", ["unknown"]))
        jev = self.CaptureJev()
        ask_couples(jev, wife, [{"father_xref": "w", "mother_xref": "w"},
                               {"father_xref": None, "mother_xref": None}], by)
        self.assertNotIn("Private", json.dumps([own, relatives, jev.states]))

    def test_place_evaluation_also_excludes_living_and_copied_places(self):
        import datetime
        people = [person("dead", "Denmark", 1800),
                  person("living", "Private living place", datetime.date.today().year - 20),
                  {**person("wife", "Private copied place", 1800), "place_copied": True}]
        self.assertEqual(set(places_by_status(people)), {"Denmark"})
        from unittest import mock
        with mock.patch("builtins.print"):
            evaluate(None, places_by_status(people[1:]), 1, 1)


if __name__ == "__main__":
    unittest.main()
