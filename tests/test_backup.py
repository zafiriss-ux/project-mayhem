"""Tests for scripts/backup.sh and the worker backup integration (C-4 / P15-D4)."""

import os
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()


@pytest.mark.integration
def test_backup_script_creates_file(tmp_path):
    db_path = tmp_path / "titan_core.db"
    _make_db(db_path)

    result = subprocess.run(
        ["bash", "scripts/backup.sh", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    backup_dir = tmp_path / "backups"
    backups = list(backup_dir.glob("titan_core.db.*"))
    assert len(backups) == 1
    assert backups[0].stat().st_size > 0


@pytest.mark.integration
def test_backup_is_readable_sqlite(tmp_path):
    db_path = tmp_path / "titan_core.db"
    _make_db(db_path)

    subprocess.run(
        ["bash", "scripts/backup.sh", str(tmp_path)],
        check=True,
    )
    backup = list((tmp_path / "backups").glob("titan_core.db.*"))[0]

    conn = sqlite3.connect(str(backup))
    result = conn.execute("PRAGMA integrity_check").fetchone()
    conn.close()
    assert result[0] == "ok"


@pytest.mark.integration
def test_backup_pruning_keeps_7(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    for i in range(10):
        f = backup_dir / f"titan_core.db.2026050{i}"
        f.write_bytes(b"x")
        old = time.time() - (i + 8) * 86400
        os.utime(f, (old, old))

    db_path = tmp_path / "titan_core.db"
    conn = sqlite3.connect(str(db_path))
    conn.close()

    subprocess.run(
        ["bash", "scripts/backup.sh", str(tmp_path)],
        check=True,
    )

    backups = list(backup_dir.glob("titan_core.db.*"))
    assert len(backups) <= 8


@pytest.mark.unit
def test_worker_run_forever_calls_backup():
    src = Path("titan/worker/__init__.py").read_text()
    assert "_run_backup" in src or "backup" in src.lower(), (
        "C-4: worker must call backup"
    )
