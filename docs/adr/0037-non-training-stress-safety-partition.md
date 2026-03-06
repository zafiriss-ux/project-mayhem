# ADR-0037 — Non-Training Stress Safety Partition

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Risk Review V8 — Risk: Non-Training Stress Protocol (absence of Safety Partition for HRV/sleep outside ACWR)
**Phase:** 7.9 Hardening
**Supplements:** ADR-0009 (safety gate hardening), ADR-0020 (degraded conservative mode), `titan/config/thresholds.py`

---

## Context

TITAN OS governance uses two classes of stress signals:

1. **Training load signals** — CTL, ATL, TSB, ACWR — derived from session data.
2. **Physiological state signals** — HRV, RHR, subjective fatigue — measured daily.

The governance gates H2 (`HARD_STOP_HRV_DELTA`) and H3 (`HARD_STOP_RHR_DELTA`) fire
when these physiological signals deviate from baseline. The interpretation is: *the
athlete's physiology shows stress; training was the cause; reduce load.*

### The Problem: HRV/RHR as Mixed Signals

HRV and RHR respond to **all stressors** — not only training load. A depressed HRV on
Monday morning may be caused by:

| Cause | ACWR signal | Governance response (current) | Correct response |
|---|---|---|---|
| Hard weekend training | Elevated (ATL spike) | HARD_STOP + rest ✅ | Rest |
| Illness onset | Normal or low | HARD_STOP + rest ✅ | Rest |
| Work/life stress (poor sleep, anxiety) | Normal | **HARD_STOP + rest** | Possible light session |
| Travel (jet lag, dehydration) | Low | **HARD_STOP + rest** | Rest / easy |
| Heat exposure (not training) | Normal | **HARD_STOP + rest** | Rest / light |
| Alcohol / poor diet | Normal | **HARD_STOP + rest** | Depends |

When HRV drops without a corresponding ACWR spike, the current system fires H2 or H3
and recommends rest or easy maintenance — which may be correct — but it does so with
the same confidence and the same communication as when training load clearly explains
the fatigue. The athlete receives no distinction between "you trained too hard" and
"your HRV is low but we don't know why."

**This creates two failure modes:**

**False-positive over-governance:** A high-achieving athlete who has a single poor
HRV morning due to a stressful work meeting receives the same HARD_STOP as someone
in genuine overreaching. Over time, this erodes operator trust in governance decisions
(Operator Trust Drift, ADR-0038).

**False-negative under-governance:** The converse case is less common but more dangerous:
an athlete in early illness onset may have normal ACWR (no unusual training) but
depressed HRV. Current gates would fire, but the recommendation ("easy maintenance")
may not be conservative enough for illness onset, which warrants full rest.

### The ACWR Orthogonality Problem

ACWR measures the ratio of recent-to-chronic training load. It is correctly measuring
what it is designed to measure. However, it provides **no information about non-training
stressors**. This means:

- If HRV drops and ACWR is normal: the system cannot distinguish life stress from
  illness from fatigue. All cases receive the same governance response.
- If HRV drops and ACWR is elevated: the system correctly identifies training-related
  fatigue.

---

## Decision

**Introduce a Non-Training Stress indicator that partitions HRV/RHR anomalies into
training-explained and training-unexplained categories. Governance communication must
reflect this distinction. Illness-pattern detection must apply a more conservative
response than life-stress detection.**

### Non-Training Stress Classification

At each DailyCoach evaluation, classify the HRV/RHR signal context:

```python
def classify_hrv_stress_context(hrv_delta_ms, acwr, rhr_delta_bpm) -> str:
    """
    Returns: 'TRAINING_EXPLAINED' | 'UNEXPLAINED_MODERATE' | 'ILLNESS_PATTERN' | 'NORMAL'
    """
    training_stressed = acwr > ACWR_SAFE_MAX or acwr > VO2_ACWR_MAX
    physiologically_stressed = (
        hrv_delta_ms >= HARD_STOP_HRV_DELTA or
        rhr_delta_bpm >= HARD_STOP_RHR_DELTA
    )

    if not physiologically_stressed:
        return 'NORMAL'
    if physiologically_stressed and training_stressed:
        return 'TRAINING_EXPLAINED'
    if physiologically_stressed and not training_stressed:
        # Sub-classify: illness pattern vs life stress
        if hrv_delta_ms >= ILLNESS_PATTERN_HRV_DELTA and rhr_delta_bpm >= ILLNESS_PATTERN_RHR_DELTA:
            return 'ILLNESS_PATTERN'
        return 'UNEXPLAINED_MODERATE'
```

