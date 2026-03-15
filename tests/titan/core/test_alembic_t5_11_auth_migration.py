"""T5-11 tests for auth tables migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def _make_config(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _column_metadata(db_path: Path, table_name: str) -> list[tuple]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(f"PRAGMA table_info({table_name})").fetchall()


def _table_exists(db_path: Path, table_name: str) -> bool:
    with sqlite3.connect(db_path) as connection:
        query = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
        return connection.execute(query, (table_name,)).fetchone() is not None


def test_auth_migration_upgrade_creates_auth_tables_with_expected_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "t5_11_upgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")

    assert _table_exists(db_path, "auth_users")
    assert _table_exists(db_path, "auth_tokens")

    user_columns = {row[1]: row for row in _column_metadata(db_path, "auth_users")}
    assert set(user_columns) == {
        "id",
        "username",
        "password_hash",
        "role",
        "athlete_id",
        "created_at",
        "is_active",
    }
    assert user_columns["id"][3] == 1
    assert user_columns["username"][3] == 1
    assert user_columns["password_hash"][3] == 1
    assert user_columns["role"][3] == 1
    assert user_columns["athlete_id"][3] == 0
    assert user_columns["created_at"][3] == 1

    token_columns = {row[1]: row for row in _column_metadata(db_path, "auth_tokens")}
    assert set(token_columns) == {"id", "user_id", "issued_at", "expires_at", "revoked"}
    assert token_columns["id"][3] == 1
    assert token_columns["user_id"][3] == 1
    assert token_columns["issued_at"][3] == 1
    assert token_columns["expires_at"][3] == 1


def test_auth_migration_downgrade_removes_auth_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "t5_11_downgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "20260315_05")

    assert not _table_exists(db_path, "auth_tokens")
    assert not _table_exists(db_path, "auth_users")
