"""
DB schema contract tests — ADR-0033 Layer 3 + ADR-0052 + Phase 9 entry gate.
Any migration that changes a column set MUST update this file in the same PR.

Column sets verified against: DatabaseManager (SCHEMA_VERSION=12).
Run to re-verify: python -c "
    import tempfile; from pathlib import Path
    from titan.core.database import DatabaseManager
    with tempfile.TemporaryDirectory() as d:
        db = DatabaseManager(db_name='t.db', db_dir=Path(d))
        for t in ['daily_metrics','training_log','gear_usage',
                  'personal_bests','governance_outcomes','athlete_threshold_offsets']:
            cols = sorted(r[1] for r in db.conn.execute(f'PRAGMA table_info({t})').fetchall())
            print(t, cols)
"
"""

from __future__ import annotations

import pytest

from titan.core.database import DatabaseManager

# ── Column contract sets (source-of-truth for schema regression) ─────────────
# These include all columns added by migrations up to SCHEMA_VERSION=12.

GOVERNANCE_OUTCOMES_COLUMNS = {
    "id",
    "athlete_id",            # migration v11 — multi-athlete support (T5-74 / ADR-0033)
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
    "decision_was_followed",       # migration v5 — feedback-loop guardrails (T1-22)
    "override_outcome_exclusion",  # migration v5
    "outcome_independence_ok",     # migration v5
    "algorithm_version_snapshot",  # migration v5
}

ATHLETE_THRESHOLD_OFFSETS_COLUMNS = {
    "id",
    "athlete_id",
    "threshold_key",
    "delta_value",
    "updated_at",
    "source",
    "confidence",
}

DAILY_METRICS_COLUMNS = {
    "id",
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
    "hrr_60",        # migration v1
    "hrr_120",       # migration v1
    "glycogen_debt", # migration v1
    "quality_flag",  # migration v3 — data sanity layer (ADR-0026 / T1-19)
}

TRAINING_LOG_COLUMNS = {
    "id",
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
    "temperature_c",     # canonical column name (ADR-0033 audit)
    "zone_distribution",
    "notes",
    "garmin_activity_id", # migration v1
    "quality_flag",       # migration v3
}

GEAR_USAGE_COLUMNS = {
    "id",
    "shoe_name",
    "total_km",
    "last_used",
    "compression_recovery_hours",
    "status",
    "shoe_type",
    "max_km_limit",
}

PERSONAL_BESTS_COLUMNS = {
    "id",
    "distance_km",
    "time_sec",
    "pace_sec_per_km",
    "date",
    "race_name",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def get_columns(db_conn, table_name: str) -> set[str]:
    rows = db_conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def test_db_conn(tmp_path):
    db = DatabaseManager(db_name="schema_contract.db", db_dir=tmp_path)
    yield db.conn


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_governance_outcomes_schema(test_db_conn) -> None:
    assert get_columns(test_db_conn, "governance_outcomes") == GOVERNANCE_OUTCOMES_COLUMNS


def test_athlete_threshold_offsets_schema(test_db_conn) -> None:
    assert get_columns(test_db_conn, "athlete_threshold_offsets") == ATHLETE_THRESHOLD_OFFSETS_COLUMNS


def test_daily_metrics_schema(test_db_conn) -> None:
    assert get_columns(test_db_conn, "daily_metrics") == DAILY_METRICS_COLUMNS


def test_training_log_schema(test_db_conn) -> None:
    assert get_columns(test_db_conn, "training_log") == TRAINING_LOG_COLUMNS


def test_gear_usage_schema(test_db_conn) -> None:
    assert get_columns(test_db_conn, "gear_usage") == GEAR_USAGE_COLUMNS


def test_personal_bests_schema(test_db_conn) -> None:
    assert get_columns(test_db_conn, "personal_bests") == PERSONAL_BESTS_COLUMNS
