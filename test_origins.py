"""
test_origins.py -- stdlib-only sanity tests for analyze_origins.py.

Run:  python test_origins.py

These guard the two things most likely to break silently once the full
15-generation GEDCOM lands:

  1. place-string -> nationality inference (NATIONALITY_RULES), including the
     US-beats-foreign-homonym ordering and native-language country names; and
  2. the (1/2)^generation weighting in both origin models.

The ISO-coverage test fails loudly if a NATIONALITY_RULES label is ever added
without a matching NATION_TO_ISO entry -- which would otherwise drop that
country from the choropleth without any error.
"""
import json
import re
import unittest
from collections import Counter
from pathlib import Path

import analyze_origins as ao
import trace_deadends as td


class TestNationalityInference(unittest.TestCase):
    def nat(self, place):
        return ao.infer_nationality(place)

    def test_us_full(self):
        self.assertEqual(self.nat("Salt Lake City, Salt Lake, Utah, United States"),
                         ("American (USA)", True))

    def test_us_state_only_no_country(self):
        self.assertEqual(self.nat("Draper, Salt Lake, Utah"), ("American (USA)", True))

    def test_us_beats_foreign_homonym(self):
        # "Sweden, Oneida, Idaho" is a Utah-area place name, not the country;
        # the US scan must win because a state token is present.
        self.assertEqual(self.nat("Sweden, Oneida, Idaho"), ("American (USA)", True))

    def test_england(self):
        self.assertEqual(self.nat("Manchester, Lancashire, England"), ("English", True))

    def test_scotland(self):
        self.assertEqual(self.nat("Edinburgh, Midlothian, Scotland"), ("Scottish", True))

    def test_wales(self):
        self.assertEqual(self.nat("Cardiff, Glamorgan, Wales"), ("Welsh", True))

    def test_ireland(self):
        self.assertEqual(self.nat("Cork, Munster, Ireland"), ("Irish", True))

    def test_northern_ireland_before_ireland(self):
        self.assertEqual(self.nat("Belfast, Antrim, Northern Ireland"),
                         ("Northern Irish", True))

    def test_denmark(self):
        self.assertEqual(self.nat("Copenhagen, Denmark"), ("Danish", True))

    def test_denmark_native_name(self):
        self.assertEqual(self.nat("Aalborg, Danmark"), ("Danish", True))

    def test_sweden(self):
        self.assertEqual(self.nat("Stockholm, Sweden"), ("Swedish", True))

    def test_prussia_to_german(self):
        self.assertEqual(self.nat("Posen, Prussia"), ("German", True))

    def test_german_state(self):
        self.assertEqual(self.nat("Munich, Bayern"), ("German", True))

    def test_switzerland(self):
        self.assertEqual(self.nat("Bern, Switzerland"), ("Swiss", True))

    def test_uk_generic(self):
        self.assertEqual(self.nat("Somewhere, United Kingdom"),
                         ("British (unspecified)", True))

    def test_empty_and_none(self):
        self.assertEqual(self.nat(""), (None, False))
        self.assertEqual(self.nat(None), (None, False))

    def test_unmapped_is_unresolved(self):
        label, resolved = self.nat("Atlantis, Mythica")
        self.assertFalse(resolved)            # surfaced for manual review
        self.assertEqual(label, "Mythica")    # last token offered as a hint


