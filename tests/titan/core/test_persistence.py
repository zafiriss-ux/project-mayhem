"""Tests for PersistenceAdapter abstract contract — T5-08-B D1."""

from __future__ import annotations

import types
from datetime import UTC, datetime

import pytest

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


class _RecordingPostgresManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def save_session(self, *args, **kwargs) -> None:
        self.calls.append(("save_session", args, kwargs))

    def get_training_load_history(self, *args, **kwargs):
        self.calls.append(("get_training_load_history", args, kwargs))
        return [("2026-01-01", 42.0)]

    def get_ctl_atl_tsb(self):
        self.calls.append(("get_ctl_atl_tsb", (), {}))
        return (1.0, 2.0, -1.0)

    def save_governance_decision(self, *args, **kwargs) -> None:
        self.calls.append(("save_governance_decision", args, kwargs))

    def get_governance_decisions(self, *args, **kwargs):
        self.calls.append(("get_governance_decisions", args, kwargs))
        return [{"date": "2026-01-01"}]

    def close(self) -> None:
        self.calls.append(("close", (), {}))


class _IncompletePostgresManager:
    def close(self) -> None:
        return None


@pytest.mark.parametrize("method_name, args, kwargs", [
    ("save_session", ("2026-01-01", "EASY", 10.0, 1800), {"rpe": 4}),
    ("get_training_load_history", (), {"days": 7}),
    ("get_ctl_atl_tsb", (), {}),
    ("save_governance_decision", ({"date": "2026-01-01"},), {}),
    ("get_governance_decisions", (), {"limit": 10}),
])
def test_postgres_adapter_delegates_supported_methods(
    method_name: str,
    args: tuple,
    kwargs: dict,
) -> None:
    manager = _RecordingPostgresManager()
    adapter = PostgreSQLAdapter(dsn="postgres://unused", manager=manager)

    result = getattr(adapter, method_name)(*args, **kwargs)

    assert manager.calls[-1][0] == method_name
    if method_name in {"get_training_load_history", "get_ctl_atl_tsb", "get_governance_decisions"}:
        assert result is not None
    else:
        assert result is None


def test_postgres_adapter_boundary_unsupported_method_raises_not_implemented() -> None:
    adapter = PostgreSQLAdapter(
        dsn="postgres://unused",
        manager=_IncompletePostgresManager(),
    )

    with pytest.raises(NotImplementedError, match="save_daily_metric"):
        adapter.save_daily_metric("2026-01-01", rhr=47)


def test_postgres_adapter_close_delegates() -> None:
    manager = _RecordingPostgresManager()
    adapter = PostgreSQLAdapter(dsn="postgres://unused", manager=manager)

    adapter.close()

    assert manager.calls[-1][0] == "close"
