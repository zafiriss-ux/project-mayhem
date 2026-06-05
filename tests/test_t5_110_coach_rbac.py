"""T5-110 — Coach-Athlete RBAC Scoping (ADR-0054).

Tests for coach_athlete_assignments table, migration seeding,
assignment CRUD, and access-control filtering.
"""
import sqlite3

import pytest

from titan.core.database import DatabaseManager
from titan.ui.operator_console import OperatorConsoleService


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_name="rbac_test.db", db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.integration
@pytest.mark.governance
def test_coach_athlete_assignments_table_exists(db):
    """coach_athlete_assignments table must be present after DB init."""
    tables = [
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert "coach_athlete_assignments" in tables


@pytest.mark.integration
@pytest.mark.governance
def test_owner_seeded_at_migration(db):
    """Fresh DB must have system→owner assignment row."""
    assigned = db.get_assigned_athletes("system")
    assert "owner" in assigned


@pytest.mark.integration
@pytest.mark.governance
def test_assign_athlete_to_coach(db):
    """assign_athlete_to_coach must make the athlete visible to that coach."""
    db.assign_athlete_to_coach("coach1", "athlete_a")
    assert db.get_assigned_athletes("coach1") == ["athlete_a"]


@pytest.mark.integration
@pytest.mark.governance
def test_coach_cannot_access_unassigned_athlete(db):
    """A coach assigned only to athlete_a must not see athlete_b."""
    db.assign_athlete_to_coach("coach1", "athlete_a")
    assigned = db.get_assigned_athletes("coach1")
    assert "athlete_a" in assigned
    assert "athlete_b" not in assigned


@pytest.mark.integration
@pytest.mark.governance
def test_system_coach_returns_all_athletes(db):
    """'system' coach must return all athletes regardless of assignment rows."""
    db.conn.execute(
        "INSERT OR IGNORE INTO athletes "
        "(athlete_id, display_name, created_at, is_cold_start, cold_start_sessions_count) "
        "VALUES ('athlete_x', 'X', datetime('now'), 1, 0)"
    )
    db.conn.execute(
        "INSERT OR IGNORE INTO athletes "
        "(athlete_id, display_name, created_at, is_cold_start, cold_start_sessions_count) "
        "VALUES ('athlete_y', 'Y', datetime('now'), 1, 0)"
    )
    db.conn.commit()

    # athlete_x assigned to coach_a, athlete_y assigned to coach_b
    db.assign_athlete_to_coach("coach_a", "athlete_x")
    db.assign_athlete_to_coach("coach_b", "athlete_y")

    all_athletes = db.get_assigned_athletes("system")
    assert "athlete_x" in all_athletes
    assert "athlete_y" in all_athletes


@pytest.mark.integration
@pytest.mark.governance
def test_duplicate_assignment_is_idempotent(db):
    """Assigning the same (coach, athlete) pair twice must not raise and must yield one row."""
    db.assign_athlete_to_coach("coach1", "athlete_a")
    db.assign_athlete_to_coach("coach1", "athlete_a")  # second call — must not error

    count = db.conn.execute(
        "SELECT COUNT(*) FROM coach_athlete_assignments "
        "WHERE coach_id = 'coach1' AND athlete_id = 'athlete_a'"
    ).fetchone()[0]
    assert count == 1
