"""SQLite phases of the TITAN OS DB stress test.

Write paths used (stated per phase in the results JSON):
  * schema: the real ``DatabaseManager`` (create_database + migrations v1..v28);
  * main load / re-sync / concurrency writes: the real Garmin persistence path
    ``titan.orchestration.garmin_persistence.persist_garmin_data`` (DataSanityChecker,
    physiological bounds, one transaction per sync, INSERT OR IGNORE idempotency);
  * manual duplicates: ``DatabaseManager.save_session`` without a Garmin id (manual path);
  * reads: the real repository methods (get_recent_activities, get_training_load_history,
    get_ctl_atl_tsb, get_hrv_history, get_baseline_rhr, get_weight_history, get_daily_metric)
    plus one raw per-athlete date-range SELECT (no repository method takes a date range);
  * athlete registration: raw INSERT into ``athletes`` (the product has no API for it);
  * bulk-insert phase: raw ``executemany`` SQL (and save_session for comparison).
"""
from __future__ import annotations

import multiprocessing as mp
import os
import random
import shutil
import signal
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import dataset as ds
from stress_common import latency_summary, measured, sqlite_storage

from titan.core.database import DatabaseManager
from titan.orchestration.garmin_persistence import PersistenceFailure, persist_garmin_data
from titan.science.tsb_engine import LOAD_HISTORY_DAYS

DB_NAME = "stress.db"


# ── small utilities ──────────────────────────────────────────────────────────

class Emit:
    """The ``emit`` callable persist_garmin_data expects; counts outcomes."""

    def __init__(self) -> None:
        self.counts: Counter = Counter()

    def __call__(self, action: str, **fields) -> None:
        out = fields.get("outcome")
        self.counts[f"{action}:{out}" if out else action] += 1


def open_db(db_dir: Path, name: str = DB_NAME) -> tuple[DatabaseManager, float]:
    t0 = time.perf_counter()
    db = DatabaseManager(db_name=name, db_dir=db_dir)
    return db, (time.perf_counter() - t0) * 1000


def register_athletes(db: DatabaseManager, ids: list[str]) -> None:
    with db.transaction():
        db.conn.executemany(
            "INSERT OR IGNORE INTO athletes (athlete_id, display_name, created_at, is_cold_start, "
            "cold_start_sessions_count) VALUES (?, ?, datetime('now'), 0, 30)",
            [(a, f"Synthetic {a}") for a in ids],
        )


def try_drop_os_cache() -> bool:
    try:
        os.sync()
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("3\n")
    except OSError:
        return False
    return True


def range_query(db: DatabaseManager, aid: str, start: str, end: str) -> list:
    with db._lock:
        return db.conn.execute(
            "SELECT date, session_type, distance_km, duration_sec, avg_hr, training_load "
            "FROM training_log WHERE athlete_id = ? AND date BETWEEN ? AND ? ORDER BY date",
            (aid, start, end),
        ).fetchall()


QUERY_NAMES = ("recent_activities_90", "range_30d_raw_sql", "training_load_history_210d",
               "ctl_atl_tsb", "hrv_history_28", "baseline_rhr_7", "weight_history_30",
               "daily_metric_one_day")


def bench_queries(db: DatabaseManager, athletes: list[str], anchor: date) -> dict:
    lat: dict[str, list[float]] = {q: [] for q in QUERY_NAMES}
    errors: Counter = Counter()
    start = (anchor - timedelta(days=30)).isoformat()
    end = anchor.isoformat()
    for aid in athletes:
        calls = (
            ("recent_activities_90", lambda a=aid: db.get_recent_activities(90, athlete_id=a)),
            ("range_30d_raw_sql", lambda a=aid: range_query(db, a, start, end)),
            ("training_load_history_210d",
             lambda a=aid: db.get_training_load_history(LOAD_HISTORY_DAYS, athlete_id=a)),
            ("ctl_atl_tsb", lambda a=aid: db.get_ctl_atl_tsb(athlete_id=a)),
            ("hrv_history_28", lambda a=aid: db.get_hrv_history(28, athlete_id=a)),
            ("baseline_rhr_7", lambda a=aid: db.get_baseline_rhr(7, athlete_id=a)),
            ("weight_history_30", lambda a=aid: db.get_weight_history(30, athlete_id=a)),
            ("daily_metric_one_day", lambda a=aid: db.get_daily_metric(end, athlete_id=a)),
        )
        for name, fn in calls:
            t0 = time.perf_counter()
            try:
                fn()
            except sqlite3.Error as e:
                errors[f"{name}:{e}"] += 1
            lat[name].append((time.perf_counter() - t0) * 1000)
    out = {q: latency_summary(v) for q, v in lat.items()}
    out["errors"] = dict(errors)
    out["athletes_sampled"] = len(athletes)
    return out


def capture_query_plans(db: DatabaseManager, aid: str, anchor: date) -> list[dict]:
    """Run the real methods once with a trace callback, then EXPLAIN QUERY PLAN each SELECT."""
    seen: list[str] = []

    def tracer(sql: str) -> None:
        s = sql.strip()
        if s.upper().startswith("SELECT") and s not in seen:
            seen.append(s)

    db.conn.set_trace_callback(tracer)
    try:
        bench_queries(db, [aid], anchor)
        db.conn.execute("SELECT id FROM training_log WHERE garmin_activity_id = ?",
                        (ds.activity_ext_id(0, 1),)).fetchall()
    finally:
        db.conn.set_trace_callback(None)
    plans = []
    for sql in seen:
        if "sqlite_master" in sql:
            continue
        try:
            params = ["x"] * sql.count("?")
            rows = db.conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
            detail = [r[-1] for r in rows]
        except sqlite3.Error as e:
            detail = [f"error: {e}"]
        plans.append({
            "sql": " ".join(sql.split())[:400],
            "plan": detail,
            "full_scan": any(d.startswith("SCAN training_log") or d.startswith("SCAN daily_metrics")
                             for d in detail),
        })
    return plans


# ── phase: bulk inserts with different batch sizes (raw SQL) ───────────────

