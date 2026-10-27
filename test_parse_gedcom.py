"""
test_parse_gedcom.py -- stdlib-only tests for parse_gedcom.py.

Run:  python test_parse_gedcom.py

Synthetic GEDCOMs are embedded INLINE (data/ and output/ are gitignored, so
fixture files there would vanish in a fresh checkout) and written to a temp dir
per test. They exercise the merge + biological-vs-adoptive logic that has no
real-data fixture:

  * dedup-by-FID merge of a "deeper pull" and BFS regeneration of generations;
  * PEDI birth/adopted preference (and blank PEDI treated as biological);
  * deterministic choice between equally-unlabelled couples;
  * conflicting unlabelled couples: date-impossible parents lose, then a couple
    naming both parents beats a half couple, before FID order decides -- and
    couples the dates can't separate are marked `tied` for core.parents;
  * explicit father/mother slots selecting the preferred biological couple;
  * the injection override that CONNECTS a biological parent FamilySearch never
    linked (a hypothetical adoption example with a disconnected biological pull);
  * root selection by FamilySearch ID.
"""
import os
import shutil
import tempfile
import unittest

import parse_gedcom as pg

HEAD = (
    "0 HEAD\n1 CHAR UTF-8\n1 SUBM @SUBM@\n"
    "0 @SUBM@ SUBM\n1 NAME Tester\n1 LANG English\n"
)
TRLR = "0 TRLR\n"


def indi(xref, name, fid, sex="U", famc=None, extra=""):
    """Build an INDI block. `famc` may be an @F@ pointer or a list of
    (pointer, pedi) tuples for multiple parent couples."""
    s = "0 %s INDI\n1 NAME %s\n1 SEX %s\n" % (xref, name, sex)
    if famc:
        couples = famc if isinstance(famc, list) else [(famc, None)]
        for ptr, pedi in couples:
            s += "1 FAMC %s\n" % ptr
            if pedi:
                s += "2 PEDI %s\n" % pedi
    s += extra
    s += "1 _FSFTID %s\n" % fid
    return s


def fam(xref, husb=None, wife=None, chil=None):
    s = "0 %s FAM\n" % xref
    if husb:
        s += "1 HUSB %s\n" % husb
    if wife:
        s += "1 WIFE %s\n" % wife
    for c in (chil or []):
        s += "1 CHIL %s\n" % c
    return s


def ged(*blocks):
    return HEAD + "".join(blocks) + TRLR


class GedcomTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pgtest_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def build(self, files, root=None, overrides=None):
        """files: dict name->text. Returns (by_fid, xref2fid, people, model)."""
        paths = [self.write(n, t) for n, t in files.items()]
        people, root_xref, model = pg.build_people(paths, root, overrides)
        by_fid = {p["fs_id"]: p for p in people if p["fs_id"]}
        xref2fid = {p["xref"]: p["fs_id"] for p in people}
        return by_fid, xref2fid, people, model

    def parents(self, person, xref2fid):
        """parent FIDs in parent_xrefs order."""
        return [xref2fid.get(x) for x in person["parent_xrefs"]]


