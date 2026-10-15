#!/usr/bin/env python
"""TITAN OS database stress test — single entry point.

Examples:
    python scripts/stress/run_stress.py --seed 20261010 --athletes 10000 --out .stress_tmp/full
    python scripts/stress/run_stress.py --small --out .stress_tmp/small          # ~200 athletes
    python scripts/stress/run_stress.py --athletes 20 --tiny --skip-pg --out /tmp/x  # smoke test

Every database is created under --out (disposable) through the real DatabaseManager.
No real TITAN database (titan_core.db in the repo or ~/Documents/TITAN) is opened.
Raw results go to <out>/results.json; the SQLite files are deleted at the end unless
--keep-db is given; the PostgreSQL cluster is always stopped and deleted.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (str(REPO), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import sqlite_phases as sp  # noqa: E402
from stress_common import setup_logging, sqlite_storage  # noqa: E402

from titan.core.database import SCHEMA_VERSION  # noqa: E402


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_config(args: argparse.Namespace) -> dict:
    small = args.small or args.tiny
    n = args.athletes if args.athletes else (200 if args.small else 10_000)
    return {
        "seed": args.seed, "athletes": n, "anchor": date.fromisoformat(args.anchor),
        "small": small, "tiny": args.tiny,
        "growth_sample": 10 if args.tiny else (50 if small else 200),
        "query_sample": 10 if args.tiny else (50 if small else 300),
        "leak_sample": n if args.leak_sample is None else args.leak_sample,
        "resync_athletes": 5 if args.tiny else (50 if small else 1000),
        "conc_duration": 1.0 if args.tiny else (3.0 if small else 20.0),
        "update_count": 50 if args.tiny else (1000 if small else 20_000),
        "rollback_syncs": 20 if args.tiny else (200 if small else 1000),
        "crash_syncs": 100 if args.tiny else (1000 if small else 6000),
        "index_insert_rows": 2_000 if args.tiny else (10_000 if small else 50_000),
        "bulk_pool_rows": 12_000 if small else 100_000,
    }


def environment(db_dir: Path) -> dict:
    db, open_ms = sp.open_db(db_dir, "pragma_probe.db")
    pr = {p: db.conn.execute(f"PRAGMA {p}").fetchone()[0] for p in (
        "journal_mode", "synchronous", "busy_timeout", "foreign_keys", "user_version", "page_size",
        "cache_size", "temp_store", "mmap_size", "wal_autocheckpoint", "locking_mode")}
    indexes = list(db.conn.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND tbl_name IN "
        "('training_log','daily_metrics','athletes','gear_usage','personal_bests') ORDER BY tbl_name"))
    tl_sql = db.conn.execute("SELECT sql FROM sqlite_master WHERE name='training_log'").fetchone()[0]
    db.close()
    for f in db_dir.glob("pragma_probe.db*"):
        f.unlink()
    info = {
        "utc_start": datetime.now(UTC).isoformat(), "git_sha": _git_sha(),
        "python": sys.version.split()[0], "sqlite_library": sqlite3.sqlite_version,
        "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "schema_version_code": SCHEMA_VERSION, "pragmas_as_set_by_DatabaseManager": pr,
        "new_db_open_ms": round(open_ms, 1),
        "indexes_on_core_tables": [{"name": n, "table": t, "sql": s} for n, t, s in indexes],
        "training_log_ddl": tl_sql,
    }
    try:
        import psutil
        info["ram_total_gb"] = round(psutil.virtual_memory().total / 2**30, 1)
    except ModuleNotFoundError:
        info["ram_total_gb"] = None
    return info


def _get(d: dict, *path, default=None):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def evaluate(res: dict) -> list[dict]:
    th = json.loads((HERE / "thresholds.json").read_text())
    q = _get(res, "phase3_queries", "warm_pass", default={})
    load = res.get("phase2_main_load", {})
    conc = _get(res, "phase5_concurrency", "runs", default=[])
    ver = res.get("verification", {})
    leak = res.get("leakage", {})
    crash = _get(res, "phase6_update_rollback_restart", "crash_restart", default={})
    growth = res.get("phase7_growth", [])
    resync = _get(res, "phase4_resync", "passes", default=[])
    va = ver.get("valid_activities", {})
    vd = ver.get("valid_daily_records", {})
    values = {
        "T01": _get(q, "ctl_atl_tsb", "p95_ms"), "T02": _get(q, "ctl_atl_tsb", "p99_ms"),
        "T03": _get(q, "recent_activities_90", "p95_ms"),
        "T04": _get(q, "range_30d_raw_sql", "p95_ms"), "T05": _get(q, "hrv_history_28", "p95_ms"),
        "T06": _get(load, "sync_latency", "p95_ms"), "T07": _get(load, "sync_latency", "p99_ms"),
        "T08": sum(r["database_is_locked_errors"] for r in conc if r["workers"] <= 4) if conc else None,
        "T09": sum(abs(r["lost_or_phantom_rows"]) for r in conc) if conc else None,
        "T10": (va.get("lost", 0) + va.get("lost_in_rolled_back_sync", 0)) if va else None,
        "T11": (vd.get("lost", 0) + vd.get("lost_in_rolled_back_sync", 0)) if vd else None,
        "T12": max((p["new_training_log_rows"] for p in resync), default=None),
        "T13": (ver.get("rows_whose_payload_tag_athlete_differs_from_athlete_id", 0)
                + _get(leak, "get_recent_activities", "athletes_with_mismatch_vs_payload_tag", default=0)
                + _get(leak, "get_hrv_history", "rows_not_matching_own_ground_truth", default=0))
        if ver and leak else None,
        "T14": (0 if ver.get("integrity_check") == "ok" else 1) + ver.get("foreign_key_violations", 0)
        if ver else None,
        "T15": _get(crash, "outer_transaction", "rows_present_after_crash"),
        "T16": (sum(abs(c["rows_after_reimport"] - c["expected_rows"])
                    + abs(c["rows_after_reimport"] - c["distinct_ids_after_reimport"])
                    for c in crash.values()) if crash else None),
        "T17": round(growth[-1]["storage"]["total_bytes"] / 2**20, 1) if growth else None,
        "T18": _get(load, "resources", "rss_max_mb"),
        "T19": growth[-1]["databasemanager_open_ms"] if growth else None,
        "T20": load.get("activity_rows_per_s_persist_only"),
    }
    out = []
    for c in th["checks"]:
        v = values.get(c["id"])
        lim = c.get("limit_ms", c.get("limit_mb", c.get("limit")))
        if v is None:
            verdict = "NOT MEASURED"
        elif c["op"] == "<=":
            verdict = "PASS" if v <= lim else "FAIL"
        elif c["op"] == ">=":
            verdict = "PASS" if v >= lim else "FAIL"
        else:
            verdict = "PASS" if v == lim else "FAIL"
        out.append({**c, "observed": v, "verdict": verdict})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=20261010)
    ap.add_argument("--athletes", type=int, default=None)
    ap.add_argument("--anchor", default="2026-10-10", help="last day of the synthetic year")
    ap.add_argument("--out", required=True, help="disposable output directory")
    ap.add_argument("--small", action="store_true", help="quick run (200 athletes, shorter phases)")
    ap.add_argument("--tiny", action="store_true", help="smoke-test sizes (used by tests/stress)")
    ap.add_argument("--skip-pg", action="store_true")
    ap.add_argument("--skip-bulk", action="store_true")
    ap.add_argument("--skip-concurrency", action="store_true")
    ap.add_argument("--leak-sample", type=int, default=None,
                    help="athletes checked with get_recent_activities (default: all)")
    ap.add_argument("--keep-db", action="store_true")
    args = ap.parse_args(argv)

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "db"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    cfg = build_config(args)
    counter = setup_logging(out)
    res: dict = {"config": {**cfg, "anchor": cfg["anchor"].isoformat(),
                            "command": "python scripts/stress/run_stress.py " + " ".join(
                                sys.argv[1:] if argv is None else argv)}}
    t_start = time.perf_counter()
    timings: dict = {}

    def step(name: str, fn, *a) -> object:
        print(f"[{time.strftime('%H:%M:%S')}] {name} ...", flush=True)
        t0 = time.perf_counter()
        r = fn(*a)
        timings[name] = round(time.perf_counter() - t0, 1)
        print(f"[{time.strftime('%H:%M:%S')}] {name} done in {timings[name]} s", flush=True)
        (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
        return r

    res["environment"] = environment(work)
    if not args.skip_bulk:
        step("phase1_bulk_insert", sp.phase_bulk_insert, work, cfg, res)
    t0 = time.perf_counter()
    db, open_ms = sp.open_db(work)
    res["environment"]["fresh_stress_db_open_ms"] = round(open_ms, 1)
    state = step("phase2_main_load+phase7_growth", sp.phase_main_load, db, cfg, res, work)
    step("verify_dataset", sp.verify_dataset, db, cfg, state, res)
    step("verify_read_path_loads", sp.verify_read_path_loads, db, cfg, res)
    step("verify_leakage", sp.verify_leakage, db, cfg, res)
    step("phase4_resync", sp.phase_resync, db, cfg, res)
    db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.close()
    res["storage_after_load_and_checkpoint"] = sqlite_storage(work / sp.DB_NAME)
    step("phase3_queries", sp.phase_queries, work, cfg, res)
    step("index_cost_on_copy", sp.phase_index_cost, work, cfg, res)
    if not args.skip_concurrency:
        step("phase5_concurrency", sp.phase_concurrency, work, cfg, res)
    step("phase6_update_rollback_restart", sp.phase_update_rollback_restart, work, cfg, res)
    step("backup_restore", sp.phase_backup_restore, work, cfg, res)
    if not args.skip_pg:
        import pg_phases
        step("postgres_comparison", pg_phases.run_pg, work / sp.DB_NAME, work, cfg, res)
    _ = t0
    res["log_action_counts"] = dict(counter.counts.most_common())
    res["phase_wall_s"] = timings
    res["total_wall_s"] = round(time.perf_counter() - t_start, 1)
    res["thresholds_evaluation"] = evaluate(res)
    res["final_storage"] = sqlite_storage(work / sp.DB_NAME)
    if not args.keep_db:
        shutil.rmtree(work, ignore_errors=True)
        res["db_deleted"] = not work.exists()
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"results: {out / 'results.json'}")
    for c in res["thresholds_evaluation"]:
        print(f"  {c['id']} {c['verdict']:13} observed={c['observed']} :: {c['metric']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
