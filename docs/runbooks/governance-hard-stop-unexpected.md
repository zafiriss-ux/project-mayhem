# Runbook — Unexpected Governance Hard Stop

**Version:** 1.0
**Date:** 2026-03-29
**Owner:** Engineering
**Trigger:** `HARD_STOP_SAFETY_GATES` lock code fires on a day when the athlete feels healthy and expects a normal session

---

## Symptoms

- Telegram morning briefing message contains `🛑 HARD STOP` or `REST` recommendation
- Lock code `HARD_STOP_SAFETY_GATES` present in `GovernanceDecision.lock_codes`
- Athlete subjectively feels recovered and the stop appears incorrect
- Gates H2, H3, H4, or H5 are listed in the decision rationale

---

## Important: Safety First

**Do not override a hard stop based on subjective feeling alone.**
The governance pipeline is designed to catch physiological stress before the athlete
perceives it. An unexpected hard stop may indicate early illness, accumulated fatigue,
or a data quality issue — all require investigation before training proceeds.

Human override is available (ADR-0042) but must be used deliberately, not reflexively.

---

## Diagnostic Steps

### Step 1 — Identify which gate fired

Check the Telegram message or Operator Console for the `DecisionRationale` output.
The rationale will name the gate (H2/H3/H4/H5) and the triggering metric value.

### Step 2 — Verify the triggering metric

**H2 — HRV Delta Hard Stop (≥ 15 ms drop from baseline)**

```
# Check recent HRV readings in Operator Console or DB
# Expected: today's HRV is ≥ 15 ms below the 14-day mean
```

Questions to ask:
- Did you wear the device overnight? (Missing night data → abnormal baseline)
- Was the HRV measurement taken in the morning after lying still for 5 minutes?
- Is this a known post-race or post-hard-workout day?

If HRV data is missing or clearly erroneous (e.g., 0 ms or 200+ ms):
→ This is likely a **data quality issue**, not a true physiological signal. See Step 4.

---

**H3 — RHR Delta Hard Stop (≥ 8 bpm rise from 7-day mean)**

Questions to ask:
- Did you consume caffeine, alcohol, or take medication that elevates heart rate?
- Is this a known illness onset or high-stress day?
- Was the device worn during sleep last night?

If RHR data is abnormal (e.g., 0 bpm, 150+ bpm during sleep):
→ Data quality issue. See Step 4.

---

**H4 — TSB Floor Hard Stop (TSB ≤ −50 AU)**

- TSB = CTL − ATL. A very negative TSB means acute load far exceeds chronic fitness.
- This gate rarely fires unexpectedly. If it does, verify the training log for recent
  weeks — the system may have ingested duplicate or incorrect activity data.

```bash
grep "tsb_value\|training_load" ~/Documents/TITAN/logs/titan.log | tail -20
```

---

**H5 — Subjective Fatigue Hard Stop (RPE ≥ 8/10)**

- This gate fires from athlete self-report. Did you enter a fatigue score of 8 or higher
  in the morning check-in?
- If no score is given, it defaults to the morning soreness value (`DailyCoach.run_morning_routine`). There is no
  Telegram command that changes it after the routine has run; the next morning uses the new input.

---

### Step 3 — Decide: Trust the gate or investigate further

| Finding | Recommended Action |
|---------|-------------------|
| Gate fired on correct data; athlete is likely more fatigued than perceived | **Take the rest day. Trust the gate.** |
| Gate fired on missing/zero data (device not worn) | Investigate data quality (Step 4) |
| Gate fired on duplicate/erroneous training log entry | Investigate data quality (Step 4) |
| Gate fired repeatedly without physiological cause | File an OBS in `SCRATCHPAD.md` for architectural review |

---

### Step 4 — Data Quality Investigation

If the triggering metric appears to be erroneous:

1. Check the Operator Console "Session Explorer" for the raw metric values.
2. Check Garmin Connect directly for the same day's HRV/RHR data.
3. If Garmin shows valid data but TITAN shows 0 or NULL:
   - Trigger a manual re-sync: Telegram `/sync` command
   - Check `garmin_sync.py` log for the specific sync session

If data quality is confirmed bad (device not worn, corrupt sync):
- The governance pipeline was correct to be cautious — proceed with rest.
- Use human override only if you have an independent HRV measurement from another device.

---

### Step 5 — Human Override (last resort)

Human override is available per ADR-0042. Use it only when:
- You have independent, trustworthy biometric data contradicting the gate
- You accept full responsibility for the session outcome
- You document the override reason in the Operator Console

Override is logged permanently in `governance_outcomes` for calibration review.

---

## Post-Incident Checklist

- [ ] Identified which gate fired and why
- [ ] Verified metric data quality
- [ ] Took rest (preferred) or applied override with documented rationale
- [ ] If repeated unexpected stops: filed OBS in `SCRATCHPAD.md`

---

## Related

- ADR-0009 — Safety gate hardening (OR semantics + gate order)
- ADR-0042 — Human Override as First-Class Invariant
- `titan/config/thresholds.py` — gate threshold constants
- `docs/training/DECISION_MODEL.md` — full 7-gate pipeline
- `docs/SLO.md` — SLO-05 (Safety Gate Non-Bypass)
