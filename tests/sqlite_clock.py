"""SQLite's ``date()`` and ``datetime()`` on the frozen Python clock (SV-19).

freezegun freezes Python's clock but not SQLite's own, so a query such as
``date('now', '-42 days')`` looks at the real date while the rows were written on frozen
days. :func:`freeze_sqlite_clock` replaces both functions on one connection with versions
that read ``datetime.now(UTC)``, which freezegun does freeze.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any


def _sqlite_time(value: Any, mods: tuple[Any, ...]) -> datetime:
    """The two forms the schema and queries use: ``('now')`` and ``('now', '-N days')``."""
    base = datetime.now(UTC).replace(tzinfo=None) if value == "now" else datetime.fromisoformat(str(value))
    for mod in mods:
        amount, unit = str(mod).split()
        if not unit.startswith("day"):
            raise ValueError(f"unsupported SQLite modifier in tests: {mod!r}")
        base += timedelta(days=float(amount))
    return base


def freeze_sqlite_clock(conn: sqlite3.Connection) -> None:
    conn.create_function("date", -1, lambda v, *m: _sqlite_time(v, m).date().isoformat())
    conn.create_function("datetime", -1, lambda v, *m: _sqlite_time(v, m).strftime("%Y-%m-%d %H:%M:%S"))
