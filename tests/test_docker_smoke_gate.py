"""T-PRA-29 (D-2): the compose smoke test runs in CI and restarts both containers."""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_ci_runs_the_compose_smoke_test() -> None:
    wf = (_ROOT / ".github" / "workflows" / "docker-smoke.yml").read_text(encoding="utf-8")
    assert "run: bash scripts/docker_smoke_test.sh" in wf
    assert 'branches: ["main"]' in wf


@pytest.mark.unit
def test_smoke_test_restarts_both_containers_and_checks_the_worker() -> None:
    script = (_ROOT / "scripts" / "docker_smoke_test.sh").read_text(encoding="utf-8")
    assert "\n$COMPOSE restart\n" in script
    assert "worker not running after restart" in script
    assert "/readyz" in script
    assert "Persistence FAILED" in script
