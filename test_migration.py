"""API/browser migration grouping contract, shared with web/migration.test.cjs."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from core import payloads


FIXTURE = Path(__file__).parent / "tests" / "fixtures" / "migration.json"


class MigrationGroupingTests(unittest.TestCase):
    def test_shared_migration_cases(self):
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
        for case in cases:
            with self.subTest(case=case["name"]):
                rows = [{"origin": origin, "settlement": settlement}
                        for origin, settlement, count in case["routes"] for _ in range(count)]
                direct = {str(i): row for i, row in enumerate(rows)}
                colors = case.get("colors", {})
                # Isolate grouping from country/place recognition; unknown settlements
                # still exercise the API's missing-region fallback.
                with patch.object(payloads.ao, "origin_of", side_effect=lambda p: (p["origin"], True, None)), \
                     patch.object(payloads.ao, "settlement_of", side_effect=lambda p: (
                         None if p["settlement"] == "(region unknown)" else p["settlement"])):
                    for order in (list(direct), list(reversed(direct))):
                        result = payloads._sankey(direct, direct, order, colors)
                        actual = {"routes": [[r["origin"], r["settlement"], r["count"]]
                                             for r in result["flows"]],
                                  "total": result["total"], "settled": result["settled"]}
                        self.assertEqual(actual, case["expected"])
                        for flow in result["flows"]:
                            self.assertEqual(flow["color"], colors.get(flow["origin"], "#6b7280"))


if __name__ == "__main__":
    unittest.main()
