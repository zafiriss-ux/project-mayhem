"""
Concurrency and restart-survival tests.

CC-01  DegradedModeTracker restart survival  — raw DB persistence mechanics
CC-02  Rate limiter ceiling under load        — LRU eviction under concurrent injection
CC-03  Concurrent athlete writes no collision — thread-safe SQLite writes
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from unittest.mock import MagicMock

import pytest

from titan.config.thresholds import RATE_LIMITER_MAX_KEYS
from titan.orchestration.coaching_pipeline import AthleteCoachingContext, coaching_pipeline
from titan.orchestration.daily_coach import DegradedModeTracker


def _days_ago(n: int) -> str:
    """A date inside the "last N days" window of the history reads (F5, D-072)."""
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(days=n)).strftime("%Y-%m-%d")

# ─────────────────────────────────────────────────────────────────────────────
# CC-01 — DegradedModeTracker restart survival (raw DB mechanics)
# ─────────────────────────────────────────────────────────────────────────────

class TestDegradedTrackerSurvivesRestart:
    """
    Directly verify that writing degraded_since to the degraded_mode_state
    table and re-instantiating DegradedModeTracker restores the timestamp.

    This test focuses on the raw persistence path rather than the high-level
    alert logic (FS-07 covers that layer).
    """

    @pytest.mark.integration
    def test_persisted_degraded_since_hydrated_on_reinstantiation(
        self, db_manager_factory: Any
    ) -> None:
        """
        CC-01-A: Write degraded_since=T directly via DB API.
        Re-instantiate DegradedModeTracker — _degraded_since[failure_type] must equal T.
        """
        db = db_manager_factory()
        failure_type = "DATA_MISSING"
        start_time = datetime.now(UTC) - timedelta(hours=3)
        db.upsert_degraded_mode_state(failure_type, start_time.isoformat())

        # Simulate process restart.
        fresh_tracker = DegradedModeTracker(db=db)

        assert failure_type in fresh_tracker._degraded_since, (
            "DegradedModeTracker must hydrate failure_type from DB on __init__"
        )
        restored = fresh_tracker._degraded_since[failure_type]
        delta = abs(
            (restored.replace(tzinfo=UTC) - start_time).total_seconds()
        )
        assert delta < 2.0, (
            f"Restored timestamp must match persisted value within 2s; delta={delta:.2f}s"
        )

    @pytest.mark.integration
    def test_multiple_failure_types_all_hydrated(
        self, db_manager_factory: Any
    ) -> None:
        """
        CC-01-B: Multiple failure_types persisted — all must be present after restart.
        """
        db = db_manager_factory()
        failure_types = ["GARMIN_SYNC", "WEATHER_SYNC", "DATA_MISSING"]
        base_time = datetime.now(UTC)

        for i, ft in enumerate(failure_types):
            ts = base_time - timedelta(hours=i + 1)
            db.upsert_degraded_mode_state(ft, ts.isoformat())

        tracker = DegradedModeTracker(db=db)

        for ft in failure_types:
            assert ft in tracker._degraded_since, (
                f"Failure type '{ft}' must be hydrated from DB after restart"
            )

    @pytest.mark.integration
    def test_no_db_tracker_starts_empty(self) -> None:
        """
        CC-01-C: DegradedModeTracker(db=None) must start with empty _degraded_since.
        """
        tracker = DegradedModeTracker(db=None)
        assert tracker._degraded_since == {}, (
            "No-DB tracker must start with empty _degraded_since dict"
        )

    @pytest.mark.integration
    def test_tracker_update_persists_new_failure(
        self, db_manager_factory: Any
    ) -> None:
        """
        CC-01-D: A newly degraded failure_type is persisted so the next
        restart also sees it.
        """
        db = db_manager_factory()
        tracker = DegradedModeTracker(db=db)

        tracker.update(
            flags={"GARMIN_SYNC": True},
            alert_fn=lambda _: None,
        )

        # Direct DB verification.
        rows = db.get_all_degraded_mode_states()
        failure_types_in_db = {r[0] for r in rows}
        assert "GARMIN_SYNC" in failure_types_in_db, (
            "Newly degraded failure type must be persisted to DB immediately"
        )

    @pytest.mark.integration
    def test_tracker_update_removes_resolved_failure_from_db(
        self, db_manager_factory: Any
    ) -> None:
        """
        CC-01-E: Resolving a failure_type (flag=False) must delete it from DB
        so a subsequent restart does not spuriously resurrect it.
        """
        db = db_manager_factory()
        # Persist a failure first.
        db.upsert_degraded_mode_state("WEATHER_SYNC", datetime.now(UTC).isoformat())

        tracker = DegradedModeTracker(db=db)
        assert "WEATHER_SYNC" in tracker._degraded_since

        # Resolve it.
        tracker.update(
            flags={"WEATHER_SYNC": False},
            alert_fn=lambda _: None,
        )

        # Simulate restart.
        fresh_tracker = DegradedModeTracker(db=db)
        assert "WEATHER_SYNC" not in fresh_tracker._degraded_since, (
            "Resolved failure type must not reappear after restart"
        )


# ─────────────────────────────────────────────────────────────────────────────
# CC-02 — Rate limiter ceiling under load
# ─────────────────────────────────────────────────────────────────────────────

class TestRateLimiterCeilingUnderLoad:
    """
    AuthenticatedRateLimiter must not grow beyond RATE_LIMITER_MAX_KEYS keys
    even when driven by RATE_LIMITER_MAX_KEYS + 100 unique (user, path) pairs.

    Requires fastapi; skipped when not installed.
    """

    @staticmethod
    def _make_limiter():
        pytest.importorskip("fastapi", reason="fastapi not installed")
        from titan.api.main import AuthenticatedRateLimiter, RateLimitConfig  # noqa: PLC0415
        return AuthenticatedRateLimiter(
            config=RateLimitConfig(coach_per_minute=100, athlete_per_minute=30)
        )

    @staticmethod
    def _inject_key(limiter: Any, key: tuple, ts: float) -> None:
        """Bypass auth and inject a key directly (mirrors existing test pattern)."""
        limiter._requests[key].append(ts)

    @pytest.mark.integration
    def test_key_count_never_exceeds_ceiling_after_eviction(self) -> None:
        """
        CC-02-A: Inject RATE_LIMITER_MAX_KEYS + 100 unique keys then evict.
        len(requests) must be ≤ RATE_LIMITER_MAX_KEYS.
        """
        limiter = self._make_limiter()
        now = monotonic()
        excess = 100
        total = RATE_LIMITER_MAX_KEYS + excess

        for i in range(total):
            key = (f"user-{i}", "ATHLETE", f"GET:/path/{i}")
            self._inject_key(limiter, key, now + i)

        limiter._evict_lru_keys()

        assert len(limiter._requests) <= RATE_LIMITER_MAX_KEYS, (
            f"Key count after eviction must be ≤ {RATE_LIMITER_MAX_KEYS}, "
            f"got {len(limiter._requests)}"
        )

    @pytest.mark.integration
    def test_eviction_event_emitted_at_ceiling(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        CC-02-B: _evict_lru_keys must emit a 'limiter_eviction' WARNING event.
        """
        limiter = self._make_limiter()
        now = monotonic()

        for i in range(RATE_LIMITER_MAX_KEYS + 5):
            key = (f"u-{i}", "ATHLETE", f"GET:/p/{i}")
            self._inject_key(limiter, key, now + i)

        with caplog.at_level(logging.WARNING, logger="titan.api.main"):
            limiter._evict_lru_keys()

        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_records, "Expected at least one WARNING log when eviction fires"

        payload = json.loads(warning_records[0].getMessage())
        assert payload.get("action") == "limiter_eviction", (
            f"Expected action='limiter_eviction', got {payload.get('action')!r}"
        )
        assert payload.get("keys_evicted", 0) >= 5

    @pytest.mark.integration
    def test_no_memory_error_or_unhandled_exception_at_ceiling(self) -> None:
        """
        CC-02-C: RATE_LIMITER_MAX_KEYS + 100 injections must not raise any exception.
        """
        limiter = self._make_limiter()
        now = monotonic()
        # Must not raise MemoryError, KeyError, or any other exception.
        for i in range(RATE_LIMITER_MAX_KEYS + 100):
            key = (f"u-{i}", "ATHLETE", f"GET:/overflow/{i}")
            self._inject_key(limiter, key, now + i)
            if len(limiter._requests) > RATE_LIMITER_MAX_KEYS:
                limiter._evict_lru_keys()

        assert len(limiter._requests) <= RATE_LIMITER_MAX_KEYS

    @pytest.mark.integration
    def test_existing_keys_not_corrupted_during_eviction(self) -> None:
        """
        CC-02-D: Keys that should survive eviction retain their request history.
        """
        limiter = self._make_limiter()
        now = monotonic()

        # Anchor key with a recent timestamp — must survive eviction.
        anchor_key = ("anchor-user", "COACH", "GET:/dashboard")
        for offset in (0.0, 1.0, 2.0):
            self._inject_key(limiter, anchor_key, now + 1_000_000 + offset)

        # Fill with stale keys that should be evicted first.
        for i in range(RATE_LIMITER_MAX_KEYS):
            key = (f"old-u-{i}", "ATHLETE", f"GET:/old/{i}")
            self._inject_key(limiter, key, now - (RATE_LIMITER_MAX_KEYS - i))

        limiter._evict_lru_keys()

        assert anchor_key in limiter._requests, (
            "Recent anchor key must survive LRU eviction"
        )
        assert len(limiter._requests[anchor_key]) == 3, (
            "Anchor key request history must not be mutated during eviction"
        )


