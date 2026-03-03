# ADR-0014 — Phase 7 ML Scaffold: Shadow/Advisory Mode with Mandatory Kill-Switch

**Date:** 2026-03-03
**Status:** Implemented (v5.8.0)
**Phase:** Phase 7 — ML Features

---

## Context

Following Phase 6 (Operator Console), TITAN OS had a stable, calibrated, observable foundation:
- Governance engine producing paired decision/outcome records in `governance_outcomes`
- OutcomeTracker surfacing calibration candidates via `/calibration`
- Structured observability across all critical paths
- Operator Console service payloads for readiness, sessions, overrides, calibration

This foundation enabled Phase 7 exploration: introducing machine learning without disrupting the existing safety-first architecture.

Three ML capabilities were identified as high-value:
1. **Load prediction**: forecast 7-day training load trajectory
2. **Injury risk scoring**: early-warning ensemble for overuse/underrecovery risk
3. **Automated periodization**: suggest phase transitions without manual intervention

The architectural challenge: how to introduce ML into a safety-critical system without compromising the non-bypassable governance layer or producing athlete-facing outputs before sufficient validation.

---

## Decision

Implement all Phase 7 ML engines in **shadow/advisory mode only**, with a **mandatory kill-switch** that defaults to ON (blocking), and require an **evidence label** on every ML recommendation payload.

### Architecture Constraints

1. **No ML engine may bypass or modify the governance gate.** The 7-gate pipeline (`GovernanceEngine`) remains the sole non-bypassable arbiter of session safety. ML engines produce *inputs* to planning, never *overrides* of governance decisions.

2. **Kill-switch mandatory before any athlete-facing path.** All three ML engines call `enforce_ml_kill_switch()` from `titan/science/ml_safety.py` before returning any athlete-facing payload. The kill-switch is controlled by `TITAN_ML_KILL_SWITCH` env var (default: `"1"` = blocking). This must be explicitly set to `"0"` / `"false"` / `"off"` to enable ML outputs.

3. **Graduated rollout model** (per engine):
   - Stage 0 (current): shadow mode — predictions computed but not surfaced to athlete
   - Stage 1 (future): advisory — predictions shown to coach/operator only
   - Stage 2 (future): suggest-only — shown to athlete with explicit "suggested by ML" label
   - Stage 3 (future): athlete-confirm — athlete must approve before applying
   - Stage 4 (future): auto-apply — only after ≥30 consecutive correct predictions and calibration gate passed

4. **Evidence label required.** Every recommendation payload dataclass includes an `evidence_label` field (STRONG / MODERATE / HEURISTIC). Phase 7 engines use `HEURISTIC` until peer-reviewed calibration data is accumulated.

### Module Implementations

| Module | Class | Mode | Kill-switch path |
|---|---|---|---|
| `titan/science/load_prediction_shadow.py` | `LoadPredictionShadowModel` | Shadow | `enforce_ml_kill_switch("load_prediction", athlete_facing=True)` |
| `titan/science/injury_risk_model.py` | `InjuryRiskEnsembleModel` | Advisory | `enforce_ml_kill_switch("injury_risk", athlete_facing=True)` |
| `titan/science/automated_periodization.py` | `AutomatedPeriodizationEngine` | Suggest-only | `enforce_ml_kill_switch("automated_periodization", athlete_facing=True)` |
| `titan/science/ml_safety.py` | `MLSafety` (module-level fns) | — | Shared kill-switch implementation |

### Kill-Switch Implementation

```python
# titan/science/ml_safety.py
import os

def is_ml_kill_switch_enabled() -> bool:
    value = os.getenv('TITAN_ML_KILL_SWITCH', '1').strip().lower()
    return value in ('1', 'true', 'on')

def enforce_ml_kill_switch(path_name: str, athlete_facing: bool) -> None:
    if athlete_facing and is_ml_kill_switch_enabled():
        raise RuntimeError(f"ML kill-switch is active — {path_name} output blocked")
```

Default-ON means a misconfiguration (forgetting to set the env var) fails safe: no ML output reaches the athlete. This is the correct failure mode for a safety-critical system.

---

## Alternatives Considered

### A. Full production ML integration immediately
Rejected. Insufficient outcome data (need ≥30 paired decisions per phase), no validated recall/precision metrics, governance gate not designed for ML input shapes.

### B. Opt-in kill-switch (default OFF)
Rejected. Default-OFF means a missed env var silently enables unvalidated ML for athletes. The failure mode is wrong. Default-ON is the only acceptable safety posture.

### C. Separate ML service (microservice)
Rejected for Phase 7. Adds deployment complexity before ML value is proven. Revisit in Phase 9 if multi-athlete scale requires it.

### D. Feature flags per engine (not global kill-switch)
Rejected for Phase 7. A single kill-switch is simpler and less error-prone. Per-engine flags may be introduced in Phase 8/9 once the global switch has proven reliable.

---

## Consequences

### Positive
- ML capability is scaffolded and testable without athlete-facing risk
- Kill-switch provides safe deployment toggle for gradual rollout
- Evidence labels establish provenance discipline from day one
- Shadow mode enables accuracy measurement against real outcomes before promotion
- All Phase 7 modules at 100% test coverage (1122 tests green as of 2026-03-02)

### Negative / Trade-offs
- Athletes receive no ML benefit yet (intentional — value follows validation)
- Kill-switch must be manually disabled per deployment; adds ops step
- HEURISTIC evidence labels reflect current calibration gap — must be revisited as data accumulates

### Future Gates (before promoting to Stage 1+)
- `LoadPredictionShadowModel`: ≥30 shadow predictions with RMSE < 10% of actual load
- `InjuryRiskEnsembleModel`: recall ≥ 0.80 on holdout set; false positive rate < 0.30
- `AutomatedPeriodizationEngine`: ≥10 athlete-confirmed suggestions with ≥80% adoption rate
- All promotions require ADR update and `evidence_label` upgrade (HEURISTIC → MODERATE)

### Promotion Control Requirements (T5-04)

Before any Phase 7 engine moves from shadow/advisory to athlete-facing Stage 1+:

1. **Gate metrics must pass** for the specific engine (criteria above).
2. **ADR must be updated** to record the promotion evidence and explicitly upgrade
   the recommendation payload evidence label from `HEURISTIC` to `MODERATE`.
3. **Deployment docs must explicitly disable the kill-switch** by setting
   `TITAN_ML_KILL_SWITCH=0` (or `false` / `off`) for the target environment.
4. **Operator Console calibration review must show promotion readiness** with
   the gate checklist visible to operators before rollout.

---

## Related

- ROADMAP.MD Phase 7 (CLOSED, 2026-03-02)
- ADR-0007 (Intensity governance architecture audit)
- ADR-0009 (Safety gate hardening — governance is non-bypassable)
- `docs/specs/adaptive_priority_lock.md` (priority ordering context)
- `titan/config/evidence_registry.py` (evidence label provenance model)
