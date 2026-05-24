"""TITAN OS — Pure-Python load test runner (stdlib only, no external deps).

Usage:
    python3 scripts/load_test.py --url http://localhost:8000 [--json-output /tmp/results.json]
"""

from __future__ import annotations

import argparse
import http.client
import json
import sqlite3
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass


@dataclass
class LoadTestResult:
    endpoint: str
    total_requests: int
    successful: int
    failed: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    req_per_sec: float
    error_rate_percent: float


class LoadTestRunner:
    def __init__(
        self,
        base_url: str,
        jwt_token: str | None = None,
        concurrency: int = 10,
        duration_seconds: int = 30,
    ) -> None:
        self.base_url = base_url
        self.jwt_token = jwt_token
        self.concurrency = concurrency
        self.duration_seconds = duration_seconds
        parsed = urllib.parse.urlparse(base_url)
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or 8000

    def _make_request(self, path: str) -> tuple[bool, float]:
        t0 = time.monotonic()
        success = False
        conn = http.client.HTTPConnection(self._host, self._port, timeout=5)
        try:
            headers: dict[str, str] = {}
            if self.jwt_token:
                headers["Authorization"] = f"Bearer {self.jwt_token}"
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            resp.read()
            success = 200 <= resp.status < 400
        except Exception:
            pass
        finally:
            conn.close()
        return success, (time.monotonic() - t0) * 1000

    def _run_http_scenario(
        self,
        path: str,
        concurrency: int,
        duration: int,
    ) -> LoadTestResult:
        results: list[tuple[bool, float]] = []
        lock = threading.Lock()
        stop_event = threading.Event()

        def worker() -> None:
            while not stop_event.is_set():
                ok, latency = self._make_request(path)
                with lock:
                    results.append((ok, latency))

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrency)]
        t_start = time.monotonic()
        for t in threads:
            t.start()
        time.sleep(duration)
        stop_event.set()
        for t in threads:
            t.join(timeout=2)
        elapsed = time.monotonic() - t_start

        total = len(results)
        if total == 0:
            return LoadTestResult(
                endpoint=path,
                total_requests=0,
                successful=0,
                failed=0,
                p50_ms=0.0,
                p95_ms=0.0,
                p99_ms=0.0,
                req_per_sec=0.0,
                error_rate_percent=100.0,
            )

        successful = sum(1 for ok, _ in results if ok)
        failed = total - successful
        latencies = sorted(lat for _, lat in results)
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        return LoadTestResult(
            endpoint=path,
            total_requests=total,
            successful=successful,
            failed=failed,
            p50_ms=p50,
            p95_ms=p95,
            p99_ms=p99,
            req_per_sec=total / elapsed,
            error_rate_percent=(failed / total) * 100,
        )

    def run(self) -> LoadTestResult:
        """Fire concurrent requests for duration_seconds.

        Collects p50, p95, p99 latency, error rate, req/sec.
        Returns LoadTestResult dataclass.
        """
        return self._run_http_scenario("/health", self.concurrency, self.duration_seconds)

    def run_db_scenario(self, db: object) -> LoadTestResult:
        """Concurrent DatabaseManager get_training_load_history() stress test (no HTTP).

        SLO: 0 sqlite3.OperationalError across all threads.
        """
        errors: list[str] = []
        latencies: list[float] = []
        lock = threading.Lock()
        stop_event = threading.Event()

        def worker() -> None:
            while not stop_event.is_set():
                t0 = time.monotonic()
                try:
                    db.get_training_load_history()  # type: ignore[union-attr]
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    with lock:
                        latencies.append(elapsed_ms)
                except sqlite3.OperationalError as exc:
                    with lock:
                        errors.append(str(exc))

        threads = [
            threading.Thread(target=worker, daemon=True) for _ in range(self.concurrency)
        ]
        t_start = time.monotonic()
        for t in threads:
            t.start()
        time.sleep(self.duration_seconds)
        stop_event.set()
        for t in threads:
            t.join(timeout=2)
        elapsed_total = time.monotonic() - t_start

        total = len(latencies) + len(errors)
        if total == 0:
            return LoadTestResult(
                endpoint="db:get_training_load_history",
                total_requests=0,
                successful=0,
                failed=0,
                p50_ms=0.0,
                p95_ms=0.0,
                p99_ms=0.0,
                req_per_sec=0.0,
                error_rate_percent=0.0,
            )

        failed = len(errors)
        successful = len(latencies)
        sorted_lat = sorted(latencies) if latencies else [0.0]
        p50 = sorted_lat[int(len(sorted_lat) * 0.50)]
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)]

        return LoadTestResult(
            endpoint="db:get_training_load_history",
            total_requests=total,
            successful=successful,
            failed=failed,
            p50_ms=p50,
            p95_ms=p95,
            p99_ms=p99,
            req_per_sec=total / elapsed_total,
            error_rate_percent=(failed / total) * 100,
        )