class TestColonialAndMessyPlaces(unittest.TestCase):
    """Real strings pulled from the 15-generation GEDCOM review list."""

    def nat(self, place):
        return ao.infer_nationality(place)

    # --- Colonial North America resolves to the New World, not Europe ---
    def test_massachusetts_bay_colony(self):
        self.assertEqual(
            self.nat("Newbury, Essex, Massachusetts Bay Colony, British Colonial America"),
            ("American (USA)", True))

    def test_connecticut_colony(self):
        self.assertEqual(
            self.nat("Hartford, Hartford, Connecticut Colony, British Colonial America"),
            ("American (USA)", True))

    def test_new_netherland_is_american(self):
        self.assertEqual(self.nat("New Amsterdam, New Netherland"), ("American (USA)", True))

    def test_bare_british_colonial_america(self):
        self.assertEqual(self.nat("British Colonial America"), ("American (USA)", True))

    def test_new_england_is_american(self):
        self.assertEqual(
            self.nat("of Dorchester, Suffolk, Massachusetts Bay Colony, New England, British Colonial America"),
            ("American (USA)", True))

    def test_british_north_america_is_canadian(self):
        self.assertEqual(self.nat("Upper Canada, British North America"), ("Canadian", True))

    def test_new_jersey_regression_guard(self):
        # "New Jersey" must stay American despite the Channel-Islands "jersey" rule.
        self.assertEqual(self.nat("Bergen, Hudson, Colony of New Jersey, British Colonial America"),
                         ("American (USA)", True))

    # --- Country abbreviations as the final token ---
    def test_eng_abbrev(self):
        self.assertEqual(self.nat("of Leeds, Yorks., Eng."), ("English", True))

    def test_bare_eng(self):
        self.assertEqual(self.nat("Eng"), ("English", True))

    def test_den_abbrev(self):
        self.assertEqual(self.nat("Orbaek, Svendborg, Den."), ("Danish", True))

    def test_denm_abbrev(self):
        self.assertEqual(self.nat("Of Bygum,Osterbolle,Viberg,Denm"), ("Danish", True))

    def test_scot_abbrev(self):
        self.assertEqual(self.nat("of Bendochy, Perth, Scot."), ("Scottish", True))

    def test_prus_abbrev(self):
        self.assertEqual(self.nat("of Droyssig, Saxe, Prus."), ("German", True))

    # --- US state postal abbreviations as the final token ---
    def test_va_abbrev(self):
        self.assertEqual(self.nat("Cobbs Hall, Northumberland Co, VA"), ("American (USA)", True))

    def test_md_abbrev(self):
        self.assertEqual(self.nat("St Mary's, St Mary's Co, MD"), ("American (USA)", True))

    def test_nj_abbrev(self):
        self.assertEqual(self.nat("nr Hackettstown,, NJ"), ("American (USA)", True))

    def test_county_abbrev_not_colorado(self):
        # "Co" (=County) must NOT be read as the Colorado postal code.
        label, resolved = self.nat("Durham Co")
        self.assertFalse(resolved)

    def test_engalnd_typo(self):
        self.assertEqual(self.nat("Cumbria, Engalnd"), ("English", True))

    # --- Wrapper punctuation gets stripped ---
    def test_angle_bracket_wrapper(self):
        self.assertEqual(self.nat("<Flitwick, Bedfordshire, England>"), ("English", True))

    def test_paren_wrapper(self):
        self.assertEqual(self.nat("(Netherlands)"), ("Dutch", True))

    # --- Comma-free strings ending in a full country name ---
    def test_comma_free_england(self):
        self.assertEqual(self.nat("Barton St David Somerset England"), ("English", True))

    def test_comma_free_wales_with_uk_suffix(self):
        self.assertEqual(self.nat("Cilgwyn,Nevern, Pembroke shire, Wales United Kingdom"),
                         ("Welsh", True))

    # --- Inline foreign-language country names ---
    def test_inglaterra(self):
        self.assertEqual(self.nat("Stratford on Avon, Warwickshire, Inglaterra"), ("English", True))

    def test_frankrijk(self):
        self.assertEqual(self.nat("Sedan, Ardennes, Frankrijk"), ("French", True))

    def test_pays_bas_holland(self):
        self.assertEqual(self.nat("Tilburg, Noord-Brabant, Pays-Bas"), ("Dutch", True))

    def test_west_germany_substring(self):
        self.assertEqual(self.nat("Dorporsch, West Germany"), ("German", True))

    def test_kingdom_of_ireland(self):
        self.assertEqual(self.nat("Drogheda, County Louth, Kingdom of Ireland"), ("Irish", True))

    def test_bailiwick_of_jersey(self):
        self.assertEqual(self.nat("Saint Helier, Bailiwick of Jersey"), ("Channel Islander", True))

    def test_isla_de_man(self):
        self.assertEqual(self.nat("Ballaugh, Isla de Man"), ("Manx", True))

    # --- New South Wales must not be read as Welsh ---
    def test_new_south_wales_is_australian(self):
        self.assertEqual(self.nat("Sydney, New South Wales, Australia"), ("Australian", True))

    # --- Diacritics fold onto the ASCII rule keys ---
    def test_accented_native_names(self):
        self.assertEqual(self.nat("Wien, Österreich"), ("Austrian", True))
        self.assertEqual(self.nat("Königsberg, Preußen"), ("German", True))
        self.assertEqual(self.nat("Roma, Lazio, Itália"), ("Italian", True))

    # --- Foreign country names as the final token ---
    def test_last_token_foreign_names(self):
        self.assertEqual(self.nat("Gent, Oost-Vlaanderen, België"), ("Belgian", True))
        self.assertEqual(self.nat("Paris, Île-de-France, França"), ("French", True))
        self.assertEqual(self.nat("Kayseri, Türkiye"), ("Turkish", True))
        self.assertEqual(self.nat("Beijing, China"), ("Chinese", True))
        self.assertEqual(self.nat("中國河南省商丘市虞城縣"), ("Chinese", True))

    def test_last_token_names_do_not_fire_as_substrings(self):
        # "franca" sits inside Villafranca, "iran" inside Miranda, "oman" inside Roman.
        self.assertEqual(self.nat("Villafranca di Verona, Veneto, Italia"), ("Italian", True))
        self.assertEqual(self.nat("Miranda de Ebro, Burgos, España"), ("Spanish", True))
        self.assertFalse(self.nat("Roma, Roman Empire")[1])

    def test_belgian_luxembourg_province_is_belgian(self):
        self.assertEqual(self.nat("Arlon, Province du Luxembourg, Walloon Region, Belgique"),
                         ("Belgian", True))
        self.assertEqual(self.nat("Luxembourg City, Luxembourg"), ("Luxembourgish", True))

    def test_more_countries(self):
        self.assertEqual(self.nat("Beirut, Lebanon"), ("Lebanese", True))
        self.assertEqual(self.nat("Tripoli, Libia"), ("Libyan", True))
        self.assertEqual(self.nat("서울, 한국"), ("Korean", True))

    def test_folding_does_not_create_us_states(self):
        # Portuguese "Geórgia" is the country; folded it would read as the US state.
        self.assertEqual(self.nat("Tbilisi, Geórgia"), ("Georgian", True))
        self.assertEqual(self.nat("Savannah, Chatham, Georgia"), ("American (USA)", True))

    def test_continents_and_empires_stay_unresolved(self):
        self.assertEqual(self.nat("Western Europe, Europe"), ("Europe", False))
        self.assertEqual(self.nat("Constantinople, Byzantine Empire"),
                         ("Byzantine Empire", False))


