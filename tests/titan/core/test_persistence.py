"""Tests for PersistenceAdapter abstract contract — T5-08-B D1."""

from __future__ import annotations

import subprocess
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from titan.core.persistence import (
    PersistenceAdapter,
    PostgreSQLAdapter,
    SQLiteAdapter,
    get_athlete_context,
    get_persistence_adapter,
)

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
        "is_db_reachable",
        "replay_tsb",
        "backup_database",
        "transaction",
        "close",
    }
)


@pytest.mark.integration
def test_persistence_adapter_is_importable() -> None:
    assert PersistenceAdapter is not None


@pytest.mark.integration
def test_persistence_adapter_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        PersistenceAdapter()  # type: ignore[abstract]


@pytest.mark.integration
def test_persistence_adapter_exposes_required_abstract_methods() -> None:
    """All expected methods must be declared abstract on the base class."""
    missing = _REQUIRED_ABSTRACT_METHODS - PersistenceAdapter.__abstractmethods__
    assert not missing, f"Methods not declared abstract: {sorted(missing)}"


@pytest.mark.integration
def test_no_extra_undocumented_abstract_methods() -> None:
    """No abstract method may be added without updating _REQUIRED_ABSTRACT_METHODS."""
    extra = PersistenceAdapter.__abstractmethods__ - _REQUIRED_ABSTRACT_METHODS
    assert not extra, (
        f"New abstract methods found that are not in _REQUIRED_ABSTRACT_METHODS: "
        f"{sorted(extra)} — update the set in this test file."
    )


@pytest.mark.integration
def test_partial_subclass_cannot_be_instantiated() -> None:
    """A subclass that only overrides one method must still raise TypeError."""

    class _Partial(PersistenceAdapter):
        def save_daily_metric(self, date: str, **kwargs) -> None:  # type: ignore[override]
            pass

    with pytest.raises(TypeError):
        _Partial()  # type: ignore[abstract]


@pytest.mark.integration
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


@pytest.mark.integration
def test_persistence_adapter_is_abstract_base_class() -> None:
    from abc import ABC

    assert issubclass(PersistenceAdapter, ABC)


@pytest.mark.integration
def test_sqlite_adapter_is_persistence_adapter(tmp_path) -> None:
    adapter = SQLiteAdapter(db_name="adapter.db", db_dir=tmp_path)
    try:
        assert isinstance(adapter, PersistenceAdapter)
    finally:
        adapter.close()


@pytest.mark.integration
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


@pytest.mark.integration
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
                athlete_id TEXT NOT NULL DEFAULT 'owner',
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
                athlete_id TEXT NOT NULL DEFAULT 'owner',
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
                athlete_id TEXT NOT NULL DEFAULT 'owner',
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
                notes TEXT,
                garmin_activity_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE personal_bests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'owner',
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
                athlete_id TEXT NOT NULL DEFAULT 'owner',
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
    adapter = PostgreSQLAdapter(dsn="postgres://unused/titan", engine=engine)
    return engine, adapter


@pytest.mark.integration
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

        with _engine.connect() as conn:
            assert conn.execute(text("SELECT athlete_id FROM daily_metrics LIMIT 1")).scalar_one() == "owner"
            assert conn.execute(text("SELECT athlete_id FROM training_log LIMIT 1")).scalar_one() == "owner"
            assert conn.execute(text("SELECT athlete_id FROM gear_usage LIMIT 1")).scalar_one() == "owner"
            assert conn.execute(text("SELECT athlete_id FROM personal_bests LIMIT 1")).scalar_one() == "owner"
            assert (
                conn.execute(text("SELECT athlete_id FROM governance_outcomes LIMIT 1")).scalar_one()
                == "owner"
            )
    finally:
        adapter.close()


@pytest.mark.integration
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


@pytest.mark.integration
def test_postgres_adapter_backup_runs_pg_dump(tmp_path) -> None:
    _engine, adapter = _build_test_engine()
    calls: list[list[str]] = []

    def _fake_run(command, *, check, capture_output, text):
        del check, capture_output, text
        calls.append(command)
        output_index = command.index("--file") + 1
        Path(command[output_index]).write_bytes(b"backup")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("titan.core.persistence.subprocess.run", _fake_run)
    try:
        result = adapter.backup_database(backup_dir=tmp_path, keep=5)
        assert result is not None
        assert result.name.endswith(".dump")
        assert result.exists()
        assert calls and calls[0][0] == "pg_dump"
        assert "--dbname" in calls[0]
    finally:
        monkeypatch.undo()
        adapter.close()


