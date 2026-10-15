"""Throwaway PostgreSQL comparison — NOT the TITAN backend.

TITAN's PostgreSQL path is disabled (``get_database_manager(backend='postgres')`` raises
NotImplementedError; ADR-0044 parity is open). This module starts a disposable local
cluster, creates a HAND-TRANSLATED equivalent of ``training_log`` / ``daily_metrics`` /
``athletes`` (same columns, same unique keys, ``date`` kept as TEXT like SQLite), copies the
rows the SQLite run stored, and runs the same query shapes. It also tests connection
cost (what pooling saves), transactions under concurrency and Row-Level Security.
"""
from __future__ import annotations

import contextlib
import random
import shutil
import subprocess
import threading
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import dataset as ds
from stress_common import latency_summary, measured

PG_BIN = Path("/usr/lib/postgresql/16/bin")
PORT = 55432

SCHEMA = """
CREATE TABLE athletes (
    athlete_id   text PRIMARY KEY,
    display_name text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE training_log (
    id bigserial PRIMARY KEY,
    athlete_id text NOT NULL DEFAULT 'owner',
    date text NOT NULL,
    session_type text, distance_km double precision, duration_sec integer,
    avg_hr integer, max_hr integer, rpe integer, training_load integer,
    shoe_id bigint, surface text, temperature_c double precision,
    zone_distribution text, notes text, garmin_activity_id text,
    quality_flag text, avg_pace_sec_per_km double precision
);
CREATE UNIQUE INDEX idx_training_log_garmin_id ON training_log (garmin_activity_id)
    WHERE garmin_activity_id IS NOT NULL;
CREATE TABLE daily_metrics (
    id bigserial PRIMARY KEY,
    athlete_id text NOT NULL DEFAULT 'owner',
    date text NOT NULL,
    weight_kg double precision, hrv_rmssd double precision, resting_hr integer,
    sleep_hours double precision, sleep_quality integer, soreness integer,
    fatigue_level integer, mood integer, notes text,
    data_source text NOT NULL DEFAULT 'garmin_api',
    hrr_60 integer, hrr_120 integer, glycogen_debt double precision, quality_flag text,
    UNIQUE (athlete_id, date)
);
"""

TL_COLS = ("athlete_id", "date", "session_type", "distance_km", "duration_sec", "avg_hr", "max_hr",
           "rpe", "training_load", "notes", "garmin_activity_id", "quality_flag",
           "avg_pace_sec_per_km")
DM_COLS = ("athlete_id", "date", "weight_kg", "hrv_rmssd", "resting_hr", "sleep_hours",
           "sleep_quality", "data_source", "quality_flag")

Q_RECENT = ("SELECT date, session_type, distance_km, duration_sec, avg_hr, training_load, "
            "avg_pace_sec_per_km FROM training_log WHERE athlete_id = %s ORDER BY date DESC LIMIT 90")
Q_RANGE = ("SELECT date, session_type, distance_km, duration_sec, avg_hr, training_load "
           "FROM training_log WHERE athlete_id = %s AND date BETWEEN %s AND %s ORDER BY date")
Q_LOAD = ("SELECT date, SUM(training_load) FROM training_log WHERE athlete_id = %s "
          "AND training_load IS NOT NULL AND training_load > 0 "
          "AND date >= to_char(current_date - %s::int, 'YYYY-MM-DD') GROUP BY date ORDER BY date")
Q_HRV = ("SELECT date, hrv_rmssd FROM daily_metrics WHERE athlete_id = %s AND hrv_rmssd IS NOT NULL "
         "AND hrv_rmssd > 0 ORDER BY date DESC LIMIT 28")