class TestCopiedPlace(unittest.TestCase):
    def test_copied_birthplace_is_not_an_origin(self):
        wife = {"birth_place": "Nantwich, Cheshire, England", "place_copied": True}
        self.assertEqual(ao.origin_of(wife), (None, False, None))
        del wife["place_copied"]
        self.assertEqual(ao.origin_of(wife)[:2], ("English", True))


class TestIsoCoverage(unittest.TestCase):
    def test_every_rule_label_has_iso(self):
        labels = ([label for _kw, label in ao.NATIONALITY_RULES]
                  + list(ao.COUNTRY_ABBREV.values()) + list(ao.COUNTRY_LAST_TOKEN.values()))
        missing = [label for label in labels if label not in ao.NATION_TO_ISO]
        # these two labels come from code paths outside the rules list:
        for label in ("American (USA)", "British (unspecified)"):
            if label not in ao.NATION_TO_ISO:
                missing.append(label)
        self.assertEqual(missing, [], f"labels missing from NATION_TO_ISO: {missing}")


def _person(xref, gen, place, parents):
    return {"xref": xref, "generation": gen, "on_direct_line": True,
            "birth_place": place, "christening_place": None,
            "parent_xrefs": parents}


class TestWeighting(unittest.TestCase):
    def setUp(self):
        # 3-generation tree: two grandparents are immigrants (Denmark, England);
        # the other two are US dead-ends (no parents recorded).
        self.people = {p["xref"]: p for p in [
            _person("@R@", 0, "Provo, Utah, United States", ["@D@", "@M@"]),
            _person("@D@", 1, "Provo, Utah, United States", ["@PGF@", "@PGM@"]),
            _person("@M@", 1, "Provo, Utah, United States", ["@MGF@", "@MGM@"]),
            _person("@PGF@", 2, "Copenhagen, Denmark", []),
            _person("@PGM@", 2, "Logan, Utah, United States", []),
            _person("@MGF@", 2, "London, England", []),
            _person("@MGM@", 2, "Ogden, Utah, United States", []),
        ]}

    def test_immigrant_model_quarters(self):
        origins, untraced, total, cycles, _ = ao.immigrant_origins(self.people, "@R@")
        self.assertAlmostEqual(origins["Danish"], 0.25)
        self.assertAlmostEqual(origins["English"], 0.25)
        self.assertAlmostEqual(untraced, 0.50)   # two US dead-end lines
        self.assertAlmostEqual(total, 1.0)
        self.assertEqual(cycles, [])

    def test_deepest_model_assigns_leaves(self):
        weights, untraced, total, _, _ = ao.weighted_origins(self.people, "@R@")
        self.assertAlmostEqual(weights["Danish"], 0.25)
        self.assertAlmostEqual(weights["English"], 0.25)
        self.assertAlmostEqual(weights["American (USA)"], 0.50)
        self.assertAlmostEqual(untraced, 0.0)
        self.assertAlmostEqual(total, 1.0)

    def test_missing_parent_half_is_untraced(self):
        # Remove the paternal grandmother entirely: her half can't resolve.
        self.people["@D@"]["parent_xrefs"] = ["@PGF@"]
        origins, untraced, total, _, _ = ao.immigrant_origins(self.people, "@R@")
        self.assertAlmostEqual(origins["Danish"], 0.25)
        self.assertAlmostEqual(origins["English"], 0.25)
        self.assertAlmostEqual(untraced, 0.50)    # PGM half (.25) + MGM dead-end (.25)
        self.assertAlmostEqual(total, 1.0)

    def test_pedigree_cycle_is_caught(self):
        # Make a US-born ancestor their own descendant's parent. The immigrant
        # model keeps climbing through US-born people, so this loop is actually
        # traversed (unlike pointing the resolved immigrant back, which would
        # terminate first). The walk must detect the cycle, not recurse forever.
        # Only the looping PGM->D edge is cut; the Danish line above @D@ survives.
        self.people["@PGM@"]["parent_xrefs"] = ["@D@"]
        origins, untraced, total, cycles, _ = ao.immigrant_origins(self.people, "@R@")
        self.assertEqual(cycles, ["@D@"])
        self.assertAlmostEqual(origins["Danish"], 0.25)
        self.assertAlmostEqual(untraced, 0.50)   # PGM's two halves (cut + absent) + MGM
        self.assertAlmostEqual(total, 1.0)
        # trace_deadends must attribute the same untraced weight, cycle included.
        events = td.trace_deadends(self.people, "@R@")
        self.assertAlmostEqual(sum(e["weight"] for e in events), untraced)
        self.assertEqual([(e["xref"], e["weight"]) for e in events if e["reason"] == "cycle"],
                         [("@PGM@", 0.125)])


