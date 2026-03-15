# ADR-0049 — Opus QA Scope Reduction: Deterministic-to-CI Migration Policy

**Date:** 2026-03-15
**Status:** Accepted
**Owner:** Architect
**Implements:** T5-37, T5-38
**Related:** PILOT-01 (TECHNICAL_DEBT.md), AGENTS.md §Opus QA Trigger Policy, ADR-0047 (Architecture Fitness Functions), ADR-0048 (API Authentication Layer)

---

## §1 Context

PILOT-01 established Opus QA as an advisory layer between Codex implementation and the mandatory gates. The pilot has been active since 2026-03-08 and has produced verdicts for T5-08-B D1, and most recently T5-11 (QA PASS, 2026-03-15).

In reviewing the T5-11 verdict and prior Opus QA sessions, a structural pattern has emerged: **Opus QA is doing two categorically different kinds of work in a single review pass:**

1. **Category A — machine-checkable:** Deterministic checks that can be codified as CI tests. Examples:
   - Threshold source assertions (are constants imported from `thresholds.py` and not inline?)
   - Test file naming conventions (does `titan/<path>/<module>.py` have a matching `tests/titan/<path>/test_<module>.py`?)
   - Evidence registry completeness (does every extracted constant have a provenance entry in `evidence_registry.py`?)
   - Category A literal presence checks (are previously identified inline Category A literals still present?)
   - Mandatory gate execution confirmation (did Codex confirm gate output?)

2. **Category B — judgment-required:** Checks that require semantic understanding of the task, boundary conditions, architectural intent, and test design. Examples:
   - Do the tests actually target the acceptance criteria in the debt item?
   - Are the critical edge cases exercised (boundary values, error paths, invariant violations)?
   - Are regression tests present for the changed behaviour?
   - Does the test design prevent the specific failure modes the task was created to fix?
   - Is the parametrization strategy appropriate for the input space?

**The problem:** Category A findings are being reviewed by Opus on every Path B pass. This consumes Opus QA cycles on checks that:
- Always have the same correct answer (the check is binary: present / absent)
- Can be run by `pytest` without human judgment
- Are already partially covered by existing hygiene tests but with gaps
- Do not benefit from the semantic reasoning that makes Opus QA valuable

If a Category A finding appears repeatedly in Opus QA verdicts, it indicates a CI gap — a pattern that should have been encoded as a test already, not a pattern that warrants ongoing Opus review.

---

## §2 Decision

### 2.1 Two-category taxonomy for Opus QA findings

All Opus QA findings are classified as either Category A or Category B:

| Category | Definition | Owner |
|---|---|---|
| **A — machine-checkable** | The finding can be expressed as a deterministic test: given this input, assert this property holds. No semantic judgment required. The test either passes or fails reproducibly. | CI (pytest) |
| **B — judgment-required** | The finding requires understanding of: the task's acceptance criteria, the architectural intent behind the requirement, what failure modes the task was created to prevent, or whether the test design is appropriate for the input space. A test runner cannot make this call. | Opus QA |

### 2.2 Migration policy: Category A findings → CI tests

**Principle:** A Category A finding that has appeared in any Opus QA verdict is evidence of a CI gap. The correct resolution is to write a CI test, not to continue relying on Opus to re-check the same pattern on every future review.

**Migration rule:** When a Category A finding is identified (either in a new verdict or in retrospect from a historical verdict), a CI test must be created that checks the pattern deterministically. Once the CI test exists and is validated, the pattern is removed from Opus QA scope.

**Scope reduction effect:** As Category A patterns migrate to CI, Opus QA scope contracts to Category B only. This is the intended steady-state: Opus reviews judgment-required test quality; CI checks machine-checkable conventions.

### 2.3 Validating test requirement for each CI gate

Every CI test created under this policy (to replace a Category A Opus finding) must itself have a **validating meta-test** — a test that:
1. Provides known-bad input to the CI gate
2. Asserts the CI gate fails or raises as expected on that input
3. Lives alongside the CI gate in the same test file

**Rationale:** A CI gate without a validating test is an unverified gate. It may pass on bad input, miss the exact failure mode, or silently no-op due to a bug in the gate itself. The meta-test is the proof that the gate is correctly wired.

