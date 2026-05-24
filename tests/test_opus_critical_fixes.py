"""Fitness tests for Opus audit TR-01/03/05/06/07/11, C-1/3/5/6/7, H-3/8 fixes."""

from pathlib import Path


def test_runbook_db_name_correct() -> None:
    src = Path("docs/runbooks/database-recovery.md").read_text()
    assert "titan.db" not in src, (
        "Runbook references stale titan.db — must be titan_core.db"
    )


def test_assert_replaced_with_raise() -> None:
    src = Path("titan/api/main.py").read_text()
    assert 'assert "titan_core.db"' not in src, (
        "TR-07: assert must be replaced with raise RuntimeError"
    )


def test_readyz_uses_is_db_reachable() -> None:
    src = Path("titan/api/main.py").read_text()
    assert "_db.conn.execute" not in src or "is_db_reachable" in src, (
        "H-8: /readyz must use is_db_reachable() not direct conn access"
    )


def test_audit_handler_emits_metric() -> None:
    src = Path("titan/api/main.py").read_text()
    assert "audit_write_failure" in src, (
        "H-3: audit failure must emit metric"
    )


def test_worker_run_forever_not_stub() -> None:
    src = Path("titan/worker/__init__.py").read_text()
    assert "run_morning_routine" in src or "DailyCoach" in src, (
        "C-1: worker must wire actual work, not just sleep"
    )
    assert src.count("time.sleep") <= 1, (
        "C-1: worker looks like a stub"
    )


def test_metrics_no_utcnow() -> None:
    src = Path("titan/observability/metrics.py").read_text()
    assert "utcnow" not in src, (
        "TR-10: metrics.py must use datetime.now(timezone.utc)"
    )


def test_dockerfile_non_root() -> None:
    src = Path("Dockerfile").read_text()
    assert "USER titan" in src, (
        "TR-18: Dockerfile must run as non-root user"
    )


def test_semgrep_config_exists() -> None:
    assert Path(".semgrep/titan_rules.yaml").exists(), (
        "TR-17: semgrep config must exist"
    )
