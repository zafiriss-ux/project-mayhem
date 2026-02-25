# ADR 0007 — Intensity Governance Architecture Audit

**Date:** 2026-02-25
**Branch:** `claude/audit-governance-architecture-zNnuL`
**Type:** Architectural Assessment (read-only, no code changes)
**Scope:** Audit of new intensity governance docs vs existing science engines

---

## Context

Three documents were added to `docs/training/`:

- `OPERATIONAL_MODEL.md` — universal training machinery (HR ceiling, drift monitoring, RPE bands, VO2 governor)
- `DECISION_MODEL.md` — deterministic 7-gate evaluation pipeline
- `profiles/5K.md` — concrete threshold values for the 5K training profile

These documents define a new intensity governance framework including: HR ceiling hard limits (153 bpm Z3, 145 bpm Z2), in-session HR drift limits (4% soft / 6% hard), RPE band ceilings, a 2-of-4 indicator downgrade rule, VO2 eligibility gating, and fueling state checks.

This audit examines:
1. Whether the new governance spec conflicts with existing science engines (ACWR, HRV, TSB, Fatigue, Readiness, AFI)
2. Whether the DECISION_MODEL evaluation order is compatible with `GOVERNANCE_PHILOSOPHY.md`
3. Whether a new orchestration layer is needed or changes should go into `daily_coach`

---

## Findings

### Section 1 — Conflicts With Existing Science Engines

#### 1.1 Critical Conflicts — Safety Non-Negotiables Breached

These are violations of `GOVERNANCE_PHILOSOPHY.md §5` ("never ignore HRV collapse", "never ignore injury flags").

**C1 — HRV Collapse: No Hard Stop**

- Spec (`DECISION_MODEL` Gate 2): `hrv < baseline_7d − 15ms` → RED, hard stop
- `GOVERNANCE_PHILOSOPHY §5`: "Never ignore HRV collapse"
- Actual (`readiness_engine.py:19`): `hrv_diff < -10` → deduct 20 points from readiness score → readiness ≈ 80/100 (status: GOOD)
- At a collapse of −15ms the readiness score is still 80 — no hard stop fires anywhere in `governance_engine.py`
- The parasympathetic guard (`autonomic_engine.py:152`) catches the *opposite* anomaly (HRV↑ + HRR↓, false recovery) — it does not catch HRV collapse (HRV↓↓)
- **Verdict: VIOLATED**

**C2 — RHR Collapse: No Hard Stop**

- Spec: `rhr > baseline_7d + 10 bpm` → RED, hard stop
- `governance_engine.py`: no RHR threshold of any kind
- `readiness_engine.py:25`: docks 15 pts at `rhr_diff > 5` — severity bands top out at 5 bpm, not 10 bpm
- **Verdict: UNIMPLEMENTED**

**C3 — TSB Critical Floor: No Load Gate**

- Spec (`DECISION_MODEL` Gate 4): `tsb < profile.tsb_critical_floor_au` (5K: −35 AU) → RED, hard stop
- `tsb_engine.py`: computes TSB correctly; labels states (OVERTRAINED at −50, FUNCTIONAL OVERREACH at −30 to −50)
- `governance_engine.py`: zero TSB gate — TSB is computed and reported but never gates any session
- A TSB of −36 AU passes all existing gates and can receive a VO2 prescription
- **Verdict: UNIMPLEMENTED**

**C4 — Injury Flag: Gate 1 Completely Absent**

- Spec: Injury flag → Gate 1 hard stop (first, non-bypassable)
- `docs/architecture/EVALUATION_ORDER.md` item 1: "Injury Risk Gate"
- `GOVERNANCE_PHILOSOPHY §5`: "Never ignore injury flags"
- `daily_coach.py`: no injury flag check; `governance_engine.py`: no injury gate
- **Verdict: UNIMPLEMENTED — highest-priority gate entirely absent**

**C5 — Subjective Fatigue: Hardcoded, 2-of-4 Permanently Incomplete**

- Spec: Subjective fatigue ≥ 7/10 = one of four primary negative indicators
- `daily_coach.py:173`: `soreness = 3,  # TODO: add morning check-in prompt` — hardcoded
- The 2-of-4 rule can never count a subjective fatigue negative because the input is always 3 (below any threshold)
- **Verdict: 2-of-4 rule permanently operates on only 3 of 4 indicators**

---

#### 1.2 Threshold Misalignments

| # | Spec (5K profile) | `readiness_engine.py` | Impact |
|---|---|---|---|
| T1 | HRV negative: `< baseline − 8ms` | First tier: `< baseline − 10ms` (line 19) | −2ms gap — spec classifies "negative" 2ms earlier than engine |
| T2 | Sleep negative: `< 60/100` | First dock at `< 50/100` (line 30) | Sleep 50–59 = negative in 2-of-4 context but zero readiness penalty in engine |
| T3 | RHR negative: `> baseline + 6 bpm` | First dock at `> baseline + 5 bpm` (line 25) | +1 bpm gap (minor) |