# ─────────────────────────────────────────────────────────────────────────────
# CC-03 — Concurrent athlete writes no collision
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrentAthleteWritesNoCollision:
    """
    Two threads writing daily_metrics for different dates to a shared
    DatabaseManager must not collide or corrupt each other's data.

    TITAN OS is single-athlete per DatabaseManager but the DB itself is
    accessed from multiple threads (Garmin sync, scheduler, DailyCoach).
    """

    @pytest.mark.integration
    def test_two_threads_write_different_dates_no_collision(
        self, db_manager_factory: Any
    ) -> None:
        """
        CC-03-A: Two threads write daily_metrics for different dates.
        Each date's row must have the correct values; no cross-thread contamination.
        """
        db = db_manager_factory()
        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def write_date_a() -> None:
            try:
                barrier.wait()
                db.save_daily_metric(
                    date=_days_ago(2),
                    hrv=60.0,
                    rhr=48,
                    sleep_hours=7.5,
                    sleep_quality=80,
                )
            except Exception as exc:
                errors.append(exc)

        def write_date_b() -> None:
            try:
                barrier.wait()
                db.save_daily_metric(
                    date=_days_ago(1),
                    hrv=55.0,
                    rhr=52,
                    sleep_hours=6.0,
                    sleep_quality=60,
                )
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=write_date_a, name="writer-A")
        t2 = threading.Thread(target=write_date_b, name="writer-B")
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        assert not errors, f"Thread errors during concurrent writes: {errors}"

        # Verify each date stored the correct values.
        hrv_rows = dict(db.get_hrv_history(days=10))
        assert _days_ago(2) in hrv_rows, "Date A row must be present after concurrent write"
        assert _days_ago(1) in hrv_rows, "Date B row must be present after concurrent write"
        assert hrv_rows[_days_ago(2)] == pytest.approx(60.0, abs=0.01), (
            "Date A HRV value must not be contaminated by date B's write"
        )
        assert hrv_rows[_days_ago(1)] == pytest.approx(55.0, abs=0.01), (
            "Date B HRV value must not be contaminated by date A's write"
        )

    @pytest.mark.integration
    def test_concurrent_writes_same_date_last_write_wins(
        self, db_manager_factory: Any
    ) -> None:
        """
        CC-03-B: Two threads writing the same date must not raise IntegrityError.
        The UPSERT semantics ensure the last writer wins without row duplication.
        """
        db = db_manager_factory()
        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def writer_1() -> None:
            try:
                barrier.wait()
                db.save_daily_metric(date=_days_ago(1), hrv=60.0, rhr=48)
            except Exception as exc:
                errors.append(exc)

        def writer_2() -> None:
            try:
                barrier.wait()
                db.save_daily_metric(date=_days_ago(1), hrv=58.0, rhr=50)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=writer_1, name="writer-1")
        t2 = threading.Thread(target=writer_2, name="writer-2")
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        assert not errors, (
            f"Concurrent same-date writes must not raise; errors: {errors}"
        )

        # Exactly one row for that date.
        hrv_rows = dict(db.get_hrv_history(days=30))
        assert _days_ago(1) in hrv_rows, "Row must exist after concurrent same-date write"
        # Value must be one of the two written values (last-write-wins UPSERT).
        assert hrv_rows[_days_ago(1)] in (
            pytest.approx(60.0, abs=0.01),
            pytest.approx(58.0, abs=0.01),
        ), (
            f"HRV value must be one of the two written values, got {hrv_rows['2026-03-01']}"
        )

    @pytest.mark.integration
    def test_high_concurrency_no_db_operational_error(
        self, db_manager_factory: Any
    ) -> None:
        """
        CC-03-C: 10 concurrent threads each writing a different date must all
        succeed without sqlite3.OperationalError or ProgrammingError.
        """
        import sqlite3

        db = db_manager_factory()
        errors: list[Exception] = []
        n_threads = 10
        barrier = threading.Barrier(n_threads)

        def worker(thread_idx: int) -> None:
            try:
                barrier.wait()
                date = _days_ago(thread_idx + 1)
                db.save_daily_metric(
                    date=date,
                    hrv=60.0 + thread_idx,
                    rhr=48 + thread_idx,
                )
            except (sqlite3.OperationalError, sqlite3.ProgrammingError) as exc:
                errors.append(exc)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(i,), name=f"worker-{i}")
            for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        assert not errors, (
            f"Expected zero errors across {n_threads} concurrent DB writes; "
            f"got {len(errors)} error(s): {errors[:3]}"
        )

        # Verify all dates were written.
        hrv_rows = dict(db.get_hrv_history(days=30))
        for i in range(n_threads):
            date = _days_ago(i + 1)
            assert date in hrv_rows, f"Date '{date}' must be present after concurrent write"