def check_health_slo(result: LoadTestResult) -> bool:
    """SLO: GET /health p95 < 50ms and error_rate < 1%."""
    return result.p95_ms < 50.0 and result.error_rate_percent < 1.0


def check_readyz_slo(result: LoadTestResult) -> bool:
    """SLO: GET /readyz p95 < 200ms and error_rate < 1%."""
    return result.p95_ms < 200.0 and result.error_rate_percent < 1.0


def check_throughput_slo(result: LoadTestResult) -> bool:
    """SLO: API throughput > 100 req/sec and error_rate < 2%."""
    return result.req_per_sec > 100.0 and result.error_rate_percent < 2.0


def check_db_slo(result: LoadTestResult) -> bool:
    """SLO: 0 sqlite3.OperationalError under concurrent load."""
    return result.failed == 0


def scenario_health_check(runner: LoadTestRunner) -> tuple[LoadTestResult, bool]:
    """GET /health — concurrency 20, duration 10s, SLO: p95 < 50ms, error < 1%."""
    r = runner._run_http_scenario("/health", 20, 10)
    return r, check_health_slo(r)


def scenario_readyz(runner: LoadTestRunner) -> tuple[LoadTestResult, bool]:
    """GET /readyz — concurrency 10, duration 10s, SLO: p95 < 200ms, error < 1%."""
    r = runner._run_http_scenario("/readyz", 10, 10)
    return r, check_readyz_slo(r)


def scenario_api_throughput(runner: LoadTestRunner) -> tuple[LoadTestResult, bool]:
    """GET /health — concurrency 50, duration 20s, SLO: req/s > 100, error < 2%."""
    r = runner._run_http_scenario("/health", 50, 20)
    return r, check_throughput_slo(r)


def _print_table(results: list[tuple[str, LoadTestResult, bool]]) -> None:
    header = "{:<30} {:>8} {:>8} {:>8} {:>10} {:>8} {:>6}".format(
        "Scenario", "p50ms", "p95ms", "p99ms", "req/s", "err%", "SLO"
    )
    print(f"\n{header}")
    print("-" * 82)
    for name, r, passed in results:
        print(
            "{:<30} {:>8.1f} {:>8.1f} {:>8.1f} {:>10.1f} {:>7.2f}% {:>6}".format(
                name,
                r.p50_ms,
                r.p95_ms,
                r.p99_ms,
                r.req_per_sec,
                r.error_rate_percent,
                "PASS" if passed else "FAIL",
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TITAN OS Load Test Runner")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--json-output", default=None)
    args = parser.parse_args()

    runner = LoadTestRunner(
        base_url=args.url,
        concurrency=args.concurrency,
        duration_seconds=args.duration,
    )

    all_results: list[tuple[str, LoadTestResult, bool]] = []
    slo_violations = 0

    r_health, passed_health = scenario_health_check(runner)
    all_results.append(("health_check", r_health, passed_health))
    if not passed_health:
        slo_violations += 1

    r_readyz, passed_readyz = scenario_readyz(runner)
    all_results.append(("readyz", r_readyz, passed_readyz))
    if not passed_readyz:
        slo_violations += 1

    r_throughput, passed_throughput = scenario_api_throughput(runner)
    all_results.append(("api_throughput", r_throughput, passed_throughput))
    if not passed_throughput:
        slo_violations += 1

    _print_table(all_results)

    if args.json_output:
        output = {
            "scenarios": [
                {
                    "name": name,
                    "endpoint": r.endpoint,
                    "total_requests": r.total_requests,
                    "successful": r.successful,
                    "failed": r.failed,
                    "p50_ms": r.p50_ms,
                    "p95_ms": r.p95_ms,
                    "p99_ms": r.p99_ms,
                    "req_per_sec": r.req_per_sec,
                    "error_rate_percent": r.error_rate_percent,
                    "slo_passed": passed,
                }
                for name, r, passed in all_results
            ],
            "slo_violations": slo_violations,
        }
        with open(args.json_output, "w") as f:
            json.dump(output, f, indent=2)

    if slo_violations > 0:
        print(f"\n❌ {slo_violations} SLO violation(s) detected")
        sys.exit(1)
    else:
        print("\n✅ All SLOs passed")
