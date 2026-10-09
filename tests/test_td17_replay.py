"""
TD-17: Telegram override replay protection tests.

Verifies the nonce-based one-time-use mechanism that prevents duplicate
override confirmations from network retries or multi-tap. Nonces live in
telegram_override_nonces (ADR-0060 D2).
"""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from titan.core.database import DatabaseManager
from titan.integrations.telegram_bot import (
    _consume_override_nonce,
    _create_override_nonce,
)


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.unit
def test_nonce_valid_first_use(db):
    nonce = _create_override_nonce(db, "dec-1", "owner")
    result = _consume_override_nonce(db, nonce)
    assert result == "dec-1"


@pytest.mark.unit
def test_nonce_invalid_second_use(db):
    nonce = _create_override_nonce(db, "dec-1", "owner")
    _consume_override_nonce(db, nonce)  # first use
    result = _consume_override_nonce(db, nonce)
    assert result is None  # replay blocked


@pytest.mark.unit
def test_nonce_expired(db):
    nonce = _create_override_nonce(db, "dec-1", "owner")
    # Manually expire it
    past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat(timespec="microseconds")
    db.conn.execute("UPDATE telegram_override_nonces SET expires_at = ? WHERE nonce = ?", (past, nonce))
    db.conn.commit()
    result = _consume_override_nonce(db, nonce)
    assert result is None


@pytest.mark.unit
def test_nonce_invalid_unknown(db):
    result = _consume_override_nonce(db, "not-a-real-nonce")
    assert result is None


@pytest.mark.unit
def test_different_decisions_different_nonces(db):
    n1 = _create_override_nonce(db, "dec-1", "owner")
    n2 = _create_override_nonce(db, "dec-2", "owner")
    assert n1 != n2
    assert _consume_override_nonce(db, n1) == "dec-1"
    assert _consume_override_nonce(db, n2) == "dec-2"


@pytest.mark.unit
def test_nonce_for_another_command_is_refused(db):
    now = datetime.now(UTC)
    db.issue_override_nonce(
        nonce="n-sync", command_type="sync", athlete_id="owner", decision_id="dec-1",
        issued_at=now, expires_at=now + timedelta(minutes=5),
    )
    assert _consume_override_nonce(db, "n-sync") is None


@pytest.mark.unit
def test_no_database_issues_and_accepts_nothing(caplog):
    with caplog.at_level("CRITICAL"):
        assert _create_override_nonce(None, "dec-1", "owner") is None
        assert _consume_override_nonce(None, "anything") is None
    assert [r.getMessage() for r in caplog.records] == ["telegram_override_nonce_unavailable"] * 2


@pytest.mark.unit
def test_database_error_fails_closed(caplog):
    class _BrokenDb:
        def issue_override_nonce(self, **_kwargs):
            raise sqlite3.OperationalError("database is locked")

        def consume_override_nonce(self, **_kwargs):
            raise sqlite3.OperationalError("database is locked")

    with caplog.at_level("CRITICAL"):
        assert _create_override_nonce(_BrokenDb(), "dec-1", "owner") is None
        assert _consume_override_nonce(_BrokenDb(), "n-1") is None
    assert [r.getMessage() for r in caplog.records] == ["telegram_override_nonce_unavailable"] * 2
