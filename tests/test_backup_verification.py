"""Tests for scripts/verify_backup.py — backup integrity verification."""

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _titan_db(data_dir: Path) -> Path:
    """A real, synthetic TITAN database (current schema) at <data_dir>/titan_core.db."""
    from titan.core.database import DatabaseManager

    DatabaseManager(db_name="titan_core.db", db_dir=data_dir).close()
    return data_dir / "titan_core.db"


def _verify(data_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/verify_backup.py", str(data_dir)], cwd=REPO_ROOT, capture_output=True, text=True,
    )


@pytest.mark.integration
def test_verify_backup_exits_0_on_valid(tmp_path: Path) -> None:
    _titan_db(tmp_path)
    subprocess.run(["bash", "scripts/backup.sh", str(tmp_path)], cwd=REPO_ROOT, check=True)
    result = subprocess.run(
        ["python3", "scripts/verify_backup.py", str(tmp_path)],
        cwd=REPO_ROOT,
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
        cwd=REPO_ROOT,
        capture_output=True,
    )
    assert result.returncode == 1


@pytest.mark.unit
def test_verify_backup_exits_1_no_backups(tmp_path: Path) -> None:
    (tmp_path / "backups").mkdir()
    result = subprocess.run(
        ["python3", "scripts/verify_backup.py", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    assert result.returncode == 1


# ── #1451 (BKP-NEW-01): only a usable TITAN database passes ──────────────────

def _artifact(tmp_path: Path, name: str = "titan_core.db.20261102") -> Path:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(exist_ok=True)
    return backup_dir / name


def _with_user_version(path: Path, version: int) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(f"PRAGMA user_version = {int(version)}")
    conn.commit()
    conn.close()


@pytest.mark.integration
def test_1451_a_zero_byte_backup_fails(tmp_path: Path) -> None:
    _artifact(tmp_path).write_bytes(b"")
    result = _verify(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "0 bytes" in result.stdout


@pytest.mark.integration
def test_1451_a_database_that_is_not_titan_fails(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(_artifact(tmp_path)))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    result = _verify(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "not a TITAN database" in result.stdout


@pytest.mark.integration
def test_1451_a_titan_version_without_the_core_tables_fails(tmp_path: Path) -> None:
    from titan.core.database import SCHEMA_VERSION

    artifact = _artifact(tmp_path)
    conn = sqlite3.connect(str(artifact))
    conn.execute("CREATE TABLE athletes (athlete_id TEXT)")
    conn.commit()
    conn.close()
    _with_user_version(artifact, SCHEMA_VERSION)
    result = _verify(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "missing tables: training_log, daily_metrics" in result.stdout


@pytest.mark.integration
def test_1451_a_backup_newer_than_this_code_fails(tmp_path: Path) -> None:
    from titan.core.database import SCHEMA_VERSION

    artifact = _artifact(tmp_path)
    shutil.copy2(_titan_db(tmp_path), artifact)
    _with_user_version(artifact, SCHEMA_VERSION + 1)
    result = _verify(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "newer than this code" in result.stdout


@pytest.mark.integration
def test_1451_an_older_titan_schema_still_passes(tmp_path: Path) -> None:
    """Control: an older TITAN schema is migrated on start, as before."""
    from titan.core.database import SCHEMA_VERSION

    artifact = _artifact(tmp_path)
    shutil.copy2(_titan_db(tmp_path), artifact)
    _with_user_version(artifact, SCHEMA_VERSION - 1)
    assert _verify(tmp_path).returncode == 0


@pytest.mark.integration
def test_1451_an_interrupted_backup_leaves_no_finished_name_and_is_not_verified(tmp_path: Path) -> None:
    """The source cannot be copied (not a database): backup.sh stops before the rename."""
    (tmp_path / "titan_core.db").write_bytes(b"notadb" * 100)
    run = subprocess.run(["bash", "scripts/backup.sh", str(tmp_path)], cwd=REPO_ROOT, capture_output=True)
    assert run.returncode != 0
    assert not [p for p in (tmp_path / "backups").iterdir() if p.name.startswith("titan_core.db.")]
    result = _verify(tmp_path)
    assert result.returncode == 1
    assert "No backups found" in result.stdout


@pytest.mark.integration
def test_1451_a_partial_or_sidecar_file_is_never_the_backup_verified(tmp_path: Path) -> None:
    good = _artifact(tmp_path, "titan_core.db.20261101")
    shutil.copy2(_titan_db(tmp_path), good)
    _artifact(tmp_path, ".titan_core.db.20261102.partial.Ab12Cd").write_bytes(b"")
    _artifact(tmp_path, "titan_core.db.20261101-journal").write_bytes(b"")
    result = _verify(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "titan_core.db.20261101\n" in result.stdout


@pytest.mark.integration
def test_1451_a_titan_schema_with_no_athletes_fails(tmp_path: Path) -> None:
    """An empty shell (schema, no rows at all) is not a restore candidate."""
    artifact = _artifact(tmp_path)
    shutil.copy2(_titan_db(tmp_path), artifact)
    conn = sqlite3.connect(str(artifact))
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM athletes")
    conn.commit()
    conn.close()
    result = _verify(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "no athletes" in result.stdout


@pytest.mark.integration
def test_1451_a_symlink_named_like_a_backup_fails(tmp_path: Path) -> None:
    _artifact(tmp_path, "titan_core.db.20261102").symlink_to(_titan_db(tmp_path))
    result = _verify(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "not a regular file" in result.stdout


@pytest.mark.integration
def test_1451_a_finished_backup_is_owner_only_and_leaves_no_partial(tmp_path: Path) -> None:
    _titan_db(tmp_path)
    subprocess.run(["bash", "scripts/backup.sh", str(tmp_path)], cwd=REPO_ROOT, check=True, capture_output=True)
    backups = tmp_path / "backups"
    finished = [p for p in backups.iterdir() if p.name.startswith("titan_core.db.")]
    assert len(finished) == 1
    assert finished[0].stat().st_mode & 0o077 == 0
    assert not [p for p in backups.iterdir() if ".partial" in p.name]
    assert _verify(tmp_path).returncode == 0