@pytest.mark.integration
def test_postgres_adapter_backup_failure_raises_runtime_error(tmp_path) -> None:
    _engine, adapter = _build_test_engine()

    def _fail_run(command, *, check, capture_output, text):
        del check, capture_output, text
        raise subprocess.CalledProcessError(1, command, stderr="boom")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("titan.core.persistence.subprocess.run", _fail_run)
    try:
        with pytest.raises(RuntimeError, match="pg_dump failed"):
            adapter.backup_database(backup_dir=tmp_path)
        assert list(tmp_path.glob("*.dump")) == []
    finally:
        monkeypatch.undo()
        adapter.close()


@pytest.mark.integration
def test_sqlite_and_postgres_backup_paths_remain_backend_specific(tmp_path) -> None:
    sqlite_adapter = SQLiteAdapter(db_name="adapter.db", db_dir=tmp_path)
    _engine, postgres_adapter = _build_test_engine()

    def _fake_run(command, *, check, capture_output, text):
        del check, capture_output, text
        output_index = command.index("--file") + 1
        Path(command[output_index]).write_bytes(b"backup")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("titan.core.persistence.subprocess.run", _fake_run)
    try:
        sqlite_backup = sqlite_adapter.backup_database(backup_dir=tmp_path / "sqlite")
        postgres_backup = postgres_adapter.backup_database(backup_dir=tmp_path / "postgres")

        assert sqlite_backup is not None
        assert sqlite_backup.suffix == ".db"
        assert postgres_backup is not None
        assert postgres_backup.suffix == ".dump"
    finally:
        monkeypatch.undo()
        sqlite_adapter.close()
        postgres_adapter.close()


