"""Account recovery uses only an isolated in-memory database."""
from importlib.util import find_spec
from io import StringIO
import unittest
from unittest import mock

_HAVE_API = all(find_spec(name) is not None for name in ("fastapi", "sqlalchemy"))
if _HAVE_API:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from api.auth import hash_password, verify_password
    from api.db import Base
    from api.models import Tree, User
    from api.reset_password import main, reset_password


@unittest.skipUnless(_HAVE_API, "needs fastapi + sqlalchemy")
class TestResetPassword(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        pw_hash, salt = hash_password("old-password")
        self.user = User(email="person@example.com", pw_hash=pw_hash, pw_salt=salt)
        self.other = User(email="other@example.com", pw_hash=pw_hash, pw_salt=salt)
        self.db.add_all([self.user, self.other])
        self.db.flush()
        self.tree = Tree(id="saved-tree", owner_id=self.user.id, meta={"root": "Example"}, people=[])
        self.db.add(self.tree)
        self.db.commit()

    def test_reset_changes_only_the_selected_account_password(self):
        old_hash, old_salt, user_id = self.user.pw_hash, self.user.pw_salt, self.user.id
        reset_password(self.db, " PERSON@example.com ", "new-password")
        self.db.expire_all()
        self.assertEqual(self.user.id, user_id)
        self.assertNotEqual(self.user.pw_salt, old_salt)
        self.assertTrue(verify_password("new-password", self.user.pw_hash, self.user.pw_salt))
        self.assertFalse(verify_password("old-password", self.user.pw_hash, self.user.pw_salt))
        self.assertEqual(self.other.pw_hash, old_hash)
        self.assertEqual(self.tree.owner_id, user_id)
        self.assertEqual(self.tree.meta, {"root": "Example"})
        self.assertEqual(self.db.query(User).count(), 2)

    def test_invalid_password_or_missing_account_changes_nothing(self):
        before = [(u.id, u.pw_hash, u.pw_salt) for u in self.db.query(User).all()]
        for email, password in (("person@example.com", "short"), ("missing@example.com", "new-password")):
            with self.subTest(email=email), self.assertRaises(ValueError):
                reset_password(self.db, email, password)
        self.assertEqual([(u.id, u.pw_hash, u.pw_salt) for u in self.db.query(User).all()], before)

    def test_cli_mismatch_does_not_open_the_database(self):
        with mock.patch("sys.argv", ["reset_password", "person@example.com"]), \
                mock.patch("api.reset_password.getpass.getpass", side_effect=["new-password", "different"]), \
                mock.patch("api.reset_password.get_db") as database, \
                mock.patch("sys.stderr", new_callable=StringIO) as error:
            with self.assertRaises(SystemExit) as result:
                main()
            self.assertEqual(result.exception.code, 2)
            database.assert_not_called()
            self.assertIn("Passwords did not match", error.getvalue())
            self.assertNotIn("new-password", error.getvalue())

    def test_cli_uses_hidden_prompts_and_existing_database_session(self):
        closed = []

        def database():
            try:
                yield self.db
            finally:
                closed.append(True)

        with mock.patch("sys.argv", ["reset_password", "person@example.com"]), \
                mock.patch("api.reset_password.getpass.getpass", side_effect=["new-password"] * 2) as prompts, \
                mock.patch("api.reset_password.get_db", database), \
                mock.patch("sys.stdout", new_callable=StringIO) as output:
            main()
            self.assertEqual(prompts.call_count, 2)
            self.assertEqual(closed, [True])
            self.assertTrue(verify_password("new-password", self.user.pw_hash, self.user.pw_salt))
            self.assertIn("Password changed", output.getvalue())
            self.assertNotIn("new-password", output.getvalue())


if __name__ == "__main__":
    unittest.main()
