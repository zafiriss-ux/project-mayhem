"""Tests for T5-115 (data_source column) and T5-116 (/manual_entry command)."""

import sqlite3

import pytest

from titan.core.database import DatabaseManager
from titan.integrations.telegram_bot import TitanTelegramBot


@pytest.fixture
def db(tmp_path):
    d = DatabaseManager(db_name="test_manual_entry.db", db_dir=tmp_path)
    yield d
    d.close()


@pytest.fixture
def bot(db):
    return TitanTelegramBot(bot_token="", chat_id="12345", db=db)


def _fetch_row(db, date: str) -> dict | None:
    with db._lock:
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM daily_metrics WHERE date = ?", (date,))
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row, strict=True))


# ── Test 1 ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_manual_entry_hrv_only(bot, db, monkeypatch):
    fixed_date = "2026-05-03"
    monkeypatch.setattr(
        "titan.integrations.telegram_bot.datetime",
        type("_DT", (), {"now": staticmethod(lambda tz=None: type("_d", (), {"strftime": lambda self, fmt: fixed_date})())}),
    )
    reply = bot.handle_manual_entry_text("HRV=65")
    assert "✅" in reply
    assert "HRV=65" in reply
    row = _fetch_row(db, fixed_date)
    assert row is not None
    assert row["hrv_rmssd"] == 65.0
    assert row["data_source"] == "manual_entry"


# ── Test 2 ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_manual_entry_full_payload(bot, db, monkeypatch):
    fixed_date = "2026-05-03"
    monkeypatch.setattr(
        "titan.integrations.telegram_bot.datetime",
        type("_DT", (), {"now": staticmethod(lambda tz=None: type("_d", (), {"strftime": lambda self, fmt: fixed_date})())}),
    )
    reply = bot.handle_manual_entry_text("HRV=65 RHR=52 SLEEP=7.5 FATIGUE=3 WEIGHT=75.0")
    assert "✅" in reply
    row = _fetch_row(db, fixed_date)
    assert row is not None
    assert row["hrv_rmssd"] == 65.0
    assert row["resting_hr"] == 52
    assert row["sleep_hours"] == 7.5
    assert row["fatigue_level"] == 3
    assert row["weight_kg"] == 75.0
    assert row["data_source"] == "manual_entry"


# ── Test 3 ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_manual_entry_garmin_sync_preserves_manual_source(db, tmp_path):
    """Garmin re-sync (garmin_api) must NOT overwrite a manual_entry data_source."""
    date = "2026-05-03"
    # First: manual entry sets the row with data_source='manual_entry'
    db.save_daily_metric(date=date, hrv=65.0, data_source="manual_entry")
    row_after_manual = _fetch_row(db, date)
    assert row_after_manual["data_source"] == "manual_entry"

    # Second: Garmin sync path calls save_daily_metric with default data_source='garmin_api'
    db.save_daily_metric(date=date, hrv=70.0, data_source="garmin_api")
    row_after_garmin = _fetch_row(db, date)
    # data_source must remain 'manual_entry' — provenance preserved
    assert row_after_garmin["data_source"] == "manual_entry"
    # hrv_rmssd is overwritten by garmin (not NULL), as per T5-66 UPSERT semantics
    assert row_after_garmin["hrv_rmssd"] == 70.0


# ── Test 4 ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_manual_entry_invalid_hrv_out_of_range(bot, db, monkeypatch):
    fixed_date = "2026-05-03"
    monkeypatch.setattr(
        "titan.integrations.telegram_bot.datetime",
        type("_DT", (), {"now": staticmethod(lambda tz=None: type("_d", (), {"strftime": lambda self, fmt: fixed_date})())}),
    )
    reply = bot.handle_manual_entry_text("HRV=250")
    assert "❌" in reply
    assert "HRV" in reply
    assert _fetch_row(db, fixed_date) is None


# ── Test 5 ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_manual_entry_invalid_fatigue_out_of_range(bot, db, monkeypatch):
    fixed_date = "2026-05-03"
    monkeypatch.setattr(
        "titan.integrations.telegram_bot.datetime",
        type("_DT", (), {"now": staticmethod(lambda tz=None: type("_d", (), {"strftime": lambda self, fmt: fixed_date})())}),
    )
    reply = bot.handle_manual_entry_text("FATIGUE=11")
    assert "❌" in reply
    assert "FATIGUE" in reply
    assert _fetch_row(db, fixed_date) is None


# ── Test 6 ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_manual_entry_malformed_input(bot):
    reply = bot.handle_manual_entry_text("notakey=5")
    assert "Usage:" in reply


# ── Test 7 ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_manual_entry_empty_command(bot):
    reply = bot.handle_manual_entry_text("")
    assert "Usage:" in reply


# ── Test 8 ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_data_source_column_exists_in_schema(tmp_path):
    db = DatabaseManager(db_name="test_schema_check.db", db_dir=tmp_path)
    cursor = db.conn.cursor()
    cursor.execute("PRAGMA table_info(daily_metrics)")
    columns = {row[1] for row in cursor.fetchall()}
    db.close()
    assert "data_source" in columns
