"""Check fingerprint values against real standard-library environment metadata."""

import hashlib
import importlib.metadata
import json
import platform
import socket
import subprocess
import sys
import venv
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "env_fingerprint.sh"


def fingerprint(interpreter):
    return subprocess.run(
        ["bash", str(SCRIPT), str(interpreter)],
        capture_output=True,
        text=True,
        check=False,
    )


def environment_hash(distributions, prefix):
    metadata = json.dumps(
        {"distributions": sorted(distributions), "prefix": prefix},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(metadata).hexdigest()


def test_fingerprint_matches_actual_metadata_and_is_repeatable():
    result = fingerprint(sys.executable)
    repeated = fingerprint(sys.executable)
    distributions = [
        (distribution.metadata["Name"], distribution.version)
        for distribution in importlib.metadata.distributions()
    ]

    assert result.returncode == repeated.returncode == 0, result.stderr
    assert result.stdout == repeated.stdout
    assert json.loads(result.stdout) == {
        "python_version": platform.python_version(),
        "venv_hash": environment_hash(distributions, sys.prefix),
        "host_id": hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest(),
    }


def test_selected_interpreter_hashes_its_prefix_and_sorted_installed_versions(tmp_path):
    environment = tmp_path / "selected python"
    venv.EnvBuilder(with_pip=False).create(environment)
    interpreter = environment / "bin" / "python"
    site_packages = environment / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    for name, version in [("Zulu", "2.0"), ("Alpha", "1.0")]:
        distribution = site_packages / f"{name}-{version}.dist-info"
        distribution.mkdir()
        (distribution / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
            encoding="utf-8",
        )

    result = fingerprint(interpreter)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["venv_hash"] == environment_hash(
        [("Alpha", "1.0"), ("Zulu", "2.0")], str(environment)
    )
    assert json.loads(result.stdout)["venv_hash"] != environment_hash(
        [("Alpha", "1.0"), ("Zulu", "2.0")], sys.prefix
    )

    (site_packages / "Zulu-2.0.dist-info" / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: Zulu\nVersion: 2.1\n", encoding="utf-8"
    )
    changed = fingerprint(interpreter)

    assert changed.returncode == 0, changed.stderr
    assert json.loads(changed.stdout)["venv_hash"] == environment_hash(
        [("Alpha", "1.0"), ("Zulu", "2.1")], str(environment)
    )
    assert changed.stdout != result.stdout


def test_interpreter_failure_preserves_status_without_fabricated_metadata(tmp_path):
    interpreter = tmp_path / "failing-python"
    interpreter.write_text("#!/bin/sh\necho interpreter-failed >&2\nexit 29\n", encoding="utf-8")
    interpreter.chmod(0o755)

    result = fingerprint(interpreter)

    assert result.returncode == 29
    assert result.stdout == ""
    assert "interpreter-failed" in result.stderr


def test_missing_interpreter_fails_without_metadata(tmp_path):
    result = fingerprint(tmp_path / "missing-python")

    assert result.returncode == 127
    assert result.stdout == ""
    assert "missing-python" in result.stderr
