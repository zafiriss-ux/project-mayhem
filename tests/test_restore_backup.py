"""#1251 (DR-NEW-01): a restore brings back the pending-audit queue with the database.

A /stop whose database write failed lives only in the pending-audit queue (ADR-0079).
Restoring the database alone turns that athlete's consent back on. ``scripts/restore_backup.py``
restores the queue copy too, and the restore drill writes it to the copy and checks that
no stopped athlete has a current consent. Synthetic data only.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import subprocess  # nosec B404 - runs the repo's own script on synthetic data
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from titan.core.athlete import CONSENT_TEXT_VERSION
from titan.core.database import DatabaseManager
from titan.core.repositories.access import PendingAuditQueue

_ROOT = Path(__file__).resolve().parents[1]
_A, _B = "a-0000000a", "a-0000000b"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def live(tmp_path: Path):
    """A data directory whose /stop for athlete A reached only the pending-audit queue."""
    data = tmp_path / "live"
    db = DatabaseManager(db_name="titan_core.db", db_dir=data)
    for athlete in (_A, _B):
        db.conn.execute(
            "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')", (athlete, athlete)
        )
    db.conn.commit()
    yesterday = datetime.now(UTC) - timedelta(days=1)
    for athlete in (_A, _B):
        db.grant_consent(athlete, CONSENT_TEXT_VERSION, now=yesterday)
    db.conn.execute(
        "CREATE TRIGGER broken_consent BEFORE UPDATE ON consent_log BEGIN SELECT RAISE(ABORT, 'damaged'); END"
    )
    db.conn.commit()
    assert db.withdraw_consent(_A, coach_id="telegram:test", action_type="TELEGRAM_STOP") == "queued_first"
    db.conn.execute("DROP TRIGGER broken_consent")
    db.conn.commit()
    assert not db.has_current_consent(_A)
    yield db
    db.close()


def _backup(db: DatabaseManager, tmp_path: Path) -> Path:
    dest = db.backup_database(backup_dir=tmp_path / "backups")
    assert dest is not None
    assert dest.with_name(dest.stem + ".pending_audit.jsonl").exists()
    return dest


def _consent_after_start(data: Path, athlete: str = _A) -> tuple[bool, bool]:
    """Consent of *athlete* in *data* when opened, and after the worker's drain at start."""
    db = DatabaseManager(db_name="titan_core.db", db_dir=data)
    try:
        before = db.has_current_consent(athlete)
        assert db.drain_pending_audit() == 0
        return before, db.has_current_consent(athlete)
    finally:
        db.close()


def test_1251_a_database_only_restore_turns_consent_back_on(live, tmp_path: Path) -> None:
    # The finding, as the old runbook restored: only the database file is copied.
    dest = _backup(live, tmp_path)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    shutil.copyfile(dest, fresh / "titan_core.db")

    assert _consent_after_start(fresh) == (True, True)


