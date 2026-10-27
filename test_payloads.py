"""test_payloads.py -- contract tests for core.payloads (the web API's data layer).

Run:  python test_payloads.py

Feeds a known small GEDCOM (tests/fixtures/sample.ged) through the SAME pipeline
the web API uses -- core.build_people() then core.{origins_summary,map_payload,
fan_payload,deadends_payload} -- and asserts the resulting JSON. This locks the
ancestors.json -> payload contract the SPA depends on: if a refactor changes the
shape or the numbers, this fails loudly instead of silently breaking the website.

Stdlib-only (core is dependency-free), so it runs anywhere the other suites do.
The synthetic tree: a child, two US-born parents, and four grandparents -- two
immigrants (Denmark, England) and two US dead-ends -- giving a clean 25/25/50
immigrant split, two migration arcs, and one of each DNA line.
"""
import unittest
from pathlib import Path

import core
from core.trace_deadends import likely_origin

FIXTURE = Path(__file__).resolve().parent / "tests" / "fixtures" / "sample.ged"


class TestPayloadContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        people, root_xref, _model = core.build_people([str(FIXTURE)])
        cls.people = people
        cls.root_xref = root_xref

    # ---- metadata --------------------------------------------------------
    def test_meta(self):
        m = core.tree_meta(self.people)
        self.assertEqual(m["n_people"], 7)
        self.assertEqual(m["n_direct"], 7)
        self.assertEqual(m["max_gen"], 2)
        self.assertEqual(m["root"], "Kid Example")
        self.assertEqual(m["root_fid"], "KID0-001")
        self.assertEqual(m["n_coords"], 7)

    # ---- origin models ---------------------------------------------------
    def test_immigrant_model_quarters(self):
        o = core.origins_summary(self.people)
        imm = {b["name"]: b["pct"] for b in o["models"]["immigrant"]["breakdown"]}
        self.assertAlmostEqual(imm["Danish"], 25.0, places=1)
        self.assertAlmostEqual(imm["English"], 25.0, places=1)
        self.assertAlmostEqual(o["models"]["immigrant"]["untraced_pct"], 50.0, places=1)

    def test_headcount_model(self):
        o = core.origins_summary(self.people)
        hc = {b["name"]: b["pct"] for b in o["models"]["headcount"]["breakdown"]}
        # 6 non-root ancestors with birthplaces: 4 American, 1 Danish, 1 English.
        self.assertAlmostEqual(hc["American (USA)"], 100.0 * 4 / 6, places=1)
        self.assertEqual(o["models"]["headcount"]["considered"], 6)

    # ---- map payload -----------------------------------------------------
    def test_map_payload_shape_and_contract(self):
        m = core.map_payload(self.people)
        # Every top-level key the SPA reads must be present (locks the contract).
        for key in ("meta", "colors", "models", "people", "arcs", "immigrants",
                    "ranges", "nat_counts", "state_counts", "immigrant_count",
                    "country_data", "country_details", "sankey", "stats"):
            self.assertIn(key, m, f"map payload missing '{key}'")
        # One canonical row per person; all 7 carry birth coordinates here.
        self.assertEqual(len(m["people"]), 7)
        self.assertEqual(sum(1 for r in m["people"] if "lat" in r), 7)
        # direct-line, excluding the root -- the "current selection" population.
        self.assertEqual(sum(1 for r in m["people"] if r["dir"] and r["gen"] != 0), 6)
        self.assertEqual(m["immigrant_count"], 2)    # Denmark + England
        self.assertEqual(len(m["immigrants"]), 2)    # one row per immigrant
        self.assertEqual(len(m["arcs"]), 2)          # each immigrant -> US-born child
        self.assertTrue(m["sankey"]["flows"])        # at least one origin->settlement
        self.assertEqual(m["ranges"]["yr_lo"], 1925)
        self.assertEqual(m["ranges"]["yr_hi"], 1980)
        self.assertEqual(m["ranges"]["gen_lo"], 0)   # root
        self.assertEqual(m["ranges"]["gen_hi"], 2)   # grandparents

    def test_people_and_immigrant_rows(self):
        """The SPA derives every view from these rows, so lock the fields it reads."""
        m = core.map_payload(self.people)
        for r in m["people"]:
            for f in ("name", "surname", "xref", "gen", "nat", "dir", "imm"):
                self.assertIn(f, r)
        origins = sorted(i["origin"] for i in m["immigrants"])
        self.assertEqual(origins, ["Danish", "English"])
        for i in m["immigrants"]:
            self.assertTrue(i["settlement"])         # always defaulted, never empty
        # DNA rows now carry a generation so the client can truncate by gen range.
        for line in ("y_line", "mt_line"):
            for row in m["stats"]["dna"][line]:
                self.assertIn("gen", row)

    def test_state_breakdown(self):
        """US state of birth (`st` on American rows + the `state_counts` tally)
        powers the by-state filter/breakdown. The fixture's American direct line
        is Dad+Far Mor+Mor Mor (Utah) and Mom (Idaho); the root is Utah-born but
        excluded from the tally (gen 0); the two immigrants carry no state."""
        m = core.map_payload(self.people)
        # Direct-line, gen != 0, American-born -> Utah x3, Idaho x1, root excluded.
        self.assertEqual(m["state_counts"], {"Utah": 3, "Idaho": 1})
        st_by_name = {r["name"]: r.get("st") for r in m["people"]}
        self.assertEqual(st_by_name["Dad Example"], "Utah")
        self.assertEqual(st_by_name["Mom Smith"], "Idaho")
        self.assertEqual(st_by_name["Far Mor Hansen"], "Utah")
        self.assertEqual(st_by_name["Kid Example"], "Utah")  # root row still tagged
        # Foreign-born immigrants get no state, keeping `st` aligned with the
        # American country filter (so a state pick never references a non-American).
        self.assertIsNone(st_by_name["Far Far Example"])   # Denmark
        self.assertIsNone(st_by_name["Mor Far Smith"])     # England

    def test_fan_records_carry_state(self):
        """Fan recs carry `st` so the SPA's state filter dims wedges like br/dna do."""
        recs = core.fan_payload(self.people)["recs"]
        st_by_name = {r["n"]: r["st"] for r in recs.values()}
        self.assertEqual(st_by_name["Dad Example"], "Utah")
        self.assertEqual(st_by_name["Far Far Example"], "")  # foreign-born -> empty

    def test_country_details(self):
        cd = core.map_payload(self.people)["country_details"]
        # three source countries born into: USA (destination), Denmark, England.
        self.assertEqual(set(cd), {"USA", "DNK", "GBR"})

        usa = cd["USA"]
        self.assertEqual(usa["total"], 4)                 # 2 parents + 2 US grandparents
        self.assertEqual(usa["imm"], 0)                   # destination -> no immigrants
        self.assertEqual(usa["settle"], [])               # ...hence no settlements
        self.assertEqual(dict(usa["by_gen"]), {1: 2, 2: 2})
        self.assertEqual(usa["earliest"]["year"], 1928)   # Far Mor (gen 2)
        self.assertEqual(usa["earliest"]["gen"], 2)
        self.assertEqual(usa["latest"]["year"], 1957)     # Mom (gen 1)
        self.assertEqual(usa["branch"], {"P": 2, "M": 2})

        dnk = cd["DNK"]
        self.assertEqual(dnk["nats"], [["Danish", 1]])    # JSON tuples -> lists
        self.assertEqual(dnk["total"], 1)
        self.assertEqual(dnk["imm"], 1)
        self.assertEqual(dnk["imm_span"], [1925, 1925])
        self.assertEqual(dnk["settle"], [["Utah", 1]])    # Far Far's child Dad born in Utah
        self.assertEqual(dnk["branch"], {"P": 1, "M": 0})
        self.assertEqual(dnk["median_life"], 74.0)        # 1925 -> 1999
        self.assertEqual(dnk["life_n"], 1)

        gbr = cd["GBR"]
        self.assertEqual(gbr["nats"], [["English", 1]])
        self.assertEqual(gbr["imm"], 1)
        self.assertEqual(gbr["settle"], [["Idaho", 1]])   # Mor Far's child Mom born in Idaho
        self.assertEqual(gbr["branch"], {"P": 0, "M": 1})

    def test_map_stats(self):
        stats = core.map_payload(self.people)["stats"]
        comp = {c["gen"]: (c["known"], c["expected"]) for c in stats["completeness"]}
        self.assertEqual(comp[1], (2, 2))
        self.assertEqual(comp[2], (4, 4))
        surnames = {s["surname"]: s["count"] for s in stats["surnames"]}
        self.assertEqual(surnames["Example"], 2)
        self.assertEqual(stats["immigration"]["total"], 2)
        # collapse couples carry parent xref/fid so the SPA can deep-link the names.
        for c in stats["collapse"]["couples"]:
            self.assertIn("fa_xref", c)
            self.assertIn("mo_xref", c)

    # ---- fan payload -----------------------------------------------------
    def test_fan_payload(self):
        f = core.fan_payload(self.people)
        self.assertEqual(len(f["recs"]), 7)
        self.assertEqual(f["root"], self.root_xref)
        kid = f["recs"][f["root"]]
        # father/mother links resolve to the right people (xrefs are renumbered,
        # so assert on names rather than hardcoded ids).
        self.assertEqual(f["recs"][kid["fa"]]["n"], "Dad Example")
        self.assertEqual(f["recs"][kid["mo"]]["n"], "Mom Smith")

    def test_fan_estimates_undocumented_deadends_only(self):
        f = core.fan_payload(self.people)
        # Far Mor Hansen: US-born dead-end (no parents) -> surname yields an estimate.
        hansen = next(r for r in f["recs"].values() if "Hansen" in r["n"])
        self.assertIn("est", hansen)
        self.assertEqual(hansen["est"]["label"], "Danish or Norwegian")
        # Mor Far Smith: born in England -> documented origin, so NO guess attached.
        smith = next(r for r in f["recs"].values() if "Mor Far" in r["n"])
        self.assertNotIn("est", smith)
        # Mor Mor Jones: US-born dead-end but Jones is ambiguous -> honest no estimate.
        jones = next(r for r in f["recs"].values() if "Jones" in r["n"])
        self.assertNotIn("est", jones)

    # ---- dead-ends -------------------------------------------------------
    def test_deadends(self):
        d = core.deadends_payload(self.people)
        self.assertAlmostEqual(d["untraced_pct"], 50.0, places=1)
        self.assertEqual(d["wall_generation"], 2)
        # both untraced lines are gen-2 US dead-ends -> "new-world leaf".
        self.assertIn("new-world leaf", d["by_reason"])
        # genuine dead-end rows carry xref/fid so the SPA can deep-link each name,
        # plus an ESTIMATED origin (label/confidence/rationale) the SPA marks as a guess.
        for r in d["top_genuine"]:
            self.assertIn("xref", r)
            self.assertIn("fid", r)
            self.assertIn("likely_origin", r)
            self.assertIn("confidence", r)
            self.assertIn("rationale", r)
            self.assertIn("surname_origin", r)
            self.assertIn("surname_confidence", r)
            self.assertIn("surname_rationale", r)
            self.assertIn("tree_origin", r)
            self.assertIn("tree_confidence", r)
            self.assertIn("tree_rationale", r)
            est = r["origin_estimate"]
            self.assertEqual(set(est), {"label", "confidence", "agreement", "rationale"})

    def test_deadends_surname_signal(self):
        # Raise the wall so the gen-2 US dead-ends count as "genuine" (gen < wall)
        # and surface in top_genuine -- letting us assert the surname guess (Phase
        # 1) end-to-end. Hansen -> -sen -> Danish or Norwegian; Jones -> honest none.
        d = core.deadends_payload(self.people, max_gen=3)
        self.assertTrue(d["top_genuine"])
        hansen = next(r for r in d["top_genuine"] if "Hansen" in r["name"])
        self.assertEqual(hansen["surname_origin"], "Danish or Norwegian")
        self.assertEqual(hansen["surname_confidence"], "medium")
        jones = next(r for r in d["top_genuine"] if "Jones" in r["name"])
        self.assertEqual(jones["surname_confidence"], "none")
        # Combined verdict: Hansen has only the surname signal (Utah place is
        # unplaceable, no other old-world Hansen in the tree) -> it passes through.
        self.assertEqual(hansen["origin_estimate"]["label"], "Danish or Norwegian")
        self.assertEqual(hansen["origin_estimate"]["confidence"], "medium")
        self.assertFalse(hansen["origin_estimate"]["agreement"])

    def test_deadends_likely_origin_aggregate(self):
        # The web payload must surface the likely-origin ESTIMATES (previously
        # computed only in the CLI's deadends.json). Both untraced lines dead-end
        # in Utah -- no colony to reason from -> one "unspecified American" bucket
        # at "none" confidence, covering the full 50% untraced.
        d = core.deadends_payload(self.people)
        self.assertIsInstance(d["likely_origin"], list)
        self.assertTrue(d["likely_origin"])
        top = d["likely_origin"][0]
        self.assertEqual(set(top), {"label", "pct", "confidence", "rationale"})
        self.assertEqual(top["label"], "Unknown (unspecified American)")
        self.assertEqual(top["confidence"], "none")
        self.assertAlmostEqual(top["pct"], 50.0, places=1)
        self.assertAlmostEqual(d["likely_origin_by_confidence"]["none"], 50.0, places=1)

    # ---- color sharing (map and fan must agree) --------------------------
    def test_ai_origin_rows(self):
        # An unmappable place with a confident AI answer shows as that country and
        # is flagged used; a medium answer rides along as a guess but isn't counted.
        people = [dict(p) for p in self.people]
        leaf = [p for p in people if p.get("generation") == 2]
        leaf[0].update(birth_place="Rouergue, West Francia",
                       ai_origin={"label": "French", "confidence": 0.99})
        leaf[1].update(birth_place="Loch Lomond, Eireann",
                       ai_origin={"label": "Scottish", "confidence": 0.6})
        rows = {r["xref"]: r for r in core.map_payload(people)["people"]}
        a, b = rows[leaf[0]["xref"]], rows[leaf[1]["xref"]]
        self.assertEqual((a["nat"], a["ai"]["used"]), ("French", True))
        self.assertEqual((b["nat"], b["ai"]["used"]), ("(untraced)", False))
        self.assertNotIn("ai", rows[self.root_xref])
        # the fan chart flags only the counted one
        recs = core.fan_payload(people)["recs"]
        self.assertEqual(recs[leaf[0]["xref"]].get("ai"), 1)
        self.assertNotIn("ai", recs[leaf[1]["xref"]])

    def test_contested_parents_row(self):
        people = [dict(p) for p in self.people]
        kid = next(p for p in people if p.get("generation") == 1)
        kid["parent_couples"] = [dict(c, tied=True) for c in kid["parent_couples"]] * 2
        row = {r["xref"]: r for r in core.map_payload(people)["people"]}[kid["xref"]]
        self.assertEqual(row["pc"], {"claims": 2, "prob": None, "decided": False, "changed": False})
        kid["ai_parents"] = {"claims": 2, "prob": 0.93, "decided": True, "changed": True}
        row = {r["xref"]: r for r in core.map_payload(people)["people"]}[kid["xref"]]
        self.assertEqual(row["pc"]["prob"], 0.93)
        self.assertNotIn("pc", {r["xref"]: r for r in core.map_payload(people)["people"]}[self.root_xref])

    def test_wife_with_copied_birthplace(self):
        people = [dict(p) for p in self.people]
        leaf = next(p for p in people if p.get("generation") == 2 and p.get("birth_lat") is not None)
        leaf.update(wife_of="@X@", fs_name="Charles Baker", place_copied=True)
        row = {r["xref"]: r for r in core.map_payload(people)["people"]}[leaf["xref"]]
        self.assertEqual(row["wife"], {"fs_name": "Charles Baker", "copied": True})
        self.assertNotIn("lat", row)                       # his birthplace isn't pinned twice
        self.assertEqual(row["nat"], "(untraced)")
        d = core.deadends_payload(people)
        self.assertIn("copied-place", d["by_reason"])
        # her estimate is her husband's documented origin -- marked, never counted
        husband = next(p for p in people if p["xref"] != leaf["xref"] and p.get("generation") == 2
                       and core.analyze_origins.origin_of(p)[1])
        leaf["wife_of"] = husband["xref"]
        genuine = core.deadends_payload(people, max_gen=3)["top_genuine"]   # gen 2 < wall
        row = next(r for r in genuine if r["xref"] == leaf["xref"])
        self.assertEqual((row["likely_origin"], row["confidence"]),
                         (core.analyze_origins.origin_of(husband)[0], "medium"))

    def test_stale_ai_origin_is_hidden_once_rules_map_the_place(self):
        people = [dict(p) for p in self.people]
        leaf = next(p for p in people if p.get("generation") == 2)
        leaf["ai_origin"] = {"label": "Maltese", "confidence": 1.0}
        row = {r["xref"]: r for r in core.map_payload(people)["people"]}[leaf["xref"]]
        self.assertNotIn("ai", row)
        self.assertNotEqual(row["nat"], "Maltese")

    def test_map_and_fan_share_colors(self):
        m = core.map_payload(self.people)
        f = core.fan_payload(self.people)
        for nat in ("Danish", "English"):
            self.assertIn(nat, m["colors"])
            self.assertEqual(m["colors"][nat], f["colors"][nat])


