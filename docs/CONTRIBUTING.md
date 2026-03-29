# Contributing to TITAN OS

**Canonical engineering contract:** `AGENTS.md` — all process rules, gate requirements,
and workflow definitions are in `AGENTS.md`. This document is a quick-start guide.
On any conflict: **`AGENTS.md` wins.**

---

## Quick Start

```bash
# 1. Clone and set up environment
git clone <repo-url>
cd project-mayhem
python --version  # Must be 3.11+
pip install -r requirements.txt

# 2. Configure environment
cp ~/Documents/TITAN/.env.example ~/Documents/TITAN/.env
# Edit .env with your credentials

# 3. Run system check
python system_check.py

# 4. Run all three mandatory gates
ruff check .
python -m pytest -q -W error::pytest.PytestWarning
python -m pytest -q
```

All three gates must be green before any commit.

---

## Branch Naming

- Feature branches: `claude/<short-description>` or `feat/<short-description>`
- Bug fixes: `fix/<short-description>`
- Never push directly to `main`

---

## Commit Message Format

```
T<tier>-<id>: <short title>

# Examples:
T1-21: Add non-training stress safety partition (ADR-0037)
T5-12: Garmin API fragility mitigation Pass 2
```

When no TECHNICAL_DEBT.md item exists: use a short descriptive title.

---

## Definition of Done (non-negotiable)

Before any commit, PR, or `make_pr`:

| Gate | Command | Requirement |
|------|---------|-------------|
| G1 — Lint | `ruff check .` | Zero findings |
| G2 — Strict tests | `python -m pytest -q -W error::pytest.PytestWarning` | Zero warnings, zero failures |
| G3 — Full suite | `python -m pytest -q` | 100% green, count same or higher |

A commit that does not pass all three gates is a process violation (AGENTS.md §HARD GATE).

---

## Test Requirements

- Every change to a module in `titan/` **must** include tests for the new/changed behaviour.
- New module `titan/<path>/<module>.py` → test file `tests/titan/<path>/test_<module>.py`
- Tests go in `tests/` for integration tests, or in root for unit tests.
- Do not use `# type: ignore`, `noqa`, or test suppression markers without a documented reason.

---

## Adding a New Science Engine

1. Place the module in `titan/science/`.
2. Register any new threshold constants in `titan/config/thresholds.py`.
3. Add evidence provenance to `titan/config/evidence_registry.py`.
4. Add a model card to `docs/model-cards/`.
5. Wire into `DailyCoach` only if the engine produces a coaching signal (requires ADR if architecturally significant).
6. Write tests covering boundary conditions and all safety-critical paths.

---

## Adding a New ADR

1. Copy `docs/templates/ADR_TEMPLATE.md` to `docs/adr/<next-number>-<short-title>.md`.
2. Fill all required fields (Date, Status, Deciders, Context, Decision, Consequences, Verification, Review Trigger).
3. Add a line to the ADR list in `CLAUDE.md` and `TECHNICAL_DEBT.md`.
4. ADRs require architect sign-off before being set to `Accepted`.

---

## Out-of-Scope Findings

Found something wrong outside the scope of your current task?

1. **Do NOT fix it now.** (AGENTS.md E4 — no scope creep)
2. Record it as an `OBS` entry in `SCRATCHPAD.md`.
3. The architect will review it and decide whether to create a TECHNICAL_DEBT.md item.

---

## PR Review Guide

See `docs/PR_REVIEW_GUIDE.md`.

---

## Key Files

| File | Purpose |
|------|---------|
| `AGENTS.md` | Canonical engineering contract (authoritative) |
| `TECHNICAL_DEBT.md` | Tiered debt register and current phase status |
| `SCRATCHPAD.md` | Engineer→Architect communication channel |
| `CLAUDE.md` | Architecture context snapshot |
| `docs/templates/` | ADR, RFC, FMEA, Post-Mortem templates |

---

## Getting Help

- Read `AGENTS.md` first — most questions are answered there.
- For architectural questions: file an OBS in `SCRATCHPAD.md`.
- For bugs: open a GitHub Issue with a minimal reproduction.
