"""test_api.py -- web API contract + auth/isolation tests via FastAPI TestClient.

Run (with the web deps installed):  .venv/Scripts/python.exe test_api.py

Uses an isolated temp SQLite DB and open registration (no INVITE_CODE). Skips
automatically if fastapi/httpx aren't importable, so a stdlib-only checkout
stays green.
"""
import os
from importlib.util import find_spec
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Isolated DB + open registration -- MUST be set before importing the app.
_TMP_DB = Path(tempfile.mkdtemp(prefix="ft_api_test_")) / "app.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ.pop("INVITE_CODE", None)
os.environ["SESSION_SECRET"] = "test-secret"

_HAVE_API = all(find_spec(name) is not None for name in
                ("fastapi", "httpx", "sqlalchemy", "anyio", "itsdangerous", "multipart"))
if _HAVE_API:
    from fastapi.testclient import TestClient
    from api.main import app

FIXTURE = Path(__file__).resolve().parent / "tests" / "fixtures" / "sample.ged"


@unittest.skipUnless(_HAVE_API, "needs fastapi + httpx + sqlalchemy")
class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)  # user A (cookie jar persists the session)
        r = cls.client.post("/api/auth/register",
                            json={"email": "a@example.com", "password": "password123"})
        assert r.status_code == 200, r.text
        with open(FIXTURE, "rb") as fh:
            up = cls.client.post("/api/trees",
                                 files={"files": ("sample.ged", fh, "text/plain")})
        assert up.status_code == 200, up.text
        cls.tree = up.json()
        cls.id = cls.tree["id"]

    def test_health_is_open(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})

    def test_me(self):
        self.assertEqual(self.client.get("/api/auth/me").json()["email"], "a@example.com")

    def test_upload_returns_meta(self):
        self.assertEqual(self.tree["meta"]["n_people"], 7)
        self.assertEqual(self.tree["meta"]["root"], "Kid Example")

    def test_list_my_trees(self):
        trees = self.client.get("/api/trees").json()
        self.assertEqual([t["id"] for t in trees], [self.id])

    def test_listing_does_not_select_people(self):
        from sqlalchemy import event
        from api.db import engine

        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        event.listen(engine, "before_cursor_execute", capture)
        try:
            self.assertEqual(self.client.get("/api/trees").status_code, 200)
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        selects = [sql for sql in statements if "from trees" in sql]
        self.assertTrue(selects)
        self.assertFalse(any("trees.people" in sql for sql in selects))

    def test_origins_endpoint(self):
        o = self.client.get(f"/api/trees/{self.id}/origins").json()
        imm = {b["name"]: b["pct"] for b in o["models"]["immigrant"]["breakdown"]}
        self.assertAlmostEqual(imm["Danish"], 25.0, places=1)

    def test_map_endpoint(self):
        m = self.client.get(f"/api/trees/{self.id}/map").json()
        self.assertEqual(len(m["people"]), 7)
        self.assertEqual(len(m["immigrants"]), 2)
        self.assertEqual(m["immigrant_count"], 2)

    def test_fan_and_deadends(self):
        self.assertEqual(len(self.client.get(f"/api/trees/{self.id}/fan").json()["recs"]), 7)
        self.assertAlmostEqual(
            self.client.get(f"/api/trees/{self.id}/deadends").json()["untraced_pct"], 50.0, places=1)

    # ---- auth / isolation --------------------------------------------------
    def test_unauthenticated_is_401(self):
        anon = TestClient(app)  # fresh, no session
        self.assertEqual(anon.get(f"/api/trees/{self.id}/map").status_code, 401)
        self.assertEqual(anon.get("/api/trees").status_code, 401)

    def test_other_user_cannot_see_my_tree(self):
        other = TestClient(app)
        r = other.post("/api/auth/register",
                       json={"email": "b@example.com", "password": "password123"})
        self.assertEqual(r.status_code, 200)
        # user B is authenticated but must not reach user A's tree
        self.assertEqual(other.get(f"/api/trees/{self.id}/map").status_code, 404)
        self.assertEqual(other.get("/api/trees").json(), [])

    def test_login_logout(self):
        c = TestClient(app)
        c.post("/api/auth/register", json={"email": "c@example.com", "password": "password123"})
        self.assertEqual(c.post("/api/auth/logout").json(), {"ok": True})
        self.assertEqual(c.get("/api/auth/me").status_code, 401)
        self.assertEqual(
            c.post("/api/auth/login",
                   json={"email": "c@example.com", "password": "password123"}).status_code, 200)
        self.assertEqual(c.get("/api/auth/me").json()["email"], "c@example.com")

    def test_delete_tree(self):
        c = TestClient(app)
        c.post("/api/auth/register", json={"email": "d@example.com", "password": "password123"})
        with open(FIXTURE, "rb") as fh:
            tid = c.post("/api/trees", files={"files": ("s.ged", fh, "text/plain")}).json()["id"]
        self.assertEqual(c.delete(f"/api/trees/{tid}").json(), {"ok": True})
        self.assertEqual(c.get(f"/api/trees/{tid}/map").status_code, 404)

    def test_bad_login_401(self):
        self.assertEqual(
            self.client.post("/api/auth/login",
                             json={"email": "a@example.com", "password": "wrong"}).status_code, 401)

    def test_garbage_upload_is_400(self):
        resp = self.client.post("/api/trees",
                                files={"files": ("x.ged", b"this is not a gedcom", "text/plain")})
        self.assertEqual(resp.status_code, 400)

    def test_export_owner_only(self):
        r = self.client.get(f"/api/trees/{self.id}/export")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers.get("content-disposition", ""))
        body = r.json()
        self.assertEqual(len(body["people"]), 7)
        self.assertIn("living_count", body["meta"])
        # another user can't export this tree
        other = TestClient(app)
        other.post("/api/auth/register",
                   json={"email": "e@example.com", "password": "password123"})
        self.assertEqual(other.get(f"/api/trees/{self.id}/export").status_code, 404)

    def test_meta_has_living_count(self):
        self.assertIn("living_count", self.client.get(f"/api/trees/{self.id}/meta").json())

    def test_upload_does_not_block_requests_and_uses_worker_session(self):
        import threading
        from api import main

        entered, release, healthy = (threading.Event() for _ in range(3))
        parser_threads, session_threads, replies = [], [], []
        parse, session_factory = main.build_people, main.SessionLocal

        def waiting_parse(*args):
            parser_threads.append(threading.get_ident())
            entered.set()
            if not release.wait(10):
                raise AssertionError("upload worker was not released")
            return parse(*args)

        def worker_session():
            session_threads.append(threading.get_ident())
            return session_factory()

        with TestClient(app) as client, mock.patch.object(main, "build_people", waiting_parse), \
                mock.patch.object(main, "SessionLocal", worker_session):
            client.cookies.update(self.client.cookies)
            def upload():
                replies.append(client.post("/api/trees", files={"files": ("s.ged", FIXTURE.read_bytes())}))
            def health():
                if client.get("/api/health").status_code == 200:
                    healthy.set()
            uploading = threading.Thread(target=upload)
            uploading.start()
            try:
                self.assertTrue(entered.wait(5), "upload did not reach parsing")
                checking = threading.Thread(target=health)
                checking.start()
                try:
                    self.assertTrue(healthy.wait(3), "parser blocked the server event loop")
                finally:
                    release.set()
                    checking.join(5)
            finally:
                release.set()
                uploading.join(10)
            self.assertFalse(uploading.is_alive())
            self.assertEqual(replies[0].status_code, 200, replies[0].text)
            self.assertEqual(parser_threads, session_threads)
            client.delete(f"/api/trees/{replies[0].json()['id']}")

    def test_startup_errors_are_not_treated_as_missing_dependencies(self):
        import builtins
        import runpy

        original_import = builtins.__import__
        def broken_startup(name, *args, **kwargs):
            if name == "api.main":
                raise RuntimeError("simulated application startup failure")
            return original_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ), \
                mock.patch("tempfile.gettempdir", return_value=tmp), \
                mock.patch("builtins.__import__", broken_startup):
            with self.assertRaisesRegex(RuntimeError, "simulated application startup failure"):
                runpy.run_path(str(Path(__file__).resolve()), run_name="startup_guard_check")


