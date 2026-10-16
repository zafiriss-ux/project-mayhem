"""Schema equivalence fitness guard — Phase 24 blocker B1.

Asserts that a freshly-initialised SQLite DatabaseManager produces exactly
the expected table set and per-table column set.

PURPOSE
    Provides a regression net for TD-08 (declarative schema descriptor).
    Any modification to create_database() or the migration ladder that changes
    table or column structure will fail here before reaching CI.

HOW TO UPDATE THIS FIXTURE
    Schema changes MUST be accompanied by:
    1. An ADR or TD entry authorising the change.
    2. An increment of SCHEMA_VERSION in titan/core/database.py.
    3. An update to AUTHORITATIVE_COLUMNS below.
    Use this helper to regenerate the fixture from the live DB:

        python -c "
        import sqlite3, json
        db = sqlite3.connect('titan_core.db')
        out = {}
        for (t,) in db.execute(
            \"SELECT name FROM sqlite_master \"
            \"WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name\"
        ):
            out[t] = [r[1] for r in db.execute(f'PRAGMA table_info({t})')]
        print(json.dumps(out, indent=2))
        "

KNOWN GAPS (recorded, not enforced here)
    None — consent_log added to SQLite ladder in v23 (TD-08 Step 5 / F3.4, 2026-06-02).

Reference: F3.1 (Opus pre-Phase-24 audit 2026-05-29).
TD-08 prerequisite · ADR-0044 · Phase-24 blocker B1.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from titan.core.database import DatabaseManager

# ---------------------------------------------------------------------------
# Authoritative column snapshot — SCHEMA_VERSION 29 (v29 adds an index only), 2026-10-16
#
# Column order follows PRAGMA table_info cid sequence:
#   create_database() base columns appear first;
#   ALTER TABLE ladder additions appear after, in migration order.
# ---------------------------------------------------------------------------
AUTHORITATIVE_COLUMNS: dict[str, list[str]] = {
    "athlete_threshold_offsets": [
        "id",
        "athlete_id",
        "threshold_key",
        "delta_value",
        "updated_at",
        "source",
        "confidence",
    ],
    "cohort_calibration_signals": [
        "id",
        "threshold_key",
        "athlete_id",
        "proposed_delta",
        "sample_size",
        "completion_delta_pp",
        "computed_at",
    ],
    "athletes": [
        "athlete_id",
        "display_name",
        "created_at",
        "is_cold_start",
        "cold_start_ends_at",
        "cold_start_sessions_count",
        "biological_sex",
        "menstrual_tracking",
    ],
    "auth_tokens": [
        "id",
        "user_id",
        "athlete_id",
        "issued_at",
        "expires_at",
        "revoked",
    ],
    "auth_users": [
        "id",
        "username",
        "password_hash",
        "role",
        "athlete_id",
        "is_active",
    ],
    "coach_athlete_assignments": [
        "id",
        "coach_id",
        "athlete_id",
        "assigned_at",
    ],
    "coach_audit_log": [
        "id",
        "coach_id",
        "athlete_id",
        "action_type",
        "resource",
        "action_detail",
        "performed_at",
    ],
    "consent_log": [
        "id",
        "athlete_id",
        "consent_type",
        "granted_at",
        "revoked_at",
    ],
    "cs_performances": [
        "id",
        "date",
        "distance_m",
        "time_sec",
        "surface",
        "wind_adjusted",
        "athlete_id",  # v28 — CS per athlete (D-028)
    ],
    "daily_metrics": [
        "id",
        "athlete_id",
        "date",
        "weight_kg",
        "hrv_rmssd",
        "resting_hr",
        "sleep_hours",
        "sleep_quality",
        "soreness",
        "fatigue_level",
        "mood",
        "notes",
        "data_source",   # T5-116 (manual-entry source tagging)
        "hrr_60",
        "hrr_120",
        "glycogen_debt",
        "quality_flag",
    ],
    "degraded_mode_state": [
        "failure_type",
        "degraded_since",
        "athlete_id",
    ],
    "gear_usage": [
        "id",
        "shoe_name",
        "total_km",
        "last_used",
        "compression_recovery_hours",
        "status",
        "shoe_type",
        "max_km_limit",
        "athlete_id",
    ],
    "governance_outcomes": [
        "id",
        "athlete_id",
        "date",
        "session_planned",
        "session_post_governance",
        "locks_applied_json",
        "governance_clean",
        "phase",
        "vlg_color",
        "apl_priority_vector_json",
        "lock_thresholds_active_json",
        "acwr",
        "tsb_value",
        "readiness_score",
        "glycogen_debt",
        "afi_value",
        "outcome_rpe",
        "outcome_completed",
        "outcome_session_type_actual",
        "outcome_notes",
        "decision_was_followed",
        "override_outcome_exclusion",
        "outcome_independence_ok",
        "algorithm_version_snapshot",
    ],
    "login_lockout": [
        "username",
        "failed_count",
        "locked_until_ts",
        "last_attempt_ts",
    ],
    "model_calibration_metadata": [
        "model_name",
        "athlete_id",
        "calibrated_at",
        "baseline_hrv_ms",
        "baseline_vo2",
        "schema_version",
    ],
    "nutrition_preferences": [
        "athlete_id",
        "training_time",
        "fasted_training",
        "dietary_style",
        "meal_frequency",
        "biological_sex",
        "menstrual_tracking",
        "updated_at",
    ],
    "override_log": [
        "id",
        "date",
        "prescribed_type",
        "actual_type",
        "reason",
    ],
    "override_signals": [
        "id",
        "decision_id",
        "athlete_id",
        "override_source",
        "override_reason",
        "created_at",
    ],
    "personal_bests": [
        "id",
        "distance_km",
        "time_sec",
        "pace_sec_per_km",
        "date",
        "race_name",
        "athlete_id",
    ],
    "sync_metadata": [
        "source",
        "last_attempt_ts",
        "last_success_ts",
        "last_sync_ok",
        "last_error_class",
    ],
    "training_log": [
        "id",
        "athlete_id",
        "date",
        "session_type",
        "distance_km",
        "duration_sec",
        "avg_hr",
        "max_hr",
        "rpe",
        "training_load",
        "shoe_id",
        "surface",
        "temperature_c",
        "zone_distribution",
        "notes",
        "garmin_activity_id",   # v1 — T5-69 activity deduplication
        "quality_flag",         # v3 — data-sanity gate
        "avg_pace_sec_per_km",  # v19 — pace storage and display
    ],
    "telegram_override_nonces": [  # v26 — ADR-0060 D2 (INV-17)
        "nonce",
        "command_type",
        "athlete_id",
        "decision_id",
        "issued_at",
        "expires_at",
        "consumed_at",
    ],
    "worker_routine_executions": [  # v26 — ADR-0060 D1 (INV-15)
        "athlete_id",
        "execution_date",
        "routine_type",
        "started_at",
        "completed_at",
    ],
    "weekly_plans": [  # v27 — D-020 (worker's Sunday weekly plan)
        "athlete_id",
        "week_start",
        "plan_json",
        "created_at",
    ],
}

# Tables a fresh SQLite DatabaseManager must create.
# Excludes Alembic-only tables (consent_log) per F3.4.
EXPECTED_TABLES: frozenset[str] = frozenset(AUTHORITATIVE_COLUMNS)

# Tables present in the live DB but not in the SQLite ladder.
# Listed for traceability; not asserted as missing in fresh-DB tests.
# consent_log was reconciled into the SQLite ladder in v23 (TD-08 Step 5).

ALEMBIC_ONLY_TABLES: frozenset[str] = frozenset()

# Tables in the descriptor that are never created by create_database() or the
# SQLite ladder — Alembic-managed or migration-only tables excluded from the
# convergence check.  The convergence test only checks tables that both the
# descriptor and the fresh DB are expected to contain.
_DESCRIPTOR_ONLY_TABLES: frozenset[str] = frozenset({
    "alembic_version",    # Written by Alembic, not create_database()
})

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fresh_db_schema() -> dict[str, list[str]]:
    """Build a fresh DatabaseManager in a temporary directory and return the
    schema as {table_name: [column_name, ...]} via PRAGMA table_info.

    Column names are returned in cid order (PRAGMA table_info ordering).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_name = "schema_equivalence_test.db"
        db = DatabaseManager(db_name, db_dir=Path(tmpdir))
        db_path = Path(tmpdir) / db_name
        conn = sqlite3.connect(str(db_path))
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            return {
                t: [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
                for t in tables
            }
        finally:
            conn.close()
            db.close()


# ---------------------------------------------------------------------------
# Test 0 — TD-08 Step 4: descriptor-vs-fresh-DB convergence
#
# Asserts that every table the SQLAlchemy descriptor defines (excluding
# Alembic-managed and descriptor-only tables) is present in a fresh
# DatabaseManager and has exactly the columns the descriptor declares.
#
# This test does NOT depend on the AUTHORITATIVE_COLUMNS fixture — it
# derives expected state directly from titan/core/schema.py.  A descriptor
# edit that forgets to update AUTHORITATIVE_COLUMNS will still be caught here.
# ---------------------------------------------------------------------------


def test_descriptor_tables_present_in_fresh_db(
    fresh_db_schema: dict[str, list[str]],
) -> None:
    """TD-08 Step 4: every descriptor table (minus exclusions) exists in fresh DB.

    Failure means either:
      - A table was added to schema.py but not to create_database() / the ladder.
      - A table was removed from create_database() / the ladder but kept in schema.py.
    """
    from titan.core.schema import table_names

    descriptor_tables = table_names() - _DESCRIPTOR_ONLY_TABLES
    actual_tables = frozenset(fresh_db_schema)

    missing_from_db = descriptor_tables - actual_tables - ALEMBIC_ONLY_TABLES
    assert not missing_from_db, (
        "Tables defined in schema.py but absent from fresh DatabaseManager "
        f"(create_database/ladder regression): {sorted(missing_from_db)}"
    )


def test_fresh_db_tables_all_declared_in_descriptor(
    fresh_db_schema: dict[str, list[str]],
) -> None:
    """TD-08 Step 4 / V4 reverse-direction: every table in a fresh DB must
    be declared in the canonical schema descriptor (titan/core/schema.py).

    Failure means a table was added to create_database() or the migration
    ladder WITHOUT updating the descriptor — exactly the defect class
    Opus V4 identified as silently passing CI before this test existed.

    Tables excluded from the check:
      ALEMBIC_ONLY_TABLES — Alembic-managed tables not created by the ladder.
      alembic_version     — Written by Alembic, not create_database(); always
                            excluded regardless of ALEMBIC_ONLY_TABLES content.
    """
    from titan.core.schema import table_names

    descriptor_tables = table_names()
    actual_tables = frozenset(fresh_db_schema)

    # Tables that are legitimately in the fresh DB but not in the descriptor.
    excluded = ALEMBIC_ONLY_TABLES | {"alembic_version"}
    undeclared = actual_tables - descriptor_tables - excluded

    assert not undeclared, (
        "Tables present in fresh DatabaseManager but absent from "
        "titan/core/schema.py (descriptor must be the single source of truth). "
        f"Undeclared tables: {sorted(undeclared)}\n"
        "Add Table() definitions to titan/core/schema.py and update "
        "AUTHORITATIVE_COLUMNS in this file."
    )


def test_descriptor_columns_match_fresh_db(
    fresh_db_schema: dict[str, list[str]],
) -> None:
    """TD-08 Step 4: for every descriptor table present in the fresh DB,
    column names match exactly.

    Failure means the descriptor and create_database() have diverged — a
    column was added to one but not the other.
    """
    from titan.core.schema import get_table, table_names

    descriptor_tables = table_names() - _DESCRIPTOR_ONLY_TABLES
    checked = 0
    mismatches: list[str] = []

    for tname in sorted(descriptor_tables):
        if tname not in fresh_db_schema:
            # Covered by test_descriptor_tables_present_in_fresh_db above.
            continue
        descriptor_cols = frozenset(c.name for c in get_table(tname).columns)
        fresh_cols = frozenset(fresh_db_schema[tname])
        missing = descriptor_cols - fresh_cols
        unexpected = fresh_cols - descriptor_cols
        if missing or unexpected:
            mismatches.append(
                f"{tname}: descriptor_extra={sorted(missing)} "
                f"fresh_extra={sorted(unexpected)}"
            )
        checked += 1

    assert not mismatches, (
        "Column mismatch between schema.py descriptor and fresh DatabaseManager:\n"
        + "\n".join(mismatches)
    )
    assert checked > 0, "No tables were checked — descriptor exclusion list too broad"


# ---------------------------------------------------------------------------
# Test 1 — table set
# ---------------------------------------------------------------------------


def test_fresh_db_table_set_matches_authoritative(
    fresh_db_schema: dict[str, list[str]],
) -> None:
    """A fresh DatabaseManager must produce exactly the expected table set.

    Failure modes:
      missing tables    → create_database() or ladder migration was removed.
      unexpected tables → new table added without updating this fixture
                          and incrementing SCHEMA_VERSION.
    """
    actual: frozenset[str] = frozenset(fresh_db_schema)
    missing = EXPECTED_TABLES - actual
    unexpected = actual - EXPECTED_TABLES - ALEMBIC_ONLY_TABLES

    assert not missing, (
        "Tables missing from fresh DB "
        f"(create_database/ladder regression): {sorted(missing)}"
    )
    assert not unexpected, (
        "Unexpected tables in fresh DB "
        f"(fixture not updated after schema change): {sorted(unexpected)}"
    )


# ---------------------------------------------------------------------------
# Test 2 — per-table column set (parametrised)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", sorted(AUTHORITATIVE_COLUMNS))
def test_fresh_db_column_set_matches_authoritative(
    fresh_db_schema: dict[str, list[str]],
    table: str,
) -> None:
    """Each table in a fresh DB must have exactly the expected columns.

    Failure modes:
      missing columns    → ALTER TABLE removed from ladder, or base DDL
                           column list was narrowed (TD-08 regression risk).
      unexpected columns → new column added without updating this fixture.

    Column ORDER is not enforced (cid ordering can vary after ALTER TABLE);
    only column NAME presence is checked.

    To resolve: update AUTHORITATIVE_COLUMNS with the ADR/TD reference.
    """
    if table not in fresh_db_schema:
        pytest.skip(
            f"Table {table!r} absent from fresh DB — covered by table-set test"
        )

    actual_cols: frozenset[str] = frozenset(fresh_db_schema[table])
    expected_cols: frozenset[str] = frozenset(AUTHORITATIVE_COLUMNS[table])

    missing = expected_cols - actual_cols
    unexpected = actual_cols - expected_cols

    assert not missing, (
        f"{table}: columns missing from fresh DB "
        f"(ladder regression or fixture drift): {sorted(missing)}"
    )
    assert not unexpected, (
        f"{table}: unexpected columns in fresh DB "
        f"(new column added without fixture update): {sorted(unexpected)}"
    )
