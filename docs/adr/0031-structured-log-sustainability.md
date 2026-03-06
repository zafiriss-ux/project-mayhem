# ADR-0031 — Structured Log Volume and Alerting Sustainability Protocol

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Risk Review V7 — Risk: Observability Overload (Πληροφοριακός Θόρυβος)
**Phase:** 7.9 Hardening
**Supplements:** ADR-0020 (Persistence Failure Policy), T2-01–T2-13 (observability rollout — all resolved)

---

## Context

Phases 3 and 4 of the TITAN OS observability rollout (T2-01 through T2-13) added
structured event emission across all major modules. This was necessary and correct.
The risk identified in Risk Review V7 is **downstream of that success**: having
*too much* observability signal, without a management strategy, creates the same
problem as having too little — critical events are buried in noise.

### Observable Signals of the Risk

1. **Repetitive hard-stop events.** If the athlete's HRV is chronically suppressed
   (e.g., during a high-training-load block), the H2 gate fires every single morning.
   The `HARD_STOP_HRV_DELTA` event is emitted, a Telegram message is sent, and the
   operator sees the same alert for 7 consecutive days. By day 4, the alert is
   cognitively invisible. The same "noise" failure mode applies to H4 (TSB floor) and
   H5 (subjective fatigue).

2. **High-cardinality sync events.** A Garmin sync of 90 days of backfill emits 90+
   structured events (`hrv_day_loaded`, `activity_synced`, etc.). Log tail during
   backfill is unreadable.

3. **No log rotation / retention policy.** Structured events are emitted to the Python
   `logging` handler, which writes to stdout or a configured file. There is no
   file rotation policy, no max-size limit, and no retention window. In a long-running
   deployment (Phase 8+, always-on server), log files can grow indefinitely.

4. **No operational runbook.** When an operator sees a `HARD_STOP_SAFETY_GATES` event
   for the first time, there is no documented procedure for what to do next. This
   increases mean time to resolution (MTTR) and forces the operator to reason from
   first principles at the worst possible moment.

5. **Alert fatigue causing bypasses.** The CLAUDE.md engineering rules explicitly ban
   `pytest.mark.skip` / `xfail` without justification, precisely because engineers
   who are fatigued by noise start taking shortcuts. The same psychology applies to
   operators ignoring Telegram alerts.

### Current Mitigations (Insufficient)

- `LOG_LEVEL` environment variable (global filter, not per-event).
- Structured events carry `event_type` keys that could be filtered — but no filter
  is configured.
- Telegram delivery uses the T3-09 fallback-aware gateway — but no deduplication.

---

## Decision

**Introduce a three-part sustainability protocol: event severity levels, alert
deduplication, and an operational runbook.**

### Part 1 — Event Severity Classification

Every structured event must carry a `severity` field:

```python
class EventSeverity:
    CRITICAL = "CRITICAL"   # Governance hard stop; requires immediate operator action
    WARNING  = "WARNING"    # Soft downgrade or degraded mode; requires attention
    INFO     = "INFO"       # Routine operational telemetry; no action required
    DEBUG    = "DEBUG"      # High-cardinality; only emitted when LOG_LEVEL=DEBUG
```

**Severity assignment for existing event types:**

| Event type | Severity |
|---|---|
| `HARD_STOP_*` | CRITICAL |
| `governance_lock_*` | CRITICAL |
| `garmin_data_stale` (ADR-0030) | CRITICAL |
| `degraded_mode_activated` | WARNING |
| `weather_synthetic_fallback_activated` | WARNING |
| `garmin_auth_failure` | WARNING |
| `hrv_day_skipped` | WARNING |
| `db_schema_migration` | INFO |
| `activity_synced` | DEBUG |
| `hrv_day_loaded` | DEBUG |
| `weather_window_computed` | INFO |

**Implementation:**
- `_emit_structured_event()` in each module is extended to accept `severity` parameter.
- Telegram gateway: only forwards `CRITICAL` and `WARNING` events by default.
  `INFO` and `DEBUG` go to log file only.
- The `LOG_LEVEL` env variable maps to Python logging levels as before; additionally,
  `TITAN_ALERT_LEVEL` env variable controls the minimum severity forwarded to Telegram.

### Part 2 — Alert Deduplication

**Problem:** A recurring governance condition (e.g., H2 fires every morning) produces
a Telegram alert every morning. By the 4th day, it is noise.