```python
# In thresholds.py
ILLNESS_PATTERN_HRV_DELTA = 20.0   # ms — threshold for dual-signal illness pattern
ILLNESS_PATTERN_RHR_DELTA = 10.0   # bpm — both signals must exceed for ILLNESS_PATTERN
```

**Rationale for dual-signal illness pattern:** Illness typically depresses both HRV
and elevates RHR simultaneously. Life stress typically depresses HRV but has a smaller
effect on RHR. The dual-threshold pattern is a well-established clinical heuristic
(evidence label: MODERATE).

### Governance Response by Context

| Classification | Gate behaviour | Coaching message |
|---|---|---|
| `NORMAL` | Gates not fired | Normal recommendation |
| `TRAINING_EXPLAINED` | Current gate logic unchanged | "Training load explains today's recovery status." |
| `UNEXPLAINED_MODERATE` | H2/H3 fires as today; recommendation: easy maintenance | **"HRV is lower than baseline but training load is normal. Possible life stress or early fatigue. Easy run or rest today."** |
| `ILLNESS_PATTERN` | H2/H3 fires; recommendation: **full rest** (not easy maintenance) | **"Both HRV and RHR indicate possible illness or significant non-training stress. Full rest recommended. If symptoms persist >48h, consult a medical professional."** |

**Critical distinction:** `ILLNESS_PATTERN` must recommend full rest — not easy
maintenance. The current governance response for H2/H3 is easy maintenance or rest
depending on other gate combinations. This ADR mandates full rest for `ILLNESS_PATTERN`
regardless of ACWR or TSB status.

### What This Does NOT Change

- The `HARD_STOP_HRV_DELTA` and `HARD_STOP_RHR_DELTA` constants remain unchanged.
- The existing H2 and H3 gate logic remains unchanged — it still fires when the deltas
  are exceeded. This ADR adds a post-gate classification layer.
- Subjective fatigue gates (H5, H6) are unchanged.

### Subjective Stress Input (Optional Operator Extension)

If the Telegram bot interaction captures subjective stress context (e.g., via a
morning survey question "Did you experience unusual stress yesterday? Yes/No"),
the system may use this to override `UNEXPLAINED_MODERATE` back to `NORMAL` or
confirm `ILLNESS_PATTERN`. This is **optional and operator-configured** — governance
must not depend on it as a required input.

---

## Debt Items Created

- **T1-21** — Governance gates H2/H3 fire without distinguishing training-explained
  from non-training-stress HRV/RHR anomalies — illness pattern and life stress produce
  identical governance response despite warranting different actions (Tier 1, safety-critical)

---

## Alternatives Considered

**Alternative A — Ask the athlete every morning about life stress**
A required daily subjective stress survey would provide direct data. Rejected as a
required input — it creates a mandatory user interaction that blocks the morning
routine if skipped. The ACWR-orthogonality approach provides an automatic signal
without requiring operator input.

**Alternative B — Use HRV trend (7-day) instead of delta**
A 7-day downward HRV trend is a stronger illness/overtraining signal than a single-day
delta. This is a valid enhancement but orthogonal to this ADR's concern (which is about
distinguishing cause, not detecting magnitude). T5-04 (science evidence review) is
the appropriate place for this enhancement.

**Alternative C — Add a new HARD_STOP gate for illness pattern**
Rejected. Adding a new governance lock code increases the lock code surface that must
be maintained in tests (ADR-0021), documentation (ADR-0024), and evidence registry.
The illness-pattern behaviour is better expressed as a governance response modifier
within the existing H2/H3 gate path.

---

## Consequences

- Positive: Athletes and operators receive contextually accurate governance messages.
  The difference between "you trained too hard" and "possible illness" is communicated
  explicitly.
- Positive: `ILLNESS_PATTERN` classification produces more conservative guidance
  (full rest) than the generic H2/H3 response (easy maintenance). This closes a
  genuine safety gap.
- Positive: `UNEXPLAINED_MODERATE` classification reduces governance drag for
  athletes experiencing occasional life-stress HRV dips — they receive an informative
  message rather than a hard stop.
- Negative (acceptable): The dual-threshold illness pattern heuristic has
  MODERATE evidence quality — it is a proxy, not a medical diagnosis. The coaching
  message must explicitly recommend medical consultation for persistent patterns.
- Constraint: T1-21 is Tier 1 (safety). Per Rule E1, it must be completed before
  any Tier 2 or higher work begins.