class TestExtractYear(unittest.TestCase):
    """extract_year signs BC dates negative so the deep (legendary) BC line
    doesn't fold onto the AD axis. The tricky cases: 'a.C.'/'avanti Cristo' are
    BC like 'BC', but a bare 'antes de <year>' is 'before' (still AD), and the
    4-digit match must skip 'AC' day numbers."""

    def test_plain_ad(self):
        self.assertEqual(pg.extract_year("1850"), 1850)
        self.assertEqual(pg.extract_year("10 September 1924"), 1924)
        self.assertEqual(pg.extract_year("19920423"), 1992)  # compact YYYYMMDD

    def test_english_bc(self):
        self.assertEqual(pg.extract_year("5626 BC"), -5626)
        self.assertEqual(pg.extract_year("0001 BC"), -1)
        self.assertEqual(pg.extract_year("3 October 3874 BC"), -3874)
        self.assertEqual(pg.extract_year("before 1071 BC"), -1071)  # "before" + BC
        self.assertEqual(pg.extract_year("4000 BCE"), -4000)

    def test_spanish_italian_dutch_bc(self):
        self.assertEqual(pg.extract_year("3916 AC"), -3916)         # antes de Cristo
        self.assertEqual(pg.extract_year("aproximadamente 0008 AC"), -8)
        self.assertEqual(pg.extract_year("0039 avanti Cristo"), -39)
        self.assertEqual(pg.extract_year("0103 v. Chr."), -103)     # voor/vor Christus
        self.assertEqual(pg.extract_year("um 0148 v. Chr."), -148)
        # the day number must not be mistaken for the year
        self.assertEqual(pg.extract_year("14 de enero de 0038 AC"), -38)

    def test_future_year_is_nulled(self):
        # An AD birth past "now" is impossible -- in this data it's an unmarked-BC
        # patriarch or a non-Gregorian epoch. Null it (don't let it set the slider
        # max). as_of_year keeps this independent of the wall clock.
        self.assertIsNone(pg.extract_year("2122", as_of_year=2026))   # bare, unmarked
        self.assertIsNone(pg.extract_year("after 2458", as_of_year=2026))
        self.assertIsNone(pg.extract_year("2358  AM.", as_of_year=2026))  # Anno Mundi
        self.assertIsNone(pg.extract_year("9999"))                    # past any plausible now
        self.assertEqual(pg.extract_year("1992", as_of_year=2026), 1992)  # plausible AD kept
        self.assertEqual(pg.extract_year("3000 BC", as_of_year=2026), -3000)  # BC never future

    def test_glued_marker(self):
        # FamilySearch often glues the marker to the digits, defeating a \b.
        self.assertEqual(pg.extract_year("estimated before 3545BCE"), -3545)
        self.assertEqual(pg.extract_year("from 0016BC to 0025BC"), -16)  # first year

    def test_cjk_and_korean_bc(self):
        self.assertEqual(pg.extract_year("西元前0173年"), -173)        # Chinese
        self.assertEqual(pg.extract_year("大約西元前2780年"), -2780)   # "approx" + Chinese
        self.assertEqual(pg.extract_year("約紀元前0350年"), -350)      # Japanese
        self.assertEqual(pg.extract_year("기원전 1046년"), -1046)      # Korean

    def test_leading_minus(self):
        self.assertEqual(pg.extract_year("-3150"), -3150)
        self.assertEqual(pg.extract_year("circa -0500"), -500)
        # a minus after a digit is a date/range separator, not a sign
        self.assertEqual(pg.extract_year("10-12-1850"), 1850)
        self.assertEqual(pg.extract_year("1425 -1430"), 1425)  # AD range, first year

    def test_antes_de_is_before_not_bc(self):
        # "antes de <year>" = "before <year>" -- an AD date, not BC.
        self.assertEqual(pg.extract_year("antes de 1305"), 1305)
        self.assertEqual(pg.extract_year("antes aproximadamente 0932"), 932)

    def test_ad_markers_stay_positive(self):
        # "AD" / "d.C." (despues de/dopo Cristo) must NOT flip the sign.
        self.assertEqual(pg.extract_year("1200 AD"), 1200)
        self.assertEqual(pg.extract_year("Aproximadamente 0795 D.C"), 795)
        # Unpadded sub-1000 years stay unmatched (the 4-digit rule is what keeps
        # 'AC' day numbers out); BC dates in this data are all zero-padded.
        self.assertIsNone(pg.extract_year("975 AD"))

    def test_no_year(self):
        self.assertIsNone(pg.extract_year(""))
        self.assertIsNone(pg.extract_year("unknown"))


