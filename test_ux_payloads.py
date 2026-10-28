"""Location text and life dates remain useful when a file has no coordinates."""
import copy
from pathlib import Path
import unittest

import core


class TestLocationFallback(unittest.TestCase):
    def test_text_and_death_dates_survive_without_embedded_coordinates(self):
        example = Path(__file__).parent / "web" / "public" / "example.ged"
        people, _, _ = core.build_people([str(example)])
        people = copy.deepcopy(people)
        for person in people:
            for field in ("birth_lat", "birth_lon", "death_lat", "death_lon"):
                person[field] = None
        payload = core.map_payload(people)
        self.assertEqual(payload["meta"]["n_coords"], 0)
        self.assertTrue(payload["country_data"])
        wren = next(p for p in payload["people"] if p["name"] == "Wren Ferncrest")
        self.assertEqual(wren["place"], "Bergen, Norway")
        self.assertEqual(wren["dyear"], 2008)
        self.assertNotIn("lat", wren)
        self.assertNotIn("dlat", wren)
        self.assertEqual(wren["missing_parents"], 2)
        avery = next(p for p in payload["people"] if p["name"] == "Avery Example")
        self.assertEqual(avery["missing_parents"], 0)
