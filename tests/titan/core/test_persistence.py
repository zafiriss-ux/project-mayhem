"""Tests for PersistenceAdapter abstract contract — T5-08-B D1."""

from __future__ import annotations

import types
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text

from titan.core.persistence import PersistenceAdapter, PostgreSQLAdapter, SQLiteAdapter

# The full set of methods that the adapter contract must expose as abstract.
_REQUIRED_ABSTRACT_METHODS = frozenset(
    {
        "save_daily_metric",
        "get_baseline_rhr",
        "get_hrv_history",
        "get_weight_history",
        "save_session",
        "get_training_load_history",
        "get_ctl_atl_tsb",
        "add_shoe",
        "get_active_shoes",
        "check_shoe_availability",
        "update_shoe_mileage",
        "save_personal_best",
        "get_pr",
        "save_hrr",
        "get_hrr_history",
        "update_glycogen_debt",
        "log_cs_performance",
        "get_cs_performances",
        "log_override",
        "record_override_signal",
        "get_override_ratio",
        "get_override_log",
        "save_governance_decision",
        "update_governance_outcome",
        "get_governance_decisions",
        "annotate_governance_outcome",
        "record_sync_outcome",
        "get_last_sync_outcome",
        "get_last_garmin_sync_timestamp",
        "backup_database",
        "transaction",
        "close",
    }
)


def test_persistence_adapter_is_importable() -> None:
    assert PersistenceAdapter is not None


def test_persistence_adapter_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        PersistenceAdapter()  # type: ignore[abstract]


def test_persistence_adapter_exposes_required_abstract_methods() -> None:
    """All expected methods must be declared abstract on the base class."""
    missing = _REQUIRED_ABSTRACT_METHODS - PersistenceAdapter.__abstractmethods__
    assert not missing, f"Methods not declared abstract: {sorted(missing)}"


def test_no_extra_undocumented_abstract_methods() -> None:
    """No abstract method may be added without updating _REQUIRED_ABSTRACT_METHODS."""
    extra = PersistenceAdapter.__abstractmethods__ - _REQUIRED_ABSTRACT_METHODS
    assert not extra, (
        f"New abstract methods found that are not in _REQUIRED_ABSTRACT_METHODS: "
        f"{sorted(extra)} — update the set in this test file."
    )


def test_partial_subclass_cannot_be_instantiated() -> None:
    """A subclass that only overrides one method must still raise TypeError."""

    class _Partial(PersistenceAdapter):
        def save_daily_metric(self, date: str, **kwargs) -> None:  # type: ignore[override]
            pass

    with pytest.raises(TypeError):
        _Partial()  # type: ignore[abstract]


def test_complete_concrete_subclass_can_be_instantiated() -> None:
    """A subclass that implements every abstract method is instantiable."""

    def _stub(self, *args, **kwargs):
        return None

    stubs = dict.fromkeys(PersistenceAdapter.__abstractmethods__, _stub)
    concrete_adapter = types.new_class(
        "ConcreteAdapter",
        (PersistenceAdapter,),
        {},
        lambda ns: ns.update(stubs),
    )
    adapter = concrete_adapter()
    assert isinstance(adapter, PersistenceAdapter)


def test_persistence_adapter_is_abstract_base_class() -> None:
    from abc import ABC

    assert issubclass(PersistenceAdapter, ABC)


def test_sqlite_adapter_is_persistence_adapter(tmp_path) -> None:
    adapter = SQLiteAdapter(db_name="adapter.db", db_dir=tmp_path)
    try:
        assert isinstance(adapter, PersistenceAdapter)
    finally:
        adapter.close()


def test_sqlite_adapter_preserves_daily_metric_behavior(tmp_path) -> None:
    adapter = SQLiteAdapter(db_name="adapter.db", db_dir=tmp_path)
    try:
        today = datetime.now(UTC).date().isoformat()
        adapter.save_daily_metric(today, rhr=45, hrv=52.5, weight=70.2)

        assert adapter.get_baseline_rhr(days=7) == 45.0
        assert adapter.get_hrv_history(days=7) == [(today, 52.5)]
        assert adapter.get_weight_history(days=7) == [(today, 70.2)]
    finally:
        adapter.close()


def test_sqlite_adapter_boundary_unknown_sync_source_returns_none(tmp_path) -> None:
    adapter = SQLiteAdapter(db_name="adapter.db", db_dir=tmp_path)
    try:
        assert adapter.get_last_sync_outcome("missing-source") is None
    finally:
        adapter.close()


