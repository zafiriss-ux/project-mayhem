"""Schema v34 (ADR-0069 §4): one step for OW-M2, P4-03, P4-04 and the injuries of §3.

(α) an unknown TSB or ACWR is stored as NULL; (β) the attempt in progress; (γ) no offsets
for H1-H5 keys, whatever writes them; (δ) one decision per athlete and day; (ε) the
athletes' injuries. Synthetic data only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.test_daily_coach_characterization import (  # noqa: F401  (world is a fixture)
    _run_scenario,
    normal_day,
    world,
)
from titan.core.database import SCHEMA_VERSION, DatabaseManager


def _db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)


def _decision(day: str, *, session: str = "EASY", acwr=1.1, tsb=-5.0, athlete: str = "owner") -> dict:
    return {
        "athlete_profile_id": athlete,
        "date": day,
        "session_planned": session,
        "session_post_governance": session,
        "locks_applied": [],
        "governance_clean": True,
        "phase": "BASE",
        "vlg_color": "GREEN",
        "apl_priority_vector": {},
        "lock_thresholds_active": {},
        "acwr": acwr,
        "tsb_value": tsb,
        "readiness_score": 70.0,
        "glycogen_debt": 1.0,
    }


def _notnull(conn, table: str) -> dict[str, int]:
    return {row[1]: row[3] for row in conn.execute(f"PRAGMA table_info({table})")}


def _objects(conn) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('index', 'trigger')")}


@pytest.mark.unit
def test_a_new_database_is_v34(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        conn = db.conn
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 34
        notnull = _notnull(conn, "governance_outcomes")
        assert notnull["acwr"] == 0 and notnull["tsb_value"] == 0
        assert {"running_since", "running_by"} <= set(_notnull(conn, "worker_routine_executions"))
        injuries = {row[1]: row for row in conn.execute("PRAGMA table_info(athlete_injuries)")}
        assert injuries["athlete_id"][3] == 1 and injuries["athlete_id"][4] is None, "athlete_id: NOT NULL, no DEFAULT"
        assert {
            "uq_governance_outcomes_athlete_date",
            "uq_athlete_injuries_one_open",
            "trg_threshold_offsets_no_hard_stop_insert",
            "trg_threshold_offsets_no_hard_stop_update",
        } <= _objects(conn)
    finally:
        db.close()


@pytest.mark.unit
def test_an_unknown_tsb_and_acwr_are_stored_as_null(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        db.save_governance_decision(_decision("2026-03-02", acwr=None, tsb=None))
        row = db.conn.execute("SELECT acwr, tsb_value FROM governance_outcomes").fetchone()
        assert tuple(row) == (None, None)
        (stored,) = db.get_governance_decisions(athlete_id="owner")
        assert stored["acwr"] is None and stored["tsb_value"] is None
    finally:
        db.close()


@pytest.mark.unit
def test_a_second_decision_of_the_day_replaces_the_first(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        db.save_governance_decision(_decision("2026-03-02", session="TEMPO"))
        db.update_governance_outcome("2026-03-02", rpe=6, athlete_id="owner")
        db.save_governance_decision(_decision("2026-03-02", session="EASY"))
        db.save_governance_decision(_decision("2026-03-02", session="EASY", athlete="athlete_2"))
        rows = db.conn.execute(
            "SELECT athlete_id, session_post_governance, outcome_rpe FROM governance_outcomes ORDER BY athlete_id"
        ).fetchall()
        assert [tuple(r) for r in rows] == [("athlete_2", "EASY", None), ("owner", "EASY", 6)]
    finally:
        db.close()


@pytest.mark.unit
@pytest.mark.parametrize("key", ["HARD_STOP_HRV_DELTA", "HARD_STOP_TSB_FLOOR", "SUBJECTIVE_FATIGUE_EXTREME"])
def test_raw_sql_cannot_write_an_offset_for_a_hard_stop_key(tmp_path: Path, key: str) -> None:
    db = _db(tmp_path)
    try:
        conn = db.conn
        with pytest.raises(sqlite3.IntegrityError, match="ADR-0052"):
            conn.execute(
                "INSERT INTO athlete_threshold_offsets "
                "(athlete_id, threshold_key, delta_value, updated_at, source, confidence) "
                "VALUES ('owner', ?, 0.1, '2026-03-02', 'manual', 0.5)",
                (key,),
            )
        conn.rollback()
        conn.execute(
            "INSERT INTO athlete_threshold_offsets "
            "(athlete_id, threshold_key, delta_value, updated_at, source, confidence) "
            "VALUES ('owner', 'ACWR_RED', 0.1, '2026-03-02', 'manual', 0.5)"
        )
        with pytest.raises(sqlite3.IntegrityError, match="ADR-0052"):
            conn.execute("UPDATE athlete_threshold_offsets SET threshold_key = ?", (key,))
        conn.rollback()
    finally:
        db.close()


@pytest.mark.unit
def test_an_athlete_has_at_most_one_open_injury(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        conn = db.conn
        insert = "INSERT INTO athlete_injuries (athlete_id, description, opened_at, closed_at) VALUES (?, ?, ?, ?)"
        conn.execute(insert, ("owner", "calf", "2026-03-01", "2026-03-05"))
        conn.execute(insert, ("owner", "knee", "2026-03-06", None))
        conn.execute(insert, ("athlete_2", "ankle", "2026-03-06", None))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ("owner", "hip", "2026-03-07", None))
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO athlete_injuries (description, opened_at) VALUES ('x', '2026-03-07')")
        conn.rollback()
    finally:
        db.close()


_V33_GOVERNANCE_OUTCOMES = """
    CREATE TABLE governance_outcomes (
        id INTEGER NOT NULL,
        athlete_id VARCHAR DEFAULT 'owner' NOT NULL,
        date VARCHAR NOT NULL,
        session_planned VARCHAR NOT NULL,
        session_post_governance VARCHAR NOT NULL,
        locks_applied_json TEXT NOT NULL,
        governance_clean INTEGER NOT NULL,
        phase VARCHAR NOT NULL,
        vlg_color VARCHAR NOT NULL,
        apl_priority_vector_json TEXT NOT NULL,
        lock_thresholds_active_json TEXT NOT NULL,
        acwr FLOAT NOT NULL,
        tsb_value FLOAT NOT NULL,
        readiness_score FLOAT NOT NULL,
        glycogen_debt FLOAT NOT NULL,
        afi_value FLOAT,
        outcome_rpe INTEGER,
        outcome_completed INTEGER,
        outcome_session_type_actual VARCHAR,
        outcome_notes TEXT,
        decision_was_followed INTEGER DEFAULT '1' NOT NULL,
        override_outcome_exclusion INTEGER DEFAULT '0' NOT NULL,
        outcome_independence_ok INTEGER DEFAULT '1' NOT NULL,
        algorithm_version_snapshot TEXT,
        CONSTRAINT pk_governance_outcomes PRIMARY KEY (id)
    );
