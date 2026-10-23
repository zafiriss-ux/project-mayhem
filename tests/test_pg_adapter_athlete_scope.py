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


def _decision(**extra):
    return {
        "date": "2026-10-02", "session_planned": "TEMPO", "session_post_governance": "EASY",
        "locks_applied": [], "governance_clean": True, "phase": "BUILD", "vlg_color": "GREEN",
        "apl_priority_vector": {}, "lock_thresholds_active": {}, "acwr": 1.0, "tsb_value": 0.0,
        "readiness_score": 70.0, "glycogen_debt": 0.0, **extra,
    }


def _engine_with_governance_columns():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE governance_outcomes (id INTEGER PRIMARY KEY, athlete_id TEXT, date TEXT, "
            "session_planned TEXT, session_post_governance TEXT, locks_applied_json TEXT, "
            "governance_clean INTEGER, phase TEXT, vlg_color TEXT, apl_priority_vector_json TEXT, "
            "lock_thresholds_active_json TEXT, acwr REAL, tsb_value REAL, readiness_score REAL, "
            "glycogen_debt REAL, afi_value REAL, algorithm_version_snapshot TEXT)"
        ))
    return engine


@pytest.mark.integration
@pytest.mark.parametrize(("decision", "stored"), [
    (_decision(athlete_profile_id="a-0000000a"), "a-0000000a"),
    (_decision(), "owner"),  # the same default the SQLite repository has
])
def test_save_governance_decision_writes_the_decisions_athlete(decision, stored):
    # MA-F8 (D-121): the PostgreSQL write named no athlete, so the column's server
    # default made every athlete's decision the owner's.
    engine = _engine_with_governance_columns()
    adapter = PostgreSQLAdapter(dsn="postgres://unused/titan", engine=engine)
    try:
        adapter.save_governance_decision(decision)
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT athlete_id, date FROM governance_outcomes")).all()
        assert [tuple(r) for r in rows] == [(stored, "2026-10-02")]
    finally:
        adapter.close()
