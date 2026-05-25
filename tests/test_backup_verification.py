"""Tests for scripts/verify_backup.py — backup integrity verification."""

import sqlite3
import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_verify_backup_exits_0_on_valid(tmp_path: Path) -> None:
    db_path = tmp_path / "titan_core.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    subprocess.run(["bash", "scripts/backup.sh", str(tmp_path)], check=True)
    result = subprocess.run(
        ["python3", "scripts/verify_backup.py", str(tmp_path)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_verify_backup_exits_1_on_corrupt(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    corrupt = backup_dir / "titan_core.db.20260101"
    corrupt.write_bytes(b"notadb" * 100)
    result = subprocess.run(
        ["python3", "scripts/verify_backup.py", str(tmp_path)],
        capture_output=True,
    )
    assert result.returncode == 1


@pytest.mark.unit
def test_verify_backup_exits_1_no_backups(tmp_path: Path) -> None:
    (tmp_path / "backups").mkdir()
    result = subprocess.run(
        ["python3", "scripts/verify_backup.py", str(tmp_path)],
        capture_output=True,
    )
    assert result.returncode == 1