class TestLikelyOrigin(unittest.TestCase):
    """The colonial-place -> probable-origin priors behind the dead-ends guess.
    Historical priors, not facts -- each returns (label, confidence, rationale)."""

    def test_new_england_is_high_confidence_english(self):
        label, conf, _ = likely_origin("Plymouth, Massachusetts")
        self.assertEqual(label, "English (New England)")
        self.assertEqual(conf, "high")

    def test_hudson_valley_is_dutch(self):
        self.assertEqual(likely_origin("Albany, New Netherland")[0], "Dutch (Hudson Valley)")

    def test_unplaceable_american_is_none_confidence(self):
        label, conf, _ = likely_origin("Provo, Utah, United States")
        self.assertEqual(label, "Unknown (unspecified American)")
        self.assertEqual(conf, "none")

    def test_old_world_places_never_hit_colony_keywords(self):
        # "berks" / "lancaster" are Pennsylvania keywords, but not in England
        self.assertEqual(likely_origin("Reading, Berkshire, England")[1], "none")
        self.assertEqual(likely_origin("Lancaster, Lancashire, England")[0],
                         "Unknown (outside colonial America)")
        self.assertEqual(likely_origin("Europe")[0], "Unknown (place not identifiable)")
        self.assertEqual(likely_origin("Lancaster, Pennsylvania")[0], "German (Pennsylvania)")

    def test_no_birthplace_is_honest_unknown(self):
        self.assertEqual(likely_origin("")[1], "none")
        self.assertEqual(likely_origin(None)[1], "none")


