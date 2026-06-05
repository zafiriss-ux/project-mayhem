from pathlib import Path

import pytest


def _setup_env_script() -> str:
    return Path("scripts/setup_env.sh").read_text(encoding="utf-8")


@pytest.mark.unit
def test_setup_env_retries_runtime_install_with_public_pypi_fallback() -> None:
    script = _setup_env_script()

    assert "install_runtime_dependencies()" in script
    assert 'PIP_INDEX_URL="https://pypi.org/simple"' in script
    assert 'PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org"' in script


@pytest.mark.unit
def test_setup_env_stops_after_failed_install_when_custom_index_is_set() -> None:
    script = _setup_env_script()

    assert 'if [ -n "${PIP_INDEX_URL:-}" ]; then' in script
    assert "return 1" in script
