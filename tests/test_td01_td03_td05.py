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
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import AuthStore, hash_password
from titan.api.main import CSRF_HEADER_NAME, CoachAuditStore, create_app
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

    def test_require_coach_athlete_access_fails_closed_when_db_none(self):
        """COACH role, non-owner athlete_id, db is None → 403 (INV-11 fail-closed)."""
        from fastapi import HTTPException

        req = _make_request(path_params={"athlete_id": "athlete-Z"}, db=None)
        coach = _make_auth_user("COACH", user_id="coach-1")

        with pytest.raises(HTTPException) as exc_info:
            self._deps.require_coach_athlete_access(req, coach)

        assert exc_info.value.status_code == 403
        assert "unavailable" in exc_info.value.detail.lower()

    def test_require_coach_athlete_access_owner_not_assigned_gets_403(self):
        """INV-11: COACH not assigned to owner, athlete_id='owner' → 403."""
        from fastapi import HTTPException

        db = MagicMock()
        db.get_assigned_athletes.return_value = []

        req = _make_request(path_params={"athlete_id": "owner"}, db=db)
        coach = _make_auth_user("COACH", user_id="coach-1")

        with pytest.raises(HTTPException) as exc_info:
            self._deps.require_coach_athlete_access(req, coach)

        assert exc_info.value.status_code == 403

    def test_require_coach_athlete_access_owner_assigned_passes(self):
        """INV-11: COACH assigned to owner, athlete_id='owner' → allow."""
        db = MagicMock()
        db.get_assigned_athletes.return_value = ["owner"]

        req = _make_request(path_params={"athlete_id": "owner"}, db=db)
        coach = _make_auth_user("COACH", user_id="coach-1")

        result = self._deps.require_coach_athlete_access(req, coach)
        assert result is coach

    def test_require_coach_athlete_access_non_coach_owner_passes(self):
        """ATHLETE role (owner's own session) accessing owner data is unaffected by coach gate."""
        req = _make_request(path_params={"athlete_id": "owner"})
        owner_user = _make_auth_user("ATHLETE", user_id="owner-1", athlete_id="owner")

        result = self._deps.require_coach_athlete_access(req, owner_user)
        assert result is owner_user

    def test_require_coach_athlete_access_no_athlete_id_passes_coach(self):
        """No athlete_id in request → permissive (not an athlete-scoped route), even for COACH."""
        req = _make_request()
        coach = _make_auth_user("COACH", user_id="coach-1")

        result = self._deps.require_coach_athlete_access(req, coach)
        assert result is coach


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
        from titan.config.settings import get_settings
        from titan.integrations.garmin_sync import _is_dev_environment

        # get_settings() is lru_cache'd (P15-ARCH5); clear it after each env change so the
        # next read reflects the new TITAN_ENV (matches the tests/test_garmin_sync.py idiom).
        monkeypatch.setenv("TITAN_ENV", "dev")
        get_settings.cache_clear()
        assert _is_dev_environment() is True

        monkeypatch.setenv("TITAN_ENV", "test")
        get_settings.cache_clear()
        assert _is_dev_environment() is True

        monkeypatch.setenv("TITAN_ENV", "prod")
        get_settings.cache_clear()
        assert _is_dev_environment() is False

        monkeypatch.delenv("TITAN_ENV", raising=False)
        get_settings.cache_clear()
        assert _is_dev_environment() is False


# ─────────────────────────────────────────────────────────────────────────────
# TD-02: SQLite reader lock — concurrent read/write safety
# ─────────────────────────────────────────────────────────────────────────────

class TestSQLiteReaderLock:
    def test_concurrent_read_write_no_corruption(self):
        """TD-02: concurrent read+write must not corrupt training load history."""
        from titan.core.database import DatabaseManager

        db = DatabaseManager(":memory:")
        errors = []

        def writer():
            for i in range(20):
                try:
                    db.save_session(
                        date=f"2026-0{i % 9 + 1}-01",
                        session_type="EASY",
                        distance_km=10.0,
                        duration_sec=3600,
                        avg_hr=140,
                    )
                except Exception as e:
                    errors.append(e)

        def reader():
            for _ in range(20):
                try:
                    db.get_training_load_history(30)
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Concurrent errors: {errors}"


# ─────────────────────────────────────────────────────────────────────────────
# TD-01 (route-level): COACH RBAC on the three assignment-scoped endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _make_rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


_ATHLETE_SCOPED_ROUTES = [
    ("POST", "/coach/overrides?athlete_id=athlete-2", {"reason": "r"}),
    ("GET", "/coach/export?athlete_id=athlete-2", None),
    ("DELETE", "/coach/athlete-data?athlete_id=athlete-2", None),
]


class TestCoachRBACRoutes:
    """Route-level integration tests for COACH RBAC on the three athlete-scoped endpoints."""

    @pytest.fixture(autouse=True)
    def setup_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        private_pem, public_pem = _make_rsa_keypair()
        monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", private_pem)
        monkeypatch.setenv("TITAN_JWT_PUBLIC_KEY", public_pem)

        auth_store = AuthStore()
        auth_store.upsert_user(
            user_id="coach-1",
            username="coach",
            password_hash=hash_password("coach-pass"),
            role="COACH",
            athlete_id=None,
        )
        self.app = create_app(auth_store=auth_store, audit_store=CoachAuditStore())
        self.client = TestClient(self.app, base_url="https://testserver")
        r = self.client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
        assert r.status_code == 200

    def _csrf(self) -> dict[str, str]:
        r = self.client.get("/api/csrf-token")
        return {CSRF_HEADER_NAME: r.json()["csrf_token"]}

    def _request(self, method: str, url: str, payload: dict | None) -> object:
        csrf = self._csrf()
        if method == "POST":
            return self.client.post(url, json=payload, headers=csrf)
        if method == "GET":
            return self.client.get(url)
        return self.client.delete(url, headers=csrf)

    @pytest.mark.integration
    def test_coach_not_assigned_gets_403_on_all_three_routes(self) -> None:
        """Authenticated COACH not assigned to athlete-2 must receive 403 on each route."""
        db = MagicMock()
        db.get_assigned_athletes.return_value = []
        self.app.state.db = db

        for method, url, payload in _ATHLETE_SCOPED_ROUTES:
            r = self._request(method, url, payload)
            assert r.status_code == 403, f"{method} {url} expected 403, got {r.status_code}"

    @pytest.mark.integration
    def test_coach_assigned_gets_200_on_all_three_routes(self) -> None:
        """Authenticated COACH assigned to athlete-2 must receive 200 on each route."""
        db = MagicMock()
        db.get_assigned_athletes.return_value = ["athlete-2"]
        self.app.state.db = db

        for method, url, payload in _ATHLETE_SCOPED_ROUTES:
            r = self._request(method, url, payload)
            assert r.status_code == 200, f"{method} {url} expected 200, got {r.status_code}"
