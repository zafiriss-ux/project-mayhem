# ADR-0021 — Governance Evolvability Protocol

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect + Engineering Lead
**Source:** Architecture Review V5 (2026-03-06) — Lock paralysis risk analysis
**Phase:** 7.8 — Post-Phase-7.7 Hardening
**Supplements:** ADR-0009 (safety gate hardening), ADR-0019 (Phase 7.7 decisions)

---

## Context

`titan/science/governance_engine.py` carries `# ARCHITECTURE LOCK — see ADR-0009 before
modifying` as line 1. This comment was introduced in ADR-0009 to prevent accidental bypass
of the non-bypassable safety gate architecture.

Two risks have emerged as the codebase matures:

**Risk 1 — Lock paralysis.** As the system grows and AI agents assist with implementation,
the comment creates a psychological and procedural barrier that prevents *legitimate*
evolution of governance logic when scientific evidence changes. Engineers and agents alike
avoid the file entirely. This is the "lock paralysis" failure mode: a protective mechanism
that ossifies instead of governing.

**Risk 2 — Undetectable semantic drift.** The current lock is enforced only by human
review. A syntactically correct change that is scientifically wrong (e.g., using the wrong
comparison operator in a gate, misreading a threshold direction) passes all existing tests
because the tests verify system behavior at happy-path values, not at threshold boundaries
for all seven gates.

**Evidence of Risk 2:** `tests/test_p0_safety_gates.py` covers P0 hard-stop boundaries
(20 tests). `tests/test_governance_integration.py` covers contract + boundary tests (27
tests). Neither file constitutes a complete mutation test suite — they do not systematically
verify that changing a threshold constant causes the appropriate gate to change behavior.

---

## Decision

**Replace the comment-based lock with a machine-verifiable Governed Evolution Protocol.**

The goal is not to remove protection — it is to make protection *automated* and *evolvable*
rather than *static* and *psychological*.

### Protocol Components

#### 1. Mutation Test Suite (T4-18)

Create `tests/test_governance_mutation.py`. For each of the 7 gates:
- Boundary-ON case: input exactly at threshold → gate fires → correct lock code returned.
- Boundary-OFF case: input one unit below threshold → gate does not fire.
- Threshold import check: gate logic uses `thresholds.py` constants, not hardcoded literals.

This suite is the machine-enforced lock. Changing gate logic without updating the mutation
tests causes an immediate test failure — a binary signal, not a comment.

#### 2. Comment Replacement

Replace the current `# ARCHITECTURE LOCK` comment with:

```python
# Gate parameters: see thresholds.py + evidence_registry.py.
# To change gate logic: (1) write ADR entry, (2) update evidence_registry.py,
# (3) update tests/test_governance_mutation.py. All three are required.
```

This shifts the protection from "do not touch" to "touch correctly". The ADR entry
provides the rationale trail; the evidence registry update provides the scientific
provenance; the mutation test update provides the automated verification.

#### 3. Evidence Registry Discipline

`titan/config/evidence_registry.py` already provides provenance for threshold constants
(STRONG / MODERATE / HEURISTIC labels). This discipline is extended:

- Every threshold used by a governance gate must have an entry in `evidence_registry.py`.
- Any threshold change must update the entry's `_LAST_REVIEWED` date and `_RATIONALE`.
- The mutation test suite imports from `thresholds.py` — a threshold value change
  automatically propagates to the mutation tests, which verify the gate still fires at
  the new boundary.

#### 4. Evolution Gate (Process)

Any PR that modifies `governance_engine.py` must:
1. Reference the ADR that justifies the change (existing or new).
2. Show `evidence_registry.py` diff (updated provenance).
3. Show `test_governance_mutation.py` diff (updated or new mutation tests).
4. Pass all three mandatory gates (ruff, pytest -W error, pytest).

This is enforced via `.github/pull_request_template.md` (T4-20).

---

## Options Considered

### Option A — Retain comment lock as-is
**Rejected.** Does not address lock paralysis or undetectable semantic drift. As AI agents
take larger implementation roles, comment-based protection is insufficient.

### Option B — Full gate isolation (each gate as independent callable)
Refactor `governance_engine.py` so each gate is an isolated callable unit with typed
`GateInputs → GateResult`. Enables independent testing and composition.

**Deferred to Phase 9.** Valuable but high blast radius — changes the internal API of
`GovernanceEngine` and affects all callers. Risk of introducing regressions during
refactor outweighs the immediate benefit. Phase 9 (lifecycle supervisor) is the right
time for this decomposition.

### Option C — Mutation tests + comment replacement + evolution gate (SELECTED)
Minimal blast radius. Achieves machine-verifiable protection without restructuring
production code. Can be done within T4-18 scope (~3h).

---

## Consequences

- `governance_engine.py:1` comment changes (one line).
- New test file: `tests/test_governance_mutation.py` (~40–60 tests across 7 gates).
- `evidence_registry.py` must be audited: all governance-gate thresholds require entries
  if not already present.
- PR template (T4-20) gains explicit governance-change checklist item.
- T4-05 ("Architecture change lock for `governance_engine.py`") status: considered
  superseded by this protocol. ADR-0021 is the forward-looking governance mechanism.

---

## Relationship to Existing ADRs

| ADR | Relationship |
|-----|-------------|
| ADR-0009 | Established the original safety gate architecture and comment lock. This ADR supersedes the comment-lock mechanism while preserving the non-bypassable gate architecture itself. |
| ADR-0014 | ML scaffold — ML engines are already required to respect governance gates. Mutation tests will include kill-switch interaction cases. |
| ADR-0019 | Phase 7.7 decisions — `data_confidence_low` and `persistence_degraded` ceiling mechanisms are advisory, not lock codes. Mutation tests will verify they do not interfere with hard-stop gate firing. |

---

## Engineer Directives (T4-18 execution)

1. Audit `evidence_registry.py` — ensure all 7 gate thresholds have entries.
2. Create `tests/test_governance_mutation.py` with parametrized boundary tests per gate.
3. Replace `governance_engine.py:1` comment per the wording above.
4. Verify: `python -m pytest tests/test_governance_mutation.py -v` — all tests green.
5. Run full acceptance gate:
   ```bash
   ruff check titan/science/governance_engine.py tests/test_governance_mutation.py
   python -m pytest -q -W error::pytest.PytestWarning
   python -m pytest -q
   ```

---

## Status

Accepted. T4-18 is the engineering execution item. Executes in Tier 4 (after Tier 1–3
items close). Independent — no ordering constraint within Tier 4.
