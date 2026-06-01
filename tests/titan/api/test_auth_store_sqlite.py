"""HD-04 / T5-70: AuthStore SQLite persistence tests (ADR-0048 conformance)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from titan.api.auth import (
    MAX_ACTIVE_REFRESH_TOKENS,
    AuthStore,
    hash_password,
    verify_password,
)
from titan.core.database import DatabaseManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path | None = None) -> AuthStore:
    """Return an AuthStore backed by either a real on-disk or in-memory DB."""
    if tmp_path is None:
        return AuthStore()  # in-memory
    db = DatabaseManager(db_name="test_auth.db", db_dir=tmp_path)
    return AuthStore(db=db)


def _future(minutes: int = 60) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


def _past(minutes: int = 60) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

class TestAuthStoreUserCrud:
    def test_upsert_and_get_user_round_trip(self) -> None:
        """create_user (upsert_user) + get_user must round-trip cleanly."""
        store = _make_store()
        store.upsert_user("u1", "alice", hash_password("secret"), "COACH", None)

        user = store.get_user("u1")
        assert user is not None
        assert user.id == "u1"
        assert user.username == "alice"
        assert user.role == "COACH"
        assert user.athlete_id is None
        assert user.is_active is True

    def test_get_user_unknown_id_returns_none(self) -> None:
        store = _make_store()
        assert store.get_user("no-such-id") is None

    def test_upsert_user_updates_existing_row(self) -> None:
        """Re-inserting with the same user_id must overwrite the row."""
        store = _make_store()
        store.upsert_user("u1", "alice", hash_password("s1"), "COACH", None)
        store.upsert_user("u1", "alice2", hash_password("s2"), "ATHLETE", "a1")

        user = store.get_user("u1")
        assert user is not None
        assert user.username == "alice2"
        assert user.role == "ATHLETE"
        assert user.athlete_id == "a1"

    def test_verify_credentials_success(self) -> None:
        store = _make_store()
        pw = "correct-horse"
        store.upsert_user("u1", "bob", hash_password(pw), "ATHLETE", "a1")

        result = store.verify_credentials("bob", pw)
        assert result is not None
        assert result.id == "u1"

    def test_verify_credentials_wrong_password_returns_none(self) -> None:
        store = _make_store()
        store.upsert_user("u1", "bob", hash_password("right-password"), "ATHLETE", "a1")
        assert store.verify_credentials("bob", "wrong-password") is None

    def test_verify_credentials_unknown_username_returns_none(self) -> None:
        store = _make_store()
        assert store.verify_credentials("nobody", "pass") is None

    def test_inactive_user_is_returned_by_get_user(self) -> None:
        """get_user returns the record regardless of is_active; callers decide."""
        store = _make_store()
        store.upsert_user("u1", "ghost", hash_password("p"), "COACH", None, is_active=False)
        user = store.get_user("u1")
        assert user is not None
        assert user.is_active is False


# ---------------------------------------------------------------------------
# Token lifecycle
# ---------------------------------------------------------------------------

class TestAuthStoreTokenLifecycle:
    def test_store_token_and_verify_active(self) -> None:
        """store_token (add_refresh_token) + is_refresh_token_active round-trip."""
        store = _make_store()
        store.upsert_user("u1", "alice", hash_password("p"), "COACH", None)
        issued = datetime.now(UTC)
        expires = _future(minutes=10080)  # 7 days

        store.add_refresh_token("jti-1", "u1", expires, issued)

        assert store.is_refresh_token_active("jti-1") is True

    def test_revoke_token_deactivates_it(self) -> None:
        store = _make_store()
        store.upsert_user("u1", "alice", hash_password("p"), "COACH", None)
        store.add_refresh_token("jti-1", "u1", _future(), datetime.now(UTC))
        assert store.is_refresh_token_active("jti-1") is True

        store.revoke_refresh_token("jti-1")
        assert store.is_refresh_token_active("jti-1") is False

    def test_expired_token_is_not_active(self) -> None:
        store = _make_store()
        store.upsert_user("u1", "alice", hash_password("p"), "COACH", None)
        store.add_refresh_token("jti-1", "u1", _past(minutes=5), _past(minutes=10))
        assert store.is_refresh_token_active("jti-1") is False

    def test_unknown_jti_is_not_active(self) -> None:
        store = _make_store()
        assert store.is_refresh_token_active("no-such-jti") is False

    def test_revoke_unknown_jti_is_noop(self) -> None:
        """Revoking a non-existent token must not raise."""
        store = _make_store()
        store.revoke_refresh_token("ghost-jti")  # must not raise

    def test_cleanup_expired_removes_expired_tokens(self) -> None:
        store = _make_store()
        store.upsert_user("u1", "alice", hash_password("p"), "COACH", None)

        store.add_refresh_token("expired-jti", "u1", _past(minutes=5), _past(minutes=10))
        store.add_refresh_token("active-jti", "u1", _future(), datetime.now(UTC))

        store.cleanup_expired()

        assert store.is_refresh_token_active("active-jti") is True
        # The expired token row is deleted; lookup returns None → not active
        assert store.is_refresh_token_active("expired-jti") is False


# ---------------------------------------------------------------------------
# Token trim (MAX_ACTIVE_REFRESH_TOKENS ceiling)
# ---------------------------------------------------------------------------

class TestAuthStoreTokenTrim:
    def test_trim_revokes_oldest_when_ceiling_exceeded(self) -> None:
        """Adding MAX+1 tokens must revoke the oldest one."""
        store = _make_store()
        store.upsert_user("u1", "alice", hash_password("p"), "COACH", None)
        base_issued = datetime.now(UTC)

        # Add MAX_ACTIVE_REFRESH_TOKENS tokens (oldest first)
        jtis = [f"jti-{i}" for i in range(MAX_ACTIVE_REFRESH_TOKENS)]
        for i, jti in enumerate(jtis):
            issued = base_issued + timedelta(seconds=i)
            store.add_refresh_token(jti, "u1", _future(), issued)

        # All are active
        for jti in jtis:
            assert store.is_refresh_token_active(jti), f"{jti} should be active"

        # Add one more — must evict the oldest (jti-0)
        store.add_refresh_token("jti-new", "u1", _future(), base_issued + timedelta(seconds=100))
        assert store.is_refresh_token_active("jti-new") is True
        assert store.is_refresh_token_active("jti-0") is False


# ---------------------------------------------------------------------------
# Persistence across DB instances
# ---------------------------------------------------------------------------

class TestAuthStorePersistence:
    def test_user_survives_db_close_and_reopen(self, tmp_path: Path) -> None:
        """Users must be readable from a freshly opened DB (real on-disk persistence)."""
        store1 = _make_store(tmp_path)
        store1.upsert_user("u1", "alice", hash_password("secret"), "COACH", None)
        store1._db.close()

        store2 = _make_store(tmp_path)
        user = store2.get_user("u1")
        assert user is not None
        assert user.username == "alice"
        store2._db.close()

    def test_token_survives_db_close_and_reopen(self, tmp_path: Path) -> None:
        """Active tokens must be readable from a freshly opened DB."""
        store1 = _make_store(tmp_path)
        store1.upsert_user("u1", "alice", hash_password("p"), "COACH", None)
        store1.add_refresh_token("jti-1", "u1", _future(), datetime.now(UTC))
        store1._db.close()

        store2 = _make_store(tmp_path)
        assert store2.is_refresh_token_active("jti-1") is True
        store2._db.close()

    def test_revocation_survives_db_close_and_reopen(self, tmp_path: Path) -> None:
        """A revoked token must remain revoked after DB reopen."""
        store1 = _make_store(tmp_path)
        store1.upsert_user("u1", "alice", hash_password("p"), "COACH", None)
        store1.add_refresh_token("jti-1", "u1", _future(), datetime.now(UTC))
        store1.revoke_refresh_token("jti-1")
        store1._db.close()

        store2 = _make_store(tmp_path)
        assert store2.is_refresh_token_active("jti-1") is False
        store2._db.close()

    def test_lockout_survives_db_close_and_reopen(self, tmp_path: Path) -> None:
        """S3 / F5.2: A locked-out account must remain locked after DB reopen.

        Verifies that login lockout state is persisted to disk and restored
        when a new AuthStore is created from the same on-disk DB — i.e. a
        container restart cannot reset lockout state.
        """
        store1 = _make_store(tmp_path)
        store1.upsert_user("u1", "alice", hash_password("p"), "COACH", None)
        # Exhaust the allowed attempts to trigger lockout.
        for _ in range(5):
            store1.record_failed_attempt("alice")
        assert store1.is_locked_out("alice"), "precondition: account must be locked"
        store1._db.close()

        store2 = _make_store(tmp_path)
        assert store2.is_locked_out("alice"), (
            "Lockout state lost after DB reopen — container restart bypasses "
            "brute-force protection (F5.2 / S3)"
        )
        store2._db.close()


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

class TestAuthStoreTTLInvariant:
    """S3 / F5.3: Token TTL boundary — access must expire before refresh."""

    def test_access_token_ttl_shorter_than_refresh_token_ttl(self) -> None:
        """ACCESS_TOKEN_TTL < REFRESH_TOKEN_TTL must always hold.

        If this invariant is violated, token rotation breaks: a client
        could hold a valid refresh token but receive an access token that
        outlives it, defeating revocation.
        """
        from titan.api.auth import ACCESS_TOKEN_TTL, REFRESH_TOKEN_TTL

        assert ACCESS_TOKEN_TTL < REFRESH_TOKEN_TTL, (
            f"ACCESS_TOKEN_TTL ({ACCESS_TOKEN_TTL}) must be strictly less than "
            f"REFRESH_TOKEN_TTL ({REFRESH_TOKEN_TTL}). "
            "Inverting this breaks token rotation and revocation guarantees."
        )


class TestAuthStoreBackwardCompat:
    def test_authstore_no_args_creates_in_memory_db(self) -> None:
        """AuthStore() without arguments must still work (in-memory SQLite)."""
        store = AuthStore()
        store.upsert_user("u1", "alice", hash_password("p"), "COACH", None)
        assert store.get_user("u1") is not None

    def test_schema_version_is_twelve(self, tmp_path: Path) -> None:
        """After migration v20 (biological_sex/menstrual_tracking addition), PRAGMA user_version must equal 20."""
        db = DatabaseManager(db_name="test_auth.db", db_dir=tmp_path)
        version = db.conn.cursor().execute("PRAGMA user_version").fetchone()[0]
        assert version == 22
        db.close()
