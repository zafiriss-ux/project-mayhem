"""
Structured metrics sink for TITAN OS.

Phase 18: logs to structured JSON via stdlib logging.
Phase 19: pluggable OTel exporter via ADR.
Phase 22: dual-emit — JSON log + Prometheus (TD-OBS).

Usage:
    metrics = get_metrics()
    metrics.counter("garmin_sync_runs")
    metrics.gauge("tsb_value", -3.2, labels={"athlete": "owner"})
    metrics.histogram("ctl_recompute_ms", 142.0)
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from prometheus_client import Counter, Gauge, Histogram

# Prometheus instruments — defined at module level so make_asgi_app() picks them up.
_CTL_RECOMPUTE = Histogram(
    "titan_ctl_recompute_ms",
    "CTL recomputation latency ms",
    buckets=[1, 5, 10, 50, 100, 500, 1000],
)

_TSB_GAUGE = Gauge(
    "titan_tsb_value",
    "Current TSB (form)",
    ["athlete"],
)

_GARMIN_SYNC = Counter(
    "titan_garmin_sync_total",
    "Garmin sync completions",
    ["athlete", "status"],
)

_API_STARTUP = Counter(
    "titan_api_startup_total",
    "API startup events",
)

_AUDIT_FAIL = Counter(
    "titan_audit_write_failure_total",
    "Coach audit write failures",
)


class MetricsCollector:
    def __init__(self, sink: str = "log") -> None:
        self._sink = sink
        self._logger = logging.getLogger("titan.metrics")

    def counter(
        self,
        name: str,
        value: int = 1,
        labels: dict | None = None,
    ) -> None:
        self._emit("counter", name, value, labels)
        _COUNTERS = {
            "garmin_sync_success": _GARMIN_SYNC,
            "api_startup": _API_STARTUP,
            "audit_write_failure": _AUDIT_FAIL,
        }
        if name in _COUNTERS:
            c = _COUNTERS[name]
            if name == "garmin_sync_success":
                athlete = (labels or {}).get("athlete", "owner")
                c.labels(athlete=athlete, status="success").inc()
            else:
                c.inc()

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict | None = None,
    ) -> None:
        self._emit("gauge", name, value, labels)
        if name == "tsb_value":
            athlete = (labels or {}).get("athlete", "owner")
            _TSB_GAUGE.labels(athlete=athlete).set(value)

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict | None = None,
    ) -> None:
        self._emit("histogram", name, value, labels)
        if name == "ctl_recompute_ms":
            _CTL_RECOMPUTE.observe(value)

    def _emit(
        self,
        metric_type: str,
        name: str,
        value: float | int,
        labels: dict | None,
    ) -> None:
        record = {
            "metric_type": metric_type,
            "name": name,
            "value": value,
            "labels": labels or {},
            "ts": datetime.now(UTC).isoformat(),
        }
        self._logger.info(json.dumps(record))


_collector: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