class _FakeAthleteContextAdapter:
    def __init__(self) -> None:
        self.closed = False

    def get_baseline_rhr(self, days: int = 7, athlete_id: str = "owner") -> float | None:
        return 50.126

    def get_hrv_history(
        self, days: int = 14, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        return [("2026-03-14", 42.678)]

    def get_weight_history(
        self, days: int = 30, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        return [("2026-03-14", 71.239)]

    def get_training_load_history(
        self, days: int | None = None, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        return [("2026-03-14", 123.456)]

    def get_ctl_atl_tsb(self, athlete_id: str = "owner") -> tuple[float, float, float]:
        return (41.239, 51.875, -10.636)

    def get_governance_decisions(
        self, limit: int = 1000, athlete_id: str = "owner"
    ) -> list[dict[str, object]]:
        return [{"date": datetime(2026, 3, 14, 6, 30, tzinfo=UTC), "governance_clean": True}]

    def close(self) -> None:
        self.closed = True


@pytest.mark.integration
def test_get_athlete_context_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAthleteContextAdapter()
    monkeypatch.setattr("titan.core.persistence.get_persistence_adapter", lambda: fake)

    result = get_athlete_context("athlete-123", days=3)

    assert result["athlete_id"] == "athlete-123"
    assert result["days"] == 3
    assert result["biometrics"]["baseline_rhr"] == 50.13
    assert result["biometrics"]["latest_hrv"] == 42.68
    assert result["training"]["ctl"] == 41.24
    assert result["training"]["training_load_history"] == [["2026-03-14", 123.46]]
    assert result["governance"]["recent_decisions"][0]["date"].startswith("2026-03-14T06:30:00")
    assert fake.closed is True


@pytest.mark.integration
def test_get_athlete_context_boundary_invalid_days(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAthleteContextAdapter()
    monkeypatch.setattr("titan.core.persistence.get_persistence_adapter", lambda: fake)

    with pytest.raises(ValueError, match="days must be >= 1"):
        get_athlete_context("athlete-123", days=0)

    assert fake.closed is False


@pytest.mark.integration
def test_get_athlete_context_omits_governance_when_flag_false(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAthleteContextAdapter()
    monkeypatch.setattr("titan.core.persistence.get_persistence_adapter", lambda: fake)

    result = get_athlete_context("athlete-123", include_governance=False)

    assert "governance" not in result
    assert "training" in result
    assert "biometrics" in result


@pytest.mark.integration
def test_get_athlete_context_omits_training_when_flag_false(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAthleteContextAdapter()
    monkeypatch.setattr("titan.core.persistence.get_persistence_adapter", lambda: fake)

    result = get_athlete_context("athlete-123", include_training=False)

    assert "training" not in result
    assert "governance" in result
    assert "biometrics" in result


@pytest.mark.integration
def test_get_athlete_context_omits_biometrics_when_flag_false(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAthleteContextAdapter()
    monkeypatch.setattr("titan.core.persistence.get_persistence_adapter", lambda: fake)

    result = get_athlete_context("athlete-123", include_biometrics=False)

    assert "biometrics" not in result
    assert "governance" in result
    assert "training" in result


@pytest.mark.integration
def test_get_persistence_adapter_uses_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN_DB_BACKEND", "sqlite")

    adapter = get_persistence_adapter()
    try:
        assert isinstance(adapter, SQLiteAdapter)
    finally:
        adapter.close()


# ---------------------------------------------------------------------------
# ADR-0033-L3-D-RESOLVED: athlete_id isolation tests
# One test per updated read method confirming cross-athlete contamination
# is prevented. (PostgreSQLAdapter path, using in-memory SQLite engine.)
# ---------------------------------------------------------------------------


def _build_two_athlete_engine() -> tuple:
    """Return (engine, adapter) with daily_metrics, training_log, and
    governance_outcomes pre-seeded for 'athlete_a' and 'athlete_b'."""
    from datetime import UTC, datetime

    _today = datetime.now(UTC).date().isoformat()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE daily_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'owner',
                date TEXT NOT NULL,
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
            CREATE TABLE training_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'owner',
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
                notes TEXT,
                garmin_activity_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE gear_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'owner',
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
            CREATE TABLE personal_bests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id TEXT NOT NULL DEFAULT 'owner',
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
                athlete_id TEXT NOT NULL DEFAULT 'owner',
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

        # Seed daily_metrics: athlete_a rhr=55, athlete_b rhr=70
        conn.execute(text(
            "INSERT INTO daily_metrics (athlete_id, date, resting_hr, hrv_rmssd, weight_kg) "
            f"VALUES ('athlete_a', '{_today}', 55, 42.0, 68.0)"
        ))
        conn.execute(text(
            "INSERT INTO daily_metrics (athlete_id, date, resting_hr, hrv_rmssd, weight_kg) "
            f"VALUES ('athlete_b', '{_today}', 70, 35.0, 80.0)"
        ))

        # Seed training_log: athlete_a load=100, athlete_b load=200
        conn.execute(text(
            "INSERT INTO training_log (athlete_id, date, session_type, distance_km, "
            "duration_sec, training_load) "
            f"VALUES ('athlete_a', '{_today}', 'EASY', 10.0, 3600, 100)"
        ))
        conn.execute(text(
            "INSERT INTO training_log (athlete_id, date, session_type, distance_km, "
            "duration_sec, training_load) "
            f"VALUES ('athlete_b', '{_today}', 'TEMPO', 8.0, 2400, 200)"
        ))

        # Seed governance_outcomes: athlete_a acwr=0.9, athlete_b acwr=1.2
        conn.execute(text(
            "INSERT INTO governance_outcomes "
            "(athlete_id, date, session_planned, session_post_governance, "
            "locks_applied_json, governance_clean, phase, vlg_color, "
            "apl_priority_vector_json, lock_thresholds_active_json, "
            "acwr, tsb_value, readiness_score, glycogen_debt, algorithm_version_snapshot) "
            f"VALUES ('athlete_a', '{_today}', 'EASY', 'EASY', '[]', 1, 'P8', "
            "'GREEN', '[]', '{}', 0.9, 5.0, 80.0, 0.1, '{}')"
        ))
        conn.execute(text(
            "INSERT INTO governance_outcomes "
            "(athlete_id, date, session_planned, session_post_governance, "
            "locks_applied_json, governance_clean, phase, vlg_color, "
            "apl_priority_vector_json, lock_thresholds_active_json, "
            "acwr, tsb_value, readiness_score, glycogen_debt, algorithm_version_snapshot) "
            f"VALUES ('athlete_b', '{_today}', 'TEMPO', 'TEMPO', '[]', 1, 'P8', "
            "'YELLOW', '[]', '{}', 1.2, -5.0, 70.0, 2.0, '{}')"
        ))

    adapter = PostgreSQLAdapter(dsn="postgres://unused/titan", engine=engine)
    return engine, adapter


@pytest.mark.integration
def test_get_baseline_rhr_isolated_by_athlete_id() -> None:
    """get_baseline_rhr() returns data for the specified athlete only."""
    _engine, adapter = _build_two_athlete_engine()
    try:
        rhr_a = adapter.get_baseline_rhr(days=365, athlete_id="athlete_a")
        rhr_b = adapter.get_baseline_rhr(days=365, athlete_id="athlete_b")
        assert rhr_a == 55.0
        assert rhr_b == 70.0
        assert rhr_a != rhr_b
    finally:
        adapter.close()


@pytest.mark.integration
def test_get_hrv_history_isolated_by_athlete_id() -> None:
    """get_hrv_history() returns data for the specified athlete only."""
    _engine, adapter = _build_two_athlete_engine()
    try:
        hrv_a = adapter.get_hrv_history(days=365, athlete_id="athlete_a")
        hrv_b = adapter.get_hrv_history(days=365, athlete_id="athlete_b")
        assert len(hrv_a) == 1
        assert hrv_a[0][1] == 42.0
        assert len(hrv_b) == 1
        assert hrv_b[0][1] == 35.0
        assert hrv_a[0][1] != hrv_b[0][1]
    finally:
        adapter.close()


@pytest.mark.integration
def test_get_weight_history_isolated_by_athlete_id() -> None:
    """get_weight_history() returns data for the specified athlete only."""
    _engine, adapter = _build_two_athlete_engine()
    try:
        w_a = adapter.get_weight_history(days=365, athlete_id="athlete_a")
        w_b = adapter.get_weight_history(days=365, athlete_id="athlete_b")
        assert len(w_a) == 1
        assert w_a[0][1] == 68.0
        assert len(w_b) == 1
        assert w_b[0][1] == 80.0
        assert w_a[0][1] != w_b[0][1]
    finally:
        adapter.close()


@pytest.mark.integration
def test_get_training_load_history_isolated_by_athlete_id() -> None:
    """get_training_load_history() returns data for the specified athlete only."""
    _engine, adapter = _build_two_athlete_engine()
    try:
        loads_a = adapter.get_training_load_history(days=365, athlete_id="athlete_a")
        loads_b = adapter.get_training_load_history(days=365, athlete_id="athlete_b")
        assert len(loads_a) == 1
        assert loads_a[0][1] == 100.0
        assert len(loads_b) == 1
        assert loads_b[0][1] == 200.0
        assert loads_a[0][1] != loads_b[0][1]
    finally:
        adapter.close()


@pytest.mark.integration
def test_get_ctl_atl_tsb_isolated_by_athlete_id() -> None:
    """get_ctl_atl_tsb() returns computed values for the specified athlete only."""
    _engine, adapter = _build_two_athlete_engine()
    try:
        ctl_a, atl_a, tsb_a = adapter.get_ctl_atl_tsb(athlete_id="athlete_a")
        ctl_b, atl_b, tsb_b = adapter.get_ctl_atl_tsb(athlete_id="athlete_b")
        # athlete_a has training_load=100, athlete_b has training_load=200
        assert ctl_a != ctl_b or atl_a != atl_b  # at least one differs
        # Verify isolation: athlete_b load (200) must produce higher CTL than athlete_a (100)
        assert ctl_b > ctl_a
    finally:
        adapter.close()


@pytest.mark.integration
def test_get_governance_decisions_isolated_by_athlete_id() -> None:
    """get_governance_decisions() returns data for the specified athlete only."""
    _engine, adapter = _build_two_athlete_engine()
    try:
        decisions_a = adapter.get_governance_decisions(limit=100, athlete_id="athlete_a")
        decisions_b = adapter.get_governance_decisions(limit=100, athlete_id="athlete_b")
        assert len(decisions_a) == 1
        assert decisions_a[0]["acwr"] == 0.9
        assert len(decisions_b) == 1
        assert decisions_b[0]["acwr"] == 1.2
        assert decisions_a[0]["acwr"] != decisions_b[0]["acwr"]
    finally:
        adapter.close()
