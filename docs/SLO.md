# TITAN OS — Service Level Objectives

**Version:** 1.0
**Date:** 2026-03-29
**Owner:** Architect
**Status:** Active

---

## Scope

This document defines Service Level Objectives (SLOs) for TITAN OS v5.8.x operating in
single-athlete, self-hosted mode. SLOs are internal engineering targets. They inform
alerting thresholds, runbook triggers, and Phase 8 readiness criteria.

---

## SLO-01 — Garmin Sync Freshness

| Field | Value |
|-------|-------|
| **Objective** | At least one successful Garmin sync per 6-hour window |
| **Target** | ≥ 99% of 6-hour windows contain a non-zero sync result |
| **Measurement window** | Rolling 30 days |
| **Alert threshold** | Three consecutive failed or empty syncs (`GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT`) → `garmin_api_degraded` CRITICAL event |
| **Runbook** | `docs/runbooks/garmin-sync-failure.md` |
| **Related ADR** | ADR-0050 |

---

## SLO-02 — Governance Pipeline Latency

| Field | Value |
|-------|-------|
| **Objective** | Full governance evaluation completes within 2 seconds |
| **Target** | P99 latency ≤ 2,000 ms |
| **Measurement window** | Per-session |
| **Alert threshold** | Any single evaluation > 5,000 ms → structured warning event |
| **Related ADR** | ADR-0009 |

---

## SLO-03 — Morning Briefing Delivery

| Field | Value |
|-------|-------|
| **Objective** | Telegram morning briefing delivered within 5 minutes of scheduled 07:00 |
| **Target** | ≥ 95% of scheduled briefings delivered by 07:05 UTC |
| **Measurement window** | Rolling 30 days |
| **Alert threshold** | Briefing not delivered by 07:10 → operator alert |
| **Runbook** | `docs/runbooks/governance-hard-stop-unexpected.md` (for safety-gate-caused delays) |

---

## SLO-04 — Database Write Availability

| Field | Value |
|-------|-------|
| **Objective** | All governance decisions and training log writes succeed |
| **Target** | Zero unhandled write failures in `governance_outcomes` and `training_log` tables |
| **Measurement window** | Continuous |
| **Alert threshold** | Any persistence failure → `DailyCoach` enters degraded-conservative mode (ADR-0020) |
| **Runbook** | `docs/runbooks/database-recovery.md` |
| **Related ADR** | ADR-0020 |

---

## SLO-05 — Safety Gate Non-Bypass

| Field | Value |
|-------|-------|
| **Objective** | No governance hard-stop gate (H1–H6) is bypassed under any code path |
| **Target** | 100% — zero bypass events in production |
| **Measurement window** | Continuous |
| **Alert threshold** | Any detection of gate bypass → P0 incident, immediate stop-the-line |
| **Verification** | `tests/test_p0_safety_gates.py`, `tests/test_governance_integration.py` |
| **Related ADR** | ADR-0009 |

---

## SLO-06 — ML Shadow Model Divergence

| Field | Value |
|-------|-------|
| **Objective** | Load prediction shadow model RMSE stays within 15% of baseline over 90 days |
| **Target** | Rolling 90-day RMSE ≤ 1.15 × baseline RMSE |
| **Measurement window** | Rolling 90 days |
| **Alert threshold** | RMSE exceeds threshold → ADR-0014 promotion review. Not automated: no drift event is emitted yet |
| **Related ADR** | ADR-0014, ADR-0033 |

---

## SLO-07 — Storage Read Latency (advisory)

| Field | Value |
|-------|-------|
| **Objective** | Athlete-scoped reads of `training_log` stay fast as the history grows |
| **Target** | `get_ctl_atl_tsb` p95 ≤ 100 ms; an athlete-scoped date-window read p95 ≤ 50 ms at realistic volume (≤ 250 ms at stress volume, 100k–1M rows) |
| **Measurement window** | Rolling 7 days |
| **Measurement** | `titan_ctl_recompute_ms` histogram on `/metrics`; the date-window read has no production metric yet; it was measured by the SQLite assessment harness, which is not in the repository |
| **Alert threshold** | None (advisory). A p95 over target is a reason to re-run the assessment |
| **Error budget** | None — advisory, does not pause work |
| **Related decisions** | D-077 (`idx_training_log_athlete_date`), D-083 |

Baseline (SQLite assessment, 2026-10-16): before the v29 index the 30-day read was 0.30 ms
realistic and 70.8 ms p95 at 1M rows; with the index, 0.02 ms and 0.17 ms.

---

## SLO Error Budget Policy

- Error budget is consumed when an SLO target is missed.
- When error budget for SLO-01, SLO-03, or SLO-04 drops below 50% in a rolling 30-day window,
  new feature work is paused until the budget is restored.
- SLO-07 is advisory and has no error budget.
- SLO-05 has zero error budget — any bypass event triggers immediate stop-the-line per AGENTS.md §7.

---

## Review Cadence

SLOs are reviewed at the Friday Weekly Governance Review (see AGENTS.md §Weekly Governance Log).
Targets are adjusted at Phase boundaries based on observed operational data.