class TestSelectedParents(unittest.TestCase):
    def setUp(self):
        self.people = [
            _person("R", 0, "Utah, United States", ["M", "AD", "AM"]),
            _person("M", 1, "Denmark", []),
            _person("AD", 1, "England", []),
            _person("AM", 1, "England", []),
        ]
        self.people[0].update(father_xref=None, mother_xref="M")
        for p in self.people:
            p["name"] = p["xref"]
        self.by = {p["xref"]: p for p in self.people}

    def test_missing_slot_never_uses_an_alternate_parent(self):
        for model in (ao.immigrant_origins, ao.weighted_origins):
            origins, untraced, total, _, _ = model(self.by, "R")
            self.assertEqual(dict(origins), {"Danish": 0.5})
            self.assertEqual((untraced, total), (0.5, 1.0))
        events = td.trace_deadends(self.by, "R")
        self.assertEqual([(e["xref"], e["reason"], e["weight"]) for e in events],
                         [("R", "one parent only", 0.5)])

    def test_mother_only_keeps_maternal_branch_and_dna(self):
        branches, _, _ = ao.branch_tags(self.people)
        self.assertEqual(branches, {"M": "M"})
        dna, y, mt = ao.dna_lines(self.people)
        self.assertEqual(dna, {"M": "mt"})
        self.assertEqual(y, [])
        self.assertEqual([p["xref"] for p in mt], ["M"])
        from core.build_fan_chart import parents_of
        self.assertEqual(parents_of(self.people[0], self.by), (None, "M"))

    def test_explicit_empty_slots_do_not_fall_back(self):
        self.assertEqual(ao.parent_slots({"parent_xrefs": ["AD", "AM"],
                                          "father_xref": None, "mother_xref": None}),
                         (None, None))
        self.assertEqual(ao.parent_slots({"parent_xrefs": ["F"]}), ("F", None))

    def test_ai_repoint_keeps_the_missing_slot(self):
        from core.parents import _repoint
        child = self.people[0]
        old = {"father_xref": "AD", "mother_xref": "AM", "preferred": True}
        chosen = {"father_xref": None, "mother_xref": "M", "pedigree": "biological"}
        child["parent_couples"] = [old, chosen]
        _repoint(child, chosen)
        self.assertEqual(ao.parent_slots(child), (None, "M"))
        origins, untraced, total, _, _ = ao.immigrant_origins(self.by, "R")
        self.assertEqual((dict(origins), untraced, total), ({"Danish": 0.5}, 0.5, 1.0))

    def test_alternate_claims_do_not_create_migration_rows(self):
        from core.payloads import map_payload
        self.by["AD"].update(birth_place="Utah, United States", parent_xrefs=["G"])
        grandparent = _person("G", 2, "Norway", [])
        grandparent["name"] = "G"
        self.people.append(grandparent)
        payload = map_payload(self.people)
        self.assertEqual([r["origin"] for r in payload["immigrants"]], ["Danish"])


