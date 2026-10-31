"""M0-17 and SP-04: the API process redacts its log lines, and a registered secret is also
found after json.dumps or repr escaped it. Synthetic values only."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from titan.utils.secrets import RedactingFilter, redact_secrets, register_secret

REPO = Path(__file__).resolve().parents[1]
CANARY_TOKEN = "123456789:CANARYcanaryCANARYcanary_abc"  # bot-token shape, fake
# Greek letters, a quote and a backslash: json.dumps and repr both escape it.
CANARY_PW = 'Κωδ"ικός\\canary-m017'


@pytest.mark.unit
def test_a_registered_secret_is_redacted_after_json_dumps() -> None:
    register_secret(CANARY_PW)
    for ensure_ascii in (True, False):
        line = json.dumps(
            {"flow": "garmin", "error_message": f"login failed with {CANARY_PW}"},
            ensure_ascii=ensure_ascii,
        )
        record = logging.LogRecord("titan.x", logging.ERROR, "", 0, line, None, None)
        RedactingFilter().filter(record)
        assert "canary-m017" not in record.getMessage()
        assert "canary-m017" not in redact_secrets(line)


@pytest.mark.unit
def test_a_registered_secret_is_redacted_in_repr() -> None:
    register_secret(CANARY_PW)
    assert "canary-m017" not in redact_secrets(repr(ValueError(f"bad password {CANARY_PW}")))


def _rsa_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return private, public


@pytest.mark.integration
def test_the_api_process_redacts_a_token_on_stderr(tmp_path) -> None:
    """scripts/run_api.py composes the API; a WARNING with a bot token reaches stderr redacted."""
    private, public = _rsa_pair()
    data = tmp_path / "data"
    data.mkdir()
    code = textwrap.dedent(
        f"""
        import logging, runpy
        runpy.run_path({str(REPO / "scripts" / "run_api.py")!r}, run_name="not_main")
        logging.getLogger("titan.api").warning("readyz db check failed: {CANARY_TOKEN}")
        """
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO),
        "TITAN_DATA_DIR": str(data),
        "TITAN_JWT_PRIVATE_KEY": private,
        "TITAN_JWT_PUBLIC_KEY": public,
        "TELEGRAM_BOT_TOKEN": "",
    }
    env.pop("TITAN_METRICS_TOKEN", None)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "readyz db check failed" in result.stderr
    assert CANARY_TOKEN not in result.stderr
