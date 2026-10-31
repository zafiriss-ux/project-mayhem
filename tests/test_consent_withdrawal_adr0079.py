"""SP-03 part B (ADR-0079): a consent withdrawal (/stop) always takes effect.

The revocation and its audit row go in one transaction. If that fails, the withdrawal goes
to a durable pending-audit queue beside the database, already counts as no consent, and the
worker writes it to the database later without writing the audit row twice. Only when
neither the database nor the queue can be written is the /stop refused. Synthetic data only.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from titan.core.athlete import CONSENT_TEXT_VERSION, AthleteNotReady, ConsentWithdrawalPending
from titan.core.database import DatabaseManager
from titan.core.repositories.access import PendingAuditQueue, PendingAuditUnreadable
from titan.integrations.telegram_bot import _STOP_NOT_RECORDED_REPLY, TitanTelegramBot

_A, _B = "a-0000000a", "a-0000000b"
OWNER_CHAT, CHAT_A = 1000, 987654321
_STOPPED = "⏹ Stopped."


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    seen: list[tuple] = []
    monkeypatch.setattr(
        "titan.observability.metrics.get_metrics",
        lambda: SimpleNamespace(
            counter=lambda name, *a, labels=None, **k: seen.append(("counter", name, labels)),
            gauge=lambda name, value, *a, **k: seen.append(("gauge", name, value)),
        ),
    )
    return seen


@pytest.fixture
def db(tmp_path: Path, counted):
    manager = DatabaseManager(db_dir=tmp_path)
    for athlete in (_A, _B):
        manager.conn.execute(
            "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')", (athlete, athlete)
        )
    manager.conn.commit()
    yesterday = datetime.now(UTC) - timedelta(days=1)
    for athlete in (_A, _B):
        manager.grant_consent(athlete, CONSENT_TEXT_VERSION, now=yesterday)
    yield manager
    manager.close()


@pytest.fixture
def bot(db, monkeypatch: pytest.MonkeyPatch):
    owner_bot = TitanTelegramBot(bot_token="", chat_id=OWNER_CHAT, db=db)
    owner_bot.sent = []
    monkeypatch.setattr(
        owner_bot, "send_message", lambda text, parse_mode="Markdown": owner_bot.sent.append(text) or True
    )
    return owner_bot


def _break(db: DatabaseManager, table: str, event: str = "INSERT") -> None:
    """Make writes to one table fail, the way a damaged table would (SP-03 scenario)."""
    db.conn.execute(
        f"CREATE TRIGGER broken_{table}_{event.lower()} BEFORE {event} ON {table} "  # nosec B608 - fixed test names
        "BEGIN SELECT RAISE(ABORT, 'table damaged'); END"
    )
    db.conn.commit()


def _mend(db: DatabaseManager) -> None:
    for (name,) in db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'broken_%'"):
        db.conn.execute(f"DROP TRIGGER {name}")  # nosec B608 - names read from sqlite_master above
    db.conn.commit()


def _stop_audit_rows(db: DatabaseManager, athlete_id: str = _A) -> list[dict]:
    return [r for r in db.get_coach_audit_log() if r["athlete_id"] == athlete_id and r["action_type"] == "TELEGRAM_STOP"]


def _open_consents(db: DatabaseManager, athlete_id: str = _A) -> int:
    return db.conn.execute(
        "SELECT COUNT(*) FROM consent_log WHERE athlete_id = ? AND revoked_at IS NULL", (athlete_id,)
    ).fetchone()[0]


def _queue(db: DatabaseManager) -> PendingAuditQueue:
    queue = db.pending_audit
    assert queue is not None
    return queue


# ── The finding: a /stop while only the audit table fails ─────────────────────


@pytest.mark.integration
def test_defect_stop_refused_when_audit_write_fails(db, bot) -> None:
    # SP-03 (the name of the audit's defect test): before ADR-0079 this /stop was refused and
    # coaching went on. Now the withdrawal takes effect while only the audit table fails.
    _break(db, "coach_audit_log")

    reply = bot.handle_athlete_stop(CHAT_A, _A)

    assert reply.startswith(_STOPPED)
    assert not db.has_current_consent(_A)
    assert db.has_current_consent(_B)
    assert _open_consents(db) == 0  # the revocation alone reached the database
    (item,) = _queue(db).pending()
    assert item["athlete_id"] == _A and item["action"] == "TELEGRAM_STOP"
    assert str(CHAT_A) not in json.dumps(item)  # no chat id in the queue (ADR-0067 D2.8)
    (alert,) = bot.sent
    assert _A in alert and "pending-audit queue" in alert and str(CHAT_A) not in alert


@pytest.mark.integration
def test_a_normal_stop_writes_both_rows_and_queues_nothing(db, bot) -> None:
    assert bot.handle_athlete_stop(CHAT_A, _A).startswith(_STOPPED)

    assert _open_consents(db) == 0
    (row,) = _stop_audit_rows(db)
    assert row["coach_id"] == f"telegram:{CHAT_A}"
    assert _queue(db).pending() == []
    assert bot.sent == []


@pytest.mark.integration
def test_revocation_and_audit_row_are_one_transaction(db) -> None:
    _break(db, "coach_audit_log")
    with pytest.raises(sqlite3.DatabaseError):
        db._access.revoke_consent_with_audit(
            _A, revoked_at=datetime.now(UTC).isoformat(), coach_id="telegram:1", action_type="TELEGRAM_STOP",
            resource="telegram",
        )
    assert _open_consents(db) == 1  # rolled back with the failed audit row


# ── Neither the database nor the queue ────────────────────────────────────────


@pytest.mark.integration
def test_stop_is_refused_only_when_the_queue_cannot_be_written_either(db, bot, monkeypatch) -> None:
    _break(db, "coach_audit_log")

    def _disk_full(self, item):  # noqa: ANN001, ANN202
        raise OSError("No space left on device")

    monkeypatch.setattr(PendingAuditQueue, "append", _disk_full)

    assert bot.handle_athlete_stop(CHAT_A, _A) == _STOP_NOT_RECORDED_REPLY
    assert db.has_current_consent(_A)
    (alert,) = bot.sent
    assert _A in alert and "still active" in alert and str(CHAT_A) not in alert


@pytest.mark.integration
def test_an_in_memory_database_has_no_queue_so_the_stop_is_refused(counted, monkeypatch) -> None:
    memory = DatabaseManager(db_name=":memory:")
    memory.conn.execute("INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')", (_A, _A))
    memory.conn.commit()
    memory.grant_consent(_A, CONSENT_TEXT_VERSION, now=datetime.now(UTC) - timedelta(days=1))
    _break(memory, "coach_audit_log")
    owner_bot = TitanTelegramBot(bot_token="", chat_id=OWNER_CHAT, db=memory)
    monkeypatch.setattr(owner_bot, "send_message", lambda text, parse_mode="Markdown": True)

    assert memory.pending_audit is None
    assert owner_bot.handle_athlete_stop(CHAT_A, _A) == _STOP_NOT_RECORDED_REPLY
    assert memory.has_current_consent(_A)
    memory.close()


@pytest.mark.integration
def test_a_failed_owner_alert_still_answers_the_athlete(db, bot, monkeypatch) -> None:
    _break(db, "coach_audit_log")

    def _raise(text, parse_mode="Markdown"):  # noqa: ANN001, ANN202
        raise RuntimeError("telegram down")

    monkeypatch.setattr(bot, "send_message", _raise)

    assert bot.handle_athlete_stop(CHAT_A, _A).startswith(_STOPPED)


# ── The pending withdrawal already counts ─────────────────────────────────────


@pytest.mark.integration
def test_a_queued_withdrawal_counts_even_when_the_database_kept_the_consent(db, bot) -> None:
    _break(db, "coach_audit_log")
    _break(db, "consent_log", "UPDATE")

    assert bot.handle_athlete_stop(CHAT_A, _A).startswith(_STOPPED)

    assert _open_consents(db) == 1  # the database could not take the revocation
    assert not db.has_current_consent(_A)  # the queue already withdraws it
    with pytest.raises(AthleteNotReady):
        from titan.worker import _require_consent

        _require_consent(db, _A)


@pytest.mark.integration
def test_agree_is_refused_while_the_athletes_stop_is_queued(db, bot) -> None:
    _break(db, "coach_audit_log")
    bot.handle_athlete_stop(CHAT_A, _A)
    _mend(db)

    with pytest.raises(ConsentWithdrawalPending):
        db.grant_consent(_A, CONSENT_TEXT_VERSION)
    reply = bot.handle_athlete_agree(CHAT_A, _A, CONSENT_TEXT_VERSION)
    assert reply.startswith("⏳")
    assert not db.has_current_consent(_A)
    assert db.grant_consent(_B, CONSENT_TEXT_VERSION) is False  # another athlete is not held up


# ── The drain ─────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_the_drain_writes_the_queued_withdrawal_once_with_its_original_time(db, bot, counted) -> None:
    _break(db, "coach_audit_log")
    _break(db, "consent_log", "UPDATE")
    bot.handle_athlete_stop(CHAT_A, _A)
    (item,) = _queue(db).pending()
    _mend(db)

    assert db.drain_pending_audit() == 0
    assert db.drain_pending_audit() == 0  # a second drain writes nothing more

    assert _open_consents(db) == 0
    (row,) = _stop_audit_rows(db)
    assert row["action_detail"].startswith(f"queue_id:{item['id']}")
    original = datetime.fromisoformat(item["revoked_at"]).strftime("%Y-%m-%d %H:%M:%S")
    assert row["performed_at"] == original
    assert _queue(db).pending() == []
    assert ("gauge", "pending_audit_queue_depth", 0) in counted


@pytest.mark.integration
def test_a_repeated_drain_after_a_crash_does_not_duplicate_the_audit_row(db) -> None:
    item = {"id": "f" * 32, "athlete_id": _A, "revoked_at": datetime.now(UTC).isoformat(), "action": "TELEGRAM_STOP"}
    _queue(db).append(item)
    # The crash: the row was committed but the "done" line never written.
    db._access.apply_queued_withdrawal(item, coach_id="telegram:pending-audit", resource="telegram")

    assert db.drain_pending_audit() == 0
    assert len(_stop_audit_rows(db)) == 1


@pytest.mark.integration
def test_the_drain_revokes_only_consents_given_at_or_before_the_stop(db) -> None:
    stop_time = datetime.now(UTC) - timedelta(hours=1)
    db.conn.execute("UPDATE consent_log SET revoked_at = ? WHERE athlete_id = ?", (stop_time.isoformat(), _A))
    later = (stop_time + timedelta(minutes=30)).isoformat()
    db.conn.execute(
        "INSERT INTO consent_log (athlete_id, consent_type, text_version, granted_at, channel)"
        " VALUES (?, 'coaching', ?, ?, 'telegram')",
        (_A, CONSENT_TEXT_VERSION, later),
    )
    db.conn.commit()
    _queue(db).append(
        {"id": "e" * 32, "athlete_id": _A, "revoked_at": stop_time.isoformat(), "action": "TELEGRAM_STOP"}
    )

    assert db.drain_pending_audit() == 0
    assert _open_consents(db) == 1  # the consent given after the /stop stays


@pytest.mark.integration
def test_a_failing_drain_keeps_the_entry_and_counts_the_failure(db, counted) -> None:
    _queue(db).append({"id": "d" * 32, "athlete_id": _A, "revoked_at": datetime.now(UTC).isoformat(), "action": "TELEGRAM_STOP"})
    _break(db, "coach_audit_log")

    assert db.drain_pending_audit() == 1
    assert len(_queue(db).pending()) == 1
    assert ("counter", "audit_write_failure", {"surface": "pending_audit"}) in counted
    assert ("gauge", "pending_audit_queue_depth", 1) in counted


# ── The file itself ───────────────────────────────────────────────────────────


@pytest.mark.integration
def test_a_missing_file_is_an_empty_queue(db) -> None:
    assert not _queue(db).path.exists()
    assert _queue(db).pending() == []
    assert db.has_current_consent(_A)


@pytest.mark.integration
def test_a_torn_last_line_is_ignored_and_cut_before_the_next_append(db) -> None:
    queue = _queue(db)
    queue.path.write_bytes(b'{"id": "torn", "athlete_id": "a-0000000b", "rev')

    assert queue.pending() == []
    assert db.has_current_consent(_B)  # an unconfirmed /stop withdraws nothing

    queue.append({"id": "c" * 32, "athlete_id": _A, "revoked_at": datetime.now(UTC).isoformat(), "action": "TELEGRAM_STOP"})

    assert [item["athlete_id"] for item in queue.pending()] == [_A]
    assert queue.path.read_bytes().count(b"\n") == 1
    assert b"torn" not in queue.path.read_bytes()


@pytest.mark.integration
def test_an_unreadable_line_withdraws_consent_from_every_athlete_but_the_owner(db) -> None:
    from titan.worker import _readiness_problem

    queue = _queue(db)
    queue.path.write_bytes(b"not json at all\n")

    with pytest.raises(PendingAuditUnreadable):
        db.has_current_consent(_B)
    assert db.has_current_consent("owner")
    assert _readiness_problem(db, _B) == "consent: pending-audit queue unreadable"
    with pytest.raises(PendingAuditUnreadable):
        db.drain_pending_audit()
    assert queue.path.read_bytes() == b"not json at all\n"  # never dropped automatically
    with pytest.raises(PendingAuditUnreadable):
        db.grant_consent(_B, CONSENT_TEXT_VERSION)


@pytest.mark.integration
def test_the_queue_file_is_private(db) -> None:
    _queue(db).append({"id": "b" * 32, "athlete_id": _A, "revoked_at": datetime.now(UTC).isoformat(), "action": "TELEGRAM_STOP"})

    assert _queue(db).path.stat().st_mode & 0o077 == 0


# ── The athlete's life cycle ──────────────────────────────────────────────────


@pytest.mark.integration
def test_erasing_an_athlete_drops_their_queued_withdrawals(db, tmp_path, monkeypatch) -> None:
    from titan.core import athlete_lifecycle

    monkeypatch.setenv(athlete_lifecycle.DELETION_RECORD_ENV, str(tmp_path / "deletions.jsonl"))
    now = datetime.now(UTC).isoformat()
    _queue(db).append({"id": "a" * 32, "athlete_id": _A, "revoked_at": now, "action": "TELEGRAM_STOP"})
    _queue(db).append({"id": "9" * 32, "athlete_id": _B, "revoked_at": now, "action": "TELEGRAM_STOP"})

    athlete_lifecycle.delete_athlete(db, _A)

    assert [item["athlete_id"] for item in _queue(db).pending()] == [_B]


@pytest.mark.integration
def test_the_drain_writes_nothing_for_an_athlete_who_no_longer_exists(db) -> None:
    db.conn.execute("DELETE FROM consent_log WHERE athlete_id = ?", (_A,))
    db.conn.execute("DELETE FROM athletes WHERE athlete_id = ?", (_A,))
    db.conn.commit()
    _queue(db).append({"id": "8" * 32, "athlete_id": _A, "revoked_at": datetime.now(UTC).isoformat(), "action": "TELEGRAM_STOP"})

    assert db.drain_pending_audit() == 0
    assert _stop_audit_rows(db) == []


# ── The worker ────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_the_worker_drains_and_reminds_the_owner_once_a_day(db, monkeypatch) -> None:
    import titan.integrations.telegram_bot as telegram_bot
    from titan import worker

    sent: list[str] = []
    monkeypatch.setattr(telegram_bot.TitanTelegramBot, "send_message", lambda self, text, parse_mode="": sent.append(text) or True)
    _queue(db).append({"id": "7" * 32, "athlete_id": _A, "revoked_at": datetime.now(UTC).isoformat(), "action": "TELEGRAM_STOP"})
    _break(db, "coach_audit_log")

    worker._drain_pending_audit(db)
    worker._drain_pending_audit(db)

    assert len(sent) == 1 and "1 consent withdrawal" in sent[0]
    _mend(db)
    worker._drain_pending_audit(db)
    assert _queue(db).pending() == []
    assert len(_stop_audit_rows(db)) == 1


# ── Backup ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_the_daily_backup_keeps_the_queue_beside_the_database(db, tmp_path) -> None:
    _queue(db).append({"id": "6" * 32, "athlete_id": _A, "revoked_at": datetime.now(UTC).isoformat(), "action": "TELEGRAM_STOP"})
    backups = tmp_path / "backups"

    dest = db.backup_database(backup_dir=backups)

    assert dest is not None
    copy = dest.with_name(dest.stem + ".pending_audit.jsonl")
    assert copy.read_bytes() == _queue(db).path.read_bytes()
    assert copy.stat().st_mode & 0o077 == 0


@pytest.mark.integration
def test_the_shell_backup_copies_the_queue(db, tmp_path) -> None:
    import subprocess  # nosec B404 - runs the repo's own script on synthetic data

    _queue(db).append({"id": "5" * 32, "athlete_id": _A, "revoked_at": datetime.now(UTC).isoformat(), "action": "TELEGRAM_STOP"})
    repo = Path(__file__).resolve().parents[1]

    subprocess.run(["bash", str(repo / "scripts" / "backup.sh"), str(db.db_path.parent)], check=True, cwd=repo, capture_output=True)  # nosec B603 B607

    copies = list((db.db_path.parent / "backups").glob("pending_audit.jsonl.*"))
    assert len(copies) == 1 and copies[0].read_bytes() == _queue(db).path.read_bytes()


# ── Review of the implementation (Opus) ───────────────────────────────────────


@pytest.mark.integration
def test_the_owner_hears_once_when_the_queue_fills_not_on_every_stop(db, bot) -> None:
    _break(db, "coach_audit_log")

    bot.handle_athlete_stop(CHAT_A, _A)
    bot.handle_athlete_stop(CHAT_A + 1, _B)

    assert len(bot.sent) == 1
    assert len(_queue(db).pending()) == 2


@pytest.mark.integration
def test_the_queued_time_is_stamped_under_the_lock(db) -> None:
    item = {"id": "4" * 32, "athlete_id": _A, "action": "TELEGRAM_STOP"}
    before = datetime.now(UTC)

    _queue(db).append(item)

    assert before <= datetime.fromisoformat(item["revoked_at"]) <= datetime.now(UTC)
    assert _queue(db).pending()[0]["revoked_at"] == item["revoked_at"]


@pytest.mark.integration
@pytest.mark.parametrize("granted", ["2026-01-01 08:00:00", "not a time"])
def test_an_old_or_unreadable_grant_time_does_not_block_the_drain(db, granted) -> None:
    db.conn.execute("UPDATE consent_log SET granted_at = ? WHERE athlete_id = ?", (granted, _A))
    db.conn.commit()
    _queue(db).append({"id": "3" * 32, "athlete_id": _A, "revoked_at": datetime.now(UTC).isoformat(), "action": "TELEGRAM_STOP"})

    assert db.drain_pending_audit() == 0
    assert _open_consents(db) == 0  # revoked: an unreadable time never keeps a consent


@pytest.mark.integration
def test_agree_waits_for_a_stop_that_holds_the_queue_lock(db) -> None:
    import threading

    queue = _queue(db)
    result: list[object] = []
    db.conn.execute("UPDATE consent_log SET revoked_at = ? WHERE athlete_id = ?", (datetime.now(UTC).isoformat(), _B))
    db.conn.commit()

    with queue.locked(exclusive=True):
        worker = threading.Thread(target=lambda: result.append(_try_grant(db)))
        worker.start()
        worker.join(timeout=0.3)
        assert worker.is_alive()  # blocked behind the /stop
        queue.append_locked({"id": "2" * 32, "athlete_id": _B, "revoked_at": datetime.now(UTC).isoformat(), "action": "TELEGRAM_STOP"})
    worker.join(timeout=5)

    assert result and isinstance(result[0], ConsentWithdrawalPending)


def _try_grant(db: DatabaseManager) -> object:
    try:
        return db.grant_consent(_B, CONSENT_TEXT_VERSION)
    except Exception as exc:  # noqa: BLE001 - the test inspects it
        return exc


@pytest.mark.integration
def test_a_queue_that_cannot_be_read_from_disk_is_no_consent(db, monkeypatch) -> None:
    from titan.worker import _readiness_problem

    def _eio(self):  # noqa: ANN001, ANN202
        raise OSError("Input/output error")

    monkeypatch.setattr(PendingAuditQueue, "read_locked", _eio)

    assert _readiness_problem(db, _A) == "consent: pending-audit queue unreadable"
    assert db.has_current_consent("owner")


@pytest.mark.integration
def test_a_failed_drain_attempt_is_counted_and_named_in_the_reminder(db, counted, monkeypatch) -> None:
    import titan.integrations.telegram_bot as telegram_bot
    from titan import worker

    sent: list[str] = []
    monkeypatch.setattr(telegram_bot.TitanTelegramBot, "send_message", lambda self, text, parse_mode="": sent.append(text) or True)
    _queue(db).path.write_bytes(b"not json\n")

    worker._drain_pending_audit(db)

    assert ("counter", "audit_write_failure", {"surface": "pending_audit"}) in counted
    assert len(sent) == 1 and "cannot be read" in sent[0]
