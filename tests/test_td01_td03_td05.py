"""Production Readiness Audit 2026-05-15 — TD-01, TD-03, TD-05, TD-18 tests.

Tests for:
  TD-01: RBAC flat-trust fix in titan/api/dependencies.py
  TD-03: Override lockdown default-deny on cold start
  TD-05: Morning routine dedup Lock replaces is_alive() check
  TD-18: Garmin token requires encryption key in production
"""
from __future__ import annotations

import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from titan.science.governance_engine import GovernanceEngine

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_auth_user(role: str, user_id: str = "user-1", athlete_id: str | None = None):
    """Create AuthUser without importing titan.api.auth (avoids pyo3 conflict)."""
    from titan.api.models import AuthUser
    return AuthUser(id=user_id, username="testuser", role=role, athlete_id=athlete_id)


def _make_request(path_params: dict | None = None, query_params: dict | None = None, db=None):
    """Build a minimal fake Request for dependency tests."""
    req = MagicMock()
    req.path_params = path_params or {}
    req.query_params = query_params or {}
    app_state = SimpleNamespace(db=db)
    req.app = SimpleNamespace(state=app_state)
    return req


def _import_dependencies():
    """Import titan.api.dependencies with auth mocked out to avoid pyo3 crash."""
    import importlib

    # Stub titan.api.auth if cryptography is broken in this environment
    if "titan.api.auth" not in sys.modules:
        auth_stub = MagicMock()
        auth_stub.ACCESS_COOKIE_NAME = "access_token"
        auth_stub.AuthError = Exception
        sys.modules["titan.api.auth"] = auth_stub

    if "titan.api.dependencies" in sys.modules:
        return sys.modules["titan.api.dependencies"]
    return importlib.import_module("titan.api.dependencies")


# ─────────────────────────────────────────────────────────────────────────────
# TD-01: RBAC — require_athlete_access and require_coach_athlete_access
# ─────────────────────────────────────────────────────────────────────────────

class TestCoachRBAC:
    @pytest.fixture(autouse=True)
    def deps(self):
        self._deps = _import_dependencies()

    def test_coach_cannot_access_unassigned_athlete(self):
        """COACH with no assignment to athlete-X must get 403."""
        from fastapi import HTTPException

        db = MagicMock()
        db.get_assigned_athletes.return_value = ["athlete-other"]

        req = _make_request(path_params={"athlete_id": "athlete-X"}, db=db)
        coach = _make_auth_user("COACH", user_id="coach-1")

        with pytest.raises(HTTPException) as exc_info:
            self._deps.require_athlete_access(coach, "athlete-X", request=req)

        assert exc_info.value.status_code == 403
        assert "athlete-X" in exc_info.value.detail

    def test_coach_can_access_assigned_athlete(self):
        """COACH assigned to athlete-Y must pass without 403."""
        db = MagicMock()
        db.get_assigned_athletes.return_value = ["athlete-Y", "athlete-Z"]

        req = _make_request(path_params={"athlete_id": "athlete-Y"}, db=db)
        coach = _make_auth_user("COACH", user_id="coach-1")

        # Must not raise
        self._deps.require_athlete_access(coach, "athlete-Y", request=req)

    def test_coach_owner_endpoint_passes(self):
        """COACH on owner-scoped request must not be blocked."""
        db = MagicMock()
        db.get_assigned_athletes.return_value = []

        req = _make_request(db=db)
        coach = _make_auth_user("COACH", user_id="coach-1")

        # athlete_id == "owner" must bypass assignment check
        self._deps.require_athlete_access(coach, "owner", request=req)

    def test_athlete_isolation_enforced(self):
        """ATHLETE trying to access another athlete's data must get 403."""
        from fastapi import HTTPException

        athlete = _make_auth_user("ATHLETE", user_id="self-1", athlete_id="athlete-1")
        req = _make_request()

        with pytest.raises(HTTPException) as exc_info:
            self._deps.require_athlete_access(athlete, "athlete-2", request=req)

        assert exc_info.value.status_code == 403

    def test_get_athlete_id_from_path_param(self):
        req = _make_request(path_params={"athlete_id": "abc-123"})
        assert self._deps._get_athlete_id_from_request(req) == "abc-123"

    def test_get_athlete_id_from_query_param(self):
        req = _make_request(query_params={"athlete_id": "qry-456"})
        assert self._deps._get_athlete_id_from_request(req) == "qry-456"

    def test_get_athlete_id_returns_none_when_absent(self):
        req = _make_request()
        assert self._deps._get_athlete_id_from_request(req) is None

    def test_require_coach_athlete_access_blocks_unassigned(self):
        """require_coach_athlete_access blocks COACH from unassigned athlete path."""
        from fastapi import HTTPException

        db = MagicMock()
        db.get_assigned_athletes.return_value = []

        req = _make_request(path_params={"athlete_id": "athlete-Z"}, db=db)
        coach = _make_auth_user("COACH", user_id="coach-1")

        with pytest.raises(HTTPException) as exc_info:
            self._deps.require_coach_athlete_access(req, coach)

        assert exc_info.value.status_code == 403

    def test_require_coach_athlete_access_passes_assigned(self):
        """require_coach_athlete_access passes COACH for assigned athlete."""
        db = MagicMock()
        db.get_assigned_athletes.return_value = ["athlete-A"]

        req = _make_request(path_params={"athlete_id": "athlete-A"}, db=db)
        coach = _make_auth_user("COACH", user_id="coach-1")

        result = self._deps.require_coach_athlete_access(req, coach)
        assert result is coach

    def test_require_coach_athlete_access_non_coach_passes(self):
        """ATHLETE role bypasses coach assignment check entirely."""
        req = _make_request(path_params={"athlete_id": "athlete-1"})
        athlete = _make_auth_user("ATHLETE", user_id="self-1", athlete_id="athlete-1")

        result = self._deps.require_coach_athlete_access(req, athlete)
        assert result is athlete


