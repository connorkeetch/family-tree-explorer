"""Compatibility shim. The implementation now lives in core/trace_deadends.py.

Kept so existing usage -- `python trace_deadends.py ...` -- keeps working
unchanged after the move into core/.
"""
from core.trace_deadends import *  # noqa: F401,F403
from core.trace_deadends import main

if __name__ == "__main__":
    main()