# ─────────────────────────────────────────────────────────────────────────────
# CC-04 — coaching_pipeline() concurrent isolation
# ─────────────────────────────────────────────────────────────────────────────


class TestCoachingPipelineConcurrentIsolation:
    """
    Two concurrent coaching_pipeline() calls with different athlete contexts
    must not cross-contaminate each other's results.

    coaching_pipeline() is the ADR-0018 kernel boundary: it calls
    context.coach._decision_pipeline() then context.coach._effect_runner().
    The frozen AthleteCoachingContext dataclass binds each call to its own
    coach instance, ensuring isolation.  These tests verify that invariant
    holds under concurrent execution.
    """

    @staticmethod
    def _make_context(athlete_id: str, coach: Any) -> AthleteCoachingContext:
        garmin_data: dict[str, Any] = {
            "activities": [],
            "weight": [],
            "sleep": [],
            "hrv": [],
            "hrv_sync_metrics": {"days_back": 7, "synced_days": 7, "skipped_days": 0},
        }
        return AthleteCoachingContext(
            athlete_id=athlete_id,
            coach=coach,
            garmin_data=garmin_data,
            soreness=1,
            subjective_fatigue_score=3,
            today_rhr=52,
            today_sleep_score=78,
            today_sleep_hours=7.5,
            baseline_rhr_for_comparison=51.0,
            persistence_degraded=False,
            garmin_data_stale=False,
            latest_hrv=65.0,
            baseline_hrv=63.0,
            hrv_summary={},
            afi_final=0.1,
            afi_constraints={},
            tsb_value=5.0,
            tsb_status="OPTIMAL",
            cs_thermal=None,
            garmin_trust=None,
            garmin_report_payload={},
            startup_hydration_confidence={},
            startup_confidence_applies=False,
        )

    @pytest.mark.integration
    def test_concurrent_coaching_pipeline_no_cross_contamination(self) -> None:
        """
        CC-04-A: Two threads calling coaching_pipeline() simultaneously with
        different athlete contexts must each use their own coach mock exactly
        once — no cross-invocation between contexts.

        threading.Barrier forces both threads into _decision_pipeline at the
        same instant, guaranteeing genuinely concurrent execution rather than
        accidental sequential ordering.
        """
        barrier = threading.Barrier(2, timeout=5)
        results: dict[str, Any] = {}
        errors: list[Exception] = []

        def make_coach(athlete_id: str) -> MagicMock:
            mock_coach = MagicMock(name=f"Coach_{athlete_id}")

            def pipeline_side_effect(**kwargs: Any) -> MagicMock:
                barrier.wait()  # Both threads rendezvous here simultaneously.
                return MagicMock(name=f"DecisionResult_{athlete_id}")

            mock_coach._decision_pipeline.side_effect = pipeline_side_effect
            mock_coach._effect_runner.return_value = True
            return mock_coach

        coach_a = make_coach("athlete_A")
        coach_b = make_coach("athlete_B")
        context_a = self._make_context("athlete_A", coach_a)
        context_b = self._make_context("athlete_B", coach_b)

        def run(ctx: AthleteCoachingContext, athlete_id: str) -> None:
            try:
                results[athlete_id] = coaching_pipeline(ctx)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=run, args=(context_a, "athlete_A"), name="pipeline-A")
        t2 = threading.Thread(target=run, args=(context_b, "athlete_B"), name="pipeline-B")
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        assert not t1.is_alive(), "athlete_A pipeline thread did not complete within timeout"
        assert not t2.is_alive(), "athlete_B pipeline thread did not complete within timeout"
        assert not errors, f"Pipeline threads raised unhandled exceptions: {errors}"
        assert "athlete_A" in results, "athlete_A coaching_pipeline did not produce a result"
        assert "athlete_B" in results, "athlete_B coaching_pipeline did not produce a result"

        # Each coach must have been called exactly once — never by the other thread.
        assert coach_a._decision_pipeline.call_count == 1, (
            f"coach_a._decision_pipeline expected 1 call, "
            f"got {coach_a._decision_pipeline.call_count} — cross-contamination detected"
        )
        assert coach_b._decision_pipeline.call_count == 1, (
            f"coach_b._decision_pipeline expected 1 call, "
            f"got {coach_b._decision_pipeline.call_count} — cross-contamination detected"
        )
        coach_a._effect_runner.assert_called_once()
        coach_b._effect_runner.assert_called_once()