### 2.4 Opus QA scope in steady state

After Category A migration, Opus QA scope is bounded to Category B findings only:

**In scope (Category B — Opus retains):**
- Do the tests actually cover the acceptance criteria in the debt item?
- Are critical edge cases exercised (boundary values, error paths, invariant violations)?
- Are regression tests present for the changed behaviour?
- Is the test design appropriate to prevent the specific failure modes the task addresses?
- Are parametrize / property-based tests used where the input space warrants it?

**Out of scope (Category A — CI handles after migration):**
- Threshold source assertions (centralization conventions)
- Test file naming convention compliance
- Evidence registry completeness
- Category A literal presence re-checks
- Re-running or confirming mandatory gate outputs (Gates 1–3 are always Codex's responsibility)

**Trigger policy unchanged:** Opus QA is still not triggered by default. Path A items proceed without Opus involvement unless the architect explicitly opts a task into Path B. This ADR does not alter the trigger criteria — it narrows the scope of what Opus does once triggered.

---

## §3 Category A patterns identified for initial migration (T5-37 triage list)

The following Category A patterns have appeared in Opus QA verdicts or hygiene audits and are candidates for CI gate migration under T5-37:

| Pattern | Description | Existing partial coverage |
|---|---|---|
| Threshold source | Constants in science modules imported from `thresholds.py`; no inline Category A literals | `tests/test_constants_hygiene.py` (partial) |
| Evidence registry completeness | Every constant in `thresholds.py` has a matching provenance entry in `evidence_registry.py` | None identified |
| Test file naming | `titan/<path>/<module>.py` → `tests/titan/<path>/test_<module>.py` | `tests/test_phase3_hygiene.py` (partial) |
| Mandatory gate confirmation | Codex must show gate output before Path B closure is authorized | Process-enforced; not a test |

This list is the starting triage. T5-37 implementation must confirm, add, or remove patterns based on a fresh audit before writing CI gates.

---

## §4 Safeguard invariants

1. **No reduction in meaningful coverage.** Category A migration must not reduce the total detection surface. Every migrated pattern must be checked more reliably by CI than it was by Opus.

2. **Every CI gate has a validating test (T5-38 paired execution rule).** No CI gate is written without its meta-test. T5-37 and T5-38 are executed in the same implementation pass, per-gate.

3. **Opus QA verdict logging rule unchanged.** All Opus verdicts (PASS or FAIL) are still logged per the PILOT-01 verdict logging rule. The log format is unchanged.

4. **PILOT-01 status unchanged.** PILOT-01 remains PILOT. This ADR narrows Opus scope; it does not promote or close PILOT-01. PILOT-01 promotion/closure requires its own binary evaluation per the criteria in TECHNICAL_DEBT.md.

5. **No retrospective scope re-classification of historical items.** This policy applies forward from 2026-03-15. Historical tasks (T5-36 and earlier) are not retrofitted.

---

## §5 New Debt Items

**T5-37 · Opus QA — Category A (machine-checkable) findings not yet migrated to CI gates**
- See TECHNICAL_DEBT.md T5-37

**T5-38 · Opus QA — CI gates replacing Category A findings lack validating tests**
- See TECHNICAL_DEBT.md T5-38

---

## §6 Consequences

**Positive:**
- Opus QA cycles are spent entirely on judgment-required test quality review (Category B)
- Category A patterns are checked on every CI run — more frequent, more durable, not dependent on Opus invocation
- False confidence from absent or incorrect CI gates is caught by T5-38 meta-tests
- Scope reduction makes Opus QA faster and its signal higher quality

**Neutral:**
- The triage pass (T5-37 §3 audit) requires one implementation pass before CI gates are written
- Some patterns may require architect classification before they can be assigned to Category A or B

**Negative:**
- T5-37 / T5-38 require implementation effort before the scope reduction takes effect
- If a Category A pattern is misclassified as B (or vice versa), the meta-test in T5-38 is the safety net

---

**ADR-0049 status: Accepted — 2026-03-15**
**Codex handoff: T5-37 and T5-38 authorized — execution order after T5-13 (Path A for both)**
