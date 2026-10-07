#!/usr/bin/env python3
"""
TITAN OS root-level launcher.

Usage (from project root):
    python main.py
"""
import logging
import os
import sys

# Ensure the project root is on sys.path so `titan` resolves as a package.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log = logging.getLogger(__name__)


def _run_launcher() -> None:
    try:
        from titan.main import main

        main()
    except Exception as exc:
        log.exception(
            "startup_failure",
            extra={
                "component": "launcher",
                "error_class": exc.__class__.__name__,
                "detail": str(exc),
            },
        )
        raise

if __name__ == "__main__":
    _run_launcher()
