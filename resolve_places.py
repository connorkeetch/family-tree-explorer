"""Compatibility shim. The implementation lives in core/resolve_places.py."""
from core.resolve_places import *  # noqa: F401,F403
from core.resolve_places import main

if __name__ == "__main__":
    main()
