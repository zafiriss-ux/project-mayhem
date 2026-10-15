"""Shared helpers for the DB stress harness: latency stats, resource sampling, log capture.

Only standard library is required. psutil is used when installed (better RSS/CPU
numbers, child processes included); otherwise the ``resource`` module is used.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import statistics
import threading
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

try:  # optional
    import psutil
except ModuleNotFoundError:  # pragma: no cover - depends on environment
    psutil = None


def pct(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile (p in 0..100). Returns None for an empty list."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * len(s) + 0.5)) - 1))
    return s[k]


def latency_summary(ms: list[float]) -> dict:
    """p50/p95/p99/max/mean of a list of millisecond latencies."""
    if not ms:
        return {"n": 0}
    return {
        "n": len(ms),
        "p50_ms": round(pct(ms, 50), 3),
        "p95_ms": round(pct(ms, 95), 3),
        "p99_ms": round(pct(ms, 99), 3),
        "max_ms": round(max(ms), 3),
        "mean_ms": round(statistics.fmean(ms), 3),
    }


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def sqlite_storage(db_path: Path) -> dict:
    """Size of the SQLite main file plus its -wal / -shm side files."""
    main = file_size(db_path)
    wal = file_size(Path(str(db_path) + "-wal"))
    shm = file_size(Path(str(db_path) + "-shm"))
    return {"db_bytes": main, "wal_bytes": wal, "shm_bytes": shm, "total_bytes": main + wal + shm}


class ResourceSampler:
    """Background sampler of RSS and CPU for this process (+children) and optional extra pids.

    ``extra_proc_names`` lets the PostgreSQL phase include the server processes.
    """

    def __init__(self, interval: float = 0.25, extra_proc_names: tuple[str, ...] = ()) -> None:
        self.interval = interval
        self.extra_proc_names = extra_proc_names
        self._rss: list[int] = []
        self._cpu: list[float] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._t0 = 0.0
        self._cpu0 = 0.0

    def _procs(self):
        me = psutil.Process(os.getpid())
        procs = [me]
        with contextlib.suppress(psutil.Error):
            procs += me.children(recursive=True)
        if self.extra_proc_names:
            for p in psutil.process_iter(["name"]):
                try:
                    if p.info["name"] in self.extra_proc_names:
                        procs.append(p)
                except psutil.Error:
                    continue
        return procs

    def _sample(self) -> None:
        if psutil is None:
            import resource
            self._rss.append(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
            return
        rss = 0
        cpu = 0.0
        for p in self._procs():
            try:
                rss += p.memory_info().rss
                cpu += p.cpu_percent(None)
            except psutil.Error:
                continue
        self._rss.append(rss)
        self._cpu.append(cpu)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._sample()

    def start(self) -> ResourceSampler:
        self._t0 = time.perf_counter()
        self._cpu0 = _proc_cpu_seconds()
        if psutil is not None:
            for p in self._procs():  # prime cpu_percent
                try:
                    p.cpu_percent(None)
                except psutil.Error:
                    continue
        self._sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join()
        self._sample()
        wall = time.perf_counter() - self._t0
        cpu_s = _proc_cpu_seconds() - self._cpu0
        out = {
            "wall_s": round(wall, 3),
            "rss_max_mb": round(max(self._rss) / 2**20, 1) if self._rss else None,
            "rss_mean_mb": round(statistics.fmean(self._rss) / 2**20, 1) if self._rss else None,
            "cpu_self_seconds": round(cpu_s, 2),
            "cpu_self_pct_of_one_core": round(100 * cpu_s / wall, 1) if wall > 0 else None,
        }
        if self._cpu:
            out["cpu_sampled_mean_pct"] = round(statistics.fmean(self._cpu), 1)
            out["cpu_sampled_max_pct"] = round(max(self._cpu), 1)
        out["sampler"] = "psutil" if psutil is not None else "resource(ru_maxrss)"
        return out


def _proc_cpu_seconds() -> float:
    t = os.times()
    return t.user + t.system + t.children_user + t.children_system


@contextmanager
def measured(store: dict, key: str, extra_proc_names: tuple[str, ...] = ()):
    """Context manager that records resource usage of a block into store[key]['resources']."""
    sampler = ResourceSampler(extra_proc_names=extra_proc_names).start()
    entry = store.setdefault(key, {})
    try:
        yield entry
    finally:
        entry["resources"] = sampler.stop()


class JsonActionCounter(logging.Handler):
    """Counts structured JSON log lines by their 'action' field (data_sanity_*, bounds_violation)."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.counts: Counter = Counter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if msg.startswith("{"):
                payload = json.loads(msg)
                key = payload.get("action") or payload.get("event") or "json_other"
                rule = payload.get("rule") or payload.get("field")
                self.counts[f"{key}:{rule}" if rule else key] += 1
            else:
                self.counts["text:" + record.name] += 1
        except (ValueError, TypeError):
            self.counts["unparsed"] += 1


def setup_logging(out_dir: Path) -> JsonActionCounter:
    """Route WARNING+ logs to a file in out_dir and count structured actions."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.WARNING)
    fh = logging.FileHandler(out_dir / "titan_warnings.log", mode="w")
    fh.setLevel(logging.WARNING)
    root.addHandler(fh)
    counter = JsonActionCounter()
    root.addHandler(counter)
    return counter