def _build_test_engine() -> tuple:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE daily_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                weight_kg REAL,
                hrv_rmssd REAL,
                resting_hr INTEGER,
                sleep_hours REAL,
                sleep_quality INTEGER,
                soreness INTEGER,
                fatigue_level INTEGER,
                mood INTEGER,
                notes TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE gear_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shoe_name TEXT NOT NULL,
                total_km REAL DEFAULT 0,
                last_used TEXT,
                compression_recovery_hours INTEGER DEFAULT 24,
                status TEXT DEFAULT 'ACTIVE',
                shoe_type TEXT,
                max_km_limit REAL DEFAULT 800
            )
        """))
        conn.execute(text("""
            CREATE TABLE training_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                session_type TEXT,
                distance_km REAL,
                duration_sec INTEGER,
                avg_hr INTEGER,
                max_hr INTEGER,
                rpe INTEGER,
                training_load INTEGER,
                shoe_id INTEGER,
                surface TEXT,
                temperature_c REAL,
                zone_distribution TEXT,
                notes TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE personal_bests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                distance_km REAL NOT NULL,
                time_sec INTEGER NOT NULL,
                pace_sec_per_km REAL,
                date TEXT NOT NULL,
                race_name TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE governance_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                session_planned TEXT NOT NULL,
                session_post_governance TEXT NOT NULL,
                locks_applied_json TEXT NOT NULL,
                governance_clean INTEGER NOT NULL,
                phase TEXT NOT NULL,
                vlg_color TEXT NOT NULL,
                apl_priority_vector_json TEXT NOT NULL,
                lock_thresholds_active_json TEXT NOT NULL,
                acwr REAL NOT NULL,
                tsb_value REAL NOT NULL,
                readiness_score REAL NOT NULL,
                glycogen_debt REAL NOT NULL,
                afi_value REAL,
                outcome_rpe INTEGER,
                outcome_completed INTEGER,
                outcome_session_type_actual TEXT,
                outcome_notes TEXT,
                decision_was_followed INTEGER NOT NULL DEFAULT 1,
                override_outcome_exclusion INTEGER NOT NULL DEFAULT 0,
                outcome_independence_ok INTEGER NOT NULL DEFAULT 1,
                algorithm_version_snapshot TEXT
            )
        """))
    adapter = PostgreSQLAdapter(dsn="postgres://unused", engine=engine)
    return engine, adapter


def test_postgres_adapter_happy_path_core_queries() -> None:
    _engine, adapter = _build_test_engine()
    today = datetime.now(UTC).date().isoformat()
    decision = {
        "date": today,
        "session_planned": "EASY",
        "session_post_governance": "EASY",
        "locks_applied": ["LOCK_A"],
        "governance_clean": True,
        "phase": "P8",
        "vlg_color": "GREEN",
        "apl_priority_vector": ["A", "B"],
        "lock_thresholds_active": {"k": 1},
        "acwr": 0.9,
        "tsb_value": 5.0,
        "readiness_score": 80.0,
        "glycogen_debt": 0.1,
    }
    try:
        adapter.save_daily_metric(today, rhr=45, hrv=50.0, weight=70.0)
        adapter.save_session(today, "EASY", 10.0, 3600, rpe=4)
        shoe_id = adapter.add_shoe("Pegasus")
        adapter.save_personal_best(5.0, 1200, today, race_name="Test")
        adapter.save_governance_decision(decision)

        assert adapter.get_baseline_rhr(days=7) == 45.0
        assert adapter.get_hrv_history(days=7) == [(today, 50.0)]
        assert adapter.get_weight_history(days=7) == [(today, 70.0)]
        assert adapter.get_training_load_history(days=7) == [(today, 240.0)]
        assert adapter.get_active_shoes()[0][0] == shoe_id
        assert adapter.get_pr(5.0) == (1200, today, "Test")
        assert adapter.get_governance_decisions(limit=10)[0]["date"] == today
    finally:
        adapter.close()


def test_postgres_adapter_boundary_returns_safe_defaults() -> None:
    _engine, adapter = _build_test_engine()
    try:
        assert adapter.get_baseline_rhr(days=7) is None
        assert adapter.get_hrr_history(days=10) == []
        assert adapter.get_cs_performances(limit=5) == []
        assert adapter.get_last_sync_outcome("garmin") is None
        assert adapter.get_last_garmin_sync_timestamp() is None
        assert adapter.get_override_ratio(days=7) == 0.0
    finally:
        adapter.close()


def test_postgres_adapter_boundary_backup_not_in_d2b() -> None:
    _engine, adapter = _build_test_engine()
    try:
        with pytest.raises(NotImplementedError, match="D7"):
            adapter.backup_database()
    finally:
        adapter.close()