class Cluster:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.data = root / "data"
        self.log = root / "server.log"

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(a) for a in args], user="postgres", capture_output=True,
                              text=True, check=True, timeout=300)

    def init_start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        shutil.chown(self.root, "postgres", "postgres")
        self._run(PG_BIN / "initdb", "-D", self.data, "-A", "trust", "-U", "stress",
                  "--no-sync", "-E", "UTF8")
        self.start()

    def start(self) -> None:
        self._run(PG_BIN / "pg_ctl", "-D", self.data, "-l", self.log, "-w", "-o",
                  f"-p {PORT} -c unix_socket_directories='' -c listen_addresses=127.0.0.1 "
                  "-c max_connections=50",
                  "start")

    def stop(self) -> None:
        self._run(PG_BIN / "pg_ctl", "-D", self.data, "-m", "fast", "-w", "stop")

    def destroy(self) -> None:
        with contextlib.suppress(subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            self.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def conninfo(self, user: str = "stress", dbname: str = "stress") -> str:
        # TCP on loopback: the worktree path is too long for a Unix socket (107-byte limit)
        return f"host=127.0.0.1 port={PORT} user={user} dbname={dbname}"


def _pg_bench(conn, athletes: list[str], anchor: date) -> dict:
    lat = {"recent_activities_90": [], "range_30d": [], "training_load_history_210d": [],
           "hrv_history_28": []}
    start = (anchor - timedelta(days=30)).isoformat()
    end = anchor.isoformat()
    with conn.cursor() as cur:
        for aid in athletes:
            for name, sql, params in (
                ("recent_activities_90", Q_RECENT, (aid,)),
                ("range_30d", Q_RANGE, (aid, start, end)),
                ("training_load_history_210d", Q_LOAD, (aid, 210)),
                ("hrv_history_28", Q_HRV, (aid,)),
            ):
                t0 = time.perf_counter()
                cur.execute(sql, params)
                cur.fetchall()
                lat[name].append((time.perf_counter() - t0) * 1000)
    out = {k: latency_summary(v) for k, v in lat.items()}
    out["athletes_sampled"] = len(athletes)
    return out


def _explain(conn, aid: str, anchor: date) -> list[dict]:
    out = []
    with conn.cursor() as cur:
        for sql, params in ((Q_RECENT, (aid,)),
                            (Q_RANGE, (aid, (anchor - timedelta(days=30)).isoformat(), anchor.isoformat())),
                            (Q_LOAD, (aid, 210)), (Q_HRV, (aid,))):
            cur.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) " + sql, params)
            plan = [r[0] for r in cur.fetchall()]
            out.append({"sql": sql[:160], "plan": plan,
                        "seq_scan": any("Seq Scan" in p for p in plan)})
    return out


