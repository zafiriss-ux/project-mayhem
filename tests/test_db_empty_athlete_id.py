"""MA-F3 8β (D-123): DatabaseManager refuses an athlete id that was passed but is empty.

Every public method that takes ``athlete_id`` refuses ``""`` and blanks, and refuses
``None`` unless its signature allows ``None`` (an auth user with no athlete). An id that
is not passed at all keeps the owner default. Synthetic data only.
"""

import inspect

import pytest

from titan.core.database import DatabaseManager


def _athlete_methods():
    names = []
    for name, member in inspect.getmembers(DatabaseManager, inspect.isfunction):
        if name.startswith("_"):
            continue
        if "athlete_id" in inspect.signature(member).parameters:
            names.append(name)
    return names


_METHODS = _athlete_methods()


def test_the_check_covers_the_methods_the_audit_named():
    # The audit counted 37 methods with an owner default; the sweep must see them.
    assert len(_METHODS) >= 37
    for name in ("save_daily_metric", "save_governance_decision", "get_governance_decisions",
                 "get_daily_metric", "save_session", "get_ctl_atl_tsb"):
        if name != "save_governance_decision":  # takes a decision dict (8α)
            assert name in _METHODS


@pytest.mark.parametrize("name", _METHODS)
@pytest.mark.parametrize("empty", ["", "   "])
def test_every_athlete_method_refuses_an_empty_id_before_touching_the_db(db_manager_factory, name, empty):
    db = db_manager_factory(db_name="test.db")
    method = getattr(db, name)
    with pytest.raises(ValueError, match="athlete_id"):
        # Only the id is real: the check runs before any argument is used.
        _call_with_only_the_id(method, empty)


@pytest.mark.parametrize("name", _METHODS)
def test_none_is_refused_unless_the_signature_allows_it(db_manager_factory, name):
    db = db_manager_factory(db_name="test.db")
    method = getattr(db, name)
    annotation = str(inspect.signature(getattr(DatabaseManager, name)).parameters["athlete_id"].annotation)
    if "None" in annotation:
        pytest.skip("this method's athlete_id may be None by design")
    with pytest.raises(ValueError, match="athlete_id"):
        _call_with_only_the_id(method, None)


def _call_with_only_the_id(method, athlete_id):
    params = inspect.signature(method).parameters
    kwargs = {}
    for pname, p in params.items():
        if pname == "athlete_id":
            kwargs[pname] = athlete_id
        elif p.default is inspect.Parameter.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            kwargs[pname] = object()  # never reached: the id check comes first
    return method(**kwargs)


def test_save_daily_metric_with_an_empty_id_writes_nothing(db_manager_factory):
    db = db_manager_factory(db_name="test.db")
    with pytest.raises(ValueError, match="athlete_id"):
        db.save_daily_metric("2026-10-02", hrv=50.0, athlete_id="")
    assert db.conn.execute("SELECT count(*) FROM daily_metrics").fetchone()[0] == 0


def test_without_an_id_the_owner_default_stays(db_manager_factory):
    db = db_manager_factory(db_name="test.db")
    db.save_daily_metric("2026-10-02", hrv=50.0)
    rows = db.conn.execute("SELECT athlete_id FROM daily_metrics").fetchall()
    assert [tuple(r) for r in rows] == [("owner",)]
    assert db.get_daily_metric("2026-10-02") is not None


def test_an_auth_user_without_an_athlete_is_still_allowed(db_manager_factory):
    db = db_manager_factory(db_name="test.db")
    db.upsert_auth_user(user_id="u-coach", username="coach-x", password_hash="h", role="coach",
                        athlete_id=None)
    assert db.get_auth_user_by_id("u-coach")["athlete_id"] is None