class TestPrivacy(unittest.TestCase):
    AS_OF = 2026

    @classmethod
    def setUpClass(cls):
        cls.people, _root, _model = core.build_people([str(FIXTURE)])

    def test_is_likely_living(self):
        self.assertTrue(core.is_likely_living({"birth_year": 1990}, self.AS_OF))
        self.assertFalse(core.is_likely_living({"birth_year": 1990, "death_year": 2010}, self.AS_OF))
        self.assertFalse(core.is_likely_living({"birth_year": 1890}, self.AS_OF))  # > 110y ago
        self.assertFalse(core.is_likely_living({}, self.AS_OF))  # no dates -> assumed deceased

    def test_count_living(self):
        # only the root (b.1980, no death) is living; everyone else has a death year
        self.assertEqual(core.count_living(self.people, self.AS_OF), 1)

    def test_redact_hides_living_pii_only(self):
        by_xref = {p["xref"]: p for p in core.redact_people(self.people, self.AS_OF)}
        root = next(p for p in self.people if p["generation"] == 0)
        redacted = by_xref[root["xref"]]
        self.assertEqual(redacted["name"], "Living person")
        self.assertIsNone(redacted["birth_place"])
        self.assertIsNone(redacted["fs_id"])
        self.assertTrue(redacted.get("redacted"))
        # a deceased ancestor is passed through untouched
        dad = next(p for p in self.people
                   if p.get("surname") == "Example" and p.get("generation") == 1)
        self.assertEqual(by_xref[dad["xref"]]["name"], dad["name"])
        self.assertEqual(by_xref[dad["xref"]]["birth_place"], dad["birth_place"])

    def test_meta_reports_living_count(self):
        self.assertEqual(core.tree_meta(self.people)["living_count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
