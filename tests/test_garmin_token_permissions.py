"""The persisted Garmin session token is readable by its owner only (0o600).

Same flaw class as CVE-2026-54447 (garminconnect <= 0.3.4): a token file
created under the default umask is world-readable.
"""

import os
import stat
import sys

import pytest

from titan.integrations.garmin_sync import GarminSync, _write_private_file

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.mark.unit
def test_new_token_file_is_owner_only(tmp_path):
    token_file = tmp_path / ".garth_token"
    _write_private_file(token_file, b"secret")
    assert token_file.read_bytes() == b"secret"
    assert _mode(token_file) == 0o600


@pytest.mark.unit
def test_existing_world_readable_token_is_tightened(tmp_path):
    token_file = tmp_path / ".garth_token"
    token_file.write_bytes(b"old")
    os.chmod(token_file, 0o644)
    _write_private_file(token_file, b"new")
    assert token_file.read_bytes() == b"new"
    assert _mode(token_file) == 0o600


@pytest.mark.integration
def test_login_saves_token_owner_only(monkeypatch, tmp_path, request):
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)
    monkeypatch.setenv("TITAN_ENV", "dev")
    previous_umask = os.umask(0o022)
    request.addfinalizer(lambda: os.umask(previous_umask))
    token_file = tmp_path / ".garth_token"

    class _FakeGarth:
        def dumps(self):
            return "fresh_token"

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

        def login(self):
            pass

    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())
    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    assert sync.connect() is True
    assert token_file.read_text(encoding="utf-8") == "fresh_token"
    assert _mode(token_file) == 0o600
