# Model Card — Governance Engine

**Model ID:** `titan.science.governance_engine.GovernanceEngine`
**Version:** v5.8.0
**Date:** 2026-03-29
**Owner:** Architect
**Status:** Production (Phase 8 OPEN)

---

## Model Overview

The Governance Engine is a deterministic, rule-based decision system — not a statistical
model. It applies a 7-gate safety pipeline to raw athlete biometrics and training load
metrics, producing a structured `GovernanceDecision` that either allows a session,
downgrades it, or hard-stops it.

This card documents the engine's decision logic, input/output contract, safety
invariants, known limitations, and evidence quality for each gate threshold.

---

## Intended Use

- **Primary use case:** Pre-session safety screening for endurance athletes (runners)
- **Deployment context:** Single-athlete, self-hosted TITAN OS instance
- **User:** The athlete themselves and/or a human coach reviewing Operator Console output
- **Not intended for:** Clinical decision support, medical diagnosis, or multi-athlete unsupervised deployment

---

## Input Features

| Feature | Source | Unit | Valid Range | Notes |
|---------|--------|------|-------------|-------|
| `hrv_rmssd` | Garmin HRV | ms | 10–200 | 7-day rolling mean used for H2 gate |
| `hrv_baseline` | Mean of the last 7 readings dated before today (D-105) | ms | 10–200 | None with fewer than 7 earlier readings → H2_MISSING, EASY ceiling (ADR-0051) |
| `rhr` | Garmin | bpm | 30–120 | H3 gate uses delta from the mean of the 7 days before today (D-105) |
| `tsb` | TSB engine (CTL−ATL) | AU | −100 to +30 | H4 gate |
| `subjective_fatigue` | Athlete self-report | RPE 0–10 | 0–10 | H5 gate |
| `acwr` | ACWR engine | ratio | 0.0–3.0 | VO2 eligibility sub-gate |
| `readiness_score` | Readiness engine | 0–100 | 0–100 | VO2 eligibility sub-gate |
| `glycogen_debt` | Glycogen engine | sessions | 0–14 | VO2 eligibility sub-gate |
| `days_since_last_vo2` | Training log | days | 0–365 | VO2 eligibility sub-gate |
| `fueling_score` | Nutrition optimizer | 0–10 | 0–10 | H6 fueling gate |

---

## Output Contract

`GovernanceDecision` object:
- `allowed: bool` — whether any session is permitted
- `session_type: str` — recommended session type (or `"REST"` if hard-stopped)
- `lock_codes: list[str]` — active lock codes from `CANONICAL_LOCK_CODES`
- `downgrade_reason: str | None` — human-readable downgrade rationale
- `decision_rationale: DecisionRationale` — structured rationale object (ADR-0038)
- `hard_stop: bool` — True if any H-gate fired

---

## Gate Architecture (7 Gates)

| Gate | ID | Threshold | Evidence Level | Lock Code |
|------|----|-----------|---------------|-----------|
| H1 — Override Lockdown | H1 | Manual override active | OPERATIONAL | `OVERRIDE_LOCKDOWN` |
| H2 — HRV Delta Hard Stop | H2 | Drop ≥ 15 ms from baseline | MODERATE | `HARD_STOP_SAFETY_GATES` |
| H3 — RHR Delta Hard Stop | H3 | Rise ≥ 8 bpm from 7-day mean | MODERATE | `HARD_STOP_SAFETY_GATES` |
| H4 — TSB Floor Hard Stop | H4 | TSB ≤ −50 AU | STRONG | `HARD_STOP_SAFETY_GATES` |
| H5 — Subjective Fatigue Hard Stop | H5 | RPE ≥ 8/10 | HEURISTIC | `HARD_STOP_SAFETY_GATES` |
| H6 — Fueling Gate | H6 | Fueling score < threshold | HEURISTIC | `FUELING_GATE_LOCK` / `FUELING_GATE_FLAG` |
| H7 — 2-of-4 Soft Downgrade | H7 | 2+ metrics ≥ soft threshold | HEURISTIC | `READINESS_2OF4_DOWNGRADE` |

All hard-stop gates (H2–H5) are OR-semantics — any single gate firing produces `hard_stop=True`.
Gate evaluation order is fixed: H1 → H2 → H3 → H4 → H5 → H6 → H7 (ADR-0009).

---

## Threshold Evidence Quality

Evidence levels follow `titan/config/evidence_registry.py`:

| Level | Meaning |
|-------|---------|
| `STRONG` | RCT or large-scale observational study (n > 1000) |
| `MODERATE` | Smaller study (n 50–1000) or meta-analysis of limited scope |
| `HEURISTIC` | Expert consensus, single-case, or internal calibration |

All gate thresholds are constants in `titan/config/thresholds.py`. Threshold adjustments
require an ADR and update to `evidence_registry.py`.

---

## Known Limitations

1. **Single-athlete calibration:** Gate thresholds are global constants, not per-athlete.
   Athletes with unusual physiological baselines may experience false positives (premature
   hard stops) or false negatives (missed downgrade). Per-athlete calibration is a Phase 9
   roadmap item.

2. **Subjective fatigue input (H5):** Self-reported RPE is subject to athlete bias.
   The threshold (≥ 8/10) is conservative but cannot account for systematic under-reporting.

3. **HRV measurement noise:** HRV readings from optical Garmin sensors have higher noise
   than chest-strap readings. The 7-day rolling mean partially mitigates this but does
   not eliminate it.

4. **No temporal context:** The engine evaluates a single time slice. It does not model
   multi-day recovery trajectories or detect improving-trend overrides for H2/H3.

5. **Cold-start behavior:** With fewer than 7 HRV readings before today the HRV baseline is
   missing (None, never 0.0 or a population value). H2 cannot compare, so governance applies
   the ADR-0051 EASY ceiling with lock `DATA_MISSING_CONSERVATIVE_H2` until 7 earlier readings
   exist (D-105).

---

## Bias and Fairness

This engine has not been evaluated across diverse athlete populations (age, sex, sport
type). All thresholds were calibrated against endurance runner profiles. Application to
other sports or demographics should be treated as out-of-distribution until validated.

---

## Test Coverage

- `tests/test_p0_safety_gates.py` — 20 boundary tests; all P0 hard-stop gates
- `tests/test_governance_integration.py` — 27 contract and boundary tests
- `tests/test_phase3_hygiene.py` — branch-coverage sweep
- CI coverage gate: ≥ 80% on `titan.science.governance_engine` + `titan.science.governance_contracts`

---

## Related

- `titan/science/governance_engine.py`
- `titan/science/governance_contracts.py`
- `titan/config/thresholds.py`
- `titan/config/evidence_registry.py`
- ADR-0009 — Safety gate hardening
- ADR-0038 — Governance Decision Rationale Protocol
- `docs/training/DECISION_MODEL.md`