@unittest.skipUnless(_HAVE_API, "needs fastapi + httpx + sqlalchemy")
class TestStaticSite(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from fastapi.staticfiles import StaticFiles
        from api import main

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.public = self.base / "public"
        (self.public / "assets").mkdir(parents=True)
        (self.public / "index.html").write_text("app shell", encoding="utf-8")
        (self.public / "readme.txt").write_text("public file", encoding="utf-8")
        (self.public / "assets" / "app.js").write_text("public asset", encoding="utf-8")
        (self.base / "private.txt").write_text("private marker", encoding="utf-8")
        (self.base / "public-other").mkdir()
        (self.base / "public-other" / "secret.txt").write_text("private marker", encoding="utf-8")
        patch = mock.patch.object(main, "_WEB_DIST", self.public)
        patch.start()
        self.addCleanup(patch.stop)
        site = FastAPI()
        site.mount("/assets", StaticFiles(directory=self.public / "assets"))
        site.get("/{full_path:path}")(main.spa)
        self.client = TestClient(site)

    def test_public_files_assets_and_deep_links_still_work(self):
        for path, body in (("/", "app shell"), ("/tree/example", "app shell"),
                           ("/readme.txt", "public file"), ("/assets/app.js", "public asset")):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual((response.status_code, response.text), (200, body))
        self.assertEqual(self.client.get("/api/missing").status_code, 404)

    def test_encoded_traversal_and_malformed_paths_are_rejected(self):
        for path in ("/%2e%2e/private.txt", "/..%2fprivate.txt",
                     "/%2e%2e/public-other/secret.txt", "/%00",
                     "/assets/%2e%2e/%2e%2e/private.txt"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_windows_anchored_and_backslash_paths_are_rejected(self):
        if os.name != "nt":
            return  # These forms are ordinary filenames on POSIX, not anchored paths.
        for path in ("/..%5cprivate.txt", "/C%3Aprivate.txt", "/C%3A%5cprivate.txt",
                     "/%5cprivate.txt", "/%5c%5clocalhost%5cshare%5cprivate.txt",
                     "/%5c%5c%3F%5cC%3A%5cprivate.txt"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_filesystem_link_cannot_escape_public_directory(self):
        link = self.public / "outside"
        try:
            link.symlink_to(self.base / "public-other", target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            # Windows directory junctions need no symlink privilege.
            import subprocess
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link),
                            str(self.base / "public-other")], check=True, capture_output=True)
        self.assertEqual(self.client.get("/outside/secret.txt").status_code, 404)

    def test_index_fallback_cannot_follow_an_outside_link(self):
        index = self.public / "index.html"
        outside = self.base / "private.txt"
        index.unlink()
        try:
            index.symlink_to(outside)
        except OSError:
            if os.name != "nt":
                raise
            # Exercise the resolved link target when Windows denies file symlinks.
            resolve = Path.resolve
            patch = mock.patch.object(Path, "resolve", lambda p, *a, **kw:
                                      resolve(outside) if p == index else resolve(p, *a, **kw))
            patch.start()
            self.addCleanup(patch.stop)
        for path in ("/", "/tree/example", "/index.html"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
