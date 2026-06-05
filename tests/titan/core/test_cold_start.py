"""
tests/titan/core/test_cold_start.py

Cold-start protocol contract tests — ADR-0033 Layer 3, L3-C.

Verifies:
  1. is_athlete_cold_start() reads athletes.is_cold_start flag (not outcome count).
  2. Fail-closed: unknown athlete returns True (INV-05).
  3. check_and_exit_cold_start() requires BOTH exit conditions.
  4. Exit is atomic: is_cold_start=0 + cold_start_ends_at set in same transaction.
  5. Owner athlete bypasses cold-start (seeded with is_cold_start=0).
  6. increment_cold_start_sessions() increments counter; no-op for graduated athletes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from titan.config.thresholds import CALIBRATION_MIN_OUTCOME_COUNT
from titan.core.database import DatabaseManager


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    instance = DatabaseManager(db_name="cold_start_contract.db", db_dir=tmp_path)
    yield instance
    instance.close()


# ── Test 1 ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_is_athlete_cold_start_returns_true_for_new_athlete(db: DatabaseManager) -> None:
    """Athlete seeded with is_cold_start=1 → is_athlete_cold_start() returns True."""
    db.conn.execute(
        "INSERT INTO athletes (athlete_id, display_name, created_at, is_cold_start, "
        "cold_start_ends_at, cold_start_sessions_count) VALUES (?,?,?,1,NULL,0)",
        ("new_athlete", "New Athlete", "2026-01-01T00:00:00+00:00"),
    )
    db.conn.commit()
    assert db.is_athlete_cold_start("new_athlete") is True


# ── Test 2 ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_is_athlete_cold_start_returns_false_for_graduated(db: DatabaseManager) -> None:
    """Owner athlete seeded with is_cold_start=0 → returns False."""
    assert db.is_athlete_cold_start("owner") is False


# ── Test 3 ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_is_athlete_cold_start_fail_closed_for_unknown(db: DatabaseManager) -> None:
    """Unknown athlete not in athletes table → returns True (fail-closed, INV-05)."""
    assert db.is_athlete_cold_start("nobody") is True


# ── Test 4 ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_cold_start_exit_requires_both_conditions(db: DatabaseManager) -> None:
    """Exit requires sessions >= 30 AND outcomes >= CALIBRATION_MIN_OUTCOME_COUNT.
    Only sessions met → no exit; is_cold_start remains 1."""
    db.conn.execute(
        "INSERT INTO athletes (athlete_id, display_name, created_at, is_cold_start, "
        "cold_start_ends_at, cold_start_sessions_count) VALUES (?,?,?,1,NULL,30)",
        ("sessions_only", "Sessions Only", "2026-01-01T00:00:00+00:00"),
    )
    db.conn.commit()

    result = db.check_and_exit_cold_start("sessions_only")
    assert result is False

    row = db.conn.execute(
        "SELECT is_cold_start FROM athletes WHERE athlete_id = 'sessions_only'"
    ).fetchone()
    assert row[0] == 1, "is_cold_start must remain 1 when only sessions condition met"


# ── Test 5 ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_cold_start_exit_sets_is_cold_start_zero(db: DatabaseManager) -> None:
    """When both conditions met → is_cold_start=0 and cold_start_ends_at populated atomically."""
    db.conn.execute(
        "INSERT INTO athletes (athlete_id, display_name, created_at, is_cold_start, "
        "cold_start_ends_at, cold_start_sessions_count) VALUES (?,?,?,1,NULL,30)",
        ("ready_athlete", "Ready Athlete", "2026-01-01T00:00:00+00:00"),
    )
    for i in range(CALIBRATION_MIN_OUTCOME_COUNT):
        db.conn.execute(
            "INSERT INTO governance_outcomes "
            "(athlete_id, date, session_planned, session_post_governance, "
            "locks_applied_json, governance_clean, phase, vlg_color, "
            "apl_priority_vector_json, lock_thresholds_active_json, "
            "acwr, tsb_value, readiness_score, glycogen_debt, outcome_completed) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
            (
                "ready_athlete", f"2026-02-{i + 1:02d}", "EASY", "EASY",
                "[]", 1, "BASE", "GREEN", "{}", "{}", 1.0, 5.0, 80.0, 1.0,
            ),
        )
    db.conn.commit()

    result = db.check_and_exit_cold_start("ready_athlete")
    assert result is True

    row = db.conn.execute(
        "SELECT is_cold_start, cold_start_ends_at FROM athletes "
        "WHERE athlete_id = 'ready_athlete'"
    ).fetchone()
    assert row[0] == 0, "is_cold_start must be 0 after graduation"
    assert row[1] is not None, "cold_start_ends_at must be set after graduation"


# ── Test 6 ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_owner_athlete_not_in_cold_start(db: DatabaseManager) -> None:
    """Owner athlete seeded with is_cold_start=0 bypasses cold-start (ADR-0033 L3-C)."""
    assert db.is_athlete_cold_start("owner") is False
    assert db.check_and_exit_cold_start("owner") is False


# ── Test 7 ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_increment_cold_start_sessions_increments(db: DatabaseManager) -> None:
    """increment_cold_start_sessions() increments counter for a cold-start athlete."""
    db.conn.execute(
        "INSERT INTO athletes (athlete_id, display_name, created_at, is_cold_start, "
        "cold_start_ends_at, cold_start_sessions_count) VALUES (?,?,?,1,NULL,5)",
        ("counting_athlete", "Counter", "2026-01-01T00:00:00+00:00"),
    )
    db.conn.commit()

    db.increment_cold_start_sessions("counting_athlete")

    row = db.conn.execute(
        "SELECT cold_start_sessions_count FROM athletes "
        "WHERE athlete_id = 'counting_athlete'"
    ).fetchone()
    assert row[0] == 6


# ── Test 8 ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_increment_noop_for_graduated_athlete(db: DatabaseManager) -> None:
    """increment_cold_start_sessions() is no-op for graduated athlete (is_cold_start=0)."""
    before = db.conn.execute(
        "SELECT cold_start_sessions_count FROM athletes WHERE athlete_id = 'owner'"
    ).fetchone()[0]

    db.increment_cold_start_sessions("owner")

    after = db.conn.execute(
        "SELECT cold_start_sessions_count FROM athletes WHERE athlete_id = 'owner'"
    ).fetchone()[0]
    assert before == after, "graduated athlete counter must not change"
