"""AGENTS §8.9 RE-01..04 (T-PRA-09): one version source, tagged releases, pinned images, rollback runbook."""

from __future__ import annotations

import re
import tomllib
from importlib import metadata
from pathlib import Path

import titan

_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    with (_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


# ── RE-01 ───────────────────────────────────────────────────────────────────


def test_runtime_version_equals_pyproject_and_package_metadata() -> None:
    declared = _pyproject_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", declared)
    assert titan.__version__ == declared
    try:
        installed = metadata.version("project-mayhem")
    except metadata.PackageNotFoundError:
        return  # source checkout / Docker image: pyproject.toml is the only source
    assert installed == declared


def test_no_version_literal_in_titan_or_launcher() -> None:
    literal = re.compile(r"""__version__\s*=\s*["']""")
    files = [*(_ROOT / "titan").rglob("*.py"), *(_ROOT / "launcher").rglob("*.py")]
    offenders = [str(p.relative_to(_ROOT)) for p in files if literal.search(p.read_text("utf-8"))]
    assert offenders == []


def test_windows_bundle_ships_pyproject_for_the_version() -> None:
    spec = (_ROOT / "launcher" / "build.spec").read_text(encoding="utf-8")
    assert "(str(root_dir / 'pyproject.toml'), '.')" in spec


# ── RE-02 ───────────────────────────────────────────────────────────────────


def test_release_workflow_runs_on_version_tags_and_checks_them() -> None:
    wf = (_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'tags: ["v*.*.*"]' in wf
    assert "does not match pyproject.toml version" in wf
    assert "merge-base --is-ancestor" in wf  # tagged commit must be on main
    assert "titan-api:${{ github.ref_name }}" in wf
    assert "titan-worker:${{ github.ref_name }}" in wf
    assert "runs-on: windows-latest" in wf
    assert 'package.ps1 -Version "${{ needs.check.outputs.version }}"' in wf
    assert "needs: [check, images, windows]" in wf  # the Release waits for every artifact


def test_release_attaches_the_exe_and_its_checksum_next_to_the_zip() -> None:
    """The Release carries TITAN.exe and TITAN.exe.sha256 as their own files, not only inside the zip."""
    wf = (_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert any(line.strip() == "dist/TITAN.exe" for line in wf.splitlines())
    assert "dist/TITAN.exe.sha256" in wf
    assert 'assets=("${zip}" TITAN.exe TITAN.exe.sha256)' in wf
    assert 'gh release upload "${GITHUB_REF_NAME}" "${assets[@]}" --clobber' in wf
    assert 'gh release create "${GITHUB_REF_NAME}" "${assets[@]}"' in wf


# ── RE-04 ───────────────────────────────────────────────────────────────────


def test_release_compose_pins_registry_images_and_never_builds() -> None:
    release = (_ROOT / "docker-compose.release.yml").read_text(encoding="utf-8")
    services = release.split("services:", 1)[1]
    for name in ("titan-api", "titan-worker"):
        block = services.split(f"  {name}:", 1)[1].split("\n  titan-", 1)[0]
        assert "build: !reset null" in block
        assert f"image: ghcr.io/zafiriss-ux/{name}:${{TITAN_VERSION:?" in block


def _worker_volume_mounts(compose_text: str) -> list[str]:
    """The `- source:target` lines under titan-worker's `volumes:` key."""
    worker = compose_text.split("\n  titan-worker:", 1)[1].split("\n  titan-", 1)[0]
    lines = worker.split("\n    volumes:", 1)[1].splitlines()[1:]
    mounts: list[str] = []
    for line in lines:
        if not line.startswith("      - "):
            break
        mounts.append(line.removeprefix("      - ").strip())
    return mounts


def test_release_worker_keeps_every_named_volume_of_the_base_compose() -> None:
    """M0-04: `volumes: !override` replaces the whole list, so a named volume left
    out of the release file is lost in production. Losing titan-secrets means a new
    token key (stored Garmin tokens become unreadable) and an empty deletion record
    (a restore could bring back deleted athletes, P4-08). Only the host bind of
    ./scripts is meant to be dropped: the released image carries its own copy."""
    base = _worker_volume_mounts((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    release = _worker_volume_mounts(
        (_ROOT / "docker-compose.release.yml").read_text(encoding="utf-8")
    )
    named = [m for m in base if not m.startswith((".", "/"))]
    assert "titan-secrets:/secrets" in named
    missing = [m for m in named if m not in release]
    assert not missing, f"release compose drops worker volumes: {missing}"
    assert not [m for m in release if m.startswith((".", "/"))], "release must not bind host paths"


# ── RE-03 ───────────────────────────────────────────────────────────────────


def test_rollback_runbook_covers_required_parts() -> None:
    runbook = (_ROOT / "docs" / "RUNBOOK_ROLLBACK.md").read_text(encoding="utf-8")
    assert "git tag --sort=-v:refname" in runbook  # prior-tag identification
    assert "TITAN_VERSION" in runbook  # image/tag rollback
    assert "/readyz" in runbook  # success verification
    assert "RUNBOOK_DR.md" in runbook  # data rollback strategy: backup restore
