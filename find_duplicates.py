"""Compatibility shim. The implementation lives in core/duplicates.py."""
from core.duplicates import *  # noqa: F401,F403
from core.duplicates import main

if __name__ == "__main__":
    main()
