"""Tests for PersistenceAdapter abstract contract — T5-08-B D1."""

from __future__ import annotations

import types

import pytest

from titan.core.persistence import PersistenceAdapter

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
    ConcreteAdapter = types.new_class(
        "ConcreteAdapter",
        (PersistenceAdapter,),
        {},
        lambda ns: ns.update(stubs),
    )
    adapter = ConcreteAdapter()
    assert isinstance(adapter, PersistenceAdapter)


def test_persistence_adapter_is_abstract_base_class() -> None:
    from abc import ABC

    assert issubclass(PersistenceAdapter, ABC)
