"""
titan/__main__.py – package entry point for ``python -m titan``.

Delegates to titan.main.main() which initialises all engines,
registers Telegram callbacks, starts background threads and
launches the interactive menu.
"""

import logging
import os
import sys

from titan.main import main

_log = logging.getLogger(__name__)

if __name__ == "__main__":
    if os.getenv("TITAN_ENABLE_API"):
        from titan.api.auth import validate_jwt_keys_at_startup
        try:
            validate_jwt_keys_at_startup()
        except Exception as exc:
            _log.critical("JWT key validation failed: %s", exc)
            sys.exit(1)
    main()
