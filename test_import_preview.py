"""Starting-person preview, reupload validation and temporary-upload boundaries."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_api import FIXTURE, _HAVE_API

if _HAVE_API:
    from fastapi.testclient import TestClient
    from api import main
    from api.db import SessionLocal
    from api import store
    from core.parse_gedcom import build_people, preview_people


FIRST = b"""0 HEAD
0 @P@ INDI
1 NAME Shared /Parent/
1 _FSFTID PARN-001
0 @C1@ INDI
1 NAME First /Child/
1 BIRT
2 DATE 1980
2 PLAC Provo, Utah
0 @C2@ INDI
1 NAME Second /Child/
0 @F@ FAM
1 HUSB @P@
1 CHIL @C1@
1 CHIL @C2@
0 TRLR
"""
SECOND = b"""0 HEAD
0 @P@ INDI
1 NAME Shared /Parent/
1 BIRT
2 DATE 1950
2 PLAC York, England
1 _FSFTID PARN-001
0 @C1@ INDI
1 NAME Other /Person/
1 BIRT
2 DATE 1977
2 PLAC Boise, Idaho
0 TRLR
"""


@unittest.skipUnless(_HAVE_API, "needs API dependencies")
class TestImportPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        response = cls.client.post("/api/auth/register", json={
            "email": "import-preview@example.com", "password": "password123"})
        assert response.status_code == 200, response.text
        cls.owner_id = response.json()["id"]

    def tearDown(self):
        for tree in self.client.get("/api/trees").json():
            self.client.delete(f"/api/trees/{tree['id']}")

    def files(self):
        return [("files", ("first.ged", FIRST)), ("files", ("second.ged", SECOND))]

    def test_preview_is_authenticated_stateless_and_does_not_enrich(self):
        self.assertEqual(TestClient(main.app).post("/api/trees/preview", files=self.files()).status_code, 401)
        with mock.patch.object(main, "_enrich", side_effect=AssertionError("preview ran enrichment")):
            response = self.client.post("/api/trees/preview", files=self.files())
            again = self.client.post("/api/trees/preview", files=self.files())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), again.json())
        preview = response.json()
        self.assertEqual(preview["candidate_count"], 2)
        self.assertEqual(preview["suggested_root"], "F0:@C1@")
        people = {person["id"]: person for person in preview["people"]}
        self.assertEqual(len(people), 4)
        self.assertEqual(people["PARN-001"], {"id": "PARN-001", "name": "Shared Parent",
                                             "year": 1950, "place": "York, England"})
        self.assertEqual(people["F1:@C1@"]["name"], "Other Person")
        self.assertEqual(people["F0:@C2@"]["year"], None)
        self.assertEqual(people["F0:@C2@"]["place"], None)
        self.assertEqual(self.client.get("/api/trees").json(), [])

    def test_any_preview_person_can_be_chosen_including_second_file_without_fid(self):
        for root, name in (("F1:@C1@", "Other Person"), ("PARN-001", "Shared Parent")):
            with self.subTest(root=root):
                response = self.client.post("/api/trees", files=self.files(), data={"root": root})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["meta"]["root"], name)

    def test_changed_reupload_rejects_a_person_not_in_the_new_files(self):
        response = self.client.post("/api/trees", files=[self.files()[0]], data={"root": "F1:@C1@"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("preview again", response.json()["detail"])
        self.assertEqual(self.client.get("/api/trees").json(), [])

    def test_automatic_and_legacy_xref_roots_still_work(self):
        for data in ({}, {"root": "@C2@"}):
            response = self.client.post("/api/trees", files=self.files(), data=data)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["meta"]["root"], "Second Child" if data else "First Child")

    def test_source_filenames_survive_creation_listing_meta_and_export(self):
        response = self.client.post("/api/trees", files=[("files", ("C:\\private\\sample.ged", FIXTURE.read_bytes()))])
        self.assertEqual(response.status_code, 200, response.text)
        tree = response.json()
        self.assertEqual(tree["meta"]["source_files"], ["sample.ged"])
        self.assertEqual(self.client.get("/api/trees").json()[0]["meta"]["source_files"], ["sample.ged"])
        for route in ("meta", "export"):
            result = self.client.get(f"/api/trees/{tree['id']}/{route}").json()
            meta = result if route == "meta" else result["meta"]
            self.assertEqual(meta["source_files"], ["sample.ged"])

    def test_existing_store_callers_need_no_source_metadata(self):
        people, _, _ = build_people([FIXTURE])
        with SessionLocal() as db:
            tree = store.create_tree(db, self.owner_id, people)
        self.assertNotIn("source_files", tree["meta"])
        self.assertNotIn("source_files", self.client.get(f"/api/trees/{tree['id']}/meta").json())

    def test_no_family_falls_back_to_all_people_with_stable_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "standalone.ged"
            path.write_bytes(SECOND)
            preview = preview_people([path])
            self.assertEqual(preview["candidate_count"], 2)
            self.assertEqual({person["id"] for person in preview["people"]}, {"PARN-001", "F0:@C1@"})

    def test_both_routes_cleanup_temporary_files_on_success_failure_and_size_limit(self):
        make_temp = tempfile.mkdtemp
        for route in ("/api/trees/preview", "/api/trees"):
            for data, limit, status in ((FIRST, 10000, 200), (b"not GEDCOM", 10000, 400), (FIRST, 1, 413)):
                created = []
                def track_temp(*args, **kwargs):
                    directory = make_temp(*args, **kwargs)
                    created.append(Path(directory))
                    return directory
                with self.subTest(route=route, status=status), \
                        mock.patch.object(main.tempfile, "mkdtemp", track_temp), \
                        mock.patch.object(main, "MAX_UPLOAD_BYTES", limit):
                    response = self.client.post(route, files={"files": ("test.ged", data)})
                self.assertEqual(response.status_code, status, response.text)
                self.assertTrue(created)
                self.assertTrue(all(not directory.exists() for directory in created))

    def test_upload_limit_applies_to_the_total_across_files_on_both_routes(self):
        for route in ("/api/trees/preview", "/api/trees"):
            with self.subTest(route=route), mock.patch.object(main, "MAX_UPLOAD_BYTES", len(FIRST) + len(SECOND) - 1):
                self.assertEqual(self.client.post(route, files=self.files()).status_code, 413)

    def test_preview_rejects_empty_and_invalid_utf8_exports(self):
        for data in (b"", b"0 HEAD\n0 TRLR\n", b"0 @I1@ INDI\n1 NAME \xff"):
            self.assertEqual(self.client.post("/api/trees/preview", files={"files": ("empty.ged", data)}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
