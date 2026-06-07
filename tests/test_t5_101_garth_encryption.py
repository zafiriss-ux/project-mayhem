"""T5-101: Garth token Fernet encryption — unit tests.

Tests cover: encrypt-on-save, decrypt-on-load, plaintext fallback (dev mode),
and legacy project-root path warning.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import titan.integrations.garmin_sync as gs_module
from titan.integrations.garmin_sync import _decrypt_token, _encrypt_token

# ---------------------------------------------------------------------------
# Test 1: file is encrypted when TITAN_GARTH_TOKEN_KEY is set
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_token_encrypted_when_key_present(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", key)

    original = "garth_session_data_abc123"
    encrypted_bytes = _encrypt_token(original)

    # The raw bytes must NOT equal the plain UTF-8 encoding.
    assert encrypted_bytes != original.encode(), (
        "Expected encrypted bytes to differ from plaintext when key is present"
    )
    # The file should begin with the Fernet token prefix (gAAAAA…)
    assert encrypted_bytes.startswith(b"gAAAAA"), (
        "Expected Fernet-encrypted bytes (gAAAAA prefix)"
    )


# ---------------------------------------------------------------------------
# Test 2: token round-trips correctly through encrypt → decrypt
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_token_decrypted_on_load(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", key)

    original = "my_garmin_session_token_xyz"
    encrypted = _encrypt_token(original)
    decrypted = _decrypt_token(encrypted)

    assert decrypted == original, (
        f"Round-trip failed: expected {original!r}, got {decrypted!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: plaintext fallback when key is absent (dev/test mode)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_token_stored_plaintext_without_key(monkeypatch):
    monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
    monkeypatch.setenv("TITAN_ENV", "dev")

    original = "plaintext_token_no_key"
    stored = _encrypt_token(original)

    # Without a key the token is stored as raw UTF-8.
    assert stored == original.encode(), (
        "Expected plaintext bytes when TITAN_GARTH_TOKEN_KEY is absent"
    )

    recovered = _decrypt_token(stored)
    assert recovered == original, (
        f"Plaintext round-trip failed: expected {original!r}, got {recovered!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: legacy project-root token triggers a WARNING log on _get_token_path()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_legacy_token_path_warning(tmp_path, monkeypatch, caplog):
    # Redirect DATA_DIR to a temp dir that has NO token file.
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path / "data"))

    # _DATA_DIR / _GARTH_TOKEN_PATH are lazy functions (P26-05 / A1-F3) so tests
    # patch _get_garth_token_path() directly rather than frozen module constants.
    new_data_dir = tmp_path / "data"
    new_token_path = new_data_dir / gs_module._GARTH_TOKEN_FILENAME
    monkeypatch.setattr(gs_module, "_get_garth_token_path", lambda: new_token_path)

    # Create a legacy token at the project root (parent of the package tree).
    project_root = Path(gs_module.__file__).parent.parent.parent
    legacy_path = project_root / gs_module._GARTH_TOKEN_FILENAME

    # Only create the legacy file if it doesn't already exist (avoid polluting real FS).
    created = False
    if not legacy_path.exists():
        legacy_path.write_bytes(b"legacy_token")
        created = True

    try:
        from titan.integrations.garmin_sync import GarminSync

        sync = GarminSync.__new__(GarminSync)
        sync.__dict__.setdefault("_connect_lock", __import__("threading").Lock())

        with caplog.at_level(logging.WARNING, logger="titan.integrations.garmin_sync"):
            token_path = sync._get_token_path()

        assert token_path == new_token_path, (
            "Token path should point to the data-dir location"
        )
        legacy_warning = any(
            "Legacy" in r.message and "garth" in r.message.lower()
            for r in caplog.records
        )
        assert legacy_warning, (
            "Expected a WARNING about legacy token at project root. "
            f"Log records: {[r.message for r in caplog.records]}"
        )
    finally:
        if created and legacy_path.exists():
            legacy_path.unlink()
