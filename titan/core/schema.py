"""
TD-08 — Canonical SQLAlchemy Core schema descriptor (Option A / S1).

This module is the SINGLE AUTHORITATIVE SOURCE for all TITAN OS table
definitions. Every other authority (create_database() DDL strings, migration
ladder CREATE TABLE statements, PostgreSQL adapter, Alembic env.py
target_metadata) must eventually derive from or validate against this
descriptor.

CURRENT STATE (Phase 24 / TD-08 — all 5 steps complete, 2026-06-02):
  Step 1 ✅  Descriptor authored (this file).
  Step 2 ✅  create_database() renders all base-table DDL from this MetaData
             via _render_table_ddl() / _BASE_TABLE_NAMES.
  Step 3 ✅  alembic/env.py imports target_metadata from this module;
             autogenerate drift detection is now functional.
  Step 4 ✅  Bidirectional convergence fitness net active
             (tests/test_schema_equivalence.py — both directions).
  Step 5 ✅  consent_log added to SQLite ladder (v23 migration) and
             ALEMBIC_ONLY_TABLES cleared.

USAGE:
    from titan.core.schema import metadata, get_table

    # Render DDL for a specific table
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import sqlite
    print(CreateTable(get_table("training_log")).compile(dialect=sqlite.dialect()))

    # Inspect column names
    cols = [c.name for c in get_table("daily_metrics").columns]

GOVERNANCE: Any schema change MUST:
  1. Update this file (add/modify Table definition).
  2. Add an ALTER TABLE migration to the ladder in database.py.
  3. Increment SCHEMA_VERSION in database.py.
  4. Update AUTHORITATIVE_COLUMNS in tests/test_schema_equivalence.py.
  5. Reference the governing ADR or TD item in a comment here.

KNOWN GAPS (tracked, not yet resolved):
  None — consent_log reconciled into the SQLite ladder (v23 migration, TD-08 Step 5 / F3.4, 2026-06-02).

References: TD-08, ADR-0044, F3.1–F3.5 (Opus pre-Phase-24 audit 2026-05-29).
"""
from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

# Naming convention for constraints — required for Alembic autogenerate
# to produce deterministic, migration-safe names.
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)

# ---------------------------------------------------------------------------
# Table 1 — daily_metrics
# Covers: create_database() base + v14 (data_source), v15 (athlete_id upsert)
# Ref: ADR-0051 MISSING_DATA_POLICY, T5-115
# ---------------------------------------------------------------------------
t_daily_metrics = Table(
    "daily_metrics",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("athlete_id", String, nullable=False, server_default="owner"),
    Column("date", String, nullable=False),
    Column("weight_kg", Float),
    Column("hrv_rmssd", Float),
    Column("resting_hr", Integer),
    Column("sleep_hours", Float),
    Column("sleep_quality", Integer),
    Column("soreness", Integer),
    Column("fatigue_level", Integer),
    Column("mood", Integer),
    Column("notes", Text),
    Column("data_source", String, nullable=False, server_default="garmin_api"),
    Column("hrr_60", Integer),      # v1 — HRR markers
    Column("hrr_120", Integer),     # v1 — HRR markers
    Column("glycogen_debt", Float), # v1 — glycogen tracking
    Column("quality_flag", Text),   # v3 — data-sanity gate (ADR-0026)
    UniqueConstraint("athlete_id", "date", name="uq_daily_metrics_athlete_date"),
)

# ---------------------------------------------------------------------------
# Table 2 — training_log
# Covers: create_database() base + v1 (garmin_activity_id), v3 (quality_flag),
#         v19 (avg_pace_sec_per_km), v20 (athlete_id on training_log)
# Ref: T5-69 (dedup), ADR-0019 (data sanity), T5-116
# ---------------------------------------------------------------------------
t_training_log = Table(
    "training_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("athlete_id", String, nullable=False, server_default="owner"),
    Column("date", String, nullable=False),
    Column("session_type", String),
    Column("distance_km", Float),
    Column("duration_sec", Integer),
    Column("avg_hr", Integer),
    Column("max_hr", Integer),
    Column("rpe", Integer),
    Column("training_load", Integer),
    Column("shoe_id", BigInteger, ForeignKey("gear_usage.id")),
    Column("surface", String),
    Column("temperature_c", Float),
    Column("zone_distribution", Text),
    Column("notes", Text),
    Column("garmin_activity_id", String),   # v1 — T5-69 deduplication
    Column("quality_flag", Integer),        # v3 — data-sanity gate
    Column("avg_pace_sec_per_km", Float),   # v19 — pace storage
)

