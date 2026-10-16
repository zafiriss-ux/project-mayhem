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


@pytest.mark.unit
def test_persistence_marker_uses_the_current_sync_metadata_columns() -> None:
    """The second CI run failed: the marker used sync_metadata columns from before v4.

    v30 (ADR-0067 D3): the marker must name its athlete, or INSERT OR IGNORE drops it silently.
    """
    from titan.core.database import DatabaseManager

    script = (_ROOT / "scripts" / "docker_smoke_test.sh").read_text(encoding="utf-8")
    assert "sync_metadata (athlete_id, source, last_sync_ok, last_error_class)" in script
    assert "WHERE athlete_id='owner' AND source='smoke_test_marker'" in script
    db = DatabaseManager(db_name=":memory:")
    try:
        columns = {row[1] for row in db.conn.execute("PRAGMA table_info(sync_metadata)")}
        assert {"athlete_id", "source", "last_sync_ok", "last_error_class"} <= columns
        db.conn.execute(
            "INSERT OR IGNORE INTO sync_metadata (athlete_id, source, last_sync_ok, last_error_class) "
            "VALUES ('owner', 'smoke_test_marker', 0, 'smoke_test')"
        )
        row = db.conn.execute(
            "SELECT last_error_class FROM sync_metadata "
            "WHERE athlete_id='owner' AND source='smoke_test_marker'"
        ).fetchone()
        assert row == ("smoke_test",)
    finally:
        db.close()


@pytest.mark.unit
def test_image_can_import_titan_from_the_api_script() -> None:
    """The first CI run of the smoke test failed with ModuleNotFoundError: titan."""
    dockerfile = (_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "WORKDIR /app" in dockerfile
    assert "ENV PYTHONPATH=/app" in dockerfile
    assert 'CMD ["python", "scripts/run_api.py"]' in dockerfile