**T2 is the most consequential.** At sleep score 55: the DECISION_MODEL counts a negative indicator and can trigger a YELLOW downgrade. The readiness engine applies no penalty (threshold is 50). The two systems output contradictory assessments for the same athlete state.

---

#### 1.3 Structural Mismatch — Graduated Downgrade vs Binary Gate

| Spec | Existing code |
|---|---|
| YELLOW → Z4/VO2 → Z3, Z3 → Z2, volume −20% | `governance_engine.py`: binary — either `EASY` (max zone 2) or full plan unchanged |
| Graduated downgrade defined in DECISION_MODEL Gate 5 | `weekly_planner.py:265-270` has INTERVALS→TEMPO→EASY chain — but fires on HRV < −10 only, at weekly plan generation scope, not at daily session gate level |

The spec's graduated downgrade (Z3→Z2 for YELLOW) has no equivalent in the daily governance layer.

---

#### 1.4 Gaps — Gates Specified But Not Implemented

| Gate | Spec | Code |
|---|---|---|
| VO2 Eligibility (Gate 6) | All 5 required: GREEN color + TSB ≥ 0 + HRV no suppression + ≥2 rest days since last VO2 + carb-available fueling | Absent from `governance_engine.py` entirely |
| Fueling Gate (Gate 7) | Flag and recommend delay for Z3/Z4/VO2 in fasted or low-carb state; phase lock violation during intensity weeks | `glycogen_model.py` tracks debt but no gate fires; debt is informational only |
| ACWR | `acwr_engine.py` calculates injury risk ratio | Never consumed by any gate — orphaned signal |
| Fatigue typing | `fatigue_engine.py` classifies CENTRAL/METABOLIC/PERIPHERAL | Orphaned; DECISION_MODEL uses self-reported fatigue, not typed classification |

---

### Section 2 — Evaluation Order vs GOVERNANCE_PHILOSOPHY.md

#### 2.1 Conceptual Alignment: COMPATIBLE ✓

The three ordering documents (`GOVERNANCE_PHILOSOPHY.md`, `DECISION_MODEL.md`, `EVALUATION_ORDER.md`) map cleanly to each other:

```
GOVERNANCE_PHILOSOPHY §6       DECISION_MODEL §4               EVALUATION_ORDER.md
─────────────────────────────  ───────────────────────────     ───────────────────
1. Hard physiological gates  ↔ Gate 1–2: Injury + Autonomic  ↔ 1. Injury Risk Gate
2. Energy / fatigue state    ↔ Gate 3: Recovery              ↔ (implicit in VLG)
3. Goal priority             ↔ Gate 4: Load (TSB/ATL)        ↔ 2. Volume Load Gauge
4. Optimization weighting    ↔ Gates 5–7: Governor/VO2/Fuel  ↔ 3. Adaptive Priority Lock
5. Recommendation output     ↔ Output generation             ↔ 4. Session Generator
```

DECISION_MODEL is the concrete instantiation of GOVERNANCE_PHILOSOPHY §6. No conceptual conflict exists between any of the three documents.

#### 2.2 Implementation Alignment: PARTIAL ✗

| Expected position in gate order | Actual `daily_coach.py` |
|---|---|
| Gate 1: Injury (hard stop, before all others) | **Absent** |
| Gate 2: Autonomic collapse (HRV/RHR → hard stop) | AFI computed (step 4); collapse threshold not gated |
| Gate 3: Recovery (sleep + fatigue discrete gate) | Folded into readiness composite (step 7); no discrete gate |
| Gate 4: Load (TSB critical floor → hard stop) | TSB computed (step 5); floor not gated |
| Gates 5–7: Intensity governor, VO2 eligibility, fueling | **Absent** |
| Behavioral gates (override ratio, CS confidence) | Correctly at final position (step 9b) ✓ |

The existing `GovernanceEngine` (step 9b) is correctly positioned as the last gate before Telegram output. Its 3 gates (parasympathetic guard, override lockdown, CS confidence) are appropriate behavioral constraints. What is missing is a physiological gate layer that must run between step 7 (readiness) and step 9b.

Note on parasympathetic guard vs HRV collapse: these are opposite physiological scenarios.
- Parasympathetic guard: HRV **elevated** (>110% baseline) + HRR impaired = false recovery anomaly ✓ handled
- HRV collapse: HRV **suppressed** (< baseline − 15ms) = overreach/stress = NOT handled

The existing guard does not substitute for an HRV collapse hard stop.

---

### Section 3 — Recommendation: New Layer vs Embedded