# ---------------------------------------------------------------------------
# Table 3 — gear_usage
# Covers: create_database() base + v24 (athlete_id, P27-B1)
# Ref: ADR-0019
# ---------------------------------------------------------------------------
t_gear_usage = Table(
    "gear_usage",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("shoe_name", String, nullable=False),
    Column("total_km", Float, server_default="0"),
    Column("last_used", String),
    Column("compression_recovery_hours", Integer, server_default="24"),
    Column("status", String, server_default="ACTIVE"),
    Column("shoe_type", String),
    Column("max_km_limit", Float, server_default="800"),
    Column("athlete_id", String, nullable=False, server_default="owner"),
)

# ---------------------------------------------------------------------------
# Table 4 — personal_bests
# Covers: create_database() base + v24 (athlete_id, P27-B1)
# Ref: ADR-0019
# ---------------------------------------------------------------------------
t_personal_bests = Table(
    "personal_bests",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("distance_km", Float, nullable=False),
    Column("time_sec", Integer, nullable=False),
    Column("pace_sec_per_km", Float),
    Column("date", String, nullable=False),
    Column("race_name", String),
    Column("athlete_id", String, nullable=False, server_default="owner"),
)

# ---------------------------------------------------------------------------
# Table 5 — governance_outcomes
# Covers: create_database() base + v11 (athlete_id migration)
# Ref: ADR-0035, ADR-0058, OutcomeTracker
# ---------------------------------------------------------------------------
t_governance_outcomes = Table(
    "governance_outcomes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("athlete_id", String, nullable=False, server_default="owner"),
    Column("date", String, nullable=False),
    Column("session_planned", String, nullable=False),
    Column("session_post_governance", String, nullable=False),
    Column("locks_applied_json", Text, nullable=False),
    Column("governance_clean", Integer, nullable=False),
    Column("phase", String, nullable=False),
    Column("vlg_color", String, nullable=False),
    Column("apl_priority_vector_json", Text, nullable=False),
    Column("lock_thresholds_active_json", Text, nullable=False),
    Column("acwr", Float, nullable=False),
    Column("tsb_value", Float, nullable=False),
    Column("readiness_score", Float, nullable=False),
    Column("glycogen_debt", Float, nullable=False),
    Column("afi_value", Float),
    Column("outcome_rpe", Integer),
    Column("outcome_completed", Integer),
    Column("outcome_session_type_actual", String),
    Column("outcome_notes", Text),
    Column("decision_was_followed", Integer, nullable=False, server_default="1"),
    Column("override_outcome_exclusion", Integer, nullable=False, server_default="0"),
    Column("outcome_independence_ok", Integer, nullable=False, server_default="1"),
    Column("algorithm_version_snapshot", Text),
)