def run_pg(sqlite_db_path: Path, work: Path, cfg: dict, res: dict) -> None:
    import psycopg

    cl = Cluster(work / "pg")
    out: dict = {"label": "NOT the TITAN backend - hand-translated equivalent schema in a "
                          "throwaway local PostgreSQL 16 cluster"}
    try:
        t0 = time.perf_counter()
        cl.init_start()
        out["cluster_init_start_s"] = round(time.perf_counter() - t0, 2)
        with psycopg.connect(cl.conninfo(dbname="postgres"), autocommit=True) as c:
            c.execute("CREATE DATABASE stress")
        conn = psycopg.connect(cl.conninfo(), autocommit=True)
        out["settings"] = {k: conn.execute(f"SHOW {k}").fetchone()[0] for k in (
            "server_version", "shared_buffers", "synchronous_commit", "fsync", "wal_level",
            "max_connections", "work_mem")}
        conn.execute(SCHEMA)

        # ── load: COPY the rows the SQLite run stored ─────────────────────────
        import sqlite3
        src = sqlite3.connect(f"file:{sqlite_db_path}?mode=ro", uri=True)
        holder: dict = {}
        with measured(holder, "copy", extra_proc_names=("postgres",)) as entry:
            t0 = time.perf_counter()
            with conn.cursor() as cur:
                with cur.copy("COPY athletes (athlete_id, display_name) FROM STDIN") as cp:
                    for (a,) in src.execute("SELECT athlete_id FROM athletes"):
                        cp.write_row((a, a))
                with cur.copy(f"COPY training_log ({', '.join(TL_COLS)}) FROM STDIN") as cp:
                    for r in src.execute(f"SELECT {', '.join(TL_COLS)} FROM training_log"):
                        cp.write_row(tuple(None if v is None else str(v) for v in r))
                with cur.copy(f"COPY daily_metrics ({', '.join(DM_COLS)}) FROM STDIN") as cp:
                    for r in src.execute(f"SELECT {', '.join(DM_COLS)} FROM daily_metrics"):
                        cp.write_row(r)
            copy_s = time.perf_counter() - t0
            conn.execute("ANALYZE")
        src.close()
        n_tl = conn.execute("SELECT count(*) FROM training_log").fetchone()[0]
        n_dm = conn.execute("SELECT count(*) FROM daily_metrics").fetchone()[0]
        out["copy_load"] = {"training_log_rows": n_tl, "daily_metrics_rows": n_dm,
                            "wall_s": round(copy_s, 2),
                            "rows_per_s": round((n_tl + n_dm) / copy_s, 1),
                            "resources": entry["resources"]}

        def sizes() -> dict:
            return {
                "database_bytes": conn.execute("SELECT pg_database_size('stress')").fetchone()[0],
                "training_log_total_bytes": conn.execute(
                    "SELECT pg_total_relation_size('training_log')").fetchone()[0],
                "daily_metrics_total_bytes": conn.execute(
                    "SELECT pg_total_relation_size('daily_metrics')").fetchone()[0],
            }
        out["storage_without_index"] = sizes()

        rng = random.Random(f"{cfg['seed']}:q")
        sample = rng.sample([ds.athlete_id(i) for i in range(cfg["athletes"])],
                            min(cfg["query_sample"], cfg["athletes"]))
        anchor = cfg["anchor"]

        # ── queries: cold (after restart) and warm, without and with index ───
        conn.close()
        cl.stop()
        cl.start()
        conn = psycopg.connect(cl.conninfo(), autocommit=True)
        out["queries_without_index_cold_after_restart"] = _pg_bench(conn, sample, anchor)
        out["queries_without_index_warm"] = _pg_bench(conn, sample, anchor)
        out["plans_without_index"] = _explain(conn, sample[0], anchor)
        t0 = time.perf_counter()
        conn.execute("CREATE INDEX idx_tl_athlete_date ON training_log (athlete_id, date)")
        out["create_index_s"] = round(time.perf_counter() - t0, 2)
        conn.execute("ANALYZE training_log")
        out["storage_with_index"] = sizes()
        _pg_bench(conn, sample[:20], anchor)
        out["queries_with_index_warm"] = _pg_bench(conn, sample, anchor)
        out["plans_with_index"] = _explain(conn, sample[0], anchor)

        # ── batch insert sizes (index present) ───────────────────────────────
        pool: list[tuple] = []
        i = 0
        need = 10_000 if cfg["small"] else 100_000
        while len(pool) < need:
            pool.extend(ds.raw_training_rows(cfg["seed"], 50_000 + i, anchor))
            i += 1
        ins_sql = (f"INSERT INTO training_log ({', '.join(TL_COLS)}) VALUES "
                   f"({', '.join(['%s'] * len(TL_COLS))}) ON CONFLICT DO NOTHING")

        def row(r, label):
            return (r[0], r[1], r[2], r[3], r[4], r[5], r[6], None, r[8], r[12],
                    f"{label}-{r[13]}", None, r[15])
        bulk = []
        for label, batch, nrows in (("b1", 1, need // 20), ("b100", 100, need),
                                    ("b1000", 1000, need)):
            rows = [row(r, label) for r in pool[:nrows]]
            lat = []
            with measured(holder, label, extra_proc_names=("postgres",)) as entry:
                t_all = time.perf_counter()
                with psycopg.connect(cl.conninfo()) as c2:
                    for s in range(0, nrows, batch):
                        t0 = time.perf_counter()
                        with c2.cursor() as cur:
                            cur.executemany(ins_sql, rows[s:s + batch])
                        c2.commit()
                        lat.append((time.perf_counter() - t0) * 1000)
                wall = time.perf_counter() - t_all
            bulk.append({"label": label, "batch_rows_per_tx": batch, "rows": nrows,
                         "rows_per_s": round(nrows / wall, 1), "tx_per_s": round(len(lat) / wall, 1),
                         "tx_latency": latency_summary(lat), "resources": entry["resources"]})
        out["batch_insert"] = bulk

        # ── connection cost (what a pool saves) ─────────────────────────────
        n_ops = 200 if cfg["small"] else 1000
        lat_new, lat_persist = [], []
        for k in range(n_ops):
            aid = sample[k % len(sample)]
            t0 = time.perf_counter()
            with psycopg.connect(cl.conninfo(), autocommit=True) as c3:
                c3.execute(Q_HRV, (aid,)).fetchall()
            lat_new.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            conn.execute(Q_HRV, (aid,)).fetchall()
            lat_persist.append((time.perf_counter() - t0) * 1000)
        out["connection_cost"] = {"connect_per_op": latency_summary(lat_new),
                                  "persistent_connection": latency_summary(lat_persist),
                                  "note": "psycopg_pool not installed; a pool removes the "
                                          "connect cost shown in connect_per_op"}

        # ── concurrency: threads, one connection each ────────────────────────
        conc_athletes = rng.sample([ds.athlete_id(i) for i in range(cfg["athletes"])],
                                   min(500, cfg["athletes"]))
        runs = []
        for cfg_idx, (workers, wr, sync_off) in enumerate(
                [(1, 0.2, False), (2, 0.2, False), (4, 0.2, False), (8, 0.2, False),
                 (8, 1.0, False), (8, 1.0, True)], start=1):
            results: list[dict] = []
            lock = threading.Lock()

            def worker(wid, cfg_idx=cfg_idx, wr=wr, results=results, lock=lock, so=sync_off):
                r = _pg_worker(cl.conninfo(), cfg_idx, wid, cfg["conc_duration"], wr,
                               conc_athletes, cfg["seed"], anchor, so)
                with lock:
                    results.append(r)
            with measured(holder, f"pgc{cfg_idx}", extra_proc_names=("postgres",)) as entry:
                ths = [threading.Thread(target=worker, args=(k,)) for k in range(workers)]
                for t in ths:
                    t.start()
                for t in ths:
                    t.join()
            stored = conn.execute("SELECT count(*) FROM training_log WHERE notes LIKE %s",
                                  (f"pgconc{cfg_idx}:%",)).fetchone()[0]
            lat_r = [x for r in results for x in r["lat_r"]]
            lat_w = [x for r in results for x in r["lat_w"]]
            errs: Counter = Counter()
            for r in results:
                errs.update(r["errors"])
            ok = sum(r["writes_ok"] for r in results)
            dur = cfg["conc_duration"]
            runs.append({"workers": workers, "write_ratio": wr, "duration_s": dur,
                         "synchronous_commit": "off (closer to SQLite synchronous=NORMAL)"
                         if sync_off else "on (default)",
                         "reads": len(lat_r), "writes_ok": ok,
                         "writes_failed": sum(r["writes_attempted"] for r in results) - ok,
                         "read_ops_per_s": round(len(lat_r) / dur, 1),
                         "write_tx_per_s": round(ok / dur, 1),
                         "read_latency": latency_summary(lat_r), "write_latency": latency_summary(lat_w),
                         "errors": dict(errs), "lost_or_phantom_rows": stored - ok,
                         "resources": entry["resources"]})
            print(f"  pg conc w={workers} wr={wr}: reads/s={runs[-1]['read_ops_per_s']} "
                  f"writes/s={runs[-1]['write_tx_per_s']} errors={dict(errs)}", flush=True)
        out["concurrency_threads_own_connection"] = runs

        # ── Row-Level Security for athlete isolation ─────────────────────────
        out["rls"] = _rls(conn, cl, sample, anchor)
        conn.close()
    except Exception as exc:  # noqa: BLE001 - recorded, SQLite results stay valid
        out["error"] = f"{type(exc).__name__}: {exc}"
        with contextlib.suppress(OSError):
            out["server_log_tail"] = cl.log.read_text()[-2000:]
    finally:
        cl.destroy()
        out["cluster_destroyed"] = not cl.root.exists()
    res["postgres_comparison"] = out


def _pg_worker(conninfo, cfg_idx, wid, duration, wr, athletes, seed, anchor, sync_off) -> dict:
    import psycopg
    rng = random.Random(f"{seed}:pg{cfg_idx}:{wid}")
    lat_r, lat_w = [], []
    errors: Counter = Counter()
    ok = n = 0
    with psycopg.connect(conninfo, autocommit=True) as c:
        if sync_off:
            c.execute("SET synchronous_commit = off")
        end = time.perf_counter() + duration
        while time.perf_counter() < end:
            aid = rng.choice(athletes)
            today = (anchor - timedelta(days=rng.randrange(365))).isoformat()
            t0 = time.perf_counter()
            try:
                if rng.random() < wr:
                    n += 1
                    with c.transaction(), c.cursor() as cur:
                        cur.execute(
                            "INSERT INTO training_log (athlete_id, date, session_type, distance_km, "
                            "duration_sec, avg_hr, max_hr, training_load, notes, garmin_activity_id) "
                            "VALUES (%s, %s, 'EASY', 10.0, 3300, 140, 160, 80, %s, %s) "
                            "ON CONFLICT DO NOTHING",
                            (aid, today, f"pgconc{cfg_idx}:{wid}:{n}", f"pg-{cfg_idx}-{wid}-{n}"))
                        cur.execute(
                            "INSERT INTO daily_metrics (athlete_id, date, hrv_rmssd, resting_hr) "
                            "VALUES (%s, %s, 60, 50) ON CONFLICT (athlete_id, date) DO UPDATE SET "
                            "hrv_rmssd = EXCLUDED.hrv_rmssd, resting_hr = EXCLUDED.resting_hr",
                            (aid, today))
                    ok += 1
                    lat_w.append((time.perf_counter() - t0) * 1000)
                else:
                    sql, params = rng.choice(((Q_RECENT, (aid,)), (Q_LOAD, (aid, 210)), (Q_HRV, (aid,))))
                    with c.transaction(), c.cursor() as cur:
                        cur.execute(sql, params)
                        cur.fetchall()
                    lat_r.append((time.perf_counter() - t0) * 1000)
            except psycopg.Error as e:
                errors[f"{type(e).__name__}"] += 1
    return {"lat_r": lat_r, "lat_w": lat_w, "errors": dict(errors), "writes_ok": ok,
            "writes_attempted": n}


def _rls(conn, cl: Cluster, sample: list[str], anchor: date) -> dict:
    import psycopg
    conn.execute("CREATE ROLE titan_app LOGIN")
    conn.execute("GRANT SELECT, INSERT ON training_log, daily_metrics TO titan_app")
    conn.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO titan_app")
    for t in ("training_log", "daily_metrics"):
        conn.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        conn.execute(f"CREATE POLICY athlete_isolation ON {t} "
                     "USING (athlete_id = current_setting('app.athlete_id', true)) "
                     "WITH CHECK (athlete_id = current_setting('app.athlete_id', true))")
    expected = dict(conn.execute(
        "SELECT athlete_id, count(*) FROM training_log WHERE athlete_id = ANY(%s) GROUP BY athlete_id",
        (sample,)).fetchall())
    out: dict = {"policy": "USING/WITH CHECK athlete_id = current_setting('app.athlete_id')"}
    leaks = wrong_counts = 0
    lat_rls, lat_rls_where = [], []
    with psycopg.connect(cl.conninfo(user="titan_app")) as app:
        unscoped = app.execute("SELECT count(*) FROM training_log").fetchone()[0]
        app.commit()
        out["rows_visible_without_app_athlete_id"] = unscoped
        for aid in sample:
            with app.transaction():
                app.execute("SELECT set_config('app.athlete_id', %s, true)", (aid,))
                t0 = time.perf_counter()
                rows = app.execute("SELECT athlete_id FROM training_log").fetchall()
                lat_rls.append((time.perf_counter() - t0) * 1000)
                t0 = time.perf_counter()
                app.execute(Q_RECENT, (aid,)).fetchall()
                lat_rls_where.append((time.perf_counter() - t0) * 1000)
            leaks += sum(1 for (a,) in rows if a != aid)
            wrong_counts += int(len(rows) != expected.get(aid, 0))
        try:
            with app.transaction():
                app.execute("SELECT set_config('app.athlete_id', %s, true)", (sample[0],))
                app.execute("INSERT INTO training_log (athlete_id, date) VALUES (%s, '2026-01-01')",
                            (sample[1],))
            out["cross_athlete_insert"] = "ACCEPTED (unexpected)"
        except psycopg.Error as e:
            out["cross_athlete_insert"] = f"rejected: {type(e).__name__}"
    lat_super = []
    for aid in sample:
        t0 = time.perf_counter()
        conn.execute(Q_RECENT, (aid,)).fetchall()
        lat_super.append((time.perf_counter() - t0) * 1000)
    out.update({
        "athletes_checked": len(sample), "foreign_rows_returned": leaks,
        "athletes_with_wrong_row_count": wrong_counts,
        "select_all_under_rls_latency": latency_summary(lat_rls),
        "recent_90_with_rls_latency": latency_summary(lat_rls_where),
        "recent_90_superuser_no_rls_latency": latency_summary(lat_super),
    })
    return out
