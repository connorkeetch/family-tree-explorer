"""test_infer_origin.py -- the surname -> likely-origin signal (Phase 1).

Surname inference is a NOISY hint, so these tests pin three things as hard as
the happy path: (1) confidence never exceeds "medium"; (2) ambiguous
high-frequency names return an honest "none" rather than a confident wrong
guess; (3) short look-alikes ("Macy", "Mac") don't trip the affix guards.

Stdlib-only (core is dependency-free). Run:  python test_infer_origin.py
"""
import unittest

from core.infer_origin import (
    surname_origin, SURNAME_DICT, AFFIX_RULES,
    build_surname_index, tree_surname_origin, combine_origin,
)

NONE = ("Unknown", "none", "")


class TestSurnameDictionary(unittest.TestCase):
    def test_distinctive_names_map_to_their_origin(self):
        cases = {
            "Murphy": "Irish",
            "Campbell": "Scottish",
            "Lloyd": "Welsh",
            "Müller": "German",
            "Mueller": "German",      # ASCII spelling
            "Schmidt": "German",
            "Rossi": "Italian",
            "Garcia": "Spanish",
            "Silva": "Portuguese",
            "de Jong": "Dutch",       # multi-word key
        }
        for name, expected in cases.items():
            label, conf, why = surname_origin(name)
            self.assertEqual(label, expected, name)
            self.assertIn(conf, ("medium", "low"), name)
            self.assertTrue(why)

    def test_common_english_names_are_low_confidence(self):
        label, conf, _ = surname_origin("Taylor")
        self.assertEqual(label, "English")
        self.assertEqual(conf, "low")  # English surnames recur everywhere


class TestAffixRules(unittest.TestCase):
    def test_prefixes(self):
        self.assertEqual(surname_origin("O'Brien")[0], "Irish")
        self.assertEqual(surname_origin("McKay")[0], "Scottish or Irish")
        self.assertEqual(surname_origin("MacLeod")[0], "Scottish or Irish")
        self.assertEqual(surname_origin("van der Berg")[0], "Dutch")
        self.assertEqual(surname_origin("von Trapp")[0], "German")
        self.assertEqual(surname_origin("Fitzgerald")[0], "Irish (Norman)")

    def test_suffixes(self):
        self.assertEqual(surname_origin("Hansen")[0], "Danish or Norwegian")
        self.assertEqual(surname_origin("Andersson")[0], "Swedish")  # -sson beats -son
        self.assertEqual(surname_origin("Kowalski")[0], "Polish")
        self.assertEqual(surname_origin("Lopez")[0], "Spanish")
        self.assertEqual(surname_origin("Martinelli")[0], "Italian")
        self.assertEqual(surname_origin("Papadopoulos")[0], "Greek")

    def test_ambiguous_son_is_low_and_hedged(self):
        label, conf, why = surname_origin("Anderson")
        self.assertEqual(label, "English or Scandinavian")
        self.assertEqual(conf, "low")
        self.assertIn("son", why.lower())


class TestHonestUnknowns(unittest.TestCase):
    """We would rather miss than guess wrong -- the provenance rule."""

    def test_welsh_or_english_ambiguous_names_are_unknown(self):
        # Jones/Williams/Davies are Welsh OR English -- omitted on purpose.
        for name in ("Jones", "Williams", "Davies", "Thomas"):
            self.assertEqual(surname_origin(name)[1], "none", name)

    def test_smith_is_unknown_not_english(self):
        # Smith may be native English OR an anglicized Schmidt -- don't pretend.
        self.assertEqual(surname_origin("Smith")[1], "none")

    def test_empty_and_none(self):
        self.assertEqual(surname_origin("")[1], "none")
        self.assertEqual(surname_origin(None)[1], "none")
        self.assertEqual(surname_origin("   ")[1], "none")


class TestFalsePositiveGuards(unittest.TestCase):
    def test_short_lookalikes_do_not_fire_prefix_rules(self):
        # "Macy" (English) is too short to be a Mac- patronymic; "Mac" alone too.
        self.assertEqual(surname_origin("Macy")[1], "none")
        self.assertEqual(surname_origin("Mac")[1], "none")
        self.assertEqual(surname_origin("Mc")[1], "none")

    def test_van_needs_a_real_name_after_it(self):
        self.assertEqual(surname_origin("Van")[1], "none")


class TestConfidenceCeiling(unittest.TestCase):
    def test_no_rule_ever_returns_high(self):
        # A surname is never proof of an individual's origin.
        for label, conf, why in SURNAME_DICT.values():
            self.assertIn(conf, ("medium", "low"))
            self.assertTrue(label and why)
        for _kind, _pat, _min, label, conf, why in AFFIX_RULES:
            self.assertIn(conf, ("medium", "low"))
            self.assertTrue(label and why)