#### Decision: Create `titan/science/intensity_governor.py`

Do not embed the new gates in `daily_coach.py` or extend `governance_engine.py`.

**Rationale:**

1. **Cohesion** — `governance_engine.py` has a documented identity: 3 behavioral/model-confidence hard locks. Adding physiological intensity gates conflates two distinct governance concerns (behavioral discipline vs physiological safety). The engine's docstring says "binary hard gates applied AFTER plan generation" — extending it with 7 graduated physiological gates changes its contract.

2. **Input contract** — The DECISION_MODEL pipeline requires new inputs absent from the current `context` dict: `injury_flag`, `subjective_fatigue`, `fueling_state`, `days_since_last_vo2`, `active_profile`. These form a new, typed input surface.

3. **Output schema** — The spec's output is richer: `gate_color` (RED/YELLOW/GREEN), `negative_signals` list, `hr_ceiling`, `drift_limit_pct`, `rpe_band`, `vo2_authorized`, `downgrade_applied`. Current governance returns binary session_type mutation.

4. **Sequential early-exit semantics** — DECISION_MODEL §4: "Gates are evaluated in strict sequence. A gate failure stops evaluation at that point." This requires explicit short-circuit control flow, not a list of independent checks.

5. **Two-layer separation** — Physiological gates (`IntensityGovernor`) should fire first; behavioral gates (`GovernanceEngine`) fire last. This matches GOVERNANCE_PHILOSOPHY §6 and EVALUATION_ORDER.md.

#### Proposed insertion point in `daily_coach.py`

```
Step 7:  Composite readiness (AFI + TSB + glycogen)   [existing — unchanged]
Step 8:  Get today's planned session from weekly plan  [existing — unchanged]
Step 8b: IntensityGovernor.evaluate(inputs, profile)   ← NEW
Step 9:  Feed activities into load engines             [existing — unchanged]
Step 9b: GovernanceEngine.apply_constraints(...)       [existing — unchanged, fires last]
```

`IntensityGovernor` consumes signals already computed (HRV deviation, RHR, TSB, sleep score, glycogen debt) without duplicating computation.

#### What `intensity_governor.py` should implement

```python
class IntensityGovernor:
    def evaluate(self, inputs: IntensityInputs, profile: Profile) -> GateResult:
        # Gate 1: injury_flag         → RED hard stop (non-bypassable)
        # Gate 2: HRV/RHR collapse    → RED hard stop; negative → YELLOW
        # Gate 3: sleep/fatigue       → YELLOW (no RED from recovery alone)
        # Gate 4: TSB critical floor  → RED hard stop; ATL elevated → YELLOW
        # Aggregate: 2-of-4 rule      → YELLOW if ≥2 negatives, regardless of individual gate color
        # Gate 5: Intensity governor  → graduated downgrade on YELLOW (Z4→Z3, Z3→Z2, −20% vol)
        # Gate 6: VO2 eligibility     → 5 conditions, replace VO2 with Z2 if any fail
        # Gate 7: Fueling state       → flag + recommend delay (does not block; logs)
        # Returns: GateResult with full audit record
```

#### In-session drift monitoring and HR ceiling

HR ceiling (153 bpm Z3 / 145 bpm Z2) and drift monitoring (4% soft / 6% hard) are **live-session** concerns requiring a real-time HR feed. They cannot run in `daily_coach.py` (morning routine). These should be:

- Documented as athlete-enforced responsibilities until a live-session component exists, OR
- Implemented as a post-session audit against recorded HR data from Garmin activity files

They are not a pre-session gate concern and must not be conflated with the morning routine.

---

## Summary

| Question | Finding |
|---|---|
| Does new governance conflict with existing engines? | **Yes — 5 safety-critical conflicts (C1–C5), 3 threshold misalignments (T1–T3), 4 unimplemented gates** |
| Is DECISION_MODEL evaluation order compatible with GOVERNANCE_PHILOSOPHY? | **Yes — conceptually aligned. Implementation is missing the first 4 gates.** |
| New `training_governor.py` or embed in `daily_coach`? | **Create `titan/science/intensity_governor.py`. Do not embed in `daily_coach` or extend `governance_engine.py`.** |

### Priority order for implementation

1. **P0 (safety):** C1 HRV collapse hard stop, C2 RHR collapse hard stop, C3 TSB critical floor gate, C4 injury flag gate
2. **P1 (correctness):** T2 sleep threshold alignment (50→60), subjective fatigue collection (C5), graduated downgrade
3. **P2 (completeness):** VO2 eligibility gate (Gate 6), fueling gate (Gate 7)
4. **P3 (hygiene):** ACWR consumption, fatigue_engine integration or explicit deprecation, EVALUATION_ORDER.md update to reflect 7-gate model

---

*Assessment only. No `.py` files modified.*
