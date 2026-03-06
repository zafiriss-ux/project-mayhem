## Summary

<!-- One paragraph: what changed and why. -->

## Tier classification

- [ ] T1 Data Integrity
- [ ] T2 Observability
- [ ] T3 Dependencies
- [ ] T4 Maintainability
- [ ] T5 Future / Experimental
- [ ] Hotfix / Unclassified

Debt item(s) addressed: <!-- e.g. T4-18, T4-19 -->

---

## Architecture checklist (ADR-0021 — mandatory for all PRs)

### Governance layer

- [ ] No numeric threshold literals added to `governance_engine.py`
      (must use `thresholds.py` constants — verified by `test_architectural_invariants.py`)
- [ ] Any new governance lock code added to `_CANONICAL_LOCK_CODES` in
      `tests/test_architectural_invariants.py` **and** the lock-code table in `CLAUDE.md`
- [ ] Boundary-ON and boundary-OFF tests added/updated in
      `tests/test_governance_mutation.py` for any changed gate logic

### Exception handling

- [ ] No new `except Exception: pass` (silent swallow) in `titan/` outside `titan/ui/`
- [ ] Any new except clause in `titan/ui/` is observable: logs a warning **and**
      prints a fallback message to the user

### Persistence / database

- [ ] Schema changes increment `SCHEMA_VERSION` in `database.py` and add a
      corresponding `_apply_vN_migrations()` method
- [ ] No new direct `self.conn` access added outside `with self._lock:` in
      `DatabaseManager` (unless in the approved init list)

### Notification / degraded mode

- [ ] Any new notification path routes through `NotificationGateway` (not direct bot call)
- [ ] New degraded-mode conditions registered with `DegradedModeTracker`

---

## Mandatory gates (must all be ✅ before requesting review)

```
ruff check .
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

- [ ] Gate 1 — `ruff check .` → zero findings
- [ ] Gate 2 — `pytest -q -W error::pytest.PytestWarning` → 100% green, no warnings
- [ ] Gate 3 — `pytest -q` → 100% green, test count same or higher

---

## Test coverage

- [ ] New or changed logic has at least one happy-path test and one boundary/error test
- [ ] No tests deleted (if a test was wrong, it was fixed, not removed)

---

## Reviewer notes

<!-- Anything that deviates from the above (with justification), or specific
areas you want reviewers to focus on. -->
