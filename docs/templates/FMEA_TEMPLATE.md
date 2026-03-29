# FMEA — [Subsystem / Feature Name]

**Date:** YYYY-MM-DD
**Version:** 1.0
**Author:** [Name]
**Scope:** [Module or subsystem path — e.g., `titan/science/governance_engine.py`]
**Status:** Draft | Reviewed | Approved

---

## Purpose

Failure Mode and Effects Analysis (FMEA) for [subsystem]. Identifies failure modes,
their effects on the athlete-facing safety model, and the controls in place to detect
and mitigate each failure.

---

## Risk Priority Number (RPN) Scale

| Score | Severity (S) | Occurrence (O) | Detection (D) |
|-------|-------------|----------------|---------------|
| 1 | No effect | Remote (< 1/year) | Almost certain detection |
| 3 | Minor degradation | Low (1–2/year) | High detection probability |
| 5 | Moderate — service degraded | Moderate (monthly) | Moderate detection |
| 7 | Significant — safety gate affected | Occasional (weekly) | Low detection probability |
| 9–10 | Critical — data loss or gate bypass | High (daily) | Near-undetectable |

**RPN = S × O × D.  RPN ≥ 50 requires a mitigation action item.**

---

## Failure Mode Analysis

| ID | Failure Mode | Effect | S | O | D | RPN | Current Controls | Action Required |
|----|-------------|--------|---|---|---|-----|-----------------|----------------|
| FM-01 | [Description] | [Effect on system/athlete] | _ | _ | _ | _ | [Tests, gates, alerts] | [None / T_-_ / ADR] |
| FM-02 | | | | | | | | |
| FM-03 | | | | | | | | |

---

## High-RPN Items (RPN ≥ 50)

### FM-XX — [Title]

**Description:** …
**Root Cause Hypothesis:** …
**Recommended Control:** …
**Owner:** @handle
**Linked Debt Item:** T_-_ / ADR-XXXX

---

## Mitigations Summary

| ID | Mitigation | Type | Status |
|----|-----------|------|--------|
| M-01 | [Description] | Preventive / Detective / Corrective | Open / Closed |

---

## Review Checklist

- [ ] All failure modes with RPN ≥ 50 have a linked action item
- [ ] All P0 safety gates are covered by at least one FM entry
- [ ] FMEA reviewed by at least one engineer other than the author
- [ ] Results reflected in TECHNICAL_DEBT.md if new items were identified

---

## Related

- ADR-XXXX
- `docs/runbooks/[relevant-runbook].md`
- TECHNICAL_DEBT.md entries: T_-_