class TestBasicParse(GedcomTestCase):
    def test_generations_and_leaf(self):
        g = ged(
            indi("@I1@", "Root /R/", "ROOT-001", "M", famc="@F1@"),
            indi("@I2@", "Dad /R/", "DAD0-002", "M", famc="@F2@"),
            indi("@I3@", "Mom /M/", "MOM0-003", "F"),
            indi("@I4@", "Gpa /R/", "GPA0-004", "M"),
            indi("@I5@", "Gma /M/", "GMA0-005", "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
            fam("@F2@", "@I4@", "@I5@", ["@I2@"]),
        )
        by_fid, x2f, people, _ = self.build({"a.ged": g}, root="ROOT-001")
        self.assertEqual(by_fid["ROOT-001"]["generation"], 0)
        self.assertEqual(by_fid["DAD0-002"]["generation"], 1)
        self.assertEqual(by_fid["MOM0-003"]["generation"], 1)
        self.assertEqual(by_fid["GPA0-004"]["generation"], 2)
        # mother is a leaf (no parents); dad is not
        self.assertTrue(by_fid["MOM0-003"]["is_leaf"])
        self.assertFalse(by_fid["DAD0-002"]["is_leaf"])
        # father-first ordering in parent_xrefs[:2]
        self.assertEqual(self.parents(by_fid["ROOT-001"], x2f)[:2], ["DAD0-002", "MOM0-003"])

    def test_root_by_fid(self):
        g = ged(
            indi("@I1@", "Root /R/", "ROOT-001", "M", famc="@F1@"),
            indi("@I2@", "Dad /R/", "DAD0-002", "M"),
            indi("@I3@", "Mom /M/", "MOM0-003", "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
        )
        _, _, people, _ = self.build({"a.ged": g}, root="ROOT-001")
        root = [p for p in people if p["generation"] == 0]
        self.assertEqual(len(root), 1)
        self.assertEqual(root[0]["fs_id"], "ROOT-001")

    def test_birth_and_death_coords(self):
        # both BIRT and DEAT carry MAP coords; the record must keep BOTH pairs
        # (death coords drive the map's place-of-death view).
        coords = ("1 BIRT\n2 DATE 1850\n2 PLAC Leeds, England\n"
                  "3 MAP\n4 LATI 53.8\n4 LONG -1.5\n"
                  "1 DEAT\n2 DATE 1910\n2 PLAC York, England\n"
                  "3 MAP\n4 LATI 53.96\n4 LONG -1.08\n")
        g = ged(
            indi("@I1@", "Root /R/", "ROOT-001", "M", famc="@F1@", extra=coords),
            indi("@I2@", "Dad /R/", "DAD0-002", "M"),
            indi("@I3@", "Mom /M/", "MOM0-003", "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
        )
        by_fid, _, _, _ = self.build({"a.ged": g}, root="ROOT-001")
        r = by_fid["ROOT-001"]
        self.assertAlmostEqual(r["birth_lat"], 53.8)
        self.assertAlmostEqual(r["birth_lon"], -1.5)
        self.assertAlmostEqual(r["death_lat"], 53.96)
        self.assertAlmostEqual(r["death_lon"], -1.08)
        self.assertEqual(r["death_place"], "York, England")


class TestPedigreePreference(GedcomTestCase):
    def _two_couples(self, pedi_birth, pedi_adopt, birth_fids, adopt_fids):
        """Child with two parent couples, one birth one adopted."""
        bf, bm = birth_fids
        af, am = adopt_fids
        return ged(
            indi("@I1@", "Child /C/", "CHLD-001", "M",
                 famc=[("@F1@", pedi_birth), ("@F2@", pedi_adopt)]),
            indi("@I2@", "BioDad /C/", bf, "M"),
            indi("@I3@", "BioMom /B/", bm, "F"),
            indi("@I4@", "AdoptDad /C/", af, "M"),
            indi("@I5@", "AdoptMom /A/", am, "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
            fam("@F2@", "@I4@", "@I5@", ["@I1@"]),
        )

    def test_birth_beats_adopted(self):
        g = self._two_couples("birth", "adopted",
                              ("BBBB-111", "BBBB-112"), ("AAAA-211", "AAAA-212"))
        by_fid, x2f, _, _ = self.build({"a.ged": g}, root="CHLD-001")
        child = by_fid["CHLD-001"]
        self.assertEqual(self.parents(child, x2f)[:2], ["BBBB-111", "BBBB-112"])
        self.assertEqual(child["pedigree"], "biological")
        # both couples still recorded; the adopted one is not preferred
        self.assertEqual(child["num_parent_couples"], 2)
        adopt = [c for c in child["parent_couples"] if c["pedigree"] == "non-biological"]
        self.assertEqual(len(adopt), 1)
        self.assertFalse(adopt[0]["preferred"])

    def test_birth_wins_even_when_adopted_sorts_first(self):
        # adopted couple FIDs sort BEFORE birth couple FIDs; PEDI must still win,
        # proving the choice is pedigree-driven, not alphabetical.
        g = self._two_couples("birth", "adopted",
                              ("ZZZZ-111", "ZZZZ-112"), ("AAAA-211", "AAAA-212"))
        by_fid, x2f, _, _ = self.build({"a.ged": g}, root="CHLD-001")
        self.assertEqual(self.parents(by_fid["CHLD-001"], x2f)[:2],
                         ["ZZZZ-111", "ZZZZ-112"])

    def test_blank_pedi_beats_adopted(self):
        # getmyancestors emits blank PEDI -> must be treated as biological.
        g = self._two_couples(None, "adopted",
                              ("BBBB-111", "BBBB-112"), ("AAAA-211", "AAAA-212"))
        by_fid, x2f, _, _ = self.build({"a.ged": g}, root="CHLD-001")
        self.assertEqual(self.parents(by_fid["CHLD-001"], x2f)[:2],
                         ["BBBB-111", "BBBB-112"])

    def test_half_biological_couple_does_not_borrow_adoptive_parent(self):
        from core import analyze_origins as ao
        from core import payloads
        g = ged(
            indi("@C@", "Child /C/", "CHLD-001", "M",
                 famc=[("@BIO@", "birth"), ("@ADOPT@", "adopted")]),
            indi("@M@", "Biomom /B/", "BIOM-001", "F", extra=placed("Denmark")),
            indi("@AD@", "AdoptDad /A/", "ADAD-001", "M", extra=placed("England")),
            indi("@AM@", "AdoptMom /A/", "AMOM-001", "F", extra=placed("England")),
            fam("@BIO@", wife="@M@", chil=["@C@"]),
            fam("@ADOPT@", "@AD@", "@AM@", ["@C@"]),
        )
        by_fid, _, people, _ = self.build({"a.ged": g}, root="CHLD-001")
        child, mother = by_fid["CHLD-001"], by_fid["BIOM-001"]
        self.assertEqual(ao.parent_slots(child), (None, mother["xref"]))
        by = {p["xref"]: p for p in people}
        origins, untraced, total, _, _ = ao.immigrant_origins(by, child["xref"])
        self.assertEqual((dict(origins), untraced, total), ({"Danish": 0.5}, 0.5, 1.0))
        rec = payloads.fan_payload(people)["recs"][child["xref"]]
        self.assertEqual((rec["fa"], rec["mo"]), (None, mother["xref"]))
        self.assertEqual([r["origin"] for r in payloads.map_payload(people)["immigrants"]],
                         ["Danish"])
        self.assertEqual(child["num_parent_couples"], 2)

    def test_two_blank_couples_deterministic(self):
        # No PEDI at all (the real getmyancestors case). Choice must be stable
        # and based on a deterministic sort of parent FIDs.
        g = self._two_couples(None, None,
                              ("MMMM-111", "MMMM-112"), ("AAAA-211", "AAAA-212"))
        by_fid, x2f, _, _ = self.build({"a.ged": g}, root="CHLD-001")
        first = self.parents(by_fid["CHLD-001"], x2f)[:2]
        # AAAA sorts before MMMM
        self.assertEqual(first, ["AAAA-211", "AAAA-212"])
        # stable across a re-parse
        by_fid2, x2f2, _, _ = self.build({"a.ged": g}, root="CHLD-001")
        self.assertEqual(self.parents(by_fid2["CHLD-001"], x2f2)[:2], first)


def born(year):
    return "1 BIRT\n2 DATE %s\n" % year


class TestConflictingParents(GedcomTestCase):
    """Blank-PEDI couples (the real getmyancestors case) that name different
    parents: the dates, then completeness, must beat alphabetical FID order."""

    def test_impossible_parent(self):
        f = lambda cb, pb, pd, mom=False: pg.impossible_parent(cb, pb, pd, mom)
        self.assertTrue(f(1739, 1730, None))               # father aged 9
        self.assertTrue(f(1700, 1640, None, mom=True))     # mother aged 60
        self.assertTrue(f(1700, 1670, 1699, mom=True))     # mother dead before birth
        self.assertFalse(f(1700, 1670, 1699))              # posthumous son: fine
        self.assertTrue(f(1700, 1670, 1698))               # father dead 2 yrs before
        self.assertTrue(f(-500, -505, None))               # BC: aged 5
        self.assertFalse(f(-500, -530, None))              # BC: aged 30
        self.assertFalse(f(None, 1730, None))              # undated child
        self.assertFalse(f(1739, None, None))              # undated parent

    def test_impossible_couple_loses_even_when_it_sorts_first(self):
        g = ged(
            indi("@I1@", "Lydia /Allen/", "CHLD-001", "F",
                 famc=[("@F1@", None), ("@F2@", None)], extra=born(1739)),
            indi("@I2@", "John /Allen/", "AAAA-111", "M", extra=born(1730)),
            indi("@I3@", "Anne /Wheatly/", "AAAA-112", "F", extra=born(1705)),
            indi("@I4@", "Seth /Allen/", "ZZZZ-211", "M", extra=born(1703)),
            indi("@I5@", "Anne /Whitely/", "ZZZZ-212", "F", extra=born(1705)),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
            fam("@F2@", "@I4@", "@I5@", ["@I1@"]),
        )
        by_fid, x2f, _, _ = self.build({"a.ged": g}, root="CHLD-001")
        self.assertEqual(self.parents(by_fid["CHLD-001"], x2f)[:2],
                         ["ZZZZ-211", "ZZZZ-212"])

    def _mads(self, child_year=None, jens_year=None):
        return ged(
            indi("@I1@", "Mads /Erichsen/", "CHLD-001", "M",
                 famc=[("@F1@", None), ("@F2@", None)],
                 extra=born(child_year) if child_year else ""),
            indi("@I2@", "Jens /Thornoe/", "AAAA-111", "M",
                 extra=born(jens_year) if jens_year else ""),
            indi("@I3@", "Fru /Erichsen/", "AAAA-112", "F"),
            indi("@I4@", "Erik /Matzen/", "ZZZZ-211", "M"),
            indi("@I5@", "Karen /Madsdatter/", "ZZZZ-212", "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
            fam("@F2@", "@I4@", "@I5@", ["@I1@"]),
        )

    def test_ties_are_marked(self):
        # Two complete, undated couples: only FID order separates them -> both tied.
        by_fid, _, _, _ = self.build({"a.ged": self._mads()}, root="CHLD-001")
        self.assertEqual([c["tied"] for c in by_fid["CHLD-001"]["parent_couples"]], [True, True])
        # ...but a couple the dates rule out (Jens aged 5) breaks the tie.
        by_fid, _, _, _ = self.build({"b.ged": self._mads(1705, 1700)}, root="CHLD-001")
        self.assertEqual([c["tied"] for c in by_fid["CHLD-001"]["parent_couples"]], [False, False])

    def test_full_couple_beats_half_couple(self):
        g = ged(
            indi("@I1@", "Isabel /Bradborne/", "CHLD-001", "F",
                 famc=[("@F1@", None), ("@F2@", None)]),
            indi("@I2@", "John /Hough/", "AAAA-111", "M"),
            indi("@I4@", "John /Bradburne/", "ZZZZ-211", "M"),
            indi("@I5@", "Anne /Vernon/", "ZZZZ-212", "F"),
            fam("@F1@", "@I2@", None, ["@I1@"]),
            fam("@F2@", "@I4@", "@I5@", ["@I1@"]),
        )
        by_fid, x2f, _, _ = self.build({"a.ged": g}, root="CHLD-001")
        self.assertEqual(self.parents(by_fid["CHLD-001"], x2f)[:2],
                         ["ZZZZ-211", "ZZZZ-212"])
        # completeness is only a tiebreak: both claims stay open to core.parents
        self.assertEqual([c["tied"] for c in by_fid["CHLD-001"]["parent_couples"]], [True, True])


def placed(place):
    return "1 BIRT\n2 PLAC %s\n" % place


class TestUnnamedWives(GedcomTestCase):
    """A wife recorded under her husband's name ("Mrs. Charles Baker" -> a woman
    called "Charles Baker") is renamed for display, and a birthplace that is just
    his -- or a vaguer version of it -- isn't counted as hers."""

    def test_detection_and_copied_places(self):
        g = ged(
            indi("@K1@", "Mary /Baker/", "KID1-001", "F", famc="@F1@"),
            indi("@H1@", "Charles /Baker/", "HUSB-001", "M", extra=placed("Nantwich, Cheshire, England")),
            indi("@W1@", "Charles /Baker/", "WIFE-001", "F", extra=placed("Nantwich, Cheshire, England")),
            indi("@K2@", "Ann /Welles/", "KID2-001", "F", famc="@F2@"),
            indi("@H2@", "Thomas /Welles/", "HUSB-002", "M", extra=placed("Canterbury, Kent, England")),
            indi("@W2@", "Mrs. /Welles/", "WIFE-002", "F", extra=placed("of Kent, England")),
            indi("@K3@", "Jens /Holm/", "KID3-001", "M", famc="@F3@"),
            indi("@H3@", "Peder /Holm/", "HUSB-003", "M", extra=placed("Essex, England")),
            indi("@W3@", "Peder /Holm/", "WIFE-003", "F", extra=placed("Odense, Denmark")),
            indi("@K4@", "Tom /Hill/", "KID4-001", "M", famc="@F4@"),
            indi("@H4@", "John /Hill/", "HUSB-004", "M", extra=placed("Kent, England")),
            indi("@W4@", "Joan /Hill/", "WIFE-004", "F", extra=placed("Kent, England")),
            fam("@F1@", "@H1@", "@W1@", ["@K1@"]),
            fam("@F2@", "@H2@", "@W2@", ["@K2@"]),
            fam("@F3@", "@H3@", "@W3@", ["@K3@"]),
            fam("@F4@", "@H4@", "@W4@", ["@K4@"]),
        )
        by_fid, x2f, _, _ = self.build({"a.ged": g}, root="KID1-001")
        w1, w2, w3, w4 = (by_fid["WIFE-00%d" % i] for i in (1, 2, 3, 4))
        # exact copy: renamed, FS name kept, placeholder name parts cleared, place copied
        self.assertEqual((w1["name"], w1["fs_name"], w1["surname"]),
                         ("Wife of Charles Baker", "Charles Baker", ""))
        self.assertEqual(x2f[w1["wife_of"]], "HUSB-001")
        self.assertTrue(w1["place_copied"])
        # "Mrs." placeholder keeps its name; "of Kent" is a vaguer Canterbury, Kent
        self.assertEqual(w2["name"], "Mrs. Welles")
        self.assertTrue(w2["place_copied"])
        # her own, different birthplace is information, not a copy
        self.assertIn("wife_of", w3)
        self.assertNotIn("place_copied", w3)
        # a real wife who merely shares his birthplace is untouched
        self.assertNotIn("wife_of", w4)


class TestMergeDeeperPull(GedcomTestCase):
    def test_dedup_and_regenerate_generations(self):
        # File A: root -> dad -> grandpa (grandpa is a leaf: the -a wall).
        a = ged(
            indi("@I1@", "Root /R/", "ROOT-001", "M", famc="@F1@"),
            indi("@I2@", "Dad /R/", "DAD0-002", "M", famc="@F2@"),
            indi("@I3@", "Mom /M/", "MOM0-003", "F"),
            indi("@I4@", "Gpa /R/", "GPA0-004", "M"),   # leaf here
            indi("@I5@", "Gma /M/", "GMA0-005", "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
            fam("@F2@", "@I4@", "@I5@", ["@I2@"]),
        )
        # File B: a frontier pull starting at grandpa GPA0-004, adding HIS parents.
        # Note the reused FID GPA0-004 but DIFFERENT xref numbers -> dedup by FID.
        b = ged(
            indi("@I1@", "Gpa /R/", "GPA0-004", "M", famc="@F1@"),
            indi("@I2@", "GGpa /R/", "GGPA-006", "M"),
            indi("@I3@", "GGma /M/", "GGMA-007", "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
        )
        # single-file: grandpa is a leaf at gen 2, no gen 3
        by1, _, p1, _ = self.build({"a.ged": a}, root="ROOT-001")
        self.assertTrue(by1["GPA0-004"]["is_leaf"])
        self.assertNotIn("GGPA-006", by1)

        # merged: grandpa gains parents, gen 3 appears, no duplicate grandpa
        by2, _, p2, _ = self.build({"a.ged": a, "b.ged": b}, root="ROOT-001")
        self.assertFalse(by2["GPA0-004"]["is_leaf"])
        self.assertEqual(by2["GGPA-006"]["generation"], 3)
        self.assertEqual(by2["GGMA-007"]["generation"], 3)
        # exactly one grandpa record (deduped by FID)
        self.assertEqual(sum(1 for p in p2 if p["fs_id"] == "GPA0-004"), 1)
        self.assertEqual(len(p2), len(p1) + 2)   # only the two new ancestors added

    def test_merge_is_order_independent_for_people(self):
        a = ged(
            indi("@I1@", "Root /R/", "ROOT-001", "M", famc="@F1@"),
            indi("@I2@", "Dad /R/", "DAD0-002", "M"),
            indi("@I3@", "Mom /M/", "MOM0-003", "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
        )
        b = ged(
            indi("@I1@", "Dad /R/", "DAD0-002", "M", famc="@F1@"),
            indi("@I2@", "Gpa /R/", "GPA0-004", "M"),
            indi("@I3@", "Gma /M/", "GMA0-005", "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
        )
        by_ab, _, _, _ = self.build({"a.ged": a, "b.ged": b}, root="ROOT-001")
        by_ba, _, _, _ = self.build({"b.ged": b, "a.ged": a}, root="ROOT-001")
        self.assertEqual({k: v["generation"] for k, v in by_ab.items()},
                         {k: v["generation"] for k, v in by_ba.items()})


class TestBiologicalInjection(GedcomTestCase):
    """A hypothetical adoption case: FamilySearch does NOT link the adopted father to
    his biological parents, so a separate pull of the bio line arrives as a
    disconnected component. Only an injected edge connects it."""

    def files(self):
        # File A (wife's tree): wife -> adopted father (a leaf, no FS parents).
        a = ged(
            indi("@I1@", "Wife /W/", "WIFE-001", "F", famc="@F1@"),
            indi("@I2@", "AdoptedDad /W/", "ADAD-002", "M"),  # leaf, no parents in FS
            indi("@I3@", "WifeMom /M/", "WMOM-003", "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
        )
        # File B (separate pull at the biological grandfather's line): the bio
        # parents + a bio great-grandfather. ADAD-002 is absent (FS never links).
        b = ged(
            indi("@I1@", "BioGpa /B/", "BIGF-011", "M", famc="@F1@"),
            indi("@I2@", "BioGGpa /B/", "BGGF-021", "M"),
            indi("@I3@", "BioMom /B/", "BIGM-012", "F"),
            fam("@F1@", "@I2@", None, ["@I1@"]),
        )
        return {"a.ged": a, "b.ged": b}

    def test_without_override_bio_line_is_disconnected(self):
        by_fid, _, _, _ = self.build(self.files(), root="WIFE-001")
        # adopted father is still a leaf; bio people are off the direct line
        self.assertTrue(by_fid["ADAD-002"]["is_leaf"])
        self.assertIsNone(by_fid["BIGF-011"]["generation"])
        self.assertFalse(by_fid["BIGF-011"]["on_direct_line"])

    def test_override_injects_and_connects_bio_line(self):
        overrides = {"ADAD-002": {"father": "BIGF-011", "mother": "BIGM-012",
                                  "pedigree": "biological"}}
        by_fid, x2f, _, model = self.build(self.files(), root="WIFE-001",
                                           overrides=overrides)
        adad = by_fid["ADAD-002"]
        # the edge now exists: adopted father is no longer a leaf...
        self.assertFalse(adad["is_leaf"])
        # ...and his biological parents lead parent_xrefs[:2]
        self.assertEqual(self.parents(adad, x2f)[:2], ["BIGF-011", "BIGM-012"])
        # generations flow up the connected biological line
        self.assertEqual(by_fid["ADAD-002"]["generation"], 1)
        self.assertEqual(by_fid["BIGF-011"]["generation"], 2)
        self.assertEqual(by_fid["BIGM-012"]["generation"], 2)
        self.assertEqual(by_fid["BGGF-021"]["generation"], 3)  # great-grandfather
        self.assertTrue(by_fid["BIGF-011"]["on_direct_line"])
        self.assertEqual(len(model.injected), 1)

    def test_override_to_missing_parent_is_reported(self):
        # bio parents were never pulled -> override edge points at nothing.
        a = ged(
            indi("@I1@", "Wife /W/", "WIFE-001", "F", famc="@F1@"),
            indi("@I2@", "AdoptedDad /W/", "ADAD-002", "M"),
            indi("@I3@", "WifeMom /M/", "WMOM-003", "F"),
            fam("@F1@", "@I2@", "@I3@", ["@I1@"]),
        )
        overrides = {"ADAD-002": {"father": "NONE-999", "mother": "NONE-998"}}
        _, _, _, model = self.build({"a.ged": a}, root="WIFE-001", overrides=overrides)
        missing = {pid for _, pid in model.missing_overrides}
        self.assertEqual(missing, {"NONE-999", "NONE-998"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