class TestDeadendAggregation(unittest.TestCase):
    def test_repeated_ancestry_has_bounded_events(self):
        people = {"R": _person("R", 0, None, ["a0", "b0"])}
        for gen in range(16):
            parents = [f"a{gen + 1}", f"b{gen + 1}"] if gen < 15 else []
            for prefix in "ab":
                xref = f"{prefix}{gen}"
                people[xref] = _person(xref, gen + 1, None, parents)
        events = td.trace_deadends(people, "R")
        self.assertEqual(len(events), 2)
        self.assertEqual({e["depth"] for e in events}, {16})
        self.assertEqual(sum(e["weight"] for e in events), 1.0)
        self.assertEqual(sum(e["weight"] for e in events), ao.immigrant_origins(people, "R")[1])

    def test_long_line_and_missing_records_preserve_weights(self):
        people = {str(i): _person(str(i), i, None, [str(i + 1)]) for i in range(1200)}
        events = td.trace_deadends(people, "0")
        self.assertLessEqual(len(events), len(people) + 1)
        self.assertAlmostEqual(sum(e["weight"] for e in events), 1.0)
        self.assertIn("missing record", {e["reason"] for e in events})


class TestCoord(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(ao.valid_coord(40.7, -111.9))

    def test_null_island_rejected(self):
        self.assertFalse(ao.valid_coord(0, 0))

    def test_out_of_range_rejected(self):
        self.assertFalse(ao.valid_coord(200, 0))
        self.assertFalse(ao.valid_coord(0, -500))

    def test_missing_rejected(self):
        self.assertFalse(ao.valid_coord(None, None))
        self.assertFalse(ao.valid_coord(40.0, None))


def _mk(x, g, par):
    return {"xref": x, "generation": g, "on_direct_line": True, "parent_xrefs": par}


class TestBranchTags(unittest.TestCase):
    def _tree(self):
        # root I1; father I2 (parents I4,I6); mother I3 (parents I5,I7)
        return [
            _mk("I1", 0, ["I2", "I3"]),
            _mk("I2", 1, ["I4", "I6"]),
            _mk("I3", 1, ["I5", "I7"]),
            _mk("I4", 2, []), _mk("I6", 2, []),
            _mk("I5", 2, []), _mk("I7", 2, []),
        ]

    def test_sides(self):
        bo, gp, root = ao.branch_tags(self._tree())
        self.assertEqual(root, "I1")
        self.assertEqual(bo["I2"], "P")
        self.assertEqual(bo["I3"], "M")
        self.assertEqual(bo["I4"], "P")
        self.assertEqual(bo["I5"], "M")
        self.assertNotIn("I1", bo)            # root itself is untagged

    def test_grandparent_codes(self):
        _, gp, _ = ao.branch_tags(self._tree())
        self.assertEqual(gp["I4"], "FF")
        self.assertEqual(gp["I6"], "FM")
        self.assertEqual(gp["I5"], "MF")
        self.assertEqual(gp["I7"], "MM")

    def test_first_path_wins_on_collapse(self):
        # I4 sits on both sides; BFS reaches it via the father (gen 2) before the
        # longer maternal path (gen 3), so it is tagged paternal.
        t = self._tree()
        for p in t:
            if p["xref"] == "I5":
                p["parent_xrefs"] = ["I4", "I7b"]
        t.append(_mk("I7b", 3, []))
        bo, _, _ = ao.branch_tags(t)
        self.assertEqual(bo["I4"], "P")

    def test_third_parent_slot_left_untagged(self):
        # A 3rd parent record is only reachable through an extra slot -> untagged.
        t = self._tree()
        for p in t:
            if p["xref"] == "I2":
                p["parent_xrefs"] = ["I4", "I6", "I8"]
        t.append(_mk("I8", 2, []))
        bo, _, _ = ao.branch_tags(t)
        self.assertNotIn("I8", bo)

    def test_no_root(self):
        bo, gp, root = ao.branch_tags([_mk("I9", 5, [])])
        self.assertEqual((bo, gp, root), ({}, {}, None))


class TestDnaLines(unittest.TestCase):
    def _tree(self):
        # father-chain: I1 -> I2 -> I4 -> I8 ; mother-chain: I1 -> I3 -> I7 -> I15
        return [
            _mk("I1", 0, ["I2", "I3"]),
            _mk("I2", 1, ["I4", "I6"]),
            _mk("I3", 1, ["I5", "I7"]),
            _mk("I4", 2, ["I8", "I9"]),
            _mk("I7", 2, ["I14", "I15"]),
            _mk("I8", 3, []), _mk("I15", 3, []),
            _mk("I5", 2, []), _mk("I6", 2, []), _mk("I9", 3, []), _mk("I14", 3, []),
        ]

    def test_patrilineal_follows_slot0(self):
        dna_of, y, mt = ao.dna_lines(self._tree())
        self.assertEqual([p["xref"] for p in y], ["I2", "I4", "I8"])
        for x in ("I2", "I4", "I8"):
            self.assertEqual(dna_of[x], "Y")

    def test_matrilineal_follows_slot1(self):
        dna_of, y, mt = ao.dna_lines(self._tree())
        self.assertEqual([p["xref"] for p in mt], ["I3", "I7", "I15"])
        for x in ("I3", "I7", "I15"):
            self.assertEqual(dna_of[x], "mt")

    def test_root_and_offline_untagged(self):
        dna_of, _, _ = ao.dna_lines(self._tree())
        self.assertNotIn("I1", dna_of)        # root is on neither single-sex line
        self.assertNotIn("I6", dna_of)        # father's mother is not patrilineal

    def test_no_root(self):
        self.assertEqual(ao.dna_lines([_mk("X", 3, [])]), ({}, [], []))


class TestSettlementOf(unittest.TestCase):
    def s(self, place):
        return ao.settlement_of({"birth_place": place})

    def test_clean_state_token(self):
        self.assertEqual(self.s("Provo, Utah, United States"), "Utah")

    def test_colonial_massachusetts(self):
        self.assertEqual(
            self.s("Newbury, Essex, Massachusetts Bay Colony, British Colonial America"),
            "Massachusetts")

    def test_colonial_plymouth_is_massachusetts(self):
        self.assertEqual(self.s("Taunton, Plymouth Colony, British Colonial America"),
                         "Massachusetts")

    def test_new_netherland_is_new_york(self):
        self.assertEqual(self.s("New Amsterdam, New Netherland"), "New York")

    def test_connecticut_colony(self):
        self.assertEqual(self.s("Ashford, Windham, Connecticut Colony, British Colonial America"),
                         "Connecticut")

    def test_trailing_postal_abbrev(self):
        self.assertEqual(self.s("Cobbs Hall, Northumberland Co, VA"), "Virginia")

    def test_canada(self):
        self.assertEqual(self.s("York, Upper Canada, British North America"), "Canada")

    def test_unmappable_returns_none(self):
        self.assertIsNone(self.s("Copenhagen, Denmark"))
        self.assertIsNone(self.s(""))
        self.assertIsNone(self.s(None))


class TestPedigreeCollapse(unittest.TestCase):
    def test_genuine_collapse_shared_parent(self):
        people = [
            _mk("I1", 0, ["I2", "I3"]),
            _mk("I2", 1, ["I4", "I5"]),
            _mk("I3", 1, ["I4", "I6"]),       # shares I4 with I2 -> collapse
            _mk("I4", 2, []), _mk("I5", 2, []), _mk("I6", 2, []),
        ]
        collapse, couples, over = ao.pedigree_collapse(people)
        self.assertIn("I4", collapse)
        self.assertNotIn("I5", collapse)
        self.assertEqual(over, [])

    def test_over_attachment_is_separate(self):
        # >2 parent records is the data artifact, NOT genuine collapse. Critically,
        # extra parents can push a generation past 2^g; genuine collapse cannot.
        people = [
            _mk("I1", 0, ["I2", "I3", "I9"]),
            _mk("I2", 1, []), _mk("I3", 1, []), _mk("I9", 1, []),
        ]
        collapse, couples, over = ao.pedigree_collapse(people)
        self.assertEqual([p["xref"] for p in over], ["I1"])
        self.assertEqual(collapse, set())     # extra parents do NOT create collapse

    def test_convergence_couple_listed(self):
        people = [
            _mk("I1", 0, ["I2", "I3"]),
            _mk("I2", 1, ["I4", "I5"]),
            _mk("I3", 1, ["I4", "I5"]),       # same couple parents two direct kids
            _mk("I4", 2, []), _mk("I5", 2, []),
        ]
        _, couples, _ = ao.pedigree_collapse(people)
        self.assertIn((("I4", "I5"), 2), couples)


class TestRealDataIfPresent(unittest.TestCase):
    """Validate the branch / collapse / DNA-line LOGIC against the real tree
    when it is available, using invariants rather than hardcoded totals -- the
    tree grows with every deeper pull, so exact counts are intentionally not
    asserted (that only produces churn). Skips automatically in a fresh checkout
    (personal data is gitignored), so CI stays green; runs locally where
    output/ancestors.json exists.
    """
    DATA = Path("output/ancestors.json")

    @unittest.skipUnless(DATA.exists(), "needs personal output/ancestors.json")
    def test_branch_and_collapse_invariants(self):
        people = json.loads(self.DATA.read_text(encoding="utf-8"))
        direct = [p for p in people
                  if p.get("on_direct_line") and p.get("generation") not in (0, None)]
        n_direct = len(direct)
        maxg = max((p.get("generation") or 0) for p in direct)

        # branch tagging: a clean P/M partition covering most of the direct line
        bo, _, _ = ao.branch_tags(people)
        sides = Counter(bo.values())
        self.assertEqual(set(sides) - {"P", "M"}, set(), "only P/M side tags")
        self.assertGreater(sides["P"], 0, "paternal side populated")
        self.assertGreater(sides["M"], 0, "maternal side populated")
        self.assertLessEqual(sides["P"] + sides["M"], n_direct, "each ancestor tagged at most once")
        self.assertGreater(sides["P"] + sides["M"], n_direct * 0.5, "most ancestors get a side")

        # genuine collapse (shared ancestors, >1 line) vs over-attachment (>2
        # parent records) are distinct buckets, both bounded by the tree size
        collapse, couples, over = ao.pedigree_collapse(people)
        self.assertTrue(0 <= len(collapse) <= n_direct)
        self.assertTrue(0 <= len(over) <= n_direct)
        self.assertTrue(all(n >= 2 for _, n in couples), "collapse couples sit on >1 line")

        # direct DNA lines: non-empty chains no deeper than the tree itself
        _, y_line, mt_line = ao.dna_lines(people)
        self.assertTrue(1 <= len(y_line) <= maxg + 1, "patrilineal (Y-DNA) line within depth")
        self.assertTrue(1 <= len(mt_line) <= maxg + 1, "matrilineal (mtDNA) line within depth")


if __name__ == "__main__":
    unittest.main(verbosity=2)
