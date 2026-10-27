"""Persistent local configuration, using only temporary data and the stdlib."""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from api.config import https_only, session_secret


class TestConfig(unittest.TestCase):
    def test_generated_secret_survives_restart_and_concurrent_starts(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ, {"SESSION_SECRET": "", "APP_DATA_DIR": directory}):
            with ThreadPoolExecutor(max_workers=8) as workers:
                values = list(workers.map(lambda _: session_secret(), range(16)))
            self.assertEqual(len(set(values)), 1)
            self.assertEqual(len(values[0]), 64)
            self.assertEqual(session_secret(), values[0])
            self.assertEqual([p.name for p in Path(directory).iterdir()], ["session-secret"])

    def test_separate_installations_have_different_secrets(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            with mock.patch.dict(os.environ, {"SESSION_SECRET": "", "APP_DATA_DIR": first}):
                one = session_secret()
            with mock.patch.dict(os.environ, {"SESSION_SECRET": "", "APP_DATA_DIR": second}):
                self.assertNotEqual(session_secret(), one)

    def test_explicit_secret_does_not_create_local_data(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ, {"SESSION_SECRET": "deployment-secret", "APP_DATA_DIR": directory}):
            self.assertEqual(session_secret(), "deployment-secret")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_empty_existing_secret_fails_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ, {"SESSION_SECRET": "", "APP_DATA_DIR": directory}):
            path = Path(directory) / "session-secret"
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "empty"):
                session_secret()
            self.assertEqual(path.read_text(encoding="utf-8"), "")

    def test_https_cookie_setting_is_explicit(self):
        for value, expected in (("0", False), ("false", False), ("", False),
                                ("1", True), ("true", True), ("YES", True)):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"SESSION_HTTPS_ONLY": value}):
                self.assertEqual(https_only(), expected)
        with mock.patch.dict(os.environ, {"SESSION_HTTPS_ONLY": "maybe"}):
            with self.assertRaises(ValueError):
                https_only()


if __name__ == "__main__":
    unittest.main()
