"""
Structured metrics sink for TITAN OS.

Phase 18: logs to structured JSON via stdlib logging.
Phase 19: pluggable OTel exporter via ADR.

Usage:
    metrics = get_metrics()
    metrics.counter("garmin_sync_runs")
    metrics.gauge("tsb_value", -3.2, labels={"athlete": "owner"})
    metrics.histogram("ctl_recompute_ms", 142.0)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime


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

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict | None = None,
    ) -> None:
        self._emit("gauge", name, value, labels)

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict | None = None,
    ) -> None:
        self._emit("histogram", name, value, labels)

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
            "ts": datetime.utcnow().isoformat() + "Z",
        }
        self._logger.info(json.dumps(record))


_collector: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
