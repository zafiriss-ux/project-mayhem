# ADR-0024 — Documentation Drift Prevention Protocol

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Master Risk Matrix — Risk #13 (Governance Documentation Rot)
**Phase:** 7.8 Hardening

---

## Context

Risk #13 is classified as **High probability, High severity**. It ranks #3 in the top-5
because documentation drift is already observable: during Phase 7.7 work, CLAUDE.md
contained stale module counts, incorrect ADR ranges, and outdated phase status (found
in Appendix A of `TECHNICAL_DEBT.md`). These were corrected manually, but no automated
check prevented the drift in the first place.

The specific failure mode for governance documentation is particularly dangerous:

1. `CLAUDE.md` lists "Governance Lock Codes (canonical set)" as a free-text comment.
   If a new lock code is added to `governance_engine.py` without updating CLAUDE.md,
   AI agents operating on the file use an incomplete canonical set and may generate
   code that introduces non-canonical lock codes — which then pass test gates because
   the tests only check that lock codes appear in the *engine*, not in the *canonical set*.

2. `evidence_registry.py` carries provenance for threshold constants, but there is no
   automated check that every threshold in `thresholds.py` has a corresponding entry.
   Entries can be silently absent.

3. `docs/adr/README.md` must be manually updated each time a new ADR is created. There
   is currently no enforcement — missed entries mean the index decays.

4. The `TECHNICAL_DEBT.md` tracking table is manually maintained. Items can be marked
   RESOLVED in the prose but left OPEN in the tracking table (or vice versa).

---

## Decision

**Replace manual documentation maintenance with automated consistency checks in CI.**

Four checks are implemented as a new CI job (`docs-consistency`) and as a pytest
module (`tests/test_documentation_consistency.py`).

### Check 1 — Canonical Lock Code Completeness

```python
# Extract all lock codes used in governance_engine.py (string literals in lock() calls)
# Assert they are a subset of the canonical set declared in a constants module.
```

**Implementation:** Move the canonical lock code set from CLAUDE.md prose into
`titan/config/thresholds.py` (or a new `titan/config/governance_constants.py`) as a
Python `frozenset`. The documentation test imports this set and compares it against
the lock codes found via AST inspection of `governance_engine.py`.

**New canonical location:**
```python
# titan/config/thresholds.py
CANONICAL_LOCK_CODES: frozenset[str] = frozenset({
    "HARD_STOP_SAFETY_GATES",
    "VO2_ELIGIBILITY_GATE",
    "FUELING_GATE_LOCK",
    "FUELING_GATE_FLAG",
    "READINESS_2OF4_DOWNGRADE",
    "INTENSITY_GATE_RED",
    "INTENSITY_GATE_YELLOW",
    "PARASYMPATHETIC_GUARD",
    "OVERRIDE_LOCKDOWN",
    "CS_CONFIDENCE_LOCK",
})
```

CLAUDE.md reference becomes: *"See `titan/config/thresholds.py::CANONICAL_LOCK_CODES`"*.
The code is the documentation.

### Check 2 — Evidence Registry Completeness

```python
# Assert: every threshold constant defined in thresholds.py has a corresponding entry
# in evidence_registry.py.
# Implementation: parse thresholds.py for UPPERCASE_CONSTANT = <number> patterns.
# Parse evidence_registry.py for the same constant names.
# Assert the sets are equal.
```

This ensures that when a new threshold is added (e.g., for Phase 8 multi-sport), the
engineer must also add its evidence provenance.

### Check 3 — ADR Index Currency

```python
# Assert: the number of .md files in docs/adr/ (excluding README.md) equals
# the number of rows in the README.md index table.
```

A mismatch means a new ADR was created without updating the index, or an ADR was
deleted without removing the index entry. Either is a process violation.

### Check 4 — TECHNICAL_DEBT.md Consistency

```python
# Assert: every item marked "✅ RESOLVED" in prose has a corresponding row in the
# Tracking table at the bottom of TECHNICAL_DEBT.md.
# Implementation: regex-parse both sections; compare item IDs.
```

### CI Job

Add to `.github/workflows/ci.yml`:

```yaml
docs-consistency:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.11" }
    - run: pip install -r requirements.txt
    - run: python -m pytest tests/test_documentation_consistency.py -v
```

This job runs on every PR and must be green before merge.

### Engineering Execution Items

**T4-21** (new Tier 4 item — documentation consistency test suite):

> Create `tests/test_documentation_consistency.py` with the 4 checks above.
> Add `CANONICAL_LOCK_CODES` frozenset to `titan/config/thresholds.py`.
> Add `docs-consistency` CI job to `ci.yml`.

---

## Options Considered

### Option A — Style guide + review checklist only
The PR template (T4-20) already requires reviewers to check ADR compliance. A style
guide adds prose guidance.

**Rejected as sole mitigation.** Human memory is the failure mode this ADR addresses.
A checklist that depends on the reviewer noticing the drift will miss it under cognitive
load. Automated checks are the only reliable mechanism.

### Option B — Git hooks (pre-commit)
Pre-commit hook that runs the consistency checks before every commit.

**Deferred.** Local pre-commit hooks are optional and not enforced in CI. Engineers can
skip them (`--no-verify`). CI enforcement is mandatory. Both can coexist but CI is the
primary gate.

### Option C — Automated CI checks (SELECTED)
Zero-dependency solution: runs on every PR, cannot be skipped, produces binary pass/fail.
Consistent with existing CI philosophy (ruff, pytest gates).

---

## Consequences

**Positive:**
- Lock code drift becomes a CI failure, not a code review miss.
- Evidence registry gaps are caught at PR time.
- ADR index decays are caught immediately.
- CLAUDE.md no longer needs to maintain the canonical lock code list — it becomes a
  pointer to the Python constant.

**Neutral:**
- CI job adds ~10s to PR pipeline time (negligible).
- Engineers must add evidence registry entries when adding thresholds (already required
  by ADR-0021, now enforced).

**Negative:**
- Check 3 (ADR index) uses file count, not semantic validation. An ADR could be renamed
  without updating the index and the count check would still pass. Acceptable trade-off
  for the implementation effort.

---

## Relationship to Existing ADRs

| ADR | Relationship |
|-----|-------------|
| ADR-0021 | Governance evolvability — mutation tests detect semantic drift in gate logic. This ADR detects documentation drift. Complementary. |
| ADR-0009 | Defines the canonical lock architecture. Check 1 enforces the canonical lock code set. |

---

## Status

Accepted. Engineering execution: **T4-21** (Tier 4 — maintainability; independent,
can be executed in parallel with other Tier 4 items after Tier 1–3 close).
