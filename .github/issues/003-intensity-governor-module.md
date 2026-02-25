---
title: "[P1] New module: titan/science/intensity_governor.py — YELLOW graduated downgrade with GateResult audit"
labels: ["P1", "new-module", "governance", "intensity"]
---

## Problem Statement

The current governance pipeline is binary: a session is either allowed or hard-blocked (EASY/REST). There is no intermediate YELLOW state that can apply graduated intensity reductions — for example, keeping a session as INTERVALS but capping it at Zone 3 instead of Zone 4, or reducing planned volume by 20% when indicators are marginal but not critical.

The audit identified that `drift_engine.py`, `glycogen_model.py`, and `fatigue_engine.py` all produce advisory outputs that currently have no enforcement path. The `DriftEngine` explicitly returns "Stop progression. No hammer today" when drift > 5%, but `daily_coach.py` does not consume this signal in any gate.

A dedicated `IntensityGovernor` module is needed to:

1. Receive multi-source advisory signals
2. Classify the aggregate state as GREEN / YELLOW / RED
3. Apply graduated constraints for YELLOW states (zone cap + volume reduction)
4. Produce a structured `GateResult` object that carries both the enforcement decision and a full audit trail

## Scope

Create `titan/science/intensity_governor.py` as a new file. Wire it into `daily_coach.py` **after** composite readiness is computed and **before** `governance_engine.apply_constraints()`. The `GateResult` it returns must be passed into the governance context so it is available for Telegram message construction.

No existing file's logic is to be changed as a prerequisite. `IntensityGovernor` reads from outputs already computed earlier in the morning routine.

## Files Touched

| File | Change |
|---|---|
| `titan/science/intensity_governor.py` | **New file** — full module |
| `titan/orchestration/daily_coach.py` | Import and call `IntensityGovernor.evaluate()` after step 7 (composite readiness), before step 9 (governance gates) |
| `titan/science/governance_engine.py` | Accept `intensity_gate_result` in context dict; if result is RED, treat as a hard stop; if YELLOW, apply zone/volume constraints |

## Module Specification

### Class: `IntensityGovernor`

```python
class IntensityGovernor:
    def evaluate(self, signals: dict) -> GateResult
```

#### Input signals dict keys

| Key | Type | Source |
|---|---|---|
| `drift_pct` | float | `DriftEngine.compute_drift()` output |
| `glycogen_debt` | float (0-10) | `GlycogenDebtAccumulator.update()` output |
| `fatigue_level` | str | `FatigueEngine.classify_fatigue()` output (`LOW`/`MEDIUM`/`HIGH`) |
| `acwr` | float | `ACWREngine.calculate_acwr()` output (ratio) |
| `readiness_score` | int (0-100) | `ReadinessEngine.analyze_readiness()` output |
| `planned_session` | str | Session type string from weekly plan |
| `planned_volume_pct` | float | Planned volume as fraction of baseline (e.g., 1.0 = 100%) |

All keys are optional — the governor must handle missing signals gracefully (treat as neutral / no signal).

### Class: `GateResult`

```python
@dataclass
class GateResult:
    color: str           # "GREEN", "YELLOW", or "RED"
    max_zone: int        # 5 = unrestricted, 3 = YELLOW cap, 2 = RED cap
    volume_modifier: float  # 1.0 = no change, 0.8 = -20%, 0.0 = blocked
    session_override: str | None  # None = keep planned, "EASY" = forced
    triggered_signals: list[str]  # which signals contributed to this result
    audit: dict          # full detail for each signal evaluated
```

### Classification Logic

#### Step 1 — Evaluate each signal independently

| Signal | YELLOW trigger | RED trigger |
|---|---|---|
| `drift_pct` | `> 3.5%` and `<= 5.0%` | `> 5.0%` |
| `glycogen_debt` | `4 <= debt <= 6` | `debt > 6` |
| `fatigue_level` | `== "MEDIUM"` | `== "HIGH"` |
| `acwr` | `> 1.3` and `<= 1.5` | `> 1.5` |
| `readiness_score` | `40 <= score < 55` | `score < 40` |

#### Step 2 — Aggregate state

```
If any signal is RED:      aggregate = RED
Elif >= 2 signals YELLOW:  aggregate = YELLOW
Elif 1 signal YELLOW:      aggregate = YELLOW  (single-signal yellow still applies)
Else:                       aggregate = GREEN
```

Note: A single YELLOW signal still triggers YELLOW state (conservative by design). The threshold for RED requires at least one individual RED signal.

#### Step 3 — Apply constraints

```
GREEN:
  max_zone = 5
  volume_modifier = 1.0
  session_override = None

YELLOW:
  max_zone = 3         (Z4 and Z5 disabled)
  volume_modifier = 0.8  (-20% volume)
  session_override = None  (session type unchanged; quality sessions allowed at reduced intensity)
  Exception: if planned_session in [HAMMER, RACE]:
    session_override = "TEMPO"  (HAMMER/RACE require Z4+; cannot be honoured at YELLOW)

RED:
  max_zone = 2
  volume_modifier = 0.0
  session_override = "EASY"
```

### Audit dict structure (per-signal)

```python
gate_result.audit = {
  'drift': {
    'value': 4.2,
    'signal_color': 'YELLOW',
    'threshold_yellow': 3.5,
    'threshold_red': 5.0
  },
  'glycogen_debt': {
    'value': 3.1,
    'signal_color': 'GREEN',
    ...
  },
  ...
  'aggregate': 'YELLOW',
  'triggered_signals': ['drift'],
  'applied_constraints': {
    'max_zone': 3,
    'volume_modifier': 0.8,
    'session_override': None
  }
}
```