def test_1251_the_restore_keeps_the_withdrawal(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    fresh = tmp_path / "fresh"
    fresh.mkdir()

    result = _load("restore_backup").restore(dest, fresh)

    assert result["ok"] is True, result
    assert result["withdrawals_in_backup"] == 1 and result["withdrawals_added"] == 1
    assert _consent_after_start(fresh) == (False, False)
    assert _consent_after_start(fresh, _B) == (True, True)


def test_1251_the_restore_keeps_the_withdrawals_already_waiting(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    data = live.db_path.parent
    live.pending_audit.append({"id": "b" * 32, "athlete_id": _B, "action": "TELEGRAM_STOP"})
    live.close()

    result = _load("restore_backup").restore(dest, data)

    assert result["ok"] is True, result
    assert result["withdrawals_added"] == 0  # A's withdrawal was still waiting in the live queue
    assert {item["athlete_id"] for item in PendingAuditQueue(data).pending()} == {_A, _B}
    assert _consent_after_start(data) == (False, False)
    assert _consent_after_start(data, _B) == (False, False)
    assert (data / "titan_core.db.before-restore").exists()


def test_1251_a_done_marker_in_the_live_queue_does_not_hide_the_withdrawal(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    data = live.db_path.parent
    (item,) = live.pending_audit.pending()
    with live.pending_audit.locked(exclusive=True):
        live.pending_audit.append_locked({"id": item["id"], "done": True})
    live.close()

    result = _load("restore_backup").restore(dest, data)

    assert result["ok"] is True, result
    assert result["withdrawals_added"] == 1
    assert _consent_after_start(data) == (False, False)


def test_1251_an_unreadable_queue_copy_stops_the_restore(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    dest.with_name(dest.stem + ".pending_audit.jsonl").write_text("not json\n")
    fresh = tmp_path / "fresh"
    fresh.mkdir()

    result = _load("restore_backup").restore(dest, fresh)

    assert result["ok"] is False and "PendingAuditUnreadable" in result["error"], result
    assert list(fresh.iterdir()) == []


def test_1251_a_kept_database_is_never_overwritten(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    data = live.db_path.parent
    live.close()
    restore = _load("restore_backup").restore
    assert restore(dest, data)["ok"] is True
    kept = (data / "titan_core.db.before-restore").read_bytes()

    second = restore(dest, data)
    assert second["ok"] is False and "already exists" in second["error"], second

    again = restore(dest, data, again=True)
    assert again["ok"] is True, again
    assert (data / "titan_core.db.before-restore").read_bytes() == kept


def test_1251_a_manual_backup_finds_its_own_queue_copy() -> None:
    queue_copy_for = _load("restore_backup").queue_copy_for

    assert queue_copy_for(Path("/b/titan_core.db.20261006")) == Path("/b/pending_audit.jsonl.20261006")
    assert queue_copy_for(Path("/b/titan_2026-10-06.db")) == Path("/b/titan_2026-10-06.pending_audit.jsonl")


def test_1251_the_command_line_restores_and_reports(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    fresh = tmp_path / "fresh"
    fresh.mkdir()

    run = subprocess.run(  # nosec B603 - the repo's own script on synthetic data
        [sys.executable, str(_ROOT / "scripts" / "restore_backup.py"), str(dest), "--data-dir", str(fresh)],
        capture_output=True, text=True, cwd=_ROOT, check=False,
    )

    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout.strip().splitlines()[-1])["withdrawals_added"] == 1
    assert _consent_after_start(fresh) == (False, False)


def test_1251_the_drill_writes_the_queue_copy_to_the_copy(live, tmp_path: Path) -> None:
    _backup(live, tmp_path)

    result = _load("restore_drill").run_drill(tmp_path / "backups")

    assert result["ok"] is True, result
    assert result["withdrawals"] == 1


def test_1251_the_drill_fails_on_an_unreadable_queue_copy(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    dest.with_name(dest.stem + ".pending_audit.jsonl").write_text("not json\n")

    result = _load("restore_drill").run_drill(tmp_path / "backups")

    assert result["ok"] is False and "PendingAuditUnreadable" in result["error"], result


def test_1251_a_withdrawal_recorded_after_the_backup_is_kept(tmp_path: Path) -> None:
    data = tmp_path / "live"
    db = DatabaseManager(db_name="titan_core.db", db_dir=data)
    db.conn.execute("INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')", (_A, _A))
    db.conn.commit()
    db.grant_consent(_A, CONSENT_TEXT_VERSION, now=datetime.now(UTC) - timedelta(days=1))
    dest = db.backup_database(backup_dir=tmp_path / "backups")
    assert db.withdraw_consent(_A, coach_id="telegram:test", action_type="TELEGRAM_STOP") == "recorded"
    db.close()

    result = _load("restore_backup").restore(dest, data)

    assert result["ok"] is True, result
    assert result["withdrawals_recorded"] == 1 and result["withdrawals_added"] == 1
    assert _consent_after_start(data) == (False, False)


def test_1251_an_unreadable_current_database_stops_the_restore_unless_skipped(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    data = live.db_path.parent
    live.close()
    for side in ("-wal", "-shm"):
        (data / f"titan_core.db{side}").unlink(missing_ok=True)
    (data / "titan_core.db").write_bytes(b"not a database" * 100)
    before = (data / "titan_core.db").read_bytes()
    restore = _load("restore_backup").restore

    refused = restore(dest, data)
    assert refused["ok"] is False and "--skip-live-withdrawals" in refused["error"], refused
    assert (data / "titan_core.db").read_bytes() == before
    assert not (data / "titan_core.db.before-restore").exists()

    skipped = restore(dest, data, skip_live_withdrawals=True)
    assert skipped["ok"] is True and "live_withdrawals_skipped" in skipped, skipped
    assert _consent_after_start(data) == (False, False)
    # #1497: B's consent cannot be checked against the unreadable database, so it is withdrawn too.
    assert _consent_after_start(data, _B) == (False, False)


def test_1251_an_unreadable_live_queue_changes_nothing(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    data = live.db_path.parent
    live.close()
    (data / "pending_audit.jsonl").write_text("not json\n")
    before = (data / "titan_core.db").read_bytes()

    result = _load("restore_backup").restore(dest, data)

    assert result["ok"] is False and "PendingAuditUnreadable" in result["error"], result
    assert (data / "titan_core.db").read_bytes() == before
    assert (data / "pending_audit.jsonl").read_text() == "not json\n"
    assert not (data / "titan_core.db.before-restore").exists()


def test_1251_a_symlinked_queue_copy_is_refused(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    copy = dest.with_name(dest.stem + ".pending_audit.jsonl")
    elsewhere = tmp_path / "elsewhere.jsonl"
    copy.rename(elsewhere)
    copy.symlink_to(elsewhere)
    fresh = tmp_path / "fresh"
    fresh.mkdir()

    result = _load("restore_backup").restore(dest, fresh)

    assert result["ok"] is False and "not a regular file" in result["error"], result
    assert list(fresh.iterdir()) == []


def test_1251_again_refuses_to_drop_a_wal_that_was_not_kept(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    data = live.db_path.parent
    live.close()
    shutil.copyfile(data / "titan_core.db", data / "titan_core.db.before-restore")
    (data / "titan_core.db-wal").write_bytes(b"x")

    result = _load("restore_backup").restore(dest, data, again=True)

    assert result["ok"] is False and "keep it before trying again" in result["error"], result
    assert (data / "titan_core.db-wal").read_bytes() == b"x"


def test_1251_the_restored_and_kept_files_are_owner_only(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    data = live.db_path.parent
    live.close()

    assert _load("restore_backup").restore(dest, data)["ok"] is True

    for name in ("titan_core.db", "titan_core.db.before-restore", "pending_audit.jsonl"):
        assert (data / name).stat().st_mode & 0o077 == 0, name


def test_1251_the_drill_fails_when_a_stopped_athlete_keeps_consent(
    live, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _backup(live, tmp_path)
    monkeypatch.setattr(DatabaseManager, "has_current_consent", lambda self, athlete_id, now=None: True)

    result = _load("restore_drill").run_drill(tmp_path / "backups")

    assert result["ok"] is False and "consent still current" in result["error"], result


def test_1251_a_missing_queue_copy_is_reported(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    dest.with_name(dest.stem + ".pending_audit.jsonl").unlink()
    fresh = tmp_path / "fresh"
    fresh.mkdir()

    result = _load("restore_backup").restore(dest, fresh)

    assert result["ok"] is True and result["queue_copy_found"] is False, result
    assert result["withdrawals_in_backup"] == 0


# ── #1497 (DR-NEW-06): no withdrawal is lost from a damaged database or with the skip flag ──


def _recorded_after_backup(tmp_path: Path) -> tuple[Path, Path]:
    """A backup where A and B consent, then A's /stop recorded in the database only."""
    data = tmp_path / "live"
    db = DatabaseManager(db_name="titan_core.db", db_dir=data)
    for athlete in (_A, _B):
        db.conn.execute(
            "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')", (athlete, athlete)
        )
    db.conn.commit()
    for athlete in (_A, _B):
        db.grant_consent(athlete, CONSENT_TEXT_VERSION, now=datetime.now(UTC) - timedelta(days=1))
    dest = db.backup_database(backup_dir=tmp_path / "backups")
    assert dest is not None
    assert db.withdraw_consent(_A, coach_id="telegram:test", action_type="TELEGRAM_STOP") == "recorded"
    db.close()
    return dest, data


def _empty_the_consent_index(database: Path) -> None:
    """Point the consent index at an empty b-tree: indexed reads of consent_log then find nothing."""
    with closing(sqlite3.connect(database)) as conn:
        conn.execute("CREATE TABLE spare_1497 (a TEXT)")
        conn.execute("CREATE INDEX spare_1497_idx ON spare_1497 (a)")
        conn.commit()
        (root,) = conn.execute("SELECT rootpage FROM sqlite_master WHERE name = 'spare_1497_idx'").fetchone()
        conn.execute("PRAGMA writable_schema = ON")
        conn.execute("UPDATE sqlite_master SET rootpage = ? WHERE name = 'idx_consent_log_athlete'", (root,))
        conn.execute("PRAGMA writable_schema = OFF")
        conn.commit()


def test_1497_a_damaged_consent_index_stops_the_restore(tmp_path: Path) -> None:
    dest, data = _recorded_after_backup(tmp_path)
    _empty_the_consent_index(data / "titan_core.db")
    before = (data / "titan_core.db").read_bytes()

    result = _load("restore_backup").restore(dest, data)

    # Before #1497 the indexed read returned no rows, the restore went on and A's consent came back.
    assert result["ok"] is False and "--skip-live-withdrawals" in result["error"], result
    assert (data / "titan_core.db").read_bytes() == before
    assert not (data / "titan_core.db.before-restore").exists()


def test_1497_the_skip_flag_withdraws_every_athlete_but_the_owner(tmp_path: Path) -> None:
    dest, data = _recorded_after_backup(tmp_path)
    _empty_the_consent_index(data / "titan_core.db")
    module = _load("restore_backup")

    result = module.restore(dest, data, skip_live_withdrawals=True)

    assert result["ok"] is True and result["consents_withdrawn_unverified"] == 2, result
    unverified = [item for item in PendingAuditQueue(data).pending() if item["action"] == module.UNVERIFIED_ACTION]
    assert sorted(item["athlete_id"] for item in unverified) == [_A, _B]
    assert _consent_after_start(data) == (False, False)
    assert _consent_after_start(data, _B) == (False, False)


def test_1497_a_consent_given_after_the_restore_is_kept(tmp_path: Path) -> None:
    dest, data = _recorded_after_backup(tmp_path)
    _empty_the_consent_index(data / "titan_core.db")
    assert _load("restore_backup").restore(dest, data, skip_live_withdrawals=True)["ok"] is True
    db = DatabaseManager(db_name="titan_core.db", db_dir=data)
    try:
        db.drain_pending_audit()
        db.grant_consent(_B, CONSENT_TEXT_VERSION)  # /agree after the restore
        assert db.drain_pending_audit() == 0
        assert db.has_current_consent(_B, now=datetime.now(UTC) + timedelta(days=1))  # from the next day (D4.4)
    finally:
        db.close()


def test_1497_the_latest_withdrawal_is_compared_as_a_time(tmp_path: Path) -> None:
    data = tmp_path / "live"
    db = DatabaseManager(db_name="titan_core.db", db_dir=data)
    # As text "…T10:00:00+05:00" sorts after "…T08:00:00+00:00", but it is 05:00 UTC, three hours earlier.
    for granted, revoked in (
        ("2026-11-05T01:00:00+00:00", "2026-11-05T10:00:00+05:00"),
        ("2026-11-05T06:00:00+00:00", "2026-11-05T08:00:00+00:00"),
    ):
        db.conn.execute(
            "INSERT INTO consent_log (athlete_id, consent_type, text_version, granted_at, revoked_at, channel) "
            "VALUES (?, 'data_processing', ?, ?, ?, 'telegram')",
            (_A, CONSENT_TEXT_VERSION, granted, revoked),
        )
    db.conn.commit()
    db.close()

    (item,) = _load("restore_backup").recorded_withdrawals(data / "titan_core.db")

    assert item["athlete_id"] == _A and item["revoked_at"] == "2026-11-05T08:00:00+00:00"


@pytest.mark.parametrize("name", [".titan_core.db.restoring", "titan_core.db.before-restore.partial"])
def test_1497_a_symlink_at_a_staging_name_is_refused(live, tmp_path: Path, name: str) -> None:
    dest = _backup(live, tmp_path)
    data = live.db_path.parent
    live.close()
    victim = tmp_path / "victim"
    victim.write_bytes(b"untouched")
    (data / name).symlink_to(victim)

    result = _load("restore_backup").restore(dest, data)

    assert result["ok"] is False, result
    assert victim.read_bytes() == b"untouched"


def test_1497_again_reads_the_withdrawals_in_the_kept_database(tmp_path: Path) -> None:
    dest, data = _recorded_after_backup(tmp_path)
    for side in ("", "-wal"):
        if (data / f"titan_core.db{side}").exists():
            shutil.copyfile(data / f"titan_core.db{side}", data / f"titan_core.db.before-restore{side}")
    shutil.copyfile(dest, data / "titan_core.db")  # the first try already swapped the backup in
    for side in ("-wal", "-shm"):
        (data / f"titan_core.db{side}").unlink(missing_ok=True)

    result = _load("restore_backup").restore(dest, data, again=True)

    assert result["ok"] is True and result["withdrawals_recorded"] == 1, result
    assert _consent_after_start(data) == (False, False)
    assert _consent_after_start(data, _B) == (True, True)


def test_1497_a_stop_between_keeping_the_database_and_its_wal_can_be_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    dest, data = _recorded_after_backup(tmp_path)
    db = DatabaseManager(db_name="titan_core.db", db_dir=data)  # an open connection keeps the -wal
    try:
        assert (data / "titan_core.db-wal").exists()
        module = _load("restore_backup")
        real_copy = module._private_copy

        def _stop_at_the_wal(source: Path, target: Path) -> None:
            if source.name.endswith("-wal"):
                raise OSError("power cut")
            real_copy(source, target)

        monkeypatch.setattr(module, "_private_copy", _stop_at_the_wal)
        assert module.restore(dest, data)["ok"] is False
        monkeypatch.setattr(module, "_private_copy", real_copy)
        assert (data / "titan_core.db.before-restore").exists()
        assert not (data / "titan_core.db.before-restore-wal").exists()

        stuck = module.restore(dest, data, again=True)
        assert stuck["ok"] is False and "copy titan_core.db-wal to titan_core.db.before-restore-wal" in stuck["error"]

        shutil.copyfile(data / "titan_core.db-wal", data / "titan_core.db.before-restore-wal")
        finished = module.restore(dest, data, again=True)
    finally:
        db.close()

    assert finished["ok"] is True and finished["withdrawals_recorded"] >= 1, finished
    assert _consent_after_start(data) == (False, False)


def test_1497_a_clock_behind_the_backup_stops_the_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest, data = _recorded_after_backup(tmp_path)
    _empty_the_consent_index(data / "titan_core.db")
    module = _load("restore_backup")
    behind = datetime.now(UTC) - timedelta(days=3)  # before the consents in the backup

    class _SlowClock(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            return behind

    monkeypatch.setattr(module, "datetime", _SlowClock)
    before = (data / "titan_core.db").read_bytes()

    result = module.restore(dest, data, skip_live_withdrawals=True)

    # A withdrawal dated before a consent does not withdraw it: the restore must not go on.
    assert result["ok"] is False and "clock" in result["error"], result
    assert (data / "titan_core.db").read_bytes() == before


def test_1497_the_skip_flag_includes_an_athlete_without_a_consent_row(tmp_path: Path) -> None:
    dest, _data = _recorded_after_backup(tmp_path)
    with closing(sqlite3.connect(dest)) as conn:
        conn.execute("INSERT INTO athletes (athlete_id, display_name, created_at) VALUES ('a-0000000c', 'c', 'now')")
        conn.commit()

    items = _load("restore_backup").unverified_withdrawals(dest, datetime.now(UTC))

    assert [item["athlete_id"] for item in items] == [_A, _B, "a-0000000c"]


def test_1497_a_damaged_kept_database_stops_again(tmp_path: Path) -> None:
    dest, data = _recorded_after_backup(tmp_path)
    for side in ("", "-wal"):
        if (data / f"titan_core.db{side}").exists():
            shutil.copyfile(data / f"titan_core.db{side}", data / f"titan_core.db.before-restore{side}")
    _empty_the_consent_index(data / "titan_core.db.before-restore")
    shutil.copyfile(dest, data / "titan_core.db")
    for side in ("-wal", "-shm"):
        (data / f"titan_core.db{side}").unlink(missing_ok=True)

    result = _load("restore_backup").restore(dest, data, again=True)

    assert result["ok"] is False and "--skip-live-withdrawals" in result["error"], result


def test_1497_a_time_without_an_offset_is_read_as_utc(tmp_path: Path) -> None:
    data = tmp_path / "live"
    db = DatabaseManager(db_name="titan_core.db", db_dir=data)
    for granted, revoked in (
        ("2026-11-05T01:00:00+00:00", "2026-11-05T09:00:00"),  # no offset: 09:00 UTC, the latest
        ("2026-11-05T06:00:00+00:00", "2026-11-05T10:00:00+05:00"),  # 05:00 UTC
    ):
        db.conn.execute(
            "INSERT INTO consent_log (athlete_id, consent_type, text_version, granted_at, revoked_at, channel) "
            "VALUES (?, 'data_processing', ?, ?, ?, 'telegram')",
            (_A, CONSENT_TEXT_VERSION, granted, revoked),
        )
    db.conn.commit()
    db.close()

    (item,) = _load("restore_backup").recorded_withdrawals(data / "titan_core.db")

    assert item["revoked_at"] == "2026-11-05T09:00:00"


def test_1497_the_withdrawals_are_read_without_the_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # quick_check is made to pass, so only the table read itself can find A's withdrawal.
    dest, data = _recorded_after_backup(tmp_path)
    _empty_the_consent_index(data / "titan_core.db")
    module = _load("restore_backup")
    real_connect = sqlite3.connect

    class _Passing:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn

        def execute(self, sql: str, *args):  # noqa: ANN002, ANN201
            return self._conn.execute("SELECT 'ok'" if sql == "PRAGMA quick_check" else sql, *args)

        def close(self) -> None:
            self._conn.close()

    monkeypatch.setattr(module.sqlite3, "connect", lambda *a, **k: _Passing(real_connect(*a, **k)))
    items = module.recorded_withdrawals(data / "titan_core.db")

    assert [item["athlete_id"] for item in items] == [_A]


def test_1497_a_hard_link_at_a_staging_name_is_refused(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    data = live.db_path.parent
    live.close()
    victim = tmp_path / "victim"
    victim.write_bytes(b"untouched")
    (data / ".titan_core.db.restoring").hardlink_to(victim)

    result = _load("restore_backup").restore(dest, data)

    assert result["ok"] is False and "not a plain file" in result["error"], result
    assert victim.read_bytes() == b"untouched"


def test_1497_a_backup_path_with_uri_characters_is_refused(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    odd = tmp_path / "we?ird#dir%41"
    odd.mkdir()
    for source in (dest, dest.with_name(dest.stem + ".pending_audit.jsonl")):
        shutil.copyfile(source, odd / source.name)
    fresh = tmp_path / "fresh"
    fresh.mkdir()

    result = _load("restore_backup").restore(odd / dest.name, fresh)

    # A raw "file:" URI would check (and create) tmp_path / "we" instead of the backup restored.
    assert result["ok"] is False and "?, # or %" in result["error"], result
    assert not (tmp_path / "we").exists()
    assert list(fresh.iterdir()) == []


def test_1497_a_uri_character_in_a_symlinked_directory_is_refused(live, tmp_path: Path) -> None:
    dest = _backup(live, tmp_path)
    linked = tmp_path / "a?b"
    linked.symlink_to(dest.parent, target_is_directory=True)  # resolves to a clean path
    fresh = tmp_path / "fresh"
    fresh.mkdir()

    result = _load("restore_backup").restore(linked / dest.name, fresh)

    assert result["ok"] is False and "?, # or %" in result["error"], result
    assert not (tmp_path / "a").exists()
    assert list(fresh.iterdir()) == []


# ── #1252 (DR-NEW-02): the database and the queue are copied as one snapshot ──


def test_1252_a_drain_during_the_backup_cannot_lose_the_withdrawal(
    live, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    import titan.core.database as database_mod

    verify = database_mod._verify_backup_artifact
    drained: list[int] = []

    def _verify_while_a_drain_runs(path, **kwargs):
        # The issue's interleaving: a drain right after the database was copied (once).
        if drained:
            return verify(path, **kwargs)
        worker = threading.Thread(target=lambda: drained.append(live.drain_pending_audit()), daemon=True)
        worker.start()
        worker.join(timeout=5)
        assert drained == [0]
        return verify(path, **kwargs)

    monkeypatch.setattr(database_mod, "_verify_backup_artifact", _verify_while_a_drain_runs)
    dest = live.backup_database(backup_dir=tmp_path / "backups")
    assert dest is not None and drained == [0]
    assert not live.has_current_consent(_A)
    fresh = tmp_path / "fresh"
    fresh.mkdir()

    result = _load("restore_backup").restore(dest, fresh)

    assert result["ok"] is True, result
    assert _consent_after_start(fresh) == (False, False)


def test_1252_the_shell_backup_copies_the_database_under_the_queue_lock(live, tmp_path: Path) -> None:
    import fcntl
    import os
    import time

    data = live.db_path.parent
    lock = os.open(data / "pending_audit.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)  # a drain is running
    try:
        run = subprocess.Popen(  # nosec B603 B607 - the repo's own script on synthetic data
            ["bash", str(_ROOT / "scripts" / "backup.sh"), str(data)],
            cwd=_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        time.sleep(1.5)
        assert run.poll() is None, "the backup must wait for the queue lock"
        assert not list((data / "backups").glob("titan_core.db.*")), "no database copy before the queue lock"
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)
    out, err = run.communicate(timeout=30)
    assert run.returncode == 0, err
    (backup,) = (data / "backups").glob("titan_core.db.*")
    (copy,) = (data / "backups").glob("pending_audit.jsonl.*")
    assert copy.read_bytes() == PendingAuditQueue(data).path.read_bytes()
    assert copy.stat().st_mode & 0o077 == 0
    live.close()
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert _load("restore_backup").restore(backup, fresh)["ok"] is True
    assert _consent_after_start(fresh) == (False, False)


def test_1252_a_drain_waits_while_the_database_is_copied(live, tmp_path: Path) -> None:
    import threading

    ensure_open = live._ensure_open_locked
    started: list[threading.Thread] = []

    def _start_a_drain_inside_the_copy() -> None:
        ensure_open()
        if not started:  # inside the copy: the queue lock and the database lock are held
            worker = threading.Thread(target=live.drain_pending_audit, daemon=True)
            worker.start()
            worker.join(timeout=0.5)
            assert worker.is_alive(), "a drain must wait until the database and the queue are copied"
            started.append(worker)

    live._ensure_open_locked = _start_a_drain_inside_the_copy
    try:
        dest = live.backup_database(backup_dir=tmp_path / "backups")
    finally:
        del live._ensure_open_locked
    started[0].join(timeout=5)
    assert dest is not None and not started[0].is_alive()
    copy = dest.with_name(dest.stem + ".pending_audit.jsonl")
    (item,) = _queue_items(copy)
    assert item["athlete_id"] == _A


def _queue_items(copy: Path) -> list[dict]:
    return _load("restore_backup").read_queue_copy(copy)


def test_1252_a_queue_that_cannot_be_copied_fails_the_backup(live, tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    (backups / f"titan_{date}.pending_audit.jsonl.partial").mkdir()  # the copy cannot be written

    assert live.backup_database(backup_dir=backups) is None

    assert not (backups / f"titan_{date}.db").exists()
    assert (backups / f"titan_{date}.db.corrupt").exists()


def test_1252_a_backup_without_a_queue_removes_an_old_queue_copy(tmp_path: Path) -> None:
    db = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path / "live")
    backups = tmp_path / "backups"
    backups.mkdir()
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    stale = backups / f"titan_{date}.pending_audit.jsonl"
    stale.write_text('{"id": "x"}\n')
    try:
        dest = db.backup_database(backup_dir=backups)
    finally:
        db.close()

    assert dest is not None and not stale.exists()
    assert dest.stat().st_mode & 0o077 == 0