"""


def _old_row(row_id: int, athlete: str, day: str, session: str, tsb: float) -> str:
    return (
        "INSERT INTO governance_outcomes (id, athlete_id, date, session_planned, session_post_governance, "
        "locks_applied_json, governance_clean, phase, vlg_color, apl_priority_vector_json, "
        "lock_thresholds_active_json, acwr, tsb_value, readiness_score, glycogen_debt, outcome_rpe) "
        f"VALUES ({row_id}, '{athlete}', '{day}', '{session}', '{session}', '[]', 1, 'BASE', 'GREEN', "
        f"'{{}}', '{{}}', 1.0, {tsb}, 70.0, 1.0, 5);"
    )


@pytest.mark.unit
def test_v33_upgrades_in_one_step_and_keeps_the_latest_decision_of_a_day(tmp_path: Path) -> None:
    """A v33 database: NOT NULL TSB/ACWR, two rows for the owner's 2/3, no v34 objects."""
    _db(tmp_path).close()
    raw = sqlite3.connect(tmp_path / "titan_core.db")
    raw.executescript(
        "DROP TABLE governance_outcomes;"
        "DROP TABLE athlete_injuries;"
        "DROP TRIGGER trg_threshold_offsets_no_hard_stop_insert;"
        "DROP TRIGGER trg_threshold_offsets_no_hard_stop_update;"
        "ALTER TABLE worker_routine_executions DROP COLUMN running_since;"
        "ALTER TABLE worker_routine_executions DROP COLUMN running_by;"
        + _V33_GOVERNANCE_OUTCOMES
        + _old_row(1, "owner", "2026-03-02", "TEMPO", -3.0)
        + _old_row(2, "owner", "2026-03-02", "EASY", -4.0)
        + _old_row(3, "owner", "2026-03-03", "LONG_RUN", -6.0)
        + _old_row(4, "athlete_2", "2026-03-02", "EASY", -2.0)
        + "PRAGMA user_version = 33;"
    )
    raw.commit()
    raw.close()

    db = _db(tmp_path)
    try:
        conn = db.conn
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 34
        rows = conn.execute(
            "SELECT id, athlete_id, date, session_post_governance, tsb_value, outcome_rpe "
            "FROM governance_outcomes ORDER BY id"
        ).fetchall()
        assert [tuple(r) for r in rows] == [
            (2, "owner", "2026-03-02", "EASY", -4.0, 5),
            (3, "owner", "2026-03-03", "LONG_RUN", -6.0, 5),
            (4, "athlete_2", "2026-03-02", "EASY", -2.0, 5),
        ]
        notnull = _notnull(conn, "governance_outcomes")
        assert notnull["acwr"] == 0 and notnull["tsb_value"] == 0
        assert {"running_since", "running_by"} <= set(_notnull(conn, "worker_routine_executions"))
        assert {
            "uq_governance_outcomes_athlete_date",
            "uq_athlete_injuries_one_open",
            "trg_threshold_offsets_no_hard_stop_insert",
            "trg_threshold_offsets_no_hard_stop_update",
        } <= _objects(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_old_row(5, "owner", "2026-03-03", "EASY", -1.0).rstrip(";"))
        conn.rollback()
    finally:
        db.close()