# ─────────────────────────────────────────────────────────────────────────────
# TD-03: Override lockdown — cold start default-deny
# ─────────────────────────────────────────────────────────────────────────────

class _NoneRatioDB:
    """DB stub returning None — simulates no outcome history (cold start)."""
    def get_override_ratio(self, **_kwargs):
        return None


class _FloatRatioDB:
    """DB stub returning a safe ratio — has outcome history."""
    def __init__(self, ratio: float = 0.10):
        self._ratio = ratio

    def get_override_ratio(self, **_kwargs):
        return self._ratio


class TestOverrideLockdownColdStart:
    def test_override_lockdown_cold_start_locked(self):
        """No outcome history (None ratio) → locked=True, reason=cold_start_no_history."""
        gov = GovernanceEngine()
        result = gov.check_override_lockdown(db=_NoneRatioDB())

        assert result["locked"] is True
        assert result.get("reason") == "cold_start_no_history"

    def test_override_lockdown_cold_start_max_zone_2(self):
        """Cold-start lock must cap at zone 2."""
        gov = GovernanceEngine()
        result = gov.check_override_lockdown(db=_NoneRatioDB())

        assert result.get("max_zone") == 2

    def test_override_lockdown_with_history_not_auto_locked(self):
        """When override ratio is within threshold, gate must NOT auto-lock."""
        gov = GovernanceEngine()
        result = gov.check_override_lockdown(db=_FloatRatioDB(ratio=0.10))

        assert result["locked"] is False
        assert result.get("ratio") == pytest.approx(0.10)

    def test_override_lockdown_with_history_above_threshold_locks(self):
        """Override ratio above threshold must still lock normally."""
        gov = GovernanceEngine()
        result = gov.check_override_lockdown(db=_FloatRatioDB(ratio=0.90))

        assert result["locked"] is True
        assert result.get("ratio") == pytest.approx(0.90)


# ─────────────────────────────────────────────────────────────────────────────
# TD-05: Morning routine dedup — Lock-based guard
# ─────────────────────────────────────────────────────────────────────────────

class TestMorningRoutineDedupLock:
    def _make_coach_stub(self):
        """Create minimal DailyCoach stub with _routine_mutex (skips __init__)."""
        from titan.orchestration.daily_coach import DailyCoach
        coach = DailyCoach.__new__(DailyCoach)
        coach._routine_mutex = threading.Lock()
        coach._routine_thread = None
        coach._routine_started_monotonic = None
        return coach

    def test_morning_routine_dedup_blocks_concurrent(self):
        """Lock held externally → run_morning_routine_async returns False."""
        coach = self._make_coach_stub()
        coach.run_morning_routine = lambda: None

        coach._routine_mutex.acquire()
        try:
            result = coach.run_morning_routine_async(trigger_source="test_concurrent")
            assert result is False
        finally:
            coach._routine_mutex.release()

    def test_morning_routine_starts_when_idle(self):
        """Lock free → run_morning_routine_async returns True and starts thread."""
        coach = self._make_coach_stub()
        ran = threading.Event()

        def _routine():
            ran.set()

        coach.run_morning_routine = _routine
        result = coach.run_morning_routine_async(trigger_source="test_idle")

        assert result is True
        assert ran.wait(timeout=2), "routine thread did not execute within 2s"

    def test_morning_routine_lock_released_after_run(self):
        """After the routine completes, the mutex must be released."""
        coach = self._make_coach_stub()
        done = threading.Event()

        def _routine():
            done.set()

        coach.run_morning_routine = _routine
        coach.run_morning_routine_async(trigger_source="test_release")
        done.wait(timeout=2)
        coach._routine_thread.join(timeout=2)

        acquired = coach._routine_mutex.acquire(blocking=False)
        assert acquired, "mutex was not released after routine completed"
        coach._routine_mutex.release()

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_morning_routine_lock_released_after_exception(self):
        """If the routine raises, the mutex must still be released."""
        coach = self._make_coach_stub()

        def _failing_routine():
            raise RuntimeError("routine error")

        coach.run_morning_routine = _failing_routine
        coach.run_morning_routine_async(trigger_source="test_exception")
        coach._routine_thread.join(timeout=2)

        acquired = coach._routine_mutex.acquire(blocking=False)
        assert acquired, "mutex was not released after routine raised"
        coach._routine_mutex.release()


