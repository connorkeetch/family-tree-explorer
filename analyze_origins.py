"""Compatibility shim. The implementation now lives in core/analyze_origins.py.

Kept so existing usage -- `python analyze_origins.py ...` and `import
analyze_origins` (including the test suite) -- keeps working unchanged after the
move into core/.
"""
from core.analyze_origins import *  # noqa: F401,F403
from core.analyze_origins import main

if __name__ == "__main__":
    main()
