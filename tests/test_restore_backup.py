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
import subprocess  # nosec B404 - runs the repo's own script on synthetic data
import sys
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