# ─────────────────────────────────────────────────────────────────────────────
# TD-18: Garmin token — require key in production
# ─────────────────────────────────────────────────────────────────────────────

class TestGarminTokenProdRequirement:
    """Tests for TD-18: Garmin token encryption requirement in production.

    These tests mock Fernet to avoid pyo3/cryptography environment conflicts
    present in the CI sandbox. The production path under test is the
    _is_dev_environment() guard and RuntimeError raise in _encrypt_token /
    _decrypt_token — not the Fernet encryption itself.
    """

    @pytest.fixture(autouse=True)
    def _mock_fernet(self):
        """Stub out cryptography.fernet.Fernet to avoid pyo3 crash."""
        fake_fernet_cls = MagicMock()
        fake_fernet_cls.return_value.encrypt.return_value = b"<encrypted>"
        fake_fernet_cls.return_value.decrypt.return_value = b"<decrypted>"
        with patch.dict(
            "sys.modules",
            {"cryptography.fernet": MagicMock(Fernet=fake_fernet_cls)},
        ):
            yield

    def test_garmin_token_requires_key_in_prod(self, monkeypatch):
        """Missing TITAN_GARTH_TOKEN_KEY in production must raise RuntimeError."""
        monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
        monkeypatch.setenv("TITAN_ENV", "prod")

        from titan.integrations import garmin_sync
        with patch.object(garmin_sync, "_get_token_encryption_key", return_value=None), pytest.raises(RuntimeError, match="TITAN_GARTH_TOKEN_KEY must be set"):
            garmin_sync._encrypt_token("some_token_data")

    def test_garmin_token_optional_in_dev(self, monkeypatch):
        """Missing TITAN_GARTH_TOKEN_KEY in dev must not raise."""
        monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
        monkeypatch.setenv("TITAN_ENV", "dev")

        from titan.integrations import garmin_sync
        with patch.object(garmin_sync, "_get_token_encryption_key", return_value=None):
            result = garmin_sync._encrypt_token("test_token")
            assert result == b"test_token"

    def test_garmin_token_optional_in_test_env(self, monkeypatch):
        """Missing TITAN_GARTH_TOKEN_KEY in test env must not raise."""
        monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
        monkeypatch.setenv("TITAN_ENV", "test")

        from titan.integrations import garmin_sync
        with patch.object(garmin_sync, "_get_token_encryption_key", return_value=None):
            result = garmin_sync._encrypt_token("test_token")
            assert result == b"test_token"

    def test_garmin_token_decrypt_requires_key_in_prod(self, monkeypatch):
        """Missing TITAN_GARTH_TOKEN_KEY in production must raise on decrypt."""
        monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
        monkeypatch.setenv("TITAN_ENV", "prod")

        from titan.integrations import garmin_sync
        with patch.object(garmin_sync, "_get_token_encryption_key", return_value=None), pytest.raises(RuntimeError, match="TITAN_GARTH_TOKEN_KEY must be set"):
            garmin_sync._decrypt_token(b"some_encrypted_bytes")

    def test_is_dev_environment_detection(self, monkeypatch):
        """_is_dev_environment correctly identifies dev/test vs prod."""
        from titan.integrations.garmin_sync import _is_dev_environment

        monkeypatch.setenv("TITAN_ENV", "dev")
        assert _is_dev_environment() is True

        monkeypatch.setenv("TITAN_ENV", "test")
        assert _is_dev_environment() is True

        monkeypatch.setenv("TITAN_ENV", "prod")
        assert _is_dev_environment() is False

        monkeypatch.delenv("TITAN_ENV", raising=False)
        assert _is_dev_environment() is False
