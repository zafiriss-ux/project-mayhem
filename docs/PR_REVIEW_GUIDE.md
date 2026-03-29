# PR Review Guide — TITAN OS

**Version:** 1.0
**Date:** 2026-03-29
**Canonical reference:** `AGENTS.md` — this guide summarises review practices.
On any conflict: **`AGENTS.md` wins.**

---

## Before You Request Review

The author is responsible for confirming all three mandatory gates pass:

```bash
ruff check .
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

A PR that does not pass all three gates **must not be reviewed** — return it to the author.

---

## Review Checklist

### Safety and Correctness (P0 — block merge if any fail)

- [ ] No governance gate threshold is changed without an accompanying ADR update and evidence label change in `evidence_registry.py`
- [ ] No hard-stop gate (H1–H7) path is modified without tests in `tests/test_p0_safety_gates.py`
- [ ] No new `except Exception:` handler that returns an empty collection without emitting a structured error event
- [ ] No new `eval()`, `exec()`, shell injection, or SQL string interpolation
- [ ] No credentials or secrets in code or test fixtures
- [ ] ML scaffold changes include kill-switch enforcement (`TITAN_ML_KILL_SWITCH` check)

### Test Coverage (P1 — block merge if any fail)

- [ ] Every changed module has corresponding test changes
- [ ] New public functions/methods have at least one positive and one negative test
- [ ] Boundary conditions for safety-critical paths are tested
- [ ] Full test suite still passes (Gate 3)

### Architecture and Design (P1 — block merge if architectural rules violated)

- [ ] No new module in `titan/science/` is added without a model card in `docs/model-cards/`
- [ ] No new threshold constant added to `thresholds.py` without `evidence_registry.py` entry
- [ ] No architectural change (new layer, new inter-module dependency) without an ADR
- [ ] Change does not introduce a circular import or violate the layer ordering (config → core → science → features → orchestration → ui)
- [ ] Out-of-scope findings are in `SCRATCHPAD.md`, not mixed into the PR

### Code Quality (P2 — request changes, non-blocking for merge if acknowledged)

- [ ] No speculative abstractions or "while we're here" cleanups
- [ ] No commented-out code left in
- [ ] Error handling matches the failure domain (only validate at system boundaries)
- [ ] Commit messages follow `T<tier>-<id>: <title>` format

---

## Review Scope Discipline

Reviewers must restrict comments to the diff. Do not comment on pre-existing issues
outside the PR scope — file an OBS in `SCRATCHPAD.md` instead (AGENTS.md E4).

**Exception:** If a pre-existing issue in an unchanged file poses an immediate safety
risk (P0 safety gate violation), call it out explicitly and file it as a blocking OBS.

---

## Approval Requirements

| PR type | Approvals required |
|---------|-------------------|
| Bug fix (Tier 1–2) | 1 (architect or senior engineer) |
| Feature (Tier 3–5) | 1 (architect) |
| Architectural change (ADR required) | Architect sign-off on ADR first, then 1 approval |
| Safety gate threshold change | Architect sign-off + ADR update (no exceptions) |

---

## Merge Requirements

- All three mandatory gates pass in CI
- All blocking review comments resolved
- No unresolved `NEEDS_DECISION` markers in the diff
- Branch is up to date with `main` before merge

---

## Post-Merge

- If the PR closes a TECHNICAL_DEBT.md item: update its status to DONE with commit hash.
- If the PR introduces a new ADR: confirm it appears in the ADR list in `CLAUDE.md`.
- If the PR includes a schema migration: confirm `CHANGES.md` is updated.

---

## Related

- `AGENTS.md` §HARD GATE — mandatory gate definitions
- `AGENTS.md` §6 — test failure protocol
- `docs/CONTRIBUTING.md` — contributor quick-start
- `docs/templates/RFC_TEMPLATE.md` — for pre-PR design discussions
