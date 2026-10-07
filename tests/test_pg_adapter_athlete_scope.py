"""G-CI-04 / INV-03: PostgreSQLAdapter HRR and glycogen writes are athlete-scoped.

The adapter used to drop ``athlete_id`` (``del athlete_id``) and update every
row for the date, whichever athlete owned it. Runs against an in-memory SQLite
engine with the columns the adapter touches.
"""

import pytest
from sqlalchemy import create_engine, text

from titan.core.persistence import PostgreSQLAdapter


def _engine_with_two_athletes():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE daily_metrics (id INTEGER PRIMARY KEY, athlete_id TEXT, "
            "date TEXT, notes TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE governance_outcomes (id INTEGER PRIMARY KEY, athlete_id TEXT, "
            "date TEXT, glycogen_debt REAL)"
        ))
        for athlete in ("owner", "athlete_b"):
            conn.execute(
                text("INSERT INTO daily_metrics (athlete_id, date) VALUES (:a, '2026-10-01')"),
                {"a": athlete},
            )
            conn.execute(
                text(
                    "INSERT INTO governance_outcomes (athlete_id, date) "
                    "VALUES (:a, '2026-10-01')"
                ),
                {"a": athlete},
            )
    return engine


@pytest.mark.integration
def test_save_hrr_updates_only_the_given_athlete():
    engine = _engine_with_two_athletes()
    adapter = PostgreSQLAdapter(dsn="postgres://unused/titan", engine=engine)
    try:
        adapter.save_hrr("2026-10-01", 30, 50, athlete_id="athlete_b")
        with engine.connect() as conn:
            rows = dict(conn.execute(text("SELECT athlete_id, notes FROM daily_metrics")).all())
        assert rows["athlete_b"] == "HRR60=30;HRR120=50"
        assert rows["owner"] is None
    finally:
        adapter.close()


@pytest.mark.integration
def test_update_glycogen_debt_updates_only_the_given_athlete():
    engine = _engine_with_two_athletes()
    adapter = PostgreSQLAdapter(dsn="postgres://unused/titan", engine=engine)
    try:
        adapter.update_glycogen_debt("2026-10-01", 4.5, athlete_id="owner")
        with engine.connect() as conn:
            rows = dict(
                conn.execute(text("SELECT athlete_id, glycogen_debt FROM governance_outcomes")).all()
            )
        assert rows["owner"] == 4.5
        assert rows["athlete_b"] is None
    finally:
        adapter.close()
