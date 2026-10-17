"""Tests for Opus Phase 20 security/hygiene fixes (TD-SEC-02, TD-SEC-03)."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_login_lockout_persists_restart(tmp_path) -> None:
    """Lockout written to a file DB must survive a new DatabaseManager instance."""
    from titan.core.database import DatabaseManager

    db_file = str(tmp_path / "test.db")
    db = DatabaseManager(db_file)
    for _ in range(5):
        db.record_failed_login("testuser", 900, 5)
    assert db.is_login_locked_out("testuser")

    # New DatabaseManager on the same file — simulates process restart.
    db2 = DatabaseManager(db_file)
    assert db2.is_login_locked_out("testuser"), "Lockout must survive restart"


@pytest.mark.integration
def test_clear_lockout_works() -> None:
    """clear_login_lockout resets the account so it is no longer locked."""
    from titan.core.database import DatabaseManager

    db = DatabaseManager(":memory:")
    for _ in range(5):
        db.record_failed_login("u", 900, 5)
    assert db.is_login_locked_out("u")
    db.clear_login_lockout("u")
    assert not db.is_login_locked_out("u")


@pytest.mark.integration
def test_security_headers_present(jwt_keys) -> None:  # noqa: ARG001
    """All required security headers must appear on every API response."""
    from fastapi.testclient import TestClient

    from titan.api.main import create_app

    client = TestClient(create_app())
    r = client.get("/health")
    assert "X-Content-Type-Options" in r.headers
    assert "X-Frame-Options" in r.headers
    assert "Content-Security-Policy" in r.headers


@pytest.mark.integration
def test_schema_version_incremented() -> None:
    """PRAGMA user_version must equal SCHEMA_VERSION == 33 after migration."""
    from titan.core.database import DatabaseManager

    db = DatabaseManager(":memory:")
    cursor = db.conn.cursor()
    cursor.execute("PRAGMA user_version")
    assert cursor.fetchone()[0] == 33
