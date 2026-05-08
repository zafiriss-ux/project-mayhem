"""T5-111: coach_audit_log persistence tests.

Verifies that coach actions are written to SQLite and survive process restart.
"""
from __future__ import annotations

import pytest

from titan.core.database import DatabaseManager


@pytest.fixture()
def db(tmp_path):
    return DatabaseManager(db_name="audit_test.db", db_dir=tmp_path)


def test_coach_action_persists_to_db(db):
    db.log_coach_action("coach1", "VIEW", "athlete_a")
    rows = db.get_coach_audit_log("coach1")
    assert len(rows) >= 1
    assert rows[0]["action_type"] == "VIEW"
    assert rows[0]["coach_id"] == "coach1"
    assert rows[0]["athlete_id"] == "athlete_a"


def test_audit_log_survives_reconnect(db, tmp_path):
    db.log_coach_action("coach1", "OVERRIDE", "athlete_b", action_detail="test detail")
    db.close()

    db2 = DatabaseManager(db_name="audit_test.db", db_dir=tmp_path)
    rows = db2.get_coach_audit_log("coach1")
    assert len(rows) >= 1
    assert rows[0]["action_type"] == "OVERRIDE"
    assert rows[0]["action_detail"] == "test detail"
    db2.close()


def test_audit_log_filtered_by_coach(db):
    db.log_coach_action("coach1", "VIEW", "athlete_a")
    db.log_coach_action("coach2", "EDIT", "athlete_b")

    rows_coach1 = db.get_coach_audit_log("coach1")
    rows_coach2 = db.get_coach_audit_log("coach2")

    assert all(r["coach_id"] == "coach1" for r in rows_coach1)
    assert all(r["coach_id"] == "coach2" for r in rows_coach2)
    assert len(rows_coach1) >= 1
    assert len(rows_coach2) >= 1


def test_audit_log_table_exists(db):
    assert "coach_audit_log" in db.get_table_names()