def phase_bulk_insert(work: Path, cfg: dict, res: dict) -> None:
    d = work / "bulk"
    d.mkdir(parents=True, exist_ok=True)
    db, _ = open_db(d)
    pool: list[tuple] = []
    i = 0
    need = cfg["bulk_pool_rows"]
    while len(pool) < need:
        pool.extend(ds.raw_training_rows(cfg["seed"], i, cfg["anchor"]))
        i += 1
    pool = pool[:need]
    out: dict = {"write_path": "raw executemany on DatabaseManager.conn (production schema)",
                 "runs": []}

    def run(label: str, batch: int, nrows: int, path: str, sync_mode: str | None = None) -> None:
        if sync_mode:
            db.conn.execute(f"PRAGMA synchronous={sync_mode}")
        rows = [r[:13] + (f"{label}-{r[13]}",) + r[14:] for r in pool[:nrows]]
        lat: list[float] = []
        key = f"bulk_{label}"
        holder: dict = {}
        with measured(holder, key) as entry:
            t_all = time.perf_counter()
            if path == "raw":
                for s in range(0, nrows, batch):
                    chunk = rows[s:s + batch]
                    t0 = time.perf_counter()
                    db.conn.execute("BEGIN")
                    db.conn.executemany(ds.TRAINING_INSERT_SQL, chunk)
                    db.conn.commit()
                    lat.append((time.perf_counter() - t0) * 1000)
            else:  # real save_session path
                for s in range(0, nrows, batch):
                    chunk = rows[s:s + batch]
                    t0 = time.perf_counter()
                    if batch == 1:
                        r = chunk[0]
                        db.save_session(date=r[1], session_type=r[2], distance_km=r[3],
                                        duration_sec=r[4], avg_hr=r[5], max_hr=r[6],
                                        training_load=r[8], notes=r[12],
                                        garmin_activity_id=r[13], athlete_id=r[0])
                    else:
                        with db.transaction():
                            for r in chunk:
                                db.save_session(date=r[1], session_type=r[2], distance_km=r[3],
                                                duration_sec=r[4], avg_hr=r[5], max_hr=r[6],
                                                training_load=r[8], notes=r[12],
                                                garmin_activity_id=r[13], athlete_id=r[0])
                    lat.append((time.perf_counter() - t0) * 1000)
            wall = time.perf_counter() - t_all
        if sync_mode:
            db.conn.execute("PRAGMA synchronous=NORMAL")
        out["runs"].append({
            "label": label, "path": path, "batch_rows_per_tx": batch, "rows": nrows,
            "synchronous": sync_mode or "NORMAL (production)",
            "wall_s": round(wall, 3), "rows_per_s": round(nrows / wall, 1),
            "tx_per_s": round(len(lat) / wall, 1), "tx_latency": latency_summary(lat),
            "resources": entry["resources"],
        })

    small = cfg["small"]
    n1 = 2_000 if small else 20_000
    nb = 10_000 if small else 100_000
    run("b1", 1, n1, "raw")
    run("b10", 10, nb // 2, "raw")
    run("b100", 100, nb, "raw")
    run("b1000", 1000, nb, "raw")
    run("b10000", 10_000, nb, "raw")
    run("save_session_autocommit", 1, n1, "save_session")
    run("save_session_tx500", 500, nb // 2, "save_session")
    run("b1_sync_full_nonprod", 1, n1 // 4, "raw", sync_mode="FULL")
    out["rows_in_table"] = db.conn.execute("SELECT COUNT(*) FROM training_log").fetchone()[0]
    out["storage"] = sqlite_storage(db.db_path)
    db.close()
    shutil.rmtree(d, ignore_errors=True)
    res["phase1_bulk_insert"] = out


# ── phase: main load through the real Garmin persistence path + growth steps ─

def phase_main_load(db: DatabaseManager, cfg: dict, res: dict, work: Path) -> dict:
    n = cfg["athletes"]
    seed, anchor = cfg["seed"], cfg["anchor"]
    fracs = (0.10, 0.25, 0.50, 1.00)
    checkpoints = {max(1, round(f * n)): f for f in fracs}
    emit = Emit()
    failed_syncs: set[tuple[str, str]] = set()
    failure_causes: Counter = Counter()
    seg_lat: list[float] = []
    all_lat: list[float] = []
    totals = Counter()
    act_dist: Counter = Counter()
    growth: list[dict] = []
    seg_t0 = time.perf_counter()
    seg_rows0 = 0
    rng = random.Random(f"{seed}:sample")
    holder: dict = {}
    with measured(holder, "load") as entry:
        t_all = time.perf_counter()
        gen_s = 0.0
        for i in range(n):
            tg = time.perf_counter()
            a = ds.generate_athlete(seed, i, anchor)
            gen_s += time.perf_counter() - tg
            register_athletes(db, [a.athlete_id])
            act_dist[len(a.activities)] += 1
            totals["activities_generated"] += len(a.activities)
            totals["activity_anomalies"] += len(a.activity_anomalies)
            totals["daily_records_generated"] += len(a.syncs)
            totals["daily_anomalies"] += len(a.daily_anomalies)
            for today, payload in a.syncs:
                t0 = time.perf_counter()
                try:
                    persist_garmin_data(db, payload, today, athlete_id=a.athlete_id, emit=emit)
                except PersistenceFailure as exc:
                    failed_syncs.add((a.athlete_id, today))
                    cause = exc.__cause__
                    failure_causes[f"{type(cause).__name__}: {str(cause)[:80]}"] += 1
                ms = (time.perf_counter() - t0) * 1000
                seg_lat.append(ms)
                all_lat.append(ms)
                totals["syncs"] += 1
                totals["activity_payload_records"] += len(payload["activities"])
            for m in a.manual_entries:  # manual path: no Garmin id
                db.save_session(date=m["date"], session_type="EASY", distance_km=m["distance_km"],
                                duration_sec=m["duration_sec"], avg_hr=m["avg_hr"],
                                max_hr=m["max_hr"], training_load=m["estimated_training_load"],
                                notes=m["name"], athlete_id=a.athlete_id)
                totals["manual_entries"] += 1
            if (i + 1) in checkpoints:
                seg_wall = time.perf_counter() - seg_t0
                rows_now = db.conn.execute("SELECT COUNT(*) FROM training_log").fetchone()[0]
                dm_now = db.conn.execute("SELECT COUNT(*) FROM daily_metrics").fetchone()[0]
                sample = rng.sample([ds.athlete_id(j) for j in range(i + 1)],
                                    min(cfg["growth_sample"], i + 1))
                tq = time.perf_counter()
                qb = bench_queries(db, sample, anchor)
                q_wall = time.perf_counter() - tq
                db2, open_ms = open_db(db.db_path.parent)
                db2.close()
                growth.append({
                    "fraction": checkpoints[i + 1], "athletes_loaded": i + 1,
                    "training_log_rows": rows_now, "daily_metrics_rows": dm_now,
                    "storage": sqlite_storage(db.db_path),
                    "segment_sync_latency": latency_summary(seg_lat),
                    "segment_syncs_per_s": round(len(seg_lat) / seg_wall, 1),
                    "segment_activity_rows_per_s": round((rows_now - seg_rows0) / seg_wall, 1),
                    "queries_warmish": qb, "query_bench_wall_s": round(q_wall, 2),
                    "databasemanager_open_ms": round(open_ms, 1),
                    "elapsed_s": round(time.perf_counter() - t_all, 1),
                })
                print(f"  growth {checkpoints[i + 1]:.0%}: rows={rows_now} "
                      f"sync p95={growth[-1]['segment_sync_latency']['p95_ms']}ms "
                      f"ctl p95={qb['ctl_atl_tsb']['p95_ms']}ms", flush=True)
                seg_lat = []
                seg_t0 = time.perf_counter()
                seg_rows0 = rows_now
        wall = time.perf_counter() - t_all
    rows = db.conn.execute("SELECT COUNT(*) FROM training_log").fetchone()[0]
    dm = db.conn.execute("SELECT COUNT(*) FROM daily_metrics").fetchone()[0]
    res["phase2_main_load"] = {
        "write_path": "persist_garmin_data (real Garmin persistence path), one weekly sync per tx; "
                      "manual duplicates via DatabaseManager.save_session; athletes via raw INSERT",
        "wall_s": round(wall, 1), "generation_s": round(gen_s, 1),
        "syncs": totals["syncs"], "syncs_failed": len(failed_syncs),
        "sync_failure_causes": dict(failure_causes),
        "sync_latency": latency_summary(all_lat),
        "syncs_per_s_incl_generation": round(totals["syncs"] / wall, 1),
        "syncs_per_s_persist_only": round(totals["syncs"] / (sum(all_lat) / 1000), 1),
        "training_log_rows": rows, "daily_metrics_rows": dm,
        "activity_rows_per_s_incl_generation": round(rows / wall, 1),
        "activity_rows_per_s_persist_only": round(rows / (sum(all_lat) / 1000), 1),
        "emit_outcomes": dict(emit.counts), "totals": dict(totals),
        "activities_per_athlete_distribution": {
            "min": min(act_dist), "max": max(act_dist),
            "mean": round(sum(k * v for k, v in act_dist.items()) / sum(act_dist.values()), 2),
            "histogram_by_10": dict(sorted(Counter((k // 10) * 10 for k in act_dist.elements()).items())),
        },
        "storage": sqlite_storage(db.db_path),
        "resources": entry["resources"],
    }
    res["phase7_growth"] = growth
    return {"failed_syncs": failed_syncs}


# ── verification: integrity, anomaly handling, duplicates, lost records ─────

def _tag_of(notes: str | None) -> tuple[str | None, int | None]:
    if not notes or ":" not in notes:
        return None, None
    a, _, k = notes.partition(":")
    try:
        return a, int(k)
    except ValueError:
        return a, None


def verify_dataset(db: DatabaseManager, cfg: dict, state: dict, res: dict) -> None:
    seed, anchor, n = cfg["seed"], cfg["anchor"], cfg["athletes"]
    failed = state["failed_syncs"]
    holder: dict = {}
    with measured(holder, "verify") as entry:
        by_ath: dict[str, list[tuple]] = defaultdict(list)
        tag_mismatch = 0
        untagged = 0
        for row in db.conn.execute(
            "SELECT athlete_id, notes, garmin_activity_id, date, distance_km, duration_sec, avg_hr, "
            "max_hr, training_load, quality_flag FROM training_log"
        ):
            ta, k = _tag_of(row[1])
            if ta is None:
                untagged += 1
                continue
            if ta != row[0]:
                tag_mismatch += 1
            by_ath[ta].append((k,) + row)
        daily: dict[str, dict[str, tuple]] = defaultdict(dict)
        for row in db.conn.execute(
            "SELECT athlete_id, date, hrv_rmssd, resting_hr, weight_kg, sleep_hours, quality_flag "
            "FROM daily_metrics"
        ):
            daily[row[0]][row[1]] = row[2:]

        valid = Counter()
        act_out: dict[str, Counter] = defaultdict(Counter)
        act_cnt: Counter = Counter()
        daily_valid = Counter()
        daily_out: dict[str, Counter] = defaultdict(Counter)
        daily_cnt: Counter = Counter()
        failed_class_presence: Counter = Counter()
        for i in range(n):
            a = ds.generate_athlete(seed, i, anchor)
            rows = by_ath.get(a.athlete_id, [])
            by_k: dict[int, list[tuple]] = defaultdict(list)
            for r in rows:
                by_k[r[0]].append(r)
            for k, act in enumerate(a.activities):
                cls = a.activity_anomalies.get(k)
                sday = _sync_day(act["date"], anchor)
                sync_failed = (a.athlete_id, sday) in failed
                if sync_failed and cls:
                    failed_class_presence[cls] += 1
                got = by_k.get(k, [])
                if cls is None:
                    if sync_failed:
                        valid["lost_in_rolled_back_sync"] += 1 if not got else 0
                        valid["kept_ok"] += 1 if got else 0
                    elif len(got) == 0:
                        valid["lost"] += 1
                    elif len(got) > 1:
                        valid["duplicated"] += 1
                    else:
                        r = got[0]
                        same = (r[4] == act["date"] and r[5] == act["distance_km"]
                                and r[6] == act["duration_sec"] and r[7] == act["avg_hr"]
                                and r[8] == act["max_hr"]
                                and r[9] == act["estimated_training_load"] and r[10] is None)
                        valid["kept_ok" if same else "kept_mutated"] += 1
                    continue
                act_cnt[cls] += 1
                if sync_failed and cls not in ("dup_resync",):
                    act_out[cls]["its sync rolled back (PersistenceFailure) -> 0 rows"] += 1
                    continue
                act_out[cls][_describe_activity(cls, got, act, sday)] += 1
            for today, payload in a.syncs:
                dcls = a.daily_anomalies.get(today)
                got = daily.get(a.athlete_id, {}).get(today)
                if dcls:
                    daily_cnt[dcls] += 1
                if (a.athlete_id, today) in failed:
                    if dcls:
                        daily_out[dcls]["sync rolled back -> no row"] += 1
                    else:
                        daily_valid["lost_in_rolled_back_sync"] += 1 if got is None else 0
                    continue
                if dcls:
                    daily_out[dcls][_describe_daily(dcls, got)] += 1
                    continue
                if got is None:
                    daily_valid["lost"] += 1
                    continue
                sl = payload["sleep"][0]
                exp = (next(e["rmssd"] for e in payload["hrv"] if e["date"] == today),
                       sl["resting_hr"], payload["weight"][0]["weight_kg"], sl["total_sleep_hours"])
                daily_valid["kept_ok" if tuple(got[:4]) == exp else "kept_mutated"] += 1
        dup_ext = db.conn.execute(
            "SELECT COUNT(*) FROM (SELECT garmin_activity_id FROM training_log WHERE "
            "garmin_activity_id IS NOT NULL GROUP BY garmin_activity_id HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        unknown_athlete_rows = db.conn.execute(
            "SELECT COUNT(*) FROM training_log t WHERE NOT EXISTS "
            "(SELECT 1 FROM athletes a WHERE a.athlete_id = t.athlete_id)"
        ).fetchone()[0]
        integrity = db.conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = db.conn.execute("PRAGMA foreign_key_check").fetchall()
    res["verification"] = {
        "valid_activities": dict(valid),
        "valid_daily_records": dict(daily_valid),
        "activity_anomaly_counts": dict(act_cnt),
        "activity_anomaly_observed": {c: dict(v) for c, v in act_out.items()},
        "activity_anomaly_expected": {c: list(v) for c, v in ds.ACTIVITY_ANOMALY_CLASSES.items()},
        "daily_anomaly_counts": dict(daily_cnt),
        "daily_anomaly_observed": {c: dict(v) for c, v in daily_out.items()},
        "daily_anomaly_expected": {c: list(v) for c, v in ds.DAILY_ANOMALY_CLASSES.items()},
        "failed_sync_anomaly_class_presence": dict(failed_class_presence),
        "rows_whose_payload_tag_athlete_differs_from_athlete_id": tag_mismatch,
        "untagged_rows": untagged,
        "duplicate_garmin_ids": dup_ext,
        "rows_with_athlete_id_not_in_athletes": unknown_athlete_rows,
        "integrity_check": integrity, "foreign_key_violations": len(fk),
        "resources": entry["resources"],
    }


def _sync_day(act_date: str, anchor: date) -> str:
    off = (anchor - date.fromisoformat(act_date)).days
    return (anchor - timedelta(days=7 * (off // 7))).isoformat()


def _describe_activity(cls: str, got: list[tuple], act: dict, sday: str) -> str:
    if not got:
        return "not stored (0 rows)"
    r = got[0]
    flag = f", quality_flag={r[10]!r}" if r[10] is not None else ""
    extra = ""
    if cls in ("hr_missing", "wrong_type_hr", "hr_extreme", "max_hr_lt_avg_hr"):
        extra = f", avg_hr={r[7]!r}, max_hr={r[8]!r}"
    elif cls in ("distance_zero", "distance_negative", "wrong_type_distance"):
        extra = f", distance_km={'neg' if (r[5] or 0) < 0 else r[5]!r}"
    elif cls in ("duration_negative", "duration_zero_with_distance", "pace_absurd"):
        extra = f", duration_sec={'neg' if (r[6] or 0) < 0 else ('0' if r[6] == 0 else '>0')}"
    elif cls in ("load_extreme", "load_negative"):
        extra = f", training_load={r[9]!r}"
    elif cls in ("date_missing", "date_null", "date_unparseable", "date_future"):
        if r[4] == act["date"]:
            extra = ", date=true date"
        elif r[4] == sday:
            extra = ", date=sync day (mis-dated)"
        else:
            extra = f", date={r[4]!r}"
    return f"stored x{len(got)}{flag}{extra}"


_DAILY_FIELDS = {"hrv_zero": (0,), "hrv_extreme": (0,), "rhr_absurd": (1,), "weight_negative": (2,),
                 "weight_zero": (2,), "sleep_minutes_as_hours": (3,), "sleep_tiny": (3,),
                 "all_optional_missing": (0, 1, 2, 3)}
_DAILY_NAMES = ("hrv", "rhr", "weight", "sleep_h")


def _describe_daily(cls: str, got: tuple | None) -> str:
    if got is None:
        return "no row"
    parts = [f"{_DAILY_NAMES[j]}={got[j]!r}" for j in _DAILY_FIELDS[cls]]
    return "row stored: " + ", ".join(parts) + f", quality_flag={got[4]!r}"


# ── read-path handling of load anomalies (ADR-0023 at read time) ─────────────

def verify_read_path_loads(db: DatabaseManager, cfg: dict, res: dict) -> None:
    seed, anchor = cfg["seed"], cfg["anchor"]
    out: dict[str, Counter] = defaultdict(Counter)
    for i in range(cfg["athletes"]):
        a = ds.generate_athlete(seed, i, anchor)
        targets = [(k, c) for k, c in a.activity_anomalies.items()
                   if c in ("load_extreme", "load_negative")]
        if not targets:
            continue
        hist = dict(db.get_training_load_history(LOAD_HISTORY_DAYS, athlete_id=a.athlete_id))
        # the repository window is relative to the wall clock: date >= date('now', '-210 days')
        cutoff = (date.today() - timedelta(days=LOAD_HISTORY_DAYS)).isoformat()
        for k, c in targets:
            d = a.activities[k]["date"]
            if d < cutoff:
                out[c]["outside the 210-day window (not testable)"] += 1
            elif d not in hist:
                out[c]["inside window: date absent from get_training_load_history (excluded)"] += 1
            else:
                out[c][f"inside window: present with value {hist[d]}"] += 1
    res["read_path_load_anomalies"] = {c: dict(v) for c, v in out.items()}


# ── leakage: every athlete-scoped read returns only that athlete's rows ──────

def verify_leakage(db: DatabaseManager, cfg: dict, res: dict) -> None:
    seed, anchor, n = cfg["seed"], cfg["anchor"], cfg["athletes"]
    by_ath: dict[str, Counter] = defaultdict(Counter)
    for _aid, notes, d, dist, dur in db.conn.execute(
        "SELECT athlete_id, notes, date, distance_km, duration_sec FROM training_log"
    ):
        ta, _ = _tag_of(notes)
        if ta is not None:
            by_ath[ta][(d, dist or 0.0, dur or 0)] += 1
    rng = random.Random(f"{seed}:leak")
    ids = [ds.athlete_id(i) for i in range(n)]
    recent_ids = ids if cfg["leak_sample"] >= n else rng.sample(ids, cfg["leak_sample"])
    holder: dict = {}
    with measured(holder, "leak") as entry:
        recent_mismatch = 0
        lat_recent: list[float] = []
        for aid in recent_ids:
            t0 = time.perf_counter()
            got = db.get_recent_activities(limit=1000, athlete_id=aid)
            lat_recent.append((time.perf_counter() - t0) * 1000)
            ms = Counter((r["date"], r["distance_km"], r["duration_sec"]) for r in got)
            if ms != by_ath.get(aid, Counter()):
                recent_mismatch += 1
        hrv_mismatch_rows = 0
        hrv_rows = 0
        lat_hrv: list[float] = []
        for i in range(n):
            a = ds.generate_athlete(seed, i, anchor)
            t0 = time.perf_counter()
            got = db.get_hrv_history(days=1000, athlete_id=a.athlete_id)
            lat_hrv.append((time.perf_counter() - t0) * 1000)
            for d, v in got:
                hrv_rows += 1
                if a.expected_hrv.get(d) != v:
                    hrv_mismatch_rows += 1
    # Methods without an athlete_id parameter (static finding, probed here).
    db.conn.execute("INSERT INTO gear_usage (shoe_name, athlete_id) VALUES ('probe-A', 'ath00000')")
    db.conn.execute("INSERT INTO gear_usage (shoe_name, athlete_id) VALUES ('probe-B', 'ath00001')")
    db.conn.execute("INSERT INTO personal_bests (distance_km, time_sec, date, athlete_id) "
                    "VALUES (5.0, 1200, '2026-01-01', 'ath00000')")
    db.conn.execute("INSERT INTO personal_bests (distance_km, time_sec, date, athlete_id) "
                    "VALUES (5.0, 1100, '2026-01-02', 'ath00001')")
    db.conn.commit()
    shoes = db.get_active_shoes()
    pr = db.get_pr(5.0)
    res["leakage"] = {
        "get_recent_activities": {
            "athletes_checked": len(recent_ids),
            "athletes_with_mismatch_vs_payload_tag": recent_mismatch,
            "latency": latency_summary(lat_recent),
        },
        "get_hrv_history": {
            "athletes_checked": n, "rows_returned": hrv_rows,
            "rows_not_matching_own_ground_truth": hrv_mismatch_rows,
            "latency": latency_summary(lat_hrv),
        },
        "unscoped_api_probe": {
            "get_active_shoes_returns_rows_of_athletes": sorted(
                {r[1] for r in shoes if r[1].startswith("probe-")}),
            "get_pr_5k_returned_time_sec": pr[0] if pr else None,
            "note": "get_active_shoes()/get_pr()/add_shoe()/save_personal_best() take no "
                    "athlete_id; two athletes' probe rows are both visible to either caller",
        },
        "resources": entry["resources"],
    }


# ── phase: queries cold vs warm + EXPLAIN QUERY PLAN ─────────────────────────

def phase_queries(work: Path, cfg: dict, res: dict) -> None:
    rng = random.Random(f"{cfg['seed']}:q")
    sample = rng.sample([ds.athlete_id(i) for i in range(cfg["athletes"])],
                        min(cfg["query_sample"], cfg["athletes"]))
    dropped = try_drop_os_cache()
    db, open_ms = open_db(work)
    out: dict = {"os_page_cache_dropped": dropped, "databasemanager_open_ms_cold": round(open_ms, 1)}
    holder: dict = {}
    with measured(holder, "cold") as e1:
        out["cold_pass"] = bench_queries(db, sample, cfg["anchor"])
    with measured(holder, "warm") as e2:
        out["warm_pass"] = bench_queries(db, sample, cfg["anchor"])
    out["cold_pass"]["resources"] = e1["resources"]
    out["warm_pass"]["resources"] = e2["resources"]
    db.close()
    db, open_ms2 = open_db(work)
    out["databasemanager_open_ms_warm"] = round(open_ms2, 1)
    out["query_plans"] = capture_query_plans(db, sample[0], cfg["anchor"])
    db.close()
    res["phase3_queries"] = out


# ── phase: repeated syncs and duplicate avoidance ────────────────────────────

def phase_resync(db: DatabaseManager, cfg: dict, res: dict) -> None:
    rng = random.Random(f"{cfg['seed']}:resync")
    idx = rng.sample(range(cfg["athletes"]), min(cfg["resync_athletes"], cfg["athletes"]))
    before_tl = db.conn.execute("SELECT COUNT(*) FROM training_log").fetchone()[0]
    before_dm = db.conn.execute("SELECT COUNT(*) FROM daily_metrics").fetchone()[0]
    passes = []
    holder: dict = {}
    for p in (2, 3):
        emit = Emit()
        lat: list[float] = []
        fails = 0
        with measured(holder, f"resync{p}") as entry:
            t_all = time.perf_counter()
            for i in idx:
                a = ds.generate_athlete(cfg["seed"], i, cfg["anchor"])
                for today, payload in a.syncs:
                    t0 = time.perf_counter()
                    try:
                        persist_garmin_data(db, payload, today, athlete_id=a.athlete_id, emit=emit)
                    except PersistenceFailure:
                        fails += 1
                    lat.append((time.perf_counter() - t0) * 1000)
            wall = time.perf_counter() - t_all
        tl = db.conn.execute("SELECT COUNT(*) FROM training_log").fetchone()[0]
        dm = db.conn.execute("SELECT COUNT(*) FROM daily_metrics").fetchone()[0]
        passes.append({
            "sync_pass": p, "athletes": len(idx), "syncs": len(lat), "syncs_failed": fails,
            "new_training_log_rows": tl - before_tl, "new_daily_metrics_rows": dm - before_dm,
            "sync_latency": latency_summary(lat), "syncs_per_s": round(len(lat) / wall, 1),
            "emit_outcomes": dict(emit.counts), "resources": entry["resources"],
        })
    dup = db.conn.execute(
        "SELECT COUNT(*) FROM (SELECT garmin_activity_id FROM training_log WHERE "
        "garmin_activity_id IS NOT NULL GROUP BY garmin_activity_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    res["phase4_resync"] = {"write_path": "persist_garmin_data (same payloads re-sent)",
                            "passes": passes, "duplicate_garmin_ids_after": dup}


# ── phase: concurrency (threads sharing one DatabaseManager / processes) ─────

def _conc_payload(cfg_idx: int, wid: int, n: int, today: str, rng: random.Random) -> dict:
    dist = round(rng.uniform(5, 15), 3)
    return {
        "activities": [{
            "activity_id": str(8_000_000_000 + cfg_idx * 10_000_000 + wid * 1_000_000 + n),
            "date": today, "activity_type": "running", "distance_km": dist,
            "duration_sec": int(dist * 330), "avg_hr": 140, "max_hr": 160,
            "estimated_training_load": 80, "avg_pace_sec_per_km": 330,
            "name": f"conc{cfg_idx}:{wid}:{n}",
        }],
        "sleep": [{"date": today, "resting_hr": 50, "sleep_score": 80, "total_sleep_hours": 7.0}],
        "hrv": [{"date": today, "rmssd": 60.0}],
        "weight": [{"date": today, "weight_kg": 70.0}],
    }


def _worker_loop(db, cfg_idx, wid, duration, write_ratio, athletes, seed, anchor) -> dict:
    rng = random.Random(f"{seed}:w{cfg_idx}:{wid}")
    lat_r: list[float] = []
    lat_w: list[float] = []
    errors: Counter = Counter()
    writes_ok = 0
    n = 0
    end = time.perf_counter() + duration
    emit = Emit()
    while time.perf_counter() < end:
        aid = rng.choice(athletes)
        if rng.random() < write_ratio:
            # spread over the year so per-day load sums stay realistic
            today = (anchor - timedelta(days=rng.randrange(365))).isoformat()
            payload = _conc_payload(cfg_idx, wid, n, today, rng)
            n += 1
            t0 = time.perf_counter()
            try:
                persist_garmin_data(db, payload, today, athlete_id=aid, emit=emit)
                writes_ok += 1
            except PersistenceFailure as exc:
                errors[f"write:{type(exc.__cause__).__name__}:{exc.__cause__}"] += 1
            lat_w.append((time.perf_counter() - t0) * 1000)
        else:
            op = rng.randrange(3)
            t0 = time.perf_counter()
            try:
                if op == 0:
                    db.get_ctl_atl_tsb(athlete_id=aid)
                elif op == 1:
                    db.get_recent_activities(90, athlete_id=aid)
                else:
                    db.get_hrv_history(28, athlete_id=aid)
            except sqlite3.Error as e:
                errors[f"read:{type(e).__name__}:{e}"] += 1
            lat_r.append((time.perf_counter() - t0) * 1000)
    return {"lat_r": lat_r, "lat_w": lat_w, "errors": dict(errors), "writes_ok": writes_ok,
            "writes_attempted": n}


def _proc_worker(db_dir, cfg_idx, wid, duration, write_ratio, athletes, seed, anchor_s, barrier, q):
    import logging
    logging.getLogger().setLevel(logging.ERROR)
    t0 = time.perf_counter()
    try:
        db = DatabaseManager(db_name=DB_NAME, db_dir=Path(db_dir))
    except Exception as e:  # noqa: BLE001 - reported to the parent
        q.put({"open_error": f"{type(e).__name__}: {e}"})
        barrier.wait()
        return
    open_ms = (time.perf_counter() - t0) * 1000
    barrier.wait()
    out = _worker_loop(db, cfg_idx, wid, duration, write_ratio, athletes, seed,
                       date.fromisoformat(anchor_s))
    out["open_ms"] = open_ms
    db.close()
    q.put(out)


def phase_concurrency(work: Path, cfg: dict, res: dict) -> None:
    rng = random.Random(f"{cfg['seed']}:conc")
    athletes = rng.sample([ds.athlete_id(i) for i in range(cfg["athletes"])],
                          min(500, cfg["athletes"]))
    configs = []
    for w in (1, 2, 4, 8):
        configs += [("threads_shared_connection", w, 0.2), ("processes_own_connection", w, 0.2),
                    ("processes_own_connection", w, 1.0)]
    runs = []
    ctx = mp.get_context("spawn")
    for cfg_idx, (mode, workers, wr) in enumerate(configs, start=1):
        holder: dict = {}
        results: list[dict] = []
        with measured(holder, "c") as entry:
            t_all = time.perf_counter()
            if mode.startswith("threads"):
                import threading
                db, _ = open_db(work)
                lock = threading.Lock()

                def tw(wid, db=db, lock=lock, cfg_idx=cfg_idx, wr=wr, results=results):
                    r = _worker_loop(db, cfg_idx, wid, cfg["conc_duration"], wr, athletes,
                                     cfg["seed"], cfg["anchor"])
                    with lock:
                        results.append(r)
                ths = [threading.Thread(target=tw, args=(k,)) for k in range(workers)]
                for t in ths:
                    t.start()
                for t in ths:
                    t.join()
                db.close()
            else:
                barrier = ctx.Barrier(workers)
                q = ctx.Queue()
                procs = [ctx.Process(target=_proc_worker, args=(
                    str(work), cfg_idx, k, cfg["conc_duration"], wr, athletes, cfg["seed"],
                    cfg["anchor"].isoformat(), barrier, q)) for k in range(workers)]
                for p in procs:
                    p.start()
                for _ in procs:
                    results.append(q.get())
                for p in procs:
                    p.join()
            wall = time.perf_counter() - t_all
        db, _ = open_db(work)
        stored = db.conn.execute("SELECT COUNT(*) FROM training_log WHERE notes LIKE ?",
                                 (f"conc{cfg_idx}:%",)).fetchone()[0]
        db.close()
        lat_r = [x for r in results for x in r.get("lat_r", [])]
        lat_w = [x for r in results for x in r.get("lat_w", [])]
        errs: Counter = Counter()
        for r in results:
            errs.update(r.get("errors", {}))
            if "open_error" in r:
                errs["open:" + r["open_error"]] += 1
        writes_ok = sum(r.get("writes_ok", 0) for r in results)
        attempted = sum(r.get("writes_attempted", 0) for r in results)
        dur = cfg["conc_duration"]
        locked = sum(v for k, v in errs.items() if "locked" in k or "busy" in k.lower())
        runs.append({
            "mode": mode, "workers": workers, "write_ratio": wr, "duration_s": dur,
            "reads": len(lat_r), "writes_attempted": attempted, "writes_ok": writes_ok,
            "writes_failed": attempted - writes_ok,
            "read_ops_per_s": round(len(lat_r) / dur, 1), "write_tx_per_s": round(writes_ok / dur, 1),
            "read_latency": latency_summary(lat_r), "write_latency": latency_summary(lat_w),
            "errors": dict(errs), "database_is_locked_errors": locked,
            "retries": 0, "deadlocks": 0,
            "rows_stored_vs_writes_ok": [stored, writes_ok],
            "lost_or_phantom_rows": stored - writes_ok,
            "open_ms_per_process": [round(r["open_ms"], 1) for r in results if "open_ms" in r],
            "wall_s_incl_startup": round(wall, 2), "resources": entry["resources"],
        })
        print(f"  conc {mode} w={workers} wr={wr}: reads/s={runs[-1]['read_ops_per_s']} "
              f"writes/s={runs[-1]['write_tx_per_s']} locked={locked}", flush=True)
    res["phase5_concurrency"] = {
        "note": "threads share one DatabaseManager (one connection + RLock, the in-process app "
                "model); processes each open their own DatabaseManager on the same file (the "
                "titan-api + titan-worker model). No retry logic exists in the app; retries=0 "
                "means none were attempted. SQLite has no deadlock detector: lock waits end "
                "after busy_timeout (5000 ms) with 'database is locked'.",
        "runs": runs,
    }


# ── phase: updates, rollback, restart after failed import ───────────────────

def _crash_payloads(tag: str, n_syncs: int, aid_pool: list[str]) -> list[tuple[str, str, dict]]:
    out = []
    base = date(2024, 1, 1)
    for j in range(n_syncs):
        aid = aid_pool[j % len(aid_pool)]
        today = (base + timedelta(days=j // len(aid_pool))).isoformat()
        acts = [{
            "activity_id": f"{tag}-{j}-{m}", "date": today, "activity_type": "running",
            "distance_km": 8.0 + m, "duration_sec": int((8.0 + m) * 320), "avg_hr": 145,
            "max_hr": 165, "estimated_training_load": 90, "avg_pace_sec_per_km": 320,
            "name": f"{tag}:{j}:{m}",
        } for m in range(3)]
        out.append((aid, today, {"activities": acts, "sleep": [], "hrv": [], "weight": []}))
    return out


def _crash_child(db_dir: str, tag: str, n_syncs: int, aids: list[str], outer_tx: bool, progress):
    import logging
    logging.getLogger().setLevel(logging.ERROR)
    db = DatabaseManager(db_name=DB_NAME, db_dir=Path(db_dir))
    payloads = _crash_payloads(tag, n_syncs, aids)
    emit = Emit()

    def go():
        for aid, today, p in payloads:
            persist_garmin_data(db, p, today, athlete_id=aid, emit=emit)
            progress.value += 1
    if outer_tx:
        with db.transaction():
            go()
            time.sleep(60)  # never reached in practice: parent kills us first
    else:
        go()
        time.sleep(60)


def phase_update_rollback_restart(work: Path, cfg: dict, res: dict) -> None:
    out: dict = {}
    rng = random.Random(f"{cfg['seed']}:upd")
    aids = [ds.athlete_id(i) for i in range(cfg["athletes"])]
    db, _ = open_db(work)
    # (a) updates: Garmin re-sync upsert of daily metrics + manual-entry preservation
    pairs = []
    for _ in range(cfg["update_count"]):
        a = ds.generate_athlete(cfg["seed"], rng.randrange(cfg["athletes"]), cfg["anchor"])
        pairs.append((a.athlete_id, rng.choice(a.syncs)[0]))
    lat: list[float] = []
    holder: dict = {}
    with measured(holder, "upd") as entry:
        for aid, d in pairs:
            t0 = time.perf_counter()
            db.save_daily_metric(date=d, hrv=77.7, athlete_id=aid)
            lat.append((time.perf_counter() - t0) * 1000)
    ok = sum(1 for aid, d in pairs if db.get_daily_metric(d, athlete_id=aid)["hrv_rmssd"] == 77.7)
    manual_pairs = [(aid, "2023-06-01") for aid in rng.sample(aids, min(100, len(aids)))]
    for aid, d in manual_pairs:
        db.save_daily_metric(date=d, soreness=3, mood=4, data_source="manual_entry", athlete_id=aid)
        db.save_daily_metric(date=d, hrv=55.0, rhr=50, athlete_id=aid)  # Garmin re-sync
    kept = sum(1 for aid, d in manual_pairs if db.conn.execute(
        "SELECT data_source, soreness, mood, hrv_rmssd FROM daily_metrics WHERE athlete_id=? AND date=?",
        (aid, d)).fetchone() == ("manual_entry", 3, 4, 55.0))
    out["updates"] = {"write_path": "DatabaseManager.save_daily_metric (ON CONFLICT upsert)",
                      "updates": len(pairs), "latency_autocommit": latency_summary(lat),
                      "values_verified": ok, "manual_rows_checked": len(manual_pairs),
                      "manual_provenance_and_subjective_fields_preserved": kept,
                      "resources": entry["resources"]}
    # (b) rollback: valid activities followed by one poisoned record in the same sync
    emit = Emit()
    lat = []
    fails = 0
    n_rb = cfg["rollback_syncs"]
    for j in range(n_rb):
        aid = aids[j % len(aids)]
        today = (date(2023, 1, 1) + timedelta(days=j % 300)).isoformat()
        acts = [{"activity_id": f"rb-{j}-{m}", "date": today, "activity_type": "running",
                 "distance_km": 10.0, "duration_sec": 3300, "avg_hr": 140, "max_hr": 160,
                 "estimated_training_load": 70, "name": f"rb:{j}:{m}"} for m in range(5)]
        acts.append({"activity_id": f"rb-{j}-bad", "date": today, "activity_type": "running",
                     "distance_km": "10,0km", "duration_sec": 3300, "name": f"rb:{j}:bad"})
        payload = {"activities": acts, "sleep": [], "hrv": [{"date": today, "rmssd": 50.0}],
                   "weight": []}
        t0 = time.perf_counter()
        try:
            persist_garmin_data(db, payload, today, athlete_id=aid, emit=emit)
        except PersistenceFailure:
            fails += 1
        lat.append((time.perf_counter() - t0) * 1000)
    leftover = db.conn.execute("SELECT COUNT(*) FROM training_log WHERE notes LIKE 'rb:%'").fetchone()[0]
    out["rollback"] = {"syncs_with_poisoned_record": n_rb, "persistence_failures": fails,
                       "rows_left_behind": leftover, "failing_tx_latency": latency_summary(lat),
                       "valid_records_discarded_with_the_batch": n_rb * 5,
                       "emit_outcomes": dict(emit.counts)}
    db.close()
    # (c) crash in the middle of an import, then restart and re-import
    ctx = mp.get_context("spawn")
    crash = {}
    for mode, outer in (("outer_transaction", True), ("per_sync_commit", False)):
        tag = f"crash_{mode}"
        n_syncs = cfg["crash_syncs"]
        progress = ctx.Value("i", 0)
        p = ctx.Process(target=_crash_child, args=(str(work), tag, n_syncs, aids[:50], outer, progress))
        p.start()
        t_wait = time.perf_counter()
        while progress.value < n_syncs // 2 and p.is_alive() and time.perf_counter() - t_wait < 600:
            time.sleep(0.01)
        done_before_kill = progress.value
        os.kill(p.pid, signal.SIGKILL)
        p.join()
        wal_before = sqlite_storage(work / DB_NAME)["wal_bytes"]
        t0 = time.perf_counter()
        db = DatabaseManager(db_name=DB_NAME, db_dir=work)
        reopen_ms = (time.perf_counter() - t0) * 1000
        integ = db.conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = len(db.conn.execute("PRAGMA foreign_key_check").fetchall())
        after_crash = db.conn.execute("SELECT COUNT(*) FROM training_log WHERE notes LIKE ?",
                                      (f"{tag}:%",)).fetchone()[0]
        emit = Emit()
        t1 = time.perf_counter()
        for aid, today, pl in _crash_payloads(tag, n_syncs, aids[:50]):
            persist_garmin_data(db, pl, today, athlete_id=aid, emit=emit)
        reimport_s = time.perf_counter() - t1
        final = db.conn.execute("SELECT COUNT(*), COUNT(DISTINCT garmin_activity_id) FROM training_log "
                                "WHERE notes LIKE ?", (f"{tag}:%",)).fetchone()
        db.close()
        crash[mode] = {
            "syncs_in_import": n_syncs, "syncs_done_in_child_before_sigkill": done_before_kill,
            "wal_bytes_after_kill": wal_before, "reopen_ms": round(reopen_ms, 1),
            "integrity_check": integ, "foreign_key_violations": fk,
            "rows_present_after_crash": after_crash,
            "expected_after_crash": 0 if outer else f"3 x committed syncs (~{3 * done_before_kill})",
            "reimport_s": round(reimport_s, 2), "rows_after_reimport": final[0],
            "distinct_ids_after_reimport": final[1], "expected_rows": 3 * n_syncs,
        }
    out["crash_restart"] = crash
    res["phase6_update_rollback_restart"] = out


# ── index cost, measured on a COPY of the full database ──────────────────────

def phase_index_cost(work: Path, cfg: dict, res: dict) -> None:
    src = sqlite3.connect(str(work / DB_NAME))
    src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    cdir = work / "index_copy"
    cdir.mkdir(exist_ok=True)
    dst = sqlite3.connect(str(cdir / DB_NAME))
    src.backup(dst)
    src.close()
    dst.close()
    db, _ = open_db(cdir)
    rng = random.Random(f"{cfg['seed']}:idx")
    sample = rng.sample([ds.athlete_id(i) for i in range(cfg["athletes"])],
                        min(cfg["query_sample"], cfg["athletes"]))
    out: dict = {"note": "measured on a disposable copy; the production schema is unchanged"}
    bench_queries(db, sample[:20], cfg["anchor"])  # warm
    out["queries_without_index"] = bench_queries(db, sample, cfg["anchor"])
    out["plans_without_index"] = capture_query_plans(db, sample[0], cfg["anchor"])

    pool = []
    i = 0
    while len(pool) < cfg["index_insert_rows"] * 2:
        pool.extend(ds.raw_training_rows(cfg["seed"], i, cfg["anchor"]))
        i += 1

    def ins(rows: list[tuple], label: str) -> dict:
        rows = [r[:13] + (f"{label}-{r[13]}",) + r[14:] for r in rows]
        lat = []
        t_all = time.perf_counter()
        for s in range(0, len(rows), 1000):
            t0 = time.perf_counter()
            db.conn.execute("BEGIN")
            db.conn.executemany(ds.TRAINING_INSERT_SQL, rows[s:s + 1000])
            db.conn.commit()
            lat.append((time.perf_counter() - t0) * 1000)
        wall = time.perf_counter() - t_all
        return {"rows": len(rows), "rows_per_s": round(len(rows) / wall, 1),
                "tx_latency_1000_rows": latency_summary(lat)}

    k = cfg["index_insert_rows"]
    out["insert_without_index"] = ins(pool[:k], "idxA")
    size0 = sqlite_storage(db.db_path)
    t0 = time.perf_counter()
    db.conn.execute("CREATE INDEX idx_stress_training_log_athlete_date ON training_log(athlete_id, date)")
    db.conn.commit()
    out["create_index_s"] = round(time.perf_counter() - t0, 2)
    db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    size1 = sqlite_storage(db.db_path)
    out["storage_before_index"] = size0
    out["storage_after_index"] = size1
    try:
        out["index_bytes_dbstat"] = db.conn.execute(
            "SELECT SUM(pgsize) FROM dbstat WHERE name='idx_stress_training_log_athlete_date'"
        ).fetchone()[0]
    except sqlite3.Error as e:
        out["index_bytes_dbstat"] = f"dbstat unavailable: {e}"
    out["insert_with_index"] = ins(pool[k:2 * k], "idxB")
    bench_queries(db, sample[:20], cfg["anchor"])
    out["queries_with_index"] = bench_queries(db, sample, cfg["anchor"])
    out["plans_with_index"] = capture_query_plans(db, sample[0], cfg["anchor"])
    db.close()
    shutil.rmtree(cdir, ignore_errors=True)
    res["index_cost_on_copy"] = out


# ── backup + restore through the real DatabaseManager.backup_database ────────

def phase_backup_restore(work: Path, cfg: dict, res: dict) -> None:
    """Hot backup via the product's backup_database(), a concurrent writer, then a restore check.

    backup_database() holds DatabaseManager._lock for the whole copy, so a writer that shares
    the DatabaseManager (the in-process app model) waits until the backup ends. The writer
    thread measures that stall. Restore = copy the backup file into a fresh directory and
    open it with DatabaseManager (the documented restore is a file copy).
    """
    import threading

    db, _ = open_db(work)
    probe = "bkprobe"  # writer rows go to a separate synthetic athlete, excluded from counts
    register_athletes(db, [probe])
    q = "SELECT COUNT(*) FROM {} WHERE athlete_id <> 'bkprobe'"
    before = {t: db.conn.execute(q.format(t)).fetchone()[0] for t in ("training_log", "daily_metrics")}
    stop = threading.Event()
    lat: list[float] = []
    errors: Counter = Counter()
    rng = random.Random(f"{cfg['seed']}:bk")

    def writer() -> None:
        n = 0
        while not stop.is_set():
            today = (cfg["anchor"] - timedelta(days=rng.randrange(365))).isoformat()
            p = _conc_payload(99, 0, n, today, rng)
            p["activities"][0]["name"] = f"bk:{n}"
            p["activities"][0]["activity_id"] = f"bk-{n}"
            n += 1
            t0 = time.perf_counter()
            try:
                persist_garmin_data(db, p, today, athlete_id=probe, emit=Emit())
            except PersistenceFailure as exc:
                errors[f"{type(exc.__cause__).__name__}: {exc.__cause__}"] += 1
            lat.append((time.perf_counter() - t0) * 1000)
            time.sleep(0.005)

    bdir = work / "backups"
    th = threading.Thread(target=writer)
    holder: dict = {}
    with measured(holder, "bk") as entry:
        th.start()
        time.sleep(0.2)
        t0 = time.perf_counter()
        path = db.backup_database(backup_dir=bdir, keep=30)
        backup_s = time.perf_counter() - t0
        time.sleep(0.2)
        stop.set()
        th.join()
    out: dict = {
        "write_path": "DatabaseManager.backup_database (sqlite3 online backup API + verify)",
        "backup_created": path is not None, "backup_s": round(backup_s, 2),
        "source_storage": sqlite_storage(db.db_path),
        "backup_bytes": path.stat().st_size if path else None,
        "concurrent_writer_latency": latency_summary(lat),
        "concurrent_writer_errors": dict(errors),
        "resources": entry["resources"],
    }
    db.close()
    if path:
        rdir = work / "restore"
        rdir.mkdir(exist_ok=True)
        shutil.copyfile(path, rdir / DB_NAME)
        t0 = time.perf_counter()
        rdb = DatabaseManager(db_name=DB_NAME, db_dir=rdir)
        out["restore_open_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        out["restore_integrity_check"] = rdb.conn.execute("PRAGMA integrity_check").fetchone()[0]
        out["restore_user_version"] = rdb.conn.execute("PRAGMA user_version").fetchone()[0]
        after = {t: rdb.conn.execute(q.format(t)).fetchone()[0] for t in ("training_log", "daily_metrics")}
        out["rows_before_backup_excl_probe"] = before
        out["rows_in_restored_copy_excl_probe"] = after
        out["restore_row_mismatch"] = sum(abs(before[t] - after[t]) for t in before)
        rdb.close()
        shutil.rmtree(rdir, ignore_errors=True)
    shutil.rmtree(bdir, ignore_errors=True)
    res["backup_restore"] = out