## Integration Point in `daily_coach.py`

The governor must be called after:
- Step 5: CS thermal adjustment
- Step 6: Glycogen debt update
- Step 7: Composite readiness (to have `readiness_score`)

And before:
- Step 9: Governance hard gates

```python
# Step 7.5 — Intensity Governor
ig = IntensityGovernor()
intensity_gate = ig.evaluate({
    'drift_pct': drift_result,
    'glycogen_debt': glycogen_debt_score,
    'fatigue_level': fatigue_classification,
    'acwr': acwr_ratio,
    'readiness_score': readiness['score'],
    'planned_session': today_plan.session_type,
    'planned_volume_pct': today_plan.volume_pct,
})
context['intensity_gate_result'] = intensity_gate
```

## Acceptance Tests

### Scenario AT-IG1: All signals GREEN — no constraints
```
Given:
  drift_pct = 2.5, glycogen_debt = 2.0, fatigue_level = "LOW"
  acwr = 1.15, readiness_score = 78, planned_session = "INTERVALS"
When: IntensityGovernor.evaluate(signals) is called
Then:
  - result.color == "GREEN"
  - result.max_zone == 5
  - result.volume_modifier == 1.0
  - result.session_override is None
  - result.triggered_signals == []
```

### Scenario AT-IG2: Single YELLOW signal — YELLOW state, Z4 cap applied
```
Given:
  drift_pct = 4.5  (YELLOW: > 3.5, <= 5.0)
  all other signals GREEN
  planned_session = "INTERVALS"
When: evaluate() is called
Then:
  - result.color == "YELLOW"
  - result.max_zone == 3
  - result.volume_modifier == 0.8
  - result.session_override is None  (INTERVALS allowed at Z3)
  - result.triggered_signals == ["drift"]
```

### Scenario AT-IG3: YELLOW state with HAMMER — override to TEMPO
```
Given:
  drift_pct = 4.5  (YELLOW)
  planned_session = "HAMMER"
When: evaluate() is called
Then:
  - result.color == "YELLOW"
  - result.session_override == "TEMPO"
  - result.max_zone == 3
```

### Scenario AT-IG4: Single RED signal — RED state, EASY forced
```
Given:
  drift_pct = 6.2  (RED: > 5.0)
  all other signals GREEN
  planned_session = "TEMPO"
When: evaluate() is called
Then:
  - result.color == "RED"
  - result.max_zone == 2
  - result.volume_modifier == 0.0
  - result.session_override == "EASY"
  - result.triggered_signals == ["drift"]
```

### Scenario AT-IG5: Multiple YELLOW signals — still YELLOW, not RED
```
Given:
  drift_pct = 4.0  (YELLOW)
  glycogen_debt = 5.5  (YELLOW)
  fatigue_level = "MEDIUM"  (YELLOW)
  acwr = 1.4  (YELLOW)
  readiness_score = 62  (GREEN)
When: evaluate() is called
Then:
  - result.color == "YELLOW"  (not RED — no RED-level signal present)
  - result.triggered_signals contains at least ["drift", "glycogen_debt", "fatigue", "acwr"]
```

### Scenario AT-IG6: RED signal coexists with YELLOW signals
```
Given:
  glycogen_debt = 7.5  (RED: > 6.0)
  fatigue_level = "MEDIUM"  (YELLOW)
When: evaluate() is called
Then:
  - result.color == "RED"  (any RED triggers aggregate RED)
  - result.triggered_signals contains "glycogen_debt"
```

### Scenario AT-IG7: Missing signal keys — graceful handling
```
Given: signals dict = {'readiness_score': 70}  (only one key present)
When: evaluate() is called
Then:
  - No KeyError or exception raised
  - Missing signals are treated as GREEN (neutral)
  - result.color == "GREEN" (only one signal present, it's GREEN)
```

### Scenario AT-IG8: Audit dict is complete
```
Given: any valid signals dict
When: evaluate() is called
Then:
  - result.audit contains a key for each signal present in input
  - result.audit contains 'aggregate' key
  - result.audit contains 'applied_constraints' key
```

### Scenario AT-IG9: Integration — YELLOW gate reduces zone in governance
```
Given:
  IntensityGovernor returns YELLOW result (max_zone=3)
  Governance hard gates do NOT fire
  planned_session = "INTERVALS"
When: full daily_coach.run_morning_routine() executes
Then:
  - Final session plan has max_zone <= 3
  - Telegram message context includes intensity_gate_result
```

### Scenario AT-IG10: Boundary — drift exactly at RED threshold
```
Given: drift_pct = 5.0
When: evaluate() is called
Then:
  - drift signal color == "YELLOW" (> 3.5, <= 5.0 — not RED)
  - drift_pct = 5.001 → RED
```

## Explicit Non-Goals

- **No changes to `DriftEngine`, `GlycogenDebtAccumulator`, `FatigueEngine`, or `ACWREngine` internals** — `IntensityGovernor` reads their outputs, does not modify their implementations.
- **No removal of any existing governance gate** — `IntensityGovernor` runs before them; it does not replace Gate 1 (parasympathetic), Gate 2 (override lockdown), or Gate 3 (CS confidence).
- **No machine learning or adaptive thresholds** — all thresholds in this module are static constants.
- **No persistence of `GateResult`** — the object is ephemeral within a single morning routine execution.
- **No changes to the Telegram message template** — the audit dict is passed as context; the LLM explanation layer uses it as available data.
- **No volume tracking or enforcement** — `volume_modifier` is a multiplier returned to the caller; the module does not track how volume is actually applied downstream.
- **No interaction with `weekly_planner.py`** — the weekly plan is read-only input; the governor does not modify future sessions.