# ---------------------------------------------------------------------------
# Table 6 — athlete_threshold_offsets
# Covers: create_database() DDL (v22 / ADR-0052 Stage 1)
# Ref: ADR-0052, T5-ThresholdAdapter
# ---------------------------------------------------------------------------
t_athlete_threshold_offsets = Table(
    "athlete_threshold_offsets",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("athlete_id", String, nullable=False),
    Column("threshold_key", String, nullable=False),
    Column("delta_value", Float, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("source", String, nullable=False),
    Column("confidence", Float, nullable=False),
    UniqueConstraint("athlete_id", "threshold_key", name="uq_athlete_threshold"),
    CheckConstraint("source IN ('manual', 'calibration')", name="ck_source_enum"),
    CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_confidence_range"),
)

# ---------------------------------------------------------------------------
# Table 7 — athletes
# Covers: create_database() DDL + v20 (biological_sex, menstrual_tracking)
# Ref: ADR-0033 Layer 3, T5-07-L3-A
# ---------------------------------------------------------------------------
t_athletes = Table(
    "athletes",
    metadata,
    Column("athlete_id", String, primary_key=True),
    Column("display_name", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("is_cold_start", Integer, nullable=False, server_default="1"),
    Column("cold_start_ends_at", String),
    Column("cold_start_sessions_count", Integer, nullable=False, server_default="0"),
    Column("biological_sex", String, server_default="male"),    # v20 — nutrition prefs T5-117
    Column("menstrual_tracking", String, server_default="no"),  # v20 — nutrition prefs T5-117
)

# ---------------------------------------------------------------------------
# Table 8 — auth_users
# Covers: Alembic t5_11 migration (auth layer Phase 8B / ADR-0047)
# Ref: ADR-0047, T5-11
# ---------------------------------------------------------------------------
t_auth_users = Table(
    "auth_users",
    metadata,
    Column("id", String, primary_key=True),
    Column("username", String, nullable=False),
    Column("password_hash", String, nullable=False),
    Column("role", String, nullable=False),
    Column("athlete_id", String),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    UniqueConstraint("username"),
)

# ---------------------------------------------------------------------------
# Table 9 — auth_tokens
# Covers: Alembic t5_11 migration
# Ref: ADR-0047, T5-11
# ---------------------------------------------------------------------------
t_auth_tokens = Table(
    "auth_tokens",
    metadata,
    Column("id", String, primary_key=True),
    Column("user_id", String, ForeignKey("auth_users.id"), nullable=False),
    Column("athlete_id", String),
    Column("issued_at", DateTime, nullable=False),
    Column("expires_at", DateTime, nullable=False),
    Column("revoked", Boolean, nullable=False, server_default="0"),
)

# ---------------------------------------------------------------------------
# Table 10 — coach_audit_log
# Covers: create_database() DDL + Alembic t5_13 migration
# Ref: T5-111, ADR-0054
# ---------------------------------------------------------------------------
t_coach_audit_log = Table(
    "coach_audit_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coach_id", String, nullable=False),
    Column("athlete_id", String, nullable=False),
    Column("action_type", String, nullable=False),
    Column("resource", String, nullable=False),
    Column("action_detail", JSON),
    Column("performed_at", DateTime, nullable=False),
)

# ---------------------------------------------------------------------------
# Table 11 — model_calibration_metadata
# Covers: create_database() DDL (v13 schema / ADR-0052 Stage 4)
# Ref: ADR-0052, EvidenceRegistry
# ---------------------------------------------------------------------------
t_model_calibration_metadata = Table(
    "model_calibration_metadata",
    metadata,
    Column("model_name", String, nullable=False),
    Column("athlete_id", String, nullable=False, server_default="default"),
    Column("calibrated_at", String, nullable=False),
    Column("baseline_hrv_ms", Float),
    Column("baseline_vo2", Float),
    Column("schema_version", Integer, nullable=False),
)

# ---------------------------------------------------------------------------
# Table 12 — consent_log
# Covers: SQLite ladder (v23 migration, TD-08 Step 5 / F3.4, 2026-06-02) and Alembic d9.
# Ref: ADR-0044 Phase 8A (GDPR), F3.4
# ---------------------------------------------------------------------------
t_consent_log = Table(
    "consent_log",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("athlete_id", String, nullable=False, server_default="default"),
    Column("consent_type", String, nullable=False),
    Column("granted_at", String, nullable=False),
    Column("revoked_at", String),
)

# ---------------------------------------------------------------------------
# Table 13 — alembic_version
# Managed by Alembic; included for descriptor completeness only.
# Never rendered by create_database().
# ---------------------------------------------------------------------------
t_alembic_version = Table(
    "alembic_version",
    metadata,
    Column("version_num", String(32), primary_key=True),
)

# ---------------------------------------------------------------------------
# Table 20 — sync_metadata
# Covers: _apply_v4_migrations() (T1-20 Garmin sync outcome ledger)
# Ref: T1-20, ADR-0030
# NOTE: ladder-created (v4); NOT in _BASE_TABLE_NAMES.
# ---------------------------------------------------------------------------
t_sync_metadata = Table(
    "sync_metadata",
    metadata,
    Column("source", String, primary_key=True),
    Column("last_attempt_ts", String),
    Column("last_success_ts", String),
    Column("last_sync_ok", Integer, nullable=False, server_default="0"),
    Column("last_error_class", String),
)

# ---------------------------------------------------------------------------
# Table 21 — nutrition_preferences
# Covers: _apply_v21_migrations() (ADR-0056 per-athlete nutrition prefs)
# Ref: ADR-0056, T5-117
# NOTE: ladder-created (v21); NOT in _BASE_TABLE_NAMES.
# ---------------------------------------------------------------------------
t_nutrition_preferences = Table(
    "nutrition_preferences",
    metadata,
    Column("athlete_id", String, primary_key=True),
    Column("training_time", String, nullable=False, server_default="variable"),
    Column("fasted_training", String, nullable=False, server_default="easy_only"),
    Column("dietary_style", String, nullable=False, server_default="standard"),
    Column("meal_frequency", Integer, nullable=False, server_default="3"),
    Column("biological_sex", String, nullable=False, server_default="male"),
    Column("menstrual_tracking", String, nullable=False, server_default="no"),
    Column("updated_at", String, nullable=False),
)

# ---------------------------------------------------------------------------
# Tables present in create_database() but absent from the live titan_core.db
# table list (sqlite_master check 2026-05-29). Retained in the descriptor
# because they exist in the DDL; will be reconciled in TD-08 Step 5.
# ---------------------------------------------------------------------------

# Table 14 — cs_performances (Critical Speed / D' calibration)
# Ref: ADR-0019, CriticalSpeedTracker
t_cs_performances = Table(
    "cs_performances",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", String, nullable=False),
    Column("distance_m", Float, nullable=False),
    Column("time_sec", Float, nullable=False),
    Column("surface", String, server_default="ROAD"),
    Column("wind_adjusted", Integer, server_default="0"),
)

# Table 15 — override_log (governance discipline audit)
t_override_log = Table(
    "override_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", String, nullable=False),
    Column("prescribed_type", String),
    Column("actual_type", String),
    Column("reason", String),
)