**Solution:** The Telegram gateway maintains a lightweight deduplication window in
memory (or as a SQLite row in `governance_outcomes`):

```python
# Deduplication rule
# If the same (event_type, lock_code) pair was sent within ALERT_DEDUP_WINDOW_HOURS,
# suppress the Telegram message and emit a DEBUG log entry only.
# Once ALERT_DEDUP_WINDOW_HOURS expires, re-send as a "condition persisting" summary.

ALERT_DEDUP_WINDOW_HOURS = 20   # Default: suppress same alert within one day
ALERT_PERSIST_SUMMARY_HOURS = 72  # After 72h of continuous same condition: send summary
```

**Summary message template (auto-generated after ALERT_PERSIST_SUMMARY_HOURS):**
```
⚠️ Persisting condition: HARD_STOP_HRV_DELTA
Active for: 72 hours (since 2026-03-03 07:12)
Occurrences: 3
Last value: HRV delta = -18ms (threshold: 15ms)
Action: Review training load. See runbook section H2.
```

**What this does NOT do:**
- It does not silence alerts on the first occurrence.
- It does not suppress alerts for different event types or different athletes (Phase 8).
- It does not require a database schema migration — the dedup window is stored in the
  existing `governance_outcomes` table using a new `event_metadata` JSON column, or
  as an in-memory dict if the table is not available (graceful degradation per ADR-0020).

### Part 3 — Operational Runbook

Create `docs/operations/RUNBOOK.md` with one section per CRITICAL event type:

```
## H2 — HARD_STOP_HRV_DELTA
Trigger: HRV delta ≥ 15ms drop from 7-day baseline
Action:
  1. Check if Garmin sync is fresh (< 26h) — ADR-0030
  2. Ask athlete: subjective fatigue, sleep quality
  3. If fatigue confirmed: rest day is correct; dismiss alert
  4. If no subjective fatigue: check sensor data quality; run manual HRV re-read
  5. If data error suspected: run `python -m titan --validate-hrv --date=today`
  6. To override (with documented reason): use Operator Console manual override
     (ADR-0012)
```

The runbook covers all 7 governance gates plus the 3 data-source staleness events
(ADR-0030).

### Part 4 — Log File Rotation Policy

Configure Python `logging.handlers.RotatingFileHandler` in `titan/main.py`:

```python
# Defaults (overridable via .env)
LOG_MAX_BYTES    = 10_485_760   # 10 MB per log file
LOG_BACKUP_COUNT = 5            # Keep 5 rotated files (50 MB max)
```

This is a configuration change, not a logic change. Existing log output format is
unchanged.

---

## Debt Items Created

- **T2-14** — Structured events lack severity levels; Telegram alert deduplication
  absent; no operational runbook (Tier 2, independent, Phase 7.9)

---

## Alternatives Considered

**Alternative A — External log management (ELK stack, Grafana Loki)**
Rejected for current phase. TITAN is a single-user, local deployment. External log
management infrastructure is a Phase 9+ concern for a potential multi-user SaaS
deployment (ADR-0016). The protocol defined here uses only stdlib components and
existing SQLite infrastructure.

**Alternative B — Reduce event emission volume**
Rejected. Reducing event emission would reduce observability. The correct response to
alert fatigue is smarter routing and deduplication, not less information.

**Alternative C — Silence recurring alerts after N occurrences**
Rejected. Silencing is not deduplication — it creates a different failure mode where
a condition persists unnoticed. The `ALERT_PERSIST_SUMMARY_HOURS` mechanism ensures
the operator receives a periodic reminder, not silence.

---

## Consequences

- Positive: Operators receive actionable Telegram alerts (CRITICAL/WARNING only), not
  a firehose of operational telemetry.
- Positive: Recurring governance conditions produce daily summaries instead of daily
  identical alerts.
- Positive: An operational runbook reduces MTTR and prevents operators from reasoning
  from first principles during incidents.
- Positive: Log rotation prevents unbounded disk growth in long-running deployments.
- Negative (acceptable): Retroactively adding `severity` to all existing
  `_emit_structured_event()` calls requires touching ~12 modules. This is a mechanical
  change with no logic impact. Rule E4 applies: touch only the severity parameter, no
  adjacent refactoring.
- Constraint: T2-14 is Tier 2 and must wait for all T1 items (T1-18, T1-19, T1-20)
  to close first, per Rule E1.
