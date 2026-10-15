#!/usr/bin/env python
"""Turn a stress-run results.json into a small summary JSON and Markdown tables.

    python scripts/stress/summarize.py .stress_tmp/full/results.json \
        --json scripts/stress/results/full_summary.json --md .stress_tmp/full/summary.md

The summary keeps only the numbers the report cites (latencies, throughput, resources,
errors, verdicts), so it stays small enough to commit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def lat(d: dict | None) -> str:
    if not d or not d.get("n"):
        return "- | - | - | -"
    return f"{d['p50_ms']} | {d['p95_ms']} | {d['p99_ms']} | {d['max_ms']}"


def res_cols(r: dict | None) -> str:
    if not r:
        return "- | -"
    return f"{r.get('rss_max_mb')} / {r.get('rss_mean_mb')} | {r.get('cpu_self_pct_of_one_core')}"


def mb(b: int | None) -> str:
    return "-" if b is None else f"{b / 2**20:.1f}"


def build(res: dict) -> tuple[dict, list[str]]:
    md: list[str] = []
    s: dict = {"environment": {k: v for k, v in res["environment"].items()
                               if k not in ("indexes_on_core_tables", "training_log_ddl")},
               "config": res["config"], "phase_wall_s": res.get("phase_wall_s"),
               "total_wall_s": res.get("total_wall_s")}

    load = res["phase2_main_load"]
    s["main_load"] = {k: load[k] for k in (
        "wall_s", "generation_s", "syncs", "syncs_failed", "sync_failure_causes", "sync_latency",
        "syncs_per_s_persist_only", "training_log_rows", "daily_metrics_rows",
        "activity_rows_per_s_persist_only", "activity_rows_per_s_incl_generation", "totals",
        "activities_per_athlete_distribution", "storage", "resources", "emit_outcomes")}
    md += ["### Κύρια φόρτωση (persist_garmin_data)", "",
           "| μέγεθος | τιμή |", "|---|---|"]
    for k in ("syncs", "syncs_failed", "training_log_rows", "daily_metrics_rows",
              "syncs_per_s_persist_only", "activity_rows_per_s_persist_only",
              "activity_rows_per_s_incl_generation", "wall_s"):
        md.append(f"| {k} | {load[k]} |")
    md.append(f"| sync p50/p95/p99/max ms | {lat(load['sync_latency']).replace(' | ', ' / ')} |")
    md.append(f"| RSS max/mean MB, CPU % | {res_cols(load['resources']).replace(' | ', ', ')} |")
    md.append("")

    growth = res.get("phase7_growth", [])
    s["growth"] = [{k: g[k] for k in ("fraction", "athletes_loaded", "training_log_rows",
                                       "daily_metrics_rows", "storage", "segment_sync_latency",
                                       "segment_syncs_per_s", "segment_activity_rows_per_s",
                                       "databasemanager_open_ms")}
                   | {"queries": {q: v for q, v in g["queries_warmish"].items()
                                  if isinstance(v, dict) and "p95_ms" in v}}
                   for g in growth]
    md += ["### Βήματα ανάπτυξης", "",
           "| % | rows training_log | storage MB | sync p95 ms | syncs/s | ctl_atl_tsb p50/p95/p99 ms "
           "| recent_90 p95 | range_30d p95 | hrv_28 p95 | open ms |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for g in growth:
        q = g["queries_warmish"]
        c = q["ctl_atl_tsb"]
        md.append(f"| {int(g['fraction'] * 100)} | {g['training_log_rows']} | "
                  f"{mb(g['storage']['total_bytes'])} | {g['segment_sync_latency']['p95_ms']} | "
                  f"{g['segment_syncs_per_s']} | {c['p50_ms']}/{c['p95_ms']}/{c['p99_ms']} | "
                  f"{q['recent_activities_90']['p95_ms']} | {q['range_30d_raw_sql']['p95_ms']} | "
                  f"{q['hrv_history_28']['p95_ms']} | {g['databasemanager_open_ms']} |")
    md.append("")

    q3 = res.get("phase3_queries", {})
    s["queries"] = {k: q3.get(k) for k in ("os_page_cache_dropped", "databasemanager_open_ms_cold",
                                            "databasemanager_open_ms_warm", "cold_pass", "warm_pass")}
    s["query_plans"] = q3.get("query_plans")
    md += ["### Ερωτήματα στο 100% (cold / warm)", "",
           "| ερώτημα | cold p50 | p95 | p99 | max | warm p50 | p95 | p99 | max |",
           "|---|---|---|---|---|---|---|---|---|"]
    for name, v in q3.get("warm_pass", {}).items():
        if isinstance(v, dict) and "p95_ms" in v:
            md.append(f"| {name} | {lat(q3['cold_pass'].get(name))} | {lat(v)} |")
    md.append("")

    ic = res.get("index_cost_on_copy", {})
    s["index_cost"] = {k: ic.get(k) for k in (
        "insert_without_index", "insert_with_index", "create_index_s", "storage_before_index",
        "storage_after_index", "index_bytes_dbstat")}
    s["index_cost"]["queries_without_index"] = ic.get("queries_without_index")
    s["index_cost"]["queries_with_index"] = ic.get("queries_with_index")
    s["index_cost"]["plans_with_index"] = ic.get("plans_with_index")
    if ic:
        md += ["### Κόστος ευρετηρίου (αντίγραφο)", "",
               "| ερώτημα | χωρίς p50/p95/p99 | με (athlete_id, date) p50/p95/p99 |", "|---|---|---|"]
        for name, v in ic["queries_without_index"].items():
            if isinstance(v, dict) and "p95_ms" in v:
                w = ic["queries_with_index"][name]
                md.append(f"| {name} | {v['p50_ms']}/{v['p95_ms']}/{v['p99_ms']} | "
                          f"{w['p50_ms']}/{w['p95_ms']}/{w['p99_ms']} |")
        md.append(f"\ninsert rows/s χωρίς / με: {ic['insert_without_index']['rows_per_s']} / "
                  f"{ic['insert_with_index']['rows_per_s']}; CREATE INDEX {ic['create_index_s']} s; "
                  f"index bytes {ic.get('index_bytes_dbstat')}\n")

    b = res.get("phase1_bulk_insert")
    if b:
        s["bulk"] = b["runs"]
        md += ["### Μαζικές εισαγωγές", "",
               "| run | path | rows/tx | rows | rows/s | tx/s | tx p50/p95/p99 ms | RSS max MB |",
               "|---|---|---|---|---|---|---|---|"]
        for r in b["runs"]:
            t = r["tx_latency"]
            md.append(f"| {r['label']} | {r['path']} ({r['synchronous']}) | {r['batch_rows_per_tx']} | "
                      f"{r['rows']} | {r['rows_per_s']} | {r['tx_per_s']} | "
                      f"{t['p50_ms']}/{t['p95_ms']}/{t['p99_ms']} | {r['resources']['rss_max_mb']} |")
        md.append("")

    rs = res.get("phase4_resync", {})
    s["resync"] = rs
    if rs:
        md += ["### Επαναλαμβανόμενοι συγχρονισμοί", "",
               "| pass | athletes | syncs | failed | new training_log | new daily_metrics | p50/p95/p99 ms | syncs/s |",
               "|---|---|---|---|---|---|---|---|"]
        for p in rs["passes"]:
            md.append(f"| {p['sync_pass']} | {p['athletes']} | {p['syncs']} | {p['syncs_failed']} | "
                      f"{p['new_training_log_rows']} | {p['new_daily_metrics_rows']} | "
                      f"{p['sync_latency']['p50_ms']}/{p['sync_latency']['p95_ms']}/"
                      f"{p['sync_latency']['p99_ms']} | {p['syncs_per_s']} |")
        md.append("")

    conc = res.get("phase5_concurrency", {}).get("runs", [])
    s["concurrency"] = [{k: r[k] for k in r if k != "open_ms_per_process"} for r in conc]
    if conc:
        md += ["### Ταυτοχρονισμός SQLite", "",
               "| mode | workers | write ratio | reads/s | writes/s | read p50/p95/p99 | write p50/p95/p99 "
               "| locked | failed writes | lost/phantom |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in conc:
            md.append(f"| {r['mode']} | {r['workers']} | {r['write_ratio']} | {r['read_ops_per_s']} | "
                      f"{r['write_tx_per_s']} | {_l3(r['read_latency'])} | {_l3(r['write_latency'])} | "
                      f"{r['database_is_locked_errors']} | {r['writes_failed']} | {r['lost_or_phantom_rows']} |")
        md.append("")

    s["update_rollback_restart"] = res.get("phase6_update_rollback_restart")
    s["backup_restore"] = res.get("backup_restore")
    s["verification"] = {k: v for k, v in res.get("verification", {}).items()
                         if k not in ("activity_anomaly_expected", "daily_anomaly_expected")}
    s["read_path_load_anomalies"] = res.get("read_path_load_anomalies")
    s["leakage"] = res.get("leakage")
    s["storage_after_load_and_checkpoint"] = res.get("storage_after_load_and_checkpoint")
    s["log_action_counts"] = res.get("log_action_counts")

    pg = res.get("postgres_comparison")
    if pg:
        s["postgres"] = {k: v for k, v in pg.items() if k not in ("plans_without_index",)}
        s["postgres"]["plans_without_index"] = pg.get("plans_without_index")
        if "error" not in pg:
            md += ["### PostgreSQL (όχι backend του TITAN)", "",
                   "| ερώτημα | cold χωρίς idx p95 | warm χωρίς idx p50/p95/p99 | warm με idx p50/p95/p99 |",
                   "|---|---|---|---|"]
            for name, v in pg["queries_without_index_warm"].items():
                if isinstance(v, dict) and "p95_ms" in v:
                    c = pg["queries_without_index_cold_after_restart"][name]
                    w = pg["queries_with_index_warm"][name]
                    md.append(f"| {name} | {c['p95_ms']} | {_l3(v)} | {_l3(w)} |")
            md += ["", "| PG conc workers | write ratio | sync commit | reads/s | writes/s | read p95 | "
                   "write p95 | errors | lost |", "|---|---|---|---|---|---|---|---|---|"]
            for r in pg["concurrency_threads_own_connection"]:
                md.append(f"| {r['workers']} | {r['write_ratio']} | {r['synchronous_commit']} | "
                          f"{r['read_ops_per_s']} | {r['write_tx_per_s']} | "
                          f"{r['read_latency'].get('p95_ms', '-')} | {r['write_latency'].get('p95_ms', '-')} | "
                          f"{r['errors']} | {r['lost_or_phantom_rows']} |")
            md.append("")

    s["thresholds_evaluation"] = res.get("thresholds_evaluation")
    md += ["### Κατώφλια", "", "| id | πηγή | μέτρηση | όριο | παρατηρήθηκε | ετυμηγορία |",
           "|---|---|---|---|---|---|"]
    for c in res.get("thresholds_evaluation", []):
        lim = c.get("limit_ms", c.get("limit_mb", c.get("limit")))
        unit = " ms" if "limit_ms" in c else (" MB" if "limit_mb" in c else "")
        md.append(f"| {c['id']} | {c['source']} | {c['metric']} | {c['op']} {lim}{unit} | "
                  f"{c['observed']} | {c['verdict']} |")
    return s, md


def _l3(d: dict) -> str:
    if not d or not d.get("n"):
        return "-"
    return f"{d['p50_ms']}/{d['p95_ms']}/{d['p99_ms']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--json", required=True)
    ap.add_argument("--md", required=True)
    a = ap.parse_args()
    res = json.loads(Path(a.results).read_text())
    s, md = build(res)
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(s, indent=1, default=str))
    Path(a.md).write_text("\n".join(md) + "\n")
    print(f"wrote {a.json} ({Path(a.json).stat().st_size} bytes) and {a.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
