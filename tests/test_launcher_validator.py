from pathlib import Path

from launcher import validator
from launcher.errors import DatabaseError, EnvironmentError, SystemError


def test_check_python_version_fails_for_older_runtime(monkeypatch):
    monkeypatch.setattr(validator.sys, "version_info", (3, 10, 9, "final", 0))

    success, error = validator.check_python_version()

    assert success is False
    assert isinstance(error, EnvironmentError)
    assert error.code == "ENV_PYTHON_VERSION"


def test_check_data_directory_creates_expected_subdirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "Documents" / "TITAN"
    monkeypatch.setattr(validator, "get_data_directory", lambda: data_dir)

    success, error = validator.check_data_directory()

    assert success is True
    assert error is None
    assert data_dir.exists()
    assert (data_dir / "logs").is_dir()
    assert (data_dir / "exports").is_dir()


def test_check_database_missing_is_non_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(validator, "get_data_directory", lambda: Path(tmp_path))

    success, error = validator.check_database()

    assert success is True
    assert isinstance(error, DatabaseError)
    assert error.code == "DB_MISSING"
