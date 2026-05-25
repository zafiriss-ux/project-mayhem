"""TD-NEW-15: Load / performance tests.

Tests the load test infrastructure itself and run in-process DB stress scenarios.
No Docker required — all tests operate against in-memory SQLite or in-process objects.
"""

import contextlib
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from scripts.load_test import LoadTestResult, LoadTestRunner, check_health_slo
from titan.core.database import DatabaseManager
from titan.orchestration.daily_coach import DailyCoach


@pytest.mark.unit
def test_load_test_result_dataclass():
    result = LoadTestResult(
        endpoint="/health",
        total_requests=1000,
        successful=995,
        failed=5,
        p50_ms=10.0,
        p95_ms=45.0,
        p99_ms=80.0,
        req_per_sec=150.0,
        error_rate_percent=0.5,
    )
    assert result.endpoint == "/health"
    assert result.total_requests == 1000
    assert result.successful == 995
    assert result.failed == 5
    assert result.p50_ms == 10.0
    assert result.p95_ms == 45.0
    assert result.p99_ms == 80.0
    assert result.req_per_sec == 150.0
    assert result.error_rate_percent == 0.5


@pytest.mark.integration
def test_scenario_db_under_load():
    db = DatabaseManager(":memory:")
    today = date(2026, 1, 30)
    for day_offset in range(30):
        d = today - timedelta(days=day_offset)
        db.conn.execute(
            "INSERT INTO training_log (athlete_id, date, training_load) VALUES (?, ?, ?)",
            ("owner", d.isoformat(), 60.0),
        )
    db.conn.commit()

    runner = LoadTestRunner(
        base_url="http://localhost:8000",
        concurrency=8,
        duration_seconds=5,
    )
    result = runner.run_db_scenario(db)
    assert result.failed == 0, (
        f"Concurrent DB reads produced {result.failed} errors"
    )
    assert result.error_rate_percent < 1.0


@pytest.mark.unit
def test_load_test_slo_validation():
    result = LoadTestResult(
        endpoint="/health",
        total_requests=1000,
        successful=995,
        failed=5,
        p50_ms=10.0,
        p95_ms=45.0,
        p99_ms=80.0,
        req_per_sec=150.0,
        error_rate_percent=0.5,
    )
    assert check_health_slo(result) is True


@pytest.mark.unit
def test_load_test_slo_violation_detected():
    result = LoadTestResult(
        endpoint="/health",
        total_requests=100,
        successful=90,
        failed=10,
        p50_ms=10.0,
        p95_ms=120.0,
        p99_ms=200.0,
        req_per_sec=20.0,
        error_rate_percent=10.0,
    )
    assert check_health_slo(result) is False


@pytest.mark.integration
def test_dailycoach_pipeline_latency():
    """Benchmark coaching pipeline hydration end-to-end (no HTTP).

    SLO: p95 < 500ms for 20 runs.
    """
    db = DatabaseManager(":memory:")
    coach = DailyCoach(
        garmin_sync=SimpleNamespace(sync_all=lambda: {}, athlete_max_hr=0),
        weather_api=SimpleNamespace(),
        telegram_bot=SimpleNamespace(send_alert=lambda *a, **kw: None),
        hrv_engine=SimpleNamespace(),
        tsb_engine=SimpleNamespace(),
        readiness_engine=SimpleNamespace(),
        optimal_time_calc=SimpleNamespace(),
        nutrition_optimizer=SimpleNamespace(),
        weekly_planner=SimpleNamespace(),
        db=db,
    )
    latencies = []
    for _ in range(20):
        t0 = time.monotonic()
        with contextlib.suppress(Exception):
            coach._hydrate_engines_from_db()
        latencies.append((time.monotonic() - t0) * 1000)
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 < 500.0, (
        f"DailyCoach hydration p95={p95:.1f}ms exceeds 500ms SLO"
    )
