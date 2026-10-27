"""Local app configuration; generated secrets belong with the persistent data."""
import os
import secrets
import tempfile
from pathlib import Path


def session_secret() -> str:
    if configured := os.environ.get("SESSION_SECRET"):
        return configured
    directory = Path(os.environ.get("APP_DATA_DIR") or "api_store")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "session-secret"
    if not path.exists():
        fd, temporary = tempfile.mkstemp(prefix=".session-secret-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(secrets.token_hex(32))
                file.flush()
                os.fsync(file.fileno())
            try:
                # Publish a complete file without replacing another starter's secret.
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            Path(temporary).unlink(missing_ok=True)
    secret = path.read_text(encoding="utf-8").strip()
    if not secret:
        raise RuntimeError(f"Session secret file is empty: {path}. Restore it from your backup.")
    return secret


def https_only() -> bool:
    value = os.environ.get("SESSION_HTTPS_ONLY", "0").strip().lower()
    if value not in ("0", "1", "false", "true", "no", "yes", "off", "on", ""):
        raise ValueError("SESSION_HTTPS_ONLY must be 0/1, false/true, no/yes, or off/on")
    return value in ("1", "true", "yes", "on")
