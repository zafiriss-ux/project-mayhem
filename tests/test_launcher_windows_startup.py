"""The Windows exe must start when Documents is unusable and when there is no console
(v5.8.0 crashed on both: WinError 2 creating Documents\\TITAN, and TeeStream writing to
sys.stdout = None in the windowed build)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from launcher import logger as launcher_logger
from launcher import validator


@pytest.fixture
def windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(validator.platform, "system", lambda: "Windows")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "profile"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(validator, "_shell_documents_folder", lambda: None)
    (tmp_path / "profile").mkdir()
    validator._windows_data_directory.cache_clear()
    yield tmp_path
    validator._windows_data_directory.cache_clear()


def _block(path: Path) -> None:
    """Make `path` impossible to use as a folder."""
    path.write_text("not a folder", encoding="utf-8")


def test_profile_documents_is_used_when_it_works(windows: Path) -> None:
    assert validator.get_data_directory() == windows / "profile" / "Documents" / "TITAN"


def test_moved_documents_folder_is_used_when_profile_documents_fails(
    windows: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _block(windows / "profile" / "Documents")
    monkeypatch.setattr(validator, "_shell_documents_folder", lambda: windows / "OneDrive" / "Documents")

    assert validator.get_data_directory() == windows / "OneDrive" / "Documents" / "TITAN"


def test_local_app_data_is_used_when_no_documents_folder_works(windows: Path) -> None:
    _block(windows / "profile" / "Documents")

    data_dir = validator.get_data_directory()

    assert data_dir == windows / "local" / "TITAN"
    assert data_dir.is_dir()


def test_logging_starts_when_profile_documents_fails(windows: Path) -> None:
    _block(windows / "profile" / "Documents")

    log = launcher_logger.setup_logging(prefix="launcher_test")
    try:
        assert launcher_logger.get_log_directory() == windows / "local" / "TITAN" / "logs"
    finally:
        for handler in log.handlers:
            handler.close()
        log.handlers.clear()


def test_tee_stream_without_a_console_writes_to_the_log_only(caplog: pytest.LogCaptureFixture) -> None:
    tee = launcher_logger.TeeStream(None, logging.getLogger("tee_test"))

    with caplog.at_level(logging.INFO, logger="tee_test"):
        assert tee.write("Version: 5.8.0\n") == len("Version: 5.8.0\n")
        tee.flush()

    assert "Version: 5.8.0" in caplog.text


def test_print_works_after_redirect_without_a_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    launcher_logger.redirect_output(logging.getLogger("tee_test"), enable=True)
    print("banner")

    assert isinstance(sys.stdout, launcher_logger.TeeStream)


def test_exe_is_built_with_a_console_window() -> None:
    """The main menu reads the keyboard; a windowed exe showed nothing after the wizard."""
    spec = (Path(__file__).resolve().parents[1] / "launcher" / "build.spec").read_text(encoding="utf-8")
    settings = [line.split("#")[0].strip() for line in spec.splitlines() if line.strip().startswith("console=")]

    assert settings == ["console=True,"]


def test_a_failing_log_handler_does_not_loop_through_the_tee(monkeypatch: pytest.MonkeyPatch) -> None:
    """5.8.1 grew memory without bound: a cp1253 handler failed on the banner, its error
    report went to stderr (a tee), was logged again, failed again, nesting each report."""
    log = logging.getLogger("tee_loop_test")
    log.propagate = False
    log.setLevel(logging.INFO)
    calls = []

    class FailingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            calls.append(record.getMessage())
            try:
                "╔══ 🏃".encode("cp1253")
            except UnicodeEncodeError:
                self.handleError(record)

    handler = FailingHandler()
    log.addHandler(handler)
    monkeypatch.setattr(logging, "raiseExceptions", True)
    monkeypatch.setattr(sys, "stdout", launcher_logger.TeeStream(None, log))
    monkeypatch.setattr(sys, "stderr", launcher_logger.TeeStream(None, log))
    try:
        print("╔══ 🏃 banner ══╗")
    finally:
        log.removeHandler(handler)

    assert calls == ["╔══ 🏃 banner ══╗"]
