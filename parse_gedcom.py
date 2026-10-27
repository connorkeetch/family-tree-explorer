"""Compatibility shim. The implementation now lives in core/parse_gedcom.py.

Kept so existing usage -- `python parse_gedcom.py ...` and `import parse_gedcom`
(including the test suite) -- keeps working unchanged after the move into core/.
"""
from core.parse_gedcom import *  # noqa: F401,F403
from core.parse_gedcom import main

if __name__ == "__main__":
    main()
