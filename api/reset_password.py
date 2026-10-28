"""Reset a local account password from the installation's own terminal."""
import argparse
from contextlib import closing
import getpass
import warnings

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .auth import hash_password
from .db import get_db
from .models import User


def reset_password(db: Session, email: str, password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None:
        raise ValueError("No local account exists for that email. No account was changed.")
    # shortcut: existing browser sessions stay valid; add session revocation before remote recovery.
    user.pw_hash, user.pw_salt = hash_password(password)
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Email of the existing local account")
    args = parser.parse_args()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("New password (at least 8 characters): ")
            confirmation = getpass.getpass("Repeat new password: ")
        if password != confirmation:
            parser.error("Passwords did not match. No account was changed.")
        with closing(get_db()) as sessions:
            reset_password(next(sessions), args.email, password)
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        parser.error("Use an interactive terminal with hidden password input. No account was changed.")
    except ValueError as error:
        parser.error(str(error))
    except SQLAlchemyError:
        parser.error("Could not update the account. Check this installation's database configuration.")
    print("Password changed. Sign in with the new password. Existing browser sessions remain signed in.")


if __name__ == "__main__":
    main()
