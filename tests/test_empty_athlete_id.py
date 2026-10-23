"""MA-F3 (D-122): an empty athlete id never becomes the owner's.

A governance decision whose athlete id was passed but is empty (``""``, blanks or
``None``) is refused, in the tracker and in every writer of ``governance_outcomes``.
Only an id that was not passed at all keeps the owner default (the approved plan,
PR-8α). Synthetic data only.
"""

import pytest
from sqlalchemy import create_engine, text

from titan.core.persistence import PostgreSQLAdapter
from titan.science.outcome_tracker import GovernanceDecision, OutcomeTracker

_EMPTY_IDS = ["", "   ", None]


def _decision_fields():
    return {
        "date": "2026-10-02", "session_planned": "TEMPO", "session_post_governance": "EASY",
        "locks_applied": [], "governance_clean": True, "phase": "BUILD", "vlg_color": "GREEN",
        "apl_priority_vector": {}, "lock_thresholds_active": {}, "acwr": 1.0, "tsb_value": 0.0,
        "readiness_score": 70.0, "glycogen_debt": 0.0, "afi_value": None,
    }


def _record(tracker, **extra):
    return tracker.record_decision(
        session_planned="TEMPO", session_post_governance="EASY", locks_applied=[],
        governance_clean=True, phase="BUILD", vlg_color="GREEN",
        apl_result={"priority_vector": {}, "lock_thresholds": {}},
        acwr=1.0, tsb_value=0.0, readiness_score=70.0, glycogen_debt=0.0,
        date="2026-10-02", **extra,
    )


def _rows(db):
    return db.conn.execute("SELECT athlete_id FROM governance_outcomes").fetchall()


@pytest.mark.parametrize("empty", _EMPTY_IDS)
def test_governance_decision_refuses_an_empty_athlete_id(empty):
    with pytest.raises(ValueError, match="athlete"):
        GovernanceDecision(**_decision_fields(), athlete_profile_id=empty)


def test_governance_decision_keeps_the_owner_default_and_the_legacy_sentinel():
    assert GovernanceDecision(**_decision_fields()).athlete_profile_id == "owner"
    assert GovernanceDecision(**_decision_fields(), athlete_profile_id="DEFAULT").athlete_profile_id == "owner"


@pytest.mark.parametrize("empty", ["", "   "])
def test_record_decision_with_an_empty_id_writes_nothing(db_manager_factory, empty):
    db = db_manager_factory(db_name="test.db")
    tracker = OutcomeTracker(db=db)
    with pytest.raises(ValueError, match="athlete"):
        _record(tracker, athlete_profile_id=empty)
    assert _rows(db) == []
    assert tracker.get_decisions(athlete_id="owner") == []


def test_record_decision_without_an_id_stays_the_owners(db_manager_factory):
    db = db_manager_factory(db_name="test.db")
    _record(OutcomeTracker(db=db))
    assert [tuple(r) for r in _rows(db)] == [("owner",)]


@pytest.mark.parametrize("empty", _EMPTY_IDS)
def test_sqlite_save_refuses_a_decision_with_an_empty_id(db_manager_factory, empty):
    db = db_manager_factory(db_name="test.db")
    with pytest.raises(ValueError, match="athlete"):
        db.save_governance_decision({**_decision_fields(), "athlete_profile_id": empty})
    assert _rows(db) == []


@pytest.mark.parametrize("empty", _EMPTY_IDS)
def test_sqlite_replace_refuses_a_decision_with_an_empty_id(db_manager_factory, empty):
    db = db_manager_factory(db_name="test.db")
    db.save_governance_decision(_decision_fields())  # the owner's row of that day
    with pytest.raises(ValueError, match="athlete"):
        db.replace_governance_decision_on({**_decision_fields(), "session_planned": "REST",
                                           "athlete_profile_id": empty})
    stored = db.conn.execute("SELECT athlete_id, session_planned FROM governance_outcomes").fetchall()
    assert [tuple(r) for r in stored] == [("owner", "TEMPO")]


def _pg_engine():
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
@pytest.mark.parametrize("empty", _EMPTY_IDS)
def test_postgresql_adapter_save_refuses_a_decision_with_an_empty_id(empty):
    engine = _pg_engine()
    adapter = PostgreSQLAdapter(dsn="postgres://unused/titan", engine=engine)
    try:
        with pytest.raises(ValueError, match="athlete"):
            adapter.save_governance_decision({**_decision_fields(), "athlete_profile_id": empty})
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM governance_outcomes")).scalar() == 0
    finally:
        adapter.close()