# Table 16 — override_signals (ADR-0042 first-class override invariant)
# Ref: ADR-0042
t_override_signals = Table(
    "override_signals",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("decision_id", String, nullable=False),
    Column("athlete_id", String, nullable=False),
    Column("override_source", String, nullable=False),
    Column("override_reason", String, nullable=False),
    Column("created_at", String, nullable=False),
)

# Table 17 — coach_athlete_assignments (ADR-0054 / T5-110 RBAC)
# Ref: ADR-0054, T5-110
t_coach_athlete_assignments = Table(
    "coach_athlete_assignments",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coach_id", String, nullable=False),
    Column("athlete_id", String, nullable=False),
    Column("assigned_at", String, nullable=False),
    UniqueConstraint("coach_id", "athlete_id"),
)

# Table 18 — degraded_mode_state (HD-06 / DegradedModeTracker persistence)
# Ref: HD-06, OBS-039
t_degraded_mode_state = Table(
    "degraded_mode_state",
    metadata,
    Column("failure_type", String, primary_key=True),
    Column("degraded_since", String, nullable=False),
    Column("athlete_id", String, nullable=False, server_default="default"),
)

# Table 19 — login_lockout (auth brute-force protection / T5-70)
# Ref: T5-70, ADR-0047
t_login_lockout = Table(
    "login_lockout",
    metadata,
    Column("username", String, primary_key=True),
    Column("failed_count", Integer, nullable=False, server_default="0"),
    Column("locked_until_ts", Float),
    Column("last_attempt_ts", Float),
)

# ---------------------------------------------------------------------------
# Table 22 — cohort_calibration_signals
# Covers: _apply_v25_migrations() (P27-01 cohort calibration scaffolding)
# Ref: Phase 27, CohortProfile (future writer), promotion query (future reader)
# NOTE: ladder-created (v25); NOT in _BASE_TABLE_NAMES.
# ---------------------------------------------------------------------------
t_cohort_calibration_signals = Table(
    "cohort_calibration_signals",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("threshold_key", String, nullable=False),
    Column("athlete_id", String, nullable=False),
    Column("proposed_delta", Float, nullable=False),
    Column("sample_size", Integer, nullable=False),
    Column("completion_delta_pp", Float),
    Column("computed_at", String, nullable=False),
    UniqueConstraint("threshold_key", "athlete_id", name="uq_cohort_calibration_signals_threshold_key"),
)

# ---------------------------------------------------------------------------
# Tables 23–24 — worker_routine_executions, telegram_override_nonces
# Covers: _apply_v26_migrations() (ADR-0060 D1/D2, INV-15 / INV-17)
# NOTE: ladder-created (v26); NOT in _BASE_TABLE_NAMES.
# ---------------------------------------------------------------------------
t_worker_routine_executions = Table(
    "worker_routine_executions",
    metadata,
    Column("athlete_id", String, primary_key=True),
    Column("execution_date", String, primary_key=True),
    Column("routine_type", String, primary_key=True),
    Column("started_at", String, nullable=False),
    Column("completed_at", String),
)

t_telegram_override_nonces = Table(
    "telegram_override_nonces",
    metadata,
    Column("nonce", String, primary_key=True),
    Column("command_type", String, nullable=False),
    Column("athlete_id", String, nullable=False),
    Column("decision_id", String, nullable=False),
    Column("issued_at", String, nullable=False),
    Column("expires_at", String, nullable=False),
    Column("consumed_at", String),
    Index("idx_telegram_override_nonces_expires", "expires_at"),
)

# ---------------------------------------------------------------------------
# Registry — lookup by table name
# ---------------------------------------------------------------------------
_TABLE_REGISTRY: dict[str, Table] = {t.name: t for t in metadata.sorted_tables}


def get_table(name: str) -> Table:
    """Return the Table descriptor by name.

    Raises KeyError if the table is not registered — fail-fast prevents
    silent drift between the descriptor and call sites.
    """
    try:
        return _TABLE_REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"Table {name!r} not found in TITAN schema descriptor. "
            f"Known tables: {sorted(_TABLE_REGISTRY)}"
        ) from None


def table_names() -> frozenset[str]:
    """Return the frozenset of all table names in the descriptor."""
    return frozenset(_TABLE_REGISTRY)
