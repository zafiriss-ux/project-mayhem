# RFC-XXXX — [Short Title]

**Date:** YYYY-MM-DD
**Status:** Draft | Under Review | Accepted | Rejected | Superseded
**Author:** [Name]
**Reviewers:** [Names]
**Target Phase:** Phase N

---

## Motivation

<!-- Why is this change needed? What problem does it solve? Reference any bug reports, debt items, or ADRs. -->

---

## Proposal

<!-- Describe the proposed change clearly and concisely. Include pseudocode, diagrams, or data model changes as needed. -->

### Interface / API Changes

<!-- List any public interface additions, changes, or removals. -->

```python
# Example: new function signature
def new_function(param: Type) -> ReturnType:
    ...
```

### Data Model Changes

<!-- Describe any schema migrations, new tables, or column changes. -->

### Configuration Changes

<!-- New env variables, threshold constants, or feature flags. -->

---

## Alternatives Considered

### Alternative A — [Name]

**Reason rejected:** …

### Alternative B — [Name]

**Reason rejected:** …

---

## Impact Assessment

| Dimension | Assessment |
|-----------|------------|
| Safety gates | Not affected / Modified — describe |
| Backward compatibility | Fully compatible / Breaking — describe migration path |
| Performance | No change / Improved / Degraded — describe |
| Test coverage required | Unit / Integration / E2E |
| Governance layer | Not affected / Review required |

---

## Rollout Plan

1. …
2. …
3. …

---

## Rollback Plan

<!-- How do we revert if this goes wrong? Feature flag? DB migration rollback? -->

---

## Acceptance Criteria

- [ ] …
- [ ] …
- [ ] All three mandatory gates pass (ruff, pytest -W error, pytest)

---

## Open Questions

- [ ] Question 1 — owner: @handle
- [ ] Question 2 — owner: @handle

---

## Related

- ADR-XXXX
- TECHNICAL_DEBT.md entry T_-_
- `path/to/affected/module.py`