@pytest.mark.unit
def test_v34_on_a_v34_database_changes_nothing(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        db.save_governance_decision(_decision("2026-03-02"))
        before = db.conn.execute("SELECT * FROM governance_outcomes").fetchall()
        cursor = db.conn.cursor()
        db._apply_v34_migrations(cursor)
        db.conn.commit()
        assert db.conn.execute("SELECT * FROM governance_outcomes").fetchall() == before
    finally:
        db.close()


@pytest.mark.unit
def test_the_first_morning_without_load_history_stores_tsb_as_unknown(world) -> None:
    """The golden's first two mornings have no load history: H4_MISSING, and TSB NULL (OW-M2)."""
    result = _run_scenario(world, [normal_day(i) for i in range(3)])
    rows = {r["date"]: r for r in result["tables"]["governance_outcomes"]}
    first = rows[min(rows)]
    assert "DATA_MISSING_CONSERVATIVE_H4" in first["locks_applied_json"]
    assert first["tsb_value"] is None
    assert any(r["tsb_value"] is not None for r in rows.values()), "a day with load history keeps its TSB"


@pytest.mark.unit
def test_the_dashboard_averages_only_known_acwr() -> None:
    from titan.ui.operator_console import OperatorConsoleService

    class _Db:
        def get_governance_decisions(self, limit: int = 1000, athlete_id: str = "owner"):
            base = {"readiness_score": 70.0, "vlg_color": "GREEN", "phase": "BASE"}
            return [
                {"date": "2026-03-02", "tsb_value": None, "acwr": None, **base},
                {"date": "2026-03-03", "tsb_value": -5.0, "acwr": 1.2, **base},
            ]

    service = OperatorConsoleService.__new__(OperatorConsoleService)
    service.db = _Db()
    payload = service.readiness_load_dashboard()
    assert payload["summary"]["avg_acwr"] == 1.2
    assert payload["timeline"][0]["tsb"] is None