class TestTreeSurnameOrigin(unittest.TestCase):
    """Phase 2: propagate origin from same-surname relatives DOCUMENTED in the tree."""

    def _people(self):
        # surname + birthplace; origin_of resolves the nationality from the place.
        return [
            {"surname": "Lloyd", "birth_place": "Cardiff, Wales"},          # Welsh
            {"surname": "Lloyd", "birth_place": "Swansea, Wales"},          # Welsh
            {"surname": "Lloyd", "birth_place": "Richmond, Virginia, United States"},  # New-World -> excluded
            {"surname": "Meyer", "birth_place": "Munich, Germany"},         # German (lone)
            {"surname": "Brown", "birth_place": "Manchester, England"},     # English
            {"surname": "Brown", "birth_place": "Berlin, Germany"},         # German (mixed w/ above)
            {"surname": "Yates", "birth_place": "Boise, Idaho, United States"},  # New-World only
        ]

    def test_agreeing_relatives_give_medium(self):
        idx = build_surname_index(self._people())
        label, conf, why = tree_surname_origin("Lloyd", idx)
        self.assertEqual(label, "Welsh")
        self.assertEqual(conf, "medium")           # 2 agree, New-World one excluded
        self.assertIn("2 same-surname relatives", why)

    def test_lone_relative_is_low(self):
        idx = build_surname_index(self._people())
        label, conf, _ = tree_surname_origin("Meyer", idx)
        self.assertEqual(label, "German")
        self.assertEqual(conf, "low")              # only one documented bearer

    def test_mixed_origins_are_low(self):
        idx = build_surname_index(self._people())
        label, conf, why = tree_surname_origin("Brown", idx)
        self.assertEqual(conf, "low")              # 1 English + 1 German -> 50% share
        self.assertIn("mixed", why)

    def test_no_documented_bearer_is_none(self):
        idx = build_surname_index(self._people())
        # Yates has only a New-World birthplace -> not in the index at all.
        self.assertEqual(tree_surname_origin("Yates", idx)[1], "none")
        self.assertEqual(tree_surname_origin("Nonexistent", idx)[1], "none")

    def test_empty_surname_is_none(self):
        idx = build_surname_index(self._people())
        self.assertEqual(tree_surname_origin("", idx)[1], "none")


class TestCombineOrigin(unittest.TestCase):
    """Phase 3: reconcile place + surname + relatives into one verdict.
    Agreement across independent signals is the ONLY path to "high"."""

    def test_no_signals_is_unknown(self):
        v = combine_origin(NONE, NONE, NONE)
        self.assertEqual(v["confidence"], "none")
        self.assertFalse(v["agreement"])
        self.assertEqual(v["rationale"], [])

    def test_single_signal_passes_through(self):
        # A strong colony prior can read "high" on its own (no boost needed).
        v = combine_origin(("English (New England)", "high", "Puritan New England"), NONE, NONE)
        self.assertEqual(v["label"], "English (New England)")
        self.assertEqual(v["confidence"], "high")
        self.assertFalse(v["agreement"])
        self.assertEqual(len(v["rationale"]), 1)

    def test_three_signals_agree_reach_high(self):
        v = combine_origin(
            ("English (Tidewater VA/MD)", "medium", "Tidewater planters"),
            ("English or Scandinavian", "low", "-son patronymic"),
            ("English", "medium", "3 relatives documented English"),
        )
        self.assertEqual(v["label"], "English")
        self.assertEqual(v["confidence"], "high")
        self.assertTrue(v["agreement"])

    def test_two_agree_with_no_dissent_boosts(self):
        # Two medium signals, nothing else active -> boosted to high.
        v = combine_origin(("English (New England)", "medium", "x"), NONE,
                           ("English", "medium", "y"))
        self.assertEqual(v["confidence"], "high")
        self.assertTrue(v["agreement"])
        # Two LOW signals agreeing -> only medium.
        v2 = combine_origin(("English (New England)", "low", "x"), NONE,
                            ("English", "low", "y"))
        self.assertEqual(v2["confidence"], "medium")

    def test_two_agree_but_third_dissents_holds_level(self):
        # Lloyd: surname+relatives say Welsh; place says something else -> hold at
        # the agreeing signals' max (medium), do NOT boost to high.
        v = combine_origin(
            ("Mixed (English/German/Scots-Irish)", "low", "colonial PA mix"),
            ("Welsh", "medium", "distinctively Welsh surname"),
            ("Welsh", "low", "1 relative documented Welsh"),
        )
        self.assertEqual(v["label"], "Welsh")
        self.assertEqual(v["confidence"], "medium")
        self.assertTrue(v["agreement"])

    def test_full_disagreement_takes_strongest_and_flags(self):
        v = combine_origin(("German (Pennsylvania)", "medium", "PA German"),
                          ("Irish", "low", "O'- prefix"), NONE)
        self.assertEqual(v["label"], "German (Pennsylvania)")
        self.assertEqual(v["confidence"], "medium")
        self.assertFalse(v["agreement"])
        self.assertEqual(len(v["rationale"]), 2)  # both shown, conflict visible

    def test_scots_irish_is_distinct_from_irish(self):
        # Ulster Scots-Irish != Gaelic Irish -> these do NOT corroborate.
        v = combine_origin(("Scots-Irish (Carolina backcountry)", "low", "backcountry"),
                          NONE, ("Irish", "medium", "relatives Irish"))
        self.assertFalse(v["agreement"])
        self.assertEqual(v["label"], "Irish")  # the stronger signal


if __name__ == "__main__":
    unittest.main(verbosity=2)
