"""AGENTS §8.10 DR-01..03 (T-PRA-08, B-6): verified, off-volume, retained backups.

DR-01  the Docker worker writes backups to their own volume, not titan-data.
DR-02  every backup artifact passes integrity_check + user_version; failures are
       quarantined, logged CRITICAL and counted; retention is daily + weekly.
DR-03  the restore drill restores the latest *real* backup and verifies it
       (selected by ``pytest -k db_integrity``).
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
import sqlite3
import subprocess
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import titan.core.database as database_mod
import titan.worker as worker_mod
from titan.core.database import SCHEMA_VERSION, DatabaseManager

_ROOT = Path(__file__).resolve().parents[1]


def _load_restore_drill():
    spec = importlib.util.spec_from_file_location("restore_drill", _ROOT / "scripts" / "restore_drill.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    manager = DatabaseManager("titan_core.db", db_dir=tmp_path / "data")
    manager.save_session(date="2026-10-01", session_type="EASY", distance_km=8.0, duration_sec=2700)
    return manager


# ── DR-02: verification of the produced artifact ────────────────────────────


def test_backup_artifact_is_verified_and_logged_with_size(db: DatabaseManager, tmp_path: Path, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="titan.core.database"):
        dest = db.backup_database(backup_dir=tmp_path / "backups")

    assert dest is not None and dest.exists()
    conn = sqlite3.connect(dest)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        conn.close()
    assert '"size_bytes"' in caplog.text and '"integrity": "ok"' in caplog.text


def test_unverifiable_backup_is_quarantined_logged_critical_and_counted(
    db: DatabaseManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    monkeypatch.setattr(database_mod, "_verify_backup_artifact", lambda *a, **k: "integrity_check: page 3 corrupt")
    counted: list[str] = []
    monkeypatch.setattr(
        "titan.observability.metrics.get_metrics",
        lambda: SimpleNamespace(counter=lambda name, *a, **k: counted.append(name)),
    )
    backup_dir = tmp_path / "backups"

    with caplog.at_level(logging.CRITICAL, logger="titan.core.database"):
        dest = db.backup_database(backup_dir=backup_dir)

    assert dest is None
    assert list(backup_dir.glob("titan_????-??-??.db")) == []
    assert len(list(backup_dir.glob("*.db.corrupt"))) == 1
    assert any(r.levelno == logging.CRITICAL and "db_backup_failed" in r.getMessage() for r in caplog.records)
    assert counted == ["backup_failure_total"]


def test_verify_rejects_schema_version_mismatch(db: DatabaseManager, tmp_path: Path) -> None:
    dest = db.backup_database(backup_dir=tmp_path / "backups")
    assert database_mod._verify_backup_artifact(dest, expected_user_version=SCHEMA_VERSION + 1) is not None


class _ConnKilledDuringBackup:
    """The live connection, except that ``backup()`` dies part-way, like a SIGKILL (RC-01)."""

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real

    def backup(self, target: sqlite3.Connection, *args, **kwargs) -> None:
        target.execute("CREATE TABLE half_written (x)")
        target.commit()
        raise KeyboardInterrupt  # not an Exception: nothing in backup_database may catch it

    def __getattr__(self, name: str):
        return getattr(self._real, name)


def test_backup_killed_midway_leaves_no_dated_file_and_the_next_call_backs_up(
    db: DatabaseManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup_dir = tmp_path / "backups"
    real = db.conn
    monkeypatch.setattr(db, "conn", _ConnKilledDuringBackup(real))
    with pytest.raises(KeyboardInterrupt):
        db.backup_database(backup_dir=backup_dir)
    monkeypatch.setattr(db, "conn", real)

    assert list(backup_dir.glob("titan_????-??-??.db")) == []

    dest = db.backup_database(backup_dir=backup_dir)
    assert dest is not None
    assert database_mod._verify_backup_artifact(dest, expected_user_version=SCHEMA_VERSION) is None
    assert [p.name for p in backup_dir.iterdir()] == [dest.name]


def test_leftover_partial_file_from_a_killed_backup_does_not_block_the_backup(
    db: DatabaseManager, tmp_path: Path
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    dest = db.backup_database(backup_dir=backup_dir)
    assert dest is not None
    dest.unlink()
    leftover = dest.with_name(dest.name + ".partial")
    leftover.write_bytes(b"not a database, cut off by SIGKILL")

    again = db.backup_database(backup_dir=backup_dir)

    assert again == dest
    assert database_mod._verify_backup_artifact(again, expected_user_version=SCHEMA_VERSION) is None
    assert not leftover.exists()


def test_leftover_partial_file_from_an_earlier_day_is_removed(db: DatabaseManager, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    old_leftover = backup_dir / "titan_2026-01-02.db.partial"
    old_leftover.write_bytes(b"cut off by SIGKILL on an earlier day")

    dest = db.backup_database(backup_dir=backup_dir)

    assert dest is not None
    assert not old_leftover.exists()


# ── DR-02: retention ────────────────────────────────────────────────────────


def test_retention_keeps_daily_window_plus_one_per_older_week(db: DatabaseManager, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    newest = date(2026, 10, 4)  # a Sunday
    names = [f"titan_{(newest - timedelta(days=i)).isoformat()}.db" for i in range(60)]
    for name in names:
        (backup_dir / name).write_bytes(b"")

    db._prune_old_backups(backup_dir, keep=7, keep_weekly=4)

    kept = sorted(p.name for p in backup_dir.glob("titan_*.db"))
    daily = sorted(names[:7])
    # The 7-day window is the ISO week ending 2026-10-04; the next four older weeks
    # each keep their newest (Sunday) backup.
    weekly = sorted(f"titan_{(newest - timedelta(weeks=w)).isoformat()}.db" for w in range(1, 5))
    assert kept == sorted(daily + weekly)


def test_retention_without_weekly_matches_previous_behavior(db: DatabaseManager, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for i in range(10):
        (backup_dir / f"titan_2026-09-{i + 10:02d}.db").write_bytes(b"")

    db._prune_old_backups(backup_dir, keep=3)

    assert sorted(p.name for p in backup_dir.glob("titan_*.db")) == [
        "titan_2026-09-17.db",
        "titan_2026-09-18.db",
        "titan_2026-09-19.db",
    ]


# ── DR-01: off-volume location ──────────────────────────────────────────────


def test_worker_backup_uses_backup_dir_and_env_retention(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict] = []
    fake_db = SimpleNamespace(backup_database=lambda **kw: calls.append(kw))
    monkeypatch.setattr(
        worker_mod,
        "get_settings",
        lambda: SimpleNamespace(
            TITAN_BACKUP_DIR=str(tmp_path / "offvolume"),
            BACKUP_RETENTION_DAILY_DAYS=7,
            BACKUP_RETENTION_WEEKLY_COUNT=4,
        ),
    )

    worker_mod._run_backup(fake_db)

    assert calls == [{"backup_dir": tmp_path / "offvolume", "keep": 7, "keep_weekly": 4}]


def _worker_block(compose: str) -> list[str]:
    lines = compose.splitlines()
    start = lines.index("  titan-worker:")
    block = []
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith("    "):
            break
        block.append(line.strip())
    return block


def test_compose_worker_writes_backups_to_their_own_volume() -> None:
    compose = (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    worker = _worker_block(compose)
    top_level_volumes = compose.split("services:")[0].splitlines()

    assert "- TITAN_BACKUP_DIR=/backups" in worker
    assert "- titan-backups:/backups" in worker
    assert "- titan-data:/data" in worker
    assert "  titan-backups:" in top_level_volumes


# ── DR-03: restore drill against the latest real backup ─────────────────────


def test_db_integrity_restore_drill_on_latest_backup(db: DatabaseManager, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    dest = db.backup_database(backup_dir=backup_dir)
    assert dest is not None
    drill = _load_restore_drill()

    result = drill.run_drill(backup_dir)

    assert result["ok"] is True, result
    assert result["backup"] == dest.name
    assert result["user_version"] == SCHEMA_VERSION
    assert drill.main(["--backup-dir", str(backup_dir)]) == 0


def test_db_integrity_restore_drill_fails_on_corrupt_backup(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "titan_2026-10-01.db").write_bytes(b"SQLite format 3\x00" + b"\xff" * 4096)
    drill = _load_restore_drill()

    result = drill.run_drill(backup_dir)

    assert result["ok"] is False
    assert drill.main(["--backup-dir", str(backup_dir)]) == 1


def test_db_integrity_restore_drill_fails_without_backups(tmp_path: Path) -> None:
    drill = _load_restore_drill()
    assert drill.run_drill(tmp_path)["ok"] is False


# ── RC-02: the local restore runbook (Scenario B) ───────────────────────────

_BACKUP_PLACEHOLDER = "~/Documents/TITAN/backups/titan_core.db.YYYYMMDD"


def _scenario_b_file_commands() -> list[str]:
    """The file-handling lines of Scenario B in database-recovery.md (cp, mv, rm, tests)."""
    text = (_ROOT / "docs" / "runbooks" / "database-recovery.md").read_text(encoding="utf-8")
    section = text.split("### Scenario B", 1)[1].split("### Scenario C", 1)[0]
    block = section.split("```bash", 1)[1].split("```", 1)[0]
    lines = [line.strip() for line in block.splitlines()]
    return [line for line in lines if line.split(" ", 1)[0] in {"cp", "mv", "rm", "["}]


def _rows(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()


@pytest.mark.skipif(shutil.which("bash") is None, reason="the runbook commands are bash")
def test_local_restore_runbook_brings_back_the_backup_and_keeps_the_old_wal(tmp_path: Path) -> None:
    backup = tmp_path / "titan_core.db.20261030"
    conn = sqlite3.connect(backup)
    conn.execute("CREATE TABLE t (x)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    # The live database after a crash: the backup's pages plus 18 rows that exist only in its -wal.
    live_dir = tmp_path / "run"
    live_dir.mkdir()
    work = tmp_path / "work.db"
    work.write_bytes(backup.read_bytes())
    writer = sqlite3.connect(work)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(18)])
    writer.commit()
    (live_dir / "titan_core.db").write_bytes(work.read_bytes())
    (live_dir / "titan_core.db-wal").write_bytes(Path(f"{work}-wal").read_bytes())
    writer.close()

    commands = _scenario_b_file_commands()
    assert any(_BACKUP_PLACEHOLDER in c for c in commands)
    script = "\n".join(c.replace(_BACKUP_PLACEHOLDER, str(backup)) for c in commands)
    result = subprocess.run(["bash", "-c", script], cwd=live_dir, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    assert _rows(live_dir / "titan_core.db") == 1, "the restored database must be the backup, not backup + old WAL"
    kept = sorted(p.name for p in live_dir.iterdir() if "before-restore" in p.name)
    assert kept, "the damaged database must be kept before the restore"
    assert _rows(live_dir / kept[0]) == 19, "the kept copy must include the writes that lived only in the -wal"
